"""Dealer gamma from the raw option chain. The one dataset the measurements back.

WHY THIS AND NOT MORE PRICE MINING. Four independent measurements now say the
sub-hour window is closed: the zero-cost ceiling of $97/week per contract, the
frequency-versus-edge trade-off, the pooled-quarters test, and the latency
decay curve. Every one of them also showed the same thing pointing the other
way -- dollars per trade GREW with holding time. Dealer gamma is the only
obtainable dataset that operates on that timescale.

WHAT IT IS, plainly. Market makers are on the other side of every option the
public buys. To stay hedged they must trade the underlying as it moves, and
which way they trade depends on their net gamma:

  dealers LONG gamma   ->  they sell rallies and buy dips to stay flat.
                           That SUPPRESSES the range. Mean reversion works,
                           breakouts fail.
  dealers SHORT gamma  ->  they buy rallies and sell dips. That AMPLIFIES the
                           range. Trends run, fading gets you hurt.

So this is not another directional signal. It is a REGIME classifier, and it
says which kind of strategy should be switched on today -- which is a question
none of the 26 billion configurations searched so far could even ask.

TWO OUTPUTS THAT ARE DIRECTLY TRADEABLE, and both answer things the user has
asked before:

  THE FLIP LEVEL -- the spot price where total gamma crosses zero. Above it
  dealers dampen, below it they amplify. It is the single most useful number
  on the page and it moves slowly enough to act on.

  GAMMA WALLS -- strikes with enormous gamma act as magnets and then as
  resistance, because hedging flow concentrates there. That is a structural
  target derived from real positioning rather than drawn on a chart, which is
  exactly what "where does price actually go" was asking for.

HONEST LIMITS, stated up front.

  OPEN INTEREST IS YESTERDAY'S. OI settles overnight, so intraday gamma is
  computed against a stale position count. Everyone in this field has that
  problem; it matters most on heavy 0DTE days.

  THE DEALER SIGN IS AN ASSUMPTION. The standard convention -- dealers long
  calls, short puts -- is a convention, not an observation. It is roughly right
  for index options and wrong often enough to matter.

  NDX IS A PROXY FOR NQ. Options on NQ futures live at CME and are not in
  these flat files. NDX index options are the closest available instrument and
  they track the same underlying, but they are not the same book.
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd
import requests

KEY = os.environ.get("POLYGON_API", "")
OUT = os.environ.get("OUT_DIR", "data/gex")
ROOTS = os.environ.get("ROOTS", "I:NDX,I:SPX").split(",")
CONTRACT_MULT = 100


def chain(root):
    """Every live contract with greeks, IV and open interest."""
    url = "https://api.polygon.io/v3/snapshot/options/" + root
    rows, cur, page = [], None, 0
    while page < 60:
        p = {"apiKey": KEY, "limit": 250}
        if cur:
            p["cursor"] = cur
        r = requests.get(url, params=p, timeout=60)
        if r.status_code != 200:
            print(f"  {root}: HTTP {r.status_code} {r.text[:160]}")
            break
        j = r.json()
        for c in j.get("results", []):
            d = c.get("details", {})
            g = c.get("greeks", {})
            rows.append(dict(
                strike=d.get("strike_price"), expiry=d.get("expiration_date"),
                kind=d.get("contract_type"),
                oi=c.get("open_interest"), iv=c.get("implied_volatility"),
                gamma=g.get("gamma"), delta=g.get("delta"),
                vol=(c.get("day") or {}).get("volume"),
                spot=(c.get("underlying_asset") or {}).get("price")))
        nxt = j.get("next_url")
        if not nxt:
            break
        cur = nxt.split("cursor=")[-1]
        page += 1
        time.sleep(0.05)
    return pd.DataFrame(rows)


def gex(df, spot):
    """Dollar gamma per 1% move, signed by the dealer convention.

    Calls counted positive and puts negative is the standard assumption that
    dealers are long the calls the public sells and short the puts the public
    buys. It is a convention, not a measurement -- the sign is the weakest link
    in every gamma model including the commercial ones.
    """
    d = df.dropna(subset=["gamma", "oi", "strike"]).copy()
    d = d[(d.oi > 0) & (d.gamma > 0)]
    sign = np.where(d.kind == "call", 1.0, -1.0)
    d["gex"] = sign * d.gamma * d.oi * CONTRACT_MULT * spot * spot * 0.01
    return d


def flip_level(d, spot):
    """Where total gamma crosses zero: dampening above, amplifying below."""
    lo, hi = spot * 0.90, spot * 1.10
    grid = np.linspace(lo, hi, 220)
    tot = []
    for s in grid:
        sign = np.where(d.kind == "call", 1.0, -1.0)
        tot.append(float((sign * d.gamma * d.oi * CONTRACT_MULT * s * s * 0.01).sum()))
    tot = np.array(tot)
    sc = np.flatnonzero(np.diff(np.sign(tot)) != 0)
    if len(sc) == 0:
        return None, grid, tot
    i = sc[int(np.argmin(np.abs(grid[sc] - spot)))]
    return float(grid[i]), grid, tot


def main():
    if not KEY:
        sys.exit("POLYGON_API not set")
    os.makedirs(OUT, exist_ok=True)
    day = time.strftime("%Y-%m-%d")
    L = [f"## {day}", ""]
    for root in ROOTS:
        df = chain(root)
        if df.empty:
            print(f"{root}: nothing returned")
            continue
        spot = float(pd.to_numeric(df.spot, errors="coerce").dropna().median())
        d = gex(df, spot)
        if d.empty:
            print(f"{root}: no gamma/OI rows")
            continue
        total = float(d.gex.sum())
        flip, grid, curve = flip_level(d, spot)
        walls = (d.groupby("strike").gex.sum().abs().sort_values(ascending=False)
                 .head(5).index.tolist())
        near = sorted(walls, key=lambda s: abs(s - spot))[:3]

        df.to_parquet(f"{OUT}/{root.replace(':','_')}_{day}_chain.parquet",
                      compression="zstd")
        L += [f"### {root} — spot {spot:,.0f}", "",
              f"- **net dealer gamma** ${total/1e9:+.2f} bn per 1% move — "
              f"**{'LONG: range suppressed, fade the extremes' if total > 0 else 'SHORT: range amplified, trends run'}**",
              f"- **flip level** {('%,.0f' % flip) if flip else 'none in ±10%'}"
              + (f"  (spot is {'above — dampening' if flip and spot > flip else 'below — amplifying'})" if flip else ""),
              f"- **gamma walls** nearest spot: "
              + ", ".join(f"{w:,.0f}" for w in near),
              f"- {len(d):,} contracts with live gamma and open interest", ""]
        print("\n".join(L[-6:]))

    rp = "research/GEX.md"
    head = ("# Dealer gamma — the regime switch\n\n"
            "Not another directional signal. Dealers long gamma sell rallies "
            "and buy dips, which suppresses the range; dealers short gamma do "
            "the opposite and amplify it. So this says which *kind* of strategy "
            "should be on today — a question none of the 26 billion "
            "configurations searched so far could ask.\n\n"
            "Caveats that matter: open interest is yesterday's, the dealer sign "
            "convention is an assumption rather than an observation, and NDX is "
            "a proxy for NQ because options on NQ futures live at CME and are "
            "not in these files.\n")
    prev = open(rp).read() if os.path.exists(rp) else head
    if not prev.startswith("# Dealer gamma"):
        prev = head
    os.makedirs("research", exist_ok=True)
    open(rp, "w").write(prev.rstrip() + "\n\n" + "\n".join(L) + "\n")
    print("wrote", rp)


if __name__ == "__main__":
    main()
