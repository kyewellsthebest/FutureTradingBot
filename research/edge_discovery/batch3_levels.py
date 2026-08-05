"""Batch 3: level-based + cross-market hypotheses.

Families:
  SWEEP  stop-run reversal: RTH takes out overnight/prior-day extreme by a
         hair then closes back inside -> fade (stops were the liquidity)
  PDHL   prior-day high/low first-touch rejection vs breakout acceptance
  RND    round-number behavior (NQ 100-pt levels)
  MAG    settlement magnet: late-day pull toward prior settlement
  XLEAD  ES -> NQ 1-min lead-lag (2023-12 .. 2025-12 both markets)
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
tday, hhmm = df["tday"], df["hhmm"]

lvb = lv.reindex(tday.values)
on_high = pd.Series(lvb["on_high"].values, index=df.index)
on_low = pd.Series(lvb["on_low"].values, index=df.index)
pdh = pd.Series(lvb["prev_rth_high"].values, index=df.index)
pdl = pd.Series(lvb["prev_rth_low"].values, index=df.index)
pdc = pd.Series(lvb["prev_rth_close"].values, index=df.index)
day_rng = (lv["rth_high"] - lv["rth_low"]).ewm(span=14, min_periods=5).mean().shift()
datr = pd.Series(day_rng.reindex(tday.values).values, index=df.index)

results = {}
def run(name, sig, d, es):
    r = H.simulate(df, sig, d, es, "nq", name, arrays=arrays)
    s_is, s_oos = H.is_oos(r)
    results[name] = {"is": s_is, "oos": s_oos}
    return r

rth = df["rth"]
cummax_rth = df["high"].where(rth).groupby(tday).cummax().groupby(tday).ffill()
cummin_rth = df["low"].where(rth).groupby(tday).cummin().groupby(tday).ffill()

# ------------------------------------------------------------------ #
# SWEEP: first break of ON low intraday, close back above -> long
# ------------------------------------------------------------------ #
for lvl_name, lvl in (("onlow", on_low), ("pdl", pdl)):
    swept = rth & (df["low"] < lvl) & (cummin_rth.shift() >= lvl)   # first bar to breach
    reclaimed = swept & (df["close"] > lvl)
    # also: breach then reclaim within 5 bars
    breach = rth & (cummin_rth < lvl) & (cummin_rth.shift(5) >= lvl)
    reclaim5 = breach & (df["close"] > lvl) & (df["close"].shift() <= lvl)
    for ek, es in {"t30": H.ExitSpec(max_hold=30),
                   "t90": H.ExitSpec(max_hold=90, eod_hhmm=1555),
                   "s1.5t3": H.ExitSpec(stop_atr=1.5, target_atr=3, max_hold=240, eod_hhmm=1555),
                   "eod": H.ExitSpec(max_hold=500, eod_hhmm=1555)}.items():
        run(f"SWEEP_{lvl_name}_rec_L_{ek}", reclaimed, +1, es)
        run(f"SWEEP5_{lvl_name}_rec_L_{ek}", reclaim5, +1, es)
for lvl_name, lvl in (("onhigh", on_high), ("pdh", pdh)):
    swept = rth & (df["high"] > lvl) & (cummax_rth.shift() <= lvl)
    rejected = swept & (df["close"] < lvl)
    breach = rth & (cummax_rth > lvl) & (cummax_rth.shift(5) <= lvl)
    reject5 = breach & (df["close"] < lvl) & (df["close"].shift() >= lvl)
    for ek, es in {"t30": H.ExitSpec(max_hold=30),
                   "t90": H.ExitSpec(max_hold=90, eod_hhmm=1555),
                   "s1.5t3": H.ExitSpec(stop_atr=1.5, target_atr=3, max_hold=240, eod_hhmm=1555),
                   "eod": H.ExitSpec(max_hold=500, eod_hhmm=1555)}.items():
        run(f"SWEEP_{lvl_name}_rej_S_{ek}", rejected, -1, es)
        run(f"SWEEP5_{lvl_name}_rej_S_{ek}", reject5, -1, es)

# continuation (acceptance) versions
acc_up = rth & (df["close"] > pdh + 0.25 * df["atr"]) & (df["close"].shift() <= pdh.shift() + 0.25 * df["atr"].shift())
acc_dn = rth & (df["close"] < pdl - 0.25 * df["atr"]) & (df["close"].shift() >= pdl.shift() - 0.25 * df["atr"].shift())
for ek, es in {"t60": H.ExitSpec(max_hold=60),
               "eod": H.ExitSpec(max_hold=500, eod_hhmm=1555),
               "trail3": H.ExitSpec(trail_atr=3, max_hold=500, eod_hhmm=1555)}.items():
    run(f"PDHL_acc_up_L_{ek}", acc_up, +1, es)
    run(f"PDHL_acc_dn_S_{ek}", acc_dn, -1, es)

# ------------------------------------------------------------------ #
# RND: NQ 100-pt round numbers — cross-and-hold vs first-touch fade
# ------------------------------------------------------------------ #
craw = df["close_raw"] if "close_raw" in df.columns else df["close"]
lvl100 = (craw / 100).round() * 100
cross_up = rth & (craw > lvl100) & (craw.shift() <= lvl100) & (craw - lvl100 < 0.3 * df["atr"])
cross_dn = rth & (craw < lvl100) & (craw.shift() >= lvl100) & (lvl100 - craw < 0.3 * df["atr"])
for ek, es in {"t15": H.ExitSpec(max_hold=15), "t60": H.ExitSpec(max_hold=60)}.items():
    run(f"RND_crossup_L_{ek}", cross_up, +1, es)
    run(f"RND_crossdn_S_{ek}", cross_dn, -1, es)
    run(f"RND_crossup_S_{ek}", cross_up, -1, es)
    run(f"RND_crossdn_L_{ek}", cross_dn, +1, es)

# ------------------------------------------------------------------ #
# MAG: 15:00 — if price within 0.5 dayATR of prior settle, gravitate to it
# ------------------------------------------------------------------ #
at_1500 = hhmm == 1500
dist = (pdc - df["close"]) / datr
mag_l = at_1500 & (dist > 0.1) & (dist < 0.5)
mag_s = at_1500 & (dist < -0.1) & (dist > -0.5)
es_mag = H.ExitSpec(max_hold=70, eod_hhmm=1559)
run("MAG_L", mag_l, +1, es_mag)
run("MAG_S", mag_s, -1, es_mag)
run("MAGrev_S", mag_l, -1, es_mag)
run("MAGrev_L", mag_s, +1, es_mag)

out = Path(H.CACHE) / "batch3_results.json"
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
