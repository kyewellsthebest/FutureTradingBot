"""
Auto-generated 60%+ WR pattern Signal classes.
Generated: 2026-04-27T13:29:23.914184+00:00
Patterns: 16
"""
from __future__ import annotations
import pandas as pd


class WRLongT12S10_01:
    name = "WR_LONG_T12S10_01"
    side = 'LONG'
    target_pts = 12.0
    stop_pts = 10.0
    max_hold_bars = 15
    expected_oos_wr = 0.6802973977695167
    expected_oos_n = 269
    expected_oos_ev_dollars = 33.271375464684006
    constraints = [
        ('dist_pdh_atr', '<=', -2.184652805328369),
        ('atr_14', '>', 5.845218896865845),
        ('atr_14', '<=', 35.44577217102051),
        ('dist_pdl_atr', '<=', 6.144991874694824),
        ('dist_pdl_atr', '<=', 1.1522971391677856),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features
        feats = build_features(intraday, daily)
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
        # natural target = entry +/- target_pts
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class WRShortT12S10_02:
    name = "WR_SHORT_T12S10_02"
    side = 'SHORT'
    target_pts = 12.0
    stop_pts = 10.0
    max_hold_bars = 15
    expected_oos_wr = 0.8894009216589862
    expected_oos_n = 217
    expected_oos_ev_dollars = 83.4562211981567
    constraints = [
        ('dist_pdh_atr', '>', -1.7907466292381287),
        ('dist_pdh_atr', '>', -0.9147045612335205),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features
        feats = build_features(intraday, daily)
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
        # natural target = entry +/- target_pts
        sign = 1 if 'SHORT' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class WRShortT12S10_03:
    name = "WR_SHORT_T12S10_03"
    side = 'SHORT'
    target_pts = 12.0
    stop_pts = 10.0
    max_hold_bars = 15
    expected_oos_wr = 0.7100977198697068
    expected_oos_n = 307
    expected_oos_ev_dollars = 40.42345276872964
    constraints = [
        ('dist_pdh_atr', '>', -1.7907466292381287),
        ('dist_pdh_atr', '<=', -0.9147045612335205),
        ('atr_14', '<=', 12.543129920959473),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features
        feats = build_features(intraday, daily)
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
        # natural target = entry +/- target_pts
        sign = 1 if 'SHORT' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class WRLongT15S10_04:
    name = "WR_LONG_T15S10_04"
    side = 'LONG'
    target_pts = 15.0
    stop_pts = 10.0
    max_hold_bars = 20
    expected_oos_wr = 0.6341463414634146
    expected_oos_n = 287
    expected_oos_ev_dollars = 41.219512195121965
    constraints = [
        ('dist_pdh_atr', '<=', -6.414770841598511),
        ('dist_pdl_atr', '<=', 6.170702695846558),
        ('dist_pdl_atr', '<=', 1.1565665006637573),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features
        feats = build_features(intraday, daily)
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
        # natural target = entry +/- target_pts
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class WRShortT15S10_05:
    name = "WR_SHORT_T15S10_05"
    side = 'SHORT'
    target_pts = 15.0
    stop_pts = 10.0
    max_hold_bars = 20
    expected_oos_wr = 0.8850574712643678
    expected_oos_n = 174
    expected_oos_ev_dollars = 108.96551724137933
    constraints = [
        ('dist_pdh_atr', '>', -1.6290432214736938),
        ('atr_14', '<=', 12.871754169464111),
        ('dist_pdh_atr', '>', -1.12160986661911),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features
        feats = build_features(intraday, daily)
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
        # natural target = entry +/- target_pts
        sign = 1 if 'SHORT' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class WRShortT15S10_06:
    name = "WR_SHORT_T15S10_06"
    side = 'SHORT'
    target_pts = 15.0
    stop_pts = 10.0
    max_hold_bars = 20
    expected_oos_wr = 0.6984126984126984
    expected_oos_n = 189
    expected_oos_ev_dollars = 58.571428571428555
    constraints = [
        ('dist_pdh_atr', '>', -1.6290432214736938),
        ('atr_14', '<=', 12.871754169464111),
        ('dist_pdh_atr', '<=', -1.12160986661911),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features
        feats = build_features(intraday, daily)
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
        # natural target = entry +/- target_pts
        sign = 1 if 'SHORT' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class WRShortT15S10_07:
    name = "WR_SHORT_T15S10_07"
    side = 'SHORT'
    target_pts = 15.0
    stop_pts = 10.0
    max_hold_bars = 20
    expected_oos_wr = 0.6096096096096096
    expected_oos_n = 333
    expected_oos_ev_dollars = 34.5945945945946
    constraints = [
        ('dist_pdh_atr', '>', -1.6290432214736938),
        ('atr_14', '>', 12.871754169464111),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features
        feats = build_features(intraday, daily)
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
        # natural target = entry +/- target_pts
        sign = 1 if 'SHORT' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class WRLongT15S12_08:
    name = "WR_LONG_T15S12_08"
    side = 'LONG'
    target_pts = 15.0
    stop_pts = 12.0
    max_hold_bars = 20
    expected_oos_wr = 0.7299270072992701
    expected_oos_n = 274
    expected_oos_ev_dollars = 61.67883211678831
    constraints = [
        ('dist_pdh_atr', '<=', -2.293734550476074),
        ('atr_14', '>', 6.433844089508057),
        ('dist_pdl_atr', '<=', 6.170702695846558),
        ('dist_pdl_atr', '<=', 1.1295526623725891),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features
        feats = build_features(intraday, daily)
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
        # natural target = entry +/- target_pts
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class WRShortT15S12_09:
    name = "WR_SHORT_T15S12_09"
    side = 'SHORT'
    target_pts = 15.0
    stop_pts = 12.0
    max_hold_bars = 20
    expected_oos_wr = 0.8583333333333333
    expected_oos_n = 360
    expected_oos_ev_dollars = 98.91666666666666
    constraints = [
        ('dist_pdh_atr', '>', -2.1832281351089478),
        ('dist_pdh_atr', '>', -1.1625027656555176),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features
        feats = build_features(intraday, daily)
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
        # natural target = entry +/- target_pts
        sign = 1 if 'SHORT' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class WRShortT15S12_10:
    name = "WR_SHORT_T15S12_10"
    side = 'SHORT'
    target_pts = 15.0
    stop_pts = 12.0
    max_hold_bars = 20
    expected_oos_wr = 0.7740112994350282
    expected_oos_n = 177
    expected_oos_ev_dollars = 74.46327683615819
    constraints = [
        ('dist_pdh_atr', '>', -2.1832281351089478),
        ('dist_pdh_atr', '<=', -1.1625027656555176),
        ('atr_14', '<=', 11.701662540435791),
        ('range_pos_50', '<=', 0.8260910511016846),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features
        feats = build_features(intraday, daily)
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
        # natural target = entry +/- target_pts
        sign = 1 if 'SHORT' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class WRLongT20S10_11:
    name = "WR_LONG_T20S10_11"
    side = 'LONG'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    expected_oos_wr = 0.6140350877192983
    expected_oos_n = 285
    expected_oos_ev_dollars = 66.49122807017545
    constraints = [
        ('dist_pdh_atr', '<=', -3.000650405883789),
        ('atr_14', '>', 5.522615194320679),
        ('dist_pdl_atr', '<=', 5.765309810638428),
        ('dist_pdl_atr', '<=', 1.1565665006637573),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features
        feats = build_features(intraday, daily)
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
        # natural target = entry +/- target_pts
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class WRShortT20S10_12:
    name = "WR_SHORT_T20S10_12"
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    expected_oos_wr = 0.7862318840579711
    expected_oos_n = 276
    expected_oos_ev_dollars = 121.59420289855075
    constraints = [
        ('dist_pdh_atr', '>', -2.303878426551819),
        ('dist_pdh_atr', '>', -1.472390055656433),
        ('atr_14', '<=', 12.404708862304688),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features
        feats = build_features(intraday, daily)
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
        # natural target = entry +/- target_pts
        sign = 1 if 'SHORT' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class WRShortT20S10_13:
    name = "WR_SHORT_T20S10_13"
    side = 'SHORT'
    target_pts = 20.0
    stop_pts = 10.0
    max_hold_bars = 30
    expected_oos_wr = 0.6312056737588653
    expected_oos_n = 282
    expected_oos_ev_dollars = 71.98581560283688
    constraints = [
        ('dist_pdh_atr', '>', -2.303878426551819),
        ('dist_pdh_atr', '>', -1.472390055656433),
        ('atr_14', '>', 12.404708862304688),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features
        feats = build_features(intraday, daily)
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
        # natural target = entry +/- target_pts
        sign = 1 if 'SHORT' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class WRLongT10S8_14:
    name = "WR_LONG_T10S8_14"
    side = 'LONG'
    target_pts = 10.0
    stop_pts = 8.0
    max_hold_bars = 10
    expected_oos_wr = 0.6651162790697674
    expected_oos_n = 215
    expected_oos_ev_dollars = 23.02325581395349
    constraints = [
        ('atr_14', '>', 5.522525310516357),
        ('atr_14', '<=', 26.710418701171875),
        ('dist_pdh_atr', '<=', -1.788422167301178),
        ('dist_pdh_atr', '<=', -6.904449701309204),
        ('dist_pdl_atr', '<=', 5.721165895462036),
        ('dist_pdl_atr', '<=', 1.1565665006637573),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features
        feats = build_features(intraday, daily)
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
        # natural target = entry +/- target_pts
        sign = 1 if 'LONG' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class WRShortT10S8_15:
    name = "WR_SHORT_T10S8_15"
    side = 'SHORT'
    target_pts = 10.0
    stop_pts = 8.0
    max_hold_bars = 10
    expected_oos_wr = 0.864516129032258
    expected_oos_n = 155
    expected_oos_ev_dollars = 62.90322580645161
    constraints = [
        ('dist_pdh_atr', '>', -1.7907466292381287),
        ('atr_14', '<=', 12.974918365478516),
        ('dist_pdh_atr', '>', -1.065984308719635),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features
        feats = build_features(intraday, daily)
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
        # natural target = entry +/- target_pts
        sign = 1 if 'SHORT' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

class WRShortT10S8_16:
    name = "WR_SHORT_T10S8_16"
    side = 'SHORT'
    target_pts = 10.0
    stop_pts = 8.0
    max_hold_bars = 10
    expected_oos_wr = 0.6527777777777778
    expected_oos_n = 288
    expected_oos_ev_dollars = 20.555555555555557
    constraints = [
        ('dist_pdh_atr', '>', -1.7907466292381287),
        ('atr_14', '<=', 12.974918365478516),
        ('dist_pdh_atr', '<=', -1.065984308719635),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features
        feats = build_features(intraday, daily)
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
        # natural target = entry +/- target_pts
        sign = 1 if 'SHORT' == 'LONG' else -1
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values,
            'target_hint': c.values + sign * self.target_pts,
        })

ALL_WR_SIGNALS = [
    WRLongT12S10_01(),
    WRShortT12S10_02(),
    WRShortT12S10_03(),
    WRLongT15S10_04(),
    WRShortT15S10_05(),
    WRShortT15S10_06(),
    WRShortT15S10_07(),
    WRLongT15S12_08(),
    WRShortT15S12_09(),
    WRShortT15S12_10(),
    WRLongT20S10_11(),
    WRShortT20S10_12(),
    WRShortT20S10_13(),
    WRLongT10S8_14(),
    WRShortT10S8_15(),
    WRShortT10S8_16(),
]