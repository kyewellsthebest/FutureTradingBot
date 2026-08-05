"""Destruction testing for surviving candidates.

Candidates:
  GAP    buy 9:30 when overnight gap < -k * dayATR (k in grid), intraday hold
  PWR    short 15:00 when day return (9:30->14:59) < -k * dayATR, exit 15:59
  DRIVE  9:35 entry in direction of 9:30-9:34 drive > k * dayATR, exit 10:00
  BIGDN  buy next RTH open->close after a big down day (ret < -1 dayATR)

Battery per candidate:
  1. parameter-perturbation grid (needs a positive plateau, not a spike)
  2. per-year P&L
  3. cost stress  ($4.40 base / $6.40 / $8.40 round trip)
  4. entry delay +1 / +3 minutes
  5. ES confirmation (same rule on ES 2023-12..2026-02, point=$50)
  6. Monte Carlo: bootstrap weekly P&L -> drawdown / worst-week distribution
"""
import sys, json, warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import harness as H


def load_sym(sym):
    df = pd.read_parquet(H.CACHE / f"{sym}_feat.parquet")
    lv = pd.read_parquet(H.CACHE / f"{sym}_levels.parquet")
    lv["datr"] = (lv["rth_high"] - lv["rth_low"]).ewm(span=14, min_periods=5).mean().shift()
    lv["ret_norm"] = (lv["rth_close"] - lv["rth_open"]) / lv["datr"]
    ctx = {}
    ctx["df"], ctx["lv"] = df, lv
    ctx["arrays"] = H.get_arrays(df)
    tday = df["tday"]
    lvb = lv.reindex(tday.values)
    ctx["prev_rth_close"] = pd.Series(lvb["prev_rth_close"].values, index=df.index)
    ctx["datr"] = pd.Series(lvb["datr"].values, index=df.index)
    ctx["big_dn_prev"] = pd.Series((lv["ret_norm"].shift() < -1.0).reindex(tday.values).values,
                                   index=df.index).fillna(False).astype(bool)
    ctx["tday"], ctx["hhmm"] = tday, df["hhmm"]
    o930 = df["open"].where(df["hhmm"] == 930).groupby(tday).transform("max")
    ctx["o930"] = o930
    return ctx


def sig_gap(ctx, k):
    gap = (ctx["df"]["close"] - ctx["prev_rth_close"]) / ctx["datr"]
    return (ctx["hhmm"] == 929) & (gap < -k)

def sig_pwr(ctx, k, at=1459):
    day_ret = (ctx["df"]["close"] - ctx["o930"]) / ctx["datr"]
    return (ctx["hhmm"] == at) & (day_ret < -k)

def sig_drive(ctx, k, at=934):
    cnow = ctx["df"]["close"].where(ctx["hhmm"] == at).groupby(ctx["tday"]).transform("max")
    drive = (cnow - ctx["o930"]) / ctx["datr"]
    up = (ctx["hhmm"] == at) & (drive > k)
    dn = (ctx["hhmm"] == at) & (drive < -k)
    return up, dn

def sig_bigdn(ctx):
    return (ctx["hhmm"] == 929) & ctx["big_dn_prev"]


def report(tag, res, cost=H.COST_RT):
    import harness as HH
    old = HH.COST_RT
    HH.COST_RT = cost
    s_is, s_oos = res.stats(end=H.IS_END), res.stats(start=H.OOS_START)
    HH.COST_RT = old
    print(f"  IS>> {H.fmt(tag, s_is)}")
    print(f"  OOS> {H.fmt(tag, s_oos)}")
    return s_is, s_oos


def mc_weekly(res, n=5000, seed=7):
    t = res.trades
    net = t["pnl_pts"] * H.POINT_VALUE[res.symbol] - H.COST_RT
    wk = net.groupby(t["exit_time"].dt.tz_localize(None).dt.to_period("W")).sum().values
    if len(wk) < 30:
        return None
    rng = np.random.default_rng(seed)
    dds, worsts = [], []
    for _ in range(n):
        path = rng.choice(wk, size=len(wk), replace=True).cumsum()
        dd = (path - np.maximum.accumulate(path)).min()
        dds.append(dd)
        worsts.append(path.min() if len(path) else 0)
    return {"med_maxDD": float(np.median(dds)), "p95_maxDD": float(np.percentile(dds, 5)),
            "weeks": len(wk), "wk_mean": float(wk.mean()), "wk_std": float(wk.std())}


def delay(sig, mins):
    return sig.shift(mins).fillna(False)


nq = load_sym("nq")
es_ = load_sym("es")

print("=" * 100)
print("CANDIDATE 1: GAP-DOWN FADE (long big down-gaps at 9:30)")
print("=" * 100)
EXITS = {"s8t8_eod": H.ExitSpec(stop_atr=8, target_atr=8, max_hold=390, eod_hhmm=1555),
         "t60": H.ExitSpec(max_hold=60),
         "eod": H.ExitSpec(max_hold=390, eod_hhmm=1555)}
for k in (0.15, 0.25, 0.35, 0.5, 0.75):
    for ek, e in EXITS.items():
        r = H.simulate(nq["df"], sig_gap(nq, k), +1, e, "nq", arrays=nq["arrays"])
        report(f"GAP k={k} {ek}", r)
