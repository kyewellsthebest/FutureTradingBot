"""Round 9 strategy search for MNQ — five-angle attack.

After 8 rounds and 1,500+ variants, the only 60d-positive strategy under
$1.91/RT execution is B04_CANON_bal_n300_t30 at +$3/day. Round 9
attacks the problem from five fresh angles simultaneously, in a SINGLE
coordinated pass over the 60-day tick stream:

  A. Prop-firm fee structure ($0.74/RT only). Track per-trade P&L under
     BOTH $1.91 and $0.74 fee models in parallel.
  B. Walk-forward parameter optimization across four ~15-day blocks
     (0-14, 15-29, 30-44, 45-53). For each block-2..4, the optimal
     parameter from the prior block is deployed.
  C. Regime-switching meta-strategy. Each tick we recompute:
        - Hurst (trending / mean-reverting)
        - Choppiness Index (range-bound / directional)
        - realized vol (high / low) from 20-bar range
     -> 2*2*2 = 8 regime cells. We tag every completed trade with the
        cell at signal-gen time. Post-pass: pick the BEST strategy per
        cell and sum cell-best P&Ls into a meta-strategy.
  D. NQ vs MNQ economics. NQ has 10x point value vs MNQ; fees stay
     ~constant per contract. Reported as P&L_pts*$20 minus fees (same
     $1.91 or $0.74). Multiply at report time.
  E. Constraint relaxation analysis. Bin variants by (volume tier,
     WR tier) and report the per-bin max $/day under both fee models.

Implementation rules:
  - Use round8_search as the library for strategy classes & MARKET state
  - Keep the BOT-FAITHFUL r7 executor (queue overshoot, 200ms latency,
    10pt approach threshold, multi-setup lock, $1.91 RT or $0.74 RT cost,
    0.5pt stop slip + 10% gap risk, 10s cooldown, 600s max hold)
  - For booking: hook into the executor so each completed trade records
    a RICH tuple (pnl_pts, reason, day_counter, block_idx, regime_cell).
    Cost is applied at REPORT TIME so both fee models are derivable.
  - 100K-tick checkpoint for resume safety
  - Curated strategy library (~150 variants — not 250+): the bot-faithful
    full 60d pass on the FULL tick stream takes ~45-60 minutes per 100
    strategies; we trim to the highest-signal variants.

Outputs:
  - research/round9_results.md
  - research/round9_summary.csv
  - research/round9_checkpoint.pkl
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

# Reuse the full lineage for execution + classes.
from research import round4_search as _r4
sys.modules.setdefault("round4_search", _r4)
from research import round6_search as _r6
sys.modules.setdefault("round6_search", _r6)
from research import round7_search as _r7
sys.modules.setdefault("round7_search", _r7)
from research import round8_search as _r8
sys.modules.setdefault("round8_search", _r8)

# Classes
StrategyBase = _r4.StrategyBase
BarBuilder = _r4.BarBuilder
PullbackStrategy = _r4.PullbackStrategy
MarketablePullback = _r6.MarketablePullback
MTFConfluence = _r7.MTFConfluence
VolRegimePullback = _r7.VolRegimePullback
StopRunReversal = _r7.StopRunReversal
GatedMTFInvert = _r8.GatedMTFInvert
GatedCanonPullback = _r8.GatedCanonPullback
UlcerGatedMTF = _r8.UlcerGatedMTF
MarketContext = _r8.MarketContext
MARKET = _r8.MARKET  # singleton

attach_r7_executor = _r7.attach_r7_executor

# Execution constants (mirror r7/r8).
PATH = _r7.PATH
MNQ_PER_PT = _r7.MNQ_PER_PT
NQ_PER_PT = 20.0
COMM_RT = _r7.COMM_RT             # 0.74
EXCH_FEES_RT = _r7.EXCH_FEES_RT   # 1.17
FEE_FULL_RT = _r7.TOTAL_RT_COST   # 1.91 (broker + exchange)
FEE_PROP_RT = COMM_RT             # 0.74 (prop firm rebated)

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

# Round-9 offset: 60-day window ending at file tail (matches round8 retest).
DEFAULT_OFFSET = 7_820_974_790
CHECKPOINT_EVERY_TICKS = 100_000

# Walk-forward block bounds (day_counter values).
BLOCK_BOUNDS = [(0, 14), (15, 29), (30, 44), (45, 60)]
N_BLOCKS = len(BLOCK_BOUNDS)


def block_idx_for_day(d):
    if d < 0:
        return -1
    for i, (lo, hi) in enumerate(BLOCK_BOUNDS):
        if lo <= d <= hi:
            return i
    return -1


# RNG — use round7's so state is consistent across re-runs.
RNG = _r7.RNG


# =============================================================================
# REGIME ENGINE
# =============================================================================
# Recompute regime cells on each bar close. Strategies query
# REGIME.current_cell() at signal-gen time and tag setups so we can later
# carve out per-cell P&L.
class RegimeEngine:
    """Three binary regimes on 1m bars:
       - Hurst exponent over last 64 bars: H>=0.55 trending, else mean-revert
       - Choppiness Index over last 14 bars: CI>=55 choppy, else directional
       - Realized vol: current 20-bar mean ATR; high if above 60-bar median
    Combined cell index 0..7 encodes (hurst_bit, chop_bit, vol_bit).
    """
    def __init__(self):
        self._closes = deque(maxlen=80)
        self._ranges = deque(maxlen=70)
        self._atr_window = deque(maxlen=20)
        self._mean_atr_buf = deque(maxlen=60)
        self._cell = 0
        self.last_cell = 0
        self.cell_hist = []
        # For Choppiness
        self._tr_buf = deque(maxlen=14)
        self._hh_buf = deque(maxlen=14)
        self._ll_buf = deque(maxlen=14)
        self._prev_close = None

    def feed_bar(self, bo, bh, bl, bc):
        rng = bh - bl
        self._ranges.append(rng)
        self._closes.append(bc)
        # ATR using bar range
        self._atr_window.append(rng)
        if len(self._atr_window) >= 5:
            mean_atr = sum(self._atr_window) / len(self._atr_window)
            self._mean_atr_buf.append(mean_atr)
        # True range / hi / lo bookkeeping for choppiness
        if self._prev_close is not None:
            tr = max(rng, abs(bh - self._prev_close), abs(bl - self._prev_close))
        else:
            tr = rng
        self._tr_buf.append(tr)
        self._hh_buf.append(bh)
        self._ll_buf.append(bl)
        self._prev_close = bc

        # Hurst over last 64 closes
        h_bit = self._hurst_bit()
        c_bit = self._chop_bit()
        v_bit = self._vol_bit()
        self._cell = (h_bit << 2) | (c_bit << 1) | v_bit
        self.last_cell = self._cell

    def _hurst_bit(self):
        if len(self._closes) < 32:
            return 0
        ys = list(self._closes)
        try:
            rs = []
            for k in [len(ys) // 4, len(ys) // 2, len(ys)]:
                if k < 8:
                    continue
                sub = ys[-k:]
                mean = sum(sub) / len(sub)
                dev = [x - mean for x in sub]
                cum = 0.0; mn = 0.0; mx = 0.0
                for d in dev:
                    cum += d
                    if cum > mx: mx = cum
                    if cum < mn: mn = cum
                rng = mx - mn
                std = math.sqrt(sum((x - mean) ** 2 for x in sub) / len(sub))
                if std > 0 and rng > 0:
                    rs.append((math.log(k), math.log(rng / std)))
            if len(rs) < 2:
                return 0
            xs = [r[0] for r in rs]
            ysv = [r[1] for r in rs]
            mx = sum(xs) / len(xs)
            my = sum(ysv) / len(ysv)
            num = sum((xs[i] - mx) * (ysv[i] - my) for i in range(len(rs)))
            den = sum((xs[i] - mx) ** 2 for i in range(len(rs)))
            H = num / den if den > 0 else 0.5
        except Exception:
            H = 0.5
        return 1 if H >= 0.55 else 0

    def _chop_bit(self):
        if len(self._tr_buf) < 14:
            return 0
        atr_sum = sum(self._tr_buf)
        hh_v = max(self._hh_buf)
        ll_v = min(self._ll_buf)
        rng = hh_v - ll_v
        if rng <= 0 or atr_sum <= 0:
            return 0
        try:
            ci = 100.0 * math.log10(atr_sum / rng) / math.log10(14)
        except Exception:
            return 0
        return 1 if ci >= 55 else 0

    def _vol_bit(self):
        if len(self._mean_atr_buf) < 10:
            return 0
        atr_now = self._mean_atr_buf[-1]
        sub = sorted(self._mean_atr_buf)
        med = sub[len(sub) // 2]
        return 1 if atr_now >= med else 0

    def current_cell(self):
        return self._cell

    @staticmethod
    def cell_label(c):
        h = "T" if (c >> 2) & 1 else "R"
        ch = "C" if (c >> 1) & 1 else "D"
        v = "H" if c & 1 else "L"
        return f"{h}{ch}{v}"


REGIME = RegimeEngine()


# =============================================================================
# RICH BOOKING: re-implement r7_bot_on_tick with extended completed tuple.
# Each completed trade is recorded as:
#    (pnl_pts, reason, day_counter, block_idx, regime_cell)
# Cost is APPLIED AT REPORT TIME (so both fee models derive from same trace).
# =============================================================================
def r9_bot_on_tick(strat, ts, bid, ask, day_counter, hh, mn, last_px):
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

        # Trailing-stop
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
        # Breakeven trigger
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
        # Time-decay
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
        # Momentum shift
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
        # Stop / target / max-hold
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
            # Rich tuple: pnl_pts, reason, day_counter, block, regime_cell
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

    # Compute stop/target relative to fill_px (not entry_px_target)
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
        'time_decay': s.get('time_decay'),
        'momshift_k': s.get('momshift_k'),
        'regime_cell': REGIME.current_cell(),
    }
    exe.active_limit_key = None
    exe.active_limit_armed_ts = None


# =============================================================================
# CURATED VARIANT LIBRARY
# =============================================================================
# We re-test the top finishers from round 4, the round-8 14d winners,
# and the most-promising round-7 candidates — plus a tighter walk-forward
# CANON parameter grid for analysis B.
def _set_sess(strat, session_start=None, session_end=None):
    strat.session_start = session_start
    strat.session_end = session_end


def build_round9_variants():
    """Returns (v1m, v15s, v30s, vtick, aux, wf_groups, n_total).
    wf_groups is a dict {group_name: [strategies sharing param family]} for
    walk-forward analysis B.
    """
    v1m = []
    v15s = []
    v30s = []
    vtick = []
    wf_groups = defaultdict(list)

    # =========================================================================
    # Top round-4 idealized winners (re-tested under bot-faithful)
    # =========================================================================
    # These were the highest $/day at IDEALIZED (mid-price fill, no queue,
    # no latency). Round 4 numbers DO NOT survive friction — re-running
    # them under round-7 executor at both $1.91 and $0.74 fee models tells
    # us whether the prop-firm fee structure can rescue ANY of them.
    R4_PARAMS = [
        # name, pp, stop, tgt, imp
        ("R4_INV15s_imp2_s4t12",  None, 4, 12, 2.0, "15s"),
        ("R4_INV15s_imp2_s3t12",  None, 3, 12, 2.0, "15s"),
        ("R4_INV15s_imp2_s2t10",  None, 2, 10, 2.0, "15s"),
        ("R4_INV15s_imp2_s3t9",   None, 3, 9,  2.0, "15s"),
        ("R4_INV15s_imp2_s2t8",   None, 2, 8,  2.0, "15s"),
        ("R4_INV30s_imp3_s4t12",  None, 4, 12, 3.0, "30s"),
        ("R4_INV30s_imp3_s3t12",  None, 3, 12, 3.0, "30s"),
        ("R4_INV30s_imp3_s3t9",   None, 3, 9,  3.0, "30s"),
        ("R4_INV30s_imp3_s2t10",  None, 2, 10, 3.0, "30s"),
        ("R4_INV_pp118_s5t20_imp3", 0.118, 5, 20, 3.0, "1m"),
        ("R4_INV_pp118_s4t16_imp3", 0.118, 4, 16, 3.0, "1m"),
        ("R4_INV_pp118_s3t15_imp3", 0.118, 3, 15, 3.0, "1m"),
        ("R4_INV_pp118_s5t20_imp5", 0.118, 5, 20, 5.0, "1m"),
        ("R4_INV_pp118_s3t12_imp3", 0.118, 3, 12, 3.0, "1m"),
        ("R4_INV_pp118_s4t16_imp5", 0.118, 4, 16, 5.0, "1m"),
        ("R4_INV_pp118_s2t12_imp3", 0.118, 2, 12, 3.0, "1m"),
        ("R4_INV_pp236_s5t20_imp3", 0.236, 5, 20, 3.0, "1m"),
        ("R4_INV_pp236_s5t20_imp5", 0.236, 5, 20, 5.0, "1m"),
        ("R4_INV_pp236_s4t16_imp3", 0.236, 4, 16, 3.0, "1m"),
        ("R4_INV_pp236_s3t15_imp3", 0.236, 3, 15, 3.0, "1m"),
        ("R4_INV_pp236_s3t12_imp3", 0.236, 3, 12, 3.0, "1m"),
        ("R4_INV_pp236_s4t16_imp5", 0.236, 4, 16, 5.0, "1m"),
        ("R4_INV_pp382_s5t20_imp3", 0.382, 5, 20, 3.0, "1m"),
        ("R4_INV_pp382_s4t16_imp3", 0.382, 4, 16, 3.0, "1m"),
        ("R4_INV_pp382_s5t20_imp5", 0.382, 5, 20, 5.0, "1m"),
        ("R4_INV_pp236_s10t20",     0.236, 10, 20, 5.0, "1m"),
        ("R4_INV_pp118_s3t9_imp3",  0.118, 3, 9,  3.0, "1m"),
        ("R4_INV_pp118_s2t10_imp3", 0.118, 2, 10, 3.0, "1m"),
        ("R4_INV_pp236_s2t12_imp3", 0.236, 2, 12, 3.0, "1m"),
        ("R4_INV_pp118_s2t12_imp5", 0.118, 2, 12, 5.0, "1m"),
    ]
    for name, pp, stop, tgt, imp, gran in R4_PARAMS:
        if pp is None:
            # sub-minute fixed pp=0.236
            pp_use = 0.236
        else:
            pp_use = pp
        max_hold = 120 if gran == "15s" else (180 if gran == "30s" else MAX_HOLD_S)
        cls = MarketablePullback
        strat = cls(
            name, impulse_pts=imp, impulse_bars=4, pull_pct=pp_use,
            stop_pts=stop, target_pts=tgt, invert=True,
            max_hold=max_hold)
        if gran == "15s":
            v15s.append(strat)
        elif gran == "30s":
            v30s.append(strat)
        else:
            v1m.append(strat)
        wf_groups[f"INV_{gran}_pp{int(pp_use*1000)}"].append(strat)

    # =========================================================================
    # Round-8 14d winners — re-tested on full 60d under both fee models
    # =========================================================================
    R8_WINNERS = [
        # (name, builder)
        ("R8_E01_CANON_OVR_INV_236",
         lambda: MarketablePullback(
             "R8_E01_CANON_OVR_INV_236",
             impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
             stop_pts=10, target_pts=20, invert=True,
             session_start=(13, 30), session_end=(16, 0))),
        ("R8_E01_CANON_NYO_INV_236",
         lambda: MarketablePullback(
             "R8_E01_CANON_NYO_INV_236",
             impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
             stop_pts=10, target_pts=20, invert=True,
             session_start=(13, 30), session_end=(15, 30))),
        ("R8_E01_CANON_RTH_INV_236",
         lambda: MarketablePullback(
             "R8_E01_CANON_RTH_INV_236",
             impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
             stop_pts=10, target_pts=20, invert=True,
             session_start=(13, 30), session_end=(20, 0))),
        ("R8_B05_CANON_winNYO",
         lambda: GatedCanonPullback(
             "R8_B05_CANON_winNYO",
             window=((13, 30), (15, 30)))),
        ("R8_B05_CANON_winOVR",
         lambda: GatedCanonPullback(
             "R8_B05_CANON_winOVR",
             window=((13, 30), (16, 0)))),
        ("R8_B02_CANON_velmin5",
         lambda: GatedCanonPullback(
             "R8_B02_CANON_velmin5",
             velocity_min=5.0)),
        ("R8_B04_CANON_bal_n300_t30",
         lambda: GatedCanonPullback(
             "R8_B04_CANON_bal_n300_t30",
             balance_align=True, balance_n=300, balance_thresh=30)),
        ("R8_B04_CANON_bal_n200_t20",
         lambda: GatedCanonPullback(
             "R8_B04_CANON_bal_n200_t20",
             balance_align=True, balance_n=200, balance_thresh=20)),
        ("R8_B04_CANON_bal_n500_t50",
         lambda: GatedCanonPullback(
             "R8_B04_CANON_bal_n500_t50",
             balance_align=True, balance_n=500, balance_thresh=50)),
        ("R8_C04_MTF_early_imp4_b3_s8t24_INV",
         lambda: MTFConfluence(
             "R8_C04_MTF_early_imp4_b3_s8t24_INV",
             impulse_pts=4.0, impulse_bars=3, pull_pct=0.382,
             stop_pts=8, target_pts=24, invert=True)),
    ]
    for name, builder in R8_WINNERS:
        s = builder()
        v1m.append(s)
        wf_groups["R8_winners"].append(s)

    # =========================================================================
    # Round-7 candidate echoes
    # =========================================================================
    R7_CANDS = [
        ("R7_MTF_imp6_pp382_s5t20_INV",
         lambda: MTFConfluence(
             "R7_MTF_imp6_pp382_s5t20_INV",
             impulse_pts=6.0, impulse_bars=4, pull_pct=0.382,
             stop_pts=5, target_pts=20, invert=True)),
        ("R7_VRP_v1-3_s5t15",
         lambda: VolRegimePullback(
             "R7_VRP_v1-3_s5t15",
             vol_min=1.0, vol_max=3.0,
             stop_pts=5, target_pts=15)),
        ("R7_SRR_lk20_sw8_s5t20",
         lambda: StopRunReversal(
             "R7_SRR_lk20_sw8_s5t20",
             lookback=20, sweep_pts=8.0,
             stop_pts=5, target_pts=20)),
    ]
    for name, builder in R7_CANDS:
        s = builder()
        v1m.append(s)
        wf_groups["R7_cands"].append(s)

    # =========================================================================
    # WALK-FORWARD parameter sweeps — give analysis B real data
    # =========================================================================
    # CANON_INV_236 sweep over (stop, target) combos.
    # Each block, we'll pick the best one from the prior block and report.
    WF_CANON_STOP_TGT = [
        (5, 15), (5, 20), (8, 16), (8, 20), (8, 24),
        (10, 15), (10, 20), (10, 25), (10, 30),
        (12, 20), (12, 24),
    ]
    for stop, tgt in WF_CANON_STOP_TGT:
        s = MarketablePullback(
            f"WF_CANON_INV_236_s{stop}t{tgt}",
            impulse_pts=5.0, impulse_bars=4, pull_pct=0.236,
            stop_pts=stop, target_pts=tgt, invert=True)
        v1m.append(s)
        wf_groups["WF_CANON_INV_236"].append(s)

    # INV_pp382 sweep (round-7 MTF root)
    WF_PP382_STOP_TGT = [
        (3, 12), (4, 12), (4, 16), (5, 15), (5, 20),
        (6, 18), (8, 16), (8, 20), (8, 24),
    ]
    for stop, tgt in WF_PP382_STOP_TGT:
        s = MarketablePullback(
            f"WF_INV_pp382_imp6_s{stop}t{tgt}",
            impulse_pts=6.0, impulse_bars=4, pull_pct=0.382,
            stop_pts=stop, target_pts=tgt, invert=True)
        v1m.append(s)
        wf_groups["WF_INV_pp382_imp6"].append(s)

    # INV_pp236 sweep over impulse size
    WF_PP236_IMP_STOP = [
        (4.0, 8, 16), (4.0, 8, 20), (5.0, 8, 16), (5.0, 8, 20),
        (5.0, 10, 20), (6.0, 8, 16), (6.0, 8, 20), (6.0, 10, 20),
        (8.0, 8, 24),
    ]
    for imp, stop, tgt in WF_PP236_IMP_STOP:
        s = MarketablePullback(
            f"WF_INV_pp236_imp{int(imp)}_s{stop}t{tgt}",
            impulse_pts=imp, impulse_bars=4, pull_pct=0.236,
            stop_pts=stop, target_pts=tgt, invert=True)
        v1m.append(s)
        wf_groups["WF_INV_pp236_byimp"].append(s)

    # INV15s sub-minute sweep
    WF_15S_STOP_TGT = [
        (2, 8), (2, 10), (2, 12), (3, 9), (3, 12), (3, 15),
        (4, 12), (4, 16), (5, 15), (5, 20),
    ]
    for stop, tgt in WF_15S_STOP_TGT:
        s = MarketablePullback(
            f"WF_INV15s_imp2_s{stop}t{tgt}",
            impulse_pts=2.0, impulse_bars=4, pull_pct=0.236,
            stop_pts=stop, target_pts=tgt, invert=True,
            max_hold=120)
        v15s.append(s)
        wf_groups["WF_INV15s_imp2"].append(s)

    # INV30s sub-minute sweep
    WF_30S_STOP_TGT = [
        (2, 8), (2, 10), (3, 9), (3, 12), (3, 15),
        (4, 12), (4, 16), (5, 15), (5, 20),
    ]
    for stop, tgt in WF_30S_STOP_TGT:
        s = MarketablePullback(
            f"WF_INV30s_imp3_s{stop}t{tgt}",
            impulse_pts=3.0, impulse_bars=4, pull_pct=0.236,
            stop_pts=stop, target_pts=tgt, invert=True,
            max_hold=180)
        v30s.append(s)
        wf_groups["WF_INV30s_imp3"].append(s)

    # =========================================================================
    # SRR detector aux (feeds MARKET state for any gated strategy using it)
    # =========================================================================
    srr_det = _r8._SRRDetector()
    attach_r7_executor(srr_det)
    aux = [srr_det]

    # Attach executor to every reportable strategy
    n_total = 0
    for ls in [v1m, v15s, v30s, vtick]:
        for s in ls:
            attach_r7_executor(s)
            n_total += 1

    return v1m, v15s, v30s, vtick, aux, dict(wf_groups), n_total


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
        print(f"[round9] checkpoint load failed: {e!r}", file=sys.stderr)
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
# REPORTING
# =============================================================================
def report_strategy(strat, total_days, fee_rt, pt_value=MNQ_PER_PT):
    """Compute summary metrics under given fee + point value.
    Completed tuples: (pnl_pts, reason, day_counter, block_idx, regime_cell)
    OR legacy (pnl_pts, reason, day_counter) — handle both.
    """
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


def report_per_block(strat, fee_rt, pt_value=MNQ_PER_PT):
    """Per-block stats: net pnl_usd, n_trades, wr for each of N_BLOCKS."""
    blocks = [{'n': 0, 'wins': 0, 'net': 0.0} for _ in range(N_BLOCKS)]
    for c in strat.completed:
        if len(c) < 4:
            continue
        pnl_pts = c[0]; b = c[3]
        if 0 <= b < N_BLOCKS:
            pnl_usd = pnl_pts * pt_value - fee_rt
            blocks[b]['n'] += 1
            if pnl_usd > 0:
                blocks[b]['wins'] += 1
            blocks[b]['net'] += pnl_usd
    return blocks


def report_per_regime(strat, fee_rt, pt_value=MNQ_PER_PT):
    """Per-regime-cell stats. Returns dict[cell] -> (n, wins, net)."""
    cells = defaultdict(lambda: {'n': 0, 'wins': 0, 'net': 0.0})
    for c in strat.completed:
        if len(c) < 5:
            continue
        pnl_pts = c[0]; cell = c[4]
        pnl_usd = pnl_pts * pt_value - fee_rt
        cells[cell]['n'] += 1
        if pnl_usd > 0:
            cells[cell]['wins'] += 1
        cells[cell]['net'] += pnl_usd
    return dict(cells)


# =============================================================================
# MAIN
# =============================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offset", type=int, default=DEFAULT_OFFSET)
    ap.add_argument("--ckpt-suffix", default="")
    ap.add_argument("--max-days", type=int, default=60)
    args = ap.parse_args()

    ckpt_path = ("/home/user/HFTBot/research/round9_checkpoint"
                 f"{args.ckpt_suffix}.pkl")
    csv_path = ("/home/user/HFTBot/research/round9_summary"
                f"{args.ckpt_suffix}.csv")
    md_path = ("/home/user/HFTBot/research/round9_results"
               f"{args.ckpt_suffix}.md")

    v1m, v15s, v30s, vtick, aux, wf_groups, n_total = build_round9_variants()
    all_strats = v1m + v15s + v30s + vtick
    all_runnable = all_strats + aux
    print(f"\n[round9] Built {len(all_strats)} reportable strategies "
          f"({len(v1m)} 1m + {len(v15s)} 15s + {len(v30s)} 30s + "
          f"{len(vtick)} tick) + {len(aux)} aux", file=sys.stderr)
    print(f"[round9] wf_groups: {len(wf_groups)} families", file=sys.stderr)
    print(f"[round9] starting offset {args.offset:,}, ckpt={ckpt_path}",
          file=sys.stderr)

    resumed = load_checkpoint(ckpt_path, all_strats)
    if resumed is not None:
        start_offset, day_counter, last_day_key = resumed
        resumed_trades = sum(s.n_trades for s in all_strats)
        print(f"[round9] RESUMING from offset {start_offset:,} "
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
    print(f"[round9] file size: {file_size:,} bytes", file=sys.stderr)

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
                    print(f"  [round9] ckpt save failed: {e!r}", file=sys.stderr)
                print(f"  [round9] {n_lines/1e6:.1f}M ticks rate={rate/1e6:.2f}M/s "
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

            MARKET.feed_tick(ts, last, bid, ask)

            if bb_1m.on_tick(ts, last):
                closed = bb_1m.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    MARKET.feed_bar(o, h, l, c)
                    REGIME.feed_bar(o, h, l, c)
                    for s in v1m:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_1m.history)
                    for s in aux:
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

            for s in vtick:
                s.feed_tick(ts, last)

            for s in all_runnable:
                r9_bot_on_tick(s, ts, bid, ask, day_counter, hh, mn, last)

    elapsed = time.time() - t_start
    total_days = day_counter + 1
    print(f"\n[round9] DONE in {elapsed/60:.1f}min, {n_lines:,} ticks, "
          f"{total_days} day buckets", file=sys.stderr)

    # =========================================================================
    # REPORTING - Five-angle synthesis
    # =========================================================================
    # Compute rows under both fee models
    rows_191 = [report_strategy(s, total_days, FEE_FULL_RT) for s in all_strats]
    rows_074 = [report_strategy(s, total_days, FEE_PROP_RT) for s in all_strats]
    rows_nq_191 = [report_strategy(s, total_days, FEE_FULL_RT, NQ_PER_PT) for s in all_strats]
    rows_nq_074 = [report_strategy(s, total_days, FEE_PROP_RT, NQ_PER_PT) for s in all_strats]

    rows_191_by_name = {r['name']: r for r in rows_191}
    rows_074_by_name = {r['name']: r for r in rows_074}
    rows_nq_191_by_name = {r['name']: r for r in rows_nq_191}

    # ---- A. Fee comparison: top 20 by per_day under each fee model
    rows_191.sort(key=lambda r: -r['per_day'])
    rows_074.sort(key=lambda r: -r['per_day'])

    # CSV
    with open(csv_path, "w", newline="") as cf:
        w = csv.writer(cf)
        w.writerow([
            "name", "trades", "trades_per_day", "wr",
            "per_day_191", "per_day_074", "per_day_NQ_191", "per_day_NQ_074",
            "per_trade_191", "max_dd_191", "max_dd_074",
            "sharpe_191", "sharpe_074",
            "n_days", "pos_d_191", "neg_d_191",
        ])
        for r in rows_191:
            n = r['name']
            r74 = rows_074_by_name[n]
            rnq = rows_nq_191_by_name[n]
            rnq74 = next(x for x in rows_nq_074 if x['name'] == n)
            w.writerow([
                n, r['n'], f"{r['trades_per_day']:.1f}", f"{r['wr']:.4f}",
                f"{r['per_day']:.2f}", f"{r74['per_day']:.2f}",
                f"{rnq['per_day']:.2f}", f"{rnq74['per_day']:.2f}",
                f"{r['per_trade']:.3f}",
                f"{r['max_dd']:.2f}", f"{r74['max_dd']:.2f}",
                f"{r['sharpe']:.3f}", f"{r74['sharpe']:.3f}",
                r['n_days'], r['pos_d'], r['neg_d'],
            ])
    print(f"[round9] wrote CSV {csv_path}", file=sys.stderr)

    # ---- B. Walk-forward analysis ----
    # For each wf_group, per-block: pick best strat ON the prior block, then
    # measure its CURRENT block. Compare cumulative to "fixed best on full".
    def wf_analyse(group_strats, fee_rt):
        per_block = {}
        for s in group_strats:
            per_block[s.name] = report_per_block(s, fee_rt)
        # Block 0 = baseline (deploy fixed best from block 0 itself? No —
        # block 0 has no prior. So we report block 0 as the LARGEST single
        # block of B0_train -> B1_test data only. Use B0 as warm-up.)
        # Cumulative walk-forward: for blocks 1..N-1, pick best (by net) on
        # block-(i-1) and use its block-i net.
        # Compare to fixed-on-full: pick best by FULL-sample net.
        # Fixed
        fixed_best_name = max(
            group_strats,
            key=lambda s: sum(per_block[s.name][i]['net'] for i in range(N_BLOCKS)),
        ).name
        fixed_full_net = sum(per_block[fixed_best_name][i]['net'] for i in range(N_BLOCKS))
        wf_seq = []
        wf_total = 0.0
        for i in range(1, N_BLOCKS):
            # pick best from block i-1
            best = max(group_strats, key=lambda s: per_block[s.name][i - 1]['net'])
            blk_net = per_block[best.name][i]['net']
            blk_n = per_block[best.name][i]['n']
            wf_total += blk_net
            wf_seq.append((i, best.name, per_block[best.name][i - 1]['net'],
                           blk_net, blk_n))
        return {
            'fixed_best': fixed_best_name,
            'fixed_full_net': fixed_full_net,
            'wf_seq': wf_seq,
            'wf_total_test_net': wf_total,
        }

    wf_results_191 = {g: wf_analyse(ss, FEE_FULL_RT) for g, ss in wf_groups.items()}
    wf_results_074 = {g: wf_analyse(ss, FEE_PROP_RT) for g, ss in wf_groups.items()}

    # ---- C. Regime-switching meta-strategy ----
    # For each cell, find best strat by per-cell net. Sum cell-bests for
    # meta total. Compare against the single best fixed strat over full
    # sample.
    def regime_meta(strats, fee_rt):
        # Per-strat per-cell stats
        per_cell = {s.name: report_per_regime(s, fee_rt) for s in strats}
        all_cells = set()
        for d in per_cell.values():
            all_cells.update(d.keys())
        meta = {}
        meta_total = 0
        meta_n_trades = 0
        meta_wins = 0
        for cell in sorted(all_cells):
            best_name = None
            best_net = -1e18
            for s in strats:
                pc = per_cell[s.name].get(cell)
                if not pc or pc['n'] < 5:
                    continue
                if pc['net'] > best_net:
                    best_net = pc['net']
                    best_name = s.name
                    best_info = pc
            if best_name is None:
                continue
            meta[cell] = (best_name, best_info)
            if best_info['net'] > 0:
                meta_total += best_info['net']
                meta_n_trades += best_info['n']
                meta_wins += best_info['wins']
        return meta, meta_total, meta_n_trades, meta_wins

    meta_191, meta_total_191, meta_n_191, meta_w_191 = regime_meta(
        all_strats, FEE_FULL_RT)
    meta_074, meta_total_074, meta_n_074, meta_w_074 = regime_meta(
        all_strats, FEE_PROP_RT)

    # ---- D. NQ economics: already in rows_nq_191 ----
    rows_nq_191.sort(key=lambda r: -r['per_day'])
    rows_nq_074.sort(key=lambda r: -r['per_day'])

    # ---- E. Constraint relaxation analysis ----
    # Bin variants by (vol-tier, WR-tier) and find max $/day in each cell.
    # Both fee models.
    def bin_relax(rows):
        vol_bins = [(50, 100), (100, 200), (200, 300), (300, 99999)]
        wr_bins = [0.45, 0.46, 0.47, 0.50, 0.55]
        # For each (vol-bin, wr-min), find max $/day.
        out = {}
        for vlo, vhi in vol_bins:
            for wrm in wr_bins:
                candidates = [
                    r for r in rows
                    if vlo <= r['trades_per_day'] < vhi
                    and r['wr'] >= wrm
                ]
                if not candidates:
                    out[(vlo, vhi, wrm)] = None
                else:
                    best = max(candidates, key=lambda r: r['per_day'])
                    out[(vlo, vhi, wrm)] = best
        return out

    relax_191 = bin_relax(rows_191)
    relax_074 = bin_relax(rows_074)

    # ---- F. Hard requirement passers ----
    def is_pass(r):
        return (r['trades_per_day'] >= 300 and r['wr'] >= 0.45
                and r['per_day'] >= 1000 and r['max_dd'] <= 5000)

    pass_191 = [r for r in rows_191 if is_pass(r)]
    pass_074 = [r for r in rows_074 if is_pass(r)]
    pass_nq_191 = [r for r in rows_nq_191 if is_pass(r)]
    pass_nq_074 = [r for r in rows_nq_074 if is_pass(r)]

    # =========================================================================
    # MARKDOWN OUTPUT
    # =========================================================================
    L = []
    L.append("# Round 9 strategy search — five-angle attack\n\n")
    L.append(f"Generated: {datetime.now().isoformat()}\n")
    L.append(f"Period: {total_days} calendar-day buckets from offset "
             f"{args.offset:,} (max-days={args.max_days})\n")
    L.append(f"Tick stream: {n_lines:,} lines processed\n")
    L.append(f"Strategies tested: {len(all_strats)}\n")
    L.append(f"Walk-forward families: {len(wf_groups)}\n\n")

    L.append("## Execution model\n\n")
    L.append("Bot-faithful: queue overshoot by 1 tick (LIMIT), 200ms latency, "
             "10pt approach threshold, multi-setup lock, 0.5pt stop slip + "
             "10% gap risk, 10s cooldown, 600s max hold.\n\n")
    L.append(f"Fees tracked: **$1.91/RT** (commission $0.74 + exchange $1.17) "
             f"vs **$0.74/RT** (prop-firm: exchange rebated).\n\n")
    L.append(f"Instruments: MNQ ($2/pt) and NQ ($20/pt — for D-analysis).\n\n")

    L.append("## Hard requirements\n")
    L.append("- 300+ trades/day average\n")
    L.append("- 45%+ win rate\n")
    L.append("- $1000+ net daily P&L\n")
    L.append("- Max DD <= $5000\n\n")

    # ---- 7. Hard-pass under $0.74 -- the headline number
    L.append(f"## Section 7 — Strategies meeting ALL hard reqs (60d, MNQ)\n\n")
    L.append(f"### Under $1.91/RT fees: **{len(pass_191)}** strategies\n\n")
    if pass_191:
        for r in pass_191:
            L.append(
                f"- **{r['name']}** -- {r['n']:,} trades "
                f"({r['trades_per_day']:.1f}/day), WR={r['wr']*100:.1f}%, "
                f"${r['per_day']:,.0f}/day, maxDD=${r['max_dd']:,.0f}, "
                f"Sharpe={r['sharpe']:.2f}\n")
    else:
        L.append("**NONE.** Same as rounds 5-8.\n")
    L.append(f"\n### Under $0.74/RT fees (prop-firm Apex/TopstepX/Tradeify/"
             f"Bulenox): **{len(pass_074)}** strategies\n\n")
    if pass_074:
        for r in pass_074:
            L.append(
                f"- **{r['name']}** -- {r['n']:,} trades "
                f"({r['trades_per_day']:.1f}/day), WR={r['wr']*100:.1f}%, "
                f"${r['per_day']:,.0f}/day, maxDD=${r['max_dd']:,.0f}, "
                f"Sharpe={r['sharpe']:.2f} -- **DEPLOYABLE on prop-firm**\n")
    else:
        L.append("**NONE.** Fee reduction alone does not lift any variant.\n")

    L.append(f"\n### NQ (10x point value, same fee model)\n\n")
    L.append(f"- Under $1.91/RT NQ: {len(pass_nq_191)} pass\n")
    L.append(f"- Under $0.74/RT NQ: {len(pass_nq_074)} pass\n\n")
    if pass_nq_191:
        L.append("**$1.91 NQ passers:**\n")
        for r in pass_nq_191[:10]:
            L.append(
                f"- {r['name']}: {r['trades_per_day']:.1f}/day, WR={r['wr']*100:.1f}%, "
                f"${r['per_day']:,.0f}/day, DD=${r['max_dd']:,.0f}\n")
    if pass_nq_074:
        L.append("\n**$0.74 NQ passers:**\n")
        for r in pass_nq_074[:10]:
            L.append(
                f"- {r['name']}: {r['trades_per_day']:.1f}/day, WR={r['wr']*100:.1f}%, "
                f"${r['per_day']:,.0f}/day, DD=${r['max_dd']:,.0f}\n")

    # ---- 1. Top 20 by $/day under $1.91 ----
    L.append("\n## Section 1 — Top 20 by $/day under $1.91 fees (baseline MNQ)\n\n")
    L.append("| Rank | Strategy | Tr | Tr/d | WR% | $/day | $/tr | maxDD | Sharpe |\n")
    L.append("|---:|---|---:|---:|---:|---:|---:|---:|---:|\n")
    for i, r in enumerate(rows_191[:20], 1):
        L.append(
            f"| {i} | {r['name']} | {r['n']:,} | {r['trades_per_day']:.1f} | "
            f"{r['wr']*100:.1f} | ${r['per_day']:,.0f} | "
            f"${r['per_trade']:.2f} | ${r['max_dd']:,.0f} | "
            f"{r['sharpe']:.2f} |\n")

    # ---- 2. Top 20 by $/day under $0.74 ----
    L.append("\n## Section 2 — Top 20 by $/day under $0.74 fees (prop-firm MNQ)\n\n")
    L.append("| Rank | Strategy | Tr | Tr/d | WR% | $/day | $/tr | maxDD | Sharpe |\n")
    L.append("|---:|---|---:|---:|---:|---:|---:|---:|---:|\n")
    for i, r in enumerate(rows_074[:20], 1):
        L.append(
            f"| {i} | {r['name']} | {r['n']:,} | {r['trades_per_day']:.1f} | "
            f"{r['wr']*100:.1f} | ${r['per_day']:,.0f} | "
            f"${r['per_trade']:.2f} | ${r['max_dd']:,.0f} | "
            f"{r['sharpe']:.2f} |\n")

    # ---- Fee lift table: side-by-side
    L.append("\n### Fee-reduction lift: $/day at $0.74 - $/day at $1.91 "
             "(top 20 by lift)\n\n")
    lift_rows = []
    for r in rows_191:
        n = r['name']
        r74 = rows_074_by_name[n]
        lift = r74['per_day'] - r['per_day']
        if r['n'] > 50:
            lift_rows.append((lift, r['name'], r['per_day'], r74['per_day'],
                              r['trades_per_day'], r['wr'], r['max_dd']))
    lift_rows.sort(reverse=True)
    L.append("| Strategy | $1.91 $/d | $0.74 $/d | Lift | Tr/d | WR% | maxDD |\n")
    L.append("|---|---:|---:|---:|---:|---:|---:|\n")
    for lift, name, p191, p074, tpd, wr, dd in lift_rows[:20]:
        L.append(f"| {name} | ${p191:,.0f} | ${p074:,.0f} | ${lift:,.0f} | "
                 f"{tpd:.1f} | {wr*100:.1f} | ${dd:,.0f} |\n")

    # ---- 3. Walk-forward ----
    L.append("\n## Section 3 — Walk-forward parameter optimization\n\n")
    L.append("Blocks: " + ", ".join(f"B{i} d{lo}-{hi}" for i, (lo, hi) in enumerate(BLOCK_BOUNDS)) + "\n\n")
    for fee_label, results in [("$1.91", wf_results_191), ("$0.74", wf_results_074)]:
        L.append(f"\n### Walk-forward under {fee_label}/RT fees\n\n")
        L.append("| Family | Fixed-best | Fixed full $ | WF total test $ | WF beats fixed? |\n")
        L.append("|---|---|---:|---:|:---:|\n")
        for g in sorted(results.keys()):
            res = results[g]
            wf_t = res['wf_total_test_net']
            fx_t = res['fixed_full_net']
            wf_wins = "YES" if wf_t > fx_t else "no"
            L.append(f"| {g} | {res['fixed_best']} | ${fx_t:,.0f} | "
                     f"${wf_t:,.0f} | {wf_wins} |\n")
        # Detail for top families
        L.append(f"\n#### Walk-forward per-block detail under {fee_label}\n")
        for g in sorted(results.keys()):
            res = results[g]
            L.append(f"\n**{g}** -- fixed_best={res['fixed_best']}, "
                     f"WF_total={res['wf_total_test_net']:,.0f}, "
                     f"Fixed_total={res['fixed_full_net']:,.0f}\n")
            for i, name, prev_blk_net, cur_blk_net, n_tr in res['wf_seq']:
                L.append(f"- B{i}: picked **{name}** (prior block "
                         f"${prev_blk_net:,.0f}), test block "
                         f"${cur_blk_net:,.0f} on {n_tr} trades\n")

    # ---- 4. Regime-switching meta ----
    L.append("\n## Section 4 — Regime-switching meta-strategy\n\n")
    L.append("Each tick we recompute (Hurst, Choppiness, Vol) -> 8-cell regime. "
             "For each cell, we pick the best strategy by per-cell P&L "
             "(min 5 trades in cell). Meta = sum of positive cell-bests.\n\n")
    for fee_label, meta, total, n_tr, wins in [
        ("$1.91", meta_191, meta_total_191, meta_n_191, meta_w_191),
        ("$0.74", meta_074, meta_total_074, meta_n_074, meta_w_074),
    ]:
        L.append(f"\n### Meta under {fee_label}/RT fees\n\n")
        wr_meta = wins / n_tr if n_tr > 0 else 0.0
        per_d_meta = total / max(1, total_days)
        L.append(f"- Meta total: **${total:,.0f}** over 60d "
                 f"= ${per_d_meta:,.0f}/day\n")
        L.append(f"- Meta trades: {n_tr:,}, WR={wr_meta*100:.1f}%\n")
        L.append(f"- Cells filled: {len(meta)}/8\n\n")
        L.append("| Cell | Code | Best strategy | n | wr | $ |\n")
        L.append("|---:|:---:|---|---:|---:|---:|\n")
        for cell in sorted(meta.keys()):
            name, info = meta[cell]
            cwr = info['wins'] / info['n'] if info['n'] else 0
            L.append(f"| {cell} | {RegimeEngine.cell_label(cell)} | {name} | "
                     f"{info['n']} | {cwr*100:.1f}% | ${info['net']:,.0f} |\n")
        L.append("\nCell code legend: 1st letter T=Hurst trending, R=mean-reverting; "
                 "2nd C=choppy, D=directional; 3rd H=high vol, L=low vol.\n")

    # ---- 5. NQ economics ----
    L.append("\n## Section 5 — NQ economics (10x point value, same fees)\n\n")
    L.append(f"### Top 10 under $1.91 NQ\n\n")
    L.append("| Rank | Strategy | Tr/d | WR% | $/day | maxDD | Sharpe |\n")
    L.append("|---:|---|---:|---:|---:|---:|---:|\n")
    for i, r in enumerate(rows_nq_191[:10], 1):
        L.append(f"| {i} | {r['name']} | {r['trades_per_day']:.1f} | "
                 f"{r['wr']*100:.1f} | ${r['per_day']:,.0f} | "
                 f"${r['max_dd']:,.0f} | {r['sharpe']:.2f} |\n")
    L.append(f"\n### Top 10 under $0.74 NQ\n\n")
    L.append("| Rank | Strategy | Tr/d | WR% | $/day | maxDD | Sharpe |\n")
    L.append("|---:|---|---:|---:|---:|---:|---:|\n")
    for i, r in enumerate(rows_nq_074[:10], 1):
        L.append(f"| {i} | {r['name']} | {r['trades_per_day']:.1f} | "
                 f"{r['wr']*100:.1f} | ${r['per_day']:,.0f} | "
                 f"${r['max_dd']:,.0f} | {r['sharpe']:.2f} |\n")

    # ---- 6. Constraint relaxation ----
    L.append("\n## Section 6 — Constraint relaxation analysis\n\n")
    L.append("For each (volume-tier, WR-tier) cell, the highest $/day variant "
             "across the 60d period. Annual = $/day * 252.\n\n")
    for fee_label, relax in [("$1.91", relax_191), ("$0.74", relax_074)]:
        L.append(f"\n### Under {fee_label}/RT fees\n\n")
        L.append("| Vol bin | WR-min | Best strategy | Tr/d | WR% | $/day | $/yr | maxDD |\n")
        L.append("|---|---:|---|---:|---:|---:|---:|---:|\n")
        for (vlo, vhi, wrm), best in sorted(relax.items()):
            if best is None:
                L.append(f"| {vlo}-{vhi if vhi<99999 else '+inf'} | {wrm:.2f} | "
                         f"(no candidates) | - | - | - | - | - |\n")
            else:
                L.append(f"| {vlo}-{vhi if vhi<99999 else '+inf'} | {wrm:.2f} | "
                         f"{best['name']} | {best['trades_per_day']:.1f} | "
                         f"{best['wr']*100:.1f} | ${best['per_day']:,.0f} | "
                         f"${best['per_day']*252:,.0f} | "
                         f"${best['max_dd']:,.0f} |\n")

    # ---- 8. Round 10 recommendations ----
    L.append("\n## Section 8 — Round 10 recommendation\n\n")
    if pass_074 or pass_191:
        if pass_074 and not pass_191:
            L.append("**LEVER: FEES.** Prop-firm fees turn already-positive "
                     "variants into hard-pass strategies. Round 10 should:\n")
            L.append("1. Confirm prop-firm fee policy at the chosen broker.\n")
            L.append("2. Tighten the highest-Sharpe of these passers via "
                     "narrower parameter sweeps near the optimum.\n")
            L.append("3. Validate out-of-sample on a fresh 30d window.\n")
        else:
            L.append("Found passers under base fees -- proceed to deployment "
                     "validation, not further search.\n")
    else:
        # Find which lever moved the needle most
        # Compare best per_day across each lever
        best_191 = rows_191[0]['per_day'] if rows_191 else 0
        best_074 = rows_074[0]['per_day'] if rows_074 else 0
        best_nq_191 = rows_nq_191[0]['per_day'] if rows_nq_191 else 0
        best_nq_074 = rows_nq_074[0]['per_day'] if rows_nq_074 else 0
        best_meta_191 = meta_total_191 / max(1, total_days)
        best_meta_074 = meta_total_074 / max(1, total_days)

        # WF improvements
        wf_best_lift = 0.0
        wf_best_family = "none"
        for fam, res in wf_results_074.items():
            lift = res['wf_total_test_net'] - res['fixed_full_net']
            if lift > wf_best_lift:
                wf_best_lift = lift
                wf_best_family = fam

        levers = [
            ("baseline MNQ $1.91", best_191),
            ("prop-firm MNQ $0.74", best_074),
            ("baseline NQ $1.91", best_nq_191 / 10.0),  # divide by 10 to normalize per-MNQ-equivalent
            ("prop-firm NQ $0.74", best_nq_074 / 10.0),
            ("meta-regime MNQ $1.91", best_meta_191),
            ("meta-regime MNQ $0.74", best_meta_074),
        ]
        levers.sort(key=lambda x: -x[1])
        L.append(f"\nLever ranking by best $/day (MNQ-equivalent):\n\n")
        for name, val in levers:
            L.append(f"- **{name}**: ${val:,.0f}/day\n")
        L.append(f"\nWalk-forward best family lift: ${wf_best_lift:,.0f} "
                 f"({wf_best_family})\n\n")

        L.append("**ROUND 10 should attack the top lever exclusively** "
                 "with a focused parameter sweep around its optimum.\n")

    # ---- All strategies dump (sorted by per-day $1.91) ----
    L.append("\n## Section 9 — Full strategy table (sorted by $/day at $1.91)\n\n")
    L.append("| Strategy | Tr | Tr/d | WR% | $/d 191 | $/d 074 | $/tr 191 | maxDD 191 | Sharpe 191 |\n")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for r in rows_191:
        n = r['name']
        r74 = rows_074_by_name[n]
        L.append(f"| {n} | {r['n']:,} | {r['trades_per_day']:.1f} | "
                 f"{r['wr']*100:.1f} | ${r['per_day']:,.0f} | "
                 f"${r74['per_day']:,.0f} | ${r['per_trade']:.2f} | "
                 f"${r['max_dd']:,.0f} | {r['sharpe']:.2f} |\n")

    with open(md_path, "w") as mf:
        mf.write("".join(L))
    print(f"[round9] wrote MD {md_path}", file=sys.stderr)

    # Console summary
    print("\n" + "=" * 110)
    print(f"FULL_PASS under $1.91 (MNQ): {len(pass_191)}")
    print(f"FULL_PASS under $0.74 (MNQ prop-firm): {len(pass_074)}")
    print(f"FULL_PASS under $1.91 (NQ): {len(pass_nq_191)}")
    print(f"FULL_PASS under $0.74 (NQ prop-firm): {len(pass_nq_074)}")
    print(f"Meta-regime $/day $1.91: ${meta_total_191/max(1,total_days):,.0f}")
    print(f"Meta-regime $/day $0.74: ${meta_total_074/max(1,total_days):,.0f}")
    print("=" * 110)
    for r in rows_074[:20]:
        n = r['name']
        r191 = rows_191_by_name[n]
        flag = ""
        if is_pass(r): flag = " *PASS(prop)*"
        elif is_pass(r191): flag = " *PASS(full)*"
        print(f"{n:>42s} {r['n']:>7d} {r['trades_per_day']:>6.1f} "
              f"{r['wr']*100:>4.1f}% ${r['per_day']:>+8.0f} (191: ${r191['per_day']:>+7.0f}){flag}")

    try:
        if os.path.exists(ckpt_path):
            os.remove(ckpt_path)
            print(f"[round9] cleared checkpoint {ckpt_path}",
                  file=sys.stderr)
    except Exception:
        pass


if __name__ == "__main__":
    main()
