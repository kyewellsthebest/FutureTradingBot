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
from flask import Flask, jsonify, request, send_from_directory
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


@app.route("/api/health/feeds")
def api_health_feeds():
    """Live diagnostic of every price/candle feed. Useful when the chart or
    top-left price ribbon is stuck — tells you which source is failing."""
    out = {}
    # CNBC direct
    try:
        res = _fetch_cnbc()
        out["cnbc"] = {"ok": res is not None,
                          "price": (res[0] if res else None)}
    except Exception as e:
        out["cnbc"] = {"ok": False, "error": str(e)}
    # yfinance 5-min
    try:
        df = download_nq("5min", force_refresh=True).tail(1)
        if df is None or df.empty:
            out["yfinance_5min"] = {"ok": False, "error": "empty"}
        else:
            latest = df.index[-1]
            if latest.tz is None: latest = pd.Timestamp(latest).tz_localize("UTC")
            age = (pd.Timestamp.now(tz="UTC") - latest).total_seconds()
            out["yfinance_5min"] = {"ok": True,
                "last_bar": latest.isoformat(), "age_seconds": int(age),
                "close": float(df.iloc[-1]["close"])}
    except Exception as e:
        out["yfinance_5min"] = {"ok": False, "error": str(e)}
    # CNBC live-bar poller (writes live_bars.json every 30s)
    if LIVE_BARS_PATH.exists():
        try:
            bars = json.loads(LIVE_BARS_PATH.read_text())
            mtime = LIVE_BARS_PATH.stat().st_mtime
            mage = time.time() - mtime
            last_bar = bars[-1] if bars else None
            out["cnbc_poller"] = {"ok": last_bar is not None,
                                     "n_bars": len(bars),
                                     "file_age_seconds": int(mage),
                                     "last_bar": last_bar}
        except Exception as e:
            out["cnbc_poller"] = {"ok": False, "error": str(e)}
    else:
        out["cnbc_poller"] = {"ok": False, "error": "live_bars.json not found"}
    # Bot's PriceMonitor snapshot (via dashboard_data.json)
    state = persistence.load_dashboard()
    out["bot_monitor"] = {
        "price": state.get("price"),
        "ts": state.get("price_ts"),
        "error": state.get("monitor_error"),
        "cycle": state.get("cycle"),
        "as_of": state.get("as_of"),
    }
    return jsonify(out)


def _enrich_price_fallback(state: dict) -> dict:
    """If the bot's snapshot price is missing or stale, replace it with a
    direct CNBC fetch (or yfinance, or the CNBC ledger). This keeps the
    dashboard ribbon populated even when the bot's PriceMonitor chain is
    failing — common on cloud hosts (Railway, etc.) where one or more
    sources get IP-blocked."""
    price = state.get("price")
    ts = state.get("price_ts")
    stale = False
    if ts:
        try:
            ts_dt = pd.Timestamp(ts)
            if ts_dt.tz is None:
                ts_dt = ts_dt.tz_localize("UTC")
            age = (pd.Timestamp.now(tz="UTC") - ts_dt).total_seconds()
            if age > 60:
                stale = True
        except Exception:
            stale = True
    if price is not None and not stale:
        return state
    # Try CNBC direct
    try:
        res = _fetch_cnbc()
        if res is not None:
            state["price"] = res[0]
            state["price_ts"] = datetime.now(timezone.utc).isoformat()
            state["price_source"] = "cnbc_direct"
            return state
    except Exception:
        pass
    # yfinance — the chart proves this works on Railway even when CNBC is blocked
    try:
        df = download_nq("5min").tail(1)
        if df is not None and not df.empty:
            last = df.iloc[-1]
            ts_idx = df.index[-1]
            if hasattr(ts_idx, "tz_localize") and ts_idx.tz is None:
                ts_idx = pd.Timestamp(ts_idx).tz_localize("UTC")
            state["price"] = float(last["close"])
            state["price_ts"] = pd.Timestamp(ts_idx).isoformat()
            state["price_source"] = "yfinance"
            return state
    except Exception:
        pass
    # Fall back to last bar in CNBC ledger
    if LIVE_BARS_PATH.exists():
        try:
            bars = json.loads(LIVE_BARS_PATH.read_text())
            if bars:
                state["price"] = bars[-1].get("close")
                state["price_ts"] = bars[-1].get("ts")
                state["price_source"] = "cnbc_ledger"
        except Exception:
            pass
    return state


@app.route("/api/data")
def api_data():
    state = persistence.load_dashboard()
    state = _enrich_price_fallback(state)
    return jsonify(state)


