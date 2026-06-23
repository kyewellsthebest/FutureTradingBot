"""Round 3 broad strategy search for MNQ intraday bot.

Tests 60+ new strategy variants across 12 avenues that have not been
tried in rounds 1 / 2 / alt-strategies / round2 hold-strategies. Uses
the SAME tick-level bid/ask execution model as
/tmp/sim_honest_battery.py (the proven-honest harness).

EXECUTION MODEL (mirrors live bot exactly):
  - 1 MNQ ($2/pt)
  - LIMIT entry: LONG fills when ASK <= entry_px; SHORT when BID >= entry_px
  - Stop-MARKET exit: LONG fills at stop_px - 0.5pt when bid <= stop_px;
                      SHORT fills at stop_px + 0.5pt when ask >= stop_px
  - LIMIT target exit: LONG fills when BID >= target_px; SHORT when ASK <= target_px
  - 0.5pt entry slip on top of limit (matches sim_honest_battery)
  - $1.91 round-trip cost = $0.74 commission + $1.17 exchange/clearing fees
  - 10s minimum cooldown after exit
  - 600s max hold (timeout exit at midpoint)

DATA: USTECH_full.csv, streaming from offset 7_820_974_790 (last ~60 trading days).

USAGE:
  python3 research/round3_search.py

OUTPUT:
  research/round3_results.md
  research/round3_summary.csv
"""
from __future__ import annotations
import csv
import math
import os
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

PATH = "/home/user/HFTBot/data/tick/ustech/USTECH_full.csv"
START_OFFSET = 7_820_974_790  # ~60 trading days from end of file

# --- Cost model (matches the live bot) ---
COMM_RT = 0.74
EXCH_FEES_RT = 1.17
TOTAL_RT_COST = COMM_RT + EXCH_FEES_RT  # 1.91
MNQ_PER_PT = 2.0
ENTRY_SLIP = 0.5
STOP_SLIP = 0.5
MAX_HOLD_SECS = 600
MIN_TARGET_HOLD = 0  # we honor LIMIT targets immediately

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
    """Generic execution engine. A strategy subclass implements only signal
    generation via `on_bar`, `on_tick_signal`, or `on_impulse`, pushing
    setups into `self.pending`.

    Setups are dicts with: side, entry, stop, target, expires (ts seconds),
    used (bool), key (dedupe).
    """
    __slots__ = (
        "name", "cooldown_s", "max_hold", "pending", "in_trade",
        "completed", "by_day", "last_exit_dt", "n_trades",
        "session_start", "session_end",
    )

    def __init__(self, name, cooldown_s=10, max_hold=MAX_HOLD_SECS,
                 session_start=None, session_end=None):
        """session_start/session_end = (hh,mm) UTC tuples or None.
        If both set, signals only generated within session.
        """
        self.name = name
        self.cooldown_s = cooldown_s
        self.max_hold = max_hold
        self.pending = []
        self.in_trade = None
        self.completed = []
        self.by_day = {}
        self.last_exit_dt = None
        self.n_trades = 0
        self.session_start = session_start  # (hh, mm)
        self.session_end = session_end

    def _in_session(self, hh, mn):
        if self.session_start is None:
            return True
        t = hh * 60 + mn
        s = self.session_start[0] * 60 + self.session_start[1]
        e = self.session_end[0] * 60 + self.session_end[1]
        if s < e:
            return s <= t < e
        else:  # wraps midnight
            return t >= s or t < e

    # Hook methods (override as needed)
    def on_bar_close(self, ts, hh, mn, bar_o, bar_h, bar_l, bar_c, hist):
        """Called at the close of every 1-min bar.
        `hist` is a deque of past closed bars: (o, h, l, c).
        """
        pass

    def on_tick_signal(self, ts, bid, ask, hh, mn):
        """Called every tick. Use to add intra-bar setups (e.g. tick-level
        Z-score, round numbers). Default: do nothing.
        """
        pass

    def add_setup(self, side, entry, stop, target, ts_now, key=None,
                  expires_in=300):
        """Add a setup. key prevents duplicates."""
        if side == "LONG":
            entry = _round_long_entry(entry)
            stop = _round_long_stop(stop)
            target = _round_long_tgt(target)
        else:
            entry = _round_short_entry(entry)
            stop = _round_short_stop(stop)
            target = _round_short_tgt(target)
        if key is not None and any(s['key'] == key and not s['used']
                                   for s in self.pending):
            return
        self.pending.append({
            'side': side, 'entry': entry, 'stop': stop, 'target': target,
            'expires': ts_now + expires_in, 'used': False, 'key': key,
        })

    def on_tick(self, ts, bid, ask, day_counter, hh, mn):
        # Expire stale
        if self.pending:
            self.pending = [s for s in self.pending
                            if s['expires'] >= ts and not s['used']]

        # In-trade exit
        if self.in_trade is not None:
            tr = self.in_trade
            exit_now = None
            if tr['side'] == 'LONG':
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
                pnl_usd = pnl * MNQ_PER_PT - TOTAL_RT_COST
                self.completed.append((pnl_usd, reason, day_counter))
                self.by_day.setdefault(day_counter, []).append(pnl_usd)
                self.last_exit_dt = ts
                self.in_trade = None
                self.n_trades += 1
            return

        # Cooldown
        if self.last_exit_dt is not None:
            if ts - self.last_exit_dt < self.cooldown_s:
                return

        # Session gate (entry only)
        if not self._in_session(hh, mn):
            return

        # Try entry trigger
        for s in self.pending:
            if s['used']:
                continue
            if s['side'] == 'LONG':
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
                'worst': 0.0, 'best': 0.0, 'max_dd': 0.0, 'trades_per_day': 0.0,
                'sharpe': 0.0, 'n_days': 0,
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
        # max DD over per-trade equity curve
        cum = 0.0
        peak = 0.0
        max_dd = 0.0
        for c in self.completed:
            cum += c[0]
            if cum > peak:
                peak = cum
            if peak - cum > max_dd:
                max_dd = peak - cum
        # Sharpe-like = mean(daily) / std(daily) * sqrt(252)
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
# AVENUE 1+9+10: Pullback variants on 1-min bars (with parameter sweep
# of impulse, pullback %, stop, target, invert, session, ATR gate)
# ===========================================================================
class PullbackStrategy(StrategyBase):
    """Generic pullback: detects an N-bar impulse (net move >= IMPULSE_PTS),
    arms an entry at PULL_PCT retracement of impulse high/low.
    If invert=True, fade direction. Else trend with direction.
    Supports ATR gate.
    """
    def __init__(self, name, impulse_pts, impulse_bars, pull_pct,
                 stop_pts, target_pts, invert=True, cooldown_s=10,
                 session_start=None, session_end=None, atr_min=None,
                 atr_max=None, atr_bars=20, max_hold=MAX_HOLD_SECS):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.impulse_pts = impulse_pts
        self.impulse_bars = impulse_bars
        self.pull_pct = pull_pct
        self.stop_pts = stop_pts
        self.target_pts = target_pts
        self.invert = invert
        self.atr_min = atr_min
        self.atr_max = atr_max
        self.atr_bars = atr_bars

    def on_bar_close(self, ts, hh, mn, bar_o, bar_h, bar_l, bar_c, hist):
        # Need impulse_bars + atr_bars history
        nbars = len(hist)
        if nbars < self.impulse_bars:
            return
        # ATR gate
        if self.atr_min is not None or self.atr_max is not None:
            if nbars < self.atr_bars + 1:
                return
            # ATR over last atr_bars
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
        # Impulse: last impulse_bars bars
        win = list(hist)[-self.impulse_bars:]
        # NOTE: hist's most recent entry is the bar that JUST closed
        # win[0][0] is open of bar (impulse_bars) ago; win[-1][3] is close just now
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
        self.add_setup(side, entry, stop, target, ts, key=key, expires_in=300)


