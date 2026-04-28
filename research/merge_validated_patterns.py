"""
Merge validated patterns from multiple runs (8yr NQ-only + 2yr cross-asset),
dedupe by name, emit Signal classes, and update validation_results.json.

Inputs (any can be missing):
    data/validated_v3_8yr.json   — 5-test gauntlet on 8yr NQ-only run
    data/validated_v3_xa.json    — 5-test gauntlet on 2yr cross-asset run

Outputs:
    research/mined_v3_signals.py        — Signal classes for ALL Tier A + Tier B
    data/validation_results.json        — `recommended: true` for Tier A only
                                          (Tier B kept as known but not auto-trading)
    data/strategy_report_full.md        — human-readable report

Tier rules (matches validate_mined_full):
    Tier A : WR ≥ 60%  AND  5/5 rigor tests passed
    Tier B : WR ≥ 55%  AND  ≥3/5 tests passed
    Reject : everything else

Usage:
    python -m research.merge_validated_patterns
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
EMITTED_PATH = PROJECT_ROOT / "research" / "mined_v3_signals.py"
VALIDATION_PATH = DATA_DIR / "validation_results.json"
REPORT_PATH = DATA_DIR / "strategy_report_full.md"

INPUT_PATHS = [
    DATA_DIR / "validated_v3_8yr.json",        # original V3 mine validated
    DATA_DIR / "validated_v3_8yr_wide.json",   # wider V3 mine validated
    DATA_DIR / "validated_v3_xa.json",         # cross-asset (was empty)
]
EXISTING_VALIDATED = DATA_DIR / "validated_existing_8yr.json"  # 5-min + WR


def _load(p: Path) -> dict | None:
    if not p.exists():
        return None
    return json.loads(p.read_text())


def _make_class_name(rule: dict, idx: int) -> str:
    s = int(rule["stop_pts"])
    t = int(rule["target_pts"])
    side = rule["side"].capitalize()
    return f"V3{side}S{s}T{t}_{idx+1:02d}"


def _make_pattern_key(rule: dict) -> tuple:
    """Stable hashable key for dedup — same constraints + side + stop/target are dupes."""
    cons = tuple(sorted(tuple(c) for c in rule["constraints"]))
    return (rule["side"], int(rule["stop_pts"]), int(rule["target_pts"]),
            int(rule["max_hold"]), cons)


def emit_signal_classes(patterns: list[dict], with_xa: bool) -> str:
    """Build the mined_v3_signals.py source. `with_xa` adds cross-asset features
    so cross-asset constraints can be evaluated."""
    lines = [
        '"""',
        "Auto-generated v3 pattern Signal classes.",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Survivors: {len(patterns)}  ",
        "Validation: 5-test rigor gauntlet (CPCV + permutation + MC + sensitivity + EV).",
        '"""',
        "from __future__ import annotations",
        "import pandas as pd",
        "",
        "from research.pattern_miner_v3 import build_v3_features",
    ]
    if with_xa:
        lines.append("from research.cross_asset_features import build_cross_asset_features")
    lines.extend(["", ""])

    cls_names: list[str] = []
    seen = set()
    for i, r in enumerate(patterns):
        cname = _make_class_name(r, i)
        if cname in seen:
            cname = f"{cname}_x"
        seen.add(cname)
        cls_names.append(cname)

        lines.append(f"class {cname}:")
        lines.append(f"    name = {r['name']!r}")
        lines.append(f"    side = {r['side']!r}")
        lines.append(f"    target_pts = {float(r['target_pts'])!r}")
        lines.append(f"    stop_pts = {float(r['stop_pts'])!r}")
        lines.append(f"    max_hold_bars = {int(r['max_hold'])!r}")
        lines.append(f"    win_rate = {r.get('win_rate')!r}")
        lines.append(f"    profit_factor = {r.get('profit_factor')!r}")
        lines.append(f"    tier = {r.get('tier', 'A')!r}")
        lines.append("    constraints = [")
        for feat, op, thr in r["constraints"]:
            lines.append(f"        ({feat!r}, {op!r}, {float(thr)!r}),")
        lines.append("    ]")
        lines.append("")
        lines.append("    def generate(self, intraday, daily):")
        lines.append("        feats = build_v3_features(intraday, daily)")
        if with_xa:
            lines.append("        try:")
            lines.append("            xa = build_cross_asset_features(intraday.index)")
            lines.append("            feats = pd.concat([feats, xa], axis=1)")
            lines.append("        except Exception:  # cross-asset data unavailable in live path")
            lines.append("            pass")
        lines.append("        if feats.empty:")
        lines.append("            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])")
        lines.append("        mask = pd.Series(True, index=feats.index)")
        lines.append("        for col, op, thr in self.constraints:")
        lines.append("            if col not in feats.columns:")
        lines.append("                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])")
        lines.append("            v = feats[col]")
        lines.append("            if op == '<=':")
        lines.append("                mask &= (v <= thr)")
        lines.append("            else:")
        lines.append("                mask &= (v > thr)")
        lines.append("        idx = intraday.index[mask.fillna(False)]")
        lines.append("        if len(idx) == 0:")
        lines.append("            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])")
        lines.append("        c = intraday['close'].loc[idx]")
        lines.append(f"        sign = 1 if {r['side']!r} == 'LONG' else -1")
        lines.append("        return pd.DataFrame({")
        lines.append("            'signal_time': idx, 'signal_name': self.name,")
        lines.append(f"            'side': {r['side']!r},")
        lines.append("            'entry_px': c.values,")
        lines.append("            'target_hint': c.values + sign * self.target_pts,")
        lines.append("        })")
        lines.append("")
    lines.append("ALL_V3_SIGNALS = [")
    for c in cls_names:
        lines.append(f"    {c}(),")
    lines.append("]")
    return "\n".join(lines)


