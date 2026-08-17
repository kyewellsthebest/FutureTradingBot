"""Learning that infers something, rather than learning that gives up.

WHAT WAS WRONG WITH THE OLD LEARNING. It had exactly one move: a family
failed a lot, so do less of it. That is not figuring anything out. It
throws away the most useful thing a batch of failures contains, which is
the SHAPE of the failure -- and the shape is where the answer is.

Today's order-flow run is the example. Six mechanisms, four horizons,
and the gross edge came out like this on MNQ:

      5s   $0.08      60s   $0.36      300s   $1.38
                                       cost   $0.60

The old learner would have recorded "flow families produce nothing, cut
their effort". The right reading is the opposite and it is quantitative:
gross edge is GROWING with horizon, roughly as a power law, while cost
is fixed. Somewhere between 60s and 300s that curve crosses the cost
line. A learner that can fit the curve can predict where -- and then go
and look there, which is a deduction rather than a preference.

THREE INFERENCES, all from measurements the search already makes.

  1  HORIZON CROSSING. Fit gross_edge ~ a * h^b per family. Cost is
     flat. Solve for h* where they meet. If h* is reachable, generate
     hypotheses AT h* -- that is the learning changing what gets
     searched. If h* is absurd, say so with the number, which closes
     the family for a reason instead of a shrug.

  2  CROSS-MARKET REPLICATION. The same mechanism tested in every
     market. Agreement across INDEPENDENT blocs is evidence; agreement
     across NQ/ES/YM/RTY is close to one observation, because they move
     together at ~0.9 correlation. This repo has already retracted a
     claim built on exactly that mistake.

  3  THE COST FRONTIER. For each market, how big an information
     coefficient would be needed to clear its own cost, given its own
     volatility. That ranks markets by achievability instead of by
     familiarity, and it is the reason MNQ is worth more attention than
     ZB regardless of which is more interesting.

WHAT NONE OF THIS DOES. None of it looks at whether a specific
hypothesis made money and searches near it. That is the mechanism that
produced 1.38 billion configurations with a measured NEGATIVE return.
These infer from the SHAPE of aggregate failure, which is a property of
the market and the cost structure, not of any individual result.
"""
from __future__ import annotations

import math
from collections import defaultdict

BLOCS = {
    "equity": ["NQ", "ES", "YM", "RTY"],
    "rates": ["ZB", "ZN", "ZF", "ZT"],
    "energy": ["CL", "NG", "HO", "RB"],
    "metals": ["GC", "HG"],
    "fx": ["6E", "6A", "6B", "6J"],
    "grain": ["ZC", "ZW", "ZS"],
    "crypto": ["MBT", "ETH"],
}
_BLOC_OF = {m: b for b, ms in BLOCS.items() for m in ms}


def bloc_of(market):
    return _BLOC_OF.get(str(market).split("@")[0], "other")


# ------------------------------------------------------- 1. horizon fit
# GUARDS ON THE INFERENCE. Without these the fit fired on 16 of 17
# families, including one with r2=0.10 and one extrapolating to 18.8
# hours. An inference engine that concludes something about everything
# is not inferring, it is decorating.
MIN_R2 = 0.70        # below this the "law" is a line through noise
MAX_HOLD_S = 14400   # 4h. This account flattens at the close; a
                     # break-even that needs an overnight hold is not
                     # reachable, whatever the fit says.
MAX_EXTRAP = 4.0     # h* may sit at most 4x beyond the longest horizon
                     # actually tested. Extrapolating a power law two
                     # orders of magnitude past your data is not a
                     # deduction, it is a wish with a slope on it.


