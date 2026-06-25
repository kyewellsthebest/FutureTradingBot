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
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

_local = threading.local()
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_legacy_data() -> Path:
    """Resolve the base data directory in this priority order:
       1. BOT_DATA_DIR env var (explicit, used on Railway with the
          persistent volume mounted at /app/data)
       2. <project_root>/data (legacy / local dev)
    """
    env_dir = os.environ.get("BOT_DATA_DIR")
    if env_dir:
        p = Path(env_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p
    return _PROJECT_ROOT / "data"


_LEGACY_DATA = _resolve_legacy_data()


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
# Per-account strategy params. Currently only the legacy account 1 is
# active -- accounts 2 and 3 (the target=18 upgrade and filtered variant)
# were removed by user request.
#
# IMPORTANT: these values are passed through detect_pullback_setup() as the
# `params` dict and OVERRIDE the module-level defaults in
# bot.pullback_strategy. To allow Railway env vars (STRAT_PULL_PCT,
# STRAT_STOP_PTS, STRAT_TARGET_PTS, STRAT_IMPULSE_PTS, STRAT_IMPULSE_BARS,
# STRAT_INVERT) to actually take effect, we read those env vars HERE rather
# than hardcoding numbers. Each env var defaults to the original baseline
# so an unconfigured deploy still gets the legacy behaviour.
# ---------------------------------------------------------------------------
_DEFAULT_PARAMS = {
    # ACCOUNT 1 -- env-driven so Railway config is the source of truth.
    #
    # Defaults below are the VALIDATED "S2 winner" config from the faithful
    # tick-data search (research/tick_strategy_findings.md): inverse-fade a
    # shallow 0.118 pullback, tight 5pt stop, large 44pt target. On 24.9M
    # real NQ ticks (Dec 2025-Feb 2026) under the bot's exact execution
    # model ($0.74 RT, 0.25pt stop slip, $2/pt, 60s cd, 600s max-hold) this
    # nets ~+$1,034/day per MNQ (worst month +$620, OOS +$1,515), maxDD
    # ~$550, profit spread across ~11k trades (top-10 = 1.2% of net), and
    # holds up at 4x worse slippage. Env vars still override everything.
    #
    # Conservative alternative (further-from-price entry = most trustworthy
    # fills, lower return): PULL=0.236, STOP=6, TARGET=30, IMPULSE=3,
    # WINDOW=4 -> ~+$528/day per MNQ.
    "1": {
        "IMPULSE_PTS":         float(os.environ.get("STRAT_IMPULSE_PTS", "2.0")),
        "IMPULSE_WINDOW_BARS": int(os.environ.get("STRAT_IMPULSE_BARS", "3")),
        "PULLBACK_PCT":        float(os.environ.get("STRAT_PULL_PCT", "0.118")),
        "STOP_PTS":            float(os.environ.get("STRAT_STOP_PTS", "5.0")),
        "TARGET_PTS":          float(os.environ.get("STRAT_TARGET_PTS", "44.0")),
        "INVERT":              os.environ.get("STRAT_INVERT", "1") == "1",
    },
}


def get_strategy_params(account_id: str | None = None) -> dict:
    """Return the strategy parameter dict for an account. Falls back to
    account 1 (the only live config) for any unknown account IDs."""
    aid = account_id or get_account()
    return dict(_DEFAULT_PARAMS.get(aid, _DEFAULT_PARAMS["1"]))


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
