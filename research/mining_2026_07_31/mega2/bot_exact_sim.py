"""EXACT-bot simulation of Friday 2026-08-14: the live executor's real
code, tick by tick, over the session's real tape.

Not the research fill model -- this drives the ACTUAL functions the
Railway bot runs, under the exact forced env of the fixed build:

  - detect_pullback_setup via on_new_1m_bar (real bar path, RTH gate)
  - try_fire_on_tick (real tick path, 1.0pt fire drift gate)
  - should_exit_on_tick / close_trade (real exits: stop slip, spread,
    600s max hold, 60s cooldown)

Two ledgers are reported:
  PAPER  -- what the bot's own book would have shown (dashboard's view,
            $0.74 RT as the account layer charges).
  BROKER -- which of those entries the OSO-fallback resting LIMIT would
            genuinely have filled (tape must trade THROUGH the limit
            while the trade is alive), $1.24 RT demo commission, target
            exits pay the half-spread the instant-close market pays.

Input: data/tick/week/MNQU6_20260814.parquet. Output:
research/BOT_EXACT_FRIDAY.md.
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

# The fixed build's forced env -- MUST be set before bot imports
os.environ.update({
    "BOT_DATA_DIR": "/tmp/simdata",
    "BROKER_ENGINE": "mirror", "BOT_SHADOW_MODE": "0",
    "STRAT_IMPULSE_PTS": "5.0", "STRAT_IMPULSE_BARS": "6",
    "STRAT_PULL_PCT": "0.618", "STRAT_STOP_PTS": "10.0",
    "STRAT_TARGET_PTS": "20.0", "STRAT_INVERT": "0",
    "STRAT_TICK_SIZE": "0.25", "STRAT_COOLDOWN_SECS": "60",
    "STRAT_FIRE_DRIFT_GATE_PT": "1.0", "STRAT_RTH_ONLY": "1",
    "BOT_TRADING_HOURS": "cme", "ANTICIPATORY_ENABLED": "0",
})
os.makedirs("/tmp/simdata", exist_ok=True)

import numpy as np                                        # noqa: E402
import pandas as pd                                       # noqa: E402

from bot.pullback_strategy import (                       # noqa: E402
    FibStrategyState, on_new_1m_bar, try_fire_on_tick,
    should_exit_on_tick, close_trade)
from research.lucid_guard import LucidState               # noqa: E402

DAY = os.environ.get("REPLAY_DAY", "20260814")
PARAMS = {"IMPULSE_PTS": 5.0, "IMPULSE_WINDOW_BARS": 6,
          "PULLBACK_PCT": 0.618, "STOP_PTS": 10.0, "TARGET_PTS": 20.0,
          "INVERT": False}
PAPER_COMM = 0.74     # what the bot's account layer charges per RT
BROKER_COMM = 1.24    # Tradovate demo reality
HALF_SPREAD = 0.125

p = ROOT / "data" / "tick" / "week" / f"MNQU6_{DAY}.parquet"
df = pd.read_parquet(p)
ts = df["ts"].to_numpy(dtype=np.int64)
px = df["price"].to_numpy(dtype=np.float64)
o = np.argsort(ts, kind="stable")
ts, px = ts[o], px[o]
print(f"{len(ts):,} ticks loaded", flush=True)

state = FibStrategyState()
lucid = LucidState()
records = []

bars = []                # closed bars: (time, o, h, l, c)
cur_min = None
cur = None               # [o, h, l, c]
bars_df = None

n = len(ts)
for k in range(n):
    t_ns = int(ts[k])
    price = float(px[k])
    now = datetime.utcfromtimestamp(t_ns / 1e9)
    m = t_ns // 60_000_000_000
    if cur_min is None:
        cur_min, cur = m, [price, price, price, price]
    elif m > cur_min:
        bars.append((pd.Timestamp(cur_min * 60, unit="s"), *cur))
        if len(bars) > 300:
            bars = bars[-300:]
        bars_df = pd.DataFrame(
            [b[1:] for b in bars], columns=["open", "high", "low", "close"],
            index=pd.DatetimeIndex([b[0] for b in bars]))
        bar_now = (bars_df.index[-1] + timedelta(seconds=60)).to_pydatetime()
        if len(bars_df) >= 7:
            try:
                rec = on_new_1m_bar(state, lucid, bars_df,
                                    bars_df.iloc[-1], bar_now, n_mnq=1,
                                    bars_trend=bars_df, params=PARAMS,
                                    calendar=None)
                if rec is not None:
                    records.append(rec)
            except Exception as e:
                print(f"bar {bar_now}: {e!r}", flush=True)
        cur_min, cur = m, [price, price, price, price]
    else:
        cur[1] = max(cur[1], price)
        cur[2] = min(cur[2], price)
        cur[3] = price

    bid, ask = price - HALF_SPREAD, price + HALF_SPREAD
    if state.active_trade is not None:
        ex = should_exit_on_tick(state.active_trade, bid, ask, now)
        if ex:
            exit_px, reason = ex
            rec = close_trade(state.active_trade, exit_px, reason, now)
            state.completed_trades.append(rec) if hasattr(
                state, "completed_trades") else None
            state.active_trade = None
            state.last_trade_close_ts = now
            records.append(rec)
    else:
        try:
            try_fire_on_tick(state, lucid, price, now, n_mnq=1,
                             params=PARAMS, calendar=None)
        except Exception as e:
            if k % 100000 == 0:
                print(f"tick fire {now}: {e!r}", flush=True)

# flatten anything open at close
if state.active_trade is not None:
    rec = close_trade(state.active_trade, float(px[-1]), "eod_flat",
                      datetime.utcfromtimestamp(int(ts[-1]) / 1e9))
    records.append(rec)

# ---- broker overlay: would the resting LIMIT have filled? ----
rows = []
paper_total = broker_total = 0.0
filled_n = 0
for r in records:
    et = r["entry_ts"]
    xt = r["exit_ts"]
    e_ns = int(pd.Timestamp(et).value)
    x_ns = int(pd.Timestamp(xt).value)
    j0 = np.searchsorted(ts, e_ns)
    j1 = np.searchsorted(ts, x_ns, side="right")
    seg = px[j0:j1]
    if r["side"] == "LONG":
        filled = bool(len(seg) and (seg < r["entry_px"]).any())
    else:
        filled = bool(len(seg) and (seg > r["entry_px"]).any())
    paper_pnl = r["pnl_usd"] - PAPER_COMM
    broker_pnl = None
    if filled:
        adj = r["adj_exit_px"]
        if r["exit_reason"] == "target":
            adj = adj - HALF_SPREAD if r["side"] == "LONG" \
                else adj + HALF_SPREAD
        pts = (adj - r["entry_px"]) if r["side"] == "LONG" \
            else (r["entry_px"] - adj)
        broker_pnl = pts * 2.0 - BROKER_COMM
        broker_total += broker_pnl
        filled_n += 1
    paper_total += paper_pnl
    rows.append((pd.Timestamp(et).strftime("%H:%M:%S"),
                 pd.Timestamp(xt).strftime("%H:%M:%S"),
                 r["side"], r["entry_px"], r["exit_reason"],
                 int(r["hold_s"]), round(paper_pnl, 2),
                 "yes" if filled else "NO",
                 round(broker_pnl, 2) if broker_pnl is not None else ""))

L = [f"# EXACT bot simulation -- Friday {DAY[:4]}-{DAY[4:6]}-{DAY[6:]}",
     "",
     "The live executor's real code (fixed build: mirror engine, 1pt "
     "fire drift gate, 60s cooldown, RTH gate) driven tick-by-tick "
     f"over the session's {len(ts):,} real MNQU6 ticks.", "",
     "| entry | exit | side | entry px | reason | hold s | paper P&L | "
     "broker fill? | broker P&L |", "|" + "---|" * 9]
for row in rows:
    L.append("| " + " | ".join(str(x) for x in row) + " |")
wins = sum(1 for r in rows if r[6] > 0)
L += ["",
      f"## PAPER book (dashboard's view): **${paper_total:+,.2f}** on "
      f"{len(rows)} trades, {wins}/{len(rows)} wins "
      f"(${PAPER_COMM}/RT)",
      f"## BROKER truth: **${broker_total:+,.2f}** -- {filled_n}/"
      f"{len(rows)} entries actually fill the resting LIMIT "
      f"(${BROKER_COMM}/RT, target exits pay half-spread)",
      "",
      "Unfilled entries are paper-only: the tape never traded through "
      "the limit while the trade was alive, so the broker order would "
      "have been cancelled at paper exit (orphan path).", ""]
out = ROOT / "research" / "BOT_EXACT_FRIDAY.md"
out.write_text("\n".join(L) + "\n")
print(f"paper ${paper_total:+,.2f} | broker ${broker_total:+,.2f} "
      f"({filled_n}/{len(rows)} filled)")
print("wrote", out)
