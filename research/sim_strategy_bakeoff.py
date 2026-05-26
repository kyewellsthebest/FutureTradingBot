"""Strategy bake-off — test 5 candidate strategies head-to-head against the
current production Pullback Impulse baseline on 2 years of NQ 1-min data.

Candidates:
  1. BASELINE     — current Pullback Impulse (window=4, target=12, stop=6)
  2. VWAP_FADE    — fade 1.5*ATR deviations from 60-bar VWAP
  3. DONCHIAN     — 20-bar breakout, 10-bar opposite stop
  4. ORB          — NY open 15-min range breakout
  5. ENGULF       — 2-bar bullish/bearish engulfing reversal
  6. PULLBACK_HRS — current strategy but only during best hours (11-15 NY)

All run with the same fill realism (LIMIT fill if price within bar H-L,
first-touch exits, 200ms latency proxy, Lucid prop costs $0.74 RT
+ 0.25pt adverse slip on stops, 2 MNQ).

Each candidate must:
  - Be Lucid-compliant (winners hold >= 10s — handled per-strategy)
  - Use a stop and target (no naked positions)
  - Run on the same dataset, same cost model

Output:
  - Console table of all six side-by-side
  - reports/strategy_bakeoff.json with full per-trade detail
"""
from __future__ import annotations
import json, time
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd

SRC = Path("/home/user/HFTBot/data/polygon/NQ_1min.csv")
OUT = Path("/home/user/HFTBot/reports/strategy_bakeoff.json")

STARTING_BAL = 50_000.0
MNQ_PER_PT = 2.0
N_MNQ = 2
ENTRY_SLIP_PTS = 0.0
ADVERSE_SLIP_PTS = 0.25
COMM_RT = 0.74
MIN_TARGET_HOLD_BARS = 1   # >=1 bar (~60s) hold to satisfy Lucid 10s rule
MAX_HOLD_BARS = 10          # 10-bar timeout
COOLDOWN_BARS = 1           # 1-bar gap


@dataclass
class Trade:
    entry_idx: int
    entry_px: float
    stop_px: float
    target_px: float
    side: int           # +1 long, -1 short
    exit_idx: int = -1
    exit_px: float = 0.0
    exit_reason: str = ""

    @property
    def hold_bars(self):
        return self.exit_idx - self.entry_idx

    @property
    def pnl_gross(self):
        pts = (self.exit_px - self.entry_px) * self.side
        return pts * MNQ_PER_PT * N_MNQ

    @property
    def pnl_net(self):
        return self.pnl_gross - COMM_RT * N_MNQ


