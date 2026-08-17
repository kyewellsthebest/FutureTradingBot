"""The autonomous researcher: runs until stopped, reports what it learns.

    python -m researcher.runner            run until RESEARCH_STOP exists
    RESEARCH_ONCE=1 python -m researcher.runner    one pass, then exit

WHAT PROTECTS IT FROM ITSELF

  never repeats        every hypothesis is fingerprinted in the ledger
  raises its own bar   the threshold grows as sqrt(2 ln trials), so
                       spending more compute cannot by itself produce a
                       finding. Feature-selection trials are counted in
                       that total too -- scoring 500 candidate features
                       is search, and search that is not counted is
                       search that inflates every later result
  seals a vault        the newest 20% of history is untouchable; a
                       candidate gets ONE look at it, ever, and only
                       after surviving everything else
  self-tests           every cycle it plants a synthetic edge and
                       confirms the harness finds it. If the harness
                       goes blind, the run HALTS rather than reporting
                       silence as evidence of absence

WHAT IT LEARNS, in four layers, each with a mechanism behind it

  1  FEATURES (researcher/features.py). A vocabulary that grows by
     composition, kept on dispersion rather than profit, thresholded
     against what the same machinery produces on targets that cannot
     carry information. This is the part that can find something nobody
     specified up front.
  2  CURRICULUM (researcher/data_tiers.py). Cheap and wide first, then
     expensive and fine for the few things worth measuring precisely.
     Promotion REFINES a measurement, it does not confirm it -- tier-2
     NQ tick and tier-1 NQ 5-minute bars are the same tape.
  3  FAILURE MEMORY (researcher/memory.py). Not "it lost" but WHY. The
     valuable failure is cost-bound: directionally right, move smaller
     than the round trip. The response is longer holds, which follows
     from arithmetic, not from fitting.
  4  CALIBRATION (researcher/memory.py). Every vault touch compares a
     predicted strength with a realised one. The ratio is this system's
     own overfitting coefficient. Until there are touches it reports
     UNKNOWN rather than assuming it does not overfit.

WHAT IT WILL NOT DO. It will not find an edge because it ran longer.
Continuous search buys exhaustive COVERAGE and an honest account of what
has been ruled out. If it reports nothing after two weeks, the useful
output is the map of dead ground -- which is worth having, and is the
opposite of what an unbounded parameter search produces.
"""
import gc
import json
import os
from concurrent.futures import ThreadPoolExecutor
import sys
import time
import traceback
from datetime import datetime, timezone

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from researcher.ledger import Ledger            # noqa: E402
from researcher import hypotheses as HY         # noqa: E402
from researcher.features import FeatureLibrary  # noqa: E402
from researcher.memory import Memory, classify  # noqa: E402
from researcher import data_tiers as DT         # noqa: E402
from researcher import insight as IN            # noqa: E402
from researcher import context as CTX           # noqa: E402
from researcher import validate as VAL          # noqa: E402
from researcher import brackets as BR           # noqa: E402
from researcher import destinations as DS       # noqa: E402
from researcher import plausible as PL          # noqa: E402

ROOT = os.environ.get("M2_REPO", os.getcwd())
RDIR = os.environ.get("RESEARCH_DIR", os.path.join(ROOT, "data", "research"))
STOP = os.path.join(RDIR, "RESEARCH_STOP")
STATUS = os.path.join(RDIR, "status.json")
FEED = os.path.join(RDIR, "feed.jsonl")
# PER-MARKET ECONOMICS. A market whose contract spec we cannot state is
# not scored at all -- scoring 24 markets with one market's $/point is
# how every result becomes meaningless. 6A quotes near 0.67 and moves
# 0.0001 in five minutes; multiplied by MNQ's $2/point and charged
# MNQ's $0.60, every trade scored -$0.5992 no matter what happened.
# (micro contract $/point, round-trip cost)
# AND THE COST HAS TO INCLUDE THE SPREAD, not just commission. The
# first version charged ZB $2.50 -- commission only -- while one ZB tick
# is worth $31.25 and the typical spread is exactly one tick. It then
# reported a "confirmed" 1-bar mean reversion at z=10.6 worth $3.13 net.
# The actual gross edge was 0.203 of ONE TICK. Against a real taker
# round trip of ~$33.75 that trade loses $27 every time.
#
# A taker paying the spread on entry and exit gives up one full spread
# per round trip, plus commission both ways.
#     cost = spread_ticks * tick_value + 2 * commission_per_side
# (micro $/point, tick size, $/tick, all-in round-trip cost)
# EVERY MARKET WITH DATA, and the cost computed rather than guessed:
#
#     cost = tick_in_price x $/point + commission
#
# Every tick below was VERIFIED against the tapes -- the smallest price
# change that actually occurs in each file -- rather than taken from
# memory. Point values are the smallest tradeable contract, micro where
# one exists, because that is what a $4,000 account can hold.
#
# One full spread per round trip is the taker assumption: you cross on
# the way in and on the way out, which costs one spread total against
# mid. Where a micro's tick differs from the full contract's, the
# micro's (wider) tick is used -- conservative, and conservative on cost
# is the only safe direction to be wrong.
#
# (symbol: $/point, tick in price, commission round trip)
_SPEC_RAW = {
    "NQ":  (2.0,        0.25,       0.10),   # MNQ
    "ES":  (5.0,        0.25,       0.20),   # MES
    "YM":  (0.50,       1.0,        0.20),   # MYM
    "RTY": (5.0,        0.10,       0.20),   # M2K
    "GC":  (10.0,       0.10,       0.20),   # MGC
    "HG":  (2500.0,     0.0005,     0.20),   # MHG micro copper
    "CL":  (100.0,      0.01,       0.20),   # MCL
    "NG":  (2500.0,     0.001,      0.20),   # MNG micro henry hub
    "HO":  (42000.0,    0.0001,     0.30),   # no micro
    "RB":  (42000.0,    0.0001,     0.30),   # no micro
    "ZB":  (1000.0,     0.03125,    2.50),   # no micro, tick 1/32
    "ZN":  (1000.0,     0.015625,   2.50),   # tick 1/64
    "ZF":  (1000.0,     0.0078125,  2.50),   # tick 1/128
    "ZT":  (2000.0,     0.00390625, 2.50),   # tick 1/256
    "6E":  (12500.0,    0.0001,     0.20),   # M6E
    "6A":  (10000.0,    0.0001,     0.20),   # M6A
    "6B":  (6250.0,     0.0001,     0.20),   # M6B
    "6J":  (6250000.0,  0.000001,   0.20),   # M6J
    "ZC":  (10.0,       0.125,      0.20),   # XC micro corn, $/cent
    "ZW":  (10.0,       0.125,      0.20),   # XW micro wheat
    "ZS":  (10.0,       0.125,      0.20),   # XK micro soybean
    "MBT": (0.10,       5.0,        0.20),   # micro bitcoin, 0.1 BTC
    "ETH": (0.10,       0.50,       0.20),   # micro ether, 0.1 ETH
    # SI (silver) is PERMANENTLY EXCLUDED by standing instruction.
}
SPEC = {k: (pv, round(tick * pv + comm, 4))
        for k, (pv, tick, comm) in _SPEC_RAW.items()}
VAULT_FRAC = 0.20
MIN_TRADES = 60
# dispersion floor, measured by features_selftest.py as the maximum the
# WHOLE three-generation growth reaches against targets that cannot
# carry information. Overridable, but never silently: the run prints it.
FEAT_FLOOR = float(os.environ.get("FEAT_FLOOR", "4.10"))
# Resolutions to rotate through on the deep tiers. Sixteen NQ tick
# sweeps (8 contracts x 2 resolutions... plus 15s and 300s) and six book
# sweeps before the deep space repeats -- and the feature library has
# grown a new generation on every one of them by then.
# LIVE COUNTERS. status.json is only written once a cycle, which on a
# six-minute cycle means the console's headline number sits frozen for
# minutes at a time and the whole thing looks dead. These are updated on
# every single hypothesis and read by the service directly, so the count
# on screen is the count right now.
LIVE = {"trials": 0, "tested": 0, "market": "", "tier": 0,
        "candidates": 0, "killed": 0, "started": None,
        # WHAT IT IS DOING RIGHT NOW, not just what it last scored.
        # market/tier are only set when a hypothesis is recorded, so
        # every setup phase -- loading tapes, growing features, saving a
        # 144 MB ledger -- rendered as "starting..." with a frozen
        # counter and a healthy green dot. Ten minutes of that is
        # indistinguishable from a dead process. stage is written at
        # each phase so a stall always names itself.
        "stage": "booting", "stage_t": 0.0}


