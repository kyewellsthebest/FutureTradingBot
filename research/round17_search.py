#!/usr/bin/env python3
"""Round 17 — six FRESH angles, bot-faithful (r9 executor).

Mission: after 16 rounds and 10K+ measured variants, no FULL_PASS under
honest r9 execution. Round 17 explores six avenues per the brief:

  A. MICRO-SCALP — 0.5..2pt targets, ultra-tight scalping with 'marketable'
     entries (~150 variants). Bet: massive volume × tiny edge × bypass queue.
  B. NEWS-WINDOW — only trade during 15-min high-impact windows, follow first
     30s direction with wide R/R (~80 variants).
  C. ENSEMBLE VOTING — fire only when k-of-6 signals align same direction
     (~80 variants). Expect: few trades, very high WR.
  D. VOL-SCALED R:R — stop and target scale with current ATR (~80 variants).
  E. ADAPTIVE WR GATE — track rolling N-trade WR, only fire next trade if
     recent WR >= threshold (~80 variants). "Stop on losing streak."
  F. EXIT-TIME OPTIMIZATION — fixed exit at N seconds, fade impulse (~80).

All strategies emit add_setup() with fill_mode set; r9 executor handles
fills, exits, cooldown, slippage, max-hold. NO custom queue logic — the
round-14 mistake is not repeated.

CANON baseline included for sanity (must match r16: ~108 tr/d, 37% WR,
~-$248/day).

Output:
  /home/user/HFTBot/research/round17_results.md
  /home/user/HFTBot/research/round17_summary.csv
"""
from __future__ import annotations
import os, sys, time, math, pickle, csv
from collections import deque, defaultdict

sys.path.insert(0, "/home/user/HFTBot")
sys.path.insert(0, "/home/user/HFTBot/research")

# Env defaults (mirror r16)
os.environ.setdefault("STRAT_INVERT", "1")
os.environ.setdefault("STRAT_PULL_PCT", "0.236")
os.environ.setdefault("STRAT_STOP_PTS", "10.0")
os.environ.setdefault("STRAT_TARGET_PTS", "20.0")
os.environ.setdefault("STRAT_IMPULSE_PTS", "5.0")
os.environ.setdefault("STRAT_IMPULSE_BARS", "4")
os.environ.setdefault("STRAT_COOLDOWN_SECS", "10")
os.environ.setdefault("BOT_HTF_TREND_FILTER", "0")

from research import round4_search as r4
from research import round6_search as r6
from research import round7_search as r7
from research import round8_search as r8
from research import round9_search as r9

StrategyBase = r4.StrategyBase
PullbackStrategy = r4.PullbackStrategy
MarketablePullback = r6.MarketablePullback
BreakoutStrategy = r6.BreakoutStrategy
BarBuilder = r4.BarBuilder
MARKET = r8.MARKET
attach_r7_executor = r7.attach_r7_executor

MNQ_PER_PT = 2.0
FEE_FULL_RT = 1.91
MAX_HOLD_S = r7.MAX_HOLD_S

PATH = "/home/user/HFTBot/data/tick/ustech/USTECH_full.csv"
OFFSET = 7_820_974_790
MAX_DAYS = 60
CHECKPOINT_EVERY_TICKS = 25_000
CHECKPOINT_PATH = "/home/user/HFTBot/research/round17_checkpoint.pkl"
RESULTS_PATH = "/home/user/HFTBot/research/round17_results.md"
SUMMARY_CSV = "/home/user/HFTBot/research/round17_summary.csv"


# ============================================================================
# Custom strategy classes — ALL use add_setup(extra={'fill_mode': ...})
# so r9.r9_bot_on_tick handles execution verbatim. No queue logic.
# ============================================================================


class MicroScalp(StrategyBase):
    """Avenue A. Ultra-tight scalp. On each new tick, watch a short rolling
    window of last-prices. If price ticked up `k_up` times in a row, place a
    marketable SHORT (fade) with very tight stop and target. Equivalently
    `k_dn` ticks down → marketable LONG.

    Uses fill_mode='marketable'. Sub-second cooldown via cool_setup_s.
    """
    def __init__(self, name, k_ticks=3, mode='fade',
                 stop_pts=1.0, target_pts=1.0,
                 max_hold=60, expires=4, cooldown_s=2,
                 cool_setup_s=1.0,
                 session_start=None, session_end=None,
                 min_move_pts=0.0):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start,
                         session_end=session_end)
        self.k_ticks = k_ticks
        self.mode = mode  # 'fade' or 'follow'
        self.stop_pts = stop_pts
        self.target_pts = target_pts
        self.expires = expires
        self.cool_setup_s = cool_setup_s
        self.min_move_pts = min_move_pts
        self._last_n = deque(maxlen=k_ticks + 2)
        self._last_setup_ts = None

    def feed_tick(self, ts, last):
        self._last_n.append(last)
        if len(self._last_n) < self.k_ticks + 1:
            return
        # Need at least 1 of in_session to gate? Executor checks too. Just emit.
        if self._last_setup_ts is not None and ts - self._last_setup_ts < self.cool_setup_s:
            return
        # Count direction in last k ticks
        seq = list(self._last_n)[-(self.k_ticks + 1):]
        ups = sum(1 for i in range(1, len(seq)) if seq[i] > seq[i - 1])
        dns = sum(1 for i in range(1, len(seq)) if seq[i] < seq[i - 1])
        net = seq[-1] - seq[0]
        if self.min_move_pts > 0 and abs(net) < self.min_move_pts:
            return
        side = None
        if ups >= self.k_ticks:
            side = "SHORT" if self.mode == 'fade' else "LONG"
        elif dns >= self.k_ticks:
            side = "LONG" if self.mode == 'fade' else "SHORT"
        if side is None:
            return
        entry = last
        extra = {
            'fill_mode': 'marketable',
            'stop_offset_pts': self.stop_pts,
            'target_offset_pts': self.target_pts,
            'exit_mode': 'stop_market',
        }
        if side == "LONG":
            stop = entry - self.stop_pts
            tgt = entry + self.target_pts
        else:
            stop = entry + self.stop_pts
            tgt = entry - self.target_pts
        self.add_setup(side, side, entry, stop, tgt, ts,
                       key=("ms", round(entry, 1), side, int(ts * 10) % 10000),
                       expires_in=self.expires, extra=extra)
        self._last_setup_ts = ts


