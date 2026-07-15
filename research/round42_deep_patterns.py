"""Round 42: DEEP PATTERN RECOGNITION — the heavy guns, none fired before.
  A. MATRIX-PROFILE MOTIFS: z-normalized 20-minute price shapes, mined
     with FFT-based MASS distance (time-series motif discovery — a
     completely different pattern technology from symbol n-grams).
     Clusters fitted on Mar-May, traded blind Jun+; direction = the
     cluster's historical forward drift.
  B. SKIP-GRAM SYMBOLS: gapped patterns (A _ B _ C) over 1m symbols —
     the n-gram miner could never see motifs with holes.
  C. TREE-RULE EXTRACTION: depth-3 decision tree on the tick feature
     set, walk-forward monthly; the single best leaf becomes ONE
     interpretable rule (this is rule mining, not the failed regressor).
  D. CONDITIONAL 2-GRAMS: symbol pairs jointly conditioned on hour
     bucket x volatility regime, de-clustered scoring.
Window: select Mar 1 - May 31, blind Jun 1 - Jul 6. Tick-walked fills,
$1.50/RT, flat 1 MNQ (ladder applied only to a survivor later).
Benchmark to beat on risk-adjusted: FADESZ+P $1,330/wk, worst day -$2,126.
"""
import time
import numpy as np, pandas as pd

