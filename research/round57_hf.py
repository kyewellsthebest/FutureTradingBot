"""Round 57: THE HIGH-FREQUENCY GRIND HUNT. User mandate: 400-500
trades/week, small wins/losses, steady incline, must beat fees.
Cost bar: at 450 tr/wk, $1.50/RT = $675/wk commission; all-in friction
~$2.7/trade gross to break even.

Three families, faithful sessions (entries 14:00-20:44 UTC, flat by
20:55, 65ms latency, trade-through passive fills, $1.50/RT), on the
28-week tape (Jan 1 - Jul 15) with sub-minute clocks:

  MICRO  micro-fade: mom over 1-5 MINUTES on 15/30/60s clocks, small
         thresholds, passive entries 0.25-1.0pt, holds 2-10 min.
         The corner round 54's GA never visited (it searched 8-12min).
  STRAN  strangle quoter: when flat, rest BUY at close-X and SELL at
         close+X simultaneously; first trade-through wins; exit at
         opposite target or timer. Passive both ways - never tested.
  VWAPZ  VWAP-magnet: fade deviations > z ATR from session VWAP,
         exit on reversion toward VWAP or timer.

Trend-day guard 8xATR stays on everything (structural, anchor-proof).
Selection: folds JanFeb/MarApr/May/JunJul6 + hostile week; band
300-600 tr/wk; fee stress $2.50/RT on finalists. Flat 1 MNQ only.
"""
import glob, json, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, "research")
import round54_clock as K
import round46_bulletproof_ga as R
from round48_drawdown import maxdd

ENTRY_LO, ENTRY_HI = 14.0, 20.73
EOD_NS = (20 * 60 + 55) * 60_000_000_000
CLOSE_NS = (21 * 60) * 60_000_000_000
GUARD = 8.0
F26 = [("2026-01-01", "2026-03-01"), ("2026-03-01", "2026-05-01"),
       ("2026-05-01", "2026-06-01"), ("2026-06-01", "2026-07-07")]


def prep_indptr():
    """Per-clock: tick index of each bar close time (for O(1) segs)."""
    ts = K.D["ts"]
    for sec in (60, 30, 15):
        C = K.D[sec]
        C["tick_at"] = np.searchsorted(ts, C["bts"], "left")
        C["day_eod_i"] = np.searchsorted(ts, C["days"] + EOD_NS, "left")
        C["day_last_i"] = np.searchsorted(ts, C["days"] + CLOSE_NS, "left") - 1
        kb1 = max(1, int(60 / sec))
        C["moms_hf"] = {km: np.concatenate(([0.0] * (km * kb1),
                                            C["c"][km * kb1:]
                                            - C["c"][:-km * kb1]))
                        for km in (1, 2, 3, 5)}


def build_vwap():
    """Session VWAP on the 60s clock (needs sizes)."""
    z = np.load("data/tick/ytd2026sz.npz")
    ts0, px0, sz0 = z["ts"], z["px"], z["sz"]
    wts, wpx, wsz = [], [], []
    for f in sorted(glob.glob("/tmp/claude-0/weekticks/MNQU6_202607*.parquet")):
        day = f[-16:-8]
        if day < "20260707" or day >= "20260716":
            continue
        t = pd.read_parquet(f)
        wts.append(np.asarray(t["ts"].to_numpy(), np.int64))
        wpx.append(np.asarray(t["price"].to_numpy(), np.float64))
        wsz.append(np.asarray(t["size"].to_numpy(), np.float64))
    wts = np.concatenate(wts); wpx = np.concatenate(wpx)
    wsz = np.concatenate(wsz)
    o = np.argsort(wts, kind="stable")
    wts, wpx, wsz = wts[o], wpx[o], wsz[o]
    cut = np.searchsorted(wts, ts0[-1], "right")
    ts = np.concatenate([ts0, wts[cut:]])
    px = np.concatenate([px0, wpx[cut:]])
    sz = np.concatenate([sz0, wsz[cut:]])
    keep = np.asarray(pd.to_datetime(ts, utc=True).dayofweek) < 5
    ts, px, sz = ts[keep], px[keep], sz[keep]
    m = ts // 60_000_000_000
    st = np.concatenate(([0], np.flatnonzero(np.diff(m)) + 1))
    vol = np.add.reduceat(sz, st)
    pv = np.add.reduceat(px * sz, st)
    bts = (m[st] + 1) * 60_000_000_000
    C = K.D[60]
    assert len(bts) == len(C["bts"]) and bts[0] == C["bts"][0], \
        "vwap clock misaligned"
    day = C["days"]
    dfr = pd.DataFrame({"pv": pv, "vol": vol})
    g = dfr.groupby(day)
    cum_pv = g["pv"].cumsum().to_numpy()
    cum_v = np.maximum(g["vol"].cumsum().to_numpy(), 1.0)
    C["vwap"] = cum_pv / cum_v


