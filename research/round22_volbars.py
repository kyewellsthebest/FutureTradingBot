"""Round 22: EVENT-TIME (volume bar) mining. Bars close after a fixed
number of contracts trade, not a fixed clock interval — the one bar
construction the symbol miner hasn't seen. Duration tercile replaces the
volume tercile in the alphabet (in event time, *speed* is the information).
De-clustered scoring from round 21 (executable schedules only).
Costs $3.50/RT. Select < 2025-01-01, blind after."""
import time
import numpy as np, pandas as pd

PT = 2.0
COST = 3.50
SPLIT = pd.Timestamp("2025-01-01", tz="UTC")


def build_volume_bars(b5, thresh):
    """Aggregate 5s bars into volume bars of ~thresh contracts."""
    vol = b5["vol"].to_numpy()
    cum = np.cumsum(vol)
    bar_id = (cum // thresh).astype(np.int64)
    g = b5.reset_index(drop=True).assign(vbid=bar_id, tsv=b5.index.asi8)
    a = g.groupby("vbid").agg(open=("open", "first"), close=("close", "last"),
                             high=("high", "max"), low=("low", "min"),
                             vol=("vol", "sum"), t0=("tsv", "first"),
                             t1=("tsv", "last"))
    a["dur"] = (a["t1"] - a["t0"]) / 1e9
    a.index = pd.to_datetime(a["t1"], utc=True)   # bar stamped at close time
    return a


def screen(df, tag, holds_bars, min_sel, results):
    c = df["close"].to_numpy(); o = df["open"].to_numpy()
    h = df["high"].to_numpy(); l = df["low"].to_numpy()
    idx = df.index; n = len(c)
    rng = h - l
    r33, r66 = np.nanpercentile(rng, 33), np.nanpercentile(rng, 66)
    size = np.where(rng <= r33, 0, np.where(rng <= r66, 1, 2))
    direc = np.where(c > o, 1, 0)
    ema = pd.Series(c).ewm(span=20, adjust=False).mean().to_numpy()
    above = np.where(c > ema, 1, 0)
    dur = df["dur"].to_numpy()
    d33, d66 = np.nanpercentile(dur, 33), np.nanpercentile(dur, 66)
    dterc = np.where(dur <= d33, 0, np.where(dur <= d66, 1, 2))
    sym = (direc * 18 + size * 6 + above * 3 + dterc).astype(np.int64)
    A = 36
    sel = np.asarray(idx < SPLIT)
    n_sel_wk = max((idx[sel].max() - idx.min()).days / 7.0, 1)
    n_bl_wk = max((idx.max() - SPLIT).days / 7.0, 1)
    for L in (3, 4):
        code = np.zeros(n, dtype=np.int64)
        for k in range(L):
            code = code * A + np.roll(sym, k)
        code[:L] = -1
        order = np.argsort(code, kind="stable")
        cs = code[order]
        bounds = np.flatnonzero(np.diff(cs)) + 1
        starts = np.concatenate(([0], bounds))
        ends = np.concatenate((bounds, [len(cs)]))
        for hold in holds_bars:
            fwd = np.roll(c, -hold) - c
            valid = np.ones(n, bool); valid[-hold:] = False
            valid &= code >= 0
            scored = []
            for s, e in zip(starts, ends):
                cd = cs[s]
                if cd < 0 or e - s < min_sel:
                    continue
                pos = np.sort(order[s:e])
                pos = pos[valid[pos]]
                kept, last = [], -10**18
                for p in pos:
                    if p >= last + hold:
                        kept.append(p); last = p
                kept = np.asarray(kept)
                if not len(kept):
                    continue
                ksel = kept[sel[kept]]; kbl = kept[~sel[kept]]
                if len(ksel) < min_sel // 4:
                    continue
                m = fwd[ksel].mean()
                scored.append((abs(m) * np.sqrt(len(ksel)), cd, m, ksel, kbl))
            scored.sort(key=lambda x: -x[0])
            for _, cd, msel, ksel, kbl in scored[:40]:
                side = 1 if msel > 0 else -1
                per_s = side * msel * PT - COST
                per_b = side * fwd[kbl].mean() * PT - COST if len(kbl) else 0.0
                results.append({
                    "pattern": f"{tag}{L}_{cd}_hb{hold}",
                    "side": side,
                    "sel_per_trade": round(per_s, 2),
                    "sel_tr_wk": round(len(ksel) / n_sel_wk, 1),
                    "sel_usd_wk": round(per_s * len(ksel) / n_sel_wk, 0),
                    "blind_per_trade": round(per_b, 2),
                    "blind_tr_wk": round(len(kbl) / n_bl_wk, 1),
                    "blind_usd_wk": round(per_b * len(kbl) / n_bl_wk, 0),
                })
        print(f"[{tag}/{L}g] done", flush=True)


def main():
    t0 = time.time()
    b5 = pd.read_parquet("data/tick/bars_5s.parquet")
    results = []
    for thresh in (1000, 3000):
        vb = build_volume_bars(b5, thresh)
        print(f"VB{thresh}: {len(vb):,} bars ({time.time()-t0:.0f}s)", flush=True)
        screen(vb, f"VB{thresh}_", holds_bars=(10, 30), min_sel=400, results=results)
    out = pd.DataFrame(results).sort_values("sel_usd_wk", ascending=False)
    out.to_csv("research/round22_volbars.csv", index=False)
    cols = ["pattern", "sel_per_trade", "sel_usd_wk", "sel_tr_wk",
            "blind_per_trade", "blind_usd_wk", "blind_tr_wk"]
    print(f"\n{len(out)} candidates ({time.time()-t0:.0f}s)")
    print("\nTOP 20 by SELECT $/wk (de-clustered, executable):")
    print(out[cols].head(20).to_string(index=False))
    surv = out[(out.sel_usd_wk > 0) & (out.blind_usd_wk > 0)]
    surv = surv.sort_values("blind_usd_wk", ascending=False)
    print(f"\npositive BOTH windows after $3.50/RT: {len(surv)}")
    print(surv[cols].head(15).to_string(index=False) if len(surv) else "(none)")


if __name__ == "__main__":
    main()
