"""A2: does the order book predict forward returns, and at what horizon?

The pilot (research/DEPTH_PILOT.md) had one week and found quote rate at
IC -0.084 and spread at -0.056, but could not settle directional
imbalance -- one week cannot separate IC 0.03 from zero. This runs the
full feature set on the tape depth_buy_book.py produces.

It measures PREDICTORS, not strategies. Every previous search in this
repo bundled a prediction question with an execution question, so a
failure said nothing about which half failed. An information coefficient
cannot be cherry-picked, because nothing is being chosen.

FEATURES (the pilot's, plus everything it could not compute)
    imb            top-of-book size imbalance -- the unsettled question
    d_imb          CHANGE in imbalance: who is arriving, not who is here
    micro_dev      microprice minus mid, in ticks -- the fair-value tilt
    spread         spread in ticks
    qrate          quote intensity vs its own recent norm
    depl_skew      queue depletion, bid vs ask: which side is being eaten
    tt_press       trade-through pressure: signed traded volume share
    add_skew       size arriving at the bid vs the ask
    ofi            order-flow imbalance: the standard adds-minus-cancels
                   construction, sign-corrected for which side moved

HORIZONS  1s, 5s, 30s, 60s, 300s, 1800s.

CONTROLS, and the second is the one that decides anything
    shuffled     feature values in random order. Same distribution, no
                 relationship. Whatever IC this shows is what the
                 pipeline manufactures from nothing.
    time-shifted the forward return slid by hours and rejoined. BOTH
                 series keep their autocorrelation; only the alignment
                 dies. This matters more than the shuffle here, because
                 book features are heavily autocorrelated and a naive
                 3/sqrt(n) noise floor on a million overlapping seconds
                 would quote a precision the data does not have. The
                 SPREAD of IC across shift offsets IS the noise floor,
                 measured rather than assumed.

GATES, fixed here before the run
    |IC| >= 0.03, AND |IC| >= 3x the measured shift floor,
    AND the sign holds in >= 75% of weeks.

Then the question that kills most survivors: an IC only pays if
IC x sigma(horizon) beats the 0.87pt round-trip cost of an MNQ taker.
Anything that fails that is a FILTER for a longer-horizon strategy, not
a signal to trade on its own -- which is what Track B is for.

Output: research/BOOK_IC.md
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
DEPTH = os.path.join(ROOT, "data", "depth")
OUT = os.path.join(ROOT, "research", "BOOK_IC.md")
TICK = 0.25
COST_PT = 0.87                      # MNQ taker round trip, measured
HZ = [1, 5, 30, 60, 300, 1800]
SHIFTS = [1800, 3600, 7200, 14400, -1800, -3600, -7200, -14400]
FEATS = ["imb", "d_imb", "micro_dev", "spread", "qrate", "depl_skew",
         "tt_press", "add_skew", "ofi"]
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def ic(x, y):
    """Spearman by hand: Pearson on ranks.

    pandas routes method="spearman" through scipy, which is NOT installed
    in this container, and ranking is faster anyway.
    """
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 500:
        return np.nan
    a = pd.Series(x[ok]).rank().values
    b = pd.Series(y[ok]).rank().values
    a = a - a.mean()
    b = b - b.mean()
    den = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / den) if den > 0 else np.nan


def load(path):
    """Per-second tape -> a gap-aware regular grid.

    The tape only carries seconds that had at least one event, and the
    feed has real holes: the daily maintenance halt, weekends, and
    whatever the exchange felt like. A forward return computed straight
    across one of those holes is not a 30-second return, it is an
    overnight return wearing a 30-second label, and it would be the
    single easiest way to manufacture an IC here.
    """
    A = pd.read_parquet(path).sort_values("sec").reset_index(drop=True)
    full = np.arange(int(A["sec"].iloc[0]), int(A["sec"].iloc[-1]) + 1)
    A = A.set_index("sec").reindex(full)
    present = A["bid_px"].notna().values
    state = ["bid_px", "ask_px", "bid_sz", "ask_sz"]
    A[state] = A[state].ffill()
    flow = ["n_evt", "n_trade", "tv_buy", "tv_sell", "bid_depl",
            "ask_depl", "bid_add", "ask_add"]
    A[flow] = A[flow].fillna(0.0)
    A["present"] = present
    A = A.dropna(subset=state)
    return A


def build(A):
    bp = A["bid_px"].values.astype(np.float64)
    ap = A["ask_px"].values.astype(np.float64)
    bs = A["bid_sz"].values.astype(np.float64)
    a_s = A["ask_sz"].values.astype(np.float64)
    tot = np.maximum(bs + a_s, 1.0)
    mid = (bp + ap) / 2.0
    F = {}
    F["imb"] = (bs - a_s) / tot
    F["d_imb"] = np.r_[np.nan, np.diff(F["imb"])]
    # microprice weights each side by the size on the OPPOSITE side: a
    # heavy bid pushes fair value up toward the ask.
    micro = (bp * a_s + ap * bs) / tot
    F["micro_dev"] = (micro - mid) / TICK
    F["spread"] = (ap - bp) / TICK
    q = A["n_evt"].values.astype(np.float64)
    norm = pd.Series(q).rolling(600, min_periods=120).mean().values
    F["qrate"] = q / np.maximum(norm, 1e-9)
    bd = A["bid_depl"].values.astype(np.float64)
    ad = A["ask_depl"].values.astype(np.float64)
    F["depl_skew"] = (ad - bd) / np.maximum(ad + bd, 1.0)
    tb = A["tv_buy"].values.astype(np.float64)
    ts_ = A["tv_sell"].values.astype(np.float64)
    F["tt_press"] = (tb - ts_) / np.maximum(tb + ts_, 1.0)
    ba = A["bid_add"].values.astype(np.float64)
    aa = A["ask_add"].values.astype(np.float64)
    F["add_skew"] = (ba - aa) / np.maximum(ba + aa, 1.0)
    # order-flow imbalance: net size added to the bid minus net added to
    # the ask, which is the adds-minus-cancels construction on a tape
    # that already separates the two.
    F["ofi"] = ((ba - bd) - (aa - ad)) / np.maximum(ba + bd + aa + ad, 1.0)
    return F, mid


def forward(mid, present, h):
    """h-second forward return in points, invalid across feed holes."""
    n = len(mid)
    y = np.full(n, np.nan)
    y[:n - h] = mid[h:] - mid[:n - h]
    # require the window to be mostly real data, not forward-filled hole
    dens = pd.Series(present.astype(np.float64)).rolling(
        h, min_periods=1).mean().shift(-h).values
    y[~(dens >= 0.5)] = np.nan
    y[~present] = np.nan
    return y


def main():
    files = sorted(glob.glob(os.path.join(DEPTH, "*_book_1s.parquet")))
    if not files:
        print("no data/depth/*_book_1s.parquet yet -- A1 has not run.")
        print("stage a plan line in data/depth/.buy and push to trigger it.")
        return
    # Each symbol is reduced on its OWN timeline. Concatenating the tapes
    # first and differencing afterwards would compute a forward return
    # from the end of one symbol's book to the start of another's, which
    # is not a return at all.
    parts, syms = [], []
    for f in files:
        sym = os.path.basename(f).split("_book_1s")[0]
        A = load(f)
        F1, mid1 = build(A)
        parts.append(dict(F=F1, mid=mid1,
                          present=A["present"].values,
                          sec=A.index.values.astype(np.int64)))
        syms.append(sym)
        print(f"  {sym}: {len(A):,} seconds, "
              f"{A['present'].mean():.0%} carried an event", flush=True)
        del A

    F = {k: np.concatenate([p["F"][k] for p in parts]) for k in FEATS}
    present = np.concatenate([p["present"] for p in parts])
    sec = np.concatenate([p["sec"] for p in parts])
    week = (sec // (7 * 86400))
    rng = np.random.default_rng(11)
    F["shuffled"] = rng.permutation(F["imb"])
    nsec = len(sec)

    nweeks = len(np.unique(week))
    log("# A2: does the order book predict forward returns?")
    log()
    log(f"`{nsec:,}` seconds of top of book across "
        f"{len(syms)} symbol(s) and {nweeks} weeks, "
        f"{present.mean():.0%} of them carrying at least one event. "
        f"Forward returns are invalidated across feed holes -- a 30-second "
        f"return computed over the maintenance halt is an overnight return "
        f"wearing a 30-second label, and it is the easiest way to "
        f"manufacture an IC here.")
    log()
    log("`shift floor` is the standard deviation of the same IC with the "
        "forward return slid by 0.5-4 hours in both directions. Both "
        "series keep their autocorrelation and only the alignment dies, "
        "so it measures what this pipeline produces from nothing at THIS "
        "sample's dependence structure. A naive 3/sqrt(n) on a million "
        "overlapping seconds would quote a precision the data does not "
        "have.")
    log()

    results = []
    for h in HZ:
        y = np.concatenate([forward(p["mid"], p["present"], h)
                            for p in parts])
        sig = float(np.nanstd(y))
        log(f"## {h}s ahead (sigma = {sig:.2f} pt)")
        log()
        log("| feature | IC | shift floor | IC/floor | weeks same sign | "
            "edge = IC x sigma | vs 0.87pt cost |")
        log("|---|---|---|---|---|---|---|")
        for name in FEATS + ["shuffled"]:
            x = F[name]
            v = ic(x, y)
            sh = [ic(x, np.roll(y, s)) for s in SHIFTS]
            floor = float(np.nanstd(sh)) if np.isfinite(sh).any() else np.nan
            per = []
            for w in np.unique(week):
                m = week == w
                if m.sum() < 5000:
                    continue
                per.append(ic(x[m], y[m]))
            per = [p for p in per if np.isfinite(p)]
            same = (float(np.mean([np.sign(p) == np.sign(v) for p in per]))
                    if per and np.isfinite(v) else np.nan)
            edge = abs(v) * sig if np.isfinite(v) else np.nan
            ratio = abs(v) / floor if floor and floor > 0 else np.nan
            log(f"| {name} | {v:+.4f} | {floor:.4f} | {ratio:.1f} | "
                f"{same:.0%} | {edge:.3f} pt | "
                f"{'**clears**' if edge > COST_PT else 'below'} |")
            results.append(dict(h=h, name=name, ic=v, floor=floor,
                                ratio=ratio, same=same, edge=edge,
                                sigma=sig))
        log()

    R = pd.DataFrame(results)
    R = R[R.name != "shuffled"]
    passed = R[(R.ic.abs() >= 0.03) & (R.ratio >= 3.0) & (R.same >= 0.75)]
    log("## Verdict against the gates fixed before the run")
    log()
    log("`|IC| >= 0.03`, `|IC| >= 3x the shift floor`, sign holds in "
        ">= 75% of weeks.")
    log()
    if not len(passed):
        log("**No feature/horizon combination passes.** The book does not "
            "predict direction at these horizons on this sample, and no "
            "execution scheme built on it would either.")
    else:
        log(f"**{len(passed)} combinations pass.**")
        log()
        log("| feature | horizon | IC | edge | tradable alone? |")
        log("|---|---|---|---|---|")
        for _, r in passed.sort_values("ic", key=abs,
                                       ascending=False).iterrows():
            log(f"| {r['name']} | {r['h']}s | {r['ic']:+.4f} | "
                f"{r['edge']:.3f} pt | "
                f"{'yes' if r['edge'] > COST_PT else 'NO -- filter only'} |")
        log()
        tradable = passed[passed.edge > COST_PT]
        if not len(tradable):
            log("Every survivor is real but too small to pay its own way: "
                f"none reaches the {COST_PT}pt round-trip cost of an MNQ "
                "taker at its horizon. That does not make them worthless "
                "-- it makes them **filters** on a longer-horizon "
                "strategy, which is what Track B is for. It does mean "
                "none of them is a standalone system.")
        else:
            log("These clear the cost of trading them directly and earn a "
                "full causal validation.")
    log()
    open(OUT, "w").write("\n".join(L) + "\n")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
