"""An elite for every KIND of strategy, not one champion overall.

THE PROBLEM WITH RANKING BY QUALITY ALONE.

A search that keeps the best thing it has found, and looks near it, ends
up on one hill. Worse, it ends up on the WRONG hill for this account.

Run the arithmetic. A round trip on MNQ costs 60c, and the goal is $300
a week on one micro. That needs about 3,000 trades a week at a realistic
edge of +0.15 round trips. But significance rises with sqrt(n) while
profit rises with n, so a rare, violent, twice-a-month cell will always
show a bigger z than a frequent modest one -- and a leaderboard sorted
by z will always prefer it, and it will always be worth less. The search
was structurally unable to find the thing that was actually wanted.

QUALITY-DIVERSITY fixes this, and it is the right shape of answer rather
than a patch. Instead of one leaderboard, keep a GRID over the ways a
strategy can BEHAVE -- how often it trades, how long it holds, which way
it leans, how it exits -- and in each cell keep the best occupant. The
best twice-a-month strategy and the best thousand-times-a-week strategy
are then both retained, permanently, and neither can crowd out the
other. That is MAP-Elites (Mouret & Clune), and its two properties are
exactly the two things wanted here:

  1  COVERAGE. The archive is a map of what the market offers at each
     trading frequency, not a single number. "The best thing we have
     that trades 3,000 times a week" becomes a question with an answer.

  2  IT NEVER RUNS OUT. Elites are a breeding pool. New candidates are
     made by crossing and mutating occupants rather than drawn from
     nothing, so the search moves through the space under its own power
     and keeps improving every niche at once. A random draw explores
     forever without ever getting better; hill-climbing gets better
     without ever exploring. This does both, by construction.

WHY THE AXES ARE BEHAVIOUR AND NOT PERFORMANCE. If a grid axis were
"profit", the archive would be a leaderboard with extra steps and would
inherit the crowding it exists to prevent. The axes have to be things a
strategy IS, not how well it did -- so two occupants of one cell are
genuinely comparable and the comparison is decided by quality alone.

WHAT THIS IS NOT. It is not a relaxation of any standard. An elite is
the best thing IN ITS NICHE and nothing more; it has not passed the
delay control, the empirical null, the stale placebo or the vault, and
being an elite confers no credibility whatever. Most cells will be
filled by something that loses money, because most of this space loses
money, and the archive says so cell by cell rather than hiding it behind
one flattering maximum.
"""
from __future__ import annotations

import json
import math
import os

# ---------------------------------------------------------------- axes
#
# Trades per week is first because it is the axis the account's
# economics actually turn on. The buckets are logarithmic because the
# difference between 10 and 40 trades a week matters and the difference
# between 4,000 and 4,030 does not.
FREQ_EDGES = [0, 5, 25, 100, 400, 1500, 10 ** 9]
FREQ_NAMES = ["<5/wk", "5-25/wk", "25-100/wk", "100-400/wk",
              "400-1500/wk", "1500+/wk"]
HOLD_EDGES = [0, 90, 400, 1200, 3600, 10 ** 9]
HOLD_NAMES = ["<90s", "90s-7m", "7m-20m", "20m-1h", "1h+"]
EXIT_NAMES = ["time", "tight-target", "even", "wide-target"]
SIDE_NAMES = ["long", "short"]

# A cell needs this many trades before its occupant means anything.
#
# CHOSEN BY MEASUREMENT, not taste. An elite is a MAXIMUM, and maxima
# are biased upward -- the thinner the sample, the more the winner of a
# cell is just the luckiest draw in it. On 250 real NQ measurements:
#
#     floor    coverage    best elite
#        60      24.2%     +13.53 RT on 69 trades      <- noise
#       200      17.9%      +3.68 RT on 8,769 trades
#       500      17.9%      +3.68 RT on 8,769 trades
#
# Sixty trades bought six points of coverage and a thirteen-round-trip
# fiction. Two hundred removes it for almost nothing, and nothing above
# 200 changes the map at all.
MIN_TRADES = 200

