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

import pandas as pd
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
    """NQ=F 5-min bars for the lightweight-charts chart. Force-refreshes
    yfinance (no cache) and merges the CNBC live-bar ledger on top so the
    most recent 1-2 bars are as fresh as possible."""
    df = None
    try:
        df = download_nq("5min", force_refresh=True).tail(500)
    except Exception as e:
        logger.warning(f"candles fetch failed: {e}")
        try:
            df = download_nq("5min").tail(500)
        except Exception:
            return jsonify([])
    if df is None or df.empty:
        return jsonify([])
    # Merge live bars (CNBC poller — fresher than yfinance for the
    # most recent 1-2 5-min windows)
    if LIVE_BARS_PATH.exists():
        try:
            live = json.loads(LIVE_BARS_PATH.read_text())
            for b in live[-100:]:
                ts = pd.Timestamp(b["ts"])
                if ts.tz is None: ts = ts.tz_localize("UTC")
                if df.index.tz is None and ts.tz is not None:
                    ts = ts.tz_localize(None)
                df.loc[ts, "open"]   = float(b["open"])
                df.loc[ts, "high"]   = float(b["high"])
                df.loc[ts, "low"]    = float(b["low"])
                df.loc[ts, "close"]  = float(b["close"])
                df.loc[ts, "volume"] = float(b.get("volume", 0))
            df = df.sort_index()
            df = df[~df.index.duplicated(keep="last")]
        except Exception as e:
            logger.warning(f"candles merge live_bars failed: {e}")
    out = []
    for ts, row in df.iterrows():
        try:
            t = int(pd.Timestamp(ts).timestamp())
        except Exception:
            continue
        out.append({
            "time": t,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row.get("volume", 0)),
        })
    return jsonify(out)


@app.route("/api/trade_markers")
def api_trade_markers():
    """Up/down arrow markers for the last 100 trades, ready to drop into
    lightweight-charts via series.setMarkers()."""
    trades = persistence.load_trades(limit=100)
    out = []
    for t in trades:
        try:
            entry_t = int(pd.Timestamp(t["entry_time"]).timestamp())
        except Exception:
            continue
        side = t.get("side")
        pnl = t.get("pnl")
        won = pnl is not None and pnl > 0
        out.append({
            "time": entry_t,
            "position": "belowBar" if side == "LONG" else "aboveBar",
            "color": "#26a69a" if side == "LONG" else "#ef5350",
            "shape": "arrowUp" if side == "LONG" else "arrowDown",
            "text": f"{side[0]}{int(t.get('qty') or 0)}",  # L12 / S8
        })
        # Add an exit marker if the trade is closed
        if t.get("exit_time"):
            try:
                exit_t = int(pd.Timestamp(t["exit_time"]).timestamp())
            except Exception:
                continue
            out.append({
                "time": exit_t,
                "position": "aboveBar" if side == "LONG" else "belowBar",
                "color": "#26a69a" if won else "#ef5350",
                "shape": "circle",
                "text": (f"+${pnl:.0f}" if won else f"-${abs(pnl):.0f}") if pnl is not None else "",
            })
    # lightweight-charts requires markers sorted by time
    out.sort(key=lambda m: m["time"])
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


