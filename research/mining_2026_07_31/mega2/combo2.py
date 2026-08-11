"""The two best rules, run together, day by day.

WHY THIS IS NOT ARITHMETIC ON TWO TABLE ROWS. Trades per week and dollars per
week add up. Best day, worst week, drawdown and losing streaks do not -- they
depend on WHEN each trade happened, whether the two rules fire on the same
days, and how their losses line up. Two strategies that each lose $300 in a
bad week are a $600 week if they lose together and a $300 week if they take
turns. The only way to know is to put both on the same clock and add the P&L
bar by bar.

WHAT THIS ALSO IS, and it matters more than the specs: an OUT-OF-SAMPLE TEST.
Each rule was found in one quarter -- the flow rule in NQH5, the duration rule
in NQU4 -- and here both are run across EVERY quarter. A rule that only works
in the three months it was discovered in is a description of those three
months. The per-quarter table below is the real result; the portfolio specs
are what you would have lived through if you had traded it.

THREE THINGS ARE PRICED HONESTLY RATHER THAN ASSUMED:

  EXECUTION. Both rules rest a limit, and the search credited that a flat two
  ticks. The maker study measured the true advantage at +$0.355 a trade at the
  front of the queue and NEGATIVE past five contracts of depth, so the
  optimistic figure is used here and the pessimistic one is reported beside it.

  OVERLAP. The rules may hold at the same time, which means two contracts on
  at once and double the risk in that moment. Concurrency is counted, not
  waved away.

  CORRELATION. One rule is LONG and the other SHORT, so they may genuinely
  diversify -- but that has to be measured rather than assumed from the signs,
  because two rules can still lose on the same days. The day-level correlation
  says how much of the second one is really a second bet.
"""
import json
import math
import os
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402
import hunt  # noqa: E402
import mega  # noqa: E402

OUT = os.environ.get("OUT_MD", os.path.join(fuse.ROOT, "research", "COMBO2.md"))
TV, TPX = 0.50, 0.25
COST = 1.24
MAKER = 0.355           # measured front-of-queue advantage over crossing
MAKER_DEEP = -0.102     # same, five-plus contracts deep in the queue
ACCOUNT = 4100.0
L = []

# The two rules, exactly as the searches reported them.
RULES = [
    # SIDE AND BAR SIZE COME FROM THE RECORD, NOT FROM READING THE LABEL.
    # The first version of this file guessed both from the rule text and got
    # both wrong -- side SHORT when the record says LONG, and 500-tick bars
    # when it was found on 250. On its own home quarter the reconstruction
    # then produced -$2.14 a trade against the +$2.35 the search reported, a
    # clean sign flip that only showed up because the home quarter was run at
    # all. Anything trading on out-of-sample quarters alone would have looked
    # merely disappointing rather than wrong.
    dict(name="A · duration+regime", k=3, side=1, stop=49, tgt=62, K=250,
         home="NQU4",
         legs=[("d_z55", 1, 0.90), ("f_eff21", 1, 0.78), ("p_chop55", 1, 0.85),
               ("v_ac144", 1, 0.30), ("i_rty_sz600", 1, 0.80)]),
    dict(name="B · two-horizon flow", k=2, side=-1, stop=82, tgt=82, K=500,
         home="NQH5",
         legs=[("f_wcofi600", -1, 0.35), ("f_wcofi120", -1, 0.35)]),
]


def log(s=""):
    print(s, flush=True)
    L.append(s)


def signal(F, rule, n):
    """k-of-n over the legs. k == len(legs) is a plain AND."""
    tot = np.zeros(n, dtype=np.int16)
    have = 0
    for fn, sd, q in rule["legs"]:
        if fn not in F:
            continue
        v = np.asarray(F[fn], dtype=np.float64)[:n]
        fin = np.isfinite(v)
        if fin.sum() < n * 0.5:
            continue
        thr = float(np.quantile(v[fin], q))
        tot += (((v >= thr) if sd > 0 else (v <= thr)) & fin).astype(np.int16)
        have += 1
    if have < rule["k"]:
        return None
    return tot >= rule["k"]


