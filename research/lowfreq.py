"""Low-frequency families. Four mechanisms, none ever tested here.

THE GAP, and it is a fair criticism of every search in this repo. 26
billion configurations were spent between 15 seconds and 50 minutes.
The lowest-frequency thing ever tried was a 3-day hold. Nobody tested
the CALENDAR, nobody tested POSITIONING, nobody separated the overnight
session from the day session as a directional bet, and nobody used the
nine years of CFTC data sitting on disk. Those are not exotic ideas --
they are the oldest documented effects in futures, and they all trade
about once a week.

FAMILY A -- CALENDAR. Day of week, turn of month, month of year. The
turn-of-month effect (buy the last day or two of the month, exit a few
days in) is one of the most replicated anomalies in finance and fires
twelve times a year. Never run here.

FAMILY B -- SESSION. In equities most of the total return historically
accrues OVERNIGHT, not during the cash session; the day session has
been roughly flat or negative for decades. If that holds in the index
futures, then "buy the close, sell the open" is a strategy with one
trade a day, no intraday risk, and a mechanism behind it. This repo
has measured overnight DISPERSION and overnight SPREAD, but never
overnight RETURN.

FAMILY C -- POSITIONING. data/research_data/cftc holds 2018-2026 of
weekly Commitments of Traders: dealers, asset managers and leveraged
money, long and short. When leveraged money is at a positioning
extreme, the crowd is on one side and the fuel for further movement is
spent. That is the classic contrarian signal, it updates weekly, and
the file has been sitting unread the whole time.

FAMILY D -- VOLATILITY REGIME. Not a signal on its own, a filter: does
anything above work only when volatility is low, or only when high.

CONTROLS, per family, because each needs a different null:

  calendar     the same bracket on ALL days -- what any day pays
  session      the opposite session, and the all-day baseline
  positioning  the COT series SHIFTED, which keeps its shape and
               autocorrelation but destroys its alignment with price
  everything   MDE printed whether or not something is found

Costs are the measured $1.99 a round turn throughout. Every family
trades between 0.2 and 5 times a week, so cost is small by
construction -- which is the entire point of looking here.
"""
from __future__ import annotations

import glob
import json
import math
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DROP = {"SI"}
COST = 1.99
RTH_FROM, RTH_TO = 13, 20
SPEC = {
    "NQ": 2.0, "ES": 5.0, "YM": 0.50, "RTY": 5.0, "GC": 10.0, "HG": 2500.0,
    "CL": 100.0, "NG": 2500.0, "HO": 42000.0, "RB": 42000.0, "ZB": 1000.0,
    "ZN": 1000.0, "ZF": 1000.0, "ZT": 2000.0, "6E": 12500.0, "6A": 10000.0,
    "6B": 6250.0, "6J": 6250000.0, "ZC": 10.0, "ZW": 10.0, "ZS": 10.0,
    "ETH": 0.10, "MBT": 0.10,
}
# COT market name -> our symbol. Only the ones we can actually trade.
COT_MAP = {
    "NASDAQ-100 STOCK INDEX (MINI)": "NQ",
    "E-MINI S&P 500": "ES",
    "DOW JONES INDUSTRIAL AVG- x $5": "YM",
    "RUSSELL E-MINI": "RTY",
    "UST 10Y NOTE": "ZN",
    "UST BOND": "ZB",
    "UST 5Y NOTE": "ZF",
    "UST 2Y NOTE": "ZT",
}


def load_5min(sym):
    p = os.path.join(ROOT, "data", "polygon", f"{sym}_5min.csv")
    return pd.read_csv(p, parse_dates=["ts"],
                       usecols=["ts", "open", "high", "low", "close"]
                       ).set_index("ts").sort_index()


def stat(pnl, weeks, label, n_baseline_sd=None):
    pnl = np.asarray(pnl, dtype=float)
    pnl = pnl[np.isfinite(pnl)]
    if len(pnl) < 30:
        return None
    sd = float(pnl.std(ddof=1))
    se = sd / math.sqrt(len(pnl))
    eq = np.cumsum(pnl)
    dd = float((np.maximum.accumulate(eq) - eq).max())
    return {"name": label, "trades": len(pnl),
            "trades_per_week": round(len(pnl) / weeks, 2),
            "per_trade": round(float(pnl.mean()), 2),
            "t": round(float(pnl.mean() / se), 2) if se > 0 else 0.0,
            "net_per_week": round(float(pnl.sum()) / weeks, 2),
            "mde_per_week": round(3.0 * se * len(pnl) / weeks, 2),
            "win_rate": round(100.0 * float((pnl > 0).mean()), 1),
            "max_drawdown": round(dd, 2)}


