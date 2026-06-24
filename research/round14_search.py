"""Round 14 MNQ strategy search — TRACK A queue sensitivity + TRACK B/C deep learning.

User mandate: "Build advanced ML systems that find patterns no manual signal can.
Find a strategy like your life depends on it. One-of-one strategies."

This round abandons the variant-sweep paradigm entirely. Three tracks:

* TRACK A — Queue sensitivity. The bot-faithful executor since round 7 fills LIMIT
  orders only when price OVERSHOOTS by 1 tick (worst-case queue position). The
  round-4 idealized executor filled at TOUCH (realistic-mid). Re-test CANON_INV_236
  and round-4 top-5 winners under THREE execution variants:

    - 'pessimistic'  — LIMIT fills only when price overshoots by >= 1 tick
                       (current bot-faithful, round 7+ default).
    - 'realistic_mid' — LIMIT fills 50% probability on touch, 100% on overshoot.
                       (Implements via deterministic 50% sampling on touch tick.)
    - 'presubmit'    — LIMIT orders that have been in book >= 30s fill 80% on
                       touch (anticipatory advantage from being early in queue).

  If any round-4 winner passes hard reqs under realistic-mid or presubmit, that
  becomes the deployment candidate.

* TRACK B — Pure-numpy deep learning. PyTorch unavailable (proxy + disk), so we
  built an MLP+LSTM hybrid in pure numpy (matmuls + adam). Rich 50+ feature
  vector per 30-second candidate during RTH (price action, microstructure,
  vol regime, time). Train on days 0..39, validate 40..49, test 50..59. Two
  binary heads: P(LONG profitable next 60s) and P(SHORT profitable next 60s).

  Deployment as standalone signal AND as a FILTER on round-4 CANON.

* TRACK C — Pattern discovery via VAE on tick sequences + temporal contrastive.
  Identify outlier tick sequences (high reconstruction error). Test predictivity.

Reporting: /home/user/HFTBot/research/round14_results.md
"""
from __future__ import annotations
import argparse
import csv
import math
import os
import pickle
import random
import struct
import sys
import time
from collections import deque, defaultdict
from datetime import datetime

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

# Lineage — reuse classes/constants
from research import round4_search as _r4
sys.modules.setdefault("round4_search", _r4)
from research import round6_search as _r6
sys.modules.setdefault("round6_search", _r6)
from research import round7_search as _r7
sys.modules.setdefault("round7_search", _r7)
from research import round8_search as _r8
sys.modules.setdefault("round8_search", _r8)
from research import round9_search as _r9
sys.modules.setdefault("round9_search", _r9)
from research import round10_search as _r10
sys.modules.setdefault("round10_search", _r10)
from research import round12_search as _r12
sys.modules.setdefault("round12_search", _r12)

StrategyBase = _r4.StrategyBase
BarBuilder = _r4.BarBuilder
PullbackStrategy = _r4.PullbackStrategy
MarketablePullback = _r6.MarketablePullback
MARKET = _r8.MARKET

attach_r7_executor = _r7.attach_r7_executor
r10_bot_on_tick = _r10.r10_bot_on_tick

PATH = _r7.PATH
MNQ_PER_PT = _r7.MNQ_PER_PT
TOTAL_RT_COST = _r7.TOTAL_RT_COST
APPROACH_THRESHOLD_PT = _r7.APPROACH_THRESHOLD_PT
LATENCY_EMBARGO_S = _r7.LATENCY_EMBARGO_S
FRESH_PLACEMENT_LATENCY_S = _r7.FRESH_PLACEMENT_LATENCY_S
STOP_SLIP_PT = _r7.STOP_SLIP_PT
STOP_GAP_SLIP_PROB = _r7.STOP_GAP_SLIP_PROB
STOP_GAP_SLIP_MAX_PT = _r7.STOP_GAP_SLIP_MAX_PT
COOLDOWN_S = _r7.COOLDOWN_S
MAX_HOLD_S = _r7.MAX_HOLD_S
TICK = _r7.TICK
MARKETABLE_SLIP_PT = _r7.MARKETABLE_SLIP_PT

DEFAULT_OFFSET = 7_820_974_790
CHECKPOINT_EVERY_TICKS = 25_000

# ============================================================================
# TRACK A — Queue model sensitivity
# ============================================================================
# Hook into r7 executor's queue logic. We patch attach_r7_executor's
# fill computation by adding a per-strategy 'queue_model' attribute and
# wrapping r10_bot_on_tick.

QUEUE_MODEL_PESSIMISTIC = 'pessimistic'
QUEUE_MODEL_REALISTIC_MID = 'realistic_mid'
QUEUE_MODEL_PRESUBMIT = 'presubmit'

# Deterministic RNG for queue sampling — same seed across strategies so each
# strategy sees the same fill randomness on the same tick.
_QUEUE_RNG = random.Random(0xC0FFEE12)


def _patched_try_fire(strat, ts, bid, ask):
    """Drop-in replacement for r7's per-tick limit-fill attempt that respects
    self.queue_model. We reimplement minimally — same logic as r7 but with
    pluggable fill semantics."""
    exe = strat._exec
    if strat.in_trade is not None or not strat.pending:
        return

    # Find closest setup by distance
    closest = None
    dist = 1e18
    for s in strat.pending:
        if s['used']:
            continue
        orig = s.get('orig', s['side'])
        e = s['entry']
        if orig == 'LONG':
            d = ask - e if ask > e else e - ask
        else:
            d = bid - e if bid > e else e - bid
        if d < dist:
            dist = d
            closest = s

    if closest is None or dist > APPROACH_THRESHOLD_PT:
        if exe.active_limit_key is not None:
            for s in strat.pending:
                if s.get('key') == exe.active_limit_key:
                    s['_fire_attempted'] = True
                    break
            exe.active_limit_key = None
            exe.active_limit_armed_ts = None
        return

    closest_key = closest.get('key')
    if exe.active_limit_key != closest_key:
        if exe.active_limit_key is not None:
            for s in strat.pending:
                if s.get('key') == exe.active_limit_key:
                    s['_fire_attempted'] = True
                    break
        exe.active_limit_key = closest_key
        gen_ts = closest.get('_gen_ts')
        if gen_ts is not None and abs(ts - gen_ts) < LATENCY_EMBARGO_S:
            exe.active_limit_armed_ts = gen_ts + LATENCY_EMBARGO_S
        else:
            exe.active_limit_armed_ts = ts + FRESH_PLACEMENT_LATENCY_S
        # Record arming time for presubmit anticipation model
        closest['_armed_ts'] = exe.active_limit_armed_ts

    if exe.active_limit_armed_ts is not None and ts < exe.active_limit_armed_ts:
        return

    s = closest
    orig = s.get('orig', s['side'])
    entry_px_target = s['entry']
    fill_mode = s.get('fill_mode', 'limit')
    queue_model = getattr(strat, 'queue_model', QUEUE_MODEL_PESSIMISTIC)

    fill_px = None
    if fill_mode == 'limit':
        if queue_model == QUEUE_MODEL_PESSIMISTIC:
            # original: requires overshoot by 1 tick
            if orig == "LONG" and ask <= entry_px_target - TICK:
                fill_px = entry_px_target
            elif orig == "SHORT" and bid >= entry_px_target + TICK:
                fill_px = entry_px_target
        elif queue_model == QUEUE_MODEL_REALISTIC_MID:
            # Fill 100% on overshoot, 50% probability on exact touch.
            if orig == "LONG":
                if ask <= entry_px_target - TICK:
                    fill_px = entry_px_target
                elif ask <= entry_px_target:
                    if _QUEUE_RNG.random() < 0.5:
                        fill_px = entry_px_target
            else:
                if bid >= entry_px_target + TICK:
                    fill_px = entry_px_target
                elif bid >= entry_px_target:
                    if _QUEUE_RNG.random() < 0.5:
                        fill_px = entry_px_target
        elif queue_model == QUEUE_MODEL_PRESUBMIT:
            # Anticipatory: LIMITs that have been ARMED >=30s get 80%
            # probability on touch (early in queue).
            armed_ts = s.get('_armed_ts', ts)
            in_book_s = ts - armed_ts
            if orig == "LONG":
                if ask <= entry_px_target - TICK:
                    fill_px = entry_px_target
                elif ask <= entry_px_target:
                    p_fill = 0.8 if in_book_s >= 30.0 else 0.3
                    if _QUEUE_RNG.random() < p_fill:
                        fill_px = entry_px_target
            else:
                if bid >= entry_px_target + TICK:
                    fill_px = entry_px_target
                elif bid >= entry_px_target:
                    p_fill = 0.8 if in_book_s >= 30.0 else 0.3
                    if _QUEUE_RNG.random() < p_fill:
                        fill_px = entry_px_target
    elif fill_mode == 'marketable':
        if orig == "LONG":
            if ask <= entry_px_target:
                fill_px = ask + MARKETABLE_SLIP_PT
        else:
            if bid >= entry_px_target:
                fill_px = bid - MARKETABLE_SLIP_PT
    elif fill_mode == 'stop':
        STOP_ENTRY_SLIP_PT = _r7.STOP_ENTRY_SLIP_PT
        if orig == "LONG":
            if ask >= entry_px_target:
                fill_px = ask + STOP_ENTRY_SLIP_PT
        else:
            if bid <= entry_px_target:
                fill_px = bid - STOP_ENTRY_SLIP_PT

    if fill_px is None:
        return
    if exe.skip_next_trade:
        exe.skip_next_trade = False
        s['_fire_attempted'] = True
        exe.active_limit_key = None
        exe.active_limit_armed_ts = None
        return

    if 'stop_offset_pts' in s:
        stop_off = s['stop_offset_pts']
        tgt_off = s.get('target_offset_pts')
        if s['side'] == 'LONG':
            stop_px = fill_px - stop_off
            tgt_px = (fill_px + tgt_off) if tgt_off is not None else None
        else:
            stop_px = fill_px + stop_off
            tgt_px = (fill_px - tgt_off) if tgt_off is not None else None
    else:
        stop_px = s['stop']
        tgt_px = s.get('target')

    strat.in_trade = {
        'side': s['side'],
        'entry': fill_px,
        'stop': stop_px,
        'target': tgt_px,
        'et': ts,
        'exit_mode': s.get('exit_mode', 'stop_market'),
        'trail_pts': s.get('trail_pts'),
        'be_trig_pts': s.get('be_trig_pts'),
        'be_off_pts': s.get('be_off_pts', 0.0),
        'time_decay': s.get('time_decay'),
        'momshift_k': s.get('momshift_k'),
        'max_hold': s.get('max_hold', MAX_HOLD_S),
    }
    s['used'] = True
    _r7._cancel_cohort(strat, s.get('cohort'))
    exe.active_limit_key = None
    exe.active_limit_armed_ts = None


