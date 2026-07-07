"""Round 25: MORE recent-regime avenues, ultra-realistic tick executor.
All new avenues on the last-3-months protocol (select Apr-May 2026,
blind Jun 1 - Jul 6), tick-walked fills (65ms latency, adverse tick),
$1.50 commission. Hard frequency cap: 500 trades/week (flagged if over).

Avenues:
  A. Sub-minute overextension fade (15s bars: the champion at finer grain)
  B. Time-of-day drift map fitted on select, traded blind
  C. Session plays: Globex reopen gap, EU open, lunch fade, close drive
  D. Graveyard retest: all 10 vault legs on the recent regime
  E. Order-flow imbalance (signed tick volume) families
  F. Champion conditioning: daily-anchor (VWAP-side) filters
"""
import os, time
import numpy as np, pandas as pd

PT = 2.0
FEES = 1.50
TICK = 0.25
LAT_NS = 65_000_000
SPLIT = pd.Timestamp("2026-06-01", tz="UTC")
SEL_LO = pd.Timestamp("2026-04-01", tz="UTC")
END = pd.Timestamp("2026-07-07", tz="UTC")


def executor(ts, px):
    n = len(ts)

    def run(times, sides, hold_min):
        out = []
        busy = 0
        hn = int(hold_min * 60_000_000_000)
        for t, s in zip(times, sides):
            if t < busy:
                continue
            ei = np.searchsorted(ts, t + LAT_NS, side="left")
            if ei >= n:
                break
            e = px[ei] + TICK * s
            xj = np.searchsorted(ts, t + hn + LAT_NS, side="left")
            if xj >= n:
                break
            out.append((ts[xj], (px[xj] - TICK * s - e) * s * PT - FEES))
            busy = ts[xj]
        return out
    return run


def wk(out, lo, hi):
    s = pd.Series([p for _, p in out],
                  index=pd.to_datetime([t for t, _ in out], utc=True))
    s = s[(s.index >= lo) & (s.index < hi)]
    if not len(s):
        return dict(usd_wk=0.0, tr_wk=0.0, per=0.0, worst=0.0, pos=0)
    w = s.resample("W").sum(); w = w[w != 0]
    weeks = max(len(w), 1)
    return dict(usd_wk=round(s.sum() / weeks, 0), tr_wk=round(len(s) / weeks, 1),
                per=round(s.mean(), 2), worst=round(w.min(), 0),
                pos=round((w > 0).mean() * 100))


def add(rows, name, out):
    a = wk(out, SEL_LO, SPLIT); b = wk(out, SPLIT, END)
    rows.append({"name": name,
                 "sel_usd_wk": a["usd_wk"], "sel_tr_wk": a["tr_wk"],
                 "bl_usd_wk": b["usd_wk"], "bl_tr_wk": b["tr_wk"],
                 "bl_per": b["per"], "bl_worst": b["worst"], "bl_pos": b["pos"],
                 "over_cap": max(a["tr_wk"], b["tr_wk"]) > 500})


