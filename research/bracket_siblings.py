"""Does the NQ breakout survive on the markets that move WITH NQ?

The wide-bracket search produced exactly what was asked for: NQ, long,
3x ATR stop, 1:2 reward, 45.5% wins against a measured 34.5% baseline,
+11.0 percentage points, 3.86 sigma, 2 trades a week. Two lookbacks --
24h and 48h -- agreed with each other, which is more than a single
lucky cell usually manages.

This is the test that decides it, and it needs no new data. ES, YM and
RTY move with NQ roughly 90% of the time. A real mechanism -- momentum
carrying through a breakout in the US index complex -- cannot be
present in the Nasdaq and absent in the S&P. If the edge is real it
shows up there too, weaker perhaps, but present. If it is a lucky draw
it does not.

That is a stronger test than any shuffle, because it does not ask what
random data would have done; it asks what the SAME mechanism should
have done somewhere else, and checks.

GC and CL are included as genuinely independent instruments -- not
siblings, so they cannot confirm the NQ result, but they can say
whether wide breakouts are a broad phenomenon or a single-market
curiosity.
"""
import sys, math, os
sys.path.insert(0, os.path.join(os.getcwd(), "research"))
import brackets_wide as bw

print(f"{'mkt':>5} {'signal':>12} {'trades':>7} {'win%':>7} {'base%':>7} "
      f"{'edge':>7} {'sigma':>7} {'$/wk':>8}")
for sym in ["NQ", "ES", "YM", "RTY", "GC", "CL"]:
    try:
        d = bw.load(sym)
    except Exception:
        continue
    pv = bw.SPEC[sym]
    weeks = (d.index[-1] - d.index[0]).days / 7.0
    o = bw.outcomes(d, 3.0, 2.0, 1)
    if o is None:
        continue
    sg = bw.signals(d, o["ent"])
    dcd = o["win"] | o["loss"]
    base = float(o["win"][dcd].sum() / max(dcd.sum(), 1))
    for sname in ("breakout288", "breakout576"):
        dec = sg[sname] & dcd
        nd = int(dec.sum())
        if nd < 50:
            continue
        w = int(o["win"][dec].sum()); wr = w / nd
        gross = (w * o["targ_d"][dec].mean()
                 - (nd - w) * o["stop_d"][dec].mean()) * pv
        net = gross - nd * 1.99
        se = math.sqrt(max(base * (1 - base), 1e-9) / nd)
        print(f"{sym:>5} {sname:>12} {nd:>7,} {100*wr:>7.2f} {100*base:>7.2f} "
              f"{100*(wr-base):>7.2f} {(wr-base)/se:>7.2f} {net/weeks:>8,.0f}")
