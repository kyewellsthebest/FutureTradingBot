"""Test "hold the full hour" strategies: enter at hour 17:00 UTC, exit
at 18:00 UTC at market (close).

No stop, no target — just ride the hour-17 bias of +4.72 pts/hr.
Same execution model: market entry at ASK, market exit at BID at end
of hour.

Variants:
  - Single shot at hour 17:00 LONG, exit at 18:00 (no stop)
  - Multi-hour: 22:00 LONG -> 23:00, 17:00 LONG -> 18:00 etc
  - With wide stop / wide target: 30pt stop, 30pt target, hour close fallback
"""
from __future__ import annotations
import sys
import copy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional
from pathlib import Path
sys.path.insert(0, "/home/user/HFTBot")

import numpy as np
import pandas as pd

from research.alternative_strategies import (
    TICK_CSV, COMMISSION_RT, MNQ_PER_PT, N_MNQ,
    STOP_SLIP_PTS, MAX_WAIT_SECS, MAX_HOLD_SECS,
    US_PER_SEC, US_PER_MIN, PROGRESS_TICKS, HISTORY_BARS,
    AltSetup, BarHistory, iter_tick_chunks,
    get_60d_offset, summarize,
)


@dataclass
class HoldCfg:
    name: str
    entry_hour: int
    entry_minute: int = 0
    side: str = "LONG"
    hold_minutes: int = 60        # exit after this many minutes
    stop_pts: Optional[float] = None  # None = no stop
    target_pts: Optional[float] = None  # None = no target


@dataclass
class HoldState:
    cfg: HoldCfg
    active: Optional[dict] = None
    completed: list = field(default_factory=list)
    last_entry_day: Optional[str] = None  # avoid multi-entry per day


def _scan_exit_or_timeout(at, bid, ask, ts, start, end):
    """Scan [start, end) for stop/target hit or time exit at last_ts.
    Returns (idx, exit_px, reason). end is the bar where we MUST exit.
    """
    side = at["side"]
    sp = at["stop_px"]
    tp = at["target_px"]
    entry_ts = at["entry_ts_us"]
    timeout_ts = at["timeout_ts_us"]
    # Stop / target detection
    if side == "LONG":
        if sp is not None:
            stop_arr = bid[start:end] <= sp
            stop_idx = (start + int(np.argmax(stop_arr))) if stop_arr.any() else None
        else:
            stop_idx = None
        if tp is not None:
            tgt_arr = bid[start:end] >= tp
            tgt_idx = (start + int(np.argmax(tgt_arr))) if tgt_arr.any() else None
        else:
            tgt_idx = None
    else:
        if sp is not None:
            stop_arr = ask[start:end] >= sp
            stop_idx = (start + int(np.argmax(stop_arr))) if stop_arr.any() else None
        else:
            stop_idx = None
        if tp is not None:
            tgt_arr = ask[start:end] <= tp
            tgt_idx = (start + int(np.argmax(tgt_arr))) if tgt_arr.any() else None
        else:
            tgt_idx = None
    # Timeout: find first idx where ts >= timeout_ts within [start, end)
    timeout_arr = ts[start:end] >= timeout_ts
    timeout_idx = (start + int(np.argmax(timeout_arr))) if timeout_arr.any() else None
    cands = []
    if stop_idx is not None: cands.append((stop_idx, "stop"))
    if tgt_idx is not None: cands.append((tgt_idx, "target"))
    if timeout_idx is not None: cands.append((timeout_idx, "timeout"))
    if not cands:
        return (None, None, None)
    cands.sort(key=lambda x: x[0])
    idx, reason = cands[0]
    if reason == "stop":
        exit_px = float(sp) - STOP_SLIP_PTS if side == "LONG" else float(sp) + STOP_SLIP_PTS
    elif reason == "target":
        exit_px = float(tp)
    else:
        # Timeout at MARKET (use bid for LONG exit, ask for SHORT exit, with slip)
        if side == "LONG":
            exit_px = float(bid[idx]) - 0.25  # small market slip
        else:
            exit_px = float(ask[idx]) + 0.25
    return (idx, exit_px, reason)


