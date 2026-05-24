"""5 complex strategies tested under ultra-realistic simulation.

ALL signals fire at the END of the bar that generates them (no look-ahead).
ALL executions use tick-precise data with 200ms latency, $1/contract comm,
NO artificial slippage (per user direction).

Strategies:
  1. Initial Balance breakout + retest
  2. VWAP extension fade with tick-delta confirmation
  3. Failed breakout reversal (false breakout)
  4. Liquidity sweep + displacement (ICT-style, properly timed)
  5. Range-then-expansion (low-volatility followed by breakout)

All run on the same 3 months of Dec 2025 — Feb 2026 tick data.
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
TARGET_RISK_USD = 50.0
MAX_CONTRACTS = 5
LATENCY_MS = 200


def _size(stop_pts):
    if stop_pts <= 0: return 1
    return max(1, min(MAX_CONTRACTS, int(TARGET_RISK_USD / (stop_pts * MNQ_PER_PT))))


def build_bars(price, ts_ns, volume, aggressor, freq="1min"):
    df = pd.DataFrame({"price": price, "volume": volume, "aggressor": aggressor,
                       "ts": pd.to_datetime(ts_ns, utc=True)})
    df["signed_vol"] = df["volume"] * df["aggressor"]
    df = df.set_index("ts")
    ohlc = df["price"].resample(freq).agg(["first", "max", "min", "last"])
    ohlc.columns = ["open", "high", "low", "close"]
    vol = df["volume"].resample(freq).sum()
    delta = df["signed_vol"].resample(freq).sum()
    out = pd.concat([ohlc, vol.rename("volume"), delta.rename("delta")], axis=1)
    return out.dropna()


def simulate_trade(price, ts_ns, signal_ts, side, entry_intent,
                   stop_px, target_px, max_hold_secs,
                   use_market_entry=True, max_wait_secs=120,
                   latency_ms=LATENCY_MS, comm=COMM_PER_CONTRACT_RT):
    """Tick-precise trade simulation. No slippage."""
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
        if side == 1: hits = scan <= entry_intent
        else: hits = scan >= entry_intent
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
        stop_hits = seg <= stop_px
        tgt_hits = seg >= target_px
    else:
        stop_hits = seg >= stop_px
        tgt_hits = seg <= target_px
    stop_first = int(np.argmax(stop_hits)) if stop_hits.any() else len(seg)
    tgt_first = int(np.argmax(tgt_hits)) if tgt_hits.any() else len(seg)

    if stop_first == len(seg) and tgt_first == len(seg):
        exit_px = float(seg[-1])
        exit_ts = int(seg_ts[-1])
        exit_reason = "timeout"
    elif stop_first <= tgt_first:
        exit_px = stop_px; exit_ts = int(seg_ts[stop_first]); exit_reason = "stop"
    else:
        exit_px = target_px; exit_ts = int(seg_ts[tgt_first]); exit_reason = "target"

    stop_pts = abs(stop_px - actual_entry_px)
    size = _size(stop_pts)
    pnl_pts = (actual_entry_px - exit_px) if side == -1 else (exit_px - actual_entry_px)
    pnl = pnl_pts * size * MNQ_PER_PT - comm * size

    return {
        "side": side, "size": size,
        "entry_ts": entry_ts, "exit_ts": exit_ts,
        "entry_px": actual_entry_px, "exit_px": exit_px,
        "exit_reason": exit_reason, "pnl_usd": float(pnl),
    }


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


# ============================================================================
# STRATEGY 1: Initial Balance breakout + retest
# ============================================================================
def strategy_ib_retest(bars_1m, price, ts_ns,
                       ib_minutes=60, retest_max_wait_secs=3600,
                       stop_pts=4.0, target_pts=6.0,
                       max_hold_secs=1800, cooldown_secs=300):
    """First IB_MINUTES of NY session sets the IB high/low. After IB closes,
    wait for breakout + retest of IB level for entry.
    """
    trades = []
    last_exit_ts = -1
    cd_ns = cooldown_secs * 1_000_000_000

    bars = bars_1m.copy()
    bars["ny_min"] = (bars.index.tz_convert("America/New_York").hour * 60 +
                      bars.index.tz_convert("America/New_York").minute)
    bars["date"] = bars.index.tz_convert("America/New_York").date

    for d, grp in bars.groupby("date"):
        ib_bars = grp[(grp["ny_min"] >= 9*60+30) & (grp["ny_min"] < 9*60+30+ib_minutes)]
        if len(ib_bars) < 5: continue
        ib_high = float(ib_bars["high"].max())
        ib_low = float(ib_bars["low"].min())
        if ib_high - ib_low < 5: continue   # need meaningful range
        post_ib = grp[grp["ny_min"] >= 9*60+30+ib_minutes]
        if post_ib.empty: continue

        breakout_up = False
        breakout_dn = False
        for ts_bar, bar in post_ib.iterrows():
            sig_ts_bar_close = int(ts_bar.value) + 60_000_000_000  # bar close = bar_open + 60s

            # check for fresh breakout (this bar broke through)
            if not breakout_up and bar["high"] > ib_high and not breakout_dn:
                breakout_up = True
                # now wait for RETEST of ib_high (limit entry there)
                entry_px = ib_high
                stop_px = entry_px - stop_pts
                target_px = entry_px + target_pts
                if last_exit_ts > 0 and sig_ts_bar_close - last_exit_ts < cd_ns:
                    continue
                trade = simulate_trade(price, ts_ns, sig_ts_bar_close, 1,
                                        entry_px, stop_px, target_px,
                                        max_hold_secs, use_market_entry=False,
                                        max_wait_secs=retest_max_wait_secs)
                if trade:
                    trades.append(trade)
                    last_exit_ts = trade["exit_ts"]
            elif not breakout_dn and bar["low"] < ib_low and not breakout_up:
                breakout_dn = True
                entry_px = ib_low
                stop_px = entry_px + stop_pts
                target_px = entry_px - target_pts
                if last_exit_ts > 0 and sig_ts_bar_close - last_exit_ts < cd_ns:
                    continue
                trade = simulate_trade(price, ts_ns, sig_ts_bar_close, -1,
                                        entry_px, stop_px, target_px,
                                        max_hold_secs, use_market_entry=False,
                                        max_wait_secs=retest_max_wait_secs)
                if trade:
                    trades.append(trade)
                    last_exit_ts = trade["exit_ts"]
    return trades


# ============================================================================
# STRATEGY 2: VWAP extension fade
# ============================================================================
def strategy_vwap_fade(bars_1m, price, ts_ns, volume, signed_vol,
                       n_std=2.0, lookback_bars=20,
                       cumdelta_confirm_thresh=200,
                       stop_pts=3.0, target_pts=4.0,
                       max_hold_secs=1200, cooldown_secs=300):
    """When current price is >n_std bar-std-devs from session VWAP, fade back.
    Filter: cumdelta over last 30s must be opposite to current price extension
    (confirms reversal flow).
    """
    trades = []
    last_exit_ts = -1
    cd_ns = cooldown_secs * 1_000_000_000

    bars = bars_1m.copy()
    bars["date"] = bars.index.tz_convert("America/New_York").date

    # Pre-compute cumulative signed vol for fast 30s window queries
    n = len(price)
    cum_signed = np.empty(n + 1, dtype=np.int64)
    cum_signed[0] = 0
    cum_signed[1:] = np.cumsum(signed_vol)
    window_ns_30 = 30 * 1_000_000_000

    for d, grp in bars.groupby("date"):
        # session VWAP
        if len(grp) < lookback_bars + 1: continue
        # rolling typical price * volume
        typical = (grp["high"] + grp["low"] + grp["close"]) / 3.0
        cum_pv = (typical * grp["volume"]).cumsum()
        cum_v = grp["volume"].cumsum()
        vwap = (cum_pv / cum_v).to_numpy()
        # std of (close - vwap) over last lookback_bars
        close = grp["close"].to_numpy()
        dev = close - vwap
        for j in range(lookback_bars, len(grp)):
            sig_dev = dev[j]
            recent_dev = dev[j - lookback_bars:j]
            sigma = float(recent_dev.std())
            if sigma <= 0: continue
            z = sig_dev / sigma
            if abs(z) < n_std: continue

            # signal fires at end of bar j → bar j+1 open
            if j + 1 >= len(grp): continue
            sig_ts = int(grp.index[j + 1].value)

            if last_exit_ts > 0 and sig_ts - last_exit_ts < cd_ns: continue

            # cumdelta filter: last 30s of ticks
            sig_idx = int(np.searchsorted(ts_ns, sig_ts, side="left"))
            window_start_ts = sig_ts - window_ns_30
            win_start_idx = int(np.searchsorted(ts_ns, window_start_ts, side="left"))
            if sig_idx <= win_start_idx: continue
            window_delta = int(cum_signed[sig_idx] - cum_signed[win_start_idx])

            side = -1 if z > 0 else 1   # fade toward VWAP
            # confirmation: delta should be opposite to current direction
            if side == -1 and window_delta > -cumdelta_confirm_thresh: continue
            if side == 1 and window_delta < cumdelta_confirm_thresh: continue

            entry_intent = float(close[j])
            if side == 1:
                stop_px = entry_intent - stop_pts
                target_px = entry_intent + target_pts
            else:
                stop_px = entry_intent + stop_pts
                target_px = entry_intent - target_pts

            trade = simulate_trade(price, ts_ns, sig_ts, side, entry_intent,
                                    stop_px, target_px, max_hold_secs,
                                    use_market_entry=True)
            if trade:
                trades.append(trade)
                last_exit_ts = trade["exit_ts"]
    return trades


# ============================================================================
# STRATEGY 3: Failed breakout reversal
# ============================================================================
def strategy_failed_breakout(bars_1m, price, ts_ns,
                              lookback_bars=30,
                              max_recapture_bars=5,
                              stop_pts=3.0, target_pts=5.0,
                              max_hold_secs=900, cooldown_secs=120):
    """A new high (or low) of the last `lookback_bars` is formed, then within
    `max_recapture_bars` price closes back inside the prior range. Fade.
    """
    trades = []
    last_exit_ts = -1
    cd_ns = cooldown_secs * 1_000_000_000

    bars = bars_1m
    highs = bars["high"].to_numpy()
    lows = bars["low"].to_numpy()
    closes = bars["close"].to_numpy()
    ts_arr = bars.index.astype("int64").to_numpy()
    n_bars = len(bars)

    for i in range(lookback_bars + max_recapture_bars, n_bars - 1):
        # Look at bar i — did it break a new high/low of prior lookback_bars?
        prior_high = highs[i - lookback_bars - 1:i].max()
        prior_low = lows[i - lookback_bars - 1:i].min()

        # Check: did some bar in (i-max_recap to i) break out then close back?
        # We use bar i's data — we know its close at bar i close
        breakout_bar = -1
        breakout_side = 0
        for k in range(max_recapture_bars):
            j = i - max_recapture_bars + k
            if j < lookback_bars: continue
            if highs[j] > prior_high and closes[i] < prior_high:
                breakout_bar = j; breakout_side = 1; break
            if lows[j] < prior_low and closes[i] > prior_low:
                breakout_bar = j; breakout_side = -1; break

        if breakout_bar < 0: continue

        # Signal: fade in direction of recapture (opposite to breakout)
        # Signal time = bar i close = bar i+1 start
        sig_ts = int(ts_arr[i + 1])
        if last_exit_ts > 0 and sig_ts - last_exit_ts < cd_ns: continue

        side = -1 if breakout_side == 1 else 1
        entry_intent = float(closes[i])
        if side == 1:
            stop_px = entry_intent - stop_pts
            target_px = entry_intent + target_pts
        else:
            stop_px = entry_intent + stop_pts
            target_px = entry_intent - target_pts

        trade = simulate_trade(price, ts_ns, sig_ts, side, entry_intent,
                                stop_px, target_px, max_hold_secs,
                                use_market_entry=True)
        if trade:
            trades.append(trade)
            last_exit_ts = trade["exit_ts"]
    return trades


# ============================================================================
# STRATEGY 4: Range-then-expansion (NR4 + breakout)
# ============================================================================
def strategy_nr_expansion(bars_1m, price, ts_ns,
                           nr_lookback=4,
                           breakout_buffer=0.5,
                           stop_pts=3.0, target_pts=5.0,
                           max_hold_secs=600, cooldown_secs=120):
    """When bar i is the narrowest range of last NR bars, place stop orders
    just outside its high and low. Take whichever triggers.
    """
    trades = []
    last_exit_ts = -1
    cd_ns = cooldown_secs * 1_000_000_000

    bars = bars_1m
    highs = bars["high"].to_numpy()
    lows = bars["low"].to_numpy()
    closes = bars["close"].to_numpy()
    ts_arr = bars.index.astype("int64").to_numpy()
    ranges = highs - lows
    n_bars = len(bars)

    for i in range(nr_lookback, n_bars - 1):
        # bar i is narrowest of last nr_lookback bars?
        if ranges[i] != ranges[i - nr_lookback + 1:i + 1].min():
            continue
        # Setup defined at bar i close → fires from bar i+1 start
        sig_ts = int(ts_arr[i + 1])
        if last_exit_ts > 0 and sig_ts - last_exit_ts < cd_ns: continue

        upper_break = float(highs[i]) + breakout_buffer
        lower_break = float(lows[i]) - breakout_buffer

        # Walk forward through ticks to find which breaks first
        sig_idx = int(np.searchsorted(ts_ns, sig_ts, side="left"))
        # look up to next 60 minutes for breakout
        deadline = sig_ts + 60 * 60 * 1_000_000_000
        end_idx = min(int(np.searchsorted(ts_ns, deadline, side="left")), len(price) - 1)
        if end_idx <= sig_idx: continue

        scan = price[sig_idx:end_idx + 1]
        upper_hits = scan >= upper_break
        lower_hits = scan <= lower_break
        u_first = int(np.argmax(upper_hits)) if upper_hits.any() else len(scan)
        l_first = int(np.argmax(lower_hits)) if lower_hits.any() else len(scan)

        if u_first == len(scan) and l_first == len(scan): continue
        if u_first <= l_first:
            side = 1; entry_intent = upper_break
        else:
            side = -1; entry_intent = lower_break

        # entry time = the moment of breakout
        triggered_idx = sig_idx + min(u_first, l_first)
        triggered_ts = int(ts_ns[triggered_idx])

        if side == 1:
            stop_px = entry_intent - stop_pts
            target_px = entry_intent + target_pts
        else:
            stop_px = entry_intent + stop_pts
            target_px = entry_intent - target_pts

        trade = simulate_trade(price, ts_ns, triggered_ts, side,
                                entry_intent, stop_px, target_px,
                                max_hold_secs, use_market_entry=True)
        if trade:
            trades.append(trade)
            last_exit_ts = trade["exit_ts"]
    return trades


# ============================================================================
# STRATEGY 5: Bar-volume-z + delta-confirm momentum
# ============================================================================
def strategy_volume_delta_momentum(bars_1m, price, ts_ns,
                                   volume_z_min=2.0,
                                   delta_z_min=2.0,
                                   lookback=30,
                                   stop_pts=4.0, target_pts=6.0,
                                   max_hold_secs=600, cooldown_secs=120):
    """Bar with unusually high volume AND unusually high delta in one direction
    signals institutional participation. Enter in direction of delta.
    """
    trades = []
    last_exit_ts = -1
    cd_ns = cooldown_secs * 1_000_000_000

    bars = bars_1m
    vols = bars["volume"].to_numpy(dtype=np.float32)
    deltas = bars["delta"].to_numpy(dtype=np.float32)
    closes = bars["close"].to_numpy()
    ts_arr = bars.index.astype("int64").to_numpy()
    n_bars = len(bars)

    for i in range(lookback, n_bars - 1):
        # Use ONLY bars before i (no current-bar info in stats!)
        prev_vol = vols[i - lookback:i]
        prev_delta = deltas[i - lookback:i]
        vol_mean = prev_vol.mean(); vol_std = max(prev_vol.std(), 1.0)
        delta_mean = prev_delta.mean(); delta_std = max(prev_delta.std(), 1.0)
        vol_z = (vols[i] - vol_mean) / vol_std
        delta_z = (deltas[i] - delta_mean) / delta_std

        if vol_z < volume_z_min: continue
        if abs(delta_z) < delta_z_min: continue

        # Signal fires at bar i close = bar i+1 start
        sig_ts = int(ts_arr[i + 1])
        if last_exit_ts > 0 and sig_ts - last_exit_ts < cd_ns: continue
        side = 1 if delta_z > 0 else -1
        entry_intent = float(closes[i])
        if side == 1:
            stop_px = entry_intent - stop_pts
            target_px = entry_intent + target_pts
        else:
            stop_px = entry_intent + stop_pts
            target_px = entry_intent - target_pts

        trade = simulate_trade(price, ts_ns, sig_ts, side, entry_intent,
                                stop_px, target_px, max_hold_secs,
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
    print(f"  {len(price):,} ticks, {len(bars_1m):,} 1-min bars, "
          f"{period_days:.0f} days  ({time.time()-t0:.0f}s)\n")

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
              f"$/tr=${s['per']:+.0f} DD={abs(s['maxdd_pct']):.1f}% "
              f"strk={s['max_streak']} → {s['ret_per_mo']:+.2f}%/mo{flag}")

    # STRATEGY 1: IB retest
    print("=" * 100)
    print("STRATEGY 1: INITIAL BALANCE BREAKOUT + RETEST")
    print("=" * 100)
    for ib_min in [30, 45, 60]:
        for stop in [2.0, 4.0, 6.0]:
            for tgt in [3.0, 6.0, 10.0]:
                label = f"IB={ib_min}m stop={stop} tgt={tgt}"
                run_and_report(label, strategy_ib_retest,
                               bars_1m=bars_1m, price=price, ts_ns=ts_ns,
                               ib_minutes=ib_min, stop_pts=stop, target_pts=tgt)
    print(f"  [elapsed {time.time()-t0:.0f}s]\n")

    # STRATEGY 2: VWAP fade
    print("=" * 100)
    print("STRATEGY 2: VWAP EXTENSION FADE WITH DELTA CONFIRMATION")
    print("=" * 100)
    for nstd in [1.5, 2.0, 2.5]:
        for cd_thresh in [100, 300, 500]:
            for stop in [2.0, 4.0]:
                for tgt in [3.0, 6.0]:
                    label = f"nstd={nstd} cd={cd_thresh} stop={stop} tgt={tgt}"
                    run_and_report(label, strategy_vwap_fade,
                                   bars_1m=bars_1m, price=price, ts_ns=ts_ns,
                                   volume=volume, signed_vol=signed_vol,
                                   n_std=nstd, cumdelta_confirm_thresh=cd_thresh,
                                   stop_pts=stop, target_pts=tgt)
    print(f"  [elapsed {time.time()-t0:.0f}s]\n")

    # STRATEGY 3: Failed breakout
    print("=" * 100)
    print("STRATEGY 3: FAILED BREAKOUT REVERSAL")
    print("=" * 100)
    for lb in [20, 30, 60]:
        for recap in [3, 5, 10]:
            for stop in [2.0, 4.0]:
                for tgt in [3.0, 6.0]:
                    label = f"lb={lb} recap={recap}b stop={stop} tgt={tgt}"
                    run_and_report(label, strategy_failed_breakout,
                                   bars_1m=bars_1m, price=price, ts_ns=ts_ns,
                                   lookback_bars=lb, max_recapture_bars=recap,
                                   stop_pts=stop, target_pts=tgt)
    print(f"  [elapsed {time.time()-t0:.0f}s]\n")

    # STRATEGY 4: NR expansion
    print("=" * 100)
    print("STRATEGY 4: NR4/NR7 RANGE-THEN-EXPANSION")
    print("=" * 100)
    for nr in [4, 7, 10]:
        for buf in [0.25, 0.5, 1.0]:
            for stop in [2.0, 4.0]:
                for tgt in [3.0, 6.0]:
                    label = f"NR{nr} buf={buf} stop={stop} tgt={tgt}"
                    run_and_report(label, strategy_nr_expansion,
                                   bars_1m=bars_1m, price=price, ts_ns=ts_ns,
                                   nr_lookback=nr, breakout_buffer=buf,
                                   stop_pts=stop, target_pts=tgt)
    print(f"  [elapsed {time.time()-t0:.0f}s]\n")

    # STRATEGY 5: Volume + delta z-momentum
    print("=" * 100)
    print("STRATEGY 5: VOLUME-Z + DELTA-Z MOMENTUM")
    print("=" * 100)
    for vz in [1.5, 2.0, 2.5, 3.0]:
        for dz in [1.5, 2.0, 2.5]:
            for stop in [2.0, 4.0]:
                for tgt in [3.0, 6.0]:
                    label = f"vz={vz} dz={dz} stop={stop} tgt={tgt}"
                    run_and_report(label, strategy_volume_delta_momentum,
                                   bars_1m=bars_1m, price=price, ts_ns=ts_ns,
                                   volume_z_min=vz, delta_z_min=dz,
                                   stop_pts=stop, target_pts=tgt)
    print(f"  [elapsed {time.time()-t0:.0f}s]\n")


if __name__ == "__main__":
    main()
