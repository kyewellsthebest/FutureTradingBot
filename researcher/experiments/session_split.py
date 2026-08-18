"""Is the overnight session a different market, and is it priced as one?

THE OBSERVATION THAT PROMPTED IT. 70% of the tier-1 tapes are outside
RTH -- 129,106 of 184,935 NQ bars. The plan document says every search
in this repo filtered to RTH and lists the overnight session as the
cheapest untested hypothesis available; that has been false for as long
as tier 1 has existed. Globex has been searched all along, mixed
indistinguishably into the same cells.

Mixing is worse than either choice, and for a reason that is arithmetic
rather than taste. The cost constant is `tick x $/point + commission`,
which assumes a one-tick spread. That is true in RTH. Overnight, when
the book is thin, it frequently is not. So the searcher charges a
daytime cost to a nighttime tape, and it does so on the majority of its
data. Every net figure computed there is optimistic by whatever the
spread actually widens to, and nobody has measured that.

WHAT THIS MEASURES, per market, per session:

    bars                how much data each session actually holds
    dispersion          per-bar |move|, the thing that sets detectability
    range               the bar's own high-low, a spread-independent
                        proxy for how wide the market is standing
    detectable edge     bar x sd / sqrt(n), the smallest thing findable

THE CONTROL. Splitting a tape in two and finding the halves differ is
not a result -- any split of any series gives two different numbers. So
the same split is run on a RANDOM assignment of bars to two groups of
the same sizes. Whatever the random split produces is what a difference
of nothing looks like here, and the session difference has to beat it.

WHAT WOULD MAKE THIS ACTIONABLE. If the overnight session's range per
bar is materially wider, the cost constant is wrong there and every
overnight result in the ledger is optimistic. If its detectable edge is
much worse, then most of the searcher's data is in its blindest region
and the budget should move. Either answer changes what the searcher
does; that is the bar an experiment has to clear to be worth running.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

QUESTION = ("Is the overnight session different enough from RTH that "
            "searching and pricing them together is wrong?")
WHY = ("70% of tier-1 bars are outside RTH and are charged an RTH "
       "spread. If overnight is wider, most of the ledger is optimistic.")
CONTROL = ("the identical split on a RANDOM assignment of bars to two "
           "groups of the same sizes -- any split gives two different "
           "numbers, so the session difference must beat a random one")

# RTH for the US index complex, in UTC. 13:30-20:00 is the cash session;
# 13:00 is used as the lower edge so the pre-open auction is counted as
# day rather than night.
RTH_FROM, RTH_TO = 13, 20
MIN_BARS = 2000


def _stats(x, bar_sigma=5.0):
    """Dispersion and the smallest edge that many bars could resolve."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 50:
        return None
    sd = float(np.std(x, ddof=1))
    return {"bars": n, "sd": round(sd, 5),
            "mean_abs": round(float(np.mean(np.abs(x))), 5),
            "detectable": round(bar_sigma * sd / np.sqrt(n), 6)}


