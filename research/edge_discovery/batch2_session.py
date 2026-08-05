"""Batch 2: session-structure hypotheses on NQ 1-min.

Families (each with an economic story about WHO creates the flow):
  GAP   overnight gap fade/continuation at RTH open (overnight inventory unwind)
  ORB   opening-range breakout + breakout FAILURE (stop hunting around OR)
  IMOM  intraday momentum: first-30-min return -> last-hour continuation
        (documented late-day rebalancing/gamma flows)
  ONP   overnight risk premium: hold long through the Globex night
        (compensation for holding risk when arbitrageurs are away)
  LUNCH lunch-hour reversion of the morning move (liquidity trough)
  PWR   power-hour continuation of the day's direction (MOC rebalancing)
  ECON  8:30/10:00 economic-release spike continuation (slow diffusion of news)
  DRIVE opening drive continuation (initiative auction imbalance)
  STL   settlement-to-reopen behavior (16:00-17:00 vs 18:00+)
"""
import sys, json, warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import harness as H

df = pd.read_parquet(H.CACHE / "nq_feat.parquet")
lv = pd.read_parquet(H.CACHE / "nq_levels.parquet")
arrays = H.get_arrays(df)

# day-level ATR (14-day EMA of daily RTH range) for gap normalization
day_rng = (lv["rth_high"] - lv["rth_low"]).ewm(span=14, min_periods=5).mean().shift()
lv["datr"] = day_rng

tday = df["tday"]
hhmm = df["hhmm"]
lv_on_bars = lv.reindex(tday.values)
prev_rth_close = pd.Series(lv_on_bars["prev_rth_close"].values, index=df.index)
datr = pd.Series(lv_on_bars["datr"].values, index=df.index)
on_high = pd.Series(lv_on_bars["on_high"].values, index=df.index)
on_low = pd.Series(lv_on_bars["on_low"].values, index=df.index)

results = {}


def run(name, sig, d, es):
    res = H.simulate(df, sig, d, es, "nq", name, arrays=arrays)
    s_is, s_oos = H.is_oos(res)
    results[name] = {"is": s_is, "oos": s_oos}
    return res


# ------------------------------------------------------------------ #
# GAP: at 9:30, gap = 9:29 close vs prior RTH close, normalized by day ATR
# ------------------------------------------------------------------ #
at_929 = hhmm == 929
gap = (df["close"] - prev_rth_close) / datr
for thr in (0.25, 0.5, 1.0):
    for ek, es in {
        "t30": H.ExitSpec(max_hold=30),
        "t60": H.ExitSpec(max_hold=60),
        "eod": H.ExitSpec(max_hold=500, eod_hhmm=1555),
        "s1t1": H.ExitSpec(stop_atr=8, target_atr=8, max_hold=390, eod_hhmm=1555),
    }.items():
        run(f"GAP_up{thr}_fade_S_{ek}", (at_929 & (gap > thr)), -1, es)
        run(f"GAP_dn{thr}_fade_L_{ek}", (at_929 & (gap < -thr)), +1, es)
        run(f"GAP_up{thr}_cont_L_{ek}", (at_929 & (gap > thr)), +1, es)
        run(f"GAP_dn{thr}_cont_S_{ek}", (at_929 & (gap < -thr)), -1, es)

# ------------------------------------------------------------------ #
# ORB: opening range = 9:30-9:44; breakout after 9:45, EOD flat 15:55
# ------------------------------------------------------------------ #
or_high = df["high"].where((hhmm >= 930) & (hhmm <= 944)).groupby(tday).cummax().groupby(tday).ffill()
or_low = df["low"].where((hhmm >= 930) & (hhmm <= 944)).groupby(tday).cummin().groupby(tday).ffill()
or_done = hhmm >= 945
brk_up = or_done & (df["close"] > or_high) & (df["close"].shift() <= or_high.shift())
brk_dn = or_done & (df["close"] < or_low) & (df["close"].shift() >= or_low.shift())
in_am = hhmm < 1200
for ek, es in {
    "eod": H.ExitSpec(max_hold=500, eod_hhmm=1555),
    "trail3": H.ExitSpec(trail_atr=3, max_hold=500, eod_hhmm=1555),
    "s2eod": H.ExitSpec(stop_atr=4, max_hold=500, eod_hhmm=1555),
    "t60": H.ExitSpec(max_hold=60),
}.items():
    run(f"ORB_up_L_{ek}", brk_up & in_am, +1, es)
    run(f"ORB_dn_S_{ek}", brk_dn & in_am, -1, es)