# ===========================================================================
# AVENUE 2: Sub-minute structural strategies — uses 15-sec bars.
# Same pullback logic but on 15s bars => much faster signal turnover.
# ===========================================================================
class PullbackSubMinute(PullbackStrategy):
    """Pullback strategy operating on user-defined bar-seconds.
    bar_seconds = 15 / 30 / 5 etc.
    """
    def __init__(self, name, bar_seconds, *args, **kwargs):
        super().__init__(name, *args, **kwargs)
        self.bar_seconds = bar_seconds
        # All bar logic externally driven; the bar builder must pass bars at
        # the specified resolution.


# ===========================================================================
# AVENUE 5: Multi-bar pattern recognition
# ===========================================================================
class EngulfStrategy(StrategyBase):
    """Bullish/bearish engulfing + retest of prior close.
    Bullish: bar[t-1] red, bar[t] green and closes above bar[t-1] high.
    Entry: limit at bar[t] midpoint (retest). Stop bar[t] low. Target ~2x.
    Bearish: mirror.
    """
    def __init__(self, name, stop_pts=8, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None, min_body=2.0):
        super().__init__(name, cooldown_s=cooldown_s,
                         session_start=session_start, session_end=session_end)
        self.stop_pts = stop_pts
        self.target_pts = target_pts
        self.min_body = min_body

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < 2:
            return
        prev_o, prev_h, prev_l, prev_c = hist[-2]
        cur_o, cur_h, cur_l, cur_c = hist[-1]
        body = abs(cur_c - cur_o)
        prev_body = abs(prev_c - prev_o)
        if body < self.min_body:
            return
        # Bullish engulf: prev red, cur green and engulfs
        if prev_c < prev_o and cur_c > cur_o and cur_c > prev_h and body >= prev_body:
            entry = (cur_o + cur_c) / 2.0
            stop = cur_l - 0.5
            target = entry + self.target_pts
            self.add_setup("LONG", entry, stop, target, ts,
                           key=("eng", round(cur_o, 1), "L"), expires_in=180)
        elif prev_c > prev_o and cur_c < cur_o and cur_c < prev_l and body >= prev_body:
            entry = (cur_o + cur_c) / 2.0
            stop = cur_h + 0.5
            target = entry - self.target_pts
            self.add_setup("SHORT", entry, stop, target, ts,
                           key=("eng", round(cur_o, 1), "S"), expires_in=180)


