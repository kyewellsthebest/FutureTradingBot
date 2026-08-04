# Databento: what to buy, and exactly what to run

Why this and nothing else: everything in this repo is **trade prints** — what
already happened. Depth of book is **resting orders** — what people are
willing to do but haven't done yet, plus every cancellation. That is a
different information set, not a finer view of the same one. It is also what
the firms collecting the ~$1/trade of available edge actually trade on.

Verify all pricing on the site before paying — the figures below are what to
expect, not a quote.

## Links

| what | where |
|---|---|
| Main site | https://databento.com |
| Pricing | https://databento.com/pricing |
| CME dataset page | https://databento.com/datasets/GLBX.MDP3 |
| Python client docs | https://databento.com/docs/quickstart |
| Schema reference | https://databento.com/docs/schemas-and-data-formats |
| Cost estimation API | https://databento.com/docs/api-reference-historical/metadata/metadata-get-cost |

## What to buy

**Dataset:** `GLBX.MDP3` — CME Globex MDP 3.0. Covers NQ, ES, RTY, YM, CL, GC,
HG, everything we trade.

**Schema:** `mbo` — market by order. Every individual order add, modify, cancel
and trade, with order IDs. This is the full book, and it is the only schema
that contains what we do not already have.

Cheaper schemas and why they are not the point:
- `mbp-10` — top 10 price levels aggregated. Useful, much smaller, but loses
  individual orders so you cannot see queue position or spoofing patterns.
- `tbbo` — trades plus the quote at the moment of each trade. Cheap. Would
  answer "was the trade at the bid or the ask" properly instead of by tick
  rule. A reasonable **cheap first step** if you want to spend $20 not $200.
- `trades` — what we already have from Polygon. Do not buy this.

**Billing:** historical data is pay-as-you-go by volume, not a subscription.
You are charged for what you download. There is normally free trial credit on
signup — enough for the first test below.

**Expected cost:** MBO is large — roughly 1–3 GB per contract-month for NQ.
Budget $100–400 for a meaningful historical sample. **Always call the cost
endpoint before any download.**

## Step by step

**1.** Sign up at https://databento.com and create an API key
(Settings → API keys). Key looks like `db-xxxxxxxxxxxxxxxxxxxx`.

**2.** Add it to this repo as an Actions secret named `DATABENTO_API`
(Settings → Secrets and variables → Actions → New repository secret). Same
place `POLYGON_API` lives. Do not paste it into a chat or a file.

**3.** Price the request before buying anything:

```python
pip install databento

import databento as db
c = db.Historical("YOUR_KEY")

print(c.metadata.get_cost(
    dataset="GLBX.MDP3",
    symbols=["NQZ5"],
    stype_in="raw_symbol",
    schema="mbo",
    start="2025-11-03",
    end="2025-11-08",          # one week
))
```

That prints dollars. If a week of one contract is affordable, scale from
there. **Do not skip this step** — MBO volumes are large enough to produce a
surprising bill.

**4.** Buy one week first, not two years:

```python
data = c.timeseries.get_range(
    dataset="GLBX.MDP3",
    symbols=["NQZ5"],
    stype_in="raw_symbol",
    schema="mbo",
    start="2025-11-03",
    end="2025-11-08",
)
data.to_file("data/mbo/NQZ5_week.dbn.zst")
```

**5.** Tell me it is there and I will run the test that decides whether the
rest is worth buying — the same discipline as everything else: measure the
information content first, against a shuffled control, and convert it to
dollars per trade before anyone builds a strategy.

## What I will measure with it, in order

These are the questions trade prints **cannot** answer, ranked by how likely I
think they are to carry something:

1. **Queue imbalance** — resting size at the bid vs the ask. The single most
   documented short-horizon predictor in the microstructure literature, and
   completely invisible in trade data.
2. **Cancellation asymmetry** — orders pulled from one side before a move.
   Someone stepping away is information; the trade tape only sees the silence
   afterwards.
3. **Queue position economics** — how long a limit order at the front of the
   book actually waits, and what fraction fill. This directly measures the
   fill assumption that `FILL_REALITY.md` had to guess at, and would settle
   whether limit-entry backtests here were ever honest.
4. **Iceberg / hidden liquidity** — refreshing size at a price level.
5. **Book pressure at multiple levels** — the shape of the book, not just the
   top.

## The honest prior

Queue imbalance is real and well documented, but it decays in **seconds** and
is mostly harvested by people co-located at the exchange. On a retail
connection from a cloud VM, most of it will be gone before an order arrives.

What I expect: the information is there and measurably larger than anything in
trade prints, and a large part of it is unreachable at our latency. The test
is worth running because "measurably larger" and "unreachable" are both
quantities, and today proved we should measure rather than assume — but go in
expecting a fight over the last few hundred milliseconds, not a free lunch.

If a week of MBO shows queue imbalance predicting at IC 0.05+ where trade
prints managed 0.0098, that is a fivefold better signal and worth the full
purchase. If it shows 0.01 again, we stop, and you have spent $20 finding out.
