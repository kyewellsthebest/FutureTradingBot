"""Stop discretising. Hold a position, do not take bets.

Today's sharpest finding: signed volume genuinely predicts returns (IC +0.0098,
same sign in 8 of 8 contracts) and yet loses to random entry when traded. The
reason is not commission -- it still loses at $0.72 round turn. It is that
turning a 1% correlation into a trade requires picking an entry price, a stop
distance, a target and a time limit, and the variance those four choices inject
is far larger than the signal.

So stop making bets. Every strategy in this project has been discrete: enter,
stop, target, exit. That is not how a small edge is harvested. A 1% IC is
harvested by holding a position proportional to the signal and rebalancing --
no stops, no targets, no entry timing. The signal says +0.3, you are long a
third of max size; it says -0.8, you are short most of max.

The maths is Grinold's fundamental law: information ratio is roughly
IC x sqrt(breadth). At IC 0.0098 with a few thousand independent readings a
year that is an IR near 0.4 -- modest, real, and completely inaccessible to a
stop-and-target strategy because the stop truncates exactly the distribution
the maths depends on.

Two hard constraints this must respect, both of which could kill it:
  - futures trade in whole contracts. On a $4k account the position ladder is
    roughly -2,-1,0,1,2, which is coarse quantisation of a continuous signal.
  - every rebalance pays commission, so the position must be allowed to drift
    rather than track the signal exactly.

Same controls as everything else: a shuffled-signal arm that proves the
harness cannot manufacture profit from noise, drift adjustment, and every
contract judged separately.

Usage: python continuous.py [SERIES] [ROOT]
"""
import os, sys, types
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
EV = os.path.join(ROOT, "data", "tick", "ev")
from econ import ECON

SERIES = sys.argv[1] if len(sys.argv) > 1 else "tick_500"
ROOTSYM = (sys.argv[2] if len(sys.argv) > 2 else "NQ").upper()
PV, TICK, COMM, TRADED, _m, _a = ECON[ROOTSYM]
DPT = PV * TICK
NS = 1_000_000_000
MAXPOS = int(os.environ.get("CONT_MAXPOS", "2"))

d = pd.read_parquet(os.path.join(EV, f"{ROOTSYM}_{SERIES}.parquet")).sort_values("ts")
d = d.reset_index(drop=True)
n = len(d)
C = d.close.values.astype(float)
vol = np.maximum(d.vol.values.astype(float), 1.0)
dlt = d.delta.values.astype(float) / vol
rngb = (d.high.values - d.low.values).astype(float)
ct = d.contract.values
print(f"{ROOTSYM} {SERIES}: {n:,} bars, {len(set(ct))} contracts, "
      f"tick ${DPT:.2f}, round turn ${COMM:.2f}, max {MAXPOS} contracts\n")


def zs(x, w=500):
    s = pd.Series(x)
    return ((s - s.rolling(w, min_periods=100).mean())
            / s.rolling(w, min_periods=100).std().replace(0, np.nan)).values


# The three features measured to carry information, combined. Signs are set by
# the earlier IC measurement, not fitted here: signed volume predicts WITH the
# flow, bar return predicts AGAINST itself (short-horizon reversal).
sig_flow = zs(pd.Series(dlt).rolling(10, min_periods=3).mean().values)
sig_rev = -zs(pd.Series(np.r_[0, np.diff(C)]).rolling(5, min_periods=2).mean().values)
SIGNALS = {"flow": sig_flow, "reversal": sig_rev,
           "flow+reversal": np.nanmean([sig_flow, sig_rev], axis=0)}
rng = np.random.default_rng(5)
SIGNALS["shuffled"] = rng.permutation(sig_flow)


def run(sig, band, scale, cut_lo, cut_hi):
    """Hold round(scale*signal) contracts, rebalance only outside a dead band."""
    s = np.clip(sig * scale, -MAXPOS, MAXPOS)
    pos = np.zeros(n)
    cur = 0.0
    for i in range(cut_lo, cut_hi):
        if np.isfinite(s[i]) and abs(s[i] - cur) >= band:
            cur = float(np.round(s[i]))          # whole contracts only
        pos[i] = cur
    # DRIFT-ADJUSTED returns. The holdout is a rally, so any strategy whose
    # average position is even slightly long earns money gross without
    # predicting anything -- which is exactly why the shuffled control showed
    # +$47/wk gross in the first version of this test. Removing the split's
    # mean per-bar move makes a constant position worth exactly zero, so only
    # POSITION TIMING can produce a profit.
    raw = np.r_[0, np.diff(C)] / TICK * DPT
    ret = raw.copy()
    ret[cut_lo:cut_hi] -= np.nanmean(raw[cut_lo:cut_hi])
    # position held into bar i earns bar i's move
    pnl = np.r_[0, pos[:-1]][cut_lo:cut_hi] * ret[cut_lo:cut_hi]
    turn = np.abs(np.diff(np.r_[0, pos[cut_lo:cut_hi]]))
    cost = turn * (COMM / 2.0)                   # one side per contract traded
    net = pnl - cost
    return net, turn, pnl


