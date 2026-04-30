"""
FRED macro feature builder + filter test against the bot's existing OOS trades.

Reads the 11 FRED CSVs the user provided (Apr 2021 → Apr 2026), aligns them
on a daily index, computes derived regime features, and tests whether they
add edge as filters or sizing signals on the bot's existing 40-pattern OOS
trade list (1,881 trades, 2024-01 → 2026-04).

Features built (all forward-filled across weekends/holidays):

  level features:
    vix, vxv, dgs10, sofr, iorb, effr, dxy, hy_spread, wti, t10y2y, t10y3m

  derived:
    vix_term_struct = vix - vxv         (pos = backwardation = panic = potential buy)
    vix_regime      = bins {<15 calm, 15-20 normal, 20-30 elevated, >30 panic}
    sofr_iorb       = sofr - iorb        (pos = repo stress)
    real_rate_proxy = dgs10 - 2.0        (rough real yield, 2% inflation expectation)
    vix_5d_change   = pct change vs 5 trading days ago
    hy_5d_change    = HY spread blowout indicator
    dxy_5d_change   = dollar momentum
    yc_inverted     = T10Y2Y < 0
    yc_steepening   = T10Y2Y - T10Y2Y_20d_ago  > 0   (recession confirmation when from inversion)

Output:
    data/macro_features.csv.gz                — daily macro panel
    stdout                                    — filter test results
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRED = PROJECT_ROOT / "data" / "research_data" / "fred"
OUT = PROJECT_ROOT / "data" / "macro_features.csv.gz"
CACHE = PROJECT_ROOT / "data" / "scenarios_trades_cache.json"
VAL = PROJECT_ROOT / "data" / "validation_results.json"


def _load(name: str, col: str) -> pd.Series:
    df = pd.read_csv(FRED / f"{name}.csv", parse_dates=["observation_date"])
    df = df.rename(columns={"observation_date": "date"})
    s = pd.to_numeric(df.set_index("date")[col], errors="coerce")
    return s.rename(name.lower())


def main():
    print("=" * 76)
    print("FRED MACRO FEATURE BUILDER + bot-trade filter test")
    print("=" * 76)

    # ---- 1. Load + align ----
    print("\n[1/4] Loading 11 FRED series ...")
    series = {
        "vix":       _load("VIX",       "VIXCLS"),
        "vxv":       _load("VXV",       "VXVCLS"),
        "dgs10":     _load("DGS10",     "DGS10"),
        "sofr":      _load("SOFR",      "SOFR"),
        "iorb":      _load("IORB",      "IORB"),
        "effr":      _load("EFFR",      "EFFR"),
        "dxy":       _load("DXY",       "DTWEXBGS"),
        "hy_spread": _load("HY_SPREAD", "BAMLH0A0HYM2"),
        "wti":       _load("WTI",       "DCOILWTICO"),
        "t10y2y":    _load("T10Y2Y",    "T10Y2Y"),
        "t10y3m":    _load("T10Y3M",    "T10Y3M"),
    }
    for k, s in series.items():
        print(f"  {k:<10} {len(s):>5} rows  {s.dropna().index.min().date()} → "
              f"{s.dropna().index.max().date()}")

    df = pd.concat(series.values(), axis=1, keys=series.keys()).sort_index()
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df.ffill()   # forward-fill weekends/holidays
    print(f"\n  unified panel: {len(df):,} daily rows  cols: {len(df.columns)}")

    # ---- 2. Derived features ----
    print("\n[2/4] Building derived features ...")
    df["vix_term_struct"]  = df["vix"] - df["vxv"]
    df["sofr_iorb"]        = df["sofr"] - df["iorb"]
    df["real_rate_proxy"]  = df["dgs10"] - 2.0   # rough proxy
    df["vix_5d_change"]    = df["vix"].pct_change(5)
    df["hy_5d_change"]     = df["hy_spread"].pct_change(5)
    df["dxy_5d_change"]    = df["dxy"].pct_change(5)
    df["dxy_20d_change"]   = df["dxy"].pct_change(20)
    df["yc_inverted"]      = (df["t10y2y"] < 0).astype(int)
    df["yc_change_20d"]    = df["t10y2y"] - df["t10y2y"].shift(20)
    df["wti_5d_change"]    = df["wti"].pct_change(5)
    # Regime bins
    df["vix_regime"] = pd.cut(df["vix"], bins=[0, 15, 20, 30, 100],
                              labels=["calm", "normal", "elevated", "panic"]).astype(str)

    df.to_csv(OUT, compression="gzip")
    print(f"  Wrote -> {OUT.relative_to(PROJECT_ROOT)}  ({OUT.stat().st_size/1024:.0f} KB)")

    # ---- 3. Test as filters on bot's OOS trades ----
    print("\n[3/4] Testing macro filters against existing OOS trades ...")
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

    # gate
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

    # Merge macro on trade dates
    tdf = pd.DataFrame(taken)
    tdf["ts"] = pd.to_datetime(tdf["ts"]).dt.tz_localize(None)
    tdf["date_only"] = tdf["ts"].dt.normalize()
    macro = df.copy(); macro.index = macro.index.tz_localize(None) if macro.index.tz else macro.index
    merged = pd.merge_asof(tdf.sort_values("ts"), macro.sort_index(),
                            left_on="date_only", right_index=True, direction="backward")

    contracts = 5; dpp = contracts * 2.0; comm = contracts * 2.0
    merged["pnl"] = merged["pts"] * dpp - comm
    base_pnl = merged["pnl"].sum()
    base_wr = (merged["pts"] > 0).mean()
    base_n = len(merged)
    print(f"\n  BASELINE (all OOS trades):")
    print(f"    n={base_n}  WR={base_wr*100:.1f}%  net=${base_pnl:+,.0f}")

    # ---- 4. Filter tests ----
    print(f"\n[4/4] Filter tests (each is independent — picks ones that ADD value):\n")
    tests = [
        ("Skip when VIX > 30 (panic — wide stops, slippage risk)",
            ~(merged["vix"] > 30)),
        ("Skip LONGs when HY spread widening fast (>5% in 5d)",
            ~((merged["side"] == "LONG") & (merged["hy_5d_change"] > 0.05))),
        ("Skip LONGs when VIX backwardated (vix > vxv) — already in panic",
            ~((merged["side"] == "LONG") & (merged["vix_term_struct"] > 0))),
        ("BOOST 1.5x when VIX backwardated (panic = mean-revert)",
            None),  # special: sizing rather than skip
        ("Skip LONGs when DXY surging (>2% in 20d) — risk-off signal",
            ~((merged["side"] == "LONG") & (merged["dxy_20d_change"] > 0.02))),
        ("Skip when SOFR-IORB > 0.05 (repo stress)",
            ~(merged["sofr_iorb"] > 0.05)),
        ("Skip LONGs when yield curve inversion deepening",
            ~((merged["side"] == "LONG") & (merged["yc_change_20d"] < -0.10))),
        ("Skip when VIX regime = 'panic'",
            ~(merged["vix_regime"] == "panic")),
        ("BOOST 1.5x SHORTs when HY spread spiking",
            None),
    ]

    results = []
    for label, mask in tests:
        if mask is None:
            # Sizing test
            if "VIX backwardated" in label:
                m = merged.copy()
                m["mult"] = np.where(m["vix_term_struct"] > 0, 1.5, 1.0)
                m["pnl_x"] = m["pnl"] * m["mult"]
                pnl = m["pnl_x"].sum(); n = len(m); wr = (m["pts"] > 0).mean()
            else:
                m = merged.copy()
                m["mult"] = np.where(
                    (m["side"] == "SHORT") & (m["hy_5d_change"] > 0.03), 1.5, 1.0)
                m["pnl_x"] = m["pnl"] * m["mult"]
                pnl = m["pnl_x"].sum(); n = len(m); wr = (m["pts"] > 0).mean()
        else:
            m = merged[mask]
            pnl = m["pnl"].sum(); n = len(m); wr = (m["pts"] > 0).mean() if len(m) else 0
        delta = pnl - base_pnl
        marker = "✓" if delta > 100 else ("✗" if delta < -100 else "—")
        results.append({"label": label, "n": n, "wr": wr, "pnl": pnl, "delta": delta, "mark": marker})
        print(f"  {marker}  {label}")
        print(f"     n={n:>4}  WR={wr*100:>5.1f}%  net=${pnl:>+9,.0f}  Δ=${delta:>+8,.0f}")

    # Best stack: combine all positive filters
    print(f"\n  --- BEST STACK (all positive filters combined) ---")
    pos = [r for r in results if r["delta"] > 100 and r["mark"] == "✓"]
    if pos:
        for r in pos:
            print(f"    + {r['label']}  (Δ ${r['delta']:+,.0f})")

    print(f"\n  Verdict:")
    n_pos = sum(1 for r in results if r["delta"] > 100)
    n_neg = sum(1 for r in results if r["delta"] < -100)
    print(f"    {n_pos} filters add edge   {n_neg} filters hurt   "
          f"{len(results)-n_pos-n_neg} are noise")


if __name__ == "__main__":
    main()
