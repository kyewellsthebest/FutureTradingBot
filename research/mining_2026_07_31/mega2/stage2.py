"""MEGA2 STAGE-2: EXACT sequential replay of stage-1 survivors + robustness.

Semantics mirror the session's exact engines (fibreplay/verify4d) precisely:
one position per config, pending limit with TTL, cooldown = H bars from fill
(cd set at fill, decremented same bar -> next signal allowed at fill+H-1),
time exit when bars-held >= H (bh incremented from fill bar -> exit at
fill+H-1), EOD flat, same-bar target DENIED, same-bar stop ALLOWED, stop
beats target. Stop/market entries pay 1 tick; limit entries fill at limit.

Per survivor: full metric suite, neighbor-cliff check, slippage +1 tick
sensitivity, commission x1.5 sensitivity, Monte Carlo bootstrap, 4-fold
walk-forward on train, correlation to buy-and-hold.

Usage: stage2.py ROOT [--validate]
Reads s1_{ROOT}.json.gz; writes s2_{ROOT}.json
"""
import json, sys, os, gzip, time, tempfile, itertools
import numpy as np, pandas as pd

sys.path.insert(0, "/home/user/FutureTradingBot")
os.environ.setdefault("BOT_DATA_DIR", tempfile.mkdtemp())
os.environ.setdefault("POLYGON_API", "fake")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = sys.argv[1]
VALIDATE = "--validate" in sys.argv
D = os.path.dirname(os.path.abspath(__file__))

# import stage1's prepared arrays & stream machinery by exec (single source of truth)
import types
s1src = open(f"{D}/stage1.py").read()
s1src = s1src.split("# ------------------------------------------------------------ scoring loop")[0]
mod = types.ModuleType("s1core")
mod.__dict__["__file__"] = f"{D}/stage1.py"
sys.argv = [sys.argv[0], ROOT]
exec(compile(s1src, "stage1core", "exec"), mod.__dict__)

# --- stage-2 exactness patches (mirror fibreplay/verify4d ground truth) ---
# 1. NO signal thinning (the sequential engine enforces spacing naturally)
mod.thin = lambda idx, spacing=None: idx
# 2. roll-gap contamination window 64 bars (not 320) and 7-day warmup
_gap = (mod.ts.diff() > pd.Timedelta("3h")) & (mod.ts.shift(1).dt.weekday != 4)
_contam64 = _gap.rolling(64, min_periods=1).max().fillna(0).values.astype(bool)
_sigok = mod.mkt & ~mod.eod_b & ~_contam64 & np.isfinite(mod.ATR) & (mod.ATR > 0)
_warm7 = int(np.searchsorted(mod.ts.values,
             (mod.ts.iloc[0] + pd.Timedelta(days=7)).to_datetime64()))
_sigok[:_warm7] = False
_sigok[mod.n - mod.HMAX - mod.TTLMAX - 2:] = False
mod.sigok = _sigok

n = mod.n; ts = mod.ts
PV, TICK, COMM = mod.PV, mod.TICK, mod.COMM
Op, Hp, Lp, Cp = mod.Op, mod.Hp, mod.Lp, mod.Cp
ne = mod.ne
C_ = mod.C_
wk_codes, W = mod.wk_codes, mod.W
rnd = mod.rnd
first_true = mod.first_true
BIG = mod.BIG
sess_cat, vol_hi, vix_hi, MA_TREND = mod.sess_cat, mod.vol_hi, mod.vix_hi, mod.MA_TREND
TRAIN_END_TS = pd.Timestamp(mod.TRAIN_END)
OOS10_TS = pd.Timestamp(mod.OOS10)

# ---------------------------------------------------------- exact replay
def resolve_fills_exact(idx, side, px, etype, ttl):
    return mod.resolve_fills(idx, side, px, etype, ttl)

