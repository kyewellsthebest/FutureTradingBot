"""Round 51: SKEW ENGINEERING. User target shape: worst day ~-$500,
best days $2.5k+ — a standout profile, not an increment.

Never-tested class: ASYMMETRIC governors. Everything so far reduced
risk on both sides; these cap the red tail and AMPLIFY the green one:
  dfloor C      : day P&L <= -C -> no new entries (day loss bounded
                  near -C minus one open trade)
  glday (X,dl)  : day P&L >= +X -> ladder thresholds drop by dl
                  (press the hot hand; 3-lots come easier)
  glweek (X,dl) : same at week scale
  trail (A,T)   : at the 15-min timer, if unrealized >= A pts, do NOT
                  exit - trail by T pts to EOD (extend the right tail;
                  the fatal cap law only forbids cutting it)
  sniper (m,q)  : only fmag >= m signals, always q lots
Base cores: BP (fade 10/1.2, guard 8, dis 60, ladder 2/4, market,
hold 15) and HYBRID (BP + ride-on-trip). Faithful sessions. Every
config also run on 2023-24 history regime pools.
"""
import json, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, "research")
import round46_bulletproof_ga as R
import round47_frontier as F
from round48_drawdown import maxdd
import round50_delusional as M

ENTRY_LO, ENTRY_HI = 14.0, 20.73
EOD_NS = (20 * 60 + 55) * 60_000_000_000
CLOSE_NS = (21 * 60) * 60_000_000_000


def sim51(g, D):
    ts, px = D["ts"], D["px"]
    n = len(ts)
    c, atr, hrs = D["c"], D["atr"], D["hrs"]
    bts, days, nb = D["bts"], D["days"], D["nb"]
    pos_atr = np.where(np.nan_to_num(atr) > 0, atr, np.inf)
    ninf = np.nan_to_num(atr, nan=np.inf)
    ent = (hrs >= ENTRY_LO) & (hrs < ENTRY_HI)
    sdt = D["sdt"]
    mom = D["moms"][10]
    thr = 1.2 * ninf
    mag = np.abs(mom) / pos_atr
    raw = np.where(mom < -thr, 1, np.where(mom > thr, -1, 0))
    sig = np.where(ent, raw, 0)
    sig = np.where(np.abs(sdt) > 8.0, 0, sig)
    sniper = g.get("sniper")
    if sniper is not None:
        sig = np.where(mag >= sniper[0], sig, 0)
    hyb = D["hybfirst"][8.0] if g.get("hybrid") else None
    idxs = np.flatnonzero(sig)
    if hyb is not None:
        idxs = np.union1d(idxs, np.flatnonzero(hyb & ent))
    dfloor = g.get("dfloor")
    glday = g.get("glday")
    glweek = g.get("glweek")
    trail = g.get("trail")
    wb = g.get("wb")
    l1_0, l2_0 = 2.0, 4.0
    out_t = []; out_p = []
    busy = 0
    cur_day = -1; day_pnl = 0.0
    cur_wk = -1; wk_pnl = 0.0
    last_special_day = -1
    for i in idxs:
        if bts[i] < busy:
            continue
        if days[i] != cur_day:
            cur_day = days[i]; day_pnl = 0.0
        wk_id = days[i] // 604_800_000_000_000
        if wk_id != cur_wk:
            cur_wk = wk_id; wk_pnl = 0.0
        if dfloor is not None and day_pnl <= -dfloor:
            continue
        is_hyb = hyb is not None and hyb[i] and sig[i] == 0
        if is_hyb and days[i] == last_special_day:
            continue
        s = int(np.sign(sdt[i])) if is_hyb else int(sig[i])
        if s == 0:
            continue
        l1, l2 = l1_0, l2_0
        if glday is not None and day_pnl >= glday[0]:
            l1 -= glday[1]; l2 -= 2 * glday[1]
        if glweek is not None and wk_pnl >= glweek[0]:
            l1 -= glweek[1]; l2 -= 2 * glweek[1]
        if sniper is not None:
            q = sniper[1]
        elif is_hyb:
            q = 1
        else:
            q = 3 if mag[i] >= l2 else (2 if mag[i] >= l1 else 1)
        if wb is not None and wk_pnl <= -wb:
            q = 1
        fi = np.searchsorted(ts, bts[i] + R.LAT_NS, "left")
        if fi >= n: break
        entry = px[fi] + R.TICK * s
        hold_eff = 600 if is_hyb else 15
        dis_eff = 100.0 if is_hyb else 60.0
        t_target = min(ts[fi] + R.HN(hold_eff) + R.LAT_NS, days[i] + EOD_NS)
        xe = np.searchsorted(ts, t_target, "left")
        day_last = np.searchsorted(ts, days[i] + CLOSE_NS, "left") - 1
        xe = min(xe, day_last)
        if xe <= fi:
            continue
        fill, k_exit, fired = M.walk_exit(D, fi, xe, entry, s, dis_eff)
        if fill is None:
            fill = px[xe] - R.TICK * s
            k_exit = xe
            if (trail is not None and not is_hyb
                    and (fill - entry) * s >= trail[0]):
                seg = px[xe:day_last]
                if len(seg) > 1:
                    fav = seg * s
                    peak = np.maximum.accumulate(fav)
                    hit = np.flatnonzero(fav <= peak - trail[1])
                    if len(hit):
                        k_exit = xe + int(hit[0])
                        fill = px[k_exit] - R.STOP_SLIP * s
                    else:
                        k_exit = xe + len(seg) - 1
                        fill = px[k_exit] - R.TICK * s
        pnl = ((fill - entry) * s * R.PT - R.FEES) * q
        out_t.append(ts[k_exit]); out_p.append(pnl)
        day_pnl += pnl; wk_pnl += pnl
        busy = ts[k_exit]
        if is_hyb:
            last_special_day = days[i]
    s_ = pd.Series(out_p,
                   index=pd.to_datetime(np.array(out_t, dtype="int64"),
                                        utc=True))
    return s_[s_.index.dayofweek < 5]


