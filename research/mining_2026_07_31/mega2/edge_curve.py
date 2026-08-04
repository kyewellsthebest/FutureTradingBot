"""THE FREQUENCY FRONTIER: how much edge is left at each trading speed?

The goal is 500 trades a week at $1,000 a week. Every search so far has
answered that by luck -- run a hunt, see what turns up, guess whether more
compute would find something faster. This measures it instead.

Method, and the whole point is the second half:

  1. Draw thousands of configs across every mechanism. Keep the ones that
     produce a tradeable book, with NO friction and NO account filters, so
     nothing is excluded for a reason unrelated to edge.
  2. Bucket them by trades per week.
  3. In each bucket, pick the best config BY TRAINING gross edge, then report
     that config's HOLDOUT gross edge.

Step 3 is the part that matters. The upper envelope of a few thousand random
configs is a noise ceiling -- take the best of 500 coin-flip sequences and it
looks like a gift. Selecting on train and reading off holdout prices that in.
The holdout number is what a config picked today would actually have earned.

Against that curve we draw the cost line. Where holdout gross falls below cost,
trading faster loses money no matter how good the search is. That crossing is
the real frequency ceiling, and it does not move with more compute.

Usage: python edge_curve.py MARKET [TF] [SECONDS]
"""
import os, sys, json, time, types
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from econ import ECON

MKT = sys.argv[1] if len(sys.argv) > 1 else "RTY"
TF = int(sys.argv[2]) if len(sys.argv) > 2 else 5
SECS = float(sys.argv[3]) if len(sys.argv) > 3 else 420.0

# Reuse the hunter's loader, mechanisms and signal code without running its
# search loop -- one engine, so a fix in one place is a fix in both.
src = open(os.path.join(HERE, "hunter.py")).read().split("\nboard = json.load(")[0]
H = types.ModuleType("hunter_defs"); H.__dict__["__file__"] = os.path.join(HERE, "hunter.py")
exec(compile(src, "hunter.py", "exec"), H.__dict__)

M = H.load(MKT, TF)
tick, dpt, comm = M["tick"], M["dpt"], M["comm"]
rng = np.random.default_rng(12345)


def book(p):
    """A config's raw trades, gross of everything. No filters, no friction."""
    C, ATR, n = M["C"], M["ATR"], M["n"]
    idx, side, ref = H.signal(M, p)
    if len(idx) < 100: return None
    lim = C[idx] - (p["pb"] * ref * tick) * side
    ttl = int(round(p["ttl"]))
    st = np.arange(1, ttl + 1); bars = idx[:, None] + st[None, :]
    adv = np.where(side[:, None] > 0, M["Lp"][bars], M["Hp"][bars])
    thr = (adv * side[:, None]) <= (lim * side)[:, None] - tick + 1e-9
    j = np.where(thr.any(1), thr.argmax(1), 10**9); ok = j < 10**9
    if ok.sum() < 100: return None
    fb = idx[ok] + 1 + j[ok]; sd = side[ok]; ep = lim[ok]; av = ATR[idx][ok]
    stk = np.maximum(p["sp"] * av, 2.0)
    risk = float(np.median(stk) * dpt)
    hold = int(round(p["hold"]))
    js = np.arange(0, hold + 1); wb = fb[:, None] + js[None, :]
    g = sd[:, None].astype(float)
    lo = np.where(g > 0, M["Lp"][wb], M["Hp"][wb]) * g
    hi = np.where(g > 0, M["Hp"][wb], M["Lp"][wb]) * g
    cw = M["Cp"][wb]; ar = np.arange(len(fb)); eps = ep * sd
    sl = eps - stk * tick; tp = eps + p["rr"] * stk * tick
    hs = lo <= sl[:, None]; ht = hi >= tp[:, None]; ht[:, 0] = False
    j1 = np.where(hs.any(1), hs.argmax(1), 10**9); j2 = np.where(ht.any(1), ht.argmax(1), 10**9)
    ks_ = j1 <= np.minimum(j2, hold); kt = (~ks_) & (j2 <= hold)
    xj = np.where(ks_, np.minimum(j1, hold), np.where(kt, np.minimum(j2, hold), hold))
    xp = np.where(ks_, sl * sd, np.where(kt, tp * sd, cw[ar, np.minimum(xj, hold)]))
    gd = np.isfinite(xp)
    if gd.sum() < 100: return None
    pl = (xp[gd] - ep[gd]) * sd[gd] * (1 / tick) * dpt      # gross, no commission
    F = fb[gd]; X = fb[gd] + xj[gd]; SD = sd[gd]
    o = np.argsort(F); pl, F, X, SD = pl[o], F[o], X[o], SD[o]
    mp = int(round(p["maxpos"]))
    free = np.zeros(mp, dtype=np.int64); took = np.zeros(len(pl), bool)
    for i in range(len(pl)):
        s_ = int(np.argmin(free))
        if free[s_] <= F[i]: took[i] = True; free[s_] = X[i]
    pl, F, X, SD = pl[took], F[took], X[took], SD[took]
    if len(pl) < 100: return None
    m = F < M["cut"]
    if m.sum() < 60 or (~m).sum() < 30: return None
    # Drift adjustment. A chronological holdout is a single directional regime
    # -- the last quarter here is a rally of ~116 ATRs on RTY -- so a net-long
    # book earns money without predicting anything, and "it worked out of
    # sample" quietly becomes "it was long during a bull market". Subtract what
    # a position of the same side and duration collects from the market's
    # average drift, computed separately in each split so the holdout's own
    # trend is what gets removed from holdout trades.
    dpb = np.empty(len(pl))
    for sel in (m, ~m):
        lo, hi = (0, M["cut"]) if sel is m else (M["cut"], n - 1)
        dpb[sel] = (C[hi] - C[lo]) / max(hi - lo, 1) / tick * dpt
    drift = dpb * (X - F) * SD
    return dict(mech=p["mech"], tpw=len(pl) / M["wks"], risk=risk,
                tr=float(pl[m].mean()), ho=float(pl[~m].mean()),
                # what is left once drift is paid for: the mechanism's own part
                tr_a=float((pl - drift)[m].mean()), ho_a=float((pl - drift)[~m].mean()),
                side=float(SD.mean()), bars=float((X - F).mean()),
                wr=float((pl > 0).mean()), n=len(pl), rr=p["rr"],
                # trades per week counted on the holdout stretch alone, since
                # that is the number the holdout edge has to be paid on
                tpw_ho=(~m).sum() / (M["wks"] * 0.25))


