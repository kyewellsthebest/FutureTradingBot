"""Complex pattern miner — test many high-probability setups.

Patterns tested:
  A. INSIDE BAR breakout (consolidation, then breakout direction)
  B. NR4 / NR7 breakout (narrowest range of N bars → expansion)
  C. PRIOR DAY HIGH/LOW retest (test then reject)
  D. SD LEVEL FADE (price at +/- 1, 2, 3 SD from daily mean → fade)
  E. ROUND NUMBER REJECTION (xx,500 / xx,000 levels)
  F. VWAP STRETCH FADE (price > 2 std from session VWAP)
  G. 3-BAR REVERSAL (morning star / evening star / engulfing)
  H. ASIAN RANGE BREAKOUT INTO LONDON

Each pattern: simple entry/exit logic, position size by stop distance.
Report stats and flag anything that meets the user spec.
"""
from __future__ import annotations
import numpy as np, pandas as pd
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "polygon" / "NQ_1min.csv"

STARTING_BALANCE     = 50_000.0
MNQ_PER_PT           = 2.0
COMM_PER_CONTRACT_RT = 2.0
TARGET_RISK_USD      = 50.0
MAX_CONTRACTS        = 5


def sz(stop_pts):
    if stop_pts <= 0: return 1
    return max(1, min(MAX_CONTRACTS, int(TARGET_RISK_USD / (stop_pts * MNQ_PER_PT))))


def resample(nq, freq):
    if freq == "1min": return nq
    return nq.resample(freq).agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna()


def stats(trades, months):
    if not trades: return None
    pnls = np.array([t["pnl_usd"] for t in trades])
    n = len(pnls)
    wins = int((pnls > 0).sum())
    gw = float(pnls[pnls > 0].sum()); gl = float(abs(pnls[pnls < 0].sum()))
    pf = gw / gl if gl > 0 else float("inf")
    cum = pnls.cumsum()
    dd = float((cum - np.maximum.accumulate(cum)).min())
    avg_w = float(pnls[pnls > 0].mean()) if wins else 0
    avg_l = float(pnls[pnls < 0].mean()) if wins < n else 0
    return {"n": n, "wr": wins/n, "pf": pf,
            "total": float(pnls.sum()), "per": float(pnls.mean()),
            "trades_per_mo": n/months,
            "maxdd": dd, "maxdd_pct": dd/STARTING_BALANCE*100,
            "rr": abs(avg_w/avg_l) if avg_l != 0 else 0,
            "ret_per_mo": float(pnls.sum())/STARTING_BALANCE*100/months}


def hits_spec(s):
    """User's strict minimums."""
    if not s: return False
    return (s["wr"] >= 0.55 and s["rr"] >= 1.2
            and s["trades_per_mo"] >= 100
            and s["ret_per_mo"] >= 3.0
            and abs(s["maxdd_pct"]) <= 2.0)


# ===========================================================================
# A. INSIDE BAR breakout
# ===========================================================================
def inside_bar_breakout(arr, target_R=1.5, stop_buf=1.0, max_hold=20):
    o = arr[:, 0]; h = arr[:, 1]; l = arr[:, 2]; c = arr[:, 3]
    n = len(arr)
    trades = []
    active = None
    for t in range(2, n):
        if active is not None:
            stop_hit = (active["side"] == "LONG" and l[t] <= active["stop"]) or \
                       (active["side"] == "SHORT" and h[t] >= active["stop"])
            tgt_hit = (active["side"] == "LONG" and h[t] >= active["target"]) or \
                      (active["side"] == "SHORT" and l[t] <= active["target"])
            ex = None
            if stop_hit: ex = active["stop"]
            elif tgt_hit: ex = active["target"]
            elif t - active["entry_bar"] >= max_hold: ex = float(c[t])
            if ex is not None:
                pp = (active["entry"] - ex) if active["side"] == "SHORT" else (ex - active["entry"])
                pnl = pp * active["size"] * MNQ_PER_PT - COMM_PER_CONTRACT_RT * active["size"]
                trades.append({"pnl_usd": float(pnl), "side": active["side"]})
                active = None
        if active is None and t > 2:
            # Inside bar: bar t-1 high < bar t-2 high AND low > bar t-2 low
            prev_h = h[t-2]; prev_l = l[t-2]
            inside_h = h[t-1]; inside_l = l[t-1]
            if inside_h < prev_h and inside_l > prev_l:
                # next bar (t) breakout
                if c[t] > inside_h:
                    entry = float(c[t]); stop = float(inside_l) - stop_buf
                    stop_pts = entry - stop
                    if stop_pts > 0:
                        active = {"side": "LONG", "entry": entry, "stop": stop,
                                  "target": entry + target_R * stop_pts,
                                  "entry_bar": t, "size": sz(stop_pts)}
                elif c[t] < inside_l:
                    entry = float(c[t]); stop = float(inside_h) + stop_buf
                    stop_pts = stop - entry
                    if stop_pts > 0:
                        active = {"side": "SHORT", "entry": entry, "stop": stop,
                                  "target": entry - target_R * stop_pts,
                                  "entry_bar": t, "size": sz(stop_pts)}
    return trades


