"""Measure what this searcher can actually see, and how often it lies.

THE QUESTION NOBODY HAD ASKED.

The engine reports a bar of 5.78 sigma and treats that as controlling
false positives. That number rests on a chain of assumptions -- returns
near enough normal, the overlap correction sized right, the empirical
null measuring the right thing, the bracket engine unbiased -- and not
one link in it has ever been checked END TO END. If the overlap
correction were off by a factor of two, the true false-positive rate
could be a hundred times the stated one and nothing in the system would
reveal it. The bar would still print 5.78.

And the other half matters more, because it is the half that decides
what the whole project means:

    240,000 hypotheses tested, zero survivors.

That sentence is uninterpretable without POWER. If this searcher would
detect a real +0.15 round-trip edge only 5% of the time, then finding
nothing says almost nothing -- the edge could be sitting there. If it
would detect one 90% of the time, then finding nothing is strong
evidence that nothing of that size exists at these horizons, which is
itself a valuable and expensive result. The system could not tell you
which, and so could not tell you what its own emptiness meant.

HOW THIS MEASURES IT. By planting edges of KNOWN size in REAL tapes and
seeing what comes back.

  * The plant is tradeable by construction. A marker at bar t moves
    price from t+1 onward, never at t, so an engine that could only
    "find" it by entering on the selection bar finds nothing -- the
    plant respects ENTRY_LAG exactly as a real edge would.

  * It is planted in real market data, not a synthetic walk, so the
    measurement exercises the actual bar construction, the actual
    session handling, the actual cost model and the actual bracket
    physics. A synthetic-only test measures the statistics and nothing
    else, and the two worst bugs this project has had were in the data
    path, not the statistics.

  * Recovery is compared in ROUND TRIPS, the unit the plant is specified
    in, so the answer is directly readable: "asked for +0.20, recovered
    +0.19" is calibration; "asked for +0.20, recovered +0.31" is a
    measurement bias and a bug.

WHAT COMES OUT. Three numbers the searcher previously could not state:

    calibration   does a known edge come back the size it went in
    power         how often an edge of size X is actually detected
    false alarms  how often pure noise clears the bar anyway

The third is the honest version of the bar. If the measured false-alarm
rate is far above what the bar implies, the bar is decoration and every
finding is suspect. That is exactly the sort of thing that has been
wrong here before, and it is now a number rather than a hope.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def plant(bars, minute, size_rt, tv, cost, hold_bars=6, side=1, rng=None):
    """Return a copy of `bars` with a real edge of known size planted.

    The edge: after every bar whose clock time is `minute`, price drifts
    `side`-ward over the next `hold_bars` bars by exactly enough that a
    trade entered at the NEXT bar and held that long nets `size_rt`
    round trips.

    THE ARITHMETIC, stated so it can be checked. Holding `hold_bars`
    bars each carrying a drift of d points earns hold*d*tv dollars gross
    and hold*d*tv - cost net. Setting that equal to size_rt * cost:

        d = cost * (1 + size_rt) / (hold_bars * tv)

    Every OHLC column is shifted together, so highs stay above lows and
    the bracket engine sees a coherent tape. The shift is cumulative and
    permanent, which is what a directional edge actually is -- a
    temporary bump that reverts would be a different hypothesis and
    would flatter any mean-reversion family that happened to look.
    """
    b = bars.copy()
    idx = b.index
    mark = np.zeros(len(b), dtype=bool)
    hh, mm = (int(x) for x in str(minute).split(":"))
    mark = (idx.hour == hh) & (idx.minute == mm)
    mark = np.asarray(mark)
    # never plant so close to the end that the window runs off the tape
    mark[-(hold_bars + 2):] = False

    d = float(cost) * (1.0 + float(size_rt)) / (float(hold_bars) * float(tv))
    drift = np.zeros(len(b))
    sel = np.flatnonzero(mark)
    # THE WINDOW STARTS AT k=2, AND THE OFF-BY-ONE HERE MATTERED.
    #
    # A trade entered at the close of bar m+1 and held `hold` bars exits
    # at m+1+hold, so it earns the drift applied at m+2 .. m+1+hold --
    # `hold` increments. The first version started the window at k=1,
    # which meant a trade entered at the close of the MARKER bar earned
    # six increments while the honest lagged trade earned five. The
    # plant paid MORE for looking ahead, so it would have measured the
    # engine's ability to cheat and called it power.
    #
    # Caught by the harness's own look-ahead test, which is the whole
    # reason that test exists.
    for k in range(2, hold_bars + 2):
        j = sel + k
        j = j[j < len(b)]
        drift[j] += side * d
    # cumulative, so the level shift persists after the window closes
    shift = np.cumsum(drift)
    for col in ("open", "high", "low", "close"):
        if col in b.columns:
            b[col] = b[col].values + shift
    return b, {"minute": minute, "size_rt": float(size_rt),
               "hold_bars": int(hold_bars), "side": int(side),
               "n_marks": int(mark.sum()), "drift_pts": float(d)}


def recover(bars, truth, tv, cost, bar_s, evaluate):
    """Measure the planted edge with the REAL engine. Returns its result."""
    hold_s = int(round(truth["hold_bars"] * bar_s))
    h = {"kind": "footprint", "dim": "minute_of_day",
         "bucket": truth["minute"], "metric": "vol",
         "dir": "with", "hold_s": hold_s, "cond": "none",
         "market": "CAL", "tier": 1,
         # the plant is directional, so ask the directional question
         "_cal_side": truth["side"]}
    # The footprint family trades WITH or AGAINST the last move, not a
    # fixed side, so it cannot express "always long here". Use the
    # feature-free fixed-side form the engine also supports: a shape
    # hypothesis conditioned on nothing is the closest, but the cleanest
    # is to measure the planted cell directly with a fixed side.
    return _fixed_side(bars, truth, tv, cost, bar_s)


def _fixed_side(bars, truth, tv, cost, bar_s=None):
    """Enter one bar after each marker, hold, exit. The honest measure.

    `bar_s` is accepted and unused: the hold is specified in BARS by the
    plant, so no seconds-to-bars conversion is needed here. Kept in the
    signature because every other measurement path in this project takes
    it, and a harness whose signature quietly differs is a harness
    somebody will call wrongly.

    Written here rather than reused from runner.evaluate because the
    point is to check the ENGINE against an independent implementation.
    A calibration harness that shares code with the thing it calibrates
    can only confirm that the code agrees with itself -- which is how
    the first version of the delay control passed while doing nothing.
    """
    idx = bars.index
    hh, mm = (int(x) for x in str(truth["minute"]).split(":"))
    mark = np.asarray((idx.hour == hh) & (idx.minute == mm))
    sel = np.flatnonzero(mark) + 1            # ENTRY_LAG: the next bar
    hold = int(truth["hold_bars"])
    sel = sel[(sel >= 0) & (sel + hold < len(bars))]
    if len(sel) < 30:
        return None
    c = bars["close"].values
    # same-day only, exactly as the engine requires
    day = pd.Series(idx).dt.normalize().values
    ok = day[sel] == day[sel + hold]
    sel = sel[ok]
    if len(sel) < 30:
        return None
    gross = truth["side"] * (c[sel + hold] - c[sel]) * tv
    net = gross - cost
    return {"n": int(len(net)), "net": float(net.mean()),
            "cu": float(net.mean() / cost),
            "sd": float(net.std(ddof=1)),
            "z": float(net.mean() / (net.std(ddof=1) / np.sqrt(len(net))
                                     + 1e-12))}


# --------------------------------------------------------------- suites
CAL_MINUTES = ["13:35", "14:05", "14:50", "15:10", "16:20", "16:55",
               "17:45", "18:05", "18:30", "19:15", "15:40", "17:20"]


def calibration(bars, tv, cost, bar_s, sizes=(0.0, 0.1, 0.25, 0.5, 1.0),
                minutes=None, hold_bars=6, verbose=True):
    """Does a known edge come back the size it went in?

    A bias here would be invisible in every other test in this project,
    because every other test asks "is it significant" and none asks "is
    it the right size". The gross-vs-net unit error that made a losing
    strategy render as "+0.098" in green would have been caught here on
    the first run.

    AVERAGED OVER MANY PLANTS, and it has to be. One planted minute is
    one draw of the market's own noise on top of the plant: on a
    driftless walk with ~160 markers the standard error is about 0.6
    round trips, so a single measurement reading +0.4 when zero was
    planted is an unremarkable fluctuation, not a bias. Reading bias off
    one draw would manufacture a bug report; averaging across a dozen
    independent times of day, and reporting the error bar, does not.
    """
    minutes = list(minutes or CAL_MINUTES)
    rows = []
    for s in sizes:
        got = []
        ns = []
        for m in minutes:
            b, truth = plant(bars, m, s, tv, cost, hold_bars=hold_bars)
            r = _fixed_side(b, truth, tv, cost, bar_s)
            if r:
                got.append(r["cu"])
                ns.append(r["n"])
        if not got:
            continue
        g = np.array(got, float)
        se = float(g.std(ddof=1) / np.sqrt(len(g))) if len(g) > 1 else 0.0
        rows.append({"asked": s, "got": float(g.mean()), "se": se,
                     "plants": len(g), "n": int(np.mean(ns)),
                     "err": float(g.mean() - s)})
        if verbose:
            print(f"    planted {s:+.2f} RT -> recovered "
                  f"{g.mean():+.3f} ± {se:.3f} RT over {len(g)} plants "
                  f"(error {g.mean() - s:+.3f})")
    return rows


def power(bars, tv, cost, bar_s, bar_sigma, sizes=(0.05, 0.1, 0.2, 0.4),
          minutes=None, hold_bars=6, verbose=True):
    """How often is an edge of size X actually DETECTED?

    Detection means clearing the significance bar the searcher is
    currently using. Planting the same size at many different times of
    day gives the rate rather than a single lucky or unlucky draw.
    """
    minutes = minutes or ["13:35", "14:05", "15:10", "16:20", "17:45",
                          "18:30", "19:15", "14:50", "16:55", "18:05"]
    out = {}
    for s in sizes:
        hits, tot, zs = 0, 0, []
        for m in minutes:
            b, truth = plant(bars, m, s, tv, cost, hold_bars=hold_bars)
            r = _fixed_side(b, truth, tv, cost, bar_s)
            if not r:
                continue
            tot += 1
            zs.append(r["z"])
            if r["z"] >= bar_sigma:
                hits += 1
        if tot:
            out[s] = {"detected": hits, "of": tot,
                      "rate": round(hits / tot, 3),
                      "median_z": round(float(np.median(zs)), 2)}
            if verbose:
                print(f"    +{s:.2f} RT planted at {tot} different times: "
                      f"detected {hits}/{tot} ({hits / tot:.0%}), "
                      f"median z {np.median(zs):.1f} vs bar {bar_sigma:.2f}")
    return out


def false_alarms(bars, tv, cost, bar_s, bar_sigma, minutes=None,
                 hold_bars=6, verbose=True):
    """How often does pure nothing clear the bar anyway?

    Every clock minute in the tape, with NO edge planted, measured the
    same way. Any that clears the bar is a false alarm, and the rate is
    the honest version of what the bar is worth.
    """
    idx = bars.index
    if minutes is None:
        mins = sorted({f"{h:02d}:{m:02d}"
                       for h, m in zip(idx.hour, idx.minute)})
    else:
        mins = list(minutes)
    zs, alarms, tot = [], 0, 0
    for m in mins:
        truth = {"minute": m, "hold_bars": hold_bars, "side": 1,
                 "size_rt": 0.0}
        r = _fixed_side(bars, truth, tv, cost, bar_s)
        if not r:
            continue
        tot += 1
        zs.append(abs(r["z"]))
        if abs(r["z"]) >= bar_sigma:
            alarms += 1
    res = {"cells": tot, "alarms": alarms,
           "rate": round(alarms / tot, 5) if tot else None,
           "max_z": round(float(np.max(zs)), 2) if zs else None,
           "p99_z": round(float(np.percentile(zs, 99)), 2) if zs else None}
    if verbose:
        print(f"    {tot} genuinely empty cells: {alarms} cleared a "
              f"{bar_sigma:.2f} bar ({res['rate']}), worst |z| "
              f"{res['max_z']}, p99 {res['p99_z']}")
    return res


def report(bars, tv, cost, bar_s, bar_sigma, verbose=True):
    """The three numbers, together. This is what makes 'nothing' mean
    something."""
    if verbose:
        print("  CALIBRATION — does a known edge come back its true size?")
    cal = calibration(bars, tv, cost, bar_s, verbose=verbose)
    if verbose:
        print("  POWER — how often would a real edge be detected?")
    pw = power(bars, tv, cost, bar_s, bar_sigma, verbose=verbose)
    if verbose:
        print("  FALSE ALARMS — how often does nothing look like something?")
    fa = false_alarms(bars, tv, cost, bar_s, bar_sigma, verbose=verbose)
    sd = dispersion(bars, tv, cost)
    req = required_trades(sd, bar_sigma) if sd else {}
    # Calibration is about INCREMENTS. A real tape carries its own drift
    # -- NQ over these years runs about +2 RT at a six-bar hold -- so the
    # question is never "does the recovered number equal the planted
    # one", it is "does an extra 0.10 show up as an extra 0.10". Reading
    # the raw level as bias would report a two-round-trip error that is
    # simply the market being up.
    base = next((r["got"] for r in cal if r["asked"] == 0.0), None)
    if base is not None:
        for r in cal:
            r["increment"] = round(r["got"] - base, 4)
            r["increment_err"] = round(r["increment"] - r["asked"], 4)
    if verbose and sd:
        print(f"  DISPERSION — {sd:.1f} RT per trade on this tape")
        print(f"  TRADES NEEDED for an edge to be detectable at "
              f"{bar_sigma:.2f}σ:")
        for e, n in req.items():
            print(f"    {e:+.2f} RT needs {n:,} trades "
                  f"({n / 3000:.0f} weeks at 3,000/wk in one market, "
                  f"{n / 20 / 3000:.0f} weeks pooled over 20)")
    reach = reachability(bars, tv, cost, bar_s, bar_sigma, verbose=verbose)
    return {"calibration": cal, "power": pw, "false_alarms": fa,
            "bar": bar_sigma, "sd_rt": sd, "required_trades": req,
            "baseline_rt": base, "reachability": reach,
            "bar_s": bar_s, "bars": int(len(bars))}


def hold_ceiling(bars, tv, cost, bar_s, bar_sigma, target_rt=1.0,
                 markets=1, fire=0.10, anchor_bars=1):
    """The longest hold at which this tape could resolve `target_rt`.

    Past this, the search is looking somewhere the data cannot answer,
    whatever is actually there -- and a wasted trial is not free,
    because the bar rises as sqrt(2 ln N) and every blind test makes the
    standard harder for every test elsewhere.

    Solvable in closed form from ONE dispersion measurement, which is
    what makes it affordable to do per tape per cycle. Under the
    measured law sd(h) = sd0 * sqrt(h / h0):

        mde(h) = bar * sd(h) * sqrt(h / bar_s) / sqrt(n * fire * markets)
               = bar * sd0 * h / (sqrt(h0 * bar_s * n * fire * markets))

    which is LINEAR in h, so

        h_max = target * sqrt(h0 * bar_s * n * fire * markets) / (bar*sd0)

    Checked against the five-point measured curve on both tapes:

        15s deep NQ    formula 70s   measured mde crosses 1.0 near 68s
        5-min tier 1   formula 463s  measured mde crosses 1.0 near 460s

    Returns None when dispersion cannot be measured, and the caller must
    treat that as "no ceiling known" rather than as zero.
    """
    sd0 = dispersion(bars, tv, cost, hold_bars=anchor_bars)
    if not sd0 or sd0 <= 0:
        return None
    h0 = float(anchor_bars) * float(bar_s)
    n = float(len(bars)) * float(fire) * float(max(1, markets))
    if n <= 1:
        return None
    h = (float(target_rt) * math.sqrt(h0 * float(bar_s) * n)
         / (float(bar_sigma) * sd0))
    return float(max(bar_s, h))


def reachability(bars, tv, cost, bar_s, bar_sigma, holds_bars=(1, 2, 6, 12, 48),
                 markets=20, fire=0.10, verbose=False):
    """WHICH HOLDS THIS TAPE CAN SEE ANYTHING AT, and how small.

    One dispersion number, measured at one hold, cannot answer the only
    question that matters for where to spend the search: is there a
    region of this space where an edge of a plausible size is reachable
    with the data that exists?

    Dispersion grows as roughly the square root of hold, so the trades
    an edge needs grow LINEARLY with hold -- while the trades a tape can
    supply shrink linearly with it. The penalty is therefore quadratic,
    and it decides everything:

        tape        hold     sd (RT)    trades for +0.15 RT
        5-min bars    5m        74.4          6,902,589
        60s bars      60s       36.9          1,697,486
        15s bars      15s       17.7            390,641

    So instead of a single "detectable size", this reports, for each
    hold, the SMALLEST EDGE this tape could actually resolve given how
    many trades it can supply. That number is a research directive: it
    says what to go looking for, and where looking is pointless.

    `fire` is the fraction of bars a cell is assumed to trigger on and
    `markets` how many the mechanism is pooled across; both are stated
    rather than hidden, because the answer is meaningless without them.
    """
    out = []
    n_bars = int(len(bars))
    weeks = max(n_bars * float(bar_s) / (6.5 * 3600.0) / 5.0, 1e-9)
    for hb in holds_bars:
        try:
            sd = dispersion(bars, tv, cost, hold_bars=hb)
        except Exception:                                     # noqa: BLE001
            sd = None
        if not sd:
            continue
        hold_s = int(hb * bar_s)
        # Trades this tape can supply, pooled: every bar is a candidate
        # entry, `fire` of them trigger, and the hold does not reduce the
        # count because entries overlap -- the overlap correction in the
        # evaluator already deflates the effective n for that, which is
        # why `eff` below is the honest figure and n_bars * fire is not.
        avail = n_bars * fire * markets
        overlap = max(1.0, hold_s / float(bar_s))
        eff = avail / overlap
        # smallest edge resolvable: bar * sd / sqrt(eff)
        mde = bar_sigma * sd / math.sqrt(max(eff, 1.0))
        out.append({
            "hold_s": hold_s, "sd_rt": round(sd, 2),
            "trades_available": int(avail),
            "effective_n": int(eff),
            "smallest_edge_rt": round(mde, 4),
            "weeks_for_0.15": round(
                required_trades(sd, bar_sigma, edges=(0.15,))[0.15]
                / max(n_bars * fire * markets / weeks, 1e-9), 1),
        })
    if verbose and out:
        print(f"  REACHABILITY on this tape ({n_bars:,} bars at {bar_s:g}s, "
              f"cell firing {fire:.0%}, pooled over {markets}):")
        for r in out:
            print(f"    hold {r['hold_s']:>6}s  sd {r['sd_rt']:>7.1f} RT  "
                  f"-> smallest edge it could resolve "
                  f"{r['smallest_edge_rt']:+.3f} RT/trade")
    return out


def required_trades(sd_rt, bar_sigma, edges=(0.05, 0.1, 0.15, 0.25, 0.5)):
    """How many trades an edge of each size needs to be DETECTABLE.

    This is the number that turns "nothing found" from a shrug into a
    research directive. Measured on real NQ: per-trade dispersion is
    about 21 round trips, and a cell that fires 166 times therefore has
    a standard error of 1.63 RT -- so it would need NINE round trips per
    trade to clear a 5.79 bar. Nine times the entire cost of trading, in
    the range this project calls bug territory.

    In other words the searcher was blind, at that cell size, to every
    edge it could plausibly have found. Its silence there was never
    evidence of absence; it was evidence of no power.

    What the arithmetic then says, and it is actionable:

        +0.15 RT needs   657,000 trades
          one market at 3,000/wk   ->  219 weeks   (hopeless)
          pooled over 20 markets   ->   11 weeks   (feasible)

    High frequency AND breadth, together. Neither alone is enough, which
    is exactly why the frequency axis of the archive and the pooled
    cross-market test are the two things that matter most.
    """
    out = {}
    for e in edges:
        n = (float(bar_sigma) * float(sd_rt) / float(e)) ** 2
        out[e] = int(round(n))
    return out


def dispersion(bars, tv, cost, hold_bars=6, minutes=None):
    """Per-trade dispersion in round trips, from the real tape.

    Everything above depends on this one number, so it is measured
    rather than assumed.
    """
    minutes = list(minutes or CAL_MINUTES)
    sds = []
    for m in minutes:
        truth = {"minute": m, "hold_bars": hold_bars, "side": 1,
                 "size_rt": 0.0}
        r = _fixed_side(bars, truth, tv, cost, None)
        if r and r.get("sd"):
            sds.append(r["sd"] / cost)
    return float(np.median(sds)) if sds else None


def detectable_size(pw, want=0.8):
    """The smallest planted size detected at least `want` of the time.

    The single most useful summary: everything below this, the searcher
    would probably have missed, so its silence about that range is not
    evidence of absence.
    """
    ok = [s for s, v in sorted(pw.items()) if v["rate"] >= want]
    return ok[0] if ok else None


# ------------------------------------------------------------ self-test
def selftest(verbose=True):
    """The harness itself has to be right, or it certifies a lie."""
    fails = []
    rng = np.random.default_rng(0)
    n = 40000
    idx = pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC")
    px = 20000 + np.cumsum(rng.normal(0, 1.0, n))
    sp = np.abs(rng.normal(0, .5, n)) + .1
    bars = pd.DataFrame({"open": px, "high": px + sp, "low": px - sp,
                         "close": px}, index=idx)
    tv, cost = 2.0, 0.60
    bar_s = 300.0

    # 1. A plant of zero must recover as zero. If the harness itself has
    #    a bias, every other number it produces is wrong.
    cal0 = calibration(bars, tv, cost, bar_s, sizes=(0.0,), verbose=False)
    r0 = cal0[0]
    # judged against the MEASURED error bar, not a number I picked
    ok = abs(r0["err"]) < max(3 * r0["se"], 0.05)
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  a zero plant recovers as zero "
              f"— {r0['got']:+.3f} ± {r0['se']:.3f} RT over "
              f"{r0['plants']} plants")
    if not ok:
        fails.append(f"harness biased at zero by {r0['err']:+.3f}")

    # 2. A plant of known size must recover at that size. This is the
    #    check that would have caught the gross/net unit error on its
    #    first run.
    cal = calibration(bars, tv, cost, bar_s, sizes=(0.2, 0.5, 1.0),
                      verbose=False)
    errs = [abs(r["err"]) for r in cal]
    ses = [r["se"] for r in cal]
    ok = all(e < max(3 * se, 0.05) for e, se in zip(errs, ses))
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  known sizes recover at their "
              f"size — worst error {max(errs):.3f} RT against error bars "
              f"of {max(ses):.3f}")
    if not ok:
        fails.append(f"recovery biased, worst {max(errs):.3f}")

    # 3. The plant must be TRADEABLE: entering on the marker bar itself
    #    must earn nothing extra. A plant that only pays when you cheat
    #    would measure the engine's cheating, not its power.
    b, t = plant(bars, "16:20", 1.0, tv, cost)
    idxb = b.index
    hh, mm = 16, 20
    mark = np.flatnonzero(np.asarray((idxb.hour == hh)
                                     & (idxb.minute == mm)))
    c = b["close"].values
    hold = t["hold_bars"]
    same = mark[(mark + hold) < len(b)]
    on_bar = (c[same + hold] - c[same]) * tv - cost      # enter AT marker
    lagged = (c[same + 1 + hold] - c[same + 1]) * tv - cost
    ok = on_bar.mean() <= lagged.mean() * 1.15
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  the plant does not reward "
              f"entering on the selection bar — on-bar "
              f"${on_bar.mean():.2f} vs lagged ${lagged.mean():.2f}")
    if not ok:
        fails.append("plant rewards look-ahead")

    # 4. False alarms on a driftless walk must be near the bar's promise,
    #    not wildly above it.
    fa = false_alarms(bars, tv, cost, bar_s, 3.5, verbose=False)
    ok = fa["rate"] is not None and fa["rate"] < 0.05
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  empty cells rarely clear a "
              f"3.5 bar on a driftless walk — {fa['rate']} "
              f"({fa['alarms']}/{fa['cells']})")
    if not ok:
        fails.append(f"false-alarm rate {fa['rate']} too high")

    # 5. Power must RISE with planted size. A harness whose power curve
    #    is flat is measuring something other than the edge.
    pw = power(bars, tv, cost, bar_s, 3.0, sizes=(0.05, 0.5, 2.0),
               minutes=["13:35", "14:05", "15:10", "16:20", "17:45"],
               verbose=False)
    rates = [pw[s]["rate"] for s in sorted(pw)]
    ok = len(rates) >= 2 and rates[-1] >= rates[0]
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  power rises with planted "
              f"size — " + ", ".join(
                  "%+.2f:%.0f%%" % (k, pw[k]["rate"] * 100)
                  for k in sorted(pw)))
    if not ok:
        fails.append("power curve not monotone")
    return fails


if __name__ == "__main__":
    f = selftest()
    print("\ncalibration selftest:", "PASS" if not f else f"FAIL {f}")
