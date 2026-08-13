"""Four data types on one clock. The synchroniser and the feature bank.

THE USER'S ARGUMENT, which is correct and which nothing here changes:

  Roughly two billion people look at price. Finding an edge in the one input
  that every single participant already stares at is the hardest possible
  version of the problem. The bot's advantages are that it never sleeps, never
  breaks a rule, never revenge-trades -- and that it can watch several
  unrelated data streams AT TICK RESOLUTION SIMULTANEOUSLY, which a human
  physically cannot. That last one is the only advantage that is about
  INFORMATION rather than discipline, and it is the one never used.

  Everything searched so far -- 26 billion configurations -- read exactly one
  stream: the NQ price path. The measured ceiling of that stream is zero. That
  result does not generalise to streams that were never loaded.

Same search model, same metal-detector filtering, same controls. More data.

FOUR TYPES, all of which are already on this disk:

  1. p_  NQ price path       what every previous search used
  2. f_  NQ order flow       the SAME file, read for size and aggressor instead
                             of price. Who is hitting what, in what size. Not
                             a transform of the price path.
  3. i_  index complex       ES, YM, RTY tapes on NQ's clock. Lead-lag,
                             divergence, breadth. Nobody hand-watches four
                             order-by-order tapes at once.
  4. m_  macro complex       CL, GC, HG on the same clock. Risk-on / risk-off.

  5. b_  order book          RESERVED, loader stubbed below -- the user says
                             they can obtain this.
  6. o_  options             RESERVED, same.

WHAT KEEPS IT HONEST -- three rails, the third specific to fusion:

  HARD LAG ON FOREIGN STREAMS. Every non-NQ stream is read as of
  (bar close - LAG_MS), never at or after it. Without this the study measures
  contemporaneous correlation and calls it prediction: ES and NQ print the same
  move in the same microsecond, and a zero-lag as-of join hands the model NQ's
  own present through ES's window. 250 ms default is still ten times faster
  than this bot's measured ~2 s entry latency.

  SHUFFLED TARGET. Same model, same folds, scrambled outcomes. A boosted tree
  with hundreds of inputs WILL fit noise; this measures how much.

  STREAM SHIFT -- the control only a fusion study can run. Slide a foreign tape
  along the calendar by a multi-day offset and re-join it. Its volatility, flow
  distribution and autocorrelation are untouched; only its alignment with NQ is
  destroyed. If "ES leads NQ" is real, the shift kills it. If the score
  survives the shift, the foreign stream was never doing the work and something
  is leaking. No amount of code review substitutes for this test.
"""
import glob
import json
import os
import re

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
RAW = os.path.join(ROOT, "data", "tick", "raw")
MULTI = os.path.join(ROOT, "data", "tick", "multi")
CACHE = os.path.join(ROOT, "data", "tick", "cache")
META = os.path.join(CACHE, "tape_meta.json")

NQ_CONTRACTS = ["NQU4", "NQZ4", "NQH5", "NQM5", "NQU5", "NQZ5", "NQH6", "NQM6"]
INDEX = ["ES", "YM", "RTY"]          # data type 3
MACRO = ["CL", "GC", "HG"]           # data type 4
FOREIGN = INDEX + MACRO
GROUP = {s: ("i_" if s in INDEX else "m_") for s in FOREIGN}
GROUP["NQ"] = "i_"                   # NQ as a satellite of another centre

# minimum tape density for a contract to count as the liquid one. GCH5 holds
# 22,805 prints against GC's 8.6 million and a name-based pick grabbed it once
# before, inventing a market that traded "161 ticks a day".
MIN_PRINTS_PER_DAY = 5_000

PT = 4                                # NQ ticks per point
TICKSZ = {"NQ": 0.25, "ES": 0.25, "YM": 1.0, "RTY": 0.10,
          "CL": 0.01, "GC": 0.10, "HG": 0.0005}
