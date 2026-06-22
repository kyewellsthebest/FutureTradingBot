"""Test strategies that exploit the per-hour directional bias.

Key finding from research/hourly_bias_probe.py:
  - Hour 17 UTC (13:00 NY): +49.3 pts avg open-to-close, +2020 pts over 41 days
  - Hour 22 UTC (18:00 NY = CME open): +16.7 pts avg
  - Hour 19 UTC (15:00 NY): +15.2 pts avg
  - Hour 18 UTC: -19.5 pts avg (SHORT bias)
  - Hour 15 UTC: -19.7 pts avg (SHORT bias)

Hypothesis: enter LONG at start of hour 17, hold for the hour (or exit on
target/stop), close at hour end. Same for SHORT in hour 15/18.

Each strategy is just a SCHEDULED ENTRY at hour start. With direction
matching the bias.
"""
from __future__ import annotations
import sys
from datetime import datetime, timedelta, timezone
sys.path.insert(0, "/home/user/HFTBot")

from research.alternative_strategies import (
    AltSetup, StratConfig, _expires,
)


# ============================================================================
# Generic "enter at hour H minute M with side S" strategy factory
# ============================================================================
def make_hour_entry(side: str, hour: int, minute: int = 0,
                    stop_pts: float = 10.0, target_pts: float = 20.0):
    def detector(arrs, bh, now, p):
        if now.hour != hour or now.minute != minute:
            return []
        last_c = float(arrs["c"][-1])
        if side == "LONG":
            return [AltSetup(
                detected_at=now, side="LONG", entry_kind="immediate",
                entry_px=last_c, stop_px=last_c - stop_pts,
                target_px=last_c + target_pts,
                expires_at=_expires(now, 120),
                note=f"h{hour}m{minute}_L",
            )]
        else:
            return [AltSetup(
                detected_at=now, side="SHORT", entry_kind="immediate",
                entry_px=last_c, stop_px=last_c + stop_pts,
                target_px=last_c - target_pts,
                expires_at=_expires(now, 120),
                note=f"h{hour}m{minute}_S",
            )]
    return detector


# ============================================================================
# Multiple-entries: detector enters every N minutes during the hour
# ============================================================================
def make_minute_entries_during_hour(side: str, hour: int,
                                     cadence_min: int = 10,
                                     stop_pts: float = 10.0,
                                     target_pts: float = 20.0,
                                     start_minute: int = 0,
                                     end_minute: int = 60):
    def detector(arrs, bh, now, p):
        if now.hour != hour:
            return []
        if now.minute < start_minute or now.minute >= end_minute:
            return []
        if (now.minute - start_minute) % cadence_min != 0:
            return []
        last_c = float(arrs["c"][-1])
        if side == "LONG":
            return [AltSetup(
                detected_at=now, side="LONG", entry_kind="immediate",
                entry_px=last_c, stop_px=last_c - stop_pts,
                target_px=last_c + target_pts,
                expires_at=_expires(now, 60),
                note=f"hr{hour}m{cadence_min}_L",
            )]
        else:
            return [AltSetup(
                detected_at=now, side="SHORT", entry_kind="immediate",
                entry_px=last_c, stop_px=last_c + stop_pts,
                target_px=last_c - target_pts,
                expires_at=_expires(now, 60),
                note=f"hr{hour}m{cadence_min}_S",
            )]
    return detector