def trades(cn, rule):
    """Every non-overlapping trade this rule would have taken on this
    contract: timestamp and dollars, priced at the measured maker edge."""
    B, F = mega.features(cn, rule["K"])
    n = len(B["c"])
    sig = signal(F, rule, n)
    if sig is None or sig.sum() < 50:
        return None
    ks = np.array(sorted({rule["stop"], rule["tgt"]}), dtype=int)
    si = int(np.where(ks == rule["stop"])[0][0])
    ti = int(np.where(ks == rule["tgt"])[0][0])
    up, dn = hunt.tau(B, ks, TPX)
    r, hold, wt = hunt.outcomes(B, up, dn, si, ti, rule["side"], ks, TPX, TV)[:3]
    del up, dn
    idx = hunt.nonoverlap(np.flatnonzero(sig), hold)
    if len(idx) < 20:
        return None
    days = len(np.unique(B["ts"] // fuse.DAY_NS))
    return pd.DataFrame(dict(
        ts=pd.to_datetime(B["ts"][idx]),
        pnl=r[idx] - COST + MAKER,
        pnl_deep=r[idx] - COST + MAKER_DEEP,
        win=wt[idx].astype(int),
        end=idx + hold[idx],
        start=idx,
        rule=rule["name"], con=cn, days=days))


def streak(x):
    """Longest run of losing DAYS actually observed."""
    best = cur = 0
    for v in x:
        cur = cur + 1 if v < 0 else 0
        best = max(best, cur)
    return best


def specs(daily, label, col="pnl"):
    d = daily[col]
    eq = d.cumsum()
    dd = float((eq - eq.cummax()).min())
    wk = d.resample("W").sum()
    winr = d[d > 0]
    losr = d[d < 0]
    return dict(
        label=label, days=len(d), total=float(d.sum()),
        perday=float(d.mean()), perweek=float(wk.mean()),
        bestday=float(d.max()), worstday=float(d.min()),
        bestweek=float(wk.max()), worstweek=float(wk.min()),
        avgwin=float(winr.mean()) if len(winr) else 0.0,
        avgloss=float(losr.mean()) if len(losr) else 0.0,
        pctwin=float((d > 0).mean()), maxdd=dd,
        streak=streak(d.to_numpy()))


def main():
    meta = fuse.tape_meta()
    cons = [c for c in fuse.NQ_CONTRACTS if c in meta]
    allt = []
    for rule in RULES:
        for cn in cons:
            try:
                t = trades(cn, rule)
            except Exception as e:                               # noqa: BLE001
                print(f"{rule['name']} {cn}: {type(e).__name__}: {e}",
                      flush=True)
                continue
            if t is not None:
                allt.append(t)
                w = t.pnl.sum() / (t.days.iloc[0] / 5)
                print(f"{rule['name'][:14]:14s} {cn}: {len(t):5,} trades, "
                      f"${t.pnl.mean():+.2f}/tr, ${w:+,.0f}/wk"
                      f"{'   <- home quarter' if cn == rule['home'] else ''}",
                      flush=True)
    if not allt:
        print("nothing to combine")
        return
    T = pd.concat(allt, ignore_index=True).sort_values("ts")
    T["day"] = T.ts.dt.floor("D")

    log("# The two best rules, traded together")
    log()
    log("Trades and dollars per week add up. **Best day, worst week, drawdown "
        "and losing streaks do not** — they depend on when each trade happened "
        "and whether the two rules lose on the same days. Two strategies that "
        "each drop $300 in a bad week are a $600 week if they fall together "
        "and a $300 week if they take turns. So both are put on one clock and "
        "the P&L is added bar by bar.")
    log()
    log("| | rule |")
    log("|---|---|")
    for r in RULES:
        legs = ", ".join(f"`{f}`{'>' if s > 0 else '<'}{q:g}"
                         for f, s, q in r["legs"])
        log(f"| **{r['name']}** | {r['k']} of ({legs}) — "
            f"**{'LONG' if r['side'] > 0 else 'SHORT'}**, {r['K']}-tick bars, "
            f"stop {r['stop']}/target {r['tgt']}, found in {r['home']} |")
    log()

    # ---------------- out of sample, which is the real test ----------------
    log("## Out of sample: every quarter, not just the one it was found in")
    log()
    log("Each rule was discovered in a single quarter. A rule that only works "
        "in the three months it was found in is a description of those three "
        "months. **This table is the actual result** — the portfolio specs "
        "below only mean something if these numbers hold up.")
    log()
    log("| quarter | " + " | ".join(r["name"] for r in RULES) + " |")
    log("|---|" + "---|" * len(RULES))
    for cn in cons:
        cells = []
        for r in RULES:
            s = T[(T.con == cn) & (T.rule == r["name"])]
            if not len(s):
                cells.append("—")
                continue
            wk = s.pnl.sum() / (s.days.iloc[0] / 5)
            mark = " ⌂" if cn == r["home"] else ""
            cells.append(f"${s.pnl.mean():+.2f}/tr · ${wk:+,.0f}/wk{mark}")
        log(f"| {cn} | " + " | ".join(cells) + " |")
    log()
    log("⌂ = the quarter the rule was found in. Everything else is out of "
        "sample.")
    log()

    # ---------------- the portfolio ----------------
    daily = T.set_index("day").pnl.resample("D").sum()
    daily = daily[daily.index.dayofweek < 5]
    dd_deep = T.set_index("day").pnl_deep.resample("D").sum()
    dd_deep = dd_deep[dd_deep.index.dayofweek < 5]

    rows = []
    for r in RULES:
        s = T[T.rule == r["name"]].set_index("day").pnl.resample("D").sum()
        s = s[s.index.dayofweek < 5]
        rows.append(specs(s.to_frame("pnl"), r["name"]))
    rows.append(specs(daily.to_frame("pnl"), "**BOTH TOGETHER**"))

    log("## Specs")
    log()
    log("| | " + " | ".join(x["label"] for x in rows) + " |")
    log("|---|" + "---|" * len(rows))

    def row(name, key, fmt="${:,.0f}"):
        log(f"| {name} | " + " | ".join(fmt.format(x[key]) for x in rows) + " |")

    tw = [len(T[T.rule == r["name"]]) for r in RULES] + [len(T)]
    nweeks = len(daily) / 5
    log("| **trades/week** | " + " | ".join(f"{t/nweeks:,.0f}" for t in tw) + " |")
    row("**$/week**", "perweek")
    row("$/day", "perday")
    log("| % of days green | " + " | ".join(f"{x['pctwin']:.0%}" for x in rows)
        + " |")
    row("**best day**", "bestday")
    row("**worst day**", "worstday")
    row("**best week**", "bestweek")
    row("**worst week**", "worstweek")
    row("avg winning day", "avgwin")
    row("avg losing day", "avgloss")
    row("**max drawdown**", "maxdd")
    log("| **longest losing streak** | "
        + " | ".join(f"{x['streak']} days" for x in rows) + " |")
    log("| total over the sample | "
        + " | ".join(f"${x['total']:,.0f}" for x in rows) + " |")
    log()
    p = rows[-1]
    log(f"`{len(daily):,}` trading days. Max drawdown **${abs(p['maxdd']):,.0f}"
        f"** is **{abs(p['maxdd'])/ACCOUNT:.0%}** of a $4,100 account.")
    log()

    # ---------------- the caveats, measured not asserted ----------------
    a = T[T.rule == RULES[0]["name"]].set_index("day").pnl.resample("D").sum()
    b = T[T.rule == RULES[1]["name"]].set_index("day").pnl.resample("D").sum()
    j = pd.concat([a, b], axis=1).dropna()
    corr = float(j.corr().iloc[0, 1]) if len(j) > 30 else float("nan")
    deep = specs(dd_deep.to_frame("pnl"), "deep queue")

    log("## What these numbers are resting on")
    log()
    sides = "one LONG and one SHORT"
    log(f"**The two rules trade opposite directions** — {sides}. Their daily "
        f"P&L correlates **{corr:+.2f}** across the {len(j):,} days both were "
        f"active. That number, not the direction labels, decides whether the "
        f"second rule is a second bet: near zero and the drawdowns genuinely "
        f"offset, strongly positive and they compound. Opposite signs do not "
        f"guarantee opposite outcomes, because both can lose on the same "
        f"choppy day.")
    log()
    log(f"**Execution is the whole result.** Both rest a limit, and the search "
        f"credited that a flat two ticks. Measured, resting is worth "
        f"**+$0.355** a trade at the front of the queue and **−$0.102** past "
        f"five contracts of depth. Everything above uses the optimistic "
        f"figure. At the pessimistic one the portfolio makes "
        f"**${deep['perweek']:+,.0f} a week** instead of "
        f"**${p['perweek']:+,.0f}**, with a max drawdown of "
        f"**${abs(deep['maxdd']):,.0f}**. Which of those two you get is "
        f"decided by the order book, which is not recorded yet.")
    log()
    ov = 0
    for cn in cons:
        s = T[T.con == cn]
        if s.rule.nunique() < 2:
            continue
        x = s[s.rule == RULES[0]["name"]]
        y = s[s.rule == RULES[1]["name"]]
        for st, en in zip(x.start, x.end):
            ov += int(((y.start < en) & (y.end > st)).sum())
    log(f"**Overlap:** the two rules hold at the same time on `{ov:,}` "
        f"occasions, which is `{ov/max(len(T),1)*100:.0f}%` of all trades. In "
        f"those moments two contracts are on and the risk is double what a "
        f"single-rule drawdown suggests. That is already inside the numbers "
        f"above — it is the reason to read the combined column rather than "
        f"adding the two.")
    log()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write("\n".join(L) + "\n")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
