"""Round 59: THE CONCURRENCY UNLOCK + SESSION EXPANSION.
User: "there has to be something above 65 tr/wk." Correct diagnosis:
the ceiling is OUR engine's one-position-at-a-time rule, not the
market's. Two untouched frequency doors:

  A. OVERLAPPING SLOTS: keep the proven trade exactly as-is (fade
     1.2xATR, hold 15, dis 60, guard 8, flat 1 MNQ per slot) but run
     up to K concurrent slots with an entry-spacing gene. Frequency
     ~K x 65 with the same per-trade edge. Exposure cap = K lots.
  B. EUROPEAN MORNING: the same core in 07:00-13:00 UTC - a second
     session the bot currently sleeps through.

Both price-only -> full 2023-2025 history judgment. Faithful fills.
"""
import gc, json, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, "research")
import round54_clock as K
import round46_bulletproof_ga as R
from round58_frontier import hist_clock, prep_clock
from round48_drawdown import maxdd

EOD_NS = (20 * 60 + 55) * 60_000_000_000
GUARD = 8.0
F26 = [("2026-01-01", "2026-03-01"), ("2026-03-01", "2026-05-01"),
       ("2026-05-01", "2026-06-01"), ("2026-06-01", "2026-07-07")]


def sim_slots(g, ts, px, C):
    """Fade with up to K overlapping flat-1 slots."""
    n = len(ts)
    c, hrs, sdt = C["c"], C["hrs"], C["sdt"]
    bts, days, nb = C["bts"], C["days"], C["nb"]
    atr = C["atr"]
    ninf = np.nan_to_num(atr, nan=np.inf)
    kb = 10
    mom = np.concatenate(([0.0] * kb, c[kb:] - c[:-kb]))
    thr = g["a"] * ninf
    lo, hi = g.get("win", (14.0, 20.73))
    ent = (hrs >= lo) & (hrs < hi) & (np.abs(sdt) <= GUARD)
    raw = np.where(mom < -thr, 1, np.where(mom > thr, -1, 0))
    sig = np.where(ent, raw, 0)
    Kmax = g["k"]
    gap_ns = int(g["gap"] * 1e9)
    out_t, out_p = [], []
    open_exits = []          # exit timestamps of live slots
    last_entry = 0
    hold_ns = R.HN(15)
    passive = g["passive"]
    for i in np.flatnonzero(sig):
        t_bar = bts[i]
        open_exits = [x for x in open_exits if x > t_bar]
        if len(open_exits) >= Kmax or t_bar - last_entry < gap_ns:
            continue
        s = int(sig[i])
        if passive:
            L = c[i] - 1.0 * s
            a0 = np.searchsorted(ts, t_bar + R.LAT_NS, "left")
            a1 = np.searchsorted(ts, t_bar + 180_000_000_000, "left")
            if a0 >= n: break
            seg = px[a0:a1]
            th = np.flatnonzero(seg * s < (L - R.TICK * s) * s + 1e-9)
            if not len(th):
                continue
            fi = a0 + int(th[0])
            entry = L
        else:
            fi = np.searchsorted(ts, t_bar + R.LAT_NS, "left")
            if fi >= n: break
            entry = px[fi] + R.TICK * s
        t_tgt = min(ts[fi] + hold_ns + R.LAT_NS, days[i] + EOD_NS)
        xe = np.searchsorted(ts, t_tgt, "left")
        xe = min(xe, C["day_last_i"][i])
        if xe <= fi:
            continue
        fill = None; k_exit = xe
        stop_lvl = entry - 60.0 * s
        seg2 = px[fi + 1:xe]
        if len(seg2):
            sh = np.flatnonzero(seg2 * s <= stop_lvl * s + 1e-9)
            if len(sh):
                k_exit = fi + 1 + int(sh[0])
                rw = min(px[k_exit], stop_lvl) if s > 0 \
                    else max(px[k_exit], stop_lvl)
                fill = rw - R.STOP_SLIP * s
        if fill is None:
            fill = px[xe] - R.TICK * s
            k_exit = xe
        out_p.append((fill - entry) * s * R.PT - R.FEES)
        out_t.append(ts[k_exit])
        open_exits.append(ts[k_exit])
        last_entry = t_bar
    s_ = pd.Series(out_p, index=pd.to_datetime(
        np.array(out_t, dtype="int64"), utc=True)).sort_index()
    return s_[s_.index.dayofweek < 5]


def metrics(s):
    if len(s) < 500:
        return None
    wk = R.wk_of(s)
    if len(wk) < 24:
        return None
    dy = s.resample("D").sum(); dy = dy[dy != 0]
    folds = []
    for lo, hi in F26:
        f = s[(s.index >= pd.Timestamp(lo, tz="UTC"))
              & (s.index < pd.Timestamp(hi, tz="UTC"))]
        w = R.wk_of(f)
        folds.append(round(float(f.sum() / max(len(w), 1))) if len(f) else 0)
    ho = float(s[s.index >= pd.Timestamp("2026-07-07", tz="UTC")].sum())
    wins = s[s > 0]
    return dict(usd_wk=round(float(s.sum() / len(wk))),
                tr_wk=round(len(s) / len(wk), 1),
                wr=round(float((s > 0).mean() * 100)),
                aw=round(float(wins.mean()), 1) if len(wins) else 0,
                al=round(float(s[s < 0].mean()), 1),
                pos=round(float((wk > 0).mean() * 100)),
                wd=round(float(dy.min())), mdd=round(float(maxdd(dy))),
                host=round(ho), minf=min(folds))


