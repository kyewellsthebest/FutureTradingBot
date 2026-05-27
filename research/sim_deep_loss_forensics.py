"""Deep loss forensics — for each trade, examine the LAST 5 BARS before
the signal fired. Find specific micro-patterns that distinguish losers
from winners. Build rules from the most discriminating patterns. Test
predictability OOS.

This is the version the user wanted: not aggregate buckets, but
"why specifically did THIS losing trade lose? what pattern was visible
BEFORE entry that distinguishes it from winners?"

Approach:
  1. Categorise the 5 bars before each signal into microstructure features:
     - body% of each bar (full body vs full range)
     - direction of each bar (up/down close vs open)
     - wick rejection at the entry price level
     - volume profile (last-bar vs prior-5-bar average)
     - cumulative move of those 5 bars (drift vs impulse)
     - body distribution (concentrated vs spread)
     - "exhaustion" signal: was there a long wick AGAINST the impulse on bar -1?
  2. For each feature: compute WR among trades with that condition
  3. Find feature COMBINATIONS where WR < 30% (vs baseline ~37%)
  4. Build rules from top discriminating patterns
  5. Test predictability with OOS split
"""
from __future__ import annotations
import json, time
from pathlib import Path
import numpy as np
import pandas as pd

from research.sim_strategy_bakeoff_tick import (
    build_1m_bars, simulate, baseline_setups, score, STARTING_BAL
)
from research.sim_loss_forensics import find_losing_streaks

SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")
OUT = Path("/home/user/HFTBot/reports/deep_loss_forensics.json")


