"""
Adaptive brain — STAGE 1: signal-replay dataset.

Replays all 97 deployed strategies (data/deployed_strategies.json) across
the full price history and records, for every signal firing:

  * the trade OUTCOME — entry/exit, win/loss, R-multiple, P&L points,
    hold time, MAE/MFE — simulated exactly the way the gauntlet does it
    (entry at the next 5-min bar open, ATR14 stop/target, exits walked on
    1-minute bars, stop assumed first on an ambiguous bar).
  * ~35 POINT-IN-TIME context features the strategy itself never sees —
    volatility state, regime, time, cross-asset moves, how many other
    strategies fired on the same bar, and the strategy's own recent
    realised hit-rate.

The output table (data/signal_dataset.csv) is the training set for the
Stage 2 meta-model, which learns to predict which firings will actually
win and sizes them accordingly.

Firing logic is taken verbatim from v11_signals (the live bot's own
evaluator) so the dataset reflects exactly what the deployed bot does.
Every feature uses only information available at or before the signal
bar — no look-ahead.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from research.indicators import atr
from research.local_data_loader import (
    load_intraday_1min, load_intraday_5min, load_vix_5min,
)
from research.v11_signals import compute_div_z, in_time_context, load_v11_strategies

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
OUT_CSV = DATA / "signal_dataset.csv"
OUT_SUMMARY = DATA / "signal_dataset_summary.json"
logger = logging.getLogger("signal_dataset")

NY = "America/New_York"


def _utc(df: pd.DataFrame) -> pd.DataFrame:
    if df is not None and df.index.tz is None:
        df = df.copy()
        df.index = df.index.tz_localize("UTC")
    return df


def simulate_trade(side: str, entry_loc: int, m: np.ndarray, idx: pd.DatetimeIndex,
                   atr14: float, stop_atr: float, target_atr: float,
                   max_hold_min: int) -> dict | None:
    """Walk 1-minute bars from entry; exit on stop / target / max-hold.

    m columns: [open, high, low, close]. Stop is checked before target on
    any bar that could hit both — the conservative assumption."""
    if entry_loc >= len(idx) or not (np.isfinite(atr14) and atr14 > 0):
        return None
    entry_px = m[entry_loc, 0]
    stop_dist = stop_atr * atr14
    tgt_dist = target_atr * atr14
    if side == "LONG":
        stop, target = entry_px - stop_dist, entry_px + tgt_dist
    else:
        stop, target = entry_px + stop_dist, entry_px - tgt_dist
    end = min(entry_loc + max_hold_min, len(idx) - 1)

    exit_px = None
    reason = "timeout"
    exit_loc = end
    mae = 0.0  # worst adverse excursion, price units (<=0)
    mfe = 0.0  # best favourable excursion (>=0)
    for j in range(entry_loc, end + 1):
        hi, lo = m[j, 1], m[j, 2]
        if side == "LONG":
            mae = min(mae, lo - entry_px)
            mfe = max(mfe, hi - entry_px)
            if lo <= stop:
                exit_px, reason, exit_loc = stop, "stop", j
                break
            if hi >= target:
                exit_px, reason, exit_loc = target, "target", j
                break
        else:
            mae = min(mae, entry_px - hi)
            mfe = max(mfe, entry_px - lo)
            if hi >= stop:
                exit_px, reason, exit_loc = stop, "stop", j
                break
            if lo <= target:
                exit_px, reason, exit_loc = target, "target", j
                break
    if exit_px is None:
        exit_px = m[end, 3]

    pnl = (exit_px - entry_px) if side == "LONG" else (entry_px - exit_px)
    return {
        "entry_px": float(entry_px),
        "exit_px": float(exit_px),
        "exit_reason": reason,
        "exit_ts": idx[exit_loc],
        "hold_min": int(exit_loc - entry_loc),
        "pnl_points": float(pnl),
        "r_multiple": float(pnl / stop_dist) if stop_dist > 0 else 0.0,
        "win": int(reason == "target"),
        "profitable": int(pnl > 0),
        "mae_atr": float(mae / atr14),
        "mfe_atr": float(mfe / atr14),
    }


def build_global_features(nq, es, rty, vix, es_z: dict) -> pd.DataFrame:
    """Per-bar market-state features — computed once, looked up per firing.
    Everything here is strictly backward-looking."""
    c, h, l, v = nq["close"], nq["high"], nq["low"], nq["volume"]
    logret = np.log(c).diff()
    a14 = atr(h, l, c, 14)
    ny = c.index.tz_convert(NY)

    G = pd.DataFrame(index=c.index)
    G["ny_hour"] = ny.hour
    G["ny_minute"] = ny.minute
    G["day_of_week"] = ny.dayofweek
    G["atr14"] = a14
    G["atr_pct"] = a14.rolling(500, min_periods=100).rank(pct=True)
    G["rv20"] = logret.rolling(20).std()
    G["rv60"] = logret.rolling(60).std()
    G["nq_ret_5"] = np.log(c / c.shift(5))
    G["nq_ret_20"] = np.log(c / c.shift(20))
    G["nq_ret_60"] = np.log(c / c.shift(60))
    sma20 = c.rolling(20).mean()
    sma50 = c.rolling(50).mean()
    sma200 = c.rolling(200).mean()
    G["nq_vs_sma50"] = c / sma50 - 1.0
    G["nq_vs_sma200"] = c / sma200 - 1.0
    G["trend_20_50_atr"] = (sma20 - sma50) / a14
    G["range20_atr"] = (h.rolling(20).max() - l.rolling(20).min()) / a14
    G["vol_ratio"] = v / v.rolling(50).mean()

    es_c = es["close"].reindex(c.index, method="ffill")
    G["es_ret_20"] = np.log(es_c / es_c.shift(20))
    if rty is not None and not rty.empty:
        rty_c = rty["close"].reindex(c.index, method="ffill")
        G["rty_ret_20"] = np.log(rty_c / rty_c.shift(20))
    else:
        G["rty_ret_20"] = np.nan

    if vix is not None and not vix.empty:
        vix_c = vix["close"].reindex(c.index, method="ffill")
        G["vix_level"] = vix_c
        G["vix_pct"] = vix_c.rolling(500).rank(pct=True)
        G["vix_z"] = (vix_c - vix_c.rolling(200).mean()) / vix_c.rolling(200).std()
        G["vix_ret_20"] = np.log(vix_c / vix_c.shift(20))
    else:
        for col in ("vix_level", "vix_pct", "vix_z", "vix_ret_20"):
            G[col] = np.nan

    # consensus depth: how many NQ-ES divergence windows are at an extreme
    if es_z:
        zmat = pd.DataFrame(es_z)
        G["n_windows_os"] = (zmat < -2.0).sum(axis=1)   # oversold count
        G["n_windows_ob"] = (zmat > 2.0).sum(axis=1)    # overbought count
    else:
        G["n_windows_os"] = 0
        G["n_windows_ob"] = 0
    return G.replace([np.inf, -np.inf], np.nan)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])
    print("=" * 74)
    print("ADAPTIVE BRAIN — STAGE 1: signal-replay dataset")
    print("=" * 74)

    strategies = load_v11_strategies()
    logger.info(f"loaded {len(strategies)} deployed strategies")

    nq_5m = _utc(load_intraday_5min("nq"))
    nq_1m = _utc(load_intraday_1min("nq"))
    es_5m = _utc(load_intraday_5min("es"))
    try:
        rty_5m = _utc(load_intraday_5min("rty"))
    except Exception:
        rty_5m = None
    try:
        vix_5m = _utc(load_vix_5min())
    except Exception:
        vix_5m = None
    logger.info(f"NQ 5m={len(nq_5m):,}  NQ 1m={len(nq_1m):,}  ES 5m={len(es_5m):,}")

    idx = nq_5m.index
    a14 = atr(nq_5m["high"], nq_5m["low"], nq_5m["close"], 14)

    # ---- Z-score series per (family, window) -------------------------------
    es_c = es_5m["close"]
    vix_c = vix_5m["close"] if vix_5m is not None else None
    z_series: dict[tuple[str, int], pd.Series] = {}
    es_z_by_win: dict[int, pd.Series] = {}
    for s in strategies:
        key = (s.family, s.z_window)
        if key in z_series:
            continue
        if s.family == "es":
            z = compute_div_z(nq_5m["close"], es_c, s.z_window)
            es_z_by_win[s.z_window] = z
        elif s.family == "vix" and vix_c is not None:
            z = compute_div_z(nq_5m["close"], vix_c, s.z_window)
        else:
            z = pd.Series(np.nan, index=idx)
        z_series[key] = z

    # ---- VIX regime series (for VIX-gated contexts) ------------------------
    if vix_c is not None:
        vc = vix_c.reindex(idx, method="ffill")
        vix_pct_s = vc.rolling(500).rank(pct=True)
        vix_z_s = (vc - vc.rolling(200).mean()) / vc.rolling(200).std()
    else:
        vix_pct_s = pd.Series(np.nan, index=idx)
        vix_z_s = pd.Series(np.nan, index=idx)

    ny = idx.tz_convert(NY)
    ny_hour = ny.hour.to_numpy()
    ny_min = ny.minute.to_numpy()

    # ---- context masks (vectorised in_time_context) ------------------------
    ctx_masks: dict[str, np.ndarray] = {}
    for ctx in sorted({s.time_context for s in strategies}):
        mask = np.array([
            in_time_context(ctx, int(ny_hour[i]), int(ny_min[i]),
                             vix_pct=vix_pct_s.iloc[i], vix_z=vix_z_s.iloc[i])
            for i in range(len(idx))
        ])
        ctx_masks[ctx] = mask
        logger.info(f"  context {ctx:<14} bars active: {mask.sum():,}")

    # ---- global per-bar features -------------------------------------------
    logger.info("building global feature matrix ...")
    G = build_global_features(nq_5m, es_5m, rty_5m, vix_5m, es_z_by_win)
    Gv = {col: G[col].to_numpy() for col in G.columns}

    nq1m_idx = nq_1m.index
    nq1m_arr = nq_1m[["open", "high", "low", "close"]].to_numpy()
    a14v = a14.to_numpy()
    n = len(idx)

    # ---- replay every strategy ---------------------------------------------
    logger.info("replaying strategies ...")
    rows: list[dict] = []
    for s in strategies:
        z = z_series[(s.family, s.z_window)].to_numpy()
        cmask = ctx_masks[s.time_context]
        if s.side == "LONG":
            cross = z < -s.z_threshold
        else:
            cross = z > s.z_threshold
        fires = np.where(cmask & cross & np.isfinite(z))[0]
        for i in fires:
            if i + 1 >= n:
                continue
            entry_ts = idx[i + 1]
            entry_loc = nq1m_idx.searchsorted(entry_ts)
            sim = simulate_trade(s.side, entry_loc, nq1m_arr, nq1m_idx,
                                 a14v[i], s.stop_atr, s.target_atr, s.max_hold_min)
            if sim is None:
                continue
            row = {
                "strategy": s.name,
                "family": s.family,
                "side": s.side,
                "signal_ts": idx[i],
                "entry_ts": entry_ts,
                # signal params
                "z_value": float(z[i]),
                "z_window": s.z_window,
                "z_threshold": s.z_threshold,
                "z_excess": abs(float(z[i])) - s.z_threshold,
                "stop_atr": s.stop_atr,
                "target_atr": s.target_atr,
                "rr": s.target_atr / s.stop_atr,
                "max_hold_min": s.max_hold_min,
                "side_long": int(s.side == "LONG"),
                "family_vix": int(s.family == "vix"),
            }
            for col in G.columns:
                row[col] = Gv[col][i]
            row.update(sim)
            rows.append(row)

    df = pd.DataFrame(rows).sort_values("signal_ts").reset_index(drop=True)
    logger.info(f"replayed {len(df):,} signal firings")

    # ---- second pass: concurrency + strategy recent hit-rate ---------------
    concurrency = df.groupby("signal_ts").size()
    df["n_concurrent_fires"] = df["signal_ts"].map(concurrency).astype(int)

    # A strategy's recent performance, point-in-time: only trades whose EXIT
    # had already happened by this trade's entry count — entry-order + shift
    # would leak the outcome of a still-open overlapping trade.
    df["strat_recent_winrate"] = np.nan
    df["strat_recent_r"] = np.nan
    df["strat_recent_n"] = 0
    for name, g in df.groupby("strategy"):
        g = g.sort_values("entry_ts")
        entries = g["entry_ts"].to_numpy()
        exits = g["exit_ts"].to_numpy()
        prof = g["profitable"].to_numpy()
        rmul = g["r_multiple"].to_numpy()
        wr = np.full(len(g), np.nan)
        rr = np.full(len(g), np.nan)
        nn = np.zeros(len(g), dtype=int)
        for pos in range(len(g)):
            elig = np.where(exits <= entries[pos])[0]
            if len(elig):
                recent = elig[-20:]
                wr[pos] = prof[recent].mean()
                rr[pos] = rmul[recent].mean()
                nn[pos] = len(recent)
        df.loc[g.index, "strat_recent_winrate"] = wr
        df.loc[g.index, "strat_recent_r"] = rr
        df.loc[g.index, "strat_recent_n"] = nn

    df.to_csv(OUT_CSV, index=False)

    overall_wr = df["win"].mean()
    overall_r = df["r_multiple"].mean()
    summary = {
        "n_firings": int(len(df)),
        "n_strategies": int(df["strategy"].nunique()),
        "date_range": [str(df["signal_ts"].min()), str(df["signal_ts"].max())],
        "overall_target_hit_rate": round(float(overall_wr), 4),
        "overall_profitable_rate": round(float(df["profitable"].mean()), 4),
        "overall_avg_r": round(float(overall_r), 4),
        "exit_reason_mix": {k: int(v) for k, v in df["exit_reason"].value_counts().items()},
        "n_features": int(len(G.columns)) + 11,
        "feature_columns": list(G.columns),
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2))

    print("\n" + "=" * 74)
    print(f"  firings replayed : {len(df):,}")
    print(f"  strategies       : {df['strategy'].nunique()}")
    print(f"  date range       : {summary['date_range'][0][:10]} -> "
          f"{summary['date_range'][1][:10]}")
    print(f"  target-hit rate  : {overall_wr*100:.1f}%")
    print(f"  profitable rate  : {df['profitable'].mean()*100:.1f}%")
    print(f"  avg R-multiple   : {overall_r:+.3f}")
    print(f"  exit mix         : {summary['exit_reason_mix']}")
    print(f"  features/row     : {summary['n_features']}")
    print(f"\nWrote {OUT_CSV.relative_to(PROJECT_ROOT)} "
          f"({OUT_CSV.stat().st_size/1e6:.1f} MB)")
    print(f"Wrote {OUT_SUMMARY.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