# ===========================================================================
# B. NR4 / NR7 breakout
# ===========================================================================
def nr_breakout(arr, n_bars=4, target_R=1.5, stop_buf=1.0, max_hold=20):
    o = arr[:, 0]; h = arr[:, 1]; l = arr[:, 2]; c = arr[:, 3]
    n = len(arr)
    ranges = h - l
    trades = []
    active = None
    for t in range(n_bars, n):
        if active is not None:
            stop_hit = (active["side"] == "LONG" and l[t] <= active["stop"]) or \
                       (active["side"] == "SHORT" and h[t] >= active["stop"])
            tgt_hit = (active["side"] == "LONG" and h[t] >= active["target"]) or \
                      (active["side"] == "SHORT" and l[t] <= active["target"])
            ex = None
            if stop_hit: ex = active["stop"]
            elif tgt_hit: ex = active["target"]
            elif t - active["entry_bar"] >= max_hold: ex = float(c[t])
            if ex is not None:
                pp = (active["entry"] - ex) if active["side"] == "SHORT" else (ex - active["entry"])
                pnl = pp * active["size"] * MNQ_PER_PT - COMM_PER_CONTRACT_RT * active["size"]
                trades.append({"pnl_usd": float(pnl), "side": active["side"]})
                active = None
        if active is None:
            # Check if bar t-1 has the narrowest range of last n_bars
            recent = ranges[t-n_bars:t]
            if ranges[t-1] == recent.min() and ranges[t-1] > 0:
                # Bar t is the trigger
                ref_h = float(h[t-1]); ref_l = float(l[t-1])
                if c[t] > ref_h:
                    entry = float(c[t]); stop = ref_l - stop_buf
                    stop_pts = entry - stop
                    if stop_pts > 0:
                        active = {"side": "LONG", "entry": entry, "stop": stop,
                                  "target": entry + target_R * stop_pts,
                                  "entry_bar": t, "size": sz(stop_pts)}
                elif c[t] < ref_l:
                    entry = float(c[t]); stop = ref_h + stop_buf
                    stop_pts = stop - entry
                    if stop_pts > 0:
                        active = {"side": "SHORT", "entry": entry, "stop": stop,
                                  "target": entry - target_R * stop_pts,
                                  "entry_bar": t, "size": sz(stop_pts)}
    return trades