def outcomes_exact(fb, epx, side, a, sp_mult, rr, trail, H):
    """H bars incl fill bar; time exit at offset H-1 (verify4d semantics)."""
    Hoff = max(H - 1, 1)
    js = np.arange(0, Hoff + 1)
    bars = fb[:, None] + js[None, :]
    sgn = side[:, None].astype(np.float64)
    SLo = np.where(sgn > 0, Lp[bars], Hp[bars]) * sgn
    SHi = np.where(sgn > 0, Hp[bars], Lp[bars]) * sgn
    Cw = Cp[bars]
    j_end = np.minimum(Hoff, ne[np.clip(fb, 0, n - 1)] - fb)
    j_end = np.maximum(j_end, 1)
    sp = rnd(epx - sp_mult * a * side) * side
    tp = rnd(epx + rr * sp_mult * a * side) * side
    if trail > 0:
        cm = np.maximum.accumulate(np.where(np.isnan(SHi), -np.inf, SHi), axis=1)
        line = np.empty_like(SLo)
        line[:, 0] = sp
        line[:, 1:] = np.maximum(sp[:, None], cm[:, :-1] - (trail * a)[:, None])
    else:
        line = np.broadcast_to(sp[:, None], SLo.shape)
    j_stop = first_true(SLo <= line)
    tgt_hit = SHi >= tp[:, None]
    tgt_hit = np.array(tgt_hit); tgt_hit[:, 0] = False
    j_tgt = first_true(tgt_hit)
    take_stop = (j_stop <= j_tgt) & (j_stop <= j_end)
    take_tgt = ~take_stop & (j_tgt <= j_end)
    xj = np.where(take_stop, j_stop, np.where(take_tgt, j_tgt, j_end))
    rowi = np.arange(len(fb))
    line_at = line[rowi, np.minimum(xj, Hoff)] * side
    close_at = Cw[rowi, np.minimum(xj, Hoff)]
    xpx = np.where(take_stop, line_at,
          np.where(take_tgt, tp * side, close_at - TICK * side))
    bad = ~np.isfinite(xpx) | ~np.isfinite(epx) | (fb < 0)
    return np.where(bad, -1, xj), np.where(bad, np.nan, xpx)

def replay(idx, side, px, etype, a_sig, cfg, extra_slip=0.0, fmask=None):
    """exact sequential replay -> trades DataFrame"""
    if fmask is not None:
        idx, side, px, a_sig = idx[fmask], side[fmask], px[fmask], a_sig[fmask]
    if len(idx) == 0: return pd.DataFrame(columns=["ei", "xi", "pnl"])
    ttl = int(cfg["ttl"]); H = int(cfg["H"])
    fb, epx = resolve_fills_exact(idx, side, px, etype, ttl)
    if extra_slip > 0:
        epx = epx + extra_slip * TICK * side
    xj, xpx = outcomes_exact(fb, epx, side, a_sig,
                             float(cfg["sp"]), float(cfg["rr"]),
                             float(cfg["trail"]), H)
    if extra_slip > 0:
        xpx = np.where(xj >= 0, xpx - extra_slip * TICK * side, xpx)
    ei, xi, pnl = [], [], []
    free = -1
    ptr = 0
    E = len(idx)
    while ptr < E:
        if idx[ptr] < free:
            ptr = int(np.searchsorted(idx, free))
            continue
        e = ptr
        if fb[e] < 0:
            free = idx[e] + ttl
        else:
            if xj[e] < 0:
                free = fb[e] + H - 1
            else:
                ei.append(fb[e]); xi.append(fb[e] + xj[e])
                pnl.append((xpx[e] - epx[e]) * side[e] * PV - COMM)
                free = fb[e] + H - 1
        ptr += 1
    if not ei: return pd.DataFrame(columns=["ei", "xi", "pnl"])
    return pd.DataFrame(dict(ei=ts.values[np.array(ei)],
                             xi=ts.values[np.clip(np.array(xi), 0, n - 1)],
                             pnl=np.array(pnl)))

