"""Round 7 strategy search for MNQ — bot-faithful, 200+ NEW avenues.

Rounds 1-6 exhausted: pullback / inverse-pullback / NBR / RSI / Bollinger /
VWAP fade & breakout / ORB / EMA pullback / ATR gates / sessions / round
numbers / z-score / tick-velocity / tick-momentum (round 6's TMC) /
liquidity-sweep / impulse-failure / breakout STOPs / RR sweeps / scale-out /
breakeven / volume bars / day-of-week / hourly bias / hold strategies. Result:
ZERO strategies pass 300tr/d & 45% WR & $1k/d & DD<=$5k under bot-faithful
execution.

Round 7 avenues (all NEW vs rounds 1-6):

  T01 Trailing-stop adaptive exits applied to marketable-pullback /
      breakout entries (trail=2,3,5pt)
  T02 Time-decay exits: close trade if not at +N pts by minute M
  T03 Exit-on-momentum-shift: close if K ticks reverse direction
  T04 Order-flow imbalance: rolling N-sec bid-hit vs ask-lift count,
      enter on extreme imbalance (continuation or fade)
  T05 Range-compression breakout: ATR drops below X for N bars then bursts
  T06 Wick-exhaustion fade: bar with >5pt wick on one side, fade the wick
  T07 3-bar inside-bar break: three inside bars then breakout
  T08 Doji / hammer / shooting-star single-bar reversal
  T09 Three-line break (Sakata) — N-pt break of recent extreme
  T10 Ichimoku tenkan/kijun-style EMA crossover on tick bars
  T11 Fractal pivots (5-bar swing high/low fade or follow)
  T12 Hidden divergence (price LH/RSI HL)
  T13 Range-expansion percentile (current bar > 90th pct range)
  T14 Multi-bar pullback windows (5,6,8,10,15 bars)
  T15 Heikin-Ashi color change
  T16 ORB battery: 5/10/15/30/60-min opening ranges
  T17 PDH/PDL fade
  T18 Gap continuation + fade
  T19 Trendline / linreg slope reversal
  T20 Z-score + wider bands & marketable
  T21 Asia-session fade in London open
  T22 CME-open drive (follow first 3pt move)
  T23 CME-open fade
  T24 NYSE open drive/fade variants (multiple windows)
  T25 Pre/post lunch fade
  T26 News-window narrow scalps (12:30, 13:30, 14:00 UTC)
  T27 Post-news momentum (after 13:30 spike)
  T28 Tick-rate spike trigger (ticks/sec > 5x baseline)
  T29 Spread-compression entry (bid-ask spread tight)
  T30 Spread-widening fade
  T31 Triple-top/bottom rejection
  T32 VWAP reclaim after break (recross from below = LONG)
  T33 EMA reclaim (close back above EMA20)
  T34 Cumulative delta proxy via tick-up/down count momentum
  T35 Stop-LIMIT exits applied to wider strategies
  T36 OCO multi-level entries (3 LIMITs at fib levels, first wins)
  T37 OCO opposite-direction (LONG breakout + SHORT breakdown)
  T38 Wide stop + trail (20pt initial, trail to BE+5)
  T39 Cap loss + free run (5pt stop, trail only target)
  T40 Asymmetric R:R (2pt stop, 30pt target)
  T41 Stop-run reversal (fade liquidity grab + snap-back)
  T42 Fade-the-fade ensemble
  T43 Microstructure bid/ask change-frequency
  T44 Realized-vol regime split
  T45 GARCH-style vol expectation gating
  T46 Cluster volume at level (price stops + vol)
  T47 DOM-proxy bid/ask imbalance > 5x normal
  T48 Friday-close fade
  T49 Sunday-open momentum
  T50 Pivot point S1/R1 daily-pivot touches
  T51 Camarilla pivot bounces
  T52 Fibonacci extension (beyond 0.618 -> 1.618/2.618)
  T53 Bart pattern (vertical + flat + vertical opposite)
  T54 Multi-timeframe confluence (1m + 5m bias)

EXECUTION MODEL: SAME as round 5/6 (queue overshoot, 200ms latency, 10pt
approach, single-LIMIT lock, stop-MARKET slip, $1.91/RT). All new strategies
use fill_mode={limit,marketable,stop}, exit_mode={stop_market,stop_limit},
with NEW per-trade behaviors: trailing stops, time-decay, momentum-shift
exit, OCO cohorts.

Outputs:
  - research/round7_results.md
  - research/round7_summary.csv
  - research/round7_checkpoint.pkl
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

# Reuse round 6 (which reuses round 4) for executor, classes, helpers.
from research import round4_search as _r4  # noqa: E402
sys.modules.setdefault("round4_search", _r4)
from research import round6_search as _r6  # noqa: E402
sys.modules.setdefault("round6_search", _r6)

PullbackStrategy = _r4.PullbackStrategy
PullbackFailure = _r4.PullbackFailure
NBarReversal = _r4.NBarReversal
RSIReversion = _r4.RSIReversion
BarBuilder = _r4.BarBuilder
VolumeBarBuilder = _r4.VolumeBarBuilder
StrategyBase = _r4.StrategyBase
_round_long_entry = _r4._round_long_entry
_round_short_entry = _r4._round_short_entry
_round_long_stop = _r4._round_long_stop
_round_short_stop = _r4._round_short_stop
_round_long_tgt = _r4._round_long_tgt
_round_short_tgt = _r4._round_short_tgt

attach_executor = _r6.attach_executor
MarketablePullback = _r6.MarketablePullback
BreakoutStrategy = _r6.BreakoutStrategy
TickMomentumContinuation = _r6.TickMomentumContinuation
ImpulseFailure = _r6.ImpulseFailure
LiquiditySweep = _r6.LiquiditySweep
ZScoreReversion = _r6.ZScoreReversion
NBarReversalMkt = _r6.NBarReversalMkt

# Execution constants (mirror round 6/5)
PATH = "/home/user/HFTBot/data/tick/ustech/USTECH_full.csv"
DEFAULT_OFFSET = 8_300_000_000  # 14-day window (last 14d of 60d ending at file end)
CHECKPOINT_EVERY_TICKS = 100_000

COMM_RT = 0.74
EXCH_FEES_RT = 1.17
TOTAL_RT_COST = COMM_RT + EXCH_FEES_RT
MNQ_PER_PT = 2.0

APPROACH_THRESHOLD_PT = 10.0
LATENCY_EMBARGO_S = 0.20
FRESH_PLACEMENT_LATENCY_S = 0.25
STOP_SLIP_PT = 0.5
STOP_GAP_SLIP_PROB = 0.10
STOP_GAP_SLIP_MAX_PT = 1.5
COOLDOWN_S = 10.0
MAX_HOLD_S = 600
STALE_FILL_PROB = 0.05
TICK = 0.25
MARKETABLE_SLIP_PT = TICK
STOP_ENTRY_SLIP_PT = TICK
STOP_LIMIT_OFFSET_PT = 2.0
STOP_LIMIT_NONFILL_PROB = 0.10

RNG = random.Random(0xC0FFEE7A)


# =============================================================================
# EXTENDED EXECUTOR: round-6 bot_on_tick plus trailing-stop / time-decay /
# momentum-shift / OCO-cohort exit behaviors carried on the in_trade dict.
# =============================================================================
class BotFaithfulExecutor:
    __slots__ = (
        "strat", "active_limit_key", "active_limit_armed_ts",
        "skip_next_trade", "last_exit_ts",
    )

    def __init__(self, strat):
        self.strat = strat
        self.active_limit_key = None
        self.active_limit_armed_ts = None
        self.skip_next_trade = False
        self.last_exit_ts = None


def attach_r7_executor(strat):
    strat._exec = BotFaithfulExecutor(strat)


def _closest_pending_r7(strat, bid, ask):
    best = None
    best_dist = float('inf')
    for s in strat.pending:
        if s.get('used') or s.get('_fire_attempted'):
            continue
        orig = s.get('orig', s['side'])
        entry = s['entry']
        fill_mode = s.get('fill_mode', 'limit')
        if fill_mode == 'stop':
            if orig == "LONG":
                if ask > entry + 0.5:
                    continue
                dist = max(0.0, entry - ask)
            else:
                if bid < entry - 0.5:
                    continue
                dist = max(0.0, bid - entry)
        else:
            if orig == "LONG":
                if ask < entry - 0.5:
                    continue
                dist = max(0.0, ask - entry)
            else:
                if bid > entry + 0.5:
                    continue
                dist = max(0.0, entry - bid)
        if dist < best_dist:
            best_dist = dist
            best = s
    return best, best_dist


def _cancel_cohort(strat, cohort_key):
    """When one OCO setup fills, mark all OTHER setups in same cohort
    as used so they can't fire."""
    if cohort_key is None:
        return
    for s in strat.pending:
        if s.get('cohort') == cohort_key and not s.get('used'):
            s['used'] = True


def r7_bot_on_tick(strat, ts, bid, ask, day_counter, hh, mn, last_px):
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

        # ---- TRAILING-STOP behavior (T01, T38, T39) ----
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

        # ---- BREAKEVEN trigger (T38) ----
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

        # ---- TIME-DECAY exit (T02) ----
        time_decay = tr.get('time_decay')
        if time_decay is not None and exit_now is None:
            decay_secs, need_pts = time_decay
            if ts - tr['et'] >= decay_secs:
                if side == 'LONG':
                    pnl = bid - entry
                else:
                    pnl = entry - ask
                if pnl < need_pts:
                    exit_now = ('decay', pnl)

        # ---- MOMENTUM-SHIFT exit (T03) ----
        # Track K consecutive ticks AGAINST our direction; exit when reached.
        mshift = tr.get('momshift_k')
        if mshift is not None and exit_now is None:
            lp = tr.get('_last_px', last_px)
            if side == 'LONG':
                if last_px < lp:
                    tr['_against'] = tr.get('_against', 0) + 1
                elif last_px > lp:
                    tr['_against'] = 0
            else:
                if last_px > lp:
                    tr['_against'] = tr.get('_against', 0) + 1
                elif last_px < lp:
                    tr['_against'] = 0
            tr['_last_px'] = last_px
            if tr.get('_against', 0) >= mshift:
                if side == 'LONG':
                    pnl = bid - entry
                else:
                    pnl = entry - ask
                exit_now = ('mshift', pnl)

        # ---- Regular stop / target / max-hold ----
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
            reason, pnl = exit_now
            pnl_usd = pnl * MNQ_PER_PT - TOTAL_RT_COST
            strat.completed.append((pnl_usd, reason, day_counter))
            strat.by_day.setdefault(day_counter, []).append(pnl_usd)
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

    closest, dist = _closest_pending_r7(strat, bid, ask)

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

    if exe.skip_next_trade:
        exe.skip_next_trade = False
        s['_fire_attempted'] = True
        exe.active_limit_key = None
        exe.active_limit_armed_ts = None
        return

    # Determine stop/target from offsets if present
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
    # OCO: cancel sibling setups in same cohort.
    _cancel_cohort(strat, s.get('cohort'))
    exe.active_limit_key = None
    exe.active_limit_armed_ts = None


