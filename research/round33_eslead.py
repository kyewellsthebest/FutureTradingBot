"""Round 33: ES -> NQ CROSS-MARKET battery — the untouched data dimension,
discovered on disk (data/xasset/ES_1s.parquet, 1-second bars to Jun 18).
Signals from ES on a 1-second grid; NQ entries tick-walked as always,
flat 1 MNQ, $1.50/RT. Select Apr 1 - May 31, blind Jun 1 - 18 (ES data
ends Jun 18 — blind is ~2.5 weeks, flagged).
  A. LEAD: ES 5/15/60-second impulse -> follow NQ immediately
  B. CATCHUP: ES moved, NQ visibly lagging the move -> NQ catch-up
  C. PAIRZ: NQ/ES log-spread z-score stretch -> NQ toward convergence
  D. NONCONF: NQ 30m extreme unconfirmed by ES -> fade NQ
  E. ESFADE: ES 10m overextension -> fade NQ (vs NQ's own fade)
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
    ts, px = z["ts"], z["px"]
    keep = (ts >= SEL_LO.value) & (ts < END.value)
    ts, px = ts[keep], px[keep]
    n = len(ts)
    print(f"NQ ticks Apr-Jun18: {n:,}", flush=True)
    es = pd.read_parquet("data/xasset/ES_1s.parquet")
    es = es[(es["ts"] >= SEL_LO.value) & (es["ts"] < END.value)]
    print(f"ES 1s rows: {len(es):,} ({time.time()-t0:.0f}s)", flush=True)

    # ---- 1-second master grid ----------------------------------------------
    sec0 = SEL_LO.value
    grid = np.arange(sec0, END.value, 1_000_000_000)
    ng = len(grid)
    # ES close ffilled onto grid
    es_sec = ((es["ts"].to_numpy() - sec0) // 1_000_000_000).astype(np.int64)
    es_close = np.full(ng, np.nan)
    es_close[np.clip(es_sec, 0, ng - 1)] = es["close"].to_numpy()
    es_close = pd.Series(es_close).ffill().to_numpy()
    # NQ last price per second
    nq_sec = ((ts - sec0) // 1_000_000_000).astype(np.int64)
    nq_close = np.full(ng, np.nan)
    nq_close[np.clip(nq_sec, 0, ng - 1)] = px
    nq_close = pd.Series(nq_close).ffill().to_numpy()
    valid = ~np.isnan(es_close) & ~np.isnan(nq_close)
    hrs = ((grid // 3_600_000_000_000) % 24).astype(int) + \
        ((grid // 60_000_000_000) % 60).astype(int) / 60.0
    rth = (hrs >= 13.5) & (hrs < 20.9)
    print(f"grid: {ng:,} seconds, valid {valid.mean()*100:.0f}% "
          f"({time.time()-t0:.0f}s)", flush=True)

    # rolling vol of 1s ES returns (60s std, in pts) via pandas
    es_r1 = np.diff(es_close, prepend=es_close[0])
    es_sd = pd.Series(es_r1).rolling(300).std().to_numpy()

    def ret(arr, k):
        r = arr - np.roll(arr, k)
        r[:k] = 0
        return r

    def run_grid(sig_idx, sides, hold_min):
        """sig at grid second i -> NQ market entry via tick walk."""
        out = []
        busy = 0
        hn = int(hold_min * 60_000_000_000)
        for i_, s in zip(sig_idx, sides):
            t = grid[i_] + 1_000_000_000       # signal known at second close
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

    # ---- A. LEAD ------------------------------------------------------------
    for k, ktag in ((5, "5s"), (15, "15s"), (60, "60s")):
        es_rk = ret(es_close, k)
        thr = 4 * np.nan_to_num(es_sd, nan=np.inf) * np.sqrt(k)
        sig = np.where((es_rk > thr) & rth & valid, 1,
                       np.where((es_rk < -thr) & rth & valid, -1, 0))
        li = np.flatnonzero(sig != 0)
        for hold in (1, 5, 15):
            add(f"A_LEAD_{ktag}_t{hold}", run_grid(li, sig[li], hold))
        print(f"[A {ktag}] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- B. CATCHUP ----------------------------------------------------------
    # ES moved k-sec strongly; NQ's own k-sec move (beta-adjusted) is < half
    beta = 1.0   # NQ pts per ES pt ~ (NQ/ES price ratio ~ 3.5) -> use ratio
    ratio = np.nanmedian(nq_close[valid] / es_close[valid])
    for k in (15, 60):
        es_rk = ret(es_close, k)
        nq_rk = ret(nq_close, k)
        thr = 4 * np.nan_to_num(es_sd, nan=np.inf) * np.sqrt(k)
        exp_nq = es_rk * ratio
        lagging = np.abs(nq_rk) < 0.4 * np.abs(exp_nq)
        sig = np.where((es_rk > thr) & lagging & rth & valid, 1,
                       np.where((es_rk < -thr) & lagging & rth & valid, -1, 0))
        li = np.flatnonzero(sig != 0)
        for hold in (1, 5, 15):
            add(f"B_CATCH_{k}s_t{hold}", run_grid(li, sig[li], hold))
    print(f"[B] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- C. PAIRZ ------------------------------------------------------------
    lsp = np.log(nq_close) - np.log(es_close)
    for W, wtag in ((1800, "30m"), (3600, "60m")):
        mu = pd.Series(lsp).rolling(W).mean().to_numpy()
        sd = pd.Series(lsp).rolling(W).std().to_numpy()
        zz = (lsp - mu) / np.where(np.nan_to_num(sd) > 0, sd, np.inf)
        for Z in (2.0, 3.0):
            sig = np.where((zz < -Z) & rth & valid, 1,
                           np.where((zz > Z) & rth & valid, -1, 0))
            li = np.flatnonzero(sig != 0)
            for hold in (5, 15, 30):
                add(f"C_PAIRZ_{wtag}_z{Z}_t{hold}", run_grid(li, sig[li], hold))
        print(f"[C {wtag}] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- D. NONCONF -----------------------------------------------------------
    W = 1800
    nq_hi = pd.Series(nq_close).rolling(W).max().to_numpy()
    nq_lo = pd.Series(nq_close).rolling(W).min().to_numpy()
    es_hi = pd.Series(es_close).rolling(W).max().shift(30).to_numpy()
    es_lo = pd.Series(es_close).rolling(W).min().shift(30).to_numpy()
    at_hi = nq_close >= nq_hi - 0.5
    at_lo = nq_close <= nq_lo + 0.5
    es_conf_hi = es_close >= np.nan_to_num(es_hi, nan=np.inf) - 0.25
    es_conf_lo = es_close <= np.nan_to_num(es_lo, nan=-np.inf) + 0.25
    sig = np.where(at_hi & ~es_conf_hi & rth & valid, -1,
                   np.where(at_lo & ~es_conf_lo & rth & valid, 1, 0))
    # fire only on transition into the state (avoid continuous refiring)
    trans = sig != np.roll(sig, 1)
    sig = np.where(trans, sig, 0)
    li = np.flatnonzero(sig != 0)
    for hold in (5, 15, 30):
        add(f"D_NONCONF_t{hold}", run_grid(li, sig[li], hold))
    print(f"[D] done ({time.time()-t0:.0f}s)", flush=True)

    # ---- E. ESFADE -------------------------------------------------------------
    es_r600 = ret(es_close, 600)
    es_atr = pd.Series(np.abs(ret(es_close, 60))).rolling(1200).mean().to_numpy()
    thr = 6 * np.nan_to_num(es_atr, nan=np.inf)
    sig = np.where((es_r600 < -thr) & rth & valid, 1,
                   np.where((es_r600 > thr) & rth & valid, -1, 0))
    trans = sig != np.roll(sig, 1)
    sig = np.where(trans, sig, 0)
    li = np.flatnonzero(sig != 0)
    for hold in (15, 30):
        add(f"E_ESFADE_t{hold}", run_grid(li, sig[li], hold))
    print(f"[E] done ({time.time()-t0:.0f}s)", flush=True)

    out = pd.DataFrame(rows).sort_values("sel_usd_wk", ascending=False)
    out.to_csv("research/round33_eslead.csv", index=False)
    cols = ["name", "sel_usd_wk", "sel_tr_wk", "sel_per", "bl_usd_wk",
            "bl_tr_wk", "bl_per", "bl_worst", "bl_pos"]
    print(f"\n{len(out)} configs ({time.time()-t0:.0f}s)")
    print("\nALL by SELECT (blind = Jun 1-18 only, ~2.5wk):")
    print(out[cols].to_string(index=False))
    ok = out[(out.sel_usd_wk > 0) & (out.bl_usd_wk > 0)]
    print(f"\nboth-positive: {len(ok)}")
    print(ok.sort_values("bl_usd_wk", ascending=False)[cols]
          .head(15).to_string(index=False))


if __name__ == "__main__":
    main()
