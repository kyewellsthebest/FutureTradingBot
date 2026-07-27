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
from research.strategy_profiles import thesis_for

logger = logging.getLogger("dashboard")
ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"

LIVE_BARS_PATH = DATA_DIR / "live_bars.json"
SIGNAL_EVENT_TTL_SECONDS = 20 * 60

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
CORS(app)


# Multi-account routing: every API request can specify ?account=N. The
# before_request hook binds the request handler thread to that account so
# all persistence calls during the request resolve to data/account_<N>/.
# Default "1" preserves single-account behaviour.
@app.before_request
def _bind_account_from_query():
    from flask import request
    from bot.account_ctx import set_account
    set_account(request.args.get("account", "1"))


@app.route("/api/accounts")
def api_accounts():
    """List of accounts ACTIVELY configured to run (from ACCOUNTS env). We
    deliberately do NOT include orphan account_N directories from disk --
    once a config is removed, the account should disappear from the
    dropdown even if its data dir still exists."""
    import os as _os
    configured = [a.strip() for a in _os.environ.get("ACCOUNTS", "1").split(",") if a.strip()]
    return jsonify({"accounts": configured})


# --- Manual pause/resume ---------------------------------------------------
# Lets the user pause new entries on any account from the dashboard. The
# pause flag is a small JSON file in the account's data dir, read by the
# bot every tick (bot/pullback_strategy.py). Survives bot restarts. Does
# NOT close any active trade -- only blocks NEW entries.
@app.route("/api/pause_status")
def api_pause_status():
    from bot.account_ctx import get_pause_state, get_account
    return jsonify({"account": get_account(), **get_pause_state()})


@app.route("/api/pause", methods=["POST"])
def api_pause():
    from bot.account_ctx import set_paused, get_account
    payload = request.get_json(silent=True) or {}
    reason = payload.get("reason") or request.args.get("reason") or "user_manual"
    result = set_paused(True, reason=reason)
    logger.warning(f"[MANUAL PAUSE] account={get_account()} reason={reason}")
    return jsonify({"ok": True, "account": get_account(), **result})


@app.route("/api/resume", methods=["POST"])
def api_resume():
    from bot.account_ctx import set_paused, get_account
    result = set_paused(False)
    logger.warning(f"[MANUAL RESUME] account={get_account()}")
    return jsonify({"ok": True, "account": get_account(), **result})


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    # no-store: phones cached the shell page for hours and kept showing
    # UI elements that were removed several deploys earlier (2026-07-25)
    resp = send_from_directory(STATIC_DIR, "index.html")
    resp.headers["Cache-Control"] = "no-store, must-revalidate"
    return resp


@app.route("/static/<path:p>")
def static_files(p):
    return send_from_directory(STATIC_DIR, p)


@app.route("/api/health")
def api_health():
    return jsonify({"ok": True, "ts": datetime.now(timezone.utc).isoformat()})


@app.route("/api/audit")
def api_audit():
    """Trade audit log -- every TradersPost interaction with full
    request/response. Used for paper-vs-broker reconciliation.

    Query params:
      n        return last N entries (default 100, max 5000)
      ref      filter to a specific orderRef (the setup_id from open)
      kind     filter to open / target / close
      since    ISO timestamp; only entries after this time
      summary  if 1, return aggregate counts instead of rows

    The audit log is JSONL at TRADERSPOST_AUDIT_DIR/traderspost_audit.jsonl
    (defaults to data/). Each row contains: ts, kind, ref, ok, status,
    error, payload, response. Cross-reference response.brokerage_orders[]
    against your Tradovate Orders tab to find divergence."""
    import os as _os
    from pathlib import Path as _P
    args = request.args
    n = min(int(args.get("n", "100")), 5000)
    ref_filter = args.get("ref")
    kind_filter = args.get("kind")
    since = args.get("since")
    summary = args.get("summary") == "1"

    log_dir = _os.environ.get("TRADERSPOST_AUDIT_DIR",
                               "/home/user/HFTBot/data")
    log_path = _P(log_dir) / "traderspost_audit.jsonl"
    if not log_path.exists():
        return jsonify({"rows": [], "count": 0,
                        "note": "no audit log yet -- first trade will create it"})
    rows = []
    try:
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if ref_filter and r.get("ref") != ref_filter:
                    continue
                if kind_filter and r.get("kind") != kind_filter:
                    continue
                if since and r.get("ts", "") < since:
                    continue
                rows.append(r)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    rows = rows[-n:]  # most recent N after filter
    if summary:
        by_kind = {}
        by_status = {"ok": 0, "fail": 0}
        for r in rows:
            k = r.get("kind", "?")
            by_kind[k] = by_kind.get(k, 0) + 1
            by_status["ok" if r.get("ok") else "fail"] += 1
        return jsonify({
            "total_rows_scanned": len(rows),
            "by_kind": by_kind,
            "by_status": by_status,
            "earliest_ts": rows[0]["ts"] if rows else None,
            "latest_ts": rows[-1]["ts"] if rows else None,
        })
    return jsonify({"count": len(rows), "rows": rows})


@app.route("/api/reconcile/<ref>")
def api_reconcile(ref):
    """Per-trade reconciliation. Given a setup_id (orderRef), return:
      - what the bot intended (from paper-account trade record)
      - every TradersPost interaction for that ref (open, target, close)
      - what TradersPost said in response to each
    Lets you compare side-by-side without grepping logs.

    Use case: you see a -$295 trade in Tradovate, you find the orderRef
    from the dashboard's recent trades, you hit /api/reconcile/{ref} and
    see the FULL story -- what we sent, what came back, what the bracket
    was supposed to do. No more inference from cash logs."""
    import os as _os
    from pathlib import Path as _P
    log_dir = _os.environ.get("TRADERSPOST_AUDIT_DIR",
                               "/home/user/HFTBot/data")
    log_path = _P(log_dir) / "traderspost_audit.jsonl"
    interactions = []
    if log_path.exists():
        try:
            with open(log_path) as f:
                for line in f:
                    try:
                        r = json.loads(line.strip())
                    except Exception:
                        continue
                    if r.get("ref") == ref or \
                       r.get("ref") == ref + "-target" or \
                       r.get("ref") == ref + "-exit":
                        interactions.append(r)
        except Exception:
            pass
    # Try to find the bot's intended trade record
    paper_record = None
    try:
        state = persistence.load_dashboard()
        for t in state.get("recent_trades", []):
            if t.get("setup_ref") == ref or t.get("orderRef") == ref:
                paper_record = t
                break
    except Exception:
        pass
    return jsonify({
        "ref": ref,
        "paper_record": paper_record,
        "interactions": interactions,
        "summary": {
            "n_interactions": len(interactions),
            "kinds": list({i.get("kind") for i in interactions}),
            "any_failed": any(not i.get("ok") for i in interactions),
        },
    })


@app.route("/api/tradovate_account")
def api_tradovate_account():
    """Live account snapshot from Tradovate: balance, equity, daily P&L.
    Used to populate the Performance tab and the topbar balance."""
    try:
        from bot.tradovate_client import get_session
    except Exception as e:
        return jsonify({"error": f"client import failed: {e!r}"}), 500
    sess = get_session()
    if not sess.is_configured:
        return jsonify({"configured": False})
    acct_id = sess.get_account_id()
    if acct_id is None:
        return jsonify({"configured": True, "error": "no_account_id"})
    # /cashBalance/getCashBalanceSnapshot gives current cash position
    status, snap = sess._rest("POST", "/cashBalance/getCashBalanceSnapshot",
                                body={"accountId": int(acct_id)})
    # /accountRiskStatus/list gives liquidation/risk state
    rs_status, rs_data = sess._rest("GET", "/accountRiskStatus/list")
    # /account/item gives account metadata
    a_status, acct_data = sess._rest("GET", "/account/item",
                                       params={"id": int(acct_id)})
    return jsonify({
        "configured": True,
        "account_id": acct_id,
        "account": acct_data if a_status == 200 else None,
        "cash_snapshot": snap if status == 200 else None,
        "risk_status": rs_data if rs_status == 200 else None,
    })


@app.route("/api/tradovate_position")
def api_tradovate_position():
    """Current open position(s) on the Tradovate account. Used to
    populate the Live tab's Active Trade card."""
    try:
        from bot.tradovate_client import get_session
    except Exception as e:
        return jsonify({"error": f"client import failed: {e!r}"}), 500
    sess = get_session()
    if not sess.is_configured:
        return jsonify({"configured": False})
    acct_id = sess.get_account_id()
    if acct_id is None:
        return jsonify({"configured": True, "error": "no_account_id"})
    # /position/list returns all positions for the user; filter by account
    status, positions = sess._rest("GET", "/position/list")
    if status != 200 or not isinstance(positions, list):
        return jsonify({
            "configured": True,
            "account_id": acct_id,
            "positions": [],
            "error": f"http_{status}",
        })
    # Tradovate positions list ALL positions across all accounts; filter
    # to the active account and to those with non-zero netPos.
    filtered = []
    for p in positions:
        if not isinstance(p, dict):
            continue
        if p.get("accountId") != acct_id:
            continue
        if not p.get("netPos"):  # 0 or None
            continue
        filtered.append(p)
    return jsonify({
        "configured": True,
        "account_id": acct_id,
        "positions": filtered,
    })


# ============================================================================
# BROKER-BACKED ENDPOINTS
# These pull EVERYTHING from Tradovate's REST/WS, not paper.
# Used by the Trades + Performance + Live tabs when the user wants
# to see broker reality. Each returns rows in the dashboard's existing
# "paper trade" shape so the frontend can render them identically.
# Reference: Tradovate API docs entity model -- FillPair (round-trip
# closed trades), Position (current open), CashBalance (realized PnL).
# ============================================================================


def _broker_pnl_pts(buy_px: float, sell_px: float) -> float:
    """Points P&L for a round trip. Buyer side is always +/- (sell-buy)
    in market terms; whether the trader is LONG or SHORT is encoded in
    which fill came first (LONG = buy first, SHORT = sell first)."""
    return float(sell_px) - float(buy_px)


def _broker_pnl_usd(pts: float, qty: int, side: str,
                     dollars_per_point: float = 2.0) -> float:
    """Convert points to USD for MNQ ($2/pt). Sign flips for SHORT."""
    sign = 1.0 if (side or "").upper() == "LONG" else -1.0
    return float(pts) * float(qty) * dollars_per_point * sign


# ---- multi-instrument contract math (SNAP-BACK BASKET, 2026-07-24) -------
# The account now trades 7 products at once, so every $-conversion must be
# per-contract. Root = longest symbol prefix match ("MESU6" -> "MES").
CONTRACT_PV = {"MNQ": 2.0, "MES": 5.0, "M2K": 5.0, "MYM": 0.5,
               "MGC": 10.0, "MCL": 100.0, "ZB": 1000.0, "NQ": 20.0,
               "ES": 50.0, "RTY": 50.0, "YM": 5.0, "GC": 100.0, "CL": 1000.0}
# All-in round-trip costs CALIBRATED to what the demo actually charged
# on 2026-07-24: gross fills +\$380.75 vs cash -\$79.13 => \$459.88 fees
# over 229 trades. Tradovate demo charges REAL commissions+exchange fees.
CONTRACT_COMM_RT = {"MNQ": 1.80, "MES": 1.80, "M2K": 1.80, "MYM": 1.80,
                    "MGC": 1.95, "MCL": 1.95, "ZB": 4.50}


def _root_of(symbol: str) -> str:
    s = str(symbol or "").upper()
    best = ""
    for r in CONTRACT_PV:
        if s.startswith(r) and len(r) > len(best):
            best = r
    return best or "MNQ"


_contract_name_cache: dict = {}


def _contract_symbol(sess, cid) -> str:
    """contractId -> contract name ("MESU6"), cached. Empty string if
    unresolvable (caller should treat as legacy MNQ)."""
    if cid is None:
        return ""
    cid = int(cid)
    if cid in _contract_name_cache:
        return _contract_name_cache[cid]
    name = ""
    try:
        c_status, contract = sess._rest("GET", "/contract/item",
                                        params={"id": cid})
        if c_status == 200 and isinstance(contract, dict):
            name = contract.get("name") or ""
    except Exception:
        name = ""
    if name:
        _contract_name_cache[cid] = name
    return name


def _collect_broker_trades(sess, acct_id: int,
                            limit: int = 1000) -> list:
    """Build the paper-shape trade list from broker data.

    PRIMARY: walk fills chronologically and pair them up by position
    accumulation. When net position returns to zero, emit a completed
    trade. This catches EVERY trade including ones whose bracket
    structure was disrupted by InvalidPrice rejections (the linkage-
    based approach misses those).

    Also persists each emitted trade to disk so future trades survive
    Tradovate's session-bounded REST history.
    """
    # Fills with timestamps + orderIds
    f_status, fills = sess._rest("GET", "/fill/list")
    if f_status != 200 or not isinstance(fills, list):
        fills = []
    # ARCHIVE UNION (2026-07-25): Tradovate's demo /fill/list is
    # session-bounded — the morning after, it returns 0 rows and the
    # whole Trades tab vanished. The user-WS fill archive on disk holds
    # every fill as it streamed (7-day retention); union it in, deduped
    # by fill id, so trade history survives Tradovate's wipes.
    try:
        from datetime import datetime as _adt, timedelta as _atd, timezone as _atz
        from bot.account_ctx import data_dir as _add
        seen_ids = {f.get("id") for f in fills if isinstance(f, dict)}
        _base = _add()
        n_arch = 0
        for dback in range(8):
            day = (_adt.now(_atz.utc) - _atd(days=dback)).strftime("%Y%m%d")
            fp = _base / f"fill_archive_{day}.jsonl"
            if not fp.exists():
                continue
            for line in fp.read_text().splitlines():
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                fid = r.get("id")
                if fid is None or fid in seen_ids or r.get("price") is None:
                    continue
                seen_ids.add(fid)
                fills.append(r)
                n_arch += 1
        if n_arch:
            logger.info(f"fill-archive union added {n_arch} fills REST no "
                        f"longer returns")
    except Exception as e:
        logger.debug(f"fill archive union: {e!r}")
    # Orders (used for exit_reason inference)
    o_status, orders = sess._rest("GET", "/order/list")
    order_by_id = {}
    if o_status == 200 and isinstance(orders, list):
        for o in orders:
            if isinstance(o, dict) and o.get("id") is not None:
                order_by_id[int(o["id"])] = o

    # Sort fills chronologically
    def _parse_ts(ts):
        try:
            t = pd.Timestamp(ts)
            if t.tz is None:
                t = t.tz_localize("UTC")
            else:
                t = t.tz_convert("UTC")
            return t
        except Exception:
            return None

    fills_clean = []
    for f in fills:
        if not isinstance(f, dict):
            continue
        ts = _parse_ts(f.get("timestamp"))
        if ts is None:
            continue
        fills_clean.append({
            "ts": ts,
            "action": f.get("action"),
            "qty": abs(int(f.get("qty") or 0)),
            "price": float(f.get("price") or 0),
            "order_id": f.get("orderId"),
            "fill_id": f.get("id"),
            "cid": f.get("contractId"),
            "raw": f,
        })
    # DETERMINISTIC TIE-BREAK: when two fills have the same millisecond
    # timestamp (Tradovate matching engine puts both legs of a position
    # flip at the same ms), sort by (ts, order_id, fill_id). Lower
    # order_id = created first, so it should be processed first.
    #
    # Bug observed: user saw "08:31:07 LONG 30072.75 -> 30072.50 = -$1.24"
    # which is mathematically a LONG losing 0.25pt. But the actual events
    # were Sell @ 30072.5 (orderId 696, opens SHORT) followed by Buy @
    # 30072.75 (orderId 704, closes SHORT). Same ts (.653). Stable
    # Python sort preserved JSON order, which had Buy before Sell ->
    # walker opened LONG @ 30072.75 instead of SHORT @ 30072.5 = wrong
    # side, swapped entry/exit. Fix: sort by orderId as tie-break.
    fills_clean.sort(key=lambda x: (
        x["ts"],
        x["order_id"] if x["order_id"] is not None else 0,
        x["fill_id"] if x["fill_id"] is not None else 0,
    ))

    # Walk: track signed position PER CONTRACT (the basket trades 7
    # products on one account — netting fills across contracts would pair
    # a gold buy with an oil sell). Open new cycle when that contract's
    # position was 0; emit a trade when it returns to 0 (or flips).
    rows = []

    def _exit_reason_for_order(oid):
        o = order_by_id.get(int(oid)) if oid is not None else None
        if not isinstance(o, dict):
            return "broker"
        otype = (o.get("orderType") or "").lower()
        if "stop" in otype:
            return "stop"
        if "limit" in otype:
            return "target"
        if "market" in otype:
            return "manual"
        return "broker"

    class _Cyc:
        __slots__ = ("pos", "tot", "qty", "ts", "side", "oid")
        def __init__(self):
            self.pos = 0; self.tot = 0.0; self.qty = 0
            self.ts = None; self.side = None; self.oid = None

    cycles: dict = {}          # contractId -> _Cyc

    # COMMISSIONS ARE REAL ON DEMO (proven 2026-07-25: cash moved exactly
    # gross fills minus \$2.01/trade). Rows subtract the calibrated
    # all-in cost so Total P&L tracks the actual account balance.

    def _emit_trade(cy, exit_fill, close_qty, symbol, pv, comm_rt):
        if cy.qty <= 0:
            return None
        entry_avg = cy.tot / cy.qty
        exit_px = exit_fill["price"]
        if cy.side == "LONG":
            pts_diff = exit_px - entry_avg
        else:
            pts_diff = entry_avg - exit_px
        comm_eff = comm_rt
        pnl_usd = (pts_diff * close_qty * pv) - (comm_eff * close_qty)
        ent_order = order_by_id.get(int(cy.oid)) if cy.oid else None
        setup_ref = ent_order.get("text") if isinstance(ent_order, dict) else None
        return {
            "ts": exit_fill["ts"].isoformat(),
            "entry_ts": cy.ts.isoformat(),
            "entry_time": cy.ts.isoformat(),
            "exit_time": exit_fill["ts"].isoformat(),
            "side": cy.side,
            "qty": close_qty,
            "n_mnq": close_qty,
            "symbol": symbol or "MNQ",
            "instr": _root_of(symbol) if symbol else "MNQ",
            "entry_px": round(entry_avg, 4),
            "exit_px": round(exit_px, 4),
            "pnl_usd": round(pnl_usd, 2),
            "pnl": round(pnl_usd, 2),
            "pnl_pts": round(pts_diff, 4),
            "exit_reason": _exit_reason_for_order(exit_fill["order_id"]),
            "hold_s": (exit_fill["ts"] - cy.ts).total_seconds(),
            "commission": round(comm_eff * close_qty, 2),
            "commission_est_live": round(comm_rt * close_qty, 2),
            "source": "broker_fill_walk",
            "entry_order_id": cy.oid,
            "exit_order_id": exit_fill["order_id"],
            "setup_ref": setup_ref,
        }

    for f in fills_clean:
        action = (f["action"] or "").lower()
        signed = f["qty"] if action == "buy" else -f["qty"]
        cy = cycles.setdefault(f["cid"], _Cyc())
        symbol = _contract_symbol(sess, f["cid"])
        root = _root_of(symbol) if symbol else "MNQ"
        pv = CONTRACT_PV.get(root, 2.0)
        comm_rt = CONTRACT_COMM_RT.get(
            root, float(os.environ.get("BROKER_COMM_PER_RT", "0.74")))
        if cy.pos == 0:
            # Starting a new position on this contract
            cy.pos = signed
            cy.tot = f["price"] * f["qty"]
            cy.qty = f["qty"]
            cy.ts = f["ts"]
            cy.side = "LONG" if signed > 0 else "SHORT"
            cy.oid = f["order_id"]
            continue
        same_dir = (cy.pos > 0 and signed > 0) or (cy.pos < 0 and signed < 0)
        if same_dir:
            cy.tot += f["price"] * f["qty"]
            cy.qty += f["qty"]
            cy.pos += signed
            continue
        # Closing or reducing
        close_qty = min(f["qty"], abs(cy.pos))
        emitted = _emit_trade(cy, f, close_qty, symbol, pv, comm_rt)
        if emitted:
            rows.append(emitted)
        # Reduce remaining entries pro-rata (avg price unchanged)
        if cy.qty > 0:
            remaining_q = max(0, cy.qty - close_qty)
            cy.tot *= remaining_q / cy.qty
            cy.qty = remaining_q
        cy.pos += signed
        if cy.pos == 0:
            cy.tot = 0.0; cy.qty = 0; cy.ts = None
            cy.side = None; cy.oid = None
        elif (cy.pos > 0) != (cy.side == "LONG"):
            # Position flipped in one fill
            cy.tot = f["price"] * abs(cy.pos)
            cy.qty = abs(cy.pos)
            cy.ts = f["ts"]
            cy.side = "LONG" if cy.pos > 0 else "SHORT"
            cy.oid = f["order_id"]
    rows.sort(key=lambda r: r.get("exit_time") or "")

    # Persist this cycle's trades to disk for cross-session history.
    try:
        _persist_broker_trades(acct_id, rows)
    except Exception as e:
        logger.debug(f"persist_broker_trades: {e!r}")

    # Merge persisted history (older sessions) with the live rows.
    try:
        rows = _merge_persisted_broker_trades(acct_id, rows, limit=limit)
    except Exception as e:
        logger.debug(f"merge_persisted_broker_trades: {e!r}")

    # AUDIT-LOG FALLBACK. Tradovate's /fill/list returns 0 rows for the
    # demo account between sessions even when trades clearly happened
    # (bundle confirmed bot fired 75 placeoso + 4 liquidateposition with
    # HTTP 200). When we have no live fills AND no persisted history,
    # synthesize trade rows from the bot's own audit_log.jsonl so the
    # dashboard's Trades tab and Performance graphs show SOMETHING
    # instead of the user-confusing "No broker fills available via
    # REST" banner. Pairs placeoso (open) with the next liquidateposition
    # OR bracket-fill of the same setup_ref.
    if not rows:
        try:
            rows = _audit_log_synth_trades(acct_id, limit=limit)
        except Exception as e:
            logger.debug(f"audit_log_synth_trades: {e!r}")

    # HIDE PRE-BASKET HISTORY (user order 2026-07-24): the ~141 trades
    # from the retired FADESZ era (<= 17 Jul 2026) stay in Tradovate's
    # records and on disk, but every dashboard surface built from this
    # walk (Trades tab, stats, equity, daily, bundle) starts fresh from
    # the cutoff. Override with BROKER_TRADES_HIDE_BEFORE=ISO or "" to
    # show everything again.
    cutoff = os.environ.get("BROKER_TRADES_HIDE_BEFORE", "2026-07-18")
    if cutoff:
        rows = [r for r in rows
                if str(r.get("exit_time") or r.get("ts") or "") >= cutoff]

    rows.sort(key=lambda r: r.get("ts") or "")
    return rows[-limit:]


def _audit_log_synth_trades(acct_id, limit=1000):
    """Build a paper-shape trade list from the bot's audit log when
    Tradovate REST returns nothing. The bot already records every
    placeoso (open) and liquidateposition (close) in audit_log.jsonl,
    keyed by setup_ref. Pair them up and emit completed trade rows.

    Returns list of dicts shaped like paper_trades rows so the existing
    dashboard render path works unchanged.
    """
    try:
        from bot.tradovate_orders import get_audit_log
    except Exception:
        return []
    audit = get_audit_log()
    if not audit:
        return []

    # Pair placeoso (open) with next liquidateposition for same setup_ref.
    opens = {}
    rows = []
    for e in audit:
        kind = e.get("kind")
        ref = e.get("setup_ref")
        if not ref:
            continue
        if kind == "placeoso" and e.get("parsed_ok"):
            body = e.get("request_body") or {}
            opens[ref] = {
                "ts": e.get("ts"),
                "side": "LONG" if body.get("action") == "Buy" else "SHORT",
                "qty": int(body.get("orderQty") or 1),
                "entry_px": float(body.get("price") or e.get("entry_price") or 0),
                "stop_px": float(((body.get("bracket1") or {}).get("stopPrice")) or 0),
                "target_px": float(((body.get("bracket2") or {}).get("price")) or 0),
            }
        elif kind == "liquidateposition" and e.get("parsed_ok"):
            # match against an earlier open with the same base ref
            # (liquidate setup_ref includes "-flat" suffix sometimes)
            base = ref.replace("-flat", "")
            op = opens.pop(base, None) or opens.pop(ref, None)
            if op is None:
                continue
            # Approximate exit price: liquidate's response doesn't
            # always have a fill price -- use the strategy's target or
            # stop based on which side hit, fall back to midpoint.
            # Best we can do without a real fill report.
            ts_open = float(op["ts"])
            ts_close = float(e.get("ts") or ts_open)
            hold_s = max(0.0, ts_close - ts_open)
            # Without a clear exit price from liquidate, mark exit_reason
            # generic. The dashboard will show this as broker close.
            rows.append({
                "ts": (pd.to_datetime(ts_close, unit="s", utc=True)
                       .isoformat()),
                "entry_time": (pd.to_datetime(ts_open, unit="s", utc=True)
                               .isoformat()),
                "exit_time": (pd.to_datetime(ts_close, unit="s", utc=True)
                              .isoformat()),
                "side": op["side"],
                "qty": op["qty"],
                "n_mnq": op["qty"],
                "entry_px": op["entry_px"],
                "exit_px": op["target_px"] or op["entry_px"],
                "stop_px": op["stop_px"],
                "target_px": op["target_px"],
                "exit_reason": "liquidate",
                "pnl_pts": 0.0,
                "pnl_usd": 0.0,
                "hold_s": hold_s,
                "_source": "audit_log_synth",
            })
    if rows:
        logger.info(f"[broker fallback] synthesised {len(rows)} trade row(s) "
                    f"from audit_log (REST returned empty)")
    return rows[-limit:]


def _broker_history_path(acct_id):
    """JSONL trade-history cache in the account data dir.

    v2 (2026-07-25): versioned filename. The v1 file held rows priced by
    OLDER walker math (single-stream pairing, baked-in commissions) and
    the merge preferred persisted rows — so every pricing fix was
    silently overridden by stale disk rows, and re-pairings of the same
    fills survived dedup as DOUBLE-counted trades (user-visible: stats
    -\\$211 vs broker cash -\\$79). New filename = clean rebuild from
    /fill/list with current math; the v1 file stays on disk untouched."""
    from bot.account_ctx import data_dir as _dd
    p = _dd() / f"broker_trades_v2_{acct_id}.jsonl"
    return p


@app.route("/api/broker/rebuild_history", methods=["POST", "GET"])
def api_broker_rebuild_history():
    """Wipe the persisted broker trade history and rebuild from the
    current Tradovate session. Used after a walker logic fix invalidates
    previously-persisted (wrong) data."""
    try:
        from bot.tradovate_client import get_session
        sess = get_session()
        if not sess.is_configured:
            return jsonify({"error": "not_configured"}), 400
        acct_id = sess.get_account_id()
        if acct_id is None:
            return jsonify({"error": "no_account_id"}), 400
        p = _broker_history_path(acct_id)
        existed = p.exists()
        if existed:
            p.unlink()
        # Rebuild from current Tradovate data
        rows = _collect_broker_trades(sess, acct_id, limit=10_000)
        return jsonify({
            "ok": True,
            "wiped_existing": existed,
            "rebuilt_path": str(p),
            "n_rebuilt": len(rows),
        })
    except Exception as e:
        return jsonify({"error": repr(e)}), 500


def _persist_broker_trades(acct_id, rows):
    """Append any new broker trades to the persistent JSONL file.
    Dedup by exit_order_id + exit_time so repeated polls don't double-write.
    """
    if not rows:
        return
    p = _broker_history_path(acct_id)
    existing_keys = set()
    if p.exists():
        try:
            with p.open("r") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                        k = (r.get("exit_order_id"), r.get("exit_time"))
                        existing_keys.add(k)
                    except Exception:
                        pass
        except Exception:
            pass
    appended = 0
    with p.open("a") as f:
        for r in rows:
            k = (r.get("exit_order_id"), r.get("exit_time"))
            if k in existing_keys:
                continue
            f.write(json.dumps(r) + "\n")
            existing_keys.add(k)
            appended += 1
    if appended:
        logger.info(f"persisted {appended} broker trade(s) to {p}")


@app.route("/api/broker/reset_history", methods=["POST", "GET"])
def api_broker_reset_history():
    """Wipe the persistent broker trade history JSONL. Use after
    fixing bugs to see clean post-fix performance without the
    polluted historical data dragging averages."""
    try:
        from bot.tradovate_client import get_session
        sess = get_session()
        if not sess.is_configured:
            return jsonify({"error": "not_configured"}), 400
        acct_id = sess.get_account_id()
        if acct_id is None:
            return jsonify({"error": "no_account_id"}), 400
        p = _broker_history_path(acct_id)
        existed = p.exists()
        if existed:
            backup = p.with_suffix(".jsonl.bak")
            try:
                p.rename(backup)
                logger.info(f"broker history wiped, backup at {backup}")
            except Exception:
                p.unlink()
        return jsonify({
            "ok": True,
            "wiped_existing": existed,
            "path": str(p),
            "message": "Broker stats reset. Reload dashboard. Next trades will populate fresh stats.",
        })
    except Exception as e:
        return jsonify({"error": repr(e)}), 500


def _merge_persisted_broker_trades(acct_id, live_rows, limit=1000):
    """Merge the live rows with any older trades from the JSONL file.
    Dedup by exit_order_id + exit_time so we don't double-count overlap.
    Returns the merged list sorted chronologically.
    """
    p = _broker_history_path(acct_id)
    if not p.exists():
        return live_rows
    persisted = []
    try:
        with p.open("r") as f:
            for line in f:
                try:
                    r = json.loads(line)
                    persisted.append(r)
                except Exception:
                    pass
    except Exception:
        return live_rows
    seen = set()
    merged = []
    # LIVE ROWS FIRST: freshly-computed rows must win over disk rows on
    # key collision, or pricing fixes can never take effect (2026-07-25:
    # persisted-first kept old commission-priced rows forever).
    for r in (live_rows + persisted):
        k = (r.get("exit_order_id"), r.get("exit_time"))
        if k in seen:
            continue
        seen.add(k)
        merged.append(r)
    merged.sort(key=lambda r: str(r.get("exit_time") or r.get("ts") or ""))
    return merged[-limit:]


