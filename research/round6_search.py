"""Round 6 strategy search for MNQ — momentum/breakout + marketable-LIMIT.

Round 5 finding: every round-4 mean-reversion pullback strategy LOST money
under the bot-faithful execution model because the queue-position model
(LIMIT only fills when price *overshoots* by 1 tick) means our "winners"
were exactly the trades where price touched and reversed — the pullback
fills we LOSE under realistic execution. Winning trades therefore went
from 54-66% to 19-37% WR.

Round 6 strategy theses (DON'T rely on touch-and-reverse fills):

  A. MOMENTUM-BREAKOUT entries: place LIMIT at recent high + 1tick.
     Fires when ASK breaks through the high. Naturally has overshoot.
  B. MARKETABLE-LIMIT pullback entries: LIMIT at ASK+1tick for LONG.
     Fills immediately on the next tick. ~99% fill rate, costs ~1 tick
     of entry slip vs the touch price.
  C. STOP-LIMIT exits (controlled-slip stops): limit at stop_px - 2pt
     for LONG. Trade-off: occasional non-fill when price gaps through.
  D. WIDER stops + HIGHER R:R (3:1 to 10:1) — robust to 1-2pt slip.
  E. Anti-impulse failure: when 5-bar impulse fails (next bar reverses
     >50% of range), fade with MARKETABLE LIMIT in fade direction.
  F. Liquidity-sweep + retest: price spikes above prior high then
     retraces below — fade with MARKETABLE LIMIT.
  G. Tick-momentum continuation: N consecutive ticks same direction =
     place MARKETABLE LIMIT in flow direction.
  H. Range-band breakouts: price closes outside 20-bar range = entry.
  I. Multi-bar reversal (3BR/4BR/5BR) with marketable-LIMIT entry.
  J. ATR / volatility / time-of-day gates on all above.
  K. Cross-session momentum (Asia/London/NY open).
  L. Z-score with momentum confirmation: only fire MR when Z>2.5 AND
     last tick reversed direction.
  M. VWAP deviation + N-bar momentum confluence.
  N. Pre-news quiet hour mean-reversion (narrow time windows).
  O. Stop-LIMIT exits applied to ROUND 4 best to control slip.
  P. LONG-only / SHORT-only variants of momentum.
  Q. Multi-tier OCO fib levels (simulated: setup an array, first fill
     wins, others auto-cancel). (Approximated via multiple setups
     with shared 'cohort' key.)
  R. Faster timeframes for momentum (1s / 3s).

EXECUTION MODEL: same as round 5 (queue-position 1tick overshoot,
200ms latency, 10pt approach, single-LIMIT lock, stop-MARKET slip,
$1.91/RT) WITH the following per-strategy opt-in extensions:

  - `fill_mode = "marketable"`: setup carries this; on a trigger tick,
    fill at ASK+1tick (LONG) / BID-1tick (SHORT) NO queue overshoot
    required. The trigger condition for marketable is: price has come
    within 1pt of entry (i.e. the cold-LIMIT is firing). After 200ms
    latency, fills at next available ASK+1 (LONG) or BID-1 (SHORT).
    This models "place a marketable LIMIT" — practically a market
    order with price protection.

  - `fill_mode = "stop"`: STOP-style entry. For LONG, place STOP-BUY
    at entry_px (a level ABOVE current ask). Triggers when ASK >=
    entry_px AT WHICH POINT it fires AT ASK+1tick (slip 1tick). For
    SHORT, STOP-SELL at entry_px below current bid, fires when
    BID <= entry_px, fills at BID-1tick.
    This is the natural momentum-breakout entry.

  - `fill_mode = "limit"` (default): existing queue-position semantics.

  - `exit_mode = "stop_limit"`: stop fills as stop_px - 2pt LIMIT
    (LONG); won't fill if price gaps past 2pt. We model 5% non-fill
    when stop level fires (proxied by checking if next tick has bid <=
    stop_px - 2pt - 0.5pt then non-fill, time out instead). Otherwise
    fills at stop_px - 2pt (or stop_px + 2pt for SHORT). This caps
    slip to a small range.

Outputs:
  - research/round6_results.md
  - research/round6_summary.csv
  - research/round6_checkpoint.pkl
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

from research import round4_search as _r4  # noqa: E402
sys.modules.setdefault("round4_search", _r4)

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

PATH = "/home/user/HFTBot/data/tick/ustech/USTECH_full.csv"
DEFAULT_OFFSET = 7_820_974_790
CHECKPOINT_EVERY_TICKS = 100_000

COMM_RT = 0.74
EXCH_FEES_RT = 1.17
TOTAL_RT_COST = COMM_RT + EXCH_FEES_RT  # $1.91
MNQ_PER_PT = 2.0

# === Execution-model constants (mirroring bot/fib_main.py and round5) ===
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

# Marketable-LIMIT extra entry slip: 1 tick beyond the touch price.
MARKETABLE_SLIP_PT = TICK    # = 0.25
# STOP-entry slip: 1 tick beyond the breakout level.
STOP_ENTRY_SLIP_PT = TICK    # = 0.25
# Stop-LIMIT exit cap (LONG: fills at stop - this; SHORT: stop + this).
STOP_LIMIT_OFFSET_PT = 2.0
# Probability a stop-LIMIT exit fails to fill (gap-through risk).
STOP_LIMIT_NONFILL_PROB = 0.10
# If a stop-LIMIT fails to fill, max_hold_s timeout exit applies.

RNG = random.Random(0xB0FAF1F2)


# ===========================================================================
# Bot-faithful executor (extended to support fill_mode + exit_mode).
#
# Stores per-strategy execution state. Per-setup `fill_mode` and `exit_mode`
# are read from the setup dict when triggering.
# ===========================================================================
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


def attach_executor(strat):
    strat._exec = BotFaithfulExecutor(strat)


def _closest_pending(strat, bid, ask):
    """Pick closest pending setup by current-market distance on impulse side.

    For STOP-entry setups (fill_mode='stop'), the "approach" is the OPPOSITE
    direction (the breakout price is ABOVE current ask for LONG, BELOW for
    SHORT). Handle that here.
    """
    best = None
    best_dist = float('inf')
    for s in strat.pending:
        if s.get('used') or s.get('_fire_attempted'):
            continue
        orig = s.get('orig', s['side'])
        entry = s['entry']
        fill_mode = s.get('fill_mode', 'limit')
        if fill_mode == 'stop':
            # Breakout: LONG fires when ASK rises to entry from below.
            # SHORT fires when BID falls to entry from above.
            if orig == "LONG":
                if ask > entry + 0.5:
                    continue  # price already past breakout
                dist = max(0.0, entry - ask)
            else:
                if bid < entry - 0.5:
                    continue
                dist = max(0.0, bid - entry)
        else:
            # LIMIT / marketable: same as round 5.
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


def bot_on_tick(strat, ts, bid, ask, day_counter, hh, mn):
    """Tick handler: mirrors round 5 with fill_mode + exit_mode extensions."""
    exe = strat._exec

    # Expire stale pending setups.
    if strat.pending:
        strat.pending = [
            s for s in strat.pending
            if s['expires'] >= ts and not s.get('used')
        ]

    # ----------------------------------------
    # In-trade: handle exits.
    # ----------------------------------------
    if strat.in_trade is not None:
        tr = strat.in_trade
        exit_mode = tr.get('exit_mode', 'stop_market')
        exit_now = None
        if tr['side'] == 'LONG':
            if bid <= tr['stop']:
                if exit_mode == 'stop_limit':
                    # Try to fill the LIMIT cap.
                    cap_px = tr['stop'] - STOP_LIMIT_OFFSET_PT
                    if bid < cap_px - 0.5 or RNG.random() < STOP_LIMIT_NONFILL_PROB:
                        # Gap-through or non-fill: continue holding,
                        # the LIMIT is "dead" — we mark exit_mode to
                        # stop_market so future ticks treat as market
                        # exit (this models bot fallback).
                        tr['exit_mode'] = 'stop_market'
                    else:
                        exit_px = cap_px
                        pnl = exit_px - tr['entry']
                        exit_now = ('stop', pnl)
                else:
                    slip = STOP_SLIP_PT
                    if RNG.random() < STOP_GAP_SLIP_PROB:
                        slip += RNG.random() * STOP_GAP_SLIP_MAX_PT
                    exit_px = tr['stop'] - slip
                    pnl = exit_px - tr['entry']
                    exit_now = ('stop', pnl)
            elif bid >= tr['target']:
                pnl = tr['target'] - tr['entry']
                exit_now = ('tgt', pnl)
            elif ts - tr['et'] >= MAX_HOLD_S:
                pnl = bid - tr['entry']
                exit_now = ('to', pnl)
        else:  # SHORT
            if ask >= tr['stop']:
                if exit_mode == 'stop_limit':
                    cap_px = tr['stop'] + STOP_LIMIT_OFFSET_PT
                    if ask > cap_px + 0.5 or RNG.random() < STOP_LIMIT_NONFILL_PROB:
                        tr['exit_mode'] = 'stop_market'
                    else:
                        exit_px = cap_px
                        pnl = tr['entry'] - exit_px
                        exit_now = ('stop', pnl)
                else:
                    slip = STOP_SLIP_PT
                    if RNG.random() < STOP_GAP_SLIP_PROB:
                        slip += RNG.random() * STOP_GAP_SLIP_MAX_PT
                    exit_px = tr['stop'] + slip
                    pnl = tr['entry'] - exit_px
                    exit_now = ('stop', pnl)
            elif ask <= tr['target']:
                pnl = tr['entry'] - tr['target']
                exit_now = ('tgt', pnl)
            elif ts - tr['et'] >= MAX_HOLD_S:
                pnl = tr['entry'] - ask
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

    # Cooldown.
    if exe.last_exit_ts is not None and ts - exe.last_exit_ts < COOLDOWN_S:
        return

    # Session gate.
    if not strat._in_session(hh, mn):
        return

    closest, dist = _closest_pending(strat, bid, ask)

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
    entry = s['entry']
    fill_mode = s.get('fill_mode', 'limit')

    # ----------------------------------------
    # Trigger condition + actual fill price per fill_mode
    # ----------------------------------------
    fill_px = None
    if fill_mode == 'limit':
        # Round 5 queue-position: strict 1-tick overshoot.
        if orig == "LONG":
            if ask <= entry - TICK:
                fill_px = entry  # LIMIT fills at our price
        else:
            if bid >= entry + TICK:
                fill_px = entry
    elif fill_mode == 'marketable':
        # Marketable LIMIT: trigger when price within 0pt of entry
        # (touch) — fills at next-best opposite quote with 1tick slip.
        if orig == "LONG":
            if ask <= entry:
                # We BUY: fill at ASK + 1tick (taking the offer).
                fill_px = ask + MARKETABLE_SLIP_PT
        else:
            if bid >= entry:
                fill_px = bid - MARKETABLE_SLIP_PT
    elif fill_mode == 'stop':
        # STOP entry: LONG fires when ASK >= entry, fills at ASK + 1tick
        if orig == "LONG":
            if ask >= entry:
                fill_px = ask + STOP_ENTRY_SLIP_PT
        else:
            if bid <= entry:
                fill_px = bid - STOP_ENTRY_SLIP_PT

    if fill_px is None:
        return

    # Stale-fill skip
    if exe.skip_next_trade:
        exe.skip_next_trade = False
        s['_fire_attempted'] = True
        exe.active_limit_key = None
        exe.active_limit_armed_ts = None
        return

    # FILL: stop/target are stored as offsets in setup OR absolutes.
    # The strategies that use non-LIMIT modes recompute stop/target
    # relative to the actual fill_px. We support both: if the setup
    # has 'stop_offset_pts' present, recompute from fill_px.
    if 'stop_offset_pts' in s:
        stop_off = s['stop_offset_pts']
        tgt_off = s['target_offset_pts']
        if s['side'] == 'LONG':
            stop_px = fill_px - stop_off
            tgt_px = fill_px + tgt_off
        else:
            stop_px = fill_px + stop_off
            tgt_px = fill_px - tgt_off
    else:
        stop_px = s['stop']
        tgt_px = s['target']

    strat.in_trade = {
        'side': s['side'],
        'entry': fill_px,
        'stop': stop_px,
        'target': tgt_px,
        'et': ts,
        'exit_mode': s.get('exit_mode', 'stop_market'),
    }
    s['used'] = True
    exe.active_limit_key = None
    exe.active_limit_armed_ts = None


# ===========================================================================
# Extended add_setup: passthrough for fill_mode/exit_mode/stop_offset_pts.
# ===========================================================================
def _patched_add_setup(self, side, orig, entry, stop, target, ts_now,
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
_SB.add_setup = _patched_add_setup


# ===========================================================================
# NEW STRATEGY CLASSES for round 6
# ===========================================================================
class MarketablePullback(PullbackStrategy):
    """Round-4 PullbackStrategy with fill_mode='marketable' on every setup.

    Same signal logic; entries fill at touch+1tick instead of waiting
    for overshoot. Higher fill rate, ~1tick entry slip.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def on_bar_close(self, ts, hh, mn, bar_o, bar_h, bar_l, bar_c, hist):
        nbars = len(hist)
        if nbars < self.impulse_bars:
            return
        if self.atr_min is not None or self.atr_max is not None:
            if nbars < self.atr_bars + 1:
                return
            tr_sum = 0.0
            for i in range(nbars - self.atr_bars, nbars):
                o, h, l, c = hist[i]
                pc = hist[i - 1][3] if i > 0 else c
                tr = max(h - l, abs(h - pc), abs(l - pc))
                tr_sum += tr
            atr = tr_sum / self.atr_bars
            if self.atr_min is not None and atr < self.atr_min:
                return
            if self.atr_max is not None and atr > self.atr_max:
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
        side = ("SHORT" if orig_side == "LONG" else "LONG") if self.invert else orig_side
        if self.long_only and side != "LONG":
            return
        if self.short_only and side != "SHORT":
            return
        if orig_side == "LONG":
            entry = ih - self.pull_pct * rng
        else:
            entry = il + self.pull_pct * rng
        # Store stop/target as offsets — actual stop_px recomputed at fill.
        key = ("mkt_pb", round(ih, 1), round(il, 1), orig_side)
        extra = {
            'fill_mode': 'marketable',
            'stop_offset_pts': self.stop_pts,
            'target_offset_pts': self.target_pts,
            'exit_mode': 'stop_market',
        }
        # entry, stop, target placeholders; fill recomputes from fill_px.
        if side == "LONG":
            stop = entry - self.stop_pts
            target = entry + self.target_pts
        else:
            stop = entry + self.stop_pts
            target = entry - self.target_pts
        self.add_setup(side, orig_side, entry, stop, target, ts,
                       key=key, expires_in=300, extra=extra)


