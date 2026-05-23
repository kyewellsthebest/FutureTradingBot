"""Multi-timeframe x entry x target sweep for Fib retrace.

User asked: test every timeframe (1m, 3m, 5m, 10m, 15m), every entry
level (0.1 to 0.9), every target (1.0x to 2.0x leg extension). Looking
for configs that hit 5%+ monthly return with 200+ trades/month.

For each (TF, entry, target):
  - Resample 1-min data to the timeframe
  - Compute pivots and 2HH+2HL trend filter
  - Run live-style sim with realistic limit fills
  - Report trades, WR, PF, total $, max DD, max streak
"""
from __future__ import annotations
import numpy as np, pandas as pd
from collections import defaultdict
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "polygon" / "NQ_1min.csv"

# Account / sizing
STARTING_BALANCE       = 50_000.0
MNQ_PER_PT             = 2.0
COMM_PER_CONTRACT_RT   = 2.0
TARGET_RISK_USD        = 250.0
MAX_CONTRACTS          = 5
MIN_CONTRACTS          = 1

# Strategy (relaxed leg req to allow more trades)
MIN_LEG_PTS            = 25.0       # was 50 — relaxed for more frequency
PIVOT_K                = 3
HTF_PIVOT_K            = 5
MAX_SETUP_AGE_BARS     = 60
MAX_HOLD_BARS          = 240
FILL_WINDOW_BARS       = 10         # 10 bars to fill at any TF


def dynamic_size(stop_pts: float) -> int:
    if stop_pts <= 0:
        return MIN_CONTRACTS
    raw = TARGET_RISK_USD / (stop_pts * MNQ_PER_PT)
    return max(MIN_CONTRACTS, min(MAX_CONTRACTS, int(raw)))


def find_pivots(high: np.ndarray, low: np.ndarray, k: int):
    n = len(high)
    highs, lows = [], []
    for t in range(k, n - k):
        if high[t] == high[t - k:t + k + 1].max():
            highs.append((t, float(high[t])))
        if low[t] == low[t - k:t + k + 1].min():
            lows.append((t, float(low[t])))
    return highs, lows


