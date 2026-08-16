"""HIGH-FREQUENCY screen: the regime the previous searches never tested.

Everything before used 5-40pt brackets on 10-minute horizons. The
stated goal is different: 100-300 trades/day, small targets, ~$1/trade
net. That regime lives on sub-minute bars with 1-6pt brackets and
1-5 minute horizons, and it has never been searched.

  bars       15 SECONDS (4x the signal density of 1-min)
  brackets   1/2 2/4 3/6 5/10 (1:2) and 2/2 3/3 5/5 (1:1) and 2/1 4/2
  horizons   60s, 180s, 300s
  entry      MARKET at the signal bar's close -- no fill assumptions
  costs      reported at BOTH retail $1.24 and membership $0.36
  control    RANDOM signal at matched frequency

Success criterion, stated up front so it cannot be moved afterwards:
a combination must net >= $1.00/trade at >= 100 trades/day.

Output: research/HF_SCREEN.md
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402

TV = 2.0
BARS = "15s"
BAR_S = 15
BRACKETS = [(1., 2.), (2., 4.), (3., 6.), (5., 10.),
            (2., 2.), (3., 3.), (5., 5.), (2., 1.), (4., 2.)]
HORIZONS = [60, 180, 300]
MAXH = max(HORIZONS)


def build_signals(bc, bh, bl, bv, rth, rng):
    n = len(bc)
    out = {}

    def sided(u, d):
        s = np.zeros(n, dtype=np.int8)
        s[u] = 1
        s[d] = -1
        return s

    for k, thr in ((2, 1.5), (4, 3.0), (8, 5.0)):
        d = np.full(n, np.nan)
        d[k:] = bc[k:] - bc[:-k]
        out[f"mom{k*BAR_S}s_cont"] = sided(d >= thr, d <= -thr)
        out[f"mom{k*BAR_S}s_fade"] = sided(d <= -thr, d >= thr)

    step = np.zeros(n)
    step[1:] = np.sign(bc[1:] - bc[:-1])
    run = np.zeros(n)
    for i in range(1, n):
        run[i] = run[i - 1] + step[i] if step[i] == step[i - 1] else step[i]
    out["streak4_cont"] = sided(run >= 4, run <= -4)
    out["streak4_fade"] = sided(run <= -4, run >= 4)

    s = pd.Series(bc)
    ma = s.rolling(80).mean().values          # 20 min
    sd = s.rolling(80).std().values
    hi = bc > ma + 1.5 * sd
    lo = bc < ma - 1.5 * sd
    out["band_fade"] = sided(lo, hi)
    out["band_cont"] = sided(hi, lo)

    vmed = pd.Series(bv).rolling(240).median().values
    spike = bv > 3.0 * np.maximum(vmed, 1)
    out["vspike_cont"] = sided(spike & (step > 0), spike & (step < 0))
    out["vspike_fade"] = sided(spike & (step < 0), spike & (step > 0))

    hi20 = s.rolling(20).max().values
    lo20 = s.rolling(20).min().values
    out["brk20_cont"] = sided(bc >= hi20, bc <= lo20)
    out["brk20_fade"] = sided(bc <= lo20, bc >= hi20)

    out["RANDOM"] = np.where(rng.random(n) < 0.15,
                             np.where(rng.random(n) < 0.5, 1, -1),
                             0).astype(np.int8)
    for k in out:
        out[k] = np.where(rth, out[k], 0).astype(np.int8)
    return out


def main():
    meta = fuse.tape_meta()
    cons = [c for c in fuse.NQ_CONTRACTS if c in meta]
    acc = {}
    days = 0
    rng = np.random.default_rng(23)
    for cn in cons:
        ts, px, sz = fuse.load_tape(meta[cn]["path"])
        o_ = np.argsort(ts, kind="stable")
        ts, px, sz = ts[o_], px[o_], sz[o_]
        idx = pd.to_datetime(ts)
        g = pd.Series(px, index=idx).resample(BARS)
        bcs = g.last().ffill()
        bc = bcs.values
        bh = g.max().ffill().values
        bl = g.min().ffill().values
        bv = pd.Series(sz, index=idx).resample(BARS).sum().values
        bt = bcs.index.view(np.int64)
        rth = np.asarray((bcs.index.hour * 60 + bcs.index.minute
                          >= 13 * 60 + 30) & (bcs.index.hour < 20))
        days += len(np.unique(bcs.index[rth].normalize()))
        sig = build_signals(bc, bh, bl, bv, rth, rng)

        for name, arr in sig.items():
            for i in np.flatnonzero(arr != 0):
                side = int(arr[i])
                t0 = int(bt[i]) + BAR_S * 1_000_000_000
                j0 = np.searchsorted(ts, t0)
                jH = np.searchsorted(ts, t0 + MAXH * 1_000_000_000)
                if j0 >= jH:
                    continue
                seg = px[j0:jH]
                tseg = ts[j0:jH]
                entry = float(seg[0])
                cmin = np.minimum.accumulate(seg)
                cmax = np.maximum.accumulate(seg)
                hz_idx = [np.searchsorted(tseg, t0 + h * 1_000_000_000)
                          for h in HORIZONS]
                for (S, T) in BRACKETS:
                    sl = entry - side * S
                    tl = entry + side * T
                    if side > 0:
                        si = np.searchsorted(-cmin, -sl)
                        ti = np.searchsorted(cmax, tl)
                    else:
                        si = np.searchsorted(cmax, sl)
                        ti = np.searchsorted(-cmin, -tl)
                    for h, hi_ in zip(HORIZONS, hz_idx):
                        a = acc.setdefault((name, S, T, h),
                                           {"t": 0, "s": 0, "o": 0,
                                            "opnl": 0.0})
                        s_ok, t_ok = si < hi_, ti < hi_
                        if t_ok and (not s_ok or ti < si):
                            a["t"] += 1
                        elif s_ok:
                            a["s"] += 1
                        else:
                            # neither barrier reached: the position is
                            # closed at the market when the clock runs
                            # out, NOT left flat. Booking it at zero
                            # hides every loser that drifted against us
                            # without travelling the full stop distance.
                            a["o"] += 1
                            k_ = min(hi_, len(seg) - 1)
                            a["opnl"] += side * (float(seg[k_]) - entry)
        del ts, px, sz
        import gc
        gc.collect()
        print(f"{cn} done", flush=True)

    rows = []
    for (name, S, T, h), d in acc.items():
        n = d["t"] + d["s"] + d["o"]
        if n < 2000:
            continue
        tpd = n / max(days, 1)
        pt = d["t"] / n
        gross = (d["t"] * T * TV - d["s"] * S * TV + d["opnl"] * TV
                 - n * 0.125 * TV) / n          # half-tick spread
        rows.append((gross - 1.24, gross - 0.36, pt, tpd, name, S, T,
                     h, n, d["o"] / n))
    rows.sort(key=lambda r: -r[1])
    L = ["# High-frequency screen: 15-second bars, tight brackets", "",
         f"NQ, 8 quarters ({days} RTH sessions), market entry at the "
         "signal bar's close, half-tick spread charged. Sorted by EV at "
         "the membership rate.", "",
         "**Success bar (set before running): net >= $1.00/trade at "
         ">= 100 trades/day.**", "",
         "A position reaching neither barrier is closed at the market at "
         "the horizon and booked at that price. An earlier version booked "
         "it at zero, which flatters any wide stop by hiding the losers "
         "that drifted without travelling the full stop distance; the "
         "`timeout` column is how big that bucket is.", "",
         "| signal | bracket | horizon | trades/day | target first | "
         "timeout | EV @ $1.24 | EV @ $0.36 |", "|" + "---|" * 8]
    for ev1, ev2, pt, tpd, name, S, T, h, n, po in rows[:25]:
        L.append(f"| {name} | {S:.0f}/{T:.0f} | {h}s | {tpd:.0f} | "
                 f"{pt:.1%} | {po:.0%} | ${ev1:+.2f} | ${ev2:+.2f} |")
    # A cell must beat the RANDOM control at its OWN bracket and horizon.
    # Positive EV means nothing if a coin flip in the same geometry is
    # positive too -- that is how the session screen produced a false
    # positive before the timeout fix.
    ctl = {(r[5], r[6], r[7]): r[1] for r in rows if r[4] == "RANDOM"}

    def beats(r):
        return r[1] > ctl.get((r[5], r[6], r[7]), -1e9) + 0.25

    hits = [r for r in rows
            if r[0] >= 1.0 and r[3] >= 100 and r[4] != "RANDOM"
            and beats(r)]
    hitsm = [r for r in rows
             if r[1] >= 1.0 and r[3] >= 100 and r[4] != "RANDOM"
             and beats(r)]
    L += ["", f"**Meeting the bar at retail $1.24: {len(hits)}**",
          f"**Meeting the bar at membership $0.36: {len(hitsm)}**",
          "", "Both counts additionally require beating the RANDOM "
          "control at the same bracket and horizon by $0.25.", ""]
    for r in (hitsm or hits)[:10]:
        L.append(f"- {r[4]} {r[5]:.0f}/{r[6]:.0f} {r[7]}s: "
                 f"{r[3]:.0f} trades/day, {r[2]:.1%} target-first, "
                 f"${r[1]:+.2f}/trade @ membership -> "
                 f"${r[1]*r[3]:+,.0f}/day")
    best_pos = [r for r in rows if r[1] > 0]
    L += ["", f"Combinations with positive EV at membership rates: "
          f"{len(best_pos)} of {len(rows)}", ""]
    out = os.path.join(fuse.ROOT, "research", "HF_SCREEN.md")
    open(out, "w").write("\n".join(L) + "\n")
    print("\n".join(L[:34]))


if __name__ == "__main__":
    main()
