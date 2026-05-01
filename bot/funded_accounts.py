"""
Funded-accounts ledger.

Tracks every Lucid account the bot has run through — passes (manually marked
when payout requested), failures (auto-recorded by LucidAccount on blow-up),
and the active account.

Persisted to data/funded_accounts.json:

  {
    "n_passed": 0, "n_failed": 0, "active_account_id": 3,
    "history": [
      {"account_id": 1, "started_at": ..., "ended_at": ..., "outcome": "FAILED",
       "blow_reason": "trail_breach@$47900<=$48000",
       "ending_balance": 47900.0, "n_trading_days": 5, "cum_pnl": -2100.0,
       "n_trades": 18, "wins": 6, "losses": 12},
      {"account_id": 2, "started_at": ..., "ended_at": ..., "outcome": "PASSED",
       "ending_balance": 52450.0, ...}
    ]
  }
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger("funded_ledger")

LEDGER_PATH = Path(__file__).resolve().parent.parent / "data" / "funded_accounts.json"


class FundedLedger:
    def __init__(self, path: Path = LEDGER_PATH) -> None:
        self.path = path
        self._data = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"n_passed": 0, "n_failed": 0, "active_account_id": 1, "history": []}
        try:
            return json.loads(self.path.read_text())
        except Exception as e:
            logger.error(f"ledger read failed: {e}")
            return {"n_passed": 0, "n_failed": 0, "active_account_id": 1, "history": []}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2, default=str))

    def record(self, outcome: dict) -> None:
        """Append a closed account to the history. Increments pass/fail counter
        based on outcome["outcome"] == "PASSED" / "FAILED"."""
        self._data["history"].append(outcome)
        if outcome.get("outcome") == "PASSED":
            self._data["n_passed"] += 1
        else:
            self._data["n_failed"] += 1
        self._data["active_account_id"] = outcome.get("account_id", 0) + 1
        self._save()

    def snapshot(self) -> dict:
        # Return a copy so callers can mutate without corrupting in-memory state
        return {
            "n_passed": self._data["n_passed"],
            "n_failed": self._data["n_failed"],
            "active_account_id": self._data["active_account_id"],
            "total_runs": self._data["n_passed"] + self._data["n_failed"],
            "history": self._data["history"][-50:],   # last 50 accounts
        }
