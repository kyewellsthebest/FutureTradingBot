"""Lightweight smoke tests — verify imports and basic happy-path behaviour."""
from __future__ import annotations

import importlib

import pandas as pd
import numpy as np


def test_research_imports():
    for mod in [
        "research.indicators",
        "research.signal_filters",
        "research.signal_generator",
        "research.vpin_calculator",
        "research.adverse_selection_detector",
        "research.regime_detector",
        "research.gex_calculator",
        "research.position_sizer",
        "research.execution_optimizer",
        "research.cot_parser",
        "research.edgar_insider",
        "research.alternative_data",
        "research.congressional_trades",
        "research.wsb_sentiment",
        "research.ml_model",
        "research.signal_engine",
        "research.data_loader",
    ]:
        importlib.import_module(mod)


def test_bot_imports():
    importlib.import_module("bot.persistence")
    importlib.import_module("bot.paper_trading")
    importlib.import_module("bot.main")


def test_dashboard_imports():
    importlib.import_module("dashboard.server")


def test_indicators_basic():
    from research.indicators import sma, ema, rsi
    s = pd.Series(np.linspace(100, 110, 50))
    assert not sma(s, 5).dropna().empty
    assert not ema(s, 5).dropna().empty
    assert rsi(s, 14).between(0, 100).all()


def test_signal_filters_bias_neutral():
    from research.signal_filters import daily_bias_at, vol_regime_at
    idx = pd.date_range("2024-01-01", periods=30, freq="1D", tz="UTC")
    daily = pd.DataFrame({
        "open": np.linspace(100, 110, 30),
        "high": np.linspace(101, 112, 30),
        "low": np.linspace(99, 109, 30),
        "close": np.linspace(100.5, 111, 30),
        "volume": 1000,
    }, index=idx)
    assert daily_bias_at(daily, idx[-1]) in {"BULLISH", "BEARISH", "NEUTRAL"}
    vr = vol_regime_at(daily, idx[-1])
    assert vr.regime in {"LOW", "NORMAL", "HIGH"}


def test_engine_constructs():
    from research.signal_engine import SignalEngine
    eng = SignalEngine()
    # Whitelist may be empty if validation_results.json missing — that's ok
    assert isinstance(eng.whitelist, set)
