"""Round 48: DRAWDOWN HUNT. New objective per user: minimize the
worst-case starting hole (max drawdown) and maximize consistency;
income is a floor, not the target.

Hidden avenue class never touched in 47 rounds: SEQUENCING GOVERNORS.
Drawdowns cluster across days; every prior overlay conditioned on
market state, none on OUR OWN equity sequence. All governors only
reduce size below the user-approved base and restore to it (never
above) - manual-sizing rule intact.

Overlays on the locked FADESZ-BP core (MOMR 10/1.2, trend-day guard
8xATR, ladder 2/4, market entry, hold 15 + exit-accel 10, dis 60,
entries til 20:44 UTC, flat by 20:55 - faithful session rules):
  daystop C   : no new entries once day P&L <= -C
  daycap C    : day P&L <= -C -> cap 1 for rest of day (soft brake)
  nextday C   : day closed <= -C -> next day cap 1 (loss-day governor)
  eqgov A,B   : drawdown from equity high > A -> cap 2, > B -> cap 1,
                restore at new high (equity-curve governor)
  volsize q   : ATR above the q-quantile of RTH ATR -> cap 1
                (price-based, verifiable on history)
  weekbrake C : week P&L <= -C -> cap 1 until next week
  qgate       : once day < -200, only fmag>=3 signals may trade
Stage 1: each alone on a grid. Stage 2: combos of the best.
Metrics: $/wk, pos-week%, worst day/week, MAXDD (worst-start hole),
tr/wk on 2026 + strong/weak 2023-24 regime pools.
"""
import json, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, "research")
import round46_bulletproof_ga as R
import round47_frontier as F

EOD_ENTRY = 20.73
EOD_NS = (20 * 60 + 55) * 60_000_000_000
CLOSE_NS = (21 * 60) * 60_000_000_000