class NewsWindow(StrategyBase):
    """Avenue B. Only trade within fixed 15-min windows. Within window, watch
    for the first 30s of price action; if a directional impulse forms
    (|net| >= trig_pts), place a marketable continuation order.

    Windows are checked using the session start/end mechanism (StrategyBase
    _in_session). Then within-session, we use _last_n / first_30s logic.
    """
    def __init__(self, name, win_start, win_end,
                 trig_pts=3.0, stop_pts=8.0, target_pts=40.0,
                 mode='follow', max_hold=600, expires=10, cooldown_s=10,
                 cool_setup_s=60.0):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=win_start, session_end=win_end)
        self.trig_pts = trig_pts
        self.stop_pts = stop_pts
        self.target_pts = target_pts
        self.mode = mode  # 'follow' or 'fade'
        self.expires = expires
        self.cool_setup_s = cool_setup_s
        self._window_t0 = None
        self._window_p0 = None
        self._last_in_session = False
        self._last_setup_ts = None
        self._win_start = win_start

    def _on_window_entry(self, ts, last):
        self._window_t0 = ts
        self._window_p0 = last

    def feed_tick(self, ts, last):
        # Detect window entry via current minute matching win_start.
        # Note: we use the cooldown_s and cool_setup_s to avoid spam.
        # Simplification: track time-since-window-start using ts modulo day.
        # Use ts day-second to know hh:mm.
        ts_sec_in_day = ts % 86400
        win_start_sec = self._win_start[0] * 3600 + self._win_start[1] * 60
        # Are we within first 30s of window?
        d_sec = (ts_sec_in_day - win_start_sec) % 86400
        if d_sec > 900:  # beyond 15-min window — gating handled by _in_session
            return
        # First 30s: just record price
        if d_sec <= 30:
            if self._window_t0 is None or d_sec < 1.0:
                # New window — capture first price
                self._window_t0 = ts
                self._window_p0 = last
            return
        # After first 30s: check impulse
        if self._window_p0 is None:
            return
        if self._last_setup_ts is not None and ts - self._last_setup_ts < self.cool_setup_s:
            return
        net = last - self._window_p0
        if abs(net) < self.trig_pts:
            return
        if net > 0:
            side = "LONG" if self.mode == 'follow' else "SHORT"
        else:
            side = "SHORT" if self.mode == 'follow' else "LONG"
        entry = last
        extra = {
            'fill_mode': 'marketable',
            'stop_offset_pts': self.stop_pts,
            'target_offset_pts': self.target_pts,
            'exit_mode': 'stop_market',
        }
        if side == "LONG":
            stop = entry - self.stop_pts
            tgt = entry + self.target_pts
        else:
            stop = entry + self.stop_pts
            tgt = entry - self.target_pts
        self.add_setup(side, side, entry, stop, tgt, ts,
                       key=("nw", round(entry, 1), side, int(ts) % 86400),
                       expires_in=self.expires, extra=extra)
        self._last_setup_ts = ts


