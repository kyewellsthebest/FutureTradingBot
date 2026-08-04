"""TICK -> EVENT BARS + ORDER FLOW.

Downloads the NQ tick release (12 quarterly contracts, ~280M trades) and
builds bar series that are IMPOSSIBLE to construct from OHLCV:

  time      — control (matches what every prior campaign used)
  tick      — closes after N trades
  volume    — closes after N contracts
  dollar    — closes after $N notional
  range     — closes after X points of movement
  imbalance — closes after |signed volume| exceeds a threshold

Event bars sample the market by ACTIVITY rather than by the clock. Returns
are closer to normal, and information arrives at a constant rate per bar
instead of being crushed into whichever 5 minutes happened to be busy.

Every bar also carries ORDER-FLOW columns derived from the trade tape:
  buyvol/sellvol  — tick-rule signed volume (uptick = buyer-initiated)
  delta           — buyvol - sellvol for the bar
  cumdelta        — running signed volume
  bigratio        — share of volume from trades >= BIG_TRADE contracts
  ntrades, dur_s  — activity/intensity
  lowsz / highsz  — CONTRACTS TRADED AT THE BAR'S LOW / HIGH
                    ^ this is the fill-probability measurement. A bare touch
                      with 2 contracts is not a fill; 500 contracts is.

Usage:
  python -m research.tickbars build        # fetch release + build all series
  python -m research.tickbars build --only volume_5000
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(os.environ.get("M2_REPO", "/home/user/FutureTradingBot"))
RAW = ROOT / "data" / "tick" / "raw"
OUT = ROOT / "data" / "tick" / "bars"
CONTRACTS = ["NQU3", "NQZ3", "NQH4", "NQM4", "NQU4", "NQZ4",
             "NQH5", "NQM5", "NQU5", "NQZ5", "NQH6", "NQM6"]
BIG_TRADE = 10          # contracts; NQ retail is 1-3, institutional prints bigger
NS = 1_000_000_000

# (name, kind, threshold) — thresholds chosen to land ~80k-400k bars each
SERIES = [
    ("time_5m",      "time",      300),
    ("time_15m",     "time",      900),
    ("tick_250",     "tick",      250),
    ("tick_1000",    "tick",      1000),
    ("tick_4000",    "tick",      4000),
    ("vol_2000",     "volume",    2000),
    ("vol_8000",     "volume",    8000),
    ("vol_30000",    "volume",    30000),
    ("dollar_50M",   "dollar",    50_000_000),
    ("dollar_200M",  "dollar",    200_000_000),
    ("range_10",     "range",     10.0),
    ("range_25",     "range",     25.0),
    ("range_50",     "range",     50.0),
    ("imb_1500",     "imbalance", 1500),
    ("imb_6000",     "imbalance", 6000),
]


def fetch_release():
    """Pull the tick parquets from the GitHub release (idempotent)."""
    RAW.mkdir(parents=True, exist_ok=True)
    missing = [c for c in CONTRACTS if not (RAW / f"{c}.parquet").exists()]
    if not missing:
        print(f"all {len(CONTRACTS)} contracts already local")
        return
    print(f"downloading {len(missing)} contracts from release nq-ticks-raw")
    # curl, not the gh CLI: the cloud execution environment has no gh, and
    # release assets are plain HTTPS downloads anyway.
    base = ("https://github.com/kyewellsthebest/futuretradingbot"
            "/releases/download/nq-ticks-raw")
    for c in missing:
        subprocess.run(["curl", "-sSLf", "-o", str(RAW / f"{c}.parquet"),
                        f"{base}/{c}.parquet"], check=True)
        print(f"  {c} ok ({(RAW / f'{c}.parquet').stat().st_size/1e6:.0f} MB)",
              flush=True)


def load_contract(c: str):
    """One contract's trades. Processing per-contract keeps peak memory near
    ~1GB instead of ~10GB, and is also more correct: an event bar must never
    span a contract roll."""
    f = RAW / f"{c}.parquet"
    if not f.exists():
        return None
    d = pd.read_parquet(f)
    d = d[(d["size"] > 0) & (d["price"] > 0)].sort_values("ts")
    return d.drop_duplicates(subset=["ts", "price", "size"]).reset_index(drop=True)


def signed_volume(price: np.ndarray, size: np.ndarray) -> np.ndarray:
    """Tick rule: uptick = buyer-initiated, downtick = seller-initiated,
    unchanged inherits the previous sign. No bid/ask in the feed, so this is
    the standard proxy — imperfect but unbiased and causal."""
    d = np.sign(np.diff(price, prepend=price[0]))
    # forward-fill zeros with the last non-zero direction
    nz = d != 0
    idx = np.where(nz, np.arange(len(d)), 0)
    np.maximum.accumulate(idx, out=idx)
    d = d[idx]
    d[d == 0] = 1
    return (d * size).astype(np.int64)


def bar_edges(kind: str, thr, ts: np.ndarray, price: np.ndarray,
              size: np.ndarray, sgn: np.ndarray) -> np.ndarray:
    """Index of the LAST tick in each bar."""
    n = len(price)
    if kind == "time":
        sec = ts // (NS * int(thr))
        return np.where(np.diff(sec, append=sec[-1] + 1) != 0)[0]
    if kind == "tick":
        return np.arange(int(thr) - 1, n, int(thr))
    if kind in ("volume", "dollar", "imbalance"):
        if kind == "volume":
            run = np.cumsum(size)
        elif kind == "dollar":
            run = np.cumsum(price * size)
        else:
            run = np.cumsum(np.abs(sgn))     # abs signed vol accumulates activity
        # bucket boundaries every `thr` units
        buckets = (run / float(thr)).astype(np.int64)
        return np.where(np.diff(buckets, append=buckets[-1] + 1) != 0)[0]
    if kind == "range":
        # Inherently sequential: each bar's start is the previous bar's end.
        # Iterating a Python list instead of a numpy array avoids building a
        # numpy scalar per tick and runs ~10x faster over 280M trades.
        pl = price.tolist()
        ends = []
        start_px = pl[0]
        t = float(thr)
        for i, v in enumerate(pl):
            if v - start_px >= t or start_px - v >= t:
                ends.append(i)
                start_px = v
        return np.array(ends, dtype=np.int64)
    raise ValueError(kind)


def build(name: str, kind: str, thr, arrs) -> pd.DataFrame:
    ts, px, sz, sgn = arrs          # computed once per contract, not per series
    ends = bar_edges(kind, thr, ts, px, sz, sgn)
    if len(ends) < 500:
        print(f"  {name}: only {len(ends)} bars — skipped")
        return None
    starts = np.r_[0, ends[:-1] + 1]

    rows = []
    big = sz >= BIG_TRADE
    for s, e in zip(starts, ends):
        if e < s:
            continue
        p = px[s:e + 1]; z = sz[s:e + 1]; g = sgn[s:e + 1]
        hi = p.max(); lo = p.min()
        rows.append((
            ts[e], p[0], hi, lo, p[-1], int(z.sum()),
            int(g[g > 0].sum()), int(-g[g < 0].sum()),
            int(e - s + 1), (ts[e] - ts[s]) / NS,
            float(z[big[s:e + 1]].sum()) / max(int(z.sum()), 1),
            int(z[p <= lo + 1e-9].sum()),      # size traded AT the low
            int(z[p >= hi - 1e-9].sum()),      # size traded AT the high
        ))
    b = pd.DataFrame(rows, columns=[
        "ts", "open", "high", "low", "close", "volume",
        "buyvol", "sellvol", "ntrades", "dur_s", "bigratio", "lowsz", "highsz"])
    b["ts"] = pd.to_datetime(b.ts, unit="ns", utc=True)
    b["delta"] = b.buyvol - b.sellvol
    b["cumdelta"] = b.delta.cumsum()
    return b


def plan():
    """Emit a GitHub Actions matrix sized to the bars that actually got built.

    Search cost per config scales with the hold window in BARS, which scales
    with bar density. A hardcoded shard count would leave the coarse series
    idle and time out the fine ones, so each series gets shards proportional to
    its density (measured, not guessed)."""
    import json as _json
    entries = []
    for name, _, _ in SERIES:
        f = OUT / f"NQ_{name}.parquet"
        if not f.exists():
            continue
        b = pd.read_parquet(f, columns=["ts"])
        per_day = len(b) / max(pd.to_datetime(b.ts).dt.date.nunique(), 1)
        sc = per_day / 288.0                      # vs 5-minute bars
        nsh = int(min(24, max(4, round(4 * max(sc, 0.25) ** 0.9 * 1.6))))
        for k in range(nsh):
            entries.append({"series": name, "shard": f"{k}/{nsh}",
                            "tag": f"{name}-{k}"})
    print(f"{len(entries)} search jobs", file=sys.stderr)
    Path(os.environ.get("GITHUB_OUTPUT", "/dev/stdout")).open("a").write(
        "matrix=" + _json.dumps({"include": entries}) + "\n")


def main():
    if "plan" in sys.argv:
        plan()
        return
    if "build" not in sys.argv:
        print(__doc__)
        return
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]

    fetch_release()
    OUT.mkdir(parents=True, exist_ok=True)
    todo = [x for x in SERIES if (only is None or x[0] == only)]
    acc = {name: [] for name, _, _ in todo}
    total = 0
    for c in CONTRACTS:
        t = load_contract(c)
        if t is None:
            print(f"  {c}: MISSING", flush=True)
            continue
        total += len(t)
        print(f"  {c}: {len(t):,} trades", flush=True)
        arrs = (t["ts"].values.astype(np.int64),
                t["price"].values.astype(np.float64),
                t["size"].values.astype(np.int64), None)
        arrs = (arrs[0], arrs[1], arrs[2], signed_volume(arrs[1], arrs[2]))
        for name, kind, thr in todo:
            b = build(name, kind, thr, arrs)
            if b is not None:
                acc[name].append(b)
        del t, arrs
    print(f"TAPE TOTAL: {total:,} trades")
    for name, kind, thr in todo:
        parts = acc[name]
        if not parts:
            print(f"  {name}: no bars"); continue
        b = pd.concat(parts, ignore_index=True).sort_values("ts").reset_index(drop=True)
        b["cumdelta"] = b.delta.cumsum()          # re-run across the full tape
        f = OUT / f"NQ_{name}.parquet"
        b.to_parquet(f, compression="zstd", index=False)
        span_d = max((b.ts.max() - b.ts.min()).days, 1)
        print(f"  {name:<12} {len(b):>8,} bars  {len(b)/span_d:>6.0f}/day -> {f.name}",
              flush=True)


if __name__ == "__main__":
    main()
