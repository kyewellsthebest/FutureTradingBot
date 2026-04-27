"""
Pattern Miner v4 — completely new strategy hunt.

Why v4 exists:
  v3 found 10 gold-standard patterns but they all anchored on
  dist_pdh_atr / dist_pdl_atr (the same structural feature your existing
  whitelist already exploits). To find GENUINELY NEW edges we have to
  force the tree to look elsewhere.

Approach:
  1. Drop PDH/PDL distance features entirely from the feature set.
  2. Add ~30 NEW features the v3 set didn't have:
       - Multi-bar sequence pattern features (n-of-last-N bars green/red,
         consecutive-higher-high count, "hammer" / "shooting star" flags)
       - Time-cohort interactions (hour × bar_dir, hour × atr regime)
       - Volume profile proxies (distance to recent VPOC = price with
         max volume in last N bars)
       - Range-shift features (range expansion/contraction velocity)
       - Wick/reversal patterns (long upper wick + bearish close, etc.)
       - Inter-scale momentum agreement (3-bar return × 10-bar return sign)
       - RTH vs non-RTH conditioning
       - Bar-since-event features (bars since last X-pt move)

  3. Use a deep DecisionTreeClassifier (depth 12) — capable of finding
     deeper feature interactions than v3.

  4. Triple-barrier labels at 1:2 RR (10/20, 12/24, 15/30, 8/16).

  5. CPCV gate (mean ≥ 55%, every fold ≥ 50%).

  6. Then validate_v4_full runs the full 5-test rigor gauntlet on each
     CPCV survivor.

Expected differences from v3:
  - Patterns will key off SEQUENCE / TIMING / VOLUME-PROFILE features
    instead of distance-to-prior-day-levels
  - Likely fewer survivors (those features are noisier than PDH/PDL)
  - But genuinely NEW strategies that don't overlap with v3 or the
    existing 5-min whitelist
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeClassifier, _tree

from research.indicators import atr, ema, rsi, session_vwap, volume_ratio
from research.local_data_loader import load_daily, load_intraday_1min
from research.pattern_miner_v3 import cpcv_fold_indices, label_1_to_2_rr
from research.signal_generator import _attach_prev_day_levels

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_PATH = PROJECT_ROOT / "data" / "mined_v4_patterns.json"
EMITTED_PATH = PROJECT_ROOT / "research" / "mined_v4_signals.py"

NY = "America/New_York"


# ---------------------------------------------------------------------------
# v4 feature set — NO PDH/PDL distance features, lots of NEW signal types
# ---------------------------------------------------------------------------

V4_FEATURES = [
    # --- bar shape & wick patterns (8)
    "body_pct", "upper_wick_pct", "lower_wick_pct", "is_inside",
    "is_hammer", "is_shooting_star", "is_doji", "wick_imbalance",
    # --- micro context (6)
    "ret_1", "ret_3", "ret_5", "ret_10", "ret_20",
    "vol_change_3",
    # --- volatility (3) — NO ATR_5 (too noisy alone)
    "atr_14", "atr_50", "atr_5_to_50_ratio",
    # --- momentum / oscillators (4)
    "rsi_2", "rsi_5", "rsi_14", "rsi_2_to_14_diff",
    # --- volume profile (4) — NEW
    "vol_ratio_10", "vol_ratio_30", "vol_ratio_60",
    "dist_vpoc_50_atr",
    # --- multi-bar sequence patterns (6) — NEW
    "n_green_in_5", "n_green_in_10",
    "consec_higher_highs", "consec_lower_lows",
    "consec_higher_lows", "consec_lower_highs",
    # --- inter-scale momentum (4) — NEW
    "ret_3_x_ret_10_sign", "ret_5_x_ret_20_sign",
    "ema_distance_5_20", "ema_distance_20_50",
    # --- range/volatility shifts (4) — NEW
    "range_expansion_3_20", "range_compression_5",
    "vol_burst_3", "vol_drought_10",
    # --- VWAP (3)
    "dist_vwap_atr", "vwap_slope_30", "above_vwap_count_10",
    # --- time cohort + interactions (5) — NEW
    "ny_hour", "ny_minute", "dow",
    "is_rth", "bars_into_session",
    # --- reversal triggers (4) — NEW
    "trap_hi_to_lo_3", "trap_lo_to_hi_3",
    "rejection_from_high_5", "rejection_from_low_5",
]


_V4_FEATURE_CACHE: dict = {}


def build_v4_features(intraday: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """Compute the v4 feature set."""
    cache_key = (id(intraday), id(daily), len(intraday))
    cached = _V4_FEATURE_CACHE.get(cache_key)
    if cached is not None:
        return cached
    df = intraday.copy()
    o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]
    rng = (h - l).replace(0.0, np.nan)
    body = (c - o)
    upper_wick = h - np.maximum(o, c)
    lower_wick = np.minimum(o, c) - l

    feats = pd.DataFrame(index=df.index)

    # --- Bar shape & wicks ---
    feats["body_pct"] = body / rng
    feats["upper_wick_pct"] = upper_wick / rng
    feats["lower_wick_pct"] = lower_wick / rng
    feats["is_inside"] = ((h < h.shift(1)) & (l > l.shift(1))).astype(float)
    # Hammer: lower wick > 2× body, body in upper half
    feats["is_hammer"] = (
        (lower_wick > 2 * body.abs()) &
        ((c - l) / rng > 0.65) &
        (body > 0)
    ).astype(float)
    # Shooting star: upper wick > 2× body, body in lower half, close < open
    feats["is_shooting_star"] = (
        (upper_wick > 2 * body.abs()) &
        ((h - c) / rng > 0.65) &
        (body < 0)
    ).astype(float)
    feats["is_doji"] = ((body.abs() / rng) < 0.1).astype(float)
    feats["wick_imbalance"] = (upper_wick - lower_wick) / rng

    # --- Micro context ---
    feats["ret_1"] = c - c.shift(1)
    feats["ret_3"] = c - c.shift(3)
    feats["ret_5"] = c - c.shift(5)
    feats["ret_10"] = c - c.shift(10)
    feats["ret_20"] = c - c.shift(20)
    feats["vol_change_3"] = v / v.shift(3).replace(0.0, np.nan)

    # --- Volatility ---
    a5 = atr(h, l, c, 5)
    a14 = atr(h, l, c, 14)
    a50 = atr(h, l, c, 50)
    feats["atr_14"] = a14
    feats["atr_50"] = a50
    feats["atr_5_to_50_ratio"] = a5 / a50.replace(0, np.nan)

    # --- RSI ---
    r2 = rsi(c, 2)
    r5 = rsi(c, 5)
    r14 = rsi(c, 14)
    feats["rsi_2"] = r2
    feats["rsi_5"] = r5
    feats["rsi_14"] = r14
    feats["rsi_2_to_14_diff"] = r2 - r14

    # --- Volume profile ---
    feats["vol_ratio_10"] = volume_ratio(v, 10)
    feats["vol_ratio_30"] = volume_ratio(v, 30)
    feats["vol_ratio_60"] = volume_ratio(v, 60)
    # VPOC proxy: price level with maximum cumulative volume in last 50 bars
    # (approximated as volume-weighted close)
    vwc_50 = (c * v).rolling(50).sum() / v.rolling(50).sum().replace(0, np.nan)
    feats["dist_vpoc_50_atr"] = (c - vwc_50) / a14

    # --- Multi-bar sequence patterns ---
    green = (body > 0).astype(int)
    feats["n_green_in_5"] = green.rolling(5).sum()
    feats["n_green_in_10"] = green.rolling(10).sum()
    # Consecutive higher highs/lows
    hh = (h > h.shift(1)).astype(int)
    ll = (l < l.shift(1)).astype(int)
    hl = (l > l.shift(1)).astype(int)
    lh = (h < h.shift(1)).astype(int)
    feats["consec_higher_highs"] = hh.groupby(
        (hh != hh.shift()).cumsum()
    ).cumcount() + 1
    feats["consec_lower_lows"] = ll.groupby(
        (ll != ll.shift()).cumsum()
    ).cumcount() + 1
    feats["consec_higher_lows"] = hl.groupby(
        (hl != hl.shift()).cumsum()
    ).cumcount() + 1
    feats["consec_lower_highs"] = lh.groupby(
        (lh != lh.shift()).cumsum()
    ).cumcount() + 1

    # --- Inter-scale momentum ---
    feats["ret_3_x_ret_10_sign"] = np.sign(feats["ret_3"]) * np.sign(feats["ret_10"])
    feats["ret_5_x_ret_20_sign"] = np.sign(feats["ret_5"]) * np.sign(feats["ret_20"])
    e5 = ema(c, 5)
    e20 = ema(c, 20)
    e50 = ema(c, 50)
    feats["ema_distance_5_20"] = (e5 - e20) / a14
    feats["ema_distance_20_50"] = (e20 - e50) / a14

    # --- Range / vol shifts ---
    feats["range_expansion_3_20"] = rng.rolling(3).mean() / rng.rolling(20).mean().replace(0, np.nan)
    feats["range_compression_5"] = rng.rolling(5).max() / rng.rolling(20).mean().replace(0, np.nan)
    feats["vol_burst_3"] = (v.rolling(3).max() / v.rolling(20).mean().replace(0, np.nan))
    feats["vol_drought_10"] = (v.rolling(10).mean() / v.rolling(60).mean().replace(0, np.nan))

    # --- VWAP ---
    vwap = session_vwap(intraday)
    feats["dist_vwap_atr"] = (c - vwap) / a14
    feats["vwap_slope_30"] = (vwap - vwap.shift(30)) / a14
    feats["above_vwap_count_10"] = (c > vwap).rolling(10).sum()

    # --- Time cohort ---
    if intraday.index.tz is None:
        intraday = intraday.tz_localize("UTC")
    ny = intraday.index.tz_convert(NY)
    ny_min_arr = ny.hour * 60 + ny.minute
    feats["ny_hour"] = ny.hour
    feats["ny_minute"] = ny.minute
    feats["dow"] = ny.dayofweek
    feats["is_rth"] = ((ny_min_arr >= 570) & (ny_min_arr < 960)).astype(float)
    # Bars elapsed since start of NY day (RTH only — else 0)
    sessions = pd.Series(ny.date, index=intraday.index)
    bars_into_session_vals = []
    last_date = None
    counter = 0
    for date_, in_rth in zip(sessions.values,
                              ((ny_min_arr >= 570) & (ny_min_arr < 960))):
        if date_ != last_date:
            counter = 0
            last_date = date_
        if in_rth:
            counter += 1
            bars_into_session_vals.append(counter)
        else:
            bars_into_session_vals.append(0)
    feats["bars_into_session"] = bars_into_session_vals

    # --- Reversal triggers ---
    # Trap: price rallied X pts in last 3 bars then closed lower (failed move)
    rise_3 = c.shift(0) - c.shift(3)
    drop_now = c - c.shift(1)
    feats["trap_hi_to_lo_3"] = ((rise_3 > 5) & (drop_now < -2)).astype(float)
    feats["trap_lo_to_hi_3"] = ((rise_3 < -5) & (drop_now > 2)).astype(float)
    # Rejection from N-bar high (price hit high but closed > X% off it)
    h5 = h.rolling(5).max()
    l5 = l.rolling(5).min()
    feats["rejection_from_high_5"] = ((h >= h5) & ((h - c) / rng > 0.5)).astype(float)
    feats["rejection_from_low_5"] = ((l <= l5) & ((c - l) / rng > 0.5)).astype(float)

    out = feats[V4_FEATURES]
    _V4_FEATURE_CACHE[cache_key] = out
    if len(_V4_FEATURE_CACHE) > 4:
        for k in list(_V4_FEATURE_CACHE.keys())[:-4]:
            _V4_FEATURE_CACHE.pop(k, None)
    return out


# ---------------------------------------------------------------------------
# Mining + CPCV — same protocol as v3 but with v4 features
# ---------------------------------------------------------------------------

@dataclass
class V4Rule:
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


def _path_constraints(tree, leaf_id: int) -> list[tuple[str, str, float]]:
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
        chain.append((V4_FEATURES[int(t.feature[parent])],
                      op, float(t.threshold[parent])))
        cur = parent
    return list(reversed(chain))


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--combos", default="10/30,12/35,15/40,8/25",
                   help="stop_pts/max_hold combos (target = 2× stop)")
    p.add_argument("--max-depth", type=int, default=12)
    p.add_argument("--min-leaf", type=int, default=300)
    p.add_argument("--min-train-wr", type=float, default=0.58)
    p.add_argument("--min-cpcv-mean-wr", type=float, default=0.55)
    p.add_argument("--min-cpcv-fold-wr", type=float, default=0.50)
    p.add_argument("--min-trades-per-week", type=float, default=3.0)
    p.add_argument("--n-folds", type=int, default=5)
    p.add_argument("--purge", type=int, default=30)
    p.add_argument("--top", type=int, default=8)
    p.add_argument("--emit", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    print("=" * 78)
    print("PATTERN MINER v4 — completely new patterns (no PDH/PDL anchor)")
    print(f"  combos: {args.combos}    folds: {args.n_folds}    purge: {args.purge} bars")
    print(f"  thresholds: train_wr ≥ {args.min_train_wr*100:.0f}%, "
          f"cpcv_mean ≥ {args.min_cpcv_mean_wr*100:.0f}%, "
          f"cpcv_min_fold ≥ {args.min_cpcv_fold_wr*100:.0f}%")
    print("=" * 78)

    print("\n[1/4] Loading 1-min + daily ...", flush=True)
    t0 = time.time()
    intraday = load_intraday_1min()
    daily = load_daily()
    days = max(1, (intraday.index[-1] - intraday.index[0]).days)
    print(f"  1-min bars: {len(intraday):,}  ({days} days)")

    print("[2/4] Building v4 features (~50, NO PDH/PDL distance) ...", flush=True)
    t1 = time.time()
    X_full = build_v4_features(intraday, daily)
    feat_valid = X_full.notna().all(axis=1)
    print(f"  feature-valid bars: {feat_valid.sum():,}  ({time.time()-t1:.1f}s)")

    combos = []
    for s in args.combos.split(","):
        a, b = s.strip().split("/")
        combos.append((float(a), int(b)))

    weeks = days / 7.0
    all_rules: list[V4Rule] = []
    print(f"\n[3/4] Mining + CPCV ...")
    for stop_pts, max_hold in combos:
        target_pts = 2.0 * stop_pts
        be_wr = (stop_pts + 3.0) / ((stop_pts + 3.0) + (target_pts - 1.0)) * 100
        print(f"\n  --- stop={stop_pts}pt  target={target_pts}pt  max_hold={max_hold}m  "
              f"(BE-WR={be_wr:.1f}%) ---")

        for side in ("LONG", "SHORT"):
            t1 = time.time()
            outcome, valid = label_1_to_2_rr(intraday, stop_pts, max_hold, side)
            mask_idx = (valid & feat_valid.to_numpy()).nonzero()[0]
            X = X_full.values[mask_idx]
            y = outcome[mask_idx]
            n = len(y)
            if n < 5000:
                continue

            cut = int(n * 0.70)
            X_tr, X_te = X[:cut], X[cut:]
            y_tr, y_te = y[:cut], y[cut:]
            tree = DecisionTreeClassifier(
                max_depth=args.max_depth,
                min_samples_leaf=args.min_leaf,
                random_state=42,
                class_weight="balanced",
            )
            tree.fit(X_tr, y_tr)

            leaf_tr = tree.apply(X_tr)
            leaf_te = tree.apply(X_te)
            candidates = []
            for leaf in np.unique(leaf_tr):
                m_tr = leaf_tr == leaf
                m_te = leaf_te == leaf
                if m_tr.sum() < args.min_leaf or m_te.sum() < 50:
                    continue
                tr_wr = float(y_tr[m_tr].mean())
                te_wr = float(y_te[m_te].mean())
                if tr_wr < args.min_train_wr or te_wr < args.min_cpcv_fold_wr:
                    continue
                candidates.append((leaf, tr_wr, te_wr, m_tr.sum() + m_te.sum()))

            print(f"    {side}: usable={n:,}  candidates={len(candidates)}  ({time.time()-t1:.1f}s)")
            if not candidates:
                continue

            cpcv_pairs = cpcv_fold_indices(n, args.n_folds, args.purge)
            full_leaf_assignments = tree.apply(X)
            survivors = []
            for leaf, tr_wr, te_wr, n_total in candidates:
                fold_wrs = []
                for _, te_idx in cpcv_pairs:
                    in_leaf = full_leaf_assignments[te_idx] == leaf
                    if in_leaf.sum() < 20:
                        continue
                    fold_wrs.append(float(y[te_idx][in_leaf].mean()))
                if not fold_wrs or len(fold_wrs) < args.n_folds // 2:
                    continue
                mean_wr = float(np.mean(fold_wrs))
                min_wr = float(np.min(fold_wrs))
                max_wr = float(np.max(fold_wrs))
                if mean_wr < args.min_cpcv_mean_wr or min_wr < args.min_cpcv_fold_wr:
                    continue
                trades_per_week = n_total / weeks
                if trades_per_week < args.min_trades_per_week:
                    continue
                survivors.append(V4Rule(
                    name="",
                    side=side, stop_pts=stop_pts, target_pts=target_pts,
                    max_hold=max_hold, n_total=n_total,
                    train_wr=tr_wr,
                    cpcv_mean_wr=mean_wr, cpcv_min_wr=min_wr, cpcv_max_wr=max_wr,
                    cpcv_n_folds=len(fold_wrs),
                    constraints=_path_constraints(tree, leaf),
                ))
            survivors.sort(key=lambda r: -r.cpcv_mean_wr * (r.n_total ** 0.3))
            survivors = survivors[:args.top]
            for r in survivors:
                preview = ", ".join(f"{c[0]}{c[1]}{c[2]:.2f}" for c in r.constraints[:3])
                if len(r.constraints) > 3:
                    preview += f"...+{len(r.constraints)-3}"
                print(f"      ✓ n={r.n_total:>4d}  cpcv WR mean={r.cpcv_mean_wr*100:.1f}% "
                      f"(min={r.cpcv_min_wr*100:.1f}%)  trades/wk={r.n_total/weeks:.1f}  | {preview}")
            all_rules.extend(survivors)

    print(f"\n[4/4] {len(all_rules)} CPCV survivors total")
    n_long = sum(1 for r in all_rules if r.side == "LONG")
    n_short = sum(1 for r in all_rules if r.side == "SHORT")
    print(f"  LONG: {n_long}    SHORT: {n_short}")

    by_side = {"LONG": 0, "SHORT": 0}
    for r in all_rules:
        by_side[r.side] += 1
        r.name = f"V4_{r.side}_S{int(r.stop_pts)}T{int(r.target_pts)}_{by_side[r.side]:02d}"

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "params": vars(args),
        "data_context": {"1min_bars": len(intraday), "days": days, "weeks": weeks},
        "patterns": [asdict(r) for r in all_rules],
    }
    RESULTS_PATH.write_text(json.dumps(payload, indent=2, default=str))
    print(f"  Wrote -> {RESULTS_PATH.relative_to(PROJECT_ROOT)}")

    if args.emit and all_rules:
        lines = [
            '"""',
            "Auto-generated v4 pattern Signal classes — NEW patterns",
            "(no PDH/PDL anchor; novel feature set).",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            f"Survivors: {len(all_rules)}  (LONG={n_long}, SHORT={n_short})",
            '"""',
            "from __future__ import annotations",
            "import pandas as pd",
            "",
            "",
        ]
        cls_names = []
        for i, r in enumerate(all_rules):
            cname = f"V4{r.side.capitalize()}S{int(r.stop_pts)}T{int(r.target_pts)}_{i+1:02d}"
            cls_names.append(cname)
            lines.append(f"class {cname}:")
            lines.append(f'    name = {r.name!r}')
            lines.append(f"    side = {r.side!r}")
            lines.append(f"    target_pts = {r.target_pts!r}")
            lines.append(f"    stop_pts = {r.stop_pts!r}")
            lines.append(f"    max_hold_bars = {r.max_hold!r}")
            lines.append(f"    cpcv_mean_wr = {r.cpcv_mean_wr!r}")
            lines.append("    constraints = [")
            for feat, op, thr in r.constraints:
                lines.append(f"        ({feat!r}, {op!r}, {thr!r}),")
            lines.append("    ]")
            lines.append("")
            lines.append("    def generate(self, intraday, daily):")
            lines.append("        from research.pattern_miner_v4 import build_v4_features")
            lines.append("        feats = build_v4_features(intraday, daily)")
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
        lines.append("ALL_V4_SIGNALS = [")
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
