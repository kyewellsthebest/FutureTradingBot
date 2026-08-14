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

# ---------------------------------------------------------------------------
# PULSE CUTOVER (2026-08-14). The old deployment (basket sleeves on ZB/ZN,
# S2 inverse-fade, shadow toggles) left env vars on the Railway service that
# silently overrode every new code default — the 2026-08-14 deploy pushed
# clean code and the host kept trading the old system. So the entrypoint now
# FORCES the validated configuration: each key below is written into
# os.environ at boot, stomping whatever the host has. Per-instance overrides
# (the MES / MYM services) use NEW names — PULSE_<KEY> — which old deploys
# cannot possess. deploy/CUTOVER.md has the three service blocks.
#
# Validated cells (tick-true, placebo-controlled, research/PULSE*.md):
#   MNQ imp 5/6bar retr .618 stop 10 tgt 20  -> +$20,701 held-out, 8/8 q
#   MES imp 1.5/6  retr .618 stop  3 tgt  6  ->  +$5,976 held-out, 6/6 q
#   MYM imp 16/6   retr .618 stop 20 tgt 40  ->  +$3,212 held-out, 7/8 q
# ---------------------------------------------------------------------------
PULSE_FORCED_ENV = {
    "BOT_VERSION": "fib",           # FibRuntime hosts the pullback executor
    "BROKER_ENGINE": "pulse",       # anything else routes to retired engines
    "BOT_SHADOW_MODE": "0",         # live orders on the (demo) broker
    "BASKET_ENABLED": "0",          # snap-back basket (ZB/ZN sleeves) RETIRED
    "ANTICIPATORY_ENABLED": "0",
    "ACCOUNTS": "1",                # one instance per service
    "TRADOVATE_SYMBOL": "MNQ",
    "POLYGON_CONTRACT": "MNQ",
    "FIB_N_MNQ": "1",               # 1 micro per trade on a $4k account
    "STRAT_IMPULSE_PTS": "5.0",
    "STRAT_IMPULSE_BARS": "6",
    "STRAT_PULL_PCT": "0.618",
    "STRAT_STOP_PTS": "10.0",
    "STRAT_TARGET_PTS": "20.0",
    "STRAT_INVERT": "0",
    "STRAT_TICK_SIZE": "0.25",      # MYM service must set PULSE_STRAT_TICK_SIZE=1.0
}


def _force_pulse_config() -> None:
    """Stomp strategy-critical env vars with the validated deployment,
    BEFORE any bot module is imported (several read env at import time).
    A PULSE_<KEY> env var is the only way to override a forced key."""
    for k, v in PULSE_FORCED_ENV.items():
        override = os.environ.get("PULSE_" + k)
        chosen = override if override not in (None, "") else v
        old = os.environ.get(k)
        if old is not None and old != chosen:
            log.warning(f"stale env {k}={old!r} overridden -> {chosen!r}"
                        f"{' (via PULSE_' + k + ')' if override else ''}")
        os.environ[k] = chosen


# Bump the suffix to force another one-time wipe on a future cutover.
RESET_MARKER = "pulse_reset_v1.done"


def _purge_old_state() -> None:
    """One-time wipe of the persistent data volume (user order 2026-08-14:
    'get rid of the current strategies and previous trading history and
    statistics'). Railway Volumes mounted at /app/data SHADOW the repo's
    data/ dir, so deleting state files from git NEVER touches the host —
    the old 318-trade history survived the previous deploy that way. This
    deletes everything in the data dir once, then leaves a marker so
    normal restarts keep their state."""
    tgt = Path(os.environ.get("BOT_DATA_DIR") or DATA_DIR)
    tgt.mkdir(parents=True, exist_ok=True)
    marker = tgt / RESET_MARKER
    if marker.exists():
        return
    removed, failed = 0, 0
    for p in tgt.iterdir():
        try:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            removed += 1
        except Exception as e:
            failed += 1
            log.error(f"purge failed for {p}: {e}")
    try:
        marker.write_text(
            f"pre-pulse state purged at "
            f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} "
            f"({removed} entries removed, {failed} failed)\n")
    except Exception as e:
        log.error(f"could not write reset marker: {e}")
    log.warning(f"PULSE RESET: purged {removed} entries from {tgt} "
                f"(old basket/paper history gone); marker={marker.name}")


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
                mode = "SHADOW" if os.environ.get("BOT_SHADOW_MODE", "0") == "1" else "LIVE"
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
    _force_pulse_config()
    _purge_old_state()
    _bootstrap_bundled_config()
    # Background dashboard
    t = threading.Thread(target=_flask_thread, name="flask-dashboard", daemon=True)
    t.start()
    # Parse ACCOUNTS env var: comma-separated list of account IDs to run.
    # Default is single-account ("1") -- the original legacy account with
    # target=12. Accounts 2/3 (the target=18 upgrade and the filtered
    # variant) were removed; override via ACCOUNTS env to revive them.
    accounts = [a.strip() for a in os.environ.get("ACCOUNTS", "1").split(",") if a.strip()]
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
