"""Where hypotheses come from -- structure, not parameter grids.

The user's requirement is that nothing is imported from outside: no
published configs, no leaderboards, no altered versions of somebody
else's decayed edge. So the space is GENERATED, and it is generated from
things measured in the tape rather than enumerated from a template.

THE GENERATOR

  1  scan the tape for FOOTPRINTS -- buckets of time where volume,
     print count, realized volatility or serial correlation is a
     statistical outlier against its own dimension. Somebody trading
     who did not choose to leaves a mark whether or not the price move
     is predictable.
  2  each footprint becomes a WINDOW.
  3  each window is crossed with a small set of readings (which way,
     how long, conditioned on what).

The result is a few thousand hypotheses anchored to measured structure,
not billions anchored to nothing. That distinction is the whole reason
this can run continuously without degenerating into the 1.38-billion-
config failure recorded as ledger entry #19.

WHY NOT JUST ENUMERATE MORE. Because the search space's SIZE is the
enemy. Every extra cell raises the bar that a real finding must clear
(see ledger.bar). A generator that produces 3,000 anchored hypotheses
is strictly better than one producing 3,000,000 arbitrary ones, even if
the real edge is in both -- because in the second the real edge is
buried under a larger pile of convincing noise.
"""
import math
import os

import numpy as np
import pandas as pd

# how a window may be read. Deliberately small: the cross product is
# what explodes, and every extra option costs every other hypothesis
# by raising the bar.
DIRECTIONS = ["with", "against"]          # momentum or fade into it
HOLDS_S = [60, 300, 900, 3600]            # 1m, 5m, 15m, 1h
CONDS = ["none", "hi_vol", "lo_vol", "up_day", "dn_day"]


def find_footprints(bars: pd.DataFrame, z=3.0, max_per_dim=8):
    """Buckets that are statistical outliers in market BEHAVIOUR.

    Deliberately not returns. A return outlier is a strategy hunting for
    a story; a VOLUME outlier is a footprint, and the story comes after.
    """
    out = []
    b = bars
    dims = {
        "minute_of_day": list(zip(b.index.hour, b.index.minute)),
        "day_of_month": b.index.day,
        "day_of_week": b.index.dayofweek,
    }
    metrics = ["vol", "n", "absret"]
    for dname, key in dims.items():
        g = b.assign(_k=key).groupby("_k")
        for m in metrics:
            if m not in b.columns:
                continue
            s = g[m].median()
            v = s.values.astype(float)
            med = np.nanmedian(v)
            mad = np.nanmedian(np.abs(v - med)) * 1.4826
            if not np.isfinite(mad) or mad <= 0:
                continue
            zz = (v - med) / mad
            idx = np.argsort(-np.abs(zz))[:max_per_dim]
            for i in idx:
                if abs(zz[i]) < z:
                    continue
                out.append({"dim": dname, "bucket": _norm(s.index[i]),
                            "metric": m, "z": round(float(zz[i]), 2)})
    return out


def _norm(k):
    if isinstance(k, tuple):
        return f"{int(k[0]):02d}:{int(k[1]):02d}"
    return int(k)


def expand(footprints, cap=4000, extra_holds=None, extra_conds=None):
    """Footprints -> concrete, testable hypotheses.

    `extra_holds` carries horizons the learner DEDUCED rather than
    horizons anybody chose. When a family's edge-vs-horizon fit says the
    crossing with cost sits at 110 seconds, 110 seconds gets tested --
    that is the inference changing what is searched, which is the only
    thing that distinguishes learning from note-taking.
    """
    hyps = []
    for f in footprints:
        fam = f"{f['dim']}/{f['metric']}"
        holds = list(HOLDS_S) + [h for h in (extra_holds or {}).get(fam, [])
                                 if h not in HOLDS_S]
        conds = CONDS + list(extra_conds or [])
        for d in DIRECTIONS:
            for h in holds:
                for c in conds:
                    hyps.append({
                        "kind": "footprint",
                        "dim": f["dim"], "bucket": f["bucket"],
                        "metric": f["metric"], "dir": d,
                        "hold_s": h, "cond": c,
                        "_family": fam,
                    })
                    if len(hyps) >= cap:
                        return hyps
    return hyps