def _collect_broker_trades_OLD_linkage(sess, acct_id: int,
                                         limit: int = 1000) -> list:
    """OLD implementation kept for reference. Used parent/oco linkage --
    missed trades whose bracket was disrupted (InvalidPrice rejections
    orphan the surviving bracket child). Superseded by the chronological
    fill-walk approach above."""
    # Fills -- timestamps + orderIds
    f_status, fills = sess._rest("GET", "/fill/list")
    fill_by_orderid = {}
    if f_status == 200 and isinstance(fills, list):
        for f in fills:
            if isinstance(f, dict) and f.get("orderId") is not None:
                fill_by_orderid[int(f["orderId"])] = f
    # Orders -- entry/exit attribution via parent/oco linkage
    o_status, orders = sess._rest("GET", "/order/list")
    order_by_id = {}
    if o_status == 200 and isinstance(orders, list):
        for o in orders:
            if isinstance(o, dict) and o.get("id") is not None:
                order_by_id[int(o["id"])] = o

    rows = []
    # PRIMARY: order-linkage reconstruction
    # A "parent" is an order with parentId=None AND has at least one
    # bracket child (another order with parentId=this.id) that's Filled.
    parents = []
    children_by_parent = {}
    for o in (order_by_id.values()):
        pid = o.get("parentId")
        if pid is None:
            parents.append(o)
        else:
            children_by_parent.setdefault(int(pid), []).append(o)

    for parent in parents:
        pid = parent.get("id")
        if pid is None:
            continue
        # Need parent to have an entry fill
        entry_fill = fill_by_orderid.get(int(pid))
        if not entry_fill:
            continue
        # Need at least one Filled bracket child (the exit)
        children = children_by_parent.get(int(pid), [])
        filled_exit = None
        for c in children:
            if c.get("ordStatus") == "Filled":
                cid = c.get("id")
                ef = fill_by_orderid.get(int(cid)) if cid else None
                if ef:
                    filled_exit = (c, ef)
                    break
        if not filled_exit:
            # Trade is still open (no bracket child filled yet)
            continue
        exit_order, exit_fill = filled_exit
        try:
            entry_ts = pd.Timestamp(entry_fill.get("timestamp"))
            exit_ts = pd.Timestamp(exit_fill.get("timestamp"))
            if entry_ts.tz is None:
                entry_ts = entry_ts.tz_localize("UTC")
            else:
                entry_ts = entry_ts.tz_convert("UTC")
            if exit_ts.tz is None:
                exit_ts = exit_ts.tz_localize("UTC")
            else:
                exit_ts = exit_ts.tz_convert("UTC")
        except Exception:
            continue
        try:
            entry_px = float(entry_fill.get("price") or 0)
            exit_px = float(exit_fill.get("price") or 0)
            qty = int(entry_fill.get("qty") or exit_fill.get("qty") or 1)
        except Exception:
            continue
        entry_action = (parent.get("action") or "").lower()
        side = "LONG" if entry_action == "buy" else "SHORT"
        if side == "LONG":
            pts_diff = exit_px - entry_px
        else:
            pts_diff = entry_px - exit_px
        comm_rt = float(os.environ.get("BROKER_COMM_PER_RT", "0.74"))
        pnl_usd = (pts_diff * qty * 2.0) - (comm_rt * qty)
        # Exit reason from the bracket child's order type
        exit_type = (exit_order.get("orderType") or "").lower()
        if "stop" in exit_type:
            exit_reason = "stop"
        elif "limit" in exit_type:
            exit_reason = "target"
        elif "market" in exit_type:
            exit_reason = "manual"
        else:
            exit_reason = "broker"
        rows.append({
            "ts": exit_ts.isoformat(),
            "entry_ts": entry_ts.isoformat(),
            "entry_time": entry_ts.isoformat(),
            "exit_time": exit_ts.isoformat(),
            "side": side,
            "qty": qty,
            "n_mnq": qty,
            "entry_px": round(entry_px, 4),
            "exit_px": round(exit_px, 4),
            "pnl_usd": round(pnl_usd, 2),
            "pnl": round(pnl_usd, 2),
            "pnl_pts": round(pts_diff, 4),
            "exit_reason": exit_reason,
            "hold_s": (exit_ts - entry_ts).total_seconds(),
            "commission": round(comm_rt * qty, 2),
            "source": "broker_order_linkage",
            "parent_order_id": int(pid),
            "exit_order_id": exit_order.get("id"),
            "setup_ref": parent.get("text"),
        })

    if rows:
        rows.sort(key=lambda r: r.get("ts") or "")
        return rows[-limit:]

    # FALLBACK: FillPair (FIFO matching). Used only when order linkage
    # yields nothing.
    fp_status, fill_pairs = sess._rest("GET", "/fillPair/list")
    fill_by_id = {}
    if f_status == 200 and isinstance(fills, list):
        for f in fills:
            if isinstance(f, dict) and f.get("id") is not None:
                fill_by_id[int(f["id"])] = f
    if (fp_status == 200 and isinstance(fill_pairs, list)
            and len(fill_pairs) > 0):
        for fp in fill_pairs:
            if not isinstance(fp, dict):
                continue
            bf = fill_by_id.get(int(fp.get("buyFillId") or 0)) or {}
            sf = fill_by_id.get(int(fp.get("sellFillId") or 0)) or {}
            buy_ts = bf.get("timestamp")
            sell_ts = sf.get("timestamp")
            if not buy_ts or not sell_ts:
                continue
            try:
                bts_dt = pd.Timestamp(buy_ts)
                sts_dt = pd.Timestamp(sell_ts)
                if bts_dt.tz is None:
                    bts_dt = bts_dt.tz_localize("UTC")
                else:
                    bts_dt = bts_dt.tz_convert("UTC")
                if sts_dt.tz is None:
                    sts_dt = sts_dt.tz_localize("UTC")
                else:
                    sts_dt = sts_dt.tz_convert("UTC")
            except Exception:
                continue
            if bts_dt <= sts_dt:
                side = "LONG"
                entry_ts, exit_ts = bts_dt, sts_dt
                entry_fill, exit_fill = bf, sf
                entry_px = float(fp.get("buyPrice") or 0)
                exit_px = float(fp.get("sellPrice") or 0)
            else:
                side = "SHORT"
                entry_ts, exit_ts = sts_dt, bts_dt
                entry_fill, exit_fill = sf, bf
                entry_px = float(fp.get("sellPrice") or 0)
                exit_px = float(fp.get("buyPrice") or 0)
            qty = int(fp.get("qty") or 1)
            pts_diff = _broker_pnl_pts(entry_px, exit_px) if side == "LONG" \
                        else _broker_pnl_pts(exit_px, entry_px)
            comm_rt = float(os.environ.get("BROKER_COMM_PER_RT", "0.74"))
            pnl_usd = (pts_diff * qty * 2.0) - (comm_rt * qty)
            exit_order_id = exit_fill.get("orderId")
            exit_reason = "broker"
            exit_order = order_by_id.get(int(exit_order_id or 0)) or {}
            otype = exit_order.get("orderType", "")
            text = (exit_order.get("text") or "").lower()
            if otype == "Stop" or "stop" in text:
                exit_reason = "stop"
            elif otype == "Limit":
                exit_reason = "target"
            elif otype == "Market":
                if "flat" in text or "timeout" in text or "close" in text:
                    exit_reason = "timeout"
                else:
                    exit_reason = "manual"
            rows.append({
                "ts": exit_ts.isoformat(),
                "entry_ts": entry_ts.isoformat(),
                "entry_time": entry_ts.isoformat(),
                "exit_time": exit_ts.isoformat(),
                "side": side,
                "qty": qty,
                "n_mnq": qty,
                "entry_px": round(entry_px, 4),
                "exit_px": round(exit_px, 4),
                "pnl_usd": round(pnl_usd, 2),
                "pnl": round(pnl_usd, 2),
                "pnl_pts": round(pts_diff, 4),
                "exit_reason": exit_reason,
                "hold_s": (exit_ts - entry_ts).total_seconds(),
                "commission": round(comm_rt * qty, 2),
                "source": "broker_fillpair",
                "position_id": fp.get("positionId"),
                "broker_buy_fill_id": fp.get("buyFillId"),
                "broker_sell_fill_id": fp.get("sellFillId"),
                "buy_price": fp.get("buyPrice"),
                "sell_price": fp.get("sellPrice"),
                "active": fp.get("active"),
            })

    # NOTE: We previously tried to reconstruct historical trades from
    # /cashBalanceLog/deps using realizedPnL deltas. That gave garbage:
    # the log includes commission rows, mark-to-market updates, AND
    # admin events (account resets that null the realizedPnL field) --
    # treating each delta as a "trade" produced thousands of false
    # rows ranging from $0.02 to $1,085+. Not workable.
    #
    # If FillPair is empty, we now return [] from this helper. The UI
    # then shows the empty-state banner with the LIVE cashBalance
    # numbers (totalCashValue, realizedPnL) -- which are correct as
    # aggregates even if per-trade breakdown isn't available.
    #
    # Per-trade history WILL populate once the bot trades live during
    # market hours, because:
    #   - Tradovate user_ws ExecutionReports capture each fill in <100ms
    #   - The bot's audit log records every placeoso attempt
    #   - The trade_timeline tracks each setup_ref through its lifecycle
    # All of those are reliable; cashBalanceLog reconstruction is not.

    rows.sort(key=lambda r: r.get("ts") or "")
    return rows[-limit:]


@app.route("/api/broker/trades")
def api_broker_trades():
    """All closed trades from the broker's FillPair table -- the
    SINGLE SOURCE OF TRUTH for what actually happened.

    Returns the same shape as /api/all_trades so the Performance tab
    + equity curve + Trades tab can swap to this endpoint with zero
    rendering changes. Each row carries source='broker_fillpair' so
    the UI can tag it.
    """
    try:
        from bot.tradovate_client import get_session
    except Exception as e:
        return jsonify({"error": f"client import failed: {e!r}"}), 500
    sess = get_session()
    if not sess.is_configured:
        return jsonify({"configured": False, "trades": []})
    acct_id = sess.get_account_id()
    if acct_id is None:
        return jsonify({"configured": True, "trades": [],
                         "error": "no_account_id"})
    rows = _collect_broker_trades(sess, acct_id, limit=10_000)
    return jsonify(rows)


@app.route("/api/broker/stats")
def api_broker_stats():
    """Performance stats from broker reality.

    Computed entirely from FillPairs + CashBalance. Includes:
      - balance (current net liq), realized P&L, open P&L
      - trade counts, win rate, profit factor, avg win/loss
      - peak balance + max drawdown
      - per-day breakdown (for the daily P&L chart)
    """
    try:
        from bot.tradovate_client import get_session
    except Exception as e:
        return jsonify({"error": f"client import failed: {e!r}"}), 500
    sess = get_session()
    if not sess.is_configured:
        return jsonify({"configured": False})
    acct_id = sess.get_account_id()
    if acct_id is None:
        return jsonify({"configured": True, "error": "no_account_id"})

    # ---- balance / open / realized ----
    cb_status, cb = sess._rest(
        "POST", "/cashBalance/getCashBalanceSnapshot",
        body={"accountId": int(acct_id)})
    balance = realized = open_pnl = net_liq = None
    starting = None
    week_realized = None
    if cb_status == 200 and isinstance(cb, dict):
        balance = cb.get("totalCashValue")
        net_liq = cb.get("netLiq")
        open_pnl = cb.get("openPnL")
        realized = cb.get("realizedPnL")
        week_realized = cb.get("weekRealizedPnL")
        starting = cb.get("netLiqSOD") or cb.get("totalCashValueSOD")

    # ---- trade stats from FillPairs ----
    # Apply the SAME reset cutoff used for paper trades. /api/admin/reset_all
    # updates lucid_account.started_at, which serves as the source-of-truth
    # cutoff for "trades since reset" across the whole dashboard. Without
    # this filter the broker view kept showing every demo-account fill
    # going back to the day the bot was wired in, polluting headline
    # stats with pre-strategy noise.
    trades_all = _collect_broker_trades(sess, acct_id, limit=100_000)
    trades = _filter_trades_since_reset(trades_all)
    n = len(trades)
    wins = sum(1 for t in trades if (t.get("pnl_usd") or 0) > 0)
    losses = sum(1 for t in trades if (t.get("pnl_usd") or 0) < 0)
    total_pnl = sum((t.get("pnl_usd") or 0) for t in trades)
    gross_win = sum((t.get("pnl_usd") or 0) for t in trades
                     if (t.get("pnl_usd") or 0) > 0)
    gross_loss = sum((t.get("pnl_usd") or 0) for t in trades
                      if (t.get("pnl_usd") or 0) < 0)
    avg_win = (gross_win / wins) if wins else 0.0
    avg_loss = (gross_loss / losses) if losses else 0.0
    pf = (gross_win / abs(gross_loss)) if gross_loss else None
    win_rate = (wins / n * 100) if n else 0.0

    # ---- equity curve + drawdown ----
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    equity_curve = []
    for t in trades:
        cum += float(t.get("pnl_usd") or 0)
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd
        equity_curve.append({
            "ts": t.get("ts"),
            "cum_pnl": round(cum, 2),
            "trade_pnl": float(t.get("pnl_usd") or 0),
        })

    # ---- per-NY-day breakdown ----
    from collections import defaultdict
    from research.signal_filters import NY_TZ
    by_day = defaultdict(lambda: {"n": 0, "pnl": 0.0, "wins": 0})
    for t in trades:
        et = t.get("exit_time")
        if not et:
            continue
        try:
            ts = pd.Timestamp(et)
            if ts.tz is None:
                ts = ts.tz_localize("UTC")
            else:
                ts = ts.tz_convert("UTC")
            ny_date = ts.tz_convert(NY_TZ).date().isoformat()
        except Exception:
            continue
        d = by_day[ny_date]
        d["n"] += 1
        pnl = float(t.get("pnl_usd") or 0)
        d["pnl"] += pnl
        if pnl > 0:
            d["wins"] += 1
    daily = [{"date": k, "n": v["n"], "wins": v["wins"],
                "win_rate": round(v["wins"] / v["n"] * 100, 1)
                            if v["n"] else 0,
                "pnl": round(v["pnl"], 2)}
              for k, v in sorted(by_day.items())]

    # ================= BROKER LEDGER OVERRIDE (2026-07-25) =================
    # User: "don't try and calculate it yourself — it should just work."
    # Tradovate's cashBalanceLog records the running balance to the PENNY
    # after every trade and every individual fee. When available, the
    # equity curve, Total P&L, max drawdown and daily P&L come straight
    # from that ledger — by construction they equal the account balance.
    # Trade counts / win rate stay from the paired-trade rows.
    pnl_source = "trades_estimated"
    try:
        cutoff_iso = os.environ.get("BROKER_TRADES_HIDE_BEFORE", "2026-07-18")
        ls, lrows = sess._rest("GET", "/cashBalanceLog/deps",
                               params={"masterid": int(acct_id)})
        if ls == 200 and isinstance(lrows, list) and lrows:
            # TRADING entries only — deposits/manual adjustments (e.g. the
            # Jul-20 account reset) must not bend the P&L curve, and the
            # running cum is built from exact DELTAS in stable order, not
            # from 'amount' snapshots (unordered ties inflated max-DD to
            # -\$700 vs the true -\$339).
            TRADE_TYPES = {"TradePaired", "Commission", "ExchangeFee",
                           "ClearingFee", "NfaFee", "BrokerageFee",
                           "IPFee", "Commision"}
            led = [r for r in lrows if isinstance(r, dict)
                   and r.get("currencyId") == 1
                   and r.get("timestamp")
                   and r.get("cashChangeType") in TRADE_TYPES
                   and r.get("delta") is not None]
            led.sort(key=lambda r: (r["timestamp"], r.get("id") or 0))
            post = [r for r in led if r["timestamp"] >= cutoff_iso]
            if len(post) >= 3:
                curve = []
                cumv = 0.0
                peak2 = 0.0
                low2 = 0.0
                for r in post:
                    cumv += float(r["delta"])
                    if cumv > peak2:
                        peak2 = cumv
                    if cumv < low2:
                        low2 = cumv
                    if r.get("cashChangeType") == "TradePaired" or r is post[-1]:
                        curve.append({
                            "ts": r["timestamp"],
                            "cum_pnl": round(cumv, 2),
                            "trade_pnl": round(float(r.get("delta") or 0), 2),
                        })
                if len(curve) > 3000:
                    curve = curve[-3000:]
                equity_curve = curve
                total_pnl = round(cumv, 2)
                # USER DEFINITION (2026-07-25): max drawdown = deepest
                # point BELOW the starting balance ("how low has it gone
                # all time"), not peak-to-trough.
                max_dd = round(abs(low2), 2)
                peak = round(peak2, 2)
                # daily P&L from ledger deltas; keep n/wins from trades
                dled: dict = {}
                for r in post:
                    td = r.get("tradeDate") or {}
                    try:
                        key = (f"{td['year']:04d}-{td['month']:02d}"
                               f"-{td['day']:02d}")
                    except Exception:
                        key = r["timestamp"][:10]
                    dled[key] = dled.get(key, 0.0) + float(r.get("delta") or 0)
                trades_by_day = {d["date"]: d for d in daily}
                daily = [{"date": k,
                          "n": trades_by_day.get(k, {}).get("n", 0),
                          "wins": trades_by_day.get(k, {}).get("wins", 0),
                          "win_rate": trades_by_day.get(k, {}).get("win_rate", 0),
                          "pnl": round(v, 2)}
                         for k, v in sorted(dled.items())]
                pnl_source = "broker_ledger"
    except Exception as e:
        logger.debug(f"ledger override: {e!r}")

    return jsonify({
        "pnl_source": pnl_source,
        "configured": True,
        "account_id": acct_id,
        "balance": balance,
        "net_liq": net_liq,
        "starting": starting,
        "realized_pnl": realized,
        "open_pnl": open_pnl,
        "week_realized": week_realized,
        "summary": {
            "n_trades": n,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 1),
            "total_pnl": round(total_pnl, 2),
            "gross_win": round(gross_win, 2),
            "gross_loss": round(gross_loss, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(pf, 2) if pf is not None else None,
            "peak_pnl": round(peak, 2),
            "max_drawdown": round(max_dd, 2),
        },
        "equity_curve": equity_curve,
        "daily": daily,
    })


@app.route("/api/broker/position")
def api_broker_position():
    """Live position(s) on the broker, enriched with stop/target levels
    from the working OCO bracket children.

    Returns a single 'position' shape compatible with the Live tab's
    Active Trade card.
    """
    try:
        from bot.tradovate_client import get_session
    except Exception as e:
        return jsonify({"error": f"client import failed: {e!r}"}), 500
    sess = get_session()
    if not sess.is_configured:
        return jsonify({"configured": False, "position": None})
    acct_id = sess.get_account_id()
    if acct_id is None:
        return jsonify({"configured": True, "position": None,
                         "error": "no_account_id"})
    # ---- /position/list ----
    p_status, positions = sess._rest("GET", "/position/list")
    open_pos = None
    all_pos = []               # every nonzero position, with symbol (basket)
    if p_status == 200 and isinstance(positions, list):
        for p in positions:
            if not isinstance(p, dict):
                continue
            if p.get("accountId") != acct_id:
                continue
            if not p.get("netPos"):
                continue
            if open_pos is None:
                open_pos = p
            sym = _contract_symbol(sess, p.get("contractId"))
            all_pos.append({
                "symbol": sym or "?",
                "instr": _root_of(sym) if sym else "?",
                "netPos": p.get("netPos"),
                "netPrice": p.get("netPrice"),
                "openPnL": p.get("openPnL"),
            })
    if open_pos is None:
        return jsonify({"configured": True, "account_id": acct_id,
                         "position": None, "positions": []})
    # ---- Enrich with bracket levels from working orders ----
    o_status, orders = sess._rest("GET", "/order/list")
    contract_id = open_pos.get("contractId")
    stop_px = target_px = None
    bracket_orders = []
    if o_status == 200 and isinstance(orders, list):
        # Need orderVersion for prices -- Order entity doesn't have them
        for o in orders:
            if not isinstance(o, dict):
                continue
            if o.get("contractId") != contract_id:
                continue
            if o.get("ordStatus") != "Working":
                continue
            oid = o.get("id")
            try:
                ov_status, ov_list = sess._rest(
                    "GET", "/orderVersion/deps",
                    params={"masterid": int(oid)})
                latest = None
                if ov_status == 200 and isinstance(ov_list, list) and ov_list:
                    latest = max(ov_list,
                                  key=lambda d: d.get("id", 0)
                                  if isinstance(d, dict) else 0)
                if not isinstance(latest, dict):
                    continue
                otype = latest.get("orderType")
                px = latest.get("price")
                spx = latest.get("stopPrice")
                bracket_orders.append({
                    "order_id": oid,
                    "type": otype,
                    "price": px,
                    "stop_price": spx,
                    "action": o.get("action"),
                })
                if otype == "Stop" and spx is not None:
                    stop_px = float(spx)
                elif otype == "Limit" and px is not None:
                    target_px = float(px)
            except Exception:
                continue
    net_pos = open_pos.get("netPos") or 0
    side = "LONG" if net_pos > 0 else "SHORT"
    return jsonify({
        "configured": True,
        "account_id": acct_id,
        "position": {
            "side": side,
            "qty": abs(int(net_pos)),
            "entry_px": open_pos.get("avgEntryPrice")
                         or open_pos.get("netPrice")
                         or open_pos.get("prevPrice"),
            "stop_px": stop_px,
            "target_px": target_px,
            "open_pnl": open_pos.get("openPnL"),
            "timestamp": open_pos.get("timestamp"),
            "contract_id": contract_id,
            "bracket_orders": bracket_orders,
            "raw": open_pos,
        },
        "positions": all_pos,
    })


@app.route("/api/basket")
def api_basket():
    """SNAP-BACK BASKET operation snapshot for the dashboard.

    Merges the engine's status file (sleeve states, positions, day/cum
    P&L — written every poll cycle) with the live-price file (Polygon,
    ~5s) and computes open P&L per sleeve and per instrument."""
    from bot.basket_engine import DATA as _basket_data
    def _read(p):
        try:
            return json.loads((_basket_data / p).read_text())
        except Exception:
            return None
    status = _read("basket_status.json")
    prices = _read("basket_prices.json") or {}
    if not status:
        return jsonify({"running": False})
    pv = status.get("pv") or {}
    inst: dict = {}
    open_total = 0.0
    for s in status.get("sleeves", []):
        r = s["instr"]
        d = inst.setdefault(r, {"instr": r,
                                "symbol": (status.get("symbols") or {}).get(r),
                                "watching": 0, "gated": 0, "armed": 0,
                                "in_trade": 0, "open_pnl": None,
                                "positions": []})
        st = s.get("state")
        if st in ("long", "short"):
            d["in_trade"] += 1
            px = (prices.get(r) or {}).get("px")
            op = None
            if px is not None and s.get("entry_px") is not None:
                sign = 1 if st == "long" else -1
                op = (float(px) - float(s["entry_px"])) * sign * \
                     float(pv.get(r, 0)) * int(status.get("units", 1))
                open_total += op
                d["open_pnl"] = (d["open_pnl"] or 0.0) + op
            d["positions"].append({"i": s["i"], "side": st,
                                   "entry_px": s.get("entry_px"),
                                   "stop": s.get("stop"), "tgt": s.get("tgt"),
                                   "bars_held": s.get("bars_held"),
                                   "max_bars": s.get("max_bars"),
                                   "open_pnl": None if op is None else round(op, 2)})
        elif st == "armed":
            d["armed"] += 1
        elif st == "gated":
            d["gated"] += 1
        else:
            d["watching"] += 1
    for r, d in inst.items():
        p = prices.get(r) or {}
        d["px"] = p.get("px")
        d["px_src"] = p.get("src")
        d["px_ts"] = p.get("ts")
        if d["open_pnl"] is not None:
            d["open_pnl"] = round(d["open_pnl"], 2)
    order = ["ES", "YM", "RTY", "GC", "CL", "ZB"]
    return jsonify({
        "running": True,
        "ts": status.get("ts"),
        "day": status.get("day"),
        "day_pnl": status.get("day_pnl"),
        "cum_pnl": status.get("cum_pnl"),
        "open_pnl": round(open_total, 2),
        "halted_today": status.get("halted_today"),
        "killed": status.get("killed"),
        "gates": status.get("gates"),
        "units": status.get("units"),
        "instruments": [inst[r] for r in order if r in inst] +
                       [v for k, v in inst.items() if k not in order],
        "sleeves": status.get("sleeves"),
    })


@app.route("/api/diagnostics/recommended_slip")
def api_diagnostics_recommended_slip():
    """Returns the slip_calibration block from the diagnostic extras
    so the dashboard can show 'Apply recommended slip' on a button.
    Always read-only -- the apply step writes a flag file the bot
    consumes on the next reload."""
    try:
        return jsonify(_build_slip_calibration())
    except Exception as e:
        return jsonify({"error": repr(e)}), 500


@app.route("/api/diagnostics/apply_slip", methods=["POST"])
def api_diagnostics_apply_slip():
    """Persist a new PAPER_STOP_SLIP_PTS recommendation to a flag file
    the bot reads on startup. NOT an env var override (that would
    require a Railway redeploy) -- this is a runtime override file
    in BOT_DATA_DIR.
    """
    try:
        body = request.get_json() or {}
        value = float(body.get("value"))
        if not (0 <= value <= 5):
            return jsonify({"error": "value out of range"}), 400
        from bot.account_ctx import data_dir as _acct_dir
        flag = _acct_dir() / "slip_override.json"
        flag.write_text(json.dumps({
            "PAPER_STOP_SLIP_PTS": value,
            "set_at": datetime.now(timezone.utc).isoformat(),
        }))
        return jsonify({"ok": True, "value": value, "path": str(flag)})
    except Exception as e:
        return jsonify({"error": repr(e)}), 500


@app.route("/api/diagnostics/polygon_readiness")
def api_polygon_readiness():
    """Tells the user when it's safe to cancel Polygon.

    Reads BOT_BAR_SOURCE + Tradovate bar fetch stats and computes:
      - hours since last Tradovate failure (or fallback)
      - traffic-light status (RED < 1h, AMBER < 24h, GREEN >= 24h)
      - total successes / failures since bot start

    Threshold for "safe to cancel": GREEN for 48 hours continuous.
    """
    out = {
        "bar_source_env": os.environ.get("BOT_BAR_SOURCE", "polygon"),
        "polygon_api_key_set": bool(
            os.environ.get("POLYGON_API")
            or os.environ.get("POLYGON_API_KEY")),
        "tradovate_demo": os.environ.get("TRADOVATE_DEMO", "true"),
    }
    try:
        from bot.tradovate_bars import get_stats
        stats = get_stats()
        out.update(stats)
        now = time.time()
        for k in ("last_tradovate_success_ts",
                   "last_tradovate_failure_ts",
                   "last_polygon_fallback_ts",
                   "first_call_ts"):
            v = stats.get(k)
            out[k.replace("_ts", "_age_h")] = (
                round((now - v) / 3600.0, 2) if v else None)
        # Light status
        last_bad = stats.get("last_polygon_fallback_ts") or stats.get("last_tradovate_failure_ts")
        if not last_bad and stats.get("tradovate_success_count", 0) > 0:
            out["status"] = "GREEN"
            out["recommendation"] = ("No fallbacks observed. Safe to keep "
                                       "BOT_BAR_SOURCE=tradovate. After 48h "
                                       "of GREEN you can cancel Polygon.")
        else:
            age_h = ((now - last_bad) / 3600.0) if last_bad else None
            if age_h is None:
                out["status"] = "GREY"
                out["recommendation"] = ("No bar fetches recorded yet -- "
                                           "wait for market hours.")
            elif age_h < 1:
                out["status"] = "RED"
                out["recommendation"] = ("Tradovate had a recent failure "
                                           "-- keep Polygon until stable.")
            elif age_h < 24:
                out["status"] = "AMBER"
                out["recommendation"] = ("Tradovate had a fallback in the "
                                           "last 24h. Wait longer before "
                                           "cancelling Polygon.")
            else:
                out["status"] = "GREEN"
                out["recommendation"] = (f"Last fallback {age_h:.1f}h ago. "
                                           f"If this stays >48h, cancel "
                                           f"Polygon.")
    except Exception as e:
        out["error"] = repr(e)
    return jsonify(out)


@app.route("/api/diagnostics/tick_replay")
def api_diagnostics_tick_replay():
    """Tick stream around a given time window. Used by the trade
    detail modal to replay price action around an entry/exit.

    Query params:
      ts_from  -- ISO timestamp or epoch seconds (start)
      ts_to    -- ISO timestamp or epoch seconds (end)
      pad_s    -- seconds to pad on each side (default 30)
    """
    try:
        from bot.tick_history import get_tick_history
        history = get_tick_history()
    except Exception as e:
        return jsonify({"error": repr(e)}), 500
    ticks_all = history.get("ticks_tail") or []
    try:
        ts_from = request.args.get("ts_from")
        ts_to = request.args.get("ts_to")
        pad = float(request.args.get("pad_s", "30"))

        def _to_epoch(v):
            if v is None:
                return None
            try:
                return float(v)
            except Exception:
                pass
            try:
                return pd.Timestamp(v).timestamp()
            except Exception:
                return None

        a = _to_epoch(ts_from)
        b = _to_epoch(ts_to)
        if a is None or b is None:
            return jsonify({"error": "invalid ts_from/ts_to"}), 400
        a -= pad
        b += pad
        filtered = [t for t in ticks_all
                     if isinstance(t, dict)
                     and t.get("ts") is not None
                     and a <= t["ts"] <= b]
        # Stats per source
        by_src = {}
        for t in filtered:
            s = t.get("src", "?")
            by_src.setdefault(s, 0)
            by_src[s] += 1
        return jsonify({
            "n": len(filtered),
            "ts_from_epoch": a,
            "ts_to_epoch": b,
            "by_source": by_src,
            "ticks": filtered,
        })
    except Exception as e:
        return jsonify({"error": repr(e)}), 500


