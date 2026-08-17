"""The autonomous researcher: runs until stopped, reports what it learns.

    python -m researcher.runner            run until RESEARCH_STOP exists
    RESEARCH_ONCE=1 python -m researcher.runner    one pass, then exit

WHAT IT ACTUALLY DOES, and what "learning" honestly means here.

  never repeats        every hypothesis is fingerprinted in the ledger
  raises its own bar   the threshold grows as sqrt(2 ln trials), so
                       spending more compute cannot by itself produce a
                       finding
  seals a vault        the newest 20% of history is untouchable; a
                       candidate gets ONE look at it, ever, and only
                       after surviving everything else
  self-tests           every cycle it plants a synthetic edge and
                       confirms the harness finds it. If the harness
                       goes blind, the run HALTS rather than reporting
                       silence as evidence of absence
  reallocates          families that produce nothing across many trials
                       get less effort. Not zero -- a family is not
                       disproved by its members failing -- but less

That last one is the only "learning" claimed, and it is deliberately
modest. Anything stronger would be a model fitted to which of its own
guesses looked good, which is the exact mechanism that produced ledger
entry #19: 1.38 billion configs with a MEASURED NEGATIVE return to
searching harder.

WHAT IT WILL NOT DO. It will not find an edge because it ran longer.
Continuous search buys exhaustive COVERAGE of a bounded space, and an
honest account of what has been ruled out. If it reports nothing after
two weeks, the useful output is the map of dead ground -- which is worth
having, and is the opposite of what an unbounded parameter search
produces.
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


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def say(msg, **kw):
    line = {"t": now(), "msg": msg}
    line.update(kw)
    print(json.dumps(line), flush=True)
    os.makedirs(RDIR, exist_ok=True)
    with open(FEED, "a") as fh:
        fh.write(json.dumps(line) + "\n")


# ----------------------------------------------------------------- data
def load_bars():
    """1-minute bars for every market with data on disk."""
    import glob
    out = {}
    poly = os.path.join(ROOT, "data", "polygon")
    for p in sorted(glob.glob(os.path.join(poly, "*_5min.csv"))):
        sym = os.path.basename(p).split("_")[0]
        if sym not in SPEC:
            continue
        try:
            d = pd.read_csv(p)
            d["ts"] = pd.to_datetime(d["ts"], utc=True)
            d = d.set_index("ts").sort_index()
            d = d[~d.index.duplicated(keep="last")]
            if len(d) < 5000:
                continue
            d["absret"] = d["close"].diff().abs()
            d["n"] = d.get("volume", pd.Series(1, index=d.index))
            d["vol"] = d["n"]
            out[sym] = d
        except Exception as exc:                              # noqa: BLE001
            say("load_failed", sym=sym, err=str(exc)[:120])
    return out


def split(d):
    """Search set and sealed vault. The vault is the NEWEST slice --
    the part most like the future we would trade in."""
    k = int(len(d) * (1 - VAULT_FRAC))
    return d.iloc[:k], d.iloc[k:]


# ------------------------------------------------------------ evaluation
def evaluate(d, h, tv=None, cost=None):
    """Score one hypothesis. Returns dict with z, edge, n."""
    tv = 2.0 if tv is None else tv
    cost = 0.60 if cost is None else cost
    idx = d.index
    if h["dim"] == "minute_of_day":
        hh, mm = (int(x) for x in str(h["bucket"]).split(":"))
        mask = (idx.hour == hh) & (idx.minute == mm)
    elif h["dim"] == "day_of_month":
        mask = idx.day == int(h["bucket"])
    else:
        mask = idx.dayofweek == int(h["bucket"])
    if h["cond"] != "none":
        rv = d["close"].diff().abs().rolling(120, min_periods=30).mean()
        dayret = d["close"].groupby(idx.normalize()).transform(
            lambda s: s.iloc[-1] - s.iloc[0])
        if h["cond"] == "hi_vol":
            mask &= (rv > rv.median()).values
        elif h["cond"] == "lo_vol":
            mask &= (rv <= rv.median()).values
        elif h["cond"] == "up_day":
            mask &= (dayret > 0).values
        elif h["cond"] == "dn_day":
            mask &= (dayret <= 0).values

    bars = max(int(h["hold_s"] / 300), 1)          # 5-min bars
    fwd = d["close"].shift(-bars) - d["close"]
    same = idx.normalize().values == \
        pd.Series(idx).shift(-bars).dt.normalize().values
    fwd = fwd.where(same)
    sign = np.sign(d["close"].diff().fillna(0.0))
    side = sign if h["dir"] == "with" else -sign
    pnl = (side * fwd).values[mask.values if hasattr(mask, "values") else mask]
    pnl = pnl[np.isfinite(pnl)]
    if len(pnl) < MIN_TRADES:
        return None
    net = pnl * tv - cost
    z = float(net.mean() / (net.std(ddof=1) / np.sqrt(len(net))
                            + 1e-12))
    return {"z": round(z, 3), "edge": round(float(pnl.mean() * tv), 4),
            "net": round(float(net.mean()), 4), "n": int(len(net))}


def selftest(d, tv=None, cost=None):
    """Plant a known edge and confirm the evaluator finds it.

    The plant has to match what the evaluator MEASURES, which is a
    FORWARD return conditioned on the sign of the last move. A jump at
    the bar itself is already history by then -- the first version of
    this planted exactly that and correctly failed, which is the test
    catching its own author rather than the harness.

    So: at the chosen bucket, push the bar up AND push the next bar up
    again. The last move is then positive and the forward move is
    positive, so "trade with the move here" must be found.
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
    h = {"dim": "minute_of_day", "bucket": f"{hh:02d}:{mm:02d}",
         "metric": "vol", "dir": "with", "hold_s": 300, "cond": "none"}
    r = evaluate(x, h, tv, cost)
    return r is not None and r["z"] > 3.0


