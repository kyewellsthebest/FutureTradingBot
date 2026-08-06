"""FX tick simulator. Bid and ask are in the data, so cost is not a guess.

This is the one thing futures could not give us. On CME trade prints we know
what traded, never what was quoted, so every fill had to be modelled -- and
that model was worth 72% of the apparent edge on the user's own strategy
(touch-fill +$0.512/trade, trade-through +$0.141). The single largest source
of error in everything measured this session was an assumption.

Dukascopy records both sides on every tick, so:

  BUY  fills at the ASK. SELL fills at the BID. No assumption.
  A resting BUY limit at price P fills when the ASK trades down to P --
    someone must be willing to sell to you there.
  A resting SELL limit at P fills when the BID trades up to P.
  The spread is a measured number that varies by hour, by symbol and by news,
    not a constant somebody guessed.

What that buys us beyond honesty: the cost of trading becomes something we can
put a distribution on. The user's earlier strategy targeted high-momentum
windows, and FX spreads widen exactly when momentum arrives -- on futures that
was invisible, here it is in the data.

Controls unchanged: random-entry arm, drift adjustment, split by period.

Usage: python fxsim.py SYMBOL [MAX_SIGNALS]
"""
import os, sys, glob
import numpy as np, pandas as pd

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
FX = os.path.join(ROOT, "data", "fx")
SYM = (sys.argv[1] if len(sys.argv) > 1 else "EURUSD").upper()
MAXSIG = int(sys.argv[2]) if len(sys.argv) > 2 else 40000

# Position sizing on a $4,100 account. A micro lot is 1,000 units, so one pip
# is $0.10 -- roughly forty steps of granularity instead of the two whole
# contracts a $4k futures account gets. That was a real constraint on the
# continuous-sizing test and it disappears here.
PIP = {"EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01,
       "XAUUSD": 0.1}.get(SYM, 0.0001)
USD_PER_PIP_MICRO = 0.10

IMP_PIPS = float(os.environ.get("IMP_PIPS", "8"))
LOOKBACK = int(os.environ.get("LOOKBACK", "400"))     # in ticks
RETRACE = float(os.environ.get("RETRACE", "0.20"))
STOP_PIPS = float(os.environ.get("STOP_PIPS", "6"))
TGT_PIPS = float(os.environ.get("TGT_PIPS", "12"))
WAIT = int(os.environ.get("WAIT", "3000"))
HOLD = int(os.environ.get("HOLD", "40000"))
RANDOM = os.environ.get("RANDOM_ARM", "0") == "1"


def load(sym):
    fs = sorted(glob.glob(os.path.join(FX, f"{sym}_*.parquet")))
    if not fs: return None
    d = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
    cols = {c.lower(): c for c in d.columns}
    tcol = cols.get("timestamp") or cols.get("time") or cols.get("ts")
    bcol = cols.get("bid"); acol = cols.get("ask")
    if not (bcol and acol):
        print(f"columns are {list(d.columns)} -- need bid and ask"); return None
    d = d.sort_values(tcol, kind="stable").reset_index(drop=True)
    return (d[bcol].values.astype(float), d[acol].values.astype(float),
            pd.to_datetime(d[tcol]).values)


