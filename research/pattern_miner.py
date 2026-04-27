"""
Organic pattern mining on 2-year 1-min NQ history.

Methodology (no hand-coded patterns):

  1. For every 1-min bar, build a 25-feature vector describing:
       - bar shape (body/range, upper/lower wick proportions, is_inside)
       - micro context (3/5/10-bar return, vol-ratio, ATR, RSI(2/14))
       - structural (distance to PDH/PDL/EQ50/session VWAP)
       - time-of-day (NY hour/minute, day-of-week)
       - regime (5d/20d realized vol ratio)

  2. Compute the 10-bar forward return on close (the label) for both
     directions — net of round-trip cost in points (so we only mine
     for patterns with edge BIG enough to beat slippage + commission).

  3. Train a regression tree on the IN-SAMPLE 70% of bars.
     min_samples_leaf=300 keeps leaves robust; max_depth=8 keeps rules
     interpretable.

  4. For each leaf, compute mean forward return on (a) in-sample bars
     and (b) the held-out 30%. Keep only leaves where:
       - same sign on both halves                  (no overfit)
       - |out-of-sample mean| > 6 points          (beats cost)
       - >= 100 OOS samples                        (statistically meaningful)

  5. For each surviving leaf, extract the path from root to leaf as a
     human-readable list of (feature, op, threshold) constraints.
     That IS the entry rule.

  6. Emit Python source for each pattern as a Signal subclass that the
     existing backtest_engine can validate end-to-end.

This finds patterns *organically* in the data — every rule comes
from feature splits the tree chose, not from things I imagined.

Usage:
    python -m research.pattern_miner                    # FAST   (3 leaves max)
    python -m research.pattern_miner --top 20           # top 20 leaves
    python -m research.pattern_miner --emit             # also write
                                                          research/mined_signals.py
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeRegressor, _tree

from research.indicators import atr, ema, rsi, session_vwap, volume_ratio
from research.local_data_loader import load_daily, load_intraday_1min
from research.signal_generator import _attach_prev_day_levels

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_PATH = PROJECT_ROOT / "data" / "mined_patterns.json"
EMITTED_PATH = PROJECT_ROOT / "research" / "mined_signals.py"

NY = "America/New_York"


# ---------------------------------------------------------------------------
# Feature engineering — every bar gets the same 25 numbers
# ---------------------------------------------------------------------------

FEATURE_COLS = [
    # Bar shape
    "body_pct", "upper_wick_pct", "lower_wick_pct", "is_inside",
    # Micro context (recent moves)
    "ret_3", "ret_5", "ret_10", "vol_ratio_30",
    # Volatility / momentum
    "atr_14", "rsi_2", "rsi_14",
    # Structural anchors
    "dist_pdh_atr", "dist_pdl_atr", "dist_eq50_atr", "dist_vwap_atr",
    # Range / position
    "range_pos_50", "high_break_20", "low_break_20",
    # Trend
    "ema5_above_ema20", "ema_slope_20",
    # Session timing
    "ny_hour", "ny_minute", "dow", "is_open_30min", "is_close_30min",
]


def build_features(intraday: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame with FEATURE_COLS aligned to intraday.index.

    Cached by (id(intraday), id(daily)) to avoid recomputing for every
    Mined* signal class on the same data.
    """
    cache_key = (id(intraday), id(daily), len(intraday))
    cached = _FEATURE_CACHE.get(cache_key)
    if cached is not None:
        return cached
    df = _attach_prev_day_levels(intraday, daily).copy()
    o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]
    rng = (h - l).replace(0.0, np.nan)
    body = (c - o)
    upper_wick = h - np.maximum(o, c)
    lower_wick = np.minimum(o, c) - l

    feats = pd.DataFrame(index=df.index)
    feats["body_pct"] = body / rng
    feats["upper_wick_pct"] = upper_wick / rng
    feats["lower_wick_pct"] = lower_wick / rng
    feats["is_inside"] = ((h < h.shift(1)) & (l > l.shift(1))).astype(float)

    feats["ret_3"] = c - c.shift(3)
    feats["ret_5"] = c - c.shift(5)
    feats["ret_10"] = c - c.shift(10)
    feats["vol_ratio_30"] = volume_ratio(v, 30)

    a14 = atr(h, l, c, 14)
    feats["atr_14"] = a14
    feats["rsi_2"] = rsi(c, 2)
    feats["rsi_14"] = rsi(c, 14)

    # Distances to key levels, in ATR units (scale-invariant)
    feats["dist_pdh_atr"] = (c - df["pdh"]) / a14
    feats["dist_pdl_atr"] = (c - df["pdl"]) / a14
    eq50 = (h.rolling(50, min_periods=50).max() + l.rolling(50, min_periods=50).min()) / 2
    feats["dist_eq50_atr"] = (c - eq50) / a14
    vwap = session_vwap(intraday)
    feats["dist_vwap_atr"] = (c - vwap) / a14

    # Range position over last 50 bars
    hh50 = h.rolling(50, min_periods=50).max()
    ll50 = l.rolling(50, min_periods=50).min()
    feats["range_pos_50"] = (c - ll50) / (hh50 - ll50).replace(0.0, np.nan)
    feats["high_break_20"] = (c > h.rolling(20).max().shift(1)).astype(float)
    feats["low_break_20"] = (c < l.rolling(20).min().shift(1)).astype(float)

    # Trend
    e5 = ema(c, 5)
    e20 = ema(c, 20)
    feats["ema5_above_ema20"] = (e5 > e20).astype(float)
    feats["ema_slope_20"] = (e20 - e20.shift(20)) / a14

    # Session time
    if intraday.index.tz is None:
        intraday = intraday.tz_localize("UTC")
    ny = intraday.index.tz_convert(NY)
    feats["ny_hour"] = ny.hour
    feats["ny_minute"] = ny.minute
    feats["dow"] = ny.dayofweek
    ny_min = ny.hour * 60 + ny.minute
    feats["is_open_30min"] = ((ny_min >= 570) & (ny_min < 600)).astype(float)
    feats["is_close_30min"] = ((ny_min >= 930) & (ny_min < 960)).astype(float)

    # Reorder consistent
    out = feats[FEATURE_COLS]
    _FEATURE_CACHE[cache_key] = out
    if len(_FEATURE_CACHE) > 4:
        # bound cache
        for k in list(_FEATURE_CACHE.keys())[:-4]:
            _FEATURE_CACHE.pop(k, None)
    return out


