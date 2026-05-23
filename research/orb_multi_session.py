"""ORB variations to boost trade frequency while keeping edge.

ORB is the one strategy with confirmed positive edge (+0.86%/mo at 13
trades/mo). To get 3%/mo with similar quality we need 3-4x more
volume. Things to try:

A. MULTI-SESSION ORB
   - Asia open: 18:00 ET (prior day, futures roll)
   - London open: 03:00 ET
   - NY AM open: 09:30 ET
   - NY PM (lunch break end): 13:00 ET
   Each session has its own opening range and breakout signal.

B. SHORTER OR WINDOWS
   - 5min, 10min, 15min OR (faster signals)

C. RE-ENTRY ON FAILURE
   - If first ORB stops out, allow one re-entry in the other direction

D. PULLBACK ENTRY
   - Wait for price to retrace to OR boundary after breakout before entering
   - Higher WR but fewer trades
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

# Sessions: (name, start_minute_NY, end_minute_NY for OR formation)
SESSIONS = [
    ("Asia",    18 * 60 + 0,   21 * 60 + 0),    # 18:00-21:00 NY (3 hour Asian session start)
    ("London",  3 * 60 + 0,    7 * 60 + 0),     # 03:00-07:00 NY (London)
    ("NY_AM",   9 * 60 + 30,   12 * 60 + 0),    # 09:30-12:00 NY AM
    ("NY_PM",   13 * 60 + 0,   16 * 60 + 0),    # 13:00-16:00 NY PM
]


def dynamic_size(stop_pts: float) -> int:
    if stop_pts <= 0: return 1
    return max(1, min(MAX_CONTRACTS, int(TARGET_RISK_USD / (stop_pts * MNQ_PER_PT))))


def find_session_orb(arr, ny_min_arr, dates, session_name,
                     session_start_min, session_end_min,
                     or_minutes, target_mult, max_one_per_session=True):
    """Find ORB trades for one session. Returns list of trade dicts."""
    o = arr[:, 0]; h = arr[:, 1]; l = arr[:, 2]; c = arr[:, 3]
    n = len(arr)
    trades = []
    current_date = None
    or_high = or_low = None
    or_done = False
    session_used = False
    active = None

    for t in range(n):
        d = dates[t]
        ny_min = int(ny_min_arr[t])
        if d != current_date:
            current_date = d
            or_high = or_low = None
            or_done = False
            session_used = False
            if active is not None:
                # close at day boundary
                exit_px = float(c[t])
                pnl_pts = (active["entry"] - exit_px) if active["side"] == "SHORT" \
                          else (exit_px - active["entry"])
                pnl = pnl_pts * active["size"] * MNQ_PER_PT - COMM_PER_CONTRACT_RT * active["size"]
                trades.append({"side": active["side"], "size": active["size"],
                               "pnl_usd": float(pnl), "session": session_name,
                               "exit_reason": "session_end",
                               "entry_bar": active["entry_bar"], "exit_bar": t})
                active = None

        # check if in OR formation window
        or_form_start = session_start_min
        or_form_end = session_start_min + or_minutes
        if or_form_start <= ny_min < or_form_end:
            if or_high is None:
                or_high = float(h[t]); or_low = float(l[t])
            else:
                or_high = max(or_high, float(h[t]))
                or_low  = min(or_low,  float(l[t]))
        elif ny_min == or_form_end:
            or_done = True

        # manage active trade
        if active is not None:
            stop_hit = (active["side"] == "LONG" and l[t] <= active["stop"]) or \
                       (active["side"] == "SHORT" and h[t] >= active["stop"])
            tgt_hit  = (active["side"] == "LONG" and h[t] >= active["target"]) or \
                       (active["side"] == "SHORT" and l[t] <= active["target"])
            exit_px = None; reason = ""
            if stop_hit and tgt_hit: exit_px = active["stop"]; reason = "stop"
            elif stop_hit: exit_px = active["stop"]; reason = "stop"
            elif tgt_hit:  exit_px = active["target"]; reason = "target"
            elif ny_min == session_end_min:
                exit_px = float(c[t]); reason = "session_end"
            if exit_px is not None:
                pnl_pts = (active["entry"] - exit_px) if active["side"] == "SHORT" \
                          else (exit_px - active["entry"])
                pnl = pnl_pts * active["size"] * MNQ_PER_PT - COMM_PER_CONTRACT_RT * active["size"]
                trades.append({"side": active["side"], "size": active["size"],
                               "pnl_usd": float(pnl), "session": session_name,
                               "exit_reason": reason,
                               "entry_bar": active["entry_bar"], "exit_bar": t})
                active = None

        # entry only after OR done, within session, not used yet
        if (active is None and or_done and not session_used and or_high is not None
                and or_form_end <= ny_min < session_end_min):
            or_size = or_high - or_low
            if or_size > 0:
                if c[t] > or_high:
                    entry_px = float(c[t])
                    stop_px = or_low
                    target_px = or_high + target_mult * or_size
                    stop_pts = entry_px - stop_px
                    if stop_pts > 0:
                        size = dynamic_size(stop_pts)
                        active = {"side": "LONG", "size": size, "entry": entry_px,
                                  "stop": stop_px, "target": target_px,
                                  "entry_bar": t}
                        if max_one_per_session:
                            session_used = True
                elif c[t] < or_low:
                    entry_px = float(c[t])
                    stop_px = or_high
                    target_px = or_low - target_mult * or_size
                    stop_pts = stop_px - entry_px
                    if stop_pts > 0:
                        size = dynamic_size(stop_pts)
                        active = {"side": "SHORT", "size": size, "entry": entry_px,
                                  "stop": stop_px, "target": target_px,
                                  "entry_bar": t}
                        if max_one_per_session:
                            session_used = True
    return trades


def stats(trades, months, starting_eq=STARTING_BALANCE):
    if not trades: return {"n": 0}
    tdf = pd.DataFrame(trades)
    n = len(tdf)
    wins = int((tdf["pnl_usd"] > 0).sum())
    gw = float(tdf[tdf["pnl_usd"] > 0]["pnl_usd"].sum())
    gl = float(abs(tdf[tdf["pnl_usd"] < 0]["pnl_usd"].sum()))
    streak = max_streak = 0
    for _, row in tdf.iterrows():
        if row["pnl_usd"] < 0:
            streak += 1
            if streak > max_streak: max_streak = streak
        else: streak = 0
    total = float(tdf["pnl_usd"].sum())
    # equity drawdown
    cum = tdf["pnl_usd"].cumsum().to_numpy()
    maxdd = float((cum - np.maximum.accumulate(cum)).min())
    avg_w = float(tdf[tdf["pnl_usd"] > 0]["pnl_usd"].mean()) if wins > 0 else 0
    avg_l = float(tdf[tdf["pnl_usd"] < 0]["pnl_usd"].mean()) if wins < n else 0
    return {"n": n, "wr": wins / n,
            "pf": gw/gl if gl > 0 else float("inf"),
            "total": total, "per": total/n,
            "trades_per_mo": n/months,
            "eq_maxdd": maxdd, "max_streak": max_streak,
            "ret_per_mo": total/starting_eq*100/months,
            "rr": abs(avg_w/avg_l) if avg_l != 0 else 0}


def main():
    print("Loading NQ 1-min data...")
    nq = pd.read_csv(DATA_FILE, parse_dates=["ts"]).set_index("ts").sort_index()
    if nq.index.tz is None:
        nq.index = nq.index.tz_localize("UTC")
    months = (nq.index[-1] - nq.index[0]).days / 30.44
    ny_idx = nq.index.tz_convert("America/New_York")
    ny_min = (ny_idx.hour * 60 + ny_idx.minute).to_numpy()
    dates = ny_idx.date
    arr = nq[["open","high","low","close"]].to_numpy()

    or_durations = [10, 15, 30, 60]
    target_mults = [0.5, 1.0, 1.5, 2.0]

    print("\n" + "=" * 100)
    print("PART 1 — INDIVIDUAL SESSION ORB RESULTS")
    print("=" * 100)
    print(f"{'Session':<8} {'OR-min':>6} {'TgtMult':>8} {'Trades':>7} {'/mo':>5} "
          f"{'WR':>6} {'PF':>5} {'RR':>5} {'$/tr':>7} {'Total':>9} {'DD':>8} {'Ret/mo':>8}")
    print("-" * 100)

    session_best = {}   # session_name -> best config
    for sess_name, sess_start, sess_end in SESSIONS:
        best_local = None
        for or_d in or_durations:
            for tm in target_mults:
                trades = find_session_orb(arr, ny_min, dates, sess_name,
                                          sess_start, sess_end, or_d, tm)
                s = stats(trades, months)
                if s["n"] < 50: continue
                pf = f"{s['pf']:.2f}" if s['pf'] < 99 else "inf"
                tag = ""
                if s["wr"] >= 0.55 and s["rr"] >= 1.2 and s["ret_per_mo"] >= 0.5:
                    tag = " ★★"
                elif s["wr"] >= 0.55 and s["ret_per_mo"] >= 0.5:
                    tag = " ★"
                elif s["total"] > 0:
                    tag = " +"
                print(f"{sess_name:<8} {or_d:>5}m {tm:>7.1f}x {s['n']:>7} "
                      f"{s['trades_per_mo']:>4.1f} {s['wr']*100:>5.1f}% {pf:>5} "
                      f"{s['rr']:>4.2f} ${s['per']:>+5,.0f} ${s['total']:>+7,.0f} "
                      f"${s['eq_maxdd']:>+6,.0f} {s['ret_per_mo']:>+6.2f}%{tag}")
                # track best for this session
                if best_local is None or s["ret_per_mo"] > best_local["ret_per_mo"]:
                    best_local = {**s, "trades": trades, "or_d": or_d, "tm": tm}
        session_best[sess_name] = best_local

    # ENSEMBLE: combine best config from each session
    print("\n" + "=" * 100)
    print("PART 2 — BEST CONFIG PER SESSION (potential ensemble)")
    print("=" * 100)
    all_ensemble_trades = []
    for sess_name, best in session_best.items():
        if best is None:
            print(f"  {sess_name}: NO PROFITABLE CONFIG")
            continue
        print(f"  {sess_name}: OR={best['or_d']}m tgt={best['tm']:.1f}x  "
              f"n={best['n']} WR={best['wr']*100:.1f}% PF={best['pf']:.2f} "
              f"RR={best['rr']:.2f} ${best['per']:+.0f}/tr "
              f"DD${best['eq_maxdd']:+,.0f} → {best['ret_per_mo']:+.2f}%/mo")
        all_ensemble_trades.extend(best["trades"])

    # combined stats
    if all_ensemble_trades:
        # sort by entry bar
        all_ensemble_trades.sort(key=lambda x: x["entry_bar"])
        s = stats(all_ensemble_trades, months)
        print("\n" + "=" * 100)
        print("ENSEMBLE: ALL SESSIONS COMBINED")
        print("=" * 100)
        pf = f"{s['pf']:.2f}" if s['pf'] < 99 else "inf"
        tag = ""
        if s["wr"] >= 0.55 and s["rr"] >= 1.2 and s["ret_per_mo"] >= 3.0:
            tag = " ★★★★ HITS USER SPEC"
        elif s["ret_per_mo"] >= 2:
            tag = " ★★"
        elif s["ret_per_mo"] >= 1:
            tag = " ★"
        print(f"  Total trades:  {s['n']} ({s['trades_per_mo']:.1f}/mo, "
              f"{s['n']/months/30:.2f}/day)")
        print(f"  Win rate:      {s['wr']*100:.1f}%")
        print(f"  Profit factor: {pf}")
        print(f"  RR (actual):   {s['rr']:.2f}")
        print(f"  Per trade:     ${s['per']:+.2f}")
        print(f"  Total P&L:     ${s['total']:+,.0f}")
        print(f"  Max DD:        ${s['eq_maxdd']:+,.0f}")
        print(f"  Max streak:    {s['max_streak']}")
        print(f"  RETURN/MO:     {s['ret_per_mo']:+.2f}%{tag}")


if __name__ == "__main__":
    main()