def _walk(ts, px, fi, xe, entry, s, dis):
    if dis is not None:
        stop_lvl = entry - dis * s
        seg = px[fi + 1:xe]
        if len(seg):
            sh = np.flatnonzero(seg * s <= stop_lvl * s + 1e-9)
            if len(sh):
                k = fi + 1 + int(sh[0])
                raw = min(px[k], stop_lvl) if s > 0 else max(px[k], stop_lvl)
                return raw - R.STOP_SLIP * s, k, True
    return None, xe, False


def sim_micro(g):
    sec = g["clock"]
    C = K.D[sec]
    ts, px = K.D["ts"], K.D["px"]
    n = len(ts)
    c, hrs, sdt = C["c"], C["hrs"], C["sdt"]
    bts, days, nb = C["bts"], C["days"], C["nb"]
    atr_eq = C["atr"] * np.sqrt(60.0 / sec)
    ninf = np.nan_to_num(atr_eq, nan=np.inf)
    mom = C["moms_hf"][g["km"]]
    thr = g["a"] * ninf
    ent = (hrs >= ENTRY_LO) & (hrs < ENTRY_HI) & (np.abs(sdt) <= GUARD)
    raw = np.where(mom < -thr, 1, np.where(mom > thr, -1, 0))
    sig = np.where(ent, raw, 0)
    sidx = np.flatnonzero(sig)
    out_t, out_p = [], []
    busy = 0
    hold_ns = R.HN(g["hold"])
    for i in sidx:
        if bts[i] < busy:
            continue
        s = int(sig[i])
        L = c[i] - g["off"] * s
        a0 = np.searchsorted(ts, bts[i] + R.LAT_NS, "left")
        a1 = np.searchsorted(ts, bts[i] + int(g["cxl"] * 1e9), "left")
        if a0 >= n: break
        seg = px[a0:a1]
        th = np.flatnonzero(seg * s < (L - R.TICK * s) * s + 1e-9)
        if not len(th):
            continue
        fi = a0 + int(th[0])
        t_tgt = min(ts[fi] + hold_ns + R.LAT_NS, days[i] + EOD_NS)
        xe = np.searchsorted(ts, t_tgt, "left")
        xe = min(xe, C["day_last_i"][i])
        if xe <= fi:
            continue
        fill, k_exit, _ = _walk(ts, px, fi, xe, L, s, 40.0)
        if fill is None:
            fill = px[xe] - R.TICK * s
            k_exit = xe
        out_p.append((fill - L) * s * R.PT - R.FEES)
        out_t.append(ts[k_exit])
        busy = ts[k_exit]
    s_ = pd.Series(out_p, index=pd.to_datetime(
        np.array(out_t, dtype="int64"), utc=True))
    return s_[s_.index.dayofweek < 5]


def sim_strangle(g):
    sec = 30
    C = K.D[sec]
    ts, px = K.D["ts"], K.D["px"]
    n = len(ts)
    c, hrs, sdt = C["c"], C["hrs"], C["sdt"]
    bts, days, nb = C["bts"], C["days"], C["nb"]
    tick_at = C["tick_at"]
    ok = (hrs >= ENTRY_LO) & (hrs < ENTRY_HI) & (np.abs(sdt) <= GUARD)
    X = g["x"]
    out_t, out_p = [], []
    busy = 0
    hold_ns = R.HN(g["hold"]) if g["hold"] else None
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
        # exit: opposite target (entry + tgt*s) trade-through, else timer
        tgt_lvl = entry + g["tgt"] * s if g["tgt"] else None
        t_tgt = (ts[fi] + hold_ns) if hold_ns else (days[i] + EOD_NS)
        t_tgt = min(t_tgt, days[i] + EOD_NS)
        xe = np.searchsorted(ts, t_tgt, "left")
        xe = min(xe, C["day_last_i"][i])
        if xe <= fi:
            continue
        fill = None; k_exit = xe
        seg2 = px[fi + 1:xe]
        if tgt_lvl is not None and len(seg2):
            ht = np.flatnonzero(seg2 * s > (tgt_lvl + R.TICK * s) * s - 1e-9)
            if len(ht):
                k_exit = fi + 1 + int(ht[0])
                fill = tgt_lvl
        if fill is None:
            f2, k2, fired = _walk(ts, px, fi, xe, entry, s, 40.0)
            if f2 is not None and k2 < k_exit:
                fill, k_exit = f2, k2
        if fill is None:
            fill = px[xe] - R.TICK * s
            k_exit = xe
        out_p.append((fill - entry) * s * R.PT - R.FEES)
        out_t.append(ts[k_exit])
        busy = ts[k_exit]
    s_ = pd.Series(out_p, index=pd.to_datetime(
        np.array(out_t, dtype="int64"), utc=True))
    return s_[s_.index.dayofweek < 5]


