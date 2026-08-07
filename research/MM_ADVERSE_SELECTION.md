# What happens after a resting order fills

Source: `01302019.NASDAQ_ITCH50.gz` (4.76 GB), first 200,000,000 messages, regular hours only.

Parsed 200,000,000 messages. Placed **46,398 passive orders** at the touch across 11 symbols.

**Fill rate 50.8%** (23,581 of 46,398). Median half-spread captured on a fill: **1.07 bps**.

## Where the mid went after we were filled

| horizon | adverse move | +/- | half-spread | NET | n |
|---|---|---|---|---|---|
| 100 msgs | -1.990 bps | 0.023 | 1.27 bps | **-0.719 bps** | 5,035 |
| 1000 msgs | -1.904 bps | 0.047 | 1.07 bps | **-0.829 bps** | 1,792 |
| 10000 msgs | -1.905 bps | 0.069 | 1.20 bps | **-0.706 bps** | 1,512 |

The adverse column is signed so that NEGATIVE means the market moved against the fill. NET is the half-spread you captured plus that move: positive means resting made money, negative means you were run over.

## Does book imbalance let a maker decline the bad fills? (h=1000)

| imbalance quintile at placement | n | adverse move | NET |
|---|---|---|---|
| 0 | 359 | -1.858 bps | -0.211 bps |
| 1 | 358 | -1.905 bps | -0.832 bps |
| 2 | 358 | -2.043 bps | -0.968 bps |
| 3 | 358 | -1.758 bps | -0.692 bps |
| 4 | 359 | -1.955 bps | -0.711 bps |

A maker does not need a signal that predicts the move. It needs one that says which fills to refuse. If the net is positive in some quintiles and negative in others, that is a business; if it is negative everywhere, no amount of CME order book data changes the answer.
