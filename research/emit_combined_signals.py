"""
Combine multiple mined-pattern JSONs into a single mined_v3_signals.py.

Reads all data/mined_v3_*.json files, dedupes patterns by their full
constraint set, emits one Signal class per unique pattern. The result
is what the engine will whitelist + trade.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
OUT = PROJECT_ROOT / "research" / "mined_v3_signals.py"

# Files to combine (most-recent leak-fixed runs only)
SOURCES = [
    "mined_v3_rr10.json",
    "mined_v3_broad.json",
    "mined_v3_wide.json",
]


def main():
    seen_constraints: set = set()
    all_patterns: list[dict] = []
    for fname in SOURCES:
        p = DATA / fname
        if not p.exists():
            print(f"  skip missing {fname}")
            continue
        d = json.loads(p.read_text())
        pats = d.get("patterns") or []
        added = 0
        for pp in pats:
            cons_key = (pp["side"], float(pp["stop_pts"]), float(pp["target_pts"]),
                          int(pp.get("max_hold", 0)),
                          tuple(tuple(c) for c in pp.get("constraints", [])))
            if cons_key in seen_constraints:
                continue
            seen_constraints.add(cons_key)
            pp["_source"] = fname
            all_patterns.append(pp)
            added += 1
        print(f"  {fname}: {added} new (of {len(pats)} in file)")
    print(f"\ntotal unique patterns: {len(all_patterns)}")
    print(f"  LONG:  {sum(1 for p in all_patterns if p['side']=='LONG')}")
    print(f"  SHORT: {sum(1 for p in all_patterns if p['side']=='SHORT')}")

    # Renumber names so emitted file has clean unique names
    long_idx = 0; short_idx = 0
    for p in all_patterns:
        s = int(p["stop_pts"]); t = int(p["target_pts"])
        if p["side"] == "LONG":
            long_idx += 1
            p["name"] = f"V3_LONG_S{s}T{t}_{long_idx:03d}"
        else:
            short_idx += 1
            p["name"] = f"V3_SHORT_S{s}T{t}_{short_idx:03d}"

    # Emit
    lines = [
        '"""',
        'Auto-generated v3 pattern Signal classes.',
        f'Generated: {datetime.now(timezone.utc).isoformat()}',
        f'Survivors: {len(all_patterns)}  (LONG={long_idx}, SHORT={short_idx})',
        f'Sources: {SOURCES}',
        'Validation: deep tree + 5-fold CPCV (Lopez de Prado),',
        '            leak-fixed _attach_prev_day_levels (UTC dates).',
        '"""',
        'from __future__ import annotations',
        'import pandas as pd',
        '',
        'from research.pattern_miner_v3 import build_v3_features',
        '',
    ]
    cls_names = []
    for i, p in enumerate(all_patterns):
        cname = f"V3{p['side'].capitalize()}S{int(p['stop_pts'])}T{int(p['target_pts'])}_{i+1:04d}"
        cls_names.append(cname)
        lines.append(f"class {cname}:")
        lines.append(f"    name = {p['name']!r}")
        lines.append(f"    side = {p['side']!r}")
        lines.append(f"    target_pts = {float(p['target_pts'])!r}")
        lines.append(f"    stop_pts = {float(p['stop_pts'])!r}")
        lines.append(f"    max_hold_bars = {int(p.get('max_hold', 30))!r}")
        lines.append(f"    cpcv_mean_wr = {float(p.get('cpcv_mean_wr', 0.0))!r}")
        lines.append(f"    cpcv_min_wr = {float(p.get('cpcv_min_wr', 0.0))!r}")
        lines.append("    constraints = [")
        for feat, op, thr in p.get("constraints", []):
            lines.append(f"        ({feat!r}, {op!r}, {thr!r}),")
        lines.append("    ]")
        lines.append("")
        lines.append("    def generate(self, intraday, daily):")
        lines.append("        feats = build_v3_features(intraday, daily)")
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
        lines.append(f"        sign = 1 if {p['side']!r} == 'LONG' else -1")
        lines.append("        return pd.DataFrame({")
        lines.append("            'signal_time': idx, 'signal_name': self.name,")
        lines.append(f"            'side': {p['side']!r},")
        lines.append("            'entry_px': c.values,")
        lines.append("            'target_hint': c.values + sign * self.target_pts,")
        lines.append("        })")
        lines.append("")
    lines.append("ALL_V3_SIGNALS = [")
    for c in cls_names:
        lines.append(f"    {c}(),")
    lines.append("]")
    OUT.write_text("\n".join(lines))
    print(f"\nWrote {OUT.relative_to(PROJECT_ROOT)} ({OUT.stat().st_size//1024}KB)")

    # Apply to validation_results.json
    val_path = DATA / "validation_results.json"
    val = json.loads(val_path.read_text())
    sigs = val.get("signals") or {}
    for n in sigs:
        sigs[n]["recommended"] = False
        if sigs[n].get("tier") == "A":
            sigs[n]["tier"] = "C"
    for p in all_patterns:
        n = p["name"]
        if n not in sigs: sigs[n] = {}
        sigs[n].update({
            "recommended": True, "tier": "A",
            "side": p["side"],
            "stop_pts": float(p["stop_pts"]),
            "target_pts": float(p["target_pts"]),
            "win_rate": float(p["cpcv_mean_wr"]),
            "trades": int(p["n_total"]),
            "rigor_level": "leak_fixed_v3_combined",
        })
    val["signals"] = sigs
    val["last_remine_combined"] = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "sources": SOURCES,
        "n_total": len(all_patterns),
    }
    val_path.write_text(json.dumps(val, indent=2, default=str))
    (PROJECT_ROOT/"bundled"/"validation_results.json").write_text(val_path.read_text())
    print(f"applied {len(all_patterns)} as Tier A in validation_results.json")


if __name__ == "__main__":
    main()