def stage(what):
    LIVE["stage"] = what
    LIVE["stage_t"] = time.time()
_SHARED = __import__("threading").Lock()
WORKERS = int(os.environ.get("RESEARCH_WORKERS",
                             str(max(1, (os.cpu_count() or 2) - 1))))
T2_RES = [60, 15, 300]
T3_RES = [5, 1, 30]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- history
# THE LEARNING GRAPHS NEED POINTS MORE OFTEN THAN ONCE A CYCLE.
#
# History used to be appended at the end of a sweep. A full sweep of 23
# markets across three tiers takes hours, so for most of a day the series
# held exactly ONE point -- and a one-point series cannot be drawn. Every
# chart on the Learning tab rendered as an empty shimmering box, which
# reads as "still loading" forever rather than "one reading so far".
#
# So it is sampled on a timer as well. The cycle-end call still happens
# and is the only one that carries a round time; the sampler fills in
# between so the graphs move while you watch them.
_HIST_LOCK = __import__("threading").Lock()
_HIST_CTX = {}


def history_point(secs=None):
    """Append one row to the learning series. Safe to call from anywhere."""
    led = _HIST_CTX.get("led")
    if led is None:
        return False
    mem = _HIST_CTX.get("mem") or type("_", (), {"d": {}})()
    libs = _HIST_CTX.get("libs") or {}
    try:
        with _HIST_LOCK:
            hp = os.path.join(RDIR, "history.json")
            hist = []
            if os.path.exists(hp):
                try:
                    hist = json.load(open(hp)) or []
                except Exception:                             # noqa: BLE001
                    hist = []
            # Under the ledger's own lock: this samples from a dict that
            # every worker thread is inserting into, and iterating it
            # unlocked raises "dictionary changed size during iteration"
            # -- silently, into the try/except, so the graphs would just
            # stop gaining points with no error anywhere.
            with led._lock:
                trials = led.d["trials"]
                distinct = len(led.d["tested"])
                nkilled = sum(1 for r in led.d["tested"].values()
                              if isinstance(r, dict) and r.get("killed"))
            row = {
                "t": now(), "cycle": _HIST_CTX.get("cycle", 0),
                "trials": trials,
                "bar": round(led.bar(), 3),
                "distinct": distinct,
                "killed": nkilled,
                "survivors": len(led.d.get("survivors", [])),
                "adaptations": len(mem.d.get("adaptations", [])),
                "families": len(mem.d.get("families", {})),
                "closed": sum(1 for a in mem.d.get("adaptations", [])
                              if a.get("kind") == "closed"),
                "deduced": sum(1 for a in mem.d.get("adaptations", [])
                               if a.get("kind") == "horizon"),
                "features": sum(len(l.scores) for l in libs.values()),
                "vault": len(led.d.get("vault_touches", {})),
            }
            # Round time only exists at the end of a round. Carrying the
            # previous value forward keeps that line continuous instead
            # of collapsing to zero between sweeps.
            row["secs"] = (int(secs) if secs is not None
                           else (hist[-1].get("secs", 0) if hist else 0))
            row["sampled"] = secs is None
            # Nothing moved and this is only a sample: replace the last
            # sample rather than growing the file with a flat line.
            if (hist and row["sampled"] and hist[-1].get("sampled")
                    and hist[-1].get("trials") == row["trials"]):
                hist[-1] = row
            else:
                hist.append(row)
            json.dump(hist[-3000:], open(hp, "w"))
        return True
    except Exception as exc:                                  # noqa: BLE001
        say("history_failed", err=str(exc)[:120])
        return False


def start_history_sampler(every=60):
    import threading

    def loop():
        while True:
            time.sleep(every)
            try:
                history_point()
            except Exception:                                 # noqa: BLE001
                pass
    t = threading.Thread(target=loop, daemon=True, name="history")
    t.start()
    return t


def say(msg, **kw):
    line = {"t": now(), "msg": msg}
    line.update(kw)
    print(json.dumps(line), flush=True)
    os.makedirs(RDIR, exist_ok=True)
    with open(FEED, "a") as fh:
        fh.write(json.dumps(line) + "\n")


def split(d):
    """Search set and sealed vault. The vault is the NEWEST slice --
    the part most like the future we would trade in."""
    k = int(len(d) * (1 - VAULT_FRAC))
    return d.iloc[:k], d.iloc[k:]


def bars_per(d):
    """Seconds per bar, inferred. The evaluator converts a hold in
    seconds into a bar count, and hardcoding 300 was fine when the only
    tier was 5-minute bars. At tier 2 it would silently hold 5x too
    long and report it as the requested horizon."""
    if len(d) < 3:
        return 300.0
    dt = np.diff(d.index.values[:2000]).astype("timedelta64[s]").astype(float)
    dt = dt[dt > 0]
    return float(np.median(dt)) if len(dt) else 300.0


# =====================================================================
# THE ONE INVARIANT THAT MAKES A WHOLE CLASS OF BUG IMPOSSIBLE
#
# Five separate false positives in this project shared one shape: a
# hypothesis selected a bar using information known only AT that bar's
# close, then entered at that same close. The entry price is then
# contaminated by the selection, and the "edge" is the contamination.
#
#   the fade           entered at a level the market had already left
#   the maker fill     marked against a mid that had moved
#   ZB 1-bar reversion  feature and target shared one price print
#   close_high/low     the close IS the bar's extreme, an order
#                      statistic, so the next close reverts by
#                      construction: -10.2 pts against -0.03 baseline
#   the breakeven stop  "exited at entry" while 50 points underwater
#
# Each was caught AFTER the fact by the delay control -- and twice I
# added a new evaluation path and forgot to wire that control into it,
# so it silently passed everything. A control you have to remember is
# not a control.
#
# So the rule is now structural. EVERY path from a signal to a trade
# goes through entries() below, and entries() always moves the entry to
# the NEXT bar. There is no argument to disable it. A signal computed
# from bar t is actionable at bar t+1 and not before, which is simply
# true: you cannot transact on a bar's close until that bar has closed,
# and by then the price is gone.
#
# The delay control still runs on top as a robustness check. It now
# tests t+2 against t+1, which is a genuine extra question rather than
# the only thing standing between the searcher and nonsense.
ENTRY_LAG = 1


def entries(mask, n, extra=0):
    """Signal bars -> tradeable entry bars. The only such conversion.

    Adds ENTRY_LAG unconditionally. If a future evaluation path forgets
    to call this, it will not silently enter at the signal bar -- it
    will fail the invariant test in researcher/selftest_all.py, which
    asserts that a planted close-at-high artifact scores flat.
    """
    m = mask.values if hasattr(mask, "values") else np.asarray(mask)
    sel = np.flatnonzero(m)
    sel = sel + ENTRY_LAG + int(extra)
    return sel[(sel >= 0) & (sel < n)]


_LEVELS = {}


