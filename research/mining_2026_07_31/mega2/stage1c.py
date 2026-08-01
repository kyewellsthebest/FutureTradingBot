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
SH_K, SH_N = (int(SHARD.split("/")[0]), int(SHARD.split("/")[1])) if SHARD else (0, 1)   # 2=wide sweep, 3=deep (promising markets)
D = os.path.dirname(os.path.abspath(__file__))
PV, TICK, COMM, TRADED_AS, MARGIN, AFFORD = ECON[ROOT]
HMAX = 96
TTLMAX = 12
WARM_DAYS = 10
THIN = 24          # min bars between signals per stream (overlap approx)
BIG = 10 ** 6

t0 = time.time()

# ---------------------------------------------------------------- data prep
df = pd.read_csv(f"{REPO}/data/polygon/{ROOT}_5min.csv")
df["ts"] = pd.to_datetime(df.ts, utc=True)
df = df.sort_values("ts").reset_index(drop=True)
n = len(df)
ts = df.ts
O = df.open.values.astype(np.float64); H_ = df.high.values.astype(np.float64)
L_ = df.low.values.astype(np.float64); C_ = df.close.values.astype(np.float64)
V_ = df.volume.values.astype(np.float64)

tr = np.maximum(df.high - df.low, (df.close - df.close.shift(1)).abs())
ATR = tr.rolling(14).mean().values

cdt = (ts + pd.Timedelta(minutes=5)).dt.tz_convert(None)
nh = (cdt.dt.hour + (cdt.dt.minute + 0.75) / 60).values
mkt = np.array([be.market_open(d.to_pydatetime() + pd.Timedelta(seconds=45)) for d in cdt])
eod_x = (nh >= be.EOD_UTC) & (nh < be.REOPEN_UTC)
eod_b = ((nh >= be.EOD_UTC - 0.5) & (nh < be.REOPEN_UTC))
gap = (ts.diff() > pd.Timedelta("3h")) & (ts.shift(1).dt.weekday != 4)
contam = gap.rolling(320, min_periods=1).max().fillna(0).values.astype(bool)

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
wk_train = (wk_first_ts < pd.Timestamp(TRAIN_END)).values
wk_o10 = (wk_first_ts >= pd.Timestamp(OOS10)).values
wk_o3 = (wk_first_ts >= pd.Timestamp(OOS3)).values
wk_year = wk_first_ts.dt.year.values
yr_counts = pd.Series(wk_year[wk_train]).value_counts()
years = sorted([y for y, c in yr_counts.items() if c >= 8])
Ymat = np.stack([(wk_year == y) & wk_train for y in years]).astype(np.float64)  # (Y,W)

# filter cells: sess(4) x trendwith(2) x volhi(2) x vixhi(2) = 32
sess_cat = np.full(n, 3, dtype=np.int64)          # other
sess_cat[(nh >= 0.0) & (nh < 7.0)] = 0            # asia
sess_cat[(nh >= 7.0) & (nh < 13.5)] = 1           # eu
sess_cat[(nh >= 13.5) & (nh < 20.0)] = 2          # us
MA_TREND = df.close.rolling(1150).mean().values
MA_HTF = df.close.rolling(600).mean().values
DAY_OPEN = df.groupby(day_codes).open.transform("first").values      # ~2-day higher-timeframe trend
htf_up = (np.where(np.isfinite(MA_HTF), C_ - MA_HTF, 0) > 0).astype(np.int64)
ATR_REF = pd.Series(ATR).rolling(8280, min_periods=2000).mean().values
vol_hi = (ATR > ATR_REF).astype(np.int64)
vix = pd.read_csv(f"{REPO}/data/polygon/vix_daily.csv")
vix["date"] = pd.to_datetime(vix.date).dt.date
vix["med"] = vix.vix.rolling(252, min_periods=60).median()
vmap = dict(zip(vix.date, (vix.vix > vix.med).astype(int)))
vix_hi = np.array([vmap.get(d, 0) for d in ts.dt.date], dtype=np.int64)

