# Footprint scan -- searching structure, not price

Every search in this project so far looked for PRICE PATTERNS. That space is infinite, almost all noise, and its few real inhabitants are published and therefore decayed. Variations on a decayed edge are still decayed.

This searches for **footprints of forced flow** instead, and inverts the direction:

    old:  find a price pattern -> invent a story -> validate
    new:  find a FOOTPRINT -> identify the mandate -> derive the prediction -> validate

Someone obliged to move 5,000 lots at a fixed time leaves marks whether or not the price move is predictable: volume, spread, volatility, serial correlation. Those marks are **rare and each has a cause**. Price patterns are infinite and most have none.

**Returns are deliberately not scanned.** A return anomaly is a strategy hunting for a story. A VOLUME anomaly with no known cause is a footprint, and the story comes afterwards.

NQ, 4 quarters, 350,107 minute bars. A bucket is flagged at 3.0 robust sigmas (median absolute deviation) from the median of its own dimension.

## vol by minute of day (UTC)

| bucket | value | z | known cause? |
|---|---|---|---|
| 19:59 | 5,922.0 | +75.2 | **UNEXPLAINED** |
| 13:30 | 3,334.0 | +41.8 | US cash open |
| 21:00 | 3,251.0 | +40.7 | CME halt |
| 20:00 | 2,810.0 | +35.0 | US cash close |
| 13:31 | 2,475.5 | +30.7 | **UNEXPLAINED** |
| 13:32 | 2,351.5 | +29.1 | **UNEXPLAINED** |
| 14:30 | 2,261.0 | +28.0 | **UNEXPLAINED** |
| 13:35 | 2,079.5 | +25.6 | **UNEXPLAINED** |
| 13:33 | 2,013.5 | +24.8 | **UNEXPLAINED** |
| 14:31 | 1,935.5 | +23.8 | **UNEXPLAINED** |
| 19:55 | 1,870.0 | +22.9 | **UNEXPLAINED** |
| 19:54 | 1,821.0 | +22.3 | **UNEXPLAINED** |

## n by minute of day (UTC)

| bucket | value | z | known cause? |
|---|---|---|---|
| 19:59 | 3,412.0 | +60.9 | **UNEXPLAINED** |
| 13:30 | 2,508.5 | +44.4 | US cash open |
| 21:00 | 1,883.0 | +33.0 | CME halt |
| 13:31 | 1,858.5 | +32.6 | **UNEXPLAINED** |
| 13:32 | 1,683.0 | +29.4 | **UNEXPLAINED** |
| 20:00 | 1,622.0 | +28.3 | US cash close |
| 14:30 | 1,556.5 | +27.1 | **UNEXPLAINED** |
| 13:35 | 1,521.0 | +26.4 | **UNEXPLAINED** |
| 13:33 | 1,448.5 | +25.1 | **UNEXPLAINED** |
| 14:31 | 1,369.5 | +23.7 | **UNEXPLAINED** |
| 14:00 | 1,284.0 | +22.1 | 10:00 ET releases |
| 15:00 | 1,237.0 | +21.3 | 11:00 ET |

## absret by minute of day (UTC)

| bucket | value | z | known cause? |
|---|---|---|---|
| 22:00 | 12.0 | +8.8 | CME reopen |
| 13:30 | 11.0 | +7.9 | US cash open |
| 14:30 | 10.1 | +7.1 | **UNEXPLAINED** |
| 13:31 | 10.1 | +7.1 | **UNEXPLAINED** |
| 14:31 | 9.2 | +6.3 | **UNEXPLAINED** |
| 13:35 | 9.1 | +6.2 | **UNEXPLAINED** |
| 21:00 | 9.0 | +6.1 | CME halt |
| 14:00 | 9.0 | +6.1 | 10:00 ET releases |
| 13:32 | 8.8 | +5.8 | **UNEXPLAINED** |
| 19:54 | 8.5 | +5.6 | **UNEXPLAINED** |
| 15:00 | 8.5 | +5.6 | 11:00 ET |
| 19:50 | 8.2 | +5.4 | MOC imbalance published |

## vol by day of month

| bucket | value | z | known cause? |
|---|---|---|---|
| 18 | 65.0 | -4.1 | **UNEXPLAINED** |
| 19 | 66.0 | -4.0 | **UNEXPLAINED** |
| 17 | 77.0 | -3.3 | **UNEXPLAINED** |

## vol by day of week

| bucket | value | z | known cause? |
|---|---|---|---|
| 6 | 78.0 | -10.5 | **UNEXPLAINED** |
| 4 | 142.0 | +6.7 | **UNEXPLAINED** |

## How to use this

Ignore every row with a known cause. The open, the close, the 08:30 releases and the CME halt will dominate and they are the most crowded moments of the day -- there is no edge in being the ten-thousandth person to notice the open is busy.

**The rows marked UNEXPLAINED are the output.** Each one is a place where somebody is trading who did not have to choose to, and we do not yet know who. For each: identify the mandate, derive what it forces them to do, predict the price consequence -- and only then run it through the gauntlet.

A footprint with no mechanism is not a strategy. But unlike a price pattern, it is a question with an answer, and the answer is findable in exchange rules and fund mandates rather than in more data.

