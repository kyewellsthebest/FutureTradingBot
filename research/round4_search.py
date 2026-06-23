"""Round 4 strategy search for MNQ.

BUG FIX vs round3_search.py:
  In PullbackStrategy (the harness), the entry trigger check was using
  s['side'] (post-invert) instead of s['orig'] (impulse direction).
  For INVERSE strategies this fires entries on momentum continuation
  instead of waiting for the pullback fill — explains the 24,856 trade
  count at 13.5% WR for CANON_INV_236_s10t20 (vs sim_honest_battery's
  few hundred trades at ~54% WR).

  Fix: store and use 'orig' side for the entry trigger condition.

Direction for round 4 (after harness verification):
  - High R:R parameter sweep on inverted pullback
  - 3BR/4BR/5BR variants
  - Adaptive exits (breakeven, trailing)
  - Multi-signal confluence
  - Reverse direction with high RR
  - LONG-only variants
  - Time-of-day extreme filters
  - Volume bars
  - Spread-aware entries
  - Anti-impulse / pullback failure
  - Momentum confluence (RSI/MACD)

EXECUTION MODEL (mirrors sim_honest_battery + live cost adjustment):
  - 1 MNQ ($2/pt)
  - LIMIT entry: LONG fills when ASK <= entry_px (entry IS a pullback long)
                 SHORT fills when BID >= entry_px (entry IS a pullback short)
  - But IMPORTANT for INVERSE: 'orig' direction governs the trigger
    (the price has to pull back to the level on the impulse side).
  - Stop-MARKET exit: LONG fills at stop_px - 0.5pt when bid <= stop_px;
                      SHORT fills at stop_px + 0.5pt when ask >= stop_px
  - LIMIT target exit: LONG fills when BID >= target_px; SHORT when ASK <= target_px
  - 0.5pt entry slip on top of limit
  - $1.91 round-trip cost = $0.74 commission + $1.17 exchange/clearing fees
  - 10s default minimum cooldown after exit
  - 600s max hold (timeout exit at midpoint)
"""
from __future__ import annotations
import csv
import math
import os
import pickle
import sys
import time
from collections import deque
from datetime import datetime, timezone

PATH = "/home/user/HFTBot/data/tick/ustech/USTECH_full.csv"
START_OFFSET = 7_820_974_790

CHECKPOINT_PATH = "/home/user/HFTBot/research/round4_checkpoint.pkl"
CHECKPOINT_EVERY_TICKS = 5_000_000

COMM_RT = 0.74
EXCH_FEES_RT = 1.17
TOTAL_RT_COST = COMM_RT + EXCH_FEES_RT  # $1.91
MNQ_PER_PT = 2.0
ENTRY_SLIP = 0.5
STOP_SLIP = 0.5
MAX_HOLD_SECS = 600

TICK = 0.25


def _round_long_entry(px):
    return math.floor(px / TICK) * TICK


def _round_short_entry(px):
    return math.ceil(px / TICK) * TICK


def _round_long_stop(px):
    return math.ceil(px / TICK) * TICK


def _round_short_stop(px):
    return math.floor(px / TICK) * TICK


def _round_long_tgt(px):
    return math.ceil(px / TICK) * TICK


def _round_short_tgt(px):
    return math.floor(px / TICK) * TICK


