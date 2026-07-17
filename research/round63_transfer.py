"""Round 63: THIRD/FOURTH/FIFTH INSTRUMENT - zero-refit transfer of
BP-Final onto micro gold (MGC), micro Dow (MYM), micro bitcoin (MBT).
Same template as round 62 (M2K): frozen NQ params (fade mom10 >
1.2xATR20, guard 8 ATR day-trend, xaccel 10, hold 15 min, passive
entry, EOD flatten 20:55 UTC, entries 14:00-20:44 UTC), dollar knobs
ATR-scaled per instrument, faithful fills, $1.50/RT worst-case fees.
Cost-to-volatility screen computed first - the M2K/MES killer.
"""
import glob, sys, time
import numpy as np, pandas as pd

LAT_NS = 65_000_000
FEES = 1.50
EOD_NS = (20 * 60 + 55) * 60_000_000_000
ENTRY_LO, ENTRY_HI = 14.0, 20.73
GUARD, XACCEL, HOLD_MIN = 8.0, 10.0, 15

INSTRUMENTS = [
    # name, dir, PT ($/point), TICK (points), min rows/day
    ("MGC gold", "/tmp/claude-0/weekticks/mgcq6", 10.0, 0.10, 10_000),
    ("MYM dow", "/tmp/claude-0/weekticks/mymu6", 0.50, 1.00, 10_000),
    ("MBT btc", "/tmp/claude-0/weekticks/mbtn6", 0.10, 5.00, 5_000),
]


