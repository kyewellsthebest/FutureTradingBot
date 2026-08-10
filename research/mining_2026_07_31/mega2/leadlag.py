"""How fast does cross-market information die? The latency price list.

The ablation next door asks whether ES / YM / RTY carry information about NQ.
It samples them on a 2.7-minute bar clock, and that clock cannot see the effect
this file is about: the index complex leads NQ on a scale of MILLISECONDS, not
minutes. By the time a 2.7-minute bar closes, whatever ES knew has been in NQ's
price for a hundred bars' worth of microstructure.

So this measures the decay curve directly, with no model in the way. For a
total latency budget L -- everything between the foreign print existing and our
order resting in the book -- how much does the foreign move over the preceding
window predict NQ's NEXT move?

WHY THIS IS THE MOST ACTIONABLE NUMBER IN THE REPO. The bot's own diagnostic
bundle measured ~2 SECOND entry latency. If the curve is worth real money at
50 ms and nothing at 2 s, then "fix the bot's latency" stops being a chore on a
list and becomes a priced decision: this much edge, for that much engineering.
And if the curve is already flat at 1 ms, cross-market speed is not the answer
and no amount of colocation would help, which is worth knowing before anybody
pays for it.

L IS TOTAL LATENCY, NOT A DATA DELAY. The foreign window ENDS at t - L and the
NQ outcome STARTS at t. Nothing in the predictor is contemporaneous with, let
alone later than, the thing being predicted. L = 0 is the physically impossible
best case and is included only as the ceiling of the curve.

THE CONTROL is the same one the ablation uses: slide the foreign tape days
along the calendar and re-measure. Correlation between two index futures is so
strong that almost any bug produces a number; only the shift separates "ES
leads NQ" from "ES and NQ are the same asset".
"""
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402

OUT = os.environ.get("OUT_MD", os.path.join(fuse.ROOT, "research", "LEADLAG.md"))
MS = 1_000_000
LAGS = [0, 1, 5, 10, 25, 50, 100, 250, 500, 1000, 2000, 5000]   # ms
FWD = [100, 1000, 5000, 30000]                                   # ms
LOOK = 1000                                                      # ms of window
STEP = int(os.environ.get("STEP", "40"))     # sample every Nth NQ print
CONTRACTS = os.environ.get("CONTRACTS", "NQZ4,NQU5,NQZ5,NQM6").split(",")
SYMS = os.environ.get("SYMS", "ES,YM,RTY,CL").split(",")
USD_PT = 2.00
COST_RT = 1.99
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def px_at(ts, px, T):
    """Price of the last print at or before each query time."""
    j = np.searchsorted(ts, T, side="right") - 1
    out = px[np.maximum(j, 0)].astype(np.float64)
    out[j < 0] = np.nan
    return out


def run(t, fwd, fts, fpx, sym, shift):
    """One (foreign stream, control) sweep. The NQ side is passed in already
    computed -- reloading a 24-million-print tape once per symbol per control
    is 32 loads for what is genuinely 4."""
    off = int(fuse.SHIFT_DAYS * fuse.DAY_NS) if shift else 0
    out = {}
    for lg in LAGS:
        a = t - lg * MS
        b = a - LOOK * MS
        if shift:
            a = fuse.shift_query(dict(ts=fts), a, off)
            b = a - LOOK * MS
        fr = (px_at(fts, fpx, a) - px_at(fts, fpx, b)) / fuse.TICKSZ[sym]
        for f in FWD:
            y = fwd[f]
            m = np.isfinite(fr) & np.isfinite(y) & (fr != 0)
            if m.sum() < 5000:
                continue
            x = fr[m]
            yy = y[m]
            ic = float(np.corrcoef(x, yy)[0, 1])
            # take a full position in the direction the foreign tape moved
            g = float(np.mean(np.sign(x) * yy)) * USD_PT
            out[(lg, f)] = (ic, g, int(m.sum()))
    return out


