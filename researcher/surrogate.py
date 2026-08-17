"""A map of the search space, learned from every result so far.

WHAT THIS IS FOR. The ledger holds two hundred thousand measurements and
used them for exactly one thing: refusing to repeat them. That is a
waste of the most expensive asset the project has. Two hundred thousand
answers about which corners of the space pay and which do not is a MAP,
and the searcher was walking past it every cycle.

The model predicts the cost-normalised edge of a hypothesis BEFORE it is
tested, from its attributes -- family, shape, direction, hold length,
exit, condition, market, tier -- together with an honest error bar. It
is used for two things:

  1  ORDERING. The same trial budget, spent on the most promising and
     the most UNCLEAR candidates first instead of in arbitrary order.
     Nothing is skipped and nothing is cheapened: every hypothesis
     tested still pays a full trial and still faces the same rising bar
     and the same gauntlet. Only the order changes, and order is free.

  2  SAYING WHAT IT HAS WORKED OUT. "Holds under two minutes lose 0.31
     of a round trip on average across 18,400 tests" is a finding about
     the market, stated with a number and a sample size. That is the
     kind of learning that was missing: the Learning tab could show what
     the searcher had CHANGED but never what it had come to KNOW.

WHY THIS MODEL AND NOT A GRADIENT-BOOSTED ONE. LightGBM is installed and
would fit better. It would also be unreadable, and the second use above
is at least as valuable as the first -- an accurate oracle that cannot
explain itself teaches nobody anything. This is an additive model with
empirical-Bayes shrinkage: each attribute value gets an effect pulled
toward the global mean in proportion to how little evidence supports it,
so a bucket seen twice barely moves and a bucket seen ten thousand times
moves freely. Backfitting handles the fact that the attributes are
correlated.

THE RISK, STATED PLAINLY. Ordering by predicted quality enriches the
tested set for things that looked good in the past, on the same tape.
That cannot manufacture significance -- the bar counts trials spent, the
vault is untouched, and a pooled mechanism still has to hold up in
markets it was not chosen from -- but it does mean the searcher will
concentrate where the tape has been kind, and a quirk of this particular
history will get more attention than it deserves. The explore share
below exists to bound that: a fixed fraction of every cycle is spent
where the model is most UNCERTAIN rather than where it is most hopeful.
"""
from __future__ import annotations

import math

import numpy as np

# Shrinkage strength. An attribute value needs about this many
# observations before its measured mean is believed at half weight.
PRIOR_N = 60.0
# Fraction of each cycle spent on the model's blind spots rather than
# its favourites.
EXPLORE = 0.35
# Numeric attributes are bucketed on a log scale; these are the edges.
HOLD_BUCKETS = [0, 90, 400, 1200, 3600, 10 ** 9]


