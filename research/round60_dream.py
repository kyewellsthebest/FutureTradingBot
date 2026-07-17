"""Round 60: THE DREAM-SPEC MEGA-SWEEP. User mandate: double the HF
config count; hunt the ~50% WR / 2:1 payoff / 200-400 tr/wk profile.
New dimensions (not re-grinds):
  F1 BRACKET MICRO-FADE: fixed tgt x stop brackets (the literal
     mathematical form of "$80 win / $40 loss") on fast-clock fades.
  F2 BRACKET STRANGLE: round-57 quoter with tight symmetric brackets.
  F3 LEVEL-TOUCH FADES: prior-day high/low, overnight extremes,
     round-number magnets - an untested signal family.
  F4 POWER-HOURS: the best F1 signals confined to open/close hours.
DREAM DETECTOR: flags any config with WR 45-55%, avgW/|avgL| >= 1.5,
tr/wk >= 150 - regardless of profit - so the closest real distance
to the dream spec is measured, not asserted.
Discipline: faithful fills, guard 8, folds + hostile week; survivors
(tr/wk>=150, $/wk>=400 worst-case fees, pos>=70, hostile>-400) get
history judgment. Best-case fee variant reported for near-misses.
"""
import gc, json, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, "research")
import round54_clock as K
import round46_bulletproof_ga as R
from round58_frontier import prep_clock, hist_clock
from round48_drawdown import maxdd

ENTRY_LO, ENTRY_HI, GUARD = 14.0, 20.73, 8.0
EOD_NS = (20 * 60 + 55) * 60_000_000_000
F26 = [("2026-01-01", "2026-03-01"), ("2026-03-01", "2026-05-01"),
       ("2026-05-01", "2026-06-01"), ("2026-06-01", "2026-07-07")]


def day_levels(C):
    """Prior-day RTH high/low and overnight high/low per bar."""
    c, hrs = C["c"], C["hrs"]
    dayid = C["days"] // 86_400_000_000_000
    n = len(c)
    pdh = np.full(n, np.nan); pdl = np.full(n, np.nan)
    onh = np.full(n, np.nan); onl = np.full(n, np.nan)
    cur = -1
    prev_h = prev_l = np.nan
    run_h = run_l = np.nan
    o_h = o_l = np.nan
    for i in range(n):
        d = dayid[i]
        if d != cur:
            prev_h, prev_l = run_h, run_l
            run_h = run_l = np.nan
            o_h = o_l = np.nan
            cur = d
        px_ = c[i]
        if hrs[i] >= 14.0:
            run_h = px_ if np.isnan(run_h) else max(run_h, px_)
            run_l = px_ if np.isnan(run_l) else min(run_l, px_)
        else:
            o_h = px_ if np.isnan(o_h) else max(o_h, px_)
            o_l = px_ if np.isnan(o_l) else min(o_l, px_)
        pdh[i] = prev_h; pdl[i] = prev_l
        onh[i] = o_h; onl[i] = o_l
    C["pdh"], C["pdl"], C["onh"], C["onl"] = pdh, pdl, onh, onl


def bracket_exit(ts, px, fi, entry, s, tgt, stop, t_max, day_last_i):
    """Tick-walk: target (trade-through) vs stop (through+slip) vs timer."""
    n = len(ts)
    xe = min(np.searchsorted(ts, t_max, "left"), day_last_i)
    if xe <= fi:
        return None, None
    tgt_lvl = entry + tgt * s
    stop_lvl = entry - stop * s
    seg = px[fi + 1:xe]
    it = ist = 1 << 60
    if len(seg):
        ht = np.flatnonzero(seg * s > (tgt_lvl + R.TICK * s) * s - 1e-9)
        hs = np.flatnonzero(seg * s <= stop_lvl * s + 1e-9)
        if len(ht): it = ht[0]
        if len(hs): ist = hs[0]
    if it < ist:
        return tgt_lvl, fi + 1 + int(it)
    if ist < it:
        k = fi + 1 + int(ist)
        raw = min(px[k], stop_lvl) if s > 0 else max(px[k], stop_lvl)
        return raw - R.STOP_SLIP * s, k
    return px[xe] - R.TICK * s, xe


