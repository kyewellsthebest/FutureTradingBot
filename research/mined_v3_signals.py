"""
Auto-generated v3 pattern Signal classes.
Generated: 2026-04-29T04:04:11.215940+00:00
Survivors: 209  
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
    name = 'V3_SHORT_S10T20_37'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    win_rate = 0.628099173553719
    profit_factor = 1.907370064398621
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

class V3ShortS15T30_04:
    name = 'V3_SHORT_S15T30_57'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.683068017366136
    profit_factor = 3.3604323616115295
    tier = 'A'
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
        ('ny_hour', '<=', 14.5),
        ('dist_low20_atr', '<=', 2.1619025468826294),
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

class V3ShortS18T36_05:
    name = 'V3_SHORT_S18T36_68'
    side = 'SHORT'
    target_pts = 36.0
    stop_pts = 18.0
    max_hold_bars = 55
    win_rate = 0.6038543897216274
    profit_factor = 2.461152780593283
    tier = 'A'
    constraints = [
        ('atr_14', '>', 5.581408977508545),
        ('dist_pdl_atr', '>', 3.9872169494628906),
        ('atr_14', '>', 7.929941177368164),
        ('dist_pdh_atr', '>', -2.655692219734192),
        ('dist_pdh_atr', '>', -1.713789939880371),
        ('dist_pdh_atr', '>', -1.1750937104225159),
        ('atr_14', '<=', 19.746262550354004),
        ('atr_14', '>', 8.843058109283447),
        ('ny_minute', '<=', 50.5),
        ('rsi_14', '<=', 72.57051086425781),
        ('dist_pdh_atr', '>', -0.974441647529602),
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

class V3ShortS18T36_06:
    name = 'V3_SHORT_S18T36_74'
    side = 'SHORT'
    target_pts = 36.0
    stop_pts = 18.0
    max_hold_bars = 55
    win_rate = 0.6366307541625857
    profit_factor = 2.72869715271786
    tier = 'A'
    constraints = [
        ('atr_14', '>', 5.581408977508545),
        ('dist_pdl_atr', '>', 3.9872169494628906),
        ('atr_14', '<=', 7.929941177368164),
        ('dist_pdl_atr', '>', 5.775390386581421),
        ('dist_pdh_atr', '<=', -2.787778377532959),
        ('dist_vwap_atr', '<=', -0.14914241433143616),
        ('dist_pdl_atr', '>', 9.185065269470215),
        ('range_pos_200', '<=', 0.33447687327861786),
        ('dist_pdl_atr', '<=', 13.386116027832031),
        ('atr_50', '<=', 8.104477882385254),
        ('dist_pdh_atr', '<=', -21.469599723815918),
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

class V3ShortS20T40_07:
    name = 'V3_SHORT_S20T40_87'
    side = 'SHORT'
    target_pts = 40.0
    stop_pts = 20.0
    max_hold_bars = 60
    win_rate = 0.6542239685658153
    profit_factor = 3.0606729526031975
    tier = 'A'
    constraints = [
        ('atr_14', '>', 5.728909015655518),
        ('dist_pdl_atr', '>', 3.9872169494628906),
        ('atr_14', '>', 7.928420305252075),
        ('dist_pdh_atr', '>', -2.667119860649109),
        ('dist_pdh_atr', '<=', -1.8222441673278809),
        ('range_pos_50', '<=', 0.8970734179019928),
        ('atr_14', '<=', 15.931173324584961),
        ('ny_hour', '<=', 14.5),
        ('dist_pdh_atr', '<=', -2.197251081466675),
        ('range_pos_50', '<=', 0.8149258196353912),
        ('ny_minute', '>', 17.5),
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

class V3ShortS20T50_08:
    name = 'V3_SHORT_S20T50_141'
    side = 'SHORT'
    target_pts = 50.0
    stop_pts = 20.0
    max_hold_bars = 100
    win_rate = 0.6240503012837306
    profit_factor = 3.25416089040282
    tier = 'A'
    constraints = [
        ('atr_14', '>', 5.154912233352661),
        ('dist_pdl_atr', '>', 5.254091501235962),
        ('range_pos_200', '>', 0.2969357669353485),
        ('dist_pdh_atr', '>', -3.571947455406189),
        ('dist_pdh_atr', '>', -2.1902589797973633),
        ('is_close_30min', '<=', 0.5),
        ('atr_14', '>', 5.876494884490967),
        ('dist_pdh_atr', '>', -1.6187658309936523),
        ('atr_5', '>', 7.632164001464844),
        ('dist_pdh_atr', '>', -1.3092986941337585),
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

class V3ShortS20T40_09:
    name = 'V3_SHORT_S20T40_241'
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

class V3ShortS10T20_10:
    name = 'V3_SHORT_S10T20_245'
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

class V3ShortS20T40_11:
    name = 'V3_SHORT_S20T40_246'
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

class V3LongS15T30_12:
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

class V3LongS8T16_13:
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

class V3ShortS8T16_14:
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

class V3ShortS10T20_15:
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

class V3ShortS10T20_16:
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

class V3LongS12T24_17:
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

class V3ShortS12T24_18:
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

class V3LongS15T30_19:
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

class V3ShortS15T30_20:
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

class V3ShortS15T30_21:
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

class V3LongS20T50_22:
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

class V3LongS15T37_23:
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

class V3LongS20T60_24:
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

class V3LongS20T50_25:
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

class V3LongS15T45_26:
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

class V3LongS15T37_27:
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

class V3LongS20T60_28:
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

class V3LongS20T50_29:
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

class V3LongS15T60_30:
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

class V3LongS12T36_31:
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

class V3LongS20T60_32:
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

class V3LongS20T50_33:
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

class V3LongS20T50_34:
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

class V3LongS20T60_35:
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

class V3LongS10T30_36:
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

class V3LongS12T30_37:
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

class V3LongS15T45_38:
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

class V3LongS20T60_39:
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

class V3LongS15T37_40:
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

class V3LongS20T60_41:
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

class V3LongS10T30_42:
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

class V3LongS20T60_43:
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

class V3LongS12T30_44:
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

class V3LongS20T50_45:
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

class V3LongS15T45_46:
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

class V3LongS10T25_47:
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

class V3LongS12T36_48:
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

class V3LongS20T60_49:
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

class V3LongS10T30_50:
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

class V3LongS20T50_51:
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

class V3LongS12T30_52:
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

class V3LongS15T37_53:
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

class V3ShortS8T16_54:
    name = 'V3_SHORT_S8T16_24'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 8.0
    max_hold_bars = 25
    win_rate = 0.5865845311430528
    profit_factor = 1.8307509411531604
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

class V3ShortS8T16_55:
    name = 'V3_SHORT_S8T16_26'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 8.0
    max_hold_bars = 25
    win_rate = 0.453551912568306
    profit_factor = 1.0362888936140053
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
        ('range_pos_50', '<=', 0.7729895710945129),
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

class V3ShortS8T16_56:
    name = 'V3_SHORT_S8T16_28'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 8.0
    max_hold_bars = 25
    win_rate = 0.5072568940493469
    profit_factor = 1.2765904923120328
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

class V3ShortS10T20_57:
    name = 'V3_SHORT_S10T20_30'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    win_rate = 0.7233115468409586
    profit_factor = 3.831370624795551
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

class V3ShortS10T20_58:
    name = 'V3_SHORT_S10T20_31'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    win_rate = 0.49357072205736896
    profit_factor = 1.3363110408808236
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

class V3ShortS10T20_59:
    name = 'V3_SHORT_S10T20_32'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    win_rate = 0.4961672473867596
    profit_factor = 1.3771375667138657
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

class V3ShortS10T20_60:
    name = 'V3_SHORT_S10T20_33'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    win_rate = 0.5581683168316832
    profit_factor = 1.7321016166281755
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

class V3ShortS10T20_61:
    name = 'V3_SHORT_S10T20_34'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    win_rate = 0.5174291938997821
    profit_factor = 1.4773145591754095
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

class V3ShortS10T20_62:
    name = 'V3_SHORT_S10T20_35'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    win_rate = 0.5023866348448688
    profit_factor = 1.4669646598686967
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

class V3ShortS10T20_63:
    name = 'V3_SHORT_S10T20_36'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    win_rate = 0.45276497695852536
    profit_factor = 1.2034412955465588
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

class V3ShortS12T24_64:
    name = 'V3_SHORT_S12T24_38'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    win_rate = 0.4545766198148783
    profit_factor = 1.2603066010513835
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

class V3ShortS12T24_65:
    name = 'V3_SHORT_S12T24_39'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    win_rate = 0.8802281368821293
    profit_factor = 11.832019405700425
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

class V3ShortS12T24_66:
    name = 'V3_SHORT_S12T24_40'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    win_rate = 0.5117344018317115
    profit_factor = 1.5164459205313914
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

class V3ShortS12T24_67:
    name = 'V3_SHORT_S12T24_41'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    win_rate = 0.605301914580265
    profit_factor = 2.129158910137079
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

class V3ShortS12T24_68:
    name = 'V3_SHORT_S12T24_42'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    win_rate = 0.6955403087478559
    profit_factor = 3.3403012274213433
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

class V3ShortS12T24_69:
    name = 'V3_SHORT_S12T24_43'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    win_rate = 0.4248927038626609
    profit_factor = 1.1194122968462425
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

class V3ShortS12T24_70:
    name = 'V3_SHORT_S12T24_44'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    win_rate = 0.5742821473158551
    profit_factor = 1.9258875356309926
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

class V3ShortS12T24_71:
    name = 'V3_SHORT_S12T24_45'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    win_rate = 0.5038560411311054
    profit_factor = 1.5534974093264249
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

class V3ShortS12T24_72:
    name = 'V3_SHORT_S12T24_46'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    win_rate = 0.46216216216216216
    profit_factor = 1.310641332158886
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

class V3ShortS12T24_73:
    name = 'V3_SHORT_S12T24_47'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    win_rate = 0.41617819460726846
    profit_factor = 1.075940454636894
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
        ('dist_vwap_atr', '>', -1.3870229721069336),
        ('dist_pdh_atr', '>', -4.999247312545776),
        ('dist_high20_atr', '>', -1.5922472476959229),
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

class V3ShortS12T24_74:
    name = 'V3_SHORT_S12T24_48'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    win_rate = 0.5918570009930486
    profit_factor = 1.8705848976310937
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

class V3ShortS12T24_75:
    name = 'V3_SHORT_S12T24_49'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    win_rate = 0.4792176039119804
    profit_factor = 1.2902154510357424
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

class V3ShortS15T30_76:
    name = 'V3_SHORT_S15T30_50'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.5716318785578748
    profit_factor = 2.1171997777601397
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

class V3ShortS15T30_77:
    name = 'V3_SHORT_S15T30_51'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.49234076861058856
    profit_factor = 1.546127183042261
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

class V3ShortS15T30_78:
    name = 'V3_SHORT_S15T30_52'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.5360824742268041
    profit_factor = 1.6172798667009716
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

class V3ShortS15T30_79:
    name = 'V3_SHORT_S15T30_53'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.5571725571725572
    profit_factor = 1.8186415197485308
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

class V3ShortS15T30_80:
    name = 'V3_SHORT_S15T30_54'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.6723095525997581
    profit_factor = 3.3468656365665943
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

class V3ShortS15T30_81:
    name = 'V3_SHORT_S15T30_55'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.6518518518518519
    profit_factor = 2.8484954974741927
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

class V3ShortS15T30_82:
    name = 'V3_SHORT_S15T30_56'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.5395051875498803
    profit_factor = 1.8422607516466485
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.143145322799683),
        ('dist_pdl_atr', '>', 3.7716599702835083),
        ('dist_pdh_atr', '<=', -2.655640721321106),
        ('dist_vwap_atr', '>', 0.3556029945611954),
        ('atr_50', '>', 8.591724395751953),
        ('dist_pdh_atr', '>', -7.252740144729614),
        ('range_pos_200', '<=', 0.87455615401268),
        ('dist_pdh_atr', '>', -4.330903768539429),
        ('ny_hour', '<=', 14.5),
        ('atr_14', '<=', 14.070582389831543),
        ('dist_pdl_atr', '<=', 14.264796257019043),
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

class V3ShortS15T30_83:
    name = 'V3_SHORT_S15T30_58'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.5530054644808743
    profit_factor = 1.9766199292131772
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
        ('autocorr_5', '>', -0.17936037480831146),
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

class V3ShortS15T30_84:
    name = 'V3_SHORT_S15T30_59'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.48027210884353744
    profit_factor = 1.473943417908542
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.143145322799683),
        ('dist_pdl_atr', '>', 3.7716599702835083),
        ('dist_pdh_atr', '<=', -2.655640721321106),
        ('dist_vwap_atr', '<=', 0.3556029945611954),
        ('dist_pdl_atr', '>', 7.351938962936401),
        ('range_pos_200', '<=', 0.2944239675998688),
        ('autocorr_20', '<=', -0.09241769090294838),
        ('atr_50', '>', 6.410015821456909),
        ('atr_50', '<=', 11.715627193450928),
        ('atr_5', '>', 9.918789386749268),
        ('ny_minute', '<=', 29.5),
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

class V3ShortS15T30_85:
    name = 'V3_SHORT_S15T30_60'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.6138461538461538
    profit_factor = 2.4519935133926074
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.143145322799683),
        ('dist_pdl_atr', '>', 3.7716599702835083),
        ('dist_pdh_atr', '<=', -2.655640721321106),
        ('dist_vwap_atr', '<=', 0.3556029945611954),
        ('dist_pdl_atr', '<=', 7.351938962936401),
        ('atr_14', '>', 6.907142639160156),
        ('range_pos_200', '<=', 0.24960873275995255),
        ('dist_pdl_atr', '>', 5.252716779708862),
        ('ny_hour', '>', 14.5),
        ('dist_pdh_atr', '<=', -18.624083518981934),
        ('atr_50', '<=', 10.725876808166504),
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

class V3ShortS15T30_86:
    name = 'V3_SHORT_S15T30_61'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.467687074829932
    profit_factor = 1.4213786035734972
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
        ('dist_pdh_atr', '<=', -5.9243292808532715),
        ('dist_vwap_atr', '<=', -4.734975099563599),
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

class V3ShortS15T30_87:
    name = 'V3_SHORT_S15T30_62'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.5258855585831063
    profit_factor = 1.7627573858549688
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.143145322799683),
        ('dist_pdl_atr', '>', 3.7716599702835083),
        ('dist_pdh_atr', '<=', -2.655640721321106),
        ('dist_vwap_atr', '>', 0.3556029945611954),
        ('atr_50', '>', 8.591724395751953),
        ('dist_pdh_atr', '>', -7.252740144729614),
        ('range_pos_200', '<=', 0.87455615401268),
        ('dist_pdh_atr', '<=', -4.330903768539429),
        ('atr_14', '<=', 8.372665405273438),
        ('autocorr_20', '<=', 0.031943466514348984),
        ('dist_pdl_atr', '>', 18.54210662841797),
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

class V3ShortS15T30_88:
    name = 'V3_SHORT_S15T30_63'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.5280199252801993
    profit_factor = 1.740742133162901
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
        ('ny_hour', '<=', 14.5),
        ('dist_low20_atr', '>', 2.1619025468826294),
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

class V3ShortS15T30_89:
    name = 'V3_SHORT_S15T30_64'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.4693042291950887
    profit_factor = 1.418211091234347
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.143145322799683),
        ('dist_pdl_atr', '>', 3.7716599702835083),
        ('dist_pdh_atr', '<=', -2.655640721321106),
        ('dist_vwap_atr', '<=', 0.3556029945611954),
        ('dist_pdl_atr', '>', 7.351938962936401),
        ('range_pos_200', '>', 0.2944239675998688),
        ('atr_14', '>', 7.192625045776367),
        ('dist_pdl_atr', '<=', 13.259193897247314),
        ('dist_pdh_atr', '>', -38.59642219543457),
        ('dist_vwap_atr', '<=', -1.146170198917389),
        ('dist_pdh_atr', '>', -5.6981987953186035),
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

class V3ShortS15T30_90:
    name = 'V3_SHORT_S15T30_65'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.44554455445544555
    profit_factor = 1.2946428571428572
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.143145322799683),
        ('dist_pdl_atr', '>', 3.7716599702835083),
        ('dist_pdh_atr', '<=', -2.655640721321106),
        ('dist_vwap_atr', '<=', 0.3556029945611954),
        ('dist_pdl_atr', '>', 7.351938962936401),
        ('range_pos_200', '<=', 0.2944239675998688),
        ('autocorr_20', '>', -0.09241769090294838),
        ('dist_pdl_atr', '<=', 15.273326396942139),
        ('dist_vwap_atr', '<=', -6.810972452163696),
        ('ny_hour', '>', 14.5),
        ('atr_50', '>', 10.715264320373535),
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

class V3ShortS15T30_91:
    name = 'V3_SHORT_S15T30_66'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 45
    win_rate = 0.5225225225225225
    profit_factor = 1.6596377275638095
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.143145322799683),
        ('dist_pdl_atr', '>', 3.7716599702835083),
        ('dist_pdh_atr', '>', -2.655640721321106),
        ('dist_pdh_atr', '<=', -1.8196828365325928),
        ('range_pos_50', '<=', 0.8748017847537994),
        ('atr_50', '>', 6.930222988128662),
        ('atr_14', '<=', 15.637444019317627),
        ('dist_pdh_atr', '>', -2.200629472732544),
        ('vol_ratio_30', '>', 1.0613701343536377),
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

class V3ShortS18T36_92:
    name = 'V3_SHORT_S18T36_67'
    side = 'SHORT'
    target_pts = 36.0
    stop_pts = 18.0
    max_hold_bars = 55
    win_rate = 0.47058262155842917
    profit_factor = 1.4626369305944693
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.581408977508545),
        ('dist_pdl_atr', '>', 3.9872169494628906),
        ('atr_14', '>', 7.929941177368164),
        ('dist_pdh_atr', '<=', -2.655692219734192),
        ('range_pos_200', '<=', 0.42825479805469513),
        ('dist_pdl_atr', '>', 7.225177526473999),
        ('dist_vwap_atr', '<=', 0.8993880748748779),
        ('dist_pdl_atr', '>', 10.045464515686035),
        ('atr_50', '<=', 16.655037879943848),
        ('dist_vwap_atr', '<=', -1.8693664073944092),
        ('dist_eq50_atr', '<=', -0.7844555675983429),
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

class V3ShortS18T36_93:
    name = 'V3_SHORT_S18T36_69'
    side = 'SHORT'
    target_pts = 36.0
    stop_pts = 18.0
    max_hold_bars = 55
    win_rate = 0.8260135135135135
    profit_factor = 8.5402635431918
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.581408977508545),
        ('dist_pdl_atr', '>', 3.9872169494628906),
        ('atr_14', '>', 7.929941177368164),
        ('dist_pdh_atr', '>', -2.655692219734192),
        ('dist_pdh_atr', '>', -1.713789939880371),
        ('dist_pdh_atr', '>', -1.1750937104225159),
        ('atr_14', '<=', 19.746262550354004),
        ('atr_14', '>', 8.843058109283447),
        ('ny_minute', '<=', 50.5),
        ('rsi_14', '<=', 72.57051086425781),
        ('dist_pdh_atr', '<=', -0.974441647529602),
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

class V3ShortS18T36_94:
    name = 'V3_SHORT_S18T36_70'
    side = 'SHORT'
    target_pts = 36.0
    stop_pts = 18.0
    max_hold_bars = 55
    win_rate = 0.7959183673469388
    profit_factor = 6.6876524252551715
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.581408977508545),
        ('dist_pdl_atr', '>', 3.9872169494628906),
        ('atr_14', '>', 7.929941177368164),
        ('dist_pdh_atr', '>', -2.655692219734192),
        ('dist_pdh_atr', '>', -1.713789939880371),
        ('dist_pdh_atr', '<=', -1.1750937104225159),
        ('ret_10', '<=', 52.25),
        ('dist_high20_atr', '<=', -1.2345865964889526),
        ('rsi_2', '>', 25.22310447692871),
        ('dist_pdh_atr', '>', -1.5588994026184082),
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

class V3ShortS18T36_95:
    name = 'V3_SHORT_S18T36_71'
    side = 'SHORT'
    target_pts = 36.0
    stop_pts = 18.0
    max_hold_bars = 55
    win_rate = 0.5570503238664674
    profit_factor = 1.9594525116376016
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.581408977508545),
        ('dist_pdl_atr', '>', 3.9872169494628906),
        ('atr_14', '>', 7.929941177368164),
        ('dist_pdh_atr', '>', -2.655692219734192),
        ('dist_pdh_atr', '<=', -1.713789939880371),
        ('range_pos_50', '<=', 0.8985439240932465),
        ('atr_14', '<=', 16.089539527893066),
        ('dist_pdh_atr', '<=', -2.197251081466675),
        ('range_pos_50', '<=', 0.8646128475666046),
        ('autocorr_20', '>', -0.1625487059354782),
        ('atr_50', '>', 7.577397108078003),
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

class V3ShortS18T36_96:
    name = 'V3_SHORT_S18T36_72'
    side = 'SHORT'
    target_pts = 36.0
    stop_pts = 18.0
    max_hold_bars = 55
    win_rate = 0.9502487562189055
    profit_factor = 115.25137614678899
    tier = 'B'
    constraints = [
        ('atr_14', '<=', 5.581408977508545),
        ('atr_14', '>', 3.906293511390686),
        ('dist_pdl_atr', '>', 8.029402732849121),
        ('range_pos_200', '>', 0.2872450202703476),
        ('dist_pdh_atr', '>', -3.9582806825637817),
        ('dist_pdh_atr', '>', -2.749853730201721),
        ('sigma_ratio_5_15', '<=', 2.325861096382141),
        ('dist_pdl_atr', '>', 13.11818552017212),
        ('dist_vwap_atr', '<=', 7.844374418258667),
        ('dist_pdl_atr', '>', 19.19728660583496),
        ('range_expansion_5', '>', 0.846703827381134),
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

class V3ShortS18T36_97:
    name = 'V3_SHORT_S18T36_73'
    side = 'SHORT'
    target_pts = 36.0
    stop_pts = 18.0
    max_hold_bars = 55
    win_rate = 0.9500734214390602
    profit_factor = 84.14981729598051
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.581408977508545),
        ('dist_pdl_atr', '>', 3.9872169494628906),
        ('atr_14', '<=', 7.929941177368164),
        ('dist_pdl_atr', '>', 5.775390386581421),
        ('dist_pdh_atr', '>', -2.787778377532959),
        ('is_close_30min', '<=', 0.5),
        ('dist_pdh_atr', '>', -2.0667593479156494),
        ('atr_14', '>', 6.134970188140869),
        ('dist_vwap_atr', '<=', 10.870199203491211),
        ('ny_hour', '>', 10.5),
        ('sigma_ratio_5_15', '>', 1.118834137916565),
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

class V3ShortS18T36_98:
    name = 'V3_SHORT_S18T36_75'
    side = 'SHORT'
    target_pts = 36.0
    stop_pts = 18.0
    max_hold_bars = 55
    win_rate = 0.46116504854368934
    profit_factor = 1.4215286715286715
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.581408977508545),
        ('dist_pdl_atr', '>', 3.9872169494628906),
        ('atr_14', '>', 7.929941177368164),
        ('dist_pdh_atr', '>', -2.655692219734192),
        ('dist_pdh_atr', '<=', -1.713789939880371),
        ('range_pos_50', '<=', 0.8985439240932465),
        ('atr_14', '>', 16.089539527893066),
        ('dist_eq50_atr', '<=', 1.2795555591583252),
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

class V3ShortS18T36_99:
    name = 'V3_SHORT_S18T36_76'
    side = 'SHORT'
    target_pts = 36.0
    stop_pts = 18.0
    max_hold_bars = 55
    win_rate = 0.7041420118343196
    profit_factor = 3.593367291644088
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.581408977508545),
        ('dist_pdl_atr', '>', 3.9872169494628906),
        ('atr_14', '<=', 7.929941177368164),
        ('dist_pdl_atr', '>', 5.775390386581421),
        ('dist_pdh_atr', '>', -2.787778377532959),
        ('is_close_30min', '<=', 0.5),
        ('dist_pdh_atr', '<=', -2.0667593479156494),
        ('range_pos_50', '<=', 0.8550179600715637),
        ('dist_eq50_atr', '>', 1.2185997366905212),
        ('hurst_proxy_50', '>', 1.5634533166885376),
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

class V3ShortS20T40_100:
    name = 'V3_SHORT_S20T40_77'
    side = 'SHORT'
    target_pts = 40.0
    stop_pts = 20.0
    max_hold_bars = 60
    win_rate = 0.47241361173933627
    profit_factor = 1.4927974805476993
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.728909015655518),
        ('dist_pdl_atr', '>', 3.9872169494628906),
        ('atr_14', '>', 7.928420305252075),
        ('dist_pdh_atr', '<=', -2.667119860649109),
        ('range_pos_200', '<=', 0.39347507059574127),
        ('dist_pdl_atr', '>', 6.005349636077881),
        ('dist_vwap_atr', '<=', 0.5528046786785126),
        ('dist_pdl_atr', '>', 10.017857551574707),
        ('atr_50', '<=', 14.74931812286377),
        ('dist_vwap_atr', '<=', -1.8359166979789734),
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
        sign = 1 if 'SHORT' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3ShortS20T40_101:
    name = 'V3_SHORT_S20T40_78'
    side = 'SHORT'
    target_pts = 40.0
    stop_pts = 20.0
    max_hold_bars = 60
    win_rate = 0.5192401363857769
    profit_factor = 1.806278326770191
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.728909015655518),
        ('dist_pdl_atr', '>', 3.9872169494628906),
        ('atr_14', '>', 7.928420305252075),
        ('dist_pdh_atr', '<=', -2.667119860649109),
        ('range_pos_200', '<=', 0.39347507059574127),
        ('dist_pdl_atr', '>', 6.005349636077881),
        ('dist_vwap_atr', '<=', 0.5528046786785126),
        ('dist_pdl_atr', '>', 10.017857551574707),
        ('atr_50', '<=', 14.74931812286377),
        ('dist_vwap_atr', '<=', -1.8359166979789734),
        ('ny_hour', '>', 13.5),
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

class V3ShortS20T40_102:
    name = 'V3_SHORT_S20T40_79'
    side = 'SHORT'
    target_pts = 40.0
    stop_pts = 20.0
    max_hold_bars = 60
    win_rate = 0.7730061349693251
    profit_factor = 5.867510571695315
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.728909015655518),
        ('dist_pdl_atr', '>', 3.9872169494628906),
        ('atr_14', '>', 7.928420305252075),
        ('dist_pdh_atr', '>', -2.667119860649109),
        ('dist_pdh_atr', '>', -1.8222441673278809),
        ('dist_pdh_atr', '<=', -1.1657680869102478),
        ('ret_10', '<=', 53.625),
        ('is_close_30min', '<=', 0.5),
        ('range_pos_50', '<=', 0.908476322889328),
        ('atr_14', '<=', 16.71017360687256),
        ('atr_14', '>', 8.780160427093506),
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

class V3ShortS20T40_103:
    name = 'V3_SHORT_S20T40_80'
    side = 'SHORT'
    target_pts = 40.0
    stop_pts = 20.0
    max_hold_bars = 60
    win_rate = 0.480881899475794
    profit_factor = 1.5369913344207529
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.728909015655518),
        ('dist_pdl_atr', '>', 3.9872169494628906),
        ('atr_14', '>', 7.928420305252075),
        ('dist_pdh_atr', '<=', -2.667119860649109),
        ('range_pos_200', '<=', 0.39347507059574127),
        ('dist_pdl_atr', '>', 6.005349636077881),
        ('dist_vwap_atr', '<=', 0.5528046786785126),
        ('dist_pdl_atr', '>', 10.017857551574707),
        ('atr_50', '<=', 14.74931812286377),
        ('dist_vwap_atr', '>', -1.8359166979789734),
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

class V3ShortS20T40_104:
    name = 'V3_SHORT_S20T40_81'
    side = 'SHORT'
    target_pts = 40.0
    stop_pts = 20.0
    max_hold_bars = 60
    win_rate = 0.9739130434782609
    profit_factor = 62.51122375090514
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.728909015655518),
        ('dist_pdl_atr', '>', 3.9872169494628906),
        ('atr_14', '>', 7.928420305252075),
        ('dist_pdh_atr', '>', -2.667119860649109),
        ('dist_pdh_atr', '>', -1.8222441673278809),
        ('dist_pdh_atr', '>', -1.1657680869102478),
        ('atr_14', '>', 8.843058109283447),
        ('atr_14', '<=', 20.550713539123535),
        ('atr_14', '>', 10.099431991577148),
        ('dist_vwap_atr', '<=', 4.301300048828125),
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

class V3ShortS20T40_105:
    name = 'V3_SHORT_S20T40_82'
    side = 'SHORT'
    target_pts = 40.0
    stop_pts = 20.0
    max_hold_bars = 60
    win_rate = 0.9930434782608696
    profit_factor = 393.8532110091743
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.728909015655518),
        ('dist_pdl_atr', '>', 3.9872169494628906),
        ('atr_14', '>', 7.928420305252075),
        ('dist_pdh_atr', '>', -2.667119860649109),
        ('dist_pdh_atr', '>', -1.8222441673278809),
        ('dist_pdh_atr', '>', -1.1657680869102478),
        ('atr_14', '>', 8.843058109283447),
        ('atr_14', '<=', 20.550713539123535),
        ('atr_14', '>', 10.099431991577148),
        ('dist_vwap_atr', '>', 4.301300048828125),
        ('dist_pdh_atr', '>', -0.9074452519416809),
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

class V3ShortS20T40_106:
    name = 'V3_SHORT_S20T40_83'
    side = 'SHORT'
    target_pts = 40.0
    stop_pts = 20.0
    max_hold_bars = 60
    win_rate = 0.9642857142857143
    profit_factor = 168.38291139240508
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.728909015655518),
        ('dist_pdl_atr', '>', 3.9872169494628906),
        ('atr_14', '<=', 7.928420305252075),
        ('dist_pdl_atr', '>', 6.527170896530151),
        ('dist_vwap_atr', '>', -1.1900330781936646),
        ('dist_pdh_atr', '>', -5.155292987823486),
        ('dist_pdh_atr', '>', -2.79539954662323),
        ('is_close_30min', '<=', 0.5),
        ('dist_pdh_atr', '>', -2.088468074798584),
        ('dist_vwap_atr', '>', 10.870199203491211),
        ('atr_50', '>', 6.475810527801514),
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

class V3ShortS20T40_107:
    name = 'V3_SHORT_S20T40_84'
    side = 'SHORT'
    target_pts = 40.0
    stop_pts = 20.0
    max_hold_bars = 60
    win_rate = 0.49541620828749544
    profit_factor = 1.6236604479096226
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.728909015655518),
        ('dist_pdl_atr', '>', 3.9872169494628906),
        ('atr_14', '>', 7.928420305252075),
        ('dist_pdh_atr', '<=', -2.667119860649109),
        ('range_pos_200', '<=', 0.39347507059574127),
        ('dist_pdl_atr', '>', 6.005349636077881),
        ('dist_vwap_atr', '<=', 0.5528046786785126),
        ('dist_pdl_atr', '<=', 10.017857551574707),
        ('range_pos_200', '<=', 0.2609298527240753),
        ('dist_vwap_atr', '<=', -3.5280697345733643),
        ('ny_hour', '>', 14.5),
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

class V3ShortS20T40_108:
    name = 'V3_SHORT_S20T40_85'
    side = 'SHORT'
    target_pts = 40.0
    stop_pts = 20.0
    max_hold_bars = 60
    win_rate = 0.5268456375838926
    profit_factor = 1.8459931699877326
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.728909015655518),
        ('dist_pdl_atr', '>', 3.9872169494628906),
        ('atr_14', '>', 7.928420305252075),
        ('dist_pdh_atr', '<=', -2.667119860649109),
        ('range_pos_200', '>', 0.39347507059574127),
        ('dist_pdh_atr', '>', -7.57851243019104),
        ('range_pos_200', '<=', 0.8810376822948456),
        ('dist_pdl_atr', '>', 7.52585244178772),
        ('is_close_30min', '<=', 0.5),
        ('dist_vwap_atr', '<=', 1.7986105680465698),
        ('dist_vwap_atr', '<=', -1.096444845199585),
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

class V3ShortS20T40_109:
    name = 'V3_SHORT_S20T40_86'
    side = 'SHORT'
    target_pts = 40.0
    stop_pts = 20.0
    max_hold_bars = 60
    win_rate = 0.8018691588785046
    profit_factor = 6.655299442163983
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.728909015655518),
        ('dist_pdl_atr', '>', 3.9872169494628906),
        ('atr_14', '>', 7.928420305252075),
        ('dist_pdh_atr', '>', -2.667119860649109),
        ('dist_pdh_atr', '<=', -1.8222441673278809),
        ('range_pos_50', '<=', 0.8970734179019928),
        ('atr_14', '<=', 15.931173324584961),
        ('ny_hour', '<=', 14.5),
        ('dist_pdh_atr', '>', -2.197251081466675),
        ('hurst_proxy_50', '>', 1.3021634221076965),
        ('range_pos_50', '<=', 0.8299549221992493),
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

class V3ShortS20T40_110:
    name = 'V3_SHORT_S20T40_88'
    side = 'SHORT'
    target_pts = 40.0
    stop_pts = 20.0
    max_hold_bars = 60
    win_rate = 0.9751824817518249
    profit_factor = 245.0529411764706
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.728909015655518),
        ('dist_pdl_atr', '>', 3.9872169494628906),
        ('atr_14', '<=', 7.928420305252075),
        ('dist_pdl_atr', '>', 6.527170896530151),
        ('dist_vwap_atr', '>', -1.1900330781936646),
        ('dist_pdh_atr', '>', -5.155292987823486),
        ('dist_pdh_atr', '>', -2.79539954662323),
        ('is_close_30min', '<=', 0.5),
        ('dist_pdh_atr', '>', -2.088468074798584),
        ('dist_vwap_atr', '<=', 10.870199203491211),
        ('ny_hour', '<=', 10.5),
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

class V3ShortS20T40_111:
    name = 'V3_SHORT_S20T40_89'
    side = 'SHORT'
    target_pts = 40.0
    stop_pts = 20.0
    max_hold_bars = 60
    win_rate = 0.8573717948717948
    profit_factor = 12.418426103646834
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.728909015655518),
        ('dist_pdl_atr', '>', 3.9872169494628906),
        ('atr_14', '<=', 7.928420305252075),
        ('dist_pdl_atr', '>', 6.527170896530151),
        ('dist_vwap_atr', '>', -1.1900330781936646),
        ('dist_pdh_atr', '>', -5.155292987823486),
        ('dist_pdh_atr', '>', -2.79539954662323),
        ('is_close_30min', '<=', 0.5),
        ('dist_pdh_atr', '<=', -2.088468074798584),
        ('rsi_5', '<=', 66.09834289550781),
        ('range_pos_50', '<=', 0.7346715927124023),
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

class V3ShortS20T40_112:
    name = 'V3_SHORT_S20T40_90'
    side = 'SHORT'
    target_pts = 40.0
    stop_pts = 20.0
    max_hold_bars = 60
    win_rate = 0.46407185628742514
    profit_factor = 1.465296332280787
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.728909015655518),
        ('dist_pdl_atr', '>', 3.9872169494628906),
        ('atr_14', '>', 7.928420305252075),
        ('dist_pdh_atr', '>', -2.667119860649109),
        ('dist_pdh_atr', '<=', -1.8222441673278809),
        ('range_pos_50', '<=', 0.8970734179019928),
        ('atr_14', '>', 15.931173324584961),
        ('dist_eq50_atr', '<=', 1.380100131034851),
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

class V3ShortS6T15_113:
    name = 'V3_SHORT_S6T15_99'
    side = 'SHORT'
    target_pts = 15.0
    stop_pts = 6.0
    max_hold_bars = 30
    win_rate = 0.4346368715083799
    profit_factor = 1.0809451133344639
    tier = 'B'
    constraints = [
        ('atr_14', '>', 3.532904267311096),
        ('dist_pdh_atr', '>', -2.9571202993392944),
        ('dist_pdh_atr', '>', -1.2831599116325378),
        ('atr_14', '<=', 10.590380191802979),
        ('dist_pdh_atr', '<=', -0.8125062584877014),
        ('range_pos_200', '<=', 0.972691148519516),
        ('ret_5', '<=', 10.625),
        ('dist_pdl_atr', '<=', 33.38383674621582),
        ('dist_pdh_atr', '>', -1.0643170475959778),
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

class V3ShortS8T20_114:
    name = 'V3_SHORT_S8T20_101'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 8.0
    max_hold_bars = 40
    win_rate = 0.9357429718875502
    profit_factor = 26.423291139240508
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

class V3ShortS8T20_115:
    name = 'V3_SHORT_S8T20_103'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 8.0
    max_hold_bars = 40
    win_rate = 0.5598393574297189
    profit_factor = 2.079958463136033
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

class V3ShortS8T20_116:
    name = 'V3_SHORT_S8T20_105'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 8.0
    max_hold_bars = 40
    win_rate = 0.4192163177670424
    profit_factor = 1.2364098470845235
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

class V3ShortS8T20_117:
    name = 'V3_SHORT_S8T20_107'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 8.0
    max_hold_bars = 40
    win_rate = 0.53604568165596
    profit_factor = 1.7693064616057437
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

class V3ShortS8T20_118:
    name = 'V3_SHORT_S8T20_109'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 8.0
    max_hold_bars = 40
    win_rate = 0.5736434108527132
    profit_factor = 2.203824756606398
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

class V3ShortS8T20_119:
    name = 'V3_SHORT_S8T20_110'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 8.0
    max_hold_bars = 40
    win_rate = 0.6370808678500987
    profit_factor = 2.9423489340229594
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

class V3ShortS10T25_120:
    name = 'V3_SHORT_S10T25_116'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 10.0
    max_hold_bars = 50
    win_rate = 0.5255354200988468
    profit_factor = 2.018284719198955
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

class V3ShortS10T25_121:
    name = 'V3_SHORT_S10T25_117'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 10.0
    max_hold_bars = 50
    win_rate = 0.5761455525606469
    profit_factor = 2.2865278868813825
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

class V3ShortS10T25_122:
    name = 'V3_SHORT_S10T25_119'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 10.0
    max_hold_bars = 50
    win_rate = 0.6504424778761062
    profit_factor = 3.2289521884671255
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

class V3ShortS12T30_123:
    name = 'V3_SHORT_S12T30_122'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 12.0
    max_hold_bars = 60
    win_rate = 0.9559965487489215
    profit_factor = 41.82985877605918
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

class V3ShortS12T30_124:
    name = 'V3_SHORT_S12T30_124'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 12.0
    max_hold_bars = 60
    win_rate = 0.9715832205683356
    profit_factor = 64.83980967486121
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

class V3ShortS12T30_125:
    name = 'V3_SHORT_S12T30_125'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 12.0
    max_hold_bars = 60
    win_rate = 0.7605363984674329
    profit_factor = 5.646356663470757
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

class V3ShortS12T30_126:
    name = 'V3_SHORT_S12T30_126'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 12.0
    max_hold_bars = 60
    win_rate = 0.4748876294703928
    profit_factor = 1.575536925941916
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

class V3ShortS12T30_127:
    name = 'V3_SHORT_S12T30_127'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 12.0
    max_hold_bars = 60
    win_rate = 0.9449152542372882
    profit_factor = 32.47375787263821
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.707773685455322),
        ('dist_pdl_atr', '>', 3.98053240776062),
        ('dist_pdh_atr', '>', -2.6508188247680664),
        ('dist_pdh_atr', '>', -1.7330909371376038),
        ('dist_pdh_atr', '>', -1.1414191722869873),
        ('atr_14', '<=', 17.353757858276367),
        ('atr_14', '>', 5.3874804973602295),
        ('dist_pdh_atr', '<=', -0.9055254459381104),
        ('atr_14', '<=', 10.598097801208496),
        ('dist_vwap_atr', '>', 6.956074237823486),
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

class V3ShortS12T30_128:
    name = 'V3_SHORT_S12T30_130'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 12.0
    max_hold_bars = 60
    win_rate = 0.595
    profit_factor = 2.624735597859898
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
        ('dist_eq50_atr', '<=', 2.47543728351593),
        ('dist_pdl_atr', '>', 24.829167366027832),
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

class V3ShortS15T37_129:
    name = 'V3_SHORT_S15T37_131'
    side = 'SHORT'
    target_pts = 37.5
    stop_pts = 15.0
    max_hold_bars = 75
    win_rate = 0.419269202087994
    profit_factor = 1.4274736216845965
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.794657230377197),
        ('dist_pdl_atr', '>', 4.037386655807495),
        ('dist_pdh_atr', '<=', -2.951348662376404),
        ('dist_vwap_atr', '<=', 0.11712724342942238),
        ('dist_pdl_atr', '>', 7.349009275436401),
        ('range_pos_200', '<=', 0.3120967000722885),
        ('dist_pdl_atr', '>', 10.01294755935669),
        ('atr_50', '<=', 16.646315574645996),
        ('dist_vwap_atr', '<=', -1.3222526907920837),
        ('range_pos_50', '<=', 0.5057366490364075),
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

class V3ShortS15T37_130:
    name = 'V3_SHORT_S15T37_132'
    side = 'SHORT'
    target_pts = 37.5
    stop_pts = 15.0
    max_hold_bars = 75
    win_rate = 0.5657060518731989
    profit_factor = 2.5200654358494976
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.794657230377197),
        ('dist_pdl_atr', '>', 4.037386655807495),
        ('dist_pdh_atr', '>', -2.951348662376404),
        ('dist_pdh_atr', '>', -1.8258918523788452),
        ('is_close_30min', '<=', 0.5),
        ('dist_pdh_atr', '>', -1.1802123188972473),
        ('atr_14', '>', 6.464821815490723),
        ('atr_14', '<=', 18.120853424072266),
        ('atr_14', '>', 8.613872051239014),
        ('dist_pdh_atr', '>', -0.9384270012378693),
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

class V3ShortS15T37_131:
    name = 'V3_SHORT_S15T37_133'
    side = 'SHORT'
    target_pts = 37.5
    stop_pts = 15.0
    max_hold_bars = 75
    win_rate = 0.6928297432871053
    profit_factor = 4.377802558985796
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.794657230377197),
        ('dist_pdl_atr', '>', 4.037386655807495),
        ('dist_pdh_atr', '>', -2.951348662376404),
        ('dist_pdh_atr', '>', -1.8258918523788452),
        ('is_close_30min', '<=', 0.5),
        ('dist_pdh_atr', '<=', -1.1802123188972473),
        ('range_pos_50', '<=', 0.9196533262729645),
        ('atr_14', '>', 5.902839660644531),
        ('atr_14', '<=', 12.932372093200684),
        ('range_pos_50', '<=', 0.8981031775474548),
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

class V3ShortS15T37_132:
    name = 'V3_SHORT_S15T37_134'
    side = 'SHORT'
    target_pts = 37.5
    stop_pts = 15.0
    max_hold_bars = 75
    win_rate = 0.7296450939457203
    profit_factor = 5.149902131361461
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.794657230377197),
        ('dist_pdl_atr', '>', 4.037386655807495),
        ('dist_pdh_atr', '>', -2.951348662376404),
        ('dist_pdh_atr', '>', -1.8258918523788452),
        ('is_close_30min', '<=', 0.5),
        ('dist_pdh_atr', '>', -1.1802123188972473),
        ('atr_14', '>', 6.464821815490723),
        ('atr_14', '<=', 18.120853424072266),
        ('atr_14', '>', 8.613872051239014),
        ('dist_pdh_atr', '<=', -0.9384270012378693),
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

class V3ShortS15T37_133:
    name = 'V3_SHORT_S15T37_135'
    side = 'SHORT'
    target_pts = 37.5
    stop_pts = 15.0
    max_hold_bars = 75
    win_rate = 0.49717395855139207
    profit_factor = 1.8397511562921565
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.794657230377197),
        ('dist_pdl_atr', '>', 4.037386655807495),
        ('dist_pdh_atr', '>', -2.951348662376404),
        ('dist_pdh_atr', '<=', -1.8258918523788452),
        ('range_pos_50', '<=', 0.8652164340019226),
        ('is_close_30min', '<=', 0.5),
        ('atr_14', '<=', 15.491820812225342),
        ('atr_14', '>', 5.891156911849976),
        ('range_pos_50', '<=', 0.7674744427204132),
        ('dist_pdh_atr', '<=', -2.1926119327545166),
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

class V3ShortS15T37_134:
    name = 'V3_SHORT_S15T37_136'
    side = 'SHORT'
    target_pts = 37.5
    stop_pts = 15.0
    max_hold_bars = 75
    win_rate = 0.45194456861868576
    profit_factor = 1.443436468113609
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.794657230377197),
        ('dist_pdl_atr', '>', 4.037386655807495),
        ('dist_pdh_atr', '>', -2.951348662376404),
        ('dist_pdh_atr', '>', -1.8258918523788452),
        ('is_close_30min', '<=', 0.5),
        ('dist_pdh_atr', '>', -1.1802123188972473),
        ('atr_14', '>', 6.464821815490723),
        ('atr_14', '<=', 18.120853424072266),
        ('atr_14', '<=', 8.613872051239014),
        ('ny_minute', '>', 28.5),
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

class V3ShortS15T37_135:
    name = 'V3_SHORT_S15T37_137'
    side = 'SHORT'
    target_pts = 37.5
    stop_pts = 15.0
    max_hold_bars = 75
    win_rate = 0.3953488372093023
    profit_factor = 1.3061612809506467
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.794657230377197),
        ('dist_pdl_atr', '>', 4.037386655807495),
        ('dist_pdh_atr', '<=', -2.951348662376404),
        ('dist_vwap_atr', '<=', 0.11712724342942238),
        ('dist_pdl_atr', '>', 7.349009275436401),
        ('range_pos_200', '>', 0.3120967000722885),
        ('atr_14', '>', 6.587737083435059),
        ('dist_pdl_atr', '>', 13.947041034698486),
        ('dist_vwap_atr', '<=', -1.3199810981750488),
        ('dist_pdl_atr', '>', 17.495197296142578),
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

class V3ShortS15T37_136:
    name = 'V3_SHORT_S15T37_138'
    side = 'SHORT'
    target_pts = 37.5
    stop_pts = 15.0
    max_hold_bars = 75
    win_rate = 0.4108241082410824
    profit_factor = 1.3959808879758364
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.794657230377197),
        ('dist_pdl_atr', '>', 4.037386655807495),
        ('dist_pdh_atr', '<=', -2.951348662376404),
        ('dist_vwap_atr', '>', 0.11712724342942238),
        ('atr_50', '>', 8.592048168182373),
        ('dist_pdh_atr', '>', -8.024375438690186),
        ('range_pos_200', '<=', 0.8864372968673706),
        ('dist_pdh_atr', '>', -4.330903768539429),
        ('is_close_30min', '<=', 0.5),
        ('atr_5', '<=', 12.299686908721924),
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

class V3ShortS15T37_137:
    name = 'V3_SHORT_S15T37_139'
    side = 'SHORT'
    target_pts = 37.5
    stop_pts = 15.0
    max_hold_bars = 75
    win_rate = 0.5291616038882139
    profit_factor = 2.2245631696268067
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.794657230377197),
        ('dist_pdl_atr', '>', 4.037386655807495),
        ('dist_pdh_atr', '<=', -2.951348662376404),
        ('dist_vwap_atr', '<=', 0.11712724342942238),
        ('dist_pdl_atr', '>', 7.349009275436401),
        ('range_pos_200', '<=', 0.3120967000722885),
        ('dist_pdl_atr', '<=', 10.01294755935669),
        ('dist_vwap_atr', '<=', -6.836822509765625),
        ('ny_hour', '>', 13.5),
        ('atr_50', '<=', 12.665737628936768),
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

class V3ShortS15T37_138:
    name = 'V3_SHORT_S15T37_140'
    side = 'SHORT'
    target_pts = 37.5
    stop_pts = 15.0
    max_hold_bars = 75
    win_rate = 0.56966618287373
    profit_factor = 2.4554917532070863
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.794657230377197),
        ('dist_pdl_atr', '>', 4.037386655807495),
        ('dist_pdh_atr', '>', -2.951348662376404),
        ('dist_pdh_atr', '<=', -1.8258918523788452),
        ('range_pos_50', '<=', 0.8652164340019226),
        ('is_close_30min', '<=', 0.5),
        ('atr_14', '<=', 15.491820812225342),
        ('atr_14', '>', 5.891156911849976),
        ('range_pos_50', '<=', 0.7674744427204132),
        ('dist_pdh_atr', '>', -2.1926119327545166),
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

class V3ShortS20T50_139:
    name = 'V3_SHORT_S20T50_142'
    side = 'SHORT'
    target_pts = 50.0
    stop_pts = 20.0
    max_hold_bars = 100
    win_rate = 0.45492537313432835
    profit_factor = 1.7280249500771687
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.154912233352661),
        ('dist_pdl_atr', '>', 5.254091501235962),
        ('range_pos_200', '<=', 0.2969357669353485),
        ('dist_pdl_atr', '>', 7.728437185287476),
        ('dist_vwap_atr', '<=', 0.3365478515625),
        ('dist_pdl_atr', '>', 10.045413494110107),
        ('atr_50', '<=', 16.66289710998535),
        ('autocorr_20', '>', -0.09187871962785721),
        ('dow', '>', 1.5),
        ('dist_pdl_atr', '<=', 34.768625259399414),
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

class V3ShortS20T50_140:
    name = 'V3_SHORT_S20T50_143'
    side = 'SHORT'
    target_pts = 50.0
    stop_pts = 20.0
    max_hold_bars = 100
    win_rate = 0.5163087637840975
    profit_factor = 2.217278163295438
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.154912233352661),
        ('dist_pdl_atr', '>', 5.254091501235962),
        ('range_pos_200', '<=', 0.2969357669353485),
        ('dist_pdl_atr', '>', 7.728437185287476),
        ('dist_vwap_atr', '<=', 0.3365478515625),
        ('dist_pdl_atr', '>', 10.045413494110107),
        ('atr_50', '<=', 16.66289710998535),
        ('autocorr_20', '>', -0.09187871962785721),
        ('dow', '<=', 1.5),
        ('dist_pdl_atr', '>', 12.024301052093506),
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

class V3ShortS20T50_141:
    name = 'V3_SHORT_S20T50_144'
    side = 'SHORT'
    target_pts = 50.0
    stop_pts = 20.0
    max_hold_bars = 100
    win_rate = 0.6559633027522935
    profit_factor = 3.6754217947672996
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.154912233352661),
        ('dist_pdl_atr', '>', 5.254091501235962),
        ('range_pos_200', '>', 0.2969357669353485),
        ('dist_pdh_atr', '>', -3.571947455406189),
        ('dist_pdh_atr', '<=', -2.1902589797973633),
        ('is_close_30min', '<=', 0.5),
        ('range_pos_50', '<=', 0.8238489031791687),
        ('dist_pdl_atr', '>', 9.657569885253906),
        ('ny_hour', '<=', 14.5),
        ('dist_pdl_atr', '>', 19.739091873168945),
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

class V3ShortS20T50_142:
    name = 'V3_SHORT_S20T50_145'
    side = 'SHORT'
    target_pts = 50.0
    stop_pts = 20.0
    max_hold_bars = 100
    win_rate = 0.6979338842975207
    profit_factor = 4.616286799620133
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.154912233352661),
        ('dist_pdl_atr', '>', 5.254091501235962),
        ('range_pos_200', '>', 0.2969357669353485),
        ('dist_pdh_atr', '>', -3.571947455406189),
        ('dist_pdh_atr', '>', -2.1902589797973633),
        ('is_close_30min', '<=', 0.5),
        ('atr_14', '>', 5.876494884490967),
        ('dist_pdh_atr', '>', -1.6187658309936523),
        ('atr_5', '>', 7.632164001464844),
        ('dist_pdh_atr', '<=', -1.3092986941337585),
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

class V3ShortS20T50_143:
    name = 'V3_SHORT_S20T50_146'
    side = 'SHORT'
    target_pts = 50.0
    stop_pts = 20.0
    max_hold_bars = 100
    win_rate = 0.427957566805425
    profit_factor = 1.5696123005279934
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.154912233352661),
        ('dist_pdl_atr', '>', 5.254091501235962),
        ('range_pos_200', '<=', 0.2969357669353485),
        ('dist_pdl_atr', '>', 7.728437185287476),
        ('dist_vwap_atr', '<=', 0.3365478515625),
        ('dist_pdl_atr', '>', 10.045413494110107),
        ('atr_50', '<=', 16.66289710998535),
        ('autocorr_20', '<=', -0.09187871962785721),
        ('atr_50', '>', 4.415417194366455),
        ('atr_14', '>', 8.660841464996338),
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

class V3ShortS20T50_144:
    name = 'V3_SHORT_S20T50_147'
    side = 'SHORT'
    target_pts = 50.0
    stop_pts = 20.0
    max_hold_bars = 100
    win_rate = 0.4217762326169406
    profit_factor = 1.5442728641929742
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.154912233352661),
        ('dist_pdl_atr', '>', 5.254091501235962),
        ('range_pos_200', '>', 0.2969357669353485),
        ('dist_pdh_atr', '<=', -3.571947455406189),
        ('atr_50', '>', 8.366023540496826),
        ('range_pos_200', '<=', 0.812441498041153),
        ('dist_pdl_atr', '>', 8.500669479370117),
        ('dist_vwap_atr', '<=', 1.4883148670196533),
        ('dist_pdl_atr', '>', 13.884960651397705),
        ('dist_vwap_atr', '<=', -1.7599976658821106),
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

class V3ShortS20T50_145:
    name = 'V3_SHORT_S20T50_148'
    side = 'SHORT'
    target_pts = 50.0
    stop_pts = 20.0
    max_hold_bars = 100
    win_rate = 0.5757442116868798
    profit_factor = 2.3037939645945844
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.154912233352661),
        ('dist_pdl_atr', '>', 5.254091501235962),
        ('range_pos_200', '>', 0.2969357669353485),
        ('dist_pdh_atr', '>', -3.571947455406189),
        ('dist_pdh_atr', '>', -2.1902589797973633),
        ('is_close_30min', '<=', 0.5),
        ('atr_14', '>', 5.876494884490967),
        ('dist_pdh_atr', '>', -1.6187658309936523),
        ('atr_5', '<=', 7.632164001464844),
        ('dist_pdl_atr', '>', 21.123571395874023),
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

class V3ShortS20T50_146:
    name = 'V3_SHORT_S20T50_149'
    side = 'SHORT'
    target_pts = 50.0
    stop_pts = 20.0
    max_hold_bars = 100
    win_rate = 0.734920634920635
    profit_factor = 5.596363098028572
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.154912233352661),
        ('dist_pdl_atr', '>', 5.254091501235962),
        ('range_pos_200', '>', 0.2969357669353485),
        ('dist_pdh_atr', '>', -3.571947455406189),
        ('dist_pdh_atr', '>', -2.1902589797973633),
        ('is_close_30min', '<=', 0.5),
        ('atr_14', '>', 5.876494884490967),
        ('dist_pdh_atr', '<=', -1.6187658309936523),
        ('dist_high20_atr', '<=', -1.5336377024650574),
        ('dist_pdl_atr', '>', 20.469656944274902),
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

class V3ShortS20T50_147:
    name = 'V3_SHORT_S20T50_150'
    side = 'SHORT'
    target_pts = 50.0
    stop_pts = 20.0
    max_hold_bars = 100
    win_rate = 0.4256357564860005
    profit_factor = 1.5006312542063145
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.154912233352661),
        ('dist_pdl_atr', '>', 5.254091501235962),
        ('range_pos_200', '<=', 0.2969357669353485),
        ('dist_pdl_atr', '>', 7.728437185287476),
        ('dist_vwap_atr', '<=', 0.3365478515625),
        ('dist_pdl_atr', '<=', 10.045413494110107),
        ('atr_14', '>', 6.517788410186768),
        ('dist_vwap_atr', '<=', -1.851383626461029),
        ('atr_50', '<=', 14.514734745025635),
        ('hurst_proxy_50', '>', 1.2947533130645752),
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

class V3ShortS6T18_148:
    name = 'V3_SHORT_S6T18_156'
    side = 'SHORT'
    target_pts = 18.0
    stop_pts = 6.0
    max_hold_bars = 35
    win_rate = 0.4316353887399464
    profit_factor = 1.2755933561918333
    tier = 'B'
    constraints = [
        ('atr_14', '>', 3.5999958515167236),
        ('dist_pdl_atr', '>', 3.7917375564575195),
        ('dist_pdh_atr', '>', -2.9570367336273193),
        ('dist_pdh_atr', '>', -1.2646206617355347),
        ('atr_14', '<=', 10.22855520248413),
        ('dist_pdh_atr', '<=', -0.8125062584877014),
        ('range_pos_200', '<=', 0.9743794798851013),
        ('ret_5', '<=', 10.625),
        ('dist_pdh_atr', '>', -1.0914069414138794),
        ('dist_high20_atr', '<=', -0.8781903684139252),
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

class V3ShortS8T24_149:
    name = 'V3_SHORT_S8T24_162'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 8.0
    max_hold_bars = 45
    win_rate = 0.5714285714285714
    profit_factor = 2.581701415585003
    tier = 'B'
    constraints = [
        ('atr_14', '>', 3.9371087551116943),
        ('dist_pdl_atr', '>', 3.7447850704193115),
        ('dist_pdh_atr', '>', -2.9448471069335938),
        ('dist_pdh_atr', '>', -1.4767142534255981),
        ('dist_pdh_atr', '>', -0.99527308344841),
        ('atr_14', '<=', 17.44008731842041),
        ('dist_pdh_atr', '<=', -0.6917383372783661),
        ('atr_14', '<=', 9.90519666671753),
        ('atr_14', '>', 5.963790655136108),
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

class V3ShortS8T24_150:
    name = 'V3_SHORT_S8T24_164'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 8.0
    max_hold_bars = 45
    win_rate = 0.6635021097046413
    profit_factor = 3.9348282097649188
    tier = 'B'
    constraints = [
        ('atr_14', '>', 3.9371087551116943),
        ('dist_pdl_atr', '>', 3.7447850704193115),
        ('dist_pdh_atr', '>', -2.9448471069335938),
        ('dist_pdh_atr', '>', -1.4767142534255981),
        ('dist_pdh_atr', '>', -0.99527308344841),
        ('atr_14', '<=', 17.44008731842041),
        ('dist_pdh_atr', '>', -0.6917383372783661),
        ('atr_14', '>', 5.785991430282593),
        ('dist_pdh_atr', '<=', -0.505618155002594),
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

class V3ShortS8T24_151:
    name = 'V3_SHORT_S8T24_165'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 8.0
    max_hold_bars = 45
    win_rate = 0.5206839492553779
    profit_factor = 2.0673801668410183
    tier = 'B'
    constraints = [
        ('atr_14', '>', 3.9371087551116943),
        ('dist_pdl_atr', '>', 3.7447850704193115),
        ('dist_pdh_atr', '>', -2.9448471069335938),
        ('dist_pdh_atr', '>', -1.4767142534255981),
        ('dist_pdh_atr', '<=', -0.99527308344841),
        ('range_pos_50', '<=', 0.9256727993488312),
        ('atr_5', '<=', 11.205473899841309),
        ('hurst_proxy_50', '>', 1.1956451535224915),
        ('range_pos_50', '<=', 0.905839741230011),
        ('ny_minute', '>', 18.5),
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

class V3ShortS8T24_152:
    name = 'V3_SHORT_S8T24_167'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 8.0
    max_hold_bars = 45
    win_rate = 0.4786836200448766
    profit_factor = 1.667658862876254
    tier = 'B'
    constraints = [
        ('atr_14', '>', 3.9371087551116943),
        ('dist_pdl_atr', '>', 3.7447850704193115),
        ('dist_pdh_atr', '>', -2.9448471069335938),
        ('dist_pdh_atr', '<=', -1.4767142534255981),
        ('range_pos_200', '<=', 0.937833309173584),
        ('dist_pdh_atr', '>', -2.1951656341552734),
        ('atr_5', '<=', 7.310299396514893),
        ('vol_ratio_60', '<=', 1.0981187224388123),
        ('range_pos_50', '<=', 0.8642899990081787),
        ('sigma_ratio_1_5', '>', 1.2173172235488892),
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

class V3ShortS8T24_153:
    name = 'V3_SHORT_S8T24_168'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 8.0
    max_hold_bars = 45
    win_rate = 0.4347568208778173
    profit_factor = 1.3824610408703322
    tier = 'B'
    constraints = [
        ('atr_14', '>', 3.9371087551116943),
        ('dist_pdl_atr', '>', 3.7447850704193115),
        ('dist_pdh_atr', '>', -2.9448471069335938),
        ('dist_pdh_atr', '<=', -1.4767142534255981),
        ('range_pos_200', '<=', 0.937833309173584),
        ('dist_pdh_atr', '>', -2.1951656341552734),
        ('atr_5', '<=', 7.310299396514893),
        ('vol_ratio_60', '<=', 1.0981187224388123),
        ('range_pos_50', '<=', 0.8642899990081787),
        ('sigma_ratio_1_5', '<=', 1.2173172235488892),
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

class V3ShortS8T24_154:
    name = 'V3_SHORT_S8T24_169'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 8.0
    max_hold_bars = 45
    win_rate = 0.6566637246248896
    profit_factor = 3.192360590147537
    tier = 'B'
    constraints = [
        ('atr_14', '>', 3.9371087551116943),
        ('dist_pdl_atr', '>', 3.7447850704193115),
        ('dist_pdh_atr', '>', -2.9448471069335938),
        ('dist_pdh_atr', '>', -1.4767142534255981),
        ('dist_pdh_atr', '>', -0.99527308344841),
        ('atr_14', '<=', 17.44008731842041),
        ('dist_pdh_atr', '<=', -0.6917383372783661),
        ('atr_14', '<=', 9.90519666671753),
        ('atr_14', '<=', 5.963790655136108),
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

class V3ShortS10T30_155:
    name = 'V3_SHORT_S10T30_171'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 10.0
    max_hold_bars = 60
    win_rate = 0.4820261437908497
    profit_factor = 1.855405255980244
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.7044336795806885),
        ('dist_pdl_atr', '>', 3.7716599702835083),
        ('dist_pdh_atr', '>', -2.8816850185394287),
        ('dist_pdh_atr', '>', -1.66233229637146),
        ('dist_pdh_atr', '>', -1.1706422567367554),
        ('atr_14', '<=', 16.274154663085938),
        ('dist_pdh_atr', '>', -0.9656634628772736),
        ('atr_14', '>', 5.625176906585693),
        ('dist_pdh_atr', '>', -0.6765306293964386),
        ('ret_20', '>', 24.625),
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

class V3ShortS10T30_156:
    name = 'V3_SHORT_S10T30_173'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 10.0
    max_hold_bars = 60
    win_rate = 0.74780526735834
    profit_factor = 6.1729515531126165
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.7044336795806885),
        ('dist_pdl_atr', '>', 3.7716599702835083),
        ('dist_pdh_atr', '>', -2.8816850185394287),
        ('dist_pdh_atr', '>', -1.66233229637146),
        ('dist_pdh_atr', '>', -1.1706422567367554),
        ('atr_14', '<=', 16.274154663085938),
        ('dist_pdh_atr', '>', -0.9656634628772736),
        ('atr_14', '>', 5.625176906585693),
        ('dist_pdh_atr', '<=', -0.6765306293964386),
        ('atr_5', '<=', 9.753874778747559),
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

class V3ShortS10T30_157:
    name = 'V3_SHORT_S10T30_176'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 10.0
    max_hold_bars = 60
    win_rate = 0.6105100463678517
    profit_factor = 3.0935795050209536
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.7044336795806885),
        ('dist_pdl_atr', '>', 3.7716599702835083),
        ('dist_pdh_atr', '>', -2.8816850185394287),
        ('dist_pdh_atr', '>', -1.66233229637146),
        ('dist_pdh_atr', '<=', -1.1706422567367554),
        ('range_pos_50', '<=', 0.9196533262729645),
        ('atr_5', '<=', 15.52524709701538),
        ('hurst_proxy_50', '>', 1.177634835243225),
        ('dist_pdh_atr', '>', -1.3686917424201965),
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

class V3ShortS10T30_158:
    name = 'V3_SHORT_S10T30_177'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 10.0
    max_hold_bars = 60
    win_rate = 0.5935178933153274
    profit_factor = 2.9362129087439963
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.7044336795806885),
        ('dist_pdl_atr', '>', 3.7716599702835083),
        ('dist_pdh_atr', '>', -2.8816850185394287),
        ('dist_pdh_atr', '>', -1.66233229637146),
        ('dist_pdh_atr', '<=', -1.1706422567367554),
        ('range_pos_50', '<=', 0.9196533262729645),
        ('atr_5', '<=', 15.52524709701538),
        ('hurst_proxy_50', '>', 1.177634835243225),
        ('dist_pdh_atr', '<=', -1.3686917424201965),
        ('dist_high20_atr', '<=', -1.3252277970314026),
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

class V3ShortS10T30_159:
    name = 'V3_SHORT_S10T30_178'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 10.0
    max_hold_bars = 60
    win_rate = 0.6538461538461539
    profit_factor = 3.837786518377865
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.7044336795806885),
        ('dist_pdl_atr', '>', 3.7716599702835083),
        ('dist_pdh_atr', '>', -2.8816850185394287),
        ('dist_pdh_atr', '>', -1.66233229637146),
        ('dist_pdh_atr', '>', -1.1706422567367554),
        ('atr_14', '<=', 16.274154663085938),
        ('dist_pdh_atr', '<=', -0.9656634628772736),
        ('atr_14', '<=', 9.827064514160156),
        ('rsi_5', '<=', 69.45834732055664),
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

class V3ShortS12T36_160:
    name = 'V3_SHORT_S12T36_181'
    side = 'SHORT'
    target_pts = 36.0
    stop_pts = 12.0
    max_hold_bars = 75
    win_rate = 0.398803383536208
    profit_factor = 1.421443387123799
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.704147815704346),
        ('dist_pdl_atr', '>', 4.63021183013916),
        ('dist_pdh_atr', '>', -2.8816850185394287),
        ('dist_pdh_atr', '>', -1.7330909371376038),
        ('dist_pdh_atr', '>', -1.123138189315796),
        ('is_close_30min', '<=', 0.5),
        ('atr_14', '<=', 17.353757858276367),
        ('atr_14', '>', 7.1270458698272705),
        ('dist_pdh_atr', '>', -0.8971956074237823),
        ('dist_pdh_atr', '>', -0.7431126832962036),
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

class V3ShortS12T36_161:
    name = 'V3_SHORT_S12T36_184'
    side = 'SHORT'
    target_pts = 36.0
    stop_pts = 12.0
    max_hold_bars = 75
    win_rate = 0.6179966044142614
    profit_factor = 3.542732003144536
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.704147815704346),
        ('dist_pdl_atr', '>', 4.63021183013916),
        ('dist_pdh_atr', '>', -2.8816850185394287),
        ('dist_pdh_atr', '>', -1.7330909371376038),
        ('dist_pdh_atr', '>', -1.123138189315796),
        ('is_close_30min', '<=', 0.5),
        ('atr_14', '<=', 17.353757858276367),
        ('atr_14', '>', 7.1270458698272705),
        ('dist_pdh_atr', '<=', -0.8971956074237823),
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

class V3ShortS12T36_162:
    name = 'V3_SHORT_S12T36_185'
    side = 'SHORT'
    target_pts = 36.0
    stop_pts = 12.0
    max_hold_bars = 75
    win_rate = 0.7716417910447761
    profit_factor = 7.388353813793867
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.704147815704346),
        ('dist_pdl_atr', '>', 4.63021183013916),
        ('dist_pdh_atr', '>', -2.8816850185394287),
        ('dist_pdh_atr', '>', -1.7330909371376038),
        ('dist_pdh_atr', '>', -1.123138189315796),
        ('is_close_30min', '<=', 0.5),
        ('atr_14', '<=', 17.353757858276367),
        ('atr_14', '>', 7.1270458698272705),
        ('dist_pdh_atr', '>', -0.8971956074237823),
        ('dist_pdh_atr', '<=', -0.7431126832962036),
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

class V3ShortS12T36_163:
    name = 'V3_SHORT_S12T36_186'
    side = 'SHORT'
    target_pts = 36.0
    stop_pts = 12.0
    max_hold_bars = 75
    win_rate = 0.6034047919293821
    profit_factor = 3.291814262569679
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.704147815704346),
        ('dist_pdl_atr', '>', 4.63021183013916),
        ('dist_pdh_atr', '>', -2.8816850185394287),
        ('dist_pdh_atr', '>', -1.7330909371376038),
        ('dist_pdh_atr', '<=', -1.123138189315796),
        ('range_pos_50', '<=', 0.9178657829761505),
        ('is_close_30min', '<=', 0.5),
        ('atr_5', '<=', 15.527668952941895),
        ('dist_pdl_atr', '>', 26.162609100341797),
        ('atr_14', '>', 6.1492414474487305),
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

class V3ShortS12T36_164:
    name = 'V3_SHORT_S12T36_188'
    side = 'SHORT'
    target_pts = 36.0
    stop_pts = 12.0
    max_hold_bars = 75
    win_rate = 0.4280587833219412
    profit_factor = 1.5092916875134015
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.704147815704346),
        ('dist_pdl_atr', '>', 4.63021183013916),
        ('dist_pdh_atr', '>', -2.8816850185394287),
        ('dist_pdh_atr', '<=', -1.7330909371376038),
        ('range_pos_50', '<=', 0.8684571087360382),
        ('is_close_30min', '<=', 0.5),
        ('atr_14', '<=', 15.332234382629395),
        ('dist_pdh_atr', '<=', -2.1943981647491455),
        ('range_pos_50', '<=', 0.8152883648872375),
        ('autocorr_5', '>', -0.2589512765407562),
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

class V3ShortS12T36_165:
    name = 'V3_SHORT_S12T36_190'
    side = 'SHORT'
    target_pts = 36.0
    stop_pts = 12.0
    max_hold_bars = 75
    win_rate = 0.3857724851143842
    profit_factor = 1.453452380952381
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.704147815704346),
        ('dist_pdl_atr', '>', 4.63021183013916),
        ('dist_pdh_atr', '<=', -2.8816850185394287),
        ('dist_vwap_atr', '<=', -0.1871253252029419),
        ('dist_pdl_atr', '>', 7.349009275436401),
        ('range_pos_200', '<=', 0.31001968681812286),
        ('dist_pdl_atr', '<=', 10.683626174926758),
        ('range_pos_50', '<=', 0.8137471973896027),
        ('dist_vwap_atr', '<=', -6.760879039764404),
        ('ny_hour', '>', 13.5),
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

class V3ShortS15T45_166:
    name = 'V3_SHORT_S15T45_191'
    side = 'SHORT'
    target_pts = 45.0
    stop_pts = 15.0
    max_hold_bars = 90
    win_rate = 0.5240975609756098
    profit_factor = 2.390971739634005
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.081039667129517),
        ('dist_pdl_atr', '>', 4.867772340774536),
        ('dist_pdh_atr', '>', -2.951348662376404),
        ('dist_pdh_atr', '>', -1.8258918523788452),
        ('is_close_30min', '<=', 0.5),
        ('atr_14', '>', 5.872344493865967),
        ('dist_pdh_atr', '>', -1.322398066520691),
        ('atr_14', '<=', 19.738442420959473),
        ('atr_5', '>', 7.630382537841797),
        ('dist_pdh_atr', '>', -0.9681582152843475),
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

class V3ShortS15T45_167:
    name = 'V3_SHORT_S15T45_192'
    side = 'SHORT'
    target_pts = 45.0
    stop_pts = 15.0
    max_hold_bars = 90
    win_rate = 0.410857868327187
    profit_factor = 1.6495546798086114
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.081039667129517),
        ('dist_pdl_atr', '>', 4.867772340774536),
        ('dist_pdh_atr', '<=', -2.951348662376404),
        ('dist_vwap_atr', '<=', 0.01895817741751671),
        ('dist_pdl_atr', '>', 7.7281494140625),
        ('range_pos_200', '<=', 0.3555995672941208),
        ('dist_pdl_atr', '>', 11.25482177734375),
        ('atr_50', '<=', 16.64601230621338),
        ('dow', '<=', 1.5),
        ('autocorr_20', '>', -0.3464062064886093),
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

class V3ShortS15T45_168:
    name = 'V3_SHORT_S15T45_195'
    side = 'SHORT'
    target_pts = 45.0
    stop_pts = 15.0
    max_hold_bars = 90
    win_rate = 0.6812896405919662
    profit_factor = 4.860688799255352
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.081039667129517),
        ('dist_pdl_atr', '>', 4.867772340774536),
        ('dist_pdh_atr', '>', -2.951348662376404),
        ('dist_pdh_atr', '>', -1.8258918523788452),
        ('is_close_30min', '<=', 0.5),
        ('atr_14', '>', 5.872344493865967),
        ('dist_pdh_atr', '>', -1.322398066520691),
        ('atr_14', '<=', 19.738442420959473),
        ('atr_5', '>', 7.630382537841797),
        ('dist_pdh_atr', '<=', -0.9681582152843475),
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

class V3ShortS15T45_169:
    name = 'V3_SHORT_S15T45_196'
    side = 'SHORT'
    target_pts = 45.0
    stop_pts = 15.0
    max_hold_bars = 90
    win_rate = 0.6720197652872143
    profit_factor = 4.74155130863644
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.081039667129517),
        ('dist_pdl_atr', '>', 4.867772340774536),
        ('dist_pdh_atr', '>', -2.951348662376404),
        ('dist_pdh_atr', '>', -1.8258918523788452),
        ('is_close_30min', '<=', 0.5),
        ('atr_14', '>', 5.872344493865967),
        ('dist_pdh_atr', '<=', -1.322398066520691),
        ('range_pos_50', '<=', 0.9004702568054199),
        ('atr_14', '<=', 10.894520282745361),
        ('atr_14', '>', 7.122173309326172),
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

class V3ShortS15T45_170:
    name = 'V3_SHORT_S15T45_197'
    side = 'SHORT'
    target_pts = 45.0
    stop_pts = 15.0
    max_hold_bars = 90
    win_rate = 0.5000950751093364
    profit_factor = 2.142511461356916
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.081039667129517),
        ('dist_pdl_atr', '>', 4.867772340774536),
        ('dist_pdh_atr', '>', -2.951348662376404),
        ('dist_pdh_atr', '<=', -1.8258918523788452),
        ('range_pos_50', '<=', 0.8652164340019226),
        ('is_close_30min', '<=', 0.5),
        ('atr_14', '<=', 15.565820693969727),
        ('atr_14', '>', 5.891156911849976),
        ('range_pos_50', '<=', 0.7674744427204132),
        ('hurst_proxy_50', '>', 1.0529366731643677),
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

class V3ShortS15T45_171:
    name = 'V3_SHORT_S15T45_198'
    side = 'SHORT'
    target_pts = 45.0
    stop_pts = 15.0
    max_hold_bars = 90
    win_rate = 0.48875479978058145
    profit_factor = 1.852607128429819
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.081039667129517),
        ('dist_pdl_atr', '>', 4.867772340774536),
        ('dist_pdh_atr', '>', -2.951348662376404),
        ('dist_pdh_atr', '>', -1.8258918523788452),
        ('is_close_30min', '<=', 0.5),
        ('atr_14', '>', 5.872344493865967),
        ('dist_pdh_atr', '>', -1.322398066520691),
        ('atr_14', '<=', 19.738442420959473),
        ('atr_5', '<=', 7.630382537841797),
        ('dist_pdl_atr', '>', 22.3335018157959),
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

class V3ShortS15T45_172:
    name = 'V3_SHORT_S15T45_199'
    side = 'SHORT'
    target_pts = 45.0
    stop_pts = 15.0
    max_hold_bars = 90
    win_rate = 0.4248565965583174
    profit_factor = 1.7398978191528818
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.081039667129517),
        ('dist_pdl_atr', '>', 4.867772340774536),
        ('dist_pdh_atr', '<=', -2.951348662376404),
        ('dist_vwap_atr', '<=', 0.01895817741751671),
        ('dist_pdl_atr', '>', 7.7281494140625),
        ('range_pos_200', '<=', 0.3555995672941208),
        ('dist_pdl_atr', '>', 11.25482177734375),
        ('atr_50', '<=', 16.64601230621338),
        ('dow', '>', 1.5),
        ('ny_hour', '>', 13.5),
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

class V3ShortS8T32_173:
    name = 'V3_SHORT_S8T32_201'
    side = 'SHORT'
    target_pts = 32.0
    stop_pts = 8.0
    max_hold_bars = 55
    win_rate = 0.9354166666666667
    profit_factor = 40.03450862715679
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.704147815704346),
        ('dist_pdl_atr', '>', 4.089028596878052),
        ('dist_pdh_atr', '>', -2.8816850185394287),
        ('dist_pdh_atr', '>', -1.2719497680664062),
        ('atr_14', '<=', 16.13575267791748),
        ('dist_pdh_atr', '>', -0.974441647529602),
        ('atr_14', '>', 5.3874804973602295),
        ('dist_pdh_atr', '>', -0.6965686678886414),
        ('dist_pdh_atr', '>', -0.5688760876655579),
        ('dist_vwap_atr', '>', 6.364563226699829),
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

class V3ShortS8T32_174:
    name = 'V3_SHORT_S8T32_203'
    side = 'SHORT'
    target_pts = 32.0
    stop_pts = 8.0
    max_hold_bars = 55
    win_rate = 0.6147368421052631
    profit_factor = 3.8471066505748586
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.704147815704346),
        ('dist_pdl_atr', '>', 4.089028596878052),
        ('dist_pdh_atr', '>', -2.8816850185394287),
        ('dist_pdh_atr', '>', -1.2719497680664062),
        ('atr_14', '<=', 16.13575267791748),
        ('dist_pdh_atr', '>', -0.974441647529602),
        ('atr_14', '>', 5.3874804973602295),
        ('dist_pdh_atr', '<=', -0.6965686678886414),
        ('atr_14', '<=', 9.9208664894104),
        ('dist_high20_atr', '<=', -0.5035964548587799),
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

class V3ShortS8T32_175:
    name = 'V3_SHORT_S8T32_204'
    side = 'SHORT'
    target_pts = 32.0
    stop_pts = 8.0
    max_hold_bars = 55
    win_rate = 0.9246031746031746
    profit_factor = 34.11124401913876
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.704147815704346),
        ('dist_pdl_atr', '>', 4.089028596878052),
        ('dist_pdh_atr', '>', -2.8816850185394287),
        ('dist_pdh_atr', '>', -1.2719497680664062),
        ('atr_14', '<=', 16.13575267791748),
        ('dist_pdh_atr', '>', -0.974441647529602),
        ('atr_14', '>', 5.3874804973602295),
        ('dist_pdh_atr', '>', -0.6965686678886414),
        ('dist_pdh_atr', '>', -0.5688760876655579),
        ('dist_vwap_atr', '<=', 6.364563226699829),
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

class V3ShortS8T32_176:
    name = 'V3_SHORT_S8T32_205'
    side = 'SHORT'
    target_pts = 32.0
    stop_pts = 8.0
    max_hold_bars = 55
    win_rate = 0.6534788540245566
    profit_factor = 4.744309491677913
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.704147815704346),
        ('dist_pdl_atr', '>', 4.089028596878052),
        ('dist_pdh_atr', '>', -2.8816850185394287),
        ('dist_pdh_atr', '>', -1.2719497680664062),
        ('atr_14', '<=', 16.13575267791748),
        ('dist_pdh_atr', '>', -0.974441647529602),
        ('atr_14', '>', 5.3874804973602295),
        ('dist_pdh_atr', '>', -0.6965686678886414),
        ('dist_pdh_atr', '<=', -0.5688760876655579),
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

class V3ShortS8T32_177:
    name = 'V3_SHORT_S8T32_207'
    side = 'SHORT'
    target_pts = 32.0
    stop_pts = 8.0
    max_hold_bars = 55
    win_rate = 0.447000451059991
    profit_factor = 1.9540488007397483
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.704147815704346),
        ('dist_pdl_atr', '>', 4.089028596878052),
        ('dist_pdh_atr', '>', -2.8816850185394287),
        ('dist_pdh_atr', '<=', -1.2719497680664062),
        ('range_pos_50', '<=', 0.9001944959163666),
        ('dist_pdh_atr', '>', -1.9952126145362854),
        ('is_close_30min', '<=', 0.5),
        ('atr_14', '<=', 15.197757244110107),
        ('dist_high20_atr', '<=', -1.3326361179351807),
        ('dist_pdh_atr', '>', -1.7545334100723267),
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

class V3ShortS8T32_178:
    name = 'V3_SHORT_S8T32_209'
    side = 'SHORT'
    target_pts = 32.0
    stop_pts = 8.0
    max_hold_bars = 55
    win_rate = 0.5661846496106785
    profit_factor = 3.096345514950166
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.704147815704346),
        ('dist_pdl_atr', '>', 4.089028596878052),
        ('dist_pdh_atr', '>', -2.8816850185394287),
        ('dist_pdh_atr', '>', -1.2719497680664062),
        ('atr_14', '<=', 16.13575267791748),
        ('dist_pdh_atr', '<=', -0.974441647529602),
        ('range_pos_200', '<=', 0.9727237224578857),
        ('dist_high20_atr', '<=', -0.9978741705417633),
        ('ny_minute', '<=', 37.5),
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

class V3ShortS10T40_179:
    name = 'V3_SHORT_S10T40_213'
    side = 'SHORT'
    target_pts = 40.0
    stop_pts = 10.0
    max_hold_bars = 70
    win_rate = 0.6283662477558348
    profit_factor = 4.511401425178147
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.794657230377197),
        ('dist_pdl_atr', '>', 4.338512182235718),
        ('dist_pdh_atr', '>', -2.8860883712768555),
        ('dist_pdh_atr', '>', -1.635829210281372),
        ('dist_pdh_atr', '>', -1.0260869264602661),
        ('atr_14', '>', 6.079609632492065),
        ('atr_14', '<=', 16.405616760253906),
        ('dist_pdh_atr', '<=', -0.7890298962593079),
        ('range_pos_50', '<=', 0.9524750709533691),
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

class V3ShortS10T40_180:
    name = 'V3_SHORT_S10T40_214'
    side = 'SHORT'
    target_pts = 40.0
    stop_pts = 10.0
    max_hold_bars = 70
    win_rate = 0.4863707165109034
    profit_factor = 2.3897665294476065
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.794657230377197),
        ('dist_pdl_atr', '>', 4.338512182235718),
        ('dist_pdh_atr', '>', -2.8860883712768555),
        ('dist_pdh_atr', '>', -1.635829210281372),
        ('dist_pdh_atr', '<=', -1.0260869264602661),
        ('range_pos_50', '<=', 0.9265121221542358),
        ('is_close_30min', '<=', 0.5),
        ('atr_14', '<=', 16.68718147277832),
        ('sigma_ratio_5_15', '<=', 2.200124979019165),
        ('dist_pdl_atr', '<=', 29.89308261871338),
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

class V3ShortS10T40_181:
    name = 'V3_SHORT_S10T40_216'
    side = 'SHORT'
    target_pts = 40.0
    stop_pts = 10.0
    max_hold_bars = 70
    win_rate = 0.518581081081081
    profit_factor = 2.8230763941415113
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.794657230377197),
        ('dist_pdl_atr', '>', 4.338512182235718),
        ('dist_pdh_atr', '>', -2.8860883712768555),
        ('dist_pdh_atr', '>', -1.635829210281372),
        ('dist_pdh_atr', '>', -1.0260869264602661),
        ('atr_14', '>', 6.079609632492065),
        ('atr_14', '<=', 16.405616760253906),
        ('dist_pdh_atr', '>', -0.7890298962593079),
        ('atr_14', '>', 7.380979061126709),
        ('dist_low20_atr', '>', 5.374875545501709),
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

class V3ShortS10T40_182:
    name = 'V3_SHORT_S10T40_218'
    side = 'SHORT'
    target_pts = 40.0
    stop_pts = 10.0
    max_hold_bars = 70
    win_rate = 0.5557386051619989
    profit_factor = 3.057730801152175
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.794657230377197),
        ('dist_pdl_atr', '>', 4.338512182235718),
        ('dist_pdh_atr', '>', -2.8860883712768555),
        ('dist_pdh_atr', '>', -1.635829210281372),
        ('dist_pdh_atr', '<=', -1.0260869264602661),
        ('range_pos_50', '<=', 0.9265121221542358),
        ('is_close_30min', '<=', 0.5),
        ('atr_14', '<=', 16.68718147277832),
        ('sigma_ratio_5_15', '<=', 2.200124979019165),
        ('dist_pdl_atr', '>', 29.89308261871338),
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

class V3ShortS12T48_183:
    name = 'V3_SHORT_S12T48_221'
    side = 'SHORT'
    target_pts = 48.0
    stop_pts = 12.0
    max_hold_bars = 100
    win_rate = 0.41870261162594774
    profit_factor = 1.9572030048746178
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.711584091186523),
        ('dist_pdl_atr', '>', 5.249834060668945),
        ('dist_pdh_atr', '>', -2.63948392868042),
        ('dist_pdh_atr', '>', -1.6393224596977234),
        ('is_close_30min', '<=', 0.5),
        ('dist_pdh_atr', '>', -1.0779293179512024),
        ('atr_14', '>', 6.228728532791138),
        ('atr_14', '<=', 17.892064094543457),
        ('atr_5', '>', 6.759814977645874),
        ('dist_pdh_atr', '>', -0.8852963447570801),
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

class V3ShortS12T48_184:
    name = 'V3_SHORT_S12T48_224'
    side = 'SHORT'
    target_pts = 48.0
    stop_pts = 12.0
    max_hold_bars = 100
    win_rate = 0.5447897623400365
    profit_factor = 3.3280636477426655
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.711584091186523),
        ('dist_pdl_atr', '>', 5.249834060668945),
        ('dist_pdh_atr', '>', -2.63948392868042),
        ('dist_pdh_atr', '>', -1.6393224596977234),
        ('is_close_30min', '<=', 0.5),
        ('dist_pdh_atr', '<=', -1.0779293179512024),
        ('range_pos_50', '<=', 0.9193956851959229),
        ('atr_14', '<=', 16.68718147277832),
        ('atr_14', '>', 5.902839660644531),
        ('dist_pdl_atr', '<=', 31.112215995788574),
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

class V3ShortS12T48_185:
    name = 'V3_SHORT_S12T48_226'
    side = 'SHORT'
    target_pts = 48.0
    stop_pts = 12.0
    max_hold_bars = 100
    win_rate = 0.6314720812182741
    profit_factor = 4.9002430815258045
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.711584091186523),
        ('dist_pdl_atr', '>', 5.249834060668945),
        ('dist_pdh_atr', '>', -2.63948392868042),
        ('dist_pdh_atr', '>', -1.6393224596977234),
        ('is_close_30min', '<=', 0.5),
        ('dist_pdh_atr', '>', -1.0779293179512024),
        ('atr_14', '>', 6.228728532791138),
        ('atr_14', '<=', 17.892064094543457),
        ('atr_5', '>', 6.759814977645874),
        ('dist_pdh_atr', '<=', -0.8852963447570801),
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

class V3ShortS12T48_186:
    name = 'V3_SHORT_S12T48_228'
    side = 'SHORT'
    target_pts = 48.0
    stop_pts = 12.0
    max_hold_bars = 100
    win_rate = 0.4673228346456693
    profit_factor = 2.4794734915887378
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.711584091186523),
        ('dist_pdl_atr', '>', 5.249834060668945),
        ('dist_pdh_atr', '>', -2.63948392868042),
        ('dist_pdh_atr', '<=', -1.6393224596977234),
        ('range_pos_50', '<=', 0.9001944959163666),
        ('is_close_30min', '<=', 0.5),
        ('dist_pdl_atr', '>', 20.8799409866333),
        ('dist_eq50_atr', '<=', 1.9540122747421265),
        ('atr_50', '<=', 10.779364109039307),
        ('atr_50', '>', 5.848622560501099),
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

class V3ShortS12T48_187:
    name = 'V3_SHORT_S12T48_230'
    side = 'SHORT'
    target_pts = 48.0
    stop_pts = 12.0
    max_hold_bars = 100
    win_rate = 0.6028192371475953
    profit_factor = 4.259976251304379
    tier = 'B'
    constraints = [
        ('atr_14', '>', 4.711584091186523),
        ('dist_pdl_atr', '>', 5.249834060668945),
        ('dist_pdh_atr', '>', -2.63948392868042),
        ('dist_pdh_atr', '>', -1.6393224596977234),
        ('is_close_30min', '<=', 0.5),
        ('dist_pdh_atr', '<=', -1.0779293179512024),
        ('range_pos_50', '<=', 0.9193956851959229),
        ('atr_14', '<=', 16.68718147277832),
        ('atr_14', '>', 5.902839660644531),
        ('dist_pdl_atr', '>', 31.112215995788574),
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

class V3ShortS15T60_188:
    name = 'V3_SHORT_S15T60_231'
    side = 'SHORT'
    target_pts = 60.0
    stop_pts = 15.0
    max_hold_bars = 130
    win_rate = 0.886339937434828
    profit_factor = 23.9866597422831
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.096276760101318),
        ('dist_pdl_atr', '>', 6.38116192817688),
        ('range_pos_200', '>', 0.4368617981672287),
        ('dist_pdh_atr', '>', -4.335883140563965),
        ('dist_pdh_atr', '>', -2.1027623414993286),
        ('is_close_30min', '<=', 0.5),
        ('dist_pdh_atr', '>', -1.366704523563385),
        ('atr_50', '>', 6.0645716190338135),
        ('atr_14', '<=', 19.415468215942383),
        ('ny_hour', '<=', 14.5),
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

class V3ShortS15T60_189:
    name = 'V3_SHORT_S15T60_232'
    side = 'SHORT'
    target_pts = 60.0
    stop_pts = 15.0
    max_hold_bars = 130
    win_rate = 0.38562591228192117
    profit_factor = 2.011149854293465
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.096276760101318),
        ('dist_pdl_atr', '>', 6.38116192817688),
        ('range_pos_200', '<=', 0.4368617981672287),
        ('dist_pdl_atr', '>', 9.416709899902344),
        ('dist_vwap_atr', '<=', 0.981489509344101),
        ('dist_pdl_atr', '>', 11.325088500976562),
        ('atr_50', '<=', 16.644947052001953),
        ('dist_vwap_atr', '<=', -1.4223196506500244),
        ('dist_eq50_atr', '<=', -0.7844333648681641),
        ('dist_pdh_atr', '<=', -13.512110233306885),
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

class V3ShortS15T60_190:
    name = 'V3_SHORT_S15T60_233'
    side = 'SHORT'
    target_pts = 60.0
    stop_pts = 15.0
    max_hold_bars = 130
    win_rate = 0.573170731707317
    profit_factor = 3.755231309691737
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.096276760101318),
        ('dist_pdl_atr', '>', 6.38116192817688),
        ('range_pos_200', '>', 0.4368617981672287),
        ('dist_pdh_atr', '>', -4.335883140563965),
        ('dist_pdh_atr', '>', -2.1027623414993286),
        ('is_close_30min', '<=', 0.5),
        ('dist_pdh_atr', '<=', -1.366704523563385),
        ('dist_pdl_atr', '>', 21.0189790725708),
        ('range_pos_50', '<=', 0.9204148054122925),
        ('atr_50', '>', 5.907296657562256),
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

class V3ShortS15T60_191:
    name = 'V3_SHORT_S15T60_234'
    side = 'SHORT'
    target_pts = 60.0
    stop_pts = 15.0
    max_hold_bars = 130
    win_rate = 0.35764685129652496
    profit_factor = 1.7247160378155455
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.096276760101318),
        ('dist_pdl_atr', '>', 6.38116192817688),
        ('range_pos_200', '<=', 0.4368617981672287),
        ('dist_pdl_atr', '>', 9.416709899902344),
        ('dist_vwap_atr', '<=', 0.981489509344101),
        ('dist_pdl_atr', '>', 11.325088500976562),
        ('atr_50', '<=', 16.644947052001953),
        ('dist_vwap_atr', '<=', -1.4223196506500244),
        ('dist_eq50_atr', '<=', -0.7844333648681641),
        ('dist_pdh_atr', '>', -13.512110233306885),
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

class V3ShortS15T60_192:
    name = 'V3_SHORT_S15T60_235'
    side = 'SHORT'
    target_pts = 60.0
    stop_pts = 15.0
    max_hold_bars = 130
    win_rate = 0.538650580875782
    profit_factor = 3.395172949969993
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.096276760101318),
        ('dist_pdl_atr', '>', 6.38116192817688),
        ('range_pos_200', '>', 0.4368617981672287),
        ('dist_pdh_atr', '>', -4.335883140563965),
        ('dist_pdh_atr', '<=', -2.1027623414993286),
        ('ny_hour', '<=', 14.5),
        ('range_pos_50', '<=', 0.7986741960048676),
        ('dist_pdl_atr', '>', 9.610740184783936),
        ('dist_pdh_atr', '>', -3.304238200187683),
        ('dist_pdl_atr', '>', 20.75528335571289),
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

class V3ShortS15T60_193:
    name = 'V3_SHORT_S15T60_238'
    side = 'SHORT'
    target_pts = 60.0
    stop_pts = 15.0
    max_hold_bars = 130
    win_rate = 0.9499568593615185
    profit_factor = 68.20980533525595
    tier = 'B'
    constraints = [
        ('atr_14', '<=', 5.096276760101318),
        ('dist_pdl_atr', '>', 13.912715435028076),
        ('atr_14', '>', 3.462265372276306),
        ('range_pos_200', '>', 0.5275476276874542),
        ('dist_pdh_atr', '>', -4.14378809928894),
        ('dist_pdl_atr', '>', 22.810126304626465),
        ('ny_hour', '<=', 14.5),
        ('dist_pdh_atr', '>', -3.0270224809646606),
        ('ema_distance', '<=', 2.691648006439209),
        ('dow', '>', 0.5),
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

class V3ShortS15T60_194:
    name = 'V3_SHORT_S15T60_239'
    side = 'SHORT'
    target_pts = 60.0
    stop_pts = 15.0
    max_hold_bars = 130
    win_rate = 0.37595002602811034
    profit_factor = 1.7545746527574422
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.096276760101318),
        ('dist_pdl_atr', '>', 6.38116192817688),
        ('range_pos_200', '>', 0.4368617981672287),
        ('dist_pdh_atr', '>', -4.335883140563965),
        ('dist_pdh_atr', '<=', -2.1027623414993286),
        ('ny_hour', '<=', 14.5),
        ('range_pos_50', '<=', 0.7986741960048676),
        ('dist_pdl_atr', '>', 9.610740184783936),
        ('dist_pdh_atr', '<=', -3.304238200187683),
        ('range_pos_200', '<=', 0.8896024227142334),
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

class V3ShortS15T60_195:
    name = 'V3_SHORT_S15T60_240'
    side = 'SHORT'
    target_pts = 60.0
    stop_pts = 15.0
    max_hold_bars = 130
    win_rate = 0.3837492391965916
    profit_factor = 1.9722498815418106
    tier = 'B'
    constraints = [
        ('atr_14', '>', 5.096276760101318),
        ('dist_pdl_atr', '>', 6.38116192817688),
        ('range_pos_200', '<=', 0.4368617981672287),
        ('dist_pdl_atr', '>', 9.416709899902344),
        ('dist_vwap_atr', '<=', 0.981489509344101),
        ('dist_pdl_atr', '>', 11.325088500976562),
        ('atr_50', '<=', 16.644947052001953),
        ('dist_vwap_atr', '>', -1.4223196506500244),
        ('ny_hour', '<=', 12.5),
        ('dist_pdl_atr', '>', 18.5684814453125),
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

class V3LongS8T16_196:
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

class V3LongS10T20_197:
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

class V3ShortS15T30_198:
    name = 'V3_SHORT_S15T30_242'
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

class V3ShortS12T24_199:
    name = 'V3_SHORT_S12T24_243'
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

class V3LongS20T40_200:
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

class V3ShortS8T16_201:
    name = 'V3_SHORT_S8T16_244'
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

class V3ShortS10T20_202:
    name = 'V3_SHORT_S10T20_247'
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

class V3LongS8T16_203:
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

class V3LongS8T16_204:
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

class V3ShortS12T24_205:
    name = 'V3_SHORT_S12T24_248'
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

class V3ShortS8T16_206:
    name = 'V3_SHORT_S8T16_249'
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

class V3ShortS8T16_207:
    name = 'V3_SHORT_S8T16_250'
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

class V3LongS10T20_208:
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

class V3LongS15T30_209:
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
    V3ShortS15T30_04(),
    V3ShortS18T36_05(),
    V3ShortS18T36_06(),
    V3ShortS20T40_07(),
    V3ShortS20T50_08(),
    V3ShortS20T40_09(),
    V3ShortS10T20_10(),
    V3ShortS20T40_11(),
    V3LongS15T30_12(),
    V3LongS8T16_13(),
    V3ShortS8T16_14(),
    V3ShortS10T20_15(),
    V3ShortS10T20_16(),
    V3LongS12T24_17(),
    V3ShortS12T24_18(),
    V3LongS15T30_19(),
    V3ShortS15T30_20(),
    V3ShortS15T30_21(),
    V3LongS20T50_22(),
    V3LongS15T37_23(),
    V3LongS20T60_24(),
    V3LongS20T50_25(),
    V3LongS15T45_26(),
    V3LongS15T37_27(),
    V3LongS20T60_28(),
    V3LongS20T50_29(),
    V3LongS15T60_30(),
    V3LongS12T36_31(),
    V3LongS20T60_32(),
    V3LongS20T50_33(),
    V3LongS20T50_34(),
    V3LongS20T60_35(),
    V3LongS10T30_36(),
    V3LongS12T30_37(),
    V3LongS15T45_38(),
    V3LongS20T60_39(),
    V3LongS15T37_40(),
    V3LongS20T60_41(),
    V3LongS10T30_42(),
    V3LongS20T60_43(),
    V3LongS12T30_44(),
    V3LongS20T50_45(),
    V3LongS15T45_46(),
    V3LongS10T25_47(),
    V3LongS12T36_48(),
    V3LongS20T60_49(),
    V3LongS10T30_50(),
    V3LongS20T50_51(),
    V3LongS12T30_52(),
    V3LongS15T37_53(),
    V3ShortS8T16_54(),
    V3ShortS8T16_55(),
    V3ShortS8T16_56(),
    V3ShortS10T20_57(),
    V3ShortS10T20_58(),
    V3ShortS10T20_59(),
    V3ShortS10T20_60(),
    V3ShortS10T20_61(),
    V3ShortS10T20_62(),
    V3ShortS10T20_63(),
    V3ShortS12T24_64(),
    V3ShortS12T24_65(),
    V3ShortS12T24_66(),
    V3ShortS12T24_67(),
    V3ShortS12T24_68(),
    V3ShortS12T24_69(),
    V3ShortS12T24_70(),
    V3ShortS12T24_71(),
    V3ShortS12T24_72(),
    V3ShortS12T24_73(),
    V3ShortS12T24_74(),
    V3ShortS12T24_75(),
    V3ShortS15T30_76(),
    V3ShortS15T30_77(),
    V3ShortS15T30_78(),
    V3ShortS15T30_79(),
    V3ShortS15T30_80(),
    V3ShortS15T30_81(),
    V3ShortS15T30_82(),
    V3ShortS15T30_83(),
    V3ShortS15T30_84(),
    V3ShortS15T30_85(),
    V3ShortS15T30_86(),
    V3ShortS15T30_87(),
    V3ShortS15T30_88(),
    V3ShortS15T30_89(),
    V3ShortS15T30_90(),
    V3ShortS15T30_91(),
    V3ShortS18T36_92(),
    V3ShortS18T36_93(),
    V3ShortS18T36_94(),
    V3ShortS18T36_95(),
    V3ShortS18T36_96(),
    V3ShortS18T36_97(),
    V3ShortS18T36_98(),
    V3ShortS18T36_99(),
    V3ShortS20T40_100(),
    V3ShortS20T40_101(),
    V3ShortS20T40_102(),
    V3ShortS20T40_103(),
    V3ShortS20T40_104(),
    V3ShortS20T40_105(),
    V3ShortS20T40_106(),
    V3ShortS20T40_107(),
    V3ShortS20T40_108(),
    V3ShortS20T40_109(),
    V3ShortS20T40_110(),
    V3ShortS20T40_111(),
    V3ShortS20T40_112(),
    V3ShortS6T15_113(),
    V3ShortS8T20_114(),
    V3ShortS8T20_115(),
    V3ShortS8T20_116(),
    V3ShortS8T20_117(),
    V3ShortS8T20_118(),
    V3ShortS8T20_119(),
    V3ShortS10T25_120(),
    V3ShortS10T25_121(),
    V3ShortS10T25_122(),
    V3ShortS12T30_123(),
    V3ShortS12T30_124(),
    V3ShortS12T30_125(),
    V3ShortS12T30_126(),
    V3ShortS12T30_127(),
    V3ShortS12T30_128(),
    V3ShortS15T37_129(),
    V3ShortS15T37_130(),
    V3ShortS15T37_131(),
    V3ShortS15T37_132(),
    V3ShortS15T37_133(),
    V3ShortS15T37_134(),
    V3ShortS15T37_135(),
    V3ShortS15T37_136(),
    V3ShortS15T37_137(),
    V3ShortS15T37_138(),
    V3ShortS20T50_139(),
    V3ShortS20T50_140(),
    V3ShortS20T50_141(),
    V3ShortS20T50_142(),
    V3ShortS20T50_143(),
    V3ShortS20T50_144(),
    V3ShortS20T50_145(),
    V3ShortS20T50_146(),
    V3ShortS20T50_147(),
    V3ShortS6T18_148(),
    V3ShortS8T24_149(),
    V3ShortS8T24_150(),
    V3ShortS8T24_151(),
    V3ShortS8T24_152(),
    V3ShortS8T24_153(),
    V3ShortS8T24_154(),
    V3ShortS10T30_155(),
    V3ShortS10T30_156(),
    V3ShortS10T30_157(),
    V3ShortS10T30_158(),
    V3ShortS10T30_159(),
    V3ShortS12T36_160(),
    V3ShortS12T36_161(),
    V3ShortS12T36_162(),
    V3ShortS12T36_163(),
    V3ShortS12T36_164(),
    V3ShortS12T36_165(),
    V3ShortS15T45_166(),
    V3ShortS15T45_167(),
    V3ShortS15T45_168(),
    V3ShortS15T45_169(),
    V3ShortS15T45_170(),
    V3ShortS15T45_171(),
    V3ShortS15T45_172(),
    V3ShortS8T32_173(),
    V3ShortS8T32_174(),
    V3ShortS8T32_175(),
    V3ShortS8T32_176(),
    V3ShortS8T32_177(),
    V3ShortS8T32_178(),
    V3ShortS10T40_179(),
    V3ShortS10T40_180(),
    V3ShortS10T40_181(),
    V3ShortS10T40_182(),
    V3ShortS12T48_183(),
    V3ShortS12T48_184(),
    V3ShortS12T48_185(),
    V3ShortS12T48_186(),
    V3ShortS12T48_187(),
    V3ShortS15T60_188(),
    V3ShortS15T60_189(),
    V3ShortS15T60_190(),
    V3ShortS15T60_191(),
    V3ShortS15T60_192(),
    V3ShortS15T60_193(),
    V3ShortS15T60_194(),
    V3ShortS15T60_195(),
    V3LongS8T16_196(),
    V3LongS10T20_197(),
    V3ShortS15T30_198(),
    V3ShortS12T24_199(),
    V3LongS20T40_200(),
    V3ShortS8T16_201(),
    V3ShortS10T20_202(),
    V3LongS8T16_203(),
    V3LongS8T16_204(),
    V3ShortS12T24_205(),
    V3ShortS8T16_206(),
    V3ShortS8T16_207(),
    V3LongS10T20_208(),
    V3LongS15T30_209(),
]