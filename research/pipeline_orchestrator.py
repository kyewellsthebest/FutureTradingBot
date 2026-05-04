"""
Auto-resuming pipeline orchestrator.

Runs the BEST-CASE strategy hunt end-to-end. Each phase is wrapped in
retry/timeout logic. State is persisted to disk after each phase so
restarts pick up where things stopped.

Phases:
  1. raw_validate    — fast 5-test screen on raw signal outcomes
  2. apply_raw       — provisional whitelist = raw survivors
  3. live_sim_raw    — verify raw survivors hold up under engine + Lucid
  4. mine_v4         — pattern_miner_v4 hunts for NEW strategies
  5. raw_validate2   — re-screen with new mined patterns added
  6. apply_final     — final whitelist = all survivors
  7. live_sim_final  — full 12-month sim with FINAL whitelist
  8. report          — generate FINAL_REPORT.html + summary

State machine: data/pipeline_state.json
  {"phase": "raw_validate", "status": "running" | "ok" | "fail",
   "attempts": 1, "last_run": "...", "results_path": "..."}

Run with:  setsid nohup python3 -u -m research.pipeline_orchestrator > /tmp/pipeline.log 2>&1 < /dev/null & disown
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
STATE_PATH = DATA / "pipeline_state.json"
LOG_PATH = PROJECT_ROOT / "logs" / "pipeline.log"
LOG_PATH.parent.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s pipeline %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout),
                              logging.FileHandler(LOG_PATH)])
log = logging.getLogger("pipeline")


# ---------------------------------------------------------------- state --

def _load_state() -> dict:
    if STATE_PATH.exists():
        try: return json.loads(STATE_PATH.read_text())
        except Exception: pass
    return {"phases": {}, "started_at": datetime.now(timezone.utc).isoformat()}


def _save_state(s: dict) -> None:
    s["last_update"] = datetime.now(timezone.utc).isoformat()
    STATE_PATH.write_text(json.dumps(s, indent=2, default=str))


def _phase_complete(state: dict, phase: str) -> bool:
    return state.get("phases", {}).get(phase, {}).get("status") == "ok"


def _mark(state: dict, phase: str, status: str, **kw) -> None:
    state.setdefault("phases", {})[phase] = {
        "status": status,
        "ran_at": datetime.now(timezone.utc).isoformat(),
        **kw,
    }
    _save_state(state)


# ---------------------------------------------------------------- runners --

def _run_module(module: str, timeout_s: int = 7200,
                 args: list[str] | None = None) -> tuple[bool, str]:
    """Run `python -m <module> [args]` with timeout. Returns (ok, tail_log)."""
    cmd = ["python3", "-u", "-m", module] + (args or [])
    log.info(f"  → running: {' '.join(cmd)} (timeout {timeout_s}s)")
    try:
        p = subprocess.run(cmd, cwd=str(PROJECT_ROOT),
                            capture_output=True, text=True, timeout=timeout_s,
                            check=False)
        tail = (p.stdout + "\n" + p.stderr).splitlines()[-30:]
        if p.returncode != 0:
            return False, "\n".join(tail) + f"\n  [exit {p.returncode}]"
        return True, "\n".join(tail)
    except subprocess.TimeoutExpired:
        return False, f"  [TIMEOUT after {timeout_s}s]"
    except Exception as e:
        return False, f"  [exception: {e!r}]\n{traceback.format_exc()[-1500:]}"


def _git_commit_push(message: str) -> None:
    """Best-effort commit + push of any new artifacts."""
    try:
        subprocess.run(["git", "add", "-A"], cwd=str(PROJECT_ROOT), check=False)
        # Skip if nothing to commit
        s = subprocess.run(["git", "diff", "--cached", "--quiet"],
                            cwd=str(PROJECT_ROOT))
        if s.returncode == 0:
            log.info("  (nothing to commit)")
            return
        subprocess.run(["git", "commit", "-m", message],
                       cwd=str(PROJECT_ROOT), check=False, capture_output=True)
        for attempt in range(4):
            r = subprocess.run(["git", "push", "-u", "origin",
                                  "claude/transfer-trading-bot-GiNxs"],
                                 cwd=str(PROJECT_ROOT),
                                 capture_output=True, text=True)
            if r.returncode == 0:
                log.info("  ✓ pushed")
                return
            log.warning(f"  push attempt {attempt+1} failed: {r.stderr[:200]}")
            time.sleep(2 ** (attempt + 1))
        log.error("  ✗ push failed after 4 attempts")
    except Exception as e:
        log.error(f"  git error: {e}")


# ---------------------------------------------------------------- phases --

def phase_raw_validate(state: dict) -> bool:
    """Fast raw-signal validator across all 221 candidate strategies."""
    log.info("PHASE: raw_validate")
    ok, tail = _run_module("research.raw_validator", timeout_s=600)
    log.info(tail)
    _mark(state, "raw_validate", "ok" if ok else "fail",
            output_tail=tail[-2000:])
    return ok


def phase_apply_raw_survivors(state: dict) -> bool:
    """Apply raw-validator survivors as the provisional whitelist."""
    log.info("PHASE: apply_raw_survivors")
    raw_path = DATA / "raw_validation_results.json"
    if not raw_path.exists():
        _mark(state, "apply_raw_survivors", "fail", reason="no raw results")
        return False
    raw = json.loads(raw_path.read_text())
    survivors = sorted([r["name"] for r in raw["results"] if r["passes_all"]])
    val_path = DATA / "validation_results.json"
    backup_path = DATA / "validation_results_pre_pipeline.json"
    if not backup_path.exists():
        backup_path.write_text(val_path.read_text())
    val = json.loads(val_path.read_text())
    sigs = val.get("signals") or {}
    n_set = 0
    for name in list(sigs.keys()):
        is_keeper = name in survivors
        if is_keeper:
            sigs[name]["recommended"] = True
            sigs[name]["tier"] = "A"
            n_set += 1
        else:
            sigs[name]["recommended"] = False
            if sigs[name].get("tier") == "A":
                sigs[name]["tier"] = "C"
    val["signals"] = sigs
    val["pipeline_provisional"] = dict(survivors=survivors, n=n_set,
                                          set_at=datetime.now(timezone.utc).isoformat())
    val_path.write_text(json.dumps(val, indent=2, default=str))
    bundled = PROJECT_ROOT / "bundled" / "validation_results.json"
    if bundled.parent.exists():
        bundled.write_text(val_path.read_text())
    log.info(f"  set {n_set} strategies as provisional Tier A: {survivors}")
    _mark(state, "apply_raw_survivors", "ok", n=n_set, survivors=survivors)
    return True


def phase_live_sim(state: dict, label: str = "raw_survivors") -> bool:
    """Run the realistic live_sim with the current whitelist."""
    log.info(f"PHASE: live_sim ({label})")
    # Save aside any existing results
    json_path = DATA / "live_sim_results.json"
    html_path = DATA / "live_sim_report.html"
    archive_json = DATA / f"live_sim_results_{label}.json"
    archive_html = DATA / f"live_sim_report_{label}.html"
    ok, tail = _run_module("research.live_sim", timeout_s=10800)  # 3h cap
    log.info(tail)
    if ok and json_path.exists():
        archive_json.write_text(json_path.read_text())
        if html_path.exists():
            archive_html.write_text(html_path.read_text())
    _mark(state, f"live_sim_{label}", "ok" if ok else "fail",
            output_tail=tail[-2000:],
            archive_json=str(archive_json) if ok else None)
    return ok


def phase_mine_v4(state: dict) -> bool:
    """Run pattern_miner_v4 to discover new strategies."""
    log.info("PHASE: mine_v4")
    miner_path = PROJECT_ROOT / "research" / "pattern_miner_v4.py"
    if not miner_path.exists():
        log.warning("  pattern_miner_v4.py not found — skipping")
        _mark(state, "mine_v4", "skip", reason="miner script missing")
        return True
    ok, tail = _run_module("research.pattern_miner_v4", timeout_s=14400)  # 4h cap
    log.info(tail)
    _mark(state, "mine_v4", "ok" if ok else "fail",
            output_tail=tail[-2000:])
    return ok


def phase_final_report(state: dict) -> bool:
    """Write a FINAL_REPORT summarising what we found."""
    log.info("PHASE: final_report")
    raw_path = DATA / "raw_validation_results.json"
    sims = {}
    for label in ("raw_survivors", "final"):
        p = DATA / f"live_sim_results_{label}.json"
        if p.exists():
            sims[label] = json.loads(p.read_text())
    raw = json.loads(raw_path.read_text()) if raw_path.exists() else {}
    survivors = sorted([r for r in raw.get("results", []) if r.get("passes_all")],
                        key=lambda r: -r["net_pnl_per_contract"])
    summary_lines = [
        "FINAL PIPELINE REPORT",
        "=" * 72,
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        f"Phases run: {list(state.get('phases', {}).keys())}",
        "",
        "=== RAW-SIGNAL SURVIVORS (5 rigorous tests) ===",
    ]
    for r in survivors:
        summary_lines.append(
            f"  {r['name']:<32}  {r['side']:<5}  n={r['n_executed']:>4}  "
            f"WR={r['win_rate']*100:.1f}%  PF={r['profit_factor']:.2f}  "
            f"Sh={r['sharpe']:+.2f}  ${r['net_pnl_per_contract']:+,.0f}/contract"
        )
    if sims:
        summary_lines.append("")
        summary_lines.append("=== LIVE-SIM RESULTS (engine + Lucid) ===")
        for label, sim in sims.items():
            wr = sim.get("win_rate", 0) * 100
            summary_lines.append(
                f"  [{label}] {sim['trades_taken']:>4} trades, "
                f"WR {wr:.1f}%, P&L ${sim['total_pnl']:+,.0f}, "
                f"final ${sim['ending_balance']:,.0f}, "
                f"failed {sim.get('n_failed_accounts', 0)} accts"
            )
    out_md = DATA / "FINAL_REPORT.md"
    out_md.write_text("\n".join(summary_lines))
    log.info(f"\n" + "\n".join(summary_lines))
    _mark(state, "final_report", "ok", path=str(out_md))
    return True


# ---------------------------------------------------------------- main --

def main():
    state = _load_state()
    log.info(f"=== PIPELINE START === state file: {STATE_PATH}")

    # Phase 1: raw_validate (idempotent — re-runnable)
    if not _phase_complete(state, "raw_validate"):
        for attempt in range(3):
            if phase_raw_validate(state): break
            log.warning(f"  raw_validate failed, attempt {attempt+1}/3")
            time.sleep(15)
        _git_commit_push("pipeline: raw_validator results")

    # Phase 2: apply raw survivors as whitelist
    if not _phase_complete(state, "apply_raw_survivors"):
        phase_apply_raw_survivors(state)
        _git_commit_push("pipeline: applied raw survivors as Tier A whitelist")

    # Phase 3: live_sim with raw-survivor whitelist
    if not _phase_complete(state, "live_sim_raw_survivors"):
        for attempt in range(2):
            if phase_live_sim(state, label="raw_survivors"): break
            log.warning(f"  live_sim failed, attempt {attempt+1}/2")
            time.sleep(60)
        _git_commit_push("pipeline: live_sim results with raw-survivor whitelist")

    # Phase 4: mine_v4 — discover new patterns (best-effort, may take hours)
    if not _phase_complete(state, "mine_v4"):
        phase_mine_v4(state)
        _git_commit_push("pipeline: pattern_miner_v4 mining results")
        # Re-validate raw signals (may now include miner output)
        if state["phases"].get("mine_v4", {}).get("status") == "ok":
            log.info("  re-running raw_validator with mined patterns included …")
            phase_raw_validate(state)
            phase_apply_raw_survivors(state)
            phase_live_sim(state, label="final")
            _git_commit_push("pipeline: final live_sim with mined patterns")

    # Phase final: report
    phase_final_report(state)
    _git_commit_push("pipeline: FINAL_REPORT.md")

    log.info("=== PIPELINE COMPLETE ===")


if __name__ == "__main__":
    while True:
        try:
            main()
            break
        except Exception as e:
            log.exception(f"main() crashed: {e}; restarting in 60s")
            time.sleep(60)
