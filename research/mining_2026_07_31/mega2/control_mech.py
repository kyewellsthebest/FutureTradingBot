"""CONTROL: run this before believing anything the multi-mechanism hunter says.

The expensive lesson of this project is that a new engine gets tested on a new
hypothesis, so when the answer is "no edge" there is no way to tell an honest
null from a broken engine. Three sub-minute engines died that way.

So: two checks, both on the engine, neither on any hypothesis.

  1. REGRESSION. The impulse-pullback path must return byte-identical results
     after the refactor. Same parameters, same market, same numbers.
  2. LIVENESS. Every new mechanism must actually fire -- produce signals, reach
     a tradeable book, and produce both winners and losers. A mechanism that
     silently generates zero trades would report as "no edge" forever.

Usage: python control_mech.py [MARKET] [TF]
"""
import os, sys, types
os.environ["HUNT_COMMMULT"] = "0.0"
os.environ["HUNT_SLIP"] = "0.0"
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = "/tmp/claude-0/-home-user-FutureTradingBot/25529eed-cfb9-5eb3-98ab-625b175d900a/scratchpad"
MKT = sys.argv[1] if len(sys.argv) > 1 else "RTY"
TF = int(sys.argv[2]) if len(sys.argv) > 2 else 5


def load_defs(path):
    """Import a hunter module's definitions without running its search loop."""
    src = open(path).read()
    head = src.split("\nboard = json.load(")[0]      # everything above the main loop
    mod = types.ModuleType("h_" + os.path.basename(path).replace(".", "_"))
    mod.__dict__["__file__"] = path
    exec(compile(head, path, "exec"), mod.__dict__)
    return mod


new = load_defs(os.path.join(HERE, "hunter.py"))
refp = os.path.join(SCRATCH, "hunter_ref.py")
ref = load_defs(refp) if os.path.exists(refp) else None

M = new.load(MKT, TF)
Mr = ref.load(MKT, TF) if ref else None

# A deliberately wide spread of impulse-pullback vectors, including ones that
# should be rejected. Rejections have to match too -- a refactor that changes
# which candidates die is not a refactor.
CASES = [dict(mech="imp", lb=lb, k=k, pb=pb, ttl=6.0, sp=sp, rr=1.8,
              hold=24.0, sess=s, dirn=d, maxpos=2)
         for lb in (3.0, 12.0, 30.0) for k in (0.6, 1.5, 3.0)
         for pb in (0.15, 0.6) for sp in (1.0, 5.0)
         for s in (0, 1) for d in (1, -1)]

print(f"CONTROL on {MKT} tf{TF}: {len(CASES)} impulse-pullback vectors\n")

fail = 0
if ref is None:
    print("  [skip] no frozen reference at", refp)
else:
    # Run the comparison with costs off and the quality gates open. At real
    # costs every one of these arbitrary vectors loses money in training, both
    # engines bail at the same early return, and the diff compares None to
    # None 144 times. Opening the gates is what gives the check something to
    # actually disagree about.
    for mod, mm in ((new, M), (ref, Mr)):
        mod.MAXDD = 1e12; mod.MINGREEN = 0.0; mod.MAXRISK = 1e12
        mod.SLIP = 0.0
        mm["comm"] = 0.0
    if hasattr(new, "COMMX"): new.COMMX = 0.0
    # tpw and wkly are per-week, and the two versions count weeks differently
    # ON PURPOSE: the old one counted UTC calendar dates, which treats a Sunday
    # evening open as its own day and inflates the denominator. The new one
    # counts CME trading days -- 678 over this span, against a calendar
    # expectation of ~676. So those two fields must differ by exactly the ratio
    # of the week counts, and everything week-independent must be identical.
    WKR = Mr["wks"] / M["wks"]
    print(f"  weeks: new {M['wks']:.1f} (CME trading days) vs "
          f"ref {Mr['wks']:.1f} (UTC dates), ratio {WKR:.4f}")
    diffs = 0; compared = 0
    for c in CASES:
        for mod in (new, ref): mod.REJC.clear()
        a = new.evaluate(M, c)
        b = ref.evaluate(Mr, {k: v for k, v in c.items() if k != "mech"})
        if (a is None) != (b is None):
            diffs += 1; print("  MISMATCH none-ness:", c); continue
        if a is None:
            # Both bailed. Comparing *why* is a real check -- the two engines
            # must reject the same vector for the same reason -- and it is the
            # only check available for vectors that never reach a result.
            compared += 1
            if set(new.REJC) != set(ref.REJC):
                diffs += 1
                print(f"  MISMATCH reason: new={sorted(new.REJC)} "
                      f"ref={sorted(ref.REJC)}  {c}")
            continue
        compared += 1
        for k in ("wr", "maxdd", "risk", "n", "tr", "ho"):     # week-independent
            if a[k] != b[k]:
                diffs += 1
                print(f"  MISMATCH {k}: new={a[k]} ref={b[k]}  {c}")
                break
        else:
            for k in ("tpw", "wkly"):                          # must scale exactly
                if b[k] and abs(a[k] / b[k] - WKR) > 0.01:
                    diffs += 1
                    print(f"  MISMATCH {k} scaling: new={a[k]} ref={b[k]} "
                          f"ratio={a[k]/b[k]:.4f} expected {WKR:.4f}  {c}")
                    break
    # A regression check where every case was rejected in both versions has
    # zero mismatches and has tested nothing. That is how a bug that squeezed
    # the whole history into two days sailed through this check.
    MINCMP = len(CASES) // 4
    print(f"  1. regression: {len(CASES)} vectors, {compared} produced results, "
          f"{diffs} mismatches -> "
          + ("PASS" if diffs == 0 and compared >= MINCMP else "FAIL"))
    if compared < MINCMP:
        print(f"     ^^ VACUOUS: only {compared} of {len(CASES)} vectors returned "
              f"anything to compare (need {MINCMP}). Nothing was actually tested.")
        fail += 1
    fail += diffs

