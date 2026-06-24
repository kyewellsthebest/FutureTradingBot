"""Round 13 strategy search for MNQ — 500 targeted variants.

User mandate (round 13): bridge the volume gap. Round 12's top 20 had
52-55% WR but only 20-32 trades/day; need ~10x volume at same WR.

500 variants across 5 narrow avenues:
  1. RETEST: top 100 winners from round 12 partial (re-test on fresh ckpt)
  2. FAST: cooldown 1-3s / max_hold 30-60s on proven T_LH/B_ASH bases (100)
  3. ENSEMBLE: portfolio router across top-5 T_LH winners (100)
  4. MULTI_LIMIT (OCO): fire 4 LIMITs simultaneously at pp {0.118,0.236,
     0.382,0.500} from same impulse, first fill wins (100)
  5. WINDOW: NYO 13:30-15:30 UTC and CME-open 22:00-23:30 UTC only;
     dense param sweep inside these windows (100)

Execution model UNCHANGED from round 12 — bot-faithful: 1-tick queue
overshoot, 200ms latency, 10pt approach threshold, multi-setup lock,
0.5pt stop slip + 10% gap risk, configurable cooldown / max_hold.

Reporting: top 20 per fee/instrument, best 5 per avenue, any FULL_PASS,
limiting-dimension analysis if no passers.
"""
from __future__ import annotations
import argparse
import csv
import math
import os
import pickle
import random
import re
import sys
import time
from collections import defaultdict, deque
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

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
from research import round12_search as _r12
sys.modules.setdefault("round12_search", _r12)

# Reuse round-12 classes & constants
StrategyBase = _r4.StrategyBase
BarBuilder = _r4.BarBuilder
MarketablePullback = _r6.MarketablePullback
MTFConfluence = _r7.MTFConfluence
MARKET = _r8.MARKET
REGIME = _r9.REGIME

AntiStopHuntPullback = _r12.AntiStopHuntPullback

attach_r7_executor = _r7.attach_r7_executor
r10_bot_on_tick = _r10.r10_bot_on_tick

PATH = _r7.PATH
MNQ_PER_PT = _r7.MNQ_PER_PT
NQ_PER_PT = 20.0
COMM_RT = _r7.COMM_RT
FEE_FULL_RT = _r7.TOTAL_RT_COST
FEE_PROP_RT = COMM_RT

DEFAULT_OFFSET = 7_820_974_790
CHECKPOINT_EVERY_TICKS = 25_000

# Round-12 partial top file (we reconstruct top 100 from it)
PARTIAL_TOP_PATH = "/home/user/HFTBot/research/round12_partial_top.txt"

RNG = random.Random(0xCAFEBA13)


# =============================================================================
# Avenue 1 — RETEST: parse round-12 partial top file, rebuild strategies
# =============================================================================
def _session_of(tag):
    """Map session tag -> (start, end) tuple of (hh, mn) tuples or None."""
    return {
        'all':  (None, None),
        'NYO':  ((13, 30), (15, 30)),
        'OVR':  ((13, 30), (16, 0)),
        'RTH':  ((13, 30), (20, 0)),
        'CME':  ((22, 0), (5, 0)),
        'PRE':  ((12, 0), (13, 30)),
        'AFT':  ((16, 0), (20, 0)),
        'LDN':  ((8, 0), (12, 0)),
    }.get(tag, (None, None))


_RE_TLH = re.compile(
    r"^T_LH_(?P<base>CANONINV|R4INV|R10BASE)_imp(?P<imp>\d+)_b(?P<b>\d+)_"
    r"s(?P<s>\d+)_t(?P<t>\d+)_pp(?P<pp>\d+)_cd(?P<cd>\d+)_"
    r"mh(?P<mh>\w+?)_(?P<ses>all|NYO|OVR|RTH|CME|PRE|AFT|LDN)$"
)
_RE_BASH = re.compile(
    r"^B_ASH_off(?P<off>\d+)_imp(?P<imp>\d+)_b(?P<b>\d+)_"
    r"pp(?P<pp>\d+)_s(?P<s>\d+)t(?P<t>\d+)_(?P<inv>INV|TRD)$"
)


def _rebuild_t_lh(m, name_prefix='R'):
    """Rebuild a T_LH strategy from regex match. Returns strategy or None."""
    base = m.group('base')
    imp = float(m.group('imp'))
    b = int(m.group('b'))
    stp = int(m.group('s'))
    tgt = int(m.group('t'))
    pp = int(m.group('pp')) / 1000.0
    cd = int(m.group('cd'))
    mh = m.group('mh')
    ses = m.group('ses')
    if tgt <= stp:
        return None
    ses_start, ses_end = _session_of(ses)
    kwargs = dict(impulse_pts=imp, impulse_bars=b, pull_pct=pp,
                  stop_pts=stp, target_pts=tgt, invert=True,
                  cooldown_s=cd, session_start=ses_start, session_end=ses_end)
    if mh != 'd':
        try:
            kwargs['max_hold'] = int(mh)
        except ValueError:
            pass
    if base == 'CANONINV':
        cls = MarketablePullback
    else:
        cls = MTFConfluence
    try:
        new_name = f"{name_prefix}_T_LH_{base}_imp{int(imp)}_b{b}_s{stp}_t{tgt}_pp{int(pp*1000)}_cd{cd}_mh{mh}_{ses}"
        s = cls(new_name, **kwargs)
        return s
    except Exception:
        return None


