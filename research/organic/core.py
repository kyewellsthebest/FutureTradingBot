"""ORGANIC BEHAVIOUR OBSERVATORY — the shared spine.

This library does NOT score strategies. It measures what the market DOES
after a given moment. A "behaviour record" is the unit of output:

    state/formation  ->  forward path distribution  ->  destinations  ->  costs

Strategies are DERIVED from behaviour records later, never assumed up front.

DESIGN RULES (violations are bugs):
  1. No lookahead. Features at bar i use bars <= i. Outcomes use bars > i.
     Every feature array is explicitly shifted or built from trailing windows.
  2. Touch-conditioning. A resting limit only fills on the subset where price
     came to it, and that subset is adversely selected. `touch_conditional()`
     measures P(touch) and E[outcome | touched] separately. Cell-average
     drift is NEVER a tradeable number.
  3. Effective N. Overlapping forward windows are not independent
     observations. `effective_n()` de-overlaps by episode and by day.
  4. Honest costs. `cost_floor()` = commission + stop-slippage expectation +
     adverse-selection buffer, expressed in ticks AND dollars, per market.
     Prior campaigns charged stops at exactly the stop price (no slippage);
     that gap is worth $200-400/wk on the incumbent book and is fixed here.
  5. Temporal splits. DISCOVERY / (embargo) / VALIDATION / TEST, chronological.
     Test data is not readable through this module without an explicit,
     logged unlock.

Usage:
    m = Market("ZB")
    ev = m.where(m.session == US)          # any boolean mask -> event indices
    rec = observe(m, ev, side=+1)          # a behaviour record
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd

REPO = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
DATA = os.path.join(REPO, "data", "polygon")

# --------------------------------------------------------------- economics
# (pv, tick, commission_round_turn, tradable_as, intraday_margin, affordable)
ECON = {
    "NQ":  (2.0,       0.25,      1.42, "MNQ", 100.0,  True),
    "ES":  (5.0,       0.25,      1.42, "MES",  50.0,  True),
    "RTY": (5.0,       0.10,      1.80, "M2K",  50.0,  True),
    "YM":  (0.5,       1.0,       1.80, "MYM",  50.0,  True),
    "GC":  (10.0,      0.10,      2.20, "MGC",  250.0, True),
    "CL":  (100.0,     0.01,      2.20, "MCL",  250.0, True),
    "NG":  (2500.0,    0.001,     2.60, "MNG",  400.0, True),
    "HG":  (2500.0,    0.0005,    2.60, "MHG",  400.0, True),
    "ZB":  (1000.0,    0.03125,   4.50, "ZB",   800.0, True),
    "ZN":  (1000.0,    0.015625,  4.50, "ZN",   700.0, True),
    "ZF":  (1000.0,    0.0078125, 4.50, "ZF",   600.0, True),
    "ZT":  (2000.0,    0.0078125, 4.50, "ZT",   500.0, True),
    "6E":  (12500.0,   0.0001,    1.60, "M6E",  300.0, True),
    "6B":  (6250.0,    0.0001,    1.60, "M6B",  300.0, True),
    "6A":  (10000.0,   0.0001,    1.60, "M6A",  300.0, True),
    "6J":  (12500000.0, 0.0000005, 3.20, "6J", 2800.0, False),
    "MBT": (0.1,       5.0,       2.20, "MBT",  900.0, True),
    "ETH": (0.1,       0.25,      2.20, "MET",  500.0, True),
    "ZC":  (50.0,      0.25,      4.00, "ZC",  1200.0, True),
    "ZW":  (50.0,      0.25,      4.00, "ZW",  1700.0, True),
    "ZS":  (50.0,      0.25,      4.00, "ZS",  2200.0, False),
    "HO":  (42000.0,   0.0001,    3.50, "HO",  7000.0, False),
    "RB":  (42000.0,   0.0001,    3.50, "RB",  7500.0, False),
}
EXCLUDED = {"SI", "SIL"}   # silver only; NQ re-admitted 2026-08-02

# ------------------------------------------------------------------ splits
# Chronological, purged. Committed here so mining code cannot drift them.
DISCOVERY_END = pd.Timestamp("2025-05-31T23:59:59Z")
EMBARGO_DAYS = 21                      # provisional; measure_embargo() refines
VALIDATION_START = DISCOVERY_END + pd.Timedelta(days=EMBARGO_DAYS)
VALIDATION_END = pd.Timestamp("2025-12-31T23:59:59Z")
TEST_START = pd.Timestamp("2026-01-01T00:00:00Z")

# ------------------------------------------------------------- cost policy
# The correction the adversarial panel surfaced: a triggered stop becomes a
# market order and does NOT fill at the trigger price. Prior campaigns
# assumed it did. Default 0.5 tick is a placeholder pending live measurement
# (bot's own bracket fills); STOP_SLIP_TICKS is the single knob.
STOP_SLIP_TICKS = float(os.environ.get("ORG_STOP_SLIP", "0.5"))
ENTRY_SLIP_TICKS_MARKET = 1.0          # market/stop entries
ENTRY_SLIP_TICKS_LIMIT = 0.0           # resting limit fills at its price
TIME_EXIT_SLIP_TICKS = 1.0             # flatten is a market order
ADVERSE_BUFFER_TICKS = 0.5             # queue-position / selection buffer

SESSIONS = {"asia": (0.0, 7.0), "eu": (7.0, 13.5), "us": (13.5, 20.0)}
EOD_UTC, REOPEN_UTC = 20.7, 22.0
HORIZONS = (1, 3, 6, 12, 24, 48, 96)   # bars forward (5m: 5min .. 8h)


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str)
                          .encode()).hexdigest()[:16]


# =====================================================================
#  MARKET — bars + causal descriptors. Nothing here peeks forward.
# =====================================================================
class Market:
    def __init__(self, root: str, tf: str = "5min", allow_test: bool = False):
        if root in EXCLUDED:
            raise ValueError(f"{root} is excluded by standing directive")
        self.root = root
        self.tf = tf
        self.pv, self.tick, self.comm, self.traded_as, self.margin, self.afford = ECON[root]

        df = pd.read_csv(f"{DATA}/{root}_{tf}.csv")
        df["ts"] = pd.to_datetime(df.ts, utc=True)
        df = df.sort_values("ts").reset_index(drop=True)
        if not allow_test:
            df = df[df.ts < TEST_START].reset_index(drop=True)
        self.df = df
        self.n = len(df)
        self.ts = df.ts
        self.O = df.open.values.astype(np.float64)
        self.H = df.high.values.astype(np.float64)
        self.L = df.low.values.astype(np.float64)
        self.C = df.close.values.astype(np.float64)
        self.V = df.volume.values.astype(np.float64)

        # ---- causal descriptors (all trailing) ----
        tr = np.maximum(self.H - self.L, np.abs(self.C - np.r_[np.nan, self.C[:-1]]))
        self.tr = tr
        self.atr = pd.Series(tr).rolling(14).mean().values
        self.rng = self.H - self.L
        self.body = np.abs(self.C - self.O)

        cdt = (self.ts + pd.Timedelta(minutes=self._tf_min())).dt.tz_convert(None)
        self.nh = (cdt.dt.hour + cdt.dt.minute / 60).values
        self.dow = cdt.dt.dayofweek.values
        self.day_codes = pd.factorize(self.ts.dt.date)[0]
        self.n_days = self.day_codes.max() + 1

        self.session = np.full(self.n, "other", dtype=object)
        for name, (lo, hi) in SESSIONS.items():
            self.session[(self.nh >= lo) & (self.nh < hi)] = name

        # volatility regime: ATR vs its own trailing month, causal
        bars_per_day = int(24 * 60 / self._tf_min())
        self.atr_ref = (pd.Series(self.atr).rolling(bars_per_day * 21, min_periods=bars_per_day * 3)
                        .mean().shift(1).values)
        self.vol_hi = self.atr > self.atr_ref
        self.atr_pct = (pd.Series(self.atr).rolling(bars_per_day * 21, min_periods=bars_per_day * 3)
                        .rank(pct=True).shift(1).values)

        # trend context, causal
        self.ma_slow = pd.Series(self.C).rolling(bars_per_day * 4).mean().shift(1).values
        self.trend_up = self.C > self.ma_slow

        # intraday location
        self.day_open = pd.Series(self.O).groupby(self.day_codes).transform("first").values
        self.day_hi = pd.Series(self.H).groupby(self.day_codes).cummax().values
        self.day_lo = pd.Series(self.L).groupby(self.day_codes).cummin().values
        span = np.maximum(self.day_hi - self.day_lo, 1e-12)
        self.pos_in_day = (self.C - self.day_lo) / span

        g = pd.Series(self.H).groupby(self.day_codes)
        self.pdh = g.max().shift(1).reindex(self.day_codes).values
        self.pdl = pd.Series(self.L).groupby(self.day_codes).min().shift(1).reindex(self.day_codes).values
        self.pdc = pd.Series(self.C).groupby(self.day_codes).last().shift(1).reindex(self.day_codes).values

        # tradability mask: market open, not into EOD flatten, not roll-gap
        gap = (self.ts.diff() > pd.Timedelta("3h")) & (self.ts.shift(1).dt.weekday != 4)
        self.contam = gap.rolling(int(bars_per_day / 2), min_periods=1).max().fillna(0).values.astype(bool)
        self.eod_block = ((self.nh >= EOD_UTC - 0.5) & (self.nh < REOPEN_UTC))
        self.eod_exit = ((self.nh >= EOD_UTC) & (self.nh < REOPEN_UTC))
        warm = bars_per_day * 25
        self.tradable = (~self.contam) & (~self.eod_block) & np.isfinite(self.atr) & (self.atr > 0)
        self.tradable[:warm] = False
        self.tradable[-(max(HORIZONS) + 5):] = False

        # split membership by bar
        self.in_discovery = (self.ts <= DISCOVERY_END).values
        self.in_validation = ((self.ts >= VALIDATION_START) & (self.ts <= VALIDATION_END)).values

        # next EOD bar index (for forced-flat horizons)
        ne = np.full(self.n + 1, self.n, dtype=np.int64)
        for i in range(self.n - 1, -1, -1):
            ne[i] = i if self.eod_exit[i] else ne[i + 1]
        self.next_eod = ne[:self.n]

    def _tf_min(self) -> int:
        return int(self.tf.replace("min", ""))

    # ---- helpers -------------------------------------------------------
    def ticks(self, price_delta):
        return price_delta / self.tick

    def dollars(self, price_delta):
        return price_delta * self.pv

    def round_px(self, px):
        return np.round(np.round(px / self.tick) * self.tick, 10)

    def where(self, mask, split="discovery"):
        """Event indices: mask AND tradable AND inside the requested split."""
        m = np.asarray(mask) & self.tradable
        if split == "discovery":
            m = m & self.in_discovery
        elif split == "validation":
            m = m & self.in_validation
        elif split == "all":
            pass
        else:
            raise ValueError(f"unknown split {split!r}")
        return np.where(m)[0]

    def cost_floor(self, stop_rate: float = 0.3, entry_is_limit: bool = True):
        """Honest per-trade cost in dollars and ticks."""
        slip_ticks = (ENTRY_SLIP_TICKS_LIMIT if entry_is_limit else ENTRY_SLIP_TICKS_MARKET)
        slip_ticks += stop_rate * STOP_SLIP_TICKS
        slip_ticks += ADVERSE_BUFFER_TICKS
        dollars = self.comm + slip_ticks * self.tick * self.pv
        return dict(dollars=round(dollars, 2), ticks=round(dollars / (self.tick * self.pv), 3),
                    comm=self.comm, slip_ticks=round(slip_ticks, 3))


# =====================================================================
#  FORWARD PATHS — what the market actually did next
# =====================================================================
def forward_matrix(m: Market, idx: np.ndarray, H: int):
    """(len(idx), H+1) matrices of high/low/close AFTER each event bar.

    Column j = bar idx+j. Column 0 is the event bar itself (entry reference
    is its CLOSE, so column 0 carries no tradeable excursion and is excluded
    from MFE/MAE — the same-bar-optimism discipline)."""
    pad = H + 2
    Hp = np.concatenate([m.H, np.full(pad, np.nan)])
    Lp = np.concatenate([m.L, np.full(pad, np.nan)])
    Cp = np.concatenate([m.C, np.full(pad, np.nan)])
    js = np.arange(0, H + 1)
    bars = idx[:, None] + js[None, :]
    return Hp[bars], Lp[bars], Cp[bars]


def effective_n(m: Market, idx: np.ndarray, H: int):
    """De-overlapped counts. Overlapping windows are not independent."""
    if len(idx) == 0:
        return dict(raw=0, episodes=0, days=0)
    keep, last = [], -10 ** 9
    for i in idx:
        if i - last >= H:
            keep.append(i)
            last = i
    return dict(raw=int(len(idx)), episodes=int(len(keep)),
                days=int(len(np.unique(m.day_codes[idx]))))


def drift_profile(m: Market, idx: np.ndarray, side: int, horizons=HORIZONS):
    """Signed forward drift from the event bar's close, in ticks.

    This is the RAW conditional drift — the honest answer to 'what does the
    market do next'. It is NOT a tradeable number (see touch_conditional)."""
    if len(idx) == 0:
        return {}
    Hm, Lm, Cm = forward_matrix(m, idx, max(horizons))
    entry = m.C[idx]
    out = {}
    for h in horizons:
        d = (Cm[:, h] - entry) * side / m.tick
        d = d[np.isfinite(d)]
        if len(d) < 5:
            continue
        boot = np.random.RandomState(_seed(idx, h)).choice(d, size=(400, len(d)))
        bmeans = boot.mean(axis=1)
        out[h] = dict(
            n=int(len(d)),
            mean_ticks=round(float(d.mean()), 3),
            median_ticks=round(float(np.median(d)), 3),
            ci95=[round(float(np.percentile(bmeans, 2.5)), 3),
                  round(float(np.percentile(bmeans, 97.5)), 3)],
            p_up=round(float((d > 0).mean()), 3),
        )
    return out