class ThreeBarReversal(StrategyBase):
    """3-bar reversal: bar1 down, bar2 small-range bottom, bar3 up.
    Enter long on close of bar3 with stop below bar2 low.
    """
    def __init__(self, name, stop_pts=6, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None,
                 min_move=3.0, max_mid_range=2.0):
        super().__init__(name, cooldown_s=cooldown_s,
                         session_start=session_start, session_end=session_end)
        self.stop_pts = stop_pts
        self.target_pts = target_pts
        self.min_move = min_move
        self.max_mid_range = max_mid_range

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < 3:
            return
        b1 = hist[-3]
        b2 = hist[-2]
        b3 = hist[-1]
        # bullish 3-bar reversal
        if (b1[3] - b1[0] <= -self.min_move and  # bar1 down move
            abs(b2[3] - b2[0]) < self.max_mid_range and  # bar2 doji-ish
            b3[3] - b3[0] >= self.min_move):  # bar3 up
            # Enter limit at bar3 close - small pullback, stop below bar2 low
            entry = b3[3] - 1.0  # slight pullback retest
            stop = min(b2[2], b3[2]) - 0.5
            target = entry + self.target_pts
            if entry > stop:
                self.add_setup("LONG", entry, stop, target, ts,
                               key=("3br_l", round(b2[0], 1)), expires_in=180)
        # bearish
        if (b1[3] - b1[0] >= self.min_move and
            abs(b2[3] - b2[0]) < self.max_mid_range and
            b3[3] - b3[0] <= -self.min_move):
            entry = b3[3] + 1.0
            stop = max(b2[1], b3[1]) + 0.5
            target = entry - self.target_pts
            if entry < stop:
                self.add_setup("SHORT", entry, stop, target, ts,
                               key=("3br_s", round(b2[0], 1)), expires_in=180)


class InsideBarBreakout(StrategyBase):
    """Inside-bar breakout: bar2 fully inside bar1. Enter on break of bar1 high/low.
    """
    def __init__(self, name, stop_pts=6, target_pts=12, cooldown_s=10,
                 session_start=None, session_end=None):
        super().__init__(name, cooldown_s=cooldown_s,
                         session_start=session_start, session_end=session_end)
        self.stop_pts = stop_pts
        self.target_pts = target_pts

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < 2:
            return
        b1 = hist[-2]
        b2 = hist[-1]
        if b2[1] < b1[1] and b2[2] > b1[2]:  # inside bar
            # LONG breakout — entry at b1.high
            entry_long = b1[1] + 0.25
            stop_long = b2[2] - 0.5
            target_long = entry_long + self.target_pts
            self.add_setup("LONG", entry_long, stop_long, target_long, ts,
                           key=("ib_l", round(b1[1], 1)), expires_in=180)
            # SHORT breakout — entry at b1.low
            entry_short = b1[2] - 0.25
            stop_short = b2[1] + 0.5
            target_short = entry_short - self.target_pts
            self.add_setup("SHORT", entry_short, stop_short, target_short, ts,
                           key=("ib_s", round(b1[2], 1)), expires_in=180)


# ===========================================================================
# AVENUE 6: Round-number psychology
# ===========================================================================
class RoundNumberFade(StrategyBase):
    """When price approaches a round-number level (multiple of N), fade it.
    Detects on every tick — when mid crosses within `proximity` pts of a
    round level after coming from far enough away.
    """
    def __init__(self, name, multiple=25.0, proximity=1.0, stop_pts=5,
                 target_pts=5, cooldown_s=10,
                 session_start=None, session_end=None,
                 require_approach_pts=5.0):
        super().__init__(name, cooldown_s=cooldown_s,
                         session_start=session_start, session_end=session_end)
        self.multiple = multiple
        self.proximity = proximity
        self.stop_pts = stop_pts
        self.target_pts = target_pts
        self.last_signal_level = None
        self.recent_extreme = None  # (extreme_px, dir)
        self.req_approach = require_approach_pts

    def on_tick_signal(self, ts, bid, ask, hh, mn):
        mid = (bid + ask) / 2.0
        # Nearest round level
        rl = round(mid / self.multiple) * self.multiple
        if self.recent_extreme is None:
            self.recent_extreme = (mid, mid)
        lo, hi = self.recent_extreme
        if mid > hi: hi = mid
        if mid < lo: lo = mid
        # decay window: if we're more than 30pts away from recent extreme,
        # reset
        if hi - lo > 60:
            lo = mid
            hi = mid
        self.recent_extreme = (lo, hi)

        # Approach from below: fade short at the level
        if hi - lo >= self.req_approach:
            if abs(mid - rl) <= self.proximity and mid <= rl:
                # short-fade entry at rl + 0.25 (just over the level)
                if self.last_signal_level != ("S", rl):
                    entry = rl
                    stop = rl + self.stop_pts
                    target = rl - self.target_pts
                    self.add_setup("SHORT", entry, stop, target, ts,
                                   key=("rn_s", rl, hh), expires_in=120)
                    self.last_signal_level = ("S", rl)
            elif abs(mid - rl) <= self.proximity and mid >= rl:
                if self.last_signal_level != ("L", rl):
                    entry = rl
                    stop = rl - self.stop_pts
                    target = rl + self.target_pts
                    self.add_setup("LONG", entry, stop, target, ts,
                                   key=("rn_l", rl, hh), expires_in=120)
                    self.last_signal_level = ("L", rl)


