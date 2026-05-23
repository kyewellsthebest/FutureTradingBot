"""Full sweep: confirmation entry + live chop filter + time blacklist.

Runs the Fib 50% strategy with combinations of three filters to find
the configuration that survives. All on 2 years of Polygon 1-min NQ.

Filter A — CONFIRMATION ENTRY:
   After level50 touch, do NOT fire on the touch bar. Wait for the NEXT
   1-min bar to close back INSIDE the leg (close<level50 for SHORT,
   close>level50 for LONG). Enter at that close price. If the next bar
   instead closes outside the leg (e.g. continues toward the stop),
   skip the setup entirely (don't keep waiting -- that's just chasing).

Filter B — LIVE CHOP FILTER:
   At arm-time (level50 touch bar), compute directional efficiency over
   the last K bars: |close_t - close_{t-K}| / sum(|close_diff|).
   Skip the setup if efficiency < threshold.

Filter C — TIME-OF-DAY BLACKLIST:
   Skip if the entry bar's NY time falls in a blacklisted window.
   Default blacklist = the worst-performing hours from baseline backtest:
   09:30-11:00 (NY open) and 19:00-19:30 (thin overnight).
"""
from __future__ import annotations
import numpy as np, pandas as pd
from dataclasses import dataclass
from pathlib import Path

from research.fib_50_time_of_day import (
    DATA_FILE, PIVOT_K, MIN_LEG_PTS, HTF_PIVOT_K, MIN_ENTRY_RISK_FRAC,
    MAX_HOLD_BARS, MAX_SETUP_AGE_BARS, CONTRACTS, MNQ_PER_PT,
    ROUND_TRIP_COMM_PER_CONTRACT,
    find_pivots, build_pivot_track, build_htf_trend, simulate,
)

# default blacklist windows in (start_min, end_min) since NY midnight
NY_BAD_HOURS = [
    (9*60 + 30, 11*60 + 0),    # NY open block — worst -$81/trade
    (19*60 + 0, 19*60 + 30),   # late-day thin — -$114/trade
    (23*60 + 30, 24*60),       # late evening — -$117/trade
    (0,         1*60 + 0),     # midnight rollover chop
    (16*60 + 0, 16*60 + 30),   # close volatility — -$105/trade
]


@dataclass
class Config:
    label: str
    require_confirmation: bool = False
    min_chop_eff: float | None = None    # None disables
    chop_lookback: int = 30
    use_time_blacklist: bool = False
    tight_stop: bool = False             # use confirm bar's wick + buffer
    tight_stop_buffer: float = 2.0       # NQ points beyond confirm bar wick
    arming_bar_must_reject: bool = False # arming bar's close back inside leg
    realistic_fill: bool = False         # require subsequent bar to retouch
    fill_window_bars: int = 5            # how many bars to wait for retouch


def in_blacklist(minute_of_day: int) -> bool:
    for s, e in NY_BAD_HOURS:
        if s <= minute_of_day < e:
            return True
    return False


