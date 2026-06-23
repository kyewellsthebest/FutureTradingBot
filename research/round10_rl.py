"""Round 10 Direction 1 — Tabular Q-learning agent pre-pass.

Trains a Q-table policy on day 0-39 of the 60-day window, then saves it
to /home/user/HFTBot/research/round10_qtable.pkl. The main round10_search
loads this Q-table and creates an RLQTableStrategy variant.

State features (binned):
- net_bin: sign of last 4-bar net (0=up, 1=down)
- vol_bin: realized vol (0=low, 1=high) — from REGIME singleton
- tape_bin: tape speed ratio (0=normal, 1=elevated)

Actions: {0: noop, 1: LONG, 2: SHORT}

Reward: realized P&L USD net of $0.74 prop-firm fees when the next
exit occurs (stop/target/timeout). For training we use a fixed bracket
(stop=5pt, target=15pt, max_hold=300s).

Training: traverse the tick stream, evaluate every bar close; epsilon-greedy
action selection with epsilon starting at 1.0 and linearly decaying to 0.05
over the training period.
"""
from __future__ import annotations
import argparse
import os
import pickle
import random
import sys
import time
from collections import defaultdict, deque

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from research import round4_search as _r4
from research import round7_search as _r7
from research import round8_search as _r8
from research import round9_search as _r9

BarBuilder = _r4.BarBuilder
MARKET = _r8.MARKET
REGIME = _r9.REGIME
PATH = _r7.PATH
MNQ_PER_PT = _r7.MNQ_PER_PT
FEE_PROP_RT = _r7.COMM_RT

DEFAULT_OFFSET = 7_820_974_790
RNG = random.Random(0xDADA0001)


class TapeSpeed:
    def __init__(self):
        self._short = deque()
        self._long = deque()
        self.r = 1.0

    def feed(self, ts):
        self._short.append(ts)
        self._long.append(ts)
        while self._short and ts - self._short[0] > 5.0:
            self._short.popleft()
        while self._long and ts - self._long[0] > 60.0:
            self._long.popleft()
        sr = len(self._short) / 5.0
        lr = len(self._long) / 60.0
        self.r = sr / lr if lr > 0.5 else 1.0


def state_of(net4, vol_bin, tape_r):
    n_bin = 0 if net4 > 0 else 1
    v_bin = 1 if vol_bin else 0
    t_bin = 1 if tape_r > 2.0 else 0
    return (n_bin, v_bin, t_bin)


