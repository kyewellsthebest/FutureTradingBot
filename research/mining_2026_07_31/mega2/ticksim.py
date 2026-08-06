"""Tick-native order simulator. No bars anywhere.

Every test in this project so far -- including the ones labelled "tick" --
built bars first and then resolved fills and exits against bar highs and lows.
That is a guess at the one quantity that decides the whole answer: on this
strategy, touch-fill says +$0.512 a trade and trade-through says +$0.141. A
72% swing sitting on an assumption.

The tape does not need to be asked politely. It records every print with its
size, so a resting order can be simulated directly:

  QUEUE. Rest a limit at price P. You are behind whatever was already there.
  You do not know that size without book data, but you DO know how much volume
  subsequently prints AT P. Fill only once QUEUE contracts have traded at your
  price -- that is your position in the line, expressed in the only unit the
  tape gives you. QUEUE=0 is the old touch-fill fantasy. Price trading a full
  tick past you fills you regardless, because the level cleared.

  EXIT. Once filled, walk the ticks. Whichever of stop or target the tape
  reaches first is the exit. No same-bar ambiguity, no convention, no
  assumption -- the actual sequence of prints.

Sweeping QUEUE from 0 upward turns the fill assumption from a guess into a
measured curve, and shows exactly how much queue position the edge can afford
before it dies.

Usage: python ticksim.py [CONTRACTS] [MAX_SIGNALS_PER_CONTRACT]
"""
import os, sys, glob, time
import numpy as np, pandas as pd

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
RAW = os.path.join(ROOT, "data", "tick", "raw")
NCON = int(sys.argv[1]) if len(sys.argv) > 1 else 8
MAXSIG = int(sys.argv[2]) if len(sys.argv) > 2 else 25000
NS = 1_000_000_000
TICKSZ = 0.25
PT = 2.0                      # MNQ dollars per point

# the strategy, in its own terms -- no bars, everything in ticks and points
IMP_PTS = float(os.environ.get("IMP_PTS", "8"))
IMP_TICKS = int(os.environ.get("IMP_TICKS", "400"))   # lookback, in trades
RETRACE = float(os.environ.get("RETRACE", "0.20"))
STOP_PTS = float(os.environ.get("STOP_PTS", "6"))
TGT_PTS = float(os.environ.get("TGT_PTS", "12"))
WAIT_TICKS = int(os.environ.get("WAIT_TICKS", "3000"))
HOLD_TICKS = int(os.environ.get("HOLD_TICKS", "40000"))
QUEUES = [float(x) for x in os.environ.get("QUEUES", "0,1,3,10,25,50").split(",")]
# TRAILING STOP -- the one exit rule never tested here. Sixteen families all
# used a fixed stop and a fixed target, which caps every winner at 2R. A trail
# keeps the loss capped but lets a winner run, and on a strategy sitting at
# 34.8% wins against a 33.3% break-even that shape change could matter.
#   TRAIL_PTS  0 = off (fixed target). Otherwise trail this far behind the
#              best price reached, after TRAIL_TRIG points of profit.
TRAIL_PTS = float(os.environ.get("TRAIL_PTS", "0"))
TRAIL_TRIG = float(os.environ.get("TRAIL_TRIG", "3"))


