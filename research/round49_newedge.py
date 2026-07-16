"""Round 49: NEW-EDGE HUNT. User mandate: a COMPLETELY DIFFERENT
strategy (not the fade + filters), judged drawdown-first.

Five structurally different mechanism families on the 2026 tape,
faithful session rules (entries 14:00-20:44 UTC, flat by 20:55,
market entries, 65ms latency, 1 adverse tick each side, $1.50/RT):

  RIDE  trend-day ride: first time |price - day open| crosses D x ATR
        (before cutoff hour), enter WITH the move, hold to EOD flatten
        (optional disaster stop). The anti-FADESZ - wins Jul-15 days.
  FLOWF order-flow follow: signed volume over W minutes exceeds
        M x avg -> enter WITH the flow, hold H minutes.
  DONCH Donchian breakout: close breaks the L-bar high/low -> enter
        with the break, hold H minutes or EOD.
  ORB   opening-range breakout: first 30 min after 14:00 sets the
        range; trade the break, exit EOD or on R-point stop.
  GAP   overnight gap: 14:00 open vs prior 20:54 close; fade or
        follow gaps > G x ATR, exit after H minutes or EOD.

Scoreboard (drawdown-first): MAXDD (worst fresh-start hole), pos-week
%, worst day/week, then $/wk. Discipline: JanFeb / MarApr / May /
JunJul folds shown; families are small grids so multiplicity is low.
Results -> research/round49_results.json
"""
import json, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, "research")
import round46_bulletproof_ga as R
import round47_frontier as F
from round48_drawdown import maxdd

ENTRY_LO, ENTRY_HI = 14.0, 20.73
EOD_NS = (20 * 60 + 55) * 60_000_000_000
CLOSE_NS = (21 * 60) * 60_000_000_000


def prep49(D):
    c, hrs, atr, idx = D["c"], D["hrs"], D["atr"], D["idx"]
    day = idx.normalize()
    # prior-session close (last c of previous calendar day) per bar
    dfc = pd.Series(c, index=idx)
    last_by_day = dfc.groupby(day).last()
    prev_close = last_by_day.shift(1)
    D["prevc"] = prev_close.reindex(day).to_numpy()
    # rolling Donchian extremes (exclusive of current bar)
    hh = pd.Series(D_h(D), index=idx)
    ll = pd.Series(D_l(D), index=idx)
    D["don"] = {L: (hh.rolling(L).max().shift(1).to_numpy(),
                    ll.rolling(L).min().shift(1).to_numpy())
                for L in (30, 60, 120)}
    # opening range (first 30 min >= 14:00) per day
    inor = (hrs >= 14.0) & (hrs < 14.5)
    orh = pd.Series(np.where(inor, D_h(D), np.nan), index=idx) \
        .groupby(day).transform("max").to_numpy()
    orl = pd.Series(np.where(inor, D_l(D), np.nan), index=idx) \
        .groupby(day).transform("min").to_numpy()
    D["orh"], D["orl"] = orh, orl


def D_h(D):
    if "h_" not in D:
        b = F and None
    return D.get("h", D["c"])  # fallback


def sim49(kind, p, D):
    ts, px = D["ts"], D["px"]
    n = len(ts)
    c, atr, hrs = D["c"], D["atr"], D["hrs"]
    bts, days, nb = D["bts"], D["days"], D["nb"]
    pos_atr = np.where(np.nan_to_num(atr) > 0, atr, np.inf)
    ent = (hrs >= ENTRY_LO) & (hrs < ENTRY_HI)
    sdt = D["sdt"]
    if kind == "RIDE":
        Dx, cutoff, dis = p
        sig = np.where(ent & (hrs < cutoff) & (sdt > Dx), 1,
                       np.where(ent & (hrs < cutoff) & (sdt < -Dx), -1, 0))
        hold = 600            # to EOD (clamped by flatten)
        one_per_day = True
    elif kind == "FLOWF":
        W, M, hold = p
        fl = D["flows"][W]
        thr = M * np.nan_to_num(D["ias"], nan=np.inf)
        sig = np.where(ent & (fl > thr), 1,
                       np.where(ent & (fl < -thr), -1, 0))
        dis = 60.0; one_per_day = False
    elif kind == "DONCH":
        L, hold, dis = p
        hh, ll = D["don"][L]
        sig = np.where(ent & (c > np.nan_to_num(hh, nan=np.inf)), 1,
                       np.where(ent & (c < np.nan_to_num(ll, nan=-np.inf)),
                                -1, 0))
        one_per_day = False
    elif kind == "ORB":
        Rstop, = p
        after = hrs >= 14.5
        sig = np.where(ent & after & (c > np.nan_to_num(D["orh"], nan=np.inf)), 1,
                       np.where(ent & after & (c < np.nan_to_num(D["orl"], nan=-np.inf)),
                                -1, 0))
        hold = 600; dis = Rstop; one_per_day = True
    else:  # GAP
        G, follow, hold = p
        gap = (D["o"] - D["prevc"]) / pos_atr
        first = (hrs >= 14.0) & (hrs < 14.05)
        s0 = np.where(first & (gap > G), 1, np.where(first & (gap < -G), -1, 0))
        sig = s0 if follow else -s0
        dis = 100.0; one_per_day = True
    sidx = np.flatnonzero(sig)
    out_t = []; out_p = []
    busy = 0; last_day_traded = -1
    for i in sidx:
        if bts[i] < busy:
            continue
        if one_per_day and days[i] == last_day_traded:
            continue
        s = sig[i]
        fi = np.searchsorted(ts, bts[i] + R.LAT_NS, "left")
        if fi >= n: break
        entry = px[fi] + R.TICK * s
        t_target = min(ts[fi] + R.HN(hold) + R.LAT_NS, days[i] + EOD_NS)
        xe = np.searchsorted(ts, t_target, "left")
        day_last = np.searchsorted(ts, days[i] + CLOSE_NS, "left") - 1
        xe = min(xe, day_last)
        if xe <= fi:
            continue
        fill = None; k_exit = xe
        if dis is not None:
            stop_lvl = entry - dis * s
            seg2 = px[fi + 1:xe]
            if len(seg2):
                sh = np.flatnonzero(seg2 * s <= stop_lvl * s + 1e-9)
                if len(sh):
                    k_exit = fi + 1 + int(sh[0])
                    raw_ = min(px[k_exit], stop_lvl) if s > 0 \
                        else max(px[k_exit], stop_lvl)
                    fill = raw_ - R.STOP_SLIP * s
        if fill is None:
            fill = px[xe] - R.TICK * s
            k_exit = xe
        out_p.append((fill - entry) * s * R.PT - R.FEES)
        out_t.append(ts[k_exit])
        busy = ts[k_exit]
        last_day_traded = days[i]
    s_ = pd.Series(out_p,
                   index=pd.to_datetime(np.array(out_t, dtype="int64"),
                                        utc=True))
    return s_[s_.index.dayofweek < 5]


