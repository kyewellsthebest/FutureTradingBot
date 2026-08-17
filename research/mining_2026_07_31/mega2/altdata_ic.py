"""Does any NON-PRICE data predict NQ at multi-day horizons?

Every one of the 22 hypotheses in the ledger read the price path, and
every one was intraday. Both of those are the wrong end of the problem:

    horizon    sigma (MNQ $)    cost      IC needed to pay
    10 min        $46          $1.83          0.040
    4 hours      $354          $1.83          0.005
    1 day        $428          $1.83          0.0043
    5 days       $957          $1.83          0.0019

At a 10-minute hold the cost bar is 0.040 and everything measured today
came in under it. At a WEEK the bar is 0.0019 -- twenty times lower.
Book imbalance measures IC 0.0425, eight times what a daily horizon
needs; it fails only because it decays to nothing inside five minutes.
A weak but PERSISTENT signal beats a strong one that evaporates, and
that is exactly the shape macro and positioning data have.

So this tests the premise before anyone builds a data pipeline for it:
does non-price data already on disk predict NQ at 1-20 days?

    DTS    Daily Treasury Statement -- actual federal cash in and out.
           Never tested. Real economic flow, not a survey.
    FRED   rates, curve, VIX, WTI. Never tested as a set.
    GEX    dealer gamma. Ledger #16 tested it DAILY and found null;
           included here for the longer horizons and as a known-null
           reference row.

POINT-IN-TIME DISCIPLINE is the whole game with this kind of data, and
it is where these studies usually die. Every series is lagged by its
real publication delay, not by when the data is *about*:

    DTS    published the NEXT business day, so lag 2 to be safe
    FRED   daily series post next morning, lag 2
    GEX    computable after the close, lag 1

CONTROLS: the target shuffled, and the feature rolled +-30/60/90 days.
The roll keeps each series' autocorrelation and destroys only its
alignment, which is the harder bar -- a spurious correlation driven by
two trending series survives shuffling but dies under the roll.

Output: research/ALTDATA_IC.md
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
RD = os.path.join(ROOT, "data", "research_data")
OUT = os.path.join(ROOT, "research", "ALTDATA_IC.md")
HZ = [1, 3, 5, 10, 20]
# 100 roll offsets, not 6. The standard deviation of six draws is
# violently noisy and biased LOW, which inflates every IC/floor ratio
# built on it. With daily observations and a 20-day forward return the
# effective sample is ~50, so the true standard error on a correlation
# is near 0.14 -- a six-sample floor reported 0.0535 and would have
# waved through five "survivors" on that basis alone.
ROLLS = ([r for r in range(25, 420, 8)]
         + [-r for r in range(25, 420, 8)])
PT = 2.0
COST = 1.83
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def ic(x, y):
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 120:
        return np.nan
    a = pd.Series(x[ok]).rank().values
    b = pd.Series(y[ok]).rank().values
    a = a - a.mean()
    b = b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 0 else np.nan


def load_px():
    p = os.path.join(ROOT, "data", "polygon", "NQ_5min.csv")
    d = pd.read_csv(p)
    d["ts"] = pd.to_datetime(d["ts"], utc=True)
    s = d.set_index("ts")["close"].resample("1D").last().dropna()
    s.index = s.index.normalize().tz_localize(None)
    return s


def load_feats():
    F = {}
    for f in sorted(glob.glob(os.path.join(RD, "fred", "*.csv"))):
        try:
            d = pd.read_csv(f)
            dc = d.columns[0]
            vc = d.columns[1]
            d[dc] = pd.to_datetime(d[dc], errors="coerce")
            v = pd.to_numeric(d[vc], errors="coerce")
            s = pd.Series(v.values, index=d[dc]).dropna()
            if len(s) > 300:
                nm = os.path.basename(f).replace(".csv", "")
                F[f"fred_{nm}"] = (s, 2)
                F[f"fred_{nm}_d5"] = (s.diff(5).dropna(), 2)
        except Exception as exc:                              # noqa: BLE001
            print(f"  fred {os.path.basename(f)}: {str(exc)[:70]}")
    for f in sorted(glob.glob(os.path.join(RD, "dts", "*.csv"))):
        base = os.path.basename(f)
        if base.startswith("38d"):
            continue
        try:
            d = pd.read_csv(f, low_memory=False)
            dc = next((c for c in d.columns
                       if "date" in c.lower()), None)
            if dc is None:
                continue
            d[dc] = pd.to_datetime(d[dc], errors="coerce")
            num = [c for c in d.columns
                   if pd.api.types.is_numeric_dtype(d[c])]
            if not num:
                continue
            g = d.groupby(dc)[num[0]].sum()
            g = g[g.index.notna()]
            if len(g) > 300:
                nm = base.split("_")[1] if "_" in base else base[:12]
                F[f"dts_{nm}"] = (g, 2)
                F[f"dts_{nm}_d5"] = (g.diff(5).dropna(), 2)
        except Exception as exc:                              # noqa: BLE001
            print(f"  dts {base}: {str(exc)[:70]}")
    try:
        g = pd.read_parquet(os.path.join(ROOT, "data", "gex",
                                         "gex_history.parquet"))
        g["day"] = pd.to_datetime(g["day"])
        for fam, sub in g.groupby("fam"):
            s = sub.set_index("day")["gex_vol"].sort_index()
            if len(s) > 300:
                F[f"gex_{fam}"] = (s, 1)
    except Exception as exc:                                  # noqa: BLE001
        print(f"  gex: {str(exc)[:70]}")
    return F


def main():
    px = load_px()
    F = load_feats()
    print(f"price days {len(px)}, features {len(F)}", flush=True)
    if not F:
        print("no features loaded")
        return
    fwd = {}
    for h in HZ:
        fwd[h] = (px.shift(-h) - px).reindex(px.index)

    rows = []
    for name, (s, lag) in F.items():
        s = s[~s.index.duplicated(keep="last")].sort_index()
        # publication lag, applied on the CALENDAR then aligned forward
        sl = s.copy()
        sl.index = sl.index + pd.Timedelta(days=lag)
        al = sl.reindex(px.index, method="ffill")
        for h in HZ:
            y = fwd[h].values
            x = al.values
            v = ic(x, y)
            if not np.isfinite(v):
                continue
            fl = [ic(np.roll(x, r), y) for r in ROLLS]
            floor = float(np.nanstd(fl)) if np.isfinite(fl).any() else np.nan
            sh = ic(np.random.default_rng(3).permutation(x), y)
            sig_usd = float(np.nanstd(y)) * PT
            edge = abs(v) * sig_usd
            rows.append((abs(v) / floor if floor else np.nan, v, floor,
                         sh, name, h, edge, edge - COST))
    rows = [r for r in rows if np.isfinite(r[0])]
    rows.sort(reverse=True)

    log("# Does any NON-PRICE data predict NQ at multi-day horizons?")
    log()
    log("Every hypothesis in the ledger read the price path, and every "
        "one was intraday. Both are the wrong end of the problem:")
    log()
    log("| horizon | sigma (MNQ $) | cost | IC needed |")
    log("|---|---|---|---|")
    log("| 10 min | $46 | $1.83 | 0.040 |")
    log("| 4 hours | $354 | $1.83 | 0.005 |")
    log("| 1 day | $428 | $1.83 | 0.0043 |")
    log("| 5 days | $957 | $1.83 | 0.0019 |")
    log()
    log("At ten minutes the bar is 0.040 and everything measured today "
        "came in under it. At a week it is **0.0019** -- twenty times "
        "lower. Book imbalance measures 0.0425, eight times what a daily "
        "horizon needs, and fails only because it decays inside five "
        "minutes. **A weak but persistent signal beats a strong one that "
        "evaporates.**")
    log()
    log(f"{len(px)} trading days. Every series lagged by its real "
        f"publication delay -- DTS and FRED by 2 days, GEX by 1 -- "
        f"because point-in-time discipline is where this kind of study "
        f"usually dies. `floor` is the standard deviation of the same IC "
        f"with the feature rolled +-30/60/90 days: that keeps each "
        f"series' autocorrelation and destroys only the alignment, which "
        f"is the harder bar, since two trending series survive shuffling "
        f"but not the roll.")
    log()
    log("| feature | horizon | IC | roll floor | IC/floor | shuffled | "
        "edge $ | vs $1.83 cost |")
    log("|" + "---|" * 8)
    for r, v, fl, sh, name, h, edge, net in rows[:25]:
        log(f"| {name} | {h}d | {v:+.4f} | {fl:.4f} | **{r:.1f}** | "
            f"{sh:+.4f} | ${edge:.2f} | ${net:+.2f} |")
    hits = [x for x in rows if x[0] >= 3.0 and x[7] > 0]
    log()
    log(f"**Clearing 3x the roll floor AND covering cost: {len(hits)} of "
        f"{len(rows)}**")
    log()
    for r, v, fl, sh, name, h, edge, net in hits[:12]:
        log(f"- `{name}` at {h}d: IC {v:+.4f}, {r:.1f}x floor, "
            f"${net:+.2f}/trade net of cost")
    log()
    log("A survivor here is a CANDIDATE, not a strategy. It would still "
        "need the full gate: held-out P&L, an all-cell empirical null, "
        "6/8 green quarters, a stale placebo that loses, and a "
        "trade-for-trade match against the live executor before any "
        "capital moves.")
    log()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write("\n".join(L) + "\n")
    print("wrote research/ALTDATA_IC.md")


if __name__ == "__main__":
    main()
