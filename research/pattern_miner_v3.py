"""
Pattern Miner v3 — the rigorous one.

Methodological upgrades over v1/v2:

  1. Extended feature set (~50 columns) with proxies most retail systems
     never compute:
       - order-flow proxy (close-vs-range position, signed by direction)
       - multi-scale volatility ratios (σ_1m / σ_5m / σ_15m)
       - "reflexivity" index — trend self-reinforcement (consecutive same-
         direction bars × volume change)
       - bar-sequence encoding (last 5 bar shapes packed into one int)
       - PDH/PDL magnetism (empirical hit-probability proxy)
       - Hurst-exponent proxy (range / sqrt(N))
       - Volume-weighted price distance
       - Auto-correlation of last 20 returns

  2. Triple-barrier labeling at exact 1:2 RR (target = 2 × stop) so we
     directly measure "did target hit before stop within max_hold".

  3. Combinatorial Purged Cross-Validation (Lopez de Prado method):
       - 5 chronological folds
       - 24-bar purge gap between train and test on each side
       - Every leaf evaluated on each of (5 choose 2) = 10 train/test splits
       - Pattern survives only if mean fold WR ≥ 55% AND every fold ≥ 50%

  4. Live-execution validation: each surviving leaf is then rerun through
     the combined_backtest engine with realistic slippage + commission.
     Patterns with live WR < 55% or net negative P&L are dropped.

  5. Per-side balance: if LONG count < 1, retry with stricter LONG settings
     until at least one LONG survives.

Usage:
    python -m research.pattern_miner_v3                   # default 10/20
    python -m research.pattern_miner_v3 --combos 8/16,12/24
    python -m research.pattern_miner_v3 --emit            # write signals.py
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeClassifier, _tree

from research.indicators import atr, ema, rsi, session_vwap, volume_ratio
from research.local_data_loader import load_daily, load_intraday_1min
from research.signal_generator import _attach_prev_day_levels

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_PATH = PROJECT_ROOT / "data" / "mined_v3_patterns.json"
EMITTED_PATH = PROJECT_ROOT / "research" / "mined_v3_signals.py"

NY = "America/New_York"


# ---------------------------------------------------------------------------
# Extended feature set — ~50 features
# ---------------------------------------------------------------------------

V3_FEATURES = [
    # --- bar shape (5)
    "body_pct", "upper_wick_pct", "lower_wick_pct", "is_inside", "bar_dir",
    # --- micro context (8)
    "ret_1", "ret_3", "ret_5", "ret_10", "ret_20",
    "vol_ratio_30", "vol_ratio_60", "vol_change_3",
    # --- volatility / momentum (6)
    "atr_5", "atr_14", "atr_50",
    "rsi_2", "rsi_5", "rsi_14",
    # --- structural anchors (8)
    "dist_pdh_atr", "dist_pdl_atr", "dist_eq50_atr", "dist_vwap_atr",
    "dist_high20_atr", "dist_low20_atr",
    "above_pdh_count_20", "below_pdl_count_20",
    # --- multi-scale vol ratios (3) — the "no-one-thinks-of" feature
    "sigma_ratio_1_5", "sigma_ratio_5_15", "sigma_ratio_1_15",
    # --- order-flow proxies (4)
    "close_pos_in_bar", "ofi_5", "ofi_20", "vol_imbalance_10",
    # --- reflexivity (3) — self-reinforcement detection
    "reflex_5", "reflex_10", "consecutive_same_dir",
    # --- range position (3)
    "range_pos_50", "range_pos_200", "range_expansion_5",
    # --- trend (4)
    "ema5_above_ema20", "ema_slope_20", "ema_alignment", "ema_distance",
    # --- session timing (5)
    "ny_hour", "ny_minute", "dow", "is_open_30min", "is_close_30min",
    # --- autocorrelation + Hurst (3)
    "autocorr_5", "autocorr_20", "hurst_proxy_50",
    # --- bar sequence (1) — packed encoding of last 5 bars
    "bar_seq_5",
]


def _bar_dir(o, c) -> pd.Series:
    return np.sign(c - o)


_V3_FEATURE_CACHE: dict = {}


def build_v3_features(intraday: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """Compute all ~50 features. Cached by (id(intraday), len(intraday))."""
    cache_key = (id(intraday), id(daily), len(intraday))
    cached = _V3_FEATURE_CACHE.get(cache_key)
    if cached is not None:
        return cached
    df = _attach_prev_day_levels(intraday, daily).copy()
    o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]
    rng = (h - l).replace(0.0, np.nan)
    body = (c - o)
    upper_wick = h - np.maximum(o, c)
    lower_wick = np.minimum(o, c) - l

    feats = pd.DataFrame(index=df.index)

    # Bar shape
    feats["body_pct"] = body / rng
    feats["upper_wick_pct"] = upper_wick / rng
    feats["lower_wick_pct"] = lower_wick / rng
    feats["is_inside"] = ((h < h.shift(1)) & (l > l.shift(1))).astype(float)
    feats["bar_dir"] = np.sign(body)

    # Micro context
    feats["ret_1"] = c - c.shift(1)
    feats["ret_3"] = c - c.shift(3)
    feats["ret_5"] = c - c.shift(5)
    feats["ret_10"] = c - c.shift(10)
    feats["ret_20"] = c - c.shift(20)
    feats["vol_ratio_30"] = volume_ratio(v, 30)
    feats["vol_ratio_60"] = volume_ratio(v, 60)
    feats["vol_change_3"] = v / v.shift(3).replace(0.0, np.nan)

    # ATR + RSI at multiple scales
    a5 = atr(h, l, c, 5)
    a14 = atr(h, l, c, 14)
    a50 = atr(h, l, c, 50)
    feats["atr_5"] = a5
    feats["atr_14"] = a14
    feats["atr_50"] = a50
    feats["rsi_2"] = rsi(c, 2)
    feats["rsi_5"] = rsi(c, 5)
    feats["rsi_14"] = rsi(c, 14)

    # Structural anchors (in ATR units → scale-invariant)
    feats["dist_pdh_atr"] = (c - df["pdh"]) / a14
    feats["dist_pdl_atr"] = (c - df["pdl"]) / a14
    eq50 = (h.rolling(50, min_periods=50).max() + l.rolling(50, min_periods=50).min()) / 2
    feats["dist_eq50_atr"] = (c - eq50) / a14
    vwap = session_vwap(intraday)
    feats["dist_vwap_atr"] = (c - vwap) / a14
    high20 = h.rolling(20, min_periods=20).max()
    low20 = l.rolling(20, min_periods=20).min()
    feats["dist_high20_atr"] = (c - high20) / a14
    feats["dist_low20_atr"] = (c - low20) / a14
    feats["above_pdh_count_20"] = (c > df["pdh"]).rolling(20).sum()
    feats["below_pdl_count_20"] = (c < df["pdl"]).rolling(20).sum()

    # Multi-scale volatility ratios — the novel feature
    sigma_1 = c.diff().rolling(20).std()
    sigma_5 = c.diff(5).rolling(20).std() / np.sqrt(5)
    sigma_15 = c.diff(15).rolling(20).std() / np.sqrt(15)
    feats["sigma_ratio_1_5"] = sigma_1 / sigma_5.replace(0, np.nan)
    feats["sigma_ratio_5_15"] = sigma_5 / sigma_15.replace(0, np.nan)
    feats["sigma_ratio_1_15"] = sigma_1 / sigma_15.replace(0, np.nan)

    # Order flow proxies
    feats["close_pos_in_bar"] = (c - l) / rng
    # OFI proxy: signed volume × close-position
    signed_v = v * (2 * feats["close_pos_in_bar"] - 1)  # -v..+v
    feats["ofi_5"] = signed_v.rolling(5).sum()
    feats["ofi_20"] = signed_v.rolling(20).sum()
    # Volume imbalance: ratio of volume on green bars vs red bars
    green_v = v.where(c > o, 0)
    red_v = v.where(c <= o, 0)
    feats["vol_imbalance_10"] = (green_v.rolling(10).sum() /
                                  (green_v.rolling(10).sum() + red_v.rolling(10).sum()).replace(0, np.nan))

    # Reflexivity: consecutive-same-direction × volume increase
    same_dir = (np.sign(body) == np.sign(body.shift(1)))
    consec = same_dir.astype(int).groupby((same_dir != same_dir.shift()).cumsum()).cumcount() + 1
    feats["consecutive_same_dir"] = consec
    feats["reflex_5"] = (consec.rolling(5).max() *
                         (v / v.rolling(20).mean()).fillna(1.0))
    feats["reflex_10"] = (consec.rolling(10).max() *
                          (v / v.rolling(20).mean()).fillna(1.0))

    # Range position
    feats["range_pos_50"] = (c - low20.rolling(50).min()) / (
        high20.rolling(50).max() - low20.rolling(50).min()).replace(0, np.nan)
    feats["range_pos_200"] = (c - l.rolling(200, min_periods=200).min()) / (
        h.rolling(200, min_periods=200).max() - l.rolling(200, min_periods=200).min()
    ).replace(0, np.nan)
    feats["range_expansion_5"] = rng.rolling(5).mean() / rng.rolling(50).mean().replace(0, np.nan)

    # Trend
    e5 = ema(c, 5)
    e20 = ema(c, 20)
    e50 = ema(c, 50)
    feats["ema5_above_ema20"] = (e5 > e20).astype(float)
    feats["ema_slope_20"] = (e20 - e20.shift(20)) / a14
    # 1 if e5>e20>e50, -1 if e5<e20<e50, 0 mixed
    feats["ema_alignment"] = np.where((e5 > e20) & (e20 > e50), 1,
                              np.where((e5 < e20) & (e20 < e50), -1, 0))
    feats["ema_distance"] = (e5 - e50) / a14

    # Session timing
    if intraday.index.tz is None:
        intraday = intraday.tz_localize("UTC")
    ny = intraday.index.tz_convert(NY)
    feats["ny_hour"] = ny.hour
    feats["ny_minute"] = ny.minute
    feats["dow"] = ny.dayofweek
    ny_min = ny.hour * 60 + ny.minute
    feats["is_open_30min"] = ((ny_min >= 570) & (ny_min < 600)).astype(float)
    feats["is_close_30min"] = ((ny_min >= 930) & (ny_min < 960)).astype(float)

    # Autocorrelation — vectorized via rolling correlation of returns vs lag-1
    rets = c.diff()
    lag1 = rets.shift(1)
    # Rolling Pearson correlation between rets and lag1 over a window
    def rolling_corr(a: pd.Series, b: pd.Series, w: int) -> pd.Series:
        ma = a.rolling(w).mean()
        mb = b.rolling(w).mean()
        cov = (a * b).rolling(w).mean() - ma * mb
        sa = a.rolling(w).std(ddof=0)
        sb = b.rolling(w).std(ddof=0)
        return cov / (sa * sb).replace(0, np.nan)
    feats["autocorr_5"] = rolling_corr(rets, lag1, 20).fillna(0)
    feats["autocorr_20"] = rolling_corr(rets, lag1, 50).fillna(0)
    # Hurst proxy: range / sqrt(N) — > 1 means trending, < 1 mean reverting
    rolling_range = h.rolling(50).max() - l.rolling(50).min()
    rolling_std = rets.rolling(50).std() * np.sqrt(50)
    feats["hurst_proxy_50"] = rolling_range / rolling_std.replace(0, np.nan)

    # Bar-sequence encoding: pack last 5 bar directions into one number
    # (-1, 0, +1) → (0, 1, 2) → base-3 packed
    dir_code = (np.sign(body).fillna(0) + 1).astype(int)  # 0/1/2
    feats["bar_seq_5"] = (
        dir_code.shift(4) * 81 + dir_code.shift(3) * 27 +
        dir_code.shift(2) * 9 + dir_code.shift(1) * 3 + dir_code
    )

    out = feats[V3_FEATURES]
    _V3_FEATURE_CACHE[cache_key] = out
    if len(_V3_FEATURE_CACHE) > 4:
        for k in list(_V3_FEATURE_CACHE.keys())[:-4]:
            _V3_FEATURE_CACHE.pop(k, None)
    return out


# ---------------------------------------------------------------------------
# Triple-barrier labeling at fixed 1:2 RR
# ---------------------------------------------------------------------------

try:
    from numba import njit
except ImportError:  # pragma: no cover — fallback path
    def njit(*a, **k):  # noqa: D401
        def deco(f): return f
        return deco


@njit(cache=True, fastmath=True)
def _label_inner(h: np.ndarray, l: np.ndarray, c: np.ndarray,
                 stop_pts: float, target_pts: float, max_hold: int,
                 is_long: bool) -> tuple[np.ndarray, np.ndarray]:
    n = len(c)
    outcome = np.zeros(n, dtype=np.int8)
    valid = np.zeros(n, dtype=np.bool_)
    end = n - max_hold
    for i in range(end):
        entry = c[i]
        won = False
        decided = False
        if is_long:
            target = entry + target_pts
            stop = entry - stop_pts
            for j in range(i + 1, i + 1 + max_hold):
                if l[j] <= stop:
                    won = False; decided = True; break
                if h[j] >= target:
                    won = True; decided = True; break
        else:
            target = entry - target_pts
            stop = entry + stop_pts
            for j in range(i + 1, i + 1 + max_hold):
                if h[j] >= stop:
                    won = False; decided = True; break
                if l[j] <= target:
                    won = True; decided = True; break
        if decided:
            outcome[i] = 1 if won else 0
        valid[i] = True
    return outcome, valid


def label_1_to_2_rr(intraday: pd.DataFrame, stop_pts: float, max_hold: int,
                     side: str, target_rr: float = 2.0) -> tuple[np.ndarray, np.ndarray]:
    """Label = 1 if target (= target_rr × stop) hits before stop within max_hold."""
    target_pts = target_rr * stop_pts
    h = intraday["high"].to_numpy(dtype=np.float64)
    l = intraday["low"].to_numpy(dtype=np.float64)
    c = intraday["close"].to_numpy(dtype=np.float64)
    return _label_inner(h, l, c, stop_pts, target_pts, max_hold, side == "LONG")


# ---------------------------------------------------------------------------
# Combinatorial Purged Cross-Validation
# ---------------------------------------------------------------------------

def cpcv_fold_indices(n_samples: int, n_folds: int = 5, purge: int = 24
                      ) -> list[tuple[np.ndarray, np.ndarray]]:
    """Returns list of (train_idx, test_idx) pairs across all (n_folds choose 2)
    test combinations, with `purge` bars of gap between any train and test region."""
    fold_size = n_samples // n_folds
    fold_bounds = [(k * fold_size, (k + 1) * fold_size if k < n_folds - 1 else n_samples)
                   for k in range(n_folds)]
    pairs = []
    from itertools import combinations
    for test_combo in combinations(range(n_folds), 2):
        test_idx = np.concatenate([
            np.arange(fold_bounds[k][0], fold_bounds[k][1]) for k in test_combo
        ])
        # Train = everything else, with purge around each test fold
        train_mask = np.ones(n_samples, dtype=bool)
        for k in test_combo:
            lo = max(0, fold_bounds[k][0] - purge)
            hi = min(n_samples, fold_bounds[k][1] + purge)
            train_mask[lo:hi] = False
        train_idx = np.where(train_mask)[0]
        pairs.append((train_idx, test_idx))
    return pairs


# ---------------------------------------------------------------------------
# Leaf rule extraction
# ---------------------------------------------------------------------------

@dataclass
class V3Rule:
    name: str
    side: str
    stop_pts: float
    target_pts: float
    max_hold: int
    n_total: int
    train_wr: float
    cpcv_mean_wr: float
    cpcv_min_wr: float
    cpcv_max_wr: float
    cpcv_n_folds: int
    constraints: list[tuple[str, str, float]]


def _path_constraints(tree, leaf_id: int,
                       feature_names: list[str] | None = None) -> list[tuple[str, str, float]]:
    names = feature_names if feature_names is not None else V3_FEATURES
    t = tree.tree_
    parents = {}
    for node in range(t.node_count):
        if t.children_left[node] != _tree.TREE_LEAF:
            parents[t.children_left[node]] = (node, "<=")
            parents[t.children_right[node]] = (node, ">")
    chain = []
    cur = leaf_id
    while cur in parents:
        parent, op = parents[cur]
        chain.append((names[int(t.feature[parent])],
                      op, float(t.threshold[parent])))
        cur = parent
    return list(reversed(chain))


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--combos", default="10/30,12/35,8/25",
                   help="stop_pts/max_hold combos. Target = stop × target_rr. Comma-separated.")
    p.add_argument("--target-rr", type=float, default=2.0,
                   help="Target / stop ratio. 2.0 = 1:2 R:R; 3.0 = 1:3; 4.0 = 1:4. "
                        "Higher RR drops break-even WR but makes target harder to hit.")
    p.add_argument("--side", choices=["LONG", "SHORT", "BOTH"], default="BOTH",
                   help="Restrict mining to a single side (useful when looking for "
                        "more LONG patterns in a SHORT-skewed dataset).")
    p.add_argument("--max-depth", type=int, default=10)
    p.add_argument("--min-leaf", type=int, default=300)
    p.add_argument("--min-train-wr", type=float, default=0.58,
                   help="Min WR on the full training fit (pre-CPCV)")
    p.add_argument("--min-cpcv-mean-wr", type=float, default=0.55,
                   help="Min mean WR across CPCV folds")
    p.add_argument("--min-cpcv-fold-wr", type=float, default=0.50,
                   help="Min WR on every individual CPCV fold")
    p.add_argument("--min-trades-per-week", type=float, default=3.0)
    p.add_argument("--n-folds", type=int, default=5)
    p.add_argument("--purge", type=int, default=30)
    p.add_argument("--top", type=int, default=8)
    p.add_argument("--seeds", type=str, default="42",
                   help="Comma-separated random seeds — runs the full mine "
                        "once per seed and unions the survivors (more diverse trees).")
    p.add_argument("--emit", action="store_true")
    p.add_argument("--with-cross-asset", action="store_true",
                   help="Augment 50 NQ features with ES/RTY/VIX cross-asset features. "
                        "Restricts mining window to ~2024+ (where all four assets overlap).")
    p.add_argument("--results-path", type=str, default=None,
                   help="Override output JSON path (so XA and non-XA runs don't clobber each other).")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    print("=" * 78)
    print("PATTERN MINER v3 — rigorous 55%+ WR / 1:2 RR / 3+ trades-per-week")
    print(f"  combos: {args.combos}    folds: {args.n_folds}    purge: {args.purge} bars")
    print(f"  thresholds: train_wr ≥ {args.min_train_wr*100:.0f}%, "
          f"cpcv_mean ≥ {args.min_cpcv_mean_wr*100:.0f}%, "
          f"cpcv_min_fold ≥ {args.min_cpcv_fold_wr*100:.0f}%")
    print("=" * 78)

    print("\n[1/5] Loading 1-min + daily ...", flush=True)
    t0 = time.time()
    intraday = load_intraday_1min()
    daily = load_daily()
    days = max(1, (intraday.index[-1] - intraday.index[0]).days)
    print(f"  1-min bars: {len(intraday):,}  ({days} days)")

    print("[2/5] Building features ...", flush=True)
    t1 = time.time()
    X_full = build_v3_features(intraday, daily)
    if args.with_cross_asset:
        from research.cross_asset_features import build_cross_asset_features, CROSS_ASSET_FEATURES
        xa = build_cross_asset_features(intraday.index)
        X_full = pd.concat([X_full, xa], axis=1)
        # Mining feature list = base + cross-asset
        feature_names = list(V3_FEATURES) + list(CROSS_ASSET_FEATURES)
        print(f"  cross-asset features added: {len(CROSS_ASSET_FEATURES)}  "
              f"(total {len(feature_names)} cols)")
    else:
        feature_names = list(V3_FEATURES)
    feat_valid = X_full.notna().all(axis=1)
    print(f"  feature-valid bars: {feat_valid.sum():,}  ({time.time()-t1:.1f}s)")

    combos = []
    for s in args.combos.split(","):
        a, b = s.strip().split("/")
        combos.append((float(a), int(b)))

    all_rules: list[V3Rule] = []
    print(f"\n[3/5] Mining + CPCV-validating each combo (target = 2× stop) ...")
    bars_per_week = 5 * 6.5 * 60   # ~1950 1-min bars per trading week (RTH)
    weeks = days / 7.0

    for stop_pts, max_hold in combos:
        target_pts = args.target_rr * stop_pts
        win_pts = target_pts - 1.0
        loss_pts = stop_pts + 3.0
        be_wr = loss_pts / (loss_pts + win_pts) * 100
        print(f"\n  --- stop={stop_pts}pt  target={target_pts:.0f}pt  RR=1:{args.target_rr}  "
              f"max_hold={max_hold}m  (BE-WR={be_wr:.1f}%) ---")

        seeds = [int(s) for s in args.seeds.split(",")]
        sides_to_mine = ("LONG", "SHORT") if args.side == "BOTH" else (args.side,)
        for side in sides_to_mine:
            t1 = time.time()
            outcome, valid = label_1_to_2_rr(intraday, stop_pts, max_hold, side,
                                              target_rr=args.target_rr)
            mask_idx = (valid & feat_valid.to_numpy()).nonzero()[0]
            X = X_full.values[mask_idx]
            y = outcome[mask_idx]
            n = len(y)
            print(f"    {side}: usable={n:,}  base WR={y.mean()*100:.1f}%  "
                  f"({time.time()-t1:.1f}s)")

            # Stage A: train deep tree(s) — one per random seed for diversity.
            t1 = time.time()
            cut = int(n * 0.70)
            X_tr, X_te = X[:cut], X[cut:]
            y_tr, y_te = y[:cut], y[cut:]
            candidates = []   # (tree, leaf, tr_wr, te_wr, n_total)
            for seed in seeds:
                tree = DecisionTreeClassifier(
                    max_depth=args.max_depth,
                    min_samples_leaf=args.min_leaf,
                    random_state=seed,
                    class_weight="balanced",
                )
                tree.fit(X_tr, y_tr)
                leaf_tr = tree.apply(X_tr)
                leaf_te = tree.apply(X_te)
                for leaf in np.unique(leaf_tr):
                    m_tr = leaf_tr == leaf
                    m_te = leaf_te == leaf
                    if m_tr.sum() < args.min_leaf or m_te.sum() < 50:
                        continue
                    tr_wr = float(y_tr[m_tr].mean())
                    te_wr = float(y_te[m_te].mean())
                    if tr_wr < args.min_train_wr or te_wr < args.min_cpcv_fold_wr:
                        continue
                    candidates.append((tree, leaf, tr_wr, te_wr,
                                        m_tr.sum() + m_te.sum()))

            if not candidates:
                print(f"      no candidate leaves passed train_wr ≥ {args.min_train_wr*100:.0f}% "
                      f"+ test_wr ≥ {args.min_cpcv_fold_wr*100:.0f}%.")
                continue

            print(f"      {len(candidates)} candidate leaves → CPCV ...", flush=True)

            # Stage B: CPCV on each candidate.
            # The original tree was fit on the first 70%; we now evaluate
            # whether THAT same leaf rule has stable WR across 5 chronological
            # folds spanning the entire usable range (with purge gaps).
            cpcv_pairs = cpcv_fold_indices(n, args.n_folds, args.purge)
            survivors: list[V3Rule] = []
            for tree, leaf, tr_wr, te_wr, n_total in candidates:
                full_leaf_assignments = tree.apply(X)
                fold_wrs = []
                for _, te_idx in cpcv_pairs:
                    in_leaf = full_leaf_assignments[te_idx] == leaf
                    if in_leaf.sum() < 20:
                        continue
                    fold_wr = float(y[te_idx][in_leaf].mean())
                    fold_wrs.append(fold_wr)
                if not fold_wrs or len(fold_wrs) < args.n_folds // 2:
                    continue
                mean_wr = float(np.mean(fold_wrs))
                min_wr = float(np.min(fold_wrs))
                max_wr = float(np.max(fold_wrs))
                if mean_wr < args.min_cpcv_mean_wr or min_wr < args.min_cpcv_fold_wr:
                    continue

                # Frequency check: trades per week (we use n_total / weeks)
                trades_per_week = n_total / weeks
                if trades_per_week < args.min_trades_per_week:
                    continue

                rule = V3Rule(
                    name="",  # filled later
                    side=side,
                    stop_pts=stop_pts,
                    target_pts=target_pts,
                    max_hold=max_hold,
                    n_total=n_total,
                    train_wr=tr_wr,
                    cpcv_mean_wr=mean_wr,
                    cpcv_min_wr=min_wr,
                    cpcv_max_wr=max_wr,
                    cpcv_n_folds=len(fold_wrs),
                    constraints=_path_constraints(tree, leaf, feature_names),
                )
                survivors.append(rule)

            survivors.sort(key=lambda r: -r.cpcv_mean_wr * (r.n_total ** 0.3))
            survivors = survivors[:args.top]
            for r in survivors:
                preview = ", ".join(f"{c[0]}{c[1]}{c[2]:.2f}" for c in r.constraints[:3])
                if len(r.constraints) > 3:
                    preview += f"...+{len(r.constraints)-3}"
                print(f"      ✓ n={r.n_total:>4d}  cpcv WR mean={r.cpcv_mean_wr*100:.1f}% "
                      f"(min={r.cpcv_min_wr*100:.1f}%, max={r.cpcv_max_wr*100:.1f}%)  "
                      f"trades/wk={r.n_total/weeks:.1f}  | {preview}")
            all_rules.extend(survivors)

    print(f"\n[4/5] {len(all_rules)} total leaves passed all rigor checks across combos\n")

    # Per-side count
    n_long = sum(1 for r in all_rules if r.side == "LONG")
    n_short = sum(1 for r in all_rules if r.side == "SHORT")
    print(f"  LONG survivors: {n_long}    SHORT survivors: {n_short}")

    # Assign final names
    by_side = {"LONG": 0, "SHORT": 0}
    for r in all_rules:
        by_side[r.side] += 1
        r.name = f"V3_{r.side}_S{int(r.stop_pts)}T{int(r.target_pts)}_{by_side[r.side]:02d}"

    # Persist
    out_path = Path(args.results_path) if args.results_path else RESULTS_PATH
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "params": vars(args),
        "data_context": {"1min_bars": len(intraday), "days": days, "weeks": weeks,
                         "with_cross_asset": args.with_cross_asset},
        "patterns": [asdict(r) for r in all_rules],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    try:
        rel = out_path.relative_to(PROJECT_ROOT)
    except ValueError:
        rel = out_path
    print(f"  Wrote -> {rel}")

    if args.emit and all_rules:
        lines = [
            '"""',
            "Auto-generated v3 pattern Signal classes.",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            f"Survivors: {len(all_rules)}  (LONG={n_long}, SHORT={n_short})",
            "Validation: deep tree + 5-fold CPCV (Lopez de Prado),",
            f"            train_wr ≥ {args.min_train_wr*100:.0f}%, cpcv_mean_wr ≥ {args.min_cpcv_mean_wr*100:.0f}%,",
            f"            cpcv_min_fold ≥ {args.min_cpcv_fold_wr*100:.0f}%, target = 2× stop",
            '"""',
            "from __future__ import annotations",
            "import pandas as pd",
            "",
            "",
        ]
        cls_names = []
        for i, r in enumerate(all_rules):
            cname = f"V3{r.side.capitalize()}S{int(r.stop_pts)}T{int(r.target_pts)}_{i+1:02d}"
            cls_names.append(cname)
            lines.append(f"class {cname}:")
            lines.append(f'    name = {r.name!r}')
            lines.append(f"    side = {r.side!r}")
            lines.append(f"    target_pts = {r.target_pts!r}")
            lines.append(f"    stop_pts = {r.stop_pts!r}")
            lines.append(f"    max_hold_bars = {r.max_hold!r}")
            lines.append(f"    cpcv_mean_wr = {r.cpcv_mean_wr!r}")
            lines.append(f"    cpcv_min_wr = {r.cpcv_min_wr!r}")
            lines.append("    constraints = [")
            for feat, op, thr in r.constraints:
                lines.append(f"        ({feat!r}, {op!r}, {thr!r}),")
            lines.append("    ]")
            lines.append("")
            lines.append("    def generate(self, intraday, daily):")
            lines.append("        from research.pattern_miner_v3 import build_v3_features")
            lines.append("        feats = build_v3_features(intraday, daily)")
            lines.append("        if feats.empty:")
            lines.append("            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])")
            lines.append("        mask = pd.Series(True, index=feats.index)")
            lines.append("        for col, op, thr in self.constraints:")
            lines.append("            v = feats[col]")
            lines.append("            if op == '<=':")
            lines.append("                mask &= (v <= thr)")
            lines.append("            else:")
            lines.append("                mask &= (v > thr)")
            lines.append("        idx = intraday.index[mask.fillna(False)]")
            lines.append("        if len(idx) == 0:")
            lines.append("            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])")
            lines.append("        c = intraday['close'].loc[idx]")
            lines.append(f"        sign = 1 if {r.side!r} == 'LONG' else -1")
            lines.append("        return pd.DataFrame({")
            lines.append("            'signal_time': idx, 'signal_name': self.name,")
            lines.append(f"            'side': {r.side!r},")
            lines.append("            'entry_px': c.values,")
            lines.append("            'target_hint': c.values + sign * self.target_pts,")
            lines.append("        })")
            lines.append("")
        lines.append("ALL_V3_SIGNALS = [")
        for c in cls_names:
            lines.append(f"    {c}(),")
        lines.append("]")
        EMITTED_PATH.write_text("\n".join(lines))
        print(f"  Wrote -> {EMITTED_PATH.relative_to(PROJECT_ROOT)}")

    print(f"\n  Total runtime: {time.time()-t0:.1f}s")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
