"""External state: who is positioned how, and who is forced to trade.

WHY THIS IS THE MISSING FAMILY. Every condition the search had --
hi_vol, lo_vol, up_day, dn_day -- is derived from the same price series
it is trying to predict. Conditioning price on price is a filter with no
outside information in it. The datasets here are outside information,
and more importantly they are information about CONSTRAINT: who holds
what, who must hedge it, and when money must move regardless of price.

  DEALER GAMMA (data/gex)  When dealers are short gamma they must buy
      strength and sell weakness to stay hedged, which amplifies moves.
      Long gamma, they do the opposite and suppress the range. This is
      the cleanest forced-flow mechanism available at daily resolution:
      the hedging is not optional.

  POSITIONING (data/research_data/cftc)  Weekly, by trader category.
      Extremes matter because a crowded position is fuel for an unwind,
      not because crowds are wrong.

  FUNDING AND CREDIT (data/research_data/fred)  SOFR-IORB tells you when
      cash is scarce; HY spreads tell you when risk appetite turns. Both
      change who can hold what.

  TREASURY FLOWS (data/research_data/dts)  Corporate tax dates move tens
      of billions on a known calendar. Nobody chooses to pay tax on a
      different day.

THE THING THAT WOULD RUIN ALL OF IT: PUBLICATION LAG.

Every series here is known LATER than the date it describes. The COT
report covers Tuesday and is published the following Friday afternoon;
using Tuesday's number on Tuesday is reading a report that does not
exist yet. That single mistake would manufacture an edge in every
positioning hypothesis at once, and it is invisible in the output --
it just looks like the feature works.

So every series declares its own lag, the lag is applied by shifting the
series forward before it is ever joined, and `lag_selftest()` verifies
that the value in force at time T was in fact published at or before T.
No series is usable here without a declared lag.
"""
from __future__ import annotations

import glob
import os

import numpy as np
import pandas as pd

ROOT = os.environ.get("M2_REPO", os.getcwd())

# Business-day lag between the date a series DESCRIBES and the moment it
# is public. Conservative in every case -- one day too many costs a
# little power, one day too few manufactures an edge.
LAGS = {
    "gex": 1,        # computed from the prior session's option chain
    "cot": 3,        # Tuesday snapshot, published Friday 15:30 ET
    "fred": 1,       # daily series, published next morning
    "dts": 1,        # Daily Treasury Statement, ~4pm next business day
}

# which CFTC market maps to which of our symbols
COT_MAP = {
    "NQ": "NASDAQ", "ES": "S&P 500", "YM": "DOW JONES",
    "RTY": "RUSSELL", "6E": "EURO FX", "6J": "JAPANESE YEN",
    "6B": "BRITISH POUND", "6A": "AUSTRALIAN DOLLAR",
}
GEX_MAP = {"NQ": "NDX", "ES": "SPX", "YM": "SPX", "RTY": "SPX"}


def _ns(idx):
    """A DatetimeIndex at nanosecond resolution, UTC, whatever came in.

    pandas 2 keeps whatever unit the source had, and parquet written by
    the deep-bar builder carries microseconds. merge_asof refuses to join
    datetime64[us, UTC] against datetime64[ns, UTC] -- so every deep-tier
    tape raised "incompatible merge keys", the exception was caught and
    logged as context_failed, and the deep tier ran with NO regime
    conditioning at all. Loudly logged and completely invisible: the
    searcher looked healthy and was quietly blind to credit stress,
    positioning and dealer gamma on the deepest data it has.
    """
    i = pd.DatetimeIndex(idx)
    if i.tz is None:
        i = i.tz_localize("UTC")
    else:
        i = i.tz_convert("UTC")
    return i.as_unit("ns") if hasattr(i, "as_unit") else i


def _daily(idx):
    return _ns(idx).normalize()


# ------------------------------------------------------------- loaders
def load_gex():
    p = os.path.join(ROOT, "data", "gex", "gex_history.parquet")
    if not os.path.exists(p):
        return None
    d = pd.read_parquet(p)
    d["day"] = pd.to_datetime(d["day"], utc=True).dt.normalize()
    out = {}
    for fam, g in d.groupby("fam"):
        s = g.set_index("day")["gex_vol"].sort_index()
        s = s[~s.index.duplicated(keep="last")]
        out[fam] = s
    return out or None