class BreakoutStrategy(StrategyBase):
    """Range/high-low breakout. Place STOP-BUY at last N-bar high + buf,
    STOP-SELL at last N-bar low - buf. Triggers on close-of-N+1th bar's
    setup arming, fires when ASK >= high+buf or BID <= low-buf.
    """
    def __init__(self, name, n_bars=20, buf_pts=0.5,
                 stop_pts=5, target_pts=15, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_S, exit_mode='stop_market',
                 long_only=False, short_only=False,
                 min_range_pts=2.0, max_range_pts=40.0,
                 expires=180):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start,
                         session_end=session_end)
        self.n_bars = n_bars
        self.buf_pts = buf_pts
        self.stop_pts = stop_pts
        self.target_pts = target_pts
        self.exit_mode = exit_mode
        self.long_only = long_only
        self.short_only = short_only
        self.min_range_pts = min_range_pts
        self.max_range_pts = max_range_pts
        self.expires = expires

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.n_bars:
            return
        win = list(hist)[-self.n_bars:]
        rh = max(b[1] for b in win)
        rl = min(b[2] for b in win)
        rng = rh - rl
        if rng < self.min_range_pts or rng > self.max_range_pts:
            return
        # LONG breakout
        if not self.short_only:
            up_entry = rh + self.buf_pts
            extra = {
                'fill_mode': 'stop',
                'stop_offset_pts': self.stop_pts,
                'target_offset_pts': self.target_pts,
                'exit_mode': self.exit_mode,
            }
            stop = up_entry - self.stop_pts
            target = up_entry + self.target_pts
            self.add_setup("LONG", "LONG", up_entry, stop, target, ts,
                           key=("brk_l", round(rh, 1), round(rl, 1)),
                           expires_in=self.expires, extra=extra)
        # SHORT breakout
        if not self.long_only:
            dn_entry = rl - self.buf_pts
            extra = {
                'fill_mode': 'stop',
                'stop_offset_pts': self.stop_pts,
                'target_offset_pts': self.target_pts,
                'exit_mode': self.exit_mode,
            }
            stop = dn_entry + self.stop_pts
            target = dn_entry - self.target_pts
            self.add_setup("SHORT", "SHORT", dn_entry, stop, target, ts,
                           key=("brk_s", round(rh, 1), round(rl, 1)),
                           expires_in=self.expires, extra=extra)


