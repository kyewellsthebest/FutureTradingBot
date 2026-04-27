"""
Flask dashboard server.

Endpoints:
  GET  /                  static index.html
  GET  /static/<path>     bundled JS/CSS (lightweightcharts.js etc.)
  GET  /api/state         current dashboard JSON
  GET  /api/candles       last N intraday candles for the chart
  GET  /api/trades        recent closed trades
  GET  /api/health        simple liveness probe

Run with:  python -m dashboard.server   (defaults to 0.0.0.0:5000)
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from bot import persistence
from research.data_loader import download_nq

logger = logging.getLogger("dashboard")
ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
CORS(app)


@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/static/<path:p>")
def static_files(p):
    return send_from_directory(STATIC_DIR, p)


@app.route("/api/health")
def health():
    return jsonify({"ok": True})


@app.route("/api/state")
def api_state():
    return jsonify(persistence.load_dashboard())


@app.route("/api/trades")
def api_trades():
    return jsonify(persistence.load_trades(limit=200))


@app.route("/api/candles")
def api_candles():
    df = download_nq("5min").tail(500)
    out = []
    for ts, row in df.iterrows():
        out.append({
            "time": int(ts.timestamp()),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        })
    return jsonify(out)


@app.route("/api/whitelist")
def api_whitelist():
    state = persistence.load_dashboard()
    return jsonify(state.get("whitelist", []))


@app.route("/api/strategy_report")
def api_strategy_report():
    p = ROOT.parent / "data" / "strategy_report.txt"
    if not p.exists():
        return jsonify({"text": ""})
    return jsonify({"text": p.read_text(errors="replace")})


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    host = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
    port = int(os.environ.get("DASHBOARD_PORT", "5000"))
    logger.info("[dashboard] http://%s:%d", host, port)
    app.run(host=host, port=port, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
