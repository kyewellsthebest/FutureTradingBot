"""Re-test all leading strategies at fixed 1 MNQ position size.

CHANGES vs 5 MNQ version:
  - Position size: FIXED at 1 MNQ (no dynamic sizing)
  - Risk per trade: stop_pts × $2 (was up to stop_pts × $10)
  - Commission: $1 round trip per trade (was $5 at 5 MNQ)
  - Per-trade P&L scaled by 1/5

THIS MEANS:
  - DD scales by 1/5 (good for tight DD spec)
  - But commission as % of risk goes UP (bad for thin-edge strategies)
  - Position-size cap no longer triggered (was 5)

Strategies retested:
  1. Pullback after impulse (the +5.28%/mo standout)
  2. Multi-bar momentum + cumdelta (post-bug-fix)
  3. NR4/NR7 range expansion
  4. Initial Balance retest
  5. VWAP fade with delta confirm

Same period: Dec 10 2025 → Feb 27 2026 (79 days tick data).
"""
from __future__ import annotations
import time
import numpy as np
import pandas as pd
from pathlib import Path

SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")

STARTING_BALANCE = 50_000.0
MNQ_PER_PT = 2.0
COMM_PER_CONTRACT_RT = 1.0
FIXED_SIZE = 1                # 1 MNQ — the test parameter
LATENCY_MS = 200


def build_bars(price, ts_ns, volume, aggressor, freq="1min"):
    df = pd.DataFrame({"price": price, "volume": volume, "aggressor": aggressor,
                       "ts": pd.to_datetime(ts_ns, utc=True)})
    df["signed_vol"] = df["volume"] * df["aggressor"]
    df = df.set_index("ts")
    ohlc = df["price"].resample(freq).agg(["first", "max", "min", "last"])
    ohlc.columns = ["open", "high", "low", "close"]
    vol = df["volume"].resample(freq).sum()
    delta = df["signed_vol"].resample(freq).sum()
    return pd.concat([ohlc, vol.rename("volume"), delta.rename("delta")], axis=1).dropna()


def simulate_trade(price, ts_ns, signal_ts, side, entry_intent,
                   stop_px, target_px, max_hold_secs,
                   use_market_entry=True, max_wait_secs=120,
                   latency_ms=LATENCY_MS, comm=COMM_PER_CONTRACT_RT,
                   fixed_size=FIXED_SIZE):
    n = len(price)
    latency_ns = latency_ms * 1_000_000
    fill_deadline = signal_ts + latency_ns

    entry_search_start = int(np.searchsorted(ts_ns, fill_deadline, side="left"))
    if entry_search_start >= n: return None

    if use_market_entry:
        entry_idx = entry_search_start
        actual_entry_px = float(price[entry_idx])
    else:
        wait_end_ts = signal_ts + max_wait_secs * 1_000_000_000
        wait_end_idx = min(int(np.searchsorted(ts_ns, wait_end_ts, side="left")), n - 1)
        if wait_end_idx <= entry_search_start: return None
        scan = price[entry_search_start:wait_end_idx + 1]
        hits = scan <= entry_intent if side == 1 else scan >= entry_intent
        if not hits.any(): return None
        entry_idx = entry_search_start + int(np.argmax(hits))
        actual_entry_px = entry_intent

    entry_ts = int(ts_ns[entry_idx])
    deadline_ts = entry_ts + max_hold_secs * 1_000_000_000
    end_idx = min(int(np.searchsorted(ts_ns, deadline_ts, side="left")), n - 1)
    if end_idx <= entry_idx: return None

    seg = price[entry_idx + 1:end_idx + 1].astype(np.float32)
    seg_ts = ts_ns[entry_idx + 1:end_idx + 1]
    if len(seg) == 0: return None

    if side == 1:
        stop_hits = seg <= stop_px; tgt_hits = seg >= target_px
    else:
        stop_hits = seg >= stop_px; tgt_hits = seg <= target_px
    s_first = int(np.argmax(stop_hits)) if stop_hits.any() else len(seg)
    t_first = int(np.argmax(tgt_hits)) if tgt_hits.any() else len(seg)

    if s_first == len(seg) and t_first == len(seg):
        exit_px = float(seg[-1]); exit_reason = "timeout"
    elif s_first <= t_first:
        exit_px = stop_px; exit_reason = "stop"
    else:
        exit_px = target_px; exit_reason = "target"

    pnl_pts = (actual_entry_px - exit_px) if side == -1 else (exit_px - actual_entry_px)
    pnl = pnl_pts * fixed_size * MNQ_PER_PT - comm * fixed_size
    return {"side": side, "size": fixed_size, "entry_ts": entry_ts,
            "exit_ts": int(seg_ts[-1]) if exit_reason == "timeout"
                       else int(seg_ts[min(s_first, t_first)]),
            "entry_px": actual_entry_px, "exit_px": exit_px,
            "pnl_usd": float(pnl), "exit_reason": exit_reason}