# ===========================================================================
# Generic strategy base — handles execution. Subclasses generate signals.
# ===========================================================================
class StrategyBase:
    """Generic execution engine.

    Setups carry both 'side' (final trade direction) AND 'orig' (the
    original signal/impulse direction).  Triggers use 'orig' so that
    INVERSE strategies still wait for the price to pull back to the
    impulse-side level instead of firing on the immediate post-impulse
    move.
    """
    __slots__ = (
        "name", "cooldown_s", "max_hold", "pending", "in_trade",
        "completed", "by_day", "last_exit_dt", "n_trades",
        "session_start", "session_end",
        # Adaptive exit params
        "be_trigger_pts", "be_offset_pts",
        "trail_distance_pts",
        "scale_out_pts", "scale_out_frac",
    )

    def __init__(self, name, cooldown_s=10, max_hold=MAX_HOLD_SECS,
                 session_start=None, session_end=None,
                 be_trigger_pts=None, be_offset_pts=0.0,
                 trail_distance_pts=None,
                 scale_out_pts=None, scale_out_frac=0.5):
        self.name = name
        self.cooldown_s = cooldown_s
        self.max_hold = max_hold
        self.pending = []
        self.in_trade = None
        self.completed = []
        self.by_day = {}
        self.last_exit_dt = None
        self.n_trades = 0
        self.session_start = session_start
        self.session_end = session_end
        self.be_trigger_pts = be_trigger_pts
        self.be_offset_pts = be_offset_pts
        self.trail_distance_pts = trail_distance_pts
        self.scale_out_pts = scale_out_pts
        self.scale_out_frac = scale_out_frac

    def _in_session(self, hh, mn):
        if self.session_start is None:
            return True
        t = hh * 60 + mn
        s = self.session_start[0] * 60 + self.session_start[1]
        e = self.session_end[0] * 60 + self.session_end[1]
        if s < e:
            return s <= t < e
        else:
            return t >= s or t < e

    def on_bar_close(self, ts, hh, mn, bar_o, bar_h, bar_l, bar_c, hist):
        pass

    def on_tick_signal(self, ts, bid, ask, hh, mn):
        pass

    def add_setup(self, side, orig, entry, stop, target, ts_now, key=None,
                  expires_in=300, extra=None):
        if side == "LONG":
            entry_r = _round_long_entry(entry)
            stop_r = _round_long_stop(stop)
            target_r = _round_long_tgt(target)
        else:
            entry_r = _round_short_entry(entry)
            stop_r = _round_short_stop(stop)
            target_r = _round_short_tgt(target)
        if key is not None and any(s['key'] == key and not s['used']
                                   for s in self.pending):
            return
        setup = {
            'side': side, 'orig': orig,
            'entry': entry_r, 'stop': stop_r, 'target': target_r,
            'expires': ts_now + expires_in, 'used': False, 'key': key,
        }
        if extra:
            setup.update(extra)
        self.pending.append(setup)

    def on_tick(self, ts, bid, ask, day_counter, hh, mn):
        if self.pending:
            self.pending = [s for s in self.pending
                            if s['expires'] >= ts and not s['used']]

        if self.in_trade is not None:
            tr = self.in_trade
            exit_now = None
            scaled = False
            if tr['side'] == 'LONG':
                # Adaptive: scale out partial when reached
                if (self.scale_out_pts is not None and
                        not tr.get('scaled') and
                        bid >= tr['entry'] + self.scale_out_pts):
                    # close scale_out_frac, raise stop to BE+offset
                    partial_pnl = self.scale_out_pts
                    tr['scaled_pnl'] = (tr.get('scaled_pnl', 0.0) +
                                        partial_pnl * self.scale_out_frac)
                    tr['scaled'] = True
                    tr['size_remaining'] = 1.0 - self.scale_out_frac
                    # Move stop to BE
                    new_stop = tr['entry']
                    if new_stop > tr['stop']:
                        tr['stop'] = new_stop
                    scaled = True
                # Breakeven move
                if (self.be_trigger_pts is not None and not tr.get('be_set')
                        and bid >= tr['entry'] + self.be_trigger_pts):
                    new_stop = tr['entry'] + self.be_offset_pts
                    if new_stop > tr['stop']:
                        tr['stop'] = new_stop
                    tr['be_set'] = True
                # Trailing
                if self.trail_distance_pts is not None:
                    high_seen = max(tr.get('high_seen', bid), bid)
                    tr['high_seen'] = high_seen
                    trail_stop = high_seen - self.trail_distance_pts
                    if trail_stop > tr['stop']:
                        tr['stop'] = trail_stop
                # Exit checks
                if bid <= tr['stop']:
                    pnl = (tr['stop'] - STOP_SLIP) - tr['entry']
                    exit_now = ('stop', pnl)
                elif bid >= tr['target']:
                    pnl = tr['target'] - tr['entry']
                    exit_now = ('tgt', pnl)
                elif ts - tr['et'] >= self.max_hold:
                    pnl = bid - tr['entry']
                    exit_now = ('to', pnl)
            else:  # SHORT
                if (self.scale_out_pts is not None and
                        not tr.get('scaled') and
                        ask <= tr['entry'] - self.scale_out_pts):
                    partial_pnl = self.scale_out_pts
                    tr['scaled_pnl'] = (tr.get('scaled_pnl', 0.0) +
                                        partial_pnl * self.scale_out_frac)
                    tr['scaled'] = True
                    tr['size_remaining'] = 1.0 - self.scale_out_frac
                    new_stop = tr['entry']
                    if new_stop < tr['stop']:
                        tr['stop'] = new_stop
                    scaled = True
                if (self.be_trigger_pts is not None and not tr.get('be_set')
                        and ask <= tr['entry'] - self.be_trigger_pts):
                    new_stop = tr['entry'] - self.be_offset_pts
                    if new_stop < tr['stop']:
                        tr['stop'] = new_stop
                    tr['be_set'] = True
                if self.trail_distance_pts is not None:
                    low_seen = min(tr.get('low_seen', ask), ask)
                    tr['low_seen'] = low_seen
                    trail_stop = low_seen + self.trail_distance_pts
                    if trail_stop < tr['stop']:
                        tr['stop'] = trail_stop
                if ask >= tr['stop']:
                    pnl = tr['entry'] - (tr['stop'] + STOP_SLIP)
                    exit_now = ('stop', pnl)
                elif ask <= tr['target']:
                    pnl = tr['entry'] - tr['target']
                    exit_now = ('tgt', pnl)
                elif ts - tr['et'] >= self.max_hold:
                    pnl = tr['entry'] - ask
                    exit_now = ('to', pnl)
            if exit_now is not None:
                reason, pnl = exit_now
                size_rem = tr.get('size_remaining', 1.0)
                # Apply remaining size
                eff_pnl = pnl * size_rem + tr.get('scaled_pnl', 0.0)
                pnl_usd = eff_pnl * MNQ_PER_PT - TOTAL_RT_COST
                self.completed.append((pnl_usd, reason, day_counter))
                self.by_day.setdefault(day_counter, []).append(pnl_usd)
                self.last_exit_dt = ts
                self.in_trade = None
                self.n_trades += 1
            return

        if self.last_exit_dt is not None:
            if ts - self.last_exit_dt < self.cooldown_s:
                return

        if not self._in_session(hh, mn):
            return

        # Try entry trigger — USE 'orig' to determine which side of price
        # we need (BUG FIX vs round3).
        for s in self.pending:
            if s['used']:
                continue
            orig = s.get('orig', s['side'])
            if orig == 'LONG':
                trig = ask <= s['entry']
            else:
                trig = bid >= s['entry']
            if trig:
                if s['side'] == 'LONG':
                    actual = s['entry'] + ENTRY_SLIP
                else:
                    actual = s['entry'] - ENTRY_SLIP
                self.in_trade = {
                    'side': s['side'], 'entry': actual,
                    'stop': s['stop'], 'target': s['target'],
                    'et': ts,
                }
                s['used'] = True
                break

    def report(self, total_days):
        n = len(self.completed)
        if n == 0:
            return {
                'name': self.name, 'n': 0, 'wr': 0.0, 'net': 0.0,
                'per_day': 0.0, 'per_trade': 0.0, 'pos_d': 0, 'neg_d': 0,
                'worst': 0.0, 'best': 0.0, 'max_dd': 0.0,
                'trades_per_day': 0.0, 'sharpe': 0.0, 'n_days': 0,
            }
        wins = sum(1 for c in self.completed if c[0] > 0)
        wr = wins / n
        net = sum(c[0] for c in self.completed)
        per_day = net / max(1, total_days)
        per_trade = net / n
        trades_per_day = n / max(1, total_days)
        day_nets = [sum(self.by_day[d]) for d in self.by_day]
        n_days = len(day_nets)
        pos_d = sum(1 for x in day_nets if x > 0)
        neg_d = sum(1 for x in day_nets if x < 0)
        worst = min(day_nets)
        best = max(day_nets)
        cum = 0.0
        peak = 0.0
        max_dd = 0.0
        for c in self.completed:
            cum += c[0]
            if cum > peak:
                peak = cum
            if peak - cum > max_dd:
                max_dd = peak - cum
        if n_days > 1:
            mean = sum(day_nets) / n_days
            var = sum((x - mean) ** 2 for x in day_nets) / (n_days - 1)
            std = math.sqrt(var)
            sharpe = (mean / std) if std > 0 else 0.0
        else:
            sharpe = 0.0
        return {
            'name': self.name, 'n': n, 'wr': wr, 'net': net,
            'per_day': per_day, 'per_trade': per_trade,
            'pos_d': pos_d, 'neg_d': neg_d, 'worst': worst, 'best': best,
            'max_dd': max_dd, 'trades_per_day': trades_per_day,
            'sharpe': sharpe, 'n_days': n_days,
        }