def excursion_stats(m: Market, idx: np.ndarray, side: int, H: int = 48):
    """Where price ACTUALLY travels: MFE/MAE distributions in ticks.

    Excludes the event bar (column 0) — no same-bar credit."""
    if len(idx) == 0:
        return {}
    Hm, Lm, Cm = forward_matrix(m, idx, H)
    entry = m.C[idx]
    fav = (Hm[:, 1:] - entry[:, None]) * side if side > 0 else (entry[:, None] - Lm[:, 1:])
    adv = (entry[:, None] - Lm[:, 1:]) if side > 0 else (Hm[:, 1:] - entry[:, None])
    mfe = np.nanmax(fav, axis=1) / m.tick
    mae = np.nanmax(adv, axis=1) / m.tick
    ok = np.isfinite(mfe) & np.isfinite(mae)
    mfe, mae = mfe[ok], mae[ok]
    if len(mfe) < 5:
        return {}
    q = [10, 25, 50, 75, 80, 90, 95]
    # time-to-MFE: how fast the good part happens
    tmfe = np.nanargmax(np.where(np.isfinite(fav), fav, -np.inf), axis=1)[ok] + 1
    return dict(
        n=int(len(mfe)),
        mfe_ticks={f"p{p}": round(float(np.percentile(mfe, p)), 2) for p in q},
        mae_ticks={f"p{p}": round(float(np.percentile(mae, p)), 2) for p in q},
        mfe_mean=round(float(mfe.mean()), 2),
        mae_mean=round(float(mae.mean()), 2),
        edge_ratio=round(float(mfe.mean() / max(mae.mean(), 1e-9)), 3),
        bars_to_mfe_median=float(np.median(tmfe)),
    )