SIDES = ["hi", "lo"]                      # top or bottom quintile
LONGSHORT = ["long", "short"]


def from_features(kept, floor, hold_mult=1.0, cap=1200):
    """Discovered features -> hypotheses.

    A feature says "these bars are different". A hypothesis has to say
    something falsifiable, so each surviving feature is turned into:
    when the feature sits in its top (or bottom) quintile, go long (or
    short), and hold for H.

    BOTH directions are always generated. Picking the direction that
    looked better in the search set is fitting the sign -- the single
    most common way a backtest manufactures an edge -- so both are
    generated, both are counted as trials, and the bar decides.

    `floor` is the dispersion threshold measured by features_selftest
    against targets with no information. Features below it are not
    weak evidence, they are the level the machinery reaches on nothing,
    so they produce no hypotheses at all.

    `hold_mult` comes from failure memory: a family whose failures were
    mostly cost-bound gets longer holds, because cost is fixed per trade
    while move size grows as sqrt(time). That is arithmetic, not a
    fitted preference.
    """
    hyps = []
    holds = [int(h * hold_mult) for h in HOLDS_S]
    for nm, score in kept:
        if score < floor:
            continue
        depth = nm.count("(") + nm.count("*")
        for s in SIDES:
            for ls in LONGSHORT:
                for h in holds:
                    hyps.append({
                        "kind": "feature", "feat": nm, "side": s,
                        "ls": ls, "hold_s": h,
                        "_family": f"feature/d{depth}",
                    })
                    if len(hyps) >= cap:
                        return hyps
    return hyps


# ---------------------------------------------------------------- flow
# ORDER-FLOW MECHANISMS. Each one is a stated reason why price should
# move, written down BEFORE looking, and a signed quantity that measures
# it. This is the difference between a footprint and a mechanism: a
# footprint says "something happens here", a mechanism says "this
# happens because someone has to do this".
#
# Why it matters that the reason comes first. A clock bucket that
# survives testing is a fact with no explanation, and facts with no
# explanation stop being true without warning. A queue that drains
# faster than it refills breaks for a reason that does not go away when
# other people notice it -- somebody still has to cross the spread.
#
# These columns exist ONLY on the book tier. They cannot be
# reconstructed from trades at any other resolution, which is the whole
# reason that data was bought.
FLOW = [
    {"name": "queue_depletion",
     "cols": ["depl"],
     "expr": lambda d: d["depl"],
     "why": "The bid queue is draining faster than the ask queue "
            "(or the reverse). A side that is being consumed and not "
            "replaced runs out, and price has to move to the next "
            "level. This is mechanical, not behavioural."},
    {"name": "flow_book_agree",
     "cols": ["imb", "tflow"],
     "expr": lambda d: _sgn(d["imb"]) * _sgn(d["tflow"]) * d["tflow"].abs(),
     "why": "Signed trade flow agreeing with resting book imbalance. "
            "Aggressive buying INTO a bid-heavy book is someone who "
            "needs the position and is not being faded; the two "
            "measurements disagreeing is usually noise."},
    {"name": "liquidity_withdrawal",
     "cols": ["spread", "adds"],
     "expr": lambda d: d["spread"] * -_sgn(d["adds"]),
     "why": "Spread widening while adds collapse. Market makers pull "
            "quotes when they expect to be run over; the withdrawal "
            "leads the move rather than following it."},
    {"name": "add_asymmetry",
     "cols": ["adds"],
     "expr": lambda d: d["adds"],
     "why": "Passive size being added to one side. Somebody willing to "
            "show size is expressing a view they are prepared to be "
            "filled on, which is a costlier signal than a trade."},
    {"name": "imbalance_change",
     "cols": ["imb"],
     "expr": lambda d: d["imb"].diff(),
     "why": "The CHANGE in book imbalance rather than its level. A "
            "level is a standing state that everyone can see and price "
            "in; the change is the new information."},
    {"name": "flow_vs_depth",
     "cols": ["tflow", "spread"],
     "expr": lambda d: d["tflow"] / d["spread"].replace(0, float("nan")),
     "why": "Trade flow relative to how thin the book is. The same "
            "order moves a thin book further, so the impact of flow "
            "depends on the depth it lands in."},
]


