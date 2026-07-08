"""Round 34: MACRO cross-asset — Gold (GC) and 30y Bond (ZB) vs NQ.
Different mechanism than ES lead-lag: these are risk-regime signals, not
sub-second races, so retail latency doesn't kill them a priori.
  A. RISKOFF: ZB surging (flight to safety) while NQ still near highs
     -> short NQ; mirror for risk-on
  B. GCSPIKE: gold impulse -> NQ direction (both ways tested)
  C. BONDDIV: ZB and NQ 30m returns same-sign (correlation break;
     normally opposite) -> trade NQ back
  D. MACROGATE: flow-follow gated by bond-implied risk regime
Grid 1s, NQ tick-walked, flat 1 MNQ, $1.50/RT.
Select Apr 1 - May 31, blind Jun 1 - 18 (data end).
"""
import time
import numpy as np, pandas as pd

PT = 2.0
FEES = 1.50
TICK = 0.25
LAT_NS = 65_000_000
SEL_LO = pd.Timestamp("2026-04-01", tz="UTC")
SPLIT = pd.Timestamp("2026-06-01", tz="UTC")
END = pd.Timestamp("2026-06-19", tz="UTC")


def main():
    t0 = time.time()
    z = np.load("data/tick/ytd2026sz.npz")
    ts, px, szv = z["ts"], z["px"], z["sz"]
    keep = (ts >= SEL_LO.value) & (ts < END.value)
    ts, px, szv = ts[keep], px[keep], szv[keep]
    n = len(ts)
    d = np.sign(np.diff(px, prepend=px[0]))
    print(f"NQ ticks: {n:,}", flush=True)
    sec0 = SEL_LO.value
    grid = np.arange(sec0, END.value, 1_000_000_000)
    ng = len(grid)

    def onto_grid(path):
        t = pd.read_parquet(path)
        t = t[(t["ts"] >= SEL_LO.value) & (t["ts"] < END.value)]
        s = ((t["ts"].to_numpy() - sec0) // 1_000_000_000).astype(np.int64)
        arr = np.full(ng, np.nan)
        arr[np.clip(s, 0, ng - 1)] = t["close"].to_numpy()
        return pd.Series(arr).ffill().to_numpy()

    gc = onto_grid("data/xasset/GC_1s.parquet")
    zb = onto_grid("data/xasset/ZB_1s.parquet")
    nq_sec = ((ts - sec0) // 1_000_000_000).astype(np.int64)
    nq = np.full(ng, np.nan)
    nq[np.clip(nq_sec, 0, ng - 1)] = px
    nq = pd.Series(nq).ffill().to_numpy()
    # NQ flow per second for the gate family
    ivs = np.zeros(ng)
    np.add.at(ivs, np.clip(nq_sec, 0, ng - 1), d * szv)
    valid = ~np.isnan(gc) & ~np.isnan(zb) & ~np.isnan(nq)
    hrs = ((grid // 3_600_000_000_000) % 24).astype(int) + \
        ((grid // 60_000_000_000) % 60).astype(int) / 60.0
    rth = (hrs >= 13.5) & (hrs < 20.9)
    print(f"grid {ng:,}s valid {valid.mean()*100:.0f}% ({time.time()-t0:.0f}s)",
          flush=True)

    def ret(a, k):
        r = a - np.roll(a, k); r[:k] = 0
        return r

    def sdroll(a, k, w):
        return pd.Series(np.abs(ret(a, k))).rolling(w).mean().to_numpy()

    def run_grid(sig, hold_min, fire_on_transition=True):
        if fire_on_transition:
            sig = np.where(sig != np.roll(sig, 1), sig, 0)
        li = np.flatnonzero(sig != 0)
        out = []
        busy = 0
        hn = int(hold_min * 60_000_000_000)
        for i_ in li:
            s = sig[i_]
            t = grid[i_] + 1_000_000_000
            if t < busy:
                continue
            ei = np.searchsorted(ts, t + LAT_NS, side="left")
            if ei >= n:
                break
            e = px[ei] + TICK * s
            xj = np.searchsorted(ts, t + hn + LAT_NS, side="left")
            if xj >= n:
                break
            out.append((ts[xj], (px[xj] - TICK * s - e) * s * PT - FEES))
            busy = ts[xj]
        return out

    def st(out, lo, hi):
        s = pd.Series([p for _, p in out],
                      index=pd.to_datetime([t for t, _ in out], utc=True))
        s = s[(s.index >= lo) & (s.index < hi)]
        w = s.resample("W").sum(); w = w[w != 0]
        if not len(s) or not len(w):
            return dict(usd_wk=0.0, tr_wk=0.0, per=0.0, worst=0.0, pos=0)
        wkn = max(len(w), 1)
        return dict(usd_wk=round(s.sum() / wkn, 0), tr_wk=round(len(s) / wkn, 1),
                    per=round(s.mean(), 2), worst=round(w.min(), 0),
                    pos=round((w > 0).mean() * 100))

    rows = []

    def add(name, out):
        a = st(out, SEL_LO, SPLIT); bl = st(out, SPLIT, END)
        rows.append({"name": name, "sel_usd_wk": a["usd_wk"],
                     "sel_tr_wk": a["tr_wk"], "sel_per": a["per"],
                     "bl_usd_wk": bl["usd_wk"], "bl_tr_wk": bl["tr_wk"],
                     "bl_per": bl["per"], "bl_worst": bl["worst"],
                     "bl_pos": bl["pos"]})

    # ---- A. RISKOFF ---------------------------------------------------------
    zb_r = ret(zb, 900)                       # 15m bond move
    zb_sd = sdroll(zb, 900, 3600)
    nq_hi30 = pd.Series(nq).rolling(1800).max().to_numpy()
    nq_lo30 = pd.Series(nq).rolling(1800).min().to_numpy()
    near_hi = nq >= nq_hi30 - 10
    near_lo = nq <= nq_lo30 + 10
    for M in (2.0, 4.0):
        thr = M * np.nan_to_num(zb_sd, nan=np.inf)
        sig = np.where((zb_r > thr) & near_hi & rth & valid, -1,
                       np.where((zb_r < -thr) & near_lo & rth & valid, 1, 0))
        for hold in (15, 30, 60):
            add(f"A_RISKOFF_M{M}_t{hold}", run_grid(sig, hold))
    print(f"[A] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- B. GCSPIKE ---------------------------------------------------------
    gc_r = ret(gc, 300)
    gc_sd = sdroll(gc, 300, 3600)
    for M in (3.0, 5.0):
        thr = M * np.nan_to_num(gc_sd, nan=np.inf)
        sigF = np.where((gc_r > thr) & rth & valid, -1,
                        np.where((gc_r < -thr) & rth & valid, 1, 0))
        for hold in (15, 30):
            add(f"B_GCSPKrisk_M{M}_t{hold}", run_grid(sigF, hold))
            add(f"B_GCSPKmom_M{M}_t{hold}", run_grid(-sigF, hold))
    print(f"[B] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- C. BONDDIV ---------------------------------------------------------
    nq_r30 = ret(nq, 1800)
    zb_r30 = ret(zb, 1800)
    nq_sd = sdroll(nq, 1800, 3600)
    zb_sd30 = sdroll(zb, 1800, 3600)
    big_nq = np.abs(nq_r30) > 1.5 * np.nan_to_num(nq_sd, nan=np.inf)
    big_zb = np.abs(zb_r30) > 1.5 * np.nan_to_num(zb_sd30, nan=np.inf)
    same = np.sign(nq_r30) == np.sign(zb_r30)
    sig = np.where(big_nq & big_zb & same & (nq_r30 > 0) & rth & valid, -1,
                   np.where(big_nq & big_zb & same & (nq_r30 < 0) & rth & valid,
                            1, 0))
    for hold in (15, 30, 60):
        add(f"C_BONDDIV_t{hold}", run_grid(sig, hold))
    print(f"[C] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- D. MACROGATE flow-follow ------------------------------------------
    ima = pd.Series(ivs).rolling(600).sum().to_numpy()
    ias = pd.Series(np.abs(ivs)).rolling(1800).mean().to_numpy() * 60
    burst = np.where((ima > 3 * np.nan_to_num(ias, nan=np.inf)) & rth & valid, 1,
                     np.where((ima < -3 * np.nan_to_num(ias, nan=np.inf)) & rth
                              & valid, -1, 0))
    zb_trend = ret(zb, 3600)
    riskon = zb_trend < 0                     # bonds falling = risk appetite
    sig = np.where(riskon, burst, 0)
    for hold in (15, 30):
        add(f"D_GATEriskon_t{hold}", run_grid(sig, hold))
    sig = np.where(~riskon, burst, 0)
    add("D_GATEriskoff_t30", run_grid(sig, 30))
    print(f"[D] done ({time.time()-t0:.0f}s)", flush=True)

    out = pd.DataFrame(rows).sort_values("sel_usd_wk", ascending=False)
    out.to_csv("research/round34_macro.csv", index=False)
    cols = ["name", "sel_usd_wk", "sel_tr_wk", "sel_per", "bl_usd_wk",
            "bl_tr_wk", "bl_per", "bl_worst", "bl_pos"]
    print(f"\n{len(out)} configs ({time.time()-t0:.0f}s)")
    print("\nALL by SELECT (blind Jun 1-18):")
    print(out[cols].to_string(index=False))
    ok = out[(out.sel_usd_wk > 0) & (out.bl_usd_wk > 0)]
    print(f"\nboth-positive: {len(ok)}")
    print(ok.sort_values("bl_usd_wk", ascending=False)[cols]
          .head(12).to_string(index=False))


if __name__ == "__main__":
    main()