def destination_hits(m: Market, idx: np.ndarray, side: int, H: int = 48):
    """Does price travel to structural places? Hit rate within H bars.

    Only destinations AHEAD of price in the trade direction are counted,
    and each is reported with the naive distance so 'it hit because it was
    close' is visible rather than hidden."""
    if len(idx) == 0:
        return {}
    Hm, Lm, Cm = forward_matrix(m, idx, H)
    entry = m.C[idx]
    atr = m.atr[idx]
    dests = {
        "prior_day_high": m.pdh[idx],
        "prior_day_low": m.pdl[idx],
        "prior_close": m.pdc[idx],
        "day_open": m.day_open[idx],
        "day_high_sofar": m.day_hi[idx],
        "day_low_sofar": m.day_lo[idx],
        "atr_1x": entry + side * atr,
        "atr_2x": entry + side * 2 * atr,
        "round_number": _nearest_round(m, entry, side),
    }
    out = {}
    for name, lvl in dests.items():
        lvl = np.asarray(lvl, dtype=np.float64)
        ahead = (lvl - entry) * side > 0
        if ahead.sum() < 20:
            continue
        if side > 0:
            hit = np.nanmax(Hm[:, 1:], axis=1) >= lvl
        else:
            hit = np.nanmin(Lm[:, 1:], axis=1) <= lvl
        sub = ahead & np.isfinite(lvl)
        dist = np.abs(lvl - entry)[sub] / np.maximum(atr[sub], 1e-12)
        out[name] = dict(
            n_ahead=int(sub.sum()),
            hit_rate=round(float(hit[sub].mean()), 3),
            median_dist_atr=round(float(np.median(dist)), 2),
        )
    return out


