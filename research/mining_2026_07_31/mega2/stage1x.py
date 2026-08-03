"""MEGA2 STAGE-1: vectorized HONEST screen. Every fill follows the session's
pessimistic standard: limit fills only on touch at the limit price (never
better), stop/market entries pay 1 tick slippage, same-bar entry+target is
DENIED, same-bar stop is ALLOWED, stop beats target on shared bars, time/EOD
exits pay 1 tick. Costs = real round-trip commission for the tradable
contract (micro where one exists).

Approximations vs stage-2 exact replay (documented, conservative where
possible): signals thinned to >=24-bar spacing instead of true in-position
lockout; no OCO between ORB sides. Stage-2 re-simulates survivors exactly.

Usage: stage1.py ROOT
Writes: s1b_{ROOT}.json.gz (top configs + funnel stats), s1bbase_{ROOT}.npz
(no-filter metrics for every base config, for parameter-cliff analysis).
"""
import json, sys, os, gzip, time, tempfile, itertools
import numpy as np, pandas as pd

REPO = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
sys.path.insert(0, REPO)
os.environ.setdefault("BOT_DATA_DIR", tempfile.mkdtemp())
os.environ.setdefault("POLYGON_API", "fake")
import bot.basket_engine as be
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from econ import ECON, TRAIN_END, OOS10, OOS3

ROOT = sys.argv[1]
DEPTH = int(os.environ.get("M2_DEPTH", "2"))
SHARD = os.environ.get("M2_SHARD", "")          # e.g. "0/3"
TF = os.environ.get("M2_TF", "5")               # 1,5 native; 15,30,60 resampled
SH_K, SH_N = (int(SHARD.split("/")[0]), int(SHARD.split("/")[1])) if SHARD else (0, 1)   # 2=wide sweep, 3=deep (promising markets)
D = os.path.dirname(os.path.abspath(__file__))
PV, TICK, COMM, TRADED_AS, MARGIN, AFFORD = ECON[ROOT]
# Grids below are expressed in 5-MINUTE-EQUIVALENT UNITS ("u"), never raw bars.
# sb() converts a unit count to actual bars for the series being searched, so
# H=48 means "4 hours" whether a bar is 13 seconds or 15 minutes. Without this
# every lookback, hold and TTL would silently mean something different on each
# of the 15 series and the results would not be comparable.
HMAX_U = 96        # 8h max hold
TTLMAX_U = 12      # 1h max limit time-in-force
WARM_DAYS = 10
# Weekly Sharpe grows as sqrt(trades), and with a fixed cost c per trade the
# gross edge that maximises it is exactly 2c -- about $2.84 on MNQ, or roughly
# 700 trades a week for $1,000. Two-hour spacing caps a stream near eleven
# signals a day and forces the search toward big, staggered trades instead.
# Half an hour allows the high-frequency end to exist; it does mean a few
# positions can overlap, which micros on this account can carry.
THIN_U = int(os.environ.get("M2_THIN", "6"))
BIG = 10 ** 6
# Net dollars per trade a config must clear to be worth a slot. $1,000/week on
# 200 trades needs $5.00/trade across the whole book, so components below about
# a third of that cannot pull their weight however often they fire.
# The optimum net edge IS roughly one round-turn cost (~$1.42 on MNQ), so a
# $1.50 floor sat right on top of the target and excluded the whole sweet spot
# from below. Sit well under it and let the portfolio choose.
EV_FLOOR = float(os.environ.get("M2_EVFLOOR", "0.60"))

t0 = time.time()

# ---------------------------------------------------------------- data prep
SERIES = "tf" + TF
df = pd.read_csv(f"{REPO}/data/polygon/{ROOT}_5min.csv")
df["ts"] = pd.to_datetime(df.ts, utc=True)
if TF != "5":
    df = (df.set_index("ts").resample(f"{TF}min", label="left", closed="left")
            .agg(open=("open","first"), high=("high","max"), low=("low","min"),
                 close=("close","last"), volume=("volume","sum"))
            .dropna(subset=["close"]).reset_index())
df = df.sort_values("ts").reset_index(drop=True)
# Bars per ACTIVE day, not per calendar day: dividing by the calendar span
# would count weekends and shrink every horizon by ~30% on every series.
_active_days = max(df.ts.dt.date.nunique(), 1)
BARS_PER_DAY = max(int(len(df) / _active_days), 12)
BAR_MIN = 1440.0 / BARS_PER_DAY
SC = BARS_PER_DAY / 288.0          # bars per 5-min-equivalent unit
def sb(u):
    """5-min-equivalent units -> actual bars of this series (>=1)."""
    return max(int(round(u * SC)), 1)
HMAX, TTLMAX, THIN = sb(HMAX_U), sb(TTLMAX_U), sb(THIN_U)
STEP = sb(1)                        # bars spanning ~5 minutes
print(f"{SERIES}: {len(df):,} bars, {BARS_PER_DAY}/day, {BAR_MIN:.2f}min/bar, "
      f"SC={SC:.3f}, HMAX={HMAX}, TTL={TTLMAX}, THIN={THIN}", flush=True)
_g = lambda c, d: (df[c].values.astype(np.float64) if c in df.columns
                   else np.full(len(df), d, dtype=np.float64))
BUYV, SELLV = _g("buyvol", 0), _g("sellvol", 0)
DELTA, CUMD = _g("delta", 0), _g("cumdelta", 0)
BIGR, NTR, DURS = _g("bigratio", 0), _g("ntrades", 1), _g("dur_s", 1)
LOWSZ, HIGHSZ = _g("lowsz", 0), _g("highsz", 0)
n = len(df)
ts = df.ts
O = df.open.values.astype(np.float64); H_ = df.high.values.astype(np.float64)
L_ = df.low.values.astype(np.float64); C_ = df.close.values.astype(np.float64)
V_ = df.volume.values.astype(np.float64)

