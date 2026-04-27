"""
Auto-generated from research.pattern_miner. DO NOT EDIT BY HAND.
Generated: 2026-04-27T13:03:59.276907+00:00
Patterns: 20   Source: 1-min NQ, 628,313 bars
"""
from __future__ import annotations
import pandas as pd
from research.pattern_miner import build_features, _empty_signals


class MinedLong01:
    name = "MINED_LONG_01"
    side = 'LONG'
    expected_oos_mean = 43.01963141025641
    expected_oos_n = 624
    constraints = [
        ('dist_pdl_atr', '<=', 4.127802610397339),
        ('dist_pdl_atr', '<=', 1.8947908282279968),
        ('atr_14', '>', 16.24260139465332),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features, _empty_signals
        feats = build_features(intraday, daily)
        if feats.empty:
            return _empty_signals()
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            v = feats[col]
            if op == '<=':
                mask &= (v <= thr)
            else:
                mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty_signals()
        c = intraday['close'].loc[idx]
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values, 'target_hint': float('nan'),
        })

class MinedShort02:
    name = "MINED_SHORT_02"
    side = 'SHORT'
    expected_oos_mean = -11.74678800856531
    expected_oos_n = 1868
    constraints = [
        ('dist_pdl_atr', '>', 4.127802610397339),
        ('dist_pdh_atr', '<=', -2.832748293876648),
        ('atr_14', '<=', 57.1982307434082),
        ('dist_vwap_atr', '<=', -2.820648193359375),
        ('atr_14', '<=', 29.332056045532227),
        ('dist_pdl_atr', '>', 7.326604843139648),
        ('atr_14', '>', 17.77003574371338),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features, _empty_signals
        feats = build_features(intraday, daily)
        if feats.empty:
            return _empty_signals()
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            v = feats[col]
            if op == '<=':
                mask &= (v <= thr)
            else:
                mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty_signals()
        c = intraday['close'].loc[idx]
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values, 'target_hint': float('nan'),
        })

class MinedShort03:
    name = "MINED_SHORT_03"
    side = 'SHORT'
    expected_oos_mean = -27.528846153846153
    expected_oos_n = 234
    constraints = [
        ('dist_pdl_atr', '>', 4.127802610397339),
        ('dist_pdh_atr', '>', -2.832748293876648),
        ('atr_14', '>', 17.538938522338867),
        ('dist_pdh_atr', '>', -1.8648883700370789),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features, _empty_signals
        feats = build_features(intraday, daily)
        if feats.empty:
            return _empty_signals()
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            v = feats[col]
            if op == '<=':
                mask &= (v <= thr)
            else:
                mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty_signals()
        c = intraday['close'].loc[idx]
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values, 'target_hint': float('nan'),
        })

class MinedShort04:
    name = "MINED_SHORT_04"
    side = 'SHORT'
    expected_oos_mean = -8.134232121922626
    expected_oos_n = 2559
    constraints = [
        ('dist_pdl_atr', '>', 4.127802610397339),
        ('dist_pdh_atr', '<=', -2.832748293876648),
        ('atr_14', '<=', 57.1982307434082),
        ('dist_vwap_atr', '>', -2.820648193359375),
        ('dist_pdh_atr', '>', -7.601422309875488),
        ('range_pos_50', '<=', 0.5865893959999084),
        ('atr_14', '>', 10.794135093688965),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features, _empty_signals
        feats = build_features(intraday, daily)
        if feats.empty:
            return _empty_signals()
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            v = feats[col]
            if op == '<=':
                mask &= (v <= thr)
            else:
                mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty_signals()
        c = intraday['close'].loc[idx]
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values, 'target_hint': float('nan'),
        })

class MinedLong05:
    name = "MINED_LONG_05"
    side = 'LONG'
    expected_oos_mean = 24.456692913385826
    expected_oos_n = 254
    constraints = [
        ('dist_pdl_atr', '<=', 4.127802610397339),
        ('dist_pdl_atr', '<=', 1.8947908282279968),
        ('atr_14', '<=', 16.24260139465332),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features, _empty_signals
        feats = build_features(intraday, daily)
        if feats.empty:
            return _empty_signals()
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            v = feats[col]
            if op == '<=':
                mask &= (v <= thr)
            else:
                mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty_signals()
        c = intraday['close'].loc[idx]
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values, 'target_hint': float('nan'),
        })

