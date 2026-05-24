"""Large-Trade Fade strategy on NQ tick data.

Hypothesis: When a single trade with volume >= LARGE_THRESHOLD prints,
it often represents institutional liquidation at an extreme. Price tends
to revert in the opposite direction shortly after.

Trade mechanics:
  - Large BUY (price>=ask, vol>=N) → SHORT entry at next tick's price
  - Large SELL (price<=bid, vol>=N) → LONG entry at next tick's price
  - Stop: HOLD_STOP_PTS NQ points from entry
  - Target: TARGET_PTS NQ points from entry
  - Time limit: HOLD_SECS seconds, then exit at last price

Tests across multiple thresholds and target/stop combinations.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from pathlib import Path

SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")

# Sizing
STARTING_BALANCE = 50_000.0
MNQ_PER_PT = 2.0
COMM_PER_CONTRACT_RT = 2.0
TARGET_RISK_USD = 50.0
MAX_CONTRACTS = 5


def dynamic_size(stop_pts: float) -> int:
    if stop_pts <= 0:
        return 1
    return max(1, min(MAX_CONTRACTS, int(TARGET_RISK_USD / (stop_pts * MNQ_PER_PT))))


def run_large_fade(price: np.ndarray, ts_ns: np.ndarray,
                   volume: np.ndarray, aggressor: np.ndarray,
                   large_threshold: int = 100,
                   stop_pts: float = 2.0,
                   target_pts: float = 2.5,
                   hold_secs: int = 60,
                   cooldown_secs: int = 30) -> list[dict]:
    """Returns list of trade dicts."""
    n = len(price)
    trades = []
    last_trade_ts = -1
    cooldown_ns = cooldown_secs * 1_000_000_000
    hold_ns = hold_secs * 1_000_000_000
    active = None

    for i in range(n - 1):
        # Manage active trade
        if active is not None:
            cur_px = float(price[i])
            cur_ts = ts_ns[i]
            stop_hit = (active["side"] == "LONG" and cur_px <= active["stop"]) or \
                       (active["side"] == "SHORT" and cur_px >= active["stop"])
            tgt_hit = (active["side"] == "LONG" and cur_px >= active["target"]) or \
                      (active["side"] == "SHORT" and cur_px <= active["target"])
            time_up = (cur_ts - active["entry_ts"]) >= hold_ns
            exit_px = None; reason = ""
            if stop_hit: exit_px = active["stop"]; reason = "stop"
            elif tgt_hit: exit_px = active["target"]; reason = "target"
            elif time_up: exit_px = cur_px; reason = "time"
            if exit_px is not None:
                pnl_pts = (active["entry"] - exit_px) if active["side"] == "SHORT" \
                          else (exit_px - active["entry"])
                pnl = pnl_pts * active["size"] * MNQ_PER_PT - COMM_PER_CONTRACT_RT * active["size"]
                trades.append({
                    "side": active["side"], "size": active["size"],
                    "entry_ts": active["entry_ts"], "exit_ts": cur_ts,
                    "entry_px": active["entry"], "exit_px": float(exit_px),
                    "pnl_usd": float(pnl), "exit_reason": reason,
                    "trigger_vol": active["trigger_vol"],
                    "hold_secs": (cur_ts - active["entry_ts"]) / 1e9,
                })
                last_trade_ts = cur_ts
                active = None

        # Look for large trade trigger
        if active is None and volume[i] >= large_threshold:
            # cooldown check
            if last_trade_ts > 0 and ts_ns[i] - last_trade_ts < cooldown_ns:
                continue
            agg = aggressor[i]
            if agg == 0:
                continue
            # Enter opposite direction at next tick
            entry_px = float(price[i + 1])
            if agg == 1:  # large BUY → expect reversal down → SHORT
                stop = entry_px + stop_pts
                target = entry_px - target_pts
                side = "SHORT"
            else:  # large SELL → expect reversal up → LONG
                stop = entry_px - stop_pts
                target = entry_px + target_pts
                side = "LONG"
            size = dynamic_size(stop_pts)
            active = {
                "side": side, "size": size, "entry": entry_px,
                "stop": stop, "target": target,
                "entry_ts": ts_ns[i + 1],
                "trigger_vol": int(volume[i]),
            }

    return trades


def stats(trades, n_calendar_days):
    if not trades:
        return None
    n = len(trades)
    pnls = np.array([t["pnl_usd"] for t in trades])
    wins = int((pnls > 0).sum())
    gw = float(pnls[pnls > 0].sum()); gl = float(abs(pnls[pnls < 0].sum()))
    pf = gw / gl if gl > 0 else float("inf")
    cum = pnls.cumsum()
    maxdd = float((cum - np.maximum.accumulate(cum)).min())
    avg_w = float(pnls[pnls > 0].mean()) if wins else 0
    avg_l = float(pnls[pnls < 0].mean()) if wins < n else 0
    rr = abs(avg_w / avg_l) if avg_l != 0 else 0
    streak = max_streak = 0
    for p in pnls:
        if p < 0:
            streak += 1
            if streak > max_streak: max_streak = streak
        else:
            streak = 0
    months = n_calendar_days / 30.44
    return {
        "n": n, "wr": wins/n, "pf": pf, "rr": rr,
        "total": float(pnls.sum()), "per": float(pnls.mean()),
        "trades_per_mo": n/months, "trades_per_day": n/n_calendar_days,
        "maxdd": maxdd, "maxdd_pct": maxdd/STARTING_BALANCE*100,
        "max_streak": max_streak,
        "ret_per_mo": float(pnls.sum())/STARTING_BALANCE*100/months,
    }


def hits_spec(s):
    if not s: return False
    return (s["wr"] >= 0.55 and s["rr"] >= 1.2 and s["trades_per_mo"] >= 100
            and s["ret_per_mo"] >= 3.0 and abs(s["maxdd_pct"]) <= 2.0)


def main():
    print("Loading tick parquet...")
    df = pd.read_parquet(SRC)
    n_days = df["ts"].dt.tz_convert("America/New_York").dt.date.nunique()
    print(f"  ticks: {len(df):,}   days: {n_days}")
    print()

    # Convert to numpy for speed
    price = df["price"].to_numpy(dtype=np.float32)
    volume = df["volume"].to_numpy(dtype=np.int32)
    aggressor = df["aggressor"].to_numpy(dtype=np.int8)
    ts_ns = df["ts"].astype("int64").to_numpy()

    print(f"{'Thresh':>7} {'Stop':>5} {'Tgt':>5} {'HoldS':>6} {'CDS':>5} "
          f"{'Trades':>7} {'/mo':>5} {'/day':>5} {'WR':>6} {'PF':>5} {'RR':>5} "
          f"{'$/tr':>6} {'Total':>9} {'DD%':>5} {'Ret/mo':>7}")
    print("-" * 120)

    all_results = []
    # Sweep parameters
    for thresh in [30, 50, 100, 200]:
        for stop in [1.0, 2.0, 3.0, 5.0]:
            for tgt in [1.5, 2.5, 4.0, 6.0]:
                for hold in [30, 60, 180]:
                    for cd in [10, 30]:
                        trades = run_large_fade(
                            price, ts_ns, volume, aggressor,
                            large_threshold=thresh,
                            stop_pts=stop, target_pts=tgt,
                            hold_secs=hold, cooldown_secs=cd,
                        )
                        s = stats(trades, n_days)
                        if not s or s["n"] < 30: continue
                        pf = f"{s['pf']:.2f}" if s['pf'] < 99 else "inf"
                        tag = ""
                        if hits_spec(s): tag = " ★★★★ HITS SPEC!"
                        elif s["wr"] >= 0.55 and s["ret_per_mo"] >= 1: tag = " ★★"
                        elif s["ret_per_mo"] >= 0.5: tag = " ★"
                        elif s["total"] > 0: tag = " +"
                        print(f"{thresh:>7} {stop:>5.1f} {tgt:>5.1f} {hold:>5}s "
                              f"{cd:>4}s {s['n']:>7} {s['trades_per_mo']:>4.1f} "
                              f"{s['trades_per_day']:>4.1f} {s['wr']*100:>5.1f}% "
                              f"{pf:>5} {s['rr']:>4.2f} ${s['per']:>+4,.0f} "
                              f"${s['total']:>+7,.0f} {abs(s['maxdd_pct']):>4.1f}% "
                              f"{s['ret_per_mo']:>+5.2f}%{tag}")
                        all_results.append({**s, "thresh": thresh, "stop": stop,
                                            "tgt": tgt, "hold": hold, "cd": cd})

    print("\n" + "=" * 80)
    print("TOP 10 BY RET/MO (with positive return and 100+ trades/mo)")
    print("=" * 80)
    all_results.sort(key=lambda x: -x["ret_per_mo"])
    pos = [r for r in all_results if r["total"] > 0 and r["trades_per_mo"] >= 50]
    for r in pos[:10]:
        pf = f"{r['pf']:.2f}" if r['pf'] < 99 else "inf"
        print(f"  thresh={r['thresh']} stop={r['stop']:.1f} tgt={r['tgt']:.1f} "
              f"hold={r['hold']}s cd={r['cd']}s | n={r['n']} "
              f"({r['trades_per_mo']:.0f}/mo, {r['trades_per_day']:.1f}/day) "
              f"WR={r['wr']*100:.1f}% PF={pf} RR={r['rr']:.2f} "
              f"DD={abs(r['maxdd_pct']):.1f}% → {r['ret_per_mo']:+.2f}%/mo")


if __name__ == "__main__":
    main()