def _sgn(s):
    import numpy as np
    return np.sign(s)


FLOW_HOLDS_S = [5, 15, 60, 300]


def from_flow(available, hold_mult=1.0, cap=600, extra_holds=None):
    """Order-flow mechanisms -> hypotheses.

    Holds are SHORT here on purpose. A queue imbalance is consumed in
    seconds; asking whether it predicts the next hour is asking a
    different question about a different thing, and the answer would be
    no for reasons that say nothing about the mechanism.

    Both directions are generated, as everywhere else. The mechanism
    supplies a reason to look, never the sign -- picking the sign that
    looked better in the search set is fitting the sign, which is the
    most common way a backtest manufactures an edge.
    """
    hyps = []
    base = [max(int(h * hold_mult), 1) for h in FLOW_HOLDS_S]
    for m in FLOW:
        if not all(c in available for c in m["cols"]):
            continue
        holds = base + [h for h in (extra_holds or {}).get(
            f"flow/{m['name']}", []) if h not in base]
        for side in SIDES:
            for ls in LONGSHORT:
                for h in holds:
                    hyps.append({
                        "kind": "flow", "mech": m["name"], "side": side,
                        "ls": ls, "hold_s": h,
                        "_family": f"flow/{m['name']}",
                    })
                    if len(hyps) >= cap:
                        return hyps
    return hyps


def from_shapes(rng, cap=900, extra_conds=None):
    """Recurring-behaviour hypotheses, SAMPLED rather than enumerated.

    The full cross product of shape x parameter x direction x exit x
    condition is far larger than one cycle should test, and enumerating
    it in a fixed order would mean the searcher spent weeks on run_up
    before ever reaching gap. Drawing at random each cycle covers the
    space evenly over time and -- because the ledger fingerprints every
    hypothesis -- never repeats one.
    """
    hyps = []
    names = list(SHAPES)
    conds = ["none"] + list(extra_conds or [])
    seen = set()
    tries = 0
    while len(hyps) < cap and tries < cap * 8:
        tries += 1
        nm = names[int(rng.integers(len(names)))]
        n = draw_n(rng)
        k = draw_k(rng)
        ls = LONGSHORT[int(rng.integers(2))]
        ex = draw_exit(rng)
        hold = draw_hold(rng)
        cond = conds[int(rng.integers(len(conds)))]
        key = (nm, n, k, ls, ex, hold, cond)
        if key in seen:
            continue
        seen.add(key)
        hyps.append({"kind": "shape", "shape": nm, "n": n, "k": k,
                     "ls": ls, "exit": list(ex) if ex else None,
                     "hold_s": hold, "cond": cond,
                     "_family": f"shape/{nm}"})
    return hyps