def _eval_dest(d, h, tv, cost, delay=0):
    """Score a destination hypothesis as the race it actually is.

    Returns the same shape of dict as everything else so the ledger,
    the bar, the gauntlet and the leaderboard need no special case --
    but the underlying measurement is a first passage, not a
    fixed-horizon return, and the stop is LEARNED here rather than
    supplied.
    """
    if "high" not in d.columns:
        return None
    k = (id(d), len(d))
    if k not in _LEVELS:
        if len(_LEVELS) > 30:
            _LEVELS.clear()
        _LEVELS[k] = (DS.build_levels(d),
                      BR.atr(d["high"].values, d["low"].values,
                             d["close"].values, 60))
    levels, unit = _LEVELS[k]
    if h["level"] not in levels:
        return None
    if h["trigger"] == "none":
        trig = np.ones(len(d), dtype=bool)
    else:
        cs = _conds(d)
        if h["trigger"] in cs:
            trig = cs[h["trigger"]]
        else:
            trig = HY.shape_mask(d, h["trigger"], 3, 2.0)
            if trig is None:
                return None
    # same invariant: the trigger is knowable at bar t, tradeable at t+1
    lag = ENTRY_LAG + delay
    trig = np.roll(np.asarray(trig), lag)
    trig[:lag] = False
    r = DS.study(d, unit, h["level"], levels, h["side"], trig,
                 int(h["max_bars"]))
    if not r or not r.get("invalidation"):
        return None
    med_unit = float(np.nanmedian(unit))
    if not np.isfinite(med_unit) or med_unit <= 0:
        return None
    cost_u = cost / (tv * med_unit)
    ev = DS.expected_value(r, cost_u)
    if not ev:
        return None
    p, rw, rk = r["p_trigger"], ev["reward"], ev["risk"]
    n = r["n_trigger"]
    # per-trade P&L in dollars, and its dispersion, so this shares the
    # significance machinery with every other family
    per = ev["ev_units"] * med_unit * tv
    var = p * (1 - p) * ((rw + rk) * med_unit * tv) ** 2
    se = (var ** 0.5) / max(n ** 0.5, 1.0)
    z = per / (se + 1e-12)
    gross = per + cost
    return {"z": round(float(z), 3), "gz": round(float(gross / (se + 1e-12)), 3),
            "edge": round(float(gross), 4), "net": round(float(per), 4),
            "n": int(n), "eff_n": int(n), "overlap": 1.0, "delay": delay,
            "win_rate": round(p, 4),
            "rr": round(rw / rk, 3) if rk else 0.0,
            "per_week": round(n / max(
                (d.index[-1] - d.index[0]).days / 7.0, 1.0), 2),
            "avg_win": round(rw * med_unit * tv, 3),
            "avg_loss": round(rk * med_unit * tv, 3),
            "lift": r["lift"], "p_base": r["p_base"],
            "stop_units": rk,
            "stop_why": r["invalidation"]["why"]}


_CONDS = {}


def _conds(d):
    """The four conditioning masks for a tape, computed once.

    Keyed by object identity plus length -- the runner holds each tape
    for the life of the process, so identity is stable, and the length
    guards against a same-address reuse after a tape is freed.
    """
    k = (id(d), len(d))
    if k in _CONDS:
        return _CONDS[k]
    extern = _EXTERN.get(k, {})
    idx = d.index
    c = d["close"]
    rv = c.diff().abs().rolling(120, min_periods=30).mean()
    # and the same problem in weaker form: thresholding on the
    # FULL-SAMPLE median of realised vol uses years of future data to
    # decide what counted as "high vol" today. A trailing median is
    # known at the time and costs nothing.
    rvmed = rv.rolling(4000, min_periods=500).median()
    day = idx.normalize()
    g = c.groupby(day)
    # LOOK-AHEAD, FIXED. This was `last - first`: the day's FULL return,
    # which at 10am you do not know. Conditioning a 10am entry on how
    # the day ends is not a filter, it is the answer. It biases every
    # up_day/dn_day cell toward a false positive, and it was in the
    # committed version. The honest quantity is the return SO FAR --
    # from the day's open to the current bar, known when the trade is
    # placed.
    dayret = c - g.transform("first")
    ok = rvmed.notna().values
    out = {"hi_vol": (rv > rvmed).values & ok,
           "lo_vol": (rv <= rvmed).values & ok,
           "up_day": (dayret > 0).values,
           "dn_day": (dayret <= 0).values}
    # EXTERNAL STATE, merged in. Every condition above is derived from
    # the same price series being predicted, which is a filter with no
    # outside information in it. These are outside information, and
    # specifically information about CONSTRAINT -- who is hedged which
    # way, who is crowded, when cash is scarce.
    out.update(extern)
    if len(_CONDS) > 40:
        _CONDS.clear()
    _CONDS[k] = out
    return out


_EXTERN = {}


def attach_context(sym, d):
    """Load external regime state for a tape and register its masks.

    Returns the condition names now available. Failure is non-fatal and
    LOUD: a missing context source means fewer conditions, and silently
    having fewer conditions looks identical to having tested them.
    """
    try:
        ctx = CTX.build(str(sym).split("@")[0], d.index)
        m = CTX.masks(ctx) if ctx is not None else {}
    except Exception as exc:                                  # noqa: BLE001
        say("context_failed", market=sym, err=str(exc)[:160])
        return []
    if not m:
        return []
    _EXTERN[(id(d), len(d))] = m
    _CONDS.pop((id(d), len(d)), None)
    return sorted(m)


