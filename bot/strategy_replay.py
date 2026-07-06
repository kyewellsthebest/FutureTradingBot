"""Server-side strategy replay: what SHOULD paper have made, day by day.

Drives the REAL strategy (bot.pullback_strategy.on_new_1m_bar) over the
last N days of Polygon 1-minute bars with the live env params, a fresh
LucidState and no news calendar -- the raw strategy with no
account-level filters. The result is embedded in the diagnostics
bundle, so every bundle carries an independent "what the strategy earns
on pure market data" baseline to compare against what live paper
actually booked. If live paper diverges from this baseline on the same
days, the paper runtime has a bug; if both decline together, it's the
market regime, not the code.

Also reports a regime metric per day: how many 1-minute bars sit at the
start of a >=TARGET_PTS move within the next 10 minutes ("target-run
density"). Days with no 44pt runs cannot produce 44pt target wins no
matter what code is running.

The replay is computed in a background thread and cached to disk
(REPLAY_TTL_S). Bundle builds never block on it: they read the latest
cache and kick off a refresh if stale.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("strategy_replay")

REPLAY_DAYS = int(os.environ.get("REPLAY_DAYS", "8"))
REPLAY_TTL_S = float(os.environ.get("REPLAY_TTL_S", "1800"))
_LOCK = threading.Lock()
_COMPUTING = False


def _cache_path():
    from bot.account_ctx import data_dir
    return data_dir() / "strategy_replay.json"


def _fetch_1m_bars(days: int):
    """Last `days` days of 1-minute bars for the live contract, via the
    same Polygon futures aggs endpoint the bot itself trades from."""
    import urllib.request
    import pandas as pd
    from research.data_loader import _polygon_key, polygon_front_month

    key = _polygon_key()
    if not key:
        raise RuntimeError("no POLYGON_API key in env")
    product = os.environ.get("POLYGON_CONTRACT", "MNQ")
    tk = os.environ.get("TRADOVATE_SYMBOL") or polygon_front_month(product)
    now_ms = int(time.time() * 1000)
    from_ms = now_ms - days * 24 * 3600 * 1000
    url = (f"https://api.polygon.io/futures/v1/aggs/{tk}"
           f"?resolution=1_minute&limit=50000"
           f"&from={from_ms}&to={now_ms}&order=asc&apiKey={key}")
    req = urllib.request.Request(url, headers={"User-Agent": "hftbot/1.0"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    rows = []
    for r in data.get("results") or []:
        try:
            ts = pd.Timestamp(int(r["window_start"]), unit="ns", tz="UTC")
            rows.append((ts, float(r["open"]), float(r["high"]),
                         float(r["low"]), float(r["close"]),
                         float(r.get("volume", 0))))
        except Exception:
            continue
    if not rows:
        raise RuntimeError(f"polygon returned no bars for {tk}")
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low",
                                     "close", "volume"]).set_index("ts")
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return tk, df


def _trade_date(ts) -> str:
    """CME trade date: sessions open 22:00/23:00 UTC the prior calendar
    day, so shift +2h and take the date."""
    return (ts + timedelta(hours=2)).strftime("%Y-%m-%d")


def _run_replay() -> dict:
    import pandas as pd
    from bot.pullback_strategy import FibStrategyState, on_new_1m_bar
    from research.lucid_guard import LucidState
    from bot.account_ctx import get_strategy_params

    t0 = time.time()
    tk, df = _fetch_1m_bars(REPLAY_DAYS)
    params = None
    try:
        params = get_strategy_params("1")
    except Exception:
        pass
    target_pts = float(os.environ.get("STRAT_TARGET_PTS",
                                      (params or {}).get("TARGET_PTS", 44.0)
                                      if isinstance(params, dict) else 44.0))

    days: dict[str, dict] = {}
    tdates = [_trade_date(ts) for ts in df.index]
    day_keys = sorted(set(tdates))
    closes = df["close"]
    # Regime: for each bar, the max |move| over the next 10 bars.
    fwd_max = pd.concat(
        [(closes.shift(-k) - closes).abs() for k in range(1, 11)],
        axis=1).max(axis=1)

    WARMUP = 240  # bars of history handed to the strategy each step
    for day in day_keys:
        day_idx = [i for i, d in enumerate(tdates) if d == day]
        if len(day_idx) < 30:
            continue
        state = FibStrategyState()
        lucid = LucidState()
        records = []
        for i in day_idx:
            window = df.iloc[max(0, i - WARMUP): i + 1]
            bar = window.iloc[-1]
            now = (df.index[i] + timedelta(seconds=60)).to_pydatetime()
            try:
                rec = on_new_1m_bar(state, lucid, window, bar, now,
                                    n_mnq=1, bars_trend=window,
                                    params=params, calendar=None)
            except Exception as e:
                logger.debug(f"replay bar {df.index[i]}: {e!r}")
                continue
            if rec is not None:
                records.append(rec)
        # Flatten anything still open at the day's last bar.
        if state.active_trade is not None:
            tr = state.active_trade
            last_px = float(df.iloc[day_idx[-1]]["close"])
            pts = ((last_px - tr.entry_px) if tr.side == "LONG"
                   else (tr.entry_px - last_px))
            records.append({"side": tr.side, "reason": "eod_flat",
                            "pnl_pts": pts, "pnl_usd": pts * 2.0})
        n = len(records)
        gross = round(sum(r.get("pnl_usd") or 0 for r in records), 2)
        exits: dict[str, int] = {}
        for r in records:
            k = str(r.get("reason") or r.get("exit_reason") or "?")
            exits[k] = exits.get(k, 0) + 1
        wins = sum(1 for r in records if (r.get("pnl_usd") or 0) > 0)
        di = [df.index[i] for i in day_idx]
        day_bars = df.loc[di]
        runs = int((fwd_max.loc[di] >= target_pts).sum())
        days[day] = {
            "n_trades": n,
            "gross_usd": gross,
            "net_usd": round(gross - 0.74 * n, 2),
            "win_pct": round(100.0 * wins / n, 1) if n else None,
            "exits": exits,
            "day_range_pts": round(float(day_bars["high"].max()
                                         - day_bars["low"].min()), 2),
            "mean_bar_range_pts": round(float(
                (day_bars["high"] - day_bars["low"]).mean()), 3),
            "target_run_bars": runs,
            "bars": len(day_idx),
        }
    return {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "ticker": tk,
        "bars_total": len(df),
        "first_bar": str(df.index[0]),
        "last_bar": str(df.index[-1]),
        "target_pts": target_pts,
        "params_source": "get_strategy_params('1')" if params else "env",
        "compute_s": round(time.time() - t0, 1),
        "days": days,
        "note": ("REAL strategy code driven bar-by-bar over Polygon 1m "
                 "bars; fresh state per trade date; no lucid/news "
                 "filters. Paper-model prices (fill at level, both "
                 "stop+target in one bar resolves to stop). Compare "
                 "net_usd against live paper's booked P&L per day."),
    }


def _refresh_worker():
    global _COMPUTING
    try:
        result = _run_replay()
        try:
            _cache_path().write_text(json.dumps(result))
        except Exception as e:
            logger.warning(f"replay cache write: {e!r}")
        logger.info(f"[strategy_replay] computed in "
                    f"{result.get('compute_s')}s: "
                    f"{len(result.get('days', {}))} days")
    except Exception as e:
        logger.warning(f"[strategy_replay] failed: {e!r}")
        try:
            _cache_path().write_text(json.dumps({
                "error": repr(e),
                "computed_at": datetime.now(timezone.utc).isoformat()}))
        except Exception:
            pass
    finally:
        with _LOCK:
            _COMPUTING = False


def get_replay(max_age_s: float = REPLAY_TTL_S) -> dict:
    """Return the cached replay, kicking off a background refresh if
    stale or missing. Never blocks the caller."""
    global _COMPUTING
    cached = None
    age = None
    try:
        p = _cache_path()
        if p.exists():
            cached = json.loads(p.read_text())
            ct = cached.get("computed_at")
            if ct:
                age = (datetime.now(timezone.utc)
                       - datetime.fromisoformat(ct)).total_seconds()
    except Exception as e:
        cached = {"error": f"cache read: {e!r}"}
    stale = age is None or age > max_age_s
    if stale:
        with _LOCK:
            if not _COMPUTING:
                _COMPUTING = True
                threading.Thread(target=_refresh_worker,
                                 name="strategy-replay",
                                 daemon=True).start()
    if cached is None:
        return {"status": "computing",
                "note": "first replay build in progress; "
                        "re-pull the bundle in ~2 minutes"}
    cached["status"] = "refreshing" if stale else "ready"
    if age is not None:
        cached["cache_age_s"] = round(age, 0)
    return cached