def family_session(sym, d, weeks, out):
    """Overnight return vs day-session return, one trade a day."""
    pv = SPEC[sym]
    h = pd.DatetimeIndex(d.index).hour
    rth = (h >= RTH_FROM) & (h < RTH_TO)
    day = pd.DatetimeIndex(d.index).normalize()
    fr = pd.DataFrame({"c": d["close"].values, "rth": rth, "day": day},
                      index=d.index)
    g = fr[fr.rth].groupby("day")["c"]
    op, cl = g.first(), g.last()
    common = op.index.intersection(cl.index)
    op, cl = op[common], cl[common]
    intraday = (cl - op).values * pv - COST
    overnight = (op.shift(-1) - cl).values[:-1] * pv - COST
    for nm, series in (("session_intraday_long", intraday),
                       ("session_overnight_long", overnight),
                       ("session_intraday_short", -intraday - 2 * COST),
                       ("session_overnight_short", -overnight - 2 * COST)):
        s = stat(series, weeks, nm)
        if s:
            s.update(market=sym, family="session")
            out.append(s)


def family_calendar(sym, d, weeks, out):
    """Day of week, turn of month. One decision per day, held one day."""
    pv = SPEC[sym]
    dly = d["close"].resample("1D").last().dropna()
    r = (dly.diff().shift(-1)).values * pv           # next-day move
    idx = pd.DatetimeIndex(dly.index)
    base = stat(r - COST, weeks, "calendar_all_days_long")
    if base:
        base.update(market=sym, family="calendar")
        out.append(base)
    for dow, nm in enumerate(["mon", "tue", "wed", "thu", "fri"]):
        m = idx.dayofweek == dow
        s = stat(r[m] - COST, weeks, f"calendar_{nm}_long")
        if s:
            s.update(market=sym, family="calendar")
            out.append(s)
    # turn of month: last 2 trading days and first 3 of the next
    dom = idx.day
    eom = dom >= 28
    som = dom <= 3
    for m, nm in ((eom, "eom"), (som, "som"), (eom | som, "turn_of_month")):
        s = stat(r[m] - COST, weeks, f"calendar_{nm}_long")
        if s:
            s.update(market=sym, family="calendar")
            out.append(s)


def load_cot():
    frames = []
    for p in sorted(glob.glob(os.path.join(ROOT, "data", "research_data",
                                           "cftc", "FinCom_*.txt"))):
        try:
            f = pd.read_csv(p, low_memory=False)
        except Exception:
            continue
        frames.append(f)
    if not frames:
        return None
    c = pd.concat(frames, ignore_index=True)
    c["mkt"] = c["Market_and_Exchange_Names"].astype(str)
    c["date"] = pd.to_datetime(c["Report_Date_as_YYYY-MM-DD"], errors="coerce")
    return c.dropna(subset=["date"])


