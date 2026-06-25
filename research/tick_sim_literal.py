"""LITERAL tick-by-tick simulator — walks every tick in order and runs the
bot's exact entry/exit state machine, with every broker-restricting factor
from the diagnostic bundle switched on.

This is the from-scratch event-loop version (no per-trade shortcuts). It
exists to (a) honor "tick by tick, exactly like the bot" and (b) be an
independent cross-check of research/tick_sim.py (the optimized engine).

Factors applied (all from the 2026-06-25 bundle):
  1  commission $0.74 / MNQ round-trip
  2  $2 / pt / MNQ
  3  entry slip 0.0 (LIMIT at pullback level)
  4  stop slip 0.25 pt adverse (stop-market)
  5  target fills on the correct side of the spread (bid LONG / ask SHORT)
  6  timeout exit at mid @ 600 s
  7  cooldown 60 s after each close
  8  max-wait 300 s for the entry to fill, else setup expires
  9  single open position at a time
  10 setup dedup (same impulse hi/lo/side never re-fires)
  11 session break (no entries 17:00-18:00 ET + weekends)
  12 HTF trend filter OFF
  13 signal->order latency ~0 (negligible vs tick spacing)
  14 min target hold 0 s

Entry-fill rule (matches the bot's is_filled, driven by IMPULSE direction):
  up impulse   -> price falls to entry  -> fill when last price <= entry
  down impulse -> price rises to entry  -> fill when last price >= entry
Exit rule (matches should_exit_on_tick):
  LONG  stop: bid <= stop -> stop-0.25 ; tgt: bid >= target -> target
  SHORT stop: ask >= stop -> stop+0.25 ; tgt: ask <= target -> target
  timeout: mid at >= entry+600s
"""
from __future__ import annotations
import time
import numpy as np
import pandas as pd
from research.tick_sim import (load_ticks, build_1m_bars, precompute_setups,
                               _in_break_ns, stats, PT_VALUE, NS)

