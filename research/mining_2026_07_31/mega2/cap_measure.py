"""Per-market size caps + daily P&L series for the 52-week projection.

For each deployed cell (MNQ 5/10/20, MES 1.5/3/6, MYM 16/20/40; all
w=6, retr .618, hold 10m, continuation), replays the exact pulse fill
model on the HELD-OUT segment of every quarter and records per trade:

  - pnl (per micro, $), entry timestamp
  - THROUGH-VOLUME: contracts (big-contract units) that trade STRICTLY
    beyond our limit price within 60s of the first cross. That volume
    went through our level; resting size up to it would have filled.

Cap logic (conservative): 1 big contract = 10 micros of notional. We
allow ourselves ~10% of the through-notional at the 25th percentile, so
cap_micros = p25(through_volume_in_bigs) -- the two factors of 10
cancel. Below that size, 75%+ of historical fills would have absorbed
us at <=10% participation; beyond it we start being the market.

Writes data/cap_measure.json. Read by projection_52wk.py.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402

TRAIN = 0.60
COMM = 1.24
DELAY_NS = 250_000_000
COOL_NS = 60_000_000_000
HOLD_NS = 10 * 60_000_000_000

MKTS = {
    "MNQ": dict(sym="NQ", imp=5.0, S=10.0, T=20.0, tv=2.0, slip=0.25),
    "MES": dict(sym="ES", imp=1.5, S=3.0, T=6.0, tv=5.0, slip=0.25),
    "MYM": dict(sym="YM", imp=16.0, S=20.0, T=40.0, tv=0.5, slip=1.0),
}
W = 6
RETR = 0.618


def replay(ts, px, sz, bt, bc, bpos, rth, lo, hi, imp, S, T, tv, slip):
    out = []
    last_x = -10**18
    for i in range(max(lo, W + 1), hi):
        if not rth[i] or bt[i] < last_x + COOL_NS:
            continue
        move = bc[i] - bc[i - W]
        if abs(move) < imp:
            continue
        up = move > 0
        limit = bc[i] - RETR * move
        side = 1 if up else -1
        j0 = np.searchsorted(ts, bt[i] + 60_000_000_000 + DELAY_NS)
        j1 = np.searchsorted(ts, bt[i] + 60_000_000_000 + HOLD_NS)
        seg = px[j0:j1]
        if not len(seg):
            continue
        hitf = np.flatnonzero(seg < limit) if up else \
            np.flatnonzero(seg > limit)
        if not len(hitf):
            continue
        f = hitf[0]
        entry = limit
        rest = seg[f:]
        stop = entry - side * S
        tgt = entry + side * T
        if side > 0:
            si = np.flatnonzero(rest <= stop)
            ti = np.flatnonzero(rest > tgt)
        else:
            si = np.flatnonzero(rest >= stop)
            ti = np.flatnonzero(rest < tgt)
        s_at = si[0] if len(si) else 10**9
        t_at = ti[0] if len(ti) else 10**9
        if t_at < s_at:
            gain = T * tv
        elif s_at < 10**9:
            xp = rest[s_at]
            ex = min(xp, stop) if side > 0 else max(xp, stop)
            gain = (side * (ex - entry) - slip) * tv
        else:
            gain = (side * (rest[-1] - entry) - slip) * tv
        # through-volume: contracts trading STRICTLY beyond the limit
        # within 60s of the first cross (the fill-capacity at our price)
        k0 = j0 + f
        k1 = min(np.searchsorted(ts, ts[k0] + 60_000_000_000), j1)
        pseg, vseg = px[k0:k1], sz[k0:k1]
        thr = float(vseg[pseg < limit].sum() if up
                    else vseg[pseg > limit].sum())
        out.append((gain - COMM, int(ts[k0]), thr))
        last_x = bt[i] + 60_000_000_000 + HOLD_NS
    return out


def main():
    meta = fuse.tape_meta()
    res = {}
    for mk, cfg in MKTS.items():
        sym = cfg["sym"]
        if sym == "NQ":
            cons = [c for c in fuse.NQ_CONTRACTS if c in meta]
        else:
            cons = sorted((c for c, v in meta.items() if v["sym"] == sym
                           and v["n"] > 3_000_000),
                          key=lambda c: meta[c]["t0"])
        trades = []
        for cn in cons:
            ts, px, sz = fuse.load_tape(meta[cn]["path"])
            idx = pd.to_datetime(ts)
            close = pd.Series(px, index=idx).resample("1min").last().ffill()
            bt = close.index.view(np.int64)
            bc = close.values
            bpos = np.searchsorted(ts, bt + 60_000_000_000, side="right")
            rth = (close.index.hour * 60 + close.index.minute
                   >= 13 * 60 + 30) & (close.index.hour < 20)
            n = len(bc)
            cut = int(n * TRAIN)
            trades += replay(ts, px, sz, bt, bc, bpos, rth, cut, n,
                             cfg["imp"], cfg["S"], cfg["T"], cfg["tv"],
                             cfg["slip"])
            del ts, px, sz, close
            print(f"  {mk} {cn}: {len(trades)} cum trades", flush=True)
        pnl = np.array([t[0] for t in trades])
        ets = np.array([t[1] for t in trades], dtype=np.int64)
        thr = np.array([t[2] for t in trades])
        daily = pd.Series(pnl, index=pd.to_datetime(ets)).resample("D").sum()
        daily = daily[daily != 0]
        res[mk] = {
            "n_trades": len(trades),
            "total": float(pnl.sum()),
            "daily": {d.strftime("%Y-%m-%d"): round(float(v), 2)
                      for d, v in daily.items()},
            "through_p10": float(np.percentile(thr, 10)),
            "through_p25": float(np.percentile(thr, 25)),
            "through_p50": float(np.percentile(thr, 50)),
            "cap_micros": int(max(1, np.percentile(thr, 25))),
        }
        print(f"{mk}: {len(trades)} trades ${pnl.sum():+,.0f} | through "
              f"p10 {np.percentile(thr, 10):.0f} p25 "
              f"{np.percentile(thr, 25):.0f} p50 "
              f"{np.percentile(thr, 50):.0f} -> cap "
              f"{res[mk]['cap_micros']} micros", flush=True)
    out = os.path.join(fuse.ROOT, "data", "cap_measure.json")
    json.dump(res, open(out, "w"))
    print("wrote", out, flush=True)


if __name__ == "__main__":
    main()
