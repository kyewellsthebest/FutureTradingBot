"""
macro_v2_test.py — test new findings from pattern miner against bot OOS trades.

Goal: identify which new filters/sizing rules ACTUALLY improve risk-adjusted
return (not just total $). Only those get added to the production stack.

Tests, in order:
  1. WTI 5d change boost (#1 feature in miner)
  2. VIX 5d change momentum (panic-continuation)
  3. Yield-curve 20d change
  4. Pair regime: TGA-z low + WTI low → SHORT
  5. Pair regime: AAII bear-high + TGA-z low → SHORT

Each must pass: P&L improves ≥ 2% AND Sharpe doesn't degrade > 5%.
Otherwise it's just leverage and we skip it.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd

P = Path("/home/user/HFTBot")

cftc = pd.read_csv(P/"data/cftc_nq_features.csv.gz", parse_dates=["date"])
cftc = cftc[cftc["contract"].str.contains("Consolidated", case=False, na=False)].set_index("date").sort_index()
macro = pd.read_csv(P/"data/macro_features.csv.gz", parse_dates=["date"]).set_index("date").sort_index()
tga   = pd.read_csv(P/"data/tga_features.csv.gz", parse_dates=["date"]).set_index("date").sort_index()
aaii  = pd.read_csv(P/"data/aaii_features.csv.gz").rename(columns={"Unnamed: 0":"date"})
aaii["date"] = pd.to_datetime(aaii["date"]); aaii = aaii.set_index("date").sort_index()
naaim = pd.read_csv(P/"data/naaim_features.csv.gz").rename(columns={"Unnamed: 0":"date"})
naaim["date"] = pd.to_datetime(naaim["date"]); naaim = naaim.set_index("date").sort_index()
for d in [cftc, macro, tga, aaii, naaim]:
    d.index = d.index.tz_localize(None) if d.index.tz else d.index

val = json.loads((P/"data/validation_results.json").read_text())
active = {n for n, s in val["signals"].items() if s.get("recommended")}
cache = json.loads((P/"data/scenarios_trades_cache.json").read_text())
test_start = pd.Timestamp("2024-01-01", tz="UTC")
raw = []
for t in cache["trades"]:
    if t["name"] in active:
        t["ts"] = pd.Timestamp(t["ts"])
        if t["ts"] >= test_start: raw.append(t)
raw.sort(key=lambda t: t["ts"])
open_until = pd.Timestamp.min.tz_localize("UTC"); today = None; n_today = 0; taken=[]
for t in raw:
    if today != t["ts"].date(): today = t["ts"].date(); n_today = 0
    if n_today >= 8 or t["ts"] < open_until: continue
    taken.append(t)
    open_until = t["ts"] + pd.Timedelta(minutes=t["max_hold"]*(5 if t["tf"]=="5m" else 1))
    n_today += 1
tdf = pd.DataFrame(taken); tdf["ts"] = pd.to_datetime(tdf["ts"]).dt.tz_localize(None); tdf["date_only"] = tdf["ts"].dt.normalize()
m = pd.merge_asof(tdf.sort_values("ts"), cftc, left_on="date_only", right_index=True, direction="backward")
m = pd.merge_asof(m, macro, left_on="date_only", right_index=True, direction="backward")
m = pd.merge_asof(m, tga,   left_on="date_only", right_index=True, direction="backward")
m = pd.merge_asof(m, aaii,  left_on="date_only", right_index=True, direction="backward", suffixes=("","_a"))
m = pd.merge_asof(m, naaim, left_on="date_only", right_index=True, direction="backward", suffixes=("","_n"))
m["pnl"] = m["pts"] * 10.0 - 10.0

def stats(pnls):
    p = np.asarray(pnls)
    eq = np.cumsum(p) + 50000
    peaks = np.maximum.accumulate(eq)
    dd = (peaks - eq).max()
    sharpe = p.mean()/p.std() if p.std()>0 else 0
    return p.sum(), dd, sharpe

base_pnl, base_dd, base_sh = stats(m["pnl"])
print(f"BASELINE:        P&L=${base_pnl:+,.0f}   maxDD=${base_dd:,.0f}   Sharpe={base_sh:.4f}\n")

# ---- existing v1 stack (from production) ----
m["mult_v1"] = 1.0
m.loc[(m["side"]=="LONG")  & (m["am_minus_lm"] >  0.30), "mult_v1"] = 1.5
m.loc[(m["side"]=="SHORT") & (m["am_minus_lm"] < -0.30), "mult_v1"] = 1.5
m.loc[(m["side"]=="SHORT") & (m["hy_5d_change"] > 0.03), "mult_v1"] = 1.5
m.loc[(m["side"]=="LONG")  & (m["bull_bear_z52w"] < -1.5), "mult_v1"] = 1.5
m.loc[(m["side"]=="SHORT") & (m["naaim"] > 90), "mult_v1"] = 1.5
m["pnl_v1"] = m["pnl"] * m["mult_v1"]
v1_pnl, v1_dd, v1_sh = stats(m["pnl_v1"])
print(f"v1 (current):    P&L=${v1_pnl:+,.0f}   maxDD=${v1_dd:,.0f}   Sharpe={v1_sh:.4f}\n")

# ---- candidate new filters ----
candidates = [
    ("WTI 5d > +5% → boost SHORTs",
     lambda x: ((x["side"]=="SHORT") & (x["wti_5d_change"] >  0.05))),
    ("WTI 5d < -5% → boost LONGs",
     lambda x: ((x["side"]=="LONG")  & (x["wti_5d_change"] < -0.05))),
    ("VIX 5d > +20% → boost SHORTs (panic continuation)",
     lambda x: ((x["side"]=="SHORT") & (x["vix_5d_change"] >  0.20))),
    ("Yield-curve 20d ch < -0.10 → boost SHORTs (curve flattening fast)",
     lambda x: ((x["side"]=="SHORT") & (x["yc_change_20d"] < -0.10))),
    ("Yield-curve 20d ch > +0.10 → boost LONGs (curve steepening)",
     lambda x: ((x["side"]=="LONG")  & (x["yc_change_20d"] >  0.10))),
    ("Pair: TGA-z<-0.5 + WTI<-3% → boost SHORTs",
     lambda x: ((x["side"]=="SHORT") & (x["tga_z_1y"] < -0.5) & (x["wti_5d_change"] < -0.03))),
    ("Pair: AAII-bear>0.45 + TGA-z<-0.5 → boost SHORTs",
     lambda x: ((x["side"]=="SHORT") & (x["bear"] > 0.45) & (x["tga_z_1y"] < -0.5))),
    ("Pair: TGA chg20d > p75 + WTI 5d < 0 → boost LONGs",
     lambda x: ((x["side"]=="LONG") & (x["tga_change_20d"] > x["tga_change_20d"].quantile(0.75))
                                    & (x["wti_5d_change"] < 0))),
]

print(f"{'Filter':<60} {'ΔP&L':>10} {'ΔDD':>9} {'ΔSh':>9} {'Verdict':>10}")
print("-" * 100)
keep = []
for name, fn in candidates:
    mt = m.copy()
    mt["mult"] = m["mult_v1"].copy()
    cond = fn(mt)
    mt.loc[cond, "mult"] = np.maximum(mt.loc[cond, "mult"], 1.5)  # cap at 1.5x even if v1 already triggered
    mt["pnl_x"] = mt["pnl"] * mt["mult"]
    pnl, dd, sh = stats(mt["pnl_x"])
    d_pnl = (pnl - v1_pnl) / v1_pnl * 100
    d_dd  = (dd - v1_dd) / v1_dd * 100
    d_sh  = (sh - v1_sh) / v1_sh * 100
    # Keep if: P&L improves ≥ 1% AND Sharpe doesn't degrade > 5%
    keep_it = d_pnl >= 1.0 and d_sh >= -5.0
    verdict = "✓ KEEP" if keep_it else "✗ skip"
    if keep_it: keep.append((name, fn))
    print(f"  {name[:58]:<60} {d_pnl:>+8.2f}% {d_dd:>+7.2f}% {d_sh:>+7.2f}% {verdict:>10}")

# ---- combine kept filters into a v2 stack ----
print(f"\nKept {len(keep)} new filters. Building v2 stack ...\n")
m["mult_v2"] = m["mult_v1"].copy()
for _, fn in keep:
    cond = fn(m)
    m.loc[cond, "mult_v2"] = np.maximum(m.loc[cond, "mult_v2"], 1.5)
m["mult_v2"] = m["mult_v2"].clip(upper=2.0)  # cap at 2x to keep variance in check
m["pnl_v2"] = m["pnl"] * m["mult_v2"]
v2_pnl, v2_dd, v2_sh = stats(m["pnl_v2"])

print(f"BASELINE:        P&L=${base_pnl:+,.0f}   maxDD=${base_dd:,.0f}   Sharpe={base_sh:.4f}")
print(f"v1 (current):    P&L=${v1_pnl:+,.0f}   maxDD=${v1_dd:,.0f}   Sharpe={v1_sh:.4f}")
print(f"v2 (new stack):  P&L=${v2_pnl:+,.0f}   maxDD=${v2_dd:,.0f}   Sharpe={v2_sh:.4f}")
print(f"\nv2 vs v1:")
print(f"  ΔP&L:    {(v2_pnl-v1_pnl)/v1_pnl*100:+.2f}%")
print(f"  ΔDD:     {(v2_dd-v1_dd)/v1_dd*100:+.2f}%")
print(f"  ΔSharpe: {(v2_sh-v1_sh)/v1_sh*100:+.2f}%")

# multiplier histogram
print(f"\nv2 multiplier distribution:")
for v in sorted(m["mult_v2"].unique()):
    cnt = (m["mult_v2"]==v).sum()
    print(f"  {v:.2f}x → {cnt:>4} trades ({cnt/len(m)*100:.0f}%)")

# Save chosen filter list to a config file the production sim can load
keep_names = [n for n, _ in keep]
out = {"v2_kept_filters": keep_names, "v2_summary": {
    "baseline_pnl": float(base_pnl), "baseline_sharpe": float(base_sh),
    "v1_pnl": float(v1_pnl), "v1_sharpe": float(v1_sh),
    "v2_pnl": float(v2_pnl), "v2_sharpe": float(v2_sh),
    "v2_max_dd": float(v2_dd),
}}
(P/"data/macro_v2_filters.json").write_text(json.dumps(out, indent=2))
print(f"\nWrote -> data/macro_v2_filters.json")
