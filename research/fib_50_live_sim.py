"""LIVE-style simulation of the Fib 50% bot with NET-DISP trend filter and
ARM-REJECT entry. Walks the 2-yr Polygon NQ 1-min history bar-by-bar,
only ever showing the bot information it would have in real time.

NO LOOK-AHEAD anywhere:
  - Pivots: only counted as known once k bars after they formed have closed
  - Trend (NET-DISP): only uses bars whose close has already happened
  - ARM-REJECT: requires the arming bar to fully close before placing the
    limit order at level50
  - Limit fill: only happens when a subsequent bar's high/low actually
    touches level50 (limit didn't exist before then)
  - Stop / target: checked intrabar (any tick can trigger)
  - Dynamic sizing: chosen at trade-open time, based on dollar risk

Reports:
  - Trades / day, trades / month
  - Trade-size distribution (1-5 MNQ) and wins at each size
  - Monthly P&L breakdown ($ and %)
  - Max 1-day drawdown
  - Max rolling 7-day drawdown
  - Equity curve summary
"""
from __future__ import annotations
import numpy as np, pandas as pd
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "polygon" / "NQ_1min.csv"

# === Strategy parameters ====================================================
PIVOT_K              = 3        # confirmed swing pivots on 1-min
MIN_LEG_PTS          = 25.0     # ignore tiny legs
MIN_ENTRY_RISK_FRAC  = 0.25     # entry must leave >=25% of leg as risk-room
MAX_HOLD_BARS        = 120      # 2-hr hard cap
MAX_SETUP_AGE_BARS   = 60       # setup expires 60 min after pivot

# Trend filter (NET-DISP)
TREND_LOOKBACK_BARS  = 30
TREND_MIN_RATIO      = 0.40

# Entry mechanic
USE_ARM_REJECT       = True     # require arming bar's close inside the leg
FILL_WINDOW_BARS     = 5        # how many bars to wait for level50 retouch

# === Sizing & accounting ====================================================
STARTING_BALANCE     = 50_000.0
MNQ_PER_PT           = 2.0      # $2/point per MNQ
COMM_PER_CONTRACT_RT = 2.0      # ~$2 round-trip per MNQ (5 MNQ = $10)
TARGET_RISK_USD      = 250.0    # try to risk ~0.5% per trade ($250 on $50k)
MAX_CONTRACTS        = 5
MIN_CONTRACTS        = 1


def dynamic_size(stop_pts: float) -> int:
    """Pick MNQ size so dollar risk is closest to TARGET_RISK_USD without
    exceeding it. Clamp to [MIN_CONTRACTS, MAX_CONTRACTS]."""
    if stop_pts <= 0:
        return MIN_CONTRACTS
    raw = TARGET_RISK_USD / (stop_pts * MNQ_PER_PT)
    n = int(raw)            # floor — never exceed target risk
    return max(MIN_CONTRACTS, min(MAX_CONTRACTS, n))


# === Pivot helpers ==========================================================
def find_pivots(high: np.ndarray, low: np.ndarray, k: int):
    """One-shot computation — same logic the live bot uses but pre-computed."""
    n = len(high)
    highs, lows = [], []
    for t in range(k, n - k):
        if high[t] == high[t - k:t + k + 1].max():
            highs.append((t, float(high[t])))
        if low[t] == low[t - k:t + k + 1].min():
            lows.append((t, float(low[t])))
    return highs, lows


# === Live-style simulator ===================================================
@dataclass
class Setup:
    side: str
    pivot_high_idx: int
    pivot_low_idx: int
    pivot_high_px: float
    pivot_low_px:  float
    level50: float
    armed_at_bar: int = -1       # bar where high/low first touched level50
    arming_bar_close_seen: bool = False
    confirmed: bool = False       # arming bar closed back inside leg
    fill_deadline_bar: int = -1


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


