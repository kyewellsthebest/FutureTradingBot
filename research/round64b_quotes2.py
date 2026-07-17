"""Round 64b: sharpened quotes A/B. Fixes from 64a: (1) imbalance
thresholds set from the actual distribution (quantile terciles), not
guessed absolutes; (2) adds instantaneous top-of-book imbalance,
quote-rate (book panic gauge) and total depth; (3) bootstrap
significance on every split - 131 trades is small, no fooling
ourselves with noise.
"""
import glob, json, sys, time
import numpy as np, pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, "research")
import round54_clock as K
from round58_frontier import prep_clock
from round64_quotes import sim_bp_trades, LAT_NS

QDIR = "/tmp/claude-0/quotes"
W_FAST, W_SLOW = 500, 5000
RNG = np.random.default_rng(64)


def attach(recs):
    qfiles = {f.split("_")[-1][:8]: f
              for f in sorted(glob.glob(f"{QDIR}/Q_MNQU6_*.parquet"))}
    by_day = {}
    for r in recs:
        d = pd.to_datetime(r[0], utc=True).strftime("%Y%m%d")
        by_day.setdefault(d, []).append(r)
    out = []
    for d in sorted(by_day):
        f = qfiles.get(d)
        if f is None:
            continue
        t = pq.read_table(f)
        qts = t.column("ts").to_numpy()
        bid = t.column("bid").to_numpy()
        ask = t.column("ask").to_numpy()
        bs = t.column("bid_size").to_numpy().astype(np.float64)
        asz = t.column("ask_size").to_numpy().astype(np.float64)
        del t
        # CRITICAL: quote files are stored newest-first - sort ascending
        o = np.argsort(qts, kind="stable")
        qts, bid, ask, bs, asz = qts[o], bid[o], ask[o], bs[o], asz[o]
        for sig_ts, s, pnl, exit_ts in by_day[d]:
            j = int(np.searchsorted(qts, sig_ts + LAT_NS, "right")) - 1
            if j < W_SLOW:
                continue
            bi, ai = bs[j], asz[j]
            bf, af = bs[j-W_FAST:j].sum(), asz[j-W_FAST:j].sum()
            bl, al_ = bs[j-W_SLOW:j].sum(), asz[j-W_SLOW:j].sum()
            span_ns = qts[j] - qts[j - W_FAST]
            out.append(dict(
                s=s, pnl=pnl,
                spread=float(ask[j] - bid[j]),
                imb_i=bi / max(bi + ai, 1.0),
                imb_f=bf / max(bf + af, 1.0),
                imb_s=bl / max(bl + al_, 1.0),
                qrate=W_FAST / max(span_ns / 1e9, 1e-6),
                depth=float(bi + ai)))
        del qts, bid, ask, bs, asz
        print(f"  {d} done", flush=True)
    return out


def boot_diff(pa, pb, n=20000):
    """P(mean(A) > mean(B)) under bootstrap resampling."""
    if not len(pa) or not len(pb):
        return float("nan")
    ma = RNG.choice(pa, (n, len(pa))).mean(1)
    mb = RNG.choice(pb, (n, len(pb))).mean(1)
    return float((ma > mb).mean())


def split(name, rows, key, signed):
    """Tercile split on (signed) feature; report each bucket + boot."""
    v = np.array([(r[key] - 0.5) * r["s"] + 0.5 if signed else r[key]
                  for r in rows])
    p = np.array([r["pnl"] for r in rows])
    q1, q2 = np.quantile(v, [1/3, 2/3])
    lo, hi = p[v <= q1], p[v > q2]
    mid = p[(v > q1) & (v <= q2)]
    conf = boot_diff(hi, lo)
    print(f"  {name:<26} cuts {q1:.4f}/{q2:.4f}", flush=True)
    for tag, arr in (("low ", lo), ("mid ", mid), ("high", hi)):
        wr = (arr > 0).mean() * 100 if len(arr) else 0
        print(f"    {tag} n={len(arr):>3}  WR {wr:4.1f}%  "
              f"avg {arr.mean():+7.2f}  tot {arr.sum():+8.0f}")
    print(f"    bootstrap P(high beats low) = {conf:.3f}  "
          f"{'SIGNIFICANT' if conf > 0.975 or conf < 0.025 else 'noise-compatible'}",
          flush=True)


def main():
    t0 = time.time()
    K.build_tape()
    prep_clock(K.D[60], K.D["ts"])
    recs = sim_bp_trades(K.D["ts"], K.D["px"], K.D[60])
    lo = pd.Timestamp("2026-06-08", tz="UTC").value
    hi = pd.Timestamp("2026-07-09", tz="UTC").value
    recs = [r for r in recs if lo <= r[0] < hi]
    K.D.clear()
    rows = attach(recs)
    print(f"\n{len(rows)} trades with book state ({time.time()-t0:.0f}s)\n",
          flush=True)
    for k in ("imb_i", "imb_f", "imb_s"):
        v = np.array([(r[k] - 0.5) * r["s"] + 0.5 for r in rows])
        print(f"{k} (aligned-signed): p10 {np.percentile(v,10):.4f} "
              f"med {np.median(v):.4f} p90 {np.percentile(v,90):.4f}",
              flush=True)
    print()
    split("spread (raw)", rows, "spread", signed=False)
    split("imb INSTANT (aligned)", rows, "imb_i", signed=True)
    split("imb FAST ~1.5s (aligned)", rows, "imb_f", signed=True)
    split("imb SLOW ~15s (aligned)", rows, "imb_s", signed=True)
    split("quote rate (panic gauge)", rows, "qrate", signed=False)
    split("top depth", rows, "depth", signed=False)
    # the 64a headline claim, tested properly
    pa = np.array([r["pnl"] for r in rows if (r["imb_f"]-0.5)*r["s"] > 0])
    pb = np.array([r["pnl"] for r in rows if (r["imb_f"]-0.5)*r["s"] <= 0])
    print(f"\n64a headline (fast imb >0.5 aligned vs contra): "
          f"n {len(pa)}/{len(pb)}  "
          f"P(aligned beats contra) = {boot_diff(pa, pb):.3f}", flush=True)
    with open("research/round64b_rows.json", "w") as f:
        json.dump(rows, f)
    print(f"\nDONE ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
