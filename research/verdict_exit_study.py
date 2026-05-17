"""
THE 15-MINUTE VERDICT — does the bot's own reversion clock improve it?

price_flow_study.py found: a trade green at the 15-min mark wins ~79% of
the time; a trade RED at 15 min wins only ~23% and averages -0.48R. The
direction of these mean-reversion trades is mostly decided early even
though the magnitude takes the full 90 min.

This script tests whether ACTING on that — exiting a still-open trade at
the verdict bar if it is underwater — actually helps the funded account.
It is not a filter (no entry is blocked); it is the strategy managing the
trade on its own live P&L, informed by the measured time-structure.

Re-simulates all 97 deployed strategies with a 1-min walk that records the
baseline exit AND the verdict exit for verdict bars {2,3,4} (10/15/20 min).
Each variant's trades are run through the same 100-trial 180-day Lucid
Monte Carlo as the deployment. Output: data/verdict_exit_study.json
"""
from __future__ import annotations
import json
import logging
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import research.pattern_miner_v6 as pmv6
from research.pattern_miner_v6 import (
    build_v6_features, StrategyDef, MNQ_DPP, COMM_PER,
)
from research.pattern_miner_v7 import build_v7_extras
from research.pattern_miner_v8 import build_v8_extras
from research.pattern_miner_v9 import build_v9_extras
from research.pattern_miner_v11 import build_v11_extras, make_v11_detector_dicts
from research.pattern_miner_v12 import make_v12_detector_dicts
from research.pattern_miner_v13 import build_v13_extras, make_v13_detector_dicts
from research.local_data_loader import (
    load_daily, load_intraday_1min, load_intraday_5min, load_vix_5min,
)
from research.mc_full_pass_rate import (
    run_one, FEE_PER_ATTEMPT, INITIAL_BALANCE,
)
from research.price_flow_study import load_deployed_specs

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
OUT_PATH = DATA / "verdict_exit_study.json"
logger = logging.getLogger("verdict")

VERDICT_BARS = [2, 3, 4]      # 5-min bars after entry = 10/15/20 min
EXIT_SLIP_PT = 1.0            # market-exit slippage for a verdict close-out