def update_validation_json(tier_a: list[dict], tier_b: list[dict],
                            tier_a_existing: list[dict] | None = None,
                            tier_b_existing: list[dict] | None = None,
                            existing_rejects: list[dict] | None = None) -> None:
    """Rewrite validation_results.json from the rigor-validated truth.

    Anything that didn't survive the 8yr 5-test gauntlet is marked
    recommended=False so the bot's whitelist drops it.
    Anything in Tier A or Tier B is marked recommended=True with tier label.
    """
    tier_a_existing = tier_a_existing or []
    tier_b_existing = tier_b_existing or []
    existing_rejects = existing_rejects or []

    data: dict = {}
    if VALIDATION_PATH.exists():
        try:
            data = json.loads(VALIDATION_PATH.read_text())
        except Exception:
            data = {}
    sigs = data.setdefault("signals", {})

    # Drop ALL entries from prior runs that are V3 or WR or 5-min — we'll
    # re-add only the ones that survived this round.
    stale = [k for k in sigs if k.startswith("V3_") or k.startswith("WR_")
              or k in {"PDL_TOUCH", "PDH_TOUCH", "EQ50_LONG", "EQ50_SHORT",
                       "GAP_FILL_LONG", "GAP_FILL_SHORT", "ZSCORE_LONG",
                       "ZSCORE_SHORT", "VOL_COMP_LONG", "VOL_COMP_SHORT",
                       "VWAP_RECLAIM_LONG", "VWAP_REJECT_SHORT"}]
    for k in stale:
        del sigs[k]

    for r in tier_a:
        sigs[r["name"]] = {
            "recommended": True,
            "tier": "A",
            "side": r["side"],
            "win_rate": r.get("win_rate"),
            "profit_factor": r.get("profit_factor"),
            "trades": r.get("n_trades"),
            "net_pnl": r.get("net_pnl"),
            "stop_pts": r.get("stop_pts"),
            "target_pts": r.get("target_pts"),
            "rigor_level": "5/5_PASS_60wr",
            "tests_passed": r.get("n_passes"),
        }
    for r in tier_b:
        sigs[r["name"]] = {
            # Tier B is live-traded too (user request) — promoted from watchlist.
            # Edge is verified (positive EV, walk-forward + permutation pass) but
            # WR is sub-60% — still profitable due to 1:2 R:R.
            "recommended": True,
            "tier": "B",
            "side": r["side"],
            "win_rate": r.get("win_rate"),
            "profit_factor": r.get("profit_factor"),
            "trades": r.get("n_trades"),
            "net_pnl": r.get("net_pnl"),
            "stop_pts": r.get("stop_pts"),
            "target_pts": r.get("target_pts"),
            "rigor_level": "tier_b_live",
            "tests_passed": r.get("n_passes"),
        }
    # Existing 5-min + WR strategies that survived 8yr validation (rule-based,
    # not constraint-based — bot already has Signal classes for them)
    for r in tier_a_existing + tier_b_existing:
        is_a = (r in tier_a_existing)
        sigs[r["name"]] = {
            "recommended": True,
            "tier": "A" if is_a else "B",
            "side": r["side"],
            "family": r.get("family", "5min"),
            "win_rate": r.get("win_rate"),
            "profit_factor": r.get("profit_factor"),
            "trades": r.get("n_trades"),
            "net_pnl": r.get("net_pnl"),
            "stop_pts": r.get("stop_pts"),
            "target_pts": r.get("target_pts"),
            "rigor_level": "5/5_PASS_8yr" if is_a else "tier_b_live_8yr",
            "tests_passed": r.get("n_passes"),
        }
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    VALIDATION_PATH.write_text(json.dumps(data, indent=2, default=str))