def main():
    t0 = time.time()
    meta = fuse.tape_meta()
    acc = {"real": {}, "shift": {}}
    for c in CONTRACTS:
        nts, npx, _ = fuse.load_tape(meta[c]["path"])
        e = np.arange(0, len(nts), STEP)
        t = nts[e]
        p0 = npx[e].astype(np.float64)
        # NQ's forward moves do not depend on the lag, so the whole sweep
        # reuses them.
        fwd = {f: (px_at(nts, npx, t + f * MS) - p0) / fuse.PT for f in FWD}
        del nts, npx, p0
        for sym in SYMS:
            fc = fuse.pick_contract(meta, sym, int(t[0]), int(t[-1]))
            if fc is None:
                print(f"  {c} {sym}: no dense contract", flush=True)
                continue
            fts, fpx, _ = fuse.load_tape(meta[fc]["path"])
            for kind in ("real", "shift"):
                o = run(t, fwd, fts, fpx, sym, kind == "shift")
                for k, v in o.items():
                    a = acc[kind].setdefault((sym,) + k, [0.0, 0.0, 0])
                    a[0] += v[0] * v[2]
                    a[1] += v[1] * v[2]
                    a[2] += v[2]
                print(f"  {c} {sym} {kind} ({time.time()-t0:.0f}s)", flush=True)
            del fts, fpx
        del t, fwd

    log("# How fast does cross-market information die?")
    log()
    log("The index complex leads NQ on a scale of **milliseconds**. A "
        "2.7-minute bar cannot see that, so this measures the decay curve "
        "directly with no model in the way.")
    log()
    log("`L` is **total latency** — everything between a foreign print "
        "existing and our order resting in the book. The foreign window ends "
        f"at `t − L`; the NQ outcome starts at `t`. Nothing in the predictor "
        f"is contemporaneous with what it predicts. `L = 0` is physically "
        f"impossible and is here only as the ceiling of the curve.")
    log()
    log(f"NQ prints sampled every {STEP}, {len(CONTRACTS)} quarters, "
        f"a {LOOK} ms foreign look-back window. `$/trade` takes a full MNQ "
        f"position in the direction the foreign tape just moved; a round turn "
        f"costs **${COST_RT:.2f}**.")
    log()
    log("**One caveat on the sample.** Consecutive samples overlap — at a 30 s "
        "outcome window, thousands of them share the same stretch of tape. "
        "That leaves the point estimates unbiased but makes their standard "
        "errors far smaller than they look, so do not read a small number as "
        "significant just because it sits on millions of rows. The shifted "
        "control, not the row count, is what makes a number here trustworthy.")
    log()
    for sym in SYMS:
        rows = [(lg, f) for (s, lg, f) in acc["real"] if s == sym]
        if not rows:
            continue
        log(f"## {sym} → NQ")
        log()
        log("| total latency | " + " | ".join(
            f"IC @ {f}ms" for f in FWD) + " | " + " | ".join(
            f"$/trade @ {f}ms" for f in FWD) + " |")
        log("|---" * (1 + 2 * len(FWD)) + "|")
        for lg in LAGS:
            ics, dol = [], []
            for f in FWD:
                k = (sym, lg, f)
                if k not in acc["real"]:
                    ics.append("—")
                    dol.append("—")
                    continue
                a = acc["real"][k]
                ics.append(f"{a[0]/a[2]:+.4f}")
                dol.append(f"${a[1]/a[2]:+.3f}")
            mark = "**" if lg >= 2000 else ""
            lab = f"{lg} ms" if lg < 1000 else f"{lg/1000:g} s"
            if lg == 2000:
                lab += " ← this bot today"
            log(f"| {mark}{lab}{mark} | " + " | ".join(ics) + " | " +
                " | ".join(dol) + " |")
        log()
        # the control
        log("| shifted control | " + " | ".join(
            (f"{acc['shift'][(sym, 0, f)][0]/acc['shift'][(sym, 0, f)][2]:+.4f}"
             if (sym, 0, f) in acc["shift"] else "—") for f in FWD) +
            " | " + " | ".join(
            (f"${acc['shift'][(sym, 0, f)][1]/acc['shift'][(sym, 0, f)][2]:+.3f}"
             if (sym, 0, f) in acc["shift"] else "—") for f in FWD) + " |")
        log()
        log(f"The control slides the {sym} tape {fuse.SHIFT_DAYS:g} days along "
            f"the calendar and repeats the L=0 row. {sym} and NQ are close to "
            f"the same asset, so almost any bug produces a number here; only "
            f"the shifted row separates *{sym} leads NQ* from *{sym} is NQ*.")
        log()
    log("## What the curve decides")
    log()
    log(f"This bot's measured entry latency is about **2 seconds**. Read the "
        f"2 s row, not the 0 ms row. The gap between them is exactly what "
        f"execution engineering is worth — if the 0 ms row clears ${COST_RT:.2f} "
        f"and the 2 s row does not, the edge is real and unreachable at "
        f"current speed, and the fix is the bot rather than the search. If "
        f"both rows sit at zero, cross-market speed is not the answer and no "
        f"colocation would change that.")
    log()
    log(f"_Ran in {(time.time()-t0)/60:.0f} min._")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write("\n".join(L) + "\n")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
