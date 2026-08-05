"""Tick batch B: cascade/absorption/event-time/session families on 1s bars.

  CASC   liquidation cascade stalls: price stopped falling while aggressive
         selling continues (passive absorption at the low) -> long, and mirror.
  VBAR   event-time (volume-bar) momentum: N same-direction volume bars ->
         continuation (clock noise removed, activity-normalized).
  OPENS  9:30:00-9:30:0x second-scale opening drive -> continuation minutes out.
  ECONS  8:30:00-8:30:0x econ-print drive -> continuation (news diffuses over
         seconds-to-minutes; only the first movers are HFT).
  SWEEPT tick-scale stop-run failure at the rolling 30-min extreme: poke above
         by a hair, fail to extend within seconds, flow flips -> reverse.
"""
import sys, json, warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import harness as H
from tick_features import load_sec

H.IS_END = "2025-03-01"
H.OOS_START = "2025-03-01"

df = load_sec(columns=["n_trades", "volume", "ret", "ret_sd", "r60",
                       "ofi10", "burst"])
arrays = H.get_arrays(df)
active = (df["n_trades"].rolling(60).sum() > 60) & df["ret_sd"].notna()
results = {}

def run(name, sig, d, es):
    r = H.simulate(df, sig, d, es, "nq", name, arrays=arrays)
    s_is, s_oos = H.is_oos(r)
    results[name] = {"is": s_is, "oos": s_oos}
    if s_is.get("n", 0) > 80 and s_is.get("t_stat", 0) > 2 and s_is.get("avg_net_usd", -9) > 0:
        print("IS>> " + H.fmt(name, s_is))
        print("OOS> " + H.fmt(name, s_oos))
    return r

EX = {
    "t30s": H.ExitSpec(max_hold=30),
    "t2m": H.ExitSpec(max_hold=120),
    "t10m": H.ExitSpec(max_hold=600),
    "s2t3": H.ExitSpec(stop_atr=2, target_atr=3, max_hold=900),
    "s3t2": H.ExitSpec(stop_atr=3, target_atr=2, max_hold=900),
}

# --- CASC: cascade stall / passive absorption --------------------------
fell = df["r60"] < -3
stalled = df["close"].diff(5) >= 0
sellers_press = df["ofi10"] < -0.3
casc_long = fell & stalled & sellers_press & active
rose = df["r60"] > 3
stalled_up = df["close"].diff(5) <= 0
buyers_press = df["ofi10"] > 0.3
casc_short = rose & stalled_up & buyers_press & active
for ek in ("t30s", "t2m", "t10m", "s2t3"):
    run(f"CASC_L_{ek}", casc_long, +1, EX[ek])
    run(f"CASC_S_{ek}", casc_short, -1, EX[ek])

