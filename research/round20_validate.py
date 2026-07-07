"""Round 20 stage 2: honest validation of the fine-grain survivors.
Non-overlapping trades, entry at NEXT 1m bar open after the signal, exit at
open of the bar `hold` minutes later, $3.50/RT costs (user grant). Weekly
P&L series per window: avg, median, worst, %positive, trades/wk.
Also validates a UNION signal (any surviving capitulation sequence -> long)
as ONE strategy, and decodes each pattern into English.
"""
import numpy as np, pandas as pd
from research.midfreq_search import load_bars

PT = 2.0
COST = 1.50 + 1.0 * PT       # $3.50/RT
SPLIT = pd.Timestamp("2025-01-01", tz="UTC")
A = 24

CANDS = [  # (codeA, codeB, hold_min, window_min)
    (12321, 5409, 60), (5471, 5409, 60), (6623, 13823, 60),
    (13823, 13823, 60), (13811, 13823, 60), (13811, 6623, 60),
    (6623, 13811, 60), (13523, 6623, 60), (13823, 6623, 60),
    (13823, 5421, 60), (13811, 5697, 60), (13811, 5697, 30),
    (13811, 13523, 60), (13523, 13811, 60), (12321, 12321, 60),
]

def decode(codev):
    s = []
    for _ in range(3):
        s.append(codev % A); codev //= A
    out = []
    for sym in reversed(s):   # oldest -> newest
        hb = sym % 2; sym //= 2
        ab = sym % 2; sym //= 2
        sz = sym % 4; sym //= 4
        di = sym % 12
        out.append(f"{'up' if di else 'dn'}{['S','M','L',''][sz]}"
                   f"{'^' if ab else 'v'}{'R' if hb else 'G'}")
    return ",".join(out)

def weekly_stats(pnl_ts):
    if not len(pnl_ts):
        return dict(avg=0, med=0, worst=0, pos=0, n=0)
    s = pd.Series([p for _, p in pnl_ts],
                  index=pd.DatetimeIndex([t for t, _ in pnl_ts]))
    w = s.resample("W").sum()
    w = w[w != 0]
    return dict(avg=round(w.mean(), 0), med=round(w.median(), 0),
                worst=round(w.min(), 0), pos=round((w > 0).mean() * 100),
                n=len(s))

def simulate(sig_side, o, idx, hold):
    """sig_side: array of 0/±1 signals on bar close i -> enter at open i+1."""
    pnl, i, n = [], 0, len(o)
    while i < n - hold - 1:
        s = sig_side[i]
        if s == 0:
            i += 1; continue
        e_in = o[i + 1]; e_out = o[i + 1 + hold]
        pnl.append((idx[i + 1], s * (e_out - e_in) * PT - COST))
        i += 1 + hold          # non-overlapping
    return pnl

def main():
    df = load_bars()
    c = df["close"].to_numpy(); o = df["open"].to_numpy()
    h = df["high"].to_numpy(); l = df["low"].to_numpy()
    idx = df.index; n = len(c)
    rng = h - l
    r33, r66 = np.nanpercentile(rng, 33), np.nanpercentile(rng, 66)
    size = np.where(rng <= r33, 0, np.where(rng <= r66, 1, 2))
    direc = np.where(c > o, 1, 0)
    ema = pd.Series(c).ewm(span=20, adjust=False).mean().to_numpy()
    above = np.where(c > ema, 1, 0)
    hrs = np.asarray(idx.hour)
    hbk = np.where((hrs >= 13) & (hrs < 21), 1, 0)
    sym = (direc * 12 + size * 4 + above * 2 + hbk).astype(np.int64)
    code = np.zeros(n, dtype=np.int64)
    for k in range(3):
        code = code * A + np.roll(sym, k)
    code[:3] = -1
    sel = np.asarray(idx < SPLIT)

    fwd60 = np.roll(c, -60) - c   # only to pick side, on SELECT window only
    rows = []
    union_long = np.zeros(n, dtype=np.int8)
    for ca, cb, hold in CANDS:
        a_recent = pd.Series((code == ca).astype(float)).rolling(30).max().to_numpy() > 0
        m = a_recent & (code == cb)
        msel = m & sel
        if msel.sum() < 50:
            continue
        side = 1 if np.nanmean(fwd60[msel]) > 0 else -1
        sig = np.where(m, side, 0).astype(np.int8)
        p_sel = simulate(np.where(sel, sig, 0), o, idx, hold)
        p_bl = simulate(np.where(~sel, sig, 0), o, idx, hold)
        ws, wb = weekly_stats(p_sel), weekly_stats(p_bl)
        if side == 1 and hold == 60:
            union_long |= np.where(m, 1, 0).astype(np.int8)
        rows.append({
            "pattern": f"{ca}->{cb} h{hold} {'L' if side==1 else 'S'}",
            "english": f"[{decode(ca)}] then [{decode(cb)}]",
            "sel_avg_wk": ws["avg"], "sel_worst": ws["worst"], "sel_pos%": ws["pos"],
            "sel_trades": ws["n"],
            "bl_avg_wk": wb["avg"], "bl_med_wk": wb["med"], "bl_worst": wb["worst"],
            "bl_pos%": wb["pos"], "bl_trades": wb["n"],
        })
    out = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print("=== individual sequences, honest non-overlap sim, $3.50/RT ===")
    print(out.to_string(index=False))

    # ONE strategy: union of all long capitulation sequences, hold 60
    sigU = union_long
    pU_sel = simulate(np.where(sel, sigU, 0), o, idx, 60)
    pU_bl = simulate(np.where(~sel, sigU, 0), o, idx, 60)
    wsU, wbU = weekly_stats(pU_sel), weekly_stats(pU_bl)
    n_sel_wk = max((idx[sel].max() - idx.min()).days / 7.0, 1)
    n_bl_wk = max((idx.max() - SPLIT).days / 7.0, 1)
    print("\n=== UNION (one strategy: any long capitulation sequence, 60m hold) ===")
    print(f"SELECT: avg ${wsU['avg']}/wk med ${wsU['med']} worst ${wsU['worst']} "
          f"pos {wsU['pos']}% trades/wk {wsU['n']/n_sel_wk:.1f}")
    print(f"BLIND : avg ${wbU['avg']}/wk med ${wbU['med']} worst ${wbU['worst']} "
          f"pos {wbU['pos']}% trades/wk {wbU['n']/n_bl_wk:.1f}")
    # blind weekly series tail for eyeballing consistency
    sb = pd.Series([p for _, p in pU_bl],
                   index=pd.DatetimeIndex([t for t, _ in pU_bl])).resample("W").sum()
    print("\nblind weekly P&L (last 26 weeks):")
    print(sb.tail(26).round(0).to_string())

if __name__ == "__main__":
    main()
