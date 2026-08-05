"""Destruction battery for OPENS (opening-drive continuation, second scale).

Rule under test: at 9:30:05, if price has moved >= k points from the 9:30:00
open, enter in that direction; exit at 10:00 (or variant).

Battery: threshold grid, exit grid, ENTRY LATENCY (+5s, +25s, +55s — can a
retail-speed system still capture it?), quarterly stability, cost stress,
combined L+S portfolio weekly stats, MC bootstrap.
"""
import sys, warnings, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import harness as H
from tick_features import load_sec

H.IS_END = "2025-03-01"
H.OOS_START = "2025-03-01"

df = load_sec(columns=["n_trades"])
arrays = H.get_arrays(df)
hhmmss = pd.Series(df.index.hour * 10000 + df.index.minute * 100 + df.index.second,
                   index=df.index)
o930 = df["open"].where(df["hhmm"] == 930).groupby(df["tday"]).transform("first")
drv = df["close"] - o930


def sig_at(second, k):
    """First bar in [93000+second, +3s] with |drive| >= k."""
    w = (hhmmss >= 93000 + second) & (hhmmss <= 93002 + second)
    first = w & ~w.shift(1).fillna(False).astype(bool)
    return first & (drv > k), first & (drv < -k)


def rep(tag, res, cost=None):
    if cost is not None:
        old = H.COST_RT
        H.COST_RT = cost
    s_is, s_oos = res.stats(end=H.IS_END), res.stats(start=H.OOS_START)
    if cost is not None:
        H.COST_RT = old
    print(f"  IS>> {H.fmt(tag, s_is)}")
    print(f"  OOS> {H.fmt(tag, s_oos)}")
    return res


EXQ = {"to935": H.ExitSpec(max_hold=300), "to1000": H.ExitSpec(max_hold=1800),
       "to1030": H.ExitSpec(max_hold=3600)}

print("== threshold grid (entry 9:30:05, exit 10:00) ==")
for k in (1, 2, 3, 5, 8):
    up, dn = sig_at(5, k)
    rep(f"L k={k}", H.simulate(df, up, +1, EXQ["to1000"], "nq", arrays=arrays))
    rep(f"S k={k}", H.simulate(df, dn, -1, EXQ["to1000"], "nq", arrays=arrays))

print("== exit grid (k=2) ==")
up, dn = sig_at(5, 2)
for ek, e in EXQ.items():
    rep(f"L {ek}", H.simulate(df, up, +1, e, "nq", arrays=arrays))
    rep(f"S {ek}", H.simulate(df, dn, -1, e, "nq", arrays=arrays))

print("== LATENCY: signal measured at 9:30:0X, k=2, exit 10:00 ==")
for sec in (10, 30, 60):
    up_d, dn_d = sig_at(sec, 2)
    rep(f"L sig@+{sec}s", H.simulate(df, up_d, +1, EXQ["to1000"], "nq", arrays=arrays))
    rep(f"S sig@+{sec}s", H.simulate(df, dn_d, -1, EXQ["to1000"], "nq", arrays=arrays))

print("== cost stress (k=2, to1000, L+S) ==")
up, dn = sig_at(5, 2)
rl = H.simulate(df, up, +1, EXQ["to1000"], "nq", arrays=arrays)
rs = H.simulate(df, dn, -1, EXQ["to1000"], "nq", arrays=arrays)
for c in (4.40, 8.40, 14.40):
    rep(f"L cost=${c}", rl, cost=c)

print("== quarterly stability (k=2, to1000, L+S combined) ==")
t = pd.concat([rl.trades, rs.trades]).sort_values("exit_time")
net = t["pnl_pts"] * 20 - H.COST_RT
q = net.groupby(t["exit_time"].dt.tz_localize(None).dt.to_period("Q")).agg(["sum", "count", "mean"])
print(q.round(1).to_string())

print("== combined weekly stats ==")
wk = net.groupby(t["exit_time"].dt.tz_localize(None).dt.to_period("W")).sum()
gross_wk = (t["pnl_pts"] * 20).groupby(t["exit_time"].dt.tz_localize(None).dt.to_period("W")).sum()
eq = net.cumsum()
dd = eq - eq.cummax()
print(f"trades/wk={len(t)/len(wk):.1f}  $/wk gross={gross_wk.mean():.0f} net={wk.mean():.0f} "
      f"std={wk.std():.0f} posW={(wk>0).mean():.2f}")
print(f"worst day={net.groupby(t['exit_time'].dt.date).sum().min():.0f} "
      f"worst wk={wk.min():.0f} avg losing wk={wk[wk<0].mean():.0f} maxDD={dd.min():.0f}")
rng = np.random.default_rng(11)
wkv = wk.values
dds = [ (lambda p: (p - np.maximum.accumulate(p)).min())(rng.choice(wkv, len(wkv), True).cumsum()) for _ in range(5000)]
print(f"MC median maxDD={np.median(dds):.0f}  5pct={np.percentile(dds,5):.0f}")
t.to_csv(H.CACHE / "opens_trades.csv", index=False)