class EnsembleVoting(StrategyBase):
    """Avenue C. On each 1m bar close, evaluate 6 binary signals; fire only
    when >= vote_thresh of them point the same direction.

    Signals:
      1. Pullback: recent impulse + retrace to pull_pct
      2. RSI extreme: RSI(14) > 70 (SHORT signal) / < 30 (LONG signal)
      3. Bollinger touch: last close near band edge
      4. VWAP deviation: dist_from_vwap > vwap_thresh * ATR
      5. Stop-cluster proximity: recent swing point within proximity
      6. Volume burst: ticks-per-sec > 2 * baseline
    """
    def __init__(self, name, vote_thresh=3, mode='follow',
                 stop_pts=8, target_pts=24,
                 pull_pct=0.236, impulse_pts=5.0, impulse_bars=4,
                 rsi_n=14, rsi_hi=70, rsi_lo=30,
                 bb_n=20, bb_k=2.0,
                 vwap_atr_mult=1.0,
                 swing_lookback=20, swing_proximity=3.0,
                 vel_burst_mult=2.0,
                 max_hold=MAX_HOLD_S, expires=180, cooldown_s=10,
                 session_start=None, session_end=None):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start,
                         session_end=session_end)
        self.vote_thresh = vote_thresh
        self.mode = mode  # 'follow' or 'fade'
        self.stop_pts = stop_pts
        self.target_pts = target_pts
        self.pull_pct = pull_pct
        self.impulse_pts = impulse_pts
        self.impulse_bars = impulse_bars
        self.rsi_n = rsi_n
        self.rsi_hi = rsi_hi
        self.rsi_lo = rsi_lo
        self.bb_n = bb_n
        self.bb_k = bb_k
        self.vwap_atr_mult = vwap_atr_mult
        self.swing_lookback = swing_lookback
        self.swing_proximity = swing_proximity
        self.vel_burst_mult = vel_burst_mult
        self.expires = expires
        self._tick_rate_hist = deque(maxlen=50)

    def feed_tick(self, ts, last):
        # Track tick rate baseline (no-op signaling; we rely on MARKET vel)
        pass

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < max(self.bb_n, self.rsi_n, self.impulse_bars, self.swing_lookback) + 2:
            return
        closes = [b[3] for b in hist]
        # Signal 1: Pullback impulse
        sig1 = 0
        win = list(hist)[-self.impulse_bars:]
        net = win[-1][3] - win[0][0]
        if abs(net) >= self.impulse_pts:
            sig1 = 1 if net > 0 else -1
        # Signal 2: RSI extreme
        sig2 = 0
        gains = 0.0; losses = 0.0
        for i in range(len(closes) - self.rsi_n, len(closes)):
            d = closes[i] - closes[i - 1]
            if d > 0:
                gains += d
            else:
                losses -= d
        rs = gains / losses if losses > 0 else 999
        rsi = 100 - 100 / (1 + rs)
        if rsi >= self.rsi_hi:
            sig2 = -1  # overbought → short
        elif rsi <= self.rsi_lo:
            sig2 = 1   # oversold → long
        # Signal 3: Bollinger touch
        sub = closes[-self.bb_n:]
        mean = sum(sub) / len(sub)
        var = sum((x - mean) ** 2 for x in sub) / len(sub)
        std = math.sqrt(var)
        upper = mean + self.bb_k * std
        lower = mean - self.bb_k * std
        sig3 = 0
        if bc >= upper:
            sig3 = -1
        elif bc <= lower:
            sig3 = 1
        # Signal 4: VWAP deviation
        sig4 = 0
        atr = MARKET.atr() or 1.0
        d_vwap = MARKET.dist_from_vwap()
        thresh = self.vwap_atr_mult * atr
        if d_vwap >= thresh:
            sig4 = -1
        elif d_vwap <= -thresh:
            sig4 = 1
        # Signal 5: Stop-cluster proximity (recent swing high/low)
        sig5 = 0
        recent = list(hist)[-self.swing_lookback:]
        swing_hi = max(b[1] for b in recent)
        swing_lo = min(b[2] for b in recent)
        if abs(bc - swing_hi) <= self.swing_proximity:
            sig5 = -1  # near resistance → short
        elif abs(bc - swing_lo) <= self.swing_proximity:
            sig5 = 1   # near support → long
        # Signal 6: Volume burst (tick velocity)
        sig6 = 0
        vel_now = MARKET.tick_velocity(10)
        vel_base = MARKET.tick_velocity(60)
        if vel_base > 0 and vel_now >= self.vel_burst_mult * vel_base:
            if net != 0:
                sig6 = 1 if net > 0 else -1

        # Vote
        votes = [sig1, sig2, sig3, sig4, sig5, sig6]
        n_pos = sum(1 for v in votes if v == 1)
        n_neg = sum(1 for v in votes if v == -1)
        if n_pos >= self.vote_thresh and n_pos > n_neg:
            base_side = "LONG"
        elif n_neg >= self.vote_thresh and n_neg > n_pos:
            base_side = "SHORT"
        else:
            return
        side = base_side if self.mode == 'follow' else ("SHORT" if base_side == "LONG" else "LONG")
        entry = bc
        extra = {
            'fill_mode': 'marketable',
            'stop_offset_pts': self.stop_pts,
            'target_offset_pts': self.target_pts,
            'exit_mode': 'stop_market',
        }
        if side == "LONG":
            stop = entry - self.stop_pts
            tgt = entry + self.target_pts
        else:
            stop = entry + self.stop_pts
            tgt = entry - self.target_pts
        self.add_setup(side, side, entry, stop, tgt, ts,
                       key=("ev", round(entry, 1), side, int(ts) % 86400),
                       expires_in=self.expires, extra=extra)


class VolScaledRR(StrategyBase):
    """Avenue D. On each 1m bar close, detect an impulse pullback signal,
    then scale stop/target as multiples of current ATR.

    Uses MARKET.atr() (60-bar mean) for ATR. Setup uses fill_mode='marketable'.
    """
    def __init__(self, name, atr_stop_mult=0.5, atr_tgt_mult=1.5,
                 pull_pct=0.236, impulse_pts=5.0, impulse_bars=4,
                 invert=True, min_atr=2.0, max_atr=30.0,
                 max_hold=MAX_HOLD_S, expires=180, cooldown_s=10,
                 session_start=None, session_end=None):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start,
                         session_end=session_end)
        self.atr_stop_mult = atr_stop_mult
        self.atr_tgt_mult = atr_tgt_mult
        self.pull_pct = pull_pct
        self.impulse_pts = impulse_pts
        self.impulse_bars = impulse_bars
        self.invert = invert
        self.min_atr = min_atr
        self.max_atr = max_atr
        self.expires = expires

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if len(hist) < self.impulse_bars:
            return
        atr = MARKET.atr()
        if atr is None or atr < self.min_atr or atr > self.max_atr:
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
        if orig_side == "LONG":
            entry = ih - self.pull_pct * rng
        else:
            entry = il + self.pull_pct * rng
        stop_pts = self.atr_stop_mult * atr
        tgt_pts = self.atr_tgt_mult * atr
        if stop_pts < 1.0:
            stop_pts = 1.0  # never less than 1pt — exec realism
        if side == "LONG":
            stop = entry - stop_pts
            tgt = entry + tgt_pts
        else:
            stop = entry + stop_pts
            tgt = entry - tgt_pts
        extra = {
            'fill_mode': 'marketable',
            'stop_offset_pts': stop_pts,
            'target_offset_pts': tgt_pts,
            'exit_mode': 'stop_market',
        }
        self.add_setup(side, orig_side, entry, stop, tgt, ts,
                       key=("vsrr", round(ih, 1), round(il, 1), side),
                       expires_in=self.expires, extra=extra)


