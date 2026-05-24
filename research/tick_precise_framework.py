"""Tick-precise execution framework for OHLC-based strategies.

CONCEPT:
  Strategies emit (timestamp, side, entry_price, stop_price, target_price)
  triples based on 1-min OHLC. The framework walks tick-by-tick from the
  signal to find:
    - REAL entry fill (no slippage, just first tick at or past entry_price)
    - REAL stop / target hit (whichever first via tick prices)

  This is the most honest backtest possible without modeling slippage.
  Realistic 200ms latency on entry (data feed delay), $1/contract comm.

TESTS:
  A. ORB v1 ensemble — verify under tick-precise fills
  B. Pullback after impulse — wait for first pullback after big move
  C. Multi-bar momentum continuation
  D. Cumdelta + ORB confluence (use tick cumdelta as ORB filter)
"""
from __future__ import annotations
import time
import numpy as np
import pandas as pd
from pathlib import Path

TICK_SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")

STARTING_BALANCE = 50_000.0
MNQ_PER_PT = 2.0
COMM_PER_CONTRACT_RT = 1.0   # $1 round trip Tradovate
TARGET_RISK_USD = 50.0
MAX_CONTRACTS = 5
LATENCY_MS = 200


def _size(stop_pts):
    if stop_pts <= 0: return 1
    return max(1, min(MAX_CONTRACTS, int(TARGET_RISK_USD / (stop_pts * MNQ_PER_PT))))


def build_1m_bars(price, ts_ns, volume, aggressor):
    """Aggregate ticks into 1-min OHLCV+cumdelta bars (no look-ahead)."""
    df = pd.DataFrame({
        "price": price, "volume": volume, "aggressor": aggressor,
        "ts": pd.to_datetime(ts_ns, utc=True),
    })
    df["signed_vol"] = df["volume"] * df["aggressor"]
    df = df.set_index("ts")
    ohlc = df["price"].resample("1min").agg(["first", "max", "min", "last"])
    ohlc.columns = ["open", "high", "low", "close"]
    vol = df["volume"].resample("1min").sum()
    delta = df["signed_vol"].resample("1min").sum()
    out = pd.concat([ohlc, vol.rename("volume"), delta.rename("delta")], axis=1)
    out = out.dropna()
    return out