def summarize(trades, period_days):
    n = len(trades)
    if n == 0: return None
    pnls = np.array([t["pnl_usd"] for t in trades])
    wins = int((pnls > 0).sum())
    gw = float(pnls[pnls > 0].sum())
    gl = float(abs(pnls[pnls < 0].sum()))
    pf = gw / gl if gl > 0 else float("inf")
    cum = pnls.cumsum()
    maxdd = float((cum - np.maximum.accumulate(cum)).min())
    avg_w = float(pnls[pnls > 0].mean()) if wins else 0
    avg_l = float(pnls[pnls < 0].mean()) if wins < n else 0
    streak = max_streak = 0
    for p in pnls:
        if p < 0:
            streak += 1
            if streak > max_streak: max_streak = streak
        else: streak = 0
    months = period_days / 30.44
    return {"n": n, "wr": wins/n, "pf": pf,
            "rr": abs(avg_w/avg_l) if avg_l != 0 else 0,
            "total": float(pnls.sum()), "per": float(pnls.mean()),
            "trades_per_day": n/period_days, "trades_per_mo": n/months,
            "maxdd": maxdd, "maxdd_pct": maxdd/STARTING_BALANCE*100,
            "max_streak": max_streak,
            "ret_per_mo": float(pnls.sum())/STARTING_BALANCE*100/months}


def hits_spec(s):
    if not s: return False
    return (s["wr"] >= 0.55 and s["rr"] >= 1.2 and s["trades_per_mo"] >= 100
            and s["ret_per_mo"] >= 3.0 and abs(s["maxdd_pct"]) <= 2.0)


# ============================================================================
# Pullback strategy (the +5.28%/mo at 5MNQ standout)
# ============================================================================
def strategy_pullback_1mnq(bars_1m, price, ts_ns,
                            impulse_pts, window_bars, pullback_pct,
                            stop_pts, target_pts,
                            max_hold_secs=600, cooldown_secs=60,
                            max_wait_secs=300):
    trades = []
    last_exit_ts = -1
    cd_ns = cooldown_secs * 1_000_000_000
    bar_arr = bars_1m[["open","high","low","close"]].to_numpy()
    bar_ts = bars_1m.index.astype("int64").to_numpy()
    n_bars = len(bar_arr)
    for i in range(window_bars, n_bars - 1):
        net = bar_arr[i, 3] - bar_arr[i - window_bars, 0]
        if abs(net) < impulse_pts: continue
        side = 1 if net > 0 else -1
        ih = bar_arr[i - window_bars + 1:i + 1, 1].max()
        il = bar_arr[i - window_bars + 1:i + 1, 2].min()
        ir = ih - il
        if side == 1:
            pb_entry = ih - pullback_pct * ir
            stop_px = pb_entry - stop_pts; tgt_px = pb_entry + target_pts
        else:
            pb_entry = il + pullback_pct * ir
            stop_px = pb_entry + stop_pts; tgt_px = pb_entry - target_pts
        if i + 1 >= n_bars: continue
        sig_ts = int(bar_ts[i + 1])
        if last_exit_ts > 0 and sig_ts - last_exit_ts < cd_ns: continue
        trade = simulate_trade(price, ts_ns, sig_ts, side, pb_entry,
                                stop_px, tgt_px, max_hold_secs + max_wait_secs,
                                use_market_entry=False, max_wait_secs=max_wait_secs)
        if trade:
            if trade["entry_ts"] - sig_ts <= max_wait_secs * 1_000_000_000:
                trades.append(trade)
                last_exit_ts = trade["exit_ts"]
    return trades