# ===========================================================================
# C. Prior day H/L retest fade
# ===========================================================================
def prior_day_fade(arr, dates, buf_pts=3.0, target_R=1.0, max_hold=30):
    o = arr[:, 0]; h = arr[:, 1]; l = arr[:, 2]; c = arr[:, 3]
    n = len(arr)
    trades = []
    active = None
    prev_high = prev_low = None
    cur_high = cur_low = None
    current_date = None

    for t in range(n):
        d = dates[t]
        if d != current_date:
            if cur_high is not None:
                prev_high = cur_high; prev_low = cur_low
            cur_high = float(h[t]); cur_low = float(l[t])
            current_date = d
        else:
            cur_high = max(cur_high, float(h[t]))
            cur_low = min(cur_low, float(l[t]))

        if active is not None:
            stop_hit = (active["side"] == "LONG" and l[t] <= active["stop"]) or \
                       (active["side"] == "SHORT" and h[t] >= active["stop"])
            tgt_hit = (active["side"] == "LONG" and h[t] >= active["target"]) or \
                      (active["side"] == "SHORT" and l[t] <= active["target"])
            ex = None
            if stop_hit: ex = active["stop"]
            elif tgt_hit: ex = active["target"]
            elif t - active["entry_bar"] >= max_hold: ex = float(c[t])
            if ex is not None:
                pp = (active["entry"] - ex) if active["side"] == "SHORT" else (ex - active["entry"])
                pnl = pp * active["size"] * MNQ_PER_PT - COMM_PER_CONTRACT_RT * active["size"]
                trades.append({"pnl_usd": float(pnl), "side": active["side"]})
                active = None
        if active is None and prev_high is not None:
            # Sweep above prior day high then close below: SHORT
            if h[t] >= prev_high and c[t] < prev_high:
                entry = float(c[t])
                stop = float(h[t]) + buf_pts
                stop_pts = stop - entry
                if stop_pts > 0 and stop_pts < 30:  # sanity cap
                    target = entry - target_R * stop_pts
                    active = {"side": "SHORT", "entry": entry, "stop": stop,
                              "target": target, "entry_bar": t, "size": sz(stop_pts)}
            elif l[t] <= prev_low and c[t] > prev_low:
                entry = float(c[t])
                stop = float(l[t]) - buf_pts
                stop_pts = entry - stop
                if stop_pts > 0 and stop_pts < 30:
                    target = entry + target_R * stop_pts
                    active = {"side": "LONG", "entry": entry, "stop": stop,
                              "target": target, "entry_bar": t, "size": sz(stop_pts)}
    return trades


# ===========================================================================
# D. SD level fade
# ===========================================================================
def sd_fade(arr, dates, n_std=2.0, target_R=1.0, stop_buf=2.0, max_hold=20):
    """At each bar, compute today's running mean and std. Fade ±n_std excursions."""
    o = arr[:, 0]; h = arr[:, 1]; l = arr[:, 2]; c = arr[:, 3]
    n = len(arr)
    trades = []
    active = None
    current_date = None
    closes_today = []

    for t in range(n):
        d = dates[t]
        if d != current_date:
            current_date = d
            closes_today = [float(c[t])]
        else:
            closes_today.append(float(c[t]))

        if active is not None:
            stop_hit = (active["side"] == "LONG" and l[t] <= active["stop"]) or \
                       (active["side"] == "SHORT" and h[t] >= active["stop"])
            tgt_hit = (active["side"] == "LONG" and h[t] >= active["target"]) or \
                      (active["side"] == "SHORT" and l[t] <= active["target"])
            ex = None
            if stop_hit: ex = active["stop"]
            elif tgt_hit: ex = active["target"]
            elif t - active["entry_bar"] >= max_hold: ex = float(c[t])
            if ex is not None:
                pp = (active["entry"] - ex) if active["side"] == "SHORT" else (ex - active["entry"])
                pnl = pp * active["size"] * MNQ_PER_PT - COMM_PER_CONTRACT_RT * active["size"]
                trades.append({"pnl_usd": float(pnl), "side": active["side"]})
                active = None

        if active is None and len(closes_today) >= 30:
            mean = np.mean(closes_today[:-1])  # exclude current
            std = np.std(closes_today[:-1])
            if std == 0: continue
            upper = mean + n_std * std
            lower = mean - n_std * std
            if h[t] >= upper and c[t] < upper:
                entry = float(c[t])
                stop = float(h[t]) + stop_buf
                stop_pts = stop - entry
                if stop_pts > 0 and stop_pts < 30:
                    target = mean
                    target_pts = entry - target
                    if target_pts >= stop_pts * target_R:
                        active = {"side": "SHORT", "entry": entry, "stop": stop,
                                  "target": target, "entry_bar": t, "size": sz(stop_pts)}
            elif l[t] <= lower and c[t] > lower:
                entry = float(c[t])
                stop = float(l[t]) - stop_buf
                stop_pts = entry - stop
                if stop_pts > 0 and stop_pts < 30:
                    target = mean
                    target_pts = target - entry
                    if target_pts >= stop_pts * target_R:
                        active = {"side": "LONG", "entry": entry, "stop": stop,
                                  "target": target, "entry_bar": t, "size": sz(stop_pts)}
    return trades