class MinedLong06:
    name = "MINED_LONG_06"
    side = 'LONG'
    expected_oos_mean = 16.99874686716792
    expected_oos_n = 399
    constraints = [
        ('dist_pdl_atr', '<=', 4.127802610397339),
        ('dist_pdl_atr', '>', 1.8947908282279968),
        ('atr_14', '<=', 28.860551834106445),
        ('dist_pdl_atr', '<=', 3.105867624282837),
        ('atr_14', '>', 16.78220272064209),
        ('range_pos_50', '>', 0.22936878353357315),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features, _empty_signals
        feats = build_features(intraday, daily)
        if feats.empty:
            return _empty_signals()
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            v = feats[col]
            if op == '<=':
                mask &= (v <= thr)
            else:
                mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty_signals()
        c = intraday['close'].loc[idx]
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values, 'target_hint': float('nan'),
        })

class MinedShort07:
    name = "MINED_SHORT_07"
    side = 'SHORT'
    expected_oos_mean = -12.973024316109422
    expected_oos_n = 658
    constraints = [
        ('dist_pdl_atr', '>', 4.127802610397339),
        ('dist_pdh_atr', '<=', -2.832748293876648),
        ('atr_14', '<=', 57.1982307434082),
        ('dist_vwap_atr', '<=', -2.820648193359375),
        ('atr_14', '>', 29.332056045532227),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features, _empty_signals
        feats = build_features(intraday, daily)
        if feats.empty:
            return _empty_signals()
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            v = feats[col]
            if op == '<=':
                mask &= (v <= thr)
            else:
                mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty_signals()
        c = intraday['close'].loc[idx]
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values, 'target_hint': float('nan'),
        })

class MinedShort08:
    name = "MINED_SHORT_08"
    side = 'SHORT'
    expected_oos_mean = -18.06205035971223
    expected_oos_n = 278
    constraints = [
        ('dist_pdl_atr', '>', 4.127802610397339),
        ('dist_pdh_atr', '>', -2.832748293876648),
        ('atr_14', '<=', 17.538938522338867),
        ('dist_vwap_atr', '>', 2.273065209388733),
        ('dist_pdh_atr', '>', -1.7093483209609985),
        ('dist_pdh_atr', '>', -1.1795326471328735),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features, _empty_signals
        feats = build_features(intraday, daily)
        if feats.empty:
            return _empty_signals()
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            v = feats[col]
            if op == '<=':
                mask &= (v <= thr)
            else:
                mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty_signals()
        c = intraday['close'].loc[idx]
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values, 'target_hint': float('nan'),
        })

class MinedShort09:
    name = "MINED_SHORT_09"
    side = 'SHORT'
    expected_oos_mean = -26.465217391304346
    expected_oos_n = 115
    constraints = [
        ('dist_pdl_atr', '>', 4.127802610397339),
        ('dist_pdh_atr', '>', -2.832748293876648),
        ('atr_14', '<=', 17.538938522338867),
        ('dist_vwap_atr', '<=', 2.273065209388733),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features, _empty_signals
        feats = build_features(intraday, daily)
        if feats.empty:
            return _empty_signals()
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            v = feats[col]
            if op == '<=':
                mask &= (v <= thr)
            else:
                mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty_signals()
        c = intraday['close'].loc[idx]
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values, 'target_hint': float('nan'),
        })

class MinedLong10:
    name = "MINED_LONG_10"
    side = 'LONG'
    expected_oos_mean = 14.18421052631579
    expected_oos_n = 399
    constraints = [
        ('dist_pdl_atr', '<=', 4.127802610397339),
        ('dist_pdl_atr', '>', 1.8947908282279968),
        ('atr_14', '>', 28.860551834106445),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features, _empty_signals
        feats = build_features(intraday, daily)
        if feats.empty:
            return _empty_signals()
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            v = feats[col]
            if op == '<=':
                mask &= (v <= thr)
            else:
                mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty_signals()
        c = intraday['close'].loc[idx]
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values, 'target_hint': float('nan'),
        })

class MinedShort11:
    name = "MINED_SHORT_11"
    side = 'SHORT'
    expected_oos_mean = -14.01413881748072
    expected_oos_n = 389
    constraints = [
        ('dist_pdl_atr', '>', 4.127802610397339),
        ('dist_pdh_atr', '>', -2.832748293876648),
        ('atr_14', '>', 17.538938522338867),
        ('dist_pdh_atr', '<=', -1.8648883700370789),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features, _empty_signals
        feats = build_features(intraday, daily)
        if feats.empty:
            return _empty_signals()
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            v = feats[col]
            if op == '<=':
                mask &= (v <= thr)
            else:
                mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty_signals()
        c = intraday['close'].loc[idx]
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values, 'target_hint': float('nan'),
        })