def simulate(F, nq_5m, nq_1m, strat: StrategyDef, contexts_d, triggers_d):
    """Walk every fired trade once; return baseline + verdict-exit pts.

    Mirrors label_strategy's entry + 1-min stop/target walk, but also
    captures the mark-to-market at each verdict checkpoint so a verdict
    exit can be evaluated without re-walking.
    """
    ctx_masks = []
    for cn in strat.contexts:
        m = contexts_d[cn](F).rolling(strat.context_window_bars).max() > 0
        ctx_masks.append(m.fillna(False))
    ctx_active = ctx_masks[0] if ctx_masks else pd.Series(True, index=F.index)
    for m in ctx_masks[1:]:
        ctx_active &= m
    trig = triggers_d[strat.trigger](F).fillna(False)
    fires = (ctx_active & trig).to_numpy()

    nq5_idx = nq_5m.index
    nq1_idx = nq_1m.index
    rows = []
    for i in np.where(fires)[0]:
        if i + 1 >= len(nq5_idx):
            continue
        entry_5m_ts = nq5_idx[i + 1]
        loc1 = nq1_idx.searchsorted(entry_5m_ts)
        if loc1 >= len(nq1_idx):
            continue
        atr14 = F.iloc[i]["atr14"]
        if not (np.isfinite(atr14) and atr14 > 0):
            continue
        entry_raw = float(nq_1m.iloc[loc1]["open"])
        stop_pts = strat.stop_atr * atr14
        tgt_pts = strat.target_atr * atr14
        if strat.side == "LONG":
            entry = entry_raw + pmv6.SLIPPAGE_PT
            stop_px, tgt_px = entry - stop_pts, entry + tgt_pts
        else:
            entry = entry_raw - pmv6.SLIPPAGE_PT
            stop_px, tgt_px = entry + stop_pts, entry - tgt_pts

        end_ts = entry_5m_ts + pd.Timedelta(minutes=strat.max_hold_min)
        win = nq_1m.loc[entry_5m_ts + pd.Timedelta(minutes=1):end_ts]
        if win.empty:
            continue
        verdict_ts = {vb: entry_5m_ts + pd.Timedelta(minutes=vb * 5)
                      for vb in VERDICT_BARS}
        mtm_at = {vb: None for vb in VERDICT_BARS}     # signed pts, pre-hit
        base_outcome, base_exit, base_hold = "TIME", float(win.iloc[-1]["close"]), strat.max_hold_min
        hit_ts = None
        for ts1, bar in win.iterrows():
            bh, bl = float(bar["high"]), float(bar["low"])
            # snapshot MTM at each verdict checkpoint not yet hit
            for vb in VERDICT_BARS:
                if mtm_at[vb] is None and ts1 >= verdict_ts[vb] and hit_ts is None:
                    px = float(bar["close"])
                    mtm_at[vb] = (px - entry) if strat.side == "LONG" else (entry - px)
            if strat.side == "LONG":
                stop_hit, tgt_hit = bl <= stop_px, bh >= tgt_px
            else:
                stop_hit, tgt_hit = bh >= stop_px, bl <= tgt_px
            if stop_hit:
                base_outcome = "STOP"
                base_exit = (stop_px - pmv6.ADVERSE_SLIP_PT if strat.side == "LONG"
                             else stop_px + pmv6.ADVERSE_SLIP_PT)
                hit_ts = ts1
                break
            if tgt_hit:
                base_outcome, base_exit, hit_ts = "TARGET", tgt_px, ts1
                break
        if hit_ts is not None:
            base_hold = (hit_ts - entry_5m_ts).total_seconds() / 60.0
        base_pts = ((base_exit - entry) if strat.side == "LONG"
                    else (entry - base_exit))

        row = {"entry_ts": entry_5m_ts, "side": strat.side,
               "stop_pts": stop_pts, "base_pts": base_pts,
               "base_hold_min": base_hold}
        # verdict variants: if the trade reached the checkpoint un-hit and
        # underwater, exit there at the verdict close (minus exit slippage)
        for vb in VERDICT_BARS:
            m = mtm_at[vb]
            if m is not None and m < 0:
                row[f"v{vb}_pts"] = m - EXIT_SLIP_PT
                row[f"v{vb}_hold"] = vb * 5
            else:
                row[f"v{vb}_pts"] = base_pts
                row[f"v{vb}_hold"] = base_hold
        rows.append(row)
    return rows


def build_universe(rows: list[dict], pts_key: str, hold_key: str) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    out = pd.DataFrame({
        "entry_ts": pd.to_datetime(df["entry_ts"]),
        "side": df["side"],
        "pts": df[pts_key].astype(float),
        "stop_pts": df["stop_pts"].astype(float),
        "max_hold_min": df[hold_key].astype(float),
    })
    if out["entry_ts"].dt.tz is None:
        out["entry_ts"] = out["entry_ts"].dt.tz_localize("UTC")
    return out.sort_values("entry_ts").reset_index(drop=True)