_FEATURE_CACHE: dict = {}


def build_labels(intraday: pd.DataFrame, horizon: int = 10) -> pd.Series:
    """Forward-N-bar return on close (in points)."""
    return intraday["close"].shift(-horizon) - intraday["close"]


# ---------------------------------------------------------------------------
# Tree -> human-readable rules
# ---------------------------------------------------------------------------

class LeafRule(NamedTuple):
    leaf_id: int
    n_in_sample: int
    n_out_sample: int
    is_mean: float          # in-sample mean forward return (points)
    oos_mean: float         # out-of-sample mean forward return
    oos_std: float
    win_rate: float
    side: str               # LONG | SHORT
    constraints: list[tuple[str, str, float]]  # (feature, op, threshold)


def _path_constraints(tree, leaf_id: int) -> list[tuple[str, str, float]]:
    """Walk root->leaf and emit the chain of (feature, op, threshold) rules."""
    t = tree.tree_
    parents = {}
    for node in range(t.node_count):
        if t.children_left[node] != _tree.TREE_LEAF:
            parents[t.children_left[node]] = (node, "<=")
            parents[t.children_right[node]] = (node, ">")
    chain: list[tuple[str, str, float]] = []
    cur = leaf_id
    while cur in parents:
        parent, op = parents[cur]
        feat_idx = int(t.feature[parent])
        thresh = float(t.threshold[parent])
        chain.append((FEATURE_COLS[feat_idx], op, thresh))
        cur = parent
    return list(reversed(chain))


def find_leaves(tree, X_train, y_train, X_test, y_test,
                *, min_oos_n: int, min_oos_abs: float) -> list[LeafRule]:
    leaf_train = tree.apply(X_train)
    leaf_test = tree.apply(X_test)
    rules: list[LeafRule] = []
    for leaf in np.unique(leaf_train):
        m_is = leaf_train == leaf
        m_oos = leaf_test == leaf
        n_is = int(m_is.sum())
        n_oos = int(m_oos.sum())
        if n_oos < min_oos_n or n_is < min_oos_n:
            continue
        is_mean = float(y_train[m_is].mean())
        oos_mean = float(y_test[m_oos].mean())
        oos_std = float(y_test[m_oos].std(ddof=0)) if n_oos > 1 else 0.0
        if np.sign(is_mean) != np.sign(oos_mean):
            continue
        if abs(oos_mean) < min_oos_abs:
            continue
        side = "LONG" if oos_mean > 0 else "SHORT"
        if side == "LONG":
            wr = float((y_test[m_oos] > 0).mean())
        else:
            wr = float((y_test[m_oos] < 0).mean())
        constraints = _path_constraints(tree, leaf)
        rules.append(LeafRule(
            leaf_id=int(leaf),
            n_in_sample=n_is,
            n_out_sample=n_oos,
            is_mean=is_mean,
            oos_mean=oos_mean,
            oos_std=oos_std,
            win_rate=wr,
            side=side,
            constraints=constraints,
        ))
    return rules