# --- VBAR: volume-bar momentum ------------------------------------------
cumv = df["volume"].cumsum()
V = 3000
bar_id = (cumv // V).to_numpy(np.int64)
pos = np.flatnonzero(np.diff(bar_id) > 0)          # row where each volume bar completes
vb_close = df["close"].to_numpy()[pos]
vb_ret = np.diff(vb_close)                          # vb_ret[j] = bar j+1 return
up3 = (vb_ret[2:] > 0) & (vb_ret[1:-1] > 0) & (vb_ret[:-2] > 0)
dn3 = (vb_ret[2:] < 0) & (vb_ret[1:-1] < 0) & (vb_ret[:-2] < 0)
sig_vb_up = pd.Series(False, index=df.index)
sig_vb_dn = pd.Series(False, index=df.index)
sig_vb_up.iloc[pos[3:][up3]] = True
sig_vb_dn.iloc[pos[3:][dn3]] = True
for ek in ("t2m", "t10m", "s2t3", "s3t2"):
    run(f"VBAR3_L_{ek}", sig_vb_up & active, +1, EX[ek])
    run(f"VBAR3_S_{ek}", sig_vb_dn & active, -1, EX[ek])
    run(f"VBAR3rev_S_{ek}", sig_vb_up & active, -1, EX[ek])
    run(f"VBAR3rev_L_{ek}", sig_vb_dn & active, +1, EX[ek])

# --- OPENS: second-scale opening drive ----------------------------------
hhmmss = pd.Series(df.index.hour * 10000 + df.index.minute * 100 + df.index.second,
                   index=df.index)
o930 = df["open"].where(df["hhmm"] == 930).groupby(df["tday"]).transform("first")
at_5s = (hhmmss >= 93005) & (hhmmss <= 93007)
first_of = at_5s & ~at_5s.shift(1).fillna(False).astype(bool)
drv = (df["close"] - o930)
for thr_t in (2, 5):
    up = first_of & (drv > thr_t)
    dn = first_of & (drv < -thr_t)
    for ek, e in {"to931": H.ExitSpec(max_hold=60), "to935": H.ExitSpec(max_hold=300),
                  "to1000": H.ExitSpec(max_hold=1800)}.items():
        run(f"OPENS{thr_t}_L_{ek}", up, +1, e)
        run(f"OPENS{thr_t}_S_{ek}", dn, -1, e)
        run(f"OPENSrev{thr_t}_S_{ek}", up, -1, e)
        run(f"OPENSrev{thr_t}_L_{ek}", dn, +1, e)

# --- ECONS: 8:30 release second-scale drive ------------------------------
pre = df["close"].where(hhmmss <= 82959).groupby(df["tday"]).transform("last")
at_ec = (hhmmss >= 83003) & (hhmmss <= 83005)
first_ec = at_ec & ~at_ec.shift(1).fillna(False).astype(bool)
mv = df["close"] - pre
big = mv.abs() > 4 * df["atr"]
for ek, e in {"t60s": H.ExitSpec(max_hold=60), "t5m": H.ExitSpec(max_hold=300),
              "t25m": H.ExitSpec(max_hold=1500)}.items():
    run(f"ECONS_cont_L_{ek}", first_ec & big & (mv > 0), +1, e)
    run(f"ECONS_cont_S_{ek}", first_ec & big & (mv < 0), -1, e)
    run(f"ECONS_fade_S_{ek}", first_ec & big & (mv > 0), -1, e)
    run(f"ECONS_fade_L_{ek}", first_ec & big & (mv < 0), +1, e)

# --- SWEEPT: tick-scale stop-run failure at rolling 30-min extreme -------
roll_hi = df["high"].rolling(1800, min_periods=600).max()
roll_lo = df["low"].rolling(1800, min_periods=600).min()
poked_hi = (df["high"] > roll_hi.shift(10)) & (df["high"] - roll_hi.shift(10) < 3.0)
fail_hi = poked_hi & (df["close"] < roll_hi.shift(10)) & (df["ofi10"] < 0)
poked_lo = (df["low"] < roll_lo.shift(10)) & (roll_lo.shift(10) - df["low"] < 3.0)
fail_lo = poked_lo & (df["close"] > roll_lo.shift(10)) & (df["ofi10"] > 0)
for ek in ("t2m", "t10m", "s2t3"):
    run(f"SWEEPT_hi_S_{ek}", fail_hi & active & df["rth"], -1, EX[ek])
    run(f"SWEEPT_lo_L_{ek}", fail_lo & active & df["rth"], +1, EX[ek])

out = Path(H.CACHE) / "tickB_results.json"
out.write_text(json.dumps(results, default=str))
print(f"\nsaved {len(results)} variants")
rows = [(v["is"]["t_stat"], k, v["is"], v["oos"]) for k, v in results.items()
        if v["is"].get("n", 0) > 80 and v["is"].get("avg_net_usd", -9) > 0
        and v["is"].get("t_stat", 0) > 1.5]
rows.sort(reverse=True)
print(f"{len(rows)} IS candidates (net>0, t>1.5):")
for t, k, s, o in rows[:25]:
    print(f"{k:<32s} IS n={s['n']:>6} avg_n={s['avg_net_usd']:>7.2f} t={s['t_stat']:>5.1f} "
          f"| OOS n={o.get('n', 0):>6} avg_n={o.get('avg_net_usd', 0):>7.2f} t={o.get('t_stat', 0):>5.1f}")
