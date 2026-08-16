"""The last idea standing: is the fade's edge CONCENTRATED somewhere?

The fade is worth about +0.3 percentage points of target-first against
entering at a random minute (ACCURACY_CURVE.md). It needs +3.5 to +4.9
to pay. Spread evenly across all signals that is hopeless, so the only
surviving story is that it is NOT spread evenly -- that it lives at full
strength inside some subset and is absent from the rest.

That requires roughly a 10x concentration. Strong, but regime effects
genuinely can be that stark, and none of these has ever been conditioned
on for this family:

  IMPULSE SIZE     a 2-point move is noise; a 25-point move in three
                   minutes is a liquidity event, and fading exhaustion
                   is a documented effect. Lumping them together may be
                   averaging two different phenomena.
  TIME OF DAY      the 13:30 open and the 20:00 close have different
                   participants from midday.
  VOLATILITY       mean reversion being regime-dependent is one of the
                   better-established facts in the literature.
  RANGE POSITION   fading an extension at the day's high is a different
                   trade from fading one in the middle.

THE BAR, fixed before running:

  1. a cell must be positive NET of the $1.33 real cost
  2. it must beat the RANDOM-direction control measured in the SAME
     cell -- not the global control, because every one of these splits
     selects a subset with its own geometry
  3. it must clear the ALL-CELL EMPIRICAL NULL at p99. With this many
     cells something will look good by luck; the null is the
     distribution of the same statistic computed on random-direction
     trades in the same cells, and the real best has to beat the null's
     99th percentile. This is the causal_search.py idiom and it is the
     honest substitute for Bonferroni.
  4. it must leave enough trades to matter. A 10x edge inside 2
     trades/day needs $25/trade, which is not on the table either.

Entries are at MARKET, so no fill assumption is anywhere in this.

Prior, stated up front: LOW. Roughly six million signals have already
said no, and conditioning searches are the most reliable way to
manufacture a false positive -- it is exactly how the C1 overnight
result was produced earlier today. The mechanisms above are why it is
worth one run anyway.

Output: research/FADE_CONDITIONING.md
"""
import gc
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402

