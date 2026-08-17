"""Calendar spreads: do they fix the capital problem, or just move it?

The constraint that killed every strategy in this project is not signal
and not cost -- it is that ONE micro contract carries $7,160 of annual
volatility against a $4,000 account, 179%, so the smallest tradeable
position is about twelve times larger than a professionally sized one.

A calendar spread -- long the front contract, short the back -- is the
only structure that attacks that directly:

  MARGIN      exchanges grant spread credit; often 80-90% lower
  VOLATILITY  the shared market risk cancels, leaving only the
              relationship between two delivery dates
  MECHANISM   storage cost, seasonal demand, contango/backwardation and,
              most usefully, FORCED ROLL FLOW -- commodity ETFs publish
              their roll schedules and must trade them regardless of
              price. That is a counterparty with a mandate.

THE ARITHMETIC THAT RUNS AGAINST IT, stated first so the result cannot
be spun. A spread has TWO legs, so cost roughly doubles. If volatility
falls 10x while cost doubles, cost per unit of volatility gets 20x
WORSE. Trading a spread is not free risk reduction -- you can always cut
risk by trading smaller, and that helps nobody.

So the spread only wins if the IC available on it is much larger than
the IC available on the outright, which is plausible precisely because
storage and roll flow move the spread while cancelling in the flat
price. That is the claim, and this measures the two numbers it needs:

  1  sigma(spread) / sigma(outright)  -- the capital efficiency, and
     how much of the account one position would actually consume
  2  the IC a spread strategy would need vs an outright strategy, given
     doubled cost and reduced volatility

If (2) comes back demanding a HIGHER IC than the outright, spreads are a
worse deal and the idea dies here. If it comes back demanding a LOWER
one, the structure is worth building a mechanism test on.

Output: research/SPREAD_VIABILITY.md
"""
import gc
import glob
import os
import re
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
MULTI = os.path.join(ROOT, "data", "tick", "multi")
RAW = os.path.join(ROOT, "data", "tick", "raw")
OUT = os.path.join(ROOT, "research", "SPREAD_VIABILITY.md")
NS = 1_000_000_000
# product: ($/point outright, tick, RT cost one leg, approx outright margin)
SPEC = {
    "CL": (1000.0, 0.01, 1.83, 1200),
    "GC": (100.0, 0.10, 1.83, 1300),
    "ES": (50.0, 0.25, 2.58, 2400),
    "YM": (5.0, 1.00, 1.83, 1200),
    "RTY": (50.0, 0.10, 1.83, 1900),
}
MON = {"F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6, "N": 7, "Q": 8,
       "U": 9, "V": 10, "X": 11, "Z": 12}
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def code_key(name):
    m = re.match(r"^([A-Z]+)([FGHJKMNQUVXZ])(\d)$", name)
    if not m:
        return None
    prod, mo, yr = m.groups()
    return prod, 2020 + int(yr), MON[mo]


def sec_series(path):
    d = pd.read_parquet(path, columns=["ts", "price"])
    d = d.sort_values("ts", kind="stable")
    ts = d.ts.values
    px = d.price.values.astype(np.float64)
    del d
    s = pd.Series(px, index=pd.to_datetime(ts))
    s = s.resample("5min").last().dropna()
    return s


