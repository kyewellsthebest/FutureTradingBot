"""
NQ Behavioral Study — a rigorous statistical characterization of how
Nasdaq-100 futures actually move, across every timeframe.

This is NOT prediction. It is measurement: 8 years of NQ price decomposed
into the statistical regularities that genuinely exist. The findings feed
strategy design — they tell us which timeframe mean-reverts vs trends,
when volatility concentrates, and whether price reversals genuinely
cluster at structural levels.

Sections:
  1. Hurst exponent per timeframe       — trend vs mean-revert character
  2. Mean-reversion half-life           — how fast overshoots snap back
  3. Return autocorrelation             — short-term predictability
  4. Volatility seasonality             — variance by hour + weekday
  5. Volatility clustering              — does a big bar beget another
  6. Reversal-level clustering          — do reversals concentrate at
                                          PDH/PDL, overnight H/L, round 100s
  7. Gap statistics                     — fill rate + speed
  8. Move-size distribution             — fat tails, typical vs extreme

Output: data/nq_behavior_study.json + printed report.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from research.local_data_loader import load_intraday_1min

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
logger = logging.getLogger("nq_study")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def resample(m1: pd.DataFrame, rule: str) -> pd.DataFrame:
    return m1.resample(rule).agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna()


def hurst_exponent(prices: np.ndarray, max_lag: int = 50) -> float:
    """Hurst via the lag-variance method.

    For each lag τ, std of (price[t+τ]-price[t]) scales as τ^H.
    H = 0.5 random walk; H < 0.5 mean-reverting; H > 0.5 trending.
    """
    prices = np.asarray(prices, dtype=float)
    prices = prices[np.isfinite(prices)]
    if len(prices) < max_lag * 4:
        return float("nan")
    lags = np.arange(2, max_lag)
    tau = []
    for lag in lags:
        diff = prices[lag:] - prices[:-lag]
        tau.append(np.sqrt(np.mean(diff ** 2)))
    tau = np.array(tau)
    good = tau > 0
    if good.sum() < 5:
        return float("nan")
    slope = np.polyfit(np.log(lags[good]), np.log(tau[good]), 1)[0]
    return float(slope)


def mean_reversion_half_life(prices: np.ndarray, ma_window: int = 50) -> float:
    """Half-life of mean reversion (bars) via an AR(1) fit on the
    deviation-from-moving-average series. -ln(2)/b where b is the
    regression coefficient of Δdev on lagged dev."""
    s = pd.Series(prices, dtype=float)
    dev = (s - s.rolling(ma_window).mean()).dropna()
    if len(dev) < 100:
        return float("nan")
    lagged = dev.shift(1).dropna()
    delta = (dev - dev.shift(1)).dropna()
    n = min(len(lagged), len(delta))
    lagged, delta = lagged.iloc[-n:].values, delta.iloc[-n:].values
    b = np.polyfit(lagged, delta, 1)[0]
    if b >= 0:
        return float("inf")   # not mean-reverting
    return float(-np.log(2) / b)


def autocorr(returns: np.ndarray, lag: int = 1) -> float:
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < lag + 10:
        return float("nan")
    a, b = r[:-lag], r[lag:]
    if a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


# ---------------------------------------------------------------------------
# Main study
# ---------------------------------------------------------------------------
def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                          stream=sys.stdout)
    logger.info("Loading NQ 1-minute data...")
    m1 = load_intraday_1min("nq")
    if m1.index.tz is None:
        m1.index = m1.index.tz_localize("UTC")
    logger.info(f"  {len(m1):,} 1-min bars, {m1.index[0]} -> {m1.index[-1]}")

    frames = {
        "1min": m1,
        "5min": resample(m1, "5min"),
        "15min": resample(m1, "15min"),
        "1hr": resample(m1, "1h"),
        "4hr": resample(m1, "4h"),
        "1day": resample(m1, "1D"),
        "1week": resample(m1, "1W"),
    }
    report: dict = {}

    # --- 1+2+3. Hurst, half-life, autocorr per timeframe ----------------
    logger.info("Section 1-3: Hurst / half-life / autocorrelation per timeframe")
    tf_stats = {}
    for name, df in frames.items():
        closes = df["close"].values
        rets = pd.Series(closes).pct_change().dropna().values
        h = hurst_exponent(closes, max_lag=min(50, len(closes) // 5))
        hl = mean_reversion_half_life(closes, ma_window=min(50, len(closes) // 10))
        ac1 = autocorr(rets, 1)
        ac5 = autocorr(rets, 5)
        vol = float(np.std(rets)) if len(rets) else float("nan")
        tf_stats[name] = {
            "n_bars": len(df),
            "hurst": round(h, 3) if h == h else None,
            "character": ("trending" if h > 0.55 else
                            "mean-reverting" if h < 0.45 else "random-walk"),
            "half_life_bars": (round(hl, 1) if np.isfinite(hl) else None),
            "autocorr_lag1": round(ac1, 4) if ac1 == ac1 else None,
            "autocorr_lag5": round(ac5, 4) if ac5 == ac5 else None,
            "return_vol_pct": round(vol * 100, 3) if vol == vol else None,
        }
        logger.info(f"  {name:7s}: Hurst={tf_stats[name]['hurst']} "
                      f"({tf_stats[name]['character']}), "
                      f"half-life={tf_stats[name]['half_life_bars']} bars, "
                      f"ac1={tf_stats[name]['autocorr_lag1']}")
    report["timeframe_character"] = tf_stats

    # --- 4. Volatility seasonality (5-min) ------------------------------
    logger.info("Section 4: volatility seasonality")
    m5 = frames["5min"].copy()
    m5_ret = m5["close"].pct_change().abs()
    ny = m5.index.tz_convert("America/New_York")
    by_hour = m5_ret.groupby(ny.hour).mean()
    by_dow = m5_ret.groupby(ny.dayofweek).mean()
    report["volatility_by_ny_hour"] = {int(h): round(v * 100, 4)
                                          for h, v in by_hour.items()}
    dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    report["volatility_by_weekday"] = {dow_names[d]: round(v * 100, 4)
                                          for d, v in by_dow.items() if d < 7}
    peak_hr = by_hour.idxmax()
    quiet_hr = by_hour.idxmin()
    logger.info(f"  most volatile NY hour: {peak_hr}:00  "
                  f"quietest: {quiet_hr}:00")

    # --- 5. Volatility clustering ---------------------------------------
    logger.info("Section 5: volatility clustering")
    abs_ret = m5["close"].pct_change().abs().dropna().values
    vol_cluster = {f"abs_ret_autocorr_lag{l}": round(autocorr(abs_ret, l), 4)
                     for l in (1, 5, 12, 78)}   # 1bar, 25min, 1hr, 1day
    report["volatility_clustering"] = vol_cluster
    logger.info(f"  |return| autocorr lag1={vol_cluster['abs_ret_autocorr_lag1']} "
                  f"(>0 = big bars cluster)")

    # --- 6. Reversal-level clustering -----------------------------------
    logger.info("Section 6: reversal clustering at structural levels")
    daily = frames["1day"].copy()
    daily["pdh"] = daily["high"].shift(1)
    daily["pdl"] = daily["low"].shift(1)
    # For each 5-min bar, attach that day's PDH/PDL
    m5d = m5.copy()
    m5d["date"] = m5d.index.tz_convert("America/New_York").normalize()
    daily_idx = daily.copy()
    daily_idx["date"] = daily_idx.index.tz_convert("America/New_York").normalize() \
        if daily_idx.index.tz is not None else daily_idx.index.normalize()
    pdh_map = dict(zip(daily_idx["date"], daily_idx["pdh"]))
    pdl_map = dict(zip(daily_idx["date"], daily_idx["pdl"]))
    m5d["pdh"] = m5d["date"].map(pdh_map)
    m5d["pdl"] = m5d["date"].map(pdl_map)

    def reversal_rate_near_level(df, level_col, side, tol_pts=8.0, fwd=12):
        """Of bars that touch `level_col`, what fraction reverse away from it
        within `fwd` bars? side='high' = expect down-reversal after touching
        a resistance level; 'low' = up-reversal after touching support."""
        closes = df["close"].values
        highs = df["high"].values
        lows = df["low"].values
        levels = df[level_col].values
        n = len(df)
        touches = 0
        reversals = 0
        for i in range(n - fwd):
            lv = levels[i]
            if not np.isfinite(lv):
                continue
            if side == "high":
                touched = highs[i] >= lv - tol_pts and lows[i] <= lv + tol_pts
                if touched:
                    touches += 1
                    # reversal = closes lower than the level within fwd bars
                    if closes[i + 1:i + 1 + fwd].min() < lv - tol_pts:
                        reversals += 1
            else:
                touched = lows[i] <= lv + tol_pts and highs[i] >= lv - tol_pts
                if touched:
                    touches += 1
                    if closes[i + 1:i + 1 + fwd].max() > lv + tol_pts:
                        reversals += 1
        return touches, (reversals / touches if touches else float("nan"))

    pdh_touch, pdh_rev = reversal_rate_near_level(m5d, "pdh", "high")
    pdl_touch, pdl_rev = reversal_rate_near_level(m5d, "pdl", "low")

    # Baseline: reversal rate at a random non-level price (synthetic level
    # = the bar's own open shifted, i.e. an arbitrary price the bar touches)
    m5d["rand_level"] = m5d["open"]
    rand_touch, rand_rev = reversal_rate_near_level(m5d, "rand_level", "high")

    # Round-number levels — nearest multiple of 100
    m5d["round100"] = (m5d["close"] / 100).round() * 100
    r100_touch, r100_rev = reversal_rate_near_level(m5d, "round100", "high")

    report["reversal_clustering"] = {
        "prior_day_high": {"touches": pdh_touch, "reversal_rate": round(pdh_rev, 3) if pdh_rev == pdh_rev else None},
        "prior_day_low":  {"touches": pdl_touch, "reversal_rate": round(pdl_rev, 3) if pdl_rev == pdl_rev else None},
        "round_100_level": {"touches": r100_touch, "reversal_rate": round(r100_rev, 3) if r100_rev == r100_rev else None},
        "random_baseline": {"touches": rand_touch, "reversal_rate": round(rand_rev, 3) if rand_rev == rand_rev else None},
    }
    logger.info(f"  reversal rate — PDH:{pdh_rev:.1%}  PDL:{pdl_rev:.1%}  "
                  f"round100:{r100_rev:.1%}  baseline:{rand_rev:.1%}")

    # --- 7. Gap statistics ----------------------------------------------
    logger.info("Section 7: gap statistics")
    daily = frames["1day"].copy()
    daily["prev_close"] = daily["close"].shift(1)
    daily["gap"] = daily["open"] - daily["prev_close"]
    daily["gap_pct"] = daily["gap"] / daily["prev_close"] * 100
    # gap "filled" = intraday trades back through the prev close
    daily["gap_filled"] = np.where(
        daily["gap"] > 0, daily["low"] <= daily["prev_close"],
        np.where(daily["gap"] < 0, daily["high"] >= daily["prev_close"], True))
    gaps = daily.dropna(subset=["gap"])
    sig_gaps = gaps[gaps["gap_pct"].abs() > 0.1]
    report["gap_stats"] = {
        "n_sessions": len(gaps),
        "n_significant_gaps": len(sig_gaps),
        "gap_fill_rate_same_day": round(sig_gaps["gap_filled"].mean(), 3),
        "avg_gap_pct": round(gaps["gap_pct"].abs().mean(), 3),
    }
    logger.info(f"  significant gaps fill same-day: "
                  f"{report['gap_stats']['gap_fill_rate_same_day']:.1%}")

    # --- 8. Move-size distribution --------------------------------------
    logger.info("Section 8: move-size distribution")
    daily_ret = frames["1day"]["close"].pct_change().dropna() * 100
    report["daily_move_distribution"] = {
        "mean_abs_pct": round(daily_ret.abs().mean(), 3),
        "median_abs_pct": round(daily_ret.abs().median(), 3),
        "p95_abs_pct": round(daily_ret.abs().quantile(0.95), 3),
        "p99_abs_pct": round(daily_ret.abs().quantile(0.99), 3),
        "max_abs_pct": round(daily_ret.abs().max(), 3),
        "kurtosis": round(float(daily_ret.kurtosis()), 2),
        "skew": round(float(daily_ret.skew()), 3),
    }

    (DATA / "nq_behavior_study.json").write_text(json.dumps(report, indent=2))
    logger.info(f"Wrote {DATA / 'nq_behavior_study.json'}")

    # ---- printed summary ------------------------------------------------
    print("\n" + "=" * 70)
    print("NQ BEHAVIORAL STUDY — 8.1 years, 2.8M 1-min bars")
    print("=" * 70)
    print("\n1. CHARACTER BY TIMEFRAME (Hurst exponent)")
    print(f"   {'TF':8s} {'Hurst':>7s} {'Character':>16s} {'Half-life':>12s} {'AC(1)':>9s}")
    for name, s in tf_stats.items():
        hl = f"{s['half_life_bars']} bars" if s['half_life_bars'] else "n/a"
        print(f"   {name:8s} {str(s['hurst']):>7s} {s['character']:>16s} "
                f"{hl:>12s} {str(s['autocorr_lag1']):>9s}")
    print("\n4. VOLATILITY — most volatile NY hours")
    top_hrs = sorted(report["volatility_by_ny_hour"].items(),
                       key=lambda x: -x[1])[:5]
    for h, v in top_hrs:
        print(f"   {h:02d}:00 ET — {v:.3f}% avg abs move")
    print("\n6. REVERSAL CLUSTERING (does price reverse at these levels?)")
    rc = report["reversal_clustering"]
    for lvl, d in rc.items():
        print(f"   {lvl:18s}: {d['reversal_rate']} reversal rate "
                f"({d['touches']:,} touches)")
    print("\n7. GAPS")
    g = report["gap_stats"]
    print(f"   significant gaps fill same day: {g['gap_fill_rate_same_day']:.1%}")
    print("\n8. DAILY MOVE DISTRIBUTION")
    dm = report["daily_move_distribution"]
    print(f"   median day: {dm['median_abs_pct']}%   95th pct: {dm['p95_abs_pct']}%   "
            f"99th: {dm['p99_abs_pct']}%   kurtosis: {dm['kurtosis']}")


if __name__ == "__main__":
    main()