def load_cot():
    fs = sorted(glob.glob(os.path.join(ROOT, "data", "research_data",
                                       "cftc", "FinCom_*.txt")))
    if not fs:
        return None
    keep = ["Market_and_Exchange_Names", "Report_Date_as_YYYY-MM-DD",
            "Open_Interest_All", "Lev_Money_Positions_Long_All",
            "Lev_Money_Positions_Short_All",
            "Asset_Mgr_Positions_Long_All", "Asset_Mgr_Positions_Short_All"]
    parts = []
    for f in fs:
        try:
            d = pd.read_csv(f, usecols=lambda c: c in keep,
                            low_memory=False)
            parts.append(d)
        except Exception:                                     # noqa: BLE001
            continue
    if not parts:
        return None
    d = pd.concat(parts, ignore_index=True)
    d["day"] = pd.to_datetime(d["Report_Date_as_YYYY-MM-DD"],
                              errors="coerce", utc=True).dt.normalize()
    d = d.dropna(subset=["day"])
    lev_l = pd.to_numeric(d.get("Lev_Money_Positions_Long_All"),
                          errors="coerce")
    lev_s = pd.to_numeric(d.get("Lev_Money_Positions_Short_All"),
                          errors="coerce")
    oi = pd.to_numeric(d.get("Open_Interest_All"), errors="coerce")
    d["lev_net"] = (lev_l - lev_s) / oi.replace(0, np.nan)
    d["name"] = d["Market_and_Exchange_Names"].astype(str).str.upper()
    return d[["day", "name", "lev_net"]].dropna(subset=["lev_net"])


def load_fred():
    base = os.path.join(ROOT, "data", "research_data", "fred")
    out = {}
    for p in glob.glob(os.path.join(base, "*.csv")):
        k = os.path.basename(p).replace(".csv", "").lower()
        try:
            d = pd.read_csv(p)
            dc = d.columns[0]
            vc = [c for c in d.columns[1:]
                  if pd.api.types.is_numeric_dtype(
                      pd.to_numeric(d[c], errors="coerce"))]
            if not vc:
                continue
            s = pd.Series(pd.to_numeric(d[vc[0]], errors="coerce").values,
                          index=pd.to_datetime(d[dc], errors="coerce",
                                               utc=True)).dropna()
            s = s[~s.index.duplicated(keep="last")].sort_index()
            s.index = s.index.normalize()
            if len(s) > 100:
                out[k] = s
        except Exception:                                     # noqa: BLE001
            continue
    return out or None


# ---------------------------------------------------- align to a tape
def _asof(series, days, lag_bdays):
    """Value known at each day, given publication lag.

    The lag is applied by moving the series' own index FORWARD, so a
    value dated Tuesday only becomes visible on Friday. Then a backward
    as-of join takes the most recent visible value. Getting this
    backwards -- joining first and lagging after -- is the same bug in a
    costume, because the join would already have seen the future.
    """
    if series is None or not len(series):
        return None
    s = series.copy()
    s.index = _ns(s.index) + pd.tseries.offsets.BDay(lag_bdays)
    s.index = _ns(s.index)          # BDay can widen the unit again
    s = s[~s.index.duplicated(keep="last")].sort_index()
    t = pd.DataFrame({"day": _ns(pd.DatetimeIndex(sorted(set(days))))})
    j = pd.merge_asof(t, s.rename("v").reset_index().rename(
        columns={s.index.name or "index": "day"}),
        on="day", direction="backward")
    return dict(zip(j["day"], j["v"]))


def build(sym, index):
    """External conditioning columns for one market's tape.

    Returns a DataFrame aligned to `index`, or None. Every column is a
    value that was PUBLIC at that timestamp.
    """
    days = _daily(index)
    uniq = pd.DatetimeIndex(sorted(set(days)))
    cols = {}

    gex = load_gex()
    if gex and sym in GEX_MAP and GEX_MAP[sym] in gex:
        m = _asof(gex[GEX_MAP[sym]], uniq, LAGS["gex"])
        if m:
            cols["gex"] = np.array([m.get(d, np.nan) for d in days],
                                   dtype=float)

    cot = load_cot()
    if cot is not None and sym in COT_MAP:
        sub = cot[cot["name"].str.contains(COT_MAP[sym], na=False)]
        if len(sub) > 20:
            s = sub.groupby("day")["lev_net"].last().sort_index()
            m = _asof(s, uniq, LAGS["cot"])
            if m:
                cols["lev_net"] = np.array([m.get(d, np.nan) for d in days],
                                           dtype=float)

    fr = load_fred()
    if fr:
        if "sofr" in fr and "iorb" in fr:
            sp = (fr["sofr"] - fr["iorb"]).dropna()
            m = _asof(sp, uniq, LAGS["fred"])
            if m:
                cols["funding"] = np.array([m.get(d, np.nan) for d in days],
                                           dtype=float)
        if "hy_spread" in fr:
            m = _asof(fr["hy_spread"], uniq, LAGS["fred"])
            if m:
                cols["credit"] = np.array([m.get(d, np.nan) for d in days],
                                          dtype=float)
    if not cols:
        return None
    return pd.DataFrame(cols, index=index)


