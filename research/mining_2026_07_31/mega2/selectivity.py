"""Real traders don't take all 458 swings a day. Can we tell which ones run?

The 2R law says a confirmation-based swing trade captures avg_swing - 2R, and
avg_swing is 2R at every scale, so the average trade captures nothing. That is
a statement about the AVERAGE swing. It says nothing about whether the swings
differ from each other in a way that is visible at the moment of confirmation.

That is the whole question here, and it is the one that matches how a
discretionary trader actually works: they do not take every setup, they skip
the ones that look ordinary and take the ones that look like they will run.
If the top slice of swings runs 4R while the average runs 2R, then selection
alone turns a zero into a real edge -- with NO improvement in direction
calling, which is the thing sixteen billion configurations failed to find.

WHAT IS MEASURED. For every confirmed swing, using only information that
exists AT CONFIRMATION:

    captured = swing size - 2R      (enter R late, exit R late)

and then, feature by feature, whether sorting swings by that feature separates
the ones that run from the ones that do not. Quintile edges come from the five
training contracts; every number reported is from the three held-out ones.

THE CONTROL. A quintile spread appears in pure noise too. So every feature is
also run with its values CIRCULARLY SHIFTED against the outcomes -- same
distribution, same autocorrelation, no alignment -- and the shifted spread is
printed beside the real one. A feature only counts if it beats its own shift.

Features are all causal at confirmation: the completed leg's shape, how the
current leg has behaved during the R points it has already travelled, the
recent rhythm of leg sizes, and where price sits in its recent range.
"""
import glob
import os
import sys

import numpy as np
import pyarrow.parquet as pq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DELAY", "1")
import grammar  # noqa: E402

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
RAW = os.path.join(ROOT, "data", "tick", "raw")
CACHE = os.path.join(ROOT, "data", "tick", "cache")
OUT = os.path.join(ROOT, "research", "SELECTIVITY.md")
PT = 4
USD_PT = 2.00
COST = 1.99
RS = [int(x) for x in os.environ.get("RS", "12,20,30").split(",")]
TRAIN = set("NQU4,NQZ4,NQH5,NQM5,NQU5".split(","))
NQ = 5
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def legs_for(c, f, R):
    """Confirmed swings at threshold R points, with causal features."""
    cp = os.path.join(CACHE, f"legs_{c}_R{R}pt.npz")
    if os.path.exists(cp):
        z = np.load(cp, allow_pickle=False)
        return {k: z[k] for k in z.files}
    t = pq.read_table(f, columns=["ts", "price", "size"])
    price = t.column("price").to_numpy(zero_copy_only=False).astype(np.float64)
    size = t.column("size").to_numpy(zero_copy_only=False).astype(np.float64)
    ts = t.column("ts").to_numpy(zero_copy_only=False).astype(np.int64)
    del t
    o = np.argsort(ts, kind="stable")
    price, size, ts = price[o], size[o], ts[o]
    assert np.all(np.diff(ts) >= 0)
    pc, vol, tsc = grammar.compress(price, size, ts)
    del price, size, ts
    piv, conf, dirs = grammar.decompose(pc, R * PT)
    n = len(piv)
    if n < 500:
        return None
    start = np.r_[0, piv[:-1]]
    S = np.abs(pc[piv] - pc[start]).astype(np.float64) / PT     # swing size, pts
    nch = (piv - start).astype(np.float64)                      # price changes
    dur = (tsc[piv] - tsc[start]).astype(np.float64) / 1e9      # seconds
    cvol = np.array([vol[a:b].sum() for a, b in zip(start, piv)])

    # ---- the NEW leg, the one we would be entering, at its confirmation ----
    # it has already travelled exactly R points; how fast, and on what volume?
    cnch = (conf - piv).astype(np.float64)                      # changes for R
    cdur = (tsc[conf] - tsc[piv]).astype(np.float64) / 1e9
    cvl = np.array([vol[a:b].sum() for a, b in zip(piv, conf)])

    # the OUTCOME: this same leg's eventual full size, so captured = S_next-2R
    S_next = np.r_[S[1:], np.nan]
    captured = S_next - 2.0 * R

    med = lambda a, w=100: (  # noqa: E731
        __import__("pandas").Series(a).rolling(w, min_periods=min(30, w))
        .median().shift(1).values)

    F = {
        "leg_size": S / np.maximum(med(S), 1e-9),
        "leg_speed": (S / np.maximum(nch, 1)) /
                     np.maximum(med(S / np.maximum(nch, 1)), 1e-9),
        "leg_secs": dur / np.maximum(med(dur), 1e-9),
        "leg_vol": cvol / np.maximum(med(cvol), 1e-9),
        "leg_vol_per_pt": (cvol / np.maximum(S, 1e-9)) /
                          np.maximum(med(cvol / np.maximum(S, 1e-9)), 1e-9),
        "retrace": S / np.maximum(np.r_[np.nan, S[:-1]], 1e-9),
        "conf_changes": cnch / np.maximum(med(cnch), 1e-9),
        "conf_secs": cdur / np.maximum(med(cdur), 1e-9),
        "conf_speed": (R / np.maximum(cnch, 1)) /
                      np.maximum(med(R / np.maximum(cnch, 1)), 1e-9),
        "conf_vol": cvl / np.maximum(med(cvl), 1e-9),
        "conf_vs_leg_vol": (cvl / np.maximum(cvol, 1e-9)) /
                           np.maximum(med(cvl / np.maximum(cvol, 1e-9)), 1e-9),
        "vol_regime": med(S, 20) / np.maximum(med(S, 200), 1e-9),
        "two_back": np.r_[np.nan, S[:-1]] / np.maximum(med(S), 1e-9),
        "dir": dirs.astype(np.float64),
    }
    out = {k: v.astype(np.float32) for k, v in F.items()}
    out["captured"] = captured.astype(np.float32)
    out["S_next"] = S_next.astype(np.float32)
    os.makedirs(CACHE, exist_ok=True)
    np.savez_compressed(cp, **out)
    return out


