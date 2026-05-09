"""
v11 Signal Engine — lean replacement for SignalEngine.

Drop-in interface (same evaluate() signature, returns TradeCandidate or None)
but built ONLY around the 119 user-pass v11 NQ-ES stat-arb strategies.

NO VPIN, regime, ML, alt-data, kill-zone, cooldown filters here. Lucid risk
(trail, DLL, post-loss cooldown) lives in the Runtime layer; this engine only
detects fires and returns the best one.

Per-bar evaluation:
  1. Compute Z-score for each unique window (10–120 bars)
  2. Iterate 117 profitable strategies; collect ones whose context matches
     the current NY-time bucket AND whose Z-trigger crossed
  3. If multiple fire on the same bar: pick highest-Sharpe (best historical
     edge wins the position slot)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from research.indicators import atr
from research.signal_engine import TradeCandidate
from research.v11_signals import (
    V11Strategy, V11State, load_v11_strategies, summary_stats,
)

logger = logging.getLogger("v11_engine")

# Slippage assumptions match the mining backtest exactly.
SLIPPAGE_PT = 2.0
ADVERSE_SLIP_PT = 2.0


class V11Engine:
    """Lean engine that runs v11 NQ-ES strategies on 5-min bars."""

    def __init__(self, min_pf: float = 1.0, require_cpcv: int = 0):
        self.strategies = load_v11_strategies(min_pf=min_pf,
                                                  require_cpcv=require_cpcv)
        if not self.strategies:
            raise RuntimeError("no v11 strategies loaded — check mined_v11_patterns.json")
        self.state = V11State(self.strategies)
        # Lookup table for distance-to-trigger views
        self._strategy_by_name = {s.name: s for s in self.strategies}
        # Track the most recent bar timestamp we've emitted a signal for
        # so we don't double-fire on the same bar
        self._last_signal_bar_ts: Optional[pd.Timestamp] = None

        logger.info(f"[v11_engine] loaded {len(self.strategies)} strategies "
                      f"({sum(1 for s in self.strategies if s.side=='LONG')} LONG, "
                      f"{sum(1 for s in self.strategies if s.side=='SHORT')} SHORT)")
        logger.info(f"[v11_engine] z_windows: {self.state.windows}")

    # ----------------------------------------------------------------------- #
    # Public per-bar API                                                      #
    # ----------------------------------------------------------------------- #
    def update_state(self,
                       intraday_5m: pd.DataFrame,
                       es_5m: pd.DataFrame,
                       rty_5m: Optional[pd.DataFrame] = None,
                       vix_5m: Optional[pd.DataFrame] = None,
                      ) -> tuple[Optional[pd.Timestamp], float]:
        """Refresh Z-scores + ATR. Always run, even if no fire."""
        max_w = max((max(ws) for ws in self.state.windows_by_family.values() if ws),
                       default=120)
        if len(intraday_5m) < max_w + 200:
            return None, float("nan")
        atr_series = None
        atr_value = float("nan")
        try:
            atr_series = atr(intraday_5m["high"], intraday_5m["low"],
                                intraday_5m["close"], n=14)
            atr_value = float(atr_series.iloc[-1])
        except Exception as e:
            logger.warning(f"[v11_engine] ATR calc failed: {e}")
        self.state.update_from_history(intraday_5m, es_5m,
                                            atr_series=atr_series,
                                            rty_5m=rty_5m, vix_5m=vix_5m)
        return intraday_5m.index[-1], atr_value

    def evaluate(self,
                   intraday_5m: pd.DataFrame,    # NQ 5-min bars
                   es_5m: pd.DataFrame,          # ES 5-min bars
                   prior_trades: list = None,    # not used (Lucid handles)
                   rty_5m: Optional[pd.DataFrame] = None,
                   vix_5m: Optional[pd.DataFrame] = None,
                  ) -> Optional[TradeCandidate]:
        """Process the most-recent 5-min bar; return a TradeCandidate or None."""
        bar_ts, atr_value = self.update_state(intraday_5m, es_5m,
                                                  rty_5m=rty_5m, vix_5m=vix_5m)
        if bar_ts is None:
            return None
        if self._last_signal_bar_ts is not None and bar_ts <= self._last_signal_bar_ts:
            return None  # already evaluated this bar
        if np.isnan(atr_value) or atr_value <= 0:
            return None

        # NY time of the bar (mining uses NY local time for context)
        ny = bar_ts.tz_convert("America/New_York")
        ny_hour = int(ny.hour)
        ny_min = int(ny.minute)

        # Evaluate strategies; pick highest-Sharpe winner
        fired = self.state.evaluate_strategies(ny_hour, ny_min)
        if not fired:
            return None
        fired.sort(key=lambda f: -f["strategy"].test_sharpe)
        winner = fired[0]
        s = winner["strategy"]
        z_value = winner["z_value"]

        # Build TradeCandidate. Entry will be filled at next-bar open in the
        # account layer, but we record the signal-bar close as the reference.
        bar_close = float(intraday_5m["close"].iloc[-1])
        stop_pts = s.stop_atr * atr_value
        target_pts = s.target_atr * atr_value
        if s.side == "LONG":
            stop_px = bar_close - stop_pts
            target_px = bar_close + target_pts
        else:
            stop_px = bar_close + stop_pts
            target_px = bar_close - target_pts

        self._last_signal_bar_ts = bar_ts

        return TradeCandidate(
            signal_name=s.name,
            side=s.side,
            signal_time=bar_ts,
            entry_px=bar_close,
            stop_px=stop_px,
            target_px=target_px,
            stop_pts=stop_pts,
            rr=s.target_atr / s.stop_atr,
            vol_regime="UNKNOWN",
            daily_bias="UNKNOWN",
            # Encode the strategy's historical edge as a "confidence" so
            # downstream code that wants a 0-1 metric has something to read.
            ml_confidence=min(1.0, max(0.0, s.test_wr)),
            ml_decision="AGREE",
            size_mult=1.0,
            contracts=25,                           # Lucid-runtime will override
            hmm_state="UNKNOWN",
            vpin=0.0,
            adverse_selection=0.0,
            stat_arb_zscore=float(z_value),
            filter_trace=[
                f"family={s.family}  ctx={s.time_context}",
                f"z[{s.family},{s.z_window}]={z_value:+.2f}",
                f"trigger={'<' if s.side=='LONG' else '>'}±{s.z_threshold}",
                f"ATR={atr_value:.2f} stop={stop_pts:.1f} target={target_pts:.1f}",
                f"hist_WR={s.test_wr*100:.0f}% PF={s.test_pf:.2f} Sharpe={s.test_sharpe:.2f}",
            ],
        )

    # ----------------------------------------------------------------------- #
    # Dashboard helpers                                                       #
    # ----------------------------------------------------------------------- #
    def summary(self) -> dict:
        return summary_stats(self.strategies)

    def closest_to_trigger(self, top_n: int = 10) -> list[dict]:
        """Strategies CLOSEST to firing on the most recent bar (for Brain tab).

        Pulls the current NY-time of the latest bar so each row can mark
        whether its time-window is currently active — distinguishing real
        FIRED from "Z crossed but waiting for the right time of day."
        """
        bar_ts = self.state.last_bar_ts
        if bar_ts is None:
            return self.state.distance_to_trigger(top_n=top_n)
        ny = bar_ts.tz_convert("America/New_York")
        return self.state.distance_to_trigger(top_n=top_n,
                                                  ny_hour=int(ny.hour),
                                                  ny_min=int(ny.minute))

    def current_z_scores(self) -> dict[int, float]:
        """Live Z values per window — returns the ES family by default
        (back-compat with the old Brain-tab card layout). For multi-family
        Z-scores see current_z_scores_by_family()."""
        return dict(self.state.z_current.get("es", {}))

    def current_z_scores_by_family(self) -> dict[str, dict[int, float]]:
        """Multi-family Z-scores: {'es': {15: -0.5, ...}, 'vix': {...}}"""
        return {fam: dict(zs) for fam, zs in self.state.z_current.items()}

    def vix_regime_state(self) -> dict[str, float]:
        """Current VIX percentile + Z-score for the dashboard."""
        return {
            "vix_pct": self.state.vix_pct_current,
            "vix_z": self.state.vix_z_current,
        }

    def strategies_table(self) -> list[dict]:
        """Strategies tab data."""
        rows = []
        for s in self.strategies:
            rows.append({
                "name": s.name,
                "side": s.side,
                "z_window": s.z_window,
                "z_threshold": s.z_threshold,
                "time_ctx": s.time_context,
                "stop_atr": s.stop_atr,
                "target_atr": s.target_atr,
                "rr": s.target_atr / s.stop_atr,
                "max_hold_min": s.max_hold_min,
                "test_n": s.test_n,
                "test_wr": s.test_wr,
                "test_pf": s.test_pf,
                "test_sharpe": s.test_sharpe,
                "test_net_1mnq": s.test_net,
                "cpcv": s.cpcv_positive,
            })
        return rows

    def strategy_by_name(self, name: str) -> Optional[V11Strategy]:
        return self._strategy_by_name.get(name)
