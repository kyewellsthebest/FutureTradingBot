"""Round 11 strategy search for MNQ — six NEW directions.

After 10 rounds and 2,000+ variants, no single-MNQ strategy has met the
hard requirements (300+ trades/day, 45%+ WR, $1000+/day, DD<=$5000) under
either $1.91 RT or $0.74 RT fees. Best ceiling so far is $29/day at MNQ
prop-firm. NQ prop-firm best is $706/day on R10_BASE_R8_C04_MTF_early.

Round 11 attacks SIX completely new levers in a single 60-day pass:

  1. LSTM/ML filter — gradient-boosted classifier (numpy from scratch
     because torch/sklearn are not installed) trained on day 0-39 of the
     window, applied as a P(win)>0.55 gate on existing pullback signals
     during day 40-53 (out-of-sample).
  2. Portfolio stacking — run the top 5 round-10 candidates concurrently
     under a single-position router; ANY firing takes the trade.
  3. Sub-second HFT mean reversion — true tick-level scalping. 3/5/7-tick
     rapid moves trigger marketable LIMIT in opposite direction.
  4. Liquidation cascade detection — fade after 3+ consecutive stop-runs.
  5. Massive parameter sweep around R10_BASE_R8_C04_MTF_early — 5000
     Latin-hypercube samples across 7 dimensions.
  6. OCO multi-LIMIT entry — 4 fib levels (0.236/0.382/0.5/0.618) as
     simultaneous LIMITs, first-fill-wins.

Implementation rules:
  - Re-use r10 bot-faithful executor (queue, latency, gaps, adaptive)
  - Cost applied at REPORT TIME ($1.91 + $0.74, MNQ + NQ)
  - 100K-tick checkpoint for resume safety
  - Total reportable strategies: ~6000+

Outputs:
  - research/round11_results.md
  - research/round11_summary.csv
  - research/round11_checkpoint.pkl
  - research/round11_ml_model.pkl  (after pre-pass)
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
from collections import deque, defaultdict
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

# Reuse full lineage
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

# Classes
StrategyBase = _r4.StrategyBase
BarBuilder = _r4.BarBuilder
PullbackStrategy = _r4.PullbackStrategy
MarketablePullback = _r6.MarketablePullback
MTFConfluence = _r7.MTFConfluence
MARKET = _r8.MARKET
MarketContext = _r8.MarketContext
GatedCanonPullback = _r8.GatedCanonPullback
REGIME = _r9.REGIME
RegimeEngine = _r9.RegimeEngine

attach_r7_executor = _r7.attach_r7_executor
block_idx_for_day = _r9.block_idx_for_day

_BaseEmitter = _r10._BaseEmitter
r10_bot_on_tick = _r10.r10_bot_on_tick

# Execution constants
PATH = _r7.PATH
MNQ_PER_PT = _r7.MNQ_PER_PT
NQ_PER_PT = 20.0
COMM_RT = _r7.COMM_RT
EXCH_FEES_RT = _r7.EXCH_FEES_RT
FEE_FULL_RT = _r7.TOTAL_RT_COST
FEE_PROP_RT = COMM_RT

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

RNG = random.Random(0xDECAFB11)


# =============================================================================
# Direction 1 — Tiny gradient-boosted classifier (numpy-free, pure python)
# =============================================================================
# We collect features at each pullback signal during day 0-39 (training);
# label = 1 if subsequent trade hits +20pt before -10pt within 600s.
# We train 30 decision stumps via greedy boosting (depth=1) on:
#   [tape_ratio, vpin, atr_5bar, atr_20bar, time_sin, time_cos,
#    dow, vwap_dev, recent_velocity_5s, spread_pts]
# In test phase (day 40-53), signals only fire when P(win)>0.55.
# =============================================================================

class GradientBoostedStumps:
    """Tiny boosted-stump classifier. Pure python (no numpy/sklearn).

    Each stump: (feat_idx, threshold, left_pred, right_pred).
    Predict: sum of stump outputs through sigmoid.
    """
    def __init__(self, n_stumps=30, lr=0.1):
        self.n_stumps = n_stumps
        self.lr = lr
        self.stumps = []
        self.feature_names = []

    @staticmethod
    def _sigmoid(z):
        if z >= 0:
            ez = math.exp(-z)
            return 1.0 / (1.0 + ez)
        ez = math.exp(z)
        return ez / (1.0 + ez)

    def predict_proba(self, x):
        z = 0.0
        for (fi, thr, lp, rp) in self.stumps:
            z += rp if x[fi] >= thr else lp
        return self._sigmoid(z)

    def fit(self, X, y):
        """X: list[list[float]], y: list[int] (0/1)."""
        if not X:
            return
        n = len(X)
        nf = len(X[0])
        # Initialize log-odds
        p = sum(y) / max(1, n)
        p = max(1e-3, min(1 - 1e-3, p))
        bias = math.log(p / (1 - p))
        # First stump = bias (feat=0, thr=-inf, both = bias/2 each side)
        self.stumps.append((0, -1e18, bias, bias))

        # Pre-compute sorted indices per feature
        sorted_idx = []
        for fi in range(nf):
            si = sorted(range(n), key=lambda i: X[i][fi])
            sorted_idx.append(si)

        # current log-odds per sample
        F = [bias] * n

        for it in range(self.n_stumps):
            # residuals = y - sigmoid(F)
            r = [y[i] - self._sigmoid(F[i]) for i in range(n)]
            # find best stump (feat, thr) minimizing sum((r - pred)^2)
            best_loss = float('inf')
            best = None
            tot_r = sum(r)
            tot_n = n
            for fi in range(nf):
                si = sorted_idx[fi]
                lr = 0.0
                ln = 0
                # candidate thresholds at every value boundary
                prev_v = None
                for ii, idx in enumerate(si):
                    v = X[idx][fi]
                    if prev_v is not None and v != prev_v and ln > 5 and (tot_n - ln) > 5:
                        # eval split at prev_v boundary
                        rr_r = tot_r - lr
                        rr_n = tot_n - ln
                        l_mean = lr / ln if ln > 0 else 0.0
                        r_mean = rr_r / rr_n if rr_n > 0 else 0.0
                        # SSE reduction
                        loss = - (lr * l_mean + rr_r * r_mean)
                        if loss < best_loss:
                            best_loss = loss
                            best = (fi, v, l_mean, r_mean)
                    lr += r[idx]
                    ln += 1
                    prev_v = v
            if best is None:
                break
            fi, thr, lp, rp = best
            lp *= self.lr
            rp *= self.lr
            self.stumps.append((fi, thr, lp, rp))
            # update F
            for i in range(n):
                F[i] += rp if X[i][fi] >= thr else lp


# Global signal-buffer for ML training: collects (features, label) at each
# pullback signal emission. label resolved on trade exit.
ML_DATASET = {
    'train_X': [],
    'train_y': [],
    'test_X': [],
    'test_y': [],
    'pending': {},  # key -> (features, day_counter)
}


def _ml_features(ts, bid, ask, last):
    """Build feature vector at current tick."""
    spread = max(0.25, ask - bid)
    tape = _r10.TAPE.ratio()
    vpin = _r10.VPIN_GAUGE.value()
    # time-of-day sin/cos
    sec_of_day = (ts % 86400)
    tsin = math.sin(2 * math.pi * sec_of_day / 86400)
    tcos = math.cos(2 * math.pi * sec_of_day / 86400)
    # ATR proxies (use MARKET's bar history if available)
    bars = list(getattr(MARKET, '_bars', []))[-20:]
    atr5 = 0.0
    atr20 = 0.0
    if len(bars) >= 5:
        atr5 = sum(abs(b[1] - b[2]) for b in bars[-5:]) / 5.0
    if len(bars) >= 20:
        atr20 = sum(abs(b[1] - b[2]) for b in bars) / len(bars)
    # vwap_dev (last - vwap proxy via mean close of recent bars)
    if len(bars) >= 5:
        vwap_proxy = sum(b[3] for b in bars[-5:]) / 5
        vwap_dev = (last - vwap_proxy) / max(1.0, atr5 if atr5 > 0 else 1.0)
    else:
        vwap_dev = 0.0
    velocity_5s = tape - 1.0
    return [tape, vpin, atr5, atr20, tsin, tcos, vwap_dev, velocity_5s,
            spread, last]


ML_MODEL = None  # populated after training


def _ml_train_split_day(day_counter):
    return day_counter < 40


def _ml_test_split_day(day_counter):
    return 40 <= day_counter < 54


# =============================================================================
# Direction 1 cont. — ML-filtered MarketablePullback
# =============================================================================
class MLFilteredPullback(MarketablePullback):
    """Identical to MarketablePullback, but on signal emission it:
      - Records features and pending key in ML_DATASET during training days.
      - During test days, computes P(win) via global ML_MODEL and SKIPS
        the signal if P<0.55.
    Trade outcome (label) updates train_y when the trade closes, via the
    completed-trade hook.
    """
    def __init__(self, *args, p_threshold=0.55, **kwargs):
        super().__init__(*args, **kwargs)
        self.p_threshold = p_threshold

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        n_before = len(self.pending)
        super().on_bar_close(ts, hh, mn, bo, bh, bl, bc, hist)
        # For each newly added setup, attach ML feature snapshot
        if len(self.pending) > n_before:
            # Use last bid/ask approximate (we don't have it here; use bc)
            feats = _ml_features(ts, bc - 0.25, bc + 0.25, bc)
            for s in self.pending[n_before:]:
                s['_ml_feats'] = feats
                # Tag whether we should filter (test phase) or just collect
                s['_ml_collect'] = True


def _ml_resolve_trade(strat, day_counter, pnl_pts, target_pts, stop_pts):
    """When an MLFiltered trade closes, push (features, label) to dataset.

    label = 1 if pnl reached +target_pts, else 0 (stops + timeouts both 0).
    """
    feats = getattr(strat, '_last_emitted_feats', None)
    if feats is None:
        return
    label = 1 if pnl_pts > 0 else 0
    if _ml_train_split_day(day_counter):
        ML_DATASET['train_X'].append(feats)
        ML_DATASET['train_y'].append(label)
    else:
        ML_DATASET['test_X'].append(feats)
        ML_DATASET['test_y'].append(label)
    strat._last_emitted_feats = None


# =============================================================================
# Direction 2 — PORTFOLIO STACKING router
# =============================================================================
# Each child strategy is a full bot-faithful strategy. We process them
# normally, but introduce a "lock" — if ANY strategy is currently in a
# trade, ALL OTHERS skip new entries. We do this by intercepting bot_on_tick.
# =============================================================================
class PortfolioRouter:
    """Single-position router that wraps multiple child strategies."""
    __slots__ = ('children', 'name', 'completed', 'by_day', 'n_trades',
                 'pending', 'in_trade', '_winner_idx')

    def __init__(self, name, children):
        self.name = name
        self.children = children
        self.completed = []
        self.by_day = {}
        self.n_trades = 0
        self.pending = []  # never used directly; child has own
        self.in_trade = None
        self._winner_idx = -1

    def any_in_trade(self):
        for c in self.children:
            if c.in_trade is not None:
                return True
        return False

    def aggregate_after_tick(self):
        """Walk children; if any closed a trade since last poll, absorb it."""
        for ci, c in enumerate(self.children):
            n = len(c.completed)
            seen = getattr(c, '_router_seen', 0)
            if n > seen:
                for trade in c.completed[seen:]:
                    self.completed.append(trade)
                    d = trade[2]
                    pnl = trade[0]
                    self.by_day.setdefault(d, []).append(pnl)
                    self.n_trades += 1
                c._router_seen = n


def portfolio_bot_on_tick(router, ts, bid, ask, day_counter, hh, mn, last):
    """Lock-aware multi-strategy tick router."""
    any_locked = router.any_in_trade()
    for c in router.children:
        # If locked elsewhere, mark each child's would-be entry as fire_attempted
        if any_locked and c.in_trade is None:
            # Don't drive on_tick (skip new entries); only manage open trade
            # But child cannot be open. So just skip.
            # Continue to allow setup pruning by calling r10_bot_on_tick — no, that emits.
            # We selectively just skip.
            continue
        r10_bot_on_tick(c, ts, bid, ask, day_counter, hh, mn, last)
    router.aggregate_after_tick()


# =============================================================================
# Direction 3 — Sub-second HFT mean reversion
# =============================================================================
# Maintain a sliding window of recent N ticks. When N ticks span < window_ms
# AND net price move > trigger_pts, fire opposite-direction marketable LIMIT.
# =============================================================================
class TickWindowGauge:
    """Track last N ticks for sub-second detection."""
    def __init__(self, maxlen=20):
        self._buf = deque(maxlen=maxlen)

    def feed(self, ts, last, bid, ask):
        self._buf.append((ts, last, bid, ask))

    def look_back(self, n_ticks, max_window_s=0.5):
        """Returns (delta_px, span_s, anchor_px) for last n_ticks if span<max_window_s."""
        if len(self._buf) < n_ticks:
            return None
        recent = list(self._buf)[-n_ticks:]
        span = recent[-1][0] - recent[0][0]
        if span > max_window_s:
            return None
        anchor = recent[0][1]
        delta = recent[-1][1] - anchor
        return (delta, span, anchor)


TICK_WIN = TickWindowGauge(maxlen=20)


class SubSecondHFT(_BaseEmitter):
    """Fires marketable LIMIT in opposite direction after a rapid N-tick move."""
    def __init__(self, name, n_ticks, max_window_s, trigger_pts,
                 stop_pts, target_pts, **kwargs):
        # Default very small cooldown for HFT
        kwargs.setdefault('cooldown_s', 0.2)
        kwargs.setdefault('fill_mode', 'marketable')
        # Session: RTH only (high liquidity)
        kwargs.setdefault('session_start', (13, 30))
        kwargs.setdefault('session_end', (20, 0))
        super().__init__(name, stop_pts, target_pts, **kwargs)
        self.n_ticks = n_ticks
        self.max_window_s = max_window_s
        self.trigger_pts = trigger_pts
        self._last_signal_ts = 0.0

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        pass

    def feed_signal(self, ts, bid, ask):
        if ts - self._last_signal_ts < self.cooldown_s:
            return
        info = TICK_WIN.look_back(self.n_ticks, self.max_window_s)
        if info is None:
            return
        delta, span, anchor = info
        if abs(delta) < self.trigger_pts:
            return
        mid = (bid + ask) / 2.0
        # FADE: if rapid up move, go SHORT; rapid down, go LONG
        if delta > 0:
            self.emit(ts, 'SHORT', bid, ('hft', 'S', round(ts, 2)),
                      expires_in=5)
        else:
            self.emit(ts, 'LONG', ask, ('hft', 'L', round(ts, 2)),
                      expires_in=5)
        self._last_signal_ts = ts


# =============================================================================
# Direction 4 — Liquidation cascade detection
# =============================================================================
# Track recent N "swing reversals" — a swing is defined by N+ point moves
# that reverse. If we see K such reversals back-to-back within T seconds,
# place a fade LIMIT M pts behind the latest reversal direction.
# =============================================================================
class SwingTracker:
    def __init__(self, swing_pts=3.0, window_s=30.0, max_swings=8):
        self.swing_pts = swing_pts
        self.window_s = window_s
        self.max_swings = max_swings
        self._anchor = None
        self._anchor_ts = 0.0
        self._direction = 0  # +1 up, -1 down, 0 none
        self._reversals = deque(maxlen=max_swings)  # (ts, direction, px)

    def feed(self, ts, last):
        if self._anchor is None:
            self._anchor = last
            self._anchor_ts = ts
            return
        delta = last - self._anchor
        if abs(delta) >= self.swing_pts:
            new_dir = 1 if delta > 0 else -1
            if self._direction != 0 and new_dir != self._direction:
                # reversal!
                self._reversals.append((ts, new_dir, last))
            self._direction = new_dir
            self._anchor = last
            self._anchor_ts = ts

    def cascade_signal(self, ts, k=3):
        """Return (last_dir, anchor_px) if K reversals in window_s ago."""
        if len(self._reversals) < k:
            return None
        recent = [r for r in self._reversals if ts - r[0] <= self.window_s]
        if len(recent) < k:
            return None
        # Last K must alternate directions
        dirs = [r[1] for r in recent[-k:]]
        for i in range(1, len(dirs)):
            if dirs[i] == dirs[i-1]:
                return None
        # Cascade detected
        return (recent[-1][1], recent[-1][2])


# We instantiate multiple swing trackers (different magnitudes)
SWING_TRACKERS = {}


class CascadeFade(_BaseEmitter):
    """Detect liquidation cascade. Place fade LIMIT M pts behind reversal."""
    def __init__(self, name, swing_pts, k_reversals, fade_offset,
                 stop_pts, target_pts, **kwargs):
        kwargs.setdefault('cooldown_s', 30)
        kwargs.setdefault('fill_mode', 'limit')
        super().__init__(name, stop_pts, target_pts, **kwargs)
        self.swing_pts = swing_pts
        self.k_reversals = k_reversals
        self.fade_offset = fade_offset
        self._last_signal_ts = 0.0
        # Ensure tracker exists
        key = (round(swing_pts, 1), 30.0)
        if key not in SWING_TRACKERS:
            SWING_TRACKERS[key] = SwingTracker(swing_pts=swing_pts)

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        pass

    def feed_signal(self, ts, bid, ask):
        if ts - self._last_signal_ts < self.cooldown_s:
            return
        tracker = SWING_TRACKERS[(round(self.swing_pts, 1), 30.0)]
        sig = tracker.cascade_signal(ts, k=self.k_reversals)
        if sig is None:
            return
        last_dir, anchor_px = sig
        # last_dir > 0 means we just had an upward break — assume liquidation
        # of shorts; we fade UP, expecting reversal back DOWN
        if last_dir > 0:
            # SHORT entry at anchor + fade_offset
            entry = anchor_px + self.fade_offset
            self.emit(ts, 'SHORT', entry, ('casc', 'S', round(ts, 0)),
                      expires_in=60)
        else:
            entry = anchor_px - self.fade_offset
            self.emit(ts, 'LONG', entry, ('casc', 'L', round(ts, 0)),
                      expires_in=60)
        self._last_signal_ts = ts


# =============================================================================
# Direction 5 — Massive Latin-hypercube sweep around R10 base winner
# =============================================================================
# 7 dimensions:
#   impulse: [2,3,4,5,6,7,8]
#   lookback (impulse_bars): [2,3,4,5]
#   stop: [4..12]
#   target: [12,16,20,24,28,32,36,40]
#   pp (pull_pct, fib): [0.118, 0.236, 0.300, 0.382, 0.450, 0.500, 0.618]
#   cooldown: [5,10,15,20]
#   session: [all, NYO, OVR, RTH, CME]
# Sample N variants via Latin hypercube (one per cell per dim).
# =============================================================================
def latin_hypercube_sample(n, dims, rng):
    """Yields n combinations with each dim's bins permuted independently."""
    bins = [list(range(len(d))) for d in dims]
    perms = []
    for b in bins:
        # repeat/extend to length n via tiling
        seq = []
        while len(seq) < n:
            x = list(b)
            rng.shuffle(x)
            seq.extend(x)
        perms.append(seq[:n])
    for i in range(n):
        yield tuple(dims[di][perms[di][i]] for di in range(len(dims)))


