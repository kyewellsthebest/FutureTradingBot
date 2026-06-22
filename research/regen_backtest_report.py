"""Regenerate research/backtest_results.md from the saved CSV summaries.

Use this after comprehensive_backtest.py has produced
backtest_summary_60d.csv (and optionally backtest_summary_full.csv).
This regenerates the markdown report using the LATEST verdict
templating in comprehensive_backtest.py, even if the original run was
launched before code edits.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, "/home/user/HFTBot")

import pandas as pd
import importlib
import research.comprehensive_backtest as cb
importlib.reload(cb)


def fake_state_from_row(row) -> cb.VariantState:
    """Build a VariantState shell with .completed_trades populated such
    that summarize() recreates the same numbers."""
    cfg = cb.VariantConfig(name=row["name"])
    vs = cb.VariantState(cfg=cfg)
    # Override summarize via .completed_trades is non-trivial. Easier:
    # just inject summary directly.
    vs._summary = {
        "name":           row["name"],
        "trades":         int(row["trades"]),
        "wr":             float(row["wr"]),
        "pnl":            float(row["pnl"]),
        "per_day":        float(row["per_day"]),
        "per_trade":      float(row["per_trade"]),
        "n_days":         int(row["n_days"]),
        "max_dd":         float(row["max_dd"]),
        "worst_day":      float(row["worst_day"]),
        "best_day":       float(row["best_day"]),
        "trades_per_day": float(row["trades_per_day"]),
        "sharpe":         float(row["sharpe"]),
    }
    return vs


def main():
    out_dir = Path("/home/user/HFTBot/research")
    csv_60 = out_dir / "backtest_summary_60d.csv"
    csv_full = out_dir / "backtest_summary_full.csv"
    if not csv_60.exists():
        print(f"missing {csv_60} — run comprehensive_backtest.py first")
        return
    df60 = pd.read_csv(csv_60)
    states_60 = {row["name"]: fake_state_from_row(row) for _, row in df60.iterrows()}
    # Monkey-patch summarize to use injected _summary
    orig = cb.summarize
    def patched_summarize(vs):
        return vs._summary if hasattr(vs, "_summary") else orig(vs)
    cb.summarize = patched_summarize

    states_full = None
    if csv_full.exists():
        df_full = pd.read_csv(csv_full)
        states_full = {row["name"]: fake_state_from_row(row)
                       for _, row in df_full.iterrows()}

    cb.write_report(states_60, states_full,
                    str(out_dir / "backtest_results.md"))


if __name__ == "__main__":
    main()