# ------------------------------------------------------------ evaluation
def evaluate(d, h, tv=None, cost=None, feats=None, bar_s=None, delay=0):
    """Score one hypothesis. Returns dict with z, edge, net, n.

    `delay` shifts the ENTRY forward by that many bars while leaving the
    signal where it was. It is the control for the single most common
    fake edge in bar data, and it caught one on the first real run.

    THE BOUNCE ARTIFACT. A feature built from close[t] - close[t-1] is
    scored against close[t+1] - close[t]. Both contain close[t], so any
    noise in that one print -- a trade at the bid rather than the ask, a
    stale quote, a thin bar -- pushes the feature up and the forward
    return down at the same time. The result is a beautiful mean
    reversion that exists only in the printed series.

    On the first run this produced ZB at z=10.6, "confirmed" in the
    vault at z=7.3, apparently worth $3.13 a trade. The gross edge was
    0.203 of ONE TICK on an instrument whose tick is worth $31.25 and
    whose typical 5-minute move is exactly one tick. Lag-1
    autocorrelation of ZB 5-minute changes is -0.070: the bounce,
    exactly.

    Entering one bar later cannot touch a real prediction about the next
    hour, but it completely destroys an artifact that lives inside a
    single shared print.
    """
    tv = 2.0 if tv is None else tv
    cost = 0.60 if cost is None else cost
    bar_s = bars_per(d) if bar_s is None else bar_s
    idx = d.index

    if h.get("kind") == "dest":
        return _eval_dest(d, h, tv, cost, delay)
    if h.get("kind") == "shape":
        m = HY.shape_mask(d, h["shape"], h.get("n", 3), h.get("k", 2.0))
        if m is None:
            return None
        mask = np.asarray(m)
        if h.get("cond", "none") != "none":
            mask = mask & _conds(d)[h["cond"]]
        side = np.full(len(d), 1.0 if h["ls"] == "long" else -1.0)
    elif h.get("kind") in ("feature", "flow"):
        if h["kind"] == "flow":
            x = HY.flow_series(d, h["mech"])
        else:
            x = feats.get(h["feat"]) if feats else None
        if x is None:
            return None
        ok = np.isfinite(x)
        if ok.sum() < MIN_TRADES * 5:
            return None
        cut = np.nanpercentile(x[ok], 80 if h["side"] == "hi" else 20)
        mask = (x >= cut) if h["side"] == "hi" else (x <= cut)
        mask = mask & ok
        side = np.where(np.ones(len(d)) > 0,
                        1.0 if h["ls"] == "long" else -1.0, 0.0)
    else:
        if h["dim"] == "minute_of_day":
            hh, mm = (int(v) for v in str(h["bucket"]).split(":"))
            mask = (idx.hour == hh) & (idx.minute == mm)
        elif h["dim"] == "day_of_month":
            mask = idx.day == int(h["bucket"])
        else:
            mask = idx.dayofweek == int(h["bucket"])
        if h["cond"] != "none":
            # PRECOMPUTED. These four masks are identical for every
            # hypothesis on this tape, and the day-return one is a
            # groupby-transform with a Python lambda over ~150k rows.
            # Recomputing it per hypothesis made a 500-hypothesis sweep
            # cost minutes instead of seconds -- the same work, done
            # 400 times.
            conds = _conds(d)
            mask = np.asarray(mask) & conds[h["cond"]]
        sign = np.sign(d["close"].diff().fillna(0.0)).values
        side = sign if h["dir"] == "with" else -sign

    bars = max(int(round(h["hold_s"] / bar_s)), 1)

    # ---- BRACKETED EXIT. A stop and a target, in units of realised
    # volatility, resolved bar by bar with the stop winning any bar that
    # touches both. This is the difference between a prediction and a
    # strategy, and it is what makes win rate and reward-to-risk mean
    # anything -- a fixed time exit produces ~50% wins and RR~1 by
    # construction.
    ex = h.get("exit")
    if ex and "high" in d.columns and "low" in d.columns:
        unit = BR.atr(d["high"].values, d["low"].values,
                      d["close"].values, 60)
        m0 = mask.values if hasattr(mask, "values") else np.asarray(mask)
        sel = entries(m0, len(d), delay)
        sel = sel[np.isfinite(unit[sel]) & (unit[sel] > 0)]
        # DELAY APPLIES HERE TOO. The first version of this branch
        # ignored `delay` entirely, so the one-bar delay control -- the
        # gate that exists specifically to kill signals that live inside
        # a single price print -- silently did nothing for every
        # bracketed hypothesis, which is now the largest family. It
        # passed them all with kept_frac 1.00 because it was handing
        # back the identical number.
        #
        # It let through "after close_high, go short": close_high
        # selects bars where the close IS the bar's maximum, an extreme
        # order statistic, so the next close reverts by construction --
        # -10.2 points on NQ 60s against an unconditional -0.03. Not
        # tradable: you cannot know close[t] was the high until the bar
        # has ended, and by then that price is gone.
        sel = sel[sel + 1 < len(d)]
        if len(sel) < MIN_TRADES:
            return None
        maxb = max(int(round(h["hold_s"] / bar_s)), 1)
        res = BR.pnl(sel, side[sel] if hasattr(side, "__len__") else side,
                     d["high"].values, d["low"].values, d["close"].values,
                     float(ex[0]), float(ex[1]), unit, maxb, tv, cost,
                     open_=(d["open"].values if "open" in d.columns
                            else None))
        net = res["net"]
        if len(net) < MIN_TRADES:
            return None
        gap = float(np.median(np.diff(sel))) if len(sel) > 1 else float(maxb)
        ov = float(np.clip(np.median(res["held"]) / max(gap, 1.0),
                           1.0, float(maxb)))
        eff = max(len(net) / ov, 2.0)
        z = float(net.mean() / (net.std(ddof=1) / np.sqrt(eff) + 1e-12))
        gross = net + cost
        gz = float(gross.mean() / (gross.std(ddof=1) / np.sqrt(eff) + 1e-12))
        wins, losses = net[net > 0], net[net < 0]
        aw = float(wins.mean()) if len(wins) else 0.0
        al = float(-losses.mean()) if len(losses) else 0.0
        span = max((idx[-1] - idx[0]).total_seconds() / 86400.0, 1.0)
        return {"z": round(z, 3), "gz": round(gz, 3),
                "edge": round(float(gross.mean()), 4),
                "net": round(float(net.mean()), 4), "n": int(len(net)),
                "eff_n": int(eff), "overlap": round(ov, 2), "delay": delay,
                "win_rate": round(float(len(wins) / len(net)), 4),
                "rr": round(aw / al, 3) if al > 0 else 0.0,
                "per_week": round(len(net) / (span / 7.0), 2),
                "avg_win": round(aw, 3), "avg_loss": round(al, 3),
                "stopped": round(res["stopped"], 3),
                "targeted": round(res["targeted"], 3),
                "timed": round(res["timed"], 3),
                "tie_share": BR.resolution_cost(res["ties"], len(net))}

    # entry at t+delay, exit `bars` later. delay=0 is entry at the
    # signal bar's own close, which is where the bounce artifact lives.
    c = d["close"]
    lag = ENTRY_LAG + delay
    fwd = c.shift(-(bars + lag)) - c.shift(-lag)
    same = idx.normalize().values == \
        pd.Series(idx).shift(-(bars + lag)).dt.normalize().values
    fwd = fwd.where(same)
    m = mask.values if hasattr(mask, "values") else np.asarray(mask)
    raw = side * fwd.values
    sel = np.flatnonzero(m & np.isfinite(raw))
    if len(sel) < MIN_TRADES:
        return None
    pnl = raw[sel]

    # OVERLAP, measured rather than assumed. Holding `bars` bars while
    # trading every bar means consecutive trades share most of their
    # path, and the naive standard error is then too small.
    #
    # But the correction depends on how far apart the trades ACTUALLY
    # are, not on the hold alone. A minute-of-day cell fires once per
    # session -- 78 bars apart on a 5-minute tape -- so a 36-bar hold
    # produces no overlap at all. Dividing those by 36 anyway was
    # over-correcting by a factor of six, which does not manufacture a
    # finding but does hide real ones, and a test that only catches
    # errors in the flattering direction is half a test.
    gap = float(np.median(np.diff(sel))) if len(sel) > 1 else float(bars)
    ov = float(np.clip(bars / max(gap, 1.0), 1.0, float(bars)))
    net = pnl * tv - cost
    eff = max(len(net) / ov, 2.0)
    se = net.std(ddof=1) / np.sqrt(eff)
    z = float(net.mean() / (se + 1e-12))

    # GROSS z, for the empirical null. The net z is dominated by the
    # cost: almost every cell loses close to a full round trip, so |z|
    # of net runs to 20+ and an "empirical null" built from it would
    # measure how reliably trading costs money, not how much noise the
    # search manufactures. Under a true null the GROSS mean is zero, so
    # gross z is the quantity whose distribution is the null.
    gross = pnl * tv
    gse = gross.std(ddof=1) / np.sqrt(eff)
    gz = float(gross.mean() / (gse + 1e-12))

    # Trade economics, for the leaderboard. Reported on NET, because
    # that is what a trade actually returns.
    wins = net[net > 0]
    losses = net[net < 0]
    win_rate = float(len(wins) / len(net)) if len(net) else 0.0
    avg_w = float(wins.mean()) if len(wins) else 0.0
    avg_l = float(-losses.mean()) if len(losses) else 0.0
    rr = float(avg_w / avg_l) if avg_l > 0 else 0.0
    span_days = max((idx[-1] - idx[0]).total_seconds() / 86400.0, 1.0)
    per_week = float(len(net) / (span_days / 7.0))

    return {"z": round(z, 3), "gz": round(gz, 3),
            "edge": round(float(pnl.mean() * tv), 4),
            "net": round(float(net.mean()), 4), "n": int(len(net)),
            "eff_n": int(eff), "overlap": round(ov, 2), "delay": delay,
            "win_rate": round(win_rate, 4), "rr": round(rr, 3),
            "per_week": round(per_week, 2),
            "avg_win": round(avg_w, 3), "avg_loss": round(avg_l, 3)}


def selftest(d, tv=None, cost=None, bar_s=None):
    """Plant a known edge and confirm the evaluator finds it.

    The plant has to match what the evaluator MEASURES, which is a
    FORWARD return conditioned on the sign of the last move. A jump at
    the bar itself is already history by then -- the first version of
    this planted exactly that and correctly failed, which is the test
    catching its own author rather than the harness.
    """
    x = d.copy()
    idx = x.index
    hh, mm = 14, 15
    hit = np.asarray((idx.hour == hh) & (idx.minute == mm))
    if hit.sum() < MIN_TRADES * 2:
        return True                      # too little data to self-test
    # SCALE THE PLANT TO THE INSTRUMENT. A fixed 2.0 points is huge for
    # FX and smaller than the 5-minute noise in ES -- and because the
    # evaluator takes direction from sign(close.diff()), a plant under
    # the noise gets the sign wrong a third of the time and half the
    # planted edge disappears. That produced a false HALT on ES while
    # the harness was working correctly.
    step = float(np.nanmedian(np.abs(np.diff(x["close"].values))))
    amp = max(4.0 * step, 1e-9)
    inc = np.zeros(len(x))
    inc[hit] = amp
    inc[np.roll(hit, 1)] = amp           # and the bar AFTER it
    # AND THE BAR AFTER THAT. Entry is now structurally at t+1
    # (ENTRY_LAG), so a plant that finishes moving at t+1 leaves nothing
    # for the trade to capture and the harness would report itself
    # blind. The plant has to extend past the entry, not up to it.
    inc[np.roll(hit, 2)] = amp
    x["close"] = x["close"].values + np.cumsum(inc)
    bs = bars_per(d) if bar_s is None else bar_s
    h = {"kind": "footprint", "dim": "minute_of_day",
         "bucket": f"{hh:02d}:{mm:02d}", "metric": "vol", "dir": "with",
         "hold_s": bs, "cond": "none"}
    r = evaluate(x, h, tv, cost, bar_s=bs)
    return r is not None and r["z"] > 3.0