# ORB failure: broke OR high then closed back inside -> fade to OR low side
fail_up = or_done & in_am & (df["high"].groupby(tday).cummax() > or_high) & \
          (df["close"] < or_high) & (df["close"].shift() >= or_high.shift())
fail_dn = or_done & in_am & (df["low"].groupby(tday).cummin() < or_low) & \
          (df["close"] > or_low) & (df["close"].shift() <= or_low.shift())
for ek, es in {
    "t60": H.ExitSpec(max_hold=60),
    "eod": H.ExitSpec(max_hold=500, eod_hhmm=1555),
    "s2t3": H.ExitSpec(stop_atr=2, target_atr=3, max_hold=240, eod_hhmm=1555),
}.items():
    run(f"ORBFAIL_up_S_{ek}", fail_up, -1, es)
    run(f"ORBFAIL_dn_L_{ek}", fail_dn, +1, es)

# ------------------------------------------------------------------ #
# IMOM: first-30-min return sign -> trade 15:00-15:59 in same direction
# ------------------------------------------------------------------ #
ret_930_1000 = pd.Series(np.nan, index=df.index)
c1000 = df["close"].where(hhmm == 959).groupby(tday).transform("max")
o930 = df["open"].where(hhmm == 930).groupby(tday).transform("max")
fm = (c1000 - o930) / datr
at_1459 = hhmm == 1459
es_pwr = H.ExitSpec(max_hold=70, eod_hhmm=1559)
for thr in (0.0, 0.25):
    run(f"IMOM_fm{thr}_L", at_1459 & (fm > thr), +1, es_pwr)
    run(f"IMOM_fm{thr}_S", at_1459 & (fm < -thr), -1, es_pwr)
# reversal version
run("IMOM_rev_S", at_1459 & (fm > 0.25), -1, es_pwr)
run("IMOM_rev_L", at_1459 & (fm < -0.25), +1, es_pwr)
# day-so-far (9:30->14:59) version
day_ret = (df["close"] - o930) / datr
run("PWR_day_L", at_1459 & (day_ret > 0.25), +1, es_pwr)
run("PWR_day_S", at_1459 & (day_ret < -0.25), -1, es_pwr)
run("PWRrev_day_S", at_1459 & (day_ret > 0.25), -1, es_pwr)
run("PWRrev_day_L", at_1459 & (day_ret < -0.25), +1, es_pwr)

# ------------------------------------------------------------------ #
# ONP: overnight premium — long at 17:59/20:00/22:00, exit 9:29 (or 9:25)
# ------------------------------------------------------------------ #
for t0 in (1759, 2000, 2200, 300):
    at_t0 = hhmm == t0
    run(f"ONP_L_{t0}", at_t0, +1, H.ExitSpec(max_hold=1200, eod_hhmm=929))
    run(f"ONP_S_{t0}", at_t0, -1, H.ExitSpec(max_hold=1200, eod_hhmm=929))
# vol-filtered: only when trailing 5-day realized daily range is modest
calm = (datr / df["close"]) < (datr / df["close"]).rolling(20000).median()
run("ONP_L_1759_calm", (hhmm == 1759) & calm, +1, H.ExitSpec(max_hold=1200, eod_hhmm=929))
run("ONP_L_1759_storm", (hhmm == 1759) & ~calm, +1, H.ExitSpec(max_hold=1200, eod_hhmm=929))

