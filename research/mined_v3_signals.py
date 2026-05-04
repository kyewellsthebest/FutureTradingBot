"""
Auto-generated v3 pattern Signal classes — ELITE FILTER (final).
Generated: 2026-05-04T03:19:10.800547+00:00
Survivors: 23 elite patterns (CPCV mean WR >= 65%, min fold >= 55%, n >= 200)
  LONG:  14  SHORT: 9
Source: combined leak-fixed mined_v3_*.json
"""
from __future__ import annotations
import pandas as pd
from research.pattern_miner_v3 import build_v3_features

class V3LongS16T16_001:
    name = 'V3_LONG_S16T16_001'
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
            if op == '<=': mask &= (v <= thr)
            else: mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        c = intraday['close'].loc[idx]
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS20T20_002:
    name = 'V3_LONG_S20T20_002'
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
            if op == '<=': mask &= (v <= thr)
            else: mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        c = intraday['close'].loc[idx]
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS12T12_003:
    name = 'V3_LONG_S12T12_003'
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
            if op == '<=': mask &= (v <= thr)
            else: mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        c = intraday['close'].loc[idx]
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS16T16_004:
    name = 'V3_LONG_S16T16_004'
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
            if op == '<=': mask &= (v <= thr)
            else: mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        c = intraday['close'].loc[idx]
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3ShortS16T16_005:
    name = 'V3_SHORT_S16T16_001'
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
            if op == '<=': mask &= (v <= thr)
            else: mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        c = intraday['close'].loc[idx]
        sign = 1 if 'SHORT' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS20T20_006:
    name = 'V3_LONG_S20T20_005'
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
            if op == '<=': mask &= (v <= thr)
            else: mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        c = intraday['close'].loc[idx]
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS20T20_007:
    name = 'V3_LONG_S20T20_006'
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
            if op == '<=': mask &= (v <= thr)
            else: mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        c = intraday['close'].loc[idx]
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS20T20_008:
    name = 'V3_LONG_S20T20_007'
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
            if op == '<=': mask &= (v <= thr)
            else: mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        c = intraday['close'].loc[idx]
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS20T20_009:
    name = 'V3_LONG_S20T20_008'
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
            if op == '<=': mask &= (v <= thr)
            else: mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        c = intraday['close'].loc[idx]
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS20T20_010:
    name = 'V3_LONG_S20T20_009'
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
            if op == '<=': mask &= (v <= thr)
            else: mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        c = intraday['close'].loc[idx]
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS20T20_011:
    name = 'V3_LONG_S20T20_010'
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
            if op == '<=': mask &= (v <= thr)
            else: mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        c = intraday['close'].loc[idx]
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS20T20_012:
    name = 'V3_LONG_S20T20_011'
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
            if op == '<=': mask &= (v <= thr)
            else: mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        c = intraday['close'].loc[idx]
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3ShortS20T20_013:
    name = 'V3_SHORT_S20T20_002'
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
            if op == '<=': mask &= (v <= thr)
            else: mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        c = intraday['close'].loc[idx]
        sign = 1 if 'SHORT' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3ShortS20T20_014:
    name = 'V3_SHORT_S20T20_003'
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
            if op == '<=': mask &= (v <= thr)
            else: mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        c = intraday['close'].loc[idx]
        sign = 1 if 'SHORT' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3ShortS20T20_015:
    name = 'V3_SHORT_S20T20_004'
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
            if op == '<=': mask &= (v <= thr)
            else: mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        c = intraday['close'].loc[idx]
        sign = 1 if 'SHORT' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS25T25_016:
    name = 'V3_LONG_S25T25_012'
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
            if op == '<=': mask &= (v <= thr)
            else: mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        c = intraday['close'].loc[idx]
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3ShortS25T25_017:
    name = 'V3_SHORT_S25T25_005'
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
            if op == '<=': mask &= (v <= thr)
            else: mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        c = intraday['close'].loc[idx]
        sign = 1 if 'SHORT' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3ShortS25T25_018:
    name = 'V3_SHORT_S25T25_006'
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
            if op == '<=': mask &= (v <= thr)
            else: mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        c = intraday['close'].loc[idx]
        sign = 1 if 'SHORT' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3ShortS25T25_019:
    name = 'V3_SHORT_S25T25_007'
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
            if op == '<=': mask &= (v <= thr)
            else: mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        c = intraday['close'].loc[idx]
        sign = 1 if 'SHORT' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS20T30_020:
    name = 'V3_LONG_S20T30_013'
    side = 'LONG'
    target_pts = 30.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.6977764321977353
    cpcv_min_wr = 0.591304347826087
    constraints = [
        ('atr_14', '>', 4.331952810287476),
        ('atr_50', '>', 6.1301610469818115),
        ('atr_14', '<=', 8.761150360107422),
        ('dist_vwap_atr', '<=', 1.581918179988861),
        ('atr_50', '<=', 8.077057361602783),
        ('dist_vwap_atr', '<=', -7.274601697921753),
        ('dow', '>', 1.5),
        ('ofi_20', '>', -4005.530029296875),
        ('range_pos_200', '<=', 0.22749794274568558),
        ('dist_pdh_atr', '>', -30.60495662689209),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
            v = feats[col]
            if op == '<=': mask &= (v <= thr)
            else: mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        c = intraday['close'].loc[idx]
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3ShortS20T30_021:
    name = 'V3_SHORT_S20T30_008'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 20.0
    max_hold_bars = 75
    cpcv_mean_wr = 0.7470523690907551
    cpcv_min_wr = 0.6616161616161617
    constraints = [
        ('atr_14', '>', 4.706928014755249),
        ('atr_14', '<=', 6.905531883239746),
        ('dist_pdh_atr', '<=', -7.8669350147247314),
        ('dist_pdl_atr', '<=', -35.268310546875),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
            v = feats[col]
            if op == '<=': mask &= (v <= thr)
            else: mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        c = intraday['close'].loc[idx]
        sign = 1 if 'SHORT' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3LongS25T37_022:
    name = 'V3_LONG_S25T37_014'
    side = 'LONG'
    target_pts = 37.5
    stop_pts = 25.0
    max_hold_bars = 90
    cpcv_mean_wr = 0.7042993412910767
    cpcv_min_wr = 0.6096654275092936
    constraints = [
        ('atr_14', '>', 5.3978352546691895),
        ('atr_14', '>', 8.670782566070557),
        ('dist_pdh_atr', '>', -7.579569339752197),
        ('dist_pdl_atr', '<=', 7.546584844589233),
        ('atr_50', '>', 8.918250560760498),
        ('dist_pdl_atr', '>', 1.7903075814247131),
        ('hurst_proxy_50', '<=', 1.08343505859375),
        ('atr_50', '<=', 11.711406230926514),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
            v = feats[col]
            if op == '<=': mask &= (v <= thr)
            else: mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        c = intraday['close'].loc[idx]
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class V3ShortS15T30_023:
    name = 'V3_SHORT_S15T30_009'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 60
    cpcv_mean_wr = 0.6527545048469758
    cpcv_min_wr = 0.5821428571428572
    constraints = [
        ('atr_14', '>', 4.830974578857422),
        ('atr_14', '<=', 6.751310348510742),
        ('dist_pdh_atr', '<=', -7.469935894012451),
        ('dist_pdl_atr', '<=', -34.83729362487793),
    ]

    def generate(self, intraday, daily):
        feats = build_v3_features(intraday, daily)
        if feats.empty:
            return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            if col not in feats.columns:
                return pd.DataFrame(columns=['signal_time','signal_name','side','entry_px','target_hint'])
            v = feats[col]
            if op == '<=': mask &= (v <= thr)
            else: mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
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
    V3LongS16T16_001(),
    V3LongS20T20_002(),
    V3LongS12T12_003(),
    V3LongS16T16_004(),
    V3ShortS16T16_005(),
    V3LongS20T20_006(),
    V3LongS20T20_007(),
    V3LongS20T20_008(),
    V3LongS20T20_009(),
    V3LongS20T20_010(),
    V3LongS20T20_011(),
    V3LongS20T20_012(),
    V3ShortS20T20_013(),
    V3ShortS20T20_014(),
    V3ShortS20T20_015(),
    V3LongS25T25_016(),
    V3ShortS25T25_017(),
    V3ShortS25T25_018(),
    V3ShortS25T25_019(),
    V3LongS20T30_020(),
    V3ShortS20T30_021(),
    V3LongS25T37_022(),
    V3ShortS15T30_023(),
]