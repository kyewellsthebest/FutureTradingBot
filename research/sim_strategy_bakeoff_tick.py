"""Tick-precision strategy bake-off — same 6 candidates as the 1-min
bake-off, but run on the full NQ 25M-tick dataset using exact fill
realism (200 ms signal->fill latency, exact tick that touches the limit
price = entry, exact tick that touches stop/target = exit, 0.25pt
adverse slip on stops, $0.74 RT commission, 2 MNQ).

This is the same simulator the production strategy was validated on
(sim_robustness_pack.py / sim_param_sensitivity.py)."""
from __future__ import annotations
import json, time
from pathlib import Path
import numpy as np
import pandas as pd
from datetime import time as _t

SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")
OUT = Path("/home/user/HFTBot/reports/strategy_bakeoff_tick.json")

# Match production cost model + Lucid-compliant gating
LATENCY_MS         = 200
MAX_WAIT_SECS      = 300
MAX_HOLD_SECS      = 600
COOLDOWN_SECS      = 60
MIN_HOLD_SECS      = 10        # >=10s on TARGET exits only
ENTRY_SLIP         = 0.0
ADVERSE_SLIP       = 0.25
COMM_RT            = 0.74
MNQ_PER_PT         = 2.0
N_MNQ              = 2
STARTING_BAL       = 50_000.0


def build_1m_bars(price, ts_ns, volume):
    df = pd.DataFrame({"price": price, "volume": volume,
                       "ts": pd.to_datetime(ts_ns, utc=True)})
    df = df.set_index("ts")
    ohlc = df["price"].resample("1min").agg(["first", "max", "min", "last"])
    ohlc.columns = ["open", "high", "low", "close"]
    vol = df["volume"].resample("1min").sum()
    return pd.concat([ohlc, vol.rename("volume")], axis=1).dropna()


