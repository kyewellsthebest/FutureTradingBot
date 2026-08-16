"""Can 161 trades/day and a 44-point target both be true?

The leaderboard claims ~161 trades/day per MNQ with a 30-44pt target hit
10-17% of the time. Run through the validated engine at the live bot's
one-position-with-lockout semantics, the same parameters produce 24
trades/day. That is a 6.7x gap and only two things can close it:

  SHORT HOLD       390 RTH minutes / 161 trades = 2.4 min a cycle, so
                   with a 60s cooldown the hold is about 90 seconds.
                   Sigma over 90s on NQ is ~14 points. A 44-point target
                   would then be a 3-sigma move, and it is claimed to hit
                   once every six trades.
  OVERLAP          many positions open at once. Then "1 MNQ" is not one
                   contract: P&L accrues to every open position while
                   commission is charged once per signal. This is the
                   same overlap inflation documented in
                   fusion_ceiling.score(), where gross was inflated by
                   roughly h and cost was not.

This measures both branches directly. For each hold it reports the trade
rate and the target-hit rate the engine actually finds, so the claimed
combination can be checked against the tape rather than argued about.

Output: research/LEADERBOARD_HOLDS.md
"""
import gc
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse                  # noqa: E402
import causal_engine as ce   # noqa: E402

TICK, TV, COMM = 0.25, 2.0, 1.33
BASE = dict(imp=2.0, w=3, retr=0.118, S=5.0, T=44.0)
HOLDS = [60, 90, 120, 300, 600]
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def main():
    meta = fuse.tape_meta()
    cons = [c for c in fuse.NQ_CONTRACTS if c in meta][:4]
    acc = {}
    days = 0
    for cn in cons:
        ts, px, _ = fuse.load_tape(meta[cn]["path"])
        o_ = np.argsort(ts, kind="stable")
        ts, px = ts[o_], px[o_]
        bt, bo, bh, bl, bc, rth = ce.bars_ohlc(ts, px)
        mi = ce.MinuteIndex(ts, px, bt)
        days += len(np.unique(pd.to_datetime(bt[rth]).normalize().values))
        for h in HOLDS:
            for lk in ("window", "none"):
                cell = dict(BASE, hold_s=h, tick=TICK, tv=TV, comm=COMM,
                            anchor="range", bo=bo, bh=bh, bl=bl,
                            arch="stop", lockout=lk)
                tr = ce.run_cell(ts, px, bt, bc, rth, 0, len(bc), cell,
                                 mindex=mi)
                a = acc.setdefault((h, lk), {"pnl": [], "tgt": 0, "n": 0})
                a["pnl"].extend(t[4] for t in tr)
                a["tgt"] += sum(1 for t in tr if t[3] == "target")
                a["n"] += len(tr)
        del ts, px, mi
        gc.collect()
        print(f"{cn} done", flush=True)

    log("# Can 161 trades/day and a 44-point target both be true?")
    log()
    log("The leaderboard claims ~161 trades/day per MNQ with a 44-point "
        "target hit 10-17% of the time. The same parameters through the "
        "validated engine, one position with the live bot's lockout, "
        "give 24 trades/day. Only two things close a 6.7x gap: a much "
        "SHORTER HOLD, or OVERLAPPING positions -- and if it is overlap, "
        "\"1 MNQ\" is not one contract, because P&L accrues to every "
        "open position while commission is charged once per signal.")
    log()
    log(f"NQ, {len(cons)} quarters, {days} RTH sessions, config #1 "
        f"(impulse 2, window 3, pull 0.118, stop 5, target 44), honest "
        f"stop-entry fills, ${COMM:.2f} round trip.")
    log()
    log("`lockout=window` is one position at a time -- the live bot's "
        "actual behaviour. `lockout=none` lets windows overlap, which is "
        "the only way to reach the claimed trade rate.")
    log()
    log("| hold | lockout | trades/day | target-hit % | $/trade | $/day |")
    log("|" + "---|" * 6)
    for h in HOLDS:
        for lk in ("window", "none"):
            a = acc[(h, lk)]
            n = max(a["n"], 1)
            log(f"| {h}s | {lk} | {a['n']/max(days,1):.0f} | "
                f"{a['tgt']/n:.1%} | ${sum(a['pnl'])/n:+.2f} | "
                f"${sum(a['pnl'])/max(days,1):+,.0f} |")
    log()
    log("## Reading this")
    log()
    log("Find the row whose trade rate is near 161. Then read its "
        "target-hit column and compare it with the claimed 10-17%, and "
        "read its lockout column to see whether that rate required "
        "overlapping positions. The claim needs a single row where the "
        "trade rate, the hit rate and one contract are all true at once.")
    log()
    open(os.path.join(fuse.ROOT, "research",
                      "LEADERBOARD_HOLDS.md"), "w").write("\n".join(L) + "\n")
    print("wrote research/LEADERBOARD_HOLDS.md")


if __name__ == "__main__":
    main()
