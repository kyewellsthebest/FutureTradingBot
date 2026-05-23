"""Comprehensive alpha hunt: ORB, Bollinger fade, VWAP fade, z-score reversion.

Tests four well-documented strategies that have published edge in
academic literature, on NQ 1-min data 2024-2026.

A. ORB (Opening Range Breakout)
   - Use first X minutes of NY session (9:30-09:30+X) to define range
   - After range complete, trade breakouts in either direction
   - Stop: opposite side of OR
   - Target: M x OR width

B. Bollinger Band Mean Reversion
   - 20-bar BB with 2 std dev
   - Touch upper → SHORT; touch lower → LONG
   - Target: middle band (SMA20)
   - Stop: outside BB by buffer

C. VWAP Mean Reversion
   - Anchored VWAP from session start
   - Compute std dev of price - VWAP
   - When |price - VWAP| > X std → fade toward VWAP

D. RSI Extreme Fade
   - RSI(14)
   - >80 → SHORT, <20 → LONG
   - Hold until RSI returns to 50

E. Lunch Hour Mean Reversion (NY 11:00-13:00 ET)
   - During lunch, range-bound behavior
   - Buy lows, sell highs of 30-min rolling range
"""
from __future__ import annotations
import numpy as np, pandas as pd
from pathlib import Path
from dataclasses import dataclass

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "polygon" / "NQ_1min.csv"

STARTING_BALANCE     = 50_000.0
MNQ_PER_PT           = 2.0
COMM_PER_CONTRACT_RT = 2.0
TARGET_RISK_USD      = 150.0
MAX_CONTRACTS        = 5


def dynamic_size(stop_pts: float) -> int:
    if stop_pts <= 0: return 1
    return max(1, min(MAX_CONTRACTS, int(TARGET_RISK_USD / (stop_pts * MNQ_PER_PT))))


def resample(nq, freq):
    if freq == "1min": return nq
    return nq.resample(freq).agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna()


# ============================================================================
# Strategy A: Opening Range Breakout
# ============================================================================
def run_orb(arr: np.ndarray, idx, ny_min: np.ndarray, dates,
            or_minutes: int = 30,
            target_mult: float = 1.5,
            bar_minutes: int = 1) -> dict:
    """ORB: define range from 9:30 to 9:30+or_minutes. After range,
    trade breakouts in either direction.
    """
    o = arr[:, 0]; h = arr[:, 1]; l = arr[:, 2]; c = arr[:, 3]
    n = len(arr)
    or_bars = or_minutes // bar_minutes

    trades = []
    active = None
    equity = STARTING_BALANCE
    equity_curve = np.zeros(n)
    current_date = None
    or_high = or_low = None
    or_complete = False
    or_used = False

    for t in range(n):
        # reset on new day
        d = dates[t]
        if d != current_date:
            current_date = d
            or_high = or_low = None
            or_complete = False
            or_used = False
            # close active trade at session end (15:55 ET)
            if active is not None:
                exit_px = float(c[t])
                pnl_pts = (active["entry"] - exit_px) if active["side"] == "SHORT" \
                          else (exit_px - active["entry"])
                pnl = pnl_pts * active["size"] * MNQ_PER_PT - COMM_PER_CONTRACT_RT * active["size"]
                equity += pnl
                trades.append({"side": active["side"], "size": active["size"],
                               "pnl_usd": float(pnl), "exit_reason": "session_end"})
                active = None

        # build opening range during first or_minutes of NY session
        minute = int(ny_min[t])
        if 9*60+30 <= minute < 9*60+30+or_minutes:
            if or_high is None:
                or_high = float(h[t]); or_low = float(l[t])
            else:
                or_high = max(or_high, float(h[t]))
                or_low  = min(or_low,  float(l[t]))
        elif minute == 9*60+30+or_minutes:
            or_complete = True

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
            if exit_px is not None:
                pnl_pts = (active["entry"] - exit_px) if active["side"] == "SHORT" \
                          else (exit_px - active["entry"])
                pnl = pnl_pts * active["size"] * MNQ_PER_PT - COMM_PER_CONTRACT_RT * active["size"]
                equity += pnl
                trades.append({"side": active["side"], "size": active["size"],
                               "pnl_usd": float(pnl), "exit_reason": reason})
                active = None

        # entry signals (only after OR complete, only once per day)
        if (active is None and or_complete and not or_used and or_high is not None
                and 9*60+30+or_minutes <= minute < 15*60+55):
            or_size = or_high - or_low
            if or_size > 0:
                if c[t] > or_high:  # bullish breakout
                    entry_px = float(c[t])
                    stop_px = or_low
                    target_px = or_high + target_mult * or_size
                    stop_pts = entry_px - stop_px
                    if stop_pts > 0:
                        size = dynamic_size(stop_pts)
                        active = {"side": "LONG", "size": size, "entry": entry_px,
                                  "stop": stop_px, "target": target_px}
                        or_used = True
                elif c[t] < or_low:  # bearish breakout
                    entry_px = float(c[t])
                    stop_px = or_high
                    target_px = or_low - target_mult * or_size
                    stop_pts = stop_px - entry_px
                    if stop_pts > 0:
                        size = dynamic_size(stop_pts)
                        active = {"side": "SHORT", "size": size, "entry": entry_px,
                                  "stop": stop_px, "target": target_px}
                        or_used = True

        equity_curve[t] = equity

    return {"trades": trades, "equity": pd.Series(equity_curve, index=idx)}


