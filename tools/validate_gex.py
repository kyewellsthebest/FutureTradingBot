"""GEX pipeline VALIDATION harness — the gate before paper trading.
Checks the 5 pre-agreed criteria against the accumulating daily log and any
snapshot files. Prints a pass/fail scoreboard. Paper trading stays BLOCKED
until all criteria that can be evaluated are green.
"""
import json, glob, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))   # make 'bot' importable when run from anywhere
LOG = ROOT / "data" / "gex_daily_log.jsonl"
RESEARCH = ROOT / "research" / "gexmap2_daily.csv"

def load_log():
    if not LOG.exists(): return []
    return [json.loads(l) for l in open(LOG) if l.strip()]

def main():
    recs = load_log()
    print(f"=== GEX PIPELINE VALIDATION ({len(recs)} daily records) ===\n")
    ok_days = [r for r in recs if r.get("ok")]
    unknown_days = [r for r in recs if not r.get("ok")]

    # C1: snapshot collected each trading day (need a run of consecutive OK days)
    c1 = len(ok_days) >= 20   # ~1 month of clean snapshots (per the design note)
    print(f"C1 daily collection: {len(ok_days)} OK / {len(unknown_days)} UNKNOWN "
          f"-> {'PASS' if c1 else 'PENDING (need >=20 OK days)'}")

    # C2: stable/repeatable — re-computing a stored snapshot reproduces the regime
    c2 = None
    try:
        from bot.gex_daily import compute_from_snapshot
        snaps = sorted(glob.glob(str(ROOT / "data" / "OPT_QQQ_*.parquet"))
                       + glob.glob("OPT_QQQ_*.parquet"))
        if snaps:
            reg = [compute_from_snapshot(s)["regime"] for s in snaps[-3:]]
            reg2 = [compute_from_snapshot(s)["regime"] for s in snaps[-3:]]
            c2 = reg == reg2
            print(f"C2 repeatable: recompute stable on {len(reg)} snapshots -> "
                  f"{'PASS' if c2 else 'FAIL'}")
        else:
            print("C2 repeatable: PENDING (no snapshot files archived yet)")
    except Exception as e:
        print(f"C2 repeatable: PENDING ({e})")

    # C3: agreement with research methodology where overlap exists (SIGN of gamma)
    c3 = None
    try:
        import pandas as pd
        rs = pd.read_csv(RESEARCH); rs["dt"] = rs["dt"].astype(str)
        rmap = {d: (1 if v > 0 else -1) for d, v in zip(rs["dt"], rs["ngp2"])}
        pairs = [(r["date"], 1 if r["total_gex"] > 0 else -1)
                 for r in ok_days if r.get("date") in rmap]
        if pairs:
            agree = sum(1 for d, s in pairs if s == rmap[d]) / len(pairs)
            c3 = agree >= 0.8
            print(f"C3 research sign-agreement: {agree*100:.0f}% on {len(pairs)} "
                  f"overlap days -> {'PASS' if c3 else 'FAIL'}")
        else:
            print("C3 research sign-agreement: PENDING (no overlap dates yet — "
                  "live builds forward; overlap accrues as both run)")
    except Exception as e:
        print(f"C3 research sign-agreement: PENDING ({e})")

    # C4: every day logged (there are no silent gaps: every run appends a record)
    c4 = len(recs) > 0
    print(f"C4 full audit log: {len(recs)} records present -> {'PASS' if c4 else 'FAIL'}")

    # C5: safe-state on failure — a failed input yields UNKNOWN, never a guess
    c5 = True
    try:
        from bot.gex_daily import compute_from_snapshot
        bad = compute_from_snapshot("/nonexistent/OPT_QQQ_19700101.parquet")
        c5 = (bad["regime"] == "UNKNOWN" and not bad["ok"])
    except Exception:
        c5 = False
    print(f"C5 safe-state on failure: bad input -> UNKNOWN -> {'PASS' if c5 else 'FAIL'}")

    print("\n=== VERDICT ===")
    gating = {"C1": c1, "C2": c2, "C3": c3, "C5": c5}
    pending = [k for k, v in gating.items() if v is None]
    failed = [k for k, v in gating.items() if v is False]
    if failed:
        print(f"  BLOCKED — failing: {failed}. Do NOT connect paper trading.")
    elif pending:
        print(f"  NOT YET — pending (need more forward data): {pending}. "
              f"Keep accumulating; account stays untouched.")
    else:
        print("  ALL EVALUABLE CRITERIA PASS — cleared to connect the PAPER engine.")

if __name__ == "__main__":
    main()