class MinedLong12:
    name = "MINED_LONG_12"
    side = 'LONG'
    expected_oos_mean = 12.867476851851851
    expected_oos_n = 432
    constraints = [
        ('dist_pdl_atr', '<=', 4.127802610397339),
        ('dist_pdl_atr', '>', 1.8947908282279968),
        ('atr_14', '<=', 28.860551834106445),
        ('dist_pdl_atr', '>', 3.105867624282837),
        ('range_pos_50', '>', 0.2635356932878494),
        ('atr_14', '>', 16.375834465026855),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features, _empty_signals
        feats = build_features(intraday, daily)
        if feats.empty:
            return _empty_signals()
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            v = feats[col]
            if op == '<=':
                mask &= (v <= thr)
            else:
                mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty_signals()
        c = intraday['close'].loc[idx]
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values, 'target_hint': float('nan'),
        })

class MinedShort13:
    name = "MINED_SHORT_13"
    side = 'SHORT'
    expected_oos_mean = -12.870909090909091
    expected_oos_n = 275
    constraints = [
        ('dist_pdl_atr', '>', 4.127802610397339),
        ('dist_pdh_atr', '>', -2.832748293876648),
        ('atr_14', '<=', 17.538938522338867),
        ('dist_vwap_atr', '>', 2.273065209388733),
        ('dist_pdh_atr', '>', -1.7093483209609985),
        ('dist_pdh_atr', '<=', -1.1795326471328735),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features, _empty_signals
        feats = build_features(intraday, daily)
        if feats.empty:
            return _empty_signals()
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            v = feats[col]
            if op == '<=':
                mask &= (v <= thr)
            else:
                mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty_signals()
        c = intraday['close'].loc[idx]
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values, 'target_hint': float('nan'),
        })

class MinedLong14:
    name = "MINED_LONG_14"
    side = 'LONG'
    expected_oos_mean = 14.637886597938145
    expected_oos_n = 194
    constraints = [
        ('dist_pdl_atr', '<=', 4.127802610397339),
        ('dist_pdl_atr', '>', 1.8947908282279968),
        ('atr_14', '<=', 28.860551834106445),
        ('dist_pdl_atr', '<=', 3.105867624282837),
        ('atr_14', '<=', 16.78220272064209),
        ('dist_pdl_atr', '<=', 2.7322089672088623),
        ('rsi_14', '>', 41.35470962524414),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features, _empty_signals
        feats = build_features(intraday, daily)
        if feats.empty:
            return _empty_signals()
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            v = feats[col]
            if op == '<=':
                mask &= (v <= thr)
            else:
                mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty_signals()
        c = intraday['close'].loc[idx]
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values, 'target_hint': float('nan'),
        })

class MinedLong15:
    name = "MINED_LONG_15"
    side = 'LONG'
    expected_oos_mean = 11.19059405940594
    expected_oos_n = 303
    constraints = [
        ('dist_pdl_atr', '<=', 4.127802610397339),
        ('dist_pdl_atr', '>', 1.8947908282279968),
        ('atr_14', '<=', 28.860551834106445),
        ('dist_pdl_atr', '<=', 3.105867624282837),
        ('atr_14', '>', 16.78220272064209),
        ('range_pos_50', '<=', 0.22936878353357315),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features, _empty_signals
        feats = build_features(intraday, daily)
        if feats.empty:
            return _empty_signals()
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            v = feats[col]
            if op == '<=':
                mask &= (v <= thr)
            else:
                mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty_signals()
        c = intraday['close'].loc[idx]
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values, 'target_hint': float('nan'),
        })

class MinedLong16:
    name = "MINED_LONG_16"
    side = 'LONG'
    expected_oos_mean = 12.629076086956522
    expected_oos_n = 184
    constraints = [
        ('dist_pdl_atr', '<=', 4.127802610397339),
        ('dist_pdl_atr', '>', 1.8947908282279968),
        ('atr_14', '<=', 28.860551834106445),
        ('dist_pdl_atr', '<=', 3.105867624282837),
        ('atr_14', '<=', 16.78220272064209),
        ('dist_pdl_atr', '>', 2.7322089672088623),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features, _empty_signals
        feats = build_features(intraday, daily)
        if feats.empty:
            return _empty_signals()
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            v = feats[col]
            if op == '<=':
                mask &= (v <= thr)
            else:
                mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty_signals()
        c = intraday['close'].loc[idx]
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values, 'target_hint': float('nan'),
        })