def run_with_config(cfg: Config, nq: pd.DataFrame, rh_src, rh_val, rl_src,
                    rl_val, htf_trend, ny_min: np.ndarray) -> list[dict]:
    arr = nq[["open", "high", "low", "close"]].to_numpy()
    closes = arr[:, 3]
    abs_close_diff = np.abs(np.diff(closes, prepend=closes[0]))
    n = len(nq)

    trades = []
    active_until = -1
    used_setups: set[tuple[int, int]] = set()

    for t in range(n - 2):       # -2 so we can peek at t+1 for confirmation
        if t < active_until:
            continue
        if rh_src[t] < 0 or rl_src[t] < 0 or rh_src[t] == rl_src[t]:
            continue
        leg = abs(rh_val[t] - rl_val[t])
        if leg < MIN_LEG_PTS:
            continue
        p1_src = max(rh_src[t], rl_src[t])
        if t - (p1_src + PIVOT_K) > MAX_SETUP_AGE_BARS:
            continue
        setup_key = (int(rh_src[t]), int(rl_src[t]))
        if setup_key in used_setups:
            continue

        level50 = (rh_val[t] + rl_val[t]) / 2.0

        if rh_src[t] < rl_src[t]:
            side = "SHORT" if arr[t, 1] >= level50 else None
        else:
            side = "LONG"  if arr[t, 2] <= level50 else None
        if side is None:
            continue

        tr = htf_trend[t]
        if (side == "LONG" and tr != 1) or (side == "SHORT" and tr != -1):
            continue

        # ---- Filter C: time blacklist -------------------------------
        if cfg.use_time_blacklist and in_blacklist(int(ny_min[t + 1])):
            continue

        # ---- Filter B: live chop filter -----------------------------
        if cfg.min_chop_eff is not None:
            lo = max(0, t - cfg.chop_lookback + 1)
            net = abs(float(closes[t]) - float(closes[lo]))
            path = float(abs_close_diff[lo+1:t+1].sum())
            if path == 0 or (net / path) < cfg.min_chop_eff:
                continue

        # ---- Filter A2: arming-bar instant rejection ----------------
        # Trade only fires if the arming bar CLOSED back inside the leg.
        # Entry stays at level50 (preserves RR).
        if cfg.arming_bar_must_reject:
            arm_close = float(arr[t, 3])
            if side == "SHORT" and arm_close >= level50:
                continue
            if side == "LONG"  and arm_close <= level50:
                continue

        # ---- Filter A: confirmation entry ---------------------------
        if cfg.require_confirmation:
            # need next bar (t+1) close back inside the leg
            next_close = float(arr[t + 1, 3])
            if side == "SHORT" and next_close >= level50:
                # next bar didn't reject the 50% level -- skip
                continue
            if side == "LONG" and next_close <= level50:
                continue
            entry_px = next_close
            entry_loc = t + 1
            entry_bar_for_sim = t + 2 if t + 2 < n else t + 1
        elif cfg.realistic_fill and cfg.arming_bar_must_reject:
            # ARM-REJECT semantics: we only decide "valid" AFTER bar t
            # closes. So the level50 limit isn't placed until bar t+1
            # starts. Need a subsequent bar to re-touch level50 to fill.
            # Look forward up to fill_window_bars. Also break the loop
            # if price hits stop (invalidation) before fill.
            filled = False
            for k in range(1, cfg.fill_window_bars + 1):
                if t + k >= n:
                    break
                bar_h = float(arr[t + k, 1])
                bar_l = float(arr[t + k, 2])
                # invalidation: bar hit the stop before re-touching level50
                if side == "SHORT" and bar_h >= float(rh_val[t]):
                    break
                if side == "LONG"  and bar_l <= float(rl_val[t]):
                    break
                # fill check
                if side == "SHORT" and bar_h >= level50:
                    filled = True; fill_bar = t + k; break
                if side == "LONG"  and bar_l <= level50:
                    filled = True; fill_bar = t + k; break
            if not filled:
                continue
            entry_px = float(level50)
            entry_loc = fill_bar
            entry_bar_for_sim = fill_bar
        else:
            entry_px = float(level50)
            entry_loc = t + 1
            entry_bar_for_sim = t + 1

        if side == "SHORT":
            stop_px   = float(rh_val[t])
            target_px = float(rl_val[t])
        else:
            stop_px   = float(rl_val[t])
            target_px = float(rh_val[t])

        # tight stop: confirmation candle's wick + buffer
        # only valid when confirmation entry is on (we need the confirm bar)
        if cfg.tight_stop and cfg.require_confirmation:
            confirm_high = float(arr[t + 1, 1])
            confirm_low  = float(arr[t + 1, 2])
            if side == "SHORT":
                tight = confirm_high + cfg.tight_stop_buffer
                if tight < stop_px:        # only tighten, never loosen
                    stop_px = tight
            else:
                tight = confirm_low - cfg.tight_stop_buffer
                if tight > stop_px:
                    stop_px = tight

        # MIN_ENTRY_RISK_FRAC (already a tight check w/ level50 entry;
        # for confirmation entry it could push us past the stop -- skip
        # if so since the trade has negative risk geometry)
        if side == "SHORT" and entry_px >= stop_px: continue
        if side == "LONG"  and entry_px <= stop_px: continue
        if abs(stop_px - entry_px) < leg * MIN_ENTRY_RISK_FRAC:
            continue

        exit_loc, exit_px, exit_reason = simulate(
            entry_bar_for_sim, side, entry_px, stop_px, target_px, arr,
        )
        pnl_pts = (entry_px - exit_px) if side == "SHORT" else (exit_px - entry_px)
        pnl_usd = pnl_pts * CONTRACTS * MNQ_PER_PT \
                  - ROUND_TRIP_COMM_PER_CONTRACT * CONTRACTS

        trades.append({
            "side": side,
            "entry_ts": nq.index[entry_loc],
            "exit_ts":  nq.index[exit_loc],
            "exit_reason": exit_reason,
            "pnl_pts": float(pnl_pts),
            "pnl_usd": float(pnl_usd),
            "leg_pts": float(leg),
            "hold_bars": int(exit_loc - entry_bar_for_sim),
        })
        active_until = exit_loc + 1
        used_setups.add(setup_key)

    return trades


