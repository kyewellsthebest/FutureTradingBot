"""The sniff test: numbers that cannot be true, and what they imply.

WHAT THIS IS PORTING. Every bug found in this project was found the same
way -- by looking at a number and thinking "that cannot be right", then
reasoning backwards to the only thing that could produce it. Not one was
found by a control firing, and not one was found by reading the code.

    96% win rate                -> impossible on futures -> dig
    empirical null 22 sigma     -> a null above the bar blocks every
                                   finding, so the null is misbuilt
    break-even at 1 second      -> a category error, not a measurement
    16 of 17 families "fit"     -> an engine that concludes something
                                   about everything is not inferring
    residual does not decay     -> therefore not a timing leak, so stop
                                   looking for one and look elsewhere

The controls in validate.py answer questions somebody thought to ask.
This file encodes the prior knowledge that tells you a question is worth
asking at all -- and, crucially, WHICH question. An implausible number
is not just a candidate to reject; it is a pointer at a specific bug.

So each rule carries a SUSPECT LIST. That is the part that matters. Any
system can flag an outlier. Saying "a win rate this high with a
symmetric bracket almost always means the exit is being resolved in your
favour, look at the tie rule and the stop fill" is the thing that turns
a flag into a fix.

WHAT THIS STILL CANNOT DO, and it should be said plainly rather than
buried. It cannot notice something nobody anticipated. The tick-ordering
bug that invalidated the entire deep tier was found by reasoning from an
impossible number to its only possible cause; there was no rule for "is
the data time-ordered", because nobody had thought to doubt it. Encoded
priors catch the recurrence of known impossibilities. Novel diagnosis is
not in here, and pretending otherwise would be the same overclaim this
file exists to catch.
"""
from __future__ import annotations


