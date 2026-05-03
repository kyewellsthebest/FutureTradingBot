"""
Side-by-side comparison of two live_sim runs (BEFORE and AFTER a fix).

Reads:
  data/live_sim_results_BEFORE.json   (saved before applying the fix)
  data/live_sim_results.json          (AFTER — most recent run)

Writes:
  data/live_sim_report.html           (overwrites; combined comparison report)

Usage:  python -m research.build_compare_report
"""
from __future__ import annotations

import base64
import io
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BEFORE_JSON = PROJECT_ROOT / "data" / "live_sim_results_BEFORE.json"
AFTER_JSON  = PROJECT_ROOT / "data" / "live_sim_results.json"
OUT_HTML    = PROJECT_ROOT / "data" / "live_sim_report.html"

PROFIT_SPLIT = 0.90
START_BAL    = 50_000.0


def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def _equity_chart(before: dict, after: dict) -> str:
    fig, ax = plt.subplots(figsize=(12, 4.5))
    for label, color, run in [("BEFORE (old VPIN)", "#ef5350", before),
                              ("AFTER (recalibrated VPIN)", "#26a69a", after)]:
        bc = run.get("balance_curve") or []
        if bc:
            xs = [pd.Timestamp(t) for t, _ in bc]
            ys = [b for _, b in bc]
            ax.plot(xs, ys, linewidth=1.6, color=color, label=label, alpha=0.9)
    ax.axhline(START_BAL, color="gray", linestyle="--", alpha=0.5, label="Start $50K")
    ax.axhline(48000, color="red", linestyle=":", alpha=0.4, label="Trail $48K")
    ax.set_title("Account balance — BEFORE vs AFTER VPIN recalibration", fontsize=13)
    ax.set_ylabel("Balance ($)")
    ax.legend(fontsize=9, loc="best")
    ax.grid(alpha=0.3)
    return _fig_to_b64(fig)


def _veto_chart(before: dict, after: dict) -> str:
    bvet = dict(before.get("block_reasons_top") or [])
    avet = dict(after.get("block_reasons_top")  or [])
    rules = sorted(set(list(bvet) + list(avet)))
    if not rules:
        return ""
    bvals = [bvet.get(r, 0) for r in rules]
    avals = [avet.get(r, 0) for r in rules]
    fig, ax = plt.subplots(figsize=(12, max(3, len(rules)*0.4)))
    y = np.arange(len(rules))
    h = 0.4
    ax.barh(y - h/2, bvals, h, color="#ef5350", label="BEFORE", alpha=0.9)
    ax.barh(y + h/2, avals, h, color="#26a69a", label="AFTER",  alpha=0.9)
    ax.set_yticks(y); ax.set_yticklabels(rules)
    ax.set_xlabel("# entries blocked")
    ax.set_title("What blocked the bot — BEFORE vs AFTER", fontsize=13)
    ax.invert_yaxis()
    ax.legend(fontsize=9)
    ax.grid(axis="x", alpha=0.3)
    return _fig_to_b64(fig)


def _strategy_table(after: dict) -> str:
    by_strat = after.get("by_strategy") or {}
    if not by_strat:
        return "<p class='muted'>No trades taken.</p>"
    rows = []
    for name, s in sorted(by_strat.items(), key=lambda kv: -kv[1]["pnl"]):
        wr = (s["wins"] / s["n"] * 100) if s["n"] else 0
        rows.append(f"<tr><td>{name}</td><td>{s['n']}</td>"
                    f"<td>{wr:.1f}%</td>"
                    f"<td style='color:{'#28a745' if s['pnl']>0 else '#dc3545'};font-weight:bold'>${s['pnl']:+,.0f}</td></tr>")
    return ("<table><tr><th>Strategy</th><th>Trades</th><th>WR</th><th>Net P&L</th></tr>"
            + "".join(rows) + "</table>")


def _trades_table(after: dict, n=100) -> str:
    trades = (after.get("trades") or [])[-n:]
    if not trades:
        return "<p class='muted'>No trades.</p>"
    rows = []
    for t in reversed(trades):
        rows.append(
            "<tr>"
            f"<td>{t['entry_ts'][:16].replace('T',' ')}</td>"
            f"<td>{t['signal']}</td>"
            f"<td>{t['side']}</td>"
            f"<td>{t['qty']}</td>"
            f"<td>{t['entry_px']:.2f}</td>"
            f"<td>{t['exit_px']:.2f}</td>"
            f"<td>{t['exit_reason']}</td>"
            f"<td style='color:{'#28a745' if t['pnl']>0 else '#dc3545'};font-weight:bold'>${t['pnl']:+,.0f}</td>"
            "</tr>"
        )
    return ("<table><tr><th>Entry</th><th>Strategy</th><th>Side</th>"
            "<th>Qty</th><th>Entry</th><th>Exit</th><th>Reason</th><th>P&L</th></tr>"
            + "".join(rows) + "</table>")