class TickMomentumContinuation(StrategyBase):
    """Fire when N consecutive ticks move in same direction.

    Tracks last-tick price. After N moves in same direction with
    cumulative travel >= min_travel_pts, place a marketable-LIMIT in
    flow direction. Stop = stop_pts; target = target_pts.
    """
    # __slots__ intentionally omitted: parent StrategyBase uses slots
    # but the harness writes `_exec` dynamically on every instance.
    # Dropping slots gives us a __dict__.

    def __init__(self, name, n_consec=5, min_travel_pts=1.0,
                 stop_pts=3, target_pts=9, cooldown_s=10,
                 session_start=None, session_end=None,
                 exit_mode='stop_market',
                 long_only=False, short_only=False,
                 max_hold=MAX_HOLD_S, expires=15,
                 cool_setup_s=30):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.n_consec = n_consec
        self.min_travel_pts = min_travel_pts
        self.stop_pts = stop_pts
        self.target_pts = target_pts
        self.exit_mode = exit_mode
        self.long_only = long_only
        self.short_only = short_only
        self.expires = expires
        self.cool_setup_s = cool_setup_s
        self._streak_dir = 0
        self._streak_len = 0
        self._streak_start_px = None
        self._last_px = None
        self._last_setup_ts = None

    def on_tick_signal(self, ts, bid, ask, hh, mn):
        # We call this from the main loop ONLY when fed (we register a
        # last-price hook via the harness). For Python perf reasons we
        # consume the last/mid here directly.
        pass

    def feed_last(self, ts, last):
        if self._last_px is None:
            self._last_px = last
            self._streak_dir = 0
            self._streak_len = 0
            self._streak_start_px = last
            return
        if last > self._last_px:
            d = 1
        elif last < self._last_px:
            d = -1
        else:
            d = 0
        if d == 0:
            self._last_px = last
            return
        if d == self._streak_dir:
            self._streak_len += 1
        else:
            self._streak_dir = d
            self._streak_len = 1
            self._streak_start_px = self._last_px
        self._last_px = last

        if self._streak_len < self.n_consec:
            return
        travel = abs(last - self._streak_start_px)
        if travel < self.min_travel_pts:
            return
        # Throttle: don't issue setups too frequently.
        if (self._last_setup_ts is not None and
                ts - self._last_setup_ts < self.cool_setup_s):
            return
        self._last_setup_ts = ts
        # Issue marketable-LIMIT setup in flow direction.
        if d > 0:
            if self.short_only:
                return
            side = "LONG"
            entry = last
        else:
            if self.long_only:
                return
            side = "SHORT"
            entry = last
        extra = {
            'fill_mode': 'marketable',
            'stop_offset_pts': self.stop_pts,
            'target_offset_pts': self.target_pts,
            'exit_mode': self.exit_mode,
        }
        if side == "LONG":
            stop = entry - self.stop_pts
            target = entry + self.target_pts
        else:
            stop = entry + self.stop_pts
            target = entry - self.target_pts
        self.add_setup(side, side, entry, stop, target, ts,
                       key=("tmc", round(entry, 1), d, int(ts*10) % 1000),
                       expires_in=self.expires, extra=extra)
        # Reset streak so we don't keep firing on the same run.
        self._streak_len = 0