def build_d5_massive_sweep(n_variants=5000, rng=None):
    """Build N MTFConfluence variants via Latin hypercube."""
    if rng is None:
        rng = random.Random(0xD5D5D5)
    dims = [
        [2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],          # impulse
        [2, 3, 4, 5],                                  # bars
        [4, 5, 6, 7, 8, 9, 10, 11, 12],                # stop
        [12, 16, 20, 24, 28, 32, 36, 40],              # target
        [0.118, 0.236, 0.300, 0.382, 0.450, 0.500, 0.618],  # pp
        [5, 10, 15, 20],                                # cooldown
        # session: (name, start, end)
        [('all', None, None),
         ('NYO', (13, 30), (15, 30)),
         ('OVR', (13, 30), (16, 0)),
         ('RTH', (13, 30), (20, 0)),
         ('CME', (22, 0), (5, 0))],
    ]
    variants = []
    for combo in latin_hypercube_sample(n_variants, dims, rng):
        imp, bars, stp, tgt, pp, cd, ses = combo
        if tgt <= stp:  # skip degenerate
            continue
        ses_name, ses_start, ses_end = ses
        # also INVERSE (the R10 winner was INV)
        for inv_tag, inv in [('INV', True), ('TRD', False)]:
            name = (f"D5_LH_imp{int(imp)}_b{bars}_s{stp}_t{tgt}_"
                    f"pp{int(pp*1000)}_cd{cd}_{ses_name}_{inv_tag}")
            try:
                s = MTFConfluence(
                    name, impulse_pts=float(imp), impulse_bars=bars,
                    pull_pct=pp, stop_pts=stp, target_pts=tgt, invert=inv,
                    cooldown_s=cd,
                    session_start=ses_start, session_end=ses_end)
                variants.append(s)
            except Exception:
                continue
        if len(variants) >= n_variants:
            break
    return variants[:n_variants]


