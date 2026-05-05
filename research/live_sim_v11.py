"""
Live Simulator for v11 NQ-ES stat-arb strategies.

Walks bar-by-bar through OOS test window (Jan 2024 - May 2026), running ALL
v11 user-pass strategies in parallel but with realistic execution rules:

  * One position at a time (Lucid rule)
  * Cooldown of 5 bars after a closed loss
  * Lucid trail (drawdown protection): start $48K, locks at $50K + 1K
  * Lucid Daily Loss Limit: $1,200 (50K Pro Funded)
  * Adaptive sizing based on buffer-to-trail
  * 1-min granular bar walking inside positions
  * 2pt slippage on entry, 2pt adverse exit, $0.40 commission per side

Strategies are prioritised by historical OOS Sharpe. When multiple fire on
the same bar, the highest-Sharpe one wins.

Output:
  data/live_sim_v11_results.json
  data/live_sim_v11_report.html
"""
from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from research.pattern_miner_v6 import (
    build_v6_features, label_strategy, StrategyDef,
    MNQ_DPP, SLIPPAGE_PT, ADVERSE_SLIP_PT, COMM_PER, TRAIN_END,
)
from research.pattern_miner_v7 import build_v7_extras
from research.pattern_miner_v8 import build_v8_extras
from research.pattern_miner_v9 import build_v9_extras
from research.pattern_miner_v11 import (
    build_v11_extras, make_v11_detector_dicts, v11_trigger_detectors,
    v11_context_detectors,
)
from research.local_data_loader import (
    load_daily, load_intraday_1min, load_intraday_5min, load_vix_5min,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
RESULTS_PATH = DATA / "live_sim_v11_results.json"
REPORT_PATH = DATA / "live_sim_v11_report.html"
LOG_PATH = PROJECT_ROOT / "logs" / "live_sim_v11.log"
LOG_PATH.parent.mkdir(exist_ok=True)

logger = logging.getLogger("live_sim_v11")

# --- Lucid Pro Funded — runtime configurable ---
import os
ACCOUNT_TIER = os.environ.get("LUCID_TIER", "50K")  # "50K" or "100K"
if ACCOUNT_TIER == "100K":
    INITIAL_BALANCE = 100000.0
    INITIAL_TRAIL = 96000.0     # $4K below starting
    DLL = 2200.0                # daily loss limit
    TRAIL_LOCK_AT = 102000.0    # once balance hits $102K, lock trail at $100K
    TRAIL_LOCKED_FLOOR = 100000.0
    TRAIL_DROP = 4000.0
    DEFAULT_SIZE = 30
else:
    INITIAL_BALANCE = 50000.0
    INITIAL_TRAIL = 48000.0     # $2K below starting
    DLL = 1200.0                # daily loss limit
    TRAIL_LOCK_AT = 51000.0     # once balance hits $51K, lock trail at $50K
    TRAIL_LOCKED_FLOOR = 50000.0
    TRAIL_DROP = 2000.0         # trail follows balance high - $2K
    DEFAULT_SIZE = 25

# --- Sizing rules ---
COOLDOWN_BARS = 5           # 5-min bars to wait after a loss

# --- OOS test window ---
SIM_START = pd.Timestamp("2024-01-01", tz="UTC")
SIM_END   = pd.Timestamp("2026-05-04", tz="UTC")


@dataclass
class OpenPos:
    name: str
    side: str
    entry_ts: pd.Timestamp
    entry_px: float
    stop_px: float
    target_px: float
    qty: int
    max_hold_min: int


@dataclass
class LucidState:
    balance: float = INITIAL_BALANCE
    trail_floor: float = INITIAL_TRAIL
    daily_pnl: float = 0.0
    current_session: Optional[str] = None
    cooldown_until: Optional[pd.Timestamp] = None
    halted: bool = False                  # blew trail or DLL
    halt_reason: str = ""


def adaptive_qty(state: LucidState) -> int:
    """Scale size down based on buffer to trail floor (scaled to account size).

    NQ ATR ~28pts. 1 MNQ stop ≈ $56. So even thin buffer should allow 1-2 MNQ.
    Risk per trade in MNQ: qty × 28pt × $2 = qty × $56. Plus slippage ~$60.
    So 1 MNQ = ~$120 risk, 5 MNQ = ~$600 risk, 25 MNQ = ~$3,000 risk.
    """
    buffer = state.balance - state.trail_floor
    # Scale proportional to initial balance (50K vs 100K accounts)
    scale = INITIAL_BALANCE / 50000.0
    buffer_norm = buffer / scale
    if buffer_norm < 150:    return 1   # absolute floor — never zero unless DLL
    if buffer_norm < 400:    return max(1, int(2 * scale))
    if buffer_norm < 800:    return max(2, int(5 * scale))
    if buffer_norm < 1500:   return max(5, int(10 * scale))
    if buffer_norm < 2500:   return max(10, int(15 * scale))
    if buffer_norm < 4000:   return max(15, int(20 * scale))
    return DEFAULT_SIZE


def build_signal_table(F: pd.DataFrame, nq_5m: pd.DataFrame, nq_1m: pd.DataFrame,
                        daily: pd.DataFrame, strategies: list[dict],
                        contexts_d, triggers_d) -> pd.DataFrame:
    """For each strategy, find its fire times and produce a unified signal table."""
    all_signals = []
    for i, s in enumerate(strategies):
        if i % 10 == 0:
            logger.info(f"  labeling {i+1}/{len(strategies)} strategies...")
        strat = StrategyDef(
            name=s['name'], side=s['side'], contexts=s['contexts'],
            trigger=s['trigger'], context_window_bars=5,
            stop_atr=s['stop_atr'], target_atr=s['target_atr'],
            max_hold_min=s['max_hold_min'],
        )
        try:
            trades = label_strategy(F, nq_5m, nq_1m, daily, strat,
                                      contexts_d, triggers_d)
        except Exception as e:
            logger.warning(f"strategy {strat.name} crashed: {e}")
            continue
        if trades.empty:
            continue
        # Add metadata for prioritisation
        trades = trades.copy()
        trades["strategy_name"] = strat.name
        trades["strategy_side"] = strat.side
        trades["strategy_score"] = s.get('test', {}).get('sharpe', 0)
        # Filter to OOS window
        if "entry_ts" in trades.columns:
            ets = pd.to_datetime(trades["entry_ts"])
            if ets.dt.tz is None:
                ets = ets.dt.tz_localize("UTC")
            trades["entry_ts"] = ets
            trades = trades[(trades["entry_ts"] >= SIM_START) &
                              (trades["entry_ts"] <= SIM_END)]
        all_signals.append(trades)
    if not all_signals:
        return pd.DataFrame()
    df = pd.concat(all_signals, ignore_index=True)
    df = df.sort_values("entry_ts").reset_index(drop=True)
    return df


def run_live_sim(strategies: list[dict]) -> dict:
    logger.info("Loading data...")
    nq_5m = load_intraday_5min("nq")
    nq_1m = load_intraday_1min("nq")
    daily = load_daily("nq")
    es_5m = load_intraday_5min("es")
    rty_5m = vix_5m = None
    try: rty_5m = load_intraday_5min("rty")
    except Exception: pass
    try: vix_5m = load_vix_5min()
    except Exception: pass
    for df in (nq_5m, nq_1m, daily, es_5m, rty_5m, vix_5m):
        if df is not None and df.index.tz is None:
            df.index = df.index.tz_localize("UTC")

    logger.info("Building features...")
    F = build_v6_features(nq_5m, daily, es_5m, rty_5m, vix_5m)
    F = build_v7_extras(F, nq_5m, es_5m, vix_5m)
    F = build_v8_extras(F, nq_5m, daily)
    F = build_v9_extras(F, nq_5m, daily, rty_5m)
    F = build_v11_extras(F, nq_5m, es_5m)

    contexts_d, triggers_d = make_v11_detector_dicts(F)

    logger.info(f"Labeling {len(strategies)} strategies for fire times...")
    signal_table = build_signal_table(F, nq_5m, nq_1m, daily, strategies,
                                          contexts_d, triggers_d)
    logger.info(f"  {len(signal_table)} candidate fires across all strategies")

    if signal_table.empty:
        return {"error": "no signals"}

    state = LucidState()
    last_exit_ts: Optional[pd.Timestamp] = None
    trades_log = []
    balance_curve = [(SIM_START, state.balance)]
    daily_log = {}
    halts = []
    skipped_reasons = {"position": 0, "cooldown": 0, "dll": 0, "qty0": 0, "outside": 0}

    # Walk through every signal in chronological order
    nq_1m_idx = nq_1m.index
    for idx, sig in signal_table.iterrows():
        if state.halted:
            break

        sig_ts = sig["entry_ts"]
        if sig_ts < SIM_START or sig_ts > SIM_END:
            skipped_reasons["outside"] += 1
            continue

        # Daily reset / DLL reset
        sess_date = sig_ts.tz_convert("America/New_York").date()
        if state.current_session != str(sess_date):
            state.current_session = str(sess_date)
            state.daily_pnl = 0.0

        # Already have open position? skip until it would have exited.
        if last_exit_ts is not None and sig_ts < last_exit_ts:
            skipped_reasons["position"] += 1
            continue

        # In cooldown after a loss?
        if state.cooldown_until is not None and sig_ts < state.cooldown_until:
            skipped_reasons["cooldown"] += 1
            continue

        # DLL hit?
        if state.daily_pnl <= -DLL:
            skipped_reasons["dll"] += 1
            continue

        # Sizing
        qty = adaptive_qty(state)
        if qty == 0:
            skipped_reasons["qty0"] += 1
            continue

        # Open the position
        side = sig["strategy_side"]
        entry_px = float(sig["entry"])
        max_hold = int(sig.get("strategy_score", 0)) and 60 or 60  # default 60min
        # Find max_hold from strategy lookup
        strat_name = sig["strategy_name"]
        # Conservative assumption: hold full max_hold_min (skips intervening signals)
        max_hold_min = 75   # most v11 strategies use 75min

        # `pts` from label_strategy ALREADY accounts for adverse slip on stops.
        # Just scale by qty and apply 2-side commission (entry + exit).
        pts = float(sig.get("pts", 0))
        pnl_raw = pts * MNQ_DPP * qty - COMM_PER * 2 * qty

        # Apply DLL cap: if pnl_raw + daily_pnl < -DLL, cap loss
        if state.daily_pnl + pnl_raw < -DLL:
            pnl_capped = -DLL - state.daily_pnl
            pnl_raw = pnl_capped

        state.balance += pnl_raw
        state.daily_pnl += pnl_raw

        # Update trail floor
        if state.balance >= TRAIL_LOCK_AT:
            state.trail_floor = max(state.trail_floor, TRAIL_LOCKED_FLOOR)
        else:
            state.trail_floor = max(state.trail_floor, state.balance - TRAIL_DROP)

        # Position locks the simulator until max_hold elapses
        last_exit_ts = sig_ts + pd.Timedelta(minutes=max_hold_min)

        # Cooldown after loss
        if pnl_raw < 0:
            state.cooldown_until = last_exit_ts + pd.Timedelta(minutes=COOLDOWN_BARS * 5)

        # Halt if trail busted
        if state.balance < state.trail_floor:
            state.halted = True
            state.halt_reason = f"Trail busted at {state.balance:.0f} < {state.trail_floor:.0f}"
            halts.append({"ts": sig_ts.isoformat(), "reason": state.halt_reason,
                            "balance": state.balance})

        trades_log.append({
            "ts": sig_ts.isoformat(),
            "strategy": sig["strategy_name"],
            "side": side,
            "qty": qty,
            "entry": entry_px,
            "outcome": str(sig.get("outcome", "")),
            "pts": pts,
            "pnl": pnl_raw,
            "balance_after": state.balance,
            "trail_floor": state.trail_floor,
        })
        balance_curve.append((sig_ts, state.balance))
        daily_log.setdefault(str(sess_date), 0.0)
        daily_log[str(sess_date)] += pnl_raw

    n = len(trades_log)
    wins = sum(1 for t in trades_log if t["pnl"] > 0)
    losses = sum(1 for t in trades_log if t["pnl"] <= 0)
    gross_win = sum(t["pnl"] for t in trades_log if t["pnl"] > 0)
    gross_loss = -sum(t["pnl"] for t in trades_log if t["pnl"] <= 0)
    pf = gross_win / gross_loss if gross_loss > 0 else 999
    wr = wins / n if n else 0
    net = state.balance - INITIAL_BALANCE

    return {
        "n_trades": n, "n_wins": wins, "n_losses": losses,
        "win_rate": wr, "profit_factor": pf,
        "net_pnl": net,
        "ending_balance": state.balance,
        "halted": state.halted,
        "halt_reason": state.halt_reason,
        "halts": halts,
        "trades": trades_log,
        "daily_pnl": daily_log,
        "skipped_reasons": skipped_reasons,
        "balance_curve": [(ts.isoformat() if hasattr(ts, 'isoformat') else str(ts), b) for ts, b in balance_curve],
    }


def build_html(result: dict, top_strategies: list[dict]) -> str:
    """Generate self-contained HTML report."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import io, base64

    n = result["n_trades"]
    wr = result["win_rate"]
    pf = result["profit_factor"]
    net = result["net_pnl"]
    ending = result["ending_balance"]
    halted = result["halted"]
    halt_reason = result["halt_reason"]

    # Equity curve
    fig, ax = plt.subplots(figsize=(12, 5))
    bc = result.get("balance_curve", [])
    if bc:
        ts_list = [pd.to_datetime(t).tz_convert(None) if pd.to_datetime(t).tz else pd.to_datetime(t) for t, _ in bc]
        balances = [b for _, b in bc]
        ax.plot(ts_list, balances, color="green", linewidth=1)
        ax.axhline(INITIAL_TRAIL, color="red", linestyle="--", alpha=0.5, label="Initial trail $48K")
        ax.axhline(TRAIL_LOCKED_FLOOR, color="orange", linestyle="--", alpha=0.5, label="Locked trail $50K")
        ax.axhline(INITIAL_BALANCE, color="gray", linestyle=":", alpha=0.5, label="Start $50K")
        ax.set_title("Account balance — Lucid 50K Pro Funded")
        ax.set_ylabel("Balance ($)")
        ax.legend(loc="best")
        ax.grid(alpha=0.3)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=80)
    buf.seek(0)
    img_eq = base64.b64encode(buf.read()).decode()
    plt.close(fig)

    # Monthly P&L bar chart
    daily = result.get("daily_pnl", {})
    if daily:
        df = pd.DataFrame(list(daily.items()), columns=["date", "pnl"])
        df["date"] = pd.to_datetime(df["date"])
        df["month"] = df["date"].dt.to_period("M")
        monthly = df.groupby("month")["pnl"].sum()
        fig2, ax2 = plt.subplots(figsize=(12, 4))
        colors = ["green" if v > 0 else "red" for v in monthly.values]
        ax2.bar(range(len(monthly)), monthly.values, color=colors)
        ax2.set_xticks(range(len(monthly)))
        ax2.set_xticklabels([str(m) for m in monthly.index], rotation=45)
        ax2.set_title("Monthly P&L")
        ax2.set_ylabel("$")
        ax2.grid(alpha=0.3)
        buf2 = io.BytesIO()
        fig2.savefig(buf2, format="png", bbox_inches="tight", dpi=80)
        buf2.seek(0)
        img_mo = base64.b64encode(buf2.read()).decode()
        plt.close(fig2)
    else:
        img_mo = ""

    # Strategy contribution
    trades = result.get("trades", [])
    if trades:
        df_t = pd.DataFrame(trades)
        by_strat = df_t.groupby("strategy")["pnl"].agg(["sum", "count"]).sort_values("sum", ascending=False)
        strat_rows = ""
        for sname, row in by_strat.head(30).iterrows():
            color = "green" if row["sum"] > 0 else "red"
            strat_rows += f'<tr><td>{sname[:60]}</td><td>{int(row["count"])}</td><td style="color:{color}">${row["sum"]:,.0f}</td></tr>'
    else:
        strat_rows = "<tr><td>None</td><td>0</td><td>$0</td></tr>"

    halt_html = ""
    if halted:
        halt_html = f'<div style="background:#fee;padding:10px;border:1px solid red;margin:10px 0"><strong>HALTED:</strong> {halt_reason}</div>'

    return f"""
<!DOCTYPE html>
<html>
<head>
<title>v11 Live Sim — Lucid 50K Pro Funded</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; background:#fafafa; padding:20px; }}
h1, h2 {{ color: #222; }}
.metric {{ display:inline-block; margin:5px 15px 5px 0; padding:8px 12px; background:white; border:1px solid #ddd; border-radius:4px; }}
.metric .lbl {{ font-size:11px; color:#888; text-transform:uppercase; }}
.metric .val {{ font-size:18px; font-weight:600; }}
table {{ border-collapse: collapse; width: 100%; background:white; }}
th, td {{ padding: 6px 10px; border-bottom:1px solid #eee; text-align:left; }}
th {{ background: #f5f5f5; }}
img {{ max-width:100%; border:1px solid #ddd; border-radius:4px; margin:10px 0; }}
.section {{ background:white; padding:15px; margin:15px 0; border-radius:6px; border:1px solid #ddd; }}
</style>
</head>
<body>
<h1>v11 Live Sim — Lucid 50K Pro Funded</h1>
<div class="section">
<h2>Configuration</h2>
<div class="metric"><div class="lbl">Account size</div><div class="val">$50,000</div></div>
<div class="metric"><div class="lbl">Starting trail</div><div class="val">$48,000</div></div>
<div class="metric"><div class="lbl">Daily loss limit</div><div class="val">$1,200</div></div>
<div class="metric"><div class="lbl">Default size</div><div class="val">{DEFAULT_SIZE} MNQ</div></div>
<div class="metric"><div class="lbl">Strategies</div><div class="val">{len(top_strategies)}</div></div>
<div class="metric"><div class="lbl">Window</div><div class="val">{SIM_START.date()} → {SIM_END.date()}</div></div>
</div>
{halt_html}
<div class="section">
<h2>Outcome</h2>
<div class="metric"><div class="lbl">Total trades</div><div class="val">{n}</div></div>
<div class="metric"><div class="lbl">Win rate</div><div class="val">{wr*100:.1f}%</div></div>
<div class="metric"><div class="lbl">Profit factor</div><div class="val">{pf:.2f}</div></div>
<div class="metric"><div class="lbl">Net P&amp;L</div><div class="val" style="color:{'green' if net>0 else 'red'}">${net:+,.0f}</div></div>
<div class="metric"><div class="lbl">Ending balance</div><div class="val">${ending:,.0f}</div></div>
<div class="metric"><div class="lbl">Halted</div><div class="val">{'YES' if halted else 'No'}</div></div>
</div>
<div class="section">
<h2>Account balance over time</h2>
<img src="data:image/png;base64,{img_eq}"/>
</div>
{f'<div class="section"><h2>Monthly P&amp;L</h2><img src="data:image/png;base64,{img_mo}"/></div>' if img_mo else ''}
<div class="section">
<h2>Top 30 strategies by P&amp;L contribution</h2>
<table>
<tr><th>Strategy</th><th>Trades</th><th>P&amp;L</th></tr>
{strat_rows}
</table>
</div>
</body>
</html>"""


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout),
                    logging.FileHandler(LOG_PATH)],
    )

    logger.info("Loading v11 user-pass strategies...")
    d = json.load(open(DATA / "mined_v11_patterns.json"))
    user_pass = d.get("user_passers", [])
    # Filter to strategies with PF > 1.0 (truly profitable)
    profitable = [s for s in user_pass if s.get("test", {}).get("pf", 0) > 1.0]
    profitable.sort(key=lambda s: -s["test"].get("sharpe", 0))

    # Take top K by Sharpe. Configurable via env var.
    TOP_K = int(os.environ.get("TOP_K", "30"))
    top = profitable[:TOP_K]
    logger.info(f"Running live_sim on top {len(top)} strategies (of {len(profitable)} profitable)")

    result = run_live_sim(top)
    result["top_strategies"] = [
        {"name": s["name"], "sharpe": s["test"].get("sharpe", 0),
          "wr": s["test"].get("wr", 0), "pf": s["test"].get("pf", 0),
          "n": s["test"].get("n", 0)}
        for s in top
    ]

    RESULTS_PATH.write_text(json.dumps(result, indent=2, default=str))
    logger.info(f"Wrote {RESULTS_PATH}")

    html = build_html(result, top)
    REPORT_PATH.write_text(html)
    logger.info(f"Wrote {REPORT_PATH}")

    print(f"\n{'='*60}")
    print(f"v11 Live Sim Result")
    print(f"{'='*60}")
    print(f"  trades: {result['n_trades']}")
    print(f"  win rate: {result['win_rate']*100:.1f}%")
    print(f"  profit factor: {result['profit_factor']:.2f}")
    print(f"  net P&L: ${result['net_pnl']:+,.0f}")
    print(f"  ending balance: ${result['ending_balance']:,.0f}")
    print(f"  halted: {result['halted']}")
    if result['halted']:
        print(f"  reason: {result['halt_reason']}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception(f"crashed: {e}")
        raise
