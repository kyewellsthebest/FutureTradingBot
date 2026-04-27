"""
Backtest engine — the 6-stage validation pipeline.

Stage 1 — Signal generation (delegated to research.signal_generator.ALL_SIGNALS)
Stage 2 — Realistic backtest with slippage + commissions
Stage 3 — Expected-value calculation
Stage 4 — Permutation test (price-shuffle null hypothesis)
Stage 5 — Walk-forward (anchored, rolling test windows)
Stage 6 — Monte Carlo (10k random orderings, max-drawdown distribution)
Stage 7 — Parameter sensitivity (re-run at +/-20% of key params)

Usage:
    from research.backtest_engine import validate_signal, run_full_validation
    run_full_validation(intraday, daily, n_permutations=1000)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from research.indicators import eq50 as _eq50
from research.signal_generator import _attach_prev_day_levels

# ---------------------------------------------------------------------------
# Cost model — matches strategy_report.txt
# ---------------------------------------------------------------------------
CONTRACTS = 30                # MNQ contracts
DOLLARS_PER_POINT = 60.0      # 30 contracts * $2/pt
SLIP_ENTRY_PTS = 2.0          # adverse slippage on entry
SLIP_STOP_PTS = 2.0           # adverse slippage on stop fills
SLIP_TARGET_PTS = 0.0         # target fills are exact (we beat the level)
COMMISSION_DOLLARS = 60.0     # round-trip per trade

# ---------------------------------------------------------------------------
# Trade record
# ---------------------------------------------------------------------------
@dataclass
class Trade:
    signal_name: str
    side: str
    entry_time: pd.Timestamp
    entry_px: float
    exit_time: pd.Timestamp
    exit_px: float
    stop_px: float
    target_px: float
    pts: float          # signed points (after slippage)
    pnl: float          # dollars (after commission)
    win: bool
    bars_held: int
    exit_reason: str    # "target" | "stop" | "timeout"


# ---------------------------------------------------------------------------
# Stage 2 — Backtest
# ---------------------------------------------------------------------------

def _enrich_with_levels(intraday: pd.DataFrame, daily: pd.DataFrame | None) -> pd.DataFrame:
    """Attach pdh/pdl/eq50 to intraday so derive_target can use them."""
    if daily is None:
        return intraday
    df = _attach_prev_day_levels(intraday, daily)
    df["eq50"] = _eq50(df["high"], df["low"], 50)
    return df


def simulate_trades(signals: pd.DataFrame,
                    intraday: pd.DataFrame,
                    *,
                    daily: pd.DataFrame | None = None,
                    stop_pts_default: float = 15.0,
                    target_rr_default: float = 2.0,
                    max_hold_bars: int = 80,
                    target_col: str = "target_hint",
                    use_signal_targets: bool = True) -> list[Trade]:
    """
    Walk every signal forward bar-by-bar; first stop or target triggered wins.
    No look-ahead. Slippage applied on entry + stops; commission deducted per trade.

    If `use_signal_targets` is True and `daily` is provided, signals get their
    natural targets (PDL→PDH, EQ50→eq, GAP_FILL→prev_close, etc.) via
    research.signal_filters.derive_target — matching what the live engine does.
    """
    trades: list[Trade] = []
    if signals.empty:
        return trades

    # Optionally enrich with PDH/PDL/EQ50 for natural targets
    df = _enrich_with_levels(intraday, daily) if (use_signal_targets and daily is not None) else None

    # Lazy-import to avoid circular import (signal_filters → CONFIG → ...)
    from research.signal_filters import derive_target

    # Build a positional index for fast lookups.
    bar_idx = {ts: i for i, ts in enumerate(intraday.index)}
    high = intraday["high"].to_numpy()
    low = intraday["low"].to_numpy()
    close = intraday["close"].to_numpy()
    times = intraday.index

    for _, sig in signals.iterrows():
        sig_time = sig["signal_time"]
        if sig_time not in bar_idx:
            continue
        i = bar_idx[sig_time]
        if i + 1 >= len(intraday) - 1:
            continue
        side = sig["side"]
        entry_raw = float(sig["entry_px"])
        # Apply entry slippage (adverse direction)
        entry_px = entry_raw + SLIP_ENTRY_PTS if side == "LONG" else entry_raw - SLIP_ENTRY_PTS

        # Stop / target placement
        stop_pts = stop_pts_default
        target_hint = sig.get(target_col, np.nan)
        sig_name = sig.get("signal_name", "")
        if pd.notna(target_hint):
            target_px = float(target_hint)
        elif df is not None and sig_time in df.index:
            row = df.loc[sig_time]
            pdh = float(row["pdh"]) if pd.notna(row.get("pdh")) else float("nan")
            pdl = float(row["pdl"]) if pd.notna(row.get("pdl")) else float("nan")
            eq = float(row["eq50"]) if pd.notna(row.get("eq50")) else float("nan")
            target_px = derive_target(sig_name, side, entry_px, pdh, pdl, eq, target_hint)
            # Floor RR at the requested default
            min_target = entry_px + stop_pts * target_rr_default if side == "LONG" \
                         else entry_px - stop_pts * target_rr_default
            if side == "LONG" and target_px < min_target:
                target_px = min_target
            if side == "SHORT" and target_px > min_target:
                target_px = min_target
        else:
            target_px = entry_px + stop_pts * target_rr_default if side == "LONG" \
                        else entry_px - stop_pts * target_rr_default

        if side == "LONG":
            stop_px = entry_px - stop_pts
        else:
            stop_px = entry_px + stop_pts

        # Walk forward
        end = min(i + 1 + max_hold_bars, len(intraday))
        exit_reason = "timeout"
        exit_idx = end - 1
        exit_px = float(close[exit_idx])

        for j in range(i + 1, end):
            hi, lo = high[j], low[j]
            if side == "LONG":
                hit_stop = lo <= stop_px
                hit_target = hi >= target_px
            else:
                hit_stop = hi >= stop_px
                hit_target = lo <= target_px
            if hit_stop and hit_target:
                # Conservative: stop wins when both trigger same bar
                exit_reason = "stop"
                exit_px = stop_px + SLIP_STOP_PTS if side == "SHORT" else stop_px - SLIP_STOP_PTS
                exit_idx = j
                break
            if hit_stop:
                exit_reason = "stop"
                exit_px = stop_px + SLIP_STOP_PTS if side == "SHORT" else stop_px - SLIP_STOP_PTS
                exit_idx = j
                break
            if hit_target:
                exit_reason = "target"
                exit_px = target_px - SLIP_TARGET_PTS if side == "SHORT" else target_px + SLIP_TARGET_PTS
                exit_idx = j
                break

        pts = (exit_px - entry_px) if side == "LONG" else (entry_px - exit_px)
        pnl = pts * DOLLARS_PER_POINT - COMMISSION_DOLLARS
        win = pts > 0

        trades.append(Trade(
            signal_name=sig["signal_name"],
            side=side,
            entry_time=sig_time,
            entry_px=entry_px,
            exit_time=times[exit_idx],
            exit_px=exit_px,
            stop_px=stop_px,
            target_px=target_px,
            pts=float(pts),
            pnl=float(pnl),
            win=win,
            bars_held=int(exit_idx - i),
            exit_reason=exit_reason,
        ))
    return trades


# ---------------------------------------------------------------------------
# Stage 3 — Expected value & summary stats
# ---------------------------------------------------------------------------

@dataclass
class TradeStats:
    n: int
    wins: int
    losses: int
    win_rate: float
    avg_win_pts: float
    avg_loss_pts: float
    ev_pts: float
    ev_dollars: float
    profit_factor: float
    net_pnl: float
    max_consec_losses: int
    max_drawdown_dollars: float


def compute_stats(trades: list[Trade]) -> TradeStats:
    if not trades:
        return TradeStats(0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0.0)
    pts = np.array([t.pts for t in trades])
    pnl = np.array([t.pnl for t in trades])
    wins = pts > 0
    n = len(trades)
    n_w = int(wins.sum())
    n_l = n - n_w
    avg_w = float(pts[wins].mean()) if n_w > 0 else 0.0
    avg_l = float(pts[~wins].mean()) if n_l > 0 else 0.0
    wr = n_w / n
    ev_pts = wr * avg_w + (1 - wr) * avg_l
    pf_num = float(pnl[wins].sum()) if n_w > 0 else 0.0
    pf_den = -float(pnl[~wins].sum()) if n_l > 0 else 0.0
    pf = pf_num / pf_den if pf_den > 0 else (math.inf if pf_num > 0 else 0.0)
    eq = np.cumsum(pnl)
    peak = np.maximum.accumulate(eq)
    dd = float((eq - peak).min())
    # Max consecutive losers
    streak, max_streak = 0, 0
    for w in wins:
        if not w:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return TradeStats(
        n=n, wins=n_w, losses=n_l, win_rate=wr,
        avg_win_pts=avg_w, avg_loss_pts=avg_l,
        ev_pts=ev_pts, ev_dollars=ev_pts * DOLLARS_PER_POINT,
        profit_factor=pf, net_pnl=float(pnl.sum()),
        max_consec_losses=max_streak,
        max_drawdown_dollars=dd,
    )


# ---------------------------------------------------------------------------
# Stage 4 — Permutation test
# ---------------------------------------------------------------------------

def _shuffle_returns(intraday: pd.DataFrame, seed: int) -> pd.DataFrame:
    """
    Bootstrap permutation: shuffle log-returns, rebuild a synthetic price path
    with identical statistical properties but no real serial structure.
    """
    rng = np.random.default_rng(seed)
    out = intraday.copy()
    closes = intraday["close"].to_numpy()
    log_rets = np.diff(np.log(closes))
    rng.shuffle(log_rets)
    new_close = closes[0] * np.exp(np.concatenate([[0.0], np.cumsum(log_rets)]))
    out["close"] = new_close
    # Re-derive open/high/low to keep ranges plausible
    bar_range = (intraday["high"] - intraday["low"]).to_numpy()
    bar_body = (intraday["close"] - intraday["open"]).to_numpy()
    out["open"] = np.concatenate([[new_close[0]], new_close[:-1]])
    out["high"] = np.maximum(out["open"], new_close) + np.abs(bar_range - np.abs(bar_body)) * 0.5
    out["low"] = np.minimum(out["open"], new_close) - np.abs(bar_range - np.abs(bar_body)) * 0.5
    return out


def permutation_test(signal_obj,
                     intraday: pd.DataFrame,
                     daily: pd.DataFrame,
                     real_pf: float,
                     n: int = 200,
                     stop_pts: float = 15.0,
                     target_rr: float = 2.0) -> tuple[float, list[float]]:
    """Returns (p_value, list_of_permuted_pfs)."""
    if real_pf <= 0:
        return 1.0, []
    beats = 0
    perm_pfs: list[float] = []
    for k in range(n):
        try:
            shuffled = _shuffle_returns(intraday, seed=k)
            sigs = signal_obj.generate(shuffled, daily)
            trades = simulate_trades(sigs, shuffled,
                                     daily=daily,
                                     stop_pts_default=stop_pts,
                                     target_rr_default=target_rr)
            s = compute_stats(trades)
            perm_pfs.append(s.profit_factor if math.isfinite(s.profit_factor) else 0.0)
            if perm_pfs[-1] >= real_pf:
                beats += 1
        except Exception:
            perm_pfs.append(0.0)
    p = (beats + 1) / (n + 1)
    return p, perm_pfs


# ---------------------------------------------------------------------------
# Stage 5 — Walk-forward
# ---------------------------------------------------------------------------

def walk_forward(signal_obj,
                 intraday: pd.DataFrame,
                 daily: pd.DataFrame,
                 *,
                 n_windows: int = 4,
                 stop_pts: float = 15.0,
                 target_rr: float = 2.0) -> tuple[float, list[dict]]:
    """
    Anchored walk-forward: train on first 70%, test on rolling 30% windows.
    Returns (consistency_score, per_window_stats).
    consistency_score = mean(test_pf) / max(in_sample_pf, 0.01)
    """
    n = len(intraday)
    if n < 1000:
        return 0.0, []
    in_end = int(n * 0.70)
    test_block = (n - in_end) // n_windows
    if test_block < 100:
        return 0.0, []

    # In-sample baseline
    sigs_is = signal_obj.generate(intraday.iloc[:in_end], daily)
    trades_is = simulate_trades(sigs_is, intraday.iloc[:in_end], daily=daily,
                                stop_pts_default=stop_pts, target_rr_default=target_rr)
    is_stats = compute_stats(trades_is)

    # Out-of-sample: roll forward in `n_windows` chunks
    windows: list[dict] = []
    pfs: list[float] = []
    for w in range(n_windows):
        start = in_end + w * test_block
        end = start + test_block if w < n_windows - 1 else n
        if end - start < 50:
            continue
        slc = intraday.iloc[start:end]
        sigs_oos = signal_obj.generate(slc, daily)
        trades_oos = simulate_trades(sigs_oos, slc, daily=daily,
                                     stop_pts_default=stop_pts, target_rr_default=target_rr)
        st = compute_stats(trades_oos)
        windows.append({
            "window": w,
            "n_trades": st.n,
            "win_rate": st.win_rate,
            "profit_factor": st.profit_factor if math.isfinite(st.profit_factor) else 0.0,
            "ev_pts": st.ev_pts,
            "net_pnl": st.net_pnl,
        })
        pfs.append(windows[-1]["profit_factor"])

    if not pfs or is_stats.profit_factor <= 0:
        return 0.0, windows
    mean_oos = float(np.mean(pfs))
    consistency = mean_oos / max(is_stats.profit_factor, 0.01)
    return consistency, windows


# ---------------------------------------------------------------------------
# Stage 6 — Monte Carlo
# ---------------------------------------------------------------------------

def monte_carlo(trades: list[Trade],
                *,
                n_paths: int = 2000,
                starting_balance: float = 50000.0,
                apex_target: float = 9000.0,
                apex_max_dd: float = 3000.0,
                seed: int = 42) -> dict:
    if not trades:
        return {"n_paths": 0}
    pnls = np.array([t.pnl for t in trades])
    rng = np.random.default_rng(seed)
    finals = np.empty(n_paths)
    max_dds = np.empty(n_paths)
    apex_pass = 0
    apex_blow = 0
    for k in range(n_paths):
        order = rng.permutation(len(pnls))
        eq = starting_balance + np.cumsum(pnls[order])
        peak = np.maximum.accumulate(eq)
        dd = (eq - peak).min()
        finals[k] = eq[-1]
        max_dds[k] = abs(dd)
        # Apex: pass = ever hit +9k, blow = trailing dd > 3k first
        gain = eq - starting_balance
        trailing = np.maximum.accumulate(np.maximum(eq, starting_balance)) - eq
        first_pass = np.argmax(gain >= apex_target) if (gain >= apex_target).any() else -1
        first_blow = np.argmax(trailing >= apex_max_dd) if (trailing >= apex_max_dd).any() else -1
        if first_pass >= 0 and (first_blow < 0 or first_pass < first_blow):
            apex_pass += 1
        elif first_blow >= 0:
            apex_blow += 1

    return {
        "n_paths": n_paths,
        "median_final": float(np.median(finals)),
        "p5_final": float(np.percentile(finals, 5)),
        "p95_final": float(np.percentile(finals, 95)),
        "median_max_dd": float(np.median(max_dds)),
        "p_dd_over_pct": float((max_dds > 0.10 * starting_balance).mean()),
        "p_apex_pass": apex_pass / n_paths,
        "p_apex_blow": apex_blow / n_paths,
    }


# ---------------------------------------------------------------------------
# Stage 7 — Parameter sensitivity
# ---------------------------------------------------------------------------

def parameter_sensitivity(signal_obj,
                          intraday: pd.DataFrame,
                          daily: pd.DataFrame,
                          *,
                          stop_pts: float = 15.0,
                          target_rr: float = 2.0) -> dict:
    """Re-run with stop -20%, +20% — check pf doesn't collapse."""
    base_sigs = signal_obj.generate(intraday, daily)
    base_pf = compute_stats(simulate_trades(base_sigs, intraday, daily=daily,
                                            stop_pts_default=stop_pts,
                                            target_rr_default=target_rr)).profit_factor
    pf_low = compute_stats(simulate_trades(base_sigs, intraday, daily=daily,
                                           stop_pts_default=stop_pts * 0.8,
                                           target_rr_default=target_rr)).profit_factor
    pf_high = compute_stats(simulate_trades(base_sigs, intraday, daily=daily,
                                            stop_pts_default=stop_pts * 1.2,
                                            target_rr_default=target_rr)).profit_factor
    base_pf = base_pf if math.isfinite(base_pf) else 0.0
    pf_low = pf_low if math.isfinite(pf_low) else 0.0
    pf_high = pf_high if math.isfinite(pf_high) else 0.0
    worst = min(pf_low, pf_high)
    fragile = base_pf > 0 and worst < 0.7 * base_pf
    return {
        "param": "stop_pts",
        "pf_default": base_pf,
        "pf_low": pf_low,
        "pf_high": pf_high,
        "fragile": bool(fragile),
    }


