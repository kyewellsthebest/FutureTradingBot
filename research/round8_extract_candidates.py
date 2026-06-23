"""Extract strategy names from round8_summary.csv that are worth re-testing
on the 60-day window. Criteria:

  Tier 1: FULL_PASS on 14-day (the holy grail — re-test all)
  Tier 2: Closest candidates by min-ratio score (per round 7 style)
  Tier 3: Top 20 by $/day with >=50 trades
  Tier 4: Top 20 by WR with >=50 trades AND $/day > 0
  Tier 5: Top 20 by trades-per-day with WR >= 40% (volume hints)

Outputs candidate set as comma-separated names to stdout.
"""
from __future__ import annotations
import argparse
import csv
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="/home/user/HFTBot/research/round8_summary.csv")
    ap.add_argument("--n-per-tier", type=int, default=15)
    args = ap.parse_args()

    rows = []
    with open(args.csv) as f:
        rd = csv.DictReader(f)
        for r in rd:
            try:
                r['n'] = int(r['trades'])
                r['tpd'] = float(r['trades_per_day'])
                r['wr'] = float(r['wr'])
                r['per_day'] = float(r['per_day'])
                r['max_dd'] = float(r['max_dd'])
            except Exception:
                continue
            rows.append(r)

    candidates = set()

    # Tier 1: FULL_PASS on 14-day
    t1 = [r for r in rows if r['tpd'] >= 300 and r['wr'] >= 0.45
          and r['per_day'] >= 1000 and r['max_dd'] <= 5000]
    for r in t1:
        candidates.add(r['name'])
    print(f"# Tier 1 (FULL_PASS on 14d): {len(t1)}", file=sys.stderr)

    # Tier 2: min-ratio score
    scored = []
    for r in rows:
        if r['n'] < 50:
            continue
        score_vol = r['tpd'] / 300
        score_wr = r['wr'] / 0.45
        score_pnl = r['per_day'] / 1000 if r['per_day'] > 0 else -1
        score_dd = 5000 / max(1.0, r['max_dd'])
        score = min(score_vol, score_wr, score_pnl, score_dd)
        scored.append((score, r))
    scored.sort(key=lambda x: -x[0])
    n = 0
    for sc, r in scored:
        if r['per_day'] > 0:
            candidates.add(r['name'])
            n += 1
            if n >= args.n_per_tier:
                break
    print(f"# Tier 2 (min-ratio close, n>=50, $/day>0): added {n}", file=sys.stderr)

    # Tier 3: top by $/day (n>=50)
    high_pnl = sorted([r for r in rows if r['n'] >= 50],
                      key=lambda r: -r['per_day'])[:args.n_per_tier]
    for r in high_pnl:
        candidates.add(r['name'])
    print(f"# Tier 3 (top $/day, n>=50): added {len(high_pnl)}", file=sys.stderr)

    # Tier 4: top by WR with $/day > 0
    high_wr = sorted([r for r in rows if r['n'] >= 50 and r['per_day'] > 0],
                    key=lambda r: -r['wr'])[:args.n_per_tier]
    for r in high_wr:
        candidates.add(r['name'])
    print(f"# Tier 4 (top WR, n>=50, $/day>0): added {len(high_wr)}", file=sys.stderr)

    # Tier 5: high-volume hints (>=200 trades, wr>=0.40)
    high_vol = sorted([r for r in rows if r['n'] >= 200 and r['wr'] >= 0.40],
                     key=lambda r: -r['tpd'])[:args.n_per_tier]
    for r in high_vol:
        candidates.add(r['name'])
    print(f"# Tier 5 (high vol, WR>=40%): added {len(high_vol)}", file=sys.stderr)

    out = sorted(candidates)
    print(f"# TOTAL UNIQUE candidates: {len(out)}", file=sys.stderr)
    print(",".join(out))


if __name__ == "__main__":
    main()
