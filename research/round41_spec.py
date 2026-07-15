"""Round 41: THE SPEC HUNT. User target: >=90% positive weeks, worst
single day > -$500, >=$1,500/wk at 1-3 MNQ. Never-tested territory:
the JOINT grid of validated overlays on the FADESZ+P champion —
each was only ever tested alone.
Dimensions:
  entry threshold a in {1.2, 1.5}
  ladder in {1/2/3, 1/2/2, cap2 (1/2)}
  FVOL top-decile action in {none, cap1, skip}
  day-stop (no new entries once day P&L <=) in {none, -350}
  disaster guard in {100pt, 60pt} (tick-walked trade-through + slip)
  neg-day quality gate in {off, on} (once day<0, only 2x+ magnitude
    signals may trade)
= 144 configs, tick-walked passive fills, $1.50/RT.
Metrics: since-Mar $/wk, %pos weeks, worst day, p5 day, worst week.
SPEC PASS = pos_wk>=88 & worst_day>=-520 & usd_wk>=1400.
"""
import time
import numpy as np, pandas as pd

PT = 2.0
FEES = 1.50
TICK = 0.25
LAT_NS = 65_000_000
STOP_SLIP = 0.25
MAR = pd.Timestamp("2026-03-01", tz="UTC")
END = pd.Timestamp("2026-07-07", tz="UTC")
HN = lambda m: int(m * 60_000_000_000)


