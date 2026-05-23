"""Unified ensemble of all proven edges, one position at a time.

Strategies in priority order (highest PF first):
  1. Asia ORB (30min OR, 0.5x target) — 66% WR, PF 2.06
  2. NY_AM ORB (15m OR, 2.0x target)  — 51% WR, PF 1.19
  3. NY_PM ORB (30m OR, 2.0x target)  — 47% WR, PF 1.12
  4. London ORB (60m OR, 1.5x target) — 48% WR, PF 1.06
  5. Lunch hour fade (11:00-12:00 range, trade to 13:00)
  6. EOD drift (14:30→15:45 lookback, exit 15:55, 8pt stop)

Conflict resolution: only one active trade at a time. Earlier signal wins.

Reports unified stats: trades, WR, PF, RR, return, DD, broken down by source.
"""
from __future__ import annotations
import numpy as np, pandas as pd
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "polygon" / "NQ_1min.csv"

STARTING_BALANCE     = 50_000.0
MNQ_PER_PT           = 2.0
COMM_PER_CONTRACT_RT = 2.0
TARGET_RISK_USD      = 150.0
MAX_CONTRACTS        = 5


def dynamic_size(stop_pts):
    if stop_pts <= 0: return 1
    return max(1, min(MAX_CONTRACTS, int(TARGET_RISK_USD / (stop_pts * MNQ_PER_PT))))


# Session definitions (NY time minutes)
SESSIONS_ORB = [
    # (name, sess_start, sess_end, or_minutes, target_mult)
    ("Asia_ORB",    18*60+0,  21*60+0,  30, 0.5),
    ("London_ORB",  3*60+0,   7*60+0,   60, 1.5),
    ("NY_AM_ORB",   9*60+30,  12*60+0,  15, 2.0),
    ("NY_PM_ORB",   13*60+0,  16*60+0,  30, 2.0),
]

LUNCH_RANGE_START = 11*60 + 0
LUNCH_RANGE_END   = 12*60 + 0
LUNCH_TRADE_END   = 13*60 + 0
LUNCH_BUFFER      = 1.0

EOD_LOOKBACK      = 14*60 + 30
EOD_ENTRY         = 15*60 + 45
EOD_EXIT          = 15*60 + 55
EOD_STOP_PTS      = 8.0
EOD_MIN_DRIFT     = 5.0


