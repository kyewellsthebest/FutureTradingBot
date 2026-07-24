# Middle-Dial Basket — deployment spec (v1, pre-build)

USER DECISION: deploy MIDDLE dial. Consistency over jackpots. Scale later by
size (1->2 micros), not by adding the heavy bond tail back.

## Sleeve source
research/multi_survivors.jsonl.gz — 8,459 gate-passing configs from the
cross-instrument mega-search (ES/RTY/YM/GC/CL/ZB 5-min, engine:
/tmp/claude-0/mega_multi.py archived in session logs; families
fade/momo/breakout/pullback/volspike; VIX/AAII/NAAIM prior-day gates).
Apply -$1.70/trade tick-honesty haircut to all bar results.

## Middle dial definition
- Base: LEAN selection (greedy max-$, pairwise corr<0.5, IS DD<=2000,
  worst-day>-1000, sleeves from MES/M2K/MYM/MGC micros only)
- Add back ZB/CL sleeves incrementally ONLY while combined worst-day
  (IS, haircut on) stays >= -$1,000. Stop there. That is "middle".
- Every sleeve trades 1 contract. All trades same-day only.

## Hard risk rails (non-negotiable in engine)
- Daily circuit-breaker: flatten ALL + halt for the day at -$1,000 realized+open
- Kill-switch: halt EVERYTHING at -$2,000 total drawdown; human restart only
- No overnight positions. No averaging down. Position cap per instrument: 1.

## Validation status
- Test 1 walk-forward: PASSED (edge survives unseen data; lean variant worst
  day -$826, ~$600-1000/wk median; middle variant to be re-measured exactly)
- Test 2 fresh-months blind: PENDING (24-product fetch, workflow run 30044256831)
- Test 3 tick replay of top sleeves: PENDING (fetch ticks via week-ticks workflow)
- DEPLOY ORDER: build engine -> Tests 2+3 -> PAPER until live matches research
  -> then account. Account untouched until then (user-authorized middle dial).