WINS = (1, 5, 21, 89)                 # bars of NQ tick-event time
# Foreign windows are WALL-CLOCK SECONDS, never bar counts, and the reason is
# the single most expensive bug this repo has caught.
#
# The first version measured a foreign stream over "the last 21 NQ bars". An NQ
# bar is 500 PRINTS, so the wall-clock length of that window is set by how long
# NQ took to trade -- which is pure NQ activity, one of the strongest features
# on the board. Every difference-of-cumulatives inherited it: foreign volume,
# print count, trade size, path length, and even |return|, whose variance grows
# with elapsed time. So the "cross-market" features were largely NQ's own clock
# wearing an ES costume.
#
# The stream-shift control caught it and could not have been talked out of it:
# sliding ES 11.5 days along the calendar left the score intact, and in three
# cases the SHIFTED tape scored HIGHER than the real one. A foreign tape that
# predicts better when it is deliberately misaligned is not carrying foreign
# information at all.
#
# A fixed wall-clock window makes "ES volume in the last 60 seconds" a fact
# about ES and nothing else.
WSEC = (5, 30, 120, 600)
VOLW = 200                            # grid points used to scale everything
LAG_MS = int(os.environ.get("LAG_MS", "250"))
# A WHOLE number of days, deliberately. A half-day offset would also throw the
# time-of-day alignment away, so a foreign stream could fail the control just
# for being busy at the open. Shifting by whole days keeps the diurnal shape
# intact and destroys only the event alignment -- so anything that survives is
# time-of-day seasonality, which NQ's own clock already provides for free and
# which is not cross-market information by any definition.
SHIFT_DAYS = float(os.environ.get("SHIFT_DAYS", "11"))
DAY_NS = 86_400_000_000_000


# ---------------------------------------------------------------- tape index
def tape_meta():
    if os.path.exists(META):
        return json.load(open(META))
    m = {}
    for f in sorted(glob.glob(os.path.join(MULTI, "*.parquet"))) + \
            sorted(glob.glob(os.path.join(RAW, "*.parquet"))):
        b = os.path.basename(f)[:-8]
        t = pq.read_table(f, columns=["ts"]).column("ts").to_numpy()
        # the month code is an uppercase letter too, so a plain [A-Z]+ grabs it
        # and turns NQZ5 into the symbol "NQZ". Anchor and strip code+year.
        mm = re.match(r"^([A-Z]+?)[FGHJKMNQUVXZ]\d+$", b)
        if mm is None:
            continue
        m[b] = dict(n=int(len(t)), t0=int(t.min()), t1=int(t.max()), path=f,
                    sym=mm.group(1))
    os.makedirs(os.path.dirname(META), exist_ok=True)
    json.dump(m, open(META, "w"))
    return m


def pick_contract(meta, sym, t0, t1):
    """Contract of `sym` with the largest calendar overlap of [t0, t1], among
    those dense enough to be the real front month."""
    best, bs = None, 0.0
    for k, v in meta.items():
        if v["sym"] != sym:
            continue
        days = max((v["t1"] - v["t0"]) / DAY_NS, 1.0)
        if v["n"] / days < MIN_PRINTS_PER_DAY:
            continue
        ov = min(t1, v["t1"]) - max(t0, v["t0"])
        if ov <= 0:
            continue
        if ov > bs:
            best, bs = k, ov
    return best


def load_tape(path):
    t = pq.read_table(path, columns=["ts", "price", "size"])
    ts = t.column("ts").to_numpy(zero_copy_only=False).astype(np.int64)
    px = t.column("price").to_numpy(zero_copy_only=False).astype(np.float64)
    sz = t.column("size").to_numpy(zero_copy_only=False).astype(np.float64)
    del t
    o = np.argsort(ts, kind="stable")
    return ts[o], px[o], sz[o]


# ------------------------------------------------------------ tape -> prefix
def cumulants(ts, px, sz):
    """Everything any window could need, as prefix sums over the raw tape. A
    window feature then costs two lookups, so a stream is one pass no matter
    how many windows are asked for.

    AGGRESSOR is the Lee-Ready tick test: uptick is a buy, downtick a sell,
    zero-tick inherits the last non-zero sign. Standard on futures, right
    roughly 85% of the time. It is NOT a transform of the price path -- it
    multiplies direction by SIZE, and size is information price does not carry.
    """
    d = np.diff(px)
    s = np.sign(d).astype(np.int8)
    s = np.r_[np.int8(0), s]
    nzi = np.maximum.accumulate(np.where(s != 0, np.arange(len(s)), 0))
    s = s[nzi].astype(np.float64)
    return dict(
        ts=ts,
        px=px,
        cv=np.cumsum(sz),                       # volume
        csv=np.cumsum(s * sz),                  # signed volume = order flow
        cn=np.arange(1, len(ts) + 1, dtype=np.float64),
        cs2=np.cumsum(sz * sz),                 # -> volume-weighted trade size
        cap=np.cumsum(np.r_[0.0, np.abs(d)]),   # path length travelled
    )


KEYS = ("px", "cv", "csv", "cn", "cs2", "cap")


def sample(C, T):
    """State of a stream as of each query time. Strictly backward: the last
    print at or before T, never the next one."""
    j = np.searchsorted(C["ts"], T, side="right") - 1
    bad = j < 0
    j = np.maximum(j, 0)
    G = {}
    for k in KEYS:
        v = C[k][j].astype(np.float64).copy()
        v[bad] = np.nan
        G[k] = v
    return G


