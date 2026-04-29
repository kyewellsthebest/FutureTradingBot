"""
Auto-generated v3 pattern Signal classes.
Generated: 2026-04-29T02:45:02.632797+00:00
Survivors: 101  
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

class V3ShortS10T20_03:
    name = 'V3_SHORT_S10T20_34'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    win_rate = 0.628
    profit_factor = 1.91
    tier = 'A'
    constraints = [
        ('atr_14', '<=', 4.461906909942627),
        ('atr_14', '>', 3.1655397415161133),
        ('dist_pdl_atr', '>', 5.891580104827881),
        ('range_pos_200', '>', 0.2989274114370346),
        ('dist_pdh_atr', '>', -3.960201144218445),
        ('dist_pdh_atr', '>', -2.493194341659546),
        ('atr_14', '>', 3.565252423286438),
        ('dist_pdl_atr', '>', 18.925270080566406),
        ('dist_eq50_atr', '<=', 4.504656791687012),
        ('dist_pdh_atr', '<=', -1.3118828535079956),
        ('range_pos_50', '<=', 0.8811541497707367),
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

class V3ShortS20T40_04:
    name = 'V3_SHORT_S20T40_76'
    side = 'SHORT'
    target_pts = 40.0
    stop_pts = 20.0
    max_hold_bars = 60
    win_rate = 0.7336956521739131
    profit_factor = 4.339654588554013
    tier = 'A'
    constraints = [
        ('atr_5', '>', 3.4499123096466064),
        ('dist_pdl_atr', '>', 5.653881788253784),
        ('atr_14', '>', 4.705383062362671),
        ('atr_14', '>', 6.158627986907959),
        ('dist_vwap_atr', '<=', -3.8593982458114624),
        ('dist_pdl_atr', '>', 14.12391471862793),
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
    name = 'V3_SHORT_S10T20_80'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    win_rate = 0.6164772727272727
    profit_factor = 2.2144581949894357
    tier = 'A'
    constraints = [
        ('atr_14', '>', 2.7137562036514282),
        ('dist_pdl_atr', '>', 4.566998481750488),
        ('atr_5', '>', 4.065537929534912),
        ('atr_5', '>', 5.493957996368408),
        ('range_pos_50', '<=', 0.41704143583774567),
        ('dist_pdl_atr', '>', 17.593965530395508),
        ('atr_50', '<=', 4.994477987289429),
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

class V3ShortS20T40_06:
    name = 'V3_SHORT_S20T40_81'
    side = 'SHORT'
    target_pts = 40.0
    stop_pts = 20.0
    max_hold_bars = 60
    win_rate = 0.6736641221374046
    profit_factor = 3.711637931034483
    tier = 'A'
    constraints = [
        ('atr_5', '>', 3.4499123096466064),
        ('dist_pdl_atr', '>', 5.653881788253784),
        ('atr_14', '>', 4.705383062362671),
        ('atr_14', '<=', 6.158627986907959),
        ('dist_pdl_atr', '>', 6.988938093185425),
        ('atr_50', '<=', 5.107365608215332),
        ('dist_pdl_atr', '>', 7.996172189712524),
        ('range_pos_200', '<=', 0.3866951912641525),
        ('dist_pdl_atr', '>', 18.842554092407227),
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

class V3LongS15T30_07:
    name = 'V3_LONG_S15T30_69'
    side = 'LONG'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.6535796766743649
    profit_factor = 2.5266100419309754
    tier = 'A'
    constraints = [
        ('atr_14', '>', 3.116254687309265),
        ('atr_5', '>', 4.506859302520752),
        ('dist_pdh_atr', '<=', -7.498788118362427),
        ('atr_14', '>', 5.42473578453064),
        ('dist_pdl_atr', '<=', 13.60510540008545),
        ('dist_pdl_atr', '<=', 2.806034207344055),
        ('autocorr_20', '>', 0.03223901614546776),
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

class V3LongS8T16_08:
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

class V3ShortS8T16_09:
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

class V3ShortS10T20_10:
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

class V3ShortS10T20_11:
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

class V3LongS12T24_12:
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

class V3ShortS12T24_13:
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

class V3LongS15T30_14:
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

class V3ShortS15T30_15:
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

class V3ShortS15T30_16:
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

class V3LongS20T50_17:
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

class V3LongS15T37_18:
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

class V3LongS20T60_19:
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

class V3LongS20T50_20:
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

class V3LongS15T45_21:
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

class V3LongS15T37_22:
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

class V3LongS20T60_23:
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

class V3LongS20T50_24:
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

class V3LongS15T60_25:
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

class V3LongS12T36_26:
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

class V3LongS20T60_27:
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

class V3LongS20T50_28:
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

class V3LongS20T50_29:
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

class V3LongS20T60_30:
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

class V3LongS10T30_31:
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

class V3LongS12T30_32:
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

class V3LongS15T45_33:
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

class V3LongS20T60_34:
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

class V3LongS15T37_35:
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

class V3LongS20T60_36:
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

class V3LongS10T30_37:
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

class V3LongS20T60_38:
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

class V3LongS12T30_39:
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

class V3LongS20T50_40:
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

class V3LongS15T45_41:
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

class V3LongS10T25_42:
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

class V3LongS12T36_43:
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

class V3LongS20T60_44:
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

class V3LongS10T30_45:
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

class V3LongS20T50_46:
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

class V3LongS12T30_47:
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

class V3LongS15T37_48:
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

class V3ShortS8T16_49:
    name = 'V3_SHORT_S8T16_24'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 8.0
    max_hold_bars = 25
    win_rate = 0.5870000000000001
    profit_factor = 1.83
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.043004274368286),
        ('dist_pdl_atr', '>', 2.4498130083084106),
        ('dist_pdh_atr', '>', -2.9448471069335938),
        ('dist_pdh_atr', '>', -1.4767688512802124),
        ('atr_14', '<=', 10.58998966217041),
        ('dist_pdh_atr', '>', -1.17132568359375),
        ('dist_pdh_atr', '<=', -0.7121082842350006),
        ('dist_pdl_atr', '>', 18.000110626220703),
        ('rsi_14', '<=', 71.96705627441406),
        ('range_pos_200', '<=', 0.9719952940940857),
        ('vol_imbalance_10', '<=', 0.6746580898761749),
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

class V3ShortS8T16_50:
    name = 'V3_SHORT_S8T16_25'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 8.0
    max_hold_bars = 25
    win_rate = 0.507
    profit_factor = 1.28
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
        ('range_pos_50', '>', 0.7729895710945129),
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

class V3ShortS10T20_51:
    name = 'V3_SHORT_S10T20_27'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    win_rate = 0.723
    profit_factor = 3.83
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('dist_pdl_atr', '>', 2.8014075756073),
        ('dist_pdh_atr', '>', -2.9352803230285645),
        ('dist_pdh_atr', '>', -1.4767688512802124),
        ('dist_pdh_atr', '>', -0.99527308344841),
        ('atr_14', '<=', 16.405616760253906),
        ('atr_14', '>', 6.00428032875061),
        ('dist_pdh_atr', '>', -0.9068338871002197),
        ('dist_pdh_atr', '<=', -0.6847145855426788),
        ('dist_high20_atr', '<=', -0.47311778366565704),
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

class V3ShortS10T20_52:
    name = 'V3_SHORT_S10T20_28'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    win_rate = 0.494
    profit_factor = 1.34
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('dist_pdl_atr', '>', 2.8014075756073),
        ('dist_pdh_atr', '>', -2.9352803230285645),
        ('dist_pdh_atr', '<=', -1.4767688512802124),
        ('range_pos_50', '<=', 0.8868695795536041),
        ('dist_pdh_atr', '<=', -2.2107986211776733),
        ('range_pos_50', '<=', 0.8043951690196991),
        ('atr_50', '>', 3.9394125938415527),
        ('ny_hour', '<=', 14.5),
        ('atr_14', '<=', 15.2545747756958),
        ('autocorr_5', '>', -0.13595503568649292),
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

class V3ShortS10T20_53:
    name = 'V3_SHORT_S10T20_29'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    win_rate = 0.496
    profit_factor = 1.38
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('dist_pdl_atr', '>', 2.8014075756073),
        ('dist_pdh_atr', '>', -2.9352803230285645),
        ('dist_pdh_atr', '<=', -1.4767688512802124),
        ('range_pos_50', '<=', 0.8868695795536041),
        ('dist_pdh_atr', '<=', -2.2107986211776733),
        ('range_pos_50', '<=', 0.8043951690196991),
        ('atr_50', '>', 3.9394125938415527),
        ('ny_hour', '<=', 14.5),
        ('atr_14', '<=', 15.2545747756958),
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

class V3ShortS10T20_54:
    name = 'V3_SHORT_S10T20_30'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    win_rate = 0.5579999999999999
    profit_factor = 1.73
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
        ('dist_vwap_atr', '>', 4.054693937301636),
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

class V3ShortS10T20_55:
    name = 'V3_SHORT_S10T20_31'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    win_rate = 0.517
    profit_factor = 1.48
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
        ('autocorr_5', '<=', -0.18456797301769257),
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

class V3ShortS10T20_56:
    name = 'V3_SHORT_S10T20_32'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    win_rate = 0.502
    profit_factor = 1.47
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('dist_pdl_atr', '>', 2.8014075756073),
        ('dist_pdh_atr', '>', -2.9352803230285645),
        ('dist_pdh_atr', '>', -1.4767688512802124),
        ('dist_pdh_atr', '<=', -0.99527308344841),
        ('atr_14', '>', 10.608480453491211),
        ('dist_high20_atr', '<=', -1.022996425628662),
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

class V3ShortS10T20_57:
    name = 'V3_SHORT_S10T20_33'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    win_rate = 0.45299999999999996
    profit_factor = 1.2
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('dist_pdl_atr', '>', 2.8014075756073),
        ('dist_pdh_atr', '>', -2.9352803230285645),
        ('dist_pdh_atr', '>', -1.4767688512802124),
        ('dist_pdh_atr', '>', -0.99527308344841),
        ('atr_14', '>', 16.405616760253906),
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

class V3ShortS12T24_58:
    name = 'V3_SHORT_S12T24_35'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    win_rate = 0.455
    profit_factor = 1.26
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.707773685455322),
        ('dist_pdl_atr', '>', 3.4693500995635986),
        ('dist_pdh_atr', '<=', -2.665213942527771),
        ('atr_14', '>', 6.7525763511657715),
        ('dist_vwap_atr', '>', 0.3452015668153763),
        ('dist_pdh_atr', '>', -7.347257375717163),
        ('range_pos_200', '<=', 0.8488775789737701),
        ('ny_hour', '<=', 14.5),
        ('dist_pdh_atr', '>', -4.3109471797943115),
        ('atr_5', '<=', 12.498469829559326),
        ('atr_50', '>', 8.83052921295166),
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

class V3ShortS12T24_59:
    name = 'V3_SHORT_S12T24_36'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    win_rate = 0.88
    profit_factor = 11.83
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.707773685455322),
        ('dist_pdl_atr', '>', 3.4693500995635986),
        ('dist_pdh_atr', '>', -2.665213942527771),
        ('dist_pdh_atr', '>', -1.4006109833717346),
        ('dist_pdh_atr', '<=', -1.0779643058776855),
        ('atr_14', '<=', 10.734930515289307),
        ('atr_14', '>', 5.923901557922363),
        ('range_pos_50', '<=', 0.9347736537456512),
        ('dist_vwap_atr', '>', 5.300555229187012),
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

class V3ShortS12T24_60:
    name = 'V3_SHORT_S12T24_37'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    win_rate = 0.512
    profit_factor = 1.52
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
        ('rsi_2', '<=', 80.24885559082031),
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

class V3ShortS12T24_61:
    name = 'V3_SHORT_S12T24_38'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    win_rate = 0.605
    profit_factor = 2.13
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.707773685455322),
        ('dist_pdl_atr', '>', 3.4693500995635986),
        ('dist_pdh_atr', '>', -2.665213942527771),
        ('dist_pdh_atr', '<=', -1.4006109833717346),
        ('range_pos_50', '<=', 0.8919178545475006),
        ('dist_pdh_atr', '>', -2.018115758895874),
        ('ret_10', '<=', 35.125),
        ('ema_distance', '>', 0.48282375931739807),
        ('dist_high20_atr', '<=', -1.4106590151786804),
        ('dist_pdh_atr', '<=', -1.7592483758926392),
        ('hurst_proxy_50', '<=', 2.0835341215133667),
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

class V3ShortS12T24_62:
    name = 'V3_SHORT_S12T24_39'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    win_rate = 0.696
    profit_factor = 3.34
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.707773685455322),
        ('dist_pdl_atr', '>', 3.4693500995635986),
        ('dist_pdh_atr', '>', -2.665213942527771),
        ('dist_pdh_atr', '<=', -1.4006109833717346),
        ('range_pos_50', '<=', 0.8919178545475006),
        ('dist_pdh_atr', '>', -2.018115758895874),
        ('ret_10', '<=', 35.125),
        ('ema_distance', '>', 0.48282375931739807),
        ('dist_high20_atr', '<=', -1.4106590151786804),
        ('dist_pdh_atr', '>', -1.7592483758926392),
        ('ofi_5', '<=', 213.7213363647461),
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

class V3ShortS12T24_63:
    name = 'V3_SHORT_S12T24_40'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    win_rate = 0.425
    profit_factor = 1.12
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.707773685455322),
        ('dist_pdl_atr', '>', 3.4693500995635986),
        ('dist_pdh_atr', '<=', -2.665213942527771),
        ('atr_14', '>', 6.7525763511657715),
        ('dist_vwap_atr', '<=', 0.3452015668153763),
        ('dist_pdl_atr', '>', 7.219175577163696),
        ('range_pos_200', '>', 0.28324197232723236),
        ('dist_pdh_atr', '>', -7.578496217727661),
        ('dist_vwap_atr', '<=', -1.3870229721069336),
        ('dist_pdh_atr', '<=', -5.281530141830444),
        ('is_open_30min', '<=', 0.5),
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

class V3ShortS12T24_64:
    name = 'V3_SHORT_S12T24_41'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    win_rate = 0.574
    profit_factor = 1.93
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.707773685455322),
        ('dist_pdl_atr', '>', 3.4693500995635986),
        ('dist_pdh_atr', '>', -2.665213942527771),
        ('dist_pdh_atr', '<=', -1.4006109833717346),
        ('range_pos_50', '<=', 0.8919178545475006),
        ('dist_pdh_atr', '>', -2.018115758895874),
        ('ret_10', '<=', 35.125),
        ('ema_distance', '>', 0.48282375931739807),
        ('dist_high20_atr', '>', -1.4106590151786804),
        ('sigma_ratio_1_5', '>', 1.0696392059326172),
        ('ofi_5', '>', 174.383056640625),
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

class V3ShortS12T24_65:
    name = 'V3_SHORT_S12T24_42'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    win_rate = 0.504
    profit_factor = 1.55
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.707773685455322),
        ('dist_pdl_atr', '>', 3.4693500995635986),
        ('dist_pdh_atr', '>', -2.665213942527771),
        ('dist_pdh_atr', '>', -1.4006109833717346),
        ('dist_pdh_atr', '>', -1.0779643058776855),
        ('atr_14', '>', 17.888303756713867),
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

class V3ShortS12T24_66:
    name = 'V3_SHORT_S12T24_43'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    win_rate = 0.462
    profit_factor = 1.31
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.707773685455322),
        ('dist_pdl_atr', '>', 3.4693500995635986),
        ('dist_pdh_atr', '<=', -2.665213942527771),
        ('atr_14', '>', 6.7525763511657715),
        ('dist_vwap_atr', '<=', 0.3452015668153763),
        ('dist_pdl_atr', '>', 7.219175577163696),
        ('range_pos_200', '<=', 0.28324197232723236),
        ('autocorr_20', '<=', -0.09257800132036209),
        ('ny_hour', '>', 14.5),
        ('dow', '>', 0.5),
        ('ema_distance', '<=', -1.4548740983009338),
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

class V3ShortS12T24_67:
    name = 'V3_SHORT_S12T24_44'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    win_rate = 0.5920000000000001
    profit_factor = 1.87
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
        ('atr_50', '<=', 7.132232904434204),
        ('atr_5', '<=', 6.932129383087158),
        ('sigma_ratio_1_5', '>', 1.0198018550872803),
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

class V3ShortS12T24_68:
    name = 'V3_SHORT_S12T24_45'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    win_rate = 0.479
    profit_factor = 1.29
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.707773685455322),
        ('dist_pdl_atr', '>', 3.4693500995635986),
        ('dist_pdh_atr', '>', -2.665213942527771),
        ('dist_pdh_atr', '<=', -1.4006109833717346),
        ('range_pos_50', '<=', 0.8919178545475006),
        ('dist_pdh_atr', '<=', -2.018115758895874),
        ('range_pos_50', '<=', 0.8086031675338745),
        ('autocorr_5', '<=', -0.19805394113063812),
        ('lower_wick_pct', '<=', 0.22018422931432724),
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

class V3ShortS15T30_69:
    name = 'V3_SHORT_S15T30_46'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.5720000000000001
    profit_factor = 2.12
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.143145322799683),
        ('dist_pdl_atr', '>', 3.7716599702835083),
        ('dist_pdh_atr', '>', -2.655640721321106),
        ('dist_pdh_atr', '>', -1.8196828365325928),
        ('dist_pdh_atr', '>', -1.175345242023468),
        ('atr_14', '>', 6.079609632492065),
        ('atr_14', '<=', 20.234673500061035),
        ('ny_minute', '<=', 51.5),
        ('atr_14', '>', 8.823062896728516),
        ('dist_pdh_atr', '>', -0.9090655744075775),
        ('vol_imbalance_10', '<=', 0.73343825340271),
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

class V3ShortS15T30_70:
    name = 'V3_SHORT_S15T30_47'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.49200000000000005
    profit_factor = 1.55
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.143145322799683),
        ('dist_pdl_atr', '>', 3.7716599702835083),
        ('dist_pdh_atr', '<=', -2.655640721321106),
        ('dist_vwap_atr', '<=', 0.3556029945611954),
        ('dist_pdl_atr', '>', 7.351938962936401),
        ('range_pos_200', '<=', 0.2944239675998688),
        ('autocorr_20', '>', -0.09241769090294838),
        ('dist_pdl_atr', '>', 15.273326396942139),
        ('dow', '>', 1.5),
        ('dow', '>', 2.5),
        ('autocorr_20', '<=', 0.1417107880115509),
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

class V3ShortS15T30_71:
    name = 'V3_SHORT_S15T30_48'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.536
    profit_factor = 1.62
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.143145322799683),
        ('dist_pdl_atr', '>', 3.7716599702835083),
        ('dist_pdh_atr', '>', -2.655640721321106),
        ('dist_pdh_atr', '>', -1.8196828365325928),
        ('dist_pdh_atr', '>', -1.175345242023468),
        ('atr_14', '>', 6.079609632492065),
        ('atr_14', '<=', 20.234673500061035),
        ('ny_minute', '<=', 51.5),
        ('atr_14', '<=', 8.823062896728516),
        ('dist_pdl_atr', '>', 31.796199798583984),
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

class V3ShortS15T30_72:
    name = 'V3_SHORT_S15T30_49'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.557
    profit_factor = 1.82
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.143145322799683),
        ('dist_pdl_atr', '>', 3.7716599702835083),
        ('dist_pdh_atr', '>', -2.655640721321106),
        ('dist_pdh_atr', '>', -1.8196828365325928),
        ('dist_pdh_atr', '>', -1.175345242023468),
        ('atr_14', '>', 6.079609632492065),
        ('atr_14', '<=', 20.234673500061035),
        ('ny_minute', '>', 51.5),
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

class V3ShortS15T30_73:
    name = 'V3_SHORT_S15T30_50'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.672
    profit_factor = 3.35
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.143145322799683),
        ('dist_pdl_atr', '>', 3.7716599702835083),
        ('dist_pdh_atr', '>', -2.655640721321106),
        ('dist_pdh_atr', '>', -1.8196828365325928),
        ('dist_pdh_atr', '<=', -1.175345242023468),
        ('range_pos_50', '<=', 0.9146275222301483),
        ('atr_14', '>', 5.924866199493408),
        ('atr_14', '<=', 12.402623653411865),
        ('atr_14', '>', 7.589281797409058),
        ('dist_pdh_atr', '<=', -1.381133794784546),
        ('vol_ratio_30', '<=', 0.8040164411067963),
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

class V3ShortS15T30_74:
    name = 'V3_SHORT_S15T30_51'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.652
    profit_factor = 2.85
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.143145322799683),
        ('dist_pdl_atr', '>', 3.7716599702835083),
        ('dist_pdh_atr', '>', -2.655640721321106),
        ('dist_pdh_atr', '>', -1.8196828365325928),
        ('dist_pdh_atr', '<=', -1.175345242023468),
        ('range_pos_50', '<=', 0.9146275222301483),
        ('atr_14', '>', 5.924866199493408),
        ('atr_14', '<=', 12.402623653411865),
        ('atr_14', '>', 7.589281797409058),
        ('dist_pdh_atr', '<=', -1.381133794784546),
        ('vol_ratio_30', '>', 0.8040164411067963),
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

class V3ShortS8T20_75:
    name = 'V3_SHORT_S8T20_57'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 8.0
    max_hold_bars = 40
    win_rate = 0.9359999999999999
    profit_factor = 26.42
    tier = 'B'
    constraints = [
        ('atr_14', '>', 3.738183617591858),
        ('dist_pdl_atr', '>', 3.79175865650177),
        ('dist_pdh_atr', '>', -2.9352803230285645),
        ('dist_pdh_atr', '>', -1.4767688512802124),
        ('atr_14', '<=', 10.58998966217041),
        ('dist_pdh_atr', '>', -1.0095460414886475),
        ('atr_14', '>', 5.3874804973602295),
        ('dist_pdh_atr', '>', -0.7884941399097443),
        ('ny_hour', '<=', 12.5),
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

class V3ShortS8T20_76:
    name = 'V3_SHORT_S8T20_59'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 8.0
    max_hold_bars = 40
    win_rate = 0.56
    profit_factor = 2.08
    tier = 'B'
    constraints = [
        ('atr_14', '>', 3.738183617591858),
        ('dist_pdl_atr', '>', 3.79175865650177),
        ('dist_pdh_atr', '>', -2.9352803230285645),
        ('dist_pdh_atr', '>', -1.4767688512802124),
        ('atr_14', '<=', 10.58998966217041),
        ('dist_pdh_atr', '>', -1.0095460414886475),
        ('atr_14', '>', 5.3874804973602295),
        ('dist_pdh_atr', '<=', -0.7884941399097443),
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

class V3ShortS8T20_77:
    name = 'V3_SHORT_S8T20_60'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 8.0
    max_hold_bars = 40
    win_rate = 0.419
    profit_factor = 1.24
    tier = 'B'
    constraints = [
        ('atr_14', '>', 3.738183617591858),
        ('dist_pdl_atr', '>', 3.79175865650177),
        ('dist_pdh_atr', '>', -2.9352803230285645),
        ('dist_pdh_atr', '>', -1.4767688512802124),
        ('atr_14', '>', 10.58998966217041),
        ('dist_pdh_atr', '>', -0.7020658850669861),
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

class V3ShortS8T20_78:
    name = 'V3_SHORT_S8T20_62'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 8.0
    max_hold_bars = 40
    win_rate = 0.536
    profit_factor = 1.77
    tier = 'B'
    constraints = [
        ('atr_14', '>', 3.738183617591858),
        ('dist_pdl_atr', '>', 3.79175865650177),
        ('dist_pdh_atr', '>', -2.9352803230285645),
        ('dist_pdh_atr', '>', -1.4767688512802124),
        ('atr_14', '<=', 10.58998966217041),
        ('dist_pdh_atr', '<=', -1.0095460414886475),
        ('range_pos_50', '<=', 0.9304640293121338),
        ('dist_high20_atr', '<=', -1.0235227346420288),
        ('dist_pdh_atr', '<=', -1.1842433214187622),
        ('dist_high20_atr', '<=', -1.2625556588172913),
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

class V3ShortS8T20_79:
    name = 'V3_SHORT_S8T20_64'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 8.0
    max_hold_bars = 40
    win_rate = 0.574
    profit_factor = 2.2
    tier = 'B'
    constraints = [
        ('atr_14', '>', 3.738183617591858),
        ('dist_pdl_atr', '>', 3.79175865650177),
        ('dist_pdh_atr', '>', -2.9352803230285645),
        ('dist_pdh_atr', '<=', -1.4767688512802124),
        ('range_pos_200', '<=', 0.9378756284713745),
        ('dist_pdh_atr', '>', -2.1951656341552734),
        ('atr_5', '<=', 7.347018003463745),
        ('range_pos_50', '<=', 0.8615493178367615),
        ('dist_vwap_atr', '>', 2.926212430000305),
        ('ny_minute', '>', 26.5),
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

class V3ShortS8T20_80:
    name = 'V3_SHORT_S8T20_65'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 8.0
    max_hold_bars = 40
    win_rate = 0.637
    profit_factor = 2.94
    tier = 'B'
    constraints = [
        ('atr_14', '>', 3.738183617591858),
        ('dist_pdl_atr', '>', 3.79175865650177),
        ('dist_pdh_atr', '>', -2.9352803230285645),
        ('dist_pdh_atr', '<=', -1.4767688512802124),
        ('range_pos_200', '<=', 0.9378756284713745),
        ('dist_pdh_atr', '>', -2.1951656341552734),
        ('atr_5', '<=', 7.347018003463745),
        ('range_pos_50', '<=', 0.8615493178367615),
        ('dist_vwap_atr', '>', 2.926212430000305),
        ('ny_minute', '<=', 26.5),
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

class V3ShortS10T25_81:
    name = 'V3_SHORT_S10T25_67'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 10.0
    max_hold_bars = 50
    win_rate = 0.526
    profit_factor = 2.02
    tier = 'B'
    constraints = [
        ('atr_14', '>', 3.984411358833313),
        ('dist_pdl_atr', '>', 3.7716599702835083),
        ('dist_pdh_atr', '>', -2.9352803230285645),
        ('dist_pdh_atr', '>', -1.4767142534255981),
        ('atr_14', '>', 10.997020244598389),
        ('dist_pdh_atr', '>', -0.8976136445999146),
        ('atr_14', '<=', 15.118744373321533),
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

class V3ShortS10T25_82:
    name = 'V3_SHORT_S10T25_68'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 10.0
    max_hold_bars = 50
    win_rate = 0.5760000000000001
    profit_factor = 2.29
    tier = 'B'
    constraints = [
        ('atr_14', '>', 3.984411358833313),
        ('dist_pdl_atr', '>', 3.7716599702835083),
        ('dist_pdh_atr', '>', -2.9352803230285645),
        ('dist_pdh_atr', '<=', -1.4767142534255981),
        ('range_pos_200', '<=', 0.9428897500038147),
        ('dist_pdh_atr', '>', -2.1951656341552734),
        ('atr_5', '<=', 8.399064064025879),
        ('is_close_30min', '<=', 0.5),
        ('rsi_14', '<=', 56.91695022583008),
        ('dist_high20_atr', '>', -1.8504980206489563),
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

class V3ShortS10T25_83:
    name = 'V3_SHORT_S10T25_69'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 10.0
    max_hold_bars = 50
    win_rate = 0.65
    profit_factor = 3.23
    tier = 'B'
    constraints = [
        ('atr_14', '>', 3.984411358833313),
        ('dist_pdl_atr', '>', 3.7716599702835083),
        ('dist_pdh_atr', '>', -2.9352803230285645),
        ('dist_pdh_atr', '>', -1.4767142534255981),
        ('atr_14', '<=', 10.997020244598389),
        ('dist_pdh_atr', '>', -1.1820775866508484),
        ('atr_14', '>', 5.056535482406616),
        ('dist_pdh_atr', '<=', -0.974441647529602),
        ('range_pos_200', '<=', 0.9465519785881042),
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

class V3ShortS12T30_84:
    name = 'V3_SHORT_S12T30_72'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 12.0
    max_hold_bars = 60
    win_rate = 0.956
    profit_factor = 41.83
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.707773685455322),
        ('dist_pdl_atr', '>', 3.98053240776062),
        ('dist_pdh_atr', '>', -2.6508188247680664),
        ('dist_pdh_atr', '>', -1.7330909371376038),
        ('dist_pdh_atr', '>', -1.1414191722869873),
        ('atr_14', '<=', 17.353757858276367),
        ('atr_14', '>', 5.3874804973602295),
        ('dist_pdh_atr', '>', -0.9055254459381104),
        ('ny_hour', '<=', 14.5),
        ('rsi_5', '>', 72.3100814819336),
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

class V3ShortS12T30_85:
    name = 'V3_SHORT_S12T30_73'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 12.0
    max_hold_bars = 60
    win_rate = 0.972
    profit_factor = 64.84
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.707773685455322),
        ('dist_pdl_atr', '>', 3.98053240776062),
        ('dist_pdh_atr', '>', -2.6508188247680664),
        ('dist_pdh_atr', '>', -1.7330909371376038),
        ('dist_pdh_atr', '>', -1.1414191722869873),
        ('atr_14', '<=', 17.353757858276367),
        ('atr_14', '>', 5.3874804973602295),
        ('dist_pdh_atr', '>', -0.9055254459381104),
        ('ny_hour', '<=', 14.5),
        ('rsi_5', '<=', 72.3100814819336),
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

class V3ShortS12T30_86:
    name = 'V3_SHORT_S12T30_74'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 12.0
    max_hold_bars = 60
    win_rate = 0.7609999999999999
    profit_factor = 5.65
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.707773685455322),
        ('dist_pdl_atr', '>', 3.98053240776062),
        ('dist_pdh_atr', '>', -2.6508188247680664),
        ('dist_pdh_atr', '>', -1.7330909371376038),
        ('dist_pdh_atr', '<=', -1.1414191722869873),
        ('range_pos_50', '<=', 0.9179277420043945),
        ('atr_14', '<=', 15.259057998657227),
        ('is_close_30min', '<=', 0.5),
        ('dist_eq50_atr', '>', 2.47543728351593),
        ('dist_high20_atr', '<=', -1.1545483469963074),
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

class V3ShortS12T30_87:
    name = 'V3_SHORT_S12T30_75'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 12.0
    max_hold_bars = 60
    win_rate = 0.475
    profit_factor = 1.58
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.707773685455322),
        ('dist_pdl_atr', '>', 3.98053240776062),
        ('dist_pdh_atr', '>', -2.6508188247680664),
        ('dist_pdh_atr', '<=', -1.7330909371376038),
        ('range_pos_50', '<=', 0.8743587136268616),
        ('atr_14', '<=', 15.391629219055176),
        ('is_close_30min', '<=', 0.5),
        ('dist_pdh_atr', '<=', -1.9702615141868591),
        ('range_pos_50', '<=', 0.8200254738330841),
        ('autocorr_5', '>', -0.23671473562717438),
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

class V3LongS8T16_88:
    name = 'V3_LONG_S8T16_65'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 8.0
    max_hold_bars = 25
    win_rate = 0.6782608695652174
    profit_factor = 2.4201348747591522
    tier = 'B'
    constraints = [
        ('atr_14', '>', 2.657066583633423),
        ('atr_5', '>', 4.2001025676727295),
        ('dist_pdh_atr', '<=', -3.8525466918945312),
        ('dist_pdl_atr', '<=', 2.6280089616775513),
        ('dist_pdl_atr', '<=', 1.6015412211418152),
        ('dist_pdl_atr', '<=', 1.08460134267807),
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

class V3LongS10T20_89:
    name = 'V3_LONG_S10T20_66'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    win_rate = 0.7085781433607521
    profit_factor = 2.9749562171628723
    tier = 'B'
    constraints = [
        ('atr_14', '>', 2.911348342895508),
        ('atr_5', '>', 4.364060163497925),
        ('dist_pdh_atr', '<=', -4.190554618835449),
        ('dist_pdl_atr', '<=', 3.250853419303894),
        ('dist_pdl_atr', '<=', 1.8944806456565857),
        ('dist_pdh_atr', '<=', -14.648489952087402),
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

class V3ShortS15T30_90:
    name = 'V3_SHORT_S15T30_77'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.6446886446886447
    profit_factor = 2.910761154855643
    tier = 'B'
    constraints = [
        ('atr_5', '>', 3.2175403833389282),
        ('dist_pdl_atr', '>', 5.156219720840454),
        ('atr_5', '>', 4.80181097984314),
        ('atr_14', '>', 6.079191446304321),
        ('dist_vwap_atr', '<=', -6.007394313812256),
        ('dist_pdl_atr', '>', 14.12391471862793),
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

class V3ShortS12T24_91:
    name = 'V3_SHORT_S12T24_78'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    win_rate = 0.5263157894736842
    profit_factor = 1.665828724652254
    tier = 'B'
    constraints = [
        ('atr_14', '>', 2.705695867538452),
        ('dist_pdl_atr', '>', 4.913482666015625),
        ('atr_5', '>', 4.062073230743408),
        ('atr_5', '>', 5.5419700145721436),
        ('range_pos_200', '<=', 0.2463163584470749),
        ('dist_pdl_atr', '>', 17.19609832763672),
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

class V3LongS20T40_92:
    name = 'V3_LONG_S20T40_67'
    side = 'LONG'
    target_pts = 40.0
    stop_pts = 20.0
    max_hold_bars = 60
    win_rate = 0.6477732793522267
    profit_factor = 3.085207396301849
    tier = 'B'
    constraints = [
        ('atr_14', '>', 3.48638379573822),
        ('atr_14', '>', 4.946934938430786),
        ('dist_pdh_atr', '<=', -3.9312071800231934),
        ('dist_pdh_atr', '<=', -8.324272632598877),
        ('atr_14', '>', 5.666432619094849),
        ('range_pos_200', '<=', 0.8657626509666443),
        ('dist_vwap_atr', '>', -4.426287651062012),
        ('atr_50', '>', 8.448511600494385),
        ('dist_pdl_atr', '<=', 9.703555583953857),
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

class V3ShortS8T16_93:
    name = 'V3_SHORT_S8T16_79'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 8.0
    max_hold_bars = 25
    win_rate = 0.5663716814159292
    profit_factor = 1.692648814600034
    tier = 'B'
    constraints = [
        ('atr_14', '>', 2.705695867538452),
        ('dist_pdl_atr', '>', 3.517611265182495),
        ('atr_5', '>', 4.065537929534912),
        ('atr_14', '>', 4.550705909729004),
        ('dist_pdh_atr', '>', -8.531864643096924),
        ('dist_pdl_atr', '>', 4.7422730922698975),
        ('dist_pdh_atr', '>', -1.8382608294487),
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

class V3ShortS10T20_94:
    name = 'V3_SHORT_S10T20_82'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    win_rate = 0.601123595505618
    profit_factor = 1.9920175301299108
    tier = 'B'
    constraints = [
        ('atr_14', '>', 2.7137562036514282),
        ('dist_pdl_atr', '>', 4.566998481750488),
        ('atr_5', '>', 4.065537929534912),
        ('atr_5', '>', 5.493957996368408),
        ('range_pos_50', '>', 0.41704143583774567),
        ('dist_pdh_atr', '>', -6.519273281097412),
        ('atr_14', '<=', 11.065822124481201),
        ('dist_pdh_atr', '>', -2.265183687210083),
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

class V3LongS8T16_95:
    name = 'V3_LONG_S8T16_68'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 8.0
    max_hold_bars = 25
    win_rate = 0.48519362186788156
    profit_factor = 1.2112430882654106
    tier = 'B'
    constraints = [
        ('atr_14', '>', 2.657066583633423),
        ('atr_5', '>', 4.2001025676727295),
        ('dist_pdh_atr', '<=', -3.8525466918945312),
        ('dist_pdl_atr', '<=', 2.6280089616775513),
        ('dist_pdl_atr', '>', 1.6015412211418152),
        ('range_pos_200', '>', 0.09877531602978706),
        ('atr_50', '>', 4.632683038711548),
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

class V3LongS8T16_96:
    name = 'V3_LONG_S8T16_70'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 8.0
    max_hold_bars = 25
    win_rate = 0.564935064935065
    profit_factor = 1.4471592930850432
    tier = 'B'
    constraints = [
        ('atr_14', '>', 2.657066583633423),
        ('atr_5', '>', 4.2001025676727295),
        ('dist_pdh_atr', '<=', -3.8525466918945312),
        ('dist_pdl_atr', '<=', 2.6280089616775513),
        ('dist_pdl_atr', '<=', 1.6015412211418152),
        ('dist_pdl_atr', '>', 1.08460134267807),
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

class V3ShortS12T24_97:
    name = 'V3_SHORT_S12T24_83'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    win_rate = 0.6595744680851063
    profit_factor = 2.6549067940224926
    tier = 'B'
    constraints = [
        ('atr_14', '>', 2.705695867538452),
        ('dist_pdl_atr', '>', 4.913482666015625),
        ('atr_5', '>', 4.062073230743408),
        ('atr_5', '>', 5.5419700145721436),
        ('range_pos_200', '>', 0.2463163584470749),
        ('dist_pdh_atr', '>', -7.356637477874756),
        ('dist_pdh_atr', '>', -2.2013434171676636),
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

class V3ShortS8T16_98:
    name = 'V3_SHORT_S8T16_84'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 8.0
    max_hold_bars = 25
    win_rate = 0.738255033557047
    profit_factor = 3.142366531376834
    tier = 'B'
    constraints = [
        ('atr_14', '>', 2.705695867538452),
        ('dist_pdl_atr', '>', 3.517611265182495),
        ('atr_5', '<=', 4.065537929534912),
        ('dist_pdl_atr', '>', 5.017570734024048),
        ('atr_50', '>', 3.391430377960205),
        ('range_pos_200', '<=', 0.23551778495311737),
        ('autocorr_20', '>', -0.14501014351844788),
        ('rsi_14', '>', 36.976829528808594),
        ('dist_vwap_atr', '<=', -6.852686643600464),
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

class V3ShortS8T16_99:
    name = 'V3_SHORT_S8T16_85'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 8.0
    max_hold_bars = 25
    win_rate = 0.6746666666666666
    profit_factor = 2.480836768972361
    tier = 'B'
    constraints = [
        ('atr_5', '>', 2.349377751350403),
        ('dist_pdl_atr', '>', 4.283675670623779),
        ('atr_5', '>', 2.983413338661194),
        ('dist_pdl_atr', '>', 9.800002098083496),
        ('atr_14', '>', 3.4468525648117065),
        ('hurst_proxy_50', '>', 1.917451798915863),
        ('atr_50', '<=', 3.6668813228607178),
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

class V3LongS10T20_100:
    name = 'V3_LONG_S10T20_72'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    win_rate = 0.463768115942029
    profit_factor = 1.1643658525324354
    tier = 'B'
    constraints = [
        ('atr_5', '>', 2.1994292736053467),
        ('atr_5', '>', 3.5077855587005615),
        ('dist_pdh_atr', '<=', -2.3043220043182373),
        ('atr_14', '>', 4.4609293937683105),
        ('atr_50', '>', 4.383905649185181),
        ('range_pos_200', '<=', 0.47427016496658325),
        ('dist_pdh_atr', '<=', -19.861943244934082),
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

class V3LongS15T30_101:
    name = 'V3_LONG_S15T30_73'
    side = 'LONG'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.4702702702702703
    profit_factor = 1.3955249309052364
    tier = 'B'
    constraints = [
        ('atr_14', '>', 2.3438990116119385),
        ('atr_50', '>', 3.5585020780563354),
        ('atr_50', '>', 4.7575037479400635),
        ('ny_hour', '<=', 13.5),
        ('dist_high20_atr', '<=', -1.0779399275779724),
        ('range_pos_200', '<=', 0.4085654318332672),
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
    V3ShortS10T20_03(),
    V3ShortS20T40_04(),
    V3ShortS10T20_05(),
    V3ShortS20T40_06(),
    V3LongS15T30_07(),
    V3LongS8T16_08(),
    V3ShortS8T16_09(),
    V3ShortS10T20_10(),
    V3ShortS10T20_11(),
    V3LongS12T24_12(),
    V3ShortS12T24_13(),
    V3LongS15T30_14(),
    V3ShortS15T30_15(),
    V3ShortS15T30_16(),
    V3LongS20T50_17(),
    V3LongS15T37_18(),
    V3LongS20T60_19(),
    V3LongS20T50_20(),
    V3LongS15T45_21(),
    V3LongS15T37_22(),
    V3LongS20T60_23(),
    V3LongS20T50_24(),
    V3LongS15T60_25(),
    V3LongS12T36_26(),
    V3LongS20T60_27(),
    V3LongS20T50_28(),
    V3LongS20T50_29(),
    V3LongS20T60_30(),
    V3LongS10T30_31(),
    V3LongS12T30_32(),
    V3LongS15T45_33(),
    V3LongS20T60_34(),
    V3LongS15T37_35(),
    V3LongS20T60_36(),
    V3LongS10T30_37(),
    V3LongS20T60_38(),
    V3LongS12T30_39(),
    V3LongS20T50_40(),
    V3LongS15T45_41(),
    V3LongS10T25_42(),
    V3LongS12T36_43(),
    V3LongS20T60_44(),
    V3LongS10T30_45(),
    V3LongS20T50_46(),
    V3LongS12T30_47(),
    V3LongS15T37_48(),
    V3ShortS8T16_49(),
    V3ShortS8T16_50(),
    V3ShortS10T20_51(),
    V3ShortS10T20_52(),
    V3ShortS10T20_53(),
    V3ShortS10T20_54(),
    V3ShortS10T20_55(),
    V3ShortS10T20_56(),
    V3ShortS10T20_57(),
    V3ShortS12T24_58(),
    V3ShortS12T24_59(),
    V3ShortS12T24_60(),
    V3ShortS12T24_61(),
    V3ShortS12T24_62(),
    V3ShortS12T24_63(),
    V3ShortS12T24_64(),
    V3ShortS12T24_65(),
    V3ShortS12T24_66(),
    V3ShortS12T24_67(),
    V3ShortS12T24_68(),
    V3ShortS15T30_69(),
    V3ShortS15T30_70(),
    V3ShortS15T30_71(),
    V3ShortS15T30_72(),
    V3ShortS15T30_73(),
    V3ShortS15T30_74(),
    V3ShortS8T20_75(),
    V3ShortS8T20_76(),
    V3ShortS8T20_77(),
    V3ShortS8T20_78(),
    V3ShortS8T20_79(),
    V3ShortS8T20_80(),
    V3ShortS10T25_81(),
    V3ShortS10T25_82(),
    V3ShortS10T25_83(),
    V3ShortS12T30_84(),
    V3ShortS12T30_85(),
    V3ShortS12T30_86(),
    V3ShortS12T30_87(),
    V3LongS8T16_88(),
    V3LongS10T20_89(),
    V3ShortS15T30_90(),
    V3ShortS12T24_91(),
    V3LongS20T40_92(),
    V3ShortS8T16_93(),
    V3ShortS10T20_94(),
    V3LongS8T16_95(),
    V3LongS8T16_96(),
    V3ShortS12T24_97(),
    V3ShortS8T16_98(),
    V3ShortS8T16_99(),
    V3LongS10T20_100(),
    V3LongS15T30_101(),
]