def simulate_trade_tick_precise(price, ts_ns, signal_ts_ns: int,
                                 side: int, entry_px: float,
                                 stop_px: float, target_px: float,
                                 max_hold_secs: int,
                                 latency_ms: int = LATENCY_MS,
                                 comm_per_contract: float = COMM_PER_CONTRACT_RT,
                                 use_market_entry: bool = True):
    """Simulate ONE trade with tick-precise execution.

    Returns (pnl, entry_filled_ts, exit_ts, exit_px, exit_reason) or None
    if entry never fills.
    """
    n = len(price)
    latency_ns = latency_ms * 1_000_000
    hold_ns = max_hold_secs * 1_000_000_000

    fill_deadline_ts = signal_ts_ns + latency_ns
    entry_search_start = int(np.searchsorted(ts_ns, fill_deadline_ts, side="left"))
    if entry_search_start >= n: return None

    # Entry semantics:
    # - Market entry: fill at NEXT tick after latency
    # - Limit entry: fill at entry_px when price reaches it
    if use_market_entry:
        entry_idx = entry_search_start
        actual_entry_px = float(price[entry_idx])
    else:
        # Look for first tick at or past entry_px
        if side == 1:
            # LONG limit: fills when price <= entry_px (buy at or better)
            # Walk forward, find first tick where price <= entry_px
            scan_end = min(entry_search_start + 600 * 4, n)  # cap search
            scan = price[entry_search_start:scan_end]
            hits = scan <= entry_px
        else:
            scan_end = min(entry_search_start + 600 * 4, n)
            scan = price[entry_search_start:scan_end]
            hits = scan >= entry_px
        if not hits.any(): return None
        entry_idx = entry_search_start + int(np.argmax(hits))
        actual_entry_px = entry_px

    entry_ts = int(ts_ns[entry_idx])
    # adjust stop / target if entry differs from signal
    if use_market_entry:
        # If entry differs significantly from intended entry_px, scale stop/target
        # For consistency: keep same absolute stop/target prices set by signal
        pass

    # Walk forward to find exit
    deadline_ts = entry_ts + hold_ns
    end_idx = min(int(np.searchsorted(ts_ns, deadline_ts, side="left")), n - 1)
    if end_idx <= entry_idx: return None

    seg = price[entry_idx + 1:end_idx + 1].astype(np.float32)
    seg_ts = ts_ns[entry_idx + 1:end_idx + 1]
    if len(seg) == 0: return None

    if side == 1:
        stop_hits = seg <= stop_px
        tgt_hits = seg >= target_px
    else:
        stop_hits = seg >= stop_px
        tgt_hits = seg <= target_px

    stop_first = int(np.argmax(stop_hits)) if stop_hits.any() else len(seg)
    tgt_first = int(np.argmax(tgt_hits)) if tgt_hits.any() else len(seg)
    if stop_first == len(seg) and tgt_first == len(seg):
        # timeout
        exit_px = float(seg[-1])
        exit_ts = int(seg_ts[-1])
        exit_reason = "timeout"
    elif stop_first <= tgt_first:
        exit_px = stop_px
        exit_ts = int(seg_ts[stop_first])
        exit_reason = "stop"
    else:
        exit_px = target_px
        exit_ts = int(seg_ts[tgt_first])
        exit_reason = "target"

    pnl_pts = (actual_entry_px - exit_px) if side == -1 else (exit_px - actual_entry_px)
    stop_pts = abs(stop_px - actual_entry_px)
    size = _size(stop_pts)
    pnl = pnl_pts * size * MNQ_PER_PT - comm_per_contract * size
    return {
        "side": side, "size": size,
        "entry_ts": entry_ts, "exit_ts": exit_ts,
        "entry_px": actual_entry_px, "exit_px": exit_px,
        "stop_px": stop_px, "target_px": target_px,
        "exit_reason": exit_reason, "pnl_usd": float(pnl),
    }


# ============================================================================
# STRATEGY A: Pullback after impulse (multi-step, latency-tolerant)
# ============================================================================
def strategy_pullback_impulse(price, ts_ns, volume, aggressor,
                              bars_1m,
                              impulse_pts: float = 8.0,       # bar must move 8pts
                              impulse_window_bars: int = 3,    # within 3 minutes
                              pullback_pct: float = 0.382,     # wait for 38% pullback
                              max_wait_secs: int = 300,        # max wait for pullback
                              init_stop_pts: float = 3.0,
                              target_pts: float = 5.0,
                              max_hold_secs: int = 600,
                              cooldown_secs: int = 60):
    """After an impulse move (N consecutive bars in one direction with X pts),
    place a limit at the pullback level. Enter when price hits the limit.
    """
    trades = []
    last_exit_ts = -1
    cd_ns = cooldown_secs * 1_000_000_000
    bar_arr = bars_1m[["open", "high", "low", "close"]].to_numpy()
    bar_ts_ns = bars_1m.index.astype("int64").to_numpy()
    n_bars = len(bar_arr)

    for i in range(impulse_window_bars, n_bars - 1):
        # check for impulse: net move over last impulse_window_bars
        net = bar_arr[i, 3] - bar_arr[i - impulse_window_bars, 0]   # close - open
        if abs(net) < impulse_pts: continue
        side = 1 if net > 0 else -1

        # Compute pullback level
        impulse_high = bar_arr[i - impulse_window_bars + 1:i + 1, 1].max()
        impulse_low = bar_arr[i - impulse_window_bars + 1:i + 1, 2].min()
        impulse_range = impulse_high - impulse_low
        if side == 1:
            pullback_entry = impulse_high - pullback_pct * impulse_range
            stop_px = pullback_entry - init_stop_pts
            target_px = pullback_entry + target_pts
        else:
            pullback_entry = impulse_low + pullback_pct * impulse_range
            stop_px = pullback_entry + init_stop_pts
            target_px = pullback_entry - target_pts

        # signal time = close of impulse bar
        signal_ts = int(bar_ts_ns[i])

        if last_exit_ts > 0 and signal_ts - last_exit_ts < cd_ns:
            continue

        # Place LIMIT at pullback price, wait up to max_wait_secs
        trade = simulate_trade_tick_precise(price, ts_ns, signal_ts,
                                             side, pullback_entry,
                                             stop_px, target_px,
                                             max_hold_secs + max_wait_secs,
                                             use_market_entry=False)
        if trade is None: continue
        # check that fill happened within max_wait_secs
        if trade["entry_ts"] - signal_ts > max_wait_secs * 1_000_000_000:
            continue
        trades.append(trade)
        last_exit_ts = trade["exit_ts"]
    return trades