def simulate_literal(ticks, setups, *, cooldown_s=60, max_wait_s=300,
                     max_hold_s=600, stop_slip=0.25, comm_rt=0.74,
                     min_tgt_hold_s=0, n_mnq=1, block_breaks=True,
                     paper_ideal=False):
    """paper_ideal=True removes broker frictions (0 commission, 0 stop slip)
    to show the idealized 'paper' result for factor decomposition."""
    ts, price, bid, ask = ticks
    if paper_ideal:
        stop_slip = 0.0; comm_rt = 0.0
    det_ts = setups["det_ts"]; tdir = setups["trade_dir"]
    orig_up = setups["orig_up"]; entry = setups["entry"]
    stop = setups["stop"]; tgt = setups["tgt"]
    nset = len(det_ts); ntick = len(ts)
    brk = _in_break_ns(ts) if block_breaks else np.zeros(ntick, bool)

    max_wait = max_wait_s*NS; max_hold = max_hold_s*NS
    cooldown = cooldown_s*NS; min_hold = min_tgt_hold_s*NS

    # pending setups: list of dicts {exp, dir, up, e, s, t, armed}
    pending = []
    used = set()
    sp = 0                      # setup pointer (added when det_ts <= now)
    t_free = ts[0]             # earliest allowed entry time
    active = None              # dict for open trade
    trades = []

    for i in range(ntick):
        now = ts[i]; p = price[i]; b = bid[i]; a = ask[i]

        # --- inject setups whose detection time has arrived ---
        while sp < nset and det_ts[sp] <= now:
            key = (round(float(entry[sp]),2), round(float(stop[sp]),2), int(tdir[sp]))
            # dedup: skip if same key already used or already pending
            if key not in used and not any(ps["key"] == key for ps in pending):
                pending.append({"exp": det_ts[sp]+max_wait, "dir": int(tdir[sp]),
                                "up": bool(orig_up[sp]), "e": float(entry[sp]),
                                "s": float(stop[sp]), "t": float(tgt[sp]),
                                "armed": False, "key": key})
            sp += 1

        # --- STICKY ARM: arm every pending setup whose level is touched,
        #     on EVERY tick (even during an open trade or cooldown), exactly
        #     like the bot. Exit can only fire on ticks AFTER entry, so we
        #     arm/exit/fire in that order below. ---
        for ps in pending:
            if not ps["armed"]:
                if (ps["up"] and p <= ps["e"]) or ((not ps["up"]) and p >= ps["e"]):
                    ps["armed"] = True

        # --- manage open trade (exit on this tick; entry tick excluded
        #     because the trade was opened on a PRIOR tick) ---
        if active is not None:
            d = active["dir"]; hold = now - active["t_in"]
            ex = None; reason = None
            if d == 1:
                if b <= active["s"]:
                    ex = active["s"] - stop_slip; reason = "stop"
                elif b >= active["t"] and hold >= min_hold:
                    ex = active["t"]; reason = "target"
            else:
                if a >= active["s"]:
                    ex = active["s"] + stop_slip; reason = "stop"
                elif a <= active["t"] and hold >= min_hold:
                    ex = active["t"]; reason = "target"
            if ex is None and hold >= max_hold:
                ex = (b+a)/2.0; reason = "timeout"
            if ex is not None:
                pnl = d*(ex-active["e"])*PT_VALUE*n_mnq - comm_rt*n_mnq
                trades.append({"fire_ts": active["t_in"], "exit_ts": now,
                               "side": "LONG" if d==1 else "SHORT",
                               "entry": active["e"], "stop": active["s"],
                               "target": active["t"], "exit_px": round(ex,2),
                               "reason": reason, "hold_s": hold/NS, "pnl": pnl})
                used.add(active["key"])
                t_free = now + cooldown
                active = None
            else:
                continue   # still in the trade -> no new entry this tick

        # --- expire stale pending setups ---
        if pending:
            pending = [ps for ps in pending if ps["exp"] >= now and ps["key"] not in used]

        # --- FIRE an armed setup (only when free + not in break) ---
        if active is None and now >= t_free and not brk[i]:
            for ps in pending:
                if ps["armed"]:
                    active = {"t_in": now, "dir": ps["dir"], "e": ps["e"],
                              "s": ps["s"], "t": ps["t"], "key": ps["key"]}
                    used.add(ps["key"])
                    break
            if active is not None:
                pending = [ps for ps in pending if ps["key"] != active["key"]]

    df = pd.DataFrame(trades)
    if not df.empty:
        df["dt"] = pd.to_datetime(df["fire_ts"])
    return df


if __name__ == "__main__":
    t0 = time.time()
    ticks = load_ticks()
    bars = build_1m_bars(ticks[0], ticks[1])
    print(f"loaded {len(ticks[0]):,} ticks, {len(bars):,} bars  {time.time()-t0:.0f}s", flush=True)

    CONFIGS = {
        "ACTUAL BOT (bundle: s10/t20/p0.236/i5/w4 INV)":
            dict(IMPULSE_PTS=5.0, IMPULSE_WINDOW_BARS=4, PULLBACK_PCT=0.236,
                 STOP_PTS=10.0, TARGET_PTS=20.0, INVERT=True),
        "NEW DEFAULT (S2 winner: s5/t44/p0.118/i2/w3 INV)":
            dict(IMPULSE_PTS=2.0, IMPULSE_WINDOW_BARS=3, PULLBACK_PCT=0.118,
                 STOP_PTS=5.0, TARGET_PTS=44.0, INVERT=True),
    }
    for label, params in CONFIGS.items():
        setups = precompute_setups(bars, params)
        t1 = time.time()
        df = simulate_literal(ticks, setups)
        print(f"\n=== {label} ===  (literal tick-by-tick, {time.time()-t1:.0f}s)")
        print("  BROKER-FAITHFUL (all factors):", stats(df))
        # factor decomposition: idealized paper vs broker-faithful
        df_ideal = simulate_literal(ticks, setups, paper_ideal=True)
        s_ideal = stats(df_ideal); s_real = stats(df)
        if s_ideal["n"] and s_real["n"]:
            print(f"  PAPER-IDEAL (0 comm, 0 slip):   per_day=${s_ideal['per_day']}")
            print(f"  cost of frictions: ${round(s_ideal['per_day']-s_real['per_day'],1)}/day "
                  f"(comm+slip across ~{s_real['tr_per_day']} tr/day)")
    print(f"\ntotal {time.time()-t0:.0f}s")