def run_unified(arr, ny_min, dates, use_trend_filter=False, prior_close_arr=None):
    o = arr[:, 0]; h = arr[:, 1]; l = arr[:, 2]; c = arr[:, 3]
    n = len(arr)

    # Per-session state
    or_state = {name: {"high": None, "low": None, "done": False, "used": False}
                for name, _, _, _, _ in SESSIONS_ORB}
    lunch_state = {"rng_h": None, "rng_l": None, "done": False, "used": False}
    eod_state = {"lookback_close": None, "used": False}

    current_date = None
    daily_open = None     # NY session open price (for HTF trend)
    active = None
    trades = []
    equity = STARTING_BALANCE
    equity_curve = np.zeros(n)

    def reset_day_state():
        for k in or_state.values():
            k["high"] = None; k["low"] = None; k["done"] = False; k["used"] = False
        lunch_state["rng_h"] = None; lunch_state["rng_l"] = None
        lunch_state["done"] = False; lunch_state["used"] = False
        eod_state["lookback_close"] = None; eod_state["used"] = False

    for t in range(n):
        d = dates[t]
        nm = int(ny_min[t])
        if d != current_date:
            current_date = d
            reset_day_state()
            daily_open = None
            if active is not None:
                exit_px = float(c[t])
                pnl_pts = (active["entry"] - exit_px) if active["side"] == "SHORT" \
                          else (exit_px - active["entry"])
                pnl = pnl_pts * active["size"] * MNQ_PER_PT - COMM_PER_CONTRACT_RT * active["size"]
                equity += pnl
                trades.append({"side": active["side"], "size": active["size"],
                               "pnl_usd": float(pnl), "exit_reason": "day_boundary",
                               "source": active["source"]})
                active = None
        # capture NY open
        if nm == 9*60 + 30 and daily_open is None:
            daily_open = float(o[t])

        # update OR formation for each session
        for (sname, ss, se, or_min, tm), state in zip(SESSIONS_ORB, [or_state[n] for n, *_ in SESSIONS_ORB]):
            if ss <= nm < ss + or_min:
                if state["high"] is None:
                    state["high"] = float(h[t]); state["low"] = float(l[t])
                else:
                    state["high"] = max(state["high"], float(h[t]))
                    state["low"]  = min(state["low"],  float(l[t]))
            elif nm == ss + or_min:
                state["done"] = True

        # update lunch range
        if LUNCH_RANGE_START <= nm < LUNCH_RANGE_END:
            if lunch_state["rng_h"] is None:
                lunch_state["rng_h"] = float(h[t]); lunch_state["rng_l"] = float(l[t])
            else:
                lunch_state["rng_h"] = max(lunch_state["rng_h"], float(h[t]))
                lunch_state["rng_l"] = min(lunch_state["rng_l"], float(l[t]))
        elif nm == LUNCH_RANGE_END:
            lunch_state["done"] = True

        # store EOD lookback close
        if nm == EOD_LOOKBACK and eod_state["lookback_close"] is None:
            eod_state["lookback_close"] = float(c[t])

        # --- manage active trade ---
        if active is not None:
            stop_hit = (active["side"] == "LONG" and l[t] <= active["stop"]) or \
                       (active["side"] == "SHORT" and h[t] >= active["stop"])
            tgt_hit = False
            if active["target"] != 0:  # 0 means time-exit only
                tgt_hit = (active["side"] == "LONG" and h[t] >= active["target"]) or \
                          (active["side"] == "SHORT" and l[t] <= active["target"])
            exit_now = False; exit_px = None; reason = ""
            if stop_hit and tgt_hit:
                exit_px = active["stop"]; reason = "stop"; exit_now = True
            elif stop_hit:
                exit_px = active["stop"]; reason = "stop"; exit_now = True
            elif tgt_hit:
                exit_px = active["target"]; reason = "target"; exit_now = True
            # source-specific time exits
            elif active["source"] == "lunch" and nm >= LUNCH_TRADE_END:
                exit_px = float(c[t]); reason = "time"; exit_now = True
            elif active["source"] == "eod" and nm >= EOD_EXIT:
                exit_px = float(c[t]); reason = "time"; exit_now = True
            elif active["source"].endswith("_ORB"):
                # find this session's end
                for sname, ss, se, *_ in SESSIONS_ORB:
                    if sname == active["source"] and nm >= se:
                        exit_px = float(c[t]); reason = "session_end"
                        exit_now = True; break
            if exit_now:
                pnl_pts = (active["entry"] - exit_px) if active["side"] == "SHORT" \
                          else (exit_px - active["entry"])
                pnl = pnl_pts * active["size"] * MNQ_PER_PT - COMM_PER_CONTRACT_RT * active["size"]
                equity += pnl
                trades.append({"side": active["side"], "size": active["size"],
                               "pnl_usd": float(pnl), "exit_reason": reason,
                               "source": active["source"]})
                active = None

        # --- entry signals (only if no active trade) ---
        if active is None:
            # 1. ORB sessions
            for sname, ss, se, or_min, tm in SESSIONS_ORB:
                state = or_state[sname]
                if state["done"] and not state["used"] and state["high"] is not None \
                        and ss + or_min <= nm < se:
                    or_size = state["high"] - state["low"]
                    if or_size > 0:
                        # HTF trend filter: bullish if current price > daily open
                        trend_long_ok = True; trend_short_ok = True
                        if use_trend_filter and daily_open is not None:
                            trend_long_ok = c[t] > daily_open
                            trend_short_ok = c[t] < daily_open
                        if c[t] > state["high"] and trend_long_ok:
                            entry_px = float(c[t])
                            stop_px = state["low"]
                            target_px = state["high"] + tm * or_size
                            stop_pts = entry_px - stop_px
                            if stop_pts > 0:
                                size = dynamic_size(stop_pts)
                                active = {"side": "LONG", "size": size,
                                          "entry": entry_px, "stop": stop_px,
                                          "target": target_px, "source": sname,
                                          "entry_bar": t}
                                state["used"] = True
                                break
                        elif c[t] < state["low"] and trend_short_ok:
                            entry_px = float(c[t])
                            stop_px = state["high"]
                            target_px = state["low"] - tm * or_size
                            stop_pts = stop_px - entry_px
                            if stop_pts > 0:
                                size = dynamic_size(stop_pts)
                                active = {"side": "SHORT", "size": size,
                                          "entry": entry_px, "stop": stop_px,
                                          "target": target_px, "source": sname,
                                          "entry_bar": t}
                                state["used"] = True
                                break

            # 2. Lunch fade
            if (active is None and lunch_state["done"] and not lunch_state["used"]
                    and lunch_state["rng_h"] is not None
                    and LUNCH_RANGE_END <= nm < LUNCH_TRADE_END):
                rh = lunch_state["rng_h"]; rl = lunch_state["rng_l"]
                mid = (rh + rl) / 2
                if h[t] >= rh:
                    entry_px = float(rh)
                    stop_px = entry_px + LUNCH_BUFFER
                    target_px = mid
                    stop_pts = stop_px - entry_px
                    if stop_pts > 0:
                        size = dynamic_size(stop_pts)
                        active = {"side": "SHORT", "size": size,
                                  "entry": entry_px, "stop": stop_px,
                                  "target": target_px, "source": "lunch",
                                  "entry_bar": t}
                        lunch_state["used"] = True
                elif l[t] <= rl:
                    entry_px = float(rl)
                    stop_px = entry_px - LUNCH_BUFFER
                    target_px = mid
                    stop_pts = entry_px - stop_px
                    if stop_pts > 0:
                        size = dynamic_size(stop_pts)
                        active = {"side": "LONG", "size": size,
                                  "entry": entry_px, "stop": stop_px,
                                  "target": target_px, "source": "lunch",
                                  "entry_bar": t}
                        lunch_state["used"] = True

            # 3. EOD drift
            if (active is None and not eod_state["used"]
                    and eod_state["lookback_close"] is not None
                    and nm == EOD_ENTRY):
                cur = float(c[t])
                drift = cur - eod_state["lookback_close"]
                if abs(drift) >= EOD_MIN_DRIFT:
                    size = dynamic_size(EOD_STOP_PTS)
                    if drift > 0:
                        active = {"side": "LONG", "size": size,
                                  "entry": cur, "stop": cur - EOD_STOP_PTS,
                                  "target": 0, "source": "eod",
                                  "entry_bar": t}
                    else:
                        active = {"side": "SHORT", "size": size,
                                  "entry": cur, "stop": cur + EOD_STOP_PTS,
                                  "target": 0, "source": "eod",
                                  "entry_bar": t}
                    eod_state["used"] = True

        equity_curve[t] = equity

    return trades, pd.Series(equity_curve, index=pd.RangeIndex(len(equity_curve)))


