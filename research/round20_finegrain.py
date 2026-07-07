"""Round 20: FINE-GRAIN SYMBOLIC MINING.
15-second and 5-second bars rebuilt from the raw tick archive (per-day
front-contract selection so rolls never mix prices), then the round-13
symbol miner re-run at both grains with two alphabets (imbalance-sign and
volume-tercile conditioned), plus sequence-of-patterns (A then B) at 1m.
Costs per user grant: $1.50 commission + $2 slippage ($3.50/RT total).
Select < 2025-01-01, blind >= 2025-01-01. Support filters per grain.
"""
import os, glob, time
import numpy as np, pandas as pd
import pyarrow.parquet as pq

PT = 2.0
FEES = 1.50
SLIP_PTS_RT = 1.0          # $2/RT at $2/pt
COST = FEES + SLIP_PTS_RT * PT   # $3.50 per round trip
SPLIT = pd.Timestamp("2025-01-01", tz="UTC")
BAR15 = "data/tick/bars_15s.parquet"
BAR5 = "data/tick/bars_5s.parquet"


def build_fine_bars():
    """Build 15s and 5s OHLCV bars from raw ticks, one front contract per day."""
    if os.path.exists(BAR15) and os.path.exists(BAR5):
        return pd.read_parquet(BAR15), pd.read_parquet(BAR5)
    files = sorted(glob.glob("data/tick/raw/NQ*.parquet"))
    parts15, parts5, daycounts = [], [], []
    t0 = time.time()
    for f in files:
        pf = pq.ParquetFile(f)
        for i in range(pf.num_row_groups):
            t = pf.read_row_group(i, columns=["ts", "price", "size"]).to_pandas()
            t = t.sort_values("ts", kind="mergesort")
            ts = t["ts"].to_numpy()
            px = t["price"].to_numpy()
            sz = t["size"].to_numpy(float)
            d = np.sign(np.diff(px, prepend=px[0]))
            day = (ts // 86_400_000_000_000).astype(np.int64)
            dc = pd.DataFrame({"day": day, "n": 1}).groupby("day")["n"].sum()
            daycounts.append(pd.DataFrame({"file": f, "day": dc.index, "n": dc.values}))
            for res_ns, sink in ((15_000_000_000, parts15), (5_000_000_000, parts5)):
                bar = (ts // res_ns) * res_ns
                g = pd.DataFrame({"bar": bar, "px": px, "sz": sz, "imb": d * sz, "ts": ts})
                a = g.groupby("bar").agg(
                    open=("px", "first"), close=("px", "last"),
                    high=("px", "max"), low=("px", "min"),
                    vol=("sz", "sum"), imb=("imb", "sum"), nt=("px", "size"),
                    tsmin=("ts", "min"), tsmax=("ts", "max"))
                a["file"] = f
                sink.append(a.reset_index())
        print(f"{os.path.basename(f)} done ({time.time()-t0:.0f}s)", flush=True)
    # front contract per calendar day = contract with the most ticks that day
    dcs = pd.concat(daycounts).groupby(["day", "file"])["n"].sum().reset_index()
    winner = dcs.sort_values("n").groupby("day")["file"].last()  # max-n file per day

    def merge(parts, path):
        df = pd.concat(parts, ignore_index=True)
        df["day"] = (df["bar"] // 86_400_000_000_000).astype(np.int64)
        df = df[df["file"].values == winner.reindex(df["day"]).values]
        # merge duplicate bars from row-group splits: open from earliest part,
        # close from latest part, extremes/sums combined
        df = df.sort_values(["bar", "tsmin"], kind="mergesort")
        opens = df.groupby("bar")["open"].first()
        df2 = df.sort_values(["bar", "tsmax"], kind="mergesort")
        closes = df2.groupby("bar")["close"].last()
        agg = df.groupby("bar").agg(high=("high", "max"), low=("low", "min"),
                                    vol=("vol", "sum"), imb=("imb", "sum"),
                                    nt=("nt", "sum"))
        agg["open"] = opens; agg["close"] = closes
        agg.index = pd.to_datetime(agg.index, utc=True)
        agg = agg.sort_index()
        agg.to_parquet(path)
        return agg

    b15 = merge(parts15, BAR15)
    b5 = merge(parts5, BAR5)
    print(f"bars built: 15s={len(b15):,} 5s={len(b5):,} ({time.time()-t0:.0f}s)", flush=True)
    return b15, b5


def mine(df, grain_tag, holds_min, bar_sec, support, results):
    """Symbolic 3/4-gram mining with two alphabets on one bar grain."""
    c = df["close"].to_numpy(); o = df["open"].to_numpy()
    h = df["high"].to_numpy(); l = df["low"].to_numpy()
    idx = df.index; n = len(c)
    rng = h - l
    r33, r66 = np.nanpercentile(rng, 33), np.nanpercentile(rng, 66)
    size = np.where(rng <= r33, 0, np.where(rng <= r66, 1, 2))
    direc = np.where(c > o, 1, 0)
    ema = pd.Series(c).ewm(span=20, adjust=False).mean().to_numpy()
    above = np.where(c > ema, 1, 0)
    imb = df["imb"].fillna(0).to_numpy()
    isgn = np.where(imb > 0, 1, 0)
    vol = df["vol"].fillna(0).to_numpy()
    v33, v66 = np.nanpercentile(vol[vol > 0], 33), np.nanpercentile(vol[vol > 0], 66)
    vterc = np.where(vol <= v33, 0, np.where(vol <= v66, 1, 2))
    hrs = np.asarray(idx.hour)
    hb = np.where((hrs >= 13) & (hrs < 21), 1, 0)
    alphabets = {
        "I": ((direc * 24 + size * 8 + above * 4 + isgn * 2 + hb).astype(np.int64), 48),
        "V": ((direc * 36 + size * 12 + above * 6 + vterc * 2 + hb).astype(np.int64), 72),
    }
    sel_mask = idx < SPLIT
    n_sel_wk = max((idx[sel_mask].max() - idx.min()).days / 7.0, 1)
    n_bl_wk = max((idx.max() - SPLIT).days / 7.0, 1)
    bars_per_min = 60 // bar_sec
    for aname, (sym, A) in alphabets.items():
        for L in (3, 4):
            code = np.zeros(n, dtype=np.int64)
            for k in range(L):
                code = code * A + np.roll(sym, k)
            code[:L] = -1
            for hold in holds_min:
                hb_bars = hold * bars_per_min
                fwd = np.roll(c, -hb_bars) - c
                fwd[-hb_bars:] = np.nan
                d = pd.DataFrame({"code": code, "fwd": fwd, "sel": sel_mask})
                d = d[(d.code >= 0) & d.fwd.notna()]
                g_sel = d[d.sel].groupby("code")["fwd"].agg(["mean", "count"])
                g_sel = g_sel[g_sel["count"] >= support]
                if not len(g_sel):
                    continue
                g_sel["score"] = g_sel["mean"].abs() * np.sqrt(g_sel["count"])
                top = g_sel.sort_values("score", ascending=False).head(60)
                g_blind = d[~d.sel].groupby("code")["fwd"].agg(["mean", "count"])
                cap = 10080.0 / hold          # non-overlapping trades per week
                for codev, r in top.iterrows():
                    side = 1 if r["mean"] > 0 else -1

                    def econ(mean_pts, cnt, weeks):
                        if cnt == 0:
                            return 0.0, 0.0, 0.0
                        per = side * mean_pts * PT - COST
                        tr_wk = min(cnt / weeks, cap)
                        return per, tr_wk, per * tr_wk

                    b = g_blind.loc[codev] if codev in g_blind.index else None
                    per_s, trwk_s, wk_s = econ(r["mean"], r["count"], n_sel_wk)
                    per_b, trwk_b, wk_b = (econ(b["mean"], b["count"], n_bl_wk)
                                           if b is not None else (0, 0, 0))
                    results.append({
                        "pattern": f"{grain_tag}{aname}{L}_{codev}_h{hold}",
                        "grain": grain_tag, "alpha": aname, "hold_min": hold,
                        "side": side,
                        "sel_per_trade": round(per_s, 2),
                        "sel_tr_wk": round(trwk_s, 1),
                        "sel_usd_wk": round(wk_s, 0),
                        "blind_per_trade": round(per_b, 2),
                        "blind_tr_wk": round(trwk_b, 1),
                        "blind_usd_wk": round(wk_b, 0),
                    })
            print(f"[{grain_tag}/{aname}/{L}g] mined", flush=True)


def mine_sequences(results):
    """Sequence-of-patterns at 1m: top select 3-grams A -> B within 30 min."""
    from research.midfreq_search import load_bars
    df = load_bars()
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
    hbk = np.where((hrs >= 13) & (hrs < 21), 1, 0)
    sym = (direc * 12 + size * 4 + above * 2 + hbk).astype(np.int64)  # alphabet 24
    A = 24; L = 3
    code = np.zeros(n, dtype=np.int64)
    for k in range(L):
        code = code * A + np.roll(sym, k)
    code[:L] = -1
    sel_mask = np.asarray(idx < SPLIT)
    n_sel_wk = max((idx[sel_mask].max() - idx.min()).days / 7.0, 1)
    n_bl_wk = max((idx.max() - SPLIT).days / 7.0, 1)
    # top 40 select-window codes by |mean fwd 30m| * sqrt(n)
    fwd30 = np.roll(c, -30) - c; fwd30[-30:] = np.nan
    d = pd.DataFrame({"code": code, "fwd": fwd30, "sel": sel_mask})
    d = d[(d.code >= 0) & d.fwd.notna()]
    g = d[d.sel].groupby("code")["fwd"].agg(["mean", "count"])
    g = g[g["count"] >= 800]
    g["score"] = g["mean"].abs() * np.sqrt(g["count"])
    top_codes = g.sort_values("score", ascending=False).head(40).index.to_numpy()
    # occurrence flags of each top code, then pairs A within 30 bars before B
    occ = {cd: (code == cd) for cd in top_codes}
    for hold in (15, 30, 60):
        fwd = np.roll(c, -hold) - c; fwd[-hold:] = np.nan
        for ca in top_codes:
            # "A happened in the last 30 minutes" rolling flag
            a_recent = pd.Series(occ[ca].astype(float)).rolling(30).max().to_numpy() > 0
            for cb in top_codes:
                m = a_recent & occ[cb]
                if m.sum() < 400:
                    continue
                f = fwd[m]; s = sel_mask[m]
                fsel, fbl = f[s], f[~s]
                fsel = fsel[~np.isnan(fsel)]; fbl = fbl[~np.isnan(fbl)]
                if len(fsel) < 300:
                    continue
                side = 1 if fsel.mean() > 0 else -1
                cap = 10080.0 / hold
                per_s = side * fsel.mean() * PT - COST
                trwk_s = min(len(fsel) / n_sel_wk, cap)
                per_b = (side * fbl.mean() * PT - COST) if len(fbl) else 0.0
                trwk_b = min(len(fbl) / n_bl_wk, cap) if len(fbl) else 0.0
                results.append({
                    "pattern": f"SEQ_{ca}->{cb}_h{hold}",
                    "grain": "1m-seq", "alpha": "S", "hold_min": hold,
                    "side": side,
                    "sel_per_trade": round(per_s, 2),
                    "sel_tr_wk": round(trwk_s, 1),
                    "sel_usd_wk": round(per_s * trwk_s, 0),
                    "blind_per_trade": round(per_b, 2),
                    "blind_tr_wk": round(trwk_b, 1),
                    "blind_usd_wk": round(per_b * trwk_b, 0),
                })
        print(f"[SEQ h{hold}] mined", flush=True)


def main():
    t0 = time.time()
    b15, b5 = build_fine_bars()
    results = []
    mine(b15, "F15", holds_min=(5, 15, 30), bar_sec=15, support=4000, results=results)
    mine(b5, "F05", holds_min=(2, 5, 15), bar_sec=5, support=8000, results=results)
    mine_sequences(results)
    out = pd.DataFrame(results).sort_values("sel_usd_wk", ascending=False)
    out.to_csv("research/round20_patterns.csv", index=False)
    print(f"\n{len(out)} candidates ({time.time()-t0:.0f}s)")
    cols = ["pattern", "sel_per_trade", "sel_usd_wk", "sel_tr_wk",
            "blind_per_trade", "blind_usd_wk", "blind_tr_wk"]
    print("\nTOP 25 by SELECT $/wk (blind = untouched verdict):")
    print(out[cols].head(25).to_string(index=False))
    surv = out[(out.sel_usd_wk > 0) & (out.blind_usd_wk > 0)]
    surv = surv.sort_values("blind_usd_wk", ascending=False)
    print(f"\npositive BOTH windows after full costs: {len(surv)}")
    print(surv[cols].head(20).to_string(index=False) if len(surv) else "(none)")


if __name__ == "__main__":
    main()