def mutate_shape(h, rng, extra_conds=None):
    """Nudge one attribute of a shape hypothesis, keeping it valid.

    Used by the archive's breeding loop. Exactly ONE attribute changes
    per call, which is what makes a lineage informative: if a child
    beats its parent you know which change did it. Mutating several at
    once turns the archive into a random search wearing a pedigree.

    A child that is not a shape hypothesis is returned untouched --
    crossover can only produce coherent members of a family, and this
    must not be the thing that breaks that.
    """
    if not isinstance(h, dict) or h.get("kind") != "shape":
        return h
    c = dict(h)
    conds = ["none"] + list(extra_conds or []) + \
        ["hi_vol", "lo_vol", "up_day", "dn_day"]
    # CONTINUOUS NUDGES, not jumps to another grid point. In a
    # continuous space a mutation that resamples uniformly is just a
    # fresh random draw wearing a parent's name -- it carries no
    # information from the parent and the archive stops being a search
    # and becomes a lottery. Small multiplicative steps keep a child
    # near its parent, which is what makes "this child beat its parent"
    # mean something.
    pick = int(rng.integers(6))
    if pick == 0:
        c["shape"] = list(SHAPES)[int(rng.integers(len(SHAPES)))]
        c["_family"] = f"shape/{c['shape']}"
    elif pick == 1:
        cur = int(c.get("n") or 3)
        c["n"] = int(min(N_RANGE[1], max(N_RANGE[0],
                                         cur + int(rng.choice([-2, -1, 1, 2])))))
    elif pick == 2:
        cur = float(c.get("k") or 2.0)
        c["k"] = round(float(min(K_RANGE[1], max(
            K_RANGE[0], cur * float(rng.uniform(0.7, 1.4))))), 3)
    elif pick == 3:
        c["ls"] = LONGSHORT[int(rng.integers(2))]
    elif pick == 4:
        ex = c.get("exit")
        if not ex or rng.random() < 0.25:
            c["exit"] = list(draw_exit(rng) or []) or None
        else:
            st = float(min(STOP_RANGE[1], max(
                STOP_RANGE[0], float(ex[0]) * float(rng.uniform(0.7, 1.4)))))
            tg = float(min(TARG_RANGE[1], max(
                TARG_RANGE[0], float(ex[1]) * float(rng.uniform(0.7, 1.4)))))
            c["exit"] = [round(st, 2), round(tg, 2)]
    else:
        # Hold length moves by a STEP rather than jumping anywhere in
        # the list. The archive's whole purpose is to improve a niche,
        # and hold length is one of the axes that defines the niche --
        # a free jump would keep throwing children into other cells
        # instead of refining the one they came from.
        cur = float(c.get("hold_s") or 300)
        step = float(rng.uniform(0.6, 1.7))
        c["hold_s"] = int(max(HOLD_MIN_S, min(HOLD_MAX_S,
                                              round(cur * step))))
    c.setdefault("_family", f"shape/{c.get('shape', 'x')}")
    c.pop("market", None)
    c.pop("tier", None)
    return c


DEST_LEVELS = ["prior_high", "prior_low", "prior_close", "session_open",
               "day_high_so_far", "day_low_so_far",
               "swing_high_20", "swing_low_20",
               "swing_high_60", "swing_low_60",
               "round_10_up", "round_10_dn", "round_50_up", "round_50_dn"]
DEST_BARS = [6, 12, 24, 48, 96]


def from_destinations(rng, triggers, cap=600):
    """Destination / trigger / invalidation hypotheses.

    Nothing here is a configuration. The destination is a level the tape
    keeps returning to, the trigger is a state that precedes the
    journey, and the STOP IS NOT SPECIFIED -- it is measured afterwards
    from where eventual winners actually travelled. That last part is
    the difference between this family and every other one: elsewhere
    the exit is drawn from a list somebody wrote down.
    """
    hyps, seen = [], set()
    trig = list(triggers) + ["none"]
    tries = 0
    while len(hyps) < cap and tries < cap * 8:
        tries += 1
        lvl = DEST_LEVELS[int(rng.integers(len(DEST_LEVELS)))]
        side = 1 if rng.integers(2) else -1
        tg = trig[int(rng.integers(len(trig)))]
        mb = int(DEST_BARS[int(rng.integers(len(DEST_BARS)))])
        key = (lvl, side, tg, mb)
        if key in seen:
            continue
        seen.add(key)
        hyps.append({"kind": "dest", "level": lvl, "side": side,
                     "trigger": tg, "max_bars": mb,
                     "hold_s": mb * 300,
                     "_family": f"dest/{lvl}"})
    return hyps


def shape_why(name):
    return SHAPES.get(name, "")


def flow_series(d, mech):
    """Evaluate a named mechanism on a book tape."""
    for m in FLOW:
        if m["name"] == mech:
            if not all(c in d.columns for c in m["cols"]):
                return None
            try:
                return m["expr"](d).values.astype(float)
            except Exception:                                 # noqa: BLE001
                return None
    return None


def flow_why(mech):
    for m in FLOW:
        if m["name"] == mech:
            return m["why"]
    return ""


