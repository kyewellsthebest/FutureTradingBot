"""
NAAIM Exposure Index (smart-money positioning) — 20 yrs of weekly history
+ AAII-NAAIM divergence + OOS filter test.

NAAIM USE Index ranges from -200 (max leveraged short) to +200 (max
leveraged long), where 0 = flat. Weekly survey of professional active
investment managers' equity exposure.

The big play: AAII (retail) vs NAAIM (pros) divergence:
  retail bull + pros bear = retail buying the top → SHORT setup
  retail bear + pros bull = retail capitulating, pros accumulating → LONG setup

Builds:
  data/naaim_features.csv.gz
  + tests filter/sizing on bot OOS trades
  + tests AAII-NAAIM divergence as composite feature

Plus: validate NAAIM against forward S&P returns to confirm signal quality.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = PROJECT_ROOT / "data" / "research_data" / "naaim.xlsx"
OUT = PROJECT_ROOT / "data" / "naaim_features.csv.gz"
AAII_PATH = PROJECT_ROOT / "data" / "aaii_features.csv.gz"
CACHE = PROJECT_ROOT / "data" / "scenarios_trades_cache.json"
VAL = PROJECT_ROOT / "data" / "validation_results.json"


def load_naaim() -> pd.DataFrame:
    df = pd.read_excel(SRC, sheet_name=0)
    df["date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df = df.rename(columns={
        "NAAIM Number": "naaim",
        "Mean/Average": "naaim_mean",
        "Most Bearish Response": "naaim_min",
        "Most Bullish Response": "naaim_max",
        "Standard Deviation": "naaim_std",
        "Quart 1 (25% at/below)": "naaim_q1",
        "Quart 2 (median)": "naaim_med",
        "Quart 3 (25% at/above)": "naaim_q3",
        "S&P 500": "spx_close",
    })
    df = df[["date", "naaim", "naaim_mean", "naaim_min", "naaim_max",
             "naaim_std", "naaim_q1", "naaim_med", "naaim_q3", "spx_close"]]
    df = df.dropna(subset=["naaim"]).sort_values("date").reset_index(drop=True)
    # Drop duplicates (the file has a couple at the bottom)
    df = df.drop_duplicates(subset=["date"], keep="first")
    return df


def main():
    print("=" * 76)
    print("NAAIM Exposure Index + AAII divergence — OOS filter test")
    print("=" * 76)

    df = load_naaim()
    print(f"\n  {len(df):,} weekly obs   {df['date'].min().date()} → {df['date'].max().date()}")
    print(f"  Recent: NAAIM={df.iloc[-1]['naaim']:.1f}  most-bearish={df.iloc[-1]['naaim_min']:.0f}  "
          f"most-bullish={df.iloc[-1]['naaim_max']:.0f}  spread={df.iloc[-1]['naaim_max']-df.iloc[-1]['naaim_min']:.0f}")
    print(f"  Range: min={df['naaim'].min():.1f}  max={df['naaim'].max():.1f}  "
          f"mean={df['naaim'].mean():.1f}  std={df['naaim'].std():.1f}")

    # Build features
    df["naaim_z52w"] = (
        (df["naaim"] - df["naaim"].rolling(52, min_periods=20).mean()) /
        df["naaim"].rolling(52, min_periods=20).std()
    )
    df["naaim_4w_ma"] = df["naaim"].rolling(4, min_periods=2).mean()
    df["naaim_change_4w"] = df["naaim"] - df["naaim"].shift(4)
    df["naaim_dispersion"] = df["naaim_max"] - df["naaim_min"]   # disagreement among managers

    # Forward-fill weekly to daily
    df_d = df.set_index("date")
    daily = pd.date_range(df_d.index.min(), df_d.index.max() + pd.Timedelta(days=10), freq="D")
    naaim_daily = df_d.reindex(daily).ffill()
    naaim_daily.to_csv(OUT, compression="gzip")
    print(f"\n  Wrote -> {OUT.relative_to(PROJECT_ROOT)}  ({OUT.stat().st_size/1024:.0f} KB)")

    # Sanity check: NAAIM as predictor of forward SPX returns
    print(f"\n[ Sanity check: NAAIM regime vs forward SPX returns ]")
    df["spx_4w_fwd"] = df["spx_close"].pct_change(4).shift(-4)
    df["regime"] = pd.cut(df["naaim"],
                          bins=[-300, 25, 50, 75, 100, 300],
                          labels=["v.bearish<25", "bearish<50", "neutral", "bullish>75", "v.bullish>100"])
    print(f"  {'regime':<20} {'n':>5}  {'avg 4w fwd SPX %':>20}")
    for r, sub in df.groupby("regime", observed=True):
        avg = sub["spx_4w_fwd"].mean() * 100
        n = len(sub)
        print(f"  {str(r):<20} {n:>5}  {avg:>18.2f}%")

    # ---- OOS filter test ----
    val = json.loads(VAL.read_text())
    active = {n for n, s in val["signals"].items() if s.get("recommended")}
    cache = json.loads(CACHE.read_text())
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
    tdf = pd.DataFrame(taken)
    tdf["ts"] = pd.to_datetime(tdf["ts"]).dt.tz_localize(None)
    tdf["date_only"] = tdf["ts"].dt.normalize()

    naaim_d = naaim_daily.copy()
    naaim_d.index = naaim_d.index.tz_localize(None) if naaim_d.index.tz else naaim_d.index
    aaii = pd.read_csv(AAII_PATH).rename(columns={"Unnamed: 0": "date"})
    aaii["date"] = pd.to_datetime(aaii["date"])
    aaii = aaii.set_index("date").sort_index()
    if aaii.index.tz is not None:
        aaii.index = aaii.index.tz_localize(None)

    m = pd.merge_asof(tdf.sort_values("ts"), naaim_d, left_on="date_only", right_index=True, direction="backward")
    m = pd.merge_asof(m, aaii, left_on="date_only", right_index=True, direction="backward",
                      suffixes=("", "_aaii"))
    m["pnl"] = m["pts"] * 10.0 - 10.0
    base = m["pnl"].sum()
    print(f"\n  BASELINE: $+{base:,.0f}  (n={len(m)})")

    # AAII-NAAIM divergence: build a composite "smart vs retail" score
    # AAII bull-bear (retail mood) vs NAAIM (smart money exposure)
    # When AAII bull-z high but NAAIM low → retail bullish, pros not → top
    # When AAII bear-z high but NAAIM high → retail bearish, pros long → bottom
    m["divergence"] = m["bull_z52w"] - m["naaim_z52w"]   # >0 = retail too bullish vs pros
    print(f"\n[ Filter / sizing tests ]\n")
    tests = [
        ("BOOST 1.5x SHORTs when NAAIM > 90 (pros leveraged long → top likely)",
            None, lambda x: np.where((x["side"]=="SHORT") & (x["naaim"]>90), 1.5, 1.0)),
        ("BOOST 1.5x LONGs when NAAIM < 30 (pros bearish → capitulation bottom)",
            None, lambda x: np.where((x["side"]=="LONG") & (x["naaim"]<30), 1.5, 1.0)),
        ("BOOST 1.5x LONGs when NAAIM-z52w < -1.5",
            None, lambda x: np.where((x["side"]=="LONG") & (x["naaim_z52w"]<-1.5), 1.5, 1.0)),
        ("BOOST 1.5x SHORTs when NAAIM-z52w > +1.5",
            None, lambda x: np.where((x["side"]=="SHORT") & (x["naaim_z52w"]>1.5), 1.5, 1.0)),
        ("BOOST 1.5x SHORTs on AAII-NAAIM divergence > +1.5 (retail FOMO at top)",
            None, lambda x: np.where((x["side"]=="SHORT") & (x["divergence"]>1.5), 1.5, 1.0)),
        ("BOOST 1.5x LONGs on AAII-NAAIM divergence < -1.5 (retail capitulation, pros buying)",
            None, lambda x: np.where((x["side"]=="LONG") & (x["divergence"]<-1.5), 1.5, 1.0)),
        ("Skip LONGs when NAAIM > 90 (overbought)",
            lambda x: ~((x["side"]=="LONG") & (x["naaim"]>90)), None),
        ("BOOST 1.5x LONGs when NAAIM increasing fast (4w change > +30)",
            None, lambda x: np.where((x["side"]=="LONG") & (x["naaim_change_4w"]>30), 1.5, 1.0)),
    ]

    results = []
    for label, skip_fn, mult_fn in tests:
        x = m.copy()
        if skip_fn is not None:
            x = x[skip_fn(x)]
            pnl = x["pnl"].sum()
        else:
            x["mult"] = mult_fn(x)
            x["pnl_x"] = x["pnl"] * x["mult"]
            pnl = x["pnl_x"].sum()
        delta = pnl - base
        marker = "✓" if delta > 100 else ("✗" if delta < -100 else "—")
        results.append({"label": label, "pnl": pnl, "delta": delta, "mark": marker})
        print(f"  {marker}  {label}")
        print(f"     net=${pnl:>+9,.0f}  Δ=${delta:>+8,.0f}  ({(delta/base)*100:+.2f}%)")

    # Composite stack of best NAAIM/divergence signals
    print(f"\n[ Best NAAIM-only stack ]")
    best = [r for r in results if r["delta"] > 100]
    if best:
        x = m.copy()
        x["mult"] = 1.0
        for label, skip_fn, mult_fn in tests:
            if any(r["label"] == label and r["delta"] > 100 for r in results):
                if mult_fn is not None:
                    x["mult"] = np.maximum(x["mult"], mult_fn(x))
        x["mult"] = x["mult"].clip(upper=2.0)   # cap 2x to keep variance reasonable
        x["pnl_x"] = x["pnl"] * x["mult"]
        combined = x["pnl_x"].sum()
        n_boost = (x["mult"] > 1.0).sum()
        print(f"  Combined NAAIM stack (cap 2x): ${combined:+,.0f}  Δ ${combined-base:+,.0f}  "
              f"({(combined-base)/base*100:+.2f}%)  ({n_boost} boosted)")


if __name__ == "__main__":
    main()
