"""Round 37: NEW DIRECTION — daily-retrained ML over the tick feature
space, walking forward through the recent window. No hand-designed rule:
a HistGradientBoosting model is retrained EVERY DAY on the trailing 20
trading days and predicts the next day's 15-minute forward returns from
~24 features (multi-horizon returns, flow, big prints, vol state, range
position, VWAP dev, time encodings, and the NEW MES spread features).
Trades: |prediction| above the train-calibrated top-decile -> market
entry, 15m hold, tick-walked, flat 1 MNQ, $1.50/RT. Every day is
out-of-sample by construction.
"""
import glob, time
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

PT = 2.0
FEES = 1.50
TICK = 0.25
LAT_NS = 65_000_000
START = pd.Timestamp("2026-04-01", tz="UTC")
END = pd.Timestamp("2026-07-07", tz="UTC")
TRAIL = 20          # training days
HOLD = 15           # minutes
Q = 0.90            # trade when |pred| above this train quantile


def main():
    t0 = time.time()
    z = np.load("data/tick/ytd2026sz.npz")
    ts, px, sz = z["ts"], z["px"], z["sz"]
    n = len(ts)
    d = np.sign(np.diff(px, prepend=px[0]))
    m = (ts // 60_000_000_000) * 60_000_000_000
    big = np.where(sz >= 20, d * sz, 0.0)
    g = pd.DataFrame({"m": m, "px": px, "sz": sz, "iv": d * sz, "bg": big,
                      "pv": px * sz})
    b = g.groupby("m").agg(open=("px", "first"), high=("px", "max"),
                           low=("px", "min"), close=("px", "last"),
                           vol=("sz", "sum"), iv=("iv", "sum"),
                           bg=("bg", "sum"), nt=("px", "size"),
                           pv=("pv", "sum"))
    b.index = pd.to_datetime(b.index, utc=True)
    # MES 1s -> 1m close for spread features
    mes = pd.concat([pd.read_parquet(f)[["ts", "price"]]
                     for f in sorted(glob.glob(
                         "/tmp/claude-0/westicks/MESU6_2026*.parquet"))
                     if pd.read_parquet(f).shape[0] > 0], ignore_index=True)
    mm = (mes["ts"].to_numpy() // 60_000_000_000) * 60_000_000_000
    esb = pd.DataFrame({"m": mm, "px": mes["price"].to_numpy()}) \
        .groupby("m")["px"].last()
    esb.index = pd.to_datetime(esb.index, utc=True)
    b = b.join(esb.rename("es"), how="left")
    b["es"] = b["es"].ffill()
    print(f"bars {len(b):,}, es cover {b['es'].notna().mean()*100:.0f}% "
          f"({time.time()-t0:.0f}s)", flush=True)

    o = b["open"].to_numpy(); h = b["high"].to_numpy()
    l = b["low"].to_numpy(); c = b["close"].to_numpy()
    vol = b["vol"].to_numpy(); iv = b["iv"].to_numpy()
    bg = b["bg"].to_numpy(); nt = b["nt"].to_numpy(); pv = b["pv"].to_numpy()
    es = b["es"].to_numpy()
    idx = b.index; bts = idx.asi8 + 60_000_000_000; nb = len(c)
    hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0
    dk = idx.normalize()
    rth = (hrs >= 13.6) & (hrs < 20.65)     # leave room for the 15m exit
    r1 = c - np.roll(c, 1); r1[0] = 0
    tr = np.maximum(h - l, np.abs(r1))
    atr = pd.Series(tr).rolling(20).mean().to_numpy()

    def roll(x, k, fn="sum"):
        s = pd.Series(x)
        return getattr(s.rolling(k), fn)().to_numpy()

    F = {}
    for k in (3, 10, 30, 60):
        mk = c - np.roll(c, k); mk[:k] = 0
        F[f"ret{k}"] = mk / np.where(np.nan_to_num(atr) > 0, atr, np.inf)
    F["atr_ratio"] = atr / np.where(roll(tr, 120, "mean") > 0,
                                    roll(tr, 120, "mean"), np.inf)
    ias = roll(np.abs(iv), 30, "mean")
    F["flow10"] = roll(iv, 10) / np.where(ias > 0, ias, np.inf)
    F["flow3"] = roll(iv, 3) / np.where(ias > 0, ias, np.inf)
    F["big10"] = roll(bg, 10) / np.where(ias > 0, ias, np.inf)
    F["volr"] = vol / np.where(roll(vol, 30, "mean") > 0,
                               roll(vol, 30, "mean"), np.inf)
    F["ntr"] = nt / np.where(roll(nt, 30, "mean") > 0,
                             roll(nt, 30, "mean"), np.inf)
    dhi = pd.Series(h, index=idx).groupby(dk).cummax().to_numpy()
    dlo = pd.Series(l, index=idx).groupby(dk).cummin().to_numpy()
    F["rngpos"] = np.where(dhi > dlo, (c - dlo) / np.where(dhi > dlo,
                                                           dhi - dlo, 1), 0.5)
    dfv = pd.DataFrame({"d": dk, "pv": pv, "v": vol}, index=idx)
    cpv = dfv.groupby("d")["pv"].cumsum().to_numpy()
    cv = dfv.groupby("d")["v"].cumsum().to_numpy()
    vwap = np.where(cv > 0, cpv / cv, np.nan)
    F["vwapdev"] = (c - vwap) / np.where(np.nan_to_num(atr) > 0, atr, np.inf)
    F["hour_sin"] = np.sin(2 * np.pi * hrs / 24)
    F["hour_cos"] = np.cos(2 * np.pi * hrs / 24)
    up = (c > o).astype(float)
    F["runlen"] = roll(up, 4) - 2         # -2..2 net color of last 4 bars
    # MES spread features
    ratio = pd.Series(c / es).rolling(1200).median().to_numpy()
    sprd = c - es * np.nan_to_num(ratio, nan=np.nanmedian(c / es))
    sm = pd.Series(sprd).rolling(60).mean().to_numpy()
    ss = pd.Series(sprd).rolling(60).std().to_numpy()
    F["esz"] = (sprd - sm) / np.where(np.nan_to_num(ss) > 0, ss, np.inf)
    esr10 = es - np.roll(es, 10); esr10[:10] = 0
    F["esret10"] = esr10 / np.where(np.nan_to_num(atr) > 0, atr, np.inf)
    F["nq_minus_es10"] = F["ret10"] - F["esret10"]

    X = np.column_stack([np.nan_to_num(np.clip(v, -50, 50)) for v in F.values()])
    names = list(F.keys())
    y = (np.roll(c, -HOLD) - c)
    y[-HOLD:] = 0
    print(f"features: {X.shape} {names} ({time.time()-t0:.0f}s)", flush=True)

    udays = pd.DatetimeIndex(sorted(dk.unique()))
    udays = udays[(udays >= START - pd.Timedelta(days=45)) & (udays < END)]
    day_arr = dk.asi8

    out = []
    picked_feats = {}
    trade_days = [dd for dd in udays if dd >= START]
    for di, day in enumerate(trade_days):
        tr_days = udays[udays < day][-TRAIL:]
        if len(tr_days) < 10:
            continue
        tr_mask = np.isin(day_arr, tr_days.asi8) & rth
        te_mask = (day_arr == day.value) & rth
        if te_mask.sum() < 50 or tr_mask.sum() < 2000:
            continue
        model = HistGradientBoostingRegressor(
            max_iter=120, max_depth=4, learning_rate=0.08,
            l2_regularization=1.0, random_state=42)
        model.fit(X[tr_mask], y[tr_mask])
        pr_tr = model.predict(X[tr_mask])
        thr = np.quantile(np.abs(pr_tr), Q)
        pr = model.predict(X[te_mask])
        sig_local = np.where(pr > thr, 1, np.where(pr < -thr, -1, 0))
        loc = np.flatnonzero(te_mask)
        busy = 0
        for j, s in zip(loc, sig_local):
            if s == 0:
                continue
            t = bts[j]
            if t < busy:
                continue
            ei = np.searchsorted(ts, t + LAT_NS, side="left")
            if ei >= n:
                break
            e = px[ei] + TICK * s
            xj = np.searchsorted(ts, t + HOLD * 60_000_000_000 + LAT_NS,
                                 side="left")
            if xj >= n:
                break
            out.append((ts[xj], (px[xj] - TICK * s - e) * s * PT - FEES))
            busy = ts[xj]
        if di % 10 == 0:
            print(f"  day {di}/{len(trade_days)} {day.date()} "
                  f"trades so far {len(out)} ({time.time()-t0:.0f}s)",
                  flush=True)

    s = pd.Series([p for _, p in out],
                  index=pd.to_datetime([t for t, _ in out], utc=True))
    s.to_frame("pnl").to_csv("research/round37_ml_trades.csv")
    w = s.resample("W").sum(); cnt = s.resample("W").count()
    print("\n=== ML walk-forward weekly (every day out-of-sample) ===")
    for i in range(len(w)):
        if cnt.iloc[i] == 0:
            continue
        print(f"  {w.index[i].date()}  ${w.iloc[i]:8.0f}  ({cnt.iloc[i]:3d} tr)")
    wk = max(len(w[w != 0]), 1)
    print(f"\nTOTAL ${s.sum():.0f} | ${s.sum()/wk:.0f}/wk | {len(s)/wk:.1f} tr/wk"
          f" | ${s.mean():.2f}/trade | {(s>0).mean()*100:.0f}% win"
          f" | worst wk ${w[w!=0].min():.0f} | pos wks {(w[w!=0]>0).mean()*100:.0f}%")


if __name__ == "__main__":
    main()
