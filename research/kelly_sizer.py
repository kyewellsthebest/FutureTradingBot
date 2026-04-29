"""
Adaptive Kelly sizing — replaces fixed 5/30 MNQ contracts with a rolling
Kelly fraction calculated from each strategy's recent performance.

Why:
    Currently every strategy trades the same fixed contract count regardless
    of recent edge. A strategy that's been losing for 30 days still gets full
    size; a strategy on a hot streak gets the same as one that's barely
    breaking even.

Kelly criterion (for binary outcomes):
    f* = (b·p - q) / b
    where b = win/loss ratio, p = WR, q = 1-p

We use HALF-KELLY (the standard practitioner's haircut) and clip to [0.1, 1.0]
so a strategy never gets fully muted (still takes 0.1x size to keep collecting
data) and never gets more than 1x base.

For each strategy we keep a rolling window of its last 60 trades (default).
Recompute the Kelly fraction on each new bar; multiply the strategy's base
contract count by it.

Functions:
    kelly_fraction(wins, losses, win_size, loss_size) -> float in [0.1, 1.0]
    size_for_strategy(strategy_name, recent_pnls, base_contracts) -> int contracts

The bot's signal engine should call size_for_strategy() at every entry.
"""
from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KELLY_STATE_PATH = PROJECT_ROOT / "data" / "kelly_state.json"


def kelly_fraction(wins: int, losses: int,
                    avg_win_dollars: float, avg_loss_dollars: float,
                    *, half_kelly: bool = True,
                    min_frac: float = 0.10, max_frac: float = 1.0) -> float:
    """Compute Kelly fraction from per-trade stats.

    Returns fraction of base size to use. Clipped to [min_frac, max_frac].
    Default half-Kelly: f* / 2 (the standard 50% haircut to limit ruin risk).

    Args:
        wins, losses: trade counts
        avg_win_dollars, avg_loss_dollars: positive numbers (loss as positive)
    """
    n = wins + losses
    if n < 10:
        return 1.0   # not enough data, use base size
    if avg_loss_dollars <= 0:
        return max_frac   # all wins — clip to max to be safe
    p = wins / n
    q = 1 - p
    b = avg_win_dollars / avg_loss_dollars
    if b <= 0:
        return min_frac
    f = (b * p - q) / b
    if half_kelly:
        f = f / 2
    return float(np.clip(f, min_frac, max_frac))


def size_for_strategy(name: str,
                       recent_pnls: list[float],
                       base_contracts: int = 5,
                       *, lookback: int = 60) -> int:
    """Per-strategy adaptive sizer.

    `recent_pnls` is the strategy's last N trade dollar P&Ls (signed).
    Returns the integer contract count to use for the next trade.
    """
    if not recent_pnls:
        return base_contracts
    arr = np.asarray(recent_pnls[-lookback:])
    wins_arr = arr[arr > 0]
    losses_arr = arr[arr <= 0]
    n_wins = len(wins_arr)
    n_losses = len(losses_arr)
    if n_wins == 0 or n_losses == 0:
        return base_contracts
    avg_win = float(wins_arr.mean())
    avg_loss = float(-losses_arr.mean())
    f = kelly_fraction(n_wins, n_losses, avg_win, avg_loss)
    sized = max(1, int(round(base_contracts * f)))
    return sized


# --------------------------------------------------------------------- #
# Persistence — bot's signal engine reads/writes this on every trade
# --------------------------------------------------------------------- #

def load_state() -> dict:
    if not KELLY_STATE_PATH.exists():
        return {"strategies": {}}
    return json.loads(KELLY_STATE_PATH.read_text())


def save_state(state: dict) -> None:
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    KELLY_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    KELLY_STATE_PATH.write_text(json.dumps(state, indent=2, default=str))


def record_trade(name: str, pnl_dollars: float, *, lookback: int = 60) -> None:
    """Append a trade outcome to the strategy's rolling window."""
    state = load_state()
    s = state["strategies"].setdefault(name, {"recent_pnls": []})
    pnls = s["recent_pnls"]
    pnls.append(float(pnl_dollars))
    s["recent_pnls"] = pnls[-lookback * 2:]   # keep 2x lookback for buffer
    save_state(state)


def current_size(name: str, base_contracts: int = 5) -> int:
    state = load_state()
    s = state.get("strategies", {}).get(name)
    if not s:
        return base_contracts
    return size_for_strategy(name, s.get("recent_pnls", []), base_contracts)


# --------------------------------------------------------------------- #
# CLI: compute current sizing for the whole whitelist from 8yr backtest
# --------------------------------------------------------------------- #

def main():
    """Backfill the kelly state from the 8yr backtest then print suggested sizes."""
    print("=" * 80)
    print("ADAPTIVE KELLY SIZER — backfill + print current sizing")
    print("=" * 80)

    # Backfill: simulate per-strategy P&L history from validation_results
    val = json.loads((PROJECT_ROOT / "data" / "validation_results.json").read_text())
    sigs = {k: v for k, v in val["signals"].items() if v.get("recommended")}
    print(f"  whitelist: {len(sigs)} strategies\n")

    print(f"{'name':<32} {'wr':>5} {'avg_win':>9} {'avg_loss':>9} "
          f"{'kelly':>6} {'base':>5} {'sized':>6}")
    print("-" * 75)

    state = {"strategies": {}, "last_updated": datetime.now(timezone.utc).isoformat()}
    for name, info in sigs.items():
        wr = float(info.get("win_rate") or 0)
        n = int(info.get("trades") or 0)
        net = float(info.get("net_pnl") or 0)
        # Use the per-trade EV implied by net + win_rate
        if n == 0 or wr <= 0 or wr >= 1:
            continue
        ev = net / n
        # Solve for avg_win, avg_loss given:
        #   ev = wr * avg_win - (1-wr) * avg_loss
        # We don't have separate distributions, so use stop/target as proxy:
        stop = float(info.get("stop_pts") or 15)
        target = float(info.get("target_pts") or 30)
        # In V3 strategies trades exit at fixed stop or target; assume that here.
        contracts = 5 if (name.startswith("V3_") or name.startswith("WR_")) else 30
        avg_win = target * contracts * 2 - contracts * 2     # less commission
        avg_loss = stop * contracts * 2 + contracts * 2      # plus commission
        f = kelly_fraction(int(wr * n), int((1 - wr) * n), avg_win, avg_loss)
        sized = max(1, int(round(contracts * f)))
        print(f"{name:<32} {wr*100:>4.1f}% ${avg_win:>+8,.0f} ${avg_loss:>+8,.0f} "
              f"{f:>5.2f}x {contracts:>5} {sized:>6}")
        state["strategies"][name] = {
            "kelly_fraction": f,
            "base_contracts": contracts,
            "sized_contracts": sized,
            "wr": wr, "avg_win": avg_win, "avg_loss": avg_loss,
            "recent_pnls": [],   # populated by record_trade as bot trades
        }

    save_state(state)
    print(f"\n  Wrote -> {KELLY_STATE_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