# ------------------------------------------------- recurring behaviour
# SHAPES. Recurring price behaviour, as opposed to clock buckets. Each
# is a configuration the tape falls into repeatedly and that somebody
# has to react to -- a run of one-way closes leaves trapped late
# entrants, a range contraction stores energy that has to release, a
# gap is an overnight repricing that intraday participants must adapt
# to. These are the closest thing here to what a chart reader means by
# a pattern, expressed so a machine can count them.
SHAPES = {
    "run_up": ("N consecutive higher closes. Momentum that has already "
               "persuaded people, which means late entrants are long "
               "and their stops are below."),
    "run_dn": ("N consecutive lower closes. The mirror -- and not "
               "assumed to behave like the mirror, since both "
               "directions are tested separately."),
    "squeeze": ("Range contracted well below its own recent normal. "
                "Volatility clusters, so a quiet stretch is followed by "
                "a loud one more often than chance -- the open question "
                "is only whether the direction is predictable."),
    "expansion": ("Range expanded well above normal: something arrived. "
                  "Whether it continues or reverts is the test."),
    "inside": ("Bar contained entirely within the previous bar's range. "
               "Nobody was willing to push, so the prior range is the "
               "reference everyone is watching."),
    "outside": ("Bar engulfing the previous bar's range. Both sides got "
                "run, which means stops on both sides were taken."),
    "gap": ("Session opened away from the prior close. An overnight "
            "repricing that intraday participants have to adapt to."),
    "close_high": ("Closed in the top of its own range -- buyers held "
                   "the level into the bell rather than fading."),
    "close_low": ("Closed at the bottom of its own range."),
}
SHAPE_N = [2, 3, 4]          # legacy anchors, kept for the self-tests
SHAPE_K = [1.5, 2.5]

# ---------------------------------------------------------------------
# THE SPACE HAD A FLOOR AND THE SEARCH HIT IT.
#
# Counted: 9 shapes x 3 lengths x 2 widths x 2 sides x 13 exits x 4 holds
# x 5 conditions = 28,080 distinct shape hypotheses, plus about 1,360
# footprint cells per market which are DETERMINISTIC -- the same tape
# yields the same buckets every cycle, so after the first cycle every
# one of them is already in the ledger.
#
# The searcher had run 256,959 trials against a universe of roughly
# thirty thousand ideas. It was not slow; it had nothing left to test.
# Each cycle it generated thousands of candidates, `seen()` rejected
# ~97% of them as already measured, and the counter crawled at twenty
# an hour. No amount of extra cores touches that -- the bottleneck was
# the size of the question set, not the speed of answering it.
#
# So the parameters are CONTINUOUS now. Hold length is any number of
# seconds on a log scale, stop and target are real multipliers rather
# than three-by-four, run length reaches twelve bars and the squeeze
# width is a real number. The space stops being a grid to exhaust and
# becomes a landscape to navigate -- which is exactly what the archive's
# breeding is for, and why the two changes belong together.
#
# The bar keeps this honest. An unbounded space does not weaken the
# standard: every draw is still a trial, and the bar still rises as
# sqrt(2 ln N). At a million trials it is 6.06 sigma, at ten million
# 6.50 -- the growth is logarithmic, so a far larger space costs
# surprisingly little in required strength while removing the ceiling
# entirely.
HOLD_MIN_S, HOLD_MAX_S = 15.0, 14400.0      # 15 seconds to four hours
STOP_RANGE = (0.4, 6.0)                     # in units of realised vol
TARG_RANGE = (0.4, 8.0)
N_RANGE = (2, 12)                           # bars in a run pattern
K_RANGE = (1.05, 4.0)                       # sigma for squeeze/expansion
P_TIME_EXIT = 0.18                          # share with no bracket


