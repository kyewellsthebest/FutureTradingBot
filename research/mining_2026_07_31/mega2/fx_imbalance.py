"""Quote imbalance on FX ticks -- the one non-null result, on data we own.

Sixteen families measured on futures TRADE PRINTS came back null. The first
thing measured on a real ORDER BOOK did not: NASDAQ ITCH gave a holdout IC of
+0.1165 for resting bid size against resting ask size, with a shuffled control
at +0.003 and a time-shifted control at -0.001. The information futures prints
do not contain is real, and it is the reason MBO costs money.

Dukascopy ships bid_volume and ask_volume on every tick. That is top of book on
both sides -- the same quantity, one level deep, on 69 million ticks across
four symbols, for nothing. So the question is no longer whether book imbalance
predicts somewhere; it is whether it predicts HERE, by enough to clear a spread
we have measured rather than guessed.

Same method as everything else in this project:

  IC against forward mid moves, at several horizons in EVENT time
  TWO controls -- a plain shuffle, and a circular shift that keeps the
    feature's persistence and destroys only its alignment with the future
  train and holdout split by time
  a decile table that assumes no linearity: sort the holdout by imbalance and
    read off what actually happened next
  everything in PIPS, against the measured half-spread, because an IC that
    does not clear the cost of crossing is not a trade

One caveat stated up front: Dukascopy's volume field is indicative liquidity at
the top of book, not an exact resting size like an ITCH order book. It is the
right shape of quantity and the wrong precision, so a weaker result here than
on ITCH would not be surprising and would not be evidence against ITCH.

Usage: python fx_imbalance.py [SYMBOL ...]
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
FX = os.path.join(ROOT, "data", "fx")
OUT = os.path.join(ROOT, "research", "FX_IMBALANCE.md")
PIP = {"EURUSD": 1e-4, "GBPUSD": 1e-4, "USDJPY": 1e-2, "XAUUSD": 1e-1}
HORIZONS = [int(x) for x in os.environ.get("HORIZONS", "1,5,20,100").split(",")]
SYMS = [s.upper() for s in (sys.argv[1:] or ["EURUSD", "GBPUSD", "USDJPY",
                                             "XAUUSD"])]
LINES = []


def log(s=""):
    print(s, flush=True)
    LINES.append(s)


def ic(x, y):
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 1000:
        return np.nan
    a = pd.Series(x[m]).rank().values
    b = pd.Series(y[m]).rank().values
    a = a - a.mean()
    b = b - b.mean()
    den = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / den) if den > 0 else np.nan


log("# Quote imbalance on FX ticks")
log()
log("Top-of-book size on the bid against top-of-book size on the ask, measured "
    "the same way the NASDAQ order book was. Everything in pips, against a "
    "spread that was measured and not modelled.")
log()

for sym in SYMS:
    fs = sorted(glob.glob(os.path.join(FX, f"{sym}_*.parquet")))
    if not fs:
        log(f"## {sym}: no data")
        continue
    d = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
    d = d.sort_values("time", kind="stable").reset_index(drop=True)
    p = PIP[sym]
    bid = d.bid.values.astype(np.float64)
    ask = d.ask.values.astype(np.float64)
    bv = d.bid_volume.values.astype(np.float64)
    av = d.ask_volume.values.astype(np.float64)
    mid = (bid + ask) / 2.0
    spread = (ask - bid) / p
    n = len(d)
    del d

    imb = (bv - av) / np.maximum(bv + av, 1.0)
    rng = np.random.default_rng(17)
    shuffled = rng.permutation(imb)
    shifted = np.roll(imb, n // 3)      # same persistence, no alignment

    cut = int(n * 0.7)
    early = np.zeros(n, bool); early[:cut] = True
    late = ~early

    log(f"## {sym}")
    log()
    log(f"{n:,} ticks. Median spread **{np.median(spread):.2f} pips**, so "
        f"crossing costs **{np.median(spread)/2:.2f} pips** each way. "
        f"Imbalance sigma {imb.std():.3f}.")
    log()
    log("| horizon | feature | train IC | holdout IC | sign held |")
    log("|---|---|---|---|---|")
    best = (None, 0.0, 0.0)
    ctrl = {}
    for h in HORIZONS:
        fwd = np.full(n, np.nan)
        fwd[:-h] = (mid[h:] - mid[:-h]) / p          # forward move, in pips
        for name, col in (("imbalance", imb), ("shuffled", shuffled),
                          ("shifted", shifted)):
            it = ic(col[early], fwd[early])
            ih = ic(col[late], fwd[late])
            held = ("yes" if np.isfinite(it) and np.isfinite(ih)
                    and np.sign(it) == np.sign(ih) else "no")
            log(f"| {h} ticks | {name} | {it:+.4f} | {ih:+.4f} | {held} |")
            ctrl[(h, name)] = ih
            if name == "imbalance" and np.isfinite(ih) and abs(ih) > abs(best[1]):
                best = (h, ih, float(np.nanstd(fwd)))
    log()

    # Price EVERY horizon, not just the strongest. The one-tick number is the
    # one to distrust: if resting bid size drains to nothing, the very next
    # quote prints a lower bid -- that is the same event observed twice, not a
    # forecast of a later one. A signal that survives at 5, 20 and 100 ticks is
    # making a claim about the future; a signal that only exists at 1 is
    # probably describing the present.
    log("| horizon | holdout IC | net of control | fwd sigma | worth | vs "
        "half-spread |")
    log("|---|---|---|---|---|---|")
    half = float(np.median(spread)) / 2.0
    for h in HORIZONS:
        fwd = np.full(n, np.nan)
        fwd[:-h] = (mid[h:] - mid[:-h]) / p
        icv = ctrl.get((h, "imbalance"), np.nan)
        sh = ctrl.get((h, "shifted"), np.nan)
        if not np.isfinite(icv):
            continue
        sd = float(np.nanstd(fwd))
        edge = abs(icv) - (abs(sh) if np.isfinite(sh) else 0.0)
        w = max(edge, 0.0) * sd
        log(f"| {h} ticks | {icv:+.4f} | {edge:+.4f} | {sd:.3f} pips | "
            f"{w:.4f} pips | {w/max(half,1e-12):.2f}x |")
    log()

    if best[0]:
        h, icv, sd = best
        sh = ctrl.get((h, "shifted"), np.nan)
        edge = abs(icv) - (abs(sh) if np.isfinite(sh) else 0.0)
        worth = max(edge, 0.0) * sd
        half = float(np.median(spread)) / 2.0
        log(f"**Best: {icv:+.4f} at {h} ticks ahead**, against a time-shifted "
            f"control of {sh:+.4f}. Forward move sigma {sd:.2f} pips.")
        log()
        log(f"- net of the control, worth about **{worth:.3f} pips** a trade")
        log(f"- crossing costs **{half:.2f} pips** each way")
        log(f"- **as a taker: "
            f"{'clears the spread' if worth > half else 'does NOT clear the spread'}**")
        log()

        # no linearity assumed: what actually happened next, by decile
        fwd = np.full(n, np.nan)
        fwd[:-h] = (mid[h:] - mid[:-h]) / p
        m = late & np.isfinite(fwd)
        H = pd.DataFrame({"imb": imb[m], "fwd": fwd[m]})
        try:
            H["dec"] = pd.qcut(H.imb, 10, labels=False, duplicates="drop")
            g = H.groupby("dec").fwd.agg(["mean", "count", "std"])
            log(f"| imbalance decile | mean move over {h} ticks | n |")
            log("|---|---|---|")
            for i, r in g.iterrows():
                log(f"| {int(i)} | {r['mean']:+.4f} pips | {int(r['count']):,} |")
            lo_, hi_ = g.iloc[0], g.iloc[-1]
            dd = hi_["mean"] - lo_["mean"]
            dse = np.sqrt(lo_["std"] ** 2 / lo_["count"]
                          + hi_["std"] ** 2 / hi_["count"])
            log()
            log(f"**Top decile minus bottom: {dd:+.4f} pips +/- {dse:.4f} "
                f"({abs(dd)/max(dse,1e-12):.1f} sigma).** One side of that is "
                f"about {dd/2:+.4f} pips against {half:.2f} pips to cross.")
        except Exception as e:
            log(f"decile table unavailable: {type(e).__name__}: {e}")
    log()

os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w").write("\n".join(LINES) + "\n")
print("\nwrote", OUT)