@app.route("/api/live_position")
def api_live_position():
    """Open-position state with live unrealized P&L vs the latest price."""
    state = persistence.load_dashboard()
    acct = state.get("account") or {}
    op = acct.get("open_position")
    px = state.get("price")
    if not op or px is None:
        return jsonify({"in_trade": False, "price": px})
    side = op.get("side")
    entry = float(op.get("entry_px") or 0)
    stop  = float(op.get("stop_px")  or 0)
    tgt   = float(op.get("target_px") or 0)
    qty   = int(op.get("qty") or 0)
    dpp   = float(state.get("dollars_per_point") or 2.0)  # MNQ = $2/pt
    if side == "LONG":
        pts_pnl = px - entry
        pts_to_stop   = px - stop
        pts_to_target = tgt - px
    else:
        pts_pnl = entry - px
        pts_to_stop   = stop - px
        pts_to_target = px - tgt
    unrealized = pts_pnl * dpp * qty
    risk = abs(entry - stop) * dpp * qty
    reward = abs(tgt - entry) * dpp * qty
    # progress 0..1 from stop -> target
    span = abs(tgt - stop)
    progress = max(0.0, min(1.0, abs(px - stop) / span)) if span > 0 else 0.5
    if side == "SHORT":
        progress = 1 - progress  # SHORT: stop above, target below
    return jsonify({
        "in_trade": True,
        "signal": op.get("signal_name"),
        "side": side, "qty": qty,
        "entry_px": entry, "stop_px": stop, "target_px": tgt,
        "current_px": px,
        "unrealized_pnl": unrealized,
        "pts_pnl": pts_pnl,
        "pts_to_stop": pts_to_stop,
        "pts_to_target": pts_to_target,
        "risk_at_stop": -risk,
        "reward_at_target": reward,
        "progress_to_target": progress,
        "entry_time": op.get("entry_time"),
    })


@app.route("/api/brain")
def api_brain():
    """What the bot is thinking right now: readiness, signal events, watchlist."""
    state = persistence.load_dashboard()
    acct = state.get("account") or {}
    in_trade = bool(acct.get("open_position"))
    # Most recent signal events (entries / exits / blocks)
    events = persistence.load_signal_events(limit=20) or []
    # Whitelist of strategies being evaluated each tick
    p = DATA_DIR / "validation_results.json"
    whitelist = []
    if p.exists():
        try:
            data = json.loads(p.read_text())
            for n, info in (data.get("signals") or {}).items():
                if info.get("recommended"):
                    whitelist.append({
                        "name": n,
                        "side": info.get("side") or ("LONG" if "_LONG" in n else "SHORT"),
                        "win_rate": info.get("win_rate"),
                        "stop_pts": info.get("stop_pts"),
                        "target_pts": info.get("target_pts"),
                    })
        except Exception:
            pass
    today = state.get("today") or {}
    n_entries = sum(1 for e in events if e.get("type") == "ENTRY")
    n_blocked = sum(1 for e in events if e.get("type") == "BLOCKED")
    n_exits = sum(1 for e in events if e.get("type") == "EXIT")
    return jsonify({
        "cycle": state.get("cycle"),
        "as_of": state.get("as_of"),
        "in_trade": in_trade,
        "kill_zone": state.get("kill_zone") or {},
        "trade_readiness": state.get("trade_readiness") or {},
        "today_trades": today.get("trades", 0),
        "today_wins": today.get("wins", 0),
        "today_losses": today.get("losses", 0),
        "n_recent_entries": n_entries,
        "n_recent_blocked": n_blocked,
        "n_recent_exits": n_exits,
        "events": events[-30:],
        "whitelist": whitelist,
        "n_strategies_watched": len(whitelist),
    })


@app.route("/api/freshness")
def api_freshness():
    """Last 5-min bar timestamp + age in seconds, for the chart freshness pill."""
    try:
        df = download_nq("5min").tail(1)
        if LIVE_BARS_PATH.exists():
            try:
                live = json.loads(LIVE_BARS_PATH.read_text())
                if live:
                    latest_live = pd.Timestamp(live[-1]["ts"])
                    if latest_live.tz is None:
                        latest_live = latest_live.tz_localize("UTC")
                    if not df.empty:
                        latest_yf = df.index[-1]
                        if latest_yf.tz is None:
                            latest_yf = pd.Timestamp(latest_yf).tz_localize("UTC")
                        if latest_live > latest_yf:
                            age = (pd.Timestamp.now(tz="UTC") - latest_live).total_seconds()
                            return jsonify({"last_bar": latest_live.isoformat(),
                                              "age_seconds": int(age),
                                              "source": "cnbc_live"})
            except Exception:
                pass
        if df.empty:
            return jsonify({"last_bar": None, "age_seconds": None, "source": "none"})
        latest = df.index[-1]
        if latest.tz is None:
            latest = pd.Timestamp(latest).tz_localize("UTC")
        age = (pd.Timestamp.now(tz="UTC") - latest).total_seconds()
        return jsonify({"last_bar": latest.isoformat(),
                          "age_seconds": int(age),
                          "source": "yfinance"})
    except Exception as e:
        return jsonify({"last_bar": None, "age_seconds": None, "error": str(e)})


