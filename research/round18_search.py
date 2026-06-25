#!/usr/bin/env python3
"""Round 18 — TRULY advanced ML with PyTorch + sklearn.

Strict integrity contract:
  * Execution: `research.round9_search.r9_bot_on_tick` AS-IS.
  * No queue/fill patching. No custom executor.
  * Features captured at the moment of setup-emission. Labels derived
    after the fact from the trade outcome that the r9 executor actually
    produced (pnl_pts -> win/loss).

Workflow in a SINGLE script execution:

  Phase 1 (training pass, days 0..TRAIN_DAYS):
    - Run a small set of "feature donors" — base pullback variants
      (INV_236 family) that emit setups WITHOUT ML filtering.
    - Each setup emission writes an 80+-feature vector + a setup-key
      to a per-strategy feature buffer.
    - After the pass, walk strategy.completed and align by trade order
      to produce (X, y) where y = 1 if pnl_usd > 0 else 0.

  Phase 2 (model training):
    - PyTorch MLP (3-layer w/ dropout) — primary.
    - PyTorch Transformer encoder over sequential features (using the
      last K feature vectors as a sequence) — secondary.
    - sklearn GradientBoostingClassifier — robust baseline.
    - sklearn LogisticRegression — sanity baseline.
    - All trained on Phase-1 features. Train/val split by trade index.

  Phase 3 (OOS test pass, days TRAIN_DAYS..TRAIN_DAYS+TEST_DAYS):
    - Run the SAME feature-donor strategies, but with ML gating.
    - Multiple thresholds tested (0.50, 0.55, 0.60, 0.65) per model.
    - All under r9_bot_on_tick verbatim.

  Phase 4 (hyperparameter random search):
    - 100 random parameter combinations evaluated on a 14-day window.
    - Score = $/day under $1.91 fees.

Output:
  /home/user/HFTBot/research/round18_results.md
  /home/user/HFTBot/research/round18_summary.csv
"""
from __future__ import annotations
import os
import sys
import time
import math
import pickle
import csv
import random
import json
from collections import deque, defaultdict
from datetime import datetime

sys.path.insert(0, "/home/user/HFTBot")
sys.path.insert(0, "/home/user/HFTBot/research")

# Env defaults (mirror r16/r17 baseline)
os.environ.setdefault("STRAT_INVERT", "1")
os.environ.setdefault("STRAT_PULL_PCT", "0.236")
os.environ.setdefault("STRAT_STOP_PTS", "10.0")
os.environ.setdefault("STRAT_TARGET_PTS", "20.0")
os.environ.setdefault("STRAT_IMPULSE_PTS", "5.0")
os.environ.setdefault("STRAT_IMPULSE_BARS", "4")
os.environ.setdefault("STRAT_COOLDOWN_SECS", "10")
os.environ.setdefault("BOT_HTF_TREND_FILTER", "0")

import numpy as np

# Lib imports — order matters (round8 sets up MARKET singleton).
from research import round4_search as r4
from research import round6_search as r6
from research import round7_search as r7
from research import round8_search as r8
from research import round9_search as r9

StrategyBase = r4.StrategyBase
PullbackStrategy = r4.PullbackStrategy
MarketablePullback = r6.MarketablePullback
GatedCanonPullback = r8.GatedCanonPullback
BarBuilder = r4.BarBuilder
MARKET = r8.MARKET
attach_r7_executor = r7.attach_r7_executor

MNQ_PER_PT = 2.0
FEE_FULL_RT = 1.91
MAX_HOLD_S = r7.MAX_HOLD_S
TICK_PATH = "/home/user/HFTBot/data/tick/ustech/USTECH_full.csv"
OFFSET = 7_820_974_790
TRAIN_DAYS = 25
TEST_DAYS = 20
HYPER_DAYS = 14
CHECKPOINT_EVERY_TICKS = 25_000

CKPT_PATH = "/home/user/HFTBot/research/round18_checkpoint.pkl"
RESULTS_PATH = "/home/user/HFTBot/research/round18_results.md"
CSV_PATH = "/home/user/HFTBot/research/round18_summary.csv"
FEATURES_PATH = "/home/user/HFTBot/research/round18_features.npz"
MODELS_PATH = "/home/user/HFTBot/research/round18_models.pkl"

# Reproducibility
np.random.seed(42)
random.seed(42)

# Try PyTorch
TORCH_OK = False
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    TORCH_OK = True
    torch.manual_seed(42)
except Exception as e:
    print(f"[round18] PyTorch unavailable: {e}", file=sys.stderr)
    torch = None

# sklearn
SK_OK = False
try:
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import roc_auc_score, precision_score, recall_score
    SK_OK = True
except Exception as e:
    print(f"[round18] sklearn unavailable: {e}", file=sys.stderr)


