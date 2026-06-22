"""Extras catalog: hour-of-day and always-long/short benchmark strategies.

These probe for a simple directional drift bias in the market. If
"always-long-once-per-hour" makes money, the market has a positive drift
that any winning strategy must align with.
"""
from __future__ import annotations
import sys
from datetime import datetime, timedelta, timezone
sys.path.insert(0, "/home/user/HFTBot")

from research.alternative_strategies import (
    AltSetup, BarHistory, StratConfig, _expires,
)


def _detect_hourly_long(arrs, bh, now, p):
    """Once per hour, at minute 0, emit a LONG signal."""
    if now.minute != 0:
        return []
    last_c = float(arrs["c"][-1])
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    return [AltSetup(
        detected_at=now, side="LONG", entry_kind="immediate",
        entry_px=last_c, stop_px=last_c - stop, target_px=last_c + target,
        expires_at=_expires(now, 120), note="hourly_long",
    )]


def _detect_hourly_short(arrs, bh, now, p):
    if now.minute != 0:
        return []
    last_c = float(arrs["c"][-1])
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    return [AltSetup(
        detected_at=now, side="SHORT", entry_kind="immediate",
        entry_px=last_c, stop_px=last_c + stop, target_px=last_c - target,
        expires_at=_expires(now, 120), note="hourly_short",
    )]


def _detect_market_open_long(arrs, bh, now, p):
    # At 13:30 UTC = NYSE open, go LONG once per day.
    if now.hour != 13 or now.minute != 30:
        return []
    last_c = float(arrs["c"][-1])
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    return [AltSetup(
        detected_at=now, side="LONG", entry_kind="immediate",
        entry_px=last_c, stop_px=last_c - stop, target_px=last_c + target,
        expires_at=_expires(now, 120), note="nyse_open_long",
    )]


def _detect_market_open_short(arrs, bh, now, p):
    if now.hour != 13 or now.minute != 30:
        return []
    last_c = float(arrs["c"][-1])
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    return [AltSetup(
        detected_at=now, side="SHORT", entry_kind="immediate",
        entry_px=last_c, stop_px=last_c + stop, target_px=last_c - target,
        expires_at=_expires(now, 120), note="nyse_open_short",
    )]


def _detect_5min_long(arrs, bh, now, p):
    """Every 5 minutes, fire a long. Stress test for cost-only baseline."""
    if now.minute % 5 != 0:
        return []
    last_c = float(arrs["c"][-1])
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    return [AltSetup(
        detected_at=now, side="LONG", entry_kind="immediate",
        entry_px=last_c, stop_px=last_c - stop, target_px=last_c + target,
        expires_at=_expires(now, 120), note="5min_long",
    )]


def _detect_5min_short(arrs, bh, now, p):
    if now.minute % 5 != 0:
        return []
    last_c = float(arrs["c"][-1])
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    return [AltSetup(
        detected_at=now, side="SHORT", entry_kind="immediate",
        entry_px=last_c, stop_px=last_c + stop, target_px=last_c - target,
        expires_at=_expires(now, 120), note="5min_short",
    )]


def _detect_5min_rr3(arrs, bh, now, p):
    """5-min cadence, 10pt stop, 30pt target. Probes whether 1:3 RR with low
    win rate beats costs."""
    if now.minute % 5 != 0:
        return []
    last_c = float(arrs["c"][-1])
    return [AltSetup(
        detected_at=now, side="LONG", entry_kind="immediate",
        entry_px=last_c, stop_px=last_c - 10.0, target_px=last_c + 30.0,
        expires_at=_expires(now, 120), note="5min_rr3_L",
    )]


def _detect_prev_bar_follow(arrs, bh, now, p):
    """Buy when prev bar was up, sell when prev bar was down."""
    if len(arrs["c"]) < 2:
        return []
    o = float(arrs["o"][-1]); c = float(arrs["c"][-1])
    last_c = c
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    if c > o:
        return [AltSetup(detected_at=now, side="LONG", entry_kind="immediate",
                        entry_px=last_c, stop_px=last_c - stop,
                        target_px=last_c + target,
                        expires_at=_expires(now, 120), note="prev_up")]
    if c < o:
        return [AltSetup(detected_at=now, side="SHORT", entry_kind="immediate",
                        entry_px=last_c, stop_px=last_c + stop,
                        target_px=last_c - target,
                        expires_at=_expires(now, 120), note="prev_dn")]
    return []