def stats(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0, "wr": 0, "pf": 0, "total": 0, "per_trade": 0,
                "avg_hold": 0, "sub60s": 0, "stops": 0, "targets": 0,
                "timeouts": 0, "maxdd": 0}
    tdf = pd.DataFrame(trades)
    n = len(tdf)
    wins = int((tdf["pnl_usd"] > 0).sum())
    gw = float(tdf[tdf["pnl_usd"] > 0]["pnl_usd"].sum())
    gl = float(abs(tdf[tdf["pnl_usd"] < 0]["pnl_usd"].sum()))
    pf = gw / gl if gl > 0 else float("inf")
    cum = tdf["pnl_usd"].cumsum().to_numpy()
    maxdd = float((cum - np.maximum.accumulate(cum)).min())
    return {
        "n": n,
        "wr": wins / n,
        "pf": pf,
        "total": float(tdf["pnl_usd"].sum()),
        "per_trade": float(tdf["pnl_usd"].mean()),
        "avg_hold": float(tdf["hold_bars"].mean()),
        "sub60s": int((tdf["hold_bars"] <= 1).sum()),
        "stops": int((tdf["exit_reason"] == "stop").sum()),
        "targets": int((tdf["exit_reason"] == "target").sum()),
        "timeouts": int((tdf["exit_reason"] == "timeout").sum()),
        "maxdd": maxdd,
    }