# ============================================================================
# NR4/NR7 expansion
# ============================================================================
def strategy_nr_1mnq(bars_1m, price, ts_ns, nr_lookback, buffer,
                     stop_pts, target_pts,
                     max_hold_secs=600, cooldown_secs=120):
    trades = []
    last_exit_ts = -1
    cd_ns = cooldown_secs * 1_000_000_000
    bars = bars_1m
    highs = bars["high"].to_numpy(); lows = bars["low"].to_numpy()
    ts_arr = bars.index.astype("int64").to_numpy()
    ranges = highs - lows
    n_bars = len(bars)
    for i in range(nr_lookback, n_bars - 1):
        if ranges[i] != ranges[i - nr_lookback + 1:i + 1].min(): continue
        sig_ts = int(ts_arr[i + 1])
        if last_exit_ts > 0 and sig_ts - last_exit_ts < cd_ns: continue
        upper = float(highs[i]) + buffer
        lower = float(lows[i]) - buffer
        sig_idx = int(np.searchsorted(ts_ns, sig_ts, side="left"))
        deadline = sig_ts + 60 * 60 * 1_000_000_000
        end_idx = min(int(np.searchsorted(ts_ns, deadline, side="left")), len(price) - 1)
        if end_idx <= sig_idx: continue
        scan = price[sig_idx:end_idx + 1]
        uh = scan >= upper; lh = scan <= lower
        u_first = int(np.argmax(uh)) if uh.any() else len(scan)
        l_first = int(np.argmax(lh)) if lh.any() else len(scan)
        if u_first == len(scan) and l_first == len(scan): continue
        if u_first <= l_first:
            side = 1; entry = upper
        else:
            side = -1; entry = lower
        trig_idx = sig_idx + min(u_first, l_first)
        trig_ts = int(ts_ns[trig_idx])
        stop_px = entry - stop_pts if side == 1 else entry + stop_pts
        tgt_px = entry + target_pts if side == 1 else entry - target_pts
        trade = simulate_trade(price, ts_ns, trig_ts, side, entry,
                                stop_px, tgt_px, max_hold_secs,
                                use_market_entry=True)
        if trade:
            trades.append(trade)
            last_exit_ts = trade["exit_ts"]
    return trades


# ============================================================================
# Multi-bar momentum + cumdelta confirmation (the post-fix one)
# ============================================================================
def strategy_momentum_1mnq(bars_1m, price, ts_ns, signed_vol,
                           n_bars_required, min_move, cd_thresh,
                           stop_pts, target_pts,
                           max_hold_secs=600, cooldown_secs=60):
    trades = []
    last_exit_ts = -1
    cd_ns = cooldown_secs * 1_000_000_000
    bar_arr = bars_1m[["open","high","low","close","delta"]].to_numpy()
    bar_ts = bars_1m.index.astype("int64").to_numpy()
    n_bars = len(bar_arr)
    for i in range(n_bars_required, n_bars - 1):
        colors = np.sign(bar_arr[i - n_bars_required + 1:i + 1, 3] -
                         bar_arr[i - n_bars_required + 1:i + 1, 0])
        if not (np.all(colors == 1) or np.all(colors == -1)): continue
        side = int(colors[0])
        total = bar_arr[i, 3] - bar_arr[i - n_bars_required, 0]
        if abs(total) < min_move: continue
        recent_d = float(bar_arr[i - n_bars_required + 1:i + 1, 4].sum())
        if side == 1 and recent_d < cd_thresh: continue
        if side == -1 and recent_d > -cd_thresh: continue
        if i + 1 >= n_bars: continue
        sig_ts = int(bar_ts[i + 1])
        if last_exit_ts > 0 and sig_ts - last_exit_ts < cd_ns: continue
        entry_intent = float(bar_arr[i, 3])
        stop_px = entry_intent - stop_pts if side == 1 else entry_intent + stop_pts
        tgt_px = entry_intent + target_pts if side == 1 else entry_intent - target_pts
        trade = simulate_trade(price, ts_ns, sig_ts, side, entry_intent,
                                stop_px, tgt_px, max_hold_secs,
                                use_market_entry=True)
        if trade:
            trades.append(trade)
            last_exit_ts = trade["exit_ts"]
    return trades