# Each rule: (name, test, what it means, where to look).
# Thresholds are deliberately loose -- this is a smoke alarm, not a
# significance test. A rule that fires on marginal cases gets ignored,
# and an ignored alarm is worse than none.
def check_result(r, hyp=None, cost=None, tick_value=None):
    """Implausibilities in a single measured result."""
    out = []
    if not r:
        return out
    wr = r.get("win_rate")
    rr = r.get("rr")
    net = r.get("net")
    n = r.get("n") or 0
    z = r.get("z")
    ex = (hyp or {}).get("exit")

    # 1. win rate. A high win rate is only legitimate when the target is
    # much closer than the stop, which shows up as a LOW reward-to-risk.
    # High win rate AND high RR together is the signature of an exit
    # being resolved in your favour.
    if wr is not None and rr is not None and n >= 200:
        if wr > 0.80 and rr > 1.2:
            out.append((
                "win rate %.0f%% together with RR %.2f" % (wr * 100, rr),
                "Winning four times in five AND making more on each win "
                "than you lose is not something futures markets offer. "
                "The two are traded off against each other by the exit, "
                "so seeing both means the exit is being resolved "
                "favourably somewhere.",
                ["the tie rule when a bar touches both barriers",
                 "stop fills assumed at the exact stop price",
                 "entry taken at a price the bar selected on",
                 "close built from an unsorted tape"]))
        elif wr > 0.92 and n >= 500:
            out.append((
                "win rate %.0f%%" % (wr * 100),
                "Above about nine in ten, on hundreds of trades, is "
                "outside what a retail-cost strategy does even with a "
                "very tight target.",
                ["entry contaminated by the selection",
                 "timeout exits being counted as wins"]))

    # 2. size. Gross edge far above the cost is not a strategy, it is a
    # bug -- if it were real it would have been arbitraged.
    if net is not None and cost and n >= 200 and net > 8 * cost:
        out.append((
            "net $%.2f/trade against a $%.2f round trip" % (net, cost),
            "More than eight times the cost of trading, per trade, "
            "repeatedly. An edge that large does not survive in a "
            "liquid market -- somebody would have taken it.",
            ["the price used for entry is not obtainable",
             "look-ahead in the conditioning",
             "corrupt or misaligned data"]))

    # 3. THE COST MODEL ITSELF. This is what actually caught ZB, and
    # the first version of this rule got it wrong in an instructive way.
    #
    # I first wrote "a gross edge below one tick is impossible". That is
    # false: winning a tick 55% of the time and losing one 45% gives a
    # MEAN of 0.1 ticks, which is a perfectly real edge. The rule fired
    # on an ordinary MNQ result and had to go.
    #
    # The genuine tell was never the edge, it was the COST. ZB was
    # charged $2.50 while one ZB tick is worth $31.25 -- a round-trip
    # cost smaller than the smallest possible price move, which means
    # the spread is simply missing from the model. A taker crosses it
    # twice; a cost below one tick cannot be right for anyone.
    if cost and tick_value and cost < tick_value:
        out.append((
            "round-trip cost $%.2f on an instrument whose tick is $%.2f"
            % (cost, tick_value),
            "The cost of trading is less than the smallest move the "
            "instrument can make, so the spread is not in the cost "
            "model. Every result on this market is flattered by roughly "
            "the amount that is missing.",
            ["commission charged without the spread",
             "tick value taken from the wrong contract size"]))

    # 4. significance. Very large z with few effective observations means
    # the standard error is wrong, usually overlap.
    eff = r.get("eff_n") or n
    if z is not None and abs(z) > 25 and eff and eff < 5000:
        out.append((
            "z = %.1f on %d effective observations" % (z, eff),
            "That much significance from that few independent trades "
            "means the standard error is too small, not that the effect "
            "is strong.",
            ["overlap correction not applied to this path",
             "trades sampled more finely than the hold length"]))

    # 5. a bracket that never resolves. If nearly everything times out,
    # the barriers are not doing anything and the reported win rate and
    # RR describe a time exit wearing a bracket's clothes.
    timed = r.get("timed")
    if ex and timed is not None and timed > 0.95:
        out.append((
            "%.0f%% of trades exited on the timer" % (timed * 100),
            "The stop and target are so far away they are never "
            "reached, so this is a fixed-time exit being reported as a "
            "bracket. Its win rate and RR do not describe the bracket.",
            ["hold length too short for the barrier distances",
             "volatility unit far larger than the bar range"]))
    return out


def check_system(*, null_p99=None, theoretical_bar=None,
                 families_total=None, families_fitting=None,
                 h_star_s=None, bar_s=None, survivors=None,
                 candidates=None):
    """Implausibilities in the searcher's own machinery.

    This is the half that has caught the most, because a broken control
    is invisible from the outside -- it just reports that everything is
    fine, or that nothing is ever good enough.
    """
    out = []

    # A null above the bar means nothing can ever pass. That is not a
    # strict standard, it is a broken null.
    if null_p99 is not None and theoretical_bar and null_p99 > theoretical_bar * 2:
        out.append((
            "empirical null p99 %.1f against a %.1f sigma bar"
            % (null_p99, theoretical_bar),
            "The null is meant to sit near the noise level. Far above "
            "the bar it blocks every possible finding, which means it "
            "is measuring the wrong quantity.",
            ["null built from NET z, which is dominated by cost",
             "null built from a mixture of markets with different "
             "economics"]))

    # An inference engine that concludes something about nearly
    # everything is not inferring.
    if families_total and families_fitting is not None:
        share = families_fitting / max(families_total, 1)
        if families_total >= 8 and share > 0.85:
            out.append((
                "%d of %d families produced a confident fit"
                % (families_fitting, families_total),
                "Real structure is rare. A model that finds it almost "
                "everywhere is fitting noise and calling it a law.",
                ["no goodness-of-fit floor",
                 "no limit on how far the fit is extrapolated",
                 "pooling incompatible units before fitting"]))

    # A break-even horizon shorter than one bar is a category error.
    if h_star_s is not None and bar_s and h_star_s < bar_s:
        out.append((
            "break-even horizon %.0fs on %.0fs bars" % (h_star_s, bar_s),
            "Shorter than a single bar, so the fit is extrapolating "
            "below the resolution of its own measurements.",
            ["units mismatched between the fitted curve and the cost",
             "cost of one market applied to a pool of many"]))

    # Survivors reported without candidates having been through the
    # gauntlet is a bookkeeping error, and the most misleading one.
    if survivors and candidates is not None and survivors > candidates:
        out.append((
            "%d survivors from %d candidates" % (survivors, candidates),
            "More things survived than were ever tested, so survivors "
            "are being recorded before the checks run.",
            ["survivor recorded at bar-clearing rather than at "
             "gauntlet-passing"]))
    return out