def _detect_prev_bar_fade(arrs, bh, now, p):
    """Fade prev bar — sell up, buy down."""
    if len(arrs["c"]) < 2:
        return []
    o = float(arrs["o"][-1]); c = float(arrs["c"][-1])
    last_c = c
    stop = p.get("stop_pts", 10.0)
    target = p.get("target_pts", 20.0)
    if c > o:
        return [AltSetup(detected_at=now, side="SHORT", entry_kind="immediate",
                        entry_px=last_c, stop_px=last_c + stop,
                        target_px=last_c - target,
                        expires_at=_expires(now, 120), note="prev_fade_dn")]
    if c < o:
        return [AltSetup(detected_at=now, side="LONG", entry_kind="immediate",
                        entry_px=last_c, stop_px=last_c - stop,
                        target_px=last_c + target,
                        expires_at=_expires(now, 120), note="prev_fade_up")]
    return []


def build_extras_catalog() -> list[StratConfig]:
    V = []
    V.append(StratConfig("Z_HOURLY_LONG_10_20", _detect_hourly_long,
                          {"stop_pts": 10.0, "target_pts": 20.0}))
    V.append(StratConfig("Z_HOURLY_SHORT_10_20", _detect_hourly_short,
                          {"stop_pts": 10.0, "target_pts": 20.0}))
    V.append(StratConfig("Z_HOURLY_LONG_RR1", _detect_hourly_long,
                          {"stop_pts": 10.0, "target_pts": 10.0}))
    V.append(StratConfig("Z_HOURLY_SHORT_RR1", _detect_hourly_short,
                          {"stop_pts": 10.0, "target_pts": 10.0}))
    V.append(StratConfig("Z_NYSE_OPEN_LONG", _detect_market_open_long,
                          {"stop_pts": 10.0, "target_pts": 20.0}))
    V.append(StratConfig("Z_NYSE_OPEN_SHORT", _detect_market_open_short,
                          {"stop_pts": 10.0, "target_pts": 20.0}))
    V.append(StratConfig("Z_5MIN_LONG_10_20", _detect_5min_long,
                          {"stop_pts": 10.0, "target_pts": 20.0}))
    V.append(StratConfig("Z_5MIN_SHORT_10_20", _detect_5min_short,
                          {"stop_pts": 10.0, "target_pts": 20.0}))
    V.append(StratConfig("Z_5MIN_RR3_LONG", _detect_5min_rr3, {}))
    V.append(StratConfig("Z_PREV_BAR_FOLLOW", _detect_prev_bar_follow,
                          {"stop_pts": 10.0, "target_pts": 20.0}))
    V.append(StratConfig("Z_PREV_BAR_FADE", _detect_prev_bar_fade,
                          {"stop_pts": 10.0, "target_pts": 20.0}))
    V.append(StratConfig("Z_PREV_BAR_FOLLOW_RR1", _detect_prev_bar_follow,
                          {"stop_pts": 10.0, "target_pts": 10.0}))
    V.append(StratConfig("Z_PREV_BAR_FADE_RR1", _detect_prev_bar_fade,
                          {"stop_pts": 10.0, "target_pts": 10.0}))
    return V


if __name__ == "__main__":
    import argparse
    from research.alternative_strategies import run, summarize, get_60d_offset
    import pandas as pd
    from pathlib import Path
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--out-dir", default="/home/user/HFTBot/research")
    args = parser.parse_args()
    strats = build_extras_catalog()
    print(f"Extras catalog: {len(strats)} strategies")
    offset = 0 if args.full else get_60d_offset()
    label = "FULL-EXTRAS" if args.full else "60D-EXTRAS"
    res = run(strats, start_offset=offset, label=label)
    rows = [summarize(s) for s in res.values()]
    df = pd.DataFrame(rows).sort_values("pnl", ascending=False)
    suffix = "_full" if args.full else "_60d"
    df.to_csv(Path(args.out_dir) / f"alt_extras_summary{suffix}.csv", index=False)
    print("Results:")
    print(df.to_string())
