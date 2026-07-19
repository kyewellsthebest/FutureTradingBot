"""Round 73: THE GAMMA MAP - first genuinely new information source.
2 years of QQQ option daily bars (132k contracts) -> reconstructed
dealer-gamma proxy -> tested against BP-Final's daily P&L over the
same 2 years. All causal joins use PRIOR-day gamma (tradable form).

Build: underlying via put-call parity per (day, near expiries);
IV via vectorized BS bisection (vol>0, T<=60d rows); gamma from BS;
net gamma proxy NGP = sum gamma*volume*100*(call +1 / put -1);
flip distance + pin strike per day. Volume-weighted (no historical
OI exists anywhere) - the 30-snapshot true-OI pile will confirm.
Tests: BP daily P&L (fade champion, faithful fills, 2024-07 ->
2026-07) split by lag-1 NGP terciles + sign; day-range (vol) by NGP;
bootstrap significance. Map saved for round 74 level strategies.
"""
import glob, json, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, "research")
from round63_transfer import build, sim_bp
import pyarrow.parquet as pq

R_RATE = 0.04
RNG = np.random.default_rng(73)


def norm_pdf(x):
    return np.exp(-0.5 * x * x) / np.sqrt(2 * np.pi)


def norm_cdf(x):
    from scipy.special import erf
    return 0.5 * (1 + erf(x / np.sqrt(2)))


def bs_price(S, K, T, sig, is_call):
    d1 = (np.log(S / K) + (R_RATE + 0.5 * sig * sig) * T) \
        / (sig * np.sqrt(T))
    d2 = d1 - sig * np.sqrt(T)
    c = S * norm_cdf(d1) - K * np.exp(-R_RATE * T) * norm_cdf(d2)
    return np.where(is_call, c,
                    c - S + K * np.exp(-R_RATE * T))


def build_gamma_map():
    df = pd.concat([pd.read_parquet(f) for f in sorted(
        glob.glob("/tmp/claude-0/opthist/OPTHIST_QQQ_*.parquet"))],
        ignore_index=True)
    df["dt"] = pd.to_datetime(df["date"], unit="ms").dt.normalize()
    df["exp"] = pd.to_datetime(df["expiry"])
    df["T"] = (df["exp"] - df["dt"]).dt.days.clip(lower=0) / 365.0 \
        + 0.5 / 365.0
    df["is_call"] = df["type"] == "call"
    # ---- underlying per day via put-call parity (near expiries)
    near = df[df["T"] <= 45 / 365].copy()
    piv = near.pivot_table(index=["dt", "exp", "strike"],
                           columns="type", values="close",
                           aggfunc="first").dropna()
    piv = piv.reset_index()
    piv["S_est"] = piv["strike"] + piv["call"] - piv["put"]
    piv["moneyness"] = np.abs(piv["call"] - piv["put"])
    piv = piv.sort_values("moneyness").groupby("dt").head(15)
    S_day = piv.groupby("dt")["S_est"].median()
    print(f"underlying inferred for {len(S_day)} days "
          f"({S_day.iloc[0]:.1f} -> {S_day.iloc[-1]:.1f})", flush=True)
    # ---- IV inversion on liquid, near-dated rows
    w = df[(df["volume"] > 0) & (df["T"] <= 60 / 365)
           & df["close"].notna()].copy()
    w["S"] = w["dt"].map(S_day)
    w = w[w["S"].notna() & (w["close"] > 0.005)]
    w = w[(w["strike"] > 0.5 * w["S"]) & (w["strike"] < 1.5 * w["S"])]
    S, K, T = (w["S"].to_numpy(), w["strike"].to_numpy(),
               w["T"].to_numpy())
    P, isc = w["close"].to_numpy(), w["is_call"].to_numpy()
    lo = np.full(len(w), 0.01); hi = np.full(len(w), 4.0)
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        pm = bs_price(S, K, T, mid, isc)
        too_high = pm > P
        hi = np.where(too_high, mid, hi)
        lo = np.where(too_high, lo, mid)
    iv = 0.5 * (lo + hi)
    ok = (iv > 0.011) & (iv < 3.99)
    w = w.iloc[np.flatnonzero(ok)]
    iv = iv[ok]; S, K, T = S[ok], K[ok], T[ok]
    d1 = (np.log(S / K) + (R_RATE + 0.5 * iv * iv) * T) \
        / (iv * np.sqrt(T))
    gamma = norm_pdf(d1) / (S * iv * np.sqrt(T))
    sign = np.where(w["is_call"].to_numpy(), 1.0, -1.0)
    w = w.assign(gsig=gamma * w["volume"].to_numpy() * 100 * sign,
                 gabs=gamma * w["volume"].to_numpy() * 100)
    print(f"IV inverted on {len(w):,} liquid contract-days",
          flush=True)
    # ---- per-day aggregates
    days = []
    for d, g in w.groupby("dt"):
        Sd = S_day[d]
        ngp = g["gsig"].sum()
        prof = g.groupby("strike")["gsig"].sum().sort_index()
        cum = prof.cumsum()
        below = cum[cum.index <= Sd]
        flips = prof.index[np.flatnonzero(np.diff(np.sign(
            cum.to_numpy())))]
        flip = float(flips[np.argmin(np.abs(flips - Sd))]) \
            if len(flips) else np.nan
        nearm = g[np.abs(g["strike"] - Sd) / Sd < 0.02]
        pin = float(nearm.groupby("strike")["gabs"].sum().idxmax()) \
            if len(nearm) else np.nan
        days.append(dict(dt=str(d.date()), S=float(Sd),
                         ngp=float(ngp), flip=flip, pin=pin,
                         flip_dist=float((Sd - flip) / Sd)
                         if np.isfinite(flip) else np.nan))
    M = pd.DataFrame(days).set_index("dt")
    M.to_csv("research/gexmap_daily.csv")
    print(f"gamma map: {len(M)} days saved", flush=True)
    return M


