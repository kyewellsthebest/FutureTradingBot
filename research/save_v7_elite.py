"""
Save v7 elite whitelist with the strategies that found real edge.
"""
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

d = json.load(open(DATA / "mined_v7_patterns.json"))
all_results = d.get("all_results", d.get("results", []))

# Robust threshold: PF > 1.0, CPCV >= 3, n >= 100
robust = [r for r in all_results
          if r.get("test", {}).get("pf", 0) > 1.0
          and r.get("cpcv_positive", 0) >= 3
          and r.get("test", {}).get("n", 0) >= 100]
robust.sort(key=lambda x: x.get("test", {}).get("sharpe", -99), reverse=True)

# All profitable
profitable = [r for r in all_results if r.get("test", {}).get("pf", 0) > 1.0]
profitable.sort(key=lambda x: x.get("test", {}).get("sharpe", -99), reverse=True)

elite = {
    "ran_at": d.get("ran_at"),
    "n_total_tested": len(all_results),
    "n_profitable_pf_gt_1": len(profitable),
    "n_robust_pf_gt_1_cpcv_3_n_100": len(robust),
    "robust_strategies": robust,
    "all_profitable": profitable,
    "thesis": {
        "primary": (
            "NQ-ES statistical arbitrage during NY afternoon. When NQ "
            "diverges >2 sigma from its 60-bar return correlation with ES, "
            "fade the divergence (SHORT if NQ over-extended, LONG if under). "
            "Multi-fold CPCV confirmation suggests real cointegration edge."
        ),
        "secondary": (
            "ES lead-lag during NY midday. When ES moves >1.5 sigma in last "
            "10 bars and NQ hasn't caught up, take NQ in direction of ES."
        ),
    },
    "deployment_notes": (
        "These strategies require live ES quotes alongside NQ. The current bot "
        "(signal_generator.py) only consumes NQ data. To deploy these honestly "
        "would need: (1) ES data feed; (2) rolling 60-bar correlation/divergence "
        "computation; (3) new named-signal types in named_signals.py."
    ),
}
out = DATA / "v7_elite.json"
out.write_text(json.dumps(elite, indent=2, default=str))
print(f"Wrote {out}")
print(f"  n_total: {elite['n_total_tested']}")
print(f"  profitable: {elite['n_profitable_pf_gt_1']}")
print(f"  robust: {elite['n_robust_pf_gt_1_cpcv_3_n_100']}")