def run_hold(cfgs: list[HoldCfg], *, start_offset=0, end_after_ticks=None,
             label="HOLD"):
    import time
    states = {c.name: HoldState(cfg=c) for c in cfgs}
    cur_min = None
    cur_o = cur_h = cur_l = cur_c = float("nan")
    n_ticks = 0
    n_bars = 0
    t0 = time.time()
    last_progress = t0
    ticks_since = 0
    print(f"[{label}] starting {len(cfgs)} hold strategies", flush=True)
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
            # Active trade exit scan in [seg_start, new_min_idx) for each state
            for ss in states.values():
                if ss.active is None:
                    continue
                idx, exit_px, reason = _scan_exit_or_timeout(
                    ss.active, bid, ask, ts_us, seg_start, new_min_idx)
                if idx is None:
                    continue
                # Record
                at = ss.active
                if at["side"] == "LONG":
                    pnl_pts = exit_px - at["entry_px"]
                else:
                    pnl_pts = at["entry_px"] - exit_px
                pnl_usd = pnl_pts * MNQ_PER_PT * N_MNQ - COMMISSION_RT
                exit_ts = datetime.fromtimestamp(ts_us[idx] / 1e6, tz=timezone.utc)
                ss.completed.append({
                    "entry_ts": at["entry_ts"], "exit_ts": exit_ts,
                    "side": at["side"], "entry_px": at["entry_px"],
                    "exit_px": exit_px,
                    "exit_reason": reason,
                    "pnl_pts": pnl_pts, "pnl_usd": pnl_usd,
                })
                ss.active = None
            # Accumulate prior bar
            if seg_start < new_min_idx:
                slm = mid[seg_start:new_min_idx]
                if cur_min is None:
                    cur_min = int(minutes[seg_start])
                    cur_o = float(slm[0]); cur_h = float(slm.max())
                    cur_l = float(slm.min()); cur_c = float(slm[-1])
                else:
                    cur_h = max(cur_h, float(slm.max()))
                    cur_l = min(cur_l, float(slm.min()))
                    cur_c = float(slm[-1])
            # Roll bar / entry detection at new minute boundary
            new_min = int(minutes[new_min_idx])
            new_dt = datetime.fromtimestamp(new_min * US_PER_MIN / 1e6, tz=timezone.utc)
            for ss in states.values():
                cfg = ss.cfg
                if ss.active is not None:
                    continue
                if new_dt.hour != cfg.entry_hour or new_dt.minute != cfg.entry_minute:
                    continue
                day = new_dt.date().isoformat()
                if ss.last_entry_day == day:
                    continue
                # Enter at this tick (first tick of new minute)
                idx = new_min_idx
                entry_px = float(ask[idx]) if cfg.side == "LONG" else float(bid[idx])
                ss.last_entry_day = day
                # Build stop/target
                if cfg.stop_pts is not None:
                    sp = entry_px - cfg.stop_pts if cfg.side == "LONG" else entry_px + cfg.stop_pts
                else:
                    sp = None
                if cfg.target_pts is not None:
                    tp = entry_px + cfg.target_pts if cfg.side == "LONG" else entry_px - cfg.target_pts
                else:
                    tp = None
                timeout_ts = ts_us[idx] + cfg.hold_minutes * 60 * US_PER_SEC
                ss.active = {
                    "entry_ts": new_dt,
                    "entry_ts_us": int(ts_us[idx]),
                    "side": cfg.side,
                    "entry_px": entry_px,
                    "stop_px": sp,
                    "target_px": tp,
                    "timeout_ts_us": int(timeout_ts),
                }
            # Roll bar accumulator
            cur_min = new_min
            cur_o = float(mid[new_min_idx])
            cur_h = cur_o; cur_l = cur_o; cur_c = cur_o
            seg_start = new_min_idx
            n_bars += 1
        # Tail: process remaining segment for exits
        for ss in states.values():
            if ss.active is None:
                continue
            idx, exit_px, reason = _scan_exit_or_timeout(
                ss.active, bid, ask, ts_us, seg_start, chunk_len)
            if idx is None:
                continue
            at = ss.active
            if at["side"] == "LONG":
                pnl_pts = exit_px - at["entry_px"]
            else:
                pnl_pts = at["entry_px"] - exit_px
            pnl_usd = pnl_pts * MNQ_PER_PT * N_MNQ - COMMISSION_RT
            exit_ts = datetime.fromtimestamp(ts_us[idx] / 1e6, tz=timezone.utc)
            ss.completed.append({
                "entry_ts": at["entry_ts"], "exit_ts": exit_ts,
                "side": at["side"], "entry_px": at["entry_px"],
                "exit_px": exit_px, "exit_reason": reason,
                "pnl_pts": pnl_pts, "pnl_usd": pnl_usd,
            })
            ss.active = None
        if seg_start < chunk_len:
            slm = mid[seg_start:chunk_len]
            if cur_min is None:
                cur_min = int(minutes[seg_start])
                cur_o = float(slm[0]); cur_h = float(slm.max())
                cur_l = float(slm.min()); cur_c = float(slm[-1])
            else:
                cur_h = max(cur_h, float(slm.max()))
                cur_l = min(cur_l, float(slm.min()))
                cur_c = float(slm[-1])
        n_ticks += chunk_len
        ticks_since += chunk_len
        if ticks_since >= PROGRESS_TICKS:
            now = time.time()
            rate = ticks_since / max(0.001, now - last_progress)
            last_progress = now
            ticks_since = 0
            tc = {k: len(s.completed) for k, s in states.items()}
            best = max(tc.items(), key=lambda kv: kv[1])
            print(f"  [{label}] {n_ticks/1e6:.1f}M ticks "
                  f"rate={rate/1e6:.2f}M/s best={best[0]}({best[1]} tr) "
                  f"elapsed={now-t0:.0f}s", flush=True)
        if end_after_ticks is not None and n_ticks >= end_after_ticks:
            break
    print(f"[{label}] done. elapsed={time.time()-t0:.0f}s", flush=True)
    return states