# =============================================================================
# Patched add_setup that passes trail_pts, time_decay, momshift_k, cohort.
# =============================================================================
def _patched_add_setup_r7(self, side, orig, entry, stop, target, ts_now,
                           key=None, expires_in=300, extra=None):
    if side == "LONG":
        entry_r = _round_long_entry(entry)
        stop_r = _round_long_stop(stop) if stop is not None else None
        target_r = _round_long_tgt(target) if target is not None else None
    else:
        entry_r = _round_short_entry(entry)
        stop_r = _round_short_stop(stop) if stop is not None else None
        target_r = _round_short_tgt(target) if target is not None else None
    if key is not None and any(s['key'] == key and not s.get('used')
                                for s in self.pending):
        return
    setup = {
        'side': side, 'orig': orig,
        'entry': entry_r, 'stop': stop_r, 'target': target_r,
        'expires': ts_now + expires_in, 'used': False, 'key': key,
        '_gen_ts': ts_now,
        '_fire_attempted': False,
    }
    if extra:
        setup.update(extra)
    self.pending.append(setup)


_SB = _r4.StrategyBase
_SB.add_setup = _patched_add_setup_r7


# =============================================================================
# NEW STRATEGY CLASSES — round 7
# =============================================================================

# ---------- T05: Range compression breakout ----------
class RangeCompressionBreakout(StrategyBase):
    """ATR over last N bars < compress_atr_max for K bars; then breakout
    of that compression-range high/low triggers STOP entry.
    """
    def __init__(self, name, n_bars=20, compress_atr_max=3.0, k_consec=4,
                 buf_pts=0.5, stop_pts=4, target_pts=12,
                 cooldown_s=10, session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=120):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.n_bars = n_bars
        self.compress_atr_max = compress_atr_max
        self.k_consec = k_consec
        self.buf_pts = buf_pts
        self.stop_pts = stop_pts
        self.target_pts = target_pts
        self.expires = expires
        self._compress_streak = 0

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.n_bars + 1:
            return
        sub = list(hist)[-self.n_bars:]
        tr_sum = 0.0
        for i in range(1, len(sub)):
            o, h, l, c = sub[i]
            pc = sub[i - 1][3]
            tr_sum += max(h - l, abs(h - pc), abs(l - pc))
        atr = tr_sum / (len(sub) - 1)
        if atr < self.compress_atr_max:
            self._compress_streak += 1
        else:
            self._compress_streak = 0
        if self._compress_streak < self.k_consec:
            return
        rh = max(b[1] for b in sub)
        rl = min(b[2] for b in sub)
        up_entry = rh + self.buf_pts
        dn_entry = rl - self.buf_pts
        extra_l = {'fill_mode': 'stop',
                   'stop_offset_pts': self.stop_pts,
                   'target_offset_pts': self.target_pts}
        extra_s = dict(extra_l)
        # Use cohort so when one fires, other cancels.
        cohort = ("rcb", round(rh, 1), round(rl, 1), ts)
        extra_l['cohort'] = cohort
        extra_s['cohort'] = cohort
        self.add_setup("LONG", "LONG", up_entry, up_entry - self.stop_pts,
                       up_entry + self.target_pts, ts,
                       key=("rcb_l", cohort), expires_in=self.expires, extra=extra_l)
        self.add_setup("SHORT", "SHORT", dn_entry, dn_entry + self.stop_pts,
                       dn_entry - self.target_pts, ts,
                       key=("rcb_s", cohort), expires_in=self.expires, extra=extra_s)


# ---------- T06: Wick exhaustion fade ----------
class WickExhaustionFade(StrategyBase):
    """Bar with wick on upper or lower side >= min_wick_pts AND wick is
    >= wick_ratio * body. Fade the wick with marketable-LIMIT.
    """
    def __init__(self, name, min_wick_pts=5.0, wick_ratio=2.0,
                 stop_pts=4, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=60):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.min_wick_pts = min_wick_pts
        self.wick_ratio = wick_ratio
        self.stop_pts = stop_pts
        self.target_pts = target_pts
        self.expires = expires

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        body = abs(bc - bo)
        upper_wick = bh - max(bo, bc)
        lower_wick = min(bo, bc) - bl
        if upper_wick >= self.min_wick_pts and upper_wick >= max(self.wick_ratio * body, 0.1):
            entry = bc
            extra = {'fill_mode': 'marketable',
                     'stop_offset_pts': self.stop_pts,
                     'target_offset_pts': self.target_pts}
            self.add_setup("SHORT", "SHORT", entry, entry + self.stop_pts,
                           entry - self.target_pts, ts,
                           key=("wex_s", round(bh, 1)),
                           expires_in=self.expires, extra=extra)
        if lower_wick >= self.min_wick_pts and lower_wick >= max(self.wick_ratio * body, 0.1):
            entry = bc
            extra = {'fill_mode': 'marketable',
                     'stop_offset_pts': self.stop_pts,
                     'target_offset_pts': self.target_pts}
            self.add_setup("LONG", "LONG", entry, entry - self.stop_pts,
                           entry + self.target_pts, ts,
                           key=("wex_l", round(bl, 1)),
                           expires_in=self.expires, extra=extra)


# ---------- T07: 3-bar inside-bar break ----------
class InsideBarBreak(StrategyBase):
    """Two/three consecutive inside bars (each high<=prev high AND
    low>=prev low). On break above latest high or below latest low,
    STOP entry in break direction.
    """
    def __init__(self, name, n_inside=2, buf_pts=0.25,
                 stop_pts=4, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=120):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.n_inside = n_inside
        self.buf_pts = buf_pts
        self.stop_pts = stop_pts
        self.target_pts = target_pts
        self.expires = expires

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.n_inside + 1:
            return
        bars = list(hist)[-(self.n_inside + 1):]
        anchor = bars[0]
        for b in bars[1:]:
            if not (b[1] <= anchor[1] and b[2] >= anchor[2]):
                return
        # All inside! Place OCO STOP setups at anchor high/low.
        cohort = ("ibb", round(anchor[1], 1), round(anchor[2], 1), ts)
        up = anchor[1] + self.buf_pts
        dn = anchor[2] - self.buf_pts
        ex_l = {'fill_mode': 'stop',
                'stop_offset_pts': self.stop_pts,
                'target_offset_pts': self.target_pts,
                'cohort': cohort}
        ex_s = dict(ex_l)
        self.add_setup("LONG", "LONG", up, up - self.stop_pts,
                       up + self.target_pts, ts,
                       key=("ibb_l", cohort), expires_in=self.expires, extra=ex_l)
        self.add_setup("SHORT", "SHORT", dn, dn + self.stop_pts,
                       dn - self.target_pts, ts,
                       key=("ibb_s", cohort), expires_in=self.expires, extra=ex_s)


# ---------- T08: Doji / hammer / shooting-star reversal ----------
class CandlePattern(StrategyBase):
    """Detect doji (body < small), hammer (long lower wick, small upper),
    shooting star (long upper wick, small lower). Trade reversal.
    """
    def __init__(self, name, pattern='hammer', body_max=1.0, wick_min=3.0,
                 stop_pts=4, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=120, fill_mode='marketable'):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.pattern = pattern
        self.body_max = body_max
        self.wick_min = wick_min
        self.stop_pts = stop_pts
        self.target_pts = target_pts
        self.expires = expires
        self.fill_mode = fill_mode

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        body = abs(bc - bo)
        upper = bh - max(bo, bc)
        lower = min(bo, bc) - bl
        if self.pattern == 'hammer':
            if body <= self.body_max and lower >= self.wick_min and upper <= body:
                entry = bc
                extra = {'fill_mode': self.fill_mode,
                         'stop_offset_pts': self.stop_pts,
                         'target_offset_pts': self.target_pts}
                self.add_setup("LONG", "LONG", entry, entry - self.stop_pts,
                               entry + self.target_pts, ts,
                               key=("ham_l", round(bl, 1)),
                               expires_in=self.expires, extra=extra)
        elif self.pattern == 'shooting_star':
            if body <= self.body_max and upper >= self.wick_min and lower <= body:
                entry = bc
                extra = {'fill_mode': self.fill_mode,
                         'stop_offset_pts': self.stop_pts,
                         'target_offset_pts': self.target_pts}
                self.add_setup("SHORT", "SHORT", entry, entry + self.stop_pts,
                               entry - self.target_pts, ts,
                               key=("ss_s", round(bh, 1)),
                               expires_in=self.expires, extra=extra)
        elif self.pattern == 'doji':
            if body <= self.body_max and (upper + lower) >= self.wick_min:
                # Doji: fade direction of prior bar's move
                if len(hist) >= 2:
                    prev = hist[-2]
                    prev_move = prev[3] - prev[0]
                    entry = bc
                    extra = {'fill_mode': self.fill_mode,
                             'stop_offset_pts': self.stop_pts,
                             'target_offset_pts': self.target_pts}
                    if prev_move > 0:
                        self.add_setup("SHORT", "SHORT", entry,
                                       entry + self.stop_pts,
                                       entry - self.target_pts, ts,
                                       key=("doji_s", round(bc, 1)),
                                       expires_in=self.expires, extra=extra)
                    else:
                        self.add_setup("LONG", "LONG", entry,
                                       entry - self.stop_pts,
                                       entry + self.target_pts, ts,
                                       key=("doji_l", round(bc, 1)),
                                       expires_in=self.expires, extra=extra)


# ---------- T10: EMA crossover ----------
class EMACross(StrategyBase):
    """Maintain two EMAs (fast, slow). On crossover, enter in cross
    direction with marketable-LIMIT.
    """
    def __init__(self, name, fast=9, slow=21, stop_pts=4, target_pts=12,
                 cooldown_s=10, session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=60, fade=False):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.fast = fast; self.slow = slow
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires
        self.fade = fade
        self._fast_ema = None
        self._slow_ema = None
        self._prev_sign = 0
        self._kf = 2.0 / (fast + 1)
        self._ks = 2.0 / (slow + 1)

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if self._fast_ema is None:
            self._fast_ema = bc
            self._slow_ema = bc
            return
        self._fast_ema = self._fast_ema + self._kf * (bc - self._fast_ema)
        self._slow_ema = self._slow_ema + self._ks * (bc - self._slow_ema)
        sign = 1 if self._fast_ema > self._slow_ema else (-1 if self._fast_ema < self._slow_ema else 0)
        if sign != 0 and self._prev_sign != 0 and sign != self._prev_sign:
            # Crossover
            side = 'LONG' if sign > 0 else 'SHORT'
            if self.fade:
                side = 'SHORT' if side == 'LONG' else 'LONG'
            entry = bc
            extra = {'fill_mode': 'marketable',
                     'stop_offset_pts': self.stop_pts,
                     'target_offset_pts': self.target_pts}
            if side == 'LONG':
                self.add_setup("LONG", "LONG", entry, entry - self.stop_pts,
                               entry + self.target_pts, ts,
                               key=("emax_l", round(entry, 1)),
                               expires_in=self.expires, extra=extra)
            else:
                self.add_setup("SHORT", "SHORT", entry, entry + self.stop_pts,
                               entry - self.target_pts, ts,
                               key=("emax_s", round(entry, 1)),
                               expires_in=self.expires, extra=extra)
        self._prev_sign = sign


