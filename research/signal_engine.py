"""
Live signal engine for the paper bot.

Loads the validated-signal whitelist from data/validation_results.json (only
signals with `recommended=True`), pulls latest bars on demand, runs only those
signals through the same filters as the backtester, then asks the ML model to
confirm direction.

Returns at most one TradeCandidate per cycle.  Caller decides whether to
actually open the trade (based on current open position, cooldown of all
realised trades, etc.).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from research.adverse_selection_detector import (
    AdverseSelectionSnapshot,
    adverse_selection_filter,
    compute_adverse_selection,
)
from research.alternative_data import MacroSnapshot, compute_macro, macro_filter
from research.data_loader import DATA_DIR, download_nq
from research.execution_optimizer import signal_half_life_ok
from research.gex_calculator import (
    GEXSnapshot,
    gex_filter,
    load_cached_snapshot as load_gex_cache,
)
from research.indicators import eq50
from research.ml_model import (
    build_features,
    confirm_direction,
    load_model,
    predict_probs,
)
from research.position_sizer import size_position
from research.regime_detector import RegimeDetector, RegimeSnapshot, regime_filter
from research.signal_filters import (
    SLIPPAGE_POINTS,
    TradeRef,
    cooldown_filter,
    daily_bias_at,
    daily_bias_filter,
    derive_target,
    key_level_proximity_filter,
    kill_zone_filter,
    min_rr_filter,
    vol_regime_at,
)
from research.signal_generator import ALL_SIGNALS as _CORE_SIGNALS, _attach_prev_day_levels


def _load_all_signals():
    """Concatenate validated 5-min set + v3 gold-standard + WR survivors."""
    all_sigs = list(_CORE_SIGNALS)
    try:
        from research.mined_v3_signals import ALL_V3_SIGNALS
        all_sigs.extend(ALL_V3_SIGNALS)
    except Exception as e:
        logger.warning(f"v3 signals unavailable: {e!r}")
    try:
        from research.mined_wr_signals import ALL_WR_SIGNALS
        all_sigs.extend(ALL_WR_SIGNALS)
    except Exception as e:
        logger.warning(f"WR signals unavailable: {e!r}")
    return all_sigs


ALL_SIGNALS = _load_all_signals()
from research.vpin_calculator import VPINSnapshot, compute_vpin, vpin_filter

logger = logging.getLogger("signal_engine")

VALIDATION_PATH = DATA_DIR / "validation_results.json"


# ---------------------------------------------------------------------------
# Trade candidate
# ---------------------------------------------------------------------------

@dataclass
class TradeCandidate:
    signal_name: str
    side: str                  # LONG | SHORT
    signal_time: pd.Timestamp  # bar close that triggered the signal
    entry_px: float            # the bar's close (we'll fill at next-bar open + slip)
    stop_px: float
    target_px: float
    stop_pts: float
    rr: float
    vol_regime: str
    daily_bias: str
    ml_confidence: float       # the directional probability (p_bull or p_bear)
    ml_decision: str           # AGREE | REDUCE | REJECT
    size_mult: float           # 1.0 = full, 0.5 = half (REDUCE), 0 = skip
    # Institutional-grade filter metadata
    contracts: int = 30                   # sized by Kelly + multipliers
    hmm_state: str = "UNKNOWN"            # LOW_VOL / NORMAL_VOL / HIGH_VOL
    vpin: float = 0.0                     # 0..1
    adverse_selection: float = 0.0        # 0..1
    stat_arb_zscore: float = 0.0          # context
    filter_trace: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class SignalEngine:
    def __init__(self,
                 validation_path: Path = VALIDATION_PATH,
                 confirm_threshold: float = 0.55):
        self.validation_path = validation_path
        self.confirm_threshold = confirm_threshold

        self.whitelist: set[str] = self._load_whitelist()
        if not self.whitelist:
            logger.warning(
                "[engine] no recommended signals in %s — bot will be flat until validation reruns",
                validation_path,
            )
        else:
            logger.info("[engine] whitelist (%d): %s", len(self.whitelist), sorted(self.whitelist))

        # Load ML model + metadata.
        try:
            self.ml_model, self.ml_meta = load_model()
            logger.info("[engine] ML model loaded (test_acc=%.3f)",
                        self.ml_meta.get("test_acc", float("nan")))
        except FileNotFoundError:
            self.ml_model = None
            self.ml_meta = None
            logger.warning("[engine] ML model not found — falling back to AGREE for all signals")

        # Regime detector (loads cached GMM model if present)
        self.regime_detector = RegimeDetector()
        if self.regime_detector.load():
            logger.info("[engine] regime model loaded")
        else:
            logger.warning("[engine] no regime model found — regime filter will no-op until trained")

        # Cached snapshots (updated on each evaluate())
        self.last_vpin: VPINSnapshot | None = None
        self.last_adverse: AdverseSelectionSnapshot | None = None
        self.last_regime: RegimeSnapshot | None = None
        self.last_gex: GEXSnapshot | None = None
        self.last_macro: MacroSnapshot | None = None
        # Counter so we only recompute slow alt-data signals occasionally
        self._slow_cycle_counter = 0

    # ----- whitelist -------------------------------------------------------

    def _load_whitelist(self) -> set[str]:
        if not self.validation_path.exists():
            return set()
        try:
            data = json.loads(self.validation_path.read_text())
        except Exception as e:
            logger.error("[engine] failed to parse %s: %s", self.validation_path, e)
            return set()
        recs = {
            name for name, info in data.get("signals", {}).items()
            if info.get("recommended") is True
        }
        return recs

    def reload_whitelist(self) -> None:
        """Re-read validation_results.json (call after a research re-run)."""
        self.whitelist = self._load_whitelist()
        logger.info("[engine] whitelist reloaded (%d): %s",
                    len(self.whitelist), sorted(self.whitelist))

    # ----- main entry ------------------------------------------------------

    def evaluate(self,
                 intraday: pd.DataFrame,
                 daily: pd.DataFrame,
                 prior_trades: list[TradeRef] | None = None,
                 ) -> Optional[TradeCandidate]:
        """
        Run all whitelisted signals on the latest data; return at most one
        TradeCandidate that passes every filter (including the new
        institutional-grade filters: VPIN, adverse selection, regime).
        """
        if not self.whitelist:
            return None
        if intraday.empty or daily.empty:
            return None

        # Precompute attached levels and eq50 once.
        df = _attach_prev_day_levels(intraday, daily)
        df["eq50"] = eq50(df["high"], df["low"], 50)

        self.refresh_microstructure(intraday, daily)

        prior_trades = prior_trades or []
        candidates: list[TradeCandidate] = []

        for sig_obj in ALL_SIGNALS:
            try:
                sigs = sig_obj.generate(intraday, daily)
            except Exception as e:
                logger.warning("[engine] signal %s raised: %s", type(sig_obj).__name__, e)
                continue
            if sigs.empty:
                continue
            # Only the very latest bar matters for live decisions.
            latest_ts = df.index[-1]
            recent = sigs[sigs["signal_time"] == latest_ts]
            for _, row in recent.iterrows():
                cand = self._evaluate_row(row, df, daily, prior_trades)
                if cand is not None:
                    candidates.append(cand)

        if not candidates:
            return None
        # Prefer AGREE > REDUCE; tie-break by RR.
        candidates.sort(key=lambda c: (0 if c.ml_decision == "AGREE" else 1, -c.rr))
        return candidates[0]

    def refresh_microstructure(self, intraday: pd.DataFrame, daily: pd.DataFrame) -> None:
        """Recompute VPIN/adverse/regime + nudge slow-refresh alt data.

        Safe to call every tick — cheap on cached data. Extracted so the meter
        on the dashboard sees fresh values even when the bar-change guard
        prevents a full evaluate().
        """
        if intraday.empty or daily.empty:
            return
        try:
            self.last_vpin = compute_vpin(intraday)
            self.last_adverse = compute_adverse_selection(intraday)
            self.last_regime = self.regime_detector.predict(daily)
        except Exception as e:
            logger.warning("[engine] microstructure refresh failed: %s", e)
        self._slow_cycle_counter += 1
        try:
            # Refresh every tick (60s). GEX just reads a disk cache — cheap.
            # compute_macro() hits cached snapshots for COT/insider/WSB etc.
            # so it's fast when caches are warm.
            self.last_gex = load_gex_cache()
            self.last_macro = compute_macro()
        except Exception as e:
            logger.warning("[engine] alt-data refresh failed: %s", e)

    # Snapshot accessors for the main loop / dashboard
    def snapshot_microstructure(self) -> dict:
        out: dict = {}
        if self.last_vpin:
            out["vpin"] = {
                "value": self.last_vpin.vpin,
                "regime": self.last_vpin.regime,
                "trend": self.last_vpin.trend,
                "spike": self.last_vpin.spike_detected,
                "reversal_signal": self.last_vpin.reversal_signal,
                "crash_warning": self.last_vpin.crash_warning,
            }
        if self.last_adverse:
            out["adverse_selection"] = {
                "score": self.last_adverse.score,
                "regime": self.last_adverse.regime,
                "spread_ratio": self.last_adverse.spread_ratio,
                "serial_correlation": self.last_adverse.serial_correlation,
                "market_shutdown": self.last_adverse.market_shutdown,
            }
        if self.last_regime:
            out["regime"] = {
                "state": self.last_regime.state,
                "confidence": self.last_regime.confidence,
                "transition_risk": self.last_regime.transition_risk,
                "probs": self.last_regime.probs,
            }
        if self.last_gex:
            out["gex"] = {
                "regime": self.last_gex.regime,
                "total_gex_billion": self.last_gex.total_gex / 1e9,
                "intensity_pct": self.last_gex.intensity_percentile,
                "zero_gamma_nq": self.last_gex.zero_gamma_nq,
                "magnets_nq": self.last_gex.magnets_nq,
            }
        else:
            out["gex"] = None
        if self.last_macro:
            out["macro"] = {
                "score": self.last_macro.macro_score,
                "bias": self.last_macro.bias,
                "components": self.last_macro.components,
                "components_available": self.last_macro.components_available,
                "details": self.last_macro.details,
            }
        return out

    # ----- per-row filter chain -------------------------------------------

    def _evaluate_row(self,
                      sig: pd.Series,
                      df: pd.DataFrame,
                      daily: pd.DataFrame,
                      prior_trades: list[TradeRef]) -> Optional[TradeCandidate]:
        name = sig["signal_name"]
        if name not in self.whitelist:
            return None

        side = sig["side"]
        sig_time = sig["signal_time"]
        entry_px = float(sig["entry_px"])
        trace: list[str] = []

        # -------- Filter 1: VPIN gate ---------
        ok, reason, vpin_mult = vpin_filter(self.last_vpin, side)
        trace.append(f"vpin: {reason}")
        if not ok:
            logger.info("[engine] %s rejected: %s", name, reason)
            return None

        # -------- Filter 2: Adverse-selection gate ---------
        ok, reason, as_mult = adverse_selection_filter(self.last_adverse, side)
        trace.append(f"adverse: {reason}")
        if not ok:
            logger.info("[engine] %s rejected: %s", name, reason)
            return None

        # -------- Filter 2b: GEX regime ---------
        ok, reason, gex_mult = gex_filter(self.last_gex, side)
        trace.append(f"gex: {reason}")
        if not ok:
            return None

        # -------- Filter 2c: Macro (alternative data) ---------
        ok, reason, macro_mult = macro_filter(self.last_macro, side)
        trace.append(f"macro: {reason}")
        if not ok:
            return None

        # -------- Filter 3: HMM regime ---------
        regime_size_mult = 1.0
        regime_stop_mult = 1.0
        if self.last_regime and self.last_regime.is_trained:
            ok, reason, regime_size_mult, regime_stop_mult = regime_filter(
                self.last_regime, name
            )
            trace.append(f"regime: {reason}")
            if not ok:
                logger.info("[engine] %s rejected: %s", name, reason)
                return None
        else:
            trace.append("regime: untrained")

        # -------- Daily bias -----------
        bias = daily_bias_at(daily, sig_time)
        ok, _ = daily_bias_filter(side, bias, name)
        trace.append(f"bias: {bias}")
        if not ok:
            return None

        vol = vol_regime_at(daily, sig_time)
        # Apply regime stop multiplier to vol.stop_pts
        stop_pts_effective = vol.stop_pts * regime_stop_mult

        # -------- Kill zone ------------
        ok, reason = kill_zone_filter(name, sig_time)
        trace.append(f"killzone: {reason}")
        if not ok:
            return None

        # -------- Level proximity ------
        try:
            row = df.loc[sig_time]
        except KeyError:
            return None
        pdh = float(row["pdh"]) if pd.notna(row["pdh"]) else float("nan")
        pdl = float(row["pdl"]) if pd.notna(row["pdl"]) else float("nan")
        eq_v = float(row["eq50"]) if pd.notna(row["eq50"]) else float("nan")

        ok, reason = key_level_proximity_filter(name, entry_px, pdh, pdl, eq_v)
        trace.append(f"proximity: {reason}")
        if not ok:
            return None

        # -------- Target + R:R ---------
        target_px = derive_target(name, side, entry_px, pdh, pdl, eq_v,
                                  sig.get("target_hint", float("nan")))
        ok, reason, rr = min_rr_filter(name, side, entry_px, stop_pts_effective, target_px)
        trace.append(f"rr: {reason}")
        if not ok:
            return None

        # -------- Cooldown -------------
        ok, reason = cooldown_filter(sig_time, prior_trades)
        trace.append(f"cooldown: {reason}")
        if not ok:
            return None

        if side == "LONG":
            stop_px = entry_px - stop_pts_effective
        else:
            stop_px = entry_px + stop_pts_effective

        # -------- ML confirmation ------
        ml_conf, ml_decision, ml_size_mult = self._ml_confirm(df, sig_time, side)
        trace.append(f"ml: {ml_decision} conf={ml_conf:.2f}")
        if ml_decision == "REJECT":
            logger.info("[engine] %s %s REJECTED by ML (conf=%.2f)", name, side, ml_conf)
            return None

        # -------- Kelly sizing with all multipliers ---------
        sizing = size_position(
            signal_name=name,
            stop_pts=stop_pts_effective,
            ml_confidence=ml_conf,
            regime_mult=regime_size_mult,
            vpin_mult=vpin_mult,
            adverse_selection_mult=as_mult,
            macro_mult=macro_mult * gex_mult,  # combine macro + gex
        )
        trace.append(f"size: {sizing.contracts}c ({sizing.reason})")
        if sizing.contracts == 0:
            return None

        # Effective legacy size_mult for compatibility with main.py scaling
        size_mult_legacy = (ml_size_mult * vol.size_mult * regime_size_mult *
                            vpin_mult * as_mult * gex_mult * macro_mult)

        return TradeCandidate(
            signal_name=name,
            side=side,
            signal_time=sig_time,
            entry_px=entry_px,
            stop_px=stop_px,
            target_px=target_px,
            stop_pts=stop_pts_effective,
            rr=float(rr),
            vol_regime=vol.regime,
            daily_bias=bias,
            ml_confidence=float(ml_conf),
            ml_decision=ml_decision,
            size_mult=float(size_mult_legacy),
            contracts=sizing.contracts,
            hmm_state=self.last_regime.state if self.last_regime else "UNKNOWN",
            vpin=self.last_vpin.vpin if self.last_vpin else 0.0,
            adverse_selection=self.last_adverse.score if self.last_adverse else 0.0,
            filter_trace=trace,
        )

    # ----- ML confirm ------------------------------------------------------

    def _ml_confirm(self, df: pd.DataFrame, sig_time: pd.Timestamp,
                    side: str) -> tuple[float, str, float]:
        """Returns (directional_confidence, decision, size_mult)."""
        if self.ml_model is None:
            return (1.0, "AGREE", 1.0)
        try:
            feats = build_features(df, df)  # daily not used by features beyond pdh/pdl already attached
        except Exception as e:
            logger.warning("[engine] feature build failed: %s — defaulting AGREE", e)
            return (1.0, "AGREE", 1.0)
        if sig_time not in feats.index:
            return (1.0, "AGREE", 1.0)
        row = feats.loc[sig_time]
        p_bear, p_neutral, p_bull = predict_probs(self.ml_model, self.ml_meta, row)
        if p_bear != p_bear:  # NaN -> default
            return (1.0, "AGREE", 1.0)
        decision = confirm_direction(p_bear, p_neutral, p_bull, side, self.confirm_threshold)
        directional = p_bull if side == "LONG" else p_bear
        size_mult = {"AGREE": 1.0, "REDUCE": 0.5, "REJECT": 0.0}[decision]
        return (directional, decision, size_mult)


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------

def _main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    intraday = download_nq("5min")
    daily = download_nq("daily")
    eng = SignalEngine()
    cand = eng.evaluate(intraday, daily, prior_trades=[])
    if cand is None:
        print("no candidate this cycle.")
    else:
        print(f"candidate: {cand}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
