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
SPEC = {
    "NQ":  (2.0,    0.60),   # MNQ  tick 0.25 = $0.50; user's stated
                             #      all-in figure including slippage
    "ES":  (5.0,    1.45),   # MES  tick 0.25 = $1.25 + $0.20 comms
    "YM":  (0.50,   0.70),   # MYM  tick 1.0  = $0.50 + $0.20
    "RTY": (5.0,    0.70),   # M2K  tick 0.10 = $0.50 + $0.20
    "GC":  (10.0,   1.20),   # MGC  tick 0.10 = $1.00 + $0.20
    "CL":  (100.0,  1.20),   # MCL  tick 0.01 = $1.00 + $0.20
    "ZB":  (1000.0, 33.75),  # no micro. tick 1/32 = $31.25 + $2.50
    "ZN":  (1000.0, 18.13),  # tick 1/64  = $15.63 + $2.50
    "ZF":  (1000.0, 10.31),  # tick 1/128 = $7.81  + $2.50
    "ZT":  (2000.0, 10.31),  # tick 1/256 = $7.81  + $2.50
}
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
T2_RES = [60, 15, 300]
T3_RES = [5, 1, 30]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
    if len(_CONDS) > 40:
        _CONDS.clear()
    _CONDS[k] = out
    return out


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

    if h.get("kind") == "feature":
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
    # entry at t+delay, exit `bars` later. delay=0 is entry at the
    # signal bar's own close, which is where the bounce artifact lives.
    c = d["close"]
    fwd = c.shift(-(bars + delay)) - c.shift(-delay)
    same = idx.normalize().values == \
        pd.Series(idx).shift(-(bars + delay)).dt.normalize().values
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
    return {"z": round(z, 3), "edge": round(float(pnl.mean() * tv), 4),
            "net": round(float(net.mean()), 4), "n": int(len(net)),
            "eff_n": int(eff), "overlap": round(ov, 2), "delay": delay}


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


def fwd_for_features(d, bars=1):
    y = (d["close"].shift(-bars) - d["close"]).values
    same = d.index.normalize().values == \
        pd.Series(d.index).shift(-bars).dt.normalize().values
    return np.where(same, y, np.nan)


# ------------------------------------------------------------------ loop
def sweep(sym, d, led, mem, libs, tier, tv, cost, budget=500,
          base_cols=None):
    """One market, one tier: grow features, build hypotheses, score."""
    srch, vault = split(d)
    bar_s = bars_per(d)
    if not selftest(srch, tv, cost, bar_s):
        return None, f"selftest failed on {sym} tier{tier}: harness blind"

    # ---- layer 1: grow the vocabulary (search set only, never vault)
    lib = libs.setdefault(f"{sym}/t{tier}", FeatureLibrary(keep=20))
    y = fwd_for_features(srch, 1)
    before = len(lib.scores)
    kept = lib.grow(srch, y, np.random.default_rng(led.d["trials"] % 9973),
                    base_cols=base_cols)
    # every feature scored is a trial. Not counting them would let the
    # search buy hundreds of extra looks for free and keep the bar low.
    led.d["trials"] += max(len(lib.scores) - before, 0)

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
    hyps = HY.expand(HY.find_footprints(srch))
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
        led.record(h, r, family=fam)
        done += 1
        if mode == "confirmed":
            cands.append((dict(h), fam, r, bar, srch, vault, bar_s))
        if done >= budget:
            break
    return (done, cands, kept), None


def gauntlet(sym, tier, cands, led, mem, libs, tv, cost):
    """What a candidate must survive, in order, before it is believed.

    The order is deliberate. The delay control runs FIRST because it is
    cheap and because the vault is a finite resource -- spending the one
    permitted look at held-back data on a bid-ask bounce artifact burns
    it forever. On the first real run this gate would have caught a ZB
    "confirmed" result that had already reached the vault.
    """
    for h, fam, r, bar, srch, vault, bar_s in cands:
        say("CANDIDATE", market=sym, tier=tier, z=r["z"],
            bar=round(bar, 2), net=r["net"], n=r["n"], what=HY.describe(h))

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
    led = Ledger(os.path.join(RDIR, "ledger.json"))
    mem = Memory(os.path.join(RDIR, "memory.json"))
    once = os.environ.get("RESEARCH_ONCE") == "1"
    say("boot", trials=led.d["trials"], bar=round(led.bar(), 2),
        feat_floor=FEAT_FLOOR, shrinkage=mem.shrinkage())

    data = DT.tier1(set(SPEC))
    if not data:
        say("no_data")
        return
    say("loaded_tier1", markets=sorted(data), n=len(data),
        effective_n=DT.effective_n(sorted(data)),
        note="correlated markets are not independent evidence")

    libs = {}
    cycle = 0
    while True:
        if os.path.exists(STOP):
            say("stopped_by_file", path=STOP)
            break
        cycle += 1
        t0 = time.time()
        for sym, d in data.items():
            if os.path.exists(STOP):
                break
            tv, cost = SPEC[sym]
            out, err = sweep(sym, d, led, mem, libs, 1, tv, cost)
            if err:
                led.halt(err)
                say("HALT_selftest_failed", why=err)
                led.save()
                mem.save()
                return
            done, cands, kept = out
            gauntlet(sym, 1, cands, led, mem, libs, tv, cost)
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
                                     tv, cost, budget=400)
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
                                            "depl", "adds", "tflow"])
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

        json.dump({"t": now(), "cycle": cycle, "summary": led.summary(),
                   "learning": mem.summary()},
                  open(STATUS, "w"), indent=1)
        say("cycle_done", cycle=cycle, secs=round(time.time() - t0),
            **led.summary())
        say("lessons", **mem.summary())
        if once:
            break
        time.sleep(int(os.environ.get("RESEARCH_SLEEP", "30")))
    led.save()
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
