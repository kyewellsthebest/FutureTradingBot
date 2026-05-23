"""TRUE pair trading: long one leg + short the other simultaneously.

Real stat arb math:
  - Spread = NQ_price - hedge_ratio * ES_price
  - Z-score the spread (using rolling window, no look-ahead)
  - When z > entry → SHORT spread = short NQ + LONG ES (dollar-equivalent)
  - When z < -entry → LONG spread = long NQ + SHORT ES
  - Exit when z crosses back to 0 (convergence)
  - Stop when z extends to stop_z (failed convergence)

Sizing for dollar-neutrality:
  - 1 NQ contract = $20/pt (5 MNQ = $10/pt)
  - 1 ES contract = $50/pt (2 MES = $10/pt)
  - So 5 MNQ + 2 MES ≈ dollar-equal hedge

P&L = sum of both legs.
"""
from __future__ import annotations
import numpy as np, pandas as pd
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "polygon"

STARTING_BALANCE     = 50_000.0
MNQ_PER_PT           = 2.0
MES_PER_PT           = 5.0
NQ_CONTRACTS         = 5     # MNQ
ES_CONTRACTS         = 2     # MES
COMM_PER_CONTRACT_RT = 2.0


def load_and_align() -> pd.DataFrame:
    nq = pd.read_csv(DATA / "NQ_5min.csv", parse_dates=["ts"]).set_index("ts").sort_index()
    es = pd.read_csv(DATA / "ES_5min.csv", parse_dates=["ts"]).set_index("ts").sort_index()
    if nq.index.tz is None: nq.index = nq.index.tz_localize("UTC")
    if es.index.tz is None: es.index = es.index.tz_localize("UTC")
    df = pd.DataFrame({
        "nq_close": nq["close"], "es_close": es["close"],
        "nq_high": nq["high"], "nq_low": nq["low"],
        "es_high": es["high"], "es_low": es["low"],
    }).dropna()
    return df


def run_pair_hedged(df: pd.DataFrame, window: int, entry_z: float,
                    exit_z: float, stop_z: float, max_hold: int = 60) -> dict:
    nq_c = df["nq_close"].to_numpy()
    es_c = df["es_close"].to_numpy()
    n = len(df)

    # log ratio = log(NQ) - log(ES). Equivalent to log price spread.
    log_nq = np.log(nq_c); log_es = np.log(es_c)
    log_ratio = log_nq - log_es

    # rolling z-score (PRIOR-bar window to avoid look-ahead)
    z = np.full(n, np.nan)
    for t in range(window, n):
        prev = log_ratio[t - window:t]   # excluding bar t
        mean = prev.mean(); std = prev.std()
        if std > 0:
            z[t] = (log_ratio[t] - mean) / std

    trades = []
    active = None   # {"side": "SHORT_SPREAD"/"LONG_SPREAD",
                    #  "nq_entry", "es_entry", "entry_bar", "entry_z"}
    equity = STARTING_BALANCE
    equity_curve = np.zeros(n)

    for t in range(n):
        if active is not None:
            exit_now = False; reason = ""
            if not np.isnan(z[t]):
                if active["side"] == "SHORT_SPREAD" and z[t] <= exit_z:
                    exit_now = True; reason = "target"
                elif active["side"] == "LONG_SPREAD" and z[t] >= exit_z:
                    exit_now = True; reason = "target"
                elif active["side"] == "SHORT_SPREAD" and z[t] >= stop_z:
                    exit_now = True; reason = "stop"
                elif active["side"] == "LONG_SPREAD" and z[t] <= -stop_z:
                    exit_now = True; reason = "stop"
            if not exit_now and t - active["entry_bar"] >= max_hold:
                exit_now = True; reason = "timeout"
            if exit_now:
                nq_exit = float(nq_c[t]); es_exit = float(es_c[t])
                if active["side"] == "SHORT_SPREAD":
                    # short NQ, long ES
                    nq_pnl_pts = active["nq_entry"] - nq_exit
                    es_pnl_pts = es_exit - active["es_entry"]
                else:  # LONG_SPREAD: long NQ, short ES
                    nq_pnl_pts = nq_exit - active["nq_entry"]
                    es_pnl_pts = active["es_entry"] - es_exit
                nq_pnl = nq_pnl_pts * NQ_CONTRACTS * MNQ_PER_PT
                es_pnl = es_pnl_pts * ES_CONTRACTS * MES_PER_PT
                # commissions on both legs
                comm = COMM_PER_CONTRACT_RT * (NQ_CONTRACTS + ES_CONTRACTS)
                pnl = nq_pnl + es_pnl - comm
                equity += pnl
                trades.append({
                    "entry_bar": active["entry_bar"], "exit_bar": t,
                    "side": active["side"], "entry_z": active["entry_z"],
                    "exit_z": float(z[t]) if not np.isnan(z[t]) else None,
                    "nq_pnl": float(nq_pnl), "es_pnl": float(es_pnl),
                    "pnl_usd": float(pnl), "exit_reason": reason,
                    "hold_bars": t - active["entry_bar"],
                })
                active = None

        if active is None and not np.isnan(z[t]):
            if z[t] > entry_z:
                # short spread = short NQ, long ES
                active = {"side": "SHORT_SPREAD",
                          "nq_entry": float(nq_c[t]),
                          "es_entry": float(es_c[t]),
                          "entry_bar": t, "entry_z": float(z[t])}
            elif z[t] < -entry_z:
                active = {"side": "LONG_SPREAD",
                          "nq_entry": float(nq_c[t]),
                          "es_entry": float(es_c[t]),
                          "entry_bar": t, "entry_z": float(z[t])}

        equity_curve[t] = equity

    return {"trades": trades, "equity": pd.Series(equity_curve, index=df.index)}


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
    avg_w = float(tdf[tdf["pnl_usd"] > 0]["pnl_usd"].mean()) if wins > 0 else 0
    avg_l = float(tdf[tdf["pnl_usd"] < 0]["pnl_usd"].mean()) if wins < n else 0
    return {"n": n, "wr": wins / n,
            "pf": gw/gl if gl > 0 else float("inf"),
            "total": total, "per": total/n,
            "trades_per_mo": n/months,
            "eq_maxdd": eq_dd, "max_streak": max_streak,
            "ret_per_mo": total/STARTING_BALANCE*100/months,
            "rr": abs(avg_w/avg_l) if avg_l != 0 else 0,
            "avg_hold": float(tdf["hold_bars"].mean())}


