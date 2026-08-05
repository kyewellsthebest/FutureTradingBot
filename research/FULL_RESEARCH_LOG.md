# Complete research log — everything tried, tested, and found

Session 2026-08-04/05. Every path, every number, every retraction.

---

## 1. THE HEADLINE

**No strategy found that survives testing.** 16 hypothesis families, 7 markets,
5 timeframes, ~240 million trades, 4 train/holdout split points. Nothing beats
a random-entry control out of sample.

**The single number that explains it all:** the information available in trade
prints is worth about **$1.06 per trade**. Trading costs **$1.32–$2.30** per
round turn. The signal is roughly **half** the toll.

---

## 2. THE TARGET, PRICED

Goal: $1,000/week, ~500 trades/week, ≤$30 risk/trade, ≥40% win rate.

Measured on RTY 5-minute bars. Best config selected on **training only**, then
its **holdout** result read off:

| trades/week | honest edge/trade | net at today's cost | $/week |
|---|---|---|---|
| 0–5 | +$2.74 | +$0.44 | +1 |
| 5–10 | +$1.37 | −$0.93 | −7 |
| 10–20 | −$0.12 | −$2.42 | −35 |
| 20–40 | +$0.45 | −$1.85 | −50 |
| 40–80 | −$0.89 | −$3.19 | −162 |
| 80–150 | −$1.02 | −$3.32 | −351 |
| 150–300 | −$0.91 | −$3.21 | −647 |
| 300–600 | −$0.78 | −$3.08 | −1,178 |

**Edge goes NEGATIVE at 10–20 trades/week.** Above that speed there is nothing
to pay costs with. 500 trades/week is not a search problem — it is absent.

---

## 3. EVERY MECHANISM TESTED

Holdout $/trade vs a random-entry control. Cells show sign-test wins/cells.

| mechanism | 5m | 15m | 60m | tick_500 | vol_5000 | range_15 | verdict |
|---|---|---|---|---|---|---|---|
| impulse-pullback | −2.21 | 35/60 | 13/32 | 13/32 | 13/32 | 15/32 | dead |
| mean reversion | −1.18 | 29/60 | 29/52 | 15/32 | 15/32 | 15/32 | dead |
| VWAP reversion | −0.81 | 30/60 | 24/52 | 14/32 | 7/32 | 17/32 | dead |
| range compression | −3.82 | null | null | 11/32 | 12/32 | 13/32 | dead |
| opening range | −4.15 | null | null | 4/9 | dead | 8/14 | dead |
| overnight gap | −3.08 | null | null | 0/4 | 0/4 | 50% | dead |
| volume spike | −0.14 | null | null | 7/31 | — | 18/32 | dead |
| calendar (hour) | 0% sign | — | −10.86 | — | 50% | — | dead |
| weekday | t=1.04 | — | — | — | — | — | dead |
| weekday × hour | 51% | — | — | — | — | — | dead |
| cross-market lead-lag | — | — | −4.7 | — | — | — | dead |
| order-flow imbalance | — | — | — | 13/32 | — | — | dead |
| continuous position | — | — | — | 1.06σ | — | — | dead |
| **random control** | — | — | **+1.46** | +2.83 | −3.67 | −0.72 | *the bar* |

**The control beats or matches every mechanism.**

Timeframes tested: 5m, 15m, 60m, 240m, plus event bars (500 trades, 5,000
contracts, 15 points of range — no clock at all).

Markets: NQ, ES, RTY, YM, CL, GC, HG (all on their own raw tick tape),
plus NG, 6E, 6B, 6A, MBT, ETH, ZF, ZT, ZC, ZW on 5-minute bars.

---

## 4. INFORMATION CONTENT — measured directly, not searched

Spearman IC vs forward returns. 8 NQ contracts, ~200M trades, split by contract.

| feature | holdout IC | consistent across contracts | worth/trade |
|---|---|---|---|
| trade intensity | +0.0151 | 100% | $1.06 |
| bar range | +0.0142 | 88% | $0.99 |
| bar return (reversal) | −0.0117 | 100% | $0.82 |
| signed volume (delta) | +0.0098 | 100% | $0.68 |
| delta / volume | +0.0055 | 75% | $0.39 |
| cumulative delta | +0.0051 | 38% | $0.36 |
| big-trade share | +0.0025 | 62% | $0.18 |
| **sweep** (50ms burst) | −0.0048 | noise | — |
| **absorption** | −0.0055 | noise | — |
| run length | +0.0011 | noise | — |
| block size | +0.0000 | noise | — |
| size skew at extremes | +0.0006 | 12% | — |
| **shuffled control** | **−0.0036** | — | — |
| **COST TO TRADE** | — | — | **$1.32–$2.30** |

**Sweeps and absorption — the two things order-flow traders swear by — carry
no information.** Both sit inside the shuffled control's noise band across
920,063 windows and 8 contracts.

---

## 5. YOUR OWN STRATEGY — tested exactly as described

Impulse on Nasdaq → ~20% retrace → enter → 12pt target, 6pt stop, ~200/day.

