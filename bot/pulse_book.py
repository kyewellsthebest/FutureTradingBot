"""The deployed book: one config table, three validated instances.

Single source of truth for what trades where. live_runner spawns one
child process per non-primary instance (env vars are process-global,
so per-market config needs per-market processes); the dashboard's
account selector maps instance ids to the per-account data dirs; and
/api/pulse serves per-instance state from this table.

Validated cells (tick-true, placebo-controlled; causal re-validation
2026-08-15 in progress -- research/CAUSAL.md is the live record).
"""
from __future__ import annotations

import os

# instance id -> config. Instance "1" runs in the primary process
# (data dir = data/), instances "2"/"3" run as child processes with
# BOT_DATA_DIR=data/account_<id>.
BOOK = {
    "1": dict(symbol="MNQ", name="Nasdaq", tick=0.25, dollars_per_pt=2.0,
              impulse_pts=5.0, impulse_bars=6, pull_pct=0.618,
              stop_pts=10.0, target_pts=20.0,
              validated=dict(held_out_usd=20701, trades_per_wk=142,
                             green_quarters="8/8", max_dd_usd=393)),
    "2": dict(symbol="MES", name="S&P 500", tick=0.25, dollars_per_pt=5.0,
              impulse_pts=1.5, impulse_bars=6, pull_pct=0.618,
              stop_pts=3.0, target_pts=6.0,
              validated=dict(held_out_usd=5976, trades_per_wk=136,
                             green_quarters="6/6", max_dd_usd=340)),
    "3": dict(symbol="MYM", name="Dow", tick=1.0, dollars_per_pt=0.5,
              impulse_pts=16.0, impulse_bars=6, pull_pct=0.618,
              stop_pts=20.0, target_pts=40.0,
              validated=dict(held_out_usd=3212, trades_per_wk=125,
                             green_quarters="7/8", max_dd_usd=398)),
}


def book_instances() -> list[str]:
    """Instance ids to run, from PULSE_BOOK (symbols or ids)."""
    raw = os.environ.get("PULSE_BOOK", "MNQ,MES,MYM")
    by_sym = {v["symbol"]: k for k, v in BOOK.items()}
    out = []
    for tok in raw.split(","):
        tok = tok.strip()
        iid = by_sym.get(tok.upper(), tok if tok in BOOK else None)
        if iid and iid not in out:
            out.append(iid)
    return out or ["1"]


def child_env(iid: str, base_data: str) -> dict:
    """Env overrides for a child instance process. Uses the PULSE_*
    override names so live_runner's forced-env layer applies them."""
    cfg = BOOK[iid]
    return {
        "PULSE_CHILD": iid,
        "PULSE_TRADOVATE_SYMBOL": cfg["symbol"],
        "PULSE_POLYGON_CONTRACT": cfg["symbol"],
        "PULSE_STRAT_IMPULSE_PTS": str(cfg["impulse_pts"]),
        "PULSE_STRAT_IMPULSE_BARS": str(cfg["impulse_bars"]),
        "PULSE_STRAT_PULL_PCT": str(cfg["pull_pct"]),
        "PULSE_STRAT_STOP_PTS": str(cfg["stop_pts"]),
        "PULSE_STRAT_TARGET_PTS": str(cfg["target_pts"]),
        "PULSE_STRAT_TICK_SIZE": str(cfg["tick"]),
        "PULSE_STRAT_DOLLARS_PER_PT": str(cfg["dollars_per_pt"]),
        "BOT_DATA_DIR": os.path.join(base_data, f"account_{iid}"),
        "DASHBOARD_DISABLED": "1",   # one dashboard, in the parent
        "PULSE_CANARY": "0",         # one canary, in the parent
    }
