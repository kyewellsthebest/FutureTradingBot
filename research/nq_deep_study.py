"""
NQ Deep Study — CONDITIONAL price-behaviour analysis.

The first study (nq_behavior_study.py) measured unconditional stats. This
one measures behaviour CONDITIONED on context — the genuinely deeper read:

  A. Reversal edge SLICED — the PDH/PDL/round-level reversal rate broken
     down by NY hour, first-touch vs repeat, and volatility regime. Tells
     us exactly WHEN and UNDER WHAT CONDITIONS the structural edge is real.

  B. Session sweep behaviour — how often the NY session takes out the
     overnight high/low and then reverses (the liquidity-sweep concept,
     measured properly instead of asserted).

  C. MFE / MAE for fade entries — for a fade entry at a structural level,
     the distribution of maximum favourable vs adverse excursion. This
     sets the optimal stop and target for v14 from data, not guesswork.

  D. Conditional mean-reversion — forward return conditioned on how far
     price has overshot (the snapback strength vs overshoot size).

Output: data/nq_deep_study.json + printed report. Feeds pattern_miner_v14.
"""
from __future__ import annotations

import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from research.local_data_loader import load_intraday_5min, load_daily
from research.signal_generator import _attach_prev_day_levels
from research.indicators import atr

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
logger = logging.getLogger("nq_deep")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                          stream=sys.stdout)
    logger.info("Loading NQ 5-min + daily...")
    m5 = load_intraday_5min("nq")
    daily = load_daily("nq")
    if m5.index.tz is None:
        m5.index = m5.index.tz_localize("UTC")
    if daily.index.tz is None:
        daily.index = daily.index.tz_localize("UTC")
    logger.info(f"  {len(m5):,} 5-min bars")

    ny = m5.index.tz_convert("America/New_York")
    m5 = m5.copy()
    m5["ny_hour"] = ny.hour
    m5["ny_date"] = ny.normalize()
    m5["atr"] = atr(m5["high"], m5["low"], m5["close"], n=14)
    m5["atr_pctile"] = m5["atr"].rolling(2000, min_periods=200).rank(pct=True)

    # Prior-day H/L via the canonical leak-free helper — the SAME one the
    # deployed v6/v11/12/13 features use (signal_generator.py, see its
    # "BUG FIX 2026-05-04" docstring). The earlier code here hand-rolled the
    # map and tz-converted the daily index to NY, which shifted its key back
    # a day and cancelled shift(1) — silently mapping each bar to its OWN
    # day's high (same-day lookahead that inflated the first-touch stats).
    lvl = _attach_prev_day_levels(m5, daily)
    m5["pdh"] = lvl["pdh"].to_numpy()
    m5["pdl"] = lvl["pdl"].to_numpy()

    # overnight H/L = high/low from 18:00 prev day to 09:30 ET (pre-RTH)
    logger.info("Computing overnight ranges...")
    onh_map, onl_map = {}, {}
    for date, grp in m5.groupby("ny_date"):
        pre = grp[grp["ny_hour"] < 9]
        if len(pre):
            onh_map[date] = pre["high"].max()
            onl_map[date] = pre["low"].min()
    m5["onh"] = m5["ny_date"].map(onh_map)
    m5["onl"] = m5["ny_date"].map(onl_map)

    report = {}

    # ===================================================================
    # A. Reversal edge SLICED
    # ===================================================================
    logger.info("Section A: reversal edge sliced by hour / touch# / vol regime")
    closes = m5["close"].values
    highs = m5["high"].values
    lows = m5["low"].values
    hours = m5["ny_hour"].values
    atr_pct = m5["atr_pctile"].values
    dates = m5["ny_date"].values

    def analyse_level(level_col: str, side: str, tol: float = 8.0, fwd: int = 12):
        """side='high' -> resistance, expect down-reversal.
        Returns sliced reversal rates."""
        levels = m5[level_col].values
        by_hour = defaultdict(lambda: [0, 0])      # hour -> [touches, reversals]
        by_touchnum = defaultdict(lambda: [0, 0])  # 1st/2nd/3rd+ touch
        by_volregime = defaultdict(lambda: [0, 0]) # low/mid/high ATR
        touches_today = defaultdict(int)
        total = [0, 0]
        n = len(m5)
        for i in range(n - fwd):
            lv = levels[i]
            if not np.isfinite(lv):
                continue
            touched = highs[i] >= lv - tol and lows[i] <= lv + tol
            if not touched:
                continue
            d = dates[i]
            touches_today[d] += 1
            tnum = min(touches_today[d], 3)
            ap = atr_pct[i]
            vr = ("low" if ap < 0.33 else "high" if ap > 0.66 else "mid") \
                if np.isfinite(ap) else "mid"
            if side == "high":
                reverted = closes[i + 1:i + 1 + fwd].min() < lv - tol
            else:
                reverted = closes[i + 1:i + 1 + fwd].max() > lv + tol
            for bucket, key in ((by_hour, int(hours[i])),
                                  (by_touchnum, tnum),
                                  (by_volregime, vr)):
                bucket[key][0] += 1
                bucket[key][1] += int(reverted)
            total[0] += 1
            total[1] += int(reverted)
        def rate(d):
            return {k: {"touches": v[0],
                          "reversal_rate": round(v[1] / v[0], 3) if v[0] else None}
                      for k, v in sorted(d.items(), key=lambda x: str(x[0]))}
        return {
            "overall": {"touches": total[0],
                          "reversal_rate": round(total[1] / total[0], 3) if total[0] else None},
            "by_ny_hour": rate(by_hour),
            "by_touch_number": rate(by_touchnum),
            "by_vol_regime": rate(by_volregime),
        }

    report["pdh_reversal_sliced"] = analyse_level("pdh", "high")
    report["pdl_reversal_sliced"] = analyse_level("pdl", "low")
    report["onh_reversal_sliced"] = analyse_level("onh", "high")
    report["onl_reversal_sliced"] = analyse_level("onl", "low")

    # log the most useful slices
    for lvl in ["pdh", "pdl", "onh", "onl"]:
        d = report[f"{lvl}_reversal_sliced"]
        best_hr = max(d["by_ny_hour"].items(),
                        key=lambda x: x[1]["reversal_rate"] or 0)
        tn = d["by_touch_number"]
        logger.info(f"  {lvl.upper()}: overall {d['overall']['reversal_rate']}, "
                      f"best hour {best_hr[0]}:00={best_hr[1]['reversal_rate']}, "
                      f"1st-touch={tn.get(1,{}).get('reversal_rate')}")

    # ===================================================================
    # B. Session sweep behaviour
    # ===================================================================
    logger.info("Section B: overnight sweep -> reversal behaviour")
    sweep_stats = {"onh_swept": 0, "onh_swept_then_reversed": 0,
                     "onl_swept": 0, "onl_swept_then_reversed": 0}
    for date, grp in m5.groupby("ny_date"):
        rth = grp[(grp["ny_hour"] >= 9) & (grp["ny_hour"] < 16)]
        if len(rth) < 10:
            continue
        onh = grp["onh"].iloc[0]
        onl = grp["onl"].iloc[0]
        if not (np.isfinite(onh) and np.isfinite(onl)):
            continue
        rth_close = rth["close"].iloc[-1]
        # ONH sweep: RTH high exceeds overnight high
        if rth["high"].max() > onh:
            sweep_stats["onh_swept"] += 1
            # reversed = closed back below the overnight high
            if rth_close < onh:
                sweep_stats["onh_swept_then_reversed"] += 1
        if rth["low"].min() < onl:
            sweep_stats["onl_swept"] += 1
            if rth_close > onl:
                sweep_stats["onl_swept_then_reversed"] += 1
    report["session_sweep"] = {
        "onh_sweep_reversal_rate": round(
            sweep_stats["onh_swept_then_reversed"] / max(sweep_stats["onh_swept"], 1), 3),
        "onl_sweep_reversal_rate": round(
            sweep_stats["onl_swept_then_reversed"] / max(sweep_stats["onl_swept"], 1), 3),
        "raw": sweep_stats,
    }
    logger.info(f"  NY sweeps overnight-high then closes back below: "
                  f"{report['session_sweep']['onh_sweep_reversal_rate']:.1%}")
    logger.info(f"  NY sweeps overnight-low then closes back above:  "
                  f"{report['session_sweep']['onl_sweep_reversal_rate']:.1%}")

    # ===================================================================
    # C. MFE / MAE for fade entries at PDL (LONG) and PDH (SHORT)
    # ===================================================================
    logger.info("Section C: MFE/MAE for fade entries")
    def mfe_mae(level_col: str, side: str, tol: float = 8.0, fwd: int = 18):
        levels = m5[level_col].values
        opens = m5["open"].values
        mfes, maes = [], []
        n = len(m5)
        for i in range(n - fwd - 1):
            lv = levels[i]
            if not np.isfinite(lv):
                continue
            touched = highs[i] >= lv - tol and lows[i] <= lv + tol
            if not touched:
                continue
            entry = opens[i + 1]
            fwd_h = highs[i + 1:i + 1 + fwd]
            fwd_l = lows[i + 1:i + 1 + fwd]
            if side == "long":   # fade a low -> expect up
                mfes.append(fwd_h.max() - entry)
                maes.append(entry - fwd_l.min())
            else:                # fade a high -> expect down
                mfes.append(entry - fwd_l.min())
                maes.append(fwd_h.max() - entry)
        mfes, maes = np.array(mfes), np.array(maes)
        if len(mfes) == 0:
            return {}
        return {
            "n": len(mfes),
            "mfe_median_pts": round(float(np.median(mfes)), 1),
            "mfe_p75_pts": round(float(np.percentile(mfes, 75)), 1),
            "mae_median_pts": round(float(np.median(maes)), 1),
            "mae_p75_pts": round(float(np.percentile(maes, 75)), 1),
            "mae_p90_pts": round(float(np.percentile(maes, 90)), 1),
        }
    report["mfe_mae_pdl_long"] = mfe_mae("pdl", "long")
    report["mfe_mae_pdh_short"] = mfe_mae("pdh", "short")
    logger.info(f"  PDL-fade LONG  : MFE med {report['mfe_mae_pdl_long'].get('mfe_median_pts')}pt, "
                  f"MAE med {report['mfe_mae_pdl_long'].get('mae_median_pts')}pt, "
                  f"MAE p90 {report['mfe_mae_pdl_long'].get('mae_p90_pts')}pt")

    # ===================================================================
    # D. Conditional mean reversion — snapback vs overshoot size
    # ===================================================================
    logger.info("Section D: conditional mean reversion (snapback vs overshoot)")
    ma = m5["close"].rolling(20).mean()
    sd = m5["close"].rolling(20).std()
    z = ((m5["close"] - ma) / sd).values
    fwd_ret = (m5["close"].shift(-6) / m5["close"] - 1).values * 100  # 30-min fwd %
    cond = {}
    for lo, hi, label in [(-99, -2.5, "z<-2.5"), (-2.5, -1.5, "-2.5..-1.5"),
                            (-1.5, 1.5, "-1.5..1.5"), (1.5, 2.5, "1.5..2.5"),
                            (2.5, 99, "z>2.5")]:
        mask = (z >= lo) & (z < hi) & np.isfinite(fwd_ret)
        if mask.sum() > 50:
            cond[label] = {
                "n": int(mask.sum()),
                "fwd_30min_mean_pct": round(float(np.mean(fwd_ret[mask])), 4),
            }
    report["conditional_mean_reversion"] = cond
    logger.info(f"  after z<-2.5 (oversold): fwd 30-min mean = "
                  f"{cond.get('z<-2.5',{}).get('fwd_30min_mean_pct')}%")
    logger.info(f"  after z>2.5 (overbought): fwd 30-min mean = "
                  f"{cond.get('z>2.5',{}).get('fwd_30min_mean_pct')}%")

    (DATA / "nq_deep_study.json").write_text(json.dumps(report, indent=2, default=str))
    logger.info(f"Wrote {DATA / 'nq_deep_study.json'}")

    # ---- printed summary ------------------------------------------------
    print("\n" + "=" * 72)
    print("NQ DEEP STUDY — conditional behaviour")
    print("=" * 72)
    print("\nA. STRUCTURAL-LEVEL REVERSAL — by 1st-touch vs repeat:")
    for lvl in ["pdh", "pdl", "onh", "onl"]:
        d = report[f"{lvl}_reversal_sliced"]
        tn = d["by_touch_number"]
        print(f"   {lvl.upper()}: overall {d['overall']['reversal_rate']}  |  "
                f"1st-touch {tn.get(1,{}).get('reversal_rate')}  "
                f"2nd {tn.get(2,{}).get('reversal_rate')}  "
                f"3rd+ {tn.get(3,{}).get('reversal_rate')}")
    print("\nA2. REVERSAL by volatility regime:")
    for lvl in ["pdh", "pdl"]:
        vr = report[f"{lvl}_reversal_sliced"]["by_vol_regime"]
        print(f"   {lvl.upper()}: low-vol {vr.get('low',{}).get('reversal_rate')}  "
                f"mid {vr.get('mid',{}).get('reversal_rate')}  "
                f"high-vol {vr.get('high',{}).get('reversal_rate')}")
    print("\nB. OVERNIGHT SWEEP -> NY REVERSAL:")
    ss = report["session_sweep"]
    print(f"   sweep ON-high then reverse: {ss['onh_sweep_reversal_rate']:.1%}")
    print(f"   sweep ON-low then reverse:  {ss['onl_sweep_reversal_rate']:.1%}")
    print("\nC. MFE/MAE for fade entries (points):")
    for k in ["mfe_mae_pdl_long", "mfe_mae_pdh_short"]:
        m = report[k]
        print(f"   {k}: MFE med {m.get('mfe_median_pts')} / p75 {m.get('mfe_p75_pts')}  "
                f"| MAE med {m.get('mae_median_pts')} / p90 {m.get('mae_p90_pts')}")
    print("\nD. CONDITIONAL SNAPBACK (forward 30-min return given Z):")
    for label, c in report["conditional_mean_reversion"].items():
        print(f"   {label:12s}: {c['fwd_30min_mean_pct']:+.4f}%  (n={c['n']:,})")


if __name__ == "__main__":
    main()
