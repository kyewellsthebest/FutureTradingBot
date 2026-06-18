"""TODAY's NQ tick test -- runs the bot's actual strategy code on
today's real Polygon NQ 1-min bars and shows what the bot SHOULD
have done vs what it actually did.

Validates whether the production divergence we saw in bundles
(WR 32% live vs 54% backtest) was the stale-bar-cache bug. With
fresh bars per minute, the strategy should perform like the
backtest does -- IF the data and code agree.

Run from any environment with Python 3.8+ and the bot repo cloned:
  - In your Codespace (has bot.pullback_strategy)
  - Locally with `pip install pandas requests`

Set your Polygon key first:
  export POLYGON_API=ABCDEF1234567890

Then run:
  python3 research/today_replay.py
"""
from __future__ import annotations

import os
import sys
import urllib.request
import urllib.parse
import json
import math
from datetime import datetime, timezone, timedelta
from collections import deque

# Strategy env -- same as Railway
os.environ.setdefault("STRAT_INVERT", "1")
os.environ.setdefault("STRAT_PULL_PCT", "0.236")
os.environ.setdefault("STRAT_STOP_PTS", "10.0")
os.environ.setdefault("STRAT_TARGET_PTS", "20.0")
os.environ.setdefault("STRAT_IMPULSE_PTS", "5.0")
os.environ.setdefault("STRAT_IMPULSE_BARS", "4")
os.environ.setdefault("STRAT_COOLDOWN_SECS", "10")
os.environ.setdefault("BOT_HTF_TREND_FILTER", "0")

# Add bot repo to path so we import the production strategy
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import bot.pullback_strategy as ps


POLY_KEY = os.environ.get("POLYGON_API")
if not POLY_KEY:
    print("Set POLYGON_API env var first (your Polygon API key)", file=sys.stderr)
    sys.exit(1)