# ============================================================================
# Strategy B: Bollinger Band Mean Reversion
# ============================================================================
def run_bollinger(arr: np.ndarray, idx,
                  period: int = 20, n_std: float = 2.0,
                  max_hold_bars: int = 30) -> dict:
    """NO-LOOK-AHEAD: band at bar t is upper[t-1] (last fully known value
    before bar t opens). Entry only checked using prior band; fill at
    that prior band level if bar t's range reaches it."""
    o = arr[:, 0]; h = arr[:, 1]; l = arr[:, 2]; c = arr[:, 3]
    n = len(arr)
    close_s = pd.Series(c)
    sma = close_s.rolling(period).mean().to_numpy()
    std = close_s.rolling(period).std().to_numpy()
    # SHIFT by 1: the band level known at bar t open is computed using bars t-period..t-1
    upper_known = np.full(n, np.nan)
    lower_known = np.full(n, np.nan)
    sma_known = np.full(n, np.nan)
    for t in range(1, n):
        upper_known[t] = sma[t - 1] + n_std * std[t - 1]
        lower_known[t] = sma[t - 1] - n_std * std[t - 1]
        sma_known[t]   = sma[t - 1]

    trades = []
    active = None
    equity = STARTING_BALANCE
    equity_curve = np.zeros(n)

    for t in range(n):
        if active is not None:
            stop_hit = (active["side"] == "LONG" and l[t] <= active["stop"]) or \
                       (active["side"] == "SHORT" and h[t] >= active["stop"])
            # exit at SMA touch (the SMA at bar t-1 is fully known at bar t open)
            target = sma_known[t]
            mid_touched = False
            if not np.isnan(target):
                mid_touched = (active["side"] == "LONG" and h[t] >= target) or \
                              (active["side"] == "SHORT" and l[t] <= target)
            exit_px = None; reason = ""
            if stop_hit and mid_touched:
                exit_px = active["stop"]; reason = "stop"
            elif stop_hit: exit_px = active["stop"]; reason = "stop"
            elif mid_touched: exit_px = target; reason = "target"
            elif t - active["entry_bar"] >= max_hold_bars:
                exit_px = float(c[t]); reason = "timeout"
            if exit_px is not None:
                pnl_pts = (active["entry"] - exit_px) if active["side"] == "SHORT" \
                          else (exit_px - active["entry"])
                pnl = pnl_pts * active["size"] * MNQ_PER_PT - COMM_PER_CONTRACT_RT * active["size"]
                equity += pnl
                trades.append({"side": active["side"], "size": active["size"],
                               "pnl_usd": float(pnl), "exit_reason": reason})
                active = None

        if active is None and t > period and not np.isnan(upper_known[t]):
            ub = upper_known[t]; lb = lower_known[t]; mid = sma_known[t]
            std_t = std[t - 1]
            # SHORT at upper band touch — limit fills if bar t's high reaches ub
            if h[t] >= ub and ub > mid:
                entry_px = float(ub)
                stop_px = entry_px + std_t * 0.5
                target_px = mid
                stop_pts = stop_px - entry_px
                if stop_pts > 0 and entry_px - target_px > 0:
                    size = dynamic_size(stop_pts)
                    active = {"entry_bar": t, "side": "SHORT", "size": size,
                              "entry": entry_px, "stop": stop_px, "target": target_px}
            elif l[t] <= lb and lb < mid:
                entry_px = float(lb)
                stop_px = entry_px - std_t * 0.5
                target_px = mid
                stop_pts = entry_px - stop_px
                if stop_pts > 0 and target_px - entry_px > 0:
                    size = dynamic_size(stop_pts)
                    active = {"entry_bar": t, "side": "LONG", "size": size,
                              "entry": entry_px, "stop": stop_px, "target": target_px}

        equity_curve[t] = equity

    return {"trades": trades, "equity": pd.Series(equity_curve, index=idx)}


