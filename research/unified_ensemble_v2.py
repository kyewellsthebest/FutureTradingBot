"""Unified ensemble v2: existing + 15-min engulfing edge."""
from __future__ import annotations
import numpy as np, pandas as pd
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "polygon" / "NQ_1min.csv"

STARTING_BALANCE     = 50_000.0
MNQ_PER_PT           = 2.0
COMM_PER_CONTRACT_RT = 2.0
TARGET_RISK_USD      = 50.0
MAX_CONTRACTS        = 5


def sz(stop_pts):
    if stop_pts <= 0: return 1
    return max(1, min(MAX_CONTRACTS, int(TARGET_RISK_USD / (stop_pts * MNQ_PER_PT))))


SESSIONS_ORB = [
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
ENGULF_TARGET_R   = 2.0
ENGULF_STOP_BUF   = 1.0


def run(arr_1m, arr_15m, ny_min, dates, idx_15m_in_1m):
    o = arr_1m[:, 0]; h = arr_1m[:, 1]; l = arr_1m[:, 2]; c = arr_1m[:, 3]
    o15 = arr_15m[:, 0]; h15 = arr_15m[:, 1]; l15 = arr_15m[:, 2]; c15 = arr_15m[:, 3]
    n = len(arr_1m)
    n15 = len(arr_15m)

    engulf_by_bar = {}
    for k in range(1, n15):
        po, pc = o15[k-1], c15[k-1]
        co, cc = o15[k], c15[k]
        if pc > po and cc < co and co > pc and cc < po:
            # Bearish engulfing → SHORT next bar
            target_1m = idx_15m_in_1m[k]
            if target_1m is not None and target_1m + 1 < n:
                entry = float(c15[k])
                stop = float(h15[k]) + ENGULF_STOP_BUF
                stop_pts = stop - entry
                if stop_pts > 0:
                    engulf_by_bar[target_1m + 1] = {
                        "side": "SHORT", "entry": entry, "stop": stop,
                        "target": entry - ENGULF_TARGET_R * stop_pts,
                        "stop_pts": stop_pts,
                    }
        elif pc < po and cc > co and co < pc and cc > po:
            target_1m = idx_15m_in_1m[k]
            if target_1m is not None and target_1m + 1 < n:
                entry = float(c15[k])
                stop = float(l15[k]) - ENGULF_STOP_BUF
                stop_pts = entry - stop
                if stop_pts > 0:
                    engulf_by_bar[target_1m + 1] = {
                        "side": "LONG", "entry": entry, "stop": stop,
                        "target": entry + ENGULF_TARGET_R * stop_pts,
                        "stop_pts": stop_pts,
                    }

    or_state = {name: {"high": None, "low": None, "done": False, "used": False}
                for name, _, _, _, _ in SESSIONS_ORB}
    lunch_state = {"rng_h": None, "rng_l": None, "done": False, "used": False}
    eod_state = {"lookback_close": None, "used": False}

    current_date = None
    active = None
    trades = []
    equity = STARTING_BALANCE

    def reset_day():
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
            reset_day()
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

        for sname, ss, se, or_min, tm in SESSIONS_ORB:
            state = or_state[sname]
            if ss <= nm < ss + or_min:
                if state["high"] is None:
                    state["high"] = float(h[t]); state["low"] = float(l[t])
                else:
                    state["high"] = max(state["high"], float(h[t]))
                    state["low"]  = min(state["low"],  float(l[t]))
            elif nm == ss + or_min:
                state["done"] = True

        if LUNCH_RANGE_START <= nm < LUNCH_RANGE_END:
            if lunch_state["rng_h"] is None:
                lunch_state["rng_h"] = float(h[t]); lunch_state["rng_l"] = float(l[t])
            else:
                lunch_state["rng_h"] = max(lunch_state["rng_h"], float(h[t]))
                lunch_state["rng_l"] = min(lunch_state["rng_l"], float(l[t]))
        elif nm == LUNCH_RANGE_END:
            lunch_state["done"] = True

        if nm == EOD_LOOKBACK and eod_state["lookback_close"] is None:
            eod_state["lookback_close"] = float(c[t])

        if active is not None:
            stop_hit = (active["side"] == "LONG" and l[t] <= active["stop"]) or \
                       (active["side"] == "SHORT" and h[t] >= active["stop"])
            tgt_hit = False
            if active["target"] != 0:
                tgt_hit = (active["side"] == "LONG" and h[t] >= active["target"]) or \
                          (active["side"] == "SHORT" and l[t] <= active["target"])
            exit_px = None; reason = ""
            if stop_hit and tgt_hit: exit_px = active["stop"]; reason = "stop"
            elif stop_hit: exit_px = active["stop"]; reason = "stop"
            elif tgt_hit: exit_px = active["target"]; reason = "target"
            elif active["source"] == "lunch" and nm >= LUNCH_TRADE_END:
                exit_px = float(c[t]); reason = "time"
            elif active["source"] == "eod" and nm >= EOD_EXIT:
                exit_px = float(c[t]); reason = "time"
            elif active["source"] == "engulf" and t - active["entry_bar"] >= 120:
                exit_px = float(c[t]); reason = "time"
            elif active["source"].endswith("_ORB"):
                for sname, ss, se, *_ in SESSIONS_ORB:
                    if sname == active["source"] and nm >= se:
                        exit_px = float(c[t]); reason = "session_end"; break
            if exit_px is not None:
                pnl_pts = (active["entry"] - exit_px) if active["side"] == "SHORT" \
                          else (exit_px - active["entry"])
                pnl = pnl_pts * active["size"] * MNQ_PER_PT - COMM_PER_CONTRACT_RT * active["size"]
                equity += pnl
                trades.append({"side": active["side"], "size": active["size"],
                               "pnl_usd": float(pnl), "exit_reason": reason,
                               "source": active["source"]})
                active = None

        if active is None:
            if t in engulf_by_bar:
                sig = engulf_by_bar[t]
                active = {"side": sig["side"], "size": sz(sig["stop_pts"]),
                          "entry": sig["entry"], "stop": sig["stop"],
                          "target": sig["target"], "source": "engulf",
                          "entry_bar": t}
            else:
                for sname, ss, se, or_min, tm in SESSIONS_ORB:
                    state = or_state[sname]
                    if state["done"] and not state["used"] and state["high"] is not None \
                            and ss + or_min <= nm < se:
                        or_size = state["high"] - state["low"]
                        if or_size > 0:
                            if c[t] > state["high"]:
                                entry = float(c[t]); stop = state["low"]
                                stop_pts = entry - stop
                                if stop_pts > 0:
                                    active = {"side": "LONG", "size": sz(stop_pts),
                                              "entry": entry, "stop": stop,
                                              "target": state["high"] + tm * or_size,
                                              "source": sname, "entry_bar": t}
                                    state["used"] = True; break
                            elif c[t] < state["low"]:
                                entry = float(c[t]); stop = state["high"]
                                stop_pts = stop - entry
                                if stop_pts > 0:
                                    active = {"side": "SHORT", "size": sz(stop_pts),
                                              "entry": entry, "stop": stop,
                                              "target": state["low"] - tm * or_size,
                                              "source": sname, "entry_bar": t}
                                    state["used"] = True; break
            if (active is None and lunch_state["done"] and not lunch_state["used"]
                    and lunch_state["rng_h"] is not None
                    and LUNCH_RANGE_END <= nm < LUNCH_TRADE_END):
                rh = lunch_state["rng_h"]; rl = lunch_state["rng_l"]
                mid = (rh + rl) / 2
                if h[t] >= rh:
                    entry = float(rh); stop = entry + LUNCH_BUFFER
                    stop_pts = stop - entry
                    if stop_pts > 0:
                        active = {"side": "SHORT", "size": sz(stop_pts),
                                  "entry": entry, "stop": stop, "target": mid,
                                  "source": "lunch", "entry_bar": t}
                        lunch_state["used"] = True
                elif l[t] <= rl:
                    entry = float(rl); stop = entry - LUNCH_BUFFER
                    stop_pts = entry - stop
                    if stop_pts > 0:
                        active = {"side": "LONG", "size": sz(stop_pts),
                                  "entry": entry, "stop": stop, "target": mid,
                                  "source": "lunch", "entry_bar": t}
                        lunch_state["used"] = True
            if (active is None and not eod_state["used"]
                    and eod_state["lookback_close"] is not None
                    and nm == EOD_ENTRY):
                cur = float(c[t])
                drift = cur - eod_state["lookback_close"]
                if abs(drift) >= EOD_MIN_DRIFT:
                    size = sz(EOD_STOP_PTS)
                    if drift > 0:
                        active = {"side": "LONG", "size": size, "entry": cur,
                                  "stop": cur - EOD_STOP_PTS, "target": 0,
                                  "source": "eod", "entry_bar": t}
                    else:
                        active = {"side": "SHORT", "size": size, "entry": cur,
                                  "stop": cur + EOD_STOP_PTS, "target": 0,
                                  "source": "eod", "entry_bar": t}
                    eod_state["used"] = True

    return trades


def main():
    print("Loading 1-min data...")
    nq = pd.read_csv(DATA_FILE, parse_dates=["ts"]).set_index("ts").sort_index()
    if nq.index.tz is None: nq.index = nq.index.tz_localize("UTC")
    months = (nq.index[-1] - nq.index[0]).days / 30.44
    cal_days = (nq.index[-1] - nq.index[0]).days

    nq15 = nq.resample("15min").agg({"open":"first","high":"max","low":"min","close":"last"}).dropna()
    # build mapping from 15-min bars to 1-min closing bar index
    idx_15m_in_1m = []
    nq_index_arr = nq.index
    for ts in nq15.index:
        close_ts = ts + pd.Timedelta(minutes=14)
        try:
            pos = nq_index_arr.get_indexer([close_ts], method="nearest")[0]
            idx_15m_in_1m.append(int(pos))
        except Exception:
            idx_15m_in_1m.append(None)

    ny = nq.index.tz_convert("America/New_York")
    ny_min = (ny.hour * 60 + ny.minute).to_numpy()
    dates = ny.date
    arr_1m = nq[["open","high","low","close"]].to_numpy()
    arr_15m = nq15[["open","high","low","close"]].to_numpy()

    print(f"  1-min bars: {len(nq):,}, 15-min bars: {len(nq15):,}")
    print("Running unified ensemble v2...")
    trades = run(arr_1m, arr_15m, ny_min, dates, idx_15m_in_1m)

    if not trades: print("No trades"); return
    tdf = pd.DataFrame(trades)
    n = len(tdf)
    wins = int((tdf["pnl_usd"] > 0).sum())
    gw = float(tdf[tdf["pnl_usd"] > 0]["pnl_usd"].sum())
    gl = float(abs(tdf[tdf["pnl_usd"] < 0]["pnl_usd"].sum()))
    total = float(tdf["pnl_usd"].sum())
    pf = gw / gl if gl > 0 else float("inf")
    avg_w = float(tdf[tdf["pnl_usd"] > 0]["pnl_usd"].mean()) if wins else 0
    avg_l = float(tdf[tdf["pnl_usd"] < 0]["pnl_usd"].mean()) if wins < n else 0
    rr = abs(avg_w/avg_l) if avg_l != 0 else 0
    cum = tdf["pnl_usd"].cumsum().to_numpy()
    maxdd = float((cum - np.maximum.accumulate(cum)).min())

    print("\n" + "=" * 80)
    print("UNIFIED ENSEMBLE V2 (with 15-min engulfing)")
    print("=" * 80)
    print(f"Trades:    {n} ({n/months:.1f}/mo, {n/cal_days:.2f}/day)")
    print(f"WR:        {wins/n*100:.2f}%")
    print(f"PF:        {pf:.2f}")
    print(f"RR:        {rr:.2f}")
    print(f"$/trade:   ${total/n:+.2f}")
    print(f"Total:     ${total:+,.0f}")
    print(f"Return:    {total/STARTING_BALANCE*100/months:+.2f}%/mo")
    print(f"Max DD:    ${maxdd:+,.0f} ({maxdd/STARTING_BALANCE*100:+.1f}%)")

    print("\nBy source:")
    for src in tdf["source"].unique():
        g = tdf[tdf["source"] == src]
        gn = len(g)
        gw_ = int((g["pnl_usd"] > 0).sum())
        gpnl = g["pnl_usd"].sum()
        gpf = (g[g["pnl_usd"] > 0]["pnl_usd"].sum()
               / abs(g[g["pnl_usd"] < 0]["pnl_usd"].sum())) \
              if (g["pnl_usd"] < 0).any() else float("inf")
        print(f"  {src:<12} n={gn:>4}  WR={gw_/gn*100:.1f}%  PF={gpf:.2f}  "
              f"Total=${gpnl:+,.0f}")

    print("\nSPEC CHECK:")
    rpm = total / STARTING_BALANCE * 100 / months
    dd_pct = abs(maxdd / STARTING_BALANCE * 100)
    print(f"  WR  ≥ 55%:     {'✅' if wins/n*100 >= 55 else '❌'}  ({wins/n*100:.1f}%)")
    print(f"  RR  ≥ 1.2:     {'✅' if rr >= 1.2 else '❌'}  ({rr:.2f})")
    print(f"  Freq ≥ 100/mo: {'✅' if n/months >= 100 else '❌'}  ({n/months:.1f}/mo)")
    print(f"  Ret ≥ 3%/mo:   {'✅' if rpm >= 3 else '❌'}  ({rpm:+.2f}%/mo)")
    print(f"  DD ≤ 2%:       {'✅' if dd_pct <= 2 else '❌'}  ({dd_pct:.1f}%)")


if __name__ == "__main__":
    main()
