# The LEVELRIDE simulator is biased. Its numbers are retracted.

Calibrating against a **driftless random walk** — where a 260/80 bracket
must return exactly zero gross, by the optional stopping theorem —
exposed two defects and left a third unresolved.

## What a known answer revealed

| stage | $/trade on a driftless walk | should be |
|---|---|---|
| as first written | −$42.62 | ≈ −$2.50 (costs only) |
| after the end-of-day fix | −$22.05 ± 3.59 | ≈ −$2.50 |
| pure barrier, no ladder machinery | −4.03 ± 2.38 **points** | 0 points |

## Defect 1 — the breakeven exit filled at a price that was not there

The rule sets the stop to the entry price after N minutes. If the trade
was already 50 points under water at that moment, the code booked the
exit **at the entry price** — a −$2 loss instead of −$100. You cannot
sell at your entry when the market is 50 points below it; that stop is
on the wrong side of the book.

This made the rule print **+$43/day on a driftless random walk**, which
is impossible with commission charged, and produced the apparent
"$32/day → $129/day" improvement. Exits are now gap-aware:
`min(price, stop)` for a long, `max` for a short.

## Defect 2 — the end-of-day flatten never fired, so winners were dropped

`FLAT_H = 20.9167`, but the synthetic sessions ran to exactly 20.90. The
flatten branch never executed and every position still open at the close
was **silently discarded rather than recorded**. The discarded ones are
the survivors, which average **+$170**. Throwing away the winners for
more than half the session was worth **$20.57/trade**.

The real-data run reaches ~21:00 so its flatten does fire — but the
calibration that was supposed to check the simulator could not see this,
because it never got there.

## Defect 3 — unlocated

−$22.05 against an expected −$2.50 leaves **−$19.55/trade of pessimism
at 5.4σ**. The pure barrier test returns zero, so the theorem holds and
the fault is in the ladder layer: entry priced at the level rather than
the crossing print, the re-arming logic, or the concurrency cap. Not yet
found.

## What this does and does not overturn

**Unaffected — the fade results.** Those ran on `causal_engine`, which
is validated independently: 29/29 against the live bot, recovers a
planted synthetic edge, and predicted the live account to within
$0.83/trade.

**Still valid — the breakeven comparison.** `OFF` and `BE` share the
same bias, so the difference between them holds even though the levels
do not. The rule is consistently *worse* than no rule.

**Retracted — LEVELRIDE at −$43/week.** It came from the biased
simulator. Treat it as unmeasured, not as a negative result.

## The method point

Calibrating against a case with a **known answer** is what caught this.
Nothing else would have. The RANDOM control and the real-data run both
inherit the same bias, so they agree with each other perfectly while
being wrong together — which is exactly what they did.
