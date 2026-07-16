"""Round 52: THE BREAKTHROUGH PUSH. User target: average day up
($200+/day), worst day and max hole held. Levers never pulled:
  1. Ride leg upsized (1 -> 2-3 lots) with a tick-walked trail that
     doubles as a tight stop (initial risk $60-80/lot).
  2. Ride re-entries (up to 2/day) - trend days re-accelerate.
  3. Fade ADD-ON: price extends X pts past a fade fill -> add 1 lot
     into the deeper overshoot (deepest extensions revert hardest -
     the fmag ladder already proves the dose-response).
  4. Magnitude-scaled hold: fmag >= 2.5 signals get 25 min.
All on the HYBRID core (fade 10/1.2 guard 8 dis 60 ladder 2/4 market
+ ride on trip) + week brake. Faithful sessions, history-checked.
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


def sim52(g, D):
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
    fsig = np.where(ent, raw, 0)
    fsig = np.where(np.abs(sdt) > 8.0, 0, fsig)
    ride_on = (np.abs(sdt) > 8.0) & ent & (hrs < 19.5)
    idxs = np.flatnonzero(fsig | ride_on)
    rq = g.get("ride_q", 1)
    rtrail = g.get("ride_trail")
    rdis = g.get("ride_dis", 100.0)
    rre = g.get("ride_re", 1)
    addon = g.get("addon")
    hold2 = g.get("hold2")
    glday = g.get("glday")
    wb = g.get("wb")
    out_t = []; out_p = []
    busy = 0
    cur_day = -1; day_pnl = 0.0
    cur_wk = -1; wk_pnl = 0.0
    rides_today = 0
    for i in idxs:
        if bts[i] < busy:
            continue
        if days[i] != cur_day:
            cur_day = days[i]; day_pnl = 0.0; rides_today = 0
        wk_id = days[i] // 604_800_000_000_000
        if wk_id != cur_wk:
            cur_wk = wk_id; wk_pnl = 0.0
        is_ride = ride_on[i] and fsig[i] == 0
        if is_ride and rides_today >= rre:
            continue
        s = int(np.sign(sdt[i])) if is_ride else int(fsig[i])
        if s == 0:
            continue
        l1, l2 = 2.0, 4.0
        if glday is not None and day_pnl >= glday[0]:
            l1 -= glday[1]; l2 -= 2 * glday[1]
        q = rq if is_ride else \
            (3 if mag[i] >= l2 else (2 if mag[i] >= l1 else 1))
        if wb is not None and wk_pnl <= -wb:
            q = 1
        fi = np.searchsorted(ts, bts[i] + R.LAT_NS, "left")
        if fi >= n: break
        entry = px[fi] + R.TICK * s
        day_last = np.searchsorted(ts, days[i] + CLOSE_NS, "left") - 1
        pnl = 0.0
        if is_ride:
            rides_today += 1
            end = np.searchsorted(ts, days[i] + EOD_NS, "left")
            end = min(end, day_last)
            if end <= fi:
                continue
            seg = px[fi + 1:end]
            k_exit = end
            fill = px[end] - R.TICK * s
            if rtrail is not None and len(seg):
                fav = (seg - entry) * s
                peak = np.maximum.accumulate(np.maximum(fav, 0.0))
                hit = np.flatnonzero(fav <= peak - rtrail)
                if len(hit):
                    k_exit = fi + 1 + int(hit[0])
                    fill = px[k_exit] - R.STOP_SLIP * s
            elif len(seg):
                stop_lvl = entry - rdis * s
                sh = np.flatnonzero(seg * s <= stop_lvl * s + 1e-9)
                if len(sh):
                    k_exit = fi + 1 + int(sh[0])
                    raw_ = min(px[k_exit], stop_lvl) if s > 0 \
                        else max(px[k_exit], stop_lvl)
                    fill = raw_ - R.STOP_SLIP * s
            pnl = ((fill - entry) * s * R.PT - R.FEES) * q
        else:
            hold_eff = 15
            if hold2 is not None and mag[i] >= hold2[0]:
                hold_eff = hold2[1]
            t_target = min(ts[fi] + R.HN(hold_eff) + R.LAT_NS,
                           days[i] + EOD_NS)
            xe = np.searchsorted(ts, t_target, "left")
            xe = min(xe, day_last)
            if xe <= fi:
                continue
            fill, k_exit, fired = M.walk_exit(D, fi, xe, entry, s, 60.0)
            if fill is None:
                fill = px[xe] - R.TICK * s
                k_exit = xe
            pnl = ((fill - entry) * s * R.PT - R.FEES) * q
            if addon is not None and q < 3:
                seg = px[fi + 1:k_exit]
                lvl = entry - addon * s
                hh = np.flatnonzero(seg * s <= lvl * s + 1e-9) \
                    if len(seg) else []
                if len(hh):
                    ai = fi + 1 + int(hh[0])
                    a_entry = px[ai] + R.TICK * s
                    pnl += (fill - a_entry) * s * R.PT - R.FEES
        out_t.append(ts[k_exit]); out_p.append(pnl)
        day_pnl += pnl; wk_pnl += pnl
        busy = ts[k_exit]
    s_ = pd.Series(out_p,
                   index=pd.to_datetime(np.array(out_t, dtype="int64"),
                                        utc=True))
    return s_[s_.index.dayofweek < 5]


def metrics(g):
    s26 = sim52(g, R.D26)
    if len(s26) < 60:
        return None
    dy = s26.resample("D").sum(); dy = dy[dy != 0]
    wk = R.wk_of(s26)
    sH = sim52(g, R.DH)
    sH = sH[sH.index < pd.Timestamp("2025-01-01", tz="UTC")]
    return dict(usd_wk=round(float(s26.sum() / max(len(wk), 1))),
                avg_day=round(float(dy.mean())),
                pos=round(float((wk > 0).mean() * 100)),
                wd=round(float(dy.min())), bd=round(float(dy.max())),
                mdd=round(float(maxdd(dy))),
                trwk=round(len(s26) / max(len(wk), 1), 1),
                sH=round(R.pool_usd_wk(sH, M.STRONG_2324)),
                wH=round(R.pool_usd_wk(sH, M.WEAK_2324)))


def show(nm, m):
    if m is None:
        print(f"{nm:<32} (too few trades)", flush=True); return
    print(f"{nm:<32} {m['usd_wk']:>5} {m['avg_day']:>4} {m['pos']:>4} "
          f"{m['wd']:>6} {m['bd']:>5} {m['mdd']:>6} {m['trwk']:>6} "
          f"{m['sH']:>5} {m['wH']:>6}", flush=True)


def main():
    t0 = time.time()
    M.init_all()
    print(f"{'variant':<32} {'$/wk':>5} {'$/d':>4} {'pos':>4} {'wd':>6} "
          f"{'bd':>5} {'MDD':>6} {'tr/wk':>6} {'sH':>5} {'wH':>6}")
    results = {}
    base = {"wb": 700.0}
    tests = [
        ("HYB+wb bench (ride 1x EOD)",   {**base}),
        # --- ride sizing ---
        ("ride 2x",                      {**base, "ride_q": 2}),
        ("ride 3x",                      {**base, "ride_q": 3}),
        # --- ride trail ---
        ("ride 1x trail30",              {**base, "ride_trail": 30.0}),
        ("ride 2x trail30",              {**base, "ride_q": 2, "ride_trail": 30.0}),
        ("ride 2x trail40",              {**base, "ride_q": 2, "ride_trail": 40.0}),
        ("ride 3x trail30",              {**base, "ride_q": 3, "ride_trail": 30.0}),
        ("ride 3x trail40",              {**base, "ride_q": 3, "ride_trail": 40.0}),
        # --- ride re-entry ---
        ("ride 2x trail30 re2",          {**base, "ride_q": 2, "ride_trail": 30.0, "ride_re": 2}),
        ("ride 3x trail40 re2",          {**base, "ride_q": 3, "ride_trail": 40.0, "ride_re": 2}),
        # --- fade add-on ---
        ("addon 8",                      {**base, "addon": 8.0}),
        ("addon 12",                     {**base, "addon": 12.0}),
        # --- magnitude hold ---
        ("hold2 25@2.5",                 {**base, "hold2": (2.5, 25)}),
        # --- stacks ---
        ("ride2 trail30 + addon12",      {**base, "ride_q": 2, "ride_trail": 30.0, "addon": 12.0}),
        ("ride2 trail30 + hold2",        {**base, "ride_q": 2, "ride_trail": 30.0, "hold2": (2.5, 25)}),
        ("ride2 trail30 + glday300",     {**base, "ride_q": 2, "ride_trail": 30.0, "glday": (300.0, 0.5)}),
        ("ride3 trail40 + addon12",      {**base, "ride_q": 3, "ride_trail": 40.0, "addon": 12.0}),
        ("FULL: r2 t30 re2 addon12",     {**base, "ride_q": 2, "ride_trail": 30.0,
                                          "ride_re": 2, "addon": 12.0}),
        ("FULL: r3 t40 re2 addon12",     {**base, "ride_q": 3, "ride_trail": 40.0,
                                          "ride_re": 2, "addon": 12.0}),
        ("FULL+glday",                   {**base, "ride_q": 2, "ride_trail": 30.0,
                                          "ride_re": 2, "addon": 12.0,
                                          "glday": (300.0, 0.5)}),
    ]
    for nm, g in tests:
        m = metrics(g)
        if m is not None:
            results[nm] = {"cfg": g, "m": m}
        show(nm, m)
    with open("research/round52_results.json", "w") as f:
        json.dump(results, f, default=str, indent=1)
    print(f"\nDONE ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
