"""Round 64: QUOTES A/B TEST on BP-Final. User's question, measured:
"does knowing the bids make our win rate higher / the strategy more
accurate?" We have 30 days of real top-of-book MNQ quotes (Jun 8 -
Jul 8). Run the deployed BP-Final trade generator over that window,
then for every trade look up the actual book state at the signal
moment and A/B every plausible quote filter:
  - spread state (tight 1-tick book vs stressed wide book)
  - top-of-book size imbalance, fast (~1.5s) and slow (~15s),
    aligned with vs against the fade direction, at 3 strictness levels
Each arm reports N / WR / avg$ / total$ vs the unfiltered baseline.
No theory - the same trades, split by what the book looked like.
"""
import glob, json, sys, time
import numpy as np, pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, "research")
import round54_clock as K
from round58_frontier import prep_clock

LAT_NS = 65_000_000
FEES = 1.50
PT, TICK = 2.0, 0.25
OFF, DIS = 1.0, 60.0
GUARD, XACCEL, HOLD_MIN = 8.0, 10.0, 15
EOD_NS = (20 * 60 + 55) * 60_000_000_000
ENTRY_LO, ENTRY_HI = 14.0, 20.73
QDIR = "/tmp/claude-0/quotes"
W_FAST, W_SLOW = 500, 5000       # trailing quote counts (~1.5s / ~15s)


def sim_bp_trades(ts, px, C):
    """BP-Final cap-1, returning per-trade records incl. signal ts."""
    n = len(ts)
    c, atr, hrs = C["c"], C["atr"], C["hrs"]
    bts, days, sdt = C["bts"], C["days"], np.abs(C["sdt"])
    ninf = np.nan_to_num(atr, nan=np.inf)
    kb = 10
    mom = np.concatenate(([0.0] * kb, c[kb:] - c[:-kb]))
    thr = 1.2 * ninf
    ent = (hrs >= ENTRY_LO) & (hrs < ENTRY_HI) & (sdt <= GUARD)
    raw = np.where(mom < -thr, 1, np.where(mom > thr, -1, 0))
    sig = np.where(ent, raw, 0)
    hold_ns = HOLD_MIN * 60_000_000_000
    recs = []
    busy = 0
    for i in np.flatnonzero(sig):
        if bts[i] < busy:
            continue
        s = int(sig[i])
        L = c[i] - OFF * s
        a0 = np.searchsorted(ts, bts[i] + LAT_NS, "left")
        a1 = np.searchsorted(ts, bts[i] + 180_000_000_000, "left")
        if a0 >= n:
            break
        seg = px[a0:a1]
        th = np.flatnonzero(seg * s < (L - TICK * s) * s + 1e-9)
        if not len(th):
            continue
        fi = a0 + int(th[0])
        t_tgt = min(ts[fi] + hold_ns + LAT_NS, days[i] + EOD_NS)
        xe = np.searchsorted(ts, t_tgt, "left")
        xe = min(xe, C["day_last_i"][i])
        if xe <= fi:
            continue
        fill = None; k = xe
        b0 = np.searchsorted(bts, ts[fi], "left")
        b1 = np.searchsorted(bts, ts[xe], "left")
        xb = b0 + np.flatnonzero(sdt[b0:b1] > XACCEL)
        x_cut = bts[xb[0]] if len(xb) else None
        stop_lvl = L - DIS * s
        seg2 = px[fi + 1:xe]
        if len(seg2):
            sh = np.flatnonzero(seg2 * s <= stop_lvl * s + 1e-9)
            if len(sh):
                k = fi + 1 + int(sh[0])
                rw = min(px[k], stop_lvl) if s > 0 else max(px[k], stop_lvl)
                fill = rw - 0.25 * s
        if x_cut is not None and (fill is None or ts[k] > x_cut):
            k = min(np.searchsorted(ts, x_cut, "left"), xe)
            fill = px[k] - TICK * s
        if fill is None:
            fill = px[xe] - TICK * s
            k = xe
        pnl = (fill - L) * s * PT - FEES
        recs.append((int(bts[i]), s, pnl, int(ts[k])))
        busy = ts[k]
    return recs