@app.route("/api/trades")
def api_trades():
    return jsonify(persistence.load_trades(limit=200))


@app.route("/api/last_trades")
def api_last_trades():
    """Last 100 trades for the live dashboard table + chart."""
    return jsonify(persistence.load_trades(limit=100))


@app.route("/api/lucid_account")
def api_lucid_account():
    """Live Lucid 50K Pro Funded account state."""
    state = persistence.load_dashboard()
    return jsonify(state.get("lucid_account") or {})


@app.route("/api/funded_accounts")
def api_funded_accounts():
    """Funded-accounts ledger: passed/failed counts + archived account history."""
    state = persistence.load_dashboard()
    return jsonify(state.get("funded_accounts") or {
        "n_passed": 0, "n_failed": 0, "active_account_id": 1,
        "total_runs": 0, "history": [],
    })


@app.route("/api/live_chart")
def api_live_chart():
    """Plotly figure JSON: last ~24h of NQ 5-min candles, pure price chart.

    Tries yfinance first (force-refresh, no cache). If that fails, falls back
    to the CNBC live-bar ledger (data/live_bars.json). If both are empty,
    returns an error string the frontend can show in the chart container.
    """
    import plotly.graph_objects as go
    df = None
    source = None
    err = None
    # Try yfinance
    try:
        df = download_nq("5min", force_refresh=True).tail(288)
        if df is not None and not df.empty:
            source = "yfinance"
    except Exception as e:
        err = f"yfinance: {e!r}"
        df = None
    # If yfinance gave nothing, fall back to the CNBC live-bar ledger
    if (df is None or df.empty) and LIVE_BARS_PATH.exists():
        try:
            live = json.loads(LIVE_BARS_PATH.read_text())
            if live:
                rows = []
                for b in live[-288:]:
                    rows.append({
                        "ts": pd.Timestamp(b["ts"]),
                        "open": float(b["open"]), "high": float(b["high"]),
                        "low": float(b["low"]), "close": float(b["close"]),
                        "volume": float(b.get("volume", 0)),
                    })
                df = pd.DataFrame(rows).set_index("ts").sort_index()
                source = "cnbc_live_bars"
        except Exception as e:
            err = f"{err or ''} | cnbc: {e!r}"
    if df is None or df.empty:
        return jsonify({
            "error": "no price data — yfinance and CNBC feeds both unavailable",
            "detail": err or "(no data)",
        })

    # Merge live-bars on top of yfinance for the most recent 1-2 bars
    if source == "yfinance" and LIVE_BARS_PATH.exists():
        try:
            live = json.loads(LIVE_BARS_PATH.read_text())
            for b in live[-100:]:
                ts = pd.Timestamp(b["ts"])
                if ts.tz is None: ts = ts.tz_localize("UTC")
                if df.index.tz is None and ts.tz is not None:
                    ts = ts.tz_localize(None)
                df.loc[ts, "open"]   = float(b["open"])
                df.loc[ts, "high"]   = float(b["high"])
                df.loc[ts, "low"]    = float(b["low"])
                df.loc[ts, "close"]  = float(b["close"])
                df.loc[ts, "volume"] = float(b.get("volume", 0))
            df = df.sort_index()
            df = df[~df.index.duplicated(keep="last")]
        except Exception as e:
            logger.warning(f"live_chart merge live_bars failed: {e}")

    # Strip timezone for plotly
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["open"], high=df["high"],
        low=df["low"], close=df["close"],
        increasing=dict(line=dict(color="#26a69a", width=1), fillcolor="#26a69a"),
        decreasing=dict(line=dict(color="#ef5350", width=1), fillcolor="#ef5350"),
        name="NQ", showlegend=False,
    ))
    fig.update_layout(
        plot_bgcolor="#131722", paper_bgcolor="#131722",
        font=dict(color="#d1d4dc"),
        height=520,
        margin=dict(l=50, r=20, t=10, b=40),
        xaxis=dict(
            rangeslider=dict(visible=False),
            gridcolor="#1e222d", color="#787b86",
            rangebreaks=[dict(bounds=["sat", "mon"])],
            type="date",
        ),
        yaxis=dict(gridcolor="#1e222d", color="#787b86",
                    title="NQ", fixedrange=False),
        dragmode="pan", hovermode="x",
    )
    # Plotly figures contain numpy arrays — go through plotly's own JSON
    # encoder so they serialize cleanly, then re-merge with our `source` tag.
    import plotly.io as pio
    payload = json.loads(pio.to_json(fig))
    payload["source"] = source
    return jsonify(payload)


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