def feats_of(libs, sym, tier, name, tape):
    """Recompute one named feature on an arbitrary slice.

    The vault and the delay control both need the feature evaluated on
    a tape the library never grew on. Recomputing from the stored spec
    is the only safe way -- reusing the search-set array would silently
    misalign, and a misaligned feature does not error, it just returns
    a different number.
    """
    lib = libs.get(f"{sym}/t{tier}")
    spec = lib.kept.get(name) if lib else None
    if spec is None:
        return None
    try:
        return FeatureLibrary.evaluate_spec(tape, spec, {})
    except Exception:                                         # noqa: BLE001
        return None


def _pnl_series(d, h, tv, cost, feats, bar_s):
    """Per-trade net P&L in chronological order, for stability testing.

    Recomputed rather than returned from evaluate() so the ordering is
    guaranteed to be chronological -- period stability split on a
    reordered series would silently test nothing.
    """
    try:
        r = evaluate(d, h, tv, cost, feats, bar_s)
        if not r:
            return None
        import numpy as _np
        idx = d.index
        if h.get("kind") == "flow":
            x = HY.flow_series(d, h["mech"])
        elif h.get("kind") == "feature":
            x = (feats or {}).get(h["feat"])
        else:
            x = None
        bars = max(int(round(h["hold_s"] / bar_s)), 1)
        c = d["close"]
        fwd = (c.shift(-bars) - c)
        same = idx.normalize().values == \
            pd.Series(idx).shift(-bars).dt.normalize().values
        fwd = fwd.where(same).values
        if x is not None:
            okx = _np.isfinite(x)
            cut = _np.nanpercentile(x[okx], 80 if h["side"] == "hi" else 20)
            m = ((x >= cut) if h["side"] == "hi" else (x <= cut)) & okx
            side = _np.full(len(d), 1.0 if h.get("ls") == "long" else -1.0)
        else:
            if h["dim"] == "minute_of_day":
                hh, mm = (int(v) for v in str(h["bucket"]).split(":"))
                m = (idx.hour == hh) & (idx.minute == mm)
            elif h["dim"] == "day_of_month":
                m = idx.day == int(h["bucket"])
            else:
                m = idx.dayofweek == int(h["bucket"])
            m = _np.asarray(m)
            if h["cond"] != "none":
                m = m & _conds(d)[h["cond"]]
            sgn = _np.sign(c.diff().fillna(0.0)).values
            side = sgn if h["dir"] == "with" else -sgn
        raw = side * fwd
        sel = _np.flatnonzero(m & _np.isfinite(raw))
        if len(sel) < MIN_TRADES:
            return None
        return raw[sel] * tv - cost
    except Exception:                                         # noqa: BLE001
        return None


def fwd_for_features(d, bars=1):
    y = (d["close"].shift(-bars) - d["close"]).values
    same = d.index.normalize().values == \
        pd.Series(d.index).shift(-bars).dt.normalize().values
    return np.where(same, y, np.nan)


# ------------------------------------------------------------------ loop
def sweep(sym, d, led, mem, libs, tier, tv, cost, budget=500,
          base_cols=None, points=None, mrows=None):
    """One market, one tier: grow features, build hypotheses, score."""
    srch, vault = split(d)
    bar_s = bars_per(d)
    if not selftest(srch, tv, cost, bar_s):
        return None, f"selftest failed on {sym} tier{tier}: harness blind"

    # ---- layer 1: grow the vocabulary (search set only, never vault)
    stage(f"{sym} tier {tier}: building features")
    lib = libs.setdefault(f"{sym}/t{tier}", FeatureLibrary(keep=20))
    y = fwd_for_features(srch, 1)
    before = len(lib.scores)
    kept = lib.grow(srch, y, np.random.default_rng(led.d["trials"] % 9973),
                    base_cols=base_cols)
    # every feature scored is a trial. Not counting them would let the
    # search buy hundreds of extra looks for free and keep the bar low.
    led.bump(max(len(lib.scores) - before, 0))

    memo = {}
    feats = {}
    for nm, spec in lib.kept.items():
        try:
            feats[nm] = FeatureLibrary.evaluate_spec(srch, spec, memo)
        except Exception:                                     # noqa: BLE001
            continue
    del memo

    # ---- layer 3: what past failures license
    fam_mult = {}
    ctx_conds = attach_context(sym, srch)
    if ctx_conds:
        say("context", market=sym, tier=tier, conditions=ctx_conds)

    deduced = {}
    for fam in list((mem.insights().get("horizons") or {})):
        th = mem.target_horizon(fam)
        if th:
            deduced[fam] = [th]
    hyps = HY.expand(HY.find_footprints(srch), extra_holds=deduced,
                     extra_conds=ctx_conds)
    for h in hyps:
        fam_mult.setdefault(h["_family"], mem.hold_multiplier(h["_family"]))
    for fam, mult in list(fam_mult.items()):
        if mult != 1.0:
            n_changed = 0
            for h in hyps:
                if h["_family"] == fam:
                    h["hold_s"] = int(h["hold_s"] * mult)
                    n_changed += 1
            # RECORD THE CHANGE, not just the lesson. A system that
            # displays what it learned but cannot show what it did
            # differently is a logging system wearing a learning
            # system's clothes.
            mem.adapt("hold", fam,
                      before=f"{HY.HOLDS_S}s",
                      after=f"{[int(x * mult) for x in HY.HOLDS_S]}s",
                      why=mem.lesson(fam)[0])
    # ORDER-FLOW MECHANISMS, where the columns exist. These are the only
    # hypotheses in the system with a reason stated before the test --
    # everything else is a footprint, which is a place a reason might
    # have left a mark.
    flow_cols = set(srch.columns)
    if {"imb", "depl", "tflow"} & flow_cols:
        fh = HY.from_flow(flow_cols,
                          mem.hold_multiplier("flow/queue_depletion"),
                          extra_holds=deduced)
        hyps += fh
        say("flow_hypotheses", market=sym, tier=tier, n=len(fh),
            mechanisms=sorted({h["mech"] for h in fh}))

    # RECURRING PRICE BEHAVIOUR, sampled fresh every cycle. This is the
    # family that keeps the space from running out: the full cross
    # product of shape x parameter x direction x exit x condition is
    # ~15,000 per market, and drawing at random each cycle covers it
    # evenly over weeks while the ledger's fingerprints guarantee
    # nothing is ever tested twice.
    if "high" in srch.columns:
        rng_s = np.random.default_rng(
            (led.d["trials"] * 7919 + len(srch)) % (2**32))
        sh = HY.from_shapes(rng_s, cap=700, extra_conds=ctx_conds)
        hyps += sh

    # DESTINATIONS. The only family where the exit is measured rather
    # than chosen: find where price keeps travelling, find what precedes
    # the journey, then learn the point at which the journey has failed.
    if "high" in srch.columns:
        rng_d = np.random.default_rng(
            (led.d["trials"] * 6151 + len(srch) * 13) % (2**32))
        dh = HY.from_destinations(
            rng_d, list(ctx_conds) + ["squeeze", "expansion", "run_up",
                                      "run_dn", "inside", "outside"],
            cap=350)
        hyps += dh

    fmult = mem.hold_multiplier("feature/d1")
    if fmult != 1.0:
        mem.adapt("hold", "feature/d1",
                  before=f"{HY.HOLDS_S}s",
                  after=f"{[int(x * fmult) for x in HY.HOLDS_S]}s",
                  why=mem.lesson("feature/d1")[0])
    hyps += HY.from_features(sorted(lib.scores.items(), key=lambda kv: -kv[1]),
                             FEAT_FLOOR, fmult)
    for fam in {h["_family"] for h in hyps}:
        pr = led.family_prior(fam)
        if pr < 0.5:
            f = led.d["families"].get(fam, {})
            mem.adapt("effort", fam, before="1.00x",
                      after=f"{pr:.2f}x",
                      why=(f"{f.get('n', 0)} hypotheses tested in this "
                           f"family, best z {f.get('best_z', 0):.2f}, "
                           f"nothing cleared the bar -- effort reduced, "
                           f"not stopped, since a family is not disproved "
                           f"by its members failing"))
    hyps.sort(key=lambda h: -led.family_prior(h["_family"]))

    done = 0
    cands = []
    allz = []
    for h in hyps:
        if os.path.exists(STOP):
            break
        fam = h.pop("_family", None)
        h["market"] = sym
        h["tier"] = tier
        if led.seen(h):
            continue
        try:
            r = evaluate(srch, h, tv, cost, feats, bar_s)
        except Exception as exc:                              # noqa: BLE001
            say("eval_error", err=str(exc)[:160], hyp=HY.describe(h))
            continue
        bar = led.bar()
        mode = classify(r, bar, cost)
        mem.note(fam, mode, r)
        if r is None:
            continue
        # EVIDENCE FOR THE INFERENCE ENGINE. Gross edge against horizon,
        # pooled per family, is what the horizon-crossing fit reads.
        # Gross, not net -- the whole question is where the growing
        # gross curve meets the flat cost line, and netting cost off
        # first destroys exactly that.
        with _SHARED:
          if points is not None:
            # IN UNITS OF THIS MARKET'S OWN COST. Pooling raw dollars
            # across markets compares ZB's $31 tick with MNQ's $0.50
            # and then judges the pool against one of them; that is the
            # same "one market's economics" error that made every 6A
            # trade score -$0.5992. A ratio of 1.0 means "paid for
            # itself here", and that means the same thing everywhere.
            points.setdefault(fam, []).append(
                (h["hold_s"], r["edge"] / cost if cost > 0 else 0.0))
          if mrows is not None:
            mrows.setdefault(fam, []).append((sym, r["edge"]))
        allz.append(r.get("gz", r["z"]))
        led.record(h, r, family=fam)
        done += 1
        LIVE["trials"] = led.d["trials"]
        LIVE["tested"] += 1
        LIVE["market"] = sym
        LIVE["tier"] = tier
        if mode == "confirmed":
            cands.append((dict(h), fam, r, bar, srch, vault, bar_s))
        if done >= budget:
            break
    # THE EMPIRICAL NULL for this sweep: what |z| the same machinery
    # reached across every cell it scored. Candidates are judged against
    # their own siblings, which accounts for the dependence between
    # hypotheses that a theoretical correction cannot see.
    # COVERAGE. How much of what was generated this cycle was already
    # in the ledger. A tape that returns 100% seen has been exhausted at
    # this resolution, and that has to be SAID -- a searcher quietly
    # regenerating hypotheses it has already tested looks identical from
    # outside to one finding nothing new, and only one of those is a
    # reason to add data.
    gen = len(hyps)
    fresh = done
    cov = 1.0 - (fresh / max(gen, 1))
    if cov > 0.97:
        say("EXHAUSTED", market=sym, tier=tier, generated=gen,
            new=fresh, seen_pct=round(cov * 100, 1),
            why="every hypothesis this tape can generate at this "
                "resolution has already been tested. More search here "
                "buys nothing; more DATA or a finer resolution would.")

    null99 = VAL.empirical_null(allz)
    if null99:
        say("empirical_null", market=sym, tier=tier, cells=len(allz),
            p99=round(null99, 2), theoretical_bar=round(led.bar(), 2))
    cands = [(*c, null99, mrows) for c in cands]
    return (done, cands, kept), None


