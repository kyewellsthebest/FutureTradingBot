"""
Auto-generated v3 pattern Signal classes.
Generated: 2026-05-04T02:44:28.487499+00:00
Survivors: 62  (LONG=39, SHORT=23)
Validation: deep tree + 5-fold CPCV (Lopez de Prado),
            train_wr ≥ 55%, cpcv_mean_wr ≥ 52%,
            cpcv_min_fold ≥ 48%, target = 2× stop
"""
from __future__ import annotations
import pandas as pd


class V3LongS8T8_01:
    name = 'V3_LONG_S8T8_01'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS8T8_02:
    name = 'V3_LONG_S8T8_02'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS8T8_03:
    name = 'V3_LONG_S8T8_03'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS8T8_04:
    name = 'V3_LONG_S8T8_04'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS8T8_05:
    name = 'V3_LONG_S8T8_05'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS8T8_06:
    name = 'V3_LONG_S8T8_06'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3ShortS8T8_07:
    name = 'V3_SHORT_S8T8_01'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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

class V3LongS12T12_08:
    name = 'V3_LONG_S12T12_07'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS12T12_09:
    name = 'V3_LONG_S12T12_08'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS12T12_10:
    name = 'V3_LONG_S12T12_09'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS12T12_11:
    name = 'V3_LONG_S12T12_10'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS12T12_12:
    name = 'V3_LONG_S12T12_11'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS12T12_13:
    name = 'V3_LONG_S12T12_12'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS12T12_14:
    name = 'V3_LONG_S12T12_13'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS12T12_15:
    name = 'V3_LONG_S12T12_14'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS12T12_16:
    name = 'V3_LONG_S12T12_15'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS12T12_17:
    name = 'V3_LONG_S12T12_16'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3ShortS12T12_18:
    name = 'V3_SHORT_S12T12_02'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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

class V3ShortS12T12_19:
    name = 'V3_SHORT_S12T12_03'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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

class V3ShortS12T12_20:
    name = 'V3_SHORT_S12T12_04'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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

class V3ShortS12T12_21:
    name = 'V3_SHORT_S12T12_05'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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

class V3ShortS12T12_22:
    name = 'V3_SHORT_S12T12_06'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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

class V3ShortS12T12_23:
    name = 'V3_SHORT_S12T12_07'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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

class V3ShortS12T12_24:
    name = 'V3_SHORT_S12T12_08'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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

class V3ShortS12T12_25:
    name = 'V3_SHORT_S12T12_09'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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

class V3ShortS12T12_26:
    name = 'V3_SHORT_S12T12_10'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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

class V3ShortS12T12_27:
    name = 'V3_SHORT_S12T12_11'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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

class V3LongS16T16_28:
    name = 'V3_LONG_S16T16_17'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS16T16_29:
    name = 'V3_LONG_S16T16_18'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS16T16_30:
    name = 'V3_LONG_S16T16_19'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS16T16_31:
    name = 'V3_LONG_S16T16_20'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS16T16_32:
    name = 'V3_LONG_S16T16_21'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS16T16_33:
    name = 'V3_LONG_S16T16_22'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS16T16_34:
    name = 'V3_LONG_S16T16_23'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS16T16_35:
    name = 'V3_LONG_S16T16_24'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS16T16_36:
    name = 'V3_LONG_S16T16_25'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS16T16_37:
    name = 'V3_LONG_S16T16_26'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3ShortS16T16_38:
    name = 'V3_SHORT_S16T16_12'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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

class V3ShortS16T16_39:
    name = 'V3_SHORT_S16T16_13'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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

class V3ShortS16T16_40:
    name = 'V3_SHORT_S16T16_14'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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

class V3ShortS16T16_41:
    name = 'V3_SHORT_S16T16_15'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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

class V3ShortS16T16_42:
    name = 'V3_SHORT_S16T16_16'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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

class V3ShortS16T16_43:
    name = 'V3_SHORT_S16T16_17'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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

