"""Phase 2: combination & regime tests for alternative strategies.

Loads the top N strategies from alt_summary_60d.csv and re-runs them
with various FILTERS to find combinations that turn a marginal loser
into a winner:

  - Time-of-day partitions: NY session, lunch skip, open skip
  - HTF trend agreement (only LONG when HTF UP)
  - ATR floor / ceiling
  - Min/max bar volume (proxy for liquidity)

Combinations tried:
  STRAT  + HTF_AGREE  + NY  + ATR_min
  STRAT  + HTF_AGREE  + skip_open + skip_close
  ... and 1:1 stop/target variant with same filters.

The same execution model is reused from research.alternative_strategies.

USAGE:
  python -m research.alt_strategies_combinations
  python -m research.alt_strategies_combinations --top 8 --full
"""
from __future__ import annotations
import argparse
import copy
import math
import os
import sys
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/HFTBot")

# Reuse all primitives
from research.alternative_strategies import (  # noqa: E402
    TICK_CSV, COMMISSION_RT, MNQ_PER_PT, N_MNQ, STOP_SLIP_PTS,
    MAX_WAIT_SECS, MAX_HOLD_SECS, MIN_TARGET_HOLD_SECONDS,
    HISTORY_BARS, PROGRESS_TICKS, US_PER_SEC, US_PER_MIN,
    AltSetup, BarHistory, iter_tick_chunks, _ema, _atr, _rsi, _expires,
    _check_exit_vec, _record_exit,
    StratState, StratConfig, get_60d_offset,
    build_catalog, summarize, write_report,
    _on_closed_bar as base_on_closed_bar,
    _check_trigger,
)


# ============================================================================
# Filtered StratConfig — extends with HTF, ATR filter etc
# ============================================================================
@dataclass
class FStratConfig(StratConfig):
    htf_agree: bool = False        # only take signals matching HTF trend
    htf_k: int = 30
    atr_min: Optional[float] = None
    atr_max: Optional[float] = None
    avoid_lunch: bool = False      # block 16:00-17:00 UTC
    skip_close: bool = False
    hour_in: Optional[set] = None  # only trade these UTC hours


def _htf_trend(arrs, k=30):
    """Fractal-pivot HTF trend over the bar history."""
    h = arrs["h"]; l = arrs["l"]
    n = len(h)
    if n < 2 * k + 1:
        return "FLAT"
    from numpy.lib.stride_tricks import sliding_window_view
    win_h = sliding_window_view(h, 2 * k + 1)
    win_l = sliding_window_view(l, 2 * k + 1)
    centers_h = h[k:n - k]
    centers_l = l[k:n - k]
    is_pivot_h = (centers_h == win_h.max(axis=1))
    is_pivot_l = (centers_l == win_l.min(axis=1))
    idx_h = np.where(is_pivot_h)[0]
    idx_l = np.where(is_pivot_l)[0]
    if len(idx_h) == 0 or len(idx_l) == 0:
        return "FLAT"
    last_h_src = int(idx_h[-1]) + k
    last_l_src = int(idx_l[-1]) + k
    last_h_val = float(h[last_h_src])
    last_l_val = float(l[last_l_src])
    if last_h_src > last_l_src and last_h_val > last_l_val:
        return "UP"
    if last_l_src > last_h_src and last_l_val < last_h_val:
        return "DOWN"
    return "FLAT"


def _on_closed_bar_filtered(ss, arrs, bh, now):
    cfg = ss.cfg
    new_setups = cfg.detector(arrs, bh, now, cfg.params)
    if not new_setups:
        return
    # ATR filter (shared across signals)
    if cfg.atr_min is not None or cfg.atr_max is not None:
        atr = _atr(arrs, 14)
        if not math.isnan(atr):
            if cfg.atr_min is not None and atr < cfg.atr_min:
                return
            if cfg.atr_max is not None and atr > cfg.atr_max:
                return
    # HTF filter
    htf = "FLAT"
    if cfg.htf_agree:
        htf = _htf_trend(arrs, cfg.htf_k)
        if htf == "FLAT":
            return
    # Hour filter
    if cfg.hour_in is not None:
        if now.hour not in cfg.hour_in:
            return
    if cfg.avoid_lunch and now.hour == 16:
        return
    if cfg.skip_close and now.hour == 20 and now.minute >= 30:
        return
    for s in new_setups:
        if cfg.invert:
            from research.alternative_strategies import _apply_invert
            s = _apply_invert(s)
        # HTF must match TRADE side
        if cfg.htf_agree:
            if htf == "UP" and s.side != "LONG":
                continue
            if htf == "DOWN" and s.side != "SHORT":
                continue
        # Dedupe
        key = (round(s.entry_px, 1), s.side, s.note[:8])
        if key in ss.recent_keys:
            continue
        already = False
        for ex in ss.pending:
            if ex.used:
                continue
            if (round(ex.entry_px, 1), ex.side, ex.note[:8]) == key:
                already = True
                break
        if already:
            continue
        ss.pending.append(s)
        ss.recent_keys.append(key)