# ===========================================================================
# Pullback strategy — uses ORIG direction for trigger (FIXED)
# ===========================================================================
class PullbackStrategy(StrategyBase):
    def __init__(self, name, impulse_pts, impulse_bars, pull_pct,
                 stop_pts, target_pts, invert=True, cooldown_s=10,
                 session_start=None, session_end=None, atr_min=None,
                 atr_max=None, atr_bars=20, max_hold=MAX_HOLD_SECS,
                 long_only=False, short_only=False,
                 be_trigger_pts=None, be_offset_pts=0.0,
                 trail_distance_pts=None,
                 scale_out_pts=None, scale_out_frac=0.5,
                 max_spread_pts=None,
                 require_3br=False, three_br_min=3.0, three_br_max_mid=2.0):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start,
                         session_end=session_end,
                         be_trigger_pts=be_trigger_pts,
                         be_offset_pts=be_offset_pts,
                         trail_distance_pts=trail_distance_pts,
                         scale_out_pts=scale_out_pts,
                         scale_out_frac=scale_out_frac)
        self.impulse_pts = impulse_pts
        self.impulse_bars = impulse_bars
        self.pull_pct = pull_pct
        self.stop_pts = stop_pts
        self.target_pts = target_pts
        self.invert = invert
        self.atr_min = atr_min
        self.atr_max = atr_max
        self.atr_bars = atr_bars
        self.long_only = long_only
        self.short_only = short_only
        self.max_spread_pts = max_spread_pts
        self.require_3br = require_3br
        self.three_br_min = three_br_min
        self.three_br_max_mid = three_br_max_mid
        self._last_bid = None
        self._last_ask = None

    def on_tick_signal(self, ts, bid, ask, hh, mn):
        self._last_bid = bid
        self._last_ask = ask

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

        # Optional 3BR confluence — only fire if last 3 bars form an
        # opposing reversal pattern.
        if self.require_3br and nbars >= 3:
            b1 = hist[-3]; b2 = hist[-2]; b3 = hist[-1]
            bullish_3br = (b1[3]-b1[0] <= -self.three_br_min and
                           abs(b2[3]-b2[0]) < self.three_br_max_mid and
                           b3[3]-b3[0] >= self.three_br_min)
            bearish_3br = (b1[3]-b1[0] >= self.three_br_min and
                           abs(b2[3]-b2[0]) < self.three_br_max_mid and
                           b3[3]-b3[0] <= -self.three_br_min)
            # For INVERSE LONG impulse (we go SHORT), need bearish 3BR;
            # for INVERSE SHORT impulse (we go LONG), need bullish 3BR.
            # For non-invert, require matching direction.
            want_long_trade = (orig_side == "SHORT") if self.invert else (orig_side == "LONG")
            if want_long_trade and not bullish_3br:
                return
            if (not want_long_trade) and not bearish_3br:
                return

        side = ("SHORT" if orig_side == "LONG" else "LONG") if self.invert else orig_side

        # Direction filters
        if self.long_only and side != "LONG":
            return
        if self.short_only and side != "SHORT":
            return

        # Spread filter
        if (self.max_spread_pts is not None and self._last_bid is not None
                and self._last_ask is not None):
            spread = self._last_ask - self._last_bid
            if spread > self.max_spread_pts:
                return

        if orig_side == "LONG":
            entry = ih - self.pull_pct * rng
        else:
            entry = il + self.pull_pct * rng
        if side == "LONG":
            stop = entry - self.stop_pts
            target = entry + self.target_pts
        else:
            stop = entry + self.stop_pts
            target = entry - self.target_pts
        key = (round(ih, 1), round(il, 1), orig_side)
        self.add_setup(side, orig_side, entry, stop, target, ts,
                       key=key, expires_in=300)


