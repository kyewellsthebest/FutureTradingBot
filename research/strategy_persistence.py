"""
Adaptive brain — STAGE 2b: strategy-quality persistence.

The per-trade meta-model failed: market context does not predict whether
an individual firing wins. But a coarser question remains, and it needs
no prediction — only persistence:

  Are some of the 97 strategies simply, durably worse than others?
  If a strategy's edge in the FIRST half of history carries into the
  SECOND half, then cutting the losers (a decision made on H1 only) will
  improve the book on H2 — genuinely out-of-sample, no hindsight.

This script splits every strategy's trades at the dataset's median date,
measures each half independently, and asks:
  1. does H1 avg-R correlate with H2 avg-R across strategies?
  2. is the ES vs VIX family gap stable across both halves?
  3. if we cut strategies using ONLY H1, is the H2 book better?

A real, persistent gap is a deployable (if modest) win. A non-persistent
one means strategy ranking is noise and pruning is just curve-fitting.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
IN_CSV = DATA / "signal_dataset.csv"
REPORT_OUT = DATA / "strategy_persistence_report.json"

MIN_HALF_N = 20      # min trades per half for the persistence correlation


def maxdd(r: np.ndarray) -> float:
    """Max drawdown of the cumulative-R curve (R units)."""
    if len(r) == 0:
        return 0.0
    curve = np.cumsum(r)
    return float((curve - np.maximum.accumulate(curve)).min())


def book_stats(r: np.ndarray) -> dict:
    if len(r) == 0:
        return {"n": 0, "total_r": 0.0, "avg_r": 0.0, "maxdd_r": 0.0,
                "ret_risk": 0.0}
    dd = maxdd(r)
    return {"n": int(len(r)), "total_r": round(float(r.sum()), 1),
            "avg_r": round(float(r.mean()), 4), "maxdd_r": round(dd, 1),
            "ret_risk": round(float(r.sum() / abs(dd)), 2) if dd < 0 else None}


def main() -> None:
    df = pd.read_csv(IN_CSV, parse_dates=["signal_ts"])
    df = df.sort_values("signal_ts").reset_index(drop=True)

    split = df["signal_ts"].median()
    h1 = df[df["signal_ts"] < split]
    h2 = df[df["signal_ts"] >= split]
    print("=" * 74)
    print("ADAPTIVE BRAIN — STAGE 2b: strategy-quality persistence")
    print("=" * 74)
    print(f"split date : {str(split)[:10]}")
    print(f"H1 trades  : {len(h1):,}   H2 trades : {len(h2):,}")

    # ---- per-strategy stats in each half ----------------------------------
    g1 = h1.groupby("strategy")["r_multiple"].agg(["count", "mean"])
    g2 = h2.groupby("strategy")["r_multiple"].agg(["count", "mean"])
    per = g1.join(g2, lsuffix="_h1", rsuffix="_h2").dropna()
    per = per.join(df.groupby("strategy")["family"].first())

    # ---- (1) persistence correlation --------------------------------------
    elig = per[(per["count_h1"] >= MIN_HALF_N) & (per["count_h2"] >= MIN_HALF_N)]
    pear = float(elig["mean_h1"].corr(elig["mean_h2"]))
    spear = float(elig["mean_h1"].corr(elig["mean_h2"], method="spearman"))
    print(f"\n--- (1) persistence: does H1 strategy edge predict H2? ---")
    print(f"  strategies with >={MIN_HALF_N} trades in both halves: {len(elig)}")
    print(f"  Pearson  corr(H1 avg-R, H2 avg-R) = {pear:+.3f}")
    print(f"  Spearman corr(H1 avg-R, H2 avg-R) = {spear:+.3f}")

    # ---- (2) family gap stability -----------------------------------------
    print(f"\n--- (2) ES vs VIX family avg-R, per half ---")
    fam = {}
    for fname in sorted(df["family"].unique()):
        r1 = h1[h1["family"] == fname]["r_multiple"]
        r2 = h2[h2["family"] == fname]["r_multiple"]
        fam[fname] = {"h1_avg_r": round(float(r1.mean()), 4), "h1_n": int(len(r1)),
                      "h2_avg_r": round(float(r2.mean()), 4), "h2_n": int(len(r2))}
        print(f"  {fname:<6} H1 avg-R={fam[fname]['h1_avg_r']:+.4f} "
              f"(n={fam[fname]['h1_n']:>5})   "
              f"H2 avg-R={fam[fname]['h2_avg_r']:+.4f} (n={fam[fname]['h2_n']:>5})")

    # ---- (3) pruning test: cut on H1, measure on H2 -----------------------
    losers_h1 = set(per[per["mean_h1"] < 0].index)          # data-driven cut
    vix_strats = set(per[per["family"] == "vix"].index)     # structural cut

    h2r = h2["r_multiple"].to_numpy()
    keep_dd = ~h2["strategy"].isin(losers_h1)
    keep_vix = ~h2["strategy"].isin(vix_strats)
    full = book_stats(h2r)
    pruned_dd = book_stats(h2[keep_dd]["r_multiple"].to_numpy())
    pruned_vix = book_stats(h2[keep_vix]["r_multiple"].to_numpy())

    # how often was an H1 decision right on H2?
    cut_and_stayed_bad = sum(1 for s in losers_h1
                             if s in per.index and per.loc[s, "mean_h2"] < 0)
    decision_hit = (cut_and_stayed_bad / len(losers_h1)) if losers_h1 else 0.0

    print(f"\n--- (3) pruning test — cut decided on H1, scored on H2 ---")
    print(f"  strategies cut by H1 avg-R<0 : {len(losers_h1)} of {len(per)}")
    print(f"  of those, still losing in H2 : {cut_and_stayed_bad} "
          f"({decision_hit*100:.0f}%)  [50% = coin flip]")
    print(f"  {'book':<26}{'n':>7}{'total_R':>10}{'avg_R':>10}{'maxDD_R':>10}{'ret/risk':>10}")
    for label, st in (("H2 full (all 97)", full),
                       ("H2 minus H1-losers", pruned_dd),
                       ("H2 minus VIX family", pruned_vix)):
        rr = st["ret_risk"] if st["ret_risk"] is not None else float("nan")
        print(f"  {label:<26}{st['n']:>7}{st['total_r']:>10.1f}"
              f"{st['avg_r']:>+10.4f}{st['maxdd_r']:>10.1f}{rr:>10.2f}")

    persistent = spear > 0.15 and pruned_dd["avg_r"] > full["avg_r"]
    family_stable = (fam.get("vix", {}).get("h1_avg_r", 1) <
                     fam.get("es", {}).get("h1_avg_r", 0)) and \
                    (fam.get("vix", {}).get("h2_avg_r", 1) <
                     fam.get("es", {}).get("h2_avg_r", 0))
    verdict = []
    if persistent:
        verdict.append("strategy quality IS persistent — H1-based pruning helps H2")
    else:
        verdict.append("strategy quality does NOT persist — per-strategy pruning is noise")
    if family_stable:
        verdict.append("VIX-family underperformance is stable across both halves")
    else:
        verdict.append("VIX-family gap is not stable across halves")
    print("\nVERDICT:")
    for v in verdict:
        print(f"  - {v}")

    report = {
        "split_date": str(split)[:10],
        "persistence_pearson": round(pear, 4),
        "persistence_spearman": round(spear, 4),
        "n_eligible_strategies": int(len(elig)),
        "family": fam,
        "n_h1_losers_cut": int(len(losers_h1)),
        "h1_decision_hit_rate_on_h2": round(decision_hit, 3),
        "h2_full": full, "h2_minus_h1_losers": pruned_dd,
        "h2_minus_vix": pruned_vix,
        "strategy_quality_persistent": bool(persistent),
        "vix_gap_stable": bool(family_stable),
        "verdict": verdict,
    }
    REPORT_OUT.write_text(json.dumps(report, indent=2))
    print(f"\nWrote {REPORT_OUT.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