def fmask_for(idx, side, f_sess, f_trend, f_vol, f_vix):
    m = np.ones(len(idx), dtype=bool)
    sc = sess_cat[idx]
    if f_sess == "us": m &= sc == 2
    elif f_sess == "eu": m &= sc == 1
    elif f_sess == "asia": m &= sc == 0
    tw = (side * np.sign(np.where(np.isfinite(MA_TREND[idx]),
                                  C_[idx] - MA_TREND[idx], 0)) > 0)
    if f_trend == "with": m &= tw
    elif f_trend == "against": m &= ~tw
    if f_vol == "hi": m &= vol_hi[idx] == 1
    elif f_vol == "lo": m &= vol_hi[idx] == 0
    if f_vix == "hi": m &= vix_hi[idx] == 1
    elif f_vix == "lo": m &= vix_hi[idx] == 0
    return m

# ---------------------------------------------------------- metric suite
def metrics(trades):
    out = {}
    if len(trades) < 30: return None
    t = trades.copy()
    t["xt"] = pd.to_datetime(t.xi, utc=True)
    tr_ = t[t.xt < TRAIN_END_TS]
    oos = t[t.xt >= OOS10_TS]
    if len(tr_) < 30: return None
    wk = tr_.groupby(tr_.xt.dt.strftime("%G-W%V"), sort=True).pnl.sum()
    dv = tr_.groupby(tr_.xt.dt.date).pnl.sum()
    mo = tr_.groupby(tr_.xt.dt.strftime("%Y-%m")).pnl.sum()
    cum = wk.cumsum()
    dd = cum - cum.cummax()
    w = tr_[tr_.pnl > 0]; l = tr_[tr_.pnl <= 0]
    dsd = wk[wk < 0].std() if (wk < 0).sum() > 2 else wk.std()
    ann = wk.mean() * 52
    yr = tr_.groupby(tr_.xt.dt.year).pnl.sum()
    ldays = dv[dv < 0]
    # equity smoothness: R^2 of cum weekly equity vs time
    x = np.arange(len(cum)); y = cum.values
    if len(x) > 3 and y.std() > 0:
        r = np.corrcoef(x, y)[0, 1]; r2 = r * r
    else:
        r2 = 0.0
    owk = oos.groupby(oos.xt.dt.strftime("%G-W%V")).pnl.sum() if len(oos) else pd.Series(dtype=float)
    out.update(
        n=int(len(tr_)), net=round(float(tr_.pnl.sum())),
        wk=round(float(wk.mean()), 1), wk_med=round(float(wk.median()), 1),
        poswk=round(float((wk > 0).mean()), 3),
        sharpe=round(float(wk.mean() / (wk.std() + 1e-9)), 3),
        sortino=round(float(wk.mean() / (dsd + 1e-9)), 3),
        pf=round(float(w.pnl.sum() / max(-l.pnl.sum(), 1e-9)), 3),
        wr=round(float(len(w) / len(tr_)), 3),
        avg_win=round(float(w.pnl.mean()), 2) if len(w) else 0,
        avg_loss=round(float(l.pnl.mean()), 2) if len(l) else 0,
        ev=round(float(tr_.pnl.mean()), 2),
        maxdd=round(float(dd.min())), avgdd=round(float(dd[dd < 0].mean()) if (dd < 0).any() else 0),
        ulcer=round(float(np.sqrt((dd ** 2).mean())), 1),
        mar=round(float(ann / max(-dd.min(), 1e-9)), 2),
        recovery=round(float(tr_.pnl.sum() / max(-dd.min(), 1e-9)), 2),
        smooth_r2=round(float(r2), 3),
        worst_day=round(float(dv.min())), avg_lose_day=round(float(ldays.mean()) if len(ldays) else 0, 1),
        worst_wk=round(float(wk.min())), worst_mo=round(float(mo.min())),
        years={int(k): round(float(v)) for k, v in yr.items()},
        all_years_pos=bool((yr > 0).all()),
        n_wks=int(len(wk)), tr_wk=round(len(tr_) / max(len(wk), 1), 1),
        oos_n=int(len(oos)), oos_net=round(float(oos.pnl.sum())),
        oos_wk=round(float(owk.mean()), 1) if len(owk) else 0,
        oos_poswk=round(float((owk > 0).mean()), 3) if len(owk) else 0,
    )
    # walk-forward: 4 sequential folds of train weeks
    folds = np.array_split(wk.values, 4)
    out["wf_folds"] = [round(float(f.sum())) for f in folds]
    out["wf_all_pos"] = bool(all(f.sum() > 0 for f in folds))
    # buy-and-hold correlation (weekly $ change of 1 contract)
    wkC = pd.Series(C_, index=ts.values).groupby(wk_codes).last()
    bh = wkC.diff() * PV
    common = min(len(bh), len(wk))
    try:
        both = pd.concat([wk.reset_index(drop=True), bh.reset_index(drop=True)], axis=1).dropna()
        out["bh_corr"] = round(float(both.corr().iloc[0, 1]), 3) if len(both) > 10 else 0.0
    except Exception:
        out["bh_corr"] = 0.0
    # Monte Carlo bootstrap of weekly pnl
    rs = np.random.RandomState(42)
    sims = rs.choice(wk.values, size=(2000, 52), replace=True)
    annual = sims.sum(1)
    cums = np.cumsum(sims, axis=1)
    dds = (cums - np.maximum.accumulate(cums, axis=1)).min(1)
    out["mc_ann_p5"] = round(float(np.percentile(annual, 5)))
    out["mc_ann_p50"] = round(float(np.percentile(annual, 50)))
    out["mc_dd_p95"] = round(float(np.percentile(dds, 5)))
    return out

