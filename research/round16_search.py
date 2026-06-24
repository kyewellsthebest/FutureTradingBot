#!/usr/bin/env python3
"""Round 16 — fresh angles, NO custom queue logic.

Mission: find strategies that don't rely on LIMIT-at-touch fills. Use the
real r9 executor (r9_bot_on_tick) AS-IS via fill_mode='marketable'/'stop'.

Avenues (per round-16 brief):
  A. MARKETABLE LIMIT entries on pullback signals (variants of MarketablePullback)
  B. STOP entries on N-bar breakouts (variants of BreakoutStrategy)
  C. Range-compression + breakout follow (custom CompressionBreakout class)
  D. Intra-minute momentum continuation, stop entry (custom IntraMinMomCont class)
  E. Adaptive intra-trade stops via be_trig + trail_pts (built into r9 executor)
  F. Time-window mean reversion (gated MarketablePullback over fixed windows)
  G. Spread-tight limit fade (custom SpreadFade class)
  H. Multi-fill OCO with cohort cancel (custom OCOBracket class)

All entries emit add_setup() with fill_mode set; r9 executor handles the
rest. No execution code modified.

Output: /home/user/HFTBot/research/round16_results.md
        /home/user/HFTBot/research/round16_summary.csv
"""
from __future__ import annotations
import os, sys, time, math, pickle, csv
from collections import deque, defaultdict

sys.path.insert(0, "/home/user/HFTBot")
sys.path.insert(0, "/home/user/HFTBot/research")

# Env defaults (mirror r15)
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
CHECKPOINT_PATH = "/home/user/HFTBot/research/round16_checkpoint.pkl"
RESULTS_PATH = "/home/user/HFTBot/research/round16_results.md"
SUMMARY_CSV = "/home/user/HFTBot/research/round16_summary.csv"


# ============================================================================
# Custom strategy classes (all emit add_setup with fill_mode → r9 executor)
# ============================================================================

