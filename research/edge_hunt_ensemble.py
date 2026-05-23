"""Hunt for non-correlated edges to stack with ORB ensemble.

A. LUNCH-HOUR MEAN REVERSION (11:00-13:00 ET)
   - Detect range during 11:00-12:30
   - Fade extremes of that range during 12:30-13:00
   - Tight stops, mean (range midpoint) as target

B. END-OF-DAY MOMENTUM (15:30-16:00 ET)
   - Compute drift direction from 14:00-15:30 (last 90 min)
   - At 15:30, enter in direction of drift
   - Hold to close (16:00)

C. ORB ON OTHER INSTRUMENTS (ES, YM, RTY)
   - Same ORB strategy, different market

D. PULLBACK RE-ENTRY ON ORB
   - After ORB breakout, wait for pullback to OR level
   - Enter on pullback for higher WR
"""
from __future__ import annotations
import numpy as np, pandas as pd
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "polygon"

STARTING_BALANCE     = 50_000.0
MNQ_PER_PT           = 2.0
COMM_PER_CONTRACT_RT = 2.0
TARGET_RISK_USD      = 150.0
MAX_CONTRACTS        = 5


def dynamic_size(stop_pts):
    if stop_pts <= 0: return 1
    return max(1, min(MAX_CONTRACTS, int(TARGET_RISK_USD / (stop_pts * MNQ_PER_PT))))


def load_5min(symbol):
    df = pd.read_csv(DATA / f"{symbol}_5min.csv", parse_dates=["ts"]).set_index("ts").sort_index()
    if df.index.tz is None: df.index = df.index.tz_localize("UTC")
    return df


def load_1min():
    df = pd.read_csv(DATA / "NQ_1min.csv", parse_dates=["ts"]).set_index("ts").sort_index()
    if df.index.tz is None: df.index = df.index.tz_localize("UTC")
    return df


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
    cum = tdf["pnl_usd"].cumsum().to_numpy()
    maxdd = float((cum - np.maximum.accumulate(cum)).min())
    avg_w = float(tdf[tdf["pnl_usd"] > 0]["pnl_usd"].mean()) if wins > 0 else 0
    avg_l = float(tdf[tdf["pnl_usd"] < 0]["pnl_usd"].mean()) if wins < n else 0
    return {"n": n, "wr": wins / n, "pf": gw/gl if gl > 0 else float("inf"),
            "total": total, "per": total/n, "trades_per_mo": n/months,
            "eq_maxdd": maxdd, "max_streak": max_streak,
            "ret_per_mo": total/starting_eq*100/months,
            "rr": abs(avg_w/avg_l) if avg_l != 0 else 0}


