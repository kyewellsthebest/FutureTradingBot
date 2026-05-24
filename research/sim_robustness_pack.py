"""Robustness analysis pack:
  1. Hour-of-day filter (NY time)  -> finds best/worst trading hours
  2. Monte Carlo bootstrap (1000x) -> confidence intervals on +10.79%/mo
  3. Daily-loss circuit breaker    -> simulate "stop after -$X day"
  4. Weekday breakdown             -> see if Mon/Fri behave differently

All four derive from a SINGLE base sim run (Lucid prop cost model).
Outputs robustness_pack.json for the HTML report.
"""
from __future__ import annotations
import json, time
import numpy as np
import pandas as pd
from pathlib import Path
import sys
sys.path.insert(0, "/home/user/HFTBot")

from bot.pullback_strategy import (
    detect_pullback_setup, _setup_key,
    MIN_TARGET_HOLD_SECONDS, COOLDOWN_SECS,
    MAX_HOLD_SECS, MAX_WAIT_SECS,
)

SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")
OUT_JSON = Path("/home/user/HFTBot/reports/robustness_pack.json")

STARTING_BAL = 50_000.0
MNQ_PER_PT = 2.0
LATENCY_MS = 200
N_MNQ = 2
ENTRY_SLIP = 0.0
ADVERSE_SLIP = 0.25
COMM_RT = 0.74


def build_1m_bars(price, ts_ns, volume):
    df = pd.DataFrame({"price": price, "volume": volume,
                       "ts": pd.to_datetime(ts_ns, utc=True)})
    df = df.set_index("ts")
    ohlc = df["price"].resample("1min").agg(["first", "max", "min", "last"])
    ohlc.columns = ["open", "high", "low", "close"]
    vol = df["volume"].resample("1min").sum()
    return pd.concat([ohlc, vol.rename("volume")], axis=1).dropna()


def run_sim(price, ts_ns, bars_1m):
    bar_ts = bars_1m.index.astype("int64").to_numpy()
    cooldown_ns = COOLDOWN_SECS * 1_000_000_000
    latency_ns = LATENCY_MS * 1_000_000
    max_hold_ns = MAX_HOLD_SECS * 1_000_000_000
    max_wait_ns = MAX_WAIT_SECS * 1_000_000_000
    min_hold_ns = MIN_TARGET_HOLD_SECONDS * 1_000_000_000

    trades = []
    used_keys = set()
    last_exit_ts = -1

    for i in range(3, len(bars_1m) - 1):
        sig_ts = int(bar_ts[i + 1])
        bars_at_i = bars_1m.iloc[:i + 1]
        setup = detect_pullback_setup(bars_at_i,
            pd.Timestamp(sig_ts, tz="UTC").to_pydatetime())
        if setup is None: continue
        key = _setup_key(setup)
        if key in used_keys: continue
        if last_exit_ts > 0 and sig_ts - last_exit_ts < cooldown_ns: continue
        side = 1 if setup.side == "LONG" else -1
        intended = float(setup.pullback_entry)
        stop_px = float(setup.stop_px_val)
        target_px = float(setup.target_px_val)
        fill_start = int(np.searchsorted(ts_ns, sig_ts + latency_ns, side="left"))
        fill_end = int(np.searchsorted(ts_ns, sig_ts + max_wait_ns, side="left"))
        if fill_start >= fill_end: continue
        scan_fill = price[fill_start:fill_end]
        hits = scan_fill <= intended if side == 1 else scan_fill >= intended
        if not hits.any(): continue
        entry_idx = fill_start + int(np.argmax(hits))
        entry_ts = int(ts_ns[entry_idx])
        entry_price = intended + (ENTRY_SLIP if side == 1 else -ENTRY_SLIP)

        timeout_ts = entry_ts + max_hold_ns
        min_target_ts = entry_ts + min_hold_ns
        exit_end = min(int(np.searchsorted(ts_ns, timeout_ts, side="left")), len(price) - 1)
        if exit_end <= entry_idx: continue
        scan_p = price[entry_idx + 1:exit_end + 1]
        scan_t = ts_ns[entry_idx + 1:exit_end + 1]
        if side == 1:
            stop_mask = scan_p <= stop_px; tgt_mask = scan_p >= target_px
        else:
            stop_mask = scan_p >= stop_px; tgt_mask = scan_p <= target_px
        stop_idx = int(np.argmax(stop_mask)) if stop_mask.any() else len(scan_p)
        if tgt_mask.any():
            cand = np.where(tgt_mask & (scan_t >= min_target_ts))[0]
            tgt_idx = int(cand[0]) if len(cand) > 0 else len(scan_p)
        else:
            tgt_idx = len(scan_p)
        if stop_idx == len(scan_p) and tgt_idx == len(scan_p):
            exit_px = float(scan_p[-1]); exit_ts = int(scan_t[-1])
        elif stop_idx <= tgt_idx:
            exit_px = stop_px - (ADVERSE_SLIP if side == 1 else -ADVERSE_SLIP)
            exit_ts = int(scan_t[stop_idx])
        else:
            exit_px = target_px; exit_ts = int(scan_t[tgt_idx])
        pnl_pts = (exit_px - entry_price) if side == 1 else (entry_price - exit_px)
        pnl_usd = pnl_pts * N_MNQ * MNQ_PER_PT - COMM_RT * N_MNQ
        trades.append({
            "entry_ts": entry_ts,
            "exit_ts": exit_ts,
            "pnl_usd": round(float(pnl_usd), 2),
        })
        used_keys.add(key)
        last_exit_ts = exit_ts
    return trades


