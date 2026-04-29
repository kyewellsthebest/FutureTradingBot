"""
Continuous-retraining orchestrator — meant to be run weekly via cron.

What it does:
    1. Refreshes the local NQ data files from broker if newer
    2. Runs the 8yr 5-test gauntlet on the current whitelist (data/recency_check)
    3. Identifies "DECAYED" or "BOTH_DEAD" strategies and removes them
    4. (Optional) re-runs pattern_miner_v3 to find new patterns
    5. (Optional) re-runs validate_mined_full to rigor-test new patterns
    6. Calls merge_validated_patterns to rebuild whitelist
    7. Logs the change-set so the user can see what was added/removed
    8. Restarts the bot if anything changed

Usage:
    # cron entry: every Sunday at 03:00 UTC
    0 3 * * 0 /usr/bin/python -m research.retrain_loop --full

    python -m research.retrain_loop --check-only   # just runs decay detection
    python -m research.retrain_loop --full          # full re-mine + re-validate
    python -m research.retrain_loop --remine-only   # mine new patterns, don't drop old
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = PROJECT_ROOT / "logs" / "retrain.log"
WHITELIST_BACKUP = PROJECT_ROOT / "data" / "whitelist_history.jsonl"


def log(msg: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now(timezone.utc).isoformat()}] {msg}"
    print(line)
    with LOG_PATH.open("a") as f:
        f.write(line + "\n")


def run(cmd: list[str]) -> int:
    log(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=PROJECT_ROOT).returncode


def snapshot_whitelist() -> dict:
    val = json.loads((PROJECT_ROOT / "data" / "validation_results.json").read_text())
    sigs = {k: v for k, v in val["signals"].items() if v.get("recommended")}
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "n_total": len(sigs),
        "n_long": sum(1 for k, v in sigs.items()
                       if (v.get("side") == "LONG") or "_LONG" in k),
        "n_short": sum(1 for k, v in sigs.items()
                        if (v.get("side") == "SHORT") or "_SHORT" in k),
        "names": sorted(sigs.keys()),
    }


def append_history(snapshot: dict) -> None:
    WHITELIST_BACKUP.parent.mkdir(parents=True, exist_ok=True)
    with WHITELIST_BACKUP.open("a") as f:
        f.write(json.dumps(snapshot, default=str) + "\n")


def check_decay() -> tuple[list[str], list[str]]:
    """Run recency_check.py and return (decayed_names, weaker_names)."""
    log("Running decay check (recency_check.py) ...")
    rc = run([sys.executable, "-m", "research.recency_check"])
    if rc != 0:
        log("WARN: recency_check failed; aborting.")
        return [], []
    res = json.loads((PROJECT_ROOT / "data" / "recency_check.json").read_text())
    decayed = [r["name"] for r in res["results"]
               if r["verdict"] in ("DECAYED", "BOTH_DEAD")]
    weaker = [r["name"] for r in res["results"] if r["verdict"] == "WEAKER"]
    log(f"  Decayed: {len(decayed)}    Weaker: {len(weaker)}")
    return decayed, weaker


def drop_signals(names: list[str]) -> int:
    """Remove the given strategy names from validation_results.json (recommended=False)."""
    if not names:
        return 0
    p = PROJECT_ROOT / "data" / "validation_results.json"
    val = json.loads(p.read_text())
    sigs = val["signals"]
    n_dropped = 0
    for name in names:
        if name in sigs and sigs[name].get("recommended"):
            sigs[name]["recommended"] = False
            sigs[name]["dropped_at"] = datetime.now(timezone.utc).isoformat()
            n_dropped += 1
    val["last_updated"] = datetime.now(timezone.utc).isoformat()
    p.write_text(json.dumps(val, indent=2, default=str))
    log(f"  Dropped {n_dropped} strategies from whitelist: {names}")
    return n_dropped


def remine_v3() -> int:
    """Run a fresh v3 mining pass on both sides at standard RR."""
    log("Re-mining v3 patterns ...")
    return run([
        sys.executable, "-m", "research.pattern_miner_v3",
        "--combos", "8/25,10/30,12/35,15/45",
        "--target-rr", "2.0",
        "--min-train-wr", "0.55",
        "--min-cpcv-mean-wr", "0.52",
        "--min-cpcv-fold-wr", "0.45",
        "--min-trades-per-week", "2.0",
        "--max-depth", "10",
        "--min-leaf", "200",
        "--top", "20",
        "--seeds", "42,7",
        "--results-path", "data/mined_v3_retrain.json",
    ])


def validate_remine() -> int:
    log("Validating re-mine ...")
    return run([
        sys.executable, "-m", "research.validate_mined_full",
        "--input", "data/mined_v3_retrain.json",
        "--output", "data/validated_v3_retrain.json",
        "--n-perm", "300", "--n-mc", "5000",
    ])


def merge() -> int:
    log("Merging validated patterns into whitelist ...")
    return run([sys.executable, "-m", "research.merge_validated_patterns"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--check-only", action="store_true",
                   help="Just run decay detection. Don't mine new patterns.")
    p.add_argument("--full", action="store_true",
                   help="Decay-check + drop + re-mine + re-validate + merge")
    p.add_argument("--remine-only", action="store_true",
                   help="Skip decay step; only mine new patterns + merge.")
    p.add_argument("--restart-bot", action="store_true",
                   help="Send SIGTERM to bot process so it picks up new whitelist.")
    args = p.parse_args()

    log("=" * 60)
    log(f"RETRAIN-LOOP started  mode={'full' if args.full else ('check' if args.check_only else 'remine')}")

    before = snapshot_whitelist()
    log(f"Before: {before['n_total']} strategies "
        f"(LONG={before['n_long']}, SHORT={before['n_short']})")

    if not args.remine_only:
        decayed, weaker = check_decay()
        if decayed:
            drop_signals(decayed)

    if args.full or args.remine_only:
        if remine_v3() == 0:
            validate_remine()
            merge()

    after = snapshot_whitelist()
    log(f"After:  {after['n_total']} strategies "
        f"(LONG={after['n_long']}, SHORT={after['n_short']})")

    added = sorted(set(after["names"]) - set(before["names"]))
    removed = sorted(set(before["names"]) - set(after["names"]))
    log(f"Added: {len(added)}   {added}")
    log(f"Removed: {len(removed)}   {removed}")

    append_history({**after, "added": added, "removed": removed})

    if args.restart_bot and (added or removed):
        log("Restarting bot (SIGTERM to bot main process if running) ...")
        # Best-effort: find any running bot by name
        try:
            subprocess.run(["pkill", "-TERM", "-f", "python -m bot"],
                           cwd=PROJECT_ROOT)
        except Exception as e:
            log(f"  pkill failed: {e}")

    log("RETRAIN-LOOP done")


if __name__ == "__main__":
    main()