@app.route("/api/filter_config")
def api_filter_config():
    """Live filter configuration + ablation findings."""
    try:
        from research.filter_config import CONFIG, describe, filter_status
        return jsonify({
            "mode": CONFIG.mode,
            "summary": describe(CONFIG),
            "status": filter_status(CONFIG),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ablation")
def api_ablation():
    """Ablation study results — which filters help vs hurt."""
    p = DATA_DIR / "ablation_results.json"
    if not p.exists():
        return jsonify({"runs": []})
    try:
        return jsonify(json.loads(p.read_text()))
    except Exception:
        return jsonify({"runs": []})


@app.route("/api/strategies")
def api_strategies():
    """Detailed list of every strategy on the whitelist OR watchlist + tier."""
    p = DATA_DIR / "validation_results.json"
    if not p.exists():
        return jsonify({"strategies": []})
    try:
        data = json.loads(p.read_text())
        signals = data.get("signals") or {}
        out = []
        for name, info in signals.items():
            recommended = bool(info.get("recommended"))
            tier = info.get("tier")
            # Show on dashboard if recommended (Tier A live-traded) OR Tier B watchlist
            if not recommended and tier != "B":
                continue
            family = "5-min" if not (name.startswith("V3_") or name.startswith("WR_")
                                      or name.startswith("HF_")) else (
                "v3" if name.startswith("V3_") else
                "WR" if name.startswith("WR_") else "HF")
            side = info.get("side", "LONG" if "_LONG" in name else "SHORT")
            # Effective tier label: A = live, B = watchlist, otherwise validated
            if recommended and tier == "A":
                tier_label = "A"
            elif tier == "B":
                tier_label = "B"
            else:
                tier_label = "live"
            out.append({
                "name": name,
                "side": side,
                "family": family,
                "tier": tier_label,
                "is_live": recommended,
                "win_rate": info.get("win_rate"),
                "profit_factor": info.get("profit_factor"),
                "trades": info.get("trades"),
                "net_pnl": info.get("net_pnl"),
                "rigor_level": info.get("rigor_level", "validated"),
                "stop_pts": info.get("stop_pts"),
                "target_pts": info.get("target_pts"),
            })
        # Sort: live first (recommended), then by net P&L descending
        out.sort(key=lambda s: (not s["is_live"], -(s.get("net_pnl") or 0)))
        n_live = sum(1 for s in out if s["is_live"])
        n_watch = sum(1 for s in out if not s["is_live"])
        return jsonify({"strategies": out, "total": len(out),
                         "n_live": n_live, "n_watch": n_watch})
    except Exception as e:
        return jsonify({"strategies": [], "error": str(e)}), 500


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
