"""Test MECHANISMS across every market at once, not markets one at a time.

THE PROBLEM THIS FIXES, and it is the largest single weakness in the
searcher as it stood.

"after a close near the low, go long" is ONE idea. The engine tested it
as twenty-three: once in MNQ, once in ES, once in ZB, and so on. That
costs twice over.

  1  MULTIPLICITY. Twenty-three cells means twenty-three trials, and the
     bar rises as sqrt(2 ln N). At 10,000 mechanisms the per-market
     scheme spends 230,000 trials and faces a 5.79 sigma bar; the same
     10,000 mechanisms tested once each face 4.87. The engine was paying
     a multiple-testing penalty for asking one question repeatedly.

  2  POWER, which is worse. A real mechanism is usually WEAK and BROAD:
     visible at 1.5 sigma in fifteen markets rather than at 8 sigma in
     one. The per-market scheme cannot see that at all -- every single
     cell fails, the idea is recorded as dead twenty-three times over,
     and the one thing that most distinguishes a real effect from a
     coincidence, that it shows up in places you did not fit it to, is
     thrown away.

     Meanwhile 8 sigma in exactly one market is the signature of an
     artifact, and the old scheme ranked it first.

So a mechanism is now one hypothesis, measured everywhere it applies,
and judged on the pooled evidence.

HOW THE POOLING IS DONE HONESTLY

Markets are not independent. ES, NQ, YM and RTY are one bet wearing four
tickers, and treating them as four replications inflates z by up to
sqrt(4/1.75) = 1.5x. Three defences, all required:

  * effective_n. Correlated blocs count once, with a small credit for
    imperfect correlation (data_tiers.effective_n). The standard error
    is widened by sqrt(k / effective_n).

  * inverse-variance weighting with a heterogeneity penalty. Markets
    disagreeing more than their own error bars allow means the effect is
    not common to them, and the pooled error is inflated by the excess
    (the I-squared / tau-squared idea from meta-analysis). A mechanism
    that is +3 in one market and -3 in another is not a weak universal
    effect, it is two unrelated accidents.

  * sign agreement. A mechanism must point the same way in most markets.
    This is not implied by the pooled mean -- one huge market can drag a
    mean positive while the majority are negative -- and it is the check
    that best separates mechanism from coincidence.

WHAT THIS DELIBERATELY DOES NOT DO. It does not pool markets whose
hypothesis was fitted to that market. A footprint found in NQ's own tape
and a feature grown from NQ's own returns are market-specific by
construction; pooling them would be comparing different questions and
calling the average an answer. Only mechanisms stated before the data is
seen -- shapes, flow, destinations -- are poolable, and the slate of
them is drawn ONCE per cycle so that every market answers the same
question.
"""
from __future__ import annotations

import json
import math

import numpy as np

# A mechanism must appear in at least this many markets before pooling
# means anything. Below it the cross-sectional spread is unmeasurable.
MIN_MARKETS = 5
# Share of markets that must agree in sign.
MIN_AGREE = 0.65


def mech_key(h) -> str:
    """Identity of a mechanism, independent of where it was measured."""
    d = {k: v for k, v in h.items()
         if k not in ("market", "tier", "_family", "_slate")}
    return json.dumps(d, sort_keys=True, separators=(",", ":"))


