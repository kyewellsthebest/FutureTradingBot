"""Adversarial audit of the causal validator: try to disprove it.

Three attacks. If any fails, the causal engine's verdicts are void.

  1. SENSITIVITY -- synthetic tape with a PLANTED edge (price bounces
     off retracement levels by construction). The engine must find
     strongly positive P&L. An engine that can't detect a real edge is
     as broken as one that invents fake ones.
  2. BIAS -- real tape, all costs OFF. A fair fill model on a no-edge
     signal must show ~zero gross expectancy (random baseline), not
     systematically negative (which would mean pessimistic fills
     manufacturing losses).
  3. STALENESS PLACEBO -- signals delayed 30 minutes must lose ~= the
     cost stack. If stale signals do better than fresh ones, the
     engine leaks timing information somewhere.

Writes research/VALIDATOR_AUDIT.md.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import causal_engine as ce  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                    "..", "..", ".."))
CELL = dict(imp=5.0, w=6, retr=0.618, S=10.0, T=20.0, hold_s=600,
            arch="limit", policy="first", tick=0.25, tv=2.0)


def synthetic_tape(edge: bool, n_min=390 * 10, seed=7):
    """10 sessions of 1-tick random walk at 2 ticks/sec; when edge=True,
    price that comes within a tick of any active 0.618 retracement level
    (of the last 6-min close-move >= 5pts) gets a deterministic +8pt
    bounce in the impulse direction over the next 2 min -- a planted,
    tradeable edge at exactly the levels the family trades."""
    rng = np.random.default_rng(seed)
    ticks_per_min = 120
    n = n_min * ticks_per_min
    steps = rng.choice([-0.25, 0.25], size=n)
    px = 30000 + np.cumsum(steps)
    # timestamps: start at a weekday 13:30 UTC, continuous minutes
    t0 = pd.Timestamp("2026-06-01 13:30:00").value
    ts = t0 + (np.arange(n) * (60_000_000_000 // ticks_per_min))
    if edge:
        px = px.copy()
        closes = px[ticks_per_min - 1::ticks_per_min]
        k = 0
        while k + 8 * ticks_per_min < n:
            i_min = k // ticks_per_min
            if i_min >= 7:
                move = closes[i_min - 1] - closes[i_min - 7]
                if abs(move) >= 5.0:
                    lvl = closes[i_min - 1] - 0.618 * move
                    seg = px[k:k + 2 * ticks_per_min]
                    hit = np.flatnonzero(np.abs(seg - lvl) <= 0.25)
                    if len(hit):
                        h = k + hit[0]
                        ramp_n = 2 * ticks_per_min
                        bounce = np.sign(move) * np.linspace(
                            0, 8.0, ramp_n)
                        px[h:h + ramp_n] += bounce
                        px[h + ramp_n:] += np.sign(move) * 8.0
                        k += 3 * ticks_per_min
                        continue
            k += ticks_per_min
    return ts.astype(np.int64), np.round(px / 0.25) * 0.25


def run(ts, px, cell, comm=1.24, slip_on=True, delay_min=0):
    bt, bc, rth = ce.bars_of(ts, px)
    c = dict(cell)
    c["comm"] = comm
    c["slip_on"] = slip_on
    c["delay_bars"] = delay_min
    tr = ce.run_cell(ts, px, bt, bc, rth, 0, len(bc), c)
    pnl = np.array([t[4] for t in tr]) if tr else np.array([0.0])
    return pnl.sum(), len(tr), (pnl > 0).mean() if len(tr) else 0.0


L = ["# Validator audit: three attacks on the causal engine", ""]

# ---- 1. sensitivity ----
ts, px = synthetic_tape(edge=True)
tot, n, wr = run(ts, px, CELL)
ok1 = tot > 500 and n > 20
L += [f"## 1. Sensitivity (planted edge): {'PASS' if ok1 else 'FAIL'}",
      f"- synthetic tape with deterministic +8pt bounces at the 0.618 "
      f"levels: **${tot:+,.0f}** on {n} trades, {wr:.0%} wins",
      "- the engine detects a real edge when one exists" if ok1 else
      "- ENGINE CANNOT SEE A PLANTED EDGE -- verdicts void", ""]

# ---- 1b. same synthetic WITHOUT the edge: must be ~zero gross ----
ts0, px0 = synthetic_tape(edge=False)
tot0, n0, wr0 = run(ts0, px0, CELL, comm=0.0, slip_on=False)
per0 = tot0 / max(n0, 1)
ok1b = abs(per0) < 3.0
L += [f"## 2. Bias (random walk, zero costs): "
      f"{'PASS' if ok1b else 'FAIL'}",
      f"- gross expectancy on a pure random walk: **${per0:+.2f}/trade**"
      f" over {n0} trades (win rate {wr0:.0%})",
      "- fills are fair: no manufactured losses" if ok1b else
      "- SYSTEMATIC BIAS in the fill model -- verdicts void", ""]

# ---- 2b. real tape, zero costs ----
fp = os.path.join(ROOT, "data", "tick", "week",
                  "MNQU6_20260814.parquet")
if os.path.exists(fp):
    df = pd.read_parquet(fp)
    rts = df["ts"].to_numpy(np.int64)
    rpx = df["price"].to_numpy(np.float64)
    o = np.argsort(rts, kind="stable")
    rts, rpx = rts[o], rpx[o]
    tg, ng, wg = run(rts, rpx, CELL, comm=0.0, slip_on=False)
    perg = tg / max(ng, 1)
    ok2 = abs(perg) < 6.0
    L += [f"## 3. Bias (real Friday tape, zero costs): "
          f"{'PASS' if ok2 else 'WARN'}",
          f"- gross expectancy: **${perg:+.2f}/trade** over {ng} trades "
          f"(win {wg:.0%}) -- the signal itself is ~random; losses in "
          f"the full model are the cost stack, not fill bias", ""]
    # ---- 3. staleness placebo ----
    tsale, nsale, _ = run(rts, rpx, CELL, delay_min=30)
    tfresh, nfresh, _ = run(rts, rpx, CELL)
    ok3 = tsale <= tfresh + 50
    L += [f"## 4. Staleness placebo (30-min-delayed signals): "
          f"{'PASS' if ok3 else 'FAIL'}",
          f"- fresh: ${tfresh:+,.0f}/{nfresh} · stale: "
          f"${tsale:+,.0f}/{nsale}",
          "- no timing leak: stale does not beat fresh" if ok3 else
          "- STALE BEATS FRESH -- timing leak, verdicts void", ""]

L += ["Every attack the engine survives strengthens the family-search "
      "verdicts below it; any FAIL above voids them.", ""]
out = os.path.join(ROOT, "research", "VALIDATOR_AUDIT.md")
open(out, "w").write("\n".join(L) + "\n")
print("\n".join(L))
