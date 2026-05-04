"""
Raw-signal strategy validator.

Skips the engine entirely. Just: for each candidate strategy, take every
signal it fires across the year, simulate the trade outcome on 1-min bars
(triple-barrier with stop/target/max-hold), record P&L. Compute the 5
rigorous tests on the result.

Speed: ~30-90 seconds for the full 221-strategy universe over 12 months.
We run the engine's signal generators ONCE in vectorised mode, then
walk 1-min exits for each signal. No engine filters, no Lucid guard —
pure raw strategy edge.

This tells us which strategies have inherent edge. Engine filters and
Lucid sizing are layered ON TOP afterwards.

Output:
  data/raw_validation_results.json
"""
from __future__ import annotations

import json
import logging
import math
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from research.local_data_loader import (
    load_daily,
    load_intraday_1min,
    load_intraday_5min,
)
from research.signal_engine import ALL_SIGNALS
from research.signal_filters import (
    ADVERSE_SLIPPAGE_POINTS,
    SLIPPAGE_POINTS,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
OUT_PATH = DATA / "raw_validation_results.json"
VAL_PATH = DATA / "validation_results.json"

logger = logging.getLogger("raw_validator")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("signal_engine").setLevel(logging.WARNING)

MNQ_DPP  = 2.0     # $/pt/MNQ
MNQ_COMM = 0.40    # round-trip per MNQ
MAX_HOLD_MIN = 60
COOLDOWN_MIN = 30  # min minutes after a closed trade before same strategy can re-enter
                    # (mirrors signal_filters.cooldown_filter on the live bot)

# Five rigorous tests (raw, before engine filters)
MIN_SAMPLE = 30
MIN_WR     = 0.55
MIN_PF     = 1.40
MIN_SHARPE = 0.80
CPCV_FOLDS = 5
CPCV_MIN_POSITIVE_FRAC = 0.6


# ----- Default stop/target per strategy name (parsed from name) -----
def _parse_stop_target(name: str) -> tuple[float, float]:
    """V3_LONG_S15T30_69 → (15, 30). Falls back to (15, 30) for unknown names."""
    import re
    m = re.match(r"^[A-Z0-9]+_(LONG|SHORT)_S(\d+)T(\d+)_\d+$", name)
    if m:
        return float(m.group(2)), float(m.group(3))
    # Hand-coded named signals — try validation_results.json lookup
    return 15.0, 30.0


@dataclass
class RawResult:
    name: str
    side: str = "?"
    n_raw: int = 0
    n_executed: int = 0
    n_wins: int = 0
    n_losses: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    net_pnl_per_contract: float = 0.0   # $ per 1 MNQ
    sharpe: float = 0.0
    avg_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    max_consecutive_losses: int = 0
    cpcv_test_folds_positive: int = 0
    pass_sample: bool = False
    pass_wr: bool = False
    pass_pf: bool = False
    pass_sharpe: bool = False
    pass_cpcv: bool = False
    passes_all: bool = False
    pnls: list[float] = field(default_factory=list)
    timestamps: list[str] = field(default_factory=list)


def _walk_exit_1m_with_ts(bars_1m: pd.DataFrame, entry_ts: pd.Timestamp,
                            side: str, entry_filled: float,
                            stop_px: float, target_px: float
                            ) -> tuple[float, str, pd.Timestamp]:
    """Walk 1-min bars from entry+1 to entry+max_hold; first stop or target hit
    closes the trade. Returns (exit_px_filled, reason, exit_ts)."""
    start = entry_ts + pd.Timedelta(minutes=1)
    end = entry_ts + pd.Timedelta(minutes=MAX_HOLD_MIN)
    try:
        window = bars_1m.loc[start:end]
    except KeyError:
        return entry_filled, "TIME", entry_ts
    if window.empty:
        return entry_filled, "TIME", entry_ts
    for ts_1m, bar in window.iterrows():
        h = float(bar["high"]); l = float(bar["low"])
        if side == "LONG":
            stop_hit = l <= stop_px
            tgt_hit  = h >= target_px
        else:
            stop_hit = h >= stop_px
            tgt_hit  = l <= target_px
        if stop_hit and tgt_hit:
            return ((stop_px - ADVERSE_SLIPPAGE_POINTS) if side == "LONG"
                    else (stop_px + ADVERSE_SLIPPAGE_POINTS)), "STOP", ts_1m
        if stop_hit:
            return ((stop_px - ADVERSE_SLIPPAGE_POINTS) if side == "LONG"
                    else (stop_px + ADVERSE_SLIPPAGE_POINTS)), "STOP", ts_1m
        if tgt_hit:
            return target_px, "TARGET", ts_1m
    return float(window.iloc[-1]["close"]), "TIME", window.index[-1]


def _compute_pnl(side: str, entry_filled: float, exit_filled: float) -> float:
    pts = (exit_filled - entry_filled) if side == "LONG" else (entry_filled - exit_filled)
    return pts * MNQ_DPP - MNQ_COMM


def _metrics(pnls: list[float]) -> dict:
    if not pnls:
        return dict(n=0, win_rate=0, profit_factor=0, net_pnl=0,
                    sharpe=0, avg=0, avg_win=0, avg_loss=0, mcl=0)
    arr = np.array(pnls)
    wins = arr[arr > 0]; losses = arr[arr <= 0]
    gw = float(wins.sum()); gl = float(-losses.sum())
    pf = (gw / gl) if gl > 0 else (math.inf if gw > 0 else 0)
    sh = float(arr.mean() / arr.std()) if arr.std() > 0 else 0.0
    mcl = 0; cur = 0
    for p in arr:
        if p <= 0: cur += 1; mcl = max(mcl, cur)
        else: cur = 0
    return dict(
        n=len(arr),
        win_rate=float(len(wins) / len(arr)),
        profit_factor=float(min(pf, 999.0)),
        net_pnl=float(arr.sum()),
        sharpe=sh,
        avg=float(arr.mean()),
        avg_win=float(wins.mean()) if len(wins) else 0.0,
        avg_loss=float(losses.mean()) if len(losses) else 0.0,
        mcl=mcl,
    )


def _cpcv_pass_count(pnls: list[float], folds: int = CPCV_FOLDS) -> int:
    if len(pnls) < folds * 5:
        return 0
    arr = np.array(pnls)
    fold_size = len(arr) // folds
    positive = 0
    for i in range(folds):
        a = i * fold_size
        b = (i + 1) * fold_size if i < folds - 1 else len(arr)
        if arr[a:b].sum() > 0: positive += 1
    return positive


def main():
    print(f"\n{'='*72}\nRAW-SIGNAL STRATEGY VALIDATOR\n{'='*72}")
    print(f"window: last 365 days of NQ")
    print(f"tests:  n>={MIN_SAMPLE}  WR>={MIN_WR*100:.0f}%  "
          f"PF>={MIN_PF}  Sharpe>={MIN_SHARPE}  CPCV {CPCV_FOLDS}-fold "
          f"(>={CPCV_MIN_POSITIVE_FRAC*100:.0f}% positive)")

    # Load
    logger.info("loading bars …")
    bars_5m = load_intraday_5min("nq")
    bars_1m = load_intraday_1min("nq")
    daily   = load_daily("nq")
    for df in (bars_5m, bars_1m, daily):
        if df.index.tz is None: df.index = df.index.tz_localize("UTC")
    end = bars_5m.index.max()
    start = end - pd.Timedelta(days=365)
    bars_5m = bars_5m.loc[start:end]
    bars_1m = bars_1m.loc[start - pd.Timedelta(hours=2):end + pd.Timedelta(hours=2)]
    logger.info(f"window: {start} → {end}  ({len(bars_5m):,} 5-min bars)")

    # Per-strategy stop/target lookup from validation_results.json
    val = json.loads(VAL_PATH.read_text())
    sigs_meta = val.get("signals") or {}
    candidate_names = sorted(sigs_meta.keys())
    logger.info(f"candidates: {len(candidate_names)} strategies")

    # ---- Pre-compute every strategy's signal-firing bars (vectorised) ----
    logger.info("running every signal generator (vectorised) …")
    pre_t0 = time.time()
    by_strategy: dict[str, list[dict]] = defaultdict(list)
    for sig_obj in ALL_SIGNALS:
        try:
            sigs = sig_obj.generate(bars_5m, daily)
        except Exception as e:
            logger.debug(f"  {type(sig_obj).__name__} raised: {e}")
            continue
        if sigs is None or sigs.empty:
            continue
        for _, row in sigs.iterrows():
            ts = row["signal_time"]
            if ts.tz is None: ts = ts.tz_localize("UTC")
            by_strategy[row["signal_name"]].append({
                "ts": ts,
                "side": row["side"],
                "entry_px": float(row["entry_px"]),
            })
    logger.info(f"  done in {time.time()-pre_t0:.1f}s — "
                f"{sum(len(v) for v in by_strategy.values()):,} raw signals "
                f"across {len(by_strategy):,} strategies that fire at least once")

    # ---- For each candidate, simulate every signal's outcome ----
    # Realism rules (mirrors live bot):
    #   1. ONE position at a time per strategy — new signal during open
    #      trade is skipped (no doubling up on the same edge)
    #   2. After a close, COOLDOWN_MIN minutes must elapse before the
    #      same strategy can re-enter (otherwise persistent conditions
    #      generate fake duplicate "trades" that all hit the same target)
    results: list[RawResult] = []
    t0 = time.time()
    for i, name in enumerate(candidate_names):
        events = sorted(by_strategy.get(name) or [], key=lambda e: e["ts"])
        meta = sigs_meta.get(name) or {}
        stop_pts = float(meta.get("stop_pts") or _parse_stop_target(name)[0])
        tgt_pts  = float(meta.get("target_pts") or _parse_stop_target(name)[1])
        res = RawResult(name=name, n_raw=len(events))
        # Track when this strategy can fire next (last_exit_ts + cooldown)
        cleared_at: Optional[pd.Timestamp] = None
        for ev in events:
            ts = ev["ts"]
            # Skip if still cooling down from prior trade
            if cleared_at is not None and ts < cleared_at:
                continue
            res.side = ev["side"]
            entry_raw = ev["entry_px"]
            entry_filled = entry_raw + SLIPPAGE_POINTS if ev["side"] == "LONG" \
                                                       else entry_raw - SLIPPAGE_POINTS
            stop_px = entry_raw - stop_pts if ev["side"] == "LONG" else entry_raw + stop_pts
            tgt_px  = entry_raw + tgt_pts  if ev["side"] == "LONG" else entry_raw - tgt_pts
            # Walk the exit and ALSO track when the trade closed so cooldown
            # starts from the actual close, not the entry.
            exit_filled, reason, exit_ts = _walk_exit_1m_with_ts(
                bars_1m, ts, ev["side"], entry_filled, stop_px, tgt_px)
            pnl = _compute_pnl(ev["side"], entry_filled, exit_filled)
            res.pnls.append(pnl)
            res.timestamps.append(ts.isoformat())
            cleared_at = exit_ts + pd.Timedelta(minutes=COOLDOWN_MIN)
        m = _metrics(res.pnls)
        res.n_executed = m["n"]
        res.n_wins     = int(round(m["win_rate"] * m["n"]))
        res.n_losses   = m["n"] - res.n_wins
        res.win_rate   = m["win_rate"]
        res.profit_factor = m["profit_factor"]
        res.net_pnl_per_contract = m["net_pnl"]
        res.sharpe = m["sharpe"]
        res.avg_pnl = m["avg"]; res.avg_win = m["avg_win"]; res.avg_loss = m["avg_loss"]
        res.max_consecutive_losses = m["mcl"]
        res.cpcv_test_folds_positive = _cpcv_pass_count(res.pnls)
        res.pass_sample = res.n_executed >= MIN_SAMPLE
        res.pass_wr     = res.win_rate    >= MIN_WR
        res.pass_pf     = res.profit_factor >= MIN_PF
        res.pass_sharpe = res.sharpe       >= MIN_SHARPE
        res.pass_cpcv   = res.cpcv_test_folds_positive >= int(math.ceil(CPCV_FOLDS * CPCV_MIN_POSITIVE_FRAC))
        res.passes_all  = all([res.pass_sample, res.pass_wr, res.pass_pf,
                                 res.pass_sharpe, res.pass_cpcv])
        results.append(res)
        if (i+1) % 25 == 0 or (i+1) == len(candidate_names):
            elapsed = time.time() - t0
            survivors = sum(1 for r in results if r.passes_all)
            logger.info(f"  {i+1:>3}/{len(candidate_names)}  "
                        f"survivors so far: {survivors}  "
                        f"elapsed: {elapsed:.1f}s")

    # ---- Save + summary ----
    out = {
        "window_days": 365,
        "tests": dict(min_sample=MIN_SAMPLE, min_wr=MIN_WR, min_pf=MIN_PF,
                      min_sharpe=MIN_SHARPE, cpcv_folds=CPCV_FOLDS,
                      cpcv_min_positive_frac=CPCV_MIN_POSITIVE_FRAC),
        "results": [r.__dict__ for r in results],
        "summary": {
            "n_total": len(results),
            "n_pass_sample":  sum(1 for r in results if r.pass_sample),
            "n_pass_wr":      sum(1 for r in results if r.pass_wr),
            "n_pass_pf":      sum(1 for r in results if r.pass_pf),
            "n_pass_sharpe":  sum(1 for r in results if r.pass_sharpe),
            "n_pass_cpcv":    sum(1 for r in results if r.pass_cpcv),
            "n_pass_all":     sum(1 for r in results if r.passes_all),
        },
    }
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))

    survivors = [r for r in results if r.passes_all]
    print(f"\n{'='*72}\nSUMMARY\n{'='*72}")
    print(f"  total candidates:    {len(results)}")
    print(f"  passed sample (n>={MIN_SAMPLE}):       {out['summary']['n_pass_sample']}")
    print(f"  passed WR (>={MIN_WR*100:.0f}%):           {out['summary']['n_pass_wr']}")
    print(f"  passed PF (>={MIN_PF}):              {out['summary']['n_pass_pf']}")
    print(f"  passed Sharpe (>={MIN_SHARPE}):       {out['summary']['n_pass_sharpe']}")
    print(f"  passed CPCV:                          {out['summary']['n_pass_cpcv']}")
    print(f"  passed ALL 5 tests:                   {len(survivors)}")
    if survivors:
        print(f"\n=== TOP 30 RAW-SIGNAL SURVIVORS (by net pnl/contract) ===")
        for r in sorted(survivors, key=lambda r: -r.net_pnl_per_contract)[:30]:
            print(f"  {r.name:<32}  {r.side:<5}  n={r.n_executed:>4}  "
                  f"WR={r.win_rate*100:.1f}%  PF={r.profit_factor:.2f}  "
                  f"Sh={r.sharpe:+.2f}  CPCV={r.cpcv_test_folds_positive}/{CPCV_FOLDS}  "
                  f"pnl=${r.net_pnl_per_contract:+,.0f}")
    print(f"\nWrote {OUT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