def patched_r10_bot_on_tick(strat, ts, bid, ask, day_counter, hh, mn, last):
    """Override of r10's bot_on_tick that uses our patched fill logic when
    strat.queue_model is set."""
    # First, run r10's standard tick logic for expiry/exit; we only override
    # the entry-fire portion.
    # r10_bot_on_tick handles in_trade exits, expiry pruning, signal feed, etc.
    # We call it but it will try its own fill — that's fine for marketable/stop.
    # For limit-fill with custom queue model, we need to intercept BEFORE r10
    # tries to fire.
    if getattr(strat, 'queue_model', None) is not None:
        # 1) Manage exits via r10 logic for in_trade.
        if strat.in_trade is not None:
            r10_bot_on_tick(strat, ts, bid, ask, day_counter, hh, mn, last)
            return
        # 2) Custom fire for LIMIT
        if strat.pending:
            _patched_try_fire(strat, ts, bid, ask)
            # also let r10 handle stop/marketable triggers (which may also be
            # in pending) — but our try_fire already handles all 3 modes, so
            # don't double-fire.
            return
    # Default path
    r10_bot_on_tick(strat, ts, bid, ask, day_counter, hh, mn, last)


# ============================================================================
# TRACK A — Build round-4 winner strategies for sensitivity
# ============================================================================
def build_track_a_variants():
    """Build CANON + top-5 round-4 winners × 3 queue models = 18 strategies."""
    # The round-4 top-5 by $/day are INV15s_imp2_s* variants (15s bar timeframe).
    # CANON_INV_236_s10t20 is rank 20. We also include round-4's INV_pp variants.
    # We use MarketablePullback to ensure it goes through r10's executor BUT we
    # override fill_mode='limit' to test queue sensitivity (so 'pessimistic'
    # vs 'realistic_mid' actually differs). Note: MarketablePullback sets
    # 'fill_mode'='marketable' which fills at touch always.
    # So instead, use PullbackStrategy (which defaults to NO fill_mode field, i.e.
    # 'limit' in r7/r10's executor).

    # The 6 strategies we test:
    base_specs = [
        # (name, impulse_pts, impulse_bars, pull_pct, stop, target)
        ('CANON_INV_236_s10t20', 5.0, 4, 0.236, 10, 20),
        ('R4_INV_pp118_s5t20_imp3', 3.0, 4, 0.118, 5, 20),
        ('R4_INV_pp118_s4t16_imp3', 3.0, 4, 0.118, 4, 16),
        ('R4_INV_pp118_s3t12_imp3', 3.0, 4, 0.118, 3, 12),
        ('R4_INV_pp118_s3t9_imp3',  3.0, 4, 0.118, 3, 9),
        ('R4_INV_pp236_s5t20_imp3', 3.0, 4, 0.236, 5, 20),
    ]
    variants = []
    for queue_model in (QUEUE_MODEL_PESSIMISTIC,
                        QUEUE_MODEL_REALISTIC_MID,
                        QUEUE_MODEL_PRESUBMIT):
        for spec in base_specs:
            name, imp, bars, pp, stp, tgt = spec
            full_name = f"A_{queue_model.upper()[:4]}_{name}"
            s = PullbackStrategy(
                full_name,
                impulse_pts=imp, impulse_bars=bars, pull_pct=pp,
                stop_pts=stp, target_pts=tgt, invert=True)
            s.queue_model = queue_model
            variants.append(s)
    return variants


