"""Round 7: overnight premium, volatility breakout, two-TF pullback,
last-hour drift. Same protocol: select 23-24, blind 25-26."""
import sys, time
import numpy as np, pandas as pd
from research.midfreq_search import load_bars, resample
from research.midfreq_round4 import metrics_split, run_exit_ts

def main():
    base = load_bars()
    rows = []
    d_close = base["close"].resample("1D").last().dropna()
    d_atr = (base["high"].resample("1D").max()
             - base["low"].resample("1D").min()).rolling(14).mean().shift(1)
    d_mom5 = d_close.diff(5).shift(1)   # 5-day momentum, known yesterday

    for tf in ("5min", "15min"):
        df = resample(base, tf)
        o = df["open"].to_numpy(); h = df["high"].to_numpy()
        l = df["low"].to_numpy(); c = df["close"].to_numpy()
        idx = df.index; ts = idx.asi8
        hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0
        years = idx.year.to_numpy(); dk = idx.normalize()
        cs = pd.Series(c, index=idx)
        tr = np.maximum(h - l, np.abs(c - np.roll(c, 1)))
        atr = pd.Series(tr).rolling(20).mean().to_numpy()
        allm = np.ones(len(c), bool)
        atr_d = dk.map(d_atr).to_numpy(float)
        mom_d = dk.map(d_mom5).to_numpy(float)
        opn = pd.Series(np.where((hrs >= 13.5) & (hrs < 13.6), o, np.nan),
                        index=idx).groupby(dk).transform("max").to_numpy()

        fams = {}
        at_close = (hrs >= 20.75) & (hrs < 20.92)
        # ONH: overnight hold, optionally gated by daily momentum
        fams["ONH_long"] = (at_close, np.zeros(len(c), bool))
        fams["ONH_momo"] = (at_close & (mom_d > 0), at_close & (mom_d < 0))
        # VBO: open +/- k * daily ATR breakout (Larry Williams style)
        for k in (0.4, 0.7):
            up_lvl = opn + k * atr_d
            dn_lvl = opn - k * atr_d
            in_rth = (hrs >= 13.6) & (hrs < 20.5)
            fams[f"VBO_k{k}"] = (in_rth & (c > up_lvl), in_rth & (c < dn_lvl))
        # TTF: 15m-equivalent trend (EMA60 slope) + pullback trigger
        ema60 = cs.ewm(span=60, adjust=False).mean()
        slope = (ema60 - ema60.shift(8)).to_numpy()
        ema20 = cs.ewm(span=20, adjust=False).mean().to_numpy()
        fams["TTF"] = ((slope > 0) & (l <= ema20) & (c > ema20),
                       (slope < 0) & (h >= ema20) & (c < ema20))
        # LHD: last-hour drift continuation (19:55+, day direction)
        late = (hrs >= 19.9) & (hrs < 20.2)
        daymove = c - opn
        for g in (20, 50):
            fams[f"LHD_g{g}"] = (late & (daymove > g), late & (daymove < -g))

        for fname, (rl, rs_) in fams.items():
            for mode, p1s in (("time", (16, 40, 65)), ("trail", (2.5, 4.0))):
                for p1 in p1s:
                    for p2 in (0, 25):
                        sig = np.where(np.nan_to_num(rl), 1,
                                       np.where(np.nan_to_num(rs_), -1, 0))
                        ys, ps, tss = run_exit_ts(o, h, l, c, atr, ts,
                                                  years, sig, mode, p1, p2,
                                                  90 if tf == "15min" else 260)
                        m = metrics_split(idx, ys, ps, tss)
                        if m:
                            rows.append({"name": f"{fname}_{tf}_{mode}{p1}h{p2}",
                                         "family": fname.split("_")[0],
                                         "tf": tf, **m})
        print(f"[{tf}] cum={len(rows)}", flush=True)

    df = pd.DataFrame(rows)
    df.to_csv("research/midfreq_results7.csv", index=False)
    sel = df[df.sel_total > 0].sort_values("sel_usd_wk", ascending=False)
    cols = ["name", "sel_usd_wk", "blind_usd_wk", "trades_wk", "win_pct"]
    both = sel[sel.blind_usd_wk > 0]
    print(f"\npositive BOTH windows: {len(both)}; top 15:")
    print(both[cols].head(15).to_string(index=False))

if __name__ == "__main__":
    main()
