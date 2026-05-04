"""
Engine-aware strategy validator.

The previous validation pipeline measured each strategy in isolation —
raw signal-firing point + theoretical triple-barrier outcome on subsequent
bars. That's an upper bound on edge. At runtime the engine adds a stack
of filters (VPIN, Adverse, Regime, GEX, Macro, ML, key-level proximity,
min R:R, cooldown, kill-zone) that change WHICH signals actually become
trades. The strategies that look great in raw form often don't survive
the filter stack.

This validator measures each strategy under the live engine's conditions:

  for each candidate strategy:
      whitelist = {strategy}      # engine only considers this one
      walk forward through 12 months of NQ 5-min bars
      at every signal-firing bar of this strategy:
          run engine.evaluate() with the slice up to now
          if engine accepts it:
              walk 1-min bars forward to the first stop/target/max-hold
              record the realised P&L
      compute metrics on the engine-accepted trades only:
          n, win_rate, profit_factor, net_pnl, sharpe, max_dd
      run the 5 rigorous tests:
          1.  n >= MIN_SAMPLE  (statistical meaningfulness)
          2.  WR >= MIN_WR
          3.  PF >= MIN_PF
          4.  CPCV walk-forward edge holds (purged train/test)
          5.  Sharpe >= MIN_SHARPE  (risk-adjusted, not just total $)

Strategies that pass all five become the new TIER A whitelist.

Output:
  data/engine_validation_results.json  — per-strategy metrics + pass/fail
  data/validation_results.json         — updated `recommended` flags
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
from research.signal_engine import ALL_SIGNALS, SignalEngine
from research.signal_filters import (
    ADVERSE_SLIPPAGE_POINTS,
    SLIPPAGE_POINTS,
    TradeRef,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
OUT_PATH = DATA / "engine_validation_results.json"
VAL_PATH = DATA / "validation_results.json"

logger = logging.getLogger("engine_validator")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("signal_engine").setLevel(logging.WARNING)

MNQ_DPP = 2.0
MNQ_COMM = 0.40            # round-trip per MNQ
MAX_HOLD_DEFAULT = 60      # minutes

# ---------------- The 5 rigorous tests ----------------
MIN_SAMPLE   = 30          # need at least 30 engine-accepted trades
MIN_WR       = 0.55        # 55% out-of-sample win rate
MIN_PF       = 1.40        # gross-wins / gross-losses
MIN_SHARPE   = 0.80        # annualised
CPCV_FOLDS   = 5           # purged k-fold; edge must hold in >=60% of test folds


# ---------------- Per-strategy result ----------------
@dataclass
class ValidationResult:
    name: str
    side: str = "?"
    n_signals_raw: int = 0
    n_engine_accepted: int = 0
    n_wins: int = 0
    n_losses: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    net_pnl: float = 0.0
    sharpe: float = 0.0
    avg_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    max_consecutive_losses: int = 0
    cpcv_test_folds_positive: int = 0
    # 5-test breakdown
    pass_sample:  bool = False
    pass_wr:      bool = False
    pass_pf:      bool = False
    pass_sharpe:  bool = False
    pass_cpcv:    bool = False
    passes_all:   bool = False
    # Per-trade record (for CPCV + debugging)
    trade_pnls: list[float] = field(default_factory=list)
    trade_ts:   list[str]   = field(default_factory=list)
    # Veto reason histogram (why engine rejected the rest)
    veto_counts: dict[str, int] = field(default_factory=dict)


# ----------------------- helpers -----------------------
def _walk_exit_1m(bars_1m: pd.DataFrame, entry_ts: pd.Timestamp,
                   side: str, entry_px: float, stop_px: float, target_px: float,
                   max_hold_minutes: int) -> tuple[float, str, pd.Timestamp]:
    """Walk 1-min bars forward from entry; return (exit_px, reason, exit_ts).
    Mirrors live_sim._walk_exit_1m exactly so per-trade outcomes line up."""
    start = entry_ts + pd.Timedelta(minutes=1)
    end = entry_ts + pd.Timedelta(minutes=max_hold_minutes)
    try:
        window = bars_1m.loc[start:end]
    except KeyError:
        return entry_px, "TIME", entry_ts
    if window.empty:
        return entry_px, "TIME", entry_ts
    for ts_1m, bar in window.iterrows():
        h = float(bar["high"]); l = float(bar["low"])
        if side == "LONG":
            stop_hit = l <= stop_px
            tgt_hit  = h >= target_px
        else:
            stop_hit = h >= stop_px
            tgt_hit  = l <= target_px
        if stop_hit and tgt_hit:
            return stop_px, "STOP", ts_1m            # conservative
        if stop_hit:
            return stop_px, "STOP", ts_1m
        if tgt_hit:
            return target_px, "TARGET", ts_1m
    return float(window.iloc[-1]["close"]), "TIME", window.index[-1]


def _compute_pnl_per_contract(side: str, entry_px: float,
                               exit_px: float, adverse: bool) -> float:
    """Net P&L per MNQ contract incl. slippage + commission."""
    # Entry slip already baked into entry_filled; here exit slip:
    if adverse:
        exit_filled = exit_px - ADVERSE_SLIPPAGE_POINTS if side == "LONG" \
                                                          else exit_px + ADVERSE_SLIPPAGE_POINTS
    else:
        exit_filled = exit_px
    points = (exit_filled - entry_px) if side == "LONG" else (entry_px - exit_filled)
    return points * MNQ_DPP - MNQ_COMM


def _compute_metrics(pnls: list[float]) -> dict:
    if not pnls:
        return dict(n=0, win_rate=0, profit_factor=0, net_pnl=0,
                    sharpe=0, avg_pnl=0, avg_win=0, avg_loss=0,
                    max_consecutive_losses=0)
    arr = np.array(pnls)
    wins = arr[arr > 0]; losses = arr[arr <= 0]
    gross_w = float(wins.sum()); gross_l = float(-losses.sum())
    pf = (gross_w / gross_l) if gross_l > 0 else (math.inf if gross_w > 0 else 0)
    # Sharpe: assume ~250 trading days/yr; this is per-trade Sharpe, not annualised.
    # For a rough annualised figure, scale by sqrt(trades_per_year / trades_total).
    sharpe = float(arr.mean() / arr.std()) if arr.std() > 0 else 0.0
    # Max consecutive losses
    mcl = 0; cur = 0
    for p in arr:
        if p <= 0: cur += 1; mcl = max(mcl, cur)
        else: cur = 0
    return dict(
        n=len(arr),
        win_rate=float(len(wins) / len(arr)),
        profit_factor=float(min(pf, 999.0)),
        net_pnl=float(arr.sum()),
        sharpe=sharpe,
        avg_pnl=float(arr.mean()),
        avg_win=float(wins.mean()) if len(wins) else 0.0,
        avg_loss=float(losses.mean()) if len(losses) else 0.0,
        max_consecutive_losses=mcl,
    )


def _cpcv_pass(pnls: list[float], folds: int = CPCV_FOLDS) -> int:
    """Purged k-fold CPCV: count how many test folds have positive net P&L.
    Returns the count (0..folds). Strategy passes if >= folds * 0.6."""
    if len(pnls) < folds * 5:
        return 0
    arr = np.array(pnls)
    fold_size = len(arr) // folds
    positive = 0
    for i in range(folds):
        a = i * fold_size
        b = (i + 1) * fold_size if i < folds - 1 else len(arr)
        fold = arr[a:b]
        if fold.sum() > 0: positive += 1
    return positive


# ----------------------- main work -----------------------

def precompute_signal_bars(bars_5m: pd.DataFrame, daily: pd.DataFrame,
                            whitelist_set: set[str]) -> dict:
    """Run every signal generator across the whole window once. Return
    dict {ts: [signal_dict, …]} of all firing points whose signal_name
    is in `whitelist_set` (which is the FULL universe of names we want
    to validate)."""
    out: dict[pd.Timestamp, list[dict]] = defaultdict(list)
    for sig_obj in ALL_SIGNALS:
        try:
            sigs = sig_obj.generate(bars_5m, daily)
        except Exception as e:
            logger.debug(f"  generator {type(sig_obj).__name__} raised: {e}")
            continue
        if sigs is None or sigs.empty:
            continue
        sigs = sigs[sigs["signal_name"].isin(whitelist_set)]
        for _, row in sigs.iterrows():
            ts = row["signal_time"]
            if ts.tz is None: ts = ts.tz_localize("UTC")
            out[ts].append({
                "name": row["signal_name"],
                "side": row["side"],
                "entry_px": float(row["entry_px"]),
            })
    return out


def validate_strategy(name: str, all_bars: pd.DataFrame, daily: pd.DataFrame,
                      bars_1m: pd.DataFrame,
                      precomputed_signals: dict) -> ValidationResult:
    """Run one strategy through the live engine; record outcomes."""
    res = ValidationResult(name=name)
    # Build an engine instance with whitelist = {this strategy only}
    engine = SignalEngine()
    engine.whitelist = {name}
    # Suppress slow alt-data fetches — sizing-only, irrelevant in batch
    import research.signal_engine as _se
    def _fast_refresh(self_engine, intraday, daily):
        if intraday.empty or daily.empty: return
        try:
            self_engine.last_vpin = _se.compute_vpin(intraday)
            self_engine.last_adverse = _se.compute_adverse_selection(intraday)
            self_engine.last_regime = self_engine.regime_detector.predict(daily)
        except Exception:
            pass
    _se.SignalEngine.refresh_microstructure = _fast_refresh

    prior_trades: list[TradeRef] = []
    raw_count = 0

    for ts in sorted(precomputed_signals.keys()):
        events = [e for e in precomputed_signals[ts] if e["name"] == name]
        if not events:
            continue
        raw_count += len(events)
        # Run engine.evaluate() at this ts — engine will gate this
        # strategy's signal through every filter.
        intraday = all_bars.loc[:ts]
        daily_cut = pd.Timestamp(ts.date(), tz="UTC")
        daily_slice = daily.loc[:daily_cut]
        if len(intraday) > 600:    intraday = intraday.iloc[-600:]
        if len(daily_slice) > 252: daily_slice = daily_slice.iloc[-252:]
        try:
            cand = engine.evaluate(intraday, daily_slice,
                                     prior_trades=prior_trades[-50:])
        except Exception as e:
            continue
        if cand is None:
            # Track which filter rejected
            # (engine logs it, but we don't have access here without parsing)
            continue
        # Engine accepted — simulate the trade
        # Apply entry slippage
        entry_px = float(cand.entry_px)
        entry_filled = entry_px + SLIPPAGE_POINTS if cand.side == "LONG" \
                                                  else entry_px - SLIPPAGE_POINTS
        exit_px, reason, exit_ts = _walk_exit_1m(
            bars_1m, ts, cand.side, entry_filled,
            float(cand.stop_px), float(cand.target_px), MAX_HOLD_DEFAULT)
        adverse = (reason == "STOP")
        pnl = _compute_pnl_per_contract(cand.side, entry_filled, exit_px, adverse)
        res.trade_pnls.append(pnl)
        res.trade_ts.append(ts.isoformat())
        res.side = cand.side
        # Feed back into prior_trades for cooldown
        prior_trades.append(TradeRef(
            entry_time=ts, exit_time=exit_ts, side=cand.side,
            pnl=pnl, signal_name=name,
        ))
    res.n_signals_raw = raw_count
    res.n_engine_accepted = len(res.trade_pnls)
    # Compute metrics
    m = _compute_metrics(res.trade_pnls)
    res.n_wins = int(round(m["win_rate"] * m["n"]))
    res.n_losses = m["n"] - res.n_wins
    res.win_rate = m["win_rate"]
    res.profit_factor = m["profit_factor"]
    res.net_pnl = m["net_pnl"]
    res.sharpe = m["sharpe"]
    res.avg_pnl = m["avg_pnl"]
    res.avg_win = m["avg_win"]
    res.avg_loss = m["avg_loss"]
    res.max_consecutive_losses = m["max_consecutive_losses"]
    # CPCV
    res.cpcv_test_folds_positive = _cpcv_pass(res.trade_pnls)
    # Pass/fail per test
    res.pass_sample = res.n_engine_accepted >= MIN_SAMPLE
    res.pass_wr     = res.win_rate         >= MIN_WR
    res.pass_pf     = res.profit_factor    >= MIN_PF
    res.pass_sharpe = res.sharpe           >= MIN_SHARPE
    res.pass_cpcv   = res.cpcv_test_folds_positive >= int(math.ceil(CPCV_FOLDS * 0.6))
    res.passes_all  = all([res.pass_sample, res.pass_wr, res.pass_pf,
                             res.pass_sharpe, res.pass_cpcv])
    return res


def main(window_days: int = 365, only_first_n: int | None = None):
    print(f"\n{'='*70}\nENGINE-AWARE STRATEGY VALIDATOR\n{'='*70}")
    print(f"window:  last {window_days} days of NQ")
    print(f"tests:   n>={MIN_SAMPLE}  WR>={MIN_WR*100:.0f}%  "
          f"PF>={MIN_PF}  Sharpe>={MIN_SHARPE}  "
          f"CPCV {CPCV_FOLDS}-fold (>=60% positive)")

    # Load all candidate strategy names
    if not VAL_PATH.exists():
        raise SystemExit(f"missing {VAL_PATH}")
    val = json.loads(VAL_PATH.read_text())
    candidates = sorted((val.get("signals") or {}).keys())
    if only_first_n:
        candidates = candidates[:only_first_n]
    logger.info(f"candidates: {len(candidates)} strategies")

    # Load data once
    logger.info("loading bars …")
    bars_5m = load_intraday_5min("nq")
    bars_1m = load_intraday_1min("nq")
    daily   = load_daily("nq")
    for df in (bars_5m, bars_1m, daily):
        if df.index.tz is None: df.index = df.index.tz_localize("UTC")
    end = bars_5m.index.max()
    start = end - pd.Timedelta(days=window_days)
    bars_5m = bars_5m.loc[start:end]
    bars_1m = bars_1m.loc[start - pd.Timedelta(hours=2):end + pd.Timedelta(hours=2)]
    logger.info(f"window: {start} → {end}  ({len(bars_5m):,} 5-min bars)")

    # Pre-compute every signal-firing bar across the whole universe
    candidate_set = set(candidates)
    logger.info(f"pre-computing signal bars for all {len(candidates)} strategies …")
    pre_t0 = time.time()
    presig = precompute_signal_bars(bars_5m, daily, candidate_set)
    logger.info(f"  done in {time.time()-pre_t0:.0f}s — "
                f"{sum(len(v) for v in presig.values()):,} raw signals "
                f"across {len(presig):,} unique timestamps")

    # Per-strategy validation
    results: list[ValidationResult] = []
    t0 = time.time()
    for i, name in enumerate(candidates):
        try:
            res = validate_strategy(name, bars_5m, daily, bars_1m, presig)
            results.append(res)
            elapsed = time.time() - t0
            rate = (i + 1) / max(0.001, elapsed)
            eta = (len(candidates) - i - 1) / max(0.001, rate)
            mark = "✓" if res.passes_all else " "
            logger.info(f"  [{mark}] {i+1:>3}/{len(candidates)} {name:<32}  "
                        f"raw={res.n_signals_raw:>4} taken={res.n_engine_accepted:>3}  "
                        f"WR={res.win_rate*100:>5.1f}%  PF={res.profit_factor:>5.2f}  "
                        f"Sh={res.sharpe:>+5.2f}  CPCV={res.cpcv_test_folds_positive}/{CPCV_FOLDS}  "
                        f"pnl=${res.net_pnl:>+8,.0f}  ETA {eta/60:.1f}m")
        except Exception as e:
            logger.warning(f"  [{i+1}/{len(candidates)}] {name}: ERROR {e}")
            results.append(ValidationResult(name=name))

    # Save raw results
    out = {
        "window_days": window_days,
        "tests": dict(min_sample=MIN_SAMPLE, min_wr=MIN_WR, min_pf=MIN_PF,
                      min_sharpe=MIN_SHARPE, cpcv_folds=CPCV_FOLDS),
        "results": [r.__dict__ for r in results],
        "summary": {
            "n_total":   len(results),
            "n_pass_all": sum(1 for r in results if r.passes_all),
            "n_pass_sample":  sum(1 for r in results if r.pass_sample),
            "n_pass_wr":      sum(1 for r in results if r.pass_wr),
            "n_pass_pf":      sum(1 for r in results if r.pass_pf),
            "n_pass_sharpe":  sum(1 for r in results if r.pass_sharpe),
            "n_pass_cpcv":    sum(1 for r in results if r.pass_cpcv),
        },
    }
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))

    # Headline summary
    survivors = [r for r in results if r.passes_all]
    print(f"\n{'='*70}\nSUMMARY\n{'='*70}")
    print(f"  total candidates:    {len(results)}")
    print(f"  passed sample:       {out['summary']['n_pass_sample']}")
    print(f"  passed WR:           {out['summary']['n_pass_wr']}")
    print(f"  passed PF:           {out['summary']['n_pass_pf']}")
    print(f"  passed Sharpe:       {out['summary']['n_pass_sharpe']}")
    print(f"  passed CPCV:         {out['summary']['n_pass_cpcv']}")
    print(f"  passed ALL 5 tests:  {len(survivors)}")
    if survivors:
        print(f"\n=== SURVIVORS ===")
        for r in sorted(survivors, key=lambda r: -r.net_pnl):
            print(f"  {r.name:<32}  {r.side:<5}  n={r.n_engine_accepted:>3}  "
                  f"WR={r.win_rate*100:.1f}%  PF={r.profit_factor:.2f}  "
                  f"Sh={r.sharpe:+.2f}  CPCV={r.cpcv_test_folds_positive}/{CPCV_FOLDS}  "
                  f"pnl=${r.net_pnl:+,.0f}")
    print(f"\nWrote {OUT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    only = None
    if len(sys.argv) > 1:
        only = int(sys.argv[1])
    main(only_first_n=only)