def _rebuild_b_ash(m, name_prefix='R'):
    off = int(m.group('off')) / 100.0
    imp = float(m.group('imp'))
    b = int(m.group('b'))
    pp = int(m.group('pp')) / 1000.0
    stp = int(m.group('s'))
    tgt = int(m.group('t'))
    inv = m.group('inv') == 'INV'
    if tgt <= stp:
        return None
    new_name = f"{name_prefix}_B_ASH_off{int(off*100)}_imp{int(imp)}_b{b}_pp{int(pp*1000)}_s{stp}t{tgt}_{'INV' if inv else 'TRD'}"
    try:
        s = AntiStopHuntPullback(
            new_name, stop_offset_quirk=off,
            impulse_pts=imp, impulse_bars=b, pull_pct=pp,
            stop_pts=stp, target_pts=tgt, invert=inv)
        return s
    except Exception:
        return None


def build_retest_top100(path=PARTIAL_TOP_PATH, n_take=100):
    """Parse the round-12 partial top file and reconstruct as many of the
    top n_take strategies as possible. Returns list of strategies."""
    out = []
    parsed_top_names = []
    if not os.path.exists(path):
        return out, parsed_top_names
    with open(path) as f:
        for line in f:
            if line.startswith('#') or line.startswith('Round'):
                continue
            parts = line.split()
            if len(parts) < 6:
                continue
            name = parts[0]
            parsed_top_names.append(name)
            if name.startswith('T_LH_'):
                m = _RE_TLH.match(name)
                if m:
                    s = _rebuild_t_lh(m, name_prefix='RT')
                    if s is not None:
                        out.append(s)
            elif name.startswith('B_ASH_'):
                m = _RE_BASH.match(name)
                if m:
                    s = _rebuild_b_ash(m, name_prefix='RT')
                    if s is not None:
                        out.append(s)
            # Other archetypes (P_CG, S_OS, F_HB, D_SCF, O_RND...) are
            # too costly to reconstruct in 100 budget; we skip them.
            if len(out) >= n_take:
                break
    return out, parsed_top_names[:n_take]


# =============================================================================
# Avenue 2 — FAST: aggressive cooldown / max_hold sweep on proven bases
# =============================================================================
# Proven bases (extracted from round-12 top-15) — only the parameter
# 5-tuples (impulse, bars, pull_pct, stop, target).
PROVEN_T_LH_BASES = [
    (2.0, 2, 0.300, 8, 16),
    (4.0, 4, 0.118, 4, 28),
    (5.0, 4, 0.236, 12, 40),
    (3.0, 2, 0.500, 15, 50),
    (6.0, 4, 0.236, 8, 12),
    (3.0, 4, 0.500, 7, 16),
    (5.0, 2, 0.236, 10, 16),
    (3.0, 3, 0.236, 5, 50),
    (4.0, 8, 0.118, 10, 12),
    (4.0, 4, 0.300, 10, 28),
    (3.0, 6, 0.118, 10, 28),
    (7.0, 3, 0.300, 9, 50),
    (6.0, 3, 0.118, 7, 12),
    (2.0, 3, 0.382, 8, 32),
    (5.0, 5, 0.236, 8, 16),
]

PROVEN_B_ASH_BASES = [
    # (offset, imp, b, pp, s, t, inv)
    (1.12, 6.0, 4, 0.382, 10, 30, True),
    (0.87, 5.0, 3, 0.300, 8,  30, True),
    (1.12, 5.0, 3, 0.300, 8,  30, True),
    (1.37, 5.0, 3, 0.300, 8,  30, True),
    (0.37, 6.0, 4, 0.382, 10, 30, True),
    (0.13, 6.0, 4, 0.382, 10, 30, True),
    (0.63, 6.0, 4, 0.382, 10, 30, True),
    (1.37, 5.0, 4, 0.118, 4,  16, True),
    (0.13, 5.0, 4, 0.118, 4,  16, True),
]


def build_fast_variants(n_target=100):
    """Cooldown {1,2,3}s × max_hold {30,60}s × top-15 T_LH bases =
    90 variants; + 10 B_ASH fast variants. Total ~100."""
    out = []
    cds = [1, 2, 3]
    mhs = [30, 60]
    sessions = [('all', None, None), ('NYO', (13, 30), (15, 30))]
    for (imp, b, pp, stp, tgt) in PROVEN_T_LH_BASES:
        for cd in cds:
            for mh in mhs:
                ses_name, ss, se = sessions[0]  # all-session by default
                name = (f"FAST_T_imp{int(imp)}_b{b}_s{stp}_t{tgt}_pp{int(pp*1000)}_"
                        f"cd{cd}_mh{mh}_{ses_name}")
                try:
                    s = MarketablePullback(
                        name, impulse_pts=imp, impulse_bars=b, pull_pct=pp,
                        stop_pts=stp, target_pts=tgt, invert=True,
                        cooldown_s=cd, max_hold=mh,
                        session_start=ss, session_end=se)
                    out.append(s)
                    if len(out) >= n_target - 10:
                        break
                except Exception:
                    pass
            if len(out) >= n_target - 10:
                break
        if len(out) >= n_target - 10:
            break
    # B_ASH fast: top 5 × cd {1,2} × max_hold {30}
    b_cnt = 0
    for (off, imp, b, pp, stp, tgt, inv) in PROVEN_B_ASH_BASES:
        for cd in [1, 2]:
            name = (f"FAST_B_off{int(off*100)}_imp{int(imp)}_b{b}_"
                    f"pp{int(pp*1000)}_s{stp}t{tgt}_cd{cd}_mh30_"
                    f"{'INV' if inv else 'TRD'}")
            try:
                s = AntiStopHuntPullback(
                    name, stop_offset_quirk=off,
                    impulse_pts=imp, impulse_bars=b, pull_pct=pp,
                    stop_pts=stp, target_pts=tgt, invert=inv,
                    cooldown_s=cd, max_hold=30)
                out.append(s)
                b_cnt += 1
                if b_cnt >= 10 or len(out) >= n_target:
                    break
            except Exception:
                pass
        if b_cnt >= 10 or len(out) >= n_target:
            break
    return out[:n_target]


