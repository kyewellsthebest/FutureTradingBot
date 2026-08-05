"""Tick batch A: order-flow families on 1-second bars (NQ, Sep 2023 - Jun 2026).

Families (behavior -> who creates it -> why it persists):
  OFI    tick-rule order-flow imbalance extremes -> momentum vs reversal.
         Aggressive flow consumes liquidity; if informed, price continues; if
         liquidation, it reverts. Split by burst/large-lot context.
  BIG    large-lot prints (>=10, >=25 lots): institutional urgency ->
         short-horizon continuation (order splitting leaves a footprint).
  BURST  trade-rate explosion with directional flow -> momentum while the
         cascade runs; fade when flow and price diverge.
  QUIET  liquidity vacuum (trade-rate collapse) -> first directional move after
         silence follows through (book is thin, moves are cheap).
  SHOCK  10s/30s/60s return z-extremes -> fade vs momentum, split by flow
         confirmation (was the move flow-driven or vacuum-driven?).
IS = Sep 2023 .. Feb 2025, OOS = Mar 2025 .. Jun 2026 (55/45 split).
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

df = load_sec(columns=["n_trades", "ret", "ret_sd", "r10", "r30", "r60",
                       "ofi10", "ofi60", "ofi300", "burst", "big_flow", "big_delta"])
arrays = H.get_arrays(df)
print(f"{len(df):,} second-bars loaded")

active = (df["n_trades"].rolling(60).sum() > 60) & df["ret_sd"].notna()
rth = df["rth"]

results = {}
def run(name, sig, d, es):
    r = H.simulate(df, sig, d, es, "nq", name, arrays=arrays)
    s_is, s_oos = H.is_oos(r)
    results[name] = {"is": s_is, "oos": s_oos}
    if s_is.get("n", 0) > 100 and s_is.get("t_stat", 0) > 2 and s_is.get("avg_net_usd", -9) > 0:
        print("IS>> " + H.fmt(name, s_is))
        print("OOS> " + H.fmt(name, s_oos))
    return r

EX = {
    "t10s": H.ExitSpec(max_hold=10),
    "t30s": H.ExitSpec(max_hold=30),
    "t2m": H.ExitSpec(max_hold=120),
    "t10m": H.ExitSpec(max_hold=600),
    "s2t2": H.ExitSpec(stop_atr=2, target_atr=2, max_hold=600),
    "s4t4": H.ExitSpec(stop_atr=4, target_atr=4, max_hold=1800),
}

# --- OFI ---------------------------------------------------------------
for w in (60, 300):
    ofi = df[f"ofi{w}"]
    hi, lo = ofi > 0.6, ofi < -0.6
    for ek in ("t30s", "t2m", "t10m"):
        run(f"OFI{w}_mom_L_{ek}", (hi & active), +1, EX[ek])
        run(f"OFI{w}_mom_S_{ek}", (lo & active), -1, EX[ek])
        run(f"OFI{w}_rev_S_{ek}", (hi & active), -1, EX[ek])
        run(f"OFI{w}_rev_L_{ek}", (lo & active), +1, EX[ek])

# OFI divergence: strong buy flow but price flat/down over same window (absorption)
absorb_buy = (df["ofi60"] > 0.5) & (df["r60"] < 0) & active
absorb_sell = (df["ofi60"] < -0.5) & (df["r60"] > 0) & active
for ek in ("t30s", "t2m", "t10m"):
    run(f"ABSORB_buyfail_S_{ek}", absorb_buy, -1, EX[ek])   # buyers absorbed -> down
    run(f"ABSORB_buyfail_L_{ek}", absorb_buy, +1, EX[ek])   # or delayed breakout
    run(f"ABSORB_sellfail_L_{ek}", absorb_sell, +1, EX[ek])
    run(f"ABSORB_sellfail_S_{ek}", absorb_sell, -1, EX[ek])

# --- BIG ---------------------------------------------------------------
big_buy = (df["big_delta"] >= 25) & active
big_sell = (df["big_delta"] <= -25) & active
big_flow_buy = (df["big_flow"] > 100) & active
big_flow_sell = (df["big_flow"] < -100) & active
for ek in ("t10s", "t30s", "t2m", "t10m"):
    run(f"BIG25_L_{ek}", big_buy, +1, EX[ek])
    run(f"BIG25_S_{ek}", big_sell, -1, EX[ek])
    run(f"BIGFLOW_L_{ek}", big_flow_buy, +1, EX[ek])
    run(f"BIGFLOW_S_{ek}", big_flow_sell, -1, EX[ek])

# --- BURST -------------------------------------------------------------
burst = (df["burst"] > 5) & active
b_up = burst & (df["r10"] > 1)
b_dn = burst & (df["r10"] < -1)
for ek in ("t30s", "t2m", "t10m"):
    run(f"BURST_up_L_{ek}", b_up, +1, EX[ek])
    run(f"BURST_dn_S_{ek}", b_dn, -1, EX[ek])
    run(f"BURST_up_S_{ek}", b_up, -1, EX[ek])
    run(f"BURST_dn_L_{ek}", b_dn, +1, EX[ek])

# --- QUIET (vacuum then move) -------------------------------------------
quiet = (df["burst"] < 0.25) & rth
q_up = quiet.shift(1).fillna(False) & (df["ret"] > df["ret_sd"])
q_dn = quiet.shift(1).fillna(False) & (df["ret"] < -df["ret_sd"])
for ek in ("t30s", "t2m"):
    run(f"QUIET_up_L_{ek}", q_up, +1, EX[ek])
    run(f"QUIET_dn_S_{ek}", q_dn, -1, EX[ek])

# --- SHOCK ---------------------------------------------------------------
for w in (10, 30, 60):
    z = df[f"r{w}"]
    up, dn = (z > 4) & active, (z < -4) & active
    flow_conf_up = up & (df["ofi10"] > 0.5)
    flow_conf_dn = dn & (df["ofi10"] < -0.5)
    vac_up = up & (df["ofi10"] < 0)
    vac_dn = dn & (df["ofi10"] > 0)
    for ek in ("t30s", "t2m", "s2t2"):
        run(f"SHK{w}_fade_S_{ek}", up, -1, EX[ek])
        run(f"SHK{w}_fade_L_{ek}", dn, +1, EX[ek])
        run(f"SHK{w}_mom_L_{ek}", flow_conf_up, +1, EX[ek])
        run(f"SHK{w}_mom_S_{ek}", flow_conf_dn, -1, EX[ek])
        run(f"SHK{w}_vacfade_S_{ek}", vac_up, -1, EX[ek])
        run(f"SHK{w}_vacfade_L_{ek}", vac_dn, +1, EX[ek])

out = Path(H.CACHE) / "tickA_results.json"
out.write_text(json.dumps(results, default=str))
print(f"\nsaved {len(results)} variants")

rows = [(v["is"]["t_stat"], k, v["is"], v["oos"]) for k, v in results.items()
        if v["is"].get("n", 0) > 100 and v["is"].get("avg_net_usd", -9) > 0
        and v["is"].get("t_stat", 0) > 1.5]
rows.sort(reverse=True)
print(f"{len(rows)} IS candidates (net>0, t>1.5):")
for t, k, s, o in rows[:25]:
    print(f"{k:<32s} IS n={s['n']:>6} avg_n={s['avg_net_usd']:>7.2f} t={s['t_stat']:>5.1f} "
          f"| OOS n={o.get('n', 0):>6} avg_n={o.get('avg_net_usd', 0):>7.2f} t={o.get('t_stat', 0):>5.1f}")