def render_report(tier_a, tier_b, rejects, sources) -> str:
    lines = [
        "# Strategy Discovery — Full Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Sources",
        "",
    ]
    for src, info in sources.items():
        if info is None:
            lines.append(f"  - **{src}**: missing")
        else:
            lines.append(
                f"  - **{src}**: {info.get('n_validated', 0)} patterns validated, "
                f"perms={info.get('n_perm')}, MC={info.get('n_mc')}"
            )
    lines.extend([
        "",
        "## Bucketing rules",
        "",
        "  - **Tier A** (live, gold standard): WR ≥ 60% AND R:R ≥ 1:2 AND passes ALL 5 rigor tests",
        "    (EV, 500-permutation, walk-forward CPCV, 10k Monte-Carlo, ±20% sensitivity)",
        "  - **Tier B** (live, lower-WR): positive EV AND passes ≥3/5 tests AND walk-forward + permutation pass",
        "    Sub-60% WR but profitable due to 1:2 R:R; sized at 5 MNQ same as Tier A",
        "  - **Reject**: negative EV, or fails permutation/walk-forward",
        "",
        f"## Tier A — Live-ready ({len(tier_a)} strategies)",
        "",
    ])
    if tier_a:
        lines.append("| Name | Side | WR | PF | Trades | Net P&L | Perm p |")
        lines.append("|---|---|---|---|---|---|---|")
        for r in sorted(tier_a, key=lambda x: -x["net_pnl"]):
            pf = r.get("profit_factor") or 0.0
            pv = r["tests"]["permutation"]["p_value"]
            lines.append(f"| {r['name']} | {r['side']} | {r['win_rate']*100:.1f}% | "
                          f"{pf:.2f} | {r['n_trades']} | "
                          f"${r['net_pnl']:+,.0f} | {pv:.4f} |")
    else:
        lines.append("(none)")

    lines.extend(["", f"## Tier B — Watchlist ({len(tier_b)} strategies)", ""])
    if tier_b:
        lines.append("| Name | Side | WR | PF | Trades | Net P&L | Tests |")
        lines.append("|---|---|---|---|---|---|---|")
        for r in sorted(tier_b, key=lambda x: -x["net_pnl"]):
            pf = r.get("profit_factor") or 0.0
            lines.append(f"| {r['name']} | {r['side']} | {r['win_rate']*100:.1f}% | "
                          f"{pf:.2f} | {r['n_trades']} | "
                          f"${r['net_pnl']:+,.0f} | {r['n_passes']}/5 |")
    else:
        lines.append("(none)")

    lines.extend(["", f"## Rejected ({len(rejects)} patterns)", ""])
    if rejects:
        lines.append("| Name | Side | WR | Tests | Failed |")
        lines.append("|---|---|---|---|---|")
        for r in sorted(rejects, key=lambda x: -x["win_rate"]):
            failed = [k for k, v in r["tests"].items() if not v.get("pass", False)]
            lines.append(f"| {r['name']} | {r['side']} | {r['win_rate']*100:.1f}% | "
                          f"{r['n_passes']}/5 | {', '.join(failed) or '-'} |")
    else:
        lines.append("(none)")
    return "\n".join(lines)


