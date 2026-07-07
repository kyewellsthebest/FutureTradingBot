"""Round 21: DE-CLUSTERED re-screen. Round 20 proved the naive screen is
fooled by overlapping occurrences (same move counted N times). This pass
scores every pattern on NON-OVERLAPPING occurrences only (greedy thin: keep
an occurrence only if >= hold after the last kept one), at 1m, 15s and 5s
grains, both alphabets. What survives this screen IS an executable schedule.
Costs $3.50/RT (user grant). Select < 2025-01-01, blind after."""
import time
import numpy as np, pandas as pd
from research.midfreq_search import load_bars

PT = 2.0
COST = 3.50
SPLIT = pd.Timestamp("2025-01-01", tz="UTC")


def thin_and_score(codes_sorted, order, fwd, valid, hold_bars, sel,
                   min_sel, top_out, tag, hold_min, results):
    """codes_sorted: code value per position in `order` (sorted by code).
    Greedy-thin each code's occurrence list; score select/blind separately."""
    bounds = np.flatnonzero(np.diff(codes_sorted)) + 1
    starts = np.concatenate(([0], bounds))
    ends = np.concatenate((bounds, [len(codes_sorted)]))
    cand = []
    for s, e in zip(starts, ends):
        cd = codes_sorted[s]
        if cd < 0 or e - s < min_sel:
            continue
        pos = np.sort(order[s:e])
        pos = pos[valid[pos]]
        if len(pos) < min_sel:
            continue
        # greedy thin to non-overlapping schedule
        kept = []
        last = -10**18
        for p in pos:
            if p >= last + hold_bars:
                kept.append(p); last = p
        kept = np.asarray(kept)
        ksel = kept[sel[kept]]; kbl = kept[~sel[kept]]
        if len(ksel) < min_sel // 4:
            continue
        cand.append((cd, ksel, kbl))
    # score on de-clustered select occurrences
    scored = []
    for cd, ksel, kbl in cand:
        m = fwd[ksel].mean()
        scored.append((abs(m) * np.sqrt(len(ksel)), cd, m, ksel, kbl))
    scored.sort(key=lambda x: -x[0])
    for _, cd, msel, ksel, kbl in scored[:top_out]:
        side = 1 if msel > 0 else -1
        per_s = side * msel * PT - COST
        per_b = side * fwd[kbl].mean() * PT - COST if len(kbl) else 0.0
        results.append({
            "pattern": f"{tag}_{cd}_h{hold_min}", "hold_min": hold_min,
            "side": side,
            "sel_per_trade": round(per_s, 2), "sel_n": len(ksel),
            "blind_per_trade": round(per_b, 2), "blind_n": len(kbl),
        })


def mine_grain(df, grain_tag, holds_min, bar_sec, min_sel, results):
    c = df["close"].to_numpy(); o = df["open"].to_numpy()
    h = df["high"].to_numpy(); l = df["low"].to_numpy()
    idx = df.index; n = len(c)
    rng = h - l
    r33, r66 = np.nanpercentile(rng, 33), np.nanpercentile(rng, 66)
    size = np.where(rng <= r33, 0, np.where(rng <= r66, 1, 2))
    direc = np.where(c > o, 1, 0)
    ema = pd.Series(c).ewm(span=20, adjust=False).mean().to_numpy()
    above = np.where(c > ema, 1, 0)
    hrs = np.asarray(idx.hour)
    hb = np.where((hrs >= 13) & (hrs < 21), 1, 0)
    alphabets = {}
    if "imb" in df.columns:
        imb = df["imb"].fillna(0).to_numpy()
        isgn = np.where(imb > 0, 1, 0)
        alphabets["I"] = ((direc * 24 + size * 8 + above * 4 + isgn * 2 + hb)
                          .astype(np.int64), 48)
    if "vol" in df.columns:
        vol = df["vol"].fillna(0).to_numpy()
        v33, v66 = np.nanpercentile(vol[vol > 0], 33), np.nanpercentile(vol[vol > 0], 66)
        vterc = np.where(vol <= v33, 0, np.where(vol <= v66, 1, 2))
        alphabets["V"] = ((direc * 36 + size * 12 + above * 6 + vterc * 2 + hb)
                          .astype(np.int64), 72)
    if not alphabets:
        alphabets["B"] = ((direc * 12 + size * 4 + above * 2 + hb)
                          .astype(np.int64), 24)
    sel = np.asarray(idx < SPLIT)
    bars_per_min = max(60 // bar_sec, 1)
    for aname, (sym, A) in alphabets.items():
        for L in (3, 4):
            code = np.zeros(n, dtype=np.int64)
            for k in range(L):
                code = code * A + np.roll(sym, k)
            code[:L] = -1
            order = np.argsort(code, kind="stable")
            codes_sorted = code[order]
            for hold in holds_min:
                hbar = hold * bars_per_min
                fwd = np.roll(c, -hbar) - c
                valid = np.ones(n, bool); valid[-hbar:] = False
                valid &= code >= 0
                thin_and_score(codes_sorted, order, fwd, valid, hbar, sel,
                               min_sel, 40, f"{grain_tag}{aname}{L}", hold, results)
            print(f"[{grain_tag}/{aname}/{L}g] done", flush=True)


def main():
    t0 = time.time()
    results = []
    b1 = load_bars()
    mine_grain(b1, "M1", holds_min=(15, 30, 60), bar_sec=60, min_sel=400, results=results)
    b15 = pd.read_parquet("data/tick/bars_15s.parquet")
    mine_grain(b15, "F15", holds_min=(5, 15, 30), bar_sec=15, min_sel=800, results=results)
    b5 = pd.read_parquet("data/tick/bars_5s.parquet")
    mine_grain(b5, "F05", holds_min=(2, 5, 15), bar_sec=5, min_sel=1500, results=results)
    out = pd.DataFrame(results)
    # weekly economics from the de-clustered (executable) schedule
    n_sel_wk = 82.0   # approx; per-pattern counts already non-overlapping
    n_bl_wk = 78.0
    out["sel_usd_wk"] = (out.sel_per_trade * out.sel_n / n_sel_wk).round(0)
    out["blind_usd_wk"] = (out.blind_per_trade * out.blind_n / n_bl_wk).round(0)
    out["sel_tr_wk"] = (out.sel_n / n_sel_wk).round(1)
    out["blind_tr_wk"] = (out.blind_n / n_bl_wk).round(1)
    out = out.sort_values("sel_usd_wk", ascending=False)
    out.to_csv("research/round21_declustered.csv", index=False)
    cols = ["pattern", "sel_per_trade", "sel_usd_wk", "sel_tr_wk",
            "blind_per_trade", "blind_usd_wk", "blind_tr_wk"]
    print(f"\n{len(out)} de-clustered candidates ({time.time()-t0:.0f}s)")
    print("\nTOP 25 by SELECT $/wk (already an executable schedule):")
    print(out[cols].head(25).to_string(index=False))
    surv = out[(out.sel_usd_wk > 0) & (out.blind_usd_wk > 0)]
    surv = surv.sort_values("blind_usd_wk", ascending=False)
    print(f"\npositive BOTH windows after $3.50/RT: {len(surv)}")
    print(surv[cols].head(20).to_string(index=False) if len(surv) else "(none)")


if __name__ == "__main__":
    main()
