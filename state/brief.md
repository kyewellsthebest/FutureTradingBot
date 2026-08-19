RESEARCH BRIEF  2026-08-19T17:28:57+00:00
627,224 trials charged, 0 survivor(s)

BINDING CONSTRAINT: EXPRESSIVENESS
  912,366 of 2,058,946 attempts (44%) could not be evaluated at all. Most of what the searcher draws, it cannot ask.
  -> fix the generator or the tape columns before reading anything else here -- these results are a sample selected by what the code can express

WHAT THE COVERAGE ACTUALLY BUYS
  468,660 cells measured
  239,185 could have seen an edge worth having
  36,761 could not -- their silence means nothing
  smallest edge ever visible anywhere: 0.013 RT/trade

NOT TESTED -- COULD NOT BE ASKED
  day_of_month/vol: 36,124/61,786 (58%) unevaluable
  day_of_month/n: 34,984/60,316 (58%) unevaluable
  day_of_month/absret: 20,732/37,625 (55%) unevaluable
  minute_of_day/absret: 222,968/409,412 (55%) unevaluable
  minute_of_day/vol: 299,120/566,691 (53%) unevaluable
  minute_of_day/n: 295,468/565,627 (52%) unevaluable

CANNOT BOTH BE TRUE
  map cell 4,2,0,1 (NQ@NQU4@15s): 4 cells -- worst: 15,245 trades but 508 independent (30x overlap)
      holds that span many bars make consecutive trades share most of their path; the raw count must never be read as evidence

GENUINELY RULED OUT
  shape/squeeze: 33,644 cells -- edges above 0.013 RT are excluded here
  shape/inside: 35,740 cells -- edges above 0.014 RT are excluded here
  shape/close_high: 40,585 cells -- edges above 0.016 RT are excluded here
  shape/expansion: 37,294 cells -- edges above 0.020 RT are excluded here
  feature/d30: 874 cells -- edges above 0.023 RT are excluded here
  feature/d8: 6,368 cells -- edges above 0.026 RT are excluded here
  feature/d7: 8,641 cells -- edges above 0.026 RT are excluded here
  feature/d10: 4,537 cells -- edges above 0.027 RT are excluded here

QUESTIONS ANSWERED WHILE YOU WERE AWAY
  cost_breakeven  (5 run(s))
      Q: How high can the all-in round turn go before the best thing the search has found stops paying?
      A: the best cell of 264,308 pays +47.490 round trips over 2,695 trades, which breaks even at an all-in round turn of $29.09 on MNQ (the search charged $0.60). after shrinking for the winner's curse it breaks even at $0.60. the 99th percentile of ALL 264,308 cells breaks even at $0.61 and the median at $-0.01, so the winner's headroom over the modelled cost is 3237.97x what the 99th percentile of the pile gets for free. at 258 trades a week it is worth the ladder in the report; the practical reading is that anything above $29.09 a round turn makes this a losing system no matter how it is executed
  session_split  (5 run(s))
      Q: Is the overnight session different enough from RTH that searching and pricing them together is wrong?
      A: overnight moves are 0.69x RTH in dispersion (a random split of the same sizes gives 1.02x, so the session effect is 16x what splitting nothing produces) overnight bars are 0.45x the RTH range, which says nothing about cost -- a quiet market can still be expensive to cross MEASURED on NQ top-of-book: spread is 3.0 ticks in RTH and 5.0 overnight (1.67x wider), against a cost model that charges 1 tick for both -- overnight results ARE optimistic, and 70% of the tier-1 tape is overnight

NEXT
  [1] make day_of_month/vol expressible, or drop it
      because 36,124 of 61,786 attempts could not be asked, so this family is counted as explored and has not been
  [1] make day_of_month/n expressible, or drop it
      because 34,984 of 60,316 attempts could not be asked, so this family is counted as explored and has not been
  [1] make day_of_month/absret expressible, or drop it
      because 20,732 of 37,625 attempts could not be asked, so this family is counted as explored and has not been
  [1] explain or fix: 4 cells -- worst: 15,245 trades but 508 independent (30x overlap) at map cell 4,2,0,1 (NQ@NQU4@15s)
      because holds that span many bars make consecutive trades share most of their path; the raw count must never be read as evidence
  [2] get finer data or more markets -- no hold on the current tapes can resolve a plausible edge
      because the best reachable size on this tape is 0.741 RT, against a plausible edge of 0.30 RT
  [4] stop re-testing shape/squeeze
      because 33,644 cells there already exclude edges above 0.013 RT