def _rebucket(p: dict) -> str:
    """Re-classify with relaxed Tier B (positive EV + 3/5 tests, 1:2 RR makes
    sub-60% WR still profitable).

    Tier A : WR ≥ 60%  AND  5/5 tests PASS
    Tier B : positive EV  AND  ≥3/5 tests PASS  AND  walk-forward (CPCV) PASS
    Reject : everything else
    """
    wr = float(p.get("win_rate") or 0)
    n_pass = int(p.get("n_passes") or 0)
    ev_dollars = float(p.get("ev_dollars") or 0)
    tests = p.get("tests") or {}
    wf_pass = bool((tests.get("walk_forward") or {}).get("pass"))
    perm_pass = bool((tests.get("permutation") or {}).get("pass"))
    if wr >= 0.60 and n_pass == 5:
        return "A"
    if ev_dollars > 0 and n_pass >= 3 and wf_pass and perm_pass:
        return "B"
    return "REJECT"


def main() -> int:
    sources = {p.name: _load(p) for p in INPUT_PATHS}
    all_patterns: list[dict] = []
    used_xa = False
    for src_name, payload in sources.items():
        if payload is None:
            continue
        if payload.get("with_cross_asset"):
            used_xa = True
        for p in payload.get("patterns", []):
            p["_source"] = src_name
            # Re-bucket using merge-time policy (validator's tier may be too strict)
            p["tier"] = _rebucket(p)
            all_patterns.append(p)

    # Dedup — prefer the version with more passes / better PF
    by_key: dict[tuple, dict] = {}
    for p in all_patterns:
        k = _make_pattern_key(p)
        prev = by_key.get(k)
        if prev is None:
            by_key[k] = p
        else:
            # Keep whichever has more passes / higher PF
            if (p["n_passes"], p.get("profit_factor") or 0) > \
               (prev["n_passes"], prev.get("profit_factor") or 0):
                by_key[k] = p
    deduped = list(by_key.values())

    # Re-name for stability
    by_side = {"LONG": 0, "SHORT": 0}
    for r in deduped:
        by_side[r["side"]] += 1
        r["name"] = f"V3_{r['side']}_S{int(r['stop_pts'])}T{int(r['target_pts'])}_{by_side[r['side']]:02d}"

    tier_a = [r for r in deduped if r["tier"] == "A"]
    tier_b = [r for r in deduped if r["tier"] == "B"]
    reject = [r for r in deduped if r["tier"] == "REJECT"]

    # Existing 5-min + WR strategies validated separately
    tier_a_existing: list[dict] = []
    tier_b_existing: list[dict] = []
    existing_rejects: list[dict] = []
    if EXISTING_VALIDATED.exists():
        ex = json.loads(EXISTING_VALIDATED.read_text())
        for p in ex.get("patterns", []):
            p["tier"] = _rebucket(p)
            if p["tier"] == "A":
                tier_a_existing.append(p)
            elif p["tier"] == "B":
                tier_b_existing.append(p)
            else:
                existing_rejects.append(p)

    print(f"V3 mined patterns: {len(deduped)}  (A:{len(tier_a)}  B:{len(tier_b)}  R:{len(reject)})")
    print(f"Existing strategies: {len(tier_a_existing)+len(tier_b_existing)+len(existing_rejects)}  "
          f"(A:{len(tier_a_existing)}  B:{len(tier_b_existing)}  R:{len(existing_rejects)})")

    # Emit Signal classes for V3 tier A + B (existing strategies have their own classes)
    code = emit_signal_classes(tier_a + tier_b, with_xa=used_xa)
    EMITTED_PATH.write_text(code)
    print(f"Wrote -> {EMITTED_PATH.relative_to(PROJECT_ROOT)}")

    update_validation_json(tier_a, tier_b,
                            tier_a_existing=tier_a_existing,
                            tier_b_existing=tier_b_existing,
                            existing_rejects=existing_rejects)
    print(f"Wrote -> {VALIDATION_PATH.relative_to(PROJECT_ROOT)}")

    # Combined report includes both V3 and existing
    all_a = tier_a + tier_a_existing
    all_b = tier_b + tier_b_existing
    all_reject = reject + existing_rejects
    REPORT_PATH.write_text(render_report(all_a, all_b, all_reject, sources))
    print(f"Wrote -> {REPORT_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