# Monkeypatch _on_closed_bar in run() — easier: copy run() and use filtered version
def _time_blocked_fcfg(cfg: FStratConfig, ts: datetime) -> bool:
    hh, mm = ts.hour, ts.minute
    if cfg.ny_session_only:
        t = hh * 60 + mm
        if t < 13 * 60 + 30 or t >= 20 * 60:
            return True
    if cfg.skip_open and hh == 22 and mm < 30:
        return True
    if cfg.skip_close and hh == 20 and mm >= 30:
        return True
    if cfg.avoid_lunch and hh == 16:
        return True
    if cfg.hour_in is not None and hh not in cfg.hour_in:
        return True
    return False


def _open_trade_fcfg(ss, setup, fire_idx, bid, ask, ts_us):
    cfg = ss.cfg
    ts = datetime.fromtimestamp(ts_us[fire_idx] / 1e6, tz=timezone.utc)
    if _time_blocked_fcfg(cfg, ts):
        return False
    if ss.last_close_ts is not None:
        if (ts - ss.last_close_ts).total_seconds() < cfg.cooldown_secs:
            return False
    if setup.side == "LONG":
        entry_px = float(ask[fire_idx])
    else:
        entry_px = float(bid[fire_idx])
    ss.active_trade = {
        "entry_ts": ts,
        "entry_ts_us": int(ts_us[fire_idx]),
        "side": setup.side,
        "entry_px": entry_px,
        "stop_px": float(setup.stop_px),
        "target_px": float(setup.target_px),
        "note": setup.note,
    }
    setup.used = True
    return True


def _process_segment_fcfg(ss, bid, ask, mid, ts_us, seg_start, seg_end):
    cur = seg_start
    while cur < seg_end:
        if ss.active_trade is not None:
            idx, exit_px, reason = _check_exit_vec(
                ss.active_trade, bid[:seg_end], ask[:seg_end], ts_us[:seg_end], cur)
            if idx is None:
                return
            _record_exit(ss, int(ts_us[idx]), exit_px, reason)
            cur = idx + 1
            continue
        if not ss.pending:
            return
        now_us = ts_us[cur]
        ss.pending = [s for s in ss.pending
                       if (not s.used) and
                       (int(s.expires_at.timestamp() * US_PER_SEC) > now_us)]
        if not ss.pending:
            return
        earliest_idx = None
        earliest_setup = None
        for s in ss.pending:
            if s.used:
                continue
            fi = _check_trigger(s, mid[:seg_end], cur)
            if fi is not None and (earliest_idx is None or fi < earliest_idx):
                earliest_idx = fi
                earliest_setup = s
        if earliest_idx is None:
            return
        opened = _open_trade_fcfg(ss, earliest_setup, earliest_idx, bid, ask, ts_us)
        if not opened:
            earliest_setup.used = True
            cur = earliest_idx + 1
            continue
        cur = earliest_idx + 1


