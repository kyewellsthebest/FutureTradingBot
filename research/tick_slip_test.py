"""Slippage-sensitivity stress test on the top search configs.

The winners use a tight 6pt stop; their edge is most exposed to stop slip
being worse than the 0.25pt observed live. Re-run each at 0.25 / 0.5 /
0.75 / 1.0 pt flat stop slip and see which configs keep their edge.
"""
from __future__ import annotations
import numpy as np, pandas as pd
from research.tick_sim import (load_ticks, build_1m_bars, precompute_setups,
                               simulate, stats, SimCfg)

CONFIGS = [
    # name, imp, W, pull, stop, tgt
    ("WINNER  i3_w3_s6_t30",  3.0, 3, 0.236, 6.0, 30.0),
    ("        i3_w5_s6_t24",  3.0, 5, 0.236, 6.0, 24.0),
    ("        i3_w3_s6_t24",  3.0, 3, 0.236, 6.0, 24.0),
    ("        i5_w3_s6_t30",  5.0, 3, 0.236, 6.0, 30.0),
    ("safer   i3_w5_s6_t18",  3.0, 5, 0.236, 6.0, 18.0),
    ("wide-st i5_w3_s8_t30",  5.0, 3, 0.236, 8.0, 30.0),
    ("wide-st i5_w3_s10_t30", 5.0, 3, 0.236, 10.0, 30.0),
    ("LIVE    i5_w4_s10_t20", 5.0, 4, 0.236, 10.0, 20.0),
]
SLIPS = [0.25, 0.5, 0.75, 1.0]

def main():
    ticks = load_ticks()
    bars = build_1m_bars(ticks[0], ticks[1])
    rows = []
    for label, imp, W, pull, stop, tgt in CONFIGS:
        params = {"IMPULSE_PTS": imp, "IMPULSE_WINDOW_BARS": W, "PULLBACK_PCT": pull,
                  "STOP_PTS": stop, "TARGET_PTS": tgt, "INVERT": True}
        setups = precompute_setups(bars, params)
        rec = {"config": label}
        for slip in SLIPS:
            df = simulate(ticks, setups, SimCfg(stop_slip=slip))
            s = stats(df)
            rec[f"$/d@{slip}"] = s["per_day"]
        rec["maxDD@1.0"] = stats(simulate(ticks, setups, SimCfg(stop_slip=1.0)))["maxDD"]
        rows.append(rec)
        print(f"done {label}", flush=True)
    out = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print("\n==== $/day per MNQ vs flat stop-slip (pts) ====")
    print(out.to_string(index=False))
    out.to_csv("research/tick_slip_test.csv", index=False)

if __name__ == "__main__":
    main()
