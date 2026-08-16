"""A1: buy top-of-book history and reduce it to a 1-second feature tape.

The pilot (research/DEPTH_PILOT.md) measured NQ book-state features on ONE
week and found quote rate at IC -0.084 (3.7 sigma) and spread at -0.056
(2.5 sigma), but could not settle the directional-imbalance question --
one week is not enough samples to separate IC 0.03 from zero. This buys
the weeks that can, and stores a tape rich enough that every feature in
the A2 harness is derivable offline without ever re-requesting a range.

That last point is the expensive one. Databento CHARGES AGAIN for a range
it has already served, so a re-download to add one column costs the same
as the original purchase. Everything the harness could plausibly want is
therefore extracted in this single pass and committed.

THE PLAN comes from data/depth/.buy, one purchase per line:

    NQU6 mbp-1 2026-07-20 2026-08-15

Every line is priced against the free metadata endpoint BEFORE a single
byte is downloaded, and the run aborts if the total exceeds MAX_SPEND.
The credit is roughly $48 with no real money behind it, so MAX_SPEND is
the whole safety story and it is set in the workflow, not defaulted here
to something generous.

PER SECOND, for every second that carried at least one event:

    bid_px ask_px bid_sz ask_sz   book state at the END of the second
    n_evt                         quote intensity
    n_trade tv_buy tv_sell        trade-through pressure, by aggressor
    bid_depl ask_depl             size removed from an unchanged level
    bid_add  ask_add              size added to an unchanged level

Imbalance, imbalance CHANGE, microprice minus mid, spread state, size
asymmetry and queue-depletion rate all derive from those columns, so A2
never needs the raw feed again.

Raw .dbn.zst files are processed in 6-hour chunks and deleted immediately;
only the derived parquet is committed.

Output: data/depth/<SYM>_book_1s.parquet
"""
import gc
import os
import sys
import time

import databento as db
import numpy as np
import pandas as pd

KEY = os.environ.get("DATABENTO_KEY")
if not KEY:
    sys.exit("DATABENTO_KEY not set")
MAX_SPEND = float(os.environ.get("MAX_SPEND", "42"))
OUTDIR = "data/depth"
PLAN_FILE = os.path.join(OUTDIR, ".buy")
DATASET = "GLBX.MDP3"
CHUNK_H = 6

os.makedirs(OUTDIR, exist_ok=True)
c = db.Historical(KEY)

COLS = ["action", "side", "size",
        "bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00"]


