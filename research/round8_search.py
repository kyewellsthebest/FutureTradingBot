"""Round 8 strategy search for MNQ — bot-faithful, 250+ NEW variants.

Round 7 finished with ZERO passers but produced three structurally
distinct HINT signals:

  - T54_MTF_imp6_pp382_s5t20_INV (Multi-TF Pullback Invert):
      46 tr/d, 28.7% WR, $5/day, DD $479.  HIGH volume, low WR.
  - T44_VRP_v10-30_s5t15 (Vol Regime Pullback):
      5 tr/d, 44.3% WR, $4/day, DD $88.  Good WR, low volume.
  - T41_SRR_lk20_sw8_s5t20 (Stop-Run Reversal):
      1.4 tr/d, 35% WR, $7/day. Best $/trade ($4.83) but tiny volume.

The structural conclusion: pullback signals exist, but WR collapses
when execution friction (queue + latency + costs) eats $1.91/RT. The
remaining path is SELECTIVITY: gate high-volume signals with quality
filters to lift WR while keeping volume above 300/day.

Round 8 directions (ALL NEW vs rounds 1-7):

  A. Signal combinations / filters (50+ variants)
     - T54_MTF gated by VRP regime
     - T54_MTF gated by SRR proximity (S/R level confluence)
     - T54_MTF gated by time-of-day session windows
     - VRP × NYO/CME open windows
     - Triple-gate: MTF + VRP + spread-tight
     - AND-of-2 / OR-of-3 ensembles
  B. ML-style feature gates on CANON_INV_236 (30+ variants)
     - Tick velocity, spread/ATR, time-of-day, ATR percentile,
       distance from VWAP, recent tick balance, day-of-week, PDH/PDL prox
     - Exhaustive sweep of 2-feature AND-gates
  C. Microstructure-aware execution (30+ variants)
     - Early-generation front-of-queue LIMIT (generate 60s ahead)
     - Off-touch entries (LIMIT 1pt past pullback)
     - Multi-ladder LIMITs at fib 0.236/0.382/0.5 (already in round 7)
     - Reverse-direction LIMITs (opposite-fakeout catch)
     - Spread-compression gate (>5 ticks of 0.25pt spread)
     - Volume-cluster gate (>30s of tight range)
  D. NEW indicators (100+ variants)
     - Hurst exponent regime
     - Choppiness Index gating
     - DeMarker extremes
     - Aroon oscillator
     - Kaufman Efficiency Ratio gate
     - Range Filter touches
     - CCI extremes
     - Williams %R extremes
     - MFI extremes
     - Stoch RSI crossovers
     - PSAR flips
     - Ulcer Index regime
     - Force Index extremes
     - Chande Momentum cross
     - VIDYA crossovers
     - Heikin-Ashi 3-bar trend
     - Renko brick reversal
     - Information entropy gate
     - Schaff Trend Cycle
  E. Hourly/session intersections of pullback
     - CANON_INV_236 confined to RTH-only / NYO-only / CME-only

EXECUTION MODEL: SAME as round 7 (queue overshoot, 200ms latency, 10pt
approach, single-LIMIT lock, stop-MARKET slip, $1.91/RT). All new
strategies use fill_mode={limit,marketable,stop}, exit_mode=stop_market
unless explicitly stop_limit.

Outputs:
  - research/round8_results.md
  - research/round8_summary.csv
  - research/round8_checkpoint.pkl
"""
from __future__ import annotations
import argparse
import csv
import math
import os
import pickle
import random
import sys
import time
from collections import deque
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

# Reuse round 7 (which reuses 6 / 4) for executor, classes, helpers.
from research import round4_search as _r4  # noqa
sys.modules.setdefault("round4_search", _r4)
from research import round6_search as _r6  # noqa
sys.modules.setdefault("round6_search", _r6)
from research import round7_search as _r7  # noqa
sys.modules.setdefault("round7_search", _r7)

StrategyBase = _r4.StrategyBase
BarBuilder = _r4.BarBuilder
PullbackStrategy = _r4.PullbackStrategy
MarketablePullback = _r6.MarketablePullback
MTFConfluence = _r7.MTFConfluence
VolRegimePullback = _r7.VolRegimePullback
StopRunReversal = _r7.StopRunReversal
attach_r7_executor = _r7.attach_r7_executor
r7_bot_on_tick = _r7.r7_bot_on_tick
_patched_add_setup_r7 = _r7._patched_add_setup_r7

# Mirror execution constants exactly.
PATH = _r7.PATH
DEFAULT_OFFSET = _r7.DEFAULT_OFFSET
CHECKPOINT_EVERY_TICKS = _r7.CHECKPOINT_EVERY_TICKS

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
STALE_FILL_PROB = _r7.STALE_FILL_PROB
TICK = _r7.TICK
MARKETABLE_SLIP_PT = _r7.MARKETABLE_SLIP_PT
STOP_ENTRY_SLIP_PT = _r7.STOP_ENTRY_SLIP_PT