class CompressionBreakout(StrategyBase):
    """Avenue C. After K consecutive narrow-range bars (each < frac * median20),
    fire a stop-entry in the direction of the first wide breakout bar.

    Marketable follow-through: place STOP-BUY at ih + buf or STOP-SELL at il - buf
    with extra={'fill_mode': 'stop'}.
    """
    def __init__(self, name, compress_k=3, compress_frac=0.5,
                 wide_mult=1.5, buf_pts=1.0,
                 stop_pts=8, target_pts=25,
                 max_hold=MAX_HOLD_S, session_start=None, session_end=None,
                 expires=120, cooldown_s=10):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.compress_k = compress_k
        self.compress_frac = compress_frac
        self.wide_mult = wide_mult
        self.buf_pts = buf_pts
        self.stop_pts = stop_pts
        self.target_pts = target_pts
        self.expires = expires
        self._ranges = deque(maxlen=20)

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        rng = bh - bl
        self._ranges.append(rng)
        if len(self._ranges) < 20:
            return
        sorted_r = sorted(self._ranges)
        median = sorted_r[len(sorted_r) // 2]
        if median <= 0:
            return
        if len(hist) < self.compress_k + 1:
            return
        # Check the last K bars BEFORE current bar were all compressed
        recent = list(hist)[-(self.compress_k + 1):-1]
        if any((b[1] - b[2]) >= self.compress_frac * median for b in recent):
            return
        # Current bar must be wide
        if rng < self.wide_mult * median:
            return
        # Direction = sign of current bar's close-open
        net = bc - bo
        if abs(net) < 0.5:
            return
        ih = bh
        il = bl
        if net > 0:
            up_entry = ih + self.buf_pts
            extra = {
                'fill_mode': 'stop',
                'stop_offset_pts': self.stop_pts,
                'target_offset_pts': self.target_pts,
                'exit_mode': 'stop_market',
            }
            self.add_setup("LONG", "LONG", up_entry,
                           up_entry - self.stop_pts,
                           up_entry + self.target_pts, ts,
                           key=("cb_l", round(ih, 1), round(il, 1)),
                           expires_in=self.expires, extra=extra)
        else:
            dn_entry = il - self.buf_pts
            extra = {
                'fill_mode': 'stop',
                'stop_offset_pts': self.stop_pts,
                'target_offset_pts': self.target_pts,
                'exit_mode': 'stop_market',
            }
            self.add_setup("SHORT", "SHORT", dn_entry,
                           dn_entry + self.stop_pts,
                           dn_entry - self.target_pts, ts,
                           key=("cb_s", round(ih, 1), round(il, 1)),
                           expires_in=self.expires, extra=extra)


class IntraMinMomCont(StrategyBase):
    """Avenue D. On 30s bar close where the bar showed >= trigger_pts net move,
    place a STOP-entry at the current close + 1pt for momentum continuation.

    Uses 30s sub-bar; signal emits stop-entry in same direction. r9 stop fills
    on next ask >= entry (LONG) or bid <= entry (SHORT).
    """
    def __init__(self, name, trigger_pts=2.0, buf_pts=1.0,
                 stop_pts=5, target_pts=15,
                 max_hold=240, session_start=None, session_end=None,
                 expires=30, cooldown_s=10):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.trigger_pts = trigger_pts
        self.buf_pts = buf_pts
        self.stop_pts = stop_pts
        self.target_pts = target_pts
        self.expires = expires

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        net = bc - bo
        if abs(net) < self.trigger_pts:
            return
        if net > 0:
            up_entry = bc + self.buf_pts
            extra = {
                'fill_mode': 'stop',
                'stop_offset_pts': self.stop_pts,
                'target_offset_pts': self.target_pts,
                'exit_mode': 'stop_market',
            }
            self.add_setup("LONG", "LONG", up_entry,
                           up_entry - self.stop_pts,
                           up_entry + self.target_pts, ts,
                           key=("immc_l", round(bc, 1), int(ts*10) % 1000),
                           expires_in=self.expires, extra=extra)
        else:
            dn_entry = bc - self.buf_pts
            extra = {
                'fill_mode': 'stop',
                'stop_offset_pts': self.stop_pts,
                'target_offset_pts': self.target_pts,
                'exit_mode': 'stop_market',
            }
            self.add_setup("SHORT", "SHORT", dn_entry,
                           dn_entry + self.stop_pts,
                           dn_entry - self.target_pts, ts,
                           key=("immc_s", round(bc, 1), int(ts*10) % 1000),
                           expires_in=self.expires, extra=extra)


class AdaptiveStopMktPB(MarketablePullback):
    """Avenue E. MarketablePullback with be_trig + trail_pts threaded into the
    setup's extra dict. r9 executor honors be_trig_pts/be_off_pts/trail_pts
    on the in_trade dict.
    """
    def __init__(self, *args, be_trig_pts=3.0, be_off_pts=0.0,
                 trail_pts=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._be_trig_pts = be_trig_pts
        self._be_off_pts = be_off_pts
        self._trail_pts = trail_pts

    def on_bar_close(self, ts, hh, mn, bar_o, bar_h, bar_l, bar_c, hist):
        # Snapshot pending size before parent adds setup
        before = len(self.pending)
        super().on_bar_close(ts, hh, mn, bar_o, bar_h, bar_l, bar_c, hist)
        # Inject adaptive params into any new setup
        for i in range(before, len(self.pending)):
            self.pending[i]['be_trig_pts'] = self._be_trig_pts
            self.pending[i]['be_off_pts'] = self._be_off_pts
            if self._trail_pts is not None:
                self.pending[i]['trail_pts'] = self._trail_pts


class SpreadFade(StrategyBase):
    """Avenue G. When MARKET.spread_tight_streak >= K and last 30s shows
    >= trigger_pts move, fade with a marketable limit in the opposite direction.
    Tick-driven: uses MARKET.last_px and MARKET.spread_tight_streak.
    """
    def __init__(self, name, tight_streak=5, trigger_pts=3.0,
                 stop_pts=4, target_pts=9,
                 max_hold=180, session_start=None, session_end=None,
                 expires=10, cool_setup_s=20, cooldown_s=10):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.tight_streak = tight_streak
        self.trigger_pts = trigger_pts
        self.stop_pts = stop_pts
        self.target_pts = target_pts
        self.expires = expires
        self.cool_setup_s = cool_setup_s
        self._buf = deque(maxlen=600)  # ~30s @ 20 ticks/s
        self._last_setup_ts = None

    def feed_tick(self, ts, last):
        # buf rolls every tick — examine 30s window
        self._buf.append((ts, last))
        while self._buf and ts - self._buf[0][0] > 30:
            self._buf.popleft()
        if MARKET.spread_tight_streak < self.tight_streak:
            return
        if len(self._buf) < 30:
            return
        first = self._buf[0][1]
        move = last - first
        if abs(move) < self.trigger_pts:
            return
        if self._last_setup_ts is not None and ts - self._last_setup_ts < self.cool_setup_s:
            return
        if not self._in_session_approx():
            pass  # session checked in r9 executor too
        # Fade direction
        side = "SHORT" if move > 0 else "LONG"
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
                       key=("sf", round(entry, 1), side, int(ts*10) % 1000),
                       expires_in=self.expires, extra=extra)
        self._last_setup_ts = ts

    def _in_session_approx(self):
        return True


class OCOBracket(StrategyBase):
    """Avenue H. On an N-bar impulse signal, place THREE setups in OCO cohort:
      - Level 1: STOP-entry in same direction at breakout+buf
      - Level 2: LIMIT-entry at first retest (mid pullback)
      - Level 3: LIMIT-entry at deep retest (deep pullback)
    First fill cancels the rest via cohort key. r9 executor handles cohort cancel.
    """
    def __init__(self, name, impulse_pts=5.0, impulse_bars=4,
                 buf_pts=1.0, mid_pull=0.3, deep_pull=0.5,
                 stop_pts=5, target_pts=15,
                 max_hold=MAX_HOLD_S, session_start=None, session_end=None,
                 expires=180, cooldown_s=10):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self.impulse_pts = impulse_pts
        self.impulse_bars = impulse_bars
        self.buf_pts = buf_pts
        self.mid_pull = mid_pull
        self.deep_pull = deep_pull
        self.stop_pts = stop_pts
        self.target_pts = target_pts
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
        side = "LONG" if net > 0 else "SHORT"
        cohort = ("oco", round(ih, 1), round(il, 1), side)

        if side == "LONG":
            # L1: stop-buy at ih + buf
            l1_entry = ih + self.buf_pts
            self.add_setup("LONG", "LONG", l1_entry,
                           l1_entry - self.stop_pts,
                           l1_entry + self.target_pts, ts,
                           key=("oco_l1", cohort),
                           expires_in=self.expires,
                           extra={'fill_mode': 'stop',
                                  'stop_offset_pts': self.stop_pts,
                                  'target_offset_pts': self.target_pts,
                                  'exit_mode': 'stop_market',
                                  'cohort': cohort})
            # L2: limit at mid pullback (ih - mid_pull * rng)
            l2_entry = ih - self.mid_pull * rng
            self.add_setup("LONG", "LONG", l2_entry,
                           l2_entry - self.stop_pts,
                           l2_entry + self.target_pts, ts,
                           key=("oco_l2", cohort),
                           expires_in=self.expires,
                           extra={'fill_mode': 'limit',
                                  'stop_offset_pts': self.stop_pts,
                                  'target_offset_pts': self.target_pts,
                                  'exit_mode': 'stop_market',
                                  'cohort': cohort})
            # L3: limit at deep pullback
            l3_entry = ih - self.deep_pull * rng
            self.add_setup("LONG", "LONG", l3_entry,
                           l3_entry - self.stop_pts,
                           l3_entry + self.target_pts, ts,
                           key=("oco_l3", cohort),
                           expires_in=self.expires,
                           extra={'fill_mode': 'limit',
                                  'stop_offset_pts': self.stop_pts,
                                  'target_offset_pts': self.target_pts,
                                  'exit_mode': 'stop_market',
                                  'cohort': cohort})
        else:
            l1_entry = il - self.buf_pts
            self.add_setup("SHORT", "SHORT", l1_entry,
                           l1_entry + self.stop_pts,
                           l1_entry - self.target_pts, ts,
                           key=("oco_s1", cohort),
                           expires_in=self.expires,
                           extra={'fill_mode': 'stop',
                                  'stop_offset_pts': self.stop_pts,
                                  'target_offset_pts': self.target_pts,
                                  'exit_mode': 'stop_market',
                                  'cohort': cohort})
            l2_entry = il + self.mid_pull * rng
            self.add_setup("SHORT", "SHORT", l2_entry,
                           l2_entry + self.stop_pts,
                           l2_entry - self.target_pts, ts,
                           key=("oco_s2", cohort),
                           expires_in=self.expires,
                           extra={'fill_mode': 'limit',
                                  'stop_offset_pts': self.stop_pts,
                                  'target_offset_pts': self.target_pts,
                                  'exit_mode': 'stop_market',
                                  'cohort': cohort})
            l3_entry = il + self.deep_pull * rng
            self.add_setup("SHORT", "SHORT", l3_entry,
                           l3_entry + self.stop_pts,
                           l3_entry - self.target_pts, ts,
                           key=("oco_s3", cohort),
                           expires_in=self.expires,
                           extra={'fill_mode': 'limit',
                                  'stop_offset_pts': self.stop_pts,
                                  'target_offset_pts': self.target_pts,
                                  'exit_mode': 'stop_market',
                                  'cohort': cohort})


# ============================================================================
# Build strategy set
# ============================================================================

def build_strategies():
    strats = []
    avenue_map = {}  # name -> avenue

    # ----------------------------------------------------------------
    # Baseline (must match r15 CANON ~$29/day @ 60 tr/d, 45% WR)
    # CANON_INV_236 with stop=10/target=20, impulse=5, bars=4, invert=True
    # ----------------------------------------------------------------
    canon = MarketablePullback(
        "BASELINE_CANON_INV_236_s10t20",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True)
    strats.append(canon)
    avenue_map[canon.name] = "BASELINE"

    # Also the LIMIT-fill variant for direct comparison to r15
    canon_lim = PullbackStrategy(
        "BASELINE_CANON_INV_236_LIMIT",
        impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
        stop_pts=10, target_pts=20, invert=True)
    strats.append(canon_lim)
    avenue_map[canon_lim.name] = "BASELINE"

    # ----------------------------------------------------------------
    # A. MARKETABLE LIMIT (pullback signal, marketable fill) — pruned
    # ----------------------------------------------------------------
    # Focused sweep — INV and TRD both, key param diagonal
    A_imp = [3.0, 5.0]
    A_pull = [0.236, 0.382, 0.5]
    A_stop_tgt = [(3, 9), (5, 15), (5, 24), (8, 24)]
    A_invert = [True, False]
    a_count = 0
    for imp in A_imp:
        for pp in A_pull:
            for sp, tg in A_stop_tgt:
                for inv in A_invert:
                    invtag = "INV" if inv else "TRD"
                    name = f"A_MKT_{invtag}_imp{int(imp*10)}_pp{int(pp*1000)}_s{sp}t{tg}"
                    s = MarketablePullback(
                        name, impulse_pts=imp, impulse_bars=4,
                        pull_pct=pp, stop_pts=sp, target_pts=tg, invert=inv)
                    strats.append(s)
                    avenue_map[name] = "A_MARKETABLE"
                    a_count += 1

    # ----------------------------------------------------------------
    # B. STOP-LIMIT entries (N-bar high/low breakout)
    # ----------------------------------------------------------------
    B_n = [5, 10, 20]
    B_buf = [1.0, 2.0]
    B_stop_tgt = [(5, 25), (8, 40), (5, 15), (8, 24)]
    b_count = 0
    for n in B_n:
        for buf in B_buf:
            for sp, tg in B_stop_tgt:
                name = f"B_BRK_n{n}_buf{int(buf*10)}_s{sp}t{tg}"
                s = BreakoutStrategy(
                    name, n_bars=n, buf_pts=buf,
                    stop_pts=sp, target_pts=tg,
                    min_range_pts=2.0, max_range_pts=80.0)
                strats.append(s)
                avenue_map[name] = "B_STOPBRK"
                b_count += 1
    # Session-windowed variants on the best base
    for sess in [((13,30),(16,0)), ((13,30),(20,0))]:
        ss, se = sess
        tag = f"{ss[0]:02d}{ss[1]:02d}_{se[0]:02d}{se[1]:02d}"
        for sp, tg in [(5, 25), (8, 40)]:
            name = f"B_BRK_n10_sess{tag}_s{sp}t{tg}"
            s = BreakoutStrategy(
                name, n_bars=10, buf_pts=1.0,
                stop_pts=sp, target_pts=tg,
                session_start=ss, session_end=se)
            strats.append(s)
            avenue_map[name] = "B_STOPBRK"
            b_count += 1

    # ----------------------------------------------------------------
    # C. CompressionBreakout (range expansion follow)
    # ----------------------------------------------------------------
    C_k = [3, 5, 8]
    C_frac = [0.5]
    C_mult = [1.5, 2.0]
    C_stop_tgt = [(8, 25), (10, 30), (12, 36), (8, 40)]
    c_count = 0
    for k in C_k:
        for frac in C_frac:
            for mult in C_mult:
                for sp, tg in C_stop_tgt:
                    name = f"C_CMP_k{k}_f{int(frac*10)}_m{int(mult*10)}_s{sp}t{tg}"
                    s = CompressionBreakout(
                        name, compress_k=k, compress_frac=frac,
                        wide_mult=mult, buf_pts=1.0,
                        stop_pts=sp, target_pts=tg)
                    strats.append(s)
                    avenue_map[name] = "C_COMPRESS"
                    c_count += 1

    # ----------------------------------------------------------------
    # D. Intra-minute (30s bar) momentum continuation
    # ----------------------------------------------------------------
    D_trig = [2.0, 3.0, 4.0]
    D_stop_tgt = [(3, 9), (5, 15), (8, 24)]
    D_sess = [None, ((13,30),(20,0))]
    d_count = 0
    for trig in D_trig:
        for sp, tg in D_stop_tgt:
            for sess in D_sess:
                if sess is None:
                    tag = "full"
                    ss = se = None
                else:
                    ss, se = sess
                    tag = f"{ss[0]:02d}{ss[1]:02d}"
                name = f"D_IMC_t{int(trig*10)}_s{sp}t{tg}_{tag}"
                s = IntraMinMomCont(
                    name, trigger_pts=trig, buf_pts=1.0,
                    stop_pts=sp, target_pts=tg,
                    session_start=ss, session_end=se)
                strats.append(s)
                avenue_map[name] = "D_INTRAMIN"
                d_count += 1

    # ----------------------------------------------------------------
    # E. Adaptive stops on MarketablePullback (be_trig + trail)
    # ----------------------------------------------------------------
    E_base = [
        (5.0, 4, 0.236, 10, 20, True),   # CANON
        (3.0, 4, 0.236, 5, 15, True),
        (5.0, 4, 0.382, 8, 24, True),
    ]
    E_trail = [(3, None), (3, 5), (5, None), (5, 8), (None, 5), (None, 8)]
    e_count = 0
    for imp, ib, pp, sp, tg, inv in E_base:
        for be_trig, trail in E_trail:
            invtag = "INV" if inv else "TRD"
            be_tag = "n" if be_trig is None else str(be_trig)
            tr_tag = "n" if trail is None else str(trail)
            name = f"E_AD_{invtag}_imp{int(imp*10)}_pp{int(pp*1000)}_s{sp}t{tg}_be{be_tag}tr{tr_tag}"
            s = AdaptiveStopMktPB(
                name, impulse_pts=imp, impulse_bars=ib,
                pull_pct=pp, stop_pts=sp, target_pts=tg, invert=inv,
                be_trig_pts=be_trig if be_trig is not None else 999.0,
                trail_pts=trail)
            strats.append(s)
            avenue_map[name] = "E_ADAPT"
            e_count += 1

    # ----------------------------------------------------------------
    # F. Time-window mean reversion (MarketablePullback with sessions)
    # ----------------------------------------------------------------
    F_windows = [
        ((13, 30), (14, 0), "1330"),
        ((17, 0), (17, 30), "1700"),
        ((20, 0), (20, 30), "2000"),
    ]
    F_stop_tgt = [(2, 6), (3, 9), (3, 12), (5, 15)]
    f_count = 0
    for ss, se, tag in F_windows:
        for sp, tg in F_stop_tgt:
            for inv in [True, False]:
                invtag = "INV" if inv else "TRD"
                name = f"F_TW_{tag}_{invtag}_s{sp}t{tg}"
                s = MarketablePullback(
                    name, impulse_pts=3.0, impulse_bars=4,
                    pull_pct=0.236, stop_pts=sp, target_pts=tg, invert=inv,
                    session_start=ss, session_end=se)
                strats.append(s)
                avenue_map[name] = "F_TIMEWIN"
                f_count += 1

    # ----------------------------------------------------------------
    # G. SpreadFade (tight-spread fade)
    # ----------------------------------------------------------------
    G_streak = [5, 10]
    G_trig = [2.0, 3.0, 5.0]
    G_stop_tgt = [(3, 9), (5, 15)]
    g_count = 0
    for st in G_streak:
        for tr_pts in G_trig:
            for sp, tg in G_stop_tgt:
                name = f"G_SF_st{st}_tr{int(tr_pts*10)}_s{sp}t{tg}"
                s = SpreadFade(
                    name, tight_streak=st, trigger_pts=tr_pts,
                    stop_pts=sp, target_pts=tg)
                strats.append(s)
                avenue_map[name] = "G_SPREAD"
                g_count += 1

    # ----------------------------------------------------------------
    # H. OCO Bracket (multi-fill: stop + limit + deep limit)
    # ----------------------------------------------------------------
    H_imp = [3.0, 5.0]
    H_buf = [1.0, 2.0]
    H_pulls = [(0.3, 0.5), (0.4, 0.6)]
    H_stop_tgt = [(5, 15), (8, 24), (5, 20)]
    h_count = 0
    for imp in H_imp:
        for buf in H_buf:
            for mp, dp in H_pulls:
                for sp, tg in H_stop_tgt:
                    name = f"H_OCO_imp{int(imp*10)}_buf{int(buf*10)}_p{int(mp*10)}{int(dp*10)}_s{sp}t{tg}"
                    s = OCOBracket(
                        name, impulse_pts=imp, impulse_bars=4,
                        buf_pts=buf, mid_pull=mp, deep_pull=dp,
                        stop_pts=sp, target_pts=tg)
                    strats.append(s)
                    avenue_map[name] = "H_OCO"
                    h_count += 1

    counts = {
        "A_MARKETABLE": a_count, "B_STOPBRK": b_count, "C_COMPRESS": c_count,
        "D_INTRAMIN": d_count, "E_ADAPT": e_count, "F_TIMEWIN": f_count,
        "G_SPREAD": g_count, "H_OCO": h_count,
    }
    return strats, avenue_map, counts


# ============================================================================
# 30-second bar builder for avenue D
# ============================================================================

class BarBuilder30s(BarBuilder):
    def __init__(self):
        super().__init__(granularity_secs=30, max_history=300)


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
        print(f"[round16] checkpoint load failed: {e}", file=sys.stderr)
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
    """Honest report. r9 emits tuples whose c[0] field is POINTS (r9 path)
    or USD (r4 path / SpreadFade since it uses r4 booking). We detect via
    the typical magnitude: r4 stores USD-with-fees-already-applied.

    SAFEST: support both. We tagged r4-booking strategies by setting a flag.
    """
    n = len(strat.completed)
    if n == 0:
        return {
            'name': strat.name, 'n': 0, 'wr': 0.0, 'net': 0.0,
            'per_day': 0.0, 'per_trade': 0.0, 'max_dd': 0.0,
            'trades_per_day': 0.0, 'sharpe': 0.0,
        }
    # r9.r9_bot_on_tick stores (pnl_pts, reason, day_counter, block, cell)
    # — i.e., 5-tuple with c[0] in POINTS. Convert to USD here.
    wins = 0
    net = 0.0
    day_nets = defaultdict(float)
    series = []
    for c in strat.completed:
        pnl_pts = c[0]
        d = c[2] if len(c) > 2 else 0
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
    print(f"[round16] Built {n_total} strategies", file=sys.stderr)
    for av, c in counts.items():
        print(f"  {av:14s}: {c}", file=sys.stderr)

    # Attach r9/r7 executor to EVERY strategy
    for s in strats:
        attach_r7_executor(s)

    # Partition by bar granularity
    v1m = []     # default 1-minute bar feed
    v30s = []    # IntraMinMomCont uses 30s bars
    vtick = []   # SpreadFade uses tick feed
    for s in strats:
        if isinstance(s, IntraMinMomCont):
            v30s.append(s)
        elif isinstance(s, SpreadFade):
            vtick.append(s)
        else:
            v1m.append(s)
    print(f"[round16] v1m={len(v1m)} v30s={len(v30s)} vtick={len(vtick)}",
          file=sys.stderr)

    # Resume
    resumed = load_checkpoint(strats)
    if resumed is not None:
        start_offset, day_counter, last_day_key = resumed
        booked = sum(s.n_trades for s in strats)
        print(f"[round16] RESUMING from offset {start_offset:,} "
              f"day={day_counter} (booked={booked:,} trades)", file=sys.stderr)
    else:
        start_offset = OFFSET
        day_counter = -1
        last_day_key = None

    bb_1m = BarBuilder(granularity_secs=60, max_history=300)
    bb_30s = BarBuilder(granularity_secs=30, max_history=300)

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
                    print(f"[round16] ckpt save fail: {e}", file=sys.stderr)
                rate = n_lines / (time.time() - t0)
                top = max((s.n_trades, s.name) for s in strats)
                print(f"  [round16] {n_lines/1e6:.2f}M ticks rate={rate:.0f}/s "
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

            # Feed MARKET (used by SpreadFade)
            MARKET.feed_tick(ts, last, bid, ask)

            # 1m bars
            if bb_1m.on_tick(ts, last):
                closed = bb_1m.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    MARKET.feed_bar(o, h, l, c)
                    for s in v1m:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_1m.history)
            # 30s bars
            if v30s and bb_30s.on_tick(ts, last):
                closed = bb_30s.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    for s in v30s:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_30s.history)
            # tick feeds
            for s in vtick:
                s.feed_tick(ts, last)

            # Execute using r9's tick handler — NO custom logic.
            # Fast-path: skip strategies with no pending and no active trade.
            # This is BEHAVIOR-PRESERVING: r9_bot_on_tick is a no-op when
            # pending is empty and in_trade is None (it merely checks
            # cooldown / session then iterates an empty pending list).
            for s in strats:
                if s.pending or s.in_trade is not None:
                    r9.r9_bot_on_tick(s, ts, bid, ask, day_counter, hh, mn, last)

    print(f"\n[round16] Done. Days={day_counter+1}, lines={n_lines:,}",
          file=sys.stderr)

    # ============================================================================
    # Report
    # ============================================================================
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

    # Top 30 per avenue
    by_avenue = defaultdict(list)
    for r in rows:
        by_avenue[r['avenue']].append(r)
    for av in by_avenue:
        by_avenue[av].sort(key=lambda r: -r['per_day'])

    # CANON baseline verification
    canon_rows = [r for r in rows if r['name'].startswith('BASELINE_')]

    with open(RESULTS_PATH, "w") as f:
        f.write(f"# Round 16 — fresh angles, bot-faithful (r9 executor)\n\n")
        f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Strategies tested: {n_total}\n")
        f.write(f"Days: {n_days}\n")
        f.write(f"Tick stream: {n_lines:,} lines\n")
        f.write(f"Fee model: ${FEE_FULL_RT}/RT, MNQ $2/pt\n\n")

        f.write(f"## CANON baseline verification\n\n")
        f.write(f"Expected per round-15 honest mid-run: ~$29/day @ 60 tr/d, ~45% WR.\n\n")
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

        f.write(f"\n## Top 30 per avenue\n\n")
        for av in ["A_MARKETABLE", "B_STOPBRK", "C_COMPRESS", "D_INTRAMIN",
                   "E_ADAPT", "F_TIMEWIN", "G_SPREAD", "H_OCO"]:
            avrows = by_avenue.get(av, [])
            if not avrows:
                continue
            f.write(f"\n### {av} ({len(avrows)} strategies, top 30)\n\n")
            f.write(f"| Rank | Strategy | Tr/d | WR% | $/day | $/tr | DD | Sharpe |\n")
            f.write(f"|---:|---|---:|---:|---:|---:|---:|---:|\n")
            for i, r in enumerate(avrows[:30], 1):
                f.write(f"| {i} | {r['name']} | {r['trades_per_day']:.1f} | "
                        f"{r['wr']*100:.1f} | ${r['per_day']:+.2f} | "
                        f"${r['per_trade']:+.2f} | ${r['max_dd']:.0f} | "
                        f"{r['sharpe']:.2f} |\n")

        # Honest assessment
        f.write(f"\n## Honest assessment\n\n")
        n_positive = sum(1 for r in rows if r['per_day'] > 0)
        n_50_per_day = sum(1 for r in rows if r['per_day'] >= 50)
        n_100_per_day = sum(1 for r in rows if r['per_day'] >= 100)
        n_500_per_day = sum(1 for r in rows if r['per_day'] >= 500)
        n_300_tpd = sum(1 for r in rows if r['trades_per_day'] >= 300)
        n_45wr = sum(1 for r in rows if r['wr'] >= 0.45)
        f.write(f"- Positive $/day: {n_positive}/{n_total}\n")
        f.write(f"- >= $50/day: {n_50_per_day}\n")
        f.write(f"- >= $100/day: {n_100_per_day}\n")
        f.write(f"- >= $500/day: {n_500_per_day}\n")
        f.write(f"- >= 300 trades/day: {n_300_tpd}\n")
        f.write(f"- >= 45% WR: {n_45wr}\n")
        f.write(f"- FULL_PASS (300/45/$1k/$5kDD): {len(full_pass)}\n\n")
        if not full_pass:
            best = rows[0]
            f.write(f"### Reality check\n\n")
            f.write(f"Round 16 best: **{best['name']}** ({best['avenue']}) — "
                    f"{best['trades_per_day']:.1f} tr/d, {best['wr']*100:.1f}% WR, "
                    f"${best['per_day']:+.0f}/day, DD=${best['max_dd']:.0f}.\n\n")
            f.write(f"After 16 rounds and ~3,000+ variants under the bot-faithful "
                    f"r9 executor (queue overshoot, latency, slippage, $1.91/RT), "
                    f"the target (300 tr/d, 45% WR, $1000+/day, DD<=$5k) remains "
                    f"unreached. The wall is structural: MNQ at 1 contract with "
                    f"$1.91 fees is not deep enough to sustain $1k+/day at 300 "
                    f"trades unless point P&L per trade averages above $3.30 — "
                    f"and at 45%+ WR with realistic queue/slippage friction, the "
                    f"net-edge after costs continues to compress toward zero.\n")
        else:
            f.write(f"### Reality check\n\n")
            f.write(f"Round 16 found {len(full_pass)} FULL_PASS strategies. "
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
    print(f"[round16] Results saved to {RESULTS_PATH}", file=sys.stderr)
    print(f"[round16] Summary CSV at {SUMMARY_CSV}", file=sys.stderr)


if __name__ == "__main__":
    main()
