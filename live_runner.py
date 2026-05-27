"""
24/7 live entrypoint for Railway / any single-process host.

Spawns:
  1. The 60-second bot loop (bot.main.Runtime.run) on the main thread
  2. The Flask dashboard (dashboard.server.app) on $PORT in a daemon thread

On startup we ALSO seed the runtime data dir (`data/`) from the bundled
static config (`bundled/`) — this is critical because Railway Volumes
mounted at `/app/data` SHADOW the repo's `data/` directory, hiding the
config files (validation_results.json, macro CSVs) that ship with the
code. Bootstrap copies those over once on first boot if missing.

Crash recovery: if the bot thread dies the dashboard keeps serving the last
snapshot. The Procfile / railway.json restarts the whole container if the
dashboard process exits non-zero.
"""
from __future__ import annotations

import logging
import os
import shutil
import sys
import threading
import time
from pathlib import Path

# Bind once before importing anything else that touches DATA_DIR
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
BUNDLED_DIR = ROOT / "bundled"
DATA_DIR.mkdir(exist_ok=True)
(ROOT / "logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("live_runner")


def _bootstrap_bundled_config() -> None:
    """Copy bundled config files into data/ if missing — needed when a
    Railway Volume is mounted at /app/data and shadows the repo's data dir.
    Without this, validation_results.json (the strategy whitelist) and the
    macro CSVs would all be invisible to the live bot."""
    if not BUNDLED_DIR.exists():
        log.warning(f"bundled/ not found at {BUNDLED_DIR}; skipping bootstrap")
        return
    copied = 0
    for src in BUNDLED_DIR.iterdir():
        if not src.is_file():
            continue
        dst = DATA_DIR / src.name
        if not dst.exists():
            try:
                shutil.copy2(src, dst)
                copied += 1
                log.info(f"bootstrapped data/{src.name} from bundled/ ({src.stat().st_size:,} bytes)")
            except Exception as e:
                log.error(f"failed to copy {src} -> {dst}: {e}")
    if copied:
        log.info(f"bootstrap copied {copied} static config files into data/")
    else:
        log.info("bundled config already present in data/ — no bootstrap needed")


def _bot_thread(account_id: str = "1") -> None:
    """Run the bot tick loop for one specific account. Catches and re-runs
    on uncaught crash. Defaults to account_id="1" for backwards compat with
    single-account deployments.

    Default runtime is the Fib 50% retracement strategy. Set BOT_VERSION=v11
    to fall back to the old NQ-ES stat-arb book; BOT_VERSION=legacy for the
    V3 runtime. BOT_SHADOW_MODE=0 in env switches Fib from shadow to live.
    """
    # Bind THIS thread to its account so all module-level path lookups
    # (persistence, lucid_account, fib_main DASHBOARD_PATH) resolve to
    # data/account_<N>/ for non-default accounts.
    from bot.account_ctx import set_account, data_dir as _dd
    set_account(account_id)
    bot_version = os.environ.get("BOT_VERSION", "fib").lower()
    import traceback as _tb
    crash_log = _dd() / "bot_crash.txt"
    heartbeat = _dd() / "bot_heartbeat.txt"
    def _hb(step: str) -> None:
        try:
            heartbeat.write_text(
                f"step={step} account={account_id} "
                f"time={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} "
                f"version={bot_version}\n")
        except Exception:
            pass
    while True:
        try:
            _hb("importing_runtime")
            if bot_version == "legacy":
                from bot.main import Runtime
                log.info(f"[acct {account_id}] starting LEGACY bot loop")
                rt = Runtime()
            elif bot_version == "v11":
                from bot.v11_main import V11Runtime as Runtime
                log.info(f"[acct {account_id}] starting v11 bot loop")
                rt = Runtime()
            else:
                from bot.fib_main import FibRuntime
                mode = "SHADOW" if os.environ.get("BOT_SHADOW_MODE", "1") == "1" else "LIVE"
                log.info(f"[acct {account_id}] starting Fib 50% bot ({mode} mode)")
                rt = FibRuntime(account_id=account_id)
            _hb("entering_run_loop")
            rt.run()
            log.warning(f"[acct {account_id}] bot loop exited cleanly — restarting in 5s")
        except Exception as e:
            tb = _tb.format_exc()
            log.exception(f"[acct {account_id}] bot loop crashed: {e} — restarting in 30s")
            try:
                crash_log.write_text(
                    f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] "
                    f"account={account_id} version={bot_version}  crash: {e!r}\n\n{tb}")
            except Exception:
                pass
            time.sleep(30)
            continue
        time.sleep(5)


def _flask_thread() -> None:
    """Serve the Flask dashboard. Bot loop runs on the main thread because it
    needs to install SIGINT/SIGTERM handlers."""
    port = int(os.environ.get("PORT", "5000"))
    host = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
    log.info(f"dashboard listening on http://{host}:{port}")
    if os.environ.get("DASHBOARD_NO_POLLER") != "1":
        from dashboard.server import _start_poller
        _start_poller()
    from dashboard.server import app
    app.run(host=host, port=port, debug=False, use_reloader=False)


def main() -> int:
    _bootstrap_bundled_config()
    # Background dashboard
    t = threading.Thread(target=_flask_thread, name="flask-dashboard", daemon=True)
    t.start()
    # Parse ACCOUNTS env var: comma-separated list of account IDs to run.
    # Default "1,2" -- user explicitly asked for the "Futures Trading Bot 2"
    # account in addition to the existing one. Override via ACCOUNTS env if
    # you want a different set.
    # Default "1,2,3" -- A/B/C: legacy target=12, upgrade target=18,
    # filtered target=18+ATR>=4 (lowest DD config). User can override
    # via ACCOUNTS env to disable any of them.
    accounts = [a.strip() for a in os.environ.get("ACCOUNTS", "1,2,3").split(",") if a.strip()]
    if len(accounts) == 1:
        # Single-account mode: run on the main thread so SIGINT/SIGTERM
        # handlers install correctly (only main thread can install them).
        _bot_thread(accounts[0])
    else:
        # Multi-account mode: spawn each non-primary account in a daemon
        # thread, run the first account on the main thread (for signals).
        log.info(f"multi-account mode -- launching {len(accounts)} accounts: {accounts}")
        for aid in accounts[1:]:
            th = threading.Thread(target=_bot_thread, args=(aid,),
                                  name=f"bot-acct-{aid}", daemon=True)
            th.start()
        _bot_thread(accounts[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
