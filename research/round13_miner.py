"""Round 13: RAW PATTERN MINER. Every 3-4 bar symbolic pattern in the
data, mined mechanically. Costs per user grant: $1.50 commission,
$2/trade slippage (0.5pt RT). Select 2023-24, blind 2025-26."""
import os
import numpy as np, pandas as pd
from research.midfreq_search import load_bars

FEES = 1.50
SLIP_PTS_RT = 1.0      # 0.5pt entry + 0.5pt exit = $2/RT at $2/pt
PT = 2.0
HOLDS = (15, 30, 60)   # minutes
SPLIT = pd.Timestamp("2025-01-01", tz="UTC")

def main():
    base = load_bars()
    try:
        vf = pd.read_parquet("data/tick/minute_volfeat.parquet")
        df = base.join(vf, how="left")
    except Exception:
        df = base.copy(); df["imb"] = 0.0
    c = df["close"].to_numpy(); o = df["open"].to_numpy()
    h = df["high"].to_numpy(); l = df["low"].to_numpy()
    idx = df.index
    n = len(c)
    # ---- symbolize each 1m bar ----
    rng = h - l
    r33, r66 = np.nanpercentile(rng, 33), np.nanpercentile(rng, 66)
    size = np.where(rng <= r33, 0, np.where(rng <= r66, 1, 2))
    direc = np.where(c > o, 1, 0)
    ema = pd.Series(c).ewm(span=20, adjust=False).mean().to_numpy()
    above = np.where(c > ema, 1, 0)
    imb = df["imb"].fillna(0).to_numpy()
    isgn = np.where(imb > 0, 1, 0)
    hrs = np.asarray(idx.hour)
    hb = np.where((hrs >= 13) & (hrs < 21), 1, 0)     # RTH-ish bucket
    sym = (direc * 24 + size * 8 + above * 4 + isgn * 2 + hb).astype(np.int64)
    A = 48
    # ---- pattern codes (3-gram and 4-gram) ----
    sel_mask = idx < SPLIT
    results = []
    for L, tag in ((3, "P3"), (4, "P4")):
        code = np.zeros(n, dtype=np.int64)
        for k in range(L):
            code = code * A + np.roll(sym, k)          # pattern ending at bar i
        code[:L] = -1
        for hold in HOLDS:
            fwd = (np.roll(c, -hold) - c)              # pts over next `hold` min
            fwd[-hold:] = np.nan
            d = pd.DataFrame({"code": code, "fwd": fwd,
                              "sel": sel_mask})
            d = d[(d.code >= 0) & d.fwd.notna()]
            g_sel = d[d.sel].groupby("code")["fwd"].agg(["mean", "count"])
            g_sel = g_sel[g_sel["count"] >= 1500]      # support in select window
            if not len(g_sel):
                continue
            g_sel["score"] = g_sel["mean"].abs() * np.sqrt(g_sel["count"])
            top = g_sel.sort_values("score", ascending=False).head(60)
            g_blind = d[~d.sel].groupby("code")["fwd"].agg(["mean", "count"])
            for codev, r in top.iterrows():
                side = 1 if r["mean"] > 0 else -1
                b = g_blind.loc[codev] if codev in g_blind.index else None
                # honest per-trade economics with the user's cost grant
                def econ(mean_pts, cnt, weeks):
                    if cnt == 0: return 0, 0, 0
                    per = side * mean_pts * PT - SLIP_PTS_RT * PT - FEES
                    tr_wk = min(cnt / weeks, 10080 / hold / 7)   # non-overlap cap
                    return per, tr_wk, per * tr_wk
                per_s, trwk_s, wk_s = econ(r["mean"], r["count"], 74)
                per_b, trwk_b, wk_b = (econ(b["mean"], b["count"], 78)
                                        if b is not None else (0, 0, 0))
                results.append({
                    "pattern": f"{tag}_{codev}_h{hold}", "hold_min": hold,
                    "side": side,
                    "sel_per_trade": round(per_s, 2),
                    "sel_tr_wk": round(trwk_s, 1),
                    "sel_usd_wk": round(wk_s, 0),
                    "blind_per_trade": round(per_b, 2),
                    "blind_tr_wk": round(trwk_b, 1),
                    "blind_usd_wk": round(wk_b, 0),
                })
        print(f"[{tag}] mined", flush=True)
    out = pd.DataFrame(results).sort_values("sel_usd_wk", ascending=False)
    out.to_csv("research/round13_patterns.csv", index=False)
    print(f"\n{len(out)} candidate patterns (support>=1500, top-60/hold)")
    cols = ["pattern", "sel_per_trade", "sel_usd_wk", "sel_tr_wk",
            "blind_per_trade", "blind_usd_wk", "blind_tr_wk"]
    print("\nTOP 25 by SELECT $/wk (blind = untouched verdict):")
    print(out[cols].head(25).to_string(index=False))
    surv = out[(out.sel_usd_wk > 0) & (out.blind_usd_wk > 0)]
    print(f"\npositive BOTH windows after full costs: {len(surv)}")
    print(surv[cols].head(15).to_string(index=False) if len(surv) else "(none)")

if __name__ == "__main__":
    main()