def simulate_fast(arr: np.ndarray, idx_ns: np.ndarray,
                  entry_pct: float, target_ext: float,
                  pivot_k: int, htf_pivot_k: int,
                  min_leg_pts: float = MIN_LEG_PTS) -> dict:
    """Pure-numpy live-style simulator.
    arr: (n, 4) of [open, high, low, close]
    Returns dict of summary stats.
    """
    h = arr[:, 1]; l = arr[:, 2]; c = arr[:, 3]
    n = len(arr)

    # Find pivots
    raw_h3, raw_l3 = find_pivots(h, l, pivot_k)
    raw_h5, raw_l5 = find_pivots(h, l, htf_pivot_k)
    conf_h3 = defaultdict(list); conf_l3 = defaultdict(list)
    conf_h5 = defaultdict(list); conf_l5 = defaultdict(list)
    for src, px in raw_h3: conf_h3[src + pivot_k].append((src, px))
    for src, px in raw_l3: conf_l3[src + pivot_k].append((src, px))
    for src, px in raw_h5: conf_h5[src + htf_pivot_k].append((src, px))
    for src, px in raw_l5: conf_l5[src + htf_pivot_k].append((src, px))

    cur_h_src, cur_h_px = -1, np.nan
    cur_l_src, cur_l_px = -1, np.nan
    seen_h5: list[tuple[int, float]] = []
    seen_l5: list[tuple[int, float]] = []

    # Setups: list of dicts (lightweight, no class)
    pending: list[dict] = []
    used = set()

    pnls: list[float] = []
    sizes: list[int] = []
    win_flags: list[bool] = []
    holds: list[int] = []
    leg_pts_list: list[float] = []

    active = None  # active trade dict

    for t in range(n):
        for src, px in conf_h3.get(t, []):
            if src > cur_h_src: cur_h_src, cur_h_px = src, px
        for src, px in conf_l3.get(t, []):
            if src > cur_l_src: cur_l_src, cur_l_px = src, px
        for src, px in conf_h5.get(t, []): seen_h5.append((src, px))
        for src, px in conf_l5.get(t, []): seen_l5.append((src, px))

        # check active trade
        if active is not None:
            stop_hit = (active["side"] == "LONG" and l[t] <= active["stop"]) or \
                       (active["side"] == "SHORT" and h[t] >= active["stop"])
            tgt_hit  = (active["side"] == "LONG" and h[t] >= active["target"]) or \
                       (active["side"] == "SHORT" and l[t] <= active["target"])
            exit_px = None
            if stop_hit and tgt_hit:
                exit_px = active["stop"]
            elif stop_hit:
                exit_px = active["stop"]
            elif tgt_hit:
                exit_px = active["target"]
            elif t - active["entry_bar"] >= MAX_HOLD_BARS:
                exit_px = float(c[t])
            if exit_px is not None:
                pnl_pts = (active["entry"] - exit_px) if active["side"] == "SHORT" \
                          else (exit_px - active["entry"])
                pnl = pnl_pts * active["size"] * MNQ_PER_PT \
                      - COMM_PER_CONTRACT_RT * active["size"]
                pnls.append(float(pnl))
                sizes.append(active["size"])
                win_flags.append(pnl > 0)
                holds.append(t - active["entry_bar"])
                leg_pts_list.append(active["leg_pts"])
                active = None

        # process pending setups
        if active is None:
            for s in pending:
                if t < s["created"] + 1: continue
                if t > s["expires"]:
                    s["expires"] = -1; continue
                fill = (s["side"] == "SHORT" and h[t] >= s["entry"]) or \
                       (s["side"] == "LONG"  and l[t] <= s["entry"])
                if not fill: continue
                stop_pts = abs(s["stop"] - s["entry"])
                size = dynamic_size(stop_pts)
                active = {
                    "entry_bar": t, "side": s["side"], "size": size,
                    "entry": s["entry"], "stop": s["stop"],
                    "target": s["target"], "leg_pts": s["leg_pts"],
                }
                used.add((s["ph"], s["pl"]))
                s["expires"] = -1
                break
        pending = [s for s in pending if s["expires"] >= 0]

        # create new setup
        if (cur_h_src >= 0 and cur_l_src >= 0 and cur_h_src != cur_l_src
                and active is None):
            key = (cur_h_src, cur_l_src)
            if key not in used:
                leg = abs(cur_h_px - cur_l_px)
                if leg >= min_leg_pts:
                    p1_src = max(cur_h_src, cur_l_src)
                    if t - (p1_src + pivot_k) <= MAX_SETUP_AGE_BARS:
                        side = "SHORT" if cur_h_src < cur_l_src else "LONG"

                        # 2HH+2HL trend filter
                        trend_ok = False
                        if len(seen_h5) >= 2 and len(seen_l5) >= 2:
                            h1, h0 = seen_h5[-1][1], seen_h5[-2][1]
                            l1, l0 = seen_l5[-1][1], seen_l5[-2][1]
                            if side == "LONG"  and h1 > h0 and l1 > l0:
                                trend_ok = True
                            if side == "SHORT" and h1 < h0 and l1 < l0:
                                trend_ok = True
                        if not trend_ok:
                            used.add(key); continue

                        # entry / stop / target
                        if side == "SHORT":
                            entry_px  = float(cur_l_px) + entry_pct  * leg
                            stop_px   = float(cur_h_px)
                            target_px = float(cur_l_px) - target_ext * leg
                        else:
                            entry_px  = float(cur_h_px) - entry_pct  * leg
                            stop_px   = float(cur_l_px)
                            target_px = float(cur_h_px) + target_ext * leg

                        # skip if already past entry
                        if side == "SHORT" and h[t] >= entry_px:
                            used.add(key); continue
                        if side == "LONG"  and l[t] <= entry_px:
                            used.add(key); continue

                        pending.append({
                            "side": side, "ph": cur_h_src, "pl": cur_l_src,
                            "entry": entry_px, "stop": stop_px,
                            "target": target_px, "leg_pts": leg,
                            "created": t,
                            "expires": t + MAX_SETUP_AGE_BARS,
                        })
                        used.add(key)

    # Summary stats
    if not pnls:
        return {"n": 0}
    arr_pnl = np.array(pnls)
    wins_count = int(arr_pnl.gt(0).sum() if hasattr(arr_pnl, 'gt') else (arr_pnl > 0).sum())
    gw = float(arr_pnl[arr_pnl > 0].sum())
    gl = float(abs(arr_pnl[arr_pnl < 0].sum()))
    cum = np.cumsum(arr_pnl)
    peak = np.maximum.accumulate(cum)
    maxdd = float((cum - peak).min())
    # longest losing streak
    streak = max_streak = 0
    for w in win_flags:
        if not w:
            streak += 1
            if streak > max_streak: max_streak = streak
        else:
            streak = 0
    # size distribution
    sizes_arr = np.array(sizes)
    size_counts = {sz: int((sizes_arr == sz).sum()) for sz in range(1, 6)}
    size_wins = {sz: 0 for sz in range(1, 6)}
    for s, w in zip(sizes, win_flags):
        if w: size_wins[s] = size_wins.get(s, 0) + 1

    return {
        "n": len(pnls),
        "wr": wins_count / len(pnls),
        "pf": gw / gl if gl > 0 else float("inf"),
        "total": float(arr_pnl.sum()),
        "per": float(arr_pnl.mean()),
        "maxdd": maxdd,
        "max_streak": max_streak,
        "size_counts": size_counts,
        "size_wins": size_wins,
        "avg_hold": float(np.mean(holds)) if holds else 0,
        "avg_leg": float(np.mean(leg_pts_list)) if leg_pts_list else 0,
    }


def resample(nq: pd.DataFrame, freq: str) -> pd.DataFrame:
    if freq == "1min":
        return nq
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    return nq.resample(freq).agg(agg).dropna()


