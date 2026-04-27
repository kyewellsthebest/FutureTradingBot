"""
Discovery — wraps each pattern in `pattern_discovery4` as a Signal subclass
so it can run through the same validation pipeline as the production signals,
and (optionally) merges survivors into ALL_SIGNALS for live use.

Usage:
    python -m research.discover_signals               # FAST: 100 perms
    python -m research.discover_signals --full        # 1000 perms
    python -m research.discover_signals --merge       # also write survivors
                                                       # to data/discovery_results.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from research import pattern_discovery4 as pd4
from research.backtest_engine import (
    monte_carlo,
    simulate_trades,
    to_json_dict,
    validate_signal,
)
from research.local_data_loader import load_daily, load_intraday_5min

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DISCOVERY_PATH = PROJECT_ROOT / "data" / "discovery_results.json"


# ---------------------------------------------------------------------------
# Wrap each pattern_discovery4 detector as a Signal-compatible object
# ---------------------------------------------------------------------------

class _DiscoverySignal:
    """Adapts a pattern_discovery4._pX_*(df) function into the Signal protocol."""

    def __init__(self, name: str, side: str, detector):
        self.name = name
        self.side = side
        self.detector = detector

    def generate(self, intraday: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
        df = pd4._build(intraday, daily)
        try:
            mask = self.detector(df)
        except Exception:
            return pd.DataFrame(columns=["signal_time", "signal_name", "side",
                                          "entry_px", "target_hint"])
        if mask is None or not mask.any():
            return pd.DataFrame(columns=["signal_time", "signal_name", "side",
                                          "entry_px", "target_hint"])
        idx = df.index[mask.fillna(False)]
        return pd.DataFrame({
            "signal_time": idx,
            "signal_name": self.name,
            "side": self.side,
            "entry_px": df.loc[idx, "close"].values,
            "target_hint": np.nan,
        })


CANDIDATES: list[_DiscoverySignal] = [
    _DiscoverySignal("GAPFILL_LONG_DISC", "LONG", pd4._p1_gap_fill_long),
    _DiscoverySignal("FAILED_BREAKDOWN_LONG", "LONG", pd4._p2_failed_breakdown_long),
    _DiscoverySignal("3HL_BREAKOUT_LONG", "LONG", pd4._p3_three_higher_lows_breakout_long),
    _DiscoverySignal("LIQ_POCKET_BREAK_LONG", "LONG", pd4._p4_liq_pocket_break_long),
    _DiscoverySignal("INSIDE2_BREAK_LONG", "LONG", pd4._p5_inside2_break_long),
    _DiscoverySignal("MIDDAY_LOW_BOUNCE_LONG", "LONG", pd4._p6_midday_low_bounce_long),
    _DiscoverySignal("OVERNIGHT_DROP_RECOVER_LONG", "LONG", pd4._p7_overnight_drop_recover_long),
    _DiscoverySignal("THIRD_VWAP_TOUCH_LONG", "LONG", pd4._p8_third_vwap_touch_long),
    _DiscoverySignal("BARS_SINCE_LOD_LONG", "LONG", pd4._p9_bars_since_lod_long),
    _DiscoverySignal("ASIAN_LOWQ_LONG", "LONG", pd4._p10_asian_lowq_long),
    _DiscoverySignal("PDH_FLIP_SUPPORT_LONG", "LONG", pd4._p11_pdh_flip_support_long),
    _DiscoverySignal("TRIPLE_DOJI_BREAK_LONG", "LONG", pd4._p12_triple_doji_break_long),
]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--full", action="store_true",
                   help="1000 permutations instead of fast 100.")
    p.add_argument("--merge", action="store_true",
                   help="Also append survivors to data/validation_results.json.")
    p.add_argument("--min-trades", type=int, default=20)
    p.add_argument("--p-value", type=float, default=0.05)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    n_perm = 1000 if args.full else 100

    print("=" * 76)
    print(f"DISCOVERY — testing 12 novel patterns from pattern_discovery4")
    print(f"             permutations={n_perm}   p-threshold<{args.p_value}")
    print("=" * 76)

    intraday = load_intraday_5min()
    daily = load_daily()
    print(f"  data: {len(intraday):,} 5-min bars across {(intraday.index[-1]-intraday.index[0]).days} days\n")

    results: dict[str, dict] = {}
    survivors: list[str] = []
    for i, sig in enumerate(CANDIDATES, 1):
        t1 = time.time()
        print(f"  [{i:>2}/{len(CANDIDATES)}] {sig.name:<32s} ...", end="", flush=True)
        v = validate_signal(sig, intraday, daily,
                            n_permutations=n_perm,
                            min_trades=args.min_trades,
                            permutation_pass_p=args.p_value)
        if v is None:
            print(" no signals")
            continue
        results[v.name] = to_json_dict(v)
        if v.recommended:
            survivors.append(v.name)
        s = v.stats
        verdict = "RECOMMENDED" if v.recommended else f"REJECTED  ({v.reject_reason})"
        print(f" n={s.n:>4d}  wr={s.win_rate*100:5.1f}%  "
              f"pf={s.profit_factor if math.isfinite(s.profit_factor) else 999:5.2f}  "
              f"ev={s.ev_pts:+6.2f}pt  p={v.perm_p_value:.3f}  -> {verdict}  "
              f"({time.time()-t1:.1f}s)")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_permutations": n_perm,
        "data_context": {
            "5min_bars": len(intraday),
            "daily_bars": len(daily),
            "start": str(intraday.index[0]),
            "end": str(intraday.index[-1]),
        },
        "signals": results,
        "survivors": survivors,
    }
    DISCOVERY_PATH.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\n  RECOMMENDED ({len(survivors)}): {', '.join(survivors) or '(none)'}")
    print(f"  Wrote -> {DISCOVERY_PATH.relative_to(PROJECT_ROOT)}")

    if args.merge and survivors:
        # Merge into validation_results.json
        vr_path = PROJECT_ROOT / "data" / "validation_results.json"
        try:
            vr = json.loads(vr_path.read_text())
        except Exception:
            vr = {"signals": {}}
        vr.setdefault("signals", {})
        merged = 0
        for name in survivors:
            vr["signals"][name] = results[name]
            merged += 1
        vr_path.write_text(json.dumps(vr, indent=2, default=str))
        print(f"  Merged {merged} survivors into {vr_path.relative_to(PROJECT_ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