files = sorted(glob.glob(os.path.join(RAW, "NQ*.parquet")))
log("# Can we tell which swings will run? The selectivity test")
log()
log("The 2R law says the AVERAGE confirmed swing captures nothing. This asks "
    "whether swings differ from each other in a way that is visible at "
    "confirmation — which is exactly what a discretionary trader relies on "
    "when they skip the ordinary setups and take the ones that look like they "
    "will run. If the answer is yes, selection alone converts a zero into an "
    "edge with **no improvement in direction calling at all**.")
log()
log("Quintile edges come from the five training contracts. Every number below "
    "is from the three held-out ones. Beside each real spread is the same "
    "feature circularly shifted against the outcomes — same values, same "
    "distribution, no alignment. A feature only counts if it beats its shift.")
log()

for R in RS:
    per = {}
    for f in files:
        c = os.path.basename(f)[:-8]
        d = legs_for(c, f, R)
        if d is None:
            continue
        per[c] = d
        print(f"  R={R}pt {c}: {len(d['captured']):,} swings", flush=True)
    if not per:
        continue
    keys = [k for k in per[next(iter(per))] if k not in
            ("captured", "S_next", "dir")]
    tr = {k: np.concatenate([per[c][k] for c in per if c in TRAIN])
          for k in keys}
    ho = {k: np.concatenate([per[c][k] for c in per if c not in TRAIN])
          for k in keys}
    cap_ho = np.concatenate([per[c]["captured"] for c in per
                             if c not in TRAIN])
    sn_ho = np.concatenate([per[c]["S_next"] for c in per if c not in TRAIN])
    ok = np.isfinite(cap_ho)

    log(f"## Swings of {R}+ points")
    log()
    log(f"{int(ok.sum()):,} confirmed swings in the held-out contracts. "
        f"Average captured after entering and exiting late: "
        f"**{np.nanmean(cap_ho[ok]):+.2f} points "
        f"(${np.nanmean(cap_ho[ok])*USD_PT:+.2f})** against ${COST:.2f} of "
        f"cost — the 2R law, restated on the holdout.")
    log()
    q = np.nanpercentile(sn_ho[ok], [50, 75, 90, 99])
    log(f"How fat is the tail? Swing length in multiples of R — "
        f"median **{q[0]/R:.2f}x**, 75th **{q[1]/R:.2f}x**, "
        f"90th **{q[2]/R:.2f}x**, 99th **{q[3]/R:.2f}x**. "
        f"Perfect selection of the top decile would capture "
        f"**{q[2]-2*R:+.1f} points (${(q[2]-2*R)*USD_PT:+.2f})** per trade. "
        f"That is the prize if any feature can find them.")
    log()
    log("| feature | Q1 (lowest) | Q2 | Q3 | Q4 | Q5 (highest) | best-worst "
        "spread | SHIFTED spread |")
    log("|---|---|---|---|---|---|---|---|")
    rows = []
    for k in keys:
        v_tr, v_ho = tr[k], ho[k]
        good = np.isfinite(v_tr)
        if good.sum() < 2000:
            continue
        edges = np.nanpercentile(v_tr[good], [20, 40, 60, 80])
        b = np.digitize(v_ho, edges)
        means, nulls = [], []
        vs = np.roll(v_ho, len(v_ho) // 3)          # the control
        bs = np.digitize(vs, edges)
        for i in range(5):
            m = ok & (b == i) & np.isfinite(v_ho)
            ms = ok & (bs == i) & np.isfinite(vs)
            means.append(np.nanmean(cap_ho[m]) if m.sum() > 200 else np.nan)
            nulls.append(np.nanmean(cap_ho[ms]) if ms.sum() > 200 else np.nan)
        if not np.isfinite(means).all():
            continue
        spread = max(means) - min(means)
        nspread = (max(nulls) - min(nulls) if np.isfinite(nulls).all()
                   else np.nan)
        rows.append((spread, nspread, k, means))
    for spread, nspread, k, means in sorted(rows, reverse=True):
        cells = " | ".join(f"{m*USD_PT:+.2f}" for m in means)
        flag = "**" if np.isfinite(nspread) and spread > 2 * nspread else ""
        log(f"| `{k}` | {cells} | {flag}${spread*USD_PT:.2f}{flag} | "
            f"${nspread*USD_PT:.2f} |")
    log()
    if rows:
        best = rows[0]
        log(f"Strongest separator: `{best[2]}`, spread "
            f"${best[0]*USD_PT:.2f} against a shifted spread of "
            f"${best[1]*USD_PT:.2f}. Every cell is dollars captured per trade "
            f"on one MNQ, BEFORE the ${COST:.2f} cost — so a quintile only "
            f"pays if its number exceeds ${COST:.2f}.")
    log()

log("---")
log("Swings are confirmation-anchored, so nothing uses hindsight. `captured` "
    "is swing size minus 2R, the real result of entering and exiting one "
    "confirmation late.")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w").write("\n".join(L) + "\n")
print("\nwrote", OUT)
