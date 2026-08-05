"""Edge-discovery research harness.

Data resolution: 1-minute bars (no tick data available in this environment).
All fills are conservative:
  * signal on bar t close -> enter at bar t+1 OPEN
  * stop & target checked against bar high/low; if both touch in the same
    bar the STOP is assumed to fill (pessimistic)
  * time exits fill at the exit bar's OPEN
Costs: $1.40 commission + $3.00 slippage = $4.40 per round trip per contract.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from numba import njit

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "research"))

CACHE = Path("/tmp/claude-0/-home-user-FutureTradingBot/9e995bcf-6e09-510e-8133-bdeedccb3152/scratchpad/cache")
CACHE.mkdir(parents=True, exist_ok=True)

COMMISSION_RT = 1.40
SLIPPAGE_RT = 3.00
COST_RT = COMMISSION_RT + SLIPPAGE_RT           # $ per round trip per contract

POINT_VALUE = {"nq": 20.0, "es": 50.0, "rty": 50.0}


# ------------------------------------------------------------------ #
# Data
# ------------------------------------------------------------------ #
def load(symbol: str = "nq") -> pd.DataFrame:
    """Continuous front-month 1-min bars, ET timestamps, with trading-day id."""
    pq = CACHE / f"{symbol}_1min_et.parquet"
    if pq.exists():
        return pd.read_parquet(pq)
    import local_data_loader as ldl
    df = ldl.load_intraday_1min(symbol).copy()
    df.index = df.index.tz_convert("America/New_York")
    df = df[(df[["open", "high", "low", "close"]] > 0).all(axis=1)]
    # trading day: Globex session starting 18:00 ET belongs to next calendar day
    idx = df.index
    tday = pd.Series(idx.date, index=idx)
    after_start = idx.hour >= 18
    tday[after_start] = (idx[after_start] + pd.Timedelta(hours=6)).date
    df["tday"] = pd.to_datetime(tday.values)
    df.to_parquet(pq)
    return df


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """Common per-bar features. Everything uses info available at bar close."""
    out = df.copy()
    c, h, l, o, v = out["close"], out["high"], out["low"], out["open"], out["volume"]
    out["ret"] = c.diff()
    out["range"] = h - l
    out["atr"] = out["range"].ewm(span=30, min_periods=10).mean()
    out["vol_ma"] = v.ewm(span=60, min_periods=20).mean()
    out["vol_z"] = (v - out["vol_ma"]) / out["vol_ma"].clip(lower=1)
    rv = out["ret"].rolling(60, min_periods=30).std()
    out["ret_sd"] = rv
    out["ret_z"] = out["ret"] / rv.clip(lower=1e-9)
    # run length of consecutive same-sign closes
    sign = np.sign(out["ret"].fillna(0))
    grp = (sign != sign.shift()).cumsum()
    out["run"] = sign.groupby(grp).cumcount() + 1
    out["run"] *= sign
    # time fields (ET)
    out["hour"] = out.index.hour
    out["minute"] = out.index.minute
    out["hhmm"] = out["hour"] * 100 + out["minute"]
    out["dow"] = out.index.dayofweek
    out["rth"] = (out["hhmm"] >= 930) & (out["hhmm"] < 1600)
    # per-trading-day cumulative fields
    g = out.groupby("tday", sort=False)
    out["day_high"] = g["high"].cummax()
    out["day_low"] = g["low"].cummin()
    pv = (c * v).groupby(out["tday"], sort=False).cumsum()
    vv = v.groupby(out["tday"], sort=False).cumsum()
    out["vwap"] = pv / vv.clip(lower=1)
    out["bar_of_day"] = g.cumcount()
    return out


def day_levels(df: pd.DataFrame) -> pd.DataFrame:
    """Per trading day: RTH open/high/low/close, overnight high/low, prior-day refs."""
    rth = df[df["rth"]]
    # overnight = STRICTLY pre-RTH bars of the trading day (18:00 -> 9:29).
    # Using all non-RTH bars would leak the 16:00-17:00 post-close session
    # (future at RTH signal time) into the levels — a lookahead that
    # fabricated a huge fake sweep-reversal edge before this fix.
    on = df[(df["hhmm"] >= 1800) | (df["hhmm"] < 930)]
    lv = pd.DataFrame({
        "rth_open": rth.groupby("tday")["open"].first(),
        "rth_high": rth.groupby("tday")["high"].max(),
        "rth_low": rth.groupby("tday")["low"].min(),
        "rth_close": rth.groupby("tday")["close"].last(),
        "on_high": on.groupby("tday")["high"].max(),
        "on_low": on.groupby("tday")["low"].min(),
        "on_close_pre_open": on[on["hhmm"] < 930].groupby("tday")["close"].last(),
    })
    lv["prev_rth_high"] = lv["rth_high"].shift()
    lv["prev_rth_low"] = lv["rth_low"].shift()
    lv["prev_rth_close"] = lv["rth_close"].shift()
    return lv


# ------------------------------------------------------------------ #
# Backtester
# ------------------------------------------------------------------ #
@dataclass
class ExitSpec:
    """Exit philosophy for a sleeve.

    stop_atr/target_atr: multiples of entry-time ATR (None = disabled)
    stop_pts/target_pts: absolute points (override ATR version)
    max_hold: minutes (bars) before time exit at open
    eod_hhmm: force flat at first bar with hhmm >= this value (same trading day)
    trail_atr: trailing stop distance in ATR multiples (from best excursion)
    """
    stop_atr: float | None = None
    target_atr: float | None = None
    stop_pts: float | None = None
    target_pts: float | None = None
    max_hold: int = 60
    eod_hhmm: int | None = None
    trail_atr: float | None = None
    label: str = ""


@dataclass
class Result:
    trades: pd.DataFrame
    symbol: str
    name: str

    def stats(self, start=None, end=None) -> dict:
        t = self.trades
        if start is not None:
            t = t[t["exit_time"] >= pd.Timestamp(start, tz="America/New_York")]
        if end is not None:
            t = t[t["exit_time"] < pd.Timestamp(end, tz="America/New_York")]
        return trade_stats(t, POINT_VALUE[self.symbol])


@njit(cache=True)
def _sim_core(sig_idx, o, h, l, c, atr, hhmm, tday, direction,
              stop_atr, target_atr, stop_pts, target_pts,
              max_hold, eod_hhmm, trail_atr):
    """Core trade loop. NaN disables a parameter; eod_hhmm<0 disables."""
    n = len(o)
    m = len(sig_idx)
    entry_i = np.empty(m, np.int64)
    exit_i = np.empty(m, np.int64)
    entry_px_a = np.empty(m, np.float64)
    exit_px_a = np.empty(m, np.float64)
    k = 0
    last_exit = -1
    for s in range(m):
        si = sig_idx[s]
        e = si + 1
        if e <= last_exit:
            continue
        entry_px = o[e]
        a = atr[si]
        stop_d = stop_pts if not np.isnan(stop_pts) else (
            stop_atr * a if not np.isnan(stop_atr) and a > 0 else np.nan)
        tgt_d = target_pts if not np.isnan(target_pts) else (
            target_atr * a if not np.isnan(target_atr) and a > 0 else np.nan)
        trail_d = trail_atr * a if not np.isnan(trail_atr) and a > 0 else np.nan

        stop_px = entry_px - direction * stop_d if not np.isnan(stop_d) else np.nan
        tgt_px = entry_px + direction * tgt_d if not np.isnan(tgt_d) else np.nan
        best = entry_px
        exit_px = np.nan
        exit_j = -1
        j_max = min(e + max_hold, n - 1)
        j = e
        while j <= j_max:
            eod_hit = False
            if eod_hhmm >= 0:
                if eod_hhmm >= 1800:
                    eod_hit = hhmm[j] >= eod_hhmm
                else:
                    # session spans midnight: only trigger in the 00:00-17:45
                    # portion so overnight entries (18:00+) aren't insta-closed
                    eod_hit = eod_hhmm <= hhmm[j] < 1745
            if tday[j] != tday[e]:
                # session/data-gap boundary: flatten at last tradable price
                # of the entry session, never book the cross-gap jump
                exit_px = c[j - 1]
                exit_j = j - 1
                break
            if eod_hit:
                exit_px = o[j]
                exit_j = j
                break
            if direction > 0:
                stop_eff = stop_px
                if not np.isnan(trail_d):
                    ts_ = best - trail_d
                    stop_eff = ts_ if np.isnan(stop_px) else max(stop_px, ts_)
                if not np.isnan(stop_eff) and l[j] <= stop_eff:
                    exit_px = min(stop_eff, o[j])
                    exit_j = j
                    break
                if not np.isnan(tgt_px) and h[j] >= tgt_px:
                    exit_px = tgt_px
                    exit_j = j
                    break
                if h[j] > best:
                    best = h[j]
            else:
                stop_eff = stop_px
                if not np.isnan(trail_d):
                    ts_ = best + trail_d
                    stop_eff = ts_ if np.isnan(stop_px) else min(stop_px, ts_)
                if not np.isnan(stop_eff) and h[j] >= stop_eff:
                    exit_px = max(stop_eff, o[j])
                    exit_j = j
                    break
                if not np.isnan(tgt_px) and l[j] <= tgt_px:
                    exit_px = tgt_px
                    exit_j = j
                    break
                if l[j] < best:
                    best = l[j]
            j += 1
        if exit_j < 0:
            exit_j = j_max
            exit_px = c[exit_j] if exit_j == n - 1 else o[min(exit_j + 1, n - 1)]
        entry_i[k] = e
        exit_i[k] = exit_j
        entry_px_a[k] = entry_px
        exit_px_a[k] = exit_px
        k += 1
        last_exit = exit_j
    return entry_i[:k], exit_i[:k], entry_px_a[:k], exit_px_a[:k]


def simulate(df: pd.DataFrame, signal: pd.Series, direction: int,
             exit_spec: ExitSpec, symbol: str = "nq", name: str = "",
             arrays: dict | None = None) -> Result:
    """signal: boolean Series aligned to df.index — True at bar t means enter
    at bar t+1 open. Non-overlapping trades (1-lot sleeve)."""
    if arrays is None:
        arrays = get_arrays(df)
    n = arrays["n"]
    sig_idx = np.flatnonzero(np.asarray(signal))
    sig_idx = sig_idx[sig_idx < n - 2]
    es = exit_spec
    f = lambda x: np.nan if x is None else float(x)
    ei, xi, epx, xpx = _sim_core(
        sig_idx, arrays["o"], arrays["h"], arrays["l"], arrays["c"],
        arrays["atr"], arrays["hhmm"], arrays["tday"], direction,
        f(es.stop_atr), f(es.target_atr), f(es.stop_pts), f(es.target_pts),
        int(es.max_hold), -1 if es.eod_hhmm is None else int(es.eod_hhmm),
        f(es.trail_atr))
    pnl = direction * (xpx - epx)
    trades = pd.DataFrame({
        "entry_time": arrays["ts"][ei], "exit_time": arrays["ts"][xi],
        "entry_px": epx, "exit_px": xpx, "dir": direction,
        "pnl_pts": pnl, "hold_min": xi - ei,
    })
    if len(trades):
        trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True).dt.tz_convert("America/New_York")
        trades["exit_time"] = pd.to_datetime(trades["exit_time"], utc=True).dt.tz_convert("America/New_York")
    return Result(trades=trades, symbol=symbol, name=name)


_ARRAY_CACHE: dict[int, dict] = {}


def get_arrays(df: pd.DataFrame) -> dict:
    key = id(df)
    if key not in _ARRAY_CACHE:
        _ARRAY_CACHE.clear()
        atr = df["atr"].to_numpy(np.float64)
        atr = np.where(np.isfinite(atr) & (atr > 0), atr, np.nan)
        _ARRAY_CACHE[key] = {
            "o": df["open"].to_numpy(np.float64),
            "h": df["high"].to_numpy(np.float64),
            "l": df["low"].to_numpy(np.float64),
            "c": df["close"].to_numpy(np.float64),
            "atr": atr,
            "hhmm": df["hhmm"].to_numpy(np.int64),
            # session code: trading day PLUS a split at any >2h data gap so
            # no simulated trade ever holds across missing data
            "tday": (pd.factorize(df["tday"])[0].astype(np.int64) * 100000
                     + (df.index.to_series().diff() > pd.Timedelta(hours=2))
                     .cumsum().to_numpy(np.int64)),
            "ts": df.index.to_numpy(),
            "n": len(df),
        }
    return _ARRAY_CACHE[key]


# ------------------------------------------------------------------ #
# Statistics
# ------------------------------------------------------------------ #
def trade_stats(trades: pd.DataFrame, point_value: float) -> dict:
    if trades is None or len(trades) == 0:
        return {"n": 0}
    gross = trades["pnl_pts"] * point_value
    net = gross - COST_RT
    weeks_span = max((trades["exit_time"].max() - trades["exit_time"].min()).days / 7.0, 1e-9)
    ex_naive = trades["exit_time"].dt.tz_localize(None)
    wk = net.groupby(ex_naive.dt.to_period("W")).sum()
    wk_gross = gross.groupby(ex_naive.dt.to_period("W")).sum()
    day = net.groupby(trades["exit_time"].dt.date).sum()
    eq = net.cumsum()
    dd = eq - eq.cummax()
    t_stat = net.mean() / (net.std(ddof=1) / np.sqrt(len(net))) if len(net) > 2 and net.std() > 0 else 0.0
    yearly = net.groupby(trades["exit_time"].dt.year).sum()
    losing_weeks = wk[wk < 0]
    return {
        "n": int(len(trades)),
        "trades_per_week": len(trades) / weeks_span,
        "win_rate": float((net > 0).mean()),
        "avg_gross_usd": float(gross.mean()),
        "avg_net_usd": float(net.mean()),
        "gross_per_week": float(wk_gross.mean()),
        "net_per_week": float(wk.mean()),
        "net_week_std": float(wk.std(ddof=1)) if len(wk) > 2 else np.nan,
        "weekly_sharpe": float(wk.mean() / wk.std(ddof=1)) if len(wk) > 2 and wk.std() > 0 else np.nan,
        "pct_pos_weeks": float((wk > 0).mean()),
        "worst_day": float(day.min()),
        "worst_week": float(wk.min()),
        "avg_losing_week": float(losing_weeks.mean()) if len(losing_weeks) else 0.0,
        "max_dd": float(dd.min()),
        "t_stat": float(t_stat),
        "total_net": float(net.sum()),
        "years_pos": f"{int((yearly > 0).sum())}/{len(yearly)}",
        "yearly": {int(k): round(float(v)) for k, v in yearly.items()},
        "avg_hold_min": float(trades["hold_min"].mean()),
    }


def fmt(name: str, s: dict) -> str:
    if s.get("n", 0) == 0:
        return f"{name:<44s} no trades"
    return (f"{name:<44s} n={s['n']:>6d} t/wk={s['trades_per_week']:>5.1f} "
            f"wr={s['win_rate']:.2f} avg_g=${s['avg_gross_usd']:>7.2f} "
            f"avg_n=${s['avg_net_usd']:>7.2f} t={s['t_stat']:>5.1f} "
            f"$wk_g={s['gross_per_week']:>7.0f} $wk_n={s['net_per_week']:>7.0f} "
            f"posW={s['pct_pos_weeks']:.2f} yrs+={s['years_pos']}")


IS_END = "2024-01-01"          # in-sample:  ... -> 2023-12-31
OOS_START = "2024-01-01"       # out-of-sample: 2024-01-01 -> present


def is_oos(res: Result) -> tuple[dict, dict]:
    return res.stats(end=IS_END), res.stats(start=OOS_START)