# =============================================================================
# Avenue 3 — ENSEMBLE: portfolio router across top-5 T_LH winners
# =============================================================================
class PortfolioRouter(StrategyBase):
    """Wraps N inner strategies. Each tick, drives all inner on_bar_close
    and aggregates their pending setups via a router rule.

    Routing rules:
      'round_robin'  — round-robin across inner strategies' setups
      'first_signal' — fire the next setup that arms
      'majority'     — only fire setups where >= K of N inner agree on side
      'recent_edge'  — prefer setups from the inner with best recent WR

    The ensemble keeps ONE in_trade at a time (StrategyBase semantics).
    Inner strategies' fills are NOT recorded; only the routed setups are.
    """
    # NOTE: no __slots__ so we get a __dict__ (need _exec from attach_r7_executor)

    def __init__(self, name, inner_strats, router_rule='first_signal',
                 majority_k=3, recent_window=20,
                 cooldown_s=5, max_hold=120,
                 session_start=None, session_end=None):
        super().__init__(name, cooldown_s=cooldown_s, max_hold=max_hold,
                         session_start=session_start, session_end=session_end)
        self._inner = list(inner_strats)
        self._router_rule = router_rule
        self._inner_idx = 0
        self._majority_k = majority_k
        self._recent_window = recent_window

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        # Drive each inner. Capture new pendings, then move them into
        # self.pending according to router rule.
        per_inner_new = []
        for inner in self._inner:
            n_before = len(inner.pending)
            try:
                inner.on_bar_close(ts, hh, mn, bo, bh, bl, bc, hist)
            except Exception:
                continue
            new = inner.pending[n_before:]
            per_inner_new.append(new)
        # Aggregate
        flat = []
        if self._router_rule == 'round_robin':
            # interleave
            max_len = max((len(x) for x in per_inner_new), default=0)
            for i in range(max_len):
                for new in per_inner_new:
                    if i < len(new):
                        flat.append(new[i])
        elif self._router_rule == 'majority':
            # Only adopt setups where K-of-N inner agree on side
            for setup in [s for inner in per_inner_new for s in inner]:
                side = setup['side']
                # Count other inner's new setups with same side
                same = sum(1 for inner_new in per_inner_new
                           for s in inner_new
                           if s['side'] == side)
                if same >= self._majority_k:
                    flat.append(setup)
        elif self._router_rule == 'recent_edge':
            # Best-WR-recent inner first
            scored = []
            for inner, new in zip(self._inner, per_inner_new):
                comp = inner.completed[-self._recent_window:]
                if comp:
                    wr = sum(1 for c in comp if c[0] > 0) / len(comp)
                else:
                    wr = 0.5
                scored.append((wr, new))
            scored.sort(key=lambda t: -t[0])
            for _, new in scored:
                flat.extend(new)
        else:  # first_signal
            for new in per_inner_new:
                flat.extend(new)
        # Adopt — but only first N to keep pending small (cap 6 outstanding)
        # Route through add_setup so the global active-set hook picks us up.
        for setup in flat[:6]:
            extra = {k: v for k, v in setup.items()
                     if k not in ('side', 'orig', 'entry', 'stop',
                                  'target', 'expires', 'used', 'key')}
            self.add_setup(setup['side'], setup.get('orig', setup['side']),
                           setup['entry'], setup['stop'], setup['target'],
                           ts, key=setup.get('key'),
                           expires_in=max(1, int(setup.get('expires', ts+300) - ts)),
                           extra=extra)
        # Clear inner pending so they don't fire independently
        for inner in self._inner:
            inner.pending = []
            inner.in_trade = None  # never let inner fire


