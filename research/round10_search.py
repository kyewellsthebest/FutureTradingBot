"""Round 10 strategy search for MNQ — RELENTLESS ten-direction battery.

After 9 rounds and 1,700+ variants, no strategy survives bot-faithful
execution at 1 MNQ + $1.91 fees with 300+ trades/day, 45%+ WR, $1000+/day,
DD<=$5000. Round 9 found prop-firm NQ at $61/day per contract as the
absolute ceiling under any prior lever.

Round 10 attacks from TEN DIRECTIONS simultaneously, in a single 60-day
pass over the tick stream (with two pre-passes for RL and GA):

  1. RL Q-learning agent (separate pre-pass; produces a frozen Q-table)
  2. Genetic algorithm parameter evolution (separate pre-pass on 7d)
  3. Pattern motif discovery — sequence-cluster centroids as signal source
  4. VPIN-gated entries — only fire pullback signals when VPIN<0.3
  5. Microstructure absorption signal (consecutive trades at one side)
  6. Speed-of-tape straddle (tick-rate jump triggers ±3pt LIMIT pair)
  7. Cyclical (day-of-week × hour) calendar grid
  8. Ensemble voting (3-of-5 round-4 winners agree at same tick)
  9. Adaptive queue position model (LIMITs in book longer fill better)
 10. Tight parameter sweep around best NQ + prop-firm result

Implementation rules:
  - Re-use the r7/r8 bot-faithful executor (queue, latency, gaps)
  - Adaptive queue model (Direction 9) is an opt-in flag per strategy
  - Cost applied at REPORT TIME so $1.91 and $0.74 both derive from one trace
  - 100K-tick checkpoint for resume safety
  - The full battery: ~190 strategies. At ~60min/90 strats from round 9
    we estimate ~2 hours wall-clock for the main pass.

Outputs:
  - research/round10_results.md
  - research/round10_summary.csv
  - research/round10_checkpoint.pkl
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
STALE_FILL_PROB = _r7.STALE_FILL_PROB
TICK = _r7.TICK
MARKETABLE_SLIP_PT = _r7.MARKETABLE_SLIP_PT
STOP_ENTRY_SLIP_PT = _r7.STOP_ENTRY_SLIP_PT
STOP_LIMIT_OFFSET_PT = _r7.STOP_LIMIT_OFFSET_PT
STOP_LIMIT_NONFILL_PROB = _r7.STOP_LIMIT_NONFILL_PROB

DEFAULT_OFFSET = 7_820_974_790
CHECKPOINT_EVERY_TICKS = 100_000

BLOCK_BOUNDS = [(0, 14), (15, 29), (30, 44), (45, 60)]
N_BLOCKS = len(BLOCK_BOUNDS)

RNG = random.Random(0xDECAFB10)


# =============================================================================
# ADAPTIVE QUEUE MODEL (Direction 9)
# =============================================================================
# Tracks per-strategy when each LIMIT setup first got placed at price.
# Probability of fill on touch grows with time-in-book:
#   age >  60s: 80%
#   30s< age <60s: 60%
#   5s < age <30s: 30%
#   age <  5s: 10%
# When a LIMIT fires under the adaptive model, we draw a random number;
# if it falls under the fill probability we consider the order filled.
# Otherwise treat as a "missed" fill (the order keeps living until the
# next touch — or until it expires).
#
# To avoid major refactor we attach the adaptive model state to the
# executor and intercept fill_mode='limit' fills inside the per-tick
# routine below.

ADAPTIVE_AGE_BANDS = [
    (60.0, 0.80),
    (30.0, 0.60),
    (5.0, 0.30),
    (0.0, 0.10),
]


def _adaptive_fill_prob(age_s):
    for thr, p in ADAPTIVE_AGE_BANDS:
        if age_s >= thr:
            return p
    return 0.10


# =============================================================================
# VPIN computation (Direction 4)
# =============================================================================
class VPINGauge:
    """Volume-Synchronized Probability of Informed Trading.

    Bulk-volume-classification (BVC) approximation: each tick adds |delta|
    to total volume, classified as BUY if last>=mid else SELL. We bucket
    into N=50 fixed-volume bins (size = adaptive). VPIN = avg over last
    50 bins of |B-S|/(B+S).
    """
    def __init__(self, bin_volume=200.0, n_bins=50):
        self.bin_volume = bin_volume
        self.n_bins = n_bins
        self._cur_buy = 0.0
        self._cur_sell = 0.0
        self._cur_total = 0.0
        self._buf = deque(maxlen=n_bins)
        self._last_px = None
        self._vpin = 0.0

    def feed_tick(self, last, bid, ask):
        mid = (bid + ask) / 2.0
        if self._last_px is None:
            self._last_px = last
            return
        delta = abs(last - self._last_px)
        if delta == 0:
            delta = 0.25
        if last >= mid:
            self._cur_buy += delta
        else:
            self._cur_sell += delta
        self._cur_total += delta
        self._last_px = last
        if self._cur_total >= self.bin_volume:
            tot = self._cur_buy + self._cur_sell
            if tot > 0:
                self._buf.append(abs(self._cur_buy - self._cur_sell) / tot)
            self._cur_buy = 0.0
            self._cur_sell = 0.0
            self._cur_total = 0.0
            if len(self._buf) > 0:
                self._vpin = sum(self._buf) / len(self._buf)

    def value(self):
        return self._vpin


VPIN_GAUGE = VPINGauge()


# =============================================================================
# TAPE SPEED gauge (Direction 6)
# =============================================================================
class TapeSpeedGauge:
    """Tracks tick-rate over short window (5s) vs baseline (60s)."""
    def __init__(self):
        self._short = deque()  # (ts,) entries within last 5s
        self._long = deque()
        self._last_ts = 0.0
        self._ratio = 1.0
        self._short_rate = 0.0
        self._long_rate = 0.0

    def feed_tick(self, ts):
        self._short.append(ts)
        self._long.append(ts)
        # prune
        while self._short and ts - self._short[0] > 5.0:
            self._short.popleft()
        while self._long and ts - self._long[0] > 60.0:
            self._long.popleft()
        self._short_rate = len(self._short) / 5.0
        self._long_rate = len(self._long) / 60.0
        if self._long_rate > 0.5:
            self._ratio = self._short_rate / self._long_rate
        else:
            self._ratio = 1.0
        self._last_ts = ts

    def ratio(self):
        return self._ratio


TAPE = TapeSpeedGauge()


# =============================================================================
# ABSORPTION signal gauge (Direction 5)
# =============================================================================
class AbsorptionGauge:
    """Track consecutive trades at ASK or BID without price moving > 0.5pt."""
    def __init__(self):
        self._anchor = None
        self._side = None
        self._count_buy = 0
        self._count_sell = 0
        self._last_px = None

    def feed_tick(self, last, bid, ask):
        mid = (bid + ask) / 2.0
        if last >= mid:
            # buy-side
            if self._side == 'BUY' and self._anchor is not None and abs(last - self._anchor) <= 0.5:
                self._count_buy += 1
            else:
                self._anchor = last
                self._side = 'BUY'
                self._count_buy = 1
                self._count_sell = 0
        else:
            if self._side == 'SELL' and self._anchor is not None and abs(last - self._anchor) <= 0.5:
                self._count_sell += 1
            else:
                self._anchor = last
                self._side = 'SELL'
                self._count_sell = 1
                self._count_buy = 0
        # Anchor drift reset
        if self._anchor is not None and abs(last - self._anchor) > 0.5:
            self._anchor = last
            self._side = 'BUY' if last >= mid else 'SELL'
            self._count_buy = 1 if self._side == 'BUY' else 0
            self._count_sell = 1 if self._side == 'SELL' else 0
        self._last_px = last

    def buy_streak(self):
        return self._count_buy

    def sell_streak(self):
        return self._count_sell


ABS_GAUGE = AbsorptionGauge()


# =============================================================================
# CALENDAR grid gauge (Direction 7)
# =============================================================================
# We track historical (day-of-week, hour) -> mean 60min returns observed
# so far. Pre-pass: no offline history; we instead build it in-pass and
# use a "warm-up" period so the early days don't fire. After 20d the
# grid becomes the signal source. This is honest in-sample observation.
class CalendarGrid:
    def __init__(self, warmup_days=20):
        self.warmup_days = warmup_days
        # (dow, hr) -> list of 60min returns at start of (dow,hr)
        self._buf = defaultdict(list)
        self._cur_cell = None
        self._cell_start_px = None
        self._cell_start_ts = None
        self.bias = {}  # (dow, hr) -> (mean, n)

    def feed_tick(self, ts, last, day_counter, hh, dow):
        cell = (dow, hh)
        if self._cur_cell is None or cell != self._cur_cell:
            # close previous cell
            if (self._cur_cell is not None and self._cell_start_px is not None
                    and ts - self._cell_start_ts >= 1800.0):
                ret = last - self._cell_start_px
                self._buf[self._cur_cell].append(ret)
                # update bias
                arr = self._buf[self._cur_cell]
                mu = sum(arr) / len(arr)
                self.bias[self._cur_cell] = (mu, len(arr))
            self._cur_cell = cell
            self._cell_start_px = last
            self._cell_start_ts = ts

    def signal(self, dow, hh, day_counter):
        """Returns 'LONG', 'SHORT', or None based on stored bias."""
        if day_counter < self.warmup_days:
            return None
        info = self.bias.get((dow, hh))
        if info is None:
            return None
        mu, n = info
        if n < 8:
            return None
        # p<0.05 proxy: mu/sigma sqrt(n) >= 1.96. We don't have sigma — use
        # threshold |mu| >= 3pt as proxy and require n>=8 samples.
        if abs(mu) < 3.0:
            return None
        return 'LONG' if mu > 0 else 'SHORT'


CAL_GRID = CalendarGrid(warmup_days=15)


# =============================================================================
# NEW STRATEGY CLASSES
# =============================================================================

class _BaseEmitter(StrategyBase):
    """Helper for strategies that emit setups from a custom signal."""
    def __init__(self, name, stop_pts, target_pts,
                 cooldown_s=10, max_hold=MAX_HOLD_S,
                 session_start=None, session_end=None,
                 fill_mode='marketable',
                 adaptive_queue=False):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.stop_pts = stop_pts
        self.target_pts = target_pts
        self.fill_mode = fill_mode
        self.adaptive_queue = adaptive_queue

    def emit(self, ts, side, entry, key, expires_in=300):
        extra = {
            'fill_mode': self.fill_mode,
            'stop_offset_pts': self.stop_pts,
            'target_offset_pts': self.target_pts,
            'exit_mode': 'stop_market',
            '_gen_ts': ts,
        }
        if self.adaptive_queue:
            extra['_adaptive'] = True
        if side == "LONG":
            stop = entry - self.stop_pts
            target = entry + self.target_pts
        else:
            stop = entry + self.stop_pts
            target = entry - self.target_pts
        self.add_setup(side, side, entry, stop, target, ts,
                       key=key, expires_in=expires_in, extra=extra)


# =============================================================================
# VPIN-gated MarketablePullback (Direction 4)
# =============================================================================
class VPINGatedPullback(MarketablePullback):
    """Round-4 idealized winner ONLY fires when VPIN < threshold."""
    def __init__(self, *args, vpin_max=0.3, **kwargs):
        super().__init__(*args, **kwargs)
        self.vpin_max = vpin_max

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if VPIN_GAUGE.value() > self.vpin_max:
            return
        super().on_bar_close(ts, hh, mn, bo, bh, bl, bc, hist)


class VPINHighFadePullback(MarketablePullback):
    """Inverse: when VPIN > 0.7 we INVERT the inversion (=trend-follow)."""
    def __init__(self, *args, vpin_min=0.7, **kwargs):
        super().__init__(*args, **kwargs)
        self.vpin_min = vpin_min

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if VPIN_GAUGE.value() < self.vpin_min:
            return
        # Flip invert just for this signal
        was = self.invert
        self.invert = not was
        try:
            super().on_bar_close(ts, hh, mn, bo, bh, bl, bc, hist)
        finally:
            self.invert = was


# =============================================================================
# Absorption strategy (Direction 5)
# =============================================================================
class AbsorptionStrategy(_BaseEmitter):
    def __init__(self, name, threshold, stop_pts, target_pts,
                 invert=False, **kwargs):
        super().__init__(name, stop_pts, target_pts, **kwargs)
        self.threshold = threshold
        self.invert = invert
        self._last_signal_ts = 0.0

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        pass

    def feed_signal(self, ts, bid, ask):
        if ts - self._last_signal_ts < 2.0:
            return
        b = ABS_GAUGE.buy_streak()
        s = ABS_GAUGE.sell_streak()
        if b >= self.threshold:
            side = 'SHORT' if self.invert else 'LONG'
            self.emit(ts, side, ask if side == 'LONG' else bid,
                      ('abs', 'L', round(ts, 0)))
            self._last_signal_ts = ts
        elif s >= self.threshold:
            side = 'LONG' if self.invert else 'SHORT'
            self.emit(ts, side, ask if side == 'LONG' else bid,
                      ('abs', 'S', round(ts, 0)))
            self._last_signal_ts = ts


# =============================================================================
# Tape-speed straddle (Direction 6)
# =============================================================================
class TapeStraddleStrategy(_BaseEmitter):
    """When tape speed jumps Nx baseline, place LONG-STOP at +offset
    and SHORT-STOP at -offset from current. OCO via cohort."""
    def __init__(self, name, multiplier, offset_pts,
                 stop_pts, target_pts, **kwargs):
        super().__init__(name, stop_pts, target_pts, **kwargs)
        self.multiplier = multiplier
        self.offset_pts = offset_pts
        self._last_signal_ts = 0.0
        self.fill_mode = 'stop'

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        pass

    def feed_signal(self, ts, bid, ask):
        if ts - self._last_signal_ts < 30.0:
            return
        if TAPE.ratio() < self.multiplier:
            return
        mid = (bid + ask) / 2.0
        cohort = ('tape', round(ts, 0))
        # LONG STOP
        e_l = mid + self.offset_pts
        extra_l = {
            'fill_mode': 'stop',
            'stop_offset_pts': self.stop_pts,
            'target_offset_pts': self.target_pts,
            'exit_mode': 'stop_market',
            'cohort': cohort,
            '_gen_ts': ts,
        }
        self.add_setup('LONG', 'LONG', e_l, e_l - self.stop_pts,
                       e_l + self.target_pts, ts, key=('tapeL', round(ts, 0)),
                       expires_in=60, extra=extra_l)
        e_s = mid - self.offset_pts
        extra_s = {
            'fill_mode': 'stop',
            'stop_offset_pts': self.stop_pts,
            'target_offset_pts': self.target_pts,
            'exit_mode': 'stop_market',
            'cohort': cohort,
            '_gen_ts': ts,
        }
        self.add_setup('SHORT', 'SHORT', e_s, e_s + self.stop_pts,
                       e_s - self.target_pts, ts, key=('tapeS', round(ts, 0)),
                       expires_in=60, extra=extra_s)
        self._last_signal_ts = ts


# =============================================================================
# Calendar grid strategy (Direction 7)
# =============================================================================
class CalendarGridStrategy(_BaseEmitter):
    def __init__(self, name, stop_pts, target_pts, **kwargs):
        super().__init__(name, stop_pts, target_pts, **kwargs)
        self._last_cell = None
        self._last_signal_ts = 0.0

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        pass

    def feed_signal(self, ts, bid, ask, day_counter, hh, dow):
        cell = (dow, hh)
        if cell == self._last_cell:
            return
        self._last_cell = cell
        if ts - self._last_signal_ts < 1800.0:
            return
        sig = CAL_GRID.signal(dow, hh, day_counter)
        if sig is None:
            return
        mid = (bid + ask) / 2.0
        if sig == 'LONG':
            self.emit(ts, 'LONG', mid + TICK, ('cal', dow, hh, day_counter),
                      expires_in=120)
        else:
            self.emit(ts, 'SHORT', mid - TICK, ('cal', dow, hh, day_counter),
                      expires_in=120)
        self._last_signal_ts = ts


# =============================================================================
# Ensemble voting strategy (Direction 8)
# =============================================================================
class EnsembleVotingStrategy(_BaseEmitter):
    """Polls 5 child round-4 strategies for pending-setup direction at each tick.
    Fires when 3+ agree on side at the same tick.
    """
    def __init__(self, name, children, vote_threshold=3,
                 stop_pts=10, target_pts=20, **kwargs):
        super().__init__(name, stop_pts, target_pts, **kwargs)
        self.children = children
        self.vote_threshold = vote_threshold
        self._last_signal_ts = 0.0

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        # Children's on_bar_close happens externally — we just look at their
        # pending lists.
        pass

    def feed_signal(self, ts, bid, ask):
        if ts - self._last_signal_ts < 20.0:
            return
        n_long = 0; n_short = 0
        for c in self.children:
            # Look at any pending setup not yet used; vote based on side
            for s in c.pending:
                if s.get('used') or s.get('_fire_attempted'):
                    continue
                side = s.get('side')
                # Only count setups near current price (within 5pt) so vote
                # is on STRONG signals
                if side == 'LONG':
                    if abs(s['entry'] - bid) <= 5.0:
                        n_long += 1
                else:
                    if abs(s['entry'] - ask) <= 5.0:
                        n_short += 1
                break  # one vote per child
        if n_long >= self.vote_threshold:
            mid = (bid + ask) / 2.0
            self.emit(ts, 'LONG', mid + TICK, ('ens', 'L', round(ts, 0)),
                      expires_in=60)
            self._last_signal_ts = ts
        elif n_short >= self.vote_threshold:
            mid = (bid + ask) / 2.0
            self.emit(ts, 'SHORT', mid - TICK, ('ens', 'S', round(ts, 0)),
                      expires_in=60)
            self._last_signal_ts = ts


# =============================================================================
# Pattern motif strategy (Direction 3) — simplified online k-means clusterer.
# We collect recent 30-sec price windows; after a 20-day warmup we cluster
# (via a simple online k-means with k=8) and tag clusters with their
# "purity" — fraction of stored exemplars that preceded a +20pt move in
# the next 5 minutes. Top-2 highest-purity clusters become signal sources.
# =============================================================================
class MotifGauge:
    def __init__(self, k=8, window_size=20):
        self.k = k
        self.window_size = window_size
        self._centroids = []  # list of normalized vectors
        self._cluster_n = [0] * k
        self._cluster_pos = [0] * k  # count of exemplars followed by +20pt move
        self._cluster_neg = [0] * k
        self._recent_ticks = deque(maxlen=window_size)  # (ts, last)
        self._future_marker = deque(maxlen=1000)  # (ts, last, cluster_idx)
        # warmup phase
        self._n_samples = 0

    def _norm(self, vec):
        if not vec:
            return vec
        mean = sum(vec) / len(vec)
        return [v - mean for v in vec]

    def _dist(self, a, b):
        return sum((x - y) ** 2 for x, y in zip(a, b))

    def feed_tick(self, ts, last):
        self._recent_ticks.append((ts, last))
        if len(self._recent_ticks) < self.window_size:
            return
        vec = [t[1] for t in self._recent_ticks]
        nv = self._norm(vec)
        # Find/assign cluster
        if len(self._centroids) < self.k:
            self._centroids.append(list(nv))
            cidx = len(self._centroids) - 1
        else:
            cidx = min(range(self.k),
                       key=lambda i: self._dist(self._centroids[i], nv))
            # Online update
            self._cluster_n[cidx] += 1
            alpha = 1.0 / max(1, self._cluster_n[cidx])
            self._centroids[cidx] = [
                self._centroids[cidx][i] * (1 - alpha) + nv[i] * alpha
                for i in range(len(nv))
            ]
        self._future_marker.append((ts, last, cidx))
        self._n_samples += 1
        # Resolve old markers (>5min ago)
        while self._future_marker and ts - self._future_marker[0][0] >= 300.0:
            ots, opx, oc = self._future_marker.popleft()
            move = last - opx
            if move >= 20.0:
                self._cluster_pos[oc] += 1
            elif move <= -20.0:
                self._cluster_pos[oc] += 1  # count both as event
            else:
                self._cluster_neg[oc] += 1

    def predict_side(self):
        """Return ('LONG', purity) etc if current pattern matches a high-purity
        cluster. Returns None if not warmed up."""
        if self._n_samples < 5000 or len(self._centroids) < self.k:
            return None
        # Compute purity per cluster
        best_c = None
        best_p = 0.0
        for i in range(self.k):
            tot = self._cluster_pos[i] + self._cluster_neg[i]
            if tot < 30:
                continue
            p = self._cluster_pos[i] / tot
            if p > best_p:
                best_p = p
                best_c = i
        if best_c is None or best_p < 0.65:
            return None
        # Current window cluster?
        if len(self._recent_ticks) < self.window_size:
            return None
        vec = [t[1] for t in self._recent_ticks]
        nv = self._norm(vec)
        cur_c = min(range(self.k),
                    key=lambda i: self._dist(self._centroids[i], nv))
        if cur_c != best_c:
            return None
        # Direction: from centroid net change sign
        ctr = self._centroids[cur_c]
        net = ctr[-1] - ctr[0]
        return ('LONG' if net > 0 else 'SHORT'), best_p


MOTIF = MotifGauge(k=8, window_size=20)


class MotifStrategy(_BaseEmitter):
    def __init__(self, name, stop_pts, target_pts, **kwargs):
        super().__init__(name, stop_pts, target_pts, **kwargs)
        self._last_signal_ts = 0.0

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        pass

    def feed_signal(self, ts, bid, ask):
        if ts - self._last_signal_ts < 60.0:
            return
        pred = MOTIF.predict_side()
        if pred is None:
            return
        side, _ = pred
        mid = (bid + ask) / 2.0
        if side == 'LONG':
            self.emit(ts, 'LONG', mid + TICK,
                      ('motif', 'L', round(ts, 0)), expires_in=120)
        else:
            self.emit(ts, 'SHORT', mid - TICK,
                      ('motif', 'S', round(ts, 0)), expires_in=120)
        self._last_signal_ts = ts


# =============================================================================
# RICH BOOKING with ADAPTIVE QUEUE support
# =============================================================================
# Re-implement r9_bot_on_tick but: when a LIMIT fires and the setup has
# the '_adaptive' flag, we compute order age = ts - _gen_ts and gate
# the fill by adaptive_fill_prob. If it fails, mark _fire_attempted but
# leave the setup alive (so it can re-try on the next touch within
# expires window).
def r10_bot_on_tick(strat, ts, bid, ask, day_counter, hh, mn, last_px):
    exe = strat._exec

    if strat.pending:
        strat.pending = [
            s for s in strat.pending
            if s['expires'] >= ts and not s.get('used')
        ]

    if strat.in_trade is not None:
        tr = strat.in_trade
        exit_mode = tr.get('exit_mode', 'stop_market')
        side = tr['side']
        entry = tr['entry']
        exit_now = None
        trail = tr.get('trail_pts')
        if trail is not None:
            if side == 'LONG':
                hi = max(tr.get('hi', entry), bid)
                tr['hi'] = hi
                new_stop = hi - trail
                if new_stop > tr['stop']:
                    tr['stop'] = new_stop
            else:
                lo = min(tr.get('lo', entry), ask)
                tr['lo'] = lo
                new_stop = lo + trail
                if new_stop < tr['stop']:
                    tr['stop'] = new_stop
        be_trig = tr.get('be_trig_pts')
        be_off = tr.get('be_off_pts', 0.0)
        if be_trig is not None and not tr.get('_be_set'):
            if side == 'LONG' and bid >= entry + be_trig:
                ns = entry + be_off
                if ns > tr['stop']:
                    tr['stop'] = ns
                tr['_be_set'] = True
            elif side == 'SHORT' and ask <= entry - be_trig:
                ns = entry - be_off
                if ns < tr['stop']:
                    tr['stop'] = ns
                tr['_be_set'] = True
        if exit_now is None:
            if side == 'LONG':
                if bid <= tr['stop']:
                    if exit_mode == 'stop_limit':
                        cap_px = tr['stop'] - STOP_LIMIT_OFFSET_PT
                        if bid < cap_px - 0.5 or RNG.random() < STOP_LIMIT_NONFILL_PROB:
                            tr['exit_mode'] = 'stop_market'
                        else:
                            pnl = cap_px - entry
                            exit_now = ('stop', pnl)
                    else:
                        slip = STOP_SLIP_PT
                        if RNG.random() < STOP_GAP_SLIP_PROB:
                            slip += RNG.random() * STOP_GAP_SLIP_MAX_PT
                        pnl = (tr['stop'] - slip) - entry
                        exit_now = ('stop', pnl)
                elif tr.get('target') is not None and bid >= tr['target']:
                    pnl = tr['target'] - entry
                    exit_now = ('tgt', pnl)
                elif ts - tr['et'] >= tr.get('max_hold', MAX_HOLD_S):
                    pnl = bid - entry
                    exit_now = ('to', pnl)
            else:
                if ask >= tr['stop']:
                    if exit_mode == 'stop_limit':
                        cap_px = tr['stop'] + STOP_LIMIT_OFFSET_PT
                        if ask > cap_px + 0.5 or RNG.random() < STOP_LIMIT_NONFILL_PROB:
                            tr['exit_mode'] = 'stop_market'
                        else:
                            pnl = entry - cap_px
                            exit_now = ('stop', pnl)
                    else:
                        slip = STOP_SLIP_PT
                        if RNG.random() < STOP_GAP_SLIP_PROB:
                            slip += RNG.random() * STOP_GAP_SLIP_MAX_PT
                        pnl = entry - (tr['stop'] + slip)
                        exit_now = ('stop', pnl)
                elif tr.get('target') is not None and ask <= tr['target']:
                    pnl = entry - tr['target']
                    exit_now = ('tgt', pnl)
                elif ts - tr['et'] >= tr.get('max_hold', MAX_HOLD_S):
                    pnl = entry - ask
                    exit_now = ('to', pnl)
        if exit_now is not None:
            reason, pnl_pts = exit_now
            cell = tr.get('regime_cell', 0)
            bidx = block_idx_for_day(day_counter)
            strat.completed.append((float(pnl_pts), reason, day_counter,
                                    bidx, cell))
            strat.by_day.setdefault(day_counter, []).append(float(pnl_pts))
            strat.in_trade = None
            strat.n_trades += 1
            exe.last_exit_ts = ts
            exe.active_limit_key = None
            exe.active_limit_armed_ts = None
            if RNG.random() < STALE_FILL_PROB:
                exe.skip_next_trade = True
        return

    if exe.last_exit_ts is not None and ts - exe.last_exit_ts < COOLDOWN_S:
        return
    if not strat._in_session(hh, mn):
        return

    closest, dist = _r7._closest_pending_r7(strat, bid, ask)
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

    if exe.active_limit_armed_ts is not None and ts < exe.active_limit_armed_ts:
        return

    s = closest
    orig = s.get('orig', s['side'])
    entry_px_target = s['entry']
    fill_mode = s.get('fill_mode', 'limit')

    fill_px = None
    if fill_mode == 'limit':
        if orig == "LONG":
            if ask <= entry_px_target - TICK:
                fill_px = entry_px_target
        else:
            if bid >= entry_px_target + TICK:
                fill_px = entry_px_target
    elif fill_mode == 'marketable':
        if orig == "LONG":
            if ask <= entry_px_target:
                fill_px = ask + MARKETABLE_SLIP_PT
        else:
            if bid >= entry_px_target:
                fill_px = bid - MARKETABLE_SLIP_PT
    elif fill_mode == 'stop':
        if orig == "LONG":
            if ask >= entry_px_target:
                fill_px = ask + STOP_ENTRY_SLIP_PT
        else:
            if bid <= entry_px_target:
                fill_px = bid - STOP_ENTRY_SLIP_PT

    if fill_px is None:
        return

    # ADAPTIVE QUEUE MODEL: probabilistic fill based on age-in-book
    if s.get('_adaptive') and fill_mode == 'limit':
        gen_ts = s.get('_gen_ts', ts)
        age = ts - gen_ts
        p = _adaptive_fill_prob(age)
        if RNG.random() > p:
            # missed fill — keep setup alive but mark _fire_attempted so
            # the engine moves on; clear active key so future ticks can re-arm
            s['_fire_attempted'] = True
            exe.active_limit_key = None
            exe.active_limit_armed_ts = None
            return

    if exe.skip_next_trade:
        exe.skip_next_trade = False
        for ps in strat.pending:
            if ps.get('key') == closest_key:
                ps['used'] = True
                break
        exe.active_limit_key = None
        exe.active_limit_armed_ts = None
        return

    side = s['side']
    s['used'] = True
    cohort = s.get('cohort')
    if cohort is not None:
        _r7._cancel_cohort(strat, cohort)

    stop_offset = s.get('stop_offset_pts')
    tgt_offset = s.get('target_offset_pts')
    if stop_offset is None:
        if side == 'LONG':
            stop = s['stop']
            tgt = s.get('target')
        else:
            stop = s['stop']
            tgt = s.get('target')
    else:
        if side == 'LONG':
            stop = fill_px - stop_offset
            tgt = fill_px + tgt_offset if tgt_offset else None
        else:
            stop = fill_px + stop_offset
            tgt = fill_px - tgt_offset if tgt_offset else None

    strat.in_trade = {
        'side': side,
        'entry': fill_px,
        'stop': stop,
        'target': tgt,
        'et': ts,
        'exit_mode': s.get('exit_mode', 'stop_market'),
        'max_hold': s.get('max_hold', MAX_HOLD_S),
        'trail_pts': s.get('trail_pts'),
        'be_trig_pts': s.get('be_trig_pts'),
        'be_off_pts': s.get('be_off_pts', 0.0),
        'regime_cell': REGIME.current_cell(),
    }
    exe.active_limit_key = None
    exe.active_limit_armed_ts = None


# =============================================================================
# VARIANT LIBRARY
# =============================================================================
def _build_r4_winners():
    """Build the 5 round-4 idealized winners for ensemble + base reference."""
    return [
        MarketablePullback("ENS_CHILD_R4_CANON_INV_236",
                           impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
                           stop_pts=10, target_pts=20, invert=True),
        MarketablePullback("ENS_CHILD_R4_INV15s_imp2_s4t12",
                           impulse_pts=2.0, impulse_bars=4, pull_pct=0.236,
                           stop_pts=4, target_pts=12, invert=True, max_hold=120),
        MarketablePullback("ENS_CHILD_R4_INV_pp118_s4t16_imp3",
                           impulse_pts=3.0, impulse_bars=4, pull_pct=0.118,
                           stop_pts=4, target_pts=16, invert=True),
        MarketablePullback("ENS_CHILD_R4_INV30s_imp3_s3t9",
                           impulse_pts=3.0, impulse_bars=4, pull_pct=0.236,
                           stop_pts=3, target_pts=9, invert=True, max_hold=180),
        MarketablePullback("ENS_CHILD_R4_INV_pp382_s5t20_imp5",
                           impulse_pts=5.0, impulse_bars=4, pull_pct=0.382,
                           stop_pts=5, target_pts=20, invert=True),
    ]


def build_round10_variants():
    """Builds the full battery. Returns (v1m, v15s, v30s, vtick_only, aux, n).

    vtick_only strategies don't subscribe to bar closes but get feed_signal()
    called per tick.
    """
    v1m = []
    v15s = []
    v30s = []
    vtick = []  # tick-only signal-emitters

    # =========================================================================
    # BASE references: the strongest prop-firm survivors from r9 (for control)
    # =========================================================================
    BASE = [
        ("R10_BASE_R4_CANON_INV_236",
         lambda: MarketablePullback(
             "R10_BASE_R4_CANON_INV_236",
             impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
             stop_pts=10, target_pts=20, invert=True)),
        ("R10_BASE_R8_C04_MTF_early_imp4_b3_s8t24_INV",
         lambda: MTFConfluence(
             "R10_BASE_R8_C04_MTF_early_imp4_b3_s8t24_INV",
             impulse_pts=4.0, impulse_bars=3, pull_pct=0.382,
             stop_pts=8, target_pts=24, invert=True)),
        ("R10_BASE_R8_B04_CANON_bal_n300_t30",
         lambda: GatedCanonPullback(
             "R10_BASE_R8_B04_CANON_bal_n300_t30",
             balance_align=True, balance_n=300, balance_thresh=30)),
    ]
    for name, builder in BASE:
        v1m.append(builder())

    # =========================================================================
    # Direction 4 — VPIN-gated variants
    # =========================================================================
    VPIN_VARIANTS = [
        (0.20, "lo"), (0.30, "mid"), (0.40, "hi"),
    ]
    for vmax, tag in VPIN_VARIANTS:
        # Base CANON inversion at three VPIN thresholds
        s = VPINGatedPullback(
            f"D4_VPIN_{tag}_CANON_INV_236",
            impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
            stop_pts=10, target_pts=20, invert=True,
            vpin_max=vmax)
        v1m.append(s)
        # And the 15s sub-minute champion
        s = VPINGatedPullback(
            f"D4_VPIN_{tag}_INV15s_imp2_s4t12",
            impulse_pts=2.0, impulse_bars=4, pull_pct=0.236,
            stop_pts=4, target_pts=12, invert=True, max_hold=120,
            vpin_max=vmax)
        v15s.append(s)
    # Inverse VPIN gate (high VPIN = trend-follow)
    for vmin, tag in [(0.50, "lo"), (0.65, "mid"), (0.80, "hi")]:
        s = VPINHighFadePullback(
            f"D4_VPINhi_{tag}_CANON",
            impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
            stop_pts=10, target_pts=20, invert=True,
            vpin_min=vmin)
        v1m.append(s)

    # =========================================================================
    # Direction 5 — Absorption strategies
    # =========================================================================
    ABS_CONFIGS = [
        (10, 3, 9), (10, 5, 15), (15, 5, 15), (15, 5, 20),
        (20, 8, 24), (25, 8, 24), (20, 5, 15), (15, 3, 9),
    ]
    for thr, stp, tgt in ABS_CONFIGS:
        s = AbsorptionStrategy(
            f"D5_ABS_t{thr}_s{stp}t{tgt}",
            threshold=thr, stop_pts=stp, target_pts=tgt, invert=False)
        vtick.append(s)
        # Also inverted (fade absorption)
        s2 = AbsorptionStrategy(
            f"D5_ABSinv_t{thr}_s{stp}t{tgt}",
            threshold=thr, stop_pts=stp, target_pts=tgt, invert=True)
        vtick.append(s2)

    # =========================================================================
    # Direction 6 — Tape speed straddle
    # =========================================================================
    for mult in [3.0, 5.0, 7.0]:
        for offset in [2.0, 3.0, 5.0]:
            for (stp, tgt) in [(5, 15), (8, 24), (5, 20)]:
                s = TapeStraddleStrategy(
                    f"D6_TAPE_x{int(mult)}_o{int(offset)}_s{stp}t{tgt}",
                    multiplier=mult, offset_pts=offset,
                    stop_pts=stp, target_pts=tgt)
                vtick.append(s)

    # =========================================================================
    # Direction 7 — Calendar grid
    # =========================================================================
    for (stp, tgt) in [(5, 15), (8, 24), (10, 20), (5, 20)]:
        s = CalendarGridStrategy(
            f"D7_CAL_s{stp}t{tgt}",
            stop_pts=stp, target_pts=tgt)
        vtick.append(s)
        s2 = CalendarGridStrategy(
            f"D7_CALadap_s{stp}t{tgt}",
            stop_pts=stp, target_pts=tgt,
            adaptive_queue=True, fill_mode='limit')
        vtick.append(s2)

    # =========================================================================
    # Direction 8 — Ensemble voting
    # =========================================================================
    # Build 5 round-4 winner children (these ALSO get reported)
    children = _build_r4_winners()
    for c in children:
        v1m.append(c)
    for thr in [2, 3, 4]:
        for (stp, tgt) in [(5, 15), (8, 24), (10, 20)]:
            s = EnsembleVotingStrategy(
                f"D8_ENS_v{thr}_s{stp}t{tgt}",
                children=children,
                vote_threshold=thr,
                stop_pts=stp, target_pts=tgt)
            vtick.append(s)

    # =========================================================================
    # Direction 3 — Motif strategies (warmup before producing signals)
    # =========================================================================
    for (stp, tgt) in [(5, 15), (8, 24), (10, 20), (5, 20)]:
        s = MotifStrategy(
            f"D3_MOTIF_s{stp}t{tgt}",
            stop_pts=stp, target_pts=tgt)
        vtick.append(s)

    # =========================================================================
    # Direction 9 — Adaptive queue model applied to BASE round-4 winners
    # We replicate the winners with adaptive_queue=True semantics injected
    # into their setup extra dict via a wrapper class
    # =========================================================================
    class AdaptivePullback(MarketablePullback):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
            # Capture pending count before
            n_before = len(self.pending)
            super().on_bar_close(ts, hh, mn, bo, bh, bl, bc, hist)
            # Mark newly added setups as adaptive + reset fill_mode to limit
            for s in self.pending[n_before:]:
                s['_adaptive'] = True
                s['_gen_ts'] = ts
                s['fill_mode'] = 'limit'

    R10_D9 = [
        ("D9_ADAP_R4_CANON_INV_236", 5.0, 4, 0.236, 10, 20, True, '1m'),
        ("D9_ADAP_R4_INV15s_imp2_s4t12", 2.0, 4, 0.236, 4, 12, True, '15s'),
        ("D9_ADAP_R4_INV_pp118_s4t16_imp3", 3.0, 4, 0.118, 4, 16, True, '1m'),
        ("D9_ADAP_R4_INV30s_imp3_s3t9", 3.0, 4, 0.236, 3, 9, True, '30s'),
        ("D9_ADAP_R4_INV_pp382_s5t20_imp5", 5.0, 4, 0.382, 5, 20, True, '1m'),
        ("D9_ADAP_R4_INV_pp236_s5t20_imp5", 5.0, 4, 0.236, 5, 20, True, '1m'),
        ("D9_ADAP_R4_INV_pp236_s10t20", 5.0, 4, 0.236, 10, 20, True, '1m'),
        ("D9_ADAP_R4_INV_pp118_s4t16_imp5", 5.0, 4, 0.118, 4, 16, True, '1m'),
        ("D9_ADAP_R4_INV_pp382_s4t16_imp3", 3.0, 4, 0.382, 4, 16, True, '1m'),
        ("D9_ADAP_R4_INV_pp236_s4t16_imp3", 3.0, 4, 0.236, 4, 16, True, '1m'),
        ("D9_ADAP_R4_INV15s_imp2_s3t12", 2.0, 4, 0.236, 3, 12, True, '15s'),
        ("D9_ADAP_R4_INV30s_imp3_s4t12", 3.0, 4, 0.236, 4, 12, True, '30s'),
    ]
    for name, imp, ibars, pp, stp, tgt, inv, gran in R10_D9:
        max_hold = 120 if gran == '15s' else (180 if gran == '30s' else MAX_HOLD_S)
        s = AdaptivePullback(name, impulse_pts=imp, impulse_bars=ibars,
                             pull_pct=pp, stop_pts=stp, target_pts=tgt,
                             invert=inv, max_hold=max_hold)
        if gran == '15s':
            v15s.append(s)
        elif gran == '30s':
            v30s.append(s)
        else:
            v1m.append(s)

    # =========================================================================
    # Direction 10 — Tight sweep around best NQ + prop-firm winner
    # Round 9: top prop-firm NQ = R8_C04_MTF_early_imp4_b3_s8t24_INV
    #   impulse_pts=4.0, impulse_bars=3, pull_pct=0.382, stop=8, tgt=24
    # We sweep within ±20% (a focused diverse 60 sample) under both fees.
    # =========================================================================
    D10_PARAMS = []
    pp_vals = [0.19, 0.236, 0.30, 0.382, 0.45]
    imp_vals = [3, 4, 5, 6]
    ibars_vals = [3, 4]
    stp_vals = [6, 8, 10, 12]
    tgt_vals = [16, 20, 24, 30]
    # Sessions
    sessions = [
        ('all', None, None),
        ('NYO', (13, 30), (15, 30)),
        ('OVR', (13, 30), (16, 0)),
        ('RTH', (13, 30), (20, 0)),
        ('CME', (22, 0), (5, 0)),
    ]
    # diverse sampling — pick subset combinations (limit to ~50 to control runtime)
    rng_seed = random.Random(0xABCDEF)
    full_combos = [
        (pp, imp, ib, st, tg, ses)
        for pp in pp_vals for imp in imp_vals for ib in ibars_vals
        for st in stp_vals for tg in tgt_vals for ses in sessions
        if tg > st
    ]
    rng_seed.shuffle(full_combos)
    for pp, imp, ib, st, tg, ses in full_combos[:50]:
        ses_name, ses_start, ses_end = ses
        name = (f"D10_MTF_pp{int(pp*1000)}_imp{imp}_b{ib}_s{st}t{tg}_{ses_name}")
        s = MTFConfluence(
            name, impulse_pts=float(imp), impulse_bars=ib, pull_pct=pp,
            stop_pts=st, target_pts=tg, invert=True,
            session_start=ses_start, session_end=ses_end)
        v1m.append(s)

    # =========================================================================
    # Direction 2 — GA top survivors (loaded from disk if pre-pass ran)
    # =========================================================================
    ga_top = _load_ga_survivors()
    for spec in ga_top[:10]:
        name = f"D2_GA_{spec['id']}"
        s = MarketablePullback(
            name, impulse_pts=spec['impulse_pts'],
            impulse_bars=spec['impulse_bars'],
            pull_pct=spec['pull_pct'],
            stop_pts=spec['stop_pts'],
            target_pts=spec['target_pts'],
            invert=True,
            session_start=spec.get('ses_start'),
            session_end=spec.get('ses_end'))
        v1m.append(s)

    # =========================================================================
    # Direction 1 — RL Q-table policy (loaded from disk if pre-pass ran)
    # =========================================================================
    qtable = _load_q_table()
    if qtable is not None:
        for (stp, tgt) in [(5, 15), (8, 24), (10, 20)]:
            s = RLQTableStrategy(
                f"D1_RL_s{stp}t{tgt}",
                qtable=qtable,
                stop_pts=stp, target_pts=tgt)
            vtick.append(s)

    # Attach executor
    n_total = 0
    for ls in [v1m, v15s, v30s, vtick]:
        for s in ls:
            attach_r7_executor(s)
            n_total += 1
    return v1m, v15s, v30s, vtick, n_total


# =============================================================================
# RL Q-table policy strategy (Direction 1, only used if pre-pass produced one)
# =============================================================================
class RLQTableStrategy(_BaseEmitter):
    def __init__(self, name, qtable, stop_pts, target_pts, **kwargs):
        super().__init__(name, stop_pts, target_pts, **kwargs)
        self.qtable = qtable
        # Use shared regime + tape gauges for state
        self._last_signal_ts = 0.0
        self._state_buf = deque(maxlen=8)

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) >= 4:
            net4 = hist[-1][3] - hist[-4][0]
            self._state_buf.append(net4)

    def feed_signal(self, ts, bid, ask):
        if ts - self._last_signal_ts < 20.0:
            return
        if not self._state_buf:
            return
        net = self._state_buf[-1]
        net_bin = 0 if net > 0 else 1
        vol_bin = 0 if REGIME.current_cell() & 1 else 1
        tape_bin = 0 if TAPE.ratio() < 2.0 else 1
        # State key
        state = (net_bin, vol_bin, tape_bin)
        q = self.qtable.get(state)
        if not q:
            return
        # action 0=noop, 1=long, 2=short
        best_a = max(range(3), key=lambda a: q.get(a, 0.0))
        if q.get(best_a, 0.0) <= 0:
            return
        mid = (bid + ask) / 2.0
        if best_a == 1:
            self.emit(ts, 'LONG', mid + TICK,
                      ('rl', 'L', round(ts, 0)), expires_in=60)
            self._last_signal_ts = ts
        elif best_a == 2:
            self.emit(ts, 'SHORT', mid - TICK,
                      ('rl', 'S', round(ts, 0)), expires_in=60)
            self._last_signal_ts = ts


def _load_q_table():
    p = "/home/user/HFTBot/research/round10_qtable.pkl"
    if os.path.exists(p):
        try:
            with open(p, "rb") as f:
                return pickle.load(f)
        except Exception:
            return None
    return None


def _load_ga_survivors():
    p = "/home/user/HFTBot/research/round10_ga_survivors.pkl"
    if os.path.exists(p):
        try:
            with open(p, "rb") as f:
                return pickle.load(f)
        except Exception:
            return []
    return []


# =============================================================================
# CHECKPOINT
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
        "rng_state": RNG.getstate(),
        "cal_grid_bias": dict(CAL_GRID.bias),
        "cal_grid_buf": {k: list(v) for k, v in CAL_GRID._buf.items()},
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
        print(f"[round10] checkpoint load failed: {e!r}", file=sys.stderr)
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
        RNG.setstate(state["rng_state"])
    except Exception:
        pass
    try:
        CAL_GRID.bias.update(state.get("cal_grid_bias", {}))
        for k, v in state.get("cal_grid_buf", {}).items():
            CAL_GRID._buf[k] = list(v)
    except Exception:
        pass
    return (int(state["offset"]),
            int(state["day_counter"]),
            state["last_day_key"])


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
# MAIN
# =============================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offset", type=int, default=DEFAULT_OFFSET)
    ap.add_argument("--ckpt-suffix", default="")
    ap.add_argument("--max-days", type=int, default=60)
    args = ap.parse_args()

    ckpt_path = ("/home/user/HFTBot/research/round10_checkpoint"
                 f"{args.ckpt_suffix}.pkl")
    csv_path = ("/home/user/HFTBot/research/round10_summary"
                f"{args.ckpt_suffix}.csv")
    md_path = "/home/user/HFTBot/research/round10_results.md"

    v1m, v15s, v30s, vtick, n_total = build_round10_variants()
    all_strats = v1m + v15s + v30s + vtick
    print(f"\n[round10] Built {len(all_strats)} reportable strategies "
          f"({len(v1m)} 1m + {len(v15s)} 15s + {len(v30s)} 30s + "
          f"{len(vtick)} tick)", file=sys.stderr)
    print(f"[round10] starting offset {args.offset:,}, ckpt={ckpt_path}",
          file=sys.stderr)

    resumed = load_checkpoint(ckpt_path, all_strats)
    if resumed is not None:
        start_offset, day_counter, last_day_key = resumed
        resumed_trades = sum(s.n_trades for s in all_strats)
        print(f"[round10] RESUMING from offset {start_offset:,} "
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
    print(f"[round10] file size: {file_size:,} bytes", file=sys.stderr)

    max_day_counter = day_counter + args.max_days

    # Pre-init dow lookup
    # Anchor: use day_counter and treat day 0 as Wednesday? We use Zeller for
    # accurate weekday from yy/mm/dd.
    def _dow(y, m, d):
        if m < 3:
            m += 12; y -= 1
        K = y % 100; J = y // 100
        h = (d + (13*(m+1))//5 + K + K//4 + J//4 + 5*J) % 7
        # 0=Sat,1=Sun,...,6=Fri; convert to Mon=0..Sun=6
        return (h + 5) % 7

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
                    print(f"  [round10] ckpt save failed: {e!r}", file=sys.stderr)
                print(f"  [round10] {n_lines/1e6:.1f}M ticks rate={rate/1e6:.2f}M/s "
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
            dow = _dow(yy, mm, dd)

            MARKET.feed_tick(ts, last, bid, ask)
            VPIN_GAUGE.feed_tick(last, bid, ask)
            TAPE.feed_tick(ts)
            ABS_GAUGE.feed_tick(last, bid, ask)
            CAL_GRID.feed_tick(ts, last, day_counter, hh, dow)
            MOTIF.feed_tick(ts, last)

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
            if v30s and bb_30s.on_tick(ts, last):
                closed = bb_30s.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    for s in v30s:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_30s.history)

            # Per-tick signal emitters
            for s in vtick:
                if isinstance(s, CalendarGridStrategy):
                    s.feed_signal(ts, bid, ask, day_counter, hh, dow)
                else:
                    fs = getattr(s, 'feed_signal', None)
                    if fs is not None:
                        fs(ts, bid, ask)

            for s in all_strats:
                r10_bot_on_tick(s, ts, bid, ask, day_counter, hh, mn, last)

    elapsed = time.time() - t_start
    total_days = day_counter + 1
    print(f"\n[round10] DONE in {elapsed/60:.1f}min, {n_lines:,} ticks, "
          f"{total_days} day buckets", file=sys.stderr)

    # =========================================================================
    # REPORTING
    # =========================================================================
    rows_191 = [report_strategy(s, total_days, FEE_FULL_RT) for s in all_strats]
    rows_074 = [report_strategy(s, total_days, FEE_PROP_RT) for s in all_strats]
    rows_nq_191 = [report_strategy(s, total_days, FEE_FULL_RT, NQ_PER_PT) for s in all_strats]
    rows_nq_074 = [report_strategy(s, total_days, FEE_PROP_RT, NQ_PER_PT) for s in all_strats]

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
    print(f"[round10] wrote CSV {csv_path}", file=sys.stderr)

    def is_pass(r):
        return (r['trades_per_day'] >= 300 and r['wr'] >= 0.45
                and r['per_day'] >= 1000 and r['max_dd'] <= 5000)

    pass_191 = [r for r in rows_191 if is_pass(r)]
    pass_074 = [r for r in rows_074 if is_pass(r)]
    pass_nq_191 = [r for r in rows_nq_191 if is_pass(r)]
    pass_nq_074 = [r for r in rows_nq_074 if is_pass(r)]

    # Categorize by direction prefix
    def _dir(name):
        for prefix in ['D1_', 'D2_', 'D3_', 'D4_', 'D5_', 'D6_', 'D7_',
                       'D8_', 'D9_', 'D10_', 'R10_BASE_', 'ENS_CHILD_']:
            if name.startswith(prefix):
                return prefix.rstrip('_')
        return 'OTHER'

    by_dir = defaultdict(list)
    for r in rows_191:
        by_dir[_dir(r['name'])].append(r)

    # ---- MARKDOWN ----
    L = []
    L.append("# Round 10 strategy search — relentless ten-direction battery\n\n")
    L.append(f"Generated: {datetime.now().isoformat()}\n")
    L.append(f"Period: {total_days} calendar-day buckets from offset "
             f"{args.offset:,} (max-days={args.max_days})\n")
    L.append(f"Tick stream: {n_lines:,} lines processed\n")
    L.append(f"Strategies tested: {len(all_strats)}\n\n")

    L.append("## Execution model\n\n")
    L.append("Bot-faithful: queue overshoot by 1 tick (LIMIT), 200ms latency, "
             "10pt approach threshold, multi-setup lock, 0.5pt stop slip + "
             "10% gap risk, 10s cooldown, 600s max hold. "
             "Adaptive queue model gates D9 strategies (age-based fill prob).\n\n")
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

    L.append("\n## Section 2 — Top 30 by $/day across all directions (MNQ $1.91)\n\n")
    L.append("| Rank | Strategy | Dir | Tr | Tr/d | WR% | $/d 191 | $/d 074 | $/d NQ 191 | DD | Sharpe |\n")
    L.append("|---:|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    nq191_by = {r['name']: r for r in rows_nq_191}
    for i, r in enumerate(rows_191[:30], 1):
        n = r['name']
        r74 = rows_074_by_name[n]
        rnq = nq191_by[n]
        L.append(
            f"| {i} | {n} | {_dir(n)} | {r['n']:,} | {r['trades_per_day']:.1f} | "
            f"{r['wr']*100:.1f} | ${r['per_day']:,.0f} | "
            f"${r74['per_day']:,.0f} | ${rnq['per_day']:,.0f} | "
            f"${r['max_dd']:,.0f} | {r['sharpe']:.2f} |\n")

    L.append("\n## Section 3 — Per-direction headline\n\n")
    L.append("| Direction | n_strats | Best $/d 191 | Best $/d 074 | Best $/d NQ191 | Best $/d NQ074 | Top strat |\n")
    L.append("|---|---:|---:|---:|---:|---:|---|\n")
    for d in sorted(by_dir.keys()):
        items = by_dir[d]
        items_sorted = sorted(items, key=lambda r: -r['per_day'])
        top = items_sorted[0]
        n_strats = len(items)
        n = top['name']
        r74 = rows_074_by_name[n]
        rnq = nq191_by[n]
        rnq74 = next(x for x in rows_nq_074 if x['name'] == n)
        L.append(f"| {d} | {n_strats} | ${top['per_day']:,.0f} | "
                 f"${r74['per_day']:,.0f} | ${rnq['per_day']:,.0f} | "
                 f"${rnq74['per_day']:,.0f} | {n} |\n")

    # ---- Top 20 by NQ $0.74 (the prior-round best lever)
    L.append("\n## Section 4 — Top 20 by $/day under NQ $0.74 (best prior lever)\n\n")
    L.append("| Rank | Strategy | Tr/d | WR% | $/day NQ | maxDD | Sharpe |\n")
    L.append("|---:|---|---:|---:|---:|---:|---:|\n")
    for i, r in enumerate(rows_nq_074[:20], 1):
        L.append(f"| {i} | {r['name']} | {r['trades_per_day']:.1f} | "
                 f"{r['wr']*100:.1f} | ${r['per_day']:,.0f} | "
                 f"${r['max_dd']:,.0f} | {r['sharpe']:.2f} |\n")

    # ---- Lever ranking
    L.append("\n## Section 5 — Lever ranking (best $/day MNQ-equivalent)\n\n")
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

    # ---- Round 11 recommendation
    L.append("\n## Section 6 — Round 11 recommendations\n\n")
    if pass_074 or pass_191 or pass_nq_074 or pass_nq_191:
        L.append("**PASSERS FOUND.** Recommend deployment validation:\n")
        L.append("1. Re-test top passers on fresh 30d window (out-of-sample).\n")
        L.append("2. Live paper-trade for 1 week before real money.\n")
        L.append("3. Monitor adaptive queue assumption — verify in live order book.\n")
    else:
        L.append("**NO PASSERS** after 10 rounds and 1,900+ variants.\n\n")
        L.append("Round 11 should attack at scale with these new angles:\n")
        L.append("1. **Multi-instrument** — acquire ES, RTY, CL tick data; cross-asset signals.\n")
        L.append("2. **Order book imbalance** — acquire L2 book data (not just trades); top-of-book size ratio.\n")
        L.append("3. **News/event injection** — economic-calendar-aligned strategy (avoid 8:30am EST data dump).\n")
        L.append("4. **Large-population GA** — run a 200-individual × 200-generation GA on a 14d window.\n")
        L.append("5. **Deep learning** — LSTM / Transformer on tick microstructure features.\n")
        L.append("6. **Maker rebate venues** — CME has no maker rebates, but PFOF / Mosaic might.\n")
        L.append("7. **Liquidation cascades** — detect rapid limit-book reload via top-of-book changes.\n")
        L.append("8. **Position sizing as variable** — Kelly fractional, vol-targeting; relax 1-contract constraint.\n")
        L.append("9. **Pyramiding** — same strategy with multiple stop/target tiers per signal.\n")
        L.append("10. **Time-budget redistribution** — strategy that only fires during specific 30-min windows where edge is statistically significant (Bonferroni-corrected).\n")

    L.append("\n## Section 7 — Full strategy table (sorted by $/day at $1.91)\n\n")
    L.append("| Strategy | Dir | Tr | Tr/d | WR% | $/d 191 | $/d 074 | $/d NQ191 | $/d NQ074 | maxDD 191 | Sharpe |\n")
    L.append("|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    nq074_by = {r['name']: r for r in rows_nq_074}
    for r in rows_191:
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
    print(f"[round10] wrote MD {md_path}", file=sys.stderr)

    print("\n" + "=" * 110)
    print(f"FULL_PASS under $1.91 (MNQ): {len(pass_191)}")
    print(f"FULL_PASS under $0.74 (MNQ prop-firm): {len(pass_074)}")
    print(f"FULL_PASS under $1.91 (NQ): {len(pass_nq_191)}")
    print(f"FULL_PASS under $0.74 (NQ prop-firm): {len(pass_nq_074)}")
    print("=" * 110)
    for r in rows_191[:30]:
        n = r['name']
        r74 = rows_074_by_name[n]
        rnq = nq191_by[n]
        flag = ""
        if is_pass(r): flag = " *PASS(full)*"
        elif is_pass(r74): flag = " *PASS(prop)*"
        elif is_pass(rnq): flag = " *PASS(NQ)*"
        print(f"{n:>50s} {r['n']:>6d} {r['trades_per_day']:>6.1f} "
              f"{r['wr']*100:>4.1f}% ${r['per_day']:>+7.0f} (074: "
              f"${r74['per_day']:>+6.0f}, NQ: ${rnq['per_day']:>+6.0f}){flag}")

    try:
        if os.path.exists(ckpt_path):
            os.remove(ckpt_path)
            print(f"[round10] cleared checkpoint {ckpt_path}", file=sys.stderr)
    except Exception:
        pass


if __name__ == "__main__":
    main()