# --------------------------------------------------- neighbor cliff check
GRIDS = dict(
    fib=dict(lb=[6, 12, 24, 48, 96], k=[1.0, 1.5, 2.0, 3.0],
             pb=[0.236, 0.382, 0.5, 0.618, 0.786],
             sp=[0.75, 1.0, 1.5, 2.5], rr=[0.75, 1.0, 1.5, 2.5],
             ttl=[2, 3, 12], H=[12, 24, 48]),
    fade=dict(lb=[6, 12, 24, 48], k=[0.8, 1.2, 1.8, 2.5], dep=[0.25, 0.5, 1.0],
              sp=[0.75, 1.0, 1.5, 2.0], rr=[0.75, 1.0, 1.5], ttl=[2, 3], H=[6, 12, 24]),
    mapull=dict(man=[20, 50, 100, 200], lb=[3, 6, 12],
                sp=[0.75, 1.0, 1.5, 2.0], rr=[0.75, 1.0, 1.5], ttl=[2, 3], H=[6, 12, 24]),
    brk=dict(N=[24, 48, 96, 192, 288], buf=[0.0, 0.25],
             sp=[1.0, 1.5, 2.0, 3.0], rr=[1.0, 1.5, 2.0, 3.0],
             trail=[0.0, 2.5, 4.0], ttl=[3, 6, 12], H=[24, 48, 96]),
    failbrk=dict(N=[48, 96, 288], m=[1, 2], sp=[1.0, 1.5, 2.0], rr=[1.0, 1.5, 2.0],
                 H=[12, 24, 48]),
    orb=dict(m=[3, 6, 12], buf=[0.0, 0.25], sp=[0.75, 1.0, 1.5, 2.0],
             rr=[1.0, 1.5, 2.0, 3.0], ttl=[6, 12, 24], H=[12, 24, 48]),
    vwaprev=dict(g=[1.5, 2.0, 2.5, 3.0], sp=[0.75, 1.0, 1.5, 2.0],
                 rr=[0.75, 1.0, 1.5], H=[6, 12, 24]),
    vwaptrend=dict(lb=[12, 24], sp=[0.75, 1.0, 1.5, 2.0], rr=[0.75, 1.0, 1.5, 2.0],
                   ttl=[2, 3, 6], H=[12, 24, 48]),
    squeeze=dict(p=[0.6, 0.75], buf=[0.0, 0.25], sp=[1.0, 1.5, 2.0],
                 rr=[1.0, 1.5, 2.0, 3.0], ttl=[3, 6, 12], H=[24, 48, 96]),
    todmom=dict(h=[7.0, 13.5, 23.0], lb=[24, 72], sp=[1.0, 1.5, 2.0],
                rr=[1.0, 1.5, 2.0], H=[6, 12, 24]),
    gap=dict(g=[0.3, 0.6, 1.0], sp=[1.0, 1.5, 2.0], rr=[1.0, 1.5, 2.0], H=[12, 24, 48]),
)

