"""Round 35: META walk-forward — is "trade what worked recently" itself
a durable system? Menu = the back-pocket family archetypes (overextension
fade, flow-follow, auction drift). Each month M: score every menu item on
months M-2..M-1, trade the winner through month M. Repeat 2023-09..2026-06.
Bar-level honest engine (next-bar-open entry, 0.5pt RT slip total, $1.50
commission) — flagged as approximation; the 2026 tick executor already
validated the menu items' fill physics.
Outputs: monthly P&L of META vs each always-on menu item.
"""
import time
import numpy as np, pandas as pd

PT = 2.0
FEES = 1.50
SLIP = 0.25          # per side, pts
START = pd.Timestamp("2023-09-01", tz="UTC")


def main():
    t0 = time.time()
    bars = pd.read_parquet("data/tick/nq_bars_1m_2p5y.parquet")
    try:
        vf = pd.read_parquet("data/tick/minute_volfeat.parquet")
        bars = bars.join(vf, how="left")
    except Exception:
        bars["imb"] = 0.0
    o = bars["open"].to_numpy(); h = bars["high"].to_numpy()
    l = bars["low"].to_numpy(); c = bars["close"].to_numpy()
    iv = bars["imb"].fillna(0).to_numpy()
    idx = bars.index
    nb = len(c)
    print(f"bars: {nb:,} {idx.min()} -> {idx.max()} ({time.time()-t0:.0f}s)",
          flush=True)
    hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0
    rth = (hrs >= 13.5) & (hrs < 20.9)
    skip30 = (hrs >= 14.0) & (hrs < 20.9)
    r1 = c - np.roll(c, 1); r1[0] = 0
    tr = np.maximum(h - l, np.abs(r1))
    atr = pd.Series(tr).rolling(20).mean().to_numpy()
    ias = pd.Series(np.abs(iv)).rolling(30).mean().to_numpy()
    ima = pd.Series(iv).rolling(10).sum().to_numpy()
    mom10 = c - np.roll(c, 10); mom10[:10] = 0
    thr12 = 1.2 * np.nan_to_num(atr, nan=np.inf)
    ivs300 = pd.Series(np.abs(iv)).rolling(300).mean().to_numpy()
    dk = idx.normalize()
    open5 = (hrs >= 13.5) & (hrs < 13.583)
    df5 = pd.DataFrame({"d": dk, "iv": np.where(open5, iv, 0)})
    oiv = df5.groupby("d")["iv"].transform("sum").to_numpy()
    fire5 = (hrs >= 13.583) & (hrs < 13.6)

    def sim(sig, hold):
        """Bar-level: enter next bar open +slip, exit at open of bar
        entry+hold +slip. Non-overlapping."""
        out_t, out_p = [], []
        i = 0
        while i < nb - hold - 2:
            s = sig[i]
            if s == 0:
                i += 1; continue
            e = o[i + 1] + SLIP * s
            x = o[i + 1 + hold] - SLIP * s
            out_t.append(idx[i + 1 + hold].value)
            out_p.append((x - e) * s * PT - FEES)
            i += 1 + hold
        return (pd.Series(out_p,
                index=pd.to_datetime(np.array(out_t, dtype="int64"), utc=True))
                if out_p else pd.Series(dtype=float))

    MENU = {}
    sigF = np.where((mom10 < -thr12) & skip30, 1,
                    np.where((mom10 > thr12) & skip30, -1, 0))
    MENU["FADE"] = sim(sigF, 15)
    sigB = np.where((ima > 3 * np.nan_to_num(ias, nan=np.inf)) & rth, 1,
                    np.where((ima < -3 * np.nan_to_num(ias, nan=np.inf)) & rth,
                             -1, 0))
    MENU["FLOW"] = sim(sigB, 30)
    base5 = 5 * np.nan_to_num(ivs300, nan=np.inf)
    sigA = np.where(fire5 & (oiv > base5), 1,
                    np.where(fire5 & (oiv < -base5), -1, 0))
    MENU["AUCT"] = sim(sigA, 240)
    MENU["FLAT"] = pd.Series(dtype=float)     # cash is a menu option
    for k, s in MENU.items():
        print(f"{k}: {len(s)} trades ({time.time()-t0:.0f}s)", flush=True)

    months = pd.period_range(START.to_period("M"),
                             idx.max().to_period("M"), freq="M")
    rows = []
    meta_pnl = []
    for M in months:
        m_start = M.to_timestamp(tz="UTC")
        m_end = (M + 1).to_timestamp(tz="UTC")
        s_start = (M - 2).to_timestamp(tz="UTC")
        scores = {}
        for k, s in MENU.items():
            w = s[(s.index >= s_start) & (s.index < m_start)]
            scores[k] = w.sum() if len(w) else 0.0
        winner = max(scores, key=scores.get)
        if scores[winner] <= 0:
            winner = "FLAT"
        w = MENU[winner]
        mp = w[(w.index >= m_start) & (w.index < m_end)].sum() \
            if len(w) else 0.0
        meta_pnl.append(mp)
        row = {"month": str(M), "pick": winner, "meta": round(mp, 0)}
        for k, s in MENU.items():
            if k == "FLAT":
                continue
            row[k] = round(s[(s.index >= m_start) & (s.index < m_end)].sum(), 0)
        rows.append(row)
    res = pd.DataFrame(rows)
    res.to_csv("research/round35_meta.csv", index=False)
    print("\n=== monthly: META pick vs always-on legs ===")
    print(res.to_string(index=False))
    meta = np.array(meta_pnl)
    nmo = len(meta)
    print(f"\nMETA: total ${meta.sum():.0f} over {nmo} months "
          f"(${meta.sum()/nmo*12/52:.0f}/wk avg) | positive months "
          f"{(meta>0).mean()*100:.0f}% | worst month ${meta.min():.0f}")
    for k in ("FADE", "FLOW", "AUCT"):
        v = res[k].to_numpy(float)
        print(f"always-{k}: total ${v.sum():.0f} | pos months "
              f"{(v>0).mean()*100:.0f}% | worst ${v.min():.0f}")


if __name__ == "__main__":
    main()