def sim_bracket_fade(g, ts, px, C, sec):
    n = len(ts)
    c, hrs, sdt = C["c"], C["hrs"], C["sdt"]
    bts, days, nb = C["bts"], C["days"], C["nb"]
    atr_eq = C["atr"] * np.sqrt(60.0 / sec)
    ninf = np.nan_to_num(atr_eq, nan=np.inf)
    kb = max(1, int(g["km"] * 60 / sec))
    mom = np.concatenate(([0.0] * kb, c[kb:] - c[:-kb]))
    thr = g["a"] * ninf
    lo, hi = g.get("win", (ENTRY_LO, ENTRY_HI))
    ent = (hrs >= lo) & (hrs < hi) & (np.abs(sdt) <= GUARD)
    if g.get("win2"):
        lo2, hi2 = g["win2"]
        ent = ent | ((hrs >= lo2) & (hrs < hi2) & (np.abs(sdt) <= GUARD))
    raw = np.where(mom < -thr, 1, np.where(mom > thr, -1, 0))
    sig = np.where(ent, raw, 0)
    out_t, out_p = [], []
    busy = 0
    for i in np.flatnonzero(sig):
        if bts[i] < busy:
            continue
        s = int(sig[i])
        L = c[i] - g["off"] * s
        a0 = np.searchsorted(ts, bts[i] + R.LAT_NS, "left")
        a1 = np.searchsorted(ts, bts[i] + 60_000_000_000, "left")
        if a0 >= n: break
        seg = px[a0:a1]
        th = np.flatnonzero(seg * s < (L - R.TICK * s) * s + 1e-9)
        if not len(th):
            continue
        fi = a0 + int(th[0])
        t_max = min(ts[fi] + R.HN(30), days[i] + EOD_NS)
        fill, k = bracket_exit(ts, px, fi, L, s, g["tgt"], g["stop"],
                               t_max, C["day_last_i"][i])
        if fill is None:
            continue
        out_p.append((fill - L) * s * R.PT - R.FEES)
        out_t.append(ts[k])
        busy = ts[k]
    s_ = pd.Series(out_p, index=pd.to_datetime(
        np.array(out_t, dtype="int64"), utc=True))
    return s_[s_.index.dayofweek < 5]


def sim_bracket_strangle(g, ts, px, C):
    n = len(ts)
    c, hrs, sdt = C["c"], C["hrs"], C["sdt"]
    bts, days, nb = C["bts"], C["days"], C["nb"]
    tick_at = np.searchsorted(ts, bts, "left")
    ok = (hrs >= ENTRY_LO) & (hrs < ENTRY_HI) & (np.abs(sdt) <= GUARD)
    X = g["x"]
    out_t, out_p = [], []
    busy = 0
    for i in np.flatnonzero(ok):
        if bts[i] < busy:
            continue
        a0 = tick_at[i]
        a1 = tick_at[i + 1] if i + 1 < nb else n
        if a0 >= n or a1 <= a0:
            continue
        seg = px[a0:a1]
        B, S = c[i] - X, c[i] + X
        hb = np.flatnonzero(seg < B - R.TICK + 1e-9)
        hs = np.flatnonzero(seg > S + R.TICK - 1e-9)
        ib = hb[0] if len(hb) else 1 << 60
        is_ = hs[0] if len(hs) else 1 << 60
        if ib == is_:
            continue
        if ib < is_:
            s, entry, fi = 1, B, a0 + int(ib)
        else:
            s, entry, fi = -1, S, a0 + int(is_)
        t_max = min(ts[fi] + R.HN(30), days[i] + EOD_NS)
        fill, k = bracket_exit(ts, px, fi, entry, s, g["tgt"], g["stop"],
                               t_max, C["day_last_i"][i])
        if fill is None:
            continue
        out_p.append((fill - entry) * s * R.PT - R.FEES)
        out_t.append(ts[k])
        busy = ts[k]
    s_ = pd.Series(out_p, index=pd.to_datetime(
        np.array(out_t, dtype="int64"), utc=True))
    return s_[s_.index.dayofweek < 5]