# ===========================================================================
# Anti-impulse / pullback FAILURE — when an impulse is followed by price
# returning to and breaking the OPPOSITE extreme of the impulse range,
# fade the failure in the direction of the breakout.
# ===========================================================================
class PullbackFailure(StrategyBase):
    """After an N-bar impulse, watch for the impulse high/low to be
    *broken* in the opposite direction within `expiry` seconds. When the
    break happens, enter a momentum trade in the break direction.
    """
    def __init__(self, name, impulse_pts=5.0, impulse_bars=4,
                 stop_pts=4, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 max_hold=MAX_HOLD_SECS, expiry=300):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.impulse_pts = impulse_pts
        self.impulse_bars = impulse_bars
        self.stop_pts = stop_pts
        self.target_pts = target_pts
        self.expiry = expiry

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        nbars = len(hist)
        if nbars < self.impulse_bars:
            return
        win = list(hist)[-self.impulse_bars:]
        net = win[-1][3] - win[0][0]
        if abs(net) < self.impulse_pts:
            return
        ih = max(b[1] for b in win)
        il = min(b[2] for b in win)
        # If impulse was UP, then a BREAK below il is the failure -> SHORT
        # If impulse was DOWN, then a BREAK above ih is the failure -> LONG
        if net > 0:
            entry = il
            stop = entry + self.stop_pts
            target = entry - self.target_pts
            self.add_setup("SHORT", "SHORT", entry, stop, target, ts,
                           key=("pbf_s", round(ih, 1), round(il, 1)),
                           expires_in=self.expiry)
        else:
            entry = ih
            stop = entry - self.stop_pts
            target = entry + self.target_pts
            self.add_setup("LONG", "LONG", entry, stop, target, ts,
                           key=("pbf_l", round(ih, 1), round(il, 1)),
                           expires_in=self.expiry)


# ===========================================================================
# N-bar reversal (3BR / 4BR / 5BR)
# ===========================================================================
class NBarReversal(StrategyBase):
    """N-bar reversal: bar1..(N-2) trend down, bar(N-1) doji/small,
    bar(N) trend up (mirror for bearish). Enter on close of bar(N).
    """
    def __init__(self, name, n_bars=3, stop_pts=4, target_pts=12,
                 cooldown_s=10, session_start=None, session_end=None,
                 min_move=3.0, max_mid_range=2.0,
                 be_trigger_pts=None, be_offset_pts=0.0,
                 trail_distance_pts=None,
                 max_hold=MAX_HOLD_SECS):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start,
                         session_end=session_end,
                         be_trigger_pts=be_trigger_pts,
                         be_offset_pts=be_offset_pts,
                         trail_distance_pts=trail_distance_pts)
        self.n_bars = n_bars
        self.stop_pts = stop_pts
        self.target_pts = target_pts
        self.min_move = min_move
        self.max_mid_range = max_mid_range

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.n_bars:
            return
        bars = list(hist)[-self.n_bars:]
        # Bullish: cumulative move of bars[0..N-2] is down, bars[N-2] is small,
        #          bars[N-1] is up
        down_part = bars[:-1]
        last = bars[-1]
        cum_down = sum(b[3] - b[0] for b in down_part)
        last_move = last[3] - last[0]
        mid_bar = bars[-2]
        mid_move = abs(mid_bar[3] - mid_bar[0])
        if cum_down <= -self.min_move * (self.n_bars - 1) * 0.6 and \
           mid_move < self.max_mid_range and \
           last_move >= self.min_move:
            entry = last[3] - 1.0
            stop = min(mid_bar[2], last[2]) - 0.5
            target = entry + self.target_pts
            if entry > stop:
                self.add_setup("LONG", "LONG", entry, stop, target, ts,
                               key=("nbr_l", round(mid_bar[0], 1),
                                    self.n_bars), expires_in=180)
        cum_up = sum(b[3] - b[0] for b in down_part)
        if cum_up >= self.min_move * (self.n_bars - 1) * 0.6 and \
           mid_move < self.max_mid_range and \
           last_move <= -self.min_move:
            entry = last[3] + 1.0
            stop = max(mid_bar[1], last[1]) + 0.5
            target = entry - self.target_pts
            if entry < stop:
                self.add_setup("SHORT", "SHORT", entry, stop, target, ts,
                               key=("nbr_s", round(mid_bar[0], 1),
                                    self.n_bars), expires_in=180)