class AdaptiveWRGate(MarketablePullback):
    """Avenue E. Wraps MarketablePullback with a rolling-WR gate. Only emit
    a new setup if rolling WR over the last `lookback_n` completed trades
    is >= `wr_thresh`. Once first lookback_n trades are accumulated, the
    gate activates.

    Implementation: override on_bar_close to compute WR from self.completed
    (which r9 booking writes pnl_pts; we check pnl_pts > 0).
    """
    def __init__(self, *args, wr_lookback=20, wr_thresh=0.45,
                 warmup_n=10, **kwargs):
        super().__init__(*args, **kwargs)
        self._wr_lookback = wr_lookback
        self._wr_thresh = wr_thresh
        self._warmup_n = warmup_n

    def _wr_ok(self):
        n = len(self.completed)
        if n < self._warmup_n:
            return True
        recent = self.completed[-self._wr_lookback:]
        wins = sum(1 for c in recent if c[0] > 0)
        wr = wins / len(recent)
        return wr >= self._wr_thresh

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        if not self._wr_ok():
            return
        super().on_bar_close(ts, hh, mn, bo, bh, bl, bc, hist)


class FixedTimeExit(StrategyBase):
    """Avenue F. On an impulse signal (1m bar), enter marketable; force exit
    at exit_secs (using max_hold). Stop is protective only. Direction is
    fade (mean-revert against impulse).
    """
    def __init__(self, name, exit_secs=60, stop_pts=5.0,
                 impulse_pts=3.0, impulse_bars=2, mode='fade',
                 pull_pct=0.0, expires=10, cooldown_s=5,
                 session_start=None, session_end=None):
        # max_hold=exit_secs ensures r9 forces exit at exit_secs
        super().__init__(name, cooldown_s=cooldown_s, max_hold=exit_secs,
                         session_start=session_start,
                         session_end=session_end)
        self.exit_secs = exit_secs
        self.stop_pts = stop_pts
        self.impulse_pts = impulse_pts
        self.impulse_bars = impulse_bars
        self.mode = mode  # 'fade' or 'follow'
        self.pull_pct = pull_pct
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
        side = ("SHORT" if orig_side == "LONG" else "LONG") if self.mode == 'fade' else orig_side
        # Enter at current close (or with optional pullback)
        if self.pull_pct > 0:
            if orig_side == "LONG":
                entry = ih - self.pull_pct * rng
            else:
                entry = il + self.pull_pct * rng
        else:
            entry = bc
        # Very large target to make max_hold the binding exit
        target_pts = 999.0
        extra = {
            'fill_mode': 'marketable',
            'stop_offset_pts': self.stop_pts,
            'target_offset_pts': target_pts,
            'exit_mode': 'stop_market',
            'max_hold': self.exit_secs,
        }
        if side == "LONG":
            stop = entry - self.stop_pts
            tgt = entry + target_pts
        else:
            stop = entry + self.stop_pts
            tgt = entry - target_pts
        self.add_setup(side, side, entry, stop, tgt, ts,
                       key=("fte", round(ih, 1), round(il, 1), side),
                       expires_in=self.expires, extra=extra)


# ============================================================================
# Build strategy set
# ============================================================================