print("-- cost stress on k=0.25 s8t8_eod:")
r = H.simulate(nq["df"], sig_gap(nq, 0.25), +1, EXITS["s8t8_eod"], "nq", arrays=nq["arrays"])
for c in (4.40, 6.40, 8.40):
    report(f"GAP cost=${c}", r, cost=c)
print("-- entry delay:")
for dmin in (1, 3):
    rd = H.simulate(nq["df"], delay(sig_gap(nq, 0.25), dmin), +1, EXITS["s8t8_eod"], "nq", arrays=nq["arrays"])
    report(f"GAP delay+{dmin}m", rd)
print("-- ES confirmation (2023-12..2026-02):")
res_es = H.simulate(es_["df"], sig_gap(es_, 0.25), +1, EXITS["s8t8_eod"], "es", arrays=es_["arrays"])
print("  ALL> " + H.fmt("GAP es k=0.25", res_es.stats()))
res_es2 = H.simulate(es_["df"], sig_gap(es_, 0.15), +1, EXITS["s8t8_eod"], "es", arrays=es_["arrays"])
print("  ALL> " + H.fmt("GAP es k=0.15", res_es2.stats()))
print("-- MC:", mc_weekly(r))
print("-- yearly:", r.stats()["yearly"])

print("=" * 100)
print("CANDIDATE 2: PWR_day_S (short weak days 15:00->16:00)")
print("=" * 100)
es_pwr = H.ExitSpec(max_hold=70, eod_hhmm=1559)
for k in (0.1, 0.25, 0.4, 0.6):
    r = H.simulate(nq["df"], sig_pwr(nq, k), -1, es_pwr, "nq", arrays=nq["arrays"])
    report(f"PWR k={k}", r)
for at in (1429, 1444, 1514):
    r = H.simulate(nq["df"], sig_pwr(nq, 0.25, at=at), -1, es_pwr, "nq", arrays=nq["arrays"])
    report(f"PWR at={at}", r)
r = H.simulate(nq["df"], sig_pwr(nq, 0.25), -1, es_pwr, "nq", arrays=nq["arrays"])
for c in (6.40, 8.40):
    report(f"PWR cost=${c}", r, cost=c)
for dmin in (1, 3):
    rd = H.simulate(nq["df"], delay(sig_pwr(nq, 0.25), dmin), -1, es_pwr, "nq", arrays=nq["arrays"])
    report(f"PWR delay+{dmin}m", rd)
res_es = H.simulate(es_["df"], sig_pwr(es_, 0.25), -1, es_pwr, "es", arrays=es_["arrays"])
print("  ALL> " + H.fmt("PWR es", res_es.stats()))
print("-- MC:", mc_weekly(r))
print("-- yearly:", r.stats()["yearly"])

print("=" * 100)
print("CANDIDATE 3: DRIVE (9:30-9:34 drive continuation to 10:00, both sides)")
print("=" * 100)
es_drv = H.ExitSpec(max_hold=90, eod_hhmm=1000)
for k in (0.05, 0.1, 0.15, 0.25):
    up, dn = sig_drive(nq, k)
    ru = H.simulate(nq["df"], up, +1, es_drv, "nq", arrays=nq["arrays"])
    rd = H.simulate(nq["df"], dn, -1, es_drv, "nq", arrays=nq["arrays"])
    report(f"DRIVE_L k={k}", ru)
    report(f"DRIVE_S k={k}", rd)
up, dn = sig_drive(nq, 0.1)
for c in (6.40, 8.40):
    ru = H.simulate(nq["df"], up, +1, es_drv, "nq", arrays=nq["arrays"])
    report(f"DRIVE_L cost=${c}", ru, cost=c)
for dmin in (1, 3):
    rud = H.simulate(nq["df"], delay(up, dmin), +1, es_drv, "nq", arrays=nq["arrays"])
    report(f"DRIVE_L delay+{dmin}m", rud)
upe, dne = sig_drive(es_, 0.1)
print("  ALL> " + H.fmt("DRIVE_L es", H.simulate(es_["df"], upe, +1, es_drv, "es", arrays=es_["arrays"]).stats()))
print("  ALL> " + H.fmt("DRIVE_S es", H.simulate(es_["df"], dne, -1, es_drv, "es", arrays=es_["arrays"]).stats()))
print("-- alt window 9:39 entry exit 10:15:")
up9, dn9 = sig_drive(nq, 0.1, at=939)
report("DRIVE_L 939", H.simulate(nq["df"], up9, +1, H.ExitSpec(max_hold=90, eod_hhmm=1015), "nq", arrays=nq["arrays"]))
report("DRIVE_S 939", H.simulate(nq["df"], dn9, -1, H.ExitSpec(max_hold=90, eod_hhmm=1015), "nq", arrays=nq["arrays"]))

print("=" * 100)
print("CANDIDATE 4: BIGDN next-day long (open->close after ret < -1 dayATR day)")
print("=" * 100)
eod = H.ExitSpec(max_hold=390, eod_hhmm=1555)
r = H.simulate(nq["df"], sig_bigdn(nq), +1, eod, "nq", arrays=nq["arrays"])
report("BIGDN", r)
print("-- yearly:", r.stats()["yearly"])
res_es = H.simulate(es_["df"], sig_bigdn(es_), +1, eod, "es", arrays=es_["arrays"])
print("  ALL> " + H.fmt("BIGDN es", res_es.stats()))