# ===========================================================================
# RSI-based mean reversion
# ===========================================================================
class RSIReversion(StrategyBase):
    """Compute 14-bar RSI on closes. When RSI >= upper, fade short;
    when RSI <= lower, fade long.
    """
    def __init__(self, name, period=14, upper=70, lower=30,
                 stop_pts=6, target_pts=10, cooldown_s=10,
                 session_start=None, session_end=None):
        super().__init__(name, cooldown_s=cooldown_s,
                         session_start=session_start, session_end=session_end)
        self.period = period
        self.upper = upper
        self.lower = lower
        self.stop_pts = stop_pts
        self.target_pts = target_pts

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.period + 1:
            return
        closes = [hist[i][3] for i in range(len(hist) - self.period - 1, len(hist))]
        gains = 0.0; losses = 0.0
        for i in range(1, len(closes)):
            d = closes[i] - closes[i - 1]
            if d > 0:
                gains += d
            else:
                losses += -d
        if losses == 0:
            rsi = 100.0
        else:
            rs = gains / losses
            rsi = 100.0 - 100.0 / (1.0 + rs)
        if rsi >= self.upper:
            entry = bc
            stop = bc + self.stop_pts
            target = bc - self.target_pts
            self.add_setup("SHORT", "SHORT", entry, stop, target, ts,
                           key=("rsi_s", round(bc, 1)), expires_in=120)
        elif rsi <= self.lower:
            entry = bc
            stop = bc - self.stop_pts
            target = bc + self.target_pts
            self.add_setup("LONG", "LONG", entry, stop, target, ts,
                           key=("rsi_l", round(bc, 1)), expires_in=120)


# ===========================================================================
# Volume-bar pullback — bars built by tick count instead of time
# ===========================================================================
class VolumeBarBuilder:
    __slots__ = ("ticks_per_bar", "n_ticks", "cur_bar", "history", "max_history")

    def __init__(self, ticks_per_bar=1000, max_history=300):
        self.ticks_per_bar = ticks_per_bar
        self.n_ticks = 0
        self.cur_bar = None
        self.history = deque(maxlen=max_history)
        self.max_history = max_history

    def on_tick(self, ts, last):
        if self.cur_bar is None:
            self.cur_bar = [last, last, last, last]
            self.n_ticks = 1
            return False
        self.n_ticks += 1
        if last > self.cur_bar[1]:
            self.cur_bar[1] = last
        if last < self.cur_bar[2]:
            self.cur_bar[2] = last
        self.cur_bar[3] = last
        if self.n_ticks >= self.ticks_per_bar:
            self.history.append(tuple(self.cur_bar))
            self.cur_bar = None
            self.n_ticks = 0
            return True
        return False

    def closed_bar(self):
        if not self.history:
            return None
        return self.history[-1]


