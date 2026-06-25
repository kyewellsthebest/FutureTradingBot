"""Faithful tick-level simulator for the live pullback (INVERSE FADE) bot.

Goal: reproduce EXACTLY what bot/pullback_strategy.py + bot/fib_main.py do
live, but on real NQ tick data (price+bid+ask), so a strategy that is
profitable here has a real chance live.

Fidelity anchors (verified against the live diagnostic bundle + 100 real
trades on 2026-06-25):
  - setup geometry: bot.pullback_strategy.detect_pullback_setup (imported)
  - entry: LIMIT at pullback_entry, 0 entry slip
  - exit: should_exit_on_tick semantics
        LONG  stop  -> bid <= stop_px   (fill stop_px - slip)
        LONG  tgt   -> bid >= target_px (fill target_px)
        SHORT stop  -> ask >= stop_px   (fill stop_px + slip)
        SHORT tgt   -> ask <= target_px (fill target_px)
        timeout -> mid, at entry+MAX_HOLD
  - costs: $0.74/MNQ round-trip, 0.25pt stop slip, $2/pt/MNQ
        target win  = +TARGET*2 - 0.74   (= +39.26 for 20pt) [verified]
        stop  loss  = -(STOP+0.25)*2 - 0.74 (= -21.24 for 10pt) [verified]
  - cooldown 60s, max_wait 300s, max_hold 600s
  - sticky arm: a pullback touch during cooldown/active trade still fires
    once free, at pullback_entry, provided setup not expired
  - session: no entries during CME daily break (17:00-18:00 ET, weekends)

Timestamps in the parquet are UTC; ET = UTC-5 for the Dec-Feb dataset (EST,
no DST before 2026-03-08).
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass

TICK_PARQUET = "data/tick/NQ.03-26.Last.parquet"
PT_VALUE = 2.0        # $/pt per MNQ
NS = 1_000_000_000

# -------------------------------------------------------------------------
# Data loading
# -------------------------------------------------------------------------
def load_ticks(path: str = TICK_PARQUET):
    df = pd.read_parquet(path, columns=["ts", "price", "bid", "ask"])
    df = df.sort_values("ts", kind="stable").reset_index(drop=True)
    ts = df["ts"].to_numpy("datetime64[ns]").astype("int64")
    price = df["price"].to_numpy("float64")
    bid = df["bid"].to_numpy("float64")
    ask = df["ask"].to_numpy("float64")
    # Some feeds carry bid/ask==0 on the very first prints; backfill to price
    bad = ~(bid > 0); bid[bad] = price[bad]
    bad = ~(ask > 0); ask[bad] = price[bad]
    return ts, price, bid, ask


def build_1m_bars(ts, price):
    """1-min OHLC from last price, indexed by bar START (UTC)."""
    s = pd.Series(price, index=pd.to_datetime(ts))
    o = s.resample("1min").first()
    h = s.resample("1min").max()
    l = s.resample("1min").min()
    c = s.resample("1min").last()
    bars = pd.DataFrame({"open": o, "high": h, "low": l, "close": c}).dropna()
    return bars


# -------------------------------------------------------------------------
# Session break (vectorized, EST = UTC-5 for this dataset)
# -------------------------------------------------------------------------
def _in_break_ns(ts_ns):
    """Boolean array: True where ts is inside the CME daily break / weekend.
    ET = UTC-5 (EST). Break = Sat all day, Fri>=17:00, Sun<18:00,
    Mon-Thu 17:00-18:00."""
    et = pd.to_datetime(ts_ns - 5 * 3600 * NS)
    dow = et.dayofweek.to_numpy()      # 0=Mon..6=Sun
    hm = (et.hour * 60 + et.minute).to_numpy()
    OPEN, CLOSE = 18 * 60, 17 * 60
    brk = (dow == 5)
    brk |= (dow == 4) & (hm >= CLOSE)
    brk |= (dow == 6) & (hm < OPEN)
    brk |= (dow <= 3) & (hm >= CLOSE) & (hm < OPEN)
    return brk


# -------------------------------------------------------------------------
# Setup precompute (vectorized; validated against detect_pullback_setup)
# -------------------------------------------------------------------------
def _tick_round_arr(px, mode):
    n = px / 0.25
    if mode == "floor":
        n = np.floor(n)
    elif mode == "ceil":
        n = np.ceil(n)
    return np.round(n * 0.25, 2)


def precompute_setups(bars: pd.DataFrame, params: dict):
    """Vectorized replica of detect_pullback_setup. Returns a structured
    dict of arrays for every bar that produces a setup.

    Detect time = bar CLOSE = bar_start + 60s (the live runtime calls
    on_new_1m_bar with `now` ~ the just-closed bar)."""
    imp_pts = float(params.get("IMPULSE_PTS", 5.0))
    W = int(params.get("IMPULSE_WINDOW_BARS", 4))
    pull = float(params.get("PULLBACK_PCT", 0.236))
    stop_pts = float(params.get("STOP_PTS", 10.0))
    tgt_pts = float(params.get("TARGET_PTS", 20.0))
    invert = bool(params.get("INVERT", True))
    min_leg = float(params.get("MIN_LEG_PTS", 0.0))

    o = bars["open"].to_numpy(); h = bars["high"].to_numpy()
    l = bars["low"].to_numpy(); c = bars["close"].to_numpy()
    start_ns = bars.index.to_numpy("datetime64[ns]").astype("int64")
    n = len(bars)
    if n < W:
        return None

    # rolling window [i-W+1 .. i]
    net = c[W - 1:] - o[: n - W + 1]              # close[i]-open[i-W+1]
    # rolling high/low over W bars
    hh = pd.Series(h).rolling(W).max().to_numpy()[W - 1:]
    ll = pd.Series(l).rolling(W).min().to_numpy()[W - 1:]
    idx = np.arange(W - 1, n)                       # bar index of window end
    rng = hh - ll

    valid = (np.abs(net) >= imp_pts) & (rng > 0) & (rng >= min_leg)
    idx = idx[valid]; net = net[valid]; hh = hh[valid]; ll = ll[valid]; rng = rng[valid]

    orig_up = net > 0                               # impulse direction up?
    # trade direction (+1 long / -1 short)
    if invert:
        trade_long = ~orig_up                       # fade
    else:
        trade_long = orig_up
    trade_dir = np.where(trade_long, 1, -1).astype("int8")

    # entry from impulse direction
    entry = np.where(orig_up, hh - pull * rng, ll + pull * rng)
    entry = np.where(orig_up, _tick_round_arr(entry, "floor"),
                     _tick_round_arr(entry, "ceil"))   # entry rounds per orig_side

    # stop/target by trade side, tick-rounded per side
    stop = np.where(trade_long, entry - stop_pts, entry + stop_pts)
    tgt = np.where(trade_long, entry + tgt_pts, entry - tgt_pts)
    stop = np.where(trade_long, _tick_round_arr(stop, "ceil"),
                    _tick_round_arr(stop, "floor"))
    tgt = np.where(trade_long, _tick_round_arr(tgt, "ceil"),
                   _tick_round_arr(tgt, "floor"))

    det_ts = start_ns[idx] + 60 * NS                # bar close time
    return {
        "det_ts": det_ts, "trade_dir": trade_dir, "orig_up": orig_up,
        "entry": entry, "stop": stop, "tgt": tgt,
        "ih": hh, "il": ll,
    }


# -------------------------------------------------------------------------
# Core simulation
# -------------------------------------------------------------------------
@dataclass
class SimCfg:
    cooldown_s: int = 60
    max_wait_s: int = 300
    max_hold_s: int = 600
    stop_slip: float = 0.25
    comm_rt: float = 0.74
    min_tgt_hold_s: int = 0
    n_mnq: int = 1
    block_breaks: bool = True


def simulate(ticks, setups, cfg: SimCfg):
    ts, price, bid, ask = ticks
    if setups is None or len(setups["det_ts"]) == 0:
        return pd.DataFrame()
    det_ts = setups["det_ts"]; tdir = setups["trade_dir"]
    orig_up = setups["orig_up"]; entry = setups["entry"]
    stop = setups["stop"]; tgt = setups["tgt"]
    ih = setups["ih"]; il = setups["il"]
    nset = len(det_ts)

    max_wait = cfg.max_wait_s * NS
    max_hold = cfg.max_hold_s * NS
    cooldown = cfg.cooldown_s * NS
    min_hold = cfg.min_tgt_hold_s * NS
    ntick = len(ts)

    trades = []
    t_free = ts[0]
    used = set()
    si = 0  # pointer: first setup whose expiry might still be >= t_free

    while True:
        # advance si past setups that can never fire again (expired before t_free)
        while si < nset and det_ts[si] + max_wait < t_free:
            si += 1
        if si >= nset:
            break

        # Find the next trade: among setups j>=si with expiry>=t_free, the
        # one whose fill happens earliest (fill = first pullback touch in
        # [det, expiry], fired at max(touch, t_free), not in break).
        best = None  # (fire_ts, j, entry_idx)
        j = si
        # earliest theoretical fill can't precede any det_ts; once det_ts[j]
        # exceeds current best fire, no later setup can win.
        while j < nset:
            dts = det_ts[j]
            if best is not None and dts > best[0]:
                break
            exp = dts + max_wait
            if exp < t_free:
                j += 1; continue
            key = (round(float(entry[j]), 2), round(float(stop[j]), 2), int(tdir[j]))
            if key in used:
                j += 1; continue
            # window of ticks to look for a pullback touch: [dts, exp]
            lo = np.searchsorted(ts, dts, "left")
            hi = np.searchsorted(ts, exp, "right")
            if lo >= hi:
                j += 1; continue
            seg_p = price[lo:hi]
            if orig_up[j]:
                touch = seg_p <= entry[j]    # price falls to entry
            else:
                touch = seg_p >= entry[j]    # price rises to entry
            if not touch.any():
                j += 1; continue
            tk = lo + int(np.argmax(touch))  # first touch tick
            fire = ts[tk]
            if fire < t_free:
                fire = t_free                 # sticky: fire when free
            if fire > exp:
                j += 1; continue
            # entry tick = first tick at/after fire
            eidx = np.searchsorted(ts, fire, "left")
            if eidx >= ntick:
                j += 1; continue
            # session break: if blocked, find next non-break touch in window
            if cfg.block_breaks and _in_break_ns(np.array([ts[eidx]]))[0]:
                # scan forward within window for a non-break touch >= t_free
                seg2_lo = max(tk, np.searchsorted(ts, t_free, "left"))
                found = False
                for k in range(seg2_lo, hi):
                    if ts[k] > exp:
                        break
                    if (orig_up[j] and price[k] <= entry[j]) or \
                       (not orig_up[j] and price[k] >= entry[j]):
                        if not _in_break_ns(np.array([ts[k]]))[0]:
                            tk = k; fire = ts[k]; eidx = k; found = True; break
                if not found:
                    j += 1; continue
            if best is None or fire < best[0]:
                best = (fire, j, eidx)
            j += 1

        if best is None:
            break
        fire_ts, j, eidx = best
        e_px = float(entry[j]); s_px = float(stop[j]); t_px = float(tgt[j])
        d = int(tdir[j])

        # ---- exit scan from eidx within max_hold ----
        deadline = fire_ts + max_hold
        hi = np.searchsorted(ts, deadline, "right")
        seg = slice(eidx, hi)
        b = bid[seg]; a = ask[seg]; tseg = ts[seg]
        hold_ok = (tseg - fire_ts) >= min_hold
        if d == 1:  # LONG
            stop_hit = b <= s_px
            tgt_hit = (b >= t_px) & hold_ok
        else:       # SHORT
            stop_hit = a >= s_px
            tgt_hit = (a <= t_px) & hold_ok
        any_exit = stop_hit | tgt_hit
        if any_exit.any():
            xi = int(np.argmax(any_exit))
            x_ts = tseg[xi]
            if stop_hit[xi]:
                reason = "stop"
                x_px = s_px - cfg.stop_slip if d == 1 else s_px + cfg.stop_slip
            else:
                reason = "target"
                x_px = t_px
        else:
            # timeout at last tick <= deadline
            xi = len(tseg) - 1
            if xi < 0:
                # no ticks after entry (end of data) -> drop
                used.add((round(e_px, 2), round(s_px, 2), d))
                t_free = fire_ts + cooldown
                continue
            x_ts = tseg[xi]; reason = "timeout"
            x_px = (b[xi] + a[xi]) / 2.0

        pnl = d * (x_px - e_px) * PT_VALUE * cfg.n_mnq - cfg.comm_rt * cfg.n_mnq
        trades.append({
            "fire_ts": fire_ts, "exit_ts": x_ts,
            "side": "LONG" if d == 1 else "SHORT",
            "entry": e_px, "stop": s_px, "target": t_px,
            "exit_px": round(x_px, 2), "reason": reason,
            "hold_s": (x_ts - fire_ts) / NS, "pnl": pnl,
        })
        used.add((round(e_px, 2), round(s_px, 2), d))
        t_free = x_ts + cooldown

    df = pd.DataFrame(trades)
    if not df.empty:
        df["dt"] = pd.to_datetime(df["fire_ts"])
    return df


# -------------------------------------------------------------------------
# Stats
# -------------------------------------------------------------------------
def stats(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"n": 0}
    n = len(df)
    days = max(1, df["dt"].dt.normalize().nunique())
    wins = (df["pnl"] > 0).sum()
    rc = df["reason"].value_counts().to_dict()
    net = df["pnl"].sum()
    # equity / drawdown
    eq = df["pnl"].cumsum().to_numpy()
    peak = np.maximum.accumulate(eq)
    dd = float((peak - eq).max())
    return {
        "n": n, "days": days, "tr_per_day": round(n / days, 1),
        "wr": round(100 * wins / n, 1),
        "tgt%": round(100 * rc.get("target", 0) / n, 1),
        "stop%": round(100 * rc.get("stop", 0) / n, 1),
        "to%": round(100 * rc.get("timeout", 0) / n, 1),
        "net": round(net, 0), "per_day": round(net / days, 1),
        "per_trade": round(net / n, 2), "maxDD": round(dd, 0),
    }


if __name__ == "__main__":
    import sys, time
    t0 = time.time()
    params = {"IMPULSE_PTS": 5.0, "IMPULSE_WINDOW_BARS": 4, "PULLBACK_PCT": 0.236,
              "STOP_PTS": 10.0, "TARGET_PTS": 20.0, "INVERT": True}
    print("loading ticks...", flush=True)
    ticks = load_ticks()
    print(f"  {len(ticks[0]):,} ticks  {time.time()-t0:.0f}s", flush=True)
    bars = build_1m_bars(ticks[0], ticks[1])
    print(f"  {len(bars):,} 1-min bars", flush=True)
    setups = precompute_setups(bars, params)
    print(f"  {len(setups['det_ts']):,} setups", flush=True)
    df = simulate(ticks, setups, SimCfg())
    print(f"sim done {time.time()-t0:.0f}s", flush=True)
    print("\nLIVE-CONFIG (INV 0.236, stop10/tgt20) on full NQ tick data:")
    print(stats(df))
