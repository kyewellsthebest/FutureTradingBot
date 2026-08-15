"""What would Friday's session have paid? Tick-true replay of the
validated cells over the REAL 2026-08-14 13:30-20:00 UTC tape.

Same fill model as the validation (pulse.py): signals on closed 1-min
bars, entry only when the tape trades through the 0.618 limit inside
the 10-min window (250ms latency), gap-aware stops +1 tick slip,
strict-penetration targets, 1 tick on timeout exits, $1.24 RT.

Input: data/tick/week/{TICKER}_20260814.parquet (Polygon trades).
Output: research/FRIDAY_REPLAY.md with the per-trade log.
"""
import os
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DAY = os.environ.get("REPLAY_DAY", "20260814")
COMM = 1.24
DELAY_NS = 250_000_000
COOL_NS = 60_000_000_000
HOLD_NS = 10 * 60_000_000_000
W = 6
RETR = 0.618

MKTS = {
    "MNQ": dict(tick="MNQU6", imp=5.0, S=10.0, T=20.0, tv=2.0, slip=0.25,
                deployed=True),
    "MES": dict(tick="MESU6", imp=1.5, S=3.0, T=6.0, tv=5.0, slip=0.25,
                deployed=False),
    "MYM": dict(tick="MYMU6", imp=16.0, S=20.0, T=40.0, tv=0.5, slip=1.0,
                deployed=False),
}


def replay(ts, px, cfg):
    idx = pd.to_datetime(ts)
    close = pd.Series(px, index=idx).resample("1min").last().ffill()
    bt = close.index.view(np.int64)
    bc = close.values
    rth = (close.index.hour * 60 + close.index.minute >= 13 * 60 + 30) & \
          (close.index.hour < 20)
    imp, S, T, tv, slip = cfg["imp"], cfg["S"], cfg["T"], cfg["tv"], \
        cfg["slip"]
    trades = []
    last_x = -10**18
    for i in range(W + 1, len(bc)):
        if not rth[i] or bt[i] < last_x + COOL_NS:
            continue
        move = bc[i] - bc[i - W]
        if abs(move) < imp:
            continue
        up = move > 0
        limit = bc[i] - RETR * move
        side = 1 if up else -1
        j0 = np.searchsorted(ts, bt[i] + 60_000_000_000 + DELAY_NS)
        j1 = np.searchsorted(ts, bt[i] + 60_000_000_000 + HOLD_NS)
        seg = px[j0:j1]
        if not len(seg):
            continue
        hitf = np.flatnonzero(seg < limit) if up else \
            np.flatnonzero(seg > limit)
        if not len(hitf):
            continue
        f = hitf[0]
        entry = limit
        rest = seg[f:]
        stop = entry - side * S
        tgt = entry + side * T
        if side > 0:
            si = np.flatnonzero(rest <= stop)
            ti = np.flatnonzero(rest > tgt)
        else:
            si = np.flatnonzero(rest >= stop)
            ti = np.flatnonzero(rest < tgt)
        s_at = si[0] if len(si) else 10**9
        t_at = ti[0] if len(ti) else 10**9
        if t_at < s_at:
            gain, o = T * tv, "target"
        elif s_at < 10**9:
            xp = rest[s_at]
            ex = min(xp, stop) if side > 0 else max(xp, stop)
            gain, o = (side * (ex - entry) - slip) * tv, "stop"
        else:
            gain, o = (side * (rest[-1] - entry) - slip) * tv, "timeout"
        et = pd.Timestamp(ts[j0 + f]).strftime("%H:%M:%S")
        trades.append((et, "LONG" if side > 0 else "SHORT", entry,
                       o, round(gain - COMM, 2)))
        last_x = bt[i] + 60_000_000_000 + HOLD_NS
    return trades


L = [f"# Friday {DAY[:4]}-{DAY[4:6]}-{DAY[6:]} session replay "
     "(13:30-20:00 UTC) -- the validated cells on the real tape", ""]
book = 0.0
for mk, cfg in MKTS.items():
    p = ROOT / "data" / "tick" / "week" / f"{cfg['tick']}_{DAY}.parquet"
    if not p.exists():
        L.append(f"## {mk}: no tape ({p.name} missing)")
        L.append("")
        continue
    df = pd.read_parquet(p)
    ts = df["ts"].to_numpy(dtype=np.int64)
    px = df["price"].to_numpy(dtype=np.float64)
    o = np.argsort(ts, kind="stable")
    ts, px = ts[o], px[o]
    trades = replay(ts, px, cfg)
    tot = sum(t[4] for t in trades)
    book += tot
    tag = " (the deployed instance)" if cfg["deployed"] else \
        " (validated, service not yet created)"
    L.append(f"## {mk}{tag}: **${tot:+,.2f}** on {len(trades)} trades")
    L.append("")
    L.append("| entry (UTC) | side | entry px | exit | P&L |")
    L.append("|---|---|---|---|---|")
    for et, sd, en, oo, pnl in trades:
        L.append(f"| {et} | {sd} | {en:,.2f} | {oo} | {pnl:+,.2f} |")
    wins = sum(1 for t in trades if t[4] > 0)
    L.append("")
    L.append(f"- win rate {wins}/{len(trades)}"
             f" ({wins/len(trades)*100:.0f}%)" if trades else "- no trades")
    L.append("")
L.append(f"## Book total: **${book:+,.2f}**")
L.append("")
L.append("Same fill model as the validation: through-the-limit entries "
         "(250ms latency), gap-aware stops +1 tick, strict targets, "
         "1 tick on timeouts, $1.24 RT commission, 1 micro each.")
out = ROOT / "research" / "FRIDAY_REPLAY.md"
out.write_text("\n".join(L) + "\n")
print("\n".join(L[:20]))
print("wrote", out)
