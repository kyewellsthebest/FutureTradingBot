"""
Build the deployment set for the live bot.

Logic:
  1. Take all bulletproof + moderate strategies (survive 4pt slippage at minimum)
  2. Add fragile SHORT strategies (PF >= 1.0) to balance the LONG/SHORT count
  3. Save to data/deployed_strategies.json — the live bot loads from this list

This is the "real-money keepers" list, separate from the full mining results.
"""
from __future__ import annotations
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
STRESS_PATH = DATA / "slippage_stress_results.json"
OUT_PATH = DATA / "deployed_strategies.json"


def main():
    d = json.loads(STRESS_PATH.read_text())
    bullet = set(d["bulletproof_strategies"])
    moderate = set(d["moderate_strategies"])
    base = {r["name"]: r for r in d["scenarios"]["baseline"]["results"]}

    keepers = set(bullet) | set(moderate)
    keep_rows = [base[n] for n in keepers if n in base]
    longs = [r for r in keep_rows if r["side"] == "LONG"]
    shorts = [r for r in keep_rows if r["side"] == "SHORT"]

    # Add fragile SHORTs (PF >= 1.0) to better-balance the L/S split
    fragile_shorts = [
        r for r in base.values()
        if r["side"] == "SHORT" and r["name"] not in keepers and r["pf"] >= 1.0
    ]
    fragile_shorts.sort(key=lambda r: -r["pf"])
    for r in fragile_shorts:
        keepers.add(r["name"])

    final_rows = [base[n] for n in keepers if n in base]
    longs = sum(1 for r in final_rows if r["side"] == "LONG")
    shorts = sum(1 for r in final_rows if r["side"] == "SHORT")

    out = {
        "n_total": len(keepers),
        "n_long": longs,
        "n_short": shorts,
        "ratio": round(longs / max(shorts, 1), 2),
        "names": sorted(keepers),
        "rationale": {
            "bulletproof": len(bullet),
            "moderate": len([n for n in moderate if n not in bullet]),
            "fragile_shorts_added": len(fragile_shorts),
            "fragile_longs_excluded": "kept out of deployment — backtest fantasies",
        },
    }
    OUT_PATH.write_text(json.dumps(out, indent=2))
    print(f"Wrote {OUT_PATH}")
    print(f"  Total deployed: {len(keepers)}")
    print(f"  LONG: {longs}, SHORT: {shorts}, ratio L:S = {longs}/{shorts} = {longs/max(shorts,1):.2f}:1")
    print(f"  Bulletproof:        {len(bullet)}")
    print(f"  Moderate (PF>=1):   {len([n for n in moderate if n not in bullet])}")
    print(f"  Fragile SHORTs:     {len(fragile_shorts)} (added to balance)")


if __name__ == "__main__":
    main()