@app.route("/api/price")
def api_price():
    """Live price. Falls back to a direct CNBC fetch if the bot's snapshot
    is empty or older than 60s — keeps the dashboard's top-left price
    populated even if the bot's PriceMonitor chain is failing."""
    state = persistence.load_dashboard()
    price = state.get("price")
    ts = state.get("price_ts")
    err = state.get("monitor_error")

    # Decide if we trust the bot's snapshot
    stale = False
    if ts:
        try:
            ts_dt = pd.Timestamp(ts)
            if ts_dt.tz is None:
                ts_dt = ts_dt.tz_localize("UTC")
            age = (pd.Timestamp.now(tz="UTC") - ts_dt).total_seconds()
            if age > 60:
                stale = True
        except Exception:
            stale = True

    if price is None or stale:
        # Try CNBC directly from the Flask process — independent of the bot
        try:
            res = _fetch_cnbc()
            if res is not None:
                live_px, _, _ = res
                live_ts = datetime.now(timezone.utc).isoformat()
                return jsonify({
                    "price": live_px, "ts": live_ts,
                    "monitor_error": err,
                    "source": "cnbc_direct",
                })
        except Exception as e:
            logger.warning(f"/api/price CNBC fallback failed: {e}")
        # yfinance — chart already proves this works in production
        try:
            df = download_nq("5min").tail(1)
            if df is not None and not df.empty:
                last = df.iloc[-1]
                ts_idx = df.index[-1]
                if hasattr(ts_idx, "tz_localize") and ts_idx.tz is None:
                    ts_idx = pd.Timestamp(ts_idx).tz_localize("UTC")
                return jsonify({
                    "price": float(last["close"]),
                    "ts": pd.Timestamp(ts_idx).isoformat(),
                    "monitor_error": err,
                    "source": "yfinance",
                })
        except Exception as e:
            logger.warning(f"/api/price yfinance fallback failed: {e}")
        # Last-resort: pull from CNBC live ledger if the poller is writing
        if LIVE_BARS_PATH.exists():
            try:
                bars = json.loads(LIVE_BARS_PATH.read_text())
                if bars:
                    last_bar = bars[-1]
                    return jsonify({
                        "price": last_bar.get("close"),
                        "ts": last_bar.get("ts"),
                        "monitor_error": err,
                        "source": "cnbc_ledger",
                    })
            except Exception:
                pass

    return jsonify({
        "price": price, "ts": ts, "monitor_error": err,
        "source": "bot",
    })


