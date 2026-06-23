"""Round 10 Direction 2 — Genetic Algorithm parameter evolution.

Starts with R4_INV15s_imp2_s4t12 as seed. Evolves a population of 60
individuals over up to 30 generations (configurable). Each evaluation
runs on a 7-day window of the tick stream.

Fitness = $/day * volume_indicator where volume_indicator = min(1.0, tr/d / 300)
to penalize low-volume strategies that can't reach the hard requirement.

Output: research/round10_ga_survivors.pkl with top-10 specs.
"""
from __future__ import annotations
import argparse
import os
import pickle
import random
import sys
import time
from collections import defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from research import round4_search as _r4
from research import round6_search as _r6
from research import round7_search as _r7
from research import round8_search as _r8
from research import round9_search as _r9
sys.modules.setdefault("round9_search", _r9)

MarketablePullback = _r6.MarketablePullback
BarBuilder = _r4.BarBuilder
MARKET = _r8.MARKET
REGIME = _r9.REGIME
r9_bot_on_tick = _r9.r9_bot_on_tick
attach_r7_executor = _r7.attach_r7_executor
PATH = _r7.PATH
MNQ_PER_PT = _r7.MNQ_PER_PT
FEE_FULL_RT = _r7.TOTAL_RT_COST
FEE_PROP_RT = _r7.COMM_RT

DEFAULT_OFFSET = 7_820_974_790  # 60d window start (we'll only use 7d)
GA_RNG = random.Random(0xABCDEF42)


# Param ranges
PARAM_SPACE = {
    'pull_pct': [0.118, 0.236, 0.30, 0.382, 0.50, 0.618],
    'impulse_pts': [2.0, 3.0, 4.0, 5.0, 6.0, 8.0],
    'impulse_bars': [2, 3, 4, 5],
    'stop_pts': [2, 3, 4, 5, 6, 8, 10, 12],
    'target_pts': [6, 8, 12, 15, 16, 20, 24, 30],
    'invert': [True, False],
    'granularity': ['15s', '30s', '1m'],
    'session': ['all', 'NYO', 'OVR', 'RTH', 'CME'],
}


def random_genome():
    g = {}
    for k, vs in PARAM_SPACE.items():
        g[k] = GA_RNG.choice(vs)
    if g['target_pts'] <= g['stop_pts']:
        g['target_pts'] = g['stop_pts'] * 2
    return g


def seed_genome():
    """R4_INV15s_imp2_s4t12 as seed."""
    return {
        'pull_pct': 0.236, 'impulse_pts': 2.0, 'impulse_bars': 4,
        'stop_pts': 4, 'target_pts': 12, 'invert': True,
        'granularity': '15s', 'session': 'all',
    }


def crossover(a, b):
    keys = list(a.keys())
    pt = GA_RNG.randint(1, len(keys) - 1)
    child = {}
    for i, k in enumerate(keys):
        child[k] = a[k] if i < pt else b[k]
    return child


def mutate(g, rate=0.05):
    out = dict(g)
    for k, vs in PARAM_SPACE.items():
        if GA_RNG.random() < rate:
            out[k] = GA_RNG.choice(vs)
    if out['target_pts'] <= out['stop_pts']:
        out['target_pts'] = out['stop_pts'] * 2
    return out


def genome_id(g):
    return (f"pp{int(g['pull_pct']*1000)}_imp{int(g['impulse_pts'])}"
            f"_b{g['impulse_bars']}_s{g['stop_pts']}_t{g['target_pts']}"
            f"_{'INV' if g['invert'] else 'TRD'}"
            f"_{g['granularity']}_{g['session']}")


def session_to_window(ses):
    if ses == 'NYO':
        return (13, 30), (15, 30)
    if ses == 'OVR':
        return (13, 30), (16, 0)
    if ses == 'RTH':
        return (13, 30), (20, 0)
    if ses == 'CME':
        return (22, 0), (5, 0)
    return None, None


def build_strategy_from_genome(g, name=None):
    ses_start, ses_end = session_to_window(g['session'])
    n = name or f"GA_{genome_id(g)}"
    max_hold = 120 if g['granularity'] == '15s' else (180 if g['granularity'] == '30s' else 600)
    s = MarketablePullback(
        n,
        impulse_pts=g['impulse_pts'],
        impulse_bars=g['impulse_bars'],
        pull_pct=g['pull_pct'],
        stop_pts=g['stop_pts'],
        target_pts=g['target_pts'],
        invert=g['invert'],
        session_start=ses_start,
        session_end=ses_end,
        max_hold=max_hold)
    attach_r7_executor(s)
    return s