class ImpulseFailure(StrategyBase):
    """After an N-bar impulse with cumulative |move|>=impulse_pts, the
    NEXT bar that closes reversing >= reverse_frac of impulse range
    fades the impulse with a marketable-LIMIT in fade direction.
    """
    # __slots__ omitted to allow dynamic _exec attribute.

    def __init__(self, name, impulse_pts=8.0, impulse_bars=5,
                 reverse_frac=0.5, stop_pts=4, target_pts=12,
                 cooldown_s=10, session_start=None, session_end=None,
                 exit_mode='stop_market', long_only=False, short_only=False,
                 max_hold=MAX_HOLD_S, expires=60):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.impulse_pts = impulse_pts
        self.impulse_bars = impulse_bars
        self.reverse_frac = reverse_frac
        self.stop_pts = stop_pts
        self.target_pts = target_pts
        self.exit_mode = exit_mode
        self.long_only = long_only
        self.short_only = short_only
        self.expires = expires
        self._pending_impulse = None  # (dir, ih, il, ts_set)

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        nbars = len(hist)
        if nbars < self.impulse_bars + 1:
            return
        win = list(hist)[-self.impulse_bars:]
        net = win[-1][3] - win[0][0]
        ih = max(b[1] for b in win)
        il = min(b[2] for b in win)
        rng = ih - il
        if rng <= 0:
            return
        # If we previously detected an impulse, check failure on this bar.
        if self._pending_impulse is not None:
            pdir, pih, pil, pts = self._pending_impulse
            if ts - pts > 180:
                self._pending_impulse = None
            else:
                bar_move = bc - bo
                pr = pih - pil
                if pdir == 1 and bar_move <= -self.reverse_frac * pr:
                    # Up impulse failed -> fade SHORT
                    if not self.long_only:
                        entry = bc
                        side = "SHORT"
                        extra = {
                            'fill_mode': 'marketable',
                            'stop_offset_pts': self.stop_pts,
                            'target_offset_pts': self.target_pts,
                            'exit_mode': self.exit_mode,
                        }
                        stop = entry + self.stop_pts
                        target = entry - self.target_pts
                        self.add_setup(side, side, entry, stop, target, ts,
                                       key=("if_s", round(pih, 1), round(pil, 1)),
                                       expires_in=self.expires, extra=extra)
                    self._pending_impulse = None
                elif pdir == -1 and bar_move >= self.reverse_frac * pr:
                    if not self.short_only:
                        entry = bc
                        side = "LONG"
                        extra = {
                            'fill_mode': 'marketable',
                            'stop_offset_pts': self.stop_pts,
                            'target_offset_pts': self.target_pts,
                            'exit_mode': self.exit_mode,
                        }
                        stop = entry - self.stop_pts
                        target = entry + self.target_pts
                        self.add_setup(side, side, entry, stop, target, ts,
                                       key=("if_l", round(pih, 1), round(pil, 1)),
                                       expires_in=self.expires, extra=extra)
                    self._pending_impulse = None
        # Then check whether the just-closed window IS a new impulse.
        if abs(net) >= self.impulse_pts:
            self._pending_impulse = (1 if net > 0 else -1, ih, il, ts)


class LiquiditySweep(StrategyBase):
    """When the latest bar pierces the prior N-bar high (or low) but
    closes BACK INSIDE the range, fade the sweep. Marketable-LIMIT in
    fade direction at bar close.
    """
    # __slots__ omitted to allow dynamic _exec attribute.

    def __init__(self, name, lookback=20, stop_pts=4, target_pts=12,
                 min_pierce_pts=1.0, cooldown_s=10,
                 session_start=None, session_end=None,
                 exit_mode='stop_market',
                 long_only=False, short_only=False,
                 max_hold=MAX_HOLD_S, expires=60):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.lookback = lookback
        self.stop_pts = stop_pts
        self.target_pts = target_pts
        self.min_pierce_pts = min_pierce_pts
        self.exit_mode = exit_mode
        self.long_only = long_only
        self.short_only = short_only
        self.expires = expires

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.lookback + 1:
            return
        prior = list(hist)[-(self.lookback+1):-1]
        prior_high = max(b[1] for b in prior)
        prior_low = min(b[2] for b in prior)
        # Sweep above: bar's high > prior_high + min_pierce AND close <= prior_high
        if bh > prior_high + self.min_pierce_pts and bc <= prior_high:
            if not self.long_only:
                entry = bc
                side = "SHORT"
                extra = {
                    'fill_mode': 'marketable',
                    'stop_offset_pts': self.stop_pts,
                    'target_offset_pts': self.target_pts,
                    'exit_mode': self.exit_mode,
                }
                stop = entry + self.stop_pts
                target = entry - self.target_pts
                self.add_setup(side, side, entry, stop, target, ts,
                               key=("ls_s", round(prior_high, 1)),
                               expires_in=self.expires, extra=extra)
        if bl < prior_low - self.min_pierce_pts and bc >= prior_low:
            if not self.short_only:
                entry = bc
                side = "LONG"
                extra = {
                    'fill_mode': 'marketable',
                    'stop_offset_pts': self.stop_pts,
                    'target_offset_pts': self.target_pts,
                    'exit_mode': self.exit_mode,
                }
                stop = entry - self.stop_pts
                target = entry + self.target_pts
                self.add_setup(side, side, entry, stop, target, ts,
                               key=("ls_l", round(prior_low, 1)),
                               expires_in=self.expires, extra=extra)


