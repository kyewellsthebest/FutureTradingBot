"""
Pre-validation filter — collapses many redundant mined patterns down to a
manageable set for the 5-test gauntlet.

Reads one or more `mined_v3_*.json` files, dedups by constraint signature
(same as merge step), scores each by `cpcv_mean_wr × n_total^0.3`, keeps
the top N globally, and writes a single combined JSON ready for the validator.

Usage:
    python -m research.filter_mined_patterns \\
        --inputs data/mined_v3_long_rr25.json,data/mined_v3_long_rr30.json \\
        --output data/mined_v3_long_top.json \\
        --top 60
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--inputs", required=True,
                   help="Comma-separated mined_v3_*.json paths")
    p.add_argument("--output", required=True)
    p.add_argument("--top", type=int, default=60,
                   help="Keep top N globally by quality score")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    files = [PROJECT_ROOT / s.strip() for s in args.inputs.split(",")]

    all_pats = []
    for f in files:
        if not f.exists():
            print(f"  missing: {f}"); continue
        d = json.loads(f.read_text())
        for p in d.get("patterns", []):
            p["_source"] = f.name
            all_pats.append(p)

    print(f"Loaded {len(all_pats)} raw patterns from {len(files)} files")

    # Dedup by constraint signature
    seen = {}
    for p in all_pats:
        key = (p["side"], int(p["stop_pts"]), int(p["target_pts"]),
               int(p["max_hold"]),
               tuple(sorted(tuple(c) for c in p["constraints"])))
        prev = seen.get(key)
        if prev is None:
            seen[key] = p
            continue
        # Keep highest cpcv_mean_wr × n_total^0.3
        def _score(x):
            return float(x.get("cpcv_mean_wr", 0)) * (max(1, int(x.get("n_total", 1))) ** 0.3)
        if _score(p) > _score(prev):
            seen[key] = p
    deduped = list(seen.values())
    print(f"Deduped to {len(deduped)} unique patterns")

    # Score and keep top N
    def _score(x):
        wr = float(x.get("cpcv_mean_wr", 0))
        n = max(1, int(x.get("n_total", 1)))
        # Reward higher WR + more trades. Penalize tiny samples.
        return wr * (n ** 0.3)

    deduped.sort(key=_score, reverse=True)
    kept = deduped[: args.top]
    print(f"Kept top {len(kept)} by score")
    print()
    print(f"  {'name':<28} {'side':<5} {'stop':<5} {'tgt':<5} {'RR':<5} "
          f"{'WR_mean':>7} {'WR_min':>7} {'#trades':>8} {'score':>7}")
    print("  " + "-" * 90)
    for r in kept[:30]:
        rr = r['target_pts']/r['stop_pts']
        print(f"  {r['name']:<28} {r['side']:<5} {r['stop_pts']:<5g} "
              f"{r['target_pts']:<5g} 1:{rr:<3.1f} "
              f"{r['cpcv_mean_wr']*100:>6.1f}% {r['cpcv_min_wr']*100:>6.1f}% "
              f"{r['n_total']:>8} {_score(r):>7.2f}")
    if len(kept) > 30:
        print(f"  ... and {len(kept)-30} more")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_files": [str(f.relative_to(PROJECT_ROOT)) for f in files if f.exists()],
        "n_raw": len(all_pats), "n_deduped": len(deduped), "n_kept": len(kept),
        "top": args.top,
        "patterns": kept,
        "params": {"selection": "top by cpcv_mean_wr × n_total^0.3"},
    }
    out = PROJECT_ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\n  Wrote -> {out.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