def read_plan():
    """One purchase per line: SYMBOL SCHEMA START END. '#' comments out."""
    plan = []
    for raw in open(PLAN_FILE):
        line = raw.split("#")[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 4:
            print(f"  ignoring unparseable plan line: {raw.strip()!r}",
                  flush=True)
            continue
        plan.append(tuple(parts))
    return plan


def price(plan):
    """Free metadata calls. Nothing is downloaded until this clears."""
    total = 0.0
    for sym, schema, s, e in plan:
        cost = c.metadata.get_cost(dataset=DATASET, symbols=[sym],
                                   stype_in="raw_symbol", schema=schema,
                                   start=s, end=e)
        size = c.metadata.get_billable_size(
            dataset=DATASET, symbols=[sym], stype_in="raw_symbol",
            schema=schema, start=s, end=e)
        print(f"plan: {sym} {schema} {s}..{e} -> ${cost:.2f} "
              f"({size/1e9:.2f} GB)", flush=True)
        total += cost
    print(f"planned total: ${total:.2f} (cap ${MAX_SPEND:.2f})", flush=True)
    if total > MAX_SPEND:
        sys.exit(f"over budget (${total:.2f} > ${MAX_SPEND:.2f}) -- "
                 "nothing purchased")
    return total


def reduce_chunk(path):
    """One .dbn.zst chunk -> per-second aggregates. Frame dies immediately.

    A full day of NQ mbp-1 as a DataFrame is what OOM-killed an earlier
    runner, so the frame is converted to numpy and dropped before any
    aggregation happens.
    """
    store = db.DBNStore.from_file(path)
    df = store.to_df()
    if not len(df):
        del df
        return None
    ts = df.index.view(np.int64)
    act = df["action"].to_numpy().astype("U1")
    side = df["side"].to_numpy().astype("U1")
    sz = df["size"].to_numpy().astype(np.float64)
    bpx = df["bid_px_00"].to_numpy().astype(np.float64)
    apx = df["ask_px_00"].to_numpy().astype(np.float64)
    bsz = df["bid_sz_00"].to_numpy().astype(np.float64)
    asz = df["ask_sz_00"].to_numpy().astype(np.float64)
    del df, store
    gc.collect()

    o = np.argsort(ts, kind="stable")
    ts, act, side, sz = ts[o], act[o], side[o], sz[o]
    bpx, apx, bsz, asz = bpx[o], apx[o], bsz[o], asz[o]

    # size change at a level that did NOT move. A level that reprices has
    # a new queue, so its size delta is not depletion of the old one and
    # must not be counted as such.
    d_bsz = np.zeros(len(ts))
    d_asz = np.zeros(len(ts))
    same_b = np.zeros(len(ts), dtype=bool)
    same_a = np.zeros(len(ts), dtype=bool)
    d_bsz[1:] = bsz[1:] - bsz[:-1]
    d_asz[1:] = asz[1:] - asz[:-1]
    same_b[1:] = bpx[1:] == bpx[:-1]
    same_a[1:] = apx[1:] == apx[:-1]
    b_depl = np.where(same_b & (d_bsz < 0), -d_bsz, 0.0)
    b_add = np.where(same_b & (d_bsz > 0), d_bsz, 0.0)
    a_depl = np.where(same_a & (d_asz < 0), -d_asz, 0.0)
    a_add = np.where(same_a & (d_asz > 0), d_asz, 0.0)

    is_tr = act == "T"
    # Databento: `side` is the initiating side, so on a trade it is the
    # AGGRESSOR -- 'B' lifted the offer, 'A' hit the bid.
    tv_b = np.where(is_tr & (side == "B"), sz, 0.0)
    tv_a = np.where(is_tr & (side == "A"), sz, 0.0)

    sec = ts // 1_000_000_000
    u, start = np.unique(sec, return_index=True)
    end = np.r_[start[1:], len(sec)]
    last = end - 1

    def ssum(v):
        return np.add.reduceat(v, start)

    out = pd.DataFrame({
        "sec": u,
        "bid_px": bpx[last].astype(np.float32),
        "ask_px": apx[last].astype(np.float32),
        "bid_sz": bsz[last].astype(np.float32),
        "ask_sz": asz[last].astype(np.float32),
        "n_evt": (end - start).astype(np.int32),
        "n_trade": ssum(is_tr.astype(np.float64)).astype(np.int32),
        "tv_buy": ssum(tv_b).astype(np.float32),
        "tv_sell": ssum(tv_a).astype(np.float32),
        "bid_depl": ssum(b_depl).astype(np.float32),
        "ask_depl": ssum(a_depl).astype(np.float32),
        "bid_add": ssum(b_add).astype(np.float32),
        "ask_add": ssum(a_add).astype(np.float32),
    })
    del ts, act, side, sz, bpx, apx, bsz, asz
    gc.collect()
    return out


def buy(sym, schema, s, e):
    days = pd.bdate_range(s, pd.Timestamp(e) - pd.Timedelta(days=1))
    frames = []
    for day in days:
        ds = day.strftime("%Y-%m-%d")
        got = 0
        for h0 in range(0, 24, CHUNK_H):
            path = os.path.join(OUTDIR, f"_{sym}_{ds}_{h0}.dbn.zst")
            a = (day + pd.Timedelta(hours=h0)).isoformat()
            b = (day + pd.Timedelta(hours=h0 + CHUNK_H)).isoformat()
            t0 = time.time()
            try:
                c.timeseries.get_range(dataset=DATASET, symbols=[sym],
                                       stype_in="raw_symbol", schema=schema,
                                       start=a, end=b, path=path)
                part = reduce_chunk(path)
            except Exception as exc:                          # noqa: BLE001
                print(f"  {ds} h{h0}: {str(exc)[:100]}", flush=True)
                part = None
            finally:
                if os.path.exists(path):
                    os.remove(path)
            if part is not None and len(part):
                frames.append(part)
                got += len(part)
            gc.collect()
        print(f"  {ds}: {got:,} seconds ({time.time()-t0:.0f}s last chunk)",
              flush=True)
    if not frames:
        print(f"  {sym}: nothing retrieved", flush=True)
        return None
    A = pd.concat(frames, ignore_index=True)
    del frames
    gc.collect()
    A = A.groupby("sec", as_index=False).agg({
        "bid_px": "last", "ask_px": "last", "bid_sz": "last",
        "ask_sz": "last", "n_evt": "sum", "n_trade": "sum",
        "tv_buy": "sum", "tv_sell": "sum", "bid_depl": "sum",
        "ask_depl": "sum", "bid_add": "sum", "ask_add": "sum"})
    A = A.sort_values("sec").reset_index(drop=True)
    out = os.path.join(OUTDIR, f"{sym}_book_1s.parquet")
    A.to_parquet(out, index=False)
    days_n = A["sec"].floordiv(86400).nunique()
    print(f"wrote {out}: {len(A):,} seconds across {days_n} days "
          f"({os.path.getsize(out)/1e6:.1f} MB)", flush=True)
    return A


def main():
    if not os.path.exists(PLAN_FILE):
        sys.exit("no data/depth/.buy -- nothing staged, nothing purchased")
    plan = read_plan()
    if not plan:
        sys.exit("data/depth/.buy has no usable plan line")
    total = price(plan)
    print(f"\nproceeding with ${total:.2f} of purchases\n", flush=True)
    for sym, schema, s, e in plan:
        print(f"=== {sym} {schema} {s}..{e} ===", flush=True)
        buy(sym, schema, s, e)


if __name__ == "__main__":
    main()