def _nearest_round(m: Market, entry, side):
    """Next 'round' price in the trade direction, scaled to the instrument."""
    mag = 10 ** np.floor(np.log10(np.maximum(np.abs(entry), 1e-9)) - 1.5)
    step = mag * 5
    if side > 0:
        return np.ceil(entry / step) * step
    return np.floor(entry / step) * step


def touch_conditional(m: Market, idx: np.ndarray, side: int, depth_ticks: float,
                      ttl: int = 6, H: int = 48):
    """THE tradeable measurement: rest a limit `depth_ticks` away, and report
    P(touch within ttl) and the forward outcome CONDITIONAL ON BEING FILLED.

    Filled instances are an adversely-selected subsample of the state; the
    unconditional drift systematically overstates what a limit order earns.
    """
    if len(idx) == 0:
        return {}
    pad = H + ttl + 3
    Hp = np.concatenate([m.H, np.full(pad, np.nan)])
    Lp = np.concatenate([m.L, np.full(pad, np.nan)])
    Cp = np.concatenate([m.C, np.full(pad, np.nan)])
    limit = m.round_px(m.C[idx] - side * depth_ticks * m.tick)

    steps = np.arange(1, ttl + 1)
    bars = idx[:, None] + steps[None, :]
    adverse = Lp[bars] if side > 0 else Hp[bars]
    hit = (adverse * side) <= (limit * side)[:, None]
    any_hit = hit.any(axis=1)
    j = np.where(any_hit, hit.argmax(axis=1), 0)
    fill_bar = idx + 1 + j

    if any_hit.sum() < 10:
        return dict(depth_ticks=depth_ticks, n_events=int(len(idx)),
                    p_touch=round(float(any_hit.mean()), 4), n_filled=int(any_hit.sum()))

    fb = fill_bar[any_hit]
    epx = limit[any_hit]
    js = np.arange(0, H + 1)
    fbars = fb[:, None] + js[None, :]
    fH, fL, fC = Hp[fbars], Lp[fbars], Cp[fbars]
    fav = (fH[:, 1:] - epx[:, None]) * side if side > 0 else (epx[:, None] - fL[:, 1:])
    adv = (epx[:, None] - fL[:, 1:]) if side > 0 else (fH[:, 1:] - epx[:, None])
    mfe = np.nanmax(fav, axis=1) / m.tick
    mae = np.nanmax(adv, axis=1) / m.tick

    out = dict(depth_ticks=depth_ticks, ttl=ttl,
               n_events=int(len(idx)), n_filled=int(any_hit.sum()),
               p_touch=round(float(any_hit.mean()), 4))
    for h in (6, 12, 24, 48):
        if h > H:
            continue
        d = (fC[:, h] - epx) * side / m.tick
        d = d[np.isfinite(d)]
        if len(d) < 10:
            continue
        out[f"drift_{h}"] = dict(mean_ticks=round(float(d.mean()), 3),
                                 median_ticks=round(float(np.median(d)), 3),
                                 p_up=round(float((d > 0).mean()), 3))
    ok = np.isfinite(mfe) & np.isfinite(mae)
    if ok.sum() > 10:
        out["mfe_p50"] = round(float(np.percentile(mfe[ok], 50)), 2)
        out["mfe_p80"] = round(float(np.percentile(mfe[ok], 80)), 2)
        out["mae_p50"] = round(float(np.percentile(mae[ok], 50)), 2)
        out["mae_p80"] = round(float(np.percentile(mae[ok], 80)), 2)
        out["edge_ratio"] = round(float(mfe[ok].mean() / max(mae[ok].mean(), 1e-9)), 3)
    return out