def resample_px(ts, px, res_ns):
    m = (ts // res_ns) * res_ns
    g = pd.DataFrame({"m": m, "px": px}).groupby("m")["px"].agg(
        open="first", high="max", low="min", close="last")
    g.index = pd.to_datetime(g.index, utc=True)
    return g


def main():
    t0 = time.time()
    z = np.load("data/tick/ytd2026.npz")
    ts, px = z["ts"], z["px"]
    keep = ts >= (SEL_LO - pd.Timedelta(days=10)).value
    ts, px = ts[keep], px[keep]
    run = executor(ts, px)
    print(f"ticks Apr+: {len(ts):,} ({time.time()-t0:.0f}s)", flush=True)
    rows = []

    # ---------- shared 1m bars ---------------------------------------------
    b1 = resample_px(ts, px, 60_000_000_000)
    o1, h1, l1, c1 = (b1[k].to_numpy() for k in ("open", "high", "low", "close"))
    i1 = b1.index; t1 = i1.asi8 + 60_000_000_000
    hr1 = np.asarray(i1.hour) + np.asarray(i1.minute) / 60.0
    dk1 = i1.normalize()
    r1 = c1 - np.roll(c1, 1); r1[0] = 0
    tr1 = np.maximum(h1 - l1, np.abs(r1))
    atr1 = pd.Series(tr1).rolling(20).mean().to_numpy()

    # ---------- A. sub-minute overextension (15s bars) ---------------------
    b15 = resample_px(ts, px, 15_000_000_000)
    c15 = b15["close"].to_numpy(); o15 = b15["open"].to_numpy()
    h15 = b15["high"].to_numpy(); l15 = b15["low"].to_numpy()
    i15 = b15.index; t15 = i15.asi8 + 15_000_000_000
    hr15 = np.asarray(i15.hour) + np.asarray(i15.minute) / 60.0
    r15 = c15 - np.roll(c15, 1); r15[0] = 0
    tr15 = np.maximum(h15 - l15, np.abs(r15))
    atr15 = pd.Series(tr15).rolling(80).mean().to_numpy()   # ~20min
    rth15 = (hr15 >= 14.0) & (hr15 < 20.9)
    for kb, ktag in ((8, "2m"), (16, "4m"), (40, "10m")):
        mom = c15 - np.roll(c15, kb); mom[:kb] = 0
        for mult in (6.0, 10.0, 16.0):     # vs 15s ATR => effective big moves
            thr = mult * np.nan_to_num(atr15, nan=np.inf)
            sig = np.where((mom < -thr) & rth15, 1,
                           np.where((mom > thr) & rth15, -1, 0))
            live = np.flatnonzero(sig != 0)
            if len(live) < 100:
                continue
            for hold in (2, 5, 10):
                add(rows, f"A_SUBF_{ktag}_m{mult}_t{hold}",
                    run(t15[live], sig[live], hold))
        print(f"[A {ktag}] done ({time.time()-t0:.0f}s)", flush=True)

    # ---------- B. time-of-day drift map (fit select, trade blind) ---------
    halfhr = (np.asarray(i1.hour) * 2 + (np.asarray(i1.minute) >= 30)).astype(int)
    fwd30 = np.roll(c1, -30) - c1; fwd30[-30:] = np.nan
    selb = np.asarray(i1 < SPLIT) & np.asarray(i1 >= SEL_LO)
    slot_mu = {}
    for s_ in range(48):
        m = selb & (halfhr == s_) & (np.asarray(i1.minute) % 30 == 0)
        v = fwd30[m]; v = v[~np.isnan(v)]
        slot_mu[s_] = v.mean() if len(v) > 20 else 0.0
    ranked = sorted(slot_mu, key=lambda s_: slot_mu[s_])
    shorts, longs = ranked[:3], ranked[-3:]
    at_slot = (np.asarray(i1.minute) % 30 == 0)
    sig = np.where(np.isin(halfhr, longs) & at_slot, 1,
                   np.where(np.isin(halfhr, shorts) & at_slot, -1, 0))
    live = np.flatnonzero(sig != 0)
    add(rows, "B_TOD_top3x30m", run(t1[live], sig[live], 30))
    print(f"[B TOD] done; long slots {longs} short slots {shorts}", flush=True)

    # ---------- C. session plays -------------------------------------------
    # Globex reopen gap-fade/follow: 22:00 open vs 21:00 close
    day_close = pd.Series(c1, index=i1).between_time("20:55", "21:00")
    dcd = day_close.groupby(day_close.index.date).last()
    reopen = (hr1 >= 22.0) & (hr1 < 22.05)
    prevc = pd.Series(i1.date, index=i1).map(
        lambda d: dcd.get(d, np.nan)).to_numpy(float)
    gap = np.where(reopen, c1 - prevc, np.nan)
    for gthr in (5.0, 15.0):
        sigf = np.where(reopen & (gap > gthr), 1,
                        np.where(reopen & (gap < -gthr), -1, 0))
        sigr = -sigf
        for nm, sg in ((f"C_GAPF_g{gthr}", sigf), (f"C_GAPR_g{gthr}", sigr)):
            live = np.flatnonzero(sg != 0)
            if len(live) < 8:
                continue
            for hold in (30, 60):
                add(rows, f"{nm}_t{hold}", run(t1[live], sg[live], hold))
    # EU open momentum/fade (07:00-09:00)
    eu = (hr1 >= 7.0) & (hr1 < 9.0)
    mom15 = c1 - np.roll(c1, 15); mom15[:15] = 0
    thr = 1.5 * np.nan_to_num(atr1, nan=np.inf)
    for nm, sg in (("C_EUF", np.where(eu & (mom15 > thr), 1,
                                      np.where(eu & (mom15 < -thr), -1, 0))),
                   ("C_EUR", np.where(eu & (mom15 < -thr), 1,
                                      np.where(eu & (mom15 > thr), -1, 0)))):
        live = np.flatnonzero(sg != 0)
        for hold in (15, 30):
            add(rows, f"{nm}_t{hold}", run(t1[live], sg[live], hold))
    # lunch fade (17:00-18:30 UTC): fade the morning trend
    am_ret = np.full(len(c1), np.nan)
    df_am = pd.DataFrame({"d": dk1, "c": c1, "am": (hr1 >= 13.5) & (hr1 < 17.0)})
    amo = df_am[df_am.am].groupby("d")["c"].first()
    amc = df_am[df_am.am].groupby("d")["c"].last()
    amr = (amc - amo)
    lunch = (hr1 >= 17.0) & (hr1 < 17.1)
    amr_bar = pd.Series(dk1).map(amr).to_numpy(float)
    sg = np.where(lunch & (amr_bar > 20), -1,
                  np.where(lunch & (amr_bar < -20), 1, 0))
    live = np.flatnonzero(sg != 0)
    for hold in (60, 90):
        add(rows, f"C_LUNCHR_t{hold}", run(t1[live], sg[live], hold))
    # close drive follow (19:30 state -> hold to close)
    late = (hr1 >= 19.5) & (hr1 < 19.6)
    day_o = pd.DataFrame({"d": dk1, "c": c1, "rth": (hr1 >= 13.5)})
    rtho = day_o[day_o.rth].groupby("d")["c"].first()
    rtho_bar = pd.Series(dk1).map(rtho).to_numpy(float)
    dret = c1 - rtho_bar
    sg = np.where(late & (dret > 15), 1, np.where(late & (dret < -15), -1, 0))
    live = np.flatnonzero(sg != 0)
    add(rows, "C_CLOSEDRV_t80", run(t1[live], sg[live], 80))
    print(f"[C sessions] done ({time.time()-t0:.0f}s)", flush=True)

    # ---------- D. graveyard: vault legs on the recent regime --------------
    def bars_tf(tf_min):
        return resample_px(ts, px, tf_min * 60_000_000_000)
    # DON 15m lb12 window 14.5-20.92, t120
    b = bars_tf(15); c_ = b["close"].to_numpy(); h_ = b["high"].to_numpy()
    l_ = b["low"].to_numpy(); ii = b.index; tt = ii.asi8 + 15 * 60_000_000_000
    hh = np.asarray(ii.hour) + np.asarray(ii.minute) / 60.0
    dh = pd.Series(h_).rolling(12).max().shift(1).to_numpy()
    dl = pd.Series(l_).rolling(12).min().shift(1).to_numpy()
    win = (hh >= 14.5) & (hh < 20.92)
    sg = np.where(win & (c_ > dh), 1, np.where(win & (c_ < dl), -1, 0))
    live = np.flatnonzero(sg != 0)
    add(rows, "D_DON_15m", run(tt[live], sg[live], 120 * 15 // 15 * 15))
    # ONH 20.75 entry hold 65 bars of 15m
    sg = np.where((hh >= 20.75) & (hh < 20.92), 1, 0)
    live = np.flatnonzero(sg != 0)
    add(rows, "D_ONH_15m", run(tt[live], sg[live], 65 * 15))
    # CONSECC 4-run fade window
    o_ = b["open"].to_numpy()
    upb = c_ > o_
    r4 = np.array([all(upb[j - 3:j + 1]) for j in range(len(c_))])
    d4 = np.array([not any(upb[j - 3:j + 1]) for j in range(len(c_))])
    rthw = (hh >= 13.5) & (hh < 20.9)
    sg = np.where(r4 & rthw, 1, np.where(d4 & rthw, -1, 0))
    live = np.flatnonzero(sg != 0)
    add(rows, "D_CONSECC_15m", run(tt[live], sg[live], 60 * 15 // 15 * 15))
    # NRB 5m t120, TDAY 5m, RSI2 5m
    b5_ = bars_tf(5); c5 = b5_["close"].to_numpy(); h5 = b5_["high"].to_numpy()
    l5 = b5_["low"].to_numpy(); o5 = b5_["open"].to_numpy()
    i5 = b5_.index; t5 = i5.asi8 + 5 * 60_000_000_000
    h5r = np.asarray(i5.hour) + np.asarray(i5.minute) / 60.0
    rth5 = (h5r >= 13.5) & (h5r < 20.9)
    rng5 = h5 - l5
    nr = pd.Series(rng5).rolling(8).min().shift(1).to_numpy()
    prevr = np.roll(rng5, 1)
    isnr = prevr <= nr
    sg = np.where(rth5 & isnr & (c5 > np.roll(h5, 1)), 1,
                  np.where(rth5 & isnr & (c5 < np.roll(l5, 1)), -1, 0))
    live = np.flatnonzero(sg != 0)
    add(rows, "D_NRB_5m", run(t5[live], sg[live], 120 * 5))
    cs5 = pd.Series(c5)
    d1_ = cs5.diff()
    rup = d1_.clip(lower=0).rolling(2).mean()
    rdn = (-d1_.clip(upper=0)).rolling(2).mean()
    rsi2 = (100 - 100 / (1 + rup / rdn.replace(0, np.nan))).to_numpy()
    sma200 = cs5.rolling(200).mean().to_numpy()
    sg = np.where((rsi2 < 10) & (c5 > sma200), 1,
                  np.where((rsi2 > 90) & (c5 < sma200), -1, 0))
    live = np.flatnonzero(sg != 0)
    add(rows, "D_RSI2_5m", run(t5[live], sg[live], 60 * 5))
    # BWEXP 3m t40, FHFADE 3m
    b3 = bars_tf(3); c3 = b3["close"].to_numpy(); o3 = b3["open"].to_numpy()
    i3 = b3.index; t3 = i3.asi8 + 3 * 60_000_000_000
    h3r = np.asarray(i3.hour) + np.asarray(i3.minute) / 60.0
    cs3 = pd.Series(c3)
    sd203 = cs3.rolling(20).std().to_numpy()
    bw = 4 * sd203
    exp_ = bw > 1.5 * np.roll(bw, 10); exp_[:30] = False
    rth3 = (h3r >= 13.5) & (h3r < 20.9)
    up3 = c3 > o3
    sg = np.where(exp_ & up3 & rth3, 1, np.where(exp_ & ~up3 & rth3, -1, 0))
    live = np.flatnonzero(sg != 0)
    add(rows, "D_BWEXP_3m", run(t3[live], sg[live], 40 * 3))
    print(f"[D graveyard] done ({time.time()-t0:.0f}s)", flush=True)

    # ---------- E. order-flow imbalance (Apr+ ticks have size) -------------
    z2 = np.load("data/tick/recent3m.npz")
    ts2, px2, sz2 = z2["ts"], z2["px"], z2["sz"]
    d_ = np.sign(np.diff(px2, prepend=px2[0]))
    m_ = (ts2 // 60_000_000_000) * 60_000_000_000
    imb = pd.DataFrame({"m": m_, "iv": d_ * sz2}).groupby("m")["iv"].sum()
    imb = imb.reindex(b1.index.asi8 // 1 * 1, fill_value=0.0)
    ima = pd.Series(imb.to_numpy()).rolling(10).sum().to_numpy()
    ias = pd.Series(np.abs(imb.to_numpy())).rolling(30).mean().to_numpy()
    rth1 = (hr1 >= 13.5) & (hr1 < 20.9)
    for mult in (3.0, 6.0):
        thr = mult * np.nan_to_num(ias, nan=np.inf)
        for nm, sg in ((f"E_IMBF_m{mult}", np.where((ima > thr) & rth1, 1,
                                                    np.where((ima < -thr) & rth1, -1, 0))),
                       (f"E_IMBR_m{mult}", np.where((ima < -thr) & rth1, 1,
                                                    np.where((ima > thr) & rth1, -1, 0)))):
            live = np.flatnonzero(sg != 0)
            if len(live) < 50:
                continue
            for hold in (5, 15, 30):
                add(rows, f"{nm}_t{hold}", run(t1[live], sg[live], hold))
    print(f"[E imbalance] done ({time.time()-t0:.0f}s)", flush=True)

    # ---------- F. champion + daily-anchor conditioning --------------------
    rtho_arr = rtho_bar
    mom10 = c1 - np.roll(c1, 10); mom10[:10] = 0
    thr = 1.2 * np.nan_to_num(atr1, nan=np.inf)
    base_l = (mom10 < -thr); base_s = (mom10 > thr)
    skip30 = (hr1 >= 14.0) & (hr1 < 20.9)
    above_anchor = c1 > rtho_arr
    for nm, lm, sm in (
        ("F_CHAMP_withanchor", base_l & above_anchor, base_s & ~above_anchor),
        ("F_CHAMP_against", base_l & ~above_anchor, base_s & above_anchor),
    ):
        sg = np.where(lm & skip30, 1, np.where(sm & skip30, -1, 0))
        live = np.flatnonzero(sg != 0)
        add(rows, f"{nm}_t15", run(t1[live], sg[live], 15))
    print(f"[F conditioning] done ({time.time()-t0:.0f}s)", flush=True)

    out = pd.DataFrame(rows).sort_values("sel_usd_wk", ascending=False)
    out.to_csv("research/round25_more.csv", index=False)
    cols = ["name", "sel_usd_wk", "sel_tr_wk", "bl_usd_wk", "bl_tr_wk",
            "bl_per", "bl_worst", "bl_pos", "over_cap"]
    print(f"\n{len(out)} configs ({time.time()-t0:.0f}s)")
    print("\nTOP 30 by SELECT — blind is the verdict (cap 500 tr/wk flagged):")
    print(out[cols].head(30).to_string(index=False))
    ok = out[(out.sel_usd_wk > 0) & (out.bl_usd_wk > 0) & ~out.over_cap]
    print(f"\nboth-positive within cap: {len(ok)}")
    print(ok.sort_values("bl_usd_wk", ascending=False)[cols]
          .head(20).to_string(index=False))


if __name__ == "__main__":
    main()
