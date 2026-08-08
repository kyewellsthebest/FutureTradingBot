"""Take megatick's survivors and try to kill them. Whatever is left is real.

A survivor list is not a result. Cell #21 survived a train screen, an
out-of-sample era, a shuffled control, an eight-contract sign vote and a
100% neighbourhood check, and it was still an artifact -- caught only when
somebody played it as actual trades and the equity curve disagreed with the
means. So this stage does the disagreeing on purpose, in four escalating
tests, and reports how many survivors are left after each.

  1  REPLICATION IN THE SAME MARKET. The rule was found on one contract and
     one bar size. Re-run it on every OTHER contract of that market, untouched
     by the search. A behaviour is a property of the market; an artifact is a
     property of the file it was found in.

  2  SCALE INVARIANCE. Re-run at the neighbouring bar sizes. Real structure in
     event space does not appear at K=4000 and vanish at K=2600 -- if it does,
     the rule found one particular slicing of the tape.

  3  CROSS-MARKET TRANSFER. Re-run on every other market. Transfer is not
     required to be tradeable, but a rule that works in one market and is
     dead-flat in fourteen is a much weaker claim than one that leans the
     same way in several.

  4  TRADE-LEVEL REPLAY. Non-overlapping trades in chronological order, one
     position at a time, signals during an open trade skipped, costs charged
     once per round turn. Reports what the account actually lives through:
     expectancy, worst day, best day, average winning and losing day and week,
     max drawdown, longest losing streak. Means are not equity curves.

Nothing here re-fits anything. Every threshold, direction and hold comes from
the survivor record; this stage only ever measures.

Usage: python megaverify.py [N_SURVIVORS]
"""
import json
import os
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import megatick as mt  # noqa: E402

ROOT = mt.ROOT
OUT = os.environ.get("OUT_MD", os.path.join(ROOT, "research", "MEGAVERIFY.md"))
CKPT = mt.CKPT
NTOP = int(sys.argv[1]) if len(sys.argv) > 1 else 25
MINTR = mt.MINTR
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


COND = re.compile(r"^(?P<name>[A-Za-z_0-9]+?)(?P<op>>|<-)(?P<th>[0-9.]+)$")
CTX = re.compile(r"^(?P<mk>\S+) K=(?P<k>\d+) h=(?P<h>\d+) (?P<file>\S+)$")


def parse(tag, ctx):
    """'L mom13>0.67 & shape<-1.35' + context -> a portable rule object."""
    side, _, body = tag.partition(" ")
    conds = []
    for part in body.split(" & "):
        m = COND.match(part.strip())
        if not m:
            return None
        conds.append((m["name"], m["op"], float(m["th"])))
    c = CTX.match(ctx)
    if not c:
        return None
    return dict(side=1 if side == "L" else -1, conds=conds, mk=c["mk"],
                k=int(c["k"]), hold=int(c["h"]), file=c["file"])


def build_mask(B, conds):
    """Rebuild the rule's mask on a DIFFERENT tape. Standardisation is local
    to each tape on purpose -- that is what makes the rule portable, and it is
    the same normalisation the search itself used."""
    F = mt.features(B)
    n = len(B["c"])
    m = np.ones(n, bool)
    for name, op, th in conds:
        if name not in F:
            return None
        f = np.asarray(F[name], np.float64)
        fin = np.isfinite(f)
        if fin.sum() < n * 0.5:
            return None
        sd = np.nanstd(np.where(fin, f, np.nan))
        if not np.isfinite(sd) or sd <= 0:
            return None
        z = np.where(fin, (f - np.nanmean(np.where(fin, f, np.nan))) / sd,
                     np.nan)
        m &= np.where(np.isfinite(z), (z >= th) if op == ">" else (z <= -th),
                      False)
    return m


def evaluate(B, rule, cfg, dedrift=True):
    """Mean net dollars per signal on this tape. No split: the whole tape is
    out of sample when the tape was never searched."""
    m = build_mask(B, rule["conds"])
    if m is None or m.sum() < MINTR:
        return None
    c = B["c"]
    h = rule["hold"]
    f = np.full(len(c), np.nan)
    f[:-h] = c[h:] - c[:-h]
    ok = np.isfinite(f)
    if dedrift:
        f = f - np.nanmean(f[ok])
    usd = f * cfg["usd_tick"] * rule["side"]
    usd -= (B["sp"] * cfg["usd_tick"] * 2.0 if cfg.get("fx")
            else mt.COMM + mt.SLIP_TICKS * cfg["usd_tick"])
    s = m & ok
    if s.sum() < MINTR:
        return None
    return float(np.mean(usd[s])), int(s.sum())


