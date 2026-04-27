"""
Win-rate-first pattern mining (the "60%+ WR scalp" search).

Different from pattern_miner.py:

  - There, the label was 10-bar mean forward return.  A leaf could
    have +20pt mean return *with* a 10pt stop never being hit, but
    in live the 10pt stop hits first and we lose.

  - Here, the label is the actual TRIPLE-BARRIER outcome at a fixed
    (target, stop, max_hold) trade structure:
        WIN  = target hit before stop within max_hold_bars
        LOSS = stop hit before target, OR timeout
    So the tree learns "what context predicts target-hitting-first
    under THIS specific stop/target".

  - We sweep multiple (target, stop, hold) combos, and for each we
    keep tree leaves where:
        * out-of-sample win rate >= 60%
        * out-of-sample sample size >= 100 trades
        * in-sample win rate also >= 55% (not over-fit)
        * gross EV after $30 friction is positive

  - Each surviving leaf becomes a Signal class.

Cost model: 5 MNQ * $2/pt = $10/pt. $10 commission round-trip = 1pt.
            Plus 2pt slippage (entry + stop). Total friction ≈ 3pt.
            Win = (target - 1)pt. Loss = (stop + 3)pt.
            Break-even WR for 12/10: (10+3)/((10+3)+(12-1)) = 54%
            so a leaf at 60% WR has +6% margin to noise.

Usage:
    python -m research.pattern_miner_wr               # sweep default combos
    python -m research.pattern_miner_wr --emit        # also write
                                                       # research/mined_wr_signals.py
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

from research.local_data_loader import load_daily, load_intraday_1min
from research.pattern_miner import build_features, FEATURE_COLS

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_PATH = PROJECT_ROOT / "data" / "mined_wr_patterns.json"
EMITTED_PATH = PROJECT_ROOT / "research" / "mined_wr_signals.py"


# ---------------------------------------------------------------------------
# Triple-barrier labeling
# ---------------------------------------------------------------------------

def label_triple_barrier(intraday: pd.DataFrame, target_pts: float,
                         stop_pts: float, max_hold: int, side: str
                         ) -> tuple[np.ndarray, np.ndarray]:
    """For each bar, does target hit BEFORE stop within max_hold bars?

    Returns:
        outcome: 0/1 array — 1 = target hit first (WIN), 0 = stop or timeout
        valid:   boolean array — True if we have enough forward bars to evaluate
    """
    h = intraday["high"].to_numpy(dtype=np.float64)
    l = intraday["low"].to_numpy(dtype=np.float64)
    c = intraday["close"].to_numpy(dtype=np.float64)
    n = len(c)
    outcome = np.zeros(n, dtype=np.int8)
    valid = np.zeros(n, dtype=bool)

    for i in range(n - max_hold):
        entry = c[i]
        if side == "LONG":
            target = entry + target_pts
            stop = entry - stop_pts
            won = False
            for j in range(i + 1, i + 1 + max_hold):
                if l[j] <= stop and h[j] >= target:
                    # Both same bar: conservative, count as loss
                    won = False
                    break
                if l[j] <= stop:
                    won = False
                    break
                if h[j] >= target:
                    won = True
                    break
            outcome[i] = 1 if won else 0
        else:  # SHORT
            target = entry - target_pts
            stop = entry + stop_pts
            won = False
            for j in range(i + 1, i + 1 + max_hold):
                if h[j] >= stop and l[j] <= target:
                    won = False
                    break
                if h[j] >= stop:
                    won = False
                    break
                if l[j] <= target:
                    won = True
                    break
            outcome[i] = 1 if won else 0
        valid[i] = True
    return outcome, valid


# ---------------------------------------------------------------------------
# Tree → leaf rules
# ---------------------------------------------------------------------------

@dataclass
class WRLeafRule:
    leaf_id: int
    side: str
    target_pts: float
    stop_pts: float
    max_hold: int
    n_in_sample: int
    n_out_sample: int
    is_wr: float
    oos_wr: float
    oos_ev_dollars: float          # using 5 MNQ + 3pt friction
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
        chain.append((FEATURE_COLS[int(t.feature[parent])],
                      op, float(t.threshold[parent])))
        cur = parent
    return list(reversed(chain))


def find_wr_leaves(tree, X_train, y_train, X_test, y_test, side, target_pts,
                   stop_pts, max_hold,
                   *, min_oos_wr: float, min_oos_n: int, min_is_wr: float
                   ) -> list[WRLeafRule]:
    leaf_train = tree.apply(X_train)
    leaf_test = tree.apply(X_test)
    rules = []
    # Per-trade economics at 5 MNQ:
    win_pts = target_pts - 1.0  # entry slip ≈ 1pt at limit
    loss_pts = -(stop_pts + 3.0)  # entry slip + stop slip + comm
    for leaf in np.unique(leaf_train):
        m_is = leaf_train == leaf
        m_oos = leaf_test == leaf
        n_is = int(m_is.sum())
        n_oos = int(m_oos.sum())
        if n_oos < min_oos_n or n_is < 50:
            continue
        is_wr = float(y_train[m_is].mean())
        oos_wr = float(y_test[m_oos].mean())
        if is_wr < min_is_wr or oos_wr < min_oos_wr:
            continue
        # EV in dollars per trade at 5 contracts ($10/pt)
        ev_pts = oos_wr * win_pts + (1 - oos_wr) * loss_pts
        ev_dollars = ev_pts * 10.0
        if ev_dollars <= 0:
            continue
        rules.append(WRLeafRule(
            leaf_id=int(leaf),
            side=side,
            target_pts=float(target_pts),
            stop_pts=float(stop_pts),
            max_hold=int(max_hold),
            n_in_sample=n_is,
            n_out_sample=n_oos,
            is_wr=is_wr,
            oos_wr=oos_wr,
            oos_ev_dollars=ev_dollars,
            constraints=_path_constraints(tree, leaf),
        ))
    return rules


# ---------------------------------------------------------------------------
# Code emission
# ---------------------------------------------------------------------------

def emit_wr_signal_class(rule: WRLeafRule, idx: int) -> tuple[str, str]:
    name = f"WR_{rule.side}_T{int(rule.target_pts)}S{int(rule.stop_pts)}_{idx:02d}"
    cls = f"WR{rule.side.capitalize()}T{int(rule.target_pts)}S{int(rule.stop_pts)}_{idx:02d}"
    lines = [f"class {cls}:"]
    lines.append(f'    name = "{name}"')
    lines.append(f"    side = {rule.side!r}")
    lines.append(f"    target_pts = {rule.target_pts!r}")
    lines.append(f"    stop_pts = {rule.stop_pts!r}")
    lines.append(f"    max_hold_bars = {rule.max_hold!r}")
    lines.append(f"    expected_oos_wr = {rule.oos_wr!r}")
    lines.append(f"    expected_oos_n = {rule.n_out_sample!r}")
    lines.append(f"    expected_oos_ev_dollars = {rule.oos_ev_dollars!r}")
    lines.append(f"    constraints = [")
    for feat, op, thr in rule.constraints:
        lines.append(f"        ({feat!r}, {op!r}, {thr!r}),")
    lines.append("    ]")
    lines.append("")
    lines.append("    def generate(self, intraday, daily):")
    lines.append("        from research.pattern_miner import build_features")
    lines.append("        feats = build_features(intraday, daily)")
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
    lines.append(f"        # natural target = entry +/- target_pts")
    lines.append(f"        sign = 1 if {rule.side!r} == 'LONG' else -1")
    lines.append("        return pd.DataFrame({")
    lines.append("            'signal_time': idx, 'signal_name': self.name,")
    lines.append(f"            'side': {rule.side!r},")
    lines.append("            'entry_px': c.values,")
    lines.append("            'target_hint': c.values + sign * self.target_pts,")
    lines.append("        })")
    return cls, "\n".join(lines)


# ---------------------------------------------------------------------------
# Driver — sweep target/stop/hold combos
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--combos", default="12/10/15,15/10/20,15/12/20,20/10/30,10/8/10",
                   help="target/stop/maxhold combos, comma-separated")
    p.add_argument("--max-depth", type=int, default=6)
    p.add_argument("--min-leaf", type=int, default=500)
    p.add_argument("--min-oos-wr", type=float, default=0.60)
    p.add_argument("--min-is-wr", type=float, default=0.55)
    p.add_argument("--min-oos-n", type=int, default=100)
    p.add_argument("--top", type=int, default=10,
                   help="Keep at most N leaves per combo")
    p.add_argument("--emit", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    print("=" * 78)
    print("WIN-RATE-FOCUSED PATTERN MINING (60%+ WR scalp search)")
    print(f"  combos (target/stop/maxhold): {args.combos}")
    print(f"  min OOS WR: {args.min_oos_wr*100:.0f}%   min IS WR: {args.min_is_wr*100:.0f}%   "
          f"min OOS n: {args.min_oos_n}")
    print("=" * 78)

    print("\n[1/4] Loading 1-min + daily ...", flush=True)
    t0 = time.time()
    intraday = load_intraday_1min()
    daily = load_daily()
    days = max(1, (intraday.index[-1] - intraday.index[0]).days)
    print(f"  1-min bars: {len(intraday):,}  ({days} days)")

    print("[2/4] Building 25 features (cached) ...", flush=True)
    t1 = time.time()
    X_full = build_features(intraday, daily)
    feat_valid = X_full.notna().all(axis=1)
    print(f"  feature-valid bars: {feat_valid.sum():,}  ({time.time()-t1:.1f}s)")

    combos = []
    for s in args.combos.split(","):
        parts = s.strip().split("/")
        combos.append((float(parts[0]), float(parts[1]), int(parts[2])))

    all_rules: list[WRLeafRule] = []
    print(f"\n[3/4] Mining each (target, stop, max_hold) combo ...")
    for target_pts, stop_pts, max_hold in combos:
        # BE-WR for context
        win = target_pts - 1.0
        loss = stop_pts + 3.0
        be_wr = loss / (loss + win) * 100
        print(f"\n  --- target={target_pts}pt  stop={stop_pts}pt  max_hold={max_hold}m  "
              f"(BE-WR={be_wr:.1f}%) ---")

        for side in ("LONG", "SHORT"):
            t1 = time.time()
            outcome, valid = label_triple_barrier(
                intraday, target_pts, stop_pts, max_hold, side,
            )
            mask = pd.Series(valid & feat_valid.to_numpy(), index=intraday.index)
            X = X_full[mask].to_numpy()
            y = outcome[mask.to_numpy()]
            n = len(y)
            cut = int(n * 0.70)
            X_tr, X_te = X[:cut], X[cut:]
            y_tr, y_te = y[:cut], y[cut:]
            base_wr = y_tr.mean()
            tree = DecisionTreeClassifier(
                max_depth=args.max_depth,
                min_samples_leaf=args.min_leaf,
                random_state=42,
                class_weight="balanced",
            )
            tree.fit(X_tr, y_tr)
            rules = find_wr_leaves(
                tree, X_tr, y_tr, X_te, y_te, side, target_pts, stop_pts, max_hold,
                min_oos_wr=args.min_oos_wr, min_oos_n=args.min_oos_n,
                min_is_wr=args.min_is_wr,
            )
            rules.sort(key=lambda r: -r.oos_ev_dollars * (r.n_out_sample ** 0.5))
            rules = rules[:args.top]
            print(f"    {side}: base WR={base_wr*100:.1f}%   "
                  f"leaves found={len(rules)}   ({time.time()-t1:.1f}s)")
            for r in rules[:5]:
                preview = ", ".join(f"{c[0]}{c[1]}{c[2]:.2f}" for c in r.constraints[:3])
                if len(r.constraints) > 3:
                    preview += f"...+{len(r.constraints)-3}"
                print(f"      n_oos={r.n_out_sample:>4d}  WR={r.oos_wr*100:>5.1f}%  "
                      f"EV=${r.oos_ev_dollars:>6.1f}  {preview}")
            all_rules.extend(rules)

    print(f"\n[4/4] {len(all_rules)} total leaves survived across all combos")
    if not all_rules:
        print("\n  No 60%+ WR patterns found at any combo. Try lowering --min-oos-wr.")
        return 0

    # Persist
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters": {
            "min_oos_wr": args.min_oos_wr,
            "min_is_wr": args.min_is_wr,
            "min_oos_n": args.min_oos_n,
            "max_depth": args.max_depth,
            "min_leaf": args.min_leaf,
        },
        "data_context": {"1min_bars": len(intraday), "days": days},
        "patterns": [
            {
                "name": f"WR_{r.side}_T{int(r.target_pts)}S{int(r.stop_pts)}_{i+1:02d}",
                **asdict(r),
            }
            for i, r in enumerate(all_rules)
        ],
    }
    RESULTS_PATH.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\n  Wrote -> {RESULTS_PATH.relative_to(PROJECT_ROOT)}")

    if args.emit:
        lines = [
            '"""',
            "Auto-generated 60%+ WR pattern Signal classes.",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            f"Patterns: {len(all_rules)}",
            '"""',
            "from __future__ import annotations",
            "import pandas as pd",
            "",
            "",
        ]
        cls_names = []
        for i, r in enumerate(all_rules):
            cname, source = emit_wr_signal_class(r, i + 1)
            cls_names.append(cname)
            lines.append(source)
            lines.append("")
        lines.append("ALL_WR_SIGNALS = [")
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