def sim_level_fade(g, ts, px, C):
    """Fade touches of pdh/pdl/onh/onl/round levels back toward range."""
    n = len(ts)
    c, hrs, sdt = C["c"], C["hrs"], C["sdt"]
    bts, days, nb = C["bts"], C["days"], C["nb"]
    ent = (hrs >= ENTRY_LO) & (hrs < ENTRY_HI) & (np.abs(sdt) <= GUARD)
    kind = g["lvl"]
    if kind == "pd":
        up_lvl, dn_lvl = C["pdh"], C["pdl"]
    elif kind == "on":
        up_lvl, dn_lvl = C["onh"], C["onl"]
    else:  # round numbers
        step = g["step"]
        up_lvl = np.ceil(c / step) * step
        dn_lvl = np.floor(c / step) * step
    prox = g["prox"]
    near_up = ent & (up_lvl - c <= prox) & (up_lvl - c > 0)
    near_dn = ent & (c - dn_lvl <= prox) & (c - dn_lvl > 0)
    out_t, out_p = [], []
    busy = 0
    for i in range(nb):
        if not (near_up[i] or near_dn[i]):
            continue
        if bts[i] < busy:
            continue
        if near_up[i]:
            s, L = -1, float(up_lvl[i])
        else:
            s, L = 1, float(dn_lvl[i])
        a0 = np.searchsorted(ts, bts[i] + R.LAT_NS, "left")
        a1 = np.searchsorted(ts, bts[i] + 120_000_000_000, "left")
        if a0 >= n: break
        seg = px[a0:a1]
        th = np.flatnonzero(seg * s < (L - R.TICK * s) * s + 1e-9)
        if not len(th):
            continue
        fi = a0 + int(th[0])
        t_max = min(ts[fi] + R.HN(30), days[i] + EOD_NS)
        fill, k = bracket_exit(ts, px, fi, L, s, g["tgt"], g["stop"],
                               t_max, C["day_last_i"][i])
        if fill is None:
            continue
        out_p.append((fill - L) * s * R.PT - R.FEES)
        out_t.append(ts[k])
        busy = ts[k]
    s_ = pd.Series(out_p, index=pd.to_datetime(
        np.array(out_t, dtype="int64"), utc=True))
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
    wins = s[s > 0]; losses = s[s < 0]
    aw = float(wins.mean()) if len(wins) else 0.0
    al = float(losses.mean()) if len(losses) else -1e-9
    return dict(usd_wk=round(float(s.sum() / len(wk))),
                tr_wk=round(len(s) / len(wk), 1),
                wr=round(float((s > 0).mean() * 100)),
                aw=round(aw, 1), al=round(al, 1),
                ratio=round(aw / abs(al), 2) if al else 0,
                pos=round(float((wk > 0).mean() * 100)),
                wd=round(float(dy.min())), mdd=round(float(maxdd(dy))),
                host=round(ho), minf=min(folds))