def bars_for(path, cfg, k):
    px, sz, sp, ts = mt.load_one(path, cfg)
    B = mt.event_bars(px, sz, sp, ts, k)
    return B


def replay(B, rule, cfg, tsb):
    """Non-overlapping trades, chronological, one position at a time."""
    m = build_mask(B, rule["conds"])
    if m is None:
        return None
    c = B["c"]
    h = rule["hold"]
    cost = (float(np.nanmean(B["sp"])) * cfg["usd_tick"] * 2.0
            if cfg.get("fx") else mt.COMM + mt.SLIP_TICKS * cfg["usd_tick"])
    idx = np.flatnonzero(m)
    out, last = [], -1
    for i in idx:
        if i <= last or i + h >= len(c):
            continue
        pnl = (c[i + h] - c[i]) * rule["side"] * cfg["usd_tick"] - cost
        out.append((tsb[i], pnl))
        last = i + h
    return out


def main():
    if not os.path.exists(CKPT):
        log("No megatick checkpoint yet — run megatick.py first.")
        open(OUT, "w").write("\n".join(L) + "\n")
        return
    z = json.load(open(CKPT))
    best = sorted([tuple(x) for x in z["T"].get("best", [])], reverse=True)
    log("# Trying to kill megatick's survivors")
    log()
    if not best:
        log("The search produced **no configuration that made money on both "
            "halves after costs**. There is nothing to verify. That is a "
            "result, not a failure of this stage.")
        open(OUT, "w").write("\n".join(L) + "\n")
        return
    log(f"{len(best):,} survivors recorded (profitable on both halves after "
        f"costs). Testing the top {NTOP} by their WORSE half.")
    log()

    rules = []
    for key, tr_, ho_, tag, mkt, ctx in best[:NTOP]:
        r = parse(tag, ctx)
        if r:
            r.update(key=key, train=tr_, hold_usd=ho_, tag=tag)
            rules.append(r)
    log(f"{len(rules)} parsed cleanly.")
    log()

    # cache the tapes we need, one at a time, never all at once
    log("| # | market | rule | found on | SAME-MARKET other contracts | "
        "scale K/2, K*2 | cross-market | verdict |")
    log("|---|---|---|---|---|---|---|---|")
    survivors = []
    for n, r in enumerate(rules, 1):
        cfg = mt.MARKETS[r["mk"]]
        import glob
        files = sorted(glob.glob(os.path.join(ROOT, cfg["dir"], cfg["glob"])))
        others = [f for f in files if os.path.basename(f) != r["file"]]
        same, agree = [], 0
        for f in others[:6]:
            B = bars_for(f, cfg, r["k"])
            if B is None:
                continue
            e = evaluate(B, r, cfg)
            del B
            if e:
                same.append(e[0]); agree += int(e[0] > 0)
        scale = []
        for kk in (max(50, r["k"] // 2), r["k"] * 2):
            B = bars_for(os.path.join(ROOT, cfg["dir"], r["file"]), cfg, kk)
            if B is None:
                continue
            e = evaluate(B, r, cfg)
            del B
            if e:
                scale.append(e[0])
        cross, cagree = [], 0
        for om in [m for m in mt.WANT if m != r["mk"]][:6]:
            oc = mt.MARKETS[om]
            of = sorted(glob.glob(os.path.join(ROOT, oc["dir"], oc["glob"])))
            if not of:
                continue
            nrow = __import__("pyarrow.parquet",
                              fromlist=["x"]).ParquetFile(of[0]).metadata.num_rows
            kk = min(mt.KLADDER, key=lambda x: abs(nrow // max(x, 1) - 5000))
            B = bars_for(of[0], oc, kk)
            if B is None:
                continue
            e = evaluate(B, r, oc)
            del B
            if e:
                cross.append(e[0]); cagree += int(e[0] > 0)
        sm = np.mean(same) if same else float("nan")
        sc = np.mean(scale) if scale else float("nan")
        cm = np.mean(cross) if cross else float("nan")
        ok = (len(same) >= 2 and sm > 0 and agree >= max(2, len(same) * 0.6)
              and len(scale) >= 1 and sc > 0)
        if ok:
            survivors.append((r, sm, sc, cm, agree, len(same)))
        log(f"| {n} | {r['mk']} | `{r['tag']}` | ${r['key']:+.2f} worse half | "
            f"${sm:+.3f} ({agree}/{len(same)} up) | ${sc:+.3f} | "
            f"${cm:+.3f} ({cagree}/{len(cross)}) | "
            f"{'**SURVIVES**' if ok else 'dead'} |")
    log()
    log(f"**{len(survivors)} of {len(rules)} survive replication and scale.** "
        f"A rule dies here if it cannot repeat on contracts it was never "
        f"found on, or if halving and doubling the bar size erases it.")
    log()

    if not survivors:
        log("Nothing reached the trade replay. The honest read: the survivors "
            "were properties of the particular contract and bar size they "
            "were found on, which is what overfitting looks like from the "
            "inside.")
        open(OUT, "w").write("\n".join(L) + "\n")
        return

    log("## Trade-level replay of what survived")
    log()
    for r, sm, sc, cm, agree, nsame in survivors[:5]:
        cfg = mt.MARKETS[r["mk"]]
        import glob
        files = sorted(glob.glob(os.path.join(ROOT, cfg["dir"], cfg["glob"])))
        trades = []
        for f in files:
            px, sz, sp, ts = mt.load_one(f, cfg)
            B = mt.event_bars(px, sz, sp, ts, r["k"])
            if B is None:
                continue
            m0 = (len(px) // r["k"]) * r["k"]
            tsb = ts[:m0].reshape(-1, r["k"])[:, 0]
            del px, sz, sp, ts
            t = replay(B, r, cfg, tsb)
            del B
            if t:
                trades += t
        if not trades:
            continue
        T = pd.DataFrame(trades, columns=["ts", "pnl"])
        T["t"] = pd.to_datetime(T.ts)
        T = T.sort_values("t")
        day = T.groupby(T.t.dt.date).pnl.sum()
        wk = T.groupby(pd.Grouper(key="t", freq="W")).pnl.sum()
        wk = wk[wk != 0]
        eq = T.pnl.cumsum()
        wins = T.pnl > 0
        streak = worst = 0
        for w in wins.values:
            streak = 0 if w else streak + 1
            worst = max(worst, streak)
        wd, ld = day[day > 0], day[day <= 0]
        log(f"### `{r['tag']}` — {r['mk']}, K={r['k']}, hold {r['hold']} bars")
        log()
        log("| metric | value |")
        log("|---|---|")
        log(f"| trades | {len(T):,} over {day.size} days "
            f"({len(T) / max(day.size, 1):.1f}/day) |")
        log(f"| win rate | {wins.mean() * 100:.1f}% |")
        log(f"| expectancy | **${T.pnl.mean():+.2f}** per trade |")
        log(f"| avg winner / loser | ${T.pnl[wins].mean():+.2f} / "
            f"${T.pnl[~wins].mean():+.2f} |")
        log(f"| **average day** | **${day.mean():+.2f}** |")
        log(f"| positive days | {len(wd)}/{day.size} "
            f"({len(wd) / max(day.size, 1) * 100:.0f}%) |")
        log(f"| avg winning / losing day | ${wd.mean():+.2f} / "
            f"${ld.mean() if len(ld) else 0:+.2f} |")
        log(f"| best / WORST day | ${day.max():+.2f} / **${day.min():+.2f}** |")
        log(f"| **average week** | **${wk.mean():+.2f}** |")
        log(f"| best / WORST week | ${wk.max():+.2f} / "
            f"**${wk.min():+.2f}** |")
        log(f"| max drawdown | ${(eq - eq.cummax()).min():+.2f} |")
        log(f"| longest losing streak | {worst} trades |")
        log()
    log("Costs are charged once per round turn: $0.74 commission plus 2.5 "
        "ticks, the all-in figure measured from your own Tradovate fills. "
        "One micro contract throughout.")
    open(OUT, "w").write("\n".join(L) + "\n")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