def metrics(s26):
    if len(s26) < 60:
        return None
    dy = s26.resample("D").sum(); dy = dy[dy != 0]
    wk = R.wk_of(s26)
    folds = []
    for lo, hi in R.F26:
        f = s26[(s26.index >= pd.Timestamp(lo, tz="UTC"))
                & (s26.index < pd.Timestamp(hi, tz="UTC"))]
        w = R.wk_of(f)
        folds.append(round(float(f.sum() / max(len(w), 1))) if len(f) else 0)
    return dict(usd_wk=round(float(s26.sum() / max(len(wk), 1))),
                pos=round(float((wk > 0).mean() * 100)),
                wd=round(float(dy.min())), ww=round(float(wk.min())),
                mdd=round(float(maxdd(dy))),
                trwk=round(len(s26) / max(len(wk), 1), 1),
                folds=folds)


def show(nm, m):
    if m is None:
        print(f"{nm:<26} (too few trades)", flush=True); return
    print(f"{nm:<26} {m['usd_wk']:>5} {m['pos']:>4} {m['ww']:>6} "
          f"{m['wd']:>6} {m['mdd']:>6} {m['trwk']:>6}  {m['folds']}",
          flush=True)


def main():
    t0 = time.time()
    R.init_globals()
    F.prep(R.D26)
    D = R.D26
    # bar highs/lows for prep49 (rebuild once; build() kept only o/c)
    b = R.bars_of(D["ts"], D["px"])
    D["h"], D["l"] = b["h"], b["l"]
    globals()["D_h"] = lambda D_: D_["h"]
    globals()["D_l"] = lambda D_: D_["l"]
    prep49(D)
    print(f"prep done ({time.time()-t0:.0f}s)", flush=True)
    print(f"{'variant':<26} {'$/wk':>5} {'pos':>4} {'ww':>6} {'wd':>6} "
          f"{'MAXDD':>6} {'tr/wk':>6}  folds[JF,MA,My,JJ]")
    results = {}
    tests = []
    for Dx in (3.0, 4.0, 5.0, 6.0):
        for cutoff in (18.0, 19.5):
            for dis in (None, 100.0):
                tests.append((f"RIDE d{Dx} c{cutoff}"
                              f"{' s100' if dis else ''}",
                              ("RIDE", (Dx, cutoff, dis))))
    for W in (5, 10, 20):
        for M in (2.0, 3.0, 4.0):
            for hold in (5, 15, 30):
                tests.append((f"FLOWF w{W} m{M} h{hold}",
                              ("FLOWF", (W, M, hold))))
    for L in (30, 60, 120):
        for hold in (30, 60):
            for dis in (60.0, None):
                tests.append((f"DONCH L{L} h{hold}"
                              f"{' s60' if dis else ''}",
                              ("DONCH", (L, hold, dis))))
    for Rstop in (40.0, 60.0):
        tests.append((f"ORB s{int(Rstop)}", ("ORB", (Rstop,))))
    for G in (0.8, 1.5):
        for follow in (True, False):
            for hold in (60, 240):
                tests.append((f"GAP g{G} {'fol' if follow else 'fade'} h{hold}",
                              ("GAP", (G, follow, hold))))
    for nm, (kind, p) in tests:
        m = metrics(sim49(kind, p, D))
        if m is not None:
            results[nm] = m
        show(nm, m)
    with open("research/round49_results.json", "w") as f:
        json.dump(results, f, indent=1)
    good = {k: v for k, v in results.items()
            if v["usd_wk"] > 150 and v["mdd"] > -1500}
    print(f"\ncandidates ($/wk>150, MAXDD>-1500): {len(good)}")
    for k, v in sorted(good.items(), key=lambda kv: kv[1]["mdd"],
                       reverse=True):
        show(k, v)
    print(f"\nDONE ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
