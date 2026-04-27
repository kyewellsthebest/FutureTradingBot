"""
Flask dashboard server (per spec).

Endpoints:
  GET  /                       dashboard.html
  GET  /api/data               full dashboard_data.json payload
  GET  /api/price              latest price + ts (polled every 500ms)
  GET  /api/candles            last ~500 5-min bars (Yahoo + live ledger)
  GET  /api/levels             static PDH/PDL/prev_close/EQ50
  GET  /api/strategy_levels    active signal-event markers (20-min TTL)
  GET  /api/trades             recent trades from SQLite DB
  GET  /api/validation         the recommended-signals whitelist
  GET  /api/health             liveness probe

Also runs its own 5-second CNBC poller that bins ticks into 5-min bars and
persists to data/live_bars.json (288 bars ≈ 24h). The main loop's
_merge_live_bars() glues the live ledger onto the head of yfinance's frame.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from bot import persistence
from bot.price_monitor import _fetch_cnbc
from research.data_loader import DATA_DIR, download_nq
from research.indicators import eq50

logger = logging.getLogger("dashboard")
ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"

LIVE_BARS_PATH = DATA_DIR / "live_bars.json"
SIGNAL_EVENT_TTL_SECONDS = 20 * 60

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
CORS(app)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/static/<path:p>")
def static_files(p):
    return send_from_directory(STATIC_DIR, p)


@app.route("/api/health")
def api_health():
    return jsonify({"ok": True, "ts": datetime.now(timezone.utc).isoformat()})


@app.route("/api/data")
def api_data():
    return jsonify(persistence.load_dashboard())


@app.route("/api/price")
def api_price():
    state = persistence.load_dashboard()
    return jsonify({
        "price": state.get("price"),
        "ts": state.get("price_ts"),
        "monitor_error": state.get("monitor_error"),
    })


@app.route("/api/candles")
def api_candles():
    try:
        df = download_nq("5min").tail(500)
    except Exception as e:
        logger.warning(f"candles fetch failed: {e}")
        return jsonify([])
    # Merge live bars
    if LIVE_BARS_PATH.exists():
        try:
            live = json.loads(LIVE_BARS_PATH.read_text())
            for b in live[-100:]:
                df.loc[b["ts"]] = [b["open"], b["high"], b["low"], b["close"], b["volume"]]
            df = df.sort_index()
            df = df[~df.index.duplicated(keep="last")]
        except Exception:
            pass
    out = []
    for ts, row in df.iterrows():
        out.append({
            "time": int(ts.timestamp()) if hasattr(ts, "timestamp") else 0,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row.get("volume", 0)),
        })
    return jsonify(out)


@app.route("/api/levels")
def api_levels():
    try:
        daily = download_nq("daily")
        intraday = download_nq("5min")
        if daily.empty or intraday.empty:
            return jsonify({})
        prev = daily.iloc[-2] if len(daily) >= 2 else daily.iloc[-1]
        eq = eq50(intraday["high"], intraday["low"], 50).iloc[-1]
        return jsonify({
            "pdh": float(prev["high"]),
            "pdl": float(prev["low"]),
            "prev_close": float(prev["close"]),
            "eq50": float(eq) if eq == eq else None,
        })
    except Exception as e:
        logger.warning(f"levels failed: {e}")
        return jsonify({})


@app.route("/api/strategy_levels")
def api_strategy_levels():
    """Active signal-event markers (20-min TTL)."""
    events = persistence.load_signal_events(limit=50)
    cutoff = time.time() - SIGNAL_EVENT_TTL_SECONDS
    out = []
    for e in events:
        ts = e.get("ts")
        try:
            t = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
        except Exception:
            continue
        if t < cutoff:
            continue
        out.append(e)
    return jsonify(out)


@app.route("/api/trades")
def api_trades():
    return jsonify(persistence.load_trades(limit=200))


@app.route("/api/validation")
def api_validation():
    p = DATA_DIR / "validation_results.json"
    if not p.exists():
        return jsonify({"signals": {}})
    try:
        data = json.loads(p.read_text())
        recommended = [n for n, info in (data.get("signals") or {}).items()
                       if info.get("recommended")]
        return jsonify({"recommended": recommended, "signals": data.get("signals", {})})
    except Exception:
        return jsonify({"signals": {}})


# ---------------------------------------------------------------------------
# CNBC 5-second poller — own thread; not the main bot loop's monitor
# ---------------------------------------------------------------------------

class CnbcLiveBarBuilder:
    def __init__(self, path: Path = LIVE_BARS_PATH, max_bars: int = 288):
        self.path = path
        self.max_bars = max_bars
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._bars: list[dict] = self._load()
        self._cur: dict | None = None
        self._last_flush = 0.0
        self._lock = threading.Lock()

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            return json.loads(self.path.read_text())[-self.max_bars:]
        except Exception:
            return []

    def _flush(self) -> None:
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps(self._bars[-self.max_bars:]))
            except Exception:
                pass

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop,
                                        name="CnbcPoller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._tick_once()
            self._stop.wait(5)

    def _tick_once(self) -> None:
        res = _fetch_cnbc()
        if res is None:
            return
        price, _, _ = res
        now = datetime.now(timezone.utc)
        bin_ts = now.replace(second=0, microsecond=0)
        bin_ts = bin_ts.replace(minute=(bin_ts.minute // 5) * 5)
        bin_iso = bin_ts.isoformat()
        if self._cur is None or self._cur["ts"] != bin_iso:
            if self._cur is not None:
                self._bars.append(self._cur)
                self._bars = self._bars[-self.max_bars:]
            self._cur = {"ts": bin_iso, "open": price, "high": price,
                         "low": price, "close": price, "volume": 0.0}
        else:
            self._cur["high"] = max(self._cur["high"], price)
            self._cur["low"] = min(self._cur["low"], price)
            self._cur["close"] = price
        # flush every 30s
        if time.time() - self._last_flush > 30:
            with self._lock:
                snap = list(self._bars)
                if self._cur is not None:
                    snap = snap + [self._cur]
                self.path.write_text(json.dumps(snap[-self.max_bars:]))
            self._last_flush = time.time()


_poller: CnbcLiveBarBuilder | None = None


def _start_poller() -> None:
    global _poller
    if _poller is None:
        _poller = CnbcLiveBarBuilder()
        _poller.start()
        logger.info("CNBC 5s poller started")


# ---------------------------------------------------------------------------

def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    host = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
    port = int(os.environ.get("DASHBOARD_PORT", "5000"))
    if os.environ.get("DASHBOARD_NO_POLLER") != "1":
        _start_poller()
    logger.info(f"http://{host}:{port}")
    app.run(host=host, port=port, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
