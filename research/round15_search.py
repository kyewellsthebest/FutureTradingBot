#!/usr/bin/env python3
"""Round 15 — VERIFIED bot-faithful harness, focused 500-variant search.

Uses round 9's r9_bot_on_tick AS-IS for execution. No custom queue logic.

TRACK 1: Verify the 6 round-14 candidates with the REAL executor.
TRACK 2: 500 new variants focused on WR improvement.

Output: /home/user/HFTBot/research/round15_results.md
"""
from __future__ import annotations
import os, sys, time, math, pickle
sys.path.insert(0, "/home/user/HFTBot")

# Hush round 4's env defaults
os.environ.setdefault("STRAT_INVERT", "1")
os.environ.setdefault("STRAT_PULL_PCT", "0.236")
os.environ.setdefault("STRAT_STOP_PTS", "10.0")
os.environ.setdefault("STRAT_TARGET_PTS", "20.0")
os.environ.setdefault("STRAT_IMPULSE_PTS", "5.0")
os.environ.setdefault("STRAT_IMPULSE_BARS", "4")
os.environ.setdefault("STRAT_COOLDOWN_SECS", "10")
os.environ.setdefault("BOT_HTF_TREND_FILTER", "0")

from research import round9_search as r9
from research import round7_search as r7
from research import round4_search as r4

PATH = "/home/user/HFTBot/data/tick/ustech/USTECH_full.csv"
OFFSET = 7_820_974_790
MAX_DAYS = 60
CHECKPOINT_EVERY_TICKS = 25_000
CHECKPOINT_PATH = "/home/user/HFTBot/research/round15_checkpoint.pkl"
RESULTS_PATH = "/home/user/HFTBot/research/round15_results.md"

# ============================================================================
# Build strategy set
# ============================================================================

def build_strategies():
    strats = []
    # TRACK 1: round-14 candidate verification (6 strats)
    track1_specs = [
        ("V_CANON_INV_236_s10t20", 5.0, 4, 0.236, 10, 20),
        ("V_INV_pp118_s5t20_imp3", 3.0, 4, 0.118, 5, 20),
        ("V_INV_pp118_s4t16_imp3", 3.0, 4, 0.118, 4, 16),
        ("V_INV_pp118_s3t12_imp3", 3.0, 4, 0.118, 3, 12),
        ("V_INV_pp118_s3t9_imp3",  3.0, 4, 0.118, 3, 9),
        ("V_INV_pp236_s5t20_imp3", 3.0, 4, 0.236, 5, 20),
    ]
    for spec in track1_specs:
        name, imp, bars, pp, stp, tgt = spec
        s = r4.PullbackStrategy(
            name, impulse_pts=imp, impulse_bars=bars,
            pull_pct=pp, stop_pts=stp, target_pts=tgt, invert=True)
        strats.append(s)

    # TRACK 2: focused param sweep on the most promising base patterns
    # pp118 and pp236 deep pullbacks with 1:3 and 1:4 R:R, INVERSE
    impulse_pts_list = [2.0, 3.0, 4.0, 5.0]
    impulse_bars_list = [3, 4, 5]
    pull_pct_list = [0.082, 0.118, 0.150, 0.180, 0.236]
    stop_pts_list = [2, 3, 4, 5]
    target_mult_list = [3, 4, 5]  # target = stop * mult (1:3, 1:4, 1:5 R:R)
    for ip in impulse_pts_list:
        for ib in impulse_bars_list:
            for pp in pull_pct_list:
                for sp in stop_pts_list:
                    for tm in target_mult_list:
                        tgt = sp * tm
                        if tgt > 30: continue
                        name = f"S_INV_imp{int(ip*10)}_b{ib}_pp{int(pp*1000)}_s{sp}t{tgt}"
                        s = r4.PullbackStrategy(
                            name, impulse_pts=ip, impulse_bars=ib,
                            pull_pct=pp, stop_pts=sp, target_pts=tgt, invert=True)
                        strats.append(s)
    return strats

