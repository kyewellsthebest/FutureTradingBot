"""Batch 3b: cross-market lead-lag hypotheses (1-min ES/NQ/RTY, 2023-12..2026-02).

Stories:
  XLAG   ES moves hard, NQ hasn't matched -> NQ catches up (index-arb latency;
         expected to be dead at 1-min, tested honestly)
  XSPRD  NQ-ES 30-min relative-performance z-extreme -> converges (pairs flow)
  XRTY   small-caps lag: big joint ES+NQ move -> RTY continues next minutes
         (slower participants in the less liquid contract)
Data window is short (~2.2y), so this is discovery-grade only; any candidate
must also make sense on the split halves.
"""
import sys, json, warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import harness as H

nq = pd.read_parquet(H.CACHE / "nq_feat.parquet")
es = pd.read_parquet(H.CACHE / "es_feat.parquet")
rty = pd.read_parquet(H.CACHE / "rty_feat.parquet")

# align on common minutes
common = nq.index.intersection(es.index)
nqc = nq.loc[common]
esc = es.loc[common]
print(f"joint NQ/ES minutes: {len(common)}  {common[0]} -> {common[-1]}")

arrays_nq = H.get_arrays(nqc)

r_nq = nqc["close"].pct_change()
r_es = esc["close"].pct_change()
sd_nq = r_nq.rolling(120, min_periods=60).std()
sd_es = r_es.rolling(120, min_periods=60).std()
z_nq1 = r_nq / sd_nq.clip(lower=1e-9)
z_es1 = r_es / sd_es.clip(lower=1e-9)

# 30-min relative performance spread (beta ~ 1 in return space)
rel = (r_nq - r_es).rolling(30).sum()
rel_sd = rel.rolling(1440, min_periods=300).std()
z_rel = rel / rel_sd.clip(lower=1e-9)

active = nqc["vol_ma"] > 30
results = {}
MID = "2025-01-15"  # split halves for stability check


def run(name, sig, d, es_spec, dfx, arrays, sym="nq"):
    r = H.simulate(dfx, sig, d, es_spec, sym, name, arrays=arrays)
    a = r.stats(end=MID)
    b = r.stats(start=MID)
    results[name] = {"h1": a, "h2": b}
    if a.get("n", 0) > 40 and (a.get("avg_net_usd", -9) > 0 or b.get("avg_net_usd", -9) > 0):
        print("H1>> " + H.fmt(name, a))
        print("H2>> " + H.fmt(name, b))


EX = {
    "t5": H.ExitSpec(max_hold=5),
    "t15": H.ExitSpec(max_hold=15),
    "t30": H.ExitSpec(max_hold=30),
    "s2t2": H.ExitSpec(stop_atr=2, target_atr=2, max_hold=60),
}

# XLAG: ES 1-min shock, NQ lagging (its own move < half of ES's in z-terms)
for thr in (3, 4):
    lag_up = (z_es1 > thr) & (z_nq1 < z_es1 * 0.5) & active
    lag_dn = (z_es1 < -thr) & (z_nq1 > z_es1 * 0.5) & active
    for ek, e in EX.items():
        run(f"XLAG_up{thr}_L_{ek}", lag_up, +1, e, nqc, arrays_nq)
        run(f"XLAG_dn{thr}_S_{ek}", lag_dn, -1, e, nqc, arrays_nq)

# XSPRD: NQ rich/cheap vs ES over 30 min -> fade with NQ leg
for thr in (2.5, 3.5):
    for ek, e in EX.items():
        run(f"XSPRD_rich{thr}_S_{ek}", (z_rel > thr) & active, -1, e, nqc, arrays_nq)
        run(f"XSPRD_cheap{thr}_L_{ek}", (z_rel < -thr) & active, +1, e, nqc, arrays_nq)

# XRTY: joint index shock -> RTY continuation
common3 = common.intersection(rty.index)
rtyc = rty.loc[common3]
arrays_rty = H.get_arrays(rtyc)
z_joint = ((z_nq1 + z_es1) / 2).reindex(common3)
r_rty = rtyc["close"].pct_change()
z_rty1 = (r_rty / r_rty.rolling(120, min_periods=60).std().clip(lower=1e-9))
act3 = (rtyc["vol_ma"] > 5)
for thr in (2.5, 3.5):
    cont_up = (z_joint > thr) & (z_rty1 < z_joint * 0.5) & act3
    cont_dn = (z_joint < -thr) & (z_rty1 > z_joint * 0.5) & act3
    for ek, e in EX.items():
        run(f"XRTY_up{thr}_L_{ek}", cont_up, +1, e, rtyc, arrays_rty, sym="rty")
        run(f"XRTY_dn{thr}_S_{ek}", cont_dn, -1, e, rtyc, arrays_rty, sym="rty")

out = Path(H.CACHE) / "batch3b_results.json"
out.write_text(json.dumps(results, default=str))
print(f"saved {len(results)} variants")