# AND A FLOOR ON THE *EFFECTIVE* SAMPLE, WHICH IS THE ONE THAT COUNTS.
#
# The raw trade count was the only guard, and raw trades are not
# independent observations. A cell holding 240 bars while firing on
# every bar has 240x overlap, so 391 trades carry the information of
# TWO. Measured on the map as it stood, the top four elites were:
#
#   cu +110.20   z 0.151   raw n   391   effective n 2   mde 2,558 RT
#   cu  +79.40   z 0.207   raw n   204   effective n 2   mde 1,342 RT
#   cu  +60.97   z 0.159   raw n   220   effective n 2   mde 1,345 RT
#   cu  +47.18   z 0.140   raw n 1,251   effective n 5   mde 1,181 RT
#
# Every one is two lucky days wearing a four-figure trade count. The
# console rendered them as "+110 RT/trade on 391 trades", which is the
# most misleading sentence this project can produce: the number is a
# maximum over a huge search of cells that could not have detected
# anything smaller than a thousand round trips per trade. The z column
# said so all along -- 0.151 is indistinguishable from nothing -- but
# the map ranked on cu and never showed z.
#
# 30 effective observations is still thin. It is a floor against
# nonsense, not a claim of significance, and the map now carries eff_n
# and mde on every cell so the thinness is visible rather than implied.
MIN_EFF = int(os.environ.get("ARCHIVE_MIN_EFF", "30"))


# HOW GOOD IS THIS CELL, ONCE ITS OWN UNCERTAINTY IS TAKEN OFF IT.
#
# The map ranked cells by raw cu and bred from the winners. Raw cu is a
# MAXIMUM over a huge search, so ranking on it ranks luck, and breeding
# on it breeds luck -- a quality-diversity search evolving toward the
# best noise it can find. The effective-n floor stopped the very worst
# of that (cells of two observations claiming +110 RT), but within the
# survivors the ordering was still raw.
#
# Empirical-Bayes shrinkage is the standard answer and it needs one
# number this project already computes. mde = 3.5 * se in cost units,
# so se = mde / 3.5 comes free with every result. Then
#
#     shrunk = cu / (1 + (se / tau)^2)
#
# with tau the scale a REAL edge is expected to have. An estimate whose
# standard error is much larger than tau collapses toward zero; one
# measured tightly keeps almost all of its value. Worked through:
#
#     cu +110.00, se 731.0   ->  +0.00   (two lucky days, now ranked last)
#     cu   +0.50, se   0.30  ->  +0.15
#     cu   +0.20, se   0.05  ->  +0.19   (kept almost whole)
#
# TAU IS A PRIOR AND IT IS STATED, not hidden. 0.20 round trips per
# trade is roughly the largest edge this project's own reachability
# analysis says is plausibly detectable and not bug territory. Raising
# it shrinks less and ranks more like the old behaviour; the whole
# argument is visible in one constant.
SHRINK_TAU = float(os.environ.get("ARCHIVE_TAU", "0.20"))


def shrunk(cu, mde):
    """cu with its own uncertainty discounted. Falls back to raw cu when
    the result predates mde, because refusing to rank an older entry
    would silently empty the map."""
    try:
        cu = float(cu)
        se = float(mde) / 3.5
    except (TypeError, ValueError):
        return float(cu) if cu is not None else 0.0
    if not (se == se) or se <= 0:
        return cu
    return cu / (1.0 + (se / SHRINK_TAU) ** 2)


def _bucket(v, edges):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    for i in range(len(edges) - 1):
        if edges[i] <= v < edges[i + 1]:
            return i
    return None