def _tape_for(market):
    """Rebuild the exact tape a stored hypothesis was tested on.

    Market names carry their tape: "NQ" is tier 1, "NQ@NQU4@60s" is the
    NQU4 contract at 60-second bars, "NQbook@5s" is the book. Evaluating
    a tier-2 hypothesis against tier-1 five-minute bars would return a
    number -- a wrong one, silently -- so the name has to be honoured.
    """
    m = str(market)
    try:
        if m.startswith("NQbook@"):
            res = int(m.split("@")[1].rstrip("s"))
            return DT.tier3(bar_s=res), "NQ"
        if "@" in m:
            parts = m.split("@")
            contract, res = parts[1], int(parts[2].rstrip("s"))
            for name, kind, path in DT.tier2_sources(res):
                if name == contract:
                    return DT.tier2_from(kind, path, res), "NQ"
            return None, None
        return None, m
    except Exception:                                     # noqa: BLE001
        return None, None


def backfill_metrics(led, data, k=40, budget_s=45.0):
    """Fill trades/week, win rate and RR on older ledger entries.

    THE TWO REASONS THE FIRST VERSION NEVER FILLED ANYTHING, both of
    which left "measuring..." on screen permanently:

      1  it passed feats=None, so every FEATURE hypothesis returned None
         immediately -- and the top of the leaderboard is almost all
         feature hypotheses
      2  it looked up tier-1 data by symbol, so a tier-2 hypothesis on
         "NQ@NQU4@60s" was scored against five-minute bars, which is a
         different tape and a different answer

    Now the tape is rebuilt from the stored market name and features are
    reconstructed from their names via FeatureLibrary.parse. Re-scoring
    is NOT a new trial -- the hypothesis is already counted -- so only
    the stored result gains fields and the bar is untouched.
    """
    t0 = time.time()
    n = 0
    cache = {}
    for row in led.near_misses(k):
        if time.time() - t0 > budget_s:
            break
        rec = led.d["tested"].get(row["fp"]) or {}
        if not isinstance(rec, dict) or rec.get("stub"):
            continue
        r = rec.get("result") or {}
        # TWO INDEPENDENT JOBS, and conflating them meant neither ran.
        # The first version skipped any row that already had metrics --
        # which also skipped the control re-check on exactly the rows
        # that needed it, since a freshly scored artifact has full
        # metrics and has never been re-checked.
        need_metrics = bool(r) and r.get("win_rate") is None
        need_check = bool(r) and not rec.get("checked") \
            and not rec.get("killed")
        # a third job: rows measured on a tape that has since been
        # corrected need measuring again, not filtering away.
        need_rescore = bool(r) and led.outdated(rec) \
            and not rec.get("rescored")
        if not (need_metrics or need_check or need_rescore):
            continue
        h = dict(row["hyp"] or {})
        market = h.get("market", "")
        base = str(market).split("@")[0]
        if base not in SPEC:
            continue
        if market in cache:
            tape = cache[market]
        else:
            tape, _ = _tape_for(market)
            if tape is None:
                tape = data.get(base)
            cache[market] = tape
        if tape is None or len(tape) < 1000:
            continue
        tv, cost = SPEC[base]
        srch, _ = split(tape)
        bs = bars_per(srch)

        feats = None
        if h.get("kind") == "feature":
            spec = FeatureLibrary.parse(h.get("feat", ""))
            if spec is None:
                continue
            try:
                feats = {h["feat"]:
                         FeatureLibrary.evaluate_spec(srch, spec, {})}
            except Exception:                             # noqa: BLE001
                continue
        try:
            fresh = evaluate(srch, h, tv, cost, feats, bs)
        except Exception:                                 # noqa: BLE001
            continue
        if not fresh:
            continue
        # RE-STAMP THE EPOCH. This re-score just ran on the CURRENT tape,
        # so if the row was carrying an old epoch -- a measurement of
        # data that has since been corrected -- it is not carrying one
        # any more. Replace the numbers wholesale rather than patching
        # fields onto a stale result, and re-stamp. Without this a row
        # invalidated by a data fix stays flagged forever even after it
        # has been measured again on good data.
        if led.outdated(rec):
            rec["result"] = r = dict(fresh)
            rec["epoch"] = led.DATA_EPOCH
            rec["code_epoch"] = led.CODE_EPOCH
            rec["rescored"] = True
        elif need_metrics:
            for key in ("win_rate", "rr", "per_week", "gz",
                        "avg_win", "avg_loss"):
                if fresh.get(key) is not None:
                    r[key] = fresh[key]

        # RE-CHECK AGAINST CONTROLS THAT DID NOT EXIST WHEN IT WAS
        # SCORED. The ledger is permanent and lives on a volume, so an
        # artifact found before a control was written stays at the top
        # of the leaderboard forever unless something goes back for it.
        try:
            rd = evaluate(srch, h, tv, cost, feats, bs, delay=1)
            keep = (rd["net"] / fresh["net"]) if (rd and fresh["net"]) else 0
            if not rd or rd["net"] <= 0 or keep < 0.5:
                led.kill(h, [f"re-checked against the delay control: "
                             f"${fresh['net']:+.2f} becomes "
                             f"${(rd or {}).get('net', 0):+.2f} when "
                             f"entered one bar later ({keep:.0%} kept). "
                             f"This was scored before that control "
                             f"existed."])
            else:
                rec["checked"] = True
        except Exception:                                     # noqa: BLE001
            pass
        n += 1
    return n