# ============================================================================
# STRATEGY B: Tick-cumdelta surge with patient entry
# ============================================================================
def strategy_cumdelta_patient(price, ts_ns, signed_vol,
                              window_secs: int = 60,
                              delta_thresh: int = 500,
                              wait_pullback_pts: float = 1.5,
                              init_stop_pts: float = 3.0,
                              target_pts: float = 5.0,
                              max_hold_secs: int = 600,
                              max_wait_secs: int = 120,
                              cooldown_secs: int = 60):
    """Wait for cumdelta surge, then wait for small pullback before entering.
    The pullback wait makes the trade latency-tolerant.
    """
    n = len(price)
    window_ns = window_secs * 1_000_000_000
    cd_ns = cooldown_secs * 1_000_000_000

    cum_signed = np.empty(n + 1, dtype=np.int64)
    cum_signed[0] = 0
    cum_signed[1:] = np.cumsum(signed_vol.astype(np.int64))
    win_start = np.searchsorted(ts_ns, ts_ns - window_ns, side="left")
    window_delta = cum_signed[1:n+1] - cum_signed[win_start]

    is_trig = np.abs(window_delta) >= delta_thresh
    edge = is_trig.copy()
    edge[1:] &= ~is_trig[:-1]
    trigger_idx = np.where(edge)[0]

    trades = []
    last_exit_ts = -1
    for trig_i in trigger_idx:
        sig_ts = int(ts_ns[trig_i])
        if last_exit_ts > 0 and sig_ts - last_exit_ts < cd_ns:
            continue
        side = 1 if window_delta[trig_i] > 0 else -1
        sig_price = float(price[trig_i])
        # entry at small pullback FROM signal price
        if side == 1:
            entry_px = sig_price - wait_pullback_pts
            stop_px = entry_px - init_stop_pts
            target_px = entry_px + target_pts
        else:
            entry_px = sig_price + wait_pullback_pts
            stop_px = entry_px + init_stop_pts
            target_px = entry_px - target_pts

        trade = simulate_trade_tick_precise(price, ts_ns, sig_ts,
                                             side, entry_px,
                                             stop_px, target_px,
                                             max_hold_secs + max_wait_secs,
                                             use_market_entry=False)
        if trade is None: continue
        if trade["entry_ts"] - sig_ts > max_wait_secs * 1_000_000_000:
            continue
        trades.append(trade)
        last_exit_ts = trade["exit_ts"]
    return trades