# ---------- T11: Fractal pivots (5-bar swing) ----------
class FractalPivot(StrategyBase):
    """5-bar swing pivot: bar[-3] is a high if its high > prior 2 + later 2.
    Fade pivot high (SHORT) when next bar closes below pivot bar's low.
    Mirror for low.
    """
    def __init__(self, name, fade=True, stop_pts=4, target_pts=12,
                 cooldown_s=10, session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=180):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.fade = fade
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < 5:
            return
        bars = list(hist)[-5:]
        b0, b1, b2, b3, b4 = bars
        # Pivot high: b2[1] > all of b0[1], b1[1], b3[1], b4[1]
        pivot_high = (b2[1] > b0[1] and b2[1] > b1[1] and b2[1] > b3[1] and b2[1] > b4[1])
        pivot_low = (b2[2] < b0[2] and b2[2] < b1[2] and b2[2] < b3[2] and b2[2] < b4[2])
        entry = bc
        extra = {'fill_mode': 'marketable',
                 'stop_offset_pts': self.stop_pts,
                 'target_offset_pts': self.target_pts}
        if pivot_high:
            side = "SHORT" if self.fade else "LONG"
            if side == "SHORT":
                self.add_setup(side, side, entry, entry + self.stop_pts,
                               entry - self.target_pts, ts,
                               key=("fp_s", round(b2[1], 1)),
                               expires_in=self.expires, extra=extra)
            else:
                self.add_setup(side, side, entry, entry - self.stop_pts,
                               entry + self.target_pts, ts,
                               key=("fp_l", round(b2[1], 1)),
                               expires_in=self.expires, extra=extra)
        if pivot_low:
            side = "LONG" if self.fade else "SHORT"
            if side == "LONG":
                self.add_setup(side, side, entry, entry - self.stop_pts,
                               entry + self.target_pts, ts,
                               key=("fp_l2", round(b2[2], 1)),
                               expires_in=self.expires, extra=extra)
            else:
                self.add_setup(side, side, entry, entry + self.stop_pts,
                               entry - self.target_pts, ts,
                               key=("fp_s2", round(b2[2], 1)),
                               expires_in=self.expires, extra=extra)


# ---------- T13: Range-expansion percentile ----------
class RangeExpansion(StrategyBase):
    """When current bar's range is in the top X% of last N bars, fade
    the bar's direction (mean reversion). Marketable-LIMIT.
    """
    def __init__(self, name, lookback=20, pct_thresh=0.90, fade=True,
                 stop_pts=5, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=60):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.lookback = lookback
        self.pct_thresh = pct_thresh
        self.fade = fade
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.lookback + 1:
            return
        sub = list(hist)[-(self.lookback+1):-1]
        ranges = sorted(b[1] - b[2] for b in sub)
        idx = int(self.pct_thresh * len(ranges))
        if idx >= len(ranges):
            idx = len(ranges) - 1
        thresh_rng = ranges[idx]
        cur_rng = bh - bl
        if cur_rng < thresh_rng or thresh_rng <= 0:
            return
        move = bc - bo
        if abs(move) < 1.0:
            return
        # Fade or follow
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
                           key=("rex_l", round(entry, 1)),
                           expires_in=self.expires, extra=extra)
        else:
            self.add_setup(side, side, entry, entry + self.stop_pts,
                           entry - self.target_pts, ts,
                           key=("rex_s", round(entry, 1)),
                           expires_in=self.expires, extra=extra)


# ---------- T15: Heikin-Ashi color change ----------
class HeikinAshiColorChange(StrategyBase):
    """Track Heikin-Ashi candles. When color changes from down to up
    (or v.v.), enter in new direction with marketable-LIMIT.
    """
    def __init__(self, name, fade=False, n_streak=3,
                 stop_pts=4, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=60):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.fade = fade
        self.n_streak = n_streak
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires
        self._ha_close = None
        self._ha_open = None
        self._streak_dir = 0
        self._streak_len = 0

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if self._ha_close is None:
            self._ha_close = (bo + bh + bl + bc) / 4.0
            self._ha_open = (bo + bc) / 2.0
            return
        new_close = (bo + bh + bl + bc) / 4.0
        new_open = (self._ha_open + self._ha_close) / 2.0
        sign = 1 if new_close > new_open else (-1 if new_close < new_open else 0)
        if sign == self._streak_dir:
            self._streak_len += 1
        else:
            # color change
            if self._streak_len >= self.n_streak and sign != 0:
                side = "LONG" if sign > 0 else "SHORT"
                if self.fade:
                    side = "SHORT" if side == "LONG" else "LONG"
                entry = bc
                extra = {'fill_mode': 'marketable',
                         'stop_offset_pts': self.stop_pts,
                         'target_offset_pts': self.target_pts}
                if side == "LONG":
                    self.add_setup(side, side, entry,
                                   entry - self.stop_pts,
                                   entry + self.target_pts, ts,
                                   key=("ha_l", round(entry, 1)),
                                   expires_in=self.expires, extra=extra)
                else:
                    self.add_setup(side, side, entry,
                                   entry + self.stop_pts,
                                   entry - self.target_pts, ts,
                                   key=("ha_s", round(entry, 1)),
                                   expires_in=self.expires, extra=extra)
            self._streak_dir = sign
            self._streak_len = 1
        self._ha_close = new_close
        self._ha_open = new_open


