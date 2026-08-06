"""Limit-order scalp simulator for 1-second bars (numba).

Execution model (conservative):
  * signal at bar t close -> LIMIT order active from bar t+1
  * BUY limit at close[t] - entry_off ticks; fills at bar j only if
    low[j] <= limit - 1 tick (price traded STRICTLY THROUGH the level) ->
    undercounts real fills and keeps every adversely-selected one
  * entry order cancelled if unfilled after entry_window bars
  * exit target: SELL limit entry + target ticks, same strict-through rule
  * stop: if low[j] <= entry - stop ticks -> market exit at stop level
    (market leg; extra slippage handled by cost model)
  * same-bar target+stop conflict -> stop wins (pessimistic)
  * time stop: after max_hold bars -> market exit at next bar open
  * session/gap boundary -> flat at last in-session close (market leg)

Cost models applied in stats:
  A "flat":   $4.40 per round trip regardless of legs (user's spec)
  B "legs":   $1.40 commission + $1.50 per MARKET leg (passive legs pay 0)
"""
import numpy as np
import pandas as pd
from numba import njit

TICK = 0.25
PV = 20.0                      # $ per NQ point
COMM = 1.40
SLIP_LEG = 1.50


@njit(cache=True)
def _scalp_core(sig_idx, direction, o, h, l, c, tday,
                entry_off, entry_window, target, stop, max_hold,
                strict=True):
    """strict=True: fills require price 1 tick THROUGH the limit
    (conservative). strict=False: fills on touch (optimistic upper bound —
    real queue fills lie between the two)."""
    n = len(o)
    m = len(sig_idx)
    e_i = np.empty(m, np.int64)
    x_i = np.empty(m, np.int64)
    e_px = np.empty(m, np.float64)
    x_px = np.empty(m, np.float64)
    mkt_leg = np.empty(m, np.int8)      # exit was market (1) or passive (0)
    k = 0
    busy_until = -1
    for s in range(m):
        si = sig_idx[s]
        if si + 1 <= busy_until or si + 2 >= n:
            continue
        limit = c[si] - direction * entry_off * TICK
        # ---- entry phase
        j = si + 1
        j_end = min(si + entry_window, n - 2)
        fill_j = -1
        while j <= j_end:
            if tday[j] != tday[si + 1]:
                break
            thr = TICK if strict else 0.0
            if direction > 0:
                if l[j] <= limit - thr:
                    fill_j = j
                    break
            else:
                if h[j] >= limit + thr:
                    fill_j = j
                    break
            j += 1
        if fill_j < 0:
            busy_until = j          # order cancelled; free after window
            continue
        entry_px = limit
        tgt = entry_px + direction * target * TICK
        stp = entry_px - direction * stop * TICK
        # ---- position phase
        j = fill_j
        exit_j = -1
        exit_px = np.nan
        was_mkt = np.int8(1)
        hold_end = min(fill_j + max_hold, n - 2)
        while True:
            if j > fill_j:      # evaluate exits from the bar after fill
                if tday[j] != tday[fill_j]:
                    exit_j = j - 1
                    exit_px = c[j - 1]
                    was_mkt = 1
                    break
                if direction > 0:
                    if l[j] <= stp:
                        exit_j = j
                        exit_px = stp
                        was_mkt = 1
                        break
                    if h[j] >= tgt + (TICK if strict else 0.0):
                        exit_j = j
                        exit_px = tgt
                        was_mkt = 0
                        break
                else:
                    if h[j] >= stp:
                        exit_j = j
                        exit_px = stp
                        was_mkt = 1
                        break
                    if l[j] <= tgt - (TICK if strict else 0.0):
                        exit_j = j
                        exit_px = tgt
                        was_mkt = 0
                        break
            else:
                # fill bar: allow stop check on the same bar (conservative:
                # if the bar that filled us also traded through the stop)
                if direction > 0 and l[j] <= stp:
                    exit_j = j
                    exit_px = stp
                    was_mkt = 1
                    break
                if direction < 0 and h[j] >= stp:
                    exit_j = j
                    exit_px = stp
                    was_mkt = 1
                    break
            if j >= hold_end:
                exit_j = j + 1
                exit_px = o[j + 1]
                was_mkt = 1
                break
            j += 1
        e_i[k] = fill_j
        x_i[k] = exit_j
        e_px[k] = entry_px
        x_px[k] = exit_px
        mkt_leg[k] = was_mkt
        k += 1
        busy_until = exit_j
    return e_i[:k], x_i[:k], e_px[:k], x_px[:k], mkt_leg[:k]