def build_strategies():
    strats = []
    avenue_map = {}

    # ----------------------------------------------------------------
    # Baselines: CANON_INV_236 (matches r16) for sanity
    # ----------------------------------------------------------------
    canon_lim = PullbackStrategy(
        "BASELINE_CANON_INV_236_LIMIT",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True)
    strats.append(canon_lim)
    avenue_map[canon_lim.name] = "BASELINE"
    canon_mkt = MarketablePullback(
        "BASELINE_CANON_INV_236_s10t20",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True)
    strats.append(canon_mkt)
    avenue_map[canon_mkt.name] = "BASELINE"

    # ----------------------------------------------------------------
    # A. MICRO-SCALP — ~150 variants
    # ----------------------------------------------------------------
    A_k = [2, 3, 4]
    A_mode = ['fade', 'follow']
    A_targets = [0.5, 1.0, 1.5, 2.0]
    A_stops = [0.5, 1.0, 1.5]
    A_cool = [1.0, 2.0, 3.0]
    A_sess = [None, ((13, 30), (20, 0))]  # full and RTH
    a_count = 0
    for k in A_k:
        for mode in A_mode:
            for tgt in A_targets:
                for sp in A_stops:
                    for cs in A_cool:
                        for sess in A_sess:
                            if sess is None:
                                ss = se = None
                                sess_tag = "full"
                            else:
                                ss, se = sess
                                sess_tag = "RTH"
                            name = (f"A_MSC_k{k}_{mode}_s{int(sp*10)}t{int(tgt*10)}"
                                    f"_cs{int(cs*10)}_{sess_tag}")
                            s = MicroScalp(
                                name, k_ticks=k, mode=mode,
                                stop_pts=sp, target_pts=tgt,
                                cool_setup_s=cs,
                                session_start=ss, session_end=se)
                            strats.append(s)
                            avenue_map[name] = "A_MICROSCALP"
                            a_count += 1
                            if a_count >= 144:
                                break
                        if a_count >= 144:
                            break
                    if a_count >= 144:
                        break
                if a_count >= 144:
                    break
            if a_count >= 144:
                break
        if a_count >= 144:
            break

    # ----------------------------------------------------------------
    # B. NEWS-WINDOW — ~80 variants (4 windows × 4 stops × 3 targets × 2 modes ~ 96)
    # ----------------------------------------------------------------
    B_windows = [
        ((12, 30), (12, 45), "1230"),
        ((13, 30), (13, 45), "1330"),
        ((14, 0), (14, 15), "1400"),
        ((18, 0), (18, 15), "1800"),
    ]
    B_stops = [5.0, 8.0, 12.0]
    B_targets = [20.0, 40.0, 60.0]
    B_modes = ['follow', 'fade']
    B_trigs = [2.0, 4.0]
    b_count = 0
    for win in B_windows:
        ws, we, tag = win
        for sp in B_stops:
            for tg in B_targets:
                for mode in B_modes:
                    for trig in B_trigs:
                        name = (f"B_NW_{tag}_{mode}_tr{int(trig*10)}"
                                f"_s{int(sp)}t{int(tg)}")
                        s = NewsWindow(
                            name, win_start=ws, win_end=we,
                            trig_pts=trig, stop_pts=sp, target_pts=tg,
                            mode=mode)
                        strats.append(s)
                        avenue_map[name] = "B_NEWSWIN"
                        b_count += 1

    # ----------------------------------------------------------------
    # C. ENSEMBLE VOTING — ~80 variants
    # ----------------------------------------------------------------
    C_thresh = [3, 4, 5]
    C_mode = ['follow', 'fade']
    C_stop_tgt = [(5, 15), (8, 24), (10, 30), (12, 36)]
    C_pulls = [0.236, 0.382]
    C_sess = [None, ((13, 30), (20, 0))]
    c_count = 0
    for vt in C_thresh:
        for mode in C_mode:
            for sp, tg in C_stop_tgt:
                for pp in C_pulls:
                    for sess in C_sess:
                        if sess is None:
                            ss = se = None
                            sess_tag = "full"
                        else:
                            ss, se = sess
                            sess_tag = "RTH"
                        name = (f"C_EV_v{vt}_{mode}_s{sp}t{tg}_pp{int(pp*1000)}"
                                f"_{sess_tag}")
                        s = EnsembleVoting(
                            name, vote_thresh=vt, mode=mode,
                            stop_pts=sp, target_pts=tg, pull_pct=pp,
                            session_start=ss, session_end=se)
                        strats.append(s)
                        avenue_map[name] = "C_ENSEMBLE"
                        c_count += 1

    # ----------------------------------------------------------------
    # D. VOLATILITY-SCALED R:R — ~80 variants
    # ----------------------------------------------------------------
    D_stop_mult = [0.3, 0.5, 0.7, 1.0]
    D_tgt_mult = [1.0, 1.5, 2.0, 3.0]
    D_invert = [True, False]
    D_pulls = [0.236, 0.382]
    D_impulse = [3.0, 5.0]
    d_count = 0
    for sm in D_stop_mult:
        for tm in D_tgt_mult:
            for inv in D_invert:
                for pp in D_pulls:
                    for imp in D_impulse:
                        if d_count >= 80:
                            break
                        invtag = "INV" if inv else "TRD"
                        name = (f"D_VSRR_{invtag}_sm{int(sm*10)}tm{int(tm*10)}"
                                f"_pp{int(pp*1000)}_imp{int(imp*10)}")
                        s = VolScaledRR(
                            name, atr_stop_mult=sm, atr_tgt_mult=tm,
                            invert=inv, pull_pct=pp, impulse_pts=imp)
                        strats.append(s)
                        avenue_map[name] = "D_VOLSCALE"
                        d_count += 1
                    if d_count >= 80:
                        break
                if d_count >= 80:
                    break
            if d_count >= 80:
                break
        if d_count >= 80:
            break

    # ----------------------------------------------------------------
    # E. ADAPTIVE WR GATE — ~80 variants
    # ----------------------------------------------------------------
    E_base_params = [
        # (imp, ib, pp, sp, tg, invert) — top winners from prior rounds
        (5.0, 4, 0.236, 10, 20, True),    # CANON
        (5.0, 4, 0.382, 8, 24, True),
        (3.0, 4, 0.236, 5, 15, True),
        (6.0, 4, 0.382, 5, 20, True),
        (4.0, 4, 0.236, 8, 16, True),
    ]
    E_lookback = [10, 20, 50]
    E_thresh = [0.40, 0.45, 0.50]
    E_warmup = [5, 10]
    e_count = 0
    for (imp, ib, pp, sp, tg, inv) in E_base_params:
        for lb in E_lookback:
            for th in E_thresh:
                for wu in E_warmup:
                    invtag = "INV" if inv else "TRD"
                    name = (f"E_AWR_{invtag}_imp{int(imp*10)}_pp{int(pp*1000)}"
                            f"_s{sp}t{tg}_lb{lb}_th{int(th*100)}_wu{wu}")
                    s = AdaptiveWRGate(
                        name, impulse_pts=imp, impulse_bars=ib,
                        pull_pct=pp, stop_pts=sp, target_pts=tg,
                        invert=inv, wr_lookback=lb, wr_thresh=th,
                        warmup_n=wu)
                    strats.append(s)
                    avenue_map[name] = "E_WRGATE"
                    e_count += 1

    # ----------------------------------------------------------------
    # F. FIXED TIME EXIT — ~80 variants
    # ----------------------------------------------------------------
    F_exit_secs = [30, 60, 90, 120, 180]
    F_stops = [3.0, 5.0, 8.0]
    F_imp = [2.0, 3.0, 5.0]
    F_imp_bars = [2, 3, 4]
    F_mode = ['fade', 'follow']
    f_count = 0
    for es in F_exit_secs:
        for sp in F_stops:
            for imp in F_imp:
                for ib in F_imp_bars:
                    for mode in F_mode:
                        if f_count >= 80:
                            break
                        name = (f"F_FTE_e{es}_s{int(sp)}_imp{int(imp*10)}"
                                f"_b{ib}_{mode}")
                        s = FixedTimeExit(
                            name, exit_secs=es, stop_pts=sp,
                            impulse_pts=imp, impulse_bars=ib, mode=mode)
                        strats.append(s)
                        avenue_map[name] = "F_FIXTIME"
                        f_count += 1
                    if f_count >= 80:
                        break
                if f_count >= 80:
                    break
            if f_count >= 80:
                break
        if f_count >= 80:
            break

    counts = {
        "A_MICROSCALP": a_count, "B_NEWSWIN": b_count, "C_ENSEMBLE": c_count,
        "D_VOLSCALE": d_count, "E_WRGATE": e_count, "F_FIXTIME": f_count,
    }
    return strats, avenue_map, counts