TV, COMM = 2.0, 1.33
W, HZ_S = 3, 600
BRACKETS = [(5., 30.), (10., 20.), (20., 10.), (10., 10.)]
IMP_BUCKETS = [(2., 5.), (5., 10.), (10., 20.), (20., 1e9)]
HOURS = [(13, 15), (15, 17), (17, 18), (18, 20)]
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def main():
    meta = fuse.tape_meta()
    cons = [c for c in fuse.NQ_CONTRACTS if c in meta][:4]
    acc = {}
    rng = np.random.default_rng(77)
    for cn in cons:
        ts, px, _ = fuse.load_tape(meta[cn]["path"])
        o_ = np.argsort(ts, kind="stable")
        ts, px = ts[o_], px[o_]
        idx = pd.to_datetime(ts)
        g = pd.Series(px, index=idx).resample("1min")
        bo = g.first().ffill().values
        bh = g.max().ffill().values
        bl = g.min().ffill().values
        bcs = g.last().ffill()
        bc = bcs.values
        bt = bcs.index.view(np.int64)
        hh = bcs.index.hour.values
        rth = np.asarray((bcs.index.hour * 60 + bcs.index.minute
                          >= 13 * 60 + 30) & (bcs.index.hour < 20))
        rngs = pd.Series(bh - bl).rolling(60).mean().values
        rmed = pd.Series(rngs).rolling(600, min_periods=100).median().values
        day = (bt // (86400 * 10**9))
        dhi = pd.Series(bh).groupby(day).cummax().values
        dlo = pd.Series(bl).groupby(day).cummin().values

        for i in range(W + 1, len(bc) - 12):
            if not rth[i] or not np.isfinite(rmed[i]):
                continue
            move = bc[i] - bo[i - W + 1]
            am = abs(move)
            if am < 2.0:
                continue
            up = move > 0
            t0 = int(bt[i]) + 60_000_000_000
            j0 = int(np.searchsorted(ts, t0))
            jH = int(np.searchsorted(ts, t0 + HZ_S * 10**9))
            if j0 >= jH:
                continue
            seg = px[j0:jH]
            entry = float(seg[0])
            cmin = np.minimum.accumulate(seg)
            cmax = np.maximum.accumulate(seg)
            # conditioning tags
            ib = next(k for k, (a, b) in enumerate(IMP_BUCKETS)
                      if a <= am < b)
            hb = next((k for k, (a, b) in enumerate(HOURS)
                       if a <= hh[i] < b), None)
            vb = 1 if rngs[i] > rmed[i] else 0
            dr = dhi[i] - dlo[i]
            pb = 1 if dr > 0 and (bc[i] - dlo[i]) / dr > 0.8 else (
                0 if dr > 0 and (bc[i] - dlo[i]) / dr < 0.2 else 2)
            tags = [("imp", ib), ("hour", hb), ("vol", vb), ("pos", pb)]
            fade = -1 if up else 1
            rnd = 1 if rng.random() < 0.5 else -1
            for (S, T) in BRACKETS:
                for side, who in ((fade, "fade"), (rnd, "RAND")):
                    if side > 0:
                        si = np.searchsorted(-cmin, -(entry - S))
                        ti = np.searchsorted(cmax, entry + T)
                    else:
                        si = np.searchsorted(cmax, entry + S)
                        ti = np.searchsorted(-cmin, -(entry - T))
                    if ti < si:
                        pnl = T * TV
                    elif si < len(seg):
                        pnl = -S * TV
                    else:
                        pnl = side * (float(seg[-1]) - entry) * TV
                    pnl -= COMM
                    for tname, tv_ in tags:
                        if tv_ is None:
                            continue
                        k = (tname, tv_, S, T, who)
                        a = acc.setdefault(k, {"p": 0.0, "n": 0})
                        a["p"] += pnl
                        a["n"] += 1
        del ts, px
        gc.collect()
        print(f"{cn} done", flush=True)

    days = 364
    rows = []
    for (tname, tv_, S, T, who), a in acc.items():
        if who != "fade" or a["n"] < 800:
            continue
        r = acc.get((tname, tv_, S, T, "RAND"))
        if not r or not r["n"]:
            continue
        ev = a["p"] / a["n"]
        rev = r["p"] / r["n"]
        rows.append((ev - rev, ev, rev, tname, tv_, S, T, a["n"]))
    nulls = sorted(r[2] for r in rows)
    p99 = (np.percentile([r[2] for r in rows], 99) if rows else 0.0)
    rows.sort(reverse=True)

    log("# Is the fade's edge concentrated in a subset?")
    log()
    log("The fade is worth about +0.3 percentage points overall and "
        "needs +3.5 to +4.9. Spread evenly that is hopeless, so the only "
        "surviving story is concentration: the edge living at full "
        "strength inside some subset and absent elsewhere. That needs "
        "roughly 10x.")
    log()
    log(f"NQ, {len(cons)} quarters, MARKET entries (no fill assumption "
        f"anywhere), ${COMM:.2f} real cost, 10-minute horizon. Each cell "
        f"carries its OWN random-direction control, because every split "
        f"selects a subset with its own geometry and the global control "
        f"does not apply to it.")
    log()
    log("| conditioning | bucket | bracket | n | fade $/trade | "
        "RANDOM same cell | **fade - random** |")
    log("|" + "---|" * 7)
    for d, ev, rev, tname, tv_, S, T, n in rows[:18]:
        log(f"| {tname} | {tv_} | {S:.0f}/{T:.0f} | {n:,} | "
            f"${ev:+.2f} | ${rev:+.2f} | **${d:+.2f}** |")
    pos = [r for r in rows if r[1] > 0 and r[0] > 0]
    log()
    log(f"**Cells positive net of cost AND beating their own control: "
        f"{len(pos)} of {len(rows)}**")
    log()
    log(f"All-cell empirical null (99th percentile of the "
        f"random-direction cells): **${p99:+.2f}/trade**. With this many "
        f"cells something always looks good by luck, so the real best "
        f"has to clear that line, not merely be positive.")
    log()
    if rows:
        best = rows[0]
        log(f"Best real cell: {best[3]}={best[4]} {best[5]:.0f}/"
            f"{best[6]:.0f} at **${best[1]:+.2f}/trade** over "
            f"{best[7]:,} trades — "
            + ("**clears the null**" if best[1] > p99 else
               f"does NOT clear the ${p99:+.2f} null."))
        log()
        log(f"At {best[7]/days:.1f} trades/day, ${best[1]:+.2f} a trade "
            f"is **${best[1]*best[7]/days*5:+,.0f}/week** — against the "
            f"$300/week target.")
    log()
    open(os.path.join(fuse.ROOT, "research",
                      "FADE_CONDITIONING.md"), "w").write("\n".join(L) + "\n")
    print("wrote research/FADE_CONDITIONING.md")


if __name__ == "__main__":
    main()
