"""Builds the per-trade feature snapshot from MarketContext + bars + setup.

Single source of truth for "what context did the bot see at the moment
this trade fired?" Used by:
  - bot/fib_main.py at trade-open time to populate the trade DB
  - eventual ML training pipeline as the input feature row

All fields are best-effort. Missing data = None (NULL in SQL). Missing
data is information, not an error.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from engine.market_context import MarketContext

# Session label heuristic (US Eastern hour bucket)
def _classify_session(et_hour: int, et_minute: int) -> str:
    if 18 <= et_hour or et_hour < 3:        return "asia"
    if 3 <= et_hour < 9:                    return "london"
    # US sessions
    if et_hour == 9 and et_minute < 30:     return "pre_us_open"
    if et_hour == 9 and et_minute >= 30:    return "us_open"
    if 10 <= et_hour < 12:                  return "us_morning"
    if 12 <= et_hour < 13:                  return "us_lunch"
    if 13 <= et_hour < 15:                  return "us_afternoon"
    if 15 <= et_hour < 16:                  return "us_close"
    if 16 <= et_hour < 18:                  return "post_us_close"
    return "unknown"


def build_trade_feature_snapshot(setup, ctx: MarketContext,
                                    *, qty: int = 2,
                                    entry_ts: Optional[datetime] = None) -> dict:
    """Returns a dict ready to pass into persistence.insert_trade_with_features.

    Args:
      setup: anything with attributes .side, .entry_price, .stop_price,
             .target_price, .impulse_pts, .impulse_high, .impulse_low,
             .strategy_name. Also works with bot/pullback_strategy.FibSetup
             which has slightly different attribute names (mapped via
             getattr fallback).
      ctx: a MarketContext (extended with .macro, .structure, .next_news_event)
      qty: position size
      entry_ts: fill time (default = ctx.now)
    """
    now = entry_ts or ctx.now

    # ---- Strategy / setup fields -------------------------------------
    side = (getattr(setup, "side", None) or "")
    if hasattr(side, "value"):
        side = side.value
    entry_px = (getattr(setup, "entry_price", None)
                 or getattr(setup, "pullback_entry", None))
    stop_px  = (getattr(setup, "stop_price", None)
                 or getattr(setup, "stop_px_val", None))
    target_px = (getattr(setup, "target_price", None)
                  or getattr(setup, "target_px_val", None))
    impulse_pts = getattr(setup, "impulse_pts", None)
    imp_high = (getattr(setup, "impulse_high", None) or
                getattr(setup, "impulse_high_val", None))
    imp_low  = (getattr(setup, "impulse_low", None) or
                getattr(setup, "impulse_low_val", None))
    impulse_range = (imp_high - imp_low) if imp_high and imp_low else None
    strat_name = getattr(setup, "strategy_name", None) or "pullback_impulse"

    out = {
        # Required by insert_trade_with_features
        "signal_name": strat_name,
        "side":        side,
        "entry_time":  (entry_ts or now).isoformat() if hasattr(now, "isoformat") else str(now),
        "entry_px":    entry_px,
        "stop_px":     stop_px,
        "target_px":   target_px,
        "qty":         int(qty),
        # Strategy reasoning
        "impulse_pts":       impulse_pts,
        "impulse_range_pts": round(impulse_range, 2) if impulse_range else None,
        # Volatility
        "atr_5_at_entry":  ctx.atr_5,
        "atr_60_at_entry": ctx.atr_60,
        "vol_ratio":       round(ctx.vol_ratio, 3),
        # Regime label (coarse)
        "regime":          _coarse_regime(ctx),
        # Time / session
        "session":         _classify_session(ctx.et_hour,
                                              getattr(ctx, "et_minute", 0)
                                              if hasattr(ctx, "et_minute") else now.minute),
        "et_hour":         ctx.et_hour,
        "et_minute":       getattr(ctx, "et_minute", now.minute),
        "day_of_week":     now.weekday() if hasattr(now, "weekday") else None,
    }

    # ---- News context ---------------------------------------------------
    evt = getattr(ctx, "next_news_event", None)
    if evt is not None:
        try:
            out["news_minutes_until"] = int(evt.minutes_until(ctx.now))
            out["news_title"]         = evt.title
            out["news_importance"]    = evt.impact
        except Exception:
            pass

    # ---- Cross-market ---------------------------------------------------
    macro = getattr(ctx, "macro", None)
    if macro is not None:
        out["vix"]                  = getattr(macro, "vix", None)
        out["vix_change_5m_pct"]    = getattr(macro, "vix_change_5m_pct", None)
        out["nq_es_spread_5m_pct"]  = getattr(macro, "nq_es_spread_5m_pct", None)
        out["dxy_change_60m_pct"]   = getattr(macro, "dxy_change_60m_pct", None)
        try:
            out["macro_alignment_score"] = round(macro.alignment_score(side), 3)
        except Exception:
            pass

    # ---- Session structure ---------------------------------------------
    struct = getattr(ctx, "structure", None)
    if struct is not None and entry_px is not None:
        try:
            out["nearest_level"] = struct.nearest_level(entry_px, threshold_pts=3.0)
            if out["nearest_level"]:
                d = struct.distance_to(entry_px, out["nearest_level"])
                out["distance_to_level_pts"] = round(d, 2) if d is not None else None
            ivab = struct.in_value_area(entry_px)
            if ivab is not None:
                out["in_value_area"] = 1 if ivab else 0
            apdh = struct.above_pdh(entry_px)
            if apdh is not None:
                out["above_pdh"] = 1 if apdh else 0
            if struct.vwap is not None:
                out["vwap_distance_pts"] = round(entry_px - struct.vwap, 2)
        except Exception:
            pass

    return out


def _coarse_regime(ctx: MarketContext) -> str:
    """Cheap regime label without ML. Combines vol_ratio + time of day."""
    if ctx.is_news_window:
        return "news"
    if ctx.is_fast_market:
        return "fast"
    if ctx.vol_ratio < 0.5:
        return "quiet_pre_storm"
    if ctx.is_us_open_15min:
        return "us_open"
    if ctx.is_us_rth:
        return "us_rth"
    return "overnight"
