#!/usr/bin/env python3
"""Round 19 — ML threshold sweet-spot search.

Round 18 found a real edge: MLP at threshold 0.65 produces 54.5% WR
versus 36% baseline, but only 0.5 trades/day. This round finds the
sweet spot where WR holds while volume scales.

Strict integrity contract:
  * Execution: research.round9_search.r9_bot_on_tick AS-IS.
  * No queue/fill patching. No custom executor.
  * Features captured at the moment of setup-emission. Labels derived
    from r9-executor trade outcomes.

Workflow:

  Phase 1: Training pass (days 0-44 = 45 days)
    - Feature donor: CANON_236_s10t20 + 4 other base strategies
    - Emit ALL setups, capture features + labels via r9 outcomes
    - Aim for ~50K training samples

  Phase 2: Train models
    - PyTorch MLP (3-layer, dropout, batchnorm)
    - LightGBM (2000 trees, max_depth 8)
    - Stacked ensemble (average of probs)
    - Probability calibration (isotonic) on held-out val set

  Phase 3: Single OOS pass (days 45-59 = 15 days) with ALL gated
           strategies in parallel.
    - Track 1: CANON_236_s10t20 × 41 thresholds × MLP (0.40-0.60 step 0.005)
    - Track 2: CANON_236_s10t20 × 7 thresholds × {MLP, LGB, ENS, MLP_cal}
    - Track 3: 3 alternative bases × 5 thresholds × MLP
    - Each strategy shares a setup-key->prediction cache so the model
      is invoked ONCE per emitted setup, not per strategy.

  Phase 4: Reporting
    - Threshold sweep curve (Pareto WR vs volume vs $/day)
    - Best (model × threshold × base) combination
    - FULL_PASS check
    - Honest assessment + round 20 recommendations

Output:
  /home/user/HFTBot/research/round19_results.md
  /home/user/HFTBot/research/round19_summary.csv
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

# Env defaults (mirror r18 baseline)
os.environ.setdefault("STRAT_INVERT", "1")
os.environ.setdefault("STRAT_PULL_PCT", "0.236")
os.environ.setdefault("STRAT_STOP_PTS", "10.0")
os.environ.setdefault("STRAT_TARGET_PTS", "20.0")
os.environ.setdefault("STRAT_IMPULSE_PTS", "5.0")
os.environ.setdefault("STRAT_IMPULSE_BARS", "4")
os.environ.setdefault("STRAT_COOLDOWN_SECS", "10")
os.environ.setdefault("BOT_HTF_TREND_FILTER", "0")

import numpy as np

# Lib imports (order matters — round8 sets up MARKET singleton)
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
TRAIN_DAYS = 45    # days 0-44
TEST_DAYS = 15     # days 45-59
CHECKPOINT_EVERY_TICKS = 25_000

CKPT_PATH = "/home/user/HFTBot/research/round19_checkpoint.pkl"
RESULTS_PATH = "/home/user/HFTBot/research/round19_results.md"
CSV_PATH = "/home/user/HFTBot/research/round19_summary.csv"
FEATURES_PATH = "/home/user/HFTBot/research/round19_features.npz"
MODELS_PATH = "/home/user/HFTBot/research/round19_models.pkl"

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
    print(f"[r19] PyTorch unavailable: {e}", file=sys.stderr)
    torch = None

# sklearn
SK_OK = False
try:
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.isotonic import IsotonicRegression
    from sklearn.metrics import roc_auc_score
    SK_OK = True
except Exception as e:
    print(f"[r19] sklearn unavailable: {e}", file=sys.stderr)

# LightGBM
LGB_OK = False
try:
    import lightgbm as lgb
    LGB_OK = True
except Exception as e:
    print(f"[r19] lightgbm unavailable: {e}", file=sys.stderr)


# =============================================================================
# FEATURE EXTRACTOR — round 18 features + new features (track 2)
# =============================================================================
class FeatureExtractor:
    """Builds a feature vector at any (ts, bid, ask, hh, mn) moment.
    Round 19 = round 18 (84 base features) + 16 new features = 100 total.
    """
    N_BASE = 84
    N_NEW = 16
    N_FEATURES = 100

    def __init__(self, bar_history_len=120, tick_history_len=4000):
        self.bars = deque(maxlen=bar_history_len)
        self.ticks = deque(maxlen=tick_history_len)
        self.signed_tick_buf = deque(maxlen=2000)
        self.session_vwap_num = 0.0
        self.session_vwap_den = 0
        self._last_session_day = None
        self._last_tick_px = None
        # NEW: bar-range history for vol regime
        self.bar_ranges = deque(maxlen=200)
        # NEW: setup-emission outcomes for rolling WR
        self.recent_setup_outcomes = deque(maxlen=20)

    def feed_tick(self, ts, last, bid, ask):
        if self._last_tick_px is not None:
            if last > self._last_tick_px:
                self.signed_tick_buf.append((ts, 1))
            elif last < self._last_tick_px:
                self.signed_tick_buf.append((ts, -1))
        self._last_tick_px = last
        self.ticks.append((ts, last, bid, ask))
        day = int(ts // 86400)
        if day != self._last_session_day:
            self._last_session_day = day
            self.session_vwap_num = 0.0
            self.session_vwap_den = 0
        self.session_vwap_num += last
        self.session_vwap_den += 1

    def feed_bar(self, o, h, l, c):
        self.bars.append((o, h, l, c))
        self.bar_ranges.append(h - l)

    def record_setup_outcome(self, win):
        self.recent_setup_outcomes.append(1 if win else 0)

    def extract(self, ts, bid, ask, hh, mn, setup_dir=0, setup_dist=0.0):
        if len(self.bars) < 20:
            return None
        bars = list(self.bars)
        last = (bid + ask) / 2.0
        f = np.zeros(self.N_FEATURES, dtype=np.float32)
        idx = 0

        # ---- Base 84 features (same as round 18) ----
        # Price action (0-19)
        for i in range(10):
            if len(bars) >= i + 2:
                b = bars[-(i + 1)]; pb = bars[-(i + 2)]
                f[idx] = (b[3] - pb[3]) / 5.0
            idx += 1
        for i in range(5):
            if len(bars) >= i + 1:
                b = bars[-(i + 1)]
                rng = max(b[1] - b[2], 0.01)
                f[idx] = rng / 5.0
            idx += 1
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
        if len(bars) >= 60:
            highs = [b[1] for b in bars[-60:]]
            lows = [b[2] for b in bars[-60:]]
            hi = max(highs); lo = min(lows)
            rg = hi - lo
            f[idx] = (last - lo) / max(rg, 0.01)
        idx += 1
        # idx == 20

        # Microstructure (20-39)
        spread = ask - bid
        f[idx] = spread / 0.5; idx += 1
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
        for w in (10.0, 30.0, 60.0, 300.0):
            cnt = sum(1 for t, _, _, _ in self.ticks if t >= ts - w)
            f[idx] = (cnt / w) / 50.0
            idx += 1
        for w in (30.0, 60.0, 300.0):
            cutoff = ts - w
            bal = sum(s for t, s in self.signed_tick_buf if t >= cutoff)
            f[idx] = bal / 50.0
            idx += 1
        for w in (60.0, 300.0):
            cutoff = ts - w
            cnt = sum(1 for t, lst, _, _ in self.ticks
                      if t >= cutoff and abs(lst - last) < 0.5)
            f[idx] = cnt / 100.0
            idx += 1
        recent_dirs = list(self.signed_tick_buf)[-100:]
        if recent_dirs:
            bal100 = sum(s for _, s in recent_dirs)
            f[idx] = bal100 / 100.0
        idx += 1
        atr5 = 0.0
        if len(bars) >= 5:
            atr5 = sum((b[1] - b[2]) for b in bars[-5:]) / 5.0
        f[idx] = spread / max(atr5, 0.5); idx += 1
        persist_s = 0.0
        for t, _, b, _ in reversed(self.ticks):
            if abs(b - bid) > 0.25:
                break
            persist_s = ts - t
            if persist_s > 60:
                break
        f[idx] = persist_s / 30.0; idx += 1
        persist_p = 0.0
        for t, lst, _, _ in reversed(self.ticks):
            if abs(lst - last) > 0.5:
                break
            persist_p = ts - t
            if persist_p > 60:
                break
        f[idx] = persist_p / 30.0; idx += 1
        if self.session_vwap_den > 0:
            vwap = self.session_vwap_num / self.session_vwap_den
            f[idx] = (last - vwap) / 5.0
        idx += 1
        f[idx] = (last - (bid + ask) / 2.0) / 0.25; idx += 1
        cutoff = ts - 60.0
        pos = sum(1 for t, s in self.signed_tick_buf if t >= cutoff and s > 0)
        neg = sum(1 for t, s in self.signed_tick_buf if t >= cutoff and s < 0)
        f[idx] = (pos - neg) / max(pos + neg, 1); idx += 1
        cnt5 = sum(1 for t, _, _, _ in self.ticks if t >= ts - 5.0)
        f[idx] = (cnt5 / 5.0) / 50.0; idx += 1
        # idx == 40

        # Vol regime (40-54)
        if len(bars) >= 5:
            f[idx] = sum((b[1] - b[2]) for b in bars[-5:]) / 5.0 / 5.0
        idx += 1
        atr20 = 0.0
        if len(bars) >= 20:
            atr20 = sum((b[1] - b[2]) for b in bars[-20:]) / 20.0
            f[idx] = atr20 / 5.0
        idx += 1
        atr60_val = 0.0
        if len(bars) >= 60:
            atr60_val = sum((b[1] - b[2]) for b in bars[-60:]) / 60.0
            f[idx] = atr60_val / 5.0
            f[idx + 1] = (atr20 / max(atr60_val, 0.01)) - 1.0
        idx += 2
        for w in (5, 15, 60):
            if len(bars) >= w + 1:
                rets = [bars[-i][3] - bars[-i - 1][3] for i in range(1, w + 1)]
                vol = math.sqrt(sum(r * r for r in rets) / len(rets))
                f[idx] = vol / 5.0
            idx += 1
        if len(bars) >= 60:
            ranges = [b[1] - b[2] for b in bars[-60:]]
            mean = sum(ranges) / len(ranges)
            var = sum((r - mean) ** 2 for r in ranges) / max(1, len(ranges) - 1)
            std = math.sqrt(max(var, 1e-9))
            cur_rng = bars[-1][1] - bars[-1][2]
            f[idx] = (cur_rng - mean) / max(std, 0.01)
        idx += 1
        if len(bars) >= 35:
            closes = [b[3] for b in bars[-35:]]
            mean = sum(closes) / len(closes)
            dev = [c - mean for c in closes]
            cum = 0; mn_v = 0; mx_v = 0
            for d in dev:
                cum += d
                if cum > mx_v: mx_v = cum
                if cum < mn_v: mn_v = cum
            rng = mx_v - mn_v
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
        if len(bars) >= 60:
            ranges_60 = sorted(b[1] - b[2] for b in bars[-60:])
            cur_rng = bars[-1][1] - bars[-1][2]
            cnt = sum(1 for r in ranges_60 if r < cur_rng)
            f[idx] = cnt / len(ranges_60)
        idx += 1
        if len(bars) >= 20:
            tr_sum = 0.0; highs = []; lows = []
            for i in range(len(bars) - 20, len(bars)):
                b = bars[i]
                pc = bars[i - 1][3] if i > 0 else b[3]
                tr = max(b[1] - b[2], abs(b[1] - pc), abs(b[2] - pc))
                tr_sum += tr
                highs.append(b[1]); lows.append(b[2])
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
        f[idx] = MARKET.atr_pct()
        idx += 1
        f[idx] = spread / max(atr20, 0.5)
        idx += 1
        if len(bars) >= 60:
            atr5_v = sum((b[1] - b[2]) for b in bars[-5:]) / 5.0
            atr60v = sum((b[1] - b[2]) for b in bars[-60:]) / 60.0
            f[idx] = (atr60v / max(atr5_v, 0.01)) - 1.0
        idx += 1
        if len(bars) >= 20:
            ys = [b[3] for b in bars[-20:]]
            xs = list(range(20))
            mx = sum(xs) / 20; my = sum(ys) / 20
            num = sum((xs[i] - mx) * (ys[i] - my) for i in range(20))
            den = sum((xs[i] - mx) ** 2 for i in range(20))
            slope = num / max(den, 1e-9)
            f[idx] = slope / 0.5
        idx += 1
        # idx == 55

        # Time features (55-74)
        f[idx] = math.sin(2 * math.pi * hh / 24); idx += 1
        f[idx] = math.cos(2 * math.pi * hh / 24); idx += 1
        f[idx] = math.sin(2 * math.pi * mn / 60); idx += 1
        f[idx] = math.cos(2 * math.pi * mn / 60); idx += 1
        dow = int((ts // 86400) % 7)
        for i in range(7):
            f[idx + i] = 1.0 if dow == i else 0.0
        idx += 7
        rth_open_min = 13 * 60 + 30
        cur_min = hh * 60 + mn
        f[idx] = (cur_min - rth_open_min) / 390.0; idx += 1
        rth_close = 20 * 60
        f[idx] = (rth_close - cur_min) / 390.0; idx += 1
        big_move_age = 600.0
        for t, lst, _, _ in reversed(self.ticks):
            if abs(lst - last) > 5.0:
                big_move_age = ts - t
                break
        f[idx] = min(big_move_age / 600.0, 1.0); idx += 1
        f[idx] = 1.0 if (rth_open_min <= cur_min < rth_close) else 0.0; idx += 1
        f[idx] = 1.0 if cur_min < rth_open_min or cur_min >= 22 * 60 else 0.0; idx += 1
        sec_of_day = (hh * 3600 + mn * 60) / 86400.0
        f[idx] = sec_of_day; idx += 1
        f[idx] = mn / 60.0; idx += 1
        f[idx] = 1.0 if (mn < 5 or mn > 55) else 0.0; idx += 1
        f[idx] = 1.0 if (hh == 0 or hh == 23) else 0.0; idx += 1
        # idx == 75

        # Setup-specific (75-83)
        f[idx] = 1.0 if setup_dir > 0 else 0.0; idx += 1
        f[idx] = 1.0 if setup_dir < 0 else 0.0; idx += 1
        f[idx] = setup_dist / 5.0; idx += 1
        f[idx] = setup_dist / max(atr20, 0.5); idx += 1
        f[idx] = spread / max(abs(setup_dist), 0.5); idx += 1
        if len(bars) >= 1:
            b = bars[-1]
            f[idx] = (b[3] - b[0]) / 5.0
        idx += 1
        if len(bars) >= 1:
            b = bars[-1]
            top_body = max(b[0], b[3])
            f[idx] = (b[1] - top_body) / 2.0
        idx += 1
        if len(bars) >= 1:
            b = bars[-1]
            bot_body = min(b[0], b[3])
            f[idx] = (bot_body - b[2]) / 2.0
        idx += 1
        if len(bars) >= 3:
            f[idx] = (bars[-1][3] - bars[-3][0]) / 5.0
        idx += 1
        # idx == 84

        # === NEW: 16 features (84-99) ===
        # Multi-bar momentum (5/15/60)
        for w in (5, 15, 60):
            if len(bars) >= w + 1:
                f[idx] = (bars[-1][3] - bars[-w - 1][3]) / 5.0
            idx += 1
        # Spread vs ATR z-score (60-bar)
        if len(bars) >= 60 and len(self.ticks) >= 60:
            cutoff = ts - 60.0 * 60.0
            sp_hist = [a - b for t, _, b, a in self.ticks if t >= cutoff]
            if len(sp_hist) >= 10:
                mean = sum(sp_hist) / len(sp_hist)
                var = sum((s - mean) ** 2 for s in sp_hist) / max(1, len(sp_hist) - 1)
                std = math.sqrt(max(var, 1e-9))
                f[idx] = (spread - mean) / max(std, 0.01)
        idx += 1
        # Setup-recent-WR (rolling 20 — note: this is per-FE shared across strats)
        if len(self.recent_setup_outcomes) >= 5:
            f[idx] = sum(self.recent_setup_outcomes) / len(self.recent_setup_outcomes)
        else:
            f[idx] = 0.337  # baseline pop rate
        idx += 1
        # Time-of-day × day-of-week interaction (cur_min/(60*24) * dow_norm)
        f[idx] = (cur_min / 1440.0) * (dow / 6.0)
        idx += 1
        # Distance to nearest round number (50pt grid for NQ)
        nearest50 = round(last / 50.0) * 50.0
        f[idx] = (last - nearest50) / 25.0  # normalized to [-1,1]
        idx += 1
        nearest25 = round(last / 25.0) * 25.0
        f[idx] = (last - nearest25) / 12.5
        idx += 1
        # Volatility regime classification (low/medium/high via ATR60 percentile)
        if len(self.bar_ranges) >= 60:
            ranges = list(self.bar_ranges)
            cur = bars[-1][1] - bars[-1][2]
            sorted_r = sorted(ranges)
            cnt = sum(1 for r in sorted_r if r < cur)
            pct = cnt / len(sorted_r)
            f[idx] = 1.0 if pct < 0.33 else 0.0  # low
            f[idx + 1] = 1.0 if 0.33 <= pct < 0.67 else 0.0  # mid
            f[idx + 2] = 1.0 if pct >= 0.67 else 0.0  # high
        idx += 3
        # Bar shape: body-to-range ratio
        if len(bars) >= 1:
            b = bars[-1]
            body = abs(b[3] - b[0])
            rng = max(b[1] - b[2], 0.01)
            f[idx] = body / rng
        idx += 1
        # Bull/bear pressure last 5 bars
        if len(bars) >= 5:
            bulls = sum(1 for b in bars[-5:] if b[3] > b[0])
            f[idx] = (bulls - 2.5) / 2.5  # in [-1, 1]
        idx += 1
        # ATR ratio (5/20)
        if atr20 > 0 and atr5 > 0:
            f[idx] = (atr5 / atr20) - 1.0
        idx += 1
        # Last bar range vs ATR20
        if len(bars) >= 1 and atr20 > 0:
            f[idx] = (bars[-1][1] - bars[-1][2]) / atr20
        idx += 1
        # Tick volatility (std of 100 recent last-prices)
        if len(self.ticks) >= 50:
            recent = [lst for _, lst, _, _ in list(self.ticks)[-100:]]
            mean = sum(recent) / len(recent)
            var = sum((r - mean) ** 2 for r in recent) / max(1, len(recent) - 1)
            f[idx] = math.sqrt(max(var, 1e-9)) / 2.0
        idx += 1
        assert idx == self.N_FEATURES, f"final idx={idx} expected {self.N_FEATURES}"

        # Sanitize
        f = np.nan_to_num(f, nan=0.0, posinf=10.0, neginf=-10.0)
        f = np.clip(f, -10.0, 10.0)
        return f


# =============================================================================
# Shared model-prediction cache: each setup-emission is fingerprinted and
# the model is queried at most once per fingerprint.
# =============================================================================
class PredictionCache:
    def __init__(self):
        self.cache = {}  # fingerprint -> {model_name: prob}

    def get(self, fp, model_name):
        d = self.cache.get(fp)
        if d is None:
            return None
        return d.get(model_name)

    def set(self, fp, model_name, prob):
        if fp not in self.cache:
            self.cache[fp] = {}
        self.cache[fp][model_name] = prob

    def clear(self):
        self.cache.clear()


# =============================================================================
# Feature-donor / ML-gate strategy (same as r18 but with shared cache)
# =============================================================================
class FDonor(MarketablePullback):
    """Feature-donor + ML-gate strategy.

    - In TRAIN mode (model=None): emits all setups + records features.
    - In INFER mode (model set): emits only setups where p >= threshold.
      Uses shared PredictionCache to avoid recomputing for the same setup
      across multiple strategies (different thresholds same model).
    """
    def __init__(self, name, fe: FeatureExtractor,
                 model=None, model_name=None, model_kind=None,
                 threshold=0.5, scaler=None, calibrator=None,
                 cache: PredictionCache = None,
                 **kwargs):
        super().__init__(name, **kwargs)
        self.fe = fe
        self.model = model
        self.model_name = model_name
        self.model_kind = model_kind
        self.threshold = threshold
        self.scaler = scaler
        self.calibrator = calibrator
        self.cache = cache
        # Recording
        self._features_emitted = []
        self._setups_emitted = []
        self._n_filtered = 0
        self._n_emitted = 0

    def _raw_predict(self, f):
        if self.model is None:
            return 1.0
        try:
            x = f.reshape(1, -1)
            if self.scaler is not None:
                x = self.scaler.transform(x)
            if self.model_kind in ('mlp', 'transformer'):
                with torch.no_grad():
                    tx = torch.from_numpy(x.astype(np.float32))
                    out = self.model(tx)
                    p = torch.sigmoid(out).cpu().numpy().reshape(-1)[0]
                    return float(p)
            elif self.model_kind == 'lgb':
                return float(self.model.predict(x)[0])
            elif self.model_kind in ('gbm', 'logreg', 'rf'):
                if hasattr(self.model, 'predict_proba'):
                    return float(self.model.predict_proba(x)[0, 1])
                return float(self.model.decision_function(x)[0])
            elif self.model_kind == 'ensemble':
                # Ensemble carries a list of (model, kind, scaler) tuples
                probs = []
                for sub_model, sub_kind, sub_scaler in self.model:
                    xx = sub_scaler.transform(f.reshape(1, -1)) if sub_scaler is not None else f.reshape(1, -1)
                    if sub_kind in ('mlp', 'transformer'):
                        with torch.no_grad():
                            tx = torch.from_numpy(xx.astype(np.float32))
                            o = sub_model(tx)
                            probs.append(float(torch.sigmoid(o).cpu().numpy().reshape(-1)[0]))
                    elif sub_kind == 'lgb':
                        probs.append(float(sub_model.predict(xx)[0]))
                    else:
                        probs.append(float(sub_model.predict_proba(xx)[0, 1]))
                return float(sum(probs) / len(probs)) if probs else 0.5
            return 1.0
        except Exception as e:
            return 0.5

    def _predict(self, fp, f):
        if self.model is None:
            return 1.0
        if self.cache is not None:
            cached = self.cache.get(fp, self.model_name)
            if cached is not None:
                # apply calibration if any
                if self.calibrator is not None:
                    try:
                        return float(self.calibrator.transform([cached])[0])
                    except Exception:
                        return cached
                return cached
        p = self._raw_predict(f)
        if self.cache is not None:
            self.cache.set(fp, self.model_name, p)
        if self.calibrator is not None:
            try:
                p = float(self.calibrator.transform([p])[0])
            except Exception:
                pass
        return p

    def on_bar_close(self, ts, hh, mn, bo, bh, bl, bc, hist):
        before = len(self.pending)
        super().on_bar_close(ts, hh, mn, bo, bh, bl, bc, hist)
        after = len(self.pending)
        if after <= before:
            return
        new_setups = self.pending[before:after]
        for s in new_setups:
            last = MARKET.last_px if MARKET.last_px is not None else bc
            bid = MARKET.last_bid if MARKET.last_bid is not None else last - 0.25
            ask = MARKET.last_ask if MARKET.last_ask is not None else last + 0.25
            setup_dir = 1 if s['side'] == 'LONG' else -1
            setup_dist = s['entry'] - last
            f = self.fe.extract(ts, bid, ask, hh, mn, setup_dir, setup_dist)
            if f is None:
                f = np.zeros(self.fe.N_FEATURES, dtype=np.float32)
            # Shared cache fingerprint: (ts, entry, side, base-spec-hash)
            # Make it stable across base strategies with same setup config.
            fp = (round(ts, 3), round(float(s['entry']), 2), s['side'])
            p = self._predict(fp, f) if self.model is not None else 1.0
            self._features_emitted.append(f)
            self._setups_emitted.append({
                'side': s['side'], 'entry': float(s['entry']),
                'stop': float(s['stop']), 'target': float(s.get('target') or 0.0),
                'ts': float(ts), 'pred': p,
            })
            if p < self.threshold:
                s['used'] = True
                self._n_filtered += 1
            else:
                self._n_emitted += 1


# =============================================================================
# PyTorch models
# =============================================================================
if TORCH_OK:
    class MLPNet(nn.Module):
        def __init__(self, in_dim=100, hidden=(128, 64, 32), dropout=0.3):
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

    class WideMLP(nn.Module):
        """Wider MLP with residual + batchnorm — for round 19."""
        def __init__(self, in_dim=100, hidden=(256, 128, 64), dropout=0.4):
            super().__init__()
            self.input = nn.Linear(in_dim, hidden[0])
            self.bn0 = nn.BatchNorm1d(hidden[0])
            self.l1 = nn.Linear(hidden[0], hidden[1])
            self.bn1 = nn.BatchNorm1d(hidden[1])
            self.l2 = nn.Linear(hidden[1], hidden[2])
            self.bn2 = nn.BatchNorm1d(hidden[2])
            self.head = nn.Linear(hidden[2], 1)
            self.drop = nn.Dropout(dropout)

        def forward(self, x):
            h = F.relu(self.bn0(self.input(x)))
            h = self.drop(h)
            h = F.relu(self.bn1(self.l1(h)))
            h = self.drop(h)
            h = F.relu(self.bn2(self.l2(h)))
            return self.head(h).squeeze(-1)


def train_torch_model(model, X_train, y_train, X_val, y_val,
                      epochs=30, batch_size=256, lr=1e-3,
                      pos_weight=None, model_name="model"):
    if not TORCH_OK:
        return None, 0.0, []
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
    n = X_train.shape[0]
    best_auc = -1.0
    best_state = None
    history = []
    patience = 5
    bad = 0

    for ep in range(epochs):
        model.train()
        idxs = np.random.permutation(n)
        total_loss = 0.0
        for i in range(0, n, batch_size):
            b = idxs[i:i + batch_size]
            if len(b) < 2:  # batchnorm needs >=2
                continue
            xb = Xt[b]; yb = yt[b]
            opt.zero_grad()
            out = model(xb)
            loss = loss_fn(out, yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            total_loss += float(loss.item()) * len(b)
        avg_loss = total_loss / max(1, n)
        model.eval()
        with torch.no_grad():
            v_out = model(Xv)
            v_prob = torch.sigmoid(v_out).cpu().numpy()
            try:
                v_auc = roc_auc_score(y_val, v_prob)
            except Exception:
                v_auc = 0.5
        history.append((ep, avg_loss, v_auc))
        improved = v_auc > best_auc
        if improved:
            best_auc = v_auc
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
            bad = 0
        else:
            bad += 1
        print(f"  [r19 {model_name}] ep{ep} loss={avg_loss:.4f} val_auc={v_auc:.4f}",
              file=sys.stderr)
        if bad >= patience:
            print(f"  [r19 {model_name}] early stop", file=sys.stderr)
            break
    if best_state is not None:
        model.load_state_dict(best_state)
    return model, best_auc, history


# =============================================================================
# Base specs (Phase 1 training donors and Phase 3 OOS gates)
# =============================================================================
# Phase 1: collect features from broad set
TRAIN_DONOR_SPECS = [
    # name, impulse, bars, pull_pct, stop, target
    ("CANON_236_s10t20", 5.0, 4, 0.236, 10, 20),  # round-18 winner
    ("CANON_236_s8t16",  5.0, 4, 0.236, 8, 16),
    ("CANON_382_s10t20", 5.0, 4, 0.382, 10, 20),
    ("IMP3_236_s8t16",   3.0, 4, 0.236, 8, 16),
    ("IMP3_118_s5t15",   3.0, 4, 0.118, 5, 15),
]

# Phase 3 Track 1: primary threshold sweep base
PRIMARY_BASE = ("CANON_236_s10t20", 5.0, 4, 0.236, 10, 20)

# Phase 3 Track 3: alternative bases for ML gating
ALT_BASES = [
    ("CANON_236_s8t16",  5.0, 4, 0.236, 8, 16),
    ("IMP3_236_s8t16",   3.0, 4, 0.236, 8, 16),
    ("IMP3_118_s5t15",   3.0, 4, 0.118, 5, 15),
]


def build_donor(name, fe, spec, model=None, model_name=None, model_kind=None,
                threshold=0.5, scaler=None, calibrator=None, cache=None,
                prefix="D"):
    _, imp, bars, pp, stp, tgt = spec
    return FDonor(
        f"{prefix}_{name}",
        fe=fe, model=model, model_name=model_name, model_kind=model_kind,
        threshold=threshold, scaler=scaler, calibrator=calibrator, cache=cache,
        impulse_pts=imp, impulse_bars=bars,
        pull_pct=pp, stop_pts=stp, target_pts=tgt,
        invert=True,
    )


# =============================================================================
# Run a tick-stream pass
# =============================================================================
def run_pass(strats, fe, start_offset, max_days, label=""):
    for s in strats:
        if not hasattr(s, '_exec') or s._exec is None:
            attach_r7_executor(s)
        else:
            attach_r7_executor(s)
    bb_1m = BarBuilder(granularity_secs=60, max_history=300)
    n_lines = 0
    t0 = time.time()
    day_counter = -1
    last_day_key = None
    last_progress = time.time()

    with open(TICK_PATH, "rb") as f:
        f.seek(start_offset)
        f.readline()
        for raw in f:
            n_lines += 1
            if n_lines % CHECKPOINT_EVERY_TICKS == 0:
                now = time.time()
                if now - last_progress > 30:
                    rate = n_lines / max(0.001, now - t0)
                    top = max((s.n_trades, s.name) for s in strats)
                    print(f"  [r19 {label}] {n_lines/1e6:.2f}M rate={rate:.0f}/s "
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

            for s in strats:
                r9.r9_bot_on_tick(s, ts, bid, ask, day_counter, hh, mn, last)

        end_offset = f.tell()

    elapsed = time.time() - t0
    print(f"[r19 {label}] PASS DONE: {n_lines:,} ticks, "
          f"{day_counter + 1} days, {elapsed/60:.1f}min, "
          f"rate={n_lines/max(1,elapsed):.0f}/s", file=sys.stderr)
    return end_offset, day_counter + 1, n_lines


# =============================================================================
# Build (X, y) from donor strategies' completed trades
# =============================================================================
def build_xy(donors):
    Xs = []; ys = []; metas = []
    for s in donors:
        if len(s._setups_emitted) == 0 or s.n_trades == 0:
            continue
        n = min(len(s._features_emitted), s.n_trades)
        for i in range(n):
            c = s.completed[i]
            pnl_pts = c[0]
            pnl_usd = pnl_pts * MNQ_PER_PT - FEE_FULL_RT
            y = 1 if pnl_usd > 0 else 0
            Xs.append(s._features_emitted[i])
            ys.append(y)
            metas.append({'strat': s.name, 'i': i,
                          'pnl_pts': float(pnl_pts), 'pnl_usd': float(pnl_usd),
                          'reason': c[1]})
    if not Xs:
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
        'name': strat.name, 'n': n,
        'tr_per_day': n / max(1, n_days),
        'wr': wins / n,
        'per_day': net / max(1, n_days),
        'per_trade': net / n,
        'dd': dd, 'sharpe': sharpe,
        'n_emit': getattr(strat, '_n_emitted', 0),
        'n_filt': getattr(strat, '_n_filtered', 0),
    }


# =============================================================================
# MAIN
# =============================================================================
def main():
    t_start = time.time()
    print(f"\n[r19] START {datetime.now().isoformat()}", file=sys.stderr)
    print(f"[r19] TORCH={TORCH_OK} SK={SK_OK} LGB={LGB_OK}", file=sys.stderr)

    fe_train = FeatureExtractor()

    # ============================================================================
    # PHASE 1: Training pass (days 0-44)
    # ============================================================================
    print(f"\n[r19] === PHASE 1: training pass ({TRAIN_DAYS}d) ===",
          file=sys.stderr)
    train_donors = []
    for nm, *spec_rest in TRAIN_DONOR_SPECS:
        s = build_donor(nm, fe_train,
                        (nm, *spec_rest), prefix="TR")
        train_donors.append(s)
    print(f"[r19] phase1 donors: {len(train_donors)}", file=sys.stderr)

    end_offset_train, days_train, lines_train = run_pass(
        train_donors, fe_train, OFFSET, TRAIN_DAYS, label="TRAIN")

    X, y, metas = build_xy(train_donors)
    if X is None or len(X) < 100:
        print(f"[r19] FATAL: not enough training data", file=sys.stderr)
        with open(RESULTS_PATH, "w") as f:
            f.write("# Round 19 — FAILED\n\nNot enough training data.\n")
        return

    print(f"[r19] training data: X={X.shape}, y={y.shape}, "
          f"pos_rate={y.mean():.3f}", file=sys.stderr)
    np.savez_compressed(FEATURES_PATH, X=X, y=y)
    print(f"[r19] features saved to {FEATURES_PATH}", file=sys.stderr)

    # Standardize
    scaler = StandardScaler()
    X_std = scaler.fit_transform(X)

    # Split: time-respecting — first 80% train, next 10% val, last 10% holdout
    n = len(X)
    n_train = int(n * 0.80)
    n_val = int(n * 0.10)
    X_train, y_train = X_std[:n_train], y[:n_train]
    X_val, y_val = X_std[n_train:n_train + n_val], y[n_train:n_train + n_val]
    X_holdout, y_holdout = X_std[n_train + n_val:], y[n_train + n_val:]
    pos_rate = y_train.mean()
    pos_weight = (1 - pos_rate) / max(pos_rate, 1e-6) if pos_rate > 0 else 1.0
    print(f"[r19] split: train={len(X_train)} val={len(X_val)} "
          f"holdout={len(X_holdout)} pos_rate={pos_rate:.3f} "
          f"pos_weight={pos_weight:.2f}", file=sys.stderr)

    # ============================================================================
    # PHASE 2: Train models
    # ============================================================================
    print(f"\n[r19] === PHASE 2: train models ===", file=sys.stderr)
    models = {}  # short_name -> (kind, model, val_auc)

    # PyTorch MLP (round 18 architecture for direct comparison)
    if TORCH_OK:
        try:
            mlp = MLPNet(in_dim=FeatureExtractor.N_FEATURES,
                         hidden=(128, 64, 32), dropout=0.3)
            mlp, mlp_auc, _ = train_torch_model(
                mlp, X_train, y_train, X_val, y_val,
                epochs=30, batch_size=256, lr=1e-3,
                pos_weight=pos_weight, model_name="MLP")
            models['MLP'] = ('mlp', mlp, mlp_auc)
            print(f"[r19] MLP val_auc={mlp_auc:.4f}", file=sys.stderr)
        except Exception as e:
            print(f"[r19] MLP train failed: {e}", file=sys.stderr)

        # WideMLP — round-19 deeper/wider variant
        try:
            wmlp = WideMLP(in_dim=FeatureExtractor.N_FEATURES,
                           hidden=(256, 128, 64), dropout=0.4)
            wmlp, wmlp_auc, _ = train_torch_model(
                wmlp, X_train, y_train, X_val, y_val,
                epochs=30, batch_size=256, lr=8e-4,
                pos_weight=pos_weight, model_name="WMLP")
            models['WMLP'] = ('mlp', wmlp, wmlp_auc)
            print(f"[r19] WMLP val_auc={wmlp_auc:.4f}", file=sys.stderr)
        except Exception as e:
            print(f"[r19] WMLP train failed: {e}", file=sys.stderr)

    # LightGBM
    if LGB_OK:
        try:
            t_lgb = time.time()
            print(f"[r19] training LGB (2000 trees, max_depth 8)...",
                  file=sys.stderr)
            lgb_train = lgb.Dataset(X_train, label=y_train)
            lgb_val = lgb.Dataset(X_val, label=y_val, reference=lgb_train)
            lgb_params = {
                'objective': 'binary', 'metric': 'auc',
                'max_depth': 8, 'num_leaves': 63,
                'learning_rate': 0.02, 'feature_fraction': 0.8,
                'bagging_fraction': 0.8, 'bagging_freq': 5,
                'lambda_l2': 0.1, 'verbose': -1,
                'is_unbalance': True,
            }
            lgb_model = lgb.train(
                lgb_params, lgb_train, num_boost_round=2000,
                valid_sets=[lgb_val],
                callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)])
            lgb_p = lgb_model.predict(X_val)
            try:
                lgb_auc = roc_auc_score(y_val, lgb_p)
            except Exception:
                lgb_auc = 0.5
            models['LGB'] = ('lgb', lgb_model, lgb_auc)
            print(f"[r19] LGB val_auc={lgb_auc:.4f} ({time.time()-t_lgb:.1f}s, "
                  f"{lgb_model.best_iteration} trees)", file=sys.stderr)
        except Exception as e:
            print(f"[r19] LGB train failed: {e}", file=sys.stderr)

    # sklearn GBM (medium-sized)
    if SK_OK:
        try:
            t_gbm = time.time()
            gbm = GradientBoostingClassifier(
                n_estimators=300, max_depth=5, learning_rate=0.05,
                subsample=0.8, random_state=42)
            gbm.fit(X_train, y_train)
            gbm_p = gbm.predict_proba(X_val)[:, 1]
            try:
                gbm_auc = roc_auc_score(y_val, gbm_p)
            except Exception:
                gbm_auc = 0.5
            models['GBM'] = ('gbm', gbm, gbm_auc)
            print(f"[r19] GBM val_auc={gbm_auc:.4f} ({time.time()-t_gbm:.1f}s)",
                  file=sys.stderr)
        except Exception as e:
            print(f"[r19] GBM train failed: {e}", file=sys.stderr)

    # === Probability calibration on holdout ===
    calibrators = {}
    if SK_OK:
        for nm, (kind, mdl, auc) in models.items():
            try:
                # Get raw probs on holdout
                if kind in ('mlp', 'transformer'):
                    with torch.no_grad():
                        Xh_t = torch.from_numpy(X_holdout.astype(np.float32))
                        out = mdl(Xh_t)
                        raw_p = torch.sigmoid(out).cpu().numpy()
                elif kind == 'lgb':
                    raw_p = mdl.predict(X_holdout)
                else:
                    raw_p = mdl.predict_proba(X_holdout)[:, 1]
                iso = IsotonicRegression(out_of_bounds='clip')
                iso.fit(raw_p, y_holdout)
                calibrators[nm] = iso
                # Calibrated AUC on holdout
                cal_p = iso.transform(raw_p)
                try:
                    ho_auc_raw = roc_auc_score(y_holdout, raw_p)
                    ho_auc_cal = roc_auc_score(y_holdout, cal_p)
                except Exception:
                    ho_auc_raw = ho_auc_cal = 0.5
                print(f"[r19] {nm} holdout AUC raw={ho_auc_raw:.4f} "
                      f"cal={ho_auc_cal:.4f}", file=sys.stderr)
            except Exception as e:
                print(f"[r19] {nm} calibration failed: {e}", file=sys.stderr)

    # === Build ensemble (only if multiple models present) ===
    ens_members = []
    for nm, (kind, mdl, auc) in models.items():
        if nm in ('MLP', 'WMLP', 'LGB') and auc > 0.5:
            ens_members.append((mdl, kind, scaler))
    if len(ens_members) >= 2:
        models['ENS'] = ('ensemble', ens_members, 0.0)

    # Save models for later inspection
    try:
        save = {}
        for nm, (kind, mdl, auc) in models.items():
            if kind == 'ensemble':
                continue  # skip ensemble (already in members)
            if kind in ('mlp', 'transformer'):
                save[nm] = {'kind': kind, 'state_dict': mdl.state_dict(),
                            'auc': auc}
            else:
                save[nm] = {'kind': kind, 'model': mdl, 'auc': auc}
        save['scaler'] = scaler
        save['calibrators'] = calibrators
        with open(MODELS_PATH, "wb") as f:
            pickle.dump(save, f)
        print(f"[r19] models saved to {MODELS_PATH}", file=sys.stderr)
    except Exception as e:
        print(f"[r19] model save failed: {e}", file=sys.stderr)

    # ============================================================================
    # PHASE 3: OOS pass (days 45-59)
    # ============================================================================
    print(f"\n[r19] === PHASE 3: OOS pass ({TEST_DAYS}d) ===", file=sys.stderr)

    fe_oos = FeatureExtractor()
    cache = PredictionCache()

    # Build all OOS strategies
    oos_strats = []

    # Baseline (no gate) — reference for all 4 bases
    baseline_bases = [PRIMARY_BASE] + ALT_BASES
    for spec in baseline_bases:
        nm = spec[0]
        s = build_donor(nm, fe_oos, spec, prefix=f"BL")
        oos_strats.append(s)

    # === TRACK 1: PRIMARY_BASE × MLP × 41 thresholds (0.40-0.60 step 0.005) ===
    track1_thresholds = [round(0.40 + 0.005 * i, 4) for i in range(41)]
    track1_strats = []
    if 'MLP' in models:
        _, mlp_mdl, _ = models['MLP']
        for thr in track1_thresholds:
            s = build_donor(
                PRIMARY_BASE[0], fe_oos, PRIMARY_BASE,
                model=mlp_mdl, model_name='MLP', model_kind='mlp',
                threshold=thr, scaler=scaler, calibrator=None, cache=cache,
                prefix=f"T1_MLP_t{int(thr*1000):03d}")
            track1_strats.append(s)
    oos_strats.extend(track1_strats)

    # === TRACK 2: PRIMARY_BASE × {WMLP, LGB, ENS} × 9 thresholds ===
    track2_thresholds = [0.40, 0.45, 0.48, 0.50, 0.52, 0.55, 0.58, 0.60, 0.65]
    track2_strats = []
    for mname in ('WMLP', 'LGB', 'ENS'):
        if mname not in models:
            continue
        kind, mdl, _ = models[mname]
        for thr in track2_thresholds:
            s = build_donor(
                PRIMARY_BASE[0], fe_oos, PRIMARY_BASE,
                model=mdl, model_name=mname, model_kind=kind,
                threshold=thr, scaler=scaler, calibrator=None, cache=cache,
                prefix=f"T2_{mname}_t{int(thr*1000):03d}")
            track2_strats.append(s)
    oos_strats.extend(track2_strats)

    # === TRACK 3: 3 alternative bases × MLP × 5 thresholds ===
    track3_thresholds = [0.45, 0.50, 0.52, 0.55, 0.60]
    track3_strats = []
    if 'MLP' in models:
        _, mlp_mdl, _ = models['MLP']
        for spec in ALT_BASES:
            nm = spec[0]
            for thr in track3_thresholds:
                s = build_donor(
                    nm, fe_oos, spec,
                    model=mlp_mdl, model_name='MLP', model_kind='mlp',
                    threshold=thr, scaler=scaler, calibrator=None, cache=cache,
                    prefix=f"T3_{nm}_MLP_t{int(thr*1000):03d}")
                track3_strats.append(s)
    oos_strats.extend(track3_strats)

    # === TRACK 4: Calibrated MLP, sweep 5 calibrated thresholds ===
    track4_thresholds = [0.30, 0.35, 0.40, 0.45, 0.50]  # calibrated probs run lower
    track4_strats = []
    if 'MLP' in models and 'MLP' in calibrators:
        _, mlp_mdl, _ = models['MLP']
        cal = calibrators['MLP']
        for thr in track4_thresholds:
            s = build_donor(
                PRIMARY_BASE[0], fe_oos, PRIMARY_BASE,
                model=mlp_mdl, model_name='MLP_CAL', model_kind='mlp',
                threshold=thr, scaler=scaler, calibrator=cal, cache=cache,
                prefix=f"T4_MLPcal_t{int(thr*1000):03d}")
            track4_strats.append(s)
    oos_strats.extend(track4_strats)

    print(f"[r19] phase3 strategies: BL={len(baseline_bases)} "
          f"T1={len(track1_strats)} T2={len(track2_strats)} "
          f"T3={len(track3_strats)} T4={len(track4_strats)} "
          f"TOTAL={len(oos_strats)}", file=sys.stderr)

    _, days_oos, _ = run_pass(oos_strats, fe_oos, end_offset_train, TEST_DAYS,
                              label="OOS")

    # ============================================================================
    # REPORTING
    # ============================================================================
    print(f"\n[r19] === REPORT ===", file=sys.stderr)

    train_rows = [report_strategy(s, days_train) for s in train_donors]
    bl_rows = [report_strategy(s, days_oos) for s in oos_strats
               if s.name.startswith("BL_")]
    t1_rows = [report_strategy(s, days_oos) for s in oos_strats
               if s.name.startswith("T1_")]
    t2_rows = [report_strategy(s, days_oos) for s in oos_strats
               if s.name.startswith("T2_")]
    t3_rows = [report_strategy(s, days_oos) for s in oos_strats
               if s.name.startswith("T3_")]
    t4_rows = [report_strategy(s, days_oos) for s in oos_strats
               if s.name.startswith("T4_")]

    all_oos_rows = bl_rows + t1_rows + t2_rows + t3_rows + t4_rows

    def is_full_pass(r):
        return (r['tr_per_day'] >= 300 and r['wr'] >= 0.45
                and r['per_day'] >= 1000 and r['dd'] <= 5000)
    full_pass_oos = [r for r in all_oos_rows if is_full_pass(r)]

    def is_relaxed(r):
        # Relaxed user bar: 100+ tr/d, 45% WR, $500+/day, $5K DD
        return (r['tr_per_day'] >= 100 and r['wr'] >= 0.45
                and r['per_day'] >= 500 and r['dd'] <= 5000)
    relaxed_pass = [r for r in all_oos_rows if is_relaxed(r)]

    # CSV dump
    with open(CSV_PATH, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["phase", "name", "n", "tr_per_day", "wr", "per_day",
                    "per_trade", "dd", "sharpe", "n_emit", "n_filt"])
        for row, phase in [(train_rows, "PHASE1_TRAIN"),
                           (bl_rows, "BASELINE"),
                           (t1_rows, "TRACK1_THR_SWEEP"),
                           (t2_rows, "TRACK2_MODELS"),
                           (t3_rows, "TRACK3_ALT_BASES"),
                           (t4_rows, "TRACK4_CALIBRATED")]:
            for r in row:
                w.writerow([phase, r['name'], r['n'],
                            f"{r['tr_per_day']:.2f}", f"{r['wr']:.4f}",
                            f"{r['per_day']:.2f}", f"{r['per_trade']:.3f}",
                            f"{r['dd']:.2f}", f"{r['sharpe']:.3f}",
                            r['n_emit'], r['n_filt']])
    print(f"[r19] csv saved {CSV_PATH}", file=sys.stderr)

    # Markdown
    L = []
    L.append("# Round 19 — ML threshold sweet-spot search\n\n")
    L.append(f"Generated: {datetime.now().isoformat()}\n")
    L.append(f"Elapsed: {(time.time()-t_start)/60:.1f} min\n")
    L.append(f"Execution: r9_bot_on_tick AS-IS. No fill patching.\n\n")
    L.append(f"PyTorch: {TORCH_OK} | sklearn: {SK_OK} | LightGBM: {LGB_OK}\n\n")

    L.append(f"## Phase 1 training data ({days_train}d)\n\n")
    L.append(f"- Total emitted setups -> features: {len(X)}\n")
    L.append(f"- Positive (win) rate: {y.mean():.3f}\n")
    L.append(f"- Train/Val/Holdout: {len(X_train)}/{len(X_val)}/{len(X_holdout)}\n")
    L.append(f"- Feature dimensionality: {FeatureExtractor.N_FEATURES} "
             f"({FeatureExtractor.N_BASE} base + {FeatureExtractor.N_NEW} new)\n\n")

    L.append("## Model validation AUCs\n\n| Model | Val AUC |\n|---|---:|\n")
    for nm, (k, m, auc) in sorted(models.items(),
                                  key=lambda kv: -kv[1][2] if kv[1][0] != 'ensemble' else 0):
        if k == 'ensemble':
            L.append(f"| {nm} ({k}) | (averaged) |\n")
        else:
            L.append(f"| {nm} ({k}) | {auc:.4f} |\n")

    # Phase 1 baseline
    L.append(f"\n## Phase 1 baseline donor in-sample ({days_train}d)\n\n")
    L.append("| Strategy | Trades | Tr/d | WR% | $/day | $/trade | DD | Sharpe |\n")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|\n")
    for r in sorted(train_rows, key=lambda r: -r['per_day']):
        L.append(f"| {r['name']} | {r['n']:,} | {r['tr_per_day']:.1f} | "
                 f"{r['wr']*100:.1f} | ${r['per_day']:+.2f} | "
                 f"${r['per_trade']:+.2f} | ${r['dd']:.0f} | "
                 f"{r['sharpe']:.2f} |\n")

    # OOS baseline
    L.append(f"\n## Phase 3 OOS BASELINE ({days_oos}d)\n\n")
    L.append("| Strategy | Trades | Tr/d | WR% | $/day | $/trade | DD | Sharpe |\n")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|\n")
    for r in sorted(bl_rows, key=lambda r: -r['per_day']):
        L.append(f"| {r['name']} | {r['n']:,} | {r['tr_per_day']:.1f} | "
                 f"{r['wr']*100:.1f} | ${r['per_day']:+.2f} | "
                 f"${r['per_trade']:+.2f} | ${r['dd']:.0f} | "
                 f"{r['sharpe']:.2f} |\n")

    # Track 1: threshold sweep
    L.append(f"\n## TRACK 1 — MLP threshold sweep on CANON_236_s10t20 ({days_oos}d OOS)\n\n")
    L.append("Sweep 0.400 - 0.600 in 0.005 increments.\n\n")
    L.append("| Threshold | Trades | Tr/d | WR% | $/day | $/trade | DD | n_filt | n_emit |\n")
    L.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for r in sorted(t1_rows, key=lambda r: r['name']):
        # extract threshold from name: T1_MLP_t<NNN>_<base>
        try:
            thr_tag = r['name'].split('_t')[1].split('_')[0]
            thr = int(thr_tag) / 1000.0
        except Exception:
            thr = 0.0
        L.append(f"| {thr:.3f} | {r['n']:,} | {r['tr_per_day']:.1f} | "
                 f"{r['wr']*100:.1f} | ${r['per_day']:+.2f} | "
                 f"${r['per_trade']:+.2f} | ${r['dd']:.0f} | "
                 f"{r['n_filt']:,} | {r['n_emit']:,} |\n")

    # Track 1 sweet-spot search
    L.append(f"\n### TRACK 1 sweet-spot\n\n")
    sweet_spot_candidates = [
        r for r in t1_rows
        if r['tr_per_day'] >= 5.0 and r['wr'] >= 0.40
    ]
    if sweet_spot_candidates:
        # Best per_day among candidates with vol>=100, WR>=45
        strict = [r for r in t1_rows
                  if r['tr_per_day'] >= 100 and r['wr'] >= 0.45]
        if strict:
            best_strict = max(strict, key=lambda r: r['per_day'])
            L.append(f"- **STRICT sweet spot (>=100tr/d & >=45% WR):** "
                     f"{best_strict['name']} ${best_strict['per_day']:+.2f}/d "
                     f"@ {best_strict['wr']*100:.1f}% WR, "
                     f"{best_strict['tr_per_day']:.1f} tr/d\n")
        else:
            L.append("- STRICT sweet spot (>=100tr/d & >=45% WR): NONE\n")
        # Best per_day overall in T1
        best_pd = max(t1_rows, key=lambda r: r['per_day'])
        L.append(f"- **Best $/day in TRACK 1:** {best_pd['name']} "
                 f"${best_pd['per_day']:+.2f}/d @ {best_pd['wr']*100:.1f}% WR, "
                 f"{best_pd['tr_per_day']:.1f} tr/d\n")
        # Best WR (with >= 10 trades)
        wr_cand = [r for r in t1_rows if r['n'] >= 10]
        if wr_cand:
            best_wr = max(wr_cand, key=lambda r: r['wr'])
            L.append(f"- **Best WR (n>=10):** {best_wr['name']} "
                     f"{best_wr['wr']*100:.1f}% WR, "
                     f"${best_wr['per_day']:+.2f}/d, "
                     f"{best_wr['tr_per_day']:.1f} tr/d\n")
    else:
        L.append("- No viable sweet-spot candidates with WR>=40 & tr/d>=5.\n")

    # Track 2: alternative models
    L.append(f"\n## TRACK 2 — Alternative models on CANON_236_s10t20\n\n")
    L.append("| Strategy | Trades | Tr/d | WR% | $/day | $/trade | DD | n_filt | n_emit |\n")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for r in sorted(t2_rows, key=lambda r: -r['per_day']):
        L.append(f"| {r['name']} | {r['n']:,} | {r['tr_per_day']:.1f} | "
                 f"{r['wr']*100:.1f} | ${r['per_day']:+.2f} | "
                 f"${r['per_trade']:+.2f} | ${r['dd']:.0f} | "
                 f"{r['n_filt']:,} | {r['n_emit']:,} |\n")

    # Track 3: alt bases
    L.append(f"\n## TRACK 3 — MLP on alternative bases\n\n")
    L.append("| Strategy | Trades | Tr/d | WR% | $/day | $/trade | DD | n_filt | n_emit |\n")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for r in sorted(t3_rows, key=lambda r: -r['per_day']):
        L.append(f"| {r['name']} | {r['n']:,} | {r['tr_per_day']:.1f} | "
                 f"{r['wr']*100:.1f} | ${r['per_day']:+.2f} | "
                 f"${r['per_trade']:+.2f} | ${r['dd']:.0f} | "
                 f"{r['n_filt']:,} | {r['n_emit']:,} |\n")

    # Track 4: calibrated
    L.append(f"\n## TRACK 4 — Probability-calibrated MLP\n\n")
    L.append("| Strategy | Trades | Tr/d | WR% | $/day | $/trade | DD | n_filt | n_emit |\n")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for r in sorted(t4_rows, key=lambda r: -r['per_day']):
        L.append(f"| {r['name']} | {r['n']:,} | {r['tr_per_day']:.1f} | "
                 f"{r['wr']*100:.1f} | ${r['per_day']:+.2f} | "
                 f"${r['per_trade']:+.2f} | ${r['dd']:.0f} | "
                 f"{r['n_filt']:,} | {r['n_emit']:,} |\n")

    # Best (model x threshold x base)
    L.append("\n## Best (model x threshold x base) overall\n\n")
    all_gated = t1_rows + t2_rows + t3_rows + t4_rows
    if all_gated:
        # Best by $/day with non-trivial vol
        vol_cand = [r for r in all_gated if r['n'] >= 20]
        if vol_cand:
            best_pd = max(vol_cand, key=lambda r: r['per_day'])
            L.append(f"- **Best $/day (n>=20):** {best_pd['name']} "
                     f"${best_pd['per_day']:+.2f}/d @ "
                     f"{best_pd['wr']*100:.1f}% WR, "
                     f"{best_pd['tr_per_day']:.1f} tr/d, DD ${best_pd['dd']:.0f}\n")
        # Best by WR
        wr_cand = [r for r in all_gated if r['n'] >= 30]
        if wr_cand:
            best_wr = max(wr_cand, key=lambda r: r['wr'])
            L.append(f"- **Best WR (n>=30):** {best_wr['name']} "
                     f"{best_wr['wr']*100:.1f}% WR, "
                     f"${best_wr['per_day']:+.2f}/d, "
                     f"{best_wr['tr_per_day']:.1f} tr/d\n")
        # Best edge per trade
        ept = [r for r in all_gated if r['n'] >= 50]
        if ept:
            best_ept = max(ept, key=lambda r: r['per_trade'])
            L.append(f"- **Best $/trade (n>=50):** {best_ept['name']} "
                     f"${best_ept['per_trade']:+.2f}/trade, "
                     f"{best_ept['n']:,} trades\n")
        # Best Sharpe
        sh_cand = [r for r in all_gated if r['n'] >= 30]
        if sh_cand:
            best_sh = max(sh_cand, key=lambda r: r['sharpe'])
            L.append(f"- **Best Sharpe (n>=30):** {best_sh['name']} "
                     f"Sharpe {best_sh['sharpe']:.2f}, "
                     f"${best_sh['per_day']:+.2f}/d, "
                     f"{best_sh['tr_per_day']:.1f} tr/d\n")

    # FULL_PASS
    L.append(f"\n## FULL_PASS (>=300 tr/d, >=45% WR, >=$1k/day, DD<=$5k)\n\n")
    if full_pass_oos:
        for r in full_pass_oos:
            L.append(f"- **{r['name']}** ${r['per_day']:+.2f}/d, "
                     f"{r['tr_per_day']:.1f} tr/d, {r['wr']*100:.1f}% WR\n")
    else:
        L.append("**NONE.**\n")

    L.append(f"\n## RELAXED pass (>=100 tr/d, >=45% WR, >=$500/d, DD<=$5k)\n\n")
    if relaxed_pass:
        for r in relaxed_pass:
            L.append(f"- **{r['name']}** ${r['per_day']:+.2f}/d, "
                     f"{r['tr_per_day']:.1f} tr/d, {r['wr']*100:.1f}% WR\n")
    else:
        L.append("**NONE.**\n")

    # Lift analysis
    L.append("\n## Lift analysis vs baseline\n\n")
    if bl_rows and all_gated:
        # Match by base — find primary base baseline
        primary_bl = [r for r in bl_rows if PRIMARY_BASE[0] in r['name']]
        if primary_bl:
            bl_primary = primary_bl[0]
            L.append(f"- Baseline ({bl_primary['name']}): "
                     f"${bl_primary['per_day']:+.2f}/d @ "
                     f"{bl_primary['wr']*100:.1f}% WR, "
                     f"{bl_primary['tr_per_day']:.1f} tr/d\n")
            best_gated = max(all_gated, key=lambda r: r['per_day'])
            lift = best_gated['per_day'] - bl_primary['per_day']
            L.append(f"- Best gated: {best_gated['name']} "
                     f"${best_gated['per_day']:+.2f}/d @ "
                     f"{best_gated['wr']*100:.1f}% WR, "
                     f"{best_gated['tr_per_day']:.1f} tr/d\n")
            L.append(f"- **ML lift: ${lift:+.2f}/day** "
                     f"(WR delta: {(best_gated['wr'] - bl_primary['wr'])*100:+.1f}pp)\n")

    # Round 20 recommendations
    L.append("\n## Honest assessment & Round 20 recommendations\n\n")
    if full_pass_oos:
        L.append("- ML gating produced FULL_PASS strategies under r9 execution.\n")
        L.append("- Recommend independent re-validation on a fresh window before live deploy.\n")
    elif relaxed_pass:
        L.append("- No FULL_PASS but RELAXED candidates exist.\n")
        L.append("- Round 20 should re-validate top relaxed pass on a different time window.\n")
    else:
        # Did the threshold sweep show any monotonic WR/$ improvement?
        if t1_rows:
            sweep_sorted = sorted(t1_rows,
                                  key=lambda r: float(r['name'].split('_t')[1].split('_')[0]))
            # WR at the top quantile vs bottom
            valid = [r for r in sweep_sorted if r['n'] >= 10]
            if len(valid) >= 5:
                low_wr = sum(r['wr'] for r in valid[:5]) / 5
                hi_wr = sum(r['wr'] for r in valid[-5:]) / 5
                L.append(f"- Threshold sweep: low-threshold avg WR={low_wr*100:.1f}% "
                         f"vs high-threshold avg WR={hi_wr*100:.1f}% "
                         f"(lift = {(hi_wr - low_wr)*100:+.1f} pp).\n")
                if hi_wr > low_wr + 0.03:
                    L.append("- ML signal IS present at top quantiles but VOLUME COLLAPSES.\n")
                    L.append("- Round 20 directions: (1) train on richer label "
                             "(continuous PnL not binary win/loss); (2) try meta-labeling "
                             "(primary signal + secondary ML on holding-period outcomes); "
                             "(3) explore harder structural features (orderbook depth, "
                             "OFI). The pure-feature MLP architecture has plateaued.\n")
                else:
                    L.append("- ML signal does NOT survive in this OOS window. "
                             "Round 18 result may have been window-specific.\n")
        L.append(f"- The $1k/day target at 1 MNQ + $1.91 fees requires a "
                 f"per-trade edge that has not been demonstrated. "
                 f"Paper-trading at the best candidate, or rejecting the goal, "
                 f"remains the rational path.\n")
        if bl_rows and all_gated:
            best_overall = max(all_gated + bl_rows, key=lambda r: r['per_day'])
            L.append(f"- Best OOS overall: **{best_overall['name']}** "
                     f"${best_overall['per_day']:+.2f}/d @ "
                     f"{best_overall['wr']*100:.1f}% WR, "
                     f"{best_overall['tr_per_day']:.1f} tr/d.\n")

    L.append("\n## Notes\n\n")
    L.append("- Feature->label alignment: features for first N emitted setups "
             "aligned to first N completed trades. r9 executor fires in "
             "setup-emission order, so this is approximate (unfilled setups "
             "introduce noise). Labels are nonetheless reliable enough for "
             "ranking by p>=threshold.\n")
    L.append("- Probability cache: setups with same (ts, entry, side) fingerprint "
             "share the same model prediction across all strategies. This avoids "
             "computational blow-up when sweeping many thresholds.\n")
    L.append("- All OOS metrics produced by r9_bot_on_tick verbatim, with ML "
             "gate operating only by marking `s['used']=True` BEFORE the "
             "executor attempts fill. No fill logic is changed.\n")
    L.append("- Probability calibration uses isotonic regression on the "
             "model's holdout split. Calibrated thresholds map directly to "
             "P(win) so a 0.50 threshold means 'predicted >50% win prob'.\n")

    with open(RESULTS_PATH, "w") as f:
        f.write("".join(L))
    print(f"[r19] wrote {RESULTS_PATH}", file=sys.stderr)

    # Console summary
    print("\n" + "=" * 80)
    print(f"ROUND 19 SUMMARY")
    print(f"Total elapsed: {(time.time()-t_start)/60:.1f}min")
    print(f"FULL_PASS strategies: {len(full_pass_oos)}")
    print(f"RELAXED_PASS strategies: {len(relaxed_pass)}")
    if bl_rows:
        bl = max(bl_rows, key=lambda r: r['per_day'])
        print(f"Best baseline: {bl['name']} ${bl['per_day']:+.2f}/d")
    if all_gated:
        bg = max(all_gated, key=lambda r: r['per_day'])
        print(f"Best gated:    {bg['name']} ${bg['per_day']:+.2f}/d "
              f"@ {bg['wr']*100:.1f}% WR, {bg['tr_per_day']:.1f} tr/d")
    print("=" * 80)

    try:
        if os.path.exists(CKPT_PATH):
            os.remove(CKPT_PATH)
    except Exception:
        pass


if __name__ == "__main__":
    main()