def render(items, prefix="  "):
    lines = []
    for what, why, suspects in items:
        lines.append(f"{prefix}IMPLAUSIBLE: {what}")
        lines.append(f"{prefix}  {why}")
        lines.append(f"{prefix}  look at: " + "; ".join(suspects))
    return "\n".join(lines)


# ------------------------------------------------------------ self-test
def selftest(verbose=True):
    """Feed it every artifact this project actually produced.

    A plausibility layer that does not catch the bugs that already
    happened is decoration. These are the real numbers from the real
    failures, and each one must fire.
    """
    fails = []

    cases = [
        ("close_low bracket, the $23.72 fake",
         dict(r={"win_rate": 0.97, "rr": 6.06, "net": 23.72, "n": 4405,
                 "z": 68.98, "eff_n": 4405, "timed": 0.996},
              hyp={"exit": [3.0, 5.0]}, cost=0.60)),
        ("close_high bracket, the $21.01 fake",
         dict(r={"win_rate": 0.9594, "rr": 2.976, "net": 21.006,
                 "n": 4631, "z": 82.33, "eff_n": 4631, "timed": 0.582},
              hyp={"exit": [2.0, 1.0]}, cost=0.60)),
        ("ZB scored with a cost below one tick",
         dict(r={"win_rate": 0.55, "rr": 1.1, "net": 3.13, "edge": 5.63,
                 "n": 38600, "z": 10.55, "eff_n": 38600},
              hyp={}, cost=2.50, tick_value=31.25)),
    ]
    for name, kw in cases:
        got = check_result(**kw)
        ok = bool(got)
        if verbose:
            print(f"  {'PASS' if ok else 'FAIL'}  flags: {name}")
            if ok:
                print(render(got, "        "))
        if not ok:
            fails.append(name)

    sys_cases = [
        ("empirical null of 22 sigma against a 4.6 bar",
         dict(null_p99=22.27, theoretical_bar=4.59)),
        ("16 of 17 families fitting",
         dict(families_total=17, families_fitting=16)),
        ("break-even at 1s on 300s bars",
         dict(h_star_s=1, bar_s=300)),
        ("47 survivors, 0 through the gauntlet",
         dict(survivors=47, candidates=0)),
    ]
    for name, kw in sys_cases:
        got = check_system(**kw)
        ok = bool(got)
        if verbose:
            print(f"  {'PASS' if ok else 'FAIL'}  flags: {name}")
            if ok:
                print(render(got, "        "))
        if not ok:
            fails.append(name)

    # and it must NOT fire on an honest, unremarkable result
    quiet = check_result(
        {"win_rate": 0.47, "rr": 1.06, "net": -0.21, "edge": 0.39,
         "n": 3800, "z": -2.8, "eff_n": 3800}, {}, 0.60, tick_value=0.50)
    if verbose:
        print(f"  {'PASS' if not quiet else 'FAIL'}  stays quiet on an "
              f"ordinary losing result")
    if quiet:
        fails.append("false alarm on an ordinary result")
    return fails


if __name__ == "__main__":
    f = selftest()
    print("\nplausibility selftest:", "PASS" if not f else f"FAIL {f}")