# ===========================================================================
# AVENUE 7: Z-score mean reversion vs N-bar VWAP
# ===========================================================================
class ZScoreReversion(StrategyBase):
    """When mid deviates > z_threshold standard deviations from rolling
    20-bar mean, fade back to mean.
    """
    def __init__(self, name, lookback_bars=20, z_threshold=2.0,
                 stop_pts=8, target_pts=8, cooldown_s=10,
                 session_start=None, session_end=None):
        super().__init__(name, cooldown_s=cooldown_s,
                         session_start=session_start, session_end=session_end)
        self.lookback_bars = lookback_bars
        self.z_threshold = z_threshold
        self.stop_pts = stop_pts
        self.target_pts = target_pts

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.lookback_bars:
            return
        closes = [hist[i][3] for i in range(len(hist) - self.lookback_bars, len(hist))]
        mean = sum(closes) / self.lookback_bars
        var = sum((c - mean) ** 2 for c in closes) / self.lookback_bars
        std = math.sqrt(var)
        if std < 0.5:
            return
        z = (bc - mean) / std
        if z >= self.z_threshold:
            entry = bc  # short at current
            stop = bc + self.stop_pts
            target = mean
            if target < entry - 1:  # at least 1pt of profit
                self.add_setup("SHORT", entry, stop, target, ts,
                               key=("z_s", round(bc, 1)), expires_in=120)
        elif z <= -self.z_threshold:
            entry = bc
            stop = bc - self.stop_pts
            target = mean
            if target > entry + 1:
                self.add_setup("LONG", entry, stop, target, ts,
                               key=("z_l", round(bc, 1)), expires_in=120)


