"""CAUSAL re-validation of the pulse cells: first-cross-wins fills.

pulse.py contained a non-causal artifact: overlapping signal windows
were awarded to the earlier SIGNAL even when a later signal's limit
crossed first in real time. No real system can trade that.

This validator implements the executable semantics the live bot now
runs (STRAT_VALIDATED_FILLS):

  - a signal bar (RTH by bar start, |close-to-close move over W| >= imp,
    not inside the post-fill lock) arms a resting limit at
    close - retr*move (tick-rounded toward harder-to-fill), alive 600s
  - all armed limits rest simultaneously; the FIRST print that trades
    strictly through any armed level (respecting each window's own arm
    time + 250ms latency) fills that level, at the level
  - single position: fills are blocked until the previous trade's exit
    + 60s; new signal bars are blocked until the filled window's end
    + 60s (the bot's pulse_lock_until)
  - exits on prints: gap-aware stop + 1 tick slip, strict-penetration
    target, timeout at the window end on the last in-window print
    (1 tick), $1.24 RT

Held-out segments (same 60/40 split). Writes research/CAUSAL.md and
data/causal_trades_{SYM}.json.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402

TRAIN = 0.60
COMM = 1.24
DELAY_NS = 250_000_000
WIN_NS = 600 * 1_000_000_000
COOL_NS = 60 * 1_000_000_000
W = 6
RETR = 0.618
BAR_NS = 60_000_000_000

MKTS = {
    "NQ": dict(imp=5.0, S=10.0, T=20.0, tv=2.0, tick=0.25),
    "ES": dict(imp=1.5, S=3.0, T=6.0, tv=5.0, tick=0.25),
    "YM": dict(imp=16.0, S=20.0, T=40.0, tv=0.5, tick=1.0),
}
ONLY = [s for s in os.environ.get("CAUSAL_ONLY", "").split(",") if s]


def run_span(ts, px, bt, bc, rth, lo, hi, cfg):
    """Causal engine over bars [lo, hi). Returns trade tuples
    (entry_ts_ns, side, entry, exit_reason, pnl_usd)."""
    imp, S, T, tv, tick = cfg["imp"], cfg["S"], cfg["T"], cfg["tv"], \
        cfg["tick"]
    trades = []
    windows = []            # [arm_ns, exp_ns, lvl, side(+1/-1)]
    lock_until = -10**18    # blocks NEW signal bars
    nofill_until = -10**18  # blocks fills (in-trade + 60s cooldown)
    n = len(ts)
    for i in range(max(lo, W + 1), hi):
        bclose = bt[i] + BAR_NS
        # 1. arm this bar's signal window
        if rth[i] and bclose >= lock_until:
            move = bc[i] - bc[i - W]
            if abs(move) >= imp:
                up = move > 0
                raw = bc[i] - RETR * move
                lvl = (np.floor(raw / tick) if up
                       else np.ceil(raw / tick)) * tick
                windows.append([bclose + DELAY_NS, bclose + WIN_NS,
                                float(lvl), 1 if up else -1])
        if not windows:
            continue
        # 2. fills inside this bar's minute (loop: exit + refill possible)
        j0 = np.searchsorted(ts, bclose)
        j1 = np.searchsorted(ts, bclose + BAR_NS)
        while j0 < j1:
            seg = px[j0:j1]
            tseg = ts[j0:j1]
            best = None     # (local_idx, window)
            for w in windows:
                a_ns, e_ns, lvl, side = w
                m = (tseg >= max(a_ns, nofill_until)) & (tseg < e_ns)
                hit = np.flatnonzero(m & ((seg < lvl) if side > 0
                                          else (seg > lvl)))
                if len(hit) and (best is None or hit[0] < best[0]):
                    best = (hit[0], w)
            if best is None:
                break
            fidx = j0 + best[0]
            a_ns, e_ns, lvl, side = best[1]
            # resolve the trade instantly over its remaining window
            kend = np.searchsorted(ts, e_ns)
            rest = px[fidx:kend]
            stop = lvl - side * S
            tgt = lvl + side * T
            if side > 0:
                si = np.flatnonzero(rest <= stop)
                ti = np.flatnonzero(rest > tgt)
            else:
                si = np.flatnonzero(rest >= stop)
                ti = np.flatnonzero(rest < tgt)
            s_at = si[0] if len(si) else 10**9
            t_at = ti[0] if len(ti) else 10**9
            if t_at < s_at:
                gain, reason, x_at = T * tv, "target", t_at
            elif s_at < 10**9:
                xp = rest[s_at]
                ex = min(xp, stop) if side > 0 else max(xp, stop)
                gain, reason, x_at = (side * (ex - lvl) - tick) * tv, \
                    "stop", s_at
            else:
                # timeout: the bot flattens on the FIRST print at/after
                # the window end (realistic instant-close), not pulse's
                # last in-window print
                xpx = px[kend] if kend < n else rest[-1]
                gain, reason, x_at = \
                    (side * (xpx - lvl) - tick) * tv, "timeout", \
                    len(rest) - 1
            exit_ns = int(ts[min(fidx + x_at, n - 1)])
            trades.append((int(ts[fidx]), side, float(lvl), reason,
                           float(gain - COMM)))
            lock_until = e_ns + COOL_NS
            # the bot's pulse_lock_until blocks FIRES too, not just new
            # signal bars -- re-entry earliest at window end + 60s
            nofill_until = max(exit_ns, e_ns) + COOL_NS
            windows = [w for w in windows if w is not best[1]]
            j0 = fidx + x_at + 1
        windows = [w for w in windows if w[1] > bclose + BAR_NS]
    return trades


def quarter_arrays(path):
    ts, px, _ = fuse.load_tape(path)
    idx = pd.to_datetime(ts)
    close = pd.Series(px, index=idx).resample("1min").last().ffill()
    bt = close.index.view(np.int64)
    bc = close.values
    rth = (close.index.hour * 60 + close.index.minute >= 13 * 60 + 30) & \
          (close.index.hour < 20)
    return ts, px, bt, bc, rth


def main():
    meta = fuse.tape_meta()
    L = ["# CAUSAL re-validation: first-cross-wins (the executable "
         "semantics)", "",
         "pulse.py's window accounting was non-causal (earlier-signal-"
         "wins on overlaps). These are the numbers a real resting-limit "
         "book can earn: same cells, same costs, held-out segments.", ""]
    for sym, cfg in MKTS.items():
        if ONLY and sym not in ONLY:
            continue
        if sym == "NQ":
            cons = [c for c in fuse.NQ_CONTRACTS if c in meta]
        else:
            cons = sorted((c for c, v in meta.items() if v["sym"] == sym
                           and v["n"] > 3_000_000),
                          key=lambda c: meta[c]["t0"])
        all_tr = []
        rows = []
        for cn in cons:
            ts, px, bt, bc, rth = quarter_arrays(meta[cn]["path"])
            cut = int(len(bc) * TRAIN)
            tr = run_span(ts, px, bt, bc, rth, cut, len(bc), cfg)
            all_tr += tr
            tot = sum(t[4] for t in tr)
            rows.append((cn, tot, len(tr)))
            print(f"  {sym} {cn}: ${tot:+,.0f} on {len(tr)}", flush=True)
        pnl = np.array([t[4] for t in all_tr])
        ets = np.array([t[0] for t in all_tr], dtype=np.int64)
        daily = pd.Series(pnl, index=pd.to_datetime(ets)).resample("D").sum()
        daily = daily[daily != 0]
        eq = daily.cumsum()
        dd = float((eq - eq.cummax()).min()) if len(eq) else 0.0
        wk = len(daily) / 5 if len(daily) else 1
        g = sum(1 for _, p, _ in rows if p > 0)
        L += [f"## {sym}: held-out **${pnl.sum():+,.0f}** on "
              f"{len(all_tr)} trades ({len(all_tr)/max(wk,1):.0f}/wk), "
              f"{g}/{len(rows)} quarters green, max DD "
              f"${abs(dd):,.0f}", ""]
        for cn, tot, nn in rows:
            L.append(f"- {cn}: ${tot:+,.0f} on {nn}")
        wins = pnl > 0
        L += ["", f"- win rate {wins.mean():.1%}, "
              f"{len(daily)} days {float((daily > 0).mean()):.0%} green, "
              f"best ${daily.max():+,.0f} worst ${daily.min():+,.0f}", ""]
        json.dump([{"ts": int(t[0]), "side": t[1], "entry": t[2],
                    "exit": t[3], "pnl": round(t[4], 2)} for t in all_tr],
                  open(os.path.join(fuse.ROOT, "data",
                                    f"causal_trades_{sym}.json"), "w"))
    open(os.path.join(fuse.ROOT, "research", "CAUSAL.md"),
         "w").write("\n".join(L) + "\n")
    print("wrote research/CAUSAL.md", flush=True)


if __name__ == "__main__":
    main()