# ============================================================================
# A. LUNCH HOUR MEAN REVERSION
# ============================================================================
def run_lunch_fade(arr, ny_min, dates,
                   range_start: int = 11 * 60 + 0,
                   range_end: int = 12 * 60 + 30,
                   trade_start: int = 12 * 60 + 30,
                   trade_end: int = 13 * 60 + 0,
                   buffer_pts: float = 1.0):
    """Fade extremes of 11:00-12:30 range during 12:30-13:00.
    Target: range midpoint. Stop: outside the range edge.
    """
    o = arr[:, 0]; h = arr[:, 1]; l = arr[:, 2]; c = arr[:, 3]
    n = len(arr)
    trades = []
    active = None
    current_date = None
    rng_high = rng_low = None
    rng_done = False
    session_used = False

    for t in range(n):
        d = dates[t]
        nm = int(ny_min[t])
        if d != current_date:
            current_date = d
            rng_high = rng_low = None
            rng_done = False
            session_used = False

        # build range
        if range_start <= nm < range_end:
            if rng_high is None:
                rng_high = float(h[t]); rng_low = float(l[t])
            else:
                rng_high = max(rng_high, float(h[t]))
                rng_low  = min(rng_low,  float(l[t]))
        elif nm == range_end:
            rng_done = True

        # manage active trade
        if active is not None:
            stop_hit = (active["side"] == "LONG" and l[t] <= active["stop"]) or \
                       (active["side"] == "SHORT" and h[t] >= active["stop"])
            tgt_hit  = (active["side"] == "LONG" and h[t] >= active["target"]) or \
                       (active["side"] == "SHORT" and l[t] <= active["target"])
            exit_now = False
            exit_px = None; reason = ""
            if stop_hit: exit_px = active["stop"]; reason = "stop"; exit_now = True
            elif tgt_hit: exit_px = active["target"]; reason = "target"; exit_now = True
            elif nm >= trade_end:
                exit_px = float(c[t]); reason = "session_end"; exit_now = True
            if exit_now:
                pnl_pts = (active["entry"] - exit_px) if active["side"] == "SHORT" \
                          else (exit_px - active["entry"])
                pnl = pnl_pts * active["size"] * MNQ_PER_PT - COMM_PER_CONTRACT_RT * active["size"]
                trades.append({"side": active["side"], "size": active["size"],
                               "pnl_usd": float(pnl), "exit_reason": reason})
                active = None

        # entry signal during trade window
        if (active is None and rng_done and not session_used and rng_high is not None
                and trade_start <= nm < trade_end):
            mid = (rng_high + rng_low) / 2
            # SHORT at range high touch
            if h[t] >= rng_high:
                entry_px = float(rng_high)
                stop_px = entry_px + buffer_pts
                target_px = mid
                stop_pts = stop_px - entry_px
                if stop_pts > 0:
                    size = dynamic_size(stop_pts)
                    active = {"side": "SHORT", "size": size, "entry": entry_px,
                              "stop": stop_px, "target": target_px}
                    session_used = True
            elif l[t] <= rng_low:
                entry_px = float(rng_low)
                stop_px = entry_px - buffer_pts
                target_px = mid
                stop_pts = entry_px - stop_px
                if stop_pts > 0:
                    size = dynamic_size(stop_pts)
                    active = {"side": "LONG", "size": size, "entry": entry_px,
                              "stop": stop_px, "target": target_px}
                    session_used = True

    return trades


# ============================================================================
# B. END-OF-DAY DRIFT (15:30 - 16:00)
# ============================================================================
def run_eod_drift(arr, ny_min, dates,
                  lookback_start: int = 14 * 60 + 0,
                  trade_time: int = 15 * 60 + 30,
                  exit_time: int = 15 * 60 + 55,
                  stop_pts: float = 8.0):
    """At 15:30, compute drift (close vs close at 14:00). Trade in drift dir.
    Hold to 15:55, exit at close.
    """
    o = arr[:, 0]; h = arr[:, 1]; l = arr[:, 2]; c = arr[:, 3]
    n = len(arr)
    trades = []
    active = None
    current_date = None
    lookback_close = None

    for t in range(n):
        d = dates[t]
        nm = int(ny_min[t])
        if d != current_date:
            current_date = d
            lookback_close = None

        # store close at 14:00 for lookback comparison
        if nm == lookback_start and lookback_close is None:
            lookback_close = float(c[t])

        # manage active trade
        if active is not None:
            stop_hit = (active["side"] == "LONG" and l[t] <= active["stop"]) or \
                       (active["side"] == "SHORT" and h[t] >= active["stop"])
            exit_px = None; reason = ""
            if stop_hit: exit_px = active["stop"]; reason = "stop"
            elif nm >= exit_time: exit_px = float(c[t]); reason = "session_end"
            if exit_px is not None:
                pnl_pts = (active["entry"] - exit_px) if active["side"] == "SHORT" \
                          else (exit_px - active["entry"])
                pnl = pnl_pts * active["size"] * MNQ_PER_PT - COMM_PER_CONTRACT_RT * active["size"]
                trades.append({"side": active["side"], "size": active["size"],
                               "pnl_usd": float(pnl), "exit_reason": reason})
                active = None

        # entry at trade_time
        if active is None and nm == trade_time and lookback_close is not None:
            current_close = float(c[t])
            drift = current_close - lookback_close
            min_drift_pts = 5.0   # only trade if drift > 5 NQ pts
            if abs(drift) >= min_drift_pts:
                size = dynamic_size(stop_pts)
                if drift > 0:  # LONG (drift up, ride into close)
                    active = {"side": "LONG", "size": size, "entry": current_close,
                              "stop": current_close - stop_pts, "target": 0}
                else:
                    active = {"side": "SHORT", "size": size, "entry": current_close,
                              "stop": current_close + stop_pts, "target": 0}

    return trades