# ------------------------------------------------------------------ #
# LUNCH: fade the 10:00->11:30 move during 11:30-13:30
# ------------------------------------------------------------------ #
c1130 = df["close"].where(hhmm == 1129).groupby(tday).transform("max")
morn = (c1130 - c1000) / datr
at_1129 = hhmm == 1129
es_lunch = H.ExitSpec(max_hold=120, eod_hhmm=1330)
run("LUNCH_fade_S", at_1129 & (morn > 0.3), -1, es_lunch)
run("LUNCH_fade_L", at_1129 & (morn < -0.3), +1, es_lunch)
run("LUNCH_cont_L", at_1129 & (morn > 0.3), +1, es_lunch)
run("LUNCH_cont_S", at_1129 & (morn < -0.3), -1, es_lunch)

# ------------------------------------------------------------------ #
# ECON: 8:30 release spike -> continuation to 9:25 (and 10:00 releases)
# ------------------------------------------------------------------ #
for t_sig, t_exit, tag in ((832, 925, "830"), (1002, 1100, "1000")):
    at_sig = hhmm == t_sig
    spike = (df["close"] - df["close"].shift(3)) / df["atr"].clip(lower=1e-9)
    big_up = at_sig & (spike > 3)
    big_dn = at_sig & (spike < -3)
    es_econ = H.ExitSpec(max_hold=90, eod_hhmm=t_exit)
    run(f"ECON{tag}_cont_L", big_up, +1, es_econ)
    run(f"ECON{tag}_cont_S", big_dn, -1, es_econ)
    run(f"ECON{tag}_fade_S", big_up, -1, es_econ)
    run(f"ECON{tag}_fade_L", big_dn, +1, es_econ)

# ------------------------------------------------------------------ #
# DRIVE: first 5 RTH minutes direction -> continue to 10:00
# ------------------------------------------------------------------ #
c935 = df["close"].where(hhmm == 934).groupby(tday).transform("max")
drive = (c935 - o930) / datr
at_934 = hhmm == 934
es_drive = H.ExitSpec(max_hold=90, eod_hhmm=1000)
for thr in (0.1, 0.25):
    run(f"DRIVE{thr}_L", at_934 & (drive > thr), +1, es_drive)
    run(f"DRIVE{thr}_S", at_934 & (drive < -thr), -1, es_drive)
    run(f"DRIVErev{thr}_S", at_934 & (drive > thr), -1, es_drive)
    run(f"DRIVErev{thr}_L", at_934 & (drive < -thr), +1, es_drive)

# ------------------------------------------------------------------ #
# STL: 16:00-16:59 move vs Globex reopen (fade the thin-tape drift)
# ------------------------------------------------------------------ #
c1659 = df["close"].where(hhmm == 1659).groupby(tday).transform("max")
c1600 = df["close"].where(hhmm == 1600).groupby(tday).transform("max")
post_stl = (c1659 - c1600) / df["atr"].clip(lower=1e-9)
at_1659 = hhmm == 1659
es_stl = H.ExitSpec(max_hold=120)
run("STL_fade_S", at_1659 & (post_stl > 2), -1, es_stl)
run("STL_fade_L", at_1659 & (post_stl < -2), +1, es_stl)
run("STL_cont_L", at_1659 & (post_stl > 2), +1, es_stl)
run("STL_cont_S", at_1659 & (post_stl < -2), -1, es_stl)

# ------------------------------------------------------------------ #
out = Path(H.CACHE) / "batch2_results.json"
out.write_text(json.dumps(results, default=str))
print(f"saved {len(results)} variants")

rows = []
for k, v in results.items():
    s, o = v["is"], v["oos"]
    if s.get("n", 0) > 60 and s.get("avg_net_usd", -9) > 0 and s.get("t_stat", 0) > 1.5:
        rows.append((s["t_stat"], k, s, o))
rows.sort(reverse=True)
print(f"\n{len(rows)} IS candidates (net>0, t>1.5, n>60):")
for t, k, s, o in rows:
    print("IS>> " + H.fmt(k, s))
    print("OOS> " + H.fmt(k, o))