# ===========================================================================
# E. Round number rejection (xx00 levels)
# ===========================================================================
def round_number_fade(arr, level_step=100.0, tol=2.0, target_R=1.5, stop_buf=2.0, max_hold=20):
    o = arr[:, 0]; h = arr[:, 1]; l = arr[:, 2]; c = arr[:, 3]
    n = len(arr)
    trades = []
    active = None
    for t in range(n):
        if active is not None:
            stop_hit = (active["side"] == "LONG" and l[t] <= active["stop"]) or \
                       (active["side"] == "SHORT" and h[t] >= active["stop"])
            tgt_hit = (active["side"] == "LONG" and h[t] >= active["target"]) or \
                      (active["side"] == "SHORT" and l[t] <= active["target"])
            ex = None
            if stop_hit: ex = active["stop"]
            elif tgt_hit: ex = active["target"]
            elif t - active["entry_bar"] >= max_hold: ex = float(c[t])
            if ex is not None:
                pp = (active["entry"] - ex) if active["side"] == "SHORT" else (ex - active["entry"])
                pnl = pp * active["size"] * MNQ_PER_PT - COMM_PER_CONTRACT_RT * active["size"]
                trades.append({"pnl_usd": float(pnl), "side": active["side"]})
                active = None
        if active is None:
            # nearest round above and below
            nearest_round_above = np.ceil(c[t] / level_step) * level_step
            nearest_round_below = np.floor(c[t] / level_step) * level_step
            # SHORT if bar touched round above and closed below
            if abs(h[t] - nearest_round_above) <= tol and c[t] < nearest_round_above:
                entry = float(c[t]); stop = float(h[t]) + stop_buf
                stop_pts = stop - entry
                if stop_pts > 0:
                    target = entry - target_R * stop_pts
                    active = {"side": "SHORT", "entry": entry, "stop": stop,
                              "target": target, "entry_bar": t, "size": sz(stop_pts)}
            elif abs(l[t] - nearest_round_below) <= tol and c[t] > nearest_round_below:
                entry = float(c[t]); stop = float(l[t]) - stop_buf
                stop_pts = entry - stop
                if stop_pts > 0:
                    target = entry + target_R * stop_pts
                    active = {"side": "LONG", "entry": entry, "stop": stop,
                              "target": target, "entry_bar": t, "size": sz(stop_pts)}
    return trades


# ===========================================================================
# F. 3-bar reversal patterns (engulfing / star)
# ===========================================================================
def three_bar_reversal(arr, target_R=1.5, stop_buf=1.0, max_hold=20):
    """Bearish engulfing: red bar fully engulfs prior green bar's body → SHORT
    Bullish engulfing: green bar fully engulfs prior red bar's body → LONG
    """
    o = arr[:, 0]; h = arr[:, 1]; l = arr[:, 2]; c = arr[:, 3]
    n = len(arr)
    trades = []
    active = None
    for t in range(2, n):
        if active is not None:
            stop_hit = (active["side"] == "LONG" and l[t] <= active["stop"]) or \
                       (active["side"] == "SHORT" and h[t] >= active["stop"])
            tgt_hit = (active["side"] == "LONG" and h[t] >= active["target"]) or \
                      (active["side"] == "SHORT" and l[t] <= active["target"])
            ex = None
            if stop_hit: ex = active["stop"]
            elif tgt_hit: ex = active["target"]
            elif t - active["entry_bar"] >= max_hold: ex = float(c[t])
            if ex is not None:
                pp = (active["entry"] - ex) if active["side"] == "SHORT" else (ex - active["entry"])
                pnl = pp * active["size"] * MNQ_PER_PT - COMM_PER_CONTRACT_RT * active["size"]
                trades.append({"pnl_usd": float(pnl), "side": active["side"]})
                active = None
        if active is None and t >= 2:
            # Bar t-1 = the signal bar (engulfing)
            prev_o = o[t-2]; prev_c = c[t-2]
            cur_o = o[t-1]; cur_c = c[t-1]
            # Bearish engulfing
            if prev_c > prev_o and cur_c < cur_o and \
               cur_o > prev_c and cur_c < prev_o:
                entry = float(o[t]); stop = float(h[t-1]) + stop_buf
                stop_pts = stop - entry
                if stop_pts > 0:
                    target = entry - target_R * stop_pts
                    active = {"side": "SHORT", "entry": entry, "stop": stop,
                              "target": target, "entry_bar": t, "size": sz(stop_pts)}
            # Bullish engulfing
            elif prev_c < prev_o and cur_c > cur_o and \
                 cur_o < prev_c and cur_c > prev_o:
                entry = float(o[t]); stop = float(l[t-1]) - stop_buf
                stop_pts = entry - stop
                if stop_pts > 0:
                    target = entry + target_R * stop_pts
                    active = {"side": "LONG", "entry": entry, "stop": stop,
                              "target": target, "entry_bar": t, "size": sz(stop_pts)}
    return trades


