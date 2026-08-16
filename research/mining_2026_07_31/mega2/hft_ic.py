"""The HFT lane, asked as a PREDICTOR question instead of a strategy one.

Two things have been done in this repo and neither is this one:

  hf_screen.py       tested STRATEGIES at HFT speed -- 15s bars, 1-6pt
                     brackets, 405 combinations, all negative. But every
                     feature in it came from the trade PRICE PATH, which
                     is the one stream fusion_ceiling measured at a
                     ceiling of zero. That result says "HFT on price
                     shape fails", not "HFT fails".
  orderflow_ic.py    tested order flow as a PREDICTOR -- signed volume,
                     big-trade share, size skew, intensity -- and found
                     it worth measuring. But it ran at 300-SECOND bars.

Nobody has run order flow as a predictor at HFT speed. That is free, the
tapes are already on disk, and it is the cheapest remaining shot at the
lane. This does it at 5s / 15s / 30s / 60s bars.

WHY A PREDICTOR AND NOT A STRATEGY. A strategy test bundles a prediction
question with an execution question, so a negative says nothing about
which half failed. An IC cannot be cherry-picked, because nothing is
being chosen, and one IC informs every strategy buildable on that
feature.

THE COST WALL, stated before the run so no result can be talked past it.
Commission is fixed per trade; opportunity grows with sqrt(time). An IC
pays only if IC x sigma(horizon) beats the round trip:

    taker both ways   $1.74 = 0.87 pt   (commission + crossing twice)
    commission only   $1.24 = 0.62 pt   (maker in AND out -- requires the
                                         6.6% passive fill rate measured
                                         in DEPTH.md to be beatable)
    membership floor  $0.36 = 0.18 pt   (the most optimistic number that
                                         is not fiction)

SUCCESS CRITERION, fixed here before running: an order-flow feature must
show |IC| at least 3x the measured shift floor, hold its sign in the
holdout contracts, and clear at least the commission-only cost at some
horizon of 60 seconds or less. Anything that clears only at 5+ minutes
is a real signal but not an HFT one, and gets routed to Track B.

CONTROLS
  shuffled    feature values in random order -- what this pipeline
              manufactures from nothing
  price       return and range over the bar. Order flow has to BEAT what
              OHLC already gives us or the data is not worth reading.
  shift floor the forward return slid by hours and rejoined. Both series
              keep their autocorrelation, only the alignment dies. On
              millions of overlapping bars this is the honest noise
              floor; 3/sqrt(n) would quote a precision the data has not
              got.

Output: research/HFT_IC.md
"""
import gc
import glob
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
RAW = os.path.join(ROOT, "data", "tick", "raw")
OUT = os.path.join(ROOT, "research", "HFT_IC.md")
NS = 1_000_000_000
BARS = [5, 15, 30, 60]
FWD = [1, 2, 4, 8, 20]
BIG = 10
TV = 2.0                       # MNQ $/pt
COSTS = [("taker", 0.87), ("commission only", 0.62), ("membership", 0.18)]
FLOW = ["delta", "dratio", "cumdelta", "bigratio", "szskew", "intensity",
        "tickrun"]
PRICE = ["ret", "rng"]
SHIFTS = [601, 1201, 2411, 4801, -601, -1201, -2411, -4801]   # in bars
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def ic(x, y):
    """Spearman by hand: Pearson on ranks. scipy is NOT installed here."""
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 1000:
        return np.nan
    a = pd.Series(x[ok]).rank().values
    b = pd.Series(y[ok]).rank().values
    a = a - a.mean()
    b = b - b.mean()
    den = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / den) if den > 0 else np.nan


