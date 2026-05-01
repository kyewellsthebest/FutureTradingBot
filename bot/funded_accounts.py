"""
Funded-accounts ledger.

Tracks every Lucid account the bot has run through. There is NO automatic
"passed" counter — Lucid's funded program pays out on profit but the
account stays alive until it breaches the trailing drawdown. So:

  - "FAILED" = trail_floor breached (account auto-restarts to a fresh $50K)
  - "ACTIVE" = current account, hasn't breached yet (this is the "pass"
               state — staying alive is the win condition)

If the bot runs forever without ever hitting drawdown, n_failed stays at 0
and the active account just keeps accumulating P&L (you draw payouts
along the way without needing to "graduate" the account).

Persisted to data/funded_accounts.json:

  {
    "n_failed": 2,
    "active_account_id": 3,
    "history": [
      {"account_id": 1, "started_at": ..., "ended_at": ..., "outcome": "FAILED",
       "blow_reason": "trail_breach@$47900<=$48000",
       "ending_balance": 47900.0, "n_trading_days": 5, "cum_pnl": -2100.0,
       "n_trades": 18, "wins": 6, "losses": 12},
      {"account_id": 2, "started_at": ..., "ended_at": ..., "outcome": "FAILED",
       "ending_balance": 47800.0, ...}
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
        default = {"n_failed": 0, "active_account_id": 1, "history": []}
        if not self.path.exists():
            return default
        try:
            d = json.loads(self.path.read_text())
            # Migrate legacy schema (drop n_passed if present)
            d.pop("n_passed", None)
            d.setdefault("n_failed", 0)
            d.setdefault("active_account_id", 1)
            d.setdefault("history", [])
            return d
        except Exception as e:
            logger.error(f"ledger read failed: {e}")
            return default

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2, default=str))

    def record(self, outcome: dict) -> None:
        """Append a closed account to the history. Only FAILED accounts
        come through here — the active account never gets recorded until
        it breaches."""
        self._data["history"].append(outcome)
        if outcome.get("outcome") == "FAILED":
            self._data["n_failed"] += 1
        self._data["active_account_id"] = outcome.get("account_id", 0) + 1
        self._save()

    def snapshot(self) -> dict:
        return {
            "n_failed": self._data["n_failed"],
            "active_account_id": self._data["active_account_id"],
            "total_runs": self._data["n_failed"] + 1,    # failed + currently active
            "history": self._data["history"][-50:],
        }
