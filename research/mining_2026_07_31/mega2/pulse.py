"""The original pullback-after-impulse family, re-tried the honest way.

The 2025 ship (impulse 5pts/4bars, limit at 0.618, 6/12 bracket) printed
+21%/mo on bar-wick fills and -$711/day on tick replay. This tests the
FAMILY tick-true from the start, both ways round (the 80% stop-first rate
of continuation is itself a hypothesis: the fade of the same setup), with
fills that only count when the tape trades THROUGH the limit, a tick of
slippage on every stop, and targets that only count on strict penetration.

Grid is 64 cells (not millions). Per NQ quarter: train on first 60%,
held-out 40%; the cell is picked on train alone; the pick's held-out and
cross-quarter records are what gets believed.
"""
import os
import pickle
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402

PSYM = os.environ.get("PSYM", "NQ")
# PLACEBO: trade the identical machinery on 30-minute-stale signals. A real
# timing edge collapses to ~zero here; a plumbing leak stays profitable.
PLACEBO = int(os.environ.get("PLACEBO", "0")) and 30
PSCALE = float(os.environ.get("PSCALE", "1.0"))   # point scale vs NQ
OUT = os.path.join(fuse.ROOT, "research",
                   ("PULSE.md" if PSYM == "NQ" else f"PULSE_{PSYM}.md")
                   if not PLACEBO else f"PULSE_{PSYM}_PLACEBO.md")
TRAIN = 0.60
COMM = 1.24
TV = float(os.environ.get("PTV", "2.0"))   # $/pt of the micro
SLIP = 0.25       # one tick on stop exits
DELAY_NS = 250_000_000   # order placement latency: no fills inside it
COOL_NS = 60_000_000_000
GRID = [dict(imp=imp, w=w, retr=r, S=S, T=T, hold=10, d=d)
        for imp in (5.0, 8.0) for w in (4, 6) for r in (0.5, 0.618)
        for S in (6.0, 10.0) for T in (12.0, 20.0) for d in (1, -1)]
GRID = [dict(c, imp=c["imp"] * PSCALE, S=c["S"] * PSCALE,
             T=c["T"] * PSCALE) for c in GRID]
if os.environ.get("FINE"):
    # the deployment cell's neighborhood, continuation only, fine steps:
    # answers "does a nearer/farther stop, deeper/shallower pullback, or a
    # different patience win more" without touching the shipped parameters
    GRID = [dict(imp=imp * PSCALE, w=6, retr=r, S=S * PSCALE,
                 T=T * PSCALE, hold=h, d=1)
            for imp in (4.0, 5.0, 6.5, 8.0)
            for r in (0.382, 0.5, 0.618, 0.786)
            for S in (8.0, 10.0, 12.0, 14.0)
            for T in (16.0, 20.0, 24.0, 28.0)
            for h in (5, 10, 20)]
if os.environ.get("PTOP"):
    # placebo scope: only the deployment cell and its fade twin need the
    # stale-signal control; 64 cells of placebo is 5 hours of no new info
    GRID = [c for c in GRID
            if c["w"] == 6 and c["retr"] == 0.618
            and abs(c["S"] - 10.0 * PSCALE) < 1e-9
            and abs(c["T"] - 20.0 * PSCALE) < 1e-9
            and abs(c["imp"] - 5.0 * PSCALE) < 1e-9]


def quarter(cn):
    ts, px, _ = fuse.load_tape(fuse.tape_meta()[cn]["path"])
    idx = pd.to_datetime(ts)
    close = pd.Series(px, index=idx).resample("1min").last().ffill()
    bt = close.index.view(np.int64)
    bc = close.values
    # map each bar END to its tick position. Resample labels bars by START
    # time; using the label raw handed the strategy the bar's own close 60
    # seconds early -- a look-ahead that manufactured +$51k of held-out
    # profit before the audit caught it. The bar closes at label + 1 minute.
    bpos = np.searchsorted(ts, bt + 60_000_000_000, side="right")
    rth = (close.index.hour * 60 + close.index.minute >= 13 * 60 + 30) & \
          (close.index.hour < 20)
    return ts, px, bt, bc, bpos, rth