# combo matrix (128 cells -> 972 filter combos); combo 0 = no filters
NCELL, NCOMBO = 128, 972
combos = []
CMAT = np.zeros((NCELL, NCOMBO), dtype=np.float64)
ci = 0
for sess_f in ("all", "us", "eu", "asia"):
    for tr_f in ("none", "with", "against"):
        for vol_f in ("none", "lo", "hi"):
            for vx_f in ("none", "lo", "hi"):
                for ht_f in ("none", "up", "dn"):
                  for bi_f in ("none", "with", "against"):
                    for cell in range(NCELL):
                        s, t, v, x, hu, ba = (cell >> 5, (cell >> 4) & 1, (cell >> 3) & 1,
                                              (cell >> 2) & 1, (cell >> 1) & 1, cell & 1)
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
                        if bi_f == "with" and ba != 1: ok = False
                        if bi_f == "against" and ba != 0: ok = False
                        if ok: CMAT[cell, ci] = 1.0
                    combos.append((sess_f, tr_f, vol_f, vx_f, ht_f, bi_f))
                    ci += 1

warm_i = int(np.searchsorted(ts.values, (ts.iloc[0] + pd.Timedelta(days=WARM_DAYS)).to_datetime64()))
sigok = mkt & ~eod_b & ~contam & np.isfinite(ATR) & (ATR > 0)
sigok[:warm_i] = False
sigok[n - HMAX - TTLMAX - 2:] = False

# padded arrays for window building
PAD = HMAX + TTLMAX + 4
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
def mom(lb):
    if lb not in MOMS:
        MOMS[lb] = np.concatenate([np.full(lb, np.nan), C_[lb:] - C_[:-lb]])
    return MOMS[lb]
def donhi(N):
    return pd.Series(H_).rolling(N).max().shift(1).values