# Volatility unit = typical 5-MINUTE displacement, averaged over ~70 minutes.
# A 14-bar true-range mean is not comparable across series (it measures 3
# minutes on tick_250 and 3.5 hours on time_15m), and summing true ranges over
# many tiny bars measures path length rather than displacement. Absolute
# close-to-close change over a fixed clock step is the same quantity on every
# series, so `sp * ATR` is the same dollar risk everywhere.
_disp = pd.Series(np.abs(C_ - pd.Series(C_).shift(STEP).values))
_aw = max(sb(14), 10)
ATR = _disp.rolling(_aw, min_periods=max(_aw // 2, 5)).mean().values

cdt = ts.dt.tz_convert(None)
nh = (cdt.dt.hour + (cdt.dt.minute + 0.75) / 60).values
mkt = np.array([be.market_open(d.to_pydatetime() + pd.Timedelta(seconds=45)) for d in cdt])
eod_x = (nh >= be.EOD_UTC) & (nh < be.REOPEN_UTC)
eod_b = ((nh >= be.EOD_UTC - 0.5) & (nh < be.REOPEN_UTC))
gap = (ts.diff() > pd.Timedelta("3h")) & (ts.shift(1).dt.weekday != 4)
contam = gap.rolling(sb(320), min_periods=1).max().fillna(0).values.astype(bool)

# next EOD-exit bar index for every bar
ne = np.full(n + 1, n, dtype=np.int64)
for i in range(n - 1, -1, -1):
    ne[i] = i if eod_x[i] else ne[i + 1]
ne = ne[:n]

# calendar indexing (weeks/days/years by EXIT time)
wk_str = ts.dt.strftime("%G-W%V")
wk_codes, wk_uniq = pd.factorize(wk_str)
W = len(wk_uniq)
day_codes, day_uniq = pd.factorize(ts.dt.date)
ND = len(day_uniq)
wk_first_ts = ts.groupby(wk_codes).first()
# SPLIT FROM THE DATA, NOT FROM A CALENDAR CONSTANT. econ.py's dates were set
# for the 5-minute files, which run to 30 July 2026. The tick tape ends when
# NQM6 rolls in mid-June, so those constants leave a 4-week holdout and an OOS3
# window containing no weeks at all -- every config scores exactly zero there
# and any filter on it is unsatisfiable. Taking the last 20% of weeks gives a
# holdout of real length whatever the tape happens to cover.
_HOLD_FRAC = 0.20
_split_i = int(round(W * (1.0 - _HOLD_FRAC)))
_split_ts = wk_first_ts.iloc[_split_i]
wk_train = (wk_first_ts < _split_ts).values
# OOS10 sits 4 days before TRAIN_END in econ.py, so one week counts as both
# train and out-of-sample. Harmless when OOS was a gate; not harmless now that
# it is the diagnostic everything rests on.
wk_o10 = (wk_first_ts >= _split_ts).values                       # full holdout
wk_o3 = (wk_first_ts >= wk_first_ts.iloc[int(round(W * 0.93))]).values  # final ~7%
print(f"split: {int(wk_train.sum())} train weeks, {int(wk_o10.sum())} holdout "
      f"({_split_ts.date()} onward), {int(wk_o3.sum())} final-stretch weeks", flush=True)
wk_year = wk_first_ts.dt.year.values
yr_counts = pd.Series(wk_year[wk_train]).value_counts()
years = sorted([y for y, c in yr_counts.items() if c >= 8])
# np.stack on an empty list raises; with a short tape no year clears 8 weeks.
# Fall back to a single all-train row so the every-year-positive check degrades
# to "positive overall" rather than crashing the shard.
Ymat = (np.stack([(wk_year == y) & wk_train for y in years]) if years
        else wk_train[None, :]).astype(np.float64)                       # (Y,W)

# filter cells: sess(4) x trendwith(2) x volhi(2) x vixhi(2) = 32
sess_cat = np.full(n, 3, dtype=np.int64)          # other
sess_cat[(nh >= 0.0) & (nh < 7.0)] = 0            # asia
sess_cat[(nh >= 7.0) & (nh < 13.5)] = 1           # eu
sess_cat[(nh >= 13.5) & (nh < 20.0)] = 2          # us
MA_TREND = df.close.rolling(max(sb(1150), 20), min_periods=max(sb(300), 10)).mean().values
MA_HTF = df.close.rolling(max(sb(600), 15), min_periods=max(sb(150), 8)).mean().values      # ~2-day higher-timeframe trend
htf_up = (np.where(np.isfinite(MA_HTF), C_ - MA_HTF, 0) > 0).astype(np.int64)
ATR_REF = pd.Series(ATR).rolling(max(sb(8280), 200), min_periods=max(sb(2000), 60)).mean().values
vol_hi = (ATR > ATR_REF).astype(np.int64)
vix = pd.read_csv(f"{REPO}/data/polygon/vix_daily.csv")
vix["date"] = pd.to_datetime(vix.date).dt.date
vix["med"] = vix.vix.rolling(252, min_periods=60).median()
vmap = dict(zip(vix.date, (vix.vix > vix.med).astype(int)))
vix_hi = np.array([vmap.get(d, 0) for d in ts.dt.date], dtype=np.int64)

# combo matrix (64 cells -> 324 filter combos); combo 0 = no filters
NCELL, NCOMBO = 64, 324
combos = []
CMAT = np.zeros((NCELL, NCOMBO), dtype=np.float64)
ci = 0
for sess_f in ("all", "us", "eu", "asia"):
    for tr_f in ("none", "with", "against"):
        for vol_f in ("none", "lo", "hi"):
            for vx_f in ("none", "lo", "hi"):
                for ht_f in ("none", "up", "dn"):
                    for cell in range(NCELL):
                        s, t, v, x, hu = (cell >> 4, (cell >> 3) & 1, (cell >> 2) & 1,
                                          (cell >> 1) & 1, cell & 1)
                        ok = True
                        if sess_f == "us" and s != 2: ok = False
                        if sess_f == "eu" and s != 1: ok = False
                        if sess_f == "asia" and s != 0: ok = False
                        if tr_f == "with" and t != 1: ok = False
                        if tr_f == "against" and t != 0: ok = False
                        if vol_f == "hi" and v != 1: ok = False
                        if vol_f == "lo" and v != 0: ok = False
                        if vx_f == "hi" and x != 1: ok = False
                        if vx_f == "lo" and x != 0: ok = False
                        if ht_f == "up" and hu != 1: ok = False
                        if ht_f == "dn" and hu != 0: ok = False
                        if ok: CMAT[cell, ci] = 1.0
                    combos.append((sess_f, tr_f, vol_f, vx_f, ht_f))
                    ci += 1

warm_i = int(np.searchsorted(ts.values, (ts.iloc[0] + pd.Timedelta(days=WARM_DAYS)).to_datetime64()))
sigok = mkt & ~eod_b & ~contam & np.isfinite(ATR) & (ATR > 0)
sigok[:warm_i] = False
sigok[n - HMAX - TTLMAX - 2:] = False

# padded arrays for window building
PAD = HMAX + TTLMAX + 4
# THE CENTRAL UNKNOWN OF THIS WHOLE PROJECT, now measurable.
# Every prior campaign assumed a resting limit fills whenever price merely
# touches it. That convention was worth more than any effect we ever measured
# (1.06 ticks in ZB). lowsz/highsz give the contracts that actually PRINTED at
# each bar's extreme, so instead of assuming, we sweep the requirement and
# watch what survives:
#   0  = bare touch fills            (the old, optimistic convention)
#   5  = a small queue must clear    (realistic for a 1-lot at the front)
#   25 = real size traded there      (conservative; you were definitely filled)
# A config whose P&L barely moves from 0 to 25 has an edge that does not live
# in the fill assumption. That is the only kind worth trading.
# On OHLCV there is no size-at-the-extreme to test, so the fill rule itself is
# the swept axis: 0 = the old bare-touch convention, 1 = price must trade a
# full tick PAST the limit. The NQ tape says a bar low sees a median of two
# contracts, nowhere near enough to fill a 1-lot behind a real queue, so
# trade-through is the honest setting and bare touch is kept only to measure
# how much of any edge is convention.
MIN_FILLS = [float(x) for x in os.environ.get("M2_MINFILL", "0,1").split(",")]
LOWSZp = np.concatenate([LOWSZ, np.zeros(PAD)])
HIGHSZp = np.concatenate([HIGHSZ, np.zeros(PAD)])
Op = np.concatenate([O, np.full(PAD, np.nan)])
Hp = np.concatenate([H_, np.full(PAD, np.nan)])
Lp = np.concatenate([L_, np.full(PAD, np.nan)])
Cp = np.concatenate([C_, np.full(PAD, np.nan)])

def rnd(px):
    return np.round(np.round(px / TICK) * TICK, 10)

def thin(idx, spacing=THIN):
    if len(idx) == 0: return idx
    keep = [idx[0]]; last = idx[0]
    for i in idx[1:]:
        if i - last >= spacing:
            keep.append(i); last = i
    return np.array(keep, dtype=np.int64)

def first_true(m):
    anyr = m.any(axis=1)
    j = m.argmax(axis=1)
    return np.where(anyr, j, BIG)

# ---------------------------------------------------------------- streams
MOMS = {}
def mom(lb_u):
    """Momentum over lb_u 5-min-equivalent units."""
    if lb_u not in MOMS:
        L = sb(lb_u)
        MOMS[lb_u] = np.concatenate([np.full(L, np.nan), C_[L:] - C_[:-L]])
    return MOMS[lb_u]
def donhi(N_u):
    return pd.Series(H_).rolling(sb(N_u)).max().shift(1).values
def donlo(N_u):
    return pd.Series(L_).rolling(sb(N_u)).min().shift(1).values

_FBA = {}
def first_bar_at(hour):
    """First bar of each day at/after `hour` UTC. Replaces the 5-minute window
    test `(nh >= h) & (nh < h + 5/60)`, which can select zero bars on a coarse
    series and many bars on a fine one."""
    if hour not in _FBA:
        ok_ = nh >= hour
        newday = np.r_[True, day_codes[1:] != day_codes[:-1]]
        first = ok_ & (np.r_[False, ~ok_[:-1]] | newday)
        _FBA[hour] = np.where(first & ok_)[0]
    return _FBA[hour]


# ============================ CROSS-MARKET DATA ============================
# Every family above this line reads one market's own price history, which is
# why they collapse onto a single mechanism: they are all looking at the same
# number. These read OTHER markets. A signal built from ES tells you something
# about NQ that NQ's own bars cannot, so the resulting streams are
# uncorrelated with the fib book by construction rather than by luck.
#
# Single leg only. A spread trade pays two round turns, and at the 2x-cost
# optimum where net edge is about one round turn, a second leg eats the whole
# thing. So the spread is the SIGNAL and the trade is one contract in the
# market that is mispriced.
PARTNERS = [p for p in ("ES", "NQ", "RTY", "YM", "GC", "CL", "HG", "NG",
                        "ZB", "ZN", "ZF", "6E", "6B", "MBT")
            if p != ROOT]

def _load_partner(p):
    """Partner closes on the target's own bar grid. Reindex-then-ffill, never
    interpolate: a partner that has not printed yet must carry its last known
    price, not a value borrowed from the future."""
    f = f"{REPO}/data/polygon/{p}_5min.csv"
    if not os.path.exists(f):
        return None
    d = pd.read_csv(f, usecols=["ts", "close"])
    d["ts"] = pd.to_datetime(d.ts, utc=True)
    if TF != "5":
        d = (d.set_index("ts").resample(f"{TF}min", label="left", closed="left")
               .agg(close=("close", "last")).dropna().reset_index())
    s = d.set_index("ts").close.reindex(ts, method="ffill")
    v = s.values.astype(np.float64)
    return v if np.isfinite(v).sum() > 0.5 * n else None

PX = {}
for _p in PARTNERS:
    _v = _load_partner(_p)
    if _v is not None:
        PX[_p] = _v
print(f"cross-market partners loaded: {len(PX)} -> {sorted(PX)}", flush=True)

def _lr(v, k):
    """Causal log return over k bars."""
    out = np.full(len(v), np.nan)
    out[k:] = np.log(np.maximum(v[k:], 1e-12) / np.maximum(v[:-k], 1e-12))
    return out

def _z(a, w):
    s = pd.Series(a)
    m = max(w, 20)
    return ((a - s.rolling(m, min_periods=m // 2).mean().values) /
            np.maximum(s.rolling(m, min_periods=m // 2).std().values, 1e-12))

def streams():
    """Cross-market signals, single-leg execution."""
    if not PX:
        return
    RT = _lr(C_, sb(1))                     # target's own 5-min-equivalent return

    # ---- 1. SPREAD REVERSION -------------------------------------------
    # Beta-hedged residual between target and partner, z-scored. When the
    # residual is stretched the target is rich or cheap against the partner;
    # fade it in the target alone.
    for p, pv in PX.items():
        RP = _lr(pv, sb(1))
        for w in ([48, 288] if DEPTH == 2 else [24, 48, 96, 288]):
            W_ = max(sb(w), 20)
            sr = pd.Series(RT); sp_ = pd.Series(RP)
            cov = sr.rolling(W_, min_periods=W_ // 2).cov(sp_).values
            var = sp_.rolling(W_, min_periods=W_ // 2).var().values
            beta = np.clip(np.where(var > 1e-18, cov / np.maximum(var, 1e-18), 0), -5, 5)
            resid = RT - beta * RP
            spread = pd.Series(np.nan_to_num(resid)).rolling(
                W_, min_periods=W_ // 2).sum().values
            zz = _z(spread, W_)
            for thr, mode in itertools.product(
                    ([1.5, 2.5] if DEPTH == 2 else [1.0, 1.5, 2.0, 2.5, 3.0]),
                    ("fade", "with")):
                sig = sigok & np.isfinite(zz) & (np.abs(zz) > thr)
                idx = thin(np.where(sig)[0])
                if len(idx) < 40: continue
                sd_ = np.sign(zz[idx]).astype(np.int64)
                # A stretched spread can mean revert or keep going. Only fade
                # was ever tested and it lost out of sample 404 times out of
                # 404, so the opposite direction is genuinely untested rather
                # than a refit of the same thing.
                side = -sd_ if mode == "fade" else sd_
                ok_ = side != 0
                if ok_.sum() < 40: continue
                i2, s2 = idx[ok_], side[ok_]
                yield ("xspread", dict(p=p, w=w, thr=thr, mode=mode), "M", i2, s2,
                       np.full(len(i2), np.nan))
                # limit variant: a resting limit is filled AT its price while a
                # market order pays a tick, and one MNQ tick is 35% of the
                # round turn -- decisive at this edge size.
                yield ("xspreadL", dict(p=p, w=w, thr=thr, mode=mode), "L", i2, s2,
                       rnd(C_[i2] - 0.5 * ATR[i2] * s2))

    # ---- 2. LEAD-LAG ----------------------------------------------------
    # The partner has already moved; does the target follow or fade?
    for p, pv in PX.items():
        for k in ([3, 12] if DEPTH == 2 else [1, 3, 6, 12, 24]):
            rp = _lr(pv, sb(k))
            zp = _z(rp, max(sb(96), 40))
            for thr, mode in itertools.product(
                    ([2.0] if DEPTH == 2 else [1.5, 2.0, 3.0]), ("with", "fade")):
                sig = sigok & np.isfinite(zp) & (np.abs(zp) > thr)
                idx = thin(np.where(sig)[0])
                if len(idx) < 40: continue
                sd_ = np.sign(zp[idx]).astype(np.int64)
                side = sd_ if mode == "with" else -sd_
                ok_ = side != 0
                if ok_.sum() < 40: continue
                i2, s2 = idx[ok_], side[ok_]
                yield ("xlead", dict(p=p, k=k, thr=thr, mode=mode), "M", i2, s2,
                       np.full(len(i2), np.nan))

    # ---- 3. DIVERGENCE / CATCH-UP ---------------------------------------
    # The partner moved and the target did not. Either the target catches up
    # or the move was partner-specific; the search decides which.
    for p, pv in PX.items():
        for k in ([6, 24] if DEPTH == 2 else [3, 6, 12, 24, 48]):
            rp, rt = _lr(pv, sb(k)), _lr(C_, sb(k))
            gap = _z(rp, max(sb(96), 40)) - _z(rt, max(sb(96), 40))
            for thr, mode in itertools.product(
                    ([2.0] if DEPTH == 2 else [1.5, 2.0, 2.5, 3.0]), ("catchup", "fade")):
                sig = sigok & np.isfinite(gap) & (np.abs(gap) > thr)
                idx = thin(np.where(sig)[0])
                if len(idx) < 40: continue
                sd_ = np.sign(gap[idx]).astype(np.int64)
                side = sd_ if mode == "catchup" else -sd_
                ok_ = side != 0
                if ok_.sum() < 40: continue
                i2, s2 = idx[ok_], side[ok_]
                yield ("xdiverge", dict(p=p, k=k, thr=thr, mode=mode), "M", i2, s2,
                       np.full(len(i2), np.nan))
                yield ("xdivergeL", dict(p=p, k=k, thr=thr, mode=mode), "L", i2, s2,
                       rnd(C_[i2] - 0.5 * ATR[i2] * s2))

    # ---- 4. BREADTH ------------------------------------------------------
    # How many partners are pushing the same way. A move the whole complex
    # agrees with is a different animal from one market wandering alone.
    if len(PX) >= 4:
        for k in ([6, 24] if DEPTH == 2 else [3, 6, 12, 24]):
            R = np.vstack([_lr(v, sb(k)) for v in PX.values()])
            breadth = np.nanmean(np.sign(R), axis=0)
            rt = _lr(C_, sb(k))
            for thr, mode in itertools.product(
                    ([0.6] if DEPTH == 2 else [0.4, 0.6, 0.8, 1.0]), ("with", "fade", "lag")):
                if mode == "lag":
                    sig = (sigok & np.isfinite(breadth) & np.isfinite(rt)
                           & (np.abs(breadth) >= thr) & (np.sign(rt) != np.sign(breadth)))
                    sd_src = breadth
                else:
                    sig = sigok & np.isfinite(breadth) & (np.abs(breadth) >= thr)
                    sd_src = breadth
                idx = thin(np.where(sig)[0])
                if len(idx) < 40: continue
                sd_ = np.sign(sd_src[idx]).astype(np.int64)
                side = -sd_ if mode == "fade" else sd_
                ok_ = side != 0
                if ok_.sum() < 40: continue
                i2, s2 = idx[ok_], side[ok_]
                yield ("xbreadth", dict(k=k, thr=thr, mode=mode), "M", i2, s2,
                       np.full(len(i2), np.nan))

# ------------------------------------------------------- fills and outcomes
def resolve_fills(idx, side, px, etype, ttl, minfill=0.0):
    if etype == "M":
        fb = idx + 1
        epx = Op[fb] + TICK * side
        return fb, epx
    steps = np.arange(1, ttl + 1)
    bars = idx[:, None] + steps[None, :]
    if etype == "L":
        adverse = np.where(side[:, None] > 0, Lp[bars], Hp[bars])
        hit = (adverse * side[:, None]) <= (px * side)[:, None]
        if minfill > 0:
            # Require a full tick THROUGH the limit, not a touch of it. Works
            # for both directions: for a buy the low must reach px - TICK, for
            # a sell the high must reach px + TICK.
            hit = (adverse * side[:, None]) <= (px * side)[:, None] - TICK + 1e-9
    else:
        favor = np.where(side[:, None] > 0, Hp[bars], Lp[bars])
        hit = (favor * side[:, None]) >= (px * side)[:, None]
    j = first_true(hit)
    ok = j < BIG
    fb = np.where(ok, idx + 1 + np.minimum(j, ttl - 1), -1)
    if etype == "L":
        epx = px.astype(np.float64)
    else:
        opx = Op[np.maximum(fb, 0)]
        epx = np.maximum(opx * side, px * side) * side + TICK * side
    return np.where(ok, fb, -1), np.where(ok, epx, np.nan)

def build_windows(fb, side, Hbars):
    js = np.arange(0, Hbars + 1)
    bars = fb[:, None] + js[None, :]
    sgn = side[:, None].astype(np.float64)
    SLo = np.where(sgn > 0, Lp[bars], Hp[bars]) * sgn
    SHi = np.where(sgn > 0, Hp[bars], Lp[bars]) * sgn
    cm = np.maximum.accumulate(np.where(np.isnan(SHi), -np.inf, SHi), axis=1)
    Cw = Cp[bars]
    j_end = np.minimum(Hbars, ne[np.clip(fb, 0, n - 1)] - fb)
    j_end = np.maximum(j_end, 1)
    return SLo, SHi, cm, Cw, j_end

def outcomes(wins, fb, epx, side, a, sp_mult, rr, trail, Hbars):
    SLo, SHi, cm, Cw, j_end = wins
    E = len(fb)
    sp = rnd(epx - sp_mult * a * side) * side
    tp = rnd(epx + rr * sp_mult * a * side) * side
    if trail > 0:
        line = np.empty_like(SLo)
        line[:, 0] = sp
        line[:, 1:] = np.maximum(sp[:, None], cm[:, :-1] - (trail * a)[:, None])
    else:
        line = np.broadcast_to(sp[:, None], SLo.shape)
    j_stop = first_true(SLo <= line)
    tgt_hit = SHi >= tp[:, None]
    tgt_hit[:, 0] = False                      # same-bar target DENIED
    j_tgt = first_true(tgt_hit)
    take_stop = (j_stop <= j_tgt) & (j_stop <= j_end)
    take_tgt = ~take_stop & (j_tgt <= j_end)
    xj = np.where(take_stop, j_stop, np.where(take_tgt, j_tgt, j_end))
    rowi = np.arange(E)
    line_at = line[rowi, np.minimum(xj, Hbars)] * side
    close_at = Cw[rowi, np.minimum(xj, Hbars)]
    xpx = np.where(take_stop, line_at,
          np.where(take_tgt, tp * side, close_at - TICK * side))
    bad = ~np.isfinite(xpx) | ~np.isfinite(epx) | (fb < 0)
    return np.where(bad, -1, xj), np.where(bad, np.nan, xpx)

# ------------------------------------------------------------ scoring loop
EXITS = {
    # H is in 5-minute-equivalent units. Small stops with small targets are
    # what the 2x-cost optimum looks like, so the grid now reaches down to
    # 0.25 ATR stops and 5-minute holds as well as up.
    "fib":      (dict(sp=[0.75, 1.0, 1.5, 2.0, 2.5], rr=[0.5, 0.75, 1.0, 1.5, 2.5],
                      trail=[0.0, 2.5], ttl=[2, 3, 12], H=[2, 6, 12, 24, 48]) if DEPTH == 2 else
                 dict(sp=[0.25, 0.4, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5],
                      rr=[0.5, 0.618, 0.75, 1.0, 1.25, 1.5, 2.0],
                      trail=[0.0, 2.5], ttl=[1, 2, 3, 6, 12], H=[1, 2, 3, 6, 12, 24, 48])),
    "momcont":  dict(sp=[0.75, 1.0, 1.5, 2.0], rr=[0.75, 1.0, 1.5, 2.0],
                     trail=[0.0, 2.5], ttl=[1], H=[6, 12, 24]),
    "exhaust":  dict(sp=[0.75, 1.0, 1.5, 2.0], rr=[0.75, 1.0, 1.5],
                     trail=[0.0], ttl=[1], H=[6, 12, 24]),
    "fade":     (dict(sp=[0.75, 1.0, 1.5, 2.0], rr=[0.5, 0.75, 1.0, 1.5],
                      trail=[0.0], ttl=[2, 3], H=[2, 6, 12, 24]) if DEPTH == 2 else
                 dict(sp=[0.25, 0.4, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0],
                      rr=[0.5, 0.618, 0.75, 1.0, 1.25, 1.5],
                      trail=[0.0, 2.5], ttl=[1, 2, 3, 6], H=[1, 2, 3, 6, 12, 24, 48])),
    "mapull":   dict(sp=[0.75, 1.0, 1.5, 2.0], rr=[0.75, 1.0, 1.5],
                     trail=[0.0], ttl=[2, 3], H=[6, 12, 24]),
    "brk":      dict(sp=[1.0, 1.5, 2.0, 3.0], rr=[1.0, 1.5, 2.0, 3.0],
                     trail=[0.0, 2.5, 4.0], ttl=[3, 6, 12], H=[24, 48, 96]),
    "failbrk":  dict(sp=[1.0, 1.5, 2.0], rr=[1.0, 1.5, 2.0],
                     trail=[0.0], ttl=[1], H=[12, 24, 48]),
    "orb":      dict(sp=[0.75, 1.0, 1.5, 2.0], rr=[1.0, 1.5, 2.0, 3.0],
                     trail=[0.0, 2.5], ttl=[6, 12, 24], H=[12, 24, 48]),
    "vwaprev":  dict(sp=[0.75, 1.0, 1.5, 2.0], rr=[0.75, 1.0, 1.5],
                     trail=[0.0], ttl=[1], H=[6, 12, 24]),
    "vwaptrend":dict(sp=[0.75, 1.0, 1.5, 2.0], rr=[0.75, 1.0, 1.5, 2.0],
                     trail=[0.0], ttl=[2, 3, 6], H=[12, 24, 48]),
    "squeeze":  dict(sp=[1.0, 1.5, 2.0], rr=[1.0, 1.5, 2.0, 3.0],
                     trail=[0.0, 2.5], ttl=[3, 6, 12], H=[24, 48, 96]),
    "todmom":   dict(sp=[1.0, 1.5, 2.0], rr=[1.0, 1.5, 2.0],
                     trail=[0.0], ttl=[1], H=[6, 12, 24]),
    "gap":      dict(sp=[1.0, 1.5, 2.0], rr=[1.0, 1.5, 2.0],
                     trail=[0.0], ttl=[1], H=[12, 24, 48]),
}
_OF = dict(sp=[0.75, 1.0, 1.5, 2.0, 2.5], rr=[0.5, 0.75, 1.0, 1.5, 2.0],
           trail=[0.0, 2.5], ttl=[1], H=[6, 12, 24, 48])
# Cross-market exits reach short and small: the whole point is many little
# trades near the 2x-cost optimum, not a few big ones.
_X = (dict(sp=[0.5, 1.0, 2.0], rr=[0.75, 1.0, 1.5], trail=[0.0, 2.5],
           ttl=[1, 3], H=[2, 6, 12, 24]) if DEPTH == 2 else
      dict(sp=[0.25, 0.4, 0.6, 0.8, 1.0, 1.5, 2.0, 2.5],
           rr=[0.5, 0.75, 1.0, 1.25, 1.5, 2.0], trail=[0.0, 2.5],
           ttl=[1, 2, 3, 6], H=[1, 2, 3, 6, 12, 24, 48]))
for _f in ("xspread", "xspreadL", "xlead", "xdiverge", "xdivergeL", "xbreadth"):
    EXITS[_f] = _X
for _f in ("deltaext", "deltadiv", "cdbrk", "absorb", "bigtrade",
           "intensity", "exhaustflow"):
    EXITS[_f] = _OF
# Order flow needs the trade tape. On OHLCV those columns are constants, so the
# families would fire on noise -- skip them rather than search a fiction.
OF_FAMS = {"deltaext", "deltadiv", "cdbrk", "absorb", "bigtrade",
           "intensity", "exhaustflow"}

rows_all = []
wvecs = []          # weekly P&L per surviving config, aligned to rows_all[i]["wi"]
base_rows = []
n_cfg_total = 0
n_gated = 0
wk_tr_idx = np.where(wk_train)[0]
wk_o10_idx = np.where(wk_o10)[0]
wk_o3_idx = np.where(wk_o3)[0]
n_streams = 0

_si = -1
for fam, pdict, etype, idx, side, px in streams():
    _si += 1
    if _si % SH_N != SH_K: continue
    n_streams += 1
    ex = EXITS[fam]
    a_sig = ATR[idx]
    trend_with = (side * np.sign(np.where(np.isfinite(MA_TREND[idx]),
                                          C_[idx] - MA_TREND[idx], 0)) > 0).astype(np.int64)
    cell = (sess_cat[idx] << 4) | (trend_with << 3) | (vol_hi[idx] << 2) | \
           (vix_hi[idx] << 1) | htf_up[idx]
    # Fill realism only applies to resting limits. Market and stop entries are
    # unaffected, so evaluating them once (mf = -1, "n/a") avoids triplicating
    # identical rows and polluting the ranking with duplicates.
    fill_levels = MIN_FILLS if etype == "L" else [-1.0]
    for ttl_u, mf in itertools.product(ex["ttl"], fill_levels):
        ttl = min(sb(ttl_u), TTLMAX)
        fb, epx = resolve_fills(idx, side, px, etype, ttl, max(mf, 0.0))
        ok = fb >= 0
        if ok.sum() < 30: continue
        fill_rate = float(ok.mean())
        fbo, epo, sdo, ao, cello = fb[ok], epx[ok], side[ok], a_sig[ok], cell[ok]
        for H_u in ex["H"]:
            Hbars = min(sb(H_u), HMAX)
            wins = build_windows(fbo, sdo, Hbars)
            for sp_mult, rr, trail in itertools.product(ex["sp"], ex["rr"], ex["trail"]):
                xj, xpx = outcomes(wins, fbo, epo, sdo, ao, sp_mult, rr, trail, Hbars)
                good = xj >= 0
                if good.sum() < 30:
                    n_cfg_total += NCOMBO
                    continue
                pnl = (xpx[good] - epo[good]) * sdo[good] * PV - COMM
                xb = np.clip(fbo[good] + xj[good], 0, n - 1)
                cg = cello[good]
                wct = wk_codes[xb] * NCELL + cg
                WCT = np.bincount(wct, weights=pnl, minlength=W * NCELL).reshape(W, NCELL)
                CNT = np.bincount(wct, minlength=W * NCELL).astype(np.float64).reshape(W, NCELL)
                wkP = WCT @ CMAT
                wkN = CNT @ CMAT
                trP = wkP[wk_tr_idx]
                nt = wkN[wk_tr_idx].sum(0)
                net_tr = trP.sum(0)
                wk_mean = net_tr / max(len(wk_tr_idx), 1)
                ev = net_tr / np.maximum(nt, 1)
                poswk = (trP > 0).mean(0)
                yrP = Ymat @ wkP
                yr_ok = (yrP > 0).all(0)
                o10 = wkP[wk_o10_idx].sum(0)
                o3 = wkP[wk_o3_idx].sum(0)
                n_cfg_total += NCOMBO
                base_rows.append(dict(fam=fam, **pdict, etype=etype, ttl=int(ttl_u),
                                      mf=float(mf), H=int(H_u), sp=float(sp_mult), rr=float(rr),
                                      trail=float(trail),
                                      wk=float(wk_mean[0]), ev=float(ev[0]),
                                      n=int(nt[0])))
                # TRAIN-ONLY GATE. o10/o3 are deliberately absent here.
                # Gating on "also positive out of sample" across billions of
                # configs manufactures the validation it appears to provide:
                # the OOS window is the last ~11 weeks of a 2.9-year tape,
                # roughly 3% of the data and a few dozen trades, so with enough
                # candidates something always clears it. Left out of the gate,
                # o10/o3 stay an unmined diagnostic worth reading.
                # A config earning $15/wk on 25 trades/wk is an excellent
                # portfolio component; the old wk_mean >= 25 bar threw those
                # away and kept only big lonely configs. What matters in a book
                # is dollars per trade above cost, consistency, and frequency —
                # size comes from stacking streams, not from one config.
                tpw = nt / max(len(wk_tr_idx), 1)
                gate = (nt >= 150) & (ev >= EV_FLOOR) & (poswk >= 0.53) & \
                       yr_ok & (wk_mean > 0)
                if not gate.any():
                    continue
                # expensive tensors only for gated combos
                GW = np.bincount(wct, weights=np.maximum(pnl, 0), minlength=W * NCELL).reshape(W, NCELL)
                GL = np.bincount(wct, weights=np.minimum(pnl, 0), minlength=W * NCELL).reshape(W, NCELL)
                WIN = np.bincount(wct, weights=(pnl > 0).astype(np.float64),
                                  minlength=W * NCELL).reshape(W, NCELL)
                dct = day_codes[xb] * NCELL + cg
                DCT = np.bincount(dct, weights=pnl, minlength=ND * NCELL).reshape(ND, NCELL)
                DCN = np.bincount(dct, minlength=ND * NCELL).astype(np.float64).reshape(ND, NCELL)
                gi = np.where(gate)[0]
                gw = (GW[wk_tr_idx].sum(0)) @ CMAT[:, gi]
                gl = (GL[wk_tr_idx].sum(0)) @ CMAT[:, gi]
                pf = gw / np.maximum(-gl, 1e-9)
                wr = ((WIN[wk_tr_idx].sum(0)) @ CMAT[:, gi]) / np.maximum(nt[gi], 1)
                dayP = DCT @ CMAT[:, gi]
                dayN = DCN @ CMAT[:, gi]
                trPg = trP[:, gi]
                cum = np.cumsum(trPg, axis=0)
                runmax = np.maximum.accumulate(cum, axis=0)
                dd = cum - runmax
                maxDD = dd.min(0)
                ulcer = np.sqrt((dd ** 2).mean(0))
                wk_std = trPg.std(0) + 1e-9
                base_i = len(base_rows) - 1
                for z, g in enumerate(gi):
                    if pf[z] < 1.05: continue
                    n_gated += 1
                    dcol = dayP[:, z]; dn_ = dayN[:, z]
                    ld = dcol[(dcol < 0) & (dn_ > 0)]
                    wvecs.append(wkP[:, g].astype(np.float32))
                    rows_all.append(dict(
                        wi=len(wvecs) - 1, tpw=round(float(tpw[g]), 2),
                        fam=fam, **pdict, etype=etype, ttl=int(ttl_u), H=int(H_u),
                        ttl_bars=int(ttl), H_bars=int(Hbars), H_min=round(H_u * 5.0, 1),
                        mf=float(mf), fill_rate=round(fill_rate, 4),
                        sp=float(sp_mult), rr=float(rr), trail=float(trail),
                        f_sess=combos[g][0], f_trend=combos[g][1],
                        f_vol=combos[g][2], f_vix=combos[g][3], f_htf=combos[g][4],
                        n_tr=int(nt[g]), wk=round(float(wk_mean[g]), 2),
                        sharpe=round(float(wk_mean[g] / wk_std[z]), 3),
                        poswk=round(float(poswk[g]), 3), pf=round(float(pf[z]), 3),
                        wr=round(float(wr[z]), 3), ev=round(float(ev[g]), 2),
                        maxdd=round(float(maxDD[z]), 0), ulcer=round(float(ulcer[z]), 1),
                        worst_wk=round(float(trPg[:, z].min()), 0),
                        worst_day=round(float(dcol.min()), 0),
                        avg_lose_day=round(float(ld.mean()) if len(ld) else 0.0, 1),
                        o10=round(float(o10[g]), 0), o3=round(float(o3[g]), 0),
                        base_i=base_i,
                    ))
    if len(rows_all) > 400000:
        rows_all.sort(key=lambda r: -r["sharpe"])
        rows_all = rows_all[:200000]
        keep = [r["wi"] for r in rows_all]
        wvecs = [wvecs[i] for i in keep]
        for _i, _r in enumerate(rows_all):
            _r["wi"] = _i

elapsed = time.time() - t0
print(f"{ROOT}: {n_streams} streams, {n_cfg_total} configs, {n_gated} gated, {elapsed:.0f}s",
      flush=True)

if rows_all:
    df_r = pd.DataFrame(rows_all)
    def pr(s, higher_better=True):
        return s.rank(ascending=higher_better, pct=True)
    # Weighted for a book rather than a single bet: dollars per trade and
    # frequency carry the most, because total P&L is ev x trades x streams.
    # Rewarding raw $/trade selects the staggered end of the curve: big wins,
    # big losses, few of them. Weekly Sharpe and trade count are what a clean
    # equity curve is made of, and $/trade only has to clear cost -- which
    # EV_FLOOR already enforces -- so it barely features here.
    score = (0.34 * pr(df_r.sharpe) + 0.26 * pr(np.log1p(df_r.n_tr)) +
             0.09 * pr(df_r.ulcer, False) + 0.08 * pr(df_r.maxdd) +
             0.07 * pr(df_r.worst_wk) + 0.06 * pr(df_r.pf) +
             0.05 * pr(df_r.o10) + 0.03 * pr(df_r.avg_lose_day) +
             0.02 * pr(df_r.ev))
    df_r["score"] = score.round(4)
    # Rank within each fill requirement, not across them. Bare-touch rows
    # score higher by construction, so a global top-N would truncate away the
    # mf=25 twin of every good config and make the honest comparison
    # impossible at merge time.
    df_r = (df_r.sort_values("score", ascending=False)
                .groupby("mf", group_keys=False).head(2500))
    top = df_r.to_dict("records")
else:
    top = []

out = dict(root=ROOT, series=SERIES, bars_per_day=int(BARS_PER_DAY),
           bar_min=round(BAR_MIN, 3), scale=round(SC, 4), min_fills=MIN_FILLS,
           traded_as=TRADED_AS, pv=PV, tick=TICK, comm=COMM,
           margin=MARGIN, afford=bool(AFFORD), engine="pessimistic-vectorized-v3-deep", depth=DEPTH,
           n_bars=int(n), n_weeks=int(W), n_streams=int(n_streams),
           n_base=len(base_rows), n_cfg=int(n_cfg_total), n_gated=int(n_gated),
           elapsed_s=round(elapsed), top=top)
SUF = ("d" if DEPTH == 3 else "b") + "_x" + SERIES + (f"_sh{SH_K}" if SHARD else "")
with gzip.open(f"{D}/pf{SUF}_{ROOT}.json.gz", "wt") as f:
    json.dump(out, f)
if top:
    # realign so row i of the matrix is candidate i of `top`
    V = np.stack([wvecs[r["wi"]] for r in top]).astype(np.float32)
    for _i, _r in enumerate(top):
        _r["wi"] = _i
    np.savez_compressed(
        f"{D}/pf{SUF}wk_{ROOT}.npz", wk=V,
        weeks=np.array([str(x) for x in wk_uniq]),
        train=wk_train.astype(bool), hold=wk_o10.astype(bool))
    print(f"{ROOT}: weekly matrix {V.shape} -> pf{SUF}wk_{ROOT}.npz", flush=True)

bd = pd.DataFrame(base_rows)
if len(bd):
    keep = (bd.ev > 0) | (bd.wk > 0) | (np.arange(len(bd)) % 20 == 0)
    bd = bd[keep]
    np.savez_compressed(f"{D}/pf{SUF}base_{ROOT}.npz", data=bd.to_records(index=False))
print(f"{ROOT}: saved {len(top)} top rows, {len(bd)}/{len(base_rows)} base rows -> tk{SUF}", flush=True)