def main():
    files = {}
    for p in glob.glob(os.path.join(MULTI, "*.parquet")) + \
            glob.glob(os.path.join(RAW, "*.parquet")):
        k = code_key(os.path.basename(p).replace(".parquet", ""))
        if k and k[0] in SPEC:
            files[k] = p

    rows = []
    for prod in SPEC:
        ks = sorted([k for k in files if k[0] == prod],
                    key=lambda k: (k[1], k[2]))
        for a, b in zip(ks, ks[1:]):
            try:
                sa, sb = sec_series(files[a]), sec_series(files[b])
            except Exception as exc:                          # noqa: BLE001
                print(f"  {a}/{b}: {str(exc)[:60]}")
                continue
            j = pd.concat([sa, sb], axis=1, join="inner").dropna()
            j.columns = ["front", "back"]
            if len(j) < 3000:
                del sa, sb, j
                gc.collect()
                continue
            ppt, tick, cost1, marg = SPEC[prod]
            spd = j["front"] - j["back"]
            # daily sigma in DOLLARS, never differencing across a break
            def dsig(s):
                dd = s.resample("1D").last().dropna()
                return float(dd.diff().std()) * ppt
            so, ss = dsig(j["front"]), dsig(spd)
            rows.append((ss / so, prod, f"{a[2]:02d}/{a[1]}",
                         f"{b[2]:02d}/{b[1]}", so, ss, len(j),
                         cost1, ppt, marg))
            print(f"  {prod} {a[1]}-{a[2]:02d}/{b[1]}-{b[2]:02d}: "
                  f"outright ${so:,.0f}/day  spread ${ss:,.0f}/day",
                  flush=True)
            del sa, sb, j, spd
            gc.collect()
    if not rows:
        print("no overlapping contract pairs found")
        return
    rows.sort()

    log("# Calendar spreads: do they fix the capital problem?")
    log()
    log("The constraint that killed everything in this project is not "
        "signal and not cost. It is that **one micro contract carries "
        "$7,160 of annual volatility against a $4,000 account** -- 179% "
        "-- so the smallest tradeable position is about twelve times "
        "larger than a professionally sized one.")
    log()
    log("A calendar spread is the only structure that attacks that "
        "directly: exchange margin credit, cancelled market risk, and "
        "mechanisms that genuinely exist -- storage cost, seasonality, "
        "and forced ETF roll flow on a published schedule.")
    log()
    log("**The arithmetic that runs against it, stated before the "
        "numbers.** A spread has two legs, so cost roughly doubles. If "
        "volatility falls 10x while cost doubles, cost per unit of "
        "volatility gets **20x worse**. A spread is not free risk "
        "reduction -- you can always cut risk by trading smaller and it "
        "helps nobody. The spread only wins if the IC available on it is "
        "much larger, which is plausible because storage and roll flow "
        "move the spread while cancelling in the flat price.")
    log()
    log("| product | pair | outright $/day | spread $/day | ratio | "
        "% of $4k acct | IC needed vs outright |")
    log("|" + "---|" * 7)
    for r, prod, ka, kb, so, ss, n, cost1, ppt, marg in rows[:16]:
        # annualised vol of one spread against a 4k account
        acct = ss * np.sqrt(252) / 4000.0
        # cost doubles, sigma shrinks by r -> IC requirement scales 2/r
        need = 2.0 / max(r, 1e-9)
        log(f"| {prod} | {ka}-{kb} | ${so:,.0f} | ${ss:,.0f} | "
            f"**{r:.3f}** | {acct:.0%} | **{need:.1f}x** |")
    log()
    med = float(np.median([r[0] for r in rows]))
    log(f"Median spread/outright volatility ratio: **{med:.3f}** -- a "
        f"spread carries about {med*100:.0f}% of the outright's daily "
        f"risk.")
    log()
    log(f"With cost doubled and volatility at {med:.3f} of the outright, "
        f"a spread strategy needs **{2.0/med:.1f}x the IC** of an "
        f"outright strategy to be equally tradable.")
    log()
    if 2.0 / med > 1.0:
        log("**So spreads start behind, and the size of the handicap is "
            "the number above.** They are worth pursuing only if a "
            "spread-specific mechanism -- ETF roll flow, storage, "
            "seasonality -- delivers an IC at least that much larger "
            "than anything available on the flat price. That is a real "
            "possibility and it is the next thing to test, but it is a "
            "hurdle to clear rather than a free lunch.")
    else:
        log("**Spreads start ahead**: volatility falls by more than cost "
            "rises, so the same IC is worth more here than on the "
            "outright.")
    log()
    log("The `% of $4k acct` column is the one that matters for "
        "deployment: it is the annualised volatility of a SINGLE spread "
        "position as a fraction of the account. Compare with 179% for "
        "one MNQ. Anything under about 30% is a position a $4,000 "
        "account can actually hold.")
    log()
    open(OUT, "w").write("\n".join(L) + "\n")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