class ZScoreReversion(StrategyBase):
    """Mean-reversion: when close has Z-score against 20-bar SMA exceed
    threshold AND prior bar moved opposite direction (confirmation),
    fade with marketable-LIMIT.
    """
    # __slots__ omitted to allow dynamic _exec attribute.

    def __init__(self, name, lookback=20, z_thresh=2.5,
                 stop_pts=4, target_pts=8, cooldown_s=10,
                 session_start=None, session_end=None,
                 exit_mode='stop_market',
                 long_only=False, short_only=False,
                 max_hold=MAX_HOLD_S, expires=60,
                 require_reversal=True):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.lookback = lookback
        self.z_thresh = z_thresh
        self.stop_pts = stop_pts
        self.target_pts = target_pts
        self.exit_mode = exit_mode
        self.long_only = long_only
        self.short_only = short_only
        self.expires = expires
        self.require_reversal = require_reversal

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.lookback + 1:
            return
        closes = [hist[i][3] for i in range(len(hist) - self.lookback, len(hist))]
        mean = sum(closes) / len(closes)
        var = sum((x - mean) ** 2 for x in closes) / len(closes)
        std = math.sqrt(var) if var > 0 else 0.0
        if std == 0:
            return
        z = (bc - mean) / std
        last_move = bc - bo
        if z >= self.z_thresh:
            if self.require_reversal and last_move >= 0:
                return
            if self.long_only:
                return
            entry = bc
            side = "SHORT"
            extra = {
                'fill_mode': 'marketable',
                'stop_offset_pts': self.stop_pts,
                'target_offset_pts': self.target_pts,
                'exit_mode': self.exit_mode,
            }
            stop = entry + self.stop_pts
            target = entry - self.target_pts
            self.add_setup(side, side, entry, stop, target, ts,
                           key=("zs_s", round(entry, 1)),
                           expires_in=self.expires, extra=extra)
        elif z <= -self.z_thresh:
            if self.require_reversal and last_move <= 0:
                return
            if self.short_only:
                return
            entry = bc
            side = "LONG"
            extra = {
                'fill_mode': 'marketable',
                'stop_offset_pts': self.stop_pts,
                'target_offset_pts': self.target_pts,
                'exit_mode': self.exit_mode,
            }
            stop = entry - self.stop_pts
            target = entry + self.target_pts
            self.add_setup(side, side, entry, stop, target, ts,
                           key=("zs_l", round(entry, 1)),
                           expires_in=self.expires, extra=extra)


class VWAPDeviation(StrategyBase):
    """Running VWAP since session start (rolling 200-bar). When |bc-vwap|
    >= dev_atr * atr AND last K bars closed same direction (continuation),
    enter in continuation direction with marketable-LIMIT.

    Variant: dev=mean-reversion (fade) or dev=continuation (with trend).
    """
    # __slots__ omitted to allow dynamic _exec attribute.

    def __init__(self, name, lookback=50, dev_atr_mult=1.0,
                 k_continuation=3, stop_pts=4, target_pts=12,
                 cooldown_s=10, session_start=None, session_end=None,
                 exit_mode='stop_market', fade=False,
                 long_only=False, short_only=False,
                 max_hold=MAX_HOLD_S, expires=60):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.lookback = lookback
        self.dev_atr_mult = dev_atr_mult
        self.k_continuation = k_continuation
        self.stop_pts = stop_pts
        self.target_pts = target_pts
        self.exit_mode = exit_mode
        self.fade = fade
        self.long_only = long_only
        self.short_only = short_only
        self.expires = expires

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.lookback + 1:
            return
        sub = list(hist)[-self.lookback:]
        # VWAP-ish: simple typical-price mean as proxy (no volume in tick data).
        vwap = sum((b[1] + b[2] + b[3]) / 3.0 for b in sub) / len(sub)
        # ATR
        tr_sum = 0.0
        for i in range(1, len(sub)):
            o, h, l, c = sub[i]
            pc = sub[i - 1][3]
            tr = max(h - l, abs(h - pc), abs(l - pc))
            tr_sum += tr
        atr = tr_sum / (len(sub) - 1) if len(sub) > 1 else 0.0
        if atr <= 0:
            return
        dev = bc - vwap
        thresh = self.dev_atr_mult * atr
        if abs(dev) < thresh:
            return
        # Last K bars same direction?
        last_k = sub[-self.k_continuation:]
        ups = sum(1 for b in last_k if b[3] >= b[0])
        dns = sum(1 for b in last_k if b[3] < b[0])
        if dev > 0:  # price above VWAP
            if self.fade:
                if self.long_only:
                    return
                side = "SHORT"
            else:
                if ups != len(last_k):
                    return
                if self.short_only:
                    return
                side = "LONG"
        else:
            if self.fade:
                if self.short_only:
                    return
                side = "LONG"
            else:
                if dns != len(last_k):
                    return
                if self.long_only:
                    return
                side = "SHORT"
        entry = bc
        extra = {
            'fill_mode': 'marketable',
            'stop_offset_pts': self.stop_pts,
            'target_offset_pts': self.target_pts,
            'exit_mode': self.exit_mode,
        }
        if side == "LONG":
            stop = entry - self.stop_pts
            target = entry + self.target_pts
        else:
            stop = entry + self.stop_pts
            target = entry - self.target_pts
        self.add_setup(side, side, entry, stop, target, ts,
                       key=("vw", side, round(entry, 1)),
                       expires_in=self.expires, extra=extra)