PT = 2.0
FEES = 1.50
TICK = 0.25
LAT_NS = 65_000_000
SEL_LO = pd.Timestamp("2026-03-01", tz="UTC")
SPLIT = pd.Timestamp("2026-06-01", tz="UTC")
END = pd.Timestamp("2026-07-07", tz="UTC")
HN = lambda m: int(m * 60_000_000_000)
W = 20            # motif window, minutes
HOLD = 15


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
    rth = (hrs >= 13.6) & (hrs < 20.65)
    sel = np.asarray(idx < SPLIT) & np.asarray(idx >= SEL_LO)
    bl = np.asarray(idx >= SPLIT) & np.asarray(idx < END)
    r1 = c - np.roll(c, 1); r1[0] = 0
    tr = np.maximum(h - l, np.abs(r1))
    atr = pd.Series(tr).rolling(20).mean().to_numpy()
    fwd = np.roll(c, -HOLD) - c; fwd[-HOLD:] = 0

    def run_ticks(sig_idx, sides, hold=HOLD):
        out = []
        busy = 0
        for i_, s in zip(sig_idx, sides):
            t = bts[i_]
            if t < busy:
                continue
            ei = np.searchsorted(ts, t + LAT_NS, "left")
            if ei >= n: break
            e = px[ei] + TICK * s
            xj = np.searchsorted(ts, t + HN(hold) + LAT_NS, "left")
            if xj >= n: break
            out.append((ts[xj], (px[xj] - TICK * s - e) * s * PT - FEES))
            busy = ts[xj]
        return out

    def stats(out, lo, hi, tag):
        s = pd.Series([p for _, p in out],
                      index=pd.to_datetime([t for t, _ in out], utc=True))
        s = s[(s.index >= lo) & (s.index < hi)]
        if len(s) < 20:
            return f"{tag}: (n={len(s)})"
        wk = s.resample("W").sum(); wk = wk[wk != 0]
        dy = s.resample("D").sum(); dy = dy[dy != 0]
        return (f"{tag}: ${s.sum()/max(len(wk),1):7.0f}/wk "
                f"{len(s)/max(len(wk),1):5.1f}tr/wk pos {int((wk>0).mean()*100):3d}% "
                f"worstday ${dy.min():6.0f} worstwk ${wk.min():6.0f}")

    # ================= A. MATRIX-PROFILE MOTIFS =========================
    print("=== A. matrix-profile motifs (20m shapes) ===", flush=True)
    valid = rth & (np.arange(nb) >= W)
    starts = np.flatnonzero(valid[:-HOLD - 1])
    # windows: z-normalized last-W closes ENDING at i
    def znorm_win(i):
        w = c[i - W + 1:i + 1]
        s_ = w.std()
        return (w - w.mean()) / (s_ if s_ > 1e-9 else 1.0)
    sel_starts = starts[sel[starts]]
    bl_starts = starts[bl[starts]]
    # subsample selection windows as motif candidates; score by how many
    # OTHER selection windows sit within distance eps (density = motif)
    rng_ = np.random.default_rng(7)
    cands = rng_.choice(sel_starts, size=min(1500, len(sel_starts)), replace=False)
    lib = np.stack([znorm_win(i) for i in sel_starts])
    lib_fwd = fwd[sel_starts]
    C = np.stack([znorm_win(i) for i in cands])
    # pairwise distance candidate->library via matrix ops (1500 x ~9k)
    d2 = ((C[:, None, :] - lib[None, :, :]) ** 2).sum(-1) if len(lib) < 4000 else None
    if d2 is None:
        # chunked
        d2 = np.empty((len(C), len(lib)), dtype=np.float32)
        for k0 in range(0, len(lib), 2000):
            d2[:, k0:k0 + 2000] = ((C[:, None, :] - lib[None, k0:k0 + 2000, :]) ** 2).sum(-1)
    eps = np.quantile(d2, 0.02)
    rows = []
    used = np.zeros(len(cands), bool)
    order = np.argsort((d2 < eps).sum(1))[::-1]
    motifs = []
    for oi in order:
        if used[oi] or len(motifs) >= 12:
            continue
        nb_mask = d2[oi] < eps
        if nb_mask.sum() < 40:
            break
        mu_fwd = lib_fwd[nb_mask].mean()
        motifs.append((cands[oi], eps, 1 if mu_fwd > 0 else -1,
                       nb_mask.sum(), mu_fwd))
        # suppress overlapping candidates
        for oj in range(len(cands)):
            if d2[oi][np.argmin(np.abs(sel_starts - cands[oj]))] < 4 * eps:
                used[oj] = True
        used[oi] = True
    print(f"  motifs found: {len(motifs)} ({time.time()-t0:.0f}s)", flush=True)
    # blind trade: window matches a motif -> trade its direction
    BL = np.stack([znorm_win(i) for i in bl_starts])
    for mi, (anchor, eps_, side, supp, mu) in enumerate(motifs[:8]):
        q = znorm_win(anchor)
        dist = ((BL - q) ** 2).sum(1)
        hits = bl_starts[dist < eps_]
        sighits_sel = sel_starts[((lib - q) ** 2).sum(1) < eps_]
        o_sel = run_ticks(sighits_sel, np.full(len(sighits_sel), side))
        o_bl = run_ticks(hits, np.full(len(hits), side))
        print("  ", stats(o_sel, SEL_LO, SPLIT, f"MOTIF{mi}(n={supp},mu={mu:+.1f}) SEL"))
        print("  ", stats(o_bl, SPLIT, END, f"MOTIF{mi} BLIND"))
    print(f"[A] done ({time.time()-t0:.0f}s)", flush=True)

    # ================= B. SKIP-GRAM SYMBOLS =============================
    print("=== B. skip-grams (A _ B _ C over 1m symbols) ===", flush=True)
    rngb = h - l
    r33, r66 = np.nanpercentile(rngb, 33), np.nanpercentile(rngb, 66)
    size_ = np.where(rngb <= r33, 0, np.where(rngb <= r66, 1, 2))
    direc = np.where(c > o, 1, 0)
    ema = pd.Series(c).ewm(span=20, adjust=False).mean().to_numpy()
    above = np.where(c > ema, 1, 0)
    sym = (direc * 6 + size_ * 2 + above).astype(np.int64)   # alphabet 12
    A_ = 12
    best = []
    code = (np.roll(sym, 4) * A_ * A_ + np.roll(sym, 2) * A_ + sym)
    code[:5] = -1
    ords = np.argsort(code, kind="stable")
    cs = code[ords]
    bounds = np.flatnonzero(np.diff(cs)) + 1
    st_ = np.concatenate(([0], bounds)); en_ = np.concatenate((bounds, [len(cs)]))
    for s0, e0 in zip(st_, en_):
        cd = cs[s0]
        if cd < 0 or e0 - s0 < 500:
            continue
        pos = np.sort(ords[s0:e0])
        pos = pos[rth[pos] & (pos < nb - HOLD - 1)]
        kept, last = [], -10**9
        for p in pos:
            if p >= last + HOLD:
                kept.append(p); last = p
        kept = np.asarray(kept)
        ksel = kept[sel[kept]]; kbl = kept[bl[kept]]
        if len(ksel) < 60:
            continue
        mu = fwd[ksel].mean()
        best.append((abs(mu) * np.sqrt(len(ksel)), cd, 1 if mu > 0 else -1,
                     ksel, kbl))
    best.sort(key=lambda x: -x[0])
    for sc, cd, side, ksel, kbl in best[:8]:
        o_sel = run_ticks(ksel, np.full(len(ksel), side))
        o_bl = run_ticks(kbl, np.full(len(kbl), side))
        print("  ", stats(o_sel, SEL_LO, SPLIT, f"SKIP_{cd} SEL"))
        print("  ", stats(o_bl, SPLIT, END, f"SKIP_{cd} BLIND"))
    print(f"[B] done ({time.time()-t0:.0f}s)", flush=True)

    # ================= C. TREE-RULE EXTRACTION ==========================
    print("=== C. depth-3 tree rule, monthly walk-forward ===", flush=True)
    from sklearn.tree import DecisionTreeRegressor
    ias = pd.Series(np.abs(iv)).rolling(30).mean().to_numpy()
    feats = {}
    for k in (3, 10, 30):
        mk = c - np.roll(c, k); mk[:k] = 0
        feats[f"ret{k}"] = mk / np.where(np.nan_to_num(atr) > 0, atr, np.inf)
    feats["flow10"] = pd.Series(iv).rolling(10).sum().to_numpy() / \
        np.where(np.nan_to_num(ias) > 0, ias, np.inf)
    feats["hour"] = hrs
    X = np.column_stack([np.nan_to_num(np.clip(v, -40, 40))
                         for v in feats.values()])
    yv = fwd
    months = [(pd.Timestamp("2026-04-01", tz="UTC"), pd.Timestamp("2026-05-01", tz="UTC")),
              (pd.Timestamp("2026-05-01", tz="UTC"), pd.Timestamp("2026-06-01", tz="UTC")),
              (pd.Timestamp("2026-06-01", tz="UTC"), pd.Timestamp("2026-07-07", tz="UTC"))]
    all_out = []
    for mlo, mhi in months:
        trm = np.asarray(idx < mlo) & np.asarray(idx >= mlo - pd.Timedelta(days=45)) & rth
        tem = np.asarray(idx >= mlo) & np.asarray(idx < mhi) & rth
        if trm.sum() < 2000:
            continue
        tree = DecisionTreeRegressor(max_depth=3, min_samples_leaf=400,
                                     random_state=0)
        tree.fit(X[trm], yv[trm])
        leaf_tr = tree.apply(X[trm])
        leaf_stats = {}
        for lf in np.unique(leaf_tr):
            v = yv[trm][leaf_tr == lf]
            leaf_stats[lf] = (v.mean(), len(v))
        best_leaf = max(leaf_stats, key=lambda k_: abs(leaf_stats[k_][0]) *
                        np.sqrt(leaf_stats[k_][1]))
        side = 1 if leaf_stats[best_leaf][0] > 0 else -1
        leaf_te = tree.apply(X[tem])
        hits = np.flatnonzero(tem)[leaf_te == best_leaf]
        all_out += run_ticks(hits, np.full(len(hits), side))
    print("  ", stats(all_out, pd.Timestamp("2026-04-01", tz="UTC"), END,
                      "TREE-RULE wf"))
    print(f"[C] done ({time.time()-t0:.0f}s)", flush=True)

    # ================= D. CONDITIONAL 2-GRAMS ===========================
    print("=== D. 2-grams x hour x vol regime ===", flush=True)
    hb = np.clip(((hrs - 13.5) // 1.5).astype(int), 0, 4)
    volhi = (atr > np.nanmedian(atr[rth])).astype(int)
    code2 = ((np.roll(sym, 1) * A_ + sym) * 5 + hb) * 2 + volhi
    code2[:2] = -1
    ords = np.argsort(code2, kind="stable")
    cs = code2[ords]
    bounds = np.flatnonzero(np.diff(cs)) + 1
    st_ = np.concatenate(([0], bounds)); en_ = np.concatenate((bounds, [len(cs)]))
    best = []
    for s0, e0 in zip(st_, en_):
        cd = cs[s0]
        if cd < 0 or e0 - s0 < 400:
            continue
        pos = np.sort(ords[s0:e0])
        pos = pos[rth[pos] & (pos < nb - HOLD - 1)]
        kept, last = [], -10**9
        for p in pos:
            if p >= last + HOLD:
                kept.append(p); last = p
        kept = np.asarray(kept)
        ksel = kept[sel[kept]]; kbl = kept[bl[kept]]
        if len(ksel) < 50:
            continue
        mu = fwd[ksel].mean()
        best.append((abs(mu) * np.sqrt(len(ksel)), cd,
                     1 if mu > 0 else -1, ksel, kbl))
    best.sort(key=lambda x: -x[0])
    for sc, cd, side, ksel, kbl in best[:8]:
        o_sel = run_ticks(ksel, np.full(len(ksel), side))
        o_bl = run_ticks(kbl, np.full(len(kbl), side))
        print("  ", stats(o_sel, SEL_LO, SPLIT, f"C2G_{cd} SEL"))
        print("  ", stats(o_bl, SPLIT, END, f"C2G_{cd} BLIND"))
    print(f"[D] done — round 42 complete ({time.time()-t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
