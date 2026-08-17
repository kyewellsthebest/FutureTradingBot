"""Destination, trigger, invalidation -- a strategy discovered, not configured.

THE SEARCH MODEL THIS IMPLEMENTS, in the user's own framing:

  1  find a recurring place price GOES TO                 the destination
  2  find where it BEGINS going there                     the trigger
  3  when it fails, find the point you KNOW it failed      the invalidation

Everything else in this searcher enumerates a grid: pick a bucket, pick
a direction, pick a hold, pick a stop, score it. Even the shape family
does that -- the exits come from a list somebody wrote down. This module
does the opposite. It measures where price actually travels, finds what
precedes those journeys, and then MEASURES the level at which the
journey is over rather than choosing one.

  the destination is measured, not chosen
  the trigger is measured, not chosen
  the stop is measured, not chosen

WHY DESTINATIONS ARE LEVELS AND NOT DISTANCES. "Price goes up 20 points"
is a distance and it recurs trivially -- price goes up 20 points all the
time, in both directions, and predicting it is predicting volatility
rather than direction. A DESTINATION is a specific place other people
are also looking at: yesterday's high, the overnight low, the session
open, a round number, the prior swing. Those recur because participants
put orders there, and orders are why price stops travelling. A level
with resting interest is a reason; a distance is a coincidence.

THE MEASUREMENT IS A RACE, NOT A RETURN. From each bar, the question is
not "what is the return in 30 minutes" but "does price touch the
destination BEFORE it touches the invalidation". That is a first-passage
problem and it is what a bracketed trade actually is. Measuring it
directly avoids the whole question of what horizon to pick, because the
horizon is however long the race takes.

    P(reach | trigger)  vs  P(reach | anything)   = the LIFT

Base rate is everything here. A destination reached 70% of the time from
any bar is not a finding -- it is a destination that is close. Only the
lift over the unconditional base rate is evidence, and the base rate is
computed on the same tape, the same horizon and the same bars.

WHAT MAKES THE INVALIDATION LEARNED. For a given trigger and
destination, adverse excursion is swept: at each candidate distance
against the position, what share of eventual winners had already gone
that far offside? A stop tighter than that is cutting trades that were
going to work. The chosen invalidation is the tightest distance that
still keeps most eventual winners -- the smallest risk that does not buy
its tightness with lost wins. Nobody picks 1.5 ATR because it sounds
right; the number comes out of the distribution.

LOOK-AHEAD, which would be fatal here and is easy to introduce. Every
level is built from data STRICTLY BEFORE the bar it is used on: prior
session values are shifted by a whole session, swings are confirmed only
after their lookback has passed, and the round-number grid is a function
of price alone. `level_selftest` checks each series against its own
timestamps.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ------------------------------------------------------------- levels
def build_levels(d):
    """Recurring reference levels, each known strictly before its bar.

    Returns {name: array}. NaN where the level is not yet defined --
    a level that does not exist yet must not silently become zero.
    """
    idx = d.index
    c = d["close"]
    hi = d["high"] if "high" in d.columns else c
    lo = d["low"] if "low" in d.columns else c
    day = pd.Series(idx.normalize(), index=idx)
    out = {}

    # prior session high, low, close -- shifted a whole session, so the
    # value in force today is yesterday's completed statistic
    g = pd.DataFrame({"d": day.values, "h": hi.values, "l": lo.values,
                      "c": c.values}, index=idx)
    daily = g.groupby("d").agg(h=("h", "max"), l=("l", "min"),
                               c=("c", "last"))
    prev = daily.shift(1)
    out["prior_high"] = prev["h"].reindex(g["d"]).values
    out["prior_low"] = prev["l"].reindex(g["d"]).values
    out["prior_close"] = prev["c"].reindex(g["d"]).values

    # today's opening price, known from the first bar onward
    first = g.groupby("d")["c"].transform("first")
    out["session_open"] = first.values

    # running session extremes SO FAR -- expanding within the day, and
    # shifted one bar so the current bar cannot define its own level
    out["day_high_so_far"] = g.groupby("d")["h"].cummax().shift(1).values
    out["day_low_so_far"] = g.groupby("d")["l"].cummin().shift(1).values

    # confirmed swing points: an extreme that has survived w bars on both
    # sides is only KNOWN w bars later, so it is shifted by w
    for w in (20, 60):
        out[f"swing_high_{w}"] = hi.rolling(w).max().shift(w).values
        out[f"swing_low_{w}"] = lo.rolling(w).min().shift(w).values

    # round numbers: the nearest grid line above and below. Purely a
    # function of current price, so no timing question arises.
    scale = float(np.nanmedian(np.abs(np.diff(c.values))))
    for mult in (10, 50):
        step = max(round(scale * mult, 10), 1e-9)
        out[f"round_{mult}_up"] = (np.ceil(c.values / step) * step)
        out[f"round_{mult}_dn"] = (np.floor(c.values / step) * step)
    return out


DESTINATIONS = list(build_levels.__doc__ and [])  # filled at runtime


# --------------------------------------------------------- first passage
def race(close, high, low, start, dest_px, inval_px, side, max_bars):
    """Does price reach the destination before the invalidation?

    Returns (outcome, bars) with outcome 1=destination, -1=invalidation,
    0=neither within max_bars.

    A bar that touches BOTH gets the INVALIDATION, for the same reason
    the bracket engine gives a tied bar to the stop: OHLC cannot order
    events inside a bar, and resolving the ambiguity in your own favour
    is how a backtest invents an edge.
    """
    n = len(start)
    c, h, lo = (np.asarray(x, dtype=float) for x in (close, high, low))
    out = np.zeros(n, dtype=np.int8)
    bars = np.full(n, max_bars, dtype=np.int32)
    active = np.ones(n, dtype=bool)
    last = len(c) - 1
    s = np.asarray(side, dtype=float)
    for k in range(1, max_bars + 1):
        j = start + k
        valid = active & (j <= last)
        if not valid.any():
            break
        jj = np.where(valid, j, 0)
        bh, bl = h[jj], lo[jj]
        longs, shorts = valid & (s > 0), valid & (s < 0)
        hit_d = np.zeros(n, dtype=bool)
        hit_i = np.zeros(n, dtype=bool)
        hit_d[longs] = bh[longs] >= dest_px[longs]
        hit_i[longs] = bl[longs] <= inval_px[longs]
        hit_d[shorts] = bl[shorts] <= dest_px[shorts]
        hit_i[shorts] = bh[shorts] >= inval_px[shorts]
        hit_d = hit_d & ~hit_i                      # tie -> invalidation
        for mask, val in ((hit_i, -1), (hit_d, 1)):
            if mask.any():
                out[mask] = val
                bars[mask] = k
                active[mask] = False
    return out, bars


def mae(close, high, low, start, side, max_bars, unit):
    """Maximum adverse excursion, in volatility units, per trade.

    How far offside each trade went before it finished. This is the raw
    material for a LEARNED stop: the invalidation should sit beyond
    where most eventual winners travelled, not at a number chosen for
    being a round multiple.
    """
    n = len(start)
    c, h, lo = (np.asarray(x, dtype=float) for x in (close, high, low))
    s = np.asarray(side, dtype=float)
    entry = c[start]
    worst = np.zeros(n)
    last = len(c) - 1
    for k in range(1, max_bars + 1):
        j = np.minimum(start + k, last)
        adverse = np.where(s > 0, entry - lo[j], h[j] - entry)
        worst = np.maximum(worst, adverse)
    return worst / np.maximum(unit[start], 1e-12)


def learn_invalidation(mae_units, outcome, keep=0.80,
                       grid=(0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0)):
    """The tightest stop that still keeps `keep` of the eventual winners.

    Swept, not chosen. For each candidate distance, what share of the
    trades that DID reach the destination had already gone that far
    offside first? A stop inside that distance would have cut them.

    Returns the distance and the share of winners it preserves, or None
    when there are too few winners to say anything -- which is the
    honest answer far more often than a number is.
    """
    win = mae_units[outcome == 1]
    if len(win) < 30:
        return None
    for gpt in grid:
        kept = float(np.mean(win <= gpt))
        if kept >= keep:
            return {"stop_units": gpt, "keeps_winners": round(kept, 3),
                    "n_winners": int(len(win)),
                    "why": (f"{kept:.0%} of the trades that reached the "
                            f"destination never went more than {gpt} "
                            f"volatility units offside first. A stop "
                            f"tighter than that cuts trades that were "
                            f"going to work.")}
    return {"stop_units": grid[-1], "keeps_winners":
            round(float(np.mean(win <= grid[-1])), 3),
            "n_winners": int(len(win)),
            "why": (f"even {grid[-1]} units only holds "
                    f"{np.mean(win <= grid[-1]):.0%} of winners -- the "
                    f"journey to this destination is too rough for a "
                    f"stop to sit outside it")}


# ------------------------------------------------------------- the study
def study(d, unit, level_name, levels, side, trigger_mask, max_bars,
          inval_units=3.0):
    """Base rate, conditional rate, and lift for one destination.

    The lift is the whole point. A destination reached 70% of the time
    from ANY bar is not a discovery, it is a destination that is close.
    Only the excess over the base rate on the same tape, same horizon
    and same bars is evidence.
    """
    c = d["close"].values
    h = d["high"].values if "high" in d.columns else c
    lo = d["low"].values if "low" in d.columns else c
    dest = np.asarray(levels[level_name], dtype=float)

    ok = np.isfinite(dest) & np.isfinite(unit) & (unit > 0)
    # the destination must be AHEAD of price in the traded direction,
    # otherwise "reaching" it is already true and means nothing
    ahead = np.where(side > 0, dest > c, dest < c)
    base_sel = np.flatnonzero(ok & ahead)
    base_sel = base_sel[base_sel + max_bars < len(c)]
    if len(base_sel) < 200:
        return None

    def rate(sel):
        if len(sel) < 60:
            return None
        s = np.full(len(sel), float(side))
        inval = c[sel] - s * inval_units * unit[sel]
        o, _ = race(c, h, lo, sel, dest[sel], inval, s, max_bars)
        return o

    o_base = rate(base_sel)
    if o_base is None:
        return None
    trig_sel = np.flatnonzero(ok & ahead & np.asarray(trigger_mask))
    trig_sel = trig_sel[trig_sel + max_bars < len(c)]
    o_trig = rate(trig_sel)
    if o_trig is None:
        return None

    p_base = float(np.mean(o_base == 1))
    p_trig = float(np.mean(o_trig == 1))
    s = np.full(len(trig_sel), float(side))
    m = mae(c, h, lo, trig_sel, s, max_bars, unit)
    inv = learn_invalidation(m, o_trig)
    # distance to the destination, in volatility units -- the reward
    dist = np.abs(dest[trig_sel] - c[trig_sel]) / unit[trig_sel]
    return {
        "level": level_name, "side": int(side),
        "n_base": int(len(base_sel)), "n_trigger": int(len(trig_sel)),
        "p_base": round(p_base, 4), "p_trigger": round(p_trig, 4),
        "lift": round(p_trig - p_base, 4),
        "reward_units": round(float(np.median(dist)), 2),
        "invalidation": inv,
    }


def expected_value(res, cost_units):
    """Is the journey worth taking, once the stop is where it belongs?

    Reward is the median distance to the destination; risk is the
    LEARNED invalidation. Both in volatility units, so cost has to be
    converted into the same units by the caller. Without that
    conversion this is a probability with no economics attached, which
    is how a 96%-win-rate artifact gets mistaken for a strategy.
    """
    if not res or not res.get("invalidation"):
        return None
    p = res["p_trigger"]
    r = res["reward_units"]
    s = res["invalidation"]["stop_units"]
    ev = p * r - (1 - p) * s - cost_units
    return {"ev_units": round(ev, 4), "reward": r, "risk": s,
            "p": p, "cost_units": round(cost_units, 4),
            "rr": round(r / s, 2) if s else None}
