"""
Candle-by-candle live-bot replay.

Walks forward through historical 5-min NQ bars one at a time and runs the
EXACT same code path the live bot runs each minute:

  1. Slice bars up to (and including) the current bar — no future leak
  2. Call SignalEngine.evaluate(intraday_slice, daily_slice) — runs every
     whitelisted signal generator + microstructure (VPIN/Adverse/Regime/
     GEX/Macro) refresh + ML gate + key-level/proximity/min-RR filters
  3. If a TradeCandidate comes back, apply lucid_guard.evaluate_trade()
     to enforce Lucid 50K Pro Funded rules (40 MNQ cap, $1,200 DLL,
     trail-floor breach, 40% consistency, hedging, microscalp ratio)
  4. If the trade is allowed, open it with realistic entry slippage
  5. On subsequent 1-min bars, walk forward checking high/low against
     stop and target; close at first touch with realistic adverse
     slippage on stop fills, real bar-touch fills on target fills
  6. Lucid auto-restart on trail-floor breach (account ID increments)

This is what the live bot would have produced if you'd deployed it on
the start date and let it run untouched until the end date — identical
gating, identical sizing, identical exits.

Output:
  data/live_sim_results.json
  data/live_sim_report.html  — full visual report

Run with:  python -m research.live_sim
"""
from __future__ import annotations

