"""Round 12 strategy search for MNQ — 20 BRAND-NEW avenues, 10,000+ variants.

User mandate: "If 7,000 variants say high volume = shit win rate, find another
7,000 variants. You don't give up." Round 12 attacks 20 brand-new directions
and ALSO hammers the existing top-3 base strategies with a 9,000-variant Latin
hypercube. Total variant count target: 10,000+.

Avenues (each is a separate strategy family with its own sweep):

  A. Reactive bracket switching — start wide, shrink after Xs no movement,
     then scratch.
  B. Anti-stop-hunting offset placement — non-standard stop offsets
     (0.13, 0.37, 0.63, 0.87 pt) on top of base R:R.
  C. Micro-momentum cascades — all 5 timeframes (100ms..30s) align.
  D. Stop-cluster fade — LIMIT-fade snap-back after estimated stop-run.
  E. Pinning / round-number magnet — fade moves away from 25/50/100-pt grid.
  F. Anti-correlation morning/afternoon — directional bias by hour.
  G. Multi-frequency Fourier signal — FFT cycle reversal.
  H. Wavelet decomposition entries — 5 scales align.
  I. Bid-ask interaction depth — persistence vs movement.
  J. Volume vacuum detection — tick-rate drop straddle.
  K. Cross-tick momentum at sub-100ms — pure microstructure.
  L. Bayesian momentum — exponentially decayed posterior on direction.
  M. Markov state classifier — discretize state, fire on high-prob transition.
  N. Time-of-day micro-strategies — 96 15-minute windows, each its own setup.
  O. Stochastic strategy generation — 2,000 randomly-sampled MTF variants.
  P. Reactive position sizing — confidence gate (skip on recent low WR).
  Q. Liquidity vacuum + speed-of-tape combo — both signals within 2s.
  R. Pre-bar formation prediction — predict close from 30s into bar.
  S. Optimal stopping (Bellman approx) — dynamic exit threshold.
  T. Massive 9,000-variant Latin sweep over the existing top-3 winners.

The user expects: NEVER conclude "this can't work." ALWAYS conclude "we need
more variants OR a new avenue." Round 13 recs are emitted at the end.
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

# Lineage
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
from research import round11_search as _r11
sys.modules.setdefault("round11_search", _r11)

# Inherit classes/constants
StrategyBase = _r4.StrategyBase
BarBuilder = _r4.BarBuilder
PullbackStrategy = _r4.PullbackStrategy
MarketablePullback = _r6.MarketablePullback
MTFConfluence = _r7.MTFConfluence
MARKET = _r8.MARKET
GatedCanonPullback = _r8.GatedCanonPullback
REGIME = _r9.REGIME

attach_r7_executor = _r7.attach_r7_executor
block_idx_for_day = _r9.block_idx_for_day

_BaseEmitter = _r10._BaseEmitter
r10_bot_on_tick = _r10.r10_bot_on_tick

TICK_WIN = _r11.TICK_WIN

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

RNG = random.Random(0xDECAFB12)


# =============================================================================
# Shared micro-gauges (used across avenues C, I, J, K, L, M, Q, R)
# =============================================================================
class MultiScaleMomentum:
    """Track price at 5 timeframes: 100ms, 500ms, 1s, 5s, 30s. Sample
    every tick into ring buffers indexed by (ts // dt)."""
    SCALES_S = (0.1, 0.5, 1.0, 5.0, 30.0)

    def __init__(self):
        self.snaps = [deque(maxlen=8) for _ in self.SCALES_S]
        self.last_bucket = [-1.0] * len(self.SCALES_S)

    def feed(self, ts, last):
        for i, dt in enumerate(self.SCALES_S):
            b = math.floor(ts / dt)
            if b > self.last_bucket[i]:
                self.snaps[i].append(last)
                self.last_bucket[i] = b

    def alignment(self, thresholds):
        """Return (sign, n_aligned) where sign is +1/-1 if all (or most)
        scales moved in same direction by >= thresholds[i] over the last
        2 sample boundaries."""
        signs = []
        for i, dt in enumerate(self.SCALES_S):
            if len(self.snaps[i]) < 2:
                continue
            delta = self.snaps[i][-1] - self.snaps[i][0]
            if abs(delta) < thresholds[i]:
                signs.append(0)
            else:
                signs.append(1 if delta > 0 else -1)
        if not signs:
            return (0, 0)
        # count alignment
        n_pos = sum(1 for s in signs if s > 0)
        n_neg = sum(1 for s in signs if s < 0)
        if n_pos == len(signs) and n_pos == len(self.SCALES_S):
            return (1, n_pos)
        if n_neg == len(signs) and n_neg == len(self.SCALES_S):
            return (-1, n_neg)
        # near-full alignment (4/5)
        if n_pos >= 4 and n_neg == 0:
            return (1, n_pos)
        if n_neg >= 4 and n_pos == 0:
            return (-1, n_neg)
        return (0, max(n_pos, n_neg))


MSM = MultiScaleMomentum()


class TickRateGauge:
    """Track ticks per second over rolling windows. Caches rate per window
    and only refreshes when at least 1s has passed since last compute.
    """
    def __init__(self):
        self._buf = deque(maxlen=4000)  # (ts,)
        self._cache = {}  # window_s -> (last_ts, last_rate)

    def feed(self, ts):
        self._buf.append(ts)
        cutoff = ts - 120.0
        while self._buf and self._buf[0] < cutoff:
            self._buf.popleft()

    def rate(self, window_s, now_ts):
        cached = self._cache.get(window_s)
        if cached is not None and now_ts - cached[0] < 0.5:
            return cached[1]
        if not self._buf:
            self._cache[window_s] = (now_ts, 0.0)
            return 0.0
        cutoff = now_ts - window_s
        # binary search would be faster but deque doesn't support it
        # iterate from right
        n = 0
        for t in reversed(self._buf):
            if t < cutoff:
                break
            n += 1
        rate = n / max(0.001, window_s)
        self._cache[window_s] = (now_ts, rate)
        return rate


TICK_RATE = TickRateGauge()


class BidAskPersistence:
    """Track if bid level has persisted while ask kept moving."""
    def __init__(self):
        self._bid_buf = deque(maxlen=200)  # (ts, bid)
        self._ask_buf = deque(maxlen=200)

    def feed(self, ts, bid, ask):
        self._bid_buf.append((ts, bid))
        self._ask_buf.append((ts, ask))

    def persistence_signal(self, persistence_ticks=5, mover_ticks=2):
        """Return +1 if bid persisted but ask moved up (accumulation),
        -1 if ask persisted but bid moved down (distribution)."""
        if len(self._bid_buf) < persistence_ticks + mover_ticks:
            return 0
        recent_bids = [b for _, b in list(self._bid_buf)[-(persistence_ticks + mover_ticks):]]
        recent_asks = [a for _, a in list(self._ask_buf)[-(persistence_ticks + mover_ticks):]]
        # bid persistence: last N bid values within 0.25pt of each other
        bid_segment = recent_bids[:persistence_ticks]
        if max(bid_segment) - min(bid_segment) <= 0.25:
            # ask moved up over the next mover_ticks
            ask_segment = recent_asks[-mover_ticks:]
            if min(ask_segment) - recent_asks[0] >= 0.5:
                return 1
        ask_segment = recent_asks[:persistence_ticks]
        if max(ask_segment) - min(ask_segment) <= 0.25:
            bid_segment = recent_bids[-mover_ticks:]
            if recent_bids[0] - max(bid_segment) >= 0.5:
                return -1
        return 0


BAP = BidAskPersistence()


class SwingHighLowTracker:
    """Track recent N-bar swing highs and lows for stop-cluster estimation
    (avenue D) and round-number distance (avenue E).

    Bars only change on bar-close, so cache results per lookback and
    invalidate on each feed_bar.
    """
    def __init__(self):
        self._bars = deque(maxlen=80)
        self._cache_hi = {}
        self._cache_lo = {}
        self._cache_rng = {}

    def feed_bar(self, o, h, l, c):
        self._bars.append((o, h, l, c))
        self._cache_hi.clear()
        self._cache_lo.clear()
        self._cache_rng.clear()

    def swing_high(self, lookback):
        cached = self._cache_hi.get(lookback)
        if cached is not None:
            return cached
        if not self._bars:
            return None
        # Iterate deque directly for last 'lookback' items
        n = min(lookback, len(self._bars))
        m = -1e18
        bars = self._bars
        # Walk from right by index
        for i in range(len(bars) - n, len(bars)):
            v = bars[i][1]
            if v > m: m = v
        self._cache_hi[lookback] = m
        return m

    def swing_low(self, lookback):
        cached = self._cache_lo.get(lookback)
        if cached is not None:
            return cached
        if not self._bars:
            return None
        n = min(lookback, len(self._bars))
        m = 1e18
        bars = self._bars
        for i in range(len(bars) - n, len(bars)):
            v = bars[i][2]
            if v < m: m = v
        self._cache_lo[lookback] = m
        return m

    def avg_range(self, lookback):
        cached = self._cache_rng.get(lookback)
        if cached is not None:
            return cached
        if not self._bars:
            return 0.0
        n = min(lookback, len(self._bars))
        total = 0.0
        bars = self._bars
        for i in range(len(bars) - n, len(bars)):
            total += bars[i][1] - bars[i][2]
        v = total / n
        self._cache_rng[lookback] = v
        return v


SWHL = SwingHighLowTracker()


# =============================================================================
# Avenue A. Reactive bracket switching
# =============================================================================
class ReactiveBracketStrategy(MarketablePullback):
    """Pullback entry, but if 30s pass without movement >= small_progress_pt,
    shrink the bracket to half (stop and target). After 60s, scratch at
    midpoint.

    We override r10_bot_on_tick's behavior indirectly: in_trade dict
    carries '_react_cfg' with the switch timings; we attach a per-tick
    monitor hook by overriding emit() to embed those in the setup extra.
    Then a per-strategy on_tick adjusts in_trade['stop'] / ['target']
    as time advances. The r10 executor reads the mutated dict on each
    tick, so changes take effect automatically.
    """
    def __init__(self, name, switch_s, shrink_factor, scratch_s, **kwargs):
        super().__init__(name, **kwargs)
        self.switch_s = switch_s
        self.shrink_factor = shrink_factor
        self.scratch_s = scratch_s


def react_postprocess(strat, ts):
    """Called every tick before r10_bot_on_tick to update in_trade bracket."""
    tr = strat.in_trade
    if tr is None:
        return
    cfg = tr.get('_react_cfg')
    if cfg is None:
        et = tr.get('et', ts)
        cfg = {
            'orig_stop': tr['stop'],
            'orig_target': tr['target'],
            'orig_entry': tr['entry'],
            'switch_s': strat.switch_s,
            'shrink_factor': strat.shrink_factor,
            'scratch_s': strat.scratch_s,
            'phase': 0,
            'et': et,
        }
        tr['_react_cfg'] = cfg
    age = ts - cfg['et']
    if cfg['phase'] == 0 and age >= cfg['switch_s']:
        # Shrink bracket
        side = tr['side']
        entry = cfg['orig_entry']
        if side == 'LONG':
            tgt_off = (cfg['orig_target'] - entry) * cfg['shrink_factor']
            stp_off = (entry - cfg['orig_stop']) * cfg['shrink_factor']
            tr['target'] = entry + tgt_off
            tr['stop'] = entry - stp_off
        else:
            tgt_off = (entry - cfg['orig_target']) * cfg['shrink_factor']
            stp_off = (cfg['orig_stop'] - entry) * cfg['shrink_factor']
            tr['target'] = entry - tgt_off
            tr['stop'] = entry + stp_off
        cfg['phase'] = 1
    if cfg['phase'] == 1 and age >= cfg['scratch_s']:
        # Scratch — set stop AND target both at entry midpoint
        side = tr['side']
        entry = cfg['orig_entry']
        if side == 'LONG':
            tr['target'] = entry + 0.25
            tr['stop'] = entry - 0.25
        else:
            tr['target'] = entry - 0.25
            tr['stop'] = entry + 0.25
        cfg['phase'] = 2


# =============================================================================
# Avenue B. Anti-stop-hunting placement
# =============================================================================
class AntiStopHuntPullback(MarketablePullback):
    """MarketablePullback but adds an extra non-standard offset to the stop
    so that stop level falls between round-number ticks. E.g. nominal
    stop at 30050, offset +0.37 -> stop at 30050.37 (not on a hunting
    grid).
    """
    def __init__(self, name, stop_offset_quirk, **kwargs):
        super().__init__(name, **kwargs)
        self.stop_offset_quirk = stop_offset_quirk

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        n_before = len(self.pending)
        super().on_bar_close(ts, hh, mn, bo, bh, bl, bc, hist)
        for s in self.pending[n_before:]:
            stop_off = s.get('stop_offset_pts')
            if stop_off is None:
                continue
            # Increase stop by quirk amount (further from entry by quirk pt)
            s['stop_offset_pts'] = stop_off + self.stop_offset_quirk
            # Re-write stop level if pre-computed
            side = s['side']
            entry = s['entry']
            if side == 'LONG':
                s['stop'] = entry - s['stop_offset_pts']
            else:
                s['stop'] = entry + s['stop_offset_pts']


# =============================================================================
# Avenue C. Micro-momentum cascades
# =============================================================================
class MicroMomentumCascade(_BaseEmitter):
    """Fire when all 5 timeframes (100ms..30s) align same direction."""
    def __init__(self, name, thresholds, stop_pts, target_pts, **kwargs):
        kwargs.setdefault('cooldown_s', 5)
        kwargs.setdefault('fill_mode', 'marketable')
        super().__init__(name, stop_pts, target_pts, **kwargs)
        self.thresholds = thresholds  # tuple of 5 floats
        self._last_signal_ts = 0.0

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        pass

    def feed_signal(self, ts, bid, ask):
        if ts - self._last_signal_ts < self.cooldown_s:
            return
        sign, n = MSM.alignment(self.thresholds)
        if sign == 0 or n < 4:
            return
        if sign > 0:
            self.emit(ts, 'LONG', ask, ('mmc', 'L', round(ts, 1)), expires_in=15)
        else:
            self.emit(ts, 'SHORT', bid, ('mmc', 'S', round(ts, 1)), expires_in=15)
        self._last_signal_ts = ts


# =============================================================================
# Avenue D. Stop-cluster fade
# =============================================================================
class StopClusterFade(_BaseEmitter):
    """Estimate stops sit ~cluster_offset pts above recent swing high
    (and below swing low). When price spikes through that level fast
    (spike_pts within 10s), place LIMIT-fade snap-back N pts away.
    """
    def __init__(self, name, cluster_offset, swing_lookback,
                 spike_pts, stop_pts, target_pts, **kwargs):
        kwargs.setdefault('cooldown_s', 30)
        kwargs.setdefault('fill_mode', 'limit')
        super().__init__(name, stop_pts, target_pts, **kwargs)
        self.cluster_offset = cluster_offset
        self.swing_lookback = swing_lookback
        self.spike_pts = spike_pts
        self._last_signal_ts = 0.0
        self._last_high_ts = 0.0
        self._last_high_px = None

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        pass

    def feed_signal(self, ts, bid, ask):
        if ts - self._last_signal_ts < self.cooldown_s:
            return
        sh = SWHL.swing_high(self.swing_lookback)
        sl = SWHL.swing_low(self.swing_lookback)
        if sh is None or sl is None:
            return
        last = (bid + ask) / 2.0
        # Stop cluster at sh + cluster_offset (long-stops above swing high)
        long_cluster = sh + self.cluster_offset
        short_cluster = sl - self.cluster_offset
        if last >= long_cluster and last - sh <= self.cluster_offset + self.spike_pts:
            # Spike through long stops — fade SHORT
            entry = last
            self.emit(ts, 'SHORT', entry - 1.0,
                      ('scf', 'S', round(ts, 0)), expires_in=30)
            self._last_signal_ts = ts
        elif last <= short_cluster and sl - last <= self.cluster_offset + self.spike_pts:
            entry = last
            self.emit(ts, 'LONG', entry + 1.0,
                      ('scf', 'L', round(ts, 0)), expires_in=30)
            self._last_signal_ts = ts


# =============================================================================
# Avenue E. Pinning / round-number magnet
# =============================================================================
class RoundNumberFade(_BaseEmitter):
    """Fade moves AWAY from nearest round-number grid in last hour of
    session. If price is moving away from nearest 25/50/100-pt level
    by >= magnet_pts and we're in session window, fade back to it.
    """
    def __init__(self, name, grid_size, magnet_pts,
                 stop_pts, target_pts, **kwargs):
        kwargs.setdefault('cooldown_s', 60)
        kwargs.setdefault('fill_mode', 'marketable')
        super().__init__(name, stop_pts, target_pts, **kwargs)
        self.grid_size = grid_size
        self.magnet_pts = magnet_pts
        self._last_signal_ts = 0.0

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        pass

    def feed_signal(self, ts, bid, ask):
        if ts - self._last_signal_ts < self.cooldown_s:
            return
        last = (bid + ask) / 2.0
        nearest = round(last / self.grid_size) * self.grid_size
        dist = last - nearest
        if abs(dist) < self.magnet_pts:
            return
        if dist > 0:
            # price above grid — fade SHORT back toward grid
            self.emit(ts, 'SHORT', bid, ('pin', 'S', round(ts, 0)), expires_in=120)
        else:
            self.emit(ts, 'LONG', ask, ('pin', 'L', round(ts, 0)), expires_in=120)
        self._last_signal_ts = ts


# =============================================================================
# Avenue F. Anti-correlation morning/afternoon
# =============================================================================
class HourlyBiasPullback(MarketablePullback):
    """Override invert based on hour-of-day vs configured bias_long_hours."""
    def __init__(self, name, bias_long_hours, **kwargs):
        super().__init__(name, **kwargs)
        self.bias_long_hours = set(bias_long_hours)

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        # Choose direction based on hour
        if hh in self.bias_long_hours:
            self.invert = False  # follow impulse
        else:
            self.invert = True
        super().on_bar_close(ts, hh, mn, bo, bh, bl, bc, hist)


# =============================================================================
# Avenue G. Multi-frequency Fourier signal
# =============================================================================
class FFTCycleStrategy(_BaseEmitter):
    """Identify dominant cycle via DFT, fire on 1/4-cycle phase reversal.
    Pure-python DFT (small window).
    """
    def __init__(self, name, fft_window, period_min, period_max,
                 stop_pts, target_pts, **kwargs):
        kwargs.setdefault('cooldown_s', 30)
        kwargs.setdefault('fill_mode', 'marketable')
        super().__init__(name, stop_pts, target_pts, **kwargs)
        self.fft_window = fft_window
        self.period_min = period_min
        self.period_max = period_max
        self._bars = deque(maxlen=fft_window)
        self._last_signal_ts = 0.0

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        self._bars.append(bc)
        if len(self._bars) < self.fft_window:
            return
        if ts - self._last_signal_ts < self.cooldown_s:
            return
        # Compute DFT power for periods in [period_min..period_max]
        x = list(self._bars)
        N = len(x)
        mean = sum(x) / N
        x = [v - mean for v in x]
        best_p = None
        best_power = 0.0
        for p in range(self.period_min, self.period_max + 1):
            # k corresponds to period p: k = N / p
            k = N / p
            re = 0.0; im = 0.0
            for n in range(N):
                ang = -2 * math.pi * k * n / N
                re += x[n] * math.cos(ang)
                im += x[n] * math.sin(ang)
            power = re * re + im * im
            if power > best_power:
                best_power = power
                best_p = p
        if best_p is None:
            return
        # Phase: last bar relative to cycle.
        # If x[-1] > 0 and turning (peak), fire SHORT (cycle expects retrace)
        # If x[-1] < 0 and turning (trough), fire LONG.
        # Approx turning by sign of (x[-1] - x[-2])
        if len(x) < 3:
            return
        dx = x[-1] - x[-2]
        last_mean_dev = x[-1]
        if last_mean_dev > 0 and dx < 0:
            self.emit(ts, 'SHORT', x[-1] + mean,
                      ('fft', 'S', round(ts, 0)), expires_in=120)
            self._last_signal_ts = ts
        elif last_mean_dev < 0 and dx > 0:
            self.emit(ts, 'LONG', x[-1] + mean,
                      ('fft', 'L', round(ts, 0)), expires_in=120)
            self._last_signal_ts = ts


# =============================================================================
# Avenue H. Wavelet decomposition entries
# =============================================================================
class WaveletAlignStrategy(_BaseEmitter):
    """Compute simple Haar wavelet at 5 scales (5,15,60,240,960 bars on
    1m grid) and fire when M of 5 scales agree on direction.
    """
    SCALES = (5, 15, 60, 240, 960)

    def __init__(self, name, n_agree, stop_pts, target_pts, **kwargs):
        kwargs.setdefault('cooldown_s', 60)
        kwargs.setdefault('fill_mode', 'marketable')
        super().__init__(name, stop_pts, target_pts, **kwargs)
        self.n_agree = n_agree
        self._bars = deque(maxlen=max(self.SCALES))
        self._last_signal_ts = 0.0

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        self._bars.append(bc)
        if len(self._bars) < self.SCALES[2]:
            return
        if ts - self._last_signal_ts < self.cooldown_s:
            return
        signs = []
        for sc in self.SCALES:
            if len(self._bars) < sc:
                continue
            sub = list(self._bars)[-sc:]
            half = sc // 2
            avg_first = sum(sub[:half]) / half
            avg_last = sum(sub[half:]) / (sc - half)
            delta = avg_last - avg_first
            signs.append(1 if delta > 0 else (-1 if delta < 0 else 0))
        n_pos = sum(1 for s in signs if s > 0)
        n_neg = sum(1 for s in signs if s < 0)
        if n_pos >= self.n_agree:
            self.emit(ts, 'LONG', bc, ('wav', 'L', round(ts, 0)),
                      expires_in=180)
            self._last_signal_ts = ts
        elif n_neg >= self.n_agree:
            self.emit(ts, 'SHORT', bc, ('wav', 'S', round(ts, 0)),
                      expires_in=180)
            self._last_signal_ts = ts


# =============================================================================
# Avenue I. Bid-ask interaction depth
# =============================================================================
class BidAskInteractionStrategy(_BaseEmitter):
    def __init__(self, name, persistence, mover, stop_pts, target_pts, **kwargs):
        kwargs.setdefault('cooldown_s', 5)
        kwargs.setdefault('fill_mode', 'marketable')
        super().__init__(name, stop_pts, target_pts, **kwargs)
        self.persistence = persistence
        self.mover = mover
        self._last_signal_ts = 0.0

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        pass

    def feed_signal(self, ts, bid, ask):
        if ts - self._last_signal_ts < self.cooldown_s:
            return
        sig = BAP.persistence_signal(self.persistence, self.mover)
        if sig > 0:
            self.emit(ts, 'LONG', ask, ('bap', 'L', round(ts, 1)), expires_in=10)
            self._last_signal_ts = ts
        elif sig < 0:
            self.emit(ts, 'SHORT', bid, ('bap', 'S', round(ts, 1)), expires_in=10)
            self._last_signal_ts = ts


# =============================================================================
# Avenue J. Volume vacuum straddle
# =============================================================================
class VolumeVacuumStrategy(_BaseEmitter):
    """Detect drop in tick rate, place straddle."""
    def __init__(self, name, ratio_threshold, det_window_s, straddle_pts,
                 stop_pts, target_pts, **kwargs):
        kwargs.setdefault('cooldown_s', 60)
        kwargs.setdefault('fill_mode', 'stop')
        super().__init__(name, stop_pts, target_pts, **kwargs)
        self.ratio_threshold = ratio_threshold
        self.det_window_s = det_window_s
        self.straddle_pts = straddle_pts
        self._last_signal_ts = 0.0

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        pass

    def feed_signal(self, ts, bid, ask):
        if ts - self._last_signal_ts < self.cooldown_s:
            return
        recent_rate = TICK_RATE.rate(self.det_window_s, ts)
        normal_rate = TICK_RATE.rate(120.0, ts)
        if normal_rate < 1.0:
            return
        if recent_rate / normal_rate > self.ratio_threshold:
            return
        mid = (bid + ask) / 2.0
        cohort = ('vac', round(ts, 0))
        e_l = mid + self.straddle_pts
        extra_l = {'fill_mode': 'stop', 'stop_offset_pts': self.stop_pts,
                   'target_offset_pts': self.target_pts,
                   'exit_mode': 'stop_market', 'cohort': cohort, '_gen_ts': ts}
        self.add_setup('LONG', 'LONG', e_l, e_l - self.stop_pts,
                       e_l + self.target_pts, ts,
                       key=('vacL', round(ts, 0)),
                       expires_in=60, extra=extra_l)
        e_s = mid - self.straddle_pts
        extra_s = {'fill_mode': 'stop', 'stop_offset_pts': self.stop_pts,
                   'target_offset_pts': self.target_pts,
                   'exit_mode': 'stop_market', 'cohort': cohort, '_gen_ts': ts}
        self.add_setup('SHORT', 'SHORT', e_s, e_s + self.stop_pts,
                       e_s - self.target_pts, ts,
                       key=('vacS', round(ts, 0)),
                       expires_in=60, extra=extra_s)
        self._last_signal_ts = ts


# =============================================================================
# Avenue K. Cross-tick momentum at sub-100ms
# =============================================================================
class _SharedSubTickBuf:
    """Single shared buffer for all SubHundredMs strategies. They look up
    a cached anchor price per window_s via the gauge instead of each
    keeping its own deque.
    """
    def __init__(self):
        self._buf = deque(maxlen=600)  # (ts, last)
        self._cache = {}  # window_s -> (last_ts, anchor)

    def feed(self, ts, last):
        self._buf.append((ts, last))

    def anchor(self, window_s, now_ts):
        c = self._cache.get(window_s)
        if c is not None and now_ts - c[0] < 0.02:  # ~20ms cache
            return c[1]
        cutoff = now_ts - window_s
        anchor = None
        for t, p in self._buf:
            if t >= cutoff:
                anchor = p
                break
        self._cache[window_s] = (now_ts, anchor)
        return anchor


SUB_TICK_BUF = _SharedSubTickBuf()


class SubHundredMsMomentum(_BaseEmitter):
    """Pure microstructure: look at every Wms net delta. Fire on extreme
    intra-W ms moves of >=N ticks.
    """
    def __init__(self, name, window_ms, threshold_ticks,
                 stop_pts, target_pts, **kwargs):
        kwargs.setdefault('cooldown_s', 0.5)
        kwargs.setdefault('fill_mode', 'marketable')
        super().__init__(name, stop_pts, target_pts, **kwargs)
        self.window_s = window_ms / 1000.0
        self.threshold_pts = threshold_ticks * TICK
        self._last_signal_ts = 0.0

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        pass

    def feed_signal(self, ts, bid, ask):
        last = (bid + ask) / 2.0
        if ts - self._last_signal_ts < self.cooldown_s:
            return
        anchor = SUB_TICK_BUF.anchor(self.window_s, ts)
        if anchor is None:
            return
        delta = last - anchor
        if abs(delta) < self.threshold_pts:
            return
        # FOLLOW (momentum, not fade)
        if delta > 0:
            self.emit(ts, 'LONG', ask, ('shm', 'L', round(ts, 2)),
                      expires_in=5)
        else:
            self.emit(ts, 'SHORT', bid, ('shm', 'S', round(ts, 2)),
                      expires_in=5)
        self._last_signal_ts = ts


# =============================================================================
# Avenue L. Bayesian momentum
# =============================================================================
class BayesianMomentum(_BaseEmitter):
    """Compute exponentially-weighted P(LONG) over last N bars.
    P = sigma(sum_i w_i * sign(close_i - close_{i-1}))
    Fire when P > threshold or < 1-threshold.
    """
    def __init__(self, name, n_bars, decay, p_threshold,
                 stop_pts, target_pts, **kwargs):
        kwargs.setdefault('cooldown_s', 30)
        kwargs.setdefault('fill_mode', 'marketable')
        super().__init__(name, stop_pts, target_pts, **kwargs)
        self.n_bars = n_bars
        self.decay = decay
        self.p_threshold = p_threshold
        self._bars = deque(maxlen=n_bars + 1)
        self._last_signal_ts = 0.0

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        self._bars.append(bc)
        if len(self._bars) < self.n_bars + 1:
            return
        if ts - self._last_signal_ts < self.cooldown_s:
            return
        bars = list(self._bars)
        s = 0.0
        w = 1.0
        wsum = 0.0
        for i in range(len(bars) - 1, 0, -1):
            d = bars[i] - bars[i-1]
            sgn = 1 if d > 0 else (-1 if d < 0 else 0)
            s += w * sgn
            wsum += w
            w *= self.decay
        # sigmoid
        z = s / max(0.001, wsum)
        p = 1.0 / (1.0 + math.exp(-3.0 * z))
        if p >= self.p_threshold:
            self.emit(ts, 'LONG', bc, ('bmo', 'L', round(ts, 0)), expires_in=120)
            self._last_signal_ts = ts
        elif p <= 1.0 - self.p_threshold:
            self.emit(ts, 'SHORT', bc, ('bmo', 'S', round(ts, 0)), expires_in=120)
            self._last_signal_ts = ts


# =============================================================================
# Avenue M. Markov state classifier
# =============================================================================
class MarkovStateStrategy(_BaseEmitter):
    """Discretize state into {bull, bear, choppy, transition} via
    realized return + std over last N bars. Maintain transition counts.
    Fire LONG when prob(bull next) >= threshold; SHORT on bear.
    """
    STATES = ('bull', 'bear', 'choppy', 'trans')

    def __init__(self, name, state_window, threshold,
                 stop_pts, target_pts, **kwargs):
        kwargs.setdefault('cooldown_s', 60)
        kwargs.setdefault('fill_mode', 'marketable')
        super().__init__(name, stop_pts, target_pts, **kwargs)
        self.state_window = state_window
        self.threshold = threshold
        self._bars = deque(maxlen=state_window + 5)
        # transition counts: dict[(from, to)] -> n
        self._trans = defaultdict(int)
        self._last_state = None
        self._last_signal_ts = 0.0

    def _classify(self, bars):
        if len(bars) < 3:
            return None
        rets = [bars[i] - bars[i-1] for i in range(1, len(bars))]
        net = bars[-1] - bars[0]
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / len(rets)
        std = math.sqrt(var)
        # rule of thumb
        if abs(net) > 4 * std and abs(net) > 1.0:
            return 'bull' if net > 0 else 'bear'
        if std < 0.4:
            return 'choppy'
        return 'trans'

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        self._bars.append(bc)
        if len(self._bars) < self.state_window:
            return
        sub = list(self._bars)[-self.state_window:]
        cur = self._classify(sub)
        if cur is None:
            return
        if self._last_state is not None and cur != self._last_state:
            self._trans[(self._last_state, cur)] += 1
        self._last_state = cur
        if ts - self._last_signal_ts < self.cooldown_s:
            return
        # Compute transition prob from cur to {bull, bear}
        total_from_cur = sum(n for (a, b), n in self._trans.items() if a == cur)
        if total_from_cur < 5:
            return
        p_bull = self._trans.get((cur, 'bull'), 0) / total_from_cur
        p_bear = self._trans.get((cur, 'bear'), 0) / total_from_cur
        if p_bull >= self.threshold:
            self.emit(ts, 'LONG', bc, ('mkv', 'L', round(ts, 0)), expires_in=120)
            self._last_signal_ts = ts
        elif p_bear >= self.threshold:
            self.emit(ts, 'SHORT', bc, ('mkv', 'S', round(ts, 0)), expires_in=120)
            self._last_signal_ts = ts


# =============================================================================
# Avenue N. Time-of-day micro-strategies
# =============================================================================
class WindowedPullback(MarketablePullback):
    """Only fire during a single 15-minute window of the day."""
    def __init__(self, name, window_hh, window_mn, **kwargs):
        kwargs.setdefault('session_start', (window_hh, window_mn))
        # end = (hh, mn+15) clamped
        mn_end = window_mn + 15
        hh_end = window_hh
        if mn_end >= 60:
            mn_end -= 60
            hh_end = (hh_end + 1) % 24
        kwargs.setdefault('session_end', (hh_end, mn_end))
        super().__init__(name, **kwargs)


# =============================================================================
# Avenue O. Stochastic strategy generation (random sample of MTF variants)
# =============================================================================
def build_stochastic_variants(n, rng):
    out = []
    for i in range(n):
        pp = rng.uniform(0.05, 0.8)
        imp = rng.uniform(2.0, 15.0)
        bars = rng.randint(2, 10)
        stp = rng.randint(1, 25)
        tgt = rng.randint(3, 60)
        cd = rng.randint(1, 30)
        if tgt <= stp:
            continue
        inv = rng.random() < 0.5
        # session choice
        ses_choice = rng.randint(0, 4)
        if ses_choice == 0:
            ses_start = None; ses_end = None; ses_name = 'all'
        elif ses_choice == 1:
            ses_start = (13, 30); ses_end = (15, 30); ses_name = 'NYO'
        elif ses_choice == 2:
            ses_start = (13, 30); ses_end = (20, 0); ses_name = 'RTH'
        elif ses_choice == 3:
            ses_start = (22, 0); ses_end = (5, 0); ses_name = 'CME'
        else:
            ses_start = (8, 0); ses_end = (12, 0); ses_name = 'LDN'
        name = (f"O_RND_{i:04d}_imp{imp:.1f}_b{bars}_s{stp}_t{tgt}_"
                f"pp{int(pp*1000)}_cd{cd}_{ses_name}_{'INV' if inv else 'TRD'}")
        try:
            s = MTFConfluence(
                name, impulse_pts=imp, impulse_bars=bars,
                pull_pct=pp, stop_pts=stp, target_pts=tgt, invert=inv,
                cooldown_s=cd, session_start=ses_start, session_end=ses_end)
            out.append(s)
        except Exception:
            continue
    return out


# =============================================================================
# Avenue P. Reactive position sizing (confidence gate)
# =============================================================================
class ConfidenceGatedPullback(MarketablePullback):
    """Same as MarketablePullback but skips entries when recent N-trade
    WR drops below threshold.
    """
    def __init__(self, name, gate_window, wr_threshold, **kwargs):
        super().__init__(name, **kwargs)
        self.gate_window = gate_window
        self.wr_threshold = wr_threshold

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        # check recent WR
        if self.n_trades >= self.gate_window:
            recent = self.completed[-self.gate_window:]
            wr = sum(1 for c in recent if c[0] > 0) / self.gate_window
            if wr < self.wr_threshold:
                return  # skip generating new setups
        super().on_bar_close(ts, hh, mn, bo, bh, bl, bc, hist)


# =============================================================================
# Avenue Q. Liquidity vacuum + speed-of-tape combo
# =============================================================================
class VacuumPlusTapeStrategy(_BaseEmitter):
    """Fire only when BOTH conditions within 2s:
       1. tape rate spike >= mult x baseline
       2. then tick rate drops to vacuum_ratio
    """
    def __init__(self, name, tape_mult, vacuum_ratio,
                 stop_pts, target_pts, **kwargs):
        kwargs.setdefault('cooldown_s', 30)
        kwargs.setdefault('fill_mode', 'marketable')
        super().__init__(name, stop_pts, target_pts, **kwargs)
        self.tape_mult = tape_mult
        self.vacuum_ratio = vacuum_ratio
        self._spike_ts = -1e9
        self._last_signal_ts = 0.0

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        pass

    def feed_signal(self, ts, bid, ask):
        ratio = _r10.TAPE.ratio()
        if ratio >= self.tape_mult:
            self._spike_ts = ts
        if ts - self._spike_ts > 2.0:
            return
        if ts - self._last_signal_ts < self.cooldown_s:
            return
        rec = TICK_RATE.rate(2.0, ts)
        norm = TICK_RATE.rate(60.0, ts)
        if norm < 1.0:
            return
        if rec / norm > self.vacuum_ratio:
            return
        # FOLLOW the spike direction
        last = (bid + ask) / 2.0
        # Use last few-tick delta from MSM
        sign, _ = MSM.alignment((0.5, 0.5, 0.5, 0.5, 0.5))
        if sign == 0:
            return
        if sign > 0:
            self.emit(ts, 'LONG', ask, ('vt', 'L', round(ts, 0)), expires_in=10)
        else:
            self.emit(ts, 'SHORT', bid, ('vt', 'S', round(ts, 0)), expires_in=10)
        self._last_signal_ts = ts


# =============================================================================
# Avenue R. Pre-bar formation prediction
# =============================================================================
class PreBarPrediction(_BaseEmitter):
    """At fraction f of a 60s bar, predict close from current OHLC progression.
    If predicted close > prior close + threshold, fire LONG.
    """
    def __init__(self, name, fraction, threshold_pts,
                 stop_pts, target_pts, **kwargs):
        kwargs.setdefault('cooldown_s', 30)
        kwargs.setdefault('fill_mode', 'marketable')
        super().__init__(name, stop_pts, target_pts, **kwargs)
        self.fraction = fraction
        self.threshold_pts = threshold_pts
        self._cur_bar = None  # (start_ts, prior_close, opening, lo, hi, last_seen)
        self._last_signal_ts = 0.0

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        # Reset current bar
        self._cur_bar = (ts, bc, bc, bc, bc, bc)

    def feed_signal(self, ts, bid, ask):
        if self._cur_bar is None:
            return
        start_ts, prior_close, o, lo, hi, last = self._cur_bar
        last = (bid + ask) / 2.0
        if last > hi: hi = last
        if last < lo: lo = last
        self._cur_bar = (start_ts, prior_close, o, lo, hi, last)
        # check fraction
        elapsed = ts - start_ts
        if elapsed < 60 * self.fraction or elapsed > 60.0:
            return
        if ts - self._last_signal_ts < self.cooldown_s:
            return
        # predicted close = current last (linear extrapolation)
        pred_delta = last - prior_close
        if pred_delta >= self.threshold_pts:
            self.emit(ts, 'LONG', ask, ('pre', 'L', round(ts, 0)), expires_in=30)
            self._last_signal_ts = ts
        elif pred_delta <= -self.threshold_pts:
            self.emit(ts, 'SHORT', bid, ('pre', 'S', round(ts, 0)), expires_in=30)
            self._last_signal_ts = ts


# =============================================================================
# Avenue S. Optimal stopping (Bellman approx)
# =============================================================================
class OptimalStoppingPullback(MarketablePullback):
    """Standard MarketablePullback entry but dynamic exit: exit early if
    current P&L > E[future P&L]. Approximation: exit when in profit AND
    velocity (last 5s tick delta) reverses direction.
    """
    def __init__(self, name, profit_lock_pts, reverse_pts, **kwargs):
        super().__init__(name, **kwargs)
        self.profit_lock_pts = profit_lock_pts
        self.reverse_pts = reverse_pts


def optimal_stop_postprocess(strat, ts, bid, ask):
    tr = strat.in_trade
    if tr is None:
        return
    side = tr['side']
    entry = tr['entry']
    last = (bid + ask) / 2.0
    pnl = (last - entry) if side == 'LONG' else (entry - last)
    if pnl < strat.profit_lock_pts:
        return
    # Get sub-second momentum to test reversal
    sign, _ = MSM.alignment((0.25, 0.25, 0.25, 1.0, 1.0))
    if side == 'LONG' and sign < 0:
        # reverse — tighten stop to entry + (pnl - reverse_pts)
        new_stop = entry + max(0.0, pnl - strat.reverse_pts)
        if new_stop > tr['stop']:
            tr['stop'] = new_stop
    elif side == 'SHORT' and sign > 0:
        new_stop = entry - max(0.0, pnl - strat.reverse_pts)
        if new_stop < tr['stop']:
            tr['stop'] = new_stop


# =============================================================================
# Avenue T. Massive 9,000-variant Latin sweep on top-3 base strategies
# =============================================================================
def latin_hypercube_sample(n, dims, rng):
    bins = [list(range(len(d))) for d in dims]
    perms = []
    for b in bins:
        seq = []
        while len(seq) < n:
            x = list(b)
            rng.shuffle(x)
            seq.extend(x)
        perms.append(seq[:n])
    for i in range(n):
        yield tuple(dims[di][perms[di][i]] for di in range(len(dims)))


def build_t_sweep(rng, n_per_base=3000):
    """For each of 3 base strategies, sweep 8+ dims via Latin hypercube."""
    out = []
    dims = [
        [2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0],          # impulse
        [2, 3, 4, 5, 6, 8],                                   # bars
        [3, 4, 5, 6, 7, 8, 9, 10, 12, 15],                    # stop
        [8, 12, 16, 20, 24, 28, 32, 36, 40, 50],              # target
        [0.118, 0.236, 0.300, 0.382, 0.450, 0.500, 0.618, 0.764],  # pp
        [3, 5, 10, 15, 20, 30],                                 # cooldown
        [None, 60, 120, 240, 600],                              # max_hold (None=default 600)
        [('all', None, None),
         ('NYO', (13, 30), (15, 30)),
         ('OVR', (13, 30), (16, 0)),
         ('RTH', (13, 30), (20, 0)),
         ('CME', (22, 0), (5, 0)),
         ('PRE', (12, 0), (13, 30)),
         ('AFT', (16, 0), (20, 0)),
         ('LDN', (8, 0), (12, 0))],
    ]
    for combo_idx, combo in enumerate(
            latin_hypercube_sample(n_per_base * 3, dims, rng)):
        imp, bars, stp, tgt, pp, cd, mh, ses = combo
        if tgt <= stp:
            continue
        ses_name, ses_start, ses_end = ses
        which_base = combo_idx % 3
        if which_base == 0:
            cls = MTFConfluence
            base_tag = 'R10BASE'
            inv = True
        elif which_base == 1:
            cls = MarketablePullback
            base_tag = 'CANONINV'
            inv = True
        else:
            cls = MTFConfluence
            base_tag = 'R4INV'
            inv = True
        kwargs = dict(impulse_pts=float(imp), impulse_bars=int(bars),
                      pull_pct=float(pp), stop_pts=int(stp),
                      target_pts=int(tgt), invert=inv, cooldown_s=int(cd),
                      session_start=ses_start, session_end=ses_end)
        if mh is not None:
            kwargs['max_hold'] = mh
        name = (f"T_LH_{base_tag}_imp{int(imp)}_b{bars}_s{stp}_t{tgt}_"
                f"pp{int(pp*1000)}_cd{cd}_mh{mh if mh else 'd'}_{ses_name}")
        try:
            s = cls(name, **kwargs)
            out.append(s)
        except Exception:
            continue
        if len(out) >= n_per_base * 3:
            break
    return out


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
        print(f"[round12] checkpoint load failed: {e!r}", file=sys.stderr)
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
    return (int(state["offset"]),
            int(state["day_counter"]),
            state["last_day_key"])


# =============================================================================
# BUILD ALL VARIANTS
# =============================================================================
def build_all_variants(quick=False, t_sweep=3000):
    """Build all variants across 20 avenues. Returns (v1m, vtick, all_strats).

    'v1m' fires on 1-minute bar close; 'vtick' on every tick.
    """
    v1m = []
    vtick = []
    rng = random.Random(0xCAFEBABE)

    # ---- A. Reactive bracket switching (1,920 → cap 480) ----
    BR_PAIRS = [(5, 10), (5, 15), (8, 16), (8, 24), (10, 20), (10, 30),
                (12, 24), (15, 30)]
    SWITCH_S = [15, 30, 60, 120]
    SHRINK = [0.5, 0.33]
    SCRATCH_S = [60, 120]
    INV = [True, False]
    A_count = 0
    for stp, tgt in BR_PAIRS:
        for sw in SWITCH_S:
            for sf in SHRINK:
                for sc in SCRATCH_S:
                    for inv in INV:
                        name = (f"A_REACT_s{stp}t{tgt}_sw{sw}_sf{int(sf*100)}_"
                                f"sc{sc}_{'INV' if inv else 'TRD'}")
                        s = ReactiveBracketStrategy(
                            name, switch_s=sw, shrink_factor=sf, scratch_s=sc,
                            impulse_pts=5.0, impulse_bars=4, pull_pct=0.382,
                            stop_pts=stp, target_pts=tgt, invert=inv)
                        v1m.append(s)
                        A_count += 1
    # cap if needed
    if A_count > 480 and not quick:
        v1m = v1m[:480]

    # ---- B. Anti-stop-hunting offsets ----
    OFFSETS = [0.13, 0.37, 0.63, 0.87, 1.13, 1.37]
    BASES = [(5.0, 4, 0.236, 10, 20),
             (4.0, 3, 0.382, 8, 24),
             (5.0, 4, 0.500, 5, 20),
             (5.0, 3, 0.300, 8, 30),
             (4.0, 3, 0.450, 6, 24),
             (5.0, 4, 0.118, 4, 16),
             (6.0, 4, 0.382, 10, 30),
             (4.0, 4, 0.500, 6, 18)]
    for off in OFFSETS:
        for (imp, bars, pp, stp, tgt) in BASES:
            for inv in INV:
                name = (f"B_ASH_off{int(off*100)}_imp{int(imp)}_b{bars}_"
                        f"pp{int(pp*1000)}_s{stp}t{tgt}_{'INV' if inv else 'TRD'}")
                s = AntiStopHuntPullback(
                    name, stop_offset_quirk=off,
                    impulse_pts=imp, impulse_bars=bars, pull_pct=pp,
                    stop_pts=stp, target_pts=tgt, invert=inv)
                v1m.append(s)
    # 6*8*2 = 96 variants

    # ---- C. Micro-momentum cascade ----
    THR_COMBOS = [
        (0.25, 0.25, 0.5, 1.0, 2.0),
        (0.25, 0.5, 1.0, 2.0, 4.0),
        (0.5, 1.0, 2.0, 3.0, 5.0),
        (0.25, 0.25, 0.25, 1.0, 2.0),
        (0.5, 0.5, 1.0, 1.5, 3.0),
        (0.25, 0.5, 0.5, 2.0, 4.0),
    ]
    RR_C = [(1, 2), (2, 4), (2, 6), (3, 6), (3, 9), (4, 8)]
    for ti, thr in enumerate(THR_COMBOS):
        for stp, tgt in RR_C:
            for ses_choice in range(4):
                if ses_choice == 0:
                    ses_start, ses_end, ses_name = None, None, 'all'
                elif ses_choice == 1:
                    ses_start, ses_end, ses_name = (13, 30), (20, 0), 'RTH'
                elif ses_choice == 2:
                    ses_start, ses_end, ses_name = (22, 0), (5, 0), 'CME'
                else:
                    ses_start, ses_end, ses_name = (8, 0), (13, 30), 'LDN'
                name = (f"C_MMC_t{ti}_s{stp}t{tgt}_{ses_name}")
                s = MicroMomentumCascade(
                    name, thresholds=thr, stop_pts=stp, target_pts=tgt,
                    session_start=ses_start, session_end=ses_end)
                vtick.append(s)
    # 6*6*4 = 144

    # ---- D. Stop-cluster fade ----
    for off in [4, 6, 8, 10, 12]:
        for sw in [10, 20, 40, 60]:
            for sp in [2.0, 3.5, 5.0]:
                for stp, tgt in [(3, 9), (4, 12), (5, 15), (6, 18), (8, 24)]:
                    name = (f"D_SCF_off{off}_sw{sw}_sp{int(sp*10)}_s{stp}t{tgt}")
                    s = StopClusterFade(
                        name, cluster_offset=off, swing_lookback=sw,
                        spike_pts=sp, stop_pts=stp, target_pts=tgt)
                    vtick.append(s)
    # 5*4*3*5 = 300

    # ---- E. Pinning / round-number ----
    for grid in [25, 50, 100]:
        for mag in [3, 5, 8, 12]:
            for stp, tgt in [(3, 9), (4, 12), (5, 15), (6, 18), (8, 24), (10, 30)]:
                for ses_choice in range(3):
                    if ses_choice == 0:
                        ses_start, ses_end, ses_name = (13, 30), (14, 0), 'POSTNYSE'
                    elif ses_choice == 1:
                        ses_start, ses_end, ses_name = (19, 0), (20, 0), 'PRENYC'
                    else:
                        ses_start, ses_end, ses_name = (3, 45), (4, 45), 'PRELDN'
                    name = (f"E_PIN_g{grid}_m{mag}_s{stp}t{tgt}_{ses_name}")
                    s = RoundNumberFade(
                        name, grid_size=grid, magnet_pts=mag,
                        stop_pts=stp, target_pts=tgt,
                        session_start=ses_start, session_end=ses_end)
                    vtick.append(s)
    # 3*4*6*3 = 216

    # ---- F. Hourly bias ----
    # Build 24 hourly-LONG-bias variants + INV
    HOUR_GROUPS = [
        (set([13, 14, 15]), 'morn'),
        (set([16, 17, 18, 19]), 'aft'),
        (set([22, 23, 0, 1]), 'asia'),
        (set([5, 6, 7, 8]), 'preldn'),
        (set([8, 9, 10, 11, 12]), 'ldn'),
        (set([13, 14, 15, 16, 17, 18, 19]), 'us'),
        (set(range(0, 12)), 'eu'),
    ]
    F_BASES = [(5.0, 4, 0.236, 10, 20), (4.0, 3, 0.382, 8, 24),
               (5.0, 3, 0.300, 8, 30), (5.0, 4, 0.500, 5, 20)]
    for hg, hname in HOUR_GROUPS:
        for (imp, bars, pp, stp, tgt) in F_BASES:
            name = f"F_HB_{hname}_imp{int(imp)}_b{bars}_s{stp}t{tgt}"
            s = HourlyBiasPullback(
                name, bias_long_hours=hg,
                impulse_pts=imp, impulse_bars=bars, pull_pct=pp,
                stop_pts=stp, target_pts=tgt, invert=False)
            v1m.append(s)
    # 7*4 = 28

    # ---- G. FFT cycle ----
    for fft_w in [30, 60, 120, 240]:
        for (pmin, pmax) in [(3, 7), (8, 15), (16, 30)]:
            for stp, tgt in [(4, 12), (5, 15), (6, 18), (8, 24), (10, 30), (12, 36)]:
                if pmax > fft_w // 2:
                    continue
                name = f"G_FFT_w{fft_w}_p{pmin}-{pmax}_s{stp}t{tgt}"
                s = FFTCycleStrategy(
                    name, fft_window=fft_w, period_min=pmin, period_max=pmax,
                    stop_pts=stp, target_pts=tgt)
                v1m.append(s)
    # ~4*3*6 = 72

    # ---- H. Wavelet ----
    for na in [3, 4, 5]:
        for stp, tgt in [(4, 12), (5, 15), (6, 18), (8, 24), (10, 30), (12, 36),
                         (15, 45), (20, 60)]:
            for ses_choice in range(3):
                if ses_choice == 0:
                    ses_start, ses_end, ses_name = None, None, 'all'
                elif ses_choice == 1:
                    ses_start, ses_end, ses_name = (13, 30), (20, 0), 'RTH'
                else:
                    ses_start, ses_end, ses_name = (22, 0), (5, 0), 'CME'
                name = f"H_WAV_a{na}_s{stp}t{tgt}_{ses_name}"
                s = WaveletAlignStrategy(
                    name, n_agree=na, stop_pts=stp, target_pts=tgt,
                    session_start=ses_start, session_end=ses_end)
                v1m.append(s)
    # 3*8*3 = 72

    # ---- I. Bid-ask interaction ----
    for per in [3, 5, 8, 12]:
        for mov in [2, 4, 6]:
            for stp, tgt in [(2, 4), (3, 6), (4, 8), (5, 10), (6, 12), (8, 16)]:
                name = f"I_BAP_p{per}_m{mov}_s{stp}t{tgt}"
                s = BidAskInteractionStrategy(
                    name, persistence=per, mover=mov,
                    stop_pts=stp, target_pts=tgt)
                vtick.append(s)
    # 4*3*6 = 72

    # ---- J. Volume vacuum straddle ----
    for r in [0.5, 0.3, 0.1]:
        for win in [10, 30, 60]:
            for sw in [3, 5, 8]:
                for stp, tgt in [(3, 9), (5, 15), (8, 24), (10, 30)]:
                    name = f"J_VAC_r{int(r*100)}_w{win}_sw{sw}_s{stp}t{tgt}"
                    s = VolumeVacuumStrategy(
                        name, ratio_threshold=r, det_window_s=win,
                        straddle_pts=sw, stop_pts=stp, target_pts=tgt)
                    vtick.append(s)
    # 3*3*3*4 = 108

    # ---- K. Sub-100ms momentum ----
    for win_ms in [50, 100, 250, 500]:
        for ticks in [2, 3, 4, 5]:
            for stp, tgt in [(0.5, 1.0), (0.75, 1.5), (1.0, 2.0),
                             (1.5, 3.0), (2.0, 4.0), (2.5, 5.0)]:
                for ses_choice in range(3):
                    if ses_choice == 0:
                        ses_start, ses_end, ses_name = None, None, 'all'
                    elif ses_choice == 1:
                        ses_start, ses_end, ses_name = (13, 30), (20, 0), 'RTH'
                    else:
                        ses_start, ses_end, ses_name = (22, 0), (5, 0), 'CME'
                    name = f"K_SHM_w{win_ms}_t{ticks}_s{int(stp*10)}t{int(tgt*10)}_{ses_name}"
                    s = SubHundredMsMomentum(
                        name, window_ms=win_ms, threshold_ticks=ticks,
                        stop_pts=stp, target_pts=tgt,
                        session_start=ses_start, session_end=ses_end)
                    vtick.append(s)
    # 4*4*6*3 = 288

    # ---- L. Bayesian momentum ----
    for nb in [5, 10, 20, 50]:
        for dc in [0.5, 0.7, 0.9]:
            for pt in [0.6, 0.7, 0.8]:
                for stp, tgt in [(4, 12), (5, 15), (6, 18), (8, 24), (10, 30), (12, 36)]:
                    for ses_choice in range(2):
                        if ses_choice == 0:
                            ses_start, ses_end, ses_name = None, None, 'all'
                        else:
                            ses_start, ses_end, ses_name = (13, 30), (20, 0), 'RTH'
                        name = f"L_BMO_n{nb}_d{int(dc*10)}_p{int(pt*10)}_s{stp}t{tgt}_{ses_name}"
                        s = BayesianMomentum(
                            name, n_bars=nb, decay=dc, p_threshold=pt,
                            stop_pts=stp, target_pts=tgt,
                            session_start=ses_start, session_end=ses_end)
                        v1m.append(s)
    # 4*3*3*6*2 = 432

    # ---- M. Markov state ----
    for sw in [20, 50, 100]:
        for thr in [0.7, 0.8, 0.9]:
            for stp, tgt in [(4, 12), (5, 15), (6, 18), (8, 24), (10, 30), (12, 36)]:
                for ses_choice in range(3):
                    if ses_choice == 0:
                        ses_start, ses_end, ses_name = None, None, 'all'
                    elif ses_choice == 1:
                        ses_start, ses_end, ses_name = (13, 30), (20, 0), 'RTH'
                    else:
                        ses_start, ses_end, ses_name = (22, 0), (5, 0), 'CME'
                    name = f"M_MKV_sw{sw}_t{int(thr*10)}_s{stp}t{tgt}_{ses_name}"
                    s = MarkovStateStrategy(
                        name, state_window=sw, threshold=thr,
                        stop_pts=stp, target_pts=tgt,
                        session_start=ses_start, session_end=ses_end)
                    v1m.append(s)
    # 3*3*6*3 = 162

    # ---- N. Time-of-day micro (96 windows × 4 R:R = 384, cap) ----
    N_RRS = [(5, 10), (8, 16), (10, 20), (5, 15)]
    for hh in range(0, 24):
        for mn in [0, 15, 30, 45]:
            for rr_i, (stp, tgt) in enumerate(N_RRS):
                name = f"N_WIN_h{hh:02d}m{mn:02d}_s{stp}t{tgt}"
                s = WindowedPullback(
                    name, window_hh=hh, window_mn=mn,
                    impulse_pts=5.0, impulse_bars=4, pull_pct=0.382,
                    stop_pts=stp, target_pts=tgt, invert=True)
                v1m.append(s)
    # 24*4*4 = 384

    # ---- O. Stochastic random ----
    O_rng = random.Random(0xBAD1DEAA)
    n_o = 500 if quick else 1000
    o_variants = build_stochastic_variants(n_o, O_rng)
    for s in o_variants:
        v1m.append(s)

    # ---- P. Confidence-gated ----
    for win in [5, 10, 20, 50]:
        for thr in [0.40, 0.45, 0.50, 0.55]:
            for (imp, bars, pp, stp, tgt) in BASES:
                for inv in [True, False]:
                    name = (f"P_CG_w{win}_t{int(thr*100)}_imp{int(imp)}_"
                            f"b{bars}_s{stp}t{tgt}_{'INV' if inv else 'TRD'}")
                    s = ConfidenceGatedPullback(
                        name, gate_window=win, wr_threshold=thr,
                        impulse_pts=imp, impulse_bars=bars, pull_pct=pp,
                        stop_pts=stp, target_pts=tgt, invert=inv)
                    v1m.append(s)
    # 4*4*8*2 = 256

    # ---- Q. Vacuum + tape ----
    for tm in [2.0, 3.0, 5.0]:
        for vr in [0.5, 0.3, 0.1]:
            for stp, tgt in [(3, 9), (4, 12), (5, 15), (6, 18), (8, 24), (10, 30)]:
                for ses_choice in range(2):
                    if ses_choice == 0:
                        ses_start, ses_end, ses_name = None, None, 'all'
                    else:
                        ses_start, ses_end, ses_name = (13, 30), (20, 0), 'RTH'
                    name = f"Q_VT_tm{int(tm*10)}_vr{int(vr*100)}_s{stp}t{tgt}_{ses_name}"
                    s = VacuumPlusTapeStrategy(
                        name, tape_mult=tm, vacuum_ratio=vr,
                        stop_pts=stp, target_pts=tgt,
                        session_start=ses_start, session_end=ses_end)
                    vtick.append(s)
    # 3*3*6*2 = 108

    # ---- R. Pre-bar prediction ----
    for f in [0.3, 0.5, 0.7]:
        for thr in [2, 3, 5, 8]:
            for stp, tgt in [(3, 9), (4, 12), (5, 15), (6, 18), (8, 24), (10, 30)]:
                name = f"R_PRE_f{int(f*10)}_t{thr}_s{stp}t{tgt}"
                s = PreBarPrediction(
                    name, fraction=f, threshold_pts=thr,
                    stop_pts=stp, target_pts=tgt)
                vtick.append(s)
    # 3*4*6 = 72

    # ---- S. Optimal stopping ----
    for pl in [2, 4, 6, 8]:
        for rv in [1, 2, 3]:
            for (imp, bars, pp, stp, tgt) in BASES:
                name = (f"S_OS_pl{pl}_rv{rv}_imp{int(imp)}_b{bars}_s{stp}t{tgt}")
                s = OptimalStoppingPullback(
                    name, profit_lock_pts=pl, reverse_pts=rv,
                    impulse_pts=imp, impulse_bars=bars, pull_pct=pp,
                    stop_pts=stp, target_pts=tgt, invert=True)
                v1m.append(s)
    # 4*3*8 = 96

    # ---- T. Massive Latin sweep ----
    if not quick:
        T_rng = random.Random(0x77777777)
        t_variants = build_t_sweep(T_rng, n_per_base=t_sweep // 3)
        for s in t_variants:
            v1m.append(s)

    return v1m, vtick


# =============================================================================
# DOW helper
# =============================================================================
def _dow(y, m, d):
    if m < 3:
        m += 12; y -= 1
    K = y % 100; J = y // 100
    h = (d + (13*(m+1))//5 + K + K//4 + J//4 + 5*J) % 7
    return (h + 5) % 7


def _dir(name):
    """Classify direction label from name prefix."""
    for prefix in ('A_', 'B_', 'C_', 'D_', 'E_', 'F_', 'G_', 'H_', 'I_',
                   'J_', 'K_', 'L_', 'M_', 'N_', 'O_', 'P_', 'Q_', 'R_',
                   'S_', 'T_'):
        if name.startswith(prefix):
            return prefix.rstrip('_')
    return 'X'


# =============================================================================
# MAIN
# =============================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offset", type=int, default=DEFAULT_OFFSET)
    ap.add_argument("--ckpt-suffix", default="")
    ap.add_argument("--max-days", type=int, default=60)
    ap.add_argument("--t-sweep", type=int, default=6000,
                    help="Total T-avenue Latin variants (3 bases × N/3)")
    ap.add_argument("--quick", action="store_true",
                    help="Skip the big T sweep + cap A-avenue")
    args = ap.parse_args()

    ckpt_path = ("/home/user/HFTBot/research/round12_checkpoint"
                 f"{args.ckpt_suffix}.pkl")
    csv_path = ("/home/user/HFTBot/research/round12_summary"
                f"{args.ckpt_suffix}.csv")
    md_path = "/home/user/HFTBot/research/round12_results.md"

    print(f"[round12] building variants (t_sweep={args.t_sweep}, "
          f"quick={args.quick})...", file=sys.stderr)
    v1m, vtick = build_all_variants(quick=args.quick, t_sweep=args.t_sweep)
    all_strats = v1m + vtick
    for s in all_strats:
        attach_r7_executor(s)
    # Pre-cache feed_signal callable and initialize next-check timestamp
    # to enable the fast-skip optimization in the main loop.
    for s in vtick:
        s._feed_signal_fn = getattr(s, 'feed_signal', None)
        s._next_feed_ts = 0.0
        if not hasattr(s, '_last_signal_ts'):
            s._last_signal_ts = 0.0

    # OPTIMIZATION: wrap StrategyBase.add_setup to add the strategy to a
    # shared 'active' set. The main loop iterates only the active set
    # instead of all 13K strategies every tick.
    _ACTIVE = set()
    _orig_add_setup = StrategyBase.add_setup
    def _patched_add_setup(self, *args, **kwargs):
        _orig_add_setup(self, *args, **kwargs)
        _ACTIVE.add(id(self))
        self._active_ref = self  # keep alive
    StrategyBase.add_setup = _patched_add_setup
    # Maintain a parallel dict so we can look up strategy by id quickly
    _ACTIVE_LOOKUP = {id(s): s for s in all_strats}
    print(f"[round12] Built {len(all_strats):,} strategies "
          f"({len(v1m)} 1m + {len(vtick)} tick)", file=sys.stderr)

    resumed = load_checkpoint(ckpt_path, all_strats)
    if resumed is not None:
        start_offset, day_counter, last_day_key = resumed
        resumed_trades = sum(s.n_trades for s in all_strats)
        print(f"[round12] RESUMING from offset {start_offset:,} "
              f"day_counter={day_counter} ({resumed_trades:,} trades booked)",
              file=sys.stderr)
    else:
        start_offset = args.offset
        day_counter = -1
        last_day_key = None

    bb_1m = BarBuilder(granularity_secs=60, max_history=300)
    n_lines = 0
    t_start = time.time()
    last_progress_t = t_start
    last_progress_ticks = 0

    file_size = os.path.getsize(PATH)
    print(f"[round12] file size: {file_size:,} bytes", file=sys.stderr)
    max_day_counter = day_counter + args.max_days

    # Detect avenue A strategies (need react_postprocess)
    a_strats = [s for s in v1m if isinstance(s, ReactiveBracketStrategy)]
    s_strats = [s for s in v1m if isinstance(s, OptimalStoppingPullback)]

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
                                    all_strats)
                except Exception as e:
                    print(f"  [round12] ckpt save failed: {e!r}", file=sys.stderr)
                print(f"  [round12] {n_lines/1e6:.1f}M ticks rate={rate/1e6:.2f}M/s "
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

            # Update gauges
            MARKET.feed_tick(ts, last, bid, ask)
            _r10.VPIN_GAUGE.feed_tick(last, bid, ask)
            _r10.TAPE.feed_tick(ts)
            TICK_WIN.feed(ts, last, bid, ask)
            MSM.feed(ts, last)
            TICK_RATE.feed(ts)
            BAP.feed(ts, bid, ask)
            SUB_TICK_BUF.feed(ts, last)

            if bb_1m.on_tick(ts, last):
                closed = bb_1m.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    MARKET.feed_bar(o, h, l, c)
                    REGIME.feed_bar(o, h, l, c)
                    SWHL.feed_bar(o, h, l, c)
                    for s in v1m:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_1m.history)

            # Per-tick signal emitters — gated by per-strategy cooldown skip.
            for s in vtick:
                nxt = s._next_feed_ts
                if ts < nxt:
                    continue
                fs = s._feed_signal_fn
                if fs is None:
                    s._next_feed_ts = 1e18
                    continue
                fs(ts, bid, ask)
                last_ts = s._last_signal_ts
                cd = s.cooldown_s
                s._next_feed_ts = max(ts, last_ts + cd)

            # Avenue A post-processing: only for strategies currently in_trade
            for s in a_strats:
                if s.in_trade is not None:
                    react_postprocess(s, ts)
            # Avenue S post-processing: only for strategies currently in_trade
            for s in s_strats:
                if s.in_trade is not None:
                    optimal_stop_postprocess(s, ts, bid, ask)

            # Bot tick — FAST PATH: only iterate the active set (strategies
            # with pending setups or open trade). _ACTIVE is updated by the
            # patched add_setup hook and pruned here.
            if _ACTIVE:
                to_remove = []
                for sid in _ACTIVE:
                    s = _ACTIVE_LOOKUP[sid]
                    r10_bot_on_tick(s, ts, bid, ask, day_counter, hh, mn, last)
                    if not s.pending and s.in_trade is None:
                        to_remove.append(sid)
                for sid in to_remove:
                    _ACTIVE.discard(sid)

    elapsed = time.time() - t_start
    total_days = day_counter + 1
    print(f"\n[round12] DONE in {elapsed/60:.1f}min, {n_lines:,} ticks, "
          f"{total_days} day buckets", file=sys.stderr)

    # =========================================================================
    # REPORTING
    # =========================================================================
    rows_191 = [report_strategy(s, total_days, FEE_FULL_RT) for s in all_strats]
    rows_074 = [report_strategy(s, total_days, FEE_PROP_RT) for s in all_strats]
    rows_nq_191 = [report_strategy(s, total_days, FEE_FULL_RT, NQ_PER_PT)
                   for s in all_strats]
    rows_nq_074 = [report_strategy(s, total_days, FEE_PROP_RT, NQ_PER_PT)
                   for s in all_strats]

    rows_191_by_name = {r['name']: r for r in rows_191}
    rows_074_by_name = {r['name']: r for r in rows_074}
    nq191_by = {r['name']: r for r in rows_nq_191}
    nq074_by = {r['name']: r for r in rows_nq_074}

    rows_191.sort(key=lambda r: -r['per_day'])
    rows_074.sort(key=lambda r: -r['per_day'])
    rows_nq_191.sort(key=lambda r: -r['per_day'])
    rows_nq_074.sort(key=lambda r: -r['per_day'])

    with open(csv_path, "w", newline="") as cf:
        w = csv.writer(cf)
        w.writerow([
            "name", "dir", "trades", "trades_per_day", "wr",
            "per_day_191", "per_day_074", "per_day_NQ_191", "per_day_NQ_074",
            "per_trade_191", "max_dd_191", "max_dd_074",
            "sharpe_191", "sharpe_074",
            "n_days", "pos_d_191", "neg_d_191",
        ])
        for r in rows_191:
            n = r['name']
            r74 = rows_074_by_name[n]
            rnq = nq191_by[n]
            rnq74 = nq074_by[n]
            w.writerow([
                n, _dir(n), r['n'], f"{r['trades_per_day']:.1f}", f"{r['wr']:.4f}",
                f"{r['per_day']:.2f}", f"{r74['per_day']:.2f}",
                f"{rnq['per_day']:.2f}", f"{rnq74['per_day']:.2f}",
                f"{r['per_trade']:.3f}",
                f"{r['max_dd']:.2f}", f"{r74['max_dd']:.2f}",
                f"{r['sharpe']:.3f}", f"{r74['sharpe']:.3f}",
                r['n_days'], r['pos_d'], r['neg_d'],
            ])
    print(f"[round12] wrote CSV {csv_path}", file=sys.stderr)

    def is_pass(r):
        return (r['trades_per_day'] >= 300 and r['wr'] >= 0.45
                and r['per_day'] >= 1000 and r['max_dd'] <= 5000)

    pass_191 = [r for r in rows_191 if is_pass(r)]
    pass_074 = [r for r in rows_074 if is_pass(r)]
    pass_nq_191 = [r for r in rows_nq_191 if is_pass(r)]
    pass_nq_074 = [r for r in rows_nq_074 if is_pass(r)]

    by_dir = defaultdict(list)
    for r in rows_191:
        by_dir[_dir(r['name'])].append(r)

    # =========================================================================
    # MARKDOWN
    # =========================================================================
    L = []
    L.append("# Round 12 strategy search — 20 BRAND-NEW avenues\n\n")
    L.append(f"Generated: {datetime.now().isoformat()}\n")
    L.append(f"Period: {total_days} calendar-day buckets from offset "
             f"{args.offset:,} (max-days={args.max_days})\n")
    L.append(f"Tick stream: {n_lines:,} lines processed\n")
    L.append(f"Strategies tested: {len(all_strats):,}\n\n")

    L.append("## Execution model\n\n")
    L.append("Bot-faithful identical to round 11: queue overshoot by 1 tick "
             "(LIMIT), 200ms latency, 10pt approach threshold, multi-setup "
             "lock, 0.5pt stop slip + 10% gap risk, 10s cooldown (avenue C "
             "uses 5s, K uses 0.5s, A uses default), 600s max hold.\n\n")
    L.append("Fees: **$1.91/RT** vs **$0.74/RT** (prop-firm). "
             "Instruments: MNQ ($2/pt) and NQ ($20/pt).\n\n")

    L.append("## Hard requirements\n")
    L.append("- 300+ trades/day average\n- 45%+ WR\n- $1,000+ $/day\n- maxDD <= $5,000\n\n")

    L.append("## Section 1 — FULL_PASS strategies\n\n")
    L.append(f"- $1.91 MNQ: **{len(pass_191)}**\n")
    L.append(f"- $0.74 MNQ (prop-firm): **{len(pass_074)}**\n")
    L.append(f"- $1.91 NQ: **{len(pass_nq_191)}**\n")
    L.append(f"- $0.74 NQ (prop-firm): **{len(pass_nq_074)}**\n\n")
    for label, ps in [("$1.91 MNQ", pass_191), ("$0.74 MNQ", pass_074),
                      ("$1.91 NQ", pass_nq_191), ("$0.74 NQ", pass_nq_074)]:
        if ps:
            L.append(f"\n### {label} passers (top 20)\n")
            for r in ps[:20]:
                L.append(f"- **{r['name']}** -- {r['n']:,} trades "
                         f"({r['trades_per_day']:.1f}/day), WR={r['wr']*100:.1f}%, "
                         f"${r['per_day']:,.0f}/day, DD=${r['max_dd']:,.0f}, "
                         f"Sharpe={r['sharpe']:.2f}\n")

    L.append("\n## Section 2 — Per-avenue best (any fee/instrument)\n\n")
    L.append("| Avenue | n_strats | Best $/d 191 | Best $/d 074 | Best $/d NQ191 | Best $/d NQ074 | Top strat |\n")
    L.append("|---|---:|---:|---:|---:|---:|---|\n")
    for d in sorted(by_dir.keys()):
        items = by_dir[d]
        # Best per fee/inst
        b191 = max(items, key=lambda r: r['per_day'])
        b074 = max((rows_074_by_name[r['name']] for r in items),
                   key=lambda r: r['per_day'])
        bnq191 = max((nq191_by[r['name']] for r in items),
                     key=lambda r: r['per_day'])
        bnq074 = max((nq074_by[r['name']] for r in items),
                     key=lambda r: r['per_day'])
        L.append(f"| {d} | {len(items):,} | ${b191['per_day']:,.0f} | "
                 f"${b074['per_day']:,.0f} | ${bnq191['per_day']:,.0f} | "
                 f"${bnq074['per_day']:,.0f} | {b191['name']} |\n")

    L.append("\n## Section 3 — Top 30 by $/day across ALL fee/instrument combos\n\n")
    # combine: for each strategy take MAX across the 4 fee/instrument settings
    combined = []
    for n in rows_191_by_name:
        best_label, best_val = None, -1e18
        for label, src in [("MNQ191", rows_191_by_name),
                           ("MNQ074", rows_074_by_name),
                           ("NQ191", nq191_by),
                           ("NQ074", nq074_by)]:
            v = src[n]['per_day']
            if v > best_val:
                best_val = v
                best_label = label
        combined.append((best_val, best_label, n))
    combined.sort(reverse=True)
    L.append("| Rank | Strategy | Av | Best fee | $/d | Tr/d | WR% | DD | Sharpe |\n")
    L.append("|---:|---|:---:|:---:|---:|---:|---:|---:|---:|\n")
    for i, (val, lab, n) in enumerate(combined[:30], 1):
        src = {"MNQ191": rows_191_by_name, "MNQ074": rows_074_by_name,
               "NQ191": nq191_by, "NQ074": nq074_by}[lab]
        r = src[n]
        L.append(f"| {i} | {n} | {_dir(n)} | {lab} | "
                 f"${val:,.0f} | {r['trades_per_day']:.1f} | "
                 f"{r['wr']*100:.1f} | ${r['max_dd']:,.0f} | "
                 f"{r['sharpe']:.2f} |\n")

    L.append("\n## Section 4 — Top 30 by MNQ $1.91 $/day\n\n")
    L.append("| Rank | Strategy | Av | Tr | Tr/d | WR% | $/d 191 | $/d 074 | $/d NQ074 | DD | Sharpe |\n")
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

    L.append("\n## Section 5 — Top 30 by MNQ $0.74 (prop-firm)\n\n")
    L.append("| Rank | Strategy | Av | Tr/d | WR% | $/d 074 | DD | Sharpe |\n")
    L.append("|---:|---|:---:|---:|---:|---:|---:|---:|\n")
    for i, r in enumerate(rows_074[:30], 1):
        L.append(f"| {i} | {r['name']} | {_dir(r['name'])} | "
                 f"{r['trades_per_day']:.1f} | "
                 f"{r['wr']*100:.1f} | ${r['per_day']:,.0f} | "
                 f"${r['max_dd']:,.0f} | {r['sharpe']:.2f} |\n")

    L.append("\n## Section 6 — Top 30 by NQ $0.74 (prop-firm)\n\n")
    L.append("| Rank | Strategy | Av | Tr/d | WR% | $/d NQ074 | DD | Sharpe |\n")
    L.append("|---:|---|:---:|---:|---:|---:|---:|---:|\n")
    for i, r in enumerate(rows_nq_074[:30], 1):
        L.append(f"| {i} | {r['name']} | {_dir(r['name'])} | "
                 f"{r['trades_per_day']:.1f} | "
                 f"{r['wr']*100:.1f} | ${r['per_day']:,.0f} | "
                 f"${r['max_dd']:,.0f} | {r['sharpe']:.2f} |\n")

    L.append("\n## Section 7 — Round 13 recommendations\n\n")
    L.append("User mindset: NEVER conclude 'this can't work.' "
             "ALWAYS conclude 'we need more variants OR a new avenue.'\n\n")
    if pass_191 or pass_074 or pass_nq_191 or pass_nq_074:
        L.append("**At least one PASSER found in round 12.** "
                 "Recommend out-of-sample validation on new window before "
                 "deployment. Continue scaling: round 13 should re-sweep "
                 "around each passer with denser Latin hypercube.\n\n")
    else:
        L.append("**No passers after round 12.** Round 13 attack angles:\n\n")
    L.append("Round 13 NEW avenues (regardless of passers):\n\n")
    L.append("1. **Deep neural network** — install PyTorch via pip; train a "
             "1D-CNN over (50, 8) tick features per signal.\n")
    L.append("2. **Reinforcement learning with deep state** — DQN with "
             "experience replay; reward = pt-PnL after fee.\n")
    L.append("3. **Microstructure: hidden Markov on tick imbalance** — "
             "5-state HMM on signed tick deltas, fire on emission probability.\n")
    L.append("4. **Cross-asset cointegration** — pair MNQ with ES/RTY/CL "
             "as leading indicators (requires separate data fetch).\n")
    L.append("5. **Genetic programming on raw indicator tree** — DEAP-style "
             "evolution of small expression trees that produce LONG/SHORT signals.\n")
    L.append("6. **Order-book reconstruction from T&S** — infer L2 imbalance "
             "from quote churn patterns; use as a richer signal.\n")
    L.append("7. **Volatility surface forecasting** — train per-hour realized-vol "
             "predictor; sub-strategies per vol regime.\n")
    L.append("8. **News timestamp library** — fetch high-impact econ events "
             "(NFP, FOMC, CPI); fire pre/post window strategies.\n")
    L.append("9. **Self-supervised tick-embedding** — train autoencoder on "
             "tick windows, cluster, route strategy per cluster.\n")
    L.append("10. **Transformer over 200-tick context** — attention-based "
             "classifier of next-30s direction (CPU-feasible with d_model=32).\n")
    L.append("11. **Heavy ensemble** — vote across top-100 round-12 survivors "
             "with majority rule per tick.\n")
    L.append("12. **Per-day-of-week regime split** — separate top-strategy "
             "per (DOW, hour-of-day) cell, 5×24 = 120 sub-models.\n")
    L.append("13. **GAN-generated synthetic ticks** — train generator on real "
             "data, synthesize counterfactual streams for robustness check.\n")
    L.append("14. **Bayesian optimization** — replace Latin hypercube with "
             "GP-EI surrogate on top-T sweep; sample 5,000 informed pts.\n")
    L.append("15. **Multi-objective Pareto frontier** — instead of single "
             "$/day, optimize (per_day, sharpe, -dd) jointly.\n")
    L.append("16. **Adversarial tick replay** — perturb prices by ±0.25pt "
             "randomly to test robustness; keep only invariant winners.\n")
    L.append("17. **Curriculum: train on low-vol days, deploy on high-vol** "
             "— or vice-versa.\n")
    L.append("18. **Quantile regression** — predict 0.1 / 0.5 / 0.9 quantile "
             "of 30-second forward return; trade on extreme tails.\n")
    L.append("19. **Reservoir computing** — random-projection state "
             "with ridge-regression readout; cheap online learning.\n")
    L.append("20. **PolicyGradient over continuous action** — output entry "
             "size and target/stop continuously (still respect 1-MNQ cap).\n\n")
    L.append("Also consider asking user: would they relax 300 tr/day to "
             "150 tr/day, or accept multiple 1-MNQ contracts simultaneously "
             "(still respects margin)? **DO NOT relax without explicit OK.**\n")

    L.append("\n## Section 8 — Full strategy table (top 300 by $/day MNQ $1.91)\n\n")
    L.append("| Strategy | Av | Tr | Tr/d | WR% | $/d 191 | $/d 074 | $/d NQ191 | $/d NQ074 | DD | Sharpe |\n")
    L.append("|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for r in rows_191[:300]:
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
    print(f"[round12] wrote MD {md_path}", file=sys.stderr)

    # Console summary
    print("\n" + "=" * 110)
    print(f"FULL_PASS under $1.91 (MNQ): {len(pass_191)}")
    print(f"FULL_PASS under $0.74 (MNQ prop-firm): {len(pass_074)}")
    print(f"FULL_PASS under $1.91 (NQ): {len(pass_nq_191)}")
    print(f"FULL_PASS under $0.74 (NQ prop-firm): {len(pass_nq_074)}")
    print("=" * 110)
    for r in rows_191[:20]:
        n = r['name']
        r74 = rows_074_by_name[n]
        rnq74 = nq074_by[n]
        flag = ""
        if is_pass(r): flag = " *PASS(full)*"
        elif is_pass(r74): flag = " *PASS(prop)*"
        elif is_pass(rnq74): flag = " *PASS(NQprop)*"
        print(f"{n[:55]:>55s} {r['n']:>6d} {r['trades_per_day']:>6.1f} "
              f"{r['wr']*100:>4.1f}% ${r['per_day']:>+7.0f} (074: "
              f"${r74['per_day']:>+6.0f}, NQ074: ${rnq74['per_day']:>+6.0f}){flag}")

    try:
        if os.path.exists(ckpt_path):
            os.remove(ckpt_path)
            print(f"[round12] cleared checkpoint {ckpt_path}", file=sys.stderr)
    except Exception:
        pass


if __name__ == "__main__":
    main()
