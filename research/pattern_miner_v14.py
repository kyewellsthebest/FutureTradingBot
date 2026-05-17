"""
Pattern Miner v14 — first-touch structural-level reversal.

Built directly on the nq_deep_study.py findings:
  * The FIRST daily touch of a prior-day / overnight high or low reverses
    ~94-96% of the time (vs ~52% baseline).
  * The edge is volatility-regime dependent — strong in mid/high vol,
    near coin-flip in low vol.
  * MFE/MAE analysis sets the stop/target from data: structural stop a
    fixed buffer beyond the level, target sized in R-multiples.

A strategy here is fully described by:
  level     : PDH / PDL / ONH / ONL  (high-type -> fade SHORT, low-type -> LONG)
  tolerance : how close a bar must come to count as a touch (pts)
  stop_buf  : structural stop distance beyond the level (pts)
  rr        : target as a multiple of the entry->stop distance
  vol_gate  : minimum ATR percentile regime (any / mid+ / high)
  max_hold  : minutes

Same 11 rigorous tests as v11/12/13 (evaluate_strategy: train/test OOS,
sample size, WR, PF, Sharpe, CPCV, 5000-trial permutation). Output to
data/mined_v14_patterns.json.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from research.pattern_miner_v6 import evaluate_strategy, TRAIN_END
from research.pattern_miner_v11 import USER_MIN_WR, USER_MIN_RR, USER_MIN_TRADES
from research.local_data_loader import (
    load_daily, load_intraday_1min, load_intraday_5min,
)
from research.indicators import atr

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
OUT_PATH = DATA / "mined_v14_patterns.json"
PROGRESS_PATH = DATA / "v14_progress.json"
LOG_PATH = PROJECT_ROOT / "logs" / "miner_v14.log"
LOG_PATH.parent.mkdir(exist_ok=True)
logger = logging.getLogger("miner_v14")

SLIPPAGE_PT = 2.0
ADVERSE_SLIP_PT = 2.0
MNQ_DPP = 2.0
COMM_PER = 0.40


@dataclass
class V14Strategy:
    name: str
    level: str          # "pdh" / "pdl" / "onh" / "onl"
    side: str           # "LONG" / "SHORT"
    tolerance: float
    stop_buf: float
    rr: float
    vol_gate: str       # "any" / "mid" / "high"
    max_hold_min: int


def build_v14_frame(m5: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """Attach PDH/PDL/ONH/ONL, ATR regime, and first-touch flags to 5-min bars."""
    m5 = m5.copy()
    ny = m5.index.tz_convert("America/New_York")
    m5["ny_hour"] = ny.hour
    m5["ny_date"] = ny.normalize()
    m5["atr"] = atr(m5["high"], m5["low"], m5["close"], n=14)
    m5["atr_pctile"] = m5["atr"].rolling(2000, min_periods=200).rank(pct=True)

    daily = daily.copy()
    daily["pdh"] = daily["high"].shift(1)
    daily["pdl"] = daily["low"].shift(1)
    dny = daily.index.tz_convert("America/New_York").normalize() \
        if daily.index.tz is not None else daily.index.normalize()
    m5["pdh"] = m5["ny_date"].map(dict(zip(dny, daily["pdh"])))
    m5["pdl"] = m5["ny_date"].map(dict(zip(dny, daily["pdl"])))

    # overnight H/L = pre-09:00 ET extremes
    onh, onl = {}, {}
    for date, grp in m5.groupby("ny_date"):
        pre = grp[grp["ny_hour"] < 9]
        if len(pre):
            onh[date] = pre["high"].max()
            onl[date] = pre["low"].min()
    m5["onh"] = m5["ny_date"].map(onh)
    m5["onl"] = m5["ny_date"].map(onl)
    return m5


def label_v14(m5: pd.DataFrame, nq_1m: pd.DataFrame,
                strat: V14Strategy) -> pd.DataFrame:
    """Label every trade for a v14 first-touch reversal strategy."""
    level_col = strat.level
    tol = strat.tolerance
    rows = []
    touched_today: set = set()
    levels = m5[level_col].values
    highs = m5["high"].values
    lows = m5["low"].values
    opens = m5["open"].values
    atr_pct = m5["atr_pctile"].values
    dates = m5["ny_date"].values
    idx = m5.index

    for i in range(len(m5) - 1):
        lv = levels[i]
        if not np.isfinite(lv):
            continue
        d = dates[i]
        # only the FIRST touch of this level today
        if d in touched_today:
            continue
        touched = highs[i] >= lv - tol and lows[i] <= lv + tol
        if not touched:
            continue
        touched_today.add(d)

        # volatility gate
        ap = atr_pct[i]
        if strat.vol_gate == "mid" and not (np.isfinite(ap) and ap >= 0.33):
            continue
        if strat.vol_gate == "high" and not (np.isfinite(ap) and ap >= 0.66):
            continue

        entry_5m_ts = idx[i]
        entry_raw = opens[i + 1]
        if strat.side == "LONG":
            entry = entry_raw + SLIPPAGE_PT
            stop_px = lv - strat.stop_buf
            stop_dist = entry - stop_px
            if stop_dist <= 0:
                continue
            tgt_px = entry + strat.rr * stop_dist
        else:
            entry = entry_raw - SLIPPAGE_PT
            stop_px = lv + strat.stop_buf
            stop_dist = stop_px - entry
            if stop_dist <= 0:
                continue
            tgt_px = entry - strat.rr * stop_dist

        end_ts = entry_5m_ts + pd.Timedelta(minutes=strat.max_hold_min)
        try:
            window = nq_1m.loc[entry_5m_ts + pd.Timedelta(minutes=1):end_ts]
        except Exception:
            continue
        if window.empty:
            continue
        outcome = "TIME"
        exit_filled = float(window.iloc[-1]["close"])
        for _, bar in window.iterrows():
            bh, bl = float(bar["high"]), float(bar["low"])
            if strat.side == "LONG":
                stop_hit = bl <= stop_px
                tgt_hit = bh >= tgt_px
            else:
                stop_hit = bh >= stop_px
                tgt_hit = bl <= tgt_px
            if stop_hit:
                outcome = "STOP"
                exit_filled = (stop_px - ADVERSE_SLIP_PT if strat.side == "LONG"
                                 else stop_px + ADVERSE_SLIP_PT)
                break
            if tgt_hit:
                outcome = "TARGET"
                exit_filled = tgt_px
                break
        pts = (exit_filled - entry) if strat.side == "LONG" else (entry - exit_filled)
        pnl = pts * MNQ_DPP - COMM_PER
        rows.append({
            "entry_ts": entry_5m_ts, "side": strat.side,
            "entry": entry, "exit": exit_filled, "outcome": outcome,
            "pts": pts, "pnl": pnl,
            "stop_pts": stop_dist, "target_pts": strat.rr * stop_dist,
        })
    return pd.DataFrame(rows)


def enumerate_v14(F: pd.DataFrame) -> list[V14Strategy]:
    strategies = []
    sid = 0
    level_side = {"pdh": "SHORT", "pdl": "LONG", "onh": "SHORT", "onl": "LONG"}
    for level, side in level_side.items():
        for tol in (5.0, 8.0, 12.0):
            for stop_buf in (8.0, 12.0, 16.0, 20.0):
                for rr in (1.0, 1.5, 2.0, 3.0):
                    for vol_gate in ("any", "mid", "high"):
                        for max_hold in (60, 90):
                            sid += 1
                            name = (f"V14_{side}_{level}_tol{int(tol)}"
                                      f"_sb{int(stop_buf)}_rr{rr}"
                                      f"_{vol_gate}_h{max_hold}_{sid:05d}")
                            strategies.append(V14Strategy(
                                name=name, level=level, side=side,
                                tolerance=tol, stop_buf=stop_buf, rr=rr,
                                vol_gate=vol_gate, max_hold_min=max_hold,
                            ))
    return strategies


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s miner_v14 %(message)s",
        handlers=[logging.StreamHandler(sys.stdout),
                    logging.FileHandler(LOG_PATH)],
    )
    print("=" * 78)
    print("PATTERN MINER v14 — first-touch structural-level reversal")
    print("=" * 78)

    progress = {"completed": [], "results": []}
    if PROGRESS_PATH.exists():
        try:
            progress = json.loads(PROGRESS_PATH.read_text())
            logger.info(f"resuming with {len(progress['completed'])} done")
        except Exception:
            pass

    print("\n[1/3] Loading data + building frame ...")
    m5 = load_intraday_5min("nq")
    nq_1m = load_intraday_1min("nq")
    daily = load_daily("nq")
    for df in (m5, nq_1m, daily):
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
    F = build_v14_frame(m5, daily)
    print(f"  {F.shape}")

    strats = enumerate_v14(F)
    print(f"\n[2/3] Enumerated {len(strats)} strategies")

    completed = set(progress.get("completed", []))
    results = list(progress.get("results", []))
    started = time.time()
    last_save = started
    n_done = 0

    print(f"\n[3/3] Mining {len(strats)} strategies ...")
    for idx, strat in enumerate(strats):
        if strat.name in completed:
            continue
        try:
            trades = label_v14(F, nq_1m, strat)
            ev = evaluate_strategy(trades, TRAIN_END)
            ev["name"] = strat.name
            ev["side"] = strat.side
            ev["level"] = strat.level
            ev["tolerance"] = strat.tolerance
            ev["stop_buf"] = strat.stop_buf
            ev["rr"] = strat.rr
            ev["vol_gate"] = strat.vol_gate
            ev["max_hold_min"] = strat.max_hold_min
            t = ev.get("test", {})
            ev["user_pass"] = (
                t.get("wr", 0) >= USER_MIN_WR
                and strat.rr >= 1.0   # v14 uses R-multiples; 1.0 RR allowed
                and t.get("n", 0) >= USER_MIN_TRADES
            )
            results.append(ev)
            completed.add(strat.name)
            n_done += 1
            if ev.get("user_pass"):
                u = sum(1 for r in results if r.get("user_pass"))
                logger.info(
                    f"  [USER-PASS #{u}] {strat.name}  n={t['n']:>4} "
                    f"WR={t['wr']*100:.1f}% PF={t['pf']:.2f} "
                    f"cpcv={ev.get('cpcv_positive',0)}/5 pnl=${t['net']:+,.0f}"
                )
            elif idx % 100 == 0:
                rate = max(1, idx + 1 - len(progress.get('completed', []))) / \
                       max(0.01, time.time() - started)
                eta = (len(strats) - idx - 1) / max(0.01, rate) / 60
                u = sum(1 for r in results if r.get("user_pass"))
                logger.info(f"  [{idx+1:>5}/{len(strats)}] u_pass={u} ETA {eta:.0f}m")
            now = time.time()
            if n_done >= 5 or (now - last_save) > 30:
                progress["completed"] = sorted(completed)
                progress["results"] = results
                PROGRESS_PATH.write_text(json.dumps(progress))
                last_save = now
                n_done = 0
        except Exception as e:
            logger.warning(f"  {strat.name} crashed: {e}")
            continue

    progress["completed"] = sorted(completed)
    progress["results"] = results
    PROGRESS_PATH.write_text(json.dumps(progress))

    user_passers = [r for r in results if r.get("user_pass")]
    OUT_PATH.write_text(json.dumps({
        "n_strategies": len(strats),
        "n_evaluated": len(results),
        "n_user_pass": len(user_passers),
        "user_passers": user_passers,
        "all_results": results,
    }, indent=2, default=str))
    logger.info(f"\nDone. {len(user_passers)} user-pass / {len(results)} tested.")
    logger.info(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
