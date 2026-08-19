RESEARCH BRIEF  2026-08-19T11:58:49+00:00
565,985 trials charged, 0 survivor(s)

BINDING CONSTRAINT: CONTROLS
  390 cells cleared the bar and 22 were killed by a control. The search finds things; the checks reject them.
  -> read the kill reasons -- if one control dominates, that is the artifact the search keeps rediscovering

WHAT THE COVERAGE ACTUALLY BUYS
  417,841 cells measured
  195,524 could have seen an edge worth having
  29,603 could not -- their silence means nothing
  smallest edge ever visible anywhere: 0.013 RT/trade

NOT TESTED -- COULD NOT BE ASKED
  day_of_month/vol: 24,010/49,672 (48%) unevaluable
  day_of_month/n: 23,294/48,626 (48%) unevaluable
  day_of_month/absret: 13,750/30,643 (45%) unevaluable
  minute_of_day/absret: 146,144/332,588 (44%) unevaluable
  minute_of_day/vol: 196,772/464,343 (42%) unevaluable
  minute_of_day/n: 194,282/464,441 (42%) unevaluable

CANNOT BOTH BE TRUE
  map cell 4,2,0,1 (NQ@NQU4@15s): 4 cells -- worst: 15,245 trades but 508 independent (30x overlap)
      holds that span many bars make consecutive trades share most of their path; the raw count must never be read as evidence

GENUINELY RULED OUT
  shape/squeeze: 28,832 cells -- edges above 0.013 RT are excluded here
  shape/inside: 30,765 cells -- edges above 0.014 RT are excluded here
  shape/close_high: 34,406 cells -- edges above 0.016 RT are excluded here
  shape/expansion: 31,709 cells -- edges above 0.020 RT are excluded here
  feature/d30: 872 cells -- edges above 0.023 RT are excluded here
  feature/d8: 6,363 cells -- edges above 0.026 RT are excluded here
  feature/d7: 8,639 cells -- edges above 0.026 RT are excluded here
  feature/d10: 4,533 cells -- edges above 0.027 RT are excluded here

QUESTIONS ANSWERED WHILE YOU WERE AWAY
  cost_breakeven  (1 run(s))
      Q: How high can the all-in round turn go before the best thing the search has found stops paying?
      A: the best cell of 256,568 pays +47.490 round trips over 2,695 trades, which breaks even at an all-in round turn of $29.09 on MNQ (the search charged $0.60). after shrinking for the winner's curse it breaks even at $0.60. the 99th percentile of ALL 256,568 cells breaks even at $0.61 and the median at $-0.01, so the winner's headroom over the modelled cost is 2878.19x what the 99th percentile of the pile gets for free. at 258 trades a week it is worth the ladder in the report; the practical reading is that anything above $29.09 a round turn makes this a losing system no matter how it is executed
  session_split  (1 run(s))
      Q: Is the overnight session different enough from RTH that searching and pricing them together is wrong?
      A: overnight moves are 0.69x RTH in dispersion (a random split of the same sizes gives 1.00x, so the session effect is 31x what splitting nothing produces) overnight bars are 0.45x the RTH range, which says nothing about cost -- a quiet market can still be expensive to cross MEASURED on NQ top-of-book: spread is 3.0 ticks in RTH and 5.0 overnight (1.67x wider), against a cost model that charges 1 tick for both -- overnight results ARE optimistic, and 70% of the tier-1 tape is overnight

NEXT
  [1] make day_of_month/vol expressible, or drop it
      because 24,010 of 49,672 attempts could not be asked, so this family is counted as explored and has not been
  [1] make day_of_month/n expressible, or drop it
      because 23,294 of 48,626 attempts could not be asked, so this family is counted as explored and has not been
  [1] make day_of_month/absret expressible, or drop it
      because 13,750 of 30,643 attempts could not be asked, so this family is counted as explored and has not been
  [1] explain or fix: 4 cells -- worst: 15,245 trades but 508 independent (30x overlap) at map cell 4,2,0,1 (NQ@NQU4@15s)
      because holds that span many bars make consecutive trades share most of their path; the raw count must never be read as evidence
  [2] get finer data or more markets -- no hold on the current tapes can resolve a plausible edge
      because the best reachable size on this tape is 0.739 RT, against a plausible edge of 0.30 RT
  [4] stop re-testing shape/squeeze
      because 28,832 cells there already exclude edges above 0.013 RT