def fetch_polygon_bars(ticker: str, start_iso: str, end_iso: str,
                        multiplier: int = 1, timespan: str = "minute") -> pd.DataFrame:
    """Pull aggs bars from Polygon for the requested window."""
    # NQ continuous front-month on Polygon is usually I:NDX or specific
    # MNQ contract. We use the front-month MNQ contract -- e.g.
    # MNQU25 -- but for backtest purposes ANY of the major NQ
    # contracts is fine. Default front-month: MNQ.
    url = (f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/"
           f"{multiplier}/{timespan}/{start_iso}/{end_iso}"
           f"?adjusted=true&sort=asc&limit=50000&apiKey={POLY_KEY}")
    req = urllib.request.Request(url, headers={"User-Agent": "today-replay/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    results = data.get("results") or []
    rows = []
    for r in results:
        ts = datetime.fromtimestamp(r["t"] / 1000, tz=timezone.utc)
        rows.append({
            "ts": ts, "open": r["o"], "high": r["h"], "low": r["l"],
            "close": r["c"], "volume": r.get("v", 0),
        })
    df = pd.DataFrame(rows).set_index("ts") if rows else pd.DataFrame()
    return df


def find_active_mnq_contract() -> str:
    """Pick the active front-month MNQ futures contract.

    MNQ rolls quarterly: H (Mar), M (Jun), U (Sep), Z (Dec).
    The actively traded contract is usually the nearest one until
    ~5 days before expiration (third Friday of the month), at which
    point traders roll to the next. We pick based on today's date.
    """
    today = datetime.now(timezone.utc)
    year = today.year
    month = today.month
    quarters = [(3, "H"), (6, "M"), (9, "U"), (12, "Z")]
    yy = str(year)[-2:]
    for qmonth, qcode in quarters:
        if month < qmonth:
            return f"MNQ{qcode}{yy}"
        if month == qmonth and today.day < 15:
            return f"MNQ{qcode}{yy}"
    # Past December of this year -> next year's March
    return f"MNQH{int(yy)+1:02d}"


def main():
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    # Pull a 36-hour window so we have enough warmup bars for the
    # 4-bar impulse window and the HTF trend (which is off here anyway)
    start = (datetime.combine(yesterday, datetime.min.time())
             .replace(tzinfo=timezone.utc))
    end = datetime.now(timezone.utc)

    # Try the active MNQ contract first, fall back to NQ if needed
    ticker = find_active_mnq_contract()
    print(f"Pulling {ticker} 1-min bars from "
          f"{start.isoformat()} to {end.isoformat()}", file=sys.stderr)
    df = fetch_polygon_bars(ticker,
                              start.strftime("%Y-%m-%d"),
                              end.strftime("%Y-%m-%d"))
    if df.empty:
        # Fallback to NQ continuous
        print(f"  empty -- falling back to NQ continuous", file=sys.stderr)
        df = fetch_polygon_bars("NQM26",
                                  start.strftime("%Y-%m-%d"),
                                  end.strftime("%Y-%m-%d"))
    if df.empty:
        print("Polygon returned no bars for either ticker. Aborting.",
              file=sys.stderr)
        sys.exit(1)
    print(f"  {len(df)} bars from {df.index[0]} to {df.index[-1]}",
          file=sys.stderr)

    # Run the bot's strategy on every minute close
    bars_window = deque(maxlen=600)  # ~10h of 1-min bars
    pending_setups = []
    in_trade = None
    completed = []
    last_exit_ts = None
    n_signals = 0

    today_only_start = datetime.combine(today, datetime.min.time()
                                          ).replace(tzinfo=timezone.utc)

    for ts, row in df.iterrows():
        bars_window.append({
            "open": row["open"], "high": row["high"],
            "low": row["low"], "close": row["close"], "ts": ts,
        })
        if len(bars_window) < ps.IMPULSE_WINDOW_BARS:
            continue

        # Build the DataFrame slice the strategy expects
        bw = list(bars_window)
        df_setup = pd.DataFrame(
            [(b["open"], b["high"], b["low"], b["close"]) for b in bw],
            columns=["open", "high", "low", "close"],
            index=pd.DatetimeIndex([b["ts"] for b in bw], name="ts"))

        # Detect setup at this bar's close
        setup = ps.detect_pullback_setup(df_setup, ts, params=None)
        if setup is not None:
            key = ps._setup_key(setup)
            if not any(ps._setup_key(s) == key for s in pending_setups
                       if not s.used):
                pending_setups.append(setup)
                n_signals += 1

        # Drop expired setups
        pending_setups = [s for s in pending_setups
                          if not s.is_invalidated(ts) and not s.used]

        # On every bar (proxy for tick stream): check entry/exit
        # Use the bar's high/low as bid/ask proxy for entry triggers.
        bid = row["low"]
        ask = row["high"]

        # In-trade exit check
        if in_trade is not None:
            r = ps.should_exit_on_tick(in_trade, bid, ask, ts)
            if r is not None:
                exit_px, reason = r
                # Apply realistic slip
                if reason == "stop":
                    if in_trade.side == "LONG":
                        exit_px -= 0.5
                    else:
                        exit_px += 0.5
                if in_trade.side == "LONG":
                    pnl_pts = exit_px - in_trade.entry_px
                else:
                    pnl_pts = in_trade.entry_px - exit_px
                pnl_usd = pnl_pts * 2.0 - 0.74
                completed.append({
                    "entry_ts": in_trade.entry_ts.isoformat(),
                    "exit_ts": ts.isoformat(),
                    "side": in_trade.side,
                    "entry": in_trade.entry_px,
                    "exit": exit_px,
                    "pnl_pts": pnl_pts,
                    "pnl_usd": pnl_usd,
                    "reason": reason,
                })
                last_exit_ts = ts
                in_trade = None
            continue

        # Cooldown gate
        if last_exit_ts is not None:
            if (ts - last_exit_ts).total_seconds() < ps.COOLDOWN_SECS:
                continue

        # Entry trigger: walk pending setups
        live_px = (bid + ask) / 2.0
        fired = None
        for s in pending_setups:
            if s.used:
                continue
            approach = getattr(s, "orig_side", None) or s.side
            if approach == "LONG" and live_px <= s.pullback_entry:
                fired = s; break
            if approach == "SHORT" and live_px >= s.pullback_entry:
                fired = s; break
        if fired is None:
            continue

        if fired.side == "LONG":
            entry_px = fired.pullback_entry + 0.5
        else:
            entry_px = fired.pullback_entry - 0.5
        in_trade = ps.open_trade(fired, 1, entry_px, ts)
        fired.used = True

    # Filter to TODAY only
    today_trades = [t for t in completed
                     if pd.Timestamp(t["entry_ts"]) >= today_only_start]

    print("\n" + "=" * 70)
    print(f"REPLAY ON TODAY'S POLYGON 1-MIN NQ BARS ({today.isoformat()})")
    print("=" * 70)
    print(f"Strategy: inverse pullback fade, pull=0.236, s10/t20, cd=10s")
    print(f"Ticker: {ticker}")
    print(f"Bars processed: {len(df)} (whole 36h window)")
    print(f"Signals detected: {n_signals}")
    print(f"Total completed trades: {len(completed)}")
    print(f"TODAY-only completed trades: {len(today_trades)}")

    if today_trades:
        wins = sum(1 for t in today_trades if t["pnl_usd"] > 0)
        wr = wins / len(today_trades) * 100
        net = sum(t["pnl_usd"] for t in today_trades)
        print(f"\nToday's P&L (what the bot SHOULD have done with fresh bars):")
        print(f"  Trades:    {len(today_trades)}")
        print(f"  Win rate:  {wr:.1f}%")
        print(f"  Net P&L:   ${net:+,.2f}")
        print(f"  Avg/trade: ${net/len(today_trades):+,.2f}")
        # Exit reason breakdown
        reasons = {}
        for t in today_trades:
            reasons.setdefault(t["reason"], []).append(t)
        print(f"\nExit reasons:")
        for r, ts_ in reasons.items():
            n = len(ts_)
            avg = sum(x["pnl_usd"] for x in ts_) / n
            print(f"  {r}: N={n} avg=${avg:+,.2f}")

        print(f"\nLast 10 trades:")
        for t in today_trades[-10:]:
            print(f"  {t['entry_ts']} {t['side']} entry={t['entry']:.2f} "
                  f"exit={t['exit']:.2f} {t['reason']} ${t['pnl_usd']:+.2f}")
    else:
        print("\nNo trades fired today on this data. Possible reasons:")
        print("  - Market wasn't volatile enough for the 5pt impulse threshold")
        print("  - Ticker mismatch -- try setting POLY_TICKER env")


if __name__ == "__main__":
    main()
