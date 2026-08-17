"""Exits: stop and target, not just "hold for N seconds".

WHY THIS WAS THE BIGGEST HOLE. Every hypothesis the searcher tested
exited on a timer. That makes it a PREDICTION -- "price will be higher
in five minutes" -- and predictions are not strategies. It is also why
every win rate came out near 50% with a reward-to-risk near 1.0: a
symmetric time exit produces a symmetric outcome distribution almost by
construction, so those two columns carried no information at all.

A real strategy says where it gets out when it is wrong and where it
takes the money when it is right. Those two numbers change everything
downstream -- the win rate, the reward-to-risk, the shape of the tail,
and how much of the account a single trade can cost. They are not extra
parameters bolted onto a signal; they are half of what a strategy is.

THE INTRABAR AMBIGUITY, and the only honest way to resolve it.

With OHLC bars you know the high and the low of each bar but not the
order they happened in. When a bar's low reaches the stop AND its high
reaches the target, both were touched and the bar cannot tell you which
came first. Assuming the target is a choice that pays you for your own
ignorance, and it is exactly the class of optimism that has produced
every false positive in this project.

    STOP ALWAYS WINS A TIED BAR.

That is pessimistic, it is wrong some of the time, and being wrong in
this direction costs a real strategy a little while refusing to invent
a fake one. `resolution_cost()` reports how often the tie occurred, so
the size of the assumption is visible rather than buried.

Stops and targets are set in units of realised volatility rather than
points, so one specification means the same thing on MNQ at 21,000 and
on 6J at 0.0066. A fixed point stop is a different strategy in every
market.
"""
from __future__ import annotations

import numpy as np


def atr(high, low, close, w=60):
    """Average true range, the natural unit for a stop."""
    h, low_, c = (np.asarray(x, dtype=float) for x in (high, low, close))
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - low_, np.maximum(np.abs(h - pc), np.abs(low_ - pc)))
    out = np.full(len(tr), np.nan)
    if len(tr) >= w:
        cs = np.cumsum(np.insert(tr, 0, 0.0))
        out[w - 1:] = (cs[w:] - cs[:-w]) / w
    return out


def run(entry_idx, side, high, low, close, stop_mult, target_mult,
        vol_unit, max_bars, open_=None):
    """Triple barrier: stop, target, or time. Returns exit price and why.

    Vectorised over TRADES and looped over BARS -- max_bars passes of
    numpy rather than one Python loop per trade. At 60 bars and 50,000
    trades that is 60 array operations instead of three million
    interpreter steps.

    Returns (exit_price, bars_held, reason) where reason is
    0=stop 1=target 2=timeout, and `ties` counts bars where both
    barriers were touched and the stop was awarded the fill.
    """
    e = np.asarray(entry_idx, dtype=np.int64)
    s = np.asarray(side, dtype=float)
    n = len(e)
    h, lo, c = (np.asarray(x, dtype=float) for x in (high, low, close))
    u = np.asarray(vol_unit, dtype=float)[e]

    entry_px = c[e]
    stop_px = entry_px - s * stop_mult * u
    tgt_px = entry_px + s * target_mult * u

    exit_px = np.full(n, np.nan)
    held = np.full(n, max_bars, dtype=np.int64)
    reason = np.full(n, 2, dtype=np.int8)
    active = np.ones(n, dtype=bool)
    ties = 0
    last = len(c) - 1

    for k in range(1, max_bars + 1):
        j = e + k
        valid = active & (j <= last)
        if not valid.any():
            break
        jj = np.where(valid, j, 0)
        bh, bl = h[jj], lo[jj]

        longs = valid & (s > 0)
        shorts = valid & (s < 0)
        s_hit = np.zeros(n, dtype=bool)
        t_hit = np.zeros(n, dtype=bool)
        s_hit[longs] = bl[longs] <= stop_px[longs]
        t_hit[longs] = bh[longs] >= tgt_px[longs]
        s_hit[shorts] = bh[shorts] >= stop_px[shorts]
        t_hit[shorts] = bl[shorts] <= tgt_px[shorts]

        # THE TIE. Both barriers touched in one bar; the order is
        # unknowable from OHLC. The stop is awarded the fill.
        both = s_hit & t_hit
        ties += int(both.sum())
        t_hit = t_hit & ~s_hit

        # A STOP DOES NOT ALWAYS FILL AT THE STOP PRICE. If the bar
        # OPENED beyond it, the market gapped through and the fill is
        # the open, not the level. Assuming the level is the same
        # "filled at a price the market has left" error that produced
        # five earlier false positives here -- and it is asymmetric,
        # because only the stop side benefits.
        #
        # Measured on random entries, zero cost, a driftless walk:
        #     stop 1.0 / target 2.0   +$0.452/trade   before this
        # Free money, manufactured entirely by tight stops filling
        # perfectly. A target is left at its level: a resting limit at
        # the target really does fill there when price trades through.
        if s_hit.any():
            fill = stop_px.copy()
            if open_ is not None:
                op = open_[jj]
                worse = np.where(s > 0, np.minimum(fill, op),
                                 np.maximum(fill, op))
                fill = np.where(s_hit, worse, fill)
            exit_px[s_hit] = fill[s_hit]
            held[s_hit] = k
            reason[s_hit] = 0
            active[s_hit] = False
        if t_hit.any():
            exit_px[t_hit] = tgt_px[t_hit]
            held[t_hit] = k
            reason[t_hit] = 1
            active[t_hit] = False

    # anything still open exits at the timeout bar's close
    if active.any():
        j = np.minimum(e[active] + max_bars, last)
        exit_px[active] = c[j]
        held[active] = j - e[active]
    return exit_px, held, reason, ties