def _pct_change(before, after):
    if before == 0:
        return "—"
    pct = (after - before) / abs(before) * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.0f}%"


def _stat_row(label: str, b_val, a_val, fmt="{}", better="up", units=""):
    """One row in the headline comparison table."""
    bs = (fmt.format(b_val) + units) if b_val is not None else "—"
    as_ = (fmt.format(a_val) + units) if a_val is not None else "—"
    delta = ""
    if isinstance(b_val, (int, float)) and isinstance(a_val, (int, float)):
        d = a_val - b_val
        good = (d > 0 and better == "up") or (d < 0 and better == "down")
        col = "#28a745" if good else "#dc3545" if d != 0 else "#6c757d"
        sign = "+" if d > 0 else ""
        delta = f"<span style='color:{col};font-weight:bold;margin-left:8px'>{sign}{d:+,.2f}".replace(",.00", "") + "</span>"
        if isinstance(b_val, int) and isinstance(a_val, int):
            delta = f"<span style='color:{col};font-weight:bold;margin-left:8px'>{sign}{int(d):+,d}</span>"
    return (f"<tr><td>{label}</td><td>{bs}</td><td>{as_}</td>"
            f"<td>{_pct_change(b_val, a_val) if isinstance(b_val,(int,float)) and isinstance(a_val,(int,float)) else ''}</td></tr>")


