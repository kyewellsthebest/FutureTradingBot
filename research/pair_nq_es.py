"""NQ-ES Pair Trading (Statistical Arbitrage).

NQ and ES are both US equity index futures. They are highly correlated
but the spread between them mean-reverts (because their underlying
movement is highly similar but local divergences happen from order flow,
single-stock news, etc).

Strategy:
  1. Compute log price ratio: log(NQ / ES) per bar
  2. Compute z-score using rolling window
  3. When z-score crosses upper threshold → SHORT NQ + LONG ES
     (we expect NQ to fall relative to ES)
  4. When z-score crosses lower threshold → LONG NQ + SHORT ES
  5. Exit when z-score crosses back to 0 (mean reversion)
  6. Stop if z-score extends further (failed convergence)

We track P&L as if trading MNQ alone (the NQ leg) since user has MNQ
account. This is a simplification — real pair trading requires both legs
but the directional NQ signal still captures the edge.
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


def dynamic_size(stop_pts: float) -> int:
    if stop_pts <= 0: return 1
    return max(1, min(MAX_CONTRACTS, int(TARGET_RISK_USD / (stop_pts * MNQ_PER_PT))))


def load_and_align() -> pd.DataFrame:
    nq = pd.read_csv(DATA / "NQ_5min.csv", parse_dates=["ts"]).set_index("ts").sort_index()
    es = pd.read_csv(DATA / "ES_5min.csv", parse_dates=["ts"]).set_index("ts").sort_index()
    if nq.index.tz is None:
        nq.index = nq.index.tz_localize("UTC")
    if es.index.tz is None:
        es.index = es.index.tz_localize("UTC")
    # align on common timestamps
    df = pd.DataFrame({
        "nq_open": nq["open"], "nq_high": nq["high"], "nq_low": nq["low"], "nq_close": nq["close"],
        "es_open": es["open"], "es_high": es["high"], "es_low": es["low"], "es_close": es["close"],
    }).dropna()
    return df


def run_pair_trade(df: pd.DataFrame,
                   window: int = 50,
                   entry_z: float = 2.0,
                   exit_z: float = 0.0,
                   stop_z: float = 3.5,
                   max_hold_bars: int = 30) -> dict:
    """Z-score based pair trade. Returns trades + equity."""
    nq_c = df["nq_close"].to_numpy()
    nq_h = df["nq_high"].to_numpy()
    nq_l = df["nq_low"].to_numpy()
    es_c = df["es_close"].to_numpy()
    n = len(df)

    # log ratio
    ratio = np.log(nq_c) - np.log(es_c)
    # rolling z-score (using only prior bars to avoid look-ahead)
    z = np.full(n, np.nan)
    for t in range(window, n):
        prev = ratio[t - window:t]   # NOT including t itself
        mean = prev.mean()
        std = prev.std()
        if std > 0:
            z[t] = (ratio[t] - mean) / std

    trades = []
    active = None
    equity = STARTING_BALANCE
    equity_curve = np.zeros(n)

    for t in range(n):
        # update active trade
        if active is not None:
            # exit conditions: z-score back to exit_z, OR stop_z breach, OR timeout
            exit_now = False
            reason = ""
            if not np.isnan(z[t]):
                if active["side"] == "SHORT_NQ" and z[t] <= exit_z:
                    exit_now = True; reason = "target"
                elif active["side"] == "LONG_NQ" and z[t] >= exit_z:
                    exit_now = True; reason = "target"
                elif active["side"] == "SHORT_NQ" and z[t] >= stop_z:
                    exit_now = True; reason = "stop"
                elif active["side"] == "LONG_NQ" and z[t] <= -stop_z:
                    exit_now = True; reason = "stop"
            if not exit_now and t - active["entry_bar"] >= max_hold_bars:
                exit_now = True; reason = "timeout"
            if exit_now:
                exit_px = float(nq_c[t])
                pnl_pts = (active["entry"] - exit_px) if active["side"] == "SHORT_NQ" \
                          else (exit_px - active["entry"])
                pnl = pnl_pts * active["size"] * MNQ_PER_PT - COMM_PER_CONTRACT_RT * active["size"]
                equity += pnl
                trades.append({
                    "entry_bar": active["entry_bar"], "exit_bar": t,
                    "side": active["side"], "size": active["size"],
                    "entry_z": active["entry_z"], "exit_z": float(z[t]) if not np.isnan(z[t]) else None,
                    "pnl_usd": float(pnl), "exit_reason": reason,
                    "hold_bars": t - active["entry_bar"],
                })
                active = None

        # new entry signal
        if active is None and not np.isnan(z[t]):
            # use prior-bar z to decide, but enter at current close
            # (the z[t] is already excluding bar t's own info)
            if z[t] > entry_z:
                # NQ overpriced vs ES → short NQ
                entry_px = float(nq_c[t])
                # stop: when z-score crosses stop_z, we'd exit on that bar's close
                # for sizing, estimate price-stop using ATR or fixed
                stop_pts = max(5.0, 0.005 * entry_px)   # 0.5% or 5pt
                size = dynamic_size(stop_pts)
                active = {"entry_bar": t, "side": "SHORT_NQ", "size": size,
                          "entry": entry_px, "entry_z": float(z[t])}
            elif z[t] < -entry_z:
                entry_px = float(nq_c[t])
                stop_pts = max(5.0, 0.005 * entry_px)
                size = dynamic_size(stop_pts)
                active = {"entry_bar": t, "side": "LONG_NQ", "size": size,
                          "entry": entry_px, "entry_z": float(z[t])}

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
    rr = abs(avg_w / avg_l) if avg_l != 0 else 0
    return {"n": n, "wr": wins / n,
            "pf": gw/gl if gl > 0 else float("inf"),
            "total": total, "per": total/n, "trades_per_mo": n/months,
            "eq_maxdd": eq_dd, "max_streak": max_streak,
            "ret_per_mo": total/STARTING_BALANCE*100/months,
            "avg_hold": float(tdf["hold_bars"].mean()),
            "rr": rr}


def main():
    print("Loading NQ + ES 5-min data and aligning...")
    df = load_and_align()
    months = (df.index[-1] - df.index[0]).days / 30.44
    print(f"  aligned bars: {len(df):,}   months: {months:.1f}")

    # First, check correlation
    nq_ret = df["nq_close"].pct_change()
    es_ret = df["es_close"].pct_change()
    print(f"  NQ-ES return correlation: {nq_ret.corr(es_ret):.4f}")

    # Sweep parameters
    print(f"\n{'Window':>7} {'EntZ':>5} {'ExitZ':>5} {'StopZ':>5} "
          f"{'Trades':>7} {'/wk':>5} {'WR':>6} {'PF':>5} {'RR':>5} "
          f"{'$/tr':>7} {'Total':>9} {'EqDD':>9} {'Ret/mo':>8}")
    print("-" * 110)

    all_results = []
    for window in [30, 50, 100]:
        for entry_z in [1.0, 1.5, 2.0, 2.5]:
            for exit_z in [0.0, 0.5]:
                for stop_z in [3.0, 4.0, 5.0]:
                    res = run_pair_trade(df, window, entry_z, exit_z, stop_z)
                    s = stats(res["trades"], res["equity"], months)
                    if s["n"] < 50: continue
                    trades_per_week = s["n"] / (months * 30 / 7)
                    pf = f"{s['pf']:.2f}" if s['pf'] < 99 else "inf"
                    tag = ""
                    spec_match = (s["wr"] >= 0.55 and trades_per_week >= 240
                                 and s["rr"] >= 1.2)
                    if spec_match:
                        tag = " ★★★★ HITS ALL SPECS"
                    elif s["wr"] >= 0.55 and s["ret_per_mo"] >= 2:
                        tag = " ★★ profitable + high WR"
                    elif s["ret_per_mo"] >= 1:
                        tag = " ★"
                    elif s["total"] > 0:
                        tag = " +"
                    print(f"{window:>7} {entry_z:>5.1f} {exit_z:>5.1f} {stop_z:>5.1f} "
                          f"{s['n']:>7} {trades_per_week:>4.1f} {s['wr']*100:>5.1f}% {pf:>5} "
                          f"{s['rr']:>4.2f} ${s['per']:>+5,.0f} "
                          f"${s['total']:>+7,.0f} ${s['eq_maxdd']:>+7,.0f} "
                          f"{s['ret_per_mo']:>+6.2f}%{tag}")
                    all_results.append({"window": window, "entry_z": entry_z,
                                        "exit_z": exit_z, "stop_z": stop_z,
                                        "trades_per_week": trades_per_week, **s})

    print("\n" + "=" * 110)
    print("TOP 10 BY MONTHLY RETURN")
    print("=" * 110)
    all_results.sort(key=lambda x: -x["ret_per_mo"])
    for r in all_results[:10]:
        pf = f"{r['pf']:.2f}" if r['pf'] < 99 else "inf"
        print(f"  w={r['window']} entZ={r['entry_z']:.1f} exitZ={r['exit_z']:.1f} "
              f"stopZ={r['stop_z']:.1f} | n={r['n']} ({r['trades_per_week']:.1f}/wk) "
              f"WR={r['wr']*100:.1f}% PF={pf} RR={r['rr']:.2f} "
              f"${r['per']:+.0f}/tr DD${r['eq_maxdd']:+,.0f} "
              f"streak={r['max_streak']} → {r['ret_per_mo']:+.2f}%/mo")


if __name__ == "__main__":
    main()