def main() -> None:
    print("Loading data...")
    nq = pd.read_csv(DATA_FILE, parse_dates=["ts"]).set_index("ts").sort_index()
    if nq.index.tz is None:
        nq.index = nq.index.tz_localize("UTC")
    print(f"  bars (1m): {len(nq):,}\n")

    cal_days = (nq.index[-1] - nq.index[0]).days
    months = cal_days / 30.44

    timeframes = ["1min", "3min", "5min", "10min", "15min"]
    entries = [0.20, 0.30, 0.382, 0.50, 0.618, 0.70, 0.80]
    target_exts = [0.0, 0.272, 0.50, 0.618, 1.0]

    print(f"Sweeping {len(timeframes)} TFs x {len(entries)} entries x "
          f"{len(target_exts)} targets = {len(timeframes)*len(entries)*len(target_exts)} configs\n")

    all_results = []
    for tf in timeframes:
        df = resample(nq, tf)
        arr = df[["open", "high", "low", "close"]].to_numpy()
        idx_ns = df.index.asi8 if hasattr(df.index, 'asi8') else df.index.astype('int64').to_numpy()
        print(f"\n--- Timeframe: {tf}  (bars: {len(df):,}) ---")
        print(f"{'Entry':>6} {'Target':>9} {'Trades':>7} {'/mo':>5} "
              f"{'WR':>6} {'PF':>5} {'$/tr':>7} {'Total':>9} {'MaxDD':>9} "
              f"{'Streak':>7} {'Return%':>8}")
        for e in entries:
            for tx in target_exts:
                stats = simulate_fast(arr, idx_ns, e, tx, PIVOT_K, HTF_PIVOT_K)
                if stats["n"] < 10:
                    continue
                ret_pct = stats["total"] / STARTING_BALANCE * 100
                ret_per_mo = ret_pct / months
                pf = f"{stats['pf']:>4.2f}" if stats['pf'] < 99 else " inf"
                tag = ""
                if ret_per_mo >= 5.0 and stats["n"] / months >= 100:
                    tag = " ★★★ HITS TARGET"
                elif ret_per_mo >= 2.0:
                    tag = " ★ good"
                elif stats["total"] > 0:
                    tag = " +"
                print(f"{e:>6.3f} {1.0+tx:>7.3g}x {stats['n']:>7} "
                      f"{stats['n']/months:>4.1f} "
                      f"{stats['wr']*100:>5.1f}% {pf} "
                      f"${stats['per']:>+5,.0f} ${stats['total']:>+7,.0f} "
                      f"${stats['maxdd']:>+7,.0f} {stats['max_streak']:>6} "
                      f"{ret_per_mo:>+5.2f}%{tag}")
                all_results.append({
                    "tf": tf, "entry": e, "target_ext": tx,
                    "n": stats["n"], "wr": stats["wr"], "pf": stats["pf"],
                    "total": stats["total"], "per": stats["per"],
                    "maxdd": stats["maxdd"], "streak": stats["max_streak"],
                    "ret_per_mo": ret_per_mo,
                    "trades_per_mo": stats["n"] / months,
                })

    print("\n\n" + "=" * 110)
    print("TOP 15 CONFIGS BY MONTHLY RETURN (min 50 trades total)")
    print("=" * 110)
    all_results.sort(key=lambda x: -x["ret_per_mo"])
    print(f"{'TF':>6} {'Entry':>6} {'Target':>8} {'Trades':>7} {'/mo':>5} "
          f"{'WR':>6} {'PF':>5} {'$/tr':>7} {'Total':>9} {'MaxDD':>9} "
          f"{'Streak':>7} {'Ret/mo':>7}")
    print("-" * 110)
    for r in all_results[:15]:
        if r["n"] < 50: continue
        pf = f"{r['pf']:>4.2f}" if r['pf'] < 99 else " inf"
        print(f"{r['tf']:>6} {r['entry']:>6.3f} {1+r['target_ext']:>6.3g}x "
              f"{r['n']:>7} {r['trades_per_mo']:>4.1f} "
              f"{r['wr']*100:>5.1f}% {pf} ${r['per']:>+5,.0f} "
              f"${r['total']:>+7,.0f} ${r['maxdd']:>+7,.0f} "
              f"{r['streak']:>6} {r['ret_per_mo']:>+5.2f}%")

    # Configs hitting the 5%/mo target
    print("\n" + "=" * 110)
    print("CONFIGS HITTING USER TARGET (≥5%/mo AND ≥100 trades/mo)")
    print("=" * 110)
    targets = [r for r in all_results
               if r["ret_per_mo"] >= 5.0 and r["trades_per_mo"] >= 100]
    if not targets:
        print("  None.")
    for r in targets:
        pf = f"{r['pf']:>4.2f}" if r['pf'] < 99 else " inf"
        print(f"  {r['tf']:>6} E={r['entry']:.3f} T={1+r['target_ext']:.3g}x  "
              f"{r['trades_per_mo']:.1f}/mo  WR={r['wr']*100:.1f}%  "
              f"PF={r['pf']:.2f}  ${r['per']:+.0f}/tr  "
              f"${r['total']:+,.0f}  DD${r['maxdd']:+,.0f}  "
              f"streak={r['streak']}  RETURN: {r['ret_per_mo']:+.2f}%/mo")


if __name__ == "__main__":
    main()