# ----------------------------------------------------------------------
# Per-trade microstructure features (last 5 bars before signal)
# ----------------------------------------------------------------------
def extract_micro_features(bars: pd.DataFrame, trades: list, base_setups: list) -> pd.DataFrame:
    o = bars["open"].to_numpy(); h = bars["high"].to_numpy()
    l = bars["low"].to_numpy();  c = bars["close"].to_numpy()
    v = bars["volume"].to_numpy()
    bar_ts = bars.index.astype("int64").to_numpy()

    # Map signal_ts -> trade outcome
    setup_by_sig = {s["sig_ts"]: s for s in base_setups}
    trade_by_sig = {}
    for t in trades:
        # Find the setup whose signal was within 5min before this trade's entry
        candidates = [s for s in base_setups
                      if s["sig_ts"] <= t["entry_ts"]
                      and s["sig_ts"] >= t["entry_ts"] - 300 * 1_000_000_000]
        if candidates:
            best = max(candidates, key=lambda s: s["sig_ts"])
            trade_by_sig[best["sig_ts"]] = t

    rows = []
    for sig_ts, s in setup_by_sig.items():
        i = int(np.searchsorted(bar_ts, sig_ts, side="left")) - 1
        if i < 6:
            continue
        # signal_bar = i (last closed bar before sig_ts emit)
        # last 5 bars = i-4 .. i inclusive
        feats = {"sig_ts": sig_ts, "side": int(s["side"]),
                 "entry_px": float(s["entry_px"]),
                 "stop_px": float(s["stop_px"]),
                 "target_px": float(s["target_px"])}

        # Per-bar microstructure for last 5 bars
        for k in range(5):
            idx = i - 4 + k   # idx 0 = bar -5 ... idx 4 = signal bar
            bo, bh, bl, bc, bv = o[idx], h[idx], l[idx], c[idx], v[idx]
            body = abs(bc - bo)
            rng = bh - bl if bh > bl else 1e-9
            body_pct = body / rng
            direction = 1 if bc > bo else (-1 if bc < bo else 0)
            # Wick rejection: how big is the wick on the SIGNAL side?
            #   for a LONG setup the signal side is "rejection from down" = lower wick
            #   for a SHORT setup it's upper wick
            if s["side"] == 1:
                wick_reject = (min(bo, bc) - bl) / rng    # lower wick %
            else:
                wick_reject = (bh - max(bo, bc)) / rng    # upper wick %
            feats[f"b{k+1}_body_pct"] = round(float(body_pct), 3)
            feats[f"b{k+1}_direction"] = int(direction)
            feats[f"b{k+1}_wick_reject"] = round(float(wick_reject), 3)
            feats[f"b{k+1}_vol"] = float(bv)

        # Same-side body run: how many of last 3 bars closed in IMPULSE direction
        last_3_dirs = [feats[f"b{k}_direction"] for k in (3, 4, 5)]
        # Impulse direction = same as setup side (LONG setup means impulse was UP)
        same_dir = sum(1 for d in last_3_dirs if d == s["side"])
        feats["last3_with_impulse"] = same_dir

        # Average body% of last 3 bars (clean trend vs choppy)
        feats["avg_body3"] = round(float(np.mean([feats[f"b{k}_body_pct"] for k in (3,4,5)])), 3)

        # Volume spike on signal bar vs prior 4
        prior_vols = [feats[f"b{k}_vol"] for k in (1,2,3,4)]
        feats["sigbar_vol_ratio"] = round(float(feats["b5_vol"] / max(np.mean(prior_vols), 1)), 2)

        # Wick rejection on signal bar (last bar) -- key exhaustion tell
        # We want to know: did the bar BEFORE signal show rejection in our favor?
        feats["sigbar_wick_reject"] = feats["b5_wick_reject"]

        # Cumulative move during last 5 bars (impulse strength)
        five_bar_move = c[i] - c[i - 5]
        feats["move_5bar"] = round(float(five_bar_move), 1)
        feats["move_5bar_with_impulse"] = round(float(five_bar_move * s["side"]), 1)

        # Outcome
        t = trade_by_sig.get(sig_ts)
        if t is None:
            feats["outcome"] = None
            feats["pnl"] = 0
            feats["loser"] = None
        else:
            feats["outcome"] = t["reason"]
            feats["pnl"] = float(t["pnl_usd"])
            feats["loser"] = int(t["pnl_usd"] < 0)
        rows.append(feats)
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------
# Find micro-patterns: feature buckets where WR significantly diverges
# ----------------------------------------------------------------------
def discover_patterns(df: pd.DataFrame):
    """For each binary/categorical feature, compute WR. Surface patterns
    where WR < 30% (significantly below the 37% baseline) or > 50%."""
    df = df.dropna(subset=["loser"]).copy()
    overall = float((1 - df["loser"]).mean())
    n_total = len(df)
    print(f"Overall trades: {n_total}, baseline WR: {overall*100:.1f}%\n")

    patterns = []

    # Pattern 1: bar BEFORE signal had a long body AGAINST the impulse
    # (bar 4 since signal is bar 5)
    df["b4_against"] = ((df["b4_direction"] != df["side"]) & (df["b4_body_pct"] > 0.6)).astype(int)
    p1 = df.groupby("b4_against").agg(n=("loser","count"), wr=("loser", lambda x: 1-x.mean()), pnl=("pnl","sum")).round(3)
    print(f"Pattern: bar-2 had >60% body AGAINST impulse direction")
    print(p1, "\n")
    patterns.append(("bar-2_against_>60body", p1.to_dict()))

    # Pattern 2: signal bar (last bar) closed AGAINST impulse direction
    df["sigbar_against"] = (df["b5_direction"] != df["side"]).astype(int)
    p2 = df.groupby("sigbar_against").agg(n=("loser","count"), wr=("loser", lambda x: 1-x.mean()), pnl=("pnl","sum")).round(3)
    print(f"Pattern: signal bar (last bar) closed AGAINST impulse direction")
    print(p2, "\n")
    patterns.append(("sigbar_against_impulse", p2.to_dict()))

    # Pattern 3: ALL last 3 bars closed in impulse direction (no pause)
    df["all3_with_impulse"] = (df["last3_with_impulse"] == 3).astype(int)
    p3 = df.groupby("all3_with_impulse").agg(n=("loser","count"), wr=("loser", lambda x: 1-x.mean()), pnl=("pnl","sum")).round(3)
    print(f"Pattern: ALL last 3 bars closed in impulse direction (no pause yet)")
    print(p3, "\n")
    patterns.append(("all3_with_impulse", p3.to_dict()))

    # Pattern 4: Signal bar has high body% and runs with impulse (momentum lock)
    df["sigbar_momentum"] = ((df["b5_direction"] == df["side"]) & (df["b5_body_pct"] > 0.7)).astype(int)
    p4 = df.groupby("sigbar_momentum").agg(n=("loser","count"), wr=("loser", lambda x: 1-x.mean()), pnl=("pnl","sum")).round(3)
    print(f"Pattern: signal bar >70% body in impulse dir (momentum lock)")
    print(p4, "\n")
    patterns.append(("sigbar_momentum_lock", p4.to_dict()))

    # Pattern 5: 5-bar move is unusually large in impulse direction (overextension)
    df["overextended"] = (df["move_5bar_with_impulse"] > 15).astype(int)
    p5 = df.groupby("overextended").agg(n=("loser","count"), wr=("loser", lambda x: 1-x.mean()), pnl=("pnl","sum")).round(3)
    print(f"Pattern: 5-bar net move > 15pt in impulse direction (overextended)")
    print(p5, "\n")
    patterns.append(("overextended_15", p5.to_dict()))

    df["overextended20"] = (df["move_5bar_with_impulse"] > 20).astype(int)
    p5b = df.groupby("overextended20").agg(n=("loser","count"), wr=("loser", lambda x: 1-x.mean()), pnl=("pnl","sum")).round(3)
    print(f"Pattern: 5-bar net move > 20pt in impulse direction (very extended)")
    print(p5b, "\n")
    patterns.append(("overextended_20", p5b.to_dict()))

    # Pattern 6: low body% on last 3 bars (chop signal)
    df["choppy"] = (df["avg_body3"] < 0.35).astype(int)
    p6 = df.groupby("choppy").agg(n=("loser","count"), wr=("loser", lambda x: 1-x.mean()), pnl=("pnl","sum")).round(3)
    print(f"Pattern: avg body% of last 3 bars < 0.35 (choppy)")
    print(p6, "\n")
    patterns.append(("choppy_last3", p6.to_dict()))

    # Pattern 7: Volume spike on signal bar (news event?)
    df["vol_spike2x"] = (df["sigbar_vol_ratio"] > 2).astype(int)
    p7 = df.groupby("vol_spike2x").agg(n=("loser","count"), wr=("loser", lambda x: 1-x.mean()), pnl=("pnl","sum")).round(3)
    print(f"Pattern: signal bar volume > 2x avg of prior 4")
    print(p7, "\n")
    patterns.append(("vol_spike_2x", p7.to_dict()))

    # Pattern 8: Wick rejection IN FAVOR on signal bar (good entry)
    df["wick_favor"] = (df["sigbar_wick_reject"] > 0.4).astype(int)
    p8 = df.groupby("wick_favor").agg(n=("loser","count"), wr=("loser", lambda x: 1-x.mean()), pnl=("pnl","sum")).round(3)
    print(f"Pattern: signal bar has >40% wick rejection in our favor")
    print(p8, "\n")
    patterns.append(("wick_favor_40", p8.to_dict()))

    return df, patterns