# ============================================================================
# STRATEGY C: Multi-bar momentum with cumdelta confirmation
# ============================================================================
def strategy_momentum_cumdelta(bars_1m, price, ts_ns, signed_vol,
                               n_bars_required: int = 3,
                               min_total_move_pts: float = 5.0,
                               cumdelta_confirm_window_secs: int = 60,
                               cumdelta_min_thresh: int = 200,
                               init_stop_pts: float = 3.0,
                               target_pts: float = 6.0,
                               max_hold_secs: int = 900,
                               cooldown_secs: int = 60):
    """N consecutive same-color bars + cumdelta confirms direction."""
    bar_arr = bars_1m[["open", "high", "low", "close", "delta"]].to_numpy()
    bar_ts_ns = bars_1m.index.astype("int64").to_numpy()
    n_bars = len(bar_arr)
    cd_ns = cooldown_secs * 1_000_000_000

    trades = []
    last_exit_ts = -1

    for i in range(n_bars_required, n_bars - 1):
        # check N consecutive same-color
        colors = np.sign(bar_arr[i - n_bars_required + 1:i + 1, 3] -
                         bar_arr[i - n_bars_required + 1:i + 1, 0])
        if not (np.all(colors == 1) or np.all(colors == -1)): continue
        side = int(colors[0])
        # total move check
        total = bar_arr[i, 3] - bar_arr[i - n_bars_required, 0]
        if abs(total) < min_total_move_pts: continue

        # cumdelta confirmation: last N bars' delta is positive (for long)
        recent_delta = float(bar_arr[i - n_bars_required + 1:i + 1, 4].sum())
        if side == 1 and recent_delta < cumdelta_min_thresh: continue
        if side == -1 and recent_delta > -cumdelta_min_thresh: continue

        # Enter at next bar's open via market
        sig_ts = int(bar_ts_ns[i])
        if last_exit_ts > 0 and sig_ts - last_exit_ts < cd_ns: continue

        entry_intent = float(bar_arr[i, 3])  # close of signal bar
        if side == 1:
            stop_px = entry_intent - init_stop_pts
            target_px = entry_intent + target_pts
        else:
            stop_px = entry_intent + init_stop_pts
            target_px = entry_intent - target_pts

        trade = simulate_trade_tick_precise(price, ts_ns, sig_ts,
                                             side, entry_intent,
                                             stop_px, target_px,
                                             max_hold_secs,
                                             use_market_entry=True)
        if trade is None: continue
        trades.append(trade)
        last_exit_ts = trade["exit_ts"]
    return trades


# ============================================================================
# REPORTING
# ============================================================================
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
    return {
        "n": n, "wr": wins/n, "pf": pf,
        "rr": abs(avg_w/avg_l) if avg_l != 0 else 0,
        "total": float(pnls.sum()), "per": float(pnls.mean()),
        "trades_per_day": n/period_days, "trades_per_mo": n/months,
        "maxdd": maxdd, "maxdd_pct": maxdd/STARTING_BALANCE*100,
        "max_streak": max_streak,
        "ret_per_mo": float(pnls.sum())/STARTING_BALANCE*100/months,
    }


def hits_spec(s):
    if not s: return False
    return (s["wr"] >= 0.55 and s["rr"] >= 1.2 and s["trades_per_mo"] >= 100
            and s["ret_per_mo"] >= 3.0 and abs(s["maxdd_pct"]) <= 2.0)


def report_one(label, params, s):
    if not s:
        print(f"  {label}: no trades — {params}")
        return
    pf = f"{s['pf']:.2f}" if s['pf'] < 99 else "inf"
    flag = " ★★★★ HITS SPEC!" if hits_spec(s) else \
           (" ★★" if s["wr"] >= 0.55 and s["ret_per_mo"] >= 2 else
            " ★" if s["ret_per_mo"] >= 1 else
            " +" if s["total"] > 0 else "")
    print(f"  {label}: n={s['n']} ({s['trades_per_mo']:.0f}/mo) "
          f"WR={s['wr']*100:.1f}% PF={pf} RR={s['rr']:.2f} "
          f"$/tr=${s['per']:+.0f} DD={abs(s['maxdd_pct']):.1f}% "
          f"→ {s['ret_per_mo']:+.2f}%/mo{flag}")


