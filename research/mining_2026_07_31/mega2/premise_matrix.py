"""Premise matrix: continuation vs FADE, every retracement depth,
both level definitions -- engine-free.

The INVERSE FADE spec (STRAT_INVERT=1, retr 0.236, S10 T20, w4)
claimed +$1,952/day on the paper simulator and delivered -$248/day
live. Its own spec sheet blames wick-touch LIMIT fills. That explains
the EXECUTION gap, but it doesn't answer whether the fade SIGNAL
carries information -- so this measures the signal alone:

  from the first tick that touches the retracement level, does price
  reach the target or the stop first?

for both trade directions, five retracement depths, both anchors
(close-to-close and the live bot's fib-of-range), against a random
tick baseline. No fill model, no lockout, no costs in the outcome --
costs only convert the outcome mix into EV.

An executability note that matters for reading the fade rows: after an
UP impulse the level sits BELOW the market, so a fade SHORT there
cannot rest as a limit (a sell limit under the market executes
immediately at the higher bid). The fade is only reachable with a
market/stop entry, which pays the gap. These rows therefore measure
the ceiling the fade could have if entry were free.

Output: research/PREMISE_MATRIX.md
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402

IMP = 5.0
S, T = 10.0, 20.0
TV, TICK, COMM = 2.0, 0.25, 1.24
HZ = 600 * 1_000_000_000
CONFIGS = [(w, r, d, a)
           for w in (4, 6)
           for r in (0.236, 0.382, 0.618)
           for d in ("cont", "fade")
           for a in ("close", "range")]


def main():
    meta = fuse.tape_meta()
    cons = [c for c in fuse.NQ_CONTRACTS if c in meta]
    acc = {c: {"t": 0, "s": 0, "o": 0} for c in CONFIGS}
    base = {"t": 0, "s": 0, "o": 0}
    rng = np.random.default_rng(5)
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
        bt = bcs.index.view(np.int64)
        bc = bcs.values
        rth = np.asarray((bcs.index.hour * 60 + bcs.index.minute
                          >= 13 * 60 + 30) & (bcs.index.hour < 20))

        def walk(f, lvl, side, jend):
            seg = px[f:jend]
            sp, tp = lvl - side * S, lvl + side * T
            if side > 0:
                si = np.flatnonzero(seg <= sp)
                ti = np.flatnonzero(seg >= tp)
            else:
                si = np.flatnonzero(seg >= sp)
                ti = np.flatnonzero(seg <= tp)
            sa = si[0] if len(si) else 10**9
            ta = ti[0] if len(ti) else 10**9
            return "t" if ta < sa else ("s" if sa < 10**9 else "o")

        for (w, r, d, a) in CONFIGS:
            cnt = acc[(w, r, d, a)]
            for i in range(w + 1, len(bc)):
                if not rth[i]:
                    continue
                if a == "range":
                    move = bc[i] - bo[i - w + 1]
                    hi_ = bh[i - w + 1:i + 1].max()
                    lo_ = bl[i - w + 1:i + 1].min()
                    rg = hi_ - lo_
                    if rg <= 0:
                        continue
                    lvl = (hi_ - r * rg) if move > 0 else (lo_ + r * rg)
                else:
                    move = bc[i] - bc[i - w]
                    lvl = bc[i] - r * move
                if abs(move) < IMP:
                    continue
                up = move > 0
                bclose = bt[i] + 60_000_000_000
                j0 = np.searchsorted(ts, bclose)
                jend = np.searchsorted(ts, bclose + HZ)
                if j0 >= jend:
                    continue
                seg = px[j0:jend]
                hit = np.flatnonzero(seg < lvl) if up else \
                    np.flatnonzero(seg > lvl)
                if not len(hit):
                    continue
                f = j0 + hit[0]
                side = (1 if up else -1)
                if d == "fade":
                    side = -side
                cnt[walk(f, float(lvl), side, jend)] += 1
        # one shared random baseline
        rt = np.flatnonzero(np.asarray(
            (idx.hour * 60 + idx.minute >= 13 * 60 + 30)
            & (idx.hour < 20)))
        if len(rt):
            for f in rng.choice(rt, size=min(12000, len(rt)),
                                replace=False):
                side = 1 if rng.integers(0, 2) else -1
                jend = np.searchsorted(ts, ts[f] + HZ)
                base[walk(int(f), float(px[f]), side, jend)] += 1
        del ts, px, bo, bh, bl, bcs
        import gc
        gc.collect()
        print(f"{cn} done", flush=True)

    def ev(d):
        n = max(sum(d.values()), 1)
        return (d["t"] * T * TV + d["s"] * (-(S + TICK) * TV)
                + d["o"] * (-TICK * TV)) / n - COMM

    be = ((S + TICK) * TV + COMM) / (T * TV + (S + TICK) * TV + COMM)
    bn = max(sum(base.values()), 1)
    L = ["# Continuation vs FADE: does either direction carry "
         "information?", "",
         f"NQ, 8 quarters, impulse >= {IMP:.0f}pt, bracket "
         f"{S:.0f}/{T:.0f}, 10-min horizon, engine-free. "
         f"Breakeven target-first rate: **{be:.1%}**. Random-tick "
         f"baseline: **{base['t']/bn:.2%}** ({bn:,} samples).", "",
         "| w | retr | direction | anchor | n | target first | "
         "EV/trade | EV at ZERO cost |", "|" + "---|" * 8]
    best = None
    for (w, r, d, a) in CONFIGS:
        c = acc[(w, r, d, a)]
        n = max(sum(c.values()), 1)
        pt = c["t"] / n
        z = (c["t"] * T * TV + c["s"] * (-S * TV)) / n
        L.append(f"| {w} | {r} | {'**FADE**' if d == 'fade' else 'cont'}"
                 f" | {a} | {n:,} | {pt:.2%} | ${ev(c):+.2f} | "
                 f"${z:+.2f} |")
        if best is None or pt > best[0]:
            best = (pt, w, r, d, a, ev(c))
    L += ["", f"Best cell: {best[3]} w={best[1]} retr={best[2]} "
          f"anchor={best[4]} at {best[0]:.2%} target-first "
          f"(${best[5]:+.2f}/trade) vs breakeven {be:.1%}.", ""]
    out = os.path.join(fuse.ROOT, "research", "PREMISE_MATRIX.md")
    open(out, "w").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