def run_live_sim(nq: pd.DataFrame) -> tuple[list[Trade], pd.Series]:
    """Bar-by-bar simulation. Returns trades + equity series (per-bar)."""
    h = nq["high"].to_numpy()
    l = nq["low"].to_numpy()
    o = nq["open"].to_numpy()
    c = nq["close"].to_numpy()
    n = len(nq)
    idx = nq.index

    # Pre-compute pivots — but mark each as KNOWN only at idx+PIVOT_K
    raw_highs, raw_lows = find_pivots(h, l, PIVOT_K)
    # "confirmed_at[i]" = list of (src_idx, px) pivots that become known on bar i
    confirmed_highs_at: dict[int, list[tuple[int, float]]] = defaultdict(list)
    confirmed_lows_at: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for src, px in raw_highs:
        confirmed_highs_at[src + PIVOT_K].append((src, px))
    for src, px in raw_lows:
        confirmed_lows_at[src + PIVOT_K].append((src, px))

    # Most-recent confirmed pivot tracker
    cur_h_src, cur_h_px = -1, np.nan
    cur_l_src, cur_l_px = -1, np.nan

    # State
    pending_setups: list[Setup] = []
    used_setup_keys: set[tuple[int, int]] = set()
    trades: list[Trade] = []
    active_trade: Trade | None = None
    equity = STARTING_BALANCE
    equity_curve = np.zeros(n)

    for t in range(n):
        # --- update confirmed-pivot tracker (bar t close happened) -------
        for src, px in confirmed_highs_at.get(t, []):
            if src > cur_h_src:
                cur_h_src, cur_h_px = src, px
        for src, px in confirmed_lows_at.get(t, []):
            if src > cur_l_src:
                cur_l_src, cur_l_px = src, px

        # --- check active trade for stop / target / timeout --------------
        if active_trade is not None:
            tr = active_trade
            stop_hit = (tr.side == "LONG" and l[t] <= tr.stop_px) or \
                       (tr.side == "SHORT" and h[t] >= tr.stop_px)
            tgt_hit = (tr.side == "LONG" and h[t] >= tr.target_px) or \
                      (tr.side == "SHORT" and l[t] <= tr.target_px)
            exit_now = False
            if stop_hit and tgt_hit:
                # both in same bar — conservatively assume stop hits first
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

        # --- update existing pending setups ------------------------------
        if active_trade is None:
            for s in pending_setups:
                # check arming (high / low touches level50)
                if s.armed_at_bar < 0:
                    if s.side == "SHORT" and h[t] >= s.level50:
                        s.armed_at_bar = t
                    elif s.side == "LONG" and l[t] <= s.level50:
                        s.armed_at_bar = t
                # check ARM-REJECT confirmation (arming bar must close back
                # inside the leg)
                if s.armed_at_bar == t and not s.arming_bar_close_seen:
                    # bar t just closed — we can now check
                    s.arming_bar_close_seen = True
                    arm_close = float(c[t])
                    if USE_ARM_REJECT:
                        bad = (s.side == "SHORT" and arm_close >= s.level50) \
                           or (s.side == "LONG"  and arm_close <= s.level50)
                        if bad:
                            s.armed_at_bar = -1
                            s.arming_bar_close_seen = False
                            continue
                    s.confirmed = True
                    s.fill_deadline_bar = t + FILL_WINDOW_BARS
                # if confirmed and we're past the arming bar, check for
                # level50 retouch (limit fill) on each subsequent bar
                elif s.confirmed and t > s.armed_at_bar:
                    # check stop invalidation (price hit pivot before retouch)
                    stop_hit = (s.side == "SHORT" and h[t] >= s.pivot_high_px) \
                            or (s.side == "LONG"  and l[t] <= s.pivot_low_px)
                    if stop_hit:
                        s.armed_at_bar = -1
                        s.confirmed = False
                        continue
                    retouch = (s.side == "SHORT" and h[t] >= s.level50) \
                           or (s.side == "LONG"  and l[t] <= s.level50)
                    if retouch:
                        # Fire the trade
                        side = s.side
                        entry_px = float(s.level50)
                        stop_px = s.pivot_high_px if side == "SHORT" \
                                                  else s.pivot_low_px
                        target_px = s.pivot_low_px if side == "SHORT" \
                                                   else s.pivot_high_px
                        stop_pts = abs(stop_px - entry_px)
                        size = dynamic_size(stop_pts)
                        active_trade = Trade(
                            entry_bar=t, exit_bar=-1,
                            entry_ts=idx[t], exit_ts=idx[t],
                            side=side, size=size,
                            entry_px=entry_px, stop_px=stop_px,
                            target_px=target_px, exit_px=0.0,
                            exit_reason="", pnl_usd=0.0,
                        )
                        used_setup_keys.add((s.pivot_high_idx, s.pivot_low_idx))
                        s.confirmed = False  # mark done
                        break
                    elif t > s.fill_deadline_bar:
                        s.confirmed = False  # expired without fill

        # --- prune dead setups -------------------------------------------
        pending_setups = [
            s for s in pending_setups
            if s.confirmed or s.armed_at_bar < 0
        ]
        # drop setups that have aged out
        pending_setups = [
            s for s in pending_setups
            if t - (max(s.pivot_high_idx, s.pivot_low_idx) + PIVOT_K)
               <= MAX_SETUP_AGE_BARS
        ]

        # --- generate new setup from latest confirmed pivots -------------
        if (cur_h_src >= 0 and cur_l_src >= 0 and cur_h_src != cur_l_src
                and active_trade is None):
            key = (cur_h_src, cur_l_src)
            if key not in used_setup_keys:
                leg = abs(cur_h_px - cur_l_px)
                if leg >= MIN_LEG_PTS:
                    p1_src = max(cur_h_src, cur_l_src)
                    if t - (p1_src + PIVOT_K) <= MAX_SETUP_AGE_BARS:
                        # only LONG when leg is up, SHORT when leg is down
                        if cur_h_src < cur_l_src:  # down-leg → SHORT setup
                            side = "SHORT"
                        else:                       # up-leg → LONG setup
                            side = "LONG"
                        level50 = (cur_h_px + cur_l_px) / 2.0

                        # ----- TREND FILTER (NET-DISP, no look-ahead) ----
                        lo = max(0, t - TREND_LOOKBACK_BARS + 1)
                        # use only bars 0..t (already closed)
                        if t - lo >= 5:    # need enough bars
                            net_move = c[t] - c[lo]
                            rng = h[lo:t+1].max() - l[lo:t+1].min()
                            if rng > 0:
                                ratio = net_move / rng
                                trend_ok = False
                                if side == "LONG"  and ratio >  TREND_MIN_RATIO:
                                    trend_ok = True
                                if side == "SHORT" and ratio < -TREND_MIN_RATIO:
                                    trend_ok = True
                                # ----- entry-risk sanity check -----------
                                stop_px_check = cur_h_px if side == "SHORT" else cur_l_px
                                risk_check = abs(stop_px_check - level50)
                                if trend_ok and risk_check >= leg * MIN_ENTRY_RISK_FRAC \
                                            and not any(s.pivot_high_idx == cur_h_src
                                                        and s.pivot_low_idx == cur_l_src
                                                        for s in pending_setups):
                                    pending_setups.append(Setup(
                                        side=side,
                                        pivot_high_idx=cur_h_src,
                                        pivot_low_idx=cur_l_src,
                                        pivot_high_px=cur_h_px,
                                        pivot_low_px=cur_l_px,
                                        level50=level50,
                                    ))

        equity_curve[t] = equity

    eq_series = pd.Series(equity_curve, index=idx, name="equity")
    return trades, eq_series


