"""Loss forensics — examine every losing trade in the baseline backtest,
extract pre-trade features, find patterns that predict losses, build a
filter that targets those patterns.

Goals (per user):
  1. Identify WHY each loss happened (pre-trade features)
  2. Find "holes" -- conditions where loss rate >> baseline
  3. Specifically attack LOSING STREAKS (6+ in a row)
  4. Build a filter that removes 80%+ of preventable losses
  5. Validate it doesn't kill return; deploy on Account 3 if good

Approach:
  - For each trade in baseline target=18: compute ~20 pre-trade features
    (ATR at multiple windows, trend strength, time, recent streak, etc.)
  - For each feature: P(loss | feature bucket)
  - Find buckets where P(loss) > 0.70 (vs baseline ~0.63)
  - Combine 2-3 features for sub-populations with even higher loss rate
  - Test rules that skip those entries
  - Specifically: detect losing-streak onset and pause after 2-3 losses

Outputs:
  reports/loss_forensics.json - per-bucket loss rates
  reports/streak_analysis.json - distribution of losing streaks
  Console: recommended filter rules + expected impact
"""
from __future__ import annotations
import json, time
from pathlib import Path
import numpy as np
import pandas as pd

from research.sim_strategy_bakeoff_tick import (
    build_1m_bars, simulate, baseline_setups, score, STARTING_BAL
)

SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")
OUT_LOSS  = Path("/home/user/HFTBot/reports/loss_forensics.json")
OUT_STRK  = Path("/home/user/HFTBot/reports/streak_analysis.json")
OUT_FINAL = Path("/home/user/HFTBot/reports/streak_filter_results.json")


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------
def compute_features(bars: pd.DataFrame, setups: list) -> pd.DataFrame:
    """For each setup, compute pre-trade features."""
    h = bars["high"].to_numpy(); l = bars["low"].to_numpy()
    c = bars["close"].to_numpy(); o = bars["open"].to_numpy()
    v = bars["volume"].to_numpy()
    bar_ts = bars.index.astype("int64").to_numpy()

    # Pre-compute multi-window ATRs and trend strengths
    tr = np.maximum.reduce([h - l, np.abs(h - np.r_[c[0], c[:-1]]),
                            np.abs(l - np.r_[c[0], c[:-1]])])
    atr5   = pd.Series(tr).rolling(5).mean().to_numpy()
    atr14  = pd.Series(tr).rolling(14).mean().to_numpy()
    atr60  = pd.Series(tr).rolling(60).mean().to_numpy()
    atr240 = pd.Series(tr).rolling(240).mean().to_numpy()

    rows = []
    for s in setups:
        i = int(np.searchsorted(bar_ts, s["sig_ts"], side="left")) - 1
        if i < 30: continue
        ny = pd.Timestamp(s["sig_ts"], tz="UTC").tz_convert("America/New_York")
        # 4h net move
        i240 = max(0, i - 240)
        i60 = max(0, i - 60)
        i30 = max(0, i - 30)
        i15 = max(0, i - 15)
        i5  = max(0, i - 5)
        # Multi-window net moves
        net_4h = float(c[i] - c[i240])
        net_1h = float(c[i] - c[i60])
        net_30m = float(c[i] - c[i30])
        # Trend strength = |net| / range
        r_4h = float(h[i240:i+1].max() - l[i240:i+1].min())
        r_1h = float(h[i60:i+1].max() - l[i60:i+1].min())
        ts_4h = abs(net_4h) / max(r_4h, 1e-9)
        ts_1h = abs(net_1h) / max(r_1h, 1e-9)
        # Volatility ratio (recent vs longer term)
        vol_ratio = float(atr5[i]) / max(float(atr60[i]), 1e-9) if np.isfinite(atr5[i]) and np.isfinite(atr60[i]) else 1.0
        # Distance from VWAP (proxy: avg of last 60 bars)
        vwap_60 = float(c[i60:i+1].mean())
        dist_vwap = float(c[i] - vwap_60)
        # Volume spike (last bar vs 30-bar avg)
        vol_avg30 = float(v[i30:i].mean()) if i >= 30 else 1
        vol_spike = float(v[i]) / max(vol_avg30, 1)
        # Trend alignment with setup direction
        # +1 = setup goes WITH 4h trend, -1 = AGAINST
        if abs(net_4h) > 30:
            trend_4h_dir = 1 if net_4h > 0 else -1
            if trend_4h_dir == s["side"]:
                trend_alignment = "with_trend"
            else:
                trend_alignment = "counter_trend"
        else:
            trend_alignment = "neutral"
        # Body % of recent bars (clean trend vs noise)
        body_recent = float(np.abs(c[i30:i+1] - o[i30:i+1]).sum())
        range_recent = float((h[i30:i+1] - l[i30:i+1]).sum())
        body_pct = body_recent / max(range_recent, 1e-9)
        rows.append({
            "sig_ts": int(s["sig_ts"]),
            "side": int(s["side"]),
            "entry_px": float(s["entry_px"]),
            "stop_px": float(s["stop_px"]),
            "target_px": float(s["target_px"]),
            "hour_ny": int(ny.hour),
            "weekday": int(ny.weekday()),
            "atr5":   round(float(atr5[i])   if np.isfinite(atr5[i])   else 0, 2),
            "atr14":  round(float(atr14[i])  if np.isfinite(atr14[i])  else 0, 2),
            "atr60":  round(float(atr60[i])  if np.isfinite(atr60[i])  else 0, 2),
            "atr240": round(float(atr240[i]) if np.isfinite(atr240[i]) else 0, 2),
            "net_4h":  round(net_4h, 1),
            "net_1h":  round(net_1h, 1),
            "net_30m": round(net_30m, 1),
            "ts_4h":   round(ts_4h, 3),
            "ts_1h":   round(ts_1h, 3),
            "vol_ratio_5_60": round(vol_ratio, 2),
            "dist_vwap": round(dist_vwap, 1),
            "vol_spike": round(vol_spike, 2),
            "body_pct_30": round(body_pct, 3),
            "trend_alignment": trend_alignment,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Streak analysis
# ---------------------------------------------------------------------------
def find_losing_streaks(trades: list) -> dict:
    """Identify losing streaks of >=2, return distribution + the worst."""
    streaks = []
    current = 0
    current_pnl = 0.0
    for t in trades:
        if t["pnl_usd"] < 0:
            current += 1
            current_pnl += t["pnl_usd"]
        else:
            if current >= 2:
                streaks.append({"length": current, "pnl": round(current_pnl, 2)})
            current = 0
            current_pnl = 0.0
    if current >= 2:
        streaks.append({"length": current, "pnl": round(current_pnl, 2)})
    # Distribution
    by_len = {}
    for s in streaks:
        L = s["length"]
        bucket = "10+" if L >= 10 else str(L)
        by_len[bucket] = by_len.get(bucket, 0) + 1
    return {
        "n_streaks_ge2": len(streaks),
        "n_streaks_ge6": sum(1 for s in streaks if s["length"] >= 6),
        "n_streaks_ge10": sum(1 for s in streaks if s["length"] >= 10),
        "max_streak": max((s["length"] for s in streaks), default=0),
        "worst_streak_pnl": min((s["pnl"] for s in streaks), default=0),
        "distribution": dict(sorted(by_len.items(), key=lambda kv: (kv[0]!="10+", int(kv[0]) if kv[0]!="10+" else 99))),
    }


# ---------------------------------------------------------------------------
# Per-feature loss-rate analysis
# ---------------------------------------------------------------------------
def loss_rate_by_bucket(features_df: pd.DataFrame, feature: str,
                        bins: list, labels: list, side_filter=None) -> pd.DataFrame:
    df = features_df.copy()
    if side_filter == "with_trend":
        df = df[df["trend_alignment"] == "with_trend"]
    elif side_filter == "counter_trend":
        df = df[df["trend_alignment"] == "counter_trend"]
    df["bucket"] = pd.cut(df[feature], bins=bins, labels=labels, include_lowest=True)
    return df.groupby("bucket", observed=True).agg(
        n=("loser", "count"),
        loss_rate=("loser", "mean"),
        avg_pnl=("pnl_usd", "mean"),
        total_pnl=("pnl_usd", "sum"),
    ).round(3)


# ---------------------------------------------------------------------------
# Build streak-aware filter: skip trades after N consecutive losses
# ---------------------------------------------------------------------------
def apply_streak_filter(setups, price, ts_ns, max_consecutive_losses=3,
                         pause_minutes=30, params=None):
    """Walk through setups in order; track running consecutive losses;
    after `max_consecutive_losses` in a row, skip new entries for
    `pause_minutes`. This simulates 'after a bad streak, wait for cooler
    heads'."""
    from research.sim_strategy_bakeoff_tick import simulate as _sim
    # Simulate one-by-one with state
    cooldown_until = -1
    consec_losses = 0
    accepted = []
    skipped = []
    pause_ns = pause_minutes * 60 * 1_000_000_000
    # We need to know each trade's outcome to track streak — so simulate ALL
    # first, then mask
    all_trades = _sim(setups, price, ts_ns)
    # Map trades back to their setup indices
    trade_by_sig = {t["entry_ts"]: t for t in all_trades}
    sorted_setups = sorted(setups, key=lambda s: s["sig_ts"])
    cooldown_until_ts = -1
    consec = 0
    filtered = []
    skipped_count = 0
    for s in sorted_setups:
        if s["sig_ts"] < cooldown_until_ts:
            skipped_count += 1
            continue
        filtered.append(s)
        # find this setup's outcome
        # match by signal -> first trade after sig_ts within max_wait
        # Approximate by entry_ts > sig_ts
        future_trades = [t for t in all_trades if t["entry_ts"] >= s["sig_ts"] and t["entry_ts"] < s["sig_ts"] + 300 * 1_000_000_000]
        if not future_trades:
            continue
        t = future_trades[0]
        if t["pnl_usd"] < 0:
            consec += 1
            if consec >= max_consecutive_losses:
                cooldown_until_ts = t["exit_ts"] + pause_ns
                consec = 0
        else:
            consec = 0
    final_trades = _sim(filtered, price, ts_ns)
    return final_trades, skipped_count


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------
def main():
    t0 = time.time()
    df = pd.read_parquet(SRC)
    period_days = (df["ts"].iloc[-1] - df["ts"].iloc[0]).total_seconds() / 86400
    price = df["price"].to_numpy(dtype=np.float32)
    volume = df["volume"].to_numpy(dtype=np.int32)
    ts_ns = df["ts"].astype("int64").to_numpy()
    bars = build_1m_bars(price, ts_ns, volume)
    print(f"Loaded {len(df):,} ticks, {len(bars):,} bars ({time.time()-t0:.0f}s)")

    # Baseline target=18 setups
    base_setups = []
    for s in baseline_setups(bars):
        side = s["side"]; entry = s["entry_px"]
        tgt = entry + 18.0 if side == 1 else entry - 18.0
        base_setups.append({**s, "target_px": tgt})

    print(f"\nRunning baseline target=18 sim...")
    trades = simulate(base_setups, price, ts_ns)
    print(f"  {len(trades)} trades ({time.time()-t0:.0f}s)")

    # Compute features for every signal that produced a trade
    print(f"\nComputing pre-trade features for {len(base_setups)} setups...")
    features = compute_features(bars, base_setups)
    # Match to trades by entry_ts proximity to sig_ts
    trade_map = {}
    for t in trades:
        # Find the closest setup before or at entry_ts
        candidates = features[(features["sig_ts"] <= t["entry_ts"]) &
                              (features["sig_ts"] >= t["entry_ts"] - 5 * 60 * 1_000_000_000)]
        if not candidates.empty:
            trade_map[t["entry_ts"]] = candidates.iloc[-1].to_dict()
    # Build trade-level df
    rows = []
    for t in trades:
        feat = trade_map.get(t["entry_ts"])
        if not feat: continue
        rows.append({**feat, "pnl_usd": t["pnl_usd"],
                     "exit_reason": t["reason"], "exit_ts": t["exit_ts"],
                     "loser": int(t["pnl_usd"] < 0)})
    tdf = pd.DataFrame(rows)
    print(f"  matched {len(tdf)} trades to features  ({time.time()-t0:.0f}s)")

    overall_loss_rate = float(tdf["loser"].mean())
    print(f"\nOverall loss rate: {overall_loss_rate*100:.1f}%")

    # ========== Per-feature loss-rate buckets ==========
    print("\n" + "=" * 80)
    print("LOSS RATE BY FEATURE BUCKET")
    print("=" * 80)
    bucket_results = {}

    for feat, bins, labels in [
        ("atr14",   [0, 2, 3, 4, 5, 7, 100],            ["<2", "2-3", "3-4", "4-5", "5-7", ">7"]),
        ("atr60",   [0, 2, 3, 4, 5, 7, 100],            ["<2", "2-3", "3-4", "4-5", "5-7", ">7"]),
        ("ts_4h",   [0, 0.3, 0.5, 0.7, 0.85, 1.0],      ["<0.3", "0.3-0.5", "0.5-0.7", "0.7-0.85", ">0.85"]),
        ("ts_1h",   [0, 0.3, 0.5, 0.7, 0.85, 1.0],      ["<0.3", "0.3-0.5", "0.5-0.7", "0.7-0.85", ">0.85"]),
        ("vol_ratio_5_60", [0, 0.5, 1.0, 1.5, 2.0, 100], ["<0.5", "0.5-1", "1-1.5", "1.5-2", ">2"]),
        ("body_pct_30",    [0, 0.3, 0.45, 0.55, 0.65, 1], ["<0.3", "0.3-0.45", "0.45-0.55", "0.55-0.65", ">0.65"]),
        ("vol_spike", [0, 0.5, 1, 2, 5, 100], ["<0.5", "0.5-1", "1-2", "2-5", ">5"]),
        ("hour_ny", [-1, 5, 9, 12, 15, 18, 23], ["0-5", "6-9", "10-12", "13-15", "16-18", "19-23"]),
    ]:
        print(f"\n{feat}:")
        out = loss_rate_by_bucket(tdf, feat, bins, labels).reset_index()
        print(out.to_string(index=False))
        bucket_results[feat] = out.to_dict(orient="records")

    # Counter-trend specific analysis
    print("\n" + "=" * 80)
    print("LOSS RATE FOR COUNTER-TREND TRADES (the painful ones)")
    print("=" * 80)
    counter_trend = tdf[tdf["trend_alignment"] == "counter_trend"]
    with_trend = tdf[tdf["trend_alignment"] == "with_trend"]
    neutral = tdf[tdf["trend_alignment"] == "neutral"]
    print(f"  with_trend:    {len(with_trend):>4} trades  loss_rate={with_trend['loser'].mean()*100:>5.1f}%  total_pnl=${with_trend['pnl_usd'].sum():>+8,.0f}")
    print(f"  neutral:       {len(neutral):>4} trades  loss_rate={neutral['loser'].mean()*100:>5.1f}%  total_pnl=${neutral['pnl_usd'].sum():>+8,.0f}")
    print(f"  counter_trend: {len(counter_trend):>4} trades  loss_rate={counter_trend['loser'].mean()*100:>5.1f}%  total_pnl=${counter_trend['pnl_usd'].sum():>+8,.0f}")

    # ========== Streak analysis ==========
    print("\n" + "=" * 80)
    print("LOSING STREAK ANALYSIS")
    print("=" * 80)
    streak_stats = find_losing_streaks(trades)
    print(f"  total streaks (>=2 in a row): {streak_stats['n_streaks_ge2']}")
    print(f"  streaks of 6+:                 {streak_stats['n_streaks_ge6']}")
    print(f"  streaks of 10+:                {streak_stats['n_streaks_ge10']}")
    print(f"  longest streak:                {streak_stats['max_streak']} trades")
    print(f"  worst streak P&L:              ${streak_stats['worst_streak_pnl']:+,.0f}")
    print(f"  Distribution: {streak_stats['distribution']}")

    # ========== Build improved filter ==========
    print("\n" + "=" * 80)
    print("CANDIDATE FILTERS")
    print("=" * 80)

    def filter_setups(rules):
        out = []
        for s in base_setups:
            i = int(np.searchsorted(bars.index.astype("int64").to_numpy(),
                                     s["sig_ts"], side="left")) - 1
            if i < 30: continue
            # Re-extract the relevant features quickly
            c_arr = bars["close"].to_numpy(); h_arr = bars["high"].to_numpy()
            l_arr = bars["low"].to_numpy(); o_arr = bars["open"].to_numpy()
            tr_arr = np.maximum.reduce([h_arr - l_arr,
                                         np.abs(h_arr - np.r_[c_arr[0], c_arr[:-1]]),
                                         np.abs(l_arr - np.r_[c_arr[0], c_arr[:-1]])])
            atr14_now = pd.Series(tr_arr).rolling(14).mean().iloc[i] if i >= 14 else None
            i240 = max(0, i - 240)
            net_4h = c_arr[i] - c_arr[i240]
            # Apply rules
            ok = True
            for rule_name, rule_fn in rules.items():
                if not rule_fn(i, atr14_now, net_4h, s, c_arr, h_arr, l_arr, o_arr):
                    ok = False; break
            if ok:
                out.append(s)
        return out

    def score_trades(trades, days):
        if not trades: return {"n":0}
        pnls = np.array([t["pnl_usd"] for t in trades])
        wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
        cum = pnls.cumsum()
        maxdd = float((cum - np.maximum.accumulate(cum)).min())
        months = days / 30.44
        # Compute losing streak metrics
        st = find_losing_streaks(trades)
        # Worst day
        tdf2 = pd.DataFrame(trades)
        tdf2["exit_dt"] = pd.to_datetime(tdf2["exit_ts"], utc=True).dt.tz_convert("America/New_York")
        tdf2["ny_date"] = tdf2["exit_dt"].dt.date
        daily = tdf2.groupby("ny_date")["pnl_usd"].sum()
        return {
            "n": len(pnls),
            "wr": round(len(wins)/len(pnls)*100, 1),
            "ret_mo": round(float(pnls.sum())/STARTING_BAL*100/months, 2),
            "max_dd_pct": round(abs(maxdd/STARTING_BAL*100), 2),
            "max_dd_usd": round(maxdd, 0),
            "worst_day": round(float(daily.min()), 0),
            "max_streak": st["max_streak"],
            "n_streaks_ge6": st["n_streaks_ge6"],
            "worst_streak_pnl": st["worst_streak_pnl"],
        }

    print(f"\n{'Filter':<48}{'n':>6}{'WR':>6}{'Ret/mo':>9}{'DD%':>6}{'WorstDay':>10}{'MaxStrk':>9}{'Strk>=6':>9}{'WorstStrk':>11}")
    print("-" * 112)
    def run_filter(label, rules):
        s = filter_setups(rules)
        t = simulate(s, price, ts_ns)
        sc = score_trades(t, period_days)
        print(f"{label:<48}{sc.get('n',0):>6}{sc.get('wr',0):>5.1f}%"
              f"{sc.get('ret_mo',0):>+8.2f}%{sc.get('max_dd_pct',0):>5.2f}%"
              f"{sc.get('worst_day',0):>+10,.0f}{sc.get('max_streak',0):>9}"
              f"{sc.get('n_streaks_ge6',0):>9}{sc.get('worst_streak_pnl',0):>+11,.0f}")
        return sc

    # Baseline reference (no extra filter beyond target=18)
    baseline_sc = run_filter("BASELINE target=18", {})

    # Current Account 3 -- ATR>=4 + adaptive stops handled inside setup gen
    # so let me re-run with simple ATR>=4 filter
    run_filter("ATR14 >= 4", {
        "atr14_ge4": lambda i, a14, net4h, s, c,h,l,o: (a14 is not None and a14 >= 4.0)
    })

    # Higher ATR threshold
    run_filter("ATR14 >= 5", {
        "atr14_ge5": lambda i, a14, net4h, s, c,h,l,o: (a14 is not None and a14 >= 5.0)
    })

    # Skip counter-trend in moderate trend
    run_filter("Skip counter-trend (4h>=40pt)", {
        "no_counter": lambda i, a14, net4h, s, c,h,l,o:
            not (abs(net4h) >= 40 and ((net4h > 0) != (s["side"] == 1)))
    })
    run_filter("Skip counter-trend (4h>=60pt)", {
        "no_counter": lambda i, a14, net4h, s, c,h,l,o:
            not (abs(net4h) >= 60 and ((net4h > 0) != (s["side"] == 1)))
    })

    # Combined: ATR + skip counter-trend in moderate trend
    run_filter("ATR>=4 AND skip ctr (4h>=40pt)", {
        "atr_ok": lambda i, a14, net4h, s, c,h,l,o: (a14 is not None and a14 >= 4.0),
        "no_counter": lambda i, a14, net4h, s, c,h,l,o:
            not (abs(net4h) >= 40 and ((net4h > 0) != (s["side"] == 1)))
    })
    run_filter("ATR>=4 AND skip ctr (4h>=60pt)", {
        "atr_ok": lambda i, a14, net4h, s, c,h,l,o: (a14 is not None and a14 >= 4.0),
        "no_counter": lambda i, a14, net4h, s, c,h,l,o:
            not (abs(net4h) >= 60 and ((net4h > 0) != (s["side"] == 1)))
    })

    # ========== Save outputs ==========
    OUT_LOSS.parent.mkdir(parents=True, exist_ok=True)
    OUT_LOSS.write_text(json.dumps({
        "overall_loss_rate": overall_loss_rate,
        "buckets": bucket_results,
        "trend_alignment": {
            "with_trend": {"n": len(with_trend), "loss_rate": float(with_trend['loser'].mean()), "total_pnl": float(with_trend['pnl_usd'].sum())},
            "counter_trend": {"n": len(counter_trend), "loss_rate": float(counter_trend['loser'].mean()), "total_pnl": float(counter_trend['pnl_usd'].sum())},
            "neutral": {"n": len(neutral), "loss_rate": float(neutral['loser'].mean()), "total_pnl": float(neutral['pnl_usd'].sum())},
        },
    }, indent=2, default=str))
    OUT_STRK.write_text(json.dumps(streak_stats, indent=2, default=str))
    print(f"\nTotal: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