# ---------- T16: ORB multi-window ----------
class ORB(StrategyBase):
    """Opening Range Breakout. On first N minutes since session_start_time,
    build the high/low. After window closes, STOP at high+buf or low-buf.
    OCO cohort: when one fires, other cancels.
    """
    def __init__(self, name, window_min=15, session_start=(13, 30),
                 buf_pts=0.5, stop_pts=5, target_pts=15,
                 cooldown_s=10, max_hold=MAX_HOLD_S, expires=3600):
        # session_end open-ended.
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold)
        self.window_min = window_min
        self.sopen = session_start
        self.buf_pts = buf_pts
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires
        self._or_high = None
        self._or_low = None
        self._or_built = False
        self._or_day = None
        self._setups_placed = False

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        # Build OR from session_start to session_start + window_min
        ss = self.sopen[0] * 60 + self.sopen[1]
        se = ss + self.window_min
        cur = hh * 60 + mn
        day_key = int(ts // 86400)
        if day_key != self._or_day:
            self._or_day = day_key
            self._or_high = None; self._or_low = None
            self._or_built = False; self._setups_placed = False
        if ss <= cur < se:
            if self._or_high is None:
                self._or_high = bh; self._or_low = bl
            else:
                self._or_high = max(self._or_high, bh)
                self._or_low = min(self._or_low, bl)
        elif cur >= se and not self._setups_placed and self._or_high is not None:
            cohort = ("orb", self.window_min, day_key)
            up = self._or_high + self.buf_pts
            dn = self._or_low - self.buf_pts
            ex_l = {'fill_mode': 'stop',
                    'stop_offset_pts': self.stop_pts,
                    'target_offset_pts': self.target_pts,
                    'cohort': cohort}
            ex_s = dict(ex_l)
            self.add_setup("LONG", "LONG", up, up - self.stop_pts,
                           up + self.target_pts, ts,
                           key=("orb_l", cohort), expires_in=self.expires, extra=ex_l)
            self.add_setup("SHORT", "SHORT", dn, dn + self.stop_pts,
                           dn - self.target_pts, ts,
                           key=("orb_s", cohort), expires_in=self.expires, extra=ex_s)
            self._setups_placed = True

    def _in_session(self, hh, mn):
        return True  # allow trade any time after OR builds


# ---------- T17: PDH/PDL fade ----------
class PDHFade(StrategyBase):
    """Track prior day high/low. Fade attempts to break PDH/PDL.
    When ask >= PDH and last close was below PDH -> SHORT (fade).
    """
    def __init__(self, name, fade=True, buf_pts=0.5,
                 stop_pts=4, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=300):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.fade = fade
        self.buf_pts = buf_pts
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires
        self._cur_day = None
        self._cur_hi = -float('inf')
        self._cur_lo = float('inf')
        self._pdh = None
        self._pdl = None
        self._last_setup_day = (None, None)

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        day = int(ts // 86400)
        if self._cur_day is None:
            self._cur_day = day
        if day != self._cur_day:
            self._pdh = self._cur_hi
            self._pdl = self._cur_lo
            self._cur_day = day
            self._cur_hi = bh
            self._cur_lo = bl
            self._last_setup_day = (None, None)
        else:
            self._cur_hi = max(self._cur_hi, bh)
            self._cur_lo = min(self._cur_lo, bl)
        if self._pdh is None:
            return
        # When current bar pierces PDH and closes below, fade SHORT
        if bh > self._pdh + 0.5 and bc <= self._pdh:
            if self._last_setup_day[0] != day:
                self._last_setup_day = (day, 'l')
                entry = bc
                side = "SHORT" if self.fade else "LONG"
                extra = {'fill_mode': 'marketable',
                         'stop_offset_pts': self.stop_pts,
                         'target_offset_pts': self.target_pts}
                if side == "SHORT":
                    self.add_setup(side, side, entry, entry + self.stop_pts,
                                   entry - self.target_pts, ts,
                                   key=("pdh_s", day),
                                   expires_in=self.expires, extra=extra)
                else:
                    self.add_setup(side, side, entry, entry - self.stop_pts,
                                   entry + self.target_pts, ts,
                                   key=("pdh_l", day),
                                   expires_in=self.expires, extra=extra)
        if bl < self._pdl - 0.5 and bc >= self._pdl:
            if self._last_setup_day[1] != 'h':
                self._last_setup_day = (day, 'h')
                entry = bc
                side = "LONG" if self.fade else "SHORT"
                extra = {'fill_mode': 'marketable',
                         'stop_offset_pts': self.stop_pts,
                         'target_offset_pts': self.target_pts}
                if side == "LONG":
                    self.add_setup(side, side, entry, entry - self.stop_pts,
                                   entry + self.target_pts, ts,
                                   key=("pdl_l", day),
                                   expires_in=self.expires, extra=extra)
                else:
                    self.add_setup(side, side, entry, entry + self.stop_pts,
                                   entry - self.target_pts, ts,
                                   key=("pdl_s", day),
                                   expires_in=self.expires, extra=extra)


# ---------- T19: Linreg slope reversal ----------
class LinRegSlopeReversal(StrategyBase):
    """Compute linreg slope over last N bars. When slope sign changes
    (and |slope| > thresh), enter in new direction with marketable.
    """
    def __init__(self, name, lookback=20, min_slope=0.05, fade=False,
                 stop_pts=4, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=60):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.lookback = lookback
        self.min_slope = min_slope
        self.fade = fade
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires
        self._prev_slope = 0.0

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.lookback:
            return
        sub = list(hist)[-self.lookback:]
        n = len(sub)
        xs = list(range(n))
        ys = [b[3] for b in sub]
        mx = sum(xs) / n
        my = sum(ys) / n
        num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
        den = sum((xs[i] - mx) ** 2 for i in range(n))
        slope = num / den if den > 0 else 0.0
        prev = self._prev_slope
        self._prev_slope = slope
        if (prev <= 0 and slope > self.min_slope) or (prev >= 0 and slope < -self.min_slope):
            side = "LONG" if slope > 0 else "SHORT"
            if self.fade:
                side = "SHORT" if side == "LONG" else "LONG"
            entry = bc
            extra = {'fill_mode': 'marketable',
                     'stop_offset_pts': self.stop_pts,
                     'target_offset_pts': self.target_pts}
            if side == "LONG":
                self.add_setup(side, side, entry, entry - self.stop_pts,
                               entry + self.target_pts, ts,
                               key=("lrs_l", round(entry, 1)),
                               expires_in=self.expires, extra=extra)
            else:
                self.add_setup(side, side, entry, entry + self.stop_pts,
                               entry - self.target_pts, ts,
                               key=("lrs_s", round(entry, 1)),
                               expires_in=self.expires, extra=extra)


# ---------- T28: Tick-rate spike ----------
class TickRateSpike(StrategyBase):
    """Track ticks/sec over rolling window. When current 10s rate >= 5x
    rolling 5min baseline, enter in direction of recent net move.
    """
    def __init__(self, name, fast_window_s=10, base_window_s=300,
                 spike_ratio=5.0, fade=False,
                 stop_pts=4, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=15,
                 cool_setup_s=30):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.fast_w = fast_window_s
        self.base_w = base_window_s
        self.spike_ratio = spike_ratio
        self.fade = fade
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires
        self.cool_setup_s = cool_setup_s
        self._ticks = deque(maxlen=20000)  # (ts, last)
        self._last_setup_ts = None

    def feed_tick(self, ts, last):
        self._ticks.append((ts, last))
        # Prune
        while self._ticks and ts - self._ticks[0][0] > self.base_w:
            self._ticks.popleft()
        if len(self._ticks) < 50:
            return
        fast_count = 0
        fast_start_px = None
        fast_end_px = self._ticks[-1][1]
        for t, px in reversed(self._ticks):
            if ts - t > self.fast_w:
                break
            fast_count += 1
            fast_start_px = px
        base_count = len(self._ticks)
        base_rate = base_count / self.base_w
        fast_rate = fast_count / max(0.1, self.fast_w)
        if base_rate <= 0:
            return
        if fast_rate < self.spike_ratio * base_rate:
            return
        if (self._last_setup_ts is not None and
                ts - self._last_setup_ts < self.cool_setup_s):
            return
        self._last_setup_ts = ts
        if fast_start_px is None:
            return
        move = fast_end_px - fast_start_px
        if abs(move) < 0.5:
            return
        side = "LONG" if move > 0 else "SHORT"
        if self.fade:
            side = "SHORT" if side == "LONG" else "LONG"
        entry = fast_end_px
        extra = {'fill_mode': 'marketable',
                 'stop_offset_pts': self.stop_pts,
                 'target_offset_pts': self.target_pts}
        if side == "LONG":
            self.add_setup(side, side, entry, entry - self.stop_pts,
                           entry + self.target_pts, ts,
                           key=("trs_l", int(ts * 10) % 10000),
                           expires_in=self.expires, extra=extra)
        else:
            self.add_setup(side, side, entry, entry + self.stop_pts,
                           entry - self.target_pts, ts,
                           key=("trs_s", int(ts * 10) % 10000),
                           expires_in=self.expires, extra=extra)


# ---------- T34: Tick-up/down cumdelta ----------
class TickCumDelta(StrategyBase):
    """Track net (up_ticks - down_ticks) over rolling window. When abs
    cumdelta exceeds thresh, enter in direction (continuation) or fade.
    """
    def __init__(self, name, window_s=60, thresh=40, fade=False,
                 stop_pts=4, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=20,
                 cool_setup_s=30):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.window_s = window_s
        self.thresh = thresh
        self.fade = fade
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires
        self.cool_setup_s = cool_setup_s
        self._ticks = deque(maxlen=50000)  # (ts, dir)
        self._last_setup_ts = None
        self._last_px = None
        self._cum = 0

    def feed_tick(self, ts, last):
        if self._last_px is not None:
            if last > self._last_px:
                d = 1
            elif last < self._last_px:
                d = -1
            else:
                d = 0
            if d != 0:
                self._ticks.append((ts, d, last))
                self._cum += d
        self._last_px = last
        # Prune
        while self._ticks and ts - self._ticks[0][0] > self.window_s:
            old_ts, old_d, _ = self._ticks.popleft()
            self._cum -= old_d
        if abs(self._cum) < self.thresh:
            return
        if (self._last_setup_ts is not None and
                ts - self._last_setup_ts < self.cool_setup_s):
            return
        self._last_setup_ts = ts
        side = "LONG" if self._cum > 0 else "SHORT"
        if self.fade:
            side = "SHORT" if side == "LONG" else "LONG"
        entry = last
        extra = {'fill_mode': 'marketable',
                 'stop_offset_pts': self.stop_pts,
                 'target_offset_pts': self.target_pts}
        if side == "LONG":
            self.add_setup(side, side, entry, entry - self.stop_pts,
                           entry + self.target_pts, ts,
                           key=("tcd_l", int(ts * 10) % 10000),
                           expires_in=self.expires, extra=extra)
        else:
            self.add_setup(side, side, entry, entry + self.stop_pts,
                           entry - self.target_pts, ts,
                           key=("tcd_s", int(ts * 10) % 10000),
                           expires_in=self.expires, extra=extra)


# ---------- T29/T30: Spread-based entries ----------
class SpreadEdge(StrategyBase):
    """Trigger on spread compression or widening. On tick, if (ask-bid)
    <= compress (or >= widen), and last bar move was X direction, enter.
    """
    def __init__(self, name, mode='compress', spread_thresh=0.5,
                 stop_pts=4, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=10,
                 cool_setup_s=20, fade=False):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.mode = mode
        self.spread_thresh = spread_thresh
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires
        self.cool_setup_s = cool_setup_s
        self.fade = fade
        self._last_bar_move = 0
        self._last_setup_ts = None
        self._spread_streak = 0

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        self._last_bar_move = bc - bo

    def feed_quote(self, ts, bid, ask, last):
        spread = ask - bid
        if self.mode == 'compress':
            cond = spread <= self.spread_thresh
        else:
            cond = spread >= self.spread_thresh
        if not cond:
            self._spread_streak = 0
            return
        self._spread_streak += 1
        if self._spread_streak < 5:
            return
        if (self._last_setup_ts is not None and
                ts - self._last_setup_ts < self.cool_setup_s):
            return
        if abs(self._last_bar_move) < 1.0:
            return
        side = "LONG" if self._last_bar_move > 0 else "SHORT"
        if self.fade:
            side = "SHORT" if side == "LONG" else "LONG"
        entry = last
        extra = {'fill_mode': 'marketable',
                 'stop_offset_pts': self.stop_pts,
                 'target_offset_pts': self.target_pts}
        self._last_setup_ts = ts
        if side == "LONG":
            self.add_setup(side, side, entry, entry - self.stop_pts,
                           entry + self.target_pts, ts,
                           key=("se_l", int(ts * 10) % 10000),
                           expires_in=self.expires, extra=extra)
        else:
            self.add_setup(side, side, entry, entry + self.stop_pts,
                           entry - self.target_pts, ts,
                           key=("se_s", int(ts * 10) % 10000),
                           expires_in=self.expires, extra=extra)


# ---------- T32/T33: VWAP / EMA RECLAIM ----------
class VWAPReclaim(StrategyBase):
    """Track price vs rolling VWAP-proxy (typical price mean). When price
    crosses from below to above VWAP (after being below for K bars),
    enter LONG marketable. Mirror for SHORT.
    """
    def __init__(self, name, lookback=50, below_k=3, fade=False,
                 stop_pts=4, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=60):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.lookback = lookback; self.below_k = below_k
        self.fade = fade
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires
        self._below_streak = 0
        self._above_streak = 0

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.lookback:
            return
        sub = list(hist)[-self.lookback:]
        vwap = sum((b[1] + b[2] + b[3]) / 3.0 for b in sub) / len(sub)
        prev_c = hist[-2][3] if len(hist) >= 2 else bc
        if prev_c < vwap:
            self._below_streak += 1
            self._above_streak = 0
        elif prev_c > vwap:
            self._above_streak += 1
            self._below_streak = 0
        # Reclaim trigger: was below for K bars, now closes above
        if self._below_streak >= self.below_k and bc > vwap:
            side = "LONG"
            if self.fade:
                side = "SHORT"
            entry = bc
            extra = {'fill_mode': 'marketable',
                     'stop_offset_pts': self.stop_pts,
                     'target_offset_pts': self.target_pts}
            if side == "LONG":
                self.add_setup(side, side, entry, entry - self.stop_pts,
                               entry + self.target_pts, ts,
                               key=("vwr_l", round(vwap, 1)),
                               expires_in=self.expires, extra=extra)
            else:
                self.add_setup(side, side, entry, entry + self.stop_pts,
                               entry - self.target_pts, ts,
                               key=("vwr_s", round(vwap, 1)),
                               expires_in=self.expires, extra=extra)
            self._below_streak = 0
        if self._above_streak >= self.below_k and bc < vwap:
            side = "SHORT"
            if self.fade:
                side = "LONG"
            entry = bc
            extra = {'fill_mode': 'marketable',
                     'stop_offset_pts': self.stop_pts,
                     'target_offset_pts': self.target_pts}
            if side == "SHORT":
                self.add_setup(side, side, entry, entry + self.stop_pts,
                               entry - self.target_pts, ts,
                               key=("vwr_s2", round(vwap, 1)),
                               expires_in=self.expires, extra=extra)
            else:
                self.add_setup(side, side, entry, entry - self.stop_pts,
                               entry + self.target_pts, ts,
                               key=("vwr_l2", round(vwap, 1)),
                               expires_in=self.expires, extra=extra)
            self._above_streak = 0


# ---------- T41: Stop-run reversal ----------
class StopRunReversal(StrategyBase):
    """When price spikes >= sweep_pts above recent N-bar high in single
    bar AND closes back BELOW the prior high, fade SHORT marketable.
    Mirror for low.
    """
    def __init__(self, name, lookback=30, sweep_pts=4.0,
                 stop_pts=4, target_pts=15, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=60):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.lookback = lookback
        self.sweep_pts = sweep_pts
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.lookback + 1:
            return
        prior = list(hist)[-(self.lookback+1):-1]
        ph = max(b[1] for b in prior)
        pl = min(b[2] for b in prior)
        # Sweep above + close below ph by significant margin
        if bh >= ph + self.sweep_pts and bc < ph - 0.5:
            entry = bc
            extra = {'fill_mode': 'marketable',
                     'stop_offset_pts': self.stop_pts,
                     'target_offset_pts': self.target_pts}
            self.add_setup("SHORT", "SHORT", entry, entry + self.stop_pts,
                           entry - self.target_pts, ts,
                           key=("srr_s", round(ph, 1)),
                           expires_in=self.expires, extra=extra)
        if bl <= pl - self.sweep_pts and bc > pl + 0.5:
            entry = bc
            extra = {'fill_mode': 'marketable',
                     'stop_offset_pts': self.stop_pts,
                     'target_offset_pts': self.target_pts}
            self.add_setup("LONG", "LONG", entry, entry - self.stop_pts,
                           entry + self.target_pts, ts,
                           key=("srr_l", round(pl, 1)),
                           expires_in=self.expires, extra=extra)


# ---------- T50/T51: Pivot points (classical) ----------
class DailyPivots(StrategyBase):
    """Compute classical pivot S1/S2/R1/R2 from prior day OHLC. Fade
    bounces off them with marketable-LIMIT.
    """
    def __init__(self, name, level='R1', fade=True,
                 stop_pts=4, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=300, buf_pts=0.5):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.level = level
        self.fade = fade
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.expires = expires
        self.buf_pts = buf_pts
        self._cur_day = None
        self._cur_hi = -float('inf')
        self._cur_lo = float('inf')
        self._cur_close = None
        self._levels = {}

    def _compute_levels(self, H, L, C):
        P = (H + L + C) / 3.0
        R1 = 2 * P - L; S1 = 2 * P - H
        R2 = P + (H - L); S2 = P - (H - L)
        R3 = H + 2 * (P - L); S3 = L - 2 * (H - P)
        return {'P': P, 'R1': R1, 'R2': R2, 'R3': R3,
                'S1': S1, 'S2': S2, 'S3': S3}

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        day = int(ts // 86400)
        if self._cur_day is None:
            self._cur_day = day
            self._cur_hi = bh; self._cur_lo = bl; self._cur_close = bc
        elif day != self._cur_day:
            if self._cur_close is not None:
                self._levels = self._compute_levels(
                    self._cur_hi, self._cur_lo, self._cur_close)
            self._cur_day = day
            self._cur_hi = bh; self._cur_lo = bl; self._cur_close = bc
        else:
            self._cur_hi = max(self._cur_hi, bh)
            self._cur_lo = min(self._cur_lo, bl)
            self._cur_close = bc
        if not self._levels or self.level not in self._levels:
            return
        lvl = self._levels[self.level]
        # Bar touched or crossed level then closed back
        if self.level.startswith('R'):
            # Resistance: fade SHORT when bar pierces and closes below
            if bh >= lvl - self.buf_pts and bc < lvl - 0.5:
                entry = bc
                side = "SHORT" if self.fade else "LONG"
                extra = {'fill_mode': 'marketable',
                         'stop_offset_pts': self.stop_pts,
                         'target_offset_pts': self.target_pts}
                if side == "SHORT":
                    self.add_setup(side, side, entry, entry + self.stop_pts,
                                   entry - self.target_pts, ts,
                                   key=("piv_s", self.level, day),
                                   expires_in=self.expires, extra=extra)
                else:
                    self.add_setup(side, side, entry, entry - self.stop_pts,
                                   entry + self.target_pts, ts,
                                   key=("piv_l", self.level, day),
                                   expires_in=self.expires, extra=extra)
        else:
            if bl <= lvl + self.buf_pts and bc > lvl + 0.5:
                entry = bc
                side = "LONG" if self.fade else "SHORT"
                extra = {'fill_mode': 'marketable',
                         'stop_offset_pts': self.stop_pts,
                         'target_offset_pts': self.target_pts}
                if side == "LONG":
                    self.add_setup(side, side, entry, entry - self.stop_pts,
                                   entry + self.target_pts, ts,
                                   key=("piv_l2", self.level, day),
                                   expires_in=self.expires, extra=extra)
                else:
                    self.add_setup(side, side, entry, entry + self.stop_pts,
                                   entry - self.target_pts, ts,
                                   key=("piv_s2", self.level, day),
                                   expires_in=self.expires, extra=extra)


# ---------- T52: Fibonacci extension projection ----------
class FibExtension(StrategyBase):
    """After an N-bar impulse with retracement to >= 0.618, target the
    1.272 / 1.618 extension. STOP entry on break of retracement bar's
    high/low in impulse direction.
    """
    def __init__(self, name, impulse_pts=8.0, impulse_bars=5,
                 retrace_min=0.5, ext_target=1.272,
                 stop_pts=5, target_pts=None, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=300):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.impulse_pts = impulse_pts
        self.impulse_bars = impulse_bars
        self.retrace_min = retrace_min
        self.ext_target = ext_target
        self.stop_pts = stop_pts
        self.target_pts = target_pts
        self.expires = expires

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.impulse_bars + 1:
            return
        win = list(hist)[-self.impulse_bars:]
        net = win[-1][3] - win[0][0]
        if abs(net) < self.impulse_pts:
            return
        ih = max(b[1] for b in win)
        il = min(b[2] for b in win)
        rng = ih - il
        if rng <= 0:
            return
        # Check retracement: current bar close
        if net > 0:
            # Up impulse: retracement = (ih - bc) / rng
            retr = (ih - bc) / rng
            if retr < self.retrace_min:
                return
            # Target the 1.272 ext = ih + 0.272 * rng
            tgt_pts = self.target_pts if self.target_pts is not None else (self.ext_target - 1.0) * rng + (ih - bc)
            up_entry = bh + 0.5
            extra = {'fill_mode': 'stop',
                     'stop_offset_pts': self.stop_pts,
                     'target_offset_pts': tgt_pts}
            self.add_setup("LONG", "LONG", up_entry, up_entry - self.stop_pts,
                           up_entry + tgt_pts, ts,
                           key=("fext_l", round(ih, 1), round(il, 1)),
                           expires_in=self.expires, extra=extra)
        else:
            retr = (bc - il) / rng
            if retr < self.retrace_min:
                return
            tgt_pts = self.target_pts if self.target_pts is not None else (self.ext_target - 1.0) * rng + (bc - il)
            dn_entry = bl - 0.5
            extra = {'fill_mode': 'stop',
                     'stop_offset_pts': self.stop_pts,
                     'target_offset_pts': tgt_pts}
            self.add_setup("SHORT", "SHORT", dn_entry, dn_entry + self.stop_pts,
                           dn_entry - tgt_pts, ts,
                           key=("fext_s", round(ih, 1), round(il, 1)),
                           expires_in=self.expires, extra=extra)


# ---------- T36: OCO multi-level fibonacci pullback ----------
class OCOFibPullback(StrategyBase):
    """After N-bar impulse, place THREE LIMITs at 0.236, 0.382, 0.5 of
    impulse range. First fill wins. INVERT version: trade against impulse.
    """
    def __init__(self, name, impulse_pts=5.0, impulse_bars=4,
                 stop_pts=5, target_pts=15, invert=True, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=300):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.impulse_pts = impulse_pts
        self.impulse_bars = impulse_bars
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.invert = invert
        self.expires = expires

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.impulse_bars:
            return
        win = list(hist)[-self.impulse_bars:]
        net = win[-1][3] - win[0][0]
        if abs(net) < self.impulse_pts:
            return
        ih = max(b[1] for b in win)
        il = min(b[2] for b in win)
        rng = ih - il
        if rng <= 0:
            return
        orig_side = "LONG" if net > 0 else "SHORT"
        side = "SHORT" if (orig_side == "LONG" and self.invert) else (
            "LONG" if (orig_side == "SHORT" and self.invert) else orig_side)
        cohort = ("ocof", round(ih, 1), round(il, 1), orig_side, ts)
        for pp in [0.236, 0.382, 0.5]:
            if orig_side == "LONG":
                entry = ih - pp * rng
            else:
                entry = il + pp * rng
            extra = {'fill_mode': 'marketable',
                     'stop_offset_pts': self.stop_pts,
                     'target_offset_pts': self.target_pts,
                     'cohort': cohort}
            if side == "LONG":
                self.add_setup(side, orig_side, entry, entry - self.stop_pts,
                               entry + self.target_pts, ts,
                               key=("ocof_l", cohort, int(pp * 1000)),
                               expires_in=self.expires, extra=extra)
            else:
                self.add_setup(side, orig_side, entry, entry + self.stop_pts,
                               entry - self.target_pts, ts,
                               key=("ocof_s", cohort, int(pp * 1000)),
                               expires_in=self.expires, extra=extra)


# ---------- T44: Realized-vol regime ----------
class VolRegimePullback(StrategyBase):
    """Compute rolling realized vol (std of returns over N bars). Trade
    pullback ONLY when vol regime in [vol_min, vol_max]. Marketable.
    """
    def __init__(self, name, vol_min=1.0, vol_max=4.0,
                 vol_bars=30, impulse_pts=5.0, impulse_bars=4,
                 pull_pct=0.382, stop_pts=5, target_pts=15,
                 invert=True, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=300):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.vol_min = vol_min; self.vol_max = vol_max
        self.vol_bars = vol_bars
        self.impulse_pts = impulse_pts
        self.impulse_bars = impulse_bars
        self.pull_pct = pull_pct
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.invert = invert
        self.expires = expires

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < max(self.impulse_bars, self.vol_bars) + 1:
            return
        sub = list(hist)[-self.vol_bars:]
        rets = [sub[i][3] - sub[i-1][3] for i in range(1, len(sub))]
        if not rets:
            return
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / len(rets)
        std = math.sqrt(var)
        if std < self.vol_min or std > self.vol_max:
            return
        win = list(hist)[-self.impulse_bars:]
        net = win[-1][3] - win[0][0]
        if abs(net) < self.impulse_pts:
            return
        ih = max(b[1] for b in win)
        il = min(b[2] for b in win)
        rng = ih - il
        orig_side = "LONG" if net > 0 else "SHORT"
        side = ("SHORT" if orig_side == "LONG" else "LONG") if self.invert else orig_side
        if orig_side == "LONG":
            entry = ih - self.pull_pct * rng
        else:
            entry = il + self.pull_pct * rng
        extra = {'fill_mode': 'marketable',
                 'stop_offset_pts': self.stop_pts,
                 'target_offset_pts': self.target_pts}
        if side == "LONG":
            self.add_setup(side, orig_side, entry, entry - self.stop_pts,
                           entry + self.target_pts, ts,
                           key=("vrp_l", round(ih, 1), round(il, 1)),
                           expires_in=self.expires, extra=extra)
        else:
            self.add_setup(side, orig_side, entry, entry + self.stop_pts,
                           entry - self.target_pts, ts,
                           key=("vrp_s", round(ih, 1), round(il, 1)),
                           expires_in=self.expires, extra=extra)


# ---------- T54: Multi-timeframe confluence ----------
class MTFConfluence(StrategyBase):
    """1m bar pullback ONLY in direction of 5m bar trend (last 5m close
    above/below 5m SMA over K bars).
    """
    def __init__(self, name, impulse_pts=5.0, impulse_bars=4,
                 pull_pct=0.382, stop_pts=5, target_pts=15,
                 invert=False, htf_sma_bars=10,
                 cooldown_s=10, session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, expires=300):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.impulse_pts = impulse_pts
        self.impulse_bars = impulse_bars
        self.pull_pct = pull_pct
        self.stop_pts = stop_pts; self.target_pts = target_pts
        self.invert = invert
        self.htf_sma_bars = htf_sma_bars
        self.expires = expires
        # Maintain a 5-bar synthetic HTF on closes of 5 consecutive 1m bars
        self._htf_closes = deque(maxlen=200)
        self._tail_count = 0
        self._tail_sum = 0

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        # Build 5m proxy: sample every 5 minutes (mn % 5 == 0).
        if mn % 5 == 0:
            self._htf_closes.append(bc)
        if len(hist) < self.impulse_bars or len(self._htf_closes) < self.htf_sma_bars:
            return
        htf_sub = list(self._htf_closes)[-self.htf_sma_bars:]
        htf_sma = sum(htf_sub) / len(htf_sub)
        htf_bias = 1 if bc > htf_sma else (-1 if bc < htf_sma else 0)
        if htf_bias == 0:
            return
        win = list(hist)[-self.impulse_bars:]
        net = win[-1][3] - win[0][0]
        if abs(net) < self.impulse_pts:
            return
        ih = max(b[1] for b in win)
        il = min(b[2] for b in win)
        rng = ih - il
        if rng <= 0:
            return
        orig_side = "LONG" if net > 0 else "SHORT"
        # Only trade pullback to HTF bias
        want_side = "LONG" if htf_bias > 0 else "SHORT"
        side = ("SHORT" if orig_side == "LONG" else "LONG") if self.invert else orig_side
        if side != want_side:
            return
        if orig_side == "LONG":
            entry = ih - self.pull_pct * rng
        else:
            entry = il + self.pull_pct * rng
        extra = {'fill_mode': 'marketable',
                 'stop_offset_pts': self.stop_pts,
                 'target_offset_pts': self.target_pts}
        if side == "LONG":
            self.add_setup(side, orig_side, entry, entry - self.stop_pts,
                           entry + self.target_pts, ts,
                           key=("mtf_l", round(ih, 1), round(il, 1)),
                           expires_in=self.expires, extra=extra)
        else:
            self.add_setup(side, orig_side, entry, entry + self.stop_pts,
                           entry - self.target_pts, ts,
                           key=("mtf_s", round(ih, 1), round(il, 1)),
                           expires_in=self.expires, extra=extra)


# =============================================================================
# Build the strategy library — 200+ variants
# =============================================================================
def build_variants_round7():
    v1m = []
    v15s = []
    v30s = []
    vtick = []  # tick-fed strategies (TickRateSpike, TickCumDelta)
    vquote = []  # quote-fed strategies (SpreadEdge)

    # ----------------------------------------
    # T01 — Trailing-stop variants on marketable pullback
    # ----------------------------------------
    def _mkpb_with_trail(name, **kwargs):
        ms = MarketablePullback(name, impulse_pts=5.0, impulse_bars=4,
                                pull_pct=0.236, stop_pts=10, target_pts=30,
                                invert=True, max_hold=MAX_HOLD_S)
        # Patch on_bar_close to add trail to extras
        orig_obc = ms.on_bar_close
        trail = kwargs.get('trail')
        be_trig = kwargs.get('be_trig')
        be_off = kwargs.get('be_off', 0.0)

        def patched(ts, hh, mn, bo, bh, bl, bc, hist):
            pre = len(ms.pending)
            orig_obc(ts, hh, mn, bo, bh, bl, bc, hist)
            for s in ms.pending[pre:]:
                if trail is not None:
                    s['trail_pts'] = trail
                if be_trig is not None:
                    s['be_trig_pts'] = be_trig
                    s['be_off_pts'] = be_off
        ms.on_bar_close = patched
        return ms

    for trail in [2, 3, 5, 8]:
        v1m.append(_mkpb_with_trail(f"T01_PB_trail{trail}", trail=trail))
    for be_trig, be_off in [(3, 0.0), (5, 0.0), (5, 1.0), (8, 2.0)]:
        v1m.append(_mkpb_with_trail(
            f"T01_PB_be{be_trig}o{int(be_off*10)}",
            be_trig=be_trig, be_off=be_off))
    # Trailing + BE combo
    for trail in [3, 5]:
        for be_trig in [3, 5]:
            v1m.append(_mkpb_with_trail(
                f"T01_PB_trail{trail}_be{be_trig}",
                trail=trail, be_trig=be_trig))

    # ----------------------------------------
    # T02 — Time-decay exits
    # ----------------------------------------
    def _mkpb_time_decay(name, decay_secs, need_pts):
        ms = MarketablePullback(name, impulse_pts=5.0, impulse_bars=4,
                                pull_pct=0.236, stop_pts=8, target_pts=20,
                                invert=True, max_hold=MAX_HOLD_S)
        orig_obc = ms.on_bar_close
        def patched(ts, hh, mn, bo, bh, bl, bc, hist):
            pre = len(ms.pending)
            orig_obc(ts, hh, mn, bo, bh, bl, bc, hist)
            for s in ms.pending[pre:]:
                s['time_decay'] = (decay_secs, need_pts)
        ms.on_bar_close = patched
        return ms

    for decay_s, pts in [(60, 1), (120, 2), (180, 3), (60, 3), (300, 5)]:
        v1m.append(_mkpb_time_decay(
            f"T02_PB_decay{decay_s}_p{pts}", decay_s, pts))

    # ----------------------------------------
    # T03 — Momentum-shift K-tick reverse exit
    # ----------------------------------------
    def _mkpb_mshift(name, k):
        ms = MarketablePullback(name, impulse_pts=5.0, impulse_bars=4,
                                pull_pct=0.236, stop_pts=8, target_pts=20,
                                invert=True, max_hold=MAX_HOLD_S)
        orig_obc = ms.on_bar_close
        def patched(ts, hh, mn, bo, bh, bl, bc, hist):
            pre = len(ms.pending)
            orig_obc(ts, hh, mn, bo, bh, bl, bc, hist)
            for s in ms.pending[pre:]:
                s['momshift_k'] = k
        ms.on_bar_close = patched
        return ms

    for k in [3, 5, 8, 12]:
        v1m.append(_mkpb_mshift(f"T03_PB_mshift{k}", k))

    # ----------------------------------------
    # T05 — Range-compression breakout
    # ----------------------------------------
    for n in [10, 20, 30]:
        for atr_max in [2.0, 3.0, 4.0]:
            for k in [3, 4, 6]:
                for stop, tgt in [(3, 9), (4, 12), (5, 15), (4, 20)]:
                    name = f"T05_RCB_n{n}_a{int(atr_max*10)}_k{k}_s{stop}t{tgt}"
                    v1m.append(RangeCompressionBreakout(
                        name, n_bars=n, compress_atr_max=atr_max,
                        k_consec=k, stop_pts=stop, target_pts=tgt))

    # ----------------------------------------
    # T06 — Wick exhaustion fade
    # ----------------------------------------
    for wick, ratio in [(4, 2.0), (5, 2.0), (6, 2.5), (8, 3.0), (10, 3.0)]:
        for stop, tgt in [(3, 9), (4, 12), (5, 15)]:
            name = f"T06_WEX_w{wick}_r{int(ratio*10)}_s{stop}t{tgt}"
            v1m.append(WickExhaustionFade(
                name, min_wick_pts=wick, wick_ratio=ratio,
                stop_pts=stop, target_pts=tgt))

    # ----------------------------------------
    # T07 — Inside-bar break
    # ----------------------------------------
    for n_in in [2, 3]:
        for stop, tgt in [(3, 9), (4, 12), (5, 15), (5, 20)]:
            name = f"T07_IBB_n{n_in}_s{stop}t{tgt}"
            v1m.append(InsideBarBreak(
                name, n_inside=n_in, stop_pts=stop, target_pts=tgt))

    # ----------------------------------------
    # T08 — Candle patterns
    # ----------------------------------------
    for pat in ['hammer', 'shooting_star', 'doji']:
        for stop, tgt in [(3, 9), (4, 12), (5, 15), (4, 16)]:
            name = f"T08_{pat[:3].upper()}_s{stop}t{tgt}"
            v1m.append(CandlePattern(
                name, pattern=pat, stop_pts=stop, target_pts=tgt))

    # ----------------------------------------
    # T10 — EMA crossover (and fade variant)
    # ----------------------------------------
    for fast, slow in [(5, 13), (9, 21), (12, 26), (8, 34)]:
        for stop, tgt in [(3, 9), (4, 12), (5, 15)]:
            name = f"T10_EMAX_{fast}_{slow}_s{stop}t{tgt}"
            v1m.append(EMACross(
                name, fast=fast, slow=slow,
                stop_pts=stop, target_pts=tgt))
            name = f"T10_EMAX_{fast}_{slow}_s{stop}t{tgt}_FADE"
            v1m.append(EMACross(
                name, fast=fast, slow=slow,
                stop_pts=stop, target_pts=tgt, fade=True))

    # ----------------------------------------
    # T11 — Fractal pivot fade
    # ----------------------------------------
    for fade in [True, False]:
        for stop, tgt in [(3, 9), (4, 12), (5, 15), (5, 20)]:
            name = f"T11_FP_{'fade' if fade else 'follow'}_s{stop}t{tgt}"
            v1m.append(FractalPivot(
                name, fade=fade, stop_pts=stop, target_pts=tgt))

    # ----------------------------------------
    # T13 — Range expansion percentile
    # ----------------------------------------
    for lk in [20, 40]:
        for pct in [0.85, 0.90, 0.95]:
            for fade in [True, False]:
                for stop, tgt in [(4, 12), (5, 15), (5, 20)]:
                    name = f"T13_REX_lk{lk}_p{int(pct*100)}_{'fade' if fade else 'flw'}_s{stop}t{tgt}"
                    v1m.append(RangeExpansion(
                        name, lookback=lk, pct_thresh=pct, fade=fade,
                        stop_pts=stop, target_pts=tgt))

    # ----------------------------------------
    # T15 — Heikin-Ashi color change
    # ----------------------------------------
    for n_streak in [2, 3, 5]:
        for fade in [False, True]:
            for stop, tgt in [(3, 9), (4, 12), (5, 15)]:
                name = f"T15_HA_n{n_streak}_{'fade' if fade else 'flw'}_s{stop}t{tgt}"
                v1m.append(HeikinAshiColorChange(
                    name, n_streak=n_streak, fade=fade,
                    stop_pts=stop, target_pts=tgt))

    # ----------------------------------------
    # T16 — ORB battery (5/10/15/30/60min)
    # ----------------------------------------
    for win in [5, 10, 15, 30, 60]:
        for ss in [(13, 30), (14, 30), (22, 0)]:  # NYO, RTH+1, CME
            for stop, tgt in [(4, 12), (5, 15), (8, 24), (10, 30)]:
                name = f"T16_ORB_w{win}_o{ss[0]:02d}{ss[1]:02d}_s{stop}t{tgt}"
                v1m.append(ORB(
                    name, window_min=win, session_start=ss,
                    stop_pts=stop, target_pts=tgt))

    # ----------------------------------------
    # T17 — PDH/PDL fade and follow
    # ----------------------------------------
    for fade in [True, False]:
        for stop, tgt in [(4, 12), (5, 15), (5, 20), (8, 24)]:
            name = f"T17_PDH_{'fade' if fade else 'flw'}_s{stop}t{tgt}"
            v1m.append(PDHFade(
                name, fade=fade, stop_pts=stop, target_pts=tgt))

    # ----------------------------------------
    # T19 — Linreg slope reversal
    # ----------------------------------------
    for lk in [10, 20, 30]:
        for slope_min in [0.02, 0.05, 0.1]:
            for fade in [False, True]:
                for stop, tgt in [(4, 12), (5, 15)]:
                    name = f"T19_LRS_lk{lk}_sl{int(slope_min*100)}_{'fade' if fade else 'flw'}_s{stop}t{tgt}"
                    v1m.append(LinRegSlopeReversal(
                        name, lookback=lk, min_slope=slope_min, fade=fade,
                        stop_pts=stop, target_pts=tgt))

    # ----------------------------------------
    # T22/T23 — CME-open drive / fade
    # ----------------------------------------
    for win in [5, 10, 15, 30]:
        for stop, tgt in [(5, 15), (5, 20), (8, 24)]:
            v1m.append(ORB(
                f"T22_CME_DRV_w{win}_s{stop}t{tgt}",
                window_min=win, session_start=(22, 0),
                stop_pts=stop, target_pts=tgt))

    # ----------------------------------------
    # T24 — NYSE open windows
    # ----------------------------------------
    for win in [5, 10, 15, 30]:
        for stop, tgt in [(5, 15), (5, 20), (8, 24)]:
            v1m.append(ORB(
                f"T24_NYO_DRV_w{win}_s{stop}t{tgt}",
                window_min=win, session_start=(13, 30),
                stop_pts=stop, target_pts=tgt))
            v1m.append(ORB(
                f"T24_NYC_DRV_w{win}_s{stop}t{tgt}",
                window_min=win, session_start=(14, 30),
                stop_pts=stop, target_pts=tgt))

    # ----------------------------------------
    # T25 — Lunch fade (17:00-18:00 UTC)
    # ----------------------------------------
    for stop, tgt in [(4, 12), (5, 15)]:
        v1m.append(MarketablePullback(
            f"T25_LUNCH_pp236_s{stop}t{tgt}",
            impulse_pts=3.0, impulse_bars=4, pull_pct=0.236,
            stop_pts=stop, target_pts=tgt, invert=True,
            session_start=(17, 0), session_end=(18, 0)))

    # ----------------------------------------
    # T26 — News-window narrow scalps (12:30, 13:30, 14:00 UTC)
    # ----------------------------------------
    for hour, minute in [(12, 30), (13, 30), (14, 0), (18, 0)]:
        end_min = (minute + 15) % 60
        end_hr = hour + ((minute + 15) // 60)
        for stop, tgt in [(5, 15), (8, 24)]:
            v1m.append(MarketablePullback(
                f"T26_NEWS_{hour:02d}{minute:02d}_s{stop}t{tgt}",
                impulse_pts=4.0, impulse_bars=3, pull_pct=0.236,
                stop_pts=stop, target_pts=tgt, invert=True,
                session_start=(hour, minute), session_end=(end_hr, end_min)))

    # ----------------------------------------
    # T28 — Tick-rate spike
    # ----------------------------------------
    for fast, base in [(10, 300), (15, 600)]:
        for ratio in [3.0, 5.0, 8.0]:
            for fade in [False, True]:
                for stop, tgt in [(3, 9), (4, 12)]:
                    name = f"T28_TRS_f{fast}b{base}_r{int(ratio*10)}_{'fade' if fade else 'flw'}_s{stop}t{tgt}"
                    vtick.append(TickRateSpike(
                        name, fast_window_s=fast, base_window_s=base,
                        spike_ratio=ratio, fade=fade,
                        stop_pts=stop, target_pts=tgt))

    # ----------------------------------------
    # T29/T30 — Spread compression / widening
    # ----------------------------------------
    for thr in [0.25, 0.5, 0.75, 1.0]:
        for fade in [False, True]:
            for stop, tgt in [(3, 9), (4, 12)]:
                vquote.append(SpreadEdge(
                    f"T29_SC_{int(thr*100)}_{'fade' if fade else 'flw'}_s{stop}t{tgt}",
                    mode='compress', spread_thresh=thr, fade=fade,
                    stop_pts=stop, target_pts=tgt))
                vquote.append(SpreadEdge(
                    f"T30_SW_{int(thr*100)}_{'fade' if fade else 'flw'}_s{stop}t{tgt}",
                    mode='widen', spread_thresh=thr, fade=fade,
                    stop_pts=stop, target_pts=tgt))

    # ----------------------------------------
    # T32 — VWAP / EMA reclaim
    # ----------------------------------------
    for lk in [30, 50, 100]:
        for k in [2, 3, 5]:
            for fade in [False, True]:
                for stop, tgt in [(4, 12), (5, 15)]:
                    name = f"T32_VWR_lk{lk}_k{k}_{'fade' if fade else 'flw'}_s{stop}t{tgt}"
                    v1m.append(VWAPReclaim(
                        name, lookback=lk, below_k=k, fade=fade,
                        stop_pts=stop, target_pts=tgt))

    # ----------------------------------------
    # T34 — Tick cumdelta
    # ----------------------------------------
    for win in [30, 60, 120]:
        for thresh in [30, 50, 100]:
            for fade in [False, True]:
                for stop, tgt in [(3, 9), (4, 12)]:
                    name = f"T34_TCD_w{win}_t{thresh}_{'fade' if fade else 'flw'}_s{stop}t{tgt}"
                    vtick.append(TickCumDelta(
                        name, window_s=win, thresh=thresh, fade=fade,
                        stop_pts=stop, target_pts=tgt))

    # ----------------------------------------
    # T36 — OCO multi-level fib pullback (invert)
    # ----------------------------------------
    for imp in [4.0, 6.0, 8.0]:
        for stop, tgt in [(5, 15), (8, 24), (10, 30)]:
            v1m.append(OCOFibPullback(
                f"T36_OCOF_imp{int(imp)}_s{stop}t{tgt}_INV",
                impulse_pts=imp, impulse_bars=4,
                stop_pts=stop, target_pts=tgt, invert=True))
            v1m.append(OCOFibPullback(
                f"T36_OCOF_imp{int(imp)}_s{stop}t{tgt}_CONT",
                impulse_pts=imp, impulse_bars=4,
                stop_pts=stop, target_pts=tgt, invert=False))

    # ----------------------------------------
    # T38 — Wide stop + trail (cap loss/free run)
    # ----------------------------------------
    for stop, trail in [(20, 5), (15, 3), (25, 8), (30, 10)]:
        ms = MarketablePullback(
            f"T38_WIDESTOP_s{stop}_trail{trail}",
            impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
            stop_pts=stop, target_pts=stop * 4, invert=True)
        orig_obc = ms.on_bar_close
        _trail_v = trail
        def make_patched(_ms, _orig, _trail):
            def patched(ts, hh, mn, bo, bh, bl, bc, hist):
                pre = len(_ms.pending)
                _orig(ts, hh, mn, bo, bh, bl, bc, hist)
                for s in _ms.pending[pre:]:
                    s['trail_pts'] = _trail
                    s['be_trig_pts'] = _trail
            return patched
        ms.on_bar_close = make_patched(ms, orig_obc, _trail_v)
        v1m.append(ms)

    # ----------------------------------------
    # T40 — Asymmetric R:R (tiny stop, huge target)
    # ----------------------------------------
    for stop, tgt in [(2, 30), (2, 50), (3, 45), (1.5, 30)]:
        v1m.append(MarketablePullback(
            f"T40_ASYM_s{int(stop*10)}_t{tgt}",
            impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
            stop_pts=stop, target_pts=tgt, invert=True))

    # ----------------------------------------
    # T41 — Stop-run reversal
    # ----------------------------------------
    for lk in [20, 30, 50]:
        for sw in [3.0, 5.0, 8.0]:
            for stop, tgt in [(4, 12), (5, 15), (5, 20)]:
                name = f"T41_SRR_lk{lk}_sw{int(sw)}_s{stop}t{tgt}"
                v1m.append(StopRunReversal(
                    name, lookback=lk, sweep_pts=sw,
                    stop_pts=stop, target_pts=tgt))

    # ----------------------------------------
    # T44 — Vol-regime pullback
    # ----------------------------------------
    for vmin, vmax in [(0.5, 2.0), (1.0, 3.0), (2.0, 5.0), (3.0, 8.0)]:
        for stop, tgt in [(4, 12), (5, 15), (8, 24)]:
            name = f"T44_VRP_v{int(vmin*10)}-{int(vmax*10)}_s{stop}t{tgt}"
            v1m.append(VolRegimePullback(
                name, vol_min=vmin, vol_max=vmax,
                stop_pts=stop, target_pts=tgt))

    # ----------------------------------------
    # T50/T51 — Pivot points
    # ----------------------------------------
    for lvl in ['R1', 'R2', 'S1', 'S2']:
        for stop, tgt in [(4, 12), (5, 15), (5, 20)]:
            for fade in [True, False]:
                name = f"T50_PIV_{lvl}_{'fade' if fade else 'flw'}_s{stop}t{tgt}"
                v1m.append(DailyPivots(
                    name, level=lvl, fade=fade,
                    stop_pts=stop, target_pts=tgt))

    # ----------------------------------------
    # T52 — Fib extension projection (STOP entry on continuation break)
    # ----------------------------------------
    for imp in [5.0, 8.0, 12.0]:
        for retr in [0.382, 0.5, 0.618]:
            for stop in [4, 6, 8]:
                name = f"T52_FEXT_imp{int(imp)}_r{int(retr*1000)}_s{stop}"
                v1m.append(FibExtension(
                    name, impulse_pts=imp, retrace_min=retr,
                    stop_pts=stop))

    # ----------------------------------------
    # T54 — MTF confluence pullback (1m + 5m bias)
    # ----------------------------------------
    for imp in [4.0, 6.0]:
        for pp in [0.236, 0.382]:
            for stop, tgt in [(4, 12), (5, 15), (5, 20)]:
                # Follow trend
                v1m.append(MTFConfluence(
                    f"T54_MTF_imp{int(imp)}_pp{int(pp*1000)}_s{stop}t{tgt}_FLW",
                    impulse_pts=imp, impulse_bars=4, pull_pct=pp,
                    stop_pts=stop, target_pts=tgt, invert=False))
                # Fade against trend (low conviction but worth checking)
                v1m.append(MTFConfluence(
                    f"T54_MTF_imp{int(imp)}_pp{int(pp*1000)}_s{stop}t{tgt}_INV",
                    impulse_pts=imp, impulse_bars=4, pull_pct=pp,
                    stop_pts=stop, target_pts=tgt, invert=True))

    # ----------------------------------------
    # 15s variants of best classes (extra coverage)
    # ----------------------------------------
    for stop, tgt in [(3, 9), (4, 12)]:
        v15s.append(RangeCompressionBreakout(
            f"T05_15s_RCB_s{stop}t{tgt}", n_bars=20, compress_atr_max=2.0,
            k_consec=3, stop_pts=stop, target_pts=tgt, max_hold=120))
        v15s.append(InsideBarBreak(
            f"T07_15s_IBB_s{stop}t{tgt}", n_inside=2,
            stop_pts=stop, target_pts=tgt, max_hold=120))
        v15s.append(EMACross(
            f"T10_15s_EMA9_21_s{stop}t{tgt}", fast=9, slow=21,
            stop_pts=stop, target_pts=tgt, max_hold=120))
        v15s.append(WickExhaustionFade(
            f"T06_15s_WEX_s{stop}t{tgt}", min_wick_pts=2.0, wick_ratio=2.0,
            stop_pts=stop, target_pts=tgt, max_hold=120))

    # ----------------------------------------
    # 30s variants
    # ----------------------------------------
    for stop, tgt in [(3, 9), (4, 12)]:
        v30s.append(RangeCompressionBreakout(
            f"T05_30s_RCB_s{stop}t{tgt}", n_bars=20, compress_atr_max=2.5,
            k_consec=3, stop_pts=stop, target_pts=tgt, max_hold=180))
        v30s.append(EMACross(
            f"T10_30s_EMA9_21_s{stop}t{tgt}", fast=9, slow=21,
            stop_pts=stop, target_pts=tgt, max_hold=180))

    # Attach executor
    all_lists = [v1m, v15s, v30s, vtick, vquote]
    n_total = 0
    for ls in all_lists:
        for s in ls:
            attach_r7_executor(s)
            n_total += 1
    return v1m, v15s, v30s, vtick, vquote, n_total


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
        print(f"[round7] checkpoint load failed: {e!r}", file=sys.stderr)
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


def _report(strat, total_days):
    n = len(strat.completed)
    if n == 0:
        return {
            'name': strat.name, 'n': 0, 'wr': 0.0, 'net': 0.0,
            'per_day': 0.0, 'per_trade': 0.0, 'pos_d': 0, 'neg_d': 0,
            'worst': 0.0, 'best': 0.0, 'max_dd': 0.0,
            'trades_per_day': 0.0, 'sharpe': 0.0, 'n_days': 0,
        }
    wins = sum(1 for c in strat.completed if c[0] > 0)
    wr = wins / n
    net = sum(c[0] for c in strat.completed)
    per_day = net / max(1, total_days)
    per_trade = net / n
    trades_per_day = n / max(1, total_days)
    day_nets = [sum(strat.by_day[d]) for d in strat.by_day]
    n_days = len(day_nets)
    pos_d = sum(1 for x in day_nets if x > 0)
    neg_d = sum(1 for x in day_nets if x < 0)
    worst = min(day_nets) if day_nets else 0.0
    best = max(day_nets) if day_nets else 0.0
    cum = 0.0; peak = 0.0; max_dd = 0.0
    for c in strat.completed:
        cum += c[0]
        if cum > peak: peak = cum
        if peak - cum > max_dd: max_dd = peak - cum
    if n_days > 1:
        mean = sum(day_nets) / n_days
        var = sum((x - mean) ** 2 for x in day_nets) / (n_days - 1)
        std = math.sqrt(var)
        sharpe = (mean / std) if std > 0 else 0.0
    else:
        sharpe = 0.0
    return {
        'name': strat.name, 'n': n, 'wr': wr, 'net': net,
        'per_day': per_day, 'per_trade': per_trade,
        'pos_d': pos_d, 'neg_d': neg_d, 'worst': worst, 'best': best,
        'max_dd': max_dd, 'trades_per_day': trades_per_day,
        'sharpe': sharpe, 'n_days': n_days,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offset", type=int, default=DEFAULT_OFFSET)
    ap.add_argument("--ckpt-suffix", default="")
    ap.add_argument("--max-days", type=int, default=14)
    args = ap.parse_args()

    ckpt_path = ("/home/user/HFTBot/research/round7_checkpoint"
                 f"{args.ckpt_suffix}.pkl")
    csv_path = ("/home/user/HFTBot/research/round7_summary"
                f"{args.ckpt_suffix}.csv")
    md_path = ("/home/user/HFTBot/research/round7_results"
               f"{args.ckpt_suffix}.md")

    v1m, v15s, v30s, vtick, vquote, n_total = build_variants_round7()
    all_strats = v1m + v15s + v30s + vtick + vquote
    print(f"\n[round7] Built {len(all_strats)} strategies: {len(v1m)} 1m + "
          f"{len(v15s)} 15s + {len(v30s)} 30s + {len(vtick)} tick + "
          f"{len(vquote)} quote", file=sys.stderr)
    print(f"[round7] starting offset {args.offset:,}, ckpt={ckpt_path}",
          file=sys.stderr)

    resumed = load_checkpoint(ckpt_path, all_strats)
    if resumed is not None:
        start_offset, day_counter, last_day_key = resumed
        resumed_trades = sum(s.n_trades for s in all_strats)
        print(f"[round7] RESUMING from offset {start_offset:,} "
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
    print(f"[round7] file size: {file_size:,} bytes", file=sys.stderr)

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
                    print(f"  [round7] ckpt save failed: {e!r}", file=sys.stderr)
                print(f"  [round7] {n_lines/1e6:.1f}M ticks rate={rate/1e6:.2f}M/s "
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

            if bb_1m.on_tick(ts, last):
                closed = bb_1m.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
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

            # Tick-fed strategies need every tick
            for s in vtick:
                s.feed_tick(ts, last)
            # Quote-fed strategies need every tick (quote + bar tracking via on_bar_close)
            for s in vquote:
                s.feed_quote(ts, bid, ask, last)

            for s in all_strats:
                r7_bot_on_tick(s, ts, bid, ask, day_counter, hh, mn, last)

    elapsed = time.time() - t_start
    total_days = day_counter + 1
    print(f"\n[round7] DONE in {elapsed/60:.1f}min, {n_lines:,} ticks, "
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
    print(f"[round7] wrote CSV {csv_path}", file=sys.stderr)

    full_pass = [r for r in rows if r['trades_per_day'] >= 300
                 and r['wr'] >= 0.45 and r['per_day'] >= 1000
                 and r['max_dd'] <= 5000]

    lines = []
    lines.append(f"# Round 7 strategy search results (offset={args.offset:,})\n\n")
    lines.append(f"Generated: {datetime.now().isoformat()}\n")
    lines.append(f"Period: {total_days} calendar-day buckets from offset "
                 f"{args.offset:,} (max-days={args.max_days})\n")
    lines.append(f"Tick stream: {n_lines:,} lines processed\n")
    lines.append(f"Strategies tested: {len(rows)}\n")
    lines.append(f"Costs applied: ${TOTAL_RT_COST:.2f}/RT, queue overshoot=1 tick "
                 f"(limit), marketable +1tick, stop-entry +1tick, stop slip "
                 f"{STOP_SLIP_PT}pt baseline + {STOP_GAP_SLIP_PROB*100:.0f}% extra\n")
    lines.append(f"Execution friction: APPROACH={APPROACH_THRESHOLD_PT}pt, "
                 f"latency_embargo={LATENCY_EMBARGO_S*1000:.0f}ms, "
                 f"fresh_placement={FRESH_PLACEMENT_LATENCY_S*1000:.0f}ms, "
                 f"stale_fill_prob={STALE_FILL_PROB*100:.0f}%, "
                 f"cooldown={COOLDOWN_S}s, max_hold={MAX_HOLD_S}s\n\n")
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
    for sc, binder, r in scored[:20]:
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
    print(f"[round7] wrote MD {md_path}", file=sys.stderr)

    print("\n" + "=" * 110)
    print(f"{'Strategy':>35s} {'N':>7s} {'/day':>6s} {'WR%':>5s} "
          f"{'$/day':>9s} {'$/tr':>7s} {'maxDD':>9s} {'sharpe':>6s}")
    print("=" * 110)
    for r in rows[:30]:
        flag = ""
        if (r['trades_per_day'] >= 300 and r['wr'] >= 0.45
                and r['per_day'] >= 1000 and r['max_dd'] <= 5000):
            flag = " *PASS*"
        elif r['per_day'] >= 500:
            flag = "  $$"
        print(f"{r['name']:>35s} {r['n']:>7d} {r['trades_per_day']:>6.1f} "
              f"{r['wr']*100:>4.1f}% ${r['per_day']:>+8.0f} "
              f"${r['per_trade']:>+6.2f} ${r['max_dd']:>+8.0f} "
              f"{r['sharpe']:>+6.2f}{flag}")
    print(f"\nFULL_PASS strategies: {len(full_pass)}")

    try:
        if os.path.exists(ckpt_path):
            os.remove(ckpt_path)
            print(f"[round7] cleared checkpoint {ckpt_path}",
                  file=sys.stderr)
    except Exception:
        pass


if __name__ == "__main__":
    main()
