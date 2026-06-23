"""Extract candidate strategy names from round7_summary.csv.

Three tiers:
  PASS:   trades/day>=300 AND wr>=0.45 AND $/day>=1000 AND maxDD<=5000
  CLOSE:  $/day>0 AND (wr>=0.40 OR trades/day>=200) — for 60d re-test
  TOP20:  Top 20 by $/day with $/day>0 — for 60d re-test
"""
import csv
import sys


def main(csv_path="/home/user/HFTBot/research/round7_summary.csv"):
    rows = []
    with open(csv_path) as f:
        for r in csv.DictReader(f):
            rows.append({
                'name': r['name'],
                'n': int(r['trades']),
                'tpd': float(r['trades_per_day']),
                'wr': float(r['wr']),
                'per_day': float(r['per_day']),
                'max_dd': float(r['max_dd']),
                'sharpe': float(r['sharpe']),
            })
    rows.sort(key=lambda r: -r['per_day'])

    pass_set = [r for r in rows if r['tpd'] >= 300 and r['wr'] >= 0.45
                and r['per_day'] >= 1000 and r['max_dd'] <= 5000]
    print(f"FULL_PASS: {len(pass_set)}")
    for r in pass_set:
        print(f"  {r['name']}: {r['tpd']:.0f}/d, WR={r['wr']*100:.1f}%, ${r['per_day']:.0f}/d, DD=${r['max_dd']:.0f}")

    # Tier 2: positive $/day with decent volume/WR
    close = [r for r in rows
             if r['per_day'] > 0 and r['n'] >= 50
             and (r['wr'] >= 0.40 or r['tpd'] >= 200)]
    print(f"\nCLOSE (positive + WR>=40% or vol>=200/d): {len(close)}")
    for r in close[:30]:
        print(f"  {r['name']}: {r['tpd']:.0f}/d, WR={r['wr']*100:.1f}%, ${r['per_day']:.0f}/d, DD=${r['max_dd']:.0f}")

    top20 = [r for r in rows if r['per_day'] > 0][:20]
    print(f"\nTOP-20 by $/day (positive only): {len(top20)}")
    for i, r in enumerate(top20, 1):
        print(f"  {i:2d}. {r['name']}: {r['tpd']:.1f}/d, WR={r['wr']*100:.1f}%, ${r['per_day']:.0f}/d, DD=${r['max_dd']:.0f}")

    # Output candidates as comma-list for 60d harness
    candidates = list({r['name'] for r in pass_set + close[:30] + top20})
    print(f"\nCANDIDATES_CSV ({len(candidates)}):")
    print(",".join(candidates))


if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "/home/user/HFTBot/research/round7_summary.csv"
    main(csv_path)
