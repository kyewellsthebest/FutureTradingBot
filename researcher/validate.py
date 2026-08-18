"""The rest of the gauntlet: the checks my own process runs that the
daemon did not.

The bot already had the rising bar, the sealed vault, the planted-edge
self-test, the one-bar delay control, the overlap correction and a
spread-inclusive cost model. Four things were missing, and every one of
them has caught something real in this repo before.

  1  ALL-CELL EMPIRICAL NULL. The theoretical bar assumes independent
     trials. They are not independent -- hypotheses in a family share
     buckets, share horizons, and overlap in time -- so sqrt(2 ln N) is
     the wrong shape. The honest substitute is to measure the actual
     distribution of z across every cell tested in this sweep and
     require a candidate to beat its p99. There is no Bonferroni
     anywhere in this repo and this is why: the empirical null is
     better and it costs nothing, because the cells are already scored.

  2  PERIOD STABILITY. An edge that lives in one quarter and nowhere
     else is a regime, an event, or luck. Requiring the sign to hold
     across most sub-periods is the cheapest way to tell a persistent
     effect from a single lucky stretch, and it is the check that
     killed most of this project's earlier candidates.

  3  STALE PLACEBO. Shift the signal thirty minutes and re-run. A real
     signal should DIE. If the stale copy performs as well, the signal
     is not doing the work -- something slower is, and it is probably
     the conditioning or the drift.

  4  CROSS-MARKET REPLICATION. Before spending the one permitted look
     at held-back data, require the effect to show the same sign in an
     INDEPENDENT market bloc. Four equity indices agreeing is about one
     observation; NQ and ZN agreeing is two. The vault is finite, and
     spending it on something that only exists in one market is how it
     gets used up on noise.

ORDER MATTERS. These run cheapest-first and all of them run BEFORE the
vault, because the vault is the only irreversible resource in the
system.
"""
from __future__ import annotations

import numpy as np


def empirical_null(zs, q=99.0, two_sided=False):
    """How HIGH does this sweep's own machinery push z on everything?

    Returns the qth percentile of z over every cell scored. A candidate
    has to beat the level its own siblings reached, which automatically
    accounts for however much dependence there is between them -- the
    thing a theoretical correction cannot know.

    ONE-SIDED, AND THE REASON MATTERS. This used to take the percentile
    of |z|, which on a real tape is not a null at all. Measured on NQ
    60-second bars over 399 cells:

        z > 10       occurred   0 times
        |z| > 10     occurred  39 times, every one of them negative
        p99 of z     2.49
        p99 of |z|  27.13

    A cell that trades twenty thousand times and pays the round trip on
    every one of them reaches z = -27 with total certainty. That is
    arithmetic, not chance, and folding it in demanded that a winner be
    ten times stronger than the most confident LOSER before it counted.
    The searcher only ever promotes a positive net, so the question the
    null has to answer is one-sided: of everything tried on this tape,
    how high did z actually get? Reading the loss tail as a null was
    making the strictest control in the system reject real edges for a
    reason that has nothing to do with them.

    two_sided=True returns the old figure, kept so the two can be
    reported side by side rather than the change being invisible.
    """
    v = np.asarray([z for z in zs if np.isfinite(z)], dtype=float)
    if len(v) < 200:
        return None
    return float(np.percentile(np.abs(v) if two_sided else v, q))


def period_stability(pnl, idx, k=6):
    """Does the sign hold across sub-periods, or live in one of them?

    Splits chronologically into k equal blocks and reports the share
    with the same sign as the whole. Chronological, not random: random
    folds scatter a regime across every block and hide exactly the
    failure this is looking for.
    """
    n = len(pnl)
    if n < k * 30:
        return None
    whole = float(np.mean(pnl))
    if whole == 0:
        return None
    sign = np.sign(whole)
    edges = np.linspace(0, n, k + 1).astype(int)
    means = []
    for i in range(k):
        seg = pnl[edges[i]:edges[i + 1]]
        if len(seg) < 10:
            continue
        means.append(float(np.mean(seg)))
    if len(means) < max(3, k - 2):
        return None
    agree = sum(1 for m in means if np.sign(m) == sign)
    return {"blocks": len(means), "agree": agree,
            "share": round(agree / len(means), 3),
            "block_means": [round(m, 5) for m in means]}