def donlo(N):
    return pd.Series(L_).rolling(N).min().shift(1).values

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
        ma = pd.Series(C_).rolling(man).mean().values
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
        us_open = np.where((nh >= 13.5) & (nh < 13.5 + 5 / 60))[0]
        for i0 in us_open:
            i1 = i0 + m_
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
        if cn >= 24:
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
    sq = pd.Series(rng).rolling(24).sum()
    sqref = sq.rolling(288, min_periods=100).mean()
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
        at = sigok & (nh >= hh) & (nh < hh + 5 / 60) & np.isfinite(m) & (m != 0)
        idx = thin(np.where(at)[0], spacing=100)
        if len(idx) < 30: continue
        side = np.sign(m[idx]).astype(np.int64)
        yield ("todmom", dict(h=hh, lb=lb), "M", idx, side, np.full(len(idx), np.nan))
    if ROOT in ("ES", "RTY", "YM", "GC", "CL"):
        dayrng = pd.Series(rng).rolling(390, min_periods=200).mean().values * 12
        prev_close = np.full(n, np.nan)
        last_rth_close = np.nan
        for i in range(n):
            if 19.9 <= nh[i] < 20.05: last_rth_close = C_[i]
            prev_close[i] = last_rth_close
        us_open = (nh >= 13.5) & (nh < 13.5 + 5 / 60)
        gapv = O - prev_close
        for g, mode in itertools.product([0.2, 0.3, 0.45, 0.6, 0.8, 1.0], ["fade", "go"]):
            sig = sigok & us_open & np.isfinite(prev_close) & np.isfinite(dayrng) & \
                  (np.abs(gapv) > g * dayrng) & (np.abs(gapv) < 5 * dayrng)
            idx = thin(np.where(sig)[0], spacing=100)
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
    # ================= MEGA3 FAMILIES (2026-08-01) =================
    cs = pd.Series(C_)
    def _ema(n): return cs.ewm(span=n, adjust=False).mean().values
    rng_ = H_ - L_
    body = np.abs(C_ - O)
    # --- RSI extremes (Wilder via EMA)
    delta = np.r_[0.0, np.diff(C_)]
    for n_ in (7, 14):
        up = pd.Series(np.maximum(delta, 0)).ewm(alpha=1/n_, adjust=False).mean().values
        dn = pd.Series(np.maximum(-delta, 0)).ewm(alpha=1/n_, adjust=False).mean().values
        rsi = 100 - 100 / (1 + up / np.maximum(dn, 1e-12))
        for th in (20.0, 25.0, 30.0):
            lo_sig = sigok & (rsi < th); hi_sig = sigok & (rsi > 100 - th)
            sig = lo_sig | hi_sig
            idx = thin(np.where(sig)[0])
            if len(idx) < 30: continue
            side = np.where(lo_sig[idx], 1, -1).astype(np.int64)
            yield ("rsirev", dict(per=n_, th=th), "M", idx, side, np.full(len(idx), np.nan))
    # --- Bollinger touch-fade (limit at band) + band-momentum continuation
    for n_, kk in ((20, 2.0), (50, 2.5)):
        ma_ = cs.rolling(n_).mean().values; sd_ = cs.rolling(n_).std().values
        up_b = ma_ + kk * sd_; lo_b = ma_ - kk * sd_
        b_lo = sigok & np.isfinite(lo_b) & (C_ < lo_b)
        b_up = sigok & np.isfinite(up_b) & (C_ > up_b)
        sig = b_lo | b_up
        idx = thin(np.where(sig)[0])
        if len(idx) >= 30:
            side = np.where(b_lo[idx], 1, -1).astype(np.int64)
            px = rnd(np.where(side > 0, lo_b[idx], up_b[idx]))
            yield ("bollrev", dict(per=n_, kk=kk), "L", idx, side, px)
            yield ("bollbrk", dict(per=n_, kk=kk), "M", idx, -side, np.full(len(idx), np.nan))
    # --- Keltner touch-fade
    e20 = _ema(20)
    for kk in (1.5, 2.5):
        up_k = e20 + kk * ATR; lo_k = e20 - kk * ATR
        b_lo = sigok & np.isfinite(lo_k) & (C_ < lo_k)
        b_up = sigok & np.isfinite(up_k) & (C_ > up_k)
        sig = b_lo | b_up
        idx = thin(np.where(sig)[0])
        if len(idx) < 30: continue
        side = np.where(b_lo[idx], 1, -1).astype(np.int64)
        px = rnd(np.where(side > 0, lo_k[idx], up_k[idx]))
        yield ("keltrev", dict(kk=kk), "L", idx, side, px)
    # --- MACD signal-line cross (magnitude floor)
    for f_, s_ in ((12, 26), (5, 20)):
        macd = _ema(f_) - _ema(s_)
        sigl = pd.Series(macd).ewm(span=9, adjust=False).mean().values
        d_ = macd - sigl
        xup = sigok & (d_ > 0) & (np.r_[0.0, d_[:-1]] <= 0) & (np.abs(macd) > 0.2 * ATR)
        xdn = sigok & (d_ < 0) & (np.r_[0.0, d_[:-1]] >= 0) & (np.abs(macd) > 0.2 * ATR)
        sig = xup | xdn
        idx = thin(np.where(sig)[0])
        if len(idx) < 30: continue
        side = np.where(xup[idx], 1, -1).astype(np.int64)
        yield ("macdx", dict(f=f_, s=s_), "M", idx, side, np.full(len(idx), np.nan))
    # --- Stochastic %K extreme cross
    hh14 = pd.Series(H_).rolling(14).max().values
    ll14 = pd.Series(L_).rolling(14).min().values
    kpc = 100 * (C_ - ll14) / np.maximum(hh14 - ll14, 1e-12)
    for th in (20.0, 10.0):
        xup = sigok & (kpc > th) & (np.r_[100.0, kpc[:-1]] <= th)
        xdn = sigok & (kpc < 100 - th) & (np.r_[0.0, kpc[:-1]] >= 100 - th)
        sig = xup | xdn
        idx = thin(np.where(sig)[0])
        if len(idx) < 30: continue
        side = np.where(xup[idx], 1, -1).astype(np.int64)
        yield ("stochx", dict(th=th), "M", idx, side, np.full(len(idx), np.nan))
    # --- typical-price z-score extremes (CCI-style)
    tp_ = (H_ + L_ + C_) / 3
    tz = (tp_ - pd.Series(tp_).rolling(20).mean().values) / \
         np.maximum(pd.Series(tp_).rolling(20).std().values, 1e-12)
    for th in (2.0, 2.5):
        sig = sigok & np.isfinite(tz) & (np.abs(tz) > th)
        idx = thin(np.where(sig)[0])
        if len(idx) < 30: continue
        side = -np.sign(tz[idx]).astype(np.int64)
        yield ("cciext", dict(th=th), "M", idx, side, np.full(len(idx), np.nan))
    # --- candle patterns
    pO = np.r_[np.nan, O[:-1]]; pC = np.r_[np.nan, C_[:-1]]
    m6_ = mom(6)
    bull_eng = sigok & (C_ > O) & (pC < pO) & (C_ > pO) & (O < pC) & (m6_ < -1.0 * ATR)
    bear_eng = sigok & (C_ < O) & (pC > pO) & (C_ < pO) & (O > pC) & (m6_ > 1.0 * ATR)
    sig = bull_eng | bear_eng
    idx = thin(np.where(sig)[0])
    if len(idx) >= 30:
        side = np.where(bull_eng[idx], 1, -1).astype(np.int64)
        yield ("engulf", dict(), "M", idx, side, np.full(len(idx), np.nan))
    lw = np.minimum(O, C_) - L_; uw = H_ - np.maximum(O, C_)
    ham = sigok & (lw > 2 * body) & (rng_ > 1.2 * ATR) & (m6_ < -1.0 * ATR)
    star = sigok & (uw > 2 * body) & (rng_ > 1.2 * ATR) & (m6_ > 1.0 * ATR)
    sig = ham | star
    idx = thin(np.where(sig)[0])
    if len(idx) >= 30:
        side = np.where(ham[idx], 1, -1).astype(np.int64)
        yield ("hammer", dict(), "M", idx, side, np.full(len(idx), np.nan))
    # --- inside-bar breakout (stop orders both sides)
    pH = np.r_[np.nan, H_[:-1]]; pL = np.r_[np.nan, L_[:-1]]
    inside = sigok & (H_ < pH) & (L_ > pL)
    for buf in (0.0, 0.25):
        ii = thin(np.where(inside)[0])
        if len(ii) < 30: continue
        idx = np.repeat(ii, 2)
        side = np.tile([1, -1], len(ii)).astype(np.int64)
        px = rnd(np.where(side > 0, pH[idx] + buf * ATR[idx], pL[idx] - buf * ATR[idx]))
        yield ("insidebrk", dict(buf=buf), "S", idx, side, px)
    # --- wide-bar close-at-extreme fade
    clv = (2 * C_ - H_ - L_) / np.maximum(rng_, 1e-12)
    sig = sigok & (rng_ > 2.0 * ATR) & (np.abs(clv) > 0.6)
    idx = thin(np.where(sig)[0])
    if len(idx) >= 30:
        side = -np.sign(clv[idx]).astype(np.int64)
        yield ("outsidefade", dict(), "M", idx, side, np.full(len(idx), np.nan))
    # --- prior-day high/low: touch-fade (limit AT level) and break (stop)
    pdh = pd.Series(H_).groupby(day_codes).max().shift(1)
    pdl = pd.Series(L_).groupby(day_codes).min().shift(1)
    PDH = pdh.reindex(day_codes).values; PDL = pdl.reindex(day_codes).values
    near_h = sigok & np.isfinite(PDH) & (H_ > PDH - 0.3 * ATR) & (C_ < PDH)
    near_l = sigok & np.isfinite(PDL) & (L_ < PDL + 0.3 * ATR) & (C_ > PDL)
    sig = near_h | near_l
    idx = thin(np.where(sig)[0])
    if len(idx) >= 30:
        side = np.where(near_h[idx], -1, 1).astype(np.int64)
        px = rnd(np.where(side < 0, PDH[idx], PDL[idx]))
        yield ("pdhfade", dict(), "L", idx, side, px)
    for buf in (0.0, 0.25):
        idx = thin(np.where(sig)[0])
        if len(idx) < 30: continue
        side = np.where(near_h[idx], 1, -1).astype(np.int64)
        px = rnd(np.where(side > 0, PDH[idx] + buf * ATR[idx], PDL[idx] - buf * ATR[idx]))
        yield ("pdhbrk", dict(buf=buf), "S", idx, side, px)
    # --- classic floor-pivot R1/S1 fade
    pc_ = pd.Series(C_).groupby(day_codes).last().shift(1)
    piv = (pdh + pdl + pc_) / 3
    R1 = (2 * piv - pdl).reindex(day_codes).values
    S1 = (2 * piv - pdh).reindex(day_codes).values
    nh_r = sigok & np.isfinite(R1) & (H_ > R1 - 0.3 * ATR) & (C_ < R1)
    nl_s = sigok & np.isfinite(S1) & (L_ < S1 + 0.3 * ATR) & (C_ > S1)
    sig = nh_r | nl_s
    idx = thin(np.where(sig)[0])
    if len(idx) >= 30:
        side = np.where(nh_r[idx], -1, 1).astype(np.int64)
        px = rnd(np.where(side < 0, R1[idx], S1[idx]))
        yield ("pivfade", dict(), "L", idx, side, px)
    # --- day-open reversion (drift back to the open)
    for kk in (1.5, 2.5):
        sig = sigok & np.isfinite(DAY_OPEN) & (np.abs(C_ - DAY_OPEN) > kk * ATR)
        idx = thin(np.where(sig)[0])
        if len(idx) < 30: continue
        side = -np.sign(C_[idx] - DAY_OPEN[idx]).astype(np.int64)
        yield ("dayopenrev", dict(kk=kk), "M", idx, side, np.full(len(idx), np.nan))
    # --- overnight / first-hour daily bias (continuation and reversal)
    pdo = pd.Series(O).groupby(day_codes).first().shift(1).reindex(day_codes).values
    pdc = pc_.reindex(day_codes).values
    at_open = sigok & (nh >= 22.0) & (nh < 22.0 + 5/60) & np.isfinite(pdc) & np.isfinite(pdo)
    for mode in ("cont", "rev"):
        idx = thin(np.where(at_open)[0], spacing=100)
        if len(idx) < 30: continue
        sd_ = np.sign(pdc[idx] - pdo[idx]).astype(np.int64)
        side = sd_ if mode == "cont" else -sd_
        ok_ = side != 0
        if ok_.sum() < 30: continue
        yield ("onbias", dict(mode=mode), "M", idx[ok_], side[ok_],
               np.full(int(ok_.sum()), np.nan))
    h1ref = np.where((nh >= 13.5) & (nh < 13.5 + 5/60), O, np.nan)
    h1ref = pd.Series(h1ref).groupby(day_codes).ffill().values
    at_h1 = sigok & (nh >= 14.5) & (nh < 14.5 + 5/60) & np.isfinite(h1ref)
    for mode in ("cont", "rev"):
        idx = thin(np.where(at_h1)[0], spacing=100)
        if len(idx) < 30: continue
        sd_ = np.sign(C_[idx] - h1ref[idx]).astype(np.int64)
        side = sd_ if mode == "cont" else -sd_
        ok_ = side != 0
        if ok_.sum() < 30: continue
        yield ("firsthr", dict(mode=mode), "M", idx[ok_], side[ok_],
               np.full(int(ok_.sum()), np.nan))
    # --- close-location-value persistence (order-flow proxy)
    clv12 = pd.Series(clv).rolling(12).mean().values
    for mode in ("with", "fade"):
        sig = sigok & np.isfinite(clv12) & (np.abs(clv12) > 0.45)
        idx = thin(np.where(sig)[0])
        if len(idx) < 30: continue
        sd_ = np.sign(clv12[idx]).astype(np.int64)
        side = sd_ if mode == "with" else -sd_
        yield ("clvper", dict(mode=mode), "M", idx, side, np.full(len(idx), np.nan))
    # --- wick-ratio fade
    wr_up = uw / np.maximum(rng_, 1e-12); wr_dn = lw / np.maximum(rng_, 1e-12)
    su = sigok & (wr_up > 0.65) & (m6_ > 0.5 * ATR) & (rng_ > 1.0 * ATR)
    sd2 = sigok & (wr_dn > 0.65) & (m6_ < -0.5 * ATR) & (rng_ > 1.0 * ATR)
    sig = su | sd2
    idx = thin(np.where(sig)[0])
    if len(idx) >= 30:
        side = np.where(su[idx], -1, 1).astype(np.int64)
        yield ("wickfade", dict(), "M", idx, side, np.full(len(idx), np.nan))
    # --- volume climax fade
    vmu = pd.Series(V_).rolling(48).mean().values
    vsd = pd.Series(V_).rolling(48).std().values
    vz = (V_ - vmu) / np.maximum(vsd, 1e-9)
    sig = sigok & np.isfinite(vz) & (vz > 3.0) & (rng_ > 2.0 * ATR) & (C_ != O)
    idx = thin(np.where(sig)[0])
    if len(idx) >= 30:
        side = -np.sign(C_[idx] - O[idx]).astype(np.int64)
        yield ("volclimax", dict(), "M", idx, side, np.full(len(idx), np.nan))
    # --- multi-timeframe aligned pullback (HTF trend + LTF impulse retrace)
    for lbH, lbL in ((144, 12), (288, 24)):
        mH = mom(lbH); mL = mom(lbL)
        sig = sigok & np.isfinite(mH) & np.isfinite(mL) & (np.abs(mH) > 2.0 * ATR) & \
              (np.sign(mH) == np.sign(mL)) & (np.abs(mL) > 1.0 * ATR)
        idx = thin(np.where(sig)[0])
        if len(idx) < 30: continue
        side = np.sign(mL[idx]).astype(np.int64)
        px = rnd(C_[idx] - 0.382 * mL[idx])
        yield ("htfalign", dict(lbH=lbH, lbL=lbL), "L", idx, side, px)


