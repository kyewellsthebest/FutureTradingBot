"""
Apply engine_validation_results.json → validation_results.json.

Reads the engine-aware validator's output and updates the `recommended`
flag (Tier A live whitelist) in validation_results.json:

  - Strategies that PASS all 5 rigorous tests under engine conditions
    → recommended = True (live tradeable)
  - Strategies that fail
    → recommended = False (dropped from live whitelist; remain in
                            validation_results.json for transparency)

A backup of the prior validation_results.json is saved first so we can
roll back trivially if the new whitelist underperforms.

Output:
  data/validation_results.json                    (updated in place)
  data/validation_results_pre_engine.json         (backup of old recommended flags)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
ENG_PATH    = DATA / "engine_validation_results.json"
VAL_PATH    = DATA / "validation_results.json"
BACKUP_PATH = DATA / "validation_results_pre_engine.json"
BUNDLED_PATH = PROJECT_ROOT / "bundled" / "validation_results.json"


def main():
    if not ENG_PATH.exists():
        raise SystemExit(f"missing {ENG_PATH} — run engine_validator first")
    if not VAL_PATH.exists():
        raise SystemExit(f"missing {VAL_PATH}")

    eng = json.loads(ENG_PATH.read_text())
    val = json.loads(VAL_PATH.read_text())

    # Backup current `recommended` flags
    BACKUP_PATH.write_text(VAL_PATH.read_text())
    print(f"backed up current validation_results.json → {BACKUP_PATH.name}")

    # Build the new whitelist: every strategy that passes ALL 5 tests
    survivors = {r["name"]: r for r in eng["results"] if r["passes_all"]}
    print(f"\nengine-validation survivors: {len(survivors)} strategies")
    print(f"  total candidates evaluated: {eng['summary']['n_total']}")

    sigs = val.get("signals") or {}
    n_promoted = 0; n_demoted = 0; n_unchanged = 0
    for name, info in sigs.items():
        was_recommended = bool(info.get("recommended"))
        is_recommended = name in survivors
        if is_recommended and not was_recommended:
            n_promoted += 1
        elif was_recommended and not is_recommended:
            n_demoted += 1
        else:
            n_unchanged += 1
        info["recommended"] = is_recommended
        info["tier"] = "A" if is_recommended else (info.get("tier") or "C")
        # Stash the engine-validated metrics so the dashboard's strategies
        # tab + descriptions tooltip can show truth-from-engine numbers.
        if name in survivors:
            r = survivors[name]
            info["engine_validated"] = {
                "n":             r["n_engine_accepted"],
                "win_rate":      r["win_rate"],
                "profit_factor": r["profit_factor"],
                "net_pnl":       r["net_pnl"],
                "sharpe":        r["sharpe"],
                "cpcv_pos":      r["cpcv_test_folds_positive"],
                "cpcv_total":    eng["tests"]["cpcv_folds"],
                "validated_at":  datetime.now(timezone.utc).isoformat(),
            }

    val["signals"] = sigs
    val["last_engine_validation"] = {
        "ran_at":            datetime.now(timezone.utc).isoformat(),
        "window_days":       eng.get("window_days"),
        "n_candidates":      eng["summary"]["n_total"],
        "n_passed_all":      eng["summary"]["n_pass_all"],
        "n_passed_sample":   eng["summary"]["n_pass_sample"],
        "n_passed_wr":       eng["summary"]["n_pass_wr"],
        "n_passed_pf":       eng["summary"]["n_pass_pf"],
        "n_passed_sharpe":   eng["summary"]["n_pass_sharpe"],
        "n_passed_cpcv":     eng["summary"]["n_pass_cpcv"],
        "tests":             eng["tests"],
    }
    VAL_PATH.write_text(json.dumps(val, indent=2, default=str))
    # Also overwrite the bundled copy so live_runner picks it up next deploy
    if BUNDLED_PATH.exists() or BUNDLED_PATH.parent.exists():
        BUNDLED_PATH.write_text(VAL_PATH.read_text())
        print(f"updated bundled copy → {BUNDLED_PATH.relative_to(PROJECT_ROOT)}")

    print(f"\nwhitelist changes applied:")
    print(f"  promoted (newly recommended): {n_promoted}")
    print(f"  demoted (previously rec, now off): {n_demoted}")
    print(f"  unchanged: {n_unchanged}")
    print(f"\nnew Tier A live whitelist ({len(survivors)} strategies):")
    for r in sorted(survivors.values(), key=lambda r: -r["net_pnl"]):
        print(f"  {r['name']:<32}  {r['side']:<5}  n={r['n_engine_accepted']:>3}  "
              f"WR={r['win_rate']*100:.1f}%  PF={r['profit_factor']:.2f}  "
              f"Sh={r['sharpe']:+.2f}  CPCV={r['cpcv_test_folds_positive']}/{eng['tests']['cpcv_folds']}  "
              f"pnl=${r['net_pnl']:+,.0f}")
    print(f"\nWrote {VAL_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
