"""Generalized CAUSAL family engine -- every variation, executable
semantics only, fast enough to sweep thousands of cells.

Cell keys:
  imp, w        impulse threshold (pts) over w bars, close-to-close
  retr          retracement fraction of the move (level = close - retr*move)
  S, T          stop / target distance (pts) from entry
  hold_s        window length seconds (fill + hold, from signal bar close)
  arch          "limit" (trade WITH impulse, resting limit at the level)
                "stop"  (trade AGAINST impulse: stop-entry triggers as
                         price crosses the level, entry pays 1 tick slip)
  policy        "first" (all windows rest, first cross fills)
                "deep"  (only the deepest pending level per direction rests)
  tick, tv      tick size (pts), $ per point
  comm          $ per round trip (default 1.24)
  slip_on       charge stop/timeout slip (default True)
  delay_bars    signal staleness in bars (placebo control)

Fill physics: entry only when the tape prints strictly beyond the level
(the condition for a resting limit to fill / a stop to trigger), 250ms
arm latency, single position, fires blocked until the filled window's
end + 60s, gap-aware stops, strict-penetration targets, timeout at the
first print past the window end.
"""
import numpy as np
import pandas as pd

BAR_NS = 60_000_000_000
DELAY_NS = 250_000_000
COOL_NS = 60 * 1_000_000_000


def bars_of(ts, px):
    idx = pd.to_datetime(ts)
    close = pd.Series(px, index=idx).resample("1min").last().ffill()
    bt = close.index.view(np.int64)
    bc = close.values
    rth = (close.index.hour * 60 + close.index.minute
           >= 13 * 60 + 30) & (close.index.hour < 20)
    return bt, bc, np.asarray(rth)


class MinuteIndex:
    """Per-minute min/max of the tape for O(minutes-scanned) first-cross
    queries instead of per-tick scans."""

    def __init__(self, ts, px, bt):
        self.ts, self.px = ts, px
        self.pos = np.searchsorted(ts, bt)          # tick idx of bar start
        self.end = np.append(self.pos[1:], len(ts))
        n = len(bt)
        self.mmin = np.full(n, np.inf)
        self.mmax = np.full(n, -np.inf)
        for m in range(n):
            a, b = self.pos[m], self.end[m]
            if a < b:
                seg = px[a:b]
                self.mmin[m] = seg.min()
                self.mmax[m] = seg.max()
        self.bt = bt

    def first_beyond(self, t_from, t_to, lvl, below):
        """First tick index with ts in [t_from, t_to) and px strictly
        beyond lvl (below=True: px < lvl). Returns -1 if none."""
        ts, px = self.ts, self.px
        j0 = np.searchsorted(ts, t_from)
        j1 = np.searchsorted(ts, t_to)
        if j0 >= j1:
            return -1
        m0 = np.searchsorted(self.bt, ts[j0], side="right") - 1
        m1 = np.searchsorted(self.bt, ts[j1 - 1], side="right") - 1
        # partial first minute
        a, b = max(j0, self.pos[m0]), min(j1, self.end[m0])
        seg = px[a:b]
        hit = np.flatnonzero(seg < lvl if below else seg > lvl)
        if len(hit):
            return a + hit[0]
        # whole minutes
        if m1 > m0:
            mm = self.mmin[m0 + 1:m1] if below else self.mmax[m0 + 1:m1]
            cand = np.flatnonzero(mm < lvl if below else mm > lvl)
            if len(cand):
                m = m0 + 1 + cand[0]
                a, b = self.pos[m], min(j1, self.end[m])
                seg = px[a:b]
                hit = np.flatnonzero(seg < lvl if below else seg > lvl)
                if len(hit):
                    return a + hit[0]
            # partial last minute
            a, b = max(j0, self.pos[m1]), j1
            if a < b and m1 > m0:
                seg = px[a:b]
                hit = np.flatnonzero(seg < lvl if below else seg > lvl)
                if len(hit):
                    return a + hit[0]
        return -1


