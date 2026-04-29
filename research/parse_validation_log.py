"""
Parse a validate_mined_full.py log file (in-progress or completed) and write
out a JSON that mimics the validator's output, so the merge step can use
partial-validation results.

Each pattern in the log has 6 lines: name + EV + PERM + WF + MC + SENS + TIER.
Patterns mid-test (no TIER line yet) are dropped.

Usage:
    python -m research.parse_validation_log <log_path> <input_dedup_json> <output_json>
"""
from __future__ import annotations
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Regex for the test summary lines
RE_NAME = re.compile(r"\[\s*(\d+)/\s*(\d+)\]\s+(\S+)")
RE_EV   = re.compile(r"EV:\s+n=\s*(\d+)\s+WR=\s*([\d.]+)%\s+PF=\s*([\d.]+)\s+EV=\$(\S+)/trade\s+net=\$(\S+)\s+(PASS|FAIL)")
RE_PERM = re.compile(r"PERM:\s+(\d+)\s+shuffles\s+p=([\d.]+)\s+(PASS|FAIL)")
RE_WF   = re.compile(r"WF:\s+CPCV\s+mean=\s*([\d.]+)%\s+min_fold=\s*([\d.]+)%\s+\(BE=(\d+)%\)\s+(PASS|FAIL)")
RE_MC   = re.compile(r"MC:\s+median=\$(\S+)\s+p5=\$(\S+)\s+Apex=(\d+)%\s+(PASS|FAIL)")
RE_SENS = re.compile(r"SENS:\s+pf_default=\s*([\d.]+)\s+pf_low=\s*([\d.]+)\s+pf_high=\s*([\d.]+)\s+(PASS|FAIL)")
RE_TIER = re.compile(r"TIER\s+(A|B|REJECT)\s+\((\d+)/5\s+tests\)")


def _num(s: str) -> float:
    s = s.replace(",", "").replace("+", "").replace("$", "")
    try:
        return float(s)
    except Exception:
        return 0.0


def parse_log(log_path: Path) -> dict[str, dict]:
    """Returns dict: name → result-dict (only for fully-tested patterns)."""
    text = log_path.read_text()
    blocks = re.split(r"\n  \[\s*\d+/", "\n" + text)[1:]   # split per-pattern
    results = {}
    for blk in blocks:
        name_match = re.match(r"\s*\d+\]\s+(\S+)", blk)
        if not name_match:
            continue
        name = name_match.group(1)
        # Extract each test
        ev_m = RE_EV.search(blk)
        perm_m = RE_PERM.search(blk)
        wf_m = RE_WF.search(blk)
        mc_m = RE_MC.search(blk)
        sens_m = RE_SENS.search(blk)
        tier_m = RE_TIER.search(blk)
        if not (ev_m and tier_m):
            continue   # not yet finished
        n_trades = int(ev_m.group(1))
        wr = float(ev_m.group(2)) / 100
        pf = float(ev_m.group(3))
        ev_dollars = _num(ev_m.group(4))
        net_pnl = _num(ev_m.group(5))
        ev_pass = ev_m.group(6) == "PASS"
        perm_p = float(perm_m.group(2)) if perm_m else 1.0
        perm_pass = perm_m.group(3) == "PASS" if perm_m else False
        wf_pass = wf_m.group(4) == "PASS" if wf_m else False
        cpcv_mean = float(wf_m.group(1)) / 100 if wf_m else 0
        cpcv_min = float(wf_m.group(2)) / 100 if wf_m else 0
        mc_pass = mc_m.group(4) == "PASS" if mc_m else False
        median_final = _num(mc_m.group(1)) if mc_m else 0
        apex_pct = float(mc_m.group(3)) if mc_m else 0
        sens_pass = sens_m.group(4) == "PASS" if sens_m else False
        pf_low = float(sens_m.group(2)) if sens_m else 0
        pf_high = float(sens_m.group(3)) if sens_m else 0
        tier = tier_m.group(1)
        n_passes = int(tier_m.group(2))
        results[name] = {
            "name": name, "n_trades": n_trades, "win_rate": wr,
            "profit_factor": pf, "ev_dollars": ev_dollars, "net_pnl": net_pnl,
            "tests": {
                "ev": {"value": ev_dollars, "pass": ev_pass},
                "permutation": {"p_value": perm_p, "n_perm": int(perm_m.group(1)) if perm_m else 0, "pass": perm_pass},
                "walk_forward": {"cpcv_mean": cpcv_mean, "cpcv_min": cpcv_min, "pass": wf_pass},
                "monte_carlo": {"median_final": median_final, "p_apex_pass": apex_pct/100, "pass": mc_pass},
                "parameter_sensitivity": {"pf_default": pf, "pf_low_20pct": pf_low, "pf_high_20pct": pf_high, "pass": sens_pass},
            },
            "n_passes": n_passes, "tier": tier if tier != "REJECT" else "REJECT",
        }
    return results


def main():
    log_path = Path(sys.argv[1])
    input_json = Path(sys.argv[2])
    output_json = Path(sys.argv[3])

    log_results = parse_log(log_path)
    print(f"Parsed {len(log_results)} fully-tested patterns from log")

    # Merge with input dedup file (which has constraint chains, side, stop, etc.)
    src = json.loads(input_json.read_text())
    src_by_name = {p["name"]: p for p in src["patterns"]}

    merged = []
    for name, result in log_results.items():
        src_p = src_by_name.get(name)
        if src_p is None:
            continue
        merged.append({
            **src_p, **result,
            "side": src_p["side"], "stop_pts": src_p["stop_pts"],
            "target_pts": src_p["target_pts"], "max_hold": src_p["max_hold"],
            "constraints": src_p["constraints"],
            "cpcv_mean_wr": src_p.get("cpcv_mean_wr", 0),
            "cpcv_min_wr": src_p.get("cpcv_min_wr", 0),
        })

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_file": str(input_json),
        "n_validated": len(merged),
        "patterns": merged,
    }
    output_json.write_text(json.dumps(out, indent=2, default=str))
    print(f"Wrote {len(merged)} -> {output_json}")
    n_a = sum(1 for r in merged if r["tier"] == "A")
    n_b = sum(1 for r in merged if r["tier"] == "B")
    n_r = sum(1 for r in merged if r["tier"] == "REJECT")
    print(f"  Tier A: {n_a}    Tier B: {n_b}    Reject: {n_r}")


if __name__ == "__main__":
    main()