def hour_of_day_analysis(trades, period_days):
    """Bucket trades by NY hour, compute per-hour P&L and trade count."""
    df = pd.DataFrame(trades)
    df["entry_dt"] = pd.to_datetime(df["entry_ts"], utc=True).dt.tz_convert("America/New_York")
    df["hour"] = df["entry_dt"].dt.hour
    df["date"] = df["entry_dt"].dt.date.astype(str)
    out = []
    months = period_days / 30.44
    for hr in range(24):
        sub = df[df["hour"] == hr]
        if sub.empty:
            out.append({"hour": hr, "trades": 0, "wins": 0, "pnl": 0, "wr": 0, "ret_mo": 0})
            continue
        pnls = sub["pnl_usd"].values
        wins = int((pnls > 0).sum())
        out.append({
            "hour": hr,
            "trades": int(len(sub)),
            "wins": wins,
            "wr": round(wins/len(sub)*100, 1),
            "pnl": round(float(pnls.sum()), 0),
            "avg_pnl_trade": round(float(pnls.mean()), 2),
            "ret_mo": round(float(pnls.sum())/STARTING_BAL*100/months, 2),
        })
    return out


def monte_carlo_bootstrap(trades, period_days, n_runs=1000):
    """Resample trades with replacement to estimate confidence intervals.
    Each run picks the same number of trades, keeps them in random order,
    and recomputes final return + max DD. Then we get the distribution."""
    pnls = np.array([t["pnl_usd"] for t in trades])
    n = len(pnls)
    months = period_days / 30.44
    rng = np.random.default_rng(42)
    rets = np.zeros(n_runs)
    dds = np.zeros(n_runs)
    for k in range(n_runs):
        sample = rng.choice(pnls, size=n, replace=True)
        cum = sample.cumsum()
        dd = float((cum - np.maximum.accumulate(cum)).min())
        rets[k] = float(sample.sum()) / STARTING_BAL * 100 / months
        dds[k] = abs(dd) / STARTING_BAL * 100
    pct = lambda arr, p: float(np.percentile(arr, p))
    return {
        "n_runs": n_runs,
        "ret_mo": {
            "median": round(pct(rets, 50), 2),
            "p05":    round(pct(rets, 5), 2),
            "p25":    round(pct(rets, 25), 2),
            "p75":    round(pct(rets, 75), 2),
            "p95":    round(pct(rets, 95), 2),
            "mean":   round(float(rets.mean()), 2),
            "std":    round(float(rets.std()), 2),
            "min":    round(float(rets.min()), 2),
            "max":    round(float(rets.max()), 2),
        },
        "max_dd_pct": {
            "median": round(pct(dds, 50), 2),
            "p05":    round(pct(dds, 5), 2),
            "p25":    round(pct(dds, 25), 2),
            "p75":    round(pct(dds, 75), 2),
            "p95":    round(pct(dds, 95), 2),
            "max":    round(float(dds.max()), 2),
        },
        "prob_positive": round(float((rets > 0).mean()) * 100, 1),
        "prob_above_3pct": round(float((rets >= 3).mean()) * 100, 1),
        "prob_above_10pct": round(float((rets >= 10).mean()) * 100, 1),
        "prob_blows_2k_trail": round(float((dds >= 4.0).mean()) * 100, 1),  # 4% of 50k = 2k
        "prob_dd_over_2pct": round(float((dds >= 2.0).mean()) * 100, 1),
    }