def simulate(setups, price, ts_ns):
    """setups = list of dicts with keys
        sig_ts:    int ns      bar-close time when setup was identified
        side:      +1/-1
        entry_px:  float       LIMIT price
        stop_px:   float
        target_px: float
        fill_mode: "limit" or "market"  (market = enter at first tick post-latency)
    """
    cooldown_ns = COOLDOWN_SECS * 1_000_000_000
    latency_ns  = LATENCY_MS * 1_000_000
    max_hold_ns = MAX_HOLD_SECS * 1_000_000_000
    max_wait_ns = MAX_WAIT_SECS * 1_000_000_000
    min_hold_ns = MIN_HOLD_SECS * 1_000_000_000

    trades = []
    last_exit_ts = -1
    used_keys = set()
    for s in setups:
        sig_ts = int(s["sig_ts"])
        if last_exit_ts > 0 and sig_ts - last_exit_ts < cooldown_ns: continue
        side = int(s["side"])
        intended = float(s["entry_px"])
        stop_px = float(s["stop_px"])
        target_px = float(s["target_px"])
        fill_mode = s.get("fill_mode", "limit")
        key = (side, round(intended, 1), sig_ts // (60 * 1_000_000_000))
        if key in used_keys: continue

        fill_start = int(np.searchsorted(ts_ns, sig_ts + latency_ns, side="left"))
        fill_end = int(np.searchsorted(ts_ns, sig_ts + max_wait_ns, side="left"))
        if fill_start >= fill_end or fill_start >= len(price): continue

        if fill_mode == "market":
            # Enter at first tick after latency
            entry_idx = fill_start
        else:
            scan = price[fill_start:fill_end]
            hits = scan <= intended if side == 1 else scan >= intended
            if not hits.any(): continue
            entry_idx = fill_start + int(np.argmax(hits))

        entry_ts = int(ts_ns[entry_idx])
        if fill_mode == "market":
            entry_price = float(price[entry_idx])
        else:
            entry_price = intended + (ENTRY_SLIP if side == 1 else -ENTRY_SLIP)

        timeout_ts = entry_ts + max_hold_ns
        min_tgt_ts = entry_ts + min_hold_ns
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
            cand = np.where(tgt_mask & (scan_t >= min_tgt_ts))[0]
            tgt_idx = int(cand[0]) if len(cand) > 0 else len(scan_p)
        else:
            tgt_idx = len(scan_p)
        if stop_idx == len(scan_p) and tgt_idx == len(scan_p):
            exit_px = float(scan_p[-1]); exit_ts = int(scan_t[-1]); reason = "timeout"
        elif stop_idx <= tgt_idx:
            exit_px = stop_px - (ADVERSE_SLIP if side == 1 else -ADVERSE_SLIP)
            exit_ts = int(scan_t[stop_idx]); reason = "stop"
        else:
            exit_px = target_px; exit_ts = int(scan_t[tgt_idx]); reason = "target"
        pnl_pts = (exit_px - entry_price) if side == 1 else (entry_price - exit_px)
        pnl_usd = pnl_pts * N_MNQ * MNQ_PER_PT - COMM_RT * N_MNQ
        trades.append({"entry_ts": entry_ts, "exit_ts": exit_ts,
                       "pnl_usd": round(float(pnl_usd), 2), "reason": reason})
        used_keys.add(key)
        last_exit_ts = exit_ts
    return trades


# =========================== STRATEGY SETUPS ================================

def baseline_setups(bars):
    """Current production: 5pt impulse over 4 closed bars, LIMIT @ 0.618 retrace."""
    o = bars["open"].to_numpy(); h = bars["high"].to_numpy()
    l = bars["low"].to_numpy();  c = bars["close"].to_numpy()
    bar_ts = bars.index.astype("int64").to_numpy()
    out = []
    W = 4; IMP = 5.0; PCT = 0.618; STOP = 6.0; TGT = 12.0
    for i in range(W, len(bars) - 1):
        net = c[i] - c[i - W]
        if abs(net) < IMP: continue
        side = 1 if net > 0 else -1
        imp_high = h[i-W+1:i+1].max()
        imp_low = l[i-W+1:i+1].min()
        if side == 1:
            entry = imp_high - (imp_high - imp_low) * PCT
            stop = entry - STOP; target = entry + TGT
        else:
            entry = imp_low + (imp_high - imp_low) * PCT
            stop = entry + STOP; target = entry - TGT
        out.append({"sig_ts": int(bar_ts[i + 1]), "side": side,
                    "entry_px": entry, "stop_px": stop, "target_px": target,
                    "fill_mode": "limit"})
    return out


def vwap_fade_setups(bars):
    """Fade 1.5x ATR deviations from 60-bar VWAP; target = VWAP."""
    h = bars["high"].to_numpy(); l = bars["low"].to_numpy()
    c = bars["close"].to_numpy(); v = bars["volume"].to_numpy()
    bar_ts = bars.index.astype("int64").to_numpy()
    W = 60; ATR_W = 14; MULT = 1.5; STOP = 8.0
    tp = (h + l + c) / 3.0
    pv = tp * v
    cum_pv = pd.Series(pv).rolling(W).sum().to_numpy()
    cum_v  = pd.Series(v).rolling(W).sum().to_numpy()
    vwap = cum_pv / np.where(cum_v > 0, cum_v, np.nan)
    tr = np.maximum.reduce([h - l, np.abs(h - np.r_[c[0], c[:-1]]),
                            np.abs(l - np.r_[c[0], c[:-1]])])
    atr = pd.Series(tr).rolling(ATR_W).mean().to_numpy()
    out = []
    for i in range(W, len(bars) - 1):
        if not np.isfinite(vwap[i]) or not np.isfinite(atr[i]): continue
        dev = c[i] - vwap[i]
        thr = MULT * atr[i]
        if dev > thr and vwap[i] < c[i]:
            entry = c[i]
            out.append({"sig_ts": int(bar_ts[i + 1]), "side": -1,
                        "entry_px": entry, "stop_px": entry + STOP,
                        "target_px": float(vwap[i]), "fill_mode": "market"})
        elif dev < -thr and vwap[i] > c[i]:
            entry = c[i]
            out.append({"sig_ts": int(bar_ts[i + 1]), "side": 1,
                        "entry_px": entry, "stop_px": entry - STOP,
                        "target_px": float(vwap[i]), "fill_mode": "market"})
    return out


def donchian_setups(bars):
    """20-bar high/low breakout; stop = 10-bar opposite extreme."""
    h = bars["high"].to_numpy(); l = bars["low"].to_numpy()
    c = bars["close"].to_numpy()
    bar_ts = bars.index.astype("int64").to_numpy()
    LB = 20; SLB = 10; TMULT = 2.0
    out = []
    for i in range(LB, len(bars) - 1):
        prior_high = h[i - LB:i].max()
        prior_low  = l[i - LB:i].min()
        if c[i] > prior_high:
            entry = c[i]
            stop = float(l[i - SLB:i].min())
            if stop >= entry: continue
            target = entry + (entry - stop) * TMULT
            out.append({"sig_ts": int(bar_ts[i + 1]), "side": 1,
                        "entry_px": entry, "stop_px": stop, "target_px": target,
                        "fill_mode": "market"})
        elif c[i] < prior_low:
            entry = c[i]
            stop = float(h[i - SLB:i].max())
            if stop <= entry: continue
            target = entry - (stop - entry) * TMULT
            out.append({"sig_ts": int(bar_ts[i + 1]), "side": -1,
                        "entry_px": entry, "stop_px": stop, "target_px": target,
                        "fill_mode": "market"})
    return out


def orb_setups(bars):
    """First 15-min NY range, first close beyond triggers breakout entry."""
    bars = bars.copy()
    bars["ny"] = bars.index.tz_convert("America/New_York")
    bars["ny_date"] = bars["ny"].dt.date
    bars["ny_time"] = bars["ny"].dt.time
    h = bars["high"].to_numpy(); l = bars["low"].to_numpy(); c = bars["close"].to_numpy()
    bar_ts = bars.index.astype("int64").to_numpy()
    OR_END = _t(9, 45); MK_OPEN = _t(9, 30); MK_CLOSE = _t(16, 0)
    BUF = 2.0; TMULT = 1.0
    out = []
    for date, day in bars.groupby("ny_date", sort=False):
        in_or = day[(day["ny_time"] >= MK_OPEN) & (day["ny_time"] < OR_END)]
        if len(in_or) < 12: continue
        oh = in_or["high"].max(); ol = in_or["low"].min()
        if oh <= ol: continue
        width = oh - ol
        tradeable = day[(day["ny_time"] >= OR_END) & (day["ny_time"] < MK_CLOSE)]
        for idx in tradeable.index:
            i = bars.index.get_loc(idx)
            if c[i] > oh:
                out.append({"sig_ts": int(bar_ts[i + 1]) if i+1<len(bars) else int(bar_ts[i]),
                            "side": 1, "entry_px": oh, "stop_px": ol - BUF,
                            "target_px": oh + width * TMULT, "fill_mode": "market"})
                break
            if c[i] < ol:
                out.append({"sig_ts": int(bar_ts[i + 1]) if i+1<len(bars) else int(bar_ts[i]),
                            "side": -1, "entry_px": ol, "stop_px": oh + BUF,
                            "target_px": ol - width * TMULT, "fill_mode": "market"})
                break
    return out


def engulf_setups(bars):
    """2-bar bullish/bearish engulfing reversal."""
    o = bars["open"].to_numpy(); c = bars["close"].to_numpy()
    bar_ts = bars.index.astype("int64").to_numpy()
    STOP = 6.0; TGT = 12.0; MIN_BODY = 3.0
    out = []
    for i in range(1, len(bars) - 1):
        prev_top = max(o[i-1], c[i-1]); prev_bot = min(o[i-1], c[i-1])
        if prev_top - prev_bot < MIN_BODY: continue
        if c[i-1] < o[i-1] and c[i] > o[i] and o[i] <= c[i-1] and c[i] >= o[i-1]:
            entry = float(c[i])
            out.append({"sig_ts": int(bar_ts[i + 1]), "side": 1,
                        "entry_px": entry, "stop_px": entry - STOP,
                        "target_px": entry + TGT, "fill_mode": "market"})
        elif c[i-1] > o[i-1] and c[i] < o[i] and o[i] >= c[i-1] and c[i] <= o[i-1]:
            entry = float(c[i])
            out.append({"sig_ts": int(bar_ts[i + 1]), "side": -1,
                        "entry_px": entry, "stop_px": entry + STOP,
                        "target_px": entry - TGT, "fill_mode": "market"})
    return out


def baseline_hrs_setups(bars):
    """Baseline restricted to NY hour 11-15 (best-hour analysis)."""
    raw = baseline_setups(bars)
    bar_ts = bars.index.astype("int64").to_numpy()
    out = []
    for s in raw:
        ny = pd.Timestamp(s["sig_ts"], tz="UTC").tz_convert("America/New_York")
        if ny.hour in (11, 12, 13, 14, 15):
            out.append(s)
    return out


# ---- additional variants ------------------------------------------------

def baseline_tight_setups(bars):
    """Quick-target micro-scalp: 3-bar impulse, 0.5 pullback, 4pt stop, 6pt target."""
    o = bars["open"].to_numpy(); h = bars["high"].to_numpy()
    l = bars["low"].to_numpy();  c = bars["close"].to_numpy()
    bar_ts = bars.index.astype("int64").to_numpy()
    out = []
    W = 3; IMP = 4.0; PCT = 0.5; STOP = 4.0; TGT = 6.0
    for i in range(W, len(bars) - 1):
        net = c[i] - c[i - W]
        if abs(net) < IMP: continue
        side = 1 if net > 0 else -1
        imp_high = h[i-W+1:i+1].max(); imp_low = l[i-W+1:i+1].min()
        if side == 1:
            entry = imp_high - (imp_high - imp_low) * PCT
            stop = entry - STOP; target = entry + TGT
        else:
            entry = imp_low + (imp_high - imp_low) * PCT
            stop = entry + STOP; target = entry - TGT
        out.append({"sig_ts": int(bar_ts[i + 1]), "side": side,
                    "entry_px": entry, "stop_px": stop, "target_px": target,
                    "fill_mode": "limit"})
    return out


def baseline_wide_setups(bars):
    """Wider target variant: 4-bar impulse, 0.618, 6pt stop, 18pt target (RR 3.0)."""
    o = bars["open"].to_numpy(); h = bars["high"].to_numpy()
    l = bars["low"].to_numpy();  c = bars["close"].to_numpy()
    bar_ts = bars.index.astype("int64").to_numpy()
    out = []
    W = 4; IMP = 5.0; PCT = 0.618; STOP = 6.0; TGT = 18.0
    for i in range(W, len(bars) - 1):
        net = c[i] - c[i - W]
        if abs(net) < IMP: continue
        side = 1 if net > 0 else -1
        imp_high = h[i-W+1:i+1].max(); imp_low = l[i-W+1:i+1].min()
        if side == 1:
            entry = imp_high - (imp_high - imp_low) * PCT
            stop = entry - STOP; target = entry + TGT
        else:
            entry = imp_low + (imp_high - imp_low) * PCT
            stop = entry + STOP; target = entry - TGT
        out.append({"sig_ts": int(bar_ts[i + 1]), "side": side,
                    "entry_px": entry, "stop_px": stop, "target_px": target,
                    "fill_mode": "limit"})
    return out


def baseline_momentum_setups(bars):
    """Anti-baseline: enter AT BREAKOUT instead of waiting for pullback.
    Same 4-bar impulse, market-fill the breakout, 8pt stop, 12pt target."""
    o = bars["open"].to_numpy(); h = bars["high"].to_numpy()
    l = bars["low"].to_numpy();  c = bars["close"].to_numpy()
    bar_ts = bars.index.astype("int64").to_numpy()
    out = []
    W = 4; IMP = 5.0; STOP = 8.0; TGT = 12.0
    for i in range(W, len(bars) - 1):
        net = c[i] - c[i - W]
        if abs(net) < IMP: continue
        side = 1 if net > 0 else -1
        entry = float(c[i])
        if side == 1:
            stop = entry - STOP; target = entry + TGT
        else:
            stop = entry + STOP; target = entry - TGT
        out.append({"sig_ts": int(bar_ts[i + 1]), "side": side,
                    "entry_px": entry, "stop_px": stop, "target_px": target,
                    "fill_mode": "market"})
    return out


def baseline_drop_worst_hrs_setups(bars):
    """Baseline excluding only the worst hours from the earlier hour analysis:
    NY hr 8, 10, 22, 23 (avg negative or near-zero contribution)."""
    raw = baseline_setups(bars)
    bad = {8, 10, 22, 23}
    out = []
    for s in raw:
        ny = pd.Timestamp(s["sig_ts"], tz="UTC").tz_convert("America/New_York")
        if ny.hour not in bad:
            out.append(s)
    return out


def score(trades, period_days):
    if not trades: return {"n": 0}
    pnls = np.array([t["pnl_usd"] for t in trades])
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    cum = pnls.cumsum()
    maxdd = float((cum - np.maximum.accumulate(cum)).min())
    months = period_days / 30.44
    return {
        "n": len(trades),
        "wr": round(len(wins)/len(pnls)*100, 1),
        "total_pnl": round(float(pnls.sum()), 0),
        "ret_mo": round(float(pnls.sum())/STARTING_BAL*100/months, 2),
        "max_dd_usd": round(maxdd, 0),
        "max_dd_pct": round(abs(maxdd/STARTING_BAL*100), 2),
        "pf": round(float(wins.sum() / abs(losses.sum())), 3) if losses.size else 0,
        "rr": round(abs(float(wins.mean()/losses.mean())), 2) if wins.size and losses.size else 0,
        "trades_per_mo": round(len(trades)/months, 0),
    }


def main():
    t0 = time.time()
    print(f"Loading tick parquet ({SRC.stat().st_size/1e6:.0f} MB)...")
    df = pd.read_parquet(SRC)
    period_days = (df["ts"].iloc[-1] - df["ts"].iloc[0]).total_seconds() / 86400
    print(f"  {len(df):,} ticks across {period_days:.0f} days ({period_days/30.44:.1f} months)")

    price = df["price"].to_numpy(dtype=np.float32)
    volume = df["volume"].to_numpy(dtype=np.int32)
    ts_ns = df["ts"].astype("int64").to_numpy()

    print("Building 1-min bars from ticks...")
    bars_1m = build_1m_bars(price, ts_ns, volume)
    print(f"  {len(bars_1m):,} 1-min bars  ({time.time()-t0:.0f}s elapsed)")

    strategies = [
        ("BASELINE (pullback)",   baseline_setups),
        ("VWAP_FADE",             vwap_fade_setups),
        ("DONCHIAN_20",           donchian_setups),
        ("ORB_15min",             orb_setups),
        ("ENGULF",                engulf_setups),
        ("BASELINE_HRS_11-15",    baseline_hrs_setups),
        ("BASELINE_TIGHT 4/6",    baseline_tight_setups),
        ("BASELINE_WIDE  6/18",   baseline_wide_setups),
        ("BASELINE_MOMENTUM",     baseline_momentum_setups),
        ("BASELINE_DROP_BAD_HRS", baseline_drop_worst_hrs_setups),
    ]

    print(f"\n{'Strategy':<22} {'Trades':>7}  {'WR':>6}  {'PF':>6}  "
          f"{'RR':>6}  {'Ret/mo':>10}  {'DD$':>10}  {'DD%':>7}  {'Tr/mo':>7}")
    print("-" * 100)
    results = {}
    for name, fn in strategies:
        ts = time.time()
        setups = fn(bars_1m)
        trades = simulate(setups, price, ts_ns)
        s = score(trades, period_days)
        elapsed = time.time() - ts
        print(f"{name:<22} {s.get('n',0):>7}  {s.get('wr',0):>5.1f}%  "
              f"{s.get('pf',0):>6.2f}  {s.get('rr',0):>6.2f}  "
              f"{s.get('ret_mo',0):>+9.2f}%  {s.get('max_dd_usd',0):>+10,.0f}  "
              f"{s.get('max_dd_pct',0):>6.2f}%  {s.get('trades_per_mo',0):>7.0f}  "
              f"[{elapsed:.0f}s]")
        results[name] = s

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nTotal: {time.time()-t0:.0f}s -> {OUT}")


if __name__ == "__main__":
    main()