### Bar-based, 45 configurations, 8 NQ contracts

Best configs, all at 6.0/12.0 points (your original reading):

| impulse | lookback | retrace | trades/day | win% | need | gross $/trade | ± |
|---|---|---|---|---|---|---|---|
| 20pt | 10 | 0.50 | 69 | 34.9% | 33.3% | +0.566 | 0.077 |
| 12pt | 10 | 0.50 | 132 | 34.9% | 33.3% | +0.553 | 0.055 |
| 12pt | 3 | 0.20 | 157 | 34.8% | 33.3% | +0.541 | 0.051 |
| 8pt | 3 | 0.20 | 257 | 34.8% | 33.3% | +0.512 | 0.040 |
| 12pt | 5 | 0.20 | 204 | 34.8% | 33.3% | +0.515 | 0.044 |

### The four cost scenarios

| scenario | gross | train | **holdout** |
|---|---|---|---|
| touch fills, no slippage | +0.512 | +0.636 | **+0.159** |
| trade-through fills | +0.141 | +0.250 | **−0.194** |
| touch fills, 1 tick slip | +0.186 | +0.312 | **−0.172** |
| **realistic (both)** | **−0.190** | −0.080 | **−0.529** |

**Trade-through fills remove 72% of the edge.** Best-case holdout (+$0.159)
is still below the $0.42 cost floor.

### Tick-native re-test — no bars anywhere

| lookback | trades | gross $/trade | sigma | train | **holdout** |
|---|---|---|---|---|---|
| 400 prints (~2 min) | 145,533 | +0.031 | 0.7 | +0.043 | −0.009 |
| 600 prints (~3 min) | 21,180 | −0.110 | 0.9 | — | +0.014 |
| 1200 prints (~6 min) | 17,232 | +0.257 | 2.0 | +0.331 | **−0.006** |
| 2400 prints | 2,234 | +0.167 | 0.5 | +0.545 | −1.164 |
| 4800 prints | **124** | +4.258 | 2.6 | +5.778 | +1.395 |

The 4800-print row is 124 trades — meaningless. **Best real result: +$0.257
in-sample, ZERO out-of-sample.**

### Cross-validation

At a 1200-print lookback the tick-native simulator gives **+$0.495/trade at
34.7% wins**; the bar engine gives **+$0.512 at 34.8%**. Two independently
written engines agreeing within 3% — neither is broken.

---

## 6. THE QUEUE PENALTY — the one solid structural finding

Simulated by resting an order and draining the queue against real prints.

| queue position | trades | no-fill | win% | gross $/trade | sigma |
|---|---|---|---|---|---|
| 0 (touch — the fantasy) | 145,533 | 8.7% | 33.4% | +0.031 | 0.7 |
| 1 contract ahead | 145,533 | 8.7% | 33.4% | +0.031 | 0.7 |
| 2 ahead | 145,013 | 9.0% | 32.9% | −0.141 | 3.2 |
| 3 ahead | 144,660 | 9.2% | 32.6% | −0.250 | 5.6 |
| 5 ahead | 144,253 | 9.5% | 32.3% | −0.368 | 8.3 |
| 10 ahead | 143,959 | 9.7% | 32.1% | −0.441 | 9.9 |
| 25 ahead | 143,893 | 9.7% | 32.1% | −0.454 | 10.2 |

**Every contract you sit behind costs ~$0.04–0.05 per trade, at 10 sigma.**
Measured off the tape, not assumed. This is why limit entries at obvious
levels bleed, and it is the first structural fact here derived without bars.

---

## 7. COMMISSION — corrected from your screenshot

My original figures were **35–70% too high**. Rebuilt from components:
Tradovate broker per side + exchange + clearing + NFA.

| plan | broker/side | NQ ES RTY YM GC | HG | CL |
|---|---|---|---|---|---|
| free | $0.39 | $1.32 | $1.52 | $1.82 |
| $99/month | $0.29 | $1.12 | $1.32 | $1.62 |
| **$1,499 lifetime** | **$0.09** | **$0.72** | **$0.92** | **$1.22** |

**Verdict on the $1,499 plan: don't buy it for this.** At $0.72 the one
genuinely predictive signal *still* loses to random entry. Commission was
never the binding constraint.

Theoretical floor with every lever pulled — lifetime plan + CME seat lease
(~$500–1,000/mo, cuts exchange fees) + passive entry + stop-limit exits —
is about **$0.42/round turn**. Nothing measured clears even that.

---

## 8. FINDINGS RETRACTED AFTER VERIFICATION

Eight results looked real and died. This section is the most useful one.