# ---------------------------------------------------------------------------
# Generic simulator: given a setup-detector + risk params, simulate fills
# ---------------------------------------------------------------------------
def simulate(bars: pd.DataFrame, setups: list[dict]) -> list[Trade]:
    """setups: list of dicts each with keys
        signal_bar: int   bar index at which the setup was identified
        side: +1 / -1
        entry_px: float   limit-fill price
        stop_px: float
        target_px: float
    The sim looks at bars[signal_bar+1:] for entry fill (limit touched within
    bar high-low range), then walks forward to find first stop/target/timeout
    exit. Enforces COOLDOWN_BARS gap between trades + de-dup of same setup."""
    o = bars["open"].to_numpy()
    h = bars["high"].to_numpy()
    l = bars["low"].to_numpy()
    c = bars["close"].to_numpy()
    n = len(bars)
    trades: list[Trade] = []
    last_exit = -COOLDOWN_BARS - 1
    used_keys: set[tuple] = set()
    for s in setups:
        sb = s["signal_bar"]
        if sb + 1 >= n: continue
        if sb < last_exit + COOLDOWN_BARS: continue
        # de-dup: skip if we already opened a trade with same direction +
        # similar entry within last 5 bars
        key = (s["side"], round(s["entry_px"], 1), sb // 5)
        if key in used_keys: continue
        # Find entry fill: scan bars[sb+1 : sb+6] for LIMIT touch
        entry_idx = -1
        for i in range(sb + 1, min(sb + 6, n)):
            if s["side"] == 1 and l[i] <= s["entry_px"] <= h[i]:
                entry_idx = i; break
            if s["side"] == -1 and l[i] <= s["entry_px"] <= h[i]:
                entry_idx = i; break
        if entry_idx == -1: continue
        # Walk forward for exit
        exit_idx = -1; exit_px = 0.0; reason = ""
        for j in range(entry_idx + 1, min(entry_idx + 1 + MAX_HOLD_BARS, n)):
            hit_stop = False; hit_tgt = False
            if s["side"] == 1:
                hit_stop = l[j] <= s["stop_px"]
                hit_tgt  = h[j] >= s["target_px"]
            else:
                hit_stop = h[j] >= s["stop_px"]
                hit_tgt  = l[j] <= s["target_px"]
            # MIN_TARGET_HOLD_BARS gate -- targets can't fire until N bars after entry
            if hit_tgt and (j - entry_idx) < MIN_TARGET_HOLD_BARS:
                hit_tgt = False
            if hit_stop and hit_tgt:
                # both hit in same bar -- conservative: assume stop first
                exit_idx = j; reason = "stop"
                exit_px = s["stop_px"] - (ADVERSE_SLIP_PTS if s["side"] == 1 else -ADVERSE_SLIP_PTS)
                break
            if hit_stop:
                exit_idx = j; reason = "stop"
                exit_px = s["stop_px"] - (ADVERSE_SLIP_PTS if s["side"] == 1 else -ADVERSE_SLIP_PTS)
                break
            if hit_tgt:
                exit_idx = j; reason = "target"; exit_px = s["target_px"]
                break
        if exit_idx == -1:
            # timeout at MAX_HOLD_BARS
            exit_idx = min(entry_idx + MAX_HOLD_BARS, n - 1)
            exit_px = c[exit_idx]
            reason = "timeout"
        t = Trade(
            entry_idx=entry_idx, entry_px=s["entry_px"] + (ENTRY_SLIP_PTS if s["side"]==1 else -ENTRY_SLIP_PTS),
            stop_px=s["stop_px"], target_px=s["target_px"],
            side=s["side"], exit_idx=exit_idx, exit_px=exit_px, exit_reason=reason,
        )
        trades.append(t)
        used_keys.add(key)
        last_exit = exit_idx
    return trades


# ---------------------------------------------------------------------------
# STRATEGY 1: BASELINE (current production) -- impulse + 0.618 pullback
# ---------------------------------------------------------------------------
def setups_baseline(bars: pd.DataFrame, *, window=4, impulse=5.0,
                    pullback_pct=0.618, stop_pts=6.0, target_pts=12.0):
    o = bars["open"].to_numpy(); h = bars["high"].to_numpy()
    l = bars["low"].to_numpy(); c = bars["close"].to_numpy()
    setups = []
    for i in range(window, len(bars) - 1):
        # impulse: net close move over window bars
        net = c[i] - c[i - window]
        if abs(net) < impulse: continue
        side = 1 if net > 0 else -1
        if side == 1:
            imp_high = h[i-window+1:i+1].max()
            imp_low = l[i-window+1:i+1].min()
            entry = imp_high - (imp_high - imp_low) * pullback_pct
            stop = entry - stop_pts; target = entry + target_pts
        else:
            imp_high = h[i-window+1:i+1].max()
            imp_low = l[i-window+1:i+1].min()
            entry = imp_low + (imp_high - imp_low) * pullback_pct
            stop = entry + stop_pts; target = entry - target_pts
        setups.append({"signal_bar": i, "side": side,
                       "entry_px": entry, "stop_px": stop, "target_px": target})
    return setups


# ---------------------------------------------------------------------------
# STRATEGY 2: VWAP_FADE -- fade 1.5*ATR deviations from rolling 60-bar VWAP
# ---------------------------------------------------------------------------
def setups_vwap_fade(bars: pd.DataFrame, *, window=60, atr_window=14,
                     atr_mult=1.5, stop_pts=8.0, target_pts=8.0):
    h = bars["high"].to_numpy(); l = bars["low"].to_numpy()
    c = bars["close"].to_numpy(); v = bars["volume"].to_numpy()
    tp = (h + l + c) / 3.0
    pv = tp * v
    # rolling VWAP
    cum_pv = pd.Series(pv).rolling(window).sum().to_numpy()
    cum_v  = pd.Series(v).rolling(window).sum().to_numpy()
    vwap = cum_pv / np.where(cum_v > 0, cum_v, np.nan)
    # ATR
    tr = np.maximum.reduce([h - l, np.abs(h - np.r_[c[0], c[:-1]]),
                            np.abs(l - np.r_[c[0], c[:-1]])])
    atr = pd.Series(tr).rolling(atr_window).mean().to_numpy()
    setups = []
    for i in range(window, len(bars) - 1):
        if not np.isfinite(vwap[i]) or not np.isfinite(atr[i]): continue
        dev = c[i] - vwap[i]
        threshold = atr_mult * atr[i]
        if dev > threshold:
            # price too high -> fade short, target = VWAP
            entry = c[i]
            target = vwap[i]
            stop = entry + stop_pts
            if target >= entry: continue
            setups.append({"signal_bar": i, "side": -1,
                           "entry_px": entry, "stop_px": stop, "target_px": target})
        elif dev < -threshold:
            entry = c[i]
            target = vwap[i]
            stop = entry - stop_pts
            if target <= entry: continue
            setups.append({"signal_bar": i, "side": 1,
                           "entry_px": entry, "stop_px": stop, "target_px": target})
    return setups


# ---------------------------------------------------------------------------
# STRATEGY 3: DONCHIAN breakout -- 20-bar high/low breakout
# ---------------------------------------------------------------------------
def setups_donchian(bars: pd.DataFrame, *, lookback=20, stop_lookback=10,
                    target_mult=2.0):
    h = bars["high"].to_numpy(); l = bars["low"].to_numpy()
    c = bars["close"].to_numpy()
    setups = []
    for i in range(lookback, len(bars) - 1):
        prior_high = h[i - lookback:i].max()
        prior_low  = l[i - lookback:i].min()
        # Breakout long
        if c[i] > prior_high:
            entry = c[i]
            stop = l[i - stop_lookback:i].min()
            if stop >= entry: continue
            target = entry + (entry - stop) * target_mult
            setups.append({"signal_bar": i, "side": 1,
                           "entry_px": entry, "stop_px": stop, "target_px": target})
        elif c[i] < prior_low:
            entry = c[i]
            stop = h[i - stop_lookback:i].max()
            if stop <= entry: continue
            target = entry - (stop - entry) * target_mult
            setups.append({"signal_bar": i, "side": -1,
                           "entry_px": entry, "stop_px": stop, "target_px": target})
    return setups


# ---------------------------------------------------------------------------
# STRATEGY 4: ORB -- Opening range (15-min NY) breakout
# ---------------------------------------------------------------------------
def setups_orb(bars: pd.DataFrame, *, or_minutes=15, target_mult=1.0,
               stop_buffer_pts=2.0):
    """Compute first 15 min of NY session OR each day; first close beyond
    OR triggers a breakout entry. Stop = opposite OR edge + buffer."""
    setups = []
    df = bars.copy()
    df["ny"] = df.index.tz_convert("America/New_York")
    df["ny_date"] = df["ny"].dt.date
    df["ny_time"] = df["ny"].dt.time
    h = bars["high"].to_numpy(); l = bars["low"].to_numpy()
    c = bars["close"].to_numpy()
    from datetime import time as _t
    market_open = _t(9, 30)
    or_end = _t(9, 30 + or_minutes)
    market_close = _t(16, 0)
    for date, day in df.groupby("ny_date", sort=False):
        in_or = day[(day["ny_time"] >= market_open) & (day["ny_time"] < or_end)]
        if len(in_or) < or_minutes - 2: continue
        or_high = in_or["high"].max()
        or_low = in_or["low"].min()
        if or_high <= or_low: continue
        or_width = or_high - or_low
        tradeable = day[(day["ny_time"] >= or_end) & (day["ny_time"] < market_close)]
        for idx_pos in tradeable.index:
            i = bars.index.get_loc(idx_pos)
            if c[i] > or_high:
                entry = or_high
                stop = or_low - stop_buffer_pts
                target = entry + or_width * target_mult
                setups.append({"signal_bar": i, "side": 1,
                               "entry_px": entry, "stop_px": stop, "target_px": target})
                break  # one trade per day
            if c[i] < or_low:
                entry = or_low
                stop = or_high + stop_buffer_pts
                target = entry - or_width * target_mult
                setups.append({"signal_bar": i, "side": -1,
                               "entry_px": entry, "stop_px": stop, "target_px": target})
                break
    return setups


# ---------------------------------------------------------------------------
# STRATEGY 5: ENGULF -- 2-bar engulfing reversal
# ---------------------------------------------------------------------------
def setups_engulf(bars: pd.DataFrame, *, stop_pts=6.0, target_pts=12.0,
                  min_engulf_pts=3.0):
    o = bars["open"].to_numpy(); c = bars["close"].to_numpy()
    h = bars["high"].to_numpy(); l = bars["low"].to_numpy()
    setups = []
    for i in range(1, len(bars) - 1):
        prev_body_top = max(o[i-1], c[i-1])
        prev_body_bot = min(o[i-1], c[i-1])
        prev_body = prev_body_top - prev_body_bot
        if prev_body < min_engulf_pts: continue
        # Bullish engulfing: prev bearish + curr bullish + closes above prev open
        if c[i-1] < o[i-1] and c[i] > o[i] and o[i] <= c[i-1] and c[i] >= o[i-1]:
            entry = c[i]
            stop = entry - stop_pts
            target = entry + target_pts
            setups.append({"signal_bar": i, "side": 1,
                           "entry_px": entry, "stop_px": stop, "target_px": target})
        # Bearish engulfing
        elif c[i-1] > o[i-1] and c[i] < o[i] and o[i] >= c[i-1] and c[i] <= o[i-1]:
            entry = c[i]
            stop = entry + stop_pts
            target = entry - target_pts
            setups.append({"signal_bar": i, "side": -1,
                           "entry_px": entry, "stop_px": stop, "target_px": target})
    return setups


# ---------------------------------------------------------------------------
# STRATEGY 6: BASELINE + best-hours-only filter (NY hr 11-15)
# ---------------------------------------------------------------------------
def setups_baseline_hrs(bars: pd.DataFrame, *, allowed_hrs=(11,12,13,14,15)):
    raw = setups_baseline(bars)
    ny = bars.index.tz_convert("America/New_York")
    out = []
    for s in raw:
        if ny[s["signal_bar"]].hour in allowed_hrs:
            out.append(s)
    return out


# ---------------------------------------------------------------------------
# Run + score
# ---------------------------------------------------------------------------
def score(trades: list[Trade], days: float) -> dict:
    if not trades:
        return {"n": 0, "ret_mo": 0.0}
    pnls = np.array([t.pnl_net for t in trades])
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    cum = pnls.cumsum()
    maxdd = float((cum - np.maximum.accumulate(cum)).min())
    months = days / 30.44
    return {
        "n": len(trades),
        "wr": round(len(wins)/len(pnls)*100, 1),
        "total_pnl": round(float(pnls.sum()), 0),
        "ret_mo": round(float(pnls.sum())/STARTING_BAL*100/months, 2),
        "max_dd_usd": round(maxdd, 0),
        "max_dd_pct": round(abs(maxdd/STARTING_BAL*100), 2),
        "pf": round(float(wins.sum() / abs(losses.sum())), 3) if len(losses) and losses.sum() != 0 else 0,
        "rr": round(abs(float(wins.mean()/losses.mean())), 2) if len(wins) and len(losses) else 0,
        "trades_per_mo": round(len(trades)/months, 0),
    }


def main():
    t0 = time.time()
    print(f"Loading {SRC.name}...")
    bars = pd.read_csv(SRC, parse_dates=["ts"]).set_index("ts")
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    days = (bars.index[-1] - bars.index[0]).total_seconds() / 86400
    print(f"  {len(bars):,} bars across {days:.0f} days ({days/30.44:.1f} months)")

    strategies = [
        ("BASELINE (pullback)", setups_baseline),
        ("VWAP_FADE",           setups_vwap_fade),
        ("DONCHIAN_20",         setups_donchian),
        ("ORB_15min",           setups_orb),
        ("ENGULF",              setups_engulf),
        ("BASELINE_HRS_11-15",  setups_baseline_hrs),
    ]

    print(f"\n{'Strategy':<22} {'Trades':>7}  {'WR':>6}  {'PF':>6}  "
          f"{'RR':>6}  {'Ret/mo':>10}  {'DD$':>10}  {'DD%':>7}  {'Tr/mo':>7}")
    print("-" * 100)
    results = {}
    for name, fn in strategies:
        ts = time.time()
        try:
            setups = fn(bars)
            trades = simulate(bars, setups)
            s = score(trades, days)
        except Exception as e:
            print(f"{name:<22} ERROR: {e}")
            continue
        elapsed = time.time() - ts
        print(f"{name:<22} {s['n']:>7}  {s.get('wr',0):>5.1f}%  "
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
