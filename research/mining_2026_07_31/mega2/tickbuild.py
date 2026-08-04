"""Event bars from the raw tape, with the intrabar path kept.

Two things every bar-based test in this project has thrown away.

THE CLOCK. A five-minute bar contains whatever happened to occur in five
minutes -- a hundred trades at lunch, forty thousand at the open. Event bars
close after a fixed amount of ACTIVITY instead: N trades, N contracts, or N
points of movement. Each bar then carries roughly the same amount of
information, which is the sampling the statistics actually assume.

THE PATH. A bar says low 45, high 80. If the stop sat at 47 and the target at
75, whether that trade won or lost depends entirely on which came first, and
the bar cannot say. Every backtest here resolved it by assuming the stop hit
first -- conservative, but a guess on a large share of trades. The tape knows.
So each bar records the position of its high and its low within itself, and
the exit logic can then be exact rather than assumed.

Output columns per bar: OHLC, volume, delta (tick-rule signed volume), the
size that printed at the high and at the low, trade count, duration, and
hi_first -- whether the high happened before the low.

Usage: python tickbuild.py [SERIES ...]     (default: all)
"""
import os, sys, glob
import numpy as np, pandas as pd

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
RAW = os.path.join(ROOT, "data", "tick", "raw")
MULTI = os.path.join(ROOT, "data", "tick", "multi")
OUT = os.path.join(ROOT, "data", "tick", "ev")
# Which root to build. Everything outside NQ lives in the multi directory,
# pulled from the multi-ticks-raw release.
ROOTSYM = os.environ.get("TB_ROOT", "NQ").upper()
NS = 1_000_000_000
BIG = 10

# Thresholds are per-root: 500 NQ trades and 500 copper trades are not
# comparable events, so each root gets thresholds scaled to its own activity.
SCALE = {"NQ": 1.0, "ES": 1.0, "RTY": 0.35, "YM": 0.30,
         "CL": 0.45, "GC": 0.45, "HG": 0.15}.get(ROOTSYM, 0.5)
# Range thresholds are quoted in TICKS, not points. 15 points is 60 ticks on
# NQ and 1,500 on crude -- the same number of points is a completely different
# event from one market to the next, whereas a tick is the market's own unit.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from econ import ECON
TICKSZ = ECON[ROOTSYM][1]

# (name, kind, threshold). No clock in any of them.
SERIES = [
    ("tick_500",   "tick",      500),
    ("tick_2000",  "tick",      2000),
    ("vol_5000",   "volume",    5000),
    ("vol_20000",  "volume",    20000),
    ("range_60t",  "range",     60),      # ticks
    ("range_160t", "range",     160),     # ticks
    ("imb_2000",   "imbalance", 2000),
]


def bar_ids(px, sz, sv, kind, thr):
    """Assign every trade to a bar, closing on activity rather than on time."""
    n = len(px)
    if kind == "tick":
        return np.arange(n) // int(thr)
    if kind == "volume":
        return (np.cumsum(sz) // thr).astype(np.int64)
    if kind == "imbalance":
        # closes when |signed volume| since the last close exceeds the
        # threshold, so a bar ends when one side has genuinely pressed
        out = np.empty(n, np.int64); run = 0.0; b = 0
        for i in range(n):
            run += sv[i]
            out[i] = b
            if abs(run) >= thr: b += 1; run = 0.0
        return out
    # range: closes after the price has covered thr points since the bar opened
    out = np.empty(n, np.int64); b = 0; lo = hi = px[0]
    for i in range(n):
        if px[i] < lo: lo = px[i]
        if px[i] > hi: hi = px[i]
        out[i] = b
        if hi - lo >= thr: b += 1; lo = hi = px[i]
    return out


def build(path, kind, thr):
    d = pd.read_parquet(path).sort_values("ts", kind="stable")
    ts = d.ts.values
    px = d.price.values.astype(float)
    sz = d["size"].values.astype(float)
    dp = np.diff(px, prepend=px[0])
    s = np.sign(dp)
    s = pd.Series(np.where(s == 0, np.nan, s)).ffill().fillna(1.0).values
    sv = s * sz
    b = bar_ids(px, sz, sv, kind, thr)
    g = pd.DataFrame(dict(b=b, px=px, sz=sz, sv=sv, ts=ts,
                          big=np.where(sz >= BIG, sz, 0.0),
                          i=np.arange(len(px))))
    a = g.groupby("b").agg(open=("px", "first"), high=("px", "max"),
                           low=("px", "min"), close=("px", "last"),
                           vol=("sz", "sum"), delta=("sv", "sum"),
                           bigv=("big", "sum"), ntr=("px", "size"),
                           ts=("ts", "first"), tend=("ts", "last"),
                           imax=("px", "idxmax"), imin=("px", "idxmin"))
    a = a[a.vol > 0]
    if len(a) < 200: return None
    # THE PATH: did the high print before the low? This is what a bar cannot
    # tell you and what decides stop-versus-target when both are touched.
    a["hi_first"] = (a["imax"].values < a["imin"].values)
    hi = g.px.values == g.groupby("b").px.transform("max").values
    lo = g.px.values == g.groupby("b").px.transform("min").values
    a["hisz"] = g[hi].groupby("b").sz.sum().reindex(a.index).fillna(0.0)
    a["losz"] = g[lo].groupby("b").sz.sum().reindex(a.index).fillna(0.0)
    a["dur_s"] = (a.tend - a.ts) / NS
    return a.drop(columns=["imax", "imin", "tend"]).reset_index(drop=True)


want = sys.argv[1:] or [s[0] for s in SERIES]
os.makedirs(OUT, exist_ok=True)
src = RAW if ROOTSYM == "NQ" else MULTI
files = sorted(f for f in glob.glob(os.path.join(src, "*.parquet"))
               if os.path.basename(f).startswith(ROOTSYM))
print(f"{ROOTSYM}: {len(files)} contracts -> {len(want)} series "
      f"(activity scale {SCALE})\n", flush=True)
for name, kind, thr in SERIES:
    if name not in want: continue
    # activity thresholds scale with the market's trade rate; range
    # thresholds convert ticks -> points using this market's tick size
    thr = (max(round(thr * SCALE), 1) if kind != "range"
           else max(round(thr * SCALE), 4) * TICKSZ)
    parts = []
    for f in files:
        c = os.path.basename(f).replace(".parquet", "")
        try:
            a = build(f, kind, thr)
        except Exception as e:
            print(f"  {name}/{c}: failed ({e})", flush=True); continue
        if a is None:
            print(f"  {name}/{c}: too few bars", flush=True); continue
        a["contract"] = c
        parts.append(a)
    if not parts: continue
    b = pd.concat(parts, ignore_index=True).sort_values("ts").reset_index(drop=True)
    p = os.path.join(OUT, f"{ROOTSYM}_{name}.parquet")
    b.to_parquet(p, compression="zstd", index=False)
    span = (b.ts.max() - b.ts.min()) / NS / 86400
    print(f"{name:>10s}: {len(b):>9,} bars over {span:.0f} days, "
          f"median {b.dur_s.median():.1f}s and {b.ntr.median():.0f} trades each, "
          f"high-before-low {b.hi_first.mean():.0%}", flush=True)