def main():
    t0 = time.time()
    print("Loading tick data...")
    df = pd.read_parquet(SRC)
    period_days = (df["ts"].iloc[-1] - df["ts"].iloc[0]).total_seconds() / 86400
    price = df["price"].to_numpy(dtype=np.float32)
    volume = df["volume"].to_numpy(dtype=np.int32)
    aggressor = df["aggressor"].to_numpy(dtype=np.int8)
    ts_ns = df["ts"].astype("int64").to_numpy()
    signed_vol = (volume * aggressor).astype(np.int64)
    bars_1m = build_bars(price, ts_ns, volume, aggressor, "1min")
    print(f"  {len(price):,} ticks, {len(bars_1m):,} bars, {period_days:.0f} days ({time.time()-t0:.0f}s)\n")

    def run_and_report(label, fn, **kwargs):
        trades = fn(**kwargs)
        s = summarize(trades, period_days)
        if not s or s["n"] < 20:
            print(f"  {label}: {s['n'] if s else 0} trades (too few)")
            return
        pf = f"{s['pf']:.2f}" if s['pf'] < 99 else "inf"
        flag = " ★★★★ HITS SPEC!" if hits_spec(s) else \
               (" ★★" if s["wr"] >= 0.55 and s["ret_per_mo"] >= 2 else
                " ★ WR" if s["wr"] >= 0.55 else
                " ★" if s["ret_per_mo"] >= 1 else
                " +" if s["total"] > 0 else "")
        print(f"  {label}: n={s['n']:>4} ({s['trades_per_mo']:.0f}/mo) "
              f"WR={s['wr']*100:.1f}% PF={pf} RR={s['rr']:.2f} "
              f"$/tr=${s['per']:+.1f} DD={abs(s['maxdd_pct']):.2f}% "
              f"strk={s['max_streak']} → {s['ret_per_mo']:+.2f}%/mo{flag}")

    print("=" * 100)
    print("STRATEGY 1: PULLBACK AFTER IMPULSE (1 MNQ FIXED)")
    print("=" * 100)
    for impulse in [5, 8, 12]:
        for window in [2, 3, 5]:
            for pullback in [0.382, 0.5, 0.618]:
                for stop in [2.0, 4.0, 6.0]:
                    for tgt in [3.0, 6.0, 10.0]:
                        run_and_report(
                            f"imp={impulse} win={window}b pb={pullback} stop={stop} tgt={tgt}",
                            strategy_pullback_1mnq,
                            bars_1m=bars_1m, price=price, ts_ns=ts_ns,
                            impulse_pts=impulse, window_bars=window, pullback_pct=pullback,
                            stop_pts=stop, target_pts=tgt)
    print(f"  [elapsed {time.time()-t0:.0f}s]\n")

    print("=" * 100)
    print("STRATEGY 2: NR4/NR7 RANGE EXPANSION (1 MNQ FIXED)")
    print("=" * 100)
    for nr in [4, 7, 10]:
        for buf in [0.25, 0.5, 1.0]:
            for stop in [2.0, 4.0]:
                for tgt in [3.0, 6.0, 10.0]:
                    run_and_report(
                        f"NR{nr} buf={buf} stop={stop} tgt={tgt}",
                        strategy_nr_1mnq,
                        bars_1m=bars_1m, price=price, ts_ns=ts_ns,
                        nr_lookback=nr, buffer=buf, stop_pts=stop, target_pts=tgt)
    print(f"  [elapsed {time.time()-t0:.0f}s]\n")

    print("=" * 100)
    print("STRATEGY 3: MULTI-BAR MOMENTUM + CUMDELTA (1 MNQ FIXED)")
    print("=" * 100)
    for nbars in [2, 3, 4]:
        for mv in [3, 6, 10]:
            for cd_thresh in [100, 300, 800]:
                for stop in [2.0, 4.0]:
                    for tgt in [3.0, 6.0]:
                        run_and_report(
                            f"nbars={nbars} mv={mv}p cd={cd_thresh} stop={stop} tgt={tgt}",
                            strategy_momentum_1mnq,
                            bars_1m=bars_1m, price=price, ts_ns=ts_ns, signed_vol=signed_vol,
                            n_bars_required=nbars, min_move=mv, cd_thresh=cd_thresh,
                            stop_pts=stop, target_pts=tgt)
    print(f"  [elapsed {time.time()-t0:.0f}s]\n")


if __name__ == "__main__":
    main()