def neighbor_stats(base_df, row):
    fam = row["fam"]
    grid = GRIDS.get(fam, {})
    sub = base_df[base_df.fam == fam]
    keys = [k for k in grid if k in sub.columns and k in row and not pd.isna(row.get(k))]
    match_all = np.ones(len(sub), dtype=bool)
    for k in keys:
        match_all &= (sub[k] == row[k]).values
    neigh_wk = []
    for k in keys:
        vals = grid[k]
        try:
            pos = vals.index(row[k])
        except ValueError:
            continue
        for step in (-1, 1):
            p2 = pos + step
            if p2 < 0 or p2 >= len(vals): continue
            m = np.ones(len(sub), dtype=bool)
            for k2 in keys:
                target = vals[p2] if k2 == k else row[k2]
                m &= (sub[k2] == target).values
            hit = sub[m]
            if len(hit): neigh_wk.append(float(hit.iloc[0].wk))
    if not neigh_wk: return dict(n_neigh=0, neigh_pos=0.0, neigh_med_wk=0.0)
    a = np.array(neigh_wk)
    return dict(n_neigh=len(a), neigh_pos=round(float((a > 0).mean()), 2),
                neigh_med_wk=round(float(np.median(a)), 1))

# --------------------------------------------------------------- driver
def stream_map():
    smap = {}
    for fam, pdict, etype, idx, side, px in mod.streams():
        key = (fam,) + tuple(sorted(pdict.items()))
        smap[key] = (etype, idx, side, px, mod.ATR[idx])
    return smap

def cfg_stream_key(r):
    fam = r["fam"]
    sig_keys = {"fib": ["lb", "k", "pb"], "fade": ["lb", "k", "dep"],
                "mapull": ["man", "lb"], "brk": ["N", "buf", "dir"],
                "failbrk": ["N", "m"], "orb": ["m", "buf"], "vwaprev": ["g"],
                "vwaptrend": ["lb"], "squeeze": ["p", "buf", "dir"],
                "todmom": ["h", "lb"], "gap": ["g", "mode"]}[fam]
    return (fam,) + tuple(sorted((k, r[k]) for k in sig_keys))

t0 = time.time()

if VALIDATE:
    smap = stream_map()
    gt = pd.read_csv(f"{D}/../mine/rates_{ROOT}.csv")
    gt["xt"] = pd.to_datetime(gt.xi, utc=True)
    sleeves = {
        "ZB#0": dict(fam="fib", lb=12, k=2.0, pb=0.382, sp=1.5, rr=1.0, trail=0.0, ttl=3, H=12),
        "ZB#1": dict(fam="fib", lb=24, k=1.5, pb=0.382, sp=1.5, rr=1.0, trail=0.0, ttl=12, H=12),
        "ZB#2": dict(fam="fib", lb=24, k=1.5, pb=0.5, sp=1.5, rr=1.0, trail=0.0, ttl=12, H=12),
    }
    for name, cfg in sleeves.items():
        key = cfg_stream_key(cfg)
        etype, idx, side, px, a_sig = smap[key]
        t = replay(idx, side, px, etype, a_sig, cfg)
        g = gt[gt.bot == name]
        print(f"{name}: stage2 n={len(t)} net={t.pnl.sum():+.0f} ev={t.pnl.mean():.2f} | "
              f"ground-truth n={len(g)} net={g.pnl.sum():+.0f} ev={g.pnl.mean():.2f}")
    sys.exit(0)

with gzip.open(f"{D}/s1_{ROOT}.json.gz", "rt") as f:
    s1 = json.load(f)
top = s1["top"]
if not top:
    json.dump(dict(root=ROOT, n_selected=0, survivors=[], note="no stage-1 passers"),
              open(f"{D}/s2_{ROOT}.json", "w"), indent=1)
    print(f"{ROOT}: no stage-1 passers"); sys.exit(0)