# ===========================================================================
# AVENUE 8: Tick velocity (price moved X pts in Y seconds -> fade or follow)
# ===========================================================================
class TickVelocityFade(StrategyBase):
    """Fade when mid moves >= move_pts in window_secs seconds."""
    def __init__(self, name, move_pts=4.0, window_secs=10, stop_pts=6,
                 target_pts=4, cooldown_s=10,
                 session_start=None, session_end=None, follow=False):
        super().__init__(name, cooldown_s=cooldown_s,
                         session_start=session_start, session_end=session_end)
        self.move_pts = move_pts
        self.window_secs = window_secs
        self.stop_pts = stop_pts
        self.target_pts = target_pts
        self.follow = follow
        self.history = deque(maxlen=2000)  # (ts, mid)

    def on_tick_signal(self, ts, bid, ask, hh, mn):
        mid = (bid + ask) / 2.0
        self.history.append((ts, mid))
        # Find the oldest tick within window_secs
        cutoff = ts - self.window_secs
        # Pop old
        while self.history and self.history[0][0] < cutoff:
            self.history.popleft()
        if len(self.history) < 5:
            return
        old_mid = self.history[0][1]
        delta = mid - old_mid
        if delta >= self.move_pts:
            # Fast up move
            if self.follow:
                # follow: small pullback long
                entry = mid - 0.5
                stop = entry - self.stop_pts
                target = entry + self.target_pts
                self.add_setup("LONG", entry, stop, target, ts,
                               key=("tvf_lf", round(mid, 0), hh, mn // 5),
                               expires_in=60)
            else:
                # fade short
                entry = mid
                stop = mid + self.stop_pts
                target = mid - self.target_pts
                self.add_setup("SHORT", entry, stop, target, ts,
                               key=("tvf_s", round(mid, 0), hh, mn // 5),
                               expires_in=60)
        elif delta <= -self.move_pts:
            if self.follow:
                entry = mid + 0.5
                stop = entry + self.stop_pts
                target = entry - self.target_pts
                self.add_setup("SHORT", entry, stop, target, ts,
                               key=("tvf_sf", round(mid, 0), hh, mn // 5),
                               expires_in=60)
            else:
                entry = mid
                stop = mid - self.stop_pts
                target = mid + self.target_pts
                self.add_setup("LONG", entry, stop, target, ts,
                               key=("tvf_l", round(mid, 0), hh, mn // 5),
                               expires_in=60)


# ===========================================================================
# AVENUE 12: Order-flow proxy via tick imbalance.
# Track count of up-ticks vs down-ticks over rolling window. Imbalance -> fade.
# ===========================================================================
class TickImbalanceFade(StrategyBase):
    """Count up-ticks (last > prev_last) vs down-ticks over rolling N-tick window.
    When imbalance ratio is extreme, fade the direction.
    """
    def __init__(self, name, window=200, threshold=0.75, stop_pts=5,
                 target_pts=4, cooldown_s=10,
                 session_start=None, session_end=None):
        super().__init__(name, cooldown_s=cooldown_s,
                         session_start=session_start, session_end=session_end)
        self.window = window
        self.threshold = threshold
        self.stop_pts = stop_pts
        self.target_pts = target_pts
        self.ticks = deque(maxlen=window)  # +1 / -1 / 0
        self.last_mid = None
        self.last_signal_at = None

    def on_tick_signal(self, ts, bid, ask, hh, mn):
        mid = (bid + ask) / 2.0
        if self.last_mid is not None:
            if mid > self.last_mid:
                self.ticks.append(1)
            elif mid < self.last_mid:
                self.ticks.append(-1)
            else:
                self.ticks.append(0)
        self.last_mid = mid
        if len(self.ticks) < self.window:
            return
        # Don't spam signals — rate-limit
        if self.last_signal_at is not None and ts - self.last_signal_at < 30:
            return
        ups = sum(1 for t in self.ticks if t > 0)
        downs = sum(1 for t in self.ticks if t < 0)
        tot = ups + downs
        if tot < 50:
            return
        up_ratio = ups / tot
        if up_ratio >= self.threshold:
            # Heavy buying — fade short
            entry = mid
            stop = mid + self.stop_pts
            target = mid - self.target_pts
            self.add_setup("SHORT", entry, stop, target, ts,
                           key=("tib_s", round(mid, 0), hh, mn),
                           expires_in=60)
            self.last_signal_at = ts
        elif up_ratio <= 1 - self.threshold:
            entry = mid
            stop = mid - self.stop_pts
            target = mid + self.target_pts
            self.add_setup("LONG", entry, stop, target, ts,
                           key=("tib_l", round(mid, 0), hh, mn),
                           expires_in=60)
            self.last_signal_at = ts


# ===========================================================================
# Bar builders — 1-min and N-second
# ===========================================================================
class BarBuilder:
    """Builds bars on a configurable granularity (in seconds).
    For 1-min bars, granularity=60. For 15-sec, granularity=15.
    """
    __slots__ = ("granularity", "cur_bucket", "cur_bar", "history", "max_history")

    def __init__(self, granularity_secs=60, max_history=300):
        self.granularity = granularity_secs
        self.cur_bucket = None
        self.cur_bar = None  # [o, h, l, c]
        self.history = deque(maxlen=max_history)  # (o, h, l, c)
        self.max_history = max_history

    def on_tick(self, ts, last):
        """Returns True if a bar just closed."""
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
        # Bar closed
        self.history.append(tuple(self.cur_bar))
        self.cur_bucket = bucket
        self.cur_bar = [last, last, last, last]
        return True

    def closed_bar(self):
        """Return the most recent CLOSED bar (o,h,l,c)."""
        if not self.history:
            return None
        return self.history[-1]


# ===========================================================================
# Build the variant list — 60+ strategies across 12 avenues
# ===========================================================================
def build_variants():
    variants_1m = []   # need 1-min bars
    variants_subm = {}  # bar_secs -> list of (strategy, on_bar_close handler) -- handled via sub-min builders
    variants_tick = []   # need only ticks
    variants_1m_strategies = []

    # ====== CANONICAL sanity check variant (proven baseline from sim_honest_battery) ======
    variants_1m_strategies.append(PullbackStrategy(
        "CANON_INV_236_s10t20",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True))

    # ====== AVENUE 9: Wide INVERSE pullback parameter sweep ======
    # 9 strategies sweeping IMPULSE_PTS, STOP, TARGET, PULL_PCT
    for impulse_pts in [3.0, 5.0, 7.0]:
        for stop, tgt in [(5, 10), (8, 16), (10, 20), (12, 24)]:
            v = PullbackStrategy(
                f"INV_imp{impulse_pts:.0f}_s{stop}t{tgt}",
                impulse_pts=impulse_pts, impulse_bars=4,
                pull_pct=0.236, stop_pts=stop, target_pts=tgt, invert=True)
            variants_1m_strategies.append(v)
    # Tighter 1:1 RR
    for imp in [3.0, 5.0]:
        for s in [5, 8, 10]:
            v = PullbackStrategy(
                f"INV_imp{imp:.0f}_s{s}t{s}_RR1",
                impulse_pts=imp, impulse_bars=4, pull_pct=0.236,
                stop_pts=s, target_pts=s, invert=True)
            variants_1m_strategies.append(v)
    # Wider PULL_PCT sweep
    for pp in [0.382, 0.5, 0.618]:
        v = PullbackStrategy(
            f"INV_pp{int(pp*1000)}_s10t20",
            impulse_pts=5.0, impulse_bars=4, pull_pct=pp,
            stop_pts=10, target_pts=20, invert=True)
        variants_1m_strategies.append(v)
    # Impulse-bars sweep
    for ib in [2, 3, 6, 8]:
        v = PullbackStrategy(
            f"INV_ib{ib}_s10t20",
            impulse_pts=5.0, impulse_bars=ib, pull_pct=0.236,
            stop_pts=10, target_pts=20, invert=True)
        variants_1m_strategies.append(v)

    # ====== AVENUE 10: NON-inverted pullback (trend-follow direction) ======
    for pp in [0.236, 0.382, 0.5]:
        for stop, tgt in [(5, 10), (8, 16), (10, 20)]:
            v = PullbackStrategy(
                f"ORIG_pp{int(pp*1000)}_s{stop}t{tgt}",
                impulse_pts=5.0, impulse_bars=4, pull_pct=pp,
                stop_pts=stop, target_pts=tgt, invert=False)
            variants_1m_strategies.append(v)

    # ====== AVENUE 3: Time-window-restricted ======
    # US RTH only (13:30-20:00 UTC)
    v = PullbackStrategy(
        "INV_236_s10t20_RTH",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True,
        session_start=(13, 30), session_end=(20, 0))
    variants_1m_strategies.append(v)
    # CME-open (22-01 UTC) only
    v = PullbackStrategy(
        "INV_236_s10t20_CMEOPEN",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True,
        session_start=(22, 0), session_end=(1, 0))
    variants_1m_strategies.append(v)
    # Lunch fade (16-18 UTC)
    v = PullbackStrategy(
        "INV_236_s5t5_LUNCH",
        impulse_pts=3.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=5, target_pts=5, invert=True,
        session_start=(16, 0), session_end=(18, 0))
    variants_1m_strategies.append(v)
    # London-NY overlap
    v = PullbackStrategy(
        "INV_236_s10t20_LDNNY",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True,
        session_start=(13, 0), session_end=(16, 0))
    variants_1m_strategies.append(v)

    # ====== AVENUE 4: Volatility-gated existing pullback ======
    for atr_min in [3.0, 5.0, 8.0]:
        v = PullbackStrategy(
            f"INV_236_s10t20_atrmin{atr_min:.0f}",
            impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
            stop_pts=10, target_pts=20, invert=True,
            atr_min=atr_min)
        variants_1m_strategies.append(v)
    # ATR-MAX (only quiet markets)
    for atr_max in [2.0, 3.0]:
        v = PullbackStrategy(
            f"INV_236_s5t5_atrmax{atr_max:.0f}",
            impulse_pts=3.0, impulse_bars=4, pull_pct=0.236,
            stop_pts=5, target_pts=5, invert=True,
            atr_max=atr_max)
        variants_1m_strategies.append(v)

    # ====== AVENUE 11: Combined filters (top promising combos) ======
    v = PullbackStrategy(
        "INV_236_s8t16_RTH_atr5",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=8, target_pts=16, invert=True,
        session_start=(13, 30), session_end=(20, 0), atr_min=5.0)
    variants_1m_strategies.append(v)
    v = PullbackStrategy(
        "INV_236_s5t10_RTH",
        impulse_pts=3.0, impulse_bars=3, pull_pct=0.236,
        stop_pts=5, target_pts=10, invert=True,
        session_start=(13, 30), session_end=(20, 0))
    variants_1m_strategies.append(v)
    v = PullbackStrategy(
        "INV_236_s5t5_RTH_fast",
        impulse_pts=3.0, impulse_bars=3, pull_pct=0.236,
        stop_pts=5, target_pts=5, invert=True,
        session_start=(13, 30), session_end=(20, 0))
    variants_1m_strategies.append(v)

    # ====== AVENUE 5: Multi-bar pattern recognition ======
    variants_1m_strategies.append(
        EngulfStrategy("ENG_s8t12", stop_pts=8, target_pts=12))
    variants_1m_strategies.append(
        EngulfStrategy("ENG_s5t10_RTH", stop_pts=5, target_pts=10,
                       session_start=(13, 30), session_end=(20, 0)))
    variants_1m_strategies.append(
        ThreeBarReversal("3BR_s6t12"))
    variants_1m_strategies.append(
        ThreeBarReversal("3BR_s4t8_RTH", stop_pts=4, target_pts=8,
                         session_start=(13, 30), session_end=(20, 0)))
    variants_1m_strategies.append(
        InsideBarBreakout("IBBO_s6t12"))
    variants_1m_strategies.append(
        InsideBarBreakout("IBBO_s4t8_RTH", stop_pts=4, target_pts=8,
                          session_start=(13, 30), session_end=(20, 0)))

    # ====== AVENUE 7: Z-score mean reversion ======
    variants_1m_strategies.append(
        ZScoreReversion("Z20_th2_s8t8"))
    variants_1m_strategies.append(
        ZScoreReversion("Z20_th1.5_s8t8", z_threshold=1.5))
    variants_1m_strategies.append(
        ZScoreReversion("Z20_th2.5_s10t10", z_threshold=2.5,
                        stop_pts=10, target_pts=10))
    variants_1m_strategies.append(
        ZScoreReversion("Z10_th2_s5t5", lookback_bars=10, z_threshold=2.0,
                        stop_pts=5, target_pts=5))

    # ====== AVENUE 2: Sub-minute structural pullback (15s and 30s bars) ======
    sub_strategies_15s = []
    sub_strategies_30s = []
    for stop, tgt in [(3, 3), (4, 4), (5, 5), (3, 6)]:
        sub_strategies_15s.append(
            PullbackStrategy(
                f"INV15s_imp2_s{stop}t{tgt}",
                impulse_pts=2.0, impulse_bars=4, pull_pct=0.236,
                stop_pts=stop, target_pts=tgt, invert=True,
                max_hold=120))
    for stop, tgt in [(4, 4), (5, 5), (6, 6), (5, 10)]:
        sub_strategies_30s.append(
            PullbackStrategy(
                f"INV30s_imp3_s{stop}t{tgt}",
                impulse_pts=3.0, impulse_bars=4, pull_pct=0.236,
                stop_pts=stop, target_pts=tgt, invert=True,
                max_hold=180))

    # ====== AVENUE 6: Round-number psychology ======
    variants_tick.append(
        RoundNumberFade("RN_25_s5t5", multiple=25.0, stop_pts=5, target_pts=5))
    variants_tick.append(
        RoundNumberFade("RN_50_s8t8", multiple=50.0, stop_pts=8, target_pts=8))
    variants_tick.append(
        RoundNumberFade("RN_100_s10t10", multiple=100.0, stop_pts=10, target_pts=10))
    variants_tick.append(
        RoundNumberFade("RN_25_s3t3_RTH", multiple=25.0, stop_pts=3, target_pts=3,
                        session_start=(13, 30), session_end=(20, 0)))
    variants_tick.append(
        RoundNumberFade("RN_10_s3t3", multiple=10.0, stop_pts=3, target_pts=3,
                        proximity=0.5, require_approach_pts=3.0))

    # ====== AVENUE 8: Tick velocity ======
    variants_tick.append(
        TickVelocityFade("TV_3pt_10s_s5t3", move_pts=3.0, window_secs=10,
                         stop_pts=5, target_pts=3, follow=False))
    variants_tick.append(
        TickVelocityFade("TV_5pt_15s_s7t5", move_pts=5.0, window_secs=15,
                         stop_pts=7, target_pts=5, follow=False))
    variants_tick.append(
        TickVelocityFade("TV_3pt_5s_s4t3", move_pts=3.0, window_secs=5,
                         stop_pts=4, target_pts=3, follow=False))
    variants_tick.append(
        TickVelocityFade("TV_5pt_10s_FOLLOW_s4t6", move_pts=5.0, window_secs=10,
                         stop_pts=4, target_pts=6, follow=True))
    variants_tick.append(
        TickVelocityFade("TV_3pt_5s_RTH_s4t3", move_pts=3.0, window_secs=5,
                         stop_pts=4, target_pts=3, follow=False,
                         session_start=(13, 30), session_end=(20, 0)))

    # ====== AVENUE 12: Order-flow tick imbalance ======
    variants_tick.append(
        TickImbalanceFade("TIB_w200_th75_s5t4", window=200, threshold=0.75,
                          stop_pts=5, target_pts=4))
    variants_tick.append(
        TickImbalanceFade("TIB_w500_th70_s6t5", window=500, threshold=0.70,
                          stop_pts=6, target_pts=5))
    variants_tick.append(
        TickImbalanceFade("TIB_w100_th80_s4t3", window=100, threshold=0.80,
                          stop_pts=4, target_pts=3))
    variants_tick.append(
        TickImbalanceFade("TIB_w200_th75_RTH_s4t3", window=200, threshold=0.75,
                          stop_pts=4, target_pts=3,
                          session_start=(13, 30), session_end=(20, 0)))

    return variants_1m_strategies, sub_strategies_15s, sub_strategies_30s, variants_tick


# ===========================================================================
# Main streaming loop
# ===========================================================================
def main():
    v1m, v15s, v30s, vtick = build_variants()
    all_strats = v1m + v15s + v30s + vtick
    print(f"\n[round3] Built {len(all_strats)} strategies: "
          f"{len(v1m)} 1m + {len(v15s)} 15s + {len(v30s)} 30s + {len(vtick)} tick",
          file=sys.stderr)

    bb_1m = BarBuilder(granularity_secs=60, max_history=300)
    bb_15s = BarBuilder(granularity_secs=15, max_history=200)
    bb_30s = BarBuilder(granularity_secs=30, max_history=200)

    n_lines = 0
    n_ticks_processed = 0
    day_counter = -1
    last_day_key = None
    t_start = time.time()
    last_progress_t = t_start
    last_progress_ticks = 0

    file_size = os.path.getsize(PATH)
    print(f"[round3] file size: {file_size:,} bytes, start offset {START_OFFSET:,}",
          file=sys.stderr)

    with open(PATH, "rb") as f:
        f.seek(START_OFFSET)
        # Read text
        f.readline()  # discard partial line
        for raw in f:
            n_lines += 1
            if n_lines % 5_000_000 == 0:
                now = time.time()
                rate = (n_lines - last_progress_ticks) / max(0.001, now - last_progress_t)
                last_progress_t = now
                last_progress_ticks = n_lines
                pos = f.tell()
                rem_bytes = file_size - pos
                eta = rem_bytes / max(rate * 60, 1)  # rough
                # Find a good-performing variant for live report
                if all_strats:
                    top_n = max((s.n_trades, s.name) for s in all_strats)
                else:
                    top_n = (0, "?")
                print(f"  [round3] {n_lines/1e6:.1f}M ticks "
                      f"rate={rate/1e6:.2f}M/s elapsed={(now-t_start)/60:.1f}m "
                      f"day={day_counter} most_trades={top_n[1]}({top_n[0]})",
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

            # Update 1-min bar; if a bar just closed, fire bar-close events
            if bb_1m.on_tick(ts, last):
                closed = bb_1m.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    for s in v1m:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_1m.history)
            # 15s bar update
            if v15s:
                if bb_15s.on_tick(ts, last):
                    closed = bb_15s.closed_bar()
                    if closed is not None:
                        o, h, l, c = closed
                        for s in v15s:
                            s.on_bar_close(ts, hh, mn, o, h, l, c, bb_15s.history)
            # 30s bar update
            if v30s:
                if bb_30s.on_tick(ts, last):
                    closed = bb_30s.closed_bar()
                    if closed is not None:
                        o, h, l, c = closed
                        for s in v30s:
                            s.on_bar_close(ts, hh, mn, o, h, l, c, bb_30s.history)

            # Tick-level signal hooks (only for tick variants)
            for s in vtick:
                s.on_tick_signal(ts, bid, ask, hh, mn)

            # Feed every strategy's exit/entry logic on this tick
            for s in all_strats:
                s.on_tick(ts, bid, ask, day_counter, hh, mn)

            n_ticks_processed += 1

    elapsed = time.time() - t_start
    total_days = day_counter + 1
    print(f"\n[round3] DONE in {elapsed/60:.1f}min, {n_lines:,} ticks, "
          f"{total_days} day buckets", file=sys.stderr)

    # ====== Report ======
    rows = []
    for s in all_strats:
        r = s.report(total_days)
        rows.append(r)
    rows.sort(key=lambda r: -r['per_day'])

    # CSV
    csv_path = "/home/user/HFTBot/research/round3_summary.csv"
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
    print(f"[round3] wrote CSV {csv_path}", file=sys.stderr)

    # MD report
    md_path = "/home/user/HFTBot/research/round3_results.md"
    lines = []
    lines.append("# Round 3 broad strategy search results\n")
    lines.append(f"Generated: {datetime.now().isoformat()}\n")
    lines.append(f"Period: 60-day window starting at file offset {START_OFFSET:,}, "
                 f"{total_days} calendar-day buckets in stream.\n")
    lines.append(f"Tick stream: {n_lines:,} lines processed\n")
    lines.append(f"Costs applied: ${TOTAL_RT_COST:.2f}/RT "
                 f"(${COMM_RT:.2f} commission + ${EXCH_FEES_RT:.2f} fees), "
                 f"{STOP_SLIP}pt stop slip, {ENTRY_SLIP}pt entry slip\n\n")
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

    # Hard-requirements pass
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
        lines.append("### Closest candidates (within 50% of each criterion)\n\n")
        close = []
        for r in rows:
            score_vol = r['trades_per_day'] / 300
            score_wr = r['wr'] / 0.45
            score_pnl = r['per_day'] / 1000
            score_dd = 5000 / max(1.0, r['max_dd'])
            # weighted combined
            score = min(score_vol, score_wr, score_pnl, score_dd)
            if score >= 0.5:
                close.append((score, r))
        close.sort(key=lambda x: -x[0])
        if close:
            for sc, r in close[:10]:
                lines.append(
                    f"- **{r['name']}** -- min-criterion-ratio {sc:.2f}, "
                    f"{r['trades_per_day']:.1f} tr/d, WR={r['wr']*100:.1f}%, "
                    f"${r['per_day']:,.0f}/day, DD=${r['max_dd']:,.0f}\n")
        else:
            lines.append("**No strategy within 50% of all criteria.**\n")

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
    print(f"[round3] wrote MD {md_path}", file=sys.stderr)

    # Stdout summary
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


if __name__ == "__main__":
    main()