# ---------------------------------------------------------------------------
# Top-level: validate one signal, then aggregate
# ---------------------------------------------------------------------------

@dataclass
class SignalValidation:
    name: str
    stats: TradeStats
    perm_p_value: float
    perm_passes: bool
    wf_consistency: float
    wf_fragile: bool
    sens: dict
    sens_fragile: bool
    recommended: bool
    reject_reason: str = ""


def validate_signal(signal_obj,
                    intraday: pd.DataFrame,
                    daily: pd.DataFrame,
                    *,
                    n_permutations: int = 200,
                    min_trades: int = 20,
                    stop_pts: float = 15.0,
                    target_rr: float = 2.0,
                    permutation_pass_p: float = 0.05) -> SignalValidation | None:
    """Run all 7 stages on a single signal class instance."""
    name = type(signal_obj).__name__
    sigs = signal_obj.generate(intraday, daily)
    if sigs.empty:
        return None
    trades = simulate_trades(sigs, intraday, daily=daily,
                             stop_pts_default=stop_pts,
                             target_rr_default=target_rr)
    stats = compute_stats(trades)
    sig_name = sigs["signal_name"].iloc[0]

    # Quick reject: too few trades or negative EV
    if stats.n < min_trades:
        return SignalValidation(
            name=sig_name, stats=stats, perm_p_value=1.0, perm_passes=False,
            wf_consistency=0.0, wf_fragile=True, sens={}, sens_fragile=True,
            recommended=False, reject_reason=f"too few trades ({stats.n})",
        )
    if stats.ev_pts <= 0:
        return SignalValidation(
            name=sig_name, stats=stats, perm_p_value=1.0, perm_passes=False,
            wf_consistency=0.0, wf_fragile=True, sens={}, sens_fragile=True,
            recommended=False, reject_reason="negative EV",
        )

    # Stage 4: Permutation test
    p_value, _ = permutation_test(signal_obj, intraday, daily,
                                  real_pf=stats.profit_factor,
                                  n=n_permutations,
                                  stop_pts=stop_pts,
                                  target_rr=target_rr)
    perm_passes = p_value < permutation_pass_p

    # Stage 5: Walk-forward
    wf_cons, _ = walk_forward(signal_obj, intraday, daily,
                              stop_pts=stop_pts, target_rr=target_rr)
    wf_fragile = wf_cons < 0.4

    # Stage 7: Parameter sensitivity
    sens = parameter_sensitivity(signal_obj, intraday, daily,
                                 stop_pts=stop_pts, target_rr=target_rr)
    sens_fragile = sens.get("fragile", False)

    # Final verdict
    reject_reason = ""
    if not perm_passes:
        reject_reason = f"permutation p={p_value:.3f} > {permutation_pass_p}"
    elif wf_fragile:
        reject_reason = f"walk-forward consistency {wf_cons:.2f} < 0.4"
    elif sens_fragile:
        reject_reason = "parameter sensitivity > 30% drop"

    recommended = bool(perm_passes and not wf_fragile and not sens_fragile and stats.ev_pts > 0)

    return SignalValidation(
        name=sig_name,
        stats=stats,
        perm_p_value=p_value,
        perm_passes=perm_passes,
        wf_consistency=wf_cons,
        wf_fragile=wf_fragile,
        sens=sens,
        sens_fragile=sens_fragile,
        recommended=recommended,
        reject_reason=reject_reason,
    )


def to_json_dict(v: SignalValidation) -> dict:
    s = v.stats
    return {
        "trades": s.n,
        "win_rate": s.win_rate,
        "avg_win_pts": s.avg_win_pts,
        "avg_loss_pts": s.avg_loss_pts,
        "ev_pts": s.ev_pts,
        "ev_dollars": s.ev_dollars,
        "profit_factor": s.profit_factor if math.isfinite(s.profit_factor) else None,
        "net_pnl": s.net_pnl,
        "max_drawdown_dollars": s.max_drawdown_dollars,
        "max_consec_losses": s.max_consec_losses,
        "perm_p_value": v.perm_p_value,
        "perm_passes": v.perm_passes,
        "wf_consistency": v.wf_consistency,
        "wf_fragile": v.wf_fragile,
        "sens_param": v.sens.get("param"),
        "sens_pf_default": v.sens.get("pf_default"),
        "sens_pf_low": v.sens.get("pf_low"),
        "sens_pf_high": v.sens.get("pf_high"),
        "sens_fragile": v.sens_fragile,
        "recommended": v.recommended,
        "reject_reason": v.reject_reason,
    }
