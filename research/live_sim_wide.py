"""
Run live_sim with whitelist = ALL candidate strategies (not just current Tier A).

The current Tier A had only 2 trades/year. We need to see what every other
strategy in the universe would do under the SAME engine + risk rules. The
ones that produce profitable trades become the new Tier A.

This temporarily expands the engine's whitelist by overwriting it on the
SignalEngine instance, then runs the full 12-month live_sim. Output:
  data/live_sim_wide_results.json   — same shape as live_sim_results.json
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from research.live_sim import LiveSim
from research.local_data_loader import load_intraday_5min

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
OUT_JSON = DATA / "live_sim_wide_results.json"
VAL_PATH = DATA / "validation_results.json"

logger = logging.getLogger("live_sim_wide")


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("signal_engine").setLevel(logging.WARNING)

    # Window: last 12 months of NQ
    bars = load_intraday_5min("nq")
    if bars.index.tz is None: bars.index = bars.index.tz_localize("UTC")
    end = bars.index.max()
    start = end - pd.Timedelta(days=365)
    logger.info(f"window: {start} → {end}")

    sim = LiveSim(start, end)

    # Override whitelist with EVERY strategy from validation_results.json
    val = json.loads(VAL_PATH.read_text())
    all_strats = sorted((val.get("signals") or {}).keys())
    sim.engine.whitelist = set(all_strats)
    logger.info(f"WIDE whitelist: {len(sim.engine.whitelist)} strategies "
                f"(was {len([n for n,s in (val.get('signals') or {}).items() if s.get('recommended')])} live)")

    result = sim.run()
    OUT_JSON.write_text(json.dumps(result, indent=2, default=str))

    # Headline
    print(f"\n{'='*72}\nWIDE-WHITELIST LIVE-SIM HEADLINE\n{'='*72}")
    print(f"  Window:         {result['window'][0][:10]} → {result['window'][1][:10]}")
    print(f"  Whitelist size: {len(all_strats)} strategies")
    print(f"  Bars evaluated: {result['bars_evaluated']:,}")
    print(f"  Signals fired:  {result['signals_fired']:,}")
    print(f"  Trades taken:   {result['trades_taken']:,}")
    print(f"  Trades blocked: {result['trades_blocked']:,}")
    print(f"  Win rate:       {result['win_rate']*100:.1f}%  ({result['n_wins']}W / {result['n_losses']}L)")
    print(f"  Total P&L:      ${result['total_pnl']:+,.0f}")
    print(f"  Final balance:  ${result['ending_balance']:,.0f}")
    print(f"  Failed accts:   {result['n_failed_accounts']}")

    # Per-strategy headline
    by = result.get("by_strategy") or {}
    if by:
        winners = [(n, s) for n, s in by.items() if s["pnl"] > 0]
        losers  = [(n, s) for n, s in by.items() if s["pnl"] <= 0]
        print(f"\n  Strategies that traded: {len(by)}")
        print(f"    profitable: {len(winners)}")
        print(f"    losing:     {len(losers)}")


if __name__ == "__main__":
    main()