# =====================================================================
#  NULLS — a pipeline never shown to find nothing cannot be trusted
# =====================================================================
def _seed(idx, salt=0):
    return int((int(idx[0]) if len(idx) else 0) * 7919 + len(idx) * 104729 + salt) % (2 ** 31)


def misalignment_null(m: Market, idx: np.ndarray, side: int, horizon: int = 12,
                      n_draws: int = 200):
    """Null = circular whole-day shift of OUTCOMES vs FEATURES.

    Day-permutation of features is broken (rolling stats survive it). Shifting
    outcomes by whole days preserves intraday structure and vol clustering
    while destroying the feature/outcome correspondence."""
    if len(idx) < 20:
        return {}
    rs = np.random.RandomState(_seed(idx, horizon))
    real = drift_profile(m, idx, side, (horizon,)).get(horizon, {}).get("mean_ticks", 0.0)
    bars_per_day = int(24 * 60 / m._tf_min())
    draws = []
    for _ in range(n_draws):
        shift = int(rs.randint(1, 200)) * bars_per_day
        shifted = (idx + shift) % (m.n - horizon - 2)
        shifted = shifted[m.tradable[shifted]]
        if len(shifted) < 20:
            continue
        d = (m.C[np.minimum(shifted + horizon, m.n - 1)] - m.C[shifted]) * side / m.tick
        draws.append(float(np.nanmean(d)))
    if len(draws) < 30:
        return {}
    draws = np.array(draws)
    return dict(real_ticks=round(real, 3),
                null_mean=round(float(draws.mean()), 3),
                null_p95=round(float(np.percentile(draws, 95)), 3),
                null_p5=round(float(np.percentile(draws, 5)), 3),
                z=round(float((real - draws.mean()) / (draws.std() + 1e-9)), 2),
                beats_null=bool(abs(real) > np.percentile(np.abs(draws), 95)))