def horizon_crossing(points, cost=1.0, max_h=MAX_HOLD_S):
    """Where would gross edge cross cost, if the trend continued?

    `points` is [(hold_seconds, edge_in_units_of_that_market_cost), ...].

    THE UNITS MATTER AND THE FIRST VERSION GOT THEM WRONG. It pooled
    gross edge in DOLLARS across every market in a family and compared
    the result against one market's cost. ZB moves $31 a tick and MNQ
    moves $0.50, so the pooled curve was essentially ZB's, judged
    against MNQ's $0.60 -- and it duly reported that clock-bucket
    families cross cost at ONE SECOND, which is what a nonsense
    comparison looks like when it is fitted carefully.

    The caller now divides each edge by ITS OWN market's cost before
    pooling, so a point of 1.0 means "this exactly paid for itself
    here" in every market alike. The crossing is then where the fitted
    ratio reaches 1.0, and `cost` stays at 1.0. Fitted in log space, which is the right space: edge grows
    with the size of a move and move size grows as a power of time.

    Returns None when the question is not answerable, and that matters
    more than the fit. Fewer than three horizons is not a curve. A
    non-positive exponent means edge is FLAT or SHRINKING with horizon,
    so there is no crossing to find and holding longer is not the
    answer. Saying nothing in those cases is the difference between an
    inference and a guess dressed as one.
    """
    pts = [(h, e) for h, e in points if h > 0 and e > 0]
    if len(pts) < 3:
        return None
    hs = sorted({h for h, _ in pts})
    if len(hs) < 3:
        return None
    # average edge per horizon first, so a horizon with many hypotheses
    # does not dominate the fit purely by count
    by_h = defaultdict(list)
    for h, e in pts:
        by_h[h].append(e)
    xs = [math.log(h) for h in sorted(by_h)]
    ys = [math.log(sum(by_h[h]) / len(by_h[h])) for h in sorted(by_h)]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return None
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = math.exp(my - b * mx)
    # goodness of fit, so a meaningless line is not reported as a law
    ss_t = sum((y - my) ** 2 for y in ys)
    ss_r = sum((y - (math.log(a) + b * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 - (ss_r / ss_t) if ss_t > 0 else 0.0
    if b <= 0.05:
        return {"fits": False, "b": round(b, 3), "r2": round(r2, 3),
                "why": (f"gross edge does not grow with horizon "
                        f"(exponent {b:+.2f}). Holding longer is not the "
                        f"answer here -- whatever this family measures "
                        f"decays as fast as the move grows.")}
    if r2 < MIN_R2:
        return {"fits": False, "b": round(b, 3), "r2": round(r2, 3),
                "why": (f"the horizon trend is too noisy to extrapolate "
                        f"(fit quality {r2:.2f}, needs {MIN_R2:.2f}). "
                        f"There may be a relationship here but these "
                        f"measurements do not establish one.")}
    h_star = math.exp((math.log(cost) - math.log(a)) / b)
    h_max_tested = max(by_h)
    over = h_star / max(h_max_tested, 1)
    reachable = bool(60 <= h_star <= max_h and over <= MAX_EXTRAP)
    note = ""
    if h_star > max_h:
        note = (f" That is beyond the {_dur(max_h)} this account can "
                f"hold intraday, so it is a reason to close the family "
                f"rather than a horizon to search.")
    elif over > MAX_EXTRAP:
        note = (f" But that is {over:.0f}x beyond the longest horizon "
                f"actually tested ({_dur(h_max_tested)}), so it is an "
                f"extrapolation rather than a measurement and is not "
                f"acted on.")
    return {
        "fits": True, "a": round(a, 6), "b": round(b, 3),
        "r2": round(r2, 3), "cost": cost,
        "h_star": int(h_star), "extrapolation": round(over, 1),
        "max_tested": int(h_max_tested),
        "reachable": reachable,
        "why": (f"gross edge grows as horizon^{b:.2f} (fit quality "
                f"{r2:.2f}), measured in multiples of each market's own "
                f"round-trip cost. It reaches break-even near "
                f"{_dur(h_star)}." + note),
    }


def _dur(s):
    s = float(s)
    if s < 90:
        return f"{s:.0f}s"
    if s < 5400:
        return f"{s / 60:.0f} min"
    if s < 172800:
        return f"{s / 3600:.1f} hours"
    return f"{s / 86400:.1f} days"


# -------------------------------------------- 2. cross-market agreement
def replication(rows):
    """How many INDEPENDENT observations agree, not how many markets.

    `rows` is [(market, gross_edge), ...] for one mechanism. Four equity
    indices agreeing is about 1.75 observations, not 4 -- they move
    together at roughly 0.9 correlation, and this project has already
    retracted a claim that counted them as four.
    """
    by_bloc = defaultdict(list)
    for m, e in rows:
        by_bloc[bloc_of(m)].append(e)
    pos = neg = 0.0
    detail = {}
    for b, es in by_bloc.items():
        weight = 1.0 + 0.25 * (len(es) - 1)
        share = sum(1 for e in es if e > 0) / len(es)
        detail[b] = {"markets": len(es), "weight": round(weight, 2),
                     "positive_share": round(share, 2)}
        if share >= 0.6:
            pos += weight
        elif share <= 0.4:
            neg += weight
    return {"blocs": detail, "agree_positive": round(pos, 2),
            "agree_negative": round(neg, 2),
            "effective_n": round(sum(1.0 + 0.25 * (len(v) - 1)
                                     for v in by_bloc.values()), 2)}


# ------------------------------------------------ 3. the cost frontier
def cost_frontier(vols, spec):
    """What skill each market demands, so effort can go where it is
    cheapest to succeed.

    A market pays when  IC x sigma x $/point  >  cost. Rearranged, the
    IC a market DEMANDS is cost / (sigma x $/point). Low is good. This
    is the movement-per-cost idea: the metric is how far a market moves
    per dollar it charges, and ranking by commission alone gets the
    table backwards.
    """
    out = []
    for m, sd in vols.items():
        if m not in spec or not sd or sd <= 0:
            continue
        pv, cost = spec[m]
        move = sd * pv
        if move <= 0:
            continue
        out.append({"market": m, "sigma_pts": round(sd, 6),
                    "move_per_trade": round(move, 3),
                    "cost": cost,
                    "ic_needed": round(cost / move, 4),
                    "moves_per_cost": round(move / cost, 2)})
    out.sort(key=lambda r: r["ic_needed"])
    return out


# ---------------------------------------------------------- assembly
def build(family_points, family_costs, market_rows, vols, spec):
    """Everything the learner has deduced this cycle."""
    horizons = {}
    for fam, pts in family_points.items():
        r = horizon_crossing(pts, family_costs.get(fam, 0.60))
        if r:
            horizons[fam] = r
    reps = {fam: replication(rows) for fam, rows in market_rows.items()
            if len(rows) >= 3}
    return {"horizons": horizons, "replication": reps,
            "frontier": cost_frontier(vols, spec)}