# ===========================================================================
# Bar builder (time-based)
# ===========================================================================
class BarBuilder:
    __slots__ = ("granularity", "cur_bucket", "cur_bar", "history", "max_history")

    def __init__(self, granularity_secs=60, max_history=300):
        self.granularity = granularity_secs
        self.cur_bucket = None
        self.cur_bar = None
        self.history = deque(maxlen=max_history)
        self.max_history = max_history

    def on_tick(self, ts, last):
        bucket = int(ts // self.granularity)
        if self.cur_bucket is None:
            self.cur_bucket = bucket
            self.cur_bar = [last, last, last, last]
            return False
        if bucket == self.cur_bucket:
            if last > self.cur_bar[1]: self.cur_bar[1] = last
            if last < self.cur_bar[2]: self.cur_bar[2] = last
            self.cur_bar[3] = last
            return False
        self.history.append(tuple(self.cur_bar))
        self.cur_bucket = bucket
        self.cur_bar = [last, last, last, last]
        return True

    def closed_bar(self):
        if not self.history:
            return None
        return self.history[-1]


# ===========================================================================
# Build variants: 60+ NEW strategies for round 4
# ===========================================================================
def build_variants():
    v1m = []   # 1-min bar
    v15s = []  # 15-second bar
    v30s = []  # 30-second bar
    vtick = [] # tick-only
    vvol_1k = []  # volume bars of 1000 ticks
    vvol_500 = [] # volume bars of 500 ticks

    # ====== CANONICAL verification ======
    # Same params as sim_honest_battery.INV_236_s10t20_cd10
    v1m.append(PullbackStrategy(
        "CANON_INV_236_s10t20",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True))

    # ====== AVENUE 1: High R:R parameter sweep on INVERTED pullback ======
    # Mathematically need ~3pt edge per trade. 4:1 or 5:1 R:R helps.
    for pp in [0.118, 0.236, 0.382, 0.5]:
        for stop, tgt in [(2, 10), (3, 12), (3, 15), (2, 12), (3, 9), (4, 16), (5, 20)]:
            for imp in [3.0, 5.0]:
                name = f"INV_pp{int(pp*1000)}_s{stop}t{tgt}_imp{int(imp)}"
                v1m.append(PullbackStrategy(
                    name, impulse_pts=imp, impulse_bars=4, pull_pct=pp,
                    stop_pts=stop, target_pts=tgt, invert=True))

    # ====== AVENUE 2: 3BR / 4BR / 5BR ======
    for n_bars in [3, 4, 5]:
        for stop, tgt in [(3, 12), (4, 16), (5, 20), (3, 9), (2, 8)]:
            v1m.append(NBarReversal(
                f"NBR{n_bars}_s{stop}t{tgt}",
                n_bars=n_bars, stop_pts=stop, target_pts=tgt,
                min_move=3.0))
        # RTH variant
        v1m.append(NBarReversal(
            f"NBR{n_bars}_s4t12_RTH",
            n_bars=n_bars, stop_pts=4, target_pts=12, min_move=3.0,
            session_start=(13, 30), session_end=(20, 0)))

    # ====== AVENUE 3: Adaptive exits (breakeven, trail) on best base ======
    v1m.append(PullbackStrategy(
        "INV_236_s10t20_BE2",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True,
        be_trigger_pts=2.0))
    v1m.append(PullbackStrategy(
        "INV_236_s10t20_BE3",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True,
        be_trigger_pts=3.0))
    v1m.append(PullbackStrategy(
        "INV_236_s10t20_TRAIL3",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True,
        trail_distance_pts=3.0))
    v1m.append(PullbackStrategy(
        "INV_236_s10t20_TRAIL2",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True,
        trail_distance_pts=2.0))

    # ====== AVENUE 4: Scale-out ======
    v1m.append(PullbackStrategy(
        "INV_236_s10t20_SCALE5",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True,
        scale_out_pts=5.0, scale_out_frac=0.5))
    v1m.append(PullbackStrategy(
        "INV_236_s10t20_SCALE3",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True,
        scale_out_pts=3.0, scale_out_frac=0.5))

    # ====== AVENUE 5: 3BR confluence with pullback ======
    v1m.append(PullbackStrategy(
        "INV_236_s10t20_3BR",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True,
        require_3br=True))
    v1m.append(PullbackStrategy(
        "INV_236_s5t15_3BR",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=5, target_pts=15, invert=True,
        require_3br=True))

    # ====== AVENUE 6: Non-inverted high R:R ======
    for pp in [0.236, 0.382, 0.5]:
        for stop, tgt in [(3, 12), (4, 16), (5, 20)]:
            v1m.append(PullbackStrategy(
                f"ORIG_pp{int(pp*1000)}_s{stop}t{tgt}",
                impulse_pts=5.0, impulse_bars=4, pull_pct=pp,
                stop_pts=stop, target_pts=tgt, invert=False))

    # ====== AVENUE 7: LONG-only & SHORT-only inversions ======
    v1m.append(PullbackStrategy(
        "INV_236_s10t20_LONGonly",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True, long_only=True))
    v1m.append(PullbackStrategy(
        "INV_236_s10t20_SHORTonly",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True, short_only=True))
    v1m.append(PullbackStrategy(
        "INV_236_s5t15_LONGonly",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=5, target_pts=15, invert=True, long_only=True))
    v1m.append(PullbackStrategy(
        "INV_236_s5t15_SHORTonly",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=5, target_pts=15, invert=True, short_only=True))

    # ====== AVENUE 8: Time-of-day extreme filters ======
    # NY close (last 30 min of NYSE: 19:30-20:00 UTC)
    v1m.append(PullbackStrategy(
        "INV_236_s10t20_NYC30",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True,
        session_start=(19, 30), session_end=(20, 0)))
    # CME open first 15 min (22:00-22:15 UTC)
    v1m.append(PullbackStrategy(
        "INV_236_s10t20_CMEOPEN15",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True,
        session_start=(22, 0), session_end=(22, 15)))
    # NYSE open first 30 min (13:30-14:00 UTC)
    v1m.append(PullbackStrategy(
        "INV_236_s10t20_NYO30",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True,
        session_start=(13, 30), session_end=(14, 0)))
    # NYSE first hour
    v1m.append(PullbackStrategy(
        "INV_236_s5t15_NYO60",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=5, target_pts=15, invert=True,
        session_start=(13, 30), session_end=(14, 30)))
    # Europe open (07:00-09:00 UTC)
    v1m.append(PullbackStrategy(
        "INV_236_s10t20_EUOPEN",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True,
        session_start=(7, 0), session_end=(9, 0)))

    # ====== AVENUE 9: Spread-aware entries ======
    v1m.append(PullbackStrategy(
        "INV_236_s10t20_SPR05",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True,
        max_spread_pts=0.5))
    v1m.append(PullbackStrategy(
        "INV_236_s10t20_SPR025",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True,
        max_spread_pts=0.25))

    # ====== AVENUE 10: Anti-impulse / pullback failure ======
    v1m.append(PullbackFailure(
        "PBF_imp5_s4t12", impulse_pts=5.0, impulse_bars=4,
        stop_pts=4, target_pts=12))
    v1m.append(PullbackFailure(
        "PBF_imp5_s3t9", impulse_pts=5.0, impulse_bars=4,
        stop_pts=3, target_pts=9))
    v1m.append(PullbackFailure(
        "PBF_imp7_s4t16", impulse_pts=7.0, impulse_bars=4,
        stop_pts=4, target_pts=16))
    v1m.append(PullbackFailure(
        "PBF_imp3_s2t8", impulse_pts=3.0, impulse_bars=3,
        stop_pts=2, target_pts=8))

    # ====== AVENUE 11: RSI confluence ======
    v1m.append(RSIReversion("RSI14_70_30_s6t10"))
    v1m.append(RSIReversion("RSI14_80_20_s5t15", upper=80, lower=20,
                           stop_pts=5, target_pts=15))
    v1m.append(RSIReversion("RSI14_75_25_s4t12_RTH", upper=75, lower=25,
                           stop_pts=4, target_pts=12,
                           session_start=(13, 30), session_end=(20, 0)))

    # ====== AVENUE 12: Sub-minute pullbacks (15s/30s) with high R:R ======
    for stop, tgt in [(2, 8), (3, 9), (3, 12), (2, 10), (4, 12)]:
        v15s.append(PullbackStrategy(
            f"INV15s_imp2_s{stop}t{tgt}",
            impulse_pts=2.0, impulse_bars=4, pull_pct=0.236,
            stop_pts=stop, target_pts=tgt, invert=True, max_hold=120))
    for stop, tgt in [(3, 12), (4, 12), (3, 9), (2, 10)]:
        v30s.append(PullbackStrategy(
            f"INV30s_imp3_s{stop}t{tgt}",
            impulse_pts=3.0, impulse_bars=4, pull_pct=0.236,
            stop_pts=stop, target_pts=tgt, invert=True, max_hold=180))

    # ====== AVENUE 13: Volume-bar pullbacks ======
    for ticks_per in [500, 1000]:
        bucket = vvol_500 if ticks_per == 500 else vvol_1k
        for stop, tgt in [(3, 9), (3, 12), (4, 16), (2, 10)]:
            bucket.append(PullbackStrategy(
                f"INVvol{ticks_per}_imp3_s{stop}t{tgt}",
                impulse_pts=3.0, impulse_bars=4, pull_pct=0.236,
                stop_pts=stop, target_pts=tgt, invert=True,
                max_hold=120))

    # ====== AVENUE 14: Combined adaptive + session ======
    v1m.append(PullbackStrategy(
        "INV_236_s10t20_BE2_RTH",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True,
        be_trigger_pts=2.0,
        session_start=(13, 30), session_end=(20, 0)))
    v1m.append(PullbackStrategy(
        "INV_236_s10t20_TRAIL3_RTH",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True,
        trail_distance_pts=3.0,
        session_start=(13, 30), session_end=(20, 0)))

    return v1m, v15s, v30s, vtick, vvol_500, vvol_1k


# ===========================================================================
# Checkpoint
# ===========================================================================
def save_checkpoint(offset, day_counter, last_day_key, all_strats):
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
    }
    tmp = CHECKPOINT_PATH + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, CHECKPOINT_PATH)