def gauntlet(sym, tier, cands, led, mem, libs, tv, cost):
    """What a candidate must survive, in order, before it is believed.

    The order is deliberate. The delay control runs FIRST because it is
    cheap and because the vault is a finite resource -- spending the one
    permitted look at held-back data on a bid-ask bounce artifact burns
    it forever. On the first real run this gate would have caught a ZB
    "confirmed" result that had already reached the vault.
    """
    for h, fam, r, bar, srch, vault, bar_s, null99, mrows in cands:
        LIVE["candidates"] += 1
        say("CANDIDATE", market=sym, tier=tier, z=r["z"],
            bar=round(bar, 2), net=r["net"], n=r["n"], what=HY.describe(h))

        # THE SNIFF TEST, before the controls. Every bug in this project
        # was found by noticing a number that could not be true and
        # reasoning back to its cause. That step is now encoded: an
        # implausible result is not merely rejected, it points at the
        # specific machinery most likely to be broken.
        base = str(sym).split("@")[0]
        tickv = None
        if base in _SPEC_RAW:
            pv, tick, _c = _SPEC_RAW[base]
            tickv = pv * tick
        odd = PL.check_result(r, h, cost, tickv)
        if odd:
            say("IMPLAUSIBLE", market=sym, tier=tier,
                what=HY.describe(h),
                flags=[{"observed": a, "means": b, "look_at": c}
                       for a, b, c in odd],
                note="this is a candidate to DOUBT, not to celebrate -- "
                     "every finding this large in this project has so "
                     "far been a bug, and the suspects are listed")
            LIVE["killed"] += 1
            led.kill(h, [a for a, _b, _c in odd])
            mem.note(fam, "no_signal", r)
            continue

        # 1. BOUNCE GATE. Entering one bar later cannot hurt a real
        # prediction about the next hour, but it annihilates an artifact
        # that lives inside a single shared print: a feature built from
        # close[t]-close[t-1] scored against close[t+1]-close[t] shares
        # close[t] with its own target, so noise in that one print moves
        # both, and the "mean reversion" is the bid-ask bounce.
        fe = {}
        if h.get("kind") == "feature":
            fe = {h["feat"]: feats_of(libs, sym, tier, h["feat"], srch)}
        rd = evaluate(srch, h, tv, cost, fe, bar_s, delay=1)
        kept_frac = (rd["net"] / r["net"]) if (rd and r["net"]) else 0.0
        if not rd or rd["net"] <= 0 or kept_frac < 0.5:
            say("KILLED_by_delay_control", market=sym, tier=tier,
                immediate_net=r["net"], delayed_net=(rd or {}).get("net"),
                kept=round(kept_frac, 3), what=HY.describe(h),
                why="entering one bar later destroys it -- bid-ask "
                    "bounce inside the signal bar's own print, not a "
                    "prediction")
            mem.note(fam, "wrong_sign", rd)
            led.kill(h, ["entering one bar later destroys it -- bid-ask "
                         "bounce inside the signal bar's own print"])
            continue

        # 2. the empirical bar, once there is calibration to raise it by
        ebar, why = mem.empirical_bar(bar)
        if ebar > bar + 0.01:
            mem.adapt("bar", "all", before=f"{bar:.2f} sigma",
                      after=f"{ebar:.2f} sigma", why=why)
        if r["z"] < ebar:
            say("below_empirical_bar", need=round(ebar, 2), why=why,
                what=HY.describe(h))
            continue

        # 3. the vault. One look, ever.
        if not led.can_touch_vault(h):
            continue
        vfeats = {}
        if h.get("kind") == "feature":
            vfeats = {h["feat"]: feats_of(libs, sym, tier, h["feat"], vault)}
            if vfeats[h["feat"]] is None:
                continue
        rv = evaluate(vault, h, tv, cost, vfeats, bar_s)
        led.touch_vault(h, rv or {})
        mem.note_vault(fam, r["z"], (rv or {}).get("z"),
                       r["n"], (rv or {}).get("n"))
        ok = bool(rv and rv["z"] > 2.0 and rv["net"] > 0)
        mem.note(fam, "confirmed" if ok else "vault_killed", rv)
        say("VAULT_RESULT", confirmed=ok, market=sym, tier=tier, vault=rv,
            delayed_net=rd["net"], what=HY.describe(h),
            note="survived the delay control and the vault. This is a "
                 "CANDIDATE for the full gauntlet -- all-cell null, "
                 "quarter stability, stale placebo, bot-exact "
                 "simulation -- not a strategy.")