def build_cfgs():
    out = []
    # H17 LONG, hold 60 min, no stop
    out.append(HoldCfg("H17_HOLD60_NOSTOP", 17, 0, "LONG", 60, None, None))
    # H17 LONG, hold 60 min, 20pt stop, no target
    out.append(HoldCfg("H17_HOLD60_STOP20", 17, 0, "LONG", 60, 20.0, None))
    out.append(HoldCfg("H17_HOLD60_STOP30", 17, 0, "LONG", 60, 30.0, None))
    out.append(HoldCfg("H17_HOLD60_STOP50", 17, 0, "LONG", 60, 50.0, None))
    # H17 LONG, hold 30 min, no stop
    out.append(HoldCfg("H17_HOLD30_NOSTOP", 17, 0, "LONG", 30, None, None))
    # H17 LONG, hold 120 min, no stop (capture more of the bias?)
    out.append(HoldCfg("H17_HOLD120_NOSTOP", 17, 0, "LONG", 120, None, None))
    # H17 LONG, hold 60 min, 30pt stop AND 30pt target
    out.append(HoldCfg("H17_HOLD60_S30_T30", 17, 0, "LONG", 60, 30.0, 30.0))
    out.append(HoldCfg("H17_HOLD60_S20_T20", 17, 0, "LONG", 60, 20.0, 20.0))
    out.append(HoldCfg("H17_HOLD60_S40_T40", 17, 0, "LONG", 60, 40.0, 40.0))
    # H22 LONG, hold 60, no stop
    out.append(HoldCfg("H22_HOLD60_NOSTOP", 22, 0, "LONG", 60, None, None))
    out.append(HoldCfg("H22_HOLD60_STOP30", 22, 0, "LONG", 60, 30.0, None))
    out.append(HoldCfg("H22_HOLD60_S30_T30", 22, 0, "LONG", 60, 30.0, 30.0))
    # H19 LONG, hold 60, no stop
    out.append(HoldCfg("H19_HOLD60_NOSTOP", 19, 0, "LONG", 60, None, None))
    out.append(HoldCfg("H19_HOLD60_STOP30", 19, 0, "LONG", 60, 30.0, None))
    # H07 LONG (Europe open?), hold 60
    out.append(HoldCfg("H07_HOLD60_NOSTOP", 7, 0, "LONG", 60, None, None))
    # H06 LONG, hold 60
    out.append(HoldCfg("H06_HOLD60_NOSTOP", 6, 0, "LONG", 60, None, None))
    # H14 SHORT (NY pre-open), hold 60, no stop
    out.append(HoldCfg("H14_HOLD60_SHORT", 14, 0, "SHORT", 60, None, None))
    out.append(HoldCfg("H15_HOLD60_SHORT", 15, 0, "SHORT", 60, None, None))
    out.append(HoldCfg("H18_HOLD60_SHORT", 18, 0, "SHORT", 60, None, None))
    out.append(HoldCfg("H20_HOLD60_SHORT", 20, 0, "SHORT", 60, None, None))
    # Multi-position daily portfolio: combine biases
    # We can't trade simultaneously (one position), but listing here.
    return out


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--out-dir", default="/home/user/HFTBot/research")
    args = parser.parse_args()
    cfgs = build_cfgs()
    offset = 0 if args.full else get_60d_offset()
    label = "FULL-HOLD" if args.full else "60D-HOLD"
    states = run_hold(cfgs, start_offset=offset, label=label)
    rows = []
    for name, ss in states.items():
        trades = ss.completed
        if not trades:
            rows.append({"name": name, "trades": 0, "wr": 0, "pnl": 0,
                         "per_day": 0, "per_trade": 0, "trades_per_day": 0,
                         "max_dd": 0, "worst_day": 0, "best_day": 0,
                         "n_days": 0, "sharpe": 0})
            continue
        df = pd.DataFrame(trades)
        df["day"] = pd.to_datetime(df["exit_ts"]).dt.date
        daily = df.groupby("day")["pnl_usd"].sum()
        pnl = float(df["pnl_usd"].sum())
        wins = int((df["pnl_usd"] > 0).sum())
        n = len(df)
        n_days = len(daily)
        eq = df["pnl_usd"].cumsum().to_numpy()
        peak = np.maximum.accumulate(eq)
        dd = (eq - peak).min()
        sharpe = (daily.mean() / daily.std()) if (len(daily) > 1 and daily.std() > 0) else 0.0
        rows.append({
            "name": name, "trades": n, "wr": wins/n, "pnl": pnl,
            "per_day": pnl/max(1, n_days), "per_trade": pnl/max(1, n),
            "trades_per_day": n/max(1, n_days),
            "max_dd": float(dd), "worst_day": float(daily.min()),
            "best_day": float(daily.max()), "n_days": n_days,
            "sharpe": float(sharpe),
        })
    df = pd.DataFrame(rows).sort_values("pnl", ascending=False)
    suffix = "_full" if args.full else "_60d"
    df.to_csv(Path(args.out_dir) / f"hold_summary{suffix}.csv", index=False)
    print("\nResults:")
    print(df.to_string())


if __name__ == "__main__":
    main()