def main():
    print("Loading data...")
    nq = pd.read_csv(DATA_FILE, parse_dates=["ts"]).set_index("ts").sort_index()
    if nq.index.tz is None: nq.index = nq.index.tz_localize("UTC")
    months = (nq.index[-1] - nq.index[0]).days / 30.44
    ny = nq.index.tz_convert("America/New_York")
    dates = ny.date

    timeframes = ["1min", "3min", "5min", "15min"]

    def run_all(df):
        arr = df[["open","high","low","close"]].to_numpy()
        _dates = df.index.tz_convert("America/New_York").date if df.index.tz else df.index.date
        results = []
        # A. Inside bar
        for tR in [1.0, 1.5, 2.0]:
            for buf in [1.0, 2.0]:
                t = inside_bar_breakout(arr, target_R=tR, stop_buf=buf)
                s = stats(t, months_local)
                if s: results.append({"name": f"Inside-bar bo (R={tR}, buf={buf})", **s})
        # B. NR4 / NR7
        for nb in [4, 7]:
            for tR in [1.0, 1.5, 2.0]:
                t = nr_breakout(arr, n_bars=nb, target_R=tR)
                s = stats(t, months_local)
                if s: results.append({"name": f"NR{nb} bo (R={tR})", **s})
        # C. Prior day fade
        for tR in [0.5, 1.0, 1.5]:
            t = prior_day_fade(arr, _dates, target_R=tR)
            s = stats(t, months_local)
            if s: results.append({"name": f"PrevDay-fade (R={tR})", **s})
        # D. SD fade
        for ns in [1.5, 2.0, 2.5]:
            for tR in [0.5, 1.0, 1.5]:
                t = sd_fade(arr, _dates, n_std=ns, target_R=tR)
                s = stats(t, months_local)
                if s: results.append({"name": f"SD-fade (n_std={ns}, R={tR})", **s})
        # E. Round number
        for step in [50, 100]:
            for tR in [1.0, 1.5]:
                t = round_number_fade(arr, level_step=step, target_R=tR)
                s = stats(t, months_local)
                if s: results.append({"name": f"Round-num ({step}, R={tR})", **s})
        # F. Engulfing
        for tR in [1.0, 1.5, 2.0]:
            t = three_bar_reversal(arr, target_R=tR)
            s = stats(t, months_local)
            if s: results.append({"name": f"Engulfing (R={tR})", **s})
        return results

    for tf in timeframes:
        df = resample(nq, tf)
        months_local = (df.index[-1] - df.index[0]).days / 30.44
        results = run_all(df)
        print(f"\n{'='*100}\nTIMEFRAME: {tf}  (bars: {len(df):,}, months: {months_local:.1f})")
        print(f"{'='*100}")
        print(f"{'Strategy':<40} {'n':>5} {'/mo':>5} {'WR':>6} {'PF':>5} "
              f"{'RR':>5} {'$/tr':>6} {'Total':>8} {'DD%':>5} {'Ret/mo':>7}")
        results.sort(key=lambda x: -x["ret_per_mo"])
        for r in results:
            if r["n"] < 20: continue
            pf = f"{r['pf']:.2f}" if r['pf'] < 99 else "inf"
            tag = ""
            if hits_spec(r):
                tag = " ★★★★ HITS SPEC!"
            elif r["wr"] >= 0.55 and r["rr"] >= 1.2 and r["ret_per_mo"] >= 1.0:
                tag = " ★★"
            elif r["ret_per_mo"] >= 0.5:
                tag = " ★"
            elif r["total"] > 0:
                tag = " +"
            print(f"{r['name']:<40} {r['n']:>5} {r['trades_per_mo']:>4.1f} "
                  f"{r['wr']*100:>5.1f}% {pf:>5} {r['rr']:>4.2f} "
                  f"${r['per']:>+4,.0f} ${r['total']:>+6,.0f} "
                  f"{abs(r['maxdd_pct']):>4.1f}% {r['ret_per_mo']:>+5.2f}%{tag}")


if __name__ == "__main__":
    main()