def stale_placebo(evaluate, tape, hyp, tv, cost, feats, bar_s,
                  shift_s=1800):
    """Shift the SIGNAL, keep the returns. A real edge should die.

    Implemented as a large entry delay, which moves the trade away from
    the moment the signal fired while leaving everything else identical.
    If the placebo keeps most of the edge, the signal was not the cause;
    something with a much longer timescale was.

    Reported as the fraction retained. Low is good, and that inversion
    is worth stating plainly because every other number in this system
    reads the other way.
    """
    bars = max(int(round(shift_s / max(bar_s, 1))), 1)
    try:
        r = evaluate(tape, hyp, tv, cost, feats, bar_s, delay=bars)
    except Exception:                                         # noqa: BLE001
        return None
    if not r:
        return None
    return {"delay_bars": bars, "net": r["net"], "z": r["z"],
            "gross": r["edge"]}


def verdict(z, net, bar, null_p99, stab, placebo, gross,
            min_stability=0.67, max_placebo_share=0.5, gz=None):
    """Everything a candidate must satisfy, with the reason it failed.

    Returns (passed, list_of_reasons). The reasons are the point: a
    candidate that dies here should die with an explanation that can be
    read months later, not with a boolean.
    """
    reasons, ok = [], True
    if net <= 0:
        ok = False
        reasons.append(f"net ${net:+.3f}/trade after costs")
    if z < bar:
        ok = False
        reasons.append(f"strength {z:.2f} below the rising bar {bar:.2f}")
    # Compared on GROSS strength, because the null is built from gross.
    # Comparing a net z against a gross null is comparing two different
    # quantities and would reject everything.
    zc = abs(gz) if gz is not None else abs(z)
    if null_p99 is not None and zc < null_p99:
        ok = False
        reasons.append(
            f"gross strength {zc:.2f} below the p99 of what this sweep's "
            f"own cells reached on everything ({null_p99:.2f}) -- the "
            f"empirical null, which accounts for the dependence between "
            f"hypotheses that the theoretical bar cannot")
    if stab is None:
        reasons.append("too few trades to test period stability")
    elif stab["share"] < min_stability:
        ok = False
        reasons.append(
            f"sign held in only {stab['agree']}/{stab['blocks']} "
            f"sub-periods ({stab['share']:.0%}, needs "
            f"{min_stability:.0%}) -- this looks like one lucky stretch "
            f"rather than a persistent effect")
    if placebo is None:
        reasons.append("stale placebo could not be run")
    else:
        share = (placebo["gross"] / gross) if gross else 0.0
        if share > max_placebo_share:
            ok = False
            reasons.append(
                f"the 30-minute STALE copy of this signal keeps "
                f"{share:.0%} of the edge (limit {max_placebo_share:.0%})"
                f" -- whatever is producing the return is not this "
                f"signal, it is something much slower")
    return ok, reasons


def replicated(family, market, mrows, bloc_of, min_blocs=2):
    """Did this show up in an INDEPENDENT bloc, not just here?

    `mrows` is {family: [(market, gross_edge), ...]} from the sweep.
    Counts blocs, not markets: NQ/ES/YM/RTY agreeing is one bloc and
    close to one observation, and this repo has already retracted a
    claim that counted it as four.

    Returns (ok, note). Not fatal on its own for single-market data --
    the book tier only exists for NQ, and demanding cross-market
    confirmation of a microstructure effect that can only be measured
    in one market would be demanding the impossible. It IS reported.
    """
    rows = (mrows or {}).get(family) or []
    if len(rows) < 2:
        return True, ("only one market carries this family, so "
                      "cross-market replication is not available -- "
                      "treat the result as one observation")
    home = bloc_of(market)
    same_sign = [m for m, e in rows if e > 0 and bloc_of(m) != home]
    blocs = {bloc_of(m) for m in same_sign}
    if len(blocs) + 1 >= min_blocs:
        return True, (f"also positive in {len(blocs)} independent "
                      f"bloc(s): {', '.join(sorted(blocs))}")
    return False, (f"positive only within {home}. No independent bloc "
                   f"shows the same sign, so this is one observation "
                   f"wearing the clothes of several.")
