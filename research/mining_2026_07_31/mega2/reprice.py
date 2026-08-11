"""Re-price the search's passive rows against the measured queue curve.

THE COLLISION. mega.py credits a resting entry a flat two ticks -- $1.00 a
trade on MNQ -- and every one of its best results is a passive row. maker.py
then measured what resting is actually worth against crossing, over 33,464
trades, and got a curve rather than a constant:

    contracts ahead of you      vs crossing
              0                   +$0.355
              2                   +$0.064
              5                   -$0.019
             25                   -$0.097
             50+                  -$0.102

So the search's headline numbers are inflated by somewhere between $0.65 and
$1.10 a trade, depending on a queue depth nobody has measured yet.

WHY THIS IS ARITHMETIC AND NOT ANOTHER SEARCH. The credit mega.py applied is a
CONSTANT added to every passive trade. Removing it and substituting a
different constant is exact -- no re-scan, no re-fit, no fresh multiple
testing. The win rates, trade counts, brackets and random-entry baselines are
all untouched; only the per-trade credit changes. That makes this a repricing
of results already in hand rather than a new set of draws against the ceiling.

WHAT IT ANSWERS. Not "does this strategy work" but "how deep can the queue be
before it stops working" -- the break-even queue depth for every candidate.
When the DOM recorder finally reports a median top-of-book depth, that number
is a lookup against this table, and the surviving rows are known immediately.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402

STATE = os.path.join(fuse.ROOT, "data", "mega_state.json")
OUT = os.environ.get("OUT_MD", os.path.join(fuse.ROOT, "research",
                                            "REPRICED.md"))
TICKVAL = 0.50
ASSUMED = 2.0 * TICKVAL          # what mega.py credited: a flat two ticks
# measured in maker.py: advantage of resting over crossing, per trade
CURVE = {0: 0.355, 2: 0.064, 5: -0.019, 10: -0.075, 25: -0.097, 50: -0.102,
         100: -0.101, 200: -0.101}
MIN_TPW = float(os.environ.get("MIN_TPW", "500"))
MIN_DOL = float(os.environ.get("MIN_DOL", "2.00"))
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def main():
    d = pd.DataFrame(json.load(open(STATE))["rows"])
    if not len(d):
        print("no rows")
        return
    npass = int(d.passive.sum())

    log("# The search's best results, re-priced against the measured queue")
    log()
    log(f"`mega.py` credits a resting entry a flat **two ticks — $1.00 a "
        f"trade** — and **{npass:,} of {len(d):,}** scored rows are passive, "
        f"including every one of the leaders. `maker.py` then measured what "
        f"resting is actually worth against crossing over 33,464 trades, and "
        f"it is not a constant:")
    log()
    log("| contracts ahead of you | worth vs crossing |")
    log("|---|---|")
    for q, v in CURVE.items():
        log(f"| {q} | **${v:+.3f}** |")
    log()
    log(f"So the headline numbers are overstated by between **$0.65 and "
        f"$1.10 a trade**. Correcting that is arithmetic, not another search: "
        f"the credit is a constant added to every passive trade, so swapping "
        f"it leaves win rates, trade counts, brackets and random-entry "
        f"baselines untouched. These are the same results, priced honestly — "
        f"not a fresh set of draws against the selection ceiling.")
    log()

    # ---- how the population moves as the queue deepens ----
    log("## What survives, as the queue gets longer")
    log()
    log(f"Gates unchanged: **≥{MIN_TPW:.0f} trades/week and ≥${MIN_DOL:.2f} a "
        f"trade**, net, beating random entry.")
    log()
    log("| contracts ahead | rows clearing both gates | best $/trade | "
        "best $/week | best $/week at 500+ trades |")
    log("|---|---|---|---|---|")
    for q, adv in CURVE.items():
        x = d.copy()
        adj = np.where(x.passive, adv - ASSUMED, 0.0)
        x["dol2"] = x.dol + adj
        x["wk2"] = x.dol2 * x.tpw
        hit = x[(x.tpw >= MIN_TPW) & (x.dol2 >= MIN_DOL)]
        fast = x[x.tpw >= MIN_TPW]
        log(f"| {q} | {len(hit):,} | ${x.dol2.max():+.2f} | "
            f"${x.wk2.max():+,.0f} | "
            f"${fast.wk2.max():+,.0f} |" if len(fast) else
            f"| {q} | {len(hit):,} | ${x.dol2.max():+.2f} | "
            f"${x.wk2.max():+,.0f} | — |")
    log()

    # ---- per-candidate break-even queue depth ----
    log("## Break-even queue depth, per candidate")
    log()
    log("For each of the strongest rows: how many contracts can sit ahead of "
        "you before it stops paying $2.00 a trade. **This is the number the "
        "DOM recorder settles.** A candidate whose break-even is 0 needs the "
        "front of the queue on every order, which is not reachable at 72 ms.")
    log()
    qs = sorted(CURVE)
    best = d[d.tpw >= MIN_TPW].nlargest(10, "wk")
    if not len(best):
        best = d.nlargest(10, "wk")
    log("| trigger | tr/wk | $/trade **as credited** | **re-priced @0** | "
        "**@5** | **@50** | break-even queue |")
    log("|---|---|---|---|---|---|---|")
    for _, r in best.iterrows():
        row = []
        for q in qs:
            adv = CURVE[q]
            row.append(r.dol + (adv - ASSUMED if r.passive else 0.0))
        be = "—"
        for q, v in zip(qs, row):
            if v >= MIN_DOL:
                be = str(q)
        if row[0] < MIN_DOL:
            be = "never"
        log(f"| {str(r.feat)[:44]} | {r.tpw:.0f} | ${r.dol:+.2f} | "
            f"${row[0]:+.2f} | ${row[2]:+.2f} | ${row[5]:+.2f} | **{be}** |")
    log()
    q0 = d.copy()
    q0["dol0"] = q0.dol + np.where(q0.passive, CURVE[0] - ASSUMED, 0.0)
    nhit0 = int(((q0.tpw >= MIN_TPW) & (q0.dol0 >= MIN_DOL)).sum())
    log(f"At the **front of the queue** — the best case physics allows, and "
        f"one we cannot actually reach — **{nhit0:,}** rows clear both gates. "
        f"Every row that needs a break-even of 0 is asking for a queue "
        f"position that costs a rack in Aurora, Illinois to obtain.")
    log()
    log("The honest reading: these are not results waiting on more searching. "
        "They are results waiting on **one measurement** — the median depth "
        "at top of book — and that measurement decides all of them at once.")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write("\n".join(L) + "\n")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
