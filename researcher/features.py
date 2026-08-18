"""Compositional feature discovery -- the part that can actually learn.

THE MINECRAFT COMPARISON, and why it decides the design.

Voyager works because Minecraft gives dense, verifiable, STATIONARY
feedback: you either got the diamond or you did not, and the rule for
getting diamonds never changes. Markets give the opposite -- feedback is
mostly noise, a good strategy loses six times in ten, and the
environment adapts to whoever exploits it. An agent that learns from
P&L feedback on market data learns to overfit. That is not a risk, it is
the definition of what it would be doing, and it is exactly the 1.38
billion configs with a measured NEGATIVE return recorded as ledger #19.

So the learning cannot be about which strategy won. It has to be about
HOW TO LOOK. This module is the part that grows: a library of feature
PRIMITIVES that get composed into new features, where a composition is
retained not because it made money but because it REVEALED STRUCTURE --
it separated the tape into buckets that behave differently from each
other.

    kept because it produced dispersion, not because it produced profit

WHAT THAT DOES AND DOES NOT BUY. Dispersion is symmetric: it asks
whether the buckets DIFFER, never which one pays. So it cannot select a
direction, and a feature kept here carries no claim about profit.

But it is NOT outcome-blind, and an earlier draft of this file claimed
it was. Dispersion is computed against forward returns. Selecting the
top scorers out of hundreds of composed candidates therefore CAN find
spurious dispersion, exactly the way any search finds spurious anything.
The protection is not the criterion, it is the control:
`features_selftest.py` runs the entire three-generation growth against
targets that cannot carry information and reports the maximum it reaches
anyway. That number, not the criterion's good intentions, is the
threshold. And every trial spent scoring a candidate here has to be
counted in the ledger alongside the hypothesis trials, because it is the
same search.

HOW COMPOSITION WORKS

  depth 0   raw columns                       close, vol, n, absret
  depth 1   one primitive applied             zscore(vol, 60)
  depth 2   primitive of a depth-1 feature    rank(zscore(vol, 60))
  depth 3   interaction of two survivors      zscore(vol,60) * ret_sign

Each generation keeps the features that discriminate, drops the rest,
and composes the survivors. That is a skill library in Voyager's sense:
useful pieces are retained and built upon, and the vocabulary grows
beyond anything specified up front.

WHAT IT STILL CANNOT DO. It cannot tell you a feature is tradable. A
feature that splits the tape cleanly may split it into buckets whose
forward returns are identical. Discovery here only proposes; the ledger,
the rising bar and the sealed vault still decide.
"""
import os

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- prims
# Each primitive is (name, arity, fn). Deliberately small and cheap:
# the value is in COMPOSITION, not in any single clever transform.
def _z(x, w):
    s = pd.Series(x)
    m = s.rolling(w, min_periods=max(5, w // 4)).mean()
    sd = s.rolling(w, min_periods=max(5, w // 4)).std()
    return ((s - m) / sd.replace(0, np.nan)).values


def _rank(x, w):
    # pandas' native rolling rank is the Cython path and is ~10x the
    # rolling-apply version, correlation 1.000 with it. At hundreds of
    # candidates per generation that is the difference between a
    # self-test that finishes and one that appears to hang.
    return pd.Series(x).rolling(w, min_periods=max(5, w // 4)) \
        .rank(pct=True).values


def _chg(x, k):
    s = pd.Series(x)
    return (s - s.shift(k)).values


def _ratio(x, w):
    s = pd.Series(x)
    m = s.rolling(w, min_periods=max(5, w // 4)).median()
    return (s / m.replace(0, np.nan)).values


def _sign(x, _):
    return np.sign(np.asarray(x, dtype=float))


def _absv(x, _):
    return np.abs(np.asarray(x, dtype=float))


UNARY = {
    "z": (_z, [20, 60, 240]),
    "rank": (_rank, [60, 240]),
    "chg": (_chg, [1, 3, 12]),
    "ratio": (_ratio, [60, 240]),
    "sign": (_sign, [0]),
    "abs": (_absv, [0]),
}
# RANGE IS A BASE COLUMN, because a whole class of indicator is built
# from it and none of them were reachable without it.
#
# The grower composed from close/vol/n/absret only, so every feature it
# could invent was a function of the CLOSE series and volume. That
# silently excluded everything built on the bar's range: ATR, ADX,
# Supertrend, and the true-range family generally. The brackets and the
# shape patterns had high/low all along -- only the feature grower was
# blind to them, which is the kind of gap that never announces itself.
#
# `hl` is the bar range and `gap` the overnight/inter-bar jump; both are
# differences rather than levels, so they are stationary in the way the
# unary primitives (z, rank, ratio) expect, which raw high/low are not.
# A raw high is just the price again and would waste a generation
# rediscovering close.
BASE = ["close", "vol", "n", "absret", "hl", "gap"]


class _BoundedMemo(dict):
    """A dict that forgets its oldest entries once it is full.

    Insertion-ordered, so popping the first key evicts the least
    recently ADDED value. Deliberately not a true LRU: the access
    pattern here is a scan over candidates grouped by seed, where
    recency of insertion and recency of use coincide, and a real LRU
    would cost a reordering on every hit for no benefit.
    """

    def __init__(self, cap=48):
        super().__init__()
        self.cap = max(4, int(cap))

    def __setitem__(self, k, v):
        super().__setitem__(k, v)
        while len(self) > self.cap:
            super().__delitem__(next(iter(self)))


class FeatureLibrary:
    """Grows a vocabulary of features, keeping what discriminates."""

    def __init__(self, keep=24):
        self.keep = keep
        self.kept = {}          # name -> spec
        self.scores = {}        # name -> dispersion score
        self.generation = 0

    # ---------- persistence ----------
    #
    # THE LIBRARY LIVED IN MEMORY ONLY, AND THE PROCESS RESTARTS.
    #
    # Feature discovery is compositional: generation two builds on the
    # features generation one kept, generation three on those. The kept
    # set is the seed list, so losing it does not merely cost the time
    # to regrow -- it resets the SEARCH to first principles. Production
    # had restarted twenty-eight times, so the deep compositions this
    # design exists to find had never been reached, and the console
    # showed it plainly: "features grown and kept" at 0 with a 24-hour
    # movement of -488.
    #
    # Only names and scores are stored. parse() rebuilds the spec from
    # the name, so there is no second serialisation format to keep in
    # step with the first -- and the name/spec round trip already has a
    # self-test guarding exactly that property.

    def dump(self):
        return {"keep": self.keep, "generation": self.generation,
                "scores": dict(self.scores)}

    @classmethod
    def load(cls, d):
        lib = cls(keep=int((d or {}).get("keep", 24)))
        lib.generation = int((d or {}).get("generation", 0))
        bad = 0
        for nm, sc in ((d or {}).get("scores") or {}).items():
            try:
                sp = cls.parse(nm)
            except Exception:                                 # noqa: BLE001
                sp = None
            if sp is None:
                # A name the current grammar cannot read is from an older
                # one. Dropping it is correct; doing so silently is not,
                # because a library that quietly shrinks every deploy
                # looks exactly like one that is working.
                bad += 1
                continue
            lib.kept[nm] = sp
            lib.scores[nm] = float(sc)
        lib._unparseable = bad
        return lib

    # ---------- construction ----------
    @staticmethod
    def evaluate_spec(df, spec, memo=None):
        """spec = ('base', col) | ('un', prim, param, sub) |
                  ('mul', subA, subB)

        `memo` caches by feature name within one generation. Without it
        a depth-3 spec recomputes its whole subtree, and since every
        depth-3 candidate shares its subtree with many siblings the
        generation costs roughly the square of what it should.
        """
        nm = FeatureLibrary.name(spec)
        if memo is not None and nm in memo:
            return memo[nm]
        kind = spec[0]
        if kind == "base":
            v = np.asarray(df[spec[1]].values, dtype=float)
        elif kind == "un":
            _, prim, param, sub = spec
            x = FeatureLibrary.evaluate_spec(df, sub, memo)
            v = UNARY[prim][0](x, param)
        elif kind == "mul":
            a = FeatureLibrary.evaluate_spec(df, spec[1], memo)
            b = FeatureLibrary.evaluate_spec(df, spec[2], memo)
            v = a * b
        else:
            raise ValueError(spec)
        # cap the cache: each entry is one float64 column (~1.5 MB on a
        # 185k-bar tape) and an uncapped memo across a large generation
        # is hundreds of MB on a machine with no swap.
        if memo is not None and len(memo) < 400:
            memo[nm] = v
        return v

    @staticmethod
    def parse(name):
        """Rebuild a spec from its printed name. The inverse of name().

        Needed because the ledger stores hypotheses by feature NAME, and
        re-scoring an old entry later -- to fill in trade metrics that
        did not exist when it was first tested -- requires the feature
        itself, on whatever tape the hypothesis was tested on. Without
        this those rows can never be completed, and they are exactly the
        rows that stay at the top of the leaderboard.

        The grammar is closed and tiny: base | prim(sub[,param]) | a*b.
        """
        t = str(name).strip()
        depth = 0
        for i, ch in enumerate(t):                       # split on top-level *
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "*" and depth == 0:
                a = FeatureLibrary.parse(t[:i])
                b = FeatureLibrary.parse(t[i + 1:])
                return ("mul", a, b) if a and b else None
        if "(" not in t:
            return ("base", t) if t else None
        prim = t[:t.index("(")]
        if prim not in UNARY:
            return None
        inner = t[t.index("(") + 1:t.rindex(")")]
        depth, cut = 0, None
        for i, ch in enumerate(inner):                   # last top-level comma
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                cut = i
        if cut is None:
            sub, param = FeatureLibrary.parse(inner), 0
        else:
            sub = FeatureLibrary.parse(inner[:cut])
            try:
                param = int(inner[cut + 1:])
            except ValueError:
                return None
        return ("un", prim, param, sub) if sub else None

    @staticmethod
    def name(spec):
        k = spec[0]
        if k == "base":
            return spec[1]
        if k == "un":
            p = f",{spec[2]}" if spec[2] else ""
            return f"{spec[1]}({FeatureLibrary.name(spec[3])}{p})"
        return f"{FeatureLibrary.name(spec[1])}*{FeatureLibrary.name(spec[2])}"

    # ---------- the selection criterion ----------
    @staticmethod
    def dispersion(x, y, q=5):
        """How differently do the tape's buckets behave, by this feature?

        Split the feature into quintiles and measure the spread of mean
        forward return across them, in units of its own standard error.
        This is NOT profit -- it never asks whether any bucket is
        positive, only whether the buckets DIFFER. A feature that sorts
        the world into groups that behave alike is useless however
        profitable one group looks.
        """
        ok = np.isfinite(x) & np.isfinite(y)
        if ok.sum() < 2000:
            return 0.0
        xv, yv = x[ok], y[ok]
        try:
            b = pd.qcut(pd.Series(xv), q, labels=False, duplicates="drop")
        except Exception:                                     # noqa: BLE001
            return 0.0
        g = pd.DataFrame({"b": b, "y": yv}).groupby("b")["y"]
        m, c = g.mean(), g.count()
        if len(m) < 3:
            return 0.0
        se = yv.std(ddof=1) / np.sqrt(c.clip(lower=1))
        return float(np.nanmax(np.abs(m - yv.mean()) / se.replace(0, np.nan)))

    # ---------- growth ----------
    def grow(self, df, y, rng, base_cols=None):
        """One generation: propose, score on dispersion, keep the best.

        `base_cols` lets a tier contribute its own vocabulary. The book
        tier has queue depletion, add rates, spread and trade-flow
        columns that exist nowhere else and cannot be reconstructed
        from trades -- restricting composition to close/vol/n/absret
        there would throw away the only thing that tier is for.
        """
        self.generation += 1
        cols = [c for c in (base_cols or BASE) if c in df.columns]
        cands = []
        if not self.kept:
            for c in cols:
                cands.append(("base", c))
        seeds = list(self.kept.values()) or [("base", c) for c in cols]
        for s in seeds:
            for prim, (_fn, params) in UNARY.items():
                for p in params:
                    cands.append(("un", prim, p, s))
        if len(seeds) >= 2:
            for _ in range(min(24, len(seeds) * 2)):
                a, b = rng.choice(len(seeds), 2, replace=False)
                cands.append(("mul", seeds[a], seeds[b]))

        scored = []
        # BOUNDED. This memo exists so a seed's array is computed once
        # and reused by its children, but it was unbounded across the
        # whole generation: hundreds of candidates, each caching a
        # full-length float array, freed only when grow() returned.
        # Measured at 430 MB of transient peak for ONE market -- and
        # with several markets growing features at the same time, that
        # sum is what got the container killed.
        #
        # Candidates are emitted grouped by seed, so a small window
        # keeps essentially all of the reuse and none of the hoard.
        memo = _BoundedMemo(int(os.environ.get("FEATURE_MEMO", "48")))
        for sp in cands:
            nm = self.name(sp)
            if nm in self.scores:
                continue
            try:
                x = self.evaluate_spec(df, sp, memo)
            except Exception:                                 # noqa: BLE001
                continue
            d = self.dispersion(x, y)
            if np.isfinite(d) and d > 0:
                scored.append((d, nm, sp))
        scored.sort(reverse=True)
        for d, nm, sp in scored[:self.keep]:
            self.kept[nm] = sp
            self.scores[nm] = round(float(d), 3)
        # prune to the best `keep`
        if len(self.kept) > self.keep:
            best = sorted(self.scores.items(), key=lambda kv: -kv[1])
            best = dict(best[:self.keep])
            self.kept = {k: v for k, v in self.kept.items() if k in best}
            self.scores = best
        return [(nm, self.scores[nm]) for nm in self.kept]

    def state(self):
        return {"generation": self.generation,
                "n_kept": len(self.kept),
                "top": sorted(self.scores.items(),
                              key=lambda kv: -kv[1])[:10]}
