"""
Local data loader for futures 1-minute files.

Files live under data/{nq,es,rty,vix}/<symbol>_<MMYY>.txt with format:
    YYYYMMDD HHMMSS;open;high;low;close;volume    (UTC timestamps)

Contract roll convention (futures): use a contract until ~9 calendar days before
its 3rd-Friday expiry, then roll to the next quarterly. VIX is a continuous
index (single file `vix.txt`), no rolling.

Public API:
    load_intraday_1min(symbol="nq")  -> 1-min OHLCV
    load_intraday_5min(symbol="nq")  -> 5-min OHLCV
    load_daily(symbol="nq")          -> daily OHLCV
    load_vix_1min()                  -> 1-min VIX index
    load_vix_5min()                  -> 5-min VIX index

Backwards compat: existing callers use the no-arg variants which default to NQ.
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path(os.environ.get("LOCAL_DATA_DIR", PROJECT_ROOT / "data"))


# -------------------------------------------------------------------- #
# Roll calendar
# -------------------------------------------------------------------- #
def _third_friday(year: int, month: int) -> date:
    d = date(year, month, 1)
    # weekday(): Mon=0..Sun=6; Friday=4
    offset = (4 - d.weekday()) % 7
    first_friday = d + timedelta(days=offset)
    return first_friday + timedelta(days=14)


def _roll_date(year: int, month: int) -> date:
    """Roll 9 calendar days before 3rd-Friday expiry."""
    return _third_friday(year, month) - timedelta(days=9)


def _parse_contract_filename(path: Path) -> tuple[int, int] | None:
    """
    Parse `nq_0624.txt` → (2024, 6). Returns None if filename doesn't match.
    Year encoding: YY in 00-50 → 2000+YY ; otherwise 1900+YY.
    """
    stem = path.stem.lower()
    if "_" not in stem:
        return None
    _, code = stem.split("_", 1)
    if len(code) != 4 or not code.isdigit():
        return None
    mm = int(code[:2])
    yy = int(code[2:])
    year = 2000 + yy if yy <= 50 else 1900 + yy
    return year, mm


def _build_contracts(asset_dir: Path) -> list[tuple[Path, date, date]]:
    """
    Discover all contract files in `asset_dir` and compute roll dates.
    Returns sorted list of (path, expiry_date, roll_date).
    The last contract uses its expiry as the cap (instead of next contract roll).
    """
    rows: list[tuple[Path, date, date]] = []
    for p in sorted(asset_dir.glob("*.txt")):
        parsed = _parse_contract_filename(p)
        if parsed is None:
            continue
        year, month = parsed
        rows.append((p, _third_friday(year, month), _roll_date(year, month)))
    rows.sort(key=lambda r: r[1])
    return rows


# -------------------------------------------------------------------- #
# Parsing
# -------------------------------------------------------------------- #
def _parse_file(path: Path) -> pd.DataFrame:
    df = pd.read_csv(
        path, sep=";", header=None,
        names=["ts", "open", "high", "low", "close", "volume"],
        engine="c",
    )
    df["ts"] = pd.to_datetime(df["ts"], format="%Y%m%d %H%M%S", utc=True)
    return df.set_index("ts").sort_index()


# -------------------------------------------------------------------- #
# Per-symbol stitching
# -------------------------------------------------------------------- #
@lru_cache(maxsize=8)
def load_intraday_1min(symbol: str = "nq") -> pd.DataFrame:
    """Stitch all contract files for `symbol` using front-month convention."""
    asset_dir = DATA_ROOT / symbol.lower()
    if not asset_dir.exists():
        raise FileNotFoundError(f"missing asset dir: {asset_dir}")

    contracts = _build_contracts(asset_dir)
    if not contracts:
        raise FileNotFoundError(f"no contract files found in {asset_dir}")

    parts: list[pd.DataFrame] = []
    prev_roll: date | None = None
    for idx, (path, expiry, roll) in enumerate(contracts):
        df = _parse_file(path)
        if df.empty:
            continue
        start = prev_roll if prev_roll is not None else df.index[0].date()
        if idx == len(contracts) - 1:
            mask = df.index.date >= start
        else:
            mask = (df.index.date >= start) & (df.index.date < roll)
        slice_ = df.loc[mask]
        if not slice_.empty:
            parts.append(slice_)
        prev_roll = roll

    combined = pd.concat(parts).sort_index()
    combined = combined[~combined.index.duplicated(keep="last")]
    return combined


@lru_cache(maxsize=8)
def load_intraday_5min(symbol: str = "nq") -> pd.DataFrame:
    m1 = load_intraday_1min(symbol)
    return m1.resample("5min").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna()


@lru_cache(maxsize=8)
def load_daily(symbol: str = "nq") -> pd.DataFrame:
    m1 = load_intraday_1min(symbol)
    daily = m1.resample("1D").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna()
    return daily[daily["volume"] > 0]


# -------------------------------------------------------------------- #
# VIX (continuous index — single file, no rolling)
# -------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def load_vix_1min() -> pd.DataFrame:
    p = DATA_ROOT / "vix" / "vix.txt"
    if not p.exists():
        raise FileNotFoundError(p)
    return _parse_file(p)


@lru_cache(maxsize=1)
def load_vix_5min() -> pd.DataFrame:
    return load_vix_1min().resample("5min").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna()


# -------------------------------------------------------------------- #
if __name__ == "__main__":
    print("=" * 72)
    print("Local Data Loader — multi-asset audit")
    print("=" * 72)
    for sym in ("nq", "es", "rty"):
        try:
            d = load_daily(sym)
            m5 = load_intraday_5min(sym)
            print(f"  {sym.upper():4s} daily={len(d):>5,}  5min={len(m5):>7,}  "
                  f"first={d.index[0].date()}  last={d.index[-1].date()}  "
                  f"close={float(d['close'].iloc[-1]):.2f}")
        except Exception as e:
            print(f"  {sym.upper():4s} ERROR  {e}")
    try:
        v = load_vix_5min()
        print(f"  VIX  5min={len(v):>7,}  first={v.index[0].date()}  "
              f"last={v.index[-1].date()}  close={float(v['close'].iloc[-1]):.2f}")
    except Exception as e:
        print(f"  VIX  ERROR  {e}")
    print("=" * 72)
