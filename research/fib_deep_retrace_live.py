"""LIVE-style simulation of the NEW Fib strategy:

  - Entry at 0.9 retracement (price comes 90% back toward originating pivot)
  - Stop at originating pivot (tight, ~10% of leg)
  - Target at 2.0x leg extension beyond the opposite pivot
  - Trend filter: 2 higher highs AND 2 higher lows (structural)
  - Min leg: 50 points
  - Dynamic sizing 1-5 MNQ targeting $250 risk per trade

NO LOOK-AHEAD anywhere:
  - Pivots known only PIVOT_K bars after they form
  - Trend filter uses only past confirmed pivots
  - Limit order at entry_pct level placed when setup confirms; fills only
    when a subsequent bar's price actually reaches it
  - Stop / target / timeout checked intrabar on each new bar
"""
from __future__ import annotations
import numpy as np, pandas as pd
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "polygon" / "NQ_1min.csv"

# === Strategy parameters ====================================================
PIVOT_K              = 3
HTF_PIVOT_K          = 5            # for 2HH+2HL trend filter
MIN_LEG_PTS          = 50.0
MAX_HOLD_BARS        = 240          # 4-hour hard cap
MAX_SETUP_AGE_BARS   = 60           # setup expires 60 min if not filled

ENTRY_PCT            = 0.90         # 90% retrace
TARGET_EXT           = 0.0          # 0 = just to opposite pivot (1.0x leg from entry)

# === Sizing ================================================================
STARTING_BALANCE     = 50_000.0
MNQ_PER_PT           = 2.0
COMM_PER_CONTRACT_RT = 2.0
TARGET_RISK_USD      = 250.0
MAX_CONTRACTS        = 5
MIN_CONTRACTS        = 1


def dynamic_size(stop_pts: float) -> int:
    if stop_pts <= 0:
        return MIN_CONTRACTS
    raw = TARGET_RISK_USD / (stop_pts * MNQ_PER_PT)
    n = int(raw)
    return max(MIN_CONTRACTS, min(MAX_CONTRACTS, n))


# === Pivots & trend filter =================================================
def find_pivots(high: np.ndarray, low: np.ndarray, k: int):
    n = len(high)
    highs, lows = [], []
    for t in range(k, n - k):
        if high[t] == high[t - k:t + k + 1].max():
            highs.append((t, float(high[t])))
        if low[t] == low[t - k:t + k + 1].min():
            lows.append((t, float(low[t])))
    return highs, lows


# === Setup / Trade ==========================================================
@dataclass
class Setup:
    side: str
    pivot_high_idx: int
    pivot_low_idx: int
    pivot_high_px: float
    pivot_low_px:  float
    entry_px:  float
    stop_px:   float
    target_px: float
    created_at_bar: int
    expires_at_bar: int


@dataclass
class Trade:
    entry_bar: int
    exit_bar: int
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    side: str
    size: int
    entry_px: float
    stop_px: float
    target_px: float
    exit_px: float
    exit_reason: str
    pnl_usd: float
    leg_pts: float