def show(nm, m):
    if m is None:
        print(f"{nm:<34} (insufficient)", flush=True); return
    print(f"{nm:<34} {m['usd_wk']:>5} {m['tr_wk']:>6} {m['wr']:>3}% "
          f"{m['aw']:>6} {m['al']:>7} {m['pos']:>4} {m['wd']:>6} "
          f"{m['mdd']:>6} {m['host']:>5} {m['minf']:>5}", flush=True)


def main():
    t0 = time.time()
    K.build_tape()
    prep_clock(K.D[60], K.D["ts"])
    ts26, px26 = K.D["ts"], K.D["px"]
    C26 = K.D[60]
    print(f"{'variant':<34} {'$/wk':>5} {'tr/wk':>6} {'wr':>4} "
          f"{'avgW':>6} {'avgL':>7} {'posW':>4} {'wd':>6} {'MDD':>6} "
          f"{'host':>5} {'minF':>5}", flush=True)
    print("--- A: overlapping slots (US session) ---", flush=True)
    results = {}
    for k in (1, 2, 3, 4):
        for gap in (0, 60, 120, 300):
            if k == 1 and gap > 0:
                continue
            for a in (1.2, 1.5):
                for passive in (True, False):
                    g = {"k": k, "gap": gap, "a": a, "passive": passive}
                    nm = (f"K{k} gap{gap} a{a} "
                          f"{'pas' if passive else 'mkt'}")
                    m = metrics(sim_slots(g, ts26, px26, C26))
                    if m is not None:
                        results[nm] = {"g": g, "m": m}
                        show(nm, m)
        print(f"  K{k} done ({time.time()-t0:.0f}s)", flush=True)
    print("--- B: EU morning window 07-13 UTC (K=1..2) ---", flush=True)
    for k in (1, 2):
        for a in (1.2, 1.5):
            g = {"k": k, "gap": 60, "a": a, "passive": True,
                 "win": (7.0, 13.0)}
            nm = f"EU K{k} a{a} pas"
            m = metrics(sim_slots(g, ts26, px26, C26))
            if m is not None:
                results[nm] = {"g": g, "m": m}
                show(nm, m)
    with open("research/round59_results.json", "w") as f:
        json.dump(results, f, indent=1)
    # ---- finalists: freq >= 100, $/wk >= 500, pos >= 75, hostile > -600
    fin = [(nm, v) for nm, v in results.items()
           if v["m"]["tr_wk"] >= 100 and v["m"]["usd_wk"] >= 500
           and v["m"]["pos"] >= 75 and v["m"]["host"] > -600]
    fin.sort(key=lambda kv: (-kv[1]["m"]["tr_wk"], -kv[1]["m"]["usd_wk"]))
    print(f"\nfinalists (>=100 tr/wk, >=$500/wk, pos>=75, host>-600): "
          f"{len(fin)}", flush=True)
    for nm, v in fin[:8]:
        show(nm, v["m"])
    if not fin:
        print("no finalists. DONE"); return
    print("\n=== fee stress $2.50/RT ===", flush=True)
    R.FEES = 2.50
    for nm, v in fin[:4]:
        m = metrics(sim_slots(v["g"], ts26, px26, C26))
        print(f"  {nm}: $/wk {m['usd_wk'] if m else '-'} "
              f"pos {m['pos'] if m else '-'}%", flush=True)
    R.FEES = 1.50
    print(f"\nfreeing 2026, building history 60s ({time.time()-t0:.0f}s)",
          flush=True)
    del ts26, px26, C26
    K.D.clear(); gc.collect()
    tsH, pxH, CH = hist_clock(60)
    print(f"history bars: {CH['nb']:,} ({time.time()-t0:.0f}s)", flush=True)
    for nm, v in fin[:4]:
        sH = sim_slots(v["g"], tsH, pxH, CH)
        print(f"-- {nm} --", flush=True)
        for yr in (2023, 2024, 2025):
            sy = sH[sH.index.year == yr]
            if len(sy) < 50:
                print(f"  {yr}: n={len(sy)}"); continue
            w = R.wk_of(sy)
            d = sy.resample("D").sum(); d = d[d != 0]
            print(f"  {yr}: $/wk {sy.sum()/max(len(w),1):6.0f} | "
                  f"tr/wk {len(sy)/max(len(w),1):5.1f} | "
                  f"pos {(w>0).mean()*100:3.0f}% | wd {d.min():6.0f} | "
                  f"MDD {maxdd(d):7.0f}", flush=True)
    print(f"\nDONE ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