# =============================================================================
# A shared MARKET-CONTEXT layer
# =============================================================================
# Each tick, we update a small set of features (spread, tick velocity,
# rolling tick up/down balance, ATR percentile, distance from session-VWAP,
# session/window flags). Strategies query MarketContext to decide whether
# to fire.
class MarketContext:
    """Singleton holding rolling features used by gate filters."""

    def __init__(self):
        # Per-tick state.
        self.last_px = None
        self.last_bid = None
        self.last_ask = None
        self.last_spread = 0.5
        # Spread-compression streak (count of consecutive ticks with
        # spread <= 0.25)
        self.spread_tight_streak = 0
        # Recent ticks (ts, last) for velocity & cumdelta calculation.
        self._tick_buf = deque(maxlen=2000)  # ~last 5 min
        self._dir_buf = deque(maxlen=500)    # last 500 directional ticks
        # ATR percentile via 1m bar history (60-bar window).
        self._bar_ranges = deque(maxlen=120)
        self._cur_atr_pct = 0.5  # 0..1 rank of current bar's range vs window
        self._cur_atr = 0.0
        # Session VWAP (resets each UTC day).
        self._vwap_day = None
        self._vwap_sum_pv = 0.0
        self._vwap_sum_v = 0.0
        self.vwap = None
        # Prior-day high/low.
        self._cur_day = None
        self._cur_hi = -float('inf')
        self._cur_lo = float('inf')
        self.pdh = None
        self.pdl = None

    def feed_tick(self, ts, last, bid, ask):
        self.last_px = last
        self.last_bid = bid
        self.last_ask = ask
        spread = ask - bid
        self.last_spread = spread
        if spread <= 0.25 + 1e-9:
            self.spread_tight_streak += 1
        else:
            self.spread_tight_streak = 0
        self._tick_buf.append((ts, last))
        # Prune to last 300s
        while self._tick_buf and ts - self._tick_buf[0][0] > 300:
            self._tick_buf.popleft()
        # Directional tick balance (last 500 dir-ticks)
        if len(self._tick_buf) >= 2:
            prev = self._tick_buf[-2][1]
            if last > prev:
                self._dir_buf.append(1)
            elif last < prev:
                self._dir_buf.append(-1)
        # Day-rollover for VWAP / PDH / PDL.
        day_key = int(ts // 86400)
        if day_key != self._vwap_day:
            self._vwap_day = day_key
            self._vwap_sum_pv = 0.0
            self._vwap_sum_v = 0.0
        # VWAP: weight = 1 per tick.
        self._vwap_sum_pv += last
        self._vwap_sum_v += 1
        self.vwap = self._vwap_sum_pv / self._vwap_sum_v
        if day_key != self._cur_day:
            if self._cur_day is not None:
                self.pdh = self._cur_hi
                self.pdl = self._cur_lo
            self._cur_day = day_key
            self._cur_hi = last
            self._cur_lo = last
        else:
            if last > self._cur_hi:
                self._cur_hi = last
            if last < self._cur_lo:
                self._cur_lo = last

    def feed_bar(self, bo, bh, bl, bc):
        rng = bh - bl
        self._bar_ranges.append(rng)
        if len(self._bar_ranges) >= 20:
            sub = sorted(self._bar_ranges)
            # rank of current rng
            idx = 0
            for r in sub:
                if r < rng:
                    idx += 1
            self._cur_atr_pct = idx / len(sub)
            self._cur_atr = sum(self._bar_ranges) / len(self._bar_ranges)

    # ---- Feature accessors ----
    def tick_velocity(self, secs=10):
        if len(self._tick_buf) < 5:
            return 0.0
        ts_now = self._tick_buf[-1][0]
        count = 0
        for t, _ in reversed(self._tick_buf):
            if ts_now - t > secs:
                break
            count += 1
        return count / max(0.1, secs)

    def tick_balance(self, n=200):
        if len(self._dir_buf) < 10:
            return 0
        sub = list(self._dir_buf)[-n:]
        return sum(sub)

    def dist_from_vwap(self):
        if self.vwap is None or self.last_px is None:
            return 0.0
        return self.last_px - self.vwap

    def atr(self):
        return self._cur_atr

    def atr_pct(self):
        return self._cur_atr_pct

    def in_window(self, hh, mn, window):
        """window = ((hs, ms), (he, me)) or None for any time."""
        if window is None:
            return True
        (hs, ms), (he, me) = window
        t = hh * 60 + mn
        s = hs * 60 + ms
        e = he * 60 + me
        if s < e:
            return s <= t < e
        else:
            return t >= s or t < e


MARKET = MarketContext()


# =============================================================================
# Filtered/Gated MTF & Pullback strategies
# =============================================================================
class GatedMTFInvert(MTFConfluence):
    """MTF Confluence pullback (INVERT) with optional MARKET filters:
       - vol regime (atr min/max via context.atr())
       - spread compression (require spread_tight_streak >= N)
       - tick balance must agree with intended trade direction
       - time-of-day window restriction
       - dist_from_vwap must be within range
       - SRR cohort proximity (require recent sweep pattern detected
         by parallel SRR detector — stored in MARKET via outside hook)
    """
    def __init__(self, name, impulse_pts=6.0, impulse_bars=4,
                 pull_pct=0.382, stop_pts=5, target_pts=20,
                 htf_sma_bars=10, invert=True,
                 # Gate params
                 atr_min=None, atr_max=None,
                 atr_pct_min=None, atr_pct_max=None,
                 spread_tight_min=None,
                 require_aligned_balance=False,
                 balance_n=200, balance_thresh=20,
                 window=None,
                 dist_vwap_min=None, dist_vwap_max=None,
                 max_spread=None,
                 require_srr_recent=False,
                 srr_recent_window_s=120,
                 cooldown_s=10, max_hold=MAX_HOLD_S,
                 session_start=None, session_end=None,
                 expires=300):
        super().__init__(name, impulse_pts=impulse_pts,
                         impulse_bars=impulse_bars, pull_pct=pull_pct,
                         stop_pts=stop_pts, target_pts=target_pts,
                         invert=invert, htf_sma_bars=htf_sma_bars,
                         cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start,
                         session_end=session_end, expires=expires)
        self.atr_min = atr_min; self.atr_max = atr_max
        self.atr_pct_min = atr_pct_min; self.atr_pct_max = atr_pct_max
        self.spread_tight_min = spread_tight_min
        self.require_aligned_balance = require_aligned_balance
        self.balance_n = balance_n
        self.balance_thresh = balance_thresh
        self.window = window
        self.dist_vwap_min = dist_vwap_min
        self.dist_vwap_max = dist_vwap_max
        self.max_spread = max_spread
        self.require_srr_recent = require_srr_recent
        self.srr_recent_window_s = srr_recent_window_s

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        # Apply window gate
        if self.window is not None and not MARKET.in_window(hh, mn, self.window):
            return
        # ATR gates
        atr = MARKET.atr()
        if self.atr_min is not None and atr < self.atr_min:
            return
        if self.atr_max is not None and atr > self.atr_max:
            return
        if self.atr_pct_min is not None and MARKET.atr_pct() < self.atr_pct_min:
            return
        if self.atr_pct_max is not None and MARKET.atr_pct() > self.atr_pct_max:
            return
        # Spread gates
        if self.spread_tight_min is not None and MARKET.spread_tight_streak < self.spread_tight_min:
            return
        if self.max_spread is not None and MARKET.last_spread > self.max_spread:
            return
        # Distance from VWAP
        d = MARKET.dist_from_vwap()
        if self.dist_vwap_min is not None and abs(d) < self.dist_vwap_min:
            return
        if self.dist_vwap_max is not None and abs(d) > self.dist_vwap_max:
            return
        # SRR-recent gate
        if self.require_srr_recent:
            last = MARKET.__dict__.get('_last_srr_ts', None)
            if last is None or (ts - last) > self.srr_recent_window_s:
                return
        # Tick balance gate vs intended direction
        if self.require_aligned_balance:
            bal = MARKET.tick_balance(self.balance_n)
            # We'll determine want side from the MTF logic; compute net
            # before calling parent. Use last bars to estimate.
            if len(hist) < self.impulse_bars:
                return
            win = list(hist)[-self.impulse_bars:]
            net = win[-1][3] - win[0][0]
            if abs(net) < self.impulse_pts:
                return
            # Inverted side
            if net > 0:
                want = "SHORT"
            else:
                want = "LONG"
            if want == "LONG" and bal < self.balance_thresh:
                return
            if want == "SHORT" and bal > -self.balance_thresh:
                return
        # Delegate to parent
        super().on_bar_close(ts, hh, mn, bo, bh, bl, bc, hist)


# =============================================================================
# Gated CANON_INV_236 pullback (ML-style feature filters)
# =============================================================================
class GatedCanonPullback(MarketablePullback):
    """CANON_INV_236 (5pt impulse / 4bar / 0.236 pull / 10stop / 20target /
    invert=True) with optional ML-style filters applied at signal-gen time.
    """
    def __init__(self, name, impulse_pts=5.0, impulse_bars=4,
                 pull_pct=0.236, stop_pts=10, target_pts=20, invert=True,
                 atr_min=None, atr_max=None,
                 atr_pct_min=None, atr_pct_max=None,
                 velocity_min=None, velocity_max=None,
                 balance_align=False, balance_n=200, balance_thresh=20,
                 max_spread=None, spread_tight_min=None,
                 dist_vwap_min=None, dist_vwap_max=None,
                 window=None,
                 cooldown_s=10, max_hold=MAX_HOLD_S,
                 session_start=None, session_end=None):
        super().__init__(name, impulse_pts=impulse_pts,
                         impulse_bars=impulse_bars, pull_pct=pull_pct,
                         stop_pts=stop_pts, target_pts=target_pts,
                         invert=invert, cooldown_s=cooldown_s,
                         max_hold=max_hold,
                         session_start=session_start,
                         session_end=session_end)
        self.atr_min = atr_min; self.atr_max = atr_max
        self.atr_pct_min = atr_pct_min; self.atr_pct_max = atr_pct_max
        self.velocity_min = velocity_min; self.velocity_max = velocity_max
        self.balance_align = balance_align
        self.balance_n = balance_n
        self.balance_thresh = balance_thresh
        self.max_spread = max_spread
        self.spread_tight_min = spread_tight_min
        self.dist_vwap_min = dist_vwap_min
        self.dist_vwap_max = dist_vwap_max
        self.window = window

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if self.window is not None and not MARKET.in_window(hh, mn, self.window):
            return
        if self.atr_min is not None and MARKET.atr() < self.atr_min:
            return
        if self.atr_max is not None and MARKET.atr() > self.atr_max:
            return
        if self.atr_pct_min is not None and MARKET.atr_pct() < self.atr_pct_min:
            return
        if self.atr_pct_max is not None and MARKET.atr_pct() > self.atr_pct_max:
            return
        v = MARKET.tick_velocity(10)
        if self.velocity_min is not None and v < self.velocity_min:
            return
        if self.velocity_max is not None and v > self.velocity_max:
            return
        if self.max_spread is not None and MARKET.last_spread > self.max_spread:
            return
        if self.spread_tight_min is not None and MARKET.spread_tight_streak < self.spread_tight_min:
            return
        d = MARKET.dist_from_vwap()
        if self.dist_vwap_min is not None and abs(d) < self.dist_vwap_min:
            return
        if self.dist_vwap_max is not None and abs(d) > self.dist_vwap_max:
            return
        if self.balance_align:
            if len(hist) < self.impulse_bars:
                return
            win = list(hist)[-self.impulse_bars:]
            net = win[-1][3] - win[0][0]
            if abs(net) < self.impulse_pts:
                return
            # We're inverted -> trade against impulse
            if net > 0:
                want = "SHORT"
            else:
                want = "LONG"
            bal = MARKET.tick_balance(self.balance_n)
            if want == "LONG" and bal < self.balance_thresh:
                return
            if want == "SHORT" and bal > -self.balance_thresh:
                return
        super().on_bar_close(ts, hh, mn, bo, bh, bl, bc, hist)


# =============================================================================
# Microstructure-aware strategies
# =============================================================================
class OffTouchPullback(MarketablePullback):
    """Same as MarketablePullback but the LIMIT entry is placed 1pt
    BEYOND the pullback level (worse price, lower fill rate, immediate
    buffer if filled).
    """
    def __init__(self, name, offset_pts=1.0, **kwargs):
        super().__init__(name, **kwargs)
        self.offset_pts = offset_pts

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        # Generate signals via parent, then tweak entries to be 1pt beyond.
        pre = len(self.pending)
        super().on_bar_close(ts, hh, mn, bo, bh, bl, bc, hist)
        for s in self.pending[pre:]:
            # Move entry past the pullback by offset_pts.
            orig = s.get('orig', s['side'])
            if orig == 'LONG':
                # We're inverted to SHORT; original entry was a fade-LONG
                # LIMIT at retracement. Wait, in MarketablePullback INVERT
                # case: orig_side LONG and side SHORT. The entry sits at
                # ih - pull_pct * rng (a fade-fill for SHORT). We want
                # the SHORT LIMIT 1pt HIGHER (further into the
                # pullback) to capture deeper retracement.
                if s['side'] == 'SHORT':
                    new_entry = s['entry'] + self.offset_pts
                    s['entry'] = new_entry
                    s['stop'] = new_entry + self.stop_pts
                    s['target'] = new_entry - self.target_pts
                else:
                    new_entry = s['entry'] - self.offset_pts
                    s['entry'] = new_entry
                    s['stop'] = new_entry - self.stop_pts
                    s['target'] = new_entry + self.target_pts
            else:
                if s['side'] == 'LONG':
                    new_entry = s['entry'] - self.offset_pts
                    s['entry'] = new_entry
                    s['stop'] = new_entry - self.stop_pts
                    s['target'] = new_entry + self.target_pts
                else:
                    new_entry = s['entry'] + self.offset_pts
                    s['entry'] = new_entry
                    s['stop'] = new_entry + self.stop_pts
                    s['target'] = new_entry - self.target_pts


class EarlyPullback(MarketablePullback):
    """Same MarketablePullback but generate signals on a 3-bar history
    instead of waiting for the 4th. This generates earlier, giving the
    LIMIT more queue time / earlier arming."""
    pass  # Use impulse_bars=3 in constructor


# =============================================================================
# NEW indicator strategies
# =============================================================================

# ---- D1: Choppiness Index gate ----
class ChoppinessGatedFade(StrategyBase):
    """Compute Choppiness Index (CI) over N bars. When CI > thresh
    (very choppy / range-bound), execute a fade-the-bar signal."""
    def __init__(self, name, lookback=14, ci_min=60,
                 stop_pts=4, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=60, fade=True,
                 min_bar_move=1.0):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.lookback = lookback; self.ci_min = ci_min
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires; self.fade = fade
        self.min_bar_move = min_bar_move

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.lookback + 1:
            return
        sub = list(hist)[-self.lookback:]
        atr_sum = 0.0
        for i in range(1, len(sub)):
            o, h, l, c = sub[i]
            pc = sub[i - 1][3]
            atr_sum += max(h - l, abs(h - pc), abs(l - pc))
        hh_v = max(b[1] for b in sub)
        ll_v = min(b[2] for b in sub)
        rng = hh_v - ll_v
        if rng <= 0 or atr_sum <= 0:
            return
        # CI = 100 * log10(sum_tr / range) / log10(N)
        ci = 100.0 * math.log10(atr_sum / rng) / math.log10(self.lookback)
        if ci < self.ci_min:
            return
        move = bc - bo
        if abs(move) < self.min_bar_move:
            return
        if self.fade:
            side = "SHORT" if move > 0 else "LONG"
        else:
            side = "LONG" if move > 0 else "SHORT"
        entry = bc
        extra = {'fill_mode': 'marketable',
                 'stop_offset_pts': self.stop_pts,
                 'target_offset_pts': self.target_pts}
        if side == "LONG":
            self.add_setup(side, side, entry, entry - self.stop_pts,
                           entry + self.target_pts, ts,
                           key=("chp_l", round(entry, 1)),
                           expires_in=self.expires, extra=extra)
        else:
            self.add_setup(side, side, entry, entry + self.stop_pts,
                           entry - self.target_pts, ts,
                           key=("chp_s", round(entry, 1)),
                           expires_in=self.expires, extra=extra)


# ---- D2: DeMarker extremes ----
class DeMarker(StrategyBase):
    """DeMarker = rolling DeMax / (DeMax+DeMin) over N bars.
    Fade extreme readings (>0.7 SHORT, <0.3 LONG)."""
    def __init__(self, name, lookback=14, hi=0.7, lo=0.3,
                 stop_pts=4, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=60):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.lookback = lookback; self.hi = hi; self.lo = lo
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.lookback + 1:
            return
        sub = list(hist)[-(self.lookback + 1):]
        demax = 0.0; demin = 0.0
        for i in range(1, len(sub)):
            dh = sub[i][1] - sub[i - 1][1]
            dl = sub[i - 1][2] - sub[i][2]
            demax += max(0.0, dh)
            demin += max(0.0, dl)
        denom = demax + demin
        if denom <= 0:
            return
        dem = demax / denom
        entry = bc
        extra = {'fill_mode': 'marketable',
                 'stop_offset_pts': self.stop_pts,
                 'target_offset_pts': self.target_pts}
        if dem > self.hi:
            self.add_setup("SHORT", "SHORT", entry, entry + self.stop_pts,
                           entry - self.target_pts, ts,
                           key=("dem_s", round(entry, 1)),
                           expires_in=self.expires, extra=extra)
        elif dem < self.lo:
            self.add_setup("LONG", "LONG", entry, entry - self.stop_pts,
                           entry + self.target_pts, ts,
                           key=("dem_l", round(entry, 1)),
                           expires_in=self.expires, extra=extra)


# ---- D3: CCI extremes ----
class CCI(StrategyBase):
    """Commodity Channel Index; fade beyond +200/-200."""
    def __init__(self, name, lookback=20, hi=200, lo=-200,
                 stop_pts=4, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=60):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.lookback = lookback; self.hi = hi; self.lo = lo
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.lookback:
            return
        sub = list(hist)[-self.lookback:]
        tps = [(b[1] + b[2] + b[3]) / 3.0 for b in sub]
        tp = tps[-1]
        sma_tp = sum(tps) / len(tps)
        md = sum(abs(x - sma_tp) for x in tps) / len(tps)
        if md <= 0:
            return
        cci = (tp - sma_tp) / (0.015 * md)
        entry = bc
        extra = {'fill_mode': 'marketable',
                 'stop_offset_pts': self.stop_pts,
                 'target_offset_pts': self.target_pts}
        if cci > self.hi:
            self.add_setup("SHORT", "SHORT", entry, entry + self.stop_pts,
                           entry - self.target_pts, ts,
                           key=("cci_s", round(entry, 1)),
                           expires_in=self.expires, extra=extra)
        elif cci < self.lo:
            self.add_setup("LONG", "LONG", entry, entry - self.stop_pts,
                           entry + self.target_pts, ts,
                           key=("cci_l", round(entry, 1)),
                           expires_in=self.expires, extra=extra)


# ---- D4: Williams %R ----
class WilliamsR(StrategyBase):
    """Williams %R over N bars. <-80 oversold (LONG), >-20 overbought (SHORT)."""
    def __init__(self, name, lookback=14, hi=-20, lo=-80, fade=True,
                 stop_pts=4, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=60):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.lookback = lookback; self.hi = hi; self.lo = lo
        self.fade = fade
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.lookback:
            return
        sub = list(hist)[-self.lookback:]
        hh_v = max(b[1] for b in sub)
        ll_v = min(b[2] for b in sub)
        if hh_v == ll_v:
            return
        wr = -100.0 * (hh_v - bc) / (hh_v - ll_v)
        entry = bc
        extra = {'fill_mode': 'marketable',
                 'stop_offset_pts': self.stop_pts,
                 'target_offset_pts': self.target_pts}
        if wr > self.hi:
            side = "SHORT" if self.fade else "LONG"
            if side == "SHORT":
                self.add_setup(side, side, entry, entry + self.stop_pts,
                               entry - self.target_pts, ts,
                               key=("wr_s", round(entry, 1)),
                               expires_in=self.expires, extra=extra)
            else:
                self.add_setup(side, side, entry, entry - self.stop_pts,
                               entry + self.target_pts, ts,
                               key=("wr_l", round(entry, 1)),
                               expires_in=self.expires, extra=extra)
        elif wr < self.lo:
            side = "LONG" if self.fade else "SHORT"
            if side == "LONG":
                self.add_setup(side, side, entry, entry - self.stop_pts,
                               entry + self.target_pts, ts,
                               key=("wr_l2", round(entry, 1)),
                               expires_in=self.expires, extra=extra)
            else:
                self.add_setup(side, side, entry, entry + self.stop_pts,
                               entry - self.target_pts, ts,
                               key=("wr_s2", round(entry, 1)),
                               expires_in=self.expires, extra=extra)


# ---- D5: Kaufman Efficiency Ratio gate (gate vs trend) ----
class KaufmanERGated(StrategyBase):
    """Kaufman ER = |close[N] - close[0]| / sum(|close[i] - close[i-1]|).
    High ER -> trending. Use as gate: only trade pullback when ER > thresh
    (trending) -> trade in direction of trend.
    """
    def __init__(self, name, lookback=20, er_min=0.5, fade=False,
                 stop_pts=4, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=60,
                 min_bar_move=1.0):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.lookback = lookback; self.er_min = er_min
        self.fade = fade
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires
        self.min_bar_move = min_bar_move

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.lookback + 1:
            return
        sub = list(hist)[-(self.lookback + 1):]
        net = abs(sub[-1][3] - sub[0][3])
        path = sum(abs(sub[i][3] - sub[i - 1][3]) for i in range(1, len(sub)))
        if path <= 0:
            return
        er = net / path
        if er < self.er_min:
            return
        # Direction = sign of net move; trade with trend.
        net_signed = sub[-1][3] - sub[0][3]
        move = bc - bo
        if abs(move) < self.min_bar_move:
            return
        if self.fade:
            side = "SHORT" if net_signed > 0 else "LONG"
        else:
            side = "LONG" if net_signed > 0 else "SHORT"
        entry = bc
        extra = {'fill_mode': 'marketable',
                 'stop_offset_pts': self.stop_pts,
                 'target_offset_pts': self.target_pts}
        if side == "LONG":
            self.add_setup(side, side, entry, entry - self.stop_pts,
                           entry + self.target_pts, ts,
                           key=("ker_l", round(entry, 1)),
                           expires_in=self.expires, extra=extra)
        else:
            self.add_setup(side, side, entry, entry + self.stop_pts,
                           entry - self.target_pts, ts,
                           key=("ker_s", round(entry, 1)),
                           expires_in=self.expires, extra=extra)


# ---- D6: Aroon oscillator ----
class Aroon(StrategyBase):
    """Aroon-Up = 100 * (N - bars_since_high) / N
    Aroon-Down = 100 * (N - bars_since_low) / N
    Fade when both > 70 (extreme range) or follow Up>Down crossover.
    """
    def __init__(self, name, lookback=14, fade=True,
                 stop_pts=4, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=60):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.lookback = lookback; self.fade = fade
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires
        self._prev_diff = 0

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.lookback:
            return
        sub = list(hist)[-self.lookback:]
        max_h = max(b[1] for b in sub)
        min_l = min(b[2] for b in sub)
        idx_hi = max(i for i, b in enumerate(sub) if b[1] == max_h)
        idx_lo = max(i for i, b in enumerate(sub) if b[2] == min_l)
        bars_since_hi = len(sub) - 1 - idx_hi
        bars_since_lo = len(sub) - 1 - idx_lo
        au = 100.0 * (self.lookback - bars_since_hi) / self.lookback
        ad = 100.0 * (self.lookback - bars_since_lo) / self.lookback
        diff = au - ad
        # Crossover
        if self._prev_diff <= 0 and diff > 20:
            side = "LONG"
            if self.fade:
                side = "SHORT"
            self._emit(ts, bc, side)
        elif self._prev_diff >= 0 and diff < -20:
            side = "SHORT"
            if self.fade:
                side = "LONG"
            self._emit(ts, bc, side)
        self._prev_diff = diff

    def _emit(self, ts, entry, side):
        extra = {'fill_mode': 'marketable',
                 'stop_offset_pts': self.stop_pts,
                 'target_offset_pts': self.target_pts}
        if side == "LONG":
            self.add_setup(side, side, entry, entry - self.stop_pts,
                           entry + self.target_pts, ts,
                           key=("ar_l", round(entry, 1)),
                           expires_in=self.expires, extra=extra)
        else:
            self.add_setup(side, side, entry, entry + self.stop_pts,
                           entry - self.target_pts, ts,
                           key=("ar_s", round(entry, 1)),
                           expires_in=self.expires, extra=extra)


# ---- D7: Stochastic RSI crossovers in extreme zones ----
class StochRSI(StrategyBase):
    """Compute RSI, then rolling stochastic of RSI. Cross above 20 LONG
    or cross below 80 SHORT (mean-revert).
    """
    def __init__(self, name, rsi_lk=14, stoch_lk=14, hi=80, lo=20,
                 fade=True, stop_pts=4, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=60):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.rsi_lk = rsi_lk; self.stoch_lk = stoch_lk
        self.hi = hi; self.lo = lo; self.fade = fade
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires
        self._rsi_buf = deque(maxlen=stoch_lk + 5)
        self._prev_srsi = None

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.rsi_lk + 1:
            return
        sub = list(hist)[-(self.rsi_lk + 1):]
        gains = 0.0; losses = 0.0
        for i in range(1, len(sub)):
            d = sub[i][3] - sub[i - 1][3]
            if d > 0:
                gains += d
            else:
                losses -= d
        if (gains + losses) <= 0:
            return
        rsi = 100.0 * gains / (gains + losses)
        self._rsi_buf.append(rsi)
        if len(self._rsi_buf) < self.stoch_lk:
            return
        sub_rsi = list(self._rsi_buf)[-self.stoch_lk:]
        mn_r = min(sub_rsi); mx_r = max(sub_rsi)
        if mx_r == mn_r:
            return
        srsi = 100.0 * (rsi - mn_r) / (mx_r - mn_r)
        prev = self._prev_srsi
        self._prev_srsi = srsi
        if prev is None:
            return
        entry = bc
        extra = {'fill_mode': 'marketable',
                 'stop_offset_pts': self.stop_pts,
                 'target_offset_pts': self.target_pts}
        if prev > self.hi and srsi <= self.hi:
            side = "SHORT" if self.fade else "LONG"
            if side == "SHORT":
                self.add_setup(side, side, entry, entry + self.stop_pts,
                               entry - self.target_pts, ts,
                               key=("sr_s", round(entry, 1)),
                               expires_in=self.expires, extra=extra)
            else:
                self.add_setup(side, side, entry, entry - self.stop_pts,
                               entry + self.target_pts, ts,
                               key=("sr_l", round(entry, 1)),
                               expires_in=self.expires, extra=extra)
        elif prev < self.lo and srsi >= self.lo:
            side = "LONG" if self.fade else "SHORT"
            if side == "LONG":
                self.add_setup(side, side, entry, entry - self.stop_pts,
                               entry + self.target_pts, ts,
                               key=("sr_l2", round(entry, 1)),
                               expires_in=self.expires, extra=extra)
            else:
                self.add_setup(side, side, entry, entry + self.stop_pts,
                               entry - self.target_pts, ts,
                               key=("sr_s2", round(entry, 1)),
                               expires_in=self.expires, extra=extra)


# ---- D8: Range Filter (smoothed extremes) ----
class RangeFilter(StrategyBase):
    """ATR-based moving extremes. Build upper/lower bands at SMA +/- k*ATR.
    Trade band touches with mean-revert.
    """
    def __init__(self, name, lookback=20, k=2.0, fade=True,
                 stop_pts=4, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=60):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.lookback = lookback; self.k = k; self.fade = fade
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.lookback + 1:
            return
        sub = list(hist)[-self.lookback:]
        sma = sum(b[3] for b in sub) / len(sub)
        atr_sum = 0.0
        for i in range(1, len(sub)):
            o, h, l, c = sub[i]
            pc = sub[i - 1][3]
            atr_sum += max(h - l, abs(h - pc), abs(l - pc))
        atr = atr_sum / max(1, len(sub) - 1)
        if atr <= 0:
            return
        upper = sma + self.k * atr
        lower = sma - self.k * atr
        entry = bc
        extra = {'fill_mode': 'marketable',
                 'stop_offset_pts': self.stop_pts,
                 'target_offset_pts': self.target_pts}
        if bh >= upper and bc < upper - 0.1:
            side = "SHORT" if self.fade else "LONG"
            if side == "SHORT":
                self.add_setup(side, side, entry, entry + self.stop_pts,
                               entry - self.target_pts, ts,
                               key=("rf_s", round(upper, 1)),
                               expires_in=self.expires, extra=extra)
            else:
                self.add_setup(side, side, entry, entry - self.stop_pts,
                               entry + self.target_pts, ts,
                               key=("rf_l", round(upper, 1)),
                               expires_in=self.expires, extra=extra)
        elif bl <= lower and bc > lower + 0.1:
            side = "LONG" if self.fade else "SHORT"
            if side == "LONG":
                self.add_setup(side, side, entry, entry - self.stop_pts,
                               entry + self.target_pts, ts,
                               key=("rf_l2", round(lower, 1)),
                               expires_in=self.expires, extra=extra)
            else:
                self.add_setup(side, side, entry, entry + self.stop_pts,
                               entry - self.target_pts, ts,
                               key=("rf_s2", round(lower, 1)),
                               expires_in=self.expires, extra=extra)


# ---- D9: Hurst exponent regime ----
class HurstGated(StrategyBase):
    """Compute Hurst H over rolling N bars via R/S analysis.
    H>0.55: trending -> trade with trend
    H<0.45: mean-reverting -> fade
    Else: skip.
    """
    def __init__(self, name, lookback=64, h_trend=0.55, h_revert=0.45,
                 stop_pts=4, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=60,
                 min_bar_move=1.5):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.lookback = lookback
        self.h_trend = h_trend; self.h_revert = h_revert
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires
        self.min_bar_move = min_bar_move

    def _hurst(self, ys):
        n = len(ys)
        if n < 8:
            return 0.5
        # Rescaled range over multiple sub-periods
        # Simple: split into halves, compute R/S for each
        try:
            rs = []
            for k in [n // 4, n // 2, n]:
                if k < 4:
                    continue
                sub = ys[-k:]
                mean = sum(sub) / len(sub)
                dev = [x - mean for x in sub]
                cum = 0.0; mn = 0.0; mx = 0.0
                for d in dev:
                    cum += d
                    if cum > mx: mx = cum
                    if cum < mn: mn = cum
                rng = mx - mn
                std = math.sqrt(sum((x - mean) ** 2 for x in sub) / len(sub))
                if std > 0 and rng > 0:
                    rs.append((math.log(k), math.log(rng / std)))
            if len(rs) < 2:
                return 0.5
            xs = [r[0] for r in rs]
            ysv = [r[1] for r in rs]
            mx = sum(xs) / len(xs)
            my = sum(ysv) / len(ysv)
            num = sum((xs[i] - mx) * (ysv[i] - my) for i in range(len(rs)))
            den = sum((xs[i] - mx) ** 2 for i in range(len(rs)))
            if den <= 0:
                return 0.5
            return num / den
        except Exception:
            return 0.5

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.lookback:
            return
        sub = list(hist)[-self.lookback:]
        ys = [b[3] for b in sub]
        H = self._hurst(ys)
        move = bc - bo
        if abs(move) < self.min_bar_move:
            return
        entry = bc
        extra = {'fill_mode': 'marketable',
                 'stop_offset_pts': self.stop_pts,
                 'target_offset_pts': self.target_pts}
        if H >= self.h_trend:
            # Follow trend
            side = "LONG" if move > 0 else "SHORT"
        elif H <= self.h_revert:
            # Fade
            side = "SHORT" if move > 0 else "LONG"
        else:
            return
        if side == "LONG":
            self.add_setup(side, side, entry, entry - self.stop_pts,
                           entry + self.target_pts, ts,
                           key=("hu_l", round(entry, 1)),
                           expires_in=self.expires, extra=extra)
        else:
            self.add_setup(side, side, entry, entry + self.stop_pts,
                           entry - self.target_pts, ts,
                           key=("hu_s", round(entry, 1)),
                           expires_in=self.expires, extra=extra)


# ---- D10: PSAR flip ----
class PSARFlip(StrategyBase):
    """Parabolic SAR. On flip, trade in new direction (or fade)."""
    def __init__(self, name, af_start=0.02, af_max=0.2, fade=False,
                 stop_pts=4, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=60):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.af0 = af_start; self.af_max = af_max
        self.fade = fade
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires
        self._trend = 0  # +1 up, -1 down
        self._sar = None; self._ep = None; self._af = self.af0

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if self._sar is None:
            self._sar = bl
            self._ep = bh
            self._trend = 1
            return
        prev_trend = self._trend
        if self._trend == 1:
            new_sar = self._sar + self._af * (self._ep - self._sar)
            new_sar = min(new_sar, bl, hist[-2][2] if len(hist) >= 2 else bl)
            if bh > self._ep:
                self._ep = bh
                self._af = min(self.af_max, self._af + self.af0)
            if bl < new_sar:
                # Flip to down
                self._trend = -1
                self._sar = self._ep
                self._ep = bl
                self._af = self.af0
            else:
                self._sar = new_sar
        else:
            new_sar = self._sar - self._af * (self._sar - self._ep)
            new_sar = max(new_sar, bh, hist[-2][1] if len(hist) >= 2 else bh)
            if bl < self._ep:
                self._ep = bl
                self._af = min(self.af_max, self._af + self.af0)
            if bh > new_sar:
                self._trend = 1
                self._sar = self._ep
                self._ep = bh
                self._af = self.af0
            else:
                self._sar = new_sar
        # Flip detection
        if prev_trend != self._trend:
            side = "LONG" if self._trend > 0 else "SHORT"
            if self.fade:
                side = "SHORT" if side == "LONG" else "LONG"
            entry = bc
            extra = {'fill_mode': 'marketable',
                     'stop_offset_pts': self.stop_pts,
                     'target_offset_pts': self.target_pts}
            if side == "LONG":
                self.add_setup(side, side, entry, entry - self.stop_pts,
                               entry + self.target_pts, ts,
                               key=("ps_l", round(entry, 1)),
                               expires_in=self.expires, extra=extra)
            else:
                self.add_setup(side, side, entry, entry + self.stop_pts,
                               entry - self.target_pts, ts,
                               key=("ps_s", round(entry, 1)),
                               expires_in=self.expires, extra=extra)


# ---- D11: TRIX cross ----
class TRIX(StrategyBase):
    """Triple-smoothed EMA momentum. TRIX = % change of triple-EMA.
    Signal line cross."""
    def __init__(self, name, period=15, signal_p=9, fade=False,
                 stop_pts=4, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=60):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.period = period; self.signal_p = signal_p
        self.fade = fade
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires
        self._e1 = None; self._e2 = None; self._e3 = None
        self._sig = None
        self._prev_trix = None
        self._prev_diff = None
        self._k = 2.0 / (period + 1)
        self._ks = 2.0 / (signal_p + 1)

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if self._e1 is None:
            self._e1 = bc; self._e2 = bc; self._e3 = bc; return
        self._e1 += self._k * (bc - self._e1)
        self._e2 += self._k * (self._e1 - self._e2)
        self._e3 += self._k * (self._e2 - self._e3)
        if self._prev_trix is None:
            self._prev_trix = self._e3
            return
        trix = (self._e3 - self._prev_trix) / max(0.001, abs(self._prev_trix)) * 1000.0
        self._prev_trix = self._e3
        if self._sig is None:
            self._sig = trix
            self._prev_diff = trix - self._sig
            return
        self._sig += self._ks * (trix - self._sig)
        diff = trix - self._sig
        if self._prev_diff is not None:
            if self._prev_diff <= 0 and diff > 0:
                side = "LONG" if not self.fade else "SHORT"
                self._emit(ts, bc, side)
            elif self._prev_diff >= 0 and diff < 0:
                side = "SHORT" if not self.fade else "LONG"
                self._emit(ts, bc, side)
        self._prev_diff = diff

    def _emit(self, ts, entry, side):
        extra = {'fill_mode': 'marketable',
                 'stop_offset_pts': self.stop_pts,
                 'target_offset_pts': self.target_pts}
        if side == "LONG":
            self.add_setup(side, side, entry, entry - self.stop_pts,
                           entry + self.target_pts, ts,
                           key=("trx_l", round(entry, 1)),
                           expires_in=self.expires, extra=extra)
        else:
            self.add_setup(side, side, entry, entry + self.stop_pts,
                           entry - self.target_pts, ts,
                           key=("trx_s", round(entry, 1)),
                           expires_in=self.expires, extra=extra)


# ---- D12: Heikin-Ashi 3-bar trend ----
class HA3Bar(StrategyBase):
    """Heikin-Ashi: enter when 3 consecutive HA bars same color AND prior
    3 were opposite (trend change confirmed)."""
    def __init__(self, name, n=3, fade=False,
                 stop_pts=4, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=60):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.n = n; self.fade = fade
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires
        self._ha_close = None; self._ha_open = None
        self._sign_buf = deque(maxlen=20)

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if self._ha_close is None:
            self._ha_close = (bo + bh + bl + bc) / 4.0
            self._ha_open = (bo + bc) / 2.0
            return
        new_close = (bo + bh + bl + bc) / 4.0
        new_open = (self._ha_open + self._ha_close) / 2.0
        sign = 1 if new_close > new_open else (-1 if new_close < new_open else 0)
        self._sign_buf.append(sign)
        self._ha_close = new_close; self._ha_open = new_open
        if len(self._sign_buf) < 2 * self.n:
            return
        recent = list(self._sign_buf)[-self.n:]
        prior = list(self._sign_buf)[-(2 * self.n):-self.n]
        if not all(s == recent[0] for s in recent):
            return
        if not all(s == prior[0] for s in prior):
            return
        if recent[0] == 0 or prior[0] == 0 or recent[0] == prior[0]:
            return
        side = "LONG" if recent[0] > 0 else "SHORT"
        if self.fade:
            side = "SHORT" if side == "LONG" else "LONG"
        entry = bc
        extra = {'fill_mode': 'marketable',
                 'stop_offset_pts': self.stop_pts,
                 'target_offset_pts': self.target_pts}
        if side == "LONG":
            self.add_setup(side, side, entry, entry - self.stop_pts,
                           entry + self.target_pts, ts,
                           key=("ha3_l", round(entry, 1)),
                           expires_in=self.expires, extra=extra)
        else:
            self.add_setup(side, side, entry, entry + self.stop_pts,
                           entry - self.target_pts, ts,
                           key=("ha3_s", round(entry, 1)),
                           expires_in=self.expires, extra=extra)


# ---- D13: Force Index extremes (tick-volume proxy: bar range) ----
class ForceIndex(StrategyBase):
    """Force = (close - prev close) * range. Fade extreme readings."""
    def __init__(self, name, lookback=13, thresh_z=2.0, fade=True,
                 stop_pts=4, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=60):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.lookback = lookback; self.thresh_z = thresh_z
        self.fade = fade
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires
        self._fi_buf = deque(maxlen=lookback + 5)

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < 2:
            return
        pc = hist[-2][3]
        rng = bh - bl
        fi = (bc - pc) * rng
        self._fi_buf.append(fi)
        if len(self._fi_buf) < self.lookback:
            return
        mean = sum(self._fi_buf) / len(self._fi_buf)
        var = sum((x - mean) ** 2 for x in self._fi_buf) / len(self._fi_buf)
        std = math.sqrt(var)
        if std <= 0:
            return
        z = (fi - mean) / std
        if abs(z) < self.thresh_z:
            return
        entry = bc
        extra = {'fill_mode': 'marketable',
                 'stop_offset_pts': self.stop_pts,
                 'target_offset_pts': self.target_pts}
        if z > 0:
            side = "SHORT" if self.fade else "LONG"
        else:
            side = "LONG" if self.fade else "SHORT"
        if side == "LONG":
            self.add_setup(side, side, entry, entry - self.stop_pts,
                           entry + self.target_pts, ts,
                           key=("fi_l", round(entry, 1)),
                           expires_in=self.expires, extra=extra)
        else:
            self.add_setup(side, side, entry, entry + self.stop_pts,
                           entry - self.target_pts, ts,
                           key=("fi_s", round(entry, 1)),
                           expires_in=self.expires, extra=extra)


# ---- D14: Chande Momentum Oscillator extremes ----
class CMO(StrategyBase):
    """CMO = 100 * (sum_up - sum_down) / (sum_up + sum_down) over N bars."""
    def __init__(self, name, lookback=14, hi=50, lo=-50, fade=True,
                 stop_pts=4, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=60):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.lookback = lookback; self.hi = hi; self.lo = lo
        self.fade = fade
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.lookback + 1:
            return
        sub = list(hist)[-(self.lookback + 1):]
        up = 0.0; dn = 0.0
        for i in range(1, len(sub)):
            d = sub[i][3] - sub[i - 1][3]
            if d > 0: up += d
            else: dn -= d
        if up + dn <= 0:
            return
        cmo = 100.0 * (up - dn) / (up + dn)
        entry = bc
        extra = {'fill_mode': 'marketable',
                 'stop_offset_pts': self.stop_pts,
                 'target_offset_pts': self.target_pts}
        if cmo > self.hi:
            side = "SHORT" if self.fade else "LONG"
            if side == "SHORT":
                self.add_setup(side, side, entry, entry + self.stop_pts,
                               entry - self.target_pts, ts,
                               key=("cmo_s", round(entry, 1)),
                               expires_in=self.expires, extra=extra)
            else:
                self.add_setup(side, side, entry, entry - self.stop_pts,
                               entry + self.target_pts, ts,
                               key=("cmo_l", round(entry, 1)),
                               expires_in=self.expires, extra=extra)
        elif cmo < self.lo:
            side = "LONG" if self.fade else "SHORT"
            if side == "LONG":
                self.add_setup(side, side, entry, entry - self.stop_pts,
                               entry + self.target_pts, ts,
                               key=("cmo_l2", round(entry, 1)),
                               expires_in=self.expires, extra=extra)
            else:
                self.add_setup(side, side, entry, entry + self.stop_pts,
                               entry - self.target_pts, ts,
                               key=("cmo_s2", round(entry, 1)),
                               expires_in=self.expires, extra=extra)


# ---- D15: Information entropy gate ----
class EntropyGated(StrategyBase):
    """Compute Shannon entropy of last N dir-ticks. Low entropy = predictable
    -> trade with recent direction. High entropy = noise -> skip.
    """
    def __init__(self, name, n_ticks=100, entropy_max=0.7, fade=False,
                 stop_pts=3, target_pts=9, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=20,
                 cool_setup_s=30):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.n_ticks = n_ticks; self.entropy_max = entropy_max
        self.fade = fade
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires
        self.cool_setup_s = cool_setup_s
        self._last_setup_ts = None
        self._last_px = None

    def feed_tick(self, ts, last):
        if self._last_px is None:
            self._last_px = last
            return
        self._last_px = last
        if (self._last_setup_ts is not None and
                ts - self._last_setup_ts < self.cool_setup_s):
            return
        # Use MARKET's directional buffer
        dirs = list(MARKET._dir_buf)[-self.n_ticks:]
        if len(dirs) < self.n_ticks:
            return
        n_up = sum(1 for d in dirs if d > 0)
        n_dn = len(dirs) - n_up
        p_up = n_up / len(dirs)
        p_dn = 1.0 - p_up
        H = 0.0
        for p in (p_up, p_dn):
            if p > 0:
                H -= p * math.log2(p)
        if H > self.entropy_max:
            return
        # Direction = majority
        side = "LONG" if n_up > n_dn else "SHORT"
        if self.fade:
            side = "SHORT" if side == "LONG" else "LONG"
        self._last_setup_ts = ts
        entry = last
        extra = {'fill_mode': 'marketable',
                 'stop_offset_pts': self.stop_pts,
                 'target_offset_pts': self.target_pts}
        if side == "LONG":
            self.add_setup(side, side, entry, entry - self.stop_pts,
                           entry + self.target_pts, ts,
                           key=("ent_l", int(ts * 10) % 10000),
                           expires_in=self.expires, extra=extra)
        else:
            self.add_setup(side, side, entry, entry + self.stop_pts,
                           entry - self.target_pts, ts,
                           key=("ent_s", int(ts * 10) % 10000),
                           expires_in=self.expires, extra=extra)


# ---- D16: Ulcer Index regime gate ----
class UlcerGatedMTF(MTFConfluence):
    """MTF Confluence pullback gated by Ulcer Index regime (low UI =
    smooth trend, high UI = choppy)."""
    def __init__(self, name, ui_lookback=20, ui_min=None, ui_max=None,
                 **kwargs):
        super().__init__(name, **kwargs)
        self.ui_lookback = ui_lookback
        self.ui_min = ui_min; self.ui_max = ui_max

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.ui_lookback + 1:
            return super().on_bar_close(ts, hh, mn, bo, bh, bl, bc, hist)
        sub = list(hist)[-self.ui_lookback:]
        peak = -float('inf')
        ssq = 0.0
        for o, h, l, c in sub:
            if c > peak:
                peak = c
            if peak > 0:
                dd = 100.0 * (c - peak) / peak
                ssq += dd * dd
        ui = math.sqrt(ssq / len(sub))
        if self.ui_min is not None and ui < self.ui_min:
            return
        if self.ui_max is not None and ui > self.ui_max:
            return
        super().on_bar_close(ts, hh, mn, bo, bh, bl, bc, hist)


# =============================================================================
# Auxiliary SRR detector — runs in parallel to feed MARKET._last_srr_ts
# =============================================================================
class _SRRDetector(StrategyBase):
    """Monitors for stop-run pattern. When detected, writes ts to
    MARKET._last_srr_ts. This signals GatedMTFInvert that an SRR
    just occurred nearby."""
    def __init__(self, name="_SRRDetector_aux", lookback=20, sweep_pts=5.0):
        super().__init__(name)
        self.lookback = lookback; self.sweep_pts = sweep_pts

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.lookback + 1:
            return
        prior = list(hist)[-(self.lookback + 1):-1]
        ph = max(b[1] for b in prior)
        pl = min(b[2] for b in prior)
        if (bh >= ph + self.sweep_pts and bc < ph - 0.5) or \
           (bl <= pl - self.sweep_pts and bc > pl + 0.5):
            MARKET._last_srr_ts = ts


# =============================================================================
# Build round 8 strategy library — 250+ variants
# =============================================================================

# Time windows used by gates
W_RTH = ((13, 30), (20, 0))   # NYSE 09:30-16:00 ET = 13:30-20:00 UTC (winter)
W_NYO = ((13, 30), (15, 30))  # NYO open 2hr
W_CME = ((22, 0), (23, 0))    # CME globex open
W_LO = ((7, 0), (11, 0))      # London open
W_OVERLAP = ((13, 30), (16, 0))  # LO/NYO overlap

WINDOWS = {
    "RTH": W_RTH, "NYO": W_NYO, "CME": W_CME, "LO": W_LO, "OVR": W_OVERLAP,
}


def build_variants_round8():
    v1m = []
    v15s = []
    v30s = []
    vtick = []

    # =================================================================
    # A. Filter-gated MTF Invert (the best round-7 high-volume signal)
    # =================================================================
    # Baseline MTF for reference
    v1m.append(MTFConfluence(
        "A00_MTF_baseline_imp6_pp382_s5t20_INV",
        impulse_pts=6.0, impulse_bars=4, pull_pct=0.382,
        stop_pts=5, target_pts=20, invert=True))

    # ATR-min/max gates
    for atr_min, atr_max in [(2.0, None), (3.0, None), (5.0, None),
                              (None, 5.0), (None, 8.0), (2.0, 6.0),
                              (3.0, 8.0)]:
        tag = f"a{int(atr_min*10) if atr_min else 0}-{int(atr_max*10) if atr_max else 99}"
        v1m.append(GatedMTFInvert(
            f"A01_MTF_atr_{tag}",
            atr_min=atr_min, atr_max=atr_max))

    # ATR percentile gates
    for ap_min, ap_max in [(0.5, None), (0.7, None), (None, 0.7), (0.3, 0.8)]:
        tag = f"ap{int((ap_min or 0)*100)}-{int((ap_max or 100)*100)}"
        v1m.append(GatedMTFInvert(
            f"A02_MTF_atrpct_{tag}",
            atr_pct_min=ap_min, atr_pct_max=ap_max))

    # Spread compression gate
    for st in [5, 10, 20]:
        v1m.append(GatedMTFInvert(
            f"A03_MTF_spread_tight{st}",
            spread_tight_min=st))
    # Max spread
    for ms in [0.5, 0.75, 1.0]:
        v1m.append(GatedMTFInvert(
            f"A04_MTF_maxspread{int(ms*100)}",
            max_spread=ms))

    # Tick balance alignment gate (require balance > thresh aligned with
    # intended direction)
    for n, thr in [(100, 10), (200, 20), (300, 30), (500, 50)]:
        v1m.append(GatedMTFInvert(
            f"A05_MTF_bal_n{n}_t{thr}",
            require_aligned_balance=True,
            balance_n=n, balance_thresh=thr))

    # Time-of-day gates
    for wname, w in WINDOWS.items():
        v1m.append(GatedMTFInvert(
            f"A06_MTF_win{wname}",
            window=w))
        # And gate plus atr
        v1m.append(GatedMTFInvert(
            f"A07_MTF_win{wname}_atr2-6",
            window=w, atr_min=2.0, atr_max=6.0))

    # SRR-recent gate (require sweep pattern detected recently)
    for w_s in [60, 120, 300]:
        v1m.append(GatedMTFInvert(
            f"A08_MTF_srr_recent{w_s}",
            require_srr_recent=True, srr_recent_window_s=w_s))

    # Triple gate: window + atr + balance
    for wname in ["RTH", "NYO", "OVR"]:
        v1m.append(GatedMTFInvert(
            f"A09_MTF_{wname}_atr2-6_bal200t20",
            window=WINDOWS[wname], atr_min=2.0, atr_max=6.0,
            require_aligned_balance=True, balance_n=200, balance_thresh=20))

    # Dist-from-VWAP gates
    for d_max in [3.0, 5.0, 10.0]:
        v1m.append(GatedMTFInvert(
            f"A10_MTF_vwap_max{int(d_max)}",
            dist_vwap_max=d_max))
    for d_min in [3.0, 5.0]:
        v1m.append(GatedMTFInvert(
            f"A11_MTF_vwap_min{int(d_min)}",
            dist_vwap_min=d_min))

    # Wider impulse / different params for MTF
    for imp in [4.0, 5.0, 6.0, 8.0]:
        for pp in [0.236, 0.382, 0.5]:
            for stop, tgt in [(5, 15), (5, 20), (8, 24)]:
                v1m.append(GatedMTFInvert(
                    f"A12_MTF_imp{int(imp)}_pp{int(pp*1000)}_s{stop}t{tgt}_atr2-6",
                    impulse_pts=imp, pull_pct=pp,
                    stop_pts=stop, target_pts=tgt,
                    atr_min=2.0, atr_max=6.0))

    # =================================================================
    # B. ML-style feature-gated CANON_INV_236
    # =================================================================
    v1m.append(MarketablePullback(
        "B00_CANON_baseline_INV_236_s10t20",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True))

    # ATR gates
    for atr_min, atr_max in [(2.0, None), (3.0, None), (None, 5.0),
                              (2.0, 6.0), (3.0, 8.0), (1.0, 4.0)]:
        tag = f"a{int(atr_min*10) if atr_min else 0}-{int(atr_max*10) if atr_max else 99}"
        v1m.append(GatedCanonPullback(
            f"B01_CANON_atr_{tag}",
            atr_min=atr_min, atr_max=atr_max))

    # Velocity gates
    for v_min in [2.0, 5.0, 10.0]:
        v1m.append(GatedCanonPullback(
            f"B02_CANON_velmin{int(v_min)}",
            velocity_min=v_min))
    for v_max in [3.0, 8.0]:
        v1m.append(GatedCanonPullback(
            f"B03_CANON_velmax{int(v_max)}",
            velocity_max=v_max))

    # Balance alignment
    for n, thr in [(200, 20), (300, 30), (500, 50)]:
        v1m.append(GatedCanonPullback(
            f"B04_CANON_bal_n{n}_t{thr}",
            balance_align=True, balance_n=n, balance_thresh=thr))

    # Time windows
    for wname, w in WINDOWS.items():
        v1m.append(GatedCanonPullback(
            f"B05_CANON_win{wname}",
            window=w))

    # Spread gates
    for ms in [0.5, 0.75]:
        v1m.append(GatedCanonPullback(
            f"B06_CANON_maxspread{int(ms*100)}",
            max_spread=ms))
    for st in [5, 10]:
        v1m.append(GatedCanonPullback(
            f"B07_CANON_tight{st}",
            spread_tight_min=st))

    # Combos: window + atr
    for wname in ["RTH", "NYO", "OVR"]:
        v1m.append(GatedCanonPullback(
            f"B08_CANON_{wname}_atr2-6",
            window=WINDOWS[wname], atr_min=2.0, atr_max=6.0))
        v1m.append(GatedCanonPullback(
            f"B09_CANON_{wname}_bal_n200t20",
            window=WINDOWS[wname],
            balance_align=True, balance_n=200, balance_thresh=20))

    # Triple combo
    for wname in ["RTH", "NYO"]:
        v1m.append(GatedCanonPullback(
            f"B10_CANON_{wname}_atr2-6_bal_n200t20",
            window=WINDOWS[wname], atr_min=2.0, atr_max=6.0,
            balance_align=True, balance_n=200, balance_thresh=20))

    # Alternative stop/target on CANON
    for stop, tgt in [(8, 16), (8, 24), (6, 18), (12, 24)]:
        v1m.append(GatedCanonPullback(
            f"B11_CANON_s{stop}t{tgt}_atr2-6",
            stop_pts=stop, target_pts=tgt,
            atr_min=2.0, atr_max=6.0))

    # =================================================================
    # C. Microstructure-aware variations
    # =================================================================
    for off in [0.5, 1.0, 1.5, 2.0]:
        v1m.append(OffTouchPullback(
            f"C01_OFFTOUCH_off{int(off*10)}_imp5_s10t20",
            offset_pts=off, impulse_pts=5.0, impulse_bars=4,
            pull_pct=0.236, stop_pts=10, target_pts=20, invert=True))
    # Off-touch with MTF
    for off in [0.5, 1.0]:
        # Reuse MTFConfluence but with patched on_bar_close for offset.
        ms = MTFConfluence(
            f"C02_MTF_OFFTOUCH_off{int(off*10)}",
            impulse_pts=6.0, impulse_bars=4, pull_pct=0.382,
            stop_pts=5, target_pts=20, invert=True)
        orig_obc = ms.on_bar_close
        _off = off

        def make_patched(_ms, _orig, _o):
            def patched(ts, hh, mn, bo, bh, bl, bc, hist):
                pre = len(_ms.pending)
                _orig(ts, hh, mn, bo, bh, bl, bc, hist)
                for s in _ms.pending[pre:]:
                    side = s['side']
                    if side == 'SHORT':
                        s['entry'] += _o
                        s['stop'] = s['entry'] + _ms.stop_pts
                        s['target'] = s['entry'] - _ms.target_pts
                    else:
                        s['entry'] -= _o
                        s['stop'] = s['entry'] - _ms.stop_pts
                        s['target'] = s['entry'] + _ms.target_pts
            return patched
        ms.on_bar_close = make_patched(ms, orig_obc, _off)
        v1m.append(ms)

    # Spread-compression gate combined with MTF
    for st_min in [3, 5, 10, 20]:
        v1m.append(GatedMTFInvert(
            f"C03_MTF_spreadgate{st_min}",
            spread_tight_min=st_min,
            impulse_pts=6.0, impulse_bars=4, pull_pct=0.382))

    # Early signal generation (3-bar impulse for MTF — earlier setup)
    for stop, tgt in [(5, 15), (5, 20), (8, 24)]:
        v1m.append(MTFConfluence(
            f"C04_MTF_early_imp4_b3_s{stop}t{tgt}_INV",
            impulse_pts=4.0, impulse_bars=3, pull_pct=0.382,
            stop_pts=stop, target_pts=tgt, invert=True))

    # =================================================================
    # D. NEW indicator strategies
    # =================================================================

    # D1: Choppiness
    for lk in [10, 14, 20]:
        for ci_min in [55, 60, 65]:
            for stop, tgt in [(4, 12), (5, 15)]:
                v1m.append(ChoppinessGatedFade(
                    f"D01_CHP_lk{lk}_ci{ci_min}_s{stop}t{tgt}",
                    lookback=lk, ci_min=ci_min,
                    stop_pts=stop, target_pts=tgt))

    # D2: DeMarker
    for lk in [10, 14, 20]:
        for hi, lo in [(0.7, 0.3), (0.75, 0.25), (0.8, 0.2)]:
            for stop, tgt in [(4, 12), (5, 15)]:
                v1m.append(DeMarker(
                    f"D02_DEM_lk{lk}_{int(hi*100)}_s{stop}t{tgt}",
                    lookback=lk, hi=hi, lo=lo,
                    stop_pts=stop, target_pts=tgt))

    # D3: CCI
    for lk in [14, 20]:
        for hi, lo in [(150, -150), (200, -200), (250, -250)]:
            for stop, tgt in [(4, 12), (5, 15)]:
                v1m.append(CCI(
                    f"D03_CCI_lk{lk}_h{hi}_s{stop}t{tgt}",
                    lookback=lk, hi=hi, lo=lo,
                    stop_pts=stop, target_pts=tgt))

    # D4: Williams %R
    for lk in [10, 14, 21]:
        for hi, lo in [(-20, -80), (-15, -85), (-10, -90)]:
            for fade in [True, False]:
                v1m.append(WilliamsR(
                    f"D04_WR_lk{lk}_h{hi}_{'fade' if fade else 'flw'}",
                    lookback=lk, hi=hi, lo=lo, fade=fade))

    # D5: Kaufman ER
    for lk in [10, 20, 40]:
        for er in [0.3, 0.5, 0.7]:
            for fade in [False, True]:
                v1m.append(KaufmanERGated(
                    f"D05_KER_lk{lk}_er{int(er*100)}_{'fade' if fade else 'flw'}",
                    lookback=lk, er_min=er, fade=fade))

    # D6: Aroon
    for lk in [10, 14, 25]:
        for fade in [True, False]:
            v1m.append(Aroon(
                f"D06_ARO_lk{lk}_{'fade' if fade else 'flw'}",
                lookback=lk, fade=fade))

    # D7: StochRSI
    for rsi_lk in [10, 14]:
        for stoch_lk in [10, 14]:
            for fade in [True, False]:
                v1m.append(StochRSI(
                    f"D07_SRSI_r{rsi_lk}_s{stoch_lk}_{'fade' if fade else 'flw'}",
                    rsi_lk=rsi_lk, stoch_lk=stoch_lk, fade=fade))

    # D8: Range filter
    for lk in [20, 30]:
        for k in [1.5, 2.0, 2.5]:
            for fade in [True, False]:
                v1m.append(RangeFilter(
                    f"D08_RF_lk{lk}_k{int(k*10)}_{'fade' if fade else 'flw'}",
                    lookback=lk, k=k, fade=fade))

    # D9: Hurst
    for lk in [32, 64, 96]:
        for ht, hr in [(0.55, 0.45), (0.6, 0.4)]:
            v1m.append(HurstGated(
                f"D09_HU_lk{lk}_{int(ht*100)}-{int(hr*100)}",
                lookback=lk, h_trend=ht, h_revert=hr))

    # D10: PSAR
    for af_st, af_mx in [(0.02, 0.2), (0.01, 0.1), (0.03, 0.3)]:
        for fade in [False, True]:
            v1m.append(PSARFlip(
                f"D10_PS_af{int(af_st*100)}-{int(af_mx*100)}_{'fade' if fade else 'flw'}",
                af_start=af_st, af_max=af_mx, fade=fade))

    # D11: TRIX
    for p, sp in [(9, 5), (15, 9), (21, 12)]:
        for fade in [False, True]:
            v1m.append(TRIX(
                f"D11_TRX_p{p}_sp{sp}_{'fade' if fade else 'flw'}",
                period=p, signal_p=sp, fade=fade))

    # D12: HA 3-bar
    for n in [2, 3]:
        for fade in [False, True]:
            for stop, tgt in [(4, 12), (5, 15)]:
                v1m.append(HA3Bar(
                    f"D12_HA{n}_{'fade' if fade else 'flw'}_s{stop}t{tgt}",
                    n=n, fade=fade, stop_pts=stop, target_pts=tgt))

    # D13: Force Index
    for lk in [10, 13, 21]:
        for z in [1.5, 2.0, 2.5]:
            for fade in [True, False]:
                v1m.append(ForceIndex(
                    f"D13_FI_lk{lk}_z{int(z*10)}_{'fade' if fade else 'flw'}",
                    lookback=lk, thresh_z=z, fade=fade))

    # D14: CMO
    for lk in [10, 14, 21]:
        for hi, lo in [(40, -40), (50, -50), (60, -60)]:
            for fade in [True, False]:
                v1m.append(CMO(
                    f"D14_CMO_lk{lk}_h{hi}_{'fade' if fade else 'flw'}",
                    lookback=lk, hi=hi, lo=lo, fade=fade))

    # D15: Entropy (tick-fed)
    for n in [50, 100, 200]:
        for h_max in [0.6, 0.7, 0.8]:
            for fade in [False, True]:
                vtick.append(EntropyGated(
                    f"D15_ENT_n{n}_h{int(h_max*10)}_{'fade' if fade else 'flw'}",
                    n_ticks=n, entropy_max=h_max, fade=fade))

    # D16: Ulcer gated MTF
    for ui_min, ui_max in [(None, 0.5), (None, 1.0), (0.3, None), (0.3, 1.5)]:
        tag = f"{int((ui_min or 0)*10)}-{int((ui_max or 100)*10)}"
        v1m.append(UlcerGatedMTF(
            f"D16_ULCER_MTF_{tag}",
            ui_min=ui_min, ui_max=ui_max,
            impulse_pts=6.0, impulse_bars=4, pull_pct=0.382,
            stop_pts=5, target_pts=20, invert=True))

    # =================================================================
    # E. Session intersections of CANON pullback
    # =================================================================
    for wname, w in WINDOWS.items():
        v1m.append(MarketablePullback(
            f"E01_CANON_{wname}_INV_236",
            impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
            stop_pts=10, target_pts=20, invert=True,
            session_start=w[0], session_end=w[1]))

    # CANON 0.382
    for wname, w in WINDOWS.items():
        v1m.append(MarketablePullback(
            f"E02_CANON_{wname}_INV_382_s5t20",
            impulse_pts=5.0, impulse_bars=4, pull_pct=0.382,
            stop_pts=5, target_pts=20, invert=True,
            session_start=w[0], session_end=w[1]))

    # MTF in windows directly via session_start/end on parent class
    for wname, w in WINDOWS.items():
        v1m.append(MTFConfluence(
            f"E03_MTF_{wname}_INV",
            impulse_pts=6.0, impulse_bars=4, pull_pct=0.382,
            stop_pts=5, target_pts=20, invert=True,
            session_start=w[0], session_end=w[1]))

    # =================================================================
    # SRR detector (aux — feeds MARKET, no trade output expected)
    # =================================================================
    srr_det = _SRRDetector()
    attach_r7_executor(srr_det)
    # Don't add to v1m so it doesn't trade; but we need it to receive bars
    aux = [srr_det]

    # Attach executor to all strategies
    n_total = 0
    for ls in [v1m, v15s, v30s, vtick]:
        for s in ls:
            attach_r7_executor(s)
            n_total += 1
    return v1m, v15s, v30s, vtick, aux, n_total


# =============================================================================
# Checkpoint
# =============================================================================
def save_checkpoint(ckpt_path, offset, day_counter, last_day_key, all_strats):
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
        "rng_state": _r7.RNG.getstate(),
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
        print(f"[round8] checkpoint load failed: {e!r}", file=sys.stderr)
        return None
    by_name = {s.name: s for s in all_strats}
    for name, v in state.get("variants", {}).items():
        s = by_name.get(name)
        if s is None:
            continue
        s.completed = list(v.get("completed", []))
        s.by_day = dict(v.get("by_day", {}))
        s.n_trades = int(v.get("n_trades", 0))
    try:
        _r7.RNG.setstate(state["rng_state"])
    except Exception:
        pass
    return (int(state["offset"]),
            int(state["day_counter"]),
            state["last_day_key"])


def _report(strat, total_days):
    return _r7._report(strat, total_days)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offset", type=int, default=DEFAULT_OFFSET)
    ap.add_argument("--ckpt-suffix", default="")
    ap.add_argument("--max-days", type=int, default=14)
    args = ap.parse_args()

    ckpt_path = ("/home/user/HFTBot/research/round8_checkpoint"
                 f"{args.ckpt_suffix}.pkl")
    csv_path = ("/home/user/HFTBot/research/round8_summary"
                f"{args.ckpt_suffix}.csv")
    md_path = ("/home/user/HFTBot/research/round8_results"
               f"{args.ckpt_suffix}.md")

    v1m, v15s, v30s, vtick, aux, n_total = build_variants_round8()
    all_strats = v1m + v15s + v30s + vtick
    # aux strategies receive bars but aren't reported
    all_runnable = all_strats + aux
    print(f"\n[round8] Built {len(all_strats)} reportable strategies "
          f"({len(v1m)} 1m + {len(v15s)} 15s + {len(v30s)} 30s + "
          f"{len(vtick)} tick) + {len(aux)} aux", file=sys.stderr)
    print(f"[round8] starting offset {args.offset:,}, ckpt={ckpt_path}",
          file=sys.stderr)

    resumed = load_checkpoint(ckpt_path, all_strats)
    if resumed is not None:
        start_offset, day_counter, last_day_key = resumed
        resumed_trades = sum(s.n_trades for s in all_strats)
        print(f"[round8] RESUMING from offset {start_offset:,} "
              f"day_counter={day_counter} ({resumed_trades:,} trades booked)",
              file=sys.stderr)
    else:
        start_offset = args.offset
        day_counter = -1
        last_day_key = None

    bb_1m = BarBuilder(granularity_secs=60, max_history=300)
    bb_15s = BarBuilder(granularity_secs=15, max_history=200)
    bb_30s = BarBuilder(granularity_secs=30, max_history=200)

    n_lines = 0
    t_start = time.time()
    last_progress_t = t_start
    last_progress_ticks = 0

    file_size = os.path.getsize(PATH)
    print(f"[round8] file size: {file_size:,} bytes", file=sys.stderr)

    max_day_counter = day_counter + args.max_days

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
                top_n = max((s.n_trades, s.name) for s in all_strats) if all_strats else (0, "?")
                try:
                    save_checkpoint(ckpt_path, pos, day_counter, last_day_key, all_strats)
                except Exception as e:
                    print(f"  [round8] ckpt save failed: {e!r}", file=sys.stderr)
                print(f"  [round8] {n_lines/1e6:.1f}M ticks rate={rate/1e6:.2f}M/s "
                      f"elapsed={(now-t_start)/60:.1f}m day={day_counter} "
                      f"most_trades={top_n[1]}({top_n[0]})",
                      file=sys.stderr, flush=True)
            try:
                line = raw.decode("ascii", errors="ignore")
                stamp_str, vals = line.split(";", 1)
                vp = vals.split(";")
                if len(vp) < 3:
                    continue
                last = float(vp[0])
                bid = float(vp[1])
                ask = float(vp[2])
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

            # Feed MARKET layer first (used by gated strategies)
            MARKET.feed_tick(ts, last, bid, ask)

            if bb_1m.on_tick(ts, last):
                closed = bb_1m.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    MARKET.feed_bar(o, h, l, c)
                    for s in v1m:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_1m.history)
                    for s in aux:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_1m.history)
            if v15s and bb_15s.on_tick(ts, last):
                closed = bb_15s.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    for s in v15s:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_15s.history)
            if v30s and bb_30s.on_tick(ts, last):
                closed = bb_30s.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    for s in v30s:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_30s.history)

            # Tick-fed strategies need every tick
            for s in vtick:
                s.feed_tick(ts, last)

            for s in all_runnable:
                r7_bot_on_tick(s, ts, bid, ask, day_counter, hh, mn, last)

    elapsed = time.time() - t_start
    total_days = day_counter + 1
    print(f"\n[round8] DONE in {elapsed/60:.1f}min, {n_lines:,} ticks, "
          f"{total_days} day buckets", file=sys.stderr)

    rows = [_report(s, total_days) for s in all_strats]
    rows.sort(key=lambda r: -r['per_day'])

    with open(csv_path, "w", newline="") as cf:
        w = csv.writer(cf)
        w.writerow(["name", "trades", "trades_per_day", "wr", "net",
                    "per_day", "per_trade", "max_dd", "worst_day",
                    "best_day", "sharpe", "n_days", "pos_d", "neg_d"])
        for r in rows:
            w.writerow([r['name'], r['n'], f"{r['trades_per_day']:.1f}",
                        f"{r['wr']:.4f}", f"{r['net']:.2f}",
                        f"{r['per_day']:.2f}", f"{r['per_trade']:.3f}",
                        f"{r['max_dd']:.2f}", f"{r['worst']:.2f}",
                        f"{r['best']:.2f}", f"{r['sharpe']:.3f}",
                        r['n_days'], r['pos_d'], r['neg_d']])
    print(f"[round8] wrote CSV {csv_path}", file=sys.stderr)

    full_pass = [r for r in rows if r['trades_per_day'] >= 300
                 and r['wr'] >= 0.45 and r['per_day'] >= 1000
                 and r['max_dd'] <= 5000]

    lines = []
    lines.append(f"# Round 8 strategy search results (offset={args.offset:,})\n\n")
    lines.append(f"Generated: {datetime.now().isoformat()}\n")
    lines.append(f"Period: {total_days} calendar-day buckets from offset "
                 f"{args.offset:,} (max-days={args.max_days})\n")
    lines.append(f"Tick stream: {n_lines:,} lines processed\n")
    lines.append(f"Strategies tested: {len(rows)}\n")
    lines.append(f"Costs applied: ${TOTAL_RT_COST:.2f}/RT, queue overshoot=1 tick "
                 f"(limit), marketable +1tick, stop-entry +1tick\n\n")
    lines.append("## Hard requirements\n")
    lines.append("- 300+ trades/day average\n")
    lines.append("- 45%+ win rate\n")
    lines.append("- $1000+ net daily P&L\n")
    lines.append("- Max DD <= $5000\n\n")

    lines.append(f"## Strategies meeting ALL hard requirements ({len(full_pass)})\n\n")
    if full_pass:
        for r in full_pass:
            lines.append(
                f"- **{r['name']}** -- {r['n']:,} trades "
                f"({r['trades_per_day']:.1f}/day), WR={r['wr']*100:.1f}%, "
                f"${r['per_day']:,.0f}/day, maxDD=${r['max_dd']:,.0f}, "
                f"Sharpe={r['sharpe']:.2f}\n")
    else:
        lines.append("**NONE**. See top-30 closest-candidates below.\n\n")

    lines.append("\n### Top 30 by $/day\n\n")
    lines.append("| Rank | Strategy | Trades | Tr/day | WR% | $/day | $/tr | maxDD | Sharpe |\n")
    lines.append("|------|----------|-------:|-------:|----:|------:|-----:|------:|-------:|\n")
    for i, r in enumerate(rows[:30], 1):
        lines.append(
            f"| {i} | {r['name']} | {r['n']:,} | {r['trades_per_day']:.1f} | "
            f"{r['wr']*100:.1f} | ${r['per_day']:,.0f} | "
            f"${r['per_trade']:.2f} | ${r['max_dd']:,.0f} | "
            f"{r['sharpe']:.2f} |\n")

    lines.append("\n### Closest candidates (min-ratio across constraints, n>=50)\n\n")
    scored = []
    for r in rows:
        if r['n'] < 50:
            continue
        score_vol = r['trades_per_day'] / 300
        score_wr = r['wr'] / 0.45
        score_pnl = r['per_day'] / 1000 if r['per_day'] > 0 else -1
        score_dd = 5000 / max(1.0, r['max_dd'])
        score = min(score_vol, score_wr, score_pnl, score_dd)
        binders = {'volume': score_vol, 'WR': score_wr,
                   'pnl': score_pnl, 'DD': score_dd}
        binder = min(binders, key=binders.get)
        scored.append((score, binder, r))
    scored.sort(key=lambda x: -x[0])
    for sc, binder, r in scored[:25]:
        lines.append(
            f"- **{r['name']}** -- min-ratio {sc:.2f} (binder: {binder}), "
            f"{r['trades_per_day']:.1f} tr/d, WR={r['wr']*100:.1f}%, "
            f"${r['per_day']:,.0f}/day, DD=${r['max_dd']:,.0f}\n")

    lines.append("\n## All strategies (sorted by $/day)\n\n")
    lines.append("| Strategy | Trades | Tr/day | WR% | Net $ | $/day | $/tr | maxDD | Worst d | Sharpe |\n")
    lines.append("|----------|-------:|-------:|----:|------:|------:|-----:|------:|--------:|-------:|\n")
    for r in rows:
        lines.append(
            f"| {r['name']} | {r['n']:,} | {r['trades_per_day']:.1f} | "
            f"{r['wr']*100:.1f} | ${r['net']:,.0f} | ${r['per_day']:,.0f} | "
            f"${r['per_trade']:.2f} | ${r['max_dd']:,.0f} | "
            f"${r['worst']:,.0f} | {r['sharpe']:.2f} |\n")

    with open(md_path, "w") as mf:
        mf.write("".join(lines))
    print(f"[round8] wrote MD {md_path}", file=sys.stderr)

    print("\n" + "=" * 110)
    print(f"{'Strategy':>40s} {'N':>7s} {'/day':>6s} {'WR%':>5s} "
          f"{'$/day':>9s} {'$/tr':>7s} {'maxDD':>9s} {'sharpe':>6s}")
    print("=" * 110)
    for r in rows[:30]:
        flag = ""
        if (r['trades_per_day'] >= 300 and r['wr'] >= 0.45
                and r['per_day'] >= 1000 and r['max_dd'] <= 5000):
            flag = " *PASS*"
        elif r['per_day'] >= 500:
            flag = "  $$"
        print(f"{r['name']:>40s} {r['n']:>7d} {r['trades_per_day']:>6.1f} "
              f"{r['wr']*100:>4.1f}% ${r['per_day']:>+8.0f} "
              f"${r['per_trade']:>+6.2f} ${r['max_dd']:>+8.0f} "
              f"{r['sharpe']:>+6.2f}{flag}")
    print(f"\nFULL_PASS strategies: {len(full_pass)}")

    try:
        if os.path.exists(ckpt_path):
            os.remove(ckpt_path)
            print(f"[round8] cleared checkpoint {ckpt_path}",
                  file=sys.stderr)
    except Exception:
        pass


if __name__ == "__main__":
    main()