def bars_for(path, barsec):
    """RTH time bars with order-flow columns from one contract's tape."""
    d = pd.read_parquet(path, columns=["ts", "price", "size"])
    d = d.sort_values("ts", kind="stable")
    ts = d.ts.values
    px = d.price.values.astype(np.float64)
    sz = d["size"].values.astype(np.float64)   # d["size"], never d.size
    del d
    idx = pd.to_datetime(ts)
    tod = idx.hour * 60 + idx.minute
    keep = np.asarray((tod >= 13 * 60 + 30) & (idx.hour < 20))
    if keep.sum() < 100_000:
        return None
    ts, px, sz = ts[keep], px[keep], sz[keep]
    del idx, tod, keep
    gc.collect()

    # tick rule: a trade above the last different price is buyer-initiated;
    # flat trades inherit the previous sign.
    dp = np.diff(px, prepend=px[0])
    sgn = np.sign(dp)
    filled = pd.Series(np.where(sgn != 0, sgn, np.nan)).ffill()
    filled = filled.fillna(1.0).values

    b = ts // (barsec * NS)
    day = ts // (86400 * NS)
    g = pd.DataFrame(dict(b=b, px=px, sz=sz, sv=filled * sz,
                          big=np.where(sz >= BIG, sz, 0.0),
                          up=(filled > 0).astype(np.float64),
                          day=day, ts=ts))
    a = g.groupby("b").agg(high=("px", "max"), low=("px", "min"),
                           close=("px", "last"), vol=("sz", "sum"),
                           delta=("sv", "sum"), bigv=("big", "sum"),
                           nup=("up", "sum"), ntr=("px", "size"),
                           day=("day", "first"), t0=("ts", "first"),
                           t1=("ts", "last"))
    a = a[a.vol > 0]
    if len(a) < 5000:
        return None
    hi = g.px.values == g.groupby("b").px.transform("max").values
    lo = g.px.values == g.groupby("b").px.transform("min").values
    a["hisz"] = g[hi].groupby("b").sz.sum().reindex(a.index).fillna(0)
    a["losz"] = g[lo].groupby("b").sz.sum().reindex(a.index).fillna(0)
    del g
    gc.collect()

    a["dratio"] = a.delta / a.vol
    a["bigratio"] = a.bigv / a.vol
    a["szskew"] = (a.hisz - a.losz) / np.maximum(a.hisz + a.losz, 1.0)
    # share of trades on the up-tick: direction of participation, not size
    a["tickrun"] = 2.0 * (a.nup / np.maximum(a.ntr, 1)) - 1.0
    dur = np.maximum((a.t1 - a.t0) / NS, 1e-3)
    a["intensity"] = a.ntr / dur
    a["intensity"] /= a["intensity"].rolling(400, min_periods=100).mean()
    a["cumdelta"] = a.delta.cumsum()
    a["cumdelta"] -= a.cumdelta.rolling(400, min_periods=100).mean()
    a["ret"] = a.close.diff()
    a["rng"] = a.high - a.low
    a["delta"] = a.delta / np.maximum(
        a.vol.rolling(400, min_periods=100).mean(), 1e-9)
    return a


def forward(a, k):
    """k-bar forward close-to-close in POINTS, never across a day break.

    Bars are keyed on wall-clock buckets, so consecutive rows can be
    yesterday's close and today's open. A forward return over that gap is
    an overnight move wearing a 30-second label.
    """
    c = a.close.values
    day = a.day.values
    n = len(c)
    y = np.full(n, np.nan)
    y[:n - k] = c[k:] - c[:n - k]
    same = np.zeros(n, dtype=bool)
    same[:n - k] = day[k:] == day[:n - k]
    y[~same] = np.nan
    return y