def scalp(df, arrays, signal, direction, entry_off=1, entry_window=10,
          target=2, stop=8, max_hold=120, strict=True):
    sig_idx = np.flatnonzero(np.asarray(signal))
    ei, xi, epx, xpx, mkt = _scalp_core(
        sig_idx, direction, arrays["o"], arrays["h"], arrays["l"], arrays["c"],
        arrays["tday"], float(entry_off), int(entry_window),
        float(target), float(stop), int(max_hold), strict)
    t = pd.DataFrame({
        "entry_time": arrays["ts"][ei], "exit_time": arrays["ts"][xi],
        "entry_px": epx, "exit_px": xpx, "dir": direction,
        "pnl_pts": direction * (xpx - epx), "mkt_exit": mkt,
        "hold_s": xi - ei,
    })
    if len(t):
        t["entry_time"] = pd.to_datetime(t["entry_time"], utc=True).dt.tz_convert("America/New_York")
        t["exit_time"] = pd.to_datetime(t["exit_time"], utc=True).dt.tz_convert("America/New_York")
    return t


def scalp_stats(t, n_signals=None, label="", start=None, end=None):
    if start is not None:
        t = t[t["exit_time"] >= pd.Timestamp(start, tz="America/New_York")]
    if end is not None:
        t = t[t["exit_time"] < pd.Timestamp(end, tz="America/New_York")]
    if len(t) < 20:
        return {"n": int(len(t))}
    gross = t["pnl_pts"] * PV
    costA = 4.40
    costB = COMM + SLIP_LEG * t["mkt_exit"]        # entry always passive
    netA = gross - costA
    netB = gross - costB
    weeks = max((t["exit_time"].max() - t["exit_time"].min()).days / 7.0, 1e-9)
    ex = t["exit_time"].dt.tz_localize(None)
    wkA = netA.groupby(ex.dt.to_period("W")).sum()
    wkB = netB.groupby(ex.dt.to_period("W")).sum()
    tA = netA.mean() / (netA.std() / np.sqrt(len(netA)) + 1e-12)
    return {
        "n": int(len(t)), "trades_wk": len(t) / weeks,
        "win": float((t["pnl_pts"] > 0).mean()),
        "gross_tr": float(gross.mean()),
        "netA_tr": float(netA.mean()), "netB_tr": float(netB.mean()),
        "wkA": float(wkA.mean()), "wkB": float(wkB.mean()),
        "wkA_std": float(wkA.std()), "poswkA": float((wkA > 0).mean()),
        "tA": float(tA),
        "hold_s": float(t["hold_s"].mean()),
        "mkt_exit_frac": float(t["mkt_exit"].mean()),
    }


def fmt(label, s):
    if s.get("n", 0) < 20:
        return f"{label:<40s} n={s.get('n', 0)} (too few)"
    return (f"{label:<40s} n={s['n']:>6d} t/wk={s['trades_wk']:>5.0f} wr={s['win']:.2f} "
            f"g=${s['gross_tr']:>5.2f} nA=${s['netA_tr']:>5.2f} nB=${s['netB_tr']:>5.2f} "
            f"$wkA={s['wkA']:>6.0f} $wkB={s['wkB']:>6.0f} t={s['tA']:>5.1f} "
            f"hold={s['hold_s']:>4.0f}s mkx={s['mkt_exit_frac']:.2f}")