def sim_vwapz(g):
    C = K.D[60]
    ts, px = K.D["ts"], K.D["px"]
    n = len(ts)
    c, hrs, sdt = C["c"], C["hrs"], C["sdt"]
    bts, days = C["bts"], C["days"]
    atr = C["atr"]
    pos_a = np.where(np.nan_to_num(atr) > 0, atr, np.inf)
    dev = (c - C["vwap"]) / pos_a
    ent = (hrs >= ENTRY_LO) & (hrs < ENTRY_HI) & (np.abs(sdt) <= GUARD)
    sig = np.where(ent & (dev > g["z"]), -1,
                   np.where(ent & (dev < -g["z"]), 1, 0))
    out_t, out_p = [], []
    busy = 0
    hold_ns = R.HN(g["hold"])
    for i in np.flatnonzero(sig):
        if bts[i] < busy:
            continue
        s = int(sig[i])
        if g["passive"]:
            L = c[i] - g["off"] * s
            a0 = np.searchsorted(ts, bts[i] + R.LAT_NS, "left")
            a1 = np.searchsorted(ts, bts[i] + 60_000_000_000, "left")
            if a0 >= n: break
            seg = px[a0:a1]
            th = np.flatnonzero(seg * s < (L - R.TICK * s) * s + 1e-9)
            if not len(th):
                continue
            fi = a0 + int(th[0])
            entry = L
        else:
            fi = np.searchsorted(ts, bts[i] + R.LAT_NS, "left")
            if fi >= n: break
            entry = px[fi] + R.TICK * s
        t_tgt = min(ts[fi] + hold_ns + R.LAT_NS, days[i] + EOD_NS)
        xe = np.searchsorted(ts, t_tgt, "left")
        xe = min(xe, C["day_last_i"][i])
        if xe <= fi:
            continue
        fill, k_exit, _ = _walk(ts, px, fi, xe, entry, s, 40.0)
        if fill is None:
            fill = px[xe] - R.TICK * s
            k_exit = xe
        out_p.append((fill - entry) * s * R.PT - R.FEES)
        out_t.append(ts[k_exit])
        busy = ts[k_exit]
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
    prep_indptr()
    build_vwap()
    print(f"prep done ({time.time()-t0:.0f}s)", flush=True)
    print(f"{'variant':<34} {'$/wk':>5} {'tr/wk':>6} {'wr':>4} "
          f"{'avgW':>6} {'avgL':>7} {'posW':>4} {'wd':>6} {'MDD':>6} "
          f"{'host':>5} {'minF':>5}")
    results = {}
    # ---- A: micro-fade grid -------------------------------------------
    print("--- MICRO-FADE ---", flush=True)
    for sec in (60, 30, 15):
        for km in (1, 2, 3, 5):
            for a in (0.5, 0.7, 0.9, 1.2):
                for off, cxl in ((0.5, 60), (1.0, 60)):
                    for hold in (2, 4, 6, 10):
                        nm = f"MICRO c{sec} m{km} a{a} o{off} h{hold}"
                        m = metrics(sim_micro({"clock": sec, "km": km,
                                               "a": a, "off": off,
                                               "cxl": cxl, "hold": hold}))
                        if m is not None and 250 <= m["tr_wk"] <= 700:
                            results[nm] = m
                            show(nm, m)
        print(f"  clock {sec} done ({time.time()-t0:.0f}s)", flush=True)
    # ---- B: strangle quoter -------------------------------------------
    print("--- STRANGLE ---", flush=True)
    for x in (3.0, 4.0, 6.0, 8.0, 10.0):
        for tgt, hold in ((None, 2), (None, 5), (None, 10),
                          (x, 10), (1.5 * x, 10)):
            nm = (f"STRAN x{x} "
                  f"{'tgt' + str(round(tgt,1)) if tgt else 'h' + str(hold)}")
            m = metrics(sim_strangle({"x": x, "tgt": tgt, "hold": hold}))
            if m is not None:
                results[nm] = m
                show(nm, m)
    print(f"  strangle done ({time.time()-t0:.0f}s)", flush=True)
    # ---- C: vwap magnet -----------------------------------------------
    print("--- VWAP-Z ---", flush=True)
    for z in (1.5, 2.0, 2.5, 3.0):
        for passive in (True, False):
            for hold in (5, 10, 15):
                nm = f"VWAPZ z{z} {'pas' if passive else 'mkt'} h{hold}"
                m = metrics(sim_vwapz({"z": z, "passive": passive,
                                       "off": 0.5, "hold": hold}))
                if m is not None:
                    results[nm] = m
                    show(nm, m)
    with open("research/round57_results.json", "w") as f:
        json.dump(results, f, indent=1)
    good = {k: v for k, v in results.items()
            if 300 <= v["tr_wk"] <= 600 and v["usd_wk"] > 250
            and v["pos"] >= 70 and v["host"] > -400}
    print(f"\n=== BAND CANDIDATES (300-600 tr/wk, >$250/wk, pos>=70%, "
          f"hostile>-400): {len(good)} ===")
    for k, v in sorted(good.items(), key=lambda kv: -kv[1]["usd_wk"]):
        show(k, v)
    print(f"\nDONE {len(results)} qualifying configs ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
