"""High-frequency wick-fade scalp.

Pattern: when a bar shows strong rejection (large upper or lower wick),
price tends to revert toward the bar's midpoint on the next 1-2 bars.

Entry signal (BEARISH REJECTION → SHORT next bar):
  - bar's upper wick >= rej_pct * bar range
  - close in lower half of bar (showing the wick rejected)
  - upper wick > lower wick

Entry signal (BULLISH REJECTION → LONG): mirror.

Trade:
  - Entry at next bar's open
  - Stop: bar's high (short) / low (long) + buffer
  - Target: midpoint of the rejection bar
  - Hold: max N bars then exit at close
"""
from __future__ import annotations
import numpy as np, pandas as pd
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "polygon" / "NQ_1min.csv"

STARTING_BALANCE     = 50_000.0
MNQ_PER_PT           = 2.0
COMM_PER_CONTRACT_RT = 2.0
TARGET_RISK_USD      = 100.0
MAX_CONTRACTS        = 5


def dynamic_size(stop_pts: float) -> int:
    if stop_pts <= 0: return 1
    return max(1, min(MAX_CONTRACTS, int(TARGET_RISK_USD / (stop_pts * MNQ_PER_PT))))


def run_scalp(arr: np.ndarray, idx,
              rej_pct: float = 0.50,
              buffer_pts: float = 0.5,
              max_hold_bars: int = 3,
              min_bar_range_pts: float = 4.0,
              min_rr: float = 0.5) -> dict:
    o = arr[:, 0]; h = arr[:, 1]; l = arr[:, 2]; c = arr[:, 3]
    n = len(arr)
    trades = []
    active = None
    equity = STARTING_BALANCE
    equity_curve = np.zeros(n)

    for t in range(n):
        if active is not None:
            stop_hit = (active["side"] == "LONG" and l[t] <= active["stop"]) or \
                       (active["side"] == "SHORT" and h[t] >= active["stop"])
            tgt_hit  = (active["side"] == "LONG" and h[t] >= active["target"]) or \
                       (active["side"] == "SHORT" and l[t] <= active["target"])
            exit_px = None; reason = ""
            if stop_hit and tgt_hit:
                exit_px = active["stop"]; reason = "stop"
            elif stop_hit: exit_px = active["stop"]; reason = "stop"
            elif tgt_hit:  exit_px = active["target"]; reason = "target"
            elif t - active["entry_bar"] >= max_hold_bars:
                exit_px = float(c[t]); reason = "timeout"
            if exit_px is not None:
                pnl_pts = (active["entry"] - exit_px) if active["side"] == "SHORT" \
                          else (exit_px - active["entry"])
                pnl = pnl_pts * active["size"] * MNQ_PER_PT \
                      - COMM_PER_CONTRACT_RT * active["size"]
                equity += pnl
                trades.append({
                    "side": active["side"], "size": active["size"],
                    "pnl_usd": float(pnl),
                    "hold_bars": t - active["entry_bar"],
                    "exit_reason": reason,
                })
                active = None

        if active is None and t + 1 < n:
            bar_range = float(h[t] - l[t])
            if bar_range < min_bar_range_pts:
                equity_curve[t] = equity
                continue
            body_top = max(float(o[t]), float(c[t]))
            body_bot = min(float(o[t]), float(c[t]))
            upper_wick = float(h[t]) - body_top
            lower_wick = body_bot - float(l[t])
            close_pct = (float(c[t]) - float(l[t])) / bar_range

            if (upper_wick / bar_range >= rej_pct and close_pct <= 0.5
                    and upper_wick > lower_wick):
                entry_px = float(o[t + 1])
                stop_px = float(h[t]) + buffer_pts
                target_px = (float(h[t]) + float(l[t])) / 2.0
                stop_pts = stop_px - entry_px
                target_pts = entry_px - target_px
                if stop_pts > 0 and target_pts >= stop_pts * min_rr:
                    size = dynamic_size(stop_pts)
                    active = {
                        "entry_bar": t + 1, "side": "SHORT", "size": size,
                        "entry": entry_px, "stop": stop_px, "target": target_px,
                    }

            elif (lower_wick / bar_range >= rej_pct and close_pct >= 0.5
                    and lower_wick > upper_wick):
                entry_px = float(o[t + 1])
                stop_px = float(l[t]) - buffer_pts
                target_px = (float(h[t]) + float(l[t])) / 2.0
                stop_pts = entry_px - stop_px
                target_pts = target_px - entry_px
                if stop_pts > 0 and target_pts >= stop_pts * min_rr:
                    size = dynamic_size(stop_pts)
                    active = {
                        "entry_bar": t + 1, "side": "LONG", "size": size,
                        "entry": entry_px, "stop": stop_px, "target": target_px,
                    }

        equity_curve[t] = equity

    return {"trades": trades, "equity": pd.Series(equity_curve, index=idx)}