def monte_carlo(sigs: pd.DataFrame, n=100):
    rng = random.Random(7)
    pool = pd.date_range("2025-01-01", "2025-06-30", freq="3D", tz="UTC")
    trials = [run_one(sigs, pool[rng.randint(0, len(pool) - 1)],
                      pool[rng.randint(0, len(pool) - 1)] + pd.Timedelta(days=180))
              for _ in range(n)]
    survs = [t for t in trials if not t["halted"]]
    pr = len(survs) / n
    avg_p = float(np.mean([t["profit"] for t in survs])) if survs else 0.0
    med_p = float(np.median([t["profit"] for t in survs])) if survs else 0.0
    wr = [t["n_wins"] / t["n_trades"] for t in trials if t["n_trades"] > 0]
    return {
        "pass_rate": pr,
        "avg_survivor_profit": avg_p,
        "median_survivor_profit": med_p,
        "avg_win_rate": float(np.mean(wr)) if wr else 0.0,
        "avg_trades": float(np.mean([t["n_trades"] for t in trials])),
        "ev_per_attempt": pr * avg_p - (1 - pr) * FEE_PER_ATTEMPT,
    }


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])

    logger.info("Loading data + features...")
    nq_5m = load_intraday_5min("nq")
    nq_1m = load_intraday_1min("nq")
    daily = load_daily("nq")
    es_5m = load_intraday_5min("es")
    rty_5m = load_intraday_5min("rty")
    vix_5m = load_vix_5min()
    for df in (nq_5m, nq_1m, daily, es_5m, rty_5m, vix_5m):
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
    F = build_v6_features(nq_5m, daily, es_5m, rty_5m, vix_5m)
    F = build_v7_extras(F, nq_5m, es_5m, vix_5m)
    F = build_v8_extras(F, nq_5m, daily)
    F = build_v9_extras(F, nq_5m, daily, rty_5m)
    F = build_v11_extras(F, nq_5m, es_5m)
    F = build_v13_extras(F, nq_5m, rty_5m, vix_5m)
    cd11, td11 = make_v11_detector_dicts(F)
    cd12, _ = make_v12_detector_dicts(F)
    cd13, td13 = make_v13_detector_dicts(F)
    contexts_d = {**cd11, **cd12, **cd13}
    triggers_d = {**td11, **td13}

    specs = load_deployed_specs()
    logger.info(f"Re-simulating {len(specs)} deployed strategies...")
    all_rows = []
    for i, s in enumerate(specs):
        if i % 15 == 0:
            logger.info(f"  {i+1}/{len(specs)}...")
        strat = StrategyDef(
            name=s["name"], side=s["side"], contexts=s["contexts"],
            trigger=s["trigger"], context_window_bars=5,
            stop_atr=s["stop_atr"], target_atr=s["target_atr"],
            max_hold_min=s["max_hold_min"],
        )
        try:
            all_rows.extend(simulate(F, nq_5m, nq_1m, strat,
                                     contexts_d, triggers_d))
        except Exception as e:
            logger.warning(f"  {s['name']} skipped: {e}")

    logger.info(f"Simulated {len(all_rows):,} trades")

    # per-trade stats + Monte Carlo for baseline and each verdict variant
    variants = {"baseline": ("base_pts", "base_hold_min")}
    for vb in VERDICT_BARS:
        variants[f"verdict_bar{vb}"] = (f"v{vb}_pts", f"v{vb}_hold")

    results = {}
    for name, (pk, hk) in variants.items():
        uni = build_universe(all_rows, pk, hk)
        pts = uni["pts"].to_numpy()
        n_changed = sum(1 for r in all_rows if r[pk] != r["base_pts"])
        mc = monte_carlo(uni)
        results[name] = {
            "n_trades": int(len(uni)),
            "n_trades_changed_vs_baseline": int(n_changed),
            "raw_win_rate": round(float((pts > 0).mean()), 4),
            "raw_mean_pts": round(float(pts.mean()), 3),
            "raw_total_pts": round(float(pts.sum()), 1),
            "mc": {k: round(v, 2) for k, v in mc.items()},
        }
        logger.info(f"  {name}: WR {results[name]['raw_win_rate']*100:.1f}%  "
                    f"MC pass {mc['pass_rate']*100:.0f}%  "
                    f"EV ${mc['ev_per_attempt']:,.0f}")

    OUT_PATH.write_text(json.dumps(results, indent=2))

    print("\n" + "=" * 78)
    print("15-MINUTE VERDICT EXIT — funded-account impact (100-trial MC)")
    print("=" * 78)
    print(f"{'variant':<16}{'trades chg':>11}{'rawWR':>8}{'rawPts':>10}"
          f"{'MC pass':>9}{'medProfit':>12}{'EV/attempt':>12}")
    print("-" * 78)
    for name, r in results.items():
        mc = r["mc"]
        print(f"{name:<16}{r['n_trades_changed_vs_baseline']:>11}"
              f"{r['raw_win_rate']*100:>7.1f}%{r['raw_total_pts']:>10,.0f}"
              f"{mc['pass_rate']*100:>8.0f}%${mc['median_survivor_profit']:>10,.0f}"
              f"${mc['ev_per_attempt']:>10,.0f}")
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
