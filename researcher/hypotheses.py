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


def expand(footprints, cap=4000):
    """Footprints -> concrete, testable hypotheses."""
    hyps = []
    for f in footprints:
        fam = f"{f['dim']}/{f['metric']}"
        for d in DIRECTIONS:
            for h in HOLDS_S:
                for c in CONDS:
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


def describe(h) -> str:
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
