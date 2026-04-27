"""
Auto-generated v3 pattern Signal classes.
Generated: 2026-04-27T17:19:31.520798+00:00
Survivors: 16  (LONG=3, SHORT=13)
Validation: deep tree + 5-fold CPCV (Lopez de Prado),
            train_wr ≥ 58%, cpcv_mean_wr ≥ 55%,
            cpcv_min_fold ≥ 50%, target = 2× stop
"""
from __future__ import annotations
import pandas as pd


class V3LongS10T20_01:
    name = 'V3_LONG_S10T20_01'
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.6646106806697046
    cpcv_min_wr = 0.5915492957746479
    constraints = [
        ('dist_pdh_atr', '<=', -3.000650405883789),
        ('atr_5', '>', 4.275170564651489),
        ('dist_pdh_atr', '<=', -8.146883487701416),
        ('dist_pdl_atr', '<=', 5.717226505279541),
        ('dist_pdl_atr', '<=', 1.1565665006637573),
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

class V3ShortS10T20_02:
    name = 'V3_SHORT_S10T20_01'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.9138287409274405
    cpcv_min_wr = 0.9030837004405287
    constraints = [
        ('dist_pdh_atr', '>', -1.616872787475586),
        ('atr_50', '<=', 14.747286319732666),
        ('dist_pdh_atr', '>', -0.953778088092804),
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

class V3ShortS10T20_03:
    name = 'V3_SHORT_S10T20_02'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.7785607081423037
    cpcv_min_wr = 0.6952380952380952
    constraints = [
        ('dist_pdh_atr', '>', -1.616872787475586),
        ('atr_50', '<=', 14.747286319732666),
        ('dist_pdh_atr', '<=', -0.953778088092804),
        ('dist_high20_atr', '<=', -0.9603008329868317),
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

class V3ShortS10T20_04:
    name = 'V3_SHORT_S10T20_03'
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.5996244057070037
    cpcv_min_wr = 0.510989010989011
    constraints = [
        ('dist_pdh_atr', '<=', -1.616872787475586),
        ('dist_pdl_atr', '>', 4.118003845214844),
        ('atr_14', '>', 9.264933586120605),
        ('range_pos_50', '<=', 0.5304614007472992),
        ('dist_pdl_atr', '>', 10.595024108886719),
        ('dist_pdh_atr', '>', -7.044693946838379),
        ('dist_low20_atr', '>', 1.5965101718902588),
        ('rsi_14', '<=', 52.440547943115234),
        ('atr_5', '<=', 16.658029556274414),
        ('range_expansion_5', '<=', 1.0203511118888855),
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

class V3LongS12T24_05:
    name = 'V3_LONG_S12T24_02'
    side = 'LONG'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    cpcv_mean_wr = 0.7166601781335811
    cpcv_min_wr = 0.6712328767123288
    constraints = [
        ('dist_pdh_atr', '<=', -4.457545518875122),
        ('dist_pdl_atr', '<=', 4.592790126800537),
        ('dist_pdl_atr', '<=', 1.1565665006637573),
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

class V3ShortS12T24_06:
    name = 'V3_SHORT_S12T24_04'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    cpcv_mean_wr = 0.8794356644214005
    cpcv_min_wr = 0.8170731707317073
    constraints = [
        ('dist_pdh_atr', '>', -2.181065797805786),
        ('dist_pdh_atr', '>', -1.1625027656555176),
        ('atr_14', '<=', 12.671159267425537),
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

class V3ShortS12T24_07:
    name = 'V3_SHORT_S12T24_05'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    cpcv_mean_wr = 0.7766867025620031
    cpcv_min_wr = 0.7222222222222222
    constraints = [
        ('dist_pdh_atr', '>', -2.181065797805786),
        ('dist_pdh_atr', '<=', -1.1625027656555176),
        ('range_pos_50', '<=', 0.865721732378006),
        ('atr_50', '<=', 13.249554634094238),
        ('dist_pdh_atr', '>', -1.7777313590049744),
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

class V3ShortS12T24_08:
    name = 'V3_SHORT_S12T24_06'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    cpcv_mean_wr = 0.7090072075497204
    cpcv_min_wr = 0.6363636363636364
    constraints = [
        ('dist_pdh_atr', '>', -2.181065797805786),
        ('dist_pdh_atr', '>', -1.1625027656555176),
        ('atr_14', '>', 12.671159267425537),
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

class V3ShortS12T24_09:
    name = 'V3_SHORT_S12T24_07'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    cpcv_mean_wr = 0.5962296413432192
    cpcv_min_wr = 0.5170068027210885
    constraints = [
        ('dist_pdh_atr', '<=', -2.181065797805786),
        ('atr_14', '<=', 9.26645565032959),
        ('atr_14', '>', 3.5013288259506226),
        ('dist_pdl_atr', '>', 5.606090784072876),
        ('dist_vwap_atr', '>', 5.33644962310791),
        ('dist_pdh_atr', '>', -7.513463020324707),
        ('ema_distance', '<=', 0.08307519182562828),
        ('dist_pdh_atr', '>', -4.954837799072266),
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

class V3ShortS12T24_10:
    name = 'V3_SHORT_S12T24_08'
    side = 'SHORT'
    target_pts = 24.0
    stop_pts = 12.0
    max_hold_bars = 35
    cpcv_mean_wr = 0.6216630335523583
    cpcv_min_wr = 0.5980392156862745
    constraints = [
        ('dist_pdh_atr', '>', -2.181065797805786),
        ('dist_pdh_atr', '<=', -1.1625027656555176),
        ('range_pos_50', '<=', 0.865721732378006),
        ('atr_50', '<=', 13.249554634094238),
        ('dist_pdh_atr', '<=', -1.7777313590049744),
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

class V3LongS8T16_11:
    name = 'V3_LONG_S8T16_03'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 8.0
    max_hold_bars = 25
    cpcv_mean_wr = 0.6687116810744205
    cpcv_min_wr = 0.5798816568047337
    constraints = [
        ('dist_pdh_atr', '<=', -6.417268514633179),
        ('dist_pdl_atr', '<=', 5.720261573791504),
        ('dist_pdl_atr', '<=', 0.8704511821269989),
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

class V3ShortS8T16_12:
    name = 'V3_SHORT_S8T16_09'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 8.0
    max_hold_bars = 25
    cpcv_mean_wr = 0.9001377347779395
    cpcv_min_wr = 0.8622754491017964
    constraints = [
        ('dist_pdh_atr', '>', -2.1822437047958374),
        ('dist_pdh_atr', '>', -1.009842038154602),
        ('atr_5', '<=', 10.776604175567627),
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

class V3ShortS8T16_13:
    name = 'V3_SHORT_S8T16_10'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 8.0
    max_hold_bars = 25
    cpcv_mean_wr = 0.6653656689632512
    cpcv_min_wr = 0.5487804878048781
    constraints = [
        ('dist_pdh_atr', '>', -2.1822437047958374),
        ('dist_pdh_atr', '<=', -1.009842038154602),
        ('atr_50', '<=', 14.493918895721436),
        ('rsi_14', '<=', 58.63845443725586),
        ('dist_pdl_atr', '>', 25.782877922058105),
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

class V3ShortS8T16_14:
    name = 'V3_SHORT_S8T16_11'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 8.0
    max_hold_bars = 25
    cpcv_mean_wr = 0.663495820895631
    cpcv_min_wr = 0.6061946902654868
    constraints = [
        ('dist_pdh_atr', '>', -2.1822437047958374),
        ('dist_pdh_atr', '>', -1.009842038154602),
        ('atr_5', '>', 10.776604175567627),
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

class V3ShortS8T16_15:
    name = 'V3_SHORT_S8T16_12'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 8.0
    max_hold_bars = 25
    cpcv_mean_wr = 0.6071342532282503
    cpcv_min_wr = 0.5392156862745098
    constraints = [
        ('dist_pdh_atr', '>', -2.1822437047958374),
        ('dist_pdh_atr', '<=', -1.009842038154602),
        ('atr_50', '<=', 14.493918895721436),
        ('rsi_14', '>', 58.63845443725586),
        ('dist_pdh_atr', '>', -1.4811562895774841),
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

class V3ShortS8T16_16:
    name = 'V3_SHORT_S8T16_13'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 8.0
    max_hold_bars = 25
    cpcv_mean_wr = 0.5898494602740271
    cpcv_min_wr = 0.554140127388535
    constraints = [
        ('dist_pdh_atr', '>', -2.1822437047958374),
        ('dist_pdh_atr', '<=', -1.009842038154602),
        ('atr_50', '<=', 14.493918895721436),
        ('rsi_14', '<=', 58.63845443725586),
        ('dist_pdl_atr', '<=', 25.782877922058105),
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
    V3LongS10T20_01(),
    V3ShortS10T20_02(),
    V3ShortS10T20_03(),
    V3ShortS10T20_04(),
    V3LongS12T24_05(),
    V3ShortS12T24_06(),
    V3ShortS12T24_07(),
    V3ShortS12T24_08(),
    V3ShortS12T24_09(),
    V3ShortS12T24_10(),
    V3LongS8T16_11(),
    V3ShortS8T16_12(),
    V3ShortS8T16_13(),
    V3ShortS8T16_14(),
    V3ShortS8T16_15(),
    V3ShortS8T16_16(),
]