def load_checkpoint(all_strats):
    if not os.path.exists(CHECKPOINT_PATH):
        return None
    try:
        with open(CHECKPOINT_PATH, "rb") as f:
            state = pickle.load(f)
    except Exception as e:
        print(f"[round4] checkpoint load failed: {e!r}", file=sys.stderr)
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
            state["last_day_key"])


def main():
    v1m, v15s, v30s, vtick, vvol_500, vvol_1k = build_variants()
    all_strats = v1m + v15s + v30s + vtick + vvol_500 + vvol_1k
    print(f"\n[round4] Built {len(all_strats)} strategies: "
          f"{len(v1m)} 1m + {len(v15s)} 15s + {len(v30s)} 30s + "
          f"{len(vtick)} tick + {len(vvol_500)} vol500 + {len(vvol_1k)} vol1k",
          file=sys.stderr)

    resumed = load_checkpoint(all_strats)
    if resumed is not None:
        start_offset, day_counter, last_day_key = resumed
        resumed_trades = sum(s.n_trades for s in all_strats)
        print(f"[round4] RESUMING from offset {start_offset:,} "
              f"day_counter={day_counter} ({resumed_trades:,} trades booked)",
              file=sys.stderr)
    else:
        start_offset = START_OFFSET
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
    print(f"[round4] file size: {file_size:,} bytes, start offset {start_offset:,}",
          file=sys.stderr)

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
                if all_strats:
                    top_n = max((s.n_trades, s.name) for s in all_strats)
                else:
                    top_n = (0, "?")
                try:
                    save_checkpoint(pos, day_counter, last_day_key, all_strats)
                except Exception as e:
                    print(f"  [round4] ckpt save failed: {e!r}", file=sys.stderr)
                print(f"  [round4] {n_lines/1e6:.1f}M ticks rate={rate/1e6:.2f}M/s "
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
            ts = day_counter * 86400 + hh * 3600 + mn * 60 + ss + ns / 1e7

            # 1-min bars
            if bb_1m.on_tick(ts, last):
                closed = bb_1m.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    for s in v1m:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_1m.history)
            # 15s bars
            if v15s and bb_15s.on_tick(ts, last):
                closed = bb_15s.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    for s in v15s:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_15s.history)
            # 30s bars
            if v30s and bb_30s.on_tick(ts, last):
                closed = bb_30s.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    for s in v30s:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_30s.history)
            # Volume bars 500
            if vvol_500 and vb_500.on_tick(ts, last):
                closed = vb_500.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    for s in vvol_500:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, vb_500.history)
            # Volume bars 1000
            if vvol_1k and vb_1k.on_tick(ts, last):
                closed = vb_1k.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    for s in vvol_1k:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, vb_1k.history)

            # Tick-level signal hooks
            for s in vtick:
                s.on_tick_signal(ts, bid, ask, hh, mn)
            # Update spread cache for spread-aware strategies
            for s in v1m:
                if isinstance(s, PullbackStrategy) and s.max_spread_pts is not None:
                    s._last_bid = bid
                    s._last_ask = ask

            # Trade execution
            for s in all_strats:
                s.on_tick(ts, bid, ask, day_counter, hh, mn)

    elapsed = time.time() - t_start
    total_days = day_counter + 1
    print(f"\n[round4] DONE in {elapsed/60:.1f}min, {n_lines:,} ticks, "
          f"{total_days} day buckets", file=sys.stderr)

    rows = []
    for s in all_strats:
        r = s.report(total_days)
        rows.append(r)
    rows.sort(key=lambda r: -r['per_day'])

    csv_path = "/home/user/HFTBot/research/round4_summary.csv"
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
    print(f"[round4] wrote CSV {csv_path}", file=sys.stderr)

    md_path = "/home/user/HFTBot/research/round4_results.md"
    lines = []
    lines.append("# Round 4 strategy search results\n\n")
    lines.append(f"Generated: {datetime.now().isoformat()}\n")
    lines.append(f"Period: 60-day window starting at file offset "
                 f"{START_OFFSET:,}, {total_days} calendar-day buckets.\n")
    lines.append(f"Tick stream: {n_lines:,} lines processed\n")
    lines.append(f"Costs applied: ${TOTAL_RT_COST:.2f}/RT "
                 f"(${COMM_RT:.2f} commission + ${EXCH_FEES_RT:.2f} fees), "
                 f"{STOP_SLIP}pt stop slip, {ENTRY_SLIP}pt entry slip\n\n")
    lines.append("## Harness FIX vs round3\n\n")
    lines.append("Round 3 had a trigger-side bug: it checked `s['side']` "
                 "(post-inversion direction) for the entry trigger, "
                 "instead of `s['orig']` (impulse direction). For INVERSE "
                 "strategies that fired entries on momentum continuation "
                 "rather than the pullback fill, generating massive trade "
                 "counts at terrible WR (e.g. CANON_INV_236_s10t20: "
                 "24,856 trades @ 13.5% WR in round3). Round 4 uses the "
                 "correct orig-side trigger.\n\n")
    lines.append("## Hard requirements\n")
    lines.append("- 300+ trades/day average\n")
    lines.append("- 45%+ win rate\n")
    lines.append("- $1000+ net daily P&L\n")
    lines.append("- Max DD <= $5000\n\n")

    lines.append("## Top 15 strategies by $/day\n\n")
    lines.append("| Rank | Strategy | Trades | Tr/day | WR% | Net $ | $/day | $/trade | maxDD | Worst d | Best d | Sharpe |\n")
    lines.append("|------|----------|-------:|-------:|----:|------:|------:|--------:|------:|--------:|-------:|-------:|\n")
    for i, r in enumerate(rows[:15], 1):
        lines.append(
            f"| {i} | {r['name']} | {r['n']:,} | {r['trades_per_day']:.1f} | "
            f"{r['wr']*100:.1f} | ${r['net']:,.0f} | ${r['per_day']:,.0f} | "
            f"${r['per_trade']:.2f} | ${r['max_dd']:,.0f} | "
            f"${r['worst']:,.0f} | ${r['best']:,.0f} | {r['sharpe']:.2f} |\n")
    lines.append("\n")

    full_pass = [r for r in rows if r['trades_per_day'] >= 300
                 and r['wr'] >= 0.45 and r['per_day'] >= 1000
                 and r['max_dd'] <= 5000]
    lines.append(f"## Strategies meeting ALL hard requirements ({len(full_pass)})\n\n")
    if full_pass:
        for r in full_pass:
            lines.append(
                f"- **{r['name']}** -- {r['n']:,} trades "
                f"({r['trades_per_day']:.1f}/day), WR={r['wr']*100:.1f}%, "
                f"net=${r['net']:,.0f}, ${r['per_day']:,.0f}/day, "
                f"maxDD=${r['max_dd']:,.0f}, Sharpe={r['sharpe']:.2f}\n")
    else:
        lines.append("**NONE**. No strategy meets all hard requirements.\n\n")
        lines.append("### Closest candidates (min-ratio across constraints)\n\n")
        scored = []
        for r in rows:
            if r['n'] < 10:
                continue
            score_vol = r['trades_per_day'] / 300
            score_wr = r['wr'] / 0.45
            score_pnl = r['per_day'] / 1000
            score_dd = 5000 / max(1.0, r['max_dd'])
            score = min(score_vol, score_wr, score_pnl, score_dd)
            # Identify the binding constraint
            binders = {
                'volume': score_vol,
                'WR': score_wr,
                'pnl': score_pnl,
                'DD': score_dd,
            }
            binder = min(binders, key=binders.get)
            scored.append((score, binder, r))
        scored.sort(key=lambda x: -x[0])
        for sc, binder, r in scored[:15]:
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
    print(f"[round4] wrote MD {md_path}", file=sys.stderr)

    print("\n" + "=" * 110)
    print(f"{'Strategy':>30s} {'N':>7s} {'/day':>6s} {'WR%':>5s} "
          f"{'$/day':>8s} {'$/tr':>7s} {'maxDD':>9s} {'worst':>8s} {'sharpe':>6s}")
    print("=" * 110)
    for r in rows[:25]:
        flag = ""
        if r['trades_per_day'] >= 300 and r['wr'] >= 0.45 and r['per_day'] >= 1000:
            flag = " *PASS*"
        elif r['per_day'] >= 1000:
            flag = "  $$"
        print(f"{r['name']:>30s} {r['n']:>7d} {r['trades_per_day']:>6.1f} "
              f"{r['wr']*100:>4.1f}% ${r['per_day']:>+7.0f} "
              f"${r['per_trade']:>+6.2f} ${r['max_dd']:>+8.0f} "
              f"${r['worst']:>+7.0f} {r['sharpe']:>+6.2f}{flag}")
    print(f"\nFULL_PASS strategies: {len(full_pass)}")

    try:
        if os.path.exists(CHECKPOINT_PATH):
            os.remove(CHECKPOINT_PATH)
            print(f"[round4] cleared checkpoint {CHECKPOINT_PATH}",
                  file=sys.stderr)
    except Exception:
        pass


if __name__ == "__main__":
    main()