def daily_loss_breaker(trades, period_days, threshold_usd):
    """Replay trades; when daily P&L drops to -threshold_usd, skip remaining
    trades for that NY day. Recompute return + DD under that rule."""
    df = pd.DataFrame(trades)
    df["entry_dt"] = pd.to_datetime(df["entry_ts"], utc=True).dt.tz_convert("America/New_York")
    df["date"] = df["entry_dt"].dt.date.astype(str)
    kept = []
    skipped = 0
    for date, group in df.groupby("date", sort=False):
        running = 0.0
        stopped = False
        for _, t in group.iterrows():
            if stopped:
                skipped += 1
                continue
            kept.append(t["pnl_usd"])
            running += float(t["pnl_usd"])
            if running <= -threshold_usd:
                stopped = True
    pnls = np.array(kept)
    if not len(pnls):
        return {"threshold": threshold_usd, "n": 0}
    cum = pnls.cumsum()
    maxdd = float((cum - np.maximum.accumulate(cum)).min())
    months = period_days / 30.44
    wins = int((pnls > 0).sum())
    return {
        "threshold_usd": threshold_usd,
        "n_trades": int(len(pnls)),
        "n_skipped": int(skipped),
        "wr": round(wins/len(pnls)*100, 1),
        "total_pnl": round(float(pnls.sum()), 0),
        "ret_mo": round(float(pnls.sum())/STARTING_BAL*100/months, 2),
        "max_dd_usd": round(maxdd, 0),
        "max_dd_pct": round(abs(maxdd/STARTING_BAL*100), 2),
    }


def weekday_analysis(trades, period_days):
    df = pd.DataFrame(trades)
    df["entry_dt"] = pd.to_datetime(df["entry_ts"], utc=True).dt.tz_convert("America/New_York")
    df["weekday"] = df["entry_dt"].dt.day_name()
    df["date"] = df["entry_dt"].dt.date.astype(str)
    months = period_days / 30.44
    out = []
    for wd in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
        sub = df[df["weekday"] == wd]
        if sub.empty: continue
        pnls = sub["pnl_usd"].values
        wins = int((pnls > 0).sum())
        out.append({
            "weekday": wd,
            "trades": int(len(sub)),
            "wr": round(wins/len(sub)*100, 1),
            "pnl": round(float(pnls.sum()), 0),
            "ret_mo": round(float(pnls.sum())/STARTING_BAL*100/months, 2),
        })
    return out