# selection: cap 3 filter-variants per base config, 60 per family, 220 total
sel = []
per_base, per_fam = {}, {}
for r in top:
    b = r["base_i"]; f = r["fam"]
    if per_base.get(b, 0) >= 3 or per_fam.get(f, 0) >= 60: continue
    per_base[b] = per_base.get(b, 0) + 1
    per_fam[f] = per_fam.get(f, 0) + 1
    sel.append(r)
    if len(sel) >= 220: break

try:
    bnp = np.load(f"{D}/s1base_{ROOT}.npz", allow_pickle=True)["data"]
    base_df = pd.DataFrame(bnp)
except Exception:
    base_df = pd.DataFrame()

smap = stream_map()
survivors = []
for r in sel:
    key = cfg_stream_key(r)
    if key not in smap: continue
    etype, idx, side, px, a_sig = smap[key]
    fm = fmask_for(idx, side, r["f_sess"], r["f_trend"], r["f_vol"], r["f_vix"])
    trades = replay(idx, side, px, etype, a_sig, r, fmask=fm)
    m = metrics(trades)
    if m is None: continue
    # gates on EXACT numbers (consistency-first)
    if not (m["n"] >= 200 and m["wk"] >= 30 and m["poswk"] >= 0.55 and
            m["pf"] >= 1.08 and m["all_years_pos"] and m["oos_net"] > 0 and
            m["wf_all_pos"]):
        continue
    slip = replay(idx, side, px, etype, a_sig, r, extra_slip=1.0, fmask=fm)
    ms = metrics(slip)
    m["slip1_wk"] = ms["wk"] if ms else 0
    t2 = trades.copy(); t2["pnl"] = t2.pnl - 0.5 * COMM
    mc_ = metrics(t2)
    m["comm150_wk"] = mc_["wk"] if mc_ else 0
    nb = neighbor_stats(base_df, r) if len(base_df) else dict(n_neigh=0, neigh_pos=0, neigh_med_wk=0)
    m.update(nb)
    cfg = {k: r[k] for k in r if k not in ("score", "base_i")}
    survivors.append(dict(cfg=cfg, **m))
    if len(survivors) >= 80: break

# final consistency ordering on exact metrics
if survivors:
    sf = pd.DataFrame([dict(i=i, sharpe=s["sharpe"], ulcer=s["ulcer"],
                            maxdd=s["maxdd"], ald=s["avg_lose_day"],
                            wwk=s["worst_wk"], oos=s["oos_wk"], n=s["n"],
                            pf=s["pf"], ev=s["ev"], wk=s["wk"],
                            r2=s["smooth_r2"], npos=s["neigh_pos"])
                       for i, s in enumerate(survivors)])
    def pr(s, hb=True): return s.rank(ascending=hb, pct=True)
    sc = (0.18 * pr(sf.sharpe) + 0.10 * pr(sf.r2) + 0.12 * pr(sf.ulcer, False) +
          0.12 * pr(sf.maxdd) + 0.10 * pr(sf.ald) + 0.10 * pr(sf.wwk) +
          0.08 * pr(sf.oos) + 0.06 * pr(np.log1p(sf.n)) + 0.05 * pr(sf.pf) +
          0.04 * pr(sf.npos) + 0.03 * pr(sf.ev) + 0.02 * pr(sf.wk))
    order = sc.sort_values(ascending=False).index
    survivors = [dict(rank=int(k) + 1, final_score=round(float(sc[i]), 4), **survivors[i])
                 for k, i in enumerate(order)]

json.dump(dict(root=ROOT, traded_as=s1["traded_as"], afford=s1["afford"],
               margin=s1["margin"], n_stage1_cfg=s1["n_cfg"],
               n_stage1_gated=s1["n_gated"], n_selected=len(sel),
               n_survivors=len(survivors), elapsed_s=round(time.time() - t0),
               engine="exact-sequential-pessimistic",
               survivors=survivors),
          open(f"{D}/s2_{ROOT}.json", "w"), indent=1)
print(f"{ROOT}: {len(sel)} selected -> {len(survivors)} exact survivors, "
      f"{time.time()-t0:.0f}s", flush=True)
