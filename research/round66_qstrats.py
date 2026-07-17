"""Round 66: QUOTE-PRIMARY STRATEGY SIMS. The two latency-proof
signals from the round 65 decay map, turned into real strategies with
faithful tick fills, on the ticks+quotes overlap days:

  S1 IMB60-FADE: 60s book-size imbalance beyond a threshold ->
     fade the heavy side (round 65: -11pt drift against it by 5m,
     flat from 0 to 500ms latency).
  S2 THIN-MOMO: trailing-10s depth persistently thin (vs a CAUSAL
     trailing 30-min baseline - round 65 used day-median, fixed
     here) -> go WITH the 1s momentum direction (+8.2pt by 5m).

Grid: threshold x hold (2/5/15/30m) x entry style (market +1 tick /
passive 1pt-180s). Fees $1.50/RT. Disaster stop 60pt, EOD 20:55.
Truth checks per config: per-day P&L, top-3-event clip, overlap with
BP-Final signal minutes, latency arm at 200ms vs 65ms.
"""
import glob, json, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, "research")
from round65_qfactory import load_day, day_features, QDIR

LAT_NS_DEF = 65_000_000
FEES = 1.50
PT, TICK = 2.0, 0.25
DIS = 60.0
EOD_NS = (20 * 60 + 55) * 60_000_000_000
ENTRY_LO, ENTRY_HI = 14.0, 20.44


def tick_day(ts_all, px_all, day_ns):
    a = np.searchsorted(ts_all, day_ns, "left")
    b = np.searchsorted(ts_all, day_ns + 86_400_000_000_000, "left")
    return ts_all[a:b], px_all[a:b]


def events_for(F, grid, kind, th):
    hrs = (grid % 86_400_000_000_000) / 3600e9
    ok = (hrs >= ENTRY_LO) & (hrs < ENTRY_HI)
    if kind == "S1":
        m = ok & (np.abs(F["imb60"]) >= th)
        s = -np.sign(F["imb60"])                # fade the heavy side
    else:
        base = pd.Series(F["dep10"]).rolling(7200, min_periods=1200) \
            .median().to_numpy()                # trailing 30 min, causal
        m = ok & (F["dep10"] < th * base) & (F["mom1s"] != 0)
        s = np.sign(F["mom1s"])                 # go with the move
    idx = np.flatnonzero(m & (s != 0))
    return idx, s


def sim_day(tsd, pxd, grid, idx, s, hold_ns, lat_ns, passive, day_ns):
    out = []
    busy = 0
    n = len(tsd)
    if n < 100:
        return out
    for i in idx:
        t_sig = grid[i] + lat_ns
        if t_sig < busy:
            continue
        sd = int(s[i])
        if passive:
            j0 = np.searchsorted(tsd, t_sig, "left")
            if j0 >= n:
                break
            L = pxd[max(j0 - 1, 0)] - 1.0 * sd
            j1 = np.searchsorted(tsd, t_sig + 180_000_000_000, "left")
            seg = pxd[j0:j1]
            th_ = np.flatnonzero(seg * sd < (L - TICK * sd) * sd + 1e-9)
            if not len(th_):
                continue
            fi = j0 + int(th_[0])
            entry = L
        else:
            fi = np.searchsorted(tsd, t_sig, "left")
            if fi >= n:
                break
            entry = pxd[fi] + TICK * sd
        t_x = min(tsd[fi] + hold_ns, day_ns + EOD_NS)
        xe = np.searchsorted(tsd, t_x, "left")
        xe = min(xe, n - 1)
        if xe <= fi:
            continue
        fill = None; k = xe
        stop_lvl = entry - DIS * sd
        seg2 = pxd[fi + 1:xe]
        if len(seg2):
            sh = np.flatnonzero(seg2 * sd <= stop_lvl * sd + 1e-9)
            if len(sh):
                k = fi + 1 + int(sh[0])
                rw = min(pxd[k], stop_lvl) if sd > 0 \
                    else max(pxd[k], stop_lvl)
                fill = rw - TICK * sd
        if fill is None:
            fill = pxd[xe] - TICK * sd
            k = xe
        out.append((int(tsd[k]), (fill - entry) * sd * PT - FEES,
                    int(grid[i]), sd))
        busy = tsd[k]
    return out