# ---------------------------------------------------------------------------
# Code generation — convert a LeafRule into a Signal class source string
# ---------------------------------------------------------------------------

def emit_signal_class(rule: LeafRule, idx: int) -> tuple[str, str]:
    """Return (class_name, python_source)."""
    name = f"MINED_{rule.side}_{idx:02d}"
    lines = [f"class Mined{rule.side.capitalize()}{idx:02d}:"]
    lines.append(f'    name = "{name}"')
    lines.append("    side = " + repr(rule.side))
    lines.append("    expected_oos_mean = " + repr(rule.oos_mean))
    lines.append("    expected_oos_n = " + repr(rule.n_out_sample))
    lines.append("    constraints = [")
    for feat, op, thr in rule.constraints:
        lines.append(f"        ({feat!r}, {op!r}, {thr!r}),")
    lines.append("    ]")
    lines.append("")
    lines.append("    def generate(self, intraday, daily):")
    lines.append("        from research.pattern_miner import build_features, _empty_signals")
    lines.append("        feats = build_features(intraday, daily)")
    lines.append("        if feats.empty:")
    lines.append("            return _empty_signals()")
    lines.append("        mask = pd.Series(True, index=feats.index)")
    lines.append("        for col, op, thr in self.constraints:")
    lines.append("            v = feats[col]")
    lines.append("            if op == '<=':")
    lines.append("                mask &= (v <= thr)")
    lines.append("            else:")
    lines.append("                mask &= (v > thr)")
    lines.append("        idx = intraday.index[mask.fillna(False)]")
    lines.append("        if len(idx) == 0:")
    lines.append("            return _empty_signals()")
    lines.append("        c = intraday['close'].loc[idx]")
    lines.append("        return pd.DataFrame({")
    lines.append("            'signal_time': idx, 'signal_name': self.name,")
    lines.append(f"            'side': {rule.side!r},")
    lines.append("            'entry_px': c.values, 'target_hint': float('nan'),")
    lines.append("        })")
    return name, "\n".join(lines)


