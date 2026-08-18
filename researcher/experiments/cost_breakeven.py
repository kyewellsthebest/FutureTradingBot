"""At what all-in round turn does the best thing found stop paying?

THE QUESTION BEHIND IT. Every net figure in this project is quoted in
round trips: `cu = net / cost`, where `cost` is what the searcher
believes a round turn costs. For MNQ that is one tick of spread plus
commission -- 0.25 x $2.00 + $0.10 = $0.60. Another document in this
repo assumes $1.24 commission alone, so $1.74 all in. Nobody has
measured which is right, and the gap between them is the difference
between the best row in 359,000 trials making money and losing a
fortune. The search cannot resolve it: what a round turn costs is a
fact about a brokerage account, not about the tape.

WHAT THIS DOES INSTEAD OF WAITING. It inverts the question. Rather than
asking "is the edge bigger than the cost", it asks "how big would the
cost have to be to eat the edge" -- which needs no outside input at all,
and turns a blocking unknown into a threshold anybody can check against
their own statement in ten seconds.

THE ARITHMETIC, and it is exact under the searcher's own accounting:

    cu    = net / cost                      (definition)
    net   = gross - cost                    (definition)
    =>  gross = cost x (1 + cu)
    =>  break-even cost = gross = cost x (1 + cu)

So the break-even is a MULTIPLIER on whatever the searcher charged, and
the multiplier is `1 + cu`. It does not depend on the market, which
matters here because the best cells are pooled across fourteen of them
with ticks that differ by a factor of sixty. A cell at cu = 0.162 pays
until costs are 1.162x what was modelled, and not a cent past it.

THE CONTROL, and it is the important part. `1 + cu` is a monotone
transform of cu, so the highest break-even in the ledger is the highest
cu in the ledger -- a MAXIMUM OVER TRIALS, which is large even when
nothing is there. The control is therefore the same statistic computed
over the whole population: if the winner's break-even is not clearly
past the p99 of every cell's break-even, the winner is the top of a
pile of noise wearing a dollar sign. This is the empirical null in the
units of somebody's brokerage statement, and it is reported next to the
headline rather than underneath it.

Shrinkage is reported too. The archive already deflates cu by its own
standard error (`shrunk = cu / (1 + (se/tau)^2)`), and the honest
break-even uses the shrunk figure, because the raw one is the winner's
curse quoted to the penny.

WHY THIS COSTS NO TRIALS, stated openly because rule 3 says looking at
the data costs. This looks at no data. It reads results the ledger has
ALREADY charged -- each of those cells paid its trial when it was
recorded -- and re-expresses them. Charging again would double-count
the same looks and raise the bar for work nobody did.
"""
from __future__ import annotations

import numpy as np

QUESTION = ("How high can the all-in round turn go before the best "
            "thing the search has found stops paying?")
WHY = ("Every net number here is quoted per round trip against a cost "
       "the search assumed. Two documents in this repo disagree about "
       "that cost by 2.9x, which flips the best result from profit to "
       "ruin. This answers it without needing the true number.")
CONTROL = ("the same break-even computed across the WHOLE population "
           "of cells -- the top one is a maximum over trials and is "
           "large even when nothing is there, so it has to clear the "
           "p99 of everything else to mean anything")

# The ladder a person can actually check themselves against. Retail
# all-in round turns for one micro run from about 20c on a cheap
# clearing arrangement to about $2.50 through a full-service broker.
LADDER = [0.20, 0.40, 0.60, 0.85, 1.00, 1.24, 1.50, 1.74, 2.00, 2.50]

MNQ_MODELLED = 0.60      # 0.25 tick x $2.00/pt + $0.10 commission
MIN_TRADES = 500         # below this the cell is not a strategy
STABLE_RUNS = 3          # runs agreeing before the question is settled


def _num(v, d=0.0):
    try:
        f = float(v)
        return f if np.isfinite(f) else d
    except (TypeError, ValueError):
        return d


def _cells(led):
    """Every clean, measured cell, as (cu, trades, eff_n, mde, per_week).

    Killed cells are excluded because they failed a control -- their cu
    is not an estimate of anything. Stale cells are excluded because
    they were measured by an engine that has since been corrected.
    """
    out = []
    for rec in (led.get("tested") or {}).values():
        if not isinstance(rec, dict) or rec.get("stub") or rec.get("killed"):
            continue
        r = rec.get("result") or {}
        if not r:
            continue
        n = _num(r.get("n"))
        if n < MIN_TRADES:
            continue
        # A cu that is missing, nan or inf is a BROKEN measurement, not
        # a cell that broke even. Coercing it to 0.0 would pile fake
        # mass at exactly break-even, which drags the population's p99
        # down and makes the winner look further clear of the pile than
        # it is -- the control failing in the flattering direction.
        cu = _num(r.get("cu"), None) if r.get("cu") is not None else None
        if cu is None:
            continue
        out.append({
            "cu": cu, "n": int(n),
            "eff_n": _num(r.get("eff_n"), n),
            "mde": _num(r.get("mde")),
            "per_week": _num(r.get("per_week")),
            "markets": len(r.get("by") or {}) or _num(r.get("markets"), 1),
            "family": rec.get("family"),
            "hyp": rec.get("hyp") or {},
        })
    return out


