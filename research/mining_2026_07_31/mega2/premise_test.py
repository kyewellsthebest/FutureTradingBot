"""Independent test of the strategy's PREMISE -- no engine involved.

Every verdict so far came from my causal engine. If that engine is
wrong, the verdicts are wrong. So this measures the one thing the
strategy claims, with a completely separate ~30-line implementation
and NO trading machinery at all: no windows, no lockout, no position
management, no commission, no slippage.

The claim: after an impulse, price retracing to the 0.618 level is
more likely than chance to run TARGET points in your favour before
STOP points against you.

Measured two ways on the same tape:
  SIGNAL   -- from the first tick that touches the retracement level
              after a qualifying impulse
  BASELINE -- from random RTH ticks (same count), same bracket

If P(target first | signal) is materially above P(target first |
random), the strategy has an edge and my engine is broken. If they
match, the engine is telling the truth.

Breakeven for a S/T bracket with costs is
  (S + slip)*tv + comm  over  (T*tv + (S+slip)*tv + comm)
Output: research/PREMISE.md
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402

W = 6
IMP = 5.0
RETR = 0.618
S, T = 10.0, 20.0
TV, TICK, COMM = 2.0, 0.25, 1.24
HORIZON_NS = 600 * 1_000_000_000


def outcome(px, j0, entry, side, s_px, t_px, j_end):
    """Walk forward from j0; return 't', 's' or 'o'."""
    seg = px[j0:j_end]
    if side > 0:
        si = np.flatnonzero(seg <= s_px)
        ti = np.flatnonzero(seg >= t_px)
    else:
        si = np.flatnonzero(seg >= s_px)
        ti = np.flatnonzero(seg <= t_px)
    s_at = si[0] if len(si) else 10**9
    t_at = ti[0] if len(ti) else 10**9
    if t_at < s_at:
        return "t"
    if s_at < 10**9:
        return "s"
    return "o"


def main():
    meta = fuse.tape_meta()
    cons = [c for c in fuse.NQ_CONTRACTS if c in meta]
    sig = {"t": 0, "s": 0, "o": 0}
    base = {"t": 0, "s": 0, "o": 0}
    rng = np.random.default_rng(11)
    for cn in cons:
        ts, px, _ = fuse.load_tape(meta[cn]["path"])
        o = np.argsort(ts, kind="stable")
        ts, px = ts[o], px[o]
        idx = pd.to_datetime(ts)
        close = pd.Series(px, index=idx).resample("1min").last().ffill()
        bt = close.index.view(np.int64)
        bc = close.values
        rth = np.asarray((close.index.hour * 60 + close.index.minute
                          >= 13 * 60 + 30) & (close.index.hour < 20))
        n_sig = 0
        for i in range(W + 1, len(bc)):
            if not rth[i]:
                continue
            move = bc[i] - bc[i - W]
            if abs(move) < IMP:
                continue
            up = move > 0
            lvl = bc[i] - RETR * move
            bclose = bt[i] + 60_000_000_000
            j0 = np.searchsorted(ts, bclose)
            j1 = np.searchsorted(ts, bclose + HORIZON_NS)
            if j0 >= j1:
                continue
            seg = px[j0:j1]
            hit = np.flatnonzero(seg < lvl) if up else \
                np.flatnonzero(seg > lvl)
            if not len(hit):
                continue
            f = j0 + hit[0]
            side = 1 if up else -1
            r = outcome(px, f, lvl, side, lvl - side * S,
                        lvl + side * T,
                        np.searchsorted(ts, bclose + HORIZON_NS))
            sig[r] += 1
            n_sig += 1
        # baseline: same number of random RTH starts, same bracket,
        # direction drawn 50/50 (the signal's own long/short mix is
        # near-even, and a random-time test must not inherit drift)
        rth_ticks = np.flatnonzero(np.asarray(
            (idx.hour * 60 + idx.minute >= 13 * 60 + 30)
            & (idx.hour < 20)))
        if len(rth_ticks) and n_sig:
            picks = rng.choice(rth_ticks, size=min(n_sig, len(rth_ticks)),
                               replace=False)
            for f in picks:
                side = 1 if rng.integers(0, 2) else -1
                lvl = px[f]
                jend = np.searchsorted(ts, ts[f] + HORIZON_NS)
                r = outcome(px, f, lvl, side, lvl - side * S,
                            lvl + side * T, jend)
                base[r] += 1
        del ts, px, close
        import gc
        gc.collect()
        print(f"{cn}: signals {n_sig:,}", flush=True)

    def stats(d, label):
        n = sum(d.values())
        pt = d["t"] / n
        ps = d["s"] / n
        po = d["o"] / n
        # P&L per trade at these outcome rates, all costs in
        ev = (d["t"] * T * TV
              + d["s"] * (-(S + TICK) * TV)
              + d["o"] * (-TICK * TV)) / n - COMM
        return (f"| {label} | {n:,} | {pt:.2%} | {ps:.2%} | {po:.2%} | "
                f"${ev:+.2f} |"), pt, ev

    row_s, pt_s, ev_s = stats(sig, "**SIGNAL** (0.618 pullback)")
    row_b, pt_b, ev_b = stats(base, "BASELINE (random RTH ticks)")
    theo = S / (S + T)
    be = ((S + TICK) * TV + COMM) / (T * TV + (S + TICK) * TV + COMM)
    L = ["# The strategy's premise, measured without my engine", "",
         f"NQ, 8 quarters, impulse >= {IMP:.0f}pt over {W} bars, "
         f"retracement {RETR}, bracket {S:.0f}/{T:.0f}, 10-min horizon. "
         "No windows, no lockout, no position management -- just: from "
         "the tick that touches the level, which side of the bracket "
         "does price reach first?", "",
         "| set | n | target first | stop first | neither | EV/trade |",
         "|---|---|---|---|---|---|", row_s, row_b, "",
         f"- random-walk expectation for a {S:.0f}/{T:.0f} bracket: "
         f"**{theo:.1%}**",
         f"- breakeven with \\${COMM} commission + 1 tick stop slip: "
         f"**{be:.1%}**",
         f"- measured edge of signal over random ticks: "
         f"**{(pt_s - pt_b) * 100:+.2f} percentage points**", "",
         ("**The signal beats random ticks and clears breakeven -- the "
          "engine is wrong.**" if (pt_s > pt_b and pt_s > be) else
          "**The signal does not clear breakeven; it is "
          f"{'above' if pt_s > pt_b else 'at or below'} random-tick "
          "selection but not by enough to pay the cost stack.**"), ""]
    out = os.path.join(fuse.ROOT, "research", "PREMISE.md")
    open(out, "w").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