def simulate(px, sz, queue):
    """Walk the tape. Returns per-trade points, and how many never filled."""
    n = len(px)
    lb = IMP_TICKS
    # impulse measured over the last lb PRINTS, not the last lb seconds
    mv = np.r_[np.full(lb, np.nan), px[lb:] - px[:-lb]]
    trig = np.abs(mv) >= IMP_PTS
    trig[:lb + 1] = False
    trig[n - (WAIT_TICKS + HOLD_TICKS + 2):] = False
    idx = np.where(trig)[0]
    if len(idx) < 100: return None
    # thin the signals so one impulse does not become ten thousand of them
    keep = np.r_[True, np.diff(idx) > lb // 2]
    idx = idx[keep]
    if len(idx) > MAXSIG:
        idx = idx[np.linspace(0, len(idx) - 1, MAXSIG).astype(int)]
    side = np.sign(mv[idx]).astype(int)
    # impulse range over the lookback window, retrace measured off it
    hi = pd.Series(px).rolling(lb).max().values[idx]
    lo = pd.Series(px).rolling(lb).min().values[idx]
    rng = np.maximum(hi - lo, TICKSZ)
    entry = np.where(side > 0, px[idx] - RETRACE * rng, px[idx] + RETRACE * rng)
    entry = np.round(entry / TICKSZ) * TICKSZ          # limits rest on ticks

    pts = np.full(len(idx), np.nan)
    nofill = 0
    for k in range(len(idx)):
        i0 = idx[k]; sd = side[k]; ep = entry[k]
        w = px[i0 + 1: i0 + 1 + WAIT_TICKS]
        s = sz[i0 + 1: i0 + 1 + WAIT_TICKS]
        if len(w) < 10:
            nofill += 1; continue
        # AT my price, or THROUGH it
        at = w == ep
        through = (w < ep) if sd > 0 else (w > ep)
        if not through.any() and not at.any():
            nofill += 1; continue
        # cumulative size that printed at my price -- the queue draining
        cum_at = np.cumsum(np.where(at, s, 0.0))
        filled_by_queue = at & (cum_at >= queue) if queue > 0 else at
        cand = filled_by_queue | through
        if not cand.any():
            nofill += 1; continue
        fpos = i0 + 1 + int(np.argmax(cand))
        # EXIT: walk the tape from the fill, first touch wins, exactly
        e = px[fpos + 1: fpos + 1 + HOLD_TICKS]
        if len(e) < 10:
            nofill += 1; continue
        sl = ep - sd * STOP_PTS
        tp = ep + sd * TGT_PTS
        if TRAIL_PTS <= 0:
            hs = (e <= sl) if sd > 0 else (e >= sl)
            ht = (e >= tp) if sd > 0 else (e <= tp)
            js = int(np.argmax(hs)) if hs.any() else 10**9
            jt = int(np.argmax(ht)) if ht.any() else 10**9
            if js == 10**9 and jt == 10**9:
                pts[k] = (e[-1] - ep) * sd      # time exit at the window end
            elif js < jt:
                pts[k] = -STOP_PTS
            else:
                pts[k] = TGT_PTS
        else:
            # running best price in the trade's favour, tick by tick
            prof = (e - ep) * sd
            best = np.maximum.accumulate(prof)
            # the stop is the fixed one until TRAIL_TRIG of profit is reached,
            # then it follows the best price at TRAIL_PTS behind
            live = np.where(best >= TRAIL_TRIG, best - TRAIL_PTS, -STOP_PTS)
            hit = prof <= live
            j = int(np.argmax(hit)) if hit.any() else 10**9
            pts[k] = float(live[j]) if j < 10**9 else float(prof[-1])
    good = np.isfinite(pts)
    return pts[good], int(nofill), idx[good]


files = sorted(glob.glob(os.path.join(RAW, "NQ*.parquet")))[:NCON]
print(f"tick-native simulation, {len(files)} NQ contracts")
print(f"impulse {IMP_PTS}pt over {IMP_TICKS} prints, {RETRACE:.0%} retrace, "
      f"stop {STOP_PTS}pt, target {TGT_PTS}pt\n")

TAPE = {}
for f in files:
    c = os.path.basename(f).replace(".parquet", "")
    d = pd.read_parquet(f).sort_values("ts", kind="stable")
    TAPE[c] = (d.price.values.astype(float), d["size"].values.astype(float),
               d.ts.values.astype(np.int64))
    print(f"  {c}: {len(d):,} prints", flush=True)

print(f"\n{'queue':>6s} {'trades':>9s} {'nofill%':>8s} {'win%':>7s} "
      f"{'pts/trade':>10s} {'GROSS $':>9s} {'+/-':>7s} {'sigma':>7s} "
      f"{'net@0.42':>9s} {'train':>8s} {'HOLD':>8s}")
for q in QUEUES:
    allp, allnf, alltot, splits = [], 0, 0, []
    for c, (px, sz, ts) in TAPE.items():
        t0 = time.time()
        r = simulate(px, sz, q)
        if r is None: continue
        p, nf, ii = r
        allp.append(p); allnf += nf; alltot += len(p) + nf
        cut = ii.min() + 0.75 * (ii.max() - ii.min())
        splits.append((p[ii < cut], p[ii >= cut]))
    if not allp: continue
    P = np.concatenate(allp)
    g = P * PT
    se = g.std() / np.sqrt(len(g))
    tr = np.concatenate([a for a, b in splits if len(a)])
    ho = np.concatenate([b for a, b in splits if len(b)])
    print(f"{q:6.0f} {len(g):9,} {allnf/max(alltot,1)*100:7.1f}% "
          f"{(P > 0).mean()*100:6.1f}% {P.mean():10.4f} {g.mean():9.4f} "
          f"{se:7.4f} {abs(g.mean())/max(se,1e-9):7.1f} {g.mean()-0.42:9.4f} "
          f"{tr.mean()*PT:8.3f} {ho.mean()*PT:8.3f}", flush=True)

print("\nqueue 0 is the touch-fill fantasy every backtest here has used.")
print("the real question is how deep in the queue the edge survives, and the")
print("column that matters is HOLD -- out of sample, after paying $0.42.")