def run_cell(ts, px, bt, bc, rth, lo, hi, cell, mindex=None):
    imp, w, retr = cell["imp"], cell["w"], cell["retr"]
    S, T = cell["S"], cell["T"]
    hold_ns = int(cell.get("hold_s", 600)) * 1_000_000_000
    arch = cell.get("arch", "limit")
    policy = cell.get("policy", "first")
    tick = cell.get("tick", 0.25)
    tv = cell.get("tv", 2.0)
    comm = cell.get("comm", 1.24)
    slip = tick if cell.get("slip_on", True) else 0.0
    dly = int(cell.get("delay_bars", 0))
    mi = mindex or MinuteIndex(ts, px, bt)
    n = len(ts)

    trades = []
    windows = []      # dict(arm, exp, lvl, below, side, fc, fc_from)
    lock_until = -10**18
    nofill_until = -10**18

    def fc_of(wd):
        frm = max(wd["arm"], nofill_until)
        if wd["fc_from"] != frm:
            j = mi.first_beyond(frm, wd["exp"], wd["lvl"], wd["below"])
            wd["fc"] = int(ts[j]) if j >= 0 else None
            wd["fc_idx"] = j
            wd["fc_from"] = frm
        return wd["fc"]

    for i in range(max(lo, w + 1 + dly), hi):
        bclose = bt[i] + BAR_NS
        if rth[i] and bclose >= lock_until:
            move = bc[i - dly] - bc[i - dly - w]
            if abs(move) >= imp:
                up = move > 0
                raw = bc[i - dly] - retr * move
                lvl = (np.floor(raw / tick) if up
                       else np.ceil(raw / tick)) * tick
                # approach: up-impulse level sits BELOW price -> the
                # tape crosses it downward (below=True); trade side:
                # limit=with impulse, stop=against
                below = up
                side = (1 if up else -1) if arch == "limit" \
                    else (-1 if up else 1)
                windows.append(dict(arm=bclose + DELAY_NS,
                                    exp=bclose + hold_ns,
                                    lvl=float(lvl), below=below,
                                    side=side, fc=None, fc_from=None,
                                    fc_idx=-1))
        nxt = bt[i + 1] + BAR_NS if i + 1 < len(bt) else 2**62
        while windows:
            windows = [wd for wd in windows
                       if wd["exp"] > max(nofill_until, bclose)]
            cand = windows
            if policy == "deep" and windows:
                deep_dn = min((wd for wd in windows if wd["below"]),
                              key=lambda d: d["lvl"], default=None)
                deep_up = max((wd for wd in windows if not wd["below"]),
                              key=lambda d: d["lvl"], default=None)
                cand = [d for d in (deep_dn, deep_up) if d]
            best = None
            for wd in cand:
                t = fc_of(wd)
                if t is not None and (best is None or t < best[0]):
                    best = (t, wd)
            if best is None or best[0] >= nxt:
                break
            t_fill, wd = best
            fidx = wd["fc_idx"]
            # limit: rests AT the level, fills at it (zero entry cost).
            # stop: a triggered market order fills WORSE than the
            # trigger -- long fills higher, short fills lower. The sign
            # was inverted here (2026-08-15), handing the stop
            # archetype a free tick in its favour and inflating exactly
            # the cells that topped the first-quarter board.
            entry = wd["lvl"] + (0 if arch == "limit"
                                 else wd["side"] * slip)
            side = wd["side"]
            stop = entry - side * S
            tgt = entry + side * T
            js = mi.first_beyond(t_fill, wd["exp"], stop + side * 1e-9,
                                 below=(side > 0))
            # stop fires at <= stop for long: use first print < stop+eps
            jt = mi.first_beyond(t_fill, wd["exp"], tgt,
                                 below=(side < 0))
            s_t = int(ts[js]) if js >= 0 else None
            t_t = int(ts[jt]) if jt >= 0 else None
            if t_t is not None and (s_t is None or t_t < s_t):
                gain, reason, exit_ns = T * tv, "target", t_t
            elif s_t is not None:
                xp = px[js]
                ex = min(xp, stop) if side > 0 else max(xp, stop)
                gain = (side * (ex - entry) - slip) * tv
                reason, exit_ns = "stop", s_t
            else:
                kend = np.searchsorted(ts, wd["exp"])
                xpx = px[kend] if kend < n else px[-1]
                gain = (side * (xpx - entry) - slip) * tv
                reason = "timeout"
                exit_ns = int(ts[min(kend, n - 1)])
            trades.append((t_fill, side, float(entry), reason,
                           float(gain - comm)))
            lock_until = wd["exp"] + COOL_NS
            nofill_until = max(exit_ns, wd["exp"]) + COOL_NS
            windows = [x for x in windows if x is not wd]
    return trades