def evaluate_population(pop, eval_days=7, offset=DEFAULT_OFFSET):
    """Run population on a [eval_days]-day stream. Returns list of dicts."""
    # Build strategies grouped by granularity
    strats_1m = []
    strats_15s = []
    strats_30s = []
    for g in pop:
        s = build_strategy_from_genome(g)
        if g['granularity'] == '15s':
            strats_15s.append((g, s))
        elif g['granularity'] == '30s':
            strats_30s.append((g, s))
        else:
            strats_1m.append((g, s))

    bb_1m = BarBuilder(granularity_secs=60, max_history=300)
    bb_15s = BarBuilder(granularity_secs=15, max_history=200)
    bb_30s = BarBuilder(granularity_secs=30, max_history=200)

    day_counter = -1
    last_day_key = None
    max_day_counter = -1 + eval_days
    n_lines = 0
    t0 = time.time()
    all_strats = [s for _, s in strats_1m + strats_15s + strats_30s]
    with open(PATH, "rb") as f:
        f.seek(offset)
        f.readline()
        for raw in f:
            n_lines += 1
            try:
                line = raw.decode("ascii", errors="ignore")
                stamp_str, vals = line.split(";", 1)
                vp = vals.split(";")
                if len(vp) < 3:
                    continue
                last = float(vp[0])
                bid = float(vp[1])
                ask = float(vp[2])
                p = stamp_str.split()
                if len(p) < 2:
                    continue
                yy = int(p[0][:4]); mm = int(p[0][4:6]); dd = int(p[0][6:8])
                hh = int(p[1][:2]); mn = int(p[1][2:4]); ss = int(p[1][4:6])
                ns = int(p[2]) if len(p) > 2 else 0
            except Exception:
                continue

            day_key = (yy, mm, dd)
            if day_key != last_day_key:
                day_counter += 1
                last_day_key = day_key
                if day_counter >= max_day_counter:
                    break

            ts = day_counter * 86400 + hh * 3600 + mn * 60 + ss + ns / 1e7

            MARKET.feed_tick(ts, last, bid, ask)

            if bb_1m.on_tick(ts, last):
                closed = bb_1m.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    MARKET.feed_bar(o, h, l, c)
                    REGIME.feed_bar(o, h, l, c)
                    for _, s in strats_1m:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_1m.history)
            if strats_15s and bb_15s.on_tick(ts, last):
                closed = bb_15s.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    for _, s in strats_15s:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_15s.history)
            if strats_30s and bb_30s.on_tick(ts, last):
                closed = bb_30s.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    for _, s in strats_30s:
                        s.on_bar_close(ts, hh, mn, o, h, l, c, bb_30s.history)

            for s in all_strats:
                r9_bot_on_tick(s, ts, bid, ask, day_counter, hh, mn, last)

    elapsed = time.time() - t0
    total_days = day_counter + 1
    out = []
    for g, s in strats_1m + strats_15s + strats_30s:
        n = s.n_trades
        net = sum(c[0] * MNQ_PER_PT - FEE_PROP_RT for c in s.completed)
        per_day = net / max(1, total_days)
        tpd = n / max(1, total_days)
        vol_factor = min(1.0, tpd / 300.0)
        fitness = per_day * vol_factor
        out.append({
            'genome': g, 'name': s.name, 'n': n, 'tpd': tpd,
            'net': net, 'per_day': per_day, 'fitness': fitness,
        })
    print(f"  [GA] evaluated {len(pop)} in {elapsed/60:.1f}min "
          f"({n_lines/1e6:.1f}M ticks, {total_days} days)", file=sys.stderr)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pop-size", type=int, default=30)
    ap.add_argument("--generations", type=int, default=8)
    ap.add_argument("--eval-days", type=int, default=7)
    ap.add_argument("--offset", type=int, default=DEFAULT_OFFSET)
    ap.add_argument("--mutation-rate", type=float, default=0.10)
    ap.add_argument("--output", default="/home/user/HFTBot/research/round10_ga_survivors.pkl")
    args = ap.parse_args()

    # Seed with R4 winner + random
    pop = [seed_genome()]
    pop.extend(random_genome() for _ in range(args.pop_size - 1))

    best_history = []
    for gen in range(args.generations):
        print(f"[GA] generation {gen}/{args.generations}", file=sys.stderr)
        results = evaluate_population(pop, eval_days=args.eval_days, offset=args.offset)
        results.sort(key=lambda r: -r['fitness'])
        top = results[0]
        print(f"  [GA] gen {gen}: best={top['name']} fitness={top['fitness']:.1f} "
              f"per_day=${top['per_day']:.0f} tpd={top['tpd']:.0f} n={top['n']}",
              file=sys.stderr)
        best_history.append({
            'gen': gen,
            'best_fitness': top['fitness'],
            'best_per_day': top['per_day'],
            'best_genome': top['genome'],
        })
        # Elitism: keep top 30%
        elite_n = max(2, args.pop_size // 3)
        elite = [r['genome'] for r in results[:elite_n]]
        # New generation: elite + crossover/mutation
        new_pop = list(elite)
        while len(new_pop) < args.pop_size:
            a = GA_RNG.choice(elite)
            b = GA_RNG.choice(elite)
            child = crossover(a, b)
            child = mutate(child, rate=args.mutation_rate)
            new_pop.append(child)
        pop = new_pop

    # Final evaluation
    print(f"[GA] final evaluation of evolved population", file=sys.stderr)
    final_results = evaluate_population(pop, eval_days=args.eval_days, offset=args.offset)
    final_results.sort(key=lambda r: -r['fitness'])

    survivors = []
    for r in final_results[:15]:
        spec = dict(r['genome'])
        spec['id'] = genome_id(r['genome'])
        ses_start, ses_end = session_to_window(r['genome']['session'])
        spec['ses_start'] = ses_start
        spec['ses_end'] = ses_end
        survivors.append(spec)

    with open(args.output, "wb") as f:
        pickle.dump(survivors, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"[GA] wrote {len(survivors)} survivors to {args.output}", file=sys.stderr)

    # Print summary
    print(f"\n[GA] Top 10 survivors by fitness:")
    for i, r in enumerate(final_results[:10], 1):
        g = r['genome']
        print(f"  {i}. fitness={r['fitness']:>6.1f} per_day=${r['per_day']:>+6.0f} "
              f"tpd={r['tpd']:>4.0f} n={r['n']:>4} -- {genome_id(g)}")


if __name__ == "__main__":
    main()
