"""Join each NQ trade to the quote that was live at that instant.

Called by .github/workflows/nq-data.yml, which does the heavy filtering in a
shell pipe (`aws s3 cp | zcat | grep`) so this only ever sees one contract's
rows. Reading a 4.9 GB quote file into pandas would need more memory than a
GitHub runner has; grepping it at C speed first costs seconds.

WHAT THIS PRODUCES is the dataset I was about to pay Databento for: every
trade, carrying the bid and ask that were resting when it printed. Two things
come out of it that the repo has been assuming rather than measuring:

  THE REAL SPREAD. Every cost figure in this project charges 2.5 ticks of
  slippage per round turn. That number came from an estimate, not from fills --
  the account has only ever traded on the simulator, which fills at the
  requested price with no slippage at all. The spread measured here is what
  crossing actually costs, and several "this loses fifteen cents a trade"
  conclusions flip if it turns out to be one tick rather than 2.5.

  THE TICK RULE'S REAL ERROR RATE. Every order flow feature in the repo infers
  who the aggressor was from the direction of the last price change. That is
  the Lee-Ready test and it is supposed to be right about 85% of the time.
  Here the true answer is known -- a trade at or above the ask was a buy, at or
  below the bid was a sell -- so the guess can be scored instead of trusted.
  f_ofi, the one feature family that kept surfacing in the search, is built
  entirely on that guess.
"""
import os
import sys

import numpy as np
import pandas as pd

TR_COLS = ["ticker", "timestamp", "sequence_number", "report_sequence",
           "price", "size", "correction", "exchange", "session_end_date"]
QT_COLS = ["ticker", "timestamp", "sequence_number", "report_sequence",
           "ask_timestamp", "ask_price", "ask_size",
           "bid_timestamp", "bid_price", "bid_size",
           "exchange", "session_end_date"]
TICK = 0.25
USD_TICK = 0.50            # MNQ


def main(day, front, trpath, qtpath, outdir):
    os.makedirs(outdir, exist_ok=True)
    tr = pd.read_csv(trpath, names=TR_COLS,
                     usecols=["ticker", "timestamp", "price", "size"])
    tr = tr[tr.ticker == front].sort_values("timestamp")
    L = [f"## {day} — `{front}`", "",
         f"{len(tr):,} trades."]
    print(f"{len(tr):,} trades on {front}")

    if os.path.getsize(qtpath) == 0:
        tr.to_parquet(f"{outdir}/{front}_{day}_trades.parquet",
                      compression="zstd")
        print("no quotes requested; wrote trades only")
        return

    qt = pd.read_csv(qtpath, names=QT_COLS,
                     usecols=["ticker", "timestamp", "ask_price", "ask_size",
                              "bid_price", "bid_size"])
    qt = qt.sort_values("timestamp")
    # a quote row can carry only one side; carry the other forward so every
    # row is a complete book rather than a one-sided update
    qt[["bid_price", "ask_price", "bid_size", "ask_size"]] = \
        qt[["bid_price", "ask_price", "bid_size", "ask_size"]].ffill()
    qt = qt.dropna(subset=["bid_price", "ask_price"])
    print(f"{len(qt):,} quote updates")

    m = pd.merge_asof(tr, qt.drop(columns=["ticker"]),
                      on="timestamp", direction="backward")
    m = m.dropna(subset=["bid_price", "ask_price"])
    # a crossed or locked book is a stale join, not a market state
    m = m[m.ask_price >= m.bid_price]

    m["spread"] = m.ask_price - m.bid_price
    # TRUE aggressor: at or above the ask, a buyer crossed. At or below the
    # bid, a seller did. Between the two it was a midpoint or hidden fill.
    m["aggressor"] = np.where(m.price >= m.ask_price, 1,
                              np.where(m.price <= m.bid_price, -1, 0))

    known = m.aggressor != 0
    guess = np.sign(m.price.diff()).replace(0, np.nan).ffill()
    acc = float((guess[known] == m.aggressor[known]).mean()) if known.any() else float("nan")

    sp = float(m.spread.median())
    L += ["",
          f"| | measured | what the repo assumed |",
          f"|---|---|---|",
          f"| median spread | **{sp/TICK:.2f} ticks** "
          f"(${sp/TICK*USD_TICK:.2f} to cross one way) | 2.5 ticks, "
          f"${2.5*USD_TICK:.2f} per round turn |",
          f"| tick-rule accuracy | **{acc*100:.1f}%** | ~85% |",
          f"| spread = 1 tick | {float((m.spread <= TICK*1.01).mean())*100:.1f}% "
          f"of trades | — |",
          f"| median top-of-book | {m.bid_size.median():.0f} bid / "
          f"{m.ask_size.median():.0f} ask | — |",
          f"| aggressive buys | {float((m.aggressor == 1).mean())*100:.1f}% | — |",
          f"| between the quotes | {float((m.aggressor == 0).mean())*100:.1f}% | — |",
          ""]
    print("\n".join(L[3:]))

    out = f"{outdir}/{front}_{day}_tbbo.parquet"
    m.to_parquet(out, compression="zstd")
    print(f"wrote {out} ({os.path.getsize(out)/1e6:.1f} MB)")

    rp = os.path.join("research", "POLY_TBBO.md")
    head = ("# Trades joined to the live quote\n\n"
            "Two numbers this repo has been asserting rather than measuring: "
            "what the spread actually costs, and how often the tick rule "
            "guesses the aggressor correctly. Every cost figure charges 2.5 "
            "ticks of slippage, but that came from an estimate — the account "
            "has only traded on the simulator, which fills at the requested "
            "price. And every order-flow feature, `f_ofi` included, infers the "
            "aggressor from the last price change instead of knowing it.\n")
    prev = open(rp).read() if os.path.exists(rp) else head
    if not prev.startswith("# Trades joined"):
        prev = head
    os.makedirs("research", exist_ok=True)
    open(rp, "w").write(prev.rstrip() + "\n\n" + "\n".join(L) + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:6])