def bp_daily_pnl():
    """Champion fade daily P&L, Jul 2024 -> Jul 2026."""
    daily = {}
    # history chunks (2024H2, 2025) from 2.5y parquet
    pf = pq.ParquetFile("data/tick/nq_ticks_2p5y.parquet")
    buckets = {}
    for batch in pf.iter_batches(batch_size=8_000_000,
                                 columns=["ts", "price"]):
        bt = batch.column("ts").to_numpy()
        bp_ = batch.column("price").to_numpy().astype(np.float32)
        keep = bt >= 1_721_000_000_000_000_000        # ~2024-07-15
        bt, bp_ = bt[keep], bp_[keep]
        if not len(bt):
            continue
        yrs = bt // 31_536_000_000_000_000
        for y in np.unique(yrs):
            m_ = yrs == y
            buckets.setdefault(int(y), []).append((bt[m_], bp_[m_]))
    import gc
    for y in sorted(buckets):
        ts = np.concatenate([a for a, _ in buckets[y]])
        px = np.concatenate([b for _, b in buckets[y]]) \
            .astype(np.float64)
        buckets[y] = None; gc.collect()
        o = np.argsort(ts, kind="stable")
        ts, px = ts[o], px[o]
        wd = (ts // 86_400_000_000_000 + 4) % 7
        keep = np.isfinite(px) & (wd < 5)
        ts, px = ts[keep], px[keep]
        if len(ts) < 500_000:
            continue
        C = build(ts, px)
        p_arr, t_arr = sim_trades(ts, px, C)
        sr = pd.Series(p_arr, index=pd.to_datetime(t_arr, utc=True))
        for d, v in sr.resample("D").sum().items():
            if v != 0:
                daily[str(d.date())] = daily.get(
                    str(d.date()), 0) + float(v)
        del ts, px, C; gc.collect()
        print(f"  hist chunk done ({y})", flush=True)
    # 2026 tape
    import round54_clock as K
    K.build_tape()
    ts, px = K.D["ts"], K.D["px"]
    C = build(ts, px)
    p_arr, t_arr = sim_trades(ts, px, C)
    sr = pd.Series(p_arr, index=pd.to_datetime(t_arr, utc=True))
    for d, v in sr.resample("D").sum().items():
        if v != 0:
            daily[str(d.date())] = daily.get(str(d.date()), 0) \
                + float(v)
    return pd.Series(daily).sort_index()


def sim_trades(ts, px, C):
    s = sim_bp(ts, px, C, 2.0, 0.25, 1.0, 60.0)
    return s.to_numpy(), s.index.asi8


def split_test(bp, M, col, name, lag):
    x = M[col].shift(lag).reindex(bp.index)
    m = x.notna() & bp.notna()
    x, y = x[m], bp[m]
    if len(y) < 60:
        print(f"{name}: n={len(y)} too thin"); return
    q1, q2 = x.quantile([1/3, 2/3])
    lo, mid, hi = y[x <= q1], y[(x > q1) & (x <= q2)], y[x > q2]
    def bt(a, b):
        ma = RNG.choice(a, (20000, len(a))).mean(1)
        mb = RNG.choice(b, (20000, len(b))).mean(1)
        return float((ma > mb).mean())
    p = bt(hi.to_numpy(), lo.to_numpy())
    print(f"{name} (lag {lag}):")
    for tag, arr in (("low ", lo), ("mid ", mid), ("high", hi)):
        print(f"  {tag} n={len(arr):>3}  avg day {arr.mean():+8.2f}"
              f"  pos% {(arr>0).mean()*100:3.0f}")
    print(f"  bootstrap P(high beats low) = {p:.3f}"
          f"{'  SIGNIFICANT' if p > 0.975 or p < 0.025 else ''}",
          flush=True)


def main():
    t0 = time.time()
    M = build_gamma_map()
    print(f"({time.time()-t0:.0f}s) building BP daily P&L...",
          flush=True)
    bp = bp_daily_pnl()
    bp.index = pd.Index(bp.index.astype(str))
    print(f"BP daily P&L days: {len(bp)} "
          f"({time.time()-t0:.0f}s)\n", flush=True)
    ov = M.index.intersection(bp.index)
    print(f"overlap days: {len(ov)}\n==== TESTS ====", flush=True)
    for lag in (1, 0):
        split_test(bp, M, "ngp", "NGP net-gamma proxy", lag)
    split_test(bp, M, "flip_dist", "distance above flip", 1)
    # vol check: does NGP predict range (mechanism sanity)
    return_ = M["S"].pct_change().abs() * 100
    x = M["ngp"].shift(1).reindex(return_.index)
    m = x.notna() & return_.notna()
    from scipy.stats import spearmanr
    ic = spearmanr(x[m], return_[m]).statistic
    print(f"\nmechanism: corr(lag-1 NGP, |daily move|) = {ic:+.3f} "
          f"(theory says NEGATIVE: high gamma pins the market)",
          flush=True)
    print(f"\nDONE ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
