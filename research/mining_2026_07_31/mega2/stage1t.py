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
THIN_U = 24        # 2h min spacing between signals per stream
BIG = 10 ** 6

t0 = time.time()

# ---------------------------------------------------------------- data prep
SERIES = os.environ.get("M2_SERIES", "time_5m")
df = pd.read_parquet(f"{REPO}/data/tick/bars/{ROOT}_{SERIES}.parquet")
df["ts"] = pd.to_datetime(df.ts, utc=True)
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
MIN_FILLS = [float(x) for x in os.environ.get("M2_MINFILL", "0,5,25").split(",")]
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

def streams():
    """yield (fam, pdict, entry_type, sig_idx, side, px). px NaN => market."""
    FIB_LB = ([6, 8, 12, 16, 24, 32, 48, 96] if DEPTH == 2 else
              [4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 144])
    FIB_K = ([0.75, 1.0, 1.5, 2.0, 3.0] if DEPTH == 2 else
             [0.6, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0])
    FIB_PB = ([0.236, 0.382, 0.5, 0.618, 0.706, 0.786, 0.886] if DEPTH == 2 else
              [0.236, 0.318, 0.382, 0.44, 0.5, 0.56, 0.618, 0.706, 0.786, 0.886])
    for lb, k, pb in itertools.product(FIB_LB, FIB_K, FIB_PB):
        m = mom(lb)
        sig = sigok & np.isfinite(m) & (np.abs(m) > k * ATR)
        idx = thin(np.where(sig)[0])
        if len(idx) < 30: continue
        side = np.sign(m[idx]).astype(np.int64)
        px = rnd(C_[idx] - pb * m[idx])
        yield ("fib", dict(lb=lb, k=k, pb=pb), "L", idx, side, px)
    FD_LB = [4, 6, 12, 24, 48] if DEPTH == 2 else [4, 6, 8, 12, 16, 24, 48, 96]
    FD_K = [0.6, 0.8, 1.2, 1.8, 2.5] if DEPTH == 2 else [0.5, 0.6, 0.8, 1.0, 1.2, 1.5, 1.8, 2.2, 2.5]
    FD_DEP = [0.0, 0.25, 0.5, 1.0] if DEPTH == 2 else [0.0, 0.25, 0.4, 0.5, 0.65, 0.8, 1.0, 1.5]
    for lb, k, dep in itertools.product(FD_LB, FD_K, FD_DEP):
        m = mom(lb)
        sig = sigok & np.isfinite(m) & (np.abs(m) > k * ATR)
        idx = thin(np.where(sig)[0])
        if len(idx) < 30: continue
        side = -np.sign(m[idx]).astype(np.int64)
        px = rnd(C_[idx] - dep * ATR[idx] * side)
        yield ("fade", dict(lb=lb, k=k, dep=dep), "L", idx, side, px)
    for man, lb in itertools.product([20, 50, 100, 200], [3, 6, 12]):
        ma = pd.Series(C_).rolling(sb(man), min_periods=max(sb(man)//2,2)).mean().values
        m = mom(lb)
        up = sigok & np.isfinite(ma) & np.isfinite(m) & (C_ > ma) & (m < 0)
        dn = sigok & np.isfinite(ma) & np.isfinite(m) & (C_ < ma) & (m > 0)
        sig = up | dn
        idx = thin(np.where(sig)[0])
        if len(idx) < 30: continue
        side = np.where(up[idx], 1, -1).astype(np.int64)
        px = rnd(C_[idx] - 0.5 * ATR[idx] * side)
        yield ("mapull", dict(man=man, lb=lb), "L", idx, side, px)
    for N, buf in itertools.product([12, 24, 48, 96, 144, 192, 288, 384], [0.0, 0.25, 0.5]):
        dh, dl = donhi(N), donlo(N)
        near_hi = sigok & np.isfinite(dh) & (H_ > dh - 0.5 * ATR) & (C_ <= dh + buf * ATR)
        near_lo = sigok & np.isfinite(dl) & (L_ < dl + 0.5 * ATR) & (C_ >= dl - buf * ATR)
        for nm, mask, sd, lvl in (("up", near_hi, 1, dh), ("dn", near_lo, -1, dl)):
            idx = thin(np.where(mask)[0])
            if len(idx) < 30: continue
            side = np.full(len(idx), sd, dtype=np.int64)
            px = rnd(lvl[idx] + buf * ATR[idx] * sd)
            yield ("brk", dict(N=N, buf=buf, dir=nm), "S", idx, side, px)
    for N, m_ in itertools.product([24, 48, 96, 192, 288], [1, 2, 3]):
        dh, dl = donhi(N), donlo(N)
        poke_hi = (H_ >= dh) & np.isfinite(dh)
        poke_lo = (L_ <= dl) & np.isfinite(dl)
        rp_hi = pd.Series(poke_hi).rolling(m_ + 1).max().fillna(0).values.astype(bool)
        rp_lo = pd.Series(poke_lo).rolling(m_ + 1).max().fillna(0).values.astype(bool)
        fail_hi = sigok & rp_hi & (C_ < dh)
        fail_lo = sigok & rp_lo & (C_ > dl)
        sig = fail_hi | fail_lo
        idx = thin(np.where(sig)[0])
        if len(idx) < 30: continue
        side = np.where(fail_hi[idx], -1, 1).astype(np.int64)
        yield ("failbrk", dict(N=N, m=m_), "M", idx, side, np.full(len(idx), np.nan))
    for m_, buf in itertools.product([3, 6, 9, 12], [0.0, 0.25, 0.5]):
        sig_i, sides, pxs = [], [], []
        us_open = first_bar_at(13.5)
        for i0 in us_open:
            i1 = i0 + sb(m_)
            if i1 + 1 >= n or day_codes[i1] != day_codes[i0]: continue
            if not sigok[i1]: continue
            rh, rl = H_[i0:i1 + 1].max(), L_[i0:i1 + 1].min()
            a = ATR[i1]
            if not np.isfinite(a): continue
            sig_i += [i1, i1]; sides += [1, -1]
            pxs += [rnd(rh + buf * a), rnd(rl - buf * a)]
        if len(sig_i) < 30: continue
        yield ("orb", dict(m=m_, buf=buf), "S",
               np.array(sig_i), np.array(sides), np.array(pxs))
    # session-anchored VWAP
    pvv = C_ * np.maximum(V_, 0)
    day_start = np.r_[True, day_codes[1:] != day_codes[:-1]]
    vwap = np.zeros(n); dev_s = np.full(n, np.nan)
    cpv = cv = cn = s1 = s2 = 0.0
    for i in range(n):
        if day_start[i]: cpv = cv = cn = s1 = s2 = 0.0
        cpv += pvv[i]; cv += max(V_[i], 1e-9); cn += 1
        vw = cpv / cv
        dv = C_[i] - vw
        s1 += dv; s2 += dv * dv
        vwap[i] = vw
        if cn >= max(sb(24), 6):
            var = s2 / cn - (s1 / cn) ** 2
            dev_s[i] = np.sqrt(max(var, 1e-18))
    dev = C_ - vwap
    for g in (1.0, 1.5, 2.0, 2.5, 3.0, 3.5):
        sig = sigok & np.isfinite(dev_s) & (np.abs(dev) > g * dev_s)
        idx = thin(np.where(sig)[0])
        if len(idx) < 30: continue
        side = -np.sign(dev[idx]).astype(np.int64)
        yield ("vwaprev", dict(g=g), "M", idx, side, np.full(len(idx), np.nan))
    for lb in (6, 12, 24, 48):
        m = mom(lb)
        up = sigok & np.isfinite(dev_s) & (C_ > vwap) & (m > 0) & (dev > 0.5 * dev_s)
        dn = sigok & np.isfinite(dev_s) & (C_ < vwap) & (m < 0) & (dev < -0.5 * dev_s)
        sig = up | dn
        idx = thin(np.where(sig)[0])
        if len(idx) < 30: continue
        side = np.where(up[idx], 1, -1).astype(np.int64)
        px = rnd(vwap[idx])
        yield ("vwaptrend", dict(lb=lb), "L", idx, side, px)
    rng = H_ - L_
    sq = pd.Series(rng).rolling(max(sb(24), 5)).sum()
    sqref = sq.rolling(max(sb(288), 40), min_periods=max(sb(100), 15)).mean()
    for p, buf in itertools.product([0.5, 0.6, 0.7, 0.8], [0.0, 0.25]):
        squeeze = (sq < p * sqref).fillna(False).values
        dh, dl = donhi(24), donlo(24)
        for nm, sd, lvl in (("up", 1, dh), ("dn", -1, dl)):
            sig = sigok & squeeze & np.isfinite(lvl)
            idx = thin(np.where(sig)[0])
            if len(idx) < 30: continue
            side = np.full(len(idx), sd, dtype=np.int64)
            px = rnd(lvl[idx] + buf * ATR[idx] * sd)
            yield ("squeeze", dict(p=p, buf=buf, dir=nm), "S", idx, side, px)
    for hh, lb in itertools.product([7.0, 13.5, 23.0], [12, 24, 72, 144]):
        m = mom(lb)
        at_i = first_bar_at(hh)
        at = np.zeros(n, dtype=bool); at[at_i] = True
        at &= sigok & np.isfinite(m) & (m != 0)
        idx = thin(np.where(at)[0], spacing=sb(100))
        if len(idx) < 30: continue
        side = np.sign(m[idx]).astype(np.int64)
        yield ("todmom", dict(h=hh, lb=lb), "M", idx, side, np.full(len(idx), np.nan))
    if ROOT in ("ES", "RTY", "YM", "GC", "CL"):
        dayrng = pd.Series(rng).rolling(sb(390), min_periods=sb(200)).mean().values * sb(12)
        prev_close = np.full(n, np.nan)
        last_rth_close = np.nan
        for i in range(n):
            if 19.9 <= nh[i] < 20.05: last_rth_close = C_[i]
            prev_close[i] = last_rth_close
        us_open = np.zeros(n, dtype=bool); us_open[first_bar_at(13.5)] = True
        gapv = O - prev_close
        for g, mode in itertools.product([0.2, 0.3, 0.45, 0.6, 0.8, 1.0], ["fade", "go"]):
            sig = sigok & us_open & np.isfinite(prev_close) & np.isfinite(dayrng) & \
                  (np.abs(gapv) > g * dayrng) & (np.abs(gapv) < 5 * dayrng)
            idx = thin(np.where(sig)[0], spacing=sb(100))
            if len(idx) < 30: continue
            sd = np.sign(gapv[idx]).astype(np.int64)
            side = -sd if mode == "fade" else sd
            yield ("gap", dict(g=g, mode=mode), "M", idx, side, np.full(len(idx), np.nan))
    # MOMENTUM CONTINUATION: market entry in impulse direction
    for lb, k in itertools.product([6, 12, 24, 48], [1.0, 1.5, 2.0, 2.5]):
        m = mom(lb)
        sig = sigok & np.isfinite(m) & (np.abs(m) > k * ATR)
        idx = thin(np.where(sig)[0])
        if len(idx) < 30: continue
        side = np.sign(m[idx]).astype(np.int64)
        yield ("momcont", dict(lb=lb, k=k), "M", idx, side, np.full(len(idx), np.nan))
    # TREND EXHAUSTION: run of r same-direction closes + stretch -> fade
    dirs = np.sign(np.r_[0.0, np.diff(C_)])
    runlen = np.zeros(n); rl = 0; prev = 0
    for i in range(1, n):
        rl = rl + 1 if dirs[i] == prev and dirs[i] != 0 else 1
        prev = dirs[i]; runlen[i] = rl
    for r_, k in itertools.product([4, 5, 6, 8], [1.5, 2.5]):
        m = mom(6)
        sig = sigok & (runlen >= r_) & np.isfinite(m) & (np.abs(m) > k * ATR)
        idx = thin(np.where(sig)[0])
        if len(idx) < 30: continue
        side = -dirs[idx].astype(np.int64)
        ok_ = side != 0
        if ok_.sum() < 30: continue
        yield ("exhaust", dict(r=r_, k=k), "M", idx[ok_], side[ok_],
               np.full(int(ok_.sum()), np.nan))
    # ============ ORDER-FLOW FAMILIES (tick-only, 2026-08-02) ============
    def _z(a, n_u):
        w = max(sb(n_u), 12); mp = max(w // 2, 6)
        s_ = pd.Series(a)
        return (a - s_.rolling(w, min_periods=mp).mean().values) / \
               np.maximum(s_.rolling(w, min_periods=mp).std().values, 1e-9)
    _rngv = H_ - L_
    dz24, dz96 = _z(DELTA, 24), _z(DELTA, 96)
    for zt, mode in itertools.product([1.5, 2.0, 3.0], ["fade", "with"]):
        for dz, nm in ((dz24, 24), (dz96, 96)):
            sig = sigok & np.isfinite(dz) & (np.abs(dz) > zt)
            idx = thin(np.where(sig)[0])
            if len(idx) < 30: continue
            sd_ = np.sign(dz[idx]).astype(np.int64)
            side = -sd_ if mode == "fade" else sd_
            ok_ = side != 0
            if ok_.sum() < 30: continue
            yield ("deltaext", dict(zt=zt, mode=mode, dn=nm), "M",
                   idx[ok_], side[ok_], np.full(int(ok_.sum()), np.nan))
    for lb in (12, 24, 48):
        _w = sb(lb)
        pmax = pd.Series(C_).rolling(_w).max().values
        pmin = pd.Series(C_).rolling(_w).min().values
        cmax = pd.Series(CUMD).rolling(_w).max().values
        cmin = pd.Series(CUMD).rolling(_w).min().values
        bear = sigok & (C_ >= pmax - 1e-9) & (CUMD < cmax - 1e-9)
        bull = sigok & (C_ <= pmin + 1e-9) & (CUMD > cmin + 1e-9)
        idx = thin(np.where(bear | bull)[0])
        if len(idx) < 30: continue
        side = np.where(bear[idx], -1, 1).astype(np.int64)
        yield ("deltadiv", dict(lb=lb), "M", idx, side, np.full(len(idx), np.nan))
    for lb in (24, 96, 288):
        chi = pd.Series(CUMD).rolling(sb(lb)).max().shift(1).values
        clo = pd.Series(CUMD).rolling(sb(lb)).min().shift(1).values
        up = sigok & np.isfinite(chi) & (CUMD > chi)
        dn = sigok & np.isfinite(clo) & (CUMD < clo)
        idx = thin(np.where(up | dn)[0])
        if len(idx) < 30: continue
        side = np.where(up[idx], 1, -1).astype(np.int64)
        yield ("cdbrk", dict(lb=lb), "M", idx, side, np.full(len(idx), np.nan))
    volz = _z(np.log1p(V_), 96); rngz = _z(_rngv, 96)
    for vt, rt, mode in itertools.product([1.5, 2.5], [-0.5, -1.0], ["with", "fade"]):
        sig = sigok & np.isfinite(volz) & np.isfinite(rngz) & (volz > vt) & (rngz < rt)
        idx = thin(np.where(sig)[0])
        if len(idx) < 30: continue
        sd_ = np.sign(DELTA[idx]).astype(np.int64)
        side = sd_ if mode == "with" else -sd_
        ok_ = side != 0
        if ok_.sum() < 30: continue
        yield ("absorb", dict(vt=vt, rt=rt, mode=mode), "M",
               idx[ok_], side[ok_], np.full(int(ok_.sum()), np.nan))
    bigz = _z(BIGR, 96)
    for bt, mode in itertools.product([1.5, 2.5], ["with", "fade"]):
        sig = sigok & np.isfinite(bigz) & (bigz > bt)
        idx = thin(np.where(sig)[0])
        if len(idx) < 30: continue
        sd_ = np.sign(DELTA[idx]).astype(np.int64)
        side = sd_ if mode == "with" else -sd_
        ok_ = side != 0
        if ok_.sum() < 30: continue
        yield ("bigtrade", dict(bt=bt, mode=mode), "M",
               idx[ok_], side[ok_], np.full(int(ok_.sum()), np.nan))
    iz = _z(np.log1p(NTR / np.maximum(DURS, 1e-6)), 96)
    for it, mode in itertools.product([2.0, 3.0], ["with", "fade"]):
        sig = sigok & np.isfinite(iz) & (iz > it)
        idx = thin(np.where(sig)[0])
        if len(idx) < 30: continue
        sd_ = np.sign(C_[idx] - O[idx]).astype(np.int64)
        side = sd_ if mode == "with" else -sd_
        ok_ = side != 0
        if ok_.sum() < 30: continue
        yield ("intensity", dict(it=it, mode=mode), "M",
               idx[ok_], side[ok_], np.full(int(ok_.sum()), np.nan))
    ez = _z(DELTA / np.maximum(np.abs(C_ - O) / np.maximum(ATR, 1e-9), 0.05), 96)
    for et in (2.0, 3.0):
        sig = sigok & np.isfinite(ez) & (np.abs(ez) > et)
        idx = thin(np.where(sig)[0])
        if len(idx) < 30: continue
        side = -np.sign(ez[idx]).astype(np.int64)
        ok_ = side != 0
        if ok_.sum() < 30: continue
        yield ("exhaustflow", dict(et=et), "M",
               idx[ok_], side[ok_], np.full(int(ok_.sum()), np.nan))

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
            # TICK-NATIVE FILL REALISM. A bare touch is not a fill: require
            # `minfill` contracts to have actually PRINTED at the extreme,
            # i.e. enough size to clear a 1-lot queue. Prices the market
            # traded straight through still fill unconditionally.
            ext_sz = np.where(side[:, None] > 0, LOWSZp[bars], HIGHSZp[bars])
            deep = (adverse * side[:, None]) < (px * side)[:, None] - 1e-9
            hit = hit & (deep | (ext_sz >= minfill))
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
    "fib":      (dict(sp=[0.75, 1.0, 1.5, 2.0, 2.5], rr=[0.5, 0.75, 1.0, 1.5, 2.5],
                      trail=[0.0, 2.5], ttl=[2, 3, 12], H=[12, 24, 48]) if DEPTH == 2 else
                 dict(sp=[0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5], rr=[0.5, 0.618, 0.75, 1.0, 1.25, 1.5, 2.0],
                      trail=[0.0, 2.5], ttl=[1, 2, 3, 6, 12], H=[6, 12, 24, 48])),
    "momcont":  dict(sp=[0.75, 1.0, 1.5, 2.0], rr=[0.75, 1.0, 1.5, 2.0],
                     trail=[0.0, 2.5], ttl=[1], H=[6, 12, 24]),
    "exhaust":  dict(sp=[0.75, 1.0, 1.5, 2.0], rr=[0.75, 1.0, 1.5],
                     trail=[0.0], ttl=[1], H=[6, 12, 24]),
    "fade":     (dict(sp=[0.75, 1.0, 1.5, 2.0], rr=[0.5, 0.75, 1.0, 1.5],
                      trail=[0.0], ttl=[2, 3], H=[6, 12, 24]) if DEPTH == 2 else
                 dict(sp=[0.5, 0.75, 1.0, 1.25, 1.5, 2.0], rr=[0.5, 0.618, 0.75, 1.0, 1.25, 1.5],
                      trail=[0.0, 2.5], ttl=[1, 2, 3, 6], H=[6, 12, 24, 48])),
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
for _f in ("deltaext", "deltadiv", "cdbrk", "absorb", "bigtrade",
           "intensity", "exhaustflow"):
    EXITS[_f] = _OF

rows_all = []
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
                gate = (nt >= 150) & (wk_mean >= 25.0) & (poswk >= 0.55) & \
                       yr_ok & (ev > 0)
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
                    rows_all.append(dict(
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

elapsed = time.time() - t0
print(f"{ROOT}: {n_streams} streams, {n_cfg_total} configs, {n_gated} gated, {elapsed:.0f}s",
      flush=True)

if rows_all:
    df_r = pd.DataFrame(rows_all)
    def pr(s, higher_better=True):
        return s.rank(ascending=higher_better, pct=True)
    score = (0.20 * pr(df_r.sharpe) + 0.12 * pr(df_r.ulcer, False) +
             0.12 * pr(df_r.maxdd) + 0.10 * pr(df_r.avg_lose_day) +
             0.10 * pr(df_r.worst_wk) + 0.08 * pr(df_r.o10) +
             0.12 * pr(np.log1p(df_r.n_tr)) + 0.06 * pr(df_r.pf) +
             0.04 * pr(df_r.ev) + 0.06 * pr(df_r.wk))
    df_r["score"] = score.round(4)
    # Rank within each fill requirement, not across them. Bare-touch rows
    # score higher by construction, so a global top-N would truncate away the
    # mf=25 twin of every good config and make the honest comparison
    # impossible at merge time.
    df_r = (df_r.sort_values("score", ascending=False)
                .groupby("mf", group_keys=False).head(1500))
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
SUF = ("d" if DEPTH == 3 else "b") + "_" + SERIES + (f"_sh{SH_K}" if SHARD else "")
with gzip.open(f"{D}/tk{SUF}_{ROOT}.json.gz", "wt") as f:
    json.dump(out, f)
bd = pd.DataFrame(base_rows)
if len(bd):
    keep = (bd.ev > 0) | (bd.wk > 0) | (np.arange(len(bd)) % 20 == 0)
    bd = bd[keep]
    np.savez_compressed(f"{D}/tk{SUF}base_{ROOT}.npz", data=bd.to_records(index=False))
print(f"{ROOT}: saved {len(top)} top rows, {len(bd)}/{len(base_rows)} base rows -> tk{SUF}", flush=True)