def build_ensembles(n_target=100):
    """Build 100 ensemble strategies from top-5 T_LH bases × 5 routing rules
    × 4 subset sizes. We construct fresh underlying instances per ensemble."""
    out = []
    top5_bases = PROVEN_T_LH_BASES[:5]
    # For each ensemble, we create N inner strategies fresh
    rules = ['first_signal', 'round_robin', 'majority', 'recent_edge']
    subsets = [
        ('top3', PROVEN_T_LH_BASES[:3]),
        ('top5', PROVEN_T_LH_BASES[:5]),
        ('top7', PROVEN_T_LH_BASES[:7]),
        ('top10', PROVEN_T_LH_BASES[:10]),
        ('top15', PROVEN_T_LH_BASES[:15]),
    ]
    cd_mh_combos = [(2, 60), (3, 120), (5, 60), (5, 120), (10, 600)]
    for sub_name, subset in subsets:
        for rule in rules:
            for cd, mh in cd_mh_combos:
                if len(out) >= n_target:
                    break
                # Build inner strategies
                inners = []
                for i, (imp, b, pp, stp, tgt) in enumerate(subset):
                    iname = f"_ens_inner_{sub_name}_{rule}_{i}_cd{cd}mh{mh}"
                    try:
                        inner = MarketablePullback(
                            iname, impulse_pts=imp, impulse_bars=b,
                            pull_pct=pp, stop_pts=stp, target_pts=tgt,
                            invert=True, cooldown_s=cd, max_hold=mh)
                    except Exception:
                        continue
                    inners.append(inner)
                if not inners:
                    continue
                name = f"ENS_{sub_name}_{rule}_cd{cd}_mh{mh}"
                ens = PortfolioRouter(
                    name, inner_strats=inners, router_rule=rule,
                    majority_k=max(2, len(inners) // 2),
                    cooldown_s=cd, max_hold=mh)
                out.append(ens)
            if len(out) >= n_target:
                break
        if len(out) >= n_target:
            break
    return out[:n_target]


# =============================================================================
# Avenue 4 — MULTI_LIMIT (OCO): fire 4 LIMITs at pp {0.118,0.236,0.382,0.5}
# =============================================================================
class MultiLimitOCO(MarketablePullback):
    """Same impulse detection as MarketablePullback, but emits MULTIPLE
    setups per impulse — one per pull_pct level. Since StrategyBase
    allows only ONE in_trade, the first that fills wins (OCO)."""
    __slots__ = ('pull_pcts',)

    def __init__(self, name, pull_pcts=(0.118, 0.236, 0.382, 0.500),
                 **kwargs):
        # ignore parent's pull_pct (we use list); set base to first for parent init
        kwargs['pull_pct'] = float(pull_pcts[0])
        super().__init__(name, **kwargs)
        self.pull_pcts = tuple(pull_pcts)

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
        rng = ih - il
        if rng <= 0:
            return
        orig_side = "LONG" if net > 0 else "SHORT"
        side = ("SHORT" if orig_side == "LONG" else "LONG") if self.invert else orig_side
        if self.long_only and side != "LONG":
            return
        if self.short_only and side != "SHORT":
            return
        for pp in self.pull_pcts:
            if orig_side == "LONG":
                entry = ih - pp * rng
            else:
                entry = il + pp * rng
            if side == "LONG":
                stop = entry - self.stop_pts
                target = entry + self.target_pts
            else:
                stop = entry + self.stop_pts
                target = entry - self.target_pts
            key = ("mloco", round(ih, 1), round(il, 1), orig_side,
                   round(pp, 3))
            extra = {
                'fill_mode': 'marketable',
                'stop_offset_pts': self.stop_pts,
                'target_offset_pts': self.target_pts,
                'exit_mode': 'stop_market',
            }
            self.add_setup(side, orig_side, entry, stop, target, ts,
                           key=key, expires_in=300, extra=extra)


def build_multilimit(n_target=100):
    """Build 100 MultiLimitOCO variants on top-10 T_LH bases × pull-pct-set
    × cooldown × max_hold."""
    out = []
    pp_sets = [
        (0.118, 0.236, 0.382, 0.500),
        (0.236, 0.382, 0.500, 0.618),
        (0.118, 0.300, 0.500),
        (0.236, 0.382, 0.500),
        (0.118, 0.236, 0.382),
        (0.382, 0.500, 0.618, 0.764),
    ]
    cd_mh = [(3, 60), (5, 120), (10, 240), (15, 600)]
    bases = PROVEN_T_LH_BASES[:10]  # 10 bases
    # 10 × 6 × 4 = 240 — cap at 100 via early break
    for (imp, b, _pp, stp, tgt) in bases:
        for ppset in pp_sets:
            for cd, mh in cd_mh:
                if len(out) >= n_target:
                    break
                pp_tag = '-'.join(f"{int(p*1000)}" for p in ppset)
                name = (f"OCO_imp{int(imp)}_b{b}_s{stp}_t{tgt}_"
                        f"pp{pp_tag}_cd{cd}_mh{mh}")
                try:
                    s = MultiLimitOCO(
                        name, pull_pcts=ppset,
                        impulse_pts=imp, impulse_bars=b,
                        stop_pts=stp, target_pts=tgt, invert=True,
                        cooldown_s=cd, max_hold=mh)
                    out.append(s)
                except Exception:
                    pass
            if len(out) >= n_target:
                break
        if len(out) >= n_target:
            break
    return out[:n_target]


# =============================================================================
# Avenue 5 — WINDOW-bounded variants (NYO and CME-open)
# =============================================================================
def build_window_variants(n_target=100):
    """Dense parameter sweep restricted to high-liquidity windows:
       NYO 13:30-15:30 UTC and CME-open 22:00-23:30 UTC.
       Use aggressive cooldown/max_hold to maximize within-window volume."""
    out = []
    windows = [
        ('NYO',  (13, 30), (15, 30)),
        ('CMEO', (22, 0),  (23, 30)),
        ('LDNO', (8, 0),   (9, 30)),  # London open as bonus high-vol
    ]
    # Sweep grids — denser than baseline
    imps = [2.0, 3.0, 4.0, 5.0, 6.0]
    bars_list = [2, 3, 4]
    pps = [0.118, 0.236, 0.300, 0.382, 0.500]
    stps = [5, 8, 10]
    tgts = [12, 20, 30]
    cds = [2, 5]
    mhs = [60, 120]
    for ws_name, ws, we in windows:
        for imp in imps:
            for b in bars_list:
                for pp in pps:
                    for stp in stps:
                        for tgt in tgts:
                            if tgt <= stp:
                                continue
                            for cd in cds:
                                for mh in mhs:
                                    if len(out) >= n_target:
                                        break
                                    name = (f"WIN_{ws_name}_imp{int(imp)}_"
                                            f"b{b}_s{stp}_t{tgt}_"
                                            f"pp{int(pp*1000)}_cd{cd}_mh{mh}")
                                    try:
                                        s = MarketablePullback(
                                            name, impulse_pts=imp,
                                            impulse_bars=b, pull_pct=pp,
                                            stop_pts=stp, target_pts=tgt,
                                            invert=True, cooldown_s=cd,
                                            max_hold=mh,
                                            session_start=ws,
                                            session_end=we)
                                        out.append(s)
                                    except Exception:
                                        pass
                                if len(out) >= n_target:
                                    break
                            if len(out) >= n_target:
                                break
                        if len(out) >= n_target:
                            break
                    if len(out) >= n_target:
                        break
                if len(out) >= n_target:
                    break
            if len(out) >= n_target:
                break
        if len(out) >= n_target:
            break
    return out[:n_target]


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
        print(f"[round13] checkpoint load failed: {e!r}", file=sys.stderr)
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
# BUILD ALL
# =============================================================================
def build_all_variants(scale=1.0):
    """Build variants across 5 avenues. scale=1.0 -> 500 variants;
    scale=0.4 -> ~200 variants (same distribution).
    """
    n100 = max(20, int(100 * scale))
    print(f"[round13] building variants (scale={scale}, "
          f"target {5*n100})...", file=sys.stderr)
    retest, parsed = build_retest_top100(n_take=n100)
    print(f"[round13] avenue 1 RETEST: {len(retest)} strategies "
          f"(from {len(parsed)} parsed names)", file=sys.stderr)
    fast = build_fast_variants(n_target=n100)
    print(f"[round13] avenue 2 FAST: {len(fast)} strategies", file=sys.stderr)
    ensembles = build_ensembles(n_target=n100)
    print(f"[round13] avenue 3 ENSEMBLE: {len(ensembles)} strategies",
          file=sys.stderr)
    multilim = build_multilimit(n_target=n100)
    print(f"[round13] avenue 4 MULTI_LIMIT: {len(multilim)} strategies",
          file=sys.stderr)
    windows = build_window_variants(n_target=n100)
    print(f"[round13] avenue 5 WINDOW: {len(windows)} strategies",
          file=sys.stderr)
    all_strats = retest + fast + ensembles + multilim + windows
    # Tag each with avenue prefix for reporting
    by_avenue = {
        'RETEST': retest,
        'FAST':   fast,
        'ENS':    ensembles,
        'OCO':    multilim,
        'WIN':    windows,
    }
    return all_strats, by_avenue


def _avenue_of(name):
    if name.startswith('RT_'):     return 'RETEST'
    if name.startswith('FAST_'):   return 'FAST'
    if name.startswith('ENS_'):    return 'ENS'
    if name.startswith('OCO_'):    return 'OCO'
    if name.startswith('WIN_'):    return 'WIN'
    return 'OTHER'


# =============================================================================
# MAIN
# =============================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offset", type=int, default=DEFAULT_OFFSET)
    ap.add_argument("--ckpt-suffix", default="")
    ap.add_argument("--max-days", type=int, default=60)
    ap.add_argument("--scale", type=float, default=1.0,
                    help="Variant-count scale (1.0=500, 0.4=200)")
    args = ap.parse_args()

    ckpt_path = ("/home/user/HFTBot/research/round13_checkpoint"
                 f"{args.ckpt_suffix}.pkl")
    csv_path = ("/home/user/HFTBot/research/round13_summary"
                f"{args.ckpt_suffix}.csv")
    md_path = "/home/user/HFTBot/research/round13_results.md"

    all_strats, by_avenue = build_all_variants(scale=args.scale)
    for s in all_strats:
        attach_r7_executor(s)
    print(f"[round13] Built {len(all_strats):,} strategies", file=sys.stderr)

    # OPTIMIZATION: active set for fast iteration
    _ACTIVE = set()
    _ACTIVE_LOOKUP = {id(s): s for s in all_strats}
    _orig_add_setup = StrategyBase.add_setup

    def _patched_add_setup(self, *args, **kwargs):
        _orig_add_setup(self, *args, **kwargs)
        sid = id(self)
        # Only track top-level strategies — inner ensemble strategies are
        # not in the lookup map and must not be iterated by the main loop.
        if sid in _ACTIVE_LOOKUP:
            _ACTIVE.add(sid)
    StrategyBase.add_setup = _patched_add_setup

    resumed = load_checkpoint(ckpt_path, all_strats)
    if resumed is not None:
        start_offset, day_counter, last_day_key = resumed
        booked = sum(s.n_trades for s in all_strats)
        print(f"[round13] RESUMING from offset {start_offset:,} "
              f"day_counter={day_counter} ({booked:,} trades booked)",
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
    print(f"[round13] file size: {file_size:,} bytes", file=sys.stderr)
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
                    save_checkpoint(ckpt_path, pos, day_counter, last_day_key,
                                    all_strats)
                except Exception as e:
                    print(f"  [round13] ckpt save failed: {e!r}", file=sys.stderr)
                print(f"  [round13] {n_lines/1e6:.1f}M ticks rate={rate/1e6:.2f}M/s "
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

            # Gauges (MARKET / REGIME suffice for our 500 variants — none
            # depend on round-12's MSM/TICK_RATE/BAP/SUB_TICK_BUF/SWHL).
            MARKET.feed_tick(ts, last, bid, ask)

            if bb_1m.on_tick(ts, last):
                closed = bb_1m.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    MARKET.feed_bar(o, h, l, c)
                    REGIME.feed_bar(o, h, l, c)
                    for s in all_strats:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_1m.history)

            # Active-set tick — only iterate strategies with pending/open
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
    print(f"\n[round13] DONE in {elapsed/60:.1f}min, {n_lines:,} ticks, "
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
            "name", "avenue", "trades", "trades_per_day", "wr",
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
                n, _avenue_of(n), r['n'], f"{r['trades_per_day']:.1f}",
                f"{r['wr']:.4f}",
                f"{r['per_day']:.2f}", f"{r74['per_day']:.2f}",
                f"{rnq['per_day']:.2f}", f"{rnq74['per_day']:.2f}",
                f"{r['per_trade']:.3f}",
                f"{r['max_dd']:.2f}", f"{r74['max_dd']:.2f}",
                f"{r['sharpe']:.3f}", f"{r74['sharpe']:.3f}",
                r['n_days'], r['pos_d'], r['neg_d'],
            ])
    print(f"[round13] wrote CSV {csv_path}", file=sys.stderr)

    def is_pass(r):
        return (r['trades_per_day'] >= 300 and r['wr'] >= 0.45
                and r['per_day'] >= 1000 and r['max_dd'] <= 5000)

    pass_191 = [r for r in rows_191 if is_pass(r)]
    pass_074 = [r for r in rows_074 if is_pass(r)]
    pass_nq_191 = [r for r in rows_nq_191 if is_pass(r)]
    pass_nq_074 = [r for r in rows_nq_074 if is_pass(r)]

    by_dir = defaultdict(list)
    for r in rows_191:
        by_dir[_avenue_of(r['name'])].append(r)

    # =========================================================================
    # MARKDOWN
    # =========================================================================
    L = []
    L.append("# Round 13 strategy search — 500 targeted variants\n\n")
    L.append(f"Generated: {datetime.now().isoformat()}\n")
    L.append(f"Period: {total_days} calendar-day buckets from offset "
             f"{args.offset:,} (max-days={args.max_days})\n")
    L.append(f"Tick stream: {n_lines:,} lines processed\n")
    L.append(f"Strategies tested: {len(all_strats):,}\n\n")
    L.append("## Avenues\n\n")
    for av, strats in by_avenue.items():
        L.append(f"- **{av}** -- {len(strats)} variants\n")
    L.append("\n")

    L.append("## Execution model\n\n")
    L.append("Bot-faithful: queue overshoot by 1 tick (LIMIT), 200ms latency, "
             "10pt approach threshold, multi-setup lock, 0.5pt stop slip + "
             "10% gap risk; cooldown/max_hold are per-variant overrides "
             "(round 13 ranges: cd=1..30s, mh=30..600s).\n\n")
    L.append("Fees: **$1.91/RT** vs **$0.74/RT** (prop-firm). "
             "Instruments: MNQ ($2/pt) and NQ ($20/pt).\n\n")

    L.append("## Hard requirements\n")
    L.append("- 300+ trades/day average\n- 45%+ WR\n- $1,000+ $/day\n"
             "- maxDD <= $5,000\n\n")

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
                         f"({r['trades_per_day']:.1f}/day), "
                         f"WR={r['wr']*100:.1f}%, "
                         f"${r['per_day']:,.0f}/day, DD=${r['max_dd']:,.0f}, "
                         f"Sharpe={r['sharpe']:.2f}\n")

    L.append("\n## Section 2 — Top 20 by $/day MNQ $1.91\n\n")
    L.append("| Rank | Strategy | Av | Tr | Tr/d | WR% | $/d 191 | $/d 074 | "
             "$/d NQ074 | DD | Sharpe |\n")
    L.append("|---:|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for i, r in enumerate(rows_191[:20], 1):
        n = r['name']
        r74 = rows_074_by_name[n]
        rnq74 = nq074_by[n]
        L.append(
            f"| {i} | {n} | {_avenue_of(n)} | {r['n']:,} | "
            f"{r['trades_per_day']:.1f} | {r['wr']*100:.1f} | "
            f"${r['per_day']:,.0f} | ${r74['per_day']:,.0f} | "
            f"${rnq74['per_day']:,.0f} | "
            f"${r['max_dd']:,.0f} | {r['sharpe']:.2f} |\n")

    L.append("\n## Section 3 — Top 20 by MNQ $0.74 (prop-firm)\n\n")
    L.append("| Rank | Strategy | Av | Tr/d | WR% | $/d 074 | DD | Sharpe |\n")
    L.append("|---:|---|:---:|---:|---:|---:|---:|---:|\n")
    for i, r in enumerate(rows_074[:20], 1):
        L.append(f"| {i} | {r['name']} | {_avenue_of(r['name'])} | "
                 f"{r['trades_per_day']:.1f} | {r['wr']*100:.1f} | "
                 f"${r['per_day']:,.0f} | ${r['max_dd']:,.0f} | "
                 f"{r['sharpe']:.2f} |\n")

    L.append("\n## Section 4 — Top 20 NQ-equivalent (best of NQ$0.74 vs NQ$1.91)\n\n")
    # combined NQ best per strategy
    nq_combined = []
    for r in rows_nq_191:
        n = r['name']
        v_191 = r['per_day']
        v_074 = nq074_by[n]['per_day']
        if v_074 > v_191:
            nq_combined.append((v_074, '074', nq074_by[n]))
        else:
            nq_combined.append((v_191, '191', r))
    nq_combined.sort(reverse=True, key=lambda x: x[0])
    L.append("| Rank | Strategy | Av | Tr/d | WR% | Best NQ $/d | Fee | DD |\n")
    L.append("|---:|---|:---:|---:|---:|---:|:---:|---:|\n")
    for i, (val, lab, r) in enumerate(nq_combined[:20], 1):
        L.append(f"| {i} | {r['name']} | {_avenue_of(r['name'])} | "
                 f"{r['trades_per_day']:.1f} | {r['wr']*100:.1f} | "
                 f"${val:,.0f} | NQ${lab} | ${r['max_dd']:,.0f} |\n")

    L.append("\n## Section 5 — Best 5 per avenue ($1.91 MNQ baseline)\n\n")
    for av in ['RETEST', 'FAST', 'ENS', 'OCO', 'WIN']:
        items = sorted(by_dir.get(av, []), key=lambda r: -r['per_day'])[:5]
        L.append(f"\n### {av} (top 5)\n")
        if not items:
            L.append("- (no strategies in this avenue)\n")
            continue
        for r in items:
            L.append(f"- **{r['name']}** -- {r['n']:,} tr "
                     f"({r['trades_per_day']:.1f}/d), "
                     f"WR={r['wr']*100:.1f}%, "
                     f"${r['per_day']:,.0f}/d, DD=${r['max_dd']:,.0f}\n")

    L.append("\n## Section 6 — Per-avenue summary\n\n")
    L.append("| Avenue | n_strats | Best $/d 191 | Best $/d 074 | "
             "Best $/d NQ074 | Top strat |\n")
    L.append("|---|---:|---:|---:|---:|---|\n")
    for av in ['RETEST', 'FAST', 'ENS', 'OCO', 'WIN']:
        items = by_dir.get(av, [])
        if not items:
            L.append(f"| {av} | 0 | - | - | - | - |\n")
            continue
        b191 = max(items, key=lambda r: r['per_day'])
        b074 = max((rows_074_by_name[r['name']] for r in items),
                   key=lambda r: r['per_day'])
        bnq074 = max((nq074_by[r['name']] for r in items),
                     key=lambda r: r['per_day'])
        L.append(f"| {av} | {len(items)} | ${b191['per_day']:,.0f} | "
                 f"${b074['per_day']:,.0f} | ${bnq074['per_day']:,.0f} | "
                 f"{b191['name']} |\n")

    # =========================================================================
    # Section 7 — limiting-dimension diagnosis (only if no passers)
    # =========================================================================
    n_pass_total = (len(pass_191) + len(pass_074) +
                    len(pass_nq_191) + len(pass_nq_074))
    L.append("\n## Section 7 — Limiting-dimension analysis\n\n")
    if n_pass_total > 0:
        L.append(f"**{n_pass_total} passing rows across all fee/instrument "
                 f"settings.** Recommend out-of-sample validation on a held-"
                 f"out window before deployment.\n")
    else:
        # Identify which dimension blocks the most strategies
        # Reqs: tr/d >=300, wr>=0.45, per_day >=1000, dd<=5000
        n_tr_fail  = sum(1 for r in rows_191 if r['trades_per_day'] < 300)
        n_wr_fail  = sum(1 for r in rows_191 if r['wr'] < 0.45)
        n_pd_fail  = sum(1 for r in rows_191 if r['per_day'] < 1000)
        n_dd_fail  = sum(1 for r in rows_191 if r['max_dd'] > 5000)
        n_tr_only  = sum(1 for r in rows_191
                         if r['trades_per_day'] < 300
                         and r['wr'] >= 0.45 and r['max_dd'] <= 5000)
        # Volume-bridged: if cd→1s halved cd→3s, did tr/d go up? Compare
        # FAST avenue (cd 1-3s, mh 30-60s) trades/day vs RETEST (mostly
        # cd 10-30s).
        fast_tpd = ([r['trades_per_day'] for r in by_dir.get('FAST', [])] or
                    [0.0])
        retest_tpd = ([r['trades_per_day']
                       for r in by_dir.get('RETEST', [])] or [0.0])
        win_tpd = ([r['trades_per_day'] for r in by_dir.get('WIN', [])] or
                   [0.0])
        oco_tpd = ([r['trades_per_day'] for r in by_dir.get('OCO', [])] or
                   [0.0])
        ens_tpd = ([r['trades_per_day'] for r in by_dir.get('ENS', [])] or
                   [0.0])
        med_fast = sorted(fast_tpd)[len(fast_tpd)//2]
        med_retest = sorted(retest_tpd)[len(retest_tpd)//2]
        med_win = sorted(win_tpd)[len(win_tpd)//2]
        med_oco = sorted(oco_tpd)[len(oco_tpd)//2]
        med_ens = sorted(ens_tpd)[len(ens_tpd)//2]

        # WR at high volume: among strategies with tr/d >= 50, what's
        # average WR?
        high_vol = [r for r in rows_191 if r['trades_per_day'] >= 50]
        avg_wr_high = (sum(r['wr'] for r in high_vol) / len(high_vol)
                       if high_vol else 0.0)
        L.append("**No FULL_PASS strategies found in round 13.** "
                 "Failure analysis:\n\n")
        L.append(f"- Strategies failing trades/day >=300:  {n_tr_fail}/"
                 f"{len(rows_191)}\n")
        L.append(f"- Strategies failing WR >=45%:          {n_wr_fail}/"
                 f"{len(rows_191)}\n")
        L.append(f"- Strategies failing $/d >=1000:        {n_pd_fail}/"
                 f"{len(rows_191)}\n")
        L.append(f"- Strategies failing maxDD <=5000:      {n_dd_fail}/"
                 f"{len(rows_191)}\n")
        L.append(f"- Failing ONLY the volume gate (tr/d): {n_tr_only}\n\n")
        L.append(f"**Median trades/day by avenue:**\n")
        L.append(f"- RETEST {med_retest:.1f}, FAST {med_fast:.1f}, "
                 f"WIN {med_win:.1f}, OCO {med_oco:.1f}, ENS {med_ens:.1f}\n\n")
        L.append(f"**Avg WR among high-volume (>=50 tr/d) strategies:** "
                 f"{avg_wr_high*100:.1f}%\n\n")

        L.append("### Limiting dimension\n\n")
        # heuristic: trades/day is the killer
        if n_tr_fail > 0.8 * len(rows_191):
            L.append("**LIMITING DIMENSION: TRADES/DAY.** Even with cd=1s "
                     "and max_hold=30s on top-15 bases (FAST avenue) and "
                     "4-way OCO multi-LIMIT, median trades/day "
                     f"is {med_fast:.1f} / {med_oco:.1f}. The intrinsic "
                     "signal rate of impulse-pullback patterns at the "
                     "tested impulse_pts/bars combinations does not "
                     "exceed ~50 events per day per archetype.\n\n")
            L.append("### Round 14 proposal — targeted at volume gap\n\n")
            L.append("1. **Lower impulse threshold further**: impulse_pts "
                     "in {1.0, 1.5, 2.0} with impulse_bars {1, 2}. Round "
                     "13 minimum was 2.0pt × 2 bars. Going to 1.0pt × 1 "
                     "bar increases per-day signal count ~5-10x.\n")
            L.append("2. **Tick-bar replacement for 1m**: rebuild "
                     "BarBuilder at 100-tick granularity (vs 60s). Same "
                     "impulse-pullback logic but ~30x more bars/day.\n")
            L.append("3. **Multi-strategy parallel execution**: instead "
                     "of OCO (one wins), allow up to K simultaneous "
                     "positions on independent setups (still 1 MNQ each, "
                     "but K different impulses). Requires harness "
                     "extension (in_trade -> in_trades list).\n")
            L.append("4. **Drop pullback gate**: enter at marketable on "
                     "impulse-end, no pullback wait — much higher fill "
                     "rate but WR likely drops to ~50%.\n")
        elif n_wr_fail > 0.5 * len(rows_191):
            L.append("**LIMITING DIMENSION: WIN RATE.** Many strategies "
                     "trade enough but don't win >=45%. Round 14 should "
                     "add WR-improving gates (HTF confluence, ATR filter, "
                     "regime classifier) on top of high-volume bases.\n")
        elif n_dd_fail > 0.5 * len(rows_191):
            L.append("**LIMITING DIMENSION: DRAWDOWN.** Tighter stops or "
                     "early-exit (BE / trail / time-decay) variants would "
                     "address this. Round 14 should focus on exit-side.\n")
        else:
            L.append("Mixed failures — no single dominant dimension. "
                     "Round 14 should run multi-objective Pareto across "
                     "(per_day, sharpe, -dd).\n")

    L.append("\n## Section 8 — Full strategy table (top 100 by $/day MNQ $1.91)\n\n")
    L.append("| Strategy | Av | Tr | Tr/d | WR% | $/d 191 | $/d 074 | "
             "$/d NQ191 | $/d NQ074 | DD | Sharpe |\n")
    L.append("|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for r in rows_191[:100]:
        n = r['name']
        r74 = rows_074_by_name[n]
        rnq = nq191_by[n]
        rnq74 = nq074_by[n]
        L.append(f"| {n} | {_avenue_of(n)} | {r['n']:,} | "
                 f"{r['trades_per_day']:.1f} | "
                 f"{r['wr']*100:.1f} | ${r['per_day']:,.0f} | "
                 f"${r74['per_day']:,.0f} | ${rnq['per_day']:,.0f} | "
                 f"${rnq74['per_day']:,.0f} | ${r['max_dd']:,.0f} | "
                 f"{r['sharpe']:.2f} |\n")

    with open(md_path, "w") as mf:
        mf.write("".join(L))
    print(f"[round13] wrote MD {md_path}", file=sys.stderr)

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
            print(f"[round13] cleared checkpoint {ckpt_path}", file=sys.stderr)
    except Exception:
        pass


if __name__ == "__main__":
    main()
