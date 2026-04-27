"""
HMM-style volatility regime detector.

Uses a 3-component GaussianMixture on daily log-returns to bucket each day as
LOW / NORMAL / HIGH vol. Persists to data/regime_model.pkl.

Per-signal regime preferences live in `SIGNAL_REGIME_AFFINITY` — a signal that
performs poorly in HIGH vol gets penalised when the current state is HIGH.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from research.data_loader import DATA_DIR

logger = logging.getLogger("regime_detector")

MODEL_PATH = DATA_DIR / "regime_model.pkl"

RegimeState = Literal["LOW_VOL", "NORMAL_VOL", "HIGH_VOL", "UNKNOWN"]

SIGNAL_REGIME_AFFINITY = {
    "PDL_TOUCH":       {"LOW_VOL": 1.0, "NORMAL_VOL": 1.0, "HIGH_VOL": 0.5},
    "PDH_TOUCH":       {"LOW_VOL": 1.0, "NORMAL_VOL": 1.0, "HIGH_VOL": 0.5},
    "EQ50_LONG":       {"LOW_VOL": 1.0, "NORMAL_VOL": 1.0, "HIGH_VOL": 0.5},
    "EQ50_SHORT":      {"LOW_VOL": 1.0, "NORMAL_VOL": 1.0, "HIGH_VOL": 0.5},
    "GAP_FILL_LONG":   {"LOW_VOL": 0.8, "NORMAL_VOL": 1.0, "HIGH_VOL": 1.1},
    "GAP_FILL_SHORT":  {"LOW_VOL": 0.8, "NORMAL_VOL": 1.0, "HIGH_VOL": 1.1},
    "ZSCORE_LONG":     {"LOW_VOL": 1.1, "NORMAL_VOL": 1.0, "HIGH_VOL": 0.7},
    "ZSCORE_SHORT":    {"LOW_VOL": 1.1, "NORMAL_VOL": 1.0, "HIGH_VOL": 0.7},
    "VOL_COMP_LONG":   {"LOW_VOL": 1.2, "NORMAL_VOL": 1.0, "HIGH_VOL": 0.6},
    "VOL_COMP_SHORT":  {"LOW_VOL": 1.2, "NORMAL_VOL": 1.0, "HIGH_VOL": 0.6},
}

REGIME_STOP_MULT = {"LOW_VOL": 0.8, "NORMAL_VOL": 1.0, "HIGH_VOL": 1.4, "UNKNOWN": 1.0}


@dataclass
class RegimeSnapshot:
    state: RegimeState
    confidence: float
    transition_risk: float
    probs: dict
    is_trained: bool = False


class RegimeDetector:
    def __init__(self):
        self.model = None
        self._state_order: list[str] = ["LOW_VOL", "NORMAL_VOL", "HIGH_VOL"]

    def load(self) -> bool:
        try:
            import joblib  # noqa: WPS433
        except Exception:
            return False
        if not MODEL_PATH.exists():
            return False
        try:
            payload = joblib.load(MODEL_PATH)
            self.model = payload["model"]
            self._state_order = payload["state_order"]
            return True
        except Exception as e:
            logger.warning("[regime] failed to load model: %s", e)
            return False

    def fit(self, daily: pd.DataFrame) -> bool:
        try:
            from sklearn.mixture import GaussianMixture
            import joblib
        except Exception:
            return False
        if daily is None or daily.empty:
            return False
        rets = np.log(daily["close"]).diff().dropna()
        rng = (daily["high"] - daily["low"]).pct_change().dropna()
        feats = pd.concat([rets.rename("ret"), rng.rename("rng")], axis=1).dropna()
        if len(feats) < 60:
            return False
        gm = GaussianMixture(n_components=3, covariance_type="full", random_state=42, n_init=3)
        gm.fit(feats.values)
        # Order components by variance of returns to map to LOW/NORMAL/HIGH.
        var = gm.covariances_[:, 0, 0]
        order = list(np.argsort(var))
        state_order = ["LOW_VOL", "NORMAL_VOL", "HIGH_VOL"]
        self.model = gm
        self._state_order = [state_order[order.index(i)] for i in range(3)]
        joblib.dump({"model": gm, "state_order": self._state_order}, MODEL_PATH)
        return True

    def predict(self, daily: pd.DataFrame) -> RegimeSnapshot:
        if self.model is None or daily is None or daily.empty:
            return RegimeSnapshot("UNKNOWN", 0.0, 0.0,
                                  {"LOW_VOL": 0.0, "NORMAL_VOL": 1.0, "HIGH_VOL": 0.0},
                                  is_trained=False)
        rets = np.log(daily["close"]).diff().dropna()
        rng = (daily["high"] - daily["low"]).pct_change().dropna()
        feats = pd.concat([rets.rename("ret"), rng.rename("rng")], axis=1).dropna()
        if feats.empty:
            return RegimeSnapshot("UNKNOWN", 0.0, 0.0,
                                  {"LOW_VOL": 0.0, "NORMAL_VOL": 1.0, "HIGH_VOL": 0.0},
                                  is_trained=True)
        last = feats.iloc[[-1]].values
        probs = self.model.predict_proba(last)[0]
        prob_map = {self._state_order[i]: float(probs[i]) for i in range(len(probs))}
        for k in ("LOW_VOL", "NORMAL_VOL", "HIGH_VOL"):
            prob_map.setdefault(k, 0.0)
        state = max(prob_map, key=prob_map.get)
        conf = float(prob_map[state])
        # 5-day transition risk: how variable were the per-day max-probs?
        recent = feats.tail(5).values
        if len(recent) >= 2:
            prs = self.model.predict_proba(recent).max(axis=1)
            transition = float(1.0 - prs.mean())
        else:
            transition = 0.0
        return RegimeSnapshot(state, conf, max(0.0, transition), prob_map, is_trained=True)


def regime_filter(snap: RegimeSnapshot | None, signal_name: str) -> tuple[bool, str, float, float]:
    """Returns (pass, reason, size_mult, stop_mult)."""
    if snap is None or not snap.is_trained:
        return True, "regime=untrained", 1.0, 1.0
    aff = SIGNAL_REGIME_AFFINITY.get(signal_name, {}).get(snap.state, 1.0)
    stop_mult = REGIME_STOP_MULT.get(snap.state, 1.0)
    if aff <= 0.5 and snap.confidence > 0.7:
        return False, f"regime={snap.state} bad for {signal_name}", 0.0, stop_mult
    return True, f"regime={snap.state} aff×{aff}", float(aff), float(stop_mult)
