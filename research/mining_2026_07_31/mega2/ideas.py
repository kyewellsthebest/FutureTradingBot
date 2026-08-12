"""Tranche 1 of the 200-idea catalogue: every concept that reduces to a
per-bar measurement, computed from data already on disk.

Both lists -- ChatGPT's 118 and ours -- converge on the same architecture:
most ideas are not strategies, they are MEASUREMENTS. "Retracement depth",
"inter-trade silence", "false-break frequency", "effective spread" are
feature columns; the strategy layer (thresholds, forms, shapes, k-of-n,
brackets, train/test/cross-quarter validation) already exists and was
debugged the hard way. So tranche 1 implements the measurable ideas as
features and lets the validated engine do what it does.

Four new data-type prefixes, which also enlarges the cross-type combination
space the engine explores:

  t_  tape microstructure INSIDE each 500-tick bar, from the raw tick tape:
      silence gaps, burstiness, largest print, one-lot share, sign
      alternation and entropy, Roll effective spread, Amihud impact,
      retracement depth, impulse timing         (GPT 5-8, 27, 30-32, 35-39,
                                                 77, 81; ours 41-43, 45-46)
  w_  session-anchored path: VWAP deviation, cumulative signed volume,
      distance to session extremes, round-number distance, false-break and
      rejection counts                           (GPT 14, 27, 72; ours 48-50)
  c_  calendar mechanics as floats: expiry Friday, roll week, month-end,
      day-of-month, Friday afternoon             (GPT 74-75; ours 11-17, 24)
  o_  overnight: gap size in range units, overnight drift direction
                                                 (ours 53, 82, 88)

Everything here is computed once per contract and cached; the engine's
forms (raw / change / rank / acceleration) and shapes (state / cross /
hold) then multiply each measurement into dozens of structurally different
conditions -- which is how ~120 of the 200 catalogue entries become
concrete tested hypotheses in a single sweep.
"""
import numpy as np
import pandas as pd

import fuse


