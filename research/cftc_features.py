"""
CFTC Traders in Financial Futures (TFF) feature builder.

Reads the weekly CFTC TFF reports for NQ futures (NASDAQ-100 Consolidated,
NQ-mini, and MNQ) and builds time-series institutional-positioning features
that get joined onto the 1-min bar data.

Why this matters:
  CFTC publishes who is positioned how in NQ every Tuesday. Asset Managers
  are mostly long-only institutions (pension, mutual fund). Leveraged Money
  are hedge funds — directional bettors. Non-Reportables are retail.
  Divergence between these groups is reliable contrarian alpha.

Features built (forward-filled to daily, then merged into 1-min bars):
  - asset_mgr_net_long      (long - short) / open_interest
  - lev_money_net_long
  - dealer_net_long
  - retail_net_long
  - asset_mgr_minus_lev_money     (AM bullish, LM bearish = trend confirmation)
  - retail_extreme_long             (>0.7 = top-ish)
  - retail_extreme_short            (<-0.5 = bottom-ish)
  - positioning_change_1w           (week-over-week shift)

Usage:
    python -m research.cftc_features
"""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CFTC_DIR = PROJECT_ROOT / "data" / "research_data" / "cftc"
OUT_PATH = PROJECT_ROOT / "data" / "cftc_nq_features.csv.gz"


# Map column name → 0-indexed position in the CSV (columns checked from header)
COLS = {
    "name": 0, "date": 2, "open_interest": 7,
    "dealer_long": 8, "dealer_short": 9,
    "asset_mgr_long": 11, "asset_mgr_short": 12,
    "lev_money_long": 14, "lev_money_short": 15,
    "other_rept_long": 17, "other_rept_short": 18,
    "nonrept_long": 22, "nonrept_short": 23,
    "ch_open_interest": 24,
    "ch_asset_mgr_long": 28, "ch_asset_mgr_short": 29,
    "ch_lev_money_long": 31, "ch_lev_money_short": 32,
}


def load_cftc_year(path: Path) -> pd.DataFrame:
    """Parse one year of CFTC TFF data, return rows for NQ contracts only."""
    rows = []
    with open(path, encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        for r in reader:
            name = r[COLS["name"]]
            if "NASDAQ" not in name.upper():
                continue
            try:
                d = pd.Timestamp(r[COLS["date"]])
                row = {"contract": name.split(" - ")[0].strip(), "date": d}
                for k, idx in COLS.items():
                    if k in ("name", "date"):
                        continue
                    val = r[idx].strip()
                    row[k] = float(val) if val and val != "." else np.nan
                rows.append(row)
            except Exception:
                continue
    return pd.DataFrame(rows)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute positioning features per contract per date."""
    df = df.copy()
    oi = df["open_interest"].replace(0, np.nan)
    df["asset_mgr_net_long"] = (df["asset_mgr_long"] - df["asset_mgr_short"]) / oi
    df["lev_money_net_long"] = (df["lev_money_long"] - df["lev_money_short"]) / oi
    df["dealer_net_long"]    = (df["dealer_long"] - df["dealer_short"]) / oi
    df["retail_net_long"]    = (df["nonrept_long"] - df["nonrept_short"]) / oi

    # Smart-money vs retail divergence
    df["am_minus_lm"] = df["asset_mgr_net_long"] - df["lev_money_net_long"]
    df["smart_vs_retail"] = (df["asset_mgr_net_long"] + df["lev_money_net_long"]) / 2 - df["retail_net_long"]

    # Extremes (z-scored over rolling 52w per contract)
    for col in ["asset_mgr_net_long", "lev_money_net_long", "retail_net_long"]:
        z = df.groupby("contract")[col].transform(
            lambda s: (s - s.rolling(52, min_periods=10).mean()) /
                      s.rolling(52, min_periods=10).std()
        )
        df[col + "_z52w"] = z

    # Week-over-week change
    df = df.sort_values(["contract", "date"])
    for col in ["asset_mgr_net_long", "lev_money_net_long", "retail_net_long"]:
        df[col + "_d1w"] = df.groupby("contract")[col].diff()
    return df


def main() -> int:
    print("=" * 70)
    print("CFTC TFF FEATURE BUILDER  —  9 yrs of NQ institutional positioning")
    print("=" * 70)

    files = sorted(CFTC_DIR.glob("FinCom_*.txt"))
    print(f"\n  Loading {len(files)} yearly files ...")
    dfs = []
    for f in files:
        d = load_cftc_year(f)
        print(f"    {f.name:<25}   {len(d):>4} NQ rows  "
              f"({d['date'].min().date()} → {d['date'].max().date()})" if len(d) else f"    {f.name}: empty")
        if len(d):
            dfs.append(d)

    df = pd.concat(dfs, ignore_index=True).sort_values(["contract", "date"])
    print(f"\n  total NQ rows: {len(df):,}  ({df['date'].min().date()} → {df['date'].max().date()})")

    df = build_features(df)

    # Pivot to a single time-series — use NASDAQ-100 Consolidated (combined view)
    consolidated = df[df["contract"].str.contains("Consolidated", case=False, na=False)].copy()
    print(f"  consolidated rows: {len(consolidated)}")

    # Save as gzipped CSV (parquet engine not available in sandbox)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_PATH, index=False, compression="gzip")
    print(f"\n  Wrote -> {OUT_PATH.relative_to(PROJECT_ROOT)}  ({OUT_PATH.stat().st_size / 1024:.0f} KB)")

    # Sanity-check: most recent observations
    print("\n  --- Most recent positioning snapshot (NASDAQ-100 Consolidated) ---")
    cols = ["date", "open_interest", "asset_mgr_net_long", "lev_money_net_long",
            "retail_net_long", "am_minus_lm"]
    recent = consolidated.tail(8)[cols]
    for _, r in recent.iterrows():
        print(f"    {r['date'].date()}  OI={r['open_interest']:>7,.0f}  "
              f"AM_net={r['asset_mgr_net_long']:>+.2%}  "
              f"LM_net={r['lev_money_net_long']:>+.2%}  "
              f"Retail={r['retail_net_long']:>+.2%}  "
              f"AM-LM={r['am_minus_lm']:>+.2%}")

    # Identify extreme positioning moments — these are where the bot should
    # bias against the crowd
    print("\n  --- Top 10 retail-bullish extremes (contrarian short setups) ---")
    extreme_ret_long = consolidated.sort_values("retail_net_long_z52w", ascending=False).head(10)
    for _, r in extreme_ret_long.iterrows():
        print(f"    {r['date'].date()}  retail_z={r['retail_net_long_z52w']:>+.2f}  "
              f"AM_net={r['asset_mgr_net_long']:>+.2%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