def main() -> None:
    print("Loading data + computing pivots/trend...")
    nq = pd.read_csv(DATA_FILE, parse_dates=["ts"]).set_index("ts").sort_index()
    if nq.index.tz is None:
        nq.index = nq.index.tz_localize("UTC")
    h = nq["high"].to_numpy(); l = nq["low"].to_numpy()
    highs3, lows3 = find_pivots(h, l, PIVOT_K)
    highs5, lows5 = find_pivots(h, l, HTF_PIVOT_K)
    n = len(nq)
    rh_src, rh_val, rl_src, rl_val = build_pivot_track(highs3, lows3, PIVOT_K, n)
    htf = build_htf_trend(highs5, lows5, HTF_PIVOT_K, n)

    ny_index = nq.index.tz_convert("America/New_York")
    ny_min = (ny_index.hour * 60 + ny_index.minute).to_numpy(dtype=np.int32)

    configs = [
        Config("BASELINE                                     "),
        Config("+ confirmation entry                         ",
               require_confirmation=True),
        Config("+ chop filter (30bar, eff>0.15)              ",
               min_chop_eff=0.15, chop_lookback=30),
        Config("+ chop filter (30bar, eff>0.25)              ",
               min_chop_eff=0.25, chop_lookback=30),
        Config("+ chop filter (60bar, eff>0.20)              ",
               min_chop_eff=0.20, chop_lookback=60),
        Config("+ time blacklist (NY open + thin hrs)        ",
               use_time_blacklist=True),
        Config("CONFIRM + chop>0.15                          ",
               require_confirmation=True, min_chop_eff=0.15, chop_lookback=30),
        Config("CONFIRM + chop>0.25                          ",
               require_confirmation=True, min_chop_eff=0.25, chop_lookback=30),
        Config("CONFIRM + chop>0.20 (60bar)                  ",
               require_confirmation=True, min_chop_eff=0.20, chop_lookback=60),
        Config("CONFIRM + time blacklist                     ",
               require_confirmation=True, use_time_blacklist=True),
        Config("ALL THREE: confirm + chop>0.20 + blacklist   ",
               require_confirmation=True, min_chop_eff=0.20,
               chop_lookback=60, use_time_blacklist=True),
        Config("ALL THREE: confirm + chop>0.15 + blacklist   ",
               require_confirmation=True, min_chop_eff=0.15,
               chop_lookback=30, use_time_blacklist=True),
        Config("CONFIRM + TIGHT STOP                          ",
               require_confirmation=True, tight_stop=True),
        Config("CONFIRM + TIGHT STOP + chop>0.20 (60)         ",
               require_confirmation=True, tight_stop=True,
               min_chop_eff=0.20, chop_lookback=60),
        Config("CONFIRM + TIGHT STOP + blacklist              ",
               require_confirmation=True, tight_stop=True,
               use_time_blacklist=True),
        Config("ALL: confirm + tight + chop>0.20 + blacklist  ",
               require_confirmation=True, tight_stop=True,
               min_chop_eff=0.20, chop_lookback=60,
               use_time_blacklist=True),
        Config("ALL: confirm + tight + chop>0.15 + blacklist  ",
               require_confirmation=True, tight_stop=True,
               min_chop_eff=0.15, chop_lookback=30,
               use_time_blacklist=True),
        Config("ARM-REJECT (entry@level50, RR preserved)      ",
               arming_bar_must_reject=True),
        Config("ARM-REJECT + chop>0.20 (60bar)                ",
               arming_bar_must_reject=True,
               min_chop_eff=0.20, chop_lookback=60),
        Config("ARM-REJECT + blacklist                        ",
               arming_bar_must_reject=True, use_time_blacklist=True),
        Config("ARM-REJECT + chop>0.20 + blacklist  *BEST?*   ",
               arming_bar_must_reject=True,
               min_chop_eff=0.20, chop_lookback=60,
               use_time_blacklist=True),
        Config("ARM-REJECT + chop>0.30 + blacklist            ",
               arming_bar_must_reject=True,
               min_chop_eff=0.30, chop_lookback=60,
               use_time_blacklist=True),
        # --- realistic fill: requires subsequent bar to re-touch level50 ---
        Config("ARM-REJECT + REALISTIC FILL                   ",
               arming_bar_must_reject=True, realistic_fill=True,
               fill_window_bars=5),
        Config("ARM-REJECT + REALISTIC FILL + chop + blacklist",
               arming_bar_must_reject=True, realistic_fill=True,
               fill_window_bars=5,
               min_chop_eff=0.20, chop_lookback=60,
               use_time_blacklist=True),
        Config("ARM-REJECT + REALISTIC (3bar) + chop + blklst ",
               arming_bar_must_reject=True, realistic_fill=True,
               fill_window_bars=3,
               min_chop_eff=0.20, chop_lookback=60,
               use_time_blacklist=True),
        Config("ARM-REJECT + REALISTIC (10bar) + chop + blklst",
               arming_bar_must_reject=True, realistic_fill=True,
               fill_window_bars=10,
               min_chop_eff=0.20, chop_lookback=60,
               use_time_blacklist=True),
    ]

    print("\nRunning configurations across full 2-yr history...\n")
    print(f"{'Config':<48} {'n':>5} {'/mo':>5} {'WR':>6} {'PF':>5} "
          f"{'$/tr':>7} {'Total':>9} {'AvgHold':>8} {'<2bar':>6} {'MaxDD':>9}")
    print("-" * 124)
    days = (nq.index[-1] - nq.index[0]).days
    months = days / 30.44
    for cfg in configs:
        trades = run_with_config(cfg, nq, rh_src, rh_val, rl_src, rl_val,
                                 htf, ny_min)
        s = stats(trades)
        pf = f"{s['pf']:>4.2f}" if np.isfinite(s['pf']) else " inf"
        print(f"{cfg.label} {s['n']:>5} {s['n']/months:>4.1f} "
              f"{s['wr']*100:>5.1f}% {pf} ${s['per_trade']:>+5,.0f} "
              f"${s['total']:>+7,.0f} {s['avg_hold']:>7.1f}m "
              f"{s['sub60s']:>5}  ${s['maxdd']:>+6,.0f}")


if __name__ == "__main__":
    main()