# ============================================================================
# Checkpoint
# ============================================================================

def save_checkpoint(offset, day_counter, last_day_key, strats):
    state = {
        "offset": int(offset),
        "day_counter": int(day_counter),
        "last_day_key": last_day_key,
        "variants": {
            s.name: {
                "completed": list(s.completed),
                "by_day": dict(s.by_day),
                "n_trades": int(s.n_trades),
            } for s in strats
        },
    }
    tmp = CHECKPOINT_PATH + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, CHECKPOINT_PATH)


def load_checkpoint(strats):
    if not os.path.exists(CHECKPOINT_PATH):
        return None
    try:
        with open(CHECKPOINT_PATH, "rb") as f:
            state = pickle.load(f)
    except Exception as e:
        print(f"[round17] checkpoint load failed: {e}", file=sys.stderr)
        return None
    by_name = {s.name: s for s in strats}
    for name, v in state.get("variants", {}).items():
        s = by_name.get(name)
        if s is None:
            continue
        s.completed = list(v.get("completed", []))
        s.by_day = dict(v.get("by_day", {}))
        s.n_trades = int(v.get("n_trades", 0))
    return (int(state["offset"]), int(state["day_counter"]), state["last_day_key"])


# ============================================================================
# Reporting
# ============================================================================

def report_strategy(strat, total_days, fee_rt=FEE_FULL_RT, pt_value=MNQ_PER_PT):
    n = len(strat.completed)
    if n == 0:
        return {
            'name': strat.name, 'n': 0, 'wr': 0.0, 'net': 0.0,
            'per_day': 0.0, 'per_trade': 0.0, 'max_dd': 0.0,
            'trades_per_day': 0.0, 'sharpe': 0.0,
        }
    # All r9 booking: (pnl_pts, reason, day, block, regime)
    # r4 booking (PullbackStrategy LIMIT): (pnl_usd, reason, day) — c[0] is USD.
    # Detect via length: 3-tuple → r4 USD path; 5-tuple → r9 points path.
    wins = 0
    net = 0.0
    day_nets = defaultdict(float)
    series = []
    for c in strat.completed:
        if len(c) >= 4:
            pnl_pts = c[0]
            d = c[2]
            pnl_usd = pnl_pts * pt_value - fee_rt
        else:
            # r4 path: pnl_usd already includes fees
            pnl_usd = c[0]
            d = c[2] if len(c) > 2 else 0
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
    cum = 0.0; peak = 0.0; max_dd = 0.0
    for x in series:
        cum += x
        if cum > peak:
            peak = cum
        if peak - cum > max_dd:
            max_dd = peak - cum
    if len(daily) > 1:
        mean = sum(daily) / len(daily)
        var = sum((x - mean) ** 2 for x in daily) / (len(daily) - 1)
        std = math.sqrt(var) if var > 0 else 0.0
        sharpe = (mean / std) if std > 0 else 0.0
    else:
        sharpe = 0.0
    return {
        'name': strat.name, 'n': n, 'wr': wr, 'net': net,
        'per_day': per_day, 'per_trade': per_trade,
        'max_dd': max_dd, 'trades_per_day': trades_per_day,
        'sharpe': sharpe,
    }