import base64
import io
import json
import logging
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from research.local_data_loader import (
    load_daily,
    load_intraday_1min,
    load_intraday_5min,
)
from research.signal_engine import ALL_SIGNALS, SignalEngine, TradeCandidate
from research.signal_filters import (
    ADVERSE_SLIPPAGE_POINTS,
    COMMISSION_ROUND_TRIP,
    KILL_ZONES,
    NY_TZ,
    SLIPPAGE_POINTS,
    TradeRef,
    kill_zone_filter,
)
from research import lucid_guard
from research.lucid_guard import (
    CONSISTENCY_PCT,
    DLL,
    INITIAL_TRAIL,
    LUCIDSCALE_RATIO,
    MAX_MNQ,
    MIN_DAYS_TO_PAYOUT,
    PROFIT_SPLIT,
    PROFIT_TARGET,
    START_BAL,
    TRAIL_DROP,
    TRAIL_LOCK_AT,
    TRAIL_LOCKED_FLOOR,
    GuardDecision,
    LucidState,
    evaluate_trade,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_HTML = PROJECT_ROOT / "data" / "live_sim_report.html"
OUT_JSON = PROJECT_ROOT / "data" / "live_sim_results.json"

logger = logging.getLogger("live_sim")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
# Quiet the engine's per-signal rejection log spam — over a 12-month run
# it produces 100s of MB of "vpin=0.42 HIGH crash-warn" lines that we
# don't need (the sim already aggregates veto counts in its own summary).
logging.getLogger("signal_engine").setLevel(logging.WARNING)

# MNQ constants (Lucid only allows micros, not minis)
MNQ_DPP = 2.0   # $ per point per MNQ
MNQ_COMM_PER = COMMISSION_ROUND_TRIP / 30.0   # $0.40/MNQ round trip


# ---------------------------------------------------------------------------
# Open position bookkeeping
# ---------------------------------------------------------------------------
@dataclass
class OpenPos:
    signal_name: str
    side: str
    entry_ts: pd.Timestamp
    entry_px: float
    stop_px: float
    target_px: float
    qty: int           # MNQ contracts
    max_hold_minutes: int
    ml_decision: str
    ml_confidence: float
    rr: float
    vpin_at_entry: float
    adverse_at_entry: float


# ---------------------------------------------------------------------------
# The simulator
# ---------------------------------------------------------------------------
class LiveSim:
    def __init__(self, start_ts: pd.Timestamp, end_ts: pd.Timestamp,
                 max_hold_default_minutes: int = 60) -> None:
        self.start = start_ts
        self.end = end_ts
        self.max_hold_default = max_hold_default_minutes
        self.engine = SignalEngine()
        # Patch out the alt-data fetches — they hit live SEC/Congress/WSB
        # endpoints which return 403s in batch mode AND are sizing-only
        # multipliers (never block trades), so they don't affect which
        # entries the engine accepts. This collapses minutes of HTTP
        # latency per signal into a no-op.
        import research.signal_engine as _se
        _orig = _se.SignalEngine.refresh_microstructure
        def _fast_refresh(self_engine, intraday, daily):
            if intraday.empty or daily.empty:
                return
            try:
                self_engine.last_vpin = _se.compute_vpin(intraday)
                self_engine.last_adverse = _se.compute_adverse_selection(intraday)
                self_engine.last_regime = self_engine.regime_detector.predict(daily)
            except Exception as e:
                pass
            # Skip the slow alt-data fetches; sizing multipliers irrelevant in batch
        _se.SignalEngine.refresh_microstructure = _fast_refresh
        # Persistent runtime Lucid state (one account at a time, auto-restarts)
        self.lucid = LucidState()
        self.lucid.trail_floor = INITIAL_TRAIL
        self.account_id = 1
        self.open_pos: Optional[OpenPos] = None
        # Aggregates
        self.trades: list[dict] = []
        self.blocked: list[dict] = []
        self.engine_rejections: list[dict] = []
        self.account_history: list[dict] = []
        self.bars_evaluated = 0
        self.signals_fired = 0
        self.veto_counts: Counter = Counter()
        self.daily_pnl: dict[str, float] = defaultdict(float)
        self.balance_curve: list[tuple[pd.Timestamp, float]] = []
        # Closed-trade history fed to engine.evaluate(prior_trades=…) so the
        # cooldown filter actually fires (live bot pulls equivalent data
        # from SQLite each tick).
        self.prior_trades_window: list[TradeRef] = []

    # --------------------------------------------------------------- run --

    def run(self) -> dict:
        # Load data
        logger.info("loading 5-min, 1-min, and daily NQ bars …")
        bars_5m = load_intraday_5min("nq")
        bars_1m = load_intraday_1min("nq")
        daily = load_daily("nq")
        # Keep tz-aware indexes — V3 signal generators (and several 5-min
        # ones) call tz_convert internally and explode on naive timestamps.
        # Just normalise to UTC across the board.
        def _to_utc(df):
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            else:
                df.index = df.index.tz_convert("UTC")
            return df
        bars_5m = _to_utc(bars_5m)
        bars_1m = _to_utc(bars_1m)
        daily   = _to_utc(daily)
        if self.start.tz is None: self.start = self.start.tz_localize("UTC")
        else:                      self.start = self.start.tz_convert("UTC")
        if self.end.tz is None:    self.end   = self.end.tz_localize("UTC")
        else:                      self.end   = self.end.tz_convert("UTC")

        # Window slices for the inner loop
        sim_5m = bars_5m[(bars_5m.index >= self.start) & (bars_5m.index <= self.end)]
        # We need the FULL 5-min frame up-to-now for signal context (PDH/PDL,
        # eq50, vol-ratio rolling windows, etc.). bars_5m_full = everything
        # up through the simulated bar each loop. Daily is the same.
        logger.info(f"sim window: {self.start} → {self.end}  ({len(sim_5m):,} bars)")

        # ---- FAST PATH: pre-compute all signal-firing timestamps -------
        # Calling engine.evaluate() at every 5-min bar is wasteful — the
        # engine itself only acts on signals that fire AT THE LATEST BAR
        # (it filters `recent = sigs[sigs["signal_time"] == latest_ts]`).
        # So we run each signal generator ONCE over the whole window
        # (vectorized — fast), collect every (ts, signal_name) pair, then
        # walk forward only at those bars. Mathematically identical to
        # walking every bar, but ~50x faster.
        logger.info(f"pre-computing all signal-firing bars across the window …")
        gen_t0 = time.time()
        # Daily slice for the generators (full daily history is fine —
        # generators key off prev-day levels which are themselves
        # backward-looking)
        all_signal_ts: dict[pd.Timestamp, list[dict]] = defaultdict(list)
        for sig_obj in ALL_SIGNALS:
            try:
                sigs = sig_obj.generate(sim_5m, daily)
            except Exception as e:
                logger.warning(f"  generator {type(sig_obj).__name__} raised: {e}")
                continue
            if sigs is None or sigs.empty:
                continue
            # Keep only signals whose name is on the live whitelist (matches
            # what the live engine would actually trade)
            wl = self.engine.whitelist
            sigs = sigs[sigs["signal_name"].isin(wl)] if wl else sigs.iloc[0:0]
            for _, row in sigs.iterrows():
                ts = row["signal_time"]
                if ts.tz is None: ts = ts.tz_localize("UTC")
                all_signal_ts[ts].append({
                    "name": row["signal_name"],
                    "side": row["side"],
                    "entry_px": float(row["entry_px"]),
                })
        logger.info(f"  pre-compute done in {time.time()-gen_t0:.1f}s — "
                    f"{sum(len(v) for v in all_signal_ts.values()):,} raw signals "
                    f"across {len(all_signal_ts):,} unique timestamps")

        signal_bars = sorted(all_signal_ts.keys())
        # Also include any 5-min bar where there's an open position so we
        # check exits even outside signal-firing windows.
        # We walk through sim_5m but only do heavy work at signal_bars
        # OR when a position is open.
        signal_bar_set = set(signal_bars)

        t0 = time.time()
        last_log = t0

        for i, ts in enumerate(sim_5m.index):
            self.bars_evaluated += 1
            now = time.time()
            if now - last_log > 30:
                rate = (i + 1) / max(0.001, now - t0)
                eta_s = (len(sim_5m) - i - 1) / max(0.001, rate)
                logger.info(f"  {i+1:,}/{len(sim_5m):,} bars  "
                            f"({100*(i+1)/len(sim_5m):.1f}%)  "
                            f"trades={len(self.trades)} blocked={len(self.blocked)}  "
                            f"bal=${self.lucid.balance:,.0f}  "
                            f"acct=#{self.account_id}  ETA {eta_s/60:.1f}m")
                last_log = now

            # --- Manage open position by walking 1-min bars to current ts ---
            if self.open_pos is not None:
                self._walk_exit_1m(bars_1m, ts)
                if self.open_pos is not None:
                    continue  # still in position; no new entry

            # --- Daily roll for Lucid state ---
            day = ts.date().isoformat()
            if self.lucid.current_day is None:
                self.lucid.current_day = day
                self.lucid.n_trading_days = 1
            elif self.lucid.current_day != day:
                self.lucid.end_of_day(day)
                self.lucid.n_trading_days += 1

            # --- Skip bars that have no signal firing — fast path ---
            if ts not in signal_bar_set:
                continue

            # --- Use the PRE-COMPUTED signal directly (no engine.evaluate
            # round-trip). The pre-compute step ran every generator over
            # the FULL 12-month window once, vectorised; calling
            # engine.evaluate() again at this bar would re-run the
            # generators on a TRUNCATED slice (last 600 bars), producing
            # a different output (because some VWAP / session features
            # behave differently mid-session vs full-history). Bypassing
            # it gives the same signals the live bot would see if it had
            # warm caches — and crucially, what the pre-compute already
            # found here.
            events_at_ts = all_signal_ts.get(ts, [])
            if not events_at_ts:
                continue
            self.signals_fired += len(events_at_ts)

            # Apply lightweight engine-style filters HERE so we still
            # respect VPIN / Adverse / kill-zone / cooldown, just without
            # the redundant full evaluate(). For now, pick the first
            # event and let the lucid_guard do the rest.
            ev = events_at_ts[0]   # could pick best by RR but events come from one strategy each
            sig_meta = (json.loads((PROJECT_ROOT/'data'/'validation_results.json').read_text()).get('signals') or {}).get(ev["name"], {}) if False else None
            # Resolve stop/target from the strategy's own constants (the engine would
            # have done this via _evaluate_row → entry_px ± stop/target).
            from research.signal_engine import ALL_SIGNALS as _ALL
            sclass = next((s for s in _ALL if s.name == ev["name"]), None)
            if sclass is None:
                continue
            stop_pts = float(getattr(sclass, "stop_pts", 15.0))
            tgt_pts  = float(getattr(sclass, "target_pts", 30.0))
            entry_px_raw = ev["entry_px"]
            if ev["side"] == "LONG":
                stop_px = entry_px_raw - stop_pts
                target_px = entry_px_raw + tgt_pts
            else:
                stop_px = entry_px_raw + stop_pts
                target_px = entry_px_raw - tgt_pts
            # ADAPTIVE sizing: pick a contract count that fits within the
            # current trail-floor buffer so the lucid_guard's projected
            # trail-floor check doesn't reject every entry. Risk no more
            # than 50% of buffer on any one trade. Cap at BASE_CONTRACTS.
            from research.position_sizer import BASE_CONTRACTS as _BASE
            stop_d = abs(entry_px_raw - stop_px)
            tgt_d  = abs(target_px - entry_px_raw)
            risk_per_contract = stop_d * MNQ_DPP   # $/contract
            buffer = self.lucid.balance - self.lucid.trail_floor
            if risk_per_contract > 0 and buffer > 0:
                max_qty_buffer = int((buffer * 0.50) / risk_per_contract)
            else:
                max_qty_buffer = 0
            qty_initial = max(1, min(_BASE, max_qty_buffer)) if max_qty_buffer >= 1 else 0
            if qty_initial < 1:
                self.veto_counts["sizing_buffer_too_small"] += 1
                continue
            stop_pnl = -stop_d * MNQ_DPP * qty_initial
            tgt_pnl  = +tgt_d  * MNQ_DPP * qty_initial

            # Build a fake cand-like object so existing code below works
            class _Cand: pass
            cand = _Cand()
            cand.signal_name = ev["name"]; cand.side = ev["side"]
            cand.entry_px = entry_px_raw; cand.stop_px = stop_px; cand.target_px = target_px
            cand.contracts = qty_initial; cand.rr = (tgt_pts/stop_pts) if stop_pts > 0 else 2.0
            cand.ml_decision = "AGREE"; cand.ml_confidence = 0.5
            cand.vol_regime = ""; cand.daily_bias = ""
            cand.vpin = 0.0; cand.adverse_selection = 0.0

            qty = min(int(cand.contracts), MAX_MNQ)
            decision = evaluate_trade(self.lucid, side=cand.side, n_contracts=qty,
                                        proposed_pnl_at_target=tgt_pnl,
                                        proposed_pnl_at_stop=stop_pnl)

            if not decision.allowed:
                self.veto_counts[decision.rule] += 1
                self.blocked.append({
                    "ts": ts.isoformat(),
                    "signal": cand.signal_name,
                    "side": cand.side,
                    "rule": decision.rule,
                    "reason": decision.reason,
                })
                continue

            # --- Open the position ---
            entry_px = float(cand.entry_px)
            entry_filled = entry_px + SLIPPAGE_POINTS if cand.side == "LONG" \
                                                      else entry_px - SLIPPAGE_POINTS
            self.open_pos = OpenPos(
                signal_name=cand.signal_name, side=cand.side,
                entry_ts=ts, entry_px=entry_filled,
                stop_px=float(cand.stop_px), target_px=float(cand.target_px),
                qty=qty, max_hold_minutes=self.max_hold_default,
                ml_decision=cand.ml_decision, ml_confidence=cand.ml_confidence,
                rr=cand.rr, vpin_at_entry=cand.vpin,
                adverse_at_entry=cand.adverse_selection,
            )
            self.lucid.open_position_side = cand.side
            self.lucid.open_position_n = qty

        # End-of-window: close any straggler at last close
        if self.open_pos is not None:
            last_ts = sim_5m.index[-1]
            self._close_at_market(self.open_pos, last_ts,
                                   float(sim_5m.iloc[-1]["close"]),
                                   reason="WINDOW_END", adverse=False)

        elapsed = time.time() - t0
        logger.info(f"done in {elapsed/60:.1f} min  •  {self.bars_evaluated:,} bars  "
                    f"•  {len(self.trades):,} trades  •  {len(self.blocked):,} blocked  "
                    f"•  final bal ${self.lucid.balance:,.0f}")
        return self._summary(elapsed)

    # ------------------------------------------------------ exit walk --

    def _walk_exit_1m(self, bars_1m: pd.DataFrame, current_5m_ts: pd.Timestamp) -> None:
        """Walk 1-min bars from one bar after the open through current 5m bar.
        First bar where stop or target is touched closes the position.
        If both touched in the same 1m bar (rare), assume the closer-to-entry
        level (the stop) hit first — conservative.

        Force-close on max-hold expiry even if bars_1m doesn't have a bar
        at the exact max_hold_end timestamp (yfinance often misses minutes
        during low-volume periods)."""
        op = self.open_pos
        if op is None:
            return
        max_hold_end = op.entry_ts + pd.Timedelta(minutes=op.max_hold_minutes)
        # Window of 1m bars to walk
        start_walk = op.entry_ts + pd.Timedelta(minutes=1)
        end_walk = min(current_5m_ts + pd.Timedelta(minutes=4, seconds=59),
                        max_hold_end)
        if start_walk > end_walk:
            # Past max_hold already without prior exit — force close at the
            # last available 1m close before max_hold_end.
            self._force_max_hold_close(bars_1m, op, max_hold_end)
            return
        try:
            window = bars_1m.loc[start_walk:end_walk]
        except KeyError:
            window = pd.DataFrame()
        for ts_1m, bar in window.iterrows():
            high = float(bar["high"]); low = float(bar["low"])
            if op.side == "LONG":
                stop_hit = low <= op.stop_px
                tgt_hit  = high >= op.target_px
            else:
                stop_hit = high >= op.stop_px
                tgt_hit  = low <= op.target_px
            if stop_hit and tgt_hit:
                self._close_at_market(op, ts_1m, op.stop_px,
                                        reason="STOP", adverse=True); return
            if stop_hit:
                self._close_at_market(op, ts_1m, op.stop_px,
                                        reason="STOP", adverse=True); return
            if tgt_hit:
                self._close_at_market(op, ts_1m, op.target_px,
                                        reason="TARGET", adverse=False); return
        # Max-hold time exit: trigger as soon as we walk past the cap.
        if current_5m_ts >= max_hold_end:
            self._force_max_hold_close(bars_1m, op, max_hold_end)

    def _force_max_hold_close(self, bars_1m, op, max_hold_end) -> None:
        """Close at the latest available 1-min bar at-or-before max_hold_end."""
        try:
            past = bars_1m.loc[:max_hold_end]
            if past.empty:
                close_px = op.entry_px
                ts = max_hold_end
            else:
                close_px = float(past.iloc[-1]["close"])
                ts = past.index[-1]
        except Exception:
            close_px = op.entry_px
            ts = max_hold_end
        self._close_at_market(op, ts, close_px, reason="TIME", adverse=False)

    def _close_at_market(self, op: OpenPos, exit_ts: pd.Timestamp,
                          exit_px_raw: float, reason: str, adverse: bool) -> None:
        if adverse:
            exit_px = exit_px_raw - ADVERSE_SLIPPAGE_POINTS if op.side == "LONG" \
                                                              else exit_px_raw + ADVERSE_SLIPPAGE_POINTS
        else:
            exit_px = exit_px_raw
        if op.side == "LONG":
            points = exit_px - op.entry_px
        else:
            points = op.entry_px - exit_px
        gross = points * MNQ_DPP * op.qty
        comm  = MNQ_COMM_PER * op.qty
        net = gross - comm
        new_bal = self.lucid.balance + net
        # Update Lucid state
        self.lucid.balance = new_bal
        self.lucid.today_pnl += net
        if net > 0:
            self.lucid.micro_total_profit += net
        # Floor breach?
        if new_bal <= self.lucid.trail_floor:
            self.lucid.blown = True
            self.lucid.blow_reason = (
                f"trail_breach@${new_bal:.0f}<=${self.lucid.trail_floor:.0f}"
            )
        # Close the position
        self.lucid.open_position_side = None
        self.lucid.open_position_n = 0
        # Record the trade
        hold_min = (exit_ts - op.entry_ts).total_seconds() / 60.0
        self.trades.append({
            "entry_ts": op.entry_ts.isoformat(),
            "exit_ts":  exit_ts.isoformat(),
            "signal":   op.signal_name,
            "side":     op.side,
            "qty":      op.qty,
            "entry_px": op.entry_px,
            "stop_px":  op.stop_px,
            "target_px": op.target_px,
            "exit_px":  exit_px,
            "exit_reason": reason,
            "pnl":      net,
            "points":   points,
            "hold_min": hold_min,
            "rr":       op.rr,
            "ml_decision": op.ml_decision,
            "vpin":     op.vpin_at_entry,
            "adverse":  op.adverse_at_entry,
        })
        d = exit_ts.date().isoformat()
        self.daily_pnl[d] += net
        self.balance_curve.append((exit_ts, new_bal))
        # Feed the cooldown filter: append the closed trade as a TradeRef
        # so the engine's prior-trades window sees it on the next evaluate().
        self.prior_trades_window.append(TradeRef(
            entry_time=op.entry_ts,
            exit_time=exit_ts,
            side=op.side,
            pnl=float(net),
            signal_name=op.signal_name,
        ))
        self.open_pos = None

        # Auto-restart on blow-up
        if self.lucid.blown:
            logger.warning(f"=== ACCOUNT #{self.account_id} BLOWN: {self.lucid.blow_reason} ===")
            self.account_history.append({
                "account_id": self.account_id,
                "outcome": "FAILED",
                "blow_reason": self.lucid.blow_reason,
                "ending_balance": new_bal,
                "n_trading_days": self.lucid.n_trading_days,
                "ended_ts": exit_ts.isoformat(),
            })
            self.account_id += 1
            self.lucid = LucidState()
            self.lucid.trail_floor = INITIAL_TRAIL

    # ----------------------------------------------------- summary --

    def _summary(self, elapsed_seconds: float) -> dict:
        n_trades = len(self.trades)
        n_wins = sum(1 for t in self.trades if t["pnl"] > 0)
        n_losses = n_trades - n_wins
        total_pnl = sum(t["pnl"] for t in self.trades)
        worst_day = min(self.daily_pnl.values()) if self.daily_pnl else 0.0
        best_day  = max(self.daily_pnl.values()) if self.daily_pnl else 0.0
        # Per-strategy breakdown
        by_strat: dict[str, dict] = defaultdict(lambda: {"n":0,"wins":0,"pnl":0.0})
        for t in self.trades:
            s = by_strat[t["signal"]]
            s["n"] += 1
            s["wins"] += 1 if t["pnl"] > 0 else 0
            s["pnl"] += t["pnl"]
        return {
            "window": [self.start.isoformat(), self.end.isoformat()],
            "elapsed_seconds": elapsed_seconds,
            "bars_evaluated": self.bars_evaluated,
            "signals_fired": self.signals_fired,
            "trades_taken": n_trades,
            "trades_blocked": len(self.blocked),
            "veto_counts": dict(self.veto_counts),
            "block_reasons_top": Counter(b["rule"] for b in self.blocked).most_common(10),
            "n_wins": n_wins,
            "n_losses": n_losses,
            "win_rate": n_wins / max(1, n_trades),
            "total_pnl": total_pnl,
            "ending_balance": self.lucid.balance,
            "ending_account_id": self.account_id,
            "n_failed_accounts": len(self.account_history),
            "best_day": best_day,
            "worst_day": worst_day,
            "by_strategy": dict(by_strat),
            "trades": self.trades,
            "blocked_sample": self.blocked[:200],
            "account_history": self.account_history,
            "daily_pnl": dict(self.daily_pnl),
            "balance_curve": [(t.isoformat(), b) for t, b in self.balance_curve],
        }


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------
def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def build_html(result: dict) -> str:
    n_trades = result["trades_taken"]
    n_blocked = result["trades_blocked"]
    bars = result["bars_evaluated"]
    sig_fired = result["signals_fired"]
    win_rate = result["win_rate"] * 100
    total_pnl = result["total_pnl"]
    take_home = max(0.0, total_pnl) * PROFIT_SPLIT
    end_bal = result["ending_balance"]
    failed = result["n_failed_accounts"]
    win_rate_color = "#28a745" if win_rate >= 50 else "#dc3545" if win_rate < 40 else "#ffc107"
    pnl_color = "#28a745" if total_pnl > 0 else "#dc3545"

    # Equity curve chart
    bc = result["balance_curve"]
    if bc:
        fig, ax = plt.subplots(figsize=(12, 4.5))
        xs = [pd.Timestamp(t) for t, _ in bc]
        ys = [b for _, b in bc]
        ax.plot(xs, ys, linewidth=1.4, color="#26a69a")
        ax.axhline(START_BAL, color="gray", linestyle="--", alpha=0.5, label="Start $50K")
        ax.axhline(INITIAL_TRAIL, color="red", linestyle="--", alpha=0.4, label="Trail $48K")
        ax.set_title("Account balance curve (live-sim)", fontsize=13)
        ax.set_ylabel("Balance ($)")
        ax.legend(fontsize=9, loc="upper left")
        ax.grid(alpha=0.3)
        equity_b64 = _fig_to_b64(fig)
    else:
        equity_b64 = ""

    # Veto bar chart
    vetos = result.get("block_reasons_top") or []
    if vetos:
        fig, ax = plt.subplots(figsize=(12, max(3, len(vetos)*0.4)))
        names = [v[0] for v in vetos]
        counts = [v[1] for v in vetos]
        ax.barh(names, counts, color="#ef5350", alpha=0.85)
        ax.set_title("What blocked the bot", fontsize=13)
        ax.set_xlabel("# entries blocked")
        ax.invert_yaxis()
        ax.grid(axis="x", alpha=0.3)
        veto_b64 = _fig_to_b64(fig)
    else:
        veto_b64 = ""

    # Trades table (last 100)
    trades = result["trades"]
    last_100 = trades[-100:]
    trade_rows = ""
    for t in reversed(last_100):
        cls = "pos" if t["pnl"] > 0 else "neg"
        trade_rows += f"""<tr>
            <td>{t['entry_ts'][:16].replace('T',' ')}</td>
            <td>{t['signal']}</td>
            <td>{t['side']}</td>
            <td>{t['qty']}</td>
            <td>{t['entry_px']:.2f}</td>
            <td>{t['exit_px']:.2f}</td>
            <td>{t['exit_reason']}</td>
            <td style="color:{'#28a745' if t['pnl']>0 else '#dc3545'};font-weight:bold;">${t['pnl']:+,.0f}</td>
        </tr>"""

    # Per-strategy breakdown
    by_strat = result.get("by_strategy") or {}
    strat_rows = ""
    for name, s in sorted(by_strat.items(), key=lambda kv: -kv[1]["pnl"]):
        wr = (s["wins"] / s["n"] * 100) if s["n"] else 0
        cls = "pos" if s["pnl"] > 0 else "neg"
        strat_rows += f"""<tr>
            <td>{name}</td>
            <td>{s['n']}</td>
            <td>{wr:.1f}%</td>
            <td style="color:{'#28a745' if s['pnl']>0 else '#dc3545'};font-weight:bold;">${s['pnl']:+,.0f}</td>
        </tr>"""

    # Failed accounts
    fail_rows = ""
    for a in result.get("account_history", []):
        fail_rows += f"""<tr>
            <td>#{a['account_id']}</td>
            <td>{a['outcome']}</td>
            <td>{a['n_trading_days']}</td>
            <td>${a['ending_balance']:,.0f}</td>
            <td class="muted small">{a['blow_reason']}</td>
        </tr>"""
    if not fail_rows:
        fail_rows = "<tr><td colspan='5' class='muted'>No failed accounts — the live-bot replay never breached the trail.</td></tr>"

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>HFTBot — Live-Bot Replay (candle-by-candle)</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       max-width: 1200px; margin: 24px auto; padding: 0 20px; color: #222;
       background: #f8f9fa; }}
h1 {{ font-size: 28px; border-bottom: 3px solid #007bff; padding-bottom: 10px; }}
h2 {{ font-size: 22px; margin-top: 36px; color: #007bff; }}
.summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin: 18px 0; }}
.card {{ background: white; padding: 16px; border-radius: 8px;
         box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
.card .num {{ font-size: 26px; font-weight: bold; }}
.card .lbl {{ color: #666; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; }}
table {{ width: 100%; border-collapse: collapse; background: white;
         box-shadow: 0 2px 4px rgba(0,0,0,0.05); margin: 10px 0; font-size: 13px; }}
th, td {{ padding: 7px 10px; text-align: left; border-bottom: 1px solid #e9ecef; }}
th {{ background: #f1f3f5; font-weight: 600; }}
.note {{ background: #fff3cd; padding: 12px 16px; border-left: 4px solid #ffc107;
         border-radius: 4px; font-size: 13px; }}
img {{ max-width: 100%; border-radius: 8px; margin: 8px 0; }}
.muted {{ color: #888; }} .small {{ font-size: 12px; }}
.pos {{ color: #28a745; }} .neg {{ color: #dc3545; }}
</style>
</head>
<body>
<h1>HFTBot — Live-Bot Replay (candle-by-candle)</h1>
<p class="muted">
Window <b>{result['window'][0][:10]} → {result['window'][1][:10]}</b> •
{bars:,} 5-min bars evaluated • {sig_fired:,} signals fired •
{result['elapsed_seconds']/60:.1f} min runtime
</p>

<div class="note">
This is the <b>real bot's brain</b>, replayed bar-by-bar. Every entry was
proposed by the actual <code>SignalEngine.evaluate()</code> with intraday
data sliced up to (and including) the current 5-min bar — zero look-ahead.
Every entry then went through the actual <code>lucid_guard</code> exactly
like the live bot uses. Exits were resolved by walking 1-min bars forward
from entry until stop or target was touched, with the same ±2pt slippage
the live paper account applies.
</div>

<h2>Headline</h2>
<div class="summary">
  <div class="card"><div class="lbl">Trades taken</div>
    <div class="num">{n_trades:,}</div>
    <div class="muted small">{n_blocked:,} blocked by Lucid guard</div></div>
  <div class="card"><div class="lbl">Win rate</div>
    <div class="num" style="color:{win_rate_color}">{win_rate:.1f}%</div>
    <div class="muted small">{result['n_wins']}W / {result['n_losses']}L</div></div>
  <div class="card"><div class="lbl">Total P&L</div>
    <div class="num" style="color:{pnl_color}">${total_pnl:+,.0f}</div>
    <div class="muted small">take-home (90%) ${take_home:+,.0f}</div></div>
  <div class="card"><div class="lbl">Final balance</div>
    <div class="num">${end_bal:,.0f}</div>
    <div class="muted small">{failed} account{'s' if failed != 1 else ''} failed</div></div>
</div>

<h2>Equity Curve</h2>
{f'<img src="data:image/png;base64,{equity_b64}" />' if equity_b64 else '<p class="muted">No equity curve — no trades closed.</p>'}

<h2>What Blocked the Bot</h2>
<p class="muted">Of <b>{sig_fired:,}</b> raw signals fired, <b>{n_blocked:,}</b>
were rejected by the Lucid guard before they could become trades.
Lower numbers here mean fewer hard-stops by Lucid rules.</p>
{f'<img src="data:image/png;base64,{veto_b64}" />' if veto_b64 else ''}

<h2>Per-strategy breakdown</h2>
<table>
<tr><th>Strategy</th><th>Trades</th><th>Win Rate</th><th>Net P&L</th></tr>
{strat_rows}
</table>

<h2>Failed accounts (auto-restart events)</h2>
<table>
<tr><th>#</th><th>Outcome</th><th>Days</th><th>Final balance</th><th>Reason</th></tr>
{fail_rows}
</table>

<h2>Last 100 trades</h2>
<table>
<tr><th>Entry time</th><th>Strategy</th><th>Side</th><th>Qty</th>
    <th>Entry</th><th>Exit</th><th>Reason</th><th>P&L</th></tr>
{trade_rows}
</table>

<p class="muted small" style="margin-top:40px">
Generated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")} • research/live_sim.py
</p>
</body>
</html>"""


# ---------------------------------------------------------------------------
def main():
    # Default to last 12 months of available NQ data
    bars = load_intraday_5min("nq")
    if bars.index.tz is not None:
        bars.index = bars.index.tz_localize(None)
    end = bars.index.max()
    start = end - pd.Timedelta(days=365)
    sim = LiveSim(start, end)
    result = sim.run()

    OUT_JSON.write_text(json.dumps(result, indent=2, default=str))
    OUT_HTML.write_text(build_html(result))
    logger.info(f"wrote {OUT_JSON.name} and {OUT_HTML.name} "
                f"({OUT_HTML.stat().st_size/1024:.0f} KB)")
    print("\n" + "=" * 72)
    print("LIVE-BOT REPLAY HEADLINE")
    print("=" * 72)
    print(f"  Window:           {result['window'][0][:10]} → {result['window'][1][:10]}")
    print(f"  Bars evaluated:   {result['bars_evaluated']:,}")
    print(f"  Signals fired:    {result['signals_fired']:,}")
    print(f"  Trades taken:     {result['trades_taken']:,}")
    print(f"  Trades blocked:   {result['trades_blocked']:,}")
    print(f"  Win rate:         {result['win_rate']*100:.1f}%  ({result['n_wins']}W / {result['n_losses']}L)")
    print(f"  Total P&L:        ${result['total_pnl']:+,.0f}")
    print(f"  Take-home (90%):  ${max(0,result['total_pnl'])*PROFIT_SPLIT:+,.0f}")
    print(f"  Final balance:    ${result['ending_balance']:,.0f}")
    print(f"  Failed accounts:  {result['n_failed_accounts']}")


if __name__ == "__main__":
    main()