def run_live_sim(nq: pd.DataFrame) -> tuple[list[Trade], pd.Series]:
    h = nq["high"].to_numpy()
    l = nq["low"].to_numpy()
    c = nq["close"].to_numpy()
    n = len(nq)
    idx = nq.index

    # --- Pre-compute pivots; mark each as known only at +PIVOT_K -----------
    raw_h3, raw_l3 = find_pivots(h, l, PIVOT_K)
    raw_h5, raw_l5 = find_pivots(h, l, HTF_PIVOT_K)
    confirmed_h3_at: dict[int, list[tuple[int, float]]] = defaultdict(list)
    confirmed_l3_at: dict[int, list[tuple[int, float]]] = defaultdict(list)
    confirmed_h5_at: dict[int, list[tuple[int, float]]] = defaultdict(list)
    confirmed_l5_at: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for src, px in raw_h3: confirmed_h3_at[src + PIVOT_K].append((src, px))
    for src, px in raw_l3: confirmed_l3_at[src + PIVOT_K].append((src, px))
    for src, px in raw_h5: confirmed_h5_at[src + HTF_PIVOT_K].append((src, px))
    for src, px in raw_l5: confirmed_l5_at[src + HTF_PIVOT_K].append((src, px))

    # Most-recent confirmed k=3 pivots (for setup geometry)
    cur_h_src, cur_h_px = -1, np.nan
    cur_l_src, cur_l_px = -1, np.nan
    # Rolling list of confirmed k=5 pivots (for trend filter — need last 2 each)
    seen_h5: list[tuple[int, float]] = []
    seen_l5: list[tuple[int, float]] = []

    pending_setups: list[Setup] = []
    used_setup_keys: set[tuple[int, int]] = set()
    trades: list[Trade] = []
    active_trade: Trade | None = None
    equity = STARTING_BALANCE
    equity_curve = np.zeros(n)

    for t in range(n):
        # --- update confirmed pivots (bar t close already happened) --------
        for src, px in confirmed_h3_at.get(t, []):
            if src > cur_h_src:
                cur_h_src, cur_h_px = src, px
        for src, px in confirmed_l3_at.get(t, []):
            if src > cur_l_src:
                cur_l_src, cur_l_px = src, px
        for src, px in confirmed_h5_at.get(t, []):
            seen_h5.append((src, px))
        for src, px in confirmed_l5_at.get(t, []):
            seen_l5.append((src, px))

        # --- check active trade ---------------------------------------------
        if active_trade is not None:
            tr = active_trade
            stop_hit = (tr.side == "LONG"  and l[t] <= tr.stop_px) or \
                       (tr.side == "SHORT" and h[t] >= tr.stop_px)
            tgt_hit  = (tr.side == "LONG"  and h[t] >= tr.target_px) or \
                       (tr.side == "SHORT" and l[t] <= tr.target_px)
            exit_now = False
            if stop_hit and tgt_hit:
                tr.exit_px = tr.stop_px; tr.exit_reason = "stop"; exit_now = True
            elif stop_hit:
                tr.exit_px = tr.stop_px; tr.exit_reason = "stop"; exit_now = True
            elif tgt_hit:
                tr.exit_px = tr.target_px; tr.exit_reason = "target"; exit_now = True
            elif t - tr.entry_bar >= MAX_HOLD_BARS:
                tr.exit_px = float(c[t]); tr.exit_reason = "timeout"; exit_now = True
            if exit_now:
                tr.exit_bar = t
                tr.exit_ts = idx[t]
                pnl_pts = (tr.entry_px - tr.exit_px) if tr.side == "SHORT" \
                          else (tr.exit_px - tr.entry_px)
                tr.pnl_usd = pnl_pts * tr.size * MNQ_PER_PT \
                             - COMM_PER_CONTRACT_RT * tr.size
                equity += tr.pnl_usd
                trades.append(tr)
                active_trade = None

        # --- check pending setups for fill ----------------------------------
        if active_trade is None:
            for s in pending_setups:
                if t < s.created_at_bar + 1: continue
                if t > s.expires_at_bar:
                    s.expires_at_bar = -1   # mark for prune
                    continue
                # Did this bar's range reach the entry price?
                fill = False
                if s.side == "SHORT" and h[t] >= s.entry_px:
                    fill = True
                elif s.side == "LONG" and l[t] <= s.entry_px:
                    fill = True
                if not fill: continue
                # Fire the trade
                stop_pts = abs(s.stop_px - s.entry_px)
                size = dynamic_size(stop_pts)
                active_trade = Trade(
                    entry_bar=t, exit_bar=-1,
                    entry_ts=idx[t], exit_ts=idx[t],
                    side=s.side, size=size,
                    entry_px=s.entry_px, stop_px=s.stop_px,
                    target_px=s.target_px, exit_px=0.0,
                    exit_reason="", pnl_usd=0.0,
                    leg_pts=abs(s.pivot_high_px - s.pivot_low_px),
                )
                used_setup_keys.add((s.pivot_high_idx, s.pivot_low_idx))
                s.expires_at_bar = -1   # mark filled
                break

        # --- prune dead setups ---------------------------------------------
        pending_setups = [s for s in pending_setups if s.expires_at_bar >= 0]

        # --- create new setup if conditions are met ------------------------
        if (cur_h_src >= 0 and cur_l_src >= 0 and cur_h_src != cur_l_src
                and active_trade is None):
            key = (cur_h_src, cur_l_src)
            if key not in used_setup_keys:
                leg = abs(cur_h_px - cur_l_px)
                if leg >= MIN_LEG_PTS:
                    p1_src = max(cur_h_src, cur_l_src)
                    age_bars = t - (p1_src + PIVOT_K)
                    if age_bars <= MAX_SETUP_AGE_BARS:
                        side = "SHORT" if cur_h_src < cur_l_src else "LONG"

                        # Trend filter: 2HH+2HL (or 2LH+2LL for DOWN)
                        trend_ok = False
                        if len(seen_h5) >= 2 and len(seen_l5) >= 2:
                            h1, h0 = seen_h5[-1][1], seen_h5[-2][1]
                            l1, l0 = seen_l5[-1][1], seen_l5[-2][1]
                            if side == "LONG"  and h1 > h0 and l1 > l0:
                                trend_ok = True
                            if side == "SHORT" and h1 < h0 and l1 < l0:
                                trend_ok = True
                        if not trend_ok:
                            used_setup_keys.add(key)  # don't retry
                            continue

                        # Calculate entry / stop / target
                        if side == "SHORT":
                            # retracement up from pivot_low toward pivot_high
                            entry_px  = float(cur_l_px) + ENTRY_PCT * (float(cur_h_px) - float(cur_l_px))
                            stop_px   = float(cur_h_px)
                            target_px = float(cur_l_px) - TARGET_EXT * (float(cur_h_px) - float(cur_l_px))
                        else:
                            entry_px  = float(cur_h_px) - ENTRY_PCT * (float(cur_h_px) - float(cur_l_px))
                            stop_px   = float(cur_l_px)
                            target_px = float(cur_h_px) + TARGET_EXT * (float(cur_h_px) - float(cur_l_px))

                        # Skip if price has already blown past the entry
                        if side == "SHORT" and h[t] >= entry_px:
                            used_setup_keys.add(key)
                            continue
                        if side == "LONG"  and l[t] <= entry_px:
                            used_setup_keys.add(key)
                            continue

                        pending_setups.append(Setup(
                            side=side,
                            pivot_high_idx=cur_h_src,
                            pivot_low_idx=cur_l_src,
                            pivot_high_px=cur_h_px,
                            pivot_low_px=cur_l_px,
                            entry_px=entry_px,
                            stop_px=stop_px,
                            target_px=target_px,
                            created_at_bar=t,
                            expires_at_bar=t + MAX_SETUP_AGE_BARS,
                        ))
                        used_setup_keys.add(key)

        equity_curve[t] = equity

    return trades, pd.Series(equity_curve, index=idx, name="equity")


