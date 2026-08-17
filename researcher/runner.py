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
SPEC = {
    "NQ":  (2.0,    0.60),   # MNQ
    "ES":  (5.0,    0.60),   # MES
    "YM":  (0.50,   0.60),   # MYM
    "RTY": (5.0,    0.60),   # M2K
    "GC":  (10.0,   0.60),   # MGC
    "CL":  (100.0,  0.60),   # MCL
    "ZB":  (1000.0, 2.50),   # no micro
    "ZN":  (1000.0, 2.50),
    "ZF":  (1000.0, 2.50),
    "ZT":  (2000.0, 2.50),
}
VAULT_FRAC = 0.20
MIN_TRADES = 60
# dispersion floor, measured by features_selftest.py as the maximum the
# WHOLE three-generation growth reaches against targets that cannot
# carry information. Overridable, but never silently: the run prints it.
FEAT_FLOOR = float(os.environ.get("FEAT_FLOOR", "4.10"))


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
def evaluate(d, h, tv=None, cost=None, feats=None, bar_s=None):
    """Score one hypothesis. Returns dict with z, edge, net, n."""
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
    fwd = d["close"].shift(-bars) - d["close"]
    same = idx.normalize().values == \
        pd.Series(idx).shift(-bars).dt.normalize().values
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
            "eff_n": int(eff), "overlap": round(ov, 2)}


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


def fwd_for_features(d, bars=1):
    y = (d["close"].shift(-bars) - d["close"]).values
    same = d.index.normalize().values == \
        pd.Series(d.index).shift(-bars).dt.normalize().values
    return np.where(same, y, np.nan)


# ------------------------------------------------------------------ loop
def sweep(sym, d, led, mem, libs, tier, tv, cost, budget=500):
    """One market, one tier: grow features, build hypotheses, score."""
    srch, vault = split(d)
    bar_s = bars_per(d)
    if not selftest(srch, tv, cost, bar_s):
        return None, f"selftest failed on {sym} tier{tier}: harness blind"

    # ---- layer 1: grow the vocabulary (search set only, never vault)
    lib = libs.setdefault(f"{sym}/t{tier}", FeatureLibrary(keep=20))
    y = fwd_for_features(srch, 1)
    before = len(lib.scores)
    kept = lib.grow(srch, y, np.random.default_rng(led.d["trials"] % 9973))
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
            for h in hyps:
                if h["_family"] == fam:
                    h["hold_s"] = int(h["hold_s"] * mult)
    fmult = mem.hold_multiplier("feature/d1")
    hyps += HY.from_features(sorted(lib.scores.items(), key=lambda kv: -kv[1]),
                             FEAT_FLOOR, fmult)
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
            cands.append((dict(h), fam, r, bar, vault, bar_s))
        if done >= budget:
            break
    return (done, cands, kept), None


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
            for h, fam, r, bar, vault, bar_s in cands:
                say("CANDIDATE", market=sym, tier=1, z=r["z"],
                    bar=round(bar, 2), net=r["net"], n=r["n"],
                    what=HY.describe(h))
                # layer 4: the empirical bar, once there is calibration
                ebar, why = mem.empirical_bar(bar)
                if r["z"] < ebar:
                    say("below_empirical_bar", need=round(ebar, 2), why=why)
                    continue
                if not led.can_touch_vault(h):
                    continue
                vfeats = {}
                if h.get("kind") == "feature":
                    spec = libs[f"{sym}/t1"].kept.get(h["feat"])
                    if spec is None:
                        continue
                    vfeats[h["feat"]] = FeatureLibrary.evaluate_spec(
                        vault, spec, {})
                rv = evaluate(vault, h, tv, cost, vfeats, bar_s)
                led.touch_vault(h, rv or {})
                mem.note_vault(fam, r["z"], (rv or {}).get("z"),
                               r["n"], (rv or {}).get("n"))
                ok = bool(rv and rv["z"] > 2.0 and rv["net"] > 0)
                mem.note(fam, "confirmed" if ok else "vault_killed", rv)
                say("VAULT_RESULT", confirmed=ok, vault=rv,
                    what=HY.describe(h))
            led.save()
            mem.save()
            say("cycle_market", cycle=cycle, market=sym, tested=done,
                features=len(kept), trials=led.d["trials"],
                bar=round(led.bar(), 2))
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