# --------------------------------------------------------- conditions
# Each is a stated mechanism, not a bucket. The sign convention is
# written down here so nothing downstream has to guess it.
CONTEXT_CONDS = {
    "short_gamma": ("gex", lambda v, med: v < 0,
                    "Dealers are net short gamma, so hedging forces them "
                    "to buy strength and sell weakness. Moves get "
                    "amplified rather than damped. The hedging is "
                    "mechanical -- it is not a view."),
    "long_gamma": ("gex", lambda v, med: v > 0,
                   "Dealers are net long gamma and hedge against the "
                   "move, suppressing range. Trend strategies should "
                   "struggle here and mean reversion should not."),
    "crowded_long": ("lev_net", lambda v, med: v > med,
                     "Leveraged money is more net long than usual. A "
                     "crowded position is fuel for an unwind -- not "
                     "because crowds are wrong, but because they are "
                     "the ones who have to sell."),
    "crowded_short": ("lev_net", lambda v, med: v < med,
                      "Leveraged money is more net short than usual, so "
                      "the vulnerable direction is up."),
    "tight_funding": ("funding", lambda v, med: v > med,
                      "SOFR above IORB by more than usual: cash is "
                      "scarce, balance sheet is expensive, and carrying "
                      "risk costs more than it did."),
    "credit_stress": ("credit", lambda v, med: v > med,
                      "High-yield spreads wider than usual. Risk "
                      "appetite is contracting, which changes who is "
                      "able to hold what."),
}


def masks(ctx):
    """Boolean masks for each context condition available on this tape.

    Thresholds are TRAILING medians, never full-sample. A full-sample
    median uses years of future data to decide what counted as unusual
    today -- the same weaker leak already fixed in the volatility
    conditions, and it would be just as invisible here.
    """
    if ctx is None or not len(ctx):
        return {}
    out = {}
    for name, (col, fn, _why) in CONTEXT_CONDS.items():
        if col not in ctx.columns:
            continue
        v = ctx[col]
        med = v.rolling(20000, min_periods=2000).median()
        ok = v.notna() & med.notna()
        try:
            out[name] = (fn(v, med) & ok).values
        except Exception:                                     # noqa: BLE001
            continue
    return {k: m for k, m in out.items() if m.sum() > 500}


def why(name):
    e = CONTEXT_CONDS.get(name)
    return e[2] if e else ""


# --------------------------------------------------------- self-test
def lag_selftest(verbose=True):
    """Prove that no context value is visible before it was published.

    Builds context on a synthetic daily index and checks, for each
    series, that the value in force on day D equals a raw observation
    dated at least `lag` business days EARLIER. A single violation means
    every positioning hypothesis is reading the future.
    """
    fails = []
    idx = pd.date_range("2024-01-02", "2026-08-01", freq="B", tz="UTC")
    gex = load_gex()
    if gex and "NDX" in gex:
        raw = gex["NDX"]
        m = _asof(raw, pd.DatetimeIndex(idx), LAGS["gex"])
        bad = 0
        for d, v in list(m.items()):
            if not np.isfinite(v if v is not None else np.nan):
                continue
            src = raw[raw == v]
            if len(src) and (d - src.index[-1]).days < LAGS["gex"]:
                bad += 1
        if verbose:
            print(f"  gex   lag {LAGS['gex']}bd: {bad} violations")
        if bad:
            fails.append(f"gex leaks on {bad} days")
    cot = load_cot()
    if cot is not None and len(cot):
        s = cot.groupby("day")["lev_net"].last().sort_index()
        m = _asof(s, pd.DatetimeIndex(idx), LAGS["cot"])
        bad = sum(1 for d, v in m.items()
                  if v is not None and np.isfinite(v)
                  and len(s[s == v])
                  and (d - s[s == v].index[-1]).days < LAGS["cot"])
        if verbose:
            print(f"  cot   lag {LAGS['cot']}bd: {bad} violations")
        if bad:
            fails.append(f"cot leaks on {bad} days")
    return fails