def attach_quotes(recs):
    """For each trade, book state at the signal moment (bar close)."""
    qfiles = {f.split("_")[-1][:8]: f
              for f in sorted(glob.glob(f"{QDIR}/Q_MNQU6_*.parquet"))}
    by_day = {}
    for r in recs:
        d = pd.to_datetime(r[0], utc=True).strftime("%Y%m%d")
        by_day.setdefault(d, []).append(r)
    out = []
    n_nofile = 0
    for d in sorted(by_day):
        f = qfiles.get(d)
        if f is None:
            n_nofile += len(by_day[d])
            continue
        t = pq.read_table(f)
        qts = t.column("ts").to_numpy()
        bid = t.column("bid").to_numpy()
        ask = t.column("ask").to_numpy()
        bs = t.column("bid_size").to_numpy().astype(np.float64)
        asz = t.column("ask_size").to_numpy().astype(np.float64)
        del t
        for sig_ts, s, pnl, exit_ts in by_day[d]:
            j = np.searchsorted(qts, sig_ts + LAT_NS, "right") - 1
            if j < W_SLOW:
                continue
            spread = float(ask[j] - bid[j])
            bfast = bs[j - W_FAST:j].sum()
            afast = asz[j - W_FAST:j].sum()
            bslow = bs[j - W_SLOW:j].sum()
            aslow = asz[j - W_SLOW:j].sum()
            imb_f = bfast / max(bfast + afast, 1.0)
            imb_s = bslow / max(bslow + aslow, 1.0)
            out.append(dict(sig_ts=sig_ts, s=s, pnl=pnl,
                            spread=spread, imb_f=imb_f, imb_s=imb_s))
        del qts, bid, ask, bs, asz
        print(f"  {d}: {len(by_day[d])} trades quoted", flush=True)
    if n_nofile:
        print(f"  ({n_nofile} trades on days with no quote file - "
              f"excluded)", flush=True)
    return out


def arm(name, rows, base=None):
    if not rows:
        print(f"  {name:<34} n=0"); return
    p = np.array([r["pnl"] for r in rows])
    wr = (p > 0).mean() * 100
    line = (f"  {name:<34} n={len(p):>3}  WR {wr:4.1f}%  "
            f"avg {p.mean():+7.2f}  tot {p.sum():+8.0f}")
    if base is not None:
        kept = p.sum()
        line += f"  (drops {base - kept:+.0f} vs base)"
    print(line, flush=True)
    return p.sum()


def main():
    t0 = time.time()
    K.build_tape()
    prep_clock(K.D[60], K.D["ts"])
    ts, px, C = K.D["ts"], K.D["px"], K.D[60]
    recs = sim_bp_trades(ts, px, C)
    lo = pd.Timestamp("2026-06-08", tz="UTC").value
    hi = pd.Timestamp("2026-07-09", tz="UTC").value
    recs = [r for r in recs if lo <= r[0] < hi]
    print(f"BP-Final trades in quote window Jun 8 - Jul 8: {len(recs)} "
          f"({time.time()-t0:.0f}s)", flush=True)
    K.D.clear()
    del ts, px, C
    rows = attach_quotes(recs)
    print(f"\ntrades with book state: {len(rows)} "
          f"({time.time()-t0:.0f}s)\n", flush=True)
    sp = np.array([r["spread"] for r in rows])
    print(f"spread at signal: 1-tick {np.mean(sp <= 0.25 + 1e-9)*100:.0f}% "
          f"| median {np.median(sp):.2f} | p90 "
          f"{np.percentile(sp, 90):.2f}", flush=True)
    print(f"\n{'ARM':<36} {'':>5} {'':>8} {'':>12}")
    base = arm("BASELINE (all quoted trades)", rows)
    arm("spread <= 1 tick at signal", [r for r in rows
        if r["spread"] <= 0.25 + 1e-9], base)
    arm("spread > 1 tick (what it drops)", [r for r in rows
        if r["spread"] > 0.25 + 1e-9])
    for tag, key in (("fast ~1.5s", "imb_f"), ("slow ~15s", "imb_s")):
        for th in (0.50, 0.55, 0.60):
            al = [r for r in rows
                  if (r[key] - 0.5) * r["s"] >= (th - 0.5)]
            ct = [r for r in rows
                  if (r[key] - 0.5) * r["s"] <= -(th - 0.5)]
            arm(f"imb {tag} ALIGNED >={th:.2f}", al, base)
            arm(f"imb {tag} CONTRA  <={1-th:.2f}", ct, base)
    arm("tight spread + fast aligned .55",
        [r for r in rows if r["spread"] <= 0.25 + 1e-9
         and (r["imb_f"] - 0.5) * r["s"] >= 0.05], base)
    with open("research/round64_quotes_rows.json", "w") as f:
        json.dump(rows, f)
    print(f"\nDONE ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