rows = []
t0 = time.time()
while time.time() - t0 < SECS:
    p = H.draw()
    p["maxpos"] = int(rng.integers(1, 5))
    r = book(p)
    if r is not None: rows.append(r)

d = pd.DataFrame(rows)
if d.empty:
    print(f"{MKT} tf{TF}: no tradeable books at all"); sys.exit(0)

fric_now = comm + 1.0 * dpt                 # today's rate + 1 tick on exits
fric_cut = comm * 0.51 + 0.4 * dpt          # lifetime plan + stop-limit exits

print(f"\n{MKT} tf{TF}: {len(d):,} tradeable books from "
      f"{len(d)/max(time.time()-t0,1)*SECS:,.0f} draws in {time.time()-t0:.0f}s")
print(f"cost per round turn: today ${fric_now:.2f}   "
      f"lifetime plan + stop-limit exits ${fric_cut:.2f}\n")

# Buckets are geometric because the interesting range spans two orders of
# magnitude and a linear grid would put almost everything in one bin.
EDG = [0, 5, 10, 20, 40, 80, 150, 300, 600, 1200, 1e9]
d["bk"] = pd.cut(d.tpw, EDG)
print(f"{'trades/wk':>12s} {'configs':>8s} {'best train $':>13s} "
      f"{'its holdout $':>14s} {'net today':>10s} {'net cheap':>10s} "
      f"{'$/wk today':>11s} {'$/wk cheap':>11s}  top mech")
best_rows = []
for b, g in d.groupby("bk", observed=True):
    if len(g) < 5: continue
    # select on train, report holdout -- averaged over the top few so the
    # answer is not one lucky config
    top = g.nlargest(max(3, len(g) // 20), "tr")
    ho = float(top.ho.mean()); tr = float(top.tr.mean())
    tpw = float(top.tpw.mean())
    net_now, net_cut = ho - fric_now, ho - fric_cut
    best_rows.append(dict(tpw=tpw, ho=ho, now=net_now * tpw, cut=net_cut * tpw))
    print(f"{str(b):>12s} {len(g):8,} {tr:13.2f} {ho:14.2f} "
          f"{net_now:10.2f} {net_cut:10.2f} {net_now*tpw:11.0f} {net_cut*tpw:11.0f}"
          f"  {top.mech.mode().iloc[0]}")

print("\nby mechanism (best-of-top-5% train, its holdout edge):")
print("  'rnd' is the control: random entries, no information at all. Its")
print("  holdout number is the bar the others must clear, not zero.")
print(f"{'mech':>6s} {'configs':>8s} {'med tpw':>8s} {'train $':>9s} "
      f"{'holdout $':>10s} {'ho>0':>6s} {'train-drift':>12s} {'hold-drift':>11s} "
      f"{'net long':>9s} {'bars held':>10s}")
for mech, g in d.groupby("mech"):
    top = g.nlargest(max(3, len(g) // 20), "tr")
    print(f"{mech:>6s} {len(g):8,} {g.tpw.median():8.1f} {top.tr.mean():9.2f} "
          f"{top.ho.mean():10.2f} {float((top.ho>0).mean()):6.0%} "
          f"{top.tr_a.mean():12.2f} {top.ho_a.mean():11.2f} "
          f"{top.side.mean():9.2f} {top.bars.mean():10.1f}")
if "rnd" in set(d.mech):
    r = d[d.mech == "rnd"]; rtop = r.nlargest(max(3, len(r) // 20), "tr")
    bar = rtop.ho.mean()
    print(f"\n  control earns ${bar:.2f}/trade in the holdout on random entries.")
    print("  after clearing that bar:")
    for mech, g in d.groupby("mech"):
        if mech == "rnd": continue
        top = g.nlargest(max(3, len(g) // 20), "tr")
        print(f"    {mech:>5s}: {top.ho.mean() - bar:+7.2f} $/trade vs the control, "
              f"{top.ho_a.mean():+7.2f} after drift adjustment")

# The honest summary: the best weekly dollars anywhere on the curve, and
# whether it is anywhere near the target.
if best_rows:
    bn = max(best_rows, key=lambda r: r["now"]); bc = max(best_rows, key=lambda r: r["cut"])
    print(f"\nbest weekly dollars from ONE config on this market:")
    print(f"  at today's cost:  ${bn['now']:,.0f}/wk at {bn['tpw']:.0f} trades/wk")
    print(f"  at reduced cost:  ${bc['cut']:,.0f}/wk at {bc['tpw']:.0f} trades/wk")
    print(f"  target is $1,000/wk at 500 trades/wk across at most 4 strategies")

d.to_csv(os.path.join(HERE, f"edge_curve_{MKT}_{TF}.csv"), index=False)