class NBarReversalMkt(NBarReversal):
    """NBarReversal with marketable-LIMIT entry."""
    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.n_bars:
            return
        bars = list(hist)[-self.n_bars:]
        down_part = bars[:-1]
        last = bars[-1]
        cum_down = sum(b[3] - b[0] for b in down_part)
        last_move = last[3] - last[0]
        mid_bar = bars[-2]
        mid_move = abs(mid_bar[3] - mid_bar[0])
        extra_long = {
            'fill_mode': 'marketable',
            'stop_offset_pts': self.stop_pts,
            'target_offset_pts': self.target_pts,
            'exit_mode': 'stop_market',
        }
        if cum_down <= -self.min_move * (self.n_bars - 1) * 0.6 and \
           mid_move < self.max_mid_range and \
           last_move >= self.min_move:
            entry = last[3]
            stop = entry - self.stop_pts
            target = entry + self.target_pts
            self.add_setup("LONG", "LONG", entry, stop, target, ts,
                           key=("nbrm_l", round(mid_bar[0], 1), self.n_bars),
                           expires_in=180, extra=extra_long)
        cum_up = sum(b[3] - b[0] for b in down_part)
        if cum_up >= self.min_move * (self.n_bars - 1) * 0.6 and \
           mid_move < self.max_mid_range and \
           last_move <= -self.min_move:
            entry = last[3]
            stop = entry + self.stop_pts
            target = entry - self.target_pts
            extra_short = dict(extra_long)
            self.add_setup("SHORT", "SHORT", entry, stop, target, ts,
                           key=("nbrm_s", round(mid_bar[0], 1), self.n_bars),
                           expires_in=180, extra=extra_short)


