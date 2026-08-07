# The signal is real, it is one seventh of the toll, and the contract was chosen for the wrong job

Three independent markets, one feature, one answer.

## Book imbalance predicts. Everywhere. By about a seventh of what crossing costs.

Resting size on the bid against resting size on the ask, measured identically
in each market: information coefficient against forward moves, a shuffled
control and a time-shifted control, train and holdout split by time, and a
decile table that assumes no linearity at all.

| market | ticks / snapshots | holdout IC | shuffled | shifted | signal | cost to cross | short by |
|---|---|---|---|---|---|---|---|
| NASDAQ equities (ITCH L3) | 79,816 snaps | **+0.1521** | -0.0060 | -0.0003 | 0.18 bps | 1.37 bps | 7.6x |
| EURUSD | 5,607,145 | **+0.1305** | +0.0014 | +0.0006 | 0.022 pips | 0.15 pips | 6.9x |
| GBPUSD | 8,734,162 | **+0.0918** | -0.0003 | -0.0006 | 0.010 pips | 0.35 pips | 34x |
| USDJPY | 10,129,402 | **+0.0641** | -0.0003 | -0.0002 | 0.001 pips | 0.20 pips | 180x |
| XAUUSD | 44,750,796 | **+0.0724** | -0.0002 | -0.0001 | 0.135 pips | 3.35 pips | 25x |

Signal is top decile minus bottom, halved, out of sample. Every control sits at
zero. Every sign holds. On NASDAQ the deciles run monotonically from -0.166 bps
to +0.249 bps at 9.2 sigma; on EURUSD from -0.024 pips to +0.019 at 89.8 sigma.

This is the first thing in this project that is not null, and it replicated
across an equity order book and four currency pairs.

It is also, in every single market, far too small to pay for crossing the
spread. That is not a disappointment; it is the most useful thing measured
here, because it says the problem was never finding a signal. **The problem is
that we kept trying to be the one who crosses.**

## The exit rule was not the missing piece either

Sixteen null families all varied the entry and left the exit fixed. Thirteen
exit rules, 58,437 trades each, every one run twice -- the same rule on the
strategy's entries and on random entries, because a trailing stop reshapes the
P&L distribution whether or not the entry knows anything.

| exit rule | win% | $/trade | strat - random |
|---|---|---|---|
| **fixed 6/12** | 33.5% | 0.0671 | **+0.2040** |
| trail 6 after 8 | 43.1% | 0.0389 | +0.1728 |
| trail 6 after 4 | 42.0% | 0.0880 | +0.1726 |
| trail 4 after 8 | 43.1% | 0.0513 | +0.1723 |
| trail 2 after 8 | 43.1% | 0.1033 | +0.1487 |
| trail 3 after 8 | 43.1% | 0.0709 | +0.1448 |
| trail 6 after 2 | 38.0% | 0.0733 | +0.1399 |
| trail 4 after 4 | 56.7% | 0.0505 | +0.1189 |
| trail 2 after 4 | 59.9% | 0.1101 | +0.1109 |
| trail 3 after 4 | 59.9% | 0.0903 | +0.1071 |
| trail 4 after 2 | 44.3% | 0.0745 | +0.0881 |
| trail 3 after 2 | 50.9% | 0.1062 | +0.0528 |
| trail 2 after 2 | **66.8%** | 0.1023 | +0.0484 |

Nothing beats the fixed rule. The ordering is monotone in how much the trail
resembles no trail at all -- the best trailing variants are the widest ones
with the latest triggers, which is to say the ones closest to a fixed stop with
the target removed.

Two things worth keeping:

- **`trail 2 after 2` doubles the win rate to 66.8% and is the second worst row
  in the table.** A tight trail turns losers into scratches and winners into
  scratches at the same rate. Anyone optimising win rate lands exactly here.
- Several of the highest differences have *negative* holdout: `trail 6 after 4`
  is second best at +0.173 and reads -0.047 out of sample. Selecting on the
  full-sample difference would have picked a rule that loses. That is the same
  anti-persistence measured everywhere else in this project.

## The contract was chosen for the wrong job

Everything here has been built on MNQ, chosen for the best volatility-to-cost
ratio *for someone who crosses the spread*. For someone who rests instead, the
ratio that decides everything is tick value against round-turn commission --
what you capture if filled on both sides, against what it costs to be there.

At the $1,499 lifetime tier ($0.09 a side broker, plus exchange and clearing):

| contract | one tick | round turn | headroom | ratio |
|---|---|---|---|---|
| ZB | $31.25 | $1.38 | **+$29.87** | 22.6x |
| ZN | $15.62 | $1.38 | **+$14.25** | 11.3x |
| MNG | $2.50 | $1.22 | +$1.28 | 2.0x |
| M6E | $1.25 | $0.70 | +$0.55 | 1.8x |
| **MES** | $1.25 | $0.72 | **+$0.53** | 1.7x |
| MHG | $1.25 | $0.92 | +$0.33 | 1.4x |
| M6A | $1.00 | $0.70 | +$0.30 | 1.4x |
| MGC | $1.00 | $0.72 | +$0.28 | 1.4x |
| **MNQ** | $0.50 | $0.72 | **-$0.22** | 0.7x |
| M2K / MYM / MCL | $0.50-1.00 | $0.72-1.22 | -$0.22 | 0.7-0.8x |
| MBT | $0.50 | $5.22 | -$4.72 | 0.1x |

**On MNQ one tick is $0.50 and a round turn costs $0.72.** Resting on both
sides and being filled perfectly, with no adverse selection and no queue,
loses twenty-two cents. Market making MNQ is not hard, it is arithmetically
impossible -- and MNQ is the contract every measurement in this project was
made on.

The same arithmetic explains the taker results without any reference to
signals. Cross a $0.50 spread and pay $0.72 and the friction is $1.22 a round
turn. The information in trade prints was measured at about $1.06. The signal
was always smaller than the toll, and the toll was set by the instrument.

## What this actually pays, honestly

Target: $1,000 a week on $4,100, which is 1,268% a year.

At 500 round turns a week that is **$2.00 net per round turn**.

- MES, one contract, capturing the full tick on both sides: $0.53 headroom.
  500 a week is $265, and that is the ceiling with perfect fills and zero
  adverse selection. Four contracts reaches $1,060 a week; margin is about $50
  intraday so the account carries it, but four lots into a moving market is
  where adverse selection stops being a footnote.
- MNQ, any size, any signal: negative before anything happens.
- Retail FX: no. A retail broker is not an exchange -- resting at the bid does
  not pay you the spread, and commission is charged anyway. The EURUSD
  imbalance edge is real and there is no venue in this account where it can be
  monetised as a maker.

So the honest position is: MES and MGC are the only affordable contracts where
resting has positive headroom at all, ZB and ZN have enormous headroom and
enormous per-tick risk, and the number that decides whether any of it works is
one this project has never measured -- **what the price does immediately after
a resting order gets filled**.

That is adverse selection, and it is the next thing to measure. The queue
simulation already written measures fill probability; it has never been asked
what happens to the fills it grants.
