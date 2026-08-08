"""Trade it. One position at a time. Against a matched random-entry control.

SHARPEN said the confirmed NQ cell makes $2.56/trade out of sample at a
4000-price-change hold, clearing the $1.75-2.00 cost. Three things are wrong
with taking that at face value, and this file attacks all three:

  1  IT WAS A BOUNDARY CHOICE. The horizon sweep stopped at 4000 and was still
     climbing. A maximum at the edge of the grid is not a maximum, it is a
     grid that ended too early. Extended here to 16,000.

  2  THE SIGNALS OVERLAP. 344 signals per week each held 4000 price changes
     cannot all be taken -- an account holds one position at a time. The
     dollars-per-week figure was explicitly a ceiling. This replays them
     chronologically, skipping any signal that fires while a trade is open,
     which is the only frequency that means anything.

  3  NO CONTROL AT THIS HORIZON. Over a 4000-price-change window NQ moves a
     lot, and "buy and hold for 37 minutes" is a strategy that also makes
     money in a market that rose. The de-drift baseline handles that for
     means, but the equity curve deserves its own control, so every run is
     paired with RANDOM ENTRIES: the same count, the same contract, the same
     hold, entries drawn uniformly. If the cell cannot beat coin-flip timing
     with identical exposure, it is exposure and not timing.

Reports raw dollars, which is what the account receives, alongside the
de-drifted number, which is what is attributable to the behaviour. Costs are
charged once per round turn.

Usage: python replaycell.py
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DELAY", "1")
import sharpen as S  # noqa: E402  (loads the cached tapes and leg table)

OUT = os.path.join(S.ROOT, "research", "REPLAY_CELL.md")
USD = S.USD
COSTS = (1.75, 2.00)
DELAY = 1
HORIZONS = [int(x) for x in os.environ.get(
    "HZ", "1000,2500,4000,6000,8000,12000,16000").split(",")]
SEED = 12345
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def replay(sig_idx, cid, tape, F):
    """Chronological, non-overlapping. Returns (entry_i, pnl_ticks)."""
    n = len(tape)
    out = []
    last = -1
    for c in sig_idx:
        e = c + DELAY
        x = e + F
        if e <= last or x >= n:
            continue
        out.append((e, float(tape[x]) - float(tape[e])))
        last = x
    return out


def shift_control(sig_idx, tape, F, off):
    """The SAME signals, slid down the tape. Preserves the exact number of
    signals AND their clustering in time -- uniform-random entries do not,
    because real signals bunch in volatile stretches and a uniform draw
    spreads them evenly. Only the alignment with price is destroyed."""
    n = len(tape)
    return replay(np.sort((np.asarray(sig_idx) + off) % (n - F - 3)), 0,
                  tape, F)


def random_control(ntrades, tape, F, rng):
    """Same count, same hold, entries drawn uniformly, still non-overlapping."""
    n = len(tape)
    if ntrades == 0 or n <= F + 2:
        return []
    cand = np.sort(rng.choice(n - F - 2, size=min(ntrades * 4, n - F - 2),
                              replace=False))
    out, last = [], -1
    for e in cand:
        if e <= last:
            continue
        out.append((int(e), float(tape[e + F]) - float(tape[e])))
        last = e + F
        if len(out) >= ntrades:
            break
    return out


log("# Trading the confirmed cell: one position at a time, against a control")
log()
log("Signals are taken in chronological order; any signal that fires while a "
    "trade is open is skipped. The control takes the SAME number of trades in "
    "the same contract with the same hold, entering at random — identical "
    "exposure, no timing. Costs are charged once per round turn.")
log()

rng = np.random.default_rng(SEED)
rows = []
for F in HORIZONS:
    tr_pnl, ho_pnl, tr_ctl, ho_ctl = [], [], [], []
    ho_ts, ho_sft = [], []
    for i, name in enumerate(S.names):
        tape = S.tapes[i]
        m = S.BASE & (S.CID == i)
        conf = S.COL["conf"][m]
        order = np.argsort(conf, kind="stable")
        conf = conf[order]
        tsc = S.COL["tsconf"][m][order]
        tr = replay(conf, i, tape, F)
        if not tr:
            continue
        ctl = random_control(len(tr), tape, F, rng)
        sft = shift_control(conf, tape, F, len(tape) // 3)
        pn = [p * USD for _, p in tr]
        cn = [p * USD for _, p in ctl]
        sn = [p * USD for _, p in sft]
        # entry index -> timestamp of the confirming leg, for day/week buckets
        pos = {int(c) + DELAY: t for c, t in zip(conf, tsc)}
        ts = [pos.get(e, 0) for e, _ in tr]
        if name in S.TRAIN:
            tr_pnl += pn; tr_ctl += cn
        else:
            ho_pnl += pn; ho_ctl += cn; ho_ts += ts; ho_sft += sn
    if not ho_pnl:
        continue
    rows.append((F, np.mean(tr_pnl), len(tr_pnl), np.mean(ho_pnl),
                 len(ho_pnl), np.mean(ho_ctl), np.array(ho_pnl),
                 np.array(ho_ts), np.mean(ho_sft) if ho_sft else np.nan))

log("## 1. Non-overlapping, and against random entries with the same exposure")
log()
log("| hold | trades (holdout) | HOLDOUT gross $/trade | random entries | "
    "same signals slid down the tape | edge over the harder control | "
    "net @ $1.75 |")
log("|---|---|---|---|---|---|---|")
for F, trm, trn, hom, hon, ctm, _, _, sfm in rows:
    hard = np.nanmax([ctm, sfm])
    log(f"| {F} | {hon:,} | **${hom:+.2f}** | ${ctm:+.2f} | ${sfm:+.2f} | "
        f"**${hom - hard:+.2f}** | ${hom - 1.75:+.2f} |")
log()
log("The **difference** column is the one that matters. Gross dollars at a "
    "long hold are mostly exposure; only the gap over random entries with the "
    "same exposure is timing, and only timing is repeatable.")
log()

best = (max(rows, key=lambda r: r[3] - np.nanmax([r[5], r[8]]))
        if rows else None)
if best:
    F, trm, trn, hom, hon, ctm, arr, tsarr, sfm = best
    log(f"## 2. The account's experience at hold {F}")
    log()
    ts = pd.to_datetime(np.asarray(tsarr, dtype="int64"))
    T = pd.DataFrame({"t": ts, "g": arr}).sort_values("t")
    T = T[T.t.astype("int64") > 0]
    for cost in COSTS:
        T["net"] = T.g - cost
        day = T.groupby(T.t.dt.date).net.sum()
        wk = T.groupby(pd.Grouper(key="t", freq="W")).net.sum()
        wk = wk[wk != 0]
        eq = T.net.cumsum()
        wins = T.net > 0
        streak = worst = 0
        for w in wins.values:
            streak = 0 if w else streak + 1
            worst = max(worst, streak)
        wd, ld = day[day > 0], day[day <= 0]
        ww, lw = wk[wk > 0], wk[wk <= 0]
        log(f"### cost ${cost:.2f}/round turn, one micro contract")
        log()
        log("| metric | value |")
        log("|---|---|")
        log(f"| trades | {len(T):,} over {day.size} days "
            f"({len(T)/max(day.size,1):.1f}/day) |")
        log(f"| win rate | {wins.mean()*100:.1f}% |")
        log(f"| expectancy | **${T.net.mean():+.2f}** per trade |")
        log(f"| avg winner / loser | ${T.net[wins].mean():+.2f} / "
            f"${T.net[~wins].mean():+.2f} |")
        log(f"| **average day** | **${day.mean():+.2f}** |")
        log(f"| positive days | {len(wd)}/{day.size} "
            f"({len(wd)/max(day.size,1)*100:.0f}%) |")
        log(f"| average winning / losing day | ${wd.mean():+.2f} / "
            f"${ld.mean() if len(ld) else 0:+.2f} |")
        log(f"| best day / **WORST day** | ${day.max():+.2f} / "
            f"**${day.min():+.2f}** |")
        log(f"| **average week** | **${wk.mean():+.2f}** |")
        log(f"| positive weeks | {len(ww)}/{wk.size} |")
        log(f"| avg winning / losing week | ${ww.mean():+.2f} / "
            f"${lw.mean() if len(lw) else 0:+.2f} |")
        log(f"| best week / **WORST week** | ${wk.max():+.2f} / "
            f"**${wk.min():+.2f}** |")
        log(f"| max drawdown | ${(eq - eq.cummax()).min():+.2f} |")
        log(f"| longest losing streak | {worst} trades |")
        log(f"| contracts for $1,000/wk | "
            f"{'not reachable — weekly average is negative' if wk.mean() <= 0 else f'{1000/wk.mean():.0f} micros'} |")
        log()

log("---")
log("Held-out contracts only. Day and week boundaries are UTC. The random "
    "control uses a fixed seed so the comparison is reproducible.")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w").write("\n".join(L) + "\n")
print("\nwrote", OUT)