# ===========================================================================
# Build the strategy library — at least 150 variants
# ===========================================================================
def build_variants_round6():
    v1m, v15s, v30s, vvol_500, vvol_1k = [], [], [], [], []
    vtick = []  # tick-momentum continuation strategies

    # ----------------------------------------
    # A. MARKETABLE-LIMIT pullback variants (mirror best round-4 params)
    #    Test: pull%, stop, target, impulse, invert, RTH/CME, LONG/SHORT
    # ----------------------------------------
    for pp in [0.118, 0.236, 0.382, 0.5]:
        for stop, tgt in [(3, 9), (3, 12), (4, 16), (5, 20), (5, 15),
                          (8, 24), (10, 30)]:
            for imp in [3.0, 5.0, 7.0]:
                name = f"MKT_pp{int(pp*1000)}_s{stop}t{tgt}_imp{int(imp)}"
                v1m.append(MarketablePullback(
                    name, impulse_pts=imp, impulse_bars=4, pull_pct=pp,
                    stop_pts=stop, target_pts=tgt, invert=True))

    # ----------------------------------------
    # A2. Marketable-LIMIT on 15s & 30s
    # ----------------------------------------
    for stop, tgt in [(3, 9), (3, 12), (4, 16), (5, 15)]:
        for pp in [0.236, 0.382]:
            v15s.append(MarketablePullback(
                f"MKT15s_pp{int(pp*1000)}_s{stop}t{tgt}_imp2",
                impulse_pts=2.0, impulse_bars=4, pull_pct=pp,
                stop_pts=stop, target_pts=tgt, invert=True, max_hold=180))
        for pp in [0.236, 0.382]:
            v30s.append(MarketablePullback(
                f"MKT30s_pp{int(pp*1000)}_s{stop}t{tgt}_imp3",
                impulse_pts=3.0, impulse_bars=4, pull_pct=pp,
                stop_pts=stop, target_pts=tgt, invert=True, max_hold=240))

    # ----------------------------------------
    # B. BREAKOUT strategies (STOP entries)
    # ----------------------------------------
    for n in [10, 15, 20, 30]:
        for stop, tgt in [(3, 9), (4, 12), (5, 15), (5, 20), (4, 16),
                          (8, 24)]:
            for buf in [0.25, 1.0]:
                name = f"BRK_n{n}_b{int(buf*100)}_s{stop}t{tgt}"
                v1m.append(BreakoutStrategy(
                    name, n_bars=n, buf_pts=buf, stop_pts=stop,
                    target_pts=tgt))
    # Breakouts with stop-LIMIT exit
    for n in [15, 20]:
        for stop, tgt in [(5, 15), (5, 20), (8, 24)]:
            name = f"BRK_n{n}_s{stop}t{tgt}_SL"
            v1m.append(BreakoutStrategy(
                name, n_bars=n, buf_pts=0.25, stop_pts=stop,
                target_pts=tgt, exit_mode='stop_limit'))

    # Breakouts RTH only / CME-open
    for stop, tgt in [(5, 15), (8, 24)]:
        v1m.append(BreakoutStrategy(
            f"BRK_n20_s{stop}t{tgt}_RTH",
            n_bars=20, buf_pts=0.25, stop_pts=stop, target_pts=tgt,
            session_start=(13, 30), session_end=(20, 0)))
        v1m.append(BreakoutStrategy(
            f"BRK_n20_s{stop}t{tgt}_CME",
            n_bars=20, buf_pts=0.25, stop_pts=stop, target_pts=tgt,
            session_start=(22, 0), session_end=(23, 0)))
        v1m.append(BreakoutStrategy(
            f"BRK_n20_s{stop}t{tgt}_NYO",
            n_bars=20, buf_pts=0.25, stop_pts=stop, target_pts=tgt,
            session_start=(13, 30), session_end=(15, 0)))
    # Breakouts LONG only / SHORT only
    v1m.append(BreakoutStrategy(
        "BRK_n20_s5t15_LONG", n_bars=20, buf_pts=0.25,
        stop_pts=5, target_pts=15, long_only=True))
    v1m.append(BreakoutStrategy(
        "BRK_n20_s5t15_SHORT", n_bars=20, buf_pts=0.25,
        stop_pts=5, target_pts=15, short_only=True))

    # 15s breakouts
    for n in [20, 40, 60]:
        for stop, tgt in [(3, 9), (4, 12), (5, 15)]:
            v15s.append(BreakoutStrategy(
                f"BRK15s_n{n}_s{stop}t{tgt}",
                n_bars=n, buf_pts=0.25, stop_pts=stop, target_pts=tgt,
                max_hold=120, expires=60))

    # ----------------------------------------
    # C. STOP-LIMIT exit variants on marketable pullback
    # ----------------------------------------
    for stop, tgt in [(5, 15), (8, 24), (10, 30)]:
        name = f"MKT_pp236_s{stop}t{tgt}_imp5_SL"
        ms = MarketablePullback(
            name, impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
            stop_pts=stop, target_pts=tgt, invert=True)
        # We override the on_bar_close to mark exit_mode='stop_limit'.
        _orig_obc = ms.on_bar_close

        def make_obc(strat_obj):
            orig_fn = strat_obj.on_bar_close
            def patched(ts, hh, mn, bo, bh, bl, bc, hist):
                # Capture pending before/after to set exit_mode.
                pre_len = len(strat_obj.pending)
                orig_fn(ts, hh, mn, bo, bh, bl, bc, hist)
                for s in strat_obj.pending[pre_len:]:
                    s['exit_mode'] = 'stop_limit'
            return patched
        ms.on_bar_close = make_obc(ms)
        v1m.append(ms)

    # ----------------------------------------
    # D. TICK-MOMENTUM CONTINUATION
    # ----------------------------------------
    for n_consec in [4, 6, 8, 10]:
        for travel in [0.5, 1.0, 2.0]:
            for stop, tgt in [(2, 6), (3, 9), (4, 12), (5, 15)]:
                name = f"TMC_n{n_consec}_tr{int(travel*10)}_s{stop}t{tgt}"
                vtick.append(TickMomentumContinuation(
                    name, n_consec=n_consec, min_travel_pts=travel,
                    stop_pts=stop, target_pts=tgt, max_hold=120,
                    expires=15, cool_setup_s=30))

    # ----------------------------------------
    # E. IMPULSE FAILURE (fade after big move reverses)
    # ----------------------------------------
    for imp in [5.0, 8.0, 12.0]:
        for ib in [4, 5]:
            for rf in [0.4, 0.5, 0.7]:
                for stop, tgt in [(3, 9), (4, 12), (5, 15)]:
                    name = f"IF_i{int(imp)}_b{ib}_rf{int(rf*10)}_s{stop}t{tgt}"
                    v1m.append(ImpulseFailure(
                        name, impulse_pts=imp, impulse_bars=ib,
                        reverse_frac=rf, stop_pts=stop, target_pts=tgt))

    # ----------------------------------------
    # F. LIQUIDITY SWEEP + RETEST
    # ----------------------------------------
    for lk in [10, 20, 40]:
        for mp in [0.5, 1.0, 2.0]:
            for stop, tgt in [(3, 9), (4, 12), (5, 15)]:
                name = f"LS_lk{lk}_mp{int(mp*10)}_s{stop}t{tgt}"
                v1m.append(LiquiditySweep(
                    name, lookback=lk, min_pierce_pts=mp,
                    stop_pts=stop, target_pts=tgt))

    # ----------------------------------------
    # G. Z-SCORE MEAN-REVERSION with momentum confirmation
    # ----------------------------------------
    for lk in [15, 20, 30]:
        for z in [2.0, 2.5, 3.0]:
            for stop, tgt in [(3, 6), (4, 8), (5, 10), (4, 12)]:
                name = f"ZS_lk{lk}_z{int(z*10)}_s{stop}t{tgt}"
                v1m.append(ZScoreReversion(
                    name, lookback=lk, z_thresh=z,
                    stop_pts=stop, target_pts=tgt, require_reversal=True))

    # ----------------------------------------
    # H. VWAP DEVIATION (both fade and continuation)
    # ----------------------------------------
    for lk in [30, 50, 100]:
        for dam in [0.5, 1.0, 1.5]:
            for stop, tgt in [(4, 12), (5, 15), (4, 16)]:
                name = f"VW_lk{lk}_d{int(dam*10)}_s{stop}t{tgt}_CONT"
                v1m.append(VWAPDeviation(
                    name, lookback=lk, dev_atr_mult=dam, k_continuation=3,
                    stop_pts=stop, target_pts=tgt, fade=False))
                name = f"VW_lk{lk}_d{int(dam*10)}_s{stop}t{tgt}_FADE"
                v1m.append(VWAPDeviation(
                    name, lookback=lk, dev_atr_mult=dam, k_continuation=3,
                    stop_pts=stop, target_pts=tgt, fade=True))

    # ----------------------------------------
    # I. NBR with marketable-LIMIT
    # ----------------------------------------
    for n in [3, 4, 5]:
        for stop, tgt in [(3, 9), (4, 12), (5, 15), (5, 20), (8, 24)]:
            name = f"NBRM{n}_s{stop}t{tgt}"
            v1m.append(NBarReversalMkt(
                name, n_bars=n, stop_pts=stop, target_pts=tgt,
                min_move=3.0))

    # ----------------------------------------
    # J. SESSION-FILTERED MARKETABLE pullbacks
    # ----------------------------------------
    sessions = {
        'NYO30': ((13, 30), (14, 0)),
        'NYO60': ((13, 30), (14, 30)),
        'NYO': ((13, 30), (20, 0)),
        'RTH': ((13, 30), (20, 0)),
        'LON': ((7, 0), (9, 0)),
        'ASIA': ((0, 0), (4, 0)),
        'CME15': ((22, 0), (22, 15)),
    }
    for sn, (ss, se) in sessions.items():
        for stop, tgt in [(5, 15), (8, 24)]:
            name = f"MKT_pp236_s{stop}t{tgt}_imp5_{sn}"
            v1m.append(MarketablePullback(
                name, impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
                stop_pts=stop, target_pts=tgt, invert=True,
                session_start=ss, session_end=se))

    # ----------------------------------------
    # K. CROSS-SESSION MOMENTUM (breakouts at session opens)
    # ----------------------------------------
    for sn, (ss, se) in [('NYO15', ((13, 30), (13, 45))),
                          ('NYO60_BRK', ((13, 30), (14, 30))),
                          ('LONOPEN', ((7, 0), (8, 0))),
                          ('CMEOPEN', ((22, 0), (22, 30)))]:
        for stop, tgt in [(5, 15), (8, 24)]:
            name = f"BRK_n20_s{stop}t{tgt}_{sn}"
            v1m.append(BreakoutStrategy(
                name, n_bars=20, buf_pts=0.25, stop_pts=stop,
                target_pts=tgt, session_start=ss, session_end=se))

    # ----------------------------------------
    # L. WIDER-stop / higher-RR marketable pullback (insurance against slip)
    # ----------------------------------------
    for stop, tgt in [(10, 50), (12, 60), (15, 75), (7, 35), (10, 60)]:
        name = f"MKT_pp236_s{stop}t{tgt}_imp5_HRR"
        v1m.append(MarketablePullback(
            name, impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
            stop_pts=stop, target_pts=tgt, invert=True))

    # ----------------------------------------
    # M. Volume bar variants of marketable pullback
    # ----------------------------------------
    for ticks_per in [500, 1000]:
        bucket = vvol_500 if ticks_per == 500 else vvol_1k
        for stop, tgt in [(3, 9), (4, 12), (5, 15), (8, 24)]:
            name = f"MKTvol{ticks_per}_s{stop}t{tgt}"
            bucket.append(MarketablePullback(
                name, impulse_pts=3.0, impulse_bars=4, pull_pct=0.236,
                stop_pts=stop, target_pts=tgt, invert=True, max_hold=180))

    # ----------------------------------------
    # N. LONG-only / SHORT-only marketable pullbacks
    # ----------------------------------------
    for stop, tgt in [(5, 15), (8, 24)]:
        for side_only in ['LONG', 'SHORT']:
            name = f"MKT_pp236_s{stop}t{tgt}_imp5_{side_only}only"
            kwargs = {'long_only': side_only == 'LONG',
                      'short_only': side_only == 'SHORT'}
            v1m.append(MarketablePullback(
                name, impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
                stop_pts=stop, target_pts=tgt, invert=True, **kwargs))

    # Attach executor + initialize state on all
    all_lists = [v1m, v15s, v30s, vvol_500, vvol_1k, vtick]
    n_total = 0
    for ls in all_lists:
        for s in ls:
            attach_executor(s)
            n_total += 1
    return v1m, v15s, v30s, vvol_500, vvol_1k, vtick, n_total