def main():
    files = sorted(glob.glob(os.path.join(RAW, "*.parquet")))
    files = [f for f in files
             if os.path.basename(f).startswith("NQ")]
    if not files:
        print(f"no NQ tick parquets in {RAW}")
        return
    log("# The HFT lane as a predictor question: does order flow "
        "predict at 5-60 second bars?")
    log()
    log("`hf_screen.py` tested 405 HFT STRATEGIES and all were negative, "
        "but every feature in it came from the trade price path -- the "
        "one stream `fusion_ceiling.py` measured at a ceiling of zero. "
        "`orderflow_ic.py` tested order flow as a PREDICTOR and found it "
        "worth measuring, but only at 300-second bars. Order flow has "
        "never been tested as a predictor at HFT speed. This does that.")
    log()
    log("Entry is not modelled and no bracket is chosen: this measures "
        "whether the feature knows anything, which is the question that "
        "has to come first.")
    log()
    cost_txt = ", ".join(f"{n} {c:.2f}pt" for n, c in COSTS)
    log(f"An IC pays only if `IC x sigma(horizon)` beats the round trip "
        f"({cost_txt}). That comparison is in every table below, because "
        f"it is the whole question at this speed.")
    log()

    survivors = []
    for barsec in BARS:
        per = {}
        for f in files:
            cn = os.path.basename(f).replace(".parquet", "")
            try:
                a = bars_for(f, barsec)
            except Exception as exc:                          # noqa: BLE001
                print(f"  {cn} {barsec}s: failed ({exc})", flush=True)
                continue
            if a is None:
                print(f"  {cn} {barsec}s: too little RTH tape", flush=True)
                continue
            per[cn] = a
            print(f"  {cn} {barsec}s: {len(a):,} bars", flush=True)
            gc.collect()
        if not per:
            continue
        cs = sorted(per)
        tr_c = cs[:max(1, len(cs) * 2 // 3)]
        ho_c = [c for c in cs if c not in tr_c]

        rng = np.random.default_rng(29)
        log(f"## {barsec}-second bars")
        log()
        log(f"train contracts: {', '.join(tr_c)} | holdout: "
            f"{', '.join(ho_c)}")
        log()
        for k in FWD:
            secs = barsec * k
            Y = {c: forward(per[c], k) for c in cs}
            sig = float(np.nanstd(np.concatenate([Y[c] for c in cs])))
            log(f"### {k} bar{'s' if k > 1 else ''} ahead = {secs}s "
                f"(sigma {sig:.2f} pt)")
            log()
            log("| feature | train IC | holdout IC | shift floor | "
                "IC/floor | edge | clears |")
            log("|---|---|---|---|---|---|---|")
            for col in FLOW + PRICE + ["shuffled"]:
                xs, ys = {}, {}
                for c in cs:
                    if col == "shuffled":
                        xs[c] = rng.permutation(per[c]["dratio"].values)
                    else:
                        xs[c] = per[c][col].values
                    ys[c] = Y[c]
                xt = np.concatenate([xs[c] for c in tr_c])
                yt = np.concatenate([ys[c] for c in tr_c])
                xh = np.concatenate([xs[c] for c in ho_c])
                yh = np.concatenate([ys[c] for c in ho_c])
                tr = ic(xt, yt)
                ho = ic(xh, yh)
                fl = [ic(xh, np.roll(yh, s)) for s in SHIFTS]
                floor = (float(np.nanstd(fl))
                         if np.isfinite(fl).any() else np.nan)
                ratio = abs(ho) / floor if floor and floor > 0 else np.nan
                edge = abs(ho) * sig
                clears = [n for n, c_ in COSTS if edge > c_]
                log(f"| {col} | {tr:+.4f} | {ho:+.4f} | {floor:.4f} | "
                    f"{ratio:.1f} | {edge:.3f} pt | "
                    f"{', '.join(clears) if clears else 'nothing'} |")
                if (col in FLOW and np.isfinite(ratio) and ratio >= 3.0
                        and np.isfinite(tr) and np.sign(tr) == np.sign(ho)
                        and edge > 0.62 and secs <= 60):
                    survivors.append((col, barsec, k, secs, ho, edge))
            log()
            del Y
            gc.collect()
        del per
        gc.collect()

    log("## Verdict against the criterion fixed before the run")
    log()
    log("|IC| >= 3x the measured shift floor, sign consistent between "
        "train and holdout contracts, and edge clearing at least the "
        "commission-only cost (0.62pt) at a horizon of 60 seconds or "
        "less.")
    log()
    if not survivors:
        log("**Nothing passes.** Order flow at 5-60 second bars does not "
            "carry enough information to pay for a round trip at this "
            "speed. Combined with the 405 negative price-path cells in "
            "`HF_SCREEN.md`, the free data is now exhausted on the HFT "
            "question: what remains untested at this speed is the ORDER "
            "BOOK, which is what the Track A purchase is for.")
    else:
        log(f"**{len(survivors)} feature/horizon combinations pass.**")
        log()
        log("| feature | bar | horizon | holdout IC | edge |")
        log("|---|---|---|---|---|")
        for col, barsec, k, secs, ho, edge in survivors:
            log(f"| {col} | {barsec}s | {secs}s | {ho:+.4f} | "
                f"{edge:.3f} pt |")
        log()
        log("These earn a full causal validation with real fill "
            "physics before anything is built on them.")
    log()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write("\n".join(L) + "\n")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
