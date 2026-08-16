"""C1: does directional skill exist OUTSIDE US cash hours?

Every search in this repo -- 28,800 causal cells, the skill screen, the
HF screen, the premise tests -- filtered to RTH 13:30-20:00 UTC. The
Asian and European sessions have NEVER been tested. Different
participants, thinner books, more trending behaviour: there is no
reason to assume the same answer, and it costs nothing to ask.

Sessions (UTC):
  ASIA    22:00-06:00   Tokyo/Sydney; thinnest
  EUROPE  06:00-13:30   London; DAX/FTSE cash open at 08:00
  US_RTH  13:30-20:00   the only window ever tested (baseline)
  US_EXT  20:00-22:00   post-close

Same 14 signal families and market entries as skill_screen.py, so the
numbers are directly comparable to the RTH results already committed.

Costs differ by session and that matters: overnight spreads are wider,
so EV is reported at BOTH a half-tick (RTH-like) and a full-tick
(overnight-realistic) crossing cost.

Success bar, fixed before running: a session/signal/bracket must beat
33.3% target-first on 1:2 by enough to clear costs -- i.e. positive EV
at the full-tick assumption, with the RANDOM control in the same
session sitting at chance.

Output: research/SESSION_SCREEN.md
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse                  # noqa: E402
import causal_engine as ce   # noqa: E402

TV, TICK, COMM = 2.0, 0.25, 1.24
HZ = 600 * 1_000_000_000
BRACKETS = [(5.0, 10.0), (10.0, 20.0), (20.0, 40.0), (20.0, 10.0)]
SESSIONS = {
    "ASIA":   lambda m: (m >= 22 * 60) | (m < 6 * 60),
    "EUROPE": lambda m: (m >= 6 * 60) & (m < 13 * 60 + 30),
    "US_RTH": lambda m: (m >= 13 * 60 + 30) & (m < 20 * 60),
    "US_EXT": lambda m: (m >= 20 * 60) & (m < 22 * 60),
}


def build_signals(bc, bh, bl, bv, rng):
    n = len(bc)
    out = {}

    def sided(u, d):
        s = np.zeros(n, dtype=np.int8)
        s[u] = 1
        s[d] = -1
        return s

    for k, thr in ((3, 3.0), (10, 10.0)):
        d = np.full(n, np.nan)
        d[k:] = bc[k:] - bc[:-k]
        out[f"mom{k}_cont"] = sided(d >= thr, d <= -thr)
        out[f"mom{k}_fade"] = sided(d <= -thr, d >= thr)

    step = np.zeros(n)
    step[1:] = np.sign(bc[1:] - bc[:-1])
    run = np.zeros(n)
    for i in range(1, n):
        run[i] = run[i - 1] + step[i] if step[i] == step[i - 1] else step[i]
    out["streak3_cont"] = sided(run >= 3, run <= -3)
    out["streak3_fade"] = sided(run <= -3, run >= 3)

    s = pd.Series(bc)
    hi30 = s.rolling(30).max().values
    lo30 = s.rolling(30).min().values
    out["ext30_fade"] = sided(bc <= lo30, bc >= hi30)
    out["ext30_cont"] = sided(bc >= hi30, bc <= lo30)

    ma = s.rolling(120).mean().values
    sd = s.rolling(120).std().values
    out["band_fade"] = sided(bc < ma - 1.5 * sd, bc > ma + 1.5 * sd)
    out["band_cont"] = sided(bc > ma + 1.5 * sd, bc < ma - 1.5 * sd)

    vmed = pd.Series(bv).rolling(60).median().values
    spike = bv > 3.0 * np.maximum(vmed, 1)
    out["vspike_cont"] = sided(spike & (step > 0), spike & (step < 0))
    out["vspike_fade"] = sided(spike & (step < 0), spike & (step > 0))

    out["RANDOM"] = np.where(rng.random(n) < 0.25,
                             np.where(rng.random(n) < 0.5, 1, -1),
                             0).astype(np.int8)
    return out


def main():
    meta = fuse.tape_meta()
    cons = [c for c in fuse.NQ_CONTRACTS if c in meta]
    acc = {}
    sess_days = {k: set() for k in SESSIONS}
    rng = np.random.default_rng(31)
    for cn in cons:
        ts, px, sz = fuse.load_tape(meta[cn]["path"])
        o_ = np.argsort(ts, kind="stable")
        ts, px, sz = ts[o_], px[o_], sz[o_]
        idx = pd.to_datetime(ts)
        g = pd.Series(px, index=idx).resample("1min")
        bcs = g.last().ffill()
        bc = bcs.values
        bh = g.max().ffill().values
        bl = g.min().ffill().values
        bv = pd.Series(sz, index=idx).resample("1min").sum().values
        bt = bcs.index.view(np.int64)
        minute = (bcs.index.hour * 60 + bcs.index.minute).values
        dows = bcs.index.dayofweek.values
        weekday = dows < 5
        mi = ce.MinuteIndex(ts, px, bt)
        sig = build_signals(bc, bh, bl, bv, rng)

        for sname, smask in SESSIONS.items():
            in_s = smask(minute) & weekday
            sess_days[sname].update(
                pd.Series(bcs.index[in_s]).dt.normalize().unique())
            for name, arr in sig.items():
                fires = np.flatnonzero((arr != 0) & in_s)
                if not len(fires):
                    continue
                for i in fires:
                    side = int(arr[i])
                    t0 = int(bt[i]) + 60_000_000_000
                    j0 = np.searchsorted(ts, t0)
                    if j0 >= len(ts):
                        continue
                    entry = float(px[j0])
                    tend = t0 + HZ
                    jend = min(np.searchsorted(ts, tend), len(ts) - 1)
                    px_end = float(px[jend])
                    for (S, T) in BRACKETS:
                        a = acc.setdefault((sname, name, S, T),
                                           {"t": 0, "s": 0, "o": 0,
                                            "opnl": 0.0})
                        js = mi.first_beyond(t0, tend, entry - side * S,
                                             below=(side > 0),
                                             inclusive=True)
                        jt = mi.first_beyond(t0, tend, entry + side * T,
                                             below=(side < 0),
                                             inclusive=True)
                        st = int(ts[js]) if js >= 0 else None
                        tt = int(ts[jt]) if jt >= 0 else None
                        if tt is not None and (st is None or tt < st):
                            a["t"] += 1
                        elif st is not None:
                            a["s"] += 1
                        else:
                            # A trade that reaches neither barrier is NOT
                            # flat -- it is closed at the market when the
                            # clock runs out. Booking it at zero hides
                            # every loser that drifted against us without
                            # travelling the full stop distance, which is
                            # most of them when the stop is wide and the
                            # session is thin.
                            a["o"] += 1
                            a["opnl"] += side * (px_end - entry)
        del ts, px, sz, mi
        import gc
        gc.collect()
        print(f"{cn} done", flush=True)

    rows = []
    for (sname, name, S, T), d in acc.items():
        n = d["t"] + d["s"] + d["o"]
        if n < 1500:
            continue
        pt = d["t"] / n
        gross = (d["t"] * T * TV - d["s"] * S * TV
                 + d["opnl"] * TV) / n
        ev_half = gross - (TICK / 2) * TV - COMM
        ev_full = gross - TICK * TV - COMM
        tpd = n / max(len(sess_days[sname]), 1)
        rows.append((ev_full, ev_half, pt, tpd, sname, name, S, T, n,
                     d["o"] / n))
    rows.sort(reverse=True)

    L = ["# C1: is there directional skill outside US cash hours?", "",
         "Every prior search in this repo filtered to RTH 13:30-20:00 "
         "UTC. This runs the same signal families and market entries "
         "across all four sessions. NQ, 8 quarters.", "",
         "`EV half` charges a half-tick crossing (RTH-like); `EV full` "
         "charges a full tick (overnight-realistic). Both include "
         f"${COMM} commission.", "",
         "**A trade that reaches neither barrier is closed at the market "
         "when the clock runs out, and booked at that price.** The first "
         "version of this screen booked those at zero, which hides every "
         "loser that drifted against us without travelling the full stop "
         "distance. With a 20-point stop in a thin overnight session that "
         "is most of them: it made the 20/10 bracket look profitable in "
         "ASIA and EUROPE and, decisively, made the RANDOM control "
         "profitable too. The `timeout` column below is how big that "
         "bucket is, so the same thing cannot hide twice.", "",
         "| session | signal | bracket | n | trades/day | target first "
         "| timeout | EV half | EV full |", "|" + "---|" * 9]
    for ev_f, ev_h, pt, tpd, sname, name, S, T, n, po in rows[:30]:
        L.append(f"| {sname} | {name} | {S:.0f}/{T:.0f} | {n:,} | "
                 f"{tpd:.0f} | {pt:.2%} | {po:.0%} | ${ev_h:+.2f} | "
                 f"${ev_f:+.2f} |")

    L += ["", "## Per-session summary (best cell vs RANDOM in the SAME "
          "bracket)", "",
          "The control has to be read at the bracket the winner used. "
          "Comparing a 20/10 winner against a 10/20 RANDOM compares two "
          "different geometries and tells you nothing -- that mistake is "
          "what let the timeout artifact through the first time.", "",
          "| session | best signal | best target-first | best EV full | "
          "RANDOM (same bracket) EV | verdict |", "|" + "---|" * 6]
    for sname in SESSIONS:
        sub = [r for r in rows if r[4] == sname and r[5] != "RANDOM"]
        if not sub:
            continue
        best = sub[0]
        rnd = [r for r in rows if r[4] == sname and r[5] == "RANDOM"
               and r[6] == best[6] and r[7] == best[7]]
        if rnd:
            rev = float(rnd[0][0])
            verdict = ("**beats its control**" if best[0] > rev + 0.25
                       else "no better than random")
            L.append(f"| {sname} | {best[5]} {best[6]:.0f}/{best[7]:.0f} "
                     f"| {best[2]:.2%} | ${best[0]:+.2f} | ${rev:+.2f} | "
                     f"{verdict} |")
        else:
            L.append(f"| {sname} | {best[5]} {best[6]:.0f}/{best[7]:.0f} "
                     f"| {best[2]:.2%} | ${best[0]:+.2f} | n/a | "
                     f"no control at this bracket |")
    # A cell only counts if it beats the RANDOM control in its own
    # bracket and session. Positive EV on its own means nothing when the
    # control is positive too.
    ctl = {(r[4], r[6], r[7]): r[0] for r in rows if r[5] == "RANDOM"}
    pos = [r for r in rows if r[5] != "RANDOM" and r[0] > 0
           and r[0] > ctl.get((r[4], r[6], r[7]), -1e9) + 0.25]
    L += ["", f"**Cells positive at full-tick cost AND beating the "
          f"RANDOM control in their own session and bracket by at least "
          f"$0.25: {len(pos)} of {len(rows)}**", ""]
    for r in pos[:15]:
        L.append(f"- {r[4]} {r[5]} {r[6]:.0f}/{r[7]:.0f}: {r[2]:.2%} "
                 f"target-first, {r[9]:.0%} timed out, ${r[0]:+.2f}/trade "
                 f"vs ${ctl.get((r[4], r[6], r[7]), float('nan')):+.2f} "
                 f"random, {r[3]:.0f} trades/day over {r[8]:,} signals")
    L.append("")
    out = os.path.join(fuse.ROOT, "research", "SESSION_SCREEN.md")
    open(out, "w").write("\n".join(L) + "\n")
    print("\n".join(L[:40]))


if __name__ == "__main__":
    main()
