"""CLI to run a calibration cycle.

Usage:
  # From real Tradovate executionReports persisted to JSONL:
  python -m engine.calibration.run_calibration --fills data/tradovate_fills.jsonl

  # From the live trade DB (synthesises minimum required fields):
  python -m engine.calibration.run_calibration --from-db

After running, the new params are written to engine/calibration/params.json
and SimFillModel will pick them up automatically on next construction.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Iterable

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("run_calibration")

OUT_PATH = Path(__file__).resolve().parent / "params.json"


def _load_jsonl(p: Path) -> Iterable[dict]:
    with open(p) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                log.warning(f"skipping bad line: {e}")


def _load_from_db() -> Iterable[dict]:
    """Synthesise calibration rows from the live trade DB. CAVEAT: the
    trade DB doesn't store the original intended price separately from
    the executed fill price -- so stop slippage shows as zero. Use this
    only as a smoke test; real calibration requires raw Tradovate
    executionReports."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from bot import persistence
    from bot.account_ctx import set_account
    set_account("1")
    rows = persistence.load_trades(limit=100_000, only_closed=True)
    for r in rows:
        # Best-effort field mapping; many will be missing
        yield {
            "intended_price": r.get("stop_px") if r.get("exit_reason") == "stop"
                              else r.get("target_px") if r.get("exit_reason") == "target"
                              else r.get("exit_px"),
            "fill_price":     r.get("exit_px"),
            "side":           r.get("side"),
            "order_type":     "Stop" if r.get("exit_reason") == "stop"
                              else "Limit" if r.get("exit_reason") == "target"
                              else "Market",
            "submitted_ts":   r.get("entry_time"),  # placeholder
            "fill_ts":        r.get("exit_time"),
            "bar_high":       None,
            "bar_low":        None,
            "atr_5":          0,    # unknown
            "atr_60":         0,
            "is_news_window": False,
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fills", type=Path, help="JSONL of executionReports")
    parser.add_argument("--from-db", action="store_true",
                        help="Synthesise from the live trade DB (rough)")
    args = parser.parse_args()
    if not args.fills and not args.from_db:
        parser.error("either --fills <path> or --from-db is required")
    fills = list(_load_jsonl(args.fills) if args.fills else _load_from_db())
    log.info(f"loaded {len(fills)} fills")
    if not fills:
        log.error("no fills to calibrate against")
        return 1

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from engine.calibration.fill_calibrator import calibrate, save_calibration
    result = calibrate(fills)
    save_calibration(result, OUT_PATH)
    log.info(f"params saved to {OUT_PATH}")
    log.info(f"summary: {json.dumps(result['summary'], indent=2)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
