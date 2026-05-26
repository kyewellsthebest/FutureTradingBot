"""Account context — per-thread account routing for the dual-account
deployment. Each bot thread sets its account_id on startup; module-level
data paths resolve dynamically based on the current thread's context.

The dashboard's Flask worker threads set the account from the ?account=N
query param via a before_request hook in dashboard/server.py.

Backward compatibility: if no account is set, falls back to "1" so
existing single-account deployments keep working.
"""
from __future__ import annotations
import threading
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