# ------------------------------------------------------- fills and outcomes
def resolve_fills(idx, side, px, etype, ttl):
    if etype == "M":
        fb = idx + 1
        epx = Op[fb] + TICK * side
        return fb, epx
    steps = np.arange(1, ttl + 1)
    bars = idx[:, None] + steps[None, :]
    if etype == "L":
        adverse = np.where(side[:, None] > 0, Lp[bars], Hp[bars])
        hit = (adverse * side[:, None]) <= (px * side)[:, None]
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

def outcomes(wins, fb, epx, side, a, sp_mult, rr, trail, Hbars, be=0.0):
    SLo, SHi, cm, Cw, j_end = wins
    E = len(fb)
    ent_s = epx * side
    sp = rnd(epx - sp_mult * a * side) * side
    if isinstance(rr, str):
        # ADAPTIVE TARGET: k x rolling-median MFE of this stream's prior
        # 60 events (shifted 1 = strictly causal). Fallback: 1.0x stop.
        kk = float(rr[1:])
        mfe = np.nanmax(SHi[:, 1:], axis=1) - ent_s
        rmed = pd.Series(mfe).rolling(60, min_periods=20).median().shift(1).values
        dist = np.where(np.isfinite(rmed) & (rmed > 0), kk * rmed, sp_mult * a)
        tp = rnd(epx + dist * side) * side
    else:
        tp = rnd(epx + rr * sp_mult * a * side) * side
    if trail > 0:
        line = np.empty_like(SLo)
        line[:, 0] = sp
        line[:, 1:] = np.maximum(sp[:, None], cm[:, :-1] - (trail * a)[:, None])
    else:
        line = np.broadcast_to(sp[:, None], SLo.shape).copy()
    if be > 0:
        # BREAK-EVEN MOVE: once price runs be x ATR in favour (bar j>=1),
        # stop can never be worse than entry from bar j+1 onward.
        be_hit = SHi >= (ent_s + be * a)[:, None]
        be_hit[:, 0] = False
        j_be = first_true(be_hit)
        js_ = np.arange(SLo.shape[1])
        after = js_[None, :] > np.minimum(j_be, BIG - 1)[:, None]
        line = np.where(after, np.maximum(line, ent_s[:, None]), line)
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
_MREV = dict(sp=[0.75, 1.0, 1.5, 2.0], rr=[0.5, 0.75, 1.0, "a0.75"],
             trail=[0.0], be=[0.0, 1.0], ttl=[1], H=[6, 12, 24])