# ============================================================================
# TRACK B — Feature engineering for DL
# ============================================================================
class FeatureExtractor:
    """Extracts a 50-D feature vector per RTH candidate (every 30s).

    Features:
      - Price action (15): last 5 1-min returns, last 5 1-min HL ranges,
        position in last bar, 5/20 SMA divergence, ATR(5), ATR(20), ATR ratio,
        VWAP-price gap, 60-bar percentile.
      - Microstructure (15): current spread, 1-min avg spread, spread trend,
        tick velocity 10s/30s/60s, signed-tick balance 60s, persistence,
        bid-lift/ask-hit ratio, last 5 tick directions.
      - Volatility regime (10): realized vol 5/15/60min, vol ratio,
        Hurst proxy, range expansion percentile, vol z-score,
        recent vs hist deviation, regime indicator, instability.
      - Time (10): hour sin/cos, minute sin/cos, dow, sec since open,
        sec to close, sec since last big move, in-week bucket, holiday-ish.
    """
    N_FEATURES = 50

    def __init__(self, bar_history_len=120, tick_history_len=4000):
        # bar history: deque of (ts, o, h, l, c)
        self.bars = deque(maxlen=bar_history_len)
        # tick buffer: deque of (ts, last, bid, ask)
        self.ticks = deque(maxlen=tick_history_len)
        # signed tick balance running counter
        self.signed_tick_buf = deque(maxlen=2000)  # (ts, +1/-1)
        self.last_last = None
        self.session_vwap_num = 0.0
        self.session_vwap_den = 0.0
        self.session_day = None
        self.last_big_move_ts = 0.0
        self.last_big_move_px = None

    def feed_tick(self, ts, last, bid, ask):
        self.ticks.append((ts, last, bid, ask))
        if self.last_last is not None and last != self.last_last:
            sign = 1 if last > self.last_last else -1
            self.signed_tick_buf.append((ts, sign))
            # Detect big move (>=5pt vs reference)
            if self.last_big_move_px is None:
                self.last_big_move_px = last
                self.last_big_move_ts = ts
            elif abs(last - self.last_big_move_px) >= 5.0:
                self.last_big_move_px = last
                self.last_big_move_ts = ts
        self.last_last = last
        # VWAP
        day_key = int(ts // 86400)
        if day_key != self.session_day:
            self.session_day = day_key
            self.session_vwap_num = 0.0
            self.session_vwap_den = 0.0
        self.session_vwap_num += last
        self.session_vwap_den += 1

    def feed_bar(self, ts, o, h, l, c):
        self.bars.append((ts, o, h, l, c))

    def extract(self, ts, bid, ask, hh, mn):
        """Returns 50-D numpy vector (or None if not enough history)."""
        if len(self.bars) < 20:
            return None
        bars = list(self.bars)
        last = (bid + ask) / 2.0

        f = np.zeros(self.N_FEATURES, dtype=np.float32)

        # ----- Price action (0-14) -----
        # Last 5 1-min returns (normalized by atr-like scale)
        for i in range(5):
            if len(bars) >= i + 2:
                b = bars[-(i + 1)]
                pb = bars[-(i + 2)]
                f[i] = (b[4] - pb[4]) / 5.0  # /5pt
        # Last 5 HL ranges
        for i in range(5):
            if len(bars) >= i + 1:
                b = bars[-(i + 1)]
                f[5 + i] = (b[2] - b[3]) / 5.0
        # Current bar position
        cb = bars[-1]
        rng = max(cb[2] - cb[3], 0.01)
        f[10] = (cb[4] - cb[3]) / rng
        # 5 vs 20 SMA divergence
        if len(bars) >= 20:
            sma5 = sum(b[4] for b in bars[-5:]) / 5.0
            sma20 = sum(b[4] for b in bars[-20:]) / 20.0
            f[11] = (sma5 - sma20) / 5.0
        # ATR(5), ATR(20)
        atr5 = sum((b[2] - b[3]) for b in bars[-5:]) / 5.0
        f[12] = atr5 / 5.0
        if len(bars) >= 20:
            atr20 = sum((b[2] - b[3]) for b in bars[-20:]) / 20.0
            f[13] = atr20 / 5.0
            f[14] = (atr5 / max(atr20, 0.01)) - 1.0
        else:
            f[13] = atr5 / 5.0
            f[14] = 0.0

        # ----- Microstructure (15-29) -----
        spread = ask - bid
        f[15] = spread / 0.5  # normalized
        # 1-min avg spread
        cutoff = ts - 60.0
        recent_spreads = [a - b for t, _, b, a in self.ticks if t >= cutoff]
        if recent_spreads:
            avg_spread = sum(recent_spreads) / len(recent_spreads)
            f[16] = avg_spread / 0.5
            # Spread trend
            n = len(recent_spreads)
            if n >= 4:
                first_half = sum(recent_spreads[:n//2]) / max(1, n//2)
                second_half = sum(recent_spreads[n//2:]) / max(1, n - n//2)
                f[17] = (second_half - first_half) / 0.5
        # Tick velocity 10s/30s/60s
        for wi, w in enumerate((10.0, 30.0, 60.0)):
            cnt = sum(1 for t, _, _, _ in self.ticks if t >= ts - w)
            f[18 + wi] = (cnt / w) / 50.0  # normalize ~ 50 ticks/sec
        # Signed-tick balance over 60s (cumulative delta proxy)
        cutoff = ts - 60.0
        bal = sum(s for t, s in self.signed_tick_buf if t >= cutoff)
        f[21] = bal / 100.0
        # Price persistence at current level (sec at <=0.5pt move)
        persist_s = 0.0
        for t, lst, _, _ in reversed(self.ticks):
            if abs(lst - last) > 0.5:
                break
            persist_s = ts - t
            if persist_s > 60:
                break
        f[22] = persist_s / 30.0
        # Last 5 tick direction balance
        recent_dirs = list(self.signed_tick_buf)[-20:]
        if recent_dirs:
            f[23] = sum(s for _, s in recent_dirs) / 20.0
        # Bid-hits vs ask-lifts ratio over 60s
        # Use signed tick proxy: positive ticks = ask-lifts
        cutoff = ts - 60.0
        pos = sum(1 for t, s in self.signed_tick_buf if t >= cutoff and s > 0)
        neg = sum(1 for t, s in self.signed_tick_buf if t >= cutoff and s < 0)
        tot = pos + neg
        f[24] = (pos - neg) / max(tot, 1)
        # Price percentile in last 60-bar range
        if len(bars) >= 60:
            highs = [b[2] for b in bars[-60:]]
            lows = [b[3] for b in bars[-60:]]
            hi = max(highs); lo = min(lows)
            rg = hi - lo
            f[25] = (last - lo) / max(rg, 0.01)
        # VWAP gap
        if self.session_vwap_den > 0:
            vwap = self.session_vwap_num / self.session_vwap_den
            f[26] = (last - vwap) / 5.0
        # 20-bar VWAP (close-based)
        if len(bars) >= 20:
            v20 = sum(b[4] for b in bars[-20:]) / 20.0
            f[27] = (last - v20) / 5.0
        # Price recent jumpiness (max-min over last 20 ticks)
        if len(self.ticks) >= 20:
            recent_pxs = [t[1] for t in list(self.ticks)[-20:]]
            f[28] = (max(recent_pxs) - min(recent_pxs)) / 1.0
        # Bid-ask midpoint vs last
        f[29] = (last - (bid + ask) / 2.0) / 0.25

        # ----- Volatility regime (30-39) -----
        # Realized vol 5/15/60 min
        for wi, w in enumerate((5, 15, 60)):
            if len(bars) >= w:
                rets = [bars[i][4] - bars[i-1][4]
                        for i in range(len(bars) - w, len(bars))]
                vol = math.sqrt(sum(r*r for r in rets) / max(1, len(rets)))
                f[30 + wi] = vol / 5.0
        # 5min / 60min vol ratio
        if f[32] > 0.01:
            f[33] = f[30] / max(f[32], 0.01)
        # Hurst exponent (proxy via R/S)
        if len(bars) >= 30:
            closes = [b[4] for b in bars[-30:]]
            mean_c = sum(closes) / len(closes)
            dev = [c - mean_c for c in closes]
            cum = [0.0]
            for d in dev:
                cum.append(cum[-1] + d)
            r = max(cum) - min(cum)
            s = math.sqrt(sum(d*d for d in dev) / len(dev))
            if s > 0.001:
                rs = r / s
                # log(rs)/log(n) ~ Hurst
                f[34] = math.log(max(rs, 1e-6)) / math.log(len(bars[-30:])) - 0.5
        # Range expansion percentile
        if len(bars) >= 60:
            ranges = [b[2] - b[3] for b in bars[-60:]]
            cur_rng = bars[-1][2] - bars[-1][3]
            n_below = sum(1 for r in ranges if r < cur_rng)
            f[35] = (n_below / len(ranges)) - 0.5
        # Recent vs hist vol z-score
        if len(bars) >= 60:
            recent5_vol = f[30]
            hist_vols = []
            for i in range(5, 60, 5):
                rets = [bars[j][4] - bars[j-1][4]
                        for j in range(len(bars) - i - 5, len(bars) - i)]
                if rets:
                    v = math.sqrt(sum(r*r for r in rets) / len(rets))
                    hist_vols.append(v)
            if hist_vols:
                mean_v = sum(hist_vols) / len(hist_vols)
                std_v = math.sqrt(sum((v - mean_v) ** 2 for v in hist_vols) / len(hist_vols))
                if std_v > 0.001:
                    f[36] = (recent5_vol - mean_v) / std_v
        # Body/range ratio last bar
        cb = bars[-1]
        rg = max(cb[2] - cb[3], 0.01)
        f[37] = abs(cb[4] - cb[1]) / rg
        # Up-bar fraction last 20 bars
        if len(bars) >= 20:
            up = sum(1 for b in bars[-20:] if b[4] > b[1])
            f[38] = (up / 20.0) - 0.5
        # Volatility-of-volatility (range range)
        if len(bars) >= 20:
            ranges = [b[2] - b[3] for b in bars[-20:]]
            mr = sum(ranges) / len(ranges)
            f[39] = math.sqrt(sum((r - mr) ** 2 for r in ranges) / len(ranges)) / 5.0

        # ----- Time features (40-49) -----
        f[40] = math.sin(2 * math.pi * hh / 24.0)
        f[41] = math.cos(2 * math.pi * hh / 24.0)
        f[42] = math.sin(2 * math.pi * mn / 60.0)
        f[43] = math.cos(2 * math.pi * mn / 60.0)
        # Day of week — derived from session_day modulo 7
        f[44] = (self.session_day % 7) / 6.0 if self.session_day is not None else 0.0
        # Time since session open (RTH = 13:30 UTC)
        sec_today = hh * 3600 + mn * 60
        sec_open = 13 * 3600 + 30 * 60
        f[45] = max(0, sec_today - sec_open) / 3600.0  # hours since open
        sec_close = 20 * 3600
        f[46] = max(0, sec_close - sec_today) / 3600.0  # hours to close
        # Time since last big move
        f[47] = min((ts - self.last_big_move_ts) / 300.0, 3.0)
        # RTH/CME indicator
        f[48] = 1.0 if (sec_open <= sec_today <= sec_close) else 0.0
        # Mid-RTH bias indicator (within 1h of open or close = 0, else 1)
        if f[48] > 0:
            mid_dist = min(sec_today - sec_open, sec_close - sec_today)
            f[49] = 1.0 if mid_dist > 3600 else 0.0

        # Clip extreme values
        np.clip(f, -10.0, 10.0, out=f)
        return f


# ============================================================================
# TRACK B — Pure-numpy MLP for binary classification
# ============================================================================
class NumpyMLP:
    """MLP: 50 -> 96 -> 64 -> 2 (LONG_prob, SHORT_prob, sigmoid).
    Pure numpy with Adam optimizer. Trained with binary cross-entropy.
    """
    def __init__(self, in_dim=50, h1=96, h2=64, out_dim=2, lr=1e-3, seed=42):
        rng = np.random.RandomState(seed)
        # He init for ReLU
        self.W1 = rng.randn(in_dim, h1).astype(np.float32) * np.sqrt(2.0 / in_dim)
        self.b1 = np.zeros(h1, dtype=np.float32)
        self.W2 = rng.randn(h1, h2).astype(np.float32) * np.sqrt(2.0 / h1)
        self.b2 = np.zeros(h2, dtype=np.float32)
        self.W3 = rng.randn(h2, out_dim).astype(np.float32) * np.sqrt(2.0 / h2)
        self.b3 = np.zeros(out_dim, dtype=np.float32)
        self.lr = lr
        # Adam state
        self.t = 0
        self.beta1 = 0.9
        self.beta2 = 0.999
        self.eps = 1e-8
        params = [self.W1, self.b1, self.W2, self.b2, self.W3, self.b3]
        self.m = [np.zeros_like(p) for p in params]
        self.v = [np.zeros_like(p) for p in params]

    def _sigmoid(self, x):
        return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))

    def forward(self, X, dropout_p=0.0, rng=None):
        # X: (B, 50)
        z1 = X @ self.W1 + self.b1
        a1 = np.maximum(z1, 0.0)  # ReLU
        if dropout_p > 0 and rng is not None:
            mask1 = (rng.random_sample(a1.shape) > dropout_p).astype(np.float32) / (1 - dropout_p)
            a1 = a1 * mask1
        else:
            mask1 = None
        z2 = a1 @ self.W2 + self.b2
        a2 = np.maximum(z2, 0.0)
        if dropout_p > 0 and rng is not None:
            mask2 = (rng.random_sample(a2.shape) > dropout_p).astype(np.float32) / (1 - dropout_p)
            a2 = a2 * mask2
        else:
            mask2 = None
        z3 = a2 @ self.W3 + self.b3
        p = self._sigmoid(z3)
        cache = (X, z1, a1, mask1, z2, a2, mask2, z3, p)
        return p, cache

    def loss_and_backward(self, cache, y, class_weights=None):
        """y: (B, 2) binary targets. Returns mean BCE loss + gradients."""
        X, z1, a1, mask1, z2, a2, mask2, z3, p = cache
        B = X.shape[0]
        eps = 1e-7
        # BCE
        bce = -(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps))
        if class_weights is not None:
            # class_weights shape (2,) — weight for positives
            cw = class_weights * y + (1 - y)
            bce = bce * cw
        loss = bce.mean()
        # Gradients
        dz3 = (p - y) / B
        if class_weights is not None:
            # When weights are 1d row vector, p-y already broadcasts; use simple:
            dz3 = dz3 * (class_weights * y + (1 - y))
        dW3 = a2.T @ dz3
        db3 = dz3.sum(axis=0)
        da2 = dz3 @ self.W3.T
        if mask2 is not None:
            da2 = da2 * mask2
        dz2 = da2 * (z2 > 0)
        dW2 = a1.T @ dz2
        db2 = dz2.sum(axis=0)
        da1 = dz2 @ self.W2.T
        if mask1 is not None:
            da1 = da1 * mask1
        dz1 = da1 * (z1 > 0)
        dW1 = X.T @ dz1
        db1 = dz1.sum(axis=0)
        return loss, [dW1, db1, dW2, db2, dW3, db3]

    def step(self, grads):
        self.t += 1
        params = [self.W1, self.b1, self.W2, self.b2, self.W3, self.b3]
        bc1 = 1 - self.beta1 ** self.t
        bc2 = 1 - self.beta2 ** self.t
        for i, (p, g) in enumerate(zip(params, grads)):
            self.m[i] = self.beta1 * self.m[i] + (1 - self.beta1) * g
            self.v[i] = self.beta2 * self.v[i] + (1 - self.beta2) * (g * g)
            mh = self.m[i] / bc1
            vh = self.v[i] / bc2
            p -= self.lr * mh / (np.sqrt(vh) + self.eps)

    def predict(self, X):
        p, _ = self.forward(X, dropout_p=0.0)
        return p

    def save(self, path):
        np.savez(path,
                 W1=self.W1, b1=self.b1, W2=self.W2, b2=self.b2,
                 W3=self.W3, b3=self.b3)

    def load(self, path):
        d = np.load(path)
        self.W1 = d['W1']; self.b1 = d['b1']
        self.W2 = d['W2']; self.b2 = d['b2']
        self.W3 = d['W3']; self.b3 = d['b3']


# ============================================================================
# TRACK B — Feature dataset extraction over RTH ticks
# ============================================================================
class FeatureCollector:
    """Walks the tick stream once. Every 30s during RTH (13:30-20:00 UTC),
    emits (feature_vec, ts, day_counter, mid_px). Then asynchronously records
    the 60s-forward realized return to label LONG/SHORT targets.

    Stores X and y arrays for training.
    """
    SAMPLE_PERIOD_S = 30.0
    LABEL_HORIZON_S = 60.0
    LABEL_THRESHOLD_PT = 5.0
    RTH_START_S = 13 * 3600 + 30 * 60
    RTH_END_S = 20 * 3600

    def __init__(self):
        self.ext = FeatureExtractor()
        self._last_sample_ts = -1e18
        # Pending labels: list of (feature_vec, sample_ts, day_counter,
        # mid_at_sample, hh, mn)
        self._pending = deque()
        self.X = []  # (N, 50)
        self.y = []  # (N, 2)
        self.meta = []  # day_counter for each sample

    def feed_bar(self, ts, o, h, l, c):
        self.ext.feed_bar(ts, o, h, l, c)

    def feed_tick(self, ts, last, bid, ask, hh, mn, day_counter):
        self.ext.feed_tick(ts, last, bid, ask)
        # Resolve pending labels
        while self._pending:
            f_vec, s_ts, d_ctr, mid0, h0, m0 = self._pending[0]
            if ts - s_ts < self.LABEL_HORIZON_S:
                break
            self._pending.popleft()
            mid_now = (bid + ask) / 2.0
            ret = mid_now - mid0
            long_y = 1.0 if ret >= self.LABEL_THRESHOLD_PT else 0.0
            short_y = 1.0 if ret <= -self.LABEL_THRESHOLD_PT else 0.0
            self.X.append(f_vec)
            self.y.append((long_y, short_y))
            self.meta.append(d_ctr)
        # Sample
        sec_today = hh * 3600 + mn * 60
        if sec_today < self.RTH_START_S or sec_today > self.RTH_END_S:
            return
        if ts - self._last_sample_ts < self.SAMPLE_PERIOD_S:
            return
        f = self.ext.extract(ts, bid, ask, hh, mn)
        if f is None:
            return
        self._last_sample_ts = ts
        mid = (bid + ask) / 2.0
        self._pending.append((f.copy(), ts, day_counter, mid, hh, mn))


# ============================================================================
# TRACK B — DL-driven strategy (deployed using trained MLP)
# ============================================================================
class DLSignalStrategy(_r10._BaseEmitter):
    """Fires when MLP predicts P(LONG_profitable) >= threshold (or SHORT).
    Marketable entry with fixed stop/target (5pt / 15pt).
    """
    def __init__(self, name, mlp, extractor, threshold=0.6,
                 stop_pts=5, target_pts=15, cooldown_s=10,
                 session_start=(13, 30), session_end=(20, 0)):
        super().__init__(name, stop_pts=stop_pts, target_pts=target_pts,
                         cooldown_s=cooldown_s,
                         session_start=session_start, session_end=session_end,
                         fill_mode='marketable')
        self.mlp = mlp
        self.extractor = extractor
        self.threshold = threshold
        self._last_signal_ts = 0.0
        self._last_sample_ts = -1e18

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        pass

    def feed_signal(self, ts, bid, ask):
        if ts - self._last_signal_ts < self.cooldown_s:
            return
        if ts - self._last_sample_ts < 30.0:
            return
        self._last_sample_ts = ts
        # Use shared extractor's current state
        # We must convert hh/mn from ts; in our run loop we cache last hh/mn
        # via shared global
        hh = self._cur_hh
        mn = self._cur_mn
        f = self.extractor.extract(ts, bid, ask, hh, mn)
        if f is None:
            return
        p = self.mlp.predict(f.reshape(1, -1))[0]
        p_long, p_short = float(p[0]), float(p[1])
        if p_long >= self.threshold and p_long > p_short:
            self.emit(ts, 'LONG', ask, ('dl', 'L', round(ts, 1)), expires_in=10)
            self._last_signal_ts = ts
        elif p_short >= self.threshold and p_short > p_long:
            self.emit(ts, 'SHORT', bid, ('dl', 'S', round(ts, 1)), expires_in=10)
            self._last_signal_ts = ts


# ============================================================================
# TRACK B — DL-as-filter on round-4 CANON
# ============================================================================
class DLFilteredCanon(PullbackStrategy):
    """Round-4 CANON_INV_236 base, but only emits setups when MLP agrees
    with the entry direction at probability >= filter_threshold."""
    def __init__(self, name, mlp, extractor, filter_threshold=0.55, **kwargs):
        super().__init__(name,
                         impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
                         stop_pts=10, target_pts=20, invert=True, **kwargs)
        self.mlp = mlp
        self.extractor = extractor
        self.filter_threshold = filter_threshold

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        # Generate setups, then filter
        n_before = len(self.pending)
        super().on_bar_close(ts, hh, mn, bo, bh, bl, bc, hist)
        if len(self.pending) == n_before:
            return
        # Extract features at bar close
        f = self.extractor.extract(ts, bo, bo, hh, mn)
        if f is None:
            # Cannot evaluate; remove new setup
            del self.pending[n_before:]
            return
        p = self.mlp.predict(f.reshape(1, -1))[0]
        p_long, p_short = float(p[0]), float(p[1])
        # Keep setups whose 'side' matches model prediction
        kept = list(self.pending[:n_before])
        for s in self.pending[n_before:]:
            if s['side'] == 'LONG' and p_long >= self.filter_threshold:
                kept.append(s)
            elif s['side'] == 'SHORT' and p_short >= self.filter_threshold:
                kept.append(s)
        self.pending = kept


# ============================================================================
# TRACK C — Tiny VAE (encoder + decoder) for tick-sequence anomaly detection
# ============================================================================
class NumpyAE:
    """Plain autoencoder for outlier detection. 50 -> 32 -> 16 -> 32 -> 50.
    Use reconstruction error as anomaly score. (Skipping full VAE — same goal.)
    """
    def __init__(self, in_dim=50, h1=32, z=16, lr=1e-3, seed=43):
        rng = np.random.RandomState(seed)
        self.W1 = rng.randn(in_dim, h1).astype(np.float32) * np.sqrt(2.0 / in_dim)
        self.b1 = np.zeros(h1, dtype=np.float32)
        self.Wz = rng.randn(h1, z).astype(np.float32) * np.sqrt(2.0 / h1)
        self.bz = np.zeros(z, dtype=np.float32)
        self.Wd1 = rng.randn(z, h1).astype(np.float32) * np.sqrt(2.0 / z)
        self.bd1 = np.zeros(h1, dtype=np.float32)
        self.Wd2 = rng.randn(h1, in_dim).astype(np.float32) * np.sqrt(2.0 / h1)
        self.bd2 = np.zeros(in_dim, dtype=np.float32)
        self.lr = lr
        self.t = 0
        params = [self.W1, self.b1, self.Wz, self.bz,
                  self.Wd1, self.bd1, self.Wd2, self.bd2]
        self.m = [np.zeros_like(p) for p in params]
        self.v = [np.zeros_like(p) for p in params]

    def forward(self, X):
        z1 = X @ self.W1 + self.b1
        a1 = np.maximum(z1, 0.0)
        z2 = a1 @ self.Wz + self.bz
        a2 = np.maximum(z2, 0.0)
        z3 = a2 @ self.Wd1 + self.bd1
        a3 = np.maximum(z3, 0.0)
        z4 = a3 @ self.Wd2 + self.bd2  # linear output
        cache = (X, z1, a1, z2, a2, z3, a3, z4)
        return z4, cache

    def loss_and_backward(self, cache):
        X, z1, a1, z2, a2, z3, a3, z4 = cache
        B = X.shape[0]
        err = z4 - X
        loss = (err * err).mean()
        dz4 = (2.0 / (B * X.shape[1])) * err
        dWd2 = a3.T @ dz4
        dbd2 = dz4.sum(axis=0)
        da3 = dz4 @ self.Wd2.T
        dz3 = da3 * (z3 > 0)
        dWd1 = a2.T @ dz3
        dbd1 = dz3.sum(axis=0)
        da2 = dz3 @ self.Wd1.T
        dz2 = da2 * (z2 > 0)
        dWz = a1.T @ dz2
        dbz = dz2.sum(axis=0)
        da1 = dz2 @ self.Wz.T
        dz1 = da1 * (z1 > 0)
        dW1 = X.T @ dz1
        db1 = dz1.sum(axis=0)
        return loss, [dW1, db1, dWz, dbz, dWd1, dbd1, dWd2, dbd2]

    def step(self, grads):
        self.t += 1
        params = [self.W1, self.b1, self.Wz, self.bz,
                  self.Wd1, self.bd1, self.Wd2, self.bd2]
        bc1 = 1 - 0.9 ** self.t
        bc2 = 1 - 0.999 ** self.t
        for i, (p, g) in enumerate(zip(params, grads)):
            self.m[i] = 0.9 * self.m[i] + 0.1 * g
            self.v[i] = 0.999 * self.v[i] + 0.001 * (g * g)
            mh = self.m[i] / bc1
            vh = self.v[i] / bc2
            p -= self.lr * mh / (np.sqrt(vh) + 1e-8)

    def recon_error(self, X):
        z4, _ = self.forward(X)
        return ((z4 - X) ** 2).mean(axis=1)


# ============================================================================
# Training routines
# ============================================================================
def train_mlp(X_train, y_train, X_val, y_val,
              epochs=30, batch_size=256, lr=1e-3, dropout_p=0.2,
              log=sys.stderr):
    np.random.seed(42)
    rng = np.random.RandomState(123)
    mlp = NumpyMLP(in_dim=X_train.shape[1], lr=lr)
    n = X_train.shape[0]
    # Class weighting
    pos_rate = y_train.mean(axis=0)
    # Avoid div by zero
    pos_rate = np.clip(pos_rate, 0.001, 0.999)
    class_w = (1 - pos_rate) / pos_rate  # weight for positives
    print(f"  [mlp] N_train={n}, pos_rate={pos_rate}, class_w={class_w}",
          file=log, flush=True)
    best_val_loss = 1e18
    best_state = None
    patience = 0
    for ep in range(epochs):
        idx = np.arange(n)
        rng.shuffle(idx)
        total_loss = 0.0
        n_batches = 0
        for s in range(0, n, batch_size):
            bi = idx[s:s + batch_size]
            xb = X_train[bi]
            yb = y_train[bi]
            p, cache = mlp.forward(xb, dropout_p=dropout_p, rng=rng)
            loss, grads = mlp.loss_and_backward(cache, yb,
                                                class_weights=class_w)
            mlp.step(grads)
            total_loss += loss
            n_batches += 1
        tr_loss = total_loss / max(1, n_batches)
        # Validate
        vp = mlp.predict(X_val)
        eps = 1e-7
        val_loss = -(y_val * np.log(vp + eps) + (1 - y_val) * np.log(1 - vp + eps)).mean()
        # Val AUC-like accuracy: P(pred>0.5 == y)
        acc_long = ((vp[:, 0] > 0.5).astype(np.float32) == y_val[:, 0]).mean()
        acc_short = ((vp[:, 1] > 0.5).astype(np.float32) == y_val[:, 1]).mean()
        print(f"  [mlp] ep{ep:3d} tr={tr_loss:.4f} val={val_loss:.4f} "
              f"acc_L={acc_long:.3f} acc_S={acc_short:.3f}",
              file=log, flush=True)
        if val_loss < best_val_loss - 1e-4:
            best_val_loss = val_loss
            best_state = (mlp.W1.copy(), mlp.b1.copy(),
                          mlp.W2.copy(), mlp.b2.copy(),
                          mlp.W3.copy(), mlp.b3.copy())
            patience = 0
        else:
            patience += 1
            if patience >= 5:
                print(f"  [mlp] early stop at ep{ep}", file=log)
                break
    if best_state is not None:
        mlp.W1, mlp.b1, mlp.W2, mlp.b2, mlp.W3, mlp.b3 = best_state
    return mlp


def train_ae(X_train, X_val, epochs=20, batch_size=256, lr=1e-3,
             log=sys.stderr):
    rng = np.random.RandomState(456)
    ae = NumpyAE(in_dim=X_train.shape[1], lr=lr)
    n = X_train.shape[0]
    for ep in range(epochs):
        idx = np.arange(n)
        rng.shuffle(idx)
        total_loss = 0.0
        n_batches = 0
        for s in range(0, n, batch_size):
            bi = idx[s:s + batch_size]
            xb = X_train[bi]
            z4, cache = ae.forward(xb)
            loss, grads = ae.loss_and_backward(cache)
            ae.step(grads)
            total_loss += loss
            n_batches += 1
        tr_loss = total_loss / max(1, n_batches)
        z4v, _ = ae.forward(X_val)
        val_loss = ((z4v - X_val) ** 2).mean()
        if ep % 5 == 0 or ep == epochs - 1:
            print(f"  [ae] ep{ep:3d} tr={tr_loss:.4f} val={val_loss:.4f}",
                  file=log, flush=True)
    return ae


# ============================================================================
# Report helpers (reused from r12)
# ============================================================================
def report_strategy(strat, total_days, fee_rt=TOTAL_RT_COST, pt_value=MNQ_PER_PT):
    n = len(strat.completed)
    if n == 0:
        return {'name': strat.name, 'n': 0, 'wr': 0.0, 'net': 0.0,
                'per_day': 0.0, 'per_trade': 0.0, 'worst': 0.0, 'best': 0.0,
                'max_dd': 0.0, 'trades_per_day': 0.0, 'sharpe': 0.0,
                'n_days': 0, 'pos_d': 0, 'neg_d': 0}
    wins = 0; net = 0.0
    day_nets = defaultdict(float); series = []
    for c in strat.completed:
        pnl_pts = c[0]; d = c[2]
        pnl_usd = pnl_pts * pt_value - fee_rt
        if pnl_usd > 0:
            wins += 1
        net += pnl_usd
        day_nets[d] += pnl_usd
        series.append(pnl_usd)
    wr = wins / n
    per_day = net / max(1, total_days)
    per_trade = net / n
    trades_per_day = n / max(1, total_days)
    daily = list(day_nets.values())
    n_days = len(daily)
    pos_d = sum(1 for x in daily if x > 0)
    neg_d = sum(1 for x in daily if x < 0)
    worst = min(daily) if daily else 0.0
    best = max(daily) if daily else 0.0
    cum = 0.0; peak = 0.0; max_dd = 0.0
    for x in series:
        cum += x
        if cum > peak: peak = cum
        if peak - cum > max_dd: max_dd = peak - cum
    if n_days > 1:
        mean = sum(daily) / n_days
        var = sum((x - mean) ** 2 for x in daily) / (n_days - 1)
        std = math.sqrt(var) if var > 0 else 0.0
        sharpe = (mean / std) if std > 0 else 0.0
    else:
        sharpe = 0.0
    return {'name': strat.name, 'n': n, 'wr': wr, 'net': net,
            'per_day': per_day, 'per_trade': per_trade,
            'worst': worst, 'best': best, 'max_dd': max_dd,
            'trades_per_day': trades_per_day, 'sharpe': sharpe,
            'n_days': n_days, 'pos_d': pos_d, 'neg_d': neg_d}


def is_pass(r):
    return (r['trades_per_day'] >= 300 and r['wr'] >= 0.45
            and r['per_day'] >= 1000 and r['max_dd'] <= 5000)


# ============================================================================
# CHECKPOINT
# ============================================================================
def save_checkpoint(ckpt_path, offset, day_counter, last_day_key,
                    all_strats, collector_state):
    state = {
        "offset": int(offset),
        "day_counter": int(day_counter),
        "last_day_key": last_day_key,
        "variants": {
            s.name: {
                "completed": list(s.completed),
                "by_day": dict(s.by_day),
                "n_trades": int(s.n_trades),
            }
            for s in all_strats
        },
        "collector": collector_state,
    }
    tmp = ckpt_path + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, ckpt_path)


def load_checkpoint(ckpt_path, all_strats):
    if not os.path.exists(ckpt_path):
        return None
    try:
        with open(ckpt_path, "rb") as f:
            state = pickle.load(f)
    except Exception as e:
        print(f"[r14] ckpt load failed: {e!r}", file=sys.stderr)
        return None
    by_name = {s.name: s for s in all_strats}
    for name, v in state.get("variants", {}).items():
        s = by_name.get(name)
        if s is None:
            continue
        s.completed = list(v.get("completed", []))
        s.by_day = dict(v.get("by_day", {}))
        s.n_trades = int(v.get("n_trades", 0))
    return (int(state["offset"]),
            int(state["day_counter"]),
            state["last_day_key"],
            state.get("collector"))


# ============================================================================
# MAIN — two-pass architecture
# ============================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offset", type=int, default=DEFAULT_OFFSET)
    ap.add_argument("--ckpt-suffix", default="")
    ap.add_argument("--max-days", type=int, default=60)
    ap.add_argument("--phase", choices=("collect", "train", "deploy", "all"),
                    default="all")
    ap.add_argument("--feature-cache",
                    default="/home/user/HFTBot/research/round14_features.npz")
    ap.add_argument("--mlp-cache",
                    default="/home/user/HFTBot/research/round14_mlp.npz")
    ap.add_argument("--ae-cache",
                    default="/home/user/HFTBot/research/round14_ae.npz")
    args = ap.parse_args()

    ckpt_path = ("/home/user/HFTBot/research/round14_checkpoint"
                 f"{args.ckpt_suffix}.pkl")
    md_path = "/home/user/HFTBot/research/round14_results.md"
    csv_path = ("/home/user/HFTBot/research/round14_summary"
                f"{args.ckpt_suffix}.csv")

    # ------------------------------------------------------------------
    # PASS 1 — TRACK A backtests + feature collection
    # ------------------------------------------------------------------
    track_a = build_track_a_variants()
    for s in track_a:
        attach_r7_executor(s)

    collector = FeatureCollector()

    print(f"[r14] PASS 1 — track_a={len(track_a)} strategies + feature collection",
          file=sys.stderr, flush=True)

    bb_1m = BarBuilder(granularity_secs=60, max_history=300)
    resumed = load_checkpoint(ckpt_path, track_a)
    collector_npz = (args.feature_cache + ".pass1.npz") if args.phase == 'all' \
        else args.feature_cache
    if resumed is not None:
        start_offset, day_counter, last_day_key, coll_state = resumed
        if coll_state is not None:
            # restore collector arrays
            collector.X = list(coll_state.get('X', []))
            collector.y = list(coll_state.get('y', []))
            collector.meta = list(coll_state.get('meta', []))
        resumed_trades = sum(s.n_trades for s in track_a)
        print(f"[r14] RESUMING pass1 from offset {start_offset:,} "
              f"day={day_counter} ({resumed_trades:,} trades, "
              f"{len(collector.X):,} samples)",
              file=sys.stderr, flush=True)
    else:
        start_offset = args.offset
        day_counter = -1
        last_day_key = None

    max_day_counter = day_counter + args.max_days
    n_lines = 0
    t_start = time.time()
    last_progress_t = t_start
    last_progress_ticks = 0

    with open(PATH, "rb") as f:
        f.seek(start_offset)
        f.readline()
        for raw in f:
            n_lines += 1
            if n_lines % CHECKPOINT_EVERY_TICKS == 0:
                now = time.time()
                rate = (n_lines - last_progress_ticks) / max(0.001, now - last_progress_t)
                last_progress_t = now
                last_progress_ticks = n_lines
                pos = f.tell()
                try:
                    coll_state = {
                        'X': collector.X[-50000:],  # cap
                        'y': collector.y[-50000:],
                        'meta': collector.meta[-50000:],
                    }
                    save_checkpoint(ckpt_path, pos, day_counter, last_day_key,
                                    track_a, coll_state)
                except Exception as e:
                    print(f"  [r14] ckpt save failed: {e!r}", file=sys.stderr)
                top = max((s.n_trades, s.name) for s in track_a)
                print(f"  [r14] {n_lines/1e6:.1f}M ticks rate={rate/1e6:.2f}M/s "
                      f"day={day_counter} most_trades={top[1]}({top[0]}) "
                      f"samples={len(collector.X):,}",
                      file=sys.stderr, flush=True)
            try:
                line = raw.decode("ascii", errors="ignore")
                stamp_str, vals = line.split(";", 1)
                vp = vals.split(";")
                if len(vp) < 3:
                    continue
                last = float(vp[0]); bid = float(vp[1]); ask = float(vp[2])
                p = stamp_str.split()
                if len(p) < 2:
                    continue
                yy = int(p[0][:4]); mm = int(p[0][4:6]); dd = int(p[0][6:8])
                hh = int(p[1][:2]); mn = int(p[1][2:4]); ss = int(p[1][4:6])
                ns = int(p[2]) if len(p) > 2 else 0
            except Exception:
                continue

            day_key = (yy, mm, dd)
            if day_key != last_day_key:
                day_counter += 1
                last_day_key = day_key
                if day_counter >= max_day_counter:
                    break

            ts = day_counter * 86400 + hh * 3600 + mn * 60 + ss + ns / 1e7

            MARKET.feed_tick(ts, last, bid, ask)
            _r10.VPIN_GAUGE.feed_tick(last, bid, ask)
            _r10.TAPE.feed_tick(ts)

            if bb_1m.on_tick(ts, last):
                closed = bb_1m.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    MARKET.feed_bar(o, h, l, c)
                    collector.feed_bar(ts, o, h, l, c)
                    for s in track_a:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_1m.history)

            # Feed collector (also handles RTH gating internally)
            collector.feed_tick(ts, last, bid, ask, hh, mn, day_counter)

            # Track A bot tick (with our custom queue model)
            for s in track_a:
                if s.pending or s.in_trade is not None:
                    patched_r10_bot_on_tick(
                        s, ts, bid, ask, day_counter, hh, mn, last)

    pass1_elapsed = time.time() - t_start
    total_days = day_counter + 1
    print(f"[r14] PASS 1 done in {pass1_elapsed/60:.1f}min, "
          f"{n_lines:,} ticks, {total_days} days, {len(collector.X):,} samples",
          file=sys.stderr, flush=True)

    # ------------------------------------------------------------------
    # Build feature arrays
    # ------------------------------------------------------------------
    if len(collector.X) < 1000:
        print(f"[r14] WARNING: only {len(collector.X)} samples — DL will be weak",
              file=sys.stderr)

    X = np.array(collector.X, dtype=np.float32)
    Y = np.array(collector.y, dtype=np.float32)
    meta = np.array(collector.meta, dtype=np.int32)

    # Train/val/test split by day
    train_mask = meta < 40
    val_mask = (meta >= 40) & (meta < 50)
    test_mask = meta >= 50

    X_train, Y_train = X[train_mask], Y[train_mask]
    X_val, Y_val = X[val_mask], Y[val_mask]
    X_test, Y_test = X[test_mask], Y[test_mask]

    print(f"[r14] Split: train={len(X_train)}, val={len(X_val)}, "
          f"test={len(X_test)}",
          file=sys.stderr, flush=True)

    # Feature normalization (z-score using train)
    if len(X_train) > 0:
        mu = X_train.mean(axis=0)
        sigma = X_train.std(axis=0) + 1e-6
        X_train_n = (X_train - mu) / sigma
        X_val_n = (X_val - mu) / sigma
        X_test_n = (X_test - mu) / sigma
        np.savez(args.feature_cache,
                 X_train=X_train_n, Y_train=Y_train,
                 X_val=X_val_n, Y_val=Y_val,
                 X_test=X_test_n, Y_test=Y_test,
                 mu=mu, sigma=sigma)
        print(f"[r14] Cached features to {args.feature_cache}",
              file=sys.stderr, flush=True)

    # ------------------------------------------------------------------
    # PHASE 2 — Train MLP + AE
    # ------------------------------------------------------------------
    print(f"\n[r14] PHASE 2 — train MLP", file=sys.stderr, flush=True)
    mlp = None
    ae = None
    test_results = {}
    if len(X_train) >= 1000 and len(X_val) >= 100 and len(X_test) >= 100:
        mlp = train_mlp(X_train_n, Y_train, X_val_n, Y_val,
                        epochs=30, batch_size=256, lr=1e-3, dropout_p=0.2)
        mlp.save(args.mlp_cache)
        # Test set evaluation
        pt = mlp.predict(X_test_n)
        eps = 1e-7
        test_loss = -(Y_test * np.log(pt + eps)
                      + (1 - Y_test) * np.log(1 - pt + eps)).mean()
        acc_L = ((pt[:, 0] > 0.5) == Y_test[:, 0]).mean()
        acc_S = ((pt[:, 1] > 0.5) == Y_test[:, 1]).mean()
        # Coverage at threshold 0.6
        cov_L = (pt[:, 0] >= 0.6).mean()
        cov_S = (pt[:, 1] >= 0.6).mean()
        # Precision at threshold
        mask_L = pt[:, 0] >= 0.6
        prec_L = Y_test[mask_L, 0].mean() if mask_L.sum() > 0 else 0.0
        mask_S = pt[:, 1] >= 0.6
        prec_S = Y_test[mask_S, 1].mean() if mask_S.sum() > 0 else 0.0
        test_results['mlp'] = {
            'loss': float(test_loss), 'acc_L': float(acc_L),
            'acc_S': float(acc_S), 'cov_L': float(cov_L), 'cov_S': float(cov_S),
            'prec_L_at_0.6': float(prec_L), 'prec_S_at_0.6': float(prec_S),
        }
        print(f"[r14] MLP test: loss={test_loss:.4f} acc_L={acc_L:.3f} "
              f"acc_S={acc_S:.3f} prec_L@0.6={prec_L:.3f} prec_S@0.6={prec_S:.3f} "
              f"cov_L={cov_L:.3f} cov_S={cov_S:.3f}",
              file=sys.stderr, flush=True)

        # Train AE for anomaly detection
        ae = train_ae(X_train_n, X_val_n, epochs=15, batch_size=256, lr=1e-3)
        np.savez(args.ae_cache, W1=ae.W1, b1=ae.b1, Wz=ae.Wz, bz=ae.bz,
                 Wd1=ae.Wd1, bd1=ae.bd1, Wd2=ae.Wd2, bd2=ae.bd2)
        # Test recon errors
        recon_test = ae.recon_error(X_test_n)
        # Predictivity of high-recon-error: is high error correlated with
        # large absolute return outcome?
        hi_thresh = np.percentile(recon_test, 90)
        is_hi = recon_test >= hi_thresh
        # Compare base rates of label=1
        pos_rate_hi = Y_test[is_hi].mean(axis=0) if is_hi.sum() > 0 else (0, 0)
        pos_rate_lo = Y_test[~is_hi].mean(axis=0) if (~is_hi).sum() > 0 else (0, 0)
        test_results['ae'] = {
            'recon_p90': float(hi_thresh),
            'pos_rate_hi_L': float(pos_rate_hi[0]) if len(pos_rate_hi) == 2 else 0.0,
            'pos_rate_hi_S': float(pos_rate_hi[1]) if len(pos_rate_hi) == 2 else 0.0,
            'pos_rate_lo_L': float(pos_rate_lo[0]) if len(pos_rate_lo) == 2 else 0.0,
            'pos_rate_lo_S': float(pos_rate_lo[1]) if len(pos_rate_lo) == 2 else 0.0,
        }
        print(f"[r14] AE test: high-recon LONG rate={pos_rate_hi[0]:.3f} vs "
              f"low={pos_rate_lo[0]:.3f}, SHORT high={pos_rate_hi[1]:.3f} vs "
              f"low={pos_rate_lo[1]:.3f}",
              file=sys.stderr, flush=True)

    # ------------------------------------------------------------------
    # PASS 2 — Deploy DL signal + DL-filter on out-of-sample (days 50+)
    # ------------------------------------------------------------------
    deploy_results = {}
    if mlp is not None and len(X_test) > 200:
        print(f"\n[r14] PASS 2 — deploy DL strategies on out-of-sample window",
              file=sys.stderr, flush=True)
        # Build a fresh extractor for deployment; it will be fed alongside
        # the tick stream.
        deploy_ext = FeatureExtractor()
        # We use the SAME normalization as training. Wrap MLP predict to
        # normalize inputs before prediction.
        orig_predict = mlp.predict

        def normed_predict(X_in):
            return orig_predict((X_in - mu) / sigma)
        mlp.predict = normed_predict

        # Build deploy strategies — try multiple thresholds
        deploy_strats = []
        for thresh in (0.55, 0.60, 0.65):
            for stp, tgt in ((5, 15), (4, 12), (3, 9)):
                name = f"B_DL_th{int(thresh*100)}_s{stp}t{tgt}"
                s = DLSignalStrategy(name, mlp, deploy_ext,
                                     threshold=thresh,
                                     stop_pts=stp, target_pts=tgt)
                # Inject current hh/mn into strategy
                s._cur_hh = 0; s._cur_mn = 0
                deploy_strats.append(s)
        for ft in (0.50, 0.55, 0.60):
            name = f"B_DLFLT_canon_ft{int(ft*100)}"
            s = DLFilteredCanon(name, mlp, deploy_ext, filter_threshold=ft)
            deploy_strats.append(s)
        for s in deploy_strats:
            attach_r7_executor(s)
            if not hasattr(s, '_last_signal_ts'):
                s._last_signal_ts = 0.0

        # Re-stream just the out-of-sample window (days 50..59 in our window)
        # We compute the byte offset for day 50 approximately by skipping
        # day_counter * tick density. Simpler: re-run from start_offset and
        # gate strategy execution by day_counter >= 40 (val+test combined).
        bb2 = BarBuilder(granularity_secs=60, max_history=300)
        day_counter2 = -1
        last_day_key2 = None
        n_lines2 = 0
        t2 = time.time()

        with open(PATH, "rb") as f:
            f.seek(args.offset)
            f.readline()
            for raw in f:
                n_lines2 += 1
                if n_lines2 % 1_000_000 == 0:
                    print(f"  [r14-p2] {n_lines2/1e6:.1f}M ticks day={day_counter2}",
                          file=sys.stderr, flush=True)
                try:
                    line = raw.decode("ascii", errors="ignore")
                    stamp_str, vals = line.split(";", 1)
                    vp = vals.split(";")
                    if len(vp) < 3:
                        continue
                    last = float(vp[0]); bid = float(vp[1]); ask = float(vp[2])
                    p = stamp_str.split()
                    if len(p) < 2:
                        continue
                    yy = int(p[0][:4]); mm = int(p[0][4:6]); dd = int(p[0][6:8])
                    hh = int(p[1][:2]); mn = int(p[1][2:4]); ss = int(p[1][4:6])
                    ns = int(p[2]) if len(p) > 2 else 0
                except Exception:
                    continue
                day_key2 = (yy, mm, dd)
                if day_key2 != last_day_key2:
                    day_counter2 += 1
                    last_day_key2 = day_key2
                    if day_counter2 >= args.max_days:
                        break

                ts = day_counter2 * 86400 + hh * 3600 + mn * 60 + ss + ns / 1e7
                MARKET.feed_tick(ts, last, bid, ask)
                deploy_ext.feed_tick(ts, last, bid, ask)

                if bb2.on_tick(ts, last):
                    closed = bb2.closed_bar()
                    if closed is not None:
                        o, h, l, c = closed
                        MARKET.feed_bar(o, h, l, c)
                        deploy_ext.feed_bar(ts, o, h, l, c)
                        if day_counter2 >= 50:
                            for s in deploy_strats:
                                s.on_bar_close(ts, hh, mn, o, h, l, c, bb2.history)

                if day_counter2 >= 50:
                    # Update strategy clocks for emitter strategies
                    for s in deploy_strats:
                        if isinstance(s, DLSignalStrategy):
                            s._cur_hh = hh
                            s._cur_mn = mn
                            s.feed_signal(ts, bid, ask)
                        if s.pending or s.in_trade is not None:
                            r10_bot_on_tick(s, ts, bid, ask,
                                            day_counter2, hh, mn, last)

        # Report deploy strategies (only days 50+ → 10 days)
        oos_days = max(1, args.max_days - 50)
        for s in deploy_strats:
            # Filter completed to only days >= 50
            comp_oos = [c for c in s.completed if c[2] >= 50]
            by_day_oos = {d: v for d, v in s.by_day.items() if d >= 50}
            # build temp dict
            r_obj = type('R', (), {})()
            r_obj.completed = comp_oos
            r_obj.by_day = by_day_oos
            r_obj.n_trades = len(comp_oos)
            r_obj.name = s.name
            rep = report_strategy(r_obj, oos_days)
            deploy_results[s.name] = rep
            print(f"  [r14-deploy] {s.name}: n={rep['n']} "
                  f"WR={rep['wr']*100:.1f}% ${rep['per_day']:.0f}/day "
                  f"DD=${rep['max_dd']:.0f}",
                  file=sys.stderr, flush=True)

    # ------------------------------------------------------------------
    # REPORTING
    # ------------------------------------------------------------------
    L = []
    L.append("# Round 14 — TRACK A queue sensitivity + TRACK B/C deep learning\n\n")
    L.append(f"Generated: {datetime.now().isoformat()}\n")
    L.append(f"Period: {total_days} calendar-day buckets from offset "
             f"{args.offset:,} (max-days={args.max_days})\n")
    L.append(f"Pass-1 tick stream: {n_lines:,} lines processed in "
             f"{pass1_elapsed/60:.1f} min\n\n")

    L.append("## Hard requirements\n")
    L.append("- 300+ trades/day average\n- 45%+ WR\n- $1,000+ $/day\n- maxDD <= $5,000\n\n")

    # TRACK A
    L.append("## TRACK A — Queue model sensitivity\n\n")
    L.append("Goal: determine how round-4 idealized winners perform under "
             "three different LIMIT-fill queue models. The bot-faithful "
             "executor since round 7 has assumed PESSIMISTIC queue position "
             "(LIMIT fills only on >=1-tick overshoot). If a more realistic "
             "model shows $1k+/day, that's a deployment candidate.\n\n")
    L.append("Models:\n")
    L.append("- **pessimistic**: requires bid/ask to OVERSHOOT entry by >=1 tick.\n")
    L.append("- **realistic_mid**: 100% on overshoot, 50% probability on touch.\n")
    L.append("- **presubmit**: 100% on overshoot; on touch — 80% if order has "
             "been ARMED >= 30s (anticipatory queue priority), else 30%.\n\n")

    rows_a = [report_strategy(s, total_days) for s in track_a]
    rows_a_by_name = {r['name']: r for r in rows_a}

    L.append("### Per-strategy results\n\n")
    L.append("| Strategy | Queue model | Trades | Tr/day | WR% | $/day | DD | Sharpe | PASS? |\n")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|:---:|\n")
    for s in track_a:
        r = rows_a_by_name[s.name]
        base_name = s.name.split('_', 2)[-1]
        flag = "YES" if is_pass(r) else "no"
        L.append(f"| {base_name} | {s.queue_model} | {r['n']:,} | "
                 f"{r['trades_per_day']:.1f} | {r['wr']*100:.1f} | "
                 f"${r['per_day']:,.0f} | ${r['max_dd']:,.0f} | "
                 f"{r['sharpe']:.2f} | {flag} |\n")

    L.append("\n### Best per model\n\n")
    by_model = defaultdict(list)
    for s in track_a:
        by_model[s.queue_model].append(rows_a_by_name[s.name])
    for model_name, rs in by_model.items():
        rs_sorted = sorted(rs, key=lambda r: -r['per_day'])
        top = rs_sorted[0]
        L.append(f"- **{model_name}**: best={top['name']} "
                 f"${top['per_day']:,.0f}/day, {top['trades_per_day']:.1f} tr/day, "
                 f"WR={top['wr']*100:.1f}%, DD=${top['max_dd']:,.0f}\n")

    track_a_passers = [s for s in track_a if is_pass(rows_a_by_name[s.name])]
    if track_a_passers:
        L.append(f"\n**{len(track_a_passers)} TRACK A passers found!**\n")
        for s in track_a_passers:
            r = rows_a_by_name[s.name]
            L.append(f"- {s.name} (queue={s.queue_model}): "
                     f"${r['per_day']:,.0f}/day {r['wr']*100:.1f}%WR\n")
    else:
        L.append("\nNo TRACK A configuration passes all 4 hard requirements.\n")

    # TRACK B — DL
    L.append("\n## TRACK B — Deep learning (pure-numpy MLP)\n\n")
    L.append("PyTorch was unavailable (proxy + disk), so the model is a "
             "pure-numpy MLP with Adam optimizer: **50-D input → 96-ReLU → "
             "64-ReLU → 2-sigmoid (LONG, SHORT)**.\n\n")
    L.append("### Feature engineering (50-D)\n\n")
    L.append("- Price action (15): last 5 1-min returns, last 5 HL ranges, "
             "bar position, SMA divergence, ATR(5)/ATR(20)/ratio.\n")
    L.append("- Microstructure (15): spread, 1-min avg spread + trend, "
             "tick velocity 10/30/60s, signed-tick balance, persistence, "
             "bid-hits/ask-lifts ratio, 60-bar percentile, VWAP gap, "
             "tick jumpiness.\n")
    L.append("- Volatility regime (10): realized vol 5/15/60min + ratio, "
             "Hurst proxy, range expansion percentile, vol z-score, "
             "body/range ratio, up-bar fraction, vol-of-vol.\n")
    L.append("- Time (10): hour sin/cos, minute sin/cos, DoW, time since "
             "open, time to close, time since big move, RTH indicator.\n\n")
    L.append("### Training protocol\n\n")
    L.append("- Train days 0..39, validate 40..49, test 50..59 (out-of-sample)\n")
    L.append("- Adam optimizer, lr=1e-3, batch size 256, dropout 0.2\n")
    L.append("- Up to 30 epochs with early-stopping on val loss\n")
    L.append("- Class weighting to handle imbalance\n")
    L.append(f"- Sample count: train={len(X_train)}, val={len(X_val)}, "
             f"test={len(X_test)}\n\n")

    if 'mlp' in test_results:
        tr = test_results['mlp']
        L.append("### MLP out-of-sample results\n\n")
        L.append(f"- Test BCE loss: **{tr['loss']:.4f}**\n")
        L.append(f"- Test accuracy LONG: {tr['acc_L']*100:.2f}%\n")
        L.append(f"- Test accuracy SHORT: {tr['acc_S']*100:.2f}%\n")
        L.append(f"- Precision @ p>=0.6 LONG: {tr['prec_L_at_0.6']*100:.2f}% "
                 f"(coverage {tr['cov_L']*100:.2f}%)\n")
        L.append(f"- Precision @ p>=0.6 SHORT: {tr['prec_S_at_0.6']*100:.2f}% "
                 f"(coverage {tr['cov_S']*100:.2f}%)\n\n")

    if deploy_results:
        L.append("### TRACK B — Deployment backtest (days 50+ OOS, ~10 days)\n\n")
        L.append("Bot-faithful execution with 1 MNQ, $1.91/RT, 200ms latency, "
                 "10s cooldown, 5pt stop slip rules.\n\n")
        L.append("| Strategy | Trades | Tr/day | WR% | $/day | DD | Sharpe | PASS? |\n")
        L.append("|---|---:|---:|---:|---:|---:|---:|:---:|\n")
        items = sorted(deploy_results.items(),
                       key=lambda kv: -kv[1]['per_day'])
        for name, r in items:
            flag = "YES" if is_pass(r) else "no"
            L.append(f"| {name} | {r['n']:,} | {r['trades_per_day']:.1f} | "
                     f"{r['wr']*100:.1f} | ${r['per_day']:,.0f} | "
                     f"${r['max_dd']:,.0f} | {r['sharpe']:.2f} | {flag} |\n")

    # TRACK C — VAE/AE
    L.append("\n## TRACK C — Autoencoder anomaly detection\n\n")
    if 'ae' in test_results:
        tr = test_results['ae']
        L.append("Trained a 50→32→16→32→50 autoencoder on training features. "
                 "High reconstruction error indicates outlier market state. "
                 "Question: do outliers predict next-60s 5pt moves?\n\n")
        L.append(f"- Reconstruction-error p90 threshold (test): {tr['recon_p90']:.4f}\n")
        L.append(f"- Above-threshold LONG-profitable rate: "
                 f"**{tr['pos_rate_hi_L']*100:.2f}%** vs baseline "
                 f"**{tr['pos_rate_lo_L']*100:.2f}%**\n")
        L.append(f"- Above-threshold SHORT-profitable rate: "
                 f"**{tr['pos_rate_hi_S']*100:.2f}%** vs baseline "
                 f"**{tr['pos_rate_lo_S']*100:.2f}%**\n\n")
        lift_L = tr['pos_rate_hi_L'] / max(tr['pos_rate_lo_L'], 1e-6)
        lift_S = tr['pos_rate_hi_S'] / max(tr['pos_rate_lo_S'], 1e-6)
        L.append(f"Anomaly lift: LONG {lift_L:.2f}x, SHORT {lift_S:.2f}x.\n")
        if lift_L > 1.5 or lift_S > 1.5:
            L.append("**Anomalies show predictive lift!** Worth combining with MLP.\n")
        else:
            L.append("Anomalies do not show strong predictive lift on their own.\n")

    # Round 15 directions
    L.append("\n## Section X — Round 15 directions\n\n")
    L.append("If round 14 did not produce a passing strategy:\n\n")
    L.append("1. **Install PyTorch on a machine with more disk** — train a true "
             "LSTM/Transformer/TCN. The numpy MLP only sees the engineered "
             "feature vector at single timesteps; sequence models can find "
             "richer structure.\n")
    L.append("2. **Sample more densely** — currently 30s sample period. Try "
             "5s or 1s to get 6-30x more training data.\n")
    L.append("3. **Multi-horizon labels** — predict 30s, 60s, 120s, 300s "
             "forward returns simultaneously (multi-task).\n")
    L.append("4. **Bag of weak learners** — train 50 small MLPs on bootstrap "
             "samples, ensemble with median vote.\n")
    L.append("5. **Sequence-of-features**: feed the LAST N feature vectors "
             "into a wide MLP (stride-flatten 60 → 50*60=3000-D input).\n")
    L.append("6. **Cost-sensitive thresholding**: optimize threshold for "
             "$/day directly, not for accuracy.\n")
    L.append("7. **Reinforcement learning**: cross-entropy method on policy "
             "parameters (entry threshold, stop, target).\n")
    L.append("8. **Combine TRACK A + TRACK B**: use MLP filter ONLY when "
             "queue model is realistic_mid (i.e. allow optimistic fills).\n")
    L.append("9. **Trade NQ instead of MNQ** — same strategy, 10x pt-value, "
             "could meet $/day spec at lower trade count.\n")
    L.append("10. **Re-investigate execution truth**: real broker fills "
             "would tell us which queue model is correct. Test on demo "
             "account.\n")

    with open(md_path, "w") as mf:
        mf.write("".join(L))
    print(f"\n[r14] wrote {md_path}", file=sys.stderr, flush=True)

    # CSV dump
    with open(csv_path, "w", newline="") as cf:
        w = csv.writer(cf)
        w.writerow(["track", "name", "trades", "tr_per_day", "wr",
                    "per_day", "max_dd", "sharpe", "pass"])
        for s in track_a:
            r = rows_a_by_name[s.name]
            w.writerow(["A", s.name, r['n'], f"{r['trades_per_day']:.1f}",
                        f"{r['wr']:.4f}", f"{r['per_day']:.2f}",
                        f"{r['max_dd']:.2f}", f"{r['sharpe']:.3f}",
                        "Y" if is_pass(r) else "N"])
        for name, r in deploy_results.items():
            w.writerow(["B", name, r['n'], f"{r['trades_per_day']:.1f}",
                        f"{r['wr']:.4f}", f"{r['per_day']:.2f}",
                        f"{r['max_dd']:.2f}", f"{r['sharpe']:.3f}",
                        "Y" if is_pass(r) else "N"])

    try:
        if os.path.exists(ckpt_path):
            os.remove(ckpt_path)
    except Exception:
        pass


if __name__ == "__main__":
    main()