# Liveness. Sweep each mechanism over a coarse spread and report what it did.
# The point is not whether it made money -- it is whether it ran at all.
print("\n  2. liveness")
# Liveness asks whether the engine can carry a mechanism all the way to a P&L
# book -- not whether the book is any good. So the account's quality filters
# come off here; leaving them on made every mechanism look dead when what had
# actually happened is that arbitrary coarse parameters lose money, as they
# should. Rejection at 'signal' or 'fills' means the mechanism never traded;
# rejection at 'drawdown' or 'green' means it traded fine and was merely bad.
new.MAXDD = 1e12
new.MINGREEN = 0.0
print(f"     {'mech':5s} {'vectors':>7s} {'signals':>9s} {'books':>6s} {'trades':>7s} "
      f"{'best $/wk':>10s}  why the rest died")
for mech in new.MECHS:
    sig = tot = books = trades = 0
    bestwk = None; seen_tp = 0
    new.REJC.clear()
    # sp is swept too: a fixed stop multiple just picks one dollar risk, and on
    # most markets that one value fails the account's risk cap for every single
    # vector. The first version of this control "passed" while proving nothing.
    for lb in (2.0, 6.0, 16.0, 30.0):
        for k in (0.4, 1.0, 2.0, 3.5):
            for sp in (0.5, 1.5, 4.0):
                for d in (1, -1):
                    p = dict(mech=mech, lb=lb, k=k, pb=0.25, ttl=8.0, sp=sp, rr=1.8,
                             hold=30.0, sess=0, dirn=d, maxpos=3)
                    tot += 1
                    ix, sd, rf = new.signal(M, p)
                    sig = max(sig, len(ix))
                    r = new.evaluate(M, p)
                    # holdout_negative / train_negative still return None but
                    # only after a complete book was built, so they count as live
                    if r is not None or new.REJC.get("_train_positive", 0) > seen_tp:
                        books += 1
                    seen_tp = new.REJC.get("_train_positive", 0)
                    if r is not None:
                        trades = max(trades, r["n"])
                        if bestwk is None or r["wkly"] > bestwk: bestwk = r["wkly"]
    PNL = ("drawdown","green","train_negative","holdout_negative","too_few_in_split")
    books += sum(new.REJC.get(k, 0) for k in PNL)
    why = "  ".join(f"{k}={v}" for k, v in sorted(new.REJC.items(), key=lambda x: -x[1])
                    if not k.startswith("_"))
    # A mechanism that never produced a signal is broken, not flat. One that
    # produces signals but never a tradeable book is untested, not disproven.
    st = "BROKEN-no-signals" if sig == 0 else ("UNTESTED-no-books" if books == 0 else "ok")
    print(f"     {mech:5s} {tot:7d} {sig:9,} {books:6d} {trades:7,} "
          f"{('$%.0f' % bestwk) if bestwk is not None else '-':>10s}  {why}")
    if sig == 0 or books == 0:
        fail += 1; print(f"           ^^ {st}")

print("\nCONTROL " + ("PASSED" if fail == 0 else f"FAILED ({fail} problems)"))
sys.exit(1 if fail else 0)