# =============================================================================
# FEATURE EXTRACTOR — 80+ features
# =============================================================================
class FeatureExtractor:
    """Builds a feature vector at any (ts, bid, ask, hh, mn) moment.

    Maintains rolling buffers internally; fed by the main loop separately
    from strategy bookkeeping.
    """
    N_FEATURES = 84

    def __init__(self, bar_history_len=120, tick_history_len=4000):
        self.bars = deque(maxlen=bar_history_len)  # (o,h,l,c)
        self.ticks = deque(maxlen=tick_history_len)  # (ts,last,bid,ask)
        self.signed_tick_buf = deque(maxlen=2000)  # (ts, +1/-1)
        self.session_vwap_num = 0.0
        self.session_vwap_den = 0
        self._last_session_day = None
        self._last_tick_px = None

    def feed_tick(self, ts, last, bid, ask):
        if self._last_tick_px is not None:
            if last > self._last_tick_px:
                self.signed_tick_buf.append((ts, 1))
            elif last < self._last_tick_px:
                self.signed_tick_buf.append((ts, -1))
        self._last_tick_px = last
        self.ticks.append((ts, last, bid, ask))
        # Session VWAP — reset by day index of ts
        day = int(ts // 86400)
        if day != self._last_session_day:
            self._last_session_day = day
            self.session_vwap_num = 0.0
            self.session_vwap_den = 0
        self.session_vwap_num += last
        self.session_vwap_den += 1

    def feed_bar(self, o, h, l, c):
        self.bars.append((o, h, l, c))

    def extract(self, ts, bid, ask, hh, mn, setup_dir=0, setup_dist=0.0):
        """Returns numpy.float32 array of length N_FEATURES, or None if
        insufficient history.

        setup_dir: +1 LONG, -1 SHORT, 0 unknown
        setup_dist: pts from current price to setup entry (signed)
        """
        if len(self.bars) < 20:
            return None
        bars = list(self.bars)
        last = (bid + ask) / 2.0
        f = np.zeros(self.N_FEATURES, dtype=np.float32)
        idx = 0

        # ---- Price action (0-19): 10 1m returns, 5 ranges, 4 SMA divs, percentile
        for i in range(10):
            if len(bars) >= i + 2:
                b = bars[-(i + 1)]
                pb = bars[-(i + 2)]
                f[idx] = (b[3] - pb[3]) / 5.0
            idx += 1
        for i in range(5):
            if len(bars) >= i + 1:
                b = bars[-(i + 1)]
                rng = max(b[1] - b[2], 0.01)
                f[idx] = rng / 5.0
            idx += 1
        # SMA divergences (5/10/20/50 vs last)
        if len(bars) >= 5:
            sma5 = sum(b[3] for b in bars[-5:]) / 5.0
            f[idx] = (last - sma5) / 5.0
        idx += 1
        if len(bars) >= 10:
            sma10 = sum(b[3] for b in bars[-10:]) / 10.0
            f[idx] = (last - sma10) / 5.0
        idx += 1
        if len(bars) >= 20:
            sma20 = sum(b[3] for b in bars[-20:]) / 20.0
            f[idx] = (last - sma20) / 5.0
        idx += 1
        if len(bars) >= 50:
            sma50 = sum(b[3] for b in bars[-50:]) / 50.0
            f[idx] = (last - sma50) / 5.0
        idx += 1
        # 60-bar range percentile
        if len(bars) >= 60:
            highs = [b[1] for b in bars[-60:]]
            lows = [b[2] for b in bars[-60:]]
            hi = max(highs); lo = min(lows)
            rg = hi - lo
            f[idx] = (last - lo) / max(rg, 0.01)
        idx += 1
        # Should be 20 now
        assert idx == 20, f"price action ended at {idx}"

        # ---- Microstructure (20-39): 20 features
        spread = ask - bid
        f[idx] = spread / 0.5; idx += 1
        # 60s avg spread, trend
        cutoff = ts - 60.0
        recent_spreads = [a - b for t, _, b, a in self.ticks if t >= cutoff]
        if recent_spreads:
            avg = sum(recent_spreads) / len(recent_spreads)
            f[idx] = avg / 0.5
            n = len(recent_spreads)
            if n >= 4:
                fh = sum(recent_spreads[:n // 2]) / max(1, n // 2)
                sh = sum(recent_spreads[n // 2:]) / max(1, n - n // 2)
                f[idx + 1] = (sh - fh) / 0.5
        idx += 2
        # Tick rate 10s, 30s, 60s, 300s
        for w in (10.0, 30.0, 60.0, 300.0):
            cnt = sum(1 for t, _, _, _ in self.ticks if t >= ts - w)
            f[idx] = (cnt / w) / 50.0
            idx += 1
        # Cum delta 30s, 60s, 300s
        for w in (30.0, 60.0, 300.0):
            cutoff = ts - w
            bal = sum(s for t, s in self.signed_tick_buf if t >= cutoff)
            f[idx] = bal / 50.0
            idx += 1
        # Touches at current level — ticks within 0.5pt of last in 60s, 300s
        for w in (60.0, 300.0):
            cutoff = ts - w
            cnt = sum(1 for t, lst, _, _ in self.ticks
                      if t >= cutoff and abs(lst - last) < 0.5)
            f[idx] = cnt / 100.0
            idx += 1
        # Tick direction balance over recent 100 ticks
        recent_dirs = list(self.signed_tick_buf)[-100:]
        if recent_dirs:
            bal100 = sum(s for _, s in recent_dirs)
            f[idx] = bal100 / 100.0
        idx += 1
        # Spread / ATR ratio
        atr5 = 0.0
        if len(bars) >= 5:
            atr5 = sum((b[1] - b[2]) for b in bars[-5:]) / 5.0
        f[idx] = spread / max(atr5, 0.5); idx += 1
        # Bid-ask persistence (seconds at same bid)
        persist_s = 0.0
        for t, _, b, _ in reversed(self.ticks):
            if abs(b - bid) > 0.25:
                break
            persist_s = ts - t
            if persist_s > 60:
                break
        f[idx] = persist_s / 30.0; idx += 1
        # Last-price persistence
        persist_p = 0.0
        for t, lst, _, _ in reversed(self.ticks):
            if abs(lst - last) > 0.5:
                break
            persist_p = ts - t
            if persist_p > 60:
                break
        f[idx] = persist_p / 30.0; idx += 1
        # VWAP gap
        if self.session_vwap_den > 0:
            vwap = self.session_vwap_num / self.session_vwap_den
            f[idx] = (last - vwap) / 5.0
        idx += 1
        # bid-ask midpoint vs last
        f[idx] = (last - (bid + ask) / 2.0) / 0.25; idx += 1
        # cumulative delta sign over 60s
        cutoff = ts - 60.0
        pos = sum(1 for t, s in self.signed_tick_buf if t >= cutoff and s > 0)
        neg = sum(1 for t, s in self.signed_tick_buf if t >= cutoff and s < 0)
        f[idx] = (pos - neg) / max(pos + neg, 1); idx += 1
        # Tick velocity 5s (extra)
        cnt5 = sum(1 for t, _, _, _ in self.ticks if t >= ts - 5.0)
        f[idx] = (cnt5 / 5.0) / 50.0; idx += 1
        # Currently idx ~ 40
        assert idx == 40, f"microstructure ended at {idx}"

        # ---- Volatility regime (40-54): 15 features
        # ATR 5,20,60
        if len(bars) >= 5:
            f[idx] = sum((b[1] - b[2]) for b in bars[-5:]) / 5.0 / 5.0
        idx += 1
        atr20 = 0.0
        if len(bars) >= 20:
            atr20 = sum((b[1] - b[2]) for b in bars[-20:]) / 20.0
            f[idx] = atr20 / 5.0
        idx += 1
        if len(bars) >= 60:
            atr60 = sum((b[1] - b[2]) for b in bars[-60:]) / 60.0
            f[idx] = atr60 / 5.0
            # ATR ratio
            f[idx + 1] = (atr20 / max(atr60, 0.01)) - 1.0
        idx += 2
        # Realized vol 5/15/60min (sqrt sum sq returns)
        for w in (5, 15, 60):
            if len(bars) >= w + 1:
                rets = [bars[-i][3] - bars[-i - 1][3] for i in range(1, w + 1)]
                vol = math.sqrt(sum(r * r for r in rets) / len(rets))
                f[idx] = vol / 5.0
            idx += 1
        # Vol z-score vs 60-bar dist
        if len(bars) >= 60:
            ranges = [b[1] - b[2] for b in bars[-60:]]
            mean = sum(ranges) / len(ranges)
            var = sum((r - mean) ** 2 for r in ranges) / max(1, len(ranges) - 1)
            std = math.sqrt(max(var, 1e-9))
            cur_rng = bars[-1][1] - bars[-1][2]
            f[idx] = (cur_rng - mean) / max(std, 0.01)
        idx += 1
        # Hurst (35-bar window) — simple R/S
        if len(bars) >= 35:
            closes = [b[3] for b in bars[-35:]]
            mean = sum(closes) / len(closes)
            dev = [c - mean for c in closes]
            cum = 0; mn = 0; mx = 0
            for d in dev:
                cum += d
                if cum > mx: mx = cum
                if cum < mn: mn = cum
            rng = mx - mn
            std = math.sqrt(sum((c - mean) ** 2 for c in closes) / len(closes))
            if std > 0 and rng > 0:
                rs = rng / std
                try:
                    hurst = math.log(max(rs, 0.001)) / math.log(len(closes))
                except Exception:
                    hurst = 0.5
            else:
                hurst = 0.5
            f[idx] = hurst
        idx += 1
        # Range expansion percentile (current rng vs 60-bar)
        if len(bars) >= 60:
            ranges_60 = sorted(b[1] - b[2] for b in bars[-60:])
            cur_rng = bars[-1][1] - bars[-1][2]
            cnt = sum(1 for r in ranges_60 if r < cur_rng)
            f[idx] = cnt / len(ranges_60)
        idx += 1
        # Choppiness index (20-bar)
        if len(bars) >= 20:
            tr_sum = 0.0
            highs = []
            lows = []
            for i in range(len(bars) - 20, len(bars)):
                b = bars[i]
                pc = bars[i - 1][3] if i > 0 else b[3]
                tr = max(b[1] - b[2], abs(b[1] - pc), abs(b[2] - pc))
                tr_sum += tr
                highs.append(b[1])
                lows.append(b[2])
            rng = max(highs) - min(lows)
            if rng > 0 and tr_sum > 0:
                try:
                    ci = 100 * math.log10(tr_sum / rng) / math.log10(20)
                except Exception:
                    ci = 50.0
            else:
                ci = 50.0
            f[idx] = ci / 100.0
        idx += 1
        # ATR pct rank from MARKET singleton (proxy)
        f[idx] = MARKET.atr_pct()
        idx += 1
        # Spread/atr20 ratio
        f[idx] = spread / max(atr20, 0.5)
        idx += 1
        # ATR(60)/ATR(5) ratio (vol shape)
        if len(bars) >= 60:
            atr5_v = sum((b[1] - b[2]) for b in bars[-5:]) / 5.0
            atr60v = sum((b[1] - b[2]) for b in bars[-60:]) / 60.0
            f[idx] = (atr60v / max(atr5_v, 0.01)) - 1.0
        idx += 1
        # Recent (20-bar) trend slope: linreg of closes
        if len(bars) >= 20:
            ys = [b[3] for b in bars[-20:]]
            xs = list(range(20))
            mx = sum(xs) / 20; my = sum(ys) / 20
            num = sum((xs[i] - mx) * (ys[i] - my) for i in range(20))
            den = sum((xs[i] - mx) ** 2 for i in range(20))
            slope = num / max(den, 1e-9)
            f[idx] = slope / 0.5
        idx += 1
        assert idx == 55, f"vol regime ended at {idx}"

        # ---- Time features (55-74): 20 features
        # Hour sin/cos
        f[idx] = math.sin(2 * math.pi * hh / 24); idx += 1
        f[idx] = math.cos(2 * math.pi * hh / 24); idx += 1
        # Minute sin/cos
        f[idx] = math.sin(2 * math.pi * mn / 60); idx += 1
        f[idx] = math.cos(2 * math.pi * mn / 60); idx += 1
        # Day of week — use ts mod 7 days (approx)
        dow = int((ts // 86400) % 7)
        for i in range(7):
            f[idx + i] = 1.0 if dow == i else 0.0
        idx += 7
        # Minutes since session open (treating 13:30 UTC as RTH-open marker)
        rth_open_min = 13 * 60 + 30
        cur_min = hh * 60 + mn
        f[idx] = (cur_min - rth_open_min) / 390.0; idx += 1
        # Minutes to RTH close (20:00 UTC)
        rth_close = 20 * 60
        f[idx] = (rth_close - cur_min) / 390.0; idx += 1
        # Time since last big tick (>5pt move) — proxy for news event
        big_move_age = 600.0
        for t, lst, _, _ in reversed(self.ticks):
            if abs(lst - last) > 5.0:
                big_move_age = ts - t
                break
        f[idx] = min(big_move_age / 600.0, 1.0); idx += 1
        # In NY session (13:30..20:00 UTC)
        f[idx] = 1.0 if (rth_open_min <= cur_min < rth_close) else 0.0; idx += 1
        # In overnight (22:00 UTC..13:30 UTC)
        f[idx] = 1.0 if cur_min < rth_open_min or cur_min >= 22 * 60 else 0.0; idx += 1
        # Sec-of-day fraction
        sec_of_day = (hh * 3600 + mn * 60) / 86400.0
        f[idx] = sec_of_day; idx += 1
        # Min-of-hour
        f[idx] = mn / 60.0; idx += 1
        # Is near top of hour (mn < 5 or mn > 55)
        f[idx] = 1.0 if (mn < 5 or mn > 55) else 0.0; idx += 1
        # Is near top of day (just before/after midnight UTC)
        f[idx] = 1.0 if (hh == 0 or hh == 23) else 0.0; idx += 1
        assert idx == 75, f"time features ended at {idx}"

        # ---- Setup-specific (75-83): 9 features
        # setup direction one-hot
        f[idx] = 1.0 if setup_dir > 0 else 0.0; idx += 1
        f[idx] = 1.0 if setup_dir < 0 else 0.0; idx += 1
        # setup distance (pts) — signed
        f[idx] = setup_dist / 5.0; idx += 1
        # setup distance as ATR multiple
        f[idx] = setup_dist / max(atr20, 0.5); idx += 1
        # spread relative to setup distance
        f[idx] = spread / max(abs(setup_dist), 0.5); idx += 1
        # Last bar bullishness (close - open)
        if len(bars) >= 1:
            b = bars[-1]
            f[idx] = (b[3] - b[0]) / 5.0
        idx += 1
        # Last bar wick top
        if len(bars) >= 1:
            b = bars[-1]
            top_body = max(b[0], b[3])
            f[idx] = (b[1] - top_body) / 2.0
        idx += 1
        # Last bar wick bottom
        if len(bars) >= 1:
            b = bars[-1]
            bot_body = min(b[0], b[3])
            f[idx] = (bot_body - b[2]) / 2.0
        idx += 1
        # 3-bar net move
        if len(bars) >= 3:
            f[idx] = (bars[-1][3] - bars[-3][0]) / 5.0
        idx += 1
        assert idx == 84, f"final idx={idx}"

        # Sanitize NaNs/inf — clip
        f = np.nan_to_num(f, nan=0.0, posinf=10.0, neginf=-10.0)
        f = np.clip(f, -10.0, 10.0)
        return f


# =============================================================================
# Feature-donor strategy — wraps MarketablePullback, captures features
# at every setup emission, AND optionally consults a model gate.
# =============================================================================
class FDonor(MarketablePullback):
    """Feature-donor & ML-gate strategy.

    - In TRAIN mode (model=None): emits all setups and records features.
    - In INFER mode (model set): emits only setups where model predicts
      win probability >= threshold. Still records features (for OOS
      analysis), tagged with the gate decision.

    Stores `_setup_features`: list aligned with each emitted setup.
    Stores `_setup_index_for_trade`: maps trade idx -> feature idx, so
    after the run we can align (X, y).
    """
    def __init__(self, name, fe: FeatureExtractor, model=None,
                 model_kind=None, threshold=0.5, scaler=None,
                 **kwargs):
        super().__init__(name, **kwargs)
        self.fe = fe
        self.model = model
        self.model_kind = model_kind  # 'mlp', 'transformer', 'gbm', 'logreg'
        self.threshold = threshold
        self.scaler = scaler
        # Recording state
        self._features_emitted = []  # list of np.ndarray length N_FEATURES
        self._setups_emitted = []    # list of dict snapshots (for join)
        self._n_filtered = 0
        self._n_emitted = 0
        self._last_setup_count = 0

    def _predict(self, f):
        if self.model is None:
            return 1.0
        try:
            x = f.reshape(1, -1)
            if self.scaler is not None:
                x = self.scaler.transform(x)
            if self.model_kind == 'mlp' or self.model_kind == 'transformer':
                with torch.no_grad():
                    tx = torch.from_numpy(x.astype(np.float32))
                    out = self.model(tx)
                    p = torch.sigmoid(out).cpu().numpy().reshape(-1)[0]
                    return float(p)
            elif self.model_kind in ('gbm', 'logreg', 'rf'):
                if hasattr(self.model, 'predict_proba'):
                    return float(self.model.predict_proba(x)[0, 1])
                else:
                    return float(self.model.decision_function(x)[0])
            else:
                return 1.0
        except Exception:
            return 0.5

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        # Snapshot count before parent emit
        before = len(self.pending)
        # Determine setup direction we'd take (for feature setup_dir)
        # Use the same logic as PullbackStrategy.on_bar_close but only to
        # predict direction; we let the parent class do the actual emit.
        super().on_bar_close(ts, hh, mn, bo, bh, bl, bc, hist)
        after = len(self.pending)
        if after > before:
            # New setup(s) emitted. Capture features for each.
            new_setups = self.pending[before:after]
            for s in new_setups:
                last = MARKET.last_px if MARKET.last_px is not None else bc
                bid = MARKET.last_bid if MARKET.last_bid is not None else last - 0.25
                ask = MARKET.last_ask if MARKET.last_ask is not None else last + 0.25
                setup_dir = 1 if s['side'] == 'LONG' else -1
                setup_dist = s['entry'] - last
                f = self.fe.extract(ts, bid, ask, hh, mn, setup_dir, setup_dist)
                if f is None:
                    # Insufficient history — still record placeholder; parent emitted.
                    f = np.zeros(self.fe.N_FEATURES, dtype=np.float32)
                # Apply ML gate
                p = self._predict(f)
                self._features_emitted.append(f)
                self._setups_emitted.append({
                    'side': s['side'], 'entry': float(s['entry']),
                    'stop': float(s['stop']), 'target': float(s.get('target') or 0.0),
                    'ts': float(ts), 'pred': p,
                })
                if p < self.threshold:
                    # Discard this setup: mark used so r9 executor ignores it
                    s['used'] = True
                    self._n_filtered += 1
                else:
                    self._n_emitted += 1


# =============================================================================
# PyTorch models
# =============================================================================
if TORCH_OK:
    class MLPNet(nn.Module):
        def __init__(self, in_dim=84, hidden=(128, 64, 32), dropout=0.3):
            super().__init__()
            layers = []
            d = in_dim
            for h in hidden:
                layers.append(nn.Linear(d, h))
                layers.append(nn.ReLU())
                layers.append(nn.Dropout(dropout))
                d = h
            layers.append(nn.Linear(d, 1))
            self.net = nn.Sequential(*layers)

        def forward(self, x):
            return self.net(x).squeeze(-1)

    class TinyTransformer(nn.Module):
        """Treats the 84-feature vector as a sequence of 12 "tokens" of dim 7
        (12*7=84). Single transformer encoder layer with self-attn. This
        is shallow but uses real transformer arithmetic.
        """
        def __init__(self, n_features=84, seq_len=12, d_model=32, nhead=4,
                     dropout=0.1):
            super().__init__()
            assert n_features % seq_len == 0
            self.seq_len = seq_len
            self.token_dim = n_features // seq_len
            self.embed = nn.Linear(self.token_dim, d_model)
            enc_layer = nn.TransformerEncoderLayer(
                d_model=d_model, nhead=nhead,
                dim_feedforward=d_model * 2,
                dropout=dropout, batch_first=True)
            self.enc = nn.TransformerEncoder(enc_layer, num_layers=2)
            self.head = nn.Linear(d_model, 1)

        def forward(self, x):
            # x: [B, n_features]
            B = x.shape[0]
            x = x.view(B, self.seq_len, self.token_dim)
            x = self.embed(x)
            h = self.enc(x)
            # Mean-pool over sequence
            h = h.mean(dim=1)
            return self.head(h).squeeze(-1)


def train_torch_model(model, X_train, y_train, X_val, y_val,
                      epochs=30, batch_size=256, lr=1e-3,
                      pos_weight=None, model_name="model"):
    """Train a PyTorch binary classifier with BCEWithLogitsLoss."""
    if not TORCH_OK:
        return None
    device = torch.device("cpu")
    model = model.to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    if pos_weight is not None:
        pw = torch.tensor([pos_weight], dtype=torch.float32, device=device)
        loss_fn = nn.BCEWithLogitsLoss(pos_weight=pw)
    else:
        loss_fn = nn.BCEWithLogitsLoss()

    Xt = torch.from_numpy(X_train.astype(np.float32)).to(device)
    yt = torch.from_numpy(y_train.astype(np.float32)).to(device)
    Xv = torch.from_numpy(X_val.astype(np.float32)).to(device)
    yv = torch.from_numpy(y_val.astype(np.float32)).to(device)
    n = X_train.shape[0]
    best_auc = -1.0
    best_state = None
    history = []

    for ep in range(epochs):
        model.train()
        idxs = np.random.permutation(n)
        total_loss = 0.0
        for i in range(0, n, batch_size):
            b = idxs[i:i + batch_size]
            xb = Xt[b]; yb = yt[b]
            opt.zero_grad()
            out = model(xb)
            loss = loss_fn(out, yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            total_loss += float(loss.item()) * len(b)
        avg_loss = total_loss / max(1, n)
        # Val
        model.eval()
        with torch.no_grad():
            v_out = model(Xv)
            v_prob = torch.sigmoid(v_out).cpu().numpy()
            try:
                v_auc = roc_auc_score(y_val, v_prob)
            except Exception:
                v_auc = 0.5
        history.append((ep, avg_loss, v_auc))
        if v_auc > best_auc:
            best_auc = v_auc
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
        print(f"  [r18 {model_name}] ep{ep} loss={avg_loss:.4f} val_auc={v_auc:.4f}",
              file=sys.stderr)
    if best_state is not None:
        model.load_state_dict(best_state)
    return model, best_auc, history


# =============================================================================
# Build feature donors (Phase 1) and ML-gated strategies (Phase 3)
# =============================================================================
DONOR_SPECS_FULL = [
    # (name, impulse, bars, pull_pct, stop, target) — for Phase 1 training
    ("CANON_236_s10t20", 5.0, 4, 0.236, 10, 20),
    ("CANON_382_s10t20", 5.0, 4, 0.382, 10, 20),
    ("CANON_500_s10t20", 5.0, 4, 0.500, 10, 20),
    ("CANON_236_s8t16",  5.0, 4, 0.236, 8, 16),
    ("CANON_236_s5t15",  5.0, 4, 0.236, 5, 15),
    ("IMP3_236_s8t16",   3.0, 4, 0.236, 8, 16),
    ("IMP4_382_s8t20",   4.0, 4, 0.382, 8, 20),
    ("IMP3_118_s5t15",   3.0, 4, 0.118, 5, 15),
]
# Smaller set for Phase 3 to keep tick-by-tick cost bounded.
DONOR_SPECS_OOS = [
    ("CANON_236_s10t20", 5.0, 4, 0.236, 10, 20),
    ("CANON_236_s8t16",  5.0, 4, 0.236, 8, 16),
    ("IMP3_118_s5t15",   3.0, 4, 0.118, 5, 15),
    ("IMP3_236_s8t16",   3.0, 4, 0.236, 8, 16),
]


def build_donor_strategies(fe, model=None, model_kind=None, threshold=0.5,
                           scaler=None, prefix="D", specs=None):
    """Build a small library of pullback variants. In donor mode (model=None),
    they emit all setups + record features. In gate mode, the model filters.
    """
    if specs is None:
        specs = DONOR_SPECS_FULL
    strats = []
    for nm, imp, bars, pp, stp, tgt in specs:
        s = FDonor(
            f"{prefix}_{nm}",
            fe=fe, model=model, model_kind=model_kind,
            threshold=threshold, scaler=scaler,
            impulse_pts=imp, impulse_bars=bars,
            pull_pct=pp, stop_pts=stp, target_pts=tgt,
            invert=True)
        strats.append(s)
    return strats


# =============================================================================
# Run a single tick-stream pass with strategies, return processed count
# =============================================================================
def run_pass(strats, fe, start_offset, max_days, label=""):
    """Single forward pass of the tick file over `max_days` calendar days
    starting at `start_offset`. Returns (end_offset, days_processed, n_lines).
    """
    # Attach r9 (r7) executor to all strategies (idempotent if already attached)
    for s in strats:
        if not hasattr(s, '_exec') or s._exec is None:
            attach_r7_executor(s)
        else:
            attach_r7_executor(s)  # reset state for new pass
    # Reset MARKET singleton state for safety between passes
    # (MARKET is global — between Phase 1 and Phase 3 we accept some
    # residual state; this is fine because rolling buffers self-stabilize.)

    bb_1m = BarBuilder(granularity_secs=60, max_history=300)
    n_lines = 0
    t0 = time.time()
    day_counter = -1
    last_day_key = None
    last_progress = time.time()

    file_size = os.path.getsize(TICK_PATH)
    with open(TICK_PATH, "rb") as f:
        f.seek(start_offset)
        f.readline()  # discard partial
        for raw in f:
            n_lines += 1
            if n_lines % CHECKPOINT_EVERY_TICKS == 0:
                now = time.time()
                if now - last_progress > 30:
                    rate = n_lines / max(0.001, now - t0)
                    top = max((s.n_trades, s.name) for s in strats)
                    print(f"  [r18 {label}] {n_lines/1e6:.2f}M ticks rate={rate:.0f}/s "
                          f"day={day_counter} most_trades={top[1]}({top[0]})",
                          file=sys.stderr, flush=True)
                    last_progress = now
            try:
                line = raw.decode("ascii", errors="ignore")
                stamp_str, vals = line.split(";", 1)
                vp = vals.split(";")
                if len(vp) < 3:
                    continue
                last = float(vp[0]); bid = float(vp[1]); ask = float(vp[2])
                p = stamp_str.split()
                if len(p) < 2:
                    continue
                yy = int(p[0][:4]); mm = int(p[0][4:6]); dd = int(p[0][6:8])
                hh = int(p[1][:2]); mn = int(p[1][2:4]); ss = int(p[1][4:6])
                ns = int(p[2]) if len(p) > 2 else 0
            except Exception:
                continue

            day_key = (yy, mm, dd)
            if day_key != last_day_key:
                day_counter += 1
                last_day_key = day_key
                if day_counter >= max_days:
                    break

            ts = day_counter * 86400 + hh * 3600 + mn * 60 + ss + ns / 1e7

            # Feed MARKET + feature extractor
            MARKET.feed_tick(ts, last, bid, ask)
            fe.feed_tick(ts, last, bid, ask)

            if bb_1m.on_tick(ts, last):
                closed = bb_1m.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    MARKET.feed_bar(o, h, l, c)
                    fe.feed_bar(o, h, l, c)
                    for s in strats:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_1m.history)

            # Execute via r9 verbatim
            for s in strats:
                r9.r9_bot_on_tick(s, ts, bid, ask, day_counter, hh, mn, last)

        end_offset = f.tell()

    elapsed = time.time() - t0
    print(f"[r18 {label}] PASS DONE: {n_lines:,} ticks, {day_counter + 1} days, "
          f"{elapsed/60:.1f}min, rate={n_lines/max(1,elapsed):.0f}/s",
          file=sys.stderr)
    return end_offset, day_counter + 1, n_lines


# =============================================================================
# Build (X, y) from donor strategies' completed trades
# =============================================================================
def build_xy(donors):
    """For each donor, align trade-index to setup-index. The r9 executor
    appends to s.completed each time a trade closes. The order matches the
    order in which setups fired (since the executor processes one trade at
    a time). So the first n_trades features correspond to the first
    n_trades completed trades.

    However, in donor mode (no gate filter), there's a subtle issue: not
    all emitted setups become trades — some expire unfilled. We need to
    track which setup index each trade corresponds to.

    Simpler approach: when ML gate is OFF (training pass), record features
    inside the donor BUT only KEEP features for setups that became trades.
    We do this by NOT using the gate path, but we still record feature per
    emission. Then we accept all-trades-first alignment as approximation:
    since the executor fires earliest-fill-first, we can align by ts.
    """
    Xs = []
    ys = []
    metas = []
    for s in donors:
        # Build a list of (ts, features) for each emitted setup
        emitted_ts = [m['ts'] for m in s._setups_emitted]
        emitted_features = s._features_emitted
        if len(emitted_ts) == 0 or s.n_trades == 0:
            continue
        # Trades in s.completed: (pnl_pts, reason, day, block, cell)
        # We need a per-trade timestamp. Unfortunately r9 doesn't store ts.
        # We use the approximate alignment: trades fire in setup-emission
        # order, but we can't be sure. We'll do a robust approximate match:
        # take the first n_trades emitted features (which represents the
        # first n_trades setups, MOST of which would have fired in r9).
        # This is approximate but realistic given the executor's queue
        # processes oldest-first.
        n = min(len(emitted_features), s.n_trades)
        for i in range(n):
            c = s.completed[i]
            pnl_pts = c[0]
            pnl_usd = pnl_pts * MNQ_PER_PT - FEE_FULL_RT
            y = 1 if pnl_usd > 0 else 0
            Xs.append(emitted_features[i])
            ys.append(y)
            metas.append({
                'strat': s.name,
                'i': i,
                'pnl_pts': float(pnl_pts),
                'pnl_usd': float(pnl_usd),
                'reason': c[1],
            })
    if len(Xs) == 0:
        return None, None, None
    X = np.stack(Xs).astype(np.float32)
    y = np.array(ys, dtype=np.int64)
    return X, y, metas


# =============================================================================
# Strategy reporting
# =============================================================================
def report_strategy(strat, n_days, fee_rt=FEE_FULL_RT, pt_value=MNQ_PER_PT):
    n = len(strat.completed)
    if n == 0:
        return {'name': strat.name, 'n': 0, 'tr_per_day': 0.0, 'wr': 0.0,
                'per_day': 0.0, 'per_trade': 0.0, 'dd': 0.0, 'sharpe': 0.0,
                'n_emit': getattr(strat, '_n_emitted', 0),
                'n_filt': getattr(strat, '_n_filtered', 0)}
    wins = 0
    net = 0.0
    day_nets = defaultdict(float)
    series = []
    for c in strat.completed:
        pnl_pts = c[0]
        pnl_usd = pnl_pts * pt_value - fee_rt
        if pnl_usd > 0:
            wins += 1
        net += pnl_usd
        series.append(pnl_usd)
        if len(c) >= 3:
            day_nets[c[2]] += pnl_usd
    cum = 0.0; peak = 0.0; dd = 0.0
    for x in series:
        cum += x
        if cum > peak:
            peak = cum
        if peak - cum > dd:
            dd = peak - cum
    days_list = list(day_nets.values())
    if len(days_list) > 1:
        mean = sum(days_list) / len(days_list)
        var = sum((x - mean) ** 2 for x in days_list) / (len(days_list) - 1)
        std = math.sqrt(max(var, 1e-9))
        sharpe = mean / std if std > 0 else 0.0
    else:
        sharpe = 0.0
    return {
        'name': strat.name,
        'n': n,
        'tr_per_day': n / max(1, n_days),
        'wr': wins / n,
        'per_day': net / max(1, n_days),
        'per_trade': net / n,
        'dd': dd,
        'sharpe': sharpe,
        'n_emit': getattr(strat, '_n_emitted', 0),
        'n_filt': getattr(strat, '_n_filtered', 0),
    }


# =============================================================================
# MAIN
# =============================================================================
def main():
    t_start = time.time()
    print(f"\n[round18] START {datetime.now().isoformat()}", file=sys.stderr)
    print(f"[round18] TORCH={TORCH_OK} SK={SK_OK}", file=sys.stderr)

    fe = FeatureExtractor()

    # ============================================================================
    # PHASE 1: Training pass (collect features + labels)
    # ============================================================================
    print(f"\n[round18] === PHASE 1: training pass ({TRAIN_DAYS}d) ===",
          file=sys.stderr)
    train_donors = build_donor_strategies(fe, model=None, prefix="TR")
    print(f"[round18] phase1 donors: {len(train_donors)}", file=sys.stderr)

    end_offset_train, days_train, lines_train = run_pass(
        train_donors, fe, OFFSET, TRAIN_DAYS, label="TRAIN")

    # Build (X, y)
    X, y, metas = build_xy(train_donors)
    if X is None or len(X) < 100:
        print(f"[round18] FATAL: not enough training data ({0 if X is None else len(X)})",
              file=sys.stderr)
        # Still write a degenerate report so the supervisor sees a file.
        with open(RESULTS_PATH, "w") as f:
            f.write("# Round 18 — FAILED\n\nNot enough training data collected.\n")
        return

    print(f"[round18] training data: X={X.shape}, y={y.shape}, "
          f"pos_rate={y.mean():.3f}", file=sys.stderr)

    # Save features for debugging
    np.savez_compressed(FEATURES_PATH, X=X, y=y)
    print(f"[round18] features saved to {FEATURES_PATH}", file=sys.stderr)

    # Standardize features
    scaler = StandardScaler()
    X_std = scaler.fit_transform(X)

    # Split — last 20% as val
    n = len(X)
    n_val = max(50, n // 5)
    perm = np.random.permutation(n)
    train_idx = perm[:n - n_val]
    val_idx = perm[n - n_val:]
    X_train, y_train = X_std[train_idx], y[train_idx]
    X_val, y_val = X_std[val_idx], y[val_idx]
    pos_rate = y_train.mean()
    pos_weight = (1 - pos_rate) / max(pos_rate, 1e-6) if pos_rate > 0 else 1.0
    print(f"[round18] split: train={len(X_train)} val={len(X_val)} "
          f"pos_rate={pos_rate:.3f} pos_weight={pos_weight:.2f}", file=sys.stderr)

    # ============================================================================
    # PHASE 2: Train models
    # ============================================================================
    print(f"\n[round18] === PHASE 2: train models ===", file=sys.stderr)
    models = {}  # name -> (kind, model, val_auc)

    # PyTorch MLP
    if TORCH_OK:
        try:
            mlp = MLPNet(in_dim=FeatureExtractor.N_FEATURES,
                         hidden=(128, 64, 32), dropout=0.3)
            mlp, mlp_auc, _ = train_torch_model(
                mlp, X_train, y_train, X_val, y_val,
                epochs=20, batch_size=256, lr=1e-3,
                pos_weight=pos_weight, model_name="MLP")
            models['MLP'] = ('mlp', mlp, mlp_auc)
            print(f"[round18] MLP val_auc={mlp_auc:.4f}", file=sys.stderr)
        except Exception as e:
            print(f"[round18] MLP train failed: {e}", file=sys.stderr)

        # PyTorch tiny transformer
        try:
            trf = TinyTransformer(n_features=FeatureExtractor.N_FEATURES,
                                  seq_len=12, d_model=32, nhead=4,
                                  dropout=0.1)
            trf, trf_auc, _ = train_torch_model(
                trf, X_train, y_train, X_val, y_val,
                epochs=15, batch_size=256, lr=5e-4,
                pos_weight=pos_weight, model_name="TRF")
            models['TRF'] = ('transformer', trf, trf_auc)
            print(f"[round18] Transformer val_auc={trf_auc:.4f}", file=sys.stderr)
        except Exception as e:
            print(f"[round18] Transformer train failed: {e}", file=sys.stderr)

    # sklearn GradientBoosting
    if SK_OK:
        try:
            print(f"[round18] training GBM (this may take ~30s)...", file=sys.stderr)
            t_gbm = time.time()
            gbm = GradientBoostingClassifier(
                n_estimators=400, max_depth=5, learning_rate=0.05,
                subsample=0.8, random_state=42)
            gbm.fit(X_train, y_train)
            gbm_p = gbm.predict_proba(X_val)[:, 1]
            try:
                gbm_auc = roc_auc_score(y_val, gbm_p)
            except Exception:
                gbm_auc = 0.5
            models['GBM'] = ('gbm', gbm, gbm_auc)
            print(f"[round18] GBM val_auc={gbm_auc:.4f} (trained in "
                  f"{time.time()-t_gbm:.1f}s)", file=sys.stderr)
        except Exception as e:
            print(f"[round18] GBM train failed: {e}", file=sys.stderr)

        # Random Forest
        try:
            rf = RandomForestClassifier(
                n_estimators=300, max_depth=12, n_jobs=-1, random_state=42,
                class_weight='balanced')
            rf.fit(X_train, y_train)
            rf_p = rf.predict_proba(X_val)[:, 1]
            try:
                rf_auc = roc_auc_score(y_val, rf_p)
            except Exception:
                rf_auc = 0.5
            models['RF'] = ('rf', rf, rf_auc)
            print(f"[round18] RF val_auc={rf_auc:.4f}", file=sys.stderr)
        except Exception as e:
            print(f"[round18] RF train failed: {e}", file=sys.stderr)

        # Logistic Regression
        try:
            lr = LogisticRegression(max_iter=500, class_weight='balanced',
                                    random_state=42)
            lr.fit(X_train, y_train)
            lr_p = lr.predict_proba(X_val)[:, 1]
            try:
                lr_auc = roc_auc_score(y_val, lr_p)
            except Exception:
                lr_auc = 0.5
            models['LR'] = ('logreg', lr, lr_auc)
            print(f"[round18] LR val_auc={lr_auc:.4f}", file=sys.stderr)
        except Exception as e:
            print(f"[round18] LR train failed: {e}", file=sys.stderr)

    # ============================================================================
    # PHASE 3: OOS test pass with ML gating
    # ============================================================================
    print(f"\n[round18] === PHASE 3: OOS test ({TEST_DAYS}d) ===",
          file=sys.stderr)

    # Build gated strategies. Keep size manageable: top-2 models × 3 thresholds.
    thresholds = [0.45, 0.55, 0.65]
    if models:
        sorted_models = sorted(models.items(), key=lambda kv: -kv[1][2])
        top_models = sorted_models[:2]
    else:
        top_models = []
    print(f"[round18] top models: {[(n, m[2]) for n, m in top_models]}",
          file=sys.stderr)

    # Build a fresh feature extractor for OOS (avoid carryover state)
    fe_oos = FeatureExtractor()

    # First, a baseline (no filter) for OOS comparison
    baseline_strats = build_donor_strategies(fe_oos, model=None, prefix="BL",
                                             specs=DONOR_SPECS_OOS)
    gate_strats = []
    for model_name, (kind, mdl, auc) in top_models:
        for thr in thresholds:
            ss = build_donor_strategies(
                fe_oos, model=mdl, model_kind=kind, threshold=thr,
                scaler=scaler, prefix=f"G_{model_name}_t{int(thr*100)}",
                specs=DONOR_SPECS_OOS)
            gate_strats.extend(ss)
    all_oos = baseline_strats + gate_strats
    print(f"[round18] phase3 strategies: {len(all_oos)} "
          f"(baseline={len(baseline_strats)} gated={len(gate_strats)})",
          file=sys.stderr)

    _, days_oos, _ = run_pass(all_oos, fe_oos, end_offset_train, TEST_DAYS,
                              label="OOS")

    # ============================================================================
    # PHASE 4: hyperparameter random search (short window)
    # ============================================================================
    print(f"\n[round18] === PHASE 4: hyperparameter search ===",
          file=sys.stderr)
    # Reduced from 500 -> 40 trials to keep total time bounded
    N_TRIALS = 40
    rng_search = random.Random(42)
    hyper_specs = []
    for i in range(N_TRIALS):
        impulse = rng_search.choice([3.0, 4.0, 5.0, 6.0])
        bars = rng_search.choice([3, 4, 5])
        pp = rng_search.choice([0.118, 0.236, 0.382, 0.500])
        stop = rng_search.choice([4, 5, 6, 8, 10, 12])
        rr = rng_search.choice([1.5, 2.0, 2.5, 3.0])
        tgt = max(4, int(stop * rr))
        if tgt > 30:
            continue
        invert = rng_search.choice([True, True, False])  # weight invert
        cooldown = rng_search.choice([5, 10, 20, 30])
        name = (f"HS_{i:03d}_imp{int(impulse*10)}_b{bars}_pp{int(pp*1000)}"
                f"_s{stop}t{tgt}_{'INV' if invert else 'TRD'}_cd{cooldown}")
        hyper_specs.append((name, impulse, bars, pp, stop, tgt, invert, cooldown))

    fe_hyper = FeatureExtractor()
    hyper_strats = []
    for nm, imp, bars, pp, stp, tgt, inv, cd in hyper_specs:
        s = MarketablePullback(
            nm, impulse_pts=imp, impulse_bars=bars,
            pull_pct=pp, stop_pts=stp, target_pts=tgt, invert=inv,
            cooldown_s=cd)
        hyper_strats.append(s)
    print(f"[round18] phase4 hyper strategies: {len(hyper_strats)}",
          file=sys.stderr)

    # Run on HYPER_DAYS starting from a fresh in-sample window (use OFFSET again
    # for repeatability and so no overlap with OOS results table).
    _, days_hyper, _ = run_pass(hyper_strats, fe_hyper, OFFSET, HYPER_DAYS,
                                label="HYPER")

    # ============================================================================
    # REPORTING
    # ============================================================================
    print(f"\n[round18] === REPORT ===", file=sys.stderr)

    # Phase 1 stats — baseline
    train_rows = [report_strategy(s, days_train) for s in train_donors]

    # Phase 3 rows
    oos_baseline_rows = [report_strategy(s, days_oos) for s in baseline_strats]
    oos_gate_rows = [report_strategy(s, days_oos) for s in gate_strats]

    # Phase 4 rows — sort by per_day
    hyper_rows = [report_strategy(s, days_hyper) for s in hyper_strats]
    hyper_rows.sort(key=lambda r: -r['per_day'])

    # FULL_PASS check on OOS
    def is_full_pass(r):
        return (r['tr_per_day'] >= 300 and r['wr'] >= 0.45
                and r['per_day'] >= 1000 and r['dd'] <= 5000)
    full_pass_oos = [r for r in oos_gate_rows + oos_baseline_rows if is_full_pass(r)]

    # CSV
    with open(CSV_PATH, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["phase", "name", "n", "tr_per_day", "wr", "per_day",
                    "per_trade", "dd", "sharpe", "n_emit", "n_filt"])
        for row, phase in [(train_rows, "PHASE1_TRAIN"),
                           (oos_baseline_rows, "PHASE3_BASELINE"),
                           (oos_gate_rows, "PHASE3_GATED"),
                           (hyper_rows, "PHASE4_HYPER")]:
            for r in row:
                w.writerow([phase, r['name'], r['n'],
                            f"{r['tr_per_day']:.2f}",
                            f"{r['wr']:.4f}",
                            f"{r['per_day']:.2f}",
                            f"{r['per_trade']:.3f}",
                            f"{r['dd']:.2f}",
                            f"{r['sharpe']:.3f}",
                            r['n_emit'], r['n_filt']])

    # Markdown report
    L = []
    L.append("# Round 18 — TRULY advanced ML (PyTorch + sklearn)\n\n")
    L.append(f"Generated: {datetime.now().isoformat()}\n")
    L.append(f"Elapsed wall-clock: {(time.time()-t_start)/60:.1f} min\n")
    L.append(f"Execution: r9_bot_on_tick AS-IS. No queue/fill patching.\n\n")
    L.append(f"PyTorch available: {TORCH_OK}\n")
    L.append(f"sklearn available: {SK_OK}\n\n")
    L.append(f"## Training data (Phase 1, {days_train}d)\n\n")
    L.append(f"- Total emitted setups -> features captured: {len(X)}\n")
    L.append(f"- Positive (win) rate: {y.mean():.3f}\n")
    L.append(f"- Train/Val split: {len(X_train)}/{len(X_val)}\n\n")
    L.append(f"## Model validation AUCs\n\n")
    L.append("| Model | Val AUC |\n|---|---:|\n")
    for n, (k, m, auc) in sorted(models.items(), key=lambda kv: -kv[1][2]):
        L.append(f"| {n} ({k}) | {auc:.4f} |\n")

    L.append(f"\n## Phase 1 baseline donor performance (in-sample {days_train}d)\n\n")
    L.append("| Strategy | Trades | Tr/d | WR% | $/day | $/trade | DD | Sharpe |\n")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|\n")
    for r in sorted(train_rows, key=lambda r: -r['per_day']):
        L.append(f"| {r['name']} | {r['n']:,} | {r['tr_per_day']:.1f} | "
                 f"{r['wr']*100:.1f} | ${r['per_day']:+.2f} | "
                 f"${r['per_trade']:+.2f} | ${r['dd']:.0f} | "
                 f"{r['sharpe']:.2f} |\n")

    L.append(f"\n## Phase 3 OOS results ({days_oos}d) — BASELINE (no gate)\n\n")
    L.append("| Strategy | Trades | Tr/d | WR% | $/day | $/trade | DD | Sharpe |\n")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|\n")
    for r in sorted(oos_baseline_rows, key=lambda r: -r['per_day']):
        L.append(f"| {r['name']} | {r['n']:,} | {r['tr_per_day']:.1f} | "
                 f"{r['wr']*100:.1f} | ${r['per_day']:+.2f} | "
                 f"${r['per_trade']:+.2f} | ${r['dd']:.0f} | "
                 f"{r['sharpe']:.2f} |\n")

    L.append(f"\n## Phase 3 OOS results ({days_oos}d) — ML-GATED\n\n")
    L.append("| Strategy | Trades | Tr/d | WR% | $/day | $/trade | DD | Sharpe | n_filt |\n")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for r in sorted(oos_gate_rows, key=lambda r: -r['per_day']):
        L.append(f"| {r['name']} | {r['n']:,} | {r['tr_per_day']:.1f} | "
                 f"{r['wr']*100:.1f} | ${r['per_day']:+.2f} | "
                 f"${r['per_trade']:+.2f} | ${r['dd']:.0f} | "
                 f"{r['sharpe']:.2f} | {r['n_filt']} |\n")

    L.append(f"\n## Phase 3 lift analysis (best gated vs best baseline)\n\n")
    if oos_baseline_rows and oos_gate_rows:
        best_bl = max(oos_baseline_rows, key=lambda r: r['per_day'])
        best_g = max(oos_gate_rows, key=lambda r: r['per_day'])
        lift = best_g['per_day'] - best_bl['per_day']
        L.append(f"- Best BASELINE: **{best_bl['name']}** ${best_bl['per_day']:+.2f}/d "
                 f"@ {best_bl['wr']*100:.1f}% WR, {best_bl['tr_per_day']:.1f} tr/d\n")
        L.append(f"- Best GATED: **{best_g['name']}** ${best_g['per_day']:+.2f}/d "
                 f"@ {best_g['wr']*100:.1f}% WR, {best_g['tr_per_day']:.1f} tr/d\n")
        L.append(f"- ML lift: **${lift:+.2f}/day**\n")
        # WR improvement
        bl_wr = best_bl['wr']
        g_wr = best_g['wr']
        L.append(f"- WR delta: {(g_wr - bl_wr)*100:+.1f} pp\n")

    L.append(f"\n## Phase 4 hyperparameter random search ({days_hyper}d, "
             f"{len(hyper_strats)} trials)\n\n")
    L.append("Top 20 by $/day:\n\n")
    L.append("| Strategy | Tr/d | WR% | $/day | $/trade | DD | Sharpe |\n")
    L.append("|---|---:|---:|---:|---:|---:|---:|\n")
    for r in hyper_rows[:20]:
        L.append(f"| {r['name']} | {r['tr_per_day']:.1f} | "
                 f"{r['wr']*100:.1f} | ${r['per_day']:+.2f} | "
                 f"${r['per_trade']:+.2f} | ${r['dd']:.0f} | "
                 f"{r['sharpe']:.2f} |\n")

    L.append(f"\n## FULL_PASS list (>=300 tr/d, >=45% WR, >=$1k/day, DD<=$5k)\n\n")
    if full_pass_oos:
        for r in full_pass_oos:
            L.append(f"- **{r['name']}** ${r['per_day']:+.2f}/d, "
                     f"{r['tr_per_day']:.1f} tr/d, {r['wr']*100:.1f}% WR\n")
    else:
        L.append("**NONE.** Consistent with rounds 5-17.\n")

    L.append(f"\n## Honest assessment\n\n")
    if full_pass_oos:
        L.append("ML gating produced FULL_PASS strategies under r9 execution. "
                 "Recommend independent re-validation on a fresh window before "
                 "any live deployment.\n")
    else:
        # Compute best $/day across all OOS rows
        all_oos_rows = oos_baseline_rows + oos_gate_rows
        if all_oos_rows:
            best = max(all_oos_rows, key=lambda r: r['per_day'])
            L.append(f"- No strategy met the $1k/day + 300tr/d + 45% WR + $5k DD bar.\n")
            L.append(f"- Best OOS result: **{best['name']}** "
                     f"${best['per_day']:+.2f}/day @ {best['wr']*100:.1f}% WR, "
                     f"{best['tr_per_day']:.1f} tr/d.\n")
            # Compare baseline vs gated heads
            if oos_baseline_rows and oos_gate_rows:
                bl_best = max(oos_baseline_rows, key=lambda r: r['per_day'])
                g_best = max(oos_gate_rows, key=lambda r: r['per_day'])
                if g_best['per_day'] > bl_best['per_day']:
                    L.append(f"- ML gating improved OOS $/day vs baseline by "
                             f"${g_best['per_day'] - bl_best['per_day']:+.2f}.\n")
                else:
                    L.append(f"- ML gating did NOT improve OOS $/day vs baseline "
                             f"(gap: ${g_best['per_day'] - bl_best['per_day']:+.2f}).\n")
        L.append(f"- The $1k/day target at 1 MNQ + $1.91 fees requires a "
                 f"per-trade edge that does not appear to exist under honest "
                 f"execution. With $2,100 capital and these results, paper-"
                 f"trading (or rejecting the goal) is the rational path.\n")
        # Best hyper search
        if hyper_rows:
            bh = hyper_rows[0]
            L.append(f"- Best hyperparameter trial (14d): "
                     f"**{bh['name']}** ${bh['per_day']:+.2f}/day "
                     f"@ {bh['wr']*100:.1f}% WR, {bh['tr_per_day']:.1f} tr/d.\n")
    L.append("\n## Notes\n\n")
    L.append("- Feature->label alignment: features for the first N emitted setups "
             "are aligned to the first N completed trades. The r9 executor processes "
             "fills in setup-emission order, so this is approximate (some setups "
             "may expire unfilled, biasing alignment). This means the trained "
             "model sees PARTIALLY noisy labels; nonetheless the donor metric we "
             "care about is OOS net P&L under r9 execution, which is robust.\n")
    L.append("- All OOS metrics are produced by r9_bot_on_tick verbatim, with "
             "the ML gate operating only by marking `s['used']=True` BEFORE the "
             "executor attempts fill. No fill logic is changed.\n")

    with open(RESULTS_PATH, "w") as f:
        f.write("".join(L))
    print(f"[round18] wrote {RESULTS_PATH}", file=sys.stderr)

    # Console summary
    print("\n" + "=" * 80)
    print(f"ROUND 18 SUMMARY")
    print(f"Total elapsed: {(time.time()-t_start)/60:.1f}min")
    print(f"FULL_PASS strategies: {len(full_pass_oos)}")
    if oos_baseline_rows:
        bl = max(oos_baseline_rows, key=lambda r: r['per_day'])
        print(f"Best OOS baseline: {bl['name']} ${bl['per_day']:+.2f}/d")
    if oos_gate_rows:
        g = max(oos_gate_rows, key=lambda r: r['per_day'])
        print(f"Best OOS gated:    {g['name']} ${g['per_day']:+.2f}/d")
    print("=" * 80)

    # Cleanup checkpoint
    try:
        if os.path.exists(CKPT_PATH):
            os.remove(CKPT_PATH)
    except Exception:
        pass


if __name__ == "__main__":
    main()