@app.route("/api/candles")
def api_candles():
    """NQ=F 5-min bars for the lightweight-charts chart.

    Strategy: try fresh yfinance first. If yfinance returns data that's
    more than 30 min stale (common — yfinance often stops updating NQ=F
    intraday), aggressively merge the CNBC live-bar ledger to bridge the
    gap. If yfinance fails entirely, fall back to the CNBC ledger alone.
    """
    df = None
    yf_age_min = None
    try:
        # Force fresh — yfinance internal cache can hold stale frames
        df = download_nq("5min", force_refresh=True).tail(500)
        if df is not None and not df.empty:
            latest = df.index[-1]
            if latest.tz is None:
                latest = pd.Timestamp(latest).tz_localize("UTC")
            yf_age_min = (pd.Timestamp.now(tz="UTC") - latest).total_seconds() / 60
    except Exception as e:
        logger.warning(f"candles fetch failed: {e}")
        try:
            df = download_nq("5min").tail(500)
        except Exception:
            df = None

    # Build live-bar frame from the CNBC ledger
    live_df = None
    if LIVE_BARS_PATH.exists():
        try:
            live = json.loads(LIVE_BARS_PATH.read_text())
            if live:
                rows = []
                for b in live[-300:]:
                    try:
                        ts = pd.Timestamp(b["ts"])
                        if ts.tz is None: ts = ts.tz_localize("UTC")
                        rows.append((ts, float(b["open"]), float(b["high"]),
                                       float(b["low"]), float(b["close"]),
                                       float(b.get("volume", 0))))
                    except Exception:
                        continue
                if rows:
                    live_df = pd.DataFrame(rows,
                        columns=["ts","open","high","low","close","volume"]
                    ).set_index("ts").sort_index()
        except Exception as e:
            logger.warning(f"live_bars parse failed: {e}")

    # If yfinance is missing entirely, use CNBC ledger as the WHOLE chart
    if (df is None or df.empty) and live_df is not None and not live_df.empty:
        df = live_df.copy()
    # If yfinance is stale (>30min) but CNBC ledger has fresher bars, merge.
    # CNBC ledger overwrites yfinance for any overlapping timestamps.
    elif df is not None and not df.empty and live_df is not None and not live_df.empty:
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        # Append live bars; drop duplicates keeping the live (fresher) row
        df = pd.concat([df, live_df]).sort_index()
        df = df[~df.index.duplicated(keep="last")]

    if df is None or df.empty:
        return jsonify([])

    # FINAL freshness layer: if the latest bar in df is more than ~5min old
    # (i.e. yfinance is stale and the CNBC poller didn't catch up), fetch
    # the current price directly from CNBC and synthesize/extend the most
    # recent 5-min bin so the chart doesn't display "stale 58 min" while
    # the price ticker happily updates from CNBC.
    try:
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        latest_bar_ts = df.index[-1]
        age_s = (pd.Timestamp.now(tz="UTC") - latest_bar_ts).total_seconds()
        if age_s > 300:
            res = _fetch_cnbc()
            if res is not None:
                live_px, _, _ = res
                now_utc = pd.Timestamp.now(tz="UTC")
                # Round down to the nearest 5-min bar boundary
                bin_min = (now_utc.minute // 5) * 5
                bin_ts = now_utc.replace(minute=bin_min, second=0, microsecond=0)
                if bin_ts in df.index:
                    # Extend the existing bar
                    df.loc[bin_ts, "high"]  = max(float(df.loc[bin_ts, "high"]), live_px)
                    df.loc[bin_ts, "low"]   = min(float(df.loc[bin_ts, "low"]),  live_px)
                    df.loc[bin_ts, "close"] = live_px
                else:
                    # Create a synthetic bar at this 5-min boundary
                    new_row = pd.DataFrame(
                        [[live_px, live_px, live_px, live_px, 0.0]],
                        columns=["open","high","low","close","volume"],
                        index=[bin_ts])
                    df = pd.concat([df, new_row]).sort_index()
                    df = df[~df.index.duplicated(keep="last")]
    except Exception as e:
        logger.warning(f"candles CNBC live-bar synthesize failed: {e}")
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
    # MNQ = $2/pt per contract. The legacy state.dollars_per_point is
    # 60 (a scaled "30 MNQ default size" constant from the old V3 stack)
    # — using it here would 30x the displayed P&L. Hardcode MNQ tick value.
    dpp = 2.0
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


@app.route("/api/strategy/<path:name>")
def api_strategy_detail(name):
    """Plain-English description + backtest stats for one strategy."""
    from research.strategy_descriptions import describe
    info = describe(name)
    # Attach the backtest stats from validation_results.json so the modal
    # has everything it needs in one fetch.
    p = DATA_DIR / "validation_results.json"
    if p.exists():
        try:
            data = json.loads(p.read_text())
            sig = (data.get("signals") or {}).get(name)
            if sig:
                info["stats"] = {
                    "win_rate":     sig.get("win_rate"),
                    "profit_factor": sig.get("profit_factor"),
                    "trades":       sig.get("trades"),
                    "net_pnl":      sig.get("net_pnl"),
                    "stop_pts":     sig.get("stop_pts"),
                    "target_pts":   sig.get("target_pts"),
                    "tier":         sig.get("tier"),
                    "is_live":      bool(sig.get("recommended")),
                    "rigor_level":  sig.get("rigor_level"),
                }
        except Exception:
            pass
    return jsonify(info)


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


@app.route("/api/admin/roll_day", methods=["GET", "POST"])
def api_admin_roll_day():
    """Force the lucid_state.json today_pnl into cum_pnl_closed_days and
    reset today_date to current NY date. Idempotent — safe to hit any time.
    Workaround when the in-process day-roll didn't fire."""
    import json as _json
    from datetime import datetime, timezone
    import pandas as _pd
    from research.signal_filters import NY_TZ
    state_path = DATA_DIR / "lucid_state.json"
    if not state_path.exists():
        return jsonify({"ok": False, "error": "lucid_state.json missing"}), 404
    try:
        s = _json.loads(state_path.read_text())
    except Exception as e:
        return jsonify({"ok": False, "error": f"parse: {e}"}), 500
    ny_today = _pd.Timestamp(datetime.now(timezone.utc)).tz_convert(NY_TZ).date().isoformat()
    before = {
        "today_date": s.get("today_date"),
        "today_pnl": s.get("today_pnl", 0.0),
        "cum_pnl_closed_days": s.get("cum_pnl_closed_days", 0.0),
        "n_trading_days": s.get("n_trading_days", 0),
    }
    if before["today_date"] == ny_today:
        return jsonify({"ok": True, "msg": "already on today's NY date — no roll needed",
                          "before": before, "ny_today": ny_today})
    s["cum_pnl_closed_days"] = float(before["cum_pnl_closed_days"]) + float(before["today_pnl"])
    s["today_pnl"] = 0.0
    s["today_date"] = ny_today
    s["n_trading_days"] = int(before["n_trading_days"]) + 1
    state_path.write_text(_json.dumps(s, indent=2, default=str))
    return jsonify({"ok": True, "msg": "rolled",
                      "before": before,
                      "after": {"today_date": s["today_date"],
                                  "today_pnl": s["today_pnl"],
                                  "cum_pnl_closed_days": s["cum_pnl_closed_days"],
                                  "n_trading_days": s["n_trading_days"]}})


# ---------------------------------------------------------------------------
# v11 endpoints (NQ-ES stat-arb)
# ---------------------------------------------------------------------------
@app.route("/api/v11/brain")
def api_v11_brain():
    """Live engine state: Z-scores, ATR, NY-time bucket, closest-to-trigger,
    recent fires, counters."""
    state = persistence.load_dashboard()
    v11 = state.get("v11") or {}
    return jsonify({
        "as_of": state.get("as_of"),
        "cycle": state.get("cycle"),
        "bot_version": state.get("bot_version", "unknown"),
        "summary": v11.get("summary") or {},
        "z_scores": v11.get("z_scores") or {},
        "atr": v11.get("atr"),
        "ny_bucket": v11.get("ny_bucket"),
        "last_bar_ts": v11.get("last_bar_ts"),
        "closest_to_trigger": v11.get("closest_to_trigger") or [],
        "recent_fires": v11.get("recent_fires") or [],
        "bars_processed": v11.get("bars_processed", 0),
        "signals_fired": v11.get("signals_fired", 0),
        "signals_blocked": v11.get("signals_blocked", 0),
        "base_size": v11.get("base_size", 25),
        "in_trade": bool((state.get("account") or {}).get("open_position")),
        "lucid": state.get("lucid_account") or {},
    })


@app.route("/api/v11/strategies")
def api_v11_strategies():
    """Strategies the bot is actually trading (the post-stress-test
    deployment set, default). Append ?all=1 for the full v11+v12 universe."""
    show_all = bool(request.args.get("all"))
    deployed_names = None
    if not show_all:
        dep_path = DATA_DIR / "deployed_strategies.json"
        if dep_path.exists():
            try:
                deployed_names = set(json.loads(dep_path.read_text()).get("names", []))
            except Exception:
                deployed_names = None
    rows = []
    TEST_YEARS = 2.33
    seen = set()
    for fname, source in [("mined_v11_patterns.json", "v11"),
                            ("mined_v12_patterns.json", "v12")]:
        p = DATA_DIR / fname
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        for s in d.get("user_passers", []):
            t = s.get("test", {})
            if t.get("pf", 0) < 1.0:
                continue
            if s["name"] in seen:
                continue
            if deployed_names is not None and s["name"] not in deployed_names:
                continue
            seen.add(s["name"])
            trig = s.get("trigger", "")
            parts = trig.split("_")
            try:
                z_window = int(parts[2])
                z_threshold = int(parts[3]) / 10.0
            except (ValueError, IndexError):
                z_window = None; z_threshold = None
            net = t.get("net", 0)
            rows.append({
                "name": s["name"],
                "source": source,
                "side": s["side"],
                "z_window": z_window,
                "z_threshold": z_threshold,
                "time_ctx": (s.get("contexts") or [None])[0],
                "stop_atr": s["stop_atr"],
                "target_atr": s["target_atr"],
                "rr": round(s["target_atr"] / s["stop_atr"], 2),
                "max_hold_min": s["max_hold_min"],
                "n_test": t.get("n", 0),
                "wr": t.get("wr", 0),
                "pf": t.get("pf", 0),
                "sharpe": t.get("sharpe", 0),
                "net_1mnq": net,
                "yearly_at_25mnq": net / TEST_YEARS * 25,
                "cpcv": s.get("cpcv_positive", 0),
            })
    rows.sort(key=lambda r: -r["sharpe"])
    return jsonify(rows)


@app.route("/api/v11/recent_fires")
def api_v11_recent_fires():
    """Just the recent_fires list for live tail (Brain tab updates)."""
    state = persistence.load_dashboard()
    v11 = state.get("v11") or {}
    return jsonify(v11.get("recent_fires") or [])


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
