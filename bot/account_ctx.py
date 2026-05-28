"""Account context — per-thread account routing for the dual-account
deployment. Each bot thread sets its account_id on startup; module-level
data paths resolve dynamically based on the current thread's context.

The dashboard's Flask worker threads set the account from the ?account=N
query param via a before_request hook in dashboard/server.py.

Backward compatibility: if no account is set, falls back to "1" so
existing single-account deployments keep working.
"""
from __future__ import annotations
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

_local = threading.local()
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_LEGACY_DATA = _PROJECT_ROOT / "data"


def set_account(account_id: str) -> None:
    """Bind the current thread to an account. Bot threads call this once
    on startup; Flask request handlers call this on each request based on
    the ?account=N query string."""
    _local.account_id = str(account_id)


def get_account() -> str:
    """Returns the current thread's account_id, or '1' if unset."""
    return getattr(_local, "account_id", "1")


def data_dir() -> Path:
    """Per-account data directory.

    Account "1" uses the legacy path data/ for backward compatibility --
    i.e. the existing $1.3k paper-trading history stays at data/ and is
    automatically the "Account 1" view. New accounts (2, 3, ...) live at
    data/account_<N>/.
    """
    acct = get_account()
    if acct == "1":
        return _LEGACY_DATA
    p = _LEGACY_DATA / f"account_{acct}"
    p.mkdir(parents=True, exist_ok=True)
    return p


def list_known_accounts() -> list[str]:
    """Enumerate accounts that have been initialised (have a directory).
    Always includes "1" (the legacy account). Used by the dashboard to
    populate the account selector dropdown."""
    out = ["1"]
    if _LEGACY_DATA.exists():
        for sub in sorted(_LEGACY_DATA.iterdir()):
            if sub.is_dir() and sub.name.startswith("account_"):
                aid = sub.name.replace("account_", "")
                if aid != "1":
                    out.append(aid)
    return out


# ---------------------------------------------------------------------------
# Per-account strategy params -- account 1 stays on the original target=12
# config (preserves the existing $1.3k+ live track record); account 2 runs
# the upgraded target=18 config so the user can A/B compare live.
# ---------------------------------------------------------------------------
_DEFAULT_PARAMS = {
    # ACCOUNT 1 -- pre-upgrade baseline (deployed since the bot first went live)
    "1": {
        "IMPULSE_PTS":        5.0,
        "IMPULSE_WINDOW_BARS": 4,
        "PULLBACK_PCT":       0.618,
        "STOP_PTS":           6.0,
        "TARGET_PTS":         12.0,   # original target
    },
    # ACCOUNT 2 -- upgraded target=18 config (from strategy_bakeoff_tick.py)
    # validated +27.04%/mo median Monte Carlo, OOS-positive on both halves.
    "2": {
        "IMPULSE_PTS":        5.0,
        "IMPULSE_WINDOW_BARS": 4,
        "PULLBACK_PCT":       0.618,
        "STOP_PTS":           6.0,
        "TARGET_PTS":         18.0,   # wider target -- $72 winners vs $48
    },
    # ACCOUNT 3 -- target=18 + multi-layer smart filter:
    #   (a) skip new entries when 14-bar ATR < 4 pt (low-vol drift days)
    #   (b) skip new entries when 5-bar ATR / 60-bar ATR < 0.5
    #       (the "calm before the storm" zone: 69.6% loss rate, NET
    #        negative P&L in the loss forensics analysis)
    #   (c) when last 4h net move >= 80 pt = "strong trend" detected,
    #       widen counter-trend stops from 6pt -> 10pt so trades survive
    #       intra-trend whipsaws and many hit target.
    #
    # Validated on the 25M-tick dataset:
    #   Baseline target=18: +27.06%/mo, 1.75% DD, -$384 worst day
    #   Account 3 v1 (ATR+adaptive): +28.23%/mo, 1.59% DD, -$338 worst day
    #   Account 3 v2 (this -- adds vol_ratio): +28.65%/mo, 1.59% DD
    # OOS split-half on v2: train DD 1.58 -> 1.44%, val DD 1.63 -> 1.32%
    # Both halves improve. Not overfit.
    "3": {
        "IMPULSE_PTS":        5.0,
        "IMPULSE_WINDOW_BARS": 4,
        "PULLBACK_PCT":       0.618,
        "STOP_PTS":           6.0,
        "TARGET_PTS":         18.0,
        "MIN_ATR":            4.0,
        "MIN_VOL_RATIO":      0.5,
        "STRONG_TREND_LOOKBACK_BARS": 240,
        "STRONG_TREND_THRESHOLD_PTS":  80.0,
        "STOP_PTS_COUNTER_TREND":     10.0,
        # Streak circuit-breaker: after 4 consecutive losses, pause new
        # entries for 60 minutes. Backtest impact: -6%/mo return BUT
        # 68% reduction in 10+ losing streaks (18 -> 8 over 79 days) and
        # worst single-day loss reduced from -$338 to -$258. Designed
        # to protect against extended bad regimes pushing toward the
        # Lucid trail floor.
        "POST_STREAK_LOSSES":     4,
        "POST_STREAK_PAUSE_MINS": 60,
    },
}


def get_strategy_params(account_id: str | None = None) -> dict:
    """Return the strategy parameter dict for an account. Falls back to
    account "2" defaults (the newest config) for any future account IDs not
    explicitly listed."""
    aid = account_id or get_account()
    return dict(_DEFAULT_PARAMS.get(aid, _DEFAULT_PARAMS["2"]))


# ---------------------------------------------------------------------------
# Manual pause flag -- user can pause/resume any account from the dashboard
# to skip suspected bad regimes (anticipated pumps/dumps, or to break out of
# a hot losing streak). Persisted as a tiny JSON file in the account dir so
# the pause state survives Railway restarts and is read by the bot every
# tick without any IPC. Active trades are NOT closed -- pause only blocks
# NEW entries (decision: panic-closing mid-trade could be worse than letting
# it play out, and it's reversible if the user changes their mind).
# ---------------------------------------------------------------------------
def pause_file() -> Path:
    return data_dir() / "manual_pause.json"


def is_paused() -> bool:
    try:
        p = pause_file()
        if not p.exists():
            return False
        return bool(json.loads(p.read_text() or "{}").get("paused"))
    except Exception:
        return False


def get_pause_state() -> dict:
    try:
        p = pause_file()
        if not p.exists():
            return {"paused": False}
        data = json.loads(p.read_text() or "{}")
        if not isinstance(data, dict):
            return {"paused": False}
        return data
    except Exception:
        return {"paused": False}


def set_paused(paused: bool, reason: str = "user_manual") -> dict:
    p = pause_file()
    if paused:
        payload = {
            "paused": True,
            "since": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
        }
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload))
        return payload
    if p.exists():
        try:
            p.unlink()
        except Exception:
            pass
    return {"paused": False}
