"""
ML confirmation layer (Part 5 of the spec).

XGBoost classifier predicting next-10-bar trend direction from technical features.

Training:
  - 70/15/15 chronological split (no shuffling — avoids look-ahead)
  - GridSearchCV over the prompt's hyperparameter grid
  - 3-fold time-series CV inside the grid

Output:
  - data/ml_model.pkl       (joblib)
  - data/ml_features.json   (feature column order + threshold + grid result)

Usage:
  python -m research.ml_model
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from xgboost import XGBClassifier

from research.data_loader import DATA_DIR, download_nq
from research.indicators import (
    atr,
    bollinger_pct_b,
    cci,
    ema,
    macd,
    price_position_in_range,
    roc,
    rsi,
    sma,
    stochastic,
    volume_ratio,
    williams_r,
    zscore,
)
from research.signal_filters import daily_bias_at
from research.signal_generator import _attach_prev_day_levels

logger = logging.getLogger("ml_model")

NY = "America/New_York"

MODEL_PATH = DATA_DIR / "ml_model.pkl"
FEATURES_PATH = DATA_DIR / "ml_features.json"

# Threshold to confirm a trade direction (prompt: 0.55).
CONFIRM_THRESHOLD = 0.55

# Label horizon and threshold (prompt: 10 bars, 0.3%).
LABEL_HORIZON = 10
LABEL_THRESHOLD = 0.003


# ---------------------------------------------------------------------------
# Feature builder
# ---------------------------------------------------------------------------

def build_features(intraday: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """Return DataFrame of features aligned to `intraday` index, no NaNs at the end."""
    df = _attach_prev_day_levels(intraday, daily)
    o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]
    feats = pd.DataFrame(index=df.index)

    feats["rsi5"] = rsi(c, 5)
    feats["rsi10"] = rsi(c, 10)
    feats["rsi14"] = rsi(c, 14)

    macd_line, macd_sig, macd_hist = macd(c)
    feats["macd"] = macd_line
    feats["macd_signal"] = macd_sig
    feats["macd_hist"] = macd_hist

    feats["bb_pct_b"] = bollinger_pct_b(c)
    feats["atr14"] = atr(h, l, c, 14)

    feats["roc5"] = roc(c, 5)
    feats["roc10"] = roc(c, 10)
    feats["roc20"] = roc(c, 20)

    feats["vol_ratio"] = volume_ratio(v, 20)

    stoch_k, stoch_d = stochastic(h, l, c, 14)
    feats["stoch_k"] = stoch_k
    feats["stoch_d"] = stoch_d

    feats["williams_r"] = williams_r(h, l, c, 14)
    feats["cci20"] = cci(h, l, c, 20)

    feats["sma5"] = sma(c, 5)
    feats["sma10"] = sma(c, 10)
    feats["sma20"] = sma(c, 20)
    feats["sma50"] = sma(c, 50)

    feats["ema5"] = ema(c, 5)
    feats["ema10"] = ema(c, 10)
    feats["ema20"] = ema(c, 20)

    feats["price_pos_50"] = price_position_in_range(h, l, c, 50)

    feats["dist_pdh"] = c - df["pdh"]
    feats["dist_pdl"] = c - df["pdl"]
    feats["gap_prev_close"] = c - df["prev_close"]

    feats["zscore20"] = zscore(c, 20)

    ny_idx = df.index.tz_convert(NY)
    feats["hour"] = ny_idx.hour
    feats["dow"] = ny_idx.dayofweek

    # Daily bias score (-1 / 0 / +1) at each bar — uses only past daily candles.
    bias_score = pd.Series(0, index=df.index, dtype=int)
    # Compute once per session for speed.
    session_dates = pd.Index(df.index.tz_convert(NY).normalize()).unique()
    bias_lookup = {}
    for ts in session_dates:
        b = daily_bias_at(daily, ts.tz_convert("UTC"))
        bias_lookup[ts] = (1 if b == "BULLISH" else -1 if b == "BEARISH" else 0)
    bias_score[:] = pd.Series(df.index.tz_convert(NY).normalize()).map(bias_lookup).to_numpy()
    feats["daily_bias_score"] = bias_score

    return feats


# ---------------------------------------------------------------------------
# Label builder
# ---------------------------------------------------------------------------

def build_labels(close: pd.Series,
                 horizon: int = LABEL_HORIZON,
                 threshold: float = LABEL_THRESHOLD) -> pd.Series:
    """0 = bearish, 1 = neutral, 2 = bullish."""
    fwd_avg = close.shift(-1).rolling(horizon, min_periods=horizon).mean().shift(-(horizon - 1))
    rel = (fwd_avg - close) / close
    labels = pd.Series(1, index=close.index, dtype=int)
    labels[rel > threshold] = 2
    labels[rel < -threshold] = 0
    # Last `horizon` bars have no forward-looking data → mark NaN-equivalent.
    labels.iloc[-horizon:] = -1
    return labels


# ---------------------------------------------------------------------------
# Train / evaluate
# ---------------------------------------------------------------------------

@dataclass
class TrainResult:
    best_params: dict
    train_acc: float
    val_acc: float
    test_acc: float
    n_train: int
    n_val: int
    n_test: int
    feature_importance_top10: list[tuple[str, float]]
    test_confusion: list[list[int]]
    test_classification: str


def train_and_save(intraday: pd.DataFrame, daily: pd.DataFrame,
                   *, fast: bool = False) -> TrainResult:
    print("[ml] building features ...", flush=True)
    feats = build_features(intraday, daily)
    labels = build_labels(intraday["close"])

    # Drop rows with NaN features or unknown label.
    mask = feats.notna().all(axis=1) & (labels >= 0)
    X = feats.loc[mask]
    y = labels.loc[mask]
    print(f"[ml] usable samples: {len(X):,}  (features={X.shape[1]})", flush=True)

    # 70 / 15 / 15 chronological split.
    n = len(X)
    cut1 = int(n * 0.70)
    cut2 = int(n * 0.85)
    X_train, X_val, X_test = X.iloc[:cut1], X.iloc[cut1:cut2], X.iloc[cut2:]
    y_train, y_val, y_test = y.iloc[:cut1], y.iloc[cut1:cut2], y.iloc[cut2:]

    if fast:
        param_grid = {
            "n_estimators": [100],
            "max_depth": [4],
            "learning_rate": [0.05],
            "subsample": [0.9],
        }
    else:
        param_grid = {
            "n_estimators": [100, 200, 300],
            "max_depth": [3, 4, 5],
            "learning_rate": [0.01, 0.05, 0.1],
            "subsample": [0.8, 0.9, 1.0],
        }

    base = XGBClassifier(
        objective="multi:softprob",
        num_class=3,
        eval_metric="mlogloss",
        tree_method="hist",
        n_jobs=-1,
        random_state=42,
        verbosity=0,
    )

    cv = TimeSeriesSplit(n_splits=3)
    print(f"[ml] grid search ({sum(1 for _ in _grid_iter(param_grid))} combos x 3 folds)", flush=True)
    gs = GridSearchCV(base, param_grid, cv=cv, scoring="accuracy", n_jobs=1, verbose=0)
    gs.fit(X_train, y_train)
    best = gs.best_estimator_

    train_acc = accuracy_score(y_train, best.predict(X_train))
    val_acc = accuracy_score(y_val, best.predict(X_val))
    test_pred = best.predict(X_test)
    test_acc = accuracy_score(y_test, test_pred)

    importances = sorted(
        zip(X.columns, best.feature_importances_), key=lambda x: x[1], reverse=True
    )
    top10 = [(name, float(score)) for name, score in importances[:10]]

    cm = confusion_matrix(y_test, test_pred, labels=[0, 1, 2]).tolist()
    cls_report = classification_report(y_test, test_pred, labels=[0, 1, 2],
                                       target_names=["bear", "neutral", "bull"],
                                       zero_division=0)

    # Persist model + metadata.
    joblib.dump(best, MODEL_PATH)
    metadata = {
        "feature_order": list(X.columns),
        "label_horizon": LABEL_HORIZON,
        "label_threshold": LABEL_THRESHOLD,
        "confirm_threshold": CONFIRM_THRESHOLD,
        "best_params": gs.best_params_,
        "train_acc": float(train_acc),
        "val_acc": float(val_acc),
        "test_acc": float(test_acc),
        "n_train": len(X_train),
        "n_val": len(X_val),
        "n_test": len(X_test),
        "feature_importance_top10": top10,
        "test_confusion_matrix": cm,
    }
    FEATURES_PATH.write_text(json.dumps(metadata, indent=2, default=str))

    return TrainResult(
        best_params=gs.best_params_,
        train_acc=float(train_acc),
        val_acc=float(val_acc),
        test_acc=float(test_acc),
        n_train=len(X_train),
        n_val=len(X_val),
        n_test=len(X_test),
        feature_importance_top10=top10,
        test_confusion=cm,
        test_classification=cls_report,
    )


def _grid_iter(grid: dict):
    """Cartesian product yield count, just for printing."""
    from itertools import product
    keys = list(grid.keys())
    for combo in product(*[grid[k] for k in keys]):
        yield dict(zip(keys, combo))


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

def load_model():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Model not found at {MODEL_PATH}; train first.")
    model = joblib.load(MODEL_PATH)
    meta = json.loads(FEATURES_PATH.read_text())
    return model, meta


def predict_probs(model, meta: dict, feature_row: pd.Series) -> tuple[float, float, float]:
    """Return (p_bear, p_neutral, p_bull) for one feature row."""
    cols = meta["feature_order"]
    X = pd.DataFrame([feature_row.reindex(cols)])
    if X.isna().any(axis=1).iloc[0]:
        return (np.nan, np.nan, np.nan)
    probs = model.predict_proba(X)[0]
    return float(probs[0]), float(probs[1]), float(probs[2])


def confirm_direction(p_bear: float, p_neutral: float, p_bull: float,
                      side: str, threshold: float = CONFIRM_THRESHOLD) -> str:
    """
    Returns one of: "AGREE" | "REDUCE" | "REJECT".
      AGREE  → ML same direction with prob > threshold → full size.
      REDUCE → ML neutral (no class above threshold)   → smaller size.
      REJECT → ML opposite direction with prob > threshold → skip trade.
    """
    if side == "LONG":
        if p_bull > threshold:
            return "AGREE"
        if p_bear > threshold:
            return "REJECT"
        return "REDUCE"
    else:
        if p_bear > threshold:
            return "AGREE"
        if p_bull > threshold:
            return "REJECT"
        return "REDUCE"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main() -> int:
    intraday = download_nq("5min")
    daily = download_nq("daily")

    fast = "--fast" in sys.argv
    print(f"[ml] {'FAST mode (1 combo)' if fast else 'FULL grid (81 combos)'}", flush=True)
    res = train_and_save(intraday, daily, fast=fast)

    print()
    print("=" * 72)
    print("ML model training results")
    print("=" * 72)
    print(f"  best params : {res.best_params}")
    print(f"  splits      : train={res.n_train:,}  val={res.n_val:,}  test={res.n_test:,}")
    print(f"  train acc   : {res.train_acc:.4f}")
    print(f"  val   acc   : {res.val_acc:.4f}")
    print(f"  test  acc   : {res.test_acc:.4f}")
    print()
    print("  top 10 features by importance:")
    for name, score in res.feature_importance_top10:
        print(f"    {name:<22s} {score:.4f}")
    print()
    print("  test confusion (rows=true, cols=pred, [bear, neutral, bull]):")
    for row in res.test_confusion:
        print(f"    {row}")
    print()
    print(res.test_classification)
    print(f"  saved -> {MODEL_PATH.name} + {FEATURES_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