def _hold_bucket(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "?"
    for i in range(len(HOLD_BUCKETS) - 1):
        if HOLD_BUCKETS[i] <= v < HOLD_BUCKETS[i + 1]:
            lo, hi = HOLD_BUCKETS[i], HOLD_BUCKETS[i + 1]
            return f"{lo}-{hi}s" if hi < 10 ** 9 else f"{lo}s+"
    return "?"


def attrs(h, family=None):
    """The readable attributes of a hypothesis.

    Deliberately coarse. The point is to learn about REGIONS -- short
    holds, fades, bracketed exits -- not to memorise individual cells,
    which the ledger already does perfectly.
    """
    a = {}
    if family:
        a["family"] = str(family).split("/")[0]
        a["subfamily"] = str(family)
    for k in ("kind", "shape", "dir", "ls", "cond", "side", "mech", "dim"):
        v = h.get(k)
        if v is not None:
            a[k] = str(v)
    if h.get("hold_s") is not None:
        a["hold"] = _hold_bucket(h["hold_s"])
    ex = h.get("exit")
    if isinstance(ex, (list, tuple)) and len(ex) == 2:
        try:
            stop, targ = float(ex[0]), float(ex[1])
            a["exit"] = "bracket"
            a["rr_shape"] = ("tight-target" if targ < stop else
                             "wide-target" if targ > stop else "even")
            a["stop_x"] = f"{stop:g}x"
        except (TypeError, ValueError):
            pass
    elif ex is not None:
        a["exit"] = str(ex)
    else:
        a["exit"] = "time"
    if h.get("market"):
        a["market"] = str(h["market"]).split("@")[0]
    if h.get("tier") is not None:
        a["tier"] = f"t{h['tier']}"
    return a


class Surrogate:
    """Additive, shrunk, backfitted. Cheap to fit, possible to read."""

    def __init__(self, prior_n=PRIOR_N):
        self.prior_n = float(prior_n)
        self.global_mean = 0.0
        self.eff = {}        # attr -> value -> (effect, n, se)
        self.n = 0
        self.resid_sd = 1.0

    # -------------------------------------------------------- fitting
    def fit(self, rows, passes=3):
        """`rows` is a sequence of (attrs_dict, y). y in cost units."""
        rows = [(a, float(y)) for a, y in rows
                if a and y is not None and np.isfinite(y)]
        self.n = len(rows)
        if self.n < 200:
            return self
        ys = np.array([y for _, y in rows], float)
        # Trim the extreme tails before fitting. A handful of artifact
        # cells at 40 cost units would otherwise define the model's idea
        # of a good region -- which is precisely backwards, since those
        # are the cells the controls exist to destroy.
        lo, hi = np.percentile(ys, [1, 99])
        keep = (ys >= lo) & (ys <= hi)
        rows = [r for r, k in zip(rows, keep) if k]
        ys = ys[keep]
        self.global_mean = float(ys.mean())

        keys = sorted({k for a, _ in rows for k in a})
        self.eff = {k: {} for k in keys}
        for _ in range(passes):
            for k in keys:
                # residual after every OTHER attribute's current effect
                sums, cnts, sqs = {}, {}, {}
                for a, y in rows:
                    v = a.get(k)
                    if v is None:
                        continue
                    pred = self.global_mean
                    for k2, v2 in a.items():
                        if k2 == k:
                            continue
                        e = self.eff.get(k2, {}).get(v2)
                        if e:
                            pred += e[0]
                    r = y - pred
                    sums[v] = sums.get(v, 0.0) + r
                    cnts[v] = cnts.get(v, 0) + 1
                    sqs[v] = sqs.get(v, 0.0) + r * r
                new = {}
                for v, c in cnts.items():
                    m = sums[v] / c
                    var = max(sqs[v] / c - m * m, 0.0)
                    # empirical-Bayes shrink toward zero effect
                    shrunk = m * (c / (c + self.prior_n))
                    se = math.sqrt(var / max(c, 1)) if c else float("inf")
                    new[v] = (float(shrunk), int(c), float(se))
                self.eff[k] = new

        res = np.array([y - self.predict_attrs(a)[0] for a, y in rows])
        self.resid_sd = float(res.std(ddof=1)) if len(res) > 1 else 1.0
        return self

    # ------------------------------------------------------ prediction
    def predict_attrs(self, a):
        """(expected edge in cost units, uncertainty)."""
        pred = self.global_mean
        var = 0.0
        unknown = 0
        for k, v in (a or {}).items():
            e = self.eff.get(k, {}).get(v)
            if e is None:
                unknown += 1
                continue
            pred += e[0]
            var += e[2] ** 2
        # Never seen this combination of values -> say so, loudly, by
        # returning a large error bar. That is what makes a candidate
        # attractive to the explore half of the budget.
        unc = math.sqrt(var) + 0.35 * self.resid_sd * unknown
        if self.n < 200:
            unc = max(unc, 1.0)
        return float(pred), float(unc)

    def predict(self, h, family=None):
        return self.predict_attrs(attrs(h, family))

    # -------------------------------------------------------- ordering
    def order(self, hyps, families=None, explore=EXPLORE, rng=None):
        """Most promising first, interleaved with least understood.

        Returns the same list, reordered. Nothing is dropped: a searcher
        that silently discards candidates is choosing what it will never
        know, and doing it without a record.
        """
        if self.n < 200 or not hyps:
            return list(hyps)
        rng = rng or np.random.default_rng(0)
        fam = families or {}
        scored = []
        for i, h in enumerate(hyps):
            mu, unc = self.predict(h, fam.get(id(h)))
            scored.append((i, mu, unc))
        by_hope = sorted(scored, key=lambda t: -t[1])
        by_doubt = sorted(scored, key=lambda t: -t[2])
        out, taken = [], set()
        n_explore = max(1, int(len(hyps) * explore))
        di = 0
        for rank, (i, _mu, _u) in enumerate(by_hope):
            # every 1/explore-th slot goes to the least understood
            if len(out) and explore > 0 and rank % max(
                    int(1 / explore), 2) == 0 and di < n_explore:
                while di < len(by_doubt) and by_doubt[di][0] in taken:
                    di += 1
                if di < len(by_doubt):
                    j = by_doubt[di][0]
                    out.append(hyps[j]); taken.add(j); di += 1
            if i not in taken:
                out.append(hyps[i]); taken.add(i)
        for i, _m, _u in scored:
            if i not in taken:
                out.append(hyps[i]); taken.add(i)
        return out

    # ----------------------------------------------------- readability
    def learned(self, min_n=400, top=14):
        """What the map says, in sentences a person can check.

        Only buckets with real evidence behind them, ranked by how far
        they sit from average, with the sample size attached so the
        reader can judge for themselves.
        """
        rows = []
        for k, vals in self.eff.items():
            for v, (e, c, se) in vals.items():
                if c < min_n or se <= 0:
                    continue
                t = abs(e) / (se + 1e-12)
                if t < 3.0:
                    continue        # not distinguishable from average
                rows.append({"attr": k, "value": v, "effect": round(e, 4),
                             "n": c, "t": round(t, 1)})
        rows.sort(key=lambda r: -abs(r["effect"]))
        return rows[:top]

    def sentences(self, **kw):
        out = []
        for r in self.learned(**kw):
            direction = "better" if r["effect"] > 0 else "worse"
            out.append(
                f"{r['attr']} = {r['value']}: {abs(r['effect']):.3f} of a "
                f"round trip {direction} than average, over {r['n']:,} "
                f"tests")
        return out


def from_ledger(led, cap=120000):
    """Build the training set out of everything measured so far.

    Cost units, so markets are comparable. Stubs and rows without a
    usable measurement are skipped.
    """
    rows = []
    for _fp, rec in list(led.d["tested"].items())[-cap:]:
        if not isinstance(rec, dict) or rec.get("stub"):
            continue
        r = rec.get("result") or {}
        h = rec.get("hyp") or {}
        if not r or not h:
            continue
        y = r.get("cu")
        if y is None:
            continue        # measured before cost units were recorded
        rows.append((attrs(h, rec.get("family")), float(y)))
    return rows


# ------------------------------------------------------------ self-test
def selftest(verbose=True):
    """It must find planted structure, resist noise, and admit ignorance."""
    fails = []
    rng = np.random.default_rng(4)

    # A space where short holds genuinely lose and fades genuinely pay,
    # with everything else noise.
    truth = {"hold": {"0-90s": -0.40, "90-400s": -0.10, "400-1200s": 0.0,
                      "1200-3600s": 0.10, "3600s+": 0.15},
             "dir": {"with": -0.05, "against": 0.20}}
    rows = []
    for _ in range(9000):
        hb = rng.choice(list(truth["hold"]))
        dr = rng.choice(list(truth["dir"]))
        mk = rng.choice(["ES", "NQ", "CL", "ZB", "GC"])
        y = truth["hold"][hb] + truth["dir"][dr] + rng.normal(0, 0.6)
        rows.append(({"hold": hb, "dir": dr, "market": mk}, y))
    s = Surrogate().fit(rows)

    got = {r["value"]: r["effect"] for r in s.learned(min_n=100, top=50)
           if r["attr"] == "hold"}
    ok = got.get("0-90s", 0) < -0.20 and got.get("3600s+", 0) > 0.05
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  recovers planted structure  "
              f"— short holds {got.get('0-90s', 0):+.2f}, long holds "
              f"{got.get('3600s+', 0):+.2f} (truth -0.40 / +0.15)")
    if not ok:
        fails.append("did not recover planted structure")

    # It must NOT invent structure in the attribute that has none.
    mkt = [r for r in s.learned(min_n=100, top=50) if r["attr"] == "market"]
    ok = not mkt
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  invents nothing about the "
              f"attribute with no signal  — {len(mkt)} market claims made "
              f"(expect 0)")
    if not ok:
        fails.append("invented structure in a null attribute")

    # Unseen values must come back with a wide error bar, not a
    # confident guess.
    _mu, u_known = s.predict_attrs({"hold": "0-90s", "dir": "with"})
    _mu2, u_new = s.predict_attrs({"hold": "brand-new", "dir": "with"})
    ok = u_new > u_known * 1.5
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  admits ignorance on unseen "
              f"ground  — uncertainty {u_known:.2f} known vs {u_new:.2f} "
              f"unknown")
    if not ok:
        fails.append("confident about ground it has never seen")

    # Ordering must put the good region first without dropping anything.
    hyps = ([{"hold_s": 30, "dir": "with"}] * 60 +
            [{"hold_s": 7200, "dir": "against"}] * 60)
    rng2 = np.random.default_rng(1)
    ordered = s.order(hyps, explore=0.0, rng=rng2)
    top20 = sum(1 for h in ordered[:20] if h["hold_s"] == 7200)
    ok = len(ordered) == len(hyps) and top20 >= 18
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  spends the budget on the "
              f"better region first  — {top20}/20 of the first slots, "
              f"{len(ordered)} of {len(hyps)} kept")
    if not ok:
        fails.append("ordering wrong or lossy")

    # A model with almost no data must not pretend to order anything.
    tiny = Surrogate().fit(rows[:50])
    ok = tiny.order(hyps) == hyps
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  refuses to reorder before it "
              f"has evidence")
    if not ok:
        fails.append("ordered on no evidence")
    return fails


if __name__ == "__main__":
    f = selftest()
    print("\nsurrogate selftest:", "PASS" if not f else f"FAIL {f}")