# ============================================================================
# Strategy C: VWAP fade
# ============================================================================
def run_vwap_fade(arr: np.ndarray, vol: np.ndarray, idx, ny_min, dates,
                  n_std: float = 2.0, max_hold_bars: int = 30) -> dict:
    o = arr[:, 0]; h = arr[:, 1]; l = arr[:, 2]; c = arr[:, 3]
    n = len(arr)
    trades = []
    active = None
    equity = STARTING_BALANCE
    equity_curve = np.zeros(n)
    current_date = None
    cum_pv = 0.0; cum_v = 0.0
    px_list: list[float] = []
    vwap_list: list[float] = []

    for t in range(n):
        d = dates[t]
        if d != current_date:
            current_date = d
            cum_pv = 0.0; cum_v = 0.0
            px_list = []
            vwap_list = []
        typical = (h[t] + l[t] + c[t]) / 3.0
        cum_pv += typical * vol[t]
        cum_v += vol[t]
        vwap = cum_pv / cum_v if cum_v > 0 else float(c[t])
        px_list.append(float(c[t]))
        vwap_list.append(vwap)
        # rolling std of (close - vwap)
        if len(px_list) >= 20:
            recent_dev = np.array(px_list[-20:]) - np.array(vwap_list[-20:])
            dev_std = float(recent_dev.std())
        else:
            dev_std = None

        if active is not None:
            stop_hit = (active["side"] == "LONG" and l[t] <= active["stop"]) or \
                       (active["side"] == "SHORT" and h[t] >= active["stop"])
            # exit when price crosses VWAP
            vwap_touched = (active["side"] == "LONG" and h[t] >= vwap) or \
                           (active["side"] == "SHORT" and l[t] <= vwap)
            exit_px = None; reason = ""
            if stop_hit: exit_px = active["stop"]; reason = "stop"
            elif vwap_touched: exit_px = vwap; reason = "target"
            elif t - active["entry_bar"] >= max_hold_bars:
                exit_px = float(c[t]); reason = "timeout"
            if exit_px is not None:
                pnl_pts = (active["entry"] - exit_px) if active["side"] == "SHORT" \
                          else (exit_px - active["entry"])
                pnl = pnl_pts * active["size"] * MNQ_PER_PT - COMM_PER_CONTRACT_RT * active["size"]
                equity += pnl
                trades.append({"side": active["side"], "size": active["size"],
                               "pnl_usd": float(pnl), "exit_reason": reason})
                active = None

        if active is None and dev_std is not None and dev_std > 0:
            dev = c[t] - vwap
            if dev > n_std * dev_std:  # too far above VWAP — SHORT
                entry_px = float(c[t])
                stop_px = entry_px + dev_std
                target_px = vwap
                stop_pts = stop_px - entry_px
                if stop_pts > 0 and entry_px - target_px > 0:
                    size = dynamic_size(stop_pts)
                    active = {"entry_bar": t, "side": "SHORT", "size": size,
                              "entry": entry_px, "stop": stop_px, "target": target_px}
            elif dev < -n_std * dev_std:
                entry_px = float(c[t])
                stop_px = entry_px - dev_std
                target_px = vwap
                stop_pts = entry_px - stop_px
                if stop_pts > 0 and target_px - entry_px > 0:
                    size = dynamic_size(stop_pts)
                    active = {"entry_bar": t, "side": "LONG", "size": size,
                              "entry": entry_px, "stop": stop_px, "target": target_px}

        equity_curve[t] = equity

    return {"trades": trades, "equity": pd.Series(equity_curve, index=idx)}


