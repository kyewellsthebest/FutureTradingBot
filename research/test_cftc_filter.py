"""
Quick test: does CFTC retail-extremes filter improve the existing bot's trades?

Logic:
  1. Load the OOS gated trade list from the cache
  2. For each trade's date, look up the most recent (weekly) CFTC retail
     z-score
  3. Compare bot performance ALL TRADES vs FILTERED (skip when retail is
     extremely bullish for shorts, or extremely bearish for longs).
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE = PROJECT_ROOT / "data" / "scenarios_trades_cache.json"
CFTC = PROJECT_ROOT / "data" / "cftc_nq_features.csv.gz"
VAL = PROJECT_ROOT / "data" / "validation_results.json"


def main():
    print("=" * 72)
    print("CFTC RETAIL-EXTREMES FILTER  —  effect on bot's existing trades")
    print("=" * 72)

    # Load CFTC features (consolidated NQ only)
    df = pd.read_csv(CFTC)
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["contract"].str.contains("Consolidated", case=False, na=False)].sort_values("date")
    df = df[["date", "retail_net_long", "retail_net_long_z52w",
             "asset_mgr_net_long_z52w", "lev_money_net_long_z52w",
             "am_minus_lm"]].copy()
    print(f"  CFTC consolidated rows: {len(df)}")

    # Load whitelist + gated cache, restrict to OOS test window
    val = json.loads(VAL.read_text())
    active = {n for n, s in val["signals"].items() if s.get("recommended")}
    cache = json.loads(CACHE.read_text())
    test_start = pd.Timestamp("2024-01-01", tz="UTC")
    raw = []
    for t in cache["trades"]:
        if t["name"] in active:
            t["ts"] = pd.Timestamp(t["ts"])
            if t["ts"] >= test_start:
                raw.append(t)
    raw.sort(key=lambda t: t["ts"])

    # Apply gate
    open_until = pd.Timestamp.min.tz_localize("UTC")
    today = None; n_today = 0
    taken = []
    for t in raw:
        if today != t["ts"].date():
            today = t["ts"].date(); n_today = 0
        if n_today >= 8 or t["ts"] < open_until: continue
        taken.append(t)
        lockout = t["max_hold"] * (5 if t["tf"] == "5m" else 1)
        open_until = t["ts"] + pd.Timedelta(minutes=lockout)
        n_today += 1
    print(f"  gated OOS trades: {len(taken)}")

    # Forward-fill CFTC weekly to daily by joining as-of
    cftc = df.set_index("date").sort_index()
    trades_df = pd.DataFrame(taken)
    trades_df["ts"] = pd.to_datetime(trades_df["ts"]).dt.tz_localize(None)
    trades_df = trades_df.sort_values("ts")
    merged = pd.merge_asof(
        trades_df, cftc.reset_index(), left_on="ts", right_on="date",
        direction="backward",
    )

    contracts = 5
    dpp = contracts * 2.0
    comm = contracts * 2.0
    merged["pnl"] = merged["pts"] * dpp - comm

    # ALL TRADES baseline
    base_pnl = merged["pnl"].sum()
    base_wr = (merged["pts"] > 0).mean()
    base_n = len(merged)
    print(f"\n  BASELINE (all OOS trades):")
    print(f"    n={base_n}  WR={base_wr*100:.1f}%  net=${base_pnl:+,.0f}")

    # Filter 1: skip LONG trades when retail z > 2.0 (retail bullish extreme)
    f1 = merged[~((merged["side"] == "LONG") & (merged["retail_net_long_z52w"] > 2.0))]
    print(f"\n  FILTER 1: skip LONGs when retail z > 2.0  (retail euphoria)")
    print(f"    n={len(f1)}  WR={(f1['pts']>0).mean()*100:.1f}%  net=${f1['pnl'].sum():+,.0f}")

    # Filter 2: skip SHORT trades when retail z < -2.0
    f2 = merged[~((merged["side"] == "SHORT") & (merged["retail_net_long_z52w"] < -2.0))]
    print(f"\n  FILTER 2: skip SHORTs when retail z < -2.0  (retail despair)")
    print(f"    n={len(f2)}  WR={(f2['pts']>0).mean()*100:.1f}%  net=${f2['pnl'].sum():+,.0f}")

    # Filter 3: combined
    f3 = merged[~(((merged["side"] == "LONG") & (merged["retail_net_long_z52w"] > 2.0)) |
                  ((merged["side"] == "SHORT") & (merged["retail_net_long_z52w"] < -2.0)))]
    print(f"\n  FILTER 3: both filters combined")
    print(f"    n={len(f3)}  WR={(f3['pts']>0).mean()*100:.1f}%  net=${f3['pnl'].sum():+,.0f}")

    # Filter 4: confirmation — TAKE longs only when retail is NOT extreme bullish
    # AND asset managers are not extreme bullish (avoid overcrowded longs)
    f4 = merged[~((merged["side"] == "LONG") &
                  ((merged["retail_net_long_z52w"] > 1.5) |
                   (merged["asset_mgr_net_long_z52w"] > 2.0)))]
    print(f"\n  FILTER 4: skip LONGs when retail z>1.5 OR asset_mgr z>2.0  (crowded)")
    print(f"    n={len(f4)}  WR={(f4['pts']>0).mean()*100:.1f}%  net=${f4['pnl'].sum():+,.0f}")

    # Boost the trades — bigger size when smart money confirms
    # (Asset Mgr long + Leveraged Money short = AM-LM divergence, trends sustain)
    sized = merged.copy()
    sized["size_mult"] = 1.0
    # Boost LONGS when AM-LM divergence is wide and positive
    boost_long = (sized["side"] == "LONG") & (sized["am_minus_lm"] > 0.25)
    sized.loc[boost_long, "size_mult"] = 1.5
    sized["pnl_sized"] = sized["pnl"] * sized["size_mult"]
    print(f"\n  FILTER 5: 1.5x size on LONGs when AM-LM > 0.25 (trend confirmation)")
    print(f"    n={len(sized)}  WR={(sized['pts']>0).mean()*100:.1f}%  "
          f"net=${sized['pnl_sized'].sum():+,.0f}")

    # Best combination: filter 4 + boost on confirmed
    best = merged[~((merged["side"] == "LONG") &
                    ((merged["retail_net_long_z52w"] > 1.5) |
                     (merged["asset_mgr_net_long_z52w"] > 2.0)))]
    best = best.copy()
    best["size_mult"] = np.where(
        (best["side"] == "LONG") & (best["am_minus_lm"] > 0.25), 1.5,
        np.where((best["side"] == "SHORT") & (best["am_minus_lm"] < -0.25), 1.5, 1.0)
    )
    best["pnl_sized"] = best["pnl"] * best["size_mult"]
    print(f"\n  COMBINED: filter overcrowded + 1.5x on AM-LM confirmation")
    print(f"    n={len(best)}  WR={(best['pts']>0).mean()*100:.1f}%  "
          f"net=${best['pnl_sized'].sum():+,.0f}")
    print(f"    vs baseline:  Δ trades={len(best)-base_n:+d}  "
          f"Δ$={best['pnl_sized'].sum()-base_pnl:+,.0f}  "
          f"Δ WR={(best['pts']>0).mean()*100 - base_wr*100:+.1f}pp")


if __name__ == "__main__":
    main()