# ============================================================================
# Main
# ============================================================================

def main():
    strats, avenue_map, counts = build_strategies()
    n_total = len(strats)
    print(f"[round17] Built {n_total} strategies", file=sys.stderr)
    for av, c in counts.items():
        print(f"  {av:14s}: {c}", file=sys.stderr)

    # Attach r9/r7 executor to EVERY strategy
    for s in strats:
        attach_r7_executor(s)

    # Partition by feed type
    v1m = []     # 1-minute bar
    vtick = []   # tick feed only
    for s in strats:
        if isinstance(s, (MicroScalp, NewsWindow)):
            vtick.append(s)
        else:
            v1m.append(s)
    print(f"[round17] v1m={len(v1m)} vtick={len(vtick)}", file=sys.stderr)

    # Resume
    resumed = load_checkpoint(strats)
    if resumed is not None:
        start_offset, day_counter, last_day_key = resumed
        booked = sum(s.n_trades for s in strats)
        print(f"[round17] RESUMING from offset {start_offset:,} "
              f"day={day_counter} (booked={booked:,} trades)", file=sys.stderr)
    else:
        start_offset = OFFSET
        day_counter = -1
        last_day_key = None

    bb_1m = BarBuilder(granularity_secs=60, max_history=300)

    n_lines = 0
    t0 = time.time()

    with open(PATH, "rb") as f:
        f.seek(start_offset)
        f.readline()  # discard partial line
        for raw in f:
            n_lines += 1
            if n_lines % CHECKPOINT_EVERY_TICKS == 0:
                pos = f.tell()
                try:
                    save_checkpoint(pos, day_counter, last_day_key, strats)
                except Exception as e:
                    print(f"[round17] ckpt save fail: {e}", file=sys.stderr)
                rate = n_lines / (time.time() - t0)
                top = max((s.n_trades, s.name) for s in strats)
                print(f"  [round17] {n_lines/1e6:.2f}M ticks rate={rate:.0f}/s "
                      f"elapsed={(time.time()-t0)/60:.1f}m day={day_counter} "
                      f"top_trades={top[1]}({top[0]})", file=sys.stderr, flush=True)

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
                if day_counter >= MAX_DAYS:
                    break
            ts = day_counter * 86400 + hh * 3600 + mn * 60 + ss + ns / 1e7

            # Feed MARKET (used by EnsembleVoting / VolScaledRR)
            MARKET.feed_tick(ts, last, bid, ask)

            # 1m bars
            if bb_1m.on_tick(ts, last):
                closed = bb_1m.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    MARKET.feed_bar(o, h, l, c)
                    for s in v1m:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_1m.history)
            # tick feeds (MicroScalp + NewsWindow)
            for s in vtick:
                s.feed_tick(ts, last)

            # Execute using r9's tick handler — verbatim. NO custom logic.
            for s in strats:
                if s.pending or s.in_trade is not None:
                    r9.r9_bot_on_tick(s, ts, bid, ask, day_counter, hh, mn, last)

    print(f"\n[round17] Done. Days={day_counter+1}, lines={n_lines:,}",
          file=sys.stderr)

    # ========================================================================
    # Report
    # ========================================================================
    n_days = max(1, day_counter + 1)
    rows = []
    for s in strats:
        r = report_strategy(s, n_days, FEE_FULL_RT)
        r['avenue'] = avenue_map.get(s.name, "?")
        rows.append(r)

    rows.sort(key=lambda r: -r['per_day'])

    full_pass = [r for r in rows
                 if r['trades_per_day'] >= 300 and r['wr'] >= 0.45
                 and r['per_day'] >= 1000 and r['max_dd'] <= 5000]

    # Per-avenue top 5
    by_avenue = defaultdict(list)
    for r in rows:
        by_avenue[r['avenue']].append(r)
    for av in by_avenue:
        by_avenue[av].sort(key=lambda r: -r['per_day'])

    canon_rows = [r for r in rows if r['name'].startswith('BASELINE_')]

    with open(RESULTS_PATH, "w") as f:
        f.write(f"# Round 17 — six fresh angles, bot-faithful (r9 executor)\n\n")
        f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Strategies tested: {n_total}\n")
        f.write(f"Days: {n_days}\n")
        f.write(f"Tick stream: {n_lines:,} lines\n")
        f.write(f"Fee model: ${FEE_FULL_RT}/RT, MNQ $2/pt\n\n")

        f.write(f"## CANON baseline verification\n\n")
        f.write(f"Expected per round-16: ~108 tr/d (LIMIT), 37% WR, -$248/day.\n\n")
        f.write(f"| Strategy | Tr/d | WR% | $/day | $/tr | DD | Sharpe |\n")
        f.write(f"|---|---:|---:|---:|---:|---:|---:|\n")
        for r in canon_rows:
            f.write(f"| {r['name']} | {r['trades_per_day']:.1f} | "
                    f"{r['wr']*100:.1f} | ${r['per_day']:+.2f} | "
                    f"${r['per_trade']:+.2f} | ${r['max_dd']:.0f} | "
                    f"{r['sharpe']:.2f} |\n")

        f.write(f"\n## FULL_PASS strategies (>=300 tr/d, >=45% WR, "
                f">=$1000/day, DD<=$5000): {len(full_pass)}\n\n")
        if full_pass:
            for r in full_pass:
                f.write(f"- **{r['name']}** ({r['avenue']}): "
                        f"{r['trades_per_day']:.1f} tr/d, "
                        f"{r['wr']*100:.1f}% WR, "
                        f"${r['per_day']:+.0f}/day, "
                        f"DD=${r['max_dd']:.0f}, Sharpe={r['sharpe']:.2f}\n")
        else:
            f.write(f"**NONE.**\n\n")

        f.write(f"\n## Top 30 by $/day (all avenues)\n\n")
        f.write(f"| Rank | Avenue | Strategy | Tr/d | WR% | $/day | $/tr | DD | Sharpe |\n")
        f.write(f"|---:|---|---|---:|---:|---:|---:|---:|---:|\n")
        for i, r in enumerate(rows[:30], 1):
            f.write(f"| {i} | {r['avenue']} | {r['name']} | "
                    f"{r['trades_per_day']:.1f} | "
                    f"{r['wr']*100:.1f} | ${r['per_day']:+.2f} | "
                    f"${r['per_trade']:+.2f} | ${r['max_dd']:.0f} | "
                    f"{r['sharpe']:.2f} |\n")

        f.write(f"\n## Top 5 per avenue\n\n")
        for av in ["A_MICROSCALP", "B_NEWSWIN", "C_ENSEMBLE", "D_VOLSCALE",
                   "E_WRGATE", "F_FIXTIME"]:
            avrows = by_avenue.get(av, [])
            if not avrows:
                continue
            f.write(f"\n### {av} ({len(avrows)} strategies, top 5)\n\n")
            f.write(f"| Rank | Strategy | Tr/d | WR% | $/day | $/tr | DD | Sharpe |\n")
            f.write(f"|---:|---|---:|---:|---:|---:|---:|---:|\n")
            for i, r in enumerate(avrows[:5], 1):
                f.write(f"| {i} | {r['name']} | {r['trades_per_day']:.1f} | "
                        f"{r['wr']*100:.1f} | ${r['per_day']:+.2f} | "
                        f"${r['per_trade']:+.2f} | ${r['max_dd']:.0f} | "
                        f"{r['sharpe']:.2f} |\n")

        # Honest assessment
        f.write(f"\n## Honest assessment\n\n")
        n_positive = sum(1 for r in rows if r['per_day'] > 0)
        n_50 = sum(1 for r in rows if r['per_day'] >= 50)
        n_100 = sum(1 for r in rows if r['per_day'] >= 100)
        n_500 = sum(1 for r in rows if r['per_day'] >= 500)
        n_300_tpd = sum(1 for r in rows if r['trades_per_day'] >= 300)
        n_45wr = sum(1 for r in rows if r['wr'] >= 0.45)
        f.write(f"- Positive $/day: {n_positive}/{n_total}\n")
        f.write(f"- >= $50/day: {n_50}\n")
        f.write(f"- >= $100/day: {n_100}\n")
        f.write(f"- >= $500/day: {n_500}\n")
        f.write(f"- >= 300 trades/day: {n_300_tpd}\n")
        f.write(f"- >= 45% WR: {n_45wr}\n")
        f.write(f"- FULL_PASS (300/45/$1k/$5kDD): {len(full_pass)}\n\n")
        if not full_pass:
            best = rows[0] if rows else None
            f.write(f"### Reality check\n\n")
            if best:
                f.write(f"Round 17 best: **{best['name']}** ({best['avenue']}) — "
                        f"{best['trades_per_day']:.1f} tr/d, "
                        f"{best['wr']*100:.1f}% WR, "
                        f"${best['per_day']:+.0f}/day, "
                        f"DD=${best['max_dd']:.0f}.\n\n")
            f.write(f"After 17 rounds and ~10,000+ honestly-measured variants "
                    f"under the bot-faithful r9 executor (queue overshoot, "
                    f"200ms latency, slippage, $1.91/RT), the target remains "
                    f"unreached. The structural wall: MNQ at 1 contract with "
                    f"$1.91 fees requires >$3.30 per-trade gross P&L on average "
                    f"to sustain $1k/day at 300 trades — and realistic friction "
                    f"keeps even the best edge from clearing that bar.\n")
        else:
            f.write(f"### Reality check\n\n")
            f.write(f"Round 17 found {len(full_pass)} FULL_PASS strategies. "
                    f"Verify on out-of-sample data before any deployment.\n")

    # CSV summary
    with open(SUMMARY_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank", "avenue", "name", "trades_per_day", "wr",
                    "per_day_usd", "per_trade_usd", "max_dd_usd",
                    "sharpe", "n_trades"])
        for i, r in enumerate(rows, 1):
            w.writerow([i, r['avenue'], r['name'],
                        f"{r['trades_per_day']:.2f}",
                        f"{r['wr']:.4f}",
                        f"{r['per_day']:.2f}",
                        f"{r['per_trade']:.2f}",
                        f"{r['max_dd']:.2f}",
                        f"{r['sharpe']:.3f}",
                        r['n']])

    # Clean up checkpoint
    try:
        if os.path.exists(CHECKPOINT_PATH):
            os.remove(CHECKPOINT_PATH)
    except Exception:
        pass
    print(f"[round17] Results saved to {RESULTS_PATH}", file=sys.stderr)
    print(f"[round17] Summary CSV at {SUMMARY_CSV}", file=sys.stderr)


if __name__ == "__main__":
    main()