def metrics(g):
    s26 = sim51(g, R.D26)
    if len(s26) < 60:
        return None
    dy = s26.resample("D").sum(); dy = dy[dy != 0]
    wk = R.wk_of(s26)
    sH = sim51(g, R.DH)
    sH = sH[sH.index < pd.Timestamp("2025-01-01", tz="UTC")]
    return dict(usd_wk=round(float(s26.sum() / max(len(wk), 1))),
                pos=round(float((wk > 0).mean() * 100)),
                wd=round(float(dy.min())), bd=round(float(dy.max())),
                ww=round(float(wk.min())), mdd=round(float(maxdd(dy))),
                trwk=round(len(s26) / max(len(wk), 1), 1),
                sH=round(R.pool_usd_wk(sH, M.STRONG_2324)),
                wH=round(R.pool_usd_wk(sH, M.WEAK_2324)))


def show(nm, m):
    if m is None:
        print(f"{nm:<30} (too few trades)", flush=True); return
    print(f"{nm:<30} {m['usd_wk']:>5} {m['pos']:>4} {m['wd']:>6} "
          f"{m['bd']:>5} {m['ww']:>6} {m['mdd']:>6} {m['trwk']:>6} "
          f"{m['sH']:>5} {m['wH']:>6}", flush=True)


def main():
    t0 = time.time()
    M.init_all()
    print(f"{'variant':<30} {'$/wk':>5} {'pos':>4} {'wd':>6} {'bd':>5} "
          f"{'ww':>6} {'MDD':>6} {'tr/wk':>6} {'sH':>5} {'wH':>6}")
    results = {}
    tests = [
        ("BP (bench)",                {}),
        ("BP+wb700 (bench)",          {"wb": 700.0}),
        ("HYBRID+wb (bench)",         {"hybrid": True, "wb": 700.0}),
        # --- day floor alone (worst-day bounding) ---
        ("dfloor 400",                {"dfloor": 400.0}),
        ("dfloor 500",                {"dfloor": 500.0}),
        ("dfloor 600",                {"dfloor": 600.0}),
        # --- hot-hand escalation alone ---
        ("glday +300",                {"glday": (300.0, 0.5)}),
        ("glday +500",                {"glday": (500.0, 0.5)}),
        ("glweek +500",               {"glweek": (500.0, 0.5)}),
        # --- winner trailing alone ---
        ("trail 15/10",               {"trail": (15.0, 10.0)}),
        ("trail 25/15",               {"trail": (25.0, 15.0)}),
        # --- sniper ---
        ("sniper m2.5 q3",            {"sniper": (2.5, 3)}),
        ("sniper m3.0 q3",            {"sniper": (3.0, 3)}),
        # --- THE SHAPE: floor + escalation (+trail) ---
        ("dfloor500 + glday300",      {"dfloor": 500.0, "glday": (300.0, 0.5)}),
        ("dfloor500 + glday500",      {"dfloor": 500.0, "glday": (500.0, 0.5)}),
        ("dfloor400 + glday300",      {"dfloor": 400.0, "glday": (300.0, 0.5)}),
        ("dfloor500+glday300+trail",  {"dfloor": 500.0, "glday": (300.0, 0.5),
                                       "trail": (15.0, 10.0)}),
        ("dfloor500+glday300+wb700",  {"dfloor": 500.0, "glday": (300.0, 0.5),
                                       "wb": 700.0}),
        ("dfloor500+glday+glweek",    {"dfloor": 500.0, "glday": (300.0, 0.5),
                                       "glweek": (500.0, 0.5)}),
        ("HYB+dfloor500+glday300",    {"hybrid": True, "dfloor": 500.0,
                                       "glday": (300.0, 0.5)}),
        ("HYB+dfloor500+glday+wb",    {"hybrid": True, "dfloor": 500.0,
                                       "glday": (300.0, 0.5), "wb": 700.0}),
    ]
    for nm, g in tests:
        m = metrics(g)
        if m is not None:
            results[nm] = {"cfg": g, "m": m}
        show(nm, m)
    with open("research/round51_results.json", "w") as f:
        json.dump(results, f, default=str, indent=1)
    print(f"\nDONE ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
