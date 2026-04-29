"""
Auto-generated v3 pattern Signal classes.
Generated: 2026-04-29T00:07:10.263223+00:00
Survivors: 43  
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

class V3LongS20T50_02:
    name = 'V3_LONG_S20T50_55'
    side = 'LONG'
    target_pts = 50.0
    stop_pts = 20.0
    max_hold_bars = 100
    win_rate = 0.6077384923282189
    profit_factor = 2.8283065732280672
    tier = 'A'
    constraints = [
        ('atr_14', '>', 5.422818660736084),
        ('dist_pdh_atr', '<=', -6.012660264968872),
        ('dist_pdl_atr', '>', 2.6566004753112793),
        ('dist_vwap_atr', '>', -1.5516149997711182),
        ('dist_pdh_atr', '<=', -8.70279598236084),
        ('dist_vwap_atr', '>', 1.6524602174758911),
        ('dist_pdh_atr', '<=', -12.643977165222168),
        ('atr_14', '<=', 6.68880033493042),
        ('dist_pdh_atr', '<=', -17.901334762573242),
        ('dist_pdh_atr', '>', -32.212989807128906),
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

class V3LongS8T16_03:
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

class V3ShortS8T16_04:
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

class V3ShortS10T20_05:
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

class V3ShortS10T20_06:
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

class V3LongS12T24_07:
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

class V3ShortS12T24_08:
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

class V3LongS15T30_09:
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

class V3ShortS15T30_10:
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

class V3ShortS15T30_11:
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

class V3LongS20T50_12:
    name = 'V3_LONG_S20T50_05'
    side = 'LONG'
    target_pts = 50.0
    stop_pts = 20.0
    max_hold_bars = 100
    win_rate = 0.4734102833158447
    profit_factor = 1.7778810058991807
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.422818660736084),
        ('dist_pdh_atr', '<=', -6.012660264968872),
        ('dist_pdl_atr', '>', 2.6566004753112793),
        ('dist_vwap_atr', '>', -1.5516149997711182),
        ('dist_pdh_atr', '<=', -8.70279598236084),
        ('dist_vwap_atr', '>', 1.6524602174758911),
        ('dist_pdh_atr', '<=', -12.643977165222168),
        ('atr_14', '>', 6.68880033493042),
        ('range_pos_200', '>', 0.7164867222309113),
        ('atr_50', '<=', 18.901336669921875),
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

class V3LongS15T37_13:
    name = 'V3_LONG_S15T37_06'
    side = 'LONG'
    target_pts = 37.5
    stop_pts = 15.0
    max_hold_bars = 75
    win_rate = 0.4286295655712687
    profit_factor = 1.4237289826623334
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.025644063949585),
        ('dist_pdh_atr', '<=', -5.3685853481292725),
        ('dist_pdl_atr', '<=', 2.735786199569702),
        ('dist_pdl_atr', '<=', 1.6782143712043762),
        ('dist_pdl_atr', '<=', 1.100551724433899),
        ('atr_50', '>', 5.29285740852356),
        ('atr_14', '<=', 19.068782806396484),
        ('is_close_30min', '<=', 0.5),
        ('atr_5', '>', 7.582827091217041),
        ('dist_pdl_atr', '<=', 1.0032547116279602),
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

class V3LongS20T60_14:
    name = 'V3_LONG_S20T60_07'
    side = 'LONG'
    target_pts = 60.0
    stop_pts = 20.0
    max_hold_bars = 130
    win_rate = 0.45758567817330403
    profit_factor = 2.012921345970061
    tier = 'B'
    constraints = [
        ('atr_50', '>', 5.569538593292236),
        ('dist_pdh_atr', '<=', -6.557131290435791),
        ('dist_pdl_atr', '>', 2.80733859539032),
        ('dist_vwap_atr', '>', -1.6907238960266113),
        ('dist_pdh_atr', '<=', -10.067314624786377),
        ('dist_vwap_atr', '>', 1.6142731308937073),
        ('dist_pdh_atr', '<=', -12.51920223236084),
        ('atr_14', '>', 6.738778352737427),
        ('range_pos_200', '>', 0.715205192565918),
        ('atr_50', '<=', 18.901336669921875),
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

class V3LongS20T50_15:
    name = 'V3_LONG_S20T50_08'
    side = 'LONG'
    target_pts = 50.0
    stop_pts = 20.0
    max_hold_bars = 100
    win_rate = 0.4931129476584022
    profit_factor = 1.995788776026928
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.422818660736084),
        ('dist_pdh_atr', '<=', -6.012660264968872),
        ('dist_pdl_atr', '<=', 2.6566004753112793),
        ('dist_pdl_atr', '<=', 1.682193100452423),
        ('atr_50', '>', 6.32197904586792),
        ('is_close_30min', '<=', 0.5),
        ('dist_pdl_atr', '<=', 1.0794454216957092),
        ('atr_14', '>', 8.80678653717041),
        ('atr_14', '<=', 20.764312744140625),
        ('atr_50', '>', 10.074498176574707),
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

class V3LongS15T45_16:
    name = 'V3_LONG_S15T45_09'
    side = 'LONG'
    target_pts = 45.0
    stop_pts = 15.0
    max_hold_bars = 95
    win_rate = 0.39938507209499574
    profit_factor = 1.499945693762188
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.182616472244263),
        ('dist_pdh_atr', '<=', -5.993844270706177),
        ('dist_pdl_atr', '<=', 2.6707526445388794),
        ('dist_pdl_atr', '<=', 1.6782143712043762),
        ('dist_pdl_atr', '<=', 1.0851181745529175),
        ('atr_50', '>', 5.468240261077881),
        ('atr_14', '<=', 19.068782806396484),
        ('is_close_30min', '<=', 0.5),
        ('atr_5', '>', 7.582827091217041),
        ('dist_pdl_atr', '<=', 0.952689915895462),
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

class V3LongS15T37_17:
    name = 'V3_LONG_S15T37_10'
    side = 'LONG'
    target_pts = 37.5
    stop_pts = 15.0
    max_hold_bars = 75
    win_rate = 0.4540190735694823
    profit_factor = 1.5574686407806513
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.025644063949585),
        ('dist_pdh_atr', '<=', -5.3685853481292725),
        ('dist_pdl_atr', '>', 2.735786199569702),
        ('dist_vwap_atr', '>', -1.1052707433700562),
        ('dist_pdh_atr', '<=', -7.801303386688232),
        ('dist_vwap_atr', '>', 1.6471625566482544),
        ('dist_pdh_atr', '<=', -12.55493688583374),
        ('atr_14', '>', 5.402706861495972),
        ('range_pos_200', '>', 0.8395050764083862),
        ('ny_hour', '<=', 13.5),
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

class V3LongS20T60_18:
    name = 'V3_LONG_S20T60_11'
    side = 'LONG'
    target_pts = 60.0
    stop_pts = 20.0
    max_hold_bars = 130
    win_rate = 0.4212867898699521
    profit_factor = 1.765749245346979
    tier = 'B'
    constraints = [
        ('atr_50', '>', 5.569538593292236),
        ('dist_pdh_atr', '<=', -6.557131290435791),
        ('dist_pdl_atr', '<=', 2.80733859539032),
        ('dist_pdl_atr', '<=', 1.799020230770111),
        ('is_close_30min', '<=', 0.5),
        ('atr_14', '>', 7.521528244018555),
        ('dist_pdl_atr', '<=', 1.2711695432662964),
        ('dist_pdl_atr', '<=', 0.9113101363182068),
        ('atr_14', '>', 10.261999130249023),
        ('dist_pdl_atr', '<=', 0.7932310998439789),
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

class V3LongS20T50_19:
    name = 'V3_LONG_S20T50_12'
    side = 'LONG'
    target_pts = 50.0
    stop_pts = 20.0
    max_hold_bars = 100
    win_rate = 0.747909569526169
    profit_factor = 5.672994538959528
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.422818660736084),
        ('dist_pdh_atr', '<=', -6.012660264968872),
        ('dist_pdl_atr', '<=', 2.6566004753112793),
        ('dist_pdl_atr', '<=', 1.682193100452423),
        ('atr_50', '>', 6.32197904586792),
        ('is_close_30min', '<=', 0.5),
        ('dist_pdl_atr', '>', 1.0794454216957092),
        ('atr_14', '<=', 18.4073429107666),
        ('atr_50', '>', 7.776537179946899),
        ('atr_14', '<=', 14.873008728027344),
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

class V3LongS15T60_20:
    name = 'V3_LONG_S15T60_15'
    side = 'LONG'
    target_pts = 60.0
    stop_pts = 15.0
    max_hold_bars = 130
    win_rate = 0.39183397247913376
    profit_factor = 2.0133195189715516
    tier = 'B'
    constraints = [
        ('atr_50', '>', 5.579204797744751),
        ('dist_pdh_atr', '<=', -6.964838027954102),
        ('dist_pdl_atr', '<=', 2.5372726917266846),
        ('dist_pdl_atr', '<=', 1.301396667957306),
        ('atr_14', '>', 7.4748735427856445),
        ('dist_pdl_atr', '<=', 0.9224593341350555),
        ('is_close_30min', '<=', 0.5),
        ('atr_14', '>', 8.863519668579102),
        ('atr_14', '<=', 19.070759773254395),
        ('atr_14', '>', 10.845812797546387),
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

class V3LongS12T36_21:
    name = 'V3_LONG_S12T36_16'
    side = 'LONG'
    target_pts = 36.0
    stop_pts = 12.0
    max_hold_bars = 80
    win_rate = 0.9367502726281353
    profit_factor = 34.42758620689655
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.1464152336120605),
        ('dist_pdh_atr', '<=', -5.706400632858276),
        ('dist_pdl_atr', '<=', 2.53735888004303),
        ('dist_pdl_atr', '<=', 1.285085916519165),
        ('dist_pdl_atr', '<=', 0.910447359085083),
        ('atr_50', '>', 5.287803888320923),
        ('atr_14', '<=', 18.732970237731934),
        ('ny_hour', '<=', 14.5),
        ('dist_pdl_atr', '<=', 0.7808554768562317),
        ('atr_5', '>', 9.129887104034424),
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

class V3LongS20T60_22:
    name = 'V3_LONG_S20T60_20'
    side = 'LONG'
    target_pts = 60.0
    stop_pts = 20.0
    max_hold_bars = 130
    win_rate = 0.7849462365591398
    profit_factor = 8.7644979988078
    tier = 'B'
    constraints = [
        ('atr_50', '>', 5.569538593292236),
        ('dist_pdh_atr', '<=', -6.557131290435791),
        ('dist_pdl_atr', '<=', 2.80733859539032),
        ('dist_pdl_atr', '<=', 1.799020230770111),
        ('is_close_30min', '<=', 0.5),
        ('atr_14', '>', 7.521528244018555),
        ('dist_pdl_atr', '<=', 1.2711695432662964),
        ('dist_pdl_atr', '>', 0.9113101363182068),
        ('atr_14', '<=', 18.867488861083984),
        ('atr_50', '>', 9.9762864112854),
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

class V3LongS20T50_23:
    name = 'V3_LONG_S20T50_21'
    side = 'LONG'
    target_pts = 50.0
    stop_pts = 20.0
    max_hold_bars = 100
    win_rate = 0.7365115615186982
    profit_factor = 5.508512355868285
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.422818660736084),
        ('dist_pdh_atr', '<=', -6.012660264968872),
        ('dist_pdl_atr', '<=', 2.6566004753112793),
        ('dist_pdl_atr', '>', 1.682193100452423),
        ('atr_50', '>', 5.913689851760864),
        ('range_pos_50', '>', 0.1762397512793541),
        ('ny_hour', '<=', 14.5),
        ('dist_pdh_atr', '<=', -8.527825832366943),
        ('autocorr_20', '>', -0.2108965516090393),
        ('atr_14', '<=', 16.71273899078369),
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

class V3LongS20T50_24:
    name = 'V3_LONG_S20T50_23'
    side = 'LONG'
    target_pts = 50.0
    stop_pts = 20.0
    max_hold_bars = 100
    win_rate = 0.45643967990336703
    profit_factor = 1.7122126738568597
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.422818660736084),
        ('dist_pdh_atr', '<=', -6.012660264968872),
        ('dist_pdl_atr', '>', 2.6566004753112793),
        ('dist_vwap_atr', '<=', -1.5516149997711182),
        ('atr_50', '>', 8.479927062988281),
        ('dist_pdl_atr', '<=', 5.999622821807861),
        ('range_pos_200', '>', 0.1737707406282425),
        ('ny_hour', '<=', 14.5),
        ('dist_pdl_atr', '<=', 4.725553750991821),
        ('dist_pdh_atr', '<=', -9.598151683807373),
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

class V3LongS20T60_25:
    name = 'V3_LONG_S20T60_27'
    side = 'LONG'
    target_pts = 60.0
    stop_pts = 20.0
    max_hold_bars = 130
    win_rate = 0.7026022304832714
    profit_factor = 5.517025189478377
    tier = 'B'
    constraints = [
        ('atr_50', '>', 5.569538593292236),
        ('dist_pdh_atr', '<=', -6.557131290435791),
        ('dist_pdl_atr', '<=', 2.80733859539032),
        ('dist_pdl_atr', '<=', 1.799020230770111),
        ('is_close_30min', '<=', 0.5),
        ('atr_14', '>', 7.521528244018555),
        ('dist_pdl_atr', '>', 1.2711695432662964),
        ('atr_14', '<=', 14.437368392944336),
        ('atr_50', '>', 9.340513229370117),
        ('dist_pdl_atr', '<=', 1.6456745266914368),
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

class V3LongS10T30_26:
    name = 'V3_LONG_S10T30_28'
    side = 'LONG'
    target_pts = 30.0
    stop_pts = 10.0
    max_hold_bars = 65
    win_rate = 0.4552656104380242
    profit_factor = 1.8017284113817376
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.003190279006958),
        ('dist_pdh_atr', '<=', -5.072253227233887),
        ('dist_pdl_atr', '<=', 2.644317626953125),
        ('dist_pdl_atr', '<=', 1.1307786107063293),
        ('atr_5', '<=', 14.507619857788086),
        ('atr_50', '>', 4.565703392028809),
        ('dist_pdl_atr', '<=', 0.82944455742836),
        ('rsi_14', '<=', 35.67315673828125),
        ('atr_5', '>', 9.129887104034424),
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

class V3LongS12T30_27:
    name = 'V3_LONG_S12T30_29'
    side = 'LONG'
    target_pts = 30.0
    stop_pts = 12.0
    max_hold_bars = 60
    win_rate = 0.44207631488484017
    profit_factor = 1.4061708615432322
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.15701150894165),
        ('dist_pdh_atr', '<=', -5.072253227233887),
        ('dist_pdl_atr', '<=', 2.886407256126404),
        ('dist_pdl_atr', '<=', 1.3538163900375366),
        ('dist_pdl_atr', '<=', 0.9202439486980438),
        ('atr_14', '<=', 18.732970237731934),
        ('atr_50', '>', 4.984282732009888),
        ('dist_pdl_atr', '<=', 0.7485883831977844),
        ('dist_high20_atr', '<=', -3.6482338905334473),
        ('vol_ratio_30', '>', 1.164069414138794),
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

class V3LongS15T45_28:
    name = 'V3_LONG_S15T45_31'
    side = 'LONG'
    target_pts = 45.0
    stop_pts = 15.0
    max_hold_bars = 95
    win_rate = 0.6472491909385113
    profit_factor = 4.206653081140036
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.182616472244263),
        ('dist_pdh_atr', '<=', -5.993844270706177),
        ('dist_pdl_atr', '<=', 2.6707526445388794),
        ('dist_pdl_atr', '>', 1.6782143712043762),
        ('range_pos_50', '>', 0.17671100050210953),
        ('atr_50', '>', 5.441735029220581),
        ('ny_hour', '<=', 14.5),
        ('dist_pdh_atr', '<=', -8.47669267654419),
        ('atr_14', '<=', 17.03957748413086),
        ('dist_pdl_atr', '<=', 2.4298654794692993),
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

class V3LongS20T60_29:
    name = 'V3_LONG_S20T60_32'
    side = 'LONG'
    target_pts = 60.0
    stop_pts = 20.0
    max_hold_bars = 130
    win_rate = 0.3975405600909373
    profit_factor = 1.5791069599141458
    tier = 'B'
    constraints = [
        ('atr_50', '>', 5.569538593292236),
        ('dist_pdh_atr', '<=', -6.557131290435791),
        ('dist_pdl_atr', '>', 2.80733859539032),
        ('dist_vwap_atr', '<=', -1.6907238960266113),
        ('dist_pdl_atr', '<=', 7.301454544067383),
        ('atr_50', '>', 8.321125507354736),
        ('range_pos_200', '>', 0.1568959653377533),
        ('dist_pdl_atr', '<=', 5.2457802295684814),
        ('ny_hour', '<=', 14.5),
        ('dist_pdh_atr', '<=', -9.01341724395752),
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

class V3LongS15T37_30:
    name = 'V3_LONG_S15T37_33'
    side = 'LONG'
    target_pts = 37.5
    stop_pts = 15.0
    max_hold_bars = 75
    win_rate = 0.845
    profit_factor = 10.57117171111777
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.025644063949585),
        ('dist_pdh_atr', '<=', -5.3685853481292725),
        ('dist_pdl_atr', '<=', 2.735786199569702),
        ('dist_pdl_atr', '<=', 1.6782143712043762),
        ('dist_pdl_atr', '>', 1.100551724433899),
        ('atr_5', '<=', 14.506757736206055),
        ('atr_50', '>', 6.5464818477630615),
        ('is_close_30min', '<=', 0.5),
        ('atr_14', '<=', 10.31950855255127),
        ('dist_vwap_atr', '<=', -5.86960244178772),
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

class V3LongS20T60_31:
    name = 'V3_LONG_S20T60_34'
    side = 'LONG'
    target_pts = 60.0
    stop_pts = 20.0
    max_hold_bars = 130
    win_rate = 0.6903409090909091
    profit_factor = 5.439250453354826
    tier = 'B'
    constraints = [
        ('atr_50', '>', 5.569538593292236),
        ('dist_pdh_atr', '<=', -6.557131290435791),
        ('dist_pdl_atr', '<=', 2.80733859539032),
        ('dist_pdl_atr', '>', 1.799020230770111),
        ('range_pos_50', '>', 0.1711648404598236),
        ('atr_50', '>', 7.954424142837524),
        ('ny_hour', '<=', 14.5),
        ('atr_14', '<=', 16.403549194335938),
        ('autocorr_20', '>', -0.19494391232728958),
        ('range_pos_50', '>', 0.24118925631046295),
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

class V3LongS10T30_32:
    name = 'V3_LONG_S10T30_35'
    side = 'LONG'
    target_pts = 30.0
    stop_pts = 10.0
    max_hold_bars = 65
    win_rate = 0.4066006600660066
    profit_factor = 1.4387952324707398
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.003190279006958),
        ('dist_pdh_atr', '<=', -5.072253227233887),
        ('dist_pdl_atr', '>', 2.644317626953125),
        ('dist_vwap_atr', '>', 0.7462461888790131),
        ('dist_pdh_atr', '<=', -7.798905849456787),
        ('dist_vwap_atr', '<=', 5.745777606964111),
        ('atr_14', '>', 5.4002766609191895),
        ('dist_pdh_atr', '<=', -12.281664371490479),
        ('atr_50', '<=', 8.697280883789062),
        ('ny_hour', '<=', 11.5),
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

class V3LongS20T60_33:
    name = 'V3_LONG_S20T60_37'
    side = 'LONG'
    target_pts = 60.0
    stop_pts = 20.0
    max_hold_bars = 130
    win_rate = 0.40256914948720607
    profit_factor = 1.6215627742970429
    tier = 'B'
    constraints = [
        ('atr_50', '>', 5.569538593292236),
        ('dist_pdh_atr', '<=', -6.557131290435791),
        ('dist_pdl_atr', '>', 2.80733859539032),
        ('dist_vwap_atr', '>', -1.6907238960266113),
        ('dist_pdh_atr', '<=', -10.067314624786377),
        ('dist_vwap_atr', '<=', 1.6142731308937073),
        ('dist_pdl_atr', '<=', 10.410420894622803),
        ('ny_hour', '<=', 14.5),
        ('atr_14', '>', 7.050776243209839),
        ('range_pos_200', '>', 0.49571916460990906),
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

class V3LongS12T30_34:
    name = 'V3_LONG_S12T30_38'
    side = 'LONG'
    target_pts = 30.0
    stop_pts = 12.0
    max_hold_bars = 60
    win_rate = 0.6720360824742269
    profit_factor = 3.79376625086397
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.15701150894165),
        ('dist_pdh_atr', '<=', -5.072253227233887),
        ('dist_pdl_atr', '<=', 2.886407256126404),
        ('dist_pdl_atr', '>', 1.3538163900375366),
        ('range_pos_50', '>', 0.17229097336530685),
        ('dist_pdl_atr', '<=', 2.193838357925415),
        ('atr_5', '<=', 15.596621036529541),
        ('atr_14', '>', 5.428649425506592),
        ('ny_hour', '<=', 14.5),
        ('autocorr_20', '>', -0.0809602364897728),
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

class V3LongS20T50_35:
    name = 'V3_LONG_S20T50_43'
    side = 'LONG'
    target_pts = 50.0
    stop_pts = 20.0
    max_hold_bars = 100
    win_rate = 0.4998722860791826
    profit_factor = 2.0182223167414737
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.422818660736084),
        ('dist_pdh_atr', '<=', -6.012660264968872),
        ('dist_pdl_atr', '>', 2.6566004753112793),
        ('dist_vwap_atr', '>', -1.5516149997711182),
        ('dist_pdh_atr', '<=', -8.70279598236084),
        ('dist_vwap_atr', '<=', 1.6524602174758911),
        ('atr_5', '>', 6.69941258430481),
        ('dist_pdl_atr', '<=', 6.170801401138306),
        ('range_pos_200', '>', 0.23140401393175125),
        ('dist_pdl_atr', '<=', 4.3615639209747314),
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

class V3LongS15T45_36:
    name = 'V3_LONG_S15T45_49'
    side = 'LONG'
    target_pts = 45.0
    stop_pts = 15.0
    max_hold_bars = 95
    win_rate = 0.7045143638850889
    profit_factor = 5.16707512335392
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.182616472244263),
        ('dist_pdh_atr', '<=', -5.993844270706177),
        ('dist_pdl_atr', '<=', 2.6707526445388794),
        ('dist_pdl_atr', '<=', 1.6782143712043762),
        ('dist_pdl_atr', '>', 1.0851181745529175),
        ('range_pos_50', '>', 0.1053534485399723),
        ('atr_14', '>', 6.912895441055298),
        ('atr_14', '<=', 14.315943241119385),
        ('sigma_ratio_1_15', '<=', 2.361002802848816),
        ('dist_low20_atr', '>', 1.0815331935882568),
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

class V3LongS10T25_37:
    name = 'V3_LONG_S10T25_56'
    side = 'LONG'
    target_pts = 25.0
    stop_pts = 10.0
    max_hold_bars = 50
    win_rate = 0.4415112618067329
    profit_factor = 1.3432716090647772
    tier = 'B'
    constraints = [
        ('atr_14', '>', 3.998560667037964),
        ('dist_pdh_atr', '<=', -4.839178562164307),
        ('dist_pdl_atr', '>', 2.712595224380493),
        ('dist_vwap_atr', '>', 0.7606991231441498),
        ('dist_pdh_atr', '<=', -7.934621810913086),
        ('dist_vwap_atr', '>', 5.745777606964111),
        ('ny_hour', '<=', 13.5),
        ('dist_pdh_atr', '<=', -13.007618427276611),
        ('rsi_14', '<=', 61.13266563415527),
        ('dist_pdh_atr', '<=', -18.328272819519043),
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

class V3LongS12T36_38:
    name = 'V3_LONG_S12T36_57'
    side = 'LONG'
    target_pts = 36.0
    stop_pts = 12.0
    max_hold_bars = 80
    win_rate = 0.40459320791595405
    profit_factor = 1.5490600704775748
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.1464152336120605),
        ('dist_pdh_atr', '<=', -5.706400632858276),
        ('dist_pdl_atr', '>', 2.53735888004303),
        ('dist_vwap_atr', '<=', 1.0250055193901062),
        ('atr_14', '>', 6.139289855957031),
        ('dist_pdl_atr', '<=', 5.273932218551636),
        ('range_pos_200', '>', 0.1974082514643669),
        ('ny_hour', '<=', 14.5),
        ('dist_pdh_atr', '<=', -10.394914627075195),
        ('dist_pdl_atr', '<=', 3.687851905822754),
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

class V3LongS20T60_39:
    name = 'V3_LONG_S20T60_59'
    side = 'LONG'
    target_pts = 60.0
    stop_pts = 20.0
    max_hold_bars = 130
    win_rate = 0.5674615152429822
    profit_factor = 2.8336991912410907
    tier = 'B'
    constraints = [
        ('atr_50', '>', 5.569538593292236),
        ('dist_pdh_atr', '<=', -6.557131290435791),
        ('dist_pdl_atr', '>', 2.80733859539032),
        ('dist_vwap_atr', '>', -1.6907238960266113),
        ('dist_pdh_atr', '<=', -10.067314624786377),
        ('dist_vwap_atr', '>', 1.6142731308937073),
        ('dist_pdh_atr', '<=', -12.51920223236084),
        ('atr_14', '<=', 6.738778352737427),
        ('autocorr_20', '<=', 0.2320891171693802),
        ('dist_pdh_atr', '<=', -18.67366600036621),
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

class V3LongS10T30_40:
    name = 'V3_LONG_S10T30_60'
    side = 'LONG'
    target_pts = 30.0
    stop_pts = 10.0
    max_hold_bars = 65
    win_rate = 0.34231697506033787
    profit_factor = 1.162046581765489
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.003190279006958),
        ('dist_pdh_atr', '<=', -5.072253227233887),
        ('dist_pdl_atr', '<=', 2.644317626953125),
        ('dist_pdl_atr', '<=', 1.1307786107063293),
        ('atr_5', '>', 14.507619857788086),
        ('dist_pdl_atr', '<=', 0.7062608897686005),
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

class V3LongS20T50_41:
    name = 'V3_LONG_S20T50_61'
    side = 'LONG'
    target_pts = 50.0
    stop_pts = 20.0
    max_hold_bars = 100
    win_rate = 0.7255772646536413
    profit_factor = 5.265298697518737
    tier = 'B'
    constraints = [
        ('atr_14', '<=', 5.422818660736084),
        ('dist_pdh_atr', '<=', -11.864818572998047),
        ('atr_14', '>', 3.881981134414673),
        ('dist_pdl_atr', '>', 22.893770217895508),
        ('ny_hour', '>', 12.5),
        ('ny_hour', '>', 13.5),
        ('dist_pdl_atr', '>', 26.1322660446167),
        ('atr_14', '>', 4.181915283203125),
        ('dist_vwap_atr', '>', 4.074731111526489),
        ('dist_vwap_atr', '<=', 13.50168514251709),
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

class V3LongS12T30_42:
    name = 'V3_LONG_S12T30_63'
    side = 'LONG'
    target_pts = 30.0
    stop_pts = 12.0
    max_hold_bars = 60
    win_rate = 0.4259537398618204
    profit_factor = 1.3958813477632213
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.15701150894165),
        ('dist_pdh_atr', '<=', -5.072253227233887),
        ('dist_pdl_atr', '>', 2.886407256126404),
        ('dist_vwap_atr', '<=', 0.7053795456886292),
        ('atr_50', '>', 6.059848308563232),
        ('dist_pdl_atr', '<=', 5.275662660598755),
        ('range_pos_200', '>', 0.19013440608978271),
        ('ny_hour', '<=', 14.5),
        ('dist_pdh_atr', '<=', -11.027214527130127),
        ('dist_pdl_atr', '<=', 3.738248348236084),
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

class V3LongS15T37_43:
    name = 'V3_LONG_S15T37_64'
    side = 'LONG'
    target_pts = 37.5
    stop_pts = 15.0
    max_hold_bars = 75
    win_rate = 0.4971864951768489
    profit_factor = 1.9183455161347833
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.025644063949585),
        ('dist_pdh_atr', '<=', -5.3685853481292725),
        ('dist_pdl_atr', '>', 2.735786199569702),
        ('dist_vwap_atr', '<=', -1.1052707433700562),
        ('dist_pdl_atr', '<=', 5.490366697311401),
        ('atr_50', '>', 7.940359354019165),
        ('range_pos_200', '>', 0.18831495195627213),
        ('ny_hour', '<=', 14.5),
        ('atr_14', '<=', 14.35991382598877),
        ('dist_pdl_atr', '<=', 3.93029522895813),
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

ALL_V3_SIGNALS = [
    V3ShortS15T30_01(),
    V3LongS20T50_02(),
    V3LongS8T16_03(),
    V3ShortS8T16_04(),
    V3ShortS10T20_05(),
    V3ShortS10T20_06(),
    V3LongS12T24_07(),
    V3ShortS12T24_08(),
    V3LongS15T30_09(),
    V3ShortS15T30_10(),
    V3ShortS15T30_11(),
    V3LongS20T50_12(),
    V3LongS15T37_13(),
    V3LongS20T60_14(),
    V3LongS20T50_15(),
    V3LongS15T45_16(),
    V3LongS15T37_17(),
    V3LongS20T60_18(),
    V3LongS20T50_19(),
    V3LongS15T60_20(),
    V3LongS12T36_21(),
    V3LongS20T60_22(),
    V3LongS20T50_23(),
    V3LongS20T50_24(),
    V3LongS20T60_25(),
    V3LongS10T30_26(),
    V3LongS12T30_27(),
    V3LongS15T45_28(),
    V3LongS20T60_29(),
    V3LongS15T37_30(),
    V3LongS20T60_31(),
    V3LongS10T30_32(),
    V3LongS20T60_33(),
    V3LongS12T30_34(),
    V3LongS20T50_35(),
    V3LongS15T45_36(),
    V3LongS10T25_37(),
    V3LongS12T36_38(),
    V3LongS20T60_39(),
    V3LongS10T30_40(),
    V3LongS20T50_41(),
    V3LongS12T30_42(),
    V3LongS15T37_43(),
]