# === Reporting ==============================================================
def report(trades: list[Trade], eq: pd.Series) -> None:
    n = len(trades)
    if n == 0:
        print("No trades."); return
    tdf = pd.DataFrame([t.__dict__ for t in trades])
    tdf["entry_ts"] = pd.to_datetime(tdf["entry_ts"])
    tdf["exit_ts"]  = pd.to_datetime(tdf["exit_ts"])
    tdf["date"]     = tdf["entry_ts"].dt.tz_convert("America/New_York").dt.date
    tdf["month"]    = tdf["entry_ts"].dt.tz_convert("America/New_York").dt.to_period("M")
    tdf["win"]      = tdf["pnl_usd"] > 0

    days = tdf["date"].nunique()
    cal_days = (eq.index[-1] - eq.index[0]).days
    cal_months = cal_days / 30.44

    print("=" * 78)
    print("LIVE-STYLE BACKTEST  —  DEEP RETRACE STRATEGY")
    print("(Entry 0.9 retrace, stop at pivot, target 2.0x leg ext, 2HH+2HL trend)")
    print("=" * 78)
    print(f"Period          : {eq.index[0].date()} → {eq.index[-1].date()}  "
          f"({cal_days} cal days, ~{cal_months:.1f} mo)")
    print(f"Starting equity : ${STARTING_BALANCE:>10,.0f}")
    print(f"Ending equity   : ${eq.iloc[-1]:>10,.0f}")
    print(f"Net P&L         : ${eq.iloc[-1] - STARTING_BALANCE:>+10,.0f}")
    pct = (eq.iloc[-1] / STARTING_BALANCE - 1) * 100
    print(f"Return          : {pct:>+10.1f}%   ({pct / cal_months:>+5.2f}% / month)")
    print()
    print(f"Total trades        : {n}")
    print(f"  per trading day   : {n / days:>5.1f}")
    print(f"  per calendar day  : {n / cal_days:>5.1f}")
    print(f"  per month         : {n / cal_months:>5.1f}")
    wins = int(tdf['win'].sum())
    print(f"Wins / Losses       : {wins} / {n - wins}  ({wins / n * 100:.1f}% WR)")
    gw = float(tdf[tdf['win']]['pnl_usd'].sum())
    gl = float(abs(tdf[~tdf['win']]['pnl_usd'].sum()))
    pf = gw / gl if gl > 0 else float('inf')
    print(f"Profit factor       : {pf:.2f}   (wins ${gw:,.0f} / losses ${gl:,.0f})")
    avg_w = tdf[tdf['win']]['pnl_usd'].mean()
    avg_l = tdf[~tdf['win']]['pnl_usd'].mean()
    print(f"Avg win / loss      : ${avg_w:>+7,.0f} / ${avg_l:>+7,.0f}  "
          f"(ratio {abs(avg_w/avg_l):.1f}x)")
    print(f"Largest win / loss  : ${tdf['pnl_usd'].max():>+7,.0f} / "
          f"${tdf['pnl_usd'].min():>+7,.0f}")

    # Size breakdown
    print(f"\n{'POSITION-SIZE BREAKDOWN':^78}")
    print("-" * 78)
    print(f"{'Size':>6} | {'Trades':>7} | {'Wins':>5} | {'WR':>6} | "
          f"{'Avg win':>8} | {'Avg loss':>9} | {'Net P&L':>10}")
    for sz in range(1, MAX_CONTRACTS + 1):
        g = tdf[tdf["size"] == sz]
        if len(g) == 0:
            print(f"{sz:>5} M | {'—':>7} | {'—':>5} | {'—':>6} | "
                  f"{'—':>8} | {'—':>9} | {'—':>10}")
            continue
        w = int(g['win'].sum())
        wr = w / len(g) * 100
        aw = g[g['win']]['pnl_usd'].mean() if w > 0 else 0
        al = g[~g['win']]['pnl_usd'].mean() if len(g) - w > 0 else 0
        net = g['pnl_usd'].sum()
        print(f"{sz:>5} M | {len(g):>7} | {w:>5} | {wr:>5.1f}% | "
              f"${aw:>+6,.0f} | ${al:>+7,.0f} | ${net:>+8,.0f}")

    # Monthly
    print(f"\n{'MONTHLY P&L':^78}")
    print("-" * 78)
    print(f"{'Month':<10} {'Trades':>7} {'Wins':>5} {'WR':>6} {'P&L':>10} {'Return%':>9}")
    monthly = tdf.groupby("month").agg(
        trades=("pnl_usd", "size"),
        wins=("win", "sum"),
        pnl=("pnl_usd", "sum"),
    )
    bal = STARTING_BALANCE
    for m, r in monthly.iterrows():
        wr = r['wins'] / r['trades'] * 100
        ret = r['pnl'] / bal * 100
        print(f"{str(m):<10} {int(r['trades']):>7} {int(r['wins']):>5} "
              f"{wr:>5.1f}% ${r['pnl']:>+8,.0f} {ret:>+7.2f}%")
        bal += r['pnl']

    # Drawdowns
    print(f"\n{'DRAWDOWNS':^78}")
    print("-" * 78)
    daily = tdf.groupby("date")["pnl_usd"].sum()
    worst_day = daily.min()
    worst_day_d = daily.idxmin()
    best_day  = daily.max()
    best_day_d  = daily.idxmax()
    print(f"Worst single day        : ${worst_day:>+10,.0f} on {worst_day_d}")
    print(f"Best single day         : ${best_day:>+10,.0f} on {best_day_d}")
    daily_full = daily.reindex(
        pd.date_range(daily.index.min(), daily.index.max()), fill_value=0
    )
    rolling7 = daily_full.rolling(7).sum()
    print(f"Worst rolling 7-day P&L : ${rolling7.min():>+10,.0f} ending "
          f"{rolling7.idxmin().date()}")
    peak = eq.cummax()
    dd = eq - peak
    max_dd = dd.min()
    max_dd_at = dd.idxmin()
    print(f"Max equity drawdown     : ${max_dd:>+10,.0f} on {max_dd_at.date()}")
    print(f"  peak ${peak.loc[max_dd_at]:,.0f} → trough ${eq.loc[max_dd_at]:,.0f}")

    # Losing streak
    streak = 0; max_streak = 0; streak_pnl = 0; max_streak_pnl = 0
    for _, row in tdf.iterrows():
        if row['pnl_usd'] < 0:
            streak += 1
            streak_pnl += row['pnl_usd']
            if streak > max_streak:
                max_streak = streak
                max_streak_pnl = streak_pnl
        else:
            streak = 0; streak_pnl = 0
    print(f"Longest losing streak   : {max_streak} trades   "
          f"(cumulative ${max_streak_pnl:+,.0f})")


def main() -> None:
    print("Loading 1-min NQ data...")
    nq = pd.read_csv(DATA_FILE, parse_dates=["ts"]).set_index("ts").sort_index()
    if nq.index.tz is None:
        nq.index = nq.index.tz_localize("UTC")
    print(f"  bars: {len(nq):,}\n")
    print("Running live-style simulation...")
    trades, eq = run_live_sim(nq)
    print(f"  trades produced: {len(trades):,}\n")
    report(trades, eq)


if __name__ == "__main__":
    main()