# ---------------------------------------------------------------------
# SPEND THE BUDGET WHERE DETECTION IS POSSIBLE.
#
# Calibration measured the noise law on real NQ: per-trade dispersion
# grows as sqrt(hold) -- 68 round trips at five minutes, 113 at thirty,
# 244 at an hour, 505 at four hours -- and a bracket truncates it
# (0.5x/0.5x cuts thirty-minute noise from 113 to 40). Since the
# smallest detectable edge is bar * noise / sqrt(n), the long-hold
# wide-bracket corner of the space CANNOT detect any edge worth having,
# whatever is actually there.
#
# Measured on the draw as it stood: of 400 slate hypotheses, 0.8% could
# have detected a +0.30 RT edge and the median could only have seen
# +2.11 RT -- an edge that large is, by this project's own rule, far
# more likely a bug than a find. Ninety-nine percent of the search was
# being spent where it could not possibly succeed.
#
# And a wasted trial is not free. The bar rises as sqrt(2 ln N), so
# every hypothesis tested in a blind cell makes the standard harder for
# every hypothesis tested anywhere else. Searching where you cannot see
# is strictly worse than not searching.
#
# THE TILT IS DERIVED, NOT CHOSEN. Log-uniform sampling puts equal
# effort in each octave of hold length. Weighting by 1/sqrt(hold) --
# exactly cancelling the measured noise growth -- puts equal effort per
# unit of DETECTABILITY instead, which is the thing worth equalising.
# In log space that is a truncated exponential with lambda = 1/2.
#
# A quarter of every draw ignores the tilt entirely. The noise law is a
# measurement and could be wrong; the archive needs coverage of the slow
# corner regardless; and a search that only looks where it expects to
# see is not a search. That share is explicit so it can be argued with.
HOLD_TILT = float(os.environ.get("RESEARCH_HOLD_TILT", "0.5"))
WIDTH_TILT = float(os.environ.get("RESEARCH_WIDTH_TILT", "2.0"))
EXPLORE_WIDE = float(os.environ.get("RESEARCH_EXPLORE_WIDE", "0.25"))


def draw_hold(rng, tilt=None):
    """Hold length, tilted toward the regime where an edge is visible.

    tilt=0 is log-uniform. tilt=0.5 exactly cancels the sqrt(hold)
    growth in noise, so effort is spread evenly over detectability
    rather than over octaves.
    """
    a, b = math.log(HOLD_MIN_S), math.log(HOLD_MAX_S)
    lam = HOLD_TILT if tilt is None else float(tilt)
    if lam <= 0 or rng.random() < EXPLORE_WIDE:
        return int(round(math.exp(rng.uniform(a, b))))
    u = float(rng.random())
    ea, eb = math.exp(-lam * a), math.exp(-lam * b)
    x = -math.log(ea - u * (ea - eb)) / lam
    return int(round(math.exp(max(a, min(b, x)))))


def draw_exit(rng):
    """A stop/target pair, tilted toward the tight end, or a time exit.

    u**WIDTH_TILT with the exponent above one concentrates draws near
    the bottom of each range. Tight brackets truncate the outcome
    distribution, which is the other lever on detectability and the one
    that does not cost holding time.
    """
    if rng.random() < P_TIME_EXIT:
        return None
    wide = rng.random() < EXPLORE_WIDE
    p = 1.0 if wide else WIDTH_TILT
    lo, hi = STOP_RANGE
    stop = lo + (hi - lo) * float(rng.random()) ** p
    lo, hi = TARG_RANGE
    targ = lo + (hi - lo) * float(rng.random()) ** p
    return (round(stop, 2), round(targ, 2))


def draw_n(rng):
    return int(rng.integers(N_RANGE[0], N_RANGE[1] + 1))


def draw_k(rng):
    return round(float(rng.uniform(*K_RANGE)), 3)


# Per-sweep cache of shape masks and the rolling normaliser.
#
# PROFILED, NOT GUESSED. 79% of a hypothesis evaluation was
# rng.rolling(240).median() inside this function -- recomputed from
# scratch for every single hypothesis, and computed even for the six of
# nine shapes that never look at it. There are only 9 shapes x 3 lengths
# x 2 widths = 54 distinct masks per market, against hundreds of
# hypotheses per market that reuse them.
#
# The memo is passed in by the caller and lives for one market sweep, so
# it cannot leak between tapes -- keying a cache on id(DataFrame) would,
# because CPython reuses ids after garbage collection and the second
# tape would silently inherit the first one's masks.
def _normaliser(d, memo):
    """Rolling median bar range. The expensive part, computed at most
    once per tape and only when a shape actually needs it."""
    if memo is not None and "_nrm" in memo:
        return memo["_nrm"]
    c = d["close"]
    hi = d["high"] if "high" in d.columns else c
    lo = d["low"] if "low" in d.columns else c
    nrm = (hi - lo).rolling(240, min_periods=60).median()
    if memo is not None:
        memo["_nrm"] = nrm
    return nrm