| claim | peak value | how it died |
|---|---|---|
| holdout persistence | 85% | contaminated sweep — live edits gave one arm mechanisms the others never saw. Real: 19–29% vs 50% chance |
| opening range | +$14.21/trade | day split at midnight UTC = 7pm New York, so "opening range" measured the middle of the overnight |
| "fees eat a real edge" | — | same contaminated sweep; no edge underneath to eat |
| 60m VWAP reversion | +$22.04/trade | regime luck. 24/52 cells (p=0.76). On RTY itself averages −$16.6 across split points |
| Monday effect | t=10.18 | overlapping observations + cross-market correlation. Real t=1.04, corrected p=0.39 |
| tick_500 opening range | +$22.71/trade | 4/9 cells (p=0.75), only produced trades in 3 of 8 contracts |
| continuous position sizing | +$29/wk | shuffled control earned +$47/wk gross; error bar ±$56 exceeded the effect (1.06σ) |
| your strategy inverted | +$6.203/trade | my own look-ahead filter — screened entries using the fill bar's full range |

---

## 9. BUGS IN MY OWN CODE — nine, all caught by controls

| bug | effect |
|---|---|
| µs vs ns timestamps (pandas 3) | 2.5 years compressed into **2 days** |
| day boundary moved to 22:00 UTC | gap mechanism silently masked out entirely |
| regression test | could pass by testing nothing (all cases rejected in both versions) |
| live edits mid-sweep | contaminated a 4-condition experiment |
| `d.size` | returned element count, not the column |
| pandas `spearman` | routes through scipy, not installed |
| asymmetric same-bar rule | allowed same-bar stops, blocked same-bar targets — penalised every trade, flipped your strategy's sign |
| fill direction = trade direction | filled every inverted order instantly at a stale level: 0% win rate, exactly −stop, zero variance |
| look-ahead entry filter | used the fill bar's full range to decide entry — cut 563 trades/day to 3 and manufactured 50.6% wins |

**Seven of nine pushed toward false negatives. One produced a false positive
(+$6.203) — and I interrogated it far less than the results I disliked.**

---

## 10. METHODS THAT PRODUCED THE NEGATIVES

Any future candidate must clear all of these.

1. **Random-entry control.** Identical holds, stops, targets, costs, filters —
   entries at random times. Its holdout return is the bar to beat, *not zero*.
   In a holdout where RTY rose 116 ATRs, zero is not the null.
2. **Drift adjustment.** Each trade charged the market's average per-bar move
   over its own split, times duration and side. A chronological holdout is one
   directional regime, so "worked out of sample" otherwise means "was long in
   a rally."
3. **Many cells + sign test.** 15 markets or 8 contracts × 4 split points. A
   real edge wins most cells; regime luck wins the cell it was found in.
4. **Select on train, report holdout.** The upper envelope of thousands of
   random configs is a noise ceiling.
5. **Test the engine before the hypothesis.** `control_mech.py` proves the
   impulse-pullback path is unchanged and every mechanism reaches a P&L book,
   and refuses to pass vacuously.
6. **Gross before net.** If a signal only wins by trading less, its gross is
   flat and the whole gap is the control's commission bill.
7. **Error bars.** A signal must clear its own standard error before it can
   clear the control.

---

## 11. DATA HELD

| source | coverage | status |
|---|---|---|
| NQ tick (Polygon) | 8 contracts, ~200M trades, 728 days | tested exhaustively |
| ES/RTY/YM/CL/GC/HG tick | 39 contracts, 1.5 GB | tested |
| 5-minute OHLCV | 25 markets, Dec 2023 – Jul 2026 | tested |
| CBOE put/call archives | 2003–2019 | **no overlap with price data** |
| CBOE SKEW | to 2026, 64 rows | too few |
| QQQ daily (Polygon) | 2024–2026 only (plan caps stocks at 2 years) | insufficient |
| VIX daily | present | untested |
| CFTC / AAII / NAAIM / macro | present | untested |

---

## 12. WHAT IS STILL OPEN

1. **Daily-horizon positioning** — the one structural escape from the cost
   problem. A $242 median daily move against $0.42 of cost is 575:1, versus
   ~1:1 intraday. Blocked on data: CBOE archives end 2019, Polygon caps stocks
   at 2 years, and this container's proxy blocks cboe.com/stooq/Yahoo.
   A workflow now fetches it from an Actions runner (open internet).
2. **Depth of book (Databento MBO, $1.80/GB)** — genuinely different
   information: resting orders and cancellations, not trade prints. Written up
   in `DATABENTO_PLAN.md`. **I do not recommend buying it** — queue imbalance
   decays in seconds and belongs to co-located firms.
3. **Untested data already on disk** — CFTC positioning, AAII/NAAIM sentiment,
   macro features, VIX. All daily, all free, all unexamined.

---

## 13. LIVE BOT WARNING

`bot/pullback_strategy.py` — the deployed strategy — **is impulse-pullback**,
the family measured at −$2.21/trade out of sample and losing to random entry
on every timeframe and all seven markets.

`INVERSE MODE` is not an escape: direction was a free parameter (`dirn = ±1`)
in every search, so fading the impulse was tested alongside following it.

**Do not take it live at any commission tier. A good week on demo is not
evidence — it is the same noise that produced the eight retractions above.**

---

## 14. THE ONE-LINE VERSION

The data contains roughly half the edge needed to pay its own transaction
costs, and the search methods that appear to find more are measurably
selecting noise.