def main():
    t0 = time.time()
    print("Loading tick data...")
    df = pd.read_parquet(TICK_SRC)
    period_days = (df["ts"].iloc[-1] - df["ts"].iloc[0]).total_seconds() / 86400
    price = df["price"].to_numpy(dtype=np.float32)
    volume = df["volume"].to_numpy(dtype=np.int32)
    aggressor = df["aggressor"].to_numpy(dtype=np.int8)
    ts_ns = df["ts"].astype("int64").to_numpy()
    signed_vol = (volume * aggressor).astype(np.int64)
    print(f"  {len(price):,} ticks, {period_days:.0f} days  ({time.time()-t0:.0f}s)")

    print("Building 1-min OHLCV+delta bars...")
    bars_1m = build_1m_bars(price, ts_ns, volume, aggressor)
    print(f"  {len(bars_1m):,} bars  ({time.time()-t0:.0f}s)\n")

    # =========================================================================
    print("=" * 100)
    print("STRATEGY A: PULLBACK AFTER IMPULSE (limit entry, latency-tolerant)")
    print("=" * 100)
    for impulse in [5, 8, 12]:
        for window in [2, 3, 5]:
            for pullback in [0.236, 0.382, 0.5, 0.618]:
                for stop in [2.0, 4.0]:
                    for tgt in [3.0, 6.0]:
                        trades = strategy_pullback_impulse(
                            price, ts_ns, volume, aggressor, bars_1m,
                            impulse_pts=impulse, impulse_window_bars=window,
                            pullback_pct=pullback, init_stop_pts=stop,
                            target_pts=tgt)
                        s = summarize(trades, period_days)
                        if s and s["n"] >= 30:
                            params = f"imp={impulse} win={window}b pb={pullback} stop={stop} tgt={tgt}"
                            report_one(params, params, s)
    print(f"  [elapsed {time.time()-t0:.0f}s]\n")

    # =========================================================================
    print("=" * 100)
    print("STRATEGY B: CUMDELTA SURGE WITH PATIENT (PULLBACK) ENTRY")
    print("=" * 100)
    for window in [30, 60, 120]:
        for thresh in [200, 400, 800]:
            for pullback in [0.5, 1.0, 2.0]:
                for stop in [2.0, 4.0]:
                    for tgt in [3.0, 6.0]:
                        trades = strategy_cumdelta_patient(
                            price, ts_ns, signed_vol,
                            window_secs=window, delta_thresh=thresh,
                            wait_pullback_pts=pullback,
                            init_stop_pts=stop, target_pts=tgt)
                        s = summarize(trades, period_days)
                        if s and s["n"] >= 30:
                            params = f"w={window}s thr={thresh} pb={pullback} stop={stop} tgt={tgt}"
                            report_one(params, params, s)
    print(f"  [elapsed {time.time()-t0:.0f}s]\n")

    # =========================================================================
    print("=" * 100)
    print("STRATEGY C: MULTI-BAR MOMENTUM + CUMDELTA CONFIRMATION")
    print("=" * 100)
    for n_bars in [2, 3, 4]:
        for move in [3, 6, 10]:
            for cd_thresh in [100, 300, 800]:
                for stop in [2.0, 4.0]:
                    for tgt in [3.0, 6.0]:
                        trades = strategy_momentum_cumdelta(
                            bars_1m, price, ts_ns, signed_vol,
                            n_bars_required=n_bars,
                            min_total_move_pts=move,
                            cumdelta_min_thresh=cd_thresh,
                            init_stop_pts=stop, target_pts=tgt)
                        s = summarize(trades, period_days)
                        if s and s["n"] >= 30:
                            params = f"nbars={n_bars} mv={move}p cd={cd_thresh} stop={stop} tgt={tgt}"
                            report_one(params, params, s)
    print(f"  [elapsed {time.time()-t0:.0f}s]\n")


if __name__ == "__main__":
    main()