class V3ShortS16T16_44:
    name = 'V3_SHORT_S16T16_18'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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

class V3LongS20T20_45:
    name = 'V3_LONG_S20T20_27'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS20T20_46:
    name = 'V3_LONG_S20T20_28'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS20T20_47:
    name = 'V3_LONG_S20T20_29'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS20T20_48:
    name = 'V3_LONG_S20T20_30'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS20T20_49:
    name = 'V3_LONG_S20T20_31'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS20T20_50:
    name = 'V3_LONG_S20T20_32'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS20T20_51:
    name = 'V3_LONG_S20T20_33'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS20T20_52:
    name = 'V3_LONG_S20T20_34'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS20T20_53:
    name = 'V3_LONG_S20T20_35'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS20T20_54:
    name = 'V3_LONG_S20T20_36'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS20T20_55:
    name = 'V3_LONG_S20T20_37'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS20T20_56:
    name = 'V3_LONG_S20T20_38'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS20T20_57:
    name = 'V3_LONG_S20T20_39'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3ShortS20T20_58:
    name = 'V3_SHORT_S20T20_19'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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

class V3ShortS20T20_59:
    name = 'V3_SHORT_S20T20_20'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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

class V3ShortS20T20_60:
    name = 'V3_SHORT_S20T20_21'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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

class V3ShortS20T20_61:
    name = 'V3_SHORT_S20T20_22'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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

class V3ShortS20T20_62:
    name = 'V3_SHORT_S20T20_23'
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
        from research.pattern_miner_v3 import build_v3_features
        feats = build_v3_features(intraday, daily)
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

ALL_V3_SIGNALS = [
    V3LongS8T8_01(),
    V3LongS8T8_02(),
    V3LongS8T8_03(),
    V3LongS8T8_04(),
    V3LongS8T8_05(),
    V3LongS8T8_06(),
    V3ShortS8T8_07(),
    V3LongS12T12_08(),
    V3LongS12T12_09(),
    V3LongS12T12_10(),
    V3LongS12T12_11(),
    V3LongS12T12_12(),
    V3LongS12T12_13(),
    V3LongS12T12_14(),
    V3LongS12T12_15(),
    V3LongS12T12_16(),
    V3LongS12T12_17(),
    V3ShortS12T12_18(),
    V3ShortS12T12_19(),
    V3ShortS12T12_20(),
    V3ShortS12T12_21(),
    V3ShortS12T12_22(),
    V3ShortS12T12_23(),
    V3ShortS12T12_24(),
    V3ShortS12T12_25(),
    V3ShortS12T12_26(),
    V3ShortS12T12_27(),
    V3LongS16T16_28(),
    V3LongS16T16_29(),
    V3LongS16T16_30(),
    V3LongS16T16_31(),
    V3LongS16T16_32(),
    V3LongS16T16_33(),
    V3LongS16T16_34(),
    V3LongS16T16_35(),
    V3LongS16T16_36(),
    V3LongS16T16_37(),
    V3ShortS16T16_38(),
    V3ShortS16T16_39(),
    V3ShortS16T16_40(),
    V3ShortS16T16_41(),
    V3ShortS16T16_42(),
    V3ShortS16T16_43(),
    V3ShortS16T16_44(),
    V3LongS20T20_45(),
    V3LongS20T20_46(),
    V3LongS20T20_47(),
    V3LongS20T20_48(),
    V3LongS20T20_49(),
    V3LongS20T20_50(),
    V3LongS20T20_51(),
    V3LongS20T20_52(),
    V3LongS20T20_53(),
    V3LongS20T20_54(),
    V3LongS20T20_55(),
    V3LongS20T20_56(),
    V3LongS20T20_57(),
    V3ShortS20T20_58(),
    V3ShortS20T20_59(),
    V3ShortS20T20_60(),
    V3ShortS20T20_61(),
    V3ShortS20T20_62(),
]