"""Two years of dealer gamma, rebuilt from option prices. No subscription.

THE POINT. The plan that serves greeks, implied vol and open interest lapses on
2026-08-16 and is not being renewed until there is a profitable strategy. Six
days of daily snapshots proves nothing, so the useful move is to OWN the
history rather than rent it.

Greeks are not data, they are arithmetic. Given a price, a strike, an expiry
and a spot, implied volatility falls out of inverting Black-Scholes and gamma
falls out of differentiating it. Polygon's `greeks` field is a convenience.
What cannot be recomputed is the option PRICE, and that is in the OPRA daily
aggregates at 4.2 MB a day -- two years for about two gigabytes, one workflow
run rather than a monthly bill.

WHAT IS GENUINELY LOST, stated plainly rather than buried. Open interest is not
in the aggregates, so this weights gamma by VOLUME instead. Those are different
measures: open interest is the position that exists, volume is the position
being traded today. Volume weighting leans heavily toward short-dated and
0DTE activity, which is where hedging pressure is most violent but also least
persistent.

That is exactly why the six remaining days matter. While the plan lives, the
snapshot job records real open interest daily. Those days become a CALIBRATION
SET: run both measures over the same sessions, and the correlation between them
is the error bar on every historical value this file produces. A proxy with a
measured error is usable; a proxy assumed to be fine is not.

SPOT WITHOUT AN INDEX FEED. The at-the-money strike is where a call and a put
cost the same -- that is put-call parity, and it reads the spot straight off
the chain. No separate index subscription, and it cannot go stale relative to
the options because it comes from the same rows.
"""
import gzip
import io
import math
import os
import re
import sys

import numpy as np
import pandas as pd

AGG_COLS = ["ticker", "volume", "open", "close", "high", "low",
            "window_start", "transactions"]
# O:SPXW260814C05800000 -> root SPXW, expiry 260814, C, strike 5800.000
OCC = re.compile(r"^O:([A-Z]+)(\d{6})([CP])(\d{8})$")
ROOTS = tuple(os.environ.get("ROOTS", "SPX,SPXW,NDX,NDXP").split(","))
R = 0.04                       # short rate; gamma is barely sensitive to it


def parse(t):
    m = OCC.match(t)
    if not m:
        return None
    root, ymd, cp, strike = m.groups()
    return root, ymd, cp, int(strike) / 1000.0


def bs_gamma(S, K, T, sigma):
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    d1 = (math.log(S / K) + (R + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    return math.exp(-0.5 * d1 * d1) / (S * sigma * math.sqrt(2 * math.pi * T))


def bs_price(S, K, T, sigma, cp):
    if T <= 0 or sigma <= 0:
        return max(0.0, (S - K) if cp == "C" else (K - S))
    d1 = (math.log(S / K) + (R + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    N = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))          # noqa: E731
    if cp == "C":
        return S * N(d1) - K * math.exp(-R * T) * N(d2)
    return K * math.exp(-R * T) * N(-d2) - S * N(-d1)


def implied_vol(px, S, K, T, cp):
    """Bisection. Slower than Newton and it cannot diverge, which matters when
    a few thousand of the inputs are stale or crossed."""
    if px <= 0 or T <= 0:
        return None
    lo, hi = 1e-4, 5.0
    if bs_price(S, K, T, hi, cp) < px:
        return None
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if bs_price(S, K, T, mid, cp) < px:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def spot_from_parity(df):
    """Where a call and a put cost the same, the strike is the forward. Reads
    spot off the chain itself, so it can never be stale relative to it."""
    near = df[df.T_yrs.between(0.01, 0.15)]
    if near.empty:
        near = df
    c = near[near.cp == "C"].set_index(["expiry", "strike"]).close
    p = near[near.cp == "P"].set_index(["expiry", "strike"]).close
    both = c.to_frame("c").join(p.to_frame("p"), how="inner").dropna()
    if both.empty:
        return None
    both["d"] = (both.c - both.p).abs()
    return float(both.d.idxmin()[1])


def one_day(raw, day):
    df = pd.read_csv(io.BytesIO(raw), names=AGG_COLS)
    pr = df.ticker.map(parse)
    df = df[pr.notna()].copy()
    if df.empty:
        return None
    df[["root", "ymd", "cp", "strike"]] = pd.DataFrame(
        pr[pr.notna()].tolist(), index=df.index)
    df = df[df.root.isin(ROOTS)]
    if df.empty:
        return None
    d0 = pd.Timestamp(day)
    exp = pd.to_datetime("20" + df.ymd, format="%Y%m%d", errors="coerce")
    df["T_yrs"] = (exp - d0).dt.days.clip(lower=0) / 365.0
    df["expiry"] = df.ymd
    df = df[(df.close > 0) & df.T_yrs.notna()]

    out = {}
    df["fam"] = np.where(df.root.str.startswith("SPX"), "SPX", "NDX")
    for fam, g in df.groupby("fam"):
        S = spot_from_parity(g)
        if not S:
            continue
        tot = 0.0
        for _, r in g.iterrows():
            iv = implied_vol(float(r.close), S, float(r.strike),
                             float(r.T_yrs), r.cp)
            if not iv:
                continue
            gm = bs_gamma(S, float(r.strike), float(r.T_yrs), iv)
            # volume-weighted, because open interest is not in the aggregates.
            # calls +, puts - is the same dealer convention the snapshot uses,
            # so the two series stay comparable during calibration.
            sign = 1.0 if r.cp == "C" else -1.0
            tot += sign * gm * float(r.volume) * 100 * S * S * 0.01
        out[fam] = dict(day=day, fam=fam, spot=S, gex_vol=tot, n=len(g))
    return list(out.values())


def main(outdir):
    os.makedirs(outdir, exist_ok=True)
    rows = []
    for line in sys.stdin:
        path = line.strip()
        if not path or not os.path.exists(path):
            continue
        day = os.path.basename(path).replace(".csv.gz", "")
        try:
            with gzip.open(path, "rb") as f:
                res = one_day(f.read(), day)
        except Exception as e:                                   # noqa: BLE001
            print(f"{day}: {type(e).__name__}: {e}", flush=True)
            continue
        if res:
            rows += res
            for r in res:
                print(f"{day} {r['fam']:4s} spot {r['spot']:>9,.0f} "
                      f"gex_vol {r['gex_vol']/1e9:+8.2f} bn  n={r['n']:,}",
                      flush=True)
    if not rows:
        print("nothing produced")
        return
    d = pd.DataFrame(rows)
    p = os.path.join(outdir, "gex_history.parquet")
    if os.path.exists(p):
        d = pd.concat([pd.read_parquet(p), d]).drop_duplicates(["day", "fam"])
    d.sort_values(["fam", "day"]).to_parquet(p, compression="zstd")
    print(f"\n{len(d):,} rows -> {p}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/gex")