@app.route("/api/diagnostics/bracket_ab")
def api_diagnostics_bracket_ab():
    """Hypothetical A/B: what would total P&L look like with the
    OPPOSITE setting of BRACKET_SLIP_PRE_ADJUST? Pure read-only
    analysis -- doesn't change anything.

    Method:
      - Pull all closed paper trades since last reset (broker analog
        is FillPair history but paper has the correct stop/target
        anchor for the counterfactual).
      - For each STOP trade, compute the alternate P&L:
          - If pre-adjust ON now: alternate fill = stop_px +/- slip
            (broker without pre-adjust)
          - If pre-adjust OFF now: alternate fill = stop_px (broker
            with pre-adjust)
      - For TARGET / TIMEOUT trades: no change.
      - Sum the delta over the trade history.
    """
    cur_adjust = (os.environ.get("BRACKET_SLIP_PRE_ADJUST", "false")
                    .lower() in ("true", "1", "yes"))
    try:
        slip = float(os.environ.get("PAPER_STOP_SLIP_PTS", "0.5"))
    except Exception:
        slip = 0.5
    rows = _filter_trades_since_reset(persistence.load_trades(
        limit=10_000, only_closed=True))
    stop_trades = [r for r in rows if r.get("exit_reason") == "stop"]
    # MNQ $2/pt, qty assumed from row
    delta_per_stop = slip * 2.0  # absolute dollar impact per stop trade
    if cur_adjust:
        # Currently better. Hypothetical = current - delta * qty
        sign = -1
        msg = ("Currently ENABLED. If disabled, each stop trade would "
                f"lose an extra ${delta_per_stop:.2f}/contract.")
    else:
        sign = +1
        msg = ("Currently DISABLED. If enabled, each stop trade would "
                f"save ${delta_per_stop:.2f}/contract.")
    n_stop = len(stop_trades)
    total_qty = sum(int(r.get("qty") or 0) for r in stop_trades)
    delta_total = sign * delta_per_stop * total_qty
    cur_pnl = sum(float(r.get("pnl") or 0) for r in rows)
    alt_pnl = cur_pnl + delta_total
    return jsonify({
        "current_setting": cur_adjust,
        "slip_pts": slip,
        "n_stop_trades": n_stop,
        "total_stop_qty": total_qty,
        "delta_per_stop_per_contract": round(delta_per_stop, 2),
        "delta_total_alternative": round(delta_total, 2),
        "current_total_pnl": round(cur_pnl, 2),
        "alternative_total_pnl": round(alt_pnl, 2),
        "recommendation": msg,
    })


@app.route("/api/diagnostics/check")
def api_diagnostics_check():
    """Lightweight version of the consistency check for the dashboard's
    Auto Health Check card. Returns the same RED/AMBER/GREEN findings
    as the bundle's consistency_check, but without dragging in the
    full bundle (much faster)."""
    try:
        extras = _build_diagnostic_extras()
        return jsonify(extras.get("consistency_check") or {})
    except Exception as e:
        return jsonify({"error": repr(e)}), 500


@app.route("/api/broker/trade/<setup_ref>")
def api_broker_trade_detail(setup_ref: str):
    """Drill-down for one specific trade: its full event timeline,
    matched broker fills, and the original orders. Used by the
    Trades-tab modal so the user can click a trade and see exactly
    what happened.

    Inputs: setup_ref tag (the bot stamps it on every order). The
    timeline module is keyed by setup_ref.
    """
    try:
        from bot.trade_timeline import get_timeline
        timeline = get_timeline(setup_ref)
    except Exception as e:
        timeline = []
    out = {"setup_ref": setup_ref, "timeline": timeline}
    # Find matching orders + fills + executionReports by text=setup_ref
    try:
        from bot.tradovate_client import get_session
        sess = get_session()
        if sess.is_configured:
            o_status, orders = sess._rest("GET", "/order/list")
            matched_orders = []
            order_ids = []
            if o_status == 200 and isinstance(orders, list):
                for o in orders:
                    if not isinstance(o, dict):
                        continue
                    text = (o.get("text") or "").strip()
                    if text == setup_ref:
                        matched_orders.append(o)
                        if o.get("id") is not None:
                            order_ids.append(int(o["id"]))
            out["orders"] = matched_orders
            # Fills for those orderIds
            f_status, fills = sess._rest("GET", "/fill/list")
            if f_status == 200 and isinstance(fills, list):
                out["fills"] = [f for f in fills
                                  if isinstance(f, dict)
                                  and f.get("orderId") in order_ids]
            # ExecutionReports for those orderIds
            er_status, ers = sess._rest("GET", "/executionReport/list")
            if er_status == 200 and isinstance(ers, list):
                out["execution_reports"] = [
                    er for er in ers
                    if isinstance(er, dict)
                    and er.get("orderId") in order_ids
                ]
            # OrderVersion for the prices on each order
            ov_chain = []
            for oid in order_ids:
                try:
                    vs, vd = sess._rest(
                        "GET", "/orderVersion/deps",
                        params={"masterid": int(oid)})
                    if vs == 200 and isinstance(vd, list):
                        ov_chain.append({"order_id": oid, "versions": vd})
                except Exception:
                    pass
            out["order_versions"] = ov_chain
    except Exception as e:
        out["broker_error"] = repr(e)
    return jsonify(out)


@app.route("/api/broker/last_trades")
def api_broker_last_trades():
    """Last N broker trades for the Trades tab. Same shape as
    /api/last_trades but sourced from FillPair instead of paper."""
    try:
        from bot.tradovate_client import get_session
    except Exception as e:
        return jsonify({"error": f"client import failed: {e!r}"}), 500
    sess = get_session()
    if not sess.is_configured:
        return jsonify({"configured": False, "trades": []})
    acct_id = sess.get_account_id()
    if acct_id is None:
        return jsonify({"configured": True, "trades": [],
                         "error": "no_account_id"})
    try:
        n = int(request.args.get("n", "50"))
    except Exception:
        n = 50
    rows = _collect_broker_trades(sess, acct_id, limit=10_000)
    # Return newest-first (Trades tab convention)
    rows = list(reversed(rows))[:n]
    return jsonify(rows)


@app.route("/api/tradovate_trades")
def api_tradovate_trades():
    """Recent broker activity on the active Tradovate account.

    Strategy: try multiple endpoints to find one that returns data.
    Tradovate's REST surface treats /fill/list, /fill/deps and
    /order/list differently depending on account type. We fall back
    through them so we always show SOMETHING when activity exists.

    Returns rows with: time, action (Buy/Sell), qty, price,
    order_id, source (which endpoint returned it).
    """
    try:
        from bot.tradovate_client import get_session
    except Exception as e:
        return jsonify({"error": f"client import failed: {e!r}"}), 500
    sess = get_session()
    if not sess.is_configured:
        return jsonify({"configured": False})
    acct_id = sess.get_account_id()
    if acct_id is None:
        return jsonify({"configured": True, "error": "no_account_id"})

    rows = []
    debug = {"attempts": []}

    # Attempt 1: /fill/list -- the canonical fill source.
    # Fills do NOT carry accountId; the API already scopes to the
    # authenticated user's accounts. We take them all.
    try:
        st, fills = sess._rest("GET", "/fill/list")
        debug["attempts"].append({"endpoint": "/fill/list",
                                    "status": st,
                                    "count": (len(fills)
                                              if isinstance(fills, list)
                                              else "non-list")})
        if st == 200 and isinstance(fills, list):
            for f in fills:
                if not isinstance(f, dict):
                    continue
                rows.append({
                    "time": f.get("timestamp"),
                    "action": f.get("action"),
                    "qty": f.get("qty"),
                    "price": f.get("price"),
                    "order_id": f.get("orderId"),
                    "fill_id": f.get("id"),
                    "contract_id": f.get("contractId"),
                    "source": "fill/list",
                })
    except Exception as e:
        debug["attempts"].append({"endpoint": "/fill/list", "error": repr(e)})

    # Attempt 2: /fill/deps with the account ID as master
    if not rows:
        try:
            st, fills = sess._rest("GET", "/fill/deps",
                                    params={"masterid": int(acct_id)})
            debug["attempts"].append({"endpoint": "/fill/deps",
                                        "status": st,
                                        "count": (len(fills)
                                                  if isinstance(fills, list)
                                                  else "non-list")})
            if st == 200 and isinstance(fills, list):
                for f in fills:
                    if not isinstance(f, dict):
                        continue
                    rows.append({
                        "time": f.get("timestamp"),
                        "action": f.get("action"),
                        "qty": f.get("qty"),
                        "price": f.get("price"),
                        "order_id": f.get("orderId"),
                        "fill_id": f.get("id"),
                        "source": "fill/deps",
                    })
        except Exception as e:
            debug["attempts"].append({"endpoint": "/fill/deps", "error": repr(e)})

    # Attempt 3: /order/list filtered to filled orders.
    # Orders have avgPrice + filledQty so we can show completed trades
    # even when /fill/* endpoints return empty.
    if not rows:
        try:
            st, orders = sess._rest("GET", "/order/list")
            debug["attempts"].append({"endpoint": "/order/list",
                                        "status": st,
                                        "count": (len(orders)
                                                  if isinstance(orders, list)
                                                  else "non-list")})
            if st == 200 and isinstance(orders, list):
                for o in orders:
                    if not isinstance(o, dict):
                        continue
                    if o.get("accountId") != acct_id:
                        continue
                    # Only filled orders count as trades
                    if o.get("ordStatus") not in ("Filled", "Completed"):
                        continue
                    rows.append({
                        "time": o.get("timestamp"),
                        "action": o.get("action"),
                        "qty": o.get("orderQty") or o.get("filledQty"),
                        "price": o.get("avgPrice") or o.get("price"),
                        "order_id": o.get("id"),
                        "fill_id": None,
                        "source": "order/list",
                    })
        except Exception as e:
            debug["attempts"].append({"endpoint": "/order/list", "error": repr(e)})

    # Newest first
    rows.sort(key=lambda r: r.get("time") or "", reverse=True)

    # Re-shape into the "fills" structure the frontend already
    # consumes -- it expects: timestamp, action, qty, price, orderId, id.
    # Skip rows with no price (canceled orders show up here from
    # /order/list but have no fill price -- not useful to display).
    fills_for_ui = []
    for r in rows[:200]:
        if r.get("price") is None:
            continue
        fills_for_ui.append({
            "timestamp": r.get("time"),
            "action": r.get("action"),
            "qty": r.get("qty"),
            "price": r.get("price"),
            "orderId": r.get("order_id"),
            "id": r.get("fill_id") or r.get("order_id"),
            "contractId": r.get("contract_id"),
        })

    return jsonify({
        "configured": True,
        "account_id": acct_id,
        "fills": fills_for_ui,
        "total_count": len(rows),
        "debug": debug,
    })


@app.route("/api/tradovate_flatten_all", methods=["GET", "POST"])
def api_tradovate_flatten_all():
    """EMERGENCY: close all open positions on the Tradovate account
    and cancel ALL working orders. Use when something looks wrong
    and you want to flatten everything immediately.

    Calls /order/liquidateposition for each open position, plus
    /order/cancelorder for each working order returned by
    /order/list (filtered to the active account).
    """
    try:
        from bot.tradovate_client import get_session
    except Exception as e:
        return jsonify({"error": f"client import failed: {e!r}"}), 500
    sess = get_session()
    if not sess.is_configured:
        return jsonify({"error": "credentials missing"}), 400
    acct_id = sess.get_account_id()
    if acct_id is None:
        return jsonify({"error": "no_account_id"}), 400

    results = {"closed_positions": [], "cancelled_orders": [], "errors": []}

    # Get all open positions for this account
    p_status, positions = sess._rest("GET", "/position/list")
    if p_status == 200 and isinstance(positions, list):
        for p in positions:
            if not isinstance(p, dict):
                continue
            if p.get("accountId") != acct_id:
                continue
            if not p.get("netPos"):  # 0 or None -> no position
                continue
            # Get the contract symbol -- /position only has contractId,
            # need /contract/item for the name.
            cid = p.get("contractId")
            c_status, contract = sess._rest(
                "GET", "/contract/item", params={"id": int(cid)})
            symbol = (contract.get("name")
                      if c_status == 200 and isinstance(contract, dict)
                      else None)
            if not symbol:
                results["errors"].append(
                    f"could not resolve symbol for contractId={cid}")
                continue
            # Flatten this contract. Tradovate REQUIRES contractId
            # (not symbol). See bot/tradovate_orders.py liquidate fix.
            l_status, l_resp = sess._rest(
                "POST", "/order/liquidateposition",
                body={
                    "accountSpec": sess.creds.username,
                    "accountId": int(acct_id),
                    "contractId": int(cid),
                    "admin": False,
                    "isAutomated": True,
                })
            results["closed_positions"].append({
                "symbol": symbol,
                "netPos": p.get("netPos"),
                "status": l_status,
                "response": str(l_resp)[:200],
            })

    # Cancel all working orders on this account
    o_status, orders = sess._rest("GET", "/order/list")
    if o_status == 200 and isinstance(orders, list):
        for o in orders:
            if not isinstance(o, dict):
                continue
            if o.get("accountId") != acct_id:
                continue
            # Working order states: PendingNew, Working, Suspended
            if o.get("ordStatus") not in ("Working", "PendingNew", "Suspended"):
                continue
            order_id = o.get("id")
            if not order_id:
                continue
            c_status, c_resp = sess._rest(
                "POST", "/order/cancelorder",
                body={"orderId": int(order_id), "isAutomated": True})
            results["cancelled_orders"].append({
                "order_id": order_id,
                "status": c_status,
                "response": str(c_resp)[:200],
            })

    return jsonify(results)


@app.route("/api/tradovate_test_order", methods=["GET", "POST"])
def api_tradovate_test_order():
    """Manual test order: places a small market order on the demo
    account to verify the broker integration. Use to debug "paper
    booked but broker has nothing" symptoms.

    Default: BUY 1 MNQ MARKET (no bracket).
    Override: ?side=Buy|Sell &qty=1 &bracket=1 &symbol=MNQM6

    With ?bracket=1 it uses placeoso with a 6pt stop / 12pt target
    bracket. Without, it sends a bare market order via placeorder.

    Returns the full Tradovate response so we can see exactly what
    the API said.
    """
    try:
        from bot.tradovate_client import get_session
        from bot.tradovate_orders import TradovateOrders
    except Exception as e:
        return jsonify({"error": f"import failed: {e!r}"}), 500
    sess = get_session()
    if not sess.is_configured:
        return jsonify({"error": "credentials missing"}), 400

    # Resolve symbol the same way the WS subscriber did
    try:
        from research.data_loader import polygon_front_month
        default_symbol = polygon_front_month(
            os.environ.get("POLYGON_CONTRACT", "MNQ"))
    except Exception:
        default_symbol = "MNQM6"
    symbol = request.args.get("symbol", default_symbol)
    side = request.args.get("side", "Buy")  # Buy or Sell
    qty = int(request.args.get("qty", "1"))
    use_bracket = request.args.get("bracket", "0") == "1"

    orders = TradovateOrders(sess)
    # Tradovate API expects side as "LONG"/"SHORT" in our wrapper
    side_strat = "LONG" if side.lower() == "buy" else "SHORT"
    if use_bracket:
        # For the test endpoint, get current market price as entry
        # estimate from PriceMonitor's snapshot (or fall back to a
        # default if not available).
        try:
            from bot.polygon_data import get_snapshot_price
            q = get_snapshot_price()
            entry_estimate = float(q[0]) if q else 29500.0
        except Exception:
            entry_estimate = 29500.0
        result = orders.submit_market_with_bracket(
            side=side_strat, qty=qty, symbol=symbol,
            stop_pts=6.0, target_pts=12.0,
            entry_estimate=entry_estimate,
            setup_ref="manual_test")
    else:
        result = orders.submit_market(
            side=side_strat, qty=qty, symbol=symbol,
            setup_ref="manual_test")
    return jsonify({
        "submitted": {
            "side": side, "qty": qty, "symbol": symbol,
            "bracket": use_bracket,
        },
        "ok": result.ok,
        "order_id": result.order_id,
        "status_code": result.status_code,
        "error": result.error,
        "response": result.response,
    })


@app.route("/api/tradovate_reset_all", methods=["GET", "POST"])
def api_tradovate_reset_all():
    """One-click reset for the Tradovate-direct setup.

    Wipes:
      - paper trades (the historical 1,971/161 noise from before
        Tradovate was wired)
      - lucid account state
      - dashboard snapshot
      - signal events

    Initializes paper account to the live Tradovate demo balance
    (or $50,000 fallback) so the dashboard's reference matches
    reality from cycle 1 onward.

    No password gate since the user explicitly asked for "reset
    everything completely". This is a single-user demo dashboard.
    """
    import shutil as _shutil
    from bot.account_ctx import data_dir
    base = data_dir()
    starting_balance = 50_000.0
    # Try to read live Tradovate balance to set the paper account's
    # starting equity to match.
    try:
        from bot.tradovate_client import get_session
        sess = get_session()
        if sess.is_configured:
            acct_id = sess.get_account_id()
            if acct_id is not None:
                status, snap = sess._rest(
                    "POST", "/cashBalance/getCashBalanceSnapshot",
                    body={"accountId": int(acct_id)})
                if status == 200 and isinstance(snap, dict):
                    bal = snap.get("totalCashValue") or snap.get("cashBalance")
                    if isinstance(bal, (int, float)) and bal > 0:
                        starting_balance = float(bal)
    except Exception as e:
        logger.debug(f"tradovate balance fetch for reset failed: {e!r}")

    errors = []
    try:
        persistence.wipe_all_trades()
    except Exception as e:
        errors.append(f"wipe_all_trades: {e!r}")
    for fname in ("dashboard_data.json", "lucid_account.json",
                   "signal_events.json", "paper_trades.db",
                   "manual_pause.json", "traderspost_audit.jsonl"):
        try:
            p = base / fname
            if p.exists():
                p.unlink()
        except Exception as e:
            errors.append(f"{fname}: {e!r}")

    # Write a reset-pending flag with the starting balance. The bot's
    # next cycle reads this and re-initializes lucid state to match.
    # Bot expects: line 1 = ISO timestamp, line 2 = float balance.
    try:
        flag = base / "reset_pending.flag"
        from datetime import datetime as _dt, timezone as _tz
        flag.write_text(f"{_dt.now(_tz.utc).isoformat()}\n"
                        f"{starting_balance}\n")
    except Exception as e:
        errors.append(f"reset_pending.flag: {e!r}")

    return jsonify({
        "ok": len(errors) == 0,
        "starting_balance": starting_balance,
        "source": "tradovate_demo_balance" if starting_balance != 50_000.0
                  else "fallback_50k",
        "errors": errors,
        "note": ("Reset complete. Refresh the dashboard in 30s to see "
                 "fresh state. The bot will start fresh on its next cycle."),
    })


@app.route("/api/tradovate_diag")
def api_tradovate_diag():
    """Self-test for the Tradovate integration: runs auth + account
    list and returns the result as JSON. Hit this from a browser to
    verify env vars are correct before we wire the bot to Tradovate.

    Successful response:
      {
        "configured": true,
        "auth_ok": true,
        "cluster": "demo",
        "user_id": 12345,
        "has_market_data": true,
        "has_live": false,
        "expires_in_min": 89,
        "accounts": [
          {"id": 1830371, "name": "Real dosh", "active": true},
          {"id": ..., "name": "DEMO7295004", "active": true}
        ],
        "selected_account_id": ...
      }
    """
    try:
        from bot.tradovate_client import get_session, _is_demo
    except Exception as e:
        return jsonify({"error": f"client import failed: {e!r}"}), 500
    sess = get_session()
    if not sess.is_configured:
        import os as _os
        present = {
            k: bool(_os.environ.get(k))
            for k in ("TRADOVATE_USERNAME", "TRADOVATE_PASSWORD",
                      "TRADOVATE_APP_ID", "TRADOVATE_APP_VERSION",
                      "TRADOVATE_CID", "TRADOVATE_DEVICE_ID",
                      "TRADOVATE_API_SECRET", "TRADOVATE_DEMO")
        }
        return jsonify({
            "configured": False,
            "error": "credentials missing",
            "env_vars_present": present,
        })
    tokens = sess.authenticate()
    if tokens is None:
        return jsonify({
            "configured": True,
            "auth_ok": False,
            "cluster": "demo" if _is_demo() else "live",
            "error": ("Authentication failed -- check Railway logs for "
                      "the Tradovate response (search 'Tradovate auth')."),
        })
    accts = sess.account_list()
    selected = sess.get_account_id()
    return jsonify({
        "configured": True,
        "auth_ok": True,
        "cluster": "demo" if _is_demo() else "live",
        "user_id": tokens.user_id,
        "has_market_data": tokens.has_market_data,
        "has_live": tokens.has_live,
        "expires_in_min": round((tokens.expires_at - __import__("time").time()) / 60, 1),
        "accounts": [
            {
                "id": a.get("id"),
                "name": a.get("name"),
                "type": a.get("accountType"),
                "active": a.get("active"),
                "legal_status": a.get("legalStatus"),
            }
            for a in accts
        ],
        "selected_account_id": selected,
    })


