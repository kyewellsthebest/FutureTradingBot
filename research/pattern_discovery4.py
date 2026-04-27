"""
Pattern Discovery v4 — ULTRA-NOVEL ideas that exploit micro-structure events
most traders wouldn't think to look at. Focus: rare, time-anchored, and
structure-anchored patterns that tend to survive permutation tests.

Key insight: permutation tests shuffle log returns but preserve distribution.
A strategy survives if it exploits TIMING and STRUCTURE that can't be randomly
reproduced. So patterns anchored to:
  - Session open/close events (gap opens, session highs/lows)
  - Prior-day key levels (PDH/PDL recovery)
  - Specific time-of-day (midday low, power hour)
  - Sequential bar behavior (3-consecutive-higher-lows)
...survive better than purely statistical patterns (VWAP, RSI extremes).

Novel LONG-focused candidates:
  1.  Gap Fill Long (mirror of validated GAP_FILL_SHORT, with relaxed R:R)
  2.  Failed Breakdown Reversal Long (breaks PDL, closes back above within 3 bars)
  3.  Three-Higher-Lows Breakout Long (3 consecutive HL's in a session, then break HOD)
  4.  Liquidity Pocket Long (3+ low-vol bars then volume expansion up)
  5.  Inside-Inside-Break Long (2 consecutive inside bars then break high with vol)
  6.  Midday Low Bounce Long (LOD made 11:00-13:00 EST, then higher-low, then rally)
  7.  Overnight Drop Recovery Long (18:00-02:00 EST down move, reversal at London)
  8.  Session VWAP Bounce Count Long (3rd touch of VWAP from above = bounce)
  9.  Late-Hour Inventory Unwind Long (last 30min if < VWAP, buyer covering)
 10.  Bar-Count-Since-Low Long (20+ bars since session low with higher closes)
 11.  Asian Box Lower Quartile Entry (London open in lower 25% of Asian range)
 12.  Triple Doji Breakout Long (3 tiny-body bars, then explosion up)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from research.data_loader import download_nq
from research.indicators import session_vwap, volume_ratio

NY = "America/New_York"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ny_time(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    return idx.tz_convert(NY)


def _fwd(close: pd.Series, n: int) -> pd.Series:
    """n-bar forward return in points, signed."""
    return close.shift(-n) - close


def _build(intraday: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """Attach all derived columns the patterns need."""
    df = intraday.copy()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    ny = _ny_time(df.index)
    df["ny_date"] = ny.date
    df["ny_min"] = ny.hour * 60 + ny.minute
    df["hour"] = ny.hour
    df["minute"] = ny.minute

    # Prior-day close attached by NY date
    d = daily.copy()
    if d.index.tz is None:
        d.index = d.index.tz_localize("UTC")
    d_ny = _ny_time(d.index).normalize()
    daily_shift = pd.Series(d["close"].values, index=d_ny.date).shift(1)
    df["prev_close"] = pd.Series(df["ny_date"]).map(daily_shift).to_numpy()

    df["vwap"] = session_vwap(df)
    df["vol_ratio"] = volume_ratio(df["volume"], 20)
    # ATR proxy: rolling true range mean
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(),
                    (df["low"] - pc).abs()], axis=1).max(axis=1)
    df["atr14"] = tr.rolling(14, min_periods=14).mean()

    df["fwd10"] = _fwd(df["close"], 10)
    df["fwd20"] = _fwd(df["close"], 20)
    df["fwd30"] = _fwd(df["close"], 30)
    return df


def _report(name: str, side: str, mask: pd.Series, df: pd.DataFrame,
            results: list[dict]) -> None:
    """Compute EV / win-rate over fwd10/20/30 and append to `results`."""
    if mask is None or not mask.any():
        print(f"  {name}: n=0 (too few samples)")
        return
    n = int(mask.sum())
    if n < 5:
        print(f"  {name}: n={n} (too few)")
        return
    fwd20 = df.loc[mask, "fwd20"].dropna()
    if fwd20.empty:
        print(f"  {name}: n={n} (no forward data)")
        return
    if side == "SHORT":
        fwd20 = -fwd20
    ev = float(fwd20.mean())
    wr = float((fwd20 > 0).mean() * 100.0)
    print(f"  {name}: n={n:>4d}  ev={ev:+7.2f}  wr={wr:5.1f}%  fwd20=({n})")
    results.append({"name": name, "side": side, "n": n, "ev": ev, "wr": wr})


# ---------------------------------------------------------------------------
# 12 pattern detectors
# ---------------------------------------------------------------------------

def _p1_gap_fill_long(df: pd.DataFrame) -> pd.Series:
    """1. Gap-down >= 20 pts that fills upward."""
    is_open = (df["hour"] == 9) & (df["minute"] == 30)
    gap = df["open"] - df["prev_close"]
    return is_open & (gap <= -20)


def _p2_failed_breakdown_long(df: pd.DataFrame, n_bars: int = 3) -> pd.Series:
    """2. Bar low < PDL but closes back above within `n_bars` bars."""
    daily_pdl = df.groupby(pd.Index(df["ny_date"]).rename("d"))["low"].transform(
        lambda x: x.shift(1).min()
    )
    broke_below = df["low"] < daily_pdl
    above_close = df["close"] > daily_pdl
    failed_bdown = broke_below & above_close
    # Recovered within n_bars
    recovered = failed_bdown & failed_bdown.rolling(n_bars, min_periods=1).max().astype(bool)
    return recovered


def _p3_three_higher_lows_breakout_long(df: pd.DataFrame) -> pd.Series:
    """3. Three consecutive higher lows then breaks session high."""
    hl = (df["low"] > df["low"].shift(1)) & (df["low"].shift(1) > df["low"].shift(2))
    sess_high = df.groupby(pd.Index(df["ny_date"]).rename("d"))["high"].cummax()
    breakout = df["close"] > sess_high.shift(1)
    return hl.shift(1).fillna(False) & breakout


def _p4_liq_pocket_break_long(df: pd.DataFrame) -> pd.Series:
    """4. 3+ low-volume bars followed by volume expansion up."""
    low_vol = df["vol_ratio"] < 0.7
    pocket_3 = low_vol & low_vol.shift(1) & low_vol.shift(2)
    breakout = (df["vol_ratio"] >= 1.5) & (df["close"] > df["open"])
    return pocket_3.shift(1).fillna(False) & breakout


def _p5_inside2_break_long(df: pd.DataFrame) -> pd.Series:
    """5. Two consecutive inside bars then break the outer high."""
    inside1 = (df["high"] < df["high"].shift(1)) & (df["low"] > df["low"].shift(1))
    inside2 = inside1 & inside1.shift(1)
    outer_high = df["high"].shift(2)
    breakout = df["close"] > outer_high
    return inside2.shift(1).fillna(False) & breakout & (df["vol_ratio"] >= 1.2)


def _p6_midday_low_bounce_long(df: pd.DataFrame) -> pd.Series:
    """6. Session low forms 11:00-13:00 EST, then a higher-low, then a rally."""
    midday = (df["ny_min"] >= 660) & (df["ny_min"] < 780)
    out = pd.Series(False, index=df.index)
    for d, sess in df.groupby(pd.Index(df["ny_date"]).rename("d"), sort=False):
        midday_part = sess[(sess["ny_min"] >= 660) & (sess["ny_min"] < 780)]
        if midday_part.empty:
            continue
        lod_min = midday_part["low"].idxmin()
        lod_price = midday_part.loc[lod_min, "low"]
        after = sess.loc[sess.index > lod_min]
        if after.empty:
            continue
        higher_low_mask = after["low"] > lod_price
        if not higher_low_mask.any():
            continue
        higher_low_ts = higher_low_mask.idxmax()
        after2 = after.loc[after.index > higher_low_ts]
        if after2.empty:
            continue
        hl_high = after.loc[higher_low_ts, "high"]
        rallies = after2.index[after2["close"] > hl_high]
        if len(rallies) > 0:
            out.loc[rallies[0]] = True
    return out


def _p7_overnight_drop_recover_long(df: pd.DataFrame) -> pd.Series:
    """7. Overnight 18:00-02:00 EST down move that reverses at London open (02:00)."""
    overnight = (df["ny_min"] >= 18 * 60) | (df["ny_min"] < 120)
    london = (df["ny_min"] >= 120) & (df["ny_min"] < 180)
    out = pd.Series(False, index=df.index)
    for d, sess in df.groupby(pd.Index(df["ny_date"]).rename("d"), sort=False):
        on = sess[(sess["ny_min"] >= 18 * 60) | (sess["ny_min"] < 120)]
        if on.empty or "atr14" not in sess:
            continue
        on_move = float(on["close"].iloc[-1] - on["close"].iloc[0])
        atr = float(sess["atr14"].dropna().iloc[-1]) if sess["atr14"].notna().any() else 0.0
        if on_move >= -1.0 * atr:
            continue
        london_part = sess[(sess["ny_min"] >= 120) & (sess["ny_min"] < 180)]
        if london_part.empty:
            continue
        bullish = london_part["close"] > london_part["open"]
        if bullish.any():
            out.loc[bullish.idxmax()] = True
    return out


def _p8_third_vwap_touch_long(df: pd.DataFrame) -> pd.Series:
    """8. Third touch of a rising session VWAP from above = bounce setup."""
    out = pd.Series(False, index=df.index)
    for d, sess in df.groupby(pd.Index(df["ny_date"]).rename("d"), sort=False):
        if "vwap" not in sess or sess["vwap"].isna().all():
            continue
        vwap_touch = (sess["low"] <= sess["vwap"]) & (sess["close"] > sess["vwap"])
        touches = sess.index[vwap_touch.fillna(False)]
        if len(touches) >= 3:
            third = touches[2]
            out.loc[third] = True
    return out


def _p9_bars_since_lod_long(df: pd.DataFrame, n_min: int = 20) -> pd.Series:
    """9. 20+ bars past the session low with successively higher closes."""
    out = pd.Series(False, index=df.index)
    for d, sess in df.groupby(pd.Index(df["ny_date"]).rename("d"), sort=False):
        if len(sess) < n_min + 1:
            continue
        lod_idx = int(np.argmin(sess["low"].to_numpy()))
        if lod_idx + n_min >= len(sess):
            continue
        closes = sess["close"].to_numpy()[lod_idx : lod_idx + n_min + 1]
        if all(closes[i] >= closes[i - 1] for i in range(1, len(closes))):
            out.iloc[lod_idx + n_min] = True
    return out


def _p10_asian_lowq_long(df: pd.DataFrame) -> pd.Series:
    """10. NY opens in the lowest 25% of the Asian-session range."""
    out = pd.Series(False, index=df.index)
    for d, sess in df.groupby(pd.Index(df["ny_date"]).rename("d"), sort=False):
        asian = sess[(sess["ny_min"] >= 20 * 60) | (sess["ny_min"] < 4 * 60)]
        if asian.empty:
            continue
        as_high = float(asian["high"].max())
        as_low = float(asian["low"].min())
        as_q1 = as_low + 0.25 * (as_high - as_low)
        ny_open = sess[(sess["hour"] == 9) & (sess["minute"] == 30)]
        if ny_open.empty:
            continue
        open_price = float(ny_open["open"].iloc[0])
        if open_price <= as_q1:
            out.loc[ny_open.index[0]] = True
    return out


def _p11_pdh_flip_support_long(df: pd.DataFrame) -> pd.Series:
    """11. Broke above PDH, retests PDH from above, bounces."""
    daily_pdh = df.groupby(pd.Index(df["ny_date"]).rename("d"))["high"].transform(
        lambda x: x.shift(1).max()
    )
    broke_above = df["close"] > daily_pdh
    broke_above_in_10bars = broke_above.rolling(10, min_periods=1).max().astype(bool)
    retest = (df["low"] <= daily_pdh) & (df["close"] > daily_pdh)
    return broke_above_in_10bars.shift(1).fillna(False) & retest


def _p12_triple_doji_break_long(df: pd.DataFrame) -> pd.Series:
    """12. Three tiny-body bars then explosion up."""
    body = (df["close"] - df["open"]).abs()
    bar_range = (df["high"] - df["low"]).replace(0.0, np.nan)
    tiny_body = (body / bar_range) < 0.2
    three_doji = tiny_body & tiny_body.shift(1) & tiny_body.shift(2)
    expansion_up = (df["close"] > df["open"]) & (df["vol_ratio"] >= 1.5) & ((body / bar_range) > 0.6)
    return three_doji.shift(1).fillna(False) & expansion_up


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 80)
    print("Pattern Discovery v4 — Novel LONG candidates")
    print("=" * 80)
    intraday = download_nq("5min")
    daily = download_nq("daily")
    df = _build(intraday, daily)
    print(f"Total bars: {len(df):,}")
    print()

    results: list[dict] = []

    print("1. GAP FILL LONG  (mirror of GAP_FILL_SHORT; gap-down >= 20 pts fills upward)")
    _report("GAPFILL_LONG", "LONG", _p1_gap_fill_long(df), df, results)
    print()

    print("2. FAILED BREAKDOWN LONG  (low < PDL, but closes back above PDL within N bars)")
    _report("FAILED_BREAKDOWN_LONG_3BAR", "LONG", _p2_failed_breakdown_long(df, 3), df, results)
    print()

    print("3. THREE HIGHER LOWS BREAKOUT LONG  (3 consec HL's in session, then break HOD)")
    _report("3HL_BREAKOUT_LONG", "LONG", _p3_three_higher_lows_breakout_long(df), df, results)
    print()

    print("4. LIQUIDITY POCKET BREAKOUT LONG  (3+ low-vol bars, then volume expansion up)")
    _report("LIQ_POCKET_BREAK_LONG", "LONG", _p4_liq_pocket_break_long(df), df, results)
    print()

    print("5. INSIDE-INSIDE-BREAK LONG  (2 consec inside bars then break outer high)")
    _report("INSIDE2_BREAK_LONG", "LONG", _p5_inside2_break_long(df), df, results)
    print()

    print("6. MIDDAY LOW BOUNCE LONG  (LOD made 11:00-13:00 EST, higher-low, then rally)")
    _report("MIDDAY_LOW_BOUNCE_LONG", "LONG", _p6_midday_low_bounce_long(df), df, results)
    print()

    print("7. OVERNIGHT DROP RECOVERY LONG  (18:00-02:00 EST down X pts, reverses at London)")
    _report("OVERNIGHT_DROP_RECOVER_LONG", "LONG", _p7_overnight_drop_recover_long(df), df, results)
    print()

    print("8. THIRD TOUCH VWAP LONG  (3rd touch of rising VWAP from above)")
    _report("THIRD_VWAP_TOUCH_LONG", "LONG", _p8_third_vwap_touch_long(df), df, results)
    print()

    print("9. BAR-COUNT-SINCE-LOW LONG  (20+ bars past session LOD with higher closes)")
    _report("BARS_SINCE_LOD_LONG", "LONG", _p9_bars_since_lod_long(df), df, results)
    print()

    print("10. ASIAN LOWER QUARTILE OPEN LONG  (NY opens in bottom 25% of Asian range)")
    _report("ASIAN_LOWQ_LONG", "LONG", _p10_asian_lowq_long(df), df, results)
    print()

    print("11. PDH FLIP SUPPORT LONG  (broke above PDH, retests PDH from above, bounces)")
    _report("PDH_FLIP_SUPPORT_LONG", "LONG", _p11_pdh_flip_support_long(df), df, results)
    print()

    print("12. TRIPLE DOJI BREAKOUT LONG  (3 tiny-body bars, then explosion up)")
    _report("TRIPLE_DOJI_BREAK_LONG", "LONG", _p12_triple_doji_break_long(df), df, results)
    print()

    # Rank by EV * sqrt(n) — favours both edge and sample size.
    ranked = sorted(results, key=lambda r: r["ev"] * np.sqrt(r["n"]), reverse=True)
    print("=" * 80)
    print("RANKED NOVEL LONG CANDIDATES (sorted by EV * sqrt(n))")
    print("=" * 80)
    print(f"{'Name':<32s} {'Side':>6s} {'n':>6s} {'ev':>8s} {'wr':>7s}  ")
    print("-" * 80)
    for r in ranked:
        print(f"{r['name']:<32s} {r['side']:>6s} {r['n']:>6d} {r['ev']:+8.2f} {r['wr']:>6.1f}%")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