def main():
    print("Loading and aligning NQ + ES 5-min data...")
    df = load_and_align()
    months = (df.index[-1] - df.index[0]).days / 30.44
    print(f"  bars: {len(df):,}   months: {months:.1f}")
    nq_ret = df["nq_close"].pct_change()
    es_ret = df["es_close"].pct_change()
    print(f"  Return correlation: {nq_ret.corr(es_ret):.4f}\n")

    print(f"{'Window':>7} {'EntZ':>5} {'ExitZ':>5} {'StopZ':>5} {'MaxH':>5} "
          f"{'Trades':>7} {'/wk':>5} {'WR':>6} {'PF':>5} {'RR':>5} "
          f"{'$/tr':>7} {'Total':>9} {'EqDD':>9} {'Ret/mo':>8}")
    print("-" * 115)

    all_results = []
    for window in [30, 50, 100, 200]:
        for entry_z in [1.5, 2.0, 2.5]:
            for stop_z in [3.0, 4.0]:
                for max_h in [30, 60, 120]:
                    res = run_pair_hedged(df, window, entry_z, 0.0, stop_z, max_h)
                    s = stats(res["trades"], res["equity"], months)
                    if s["n"] < 50: continue
                    twk = s["n"] / (months * 30 / 7)
                    pf = f"{s['pf']:.2f}" if s['pf'] < 99 else "inf"
                    tag = ""
                    if (s["wr"] >= 0.55 and twk >= 240 and s["rr"] >= 1.2):
                        tag = " ★★★★ HITS ALL"
                    elif s["wr"] >= 0.55 and s["ret_per_mo"] >= 2:
                        tag = " ★★"
                    elif s["ret_per_mo"] >= 1:
                        tag = " ★"
                    elif s["total"] > 0:
                        tag = " +"
                    print(f"{window:>7} {entry_z:>5.1f} {0.0:>5.1f} {stop_z:>5.1f} {max_h:>5} "
                          f"{s['n']:>7} {twk:>4.1f} {s['wr']*100:>5.1f}% {pf:>5} "
                          f"{s['rr']:>4.2f} ${s['per']:>+5,.0f} "
                          f"${s['total']:>+7,.0f} ${s['eq_maxdd']:>+7,.0f} "
                          f"{s['ret_per_mo']:>+6.2f}%{tag}")
                    all_results.append({"window": window, "entry_z": entry_z,
                                        "stop_z": stop_z, "max_h": max_h,
                                        "trades_per_week": twk, **s})

    print("\n" + "=" * 110)
    print("TOP 10 BY MONTHLY RETURN")
    print("=" * 110)
    all_results.sort(key=lambda x: -x["ret_per_mo"])
    for r in all_results[:10]:
        pf = f"{r['pf']:.2f}" if r['pf'] < 99 else "inf"
        print(f"  w={r['window']} entZ={r['entry_z']:.1f} stopZ={r['stop_z']:.1f} "
              f"maxH={r['max_h']} | n={r['n']} ({r['trades_per_week']:.1f}/wk) "
              f"WR={r['wr']*100:.1f}% PF={pf} RR={r['rr']:.2f} "
              f"${r['per']:+.0f}/tr DD${r['eq_maxdd']:+,.0f} "
              f"streak={r['max_streak']} → {r['ret_per_mo']:+.2f}%/mo")


if __name__ == "__main__":
    main()