def load_ticks(d, min_rows):
    parts, kept, skipped = [], 0, 0
    for f in sorted(glob.glob(f"{d}/*.parquet")):
        df = pd.read_parquet(f, columns=["ts", "price"])
        if len(df) < min_rows:
            skipped += 1
            continue
        kept += 1
        parts.append(df)
    df = pd.concat(parts, ignore_index=True)
    ts = df["ts"].to_numpy(np.int64)
    px = pd.to_numeric(df["price"], errors="coerce").to_numpy(np.float64)
    ok = np.isfinite(px)
    ts, px = ts[ok], px[ok]
    o = np.argsort(ts, kind="stable")
    ts, px = ts[o], px[o]
    wd = (ts // 86_400_000_000_000 + 4) % 7
    m = wd < 5
    return ts[m], px[m], kept, skipped


def build(ts, px):
    m = ts // 60_000_000_000
    st = np.concatenate(([0], np.flatnonzero(np.diff(m)) + 1))
    en = np.concatenate((st[1:], [len(m)]))
    c = px[en - 1]
    h = np.maximum.reduceat(px, st)
    l = np.minimum.reduceat(px, st)
    bmin = m[st]
    bts = (bmin + 1) * 60_000_000_000          # bar close ts
    days = (bmin * 60_000_000_000) // 86_400_000_000_000 \
        * 86_400_000_000_000
    hrs = (bmin % 1440) / 60.0
    r1 = c - np.roll(c, 1); r1[0] = 0
    tr = np.maximum(h - l, np.abs(r1))
    atr = pd.Series(tr).rolling(20).mean().to_numpy()
    nb = len(c)
    # day-open (first bar >= 14:00 UTC each day) + last tick idx per day
    day_open = np.full(nb, np.nan)
    cur_day, cur_open = -1, np.nan
    for i in range(nb):
        if days[i] != cur_day:
            cur_day, cur_open = days[i], np.nan
        if np.isnan(cur_open) and hrs[i] >= 14.0:
            cur_open = c[i]
        day_open[i] = cur_open
    pos_atr = np.where(np.nan_to_num(atr) > 0, atr, np.inf)
    sdt = np.abs(c - day_open) / pos_atr
    sdt = np.nan_to_num(sdt)
    # last tick index of each calendar day (for EOD clamp)
    td = ts // 86_400_000_000_000
    dl = np.concatenate((np.flatnonzero(np.diff(td)), [len(ts) - 1]))
    dl_days = td[dl] * 86_400_000_000_000
    day_last_i = dl[np.searchsorted(dl_days, days)]
    return dict(c=c, atr=atr, hrs=hrs, bts=bts, days=days, sdt=sdt,
                nb=nb, day_last_i=day_last_i)


def sim_bp(ts, px, C, PT, TICK, OFF, DIS):
    n = len(ts)
    c, atr, hrs = C["c"], C["atr"], C["hrs"]
    bts, days, sdt = C["bts"], C["days"], C["sdt"]
    ninf = np.nan_to_num(atr, nan=np.inf)
    kb = 10
    mom = np.concatenate(([0.0] * kb, c[kb:] - c[:-kb]))
    thr = 1.2 * ninf
    ent = (hrs >= ENTRY_LO) & (hrs < ENTRY_HI) & (sdt <= GUARD)
    raw = np.where(mom < -thr, 1, np.where(mom > thr, -1, 0))
    sig = np.where(ent, raw, 0)
    hold_ns = HOLD_MIN * 60_000_000_000
    out_t, out_p = [], []
    busy = 0
    for i in np.flatnonzero(sig):
        if bts[i] < busy:
            continue
        s = int(sig[i])
        L = c[i] - OFF * s
        a0 = np.searchsorted(ts, bts[i] + LAT_NS, "left")
        a1 = np.searchsorted(ts, bts[i] + 180_000_000_000, "left")
        if a0 >= n:
            break
        seg = px[a0:a1]
        th = np.flatnonzero(seg * s < (L - TICK * s) * s + 1e-9)
        if not len(th):
            continue
        fi = a0 + int(th[0])
        t_tgt = min(ts[fi] + hold_ns + LAT_NS, days[i] + EOD_NS)
        xe = np.searchsorted(ts, t_tgt, "left")
        xe = min(xe, C["day_last_i"][i])
        if xe <= fi:
            continue
        fill = None; k = xe
        # xaccel: bar-level day-trend blowout during hold -> bail
        b0 = np.searchsorted(bts, ts[fi], "left")
        b1 = np.searchsorted(bts, ts[xe], "left")
        xb = b0 + np.flatnonzero(sdt[b0:b1] > XACCEL)
        x_cut = bts[xb[0]] if len(xb) else None
        stop_lvl = L - DIS * s
        seg2 = px[fi + 1:xe]
        if len(seg2):
            sh = np.flatnonzero(seg2 * s <= stop_lvl * s + 1e-9)
            if len(sh):
                k = fi + 1 + int(sh[0])
                rw = min(px[k], stop_lvl) if s > 0 else max(px[k], stop_lvl)
                fill = rw - TICK * s
        if x_cut is not None and (fill is None or ts[k] > x_cut):
            k = min(np.searchsorted(ts, x_cut, "left"), xe)
            fill = px[k] - TICK * s
        if fill is None:
            fill = px[xe] - TICK * s
            k = xe
        out_p.append((fill - L) * s * PT - FEES)
        out_t.append(ts[k])
        busy = ts[k]
    s_ = pd.Series(out_p, index=pd.to_datetime(
        np.array(out_t, dtype="int64"), utc=True)).sort_index()
    return s_[s_.index.dayofweek < 5]


def main():
    t0 = time.time()
    for name, d, PT, TICK, min_rows in INSTRUMENTS:
        print(f"\n{'='*62}\n{name}  (PT=${PT}/pt, tick={TICK})", flush=True)
        ts, px, kept, skipped = load_ticks(d, min_rows)
        C = build(ts, px)
        rth = (C["hrs"] >= 14.0) & (C["hrs"] < 20.9)
        atr_med = float(np.nanmedian(C["atr"][rth]))
        friction = FEES + 2 * TICK * PT
        f_pct = friction / (atr_med * PT) * 100
        OFF = max(TICK, round(0.05 * atr_med / TICK) * TICK)
        DIS = 3.0 * atr_med
        d0 = pd.to_datetime(ts[0], utc=True).date()
        d1 = pd.to_datetime(ts[-1], utc=True).date()
        print(f"  days kept {kept} / skipped {skipped} (thin) | "
              f"{len(ts):,} ticks | {d0} -> {d1}")
        print(f"  median RTH 1m ATR: {atr_med:.2f}pt = "
              f"${atr_med*PT:.2f} | friction ${friction:.2f}/trade "
              f"= {f_pct:.0f}% of ATR  "
              f"({'PASS <=10%' if f_pct <= 10 else 'FAIL >10% screen'})")
        print(f"  scaled knobs: OFF={OFF:.2f}pt  DIS={DIS:.1f}pt")
        s = sim_bp(ts, px, C, PT, TICK, OFF, DIS)
        if len(s) < 20:
            print(f"  only {len(s)} trades - insufficient. DEAD.")
            continue
        wk = s.resample("W").sum(); wk = wk[wk != 0]
        dy = s.resample("D").sum(); dy = dy[dy != 0]
        wins = s[s > 0]
        eq = dy.cumsum()
        mdd = float((eq - eq.cummax()).min())
        print(f"  trades {len(s)} | {len(s)/len(wk):.0f}/wk | "
              f"WR {(s>0).mean()*100:.0f}% | avgW {wins.mean():.1f} "
              f"avgL {s[s<0].mean():.1f}")
        print(f"  $/wk {s.sum()/len(wk):+.0f} | pos wks "
              f"{(wk>0).mean()*100:.0f}% | worst day {dy.min():+.0f} | "
              f"MDD {mdd:+.0f}")
        print("  weekly:", " ".join(f"{v:+.0f}" for v in wk))
        del ts, px, C
    print(f"\nDONE ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