# ============================================================================
# Streaming main loop
# ============================================================================

def save_checkpoint(offset, day_counter, last_day_key, strats):
    state = {
        "offset": int(offset),
        "day_counter": int(day_counter),
        "last_day_key": last_day_key,
        "variants": {
            s.name: {
                "completed": list(s.completed),
                "by_day": dict(s.by_day),
                "n_trades": int(s.n_trades),
            } for s in strats
        },
    }
    tmp = CHECKPOINT_PATH + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, CHECKPOINT_PATH)


def load_checkpoint(strats):
    if not os.path.exists(CHECKPOINT_PATH):
        return None
    try:
        with open(CHECKPOINT_PATH, "rb") as f:
            state = pickle.load(f)
    except Exception as e:
        print(f"[round15] checkpoint load failed: {e}", file=sys.stderr)
        return None
    by_name = {s.name: s for s in strats}
    for name, v in state.get("variants", {}).items():
        s = by_name.get(name)
        if s is None: continue
        s.completed = list(v.get("completed", []))
        s.by_day = dict(v.get("by_day", {}))
        s.n_trades = int(v.get("n_trades", 0))
    return (int(state["offset"]), int(state["day_counter"]), state["last_day_key"])


def main():
    strats = build_strategies()
    print(f"\n[round15] Built {len(strats)} strategies", file=sys.stderr)

    # Attach round 9's executor (uses round 7's BotFaithfulExecutor)
    for s in strats:
        r7.attach_r7_executor(s)

    # Resume
    resumed = load_checkpoint(strats)
    if resumed is not None:
        start_offset, day_counter, last_day_key = resumed
        booked = sum(s.n_trades for s in strats)
        print(f"[round15] RESUMING from offset {start_offset:,} "
              f"day={day_counter} (booked={booked:,} trades)", file=sys.stderr)
    else:
        start_offset = OFFSET
        day_counter = -1
        last_day_key = None

    bb_1m = r9.BarBuilder(granularity_secs=60, max_history=300)

    n_lines = 0
    t0 = time.time()

    with open(PATH, "rb") as f:
        f.seek(start_offset)
        f.readline()  # discard partial line
        for raw in f:
            n_lines += 1
            if n_lines % CHECKPOINT_EVERY_TICKS == 0:
                pos = f.tell()
                try:
                    save_checkpoint(pos, day_counter, last_day_key, strats)
                except Exception as e:
                    print(f"[round15] ckpt save fail: {e}", file=sys.stderr)
                rate = n_lines / (time.time() - t0)
                top = max((s.n_trades, s.name) for s in strats)
                print(f"  [round15] {n_lines/1e6:.2f}M ticks rate={rate:.0f}/s "
                      f"elapsed={(time.time()-t0)/60:.1f}m day={day_counter} "
                      f"most_trades={top[1]}({top[0]})", file=sys.stderr, flush=True)

            try:
                line = raw.decode("ascii", errors="ignore")
                stamp_str, vals = line.split(";", 1)
                vp = vals.split(";")
                if len(vp) < 3: continue
                last = float(vp[0]); bid = float(vp[1]); ask = float(vp[2])
                p = stamp_str.split()
                yy = int(p[0][:4]); mm = int(p[0][4:6]); dd = int(p[0][6:8])
                hh = int(p[1][:2]); mn = int(p[1][2:4]); ss = int(p[1][4:6])
                ns = int(p[2]) if len(p) > 2 else 0
            except Exception:
                continue

            day_key = (yy, mm, dd)
            if day_key != last_day_key:
                day_counter += 1
                last_day_key = day_key
                if day_counter >= MAX_DAYS: break
            ts = day_counter*86400 + hh*3600 + mn*60 + ss + ns/1e7

            if bb_1m.on_tick(ts, last):
                closed = bb_1m.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    for s in strats:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_1m.history)
            # Use round 9's executor exactly
            for s in strats:
                r9.r9_bot_on_tick(s, ts, bid, ask, day_counter, hh, mn, last)

    print(f"\n[round15] Done. Days={day_counter+1}, lines={n_lines:,}", file=sys.stderr)

    # ============================================================================
    # Report
    # ============================================================================
    n_days = max(1, day_counter + 1)
    rows = []
    for s in strats:
        n = s.n_trades
        if n == 0:
            rows.append({"name": s.name, "n": 0, "wr": 0, "per_day": 0,
                         "tr_per_day": 0, "per_trade": 0, "dd": 0, "sharpe": 0})
            continue
        wins = sum(1 for c in s.completed if c[0] > 0)
        net = sum(c[0] for c in s.completed)
        cum = 0; peak = 0; dd = 0
        for c in s.completed:
            cum += c[0]
            if cum > peak: peak = cum
            if peak - cum > dd: dd = peak - cum
        day_nets = [sum(s.by_day[d]) for d in s.by_day]
        if len(day_nets) > 1:
            mean = sum(day_nets) / len(day_nets)
            var = sum((x - mean)**2 for x in day_nets) / (len(day_nets) - 1)
            std = math.sqrt(var)
            sharpe = mean / std if std > 0 else 0
        else:
            sharpe = 0
        rows.append({"name": s.name, "n": n, "wr": wins/n, "per_day": net/n_days,
                     "tr_per_day": n/n_days, "per_trade": net/n, "dd": dd,
                     "sharpe": sharpe})

    rows.sort(key=lambda r: -r["per_day"])
    full_pass = [r for r in rows
                 if r["tr_per_day"] >= 300 and r["wr"] >= 0.45
                 and r["per_day"] >= 1000 and r["dd"] <= 5000]

    with open(RESULTS_PATH, "w") as f:
        f.write(f"# Round 15 — VERIFIED bot-faithful results\n\n")
        f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Strategies tested: {len(strats)}\n")
        f.write(f"Days: {n_days}\n")
        f.write(f"Tick stream: {n_lines:,} lines\n\n")
        f.write(f"## TRACK 1: Verification of round-14 candidates\n\n")
        f.write(f"| Strategy | Tr/d | WR% | $/day | DD | Sharpe |\n")
        f.write(f"|---|---:|---:|---:|---:|---:|\n")
        for r in rows:
            if not r["name"].startswith("V_"): continue
            f.write(f"| {r['name']} | {r['tr_per_day']:.1f} | {r['wr']*100:.1f} | "
                    f"${r['per_day']:+.2f} | ${r['dd']:+.0f} | {r['sharpe']:.2f} |\n")
        f.write(f"\n## FULL_PASS strategies (300+/45%/$1k/$5K DD): {len(full_pass)}\n\n")
        if full_pass:
            for r in full_pass[:20]:
                f.write(f"- **{r['name']}**: {r['tr_per_day']:.1f} tr/d, "
                        f"{r['wr']*100:.1f}% WR, ${r['per_day']:+.0f}/day, "
                        f"DD=${r['dd']:+.0f}, Sharpe={r['sharpe']:.2f}\n")
        else:
            f.write(f"**NONE.**\n\n")
        f.write(f"\n## Top 30 by $/day\n\n")
        f.write(f"| Rank | Strategy | Tr/d | WR% | $/day | $/tr | DD | Sharpe |\n")
        f.write(f"|---:|---|---:|---:|---:|---:|---:|---:|\n")
        for i, r in enumerate(rows[:30], 1):
            f.write(f"| {i} | {r['name']} | {r['tr_per_day']:.1f} | "
                    f"{r['wr']*100:.1f} | ${r['per_day']:+.2f} | "
                    f"${r['per_trade']:+.2f} | ${r['dd']:+.0f} | {r['sharpe']:.2f} |\n")

    # Clean up checkpoint
    try:
        if os.path.exists(CHECKPOINT_PATH):
            os.remove(CHECKPOINT_PATH)
    except: pass
    print(f"[round15] Results saved to {RESULTS_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