def family_cot(sym, d, weeks, cot, out):
    """Leveraged-money positioning extremes, weekly, held one week."""
    if cot is None:
        return
    names = [k for k, v in COT_MAP.items() if v == sym]
    if not names:
        return
    sub = cot[cot["mkt"].str.upper().str.contains(names[0].upper(), regex=False)]
    if len(sub) < 60:
        return
    sub = sub.sort_values("date")
    net = (sub["Lev_Money_Positions_Long_All"].astype(float)
           - sub["Lev_Money_Positions_Short_All"].astype(float))
    oi = sub["Open_Interest_All"].astype(float).replace(0, np.nan)
    frac = (net / oi).values
    # COT report dates are tz-naive; the price index is UTC. Comparing
    # them raises rather than silently misaligning, which is the good
    # failure mode -- but it still has to be handled.
    dates = pd.DatetimeIndex(sub["date"].values).tz_localize("UTC")
    z = pd.Series(frac).rolling(104, min_periods=52)
    zz = ((pd.Series(frac) - z.mean()) / z.std()).values
    pv = SPEC[sym]
    dly = d["close"].resample("1D").last().ffill()
    fwd = []
    for i, dt in enumerate(dates):
        a = dly.index.searchsorted(dt)
        b = dly.index.searchsorted(dt + pd.Timedelta(days=7))
        if a >= len(dly) or b >= len(dly) or a == b:
            fwd.append(np.nan)
        else:
            fwd.append((dly.iloc[b] - dly.iloc[a]) * pv)
    fwd = np.array(fwd)
    for thr, nm in ((1.0, "z1"), (1.5, "z15")):
        # CONTRARIAN: crowd very long -> we go short, and vice versa
        m = np.isfinite(zz) & np.isfinite(fwd) & (np.abs(zz) >= thr)
        if m.sum() < 30:
            continue
        pnl = -np.sign(zz[m]) * fwd[m] - COST
        s = stat(pnl, weeks, f"cot_contrarian_{nm}")
        if s:
            s.update(market=sym, family="cot")
            out.append(s)
        s2 = stat(np.sign(zz[m]) * fwd[m] - COST, weeks, f"cot_follow_{nm}")
        if s2:
            s2.update(market=sym, family="cot")
            out.append(s2)
        # CONTROL: shift the COT series a year -- same shape, wrong dates
        sh = np.roll(zz, 52)
        m2 = np.isfinite(sh) & np.isfinite(fwd) & (np.abs(sh) >= thr)
        if m2.sum() >= 30:
            s3 = stat(-np.sign(sh[m2]) * fwd[m2] - COST, weeks,
                      f"cot_SHIFTED_{nm}")
            if s3:
                s3.update(market=sym, family="cot_control")
                out.append(s3)


def main():
    print(__doc__, flush=True)
    print("=" * 78, flush=True)
    syms = [os.path.basename(p).replace("_5min.csv", "")
            for p in sorted(glob.glob(os.path.join(ROOT, "data", "polygon",
                                                   "*_5min.csv")))]
    syms = [s for s in syms if s not in DROP and s in SPEC]
    cot = load_cot()
    print(f"COT rows: {0 if cot is None else len(cot):,}   markets: {len(syms)}\n")
    out = []
    for sym in syms:
        d = load_5min(sym)
        weeks = (d.index[-1] - d.index[0]).days / 7.0
        family_session(sym, d, weeks, out)
        family_calendar(sym, d, weeks, out)
        family_cot(sym, d, weeks, cot, out)
    n = len([r for r in out if r["family"] != "cot_control"])
    bar = max(3.0, math.sqrt(2 * math.log(max(n, 2))) + 0.8)
    print(f"{n:,} configurations -> bar {bar:.2f} sigma\n")

    real = [r for r in out if r["family"] != "cot_control"]
    real.sort(key=lambda r: -abs(r["t"]))
    print(f"{'mkt':>5} {'family':>9} {'config':>26} {'trades':>7} {'/wk':>5} "
          f"{'$/trade':>8} {'t':>6} {'$/wk':>8} {'win%':>6}")
    for r in real[:22]:
        print(f"{r['market']:>5} {r['family']:>9} {r['name']:>26} "
              f"{r['trades']:>7,} {r['trades_per_week']:>5.1f} "
              f"{r['per_trade']:>8,.1f} {r['t']:>6.2f} "
              f"{r['net_per_week']:>8,.0f} {r['win_rate']:>6.1f}")

    surv = [r for r in real if abs(r["t"]) >= bar and r["net_per_week"] > 0
            and r["net_per_week"] > r["mde_per_week"]]
    print(f"\n{len(surv)} clear |t| >= {bar:.2f}, positive, and above own MDE")
    for r in surv[:12]:
        print(f"   {r['market']} {r['name']}: ${r['net_per_week']:,.0f}/wk, "
              f"t={r['t']}, {r['trades_per_week']:.1f}/wk, "
              f"win {r['win_rate']}%, DD ${r['max_drawdown']:,.0f}")
    ctl = [r for r in out if r["family"] == "cot_control"]
    if ctl:
        print(f"\nCOT shifted-control best |t|: "
              f"{max(abs(r['t']) for r in ctl):.2f}  "
              f"(real COT best: "
              f"{max((abs(r['t']) for r in real if r['family']=='cot'), default=0):.2f})")
    json.dump({"n_configs": n, "bar": round(bar, 2), "rows": out,
               "survivors": surv},
              open(os.path.join(ROOT, "research", "LOWFREQ.json"), "w"),
              indent=1)
    print("\nwrote research/LOWFREQ.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