def build_hour_catalog() -> list[StratConfig]:
    V = []
    # Single shot at hour open
    biases = [
        ("LONG",  17),   # strongest LONG hour
        ("LONG",  22),
        ("LONG",  19),
        ("LONG",  0),
        ("LONG",  6),
        ("LONG",  14),
        ("LONG",  7),
        ("SHORT", 15),   # strongest SHORT hour
        ("SHORT", 18),
        ("SHORT", 5),
        ("SHORT", 2),
        ("SHORT", 20),
    ]
    for side, hr in biases:
        V.append(StratConfig(
            f"H{hr:02d}_{side}_SINGLE_10_20",
            make_hour_entry(side, hr, 0, 10.0, 20.0),
            {}, invert=False))
        # 10-min cadence within the hour
        V.append(StratConfig(
            f"H{hr:02d}_{side}_10min_10_20",
            make_minute_entries_during_hour(side, hr, 10, 10.0, 20.0),
            {}, invert=False))
        # 5-min cadence with smaller stop/target
        V.append(StratConfig(
            f"H{hr:02d}_{side}_5min_8_16",
            make_minute_entries_during_hour(side, hr, 5, 8.0, 16.0),
            {}, invert=False))
        # 5-min cadence 1:1 RR
        V.append(StratConfig(
            f"H{hr:02d}_{side}_5min_RR1",
            make_minute_entries_during_hour(side, hr, 5, 10.0, 10.0),
            {}, invert=False))
    # H17 special: try larger targets since avg move is 49pts
    V.append(StratConfig("H17_LONG_5min_15_45",
        make_minute_entries_during_hour("LONG", 17, 5, 15.0, 45.0), {}))
    V.append(StratConfig("H17_LONG_2min_10_20",
        make_minute_entries_during_hour("LONG", 17, 2, 10.0, 20.0), {}))
    V.append(StratConfig("H17_LONG_1min_10_20",
        make_minute_entries_during_hour("LONG", 17, 1, 10.0, 20.0), {}))
    V.append(StratConfig("H17_LONG_SINGLE_20_60",
        make_hour_entry("LONG", 17, 0, 20.0, 60.0), {}))
    V.append(StratConfig("H17_LONG_SINGLE_30_30",
        make_hour_entry("LONG", 17, 0, 30.0, 30.0), {}))
    V.append(StratConfig("H17_LONG_SINGLE_40_40",
        make_hour_entry("LONG", 17, 0, 40.0, 40.0), {}))
    # Two-hour LONG window 17-18 every 5 minutes
    def two_hour_long(arrs, bh, now, p):
        if not (now.hour == 17 or (now.hour == 18 and now.minute < 30)):
            return []
        if now.minute % 5 != 0:
            return []
        last_c = float(arrs["c"][-1])
        return [AltSetup(detected_at=now, side="LONG", entry_kind="immediate",
                          entry_px=last_c, stop_px=last_c - 10.0,
                          target_px=last_c + 20.0,
                          expires_at=_expires(now, 60),
                          note="h17_18_L")]
    V.append(StratConfig("H17_18_LONG_5min_10_20", two_hour_long, {}))
    # Multi-hour LONG: 17,19,22,0,6,7,14 (all positive bias hours) at 5min
    def multi_long(arrs, bh, now, p):
        if now.hour not in {17, 19, 22, 0, 6, 7, 14}:
            return []
        if now.minute % 5 != 0:
            return []
        last_c = float(arrs["c"][-1])
        return [AltSetup(detected_at=now, side="LONG", entry_kind="immediate",
                          entry_px=last_c, stop_px=last_c - 10.0,
                          target_px=last_c + 20.0,
                          expires_at=_expires(now, 60),
                          note="multi_L")]
    V.append(StratConfig("MULTI_POS_HOURS_LONG_5min_10_20", multi_long, {}))
    # Multi-hour SHORT: 15, 18, 5, 2
    def multi_short(arrs, bh, now, p):
        if now.hour not in {15, 18, 5, 2}:
            return []
        if now.minute % 5 != 0:
            return []
        last_c = float(arrs["c"][-1])
        return [AltSetup(detected_at=now, side="SHORT", entry_kind="immediate",
                          entry_px=last_c, stop_px=last_c + 10.0,
                          target_px=last_c - 20.0,
                          expires_at=_expires(now, 60),
                          note="multi_S")]
    V.append(StratConfig("MULTI_NEG_HOURS_SHORT_5min_10_20", multi_short, {}))
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
    strats = build_hour_catalog()
    print(f"Hour-of-day catalog: {len(strats)} strategies")
    offset = 0 if args.full else get_60d_offset()
    label = "FULL-HOUR" if args.full else "60D-HOUR"
    res = run(strats, start_offset=offset, label=label)
    rows = [summarize(s) for s in res.values()]
    df = pd.DataFrame(rows).sort_values("pnl", ascending=False)
    suffix = "_full" if args.full else "_60d"
    df.to_csv(Path(args.out_dir) / f"alt_hour_summary{suffix}.csv", index=False)
    print("Results:")
    print(df.to_string())