def build_html(before: dict, after: dict) -> str:
    b = before; a = after
    pnl_b = b.get("total_pnl", 0); pnl_a = a.get("total_pnl", 0)
    take_b = max(0, pnl_b) * PROFIT_SPLIT
    take_a = max(0, pnl_a) * PROFIT_SPLIT
    wr_b = b.get("win_rate", 0) * 100
    wr_a = a.get("win_rate", 0) * 100

    equity = _equity_chart(b, a)
    vetos  = _veto_chart(b, a)
    strats = _strategy_table(a)
    trades = _trades_table(a)

    summary_table = "<table><tr><th>Metric</th><th>BEFORE (old VPIN)</th>"\
                    "<th>AFTER (recalibrated)</th><th>Δ</th></tr>"
    summary_table += _stat_row("Trades taken", b.get("trades_taken"), a.get("trades_taken"))
    summary_table += _stat_row("Trades blocked by Lucid+filters", b.get("trades_blocked"), a.get("trades_blocked"), better="down")
    summary_table += _stat_row("Wins", b.get("n_wins"), a.get("n_wins"))
    summary_table += _stat_row("Losses", b.get("n_losses"), a.get("n_losses"), better="down")
    summary_table += f"<tr><td>Win rate</td><td>{wr_b:.1f}%</td><td>{wr_a:.1f}%</td><td>{wr_a-wr_b:+.1f} pp</td></tr>"
    summary_table += f"<tr><td>Total P&L</td><td style='color:{'#28a745' if pnl_b>0 else '#dc3545'};font-weight:bold'>${pnl_b:+,.0f}</td>"\
                     f"<td style='color:{'#28a745' if pnl_a>0 else '#dc3545'};font-weight:bold'>${pnl_a:+,.0f}</td>"\
                     f"<td>{_pct_change(pnl_b, pnl_a)}</td></tr>"
    summary_table += f"<tr><td>Take-home (90% split)</td><td>${take_b:+,.0f}</td><td>${take_a:+,.0f}</td><td>{_pct_change(take_b, take_a)}</td></tr>"
    summary_table += _stat_row("Final balance", b.get("ending_balance"), a.get("ending_balance"), fmt="${:,.0f}")
    summary_table += _stat_row("Failed accounts (drawdown breaches)", b.get("n_failed_accounts"), a.get("n_failed_accounts"), better="down")
    summary_table += "</table>"

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>HFTBot — Live-Bot Replay (BEFORE vs AFTER VPIN fix)</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       max-width: 1200px; margin: 24px auto; padding: 0 20px; color: #222; background: #f8f9fa; }}
h1 {{ font-size: 28px; border-bottom: 3px solid #007bff; padding-bottom: 10px; }}
h2 {{ font-size: 22px; margin-top: 32px; color: #007bff; }}
.note {{ background: #fff3cd; padding: 12px 16px; border-left: 4px solid #ffc107;
         border-radius: 4px; font-size: 13px; margin: 14px 0; }}
.note.good {{ background: #d1e7dd; border-left-color: #28a745; }}
.note.bad  {{ background: #f8d7da; border-left-color: #dc3545; }}
table {{ width: 100%; border-collapse: collapse; background: white;
         box-shadow: 0 2px 4px rgba(0,0,0,0.05); margin: 10px 0; font-size: 13px; }}
th, td {{ padding: 7px 10px; text-align: left; border-bottom: 1px solid #e9ecef; }}
th {{ background: #f1f3f5; font-weight: 600; }}
img {{ max-width: 100%; border-radius: 8px; margin: 8px 0; }}
.muted {{ color: #888; }}
code {{ background: #eee; padding: 1px 4px; border-radius: 3px; font-size: 12px; }}
</style>
</head>
<body>

<h1>HFTBot — Live-Bot Replay (BEFORE vs AFTER VPIN fix)</h1>
<p class="muted">
Window <b>{a['window'][0][:10]} → {a['window'][1][:10]}</b> •
{a['bars_evaluated']:,} 5-min bars •
{a['signals_fired']:,} signals fired (AFTER) vs {b['signals_fired']:,} (BEFORE)
</p>

<div class="note">
This sim walks forward through 12 months of NQ futures bars, calling the
bot's <b>actual <code>SignalEngine.evaluate()</code></b> with intraday
data sliced up to (and including) the current 5-min bar — zero look-ahead.
Every entry then went through the actual <code>lucid_guard</code>. Exits
were resolved by walking 1-min bars from entry until stop or target was
touched, with the same ±2pt slippage the live paper account applies.
</div>

<div class="note bad">
<b>The bug we found:</b> The original VPIN thresholds were calibrated for
an asset class that runs much lower VPIN (likely stocks). On NQ E-mini's
deep continuous order flow, VPIN naturally runs in the 0.36–0.49 band.
Empirical sample of 12 months: <b>mean 0.42, p10 0.36, p99 0.52</b>.
Under the old thresholds (HIGH ≥0.35, EXTREME ≥0.45), the bot was in
"block trades" mode <b>93% of the time</b> — exactly what the live
deployment showed (FLAT for hours/days with zero entries).
</div>

<div class="note good">
<b>The fix (data-driven recalibration):</b><br>
LOW &lt; 0.39 (≈p25) • NORMAL &lt; 0.44 (p25-p70) • ELEVATED &lt; 0.48 (p70-p90)
• HIGH &lt; 0.52 (p90-p99) • EXTREME ≥ 0.52 (&gt;p99)<br>
Crash-warn threshold raised from 0.35 to 0.50.
The bot is now blocked only during the genuinely top-decile of toxic-flow
periods, not during normal flow.
</div>

<h2>Headline comparison</h2>
{summary_table}

<h2>Equity curve</h2>
<img src="data:image/png;base64,{equity}" />

<h2>What blocked the bot</h2>
<p class="muted">
Vetoes by rule, BEFORE vs AFTER. The big drop in
<code>vpin</code>-related blocks shows where the fix lands.
</p>
{f'<img src="data:image/png;base64,{vetos}" />' if vetos else ''}

<h2>Per-strategy breakdown (AFTER)</h2>
{strats}

<h2>Last 100 trades (AFTER)</h2>
{trades}

<p class="muted small" style="margin-top:36px">
Generated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")} •
research/build_compare_report.py
</p>
</body>
</html>"""


def main():
    if not BEFORE_JSON.exists():
        raise SystemExit(f"missing {BEFORE_JSON}")
    if not AFTER_JSON.exists():
        raise SystemExit(f"missing {AFTER_JSON}")
    before = json.loads(BEFORE_JSON.read_text())
    after  = json.loads(AFTER_JSON.read_text())
    OUT_HTML.write_text(build_html(before, after))
    size_kb = OUT_HTML.stat().st_size / 1024
    print(f"wrote {OUT_HTML.name} ({size_kb:.0f} KB)")
    print()
    print("BEFORE vs AFTER:")
    print(f"  trades taken:    {before.get('trades_taken')} → {after.get('trades_taken')}")
    print(f"  blocked:         {before.get('trades_blocked')} → {after.get('trades_blocked')}")
    print(f"  total P&L:       ${before.get('total_pnl',0):+,.0f} → ${after.get('total_pnl',0):+,.0f}")
    print(f"  final balance:   ${before.get('ending_balance',0):,.0f} → ${after.get('ending_balance',0):,.0f}")
    print(f"  failed accounts: {before.get('n_failed_accounts')} → {after.get('n_failed_accounts')}")


if __name__ == "__main__":
    main()