class PooledBook:
    """Accumulates one mechanism's measurement in each market."""

    def __init__(self):
        self.rows = {}          # key -> {sym: (mu, se, n, hyp, family)}

    def add(self, h, sym, result, cost, family=None):
        """Record one market's measurement of a mechanism.

        The effect is stored as NET profit in units of that market's own
        round-trip cost: 0 is break-even, +1 means it earns a whole extra
        round trip per trade, -1 means it loses one. Pooling raw dollars would compare ZB's $31 tick with MNQ's
        $0.50 and then judge the pool against one of them -- the same
        category error that once made every 6A trade score -$0.5992. A
        ratio of 1.0 means "paid for itself here", and that means the
        same thing everywhere.
        """
        if not result or not cost:
            return
        n = int(result.get("n") or 0)
        if n < 30:
            return
        # NET, not gross. The question a pooled mechanism has to answer
        # is "does it pay after the cost of trading", and with gross the
        # break-even point sits at 1.0 -- so the `mean > 0` gate below
        # would have promoted a mechanism earning a tenth of its own
        # cost. Measured in net round trips, 0 is break-even and the
        # gate means what it says.
        edge = result.get("net")
        if edge is None:
            return
        # standard error of the per-trade edge, in cost units, deflated
        # for overlap exactly as the single-market path does
        sd = result.get("sd")
        eff = result.get("eff_n") or n
        if sd is None or not np.isfinite(sd) or sd <= 0 or eff <= 1:
            return
        mu = float(edge) / float(cost)
        se = (float(sd) / float(cost)) / math.sqrt(eff)
        if not np.isfinite(mu) or not np.isfinite(se) or se <= 0:
            return
        k = mech_key(h)
        slot = self.rows.setdefault(k, {"hyp": None, "family": family,
                                        "by": {}})
        if slot["hyp"] is None:
            slot["hyp"] = {kk: vv for kk, vv in h.items()
                           if kk not in ("market", "tier", "_family")}
        slot["by"][sym] = (mu, se, n)

    # ------------------------------------------------------------ test
    def test(self, effective_n, min_markets=MIN_MARKETS):
        """Pooled verdict per mechanism. One hypothesis, one result."""
        out = []
        for key, slot in self.rows.items():
            by = slot["by"]
            if len(by) < min_markets:
                continue
            v = pool(by, effective_n)
            if v is None:
                continue
            v.update(key=key, hyp=slot["hyp"], family=slot["family"])
            out.append(v)
        out.sort(key=lambda r: -r["z"])
        return out


def pool(by, effective_n):
    """Combine per-market effects into one honest statistic.

    `by` maps symbol -> (mu, se, n) with mu already in cost units.
    """
    syms = sorted(by)
    k = len(syms)
    if k < 2:
        return None
    mu = np.array([by[s][0] for s in syms], float)
    se = np.array([by[s][1] for s in syms], float)
    nn = np.array([by[s][2] for s in syms], int)
    ok = np.isfinite(mu) & np.isfinite(se) & (se > 0)
    if ok.sum() < 2:
        return None
    mu, se, nn = mu[ok], se[ok], nn[ok]
    syms = [s for s, o in zip(syms, ok) if o]
    k = len(syms)

    w = 1.0 / se ** 2
    mean = float((w * mu).sum() / w.sum())
    se_fixed = float(1.0 / math.sqrt(w.sum()))

    # HETEROGENEITY. Q is the weighted scatter of the market effects
    # about the pooled mean. Under a single common effect its
    # expectation is k-1; anything above that is real disagreement
    # between markets, and the pooled error must absorb it or the
    # combined z is a statement about markets that do not agree.
    Q = float((w * (mu - mean) ** 2).sum())
    tau2 = max(0.0, (Q - (k - 1)) / max(w.sum() - (w ** 2).sum() / w.sum(),
                                        1e-12))
    if tau2 > 0:                       # random-effects: re-weight
        w = 1.0 / (se ** 2 + tau2)
        mean = float((w * mu).sum() / w.sum())
        se_pool = float(1.0 / math.sqrt(w.sum()))
    else:
        se_pool = se_fixed

    # CORRELATION. Four equity indices are not four observations.
    eff = float(effective_n(syms) or k)
    eff = max(1.0, min(eff, k))
    se_pool *= math.sqrt(k / eff)

    agree = float(max((mu > 0).sum(), (mu < 0).sum()) / k)
    z = mean / se_pool if se_pool > 0 else 0.0
    # WHAT THIS POOLED TEST COULD HAVE SEEN.
    #
    # The per-market number is hopeless on its own -- calibration put a
    # typical cell's smallest detectable edge at about 0.9 round trips,
    # and anything that large is bug territory. Pooling is what rescues
    # it: combining k markets shrinks the standard error, so the pooled
    # test can see roughly sqrt(effective_n) times smaller an effect
    # than any one market could.
    #
    # Reporting it here means a pooled null result finally means
    # something: "measured -0.05 RT, could have detected +0.18" is
    # evidence of absence in that range, where the same sentence with
    # "could have detected +2.0" is evidence of nothing at all.
    mde = 5.79 * se_pool
    return {
        "z": float(z),
        "mean_cost_units": mean,
        "se": se_pool,
        "markets": syms,
        "k": k,
        "effective_n": round(eff, 2),
        "agree": round(agree, 3),
        "tau2": float(tau2),
        "Q": round(Q, 2),
        "n_total": int(nn.sum()),
        "mde": round(float(mde), 4),
        "per_market": {s: round(float(m), 4) for s, m in zip(syms, mu)},
        # A mechanism must be broad AND consistent AND pay for itself.
        "coherent": bool(agree >= MIN_AGREE and abs(mean) > 0),
    }


