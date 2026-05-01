"""
24/7 live entrypoint for Railway / any single-process host.

Spawns:
  1. The 60-second bot loop (bot.main.Runtime.run) in a background thread
  2. The Flask dashboard (dashboard.server.app) bound to $PORT in the main thread

Railway sets PORT — we honor it. State persists to data/ which Railway keeps
across restarts as long as a volume is mounted (otherwise the funded-account
ledger and trade DB are ephemeral).

Crash recovery: if the bot thread dies the dashboard keeps serving the last
snapshot. The Procfile / railway.json restarts the whole container if the
dashboard process exits non-zero.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time

# Bind once before importing anything else that touches DATA_DIR
os.makedirs("data", exist_ok=True)
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("live_runner")


def _bot_thread() -> None:
    """Run the 60-second tick loop. Catches and re-runs on uncaught crash."""
    while True:
        try:
            from bot.main import Runtime
            log.info("starting bot loop")
            Runtime().run()
            log.warning("bot loop exited cleanly — restarting in 5s")
        except Exception as e:
            log.exception(f"bot loop crashed: {e} — restarting in 30s")
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
    # Background dashboard
    t = threading.Thread(target=_flask_thread, name="flask-dashboard", daemon=True)
    t.start()
    # Main thread runs the bot loop (so signal handlers install correctly)
    _bot_thread()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