def shift_query(C, T, shift_ns):
    """Query times slid along the calendar and wrapped inside the stream's own
    range. Same stream, wrong times -- the fusion null."""
    a, b = int(C["ts"][0]), int(C["ts"][-1])
    span = max(b - a, 1)
    return a + ((T - a + int(shift_ns)) % span)


# ---------------------------------------------------------------- NQ bar grid
def nq_bars(ts, px, k):
    """Tick-event bars: every k price prints, never every k seconds. A bar of
    500 prints carries the same information at 3am as at the open; a bar of one
    minute does not."""
    m = (len(px) // k) * k
    q = px[:m].reshape(-1, k)
    t = ts[:m].reshape(-1, k)
    return dict(o=q[:, 0].copy(), c=q[:, -1].copy(),
                h=q.max(1), l=q.min(1),
                ts=t[:, -1].copy(), ts0=t[:, 0].copy())


# -------------------------------------------------------------------- helpers
def _roll(a, w, how):
    s = pd.Series(a, dtype="float64")
    r = s.rolling(w, min_periods=max(2, w // 2))
    return getattr(r, how)().to_numpy()


def _z(a, w=VOLW):
    """Rolling z-score. Applied to DIFFERENCES, never to price levels -- a
    rolling variance of numbers near 20,000 loses most of its significant
    digits to cancellation."""
    mu = _roll(a, w, "mean")
    sd = _roll(a, w, "std")
    return (np.asarray(a, dtype=np.float64) - mu) / np.maximum(sd, 1e-9)


def _lagdiff(a, w):
    a = np.asarray(a, dtype=np.float64)
    out = np.full(len(a), np.nan)
    out[w:] = a[w:] - a[:-w]
    return out


# ------------------------------------------------------------------- features
def stream_features(G, pre, tick):
    """The same six questions asked of every stream, at four horizons.

    Deliberately identical across streams, so the model can compare like with
    like and so a difference between two streams is a fact about the markets
    rather than about which features happened to get written for which.

      ret  where it went, in its own volatility units
      ofi  order flow imbalance: signed volume over total volume, in [-1, 1]
      sz   volume-weighted mean trade size -- big prints or small ones
      vol  how much traded
      int  print intensity -- how many separate decisions
      eff  how straight the path was: net move over distance travelled
    """
    px, cv, csv, cn, cs2, cap = (G[k] for k in KEYS)
    r1 = _lagdiff(px, 1) / tick
    scale = np.maximum(_roll(np.abs(r1), VOLW, "mean"), 1e-9)
    F = {}
    rets = {}
    for w in WINS:
        dv = _lagdiff(cv, w)
        ret = _lagdiff(px, w) / tick
        rz = ret / (scale * np.sqrt(w))
        F[f"{pre}ret{w}"] = rz
        rets[w] = rz
        F[f"{pre}ofi{w}"] = _lagdiff(csv, w) / np.maximum(dv, 1e-9)
        F[f"{pre}sz{w}"] = _z(_lagdiff(cs2, w) / np.maximum(dv, 1e-9))
        F[f"{pre}vol{w}"] = _z(dv)
        F[f"{pre}int{w}"] = _z(_lagdiff(cn, w))
        F[f"{pre}eff{w}"] = ret * tick / np.maximum(_lagdiff(cap, w), 1e-9)
    return F, rets


def wallclock_features(C, T, pre, tick, lag_ns=0, shift_off=0):
    """A stream measured over FIXED SECONDS, sampled at NQ's bar closes.

    NQ's clock decides only WHEN we look. It no longer decides HOW FAR BACK we
    look, which is what leaked before. Every window here is the same number of
    seconds at every sample, so a foreign stream's volume, intensity and
    movement are facts about that stream alone.

    `lag_ns` is the hard latency rail: the window ENDS at (sample - lag), never
    at the sample itself.
    """
    end = T - lag_ns
    if shift_off:
        end = shift_query(C, end, shift_off)
    F, rets = {}, {}
    A = sample(C, end)
    for ws in WSEC:
        Bp = sample(C, end - ws * 1_000_000_000)
        dv = A["cv"] - Bp["cv"]
        dn = A["cn"] - Bp["cn"]
        d2 = A["cs2"] - Bp["cs2"]
        dsv = A["csv"] - Bp["csv"]
        dap = A["cap"] - Bp["cap"]
        ret = (A["px"] - Bp["px"]) / tick
        scale = np.maximum(_roll(np.abs(ret), VOLW, "mean"), 1e-9)
        F[f"{pre}ret{ws}"] = ret / scale
        rets[ws] = ret / scale
        F[f"{pre}ofi{ws}"] = np.where(dv > 0, dsv / np.maximum(dv, 1e-9), np.nan)
        F[f"{pre}sz{ws}"] = _z(np.where(dv > 0, d2 / np.maximum(dv, 1e-9),
                                        np.nan))
        F[f"{pre}vol{ws}"] = _z(dv)
        F[f"{pre}int{ws}"] = _z(dn)
        F[f"{pre}eff{ws}"] = np.where(dap > 0, ret * tick /
                                      np.maximum(dap, 1e-9), np.nan)
    return F, rets


def price_path_features(B):
    """Data type 1. Same family ceiling.py used, so the baseline row of the
    ablation is directly comparable to the zero already measured."""
    c, h, l, o = B["c"], B["h"], B["l"], B["o"]
    F = {}
    dc = np.r_[np.nan, np.diff(c)]
    flip = np.r_[np.nan, (np.sign(dc[1:]) * np.sign(dc[:-1]) < 0).astype(float)]
    for w in (3, 8, 21, 55, 144):
        prev = np.r_[np.full(w, np.nan), c[:-w]]
        hh = _roll(h, w, "max")
        ll = _roll(l, w, "min")
        rng = np.maximum(hh - ll, 1e-9)
        F[f"p_mom{w}"] = _z(c - prev)
        F[f"p_rev{w}"] = -_z(c - _roll(c, w, "mean"))
        F[f"p_pos{w}"] = (c - ll) / rng * 2 - 1
        F[f"p_rng{w}"] = _z(rng)
        F[f"p_chop{w}"] = _roll(flip, w, "mean")
    F["p_shape"] = (c - l) / np.maximum(h - l, 1e-9) * 2 - 1
    F["p_body"] = (c - o) / np.maximum(h - l, 1e-9)
    F["p_gap"] = np.r_[np.nan, o[1:] - c[:-1]] / PT
    F["p_hour"] = ((B["ts"] // 3_600_000_000_000) % 24).astype(np.float64)
    F["p_dow"] = ((B["ts"] // DAY_NS) % 7).astype(np.float64)
    return F


def cross_features(nq_rets, fr, wins=None):
    """The part a single-stream search cannot express by construction.

    DIVERGENCE  foreign move minus NQ move, both in their own sigma units. The
                classic "ES already went, NQ has not yet" setup, stated so it
                can be falsified instead of eyeballed.
    BREADTH     how many of the index complex agree on direction. One index
                moving is noise; four moving together is a decision by somebody
                large enough to be in all four.
    DISPERSION  spread of the complex's moves -- are they trading as one asset
                or separately.
    RISK        gold minus oil: the macro complex's one interpretable axis.
    """
    F = {}
    # NQ's leg of every divergence is measured over the SAME wall-clock window
    # as the foreign leg. Differencing a 21-bar NQ move against a 60-second ES
    # move would reintroduce exactly the bar-duration channel the wall-clock
    # windows exist to remove.
    for w in (WSEC if wins is None else wins):
        nr = nq_rets[w]
        idx = []
        for s in INDEX:
            if s not in fr:
                continue
            v = fr[s][w]
            F[f"i_div{s}{w}"] = v - nr
            idx.append(v)
        if len(idx) >= 2:
            # nanmean/nanstd warn on all-NaN columns, which happen whenever a
            # quarter has no dense contract for a member. Done by hand so a
            # coverage gap stays a NaN instead of a screenful of warnings.
            M = np.vstack(idx)
            fin = np.isfinite(M)
            Z = np.where(fin, M, 0.0)
            live = fin.sum(0)
            n = np.maximum(live, 1)
            mean = np.where(live > 0, Z.sum(0) / n, np.nan)
            var = np.where(live > 1, (Z * Z).sum(0) / n - (Z.sum(0) / n) ** 2,
                           np.nan)
            F[f"i_breadth{w}"] = np.where(live > 0,
                                          np.sign(Z).sum(0) / n, np.nan)
            F[f"i_mean{w}"] = mean
            F[f"i_disp{w}"] = np.sqrt(np.maximum(var, 0.0))
            F[f"i_lead{w}"] = mean - nr
        for s in MACRO:
            if s in fr:
                F[f"m_div{s}{w}"] = fr[s][w] - nr
        if "GC" in fr and "CL" in fr:
            F[f"m_risk{w}"] = fr["GC"][w] - fr["CL"][w]
    return F


# --------------------------------------------------------------- book/options
def load_book(contract, T):
    """RESERVED -- data type 5, which the user says they can obtain.

    Expected: data/book/<contract>.parquet with ts (int64 ns), bid_px, ask_px,
    bid_sz, ask_sz, and optionally deeper levels as bid_px2.. / bid_sz2.. so
    depth imbalance and book slope can be built. Sampled on the same clock with
    the same LAG_MS rail; the ablation picks a b_ group up automatically.
    """
    p = os.path.join(ROOT, "data", "book", f"{contract}.parquet")
    return None if not os.path.exists(p) else _book_feats(p, T)


def load_options(root, T):
    """RESERVED -- data type 6. Expected: data/options/<root>_greeks.parquet
    with ts, strike, expiry, iv, delta, gamma, oi, so dealer gamma, put/call
    skew and the IV term structure land on the same clock."""
    p = os.path.join(ROOT, "data", "options", f"{root}_greeks.parquet")
    return None if not os.path.exists(p) else _opt_feats(p, T)


def _book_feats(p, T):
    raise NotImplementedError(f"{p} exists -- wire depth features here")


def _opt_feats(p, T):
    raise NotImplementedError(f"{p} exists -- wire greek features here")


# ------------------------------------------------------------------ assembly
def build(contract, k, lag_ms=None, shift=False, verbose=True):
    """One NQ contract, all available streams, one aligned feature matrix."""
    lag = (LAG_MS if lag_ms is None else lag_ms) * 1_000_000
    meta = tape_meta()
    ts, px, _sz = load_tape(meta[contract]["path"])
    B = nq_bars(ts, px, k)
    T = B["ts"]                      # foreign streams queried at bar close-lag
    F = price_path_features(B)

    Cn = cumulants(ts, px, _sz)
    # NQ's own tape needs no lag -- the bar has closed, its last print is known.
    # Bar-count flow features stay: they are NQ's clock applied to NQ, which is
    # a legitimate NQ fact, not a foreign stream in disguise.
    Gn = sample(Cn, T)
    fn, _ = stream_features(Gn, "f_", TICKSZ["NQ"])
    F.update(fn)
    # ...and a matched WALL-CLOCK set, which is what the divergences difference
    # against and what makes NQ comparable to the foreign streams.
    fw, nq_rets = wallclock_features(Cn, T, "wc", TICKSZ["NQ"])
    # split by INFORMATION TYPE rather than by source file. NQ's wall-clock
    # RETURN is price, and it has to land in the price group or the
    # "everything except price path" set would quietly contain NQ's returns and
    # stop meaning what its name says.
    for k, v in fw.items():
        F[("p_" if k.startswith(("wcret", "wceff")) else "f_") + k] = v
    del Cn, Gn, ts, px, _sz

    off = int(SHIFT_DAYS * DAY_NS) if shift else 0
    fr, cov = {}, {}
    # the centre market is whatever contract was asked for; its own symbol
    # must not appear among the "foreign" satellites (for ES-centred bars a
    # satellite ES stream would be the centre's own tape wearing an i_ prefix)
    # and NQ joins the index satellites whenever it is not the centre.
    csym = meta[contract]["sym"]
    foreign = [s for s in (["NQ"] if csym != "NQ" else []) + FOREIGN
               if s != csym]
    for s in foreign:
        c = pick_contract(meta, s, int(T[0]), int(T[-1]))
        if c is None:
            # emit the group's columns as all-NaN rather than dropping them.
            # Every contract must present an IDENTICAL feature set or the
            # matrices cannot be stacked, and a quarter where GC has no dense
            # contract is a coverage fact, not a different experiment.
            C = dict(ts=np.array([0, 1], dtype=np.int64),
                     **{k: np.full(2, np.nan) for k in KEYS})
            C["ts"] = np.array([0, 1], dtype=np.int64)
        else:
            fts, fpx, fsz = load_tape(meta[c]["path"])
            C = cumulants(fts, fpx, fsz)
            del fts, fpx, fsz
        ff, rr = wallclock_features(C, T, GROUP[s] + s.lower() + "_",
                                    TICKSZ[s], lag_ns=lag, shift_off=off)
        F.update(ff)
        fr[s] = rr
        cov[s] = 0.0 if c is None else float(
            np.isfinite(sample(C, T - lag)["px"]).mean())
        if verbose:
            print(f"    {contract} <- {str(c):7s} {cov[s]*100:5.1f}% covered",
                  flush=True)
        del C
    F.update(cross_features(nq_rets, fr))
    return B, F, cov