# ----------------------------------------------------------------------
# Build candidate rules + test
# ----------------------------------------------------------------------
def test_rule(bars, base_setups, price, ts_ns, period_days, rule_fn, label):
    bar_ts = bars.index.astype("int64").to_numpy()
    filtered = []
    for s in base_setups:
        i = int(np.searchsorted(bar_ts, s["sig_ts"], side="left")) - 1
        if i < 6:
            filtered.append(s); continue
        if rule_fn(bars, i, s):
            filtered.append(s)
    trades = simulate(filtered, price, ts_ns)
    if not trades:
        print(f"{label}: NO TRADES")
        return
    pnls = np.array([t["pnl_usd"] for t in trades])
    wins = pnls[pnls > 0]
    cum = pnls.cumsum()
    maxdd = float((cum - np.maximum.accumulate(cum)).min())
    months = period_days / 30.44
    st = find_losing_streaks(trades)
    print(f"{label:<55} n={len(trades):>5} WR={len(wins)/len(pnls)*100:>4.1f}% "
          f"ret={float(pnls.sum())/STARTING_BAL*100/months:>+6.2f}%/mo "
          f"DD={abs(maxdd)/STARTING_BAL*100:.2f}% strk_ge6={st['n_streaks_ge6']}")


def main():
    t0 = time.time()
    df = pd.read_parquet(SRC)
    period_days = (df["ts"].iloc[-1] - df["ts"].iloc[0]).total_seconds() / 86400
    price = df["price"].to_numpy(dtype=np.float32)
    volume = df["volume"].to_numpy(dtype=np.int32)
    ts_ns = df["ts"].astype("int64").to_numpy()
    bars = build_1m_bars(price, ts_ns, volume)
    print(f"Loaded {len(df):,} ticks, {len(bars):,} bars  ({time.time()-t0:.0f}s)\n")

    base_setups = []
    for s in baseline_setups(bars):
        side = s["side"]; entry = s["entry_px"]
        tgt = entry + 18.0 if side == 1 else entry - 18.0
        base_setups.append({**s, "target_px": tgt})

    print("Running baseline target=18 sim...")
    trades = simulate(base_setups, price, ts_ns)
    print(f"  {len(trades)} trades ({time.time()-t0:.0f}s)\n")

    print("Extracting micro-features for every signal...")
    feat_df = extract_micro_features(bars, trades, base_setups)
    n_with_outcome = feat_df["loser"].notna().sum()
    print(f"  {n_with_outcome} trades have outcomes  ({time.time()-t0:.0f}s)\n")

    print("=" * 80)
    print("PATTERN DISCOVERY")
    print("=" * 80)
    df_with_pat, patterns = discover_patterns(feat_df)

    # Now test the most promising rules as filters
    print("\n" + "=" * 80)
    print("RULE TESTING: SKIP TRADES WHEN PATTERN MATCHES")
    print("=" * 80)
    bar_ts_local = bars.index.astype("int64").to_numpy()
    o = bars["open"].to_numpy(); c = bars["close"].to_numpy()
    h = bars["high"].to_numpy(); l = bars["low"].to_numpy()

    def rule_skip_overextended(bars, i, s, threshold=15):
        move_5bar = c[i] - c[i-5]
        return not (move_5bar * s["side"] > threshold)

    def rule_skip_choppy(bars, i, s):
        bodies = [abs(c[i-k] - o[i-k]) for k in range(3)]
        ranges = [max(h[i-k] - l[i-k], 1e-9) for k in range(3)]
        avg_body = sum(b/r for b,r in zip(bodies, ranges)) / 3
        return avg_body >= 0.35

    def rule_skip_momentum_lock(bars, i, s):
        body = abs(c[i] - o[i])
        rng = max(h[i] - l[i], 1e-9)
        if body/rng > 0.7 and ((c[i]-o[i]) > 0) == (s["side"] == 1):
            return False
        return True

    def rule_skip_all3_with_impulse(bars, i, s):
        for k in range(1, 4):
            bd = 1 if c[i-k+1] > o[i-k+1] else (-1 if c[i-k+1] < o[i-k+1] else 0)
            if bd != s["side"]:
                return True  # at least one against impulse — OK to take
        return False  # all 3 with impulse — skip

    test_rule(bars, base_setups, price, ts_ns, period_days,
              lambda b, i, s: True, "BASELINE (no rule)")
    test_rule(bars, base_setups, price, ts_ns, period_days,
              rule_skip_overextended, "Skip if 5-bar move > 15pt in impulse dir")
    test_rule(bars, base_setups, price, ts_ns, period_days,
              lambda b,i,s: rule_skip_overextended(b,i,s,20), "Skip if 5-bar move > 20pt in impulse dir")
    test_rule(bars, base_setups, price, ts_ns, period_days,
              rule_skip_choppy, "Skip if avg body% last 3 bars < 0.35")
    test_rule(bars, base_setups, price, ts_ns, period_days,
              rule_skip_momentum_lock, "Skip if signal bar = momentum lock (>70% body with impulse)")
    test_rule(bars, base_setups, price, ts_ns, period_days,
              rule_skip_all3_with_impulse, "Skip if all 3 prior bars closed with impulse")

    # Combined: overextended + momentum lock + all 3 with impulse
    def rule_combined(bars, i, s):
        return (rule_skip_overextended(bars, i, s) and
                rule_skip_momentum_lock(bars, i, s) and
                rule_skip_all3_with_impulse(bars, i, s))
    test_rule(bars, base_setups, price, ts_ns, period_days,
              rule_combined, "COMBINED: skip overextended + momentum + all3")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"patterns": [{"name": n, "table": t} for n, t in patterns]},
                              indent=2, default=str))
    print(f"\nTotal: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