def _z(a, w=288):
    s = pd.Series(a, dtype="float64")
    m = s.rolling(w, min_periods=w // 4).mean()
    sd = s.rolling(w, min_periods=w // 4).std()
    return ((s - m) / sd.replace(0, np.nan)).to_numpy()


def build(cn, K, B):
    """All tranche-1 features for one contract, aligned to its bar grid."""
    n = len(B["c"])
    ts, px, sz = fuse.load_tape(fuse.tape_meta()[cn]["path"])
    m = (len(px) // K) * K
    P = px[:m].reshape(-1, K)[:n]
    S = sz[:m].reshape(-1, K)[:n].astype(np.float64)
    T = ts[:m].reshape(-1, K)[:n].astype(np.float64)
    o, h, l, c = B["o"][:n], B["h"][:n], B["l"][:n], B["c"][:n]
    rng = np.maximum(h - l, 1e-9)
    unit = max(float(np.median(rng)), 1e-9)
    F = {}

    # ---- t_: inside-the-bar microstructure --------------------------------
    dt = np.diff(T, axis=1) / 1e9
    F["t_gapmax"] = np.log1p(dt.max(axis=1))          # longest silence
    mu = dt.mean(axis=1)
    F["t_burst"] = dt.std(axis=1) / np.maximum(mu, 1e-9)   # burstiness CV
    tot = np.maximum(S.sum(axis=1), 1.0)
    F["t_bigprint"] = S.max(axis=1) / tot             # largest single print
    F["t_1lot"] = (S <= 1.0).mean(axis=1)             # retail share
    F["t_szmed"] = _z(np.median(S, axis=1))           # participant change

    d = np.diff(P, axis=1)
    sgn = np.sign(d)
    nz = np.abs(sgn)
    flips = (sgn[:, 1:] * sgn[:, :-1] < 0).sum(axis=1)
    moves = np.maximum(nz.sum(axis=1), 1.0)
    F["t_alt"] = flips / moves                        # alternation rate
    up = (sgn > 0).sum(axis=1) / moves
    up = np.clip(up, 1e-6, 1 - 1e-6)
    F["t_ent"] = -(up * np.log(up) + (1 - up) * np.log(1 - up))
    cov = (d[:, 1:] * d[:, :-1]).mean(axis=1)
    F["t_roll"] = 2 * np.sqrt(np.maximum(-cov, 0.0)) / 0.25   # eff. spread
    F["t_amihud"] = _z(rng / np.maximum((P * S).sum(axis=1), 1.0))
    dirn = np.where(c >= o, 1.0, -1.0)
    ext = np.where(dirn > 0, h, l)
    F["t_retr"] = np.abs(ext - c) / rng               # give-back after push
    F["t_impdur"] = np.argmax(np.abs(P - o[:, None]), axis=1) / float(K)

    # ---- w_: session-anchored path ----------------------------------------
    day = (B["ts"][:n] // fuse.DAY_NS).astype(np.int64)
    g = pd.Series(np.arange(n)).groupby(day)
    vol = S.sum(axis=1)
    pv = (P * S).sum(axis=1)
    cv = pd.Series(vol).groupby(day).cumsum().to_numpy()
    cpv = pd.Series(pv).groupby(day).cumsum().to_numpy()
    F["w_vwapd"] = (c - cpv / np.maximum(cv, 1.0)) / unit
    ofi = ((sgn * np.abs(np.diff(P, axis=1))) *
           (S[:, 1:])).sum(axis=1)                    # signed flow proxy
    F["w_cvd"] = _z(pd.Series(ofi).groupby(day).cumsum().to_numpy())
    hi = pd.Series(h).groupby(day).cummax().to_numpy()
    lo = pd.Series(l).groupby(day).cummin().to_numpy()
    F["w_dhi"] = (hi - c) / unit                      # distance to day high
    F["w_dlo"] = (c - lo) / unit
    F["w_round"] = np.abs(c / 25.0 - np.round(c / 25.0))   # 25pt magnets
    ph = np.r_[h[0], h[:-1]]
    fb = ((h > ph) & (c < ph)).astype(float)          # poked above, failed
    F["w_fbreak"] = pd.Series(fb).rolling(21, min_periods=6).mean().to_numpy()
    near = ((hi - h) / unit < 0.15) & (h < hi + 1e-9)
    F["w_reject"] = pd.Series(near.astype(float)).rolling(
        34, min_periods=9).sum().to_numpy()           # knocking on the high

    # ---- c_: calendar mechanics -------------------------------------------
    idx = pd.to_datetime(B["ts"][:n])
    dow, dom, mon = idx.dayofweek.values, idx.day.values, idx.month.values
    F["c_dom"] = dom.astype(float)
    F["c_eom"] = ((dom >= 26) | (dom <= 2)).astype(float)
    third_fri = (dow == 4) & (dom >= 15) & (dom <= 21)
    F["c_expfri"] = third_fri.astype(float)
    F["c_rollwk"] = (np.isin(mon, (3, 6, 9, 12)) &
                     (dom >= 8) & (dom <= 14)).astype(float)
    F["c_friday"] = (dow == 4).astype(float)
    hour = idx.hour.values + idx.minute.values / 60.0
    F["c_lunch"] = ((hour >= 16.5) & (hour <= 18.0)).astype(float)  # UTC

    # ---- o_: overnight ----------------------------------------------------
    # anchored to the 5pm ET maintenance halt, not UTC midnight -- Globex is
    # OPEN at UTC midnight, so a midnight-anchored "gap" measures a one-tick
    # seam in continuous trading (p90 came back at 0.07 range-units, absurd).
    dayg = ((B["ts"][:n] - 21 * 3_600_000_000_000) // fuse.DAY_NS).astype(np.int64)
    first_o = pd.Series(o).groupby(dayg).transform("first").to_numpy()
    last_c = pd.Series(c).groupby(dayg).transform("last").to_numpy()
    prev_close = pd.Series(last_c).groupby(dayg).first()
    pc = prev_close.shift(1).reindex(pd.Series(dayg)).to_numpy()
    F["o_gap"] = (first_o - pc) / unit
    F["o_gapabs"] = np.abs(F["o_gap"])
    del P, S, T, ts, px, sz
    return {k: np.asarray(v, dtype=np.float32)[:n] for k, v in F.items()}