def main():
    print("Loading NQ 1-min data...")
    nq = pd.read_csv(DATA_FILE, parse_dates=["ts"]).set_index("ts").sort_index()
    if nq.index.tz is None: nq.index = nq.index.tz_localize("UTC")
    months = (nq.index[-1] - nq.index[0]).days / 30.44
    cal_days = (nq.index[-1] - nq.index[0]).days
    ny = nq.index.tz_convert("America/New_York")
    ny_min = (ny.hour * 60 + ny.minute).to_numpy()
    dates = ny.date
    arr = nq[["open", "high", "low", "close"]].to_numpy()

    print(f"  bars: {len(nq):,}, months: {months:.1f}\n")
    print("Running ensemble WITHOUT trend filter...")
    trades_a, _ = run_unified(arr, ny_min, dates, use_trend_filter=False)
    print("Running ensemble WITH trend filter (only ORB with daily direction)...")
    trades_b, _ = run_unified(arr, ny_min, dates, use_trend_filter=True)

    def show(label, trades):
        if not trades:
            print(f"{label}: no trades"); return
        tdf = pd.DataFrame(trades)
        n = len(tdf)
        wins = int((tdf["pnl_usd"] > 0).sum())
        gw = float(tdf[tdf["pnl_usd"] > 0]["pnl_usd"].sum())
        gl = float(abs(tdf[tdf["pnl_usd"] < 0]["pnl_usd"].sum()))
        pf = gw / gl if gl > 0 else float("inf")
        total = float(tdf["pnl_usd"].sum())
        avg_w = float(tdf[tdf["pnl_usd"] > 0]["pnl_usd"].mean()) if wins else 0
        avg_l = float(tdf[tdf["pnl_usd"] < 0]["pnl_usd"].mean()) if wins < n else 0
        rr = abs(avg_w/avg_l) if avg_l != 0 else 0
        cum = tdf["pnl_usd"].cumsum().to_numpy()
        maxdd = float((cum - np.maximum.accumulate(cum)).min())
        streak = max_streak = 0
        for _, row in tdf.iterrows():
            if row["pnl_usd"] < 0:
                streak += 1
                if streak > max_streak: max_streak = streak
            else: streak = 0
        print(f"\n{'='*78}\n{label}\n{'='*78}")
        print(f"Total trades: {n} ({n/months:.1f}/mo, {n/months/4.3:.1f}/wk, {n/cal_days:.2f}/day)")
        print(f"WR: {wins/n*100:.2f}%  PF: {pf:.2f}  RR: {rr:.2f}")
        print(f"$/trade: ${total/n:+.2f}  Total: ${total:+,.0f}  "
              f"Return: {total/STARTING_BALANCE*100/months:+.2f}%/mo")
        print(f"Max DD: ${maxdd:+,.0f}  Max streak: {max_streak}")
        # source breakdown
        print("By source:")
        for src in tdf["source"].unique():
            g = tdf[tdf["source"] == src]
            gn = len(g)
            gw_ = int((g["pnl_usd"] > 0).sum())
            gpnl = g["pnl_usd"].sum()
            gpf = (g[g["pnl_usd"] > 0]["pnl_usd"].sum()
                   / abs(g[g["pnl_usd"] < 0]["pnl_usd"].sum())) \
                  if (g["pnl_usd"] < 0).any() else float("inf")
            print(f"  {src:<12} n={gn:>4}  WR={gw_/gn*100:.1f}%  "
                  f"PF={gpf:.2f}  Total=${gpnl:+,.0f}")
        # spec
        rpm = total/STARTING_BALANCE*100/months
        print("\nSpec check:")
        print(f"  WR  >= 55%: {'✅' if wins/n*100 >= 55 else '❌'} ({wins/n*100:.1f}%)")
        print(f"  RR  >= 1.2: {'✅' if rr >= 1.2 else '❌'} ({rr:.2f})")
        print(f"  Ret >= 3%/mo: {'✅' if rpm >= 3 else '❌'} ({rpm:+.2f}%/mo)")
        print(f"  Freq >= 1/day: {'✅' if n/cal_days >= 1 else '❌'} ({n/cal_days:.2f}/day)")

    cal_days = (nq.index[-1] - nq.index[0]).days
    show("WITHOUT trend filter", trades_a)
    show("WITH trend filter (daily direction confluence on ORBs)", trades_b)
    return  # rest of original main() inlined into show()
    trades, equity = run_unified(arr, ny_min, dates)

    if not trades:
        print("No trades."); return
    tdf = pd.DataFrame(trades)
    n = len(tdf)
    wins = int((tdf["pnl_usd"] > 0).sum())
    gw = float(tdf[tdf["pnl_usd"] > 0]["pnl_usd"].sum())
    gl = float(abs(tdf[tdf["pnl_usd"] < 0]["pnl_usd"].sum()))
    total = float(tdf["pnl_usd"].sum())
    pf = gw / gl if gl > 0 else float("inf")
    avg_w = float(tdf[tdf["pnl_usd"] > 0]["pnl_usd"].mean()) if wins else 0
    avg_l = float(tdf[tdf["pnl_usd"] < 0]["pnl_usd"].mean()) if wins < n else 0
    rr = abs(avg_w / avg_l) if avg_l != 0 else 0
    streak = max_streak = 0
    for _, row in tdf.iterrows():
        if row["pnl_usd"] < 0:
            streak += 1
            if streak > max_streak: max_streak = streak
        else: streak = 0
    cum = tdf["pnl_usd"].cumsum().to_numpy()
    maxdd = float((cum - np.maximum.accumulate(cum)).min())

    print("\n" + "=" * 80)
    print("UNIFIED ENSEMBLE RESULTS (one position at a time, true P&L)")
    print("=" * 80)
    print(f"Period:        {nq.index[0].date()} → {nq.index[-1].date()}  ({months:.1f} months)")
    print(f"Total trades:  {n}")
    print(f"  per month:   {n/months:.1f}")
    print(f"  per week:    {n/months/4.3:.1f}")
    print(f"  per day:     {n/cal_days:.2f}")
    print(f"Win rate:      {wins/n*100:.2f}%")
    print(f"Profit factor: {pf:.2f}")
    print(f"RR (actual):   {rr:.2f}")
    print(f"Avg win:       ${avg_w:+.2f}")
    print(f"Avg loss:      ${avg_l:+.2f}")
    print(f"Per trade:     ${total/n:+.2f}")
    print(f"Total P&L:     ${total:+,.0f}")
    print(f"Return:        {total/STARTING_BALANCE*100:+.1f}%  ({total/STARTING_BALANCE*100/months:+.2f}%/mo)")
    print(f"Max DD:        ${maxdd:+,.0f}")
    print(f"Max losing streak: {max_streak} trades")

    print("\n" + "-" * 80)
    print("BREAKDOWN BY SOURCE")
    print("-" * 80)
    for src in tdf["source"].unique():
        g = tdf[tdf["source"] == src]
        gn = len(g)
        gw_ = int((g["pnl_usd"] > 0).sum())
        gpnl = g["pnl_usd"].sum()
        gpf = g[g["pnl_usd"] > 0]["pnl_usd"].sum() / abs(g[g["pnl_usd"] < 0]["pnl_usd"].sum()) \
              if (g["pnl_usd"] < 0).any() else float("inf")
        print(f"  {src:<12} n={gn:>4}  WR={gw_/gn*100:.1f}%  PF={gpf:.2f}  "
              f"$/tr=${gpnl/gn:+.0f}  Total=${gpnl:+,.0f}")

    # Check against user spec
    print("\n" + "=" * 80)
    print("USER SPEC CHECK")
    print("=" * 80)
    spec_results = {
        "WR ≥ 55%": (wins/n*100 >= 55, f"{wins/n*100:.1f}%"),
        "RR ≥ 1.2": (rr >= 1.2, f"{rr:.2f}"),
        "Return ≥ 3%/mo": (total/STARTING_BALANCE*100/months >= 3.0,
                          f"{total/STARTING_BALANCE*100/months:.2f}%/mo"),
        "High frequency": (n/cal_days >= 1, f"{n/cal_days:.2f}/day"),
    }
    for spec, (passed, val) in spec_results.items():
        mark = "✅" if passed else "❌"
        print(f"  {mark} {spec:<25} → {val}")


if __name__ == "__main__":
    main()
