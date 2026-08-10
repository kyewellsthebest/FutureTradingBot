"""Fetch order book data from Databento. RUN THIS ON YOUR OWN MACHINE.

I cannot run it from the research container -- hist.databento.com is refused by
this environment's egress policy (403 on CONNECT), which is an organisation
network rule, not anything to do with the key.

    pip install databento
    export DATABENTO_KEY=db-...        # your key, NOT pasted into a file
    python fetch_book.py

It prices the request FIRST and refuses to download anything above MAX_USD
without you saying so, because the free credit is finite and depth data is
much larger than people expect.

WHY THESE TWO REQUESTS, IN THIS ORDER

  tbbo  -- one record per TRADE, carrying the best bid and offer at the moment
           it happened. Same row count as the tick data already on disk, so it
           is cheap, and it buys two things nothing else can:

             * the TRUE aggressor side. Every order flow number in this repo so
               far is inferred with the Lee-Ready tick rule, which is right
               about 85% of the time. f_ofi -- the one feature family that kept
               surfacing in the hunt -- is built on that guess. This replaces
               the guess with the fact.
             * queue imbalance at the top of book, and the real spread, at
               every trade.

  mbp-10 -- the full ten levels. Genuinely new information: resting size that
           has NOT traded. Every stream measured so far, all six of them, only
           ever sees what already happened. This is the only one that shows
           intent in advance.

           It is also far bigger, so this asks for THREE WEEKS. That is several
           million book updates -- plenty to measure whether depth carries
           signal at all. Do not buy a quarter of it until that answer is yes.

NQM6 ON PURPOSE. Every single one of the 120 "+$2 a trade" rows in the hunt
came from that one quarter, and the same rules lose $1.40 a trade across the
other seven. If the book explains what was different about NQM6, that is worth
knowing whichever way it comes out.
"""
import os
import sys

DATASET = "GLBX.MDP3"
SYMBOL = os.environ.get("SYMBOL", "NQM6")
MAX_USD = float(os.environ.get("MAX_USD", "40"))
OUTDIR = os.environ.get("OUTDIR", "book_out")

# NQM6 traded 2026-03-20 to 2026-06-18. The mbp-10 window is a liquid stretch
# well clear of both the roll and expiry.
JOBS = [
    dict(schema="tbbo",   start="2026-03-23", end="2026-06-12", tag="tbbo_full"),
    dict(schema="mbp-10", start="2026-04-06", end="2026-04-24", tag="mbp10_3wk"),
]


def main():
    key = os.environ.get("DATABENTO_KEY")
    if not key:
        sys.exit("set DATABENTO_KEY first (and rotate the one you pasted in "
                 "chat -- it is in a transcript now)")
    import databento as db
    c = db.Historical(key)
    os.makedirs(OUTDIR, exist_ok=True)

    print(f"{'job':12s} {'schema':8s} {'window':26s} {'size':>10s} {'cost':>9s}")
    plan = []
    for j in JOBS:
        kw = dict(dataset=DATASET, symbols=[SYMBOL], schema=j["schema"],
                  start=j["start"], end=j["end"], stype_in="raw_symbol")
        try:
            usd = c.metadata.get_cost(**kw)
            gb = c.metadata.get_billable_size(**kw) / 1e9
        except Exception as e:                                   # noqa: BLE001
            print(f"{j['tag']:12s} pricing failed: {e}")
            continue
        print(f"{j['tag']:12s} {j['schema']:8s} {j['start']}..{j['end']}  "
              f"{gb:8.2f}GB {usd:8.2f}$")
        plan.append((j, kw, usd))

    total = sum(u for _, _, u in plan)
    print(f"\ntotal ${total:.2f} (cap ${MAX_USD:.2f}, free credit is $125)")
    if total > MAX_USD:
        print("Above the cap. Re-run with MAX_USD=<higher> if you are happy, "
              "or shorten the windows in JOBS. Nothing downloaded.")
        return
    if input("download? [y/N] ").strip().lower() != "y":
        return

    for j, kw, _ in plan:
        print(f"\ndownloading {j['tag']} ...", flush=True)
        data = c.timeseries.get_range(**kw)
        df = data.to_df()
        out = os.path.join(OUTDIR, f"{SYMBOL}_{j['tag']}.parquet")
        df.to_parquet(out, compression="zstd")
        mb = os.path.getsize(out) / 1e6
        print(f"  {len(df):,} rows -> {out}  ({mb:.0f} MB)")
        print(f"  columns: {list(df.columns)[:14]}")

    print(f"\nDone. Put the files in data/book/ in the repo and push, or send "
          f"them over -- any format, I will convert. If the tbbo file is too "
          f"big for git, ship the mbp-10 one first; three weeks of depth is "
          f"enough to answer whether the book carries anything.")


if __name__ == "__main__":
    main()