class MinedShort17:
    name = "MINED_SHORT_17"
    side = 'SHORT'
    expected_oos_mean = -8.759943181818182
    expected_oos_n = 352
    constraints = [
        ('dist_pdl_atr', '>', 4.127802610397339),
        ('dist_pdh_atr', '>', -2.832748293876648),
        ('atr_14', '<=', 17.538938522338867),
        ('dist_vwap_atr', '>', 2.273065209388733),
        ('dist_pdh_atr', '<=', -1.7093483209609985),
        ('rsi_14', '<=', 57.20286750793457),
        ('dist_vwap_atr', '>', 6.235148906707764),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features, _empty_signals
        feats = build_features(intraday, daily)
        if feats.empty:
            return _empty_signals()
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            v = feats[col]
            if op == '<=':
                mask &= (v <= thr)
            else:
                mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty_signals()
        c = intraday['close'].loc[idx]
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values, 'target_hint': float('nan'),
        })

class MinedLong18:
    name = "MINED_LONG_18"
    side = 'LONG'
    expected_oos_mean = 12.651234567901234
    expected_oos_n = 162
    constraints = [
        ('dist_pdl_atr', '<=', 4.127802610397339),
        ('dist_pdl_atr', '>', 1.8947908282279968),
        ('atr_14', '<=', 28.860551834106445),
        ('dist_pdl_atr', '<=', 3.105867624282837),
        ('atr_14', '<=', 16.78220272064209),
        ('dist_pdl_atr', '<=', 2.7322089672088623),
        ('rsi_14', '<=', 41.35470962524414),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features, _empty_signals
        feats = build_features(intraday, daily)
        if feats.empty:
            return _empty_signals()
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            v = feats[col]
            if op == '<=':
                mask &= (v <= thr)
            else:
                mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty_signals()
        c = intraday['close'].loc[idx]
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values, 'target_hint': float('nan'),
        })

class MinedLong19:
    name = "MINED_LONG_19"
    side = 'LONG'
    expected_oos_mean = 9.752808988764045
    expected_oos_n = 267
    constraints = [
        ('dist_pdl_atr', '>', 4.127802610397339),
        ('dist_pdh_atr', '<=', -2.832748293876648),
        ('atr_14', '<=', 57.1982307434082),
        ('dist_vwap_atr', '>', -2.820648193359375),
        ('dist_pdh_atr', '<=', -7.601422309875488),
        ('dist_pdh_atr', '<=', -41.683570861816406),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features, _empty_signals
        feats = build_features(intraday, daily)
        if feats.empty:
            return _empty_signals()
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            v = feats[col]
            if op == '<=':
                mask &= (v <= thr)
            else:
                mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty_signals()
        c = intraday['close'].loc[idx]
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'LONG',
            'entry_px': c.values, 'target_hint': float('nan'),
        })

class MinedShort20:
    name = "MINED_SHORT_20"
    side = 'SHORT'
    expected_oos_mean = -9.430232558139535
    expected_oos_n = 172
    constraints = [
        ('dist_pdl_atr', '>', 4.127802610397339),
        ('dist_pdh_atr', '>', -2.832748293876648),
        ('atr_14', '<=', 17.538938522338867),
        ('dist_vwap_atr', '>', 2.273065209388733),
        ('dist_pdh_atr', '<=', -1.7093483209609985),
        ('rsi_14', '>', 57.20286750793457),
        ('dist_pdh_atr', '>', -2.1814008951187134),
    ]

    def generate(self, intraday, daily):
        from research.pattern_miner import build_features, _empty_signals
        feats = build_features(intraday, daily)
        if feats.empty:
            return _empty_signals()
        mask = pd.Series(True, index=feats.index)
        for col, op, thr in self.constraints:
            v = feats[col]
            if op == '<=':
                mask &= (v <= thr)
            else:
                mask &= (v > thr)
        idx = intraday.index[mask.fillna(False)]
        if len(idx) == 0:
            return _empty_signals()
        c = intraday['close'].loc[idx]
        return pd.DataFrame({
            'signal_time': idx, 'signal_name': self.name,
            'side': 'SHORT',
            'entry_px': c.values, 'target_hint': float('nan'),
        })

ALL_MINED_SIGNALS = [
    MinedLong01(),
    MinedShort02(),
    MinedShort03(),
    MinedShort04(),
    MinedLong05(),
    MinedLong06(),
    MinedShort07(),
    MinedShort08(),
    MinedShort09(),
    MinedLong10(),
    MinedShort11(),
    MinedLong12(),
    MinedShort13(),
    MinedLong14(),
    MinedLong15(),
    MinedLong16(),
    MinedShort17(),
    MinedLong18(),
    MinedLong19(),
    MinedShort20(),
]