# ============================================================================
# C. ORB on different instruments
# ============================================================================
def run_orb_general(arr, ny_min, dates, instr_pt_value: float,
                    contracts: int,
                    sess_start: int, sess_end: int,
                    or_minutes: int, target_mult: float):
    o = arr[:, 0]; h = arr[:, 1]; l = arr[:, 2]; c = arr[:, 3]
    n = len(arr)
    trades = []
    active = None
    current_date = None
    or_high = or_low = None
    or_done = False
    used = False

    for t in range(n):
        d = dates[t]
        nm = int(ny_min[t])
        if d != current_date:
            current_date = d
            or_high = or_low = None
            or_done = False
            used = False

        if sess_start <= nm < sess_start + or_minutes:
            if or_high is None: or_high = float(h[t]); or_low = float(l[t])
            else: or_high = max(or_high, float(h[t])); or_low = min(or_low, float(l[t]))
        elif nm == sess_start + or_minutes:
            or_done = True

        if active is not None:
            stop_hit = (active["side"] == "LONG" and l[t] <= active["stop"]) or \
                       (active["side"] == "SHORT" and h[t] >= active["stop"])
            tgt_hit  = (active["side"] == "LONG" and h[t] >= active["target"]) or \
                       (active["side"] == "SHORT" and l[t] <= active["target"])
            exit_px = None; reason = ""
            if stop_hit: exit_px = active["stop"]; reason = "stop"
            elif tgt_hit: exit_px = active["target"]; reason = "target"
            elif nm >= sess_end: exit_px = float(c[t]); reason = "session_end"
            if exit_px is not None:
                pnl_pts = (active["entry"] - exit_px) if active["side"] == "SHORT" \
                          else (exit_px - active["entry"])
                pnl = pnl_pts * contracts * instr_pt_value - COMM_PER_CONTRACT_RT * contracts
                trades.append({"side": active["side"], "size": contracts,
                               "pnl_usd": float(pnl), "exit_reason": reason})
                active = None

        if (active is None and or_done and not used and or_high is not None
                and sess_start + or_minutes <= nm < sess_end):
            or_size = or_high - or_low
            if or_size > 0:
                if c[t] > or_high:
                    entry_px = float(c[t])
                    stop_px = or_low
                    target_px = or_high + target_mult * or_size
                    stop_pts = entry_px - stop_px
                    if stop_pts > 0:
                        active = {"side": "LONG", "entry": entry_px,
                                  "stop": stop_px, "target": target_px}
                        used = True
                elif c[t] < or_low:
                    entry_px = float(c[t])
                    stop_px = or_high
                    target_px = or_low - target_mult * or_size
                    stop_pts = stop_px - entry_px
                    if stop_pts > 0:
                        active = {"side": "SHORT", "entry": entry_px,
                                  "stop": stop_px, "target": target_px}
                        used = True
    return trades