def main():
    t0 = time.time()
    print("Loading tick data...")
    df = pd.read_parquet(SRC)
    period_days = (df["ts"].iloc[-1] - df["ts"].iloc[0]).total_seconds() / 86400
    price = df["price"].to_numpy(dtype=np.float32)
    volume = df["volume"].to_numpy(dtype=np.int32)
    ts_ns = df["ts"].astype("int64").to_numpy()
    bars_1m = build_1m_bars(price, ts_ns, volume)
    print(f"  ready ({time.time()-t0:.0f}s)")

    print(f"\nRunning base sim (2 MNQ, Lucid costs $0.74 + 0.25pt adv)...")
    trades = run_sim(price, ts_ns, bars_1m)
    print(f"  {len(trades)} trades ({time.time()-t0:.0f}s)")

    print("\n[1/4] Hour-of-day analysis...")
    hour = hour_of_day_analysis(trades, period_days)
    for h in hour:
        if h["trades"] > 0:
            print(f"  hr={h['hour']:>2}: {h['trades']:>5} trades  WR={h['wr']:>5.1f}%  "
                  f"P&L=${h['pnl']:>+8,.0f}  ret_mo={h['ret_mo']:>+6.2f}%")

    print("\n[2/4] Monte Carlo bootstrap (1000 runs)...")
    mc = monte_carlo_bootstrap(trades, period_days, n_runs=1000)
    r = mc["ret_mo"]
    d = mc["max_dd_pct"]
    print(f"  Return/mo: median={r['median']:+.2f}%  "
          f"5-95% range=[{r['p05']:+.2f}%, {r['p95']:+.2f}%]")
    print(f"  Max DD %:  median={d['median']:.2f}%   "
          f"5-95% range=[{d['p05']:.2f}%, {d['p95']:.2f}%]")
    print(f"  P(positive month)={mc['prob_positive']}%  "
          f"P(>=3%)={mc['prob_above_3pct']}%  P(>=10%)={mc['prob_above_10pct']}%")
    print(f"  P(DD blows $2K trail / 4%)={mc['prob_blows_2k_trail']}%")

    print("\n[3/4] Daily loss circuit breaker test...")
    breaker_results = []
    for thr in [500, 700, 900, 1100, 0]:  # 0 = no breaker (baseline)
        if thr == 0:
            pnls = np.array([t["pnl_usd"] for t in trades])
            cum = pnls.cumsum()
            maxdd = float((cum - np.maximum.accumulate(cum)).min())
            months = period_days / 30.44
            baseline = {
                "threshold_usd": 0, "n_trades": len(trades), "n_skipped": 0,
                "wr": round(float((pnls>0).sum())/len(pnls)*100, 1),
                "total_pnl": round(float(pnls.sum()), 0),
                "ret_mo": round(float(pnls.sum())/STARTING_BAL*100/months, 2),
                "max_dd_usd": round(maxdd, 0),
                "max_dd_pct": round(abs(maxdd/STARTING_BAL*100), 2),
            }
            print(f"  no breaker   (baseline):  n={baseline['n_trades']:>4}  skipped={baseline['n_skipped']:>3}  "
                  f"ret={baseline['ret_mo']:+.2f}%/mo  DD=${baseline['max_dd_usd']:>+,.0f} ({baseline['max_dd_pct']}%)")
            breaker_results.append(baseline)
        else:
            b = daily_loss_breaker(trades, period_days, thr)
            print(f"  stop at -${thr:>4}:           n={b['n_trades']:>4}  skipped={b['n_skipped']:>3}  "
                  f"ret={b['ret_mo']:+.2f}%/mo  DD=${b['max_dd_usd']:>+,.0f} ({b['max_dd_pct']}%)")
            breaker_results.append(b)

    print("\n[4/4] Weekday analysis...")
    wd = weekday_analysis(trades, period_days)
    for w in wd:
        print(f"  {w['weekday']:<10}: {w['trades']:>5} trades  WR={w['wr']:>5.1f}%  "
              f"P&L=${w['pnl']:>+8,.0f}  ret_mo={w['ret_mo']:>+6.2f}%")

    out = {
        "meta": {
            "n_trades": len(trades),
            "period_days": round(period_days, 1),
            "n_mnq": N_MNQ, "comm_rt": COMM_RT, "adverse_slip": ADVERSE_SLIP,
        },
        "hour_of_day": hour,
        "monte_carlo": mc,
        "daily_breaker": breaker_results,
        "weekday": wd,
        "trades": trades,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nWrote {OUT_JSON} ({time.time()-t0:.0f}s total)")


if __name__ == "__main__":
    main()