# === Reporting ==============================================================
def report(trades: list[Trade], eq: pd.Series) -> None:
    n_trades = len(trades)
    if n_trades == 0:
        print("No trades."); return
    tdf = pd.DataFrame([t.__dict__ for t in trades])
    tdf["entry_ts"] = pd.to_datetime(tdf["entry_ts"])
    tdf["exit_ts"]  = pd.to_datetime(tdf["exit_ts"])
    tdf["date"]     = tdf["entry_ts"].dt.tz_convert("America/New_York").dt.date
    tdf["month"]    = tdf["entry_ts"].dt.tz_convert("America/New_York").dt.to_period("M")
    tdf["win"]      = tdf["pnl_usd"] > 0

    days_traded = tdf["date"].nunique()
    cal_days = (eq.index[-1] - eq.index[0]).days
    cal_months = cal_days / 30.44
    print("=" * 78)
    print("LIVE-STYLE BACKTEST  —  NET-DISP trend filter + ARM-REJECT entry")
    print("=" * 78)
    print(f"Period          : {eq.index[0].date()} → {eq.index[-1].date()}  "
          f"({cal_days} cal days, ~{cal_months:.1f} mo)")
    print(f"Starting equity : ${STARTING_BALANCE:>10,.0f}")
    print(f"Ending equity   : ${eq.iloc[-1]:>10,.0f}")
    print(f"Net P&L         : ${eq.iloc[-1] - STARTING_BALANCE:>+10,.0f}")
    pct = (eq.iloc[-1] / STARTING_BALANCE - 1) * 100
    print(f"Return          : {pct:>+10.1f}%   over {cal_months:.1f} months "
          f"→ {pct / cal_months:>+5.2f}% / month")
    print()
    print(f"Total trades         : {n_trades}")
    print(f"  per trading day    : {n_trades / days_traded:>5.1f}")
    print(f"  per calendar day   : {n_trades / cal_days:>5.1f}")
    print(f"  per month          : {n_trades / cal_months:>5.1f}")
    wins = int(tdf['win'].sum())
    print(f"Wins / Losses        : {wins} / {n_trades - wins}  "
          f"({wins / n_trades * 100:.1f}% win rate)")
    gw = float(tdf[tdf['win']]['pnl_usd'].sum())
    gl = float(abs(tdf[~tdf['win']]['pnl_usd'].sum()))
    pf = gw / gl if gl > 0 else float('inf')
    print(f"Profit factor        : {pf:.2f}   (wins ${gw:,.0f} / losses ${gl:,.0f})")
    print(f"Avg win / loss       : ${tdf[tdf['win']]['pnl_usd'].mean():>+6,.0f} / "
          f"${tdf[~tdf['win']]['pnl_usd'].mean():>+6,.0f}")

    # Size breakdown
    print(f"\n{'POSITION-SIZE BREAKDOWN':^78}")
    print("-" * 78)
    print(f"{'Size':>6} | {'Trades':>7} | {'Wins':>5} | {'Losses':>7} | "
          f"{'WR':>6} | {'$ won':>10} | {'$ lost':>10} | {'Net':>10}")
    for sz in range(1, MAX_CONTRACTS + 1):
        g = tdf[tdf["size"] == sz]
        if len(g) == 0:
            print(f"{sz:>5} M | {'—':>7} | {'—':>5} | {'—':>7} | "
                  f"{'—':>6} | {'—':>10} | {'—':>10} | {'—':>10}")
            continue
        w = int(g['win'].sum())
        wr = w / len(g) * 100
        wd = float(g[g['win']]['pnl_usd'].sum())
        ld = float(g[~g['win']]['pnl_usd'].sum())
        print(f"{sz:>5} M | {len(g):>7} | {w:>5} | {len(g)-w:>7} | "
              f"{wr:>5.1f}% | ${wd:>+8,.0f} | ${ld:>+8,.0f} | ${wd+ld:>+8,.0f}")

    # Monthly breakdown
    print(f"\n{'MONTHLY P&L':^78}")
    print("-" * 78)
    print(f"{'Month':<10} {'Trades':>7} {'Wins':>5} {'WR':>6} "
          f"{'P&L $':>10} {'Return %':>10} {'End equity':>12}")
    monthly = tdf.groupby("month").agg(
        trades=("pnl_usd", "size"),
        wins=("win", "sum"),
        pnl=("pnl_usd", "sum"),
    )
    eq_per_month = eq.resample("ME").last()
    eq_per_month.index = eq_per_month.index.to_period("M")
    starting = STARTING_BALANCE
    for m, row in monthly.iterrows():
        end_eq = float(eq_per_month.get(m, starting + row["pnl"]))
        ret = row["pnl"] / starting * 100
        wr = row["wins"] / row["trades"] * 100
        print(f"{str(m):<10} {int(row['trades']):>7} {int(row['wins']):>5} "
              f"{wr:>5.1f}% ${row['pnl']:>+8,.0f} {ret:>+8.2f}% "
              f"${end_eq:>10,.0f}")
        starting = end_eq

    # Drawdowns
    print(f"\n{'DRAWDOWNS':^78}")
    print("-" * 78)
    # 1-day drawdown: worst single-day P&L
    daily_pnl = tdf.groupby("date")["pnl_usd"].sum()
    worst_day = daily_pnl.min()
    worst_day_date = daily_pnl.idxmin()
    best_day = daily_pnl.max()
    best_day_date = daily_pnl.idxmax()
    print(f"Worst single trading day : ${worst_day:>+10,.0f} on {worst_day_date}")
    print(f"Best  single trading day : ${best_day:>+10,.0f} on {best_day_date}")
    # 7-day rolling drawdown
    daily_pnl_full = daily_pnl.reindex(
        pd.date_range(daily_pnl.index.min(), daily_pnl.index.max()),
        fill_value=0,
    )
    rolling_7d = daily_pnl_full.rolling(7).sum()
    worst_week = rolling_7d.min()
    worst_week_end = rolling_7d.idxmin()
    print(f"Worst rolling 7-day P&L  : ${worst_week:>+10,.0f} ending {worst_week_end.date()}")
    # equity-curve max drawdown
    running_peak = eq.cummax()
    dd = eq - running_peak
    max_dd = dd.min()
    max_dd_at = dd.idxmin()
    print(f"Max equity drawdown      : ${max_dd:>+10,.0f} on {max_dd_at.date()}")
    print(f"  (peak ${running_peak.loc[max_dd_at]:,.0f} → trough ${eq.loc[max_dd_at]:,.0f})")

    # Hold time distribution
    holds = (tdf["exit_bar"] - tdf["entry_bar"]).astype(int)
    print(f"\n{'HOLD-TIME DISTRIBUTION (minutes)':^78}")
    print("-" * 78)
    bins = [(0, 1, "≤1m"), (1, 5, "1-5m"), (5, 15, "5-15m"),
            (15, 30, "15-30m"), (30, 60, "30-60m"), (60, 1000, ">60m")]
    for lo, hi, lab in bins:
        c = int(((holds > lo) & (holds <= hi)).sum())
        pct = c / n_trades * 100
        print(f"  {lab:>7} : {c:>4}  ({pct:>4.1f}%)")


def main() -> None:
    print("Loading 1-min NQ data...")
    nq = pd.read_csv(DATA_FILE, parse_dates=["ts"]).set_index("ts").sort_index()
    if nq.index.tz is None:
        nq.index = nq.index.tz_localize("UTC")
    print(f"  bars: {len(nq):,}\n")
    print("Running live-style simulation (this takes ~1 min)...")
    trades, eq = run_live_sim(nq)
    print(f"  trades produced: {len(trades):,}\n")
    report(trades, eq)


if __name__ == "__main__":
    main()
