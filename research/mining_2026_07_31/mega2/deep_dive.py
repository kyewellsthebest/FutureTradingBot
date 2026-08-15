"""Deep dive: does the negative verdict survive attacking my OWN
assumptions? Every fill rule toggled independently, 8 NQ quarters.

The causal engine embeds four judgement calls that could each be too
harsh. This tests them one at a time and together:

  entry_touch   entries fill when the tape TOUCHES the limit (vs must
                trade strictly through it)
  target_touch  targets fill on a touch (vs strict penetration)
  lockout       window  = blocked until the signal window ends +60s
                exit    = realistic bot: flat after exit, +60s, free
                none    = windows resolve independently (multi-position:
                          isolates the single-position constraint)
  comm          $1.24 RT vs $0.36 (the $1,499-membership rate) vs $0

If every combination is negative, the verdict is robust. If any
plausible combination is positive, the strategy's profitability hinges
on that assumption and it must be named.

Cells tested: the deployed cell (5/6, .618, 10/20, 600s) and the
user's ORIGINAL 2025 spec (5/4, .618, 6/12, 600s).
Output: research/DEEP_DIVE.md
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse                  # noqa: E402
import causal_engine as ce   # noqa: E402

CELLS = {
    "deployed (5/6bar, .618, S10 T20)":
        dict(imp=5.0, w=6, retr=0.618, S=10.0, T=20.0),
    "original 2025 spec (5/4bar, .618, S6 T12)":
        dict(imp=5.0, w=4, retr=0.618, S=6.0, T=12.0),
}
BASE = dict(hold_s=600, arch="limit", policy="first", tick=0.25, tv=2.0)

VARIANTS = [
    ("baseline (strict entry, strict target, window lockout)",
     dict()),
    ("entries fill on TOUCH", dict(entry_touch=True)),
    ("targets fill on TOUCH", dict(target_touch=True)),
    ("both fill on TOUCH", dict(entry_touch=True, target_touch=True)),
    ("lockout = exit+60s (realistic bot)", dict(lockout="exit")),
    ("lockout = none (multi-position)", dict(lockout="none")),
    ("TOUCH both + lockout exit",
     dict(entry_touch=True, target_touch=True, lockout="exit")),
    ("TOUCH both + no lockout",
     dict(entry_touch=True, target_touch=True, lockout="none")),
    ("membership commission $0.36",
     dict(comm=0.36)),
    ("TOUCH both + no lockout + $0.36 comm",
     dict(entry_touch=True, target_touch=True, lockout="none",
          comm=0.36)),
    ("EVERYTHING RELAXED: touch/touch/none/zero costs",
     dict(entry_touch=True, target_touch=True, lockout="none",
          comm=0.0, slip_on=False)),
]


def main():
    meta = fuse.tape_meta()
    cons = [c for c in fuse.NQ_CONTRACTS if c in meta]
    # stream one quarter at a time -- holding 8 tapes at once OOMs
    # alongside the parallel family search
    acc = {(cn2, vn): [0.0, 0, 0] for cn2 in CELLS for vn, _ in VARIANTS}
    for cn in cons:
        ts, px, _ = fuse.load_tape(meta[cn]["path"])
        o = np.argsort(ts, kind="stable")
        ts, px = ts[o], px[o]
        bt, bc, rth = ce.bars_of(ts, px)
        mi = ce.MinuteIndex(ts, px, bt)
        for cname, cparams in CELLS.items():
            for vname, vparams in VARIANTS:
                cell = {**BASE, **cparams, **vparams}
                tr = ce.run_cell(ts, px, bt, bc, rth, 0, len(bc), cell,
                                 mindex=mi)
                a = acc[(cname, vname)]
                a[0] += sum(t[4] for t in tr)
                a[1] += len(tr)
                a[2] += sum(1 for t in tr if t[4] > 0)
        del ts, px, bt, bc, rth, mi
        import gc
        gc.collect()
        print(f"{cn} done", flush=True)

    L = ["# Deep dive: attacking my own causal assumptions", "",
         "Every fill rule the negative verdict rests on, toggled "
         "independently across all 8 NQ quarters (full data, one fixed "
         "cell -- no selection). If the strategy only works under an "
         "assumption, this names it.", ""]
    for cname, cparams in CELLS.items():
        L += [f"## {cname}", "",
              "| variant | trades | win rate | $/trade | **total** |",
              "|---|---|---|---|---|"]
        print(f"\n=== {cname}", flush=True)
        for vname, vparams in VARIANTS:
            tot, n, wins = acc[(cname, vname)]
            per = tot / n if n else 0.0
            wr = wins / n if n else 0.0
            L.append(f"| {vname} | {n:,} | {wr:.1%} | ${per:+.2f} | "
                     f"**${tot:+,.0f}** |")
            print(f"  {vname:52} {n:6,} tr  {wr:5.1%}  "
                  f"${per:+6.2f}/tr  ${tot:+10,.0f}", flush=True)
        L.append("")
    L += ["## Read", "",
          "The last row is the physical ceiling: entries and targets "
          "fill on any touch, unlimited concurrent positions, and ZERO "
          "commission or slippage. No real account can beat it. If it "
          "is not clearly positive, no cost structure or execution "
          "improvement can rescue this cell.", ""]
    out = os.path.join(fuse.ROOT, "research", "DEEP_DIVE.md")
    open(out, "w").write("\n".join(L) + "\n")
    print("\nwrote", out, flush=True)


if __name__ == "__main__":
    main()