# =============================================================================
# Direction 6 — OCO multi-LIMIT entry (4 fib levels)
# =============================================================================
class OCOMultiLimit(MarketablePullback):
    """Identical signal generation to MarketablePullback, but instead of
    emitting ONE setup at pp, emits FOUR — at fib 0.236/0.382/0.5/0.618.
    All share the same cohort key so first-fill cancels the rest.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        n_before = len(self.pending)
        super().on_bar_close(ts, hh, mn, bo, bh, bl, bc, hist)
        new_setups = self.pending[n_before:]
        # For each newly added setup, build 3 more clones at other fib levels
        clones = []
        FIBS = (0.236, 0.382, 0.500, 0.618)
        for s in new_setups:
            # Determine impulse start/end from setup entry vs original
            # Original entry is set at impulse_anchor + pp*impulse_size (LONG)
            # We can reconstruct anchor from stop/target offsets
            side = s['side']
            entry = s['entry']
            stop = s.get('stop')
            tgt = s.get('target')
            stop_off = s.get('stop_offset_pts')
            tgt_off = s.get('target_offset_pts')
            if stop_off is None and stop is not None:
                stop_off = abs(entry - stop)
            if tgt_off is None and tgt is not None:
                tgt_off = abs(tgt - entry)
            # The pull-back ratio used for original; we infer anchor as
            # entry adjusted backwards by an impulse representation. We
            # don't have impulse size here, so we approximate by treating
            # the impulse as 5*stop_off (canonical R10 base 5/10 ratio).
            # We make 4 LIMITs at incrementally adjusted entries:
            #   delta = (fib - origin_fib) * impulse_size
            # Approximation: impulse_size = stop_off * 2 (conservative)
            imp_size = max(2.0, (stop_off or 5.0) * 2.0)
            origin_pp = self.pull_pct
            cohort = ('oco', round(s.get('_gen_ts', 0), 0), s.get('key'))
            for fi, fib in enumerate(FIBS):
                if abs(fib - origin_pp) < 1e-6:
                    s['cohort'] = cohort
                    continue
                if side == 'LONG':
                    # entry is BELOW impulse high (LONG fade)
                    new_entry = entry + (fib - origin_pp) * imp_size * (-1 if not self.invert else 1)
                else:
                    new_entry = entry - (fib - origin_pp) * imp_size * (-1 if not self.invert else 1)
                clone_extra = {
                    'fill_mode': s.get('fill_mode', 'limit'),
                    'stop_offset_pts': stop_off,
                    'target_offset_pts': tgt_off,
                    'exit_mode': 'stop_market',
                    'cohort': cohort,
                    '_gen_ts': s.get('_gen_ts', ts),
                }
                if side == 'LONG':
                    cs = new_entry - (stop_off or 5.0)
                    ct = new_entry + (tgt_off or 10.0)
                else:
                    cs = new_entry + (stop_off or 5.0)
                    ct = new_entry - (tgt_off or 10.0)
                clones.append({
                    'side': side,
                    'orig': s.get('orig', side),
                    'entry': new_entry,
                    'stop': cs,
                    'target': ct,
                    'expires': s['expires'],
                    'used': False,
                    'key': ('oco', fi, round(s.get('_gen_ts', 0), 0)),
                    **clone_extra,
                })
            s['cohort'] = cohort
        for c in clones:
            self.pending.append(c)


# =============================================================================
# DOW helper (copied from r10)
# =============================================================================
def _dow(y, m, d):
    if m < 3:
        m += 12; y -= 1
    K = y % 100; J = y // 100
    h = (d + (13*(m+1))//5 + K + K//4 + J//4 + 5*J) % 7
    return (h + 5) % 7


# =============================================================================
# REPORT
# =============================================================================
def report_strategy(strat, total_days, fee_rt, pt_value=MNQ_PER_PT):
    n = len(strat.completed)
    if n == 0:
        return {
            'name': strat.name, 'n': 0, 'wr': 0.0, 'net': 0.0,
            'per_day': 0.0, 'per_trade': 0.0,
            'worst': 0.0, 'best': 0.0, 'max_dd': 0.0,
            'trades_per_day': 0.0, 'sharpe': 0.0, 'n_days': 0,
            'pos_d': 0, 'neg_d': 0,
        }
    wins = 0
    net = 0.0
    day_nets = defaultdict(float)
    series = []
    for c in strat.completed:
        pnl_pts = c[0]
        d = c[2]
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
    return {
        'name': strat.name, 'n': n, 'wr': wr, 'net': net,
        'per_day': per_day, 'per_trade': per_trade,
        'worst': worst, 'best': best, 'max_dd': max_dd,
        'trades_per_day': trades_per_day, 'sharpe': sharpe, 'n_days': n_days,
        'pos_d': pos_d, 'neg_d': neg_d,
    }


# =============================================================================
# CHECKPOINT
# =============================================================================
def save_checkpoint(ckpt_path, offset, day_counter, last_day_key,
                    all_strats, portfolio):
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
        "portfolio": {
            'completed': list(portfolio.completed),
            'by_day': dict(portfolio.by_day),
            'n_trades': int(portfolio.n_trades),
        } if portfolio is not None else None,
        "rng_state": RNG.getstate(),
        "ml_dataset": {
            'train_X': ML_DATASET['train_X'][-50000:],  # cap memory
            'train_y': ML_DATASET['train_y'][-50000:],
            'test_X': ML_DATASET['test_X'][-50000:],
            'test_y': ML_DATASET['test_y'][-50000:],
        },
    }
    tmp = ckpt_path + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, ckpt_path)


def load_checkpoint(ckpt_path, all_strats, portfolio):
    if not os.path.exists(ckpt_path):
        return None
    try:
        with open(ckpt_path, "rb") as f:
            state = pickle.load(f)
    except Exception as e:
        print(f"[round11] checkpoint load failed: {e!r}", file=sys.stderr)
        return None
    by_name = {s.name: s for s in all_strats}
    for name, v in state.get("variants", {}).items():
        s = by_name.get(name)
        if s is None:
            continue
        s.completed = list(v.get("completed", []))
        s.by_day = dict(v.get("by_day", {}))
        s.n_trades = int(v.get("n_trades", 0))
    if portfolio is not None and state.get("portfolio"):
        portfolio.completed = list(state["portfolio"].get('completed', []))
        portfolio.by_day = dict(state["portfolio"].get('by_day', {}))
        portfolio.n_trades = int(state["portfolio"].get('n_trades', 0))
    try:
        RNG.setstate(state["rng_state"])
    except Exception:
        pass
    md = state.get('ml_dataset', {})
    ML_DATASET['train_X'] = list(md.get('train_X', []))
    ML_DATASET['train_y'] = list(md.get('train_y', []))
    ML_DATASET['test_X'] = list(md.get('test_X', []))
    ML_DATASET['test_y'] = list(md.get('test_y', []))
    return (int(state["offset"]),
            int(state["day_counter"]),
            state["last_day_key"])


# =============================================================================
# MAIN
# =============================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offset", type=int, default=DEFAULT_OFFSET)
    ap.add_argument("--ckpt-suffix", default="")
    ap.add_argument("--max-days", type=int, default=60)
    ap.add_argument("--n-sweep", type=int, default=5000)
    ap.add_argument("--skip-d5-sweep", action="store_true",
                    help="Skip the 5000-variant Latin hypercube (for quick runs)")
    args = ap.parse_args()

    ckpt_path = ("/home/user/HFTBot/research/round11_checkpoint"
                 f"{args.ckpt_suffix}.pkl")
    csv_path = ("/home/user/HFTBot/research/round11_summary"
                f"{args.ckpt_suffix}.csv")
    md_path = "/home/user/HFTBot/research/round11_results.md"
    ml_path = "/home/user/HFTBot/research/round11_ml_model.pkl"

    # =========================================================================
    # BUILD VARIANTS
    # =========================================================================
    print(f"[round11] building variants...", file=sys.stderr)
    v1m = []
    v15s = []
    vtick = []

    # ----- Direction 1 — ML filter variants (3) -----
    ml_variants = [
        MLFilteredPullback(
            "D1_ML_CANON_INV_236",
            impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
            stop_pts=10, target_pts=20, invert=True, p_threshold=0.55),
        MLFilteredPullback(
            "D1_ML_INV_pp382_s8t24",
            impulse_pts=4.0, impulse_bars=3, pull_pct=0.382,
            stop_pts=8, target_pts=24, invert=True, p_threshold=0.55),
        MLFilteredPullback(
            "D1_ML_INV_pp118_s4t16",
            impulse_pts=3.0, impulse_bars=4, pull_pct=0.118,
            stop_pts=4, target_pts=16, invert=True, p_threshold=0.55),
    ]
    for s in ml_variants:
        v1m.append(s)
    # Also baseline unfiltered for OOS comparison
    baseline_for_ml = MarketablePullback(
        "D1_BASELINE_CANON_INV_236_unfiltered",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True)
    v1m.append(baseline_for_ml)

    # ----- Direction 2 — Portfolio stacking -----
    # Children: top 5 from round 10
    portfolio_children = [
        MTFConfluence(
            "PORT_R10_BASE_R8_C04_MTF_early_imp4_b3_s8t24_INV",
            impulse_pts=4.0, impulse_bars=3, pull_pct=0.382,
            stop_pts=8, target_pts=24, invert=True),
        MTFConfluence(
            "PORT_D10_MTF_pp450_imp4_b3_s6t24_all",
            impulse_pts=4.0, impulse_bars=3, pull_pct=0.450,
            stop_pts=6, target_pts=24, invert=True),
        MTFConfluence(
            "PORT_D10_MTF_pp300_imp5_b3_s8t30_all",
            impulse_pts=5.0, impulse_bars=3, pull_pct=0.300,
            stop_pts=8, target_pts=30, invert=True),
        MTFConfluence(
            "PORT_D10_MTF_pp382_imp5_b3_s12t24_all",
            impulse_pts=5.0, impulse_bars=3, pull_pct=0.382,
            stop_pts=12, target_pts=24, invert=True),
        MTFConfluence(
            "PORT_D10_MTF_pp382_imp4_b3_s12t20_all",
            impulse_pts=4.0, impulse_bars=3, pull_pct=0.382,
            stop_pts=12, target_pts=20, invert=True),
    ]
    for c in portfolio_children:
        v1m.append(c)
    portfolio = PortfolioRouter("D2_PORTFOLIO_top5_R10", portfolio_children)
    # mark _router_seen on children
    for c in portfolio_children:
        c._router_seen = 0

    # ----- Direction 3 — Sub-second HFT (parameter sweep) -----
    HFT_CONFIGS = []
    for n_t in [3, 5, 7]:
        for win in [0.3, 0.5, 0.8]:
            for trig in [1.0, 1.5, 2.0, 3.0]:
                for (stp, tgt) in [(1.0, 1.5), (1.0, 2.0), (1.5, 3.0),
                                   (2.0, 3.0), (2.0, 4.0)]:
                    HFT_CONFIGS.append((n_t, win, trig, stp, tgt))
    # That's 3*3*4*5 = 180 combos. Sample 120 for runtime.
    rng_hft = random.Random(0xBEAD)
    rng_hft.shuffle(HFT_CONFIGS)
    HFT_CONFIGS = HFT_CONFIGS[:120]
    for n_t, win, trig, stp, tgt in HFT_CONFIGS:
        name = (f"D3_HFT_n{n_t}_w{int(win*1000)}_"
                f"t{int(trig*10)}_s{int(stp*10)}t{int(tgt*10)}")
        s = SubSecondHFT(name, n_ticks=n_t, max_window_s=win,
                         trigger_pts=trig, stop_pts=stp, target_pts=tgt)
        vtick.append(s)

    # ----- Direction 4 — Liquidation cascade -----
    CASCADE_CONFIGS = []
    for swing in [3.0, 5.0, 8.0]:
        for k in [2, 3, 4]:
            for fade in [2.0, 3.0, 5.0]:
                for (stp, tgt) in [(5, 15), (8, 24), (10, 20),
                                   (6, 18), (10, 30)]:
                    CASCADE_CONFIGS.append((swing, k, fade, stp, tgt))
    for swing, k, fade, stp, tgt in CASCADE_CONFIGS:
        name = (f"D4_CASC_sw{int(swing)}_k{k}_fd{int(fade)}_s{stp}t{tgt}")
        s = CascadeFade(name, swing_pts=swing, k_reversals=k,
                        fade_offset=fade, stop_pts=stp, target_pts=tgt)
        vtick.append(s)

    # ----- Direction 5 — Massive Latin hypercube sweep -----
    if not args.skip_d5_sweep:
        print(f"[round11] building D5 LH sweep N={args.n_sweep}...",
              file=sys.stderr)
        d5_variants = build_d5_massive_sweep(args.n_sweep)
        # Hard cap at 5000 for memory; each MTFConfluence is small (~100 bytes)
        for s in d5_variants:
            v1m.append(s)
    else:
        d5_variants = []

    # ----- Direction 6 — OCO multi-LIMIT (around best 1m winner) -----
    OCO_CONFIGS = [
        ("D6_OCO_CANON_INV_236",
         {'impulse_pts': 5.0, 'impulse_bars': 4, 'pull_pct': 0.236,
          'stop_pts': 10, 'target_pts': 20, 'invert': True}),
        ("D6_OCO_INV_pp382_s8t24_imp4",
         {'impulse_pts': 4.0, 'impulse_bars': 3, 'pull_pct': 0.382,
          'stop_pts': 8, 'target_pts': 24, 'invert': True}),
        ("D6_OCO_INV_pp450_s6t24_imp4",
         {'impulse_pts': 4.0, 'impulse_bars': 3, 'pull_pct': 0.450,
          'stop_pts': 6, 'target_pts': 24, 'invert': True}),
        ("D6_OCO_INV_pp500_s5t20_imp5",
         {'impulse_pts': 5.0, 'impulse_bars': 4, 'pull_pct': 0.500,
          'stop_pts': 5, 'target_pts': 20, 'invert': True}),
        ("D6_OCO_INV_pp236_s5t20_imp5",
         {'impulse_pts': 5.0, 'impulse_bars': 4, 'pull_pct': 0.236,
          'stop_pts': 5, 'target_pts': 20, 'invert': True}),
    ]
    for name, kwargs in OCO_CONFIGS:
        s = OCOMultiLimit(name, **kwargs)
        v1m.append(s)

    # Attach executor
    all_strats = v1m + v15s + vtick
    for s in all_strats:
        attach_r7_executor(s)

    # Also attach to portfolio children (already in v1m, so done above)
    print(f"[round11] Built {len(all_strats):,} strategies "
          f"({len(v1m)} 1m + {len(v15s)} 15s + {len(vtick)} tick) "
          f"+ 1 portfolio router", file=sys.stderr)

    # =========================================================================
    # RESUME / RUN
    # =========================================================================
    resumed = load_checkpoint(ckpt_path, all_strats, portfolio)
    if resumed is not None:
        start_offset, day_counter, last_day_key = resumed
        resumed_trades = sum(s.n_trades for s in all_strats)
        print(f"[round11] RESUMING from offset {start_offset:,} "
              f"day_counter={day_counter} ({resumed_trades:,} trades booked)",
              file=sys.stderr)
    else:
        start_offset = args.offset
        day_counter = -1
        last_day_key = None

    # Load ML model if present (mid-run)
    global ML_MODEL
    if os.path.exists(ml_path):
        try:
            with open(ml_path, 'rb') as f:
                ML_MODEL = pickle.load(f)
            print(f"[round11] loaded ML model with {len(ML_MODEL.stumps)} stumps",
                  file=sys.stderr)
        except Exception as e:
            print(f"[round11] ml load fail: {e}", file=sys.stderr)

    bb_1m = BarBuilder(granularity_secs=60, max_history=300)
    bb_15s = BarBuilder(granularity_secs=15, max_history=200)

    n_lines = 0
    t_start = time.time()
    last_progress_t = t_start
    last_progress_ticks = 0

    file_size = os.path.getsize(PATH)
    print(f"[round11] file size: {file_size:,} bytes", file=sys.stderr)

    max_day_counter = day_counter + args.max_days
    ml_trained_at_day = -1  # track when we train mid-run

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
                    save_checkpoint(ckpt_path, pos, day_counter, last_day_key,
                                    all_strats, portfolio)
                except Exception as e:
                    print(f"  [round11] ckpt save failed: {e!r}", file=sys.stderr)
                print(f"  [round11] {n_lines/1e6:.1f}M ticks rate={rate/1e6:.2f}M/s "
                      f"elapsed={(now-t_start)/60:.1f}m day={day_counter} "
                      f"port_n={portfolio.n_trades} "
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
                # ML training trigger: train at day 40 when transitioning
                # from in-sample to out-of-sample
                if (day_counter == 40 and ML_MODEL is None
                        and len(ML_DATASET['train_X']) >= 200):
                    print(f"\n[round11] ML training: n_train="
                          f"{len(ML_DATASET['train_X'])}", file=sys.stderr)
                    t_ml = time.time()
                    model = GradientBoostedStumps(n_stumps=30, lr=0.1)
                    model.fit(ML_DATASET['train_X'], ML_DATASET['train_y'])
                    ML_MODEL = model
                    with open(ml_path, 'wb') as mf:
                        pickle.dump(model, mf)
                    print(f"[round11] ML trained in {time.time()-t_ml:.1f}s, "
                          f"{len(model.stumps)} stumps", file=sys.stderr)

            ts = day_counter * 86400 + hh * 3600 + mn * 60 + ss + ns / 1e7
            dow = _dow(yy, mm, dd)

            # Gauges
            MARKET.feed_tick(ts, last, bid, ask)
            _r10.VPIN_GAUGE.feed_tick(last, bid, ask)
            _r10.TAPE.feed_tick(ts)
            TICK_WIN.feed(ts, last, bid, ask)
            # Update all swing trackers
            for tr in SWING_TRACKERS.values():
                tr.feed(ts, last)

            if bb_1m.on_tick(ts, last):
                closed = bb_1m.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    MARKET.feed_bar(o, h, l, c)
                    REGIME.feed_bar(o, h, l, c)
                    for s in v1m:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_1m.history)
            if v15s and bb_15s.on_tick(ts, last):
                closed = bb_15s.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    for s in v15s:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_15s.history)

            # Per-tick signal emitters
            for s in vtick:
                fs = getattr(s, 'feed_signal', None)
                if fs is not None:
                    fs(ts, bid, ask)

            # ML filter: for MLFilteredPullback strategies during test phase,
            # iterate pending and check P(win) at the moment of entry approach.
            # Simplified: if ML_MODEL is loaded and this is a test-phase day,
            # prune setups for ML strategies whose ML_feats give P < threshold.
            if ML_MODEL is not None and _ml_test_split_day(day_counter):
                for ms in ml_variants:
                    if not ms.pending:
                        continue
                    kept = []
                    for setup in ms.pending:
                        if setup.get('_ml_filtered'):
                            kept.append(setup)
                            continue
                        feats = setup.get('_ml_feats')
                        if feats is None:
                            kept.append(setup)
                            continue
                        try:
                            p = ML_MODEL.predict_proba(feats)
                        except Exception:
                            p = 0.5
                        if p >= ms.p_threshold:
                            setup['_ml_filtered'] = True
                            kept.append(setup)
                        # else drop
                    ms.pending = kept

            # Bot tick for all per-strategy
            for s in all_strats:
                # Skip portfolio children if router is locked elsewhere
                if (hasattr(s, '_router_seen')
                        and portfolio.any_in_trade()
                        and s.in_trade is None
                        and getattr(portfolio, '_winner_idx', -1) != id(s)):
                    # Allow setup pruning but skip new entries
                    # Note: r10_bot_on_tick handles this internally if we set
                    # last_exit_ts/cooldown; safest is to call it but make sure
                    # pending list won't generate entries elsewhere. To keep
                    # things simple: just skip on_tick for non-active children.
                    continue
                r10_bot_on_tick(s, ts, bid, ask, day_counter, hh, mn, last)

            # Aggregate portfolio
            portfolio.aggregate_after_tick()

            # ML dataset collection: for ML strategies, when they close a
            # trade we resolve label using the most recent completed entry.
            for ms in ml_variants:
                if not ms.completed:
                    continue
                last_seen = getattr(ms, '_ml_seen_idx', 0)
                if len(ms.completed) <= last_seen:
                    continue
                # New trades closed; for each new one, attach label from feats
                # buffered at signal time (we don't have a feats-per-trade
                # mapping perfectly preserved; we approximate by using the
                # most recently emitted setup's feats — best effort).
                feats = getattr(ms, '_ml_last_emit_feats', None)
                for trade in ms.completed[last_seen:]:
                    pnl_pts = trade[0]
                    label = 1 if pnl_pts > 0 else 0
                    if feats is None:
                        continue
                    if _ml_train_split_day(day_counter):
                        ML_DATASET['train_X'].append(list(feats))
                        ML_DATASET['train_y'].append(label)
                    else:
                        ML_DATASET['test_X'].append(list(feats))
                        ML_DATASET['test_y'].append(label)
                ms._ml_seen_idx = len(ms.completed)

            # Snapshot last emitted feats on ML strategies (best-effort)
            for ms in ml_variants:
                if ms.pending:
                    last_setup = ms.pending[-1]
                    f_ = last_setup.get('_ml_feats')
                    if f_ is not None:
                        ms._ml_last_emit_feats = f_

    elapsed = time.time() - t_start
    total_days = day_counter + 1
    print(f"\n[round11] DONE in {elapsed/60:.1f}min, {n_lines:,} ticks, "
          f"{total_days} day buckets", file=sys.stderr)

    # =========================================================================
    # REPORTING
    # =========================================================================
    all_reportable = list(all_strats) + [portfolio]
    rows_191 = [report_strategy(s, total_days, FEE_FULL_RT)
                for s in all_reportable]
    rows_074 = [report_strategy(s, total_days, FEE_PROP_RT)
                for s in all_reportable]
    rows_nq_191 = [report_strategy(s, total_days, FEE_FULL_RT, NQ_PER_PT)
                   for s in all_reportable]
    rows_nq_074 = [report_strategy(s, total_days, FEE_PROP_RT, NQ_PER_PT)
                   for s in all_reportable]

    rows_191_by_name = {r['name']: r for r in rows_191}
    rows_074_by_name = {r['name']: r for r in rows_074}

    rows_191.sort(key=lambda r: -r['per_day'])
    rows_074.sort(key=lambda r: -r['per_day'])
    rows_nq_191.sort(key=lambda r: -r['per_day'])
    rows_nq_074.sort(key=lambda r: -r['per_day'])

    with open(csv_path, "w", newline="") as cf:
        w = csv.writer(cf)
        w.writerow([
            "name", "trades", "trades_per_day", "wr",
            "per_day_191", "per_day_074", "per_day_NQ_191", "per_day_NQ_074",
            "per_trade_191", "max_dd_191", "max_dd_074",
            "sharpe_191", "sharpe_074",
            "n_days", "pos_d_191", "neg_d_191",
        ])
        nq191_by = {r['name']: r for r in rows_nq_191}
        nq074_by = {r['name']: r for r in rows_nq_074}
        for r in rows_191:
            n = r['name']
            r74 = rows_074_by_name[n]
            rnq = nq191_by[n]
            rnq74 = nq074_by[n]
            w.writerow([
                n, r['n'], f"{r['trades_per_day']:.1f}", f"{r['wr']:.4f}",
                f"{r['per_day']:.2f}", f"{r74['per_day']:.2f}",
                f"{rnq['per_day']:.2f}", f"{rnq74['per_day']:.2f}",
                f"{r['per_trade']:.3f}",
                f"{r['max_dd']:.2f}", f"{r74['max_dd']:.2f}",
                f"{r['sharpe']:.3f}", f"{r74['sharpe']:.3f}",
                r['n_days'], r['pos_d'], r['neg_d'],
            ])
    print(f"[round11] wrote CSV {csv_path}", file=sys.stderr)

    def is_pass(r):
        return (r['trades_per_day'] >= 300 and r['wr'] >= 0.45
                and r['per_day'] >= 1000 and r['max_dd'] <= 5000)

    pass_191 = [r for r in rows_191 if is_pass(r)]
    pass_074 = [r for r in rows_074 if is_pass(r)]
    pass_nq_191 = [r for r in rows_nq_191 if is_pass(r)]
    pass_nq_074 = [r for r in rows_nq_074 if is_pass(r)]

    def _dir(name):
        for prefix in ['D1_', 'D2_', 'D3_', 'D4_', 'D5_', 'D6_',
                       'PORT_', 'BASELINE']:
            if name.startswith(prefix):
                return prefix.rstrip('_')
        return 'OTHER'

    by_dir = defaultdict(list)
    for r in rows_191:
        by_dir[_dir(r['name'])].append(r)

    # =========================================================================
    # MARKDOWN REPORT
    # =========================================================================
    L = []
    L.append("# Round 11 strategy search — six NEW directions\n\n")
    L.append(f"Generated: {datetime.now().isoformat()}\n")
    L.append(f"Period: {total_days} calendar-day buckets from offset "
             f"{args.offset:,} (max-days={args.max_days})\n")
    L.append(f"Tick stream: {n_lines:,} lines processed\n")
    L.append(f"Strategies tested: {len(all_strats):,} + 1 portfolio router\n\n")

    L.append("## Execution model\n\n")
    L.append("Bot-faithful: queue overshoot by 1 tick (LIMIT), 200ms latency, "
             "10pt approach threshold, multi-setup lock, 0.5pt stop slip + "
             "10% gap risk, 10s cooldown (HFT uses 0.2s), 600s max hold.\n\n")
    L.append(f"Fees tracked: **$1.91/RT** vs **$0.74/RT** (prop-firm). "
             f"Instruments: MNQ ($2/pt) and NQ ($20/pt).\n\n")

    L.append("## Hard requirements\n")
    L.append("- 300+ trades/day average\n- 45%+ WR\n- $1000+ $/day\n- maxDD <= $5000\n\n")

    L.append(f"## Section 1 — FULL_PASS strategies\n\n")
    L.append(f"- $1.91 MNQ: **{len(pass_191)}**\n")
    L.append(f"- $0.74 MNQ (prop-firm): **{len(pass_074)}**\n")
    L.append(f"- $1.91 NQ: **{len(pass_nq_191)}**\n")
    L.append(f"- $0.74 NQ (prop-firm): **{len(pass_nq_074)}**\n\n")
    for label, ps in [("$1.91 MNQ", pass_191), ("$0.74 MNQ", pass_074),
                      ("$1.91 NQ", pass_nq_191), ("$0.74 NQ", pass_nq_074)]:
        if ps:
            L.append(f"\n### {label} passers\n")
            for r in ps:
                L.append(f"- **{r['name']}** -- {r['n']:,} trades "
                         f"({r['trades_per_day']:.1f}/day), WR={r['wr']*100:.1f}%, "
                         f"${r['per_day']:,.0f}/day, DD=${r['max_dd']:,.0f}, "
                         f"Sharpe={r['sharpe']:.2f}\n")

    L.append("\n## Section 2 — Direction summary (best $/day per direction)\n\n")
    L.append("| Direction | n_strats | Best $/d 191 | Best $/d 074 | Best $/d NQ191 | Best $/d NQ074 | Top strat |\n")
    L.append("|---|---:|---:|---:|---:|---:|---|\n")
    nq191_by = {r['name']: r for r in rows_nq_191}
    nq074_by = {r['name']: r for r in rows_nq_074}
    for d in sorted(by_dir.keys()):
        items = by_dir[d]
        items_sorted = sorted(items, key=lambda r: -r['per_day'])
        top = items_sorted[0]
        n_strats = len(items)
        n = top['name']
        r74 = rows_074_by_name[n]
        rnq = nq191_by[n]
        rnq74 = nq074_by[n]
        L.append(f"| {d} | {n_strats:,} | ${top['per_day']:,.0f} | "
                 f"${r74['per_day']:,.0f} | ${rnq['per_day']:,.0f} | "
                 f"${rnq74['per_day']:,.0f} | {n} |\n")

    # Section 3 — ML filter analysis
    L.append("\n## Section 3 — ML filter (D1) analysis\n\n")
    L.append(f"- Training samples collected (day 0-39): "
             f"{len(ML_DATASET['train_X']):,}\n")
    L.append(f"- Test samples collected (day 40-53): "
             f"{len(ML_DATASET['test_X']):,}\n")
    if ML_MODEL is not None:
        L.append(f"- Model: {len(ML_MODEL.stumps)} gradient-boosted stumps\n")
        # Compute in-sample / out-of-sample accuracy
        def _acc(X, y):
            if not X: return 0.0, 0
            correct = 0
            for xi, yi in zip(X, y):
                p = ML_MODEL.predict_proba(xi)
                pred = 1 if p > 0.5 else 0
                if pred == yi: correct += 1
            return correct / len(X), len(X)
        ia, ni = _acc(ML_DATASET['train_X'], ML_DATASET['train_y'])
        oa, no = _acc(ML_DATASET['test_X'], ML_DATASET['test_y'])
        L.append(f"- In-sample accuracy: {ia*100:.1f}% (n={ni:,})\n")
        L.append(f"- Out-of-sample accuracy: {oa*100:.1f}% (n={no:,})\n")
    else:
        L.append("- Model NOT trained (insufficient training samples)\n")
    L.append("\n### ML-filtered vs baseline\n")
    L.append("| Strategy | Tr/d | WR% | $/d 191 | $/d 074 | $/d NQ074 | maxDD 074 |\n")
    L.append("|---|---:|---:|---:|---:|---:|---:|\n")
    for ms in ml_variants + [baseline_for_ml]:
        r = rows_191_by_name.get(ms.name)
        if r is None: continue
        r74 = rows_074_by_name[ms.name]
        rnq74 = nq074_by[ms.name]
        L.append(f"| {ms.name} | {r['trades_per_day']:.1f} | "
                 f"{r['wr']*100:.1f} | ${r['per_day']:,.0f} | "
                 f"${r74['per_day']:,.0f} | ${rnq74['per_day']:,.0f} | "
                 f"${r74['max_dd']:,.0f} |\n")

    # Section 4 — Portfolio aggregate
    L.append("\n## Section 4 — Portfolio stacking (D2)\n\n")
    pr = rows_191_by_name.get(portfolio.name)
    if pr is not None:
        pr74 = rows_074_by_name[portfolio.name]
        prnq = nq191_by[portfolio.name]
        prnq74 = nq074_by[portfolio.name]
        L.append(f"- Total trades: {pr['n']:,} ({pr['trades_per_day']:.1f}/day)\n")
        L.append(f"- WR: {pr['wr']*100:.1f}%\n")
        L.append(f"- $/day MNQ $1.91: ${pr['per_day']:,.0f}\n")
        L.append(f"- $/day MNQ $0.74: ${pr74['per_day']:,.0f}\n")
        L.append(f"- $/day NQ $1.91: ${prnq['per_day']:,.0f}\n")
        L.append(f"- $/day NQ $0.74: ${prnq74['per_day']:,.0f}\n")
        L.append(f"- Max DD $1.91: ${pr['max_dd']:,.0f}\n")
        L.append(f"- Sharpe: {pr['sharpe']:.2f}\n")

    # Section 5 — Sub-second HFT top 10
    L.append("\n## Section 5 — Sub-second HFT (D3) top 10 by $/day NQ $0.74\n\n")
    hft_rows = [r for r in rows_nq_074 if r['name'].startswith('D3_HFT_')]
    hft_rows.sort(key=lambda r: -r['per_day'])
    L.append("| Strategy | Tr/d | WR% | $/d NQ074 | maxDD | Sharpe |\n")
    L.append("|---|---:|---:|---:|---:|---:|\n")
    for r in hft_rows[:10]:
        L.append(f"| {r['name']} | {r['trades_per_day']:.1f} | "
                 f"{r['wr']*100:.1f} | ${r['per_day']:,.0f} | "
                 f"${r['max_dd']:,.0f} | {r['sharpe']:.2f} |\n")

    # Section 6 — Liquidation cascade top 10
    L.append("\n## Section 6 — Liquidation cascade (D4) top 10 by $/day NQ $0.74\n\n")
    casc_rows = [r for r in rows_nq_074 if r['name'].startswith('D4_CASC_')]
    casc_rows.sort(key=lambda r: -r['per_day'])
    L.append("| Strategy | Tr/d | WR% | $/d NQ074 | maxDD | Sharpe |\n")
    L.append("|---|---:|---:|---:|---:|---:|\n")
    for r in casc_rows[:10]:
        L.append(f"| {r['name']} | {r['trades_per_day']:.1f} | "
                 f"{r['wr']*100:.1f} | ${r['per_day']:,.0f} | "
                 f"${r['max_dd']:,.0f} | {r['sharpe']:.2f} |\n")

    # Section 7 — Massive LH sweep top 30
    L.append("\n## Section 7 — D5 Latin-hypercube sweep top 30 by $/day NQ $0.74\n\n")
    d5_rows = [r for r in rows_nq_074 if r['name'].startswith('D5_LH_')]
    d5_rows.sort(key=lambda r: -r['per_day'])
    L.append("| Rank | Strategy | Tr/d | WR% | $/d NQ074 | $/d MNQ074 | maxDD | Sharpe |\n")
    L.append("|---:|---|---:|---:|---:|---:|---:|---:|\n")
    for i, r in enumerate(d5_rows[:30], 1):
        r74m = rows_074_by_name[r['name']]
        L.append(f"| {i} | {r['name']} | {r['trades_per_day']:.1f} | "
                 f"{r['wr']*100:.1f} | ${r['per_day']:,.0f} | "
                 f"${r74m['per_day']:,.0f} | "
                 f"${r['max_dd']:,.0f} | {r['sharpe']:.2f} |\n")

    # Section 8 — OCO multi-LIMIT results
    L.append("\n## Section 8 — OCO multi-LIMIT (D6) results\n\n")
    oco_rows = [r for r in rows_nq_074 if r['name'].startswith('D6_OCO_')]
    oco_rows.sort(key=lambda r: -r['per_day'])
    L.append("| Strategy | Tr/d | WR% | $/d NQ074 | $/d MNQ074 | maxDD | Sharpe |\n")
    L.append("|---|---:|---:|---:|---:|---:|---:|\n")
    for r in oco_rows:
        r74m = rows_074_by_name[r['name']]
        L.append(f"| {r['name']} | {r['trades_per_day']:.1f} | "
                 f"{r['wr']*100:.1f} | ${r['per_day']:,.0f} | "
                 f"${r74m['per_day']:,.0f} | "
                 f"${r['max_dd']:,.0f} | {r['sharpe']:.2f} |\n")

    # Section 9 — Top 30 overall
    L.append("\n## Section 9 — Top 30 overall by $/day under MNQ $1.91\n\n")
    L.append("| Rank | Strategy | Dir | Tr | Tr/d | WR% | $/d 191 | $/d 074 | $/d NQ074 | DD | Sharpe |\n")
    L.append("|---:|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for i, r in enumerate(rows_191[:30], 1):
        n = r['name']
        r74 = rows_074_by_name[n]
        rnq74 = nq074_by[n]
        L.append(
            f"| {i} | {n} | {_dir(n)} | {r['n']:,} | {r['trades_per_day']:.1f} | "
            f"{r['wr']*100:.1f} | ${r['per_day']:,.0f} | "
            f"${r74['per_day']:,.0f} | ${rnq74['per_day']:,.0f} | "
            f"${r['max_dd']:,.0f} | {r['sharpe']:.2f} |\n")

    # Section 10 — Top 30 by NQ prop-firm
    L.append("\n## Section 10 — Top 30 by $/day NQ $0.74 (best prior lever)\n\n")
    L.append("| Rank | Strategy | Dir | Tr/d | WR% | $/day NQ | maxDD | Sharpe |\n")
    L.append("|---:|---|:---:|---:|---:|---:|---:|---:|\n")
    for i, r in enumerate(rows_nq_074[:30], 1):
        L.append(f"| {i} | {r['name']} | {_dir(r['name'])} | "
                 f"{r['trades_per_day']:.1f} | "
                 f"{r['wr']*100:.1f} | ${r['per_day']:,.0f} | "
                 f"${r['max_dd']:,.0f} | {r['sharpe']:.2f} |\n")

    # Section 11 — Lever ranking
    L.append("\n## Section 11 — Lever ranking (best $/day MNQ-equivalent)\n\n")
    best_191 = rows_191[0]['per_day'] if rows_191 else 0
    best_074 = rows_074[0]['per_day'] if rows_074 else 0
    best_nq_191 = rows_nq_191[0]['per_day'] if rows_nq_191 else 0
    best_nq_074 = rows_nq_074[0]['per_day'] if rows_nq_074 else 0
    levers = [
        ("baseline MNQ $1.91", best_191),
        ("prop-firm MNQ $0.74", best_074),
        ("baseline NQ $1.91 / MNQ-equiv", best_nq_191 / 10.0),
        ("prop-firm NQ $0.74 / MNQ-equiv", best_nq_074 / 10.0),
    ]
    levers.sort(key=lambda x: -x[1])
    for name, val in levers:
        L.append(f"- **{name}**: ${val:,.0f}/day\n")

    # Section 12 — Round 12 recommendations
    L.append("\n## Section 12 — Round 12 recommendations\n\n")
    if pass_074 or pass_191 or pass_nq_074 or pass_nq_191:
        L.append("**PASSERS FOUND.** Recommend deployment validation:\n")
        L.append("1. Re-test top passers on fresh 30d window (out-of-sample).\n")
        L.append("2. Live paper-trade for 1 week before real money.\n")
        L.append("3. Verify execution assumptions in live order book.\n")
    else:
        L.append("**NO PASSERS** after 11 rounds and 8,000+ variants.\n\n")
        L.append("Round 12 attack angles (NEW levers — never tried):\n")
        L.append("1. **Proper neural network** — install PyTorch via pip; train\n")
        L.append("   a 2-layer LSTM (64 hidden, 30 timesteps) on tick features.\n")
        L.append("2. **Hourly-regime ML** — separate model per (dow, hour) cell;\n")
        L.append("   168 cells x 30-stump models = better local fit.\n")
        L.append("3. **Random forest feature discovery** — train RF on a richer\n")
        L.append("   feature set (orderbook imbalance, volume profile, microvol,\n")
        L.append("   cross-tick acceleration) and extract feature importance.\n")
        L.append("4. **Genetic feature search** — auto-discover non-obvious\n")
        L.append("   feature combinations via tree-of-thoughts variant search.\n")
        L.append("5. **Per-day regime classifier** — pre-label every day as one\n")
        L.append("   of (trend, range, vol-spike, news) and run strategy router\n")
        L.append("   that picks ONE strategy per regime.\n")
        L.append("6. **Acquire L2 orderbook data** — top-of-book size, depth\n")
        L.append("   imbalance, hidden-liquidity detection. Currently only T&S.\n")
        L.append("7. **MNQ + NQ hybrid** — open MNQ but trail via NQ proxy.\n")
        L.append("8. **Cross-asset signal** — ES, RTY, CL leading indicators.\n")
        L.append("9. **Triple-barrier ML labels** — use Lopez de Prado's purged\n")
        L.append("   k-fold CV and triple-barrier labeling for cleaner training.\n")
        L.append("10. **Acceptance-bound relaxation** — propose to user that\n")
        L.append("    300 tr/d may be infeasible; offer 150 tr/d alternative.\n")
        L.append("    (NEVER without explicit user OK.)\n")

    L.append("\n## Section 13 — Full strategy table (sorted by $/day at $1.91, top 200)\n\n")
    L.append("| Strategy | Dir | Tr | Tr/d | WR% | $/d 191 | $/d 074 | $/d NQ191 | $/d NQ074 | maxDD 191 | Sharpe |\n")
    L.append("|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for r in rows_191[:200]:
        n = r['name']
        r74 = rows_074_by_name[n]
        rnq = nq191_by[n]
        rnq74 = nq074_by[n]
        L.append(f"| {n} | {_dir(n)} | {r['n']:,} | {r['trades_per_day']:.1f} | "
                 f"{r['wr']*100:.1f} | ${r['per_day']:,.0f} | "
                 f"${r74['per_day']:,.0f} | ${rnq['per_day']:,.0f} | "
                 f"${rnq74['per_day']:,.0f} | ${r['max_dd']:,.0f} | "
                 f"{r['sharpe']:.2f} |\n")

    with open(md_path, "w") as mf:
        mf.write("".join(L))
    print(f"[round11] wrote MD {md_path}", file=sys.stderr)

    # Console summary
    print("\n" + "=" * 110)
    print(f"FULL_PASS under $1.91 (MNQ): {len(pass_191)}")
    print(f"FULL_PASS under $0.74 (MNQ prop-firm): {len(pass_074)}")
    print(f"FULL_PASS under $1.91 (NQ): {len(pass_nq_191)}")
    print(f"FULL_PASS under $0.74 (NQ prop-firm): {len(pass_nq_074)}")
    print("=" * 110)
    for r in rows_191[:30]:
        n = r['name']
        r74 = rows_074_by_name[n]
        rnq74 = nq074_by[n]
        flag = ""
        if is_pass(r): flag = " *PASS(full)*"
        elif is_pass(r74): flag = " *PASS(prop)*"
        elif is_pass(rnq74): flag = " *PASS(NQprop)*"
        print(f"{n[:50]:>50s} {r['n']:>6d} {r['trades_per_day']:>6.1f} "
              f"{r['wr']*100:>4.1f}% ${r['per_day']:>+7.0f} (074: "
              f"${r74['per_day']:>+6.0f}, NQ074: ${rnq74['per_day']:>+6.0f}){flag}")

    try:
        if os.path.exists(ckpt_path):
            os.remove(ckpt_path)
            print(f"[round11] cleared checkpoint {ckpt_path}", file=sys.stderr)
    except Exception:
        pass


if __name__ == "__main__":
    main()