def resample(nq, freq):
    if freq == "1min": return nq
    return nq.resample(freq).agg({"open":"first","high":"max","low":"min","close":"last"}).dropna()


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

    timeframes = ["1min", "2min", "3min", "5min"]
    rej_pcts   = [0.40, 0.50, 0.60]
    min_ranges = [2.0, 4.0, 6.0]
    rrs        = [0.5, 1.0]

    all_results = []
    for tf in timeframes:
        df = resample(nq, tf)
        arr = df[["open","high","low","close"]].to_numpy()
        print(f"\n=== {tf} ({len(df):,} bars) ===")
        print(f"{'Rej%':>5} {'MinRng':>7} {'RR':>4} {'Trades':>7} {'/hr':>5} "
              f"{'WR':>6} {'PF':>5} {'$/tr':>6} {'Total':>9} {'EqDD':>8} "
              f"{'Streak':>7} {'Ret/mo':>7}")
        for rej in rej_pcts:
            for mr in min_ranges:
                for rr in rrs:
                    res = run_scalp(arr, df.index, rej_pct=rej,
                                     min_bar_range_pts=mr, min_rr=rr)
                    s = stats(res["trades"], res["equity"], months)
                    if s["n"] < 100: continue
                    trades_per_hr = s["n"] / (months * 30 * 7)
                    pf = f"{s['pf']:.2f}" if s['pf'] < 99 else "inf"
                    tag = ""
                    if (s["ret_per_mo"] >= 5.0 and trades_per_hr >= 5
                            and abs(s["eq_maxdd"]) < 2000):
                        tag = " ★★★★ HITS SPEC"
                    elif s["ret_per_mo"] >= 2.0:
                        tag = " ★★"
                    elif s["ret_per_mo"] >= 0.5:
                        tag = " ★"
                    elif s["total"] > 0:
                        tag = " +"
                    print(f"{rej:>5.2f} {mr:>6.1f}p {rr:>4.1f} {s['n']:>7} "
                          f"{trades_per_hr:>4.1f} {s['wr']*100:>5.1f}% {pf:>5} "
                          f"${s['per']:>+4,.0f} ${s['total']:>+7,.0f} "
                          f"${s['eq_maxdd']:>+6,.0f} {s['max_streak']:>6} "
                          f"{s['ret_per_mo']:>+5.2f}%{tag}")
                    all_results.append({"tf": tf, "rej": rej, "mr": mr, "rr": rr,
                                        **s, "trades_per_hr": trades_per_hr})

    print("\n" + "=" * 110)
    print("TOP 10 BY MONTHLY RETURN (min 100 trades)")
    print("=" * 110)
    all_results.sort(key=lambda x: -x["ret_per_mo"])
    for r in all_results[:10]:
        pf = f"{r['pf']:.2f}" if r['pf'] < 99 else "inf"
        print(f"  {r['tf']:>4} rej={r['rej']:.2f} minRng={r['mr']:.0f} "
              f"rr={r['rr']:.1f} | n={r['n']} ({r['trades_per_hr']:.1f}/hr) "
              f"WR={r['wr']*100:.1f}% PF={pf} ${r['per']:+.0f}/tr "
              f"DD${r['eq_maxdd']:+,.0f} streak={r['max_streak']} "
              f"→ {r['ret_per_mo']:+.2f}%/mo")


if __name__ == "__main__":
    main()
