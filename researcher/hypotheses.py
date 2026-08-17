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


def from_flow(available, hold_mult=1.0, cap=600):
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
    holds = [max(int(h * hold_mult), 1) for h in FLOW_HOLDS_S]
    for m in FLOW:
        if not all(c in available for c in m["cols"]):
            continue
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


def describe(h) -> str:
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