def sim48(cfg, D):
    ts, px = D["ts"], D["px"]
    n = len(ts)
    c, atr, hrs = D["c"], D["atr"], D["hrs"]
    bts, days = D["bts"], D["days"]
    ninf = np.nan_to_num(atr, nan=np.inf)
    pos_atr = np.where(np.nan_to_num(atr) > 0, atr, np.inf)
    mom = D["moms"][10]
    thr = 1.2 * ninf
    mag = np.abs(mom) / pos_atr
    raw = np.where(mom < -thr, 1, np.where(mom > thr, -1, 0))
    sig = np.where((hrs >= 14.0) & (hrs < EOD_ENTRY), raw, 0)
    sig = np.where(np.abs(D["sdt"]) > 8.0, 0, sig)
    sdt = D["sdt"]
    atr_hi = None
    if cfg.get("volsize"):
        rthm = (hrs >= 14.0) & (hrs < 20.9)
        atr_hi = np.nan_to_num(atr) > np.nanquantile(atr[rthm], cfg["volsize"])
    daystop = cfg.get("daystop")
    daycap = cfg.get("daycap")
    nextday = cfg.get("nextday")
    eqgov = cfg.get("eqgov")
    weekbrake = cfg.get("weekbrake")
    qgate = cfg.get("qgate", False)
    sidx = np.flatnonzero(sig)
    out_t = []; out_p = []
    busy = 0
    cur_day = -1; day_pnl = 0.0; prev_day_pnl = 0.0
    cur_wk = -1; wk_pnl = 0.0
    equity = 0.0; eq_hi = 0.0
    for i in sidx:
        if bts[i] < busy:
            continue
        s = sig[i]
        if days[i] != cur_day:
            prev_day_pnl = day_pnl if cur_day != -1 else 0.0
            cur_day = days[i]; day_pnl = 0.0
        wk_id = (days[i] // 604_800_000_000_000)
        if wk_id != cur_wk:
            cur_wk = wk_id; wk_pnl = 0.0
        if daystop is not None and day_pnl <= -daystop:
            continue
        if qgate and day_pnl < -200 and mag[i] < 3.0:
            continue
        q = 3 if mag[i] >= 4.0 else (2 if mag[i] >= 2.0 else 1)
        if daycap is not None and day_pnl <= -daycap:
            q = 1
        if nextday is not None and prev_day_pnl <= -nextday:
            q = 1
        if eqgov is not None:
            dd = eq_hi - equity
            if dd > eqgov[1]:
                q = 1
            elif dd > eqgov[0]:
                q = min(q, 2)
        if weekbrake is not None and wk_pnl <= -weekbrake:
            q = 1
        if atr_hi is not None and atr_hi[i]:
            q = 1
        fi = np.searchsorted(ts, bts[i] + R.LAT_NS, "left")
        if fi >= n: break
        entry = px[fi] + R.TICK * s
        t_target = min(ts[fi] + R.HN(15) + R.LAT_NS, days[i] + EOD_NS)
        xe = np.searchsorted(ts, t_target, "left")
        day_last = np.searchsorted(ts, days[i] + CLOSE_NS, "left") - 1
        xe = min(xe, day_last)
        if xe <= fi:
            xe = min(fi + 1, day_last)
            if xe <= fi: continue
        # exit-accel 10: bail if trend guard trips mid-hold
        b0 = np.searchsorted(bts, ts[fi], "left")
        for j in range(b0 + 3, min(b0 + 15, D["nb"])):
            if abs(sdt[j]) > 10.0:
                xe2 = np.searchsorted(ts, bts[j] + R.LAT_NS, "left")
                if fi < xe2 < xe:
                    xe = xe2
                break
        fill = None; k_exit = xe
        stop_lvl = entry - 60.0 * s
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
        pnl = ((fill - entry) * s * R.PT - R.FEES) * q
        out_t.append(ts[k_exit]); out_p.append(pnl)
        day_pnl += pnl; wk_pnl += pnl
        equity += pnl; eq_hi = max(eq_hi, equity)
        busy = ts[k_exit]
    s_ = pd.Series(out_p,
                   index=pd.to_datetime(np.array(out_t, dtype="int64"),
                                        utc=True))
    return s_[s_.index.dayofweek < 5]


def maxdd(dy):
    vals = dy.to_numpy()
    worst = 0.0
    run = 0.0
    for v in vals:               # worst contiguous-run sum (fresh-start hole)
        run = min(v, run + v)
        worst = min(worst, run)
    return worst


def metrics(cfg):
    s26 = sim48(cfg, R.D26)
    if len(s26) < 200:
        return None
    dy = s26.resample("D").sum(); dy = dy[dy != 0]
    wk = R.wk_of(s26)
    sH = sim48(cfg, R.DH)
    sH = sH[sH.index < pd.Timestamp("2025-01-01", tz="UTC")]
    return dict(usd_wk=round(float(s26.sum() / max(len(wk), 1))),
                pos=round(float((wk > 0).mean() * 100)),
                wd=round(float(dy.min())), ww=round(float(wk.min())),
                mdd=round(float(maxdd(dy))),
                trwk=round(len(s26) / max(len(wk), 1), 1),
                sH=round(R.pool_usd_wk(sH, R.STRONG_2324)),
                wH=round(R.pool_usd_wk(sH, R.WEAK_2324)))


def show(nm, m):
    if m is None:
        print(f"{nm:<28} (too few trades)", flush=True); return
    print(f"{nm:<28} {m['usd_wk']:>5} {m['pos']:>4} {m['ww']:>6} "
          f"{m['wd']:>6} {m['mdd']:>6} {m['trwk']:>6} {m['sH']:>5} "
          f"{m['wH']:>6}", flush=True)


def main():
    t0 = time.time()
    R.init_globals()
    F.prep(R.D26); F.prep(R.DH)
    print(f"{'variant':<28} {'$/wk':>5} {'pos':>4} {'ww':>6} {'wd':>6} "
          f"{'MAXDD':>6} {'tr/wk':>6} {'sH':>5} {'wH':>6}")
    results = {}
    stage1 = [
        ("BP full (baseline)",       {}),
        ("BP cap-1 (baseline)",      {"eqgov": (0.0, 0.0)}),  # dd>0 -> cap1
        ("daystop 300",              {"daystop": 300.0}),
        ("daystop 450",              {"daystop": 450.0}),
        ("daystop 600",              {"daystop": 600.0}),
        ("daycap 250",               {"daycap": 250.0}),
        ("daycap 400",               {"daycap": 400.0}),
        ("nextday 300",              {"nextday": 300.0}),
        ("nextday 600",              {"nextday": 600.0}),
        ("eqgov 800/1600",           {"eqgov": (800.0, 1600.0)}),
        ("eqgov 600/1200",           {"eqgov": (600.0, 1200.0)}),
        ("eqgov 1000/2000",          {"eqgov": (1000.0, 2000.0)}),
        ("volsize q75",              {"volsize": 0.75}),
        ("volsize q90",              {"volsize": 0.90}),
        ("weekbrake 700",            {"weekbrake": 700.0}),
        ("weekbrake 1000",           {"weekbrake": 1000.0}),
        ("qgate",                    {"qgate": True}),
    ]
    for nm, cfg in stage1:
        m = metrics(cfg)
        results[nm] = {"cfg": cfg, "m": m}
        show(nm, m)
    print("\n--- stage 2: combos ---", flush=True)
    stage2 = [
        ("daycap400 + eqgov8/16",    {"daycap": 400.0, "eqgov": (800.0, 1600.0)}),
        ("daycap400 + nextday600",   {"daycap": 400.0, "nextday": 600.0}),
        ("daycap250 + eqgov6/12",    {"daycap": 250.0, "eqgov": (600.0, 1200.0)}),
        ("daystop450 + eqgov8/16",   {"daystop": 450.0, "eqgov": (800.0, 1600.0)}),
        ("daycap400+eqgov+volq90",   {"daycap": 400.0, "eqgov": (800.0, 1600.0),
                                      "volsize": 0.90}),
        ("daycap400+eqgov+wb700",    {"daycap": 400.0, "eqgov": (800.0, 1600.0),
                                      "weekbrake": 700.0}),
        ("full stack",               {"daycap": 400.0, "eqgov": (800.0, 1600.0),
                                      "nextday": 600.0, "volsize": 0.90,
                                      "weekbrake": 700.0}),
    ]
    for nm, cfg in stage2:
        m = metrics(cfg)
        results[nm] = {"cfg": cfg, "m": m}
        show(nm, m)
    with open("research/round48_results.json", "w") as f:
        json.dump(results, f, indent=1)
    print(f"\nDONE ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
