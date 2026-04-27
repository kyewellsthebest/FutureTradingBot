"""
Auto-generated v4 pattern Signal classes — NEW patterns
(no PDH/PDL anchor; novel feature set).
Generated: 2026-04-27T21:51:29.579844+00:00
Survivors: 2  (LONG=0, SHORT=2)
"""
from __future__ import annotations
import pandas as pd


class V4ShortS12T24_01:
    name = 'V4_SHORT_S12T24_01'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    cpcv_mean_wr = 0.5876184730283041
    constraints = [
        ('atr_14', '<=', 9.322625160217285),
        ('atr_14', '>', 3.4005573987960815),
        ('bars_into_session', '>', 141.5),
        ('atr_14', '>', 6.0590980052948),
        ('dist_vwap_atr', '<=', 21.640140533447266),
        ('bars_into_session', '>', 322.5),
        ('atr_14', '<=', 7.798141956329346),
        ('dist_vwap_atr', '>', 6.975290298461914),
        ('dow', '<=', 3.5),
        ('bars_into_session', '>', 348.5),
        ('atr_50', '>', 6.758034706115723),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner_v4 import build_v4_features
        feats = build_v4_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            v = feats[col]
            if op == '<=':
                mask &= (v <= thr)
            else:
                mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        c = intraday['close'].loc[idx]
        sign = 1 if 'SHORT' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V4ShortS12T24_02:
    name = 'V4_SHORT_S12T24_02'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    cpcv_mean_wr = 0.5205543241180214
    constraints = [
        ('atr_14', '>', 9.322625160217285),
        ('dist_vwap_atr', '<=', 9.720065593719482),
        ('ema_distance_5_20', '>', 0.057578735053539276),
        ('dist_vwap_atr', '<=', 6.271219968795776),
        ('vol_drought_10', '>', 0.5168278217315674),
        ('vol_burst_3', '<=', 1.9380950331687927),
        ('ny_minute', '>', 7.5),
        ('bars_into_session', '<=', 198.5),
        ('atr_50', '<=', 10.447432518005371),
        ('ema_distance_20_50', '<=', 0.9775358140468597),
        ('lower_wick_pct', '>', 0.17262665182352066),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner_v4 import build_v4_features
        feats = build_v4_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            v = feats[col]
            if op == '<=':
                mask &= (v <= thr)
            else:
                mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        c = intraday['close'].loc[idx]
        sign = 1 if 'SHORT' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

ALL_V4_SIGNALS = [
    V4ShortS12T24_01(),
    V4ShortS12T24_02(),
]