def pnl(entry_idx, side, high, low, close, stop_mult, target_mult,
        vol_unit, max_bars, tv, cost, open_=None):
    """Net P&L per trade under a bracket, plus the outcome mix."""
    c = np.asarray(close, dtype=float)
    ex, held, reason, ties = run(entry_idx, side, high, low, c,
                                 stop_mult, target_mult, vol_unit, max_bars,
                                 open_=open_)
    s = np.asarray(side, dtype=float)
    gross = s * (ex - c[np.asarray(entry_idx, dtype=np.int64)])
    ok = np.isfinite(gross)
    net = gross[ok] * tv - cost
    return {
        "net": net, "held": held[ok], "reason": reason[ok],
        "ties": ties,
        "stopped": float(np.mean(reason[ok] == 0)) if ok.any() else 0.0,
        "targeted": float(np.mean(reason[ok] == 1)) if ok.any() else 0.0,
        "timed": float(np.mean(reason[ok] == 2)) if ok.any() else 0.0,
    }


def resolution_cost(ties, n):
    """How much of the result rests on the tie-breaking assumption."""
    if not n:
        return 0.0
    return round(ties / n, 4)


# --------------------------------------------------------- self-test
def selftest():
    """Hand-checkable cases. Every one is verifiable by eye.

    A barrier engine that is subtly wrong does not error -- it just
    reports a better strategy than exists, which is the failure this
    project keeps finding. So the cases below are trivial on purpose.
    """
    fails = []
    # bar 0 entry at 100. unit=1, stop 2 -> 98, target 2 -> 102
    #   bar1 low 97  : stop hit
    #   bar2 high 103: target (but trade already closed)
    c = np.array([100., 100., 100., 100., 100.])
    h = np.array([100., 100.5, 103., 100., 100.])
    lo = np.array([100., 97., 99., 100., 100.])
    u = np.ones(5)
    ex, held, rsn, ties = run([0], [1.0], h, lo, c, 2, 2, u, 4)
    if not (ex[0] == 98 and held[0] == 1 and rsn[0] == 0):
        fails.append(f"long stop: got px={ex[0]} held={held[0]} rsn={rsn[0]}")

    # target first, stop never touched
    h2 = np.array([100., 100.5, 103., 100., 100.])
    lo2 = np.array([100., 99.5, 99., 100., 100.])
    ex, held, rsn, _ = run([0], [1.0], h2, lo2, c, 2, 2, u, 4)
    if not (ex[0] == 102 and held[0] == 2 and rsn[0] == 1):
        fails.append(f"long target: got px={ex[0]} held={held[0]} rsn={rsn[0]}")

    # neither touched -> timeout at close
    h3 = np.array([100., 100.5, 100.5, 100.5, 100.5])
    lo3 = np.array([100., 99.5, 99.5, 99.5, 99.5])
    c3 = np.array([100., 100.1, 100.2, 100.3, 100.4])
    ex, held, rsn, _ = run([0], [1.0], h3, lo3, c3, 2, 2, u, 4)
    if not (abs(ex[0] - 100.4) < 1e-9 and rsn[0] == 2):
        fails.append(f"timeout: got px={ex[0]} rsn={rsn[0]}")

    # THE TIE: one bar touches both. Stop must win.
    h4 = np.array([100., 103., 100., 100., 100.])
    lo4 = np.array([100., 97., 100., 100., 100.])
    ex, held, rsn, ties = run([0], [1.0], h4, lo4, c, 2, 2, u, 4)
    if not (ex[0] == 98 and rsn[0] == 0 and ties == 1):
        fails.append(f"tie must go to the stop: px={ex[0]} rsn={rsn[0]} "
                     f"ties={ties}")

    # GAP THROUGH THE STOP: the bar OPENS below it, so the fill is the
    # open and not the level. This is the asymmetry that handed tight
    # stops free money on random data.
    op = np.array([100., 95., 100., 100., 100.])
    ex, held, rsn, _ = run([0], [1.0], h, lo, c, 2, 2, u, 4, open_=op)
    if abs(ex[0] - 95.0) > 1e-9:
        fails.append(f"gap through stop should fill at the open 95, "
                     f"got {ex[0]}")

    # SHORT: mirror of case 1. stop is ABOVE entry.
    ex, held, rsn, _ = run([0], [-1.0], h2, lo2, c, 2, 2, u, 4)
    if not (ex[0] == 102 and rsn[0] == 0):
        fails.append(f"short stop: px={ex[0]} rsn={rsn[0]}")
    return fails


if __name__ == "__main__":
    f = selftest()
    print("brackets selftest:", "PASS" if not f else "FAIL")
    for x in f:
        print("  ", x)
