"""
HMM-like regime detector — 3-state Gaussian Mixture on 8 daily features.

Features (per spec):
  1. 5-day realised volatility
  2. 10-day realised volatility
  3. 20-day realised volatility
  4. ATR / price (volatility ratio)
  5. 20-day momentum
  6. 5-day volume / 20-day volume ratio
  7. Gap size (open vs prev close, pct)
  8. Daily range / ATR

States are labeled by the trace of each component's covariance matrix:
  smallest trace → LOW_VOL, middle → NORMAL_VOL, largest → HIGH_VOL.

Per-regime allowlists (per spec):
  LOW_VOL    PDL_TOUCH, EQ50_SHORT, ZSCORE_*               size 1.0  stop 0.8x  RR 2.0  3/day
  NORMAL_VOL all signals                                    size 1.0  stop 1.0x  RR 1.5  2/day
  HIGH_VOL   GAP_FILL_*, ZSCORE_* only                      size 0.5  stop 1.5x  RR 3.0  1/day
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from research.data_loader import DATA_DIR

logger = logging.getLogger("regime")

State = Literal["LOW_VOL", "NORMAL_VOL", "HIGH_VOL", "UNKNOWN"]
MODEL_PATH = DATA_DIR / "regime_model.pkl"

REGIME_ALLOWLISTS: dict[str, set[str]] = {
    "LOW_VOL": {"PDL_TOUCH", "EQ50_SHORT", "ZSCORE_LONG", "ZSCORE_SHORT"},
    "NORMAL_VOL": set(),  # empty = all allowed
    "HIGH_VOL": {"GAP_FILL_LONG", "GAP_FILL_SHORT", "ZSCORE_LONG", "ZSCORE_SHORT"},
}
REGIME_PARAMS = {
    "LOW_VOL":    {"size_mult": 1.0, "stop_mult": 0.8, "min_rr": 2.0, "max_trades": 3},
    "NORMAL_VOL": {"size_mult": 1.0, "stop_mult": 1.0, "min_rr": 1.5, "max_trades": 2},
    "HIGH_VOL":   {"size_mult": 0.5, "stop_mult": 1.5, "min_rr": 3.0, "max_trades": 1},
}


@dataclass
class RegimeSnapshot:
    state: State
    confidence: float
    transition_risk: float
    probs: dict[str, float] = field(default_factory=dict)
    is_trained: bool = False


def _features(daily: pd.DataFrame) -> pd.DataFrame:
    d = daily.copy()
    rets = np.log(d["close"]).diff()
    feats = pd.DataFrame(index=d.index)
    feats["rv5"] = rets.rolling(5).std() * np.sqrt(252)
    feats["rv10"] = rets.rolling(10).std() * np.sqrt(252)
    feats["rv20"] = rets.rolling(20).std() * np.sqrt(252)
    pc = d["close"].shift(1)
    tr = pd.concat([d["high"] - d["low"], (d["high"] - pc).abs(),
                    (d["low"] - pc).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    feats["atr_ratio"] = atr / d["close"]
    feats["mom20"] = d["close"].pct_change(20)
    feats["vol_ratio"] = d["volume"].rolling(5).mean() / d["volume"].rolling(20).mean()
    feats["gap"] = (d["open"] - pc) / pc
    feats["range_atr"] = (d["high"] - d["low"]) / atr.replace(0, np.nan)
    return feats.dropna()


class RegimeDetector:
    def __init__(self) -> None:
        self.model = None
        self.label_map: dict[int, State] = {}
        self.feature_cols: list[str] = []

    def fit(self, daily: pd.DataFrame) -> None:
        try:
            from sklearn.mixture import GaussianMixture
        except Exception as e:
            logger.warning(f"sklearn unavailable: {e}")
            return
        feats = _features(daily)
        if len(feats) < 60:
            logger.warning(f"too few daily bars to train regime model ({len(feats)})")
            return
        X = feats.values
        gmm = GaussianMixture(n_components=3, covariance_type="full",
                              random_state=42, n_init=3, max_iter=200)
        gmm.fit(X)
        traces = [float(np.trace(c)) for c in gmm.covariances_]
        order = np.argsort(traces)
        self.label_map = {int(order[0]): "LOW_VOL",
                          int(order[1]): "NORMAL_VOL",
                          int(order[2]): "HIGH_VOL"}
        self.model = gmm
        self.feature_cols = list(feats.columns)
        self.save()
        logger.info(f"regime model trained: traces={traces}, label_map={self.label_map}")

    def save(self) -> None:
        try:
            import joblib
            joblib.dump({"model": self.model, "label_map": self.label_map,
                         "feature_cols": self.feature_cols}, MODEL_PATH)
        except Exception as e:
            logger.warning(f"failed to save regime model: {e}")

    def load(self) -> bool:
        if not MODEL_PATH.exists():
            return False
        try:
            import joblib
            obj = joblib.load(MODEL_PATH)
            self.model = obj["model"]
            self.label_map = {int(k): v for k, v in obj["label_map"].items()}
            self.feature_cols = obj["feature_cols"]
            return True
        except Exception as e:
            logger.warning(f"failed to load regime model: {e}")
            return False

    def predict(self, daily: pd.DataFrame) -> RegimeSnapshot:
        if self.model is None:
            return RegimeSnapshot("UNKNOWN", 0.0, 0.0,
                                  {"LOW_VOL": 0.0, "NORMAL_VOL": 1.0, "HIGH_VOL": 0.0},
                                  is_trained=False)
        feats = _features(daily)
        if feats.empty:
            return RegimeSnapshot("UNKNOWN", 0.0, 0.0, {}, is_trained=True)
        x = feats.iloc[[-1]].values
        probs = self.model.predict_proba(x)[0]
        labeled = {self.label_map.get(i, f"S{i}"): float(p) for i, p in enumerate(probs)}
        labeled.setdefault("LOW_VOL", 0.0)
        labeled.setdefault("NORMAL_VOL", 0.0)
        labeled.setdefault("HIGH_VOL", 0.0)
        state = max(labeled, key=labeled.get)
        confidence = float(labeled[state])
        # Transition risk: 1 - confidence, plus boost if recent confidence dropped
        if len(feats) >= 5:
            recent_probs = self.model.predict_proba(feats.tail(5).values)
            states = [self.label_map.get(int(p.argmax()), "?") for p in recent_probs]
            changes = sum(1 for i in range(1, len(states)) if states[i] != states[i - 1])
            transition_risk = float(min(1.0, (1.0 - confidence) + 0.1 * changes))
        else:
            transition_risk = float(1.0 - confidence)
        return RegimeSnapshot(state, confidence, transition_risk, labeled, is_trained=True)


def regime_filter(snap: RegimeSnapshot | None,
                   signal_name: str) -> tuple[bool, str, float, float]:
    """(pass, reason, size_mult, stop_mult)."""
    if snap is None or not snap.is_trained:
        return True, "regime=untrained", 1.0, 1.0
    state = snap.state
    if state not in REGIME_PARAMS:
        return True, f"regime={state} unknown ×1.0", 1.0, 1.0
    params = REGIME_PARAMS[state]
    allowlist = REGIME_ALLOWLISTS.get(state, set())
    if allowlist and signal_name not in allowlist:
        return False, f"regime {state} blocks {signal_name}", 0.0, 1.0
    return (True,
            f"regime {state} (conf={snap.confidence:.2f}) ×{params['size_mult']} stop×{params['stop_mult']}",
            params["size_mult"], params["stop_mult"])