@app.route("/api/diag")
def api_diag():
    """Server-side diagnostic — tells you whether the BOT process (not just
    the Flask dashboard) is actually alive and writing. Triggered by the
    "no trades yet" debugging session: dashboard server can be up while
    the bot loop has crashed silently."""
    from pathlib import Path as _P
    import os as _os
    from bot.account_ctx import data_dir as _acct_dir
    base = _acct_dir()   # per-account (respects ?account=N from before_request)
    def _info(p):
        if not p.exists(): return {"exists": False}
        st = p.stat()
        age = (datetime.now(timezone.utc).timestamp() - st.st_mtime)
        return {"exists": True, "size": st.st_size,
                "age_s": round(age, 1),
                "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()}
    out = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "files": {
            "dashboard_data.json": _info(base / "dashboard_data.json"),
            "lucid_account.json":  _info(base / "lucid_account.json"),  # correct name
            "paper_trades.db":     _info(base / "paper_trades.db"),
            "signal_events.json":  _info(base / "signal_events.json"),
            "live_bars.json":      _info(base / "live_bars.json"),
            "bot_heartbeat.txt":   _info(base / "bot_heartbeat.txt"),
            "bot_crash.txt":       _info(base / "bot_crash.txt"),
        },
        "env": {
            "BOT_SHADOW_MODE": _os.environ.get("BOT_SHADOW_MODE", "1"),
            "BOT_VERSION":     _os.environ.get("BOT_VERSION", "fib"),
            "POLYGON_API":     "set" if _os.environ.get("POLYGON_API") else "missing",
        },
    }
    # Show the actual crash traceback if one was captured by live_runner.
    cp = base / "bot_crash.txt"
    if cp.exists():
        try:
            out["crash_traceback"] = cp.read_text()[-4000:]
        except Exception as e:
            out["crash_traceback"] = f"<read failed: {e}>"
    hb = base / "bot_heartbeat.txt"
    if hb.exists():
        try:
            out["heartbeat"] = hb.read_text().strip()
        except Exception:
            pass
    # Snapshot fields the bot is supposed to populate. If these are missing,
    # the bot loop never reached _publish_dashboard().
    try:
        snap = persistence.load_dashboard()
        out["snapshot"] = {
            "has_ts": bool(snap.get("ts")),
            "has_cycle": "cycle" in snap,
            "cycle": snap.get("cycle"),
            "bars_processed": snap.get("bars_processed"),
            "bars_1m_source": snap.get("bars_1m_source"),
            "signals_fired": snap.get("signals_fired"),
            "signals_blocked": snap.get("signals_blocked"),
            "last_error": snap.get("last_error"),
            "mode": snap.get("mode"),
            "price": snap.get("price"),
            "price_ts": snap.get("price_ts"),
            "price_source": snap.get("price_source"),
            "price_realtime": snap.get("price_realtime"),
        }
        # WS health -- the key diagnostic for "why isn't bot trading":
        # if tick_count is 0 several minutes after start, the Polygon
        # plan isn't delivering real-time futures WebSocket ticks and
        # the bot is stuck on delayed REST aggregates.
        out["polygon_ws"] = snap.get("polygon_ws", {"enabled": False})
        out["ws_tick_bars"] = snap.get("ws_tick_bars", 0)
        # Tradovate market data health
        out["tradovate_md"] = snap.get("tradovate_md", {"enabled": False})
    except Exception as e:
        out["snapshot"] = {"error": str(e)}
    # Try to read Lucid state directly — if the bot ever ran, applied_reset_serial
    # is the most reliable "bot was alive" marker.
    try:
        lp = base / "lucid_account.json"
        if lp.exists():
            ls = json.loads(lp.read_text())
            out["lucid"] = {
                "applied_reset_serial": ls.get("applied_reset_serial"),
                "started_at":           ls.get("started_at"),
                "balance":              ls.get("balance"),
                "today_pnl":            ls.get("today_pnl"),
            }
    except Exception as e:
        out["lucid"] = {"error": str(e)}
    # CNBC poller (writes live_bars.json every 30s); independent of bot
    lb = base / "live_bars.json"
    if lb.exists():
        out["cnbc_poller_alive"] = (datetime.now(timezone.utc).timestamp()
                                    - lb.stat().st_mtime) < 120
    else:
        out["cnbc_poller_alive"] = False
    # Memory + process stats -- Railway killed the deploy for OOM, so we
    # want this visible to catch future leaks before they crash again.
    try:
        import os as _os, resource
        rusage = resource.getrusage(resource.RUSAGE_SELF)
        # ru_maxrss is in KB on Linux, bytes on macOS
        ru_max_mb = rusage.ru_maxrss / 1024
        out["memory"] = {
            "rss_max_mb": round(ru_max_mb, 1),
            "user_cpu_s": round(rusage.ru_utime, 1),
            "sys_cpu_s":  round(rusage.ru_stime, 1),
        }
        # Try to read current RSS from /proc/self/status (Linux)
        try:
            with open("/proc/self/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        kb = int(line.split()[1])
                        out["memory"]["rss_current_mb"] = round(kb / 1024, 1)
                    elif line.startswith("VmSize:"):
                        kb = int(line.split()[1])
                        out["memory"]["vsize_mb"] = round(kb / 1024, 1)
        except Exception:
            pass
    except Exception as e:
        out["memory_error"] = repr(e)
    # Top-level interpretation
    snap_age = out["files"]["dashboard_data.json"].get("age_s", 1e9)
    if not out["files"]["dashboard_data.json"]["exists"]:
        out["verdict"] = "bot has NEVER written a snapshot — startup crash or wiped <60s ago"
    elif snap_age > 300:
        out["verdict"] = f"bot snapshot is {snap_age/60:.1f}min stale — bot loop is dead"
    elif not out["snapshot"].get("has_cycle"):
        out["verdict"] = "snapshot file exists but no cycle field — wrong bot version?"
    elif out["snapshot"].get("cycle", 0) < 2:
        out["verdict"] = "bot is starting up (first cycle pending)"
    else:
        out["verdict"] = "bot is alive and ticking"
    return jsonify(out)


@app.route("/api/health/polygon")
def api_health_polygon():
    """Probe what the configured Polygon.io key can actually access.
    Hit this once after adding POLYGON_API to see your plan's entitlements:
    which tickers return data, how stale it is (delayed plans show 15+ min),
    and the last close. Tells us whether to use index, ETF, or futures
    tickers for the live bot."""
    try:
        from research.data_loader import polygon_diagnostic
        return jsonify(polygon_diagnostic())
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


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
    """Live price. Polygon-ONLY by design. No fallbacks.

    User directive: "we only should be using 1 stream for the price and
    tick data which is polygon." Previous code fell through to CNBC
    (15-min delayed), yfinance (1-15min delayed), and a CSV ledger when
    Polygon blipped -- that's what produced the dashboard NQ price
    flickering between 30501 and 30510 (a 9pt gap = Polygon vs delayed
    CNBC of the same NQ from 15 minutes ago).

    If Polygon snapshot fails, return null price. Frontend treats null
    as "data unavailable" and won't lie to the user with a stale value.
    """
    # FIRST: read the bot's published PriceMonitor snapshot from disk.
    # The bot polls Polygon every cycle, rejects stale data internally
    # via bot.polygon_data, and writes the fresh price to its snapshot.
    # As long as the snapshot is recent and the published price isn't
    # frozen (price_ts moves between polls), we use it directly. No
    # source-name discrimination -- bot.polygon_data already enforces
    # freshness, so whatever it gave us is good.
    try:
        state = persistence.load_dashboard()
        ws_price = state.get("price")
        ws_ts = state.get("price_ts")
        ws_source = state.get("price_source") or "polygon"
        snap_ts = state.get("ts")
        if ws_price is not None and snap_ts:
            try:
                from datetime import datetime as _dt
                # Use the snapshot's own ts (when the bot wrote it) as
                # the freshness gate. price_ts can lag behind ts when
                # the bot is using REST aggs (which only updates at
                # minute boundaries), but the snapshot being recent
                # means the bot at least TRIED to refresh recently.
                snap_t = _dt.fromisoformat(str(snap_ts).replace("Z", "+00:00"))
                snap_age = (datetime.now(timezone.utc) - snap_t).total_seconds()
            except Exception:
                snap_age = 0.0
            # Accept if the bot's last publish was <30s ago. The bot
            # publishes on every poll (~3-5s when idle, faster when
            # in trade), so >30s indicates the bot is dead.
            if snap_age < 30.0:
                return jsonify({
                    "price": float(ws_price),
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "age_s": round(float(snap_age), 2),
                    "source": str(ws_source),
                })
    except Exception as e:
        logger.debug(f"/api/price snapshot read failed: {e}")

    # FALLBACK: hit Polygon directly via the clean client. Runs
    # when the bot's snapshot doesn't have a recent price (e.g.
    # Tradovate WS is silent). Set POLYGON_SKIP=1 to disable.
    import os as _os
    if _os.environ.get("POLYGON_SKIP", "0") != "1":
        try:
            from bot.polygon_data import get_snapshot_price
            q = get_snapshot_price()
            if q is not None:
                price, age = q
                if age < 60:
                    return jsonify({
                        "price": float(price),
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "age_s": round(float(age), 2),
                        "source": "polygon_snapshot",
                    })
        except Exception as e:
            logger.warning(f"/api/price polygon snapshot failed: {e}")

    # Polygon failed -- return null so the frontend can show "—"
    # instead of a stale fallback price. State.monitor_error helps the
    # user see what's actually wrong.
    state = persistence.load_dashboard()
    return jsonify({
        "price": None,
        "ts": None,
        "monitor_error": state.get("monitor_error"),
        "source": "polygon_unavailable",
    })


@app.route("/api/candles")
def api_candles():
    """NQ=F 1-min bars for the lightweight-charts chart — matches the
    setup-detection timeframe the bot trades on.

    Strategy: try fresh 1-min first (Polygon/yfinance via download_nq);
    fall back to cached on transient failure. If the live 1-min feed is
    unavailable, fall back to 5-min so the chart still shows something.
    """
    df = None
    yf_age_min = None
    timeframe_used = "1min"
    try:
        df = download_nq("1min", force_refresh=True).tail(500)
        if df is not None and not df.empty:
            latest = df.index[-1]
            if latest.tz is None:
                latest = pd.Timestamp(latest).tz_localize("UTC")
            yf_age_min = (pd.Timestamp.now(tz="UTC") - latest).total_seconds() / 60
    except Exception as e:
        logger.warning(f"1-min candles fetch failed: {e}")
        try:
            df = download_nq("1min").tail(500)
        except Exception:
            df = None
    # Last-ditch fallback: 5-min so the chart never goes blank.
    if df is None or df.empty:
        try:
            df = download_nq("5min").tail(500)
            timeframe_used = "5min"
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
    """Up/down arrow markers for recent trades, ready to drop into
    lightweight-charts via series.setMarkers().

    Markers EXPIRE after MARKER_TTL_SECONDS (default 1 hour) so the chart
    only shows fresh activity — old entry/exit arrows clear themselves
    rather than cluttering the left edge forever. Each marker is shown
    only while its own timestamp (entry OR exit) is within the window."""
    MARKER_TTL_SECONDS = 3600  # 1 hour
    now_s = int(pd.Timestamp.now(tz="UTC").timestamp())
    cutoff = now_s - MARKER_TTL_SECONDS
    trades = _filter_trades_since_reset(persistence.load_trades(limit=2000))[:100]
    out = []
    for t in trades:
        try:
            entry_t = int(pd.Timestamp(t["entry_time"]).timestamp())
        except Exception:
            continue
        side = t.get("side")
        pnl = t.get("pnl")
        won = pnl is not None and pnl > 0
        # Entry arrow — only while within the 1h window
        if entry_t >= cutoff:
            out.append({
                "time": entry_t,
                "position": "belowBar" if side == "LONG" else "aboveBar",
                "color": "#26a69a" if side == "LONG" else "#ef5350",
                "shape": "arrowUp" if side == "LONG" else "arrowDown",
                "text": f"{side[0]}{int(t.get('qty') or 0)}",  # L12 / S8
            })
        # Exit dot — only while within the 1h window
        if t.get("exit_time"):
            try:
                exit_t = int(pd.Timestamp(t["exit_time"]).timestamp())
            except Exception:
                continue
            if exit_t >= cutoff:
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
    """Open-position state with live unrealized P&L vs the latest price.

    Pass ?source=broker to read the position from Tradovate's
    /position/list (the broker's view of what's actually open) instead
    of the paper account.
    """
    source = (request.args.get("source") or "paper").lower()
    if source == "broker":
        try:
            from bot.tradovate_client import get_session
            sess = get_session()
            if sess.is_configured:
                acct_id = sess.get_account_id()
                state = persistence.load_dashboard()
                px = state.get("price")
                if acct_id is not None:
                    p_status, positions = sess._rest("GET", "/position/list")
                    open_pos = None
                    if p_status == 200 and isinstance(positions, list):
                        for p in positions:
                            if not isinstance(p, dict):
                                continue
                            if p.get("accountId") != acct_id:
                                continue
                            if not p.get("netPos"):
                                continue
                            open_pos = p
                            break
                    if open_pos is None:
                        return jsonify({"in_trade": False, "price": px,
                                         "source": "broker"})
                    # Bracket lookup for stop/target
                    o_status, orders = sess._rest("GET", "/order/list")
                    stop_px = target_px = None
                    contract_id = open_pos.get("contractId")
                    if o_status == 200 and isinstance(orders, list):
                        for o in orders:
                            if not isinstance(o, dict):
                                continue
                            if o.get("contractId") != contract_id:
                                continue
                            if o.get("ordStatus") != "Working":
                                continue
                            oid = o.get("id")
                            try:
                                ov_s, ov = sess._rest(
                                    "GET", "/orderVersion/deps",
                                    params={"masterid": int(oid)})
                                if ov_s == 200 and isinstance(ov, list) and ov:
                                    latest = max(ov,
                                                  key=lambda d: d.get("id", 0)
                                                  if isinstance(d, dict) else 0)
                                    otype = latest.get("orderType")
                                    if otype == "Stop":
                                        sp = latest.get("stopPrice")
                                        if sp is not None:
                                            stop_px = float(sp)
                                    elif otype == "Limit":
                                        lp = latest.get("price")
                                        if lp is not None:
                                            target_px = float(lp)
                            except Exception:
                                pass
                    net_pos = open_pos.get("netPos") or 0
                    side = "LONG" if net_pos > 0 else "SHORT"
                    qty = abs(int(net_pos))
                    entry = (open_pos.get("avgEntryPrice")
                             or open_pos.get("netPrice") or 0)
                    entry = float(entry or 0)
                    stop = float(stop_px or 0)
                    tgt = float(target_px or 0)
                    dpp = 2.0
                    if side == "LONG":
                        pts_pnl = (px - entry) if px else 0
                    else:
                        pts_pnl = (entry - px) if px else 0
                    unrealized = pts_pnl * dpp * qty
                    span = abs(tgt - stop) if stop and tgt else 0
                    progress = (max(0.0, min(1.0,
                                  abs(px - stop) / span))
                                  if (span > 0 and px) else 0.5)
                    if side == "SHORT" and span > 0:
                        progress = 1 - progress
                    return jsonify({
                        "in_trade": True,
                        "source": "broker",
                        "signal": "tradovate",
                        "side": side, "qty": qty,
                        "entry_px": entry, "stop_px": stop,
                        "target_px": tgt,
                        "current_px": px,
                        "unrealized_usd": round(unrealized, 2),
                        "progress": progress,
                        "open_pnl_broker": open_pos.get("openPnL"),
                    })
        except Exception as e:
            logger.warning(f"broker live position: {e!r}")
        # Fall through to paper
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
        "profile": thesis_for(op.get("signal_name"), side),
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


def _reset_cutoff_ts():
    """Returns the lucid_account.started_at as a pandas Timestamp in UTC,
    or None if not available. Trades older than this cutoff are filtered
    out of every dashboard endpoint so a partial DB wipe can't leak old
    rows into the UI after a reset."""
    try:
        from bot.account_ctx import data_dir as _acct_dir
        candidates = []
        # explicit strategy-deploy cutoff (written on LEVELRIDE reset) —
        # authoritative, survives lucid rewrites
        cf = _acct_dir() / "strategy_cutoff.txt"
        if cf.exists():
            try:
                candidates.append(pd.Timestamp(cf.read_text().strip()))
            except Exception:
                pass
        lp = _acct_dir() / "lucid_account.json"
        if lp.exists():
            sa = json.loads(lp.read_text()).get("started_at")
            if sa:
                candidates.append(pd.Timestamp(sa))
        if not candidates:
            return None
        # use the LATEST cutoff so old broker fills are always excluded
        t = max((c.tz_convert("UTC") if c.tz is not None
                 else c.tz_localize("UTC")) for c in candidates)
        return t
    except Exception as e:
        logger.warning(f"reset cutoff parse failed: {e}")
        return None


def _filter_trades_since_reset(rows, cutoff=None):
    """Drop trade dicts whose entry_time is before the reset cutoff. Safe
    to call with cutoff=None (returns rows unchanged)."""
    if cutoff is None:
        cutoff = _reset_cutoff_ts()
    if cutoff is None:
        return rows
    out = []
    for r in rows:
        et = r.get("entry_time")
        if not et:
            continue
        try:
            ets = pd.Timestamp(et)
            ets = ets.tz_convert("UTC") if ets.tz is not None else ets.tz_localize("UTC")
            if ets < cutoff:
                continue
        except Exception:
            continue
        out.append(r)
    return out


@app.route("/api/trades")
def api_trades():
    """Recent trades for the dashboard's main chart / Trades tab.

    Pass ?source=broker to read broker FillPairs instead of paper.
    Default is paper for backwards compat with bookmarks; the frontend
    appends source=broker automatically when the user is in broker mode.
    """
    source = (request.args.get("source") or "paper").lower()
    if source == "broker":
        # Strict isolation: in broker mode, never return paper rows even
        # if broker is unreachable. See /api/all_trades for the full
        # explanation; same dashboard-glitch fix.
        try:
            from bot.tradovate_client import get_session
            sess = get_session()
            if sess.is_configured:
                acct_id = sess.get_account_id()
                if acct_id is not None:
                    rows = _collect_broker_trades(sess, acct_id, limit=10_000)
                    # Filter to trades after the most recent reset cutoff
                    # so the broker tab matches the paper tab's "since
                    # reset" semantics.
                    rows = _filter_trades_since_reset(rows)
                    return jsonify(list(reversed(rows))[:200])
        except Exception as e:
            logger.warning(f"broker trades fallback: {e!r}")
        return jsonify([])
    # Load extra so the post-cutoff filter still has at least 200 rows.
    rows = persistence.load_trades(limit=2000)
    return jsonify(_filter_trades_since_reset(rows)[:200])


@app.route("/api/all_trades")
def api_all_trades():
    """All closed trades since the current strategy was deployed, normalised
    to the dashboard's recent_trades shape. Used by the Performance tab so
    equity curve / monthly P&L / hold-time histogram / win-loss distribution
    aggregate over the FULL history (not just the 30-deep recent_trades
    deque), AND only count trades fired by the active strategy version
    (filtered by lucid_account.started_at).

    Pass ?source=broker to return broker FillPair rows instead of paper
    rows. The Performance tab uses this so charts/stats reflect what
    the broker ACTUALLY executed, not paper expectations.
    """
    source = (request.args.get("source") or "paper").lower()
    if source == "broker":
        # When the user explicitly asks for broker reality we MUST NOT
        # silently substitute paper data. That was the dashboard-glitch
        # bug: paper and broker tabs showed identical Performance numbers
        # because broker auth was dead (account_list=[], account_id=None)
        # and the route returned paper rows labeled as broker. Now we
        # return an empty array so the frontend knows there's nothing to
        # show and can display a clear "broker unavailable" banner.
        try:
            from bot.tradovate_client import get_session
            sess = get_session()
            if sess.is_configured:
                acct_id = sess.get_account_id()
                if acct_id is not None:
                    rows = _collect_broker_trades(sess, acct_id,
                                                    limit=100_000)
                    # Apply the same reset cutoff so equity curve / monthly
                    # P&L / hold-time histogram on the Performance tab
                    # reflect only the post-reset broker activity.
                    return jsonify(_filter_trades_since_reset(rows))
        except Exception as e:
            logger.warning(f"broker trades fallback: {e!r}")
        return jsonify([])
    rows = persistence.load_trades(limit=100_000, only_closed=True)
    # Cutoff: only count trades since the most recent RESET_SERIAL bump.
    # Without this, pre-upgrade trades (older window=3 / target=10 params)
    # could pollute the Performance tab once those trades' DB rows survive
    # a partial reset.
    cutoff = None
    try:
        from bot.account_ctx import data_dir as _acct_dir; lp = _acct_dir() / "lucid_account.json"
        if lp.exists():
            ls = json.loads(lp.read_text())
            sa = ls.get("started_at")
            if sa:
                cutoff = pd.Timestamp(sa).tz_convert("UTC") \
                    if pd.Timestamp(sa).tz is not None \
                    else pd.Timestamp(sa).tz_localize("UTC")
    except Exception as e:
        logger.warning(f"/api/all_trades cutoff parse failed: {e}")
    out = []
    for r in rows:
        et, xt = r.get("entry_time"), r.get("exit_time")
        if not et or not xt:
            continue
        # Parse + normalise to UTC. SQLite stores both "2026-05-25T12:00:00+00:00"
        # and (legacy) "2026-05-25 12:00:00" -- string sort would interleave
        # these wrong. We parse with pandas (handles both) and convert to
        # canonical UTC ISO so JS new Date() interprets identically.
        try:
            et_ts = pd.Timestamp(et)
            xt_ts = pd.Timestamp(xt)
            if et_ts.tz is None: et_ts = et_ts.tz_localize("UTC")
            else: et_ts = et_ts.tz_convert("UTC")
            if xt_ts.tz is None: xt_ts = xt_ts.tz_localize("UTC")
            else: xt_ts = xt_ts.tz_convert("UTC")
        except Exception:
            continue
        if cutoff is not None and et_ts < cutoff:
            continue
        hold_s = (xt_ts - et_ts).total_seconds()
        out.append({
            "ts": xt_ts.isoformat(),
            "entry_ts": et_ts.isoformat(),
            "_sort_key": et_ts.timestamp(),  # numeric sort, drop before send
            "side": r.get("side"),
            "n_mnq": int(r.get("qty") or 0),
            "entry_px": float(r.get("entry_px") or 0),
            "exit_px": float(r.get("exit_px") or 0),
            "exit_reason": r.get("exit_reason") or "",
            "pnl_usd": float(r.get("pnl") or 0),
            "pnl_pts": 0.0,
            "hold_s": float(hold_s),
        })
    # Sort by real timestamp (not the lexicographic SQL order) so the equity
    # curve walks left-to-right strictly chronologically even if entry_time
    # rows are stored in mixed string formats.
    out.sort(key=lambda d: d["_sort_key"])
    for d in out:
        d.pop("_sort_key", None)
    return jsonify(out)


@app.route("/api/last_trades")
def api_last_trades():
    """Last 100 trades for the live dashboard table + chart. Filtered to
    trades after the most recent reset so the Trades tab never shows
    pre-reset history.

    Pass ?source=broker to read from Tradovate FillPairs (broker reality)
    instead of paper. The Trades tab uses this so the user sees what
    the BROKER actually executed.
    """
    source = (request.args.get("source") or "paper").lower()
    if source == "broker":
        # Strict isolation: in broker mode never substitute paper rows.
        try:
            from bot.tradovate_client import get_session
            sess = get_session()
            if sess.is_configured:
                acct_id = sess.get_account_id()
                if acct_id is not None:
                    rows = _collect_broker_trades(sess, acct_id, limit=10_000)
                    # Honour the reset cutoff so the live Trades tab
                    # only shows post-reset broker activity. The actual
                    # Tradovate cash balance is unaffected (it's read
                    # straight from /cashBalance, not from this list).
                    rows = _filter_trades_since_reset(rows)
                    return jsonify(list(reversed(rows))[:100])
        except Exception as e:
            logger.warning(f"broker last_trades fallback: {e!r}")
        return jsonify([])
    rows = persistence.load_trades(limit=2000)
    return jsonify(_filter_trades_since_reset(rows)[:100])


@app.route("/api/export/<period>")
def api_export(period):
    """Self-contained printable HTML trade report. period in
    {day,week,month,all}. Browser can save-as-PDF. The report includes
    aggregate stats (P&L, WR, RR, PF, max DD, hold-time distribution)
    and a full trade-by-trade ledger. Always filtered to trades since
    lucid_account.started_at (current strategy version only)."""
    import pandas as _pd
    from datetime import timedelta as _td
    now_utc = datetime.now(timezone.utc)
    # Period -> cutoff datetime (None = no period cap)
    period = (period or "all").lower()
    if period == "day":
        period_cut = now_utc - _td(days=1)
    elif period == "week":
        period_cut = now_utc - _td(days=7)
    elif period == "month":
        period_cut = now_utc - _td(days=30)
    elif period == "all":
        period_cut = None
    else:
        return ("unknown period", 400)
    # Strategy-deploy cutoff (always applied)
    deploy_cut = None
    try:
        from bot.account_ctx import data_dir as _acct_dir; lp = _acct_dir() / "lucid_account.json"
        if lp.exists():
            ls = json.loads(lp.read_text())
            sa = ls.get("started_at")
            if sa:
                deploy_cut = _pd.Timestamp(sa)
                if deploy_cut.tz is None:
                    deploy_cut = deploy_cut.tz_localize("UTC")
                else:
                    deploy_cut = deploy_cut.tz_convert("UTC")
    except Exception:
        pass
    # Load + filter
    raw = persistence.load_trades(limit=100_000, only_closed=True)
    trades = []
    for r in raw:
        et = r.get("entry_time"); xt = r.get("exit_time")
        if not et or not xt: continue
        try:
            et_ts = _pd.Timestamp(et)
            xt_ts = _pd.Timestamp(xt)
            if et_ts.tz is None: et_ts = et_ts.tz_localize("UTC")
            else: et_ts = et_ts.tz_convert("UTC")
            if xt_ts.tz is None: xt_ts = xt_ts.tz_localize("UTC")
            else: xt_ts = xt_ts.tz_convert("UTC")
        except Exception:
            continue
        if deploy_cut is not None and et_ts < deploy_cut: continue
        if period_cut is not None and et_ts < period_cut: continue
        trades.append({
            "entry_ts": et_ts, "exit_ts": xt_ts,
            "hold_s": (xt_ts - et_ts).total_seconds(),
            "side": r.get("side"),
            "qty": int(r.get("qty") or 0),
            "entry_px": float(r.get("entry_px") or 0),
            "exit_px": float(r.get("exit_px") or 0),
            "stop_px": float(r.get("stop_px") or 0),
            "target_px": float(r.get("target_px") or 0),
            "exit_reason": r.get("exit_reason") or "",
            "pnl": float(r.get("pnl") or 0),
            "commission": float(r.get("commission") or 0),
        })
    trades.sort(key=lambda t: t["entry_ts"])
    # Aggregate stats
    n = len(trades)
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] < 0]
    pnl_total = sum(t["pnl"] for t in trades)
    pnl_wins = sum(t["pnl"] for t in wins)
    pnl_losses = sum(t["pnl"] for t in losses)
    wr = (len(wins) / n * 100) if n else 0
    avg_w = (pnl_wins / len(wins)) if wins else 0
    avg_l = (pnl_losses / len(losses)) if losses else 0
    rr = (abs(avg_w / avg_l)) if avg_l else 0
    pf = (abs(pnl_wins / pnl_losses)) if pnl_losses else 0
    # Cumulative + max DD
    cum = 0.0; peak = 0.0; max_dd = 0.0
    for t in trades:
        cum += t["pnl"]
        if cum > peak: peak = cum
        if peak - cum > max_dd: max_dd = peak - cum
    # Period label
    period_label = {
        "day":   "Last 24 hours",
        "week":  "Last 7 days",
        "month": "Last 30 days",
        "all":   "All trades (since strategy deploy)",
    }.get(period, period)
    # Render HTML
    html = _render_export_html(
        trades=trades, n=n, wins=wins, losses=losses,
        pnl_total=pnl_total, wr=wr, rr=rr, pf=pf, max_dd=max_dd,
        avg_w=avg_w, avg_l=avg_l, period_label=period_label,
        generated_at=now_utc, deploy_cut=deploy_cut,
    )
    filename = f"hftbot_trades_{period}_{now_utc.strftime('%Y%m%d_%H%M')}.html"
    from flask import Response
    return Response(
        html, mimetype="text/html",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _render_export_html(trades, n, wins, losses, pnl_total, wr, rr, pf,
                        max_dd, avg_w, avg_l, period_label, generated_at,
                        deploy_cut) -> str:
    """Build the printable trade-report HTML. Self-contained (no CDN)."""
    def _row(t):
        et = t["entry_ts"].strftime("%Y-%m-%d %H:%M:%S UTC")
        xt = t["exit_ts"].strftime("%H:%M:%S")
        hold = f"{t['hold_s']:.0f}s" if t["hold_s"] < 60 else f"{t['hold_s']/60:.1f}m"
        pnl_class = "pos" if t["pnl"] > 0 else "neg" if t["pnl"] < 0 else ""
        side_class = "long" if t["side"] == "LONG" else "short"
        return (f"<tr>"
                f"<td class='mono'>{et}</td>"
                f"<td class='mono'>{xt}</td>"
                f"<td class='hold'>{hold}</td>"
                f"<td class='{side_class}'>{t['side']}</td>"
                f"<td>{t['qty']}</td>"
                f"<td class='mono'>{t['entry_px']:.2f}</td>"
                f"<td class='mono'>{t['stop_px']:.2f}</td>"
                f"<td class='mono'>{t['target_px']:.2f}</td>"
                f"<td class='mono'>{t['exit_px']:.2f}</td>"
                f"<td>{t['exit_reason']}</td>"
                f"<td class='mono {pnl_class}'>${t['pnl']:+,.2f}</td>"
                f"</tr>")
    rows = "\n".join(_row(t) for t in trades) or "<tr><td colspan='11' style='text-align:center;color:#888'>No trades in this period.</td></tr>"
    deploy_str = deploy_cut.strftime("%Y-%m-%d %H:%M UTC") if deploy_cut else "—"
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8" />
<title>HFTBot Trade Report — {period_label}</title>
<style>
  @media print {{ body {{ background: white; color: black; }} .no-print {{ display: none; }} }}
  body {{ font-family: -apple-system, system-ui, sans-serif; background: #0f1422;
         color: #d4dae5; max-width: 1200px; margin: 0 auto; padding: 24px;
         font-size: 13px; }}
  h1 {{ color: #22d39a; margin: 0 0 4px 0; font-size: 22px; }}
  h2 {{ color: #d4dae5; margin: 22px 0 8px 0; font-size: 15px;
        border-bottom: 1px solid #2a3344; padding-bottom: 4px; }}
  .meta {{ color: #8a93a6; font-size: 11px; margin-bottom: 18px; }}
  .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px;
           margin-bottom: 18px; }}
  .stat {{ background: #161d2b; border: 1px solid #1f2733; border-radius: 8px;
           padding: 10px 12px; }}
  .stat-label {{ font-size: 10px; color: #8a93a6; text-transform: uppercase;
                 letter-spacing: 0.6px; }}
  .stat-value {{ font-size: 18px; font-weight: 700; margin-top: 4px;
                 font-variant-numeric: tabular-nums; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
  th, td {{ padding: 4px 6px; text-align: right;
           border-bottom: 1px solid rgba(255,255,255,0.05); }}
  th {{ background: #161d2b; color: #8a93a6; text-transform: uppercase;
        font-size: 10px; letter-spacing: 0.5px; }}
  th:first-child, td:first-child {{ text-align: left; }}
  td:nth-child(4) {{ text-align: left; }}
  td:nth-child(10) {{ text-align: left; }}
  .mono {{ font-family: 'SF Mono', Menlo, Consolas, monospace;
           font-variant-numeric: tabular-nums; }}
  .pos {{ color: #22d39a; }} .neg {{ color: #ff5470; }}
  .long {{ color: #22d39a; font-weight: 600; }}
  .short {{ color: #ff5470; font-weight: 600; }}
  .hold {{ color: #8a93a6; }}
</style></head><body>
<h1>HFTBot Trade Report</h1>
<div class="meta">
  Period: <b>{period_label}</b> &middot;
  Generated: {generated_at.strftime("%Y-%m-%d %H:%M UTC")} &middot;
  Strategy deploy cutoff: {deploy_str}
</div>
<div class="grid">
  <div class="stat"><div class="stat-label">Trades</div><div class="stat-value">{n}</div></div>
  <div class="stat"><div class="stat-label">Win rate</div><div class="stat-value">{wr:.1f}%</div></div>
  <div class="stat"><div class="stat-label">Net P&L</div>
    <div class="stat-value {'pos' if pnl_total>=0 else 'neg'}">${pnl_total:+,.2f}</div></div>
  <div class="stat"><div class="stat-label">Profit factor</div>
    <div class="stat-value">{pf:.2f}</div></div>
  <div class="stat"><div class="stat-label">R:R realised</div>
    <div class="stat-value">{rr:.2f}</div></div>
  <div class="stat"><div class="stat-label">Wins / Losses</div>
    <div class="stat-value">{len(wins)} / {len(losses)}</div></div>
  <div class="stat"><div class="stat-label">Avg win / loss</div>
    <div class="stat-value" style="font-size:14px">${avg_w:+,.2f} / ${avg_l:+,.2f}</div></div>
  <div class="stat"><div class="stat-label">Max drawdown</div>
    <div class="stat-value neg">-${max_dd:,.0f}</div></div>
</div>
<h2>Trades ({n})</h2>
<table>
<thead><tr>
  <th>Entry (UTC)</th><th>Exit</th><th>Hold</th><th>Side</th><th>Qty</th>
  <th>Entry</th><th>Stop</th><th>Target</th><th>Exit</th><th>Reason</th><th>P&amp;L</th>
</tr></thead>
<tbody>
{rows}
</tbody></table>
</body></html>"""


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


# ===========================================================================
# Downloads -- one endpoint, many kinds. Sets Content-Disposition so the
# browser downloads the file rather than displaying it. Designed so the
# user can `curl -O` or click a button on the dashboard and get the same
# artifact. The "bundle" kind is the all-in-one diagnostic that pulls
# every other kind together into one JSON.
# ===========================================================================
def _build_health_payload(include_verify: bool = False):
    """The 'I want to know what the bot is doing right now' payload."""
    from bot.account_ctx import data_dir as _acct_dir, get_account
    base = _acct_dir()
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "account": get_account(),
        "snapshot": {},
        "lucid": {},
        "active_trade": None,
        "pending_setups": [],
        "files": {},
        "files_age_s": {},
    }
    # In-memory snapshot
    try:
        snap = persistence.load_dashboard()
        payload["snapshot"] = {
            "ts": snap.get("ts"),
            "cycle": snap.get("cycle"),
            "bars_processed": snap.get("bars_processed"),
            "bars_1m_source": snap.get("bars_1m_source"),
            "signals_fired": snap.get("signals_fired"),
            "signals_blocked": snap.get("signals_blocked"),
            "last_error": snap.get("last_error"),
            "mode": snap.get("mode"),
            "price_ts": snap.get("price_ts"),
            "price": snap.get("price"),
            "htf_trend": snap.get("htf_trend"),
        }
        payload["shadow_engine"] = snap.get("shadow_engine")
        payload["active_trade"] = (snap.get("fib") or {}).get("active_trade")
        payload["pending_setups"] = (snap.get("fib") or {}).get("pending_setups", [])
        payload["lifetime_stats"] = snap.get("lifetime_stats")
    except Exception as e:
        payload["snapshot_error"] = repr(e)
    # Lucid state
    try:
        lp = base / "lucid_account.json"
        if lp.exists():
            payload["lucid"] = json.loads(lp.read_text())
    except Exception as e:
        payload["lucid_error"] = repr(e)
    # File ages (key signal for "is bot alive")
    for fname in ["dashboard_data.json", "lucid_account.json",
                   "paper_trades.db", "live_bars.json",
                   "bot_heartbeat.txt", "bot_crash.txt",
                   "manual_pause.json"]:
        p = base / fname
        if p.exists():
            st = p.stat()
            age = datetime.now(timezone.utc).timestamp() - st.st_mtime
            payload["files"][fname] = {
                "exists": True, "size": st.st_size,
                "age_s": round(age, 1),
                "mtime": datetime.fromtimestamp(st.st_mtime,
                                                  tz=timezone.utc).isoformat(),
            }
        else:
            payload["files"][fname] = {"exists": False}
    # Pause status
    try:
        from bot.account_ctx import get_pause_state
        payload["pause_state"] = get_pause_state()
    except Exception:
        payload["pause_state"] = None
    if include_verify:
        try:
            with app.test_request_context(f"/api/admin/verify_today?account={get_account()}"):
                resp = api_admin_verify_today()
                if isinstance(resp, tuple):
                    body = resp[0].get_json() if hasattr(resp[0], "get_json") else None
                else:
                    body = resp.get_json() if hasattr(resp, "get_json") else None
                payload["verification"] = body
        except Exception as e:
            payload["verification_error"] = repr(e)
    return payload


def _build_config_payload():
    """Strategy params + risk gate config + sanitized env vars."""
    import os as _os
    from bot.account_ctx import get_strategy_params, get_account, _DEFAULT_PARAMS
    out = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "account": get_account(),
        "strategy_params": get_strategy_params(),
        "all_account_params": _DEFAULT_PARAMS,
        "risk_settings": {
            "FIB_AUTO_DLL": _os.environ.get("FIB_AUTO_DLL", "700.0"),
            "default_cooldown_secs": 60,
            "default_max_hold_secs": 600,
            "default_max_wait_secs": 300,
            "min_target_hold_secs": 10,
        },
        "env": {
            "BOT_VERSION":     _os.environ.get("BOT_VERSION", ""),
            "BOT_SHADOW_MODE": _os.environ.get("BOT_SHADOW_MODE", "1"),
            "POLYGON_API":     "set" if _os.environ.get("POLYGON_API") else "missing",
            "ACCOUNTS":        _os.environ.get("ACCOUNTS", "1"),
            "FIB_AUTO_DLL":    _os.environ.get("FIB_AUTO_DLL", "(default)"),
            # NEVER include actual secret values
        },
        "tradovate": {
            "TRADOVATE_LIVE": _os.environ.get("TRADOVATE_LIVE", "false"),
            "credentials_set": all(_os.environ.get(k) for k in
                                    ("TRADOVATE_USERNAME","TRADOVATE_PASSWORD")),
        },
        "traderspost": {
            "TRADERSPOST_LIVE":        _os.environ.get("TRADERSPOST_LIVE", "false"),
            "webhook_url_set":         bool(_os.environ.get("TRADERSPOST_WEBHOOK_URL")),
            "ticker":                  _os.environ.get("TRADERSPOST_TICKER", "MNQ"),
        },
    }
    return out


def _collect_tradovate_snapshot() -> dict:
    """Hit every Tradovate-related diagnostic endpoint in one go and
    return the merged JSON. Used by the bundle download so the user
    can send ONE file that has everything we'd otherwise ask them to
    screenshot one URL at a time."""
    out = {}
    try:
        from bot.tradovate_client import get_session
    except Exception as e:
        return {"error": f"tradovate client import failed: {e!r}"}
    sess = get_session()
    if not sess.is_configured:
        return {"configured": False}

    # Each call wrapped so one failure doesn't kill the whole bundle.
    def _safe(label, fn):
        try:
            out[label] = fn()
        except Exception as e:
            out[label] = {"error": repr(e)}

    _safe("auth_diag", lambda: {
        "configured": True,
        "cluster": ("demo" if os.environ.get("TRADOVATE_DEMO", "true").lower()
                              in ("true", "1", "yes") else "live"),
        "user_id": (sess.get_tokens().user_id if sess.get_tokens() else None),
    })
    _safe("account_list", lambda: sess.account_list())
    _safe("account_id", lambda: sess.get_account_id())
    acct_id = sess.get_account_id()

    if acct_id is not None:
        _safe("cash_balance",
               lambda: sess._rest("POST",
                                    "/cashBalance/getCashBalanceSnapshot",
                                    body={"accountId": int(acct_id)}))
        _safe("cash_balance_history",
               lambda: sess._rest("GET", "/cashBalanceLog/deps",
                                    params={"masterid": int(acct_id)}))
        _safe("position_list",
               lambda: sess._rest("GET", "/position/list"))
        _safe("order_list_raw",
               lambda: sess._rest("GET", "/order/list"))
        _safe("fill_list_raw",
               lambda: sess._rest("GET", "/fill/list"))
        _safe("fill_deps_raw",
               lambda: sess._rest("GET", "/fill/deps",
                                    params={"masterid": int(acct_id)}))
        # Per Tradovate API PDF (entity model section), THESE are the
        # endpoints with ground-truth broker activity. They're the answer
        # to "what really happened on the matching engine".
        #
        # /executionReport/list -- every event the matching engine
        # generated for our orders (New/PartialFill/Fill/Cancelled/
        # Rejected/Expired/...). Contains rejectReason which tells us
        # WHY an order was refused. Without these, we have to guess from
        # ordStatus changes alone.
        _safe("execution_report_list",
               lambda: sess._rest("GET", "/executionReport/list"))
        # /fillPair/list -- round-trip pairs (buyFill + sellFill matched
        # together). buyPrice + sellPrice show actual entry + exit
        # prices for each closed trade. This is what the BROKER's
        # P&L is calculated from -- compare against paper P&L to
        # find the discrepancy.
        _safe("fill_pair_list",
               lambda: sess._rest("GET", "/fillPair/list"))
        # /orderVersion/list -- every Order's current OrderVersion row.
        # Order entity has no price/qty; OrderVersion is where the
        # actual numbers live. Without these, "what price did we
        # actually send?" is unanswerable from the bundle.
        _safe("order_version_list",
               lambda: sess._rest("GET", "/orderVersion/list"))
        # Per-order detail: for each order in order_list_raw, pull the
        # full OrderVersion chain so we can see modifications (initial
        # price -> any cancel-replace -> final). Crucial for spotting
        # cases where Tradovate altered an order after submission.
        try:
            ord_status, ord_list = sess._rest("GET", "/order/list")
            if ord_status == 200 and isinstance(ord_list, list):
                detail = []
                # Cap at most recent 50 orders to avoid massive bundles
                for o in ord_list[-50:]:
                    oid = o.get("id") if isinstance(o, dict) else None
                    if not oid:
                        continue
                    try:
                        vs, vd = sess._rest(
                            "GET", "/orderVersion/deps",
                            params={"masterid": int(oid)})
                        detail.append({
                            "order_id": oid,
                            "order": o,
                            "version_http": vs,
                            "versions": vd if isinstance(vd, list) else [],
                        })
                    except Exception as e:
                        detail.append({"order_id": oid, "error": repr(e)})
                out["per_order_versions"] = detail
        except Exception as e:
            out["per_order_versions"] = {"error": repr(e)}
        _safe("risk_status",
               lambda: sess._rest("GET", "/accountRiskStatus/list"))
        # Contract spec for the trading symbol. The bot's find_contract()
        # resolves root -> front-month entity (tick size, value, status)
        # via /contract/suggest. /contract/find?name=MNQ alone returns
        # 404 because it wants the full contract name (e.g. MNQM6).
        try:
            sym_root = os.environ.get("POLYGON_CONTRACT", "MNQ")
            resolved = sess.find_contract(sym_root)
            out["contract_resolved"] = resolved
            if resolved and resolved.get("name"):
                # Also pull tick/value spec via /contract/item
                try:
                    spec_status, spec_data = sess._rest(
                        "GET", "/contract/item",
                        params={"id": int(resolved["id"])})
                    out["contract_spec"] = {"http": spec_status,
                                              "data": spec_data}
                except Exception as e:
                    out["contract_spec"] = {"error": repr(e)}
        except Exception as e:
            out["contract_resolved"] = {"error": repr(e)}

    # Bot's own audit log of every order placement attempt. Includes
    # the EXACT request body sent, raw response, parsed result, and
    # bracket verification with mismatch flags. This is the single
    # most useful artifact for diagnosing entry/bracket bugs.
    try:
        from bot.tradovate_orders import get_audit_log
        out["bot_audit_log"] = get_audit_log()
    except Exception as e:
        out["bot_audit_log"] = {"error": repr(e)}

    # REST latency stats per endpoint. Catches network hiccups that
    # explain why an entry slipped (placeoso took 800ms -> price moved
    # 1pt by the time the LIMIT was on the book).
    try:
        from bot.tradovate_client import get_latency_stats
        out["rest_latency"] = get_latency_stats()
    except Exception as e:
        out["rest_latency"] = {"error": repr(e)}

    return out


def _build_paper_broker_forensics(tradovate_snap: dict) -> dict:
    """The most important diagnostic. Detects every mechanism that
    could cause paper-vs-broker P&L to diverge:

      1. STALE FILLS: broker LIMIT filled AFTER paper had closed the
         trade. Paper books P&L without this trade; broker takes a
         fresh stale-position outcome.

      2. MISSED ENTRIES: paper booked a trade but broker's LIMIT
         never filled at all (cancelled, expired, or still working).
         Paper takes phantom P&L; broker stays flat for that signal.

      3. TARGET MISSES: paper detected target on a wick. Broker
         bracket LIMIT didn't fill because bid/ask never reached the
         level. Bracket sat, then stop fired instead.

      4. STOP SLIPPAGE: broker's stop fill price differs from paper's
         expected stop_px by more than the modeled PAPER_STOP_SLIP_PTS.

      5. BRACKET REJECTIONS: bracket children rejected by Tradovate
         (InvalidPrice etc.) -- position ran with broken protection.

      6. EXTRA BROKER FILLS: broker fills that don't correspond to
         any paper trade.

      7. TIME-TO-FILL: histogram of how long LIMITs took to fill.

      8. TARGET CHASE EVENTS: every time the bot forced a broker
         market close because paper detected target.

    Outputs a 'findings' list with each detected mechanism + the
    specific trades it affected + the dollar delta.
    """
    findings = []
    summary = {
        "stale_fills_detected": 0,
        "missed_entries_detected": 0,
        "target_misses_detected": 0,
        "stop_slip_excess_detected": 0,
        "bracket_rejections": 0,
        "extra_broker_fills": 0,
        "target_chase_events": 0,
        "stale_limit_cancels": 0,
        "total_estimated_leak": 0.0,
    }

    def _list_of(key):
        v = tradovate_snap.get(key)
        if isinstance(v, tuple) and len(v) == 2:
            v = v[1]
        return v if isinstance(v, list) else []

    fills = _list_of("fill_list_raw")
    orders = _list_of("order_list_raw")
    exec_reports = _list_of("execution_report_list")
    audit = tradovate_snap.get("bot_audit_log") or []
    if not isinstance(audit, list):
        audit = []

    # Index data
    order_by_id = {int(o["id"]): o for o in orders
                    if isinstance(o, dict) and o.get("id") is not None}
    fills_by_order = {}
    for f in fills:
        if isinstance(f, dict) and f.get("orderId") is not None:
            fills_by_order.setdefault(int(f["orderId"]), []).append(f)

    # === Finding 5: bracket rejections ===
    for er in exec_reports:
        if not isinstance(er, dict):
            continue
        if er.get("execType") == "Rejected":
            findings.append({
                "type": "bracket_rejection",
                "severity": "HIGH",
                "ts": er.get("timestamp"),
                "order_id": er.get("orderId"),
                "reason": er.get("rejectReason"),
                "action": er.get("action"),
                "impact_usd": None,
                "description": "Bracket child rejected by Tradovate. "
                                "Position ran with broken protection."
            })
            summary["bracket_rejections"] += 1

    # === Finding 1+2: stale fills + missed entries via audit log ===
    # Pull paper trades and pair with audit entries by setup_ref.
    try:
        paper_rows = _filter_trades_since_reset(
            persistence.load_trades(limit=10_000, only_closed=True))
    except Exception as e:
        paper_rows = []
        findings.append({
            "type": "_diagnostic_error",
            "severity": "INFO",
            "description": f"failed to load paper trades: {e!r}"})

    # Index audit entries by setup_ref
    audit_by_ref = {}
    for a in audit:
        if isinstance(a, dict) and a.get("setup_ref"):
            audit_by_ref[a["setup_ref"]] = a

    # For each paper trade, check what happened on broker
    paper_close_times = {}
    for p in paper_rows:
        ref_pat = None
        try:
            tid = p.get("id")
            ets = p.get("entry_time")
            if tid and ets:
                ets_secs = int(pd.Timestamp(ets).timestamp())
                # The bot's setup_ref format is "acct1_<id>_<epoch_secs>"
                # but timing may not match exactly. We'll try suffix match.
                ref_pat = f"_{tid}_{ets_secs}"
            elif tid:
                ref_pat = f"_{tid}_"
        except Exception:
            pass
        # Match audit entries
        matched_audit = None
        if ref_pat:
            for ref, a in audit_by_ref.items():
                if ref_pat in ref:
                    matched_audit = a
                    break
        if not matched_audit:
            continue

        # Check what the broker order did
        parent_oid = matched_audit.get("parsed_order_id")
        if not parent_oid:
            continue
        parent_order = order_by_id.get(int(parent_oid))
        if not parent_order:
            continue

        parent_status = parent_order.get("ordStatus")
        parent_fills = fills_by_order.get(int(parent_oid), [])

        if parent_status in ("Canceled", "Rejected") and not parent_fills:
            findings.append({
                "type": "missed_entry",
                "severity": "MEDIUM",
                "setup_ref": matched_audit.get("setup_ref"),
                "paper_entry_px": p.get("entry_px"),
                "paper_exit_px": p.get("exit_px"),
                "paper_pnl": p.get("pnl"),
                "parent_status": parent_status,
                "impact_usd": -float(p.get("pnl") or 0),
                "description": (
                    f"Paper booked trade ({p.get('side')} pnl=${p.get('pnl')}) "
                    f"but broker LIMIT never filled (status={parent_status}). "
                    f"Paper P&L is phantom for this trade."),
            })
            summary["missed_entries_detected"] += 1
            summary["total_estimated_leak"] += abs(float(p.get("pnl") or 0))

        if parent_fills:
            try:
                fill_ts = pd.Timestamp(parent_fills[0].get("timestamp"))
                if fill_ts.tz is None:
                    fill_ts = fill_ts.tz_localize("UTC")
                else:
                    fill_ts = fill_ts.tz_convert("UTC")
                paper_exit_ts = pd.Timestamp(p.get("exit_time"))
                if paper_exit_ts.tz is None:
                    paper_exit_ts = paper_exit_ts.tz_localize("UTC")
                else:
                    paper_exit_ts = paper_exit_ts.tz_convert("UTC")
                if fill_ts > paper_exit_ts:
                    # STALE FILL: broker fill happened AFTER paper exited
                    findings.append({
                        "type": "stale_fill",
                        "severity": "HIGH",
                        "setup_ref": matched_audit.get("setup_ref"),
                        "paper_entry_px": p.get("entry_px"),
                        "paper_exit_px": p.get("exit_px"),
                        "paper_pnl": p.get("pnl"),
                        "broker_fill_px": parent_fills[0].get("price"),
                        "fill_lag_s": (fill_ts - paper_exit_ts).total_seconds(),
                        "impact_usd": None,
                        "description": (
                            f"Broker LIMIT filled "
                            f"{(fill_ts - paper_exit_ts).total_seconds():.1f}s "
                            f"AFTER paper had closed the trade. Broker "
                            f"now holds a stale position the strategy "
                            f"doesn't want."),
                    })
                    summary["stale_fills_detected"] += 1
            except Exception:
                pass

    # === Finding 7: LIMIT fill latency ===
    latencies = []
    for a in audit:
        if not isinstance(a, dict) or a.get("kind") != "placeoso":
            continue
        if not a.get("parsed_ok"):
            continue
        parent_oid = a.get("parsed_order_id")
        if not parent_oid:
            continue
        pfills = fills_by_order.get(int(parent_oid), [])
        if not pfills:
            continue
        try:
            submit_ts = a.get("ts")
            first_fill_ts = pd.Timestamp(pfills[0].get("timestamp"))
            if first_fill_ts.tz is None:
                first_fill_ts = first_fill_ts.tz_localize("UTC")
            else:
                first_fill_ts = first_fill_ts.tz_convert("UTC")
            latency_s = first_fill_ts.timestamp() - float(submit_ts)
            latencies.append({
                "setup_ref": a.get("setup_ref"),
                "side": a.get("side"),
                "latency_s": round(latency_s, 3),
                "marketable": a.get("marketable_with_improvement"),
            })
        except Exception:
            pass
    if latencies:
        sorted_lat = sorted(l["latency_s"] for l in latencies)
        n = len(sorted_lat)
        summary["limit_fill_latency"] = {
            "n": n,
            "p50_s": round(sorted_lat[n // 2], 3),
            "p95_s": round(sorted_lat[min(n - 1, int(n * 0.95))], 3),
            "max_s": round(sorted_lat[-1], 3),
            "within_1s": sum(1 for x in sorted_lat if x <= 1.0),
            "within_5s": sum(1 for x in sorted_lat if x <= 5.0),
            "over_30s": sum(1 for x in sorted_lat if x > 30.0),
        }

    # === Finding 8: target chase + stale cancel events from log_tail ===
    try:
        log_path = None
        env_log = os.environ.get("BOT_LOG_FILE")
        if env_log:
            log_path = env_log
        else:
            from bot.fib_main import LOG_PATH
            log_path = str(LOG_PATH)
        if log_path and os.path.exists(log_path):
            with open(log_path, "r", errors="replace") as f:
                # Read last ~200KB
                f.seek(0, 2)
                size = f.tell()
                if size > 200_000:
                    f.seek(size - 200_000)
                lines = f.read().split("\n")
                for line in lines:
                    if "TARGET CHASE" in line:
                        summary["target_chase_events"] += 1
                    if "STALE LIMIT CANCELLED" in line:
                        summary["stale_limit_cancels"] += 1
                    if "FAST FIRE" in line:
                        summary.setdefault("fast_fire_events", 0)
                        summary["fast_fire_events"] += 1
    except Exception:
        pass

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "n_findings": len(findings),
        "findings": findings[:200],   # cap at 200 to keep bundle size sane
        "limit_fill_latency_samples": latencies[-50:],
    }


def _build_diagnostic_extras() -> dict:
    """Bot-internal diagnostic data not tied to broker API: strategy
    decision log, Polygon-vs-Tradovate price diff history, WS connection
    state, tick history, trade timelines, slip self-calibration. Lives
    in its own helper because none of it requires a Tradovate REST
    round-trip."""
    extras = {}
    # Strategy decision log: every setup detected / blocked / fired with
    # full snapshot. This is THE artifact for answering "why didn't the
    # bot trade right now" or "why did it fire that setup".
    try:
        from bot.pullback_strategy import get_decision_log
        extras["strategy_decisions"] = get_decision_log()
    except Exception as e:
        extras["strategy_decisions"] = {"error": repr(e)}
    # Polygon vs Tradovate live price diff. If consistently 0 it means
    # the two feeds agree -- the strategy's decisions translate to
    # broker reality. If non-zero, the strategy is firing on a price
    # the broker never saw.
    try:
        from bot.price_diff_tracker import get_price_diff_history
        extras["price_diff_history"] = get_price_diff_history()
    except Exception as e:
        extras["price_diff_history"] = {"unavailable": repr(e)}
    # Tick history: last N ticks the strategy saw. Lets us replay
    # exactly what the bot decided on.
    try:
        from bot.tick_history import get_tick_history
        extras["tick_history"] = get_tick_history()
    except Exception as e:
        extras["tick_history"] = {"unavailable": repr(e)}
    # Per-trade event timelines. Every state transition (setup detected
    # -> placeoso sent -> broker poll #1/2/3/4 -> filled -> paper closed)
    # timestamped to the setup_ref tag. Pairs with reconciliation rows.
    try:
        from bot.trade_timeline import (
            get_timeline_all, get_summary, get_latency_report)
        extras["trade_timelines"] = get_timeline_all()
        extras["trade_timelines_summary"] = get_summary()
        # Per-trade latency + price-divergence report. Each row carries
        # measured ms-precision delays at each stage (paper signal ->
        # placeoso send -> REST ack -> broker fill, plus the same for
        # the close side) and the entry-price gap between paper and
        # broker. Aggregates at the top show p50/p95/p99 across the
        # session so a single bundle answers "is the broker slow or
        # is it just diverging on a few outliers".
        extras["trade_latency_report"] = get_latency_report()
    except Exception as e:
        extras["trade_timelines"] = {"unavailable": repr(e)}
    # Per-trade tick + decision snapshots. For every paper trade
    # that closed >= 3 min ago, the snapshot worker has stitched
    # together the 3-min-before / 3-min-after tick path, the paper
    # entry / stop / target / exit, the broker placeoso intent, the
    # actual broker fill, and the broker close. Each snapshot is
    # ~5-10 KB and the ring is bounded at the most recent 50 trades.
    try:
        from bot.trade_tick_snapshots import (
            get_snapshots, get_pending_count)
        extras["per_trade_snapshots"] = get_snapshots()
        extras["per_trade_snapshots_pending"] = get_pending_count()
    except Exception as e:
        extras["per_trade_snapshots"] = {"unavailable": repr(e)}
    # Anticipatory pre-submit telemetry (why the pre-rested LIMIT did or
    # didn't get placed on each check). This is the block that makes the
    # missed-winner / never-fired-anticipatory problem provable from one
    # bundle instead of inferred from timelines.
    try:
        snap = persistence.load_dashboard()
        extras["anticipatory_diag"] = snap.get("anticipatory_diag")
        # Exit-path ledger + effective execution knobs (published by the
        # bot alongside anticipatory_diag; see fib_main._publish_dashboard).
        extras["close_path_counts"] = snap.get("close_path_counts")
        extras["exec_knobs"] = snap.get("exec_knobs")
    except Exception as e:
        extras["anticipatory_diag"] = {"unavailable": repr(e)}
    # FILL ARCHIVE. Tradovate's /fill/list is trade-date-scoped, so a
    # bundle taken after the 5pm CT roll (or on a holiday) has NO fills
    # for the day just traded -- the 2026-07-04 bundle couldn't verify
    # July 3's broker P&L at all. The user-WS persists every fill to a
    # rolling JSONL archive (bot/tradovate_user_ws._archive_fill); embed
    # the last 3 days so per-trade broker P&L is always reconstructable
    # from the bundle alone (join on orderId against the timelines).
    try:
        import json as _json
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz
        from bot.account_ctx import data_dir as _acct_dd
        _rows = []
        _base = _acct_dd()
        for _d in range(3):
            _day = (_dt.now(_tz.utc) - _td(days=_d)).strftime("%Y%m%d")
            _f = _base / f"fill_archive_{_day}.jsonl"
            if not _f.exists():
                continue
            for _line in _f.read_text().splitlines():
                try:
                    _rows.append(_json.loads(_line))
                except Exception:
                    continue
        # Dedupe by fill id (archives written before the dedupe fix, or
        # replayed on reconnect, contain the same fill 2+ times; keep
        # the first row). Position math on duplicated fills fabricates
        # phantom netPos stacks.
        _seen_ids = set()
        _ded = []
        for _r in _rows:
            _fid = _r.get("id")
            if _fid is not None and _fid in _seen_ids:
                continue
            if _fid is not None:
                _seen_ids.add(_fid)
            _ded.append(_r)
        _rows = _ded
        # Newest last; cap so a hyperactive week can't bloat the bundle.
        extras["fill_archive"] = _rows[-6000:]
        extras["fill_archive_count"] = len(_rows)
    except Exception as e:
        extras["fill_archive"] = {"unavailable": repr(e)}
    # Bot process uptime + cycle counters from the live snapshot.
    try:
        snap = persistence.load_dashboard()
        extras["bot_runtime"] = {
            "cycle": snap.get("cycle"),
            "bars_processed": snap.get("bars_processed"),
            "signals_fired": snap.get("signals_fired"),
            "signals_blocked": snap.get("signals_blocked"),
            "last_error": snap.get("last_error"),
            "polygon_ws": snap.get("polygon_ws"),
            "tradovate_md": snap.get("tradovate_md"),
            "ws_tick_bars": snap.get("ws_tick_bars"),
        }
    except Exception as e:
        extras["bot_runtime"] = {"error": repr(e)}
    # Process info: pid, memory, started-at. Helps spot OOM kills /
    # restarts.
    try:
        import os as _os
        import resource as _resource
        import time as _time
        ru = _resource.getrusage(_resource.RUSAGE_SELF)
        extras["process"] = {
            "pid": _os.getpid(),
            "rss_kb": ru.ru_maxrss,
            "user_cpu_s": ru.ru_utime,
            "sys_cpu_s": ru.ru_stime,
            "now": _time.time(),
        }
    except Exception as e:
        extras["process"] = {"error": repr(e)}
    # Slip self-calibration: compute the actual avg stop-fill slip from
    # broker FillPairs and recommend a PAPER_STOP_SLIP_PTS value. Don't
    # auto-apply -- show on dashboard so the user decides.
    try:
        extras["slip_calibration"] = _build_slip_calibration()
    except Exception as e:
        extras["slip_calibration"] = {"error": repr(e)}
    # Recent log tail. Pulled from the bot's logger if a file handler
    # is configured, otherwise from /tmp/bot.log if it exists. Capped
    # at ~50 KB so the bundle stays reasonable.
    try:
        extras["log_tail"] = _read_log_tail(50_000)
    except Exception as e:
        extras["log_tail"] = {"error": repr(e)}
    # Tradovate user WebSocket state + recent real-time events
    # (ExecutionReport, Fill, Order, Position, CashBalance updates).
    # If this is healthy, fill detection latency drops from ~500ms
    # (REST poll) to <100ms (WS push).
    try:
        from bot.tradovate_user_ws import get_user_ws
        ws = get_user_ws()
        if ws is not None:
            extras["tradovate_user_ws"] = {
                "health": ws.health(),
                "recent_events": ws.get_recent_events(100),
                "recent_fills": ws.get_fills(50),
                "recent_exec_reports": ws.get_exec_reports(50),
            }
        else:
            extras["tradovate_user_ws"] = {"unavailable": "no ws instance"}
    except Exception as e:
        extras["tradovate_user_ws"] = {"error": repr(e)}
    # Tradovate bar fetch stats -- powers the Polygon-cancel readiness
    # card and tells us whether Tradovate is reliable enough yet.
    try:
        from bot.tradovate_bars import get_stats as _bar_stats, health as _bar_h
        extras["tradovate_bars"] = {
            "stats": _bar_stats(),
            "health": _bar_h(),
        }
    except Exception as e:
        extras["tradovate_bars"] = {"error": repr(e)}
    # Auto consistency check: scan the bundle for known divergence
    # patterns and surface them as actionable findings.
    try:
        extras["consistency_check"] = _run_consistency_check(extras)
    except Exception as e:
        extras["consistency_check"] = {"error": repr(e)}
    return extras


def _run_consistency_check(extras: dict) -> dict:
    """Scan the diagnostic data for known divergence patterns. Returns
    a list of findings the user (and the assistant) can act on without
    having to manually inspect the whole bundle. RED flags are
    actionable, AMBER flags are heuristics, GREEN flags are good
    confirmations.
    """
    findings = []

    def _add(level: str, code: str, msg: str, **detail):
        findings.append({"level": level, "code": code,
                          "message": msg, **detail})

    # ---- Price diff ----
    pd_hist = extras.get("price_diff_history") or {}
    if isinstance(pd_hist, dict):
        if pd_hist.get("n", 0) >= 50:
            abs_mean = pd_hist.get("abs_mean", 0.0)
            p95 = pd_hist.get("p95", 0.0)
            if abs(abs_mean) > 0.5:
                _add("RED", "price_diff_high",
                     f"Polygon vs Tradovate mean diff = {abs_mean}pt "
                     f"(p95 {p95}pt). Strategy may fire on prices "
                     f"broker never sees.")
            elif abs(abs_mean) > 0.15:
                _add("AMBER", "price_diff_moderate",
                     f"Polygon vs Tradovate mean diff = {abs_mean}pt.")
            else:
                _add("GREEN", "price_diff_ok",
                     f"Polygon vs Tradovate aligned (abs_mean {abs_mean}pt)")

    # ---- Slip calibration ----
    slip = extras.get("slip_calibration") or {}
    if isinstance(slip, dict) and slip.get("n_samples"):
        rec = slip.get("recommended_PAPER_STOP_SLIP_PTS")
        cur = slip.get("current_env_value")
        if rec is not None and cur is not None:
            if abs(rec - cur) > 0.25:
                _add("AMBER", "slip_recalibrate",
                     f"Observed avg stop slip = {rec}pt but env says "
                     f"{cur}pt. Update PAPER_STOP_SLIP_PTS.")
            else:
                _add("GREEN", "slip_aligned",
                     f"PAPER_STOP_SLIP_PTS ({cur}) matches observed "
                     f"({rec})")

    # ---- WebSocket health ----
    ws_state = extras.get("tradovate_user_ws") or {}
    if isinstance(ws_state, dict):
        h = ws_state.get("health") or {}
        if h.get("connected") and h.get("subscribed"):
            _add("GREEN", "user_ws_live",
                 f"User WS connected, {h.get('frames_seen', 0)} frames "
                 f"seen.")
        elif ws_state.get("unavailable"):
            _add("AMBER", "user_ws_unavailable",
                 "User WS not initialized -- fills polled by REST "
                 "(higher latency).")
        else:
            _add("AMBER", "user_ws_disconnected",
                 f"User WS not connected: last_error={h.get('last_error')!r}")

    # ---- REST latency ----
    runtime = extras.get("bot_runtime") or {}
    poly = (runtime.get("polygon_ws") or {}) if isinstance(runtime, dict) else {}
    if isinstance(poly, dict):
        if poly.get("connected") is False:
            _add("RED", "polygon_ws_down",
                 "Polygon WS disconnected.")

    # ---- Decision log ----
    decisions = extras.get("strategy_decisions") or []
    if isinstance(decisions, list):
        blocks = [d for d in decisions if d.get("event") == "entry_blocked"]
        if blocks:
            from collections import Counter
            reasons = Counter(d.get("reason") for d in blocks)
            top = reasons.most_common(3)
            _add("AMBER", "entries_blocked",
                 f"{len(blocks)} blocked entries in log. Top reasons: "
                 f"{top}")

    # ---- Process ----
    proc = extras.get("process") or {}
    if isinstance(proc, dict) and isinstance(proc.get("rss_kb"), (int, float)):
        rss_mb = proc["rss_kb"] / 1024
        if rss_mb > 1500:
            _add("AMBER", "high_memory",
                 f"Bot RSS = {rss_mb:.1f} MB -- watch for OOM.")

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "n_findings": len(findings),
        "by_level": {
            lvl: sum(1 for f in findings if f["level"] == lvl)
            for lvl in ("RED", "AMBER", "GREEN")
        },
        "findings": findings,
    }


def _read_log_tail(max_bytes: int) -> dict:
    """Best-effort read of the last `max_bytes` of the bot's log file.

    Resolution order:
      1. BOT_LOG_FILE env var
      2. fib_main.LOG_PATH (the actual handler target)
      3. Common Railway / local paths
    """
    import pathlib
    candidates = [os.environ.get("BOT_LOG_FILE")]
    try:
        from bot.fib_main import LOG_PATH as _bot_log_path
        candidates.append(str(_bot_log_path))
    except Exception:
        pass
    # If a base log file is present + rotation backups exist, also
    # surface the most recent backup so we don't lose history that
    # just rotated out moments before the bundle was generated.
    candidates += [
        "/app/data/bot.log",
        "/app/data/bot_fib.log",
        str(ROOT.parent / "logs" / "bot_fib.log"),
        "/tmp/bot.log",
        "/tmp/hftbot.log",
        str(ROOT.parent / "bot.log"),
    ]
    seen = set()
    for c in candidates:
        if not c or c in seen:
            continue
        seen.add(c)
        p = pathlib.Path(c)
        if not p.exists():
            continue
        try:
            size = p.stat().st_size
            with p.open("rb") as f:
                if size > max_bytes:
                    f.seek(size - max_bytes)
                data = f.read().decode("utf-8", errors="replace")
            # Look for sibling rotation files for additional context
            rotation_siblings = []
            for i in range(1, 5):
                rp = pathlib.Path(f"{c}.{i}")
                if rp.exists():
                    rotation_siblings.append({
                        "path": str(rp),
                        "size": rp.stat().st_size,
                    })
            return {"path": str(p), "bytes": len(data),
                     "truncated": size > max_bytes,
                     "rotation_siblings": rotation_siblings,
                     "tail": data}
        except Exception as e:
            return {"path": str(p), "error": repr(e)}
    return {"unavailable": "no log file found",
            "checked_paths": [c for c in candidates if c]}


def _build_slip_calibration() -> dict:
    """Read actual broker fills and estimate the avg stop-fill slip.
    The dashboard surfaces this as a recommendation -- the user decides
    whether to update PAPER_STOP_SLIP_PTS to match.
    """
    out = {"ts": datetime.now(timezone.utc).isoformat()}
    # Pull paper trades (with stop_px) and try to pair with broker fills
    paper = _filter_trades_since_reset(persistence.load_trades(
        limit=10_000, only_closed=True))
    stop_trades = [t for t in paper if t.get("exit_reason") == "stop"]
    out["paper_stop_count"] = len(stop_trades)
    # Get broker fills from a fresh tradovate snapshot
    try:
        snap = _collect_tradovate_snapshot()
    except Exception as e:
        out["error"] = f"snap failed: {e!r}"
        return out

    def _list_of(key):
        v = snap.get(key)
        if isinstance(v, tuple) and len(v) == 2:
            v = v[1]
        return v if isinstance(v, list) else []

    fills = _list_of("fill_list_raw")
    if not fills:
        out["unavailable"] = "no broker fills yet"
        return out
    # Match by time window (within 60s of paper exit_time)
    slips = []
    for t in stop_trades:
        try:
            et_dt = pd.Timestamp(t["exit_time"])
            if et_dt.tz is None:
                et_dt = et_dt.tz_localize("UTC")
            else:
                et_dt = et_dt.tz_convert("UTC")
        except Exception:
            continue
        stop_px = float(t.get("stop_px") or 0)
        side = (t.get("side") or "").upper()
        if not stop_px or side not in ("LONG", "SHORT"):
            continue
        # Find broker fill nearest in time
        for f in fills:
            if not isinstance(f, dict):
                continue
            fts = f.get("timestamp")
            try:
                fts_dt = pd.Timestamp(fts)
                if fts_dt.tz is None:
                    fts_dt = fts_dt.tz_localize("UTC")
                else:
                    fts_dt = fts_dt.tz_convert("UTC")
                if abs((fts_dt - et_dt).total_seconds()) > 60:
                    continue
            except Exception:
                continue
            fpx = f.get("price")
            if fpx is None:
                continue
            # For LONG stop: broker SELLS at fpx <= stop_px (slip = stop - fpx)
            # For SHORT stop: broker BUYS at fpx >= stop_px (slip = fpx - stop)
            if side == "LONG":
                slips.append(float(stop_px) - float(fpx))
            else:
                slips.append(float(fpx) - float(stop_px))
            break
    if not slips:
        out["unavailable"] = "no matchable stop fills yet"
        return out
    slips.sort()
    n = len(slips)
    mean = sum(slips) / n
    out.update({
        "n_samples": n,
        "mean_slip_pts": round(mean, 4),
        "median_slip_pts": round(slips[n // 2], 4),
        "p95_slip_pts": round(slips[min(n - 1, int(n * 0.95))], 4),
        "min_slip_pts": round(slips[0], 4),
        "max_slip_pts": round(slips[-1], 4),
        "recommended_PAPER_STOP_SLIP_PTS": round(max(0.0, mean), 2),
        "current_env_value": float(
            os.environ.get("PAPER_STOP_SLIP_PTS", "0.5")),
    })
    return out


def _build_code_state_payload():
    """Git SHA + hash of every Python file in bot/ and engine/ so I can
    tell if anyone manually edited live code, and identify regressions."""
    import hashlib
    import subprocess
    out = {"ts": datetime.now(timezone.utc).isoformat(),
            "git_sha": None, "git_dirty": None, "branch": None,
            "files": {}, "python_version": None}
    # Railway/Heroku-style deploys often strip the git binary AND the
    # .git directory, but the deploy SHA is exposed via env vars.
    # Try those first, then fall back to reading .git/HEAD directly
    # (Docker images sometimes have .git without the binary).
    for env_key in ("RAILWAY_GIT_COMMIT_SHA", "SOURCE_VERSION",
                     "HEROKU_SLUG_COMMIT", "GIT_COMMIT", "COMMIT_SHA"):
        if os.environ.get(env_key):
            out["git_sha"] = os.environ[env_key]
            out["git_sha_source"] = f"env:{env_key}"
            break
    for env_key in ("RAILWAY_GIT_BRANCH", "HEROKU_BRANCH", "GIT_BRANCH",
                     "BRANCH"):
        if os.environ.get(env_key):
            out["branch"] = os.environ[env_key]
            break
    if not out.get("git_sha"):
        try:
            out["git_sha"] = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=str(ROOT.parent),
                stderr=subprocess.DEVNULL).decode().strip()
            out["git_sha_source"] = "git_cmd"
        except Exception:
            pass
    if not out.get("git_sha"):
        # Last resort: read .git/HEAD ourselves
        try:
            head_path = ROOT.parent / ".git" / "HEAD"
            if head_path.exists():
                head = head_path.read_text().strip()
                if head.startswith("ref:"):
                    ref = head.split(" ", 1)[1].strip()
                    ref_path = ROOT.parent / ".git" / ref
                    if ref_path.exists():
                        out["git_sha"] = ref_path.read_text().strip()
                        out["branch"] = ref.replace("refs/heads/", "")
                        out["git_sha_source"] = "head_file"
                else:
                    out["git_sha"] = head
                    out["git_sha_source"] = "detached_head"
        except Exception:
            pass
    if not out.get("branch"):
        try:
            out["branch"] = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(ROOT.parent),
                stderr=subprocess.DEVNULL).decode().strip()
        except Exception:
            pass
    try:
        st = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=str(ROOT.parent),
            stderr=subprocess.DEVNULL).decode().strip()
        out["git_dirty"] = bool(st)
        out["git_dirty_files"] = [line[3:] for line in st.split("\n") if line]
    except Exception:
        pass
    import sys as _sys
    out["python_version"] = _sys.version
    # Hash each .py file in production paths
    for sub in ("bot", "engine", "dashboard"):
        base = ROOT.parent / sub
        if not base.exists():
            continue
        for p in sorted(base.rglob("*.py")):
            try:
                h = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
                rel = str(p.relative_to(ROOT.parent))
                out["files"][rel] = {"sha256_16": h, "size": p.stat().st_size}
            except Exception:
                pass
    return out


def _build_trades_csv():
    """All trades since reset cutoff, as CSV. Suitable for spreadsheet."""
    import csv
    import io
    rows = _filter_trades_since_reset(persistence.load_trades(limit=100_000,
                                                              only_closed=True))
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=[
        "entry_time", "exit_time", "side", "qty",
        "entry_px", "stop_px", "target_px", "exit_px",
        "exit_reason", "pnl", "commission", "signal_name",
        "ml_decision", "vol_regime", "daily_bias", "rr",
    ])
    writer.writeheader()
    for r in rows:
        writer.writerow({k: r.get(k, "") for k in writer.fieldnames})
    return buf.getvalue()


def _build_equity_csv():
    """Cumulative equity curve as CSV. Each row = one trade exit, with
    running P&L. Easy to import into Excel/Google Sheets."""
    import csv
    import io
    rows = sorted(_filter_trades_since_reset(persistence.load_trades(
        limit=100_000, only_closed=True)),
                  key=lambda r: r.get("exit_time") or "")
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["exit_time", "pnl", "cum_pnl", "side", "exit_reason"])
    cum = 0.0
    for r in rows:
        pnl = float(r.get("pnl") or 0)
        cum += pnl
        writer.writerow([r.get("exit_time"), pnl, round(cum, 2),
                          r.get("side"), r.get("exit_reason")])
    return buf.getvalue()


def _build_daily_csv():
    """Per-NY-day P&L breakdown as CSV. Critical for funded-account
    consistency analysis."""
    import csv
    import io
    from collections import defaultdict
    rows = _filter_trades_since_reset(persistence.load_trades(
        limit=100_000, only_closed=True))
    by_day = defaultdict(lambda: {"n":0, "pnl":0.0, "wins":0,
                                    "peak_run":0.0, "trough_run":0.0})
    for r in sorted(rows, key=lambda x: x.get("exit_time") or ""):
        et_str = r.get("exit_time")
        if not et_str:
            continue
        try:
            ts = pd.Timestamp(et_str)
            ts = ts.tz_convert("UTC") if ts.tz is not None else ts.tz_localize("UTC")
            # NY date: 16:00 ET rollover
            from research.signal_filters import NY_TZ
            ny_date = ts.tz_convert(NY_TZ).date().isoformat()
        except Exception:
            continue
        d = by_day[ny_date]
        pnl = float(r.get("pnl") or 0)
        d["n"] += 1
        d["pnl"] += pnl
        if pnl > 0: d["wins"] += 1
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ny_date", "n_trades", "wins", "win_rate", "pnl"])
    for day in sorted(by_day):
        d = by_day[day]
        wr = (d["wins"] / d["n"] * 100) if d["n"] else 0
        writer.writerow([day, d["n"], d["wins"], f"{wr:.1f}%", round(d["pnl"], 2)])
    return buf.getvalue()


def _build_execution_audit(recon: dict, tradovate_snap: dict) -> dict:
    """SELF-AUDITING VERDICT: is the broker trading exactly like paper?

    "Fixed" must be a machine-checked property, not a judgment call made
    while reading bundles. Any execution bug that affects money must
    manifest as one of a CLOSED list of violations:
      1. a broker round-trip with no paper trade   (extra trade)
      2. a paper trade with no broker fill          (missing trade)
      3. entry price off paper's booked entry       (wrong entry)
      4. exit price off paper's booked exit         (wrong exit)
      5. |netPos| > 1 at any moment                 (wrong size)
      6. broker P&L that doesn't reconcile with the
         per-trade ledger + fees                    (unexplained money)
    This function checks all six against Tradovate's OWN records (the
    WS fill archive + cash ledger -- not the bot's self-reporting) and
    emits verdict GREEN / YELLOW / RED with named evidence. GREEN over
    a full session == "broker trades exactly like paper" by definition
    of the spec; any bug that exists must trip a check.
    """
    import json as _json
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz

    def _p(t):
        return _dt.fromisoformat(str(t).replace("Z", "+00:00")).timestamp()

    fees_rt = float(os.environ.get("AUDIT_FEES_PER_RT", "1.96"))
    MNQ = 2.0
    out: dict = {"ts": _dt.now(_tz.utc).isoformat()}

    # ---- 1. Load the fill archive (authoritative, survives date roll)
    fills_by_id: dict = {}
    try:
        from bot.account_ctx import data_dir as _dd
        base = _dd()
        for d in range(3):
            day = (_dt.now(_tz.utc) - _td(days=d)).strftime("%Y%m%d")
            f = base / f"fill_archive_{day}.jsonl"
            if not f.exists():
                continue
            for line in f.read_text().splitlines():
                try:
                    rec = _json.loads(line)
                    if rec.get("id") is not None:
                        fills_by_id[rec["id"]] = rec
                except Exception:
                    continue
    except Exception as e:
        out["fill_archive_error"] = repr(e)
    # Merge today's REST /fill/list (authoritative for the current trade
    # date) over the WS-observed archive: fills that landed during a WS
    # outage or bot restart are missing from the archive, and each gap
    # skews the running-netPos walk for everything after it.
    try:
        rest_fills = tradovate_snap.get("fill_list_raw")
        if (isinstance(rest_fills, (list, tuple)) and len(rest_fills) == 2
                and isinstance(rest_fills[1], list)):
            rest_fills = rest_fills[1]
        for f in (rest_fills or []):
            if isinstance(f, dict) and f.get("id") is not None:
                fills_by_id[f["id"]] = {
                    k: f.get(k) for k in (
                        "id", "orderId", "contractId", "timestamp",
                        "tradeDate", "action", "qty", "price", "active")}
    except Exception:
        pass
    fills = sorted(fills_by_id.values(), key=lambda x: _p(x["timestamp"]))
    out["fills_used"] = len(fills)
    if not fills:
        out["verdict"] = "NO_DATA"
        out["reasons"] = ["fill archive empty -- no broker activity yet"]
        return out
    # Reporting window: violations older than AUDIT_WINDOW_H hours are
    # aged out of the verdict (they belong to code that has since been
    # redeployed). The FIFO walk still runs over ALL fills so pairing
    # and netPos stay correct; only the REPORTED events are filtered.
    window_h = float(os.environ.get("AUDIT_WINDOW_H", "24"))
    cutoff = _dt.now(_tz.utc).timestamp() - window_h * 3600.0
    out["window_h"] = window_h

    # ---- 2. FIFO-pair fills into unit round trips; track netPos path
    lots: list = []          # open lots: (side +1/-1, px, oid, ts)
    rts: list = []           # realized: dict per unit round trip
    pos = 0
    max_abs_pos = 0
    excursions = 0
    for f in fills:
        d = 1 if f.get("action") == "Buy" else -1
        for _ in range(int(f.get("qty", 1) or 1)):
            if lots and lots[0][0] != d:
                s, epx, eoid, ets = lots.pop(0)
                pnl = (float(f["price"]) - epx) * s * MNQ
                rts.append({
                    "entry_ts": ets, "exit_ts": f["timestamp"],
                    "side": "LONG" if s > 0 else "SHORT",
                    "entry_px": epx, "exit_px": float(f["price"]),
                    "entry_oid": eoid, "exit_oid": f.get("orderId"),
                    "pnl_gross": round(pnl, 2),
                })
            else:
                lots.append((d, float(f["price"]), f.get("orderId"),
                             f["timestamp"]))
            pos += d
            if _p(f["timestamp"]) >= cutoff:
                max_abs_pos = max(max_abs_pos, abs(pos))
        if abs(pos) > 1 and _p(f["timestamp"]) >= cutoff:
            excursions += 1
    out["open_lots_at_snapshot"] = len(lots)
    # Age out round trips that closed before the reporting window.
    rts = [rt for rt in rts if _p(rt["exit_ts"]) >= cutoff]

    # ---- 3. Map entry order ids -> paper trades (from recon timelines)
    rows = recon.get("rows") or []
    oid_to_row: dict = {}
    for i, r in enumerate(rows):
        for e in (r.get("timeline") or []):
            if isinstance(e, dict) and e.get("order_id") and e.get(
                    "event") in ("placeoso_result", "pre_submitted_adopted",
                                 "anticipatory_fill_adopted_on_mismatch"):
                oid_to_row.setdefault(int(e["order_id"]), i)

    # RESTART-PROOF JOIN. Timelines live in memory and are wiped by every
    # Railway restart, which killed the oid->paper join (bundle11: 0/163
    # matched after two restarts). The bot audit log lives on disk and
    # records setup_ref + parsed_order_id for every placeoso -- use it
    # as a second join source: oid -> setup_ref -> recon row.
    ref_to_row: dict = {}
    id_to_row: dict = {}
    for i, r in enumerate(rows):
        if r.get("setup_ref"):
            ref_to_row.setdefault(str(r["setup_ref"]), i)
        if r.get("paper_id") is not None:
            id_to_row.setdefault(int(r["paper_id"]), i)
    import re as _re_mod
    _re_audit = _re_mod.compile(r"^acct\d+_(\d+)_(\d+)$")
    oid_to_ref: dict = {}
    try:
        al = tradovate_snap.get("bot_audit_log") or []
        if isinstance(al, list) and len(al) == 2 and isinstance(al[0], int):
            al = al[1]
        for a in (al or []):
            if (isinstance(a, dict) and a.get("kind") == "placeoso"
                    and a.get("parsed_order_id")):
                oid_to_ref[int(a["parsed_order_id"])] = str(
                    a.get("setup_ref") or "")
    except Exception:
        pass

    session_lo = max(_p(fills[0]["timestamp"]) - 600, cutoff)
    win_idx = set()
    for i, r in enumerate(rows):
        try:
            if r.get("paper_entry_time") and _p(
                    r["paper_entry_time"]) >= session_lo:
                win_idx.add(i)
        except Exception:
            continue
    paper_in_window = [rows[i] for i in win_idx]

    trades: list = []
    orphans: list = []
    link_lost: list = []
    matched_row_idx: set = set()
    for rt in rts:
        eoid = int(rt["entry_oid"]) if rt.get("entry_oid") is not None else None
        idx = oid_to_row.get(eoid) if eoid is not None else None
        aud_ref = oid_to_ref.get(eoid) if eoid is not None else None
        if idx is None and aud_ref:
            idx = ref_to_row.get(aud_ref)
        if idx is None and aud_ref:
            # The setup_ref encodes the paper trade's DB id:
            # "acct1_<trade_id>_<fire_epoch>". Both survive restarts,
            # so this join works even when timelines were wiped.
            m = _re_audit.match(aud_ref)
            if m:
                idx = id_to_row.get(int(m.group(1)))
                if idx is None:
                    # Fallback: fire epoch vs paper entry time (±10s).
                    fire_t = float(m.group(2))
                    best = None
                    for j, r2 in enumerate(rows):
                        try:
                            d = abs(_p(r2["paper_entry_time"]) - fire_t)
                        except Exception:
                            continue
                        if d <= 10 and (best is None or d < best[1]):
                            best = (j, d)
                    if best is not None:
                        idx = best[0]
        if idx is None:
            if aud_ref:
                # Bot-submitted (audit log has the placeoso) but the
                # paper row can't be located -- a restart artifact,
                # NOT a broker-only trade. Don't count as orphan.
                link_lost.append({**rt, "ref": aud_ref})
            else:
                orphans.append(rt)
            continue
        matched_row_idx.add(idx)
        r = rows[idx]
        booked_entry = None
        exit_path = None
        for e in (r.get("timeline") or []):
            if e.get("event") == "trade_open_started":
                booked_entry = e.get("entry_px")
            if e.get("event") == "broker_close_result":
                exit_path = e.get("mode") or "instant_liquidate"
        if booked_entry is None:
            # Timeline wiped by a restart -- the recon row's DB price is
            # the same paper entry, so parity stays measurable.
            booked_entry = r.get("paper_entry_px")
        side = r.get("paper_side")
        egap = xgap = None
        if booked_entry is not None:
            egap = round((rt["entry_px"] - booked_entry)
                         * (1 if side == "LONG" else -1), 2)
        if r.get("paper_exit_px") is not None:
            xgap = round((r["paper_exit_px"] - rt["exit_px"])
                         * (1 if side == "LONG" else -1), 2)
        pnl_net = round(rt["pnl_gross"] - fees_rt, 2)
        trades.append({
            "ref": r.get("setup_ref"),
            "entry_time": r.get("paper_entry_time"),
            "side": side,
            "paper_pnl": r.get("paper_pnl"),
            "broker_pnl_net": pnl_net,
            "delta": (round(pnl_net - r["paper_pnl"], 2)
                      if r.get("paper_pnl") is not None else None),
            "entry_gap_pts": egap, "exit_gap_pts": xgap,
            "exit_path": exit_path,
            "entry_oid": rt.get("entry_oid"),
        })

    unfilled_paper = [
        {"ref": rows[i].get("setup_ref"),
         "entry_time": rows[i].get("paper_entry_time"),
         "paper_pnl": rows[i].get("paper_pnl")}
        for i in sorted(win_idx - matched_row_idx)]

    # ---- 4. Money conservation vs Tradovate's cash ledger
    ledger_gross = None
    try:
        cbh = tradovate_snap.get("cash_balance_history")
        if isinstance(cbh, list) and len(cbh) == 2 and isinstance(
                cbh[0], int):
            cbh = cbh[1]
        # Sum TradePaired cash deltas whose timestamps fall inside the
        # archive's own time span -- exact same window as the fills we
        # paired, so the two numbers are directly comparable.
        lo_t = max(_p(fills[0]["timestamp"]) - 60, cutoff)
        hi_t = _p(fills[-1]["timestamp"]) + 60
        tp = 0.0
        n_tp = 0
        for c in (cbh or []):
            if not isinstance(c, dict) or c.get(
                    "cashChangeType") != "TradePaired":
                continue
            try:
                ct = _p(c.get("timestamp"))
            except Exception:
                continue
            if lo_t <= ct <= hi_t:
                tp += c.get("delta") or 0
                n_tp += 1
        # No TradePaired entries in the window means the cash-history
        # snapshot is empty/stale (common right after a restart), not
        # that the broker made $0 -- comparing against 0.0 fabricated
        # a RED "unexplained money" verdict. Report None instead.
        ledger_gross = round(tp, 2) if n_tp > 0 else None
    except Exception:
        pass
    rt_gross = round(sum(rt["pnl_gross"] for rt in rts), 2)

    # ---- 5. Invariants + verdict
    def _pct(a, b):
        return round(100.0 * a / b, 1) if b else 0.0
    deltas = sorted(t["delta"] for t in trades if t.get("delta") is not None)
    orphan_cost = round(sum(o["pnl_gross"] - fees_rt for o in orphans), 2)
    inv = {
        "one_to_one": {
            "paper_trades_in_window": len(paper_in_window),
            "matched": len(matched_row_idx),
            "paper_without_broker_fill": len(unfilled_paper),
            "broker_rts_without_paper": len(orphans),
            "bot_submitted_link_lost": len(link_lost),
        },
        "single_position": {
            "max_abs_netpos": max_abs_pos, "excursions_gt1": excursions,
        },
        "entry_parity_pts": _dist([t["entry_gap_pts"] for t in trades]),
        "exit_parity_pts": _dist([t["exit_gap_pts"] for t in trades]),
        "pnl_delta_usd": {
            "sum": round(sum(deltas), 2) if deltas else None,
            "p50": deltas[len(deltas) // 2] if deltas else None,
            "worst": deltas[0] if deltas else None,
            "expected_fee_drag_per_trade": round(fees_rt - 0.74, 2),
        },
        "orphan_cost_usd": orphan_cost,
        "money_conservation": {
            "gross_from_paired_fills": rt_gross,
            "gross_from_cash_ledger": ledger_gross,
            "diff": (round(rt_gross - ledger_gross, 2)
                     if ledger_gross is not None else None),
        },
    }
    reasons = []
    verdict = "GREEN"
    if excursions > 0:
        verdict = "RED"
        reasons.append(f"netPos exceeded 1 ({excursions} moments, "
                       f"max {max_abs_pos}) -- stacking bug")
    if len(orphans) > 2:
        verdict = "RED"
        reasons.append(f"{len(orphans)} broker round-trips with no paper "
                       f"trade (cost ${orphan_cost}) -- broker-only trades")
    if inv["money_conservation"]["diff"] is not None and abs(
            inv["money_conservation"]["diff"]) > 25:
        verdict = "RED"
        reasons.append("per-trade ledger does not reconcile with "
                       "Tradovate cash ledger -- unexplained money")
    if _pct(len(unfilled_paper), len(paper_in_window)) > 5:
        if verdict != "RED":
            verdict = "YELLOW"
        reasons.append(f"{len(unfilled_paper)} paper trades "
                       f"({_pct(len(unfilled_paper), len(paper_in_window))}%)"
                       f" have no broker fill -- missing trades")
    if deltas and sum(deltas) < -(fees_rt - 0.74) * max(
            1, len(trades)) - 60:
        if verdict != "RED":
            verdict = "YELLOW"
        reasons.append("per-trade P&L delta worse than fee drag by >$60 "
                       "-- execution slippage beyond model")
    if not reasons:
        reasons.append("all invariants hold: broker took exactly paper's "
                       "trades, one contract, prices in tolerance, every "
                       "dollar reconciled")
    out.update({
        "verdict": verdict, "reasons": reasons, "invariants": inv,
        "trades": trades[-250:],
        "orphans": orphans[-50:],
        "link_lost": link_lost[-50:],
        "unfilled_paper": unfilled_paper[-50:],
        "fees_per_rt_assumed": fees_rt,
    })
    return out


def _dist(vals):
    """Small helper: distribution summary of a list (Nones dropped)."""
    v = sorted(x for x in vals if x is not None)
    if not v:
        return None
    worst = v[0] if abs(v[0]) > abs(v[-1]) else v[-1]
    return {"n": len(v), "p50": v[len(v) // 2],
            "p90": v[int(0.9 * len(v))] if len(v) > 1 else v[-1],
            "worst": worst, "min": v[0], "max": v[-1]}


def _build_reconciliation_payload(tradovate_snap: dict) -> dict:
    """Side-by-side paper-vs-broker reconciliation.

    For each closed paper trade (since reset cutoff), find the nearest
    Tradovate fill pair and compute the divergence. This is the SINGLE
    most useful artifact for diagnosing the paper-vs-broker leak: it
    shows exactly which trades had bracket mismatches, slipped fills,
    or wrong exit prices.

    Outputs per-trade:
      {paper_entry, paper_exit, paper_pnl,
       broker_entry, broker_exit, broker_pnl,
       entry_slip, exit_slip, pnl_delta, exec_reports}
    """
    out = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "rows": [],
        "summary": {},
    }
    try:
        paper = _filter_trades_since_reset(persistence.load_trades(
            limit=10_000, only_closed=True))
    except Exception as e:
        out["error"] = f"load_trades failed: {e!r}"
        return out

    # Pull broker artifacts from the snapshot we already collected
    def _list_of(key):
        v = tradovate_snap.get(key)
        if isinstance(v, tuple) and len(v) == 2:
            # _rest returns (status, body)
            v = v[1]
        return v if isinstance(v, list) else []

    fill_pairs = _list_of("fill_pair_list")
    fills = _list_of("fill_list_raw")
    exec_reports = _list_of("execution_report_list")
    orders = _list_of("order_list_raw")

    # Index ExecutionReports by orderId for fast lookup
    er_by_order = {}
    for er in exec_reports:
        if isinstance(er, dict):
            oid = er.get("orderId")
            if oid:
                er_by_order.setdefault(int(oid), []).append(er)

    # NEW: Build setup_ref -> [order_ids] mapping. Every order the bot
    # submits is tagged with text=setup_ref (capped at 64 chars). We can
    # therefore pair paper trades to broker orders EXACTLY by ref tag,
    # instead of guessing by time-window proximity. This is a huge win
    # for reconciliation accuracy.
    order_ids_by_ref = {}
    order_by_id = {}
    for o in orders:
        if not isinstance(o, dict):
            continue
        oid = o.get("id")
        text = (o.get("text") or "").strip()
        if oid is not None:
            order_by_id[int(oid)] = o
        if text and oid is not None:
            order_ids_by_ref.setdefault(text, []).append(int(oid))
    # Build fill-pair index by buyFillId/sellFillId -> their orderId
    fill_by_id = {}
    for f in fills:
        if isinstance(f, dict) and f.get("id") is not None:
            fill_by_id[int(f["id"])] = f
    # Reverse-map: orderId -> [fill_pairs touching that order]
    pair_by_order_id = {}
    for fp in fill_pairs:
        if not isinstance(fp, dict):
            continue
        for fk in ("buyFillId", "sellFillId"):
            fid = fp.get(fk)
            if fid is None:
                continue
            fill = fill_by_id.get(int(fid))
            if isinstance(fill, dict) and fill.get("orderId") is not None:
                pair_by_order_id.setdefault(int(fill["orderId"]), []).append(fp)

    # Build a chronological list of fill pairs as (ts, pair_dict)
    pair_times = []
    for fp in fill_pairs:
        if not isinstance(fp, dict):
            continue
        # FillPair has buyFillId + sellFillId; look up fills for ts
        bf = None
        sf = None
        for f in fills:
            if not isinstance(f, dict):
                continue
            if f.get("id") == fp.get("buyFillId"):
                bf = f
            elif f.get("id") == fp.get("sellFillId"):
                sf = f
        # Approximate the trade's open ts as earlier of the two fills
        ts_open = None
        ts_close = None
        if bf and sf:
            bts = bf.get("timestamp")
            sts = sf.get("timestamp")
            try:
                bts_dt = pd.Timestamp(bts).tz_convert("UTC") \
                    if pd.Timestamp(bts).tz else pd.Timestamp(bts).tz_localize("UTC")
                sts_dt = pd.Timestamp(sts).tz_convert("UTC") \
                    if pd.Timestamp(sts).tz else pd.Timestamp(sts).tz_localize("UTC")
                ts_open = min(bts_dt, sts_dt)
                ts_close = max(bts_dt, sts_dt)
            except Exception:
                pass
        pair_times.append({
            "pair": fp, "buy_fill": bf, "sell_fill": sf,
            "ts_open": ts_open, "ts_close": ts_close,
        })

    # Try to grab the timeline so we can attach the per-trade event
    # log to each row -- the user can see the full timestamp chain
    # without opening another file.
    try:
        from bot.trade_timeline import get_timeline_all
        timelines = get_timeline_all()
    except Exception:
        timelines = {}

    # For each paper trade, prefer exact match by setup_ref tag. The
    # bot tags every order with text=setup_ref, so we can pair
    # paper<->broker without ambiguity. Falls back to time-window
    # only if no ref is found.
    used = set()                # pair_times indices used
    used_refs = set()           # setup_refs already matched
    matched_pnl_delta = 0.0
    total_paper = 0.0
    total_broker = 0.0
    matched = 0
    unmatched = 0
    matched_by_ref = 0
    matched_by_time = 0

    def _pt_index_for_order_id(order_id):
        """Return the pair_times index whose FillPair touches order_id."""
        for idx, pt in enumerate(pair_times):
            fp = pt["pair"]
            for fk in ("buyFillId", "sellFillId"):
                fid = fp.get(fk)
                if fid is None:
                    continue
                fill = fill_by_id.get(int(fid))
                if isinstance(fill, dict):
                    if fill.get("orderId") == order_id:
                        return idx
        return None

    for t in paper:
        et = t.get("exit_time")
        side = t.get("side")
        try:
            et_dt = pd.Timestamp(et).tz_convert("UTC") \
                if pd.Timestamp(et).tz else pd.Timestamp(et).tz_localize("UTC")
        except Exception:
            et_dt = None
        # Reconstruct the setup_ref the bot would have tagged. The
        # format is acct{aid}_{db_id}_{epoch_secs}, but the trade's
        # entry_time gives us the secs. We can also try matching by
        # any "setup_ref" field if persistence stored it.
        ref_candidates = []
        if t.get("setup_ref"):
            ref_candidates.append(t["setup_ref"])
        # If we have the trade db id, reconstruct
        try:
            tid = t.get("id")
            et_secs = None
            if t.get("entry_time"):
                ets = pd.Timestamp(t["entry_time"])
                et_secs = int(ets.timestamp())
            for aid_key in ("account_id", "acct"):
                aid_val = t.get(aid_key)
                if aid_val and tid and et_secs:
                    ref_candidates.append(f"acct{aid_val}_{tid}_{et_secs}")
            # Best-effort scan: any timeline ref that matches the trade
            # db id should also work
            if tid:
                for ref in timelines.keys():
                    if f"_{tid}_" in ref:
                        ref_candidates.append(ref)
        except Exception:
            pass

        best = None
        best_dt = None
        match_method = None

        # Resolve this trade's own timeline up front (keyed by setup_ref).
        # It is the bot's authoritative paper<->broker link, so we can
        # read the exact broker ENTRY order_id it stamped -- no fuzzy
        # matching, and it works for adopted anticipatory orders too
        # (whose text tag is acct*_antc_* and never matched the
        # reconstructed ref).
        _tl_for_trade = None
        for ref in ref_candidates:
            if ref in timelines:
                _tl_for_trade = timelines[ref]
                break

        # Pass 0: deterministic match via the order_id recorded in the
        # trade's OWN timeline. placeoso_result carries the reactive
        # entry order_id; pre_submitted_adopted / anticipatory carry the
        # pre-rested limit's order_id. Either uniquely identifies the
        # broker fill pair for THIS paper trade.
        if best is None and _tl_for_trade:
            tl_oids = []
            for e in _tl_for_trade:
                if not isinstance(e, dict):
                    continue
                oid = e.get("order_id")
                if oid:
                    tl_oids.append(int(oid))
            for oid in tl_oids:
                idx = _pt_index_for_order_id(oid)
                if idx is not None and idx not in used:
                    best = idx
                    best_dt = 0
                    match_method = "timeline_order_id"
                    break

        # Pass 1: exact setup_ref tag
        if best is None:
            for ref in ref_candidates:
                if ref in used_refs:
                    continue
                ids = order_ids_by_ref.get(ref) or []
                for oid in ids:
                    idx = _pt_index_for_order_id(oid)
                    if idx is not None and idx not in used:
                        best = idx
                        best_dt = 0
                        match_method = f"ref:{ref}"
                        used_refs.add(ref)
                        break
                if best is not None:
                    break

        # Pass 2: time-window fallback. Tightened 300s -> 15s: now that
        # Pass 0 matches deterministically by the timeline's own
        # order_id, the only reason to fall here is a trade whose
        # timeline lacks an order_id. A 300s window paired fills MINUTES
        # apart (seen: 234s deltas) and produced phantom ±40pt slippage
        # in attribution. 15s keeps genuine near-simultaneous pairings
        # and leaves the rest honestly UNMATCHED.
        if best is None:
            for idx, pt in enumerate(pair_times):
                if idx in used:
                    continue
                if pt["ts_close"] is None or et_dt is None:
                    continue
                dt = abs((pt["ts_close"] - et_dt).total_seconds())
                if dt > 15:
                    continue
                if best_dt is None or dt < best_dt:
                    best = idx
                    best_dt = dt
                    match_method = "time_window"
        row = {
            "paper_id": t.get("id"),
            "paper_entry_time": t.get("entry_time"),
            "paper_exit_time": et,
            "paper_side": side,
            "paper_qty": t.get("qty"),
            "paper_entry_px": t.get("entry_px"),
            "paper_exit_px": t.get("exit_px"),
            "paper_stop_px": t.get("stop_px"),
            "paper_target_px": t.get("target_px"),
            "paper_pnl": t.get("pnl"),
            "paper_exit_reason": t.get("exit_reason"),
            "ref_candidates": ref_candidates,
            "matched": False,
            "match_method": match_method,
        }
        # Attach timeline events for any matched ref
        for ref in ref_candidates:
            if ref in timelines:
                row["timeline"] = timelines[ref]
                row["setup_ref"] = ref
                break
        if best is not None:
            used.add(best)
            pt = pair_times[best]
            fp = pt["pair"]
            buy_px = fp.get("buyPrice")
            sell_px = fp.get("sellPrice")
            row["matched"] = True
            row["match_delta_seconds"] = best_dt
            row["broker_buy_price"] = buy_px
            row["broker_sell_price"] = sell_px
            row["broker_qty"] = fp.get("qty")
            row["broker_active"] = fp.get("active")
            row["broker_position_id"] = fp.get("positionId")
            row["broker_buy_fill_ts"] = (
                pt["buy_fill"].get("timestamp") if pt["buy_fill"] else None)
            row["broker_sell_fill_ts"] = (
                pt["sell_fill"].get("timestamp") if pt["sell_fill"] else None)
            # Calculate broker entry vs exit by side
            if side and side.upper() == "LONG":
                broker_entry = buy_px
                broker_exit = sell_px
            else:
                broker_entry = sell_px
                broker_exit = buy_px
            row["broker_entry_px"] = broker_entry
            row["broker_exit_px"] = broker_exit
            try:
                pts_diff = float(broker_exit) - float(broker_entry)
                if side and side.upper() == "SHORT":
                    pts_diff = -pts_diff
                row["broker_pts"] = pts_diff
                # MNQ: $2 per point per contract
                row["broker_pnl_gross"] = pts_diff * 2.0 * float(fp.get("qty") or 1)
            except Exception:
                pass
            # Slippage analysis
            try:
                row["entry_slip"] = (
                    float(broker_entry) - float(t.get("entry_px") or 0))
                row["exit_slip"] = (
                    float(broker_exit) - float(t.get("exit_px") or 0))
            except Exception:
                pass
            try:
                row["pnl_delta"] = (
                    float(row.get("broker_pnl_gross") or 0)
                    - float(t.get("pnl") or 0))
                matched_pnl_delta += row["pnl_delta"]
                total_paper += float(t.get("pnl") or 0)
                total_broker += float(row.get("broker_pnl_gross") or 0)
            except Exception:
                pass
            # Find execution reports for the buyFill/sellFill orderIds
            er_keys = set()
            for f in (pt["buy_fill"], pt["sell_fill"]):
                if isinstance(f, dict) and f.get("orderId"):
                    er_keys.add(int(f["orderId"]))
            ers = []
            for k in er_keys:
                ers.extend(er_by_order.get(k, []))
            row["execution_reports"] = ers
            matched += 1
            if match_method and (match_method.startswith("ref:")
                                 or match_method == "timeline_order_id"):
                matched_by_ref += 1
            else:
                matched_by_time += 1
        else:
            unmatched += 1
        out["rows"].append(row)

    out["summary"] = {
        "paper_trades_count": len(paper),
        "matched": matched,
        "matched_by_setup_ref": matched_by_ref,
        "matched_by_time_window": matched_by_time,
        "unmatched": unmatched,
        "total_paper_pnl": round(total_paper, 2),
        "total_broker_pnl": round(total_broker, 2),
        "total_pnl_delta": round(matched_pnl_delta, 2),
        "unmatched_broker_pairs": [
            pt["pair"] for idx, pt in enumerate(pair_times)
            if idx not in used
        ],
    }
    return out


def _build_decisions_payload():
    """Recent block reasons + signal stats. The 'why isn't it trading?'
    debugging payload."""
    from bot.account_ctx import data_dir as _acct_dir, get_account
    out = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "account": get_account(),
        "counters": {},
        "pending_setups": [],
        "last_block_reasons": [],
    }
    try:
        snap = persistence.load_dashboard()
        out["counters"] = {
            "signals_fired":   snap.get("signals_fired"),
            "signals_blocked": snap.get("signals_blocked"),
            "cycle":           snap.get("cycle"),
            "bars_processed":  snap.get("bars_processed"),
        }
        fib = snap.get("fib") or {}
        out["pending_setups"] = fib.get("pending_setups", [])
        # Collate unique block reasons across pending setups
        reasons = {}
        for s in fib.get("pending_setups", []):
            r = s.get("last_block_reason")
            if r:
                reasons[r] = reasons.get(r, 0) + 1
        out["last_block_reasons"] = [{"reason": k, "count": v}
                                       for k, v in reasons.items()]
        out["circuit_breaker"] = fib.get("circuit_breaker")
        out["manual_pause"]    = fib.get("manual_pause")
    except Exception as e:
        out["error"] = repr(e)
    return out


def _build_basket_bundle(tradovate_snap: dict) -> dict:
    """SNAP-BACK BASKET section of the diagnostic bundle.

    Everything needed to verify the multi-instrument engine from one
    file: engine status + prices + gates (with ages), config hash,
    broker-vs-engine position cross-check, basket-tagged fills, the
    engine's own log lines, and a CHECKS list with an overall verdict.
    Read `checks` first: any ERROR names the broken invariant."""
    from bot.basket_engine import DATA as _bdata, basket_enabled
    repo = Path(__file__).resolve().parent.parent
    now = datetime.now(timezone.utc)
    out: dict = {"checks": [], "verdict": "GREEN"}
    checks = out["checks"]

    def _chk(level, code, msg):
        checks.append({"level": level, "code": code, "msg": msg})
        if level == "ERROR":
            out["verdict"] = "RED"
        elif level == "WARN" and out["verdict"] == "GREEN":
            out["verdict"] = "YELLOW"

    def _read_json(name):
        try:
            return json.loads((_bdata / name).read_text())
        except FileNotFoundError:
            return None
        except Exception as e:
            return {"_read_error": repr(e)}

    def _age_s(iso):
        try:
            t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            return round((now - t).total_seconds(), 1)
        except Exception:
            return None

    enabled = basket_enabled()
    killed = (_bdata / "basket_killed.flag").exists()
    out["enabled"] = enabled
    out["data_dir"] = str(_bdata)
    out["kill_flag"] = killed

    status = _read_json("basket_status.json")
    prices = _read_json("basket_prices.json")
    gates = _read_json("gates_daily.json")
    out["status"] = status
    out["prices"] = prices
    out["gates_file"] = gates

    # -- config integrity: deployed sleeves == research file, hashed --
    try:
        import hashlib
        cfg_raw = (repo / "research" / "basket_sleeves.json").read_bytes()
        cfg = json.loads(cfg_raw)
        out["config"] = {
            "md5": hashlib.md5(cfg_raw).hexdigest(),
            "n_sleeves": len(cfg.get("sleeves", [])),
            "contracts": cfg.get("contracts"),
            "validated": cfg.get("validated"),
            "rails": cfg.get("rails"),
        }
        if len(cfg.get("sleeves", [])) != 26:
            _chk("ERROR", "config_sleeves",
                 f"expected 26 sleeves, config has {len(cfg.get('sleeves', []))}")
    except Exception as e:
        out["config"] = {"error": repr(e)}
        _chk("ERROR", "config_missing", f"basket_sleeves.json unreadable: {e!r}")

    # -- engine liveness --
    if not enabled:
        _chk("WARN", "not_enabled",
             "basket disabled via BASKET_ENABLED=0 or basket_disabled.flag")
    if status is None:
        _chk("ERROR" if enabled else "WARN", "no_status",
             "basket_status.json missing — engine has never completed a cycle")
    else:
        age = _age_s(status.get("ts"))
        out["status_age_s"] = age
        # weekday market hours: expect a cycle at least every ~5 min
        market_open = now.weekday() < 5 and not (
            now.weekday() == 4 and now.hour >= 22) and now.hour != 22
        if age is None:
            _chk("ERROR", "status_ts", "status file has unparseable timestamp")
        elif enabled and market_open and age > 300:
            _chk("ERROR", "status_stale",
                 f"status is {age:.0f}s old — engine thread looks dead/stuck")
        elif age > 300:
            _chk("WARN", "status_stale_closed",
                 f"status is {age:.0f}s old (market may be closed — OK if so)")
        if status.get("killed") or killed:
            _chk("ERROR", "kill_switch",
                 "KILL-SWITCH tripped (cum P&L <= -$2,000). Human reset required.")
        if status.get("halted_today"):
            _chk("WARN", "daily_breaker",
                 "daily breaker tripped (day <= -$1,000) — flat until tomorrow")
        g = status.get("gates") or {}
        if g.get("fresh") is False:
            _chk("WARN", "gates_stale",
                 "gates data stale >5 days — gated sleeves are safe-OFF")
        # sleeve-state census for a one-line read
        census: dict = {}
        for s in status.get("sleeves", []):
            census[s.get("state")] = census.get(s.get("state"), 0) + 1
        out["sleeve_census"] = census
        # symbols must be resolved or the engine is idle (no bars, no
        # prices, no trades) — the exact failure the 05:38 bundle caught
        if not status.get("symbols"):
            _chk("ERROR", "no_symbols",
                 "status.symbols is empty — engine has no contracts to "
                 "trade (idle). Restart bug or contract resolver failure.")
        # bar feed: without bars the bots are blind (07:23 bundle: all
        # Tradovate chart fetches rejected, prox stuck at 0, no trades)
        bars = status.get("bars") or {}
        if bars:
            dead = [r for r, v in bars.items()
                    if not (isinstance(v, dict) and v.get("n"))]
            out["bar_feed"] = {r: (v.get("src"), v.get("n"))
                               for r, v in bars.items() if isinstance(v, dict)}
            if len(dead) == len(bars):
                _chk("ERROR", "no_bars",
                     "NO market has bars — bots are blind, zero trades "
                     "possible (check Polygon aggs + log)")
            elif dead:
                _chk("WARN", "bars_missing",
                     f"no bars for: {', '.join(dead)} — those bots idle")

    # -- price feed health --
    if isinstance(prices, dict) and not prices and status is not None:
        _chk("WARN", "prices_empty",
             "basket_prices.json is {} — price thread runs but EVERY "
             "source fails (polygon errors + no bars yet)")
    if prices and isinstance(prices, dict):
        srcs = {}
        stale_px = []
        for r, p in prices.items():
            if not isinstance(p, dict):
                continue
            srcs[p.get("src")] = srcs.get(p.get("src"), 0) + 1
            a = _age_s(p.get("ts"))
            if a is not None and a > 120:
                stale_px.append(f"{r}:{a:.0f}s")
        out["price_sources"] = srcs
        if srcs and not srcs.get("polygon-live"):
            _chk("WARN", "polygon_down",
                 "no polygon-live prices — all falling back to bar closes "
                 "(check POLYGON_API on the host)")
        if stale_px:
            _chk("WARN", "prices_stale", "stale prices: " + ", ".join(stale_px))
    elif prices is None and status is not None:
        _chk("WARN", "no_prices", "basket_prices.json missing — price thread not running")

    # -- gates sanity --
    if gates and isinstance(gates, dict) and "_read_error" not in gates:
        try:
            gage = (now.date() - datetime.fromisoformat(gates["date"]).date()).days
            out["gates_age_days"] = gage
            if gage > 5:
                _chk("WARN", "gates_file_old",
                     f"gates_daily.json is {gage} days old — engine's daily "
                     "self-update isn't running (check VIX fetch in log_lines)")
        except Exception:
            _chk("WARN", "gates_date", "gates_daily.json date unparseable")
    else:
        _chk("WARN", "no_gates",
             "gates_daily.json missing — engine writes it at startup; if the "
             "engine is running this means its first cycle hasn't finished")

    # -- broker cross-check: engine's open sleeves vs Tradovate positions --
    try:
        eng_open: dict = {}
        for s in (status or {}).get("sleeves", []):
            if s.get("state") in ("long", "short"):
                r = s["instr"]
                eng_open[r] = eng_open.get(r, 0) + (
                    1 if s["state"] == "long" else -1)
        brk_open: dict = {}
        pl = (tradovate_snap or {}).get("position_list")
        raw_pos = (pl[1] if isinstance(pl, (list, tuple)) and len(pl) == 2
                   and isinstance(pl[1], list) else
                   pl if isinstance(pl, list) else [])
        if raw_pos:
            from bot.tradovate_client import get_session as _gs2
            sess2 = _gs2()
            back = {"MES": "ES", "M2K": "RTY", "MYM": "YM",
                    "MGC": "GC", "MCL": "CL", "ZB": "ZB"}
            for p in raw_pos:
                if not isinstance(p, dict) or not p.get("netPos"):
                    continue
                sym = _contract_symbol(sess2, p.get("contractId"))
                r = back.get(_root_of(sym)) if sym else None
                if r:
                    brk_open[r] = brk_open.get(r, 0) + int(p["netPos"])
        out["cross_check"] = {"engine_net_by_root": eng_open,
                              "broker_net_by_root": brk_open}
        # only compare when both sides are readable; engine counts units=1
        for r in set(eng_open) | set(brk_open):
            if eng_open.get(r, 0) != brk_open.get(r, 0):
                _chk("ERROR", "position_mismatch",
                     f"{r}: engine thinks net {eng_open.get(r, 0)}, broker "
                     f"has {brk_open.get(r, 0)} — reconcile before trusting P&L")
    except Exception as e:
        out["cross_check"] = {"error": repr(e)}

    # -- basket-tagged fills (setup_ref 'basket:...') --
    try:
        from bot.tradovate_client import get_session as _gs
        sess = _gs()
        if sess.is_configured:
            rows = _collect_broker_trades(sess, sess.get_account_id(), limit=500)
            brows = [r for r in rows
                     if str(r.get("setup_ref") or "").startswith("basket:")
                     or (r.get("instr") and r.get("instr") != "MNQ")]
            out["basket_trades"] = brows[-40:]
            out["basket_trades_count"] = len(brows)
        else:
            out["basket_trades"] = "broker not configured"
    except Exception as e:
        out["basket_trades_error"] = repr(e)

    # -- PER-BOT TRADE JOURNAL (basket_trades.jsonl, engine-written) --
    # One row per completed trade per mini-bot: intended limit vs real
    # entry, bracket levels vs real exit, duration, exit reason. Ground
    # truth for "which of the 26 bots is misbehaving". Flags are
    # mechanical-fidelity only — a losing streak is not an anomaly, a
    # fill off its limit price or a hold past H bars is.
    try:
        _TICK = {"ES": 0.25, "RTY": 0.10, "YM": 1.0,
                 "GC": 0.10, "CL": 0.01, "ZB": 0.03125}
        jpath = _bdata / "basket_trades.jsonl"
        jrows = []
        if jpath.exists():
            for ln in jpath.read_text().splitlines()[-2000:]:
                try:
                    jrows.append(json.loads(ln))
                except Exception:
                    pass
        out["bot_trades"] = jrows[-250:]
        out["bot_trades_count"] = len(jrows)
        per: dict = {}
        for t in jrows:
            k = f"s{t.get('sleeve')}:{t.get('instr')}"
            b = per.setdefault(k, {
                "desc": t.get("desc"), "fam": t.get("fam"),
                "H": t.get("H"), "trades": 0, "wins": 0, "net": 0.0,
                "hold_s": [], "exits": {}, "issues": []})
            b["trades"] += 1
            pnl = float(t.get("pnl") or 0)
            b["net"] = round(b["net"] + pnl, 2)
            if pnl > 0:
                b["wins"] += 1
            if t.get("hold_s") is not None:
                b["hold_s"].append(t["hold_s"])
            w = t.get("exit_reason") or "?"
            b["exits"][w] = b["exits"].get(w, 0) + 1
            tick = _TICK.get(t.get("instr"), 0.25)
            # DIRECTIONAL fills only (2026-07-27: v1 used abs() and
            # flagged s18's short sold 0.5 ABOVE its limit — that is
            # price improvement, normal and good). worse>0 = paid more
            # than the limit allows / received less: impossible for a
            # real limit order, so it means a bookkeeping bug.
            sgn = 1 if t.get("side") == "long" else -1
            try:
                if (t.get("entry_px") is not None
                        and t.get("limit_px") is not None
                        and (t["entry_px"] - t["limit_px"]) * sgn > tick + 1e-9):
                    b["issues"].append(
                        f"entry {t['entry_px']} worse than limit {t['limit_px']}")
            except Exception:
                pass
            try:
                if (w == "target" and t.get("tgt_px") is not None
                        and t.get("exit_px") is not None
                        and (t["tgt_px"] - t["exit_px"]) * sgn > tick + 1e-9):
                    b["issues"].append(
                        f"target exit {t['exit_px']} worse than {t['tgt_px']}")
                # stops fill at market once triggered: allow real
                # slippage, flag only excess (>4 ticks) or a fill on the
                # WRONG side of the trigger (better by >2 ticks).
                if (w == "stop" and t.get("stop_px") is not None
                        and t.get("exit_px") is not None):
                    worse = (t["stop_px"] - t["exit_px"]) * sgn
                    if worse > 4 * tick + 1e-9 or worse < -(2 * tick + 1e-9):
                        b["issues"].append(
                            f"stop exit {t['exit_px']} vs trigger {t['stop_px']}")
            except Exception:
                pass
            try:
                H = int(t.get("H") or 0)
                if (H and t.get("bars_held") is not None
                        and int(t["bars_held"]) > H + 1):
                    b["issues"].append(
                        f"held {t['bars_held']} bars vs H={H}")
            except Exception:
                pass
        for k, b in per.items():
            hs = b.pop("hold_s")
            b["avg_hold_s"] = round(sum(hs) / len(hs), 1) if hs else None
            b["win_rate"] = (round(b["wins"] / b["trades"], 2)
                             if b["trades"] else None)
            b["issue_count"] = len(b["issues"])
            b["issues"] = b["issues"][-5:]   # keep the bundle readable
        out["per_bot"] = per
        bad = {k: b for k, b in per.items() if b["issue_count"]}
        if bad:
            _chk("WARN", "bot_anomalies",
                 "mechanical anomalies in: " + ", ".join(
                     f"{k} ({b['issue_count']}x, e.g. {b['issues'][-1]})"
                     for k, b in sorted(bad.items())))
        if not jrows and status is not None:
            out["bot_trades_note"] = ("journal empty — populates from the "
                                      "first completed trade after this deploy")
    except Exception as e:
        out["bot_trades_error"] = repr(e)

    # -- engine log lines (orders, errors, breaker events) --
    try:
        tail = _read_log_tail(400_000)
        lines = (tail.get("tail") or tail.get("text") or "")
        if isinstance(lines, str):
            bl = [ln for ln in lines.splitlines() if "[basket]" in ln]
            out["log_lines"] = bl[-120:]
            n_err = sum(1 for ln in bl if " ERROR " in ln or "error" in ln.lower())
            if n_err:
                _chk("WARN", "log_errors",
                     f"{n_err} basket error lines in recent log — read log_lines")
    except Exception as e:
        out["log_lines_error"] = repr(e)

    if not checks:
        _chk("OK", "all_clear", "all basket invariants hold")
    return out


@app.route("/api/download/<kind>")
def api_download(kind: str):
    """Unified download endpoint. Returns the requested kind with a
    Content-Disposition header so browsers save instead of display."""
    from bot.account_ctx import data_dir as _acct_dir, get_account
    from flask import Response, send_file

    aid = get_account()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base_name = f"hftbot_acct{aid}_{ts}"

    def _json_resp(payload, filename):
        body = json.dumps(payload, indent=2, default=str)
        return Response(
            body,
            mimetype="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    def _text_resp(body, filename, mime="text/plain"):
        return Response(
            body,
            mimetype=mime,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    if kind == "bundle":
        include_verify = (request.args.get("verify", "1") == "1")
        payload = {
            "kind": "diagnostic_bundle",
            "ts": datetime.now(timezone.utc).isoformat(),
            "health": _build_health_payload(include_verify=include_verify),
            "config": _build_config_payload(),
            "code_state": _build_code_state_payload(),
            "decisions": _build_decisions_payload(),
        }
        # Trim very large entries to keep file manageable
        try:
            rows = _filter_trades_since_reset(persistence.load_trades(limit=200))[:100]
            payload["recent_trades"] = rows
        except Exception as e:
            payload["recent_trades_error"] = repr(e)
        # NEW: include the full set of Tradovate diagnostic endpoints
        # so the user only has to download one file instead of
        # screenshotting 6 different URLs every time something looks off.
        tradovate_snap = _collect_tradovate_snapshot()
        payload["tradovate"] = tradovate_snap
        # SNAP-BACK BASKET verification: engine status, prices, gates,
        # config hash, broker cross-check, basket fills, engine log +
        # a GREEN/YELLOW/RED verdict. Read basket.checks first.
        try:
            payload["basket"] = _build_basket_bundle(tradovate_snap)
        except Exception as e:
            payload["basket_error"] = repr(e)
        # THE most important diagnostic: explicit detection of every
        # mechanism that causes paper-vs-broker divergence. Stale
        # fills, missed entries, bracket rejections, latency, target
        # chase events, etc. Each finding has a $ impact estimate.
        try:
            payload["paper_broker_forensics"] = _build_paper_broker_forensics(
                tradovate_snap)
        except Exception as e:
            payload["paper_broker_forensics_error"] = repr(e)
        # Bot-internal diagnostic data (strategy decisions, tick history,
        # Polygon-vs-Tradovate price diff). No broker round-trips.
        try:
            payload["diagnostics"] = _build_diagnostic_extras()
        except Exception as e:
            payload["diagnostics_error"] = repr(e)
        # Side-by-side paper-vs-broker reconciliation. Pairs each paper
        # trade with the nearest broker fill pair and computes slippage
        # + pnl delta. THIS IS THE ARTIFACT for diagnosing the
        # paper-vs-broker leak.
        try:
            payload["reconciliation"] = _build_reconciliation_payload(
                tradovate_snap)
        except Exception as e:
            payload["reconciliation_error"] = repr(e)
        # SELF-AUDIT VERDICT. Checks the closed list of invariants that
        # define "broker trades exactly like paper" against Tradovate's
        # own fill archive + cash ledger and emits GREEN/YELLOW/RED with
        # named evidence. Read THIS first in every bundle: GREEN over a
        # full session means fixed by definition; anything else names
        # the violating trade/order/reason.
        # STRATEGY REPLAY BASELINE. The real strategy code run over the
        # last week of Polygon 1m bars with no account filters: what
        # paper SHOULD have made each day. Computed in a background
        # thread + disk cache, so this never blocks the bundle build.
        try:
            from bot.strategy_replay import get_replay
            payload["strategy_replay"] = get_replay()
            # Side-by-side: live paper's ACTUAL per-day results from the
            # DB, same trade-date convention as the replay. Divergence
            # between these two tables on the same day = paper-runtime
            # bug; parallel movement = market regime.
            try:
                from datetime import timedelta as _tdd
                live_days: dict = {}
                for t in persistence.load_trades(limit=10_000,
                                                 only_closed=True):
                    et = t.get("entry_time")
                    if not et or t.get("pnl") is None:
                        continue
                    d = (datetime.fromisoformat(et) + _tdd(hours=2)
                         ).strftime("%Y-%m-%d")
                    rec = live_days.setdefault(
                        d, {"n_trades": 0, "net_usd": 0.0, "wins": 0,
                            "exits": {}})
                    rec["n_trades"] += 1
                    rec["net_usd"] = round(rec["net_usd"] + t["pnl"], 2)
                    if t["pnl"] > 0:
                        rec["wins"] += 1
                    er = str(t.get("exit_reason") or "?")
                    rec["exits"][er] = rec["exits"].get(er, 0) + 1
                cutoff_d = (datetime.now(timezone.utc)
                            - _tdd(days=10)).strftime("%Y-%m-%d")
                payload["strategy_replay"]["live_paper_days"] = {
                    k: v for k, v in sorted(live_days.items())
                    if k >= cutoff_d}
            except Exception as e:
                payload["strategy_replay"]["live_paper_days"] = {
                    "error": repr(e)}
        except Exception as e:
            payload["strategy_replay"] = {"error": repr(e)}
        try:
            payload["execution_audit"] = _build_execution_audit(
                payload.get("reconciliation") or {}, tradovate_snap)
        except Exception as e:
            payload["execution_audit_error"] = repr(e)
        # Bot's market data snapshot at the time of the bundle (last
        # tick, bid/ask, contract resolved). Lets us cross-check that
        # the contract symbol matches what Tradovate has.
        try:
            from bot.tradovate_client import get_session as _gs
            sess = _gs()
            payload["resolved_contract"] = {
                "symbol_env": os.environ.get("FUTURES_SYMBOL", "MNQ"),
                "session_account_id": sess.get_account_id(),
                "is_configured": sess.is_configured,
            }
        except Exception as e:
            payload["resolved_contract"] = {"error": repr(e)}
        # Dashboard live snapshot (fib_main's last cycle output: pending
        # setups, live price, bias, signals). Pairs with bot_audit_log to
        # explain WHY each placeoso happened.
        try:
            payload["live_snapshot"] = persistence.load_dashboard()
        except Exception as e:
            payload["live_snapshot_error"] = repr(e)
        return _json_resp(payload, f"{base_name}_bundle.json")

    if kind == "health":
        return _json_resp(_build_health_payload(), f"{base_name}_health.json")
    if kind == "diag":
        # Reuse the existing diag endpoint
        with app.test_request_context(f"/api/diag?account={aid}"):
            diag = api_diag()
            body = diag.get_json() if hasattr(diag, "get_json") else diag
        return _json_resp(body, f"{base_name}_diag.json")
    if kind == "crash":
        cp = _acct_dir() / "bot_crash.txt"
        if not cp.exists():
            return _text_resp("(no crash trace found)\n",
                                 f"{base_name}_crash.txt")
        return _text_resp(cp.read_text(), f"{base_name}_crash.txt")
    if kind == "decisions":
        return _json_resp(_build_decisions_payload(),
                            f"{base_name}_decisions.json")

    if kind == "trades.csv":
        return _text_resp(_build_trades_csv(),
                            f"{base_name}_trades.csv", mime="text/csv")
    if kind == "equity.csv":
        return _text_resp(_build_equity_csv(),
                            f"{base_name}_equity.csv", mime="text/csv")
    if kind == "daily.csv":
        return _text_resp(_build_daily_csv(),
                            f"{base_name}_daily.csv", mime="text/csv")

    if kind == "config":
        return _json_resp(_build_config_payload(), f"{base_name}_config.json")
    if kind == "code_state":
        return _json_resp(_build_code_state_payload(),
                            f"{base_name}_code_state.json")
    if kind == "lucid":
        lp = _acct_dir() / "lucid_account.json"
        if lp.exists():
            try:
                data = json.loads(lp.read_text())
            except Exception as e:
                data = {"error": repr(e)}
        else:
            data = {"error": "lucid_account.json missing"}
        return _json_resp(data, f"{base_name}_lucid.json")
    if kind == "shadow":
        sp = _acct_dir() / "shadow_engine.json"
        if sp.exists():
            try:
                data = json.loads(sp.read_text())
            except Exception as e:
                data = {"error": repr(e)}
        else:
            data = {"error": "shadow_engine.json missing (bot not running engine yet)"}
        return _json_resp(data, f"{base_name}_shadow_engine.json")
    if kind == "shadow_vs_live":
        # The single most useful download: side-by-side live trades and
        # engine trades for the same time period. The compare for me to
        # quickly verify they agree.
        sp = _acct_dir() / "shadow_engine.json"
        live_rows = _filter_trades_since_reset(persistence.load_trades(limit=10_000))
        try:
            shadow = json.loads(sp.read_text()) if sp.exists() else None
        except Exception as e:
            shadow = {"error": repr(e)}
        payload = {
            "kind": "shadow_vs_live_comparison",
            "ts": datetime.now(timezone.utc).isoformat(),
            "live_trades": live_rows,
            "shadow": shadow,
        }
        return _json_resp(payload, f"{base_name}_shadow_vs_live.json")
    if kind == "tradovate":
        try:
            from engine.brokers.tradovate import tradovate_status
            data = tradovate_status()
        except Exception as e:
            data = {"error": repr(e)}
        return _json_resp(data, f"{base_name}_tradovate.json")
    if kind == "tradovate_full":
        # Full Tradovate diagnostic dump: every entity table the API
        # PDF says is useful for reconciliation. Heavier than the
        # standalone tradovate dump.
        return _json_resp(_collect_tradovate_snapshot(),
                            f"{base_name}_tradovate_full.json")
    if kind == "reconcile":
        # Paper-vs-broker side-by-side. Separated from bundle so the
        # user can grab it quickly to see slippage + missed brackets.
        return _json_resp(
            _build_reconciliation_payload(_collect_tradovate_snapshot()),
            f"{base_name}_reconcile.json")
    if kind == "audit_log":
        # Bot's audit of every placeoso/placeorder/liquidate attempt
        # with full request body + raw response + parsed result +
        # bracket verification. Tiny file, immediately actionable.
        try:
            from bot.tradovate_orders import get_audit_log
            data = {"ts": datetime.now(timezone.utc).isoformat(),
                    "entries": get_audit_log()}
        except Exception as e:
            data = {"error": repr(e)}
        return _json_resp(data, f"{base_name}_audit_log.json")
    if kind == "diagnostics":
        # Bot-internal diagnostic data: strategy decisions, tick history,
        # price-diff samples. No broker round-trips.
        return _json_resp(_build_diagnostic_extras(),
                            f"{base_name}_diagnostics.json")
    if kind == "timeline":
        # Standalone trade-event timeline. One row per setup_ref with
        # the full chain of state transitions.
        try:
            from bot.trade_timeline import get_timeline_all, get_summary
            data = {"ts": datetime.now(timezone.utc).isoformat(),
                    "summary": get_summary(),
                    "timelines": get_timeline_all()}
        except Exception as e:
            data = {"error": repr(e)}
        return _json_resp(data, f"{base_name}_timeline.json")
    if kind == "traderspost":
        try:
            from engine.brokers.traderspost import traderspost_status
            data = traderspost_status()
        except Exception as e:
            data = {"error": repr(e)}
        return _json_resp(data, f"{base_name}_traderspost.json")
    if kind == "verify":
        with app.test_request_context(f"/api/admin/verify_today?account={aid}"):
            resp = api_admin_verify_today()
            if isinstance(resp, tuple):
                body = resp[0].get_json() if hasattr(resp[0], "get_json") else None
            else:
                body = resp.get_json() if hasattr(resp, "get_json") else None
        return _json_resp(body, f"{base_name}_verify.json")
    if kind == "regime_today":
        try:
            data = _build_regime_today_payload()
        except Exception as e:
            data = {"ok": False, "error": repr(e)}
        return _json_resp(data, f"{base_name}_regime_today.json")

    return jsonify({"ok": False, "error": f"unknown download kind: {kind}"}), 400


def _build_regime_today_payload():
    """Pulls today's NQ 1-min bars from Polygon, compares apples-to-apples
    against the SAME ELAPSED TIME of the prior 6 NY days, and returns a
    verdict on whether today is unusually quiet/choppy or whether
    something else is off."""
    from research.data_loader import download_nq
    from research.signal_filters import NY_TZ
    from datetime import datetime, timezone, timedelta
    import pandas as _pd

    bars = download_nq("1min", force_refresh=True)
    if bars is None or bars.empty:
        return {"ok": False, "error": "no bars returned from Polygon"}
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    else:
        bars.index = bars.index.tz_convert("UTC")
    bars = bars.sort_index()

    now_utc = datetime.now(timezone.utc)

    def _ny_day_start_utc(dt_utc):
        """Return the UTC start of the NY day that contains dt_utc.
        NY day rolls at 16:00 ET; tz handled properly (DST-aware)."""
        et = _pd.Timestamp(dt_utc).tz_convert(NY_TZ)
        if et.hour >= 16:
            start = et.replace(hour=16, minute=0, second=0, microsecond=0)
        else:
            start = (et - _pd.Timedelta(days=1)).replace(
                hour=16, minute=0, second=0, microsecond=0)
        return start.tz_convert("UTC").to_pydatetime()

    today_start = _ny_day_start_utc(now_utc)
    elapsed_secs = (now_utc - today_start).total_seconds()

    def _slice(start_utc, end_utc):
        m = (bars.index >= _pd.Timestamp(start_utc)) & \
            (bars.index <= _pd.Timestamp(end_utc))
        return bars.loc[m]

    def _analyze(b):
        if b.empty: return None
        h = float(b["high"].max()); l = float(b["low"].min())
        rng = b["high"] - b["low"]
        # Count 5pt 4-bar impulses -- matches strategy logic exactly
        impulses = 0
        impulse_pts_sum = 0.0
        c = b["close"].to_numpy(); o = b["open"].to_numpy()
        for i in range(4, len(b) + 1):
            net = c[i-1] - o[i-4]
            if abs(net) >= 5.0:
                impulses += 1
                impulse_pts_sum += abs(net)
        # 5-bar ATR
        atr5 = 0.0
        if len(b) >= 6:
            hh = b["high"].to_numpy()[-6:]; ll = b["low"].to_numpy()[-6:]
            cc = b["close"].to_numpy()[-6:]
            import numpy as _np
            prev = _np.r_[cc[0], cc[:-1]]
            tr = _np.maximum.reduce([hh - ll, _np.abs(hh - prev), _np.abs(ll - prev)])
            atr5 = float(tr[1:].mean())
        return {
            "n_bars":                int(len(b)),
            "range_pts":             round(h - l, 2),
            "avg_bar_range_pts":     round(float(rng.mean()), 3),
            "median_bar_range_pts":  round(float(rng.median()), 3),
            "total_volume":          int(b["volume"].sum()),
            "avg_volume_per_bar":    round(float(b["volume"].mean()), 1),
            "n_5pt_impulses":        int(impulses),
            "avg_impulse_pts":       round(impulse_pts_sum / impulses, 2) if impulses else 0,
            "impulses_per_hour":     round(impulses / max(len(b) / 60.0, 0.1), 2),
            "atr_5bar_pts":          round(atr5, 2),
        }

    today_bars = _slice(today_start, now_utc)
    today_stats = _analyze(today_bars)

    # Baseline: same elapsed window from each of the prior 6 NY days.
    baseline_days = []
    for k in range(1, 7):
        d_start = today_start - timedelta(days=k)
        d_end   = d_start + timedelta(seconds=elapsed_secs)
        d_bars  = _slice(d_start, d_end)
        a = _analyze(d_bars)
        if a:
            baseline_days.append({
                "ny_date_start_utc": d_start.isoformat(),
                "elapsed_window":    a,
            })

    # Mean baseline
    def _mean(field):
        vals = [d["elapsed_window"][field] for d in baseline_days
                if d["elapsed_window"].get(field) is not None]
        if not vals: return None
        return sum(vals) / len(vals)

    baseline_avg = None
    if baseline_days:
        baseline_avg = {
            "n_bars":            round(_mean("n_bars") or 0),
            "range_pts":         round(_mean("range_pts") or 0, 2),
            "avg_bar_range_pts": round(_mean("avg_bar_range_pts") or 0, 3),
            "total_volume":      round(_mean("total_volume") or 0),
            "n_5pt_impulses":    round(_mean("n_5pt_impulses") or 0),
            "impulses_per_hour": round(_mean("impulses_per_hour") or 0, 2),
            "atr_5bar_pts":      round(_mean("atr_5bar_pts") or 0, 2),
        }

    # Verdict
    verdict_lines = [
        f"=== TODAY vs LAST 6 DAYS (apples-to-apples, same elapsed window) ===",
        f"Now: {now_utc.isoformat()}",
        f"NY day started: {today_start.isoformat()}",
        f"Elapsed: {elapsed_secs/3600:.1f} hours into the NY day",
        f"",
    ]
    diagnosis = "no_diagnosis"
    if today_stats and baseline_avg:
        def _pct(t_field):
            t = today_stats.get(t_field) or 0
            b = baseline_avg.get(t_field) or 0
            if b == 0: return None
            return round(100 * t / b, 0)
        i_pct = _pct("n_5pt_impulses")
        v_pct = _pct("total_volume")
        r_pct = _pct("avg_bar_range_pts")
        atr_pct = _pct("atr_5bar_pts")

        verdict_lines.append(f"  Bars elapsed:        {today_stats['n_bars']} vs {baseline_avg['n_bars']} avg")
        verdict_lines.append(f"  Total range:         {today_stats['range_pts']:.0f}pt vs {baseline_avg['range_pts']:.0f}pt avg")
        verdict_lines.append(f"  Avg bar range:       {today_stats['avg_bar_range_pts']:.2f}pt vs {baseline_avg['avg_bar_range_pts']:.2f}pt avg  ({r_pct}% of normal)")
        verdict_lines.append(f"  5-bar ATR (current): {today_stats['atr_5bar_pts']:.2f}pt vs {baseline_avg['atr_5bar_pts']:.2f}pt avg  ({atr_pct}% of normal)")
        verdict_lines.append(f"  Total volume:        {today_stats['total_volume']:,} vs {baseline_avg['total_volume']:,} avg  ({v_pct}% of normal)")
        verdict_lines.append(f"  5pt impulses:        {today_stats['n_5pt_impulses']} vs {baseline_avg['n_5pt_impulses']} avg  ({i_pct}% of normal)")
        verdict_lines.append(f"  Impulses/hour:       {today_stats['impulses_per_hour']:.2f} vs {baseline_avg['impulses_per_hour']:.2f} avg")
        verdict_lines.append(f"")
        # Verdict logic
        if i_pct is not None and i_pct < 50:
            diagnosis = "low_opportunity_market"
            verdict_lines.append(f"DIAGNOSIS: low_opportunity_market")
            verdict_lines.append(f"  Today has only {i_pct}% of the usual 5pt impulse count.")
            verdict_lines.append(f"  The strategy fires on 5pt 4-bar impulses; if those don't happen,")
            verdict_lines.append(f"  the bot CAN'T trade. This is a quiet-market day, NOT a bot bug.")
        elif i_pct is not None and i_pct < 75:
            diagnosis = "below_average_market"
            verdict_lines.append(f"DIAGNOSIS: below_average_market")
            verdict_lines.append(f"  Today is showing {i_pct}% of typical impulse count -- slower")
            verdict_lines.append(f"  than usual but not unusual. Expect ~{i_pct}% of typical trade count.")
        else:
            diagnosis = "market_normal_check_bot"
            verdict_lines.append(f"DIAGNOSIS: market_normal_check_bot")
            verdict_lines.append(f"  Impulse count is {i_pct}% of normal -- market is roughly normal.")
            verdict_lines.append(f"  If the bot still isn't trading, check:")
            verdict_lines.append(f"    - Health snapshot: bars_1m_source must be 'real'")
            verdict_lines.append(f"    - Last error field non-null?")
            verdict_lines.append(f"    - Risk gates (auto-DLL, cooldown, news blackout)")
        if r_pct is not None and r_pct < 70:
            verdict_lines.append(f"VOLATILITY: avg bar range is {r_pct}% of normal -- price action is QUIET / CHOPPY.")
        elif r_pct is not None and r_pct > 130:
            verdict_lines.append(f"VOLATILITY: elevated ({r_pct}% of normal) -- possibly news/event driven.")
        if v_pct is not None and v_pct < 70:
            verdict_lines.append(f"VOLUME: {v_pct}% of normal -- low participation, thin liquidity.")
        elif v_pct is not None and v_pct > 130:
            verdict_lines.append(f"VOLUME: {v_pct}% of normal -- heavy participation.")

    return {
        "ok": True,
        "ts": now_utc.isoformat(),
        "today_window": {
            "start_utc": today_start.isoformat(),
            "end_utc":   now_utc.isoformat(),
            "elapsed_hours": round(elapsed_secs / 3600, 2),
            "stats": today_stats,
        },
        "baseline_days": baseline_days,
        "baseline_avg":  baseline_avg,
        "diagnosis":     diagnosis,
        "verdict":       verdict_lines,
    }


@app.route("/api/admin/verify_today", methods=["GET", "POST"])
def api_admin_verify_today():
    """Per-trade audit: for every trade closed today, fetch real Polygon
    1-min bars covering the trade window and verify the bot's claimed
    behaviour matches the actual market.

    Replicates the strategy's logic exactly:
      - impulse = window[-1].close - window[0].open over LAST 4 bars
      - signal can fire any time in [entry_min - 5, entry_min]; we scan
        every candidate and accept the trade if ANY signal time produces
        an impulse + pullback level + side that matches the bot's record
      - then checks: did some bar in [signal+1, signal+5] actually touch
        the claimed entry, and did some bar in [fill, fill+10] hit the
        claimed stop or target as recorded

    Returns a JSON report. OK = bot behaviour confirmed by Polygon ticks.
    MISMATCH = at least one check failed; details show which one and the
    closest signal-time candidate so you can see how far off it was.
    """
    from research.data_loader import download_nq
    from datetime import datetime, timedelta, timezone as _tz
    import pandas as _pd

    # Pull today's closed trades (NY day, post-reset).
    cutoff = _reset_cutoff_ts()
    all_rows = _filter_trades_since_reset(persistence.load_trades(limit=10_000),
                                          cutoff=cutoff)
    since_param = request.args.get("since")
    if since_param:
        try:
            since_ts = _pd.Timestamp(since_param)
            since_ts = since_ts.tz_convert("UTC") if since_ts.tz is not None \
                       else since_ts.tz_localize("UTC")
        except Exception:
            return jsonify({"ok": False, "error": f"bad since: {since_param}"}), 400
    else:
        since_ts = _pd.Timestamp.now(tz="UTC").normalize()
    today_rows = []
    for r in all_rows:
        et = r.get("entry_time"); xt = r.get("exit_time")
        if not et or not xt:
            continue
        try:
            ets = _pd.Timestamp(et)
            ets = ets.tz_convert("UTC") if ets.tz is not None else ets.tz_localize("UTC")
            if ets < since_ts:
                continue
            today_rows.append((r, ets))
        except Exception:
            continue

    if not today_rows:
        return jsonify({
            "ok": True,
            "since": since_ts.isoformat(),
            "n_trades": 0,
            "msg": "No trades to verify in this window.",
        })

    # Fetch today's Polygon 1-min bars (force refresh to bypass cache).
    try:
        bars = download_nq("1min", force_refresh=True)
        if bars is None or bars.empty:
            return jsonify({"ok": False, "error": "Polygon returned no 1-min data"}), 502
        if bars.index.tz is None:
            bars.index = bars.index.tz_localize("UTC")
        else:
            bars.index = bars.index.tz_convert("UTC")
    except Exception as e:
        return jsonify({"ok": False, "error": f"Polygon fetch failed: {e!r}"}), 502

    # Strategy constants -- read from env so the verifier tracks the
    # live config (STRAT_* env vars). Previously hardcoded to the old
    # baseline (pull=0.618, stop=6, tgt=12), so when the live bot was
    # running inverse mode (pull=0.236, stop=10, tgt=20) every trade
    # got flagged as entry_price_off / side_mismatch.
    IMPULSE_PTS    = float(os.environ.get("STRAT_IMPULSE_PTS", "5.0"))
    IMPULSE_WINDOW = int(os.environ.get("STRAT_IMPULSE_BARS", "4"))
    PULLBACK_PCT   = float(os.environ.get("STRAT_PULL_PCT", "0.618"))
    STOP_PTS       = float(os.environ.get("STRAT_STOP_PTS", "6.0"))
    TARGET_PTS     = float(os.environ.get("STRAT_TARGET_PTS", "12.0"))
    INVERT_MODE    = os.environ.get("STRAT_INVERT", "0") == "1"
    MAX_WAIT_MIN   = 5
    MAX_HOLD_MIN   = 10
    ENTRY_TOL      = 0.5    # pt tolerance for matching entry prices

    audited = []
    summary = {"verified": 0, "mismatched": 0, "polygon_missing": 0,
               "bot_data_source": None}
    # Tell the user what source the bot is on so they can correlate the
    # audit with the bot's actual data quality.
    try:
        from bot.persistence import load_dashboard
        snap = load_dashboard()
        summary["bot_data_source"] = snap.get("bars_1m_source")
    except Exception:
        pass

    def _scan_signals(entry_ts, bot_entry_px, bot_side):
        """Try every candidate signal time in [entry_min - MAX_WAIT_MIN - 2, entry_min].
        Return the best matching candidate (or None) along with diagnostics
        for the closest one.

        Bar timestamp convention: Polygon bars are indexed at the START of
        the minute. Bar at index T represents the minute [T, T+1) and
        closes at T+1. So when the bot's _bars_1m has its latest bar at
        index N, that bar closed at N+1, and the impulse window the
        strategy used was bars at indices [N-3, N-2, N-1, N].

        For a fill at wall clock W (entry_ts), the bot's _bars_1m latest
        bar could be at any index N in [floor(W) - 7, floor(W)] -- we
        widen the scan to handle both "polygon returns only closed bars"
        (N = floor(W) - 1) and "polygon returns in-progress bar"
        (N = floor(W)) cases, plus up to 5min of wait + a couple minutes
        of cache staleness.
        """
        entry_min = entry_ts.floor("min")
        best_match = None
        closest_diag = None
        # k = 0: latest impulse bar at index entry_min (in-progress / just-closed)
        # k = 1: latest impulse bar at index entry_min - 1 (canonical case)
        # ... up to k = 7 to cover MAX_WAIT_MIN + cache slack
        for k in range(0, MAX_WAIT_MIN + 3):
            latest_bar_idx = entry_min - timedelta(minutes=k)
            earliest_bar_idx = latest_bar_idx - timedelta(minutes=IMPULSE_WINDOW - 1)
            window = bars[(bars.index >= earliest_bar_idx) & (bars.index <= latest_bar_idx)]
            if len(window) < IMPULSE_WINDOW:
                continue
            window = window.iloc[-IMPULSE_WINDOW:]   # last 4 only
            net = float(window["close"].iloc[-1]) - float(window["open"].iloc[0])
            sig_close_ts = latest_bar_idx + timedelta(minutes=1)  # bar's close time
            if abs(net) < IMPULSE_PTS:
                if closest_diag is None or abs(IMPULSE_PTS - abs(net)) < abs(closest_diag.get("missing_by", 999)):
                    closest_diag = {"sig_close_ts": sig_close_ts.isoformat(),
                                    "latest_bar_idx": latest_bar_idx.isoformat(),
                                    "k_back": k,
                                    "impulse_pts": round(net, 2),
                                    "missing_by": round(IMPULSE_PTS - abs(net), 2),
                                    "fail": "impulse_too_small"}
                continue
            impulse_side = "LONG" if net > 0 else "SHORT"
            imp_high = float(window["high"].max())
            imp_low  = float(window["low"].min())
            rng = imp_high - imp_low
            if rng <= 0:
                continue
            # Entry geometry is anchored to the IMPULSE direction
            # regardless of INVERT (the bot uses orig_side for the
            # retracement calc and only flips the trade side).
            if impulse_side == "LONG":
                expected_entry = imp_high - PULLBACK_PCT * rng
            else:
                expected_entry = imp_low + PULLBACK_PCT * rng
            # The TRADE side the bot should be on. INVERT flips it.
            expected_side = (
                ("SHORT" if impulse_side == "LONG" else "LONG")
                if INVERT_MODE else impulse_side
            )
            diag = {
                "sig_close_ts": sig_close_ts.isoformat(),
                "latest_bar_idx": latest_bar_idx.isoformat(),
                "k_back": k,
                "impulse_pts": round(net, 2),
                "impulse_side": impulse_side,
                "expected_side": expected_side,
                "expected_entry": round(expected_entry, 2),
                "entry_diff": round(expected_entry - bot_entry_px, 2),
            }
            if expected_side != bot_side:
                diag["fail"] = "side_mismatch"
                if closest_diag is None or abs(diag["entry_diff"]) < abs(closest_diag.get("entry_diff", 999)):
                    closest_diag = diag
                continue
            if abs(expected_entry - bot_entry_px) >= ENTRY_TOL:
                diag["fail"] = "entry_price_off"
                if closest_diag is None or abs(diag["entry_diff"]) < abs(closest_diag.get("entry_diff", 999)):
                    closest_diag = diag
                continue
            # Match!
            diag["fail"] = None
            return diag, diag
        return None, closest_diag

    for r, entry_ts in today_rows:
        bot_entry_px  = float(r.get("entry_px") or 0)
        bot_exit_px   = float(r.get("exit_px") or 0)
        bot_stop_px   = float(r.get("stop_px") or 0)
        bot_target_px = float(r.get("target_px") or 0)
        bot_side      = r.get("side")
        bot_pnl       = float(r.get("pnl") or 0)
        bot_reason    = r.get("exit_reason") or ""
        side_sign     = 1 if bot_side == "LONG" else -1

        # Check Polygon coverage.
        window_start = entry_ts - timedelta(minutes=MAX_WAIT_MIN + IMPULSE_WINDOW + 2)
        window_end   = entry_ts + timedelta(minutes=MAX_HOLD_MIN + 2)
        slice_bars = bars[(bars.index >= window_start) & (bars.index <= window_end)]
        if slice_bars.empty:
            summary["polygon_missing"] += 1
            audited.append({"entry_ts": entry_ts.isoformat(),
                            "side": bot_side, "bot_pnl": round(bot_pnl, 2),
                            "verdict": "NO_DATA",
                            "note": "Polygon has no 1-min bars for this trade window."})
            continue

        match, closest = _scan_signals(entry_ts, bot_entry_px, bot_side)

        # Reality checks: did entry, stop, target actually get touched.
        post_signal = slice_bars[slice_bars.index >= entry_ts.floor("min") - timedelta(minutes=MAX_WAIT_MIN)]
        if side_sign == 1:
            touched_entry = bool((post_signal["low"]  <= bot_entry_px).any())
        else:
            touched_entry = bool((post_signal["high"] >= bot_entry_px).any())
        hold_bars = slice_bars[slice_bars.index >= entry_ts.floor("min")]
        if side_sign == 1:
            hit_stop = bool((hold_bars["low"]  <= bot_stop_px).any())
            hit_tgt  = bool((hold_bars["high"] >= bot_target_px).any())
        else:
            hit_stop = bool((hold_bars["high"] >= bot_stop_px).any())
            hit_tgt  = bool((hold_bars["low"]  <= bot_target_px).any())
        exit_match = (
            (bot_reason == "stop"   and hit_stop) or
            (bot_reason == "target" and hit_tgt)  or
            (bot_reason == "timeout")
        )

        signal_match = match is not None
        verdict = "OK" if (signal_match and touched_entry and exit_match) else "MISMATCH"
        if verdict == "OK": summary["verified"] += 1
        else: summary["mismatched"] += 1

        audited.append({
            "entry_ts": entry_ts.isoformat(),
            "side": bot_side,
            "bot_entry_px": round(bot_entry_px, 2),
            "bot_exit_px":  round(bot_exit_px, 2),
            "bot_stop_px":  round(bot_stop_px, 2),
            "bot_target_px": round(bot_target_px, 2),
            "bot_exit_reason": bot_reason,
            "bot_pnl": round(bot_pnl, 2),
            "polygon": {
                "signal_match": signal_match,
                "matched_signal": match,
                "closest_signal": closest,
                "bar_touched_entry": touched_entry,
                "bar_hit_stop": hit_stop,
                "bar_hit_target": hit_tgt,
                "exit_reason_matches_bars": exit_match,
            },
            "verdict": verdict,
        })

    return jsonify({
        "ok": True,
        "since": since_ts.isoformat(),
        "n_trades": len(today_rows),
        "summary": summary,
        "trades": audited,
        "note": "OK requires: matching impulse signal time exists with side+entry "
                "consistent with strategy; entry was touched; exit reason matches "
                "what bars actually did.",
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


@app.route("/api/admin/reset_all", methods=["POST"])
def api_admin_reset_all():
    """NUCLEAR RESET. Wipes paper trade history, Lucid balance state, pause
    flag, snapshots, signal events -- everything that accumulates per-account
    runtime state. Also deletes orphan account_2/account_3 directories on
    the persistent volume.

    Requires ?confirm=YES guard so it can't trigger accidentally. After this
    runs, the bot starts a NEW Lucid account at $50,000 with zero trade
    history on its next cycle.
    """
    import shutil
    if request.args.get("confirm") != "YES":
        return jsonify({
            "ok": False,
            "error": "confirmation required",
            "hint": "POST /api/admin/reset_all?confirm=YES&password=...",
        }), 400
    # Password gate -- prevents accidental resets even if someone hits the
    # endpoint directly. Keep simple; this is a single-user dashboard.
    if request.args.get("password") != "Pepp3r06":
        return jsonify({
            "ok": False,
            "error": "invalid password",
        }), 401

    from bot.account_ctx import data_dir, _LEGACY_DATA
    base = data_dir()
    # First, wipe trade rows via the persistence helper. Does DELETE+VACUUM
    # (safe under concurrent bot writes) rather than relying on file unlink,
    # which is unreliable while the bot may hold the DB open. Falls back to
    # unlink internally if DELETE fails.
    rows_wiped = 0
    try:
        rows_wiped = persistence.wipe_all_trades()
    except Exception as e:
        logger.warning(f"reset_all: wipe_all_trades failed: {e!r}")
    # Files to delete from the active account's dir. Note paper_trades.db
    # is still listed for the case where the bot is dead and we can't
    # rely on the persistence wipe -- unlink as a belt-and-braces.
    targets = [
        "paper_trades.db",
        "lucid_account.json",        # current name
        "lucid_state.json",          # legacy name (may also exist)
        "dashboard_data.json",
        "manual_pause.json",
        "signal_events.json",
        "live_bars.json",
        "bot_heartbeat.txt",
        "bot_crash.txt",
        "kelly_state.json",
    ]
    deleted = []
    errors = []
    for name in targets:
        p = base / name
        if p.exists():
            try:
                p.unlink()
                deleted.append(str(p))
            except Exception as e:
                errors.append(f"{p}: {e!r}")
    # Nuke orphan account_2/3 dirs on the persistent volume.
    for aid in ("2", "3"):
        d = _LEGACY_DATA / f"account_{aid}"
        if d.exists() and d.is_dir():
            try:
                shutil.rmtree(d)
                deleted.append(str(d) + "/ (entire dir)")
            except Exception as e:
                errors.append(f"{d}: {e!r}")
    # Also wipe the persisted broker trade history JSONL. The dashboard
    # builds its "broker mode" Activity / Performance / Trades tabs from
    # the merge of (live Tradovate FillPairs API) + this JSONL, so if we
    # leave the JSONL alone the user sees stale pre-reset broker trades
    # under the new strategy's stats. Tradovate's server-side account
    # state is unaffected -- we only remove the bot's local cache.
    try:
        from bot.tradovate_client import get_session
        sess = get_session()
        if sess.is_configured:
            acct_id = sess.get_account_id()
            if acct_id is not None:
                bp = _broker_history_path(acct_id)
                if bp.exists():
                    try:
                        bp.rename(bp.with_suffix(".jsonl.bak"))
                        deleted.append(str(bp) + " (renamed to .bak)")
                    except Exception:
                        try:
                            bp.unlink()
                            deleted.append(str(bp))
                        except Exception as e:
                            errors.append(f"{bp}: {e!r}")
    except Exception as e:
        logger.warning(f"reset_all: broker history wipe skipped: {e!r}")
    # Optional ?starting_balance=NNNNN to start the bot at a non-default
    # balance (e.g. align with a broker account that lost some equity
    # before reset). Must be > 0. Default behaviour (omit param) = $50k.
    custom_balance = None
    sb_param = request.args.get("starting_balance")
    if sb_param:
        try:
            v = float(sb_param)
            if v > 0:
                custom_balance = v
        except Exception:
            pass
    # Write a fresh lucid_account.json immediately so the dashboard's
    # reset-cutoff filter (_reset_cutoff_ts) starts working RIGHT NOW,
    # not after the bot processes the flag. If the bot is paused or
    # slow to consume the flag, the dashboard would otherwise keep
    # showing pre-reset trades indefinitely. The bot's own
    # _hard_reset_all will overwrite this with its full state on the
    # next tick; until then it's a placeholder that pins started_at
    # to "now" so trade filtering is correct.
    try:
        from bot.lucid_account import START_BAL, INITIAL_TRAIL, RESET_SERIAL
        reset_now_iso = datetime.now(timezone.utc).isoformat()
        bal = float(custom_balance) if custom_balance is not None else float(START_BAL)
        trail = bal - (START_BAL - INITIAL_TRAIL)
        lp = base / "lucid_account.json"
        lp.write_text(json.dumps({
            "account_id": 1,
            "started_at": reset_now_iso,
            "peak_eod_high": bal,
            "trail_floor": trail,
            "trail_locked": True,
            "cum_pnl_closed_days": 0.0,
            "today_pnl": 0.0,
            "today_date": reset_now_iso[:10],
            "n_trading_days": 0,
            "micro_total_profit": 0.0,
            "micro_short_profit": 0.0,
            "blown": False,
            "blow_reason": None,
            "applied_reset_serial": RESET_SERIAL,
            "auto_pause_armed": True,
            "balance": bal,
        }, indent=2))
        deleted.append(str(lp) + f" (rewritten as fresh @ ${bal:,.0f})")
    except Exception as e:
        errors.append(f"lucid_account.json rewrite: {e!r}")
    # Drop a flag file so the running bot's _tick loop picks up the reset
    # on its next cycle (within ~1 sec when flat, ~10 sec when in a trade)
    # and wipes its in-memory state too. Without this, the bot would keep
    # writing its stale in-memory state right back to disk. The flag file
    # contains the ISO timestamp on line 1 and (optionally) the custom
    # starting balance on line 2.
    try:
        flag = base / "reset_pending.flag"
        flag.parent.mkdir(parents=True, exist_ok=True)
        body = datetime.now(timezone.utc).isoformat()
        if custom_balance is not None:
            body += f"\n{custom_balance}"
        flag.write_text(body)
        deleted.append(str(flag) + " (created, bot will consume)")
    except Exception as e:
        errors.append(f"reset_pending.flag: {e!r}")
    return jsonify({
        "ok": True,
        "msg": "Account reset. Bot will wipe in-memory state on next tick.",
        "account": data_dir().name,
        "rows_wiped": rows_wiped,
        "deleted": deleted,
        "errors": errors,
        "next_steps": [
            "Reload the dashboard in ~5-10s to see the fresh $50k balance",
            "If the bot is not running, redeploy on Railway",
        ],
    })


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
                "profile": thesis_for(s["name"], s["side"]),
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