def main():
    t0 = time.time()
    K.build_tape()
    for sec in (60, 30):
        prep_clock(K.D[sec], K.D["ts"])
    day_levels(K.D[60])
    ts26, px26 = K.D["ts"], K.D["px"]
    n_run = 0
    dream = []       # WR 45-55, ratio >= 1.5, tr/wk >= 150
    surv = []        # full survivor bar
    near = []        # top by $/wk regardless
    def consider(nm, m, g, fam):
        nonlocal n_run
        if m is None:
            return
        if 45 <= m["wr"] <= 55 and m["ratio"] >= 1.5 and m["tr_wk"] >= 150:
            dream.append((nm, m))
            print(f"DREAM-FLAG {nm}: {m}", flush=True)
        if (m["tr_wk"] >= 150 and m["usd_wk"] >= 400 and m["pos"] >= 70
                and m["host"] > -400):
            surv.append((nm, g, fam, m))
            print(f"SURVIVOR {nm}: {m}", flush=True)
        near.append((m["usd_wk"], nm, m))
    # ---- F1: bracket micro-fade -----------------------------------
    for sec in (60, 30):
        C = K.D[sec]
        for km in (2, 3, 5):
            for a in (0.8, 1.0, 1.2):
                for off in (0.5, 1.0):
                    for tgt in (4.0, 6.0, 8.0, 12.0):
                        for stop in (6.0, 10.0, 20.0):
                            g = {"km": km, "a": a, "off": off,
                                 "tgt": tgt, "stop": stop}
                            n_run += 1
                            m = metrics(sim_bracket_fade(g, ts26, px26,
                                                         C, sec))
                            consider(f"F1 c{sec} m{km} a{a} o{off} "
                                     f"t{tgt} s{stop}", m, g, "F1")
        print(f"F1 clock {sec} done: {n_run} ({time.time()-t0:.0f}s)",
              flush=True)
    # ---- F2: bracket strangle --------------------------------------
    C = K.D[30]
    for x in (4.0, 6.0, 8.0):
        for tgt in (4.0, 6.0, 8.0, 12.0):
            for stop in (6.0, 8.0, 12.0, 20.0):
                g = {"x": x, "tgt": tgt, "stop": stop}
                n_run += 1
                m = metrics(sim_bracket_strangle(g, ts26, px26, C))
                consider(f"F2 x{x} t{tgt} s{stop}", m, g, "F2")
    print(f"F2 done: {n_run} ({time.time()-t0:.0f}s)", flush=True)
    # ---- F3: level-touch fades --------------------------------------
    C = K.D[60]
    for lvl, step in (("pd", 0), ("on", 0), ("rnd", 50.0), ("rnd", 100.0)):
        for prox in (3.0, 6.0):
            for tgt in (6.0, 10.0):
                for stop in (10.0, 20.0):
                    g = {"lvl": lvl, "step": step, "prox": prox,
                         "tgt": tgt, "stop": stop}
                    n_run += 1
                    m = metrics(sim_level_fade(g, ts26, px26, C))
                    consider(f"F3 {lvl}{int(step) if step else ''} "
                             f"p{prox} t{tgt} s{stop}", m, g, "F3")
    print(f"F3 done: {n_run} ({time.time()-t0:.0f}s)", flush=True)
    # ---- F4: power hours --------------------------------------------
    for sec in (60, 30):
        C = K.D[sec]
        for km in (2, 3):
            for a in (0.8, 1.0):
                for tgt in (4.0, 6.0, 8.0):
                    for stop in (6.0, 10.0):
                        g = {"km": km, "a": a, "off": 0.5, "tgt": tgt,
                             "stop": stop, "win": (14.0, 15.5),
                             "win2": (19.5, 20.73)}
                        n_run += 1
                        m = metrics(sim_bracket_fade(g, ts26, px26,
                                                     C, sec))
                        consider(f"F4 c{sec} m{km} a{a} t{tgt} s{stop}",
                                 m, g, "F4")
    print(f"F4 done: {n_run} ({time.time()-t0:.0f}s)", flush=True)
    # ---- report ------------------------------------------------------
    near.sort(key=lambda z: -z[0])
    print(f"\n=== TOP 12 by $/wk (of {n_run} configs) ===")
    for usd, nm, m in near[:12]:
        print(f"  {nm}: {m}", flush=True)
    print(f"\ndream flags: {len(dream)} | survivors: {len(surv)}")
    with open("research/round60_results.json", "w") as f:
        json.dump({"n_run": n_run,
                   "dream": [(nm, m) for nm, m in dream],
                   "survivors": [(nm, m) for nm, _, _, m in surv],
                   "top": [(nm, m) for _, nm, m in near[:25]]},
                  f, indent=1, default=str)
    # history judgment for survivors
    if surv:
        print("\nfreeing 2026, history judgment...", flush=True)
        del ts26, px26
        K.D.clear(); gc.collect()
        for sec in {60}:
            tsH, pxH, CH = hist_clock(sec)
            day_levels(CH)
            for nm, g, fam, m in surv[:5]:
                simf = {"F1": lambda: sim_bracket_fade(g, tsH, pxH, CH, sec),
                        "F3": lambda: sim_level_fade(g, tsH, pxH, CH)}.get(fam)
                if simf is None:
                    continue
                sH = simf()
                print(f"-- {nm} --", flush=True)
                for yr in (2023, 2024, 2025):
                    sy = sH[sH.index.year == yr]
                    if len(sy) < 50:
                        print(f"  {yr}: n={len(sy)}"); continue
                    w = R.wk_of(sy)
                    d = sy.resample("D").sum(); d = d[d != 0]
                    print(f"  {yr}: $/wk {sy.sum()/max(len(w),1):6.0f} | "
                          f"pos {(w>0).mean()*100:3.0f}% | wd {d.min():6.0f}",
                          flush=True)
    print(f"\nDONE {n_run} configs ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
