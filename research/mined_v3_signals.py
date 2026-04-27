"""
Auto-generated v3 pattern Signal classes.
Generated: 2026-04-27T17:30:46.406250+00:00
Survivors: 29  (LONG=11, SHORT=18)
Validation: deep tree + 5-fold CPCV (Lopez de Prado),
            train_wr ≥ 58%, cpcv_mean_wr ≥ 55%,
            cpcv_min_fold ≥ 50%, target = 2× stop
"""
from __future__ import annotations
import pandas as pd


class V3LongS15T30_01:
    name = 'V3_LONG_S15T30_01'
    side = 'LONG'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 40
    cpcv_mean_wr = 0.9388313021256607
    cpcv_min_wr = 0.9044585987261147
    constraints = [
        ('dist_pdh_atr', '<=', -4.2775959968566895),
        ('atr_14', '>', 7.711775302886963),
        ('dist_pdl_atr', '<=', 3.173346996307373),
        ('dist_pdl_atr', '<=', 1.1629811525344849),
        ('atr_14', '<=', 18.097728729248047),
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

class V3LongS15T30_02:
    name = 'V3_LONG_S15T30_02'
    side = 'LONG'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 40
    cpcv_mean_wr = 0.7176114612199076
    cpcv_min_wr = 0.6255924170616114
    constraints = [
        ('dist_pdh_atr', '<=', -4.2775959968566895),
        ('atr_14', '>', 7.711775302886963),
        ('dist_pdl_atr', '<=', 3.173346996307373),
        ('dist_pdl_atr', '>', 1.1629811525344849),
        ('range_pos_50', '>', 0.13373978435993195),
        ('atr_14', '<=', 22.995067596435547),
        ('dist_pdl_atr', '<=', 2.408532738685608),
        ('atr_50', '<=', 12.977357864379883),
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

class V3LongS15T30_03:
    name = 'V3_LONG_S15T30_03'
    side = 'LONG'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 40
    cpcv_mean_wr = 0.6459788564829605
    cpcv_min_wr = 0.576271186440678
    constraints = [
        ('dist_pdh_atr', '<=', -4.2775959968566895),
        ('atr_14', '>', 7.711775302886963),
        ('dist_pdl_atr', '<=', 3.173346996307373),
        ('dist_pdl_atr', '<=', 1.1629811525344849),
        ('atr_14', '>', 18.097728729248047),
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

class V3LongS15T30_04:
    name = 'V3_LONG_S15T30_04'
    side = 'LONG'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 40
    cpcv_mean_wr = 0.5843133110647561
    cpcv_min_wr = 0.526595744680851
    constraints = [
        ('dist_pdh_atr', '<=', -4.2775959968566895),
        ('atr_14', '>', 7.711775302886963),
        ('dist_pdl_atr', '>', 3.173346996307373),
        ('range_pos_50', '<=', 0.4592994153499603),
        ('dist_pdh_atr', '<=', -7.360809087753296),
        ('dist_vwap_atr', '>', -2.4402260780334473),
        ('ofi_20', '<=', 4043.8486328125),
        ('dist_vwap_atr', '>', 2.537870168685913),
        ('atr_50', '<=', 10.114824771881104),
        ('dist_pdl_atr', '<=', 36.664628982543945),
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

class V3ShortS15T30_05:
    name = 'V3_SHORT_S15T30_01'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 40
    cpcv_mean_wr = 0.9042821516382183
    cpcv_min_wr = 0.821656050955414
    constraints = [
        ('dist_pdh_atr', '>', -2.1806464195251465),
        ('dist_pdh_atr', '>', -1.347974181175232),
        ('atr_14', '<=', 14.524845123291016),
        ('atr_50', '>', 10.202165603637695),
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

class V3ShortS15T30_06:
    name = 'V3_SHORT_S15T30_02'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 40
    cpcv_mean_wr = 0.7689669712744039
    cpcv_min_wr = 0.6995073891625616
    constraints = [
        ('dist_pdh_atr', '>', -2.1806464195251465),
        ('dist_pdh_atr', '>', -1.347974181175232),
        ('atr_14', '<=', 14.524845123291016),
        ('atr_50', '<=', 10.202165603637695),
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

class V3ShortS15T30_07:
    name = 'V3_SHORT_S15T30_03'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 40
    cpcv_mean_wr = 0.6700729649168509
    cpcv_min_wr = 0.527027027027027
    constraints = [
        ('dist_pdh_atr', '>', -2.1806464195251465),
        ('dist_pdh_atr', '>', -1.347974181175232),
        ('atr_14', '>', 14.524845123291016),
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

class V3ShortS15T30_08:
    name = 'V3_SHORT_S15T30_04'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 40
    cpcv_mean_wr = 0.6129211966163972
    cpcv_min_wr = 0.5036496350364964
    constraints = [
        ('dist_pdh_atr', '<=', -2.1806464195251465),
        ('atr_14', '<=', 9.158025741577148),
        ('atr_14', '>', 3.5013288259506226),
        ('dist_pdl_atr', '>', 5.599935293197632),
        ('dist_vwap_atr', '>', 4.035581350326538),
        ('dist_pdh_atr', '>', -7.4553632736206055),
        ('range_pos_200', '<=', 0.8881178796291351),
        ('dist_pdh_atr', '>', -4.954602241516113),
        ('atr_50', '>', 6.241436004638672),
        ('ema_distance', '<=', 0.1353037729859352),
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

class V3ShortS15T30_09:
    name = 'V3_SHORT_S15T30_05'
    side = 'SHORT'
    target_pts = 30.0
    stop_pts = 15.0
    max_hold_bars = 40
    cpcv_mean_wr = 0.6356391091428235
    cpcv_min_wr = 0.5238095238095238
    constraints = [
        ('dist_pdh_atr', '>', -2.1806464195251465),
        ('dist_pdh_atr', '<=', -1.347974181175232),
        ('range_pos_50', '<=', 0.890802651643753),
        ('atr_50', '<=', 14.508423328399658),
        ('dist_high20_atr', '<=', -1.3494371175765991),
        ('dist_pdh_atr', '<=', -1.8495615124702454),
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

class V3LongS8T16_10:
    name = 'V3_LONG_S8T16_05'
    side = 'LONG'
    target_pts = 16.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.7037788151525065
    cpcv_min_wr = 0.6287878787878788
    constraints = [
        ('dist_pdh_atr', '<=', -6.417268514633179),
        ('dist_pdl_atr', '<=', 5.71639347076416),
        ('dist_pdl_atr', '<=', 0.7824103832244873),
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

class V3ShortS8T16_11:
    name = 'V3_SHORT_S8T16_06'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.9125748806904179
    cpcv_min_wr = 0.8848167539267016
    constraints = [
        ('dist_pdh_atr', '>', -2.1822437047958374),
        ('dist_pdh_atr', '>', -1.009842038154602),
        ('atr_5', '<=', 11.746191501617432),
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

class V3ShortS8T16_12:
    name = 'V3_SHORT_S8T16_07'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.5982030191470388
    cpcv_min_wr = 0.5228070175438596
    constraints = [
        ('dist_pdh_atr', '>', -2.1822437047958374),
        ('dist_pdh_atr', '<=', -1.009842038154602),
        ('atr_50', '<=', 14.493918895721436),
        ('rsi_14', '<=', 59.09880828857422),
        ('dist_pdh_atr', '<=', -1.6572471857070923),
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
    name = 'V3_SHORT_S8T16_08'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.7104437411015139
    cpcv_min_wr = 0.6390977443609023
    constraints = [
        ('dist_pdh_atr', '>', -2.1822437047958374),
        ('dist_pdh_atr', '<=', -1.009842038154602),
        ('atr_50', '<=', 14.493918895721436),
        ('rsi_14', '<=', 59.09880828857422),
        ('dist_pdh_atr', '>', -1.6572471857070923),
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
    name = 'V3_SHORT_S8T16_09'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.6186887278569164
    cpcv_min_wr = 0.5412371134020618
    constraints = [
        ('dist_pdh_atr', '>', -2.1822437047958374),
        ('dist_pdh_atr', '<=', -1.009842038154602),
        ('atr_50', '<=', 14.493918895721436),
        ('rsi_14', '>', 59.09880828857422),
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

class V3ShortS8T16_15:
    name = 'V3_SHORT_S8T16_10'
    side = 'SHORT'
    target_pts = 16.0
    stop_pts = 8.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.6326971442126097
    cpcv_min_wr = 0.565
    constraints = [
        ('dist_pdh_atr', '>', -2.1822437047958374),
        ('dist_pdh_atr', '>', -1.009842038154602),
        ('atr_5', '>', 11.746191501617432),
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

class V3LongS6T12_16:
    name = 'V3_LONG_S6T12_06'
    side = 'LONG'
    target_pts = 12.0
    stop_pts = 6.0
    max_hold_bars = 20
    cpcv_mean_wr = 0.6157107880825674
    cpcv_min_wr = 0.5099337748344371
    constraints = [
        ('dist_pdh_atr', '<=', -2.184652805328369),
        ('atr_5', '<=', 31.775226593017578),
        ('dist_pdh_atr', '<=', -7.258104085922241),
        ('dist_pdl_atr', '<=', 5.6255128383636475),
        ('dist_pdl_atr', '<=', 0.8820010721683502),
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

class V3LongS6T12_17:
    name = 'V3_LONG_S6T12_07'
    side = 'LONG'
    target_pts = 12.0
    stop_pts = 6.0
    max_hold_bars = 20
    cpcv_mean_wr = 0.5680141603236578
    cpcv_min_wr = 0.5232558139534884
    constraints = [
        ('dist_pdh_atr', '<=', -2.184652805328369),
        ('atr_5', '<=', 31.775226593017578),
        ('dist_pdh_atr', '<=', -7.258104085922241),
        ('dist_pdl_atr', '<=', 5.6255128383636475),
        ('dist_pdl_atr', '>', 0.8820010721683502),
        ('atr_5', '<=', 20.16368293762207),
        ('dist_pdl_atr', '<=', 2.3921743631362915),
        ('range_pos_200', '>', 0.08256879821419716),
        ('atr_14', '<=', 12.588799476623535),
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

class V3ShortS6T12_18:
    name = 'V3_SHORT_S6T12_11'
    side = 'SHORT'
    target_pts = 12.0
    stop_pts = 6.0
    max_hold_bars = 20
    cpcv_mean_wr = 0.8101241873722802
    cpcv_min_wr = 0.7936507936507936
    constraints = [
        ('dist_pdh_atr', '>', -2.20857310295105),
        ('dist_pdh_atr', '>', -1.024899661540985),
        ('atr_14', '<=', 12.309150218963623),
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

class V3LongS14T28_19:
    name = 'V3_LONG_S14T28_08'
    side = 'LONG'
    target_pts = 28.0
    stop_pts = 14.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.9066864274393026
    cpcv_min_wr = 0.8670886075949367
    constraints = [
        ('atr_14', '>', 7.711775302886963),
        ('dist_pdh_atr', '<=', -2.629901647567749),
        ('dist_pdl_atr', '<=', 4.127469778060913),
        ('dist_pdl_atr', '<=', 1.1565665006637573),
        ('atr_5', '<=', 19.04809284210205),
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

class V3LongS14T28_20:
    name = 'V3_LONG_S14T28_09'
    side = 'LONG'
    target_pts = 28.0
    stop_pts = 14.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.7040803349956762
    cpcv_min_wr = 0.6581196581196581
    constraints = [
        ('atr_14', '>', 7.711775302886963),
        ('dist_pdh_atr', '<=', -2.629901647567749),
        ('dist_pdl_atr', '<=', 4.127469778060913),
        ('dist_pdl_atr', '>', 1.1565665006637573),
        ('range_pos_50', '>', 0.11741142347455025),
        ('dist_pdl_atr', '<=', 2.4651743173599243),
        ('atr_14', '<=', 15.134600162506104),
        ('dist_pdl_atr', '<=', 1.9804092645645142),
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

class V3LongS14T28_21:
    name = 'V3_LONG_S14T28_10'
    side = 'LONG'
    target_pts = 28.0
    stop_pts = 14.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.6381004278623983
    cpcv_min_wr = 0.5545454545454546
    constraints = [
        ('atr_14', '>', 7.711775302886963),
        ('dist_pdh_atr', '<=', -2.629901647567749),
        ('dist_pdl_atr', '<=', 4.127469778060913),
        ('dist_pdl_atr', '<=', 1.1565665006637573),
        ('atr_5', '>', 19.04809284210205),
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

class V3ShortS14T28_22:
    name = 'V3_SHORT_S14T28_12'
    side = 'SHORT'
    target_pts = 28.0
    stop_pts = 14.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.8766275586078042
    cpcv_min_wr = 0.8549618320610687
    constraints = [
        ('atr_14', '>', 9.16924238204956),
        ('dist_pdl_atr', '>', 2.3352818489074707),
        ('dist_pdh_atr', '>', -1.7577728629112244),
        ('dist_pdh_atr', '>', -0.9237231910228729),
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

class V3ShortS14T28_23:
    name = 'V3_SHORT_S14T28_13'
    side = 'SHORT'
    target_pts = 28.0
    stop_pts = 14.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.7278326691913117
    cpcv_min_wr = 0.593939393939394
    constraints = [
        ('atr_14', '<=', 9.16924238204956),
        ('dist_pdh_atr', '>', -2.1086642742156982),
        ('dist_pdh_atr', '>', -1.6106142401695251),
        ('dist_vwap_atr', '>', 12.724626541137695),
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

class V3ShortS14T28_24:
    name = 'V3_SHORT_S14T28_14'
    side = 'SHORT'
    target_pts = 28.0
    stop_pts = 14.0
    max_hold_bars = 30
    cpcv_mean_wr = 0.6521374007499045
    cpcv_min_wr = 0.5454545454545454
    constraints = [
        ('atr_14', '<=', 9.16924238204956),
        ('dist_pdh_atr', '>', -2.1086642742156982),
        ('dist_pdh_atr', '>', -1.6106142401695251),
        ('dist_vwap_atr', '<=', 12.724626541137695),
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

class V3LongS9T18_25:
    name = 'V3_LONG_S9T18_11'
    side = 'LONG'
    target_pts = 18.0
    stop_pts = 9.0
    max_hold_bars = 25
    cpcv_mean_wr = 0.729847418674774
    cpcv_min_wr = 0.6641221374045801
    constraints = [
        ('dist_pdh_atr', '<=', -2.512966513633728),
        ('atr_14', '>', 5.495700836181641),
        ('dist_pdh_atr', '<=', -7.042763710021973),
        ('dist_pdl_atr', '<=', 2.33821439743042),
        ('dist_pdl_atr', '<=', 0.7824103832244873),
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

class V3ShortS9T18_26:
    name = 'V3_SHORT_S9T18_15'
    side = 'SHORT'
    target_pts = 18.0
    stop_pts = 9.0
    max_hold_bars = 25
    cpcv_mean_wr = 0.797810859987622
    cpcv_min_wr = 0.744
    constraints = [
        ('dist_pdh_atr', '>', -2.3077621459960938),
        ('dist_pdh_atr', '>', -1.1317104697227478),
        ('atr_14', '<=', 12.671159267425537),
        ('dist_pdh_atr', '<=', -0.791479080915451),
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

class V3ShortS9T18_27:
    name = 'V3_SHORT_S9T18_16'
    side = 'SHORT'
    target_pts = 18.0
    stop_pts = 9.0
    max_hold_bars = 25
    cpcv_mean_wr = 0.6264134015879399
    cpcv_min_wr = 0.5490196078431373
    constraints = [
        ('dist_pdh_atr', '>', -2.3077621459960938),
        ('dist_pdh_atr', '<=', -1.1317104697227478),
        ('range_pos_50', '<=', 0.8657806515693665),
        ('atr_50', '<=', 13.635555744171143),
        ('dist_pdh_atr', '<=', -1.6883309483528137),
        ('rsi_14', '<=', 56.1673583984375),
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

class V3ShortS9T18_28:
    name = 'V3_SHORT_S9T18_17'
    side = 'SHORT'
    target_pts = 18.0
    stop_pts = 9.0
    max_hold_bars = 25
    cpcv_mean_wr = 0.6931660699762897
    cpcv_min_wr = 0.6666666666666666
    constraints = [
        ('dist_pdh_atr', '>', -2.3077621459960938),
        ('dist_pdh_atr', '<=', -1.1317104697227478),
        ('range_pos_50', '<=', 0.8657806515693665),
        ('atr_50', '<=', 13.635555744171143),
        ('dist_pdh_atr', '>', -1.6883309483528137),
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

class V3ShortS9T18_29:
    name = 'V3_SHORT_S9T18_18'
    side = 'SHORT'
    target_pts = 18.0
    stop_pts = 9.0
    max_hold_bars = 25
    cpcv_mean_wr = 0.6272472878070942
    cpcv_min_wr = 0.5662650602409639
    constraints = [
        ('dist_pdh_atr', '>', -2.3077621459960938),
        ('dist_pdh_atr', '>', -1.1317104697227478),
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

ALL_V3_SIGNALS = [
    V3LongS15T30_01(),
    V3LongS15T30_02(),
    V3LongS15T30_03(),
    V3LongS15T30_04(),
    V3ShortS15T30_05(),
    V3ShortS15T30_06(),
    V3ShortS15T30_07(),
    V3ShortS15T30_08(),
    V3ShortS15T30_09(),
    V3LongS8T16_10(),
    V3ShortS8T16_11(),
    V3ShortS8T16_12(),
    V3ShortS8T16_13(),
    V3ShortS8T16_14(),
    V3ShortS8T16_15(),
    V3LongS6T12_16(),
    V3LongS6T12_17(),
    V3ShortS6T12_18(),
    V3LongS14T28_19(),
    V3LongS14T28_20(),
    V3LongS14T28_21(),
    V3ShortS14T28_22(),
    V3ShortS14T28_23(),
    V3ShortS14T28_24(),
    V3LongS9T18_25(),
    V3ShortS9T18_26(),
    V3ShortS9T18_27(),
    V3ShortS9T18_28(),
    V3ShortS9T18_29(),
]