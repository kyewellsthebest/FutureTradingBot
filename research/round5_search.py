"""Round 5 strategy search for MNQ — BOT-FAITHFUL execution model.

vs round4_search.py: round 4 used an idealized execution model (LIMIT at
the exact pullback price fills as soon as ask/bid touches it). The live
bot has substantially more friction. The user observed that round 4's 17
strategies destroy their edge once execution friction is applied. Round 5
mirrors the live bot's execution layer end-to-end:

  1. Anticipatory pre-submit threshold (APPROACH_THRESHOLD_PT = 10.0).
     A LIMIT is only resting on the matching engine when current price
     is within 10pt of the pullback. If a setup is generated farther
     away, no anticipatory LIMIT exists. When price eventually arrives,
     the bot submits a fresh LIMIT — but there is a 250ms latency
     penalty before that order is live in the book. During that window,
     the price may have already passed the level (miss).

  2. Single-active-LIMIT lock. When multiple pending setups exist, only
     the CLOSEST one (by distance from current ask/bid on the impulse
     side) has an active broker LIMIT. The others have fire_attempted=
     True (because when this one became closest, the previous closer
     setup was cancelled, locking out paper firing on it). When the
     closer-setup arrives or expires/exits, the next-closest gets a
     fresh LIMIT after the same 250ms latency.

  3. 200ms latency embargo on a brand-new setup. The setup is generated
     on a bar-close tick; the actual placeoso call (and matching engine
     acknowledgement) takes ~200ms. We embargo entry triggers on the
     setup for the first 200ms after generation.

  4. Queue position model. When ASK touches our LIMIT BUY price, we are
     behind N contracts in the queue at that price level. A real fill
     typically requires the price to move THROUGH the level, not just
     touch it. We approximate this by requiring ask < entry_px (i.e.
     strict, by 1 tick) for LONG fills, and bid > entry_px for SHORT.

  5. Real bid/ask from tick data. No synthetic spread — we use the
     actual ASK/BID columns. (Round 4 also used these, but applied a
     0.5pt entry slip on top — round 5 does not add slip because the
     queue/touch-through model already accounts for it.)

  6. Stop-MARKET slip. When stop_px is touched (LONG: bid <= stop_px;
     SHORT: ask >= stop_px), the market exit fills 0.5pt worse than
     stop_px. 10% of the time, an extra random 0-1.5pt gap-risk slip
     is added.

  7. $1.91 round-trip cost.

  8. 10s cooldown after exit before any new entry.

  9. Stale-fill / mismatch hedge: 5% probability that a fill is "stale"
     (broker netPos diverges from paper) — when that happens the bot
     pauses 1 trade. We model this by SKIPPING the next 1 trade after
     a probabilistic 5% per-fill event.

Run inputs:
  - 60-day tick window starting at the same offset as round 4.
  - Robustness: optional --offset to test earlier 60-day windows.
  - Strategy set: 17 round-4 passers + top 30 by $/day.

Outputs:
  - research/round5_results.md   — markdown report
  - research/round5_summary.csv  — CSV
  - research/round5_checkpoint.pkl  — checkpoint
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

# Import the strategy classes and bar builders from round 4 so we can
# reuse the signal-generation logic unchanged. The execution model is
# the ONLY thing that changes in round 5.
#
# Path setup: make BOTH 'research.round4_search' (when launched as a
# module under the research package) and 'round4_search' (when launched
# directly from research/) resolve to the SAME module object. Without
# this, the StrategyBase class gets duplicated and our add_setup patch
# fails to apply to the class actually used by instantiated strategies.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

# Force a single canonical import path.
from research import round4_search as _r4  # noqa: E402
sys.modules.setdefault("round4_search", _r4)
PullbackStrategy = _r4.PullbackStrategy
PullbackFailure = _r4.PullbackFailure
NBarReversal = _r4.NBarReversal
RSIReversion = _r4.RSIReversion
BarBuilder = _r4.BarBuilder
VolumeBarBuilder = _r4.VolumeBarBuilder
_round_long_entry = _r4._round_long_entry
_round_short_entry = _r4._round_short_entry
_round_long_stop = _r4._round_long_stop
_round_short_stop = _r4._round_short_stop
_round_long_tgt = _r4._round_long_tgt
_round_short_tgt = _r4._round_short_tgt

PATH = "/home/user/HFTBot/data/tick/ustech/USTECH_full.csv"
DEFAULT_OFFSET = 7_820_974_790

CHECKPOINT_EVERY_TICKS = 5_000_000

COMM_RT = 0.74
EXCH_FEES_RT = 1.17
TOTAL_RT_COST = COMM_RT + EXCH_FEES_RT  # $1.91
MNQ_PER_PT = 2.0

# === Execution-model constants (mirroring bot/fib_main.py) ===
APPROACH_THRESHOLD_PT = 10.0    # bot anticipatory threshold
LATENCY_EMBARGO_S = 0.20        # tick that generated the setup -> LIMIT in book
FRESH_PLACEMENT_LATENCY_S = 0.25  # LIMIT placed AFTER price arrives (cold setup)
STOP_SLIP_PT = 0.5              # baseline stop-MARKET slip
STOP_GAP_SLIP_PROB = 0.10       # prob of extra gap slip
STOP_GAP_SLIP_MAX_PT = 1.5      # max extra gap slip
COOLDOWN_S = 10.0
MAX_HOLD_S = 600
STALE_FILL_PROB = 0.05          # prob of stale-fill -> skip next trade
TICK = 0.25                     # 1 tick = 0.25 in MNQ

# Use a fixed seed so the run is reproducible across resumes.
RNG = random.Random(0xB0FAF1F1)


# ===========================================================================
# Bot-faithful execution wrapper.
#
# We REPLACE StrategyBase.on_tick with a method that models the live bot's
# execution layer. We keep the signal-generation hooks (on_bar_close,
# on_tick_signal, add_setup) untouched — round-4 strategies stay
# unchanged on the signal side.
# ===========================================================================
class BotFaithfulExecutor:
    """Per-strategy state for the bot-faithful execution model.

    Attached to a round-4 StrategyBase instance by `attach_executor`.
    Exposes a new `bot_on_tick(ts, bid, ask, day_counter, hh, mn)` method
    used instead of `on_tick`.
    """
    __slots__ = (
        "strat", "active_limit_key", "active_limit_armed_ts",
        "skip_next_trade", "last_exit_ts",
    )

    def __init__(self, strat):
        self.strat = strat
        # The setup_key of the setup whose LIMIT currently rests in the
        # book. None when no LIMIT is live.
        self.active_limit_key = None
        # ts at which the active LIMIT becomes fillable (LATENCY).
        self.active_limit_armed_ts = None
        # If True, the next trigger is skipped (stale-fill model).
        self.skip_next_trade = False
        # Tracked separately from strat.last_exit_dt because the strat's
        # value isn't reset on stale skips.
        self.last_exit_ts = None


def attach_executor(strat):
    strat._exec = BotFaithfulExecutor(strat)


def _setup_key(s):
    """Bot uses (entry, stop, target, side) — round 4 stores 'key' on
    add. Use the round 4 key (already unique per setup)."""
    return s['key']


def _closest_pending(strat, bid, ask):
    """Return the pending setup whose entry price is closest to the
    current market, using the IMPULSE side (orig) for the approach
    direction — same as the bot's `_check_anticipatory_limit`.

    Skips setups already used or with fire_attempted=True.
    """
    best = None
    best_dist = float('inf')
    # Use a side-aware current price: for LONG impulse, the price needs
    # to come DOWN to the pullback (current is the ask falling toward
    # entry); for SHORT, BID rising toward entry.
    for s in strat.pending:
        if s.get('used') or s.get('_fire_attempted'):
            continue
        orig = s.get('orig', s['side'])
        entry = s['entry']
        if orig == "LONG":
            # UP impulse, pullback entry sits below the impulse high,
            # price must fall to it. "current" price is ask (we BUY).
            # Skip if price is already FAR past entry — but accept setups
            # that are on the right side OR very near (within 0.5pt past)
            # because a LIMIT placed earlier may still fill on a re-touch.
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
    """Tick handler that mirrors the live bot's execution layer.

    Replaces round-4 StrategyBase.on_tick.
    """
    exe = strat._exec

    # Expire stale pending setups (mirror round 4 cleanup).
    if strat.pending:
        strat.pending = [
            s for s in strat.pending
            if s['expires'] >= ts and not s.get('used')
        ]

    # ----------------------------------------
    # In-trade: handle exits (stop / target / timeout).
    # ----------------------------------------
    if strat.in_trade is not None:
        tr = strat.in_trade
        exit_now = None
        if tr['side'] == 'LONG':
            # Stop: stop-MARKET sells at bid <= stop_px, fill = stop_px
            # minus baseline 0.5pt slip and 10% extra gap risk.
            if bid <= tr['stop']:
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
            # Active LIMIT is no longer relevant.
            exe.active_limit_key = None
            exe.active_limit_armed_ts = None
            # Stale-fill model: 5% chance the broker netPos diverged on
            # this fill and the bot will pause 1 trade.
            if RNG.random() < STALE_FILL_PROB:
                exe.skip_next_trade = True
        return

    # ----------------------------------------
    # Cooldown gate (10s after exit).
    # ----------------------------------------
    if exe.last_exit_ts is not None and ts - exe.last_exit_ts < COOLDOWN_S:
        return

    # Session gate.
    if not strat._in_session(hh, mn):
        return

    # ----------------------------------------
    # Decide which setup (if any) gets the broker's active LIMIT this
    # tick. Bot logic:
    #   - Find the closest pending setup (by distance to current market
    #     on the impulse side).
    #   - If the closest is the SAME as our active LIMIT, keep it.
    #   - If a different setup is now closer, CANCEL the active LIMIT
    #     and lock that setup out (fire_attempted=True), then start a
    #     new LIMIT on the closer setup with a fresh-placement latency.
    #   - If no setup is within APPROACH_THRESHOLD_PT, cancel and lock
    #     out the active LIMIT, then idle.
    # ----------------------------------------
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
        # If price was ALREADY within 10pt at setup generation, the
        # anticipatory path runs: LIMIT armed LATENCY_EMBARGO_S after
        # generation. Otherwise it's a cold submit -- fresh-placement
        # latency from NOW.
        # We approximate "anticipatory placed" by checking distance at
        # CURRENT tick (since we only see ticks after gen_ts; close
        # enough). If gen_ts == ts (this is the gen tick itself), hot
        # path; else cold path.
        if gen_ts is not None and abs(ts - gen_ts) < LATENCY_EMBARGO_S:
            exe.active_limit_armed_ts = gen_ts + LATENCY_EMBARGO_S
        else:
            exe.active_limit_armed_ts = ts + FRESH_PLACEMENT_LATENCY_S

    # ----------------------------------------
    # Embargo: LIMIT not yet live in the matching engine.
    # ----------------------------------------
    if exe.active_limit_armed_ts is not None and ts < exe.active_limit_armed_ts:
        return

    # ----------------------------------------
    # Trigger check on the active LIMIT setup.
    # Queue-position model: require strict 1-tick overshoot through the
    # level (not just a touch) for the resting LIMIT to fill.
    # ----------------------------------------
    s = closest
    orig = s.get('orig', s['side'])
    entry = s['entry']
    if orig == "LONG":
        # LIMIT BUY at entry: queue clearing requires ASK strictly below
        # the level (a seller crossed our bid).
        trig = ask <= entry - TICK
    else:
        trig = bid >= entry + TICK

    if not trig:
        return

    # Stale-fill skip: 5% probability the bot paused this trade after a
    # mismatch on the prior fill. Consume the skip.
    if exe.skip_next_trade:
        exe.skip_next_trade = False
        s['_fire_attempted'] = True
        exe.active_limit_key = None
        exe.active_limit_armed_ts = None
        return

    # FILL. LIMIT fills at our price exactly (or doesn't).
    strat.in_trade = {
        'side': s['side'],
        'entry': entry,
        'stop': s['stop'],
        'target': s['target'],
        'et': ts,
    }
    s['used'] = True
    exe.active_limit_key = None
    exe.active_limit_armed_ts = None


# ===========================================================================
# Wrap add_setup to stamp the generation ts on each setup.
# ===========================================================================
_orig_add_setup = None


def _patched_add_setup(self, side, orig, entry, stop, target, ts_now,
                       key=None, expires_in=300, extra=None):
    if side == "LONG":
        entry_r = _round_long_entry(entry)
        stop_r = _round_long_stop(stop)
        target_r = _round_long_tgt(target)
    else:
        entry_r = _round_short_entry(entry)
        stop_r = _round_short_stop(stop)
        target_r = _round_short_tgt(target)
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


# Patch the StrategyBase classes globally — round-4 strategy subclasses
# inherit add_setup from StrategyBase.
_SB = _r4.StrategyBase
_SB.add_setup = _patched_add_setup


# ===========================================================================
# Build the strategy set: 17 round-4 passers UNION top 30 by $/day.
# ===========================================================================
ROUND4_FULL_PASS = [
    "INV15s_imp2_s4t12", "INV15s_imp2_s3t12", "INV15s_imp2_s2t10",
    "INV15s_imp2_s3t9", "INV15s_imp2_s2t8",
    "INV30s_imp3_s4t12", "INV30s_imp3_s3t12",
    "INV_pp118_s5t20_imp3", "INV_pp118_s4t16_imp3",
    "INV_pp118_s3t12_imp3", "INV30s_imp3_s3t9",
    "CANON_INV_236_s10t20", "INV_pp118_s3t9_imp3",
    "INV_pp118_s3t9_imp5", "INV_236_s10t20_SCALE5",
    "INV_pp236_s3t9_imp3", "INV_236_s10t20_SCALE3",
]

ROUND4_TOP30 = [
    "INV15s_imp2_s4t12", "INV15s_imp2_s3t12", "INV15s_imp2_s2t10",
    "INV15s_imp2_s3t9", "INV15s_imp2_s2t8",
    "INV30s_imp3_s4t12", "INV30s_imp3_s3t12",
    "INV_pp118_s5t20_imp3", "INV_pp118_s4t16_imp3",
    "INV_pp118_s3t15_imp3", "INV_pp118_s5t20_imp5",
    "INV_pp118_s3t12_imp3", "INV_pp118_s4t16_imp5",
    "INV30s_imp3_s3t9", "INV_pp118_s2t12_imp3",
    "INV30s_imp3_s2t10", "INV_pp236_s5t20_imp3",
    "INV_pp118_s3t15_imp5", "INV_pp236_s4t16_imp3",
    "CANON_INV_236_s10t20", "INV_pp118_s2t10_imp3",
    "INV_pp118_s3t9_imp3", "INV_pp118_s3t12_imp5",
    "INV_pp236_s3t15_imp3", "INV_pp236_s5t20_imp5",
    "INV_pp118_s2t12_imp5", "INV_236_s10t20_BE3",
    "INV_pp382_s5t20_imp3", "INV_pp236_s3t12_imp3",
    "INV_236_s10t20_BE2",
]

R5_NAMES = list(dict.fromkeys(ROUND4_FULL_PASS + ROUND4_TOP30))


def build_variants_round5():
    """Build only the round-4 strategies we care about for round 5
    (~30 unique strategies)."""
    v1m, v15s, v30s, vtick, vvol_500, vvol_1k = _r4.build_variants()
    all_r4 = v1m + v15s + v30s + vtick + vvol_500 + vvol_1k
    by_name = {s.name: s for s in all_r4}

    # Track which bar-builder each strategy needs by inspecting its
    # class + name (1m default, names starting with INV15s use 15s,
    # INV30s use 30s, INVvol use volume bars).
    v1m_pick, v15s_pick, v30s_pick = [], [], []
    vvol_500_pick, vvol_1k_pick = [], []
    missing = []
    for nm in R5_NAMES:
        s = by_name.get(nm)
        if s is None:
            missing.append(nm)
            continue
        # Fresh state: zero out completed/by_day/n_trades.
        s.completed = []
        s.by_day = {}
        s.n_trades = 0
        s.pending = []
        s.in_trade = None
        s.last_exit_dt = None
        attach_executor(s)
        if nm.startswith("INV15s"):
            v15s_pick.append(s)
        elif nm.startswith("INV30s"):
            v30s_pick.append(s)
        elif nm.startswith("INVvol500"):
            vvol_500_pick.append(s)
        elif nm.startswith("INVvol1000"):
            vvol_1k_pick.append(s)
        else:
            v1m_pick.append(s)
    if missing:
        print(f"[round5] WARNING: missing strategies {missing}",
              file=sys.stderr)
    return v1m_pick, v15s_pick, v30s_pick, vvol_500_pick, vvol_1k_pick


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
        print(f"[round5] checkpoint load failed: {e!r}", file=sys.stderr)
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


# ===========================================================================
# Main
# ===========================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offset", type=int, default=DEFAULT_OFFSET,
                    help="File offset to start at (default: round 4 offset)")
    ap.add_argument("--ckpt-suffix", default="",
                    help="Suffix for checkpoint/results filenames (for "
                         "robustness sub-runs)")
    ap.add_argument("--max-days", type=int, default=60,
                    help="Stop after this many calendar days have elapsed")
    args = ap.parse_args()

    ckpt_path = ("/home/user/HFTBot/research/round5_checkpoint"
                 f"{args.ckpt_suffix}.pkl")
    csv_path = ("/home/user/HFTBot/research/round5_summary"
                f"{args.ckpt_suffix}.csv")
    md_path = ("/home/user/HFTBot/research/round5_results"
               f"{args.ckpt_suffix}.md")

    v1m, v15s, v30s, vvol_500, vvol_1k = build_variants_round5()
    all_strats = v1m + v15s + v30s + vvol_500 + vvol_1k
    print(f"\n[round5] Built {len(all_strats)} strategies for bot-faithful "
          f"execution: {len(v1m)} 1m + {len(v15s)} 15s + {len(v30s)} 30s + "
          f"{len(vvol_500)} vol500 + {len(vvol_1k)} vol1k",
          file=sys.stderr)
    print(f"[round5] starting offset {args.offset:,}, ckpt={ckpt_path}",
          file=sys.stderr)

    resumed = load_checkpoint(ckpt_path, all_strats)
    if resumed is not None:
        start_offset, day_counter, last_day_key = resumed
        resumed_trades = sum(s.n_trades for s in all_strats)
        print(f"[round5] RESUMING from offset {start_offset:,} "
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
    print(f"[round5] file size: {file_size:,} bytes",
          file=sys.stderr)

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
                    print(f"  [round5] ckpt save failed: {e!r}", file=sys.stderr)
                print(f"  [round5] {n_lines/1e6:.1f}M ticks rate={rate/1e6:.2f}M/s "
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

            # 1m bars
            if bb_1m.on_tick(ts, last):
                closed = bb_1m.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    for s in v1m:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_1m.history)
            # 15s
            if v15s and bb_15s.on_tick(ts, last):
                closed = bb_15s.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    for s in v15s:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_15s.history)
            # 30s
            if v30s and bb_30s.on_tick(ts, last):
                closed = bb_30s.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    for s in v30s:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_30s.history)
            # vol500
            if vvol_500 and vb_500.on_tick(ts, last):
                closed = vb_500.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    for s in vvol_500:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, vb_500.history)
            # vol1k
            if vvol_1k and vb_1k.on_tick(ts, last):
                closed = vb_1k.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    for s in vvol_1k:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, vb_1k.history)

            # Spread cache for spread-aware strategies (none used here
            # but keep for safety).
            for s in v1m:
                if hasattr(s, "_last_bid"):
                    s._last_bid = bid
                    s._last_ask = ask

            # Bot-faithful execution per strategy.
            for s in all_strats:
                bot_on_tick(s, ts, bid, ask, day_counter, hh, mn)

    elapsed = time.time() - t_start
    total_days = day_counter + 1
    print(f"\n[round5] DONE in {elapsed/60:.1f}min, {n_lines:,} ticks, "
          f"{total_days} day buckets", file=sys.stderr)

    rows = [_report(s, total_days) for s in all_strats]
    rows.sort(key=lambda r: -r['per_day'])

    # Read round-4 results for comparison.
    r4_by_name = {}
    try:
        with open("/home/user/HFTBot/research/round4_summary.csv") as cf:
            rdr = csv.DictReader(cf)
            for row in rdr:
                r4_by_name[row['name']] = row
    except Exception as e:
        print(f"[round5] couldn't read round4 csv: {e!r}", file=sys.stderr)

    with open(csv_path, "w", newline="") as cf:
        w = csv.writer(cf)
        w.writerow(["name", "trades", "trades_per_day", "wr", "net",
                    "per_day", "per_trade", "max_dd", "worst_day",
                    "best_day", "sharpe", "n_days", "pos_d", "neg_d",
                    "r4_per_day", "edge_loss_$/day"])
        for r in rows:
            r4 = r4_by_name.get(r['name'], {})
            r4_pd = float(r4.get('per_day', 0) or 0)
            edge_loss = r4_pd - r['per_day']
            w.writerow([r['name'], r['n'], f"{r['trades_per_day']:.1f}",
                        f"{r['wr']:.4f}", f"{r['net']:.2f}",
                        f"{r['per_day']:.2f}", f"{r['per_trade']:.3f}",
                        f"{r['max_dd']:.2f}", f"{r['worst']:.2f}",
                        f"{r['best']:.2f}", f"{r['sharpe']:.3f}",
                        r['n_days'], r['pos_d'], r['neg_d'],
                        f"{r4_pd:.2f}", f"{edge_loss:.2f}"])
    print(f"[round5] wrote CSV {csv_path}", file=sys.stderr)

    full_pass = [r for r in rows if r['trades_per_day'] >= 300
                 and r['wr'] >= 0.45 and r['per_day'] >= 1000
                 and r['max_dd'] <= 5000]

    lines = []
    lines.append(f"# Round 5 strategy search results (offset={args.offset:,})\n\n")
    lines.append(f"Generated: {datetime.now().isoformat()}\n")
    lines.append(f"Period: {total_days} calendar-day buckets from offset "
                 f"{args.offset:,} (max-days={args.max_days})\n")
    lines.append(f"Tick stream: {n_lines:,} lines processed\n")
    lines.append(f"Costs applied: ${TOTAL_RT_COST:.2f}/RT, "
                 f"queue overshoot=1 tick, stop slip {STOP_SLIP_PT}pt baseline "
                 f"+ {STOP_GAP_SLIP_PROB*100:.0f}% chance of "
                 f"0-{STOP_GAP_SLIP_MAX_PT}pt extra\n")
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

    lines.append("## R4 (idealized) vs R5 (bot-faithful) -- execution edge loss\n\n")
    lines.append("| Strategy | R4 $/day | R5 $/day | Edge loss | R4 WR% | R5 WR% | R5 tr/d |\n")
    lines.append("|----------|---------:|---------:|----------:|-------:|-------:|--------:|\n")
    for r in rows:
        r4 = r4_by_name.get(r['name'], {})
        r4_pd = float(r4.get('per_day', 0) or 0)
        r4_wr = float(r4.get('wr', 0) or 0) * 100
        edge_loss = r4_pd - r['per_day']
        loss_pct = (edge_loss / max(1.0, r4_pd)) * 100 if r4_pd > 0 else 0
        lines.append(
            f"| {r['name']} | ${r4_pd:,.0f} | ${r['per_day']:,.0f} | "
            f"${edge_loss:,.0f} ({loss_pct:.0f}%) | {r4_wr:.1f} | "
            f"{r['wr']*100:.1f} | {r['trades_per_day']:.1f} |\n")
    lines.append("\n")

    lines.append(f"## Strategies meeting ALL hard requirements ({len(full_pass)})\n\n")
    if full_pass:
        for r in full_pass:
            lines.append(
                f"- **{r['name']}** -- {r['n']:,} trades "
                f"({r['trades_per_day']:.1f}/day), WR={r['wr']*100:.1f}%, "
                f"${r['per_day']:,.0f}/day, maxDD=${r['max_dd']:,.0f}, "
                f"Sharpe={r['sharpe']:.2f}\n")
    else:
        lines.append("**NONE**. Execution friction kills the edge on every "
                     "round-4 candidate.\n\n")
        lines.append("### Closest candidates (min-ratio across constraints)\n\n")
        scored = []
        for r in rows:
            if r['n'] < 10:
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
        for sc, binder, r in scored[:15]:
            lines.append(
                f"- **{r['name']}** -- min-ratio {sc:.2f} (binder: {binder}), "
                f"{r['trades_per_day']:.1f} tr/d, WR={r['wr']*100:.1f}%, "
                f"${r['per_day']:,.0f}/day, DD=${r['max_dd']:,.0f}\n")

    lines.append("\n## All strategies (sorted by R5 $/day)\n\n")
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
    print(f"[round5] wrote MD {md_path}", file=sys.stderr)

    print("\n" + "=" * 110)
    print(f"{'Strategy':>30s} {'N':>7s} {'/day':>6s} {'WR%':>5s} "
          f"{'$/day':>9s} {'$/tr':>7s} {'maxDD':>9s} {'sharpe':>6s}")
    print("=" * 110)
    for r in rows[:25]:
        flag = ""
        if r['trades_per_day'] >= 300 and r['wr'] >= 0.45 and r['per_day'] >= 1000:
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
            print(f"[round5] cleared checkpoint {ckpt_path}",
                  file=sys.stderr)
    except Exception:
        pass


if __name__ == "__main__":
    main()