def behaviour(hyp, result):
    """Which cell of the map this hypothesis lives in.

    Returns None when the measurement is too thin to place -- an
    unplaceable result is not an elite of anywhere.
    """
    if not result:
        return None
    n = int(result.get("n") or 0)
    if n < MIN_TRADES:
        return None
    # eff_n is absent on results from older engines; treat missing as
    # failing, because admitting an unknown sample size is exactly the
    # hole this closes.
    if int(result.get("eff_n") or 0) < MIN_EFF:
        return None
    f = _bucket(result.get("per_week"), FREQ_EDGES)
    h = _bucket(hyp.get("hold_s"), HOLD_EDGES)
    if f is None or h is None:
        return None

    ex = hyp.get("exit")
    if isinstance(ex, (list, tuple)) and len(ex) == 2:
        try:
            stop, targ = float(ex[0]), float(ex[1])
            e = 1 if targ < stop else (3 if targ > stop else 2)
        except (TypeError, ValueError):
            e = 0
    else:
        e = 0

    ls = str(hyp.get("ls") or hyp.get("dir") or "").lower()
    s = 1 if ls in ("short", "against", "-1") else 0
    return (f, h, e, s)


def cell_name(c):
    f, h, e, s = c
    return (f"{FREQ_NAMES[f]} · {HOLD_NAMES[h]} · {EXIT_NAMES[e]} · "
            f"{SIDE_NAMES[s]}")


TOTAL_CELLS = (len(FREQ_NAMES) * len(HOLD_NAMES) * len(EXIT_NAMES)
               * len(SIDE_NAMES))


class Archive:
    """The map. One elite per behavioural cell, kept forever."""

    def __init__(self, d=None):
        self.cells = {}
        self.improvements = 0
        self.considered = 0
        if d:
            self.load(d)

    # ------------------------------------------------------- occupancy
    def consider(self, hyp, family, result):
        """Offer a measurement to the map. True if it took a cell.

        Quality is NET round trips, because that is the only unit in
        which two markets are comparable and the only one whose sign is
        the sign of the money.
        """
        self.considered += 1
        c = behaviour(hyp, result)
        if c is None:
            return False
        cu = result.get("cu")
        if cu is None:
            return False
        try:
            cu = float(cu)
        except (TypeError, ValueError):
            return False
        if not (cu == cu) or abs(cu) > 1e6:      # NaN or nonsense
            return False
        key = ",".join(str(x) for x in c)
        # RANK ON THE SHRUNK VALUE, keep the raw one for display. The
        # occupant of a niche should be the best RELIABLE thing found
        # there, because that is what breeding will build on.
        sc = shrunk(cu, result.get("mde"))
        cur = self.cells.get(key)
        if cur is not None and float(cur.get("shrunk", cur.get("cu", -9e9))) >= sc:
            return False
        self.cells[key] = {
            "cu": round(cu, 5), "shrunk": round(sc, 5),
            "hyp": hyp, "family": family,
            "z": result.get("z"), "n": result.get("n"),
            # THE TWO NUMBERS THAT SAY WHETHER cu MEANS ANYTHING.
            # Without them a cell of two overlapping days and a cell of
            # eight hundred independent ones render identically.
            "eff_n": result.get("eff_n"), "mde": result.get("mde"),
            "overlap": result.get("overlap"),
            "per_week": result.get("per_week"),
            "win_rate": result.get("win_rate"), "rr": result.get("rr"),
            "market": hyp.get("market"),
        }
        self.improvements += 1
        return True

    def coverage(self):
        return {"filled": len(self.cells), "total": TOTAL_CELLS,
                "pct": round(100.0 * len(self.cells) / TOTAL_CELLS, 1),
                "improvements": self.improvements,
                "considered": self.considered}

    def best_at_frequency(self, min_per_week):
        """The best thing on the map that trades often enough to matter.

        This is the question the account actually asks, and before the
        map existed there was no way to ask it -- the leaderboard was
        sorted by significance, which systematically prefers the rare.
        """
        best = None
        for key, e in self.cells.items():
            if (e.get("per_week") or 0) < min_per_week:
                continue
            if best is None or e["cu"] > best["cu"]:
                best = dict(e, cell=key)
        return best

    def by_frequency(self):
        """The best occupant of each trading-frequency band.

        NOT a global ranking of the map. Sorting every cell by quality
        and showing the top few re-imports the exact bias this class was
        built to remove: rare cells have the fattest tails, so a global
        sort fills with twice-a-month outliers -- the first version of
        this method did precisely that and put a +37 round-trip cell at
        two trades a week on top.

        One row per frequency band is the honest view. It shows what the
        market offers at each rate of trading, which is the question the
        account's arithmetic actually asks, and it makes the outlier
        visible as what it is: the best of a nearly-empty corner.
        """
        best = {}
        for key, e in self.cells.items():
            f = int(key.split(",")[0])
            cur = best.get(f)
            if cur is None or e["cu"] > cur["cu"]:
                best[f] = dict(e, cell=key)
        return [dict(best[f], band=FREQ_NAMES[f])
                for f in sorted(best)]

    def top(self, k=12):
        rows = [dict(v, cell=k_) for k_, v in self.cells.items()]
        rows.sort(key=lambda r: -r["cu"])
        return rows[:k]

    # -------------------------------------------------------- breeding
    def breed(self, rng, n, mutate=None):
        """New candidates from the occupants of the map.

        Crossover then mutation, the standard MAP-Elites loop. Parents
        are drawn UNIFORMLY over filled cells rather than by quality:
        the point is to improve every niche, and weighting by quality
        would re-import the crowding the map exists to prevent.
        """
        elites = [e["hyp"] for e in self.cells.values() if e.get("hyp")]
        if len(elites) < 2 or n <= 0:
            return []
        out = []
        for _ in range(int(n)):
            a = elites[int(rng.integers(len(elites)))]
            b = elites[int(rng.integers(len(elites)))]
            child = _cross(a, b, rng)
            if mutate:
                child = mutate(child, rng)
            out.append(child)
        return out

    # ------------------------------------------------------ persistence
    def dump(self):
        return {"cells": self.cells, "improvements": self.improvements,
                "considered": self.considered}

    def load(self, d):
        self.cells = dict(d.get("cells") or {})
        self.improvements = int(d.get("improvements") or 0)
        self.considered = int(d.get("considered") or 0)

    def save(self, path):
        tmp = str(path) + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(self.dump(), fh, separators=(",", ":"))
        import os
        os.replace(tmp, path)


