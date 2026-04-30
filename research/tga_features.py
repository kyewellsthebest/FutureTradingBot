"""
Treasury General Account (TGA) features + AAII sentiment + OOS filter test.

The TGA balance is one of the most-watched but least-known indicators by
retail. When Treasury balance RISES, money is being drained from the
banking system (bond issuance > spending) → tightening conditions →
bearish equity. When TGA FALLS, Treasury is spending → liquidity flowing
back into banks → bullish equity. Daily resolution.

Plus AAII sentiment survey (weekly bullish/bearish %) as contrarian
indicator: extreme bullish + bot-LONG = avoid; extreme bearish + bot-LONG
= confirm.

Builds:
  data/tga_features.csv.gz  — daily TGA panel + AAII forward-filled
  filter test against bot's existing 1,881 OOS trades

Data:
  - DTS_OpCashBal: 4,768 rows daily 2021-04 to 2026-04
  - AAII: 21 weeks (Dec 2025 to Apr 2026) — too little for backtest, but
          we structure the loader for future expansion
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DTS_DIR = PROJECT_ROOT / "data" / "research_data" / "dts"
OUT = PROJECT_ROOT / "data" / "tga_features.csv.gz"
CACHE = PROJECT_ROOT / "data" / "scenarios_trades_cache.json"
VAL = PROJECT_ROOT / "data" / "validation_results.json"


# AAII sentiment — paste from user message. Format: Apr 22 = 2026-04-22.
AAII_RAW = """\
Apr 22|46.0|19.5|34.4
Apr 15|31.7|25.5|42.8
Apr 8|35.7|21.3|43.0
Apr 1|33.6|15.0|51.4
Mar 25|32.1|18.1|49.8
Mar 18|30.4|17.6|52.0
Mar 11|31.9|21.7|46.4
Mar 4|33.1|31.4|35.5
Feb 25|33.2|27.0|39.8
Feb 18|34.5|28.5|36.9
Feb 11|38.5|23.3|38.1
Feb 4|39.7|31.3|29.0
Jan 28|44.4|24.8|30.8
Jan 21|43.2|24.1|32.7
Jan 14|49.5|22.3|28.2
Jan 7|42.5|27.5|30.0
Dec 31|42.0|31.0|27.0
Dec 24|37.4|27.8|34.8
Dec 17|44.1|22.7|33.2
Dec 10|44.6|24.8|30.6
Dec 3|44.3|24.9|30.8
"""


def load_aaii() -> pd.DataFrame:
    rows = []
    # Apr 22 = most recent (2026), Dec 3 = 2025-12-03
    base_year = 2026
    last_month = 99
    for line in AAII_RAW.strip().split("\n"):
        date_s, bull, neut, bear = line.split("|")
        month_str, day = date_s.split()
        m = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
             "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}[month_str]
        # If month rolls back (e.g. Dec after Jan), it's the prior year
        if m > last_month:
            base_year -= 1
        last_month = m
        d = pd.Timestamp(year=base_year, month=m, day=int(day))
        rows.append({"date": d, "aaii_bull": float(bull), "aaii_neut": float(neut),
                      "aaii_bear": float(bear)})
    df = pd.DataFrame(rows).sort_values("date")
    df["aaii_bull_bear"] = df["aaii_bull"] - df["aaii_bear"]
    return df


def load_tga() -> pd.Series:
    """Load Treasury General Account closing balance (daily, 5 yrs)."""
    df = pd.read_csv(DTS_DIR / "DTS_OpCashBal_20210429_20260428.csv",
                     encoding="utf-8-sig")
    # Keep only Closing Balance rows
    df = df[df["Type of Account"] == "Treasury General Account (TGA) Closing Balance"]
    df["date"] = pd.to_datetime(df["Record Date"])
    s = df.set_index("date")["Opening Balance Today"].astype(float)
    s.name = "tga"
    return s.sort_index()


def main():
    print("=" * 76)
    print("TGA + AAII feature builder + OOS filter test")
    print("=" * 76)

    # ---- 1. Load TGA + build features ----
    print("\n[1/3] Loading Treasury General Account (TGA) daily balance ...")
    tga = load_tga()
    print(f"  {len(tga):,} daily rows  {tga.index.min().date()} → {tga.index.max().date()}")
    print(f"  current: ${tga.iloc[-1]:,.0f}M    1-yr avg: ${tga.tail(252).mean():,.0f}M")

    df = pd.DataFrame(tga)
    df["tga_change_1d"] = df["tga"].diff()
    df["tga_change_5d"] = df["tga"].diff(5)
    df["tga_change_20d"] = df["tga"].diff(20)
    df["tga_pct_5d"] = df["tga"].pct_change(5)
    df["tga_pct_20d"] = df["tga"].pct_change(20)
    # 252-day rolling z-score of TGA level (so bot knows when TGA is unusually high/low)
    df["tga_z_1y"] = (
        (df["tga"] - df["tga"].rolling(252, min_periods=60).mean()) /
        df["tga"].rolling(252, min_periods=60).std()
    )
    # Detect "TGA drain" days (big drops) — historically very bullish equity
    df["tga_drain_5d"] = (df["tga_change_5d"] < df["tga_change_5d"].rolling(252, min_periods=60).quantile(0.10)).astype(int)
    df["tga_build_5d"] = (df["tga_change_5d"] > df["tga_change_5d"].rolling(252, min_periods=60).quantile(0.90)).astype(int)

    # ---- 2. AAII sentiment ----
    print("\n[2/3] Loading AAII sentiment (21 weeks Dec 2025 - Apr 2026) ...")
    aaii = load_aaii()
    print(f"  {len(aaii)} weekly observations")
    print(f"  most recent: bull={aaii.iloc[-1]['aaii_bull']:.1f}%  "
          f"bear={aaii.iloc[-1]['aaii_bear']:.1f}%  "
          f"net={aaii.iloc[-1]['aaii_bull_bear']:+.1f}%")
    aaii_d = aaii.set_index("date")
    # Forward-fill AAII to daily (each weekly print is valid for the next 7 days)
    daily_idx = pd.date_range(aaii_d.index.min(), aaii_d.index.max() + pd.Timedelta(days=7), freq="D")
    aaii_daily = aaii_d.reindex(daily_idx).ffill()
    df = df.join(aaii_daily, how="left")

    df.to_csv(OUT, compression="gzip")
    print(f"\n  Wrote -> {OUT.relative_to(PROJECT_ROOT)}  ({OUT.stat().st_size/1024:.0f} KB)")

    # ---- 3. Test as filters against OOS bot trades ----
    print("\n[3/3] Testing TGA + AAII filters on OOS bot trades ...")
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
    df_idx = df.copy(); df_idx.index = df_idx.index.tz_localize(None) if df_idx.index.tz else df_idx.index
    merged = pd.merge_asof(tdf.sort_values("ts"), df_idx,
                            left_on="date_only", right_index=True, direction="backward")
    merged["pnl"] = merged["pts"] * 10.0 - 10.0
    base = merged["pnl"].sum()
    print(f"\n  BASELINE: $+{base:,.0f}  (n={len(merged)})")

    tests = [
        ("BOOST 1.5x LONGs on TGA drain (liquidity injection)",
            None, lambda m: np.where((m["side"]=="LONG") & (m["tga_drain_5d"]==1), 1.5, 1.0)),
        ("Skip LONGs when TGA building (>p90 build)",
            lambda m: ~((m["side"]=="LONG") & (m["tga_build_5d"]==1)), None),
        ("BOOST 1.5x LONGs when TGA z<-1 (Treasury cash unusually low)",
            None, lambda m: np.where((m["side"]=="LONG") & (m["tga_z_1y"]<-1.0), 1.5, 1.0)),
        ("Skip LONGs when TGA z>+1 (Treasury cash unusually high → drain pending)",
            lambda m: ~((m["side"]=="LONG") & (m["tga_z_1y"]>1.0)), None),
        ("Skip LONGs when AAII bullish > 50% (retail euphoria — contrarian)",
            lambda m: ~((m["side"]=="LONG") & (m["aaii_bull"].fillna(0)>50)), None),
        ("BOOST 1.5x LONGs when AAII bearish > 50% (retail despair — contrarian)",
            None, lambda m: np.where((m["side"]=="LONG") & (m["aaii_bear"].fillna(0)>50), 1.5, 1.0)),
        ("BOOST 1.5x SHORTs when AAII bullish > 50%",
            None, lambda m: np.where((m["side"]=="SHORT") & (m["aaii_bull"].fillna(0)>50), 1.5, 1.0)),
    ]

    print()
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
        print(f"  {marker}  {label}")
        print(f"     net=${pnl:>+9,.0f}  Δ=${delta:>+8,.0f}  ({(delta/base)*100:+.2f}%)")


if __name__ == "__main__":
    main()