def run(ts, px, bt, bc, bpos, rth, cell, lo, hi):
    imp, w, r = cell["imp"], cell["w"], cell["retr"]
    S, T, hold, d = cell["S"], cell["T"], cell["hold"] * 60_000_000_000, \
        cell["d"]
    pnl, outs, ets, last_x = [], [], [], -10**18
    n = len(bc)
    for i in range(max(lo, w + 1), hi):
        if not rth[i] or bt[i] < last_x + COOL_NS:
            continue
        if i - PLACEBO - w < 0:
            continue
        move = bc[i - PLACEBO] - bc[i - PLACEBO - w]
        if abs(move) < imp:
            continue
        up = move > 0
        limit = bc[i - PLACEBO] - r * move  # retracement of the impulse
        # direction: d=+1 continuation (with the impulse), d=-1 fade
        side = (1 if up else -1) * d
        j0 = np.searchsorted(ts, bt[i] + 60_000_000_000 + DELAY_NS)
        j1 = np.searchsorted(ts, bt[i] + 60_000_000_000 + hold)
        seg = px[j0:j1]
        if not len(seg):
            continue
        # fill only when the tape trades THROUGH the limit
        if up:
            hitf = np.flatnonzero(seg < limit)
        else:
            hitf = np.flatnonzero(seg > limit)
        if not len(hitf):
            continue
        f = hitf[0]
        entry = limit
        rest = seg[f:]
        stop = entry - side * S
        tgt = entry + side * T
        if side > 0:
            si = np.flatnonzero(rest <= stop)
            ti = np.flatnonzero(rest > tgt)      # strict penetration
        else:
            si = np.flatnonzero(rest >= stop)
            ti = np.flatnonzero(rest < tgt)
        s_at = si[0] if len(si) else 10**9
        t_at = ti[0] if len(ti) else 10**9
        if t_at < s_at:
            gain, o = T * TV, "t"
        elif s_at < 10**9:
            # gap-aware: if the trigger tick is past the stop, that print --
            # not the stop price -- is the honest exit
            xp = rest[s_at]
            ex = min(xp, stop) if side > 0 else max(xp, stop)
            gain, o = (side * (ex - entry) - SLIP) * TV, "s"
        else:
            # timeout exits cross the spread: one tick charged
            gain, o = (side * (rest[-1] - entry) - SLIP) * TV, "o"
        pnl.append(gain - COMM)
        outs.append(o)
        ets.append(ts[j0 + f])
        last_x = bt[i] + 60_000_000_000 + hold
    return np.array(pnl), outs, np.array(ets, dtype=np.int64)