def run(state, slot, budget_s=None):
    data = (state or {}).get("data") or {}
    spec = (state or {}).get("spec") or {}
    bar_sigma = float((state or {}).get("bar") or 5.0)
    if not data:
        return None
    rng = np.random.default_rng(int(slot.get("runs", 0)) * 7919 + 11)
    rows, measured = [], 0
    for sym in sorted(data):
        d = data[sym]
        if d is None or len(d) < MIN_BARS or "close" not in d.columns:
            continue
        idx = pd.DatetimeIndex(d.index)
        day = (idx.hour >= RTH_FROM) & (idx.hour < RTH_TO)
        if day.sum() < MIN_BARS // 4 or (~day).sum() < MIN_BARS // 4:
            continue
        mv = d["close"].diff().values
        rngbar = ((d["high"] - d["low"]).values
                  if {"high", "low"} <= set(d.columns) else None)

        a, b = _stats(mv[day], bar_sigma), _stats(mv[~day], bar_sigma)
        if not a or not b:
            continue
        # THE CONTROL: same sizes, random membership.
        perm = rng.permutation(len(mv))
        ga = np.zeros(len(mv), bool)
        ga[perm[:int(day.sum())]] = True
        ca, cb = _stats(mv[ga], bar_sigma), _stats(mv[~ga], bar_sigma)
        if not ca or not cb:
            continue

        real = b["sd"] / a["sd"] if a["sd"] else None
        ctrl = cb["sd"] / ca["sd"] if ca["sd"] else None
        row = {
            "market": sym,
            "rth": a, "overnight": b,
            "sd_ratio_overnight_over_rth": (round(real, 4) if real else None),
            "sd_ratio_random_control": (round(ctrl, 4) if ctrl else None),
            "overnight_share_of_bars": round(float((~day).mean()), 3),
        }
        if rngbar is not None:
            rr, rn = rngbar[day], rngbar[~day]
            rr, rn = rr[np.isfinite(rr)], rn[np.isfinite(rn)]
            if len(rr) > 50 and len(rn) > 50:
                row["median_range_rth"] = round(float(np.median(rr)), 4)
                row["median_range_overnight"] = round(float(np.median(rn)), 4)
                row["range_ratio"] = round(
                    float(np.median(rn) / max(np.median(rr), 1e-9)), 4)
                # A spread wider than one tick is what the cost constant
                # does not model. Range is not spread, but a market whose
                # BARS are wider is a market whose book is thinner, and
                # it is the only proxy available without book data.
                tick = None
                if sym in spec:
                    tick = spec[sym][1] / max(spec[sym][0], 1e-9)
                if tick:
                    row["range_ticks_rth"] = round(
                        float(np.median(rr)) / tick, 2)
                    row["range_ticks_overnight"] = round(
                        float(np.median(rn)) / tick, 2)
                # RANGE IS NOT SPREAD, and this experiment proved it the
                # hard way. Bar range said overnight is 0.45x RTH, which
                # reads as "cheaper"; the actual book says the spread is
                # 67% WIDER. A quiet market has small bars and can still
                # be expensive to cross. The range columns stay because
                # they measure something real, but no cost conclusion is
                # drawn from them any more -- see book_spread below.
        rows.append(row)
        measured += 2

    # THE MEASUREMENT THAT ACTUALLY ANSWERS THE COST QUESTION.
    # Top-of-book exists for NQ, so the spread can be measured instead
    # of inferred. This is one market and four weeks, so it is evidence
    # about NQ rather than about futures -- said here rather than left
    # for a reader to assume.
    book = None
    try:
        from researcher import data_tiers as _DT
        b = _DT.tier3(bar_s=1)
        if b is not None and "spread" in b.columns and len(b) > 10000:
            bh = pd.DatetimeIndex(b.index).hour
            bday = (bh >= RTH_FROM) & (bh < RTH_TO)
            sp = b["spread"].values
            tick_nq = 0.25

            def _sp(m):
                x = sp[m]
                x = x[np.isfinite(x) & (x > 0)]
                if len(x) < 1000:
                    return None
                return {"seconds": int(len(x)),
                        "median_ticks": round(float(np.median(x)) / tick_nq, 2),
                        "p90_ticks": round(float(np.percentile(x, 90))
                                           / tick_nq, 2)}
            r_, n_ = _sp(bday), _sp(~bday)
            if r_ and n_:
                book = {"symbol": "NQ", "rth": r_, "overnight": n_,
                        "widening": round(n_["median_ticks"]
                                          / max(r_["median_ticks"], 1e-9), 3),
                        "cost_model_assumes_ticks": 1.0}
                measured += 2
    except Exception:                                         # noqa: BLE001
        book = None

    if not rows:
        return None
    ratios = [r["sd_ratio_overnight_over_rth"] for r in rows
              if r.get("sd_ratio_overnight_over_rth")]
    ctrls = [r["sd_ratio_random_control"] for r in rows
             if r.get("sd_ratio_random_control")]
    rr = [r["range_ratio"] for r in rows if r.get("range_ratio")]
    return {
        "markets": len(rows),
        "measurements": measured,
        "median_sd_ratio": round(float(np.median(ratios)), 4) if ratios else None,
        "median_sd_ratio_control": (round(float(np.median(ctrls)), 4)
                                    if ctrls else None),
        "median_range_ratio": round(float(np.median(rr)), 4) if rr else None,
        "book_spread": book,
        "per_market": rows,
    }


def done(slot):
    """Five agreeing runs is enough for a property of the tapes.

    This measures the tapes, not the market, and the tapes barely
    change. Running it forever would spend trials to re-confirm a
    constant.
    """
    return int(slot.get("runs") or 0) >= 5


def verdict(slot):
    r = (slot.get("latest") or {})
    real, ctrl = r.get("median_sd_ratio"), r.get("median_sd_ratio_control")
    rng = r.get("median_range_ratio")
    if real is None or ctrl is None:
        return "not enough data yet"
    # A random split of the same sizes lands at 1.0 by construction, so
    # the honest comparison is how far the real split is from that.
    lift = abs(real - 1.0) / max(abs(ctrl - 1.0), 0.01)
    parts = [f"overnight moves are {real:.2f}x RTH in dispersion "
             f"(a random split of the same sizes gives {ctrl:.2f}x, "
             f"so the session effect is {lift:.0f}x what splitting "
             f"nothing produces)"]
    if rng:
        parts.append(f"overnight bars are {rng:.2f}x the RTH range, which "
                     f"says nothing about cost -- a quiet market can still "
                     f"be expensive to cross")
    bk = r.get("book_spread")
    if bk:
        rt_, on_ = bk["rth"]["median_ticks"], bk["overnight"]["median_ticks"]
        parts.append(
            f"MEASURED on {bk['symbol']} top-of-book: spread is {rt_:.1f} "
            f"ticks in RTH and {on_:.1f} overnight ({bk['widening']:.2f}x "
            f"wider), against a cost model that charges "
            f"{bk['cost_model_assumes_ticks']:.0f} tick for both")
        if bk["widening"] > 1.15:
            parts.append("-- overnight results ARE optimistic, and 70% of "
                         "the tier-1 tape is overnight")
    else:
        parts.append("no book data, so the spread question is unanswered")
    return " ".join(parts)