def random_entry_control(m: Market, side: int, n: int, horizon: int = 12,
                         match_mask=None, seed: int = 0):
    """Matched-random-entry baseline: the same geometry at random times.

    Isolates timing skill from 'this exit geometry wins at random times in a
    reverting market' — the exact confound of the incumbent edge's shape."""
    pool = np.where(m.tradable & m.in_discovery & (match_mask if match_mask is not None else True))[0]
    if len(pool) < n or n < 20:
        return {}
    rs = np.random.RandomState(seed)
    pick = rs.choice(pool, size=min(n, len(pool)), replace=False)
    return drift_profile(m, pick, side, (horizon,)).get(horizon, {})


# =====================================================================
#  BEHAVIOUR RECORD — the unit of output
# =====================================================================
@dataclass
class Behaviour:
    market: str
    observation: str            # plain-language description of the state
    side: int                   # +1 long-hypothesis, -1 short-hypothesis
    n_events: int
    n_effective: int
    n_days: int
    split: str
    drift: dict = field(default_factory=dict)
    excursion: dict = field(default_factory=dict)
    destinations: dict = field(default_factory=dict)
    null: dict = field(default_factory=dict)
    cost: dict = field(default_factory=dict)
    context: dict = field(default_factory=dict)
    verdict: str = ""

    def to_dict(self):
        return asdict(self)


def observe(m: Market, idx: np.ndarray, side: int, observation: str,
            split: str = "discovery", H: int = 48, want_null: bool = True,
            min_events: int = 200) -> Behaviour:
    """Measure everything about what happens after these moments."""
    eff = effective_n(m, idx, H)
    b = Behaviour(market=m.root, observation=observation, side=side,
                  n_events=eff["raw"], n_effective=eff["episodes"],
                  n_days=eff["days"], split=split,
                  cost=m.cost_floor())
    if eff["raw"] < min_events or eff["episodes"] < 60:
        b.verdict = f"UNDERPOWERED (raw={eff['raw']}, episodes={eff['episodes']})"
        return b
    b.drift = drift_profile(m, idx, side)
    b.excursion = excursion_stats(m, idx, side, H)
    b.destinations = destination_hits(m, idx, side, H)
    if want_null:
        b.null = misalignment_null(m, idx, side)
    # context breakdown: does the behaviour depend on WHEN / vol / trend?
    b.context = _context_breakdown(m, idx, side)
    b.verdict = _verdict(m, b)
    return b