def main():
    os.makedirs(RDIR, exist_ok=True)
    stage("loading the ledger")
    led = Ledger(os.path.join(RDIR, "ledger.json"))
    mem = Memory(os.path.join(RDIR, "memory.json"))
    stage("ledger loaded (%s entries)" % len(led.d["tested"]))
    once = os.environ.get("RESEARCH_ONCE") == "1"
    LIVE["trials"] = led.d["trials"]
    LIVE["started"] = now()
    say("boot", trials=led.d["trials"], bar=round(led.bar(), 2),
        feat_floor=FEAT_FLOOR, shrinkage=mem.shrinkage())

    stage("loading tier-1 data for %d markets" % len(SPEC))
    data = DT.tier1(set(SPEC))
    if not data:
        say("no_data")
        return
    say("loaded_tier1", markets=sorted(data), n=len(data),
        effective_n=DT.effective_n(sorted(data)),
        note="correlated markets are not independent evidence")

    libs = {}
    cycle = 0
    # Hand the sampler live references so the learning graphs gain a
    # point every minute instead of once a sweep.
    _HIST_CTX.update(led=led, mem=mem, libs=libs, cycle=0)
    history_point()
    start_history_sampler(int(os.environ.get("RESEARCH_HIST_S", "60")))
    while True:
        if os.path.exists(STOP):
            say("stopped_by_file", path=STOP)
            break
        cycle += 1
        _HIST_CTX["cycle"] = cycle
        t0 = time.time()
        points, mrows, vols = {}, {}, {}
        # PARALLEL ACROSS MARKETS. Markets are independent -- each
        # sweep reads its own tape and writes only its own results --
        # so the only shared state is the ledger and the memory, and
        # both are written on the main thread after the workers return.
        #
        # Threads rather than processes on purpose: the work is numpy
        # and pandas, which release the GIL for the array operations
        # that dominate, and processes would need every tape pickled
        # to each worker. Measured, not assumed -- see the timing in
        # the commit.
        syms = [s for s in data if not os.path.exists(STOP)]
        for sym in syms:
            vols[sym] = float(data[sym]["close"].diff().abs().median() or 0.0)

        def _run(sym):
            tv, cost = SPEC[sym]
            try:
                return sym, sweep(sym, data[sym], led, mem, libs, 1,
                                  tv, cost, points=points, mrows=mrows)
            except Exception as exc:                          # noqa: BLE001
                return sym, (None, f"sweep crashed on {sym}: "
                                   f"{str(exc)[:200]}")

        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            results = list(ex.map(_run, syms))

        for sym, (out, err) in results:
            if os.path.exists(STOP):
                break
            tv, cost = SPEC[sym]
            if err:
                led.halt(err)
                say("HALT_selftest_failed", why=err)
                led.save(force=True)
                mem.save()
                return
            done, cands, kept = out
            gauntlet(sym, 1, cands, led, mem, libs, tv, cost)
            stage(f"{sym}: saving the ledger")
            led.save()
            mem.save()
            say("cycle_market", cycle=cycle, market=sym, tier=1, tested=done,
                features=len(kept), trials=led.d["trials"],
                bar=round(led.bar(), 2))
            gc.collect()

        # ---- tier 2: NQ tick, one contract per cycle, 60-second bars.
        # This is where "merge the deep data" actually happens. It runs
        # after the breadth sweep because it is ~40x the compute, and
        # one contract at a time because 4.7 GB of tick data will not
        # fit alongside anything else on a box with no swap.
        if not os.path.exists(STOP):
            res_probe = T2_RES[0]
            cs = DT.tier2_sources(res_probe)
            if not cs:
                # LOUD. A tier that is absent looks identical to a tier
                # that found nothing, and the second is a result while
                # the first is a broken deployment. data/tick/ is
                # gitignored (4.7 GB), so on any deploy target this
                # means build_deep_bars.py was never run or its output
                # was never committed.
                say("TIER2_MISSING", searched=DT.BARS,
                    why="no deep-tier bars and no raw tick data. The "
                        "searcher is running on tier 1 and tier 3 only "
                        "-- a third of its data is absent. Run "
                        "researcher/build_deep_bars.py where the raw "
                        "ticks live and commit data/research_bars/.")
            if cs:
                # ROTATE CONTRACT AND RESOLUTION. The hypothesis space is
                # bounded on purpose -- that is what keeps the bar
                # meaningful -- so it exhausts in hours if the only axis
                # is which footprint. Resolution is a genuine second
                # axis: the same question asked of 15-second bars and of
                # 5-minute bars is two different questions, because the
                # move size that has to clear a fixed cost differs by
                # sqrt(20). It is not the same test repeated.
                res = T2_RES[((cycle - 1) // len(cs)) % len(T2_RES)]
                srcs = DT.tier2_sources(res) or cs
                name, kind, p = srcs[(cycle - 1) % len(srcs)]
                cn = f"{name}@{res}s"
                try:
                    a = DT.tier2_from(kind, p, res)
                except Exception as exc:                      # noqa: BLE001
                    a = None
                    say("tier2_load_failed", contract=cn, err=str(exc)[:150])
                if a is not None and len(a) > 5000:
                    tv, cost = SPEC["NQ"]
                    out, err = sweep(f"NQ@{cn}", a, led, mem, libs, 2,
                                     tv, cost, budget=400,
                                     points=points, mrows=mrows)
                    if err:
                        say("tier2_selftest_failed", why=err)
                    else:
                        done, cands, kept = out
                        gauntlet(f"NQ@{cn}", 2, cands, led, mem, libs,
                                 tv, cost)
                        say("cycle_market", cycle=cycle,
                            market=f"NQ@{cn}", tier=2, tested=done,
                            features=len(kept), bars=len(a),
                            trials=led.d["trials"], bar=round(led.bar(), 2),
                            note=DT.Curriculum.caveat(1, 2, "NQ"))
                    del a
                led.save()
                mem.save()
                gc.collect()

        # ---- tier 3: NQ top-of-book. Queue depletion, add rates,
        # spread and trade flow exist at no other tier and cannot be
        # reconstructed from trades, so these hypotheses ENTER here
        # rather than being screened first -- and pay the higher bar of
        # one market and four weeks.
        if not os.path.exists(STOP) and cycle % 2 == 1:
            res3 = T3_RES[((cycle - 1) // 2) % len(T3_RES)]
            try:
                b = DT.tier3(bar_s=res3)
            except Exception as exc:                          # noqa: BLE001
                b = None
                say("tier3_load_failed", err=str(exc)[:150])
            if b is not None and len(b) > 5000:
                tv, cost = SPEC["NQ"]
                out, err = sweep(f"NQbook@{res3}s", b, led, mem, libs, 3,
                                 tv, cost,
                                 budget=400,
                                 base_cols=["close", "vol", "n", "absret",
                                            "imb", "spread", "qrate",
                                            "depl", "adds", "tflow"],
                                 points=points, mrows=mrows)
                if err:
                    say("tier3_selftest_failed", why=err)
                else:
                    done, cands, kept = out
                    gauntlet(f"NQbook@{res3}s", 3, cands, led, mem, libs,
                             tv, cost)
                    say("cycle_market", cycle=cycle,
                        market=f"NQbook@{res3}s",
                        tier=3, tested=done, features=len(kept),
                        bars=len(b), trials=led.d["trials"],
                        bar=round(led.bar(), 2))
                del b
            led.save()
            mem.save()
            gc.collect()

        # ---- BACKFILL. The leaderboard reports trades/week, win rate
        # and RR, which older ledger entries predate. The ledger never
        # retests by design, so without this the best entries would show
        # blanks permanently -- the top row is the top row precisely
        # because nothing has beaten it. Re-scoring is NOT a new trial:
        # the hypothesis is already counted, and this only fills in
        # fields on the stored result.
        try:
            stage("re-checking older results against current controls")
            filled = backfill_metrics(led, data)
            if filled:
                say("backfilled_metrics", rows=filled)
        except Exception as exc:                              # noqa: BLE001
            say("backfill_failed", err=str(exc)[:160])

        # ---- INFER. Everything above measured; this deduces.
        # edges are already normalised to each market's own cost, so
        # break-even is the ratio 1.0 for every family alike
        ins = IN.build(points, {f: 1.0 for f in points}, mrows, vols, SPEC)
        mem.set_insights(ins)
        for fam, hz in (ins.get("horizons") or {}).items():
            if hz.get("fits") and hz.get("reachable"):
                # This is the inference CHANGING the search: the next
                # cycle will test this family at the deduced horizon,
                # which nobody put in the list.
                mem.adapt("horizon", fam,
                          before=f"{HY.HOLDS_S if not fam.startswith('flow/') else HY.FLOW_HOLDS_S}s",
                          after=f"+{hz['h_star']}s (deduced)",
                          why=hz["why"])
            elif hz.get("fits"):
                # hz["why"] already explains why it is out of reach --
                # appending a second sentence saying the same thing
                # produced the doubled paragraph on the console.
                mem.adapt("closed", fam, before="searching",
                          after=f"crossing at {IN._dur(hz['h_star'])}",
                          why=hz["why"])
        hz_all = ins.get("horizons") or {}
        sysodd = PL.check_system(
            families_total=len(hz_all),
            families_fitting=sum(1 for h in hz_all.values()
                                 if h.get("fits")),
            survivors=len(led.d.get("survivors", [])),
            candidates=None)
        if sysodd:
            say("SYSTEM_IMPLAUSIBLE",
                flags=[{"observed": a, "means": b, "look_at": c}
                       for a, b, c in sysodd])

        say("inferred", horizons=len(hz_all),
            reachable=sum(1 for h in (ins.get("horizons") or {}).values()
                          if h.get("fits") and h.get("reachable")),
            frontier_best=[r["market"] for r in ins.get("frontier", [])[:5]])
        mem.save()

        history_point(secs=round(time.time() - t0))

        led.save(force=True)
        json.dump({"t": now(), "cycle": cycle, "summary": led.summary(),
                   "learning": mem.summary(), "insight": ins},
                  open(STATUS, "w"), indent=1)
        say("cycle_done", cycle=cycle, secs=round(time.time() - t0),
            **led.summary())
        say("lessons", **mem.summary())
        if once:
            break
        time.sleep(int(os.environ.get("RESEARCH_SLEEP", "30")))
    led.save(force=True)
    mem.save()
    say("exit", **led.summary())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        say("interrupted")
    except Exception:                                         # noqa: BLE001
        say("crash", tb=traceback.format_exc()[-1500:])
        raise