def main():
    t0 = time.time()
    z = np.load("data/tick/ytd2026sz.npz")
    ts, px, sz = z["ts"], z["px"], z["sz"]
    n = len(ts)
    d = np.sign(np.diff(px, prepend=px[0]))
    m = (ts // 60_000_000_000) * 60_000_000_000
    g = pd.DataFrame({"m": m, "px": px, "iv": d * sz})
    b = g.groupby("m").agg(open=("px", "first"), high=("px", "max"),
                           low=("px", "min"), close=("px", "last"),
                           iv=("iv", "sum"))
    b.index = pd.to_datetime(b.index, utc=True)
    o, h, l, c = (b[k].to_numpy() for k in ("open", "high", "low", "close"))
    iv = b["iv"].to_numpy()
    idx = b.index; bts = idx.asi8 + 60_000_000_000; nb = len(c)
    hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0
    dk = idx.normalize(); days = dk.asi8
    skip30 = (hrs >= 14.0) & (hrs < 20.9)
    rth = (hrs >= 13.5) & (hrs < 20.9)
    r1 = c - np.roll(c, 1); r1[0] = 0
    tr = np.maximum(h - l, np.abs(r1))
    atr = pd.Series(tr).rolling(20).mean().to_numpy()
    mom10 = c - np.roll(c, 10); mom10[:10] = 0
    fmag = np.abs(mom10) / np.where(np.nan_to_num(atr) > 0, atr, np.inf)
    fvol = pd.Series(np.abs(iv)).rolling(120).std().to_numpy()
    fvol_hi = fvol > np.nanquantile(fvol[rth], 0.9)

    def run(a_, ladder, fvol_mode, day_stop, disaster, qgate):
        thr = a_ * np.nan_to_num(atr, nan=np.inf)
        sig = np.where((mom10 < -thr) & skip30, 1,
                       np.where((mom10 > thr) & skip30, -1, 0))
        if ladder == "123":
            qbase = np.where(fmag >= 3 * a_ / 1.2, 3,
                             np.where(fmag >= 2 * a_ / 1.2, 2, 1))
        elif ladder == "122":
            qbase = np.where(fmag >= 2 * a_ / 1.2, 2, 1)
        else:  # cap2
            qbase = np.where(fmag >= 2.5 * a_ / 1.2, 2, 1)
        qbase = qbase.astype(int)
        out = []
        busy = 0
        i = 0
        cur_day = -1
        day_pnl = 0.0
        while i < nb - 2:
            s = sig[i]
            if s == 0 or bts[i] < busy:
                i += 1; continue
            if days[i] != cur_day:
                cur_day = days[i]; day_pnl = 0.0
            if day_stop is not None and day_pnl <= day_stop:
                i += 1; continue
            q = qbase[i]
            if qgate and day_pnl < 0 and fmag[i] < 2 * a_ / 1.2:
                i += 1; continue
            if fvol_mode == "cap1" and fvol_hi[i]:
                q = 1
            elif fvol_mode == "skip" and fvol_hi[i]:
                i += 1; continue
            L = c[i] - 1.0 * s
            a0 = np.searchsorted(ts, bts[i] + LAT_NS, "left")
            a1 = np.searchsorted(ts, bts[i] + HN(3), "left")
            if a0 >= n: break
            seg = px[a0:a1]
            th_ = np.flatnonzero(seg * s < (L - TICK * s) * s + 1e-9)
            if not len(th_):
                i += 1; continue
            fi = a0 + th_[0]
            xe = np.searchsorted(ts, ts[fi] + HN(15) + LAT_NS, "left")
            if xe >= n: break
            fill = None; k_exit = xe
            stop_lvl = L - disaster * s
            seg2 = px[fi + 1:xe]
            if len(seg2):
                sh = np.flatnonzero(seg2 * s <= stop_lvl * s + 1e-9)
                if len(sh):
                    k_exit = fi + 1 + int(sh[0])
                    raw = min(px[k_exit], stop_lvl) if s > 0 else max(px[k_exit], stop_lvl)
                    fill = raw - STOP_SLIP * s
            if fill is None:
                fill = px[xe] - TICK * s
                k_exit = xe
            pnl = ((fill - L) * s * PT - FEES) * q
            out.append((ts[k_exit], pnl))
            day_pnl += pnl
            busy = ts[k_exit]
            i += 1
        return out

    def stats(out):
        s = pd.Series([p for _, p in out],
                      index=pd.to_datetime([t for t, _ in out], utc=True))
        s = s[(s.index >= MAR) & (s.index < END)]
        if len(s) < 100:
            return None
        wk = s.resample("W").sum(); wk = wk[wk != 0]
        dy = s.resample("D").sum(); dy = dy[dy != 0]
        return {"usd_wk": round(s.sum() / max(len(wk), 1), 0),
                "pos_wk": round((wk > 0).mean() * 100),
                "worst_day": round(dy.min(), 0),
                "p5_day": round(np.percentile(dy, 5), 0),
                "worst_wk": round(wk.min(), 0),
                "tr_wk": round(len(s) / max(len(wk), 1), 1)}

    rows = []
    n_run = 0
    for a_ in (1.2, 1.5):
        for ladder in ("123", "122", "cap2"):
            for fvol_mode in ("none", "cap1", "skip"):
                for day_stop in (None, -350.0):
                    for disaster in (100.0, 60.0):
                        for qgate in (False, True):
                            st = stats(run(a_, ladder, fvol_mode,
                                           day_stop, disaster, qgate))
                            n_run += 1
                            if st:
                                st["name"] = (f"a{a_}_{ladder}_fv-{fvol_mode}"
                                              f"_ds{int(day_stop) if day_stop else 0}"
                                              f"_dis{int(disaster)}"
                                              f"{'_qg' if qgate else ''}")
                                rows.append(st)
            print(f"[a{a_} {ladder}] done {n_run} ({time.time()-t0:.0f}s)",
                  flush=True)
    out = pd.DataFrame(rows)
    out.to_csv("research/round41_spec.csv", index=False)
    cols = ["name", "usd_wk", "pos_wk", "worst_day", "p5_day", "worst_wk", "tr_wk"]
    spec = out[(out.pos_wk >= 88) & (out.worst_day >= -520) & (out.usd_wk >= 1400)]
    print(f"\n{len(out)} configs ({time.time()-t0:.0f}s)")
    print(f"\nSPEC PASSES (>=88% pos wks, worst day >=-520, >=$1400/wk): {len(spec)}")
    if len(spec):
        print(spec.sort_values("usd_wk", ascending=False)[cols].to_string(index=False))
    print("\nFrontier by worst_day (best 15 with usd_wk>=1100):")
    fr = out[out.usd_wk >= 1100].sort_values("worst_day", ascending=False)
    print(fr[cols].head(15).to_string(index=False))
    print("\nFrontier by usd_wk (best 15 with worst_day>=-700):")
    fr2 = out[out.worst_day >= -700].sort_values("usd_wk", ascending=False)
    print(fr2[cols].head(15).to_string(index=False))


if __name__ == "__main__":
    main()