# ============================================================================
# Strategy D: RSI extreme fade
# ============================================================================
def run_rsi_fade(arr: np.ndarray, idx,
                 rsi_period: int = 14,
                 upper_rsi: float = 80.0, lower_rsi: float = 20.0,
                 max_hold_bars: int = 30) -> dict:
    o = arr[:, 0]; h = arr[:, 1]; l = arr[:, 2]; c = arr[:, 3]
    n = len(arr)
    close_s = pd.Series(c)
    diff = close_s.diff()
    gain = diff.where(diff > 0, 0)
    loss = -diff.where(diff < 0, 0)
    avg_gain = gain.ewm(alpha=1/rsi_period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/rsi_period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    rsi = (100 - (100 / (1 + rs))).to_numpy()

    trades = []
    active = None
    equity = STARTING_BALANCE
    equity_curve = np.zeros(n)

    for t in range(n):
        if active is not None:
            stop_hit = (active["side"] == "LONG" and l[t] <= active["stop"]) or \
                       (active["side"] == "SHORT" and h[t] >= active["stop"])
            # exit when RSI returns past 50
            rsi_back = (active["side"] == "SHORT" and rsi[t] < 50) or \
                       (active["side"] == "LONG" and rsi[t] > 50)
            exit_px = None; reason = ""
            if stop_hit: exit_px = active["stop"]; reason = "stop"
            elif rsi_back: exit_px = float(c[t]); reason = "target"
            elif t - active["entry_bar"] >= max_hold_bars:
                exit_px = float(c[t]); reason = "timeout"
            if exit_px is not None:
                pnl_pts = (active["entry"] - exit_px) if active["side"] == "SHORT" \
                          else (exit_px - active["entry"])
                pnl = pnl_pts * active["size"] * MNQ_PER_PT - COMM_PER_CONTRACT_RT * active["size"]
                equity += pnl
                trades.append({"side": active["side"], "size": active["size"],
                               "pnl_usd": float(pnl), "exit_reason": reason})
                active = None

        if active is None and t > rsi_period:
            if rsi[t] > upper_rsi:
                entry_px = float(c[t])
                stop_px = entry_px + 5.0  # 5pt stop
                stop_pts = 5.0
                size = dynamic_size(stop_pts)
                active = {"entry_bar": t, "side": "SHORT", "size": size,
                          "entry": entry_px, "stop": stop_px, "target": 0}  # exit on RSI return
            elif rsi[t] < lower_rsi:
                entry_px = float(c[t])
                stop_px = entry_px - 5.0
                stop_pts = 5.0
                size = dynamic_size(stop_pts)
                active = {"entry_bar": t, "side": "LONG", "size": size,
                          "entry": entry_px, "stop": stop_px, "target": 0}

        equity_curve[t] = equity

    return {"trades": trades, "equity": pd.Series(equity_curve, index=idx)}


# ============================================================================
# Reporting
# ============================================================================
def stats(trades, equity, months):
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
    eq_dd = float((equity - equity.cummax()).min())
    return {"n": n, "wr": wins / n,
            "pf": gw/gl if gl > 0 else float("inf"),
            "total": total, "per": total/n, "trades_per_mo": n/months,
            "eq_maxdd": eq_dd, "max_streak": max_streak,
            "ret_per_mo": total/STARTING_BALANCE*100/months}


def main():
    print("Loading data...")
    nq = pd.read_csv(DATA_FILE, parse_dates=["ts"]).set_index("ts").sort_index()
    if nq.index.tz is None:
        nq.index = nq.index.tz_localize("UTC")
    months = (nq.index[-1] - nq.index[0]).days / 30.44
    print(f"  bars: {len(nq):,}   months: {months:.1f}\n")

    ny_index = nq.index.tz_convert("America/New_York")
    ny_min = (ny_index.hour * 60 + ny_index.minute).to_numpy()
    dates = ny_index.date

    print("=" * 100)
    print("A. OPENING RANGE BREAKOUT (ORB) — sweep OR period and target multiple")
    print("=" * 100)
    arr1 = nq[["open","high","low","close"]].to_numpy()
    vol1 = nq["volume"].to_numpy()
    print(f"{'OR-min':>7} {'TgtMult':>8} {'Trades':>7} {'/mo':>5} {'WR':>6} "
          f"{'PF':>5} {'$/tr':>7} {'Total':>9} {'EqDD':>9} {'Ret/mo':>8}")
    for or_min in [15, 30, 60]:
        for tm in [0.5, 1.0, 1.5, 2.0]:
            res = run_orb(arr1, nq.index, ny_min, dates, or_min, tm)
            s = stats(res["trades"], res["equity"], months)
            if s["n"] == 0: continue
            pf = f"{s['pf']:.2f}" if s['pf'] < 99 else "inf"
            tag = ""
            if s["ret_per_mo"] >= 2.0 and abs(s["eq_maxdd"]) < 5000: tag = " ★★"
            elif s["ret_per_mo"] >= 0.5: tag = " ★"
            elif s["total"] > 0: tag = " +"
            print(f"{or_min:>6}m {tm:>7.1f}x {s['n']:>7} "
                  f"{s['trades_per_mo']:>4.1f} {s['wr']*100:>5.1f}% {pf:>5} "
                  f"${s['per']:>+5,.0f} ${s['total']:>+7,.0f} "
                  f"${s['eq_maxdd']:>+7,.0f} {s['ret_per_mo']:>+6.2f}%{tag}")

    print("\n" + "=" * 100)
    print("B. BOLLINGER BAND MEAN REVERSION — sweep period and stddev")
    print("=" * 100)
    print(f"{'Period':>7} {'N_std':>6} {'Trades':>7} {'/mo':>5} {'WR':>6} "
          f"{'PF':>5} {'$/tr':>7} {'Total':>9} {'EqDD':>9} {'Ret/mo':>8}")
    for period in [10, 20, 50]:
        for nstd in [1.5, 2.0, 2.5]:
            res = run_bollinger(arr1, nq.index, period, nstd)
            s = stats(res["trades"], res["equity"], months)
            if s["n"] == 0: continue
            pf = f"{s['pf']:.2f}" if s['pf'] < 99 else "inf"
            tag = ""
            if s["ret_per_mo"] >= 2.0 and abs(s["eq_maxdd"]) < 5000: tag = " ★★"
            elif s["ret_per_mo"] >= 0.5: tag = " ★"
            elif s["total"] > 0: tag = " +"
            print(f"{period:>6} {nstd:>5.1f}σ {s['n']:>7} "
                  f"{s['trades_per_mo']:>4.1f} {s['wr']*100:>5.1f}% {pf:>5} "
                  f"${s['per']:>+5,.0f} ${s['total']:>+7,.0f} "
                  f"${s['eq_maxdd']:>+7,.0f} {s['ret_per_mo']:>+6.2f}%{tag}")

    print("\n" + "=" * 100)
    print("C. VWAP DEVIATION FADE — sweep n_std")
    print("=" * 100)
    print(f"{'N_std':>6} {'Trades':>7} {'/mo':>5} {'WR':>6} "
          f"{'PF':>5} {'$/tr':>7} {'Total':>9} {'EqDD':>9} {'Ret/mo':>8}")
    for nstd in [1.5, 2.0, 2.5, 3.0]:
        res = run_vwap_fade(arr1, vol1, nq.index, ny_min, dates, nstd)
        s = stats(res["trades"], res["equity"], months)
        if s["n"] == 0: continue
        pf = f"{s['pf']:.2f}" if s['pf'] < 99 else "inf"
        tag = ""
        if s["ret_per_mo"] >= 2.0 and abs(s["eq_maxdd"]) < 5000: tag = " ★★"
        elif s["ret_per_mo"] >= 0.5: tag = " ★"
        elif s["total"] > 0: tag = " +"
        print(f"{nstd:>5.1f}σ {s['n']:>7} {s['trades_per_mo']:>4.1f} "
              f"{s['wr']*100:>5.1f}% {pf:>5} ${s['per']:>+5,.0f} "
              f"${s['total']:>+7,.0f} ${s['eq_maxdd']:>+7,.0f} "
              f"{s['ret_per_mo']:>+6.2f}%{tag}")

    print("\n" + "=" * 100)
    print("D. RSI EXTREMES FADE — sweep thresholds")
    print("=" * 100)
    print(f"{'Upper':>6} {'Lower':>6} {'Trades':>7} {'/mo':>5} {'WR':>6} "
          f"{'PF':>5} {'$/tr':>7} {'Total':>9} {'EqDD':>9} {'Ret/mo':>8}")
    for up_low in [(75, 25), (80, 20), (85, 15), (90, 10)]:
        res = run_rsi_fade(arr1, nq.index, 14, up_low[0], up_low[1])
        s = stats(res["trades"], res["equity"], months)
        if s["n"] == 0: continue
        pf = f"{s['pf']:.2f}" if s['pf'] < 99 else "inf"
        tag = ""
        if s["ret_per_mo"] >= 2.0 and abs(s["eq_maxdd"]) < 5000: tag = " ★★"
        elif s["ret_per_mo"] >= 0.5: tag = " ★"
        elif s["total"] > 0: tag = " +"
        print(f"{up_low[0]:>5}/{up_low[1]:<5} {s['n']:>7} "
              f"{s['trades_per_mo']:>4.1f} {s['wr']*100:>5.1f}% {pf:>5} "
              f"${s['per']:>+5,.0f} ${s['total']:>+7,.0f} "
              f"${s['eq_maxdd']:>+7,.0f} {s['ret_per_mo']:>+6.2f}%{tag}")


if __name__ == "__main__":
    main()
