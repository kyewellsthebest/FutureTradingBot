"""
Auto-generated v3 pattern Signal classes.
Generated: 2026-04-28T23:01:43.905042+00:00
Survivors: 10  
Validation: 5-test rigor gauntlet (CPCV + permutation + MC + sensitivity + EV).
"""
from __future__ import annotations
import pandas as pd

from research.pattern_miner_v3 import build_v3_features


class V3ShortS15T30_01:
    name = 'V3_SHORT_S15T30_05'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.6034231609613984
    profit_factor = 2.393224440411373
    tier = 'A'
    constraints = [
        ('atr_14', '>', 5.143145322799683),
        ('dist_pdl_atr', '>', 3.7716599702835083),
        ('dist_pdh_atr', '>', -2.655640721321106),
        ('dist_pdh_atr', '>', -1.8196828365325928),
        ('dist_pdh_atr', '>', -1.175345242023468),
        ('atr_14', '>', 6.079609632492065),
        ('atr_14', '<=', 17.479268074035645),
        ('ny_minute', '<=', 50.5),
        ('atr_14', '>', 8.823062896728516),
        ('dist_pdh_atr', '>', -0.9380735754966736),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS8T16_02:
    name = 'V3_LONG_S8T16_02'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 8.0
    max_hold_bars = 25
    win_rate = 0.48913896885632036
    profit_factor = 1.2215575954989635
    tier = 'B'
    constraints = [
        ('atr_14', '>', 3.795033812522888),
        ('dist_pdh_atr', '<=', -3.2557623386383057),
        ('atr_14', '>', 5.031558275222778),
        ('dist_pdl_atr', '<=', 1.9920040369033813),
        ('dist_pdl_atr', '>', 0.9122057557106018),
        ('dist_low20_atr', '>', 0.9124655723571777),
        ('atr_5', '<=', 16.067728996276855),
        ('dist_pdl_atr', '>', 1.2276766300201416),
        ('dist_low20_atr', '>', 1.2331452369689941),
        ('ret_20', '>', -33.875),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
            v = feats[col]
            if op == '<=':
                mask &= (v <= thr)
            else:
                mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        c = intraday['close'].loc[idx]
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3ShortS8T16_03:
    name = 'V3_SHORT_S8T16_01'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 8.0
    max_hold_bars = 25
    win_rate = 0.4766209476309227
    profit_factor = 1.1326910289602874
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.043004274368286),
        ('dist_pdl_atr', '>', 2.4498130083084106),
        ('dist_pdh_atr', '>', -2.9448471069335938),
        ('dist_pdh_atr', '<=', -1.4767688512802124),
        ('range_pos_200', '<=', 0.9378756284713745),
        ('atr_5', '<=', 13.373907089233398),
        ('range_pos_50', '<=', 0.8449806272983551),
        ('atr_50', '>', 3.855209231376648),
        ('dist_pdh_atr', '>', -2.206063389778137),
        ('atr_5', '<=', 7.345613241195679),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS10T20_04:
    name = 'V3_SHORT_S10T20_02'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    win_rate = 0.4862932061978546
    profit_factor = 1.2510523525926849
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('dist_pdl_atr', '>', 2.8014075756073),
        ('dist_pdh_atr', '>', -2.9352803230285645),
        ('dist_pdh_atr', '<=', -1.4767688512802124),
        ('range_pos_50', '<=', 0.8868695795536041),
        ('dist_pdh_atr', '>', -2.2107986211776733),
        ('atr_5', '<=', 14.28479528427124),
        ('dist_pdh_atr', '<=', -1.8261911273002625),
        ('range_pos_50', '<=', 0.8292435705661774),
        ('autocorr_5', '>', -0.18456797301769257),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS10T20_05:
    name = 'V3_SHORT_S10T20_03'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    win_rate = 0.4996651038178165
    profit_factor = 1.3881866540264391
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('dist_pdl_atr', '>', 2.8014075756073),
        ('dist_pdh_atr', '>', -2.9352803230285645),
        ('dist_pdh_atr', '<=', -1.4767688512802124),
        ('range_pos_50', '<=', 0.8868695795536041),
        ('dist_pdh_atr', '<=', -2.2107986211776733),
        ('range_pos_50', '<=', 0.8043951690196991),
        ('atr_14', '<=', 15.266812324523926),
        ('ny_hour', '<=', 14.5),
        ('autocorr_5', '<=', -0.13595503568649292),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS12T24_06:
    name = 'V3_LONG_S12T24_03'
    side = 'LONG'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    win_rate = 0.5917220235053654
    profit_factor = 2.0840714672441796
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.391809940338135),
        ('dist_pdh_atr', '<=', -3.944929838180542),
        ('atr_14', '>', 5.619614839553833),
        ('dist_pdl_atr', '<=', 2.1953364610671997),
        ('dist_pdl_atr', '>', 1.0952328443527222),
        ('dist_low20_atr', '>', 1.0945197343826294),
        ('atr_5', '<=', 16.38709545135498),
        ('dist_pdl_atr', '>', 1.6970905661582947),
        ('dist_low20_atr', '>', 1.6281297206878662),
        ('range_pos_50', '>', 0.18204688280820847),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
            v = feats[col]
            if op == '<=':
                mask &= (v <= thr)
            else:
                mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        c = intraday['close'].loc[idx]
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3ShortS12T24_07:
    name = 'V3_SHORT_S12T24_04'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    win_rate = 0.4865697930427125
    profit_factor = 1.3733360638951464
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.707773685455322),
        ('dist_pdl_atr', '>', 3.4693500995635986),
        ('dist_pdh_atr', '>', -2.665213942527771),
        ('dist_pdh_atr', '<=', -1.4006109833717346),
        ('range_pos_50', '<=', 0.8919178545475006),
        ('dist_pdh_atr', '<=', -2.018115758895874),
        ('range_pos_50', '<=', 0.8086031675338745),
        ('autocorr_5', '>', -0.19805394113063812),
        ('atr_50', '>', 7.132232904434204),
        ('atr_50', '<=', 12.728631973266602),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS15T30_08:
    name = 'V3_LONG_S15T30_04'
    side = 'LONG'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.9668552950687146
    profit_factor = 46.730352303523034
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.312023639678955),
        ('dist_pdh_atr', '<=', -4.292487859725952),
        ('dist_pdl_atr', '<=', 2.841599225997925),
        ('dist_pdl_atr', '<=', 1.673180103302002),
        ('dist_pdl_atr', '<=', 1.1024043560028076),
        ('atr_14', '>', 7.1410441398620605),
        ('atr_14', '<=', 19.068782806396484),
        ('ny_hour', '<=', 14.5),
        ('dist_pdl_atr', '<=', 0.9135347604751587),
        ('atr_5', '>', 9.619722366333008),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
            v = feats[col]
            if op == '<=':
                mask &= (v <= thr)
            else:
                mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        c = intraday['close'].loc[idx]
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3ShortS15T30_09:
    name = 'V3_SHORT_S15T30_07'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.5177584846093133
    profit_factor = 1.709456383172464
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.143145322799683),
        ('dist_pdl_atr', '>', 3.7716599702835083),
        ('dist_pdh_atr', '<=', -2.655640721321106),
        ('dist_vwap_atr', '<=', 0.3556029945611954),
        ('dist_pdl_atr', '>', 7.351938962936401),
        ('range_pos_200', '>', 0.2944239675998688),
        ('atr_14', '>', 7.192625045776367),
        ('dist_pdl_atr', '>', 13.259193897247314),
        ('dist_vwap_atr', '<=', -0.6826021075248718),
        ('dist_pdh_atr', '>', -5.9243292808532715),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS15T30_10:
    name = 'V3_SHORT_S15T30_08'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.5256495669553631
    profit_factor = 1.6841117253898836
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.143145322799683),
        ('dist_pdl_atr', '>', 3.7716599702835083),
        ('dist_pdh_atr', '>', -2.655640721321106),
        ('dist_pdh_atr', '<=', -1.8196828365325928),
        ('range_pos_50', '<=', 0.8748017847537994),
        ('atr_50', '>', 6.930222988128662),
        ('atr_14', '<=', 15.637444019317627),
        ('dist_pdh_atr', '<=', -2.200629472732544),
        ('range_pos_50', '<=', 0.807697206735611),
        ('ema_slope_20', '<=', 1.0278392434120178),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

ALL_V3_SIGNALS = [
    V3ShortS15T30_01(),
    V3LongS8T16_02(),
    V3ShortS8T16_03(),
    V3ShortS10T20_04(),
    V3ShortS10T20_05(),
    V3LongS12T24_06(),
    V3ShortS12T24_07(),
    V3LongS15T30_08(),
    V3ShortS15T30_09(),
    V3ShortS15T30_10(),
]