def _context_breakdown(m: Market, idx: np.ndarray, side: int, horizon: int = 12):
    out = {}
    for label, groups in (
        ("session", {s: m.session[idx] == s for s in ("asia", "eu", "us")}),
        ("vol", {"hi": m.vol_hi[idx], "lo": ~m.vol_hi[idx]}),
        ("trend", {"up": m.trend_up[idx], "dn": ~m.trend_up[idx]}),
        ("dow", {str(d): m.dow[idx] == d for d in range(5)}),
    ):
        sub = {}
        for gname, gmask in groups.items():
            gi = idx[np.asarray(gmask, dtype=bool)]
            if len(gi) < 80:
                continue
            d = drift_profile(m, gi, side, (horizon,)).get(horizon)
            if d:
                sub[gname] = dict(n=d["n"], mean_ticks=d["mean_ticks"], p_up=d["p_up"])
        if sub:
            out[label] = sub
    return out


def _verdict(m: Market, b: Behaviour) -> str:
    d12 = b.drift.get(12, {})
    if not d12:
        return "NO DRIFT DATA"
    mean = d12["mean_ticks"]
    lo, hi = d12["ci95"]
    floor = b.cost["ticks"]
    if lo <= 0 <= hi:
        return f"NULL (12-bar drift {mean:+.2f}t, CI spans zero)"
    if abs(mean) < floor:
        return f"REAL BUT UNTRADEABLE ({mean:+.2f}t < {floor:.2f}t cost floor)"
    if b.null and not b.null.get("beats_null", False):
        return f"FAILS MISALIGNMENT NULL (z={b.null.get('z')})"
    return f"CANDIDATE ({mean:+.2f}t vs {floor:.2f}t floor, z={b.null.get('z', '?')})"


# =====================================================================
#  FORMATION ALPHABET — scale-free shapes, discovered not named
# =====================================================================
def encode_bars(m: Market, n_letters: int = 9):
    """Each bar -> one letter, scale-free. NO pattern names, no dogma.

    Letter = (direction+size of the close move) x (where the close sat in
    the bar's own range). Both normalized by trailing ATR so the alphabet
    means the same thing in every regime and every market."""
    prev_c = np.r_[np.nan, m.C[:-1]]
    move = (m.C - prev_c) / np.maximum(m.atr, 1e-12)
    clv = (2 * m.C - m.H - m.L) / np.maximum(m.rng, 1e-12)   # -1 .. +1
    mv = np.digitize(move, [-0.5, -0.15, 0.15, 0.5])          # 0..4
    cl = np.digitize(clv, [-0.33, 0.33])                      # 0..2
    if n_letters == 9:
        mv3 = np.digitize(move, [-0.25, 0.25])                # 0..2
        letters = mv3 * 3 + cl
    else:
        letters = mv * 3 + cl                                  # 0..14
    letters = letters.astype(np.int16)
    letters[~np.isfinite(move) | ~np.isfinite(clv)] = -1
    return letters


def formation_words(m: Market, k: int = 3, n_letters: int = 9):
    """Rolling k-letter word ending at each bar (causal). -1 = invalid."""
    L = encode_bars(m, n_letters)
    word = np.zeros(m.n, dtype=np.int64)
    valid = np.ones(m.n, dtype=bool)
    for j in range(k):
        s = np.r_[np.full(j, -1), L[:m.n - j]] if j else L
        valid &= s >= 0
        word = word * n_letters + np.maximum(s, 0)
    word[~valid] = -1
    return word


def multi_scale(m: Market, factor: int):
    """Resample to a coarser timeframe, preserving OHLCV integrity."""
    df = m.df.set_index("ts")
    agg = df.resample(f"{m._tf_min() * factor}min", label="left", closed="left").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum")).dropna(subset=["close"])
    return agg.reset_index()


# =====================================================================
#  MANIFEST — everything a run must declare before it runs
# =====================================================================
def manifest():
    return dict(
        splits=dict(discovery_end=str(DISCOVERY_END), embargo_days=EMBARGO_DAYS,
                    validation=[str(VALIDATION_START), str(VALIDATION_END)],
                    test_start=str(TEST_START)),
        costs=dict(stop_slip_ticks=STOP_SLIP_TICKS,
                   entry_slip_market=ENTRY_SLIP_TICKS_MARKET,
                   time_exit_slip=TIME_EXIT_SLIP_TICKS,
                   adverse_buffer=ADVERSE_BUFFER_TICKS),
        horizons=list(HORIZONS),
        excluded=sorted(EXCLUDED),
        core_sha=_sha(open(__file__).read()) if os.path.exists(__file__) else "n/a",
    )


if __name__ == "__main__":
    print(json.dumps(manifest(), indent=1))
