"""
Auto-generated v3 pattern Signal classes.
Generated: 2026-05-04T03:02:00.319955+00:00
Survivors: 201  (LONG=102, SHORT=99)
Sources: ['mined_v3_rr10.json', 'mined_v3_broad.json', 'mined_v3_wide.json']
Validation: deep tree + 5-fold CPCV (Lopez de Prado),
            leak-fixed _attach_prev_day_levels (UTC dates).
"""
from __future__ import annotations
import pandas as pd

from research.pattern_miner_v3 import build_v3_features

class V3LongS8T8_0001:
    name = 'V3_LONG_S8T8_001'
    side = 'LONG'
    target_pts = 8.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.5895377857216293
    cpcv_min_wr = 0.5363128491620112
    constraints = [
        ('atr_14', '>', 2.706931471824646),
        ('atr_5', '<=', 20.052778244018555),
        ('atr_14', '>', 3.4773783683776855),
        ('atr_5', '<=', 13.589250087738037),
        ('dist_pdh_atr', '>', 4.697079658508301),
        ('is_close_30min', '<=', 0.5),
        ('dist_low20_atr', '<=', 0.6921310722827911),
        ('sigma_ratio_5_15', '<=', 1.6087714433670044),
        ('dist_eq50_atr', '>', -3.485216975212097),
        ('ny_minute', '<=', 33.5),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS8T8_0002:
    name = 'V3_LONG_S8T8_002'
    side = 'LONG'
    target_pts = 8.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.575195777405637
    cpcv_min_wr = 0.4984520123839009
    constraints = [
        ('atr_14', '>', 2.706931471824646),
        ('atr_5', '<=', 20.052778244018555),
        ('atr_14', '>', 3.4773783683776855),
        ('atr_5', '<=', 13.589250087738037),
        ('dist_pdh_atr', '>', 4.697079658508301),
        ('is_close_30min', '<=', 0.5),
        ('dist_low20_atr', '>', 0.6921310722827911),
        ('dist_vwap_atr', '>', 2.4648196697235107),
        ('atr_50', '<=', 7.428928375244141),
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS8T8_0003:
    name = 'V3_LONG_S8T8_003'
    side = 'LONG'
    target_pts = 8.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.5482617713099543
    cpcv_min_wr = 0.5268085106382979
    constraints = [
        ('atr_14', '>', 2.706931471824646),
        ('atr_5', '<=', 20.052778244018555),
        ('atr_14', '>', 3.4773783683776855),
        ('atr_5', '<=', 13.589250087738037),
        ('dist_pdh_atr', '>', 4.697079658508301),
        ('is_close_30min', '<=', 0.5),
        ('dist_low20_atr', '<=', 0.6921310722827911),
        ('sigma_ratio_5_15', '<=', 1.6087714433670044),
        ('dist_eq50_atr', '>', -3.485216975212097),
        ('ny_minute', '>', 33.5),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS8T8_0004:
    name = 'V3_LONG_S8T8_004'
    side = 'LONG'
    target_pts = 8.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.6167800291593489
    cpcv_min_wr = 0.5338345864661654
    constraints = [
        ('atr_14', '>', 2.706931471824646),
        ('atr_5', '<=', 20.052778244018555),
        ('atr_14', '>', 3.4773783683776855),
        ('atr_5', '<=', 13.589250087738037),
        ('dist_pdh_atr', '<=', 4.697079658508301),
        ('dist_vwap_atr', '<=', 6.662899971008301),
        ('atr_5', '>', 5.191962480545044),
        ('ema_distance', '>', 4.475109815597534),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS8T8_0005:
    name = 'V3_LONG_S8T8_005'
    side = 'LONG'
    target_pts = 8.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.6020629230850014
    cpcv_min_wr = 0.5512820512820513
    constraints = [
        ('atr_14', '>', 2.706931471824646),
        ('atr_5', '<=', 20.052778244018555),
        ('atr_14', '>', 3.4773783683776855),
        ('atr_5', '<=', 13.589250087738037),
        ('dist_pdh_atr', '<=', 4.697079658508301),
        ('dist_vwap_atr', '<=', 6.662899971008301),
        ('atr_5', '>', 5.191962480545044),
        ('ema_distance', '<=', 4.475109815597534),
        ('range_pos_200', '<=', 0.008088434115052223),
        ('range_expansion_5', '<=', 0.9293066561222076),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS8T8_0006:
    name = 'V3_LONG_S8T8_006'
    side = 'LONG'
    target_pts = 8.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.5418289367137529
    cpcv_min_wr = 0.5096952908587258
    constraints = [
        ('atr_14', '>', 2.706931471824646),
        ('atr_5', '<=', 20.052778244018555),
        ('atr_14', '>', 3.4773783683776855),
        ('atr_5', '>', 13.589250087738037),
        ('vol_change_3', '<=', 5.466118574142456),
        ('atr_5', '<=', 17.20926284790039),
        ('ofi_5', '>', -745.1919860839844),
        ('ny_minute', '>', 55.5),
        ('dist_pdh_atr', '<=', -1.3776379227638245),
        ('ema_distance', '>', 1.0451972484588623),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS8T8_0007:
    name = 'V3_SHORT_S8T8_001'
    side = 'SHORT'
    target_pts = 8.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.5884116547772322
    cpcv_min_wr = 0.5365853658536586
    constraints = [
        ('atr_14', '>', 2.374924063682556),
        ('atr_14', '>', 3.206903338432312),
        ('atr_5', '<=', 20.57501792907715),
        ('atr_14', '>', 4.700930833816528),
        ('atr_5', '<=', 15.112215518951416),
        ('dist_pdh_atr', '>', -7.484505653381348),
        ('ema_distance', '<=', 2.8988640308380127),
        ('atr_50', '<=', 4.397131443023682),
        ('dist_pdl_atr', '>', 13.302723407745361),
        ('dist_pdh_atr', '<=', 2.4621165990829468),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS12T12_0008:
    name = 'V3_LONG_S12T12_007'
    side = 'LONG'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.5800058537291995
    cpcv_min_wr = 0.5471856622794735
    constraints = [
        ('atr_14', '>', 3.112475275993347),
        ('atr_14', '>', 3.9063631296157837),
        ('dist_vwap_atr', '>', 1.9870991110801697),
        ('dist_pdh_atr', '>', 2.7288014888763428),
        ('is_close_30min', '<=', 0.5),
        ('ofi_20', '>', 2388.6744384765625),
        ('sigma_ratio_1_15', '<=', 2.8405243158340454),
        ('atr_50', '<=', 9.415329933166504),
        ('range_pos_50', '>', 0.7717762887477875),
        ('above_pdh_count_20', '>', 18.5),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS12T12_0009:
    name = 'V3_LONG_S12T12_008'
    side = 'LONG'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.5525541327750334
    cpcv_min_wr = 0.4945469798657718
    constraints = [
        ('atr_14', '>', 3.112475275993347),
        ('atr_14', '>', 3.9063631296157837),
        ('dist_vwap_atr', '>', 1.9870991110801697),
        ('dist_pdh_atr', '<=', 2.7288014888763428),
        ('atr_14', '>', 5.560963153839111),
        ('atr_5', '<=', 20.869565963745117),
        ('dist_eq50_atr', '<=', 5.617683172225952),
        ('dist_pdh_atr', '>', -22.797100067138672),
        ('hurst_proxy_50', '>', 2.1211520433425903),
        ('atr_50', '<=', 9.487069129943848),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS12T12_0010:
    name = 'V3_LONG_S12T12_009'
    side = 'LONG'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.5605451255239792
    cpcv_min_wr = 0.5202312138728323
    constraints = [
        ('atr_14', '>', 3.112475275993347),
        ('atr_14', '>', 3.9063631296157837),
        ('dist_vwap_atr', '>', 1.9870991110801697),
        ('dist_pdh_atr', '>', 2.7288014888763428),
        ('is_close_30min', '<=', 0.5),
        ('ofi_20', '<=', 2388.6744384765625),
        ('rsi_5', '<=', 35.85439872741699),
        ('ofi_20', '>', -1179.9562377929688),
        ('dist_pdh_atr', '>', 10.788175106048584),
        ('range_pos_200', '>', 0.6408588588237762),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS12T12_0011:
    name = 'V3_LONG_S12T12_010'
    side = 'LONG'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.6243839243802809
    cpcv_min_wr = 0.5570866141732284
    constraints = [
        ('atr_14', '>', 3.112475275993347),
        ('atr_14', '>', 3.9063631296157837),
        ('dist_vwap_atr', '>', 1.9870991110801697),
        ('dist_pdh_atr', '>', 2.7288014888763428),
        ('is_close_30min', '<=', 0.5),
        ('ofi_20', '<=', 2388.6744384765625),
        ('rsi_5', '<=', 35.85439872741699),
        ('ofi_20', '<=', -1179.9562377929688),
        ('atr_50', '<=', 9.116754531860352),
        ('sigma_ratio_1_15', '>', 1.2478495836257935),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS12T12_0012:
    name = 'V3_LONG_S12T12_011'
    side = 'LONG'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.5528547681292416
    cpcv_min_wr = 0.4936014625228519
    constraints = [
        ('atr_14', '>', 3.112475275993347),
        ('atr_14', '>', 3.9063631296157837),
        ('dist_vwap_atr', '<=', 1.9870991110801697),
        ('atr_14', '>', 4.41860818862915),
        ('atr_5', '<=', 27.248538970947266),
        ('dist_pdl_atr', '>', -36.779632568359375),
        ('range_pos_50', '<=', 0.05113895796239376),
        ('range_expansion_5', '<=', 0.9314846694469452),
        ('dist_pdl_atr', '>', -21.493264198303223),
        ('range_pos_200', '<=', 0.014133276883512735),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS12T12_0013:
    name = 'V3_LONG_S12T12_012'
    side = 'LONG'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.569301359015311
    cpcv_min_wr = 0.5207547169811321
    constraints = [
        ('atr_14', '>', 3.112475275993347),
        ('atr_14', '>', 3.9063631296157837),
        ('dist_vwap_atr', '>', 1.9870991110801697),
        ('dist_pdh_atr', '<=', 2.7288014888763428),
        ('atr_14', '<=', 5.560963153839111),
        ('dist_vwap_atr', '<=', 13.071813583374023),
        ('hurst_proxy_50', '<=', 2.182258725166321),
        ('dow', '>', 0.5),
        ('dist_high20_atr', '<=', -3.251760244369507),
        ('sigma_ratio_5_15', '<=', 1.6871350407600403),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS12T12_0014:
    name = 'V3_LONG_S12T12_013'
    side = 'LONG'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.6121463647283616
    cpcv_min_wr = 0.5315985130111525
    constraints = [
        ('atr_14', '>', 3.112475275993347),
        ('atr_14', '>', 3.9063631296157837),
        ('dist_vwap_atr', '<=', 1.9870991110801697),
        ('atr_14', '>', 4.41860818862915),
        ('atr_5', '<=', 27.248538970947266),
        ('dist_pdl_atr', '>', -36.779632568359375),
        ('range_pos_50', '<=', 0.05113895796239376),
        ('range_expansion_5', '<=', 0.9314846694469452),
        ('dist_pdl_atr', '<=', -21.493264198303223),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS12T12_0015:
    name = 'V3_LONG_S12T12_014'
    side = 'LONG'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.5407286065711701
    cpcv_min_wr = 0.48450704225352115
    constraints = [
        ('atr_14', '>', 3.112475275993347),
        ('atr_14', '>', 3.9063631296157837),
        ('dist_vwap_atr', '>', 1.9870991110801697),
        ('dist_pdh_atr', '>', 2.7288014888763428),
        ('is_close_30min', '<=', 0.5),
        ('ofi_20', '<=', 2388.6744384765625),
        ('rsi_5', '<=', 35.85439872741699),
        ('ofi_20', '<=', -1179.9562377929688),
        ('atr_50', '<=', 9.116754531860352),
        ('sigma_ratio_1_15', '<=', 1.2478495836257935),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS12T12_0016:
    name = 'V3_LONG_S12T12_015'
    side = 'LONG'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.5910176208746667
    cpcv_min_wr = 0.5661764705882353
    constraints = [
        ('atr_14', '>', 3.112475275993347),
        ('atr_14', '>', 3.9063631296157837),
        ('dist_vwap_atr', '>', 1.9870991110801697),
        ('dist_pdh_atr', '>', 2.7288014888763428),
        ('is_close_30min', '<=', 0.5),
        ('ofi_20', '<=', 2388.6744384765625),
        ('rsi_5', '<=', 35.85439872741699),
        ('ofi_20', '<=', -1179.9562377929688),
        ('atr_50', '>', 9.116754531860352),
        ('range_pos_50', '>', 0.46821312606334686),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS12T12_0017:
    name = 'V3_LONG_S12T12_016'
    side = 'LONG'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.5911830168341163
    cpcv_min_wr = 0.5087719298245614
    constraints = [
        ('atr_14', '>', 3.112475275993347),
        ('atr_14', '>', 3.9063631296157837),
        ('dist_vwap_atr', '<=', 1.9870991110801697),
        ('atr_14', '>', 4.41860818862915),
        ('atr_5', '<=', 27.248538970947266),
        ('dist_pdl_atr', '>', -36.779632568359375),
        ('range_pos_50', '<=', 0.05113895796239376),
        ('range_expansion_5', '>', 0.9314846694469452),
        ('sigma_ratio_5_15', '>', 2.183490514755249),
        ('dist_vwap_atr', '<=', -8.133699417114258),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS12T12_0018:
    name = 'V3_SHORT_S12T12_002'
    side = 'SHORT'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.5659382550549056
    cpcv_min_wr = 0.5413427561837456
    constraints = [
        ('atr_14', '>', 3.5315141677856445),
        ('atr_14', '<=', 4.836634397506714),
        ('atr_50', '>', 4.331652402877808),
        ('dist_vwap_atr', '<=', 5.784951448440552),
        ('autocorr_20', '<=', 0.11097856238484383),
        ('dist_vwap_atr', '>', -8.83698844909668),
        ('is_close_30min', '<=', 0.5),
        ('ofi_20', '<=', 991.7224426269531),
        ('dist_pdl_atr', '<=', 22.023950576782227),
        ('ny_hour', '>', 11.5),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS12T12_0019:
    name = 'V3_SHORT_S12T12_003'
    side = 'SHORT'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.5644105193809936
    cpcv_min_wr = 0.5182926829268293
    constraints = [
        ('atr_14', '>', 3.5315141677856445),
        ('atr_14', '>', 4.836634397506714),
        ('dist_pdh_atr', '<=', -6.872745037078857),
        ('atr_5', '<=', 24.96738052368164),
        ('dist_vwap_atr', '<=', -1.386819064617157),
        ('ofi_5', '>', 731.8138122558594),
        ('atr_14', '>', 5.36432147026062),
        ('hurst_proxy_50', '>', 2.3930145502090454),
        ('atr_5', '>', 7.891968250274658),
        ('ret_3', '>', 2.625),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS12T12_0020:
    name = 'V3_SHORT_S12T12_004'
    side = 'SHORT'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.6050632085984541
    cpcv_min_wr = 0.5528942115768463
    constraints = [
        ('atr_14', '>', 3.5315141677856445),
        ('atr_14', '>', 4.836634397506714),
        ('dist_pdh_atr', '<=', -6.872745037078857),
        ('atr_5', '<=', 24.96738052368164),
        ('dist_vwap_atr', '<=', -1.386819064617157),
        ('ofi_5', '>', 731.8138122558594),
        ('atr_14', '>', 5.36432147026062),
        ('hurst_proxy_50', '<=', 2.3930145502090454),
        ('ofi_20', '>', 5558.2216796875),
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

class V3ShortS12T12_0021:
    name = 'V3_SHORT_S12T12_005'
    side = 'SHORT'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.6509643387497539
    cpcv_min_wr = 0.5209302325581395
    constraints = [
        ('atr_14', '>', 3.5315141677856445),
        ('atr_14', '>', 4.836634397506714),
        ('dist_pdh_atr', '>', -6.872745037078857),
        ('range_pos_200', '>', 0.9080181419849396),
        ('atr_50', '>', 5.339649438858032),
        ('atr_50', '>', 10.103973865509033),
        ('autocorr_20', '>', 0.02987294364720583),
        ('dist_vwap_atr', '>', 10.57235860824585),
        ('vol_ratio_30', '<=', 1.0232904553413391),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS12T12_0022:
    name = 'V3_SHORT_S12T12_006'
    side = 'SHORT'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.6066381884444638
    cpcv_min_wr = 0.4847457627118644
    constraints = [
        ('atr_14', '>', 3.5315141677856445),
        ('atr_14', '>', 4.836634397506714),
        ('dist_pdh_atr', '<=', -6.872745037078857),
        ('atr_5', '<=', 24.96738052368164),
        ('dist_vwap_atr', '>', -1.386819064617157),
        ('dist_pdh_atr', '<=', -22.781721115112305),
        ('atr_50', '>', 5.087145090103149),
        ('hurst_proxy_50', '>', 0.9313125908374786),
        ('sigma_ratio_1_15', '>', 2.8627841472625732),
        ('atr_14', '<=', 9.021707534790039),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS12T12_0023:
    name = 'V3_SHORT_S12T12_007'
    side = 'SHORT'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.5895481243371982
    cpcv_min_wr = 0.5011655011655012
    constraints = [
        ('atr_14', '>', 3.5315141677856445),
        ('atr_14', '>', 4.836634397506714),
        ('dist_pdh_atr', '<=', -6.872745037078857),
        ('atr_5', '<=', 24.96738052368164),
        ('dist_vwap_atr', '<=', -1.386819064617157),
        ('ofi_5', '<=', 731.8138122558594),
        ('range_pos_50', '>', 0.06156914494931698),
        ('dist_pdh_atr', '>', -76.63924407958984),
        ('dist_pdl_atr', '<=', -37.81321144104004),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS12T12_0024:
    name = 'V3_SHORT_S12T12_008'
    side = 'SHORT'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.5738358035137487
    cpcv_min_wr = 0.5171339563862928
    constraints = [
        ('atr_14', '>', 3.5315141677856445),
        ('atr_14', '>', 4.836634397506714),
        ('dist_pdh_atr', '>', -6.872745037078857),
        ('range_pos_200', '>', 0.9080181419849396),
        ('atr_50', '>', 5.339649438858032),
        ('atr_50', '>', 10.103973865509033),
        ('autocorr_20', '<=', 0.02987294364720583),
        ('dist_pdh_atr', '>', 19.292261123657227),
        ('reflex_10', '<=', 3.6517616510391235),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS12T12_0025:
    name = 'V3_SHORT_S12T12_009'
    side = 'SHORT'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.603531360809359
    cpcv_min_wr = 0.5368421052631579
    constraints = [
        ('atr_14', '>', 3.5315141677856445),
        ('atr_14', '>', 4.836634397506714),
        ('dist_pdh_atr', '>', -6.872745037078857),
        ('range_pos_200', '>', 0.9080181419849396),
        ('atr_50', '>', 5.339649438858032),
        ('atr_50', '<=', 10.103973865509033),
        ('ofi_20', '>', 2384.9735107421875),
        ('sigma_ratio_1_15', '>', 2.660664677619934),
        ('ret_20', '<=', 38.625),
        ('hurst_proxy_50', '>', 1.7415627241134644),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS12T12_0026:
    name = 'V3_SHORT_S12T12_010'
    side = 'SHORT'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.6045594367336402
    cpcv_min_wr = 0.5133333333333333
    constraints = [
        ('atr_14', '>', 3.5315141677856445),
        ('atr_14', '>', 4.836634397506714),
        ('dist_pdh_atr', '>', -6.872745037078857),
        ('range_pos_200', '>', 0.9080181419849396),
        ('atr_50', '>', 5.339649438858032),
        ('atr_50', '>', 10.103973865509033),
        ('autocorr_20', '>', 0.02987294364720583),
        ('dist_vwap_atr', '<=', 10.57235860824585),
        ('dist_pdl_atr', '<=', 16.445775985717773),
        ('autocorr_5', '<=', 0.04543016850948334),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS12T12_0027:
    name = 'V3_SHORT_S12T12_011'
    side = 'SHORT'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.5859940271352067
    cpcv_min_wr = 0.4935897435897436
    constraints = [
        ('atr_14', '>', 3.5315141677856445),
        ('atr_14', '>', 4.836634397506714),
        ('dist_pdh_atr', '>', -6.872745037078857),
        ('range_pos_200', '<=', 0.9080181419849396),
        ('atr_5', '<=', 32.400779724121094),
        ('dist_vwap_atr', '<=', 14.663312911987305),
        ('dist_pdh_atr', '>', 22.25608253479004),
        ('atr_5', '>', 8.769699573516846),
        ('dist_low20_atr', '>', 0.8040255010128021),
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

class V3LongS16T16_0028:
    name = 'V3_LONG_S16T16_017'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5938731157228656
    cpcv_min_wr = 0.5203094777562862
    constraints = [
        ('atr_14', '>', 3.4830528497695923),
        ('atr_14', '>', 4.371206760406494),
        ('atr_14', '>', 5.446556091308594),
        ('dist_vwap_atr', '>', 1.5822489857673645),
        ('dist_pdh_atr', '>', 4.586334705352783),
        ('is_close_30min', '<=', 0.5),
        ('atr_50', '<=', 7.376214504241943),
        ('dist_pdh_atr', '<=', 52.035888671875),
        ('autocorr_20', '<=', -0.08377523347735405),
        ('atr_50', '>', 5.693782329559326),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS16T16_0029:
    name = 'V3_LONG_S16T16_018'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.572345130296154
    cpcv_min_wr = 0.5290037831021438
    constraints = [
        ('atr_14', '>', 3.4830528497695923),
        ('atr_14', '>', 4.371206760406494),
        ('atr_14', '>', 5.446556091308594),
        ('dist_vwap_atr', '>', 1.5822489857673645),
        ('dist_pdh_atr', '<=', 4.586334705352783),
        ('dist_pdl_atr', '<=', 69.09688186645508),
        ('hurst_proxy_50', '<=', 1.5376187562942505),
        ('atr_50', '>', 6.177837371826172),
        ('atr_50', '<=', 7.897101640701294),
        ('range_pos_200', '<=', 0.7669987976551056),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS16T16_0030:
    name = 'V3_LONG_S16T16_019'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5790032287047435
    cpcv_min_wr = 0.5471521942110178
    constraints = [
        ('atr_14', '>', 3.4830528497695923),
        ('atr_14', '>', 4.371206760406494),
        ('atr_14', '>', 5.446556091308594),
        ('dist_vwap_atr', '<=', 1.5822489857673645),
        ('ny_hour', '>', 14.5),
        ('atr_14', '>', 9.484745025634766),
        ('dist_pdl_atr', '<=', 18.267925262451172),
        ('dow', '<=', 3.5),
        ('hurst_proxy_50', '<=', 1.3589122295379639),
        ('atr_50', '<=', 12.333449363708496),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS16T16_0031:
    name = 'V3_LONG_S16T16_020'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.6224355515943581
    cpcv_min_wr = 0.5013661202185792
    constraints = [
        ('atr_14', '>', 3.4830528497695923),
        ('atr_14', '>', 4.371206760406494),
        ('atr_14', '>', 5.446556091308594),
        ('dist_vwap_atr', '<=', 1.5822489857673645),
        ('ny_hour', '<=', 14.5),
        ('dist_pdh_atr', '<=', -51.93195915222168),
        ('atr_50', '>', 7.955554485321045),
        ('sigma_ratio_1_15', '>', 1.3092020750045776),
        ('atr_14', '>', 9.347746849060059),
        ('dist_eq50_atr', '<=', -1.3853703141212463),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS16T16_0032:
    name = 'V3_LONG_S16T16_021'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.651332728759677
    cpcv_min_wr = 0.5372050816696915
    constraints = [
        ('atr_14', '>', 3.4830528497695923),
        ('atr_14', '>', 4.371206760406494),
        ('atr_14', '>', 5.446556091308594),
        ('dist_vwap_atr', '>', 1.5822489857673645),
        ('dist_pdh_atr', '>', 4.586334705352783),
        ('is_close_30min', '<=', 0.5),
        ('atr_50', '>', 7.376214504241943),
        ('dist_pdl_atr', '<=', 51.05826377868652),
        ('autocorr_20', '<=', -0.291581928730011),
        ('atr_5', '>', 8.597645282745361),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS16T16_0033:
    name = 'V3_LONG_S16T16_022'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.6791049397650596
    cpcv_min_wr = 0.5791666666666667
    constraints = [
        ('atr_14', '>', 3.4830528497695923),
        ('atr_14', '>', 4.371206760406494),
        ('atr_14', '>', 5.446556091308594),
        ('dist_vwap_atr', '>', 1.5822489857673645),
        ('dist_pdh_atr', '>', 4.586334705352783),
        ('is_close_30min', '<=', 0.5),
        ('atr_50', '<=', 7.376214504241943),
        ('dist_pdh_atr', '<=', 52.035888671875),
        ('autocorr_20', '>', -0.08377523347735405),
        ('ema_slope_20', '>', 4.556445837020874),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS16T16_0034:
    name = 'V3_LONG_S16T16_023'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5394215614291665
    cpcv_min_wr = 0.4943181818181818
    constraints = [
        ('atr_14', '>', 3.4830528497695923),
        ('atr_14', '>', 4.371206760406494),
        ('atr_14', '>', 5.446556091308594),
        ('dist_vwap_atr', '<=', 1.5822489857673645),
        ('ny_hour', '<=', 14.5),
        ('dist_pdh_atr', '<=', -51.93195915222168),
        ('atr_50', '>', 7.955554485321045),
        ('sigma_ratio_1_15', '>', 1.3092020750045776),
        ('atr_14', '>', 9.347746849060059),
        ('dist_eq50_atr', '>', -1.3853703141212463),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS16T16_0035:
    name = 'V3_LONG_S16T16_024'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5601363633582442
    cpcv_min_wr = 0.5220458553791887
    constraints = [
        ('atr_14', '>', 3.4830528497695923),
        ('atr_14', '>', 4.371206760406494),
        ('atr_14', '>', 5.446556091308594),
        ('dist_vwap_atr', '<=', 1.5822489857673645),
        ('ny_hour', '>', 14.5),
        ('atr_14', '<=', 9.484745025634766),
        ('dist_pdh_atr', '>', -30.08091926574707),
        ('atr_14', '>', 6.560628890991211),
        ('dist_vwap_atr', '>', 0.29977627098560333),
        ('atr_14', '>', 7.3804051876068115),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS16T16_0036:
    name = 'V3_LONG_S16T16_025'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.6170575187701832
    cpcv_min_wr = 0.515748031496063
    constraints = [
        ('atr_14', '>', 3.4830528497695923),
        ('atr_14', '>', 4.371206760406494),
        ('atr_14', '>', 5.446556091308594),
        ('dist_vwap_atr', '<=', 1.5822489857673645),
        ('ny_hour', '>', 14.5),
        ('atr_14', '>', 9.484745025634766),
        ('dist_pdl_atr', '<=', 18.267925262451172),
        ('dow', '>', 3.5),
        ('dist_eq50_atr', '<=', -0.22745376825332642),
        ('dist_pdl_atr', '>', 3.770524263381958),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS16T16_0037:
    name = 'V3_LONG_S16T16_026'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5710016451314462
    cpcv_min_wr = 0.5
    constraints = [
        ('atr_14', '>', 3.4830528497695923),
        ('atr_14', '>', 4.371206760406494),
        ('atr_14', '<=', 5.446556091308594),
        ('dist_vwap_atr', '>', 6.423284530639648),
        ('hurst_proxy_50', '<=', 1.329709529876709),
        ('range_pos_50', '>', 0.7855609953403473),
        ('ema_distance', '>', 1.5712488889694214),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS16T16_0038:
    name = 'V3_SHORT_S16T16_012'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5607609617390722
    cpcv_min_wr = 0.5186827105763141
    constraints = [
        ('atr_14', '>', 3.8643712997436523),
        ('atr_14', '>', 4.931562662124634),
        ('dist_vwap_atr', '>', 1.7995506525039673),
        ('atr_50', '<=', 7.45496392250061),
        ('ema_slope_20', '<=', 4.101552724838257),
        ('dist_pdh_atr', '>', 4.586323022842407),
        ('dist_pdh_atr', '<=', 51.06937789916992),
        ('ny_hour', '>', 14.5),
        ('dist_vwap_atr', '>', 10.391116619110107),
        ('ny_minute', '>', 8.5),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS16T16_0039:
    name = 'V3_SHORT_S16T16_013'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5522265949757175
    cpcv_min_wr = 0.48873483535528595
    constraints = [
        ('atr_14', '>', 3.8643712997436523),
        ('atr_14', '>', 4.931562662124634),
        ('dist_vwap_atr', '>', 1.7995506525039673),
        ('atr_50', '>', 7.45496392250061),
        ('dist_pdl_atr', '>', 11.069048404693604),
        ('dist_vwap_atr', '>', 3.237857699394226),
        ('dist_pdh_atr', '>', -26.23423480987549),
        ('dist_pdl_atr', '<=', 50.70129203796387),
        ('range_pos_50', '<=', 0.26840560138225555),
        ('atr_50', '<=', 10.918565273284912),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS16T16_0040:
    name = 'V3_SHORT_S16T16_014'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.6412859122194199
    cpcv_min_wr = 0.5454545454545454
    constraints = [
        ('atr_14', '>', 3.8643712997436523),
        ('atr_14', '>', 4.931562662124634),
        ('dist_vwap_atr', '<=', 1.7995506525039673),
        ('atr_50', '<=', 6.2363340854644775),
        ('ret_20', '>', -25.125),
        ('ny_hour', '<=', 11.5),
        ('dist_pdl_atr', '>', -15.425897598266602),
        ('dist_pdl_atr', '>', 12.151120662689209),
        ('dist_pdh_atr', '<=', -7.225845098495483),
        ('range_pos_200', '>', 0.4475998431444168),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS16T16_0041:
    name = 'V3_SHORT_S16T16_015'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.6879678475726744
    cpcv_min_wr = 0.5441696113074205
    constraints = [
        ('atr_14', '>', 3.8643712997436523),
        ('atr_14', '>', 4.931562662124634),
        ('dist_vwap_atr', '>', 1.7995506525039673),
        ('atr_50', '<=', 7.45496392250061),
        ('ema_slope_20', '<=', 4.101552724838257),
        ('dist_pdh_atr', '<=', 4.586323022842407),
        ('dow', '>', 2.5),
        ('hurst_proxy_50', '<=', 2.193789482116699),
        ('dist_pdl_atr', '<=', 1.6952741146087646),
        ('dist_pdh_atr', '>', -29.937230110168457),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS16T16_0042:
    name = 'V3_SHORT_S16T16_016'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.6530025791594536
    cpcv_min_wr = 0.5153846153846153
    constraints = [
        ('atr_14', '>', 3.8643712997436523),
        ('atr_14', '>', 4.931562662124634),
        ('dist_vwap_atr', '<=', 1.7995506525039673),
        ('atr_50', '>', 6.2363340854644775),
        ('atr_14', '<=', 23.066667556762695),
        ('dist_pdh_atr', '>', -7.569854497909546),
        ('ema_distance', '<=', -2.693841576576233),
        ('sigma_ratio_1_5', '<=', 0.9835316836833954),
        ('ofi_5', '>', -2887.9930419921875),
        ('sigma_ratio_1_15', '<=', 1.2447233200073242),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS16T16_0043:
    name = 'V3_SHORT_S16T16_017'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.6658447522704816
    cpcv_min_wr = 0.5283018867924528
    constraints = [
        ('atr_14', '>', 3.8643712997436523),
        ('atr_14', '>', 4.931562662124634),
        ('dist_vwap_atr', '>', 1.7995506525039673),
        ('atr_50', '>', 7.45496392250061),
        ('dist_pdl_atr', '>', 11.069048404693604),
        ('dist_vwap_atr', '>', 3.237857699394226),
        ('dist_pdh_atr', '<=', -26.23423480987549),
        ('ny_minute', '>', 28.5),
        ('dist_pdl_atr', '<=', 20.463836669921875),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS16T16_0044:
    name = 'V3_SHORT_S16T16_018'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5804343603197301
    cpcv_min_wr = 0.553921568627451
    constraints = [
        ('atr_14', '>', 3.8643712997436523),
        ('atr_14', '>', 4.931562662124634),
        ('dist_vwap_atr', '>', 1.7995506525039673),
        ('atr_50', '>', 7.45496392250061),
        ('dist_pdl_atr', '>', 11.069048404693604),
        ('dist_vwap_atr', '>', 3.237857699394226),
        ('dist_pdh_atr', '<=', -26.23423480987549),
        ('ny_minute', '>', 28.5),
        ('dist_pdl_atr', '>', 20.463836669921875),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0045:
    name = 'V3_LONG_S20T20_027'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.5650558061405759
    cpcv_min_wr = 0.5072374499538035
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '>', 5.3883140087127686),
        ('dist_vwap_atr', '<=', 1.6508015394210815),
        ('atr_14', '>', 7.110764503479004),
        ('ny_hour', '<=', 14.5),
        ('autocorr_20', '<=', -0.1486605852842331),
        ('dist_vwap_atr', '<=', -4.7953972816467285),
        ('ny_hour', '<=', 13.5),
        ('dist_pdh_atr', '<=', -6.30812668800354),
        ('dist_eq50_atr', '<=', 1.603538691997528),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0046:
    name = 'V3_LONG_S20T20_028'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.5558215345835968
    cpcv_min_wr = 0.5270718232044199
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '>', 5.3883140087127686),
        ('dist_vwap_atr', '<=', 1.6508015394210815),
        ('atr_14', '>', 7.110764503479004),
        ('ny_hour', '>', 14.5),
        ('atr_50', '>', 10.434672355651855),
        ('dist_pdl_atr', '<=', 17.783547401428223),
        ('ofi_20', '>', -3355.2794189453125),
        ('ny_minute', '<=', 15.5),
        ('dist_pdh_atr', '>', -21.49852180480957),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0047:
    name = 'V3_LONG_S20T20_029'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.5728369023031269
    cpcv_min_wr = 0.52
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '>', 5.3883140087127686),
        ('dist_vwap_atr', '<=', 1.6508015394210815),
        ('atr_14', '<=', 7.110764503479004),
        ('dist_pdh_atr', '>', -53.00741386413574),
        ('dist_pdl_atr', '>', -34.83729362487793),
        ('dist_pdh_atr', '>', -28.689464569091797),
        ('ny_hour', '<=', 14.5),
        ('atr_14', '>', 5.9254491329193115),
        ('autocorr_20', '<=', -0.25376784801483154),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0048:
    name = 'V3_LONG_S20T20_030'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.683775890305593
    cpcv_min_wr = 0.6025641025641025
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '>', 5.3883140087127686),
        ('dist_vwap_atr', '>', 1.6508015394210815),
        ('atr_50', '<=', 6.212240695953369),
        ('dist_pdh_atr', '>', 0.7070620656013489),
        ('dist_vwap_atr', '<=', 12.688347816467285),
        ('ema_slope_20', '<=', 4.551342964172363),
        ('range_pos_200', '<=', 0.5837914943695068),
        ('range_expansion_5', '<=', 1.1940688490867615),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0049:
    name = 'V3_LONG_S20T20_031'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.583726559115002
    cpcv_min_wr = 0.48043818466353677
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '>', 5.3883140087127686),
        ('dist_vwap_atr', '>', 1.6508015394210815),
        ('atr_50', '>', 6.212240695953369),
        ('atr_50', '>', 9.303894519805908),
        ('hurst_proxy_50', '>', 0.9334892630577087),
        ('dist_pdl_atr', '>', 64.38891983032227),
        ('dow', '>', 2.5),
        ('atr_50', '<=', 11.144440174102783),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0050:
    name = 'V3_LONG_S20T20_032'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.5556274446228766
    cpcv_min_wr = 0.4978540772532189
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '>', 5.3883140087127686),
        ('dist_vwap_atr', '<=', 1.6508015394210815),
        ('atr_14', '>', 7.110764503479004),
        ('ny_hour', '>', 14.5),
        ('atr_50', '>', 10.434672355651855),
        ('dist_pdl_atr', '>', 17.783547401428223),
        ('hurst_proxy_50', '<=', 1.772596538066864),
        ('reflex_10', '>', 3.059368371963501),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0051:
    name = 'V3_LONG_S20T20_033'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.5693972518175209
    cpcv_min_wr = 0.5127118644067796
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '>', 5.3883140087127686),
        ('dist_vwap_atr', '<=', 1.6508015394210815),
        ('atr_14', '>', 7.110764503479004),
        ('ny_hour', '<=', 14.5),
        ('autocorr_20', '>', -0.1486605852842331),
        ('dist_pdh_atr', '<=', -51.93326187133789),
        ('sigma_ratio_1_15', '>', 1.3095135688781738),
        ('atr_14', '>', 9.368990421295166),
        ('hurst_proxy_50', '<=', 1.671325445175171),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0052:
    name = 'V3_LONG_S20T20_034'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.5785494685803814
    cpcv_min_wr = 0.5120481927710844
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '>', 5.3883140087127686),
        ('dist_vwap_atr', '<=', 1.6508015394210815),
        ('atr_14', '>', 7.110764503479004),
        ('ny_hour', '<=', 14.5),
        ('autocorr_20', '<=', -0.1486605852842331),
        ('dist_vwap_atr', '<=', -4.7953972816467285),
        ('ny_hour', '>', 13.5),
        ('sigma_ratio_1_5', '>', 1.5680353045463562),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0053:
    name = 'V3_LONG_S20T20_035'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.6134518429876877
    cpcv_min_wr = 0.4861878453038674
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '>', 5.3883140087127686),
        ('dist_vwap_atr', '<=', 1.6508015394210815),
        ('atr_14', '>', 7.110764503479004),
        ('ny_hour', '<=', 14.5),
        ('autocorr_20', '>', -0.1486605852842331),
        ('dist_pdh_atr', '<=', -51.93326187133789),
        ('sigma_ratio_1_15', '>', 1.3095135688781738),
        ('atr_14', '>', 9.368990421295166),
        ('hurst_proxy_50', '>', 1.671325445175171),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0054:
    name = 'V3_LONG_S20T20_036'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.6151446845428599
    cpcv_min_wr = 0.5197568389057751
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '<=', 5.3883140087127686),
        ('dist_vwap_atr', '<=', 6.809353590011597),
        ('dist_pdl_atr', '>', 0.393512487411499),
        ('dist_pdh_atr', '>', 7.357413291931152),
        ('dow', '<=', 1.5),
        ('atr_50', '>', 4.944312572479248),
        ('atr_50', '>', 5.6749396324157715),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0055:
    name = 'V3_LONG_S20T20_037'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.6213981930323302
    cpcv_min_wr = 0.5376884422110553
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '>', 5.3883140087127686),
        ('dist_vwap_atr', '<=', 1.6508015394210815),
        ('atr_14', '>', 7.110764503479004),
        ('ny_hour', '<=', 14.5),
        ('autocorr_20', '>', -0.1486605852842331),
        ('dist_pdh_atr', '>', -51.93326187133789),
        ('dist_pdl_atr', '>', 48.9782600402832),
        ('autocorr_5', '<=', 0.1694444939494133),
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS20T20_0056:
    name = 'V3_LONG_S20T20_038'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.5764443102748003
    cpcv_min_wr = 0.48520710059171596
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '>', 5.3883140087127686),
        ('dist_vwap_atr', '>', 1.6508015394210815),
        ('atr_50', '<=', 6.212240695953369),
        ('dist_pdh_atr', '>', 0.7070620656013489),
        ('dist_vwap_atr', '>', 12.688347816467285),
        ('dist_pdl_atr', '<=', 57.194576263427734),
        ('dist_pdl_atr', '>', 40.22197341918945),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0057:
    name = 'V3_LONG_S20T20_039'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.5840963370996362
    cpcv_min_wr = 0.5104895104895105
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '<=', 5.3883140087127686),
        ('dist_vwap_atr', '>', 6.809353590011597),
        ('hurst_proxy_50', '<=', 1.3783873915672302),
        ('autocorr_20', '>', 0.012821635231375694),
        ('atr_14', '>', 4.225718259811401),
        ('dist_vwap_atr', '<=', 9.571287631988525),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS20T20_0058:
    name = 'V3_SHORT_S20T20_019'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.642487422405511
    cpcv_min_wr = 0.6259067357512953
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('atr_14', '>', 6.479059934616089),
        ('dist_vwap_atr', '<=', 1.9368405938148499),
        ('dist_vwap_atr', '<=', -1.760023057460785),
        ('dist_pdh_atr', '>', -76.73511505126953),
        ('ofi_20', '>', -3156.9373779296875),
        ('ny_minute', '<=', 48.5),
        ('ofi_5', '<=', 4057.5797119140625),
        ('dist_pdl_atr', '>', 32.94671440124512),
        ('dow', '>', 2.5),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS20T20_0059:
    name = 'V3_SHORT_S20T20_020'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.6107836218659184
    cpcv_min_wr = 0.49396267837541163
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('atr_14', '>', 6.479059934616089),
        ('dist_vwap_atr', '>', 1.9368405938148499),
        ('atr_50', '>', 9.303894519805908),
        ('dist_pdl_atr', '>', 64.1672477722168),
        ('dow', '<=', 2.5),
        ('sigma_ratio_1_5', '<=', 1.1841718554496765),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS20T20_0060:
    name = 'V3_SHORT_S20T20_021'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.6401982973777484
    cpcv_min_wr = 0.5492610837438424
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('atr_14', '>', 6.479059934616089),
        ('dist_vwap_atr', '>', 1.9368405938148499),
        ('atr_50', '>', 9.303894519805908),
        ('dist_pdl_atr', '<=', 64.1672477722168),
        ('dist_pdl_atr', '<=', 9.636948585510254),
        ('below_pdl_count_20', '<=', 7.5),
        ('atr_50', '>', 9.839427947998047),
        ('dist_vwap_atr', '>', 7.2471489906311035),
        ('ny_minute', '<=', 32.5),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS20T20_0061:
    name = 'V3_SHORT_S20T20_022'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.7215903202323773
    cpcv_min_wr = 0.5315315315315315
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('atr_14', '<=', 6.479059934616089),
        ('atr_14', '>', 5.069453001022339),
        ('dist_pdh_atr', '<=', 5.450583457946777),
        ('dist_pdh_atr', '>', -55.55416297912598),
        ('dist_pdl_atr', '<=', -23.00417137145996),
        ('atr_50', '>', 5.771270990371704),
        ('dist_vwap_atr', '>', -6.727622985839844),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS20T20_0062:
    name = 'V3_SHORT_S20T20_023'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.642323182557275
    cpcv_min_wr = 0.5138121546961326
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('atr_14', '>', 6.479059934616089),
        ('dist_vwap_atr', '>', 1.9368405938148499),
        ('atr_50', '<=', 9.303894519805908),
        ('dist_pdh_atr', '>', -24.197967529296875),
        ('hurst_proxy_50', '>', 1.0948295593261719),
        ('dist_pdh_atr', '>', 34.602182388305664),
        ('ny_hour', '>', 12.5),
        ('dow', '<=', 1.5),
        ('atr_50', '>', 7.649400472640991),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS8T8_0063:
    name = 'V3_LONG_S8T8_040'
    side = 'LONG'
    target_pts = 8.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.5266867376227958
    cpcv_min_wr = 0.5007710496555978
    constraints = [
        ('atr_14', '>', 2.706931471824646),
        ('atr_5', '<=', 20.052778244018555),
        ('atr_14', '>', 3.4773783683776855),
        ('atr_5', '<=', 13.589250087738037),
        ('dist_pdh_atr', '>', 4.697079658508301),
        ('is_close_30min', '<=', 0.5),
        ('dist_low20_atr', '>', 0.6921310722827911),
        ('dist_vwap_atr', '>', 2.4648196697235107),
        ('atr_50', '<=', 7.428928375244141),
        ('ny_hour', '>', 10.5),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS8T8_0064:
    name = 'V3_LONG_S8T8_041'
    side = 'LONG'
    target_pts = 8.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.5095783452377594
    cpcv_min_wr = 0.4807200800088899
    constraints = [
        ('atr_14', '>', 2.706931471824646),
        ('atr_5', '<=', 20.052778244018555),
        ('atr_14', '>', 3.4773783683776855),
        ('atr_5', '<=', 13.589250087738037),
        ('dist_pdh_atr', '<=', 4.697079658508301),
        ('dist_vwap_atr', '>', 6.662899971008301),
        ('dist_pdh_atr', '>', -27.764551162719727),
        ('atr_50', '>', 5.283106565475464),
        ('dist_pdl_atr', '>', 9.767869472503662),
        ('atr_50', '>', 5.6671528816223145),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS8T8_0065:
    name = 'V3_LONG_S8T8_042'
    side = 'LONG'
    target_pts = 8.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.5317909659604151
    cpcv_min_wr = 0.5065320665083135
    constraints = [
        ('atr_14', '>', 2.706931471824646),
        ('atr_5', '<=', 20.052778244018555),
        ('atr_14', '>', 3.4773783683776855),
        ('atr_5', '<=', 13.589250087738037),
        ('dist_pdh_atr', '>', 4.697079658508301),
        ('is_close_30min', '<=', 0.5),
        ('dist_low20_atr', '>', 0.6921310722827911),
        ('dist_vwap_atr', '>', 2.4648196697235107),
        ('atr_50', '>', 7.428928375244141),
        ('ofi_20', '>', 3895.6326904296875),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS8T8_0066:
    name = 'V3_LONG_S8T8_043'
    side = 'LONG'
    target_pts = 8.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.5104137101004909
    cpcv_min_wr = 0.4837177747625509
    constraints = [
        ('atr_14', '>', 2.706931471824646),
        ('atr_5', '<=', 20.052778244018555),
        ('atr_14', '>', 3.4773783683776855),
        ('atr_5', '>', 13.589250087738037),
        ('vol_change_3', '<=', 5.466118574142456),
        ('atr_5', '<=', 17.20926284790039),
        ('ofi_5', '<=', -745.1919860839844),
        ('lower_wick_pct', '<=', 0.09422863647341728),
        ('is_close_30min', '<=', 0.5),
        ('ret_1', '>', -17.875),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS8T8_0067:
    name = 'V3_LONG_S8T8_044'
    side = 'LONG'
    target_pts = 8.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.5200385906917437
    cpcv_min_wr = 0.514978601997147
    constraints = [
        ('atr_14', '>', 2.706931471824646),
        ('atr_5', '<=', 20.052778244018555),
        ('atr_14', '>', 3.4773783683776855),
        ('atr_5', '<=', 13.589250087738037),
        ('dist_pdh_atr', '>', 4.697079658508301),
        ('is_close_30min', '<=', 0.5),
        ('dist_low20_atr', '<=', 0.6921310722827911),
        ('sigma_ratio_5_15', '>', 1.6087714433670044),
        ('ofi_20', '>', -3280.375732421875),
        ('dist_vwap_atr', '>', -0.6927914023399353),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS8T8_0068:
    name = 'V3_LONG_S8T8_045'
    side = 'LONG'
    target_pts = 8.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.5129145086704866
    cpcv_min_wr = 0.48482758620689653
    constraints = [
        ('atr_14', '>', 2.706931471824646),
        ('atr_5', '<=', 20.052778244018555),
        ('atr_14', '>', 3.4773783683776855),
        ('atr_5', '>', 13.589250087738037),
        ('vol_change_3', '<=', 5.466118574142456),
        ('atr_5', '<=', 17.20926284790039),
        ('ofi_5', '<=', -745.1919860839844),
        ('lower_wick_pct', '>', 0.09422863647341728),
        ('dist_high20_atr', '>', -4.346739053726196),
        ('range_expansion_5', '>', 1.2816312909126282),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS8T8_0069:
    name = 'V3_LONG_S8T8_046'
    side = 'LONG'
    target_pts = 8.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.5260895283139381
    cpcv_min_wr = 0.5047879616963065
    constraints = [
        ('atr_14', '>', 2.706931471824646),
        ('atr_5', '<=', 20.052778244018555),
        ('atr_14', '>', 3.4773783683776855),
        ('atr_5', '<=', 13.589250087738037),
        ('dist_pdh_atr', '<=', 4.697079658508301),
        ('dist_vwap_atr', '<=', 6.662899971008301),
        ('atr_5', '>', 5.191962480545044),
        ('ema_distance', '<=', 4.475109815597534),
        ('range_pos_200', '<=', 0.008088434115052223),
        ('range_expansion_5', '>', 0.9293066561222076),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS8T8_0070:
    name = 'V3_LONG_S8T8_047'
    side = 'LONG'
    target_pts = 8.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.5299172223069597
    cpcv_min_wr = 0.4654696132596685
    constraints = [
        ('atr_14', '>', 2.706931471824646),
        ('atr_5', '<=', 20.052778244018555),
        ('atr_14', '>', 3.4773783683776855),
        ('atr_5', '<=', 13.589250087738037),
        ('dist_pdh_atr', '<=', 4.697079658508301),
        ('dist_vwap_atr', '>', 6.662899971008301),
        ('dist_pdh_atr', '>', -27.764551162719727),
        ('atr_50', '>', 5.283106565475464),
        ('dist_pdl_atr', '<=', 9.767869472503662),
        ('below_pdl_count_20', '>', 14.5),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS8T8_0071:
    name = 'V3_LONG_S8T8_048'
    side = 'LONG'
    target_pts = 8.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.5930866397654475
    cpcv_min_wr = 0.5229357798165137
    constraints = [
        ('atr_14', '>', 2.706931471824646),
        ('atr_5', '<=', 20.052778244018555),
        ('atr_14', '>', 3.4773783683776855),
        ('atr_5', '<=', 13.589250087738037),
        ('dist_pdh_atr', '<=', 4.697079658508301),
        ('dist_vwap_atr', '<=', 6.662899971008301),
        ('atr_5', '<=', 5.191962480545044),
        ('dist_pdl_atr', '>', 5.072266101837158),
        ('rsi_14', '<=', 38.90500259399414),
        ('dist_vwap_atr', '>', 1.751828670501709),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS8T8_0072:
    name = 'V3_LONG_S8T8_049'
    side = 'LONG'
    target_pts = 8.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.5411222944220058
    cpcv_min_wr = 0.4854368932038835
    constraints = [
        ('atr_14', '>', 2.706931471824646),
        ('atr_5', '<=', 20.052778244018555),
        ('atr_14', '>', 3.4773783683776855),
        ('atr_5', '<=', 13.589250087738037),
        ('dist_pdh_atr', '>', 4.697079658508301),
        ('is_close_30min', '>', 0.5),
        ('autocorr_5', '<=', -0.2259875312447548),
        ('ret_5', '<=', -6.375),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS8T8_0073:
    name = 'V3_LONG_S8T8_050'
    side = 'LONG'
    target_pts = 8.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.532640716755587
    cpcv_min_wr = 0.5079365079365079
    constraints = [
        ('atr_14', '>', 2.706931471824646),
        ('atr_5', '<=', 20.052778244018555),
        ('atr_14', '>', 3.4773783683776855),
        ('atr_5', '<=', 13.589250087738037),
        ('dist_pdh_atr', '<=', 4.697079658508301),
        ('dist_vwap_atr', '>', 6.662899971008301),
        ('dist_pdh_atr', '<=', -27.764551162719727),
        ('atr_50', '>', 7.797171115875244),
        ('atr_50', '>', 8.996849060058594),
        ('ret_20', '<=', 15.125),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS8T8_0074:
    name = 'V3_SHORT_S8T8_024'
    side = 'SHORT'
    target_pts = 8.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.5295336175821516
    cpcv_min_wr = 0.5061576354679803
    constraints = [
        ('atr_14', '>', 2.374924063682556),
        ('atr_14', '>', 3.206903338432312),
        ('atr_5', '<=', 20.57501792907715),
        ('atr_14', '<=', 4.700930833816528),
        ('atr_50', '>', 4.3152546882629395),
        ('dist_vwap_atr', '<=', 6.671597719192505),
        ('atr_5', '>', 3.2094651460647583),
        ('range_pos_200', '>', 0.11066866666078568),
        ('dist_pdl_atr', '>', 5.151207685470581),
        ('dist_pdl_atr', '<=', 31.74363613128662),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS8T8_0075:
    name = 'V3_SHORT_S8T8_025'
    side = 'SHORT'
    target_pts = 8.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.5283393395446564
    cpcv_min_wr = 0.4960552268244576
    constraints = [
        ('atr_14', '>', 2.374924063682556),
        ('atr_14', '>', 3.206903338432312),
        ('atr_5', '<=', 20.57501792907715),
        ('atr_14', '>', 4.700930833816528),
        ('atr_5', '<=', 15.112215518951416),
        ('dist_pdh_atr', '>', -7.484505653381348),
        ('ema_distance', '>', 2.8988640308380127),
        ('dist_high20_atr', '>', -0.8197844326496124),
        ('ofi_20', '<=', 4183.590087890625),
        ('ny_minute', '>', 32.5),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS8T8_0076:
    name = 'V3_SHORT_S8T8_026'
    side = 'SHORT'
    target_pts = 8.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.5275859605823718
    cpcv_min_wr = 0.484
    constraints = [
        ('atr_14', '>', 2.374924063682556),
        ('atr_14', '>', 3.206903338432312),
        ('atr_5', '<=', 20.57501792907715),
        ('atr_14', '>', 4.700930833816528),
        ('atr_5', '<=', 15.112215518951416),
        ('dist_pdh_atr', '<=', -7.484505653381348),
        ('ofi_5', '>', -1674.56591796875),
        ('is_open_30min', '>', 0.5),
        ('ny_minute', '>', 30.5),
        ('dist_pdl_atr', '<=', -0.5113499164581299),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS8T8_0077:
    name = 'V3_SHORT_S8T8_027'
    side = 'SHORT'
    target_pts = 8.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.5171097234355272
    cpcv_min_wr = 0.4830917874396135
    constraints = [
        ('atr_14', '>', 2.374924063682556),
        ('atr_14', '>', 3.206903338432312),
        ('atr_5', '<=', 20.57501792907715),
        ('atr_14', '>', 4.700930833816528),
        ('atr_5', '<=', 15.112215518951416),
        ('dist_pdh_atr', '>', -7.484505653381348),
        ('ema_distance', '>', 2.8988640308380127),
        ('dist_high20_atr', '<=', -0.8197844326496124),
        ('atr_14', '>', 12.823307991027832),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS8T8_0078:
    name = 'V3_SHORT_S8T8_028'
    side = 'SHORT'
    target_pts = 8.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.5506692176170584
    cpcv_min_wr = 0.5
    constraints = [
        ('atr_14', '>', 2.374924063682556),
        ('atr_14', '>', 3.206903338432312),
        ('atr_5', '<=', 20.57501792907715),
        ('atr_14', '<=', 4.700930833816528),
        ('atr_50', '>', 4.3152546882629395),
        ('dist_vwap_atr', '>', 6.671597719192505),
        ('dow', '>', 3.5),
        ('autocorr_5', '>', -0.08135323226451874),
        ('dist_vwap_atr', '>', 8.691595554351807),
        ('range_pos_200', '<=', 0.9320142865180969),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS12T12_0079:
    name = 'V3_LONG_S12T12_051'
    side = 'LONG'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.5173688712669088
    cpcv_min_wr = 0.4951581269919098
    constraints = [
        ('atr_14', '>', 3.112475275993347),
        ('atr_14', '>', 3.9063631296157837),
        ('dist_vwap_atr', '>', 1.9870991110801697),
        ('dist_pdh_atr', '<=', 2.7288014888763428),
        ('atr_14', '>', 5.560963153839111),
        ('atr_5', '<=', 20.869565963745117),
        ('dist_eq50_atr', '<=', 5.617683172225952),
        ('dist_pdh_atr', '>', -22.797100067138672),
        ('hurst_proxy_50', '<=', 2.1211520433425903),
        ('hurst_proxy_50', '<=', 1.5938084125518799),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS12T12_0080:
    name = 'V3_LONG_S12T12_052'
    side = 'LONG'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.5173568651497169
    cpcv_min_wr = 0.48635235732009924
    constraints = [
        ('atr_14', '>', 3.112475275993347),
        ('atr_14', '>', 3.9063631296157837),
        ('dist_vwap_atr', '<=', 1.9870991110801697),
        ('atr_14', '>', 4.41860818862915),
        ('atr_5', '<=', 27.248538970947266),
        ('dist_pdl_atr', '>', -36.779632568359375),
        ('range_pos_50', '>', 0.05113895796239376),
        ('ema_slope_20', '<=', -2.3581345081329346),
        ('atr_50', '>', 5.200146436691284),
        ('dist_pdl_atr', '>', 29.172560691833496),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS12T12_0081:
    name = 'V3_LONG_S12T12_053'
    side = 'LONG'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.6622101449371864
    cpcv_min_wr = 0.5681818181818182
    constraints = [
        ('atr_14', '>', 3.112475275993347),
        ('atr_14', '>', 3.9063631296157837),
        ('dist_vwap_atr', '<=', 1.9870991110801697),
        ('atr_14', '<=', 4.41860818862915),
        ('dist_pdl_atr', '<=', 5.501065015792847),
        ('ema_slope_20', '>', -0.5653915405273438),
        ('autocorr_20', '<=', -0.0047715900000184774),
        ('autocorr_5', '<=', -0.08553231135010719),
        ('dist_pdh_atr', '>', -23.394363403320312),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS12T12_0082:
    name = 'V3_LONG_S12T12_054'
    side = 'LONG'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.5327891334910928
    cpcv_min_wr = 0.47701149425287354
    constraints = [
        ('atr_14', '>', 3.112475275993347),
        ('atr_14', '>', 3.9063631296157837),
        ('dist_vwap_atr', '>', 1.9870991110801697),
        ('dist_pdh_atr', '>', 2.7288014888763428),
        ('is_close_30min', '<=', 0.5),
        ('ofi_20', '>', 2388.6744384765625),
        ('sigma_ratio_1_15', '<=', 2.8405243158340454),
        ('atr_50', '>', 9.415329933166504),
        ('range_pos_200', '<=', 0.810725748538971),
        ('dow', '<=', 2.5),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS12T12_0083:
    name = 'V3_LONG_S12T12_055'
    side = 'LONG'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.5542337418434481
    cpcv_min_wr = 0.46153846153846156
    constraints = [
        ('atr_14', '>', 3.112475275993347),
        ('atr_14', '>', 3.9063631296157837),
        ('dist_vwap_atr', '>', 1.9870991110801697),
        ('dist_pdh_atr', '>', 2.7288014888763428),
        ('is_close_30min', '>', 0.5),
        ('dist_vwap_atr', '<=', 10.43358850479126),
        ('dist_pdl_atr', '<=', 20.019065856933594),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS12T12_0084:
    name = 'V3_SHORT_S12T12_029'
    side = 'SHORT'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.5196961902309276
    cpcv_min_wr = 0.49646660694734746
    constraints = [
        ('atr_14', '>', 3.5315141677856445),
        ('atr_14', '>', 4.836634397506714),
        ('dist_pdh_atr', '<=', -6.872745037078857),
        ('atr_5', '<=', 24.96738052368164),
        ('dist_vwap_atr', '<=', -1.386819064617157),
        ('ofi_5', '>', 731.8138122558594),
        ('atr_14', '>', 5.36432147026062),
        ('hurst_proxy_50', '<=', 2.3930145502090454),
        ('ofi_20', '<=', 5558.2216796875),
        ('bar_seq_5', '<=', 230.5),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS12T12_0085:
    name = 'V3_SHORT_S12T12_030'
    side = 'SHORT'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.5144587721180549
    cpcv_min_wr = 0.49962497656103505
    constraints = [
        ('atr_14', '>', 3.5315141677856445),
        ('atr_14', '>', 4.836634397506714),
        ('dist_pdh_atr', '<=', -6.872745037078857),
        ('atr_5', '<=', 24.96738052368164),
        ('dist_vwap_atr', '>', -1.386819064617157),
        ('dist_pdh_atr', '<=', -22.781721115112305),
        ('atr_50', '>', 5.087145090103149),
        ('hurst_proxy_50', '>', 0.9313125908374786),
        ('sigma_ratio_1_15', '<=', 2.8627841472625732),
        ('dist_pdh_atr', '>', -32.56195259094238),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS12T12_0086:
    name = 'V3_SHORT_S12T12_031'
    side = 'SHORT'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.5267004278433192
    cpcv_min_wr = 0.486231884057971
    constraints = [
        ('atr_14', '>', 3.5315141677856445),
        ('atr_14', '>', 4.836634397506714),
        ('dist_pdh_atr', '<=', -6.872745037078857),
        ('atr_5', '<=', 24.96738052368164),
        ('dist_vwap_atr', '>', -1.386819064617157),
        ('dist_pdh_atr', '>', -22.781721115112305),
        ('atr_50', '>', 5.435238838195801),
        ('atr_50', '<=', 6.128902912139893),
        ('hurst_proxy_50', '>', 1.1946370005607605),
        ('sigma_ratio_1_15', '>', 1.2696569561958313),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS12T12_0087:
    name = 'V3_SHORT_S12T12_032'
    side = 'SHORT'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.5489465292997997
    cpcv_min_wr = 0.4752475247524752
    constraints = [
        ('atr_14', '>', 3.5315141677856445),
        ('atr_14', '>', 4.836634397506714),
        ('dist_pdh_atr', '>', -6.872745037078857),
        ('range_pos_200', '>', 0.9080181419849396),
        ('atr_50', '>', 5.339649438858032),
        ('atr_50', '<=', 10.103973865509033),
        ('ofi_20', '<=', 2384.9735107421875),
        ('dist_pdh_atr', '>', 26.122446060180664),
        ('ny_hour', '>', 13.5),
        ('atr_14', '<=', 6.6510279178619385),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS12T12_0088:
    name = 'V3_SHORT_S12T12_033'
    side = 'SHORT'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.6129179757498195
    cpcv_min_wr = 0.4875
    constraints = [
        ('atr_14', '>', 3.5315141677856445),
        ('atr_14', '>', 4.836634397506714),
        ('dist_pdh_atr', '>', -6.872745037078857),
        ('range_pos_200', '<=', 0.9080181419849396),
        ('atr_5', '<=', 32.400779724121094),
        ('dist_vwap_atr', '<=', 14.663312911987305),
        ('dist_pdh_atr', '>', 22.25608253479004),
        ('atr_5', '<=', 8.769699573516846),
        ('dist_vwap_atr', '>', 11.886986255645752),
        ('atr_50', '<=', 5.857391119003296),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS12T12_0089:
    name = 'V3_SHORT_S12T12_034'
    side = 'SHORT'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.5342640951915432
    cpcv_min_wr = 0.4724220623501199
    constraints = [
        ('atr_14', '>', 3.5315141677856445),
        ('atr_14', '>', 4.836634397506714),
        ('dist_pdh_atr', '<=', -6.872745037078857),
        ('atr_5', '>', 24.96738052368164),
        ('atr_5', '<=', 33.141714096069336),
        ('rsi_5', '>', 36.38434982299805),
        ('ret_1', '<=', 24.125),
        ('reflex_10', '>', 5.468762636184692),
        ('range_pos_50', '>', 0.543060302734375),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS12T12_0090:
    name = 'V3_SHORT_S12T12_035'
    side = 'SHORT'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.5844451742826486
    cpcv_min_wr = 0.5033333333333333
    constraints = [
        ('atr_14', '>', 3.5315141677856445),
        ('atr_14', '>', 4.836634397506714),
        ('dist_pdh_atr', '>', -6.872745037078857),
        ('range_pos_200', '<=', 0.9080181419849396),
        ('atr_5', '<=', 32.400779724121094),
        ('dist_vwap_atr', '>', 14.663312911987305),
        ('dist_pdh_atr', '>', 11.962432384490967),
        ('ofi_20', '>', -589.8533630371094),
        ('autocorr_20', '<=', -0.06970175728201866),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS12T12_0091:
    name = 'V3_SHORT_S12T12_036'
    side = 'SHORT'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.5162954016119672
    cpcv_min_wr = 0.488
    constraints = [
        ('atr_14', '>', 3.5315141677856445),
        ('atr_14', '>', 4.836634397506714),
        ('dist_pdh_atr', '<=', -6.872745037078857),
        ('atr_5', '<=', 24.96738052368164),
        ('dist_vwap_atr', '<=', -1.386819064617157),
        ('ofi_5', '>', 731.8138122558594),
        ('atr_14', '>', 5.36432147026062),
        ('hurst_proxy_50', '<=', 2.3930145502090454),
        ('ofi_20', '>', 5558.2216796875),
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

class V3ShortS12T12_0092:
    name = 'V3_SHORT_S12T12_037'
    side = 'SHORT'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.5843347661978585
    cpcv_min_wr = 0.5076142131979695
    constraints = [
        ('atr_14', '<=', 3.5315141677856445),
        ('atr_14', '>', 2.3764352798461914),
        ('dist_eq50_atr', '<=', 0.958788275718689),
        ('dist_vwap_atr', '<=', 0.17614775896072388),
        ('dist_pdl_atr', '>', -2.6853184700012207),
        ('ny_hour', '<=', 11.5),
        ('dow', '<=', 3.5),
        ('hurst_proxy_50', '>', 2.0243613719940186),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS12T12_0093:
    name = 'V3_SHORT_S12T12_038'
    side = 'SHORT'
    target_pts = 12.0
    stop_pts = 12.0
    max_hold_bars = 45
    cpcv_mean_wr = 0.6050753815596909
    cpcv_min_wr = 0.5432098765432098
    constraints = [
        ('atr_14', '>', 3.5315141677856445),
        ('atr_14', '>', 4.836634397506714),
        ('dist_pdh_atr', '>', -6.872745037078857),
        ('range_pos_200', '<=', 0.9080181419849396),
        ('atr_5', '<=', 32.400779724121094),
        ('dist_vwap_atr', '>', 14.663312911987305),
        ('dist_pdh_atr', '>', 11.962432384490967),
        ('ofi_20', '>', -589.8533630371094),
        ('autocorr_20', '>', -0.06970175728201866),
        ('sigma_ratio_1_5', '<=', 1.1047145128250122),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS16T16_0094:
    name = 'V3_LONG_S16T16_056'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5194304941997812
    cpcv_min_wr = 0.48905698436712053
    constraints = [
        ('atr_14', '>', 3.4830528497695923),
        ('atr_14', '>', 4.371206760406494),
        ('atr_14', '>', 5.446556091308594),
        ('dist_vwap_atr', '>', 1.5822489857673645),
        ('dist_pdh_atr', '<=', 4.586334705352783),
        ('dist_pdl_atr', '<=', 69.09688186645508),
        ('hurst_proxy_50', '<=', 1.5376187562942505),
        ('atr_50', '>', 6.177837371826172),
        ('atr_50', '>', 7.897101640701294),
        ('dist_pdh_atr', '>', -10.247646808624268),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS16T16_0095:
    name = 'V3_LONG_S16T16_057'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5239502027349434
    cpcv_min_wr = 0.4765494137353434
    constraints = [
        ('atr_14', '>', 3.4830528497695923),
        ('atr_14', '>', 4.371206760406494),
        ('atr_14', '>', 5.446556091308594),
        ('dist_vwap_atr', '>', 1.5822489857673645),
        ('dist_pdh_atr', '>', 4.586334705352783),
        ('is_close_30min', '<=', 0.5),
        ('atr_50', '>', 7.376214504241943),
        ('dist_pdl_atr', '<=', 51.05826377868652),
        ('autocorr_20', '>', -0.291581928730011),
        ('dow', '<=', 2.5),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS16T16_0096:
    name = 'V3_LONG_S16T16_058'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5421448837792214
    cpcv_min_wr = 0.5215782983970407
    constraints = [
        ('atr_14', '>', 3.4830528497695923),
        ('atr_14', '>', 4.371206760406494),
        ('atr_14', '>', 5.446556091308594),
        ('dist_vwap_atr', '>', 1.5822489857673645),
        ('dist_pdh_atr', '>', 4.586334705352783),
        ('is_close_30min', '<=', 0.5),
        ('atr_50', '<=', 7.376214504241943),
        ('dist_pdh_atr', '<=', 52.035888671875),
        ('autocorr_20', '>', -0.08377523347735405),
        ('ema_slope_20', '<=', 4.556445837020874),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS16T16_0097:
    name = 'V3_LONG_S16T16_059'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5281434659370225
    cpcv_min_wr = 0.49707792207792206
    constraints = [
        ('atr_14', '>', 3.4830528497695923),
        ('atr_14', '>', 4.371206760406494),
        ('atr_14', '>', 5.446556091308594),
        ('dist_vwap_atr', '>', 1.5822489857673645),
        ('dist_pdh_atr', '<=', 4.586334705352783),
        ('dist_pdl_atr', '<=', 69.09688186645508),
        ('hurst_proxy_50', '>', 1.5376187562942505),
        ('atr_50', '>', 4.917927026748657),
        ('dow', '>', 2.5),
        ('hurst_proxy_50', '>', 2.089665174484253),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS16T16_0098:
    name = 'V3_LONG_S16T16_060'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5152796376063599
    cpcv_min_wr = 0.47568523430592397
    constraints = [
        ('atr_14', '>', 3.4830528497695923),
        ('atr_14', '>', 4.371206760406494),
        ('atr_14', '>', 5.446556091308594),
        ('dist_vwap_atr', '<=', 1.5822489857673645),
        ('ny_hour', '<=', 14.5),
        ('dist_pdh_atr', '>', -51.93195915222168),
        ('dist_pdl_atr', '>', -34.84712600708008),
        ('autocorr_20', '<=', -0.25440676510334015),
        ('atr_50', '<=', 8.352328777313232),
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

class V3LongS16T16_0099:
    name = 'V3_LONG_S16T16_061'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5309348203481848
    cpcv_min_wr = 0.4931972789115646
    constraints = [
        ('atr_14', '>', 3.4830528497695923),
        ('atr_14', '>', 4.371206760406494),
        ('atr_14', '>', 5.446556091308594),
        ('dist_vwap_atr', '<=', 1.5822489857673645),
        ('ny_hour', '>', 14.5),
        ('atr_14', '>', 9.484745025634766),
        ('dist_pdl_atr', '<=', 18.267925262451172),
        ('dow', '>', 3.5),
        ('dist_eq50_atr', '<=', -0.22745376825332642),
        ('dist_pdl_atr', '<=', 3.770524263381958),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS16T16_0100:
    name = 'V3_LONG_S16T16_062'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.7099751897501765
    cpcv_min_wr = 0.584
    constraints = [
        ('atr_14', '>', 3.4830528497695923),
        ('atr_14', '>', 4.371206760406494),
        ('atr_14', '<=', 5.446556091308594),
        ('dist_vwap_atr', '<=', 6.423284530639648),
        ('dist_pdl_atr', '>', 9.070555210113525),
        ('dist_pdl_atr', '>', 39.90432929992676),
        ('above_pdh_count_20', '>', 2.5),
        ('dist_pdl_atr', '<=', 52.411848068237305),
        ('range_pos_50', '>', 0.6649551689624786),
        ('dist_pdl_atr', '>', 43.43951988220215),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS16T16_0101:
    name = 'V3_LONG_S16T16_063'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5486563635179699
    cpcv_min_wr = 0.4828711256117455
    constraints = [
        ('atr_14', '>', 3.4830528497695923),
        ('atr_14', '>', 4.371206760406494),
        ('atr_14', '<=', 5.446556091308594),
        ('dist_vwap_atr', '<=', 6.423284530639648),
        ('dist_pdl_atr', '>', 9.070555210113525),
        ('dist_pdl_atr', '<=', 39.90432929992676),
        ('atr_50', '>', 5.360793352127075),
        ('ofi_20', '>', -212.6221466064453),
        ('autocorr_20', '<=', 0.009045818820595741),
        ('ret_20', '<=', 4.125),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS16T16_0102:
    name = 'V3_LONG_S16T16_064'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5731064103478551
    cpcv_min_wr = 0.488135593220339
    constraints = [
        ('atr_14', '>', 3.4830528497695923),
        ('atr_14', '>', 4.371206760406494),
        ('atr_14', '>', 5.446556091308594),
        ('dist_vwap_atr', '>', 1.5822489857673645),
        ('dist_pdh_atr', '>', 4.586334705352783),
        ('is_close_30min', '>', 0.5),
        ('dist_pdl_atr', '>', 19.75087070465088),
        ('hurst_proxy_50', '>', 1.490000307559967),
        ('sigma_ratio_1_5', '<=', 0.9697071015834808),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS16T16_0103:
    name = 'V3_LONG_S16T16_065'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.6571560688873722
    cpcv_min_wr = 0.5025906735751295
    constraints = [
        ('atr_14', '>', 3.4830528497695923),
        ('atr_14', '<=', 4.371206760406494),
        ('dist_vwap_atr', '>', 11.81067705154419),
        ('dist_pdl_atr', '<=', 69.30744934082031),
        ('dist_pdh_atr', '>', 24.345277786254883),
        ('rsi_14', '<=', 60.49250602722168),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS16T16_0104:
    name = 'V3_LONG_S16T16_066'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5878327421794831
    cpcv_min_wr = 0.46153846153846156
    constraints = [
        ('atr_14', '>', 3.4830528497695923),
        ('atr_14', '>', 4.371206760406494),
        ('atr_14', '<=', 5.446556091308594),
        ('dist_vwap_atr', '<=', 6.423284530639648),
        ('dist_pdl_atr', '<=', 9.070555210113525),
        ('dist_pdh_atr', '>', -57.34095764160156),
        ('atr_50', '>', 4.181471824645996),
        ('autocorr_20', '>', -0.13211984932422638),
        ('range_pos_200', '>', 0.43234187364578247),
        ('dist_pdh_atr', '<=', -31.04534149169922),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS16T16_0105:
    name = 'V3_LONG_S16T16_067'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5963697577467597
    cpcv_min_wr = 0.4885057471264368
    constraints = [
        ('atr_14', '>', 3.4830528497695923),
        ('atr_14', '>', 4.371206760406494),
        ('atr_14', '>', 5.446556091308594),
        ('dist_vwap_atr', '>', 1.5822489857673645),
        ('dist_pdh_atr', '>', 4.586334705352783),
        ('is_close_30min', '>', 0.5),
        ('dist_pdl_atr', '<=', 19.75087070465088),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS16T16_0106:
    name = 'V3_LONG_S16T16_068'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5962499838905835
    cpcv_min_wr = 0.48484848484848486
    constraints = [
        ('atr_14', '>', 3.4830528497695923),
        ('atr_14', '>', 4.371206760406494),
        ('atr_14', '<=', 5.446556091308594),
        ('dist_vwap_atr', '>', 6.423284530639648),
        ('hurst_proxy_50', '>', 1.329709529876709),
        ('ema_slope_20', '<=', 4.025903224945068),
        ('dist_pdh_atr', '>', -6.244807958602905),
        ('range_pos_50', '>', 0.5229621529579163),
        ('dist_pdh_atr', '<=', 22.98715877532959),
        ('dist_low20_atr', '<=', 1.0632104277610779),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS16T16_0107:
    name = 'V3_LONG_S16T16_069'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5573682427822078
    cpcv_min_wr = 0.48873873873873874
    constraints = [
        ('atr_14', '>', 3.4830528497695923),
        ('atr_14', '>', 4.371206760406494),
        ('atr_14', '>', 5.446556091308594),
        ('dist_vwap_atr', '<=', 1.5822489857673645),
        ('ny_hour', '>', 14.5),
        ('atr_14', '>', 9.484745025634766),
        ('dist_pdl_atr', '>', 18.267925262451172),
        ('dist_pdh_atr', '<=', -1.4882833361625671),
        ('dist_high20_atr', '>', -3.4875128269195557),
        ('autocorr_20', '>', -0.012409772258251905),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS16T16_0108:
    name = 'V3_LONG_S16T16_070'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5991405687364468
    cpcv_min_wr = 0.5069637883008357
    constraints = [
        ('atr_14', '>', 3.4830528497695923),
        ('atr_14', '>', 4.371206760406494),
        ('atr_14', '>', 5.446556091308594),
        ('dist_vwap_atr', '>', 1.5822489857673645),
        ('dist_pdh_atr', '>', 4.586334705352783),
        ('is_close_30min', '<=', 0.5),
        ('atr_50', '>', 7.376214504241943),
        ('dist_pdl_atr', '<=', 51.05826377868652),
        ('autocorr_20', '<=', -0.291581928730011),
        ('atr_5', '<=', 8.597645282745361),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS16T16_0109:
    name = 'V3_LONG_S16T16_071'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5916303636542632
    cpcv_min_wr = 0.5301204819277109
    constraints = [
        ('atr_14', '>', 3.4830528497695923),
        ('atr_14', '>', 4.371206760406494),
        ('atr_14', '<=', 5.446556091308594),
        ('dist_vwap_atr', '>', 6.423284530639648),
        ('hurst_proxy_50', '<=', 1.329709529876709),
        ('range_pos_50', '<=', 0.7855609953403473),
        ('dist_vwap_atr', '<=', 10.935974597930908),
        ('dist_pdl_atr', '>', 24.051812171936035),
        ('dist_vwap_atr', '<=', 7.890474081039429),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS16T16_0110:
    name = 'V3_SHORT_S16T16_039'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5190377535539697
    cpcv_min_wr = 0.4896878090125724
    constraints = [
        ('atr_14', '>', 3.8643712997436523),
        ('atr_14', '>', 4.931562662124634),
        ('dist_vwap_atr', '<=', 1.7995506525039673),
        ('atr_50', '>', 6.2363340854644775),
        ('atr_14', '<=', 23.066667556762695),
        ('dist_pdh_atr', '<=', -7.569854497909546),
        ('range_pos_200', '>', 0.041826942935585976),
        ('dist_pdh_atr', '>', -80.47700119018555),
        ('ema_distance', '<=', 3.375933527946472),
        ('dist_eq50_atr', '>', 1.6694000363349915),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS16T16_0111:
    name = 'V3_SHORT_S16T16_040'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5174305694387172
    cpcv_min_wr = 0.5082339579784213
    constraints = [
        ('atr_14', '>', 3.8643712997436523),
        ('atr_14', '>', 4.931562662124634),
        ('dist_vwap_atr', '<=', 1.7995506525039673),
        ('atr_50', '>', 6.2363340854644775),
        ('atr_14', '<=', 23.066667556762695),
        ('dist_pdh_atr', '>', -7.569854497909546),
        ('ema_distance', '>', -2.693841576576233),
        ('above_pdh_count_20', '>', 0.5),
        ('hurst_proxy_50', '<=', 1.761301577091217),
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

class V3ShortS16T16_0112:
    name = 'V3_SHORT_S16T16_041'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5330930797921264
    cpcv_min_wr = 0.5023183925811437
    constraints = [
        ('atr_14', '>', 3.8643712997436523),
        ('atr_14', '>', 4.931562662124634),
        ('dist_vwap_atr', '>', 1.7995506525039673),
        ('atr_50', '>', 7.45496392250061),
        ('dist_pdl_atr', '>', 11.069048404693604),
        ('dist_vwap_atr', '>', 3.237857699394226),
        ('dist_pdh_atr', '>', -26.23423480987549),
        ('dist_pdl_atr', '>', 50.70129203796387),
        ('dow', '<=', 3.5),
        ('dist_pdl_atr', '<=', 86.8730583190918),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS16T16_0113:
    name = 'V3_SHORT_S16T16_042'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5344496988318725
    cpcv_min_wr = 0.466182478438493
    constraints = [
        ('atr_14', '>', 3.8643712997436523),
        ('atr_14', '>', 4.931562662124634),
        ('dist_vwap_atr', '>', 1.7995506525039673),
        ('atr_50', '>', 7.45496392250061),
        ('dist_pdl_atr', '<=', 11.069048404693604),
        ('below_pdl_count_20', '<=', 7.5),
        ('dist_eq50_atr', '<=', 5.526617527008057),
        ('ema_slope_20', '>', -1.1886123418807983),
        ('dist_pdl_atr', '<=', 6.590708017349243),
        ('dow', '<=', 2.5),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS16T16_0114:
    name = 'V3_SHORT_S16T16_043'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5401145615475366
    cpcv_min_wr = 0.5088305489260143
    constraints = [
        ('atr_14', '>', 3.8643712997436523),
        ('atr_14', '>', 4.931562662124634),
        ('dist_vwap_atr', '>', 1.7995506525039673),
        ('atr_50', '>', 7.45496392250061),
        ('dist_pdl_atr', '<=', 11.069048404693604),
        ('below_pdl_count_20', '<=', 7.5),
        ('dist_eq50_atr', '<=', 5.526617527008057),
        ('ema_slope_20', '>', -1.1886123418807983),
        ('dist_pdl_atr', '>', 6.590708017349243),
        ('dist_pdh_atr', '<=', -11.880804538726807),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS16T16_0115:
    name = 'V3_SHORT_S16T16_044'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.555501664772828
    cpcv_min_wr = 0.47657841140529533
    constraints = [
        ('atr_14', '>', 3.8643712997436523),
        ('atr_14', '>', 4.931562662124634),
        ('dist_vwap_atr', '<=', 1.7995506525039673),
        ('atr_50', '<=', 6.2363340854644775),
        ('ret_20', '>', -25.125),
        ('ny_hour', '<=', 11.5),
        ('dist_pdl_atr', '>', -15.425897598266602),
        ('dist_pdl_atr', '>', 12.151120662689209),
        ('dist_pdh_atr', '>', -7.225845098495483),
        ('atr_50', '<=', 4.359382629394531),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS16T16_0116:
    name = 'V3_SHORT_S16T16_045'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5394787960887129
    cpcv_min_wr = 0.4792332268370607
    constraints = [
        ('atr_14', '>', 3.8643712997436523),
        ('atr_14', '>', 4.931562662124634),
        ('dist_vwap_atr', '<=', 1.7995506525039673),
        ('atr_50', '<=', 6.2363340854644775),
        ('ret_20', '>', -25.125),
        ('ny_hour', '<=', 11.5),
        ('dist_pdl_atr', '>', -15.425897598266602),
        ('dist_pdl_atr', '<=', 12.151120662689209),
        ('ny_hour', '<=', 10.5),
        ('atr_50', '>', 5.77043890953064),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS16T16_0117:
    name = 'V3_SHORT_S16T16_046'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5761827505401309
    cpcv_min_wr = 0.47869674185463656
    constraints = [
        ('atr_14', '>', 3.8643712997436523),
        ('atr_14', '>', 4.931562662124634),
        ('dist_vwap_atr', '>', 1.7995506525039673),
        ('atr_50', '<=', 7.45496392250061),
        ('ema_slope_20', '<=', 4.101552724838257),
        ('dist_pdh_atr', '>', 4.586323022842407),
        ('dist_pdh_atr', '>', 51.06937789916992),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS16T16_0118:
    name = 'V3_SHORT_S16T16_047'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.7108347364205995
    cpcv_min_wr = 0.6454545454545455
    constraints = [
        ('atr_14', '>', 3.8643712997436523),
        ('atr_14', '>', 4.931562662124634),
        ('dist_vwap_atr', '>', 1.7995506525039673),
        ('atr_50', '>', 7.45496392250061),
        ('dist_pdl_atr', '<=', 11.069048404693604),
        ('below_pdl_count_20', '<=', 7.5),
        ('dist_eq50_atr', '>', 5.526617527008057),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS16T16_0119:
    name = 'V3_SHORT_S16T16_048'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5154549959364226
    cpcv_min_wr = 0.46021220159151194
    constraints = [
        ('atr_14', '>', 3.8643712997436523),
        ('atr_14', '>', 4.931562662124634),
        ('dist_vwap_atr', '>', 1.7995506525039673),
        ('atr_50', '>', 7.45496392250061),
        ('dist_pdl_atr', '>', 11.069048404693604),
        ('dist_vwap_atr', '<=', 3.237857699394226),
        ('hurst_proxy_50', '<=', 2.4572609663009644),
        ('dist_eq50_atr', '<=', 3.390561580657959),
        ('atr_14', '>', 22.704011917114258),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS16T16_0120:
    name = 'V3_SHORT_S16T16_049'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.6501754926136984
    cpcv_min_wr = 0.48226950354609927
    constraints = [
        ('atr_14', '>', 3.8643712997436523),
        ('atr_14', '<=', 4.931562662124634),
        ('range_pos_200', '<=', 0.8911032676696777),
        ('atr_50', '>', 4.447466135025024),
        ('dist_eq50_atr', '<=', 3.1969215869903564),
        ('dow', '<=', 1.5),
        ('dist_vwap_atr', '>', 11.462793827056885),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS16T16_0121:
    name = 'V3_SHORT_S16T16_050'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.5864600797568263
    cpcv_min_wr = 0.47398843930635837
    constraints = [
        ('atr_14', '>', 3.8643712997436523),
        ('atr_14', '>', 4.931562662124634),
        ('dist_vwap_atr', '>', 1.7995506525039673),
        ('atr_50', '>', 7.45496392250061),
        ('dist_pdl_atr', '<=', 11.069048404693604),
        ('below_pdl_count_20', '>', 7.5),
        ('atr_14', '>', 7.313498258590698),
        ('hurst_proxy_50', '>', 2.2411134243011475),
        ('range_pos_200', '>', 0.8617177903652191),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS16T16_0122:
    name = 'V3_SHORT_S16T16_051'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.6292488942476895
    cpcv_min_wr = 0.5176991150442478
    constraints = [
        ('atr_14', '>', 3.8643712997436523),
        ('atr_14', '<=', 4.931562662124634),
        ('range_pos_200', '<=', 0.8911032676696777),
        ('atr_50', '>', 4.447466135025024),
        ('dist_eq50_atr', '<=', 3.1969215869903564),
        ('dow', '>', 1.5),
        ('hurst_proxy_50', '<=', 1.0150066614151),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS16T16_0123:
    name = 'V3_SHORT_S16T16_052'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.6449061641327978
    cpcv_min_wr = 0.46062992125984253
    constraints = [
        ('atr_14', '>', 3.8643712997436523),
        ('atr_14', '>', 4.931562662124634),
        ('dist_vwap_atr', '>', 1.7995506525039673),
        ('atr_50', '<=', 7.45496392250061),
        ('ema_slope_20', '>', 4.101552724838257),
        ('atr_14', '>', 5.784822702407837),
        ('dist_vwap_atr', '>', 13.727433204650879),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS16T16_0124:
    name = 'V3_SHORT_S16T16_053'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 16.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.6125878037488579
    cpcv_min_wr = 0.5439330543933054
    constraints = [
        ('atr_14', '>', 3.8643712997436523),
        ('atr_14', '<=', 4.931562662124634),
        ('range_pos_200', '>', 0.8911032676696777),
        ('dist_pdl_atr', '>', 99.7193489074707),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0125:
    name = 'V3_LONG_S20T20_072'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.5046992208583895
    cpcv_min_wr = 0.46847950673886407
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '>', 5.3883140087127686),
        ('dist_vwap_atr', '>', 1.6508015394210815),
        ('atr_50', '>', 6.212240695953369),
        ('atr_50', '>', 9.303894519805908),
        ('hurst_proxy_50', '>', 0.9334892630577087),
        ('dist_pdl_atr', '<=', 64.38891983032227),
        ('dist_pdl_atr', '>', 9.662386894226074),
        ('atr_14', '>', 8.4290132522583),
        ('autocorr_20', '>', -0.23500586301088333),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0126:
    name = 'V3_LONG_S20T20_073'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.5187665701503168
    cpcv_min_wr = 0.5032579185520362
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '>', 5.3883140087127686),
        ('dist_vwap_atr', '>', 1.6508015394210815),
        ('atr_50', '>', 6.212240695953369),
        ('atr_50', '<=', 9.303894519805908),
        ('ny_hour', '<=', 14.5),
        ('dist_pdh_atr', '<=', 26.117377281188965),
        ('dist_vwap_atr', '<=', 17.286802291870117),
        ('dist_pdl_atr', '>', 6.966649293899536),
        ('dist_pdh_atr', '>', -22.957416534423828),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0127:
    name = 'V3_LONG_S20T20_074'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.5165255815156576
    cpcv_min_wr = 0.4985881095932229
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '>', 5.3883140087127686),
        ('dist_vwap_atr', '<=', 1.6508015394210815),
        ('atr_14', '>', 7.110764503479004),
        ('ny_hour', '<=', 14.5),
        ('autocorr_20', '<=', -0.1486605852842331),
        ('dist_vwap_atr', '>', -4.7953972816467285),
        ('hurst_proxy_50', '<=', 1.4687333703041077),
        ('dist_pdl_atr', '>', -9.098411083221436),
        ('autocorr_20', '>', -0.3671398460865021),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0128:
    name = 'V3_LONG_S20T20_075'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.5222558090138987
    cpcv_min_wr = 0.48513740886146944
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '>', 5.3883140087127686),
        ('dist_vwap_atr', '>', 1.6508015394210815),
        ('atr_50', '>', 6.212240695953369),
        ('atr_50', '>', 9.303894519805908),
        ('hurst_proxy_50', '>', 0.9334892630577087),
        ('dist_pdl_atr', '<=', 64.38891983032227),
        ('dist_pdl_atr', '<=', 9.662386894226074),
        ('below_pdl_count_20', '>', 7.5),
        ('hurst_proxy_50', '<=', 2.231621742248535),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0129:
    name = 'V3_LONG_S20T20_076'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.5222490664378825
    cpcv_min_wr = 0.4742616033755274
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '>', 5.3883140087127686),
        ('dist_vwap_atr', '>', 1.6508015394210815),
        ('atr_50', '>', 6.212240695953369),
        ('atr_50', '<=', 9.303894519805908),
        ('ny_hour', '>', 14.5),
        ('below_pdl_count_20', '<=', 2.5),
        ('dow', '<=', 3.5),
        ('dist_vwap_atr', '<=', 16.198789596557617),
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS20T20_0130:
    name = 'V3_LONG_S20T20_077'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.7700065776787015
    cpcv_min_wr = 0.6909090909090909
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '<=', 5.3883140087127686),
        ('dist_vwap_atr', '>', 6.809353590011597),
        ('hurst_proxy_50', '<=', 1.3783873915672302),
        ('autocorr_20', '<=', 0.012821635231375694),
        ('is_close_30min', '<=', 0.5),
        ('ny_hour', '>', 13.5),
        ('dow', '>', 1.5),
        ('atr_50', '<=', 5.153106927871704),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0131:
    name = 'V3_LONG_S20T20_078'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.7640087617902726
    cpcv_min_wr = 0.6955223880597015
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '>', 5.3883140087127686),
        ('dist_vwap_atr', '<=', 1.6508015394210815),
        ('atr_14', '<=', 7.110764503479004),
        ('dist_pdh_atr', '<=', -53.00741386413574),
        ('atr_14', '<=', 6.466694116592407),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0132:
    name = 'V3_LONG_S20T20_079'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.5339948752223601
    cpcv_min_wr = 0.4953560371517028
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '>', 5.3883140087127686),
        ('dist_vwap_atr', '<=', 1.6508015394210815),
        ('atr_14', '>', 7.110764503479004),
        ('ny_hour', '>', 14.5),
        ('atr_50', '>', 10.434672355651855),
        ('dist_pdl_atr', '<=', 17.783547401428223),
        ('ofi_20', '<=', -3355.2794189453125),
        ('atr_50', '<=', 13.818857669830322),
        ('ema_distance', '<=', -1.2331272959709167),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0133:
    name = 'V3_LONG_S20T20_080'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.673987634533733
    cpcv_min_wr = 0.595
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '<=', 5.3883140087127686),
        ('dist_vwap_atr', '>', 6.809353590011597),
        ('hurst_proxy_50', '<=', 1.3783873915672302),
        ('autocorr_20', '<=', 0.012821635231375694),
        ('is_close_30min', '<=', 0.5),
        ('ny_hour', '<=', 13.5),
        ('sigma_ratio_5_15', '<=', 1.7442598342895508),
        ('reflex_10', '<=', 4.126854419708252),
        ('vol_ratio_60', '>', 0.6077725291252136),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0134:
    name = 'V3_LONG_S20T20_081'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.7116343090814208
    cpcv_min_wr = 0.5849056603773585
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '<=', 5.3883140087127686),
        ('dist_vwap_atr', '>', 6.809353590011597),
        ('hurst_proxy_50', '<=', 1.3783873915672302),
        ('autocorr_20', '<=', 0.012821635231375694),
        ('is_close_30min', '<=', 0.5),
        ('ny_hour', '>', 13.5),
        ('dow', '<=', 1.5),
        ('autocorr_20', '<=', -0.1453140452504158),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0135:
    name = 'V3_LONG_S20T20_082'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.6870375350767318
    cpcv_min_wr = 0.5352112676056338
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '>', 5.3883140087127686),
        ('dist_vwap_atr', '>', 1.6508015394210815),
        ('atr_50', '<=', 6.212240695953369),
        ('dist_pdh_atr', '>', 0.7070620656013489),
        ('dist_vwap_atr', '<=', 12.688347816467285),
        ('ema_slope_20', '>', 4.551342964172363),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0136:
    name = 'V3_LONG_S20T20_083'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.6556201480553772
    cpcv_min_wr = 0.5791505791505791
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '>', 5.3883140087127686),
        ('dist_vwap_atr', '<=', 1.6508015394210815),
        ('atr_14', '>', 7.110764503479004),
        ('ny_hour', '<=', 14.5),
        ('autocorr_20', '>', -0.1486605852842331),
        ('dist_pdh_atr', '<=', -51.93326187133789),
        ('sigma_ratio_1_15', '>', 1.3095135688781738),
        ('atr_14', '<=', 9.368990421295166),
        ('dist_pdl_atr', '>', -22.534152030944824),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0137:
    name = 'V3_LONG_S20T20_084'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.6583603443181762
    cpcv_min_wr = 0.5163934426229508
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '<=', 5.3883140087127686),
        ('dist_vwap_atr', '<=', 6.809353590011597),
        ('dist_pdl_atr', '>', 0.393512487411499),
        ('dist_pdh_atr', '>', 7.357413291931152),
        ('dow', '<=', 1.5),
        ('atr_50', '>', 4.944312572479248),
        ('atr_50', '<=', 5.6749396324157715),
        ('autocorr_20', '<=', 0.08378569409251213),
        ('dist_pdl_atr', '<=', 31.68939971923828),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0138:
    name = 'V3_LONG_S20T20_085'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.6903236200566281
    cpcv_min_wr = 0.6213592233009708
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '>', 5.3883140087127686),
        ('dist_vwap_atr', '<=', 1.6508015394210815),
        ('atr_14', '>', 7.110764503479004),
        ('ny_hour', '>', 14.5),
        ('atr_50', '>', 10.434672355651855),
        ('dist_pdl_atr', '<=', 17.783547401428223),
        ('ofi_20', '<=', -3355.2794189453125),
        ('atr_50', '<=', 13.818857669830322),
        ('ema_distance', '>', -1.2331272959709167),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0139:
    name = 'V3_LONG_S20T20_086'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.6605654927328561
    cpcv_min_wr = 0.576271186440678
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '>', 5.3883140087127686),
        ('dist_vwap_atr', '<=', 1.6508015394210815),
        ('atr_14', '>', 7.110764503479004),
        ('ny_hour', '<=', 14.5),
        ('autocorr_20', '>', -0.1486605852842331),
        ('dist_pdh_atr', '>', -51.93326187133789),
        ('dist_pdl_atr', '>', 48.9782600402832),
        ('autocorr_5', '>', 0.1694444939494133),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0140:
    name = 'V3_LONG_S20T20_087'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.5662299667122026
    cpcv_min_wr = 0.5056179775280899
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '>', 5.3883140087127686),
        ('dist_vwap_atr', '<=', 1.6508015394210815),
        ('atr_14', '>', 7.110764503479004),
        ('ny_hour', '<=', 14.5),
        ('autocorr_20', '>', -0.1486605852842331),
        ('dist_pdh_atr', '<=', -51.93326187133789),
        ('sigma_ratio_1_15', '<=', 1.3095135688781738),
        ('dist_vwap_atr', '>', -5.356740474700928),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS20T20_0141:
    name = 'V3_LONG_S20T20_088'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.594722517126411
    cpcv_min_wr = 0.55625
    constraints = [
        ('atr_14', '>', 3.8027161359786987),
        ('atr_14', '<=', 5.3883140087127686),
        ('dist_vwap_atr', '>', 6.809353590011597),
        ('hurst_proxy_50', '<=', 1.3783873915672302),
        ('autocorr_20', '<=', 0.012821635231375694),
        ('is_close_30min', '<=', 0.5),
        ('ny_hour', '<=', 13.5),
        ('sigma_ratio_5_15', '<=', 1.7442598342895508),
        ('reflex_10', '<=', 4.126854419708252),
        ('vol_ratio_60', '<=', 0.6077725291252136),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS20T20_0142:
    name = 'V3_SHORT_S20T20_054'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.5128969204138245
    cpcv_min_wr = 0.5026987972289515
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('atr_14', '>', 6.479059934616089),
        ('dist_vwap_atr', '<=', 1.9368405938148499),
        ('dist_vwap_atr', '>', -1.760023057460785),
        ('atr_14', '>', 10.031204223632812),
        ('dist_high20_atr', '>', -5.587437152862549),
        ('dist_pdl_atr', '>', -15.716889381408691),
        ('autocorr_5', '>', -0.5506391525268555),
        ('autocorr_5', '<=', -0.015154060907661915),
        ('sigma_ratio_1_5', '<=', 1.5766159892082214),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS20T20_0143:
    name = 'V3_SHORT_S20T20_055'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.5243455228165149
    cpcv_min_wr = 0.4922027290448343
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('atr_14', '>', 6.479059934616089),
        ('dist_vwap_atr', '<=', 1.9368405938148499),
        ('dist_vwap_atr', '<=', -1.760023057460785),
        ('dist_pdh_atr', '>', -76.73511505126953),
        ('ofi_20', '>', -3156.9373779296875),
        ('ny_minute', '>', 48.5),
        ('ny_hour', '<=', 14.5),
        ('ema_distance', '>', -3.390814781188965),
        ('range_pos_50', '<=', 0.40777966380119324),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS20T20_0144:
    name = 'V3_SHORT_S20T20_056'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.5230067262750357
    cpcv_min_wr = 0.4941790445604175
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('atr_14', '>', 6.479059934616089),
        ('dist_vwap_atr', '<=', 1.9368405938148499),
        ('dist_vwap_atr', '>', -1.760023057460785),
        ('atr_14', '>', 10.031204223632812),
        ('dist_high20_atr', '>', -5.587437152862549),
        ('dist_pdl_atr', '>', -15.716889381408691),
        ('autocorr_5', '>', -0.5506391525268555),
        ('autocorr_5', '>', -0.015154060907661915),
        ('above_pdh_count_20', '>', 3.5),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS20T20_0145:
    name = 'V3_SHORT_S20T20_057'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.5416227002832025
    cpcv_min_wr = 0.49160671462829736
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('atr_14', '>', 6.479059934616089),
        ('dist_vwap_atr', '<=', 1.9368405938148499),
        ('dist_vwap_atr', '<=', -1.760023057460785),
        ('dist_pdh_atr', '>', -76.73511505126953),
        ('ofi_20', '<=', -3156.9373779296875),
        ('autocorr_20', '>', -0.14862406998872757),
        ('sigma_ratio_5_15', '<=', 2.178793787956238),
        ('atr_50', '<=', 8.968799114227295),
        ('dist_pdl_atr', '<=', 16.104350090026855),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS20T20_0146:
    name = 'V3_SHORT_S20T20_058'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.5360275876844699
    cpcv_min_wr = 0.49093581577658013
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('atr_14', '>', 6.479059934616089),
        ('dist_vwap_atr', '<=', 1.9368405938148499),
        ('dist_vwap_atr', '<=', -1.760023057460785),
        ('dist_pdh_atr', '>', -76.73511505126953),
        ('ofi_20', '>', -3156.9373779296875),
        ('ny_minute', '<=', 48.5),
        ('ofi_5', '<=', 4057.5797119140625),
        ('dist_pdl_atr', '<=', 32.94671440124512),
        ('ema_distance', '>', 1.115067183971405),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS20T20_0147:
    name = 'V3_SHORT_S20T20_059'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.5268870467738226
    cpcv_min_wr = 0.47420464316423044
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('atr_14', '>', 6.479059934616089),
        ('dist_vwap_atr', '>', 1.9368405938148499),
        ('atr_50', '>', 9.303894519805908),
        ('dist_pdl_atr', '<=', 64.1672477722168),
        ('dist_pdl_atr', '<=', 9.636948585510254),
        ('below_pdl_count_20', '<=', 7.5),
        ('atr_50', '>', 9.839427947998047),
        ('dist_vwap_atr', '<=', 7.2471489906311035),
        ('dist_pdl_atr', '<=', 5.681260108947754),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS20T20_0148:
    name = 'V3_SHORT_S20T20_060'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.701336908158914
    cpcv_min_wr = 0.47700394218134035
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('atr_14', '>', 6.479059934616089),
        ('dist_vwap_atr', '>', 1.9368405938148499),
        ('atr_50', '>', 9.303894519805908),
        ('dist_pdl_atr', '>', 64.1672477722168),
        ('dow', '<=', 2.5),
        ('sigma_ratio_1_5', '>', 1.1841718554496765),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS20T20_0149:
    name = 'V3_SHORT_S20T20_061'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.5181433232858339
    cpcv_min_wr = 0.48484848484848486
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('atr_14', '>', 6.479059934616089),
        ('dist_vwap_atr', '>', 1.9368405938148499),
        ('atr_50', '>', 9.303894519805908),
        ('dist_pdl_atr', '<=', 64.1672477722168),
        ('dist_pdl_atr', '<=', 9.636948585510254),
        ('below_pdl_count_20', '>', 7.5),
        ('hurst_proxy_50', '<=', 2.2337801456451416),
        ('range_pos_50', '>', 0.9000845849514008),
        ('rsi_14', '<=', 72.41215896606445),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS20T20_0150:
    name = 'V3_SHORT_S20T20_062'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.5646882696455986
    cpcv_min_wr = 0.4758454106280193
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('atr_14', '>', 6.479059934616089),
        ('dist_vwap_atr', '>', 1.9368405938148499),
        ('atr_50', '<=', 9.303894519805908),
        ('dist_pdh_atr', '>', -24.197967529296875),
        ('hurst_proxy_50', '>', 1.0948295593261719),
        ('dist_pdh_atr', '<=', 34.602182388305664),
        ('ret_20', '<=', 41.875),
        ('dow', '<=', 3.5),
        ('dist_vwap_atr', '>', 14.689221382141113),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS20T20_0151:
    name = 'V3_SHORT_S20T20_063'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.7300573801135793
    cpcv_min_wr = 0.6091370558375635
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('atr_14', '>', 6.479059934616089),
        ('dist_vwap_atr', '>', 1.9368405938148499),
        ('atr_50', '<=', 9.303894519805908),
        ('dist_pdh_atr', '<=', -24.197967529296875),
        ('atr_14', '<=', 7.775419473648071),
        ('below_pdl_count_20', '<=', 10.5),
        ('dist_pdl_atr', '<=', 20.227118492126465),
        ('dist_pdl_atr', '>', 7.980790138244629),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS20T20_0152:
    name = 'V3_SHORT_S20T20_064'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.5547792649143677
    cpcv_min_wr = 0.5186246418338109
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('atr_14', '<=', 6.479059934616089),
        ('atr_14', '>', 5.069453001022339),
        ('dist_pdh_atr', '>', 5.450583457946777),
        ('dist_pdh_atr', '<=', 51.29611778259277),
        ('ema_slope_20', '<=', 4.162099123001099),
        ('ny_hour', '<=', 14.5),
        ('autocorr_20', '>', -0.07363193482160568),
        ('dist_vwap_atr', '<=', 2.1452821493148804),
        ('hurst_proxy_50', '>', 1.4493773579597473),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS20T20_0153:
    name = 'V3_SHORT_S20T20_065'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.6852878527481654
    cpcv_min_wr = 0.6075949367088608
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('atr_14', '>', 6.479059934616089),
        ('dist_vwap_atr', '>', 1.9368405938148499),
        ('atr_50', '<=', 9.303894519805908),
        ('dist_pdh_atr', '<=', -24.197967529296875),
        ('atr_14', '>', 7.775419473648071),
        ('dist_pdl_atr', '>', -4.071153402328491),
        ('autocorr_5', '>', -0.12930918484926224),
        ('dist_pdh_atr', '<=', -31.84047031402588),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS20T20_0154:
    name = 'V3_SHORT_S20T20_066'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.6381124376249094
    cpcv_min_wr = 0.55
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('atr_14', '>', 6.479059934616089),
        ('dist_vwap_atr', '<=', 1.9368405938148499),
        ('dist_vwap_atr', '<=', -1.760023057460785),
        ('dist_pdh_atr', '>', -76.73511505126953),
        ('ofi_20', '>', -3156.9373779296875),
        ('ny_minute', '<=', 48.5),
        ('ofi_5', '>', 4057.5797119140625),
        ('dist_vwap_atr', '>', -3.548136830329895),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS20T20_0155:
    name = 'V3_SHORT_S20T20_067'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.601679380718576
    cpcv_min_wr = 0.4630225080385852
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('atr_14', '>', 6.479059934616089),
        ('dist_vwap_atr', '<=', 1.9368405938148499),
        ('dist_vwap_atr', '>', -1.760023057460785),
        ('atr_14', '>', 10.031204223632812),
        ('dist_high20_atr', '>', -5.587437152862549),
        ('dist_pdl_atr', '<=', -15.716889381408691),
        ('dist_pdl_atr', '>', -19.22915267944336),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS20T20_0156:
    name = 'V3_SHORT_S20T20_068'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.6501130110555119
    cpcv_min_wr = 0.5240963855421686
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('atr_14', '<=', 6.479059934616089),
        ('atr_14', '>', 5.069453001022339),
        ('dist_pdh_atr', '>', 5.450583457946777),
        ('dist_pdh_atr', '<=', 51.29611778259277),
        ('ema_slope_20', '<=', 4.162099123001099),
        ('ny_hour', '>', 14.5),
        ('dist_vwap_atr', '>', 12.28780460357666),
        ('autocorr_5', '>', -0.18798258155584335),
        ('dist_pdh_atr', '>', 27.747035026550293),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS20T20_0157:
    name = 'V3_SHORT_S20T20_069'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.6754706547652695
    cpcv_min_wr = 0.6417112299465241
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('atr_14', '>', 6.479059934616089),
        ('dist_vwap_atr', '<=', 1.9368405938148499),
        ('dist_vwap_atr', '>', -1.760023057460785),
        ('atr_14', '<=', 10.031204223632812),
        ('dist_pdh_atr', '<=', -13.333211421966553),
        ('dist_pdl_atr', '<=', 29.646885871887207),
        ('sigma_ratio_1_15', '<=', 2.712403416633606),
        ('autocorr_20', '>', 0.21842306852340698),
        ('sigma_ratio_5_15', '<=', 1.4572380781173706),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS20T20_0158:
    name = 'V3_SHORT_S20T20_070'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.5085459867111429
    cpcv_min_wr = 0.4714285714285714
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('atr_14', '>', 6.479059934616089),
        ('dist_vwap_atr', '<=', 1.9368405938148499),
        ('dist_vwap_atr', '>', -1.760023057460785),
        ('atr_14', '>', 10.031204223632812),
        ('dist_high20_atr', '<=', -5.587437152862549),
        ('atr_14', '>', 12.754677295684814),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS20T20_0159:
    name = 'V3_SHORT_S20T20_071'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.5731382384947686
    cpcv_min_wr = 0.4716981132075472
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('atr_14', '>', 6.479059934616089),
        ('dist_vwap_atr', '>', 1.9368405938148499),
        ('atr_50', '<=', 9.303894519805908),
        ('dist_pdh_atr', '>', -24.197967529296875),
        ('hurst_proxy_50', '<=', 1.0948295593261719),
        ('dow', '>', 1.5),
        ('dist_pdh_atr', '>', -1.5011086463928223),
        ('dist_vwap_atr', '<=', 8.464109420776367),
        ('dist_high20_atr', '<=', -1.1398972272872925),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS20T20_0160:
    name = 'V3_SHORT_S20T20_072'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.5688614885009395
    cpcv_min_wr = 0.47555555555555556
    constraints = [
        ('atr_14', '>', 4.461906909942627),
        ('atr_14', '>', 6.479059934616089),
        ('dist_vwap_atr', '<=', 1.9368405938148499),
        ('dist_vwap_atr', '<=', -1.760023057460785),
        ('dist_pdh_atr', '>', -76.73511505126953),
        ('ofi_20', '>', -3156.9373779296875),
        ('ny_minute', '>', 48.5),
        ('ny_hour', '>', 14.5),
        ('dow', '>', 1.5),
        ('ema_distance', '<=', -1.3288363814353943),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS25T25_0161:
    name = 'V3_LONG_S25T25_089'
    side = 'LONG'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.5239991797828808
    cpcv_min_wr = 0.5092324936581912
    constraints = [
        ('atr_14', '>', 4.113550662994385),
        ('atr_14', '>', 5.54906702041626),
        ('atr_50', '>', 6.516178131103516),
        ('dist_vwap_atr', '<=', -1.6859248876571655),
        ('atr_50', '>', 9.441154956817627),
        ('dist_pdh_atr', '>', -48.39643478393555),
        ('autocorr_20', '<=', -0.03677808493375778),
        ('ny_hour', '>', 10.5),
        ('dist_eq50_atr', '<=', 1.5063607096672058),
        ('is_close_30min', '<=', 0.5),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS25T25_0162:
    name = 'V3_LONG_S25T25_090'
    side = 'LONG'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.5118761075307245
    cpcv_min_wr = 0.49055324917393883
    constraints = [
        ('atr_14', '>', 4.113550662994385),
        ('atr_14', '>', 5.54906702041626),
        ('atr_50', '>', 6.516178131103516),
        ('dist_vwap_atr', '>', -1.6859248876571655),
        ('dist_pdl_atr', '<=', 93.6421127319336),
        ('dist_pdh_atr', '>', -8.250753402709961),
        ('atr_5', '>', 6.587902545928955),
        ('dow', '>', 2.5),
        ('ny_hour', '<=', 13.5),
        ('dist_pdh_atr', '<=', 6.003154754638672),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS25T25_0163:
    name = 'V3_LONG_S25T25_091'
    side = 'LONG'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.5990728169783213
    cpcv_min_wr = 0.5591603053435115
    constraints = [
        ('atr_14', '>', 4.113550662994385),
        ('atr_14', '>', 5.54906702041626),
        ('atr_50', '<=', 6.516178131103516),
        ('dist_pdh_atr', '>', 2.7585480213165283),
        ('ny_hour', '<=', 14.5),
        ('ret_20', '<=', 38.125),
        ('dist_pdh_atr', '<=', 45.68975830078125),
        ('dow', '<=', 2.5),
        ('dist_pdh_atr', '>', 5.559862852096558),
        ('atr_50', '>', 5.594427824020386),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS25T25_0164:
    name = 'V3_LONG_S25T25_092'
    side = 'LONG'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.5293154618077076
    cpcv_min_wr = 0.4852216748768473
    constraints = [
        ('atr_14', '>', 4.113550662994385),
        ('atr_14', '>', 5.54906702041626),
        ('atr_50', '>', 6.516178131103516),
        ('dist_vwap_atr', '<=', -1.6859248876571655),
        ('atr_50', '>', 9.441154956817627),
        ('dist_pdh_atr', '>', -48.39643478393555),
        ('autocorr_20', '>', -0.03677808493375778),
        ('dow', '<=', 2.5),
        ('dist_pdl_atr', '>', 13.228353500366211),
        ('atr_50', '<=', 16.109825134277344),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS25T25_0165:
    name = 'V3_LONG_S25T25_093'
    side = 'LONG'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.5579295428476322
    cpcv_min_wr = 0.5080336648814078
    constraints = [
        ('atr_14', '>', 4.113550662994385),
        ('atr_14', '>', 5.54906702041626),
        ('atr_50', '>', 6.516178131103516),
        ('dist_vwap_atr', '>', -1.6859248876571655),
        ('dist_pdl_atr', '<=', 93.6421127319336),
        ('dist_pdh_atr', '>', -8.250753402709961),
        ('atr_5', '>', 6.587902545928955),
        ('dow', '<=', 2.5),
        ('dist_pdl_atr', '<=', 61.7198600769043),
        ('hurst_proxy_50', '<=', 0.9440158903598785),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS25T25_0166:
    name = 'V3_LONG_S25T25_094'
    side = 'LONG'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.6627155241052803
    cpcv_min_wr = 0.5568965517241379
    constraints = [
        ('atr_14', '>', 4.113550662994385),
        ('atr_14', '>', 5.54906702041626),
        ('atr_50', '>', 6.516178131103516),
        ('dist_vwap_atr', '<=', -1.6859248876571655),
        ('atr_50', '>', 9.441154956817627),
        ('dist_pdh_atr', '<=', -48.39643478393555),
        ('ema_slope_20', '<=', 0.22388377040624619),
        ('sigma_ratio_1_15', '>', 1.471948504447937),
        ('sigma_ratio_1_5', '>', 1.4037137031555176),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS25T25_0167:
    name = 'V3_LONG_S25T25_095'
    side = 'LONG'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.6193634560243464
    cpcv_min_wr = 0.55741127348643
    constraints = [
        ('atr_14', '>', 4.113550662994385),
        ('atr_14', '>', 5.54906702041626),
        ('atr_50', '<=', 6.516178131103516),
        ('dist_pdh_atr', '<=', 2.7585480213165283),
        ('ny_hour', '<=', 14.5),
        ('autocorr_20', '<=', 0.22870878130197525),
        ('dist_pdl_atr', '<=', 0.8901649415493011),
        ('dist_pdl_atr', '<=', -3.1493923664093018),
        ('ny_hour', '>', 11.5),
        ('dist_pdh_atr', '>', -24.56338596343994),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS25T25_0168:
    name = 'V3_LONG_S25T25_096'
    side = 'LONG'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.5866312872000179
    cpcv_min_wr = 0.5150375939849624
    constraints = [
        ('atr_14', '>', 4.113550662994385),
        ('atr_14', '>', 5.54906702041626),
        ('atr_50', '>', 6.516178131103516),
        ('dist_vwap_atr', '<=', -1.6859248876571655),
        ('atr_50', '>', 9.441154956817627),
        ('dist_pdh_atr', '>', -48.39643478393555),
        ('autocorr_20', '>', -0.03677808493375778),
        ('dow', '<=', 2.5),
        ('dist_pdl_atr', '<=', 13.228353500366211),
        ('dist_pdl_atr', '<=', -21.563627243041992),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS25T25_0169:
    name = 'V3_LONG_S25T25_097'
    side = 'LONG'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.6766723490431127
    cpcv_min_wr = 0.5390625
    constraints = [
        ('atr_14', '>', 4.113550662994385),
        ('atr_14', '<=', 5.54906702041626),
        ('dist_vwap_atr', '<=', 5.762884140014648),
        ('dist_pdh_atr', '<=', -36.47657012939453),
        ('ny_hour', '>', 12.5),
        ('atr_50', '>', 5.012780427932739),
        ('dow', '<=', 2.5),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS25T25_0170:
    name = 'V3_LONG_S25T25_098'
    side = 'LONG'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.5278571000437029
    cpcv_min_wr = 0.46050670640834573
    constraints = [
        ('atr_14', '>', 4.113550662994385),
        ('atr_14', '>', 5.54906702041626),
        ('atr_50', '>', 6.516178131103516),
        ('dist_vwap_atr', '<=', -1.6859248876571655),
        ('atr_50', '>', 9.441154956817627),
        ('dist_pdh_atr', '<=', -48.39643478393555),
        ('ema_slope_20', '<=', 0.22388377040624619),
        ('sigma_ratio_1_15', '>', 1.471948504447937),
        ('sigma_ratio_1_5', '<=', 1.4037137031555176),
        ('dist_pdl_atr', '<=', -15.503286838531494),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS25T25_0171:
    name = 'V3_LONG_S25T25_099'
    side = 'LONG'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.6302298749626092
    cpcv_min_wr = 0.47474747474747475
    constraints = [
        ('atr_14', '>', 4.113550662994385),
        ('atr_14', '>', 5.54906702041626),
        ('atr_50', '>', 6.516178131103516),
        ('dist_vwap_atr', '<=', -1.6859248876571655),
        ('atr_50', '>', 9.441154956817627),
        ('dist_pdh_atr', '<=', -48.39643478393555),
        ('ema_slope_20', '<=', 0.22388377040624619),
        ('sigma_ratio_1_15', '>', 1.471948504447937),
        ('sigma_ratio_1_5', '<=', 1.4037137031555176),
        ('dist_pdl_atr', '>', -15.503286838531494),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS25T25_0172:
    name = 'V3_LONG_S25T25_100'
    side = 'LONG'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.5946915831057916
    cpcv_min_wr = 0.5467980295566502
    constraints = [
        ('atr_14', '>', 4.113550662994385),
        ('atr_14', '>', 5.54906702041626),
        ('atr_50', '<=', 6.516178131103516),
        ('dist_pdh_atr', '>', 2.7585480213165283),
        ('ny_hour', '<=', 14.5),
        ('ret_20', '>', 38.125),
        ('atr_50', '>', 5.659958839416504),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS25T25_0173:
    name = 'V3_SHORT_S25T25_073'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.5243312067821683
    cpcv_min_wr = 0.5010183299389002
    constraints = [
        ('atr_14', '>', 4.700997352600098),
        ('atr_14', '>', 7.3564982414245605),
        ('dist_pdh_atr', '<=', -7.51108717918396),
        ('atr_50', '>', 7.859732151031494),
        ('sigma_ratio_5_15', '<=', 1.9677127599716187),
        ('dist_pdh_atr', '>', -43.907331466674805),
        ('ny_minute', '>', 15.5),
        ('dow', '>', 1.5),
        ('atr_14', '>', 7.923868656158447),
        ('ofi_20', '>', -3955.2374267578125),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS25T25_0174:
    name = 'V3_SHORT_S25T25_074'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.5161658300806412
    cpcv_min_wr = 0.5036743923120407
    constraints = [
        ('atr_14', '>', 4.700997352600098),
        ('atr_14', '>', 7.3564982414245605),
        ('dist_pdh_atr', '<=', -7.51108717918396),
        ('atr_50', '>', 7.859732151031494),
        ('sigma_ratio_5_15', '<=', 1.9677127599716187),
        ('dist_pdh_atr', '>', -43.907331466674805),
        ('ny_minute', '<=', 15.5),
        ('dist_pdl_atr', '>', -6.67734956741333),
        ('ny_hour', '<=', 13.5),
        ('atr_5', '>', 7.2328941822052),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS25T25_0175:
    name = 'V3_SHORT_S25T25_075'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.5120421580891226
    cpcv_min_wr = 0.4812083729781161
    constraints = [
        ('atr_14', '>', 4.700997352600098),
        ('atr_14', '>', 7.3564982414245605),
        ('dist_pdh_atr', '<=', -7.51108717918396),
        ('atr_50', '>', 7.859732151031494),
        ('sigma_ratio_5_15', '<=', 1.9677127599716187),
        ('dist_pdh_atr', '>', -43.907331466674805),
        ('ny_minute', '>', 15.5),
        ('dow', '<=', 1.5),
        ('atr_50', '>', 12.54603910446167),
        ('vol_imbalance_10', '>', 0.21537497639656067),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS25T25_0176:
    name = 'V3_SHORT_S25T25_076'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.5585400716933708
    cpcv_min_wr = 0.5280403276622558
    constraints = [
        ('atr_14', '>', 4.700997352600098),
        ('atr_14', '>', 7.3564982414245605),
        ('dist_pdh_atr', '>', -7.51108717918396),
        ('ema_distance', '<=', -1.1763188242912292),
        ('sigma_ratio_1_15', '>', 1.51142418384552),
        ('atr_5', '>', 8.3695969581604),
        ('dist_pdl_atr', '<=', 16.445698738098145),
        ('dist_pdl_atr', '>', 1.2186647057533264),
        ('hurst_proxy_50', '>', 1.4722161889076233),
        ('atr_14', '<=', 16.60434913635254),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS25T25_0177:
    name = 'V3_SHORT_S25T25_077'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.6058868484065706
    cpcv_min_wr = 0.4943330427201395
    constraints = [
        ('atr_14', '>', 4.700997352600098),
        ('atr_14', '>', 7.3564982414245605),
        ('dist_pdh_atr', '>', -7.51108717918396),
        ('ema_distance', '>', -1.1763188242912292),
        ('atr_50', '>', 11.083081722259521),
        ('dist_pdl_atr', '<=', 63.237043380737305),
        ('dist_pdl_atr', '<=', 8.185019493103027),
        ('dist_pdl_atr', '>', 2.0384784936904907),
        ('autocorr_5', '<=', -0.02759090717881918),
        ('ema_slope_20', '>', 0.3520885705947876),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS25T25_0178:
    name = 'V3_SHORT_S25T25_078'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.6735090986160361
    cpcv_min_wr = 0.5161016949152543
    constraints = [
        ('atr_14', '>', 4.700997352600098),
        ('atr_14', '>', 7.3564982414245605),
        ('dist_pdh_atr', '>', -7.51108717918396),
        ('ema_distance', '>', -1.1763188242912292),
        ('atr_50', '>', 11.083081722259521),
        ('dist_pdl_atr', '>', 63.237043380737305),
        ('dow', '<=', 3.5),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS25T25_0179:
    name = 'V3_SHORT_S25T25_079'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.5612196500101105
    cpcv_min_wr = 0.519406392694064
    constraints = [
        ('atr_14', '>', 4.700997352600098),
        ('atr_14', '>', 7.3564982414245605),
        ('dist_pdh_atr', '>', -7.51108717918396),
        ('ema_distance', '<=', -1.1763188242912292),
        ('sigma_ratio_1_15', '<=', 1.51142418384552),
        ('ny_hour', '<=', 14.5),
        ('atr_50', '>', 6.993133068084717),
        ('sigma_ratio_1_15', '>', 1.0643956661224365),
        ('ofi_20', '>', -2599.6199951171875),
        ('atr_50', '<=', 14.162473201751709),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS25T25_0180:
    name = 'V3_SHORT_S25T25_080'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.6002589501069956
    cpcv_min_wr = 0.497787610619469
    constraints = [
        ('atr_14', '>', 4.700997352600098),
        ('atr_14', '<=', 7.3564982414245605),
        ('dist_pdh_atr', '<=', 2.782620668411255),
        ('atr_50', '<=', 5.590426206588745),
        ('is_close_30min', '<=', 0.5),
        ('dist_vwap_atr', '<=', 11.58775281906128),
        ('dist_pdl_atr', '>', 12.170588493347168),
        ('dist_pdh_atr', '<=', -5.6758716106414795),
        ('hurst_proxy_50', '<=', 2.1214267015457153),
        ('dist_pdl_atr', '>', 18.416318893432617),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS25T25_0181:
    name = 'V3_SHORT_S25T25_081'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.572936940909425
    cpcv_min_wr = 0.5004492362982929
    constraints = [
        ('atr_14', '>', 4.700997352600098),
        ('atr_14', '>', 7.3564982414245605),
        ('dist_pdh_atr', '>', -7.51108717918396),
        ('ema_distance', '>', -1.1763188242912292),
        ('atr_50', '<=', 11.083081722259521),
        ('hurst_proxy_50', '<=', 1.9111740589141846),
        ('dow', '<=', 1.5),
        ('dow', '>', 0.5),
        ('dist_vwap_atr', '>', -4.465031623840332),
        ('range_pos_200', '<=', 0.46919457614421844),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS25T25_0182:
    name = 'V3_SHORT_S25T25_082'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.8295271032927539
    cpcv_min_wr = 0.7233201581027668
    constraints = [
        ('atr_14', '>', 4.700997352600098),
        ('atr_14', '<=', 7.3564982414245605),
        ('dist_pdh_atr', '<=', 2.782620668411255),
        ('atr_50', '>', 5.590426206588745),
        ('dist_pdl_atr', '<=', -21.90987491607666),
        ('dist_pdl_atr', '<=', -34.95074462890625),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS25T25_0183:
    name = 'V3_SHORT_S25T25_083'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.5650125939127136
    cpcv_min_wr = 0.5087719298245614
    constraints = [
        ('atr_14', '>', 4.700997352600098),
        ('atr_14', '>', 7.3564982414245605),
        ('dist_pdh_atr', '>', -7.51108717918396),
        ('ema_distance', '<=', -1.1763188242912292),
        ('sigma_ratio_1_15', '<=', 1.51142418384552),
        ('ny_hour', '<=', 14.5),
        ('atr_50', '>', 6.993133068084717),
        ('sigma_ratio_1_15', '<=', 1.0643956661224365),
        ('autocorr_20', '<=', 0.2305338978767395),
        ('atr_5', '<=', 14.604333400726318),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS25T25_0184:
    name = 'V3_SHORT_S25T25_084'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.7302275997502742
    cpcv_min_wr = 0.64
    constraints = [
        ('atr_14', '>', 4.700997352600098),
        ('atr_14', '>', 7.3564982414245605),
        ('dist_pdh_atr', '<=', -7.51108717918396),
        ('atr_50', '<=', 7.859732151031494),
        ('dist_pdh_atr', '>', -40.89674186706543),
        ('dist_pdh_atr', '<=', -13.274042129516602),
        ('dist_pdh_atr', '>', -24.779438018798828),
        ('below_pdl_count_20', '>', 19.5),
        ('atr_50', '>', 7.033936500549316),
        ('dist_pdl_atr', '>', -11.621344566345215),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS25T25_0185:
    name = 'V3_SHORT_S25T25_085'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.5346346656232581
    cpcv_min_wr = 0.5112285336856011
    constraints = [
        ('atr_14', '>', 4.700997352600098),
        ('atr_14', '>', 7.3564982414245605),
        ('dist_pdh_atr', '>', -7.51108717918396),
        ('ema_distance', '>', -1.1763188242912292),
        ('atr_50', '>', 11.083081722259521),
        ('dist_pdl_atr', '<=', 63.237043380737305),
        ('dist_pdl_atr', '<=', 8.185019493103027),
        ('dist_pdl_atr', '>', 2.0384784936904907),
        ('autocorr_5', '<=', -0.02759090717881918),
        ('ema_slope_20', '<=', 0.3520885705947876),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS25T25_0186:
    name = 'V3_SHORT_S25T25_086'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.5535572233186491
    cpcv_min_wr = 0.47756874095513746
    constraints = [
        ('atr_14', '>', 4.700997352600098),
        ('atr_14', '>', 7.3564982414245605),
        ('dist_pdh_atr', '<=', -7.51108717918396),
        ('atr_50', '>', 7.859732151031494),
        ('sigma_ratio_5_15', '>', 1.9677127599716187),
        ('dist_pdl_atr', '<=', 18.233357429504395),
        ('ema_slope_20', '>', -0.25087061524391174),
        ('dist_pdh_atr', '<=', -33.76321029663086),
        ('dist_pdl_atr', '<=', -3.2073538303375244),
        ('range_pos_200', '<=', 0.4766676276922226),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS25T25_0187:
    name = 'V3_SHORT_S25T25_087'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.5605122717899622
    cpcv_min_wr = 0.46798029556650245
    constraints = [
        ('atr_14', '>', 4.700997352600098),
        ('atr_14', '>', 7.3564982414245605),
        ('dist_pdh_atr', '<=', -7.51108717918396),
        ('atr_50', '>', 7.859732151031494),
        ('sigma_ratio_5_15', '>', 1.9677127599716187),
        ('dist_pdl_atr', '<=', 18.233357429504395),
        ('ema_slope_20', '>', -0.25087061524391174),
        ('dist_pdh_atr', '>', -33.76321029663086),
        ('atr_50', '>', 9.246230602264404),
        ('sigma_ratio_1_15', '<=', 1.877561092376709),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS25T25_0188:
    name = 'V3_SHORT_S25T25_088'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.5603517984779488
    cpcv_min_wr = 0.47045454545454546
    constraints = [
        ('atr_14', '>', 4.700997352600098),
        ('atr_14', '<=', 7.3564982414245605),
        ('dist_pdh_atr', '>', 2.782620668411255),
        ('dist_pdh_atr', '>', 52.168800354003906),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS25T25_0189:
    name = 'V3_SHORT_S25T25_089'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.6835796035526494
    cpcv_min_wr = 0.6242038216560509
    constraints = [
        ('atr_14', '>', 4.700997352600098),
        ('atr_14', '>', 7.3564982414245605),
        ('dist_pdh_atr', '>', -7.51108717918396),
        ('ema_distance', '<=', -1.1763188242912292),
        ('sigma_ratio_1_15', '<=', 1.51142418384552),
        ('ny_hour', '<=', 14.5),
        ('atr_50', '>', 6.993133068084717),
        ('sigma_ratio_1_15', '<=', 1.0643956661224365),
        ('autocorr_20', '>', 0.2305338978767395),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS25T25_0190:
    name = 'V3_SHORT_S25T25_090'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.5404943475730762
    cpcv_min_wr = 0.49230769230769234
    constraints = [
        ('atr_14', '>', 4.700997352600098),
        ('atr_14', '>', 7.3564982414245605),
        ('dist_pdh_atr', '>', -7.51108717918396),
        ('ema_distance', '>', -1.1763188242912292),
        ('atr_50', '<=', 11.083081722259521),
        ('hurst_proxy_50', '>', 1.9111740589141846),
        ('dist_pdh_atr', '<=', 25.107080459594727),
        ('dist_pdl_atr', '<=', 42.804710388183594),
        ('dist_pdh_atr', '<=', 9.92540693283081),
        ('dist_vwap_atr', '>', 8.904847621917725),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS25T25_0191:
    name = 'V3_SHORT_S25T25_091'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.6084284688108883
    cpcv_min_wr = 0.5032051282051282
    constraints = [
        ('atr_14', '>', 4.700997352600098),
        ('atr_14', '>', 7.3564982414245605),
        ('dist_pdh_atr', '>', -7.51108717918396),
        ('ema_distance', '>', -1.1763188242912292),
        ('atr_50', '<=', 11.083081722259521),
        ('hurst_proxy_50', '<=', 1.9111740589141846),
        ('dow', '<=', 1.5),
        ('dow', '<=', 0.5),
        ('dist_pdh_atr', '>', 33.92471694946289),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS25T25_0192:
    name = 'V3_SHORT_S25T25_092'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.6314936620870897
    cpcv_min_wr = 0.4830508474576271
    constraints = [
        ('atr_14', '>', 4.700997352600098),
        ('atr_14', '>', 7.3564982414245605),
        ('dist_pdh_atr', '<=', -7.51108717918396),
        ('atr_50', '>', 7.859732151031494),
        ('sigma_ratio_5_15', '<=', 1.9677127599716187),
        ('dist_pdh_atr', '<=', -43.907331466674805),
        ('atr_50', '>', 9.218235492706299),
        ('range_pos_50', '>', 0.6698040664196014),
        ('ema_slope_20', '<=', 2.1671866178512573),
        ('atr_5', '<=', 11.3272123336792),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS25T25_0193:
    name = 'V3_SHORT_S25T25_093'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.615581577425103
    cpcv_min_wr = 0.46846846846846846
    constraints = [
        ('atr_14', '>', 4.700997352600098),
        ('atr_14', '>', 7.3564982414245605),
        ('dist_pdh_atr', '>', -7.51108717918396),
        ('ema_distance', '>', -1.1763188242912292),
        ('atr_50', '<=', 11.083081722259521),
        ('hurst_proxy_50', '<=', 1.9111740589141846),
        ('dow', '>', 1.5),
        ('dist_pdh_atr', '>', -2.010227918624878),
        ('dist_pdh_atr', '<=', 24.77925205230713),
        ('dist_vwap_atr', '<=', -3.205049514770508),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS25T25_0194:
    name = 'V3_SHORT_S25T25_094'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.6493262249863412
    cpcv_min_wr = 0.54
    constraints = [
        ('atr_14', '>', 4.700997352600098),
        ('atr_14', '>', 7.3564982414245605),
        ('dist_pdh_atr', '<=', -7.51108717918396),
        ('atr_50', '>', 7.859732151031494),
        ('sigma_ratio_5_15', '>', 1.9677127599716187),
        ('dist_pdl_atr', '<=', 18.233357429504395),
        ('ema_slope_20', '<=', -0.25087061524391174),
        ('dist_pdh_atr', '<=', -26.00394344329834),
        ('sigma_ratio_5_15', '>', 3.074321746826172),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS25T25_0195:
    name = 'V3_SHORT_S25T25_095'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.5491657853842357
    cpcv_min_wr = 0.5268817204301075
    constraints = [
        ('atr_14', '>', 4.700997352600098),
        ('atr_14', '>', 7.3564982414245605),
        ('dist_pdh_atr', '<=', -7.51108717918396),
        ('atr_50', '<=', 7.859732151031494),
        ('dist_pdh_atr', '>', -40.89674186706543),
        ('dist_pdh_atr', '>', -13.274042129516602),
        ('dist_pdl_atr', '<=', 10.986385345458984),
        ('atr_5', '>', 10.071335792541504),
        ('dow', '<=', 1.5),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS25T25_0196:
    name = 'V3_SHORT_S25T25_096'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.6312193549205567
    cpcv_min_wr = 0.4603960396039604
    constraints = [
        ('atr_14', '>', 4.700997352600098),
        ('atr_14', '<=', 7.3564982414245605),
        ('dist_pdh_atr', '>', 2.782620668411255),
        ('dist_pdh_atr', '<=', 52.168800354003906),
        ('atr_50', '<=', 7.227749586105347),
        ('dow', '<=', 3.5),
        ('dist_pdl_atr', '<=', 91.12670516967773),
        ('dist_vwap_atr', '<=', 2.648982286453247),
        ('atr_50', '>', 5.0172224044799805),
        ('dist_pdl_atr', '>', 59.93665313720703),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS25T25_0197:
    name = 'V3_SHORT_S25T25_097'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.6133891248708223
    cpcv_min_wr = 0.49074074074074076
    constraints = [
        ('atr_14', '>', 4.700997352600098),
        ('atr_14', '<=', 7.3564982414245605),
        ('dist_pdh_atr', '>', 2.782620668411255),
        ('dist_pdh_atr', '<=', 52.168800354003906),
        ('atr_50', '>', 7.227749586105347),
        ('dist_pdh_atr', '<=', 31.34073829650879),
        ('ema_distance', '<=', 0.3465716391801834),
        ('dist_vwap_atr', '<=', 7.492036819458008),
        ('range_pos_200', '<=', 0.7266432642936707),
        ('range_pos_50', '<=', 0.3425765782594681),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS25T25_0198:
    name = 'V3_SHORT_S25T25_098'
    side = 'SHORT'
    target_pts = 25.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.5285649156241099
    cpcv_min_wr = 0.46195652173913043
    constraints = [
        ('atr_14', '>', 4.700997352600098),
        ('atr_14', '>', 7.3564982414245605),
        ('dist_pdh_atr', '>', -7.51108717918396),
        ('ema_distance', '<=', -1.1763188242912292),
        ('sigma_ratio_1_15', '<=', 1.51142418384552),
        ('ny_hour', '>', 14.5),
        ('dist_pdl_atr', '<=', 18.64813232421875),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS25T50_0199:
    name = 'V3_LONG_S25T50_101'
    side = 'LONG'
    target_pts = 50.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.5534018556718712
    cpcv_min_wr = 0.46715328467153283
    constraints = [
        ('atr_14', '>', 5.517806768417358),
        ('atr_14', '>', 8.60915470123291),
        ('atr_14', '<=', 11.36486530303955),
        ('is_close_30min', '<=', 0.5),
        ('ny_hour', '>', 11.5),
        ('atr_50', '>', 9.31279182434082),
        ('dist_pdl_atr', '<=', -23.77928638458252),
        ('dist_pdh_atr', '>', -65.31815338134766),
        ('dist_pdh_atr', '>', -52.77103805541992),
        ('dist_pdl_atr', '>', -29.048919677734375),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3ShortS25T50_0200:
    name = 'V3_SHORT_S25T50_099'
    side = 'SHORT'
    target_pts = 50.0
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.6387914369150146
    cpcv_min_wr = 0.4970414201183432
    constraints = [
        ('atr_14', '>', 5.728909015655518),
        ('atr_14', '>', 8.142641544342041),
        ('atr_14', '<=', 11.168227672576904),
        ('is_close_30min', '<=', 0.5),
        ('dist_vwap_atr', '<=', -1.799842655658722),
        ('dist_pdl_atr', '>', -6.3654491901397705),
        ('dist_pdl_atr', '<=', 17.90646457672119),
        ('dist_pdl_atr', '>', 11.61466360092163),
        ('atr_14', '<=', 10.42824649810791),
        ('hurst_proxy_50', '>', 2.142161011695862),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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

class V3LongS40T80_0201:
    name = 'V3_LONG_S40T80_102'
    side = 'LONG'
    target_pts = 80.0
    stop_pts = 40.0
    max_hold_bars = 150
    cpcv_mean_wr = 0.5892495828423502
    cpcv_min_wr = 0.48148148148148145
    constraints = [
        ('atr_14', '>', 6.609342575073242),
        ('atr_50', '>', 10.046996116638184),
        ('atr_50', '>', 15.28089189529419),
        ('dist_pdh_atr', '>', -15.978958129882812),
        ('dist_vwap_atr', '<=', -4.134654521942139),
        ('dow', '<=', 1.5),
        ('dist_pdh_atr', '>', -7.623062372207642),
        ('autocorr_5', '<=', -0.0073968463111668825),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
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
    V3LongS8T8_0001(),
    V3LongS8T8_0002(),
    V3LongS8T8_0003(),
    V3LongS8T8_0004(),
    V3LongS8T8_0005(),
    V3LongS8T8_0006(),
    V3ShortS8T8_0007(),
    V3LongS12T12_0008(),
    V3LongS12T12_0009(),
    V3LongS12T12_0010(),
    V3LongS12T12_0011(),
    V3LongS12T12_0012(),
    V3LongS12T12_0013(),
    V3LongS12T12_0014(),
    V3LongS12T12_0015(),
    V3LongS12T12_0016(),
    V3LongS12T12_0017(),
    V3ShortS12T12_0018(),
    V3ShortS12T12_0019(),
    V3ShortS12T12_0020(),
    V3ShortS12T12_0021(),
    V3ShortS12T12_0022(),
    V3ShortS12T12_0023(),
    V3ShortS12T12_0024(),
    V3ShortS12T12_0025(),
    V3ShortS12T12_0026(),
    V3ShortS12T12_0027(),
    V3LongS16T16_0028(),
    V3LongS16T16_0029(),
    V3LongS16T16_0030(),
    V3LongS16T16_0031(),
    V3LongS16T16_0032(),
    V3LongS16T16_0033(),
    V3LongS16T16_0034(),
    V3LongS16T16_0035(),
    V3LongS16T16_0036(),
    V3LongS16T16_0037(),
    V3ShortS16T16_0038(),
    V3ShortS16T16_0039(),
    V3ShortS16T16_0040(),
    V3ShortS16T16_0041(),
    V3ShortS16T16_0042(),
    V3ShortS16T16_0043(),
    V3ShortS16T16_0044(),
    V3LongS20T20_0045(),
    V3LongS20T20_0046(),
    V3LongS20T20_0047(),
    V3LongS20T20_0048(),
    V3LongS20T20_0049(),
    V3LongS20T20_0050(),
    V3LongS20T20_0051(),
    V3LongS20T20_0052(),
    V3LongS20T20_0053(),
    V3LongS20T20_0054(),
    V3LongS20T20_0055(),
    V3LongS20T20_0056(),
    V3LongS20T20_0057(),
    V3ShortS20T20_0058(),
    V3ShortS20T20_0059(),
    V3ShortS20T20_0060(),
    V3ShortS20T20_0061(),
    V3ShortS20T20_0062(),
    V3LongS8T8_0063(),
    V3LongS8T8_0064(),
    V3LongS8T8_0065(),
    V3LongS8T8_0066(),
    V3LongS8T8_0067(),
    V3LongS8T8_0068(),
    V3LongS8T8_0069(),
    V3LongS8T8_0070(),
    V3LongS8T8_0071(),
    V3LongS8T8_0072(),
    V3LongS8T8_0073(),
    V3ShortS8T8_0074(),
    V3ShortS8T8_0075(),
    V3ShortS8T8_0076(),
    V3ShortS8T8_0077(),
    V3ShortS8T8_0078(),
    V3LongS12T12_0079(),
    V3LongS12T12_0080(),
    V3LongS12T12_0081(),
    V3LongS12T12_0082(),
    V3LongS12T12_0083(),
    V3ShortS12T12_0084(),
    V3ShortS12T12_0085(),
    V3ShortS12T12_0086(),
    V3ShortS12T12_0087(),
    V3ShortS12T12_0088(),
    V3ShortS12T12_0089(),
    V3ShortS12T12_0090(),
    V3ShortS12T12_0091(),
    V3ShortS12T12_0092(),
    V3ShortS12T12_0093(),
    V3LongS16T16_0094(),
    V3LongS16T16_0095(),
    V3LongS16T16_0096(),
    V3LongS16T16_0097(),
    V3LongS16T16_0098(),
    V3LongS16T16_0099(),
    V3LongS16T16_0100(),
    V3LongS16T16_0101(),
    V3LongS16T16_0102(),
    V3LongS16T16_0103(),
    V3LongS16T16_0104(),
    V3LongS16T16_0105(),
    V3LongS16T16_0106(),
    V3LongS16T16_0107(),
    V3LongS16T16_0108(),
    V3LongS16T16_0109(),
    V3ShortS16T16_0110(),
    V3ShortS16T16_0111(),
    V3ShortS16T16_0112(),
    V3ShortS16T16_0113(),
    V3ShortS16T16_0114(),
    V3ShortS16T16_0115(),
    V3ShortS16T16_0116(),
    V3ShortS16T16_0117(),
    V3ShortS16T16_0118(),
    V3ShortS16T16_0119(),
    V3ShortS16T16_0120(),
    V3ShortS16T16_0121(),
    V3ShortS16T16_0122(),
    V3ShortS16T16_0123(),
    V3ShortS16T16_0124(),
    V3LongS20T20_0125(),
    V3LongS20T20_0126(),
    V3LongS20T20_0127(),
    V3LongS20T20_0128(),
    V3LongS20T20_0129(),
    V3LongS20T20_0130(),
    V3LongS20T20_0131(),
    V3LongS20T20_0132(),
    V3LongS20T20_0133(),
    V3LongS20T20_0134(),
    V3LongS20T20_0135(),
    V3LongS20T20_0136(),
    V3LongS20T20_0137(),
    V3LongS20T20_0138(),
    V3LongS20T20_0139(),
    V3LongS20T20_0140(),
    V3LongS20T20_0141(),
    V3ShortS20T20_0142(),
    V3ShortS20T20_0143(),
    V3ShortS20T20_0144(),
    V3ShortS20T20_0145(),
    V3ShortS20T20_0146(),
    V3ShortS20T20_0147(),
    V3ShortS20T20_0148(),
    V3ShortS20T20_0149(),
    V3ShortS20T20_0150(),
    V3ShortS20T20_0151(),
    V3ShortS20T20_0152(),
    V3ShortS20T20_0153(),
    V3ShortS20T20_0154(),
    V3ShortS20T20_0155(),
    V3ShortS20T20_0156(),
    V3ShortS20T20_0157(),
    V3ShortS20T20_0158(),
    V3ShortS20T20_0159(),
    V3ShortS20T20_0160(),
    V3LongS25T25_0161(),
    V3LongS25T25_0162(),
    V3LongS25T25_0163(),
    V3LongS25T25_0164(),
    V3LongS25T25_0165(),
    V3LongS25T25_0166(),
    V3LongS25T25_0167(),
    V3LongS25T25_0168(),
    V3LongS25T25_0169(),
    V3LongS25T25_0170(),
    V3LongS25T25_0171(),
    V3LongS25T25_0172(),
    V3ShortS25T25_0173(),
    V3ShortS25T25_0174(),
    V3ShortS25T25_0175(),
    V3ShortS25T25_0176(),
    V3ShortS25T25_0177(),
    V3ShortS25T25_0178(),
    V3ShortS25T25_0179(),
    V3ShortS25T25_0180(),
    V3ShortS25T25_0181(),
    V3ShortS25T25_0182(),
    V3ShortS25T25_0183(),
    V3ShortS25T25_0184(),
    V3ShortS25T25_0185(),
    V3ShortS25T25_0186(),
    V3ShortS25T25_0187(),
    V3ShortS25T25_0188(),
    V3ShortS25T25_0189(),
    V3ShortS25T25_0190(),
    V3ShortS25T25_0191(),
    V3ShortS25T25_0192(),
    V3ShortS25T25_0193(),
    V3ShortS25T25_0194(),
    V3ShortS25T25_0195(),
    V3ShortS25T25_0196(),
    V3ShortS25T25_0197(),
    V3ShortS25T25_0198(),
    V3LongS25T50_0199(),
    V3ShortS25T50_0200(),
    V3LongS40T80_0201(),
]