_MCONT = dict(sp=[1.0, 1.5, 2.0], rr=[0.75, 1.0, 1.5, 2.0, "a1.0"],
              trail=[0.0, 2.5], be=[0.0, 1.0], ttl=[1], H=[12, 24, 48])
_LREV = dict(sp=[1.0, 1.5, 2.0, 2.5], rr=[0.5, 0.75, 1.0, "a0.75"],
             trail=[0.0, 2.5], be=[0.0, 1.0], ttl=[2, 3, 6], H=[12, 24, 48])
_SBRK = dict(sp=[1.0, 1.5, 2.0], rr=[1.0, 1.5, 2.0, "a1.0"],
             trail=[0.0, 2.5], be=[0.0, 1.0], ttl=[3, 6], H=[24, 48])
for _f in ("rsirev", "cciext", "outsidefade", "dayopenrev", "wickfade",
           "volclimax", "clvper", "stochx", "engulf", "hammer"):
    EXITS[_f] = _MREV
for _f in ("macdx", "onbias", "firsthr", "bollbrk"):
    EXITS[_f] = _MCONT
for _f in ("bollrev", "keltrev", "pdhfade", "pivfade"):
    EXITS[_f] = _LREV
for _f in ("insidebrk", "pdhbrk"):
    EXITS[_f] = _SBRK