def main():
    meta = fuse.tape_meta()
    if PSYM == "NQ":
        cons = [c for c in fuse.NQ_CONTRACTS if c in meta]
    else:
        cons = sorted((c for c, v in meta.items() if v["sym"] == PSYM
                       and v["n"] > 3_000_000), key=lambda c: meta[c]["t0"])
    tag = f"{PSYM}_{'F' if os.environ.get('FINE') else 'B'}"           f"{'_P' if PLACEBO else ''}"
    ckp = os.path.join(fuse.ROOT, "data", f"pulse_ck_{tag}.pkl")
    per, done = {}, set()
    if os.path.exists(ckp):
        try:
            per, done = pickle.load(open(ckp, "rb"))
            print(f"  resume: {sorted(done)}", flush=True)
        except Exception:                                        # noqa: BLE001
            per, done = {}, set()
    for cn in cons:
        if cn in done:
            continue
        data = quarter(cn)
        n = len(data[3])
        cut = int(n * TRAIN)
        days = max((data[2][-1] - data[2][0]) / fuse.DAY_NS, 1)
        for cell in GRID:
            a, _, _ = run(*data, cell, 0, cut)
            b, ob, eb = run(*data, cell, cut, n)
            k = tuple(sorted(cell.items()))
            r = per.setdefault(k, dict(cell=cell, tra=0.0, trn=0, tea=0.0,
                                       ten=0, q=[]))
            r["tra"] += float(a.sum()); r["trn"] += len(a)
            r["tea"] += float(b.sum()); r["ten"] += len(b)
            r["q"].append((cn, float(b.sum()), len(b)))
            r.setdefault("outs", []).extend(ob)
            r.setdefault("pnls", []).append(b)
            r.setdefault("ets", []).append(eb)
        done.add(cn)
        pickle.dump((per, done), open(ckp + ".tmp", "wb"))
        os.replace(ckp + ".tmp", ckp)
        print(f"  {cn} done ({days:.0f}d)", flush=True)

    wk_all = sum((meta[c]["t1"] - meta[c]["t0"]) / fuse.DAY_NS
                 for c in cons) / 7 * (1 - TRAIN)
    L = ["# Pullback-after-impulse, tick-true, both directions", "",
         "The 2025 ship's family (impulse -> retracement limit -> bracket) "
         "with honest fills: entry only when the tape trades through the "
         "limit, one tick slippage on stops, strict penetration on targets, "
         f"${COMM}/side commission. 64 cells, 8 NQ quarters.", "",
         "| imp | w | retr | S | T | dir | train $ | **held-out $** | "
         "ho trades | ho tr/wk | green q |", "|" + "---|" * 11]
    rows = sorted(per.values(), key=lambda r: -r["tra"])
    for r in rows[:10]:
        c = r["cell"]
        g = sum(1 for _, p, _ in r["q"] if p > 0)
        L.append(f"| {c['imp']} | {c['w']} | {c['retr']} | {c['S']} | "
                 f"{c['T']} | {'cont' if c['d'] > 0 else 'FADE'} | "
                 f"{r['tra']:+,.0f} | **{r['tea']:+,.0f}** | {r['ten']} | "
                 f"{r['ten']/wk_all:.0f} | {g}/{len(r['q'])} |")
    best = rows[0]
    L += ["", f"Top-by-train cell held-out: **${best['tea']:+,.0f}** over "
          f"{best['ten']} trades ({best['ten']/wk_all:.0f}/wk). Per "
          "quarter:", ""]
    for cn, p, nn in best["q"]:
        L.append(f"- {cn}: ${p:+,.0f} on {nn}")
    o = pd.Series(best["outs"]).value_counts(normalize=True)
    ap = np.concatenate(best["pnls"])
    et = np.concatenate(best["ets"])
    daily = pd.Series(ap, index=pd.to_datetime(et)).resample("D").sum()
    daily = daily[daily != 0]
    eq = daily.cumsum()
    dd = float((eq - eq.cummax()).min())
    wins = ap > 0
    L += ["", "## Anatomy (held-out, top cell)", "",
          f"- outcomes: target {o.get('t', 0):.0%}, stop {o.get('s', 0):.0%},"
          f" timeout {o.get('o', 0):.0%}",
          f"- win rate {wins.mean():.1%}, avg win "
          f"${ap[wins].mean() if wins.any() else 0:+.2f}, avg loss "
          f"${ap[~wins].mean() if (~wins).any() else 0:+.2f}",
          f"- {len(daily)} trading days: {float((daily > 0).mean()):.0%} "
          f"green, best ${daily.max():+,.0f}, worst ${daily.min():+,.0f}",
          f"- **max drawdown ${abs(dd):,.0f}** "
          f"({abs(dd)/4100:.1%} of the $4,100 account)",
          "", "Random-walk baseline for a 10/20 bracket is 33.3% "
          "target-first; the bar above breakeven-with-costs is ~35.5%. "
          "The measured rate against those two numbers IS the edge.", ""]
    open(OUT, "w").write("\n".join(L) + "\n")
    print("wrote", OUT, flush=True)


if __name__ == "__main__":
    main()