def main():
    t0 = time.time()
    import round54_clock as K
    K.build_tape()
    ts_all, px_all = K.D["ts"], K.D["px"]
    # BP-Final signal minutes for overlap check
    from round58_frontier import prep_clock
    prep_clock(K.D[60], K.D["ts"])
    from round64_quotes import sim_bp_trades
    bp = sim_bp_trades(K.D["ts"], K.D["px"], K.D[60])
    bp_min = set(r[0] // 60_000_000_000 for r in bp)
    print(f"tape + BP reference ready ({time.time()-t0:.0f}s)", flush=True)
    # cache per-day features once
    days = []
    for f in sorted(glob.glob(f"{QDIR}/Q_MNQU6_*.parquet")):
        d = f.split("_")[-1][:8]
        if pd.Timestamp(d).dayofweek >= 5:
            continue
        day_ns = int(pd.Timestamp(d).value)
        tsd, pxd = tick_day(ts_all, px_all, day_ns)
        if len(tsd) < 100_000:
            print(f"  {d}: no ticks, skipped", flush=True)
            continue
        qts, bid, ask, bs, asz = load_day(f)
        if len(qts) < 1_000_000:
            continue
        grid, j, mid, F = day_features(qts, bid, ask, bs, asz)
        days.append((d, day_ns, grid,
                     {k: F[k] for k in ("imb60", "dep10", "mom1s")}))
        del qts, bid, ask, bs, asz, F
        print(f"  {d}: features cached ({time.time()-t0:.0f}s)",
              flush=True)
    print(f"\noverlap days: {len(days)}", flush=True)
    nwk = len(days) / 5.0
    results = {}
    GRID = [("S1", th, hold, pas)
            for th in (0.08, 0.10, 0.12, 0.15)
            for hold in (2, 5, 15, 30) for pas in (False, True)] + \
           [("S2", th, hold, pas)
            for th in (0.40, 0.50, 0.60)
            for hold in (2, 5, 15, 30) for pas in (False, True)]
    hdr = (f"{'config':<26} {'n':>4} {'/wk':>5} {'WR':>4} {'avg$':>7} "
           f"{'tot$':>7} {'$/wk':>6} {'clip3':>7} {'posD':>5} "
           f"{'ovlBP':>6} {'@200':>7}")
    print(hdr, flush=True)
    for kind, th, hold, pas in GRID:
        trades = []
        for d, day_ns, grid, F in days:
            idx, s = events_for(F, grid, kind, th)
            if not len(idx):
                continue
            trades += sim_day(*tick_day(ts_all, px_all, day_ns), grid,
                              idx, s, hold * 60_000_000_000,
                              LAT_NS_DEF, pas, day_ns)
        if len(trades) < 15:
            continue
        p = np.array([t[1] for t in trades])
        et = np.array([t[0] for t in trades])
        sig_min = set(t[2] // 60_000_000_000 for t in trades)
        ovl = np.mean([any((m + o) in bp_min for o in range(-3, 4))
                       for m in sig_min])
        dy = pd.Series(p, index=pd.to_datetime(et, utc=True)) \
            .resample("D").sum()
        dy = dy[dy != 0]
        clip = p.sum() - np.sort(p)[-3:].sum()
        # 200ms latency arm
        p2sum = 0.0; n2 = 0
        for d, day_ns, grid, F in days:
            idx, s = events_for(F, grid, kind, th)
            if not len(idx):
                continue
            tr2 = sim_day(*tick_day(ts_all, px_all, day_ns), grid, idx,
                          s, hold * 60_000_000_000, 200_000_000,
                          pas, day_ns)
            p2sum += sum(t[1] for t in tr2); n2 += len(tr2)
        nm = (f"{kind} th{th} h{hold} "
              f"{'pas' if pas else 'mkt'}")
        row = (f"{nm:<26} {len(p):>4} {len(p)/nwk:>5.1f} "
               f"{(p>0).mean()*100:>3.0f}% {p.mean():>+7.2f} "
               f"{p.sum():>+7.0f} {p.sum()/nwk:>+6.0f} "
               f"{clip:>+7.0f} {(dy>0).mean()*100:>4.0f}% "
               f"{ovl*100:>5.0f}% {p2sum/nwk if n2 else 0:>+7.0f}")
        print(row, flush=True)
        results[nm] = dict(n=len(p), usd_wk=round(p.sum()/nwk),
                           wr=round((p>0).mean()*100),
                           clip3=round(clip), posd=round((dy>0).mean()*100),
                           ovl=round(ovl*100),
                           usd_wk_200=round(p2sum/nwk) if n2 else 0,
                           daily={str(k.date()): round(v)
                                  for k, v in dy.items()})
    with open("research/round66_results.json", "w") as fo:
        json.dump(results, fo, indent=1)
    print(f"\nDONE ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
