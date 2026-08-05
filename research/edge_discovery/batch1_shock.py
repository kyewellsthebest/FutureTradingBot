"""Batch 1: shock / microstructure-event hypotheses on NQ 1-min.

Families:
  A  return-shock fade (stop-cascade / liquidity-vacuum proxy)
  B  multi-minute cascade fade
  C  absorption (huge volume, tiny range) -> reversal of prior move
  D  volume-climax after extended run -> fade
  E  run-length continuation vs reversion
  F  volatility compression -> expansion continuation
  G  VWAP deviation fade (RTH)
  H  bar-to-bar gap fade
Each: long and short separately, several exit philosophies.
Selection here is IN-SAMPLE (<2024). OOS shown for context but candidates
are picked on IS t-stat and then destruction-tested later.
"""
import sys, json, warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import harness as H

df = pd.read_parquet(H.CACHE / "nq_feat.parquet")
print(f"bars={len(df)}  {df.index[0]} -> {df.index[-1]}")

# 5-minute cumulative return z
r5 = df["close"].diff(5)
r5_sd = r5.rolling(120, min_periods=60).std()
z5 = r5 / r5_sd.clip(lower=1e-9)

# rolling 30-bar range percentile (compression detector)
rng30 = df["high"].rolling(30).max() - df["low"].rolling(30).min()
rng30_pct = rng30.rolling(1440, min_periods=300).rank(pct=True)

vwap_dev = (df["close"] - df["vwap"]) / df["atr"].clip(lower=1e-9)
gap_open = (df["open"] - df["close"].shift())            # bar-to-bar gap, known at bar open... use prior bar signal instead
prev_close_jump = df["close"].diff()                     # alias of ret

active = df["vol_ma"] > 30            # skip dead overnight minutes for micro events

EXITS = {
    "t5":   H.ExitSpec(max_hold=5),
    "t15":  H.ExitSpec(max_hold=15),
    "t30":  H.ExitSpec(max_hold=30),
    "s2t2_60": H.ExitSpec(stop_atr=2, target_atr=2, max_hold=60),
    "s3t1.5_60": H.ExitSpec(stop_atr=3, target_atr=1.5, max_hold=60),
    "trail2_120": H.ExitSpec(trail_atr=2, max_hold=120),
}

SIGNALS = {}

# --- A: single-bar shock fade -------------------------------------- #
for thr in (3, 4, 5):
    SIGNALS[f"A_shockfade_dn{thr}_L"] = ((df["ret_z"] < -thr) & active, +1)
    SIGNALS[f"A_shockfade_up{thr}_S"] = ((df["ret_z"] > thr) & active, -1)
# volume-split variants: cascade with volume vs vacuum without
SIGNALS["A_shock4_dn_hivol_L"] = ((df["ret_z"] < -4) & (df["vol_z"] > 2) & active, +1)
SIGNALS["A_shock4_dn_lovol_L"] = ((df["ret_z"] < -4) & (df["vol_z"] < 0.5) & active, +1)
SIGNALS["A_shock4_up_hivol_S"] = ((df["ret_z"] > 4) & (df["vol_z"] > 2) & active, -1)
SIGNALS["A_shock4_up_lovol_S"] = ((df["ret_z"] > 4) & (df["vol_z"] < 0.5) & active, -1)
# continuation versions (momentum after shock)
SIGNALS["A_shockmom_dn4_S"] = ((df["ret_z"] < -4) & active, -1)
SIGNALS["A_shockmom_up4_L"] = ((df["ret_z"] > 4) & active, +1)

# --- B: 5-min cascade fade ------------------------------------------ #
for thr in (3, 4):
    SIGNALS[f"B_casc5_dn{thr}_L"] = ((z5 < -thr) & active, +1)
    SIGNALS[f"B_casc5_up{thr}_S"] = ((z5 > thr) & active, -1)

# --- C: absorption --------------------------------------------------- #
absorb = (df["vol_z"] > 3) & (df["range"] < 0.5 * df["atr"]) & active
prior_dn = df["close"].diff(10) < 0
SIGNALS["C_absorb_after_dn_L"] = (absorb & prior_dn, +1)
SIGNALS["C_absorb_after_up_S"] = (absorb & ~prior_dn, -1)
# opposite: absorption breaks (continuation)
SIGNALS["C_absorb_after_dn_S"] = (absorb & prior_dn, -1)
SIGNALS["C_absorb_after_up_L"] = (absorb & ~prior_dn, +1)

# --- D: volume climax after run -------------------------------------- #
climax_up = (df["run"] >= 6) & (df["vol_z"] > 2) & active
climax_dn = (df["run"] <= -6) & (df["vol_z"] > 2) & active
SIGNALS["D_climax_up_S"] = (climax_up, -1)
SIGNALS["D_climax_dn_L"] = (climax_dn, +1)

# --- E: plain run-length --------------------------------------------- #
for k in (5, 8):
    SIGNALS[f"E_run{k}_up_S"] = ((df["run"] >= k) & active, -1)
    SIGNALS[f"E_run{k}_dn_L"] = ((df["run"] <= -k) & active, +1)
    SIGNALS[f"E_run{k}_up_L"] = ((df["run"] >= k) & active, +1)
    SIGNALS[f"E_run{k}_dn_S"] = ((df["run"] <= -k) & active, -1)

# --- F: compression -> expansion continuation ------------------------- #
squeeze = rng30_pct < 0.10
expand_up = squeeze.shift() & (df["ret_z"] > 2)
expand_dn = squeeze.shift() & (df["ret_z"] < -2)
SIGNALS["F_squeeze_brk_up_L"] = (expand_up & active, +1)
SIGNALS["F_squeeze_brk_dn_S"] = (expand_dn & active, -1)
SIGNALS["F_squeeze_brk_up_S"] = (expand_up & active, -1)
SIGNALS["F_squeeze_brk_dn_L"] = (expand_dn & active, +1)

# --- G: VWAP deviation fade (RTH only) -------------------------------- #
for thr in (4, 6):
    SIGNALS[f"G_vwapfade_hi{thr}_S"] = ((vwap_dev > thr) & df["rth"], -1)
    SIGNALS[f"G_vwapfade_lo{thr}_L"] = ((vwap_dev < -thr) & df["rth"], +1)

# --- H: minute-gap fade ------------------------------------------------ #
jump = df["ret"].abs() > 3 * df["atr"]
SIGNALS["H_bigbar_dn_L"] = (jump & (df["ret"] < 0) & active, +1)
SIGNALS["H_bigbar_up_S"] = (jump & (df["ret"] > 0) & active, -1)

results = {}
for name, (sig, d) in SIGNALS.items():
    nsig = int(sig.sum())
    if nsig < 50:
        print(f"{name:<44s} SKIP nsig={nsig}")
        continue
    for ek, es in EXITS.items():
        res = H.simulate(df, sig, d, es, "nq", f"{name}_{ek}")
        s_is, s_oos = H.is_oos(res)
        key = f"{name}_{ek}"
        results[key] = {"is": s_is, "oos": s_oos}
        if s_is.get("n", 0) > 30 and abs(s_is.get("t_stat", 0)) > 2:
            print("IS>> " + H.fmt(key, s_is))
            print("OOS> " + H.fmt(key, s_oos))

out = Path(H.CACHE) / "batch1_results.json"
out.write_text(json.dumps(results, default=str))
print("saved", out, len(results), "variants")
