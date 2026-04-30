"""
AAII Investor Sentiment Survey — full historical archive + OOS filter test.

User uploaded the AAII archive .xls covering 1987-06 to 2026-04 (2,023
weekly readings). This is the full multi-year history I needed for proper
backtest of contrarian sentiment filters.

Builds features:
  - aaii_bull, aaii_neut, aaii_bear (raw decimals: 0.46 = 46%)
  - aaii_bull_bear (spread)
  - aaii_bull_z52w (52-week rolling z-score of bullish %)
  - aaii_bear_z52w (52-week rolling z-score of bearish %)
  - aaii_extreme_bull (z >= 2: contrarian short signal)
  - aaii_extreme_bear (z <= -2: contrarian long signal)
  - aaii_8w_bull (8-week MA — smooths week-to-week noise)

Then tests as filter/sizing on bot OOS trades (1,881 trades 2024-01 → 2026-04).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = PROJECT_ROOT / "data" / "research_data" / "aaii_sentiment.xls"
OUT = PROJECT_ROOT / "data" / "aaii_features.csv.gz"
CACHE = PROJECT_ROOT / "data" / "scenarios_trades_cache.json"
VAL = PROJECT_ROOT / "data" / "validation_results.json"


def load_aaii() -> pd.DataFrame:
    df = pd.read_excel(SRC, sheet_name="SENTIMENT", skiprows=3)
    df["date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["date"]).copy()
    df["bull"] = pd.to_numeric(df["Bullish"], errors="coerce")
    df["neut"] = pd.to_numeric(df["Neutral"], errors="coerce")
    df["bear"] = pd.to_numeric(df["Bearish"], errors="coerce")
    df = df.dropna(subset=["bull", "bear"]).sort_values("date").reset_index(drop=True)
    df = df[["date", "bull", "neut", "bear"]]
    df["bull_bear"] = df["bull"] - df["bear"]
    return df


def main():
    print("=" * 76)
    print("AAII full-history sentiment + OOS filter test")
    print("=" * 76)

    df = load_aaii()
    print(f"\n  Parsed: {len(df):,} weekly obs   {df['date'].min().date()} → {df['date'].max().date()}")
    print(f"  Recent: bull={df.iloc[-1]['bull']*100:.1f}%  bear={df.iloc[-1]['bear']*100:.1f}%  "
          f"spread={df.iloc[-1]['bull_bear']*100:+.1f}%")

    # 52-week z-scores (1 yr of weekly data)
    for col in ["bull", "bear", "bull_bear"]:
        df[f"{col}_z52w"] = (
            (df[col] - df[col].rolling(52, min_periods=20).mean()) /
            df[col].rolling(52, min_periods=20).std()
        )
    df["bull_8w_ma"] = df["bull"].rolling(8, min_periods=4).mean()
    df["bear_8w_ma"] = df["bear"].rolling(8, min_periods=4).mean()

    # Forward-fill weekly to daily (each Wednesday's print valid for next 7 days)
    df_d = df.set_index("date")
    daily = pd.date_range(df_d.index.min(), df_d.index.max() + pd.Timedelta(days=10), freq="D")
    aaii_daily = df_d.reindex(daily).ffill()
    aaii_daily.to_csv(OUT, compression="gzip")
    print(f"\n  Wrote -> {OUT.relative_to(PROJECT_ROOT)}  ({OUT.stat().st_size/1024:.0f} KB)")

    # ---- OOS test against bot trades ----
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
    open_until = pd.Timestamp.min.tz_localize("UTC"); today = None; n_today = 0; taken = []
    for t in raw:
        if today != t["ts"].date(): today = t["ts"].date(); n_today = 0
        if n_today >= 8 or t["ts"] < open_until: continue
        taken.append(t)
        open_until = t["ts"] + pd.Timedelta(minutes=t["max_hold"]*(5 if t["tf"]=="5m" else 1))
        n_today += 1

    tdf = pd.DataFrame(taken)
    tdf["ts"] = pd.to_datetime(tdf["ts"]).dt.tz_localize(None)
    tdf["date_only"] = tdf["ts"].dt.normalize()
    aaii_d = aaii_daily.copy()
    aaii_d.index = aaii_d.index.tz_localize(None) if aaii_d.index.tz else aaii_d.index
    merged = pd.merge_asof(tdf.sort_values("ts"), aaii_d,
                            left_on="date_only", right_index=True, direction="backward")
    merged["pnl"] = merged["pts"] * 10.0 - 10.0
    base = merged["pnl"].sum()
    print(f"\n  BASELINE: $+{base:,.0f}  (n={len(merged)})  WR={(merged['pts']>0).mean()*100:.1f}%")

    print(f"\n[ AAII filter tests on full historical context ]\n")
    tests = [
        ("Skip LONGs when AAII bull > 50% (raw retail euphoria)",
            lambda m: ~((m["side"]=="LONG") & (m["bull"]>0.50)), None),
        ("BOOST 1.5x SHORTs when AAII bull > 50%",
            None, lambda m: np.where((m["side"]=="SHORT") & (m["bull"]>0.50), 1.5, 1.0)),
        ("BOOST 1.5x LONGs when AAII bear > 50% (retail despair → contrarian buy)",
            None, lambda m: np.where((m["side"]=="LONG") & (m["bear"]>0.50), 1.5, 1.0)),
        ("Skip LONGs when bull-z52w > +1.5 (bullish extreme)",
            lambda m: ~((m["side"]=="LONG") & (m["bull_z52w"]>1.5)), None),
        ("BOOST 1.5x LONGs when bear-z52w > +1.5 (extreme bearish = bottom?)",
            None, lambda m: np.where((m["side"]=="LONG") & (m["bear_z52w"]>1.5), 1.5, 1.0)),
        ("BOOST 1.5x SHORTs when bull-z52w > +1.5",
            None, lambda m: np.where((m["side"]=="SHORT") & (m["bull_z52w"]>1.5), 1.5, 1.0)),
        ("Skip SHORTs when AAII bear-z52w > +1.5 (capitulation done)",
            lambda m: ~((m["side"]=="SHORT") & (m["bear_z52w"]>1.5)), None),
        ("Use bull-bear z52w: BOOST 1.5x LONGs when spread-z < -1.5 (despair)",
            None, lambda m: np.where((m["side"]=="LONG") & (m["bull_bear_z52w"]<-1.5), 1.5, 1.0)),
        ("Use bull-bear z52w: BOOST 1.5x SHORTs when spread-z > +1.5 (euphoria)",
            None, lambda m: np.where((m["side"]=="SHORT") & (m["bull_bear_z52w"]>1.5), 1.5, 1.0)),
    ]
    results = []
    for label, skip_fn, mult_fn in tests:
        m = merged.copy()
        if skip_fn is not None:
            m = m[skip_fn(m)]
            pnl = m["pnl"].sum()
        else:
            m["mult"] = mult_fn(m)
            m["pnl_x"] = m["pnl"] * m["mult"]
            pnl = m["pnl_x"].sum()
        delta = pnl - base
        marker = "✓" if delta > 100 else ("✗" if delta < -100 else "—")
        results.append({"label": label, "pnl": pnl, "delta": delta, "mark": marker})
        print(f"  {marker}  {label}")
        print(f"     net=${pnl:>+9,.0f}  Δ=${delta:>+8,.0f}  ({(delta/base)*100:+.2f}%)")

    # Combined best
    print(f"\n[ Combined stack — only filters with positive Δ > $500 ] ")
    pos = [r for r in results if r["delta"] > 500]
    if pos:
        # Apply combined skip + boost
        m = merged.copy()
        skips = [
            ("bull > 0.50 LONG",   lambda x: ~((x["side"]=="LONG") & (x["bull"]>0.50))),
            ("bull_z52w > 1.5 LONG", lambda x: ~((x["side"]=="LONG") & (x["bull_z52w"]>1.5))),
        ]
        for _, fn in skips:
            m = m[fn(m)]
        m["mult"] = 1.0
        m.loc[(m["side"]=="LONG") & (m["bear"]>0.50), "mult"] = 1.5
        m.loc[(m["side"]=="LONG") & (m["bear_z52w"]>1.5), "mult"] = 1.5
        m.loc[(m["side"]=="SHORT") & (m["bull"]>0.50), "mult"] = 1.5
        m.loc[(m["side"]=="SHORT") & (m["bull_z52w"]>1.5), "mult"] = 1.5
        m.loc[(m["side"]=="SHORT") & (m["bull_bear_z52w"]>1.5), "mult"] = 1.5
        m["pnl_x"] = m["pnl"] * m["mult"]
        combined = m["pnl_x"].sum()
        print(f"\n  Combined AAII stack: ${combined:+,.0f}  (Δ from baseline ${combined-base:+,.0f}, {(combined-base)/base*100:+.2f}%)")


if __name__ == "__main__":
    main()