# ===========================================================================
# Checkpoint
# ===========================================================================
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
        print(f"[round6] checkpoint load failed: {e!r}", file=sys.stderr)
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
    ap.add_argument("--max-days", type=int, default=60)
    args = ap.parse_args()

    ckpt_path = ("/home/user/HFTBot/research/round6_checkpoint"
                 f"{args.ckpt_suffix}.pkl")
    csv_path = ("/home/user/HFTBot/research/round6_summary"
                f"{args.ckpt_suffix}.csv")
    md_path = ("/home/user/HFTBot/research/round6_results"
               f"{args.ckpt_suffix}.md")

    v1m, v15s, v30s, vvol_500, vvol_1k, vtick, n_total = build_variants_round6()
    all_strats = v1m + v15s + v30s + vvol_500 + vvol_1k + vtick
    print(f"\n[round6] Built {len(all_strats)} strategies for bot-faithful "
          f"execution: {len(v1m)} 1m + {len(v15s)} 15s + {len(v30s)} 30s + "
          f"{len(vvol_500)} vol500 + {len(vvol_1k)} vol1k + "
          f"{len(vtick)} tick", file=sys.stderr)
    print(f"[round6] starting offset {args.offset:,}, ckpt={ckpt_path}",
          file=sys.stderr)

    resumed = load_checkpoint(ckpt_path, all_strats)
    if resumed is not None:
        start_offset, day_counter, last_day_key = resumed
        resumed_trades = sum(s.n_trades for s in all_strats)
        print(f"[round6] RESUMING from offset {start_offset:,} "
              f"day_counter={day_counter} ({resumed_trades:,} trades booked)",
              file=sys.stderr)
    else:
        start_offset = args.offset
        day_counter = -1
        last_day_key = None

    bb_1m = BarBuilder(granularity_secs=60, max_history=300)
    bb_15s = BarBuilder(granularity_secs=15, max_history=200)
    bb_30s = BarBuilder(granularity_secs=30, max_history=200)
    vb_500 = VolumeBarBuilder(ticks_per_bar=500, max_history=300)
    vb_1k = VolumeBarBuilder(ticks_per_bar=1000, max_history=300)

    n_lines = 0
    t_start = time.time()
    last_progress_t = t_start
    last_progress_ticks = 0

    file_size = os.path.getsize(PATH)
    print(f"[round6] file size: {file_size:,} bytes", file=sys.stderr)

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
                    print(f"  [round6] ckpt save failed: {e!r}", file=sys.stderr)
                print(f"  [round6] {n_lines/1e6:.1f}M ticks rate={rate/1e6:.2f}M/s "
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
            if vvol_500 and vb_500.on_tick(ts, last):
                closed = vb_500.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    for s in vvol_500:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, vb_500.history)
            if vvol_1k and vb_1k.on_tick(ts, last):
                closed = vb_1k.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    for s in vvol_1k:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, vb_1k.history)

            # Tick-momentum strategies need every tick's last-price.
            for s in vtick:
                s.feed_last(ts, last)

            for s in v1m:
                if hasattr(s, "_last_bid"):
                    s._last_bid = bid
                    s._last_ask = ask

            for s in all_strats:
                bot_on_tick(s, ts, bid, ask, day_counter, hh, mn)

    elapsed = time.time() - t_start
    total_days = day_counter + 1
    print(f"\n[round6] DONE in {elapsed/60:.1f}min, {n_lines:,} ticks, "
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
    print(f"[round6] wrote CSV {csv_path}", file=sys.stderr)

    full_pass = [r for r in rows if r['trades_per_day'] >= 300
                 and r['wr'] >= 0.45 and r['per_day'] >= 1000
                 and r['max_dd'] <= 5000]

    lines = []
    lines.append(f"# Round 6 strategy search results (offset={args.offset:,})\n\n")
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
    print(f"[round6] wrote MD {md_path}", file=sys.stderr)

    print("\n" + "=" * 110)
    print(f"{'Strategy':>30s} {'N':>7s} {'/day':>6s} {'WR%':>5s} "
          f"{'$/day':>9s} {'$/tr':>7s} {'maxDD':>9s} {'sharpe':>6s}")
    print("=" * 110)
    for r in rows[:30]:
        flag = ""
        if (r['trades_per_day'] >= 300 and r['wr'] >= 0.45
                and r['per_day'] >= 1000 and r['max_dd'] <= 5000):
            flag = " *PASS*"
        elif r['per_day'] >= 1000:
            flag = "  $$"
        print(f"{r['name']:>30s} {r['n']:>7d} {r['trades_per_day']:>6.1f} "
              f"{r['wr']*100:>4.1f}% ${r['per_day']:>+8.0f} "
              f"${r['per_trade']:>+6.2f} ${r['max_dd']:>+8.0f} "
              f"{r['sharpe']:>+6.2f}{flag}")
    print(f"\nFULL_PASS strategies: {len(full_pass)}")

    try:
        if os.path.exists(ckpt_path):
            os.remove(ckpt_path)
            print(f"[round6] cleared checkpoint {ckpt_path}",
                  file=sys.stderr)
    except Exception:
        pass


if __name__ == "__main__":
    main()