def shape_mask(d, name, n=3, k=2.0, memo=None):
    """Boolean mask for a shape, computed only from PAST bars."""
    import numpy as _np
    key = (name, n, k)
    if memo is not None and key in memo:
        return memo[key]
    out = _shape_mask(d, name, n, k, memo)
    if memo is not None:
        memo[key] = out
    return out


def _shape_mask(d, name, n, k, memo):
    import numpy as _np
    c = d["close"]
    hi = d["high"] if "high" in d.columns else c
    lo = d["low"] if "low" in d.columns else c
    op = d["open"] if "open" in d.columns else c
    rng = (hi - lo)
    # LAZY. Six of the nine shapes below never touch the normaliser, and
    # it was the single most expensive line in the whole search.
    nrm = None
    if name in ("squeeze", "expansion", "gap"):
        nrm = _normaliser(d, memo)
    up = (c.diff() > 0)
    dn = (c.diff() < 0)
    if name == "run_up":
        return up.rolling(n).sum().eq(n).fillna(False).values
    if name == "run_dn":
        return dn.rolling(n).sum().eq(n).fillna(False).values
    if name == "squeeze":
        return (rng < nrm / k).fillna(False).values
    if name == "expansion":
        return (rng > nrm * k).fillna(False).values
    if name == "inside":
        return ((hi <= hi.shift(1)) & (lo >= lo.shift(1))).fillna(False).values
    if name == "outside":
        return ((hi > hi.shift(1)) & (lo < lo.shift(1))).fillna(False).values
    if name == "gap":
        prev_day = d.index.normalize().values != \
            _np.roll(d.index.normalize().values, 1)
        g = (op - c.shift(1)).abs() > nrm
        return (g.fillna(False).values & prev_day)
    if name == "close_high":
        return ((c - lo) / rng.replace(0, _np.nan) > 0.8).fillna(False).values
    if name == "close_low":
        return ((c - lo) / rng.replace(0, _np.nan) < 0.2).fillna(False).values
    return None


# ---------------------------------------------------------- exits
# BRACKETS. A hypothesis without an exit is a prediction; with one it is
# a strategy. Expressed in units of realised volatility so a single
# specification means the same thing in every market.
STOPS = [1.0, 2.0, 3.0]
TARGETS = [1.0, 2.0, 3.0, 5.0]
EXITS = [None] + [(s, t) for s in STOPS for t in TARGETS]


def describe(h) -> str:
    if h.get("kind") == "dest":
        d = "up to" if h["side"] > 0 else "down to"
        t = "" if h["trigger"] == "none" else f" after {h['trigger'].replace('_',' ')}"
        return (f"price travels {d} {h['level'].replace('_',' ')}"
                f"{t}, stop learned from where winners went")
    if h.get("kind") == "shape":
        ex = h.get("exit")
        tail = (f", stop {ex[0]}x vol, target {ex[1]}x vol"
                if ex else f", hold {h['hold_s']}s")
        nm = h["shape"].replace("_", " ")
        extra = f" ({h['n']} bars)" if h["shape"].startswith("run") else ""
        return f"after {nm}{extra}, go {h['ls']}{tail}"
    if h.get("kind") == "flow":
        q = "high" if h["side"] == "hi" else "low"
        return (f"when {h['mech'].replace('_', ' ')} is {q}, go "
                f"{h['ls']}, hold {h['hold_s']}s")
    if h.get("kind") == "feature":
        q = "top" if h["side"] == "hi" else "bottom"
        return (f"when {h['feat']} is in its {q} quintile, go "
                f"{h['ls']}, hold {h['hold_s']}s")
    if h.get("kind") != "footprint":
        return str(h)
    d = "trade with the move" if h["dir"] == "with" else "fade the move"
    c = "" if h["cond"] == "none" else f", only when {h['cond']}"
    return (f"at {h['dim']}={h['bucket']} (flagged on {h['metric']}), "
            f"{d}, hold {h['hold_s']}s{c}")