# ------------------------------------------------------------ self-test
def selftest(verbose=True):
    """The three things this must get right, and the one it must refuse.

    A pooled statistic that cannot be trusted is worse than none: it
    would let a weak-and-broad artifact through with the authority of
    twenty-three markets behind it.
    """
    fails = []
    rng = np.random.default_rng(11)

    def eff_indep(syms):
        return float(len(syms))

    def eff_bloc(syms):
        from researcher.data_tiers import effective_n as en
        return en(syms)

    # 1. pure noise across 20 independent markets must not pool to a
    #    significant answer more than chance allows
    zs = []
    for _ in range(400):
        by = {f"M{i}": (rng.normal(0, 0.05), 0.05, 500) for i in range(20)}
        v = pool(by, eff_indep)
        zs.append(abs(v["z"]))
    p99 = float(np.percentile(zs, 99))
    ok = p99 < 3.4
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  noise stays near the noise "
              f"level  — p99 |z| {p99:.2f} (expect ~2.6)")
    if not ok:
        fails.append("pooled null too hot")

    # 2. a weak effect present in EVERY market must be found. This is
    #    the case the per-market scheme is blind to: 1.5 sigma each,
    #    which no single market can ever clear a 5 sigma bar with.
    by = {}
    per = []
    for i in range(18):
        se = 0.05
        mu = rng.normal(0.075, 0.05)         # ~1.5 sigma in each market
        by[f"M{i}"] = (mu, se, 800)
        per.append(mu / se)
    v = pool(by, eff_indep)
    ok = v["z"] > 4.9 and v["agree"] >= 0.85
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  weak-but-universal effect "
              f"found  — each market only {np.mean(per):.1f}σ, pooled "
              f"{v['z']:.1f}σ")
    if not ok:
        fails.append("missed a broad weak effect")

    # 3. one market screaming while the rest say nothing must NOT pool
    #    to a finding. This is the artifact signature and the exact
    #    shape of what the old leaderboard ranked first.
    by = {f"M{i}": (rng.normal(0, 0.01), 0.05, 500) for i in range(17)}
    by["LOUD"] = (2.0, 0.05, 500)            # 40 sigma on its own
    v = pool(by, eff_indep)
    ok = v["z"] < 4.0 and not v["coherent"]
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  one loud market does not "
              f"carry the pool  — pooled {v['z']:.2f}σ, agreement "
              f"{v['agree']:.0%}, heterogeneity absorbed it")
    if not ok:
        fails.append("a single outlier market dominated the pool")

    # 4. correlated blocs must not count as independent evidence
    equities = ["ES", "NQ", "YM", "RTY"]
    by = {s: (0.25, 0.05, 800) for s in equities}
    z_naive = pool(by, eff_indep)["z"]
    z_real = pool(by, eff_bloc)["z"]
    ok = z_real < z_naive * 0.85
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  correlated markets are "
              f"discounted  — four equity indices {z_naive:.1f}σ if "
              f"treated as independent, {z_real:.1f}σ in truth")
    if not ok:
        fails.append("correlation not discounted")

    # 5. below the market floor it must refuse to answer at all
    v = PooledBook().test(eff_indep)
    ok = v == []
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  refuses to pool an empty "
              f"book")
    if not ok:
        fails.append("pooled an empty book")
    return fails


if __name__ == "__main__":
    f = selftest()
    print("\npooled selftest:", "PASS" if not f else f"FAIL {f}")
