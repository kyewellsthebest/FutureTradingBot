"""Round 23: NEIGHBORHOOD DEEPENING of the verified vault families.
Instead of mining fresh noise, sweep the parameter neighborhoods of the
three strongest triple-gated legs — ONH (overnight premium), BWEXP
(band-width expansion) and DON (Donchian EOD) — for stronger variants.
Same honest engine (next-bar-open entry, slip, fees) and select/blind
protocol. Run with SIM_FEES=1.50 SIM_SLIP=0.5 (user cost grant)."""
import time
import numpy as np, pandas as pd
from research.midfreq_search import load_bars, resample
from research.midfreq_round4 import metrics_split, run_exit_ts


def sweep(df, name, sig, mode, p1, rows):
    o = df["open"].to_numpy(); h = df["high"].to_numpy()
    l = df["low"].to_numpy(); c = df["close"].to_numpy()
    idx = df.index; ts = idx.asi8; years = idx.year.to_numpy()
    tr = np.maximum(h - l, np.abs(c - np.roll(c, 1)))
    atr = pd.Series(tr).rolling(20).mean().to_numpy()
    ys, ps, tss = run_exit_ts(o, h, l, c, atr, ts, years, sig, mode, p1, 0, 400)
    m = metrics_split(idx.asi8, years, ps, tss)
    if m:
        rows.append({"name": name, **m})


def main():
    t0 = time.time()
    base = load_bars()
    rows = []

    # ---------- ONH: overnight premium (long at T0, hold H bars of 15m) ----
    df = resample(base, "15min")
    idx = df.index
    hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0
    dow = np.asarray(idx.dayofweek)
    for t0e in (19.75, 20.0, 20.25, 20.5, 20.75):
        base_sig = ((hrs >= t0e) & (hrs < t0e + 0.25)).astype(np.int8)
        for hold in (30, 50, 65, 80):
            for dtag, dmask in (("all", np.ones(len(idx), bool)),
                                ("noFri", dow != 4), ("noMon", dow != 0)):
                sig = np.where(dmask, base_sig, 0).astype(np.int8)
                sweep(df, f"ONH_t{t0e}_h{hold}_{dtag}", sig, "time", hold, rows)
    print(f"ONH swept ({time.time()-t0:.0f}s)", flush=True)

    # ---------- BWEXP: band-width expansion --------------------------------
    for tf in ("3min", "5min"):
        df = resample(base, tf)
        idx = df.index
        o = df["open"].to_numpy(); c = df["close"].to_numpy()
        hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0
        cs = pd.Series(c, index=idx)
        sd20 = cs.rolling(20).std()
        bw = (4 * sd20).to_numpy()
        up = c > o; dn = c < o
        rth = (hrs >= 13.5) & (hrs < 20.9)
        for k in (1.3, 1.5, 1.8, 2.2):
            for d in (10, 20):
                exp_ = bw > k * np.roll(bw, d)
                exp_[:d + 20] = False
                for stag, smask in (("rth", rth), ("all", np.ones(len(c), bool))):
                    sig = np.where(exp_ & up & smask, 1,
                                   np.where(exp_ & dn & smask, -1, 0)).astype(np.int8)
                    for hold in (20, 40, 60):
                        sweep(df, f"BWEXP{tf}_k{k}_d{d}_{stag}_t{hold}",
                              sig, "time", hold, rows)
                    sweep(df, f"BWEXP{tf}_k{k}_d{d}_{stag}_tr2",
                          sig, "trail", 2.0, rows)
        print(f"BWEXP {tf} swept ({time.time()-t0:.0f}s)", flush=True)

    # ---------- DON: Donchian breakout EOD window --------------------------
    for tf in ("15min", "30min"):
        df = resample(base, tf)
        idx = df.index
        h_ = df["high"].to_numpy(); l_ = df["low"].to_numpy()
        c = df["close"].to_numpy()
        hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0
        for lb in (8, 12, 16, 20):
            dh = pd.Series(h_).rolling(lb).max().shift(1).to_numpy()
            dl = pd.Series(l_).rolling(lb).min().shift(1).to_numpy()
            for wlo, whi, wtag in ((14.5, 20.92, "std"), (13.5, 20.92, "wide"),
                                   (16.0, 20.92, "late")):
                win = (hrs >= wlo) & (hrs < whi)
                sig = np.where(win & (c > dh), 1,
                               np.where(win & (c < dl), -1, 0)).astype(np.int8)
                for hold in (40, 80, 120):
                    sweep(df, f"DON{tf}_lb{lb}_{wtag}_t{hold}",
                          sig, "time", hold, rows)
                sweep(df, f"DON{tf}_lb{lb}_{wtag}_tr2", sig, "trail", 2.0, rows)
        print(f"DON {tf} swept ({time.time()-t0:.0f}s)", flush=True)

    out = pd.DataFrame(rows)
    out.to_csv("research/round23_deepen.csv", index=False)
    cols = ["name", "sel_usd_wk", "blind_usd_wk", "trades_wk", "win_pct"]
    print(f"\n{len(out)} variants ({time.time()-t0:.0f}s)")
    print("\nTOP 20 by SELECT $/wk:")
    print(out.sort_values("sel_usd_wk", ascending=False)[cols]
          .head(20).to_string(index=False))
    ok = out[(out.sel_usd_wk > 0) & (out.blind_usd_wk > 0)]
    ok = ok.sort_values("blind_usd_wk", ascending=False)
    print(f"\npositive BOTH windows: {len(ok)}")
    print(ok[cols].head(25).to_string(index=False))


if __name__ == "__main__":
    main()