def main():
    print("=" * 100)
    print("HUNT FOR NON-CORRELATED EDGES")
    print("=" * 100)

    # --- LUNCH FADE on NQ 1-min ---
    nq1 = load_1min()
    months = (nq1.index[-1] - nq1.index[0]).days / 30.44
    ny_idx = nq1.index.tz_convert("America/New_York")
    ny_min_1 = (ny_idx.hour * 60 + ny_idx.minute).to_numpy()
    dates_1 = ny_idx.date
    arr1 = nq1[["open","high","low","close"]].to_numpy()

    print("\nA. LUNCH HOUR MEAN REVERSION (NQ 1-min)")
    print("-" * 100)
    print(f"{'RangeStart':>11} {'RangeEnd':>9} {'TradeEnd':>9} {'Buffer':>7} "
          f"{'Trades':>7} {'/mo':>5} {'WR':>6} {'PF':>5} {'RR':>5} "
          f"{'$/tr':>7} {'Total':>9} {'DD':>8} {'Ret/mo':>8}")
    lunch_best = None
    for rs in [10*60+30, 11*60+0, 11*60+30]:
        for re_ in [12*60+0, 12*60+30, 13*60+0]:
            if re_ <= rs: continue
            for te in [12*60+30, 13*60+0, 13*60+30]:
                if te <= re_: continue
                for buf in [1.0, 2.0, 3.0]:
                    trades = run_lunch_fade(arr1, ny_min_1, dates_1, rs, re_, re_, te, buf)
                    s = stats(trades, months)
                    if s["n"] < 30: continue
                    pf = f"{s['pf']:.2f}" if s['pf'] < 99 else "inf"
                    tag = ""
                    if s["wr"] >= 0.55 and s["ret_per_mo"] >= 0.5: tag = " ★★"
                    elif s["ret_per_mo"] >= 0.3: tag = " ★"
                    elif s["total"] > 0: tag = " +"
                    print(f"{rs//60}:{rs%60:02d} →   {re_//60}:{re_%60:02d}  "
                          f"{te//60}:{te%60:02d}  {buf:>6.1f}p  "
                          f"{s['n']:>7} {s['trades_per_mo']:>4.1f} "
                          f"{s['wr']*100:>5.1f}% {pf:>5} {s['rr']:>4.2f} "
                          f"${s['per']:>+5,.0f} ${s['total']:>+7,.0f} "
                          f"${s['eq_maxdd']:>+6,.0f} {s['ret_per_mo']:>+6.2f}%{tag}")
                    if lunch_best is None or s["ret_per_mo"] > lunch_best["ret_per_mo"]:
                        lunch_best = {**s, "trades": trades, "config": (rs, re_, te, buf)}

    # --- END-OF-DAY DRIFT ---
    print("\n\nB. END-OF-DAY DRIFT (NQ 1-min)")
    print("-" * 100)
    print(f"{'Lookback':>9} {'TradeT':>7} {'ExitT':>7} {'StopPts':>8} "
          f"{'Trades':>7} {'/mo':>5} {'WR':>6} {'PF':>5} {'RR':>5} "
          f"{'$/tr':>7} {'Total':>9} {'DD':>8} {'Ret/mo':>8}")
    eod_best = None
    for lb in [13*60+0, 13*60+30, 14*60+0, 14*60+30]:
        for tt in [15*60+0, 15*60+15, 15*60+30, 15*60+45]:
            if tt <= lb: continue
            for et in [15*60+45, 15*60+55]:
                if et <= tt: continue
                for sp in [5.0, 8.0, 12.0, 20.0]:
                    trades = run_eod_drift(arr1, ny_min_1, dates_1, lb, tt, et, sp)
                    s = stats(trades, months)
                    if s["n"] < 30: continue
                    pf = f"{s['pf']:.2f}" if s['pf'] < 99 else "inf"
                    tag = ""
                    if s["wr"] >= 0.55 and s["ret_per_mo"] >= 0.5: tag = " ★★"
                    elif s["ret_per_mo"] >= 0.3: tag = " ★"
                    elif s["total"] > 0: tag = " +"
                    print(f"{lb//60}:{lb%60:02d}    {tt//60}:{tt%60:02d}  "
                          f"{et//60}:{et%60:02d}  {sp:>7.0f}p "
                          f"{s['n']:>7} {s['trades_per_mo']:>4.1f} "
                          f"{s['wr']*100:>5.1f}% {pf:>5} {s['rr']:>4.2f} "
                          f"${s['per']:>+5,.0f} ${s['total']:>+7,.0f} "
                          f"${s['eq_maxdd']:>+6,.0f} {s['ret_per_mo']:>+6.2f}%{tag}")
                    if eod_best is None or s["ret_per_mo"] > eod_best["ret_per_mo"]:
                        eod_best = {**s, "trades": trades, "config": (lb, tt, et, sp)}

    # --- ORB on ES, YM, RTY ---
    print("\n\nC. ORB ON OTHER INSTRUMENTS (NY AM, 30min OR, 1.0x target)")
    print("-" * 100)
    instruments = [
        ("ES",  5.0, 1),    # MES = $5/pt, 1 contract
        ("YM",  0.5, 2),    # MYM = $0.50/pt, 2 contracts for similar $ exposure
        ("RTY", 5.0, 1),    # M2K = $5/pt? actually $10/pt, use 1
    ]
    print(f"{'Instr':<7} {'Trades':>7} {'/mo':>5} {'WR':>6} {'PF':>5} {'RR':>5} "
          f"{'$/tr':>7} {'Total':>9} {'DD':>8} {'Ret/mo':>8}")
    instrument_results = {}
    for sym, pt_val, contracts in instruments:
        try:
            df = load_5min(sym)
        except FileNotFoundError:
            continue
        ny = df.index.tz_convert("America/New_York")
        nm = (ny.hour * 60 + ny.minute).to_numpy()
        dat = ny.date
        arr = df[["open","high","low","close"]].to_numpy()
        # NY AM 30min OR, 1.0x target
        trades = run_orb_general(arr, nm, dat, pt_val, contracts,
                                  9*60+30, 16*60, 30, 1.0)
        s = stats(trades, months)
        if s["n"] >= 30:
            pf = f"{s['pf']:.2f}" if s['pf'] < 99 else "inf"
            tag = ""
            if s["ret_per_mo"] >= 0.5: tag = " ★"
            elif s["total"] > 0: tag = " +"
            print(f"{sym:<7} {s['n']:>7} {s['trades_per_mo']:>4.1f} "
                  f"{s['wr']*100:>5.1f}% {pf:>5} {s['rr']:>4.2f} "
                  f"${s['per']:>+5,.0f} ${s['total']:>+7,.0f} "
                  f"${s['eq_maxdd']:>+6,.0f} {s['ret_per_mo']:>+6.2f}%{tag}")
            instrument_results[sym] = {**s, "trades": trades}

    print("\n\n" + "=" * 100)
    print("BEST CONFIGS FROM EACH NEW STRATEGY")
    print("=" * 100)
    if lunch_best:
        rs, re_, te, buf = lunch_best["config"]
        print(f"Lunch fade: {rs//60}:{rs%60:02d}-{re_//60}:{re_%60:02d} range, "
              f"trade until {te//60}:{te%60:02d}, buf {buf:.1f}p")
        print(f"  n={lunch_best['n']} WR={lunch_best['wr']*100:.1f}% "
              f"PF={lunch_best['pf']:.2f} ${lunch_best['per']:+.0f}/tr "
              f"DD${lunch_best['eq_maxdd']:+,.0f} → {lunch_best['ret_per_mo']:+.2f}%/mo")
    if eod_best:
        lb, tt, et, sp = eod_best["config"]
        print(f"EOD drift: lookback {lb//60}:{lb%60:02d}, enter {tt//60}:{tt%60:02d}, "
              f"exit {et//60}:{et%60:02d}, stop {sp:.0f}p")
        print(f"  n={eod_best['n']} WR={eod_best['wr']*100:.1f}% "
              f"PF={eod_best['pf']:.2f} ${eod_best['per']:+.0f}/tr "
              f"DD${eod_best['eq_maxdd']:+,.0f} → {eod_best['ret_per_mo']:+.2f}%/mo")


if __name__ == "__main__":
    main()