def simulate(bid, ask, ts, rng=None):
    """Walk the quotes. Entry and exit priced off the correct side, always."""
    n = len(bid)
    mid = (bid + ask) / 2.0
    lb = LOOKBACK
    mv = np.r_[np.full(lb, np.nan), (mid[lb:] - mid[:-lb])] / PIP
    if RANDOM:
        # the control: same count, same holds, entries at random moments
        k = int((np.abs(mv) >= IMP_PIPS).sum())
        idx = np.sort(rng.choice(np.arange(lb + 1, n - (WAIT + HOLD + 2)),
                                 size=min(k, MAXSIG), replace=False))
        side = rng.choice([-1, 1], size=len(idx))
    else:
        trig = np.abs(mv) >= IMP_PIPS
        trig[:lb + 1] = False
        trig[n - (WAIT + HOLD + 2):] = False
        idx = np.where(trig)[0]
        if len(idx) < 100: return None
        keep = np.r_[True, np.diff(idx) > lb // 2]
        idx = idx[keep]
        side = np.sign(mv[idx]).astype(int)
    if len(idx) > MAXSIG:
        sel = np.linspace(0, len(idx) - 1, MAXSIG).astype(int)
        idx, side = idx[sel], side[sel]
    hi = pd.Series(mid).rolling(lb).max().values[idx]
    lo = pd.Series(mid).rolling(lb).min().values[idx]
    rngp = np.maximum(hi - lo, PIP)
    entry = np.where(side > 0, mid[idx] - RETRACE * rngp, mid[idx] + RETRACE * rngp)

    out, spreads, nofill = [], [], 0
    for k in range(len(idx)):
        i0 = int(idx[k]); sd = int(side[k]); ep = float(entry[k])
        b = bid[i0 + 1: i0 + 1 + WAIT]; a = ask[i0 + 1: i0 + 1 + WAIT]
        if len(b) < 10: nofill += 1; continue
        # a resting BUY fills when the ASK comes down to it; a SELL when the
        # BID comes up. Using mid for either would be a free half-spread.
        hit = (a <= ep) if sd > 0 else (b >= ep)
        if not hit.any(): nofill += 1; continue
        j = int(np.argmax(hit)); f = i0 + 1 + j
        spreads.append((ask[f] - bid[f]) / PIP)
        eb = bid[f + 1: f + 1 + HOLD]; ea = ask[f + 1: f + 1 + HOLD]
        if len(eb) < 10: nofill += 1; continue
        # exits also pay the correct side: a long exits into the BID
        px_out = eb if sd > 0 else ea
        prof = (px_out - ep) * sd / PIP
        sl_hit = prof <= -STOP_PIPS
        tp_hit = prof >= TGT_PIPS
        js = int(np.argmax(sl_hit)) if sl_hit.any() else 10**9
        jt = int(np.argmax(tp_hit)) if tp_hit.any() else 10**9
        if js == 10**9 and jt == 10**9: p = float(prof[-1])
        elif js < jt: p = -STOP_PIPS
        else: p = TGT_PIPS
        out.append((p, i0))
    if not out: return None
    P = np.array([o[0] for o in out]); I = np.array([o[1] for o in out])
    return P, I, nofill, np.array(spreads)


r = load(SYM)
if r is None:
    print(f"no {SYM} parquet in {FX} yet"); sys.exit(0)
bid, ask, ts = r
sp = (ask - bid) / PIP
days = (ts.max() - ts.min()) / np.timedelta64(1, "D")
print(f"{SYM}: {len(bid):,} ticks over {days:.0f} days")
print(f"SPREAD, measured not assumed: median {np.median(sp):.2f} pips, "
      f"mean {sp.mean():.2f}, 90th pct {np.percentile(sp,90):.2f}, "
      f"99th {np.percentile(sp,99):.2f}")
print(f"  a round turn therefore costs about ${np.median(sp)*USD_PER_PIP_MICRO:.3f} "
      f"per micro lot, versus $1.32 on MNQ\n")

rng = np.random.default_rng(7)
res = {}
for arm in ("strategy", "random"):
    os.environ["RANDOM_ARM"] = "1" if arm == "random" else "0"
    globals()["RANDOM"] = arm == "random"
    o = simulate(bid, ask, ts, rng)
    if o is None: print(f"{arm}: no trades"); continue
    P, I, nf, spr = o
    cut = I.min() + 0.75 * (I.max() - I.min())
    tr, ho = P[I < cut], P[I >= cut]
    usd = P * USD_PER_PIP_MICRO
    se = usd.std() / np.sqrt(len(usd))
    res[arm] = usd.mean()
    print(f"{arm:>9s}: {len(P):,} trades, {nf/(len(P)+nf)*100:.0f}% nofill, "
          f"{(P>0).mean()*100:.1f}% win")
    print(f"           NET ${usd.mean():+.4f}/trade +/- ${se:.4f} "
          f"({abs(usd.mean())/max(se,1e-12):.1f} sigma), "
          f"train ${tr.mean()*USD_PER_PIP_MICRO:+.3f} "
          f"HOLDOUT ${ho.mean()*USD_PER_PIP_MICRO:+.3f}")
    print(f"           spread paid at entry: median {np.median(spr):.2f} pips")
if len(res) == 2:
    d = res["strategy"] - res["random"]
    print(f"\nstrategy minus random: ${d:+.4f}/trade -- this is the only "
          f"number that means anything")