import time
def run_filtered(strats: list[FStratConfig], *, start_offset: int = 0,
                 end_after_ticks=None, label="FRUN"):
    print(f"\n[{label}] starting {len(strats)} filtered strats", flush=True)
    states = {s.name: StratState(cfg=s) for s in strats}
    bh = BarHistory(keep=HISTORY_BARS)
    cur_min = None
    cur_o = cur_h = cur_l = cur_c = float("nan")
    cur_v = 0
    n_ticks = 0
    n_bars = 0
    t0 = time.time()
    last_progress = t0
    ticks_since = 0
    states_list = list(states.values())
    for chunk in iter_tick_chunks(TICK_CSV, start_offset=start_offset):
        ts_us = chunk["ts"]
        bid = chunk["bid"]
        ask = chunk["ask"]
        mid = chunk["mid"]
        chunk_len = len(ts_us)
        minutes = ts_us // US_PER_MIN
        prev_min = cur_min if cur_min is not None else int(minutes[0])
        diff_idxs = np.where(np.diff(np.concatenate([[prev_min], minutes])) != 0)[0]
        seg_start = 0
        for new_min_idx in diff_idxs:
            if seg_start < new_min_idx:
                slm = mid[seg_start:new_min_idx]
                if cur_min is None:
                    cur_min = int(minutes[seg_start])
                    cur_o = float(slm[0]); cur_h = float(slm.max())
                    cur_l = float(slm.min()); cur_c = float(slm[-1])
                    cur_v = int(len(slm))
                else:
                    cur_h = max(cur_h, float(slm.max()))
                    cur_l = min(cur_l, float(slm.min()))
                    cur_c = float(slm[-1])
                    cur_v += int(len(slm))
            for ss in states_list:
                _process_segment_fcfg(ss, bid, ask, mid, ts_us, seg_start, new_min_idx)
            closed_ts_us = cur_min * US_PER_MIN
            bh.append(closed_ts_us, cur_o, cur_h, cur_l, cur_c, cur_v)
            n_bars += 1
            if len(bh.c) >= 5:
                arrs = bh.arrays()
                bar_close_ts = datetime.fromtimestamp(
                    (closed_ts_us + US_PER_MIN) / 1e6, tz=timezone.utc)
                for ss in states_list:
                    _on_closed_bar_filtered(ss, arrs, bh, bar_close_ts)
            cur_min = int(minutes[new_min_idx])
            cur_o = float(mid[new_min_idx]); cur_h = cur_o
            cur_l = cur_o; cur_c = cur_o; cur_v = 1
            seg_start = new_min_idx
        if seg_start < chunk_len:
            slm = mid[seg_start:chunk_len]
            if cur_min is None:
                cur_min = int(minutes[seg_start])
                cur_o = float(slm[0]); cur_h = float(slm.max())
                cur_l = float(slm.min()); cur_c = float(slm[-1])
                cur_v = int(len(slm))
            else:
                cur_h = max(cur_h, float(slm.max()))
                cur_l = min(cur_l, float(slm.min()))
                cur_c = float(slm[-1])
                cur_v += int(len(slm))
            for ss in states_list:
                _process_segment_fcfg(ss, bid, ask, mid, ts_us, seg_start, chunk_len)
        n_ticks += chunk_len
        ticks_since += chunk_len
        if ticks_since >= PROGRESS_TICKS:
            now = time.time()
            rate = ticks_since / max(0.001, now - last_progress)
            last_progress = now
            ticks_since = 0
            tc = {k: len(s.completed) for k, s in states.items()}
            best = max(tc.items(), key=lambda kv: kv[1])
            print(f"  [{label}] {n_ticks/1e6:.1f}M ticks  "
                  f"{n_bars:,} bars  rate={rate/1e6:.2f}M/s  "
                  f"best={best[0]}({best[1]} tr)  "
                  f"elapsed={now-t0:.0f}s", flush=True)
        if end_after_ticks is not None and n_ticks >= end_after_ticks:
            break
    print(f"[{label}] done. ticks={n_ticks:,} bars={n_bars:,} "
          f"elapsed={time.time()-t0:.0f}s", flush=True)
    return states


def build_combo_catalog(top_strats: list[StratConfig]) -> list[FStratConfig]:
    out = []
    for base in top_strats:
        bp = dict(base.params)
        # 1) HTF agree
        out.append(FStratConfig(
            name=f"{base.name}+HTF30",
            detector=base.detector, params=bp, invert=base.invert,
            htf_agree=True, htf_k=30,
        ))
        # 2) NY session
        out.append(FStratConfig(
            name=f"{base.name}+NY",
            detector=base.detector, params=bp, invert=base.invert,
            ny_session_only=True,
        ))
        # 3) HTF + NY
        out.append(FStratConfig(
            name=f"{base.name}+HTF30+NY",
            detector=base.detector, params=bp, invert=base.invert,
            htf_agree=True, htf_k=30, ny_session_only=True,
        ))
        # 4) ATR min 5
        out.append(FStratConfig(
            name=f"{base.name}+ATR5",
            detector=base.detector, params=bp, invert=base.invert,
            atr_min=5.0,
        ))
        # 5) ATR + HTF + NY (most restrictive)
        out.append(FStratConfig(
            name=f"{base.name}+HTF30+ATR5+NY",
            detector=base.detector, params=bp, invert=base.invert,
            htf_agree=True, htf_k=30, atr_min=5.0, ny_session_only=True,
        ))
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=6,
                        help="How many top base strategies to combine")
    parser.add_argument("--full", action="store_true",
                        help="Run on full data")
    parser.add_argument("--out-dir", default="/home/user/HFTBot/research")
    args = parser.parse_args()

    # Load summary CSV
    summary_path = Path(args.out_dir) / "alt_summary_60d.csv"
    if not summary_path.exists():
        print(f"ERROR: {summary_path} not found. Run alternative_strategies.py first")
        sys.exit(1)
    df = pd.read_csv(summary_path).sort_values("pnl", ascending=False)
    top_names = df.head(args.top)["name"].tolist()
    print(f"Top {args.top} base strategies: {top_names}")
    all_strats = build_catalog()
    top_strats = [s for s in all_strats if s.name in top_names]
    combos = build_combo_catalog(top_strats)
    print(f"Built {len(combos)} combo variants")

    out_dir = Path(args.out_dir)
    offset = get_60d_offset() if not args.full else 0
    label = "60D-COMBO" if not args.full else "FULL-COMBO"
    results = run_filtered(combos, start_offset=offset, label=label)
    rows = [summarize(s) for s in results.values()]
    df_out = pd.DataFrame(rows).sort_values("pnl", ascending=False)
    suffix = "_full" if args.full else "_60d"
    df_out.to_csv(out_dir / f"alt_combo_summary{suffix}.csv", index=False)
    print("\nTop 20 combos:")
    print(df_out.head(20).to_string())


if __name__ == "__main__":
    main()