# ------------------------------------------------------------------ loop
def main():
    os.makedirs(RDIR, exist_ok=True)
    led = Ledger(os.path.join(RDIR, "ledger.json"))
    once = os.environ.get("RESEARCH_ONCE") == "1"
    say("boot", trials=led.d["trials"], bar=led.bar())

    data = load_bars()
    if not data:
        say("no_data")
        return
    say("loaded", markets=sorted(data), n=len(data))

    cycle = 0
    while True:
        if os.path.exists(STOP):
            say("stopped_by_file", path=STOP)
            break
        cycle += 1
        t0 = time.time()
        for sym, d in data.items():
            tv, cost = SPEC[sym]
            srch, vault = split(d)

            if not selftest(srch, tv, cost):
                led.halt(f"selftest failed on {sym}: harness blind")
                say("HALT_selftest_failed", sym=sym)
                led.save()
                return

            fps = HY.find_footprints(srch)
            hyps = HY.expand(fps)
            # effort follows the family prior
            hyps.sort(key=lambda h: -led.family_prior(h["_family"]))
            done = 0
            for h in hyps:
                if os.path.exists(STOP):
                    break
                fam = h.pop("_family", None)
                h["market"] = sym
                if led.seen(h):
                    continue
                try:
                    r = evaluate(srch, h, tv, cost)
                except Exception as exc:                      # noqa: BLE001
                    say("eval_error", err=str(exc)[:160],
                        hyp=HY.describe(h))
                    continue
                if r is None:
                    continue
                led.record(h, r, family=fam)
                done += 1
                bar = led.bar()
                if r["z"] >= bar and r["net"] > 0:
                    say("CANDIDATE", market=sym, z=r["z"], bar=round(bar, 2),
                        net=r["net"], n=r["n"], what=HY.describe(h))
                    if led.can_touch_vault(h):
                        rv = evaluate(vault, h, tv, cost)
                        led.touch_vault(h, rv or {})
                        ok = bool(rv and rv["z"] > 2.0 and rv["net"] > 0)
                        say("VAULT_RESULT", confirmed=ok,
                            vault=rv, what=HY.describe(h))
                if done >= 400:
                    break
            led.save()
            say("cycle_market", cycle=cycle, market=sym, tested=done,
                trials=led.d["trials"], bar=round(led.bar(), 2))
            gc.collect()

        json.dump({"t": now(), "cycle": cycle,
                   "summary": led.summary()},
                  open(STATUS, "w"), indent=1)
        say("cycle_done", cycle=cycle, secs=round(time.time() - t0),
            **led.summary())
        if once:
            break
        time.sleep(int(os.environ.get("RESEARCH_SLEEP", "30")))
    led.save()
    say("exit", **led.summary())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        say("interrupted")
    except Exception:                                         # noqa: BLE001
        say("crash", tb=traceback.format_exc()[-1500:])
        raise