def _cross(a, b, rng):
    """One child from two parents, attribute by attribute.

    Only fields both parents share are crossed, so a child is always a
    coherent member of the family its parents came from. Crossing a
    shape hypothesis with a destination one would produce a dict that
    describes nothing.
    """
    keys = set(a) & set(b)
    keys -= {"market", "tier", "_family"}
    child = dict(a)
    for k in sorted(keys):
        if rng.random() < 0.5:
            child[k] = b[k]
    for k in ("market", "tier"):
        child.pop(k, None)
    return child


# ------------------------------------------------------------ self-test
def selftest(verbose=True):
    """The two properties that make this worth having, and one it must
    not have."""
    import numpy as np
    fails = []
    rng = np.random.default_rng(0)

    A = Archive()

    # 1. A frequent, modest strategy must survive the presence of a rare,
    #    spectacular one. This is the whole reason the archive exists:
    #    ranking by quality alone throws the frequent one away, and the
    #    frequent one is the only one that can pay the bills.
    rare = ({"shape": "gap", "hold_s": 3600, "exit": [1.0, 5.0],
             "ls": "long"},
            {"cu": 0.90, "n": 400, "per_week": 3, "z": 6.0,
             "eff_n": 400})
    freq = ({"shape": "run_up", "hold_s": 60, "exit": [1.0, 1.0],
             "ls": "long"},
            {"cu": 0.14, "n": 90000, "per_week": 3000, "z": 4.0,
             "eff_n": 9000})
    A.consider(rare[0], "shape/gap", rare[1])
    A.consider(freq[0], "shape/run_up", freq[1])
    got = A.best_at_frequency(1000)
    ok = got is not None and got["per_week"] == 3000
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  a frequent modest strategy is "
              f"not crowded out by a rare spectacular one  — best above "
              f"1000/wk is {got and got['per_week']}/wk at "
              f"{got and got['cu']:+.2f} RT")
    if not ok:
        fails.append("frequent niche lost to a rare one")

    # 2. Within one cell, quality decides -- and only quality.
    better = dict(freq[1]); better["cu"] = 0.30
    A.consider(freq[0], "shape/run_up", better)
    cell = A.best_at_frequency(1000)
    ok = abs(cell["cu"] - 0.30) < 1e-9
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  a better occupant replaces a "
              f"worse one in the same cell  — {cell['cu']:+.2f} RT")
    if not ok:
        fails.append("cell not improved by a better occupant")

    # 2b. THE FAILURE THAT PUT NOISE AT THE TOP OF THE CONSOLE. A cell
    #     with a large RAW trade count but almost no independent
    #     observations must not take a niche, however spectacular its
    #     number. The four best elites on the real map were exactly this:
    #     240x overlap, effective n of 2, and cu up to +110 RT.
    thin = ({"shape": "inside", "hold_s": 3600, "exit": None,
             "ls": "long"},
            {"cu": 110.2, "n": 391, "per_week": 800, "z": 0.151,
             "eff_n": 2, "mde": 2558.1})
    took = A.consider(thin[0], "shape/inside", thin[1])
    ok = not took
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  a huge number built from two "
              f"independent observations is refused a niche  — 391 raw "
              f"trades, effective n 2, +110.20 RT {'rejected' if ok else 'ACCEPTED'}")
    if not ok:
        fails.append("thin cell admitted to the map on raw trade count")

    worse = dict(freq[1]); worse["cu"] = -5.0
    A.consider(freq[0], "shape/run_up", worse)
    ok = abs(A.best_at_frequency(1000)["cu"] - 0.30) < 1e-9
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  a worse occupant does not "
              f"displace a better one")
    if not ok:
        fails.append("cell regressed")

    # 3. Thin measurements are not elites of anywhere.
    thin = ({"shape": "inside", "hold_s": 300, "exit": None, "ls": "long"},
            {"cu": 99.0, "n": 5, "per_week": 1, "z": 40})
    before = len(A.cells)
    A.consider(thin[0], "shape/inside", thin[1])
    ok = len(A.cells) == before
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  refuses a cell to a result "
              f"with 5 trades, however good it looks")
    if not ok:
        fails.append("thin result admitted")

    # 4. Breeding must produce coherent, novel children.
    for i in range(40):
        A.consider({"shape": ["run_up", "run_dn", "squeeze"][i % 3],
                    "hold_s": [60, 300, 900, 3600][i % 4],
                    "exit": [[1.0, 2.0], [2.0, 1.0], None][i % 3],
                    "ls": ["long", "short"][i % 2]},
                   "shape/x",
                   {"cu": rng.normal(0, .2), "n": 500,
                    "per_week": float(10 ** (1 + i % 3)), "z": 1.0})
    kids = A.breed(rng, 50)
    ok = (len(kids) == 50
          and all(isinstance(k, dict) and "shape" in k for k in kids)
          and all("market" not in k for k in kids))
    novel = sum(1 for k in kids
                if k not in [e["hyp"] for e in A.cells.values()])
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  breeding yields coherent "
              f"children  — {len(kids)} bred, {novel} of them not already "
              f"in the archive")
    if not ok:
        fails.append("breeding produced malformed children")

    # 5. Coverage must be a real fraction of a real grid.
    cov = A.coverage()
    ok = 0 < cov["filled"] <= cov["total"] == TOTAL_CELLS
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  coverage is meaningful  — "
              f"{cov['filled']}/{cov['total']} cells ({cov['pct']}%)")
    if not ok:
        fails.append("coverage nonsensical")
    return fails


if __name__ == "__main__":
    f = selftest()
    print("\narchive selftest:", "PASS" if not f else f"FAIL {f}")