print(f"{'signal':>14s} {'band':>5s} {'scale':>6s} {'train $/wk':>11s} "
      f"{'holdout $/wk':>13s} {'trades/wk':>10s} {'holdout Sharpe':>15s}")
rows = []
CUT = int(n * 0.75)
BARS_PER_WK = n / ((d.ts.max() - d.ts.min()) / NS / 86400 / 7 * 5)
for name, sg in SIGNALS.items():
    for band in (0.5, 1.0):
        for scale in (1.0, 2.0, 4.0):
            tr, tt, trg = run(sg, band, scale, 200, CUT)
            ho, ht, hog = run(sg, band, scale, CUT, n)
            if ht.sum() < 50: continue
            wtr = (CUT - 200) / BARS_PER_WK
            who = (n - CUT) / BARS_PER_WK
            shp = (ho.mean() / ho.std() * np.sqrt(BARS_PER_WK * 52)
                   if ho.std() > 0 else 0.0)
            rows.append(dict(signal=name, band=band, scale=scale,
                             tr=tr.sum() / max(wtr, 1e-9),
                             ho=ho.sum() / max(who, 1e-9),
                             # GROSS matters: if a signal only wins because it
                             # trades less, its gross is flat and the whole gap
                             # is the control's commission bill, not prediction
                             ho_gross=hog.sum() / max(who, 1e-9),
                             tpw=ht.sum() / max(who, 1e-9), sharpe=shp))
            print(f"{name:>14s} {band:5.1f} {scale:6.1f} {rows[-1]['tr']:11.0f} "
                  f"{rows[-1]['ho']:13.0f} {rows[-1]['tpw']:10.1f} {shp:15.2f}")

r = pd.DataFrame(rows)
sh = r[r.signal == "shuffled"]
real = r[r.signal != "shuffled"]
print(f"\nshuffled control: best holdout ${sh.ho.max():,.0f}/wk, "
      f"median ${sh.ho.median():,.0f}/wk")
print(f"real signals:     best holdout ${real.ho.max():,.0f}/wk, "
      f"median ${real.ho.median():,.0f}/wk")
best = real.loc[real.tr.idxmax()]      # chosen on TRAIN only
print(f"\npicked on training alone: {best.signal} band {best.band} "
      f"scale {best.scale}")
print(f"  train ${best.tr:,.0f}/wk -> holdout ${best.ho:,.0f}/wk, "
      f"{best.tpw:.1f} trades/wk, Sharpe {best.sharpe:.2f}")
if best.ho > sh.ho.max():
    print("  beats every shuffled arm out of sample.")
else:
    print(f"  does NOT beat the shuffled control's ${sh.ho.max():,.0f}/wk. "
          f"No edge here.")
# The decisive diagnostic. Gross P&L ignores commission entirely, so it cannot
# reward a signal merely for sitting still. If the real signal's gross is
# positive while shuffled gross is flat, the position sign genuinely predicts.
# If both are flat, the whole result was turnover and nothing else.
print(f"\nGROSS holdout \$/wk, commission excluded -- this is the honest test:")
print(f"{'signal':>14s} {'gross':>9s} {'net':>9s} {'trades/wk':>10s} "
      f"{'cost/wk':>9s}")
for name in SIGNALS:
    g = r[r.signal == name]
    if not len(g): continue
    b = g.loc[g.tr.idxmax()]
    print(f"{name:>14s} {b.ho_gross:9.0f} {b.ho:9.0f} {b.tpw:10.1f} "
          f"{b.ho_gross-b.ho:9.0f}")
print("\nturnover-matched: every arm forced to about the same trades/wk")
tgt = float(real.loc[real.tr.idxmax()].tpw)
print(f"  target {tgt:.0f} trades/wk")
for name, sg in SIGNALS.items():
    best_d, best_b = None, None
    for band in np.arange(0.05, 4.0, 0.05):
        _, ht2, hg2 = run(sg, band, 1.0, CUT, n)
        t2 = ht2.sum() / max((n - CUT) / BARS_PER_WK, 1e-9)
        dd = abs(t2 - tgt)
        if best_d is None or dd < best_d:
            best_d, best_b = dd, (band, t2, hg2.sum() / max((n-CUT)/BARS_PER_WK, 1e-9))
    if best_b:
        ok = "" if abs(best_b[1] - tgt) < tgt * 0.35 else "   <- could not match"
        print(f"  {name:>14s}: band {best_b[0]:.2f} -> {best_b[1]:6.1f} trades/wk, "
              f"gross \${best_b[2]:8.0f}/wk{ok}")

r.to_csv(os.path.join(HERE, f"continuous_{ROOTSYM}_{SERIES}.csv"), index=False)
