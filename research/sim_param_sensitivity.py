"""Parameter sensitivity sweep — run the pullback sim across +/-10% on each
key parameter to measure strategy robustness. Slow (~10 min): N sim runs.

Output: prints a table; also writes JSON for the analysis report.
"""
from __future__ import annotations
import json, time
import numpy as np
import pandas as pd
from pathlib import Path
import sys
sys.path.insert(0, "/home/user/HFTBot")

# Import the strategy params - we'll monkey-patch them per scenario
import bot.pullback_strategy as ps

SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")
OUT_JSON = Path("/home/user/HFTBot/reports/param_sensitivity.json")
STARTING_BALANCE = 50_000.0
MNQ_PER_PT = 2.0
LATENCY_MS = 200
N_MNQ = 2
ENTRY_SLIP = 0.0
ADVERSE_SLIP = 0.25
COMM_RT = 0.74

# Each scenario: (label, override_dict_for_strategy_params)
BASELINE = {
    "IMPULSE_PTS": 5.0, "IMPULSE_WINDOW_BARS": 3,
    "PULLBACK_PCT": 0.618, "STOP_PTS": 6.0, "TARGET_PTS": 10.0,
}
SCENARIOS = [
    ("BASELINE",                BASELINE),
    ("impulse -1 (4pt)",        {**BASELINE, "IMPULSE_PTS": 4.0}),
    ("impulse +1 (6pt)",        {**BASELINE, "IMPULSE_PTS": 6.0}),
    ("impulse +2 (7pt)",        {**BASELINE, "IMPULSE_PTS": 7.0}),
    ("retrace 0.5",             {**BASELINE, "PULLBACK_PCT": 0.5}),
    ("retrace 0.786",           {**BASELINE, "PULLBACK_PCT": 0.786}),
    ("stop -1 (5pt)",           {**BASELINE, "STOP_PTS": 5.0}),
    ("stop +1 (7pt)",           {**BASELINE, "STOP_PTS": 7.0}),
    ("target -1 (9pt)",         {**BASELINE, "TARGET_PTS": 9.0}),
    ("target +2 (12pt)",        {**BASELINE, "TARGET_PTS": 12.0}),
    ("window 2 bars",           {**BASELINE, "IMPULSE_WINDOW_BARS": 2}),
    ("window 4 bars",           {**BASELINE, "IMPULSE_WINDOW_BARS": 4}),
]


def build_1m_bars(price, ts_ns, volume):
    df = pd.DataFrame({"price": price, "volume": volume,
                       "ts": pd.to_datetime(ts_ns, utc=True)})
    df = df.set_index("ts")
    ohlc = df["price"].resample("1min").agg(["first", "max", "min", "last"])
    ohlc.columns = ["open", "high", "low", "close"]
    vol = df["volume"].resample("1min").sum()
    return pd.concat([ohlc, vol.rename("volume")], axis=1).dropna()


def run_sim(price, ts_ns, bars_1m, params):
    # Apply param overrides
    for k, v in params.items():
        setattr(ps, k, v)
    bar_ts = bars_1m.index.astype("int64").to_numpy()
    cooldown_ns = ps.COOLDOWN_SECS * 1_000_000_000
    latency_ns = LATENCY_MS * 1_000_000
    max_hold_ns = ps.MAX_HOLD_SECS * 1_000_000_000
    max_wait_ns = ps.MAX_WAIT_SECS * 1_000_000_000
    min_hold_ns = ps.MIN_TARGET_HOLD_SECONDS * 1_000_000_000

    trades = []
    used_keys = set()
    last_exit_ts = -1
    window_bars = params["IMPULSE_WINDOW_BARS"]

    for i in range(window_bars, len(bars_1m) - 1):
        sig_ts = int(bar_ts[i + 1])
        bars_at_i = bars_1m.iloc[:i + 1]
        setup = ps.detect_pullback_setup(bars_at_i,
            pd.Timestamp(sig_ts, tz="UTC").to_pydatetime())
        if setup is None: continue
        key = ps._setup_key(setup)
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
        trades.append(round(float(pnl_usd), 2))
        used_keys.add(key)
        last_exit_ts = exit_ts
    return trades


def summarize(trades, period_days):
    if not trades: return {"n": 0}
    pnls = np.array(trades)
    wins = int((pnls > 0).sum())
    cum = pnls.cumsum()
    maxdd = float((cum - np.maximum.accumulate(cum)).min())
    gw = float(pnls[pnls > 0].sum()); gl = float(abs(pnls[pnls < 0].sum()))
    avg_w = float(pnls[pnls > 0].mean()) if wins else 0
    avg_l = float(pnls[pnls < 0].mean()) if (len(pnls) - wins) else 0
    months = period_days / 30.44
    total = float(pnls.sum())
    return {
        "n": len(pnls), "wr": round(wins/len(pnls)*100, 1),
        "total": round(total, 0), "ret_mo": round(total/STARTING_BALANCE*100/months, 2),
        "dd_usd": round(maxdd, 0), "dd_pct": round(abs(maxdd/STARTING_BALANCE*100), 2),
        "pf": round(gw/gl, 3) if gl > 0 else 999,
        "rr": round(abs(avg_w/avg_l), 2) if avg_l else 0,
        "trades_per_mo": round(len(pnls)/months, 0),
    }


def main():
    t0 = time.time()
    print("Loading tick data...")
    df = pd.read_parquet(SRC)
    period_days = (df["ts"].iloc[-1] - df["ts"].iloc[0]).total_seconds() / 86400
    price = df["price"].to_numpy(dtype=np.float32)
    volume = df["volume"].to_numpy(dtype=np.int32)
    ts_ns = df["ts"].astype("int64").to_numpy()
    bars_1m = build_1m_bars(price, ts_ns, volume)
    print(f"  ready ({time.time()-t0:.0f}s)\n")

    print(f"{'Scenario':<28} {'Trades':>8}{'WR':>7}{'RR':>6}{'PF':>6}"
          f"{'Ret/mo':>10}{'DD$':>10}{'DD%':>7}{'Tr/mo':>8}")
    results = {}
    for name, params in SCENARIOS:
        ts = time.time()
        trades = run_sim(price, ts_ns, bars_1m, params)
        s = summarize(trades, period_days)
        results[name] = {"params": {k: v for k, v in params.items()}, **s}
        dt = time.time() - ts
        print(f"{name:<28} {s.get('n',0):>8}{s.get('wr',0):>6.1f}%{s.get('rr',0):>6.2f}"
              f"{s.get('pf',0):>6.2f}{s.get('ret_mo',0):>+9.2f}%"
              f"{s.get('dd_usd',0):>+10,.0f}{s.get('dd_pct',0):>6.2f}%"
              f"{s.get('trades_per_mo',0):>8.0f}  [{dt:.0f}s]")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nWrote {OUT_JSON} ({time.time()-t0:.0f}s total)")


if __name__ == "__main__":
    main()