def _empty_signals() -> pd.DataFrame:
    return pd.DataFrame(columns=["signal_time", "signal_name", "side",
                                  "entry_px", "target_hint"])


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--horizon", type=int, default=10,
                   help="Forward-bar window for label (default 10 = 10 min)")
    p.add_argument("--max-depth", type=int, default=7)
    p.add_argument("--min-leaf", type=int, default=400,
                   help="Min in-sample samples per leaf")
    p.add_argument("--min-oos-n", type=int, default=100,
                   help="Min OOS samples per surviving leaf")
    p.add_argument("--min-edge-pts", type=float, default=6.0,
                   help="Min |OOS mean forward return| in points (must beat cost)")
    p.add_argument("--top", type=int, default=15,
                   help="Keep at most N leaves (best by |oos_mean|*sqrt(n))")
    p.add_argument("--emit", action="store_true",
                   help="Write surviving rules to research/mined_signals.py")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    print("=" * 78)
    print("ORGANIC PATTERN MINING — 2-year 1-min NQ history")
    print(f"  horizon={args.horizon} bars   max_depth={args.max_depth}   "
          f"min_leaf={args.min_leaf}   min_edge={args.min_edge_pts}pt")
    print("=" * 78)

    print("\n[1/5] Loading 1-min + daily ...", flush=True)
    t0 = time.time()
    intraday = load_intraday_1min()
    daily = load_daily()
    days = max(1, (intraday.index[-1] - intraday.index[0]).days)
    print(f"  1-min bars: {len(intraday):,}  ({days} days)")

    print("[2/5] Building features (25 columns) + labels ...", flush=True)
    t1 = time.time()
    X = build_features(intraday, daily)
    y = build_labels(intraday, horizon=args.horizon)
    df = pd.concat([X, y.rename("y")], axis=1).dropna()
    print(f"  usable bars: {len(df):,}  ({time.time()-t1:.1f}s)")

    n = len(df)
    cut = int(n * 0.70)
    X_train = df[FEATURE_COLS].iloc[:cut].to_numpy()
    y_train = df["y"].iloc[:cut].to_numpy()
    X_test = df[FEATURE_COLS].iloc[cut:].to_numpy()
    y_test = df["y"].iloc[cut:].to_numpy()
    print(f"  in-sample: {len(X_train):,}   out-of-sample: {len(X_test):,}")

    print("\n[3/5] Training regression tree ...", flush=True)
    t1 = time.time()
    tree = DecisionTreeRegressor(
        max_depth=args.max_depth,
        min_samples_leaf=args.min_leaf,
        random_state=42,
    )
    tree.fit(X_train, y_train)
    print(f"  trained in {time.time()-t1:.1f}s   nodes={tree.tree_.node_count}   "
          f"leaves={tree.get_n_leaves()}")

    print(f"\n[4/5] Filtering leaves "
          f"(same sign IS/OOS, |OOS mean| ≥ {args.min_edge_pts}pt, OOS n ≥ {args.min_oos_n}) ...")
    rules = find_leaves(tree, X_train, y_train, X_test, y_test,
                        min_oos_n=args.min_oos_n,
                        min_oos_abs=args.min_edge_pts)
    rules.sort(key=lambda r: -abs(r.oos_mean) * (r.n_out_sample ** 0.5))
    rules = rules[:args.top]
    print(f"  {len(rules)} leaves survived\n")

    if not rules:
        print("No patterns met the edge threshold. Try lowering --min-edge-pts.")
        return 0

    # Show summary
    print(f"  {'#':>2}  {'side':<6} {'n_oos':>6} {'IS mean':>9} {'OOS mean':>9} "
          f"{'WR':>6} {'rule preview':<30}")
    print("  " + "-" * 76)
    for i, r in enumerate(rules):
        depth = len(r.constraints)
        first_three = ", ".join(f"{c[0]}{c[1]}{c[2]:.2f}" for c in r.constraints[:3])
        if depth > 3:
            first_three += f"...+{depth-3}"
        print(f"  {i+1:>2}  {r.side:<6} {r.n_out_sample:>6,} "
              f"{r.is_mean:>+8.2f}p {r.oos_mean:>+8.2f}p {r.win_rate*100:>5.1f}%  "
              f"{first_three}")

    # Per-pattern detail
    print("\n[5/5] Per-pattern detail (root-to-leaf rule paths):")
    for i, r in enumerate(rules):
        print(f"\n  --- Pattern {i+1} (MINED_{r.side}_{i+1:02d}) ---")
        print(f"     n_oos={r.n_out_sample:,}   "
              f"oos_mean=+{r.oos_mean:.2f}pt" if r.side == "LONG"
              else f"     n_oos={r.n_out_sample:,}   oos_mean={r.oos_mean:.2f}pt")
        print(f"     in-sample mean={r.is_mean:+.2f}pt   win_rate={r.win_rate*100:.1f}%")
        print("     entry conditions:")
        for col, op, thr in r.constraints:
            print(f"       {col} {op} {thr:.4f}")

    # Persist
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "horizon_bars": args.horizon,
        "tree_params": {
            "max_depth": args.max_depth, "min_samples_leaf": args.min_leaf,
        },
        "filters": {
            "min_oos_n": args.min_oos_n, "min_edge_pts": args.min_edge_pts,
        },
        "data_context": {
            "1min_bars": len(intraday),
            "usable_bars": int(n),
            "in_sample": int(cut),
            "out_of_sample": int(n - cut),
        },
        "patterns": [
            {
                "name": f"MINED_{r.side}_{i+1:02d}",
                "side": r.side,
                "n_in_sample": r.n_in_sample,
                "n_out_sample": r.n_out_sample,
                "is_mean": r.is_mean,
                "oos_mean": r.oos_mean,
                "oos_std": r.oos_std,
                "win_rate": r.win_rate,
                "constraints": [
                    {"feature": c[0], "op": c[1], "threshold": c[2]}
                    for c in r.constraints
                ],
            }
            for i, r in enumerate(rules)
        ],
    }
    RESULTS_PATH.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\n  Wrote -> {RESULTS_PATH.relative_to(PROJECT_ROOT)}")

    if args.emit:
        # Emit Python module with one Signal class per pattern
        lines = [
            '"""',
            "Auto-generated from research.pattern_miner. DO NOT EDIT BY HAND.",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            f"Patterns: {len(rules)}   Source: 1-min NQ, {len(intraday):,} bars",
            '"""',
            "from __future__ import annotations",
            "import pandas as pd",
            "from research.pattern_miner import build_features, _empty_signals",
            "",
            "",
        ]
        names = []
        for i, r in enumerate(rules):
            cname, source = emit_signal_class(r, i + 1)
            names.append(cname)
            lines.append(source)
            lines.append("")
        lines.append(f"ALL_MINED_SIGNALS = [")
        for i, r in enumerate(rules):
            cls_basename = f"Mined{r.side.capitalize()}{i+1:02d}"
            lines.append(f"    {cls_basename}(),")
        lines.append("]")
        EMITTED_PATH.write_text("\n".join(lines))
        print(f"  Wrote -> {EMITTED_PATH.relative_to(PROJECT_ROOT)}")

    print(f"\n  Total runtime: {time.time()-t0:.1f}s")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