def epsilon_at(step, total_steps):
    if total_steps <= 0:
        return 0.05
    frac = min(1.0, step / total_steps)
    return max(0.05, 1.0 - frac * 0.95)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offset", type=int, default=DEFAULT_OFFSET)
    ap.add_argument("--train-days", type=int, default=40)
    ap.add_argument("--stop-pts", type=float, default=5.0)
    ap.add_argument("--target-pts", type=float, default=15.0)
    ap.add_argument("--max-hold-s", type=float, default=300.0)
    ap.add_argument("--alpha", type=float, default=0.10)
    ap.add_argument("--gamma", type=float, default=0.95)
    ap.add_argument("--output", default="/home/user/HFTBot/research/round10_qtable.pkl")
    args = ap.parse_args()

    Q = defaultdict(lambda: {0: 0.0, 1: 0.0, 2: 0.0})
    visits = defaultdict(int)
    tape = TapeSpeed()
    bb = BarBuilder(granularity_secs=60, max_history=200)

    day_counter = -1
    last_day_key = None
    max_day_counter = -1 + args.train_days
    n_lines = 0
    n_bars = 0
    n_actions = 0
    n_completions = 0
    t0 = time.time()

    # Current "open" trade tracked separately (single-trade Q learner).
    open_trade = None  # dict with state, action, entry_px, et, side
    # Estimate of total bar steps for epsilon scheduling
    EST_BARS = args.train_days * 1440  # ~1440 bars/day max

    print(f"[RL] training Q-table over {args.train_days}d "
          f"with stop={args.stop_pts}pt target={args.target_pts}pt",
          file=sys.stderr)

    with open(PATH, "rb") as f:
        f.seek(args.offset)
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
            tape.feed(ts)
            MARKET.feed_tick(ts, last, bid, ask)

            # Manage open trade
            if open_trade is not None:
                ot = open_trade
                pnl = None
                if ot['side'] == 'LONG':
                    if bid <= ot['stop']:
                        pnl = ot['stop'] - ot['entry']
                    elif bid >= ot['target']:
                        pnl = ot['target'] - ot['entry']
                    elif ts - ot['et'] >= args.max_hold_s:
                        pnl = bid - ot['entry']
                else:
                    if ask >= ot['stop']:
                        pnl = ot['entry'] - ot['stop']
                    elif ask <= ot['target']:
                        pnl = ot['entry'] - ot['target']
                    elif ts - ot['et'] >= args.max_hold_s:
                        pnl = ot['entry'] - ask
                if pnl is not None:
                    reward = pnl * MNQ_PER_PT - FEE_PROP_RT
                    # Q-learning update — no next state because trade ends
                    s = ot['state']
                    a = ot['action']
                    cur = Q[s][a]
                    Q[s][a] = cur + args.alpha * (reward - cur)
                    visits[s] += 1
                    n_completions += 1
                    open_trade = None
                    if n_completions % 1000 == 0:
                        print(f"  [RL] {n_completions} completions, "
                              f"{n_actions} actions, "
                              f"{n_lines/1e6:.1f}M ticks, "
                              f"{(time.time()-t0)/60:.1f}m elapsed",
                              file=sys.stderr, flush=True)

            if bb.on_tick(ts, last):
                closed = bb.closed_bar()
                if closed is not None:
                    o, h, l, c = closed
                    MARKET.feed_bar(o, h, l, c)
                    REGIME.feed_bar(o, h, l, c)
                    n_bars += 1
                    if open_trade is None:
                        hist = bb.history
                        if len(hist) >= 4:
                            net4 = hist[-1][3] - hist[-4][0]
                            vol_bit = REGIME.current_cell() & 1
                            s = state_of(net4, vol_bit, tape.r)
                            # epsilon-greedy action
                            eps = epsilon_at(n_bars, EST_BARS)
                            if RNG.random() < eps:
                                a = RNG.randint(0, 2)
                            else:
                                qa = Q[s]
                                a = max(qa, key=qa.get)
                            n_actions += 1
                            if a == 0:
                                # noop reward 0
                                cur = Q[s][a]
                                Q[s][a] = cur + args.alpha * (0.0 - cur)
                                visits[s] += 1
                            else:
                                side = 'LONG' if a == 1 else 'SHORT'
                                mid = (bid + ask) / 2.0
                                entry = ask if side == 'LONG' else bid
                                if side == 'LONG':
                                    stop = entry - args.stop_pts
                                    target = entry + args.target_pts
                                else:
                                    stop = entry + args.stop_pts
                                    target = entry - args.target_pts
                                open_trade = {
                                    'state': s, 'action': a, 'side': side,
                                    'entry': entry, 'stop': stop,
                                    'target': target, 'et': ts,
                                }

    elapsed = time.time() - t0
    print(f"[RL] DONE in {elapsed/60:.1f}min, {n_lines:,} ticks, "
          f"{day_counter+1} days, {n_bars} bars, "
          f"{n_actions} actions, {n_completions} completions",
          file=sys.stderr)

    # Convert defaultdict to regular dict
    Q_out = {k: dict(v) for k, v in Q.items()}
    with open(args.output, "wb") as f:
        pickle.dump(Q_out, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"[RL] saved Q-table ({len(Q_out)} states) to {args.output}",
          file=sys.stderr)

    # Print summary
    print(f"\n[RL] Q-table summary:")
    for s in sorted(Q_out.keys()):
        q = Q_out[s]
        v = visits[s]
        best_a = max(q, key=q.get)
        names = {0: 'noop', 1: 'LONG', 2: 'SHORT'}
        print(f"  state {s}: visits={v} "
              f"Q[noop]={q[0]:+.2f} Q[LONG]={q[1]:+.2f} Q[SHORT]={q[2]:+.2f} "
              f"-> {names[best_a]}")


if __name__ == "__main__":
    main()