def _shrunk(cu, mde):
    """The archive's own deflation, restated here so this file stands
    alone if the archive is empty. se is inferred from the minimum
    detectable effect the same way archive.py infers it."""
    if not mde:
        return None
    se = mde / 3.5
    tau = 0.20
    return cu / (1.0 + (se / tau) ** 2)


def run(state, slot, budget_s=None):
    led = (state or {}).get("ledger") or {}
    cells = _cells(led)
    if len(cells) < 50:
        return None

    cus = np.array([c["cu"] for c in cells], dtype=float)
    best = max(cells, key=lambda c: c["cu"])

    # THE CONTROL: what the best-looking cell looks like when the
    # population is the reference, not the leaderboard.
    p99 = float(np.percentile(cus, 99))
    p50 = float(np.percentile(cus, 50))

    sh = _shrunk(best["cu"], best["mde"])
    rows = []
    for c in LADDER:
        # net per trade at an all-in round turn of c, for a cell the
        # searcher priced at MNQ_MODELLED.
        gross = MNQ_MODELLED * (1.0 + best["cu"])
        per_trade = gross - c
        row = {"round_turn": c, "net_per_trade": round(per_trade, 4)}
        if best["per_week"]:
            row["per_week"] = round(per_trade * best["per_week"], 2)
        if sh is not None:
            g2 = MNQ_MODELLED * (1.0 + sh)
            row["net_per_trade_shrunk"] = round(g2 - c, 4)
            if best["per_week"]:
                row["per_week_shrunk"] = round((g2 - c) * best["per_week"], 2)
        rows.append(row)

    return {
        "measurements": 0,        # see the module docstring: no new looks
        "cells_considered": len(cells),
        "best": {
            "cu": round(best["cu"], 4),
            "cu_shrunk": (round(sh, 4) if sh is not None else None),
            "trades": best["n"],
            "eff_n": round(best["eff_n"], 1),
            "markets": int(best["markets"] or 1),
            "per_week": round(best["per_week"], 1) or None,
            "family": best["family"],
        },
        "breakeven_multiplier": round(1.0 + best["cu"], 4),
        "breakeven_mnq_dollars": round(MNQ_MODELLED * (1.0 + best["cu"]), 4),
        "breakeven_mnq_dollars_shrunk": (
            round(MNQ_MODELLED * (1.0 + sh), 4) if sh is not None else None),
        # the population, i.e. what "best of N nothing" looks like here
        "control_p99_breakeven_mnq": round(MNQ_MODELLED * (1.0 + p99), 4),
        "control_p50_breakeven_mnq": round(MNQ_MODELLED * (1.0 + p50), 4),
        "modelled_cost_mnq": MNQ_MODELLED,
        "ladder": rows,
    }


def done(slot):
    """Settled when the answer has stopped moving.

    A cost curve over a leaderboard that never changes is a report, not
    a question, and rule 4 says a question has to end. But the
    leaderboard CAN change, so "done" means the break-even has been the
    same for STABLE_RUNS runs -- and a genuinely better cell moves it
    and reopens the question by itself.
    """
    h = [x.get("breakeven_multiplier") for x in (slot.get("history") or [])]
    h = [x for x in h if x is not None][-STABLE_RUNS:]
    return len(h) >= STABLE_RUNS and (max(h) - min(h)) < 0.005


def verdict(slot):
    r = slot.get("latest") or {}
    if not r:
        return "not enough data yet"
    b, be = r["best"], r["breakeven_mnq_dollars"]
    ctrl = r["control_p99_breakeven_mnq"]
    parts = [
        f"the best cell of {r['cells_considered']:,} pays {b['cu']:+.3f} "
        f"round trips over {b['trades']:,} trades, which breaks even at "
        f"an all-in round turn of ${be:.2f} on MNQ (the search charged "
        f"${r['modelled_cost_mnq']:.2f})"]
    shd = r.get("breakeven_mnq_dollars_shrunk")
    if shd is not None:
        parts.append(f"after shrinking for the winner's curse it breaks "
                     f"even at ${shd:.2f}")
    # THE CONTROL, said in the same breath as the headline and QUOTED
    # AS A RATIO rather than as a verdict word. A threshold here would
    # turn a continuous quantity into a yes/no at some line I picked,
    # and the interesting cases land within a few cents of any line.
    margin = be - r["modelled_cost_mnq"]
    ctrl_margin = ctrl - r["modelled_cost_mnq"]
    lift = margin / ctrl_margin if ctrl_margin > 1e-9 else float("inf")
    parts.append(
        f"the 99th percentile of ALL {r['cells_considered']:,} cells "
        f"breaks even at ${ctrl:.2f} and the median at "
        f"${r['control_p50_breakeven_mnq']:.2f}, so the winner's headroom "
        f"over the modelled cost is {lift:.2f}x what the 99th percentile "
        f"of the pile gets for free"
        + (" -- that is selection, not an edge" if lift < 1.5 else ""))
    if b.get("per_week"):
        parts.append(f"at {b['per_week']:,.0f} trades a week it is worth "
                     f"the ladder in the report; the practical reading is "
                     f"that anything above ${be:.2f} a round turn makes "
                     f"this a losing system no matter how it is executed")
    return ". ".join(parts)
