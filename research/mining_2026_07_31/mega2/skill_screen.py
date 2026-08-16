"""SKILL SCREEN: which signal families predict direction at all?

The target is concrete: ~38-40% target-first on a 1:2 bracket buys
$300/week per strategy. Breakeven with zero cost is 33.3%. The
pullback family measures 28.0% -- worse than a coin flip.

Rather than build strategies and discover they fail, this screens the
one property any strategy needs: does the signal predict which side of
a bracket price reaches first? Entry is at the MARKET on the signal
bar's close -- no limit orders, no fill assumptions, nothing to argue
about. If a family can't clear 33.3% here, no execution scheme saves
it; if it clears 38%, it earns a full validation.

Families screened (each in both directions where meaningful):
  mom3 / mom10    short- and medium-horizon momentum
  streak          N consecutive same-direction bars
  ext30           price at a 30-bar extreme
  vwapdev         deviation from session VWAP in sigmas
  compress        low-volatility coil, trade the last bar's direction
  volspike        bar volume >> median
  openbreak       break of the 13:30-14:00 opening range
  range_pos       position of the close within the day's range

Brackets: 5/10, 10/20, 20/40 (1:2) and 10/5, 20/10 (2:1).
Baseline: identical measurement from random RTH bar closes.
Output: research/SKILL_SCREEN.md
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse                  # noqa: E402
import causal_engine as ce   # noqa: E402

HZ = 600 * 1_000_000_000
TV, TICK, COMM = 2.0, 0.25, 1.24
BRACKETS = [(5.0, 10.0), (10.0, 20.0), (20.0, 40.0),
            (10.0, 5.0), (20.0, 10.0)]


def signals(bo, bh, bl, bc, bv, rth, tod):
    """Return {name: side_array} where side is +1/-1/0 per bar."""
    n = len(bc)
    out = {}
    z = np.zeros(n, dtype=np.int8)

    def sided(cond_up, cond_dn):
        s = np.zeros(n, dtype=np.int8)
        s[cond_up] = 1
        s[cond_dn] = -1
        return s

    for k, thr in ((3, 3.0), (10, 10.0)):
        d = np.full(n, np.nan)
        d[k:] = bc[k:] - bc[:-k]
        up, dn = (d >= thr), (d <= -thr)
        out[f"mom{k}_cont"] = sided(up, dn)
        out[f"mom{k}_fade"] = sided(dn, up)

    # consecutive same-direction bars
    step = np.zeros(n)
    step[1:] = np.sign(bc[1:] - bc[:-1])
    run = np.zeros(n)
    for i in range(1, n):
        run[i] = run[i - 1] + step[i] if step[i] == step[i - 1] else step[i]
    out["streak3_cont"] = sided(run >= 3, run <= -3)
    out["streak3_fade"] = sided(run <= -3, run >= 3)

    # 30-bar extreme
    s = pd.Series(bc)
    hi30 = s.rolling(30).max().values
    lo30 = s.rolling(30).min().values
    at_hi, at_lo = (bc >= hi30), (bc <= lo30)
    out["ext30_cont"] = sided(at_hi, at_lo)
    out["ext30_fade"] = sided(at_lo, at_hi)

    # session VWAP deviation
    tp = (bh + bl + bc) / 3.0
    day = (np.arange(n) // 1440)
    dv = pd.DataFrame({"d": day, "pv": tp * bv, "v": bv})
    cpv = dv.groupby("d")["pv"].cumsum().values
    cv = dv.groupby("d")["v"].cumsum().values
    vwap = np.where(cv > 0, cpv / np.maximum(cv, 1e-9), bc)
    dev = bc - vwap
    sd = pd.Series(dev).rolling(120).std().values
    hi_dev = dev > 1.5 * sd
    lo_dev = dev < -1.5 * sd
    out["vwapdev_fade"] = sided(lo_dev, hi_dev)
    out["vwapdev_cont"] = sided(hi_dev, lo_dev)

    # volatility compression -> trade last bar direction
    rng10 = pd.Series(bh - bl).rolling(10).mean().values
    rng60 = pd.Series(bh - bl).rolling(60).mean().values
    coil = rng10 < 0.6 * rng60
    out["compress_cont"] = sided(coil & (step > 0), coil & (step < 0))

    # volume spike
    vmed = pd.Series(bv).rolling(60).median().values
    spike = bv > 3.0 * np.maximum(vmed, 1)
    out["volspike_cont"] = sided(spike & (step > 0), spike & (step < 0))
    out["volspike_fade"] = sided(spike & (step < 0), spike & (step > 0))

    # opening-range break (range set 13:30-14:00 UTC)
    orh = np.full(n, np.nan)
    orl = np.full(n, np.nan)
    inor = (tod >= 13 * 60 + 30) & (tod < 14 * 60)
    for d0 in np.unique(day):
        m = (day == d0) & inor
        if m.sum() < 5:
            continue
        after = (day == d0) & (tod >= 14 * 60)
        orh[after] = bh[m].max()
        orl[after] = bl[m].min()
    out["openbreak_cont"] = sided(bc > orh, bc < orl)
    out["openbreak_fade"] = sided(bc < orl, bc > orh)

    for k in out:
        out[k] = np.where(rth, out[k], 0).astype(np.int8)
    return out


def main():
    meta = fuse.tape_meta()
    cons = [c for c in fuse.NQ_CONTRACTS if c in meta]
    acc = {}
    rng = np.random.default_rng(17)
    for cn in cons:
        ts, px, sz = fuse.load_tape(meta[cn]["path"])
        o_ = np.argsort(ts, kind="stable")
        ts, px, sz = ts[o_], px[o_], sz[o_]
        idx = pd.to_datetime(ts)
        g = pd.Series(px, index=idx).resample("1min")
        bo = g.first().ffill().values
        bh = g.max().ffill().values
        bl = g.min().ffill().values
        bcs = g.last().ffill()
        bc = bcs.values
        bv = pd.Series(sz, index=idx).resample("1min").sum().values
        bt = bcs.index.view(np.int64)
        tod = (bcs.index.hour * 60 + bcs.index.minute).values
        rth = np.asarray((tod >= 13 * 60 + 30) & (bcs.index.hour < 20))
        mi = ce.MinuteIndex(ts, px, bt)
        sig = signals(bo, bh, bl, bc, bv, rth, tod)
        sig["RANDOM"] = np.where(
            rth & (rng.random(len(bc)) < 0.25),
            np.where(rng.random(len(bc)) < 0.5, 1, -1), 0).astype(np.int8)

        for name, arr in sig.items():
            fires = np.flatnonzero(arr != 0)
            for (S, T) in BRACKETS:
                key = (name, S, T)
                a = acc.setdefault(key, {"t": 0, "s": 0, "o": 0})
                for i in fires:
                    side = int(arr[i])
                    t0 = int(bt[i]) + 60_000_000_000
                    j0 = np.searchsorted(ts, t0)
                    if j0 >= len(ts):
                        continue
                    entry = float(px[j0])
                    tend = t0 + HZ
                    js = mi.first_beyond(t0, tend, entry - side * S,
                                         below=(side > 0), inclusive=True)
                    jt = mi.first_beyond(t0, tend, entry + side * T,
                                         below=(side < 0), inclusive=True)
                    st = int(ts[js]) if js >= 0 else None
                    tt = int(ts[jt]) if jt >= 0 else None
                    if tt is not None and (st is None or tt < st):
                        a["t"] += 1
                    elif st is not None:
                        a["s"] += 1
                    else:
                        a["o"] += 1
        del ts, px, sz, mi
        import gc
        gc.collect()
        print(f"{cn} done", flush=True)

    rows = []
    for (name, S, T), d in acc.items():
        n = d["t"] + d["s"] + d["o"]
        if n < 500:
            continue
        pt = d["t"] / n
        # entry pays half a tick crossing the spread
        ev = (d["t"] * T * TV - d["s"] * S * TV
              - n * (TICK / 2) * TV) / n - COMM
        rows.append((ev, pt, name, S, T, n))
    rows.sort(reverse=True)
    L = ["# Skill screen: does any signal family predict direction?", "",
         "Entry at the MARKET on the signal bar's close (no limit "
         "orders, no fill assumptions), 10-min horizon, half-tick "
         "spread + $1.24 commission. NQ, 8 quarters.", "",
         "Target for $300/week: **~38-40%** target-first on a 1:2 "
         "bracket. Zero-cost breakeven: **33.3%**.", "",
         "| signal | bracket | n | target first | EV/trade |",
         "|---|---|---|---|---|"]
    for ev, pt, name, S, T, n in rows[:28]:
        L.append(f"| {name} | {S:.0f}/{T:.0f} | {n:,} | {pt:.2%} | "
                 f"${ev:+.2f} |")
    good = [r for r in rows if r[0] > 0]
    L += ["", f"**Positive-EV combinations: {len(good)} of {len(rows)}**",
          ""]
    for ev, pt, name, S, T, n in good[:15]:
        L.append(f"- {name} {S:.0f}/{T:.0f}: {pt:.2%} target-first, "
                 f"${ev:+.2f}/trade over {n:,} signals")
    L.append("")
    out = os.path.join(fuse.ROOT, "research", "SKILL_SCREEN.md")
    open(out, "w").write("\n".join(L) + "\n")
    print("\n".join(L[:40]))


if __name__ == "__main__":
    main()