EXITS["htfalign"] = dict(sp=[1.0, 1.5, 2.5], rr=[0.5, 0.75, 1.0, "a0.75"],
                         trail=[0.0, 2.5], be=[0.0, 1.0], ttl=[2, 3, 12], H=[12, 24, 48])
EXITS["fib"] = dict(EXITS["fib"], be=[0.0, 1.0])


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
    bias_with = (side * np.sign(np.where(np.isfinite(DAY_OPEN[idx]),
                                         C_[idx] - DAY_OPEN[idx], 0)) > 0).astype(np.int64)
    cell = (sess_cat[idx] << 5) | (trend_with << 4) | (vol_hi[idx] << 3) | \
           (vix_hi[idx] << 2) | (htf_up[idx] << 1) | bias_with
    for ttl in ex["ttl"]:
        fb, epx = resolve_fills(idx, side, px, etype, ttl)
        ok = fb >= 0
        if ok.sum() < 30: continue
        fbo, epo, sdo, ao, cello = fb[ok], epx[ok], side[ok], a_sig[ok], cell[ok]
        for Hbars in ex["H"]:
            wins = build_windows(fbo, sdo, Hbars)
            for sp_mult, rr, trail, be in itertools.product(
                    ex["sp"], ex["rr"], ex["trail"], ex.get("be", [0.0])):
                xj, xpx = outcomes(wins, fbo, epo, sdo, ao, sp_mult, rr, trail, Hbars, be)
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
                base_rows.append(dict(fam=fam, **pdict, etype=etype, ttl=int(ttl),
                                      H=int(Hbars), sp=float(sp_mult), rr=str(rr),
                                      trail=float(trail), be=float(be),
                                      wk=float(wk_mean[0]), ev=float(ev[0]),
                                      n=int(nt[0])))
                gate = (nt >= 150) & (wk_mean >= 25.0) & (poswk >= 0.55) & \
                       yr_ok & (o10 > 0) & (ev > 0)
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
                        fam=fam, **pdict, etype=etype, ttl=int(ttl), H=int(Hbars),
                        sp=float(sp_mult), rr=str(rr), trail=float(trail), be=float(be),
                        f_sess=combos[g][0], f_trend=combos[g][1],
                        f_vol=combos[g][2], f_vix=combos[g][3], f_htf=combos[g][4],
                        f_bias=combos[g][5],
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
    df_r = df_r.sort_values("score", ascending=False).head(4000)
    top = df_r.to_dict("records")
else:
    top = []

out = dict(root=ROOT, traded_as=TRADED_AS, pv=PV, tick=TICK, comm=COMM,
           margin=MARGIN, afford=bool(AFFORD), engine="pessimistic-vectorized-v3-deep", depth=DEPTH,
           n_bars=int(n), n_weeks=int(W), n_streams=int(n_streams),
           n_base=len(base_rows), n_cfg=int(n_cfg_total), n_gated=int(n_gated),
           elapsed_s=round(elapsed), top=top)
SUF = ("d" if DEPTH == 3 else "b") + (f"sh{SH_K}" if SHARD else "")
with gzip.open(f"{D}/s1c{SUF}_{ROOT}.json.gz", "wt") as f:
    json.dump(out, f)
bd = pd.DataFrame(base_rows)
if len(bd):
    np.savez_compressed(f"{D}/s1c{SUF}base_{ROOT}.npz", data=bd.to_records(index=False))
print(f"{ROOT}: saved {len(top)} top rows, {len(base_rows)} base rows -> s1{SUF}", flush=True)
