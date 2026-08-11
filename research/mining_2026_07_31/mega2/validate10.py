"""Every top strategy, run on the quarters it was not found in.

WHAT KILLED THE FIRST TWO. Each was profitable in the single quarter the
search discovered it in and lost money almost everywhere else -- rule A green
in one quarter of eight, rule B in three, together -$228 a week with a
drawdown six times the account. The search's sigma had already said so: 4.76
against a 6.28 noise ceiling means "this is what randomness produces", and out
of sample it behaved exactly like randomness.

So the question for the rest is not "how much does it make" but "does it
survive a quarter it was not fitted to". This runs every distinct top
strategy across all eight and reports the two numbers that matter: what it
earns at home, and what it earns everywhere else.

TWO THINGS THIS FILE IS CAREFUL ABOUT, both learned the hard way today.

  DEDUPLICATION FIRST. The top five by dollars-per-week were four copies of
  one rule with thresholds nudged by 0.02 -- the dig reporting its own
  neighbours. Validating a "top ten" naively would test one strategy ten
  times and call the agreement confirmation. Strategies are keyed by their
  SET of features, side and bar size, and only the best of each family runs.

  THE RECORD IS THE TRUTH, NOT THE LABEL. Reconstructing rule A by reading its
  text got both the direction and the bar size wrong -- SHORT on 500-tick bars
  when it was LONG on 250 -- and produced a clean sign flip, -$2.14 a trade
  against the +$2.35 reported. It only surfaced because the home quarter was
  run at all. So the home quarter is now the CONTROL: if a reconstruction
  cannot reproduce the search's own number on the quarter it came from,
  nothing else in its row means anything, and the row is flagged rather than
  quietly believed.
"""
import json
import os
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402
import hunt  # noqa: E402
import mega  # noqa: E402

OUT = os.environ.get("OUT_MD", os.path.join(fuse.ROOT, "research", "VALIDATE.md"))
TOPN = int(os.environ.get("TOPN", "10"))
TV, TPX, COST = 0.50, 0.25, 1.24
MAKER, MAKER_DEEP = 0.355, -0.102
ACCOUNT = 4100.0
STATES = ["data/mega6_state.json", "data/mega_state.json",
          "data/mega_state_tight.json"]
LEG = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)([<>])([0-9.]+)")
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def parse(rec):
    """Legs and combiner from the label; side, bars and bracket from the
    record. Only the leg thresholds live in the text."""
    f = rec["feat"].replace("DIG ", "").strip()
    m = re.match(r"^(\d+)of\((.*)\)$", f)
    if m:
        k, body = int(m.group(1)), m.group(2)
    elif "|" in f:
        k, body = 1, f
    elif "&" in f:
        body = f
        k = len(LEG.findall(body))
    else:
        body, k = f, 1
    legs = [(a, 1 if op == ">" else -1, float(q))
            for a, op, q in LEG.findall(body)]
    if not legs:                       # a bare single feature, no threshold
        legs = [(f, int(rec["side"]), float(rec["q"]))]
        k = 1
    return dict(k=min(k, len(legs)), legs=legs, side=int(rec["side"]),
                stop=int(rec["stop"]), tgt=int(rec["tgt"]), K=int(rec["K"]),
                home=rec["con"], claim_dol=float(rec["dol"]),
                claim_tpw=float(rec["tpw"]), zd=float(rec["zd"]),
                passive=bool(rec["passive"]), feat=f)


def load():
    """Best of each distinct family, across every search this repo ran."""
    rows = []
    for p in STATES:
        fp = os.path.join(fuse.ROOT, p)
        if not os.path.exists(fp):
            continue
        try:
            rows += json.load(open(fp)).get("rows", [])
        except Exception:                                        # noqa: BLE001
            continue
    d = pd.DataFrame(rows)
    if not len(d):
        return []
    # price the passive credit honestly before ranking, or the ranking is of
    # the optimism rather than of the strategies
    d["dr"] = d.dol.where(~d.passive, d.dol - 1.00 + MAKER)
    d["wr"] = d.dr * d.tpw
    d = d[d.wr > 0].sort_values("wr", ascending=False)
    seen, out = set(), []
    for _, r in d.iterrows():
        legs = LEG.findall(r["feat"].replace("DIG ", ""))
        key = (frozenset(a for a, _, _ in legs) or frozenset([r["feat"]]),
               int(r["side"]), int(r["K"]))
        if key in seen:
            continue
        seen.add(key)
        out.append(parse(r))
        if len(out) >= TOPN:
            break
    return out


def signal(F, rule, n):
    tot, have = np.zeros(n, dtype=np.int16), 0
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


def evaluate(B, F, rule):
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
    return pd.DataFrame(dict(ts=pd.to_datetime(B["ts"][idx]),
                             pnl=r[idx] - COST + MAKER,
                             pnl_deep=r[idx] - COST + MAKER_DEEP,
                             days=days))


def specs(s):
    d = s.set_index(s.ts.dt.floor("D")).pnl.resample("D").sum()
    d = d[d.index.dayofweek < 5]
    if not len(d):
        return None
    eq = d.cumsum()
    wk = d.resample("W").sum()
    run = cur = 0
    for v in d:
        cur = cur + 1 if v < 0 else 0
        run = max(run, cur)
    return dict(perweek=float(wk.mean()), bestwk=float(wk.max()),
                worstwk=float(wk.min()), dd=float((eq - eq.cummax()).min()),
                streak=run, green=float((d > 0).mean()), tot=float(d.sum()))


def main():
    rules = load()
    if not rules:
        print("no candidates")
        return
    meta = fuse.tape_meta()
    cons = [c for c in fuse.NQ_CONTRACTS if c in meta]
    need = sorted({(cn, r["K"]) for cn in cons for r in rules})
    print(f"{len(rules)} distinct strategies x {len(cons)} quarters "
          f"({len(need)} feature builds)", flush=True)

    res = {i: {} for i in range(len(rules))}
    for cn, K in need:
        try:
            B, F = mega.features(cn, K)
        except Exception as e:                                   # noqa: BLE001
            print(f"{cn} K{K}: {type(e).__name__}: {e}", flush=True)
            continue
        for i, r in enumerate(rules):
            if r["K"] != K:
                continue
            try:
                t = evaluate(B, F, r)
            except Exception:                                    # noqa: BLE001
                continue
            if t is not None:
                res[i][cn] = t
        print(f"  built {cn} K{K}", flush=True)
        del B, F

    log("# Do any of them survive a quarter they were not fitted to?")
    log()
    log(f"The first two did not. Each was profitable in the single quarter it "
        f"was discovered in and lost money almost everywhere else — together "
        f"**−$228 a week** with a drawdown six times the account. The sigma "
        f"had already said so: 4.76 against a 6.28 noise ceiling means *this "
        f"is what randomness produces*, and out of sample it behaved exactly "
        f"like randomness.")
    log()
    log(f"So the question here is not how much each makes. It is whether any "
        f"of them survives a quarter it was not fitted to. `{len(rules)}` "
        f"distinct strategies, `{len(cons)}` quarters, priced at the "
        f"**+$0.355** a trade that resting a limit was actually measured to be "
        f"worth rather than the flat two ticks the search assumed.")
    log()
    log("Deduplicated by feature set, side and bar size first — the top five "
        "by dollars per week were four copies of one rule with thresholds "
        "nudged by 0.02, the dig reporting its own neighbours. Testing that "
        "as ten strategies would be testing one, ten times, and calling the "
        "agreement confirmation.")
    log()
    log("| # | strategy | side | home | **home $/tr** | **out-of-sample "
        "$/tr** | green qtrs | claimed | check |")
    log("|---|---|---|---|---|---|---|---|---|")
    summary = []
    for i, r in enumerate(rules):
        got = res[i]
        if not got:
            continue
        hm = got.get(r["home"])
        hdol = float(hm.pnl.mean()) if hm is not None else float("nan")
        oos = [t for c, t in got.items() if c != r["home"]]
        odol = float(pd.concat(oos).pnl.mean()) if oos else float("nan")
        green = sum(1 for c, t in got.items() if t.pnl.mean() > 0)
        # the control: does the home quarter reproduce what the search said?
        claim_repriced = (r["claim_dol"] - 1.00 + MAKER if r["passive"]
                          else r["claim_dol"])
        ok = (abs(hdol - claim_repriced) < 0.60) if hm is not None else False
        name = ", ".join(f"`{a}`" for a, _, _ in r["legs"])[:70]
        summary.append((i, r, hdol, odol, green, len(got)))
        log(f"| {i+1} | {r['k']}of({name}) | "
            f"{'L' if r['side'] > 0 else 'S'} | {r['home']} | "
            f"${hdol:+.2f} | **${odol:+.2f}** | {green}/{len(got)} | "
            f"${claim_repriced:+.2f} | {'ok' if ok else '**MISMATCH**'} |")
    log()
    log("`out-of-sample $/tr` is the only column that matters. `check` "
        "compares the home quarter against what the search claimed, repriced "
        "for execution — a mismatch means the reconstruction is wrong and the "
        "whole row should be ignored, which is exactly how a direction error "
        "was caught earlier today.")
    log()

    good = [(i, r, h, o, g, n) for i, r, h, o, g, n in summary if o > 0]
    log("## Verdict")
    log()
    if not good:
        log(f"**Not one of the {len(summary)} strategies is profitable out of "
            f"sample.** Every single one makes money in the quarter it was "
            f"found in and loses money on average across the others. That is "
            f"not a marginal result or a tuning problem — it is what "
            f"overfitting looks like when you go and check, and it is the "
            f"same answer the selection ceiling gave before any of these "
            f"were backtested.")
    else:
        log(f"**{len(good)} of {len(summary)} are positive out of sample.** "
            f"Full specs below. Positive out of sample is necessary, not "
            f"sufficient — with {len(summary)} tested, roughly "
            f"{len(summary)*0.5:.0f} would land positive by chance alone, so "
            f"the size and the consistency across quarters matter more than "
            f"the sign.")
        log()
        log("| strategy | $/week | best wk | worst wk | max drawdown | "
            "longest losing streak | green days |")
        log("|---|---|---|---|---|---|---|")
        for i, r, h, o, g, n in sorted(good, key=lambda z: -z[3]):
            allt = pd.concat([t for c, t in res[i].items()
                              if c != r["home"]])
            sp = specs(allt)
            if not sp:
                continue
            log(f"| {i+1} · {r['k']}of(...) {'L' if r['side'] > 0 else 'S'} | "
                f"**${sp['perweek']:+,.0f}** | ${sp['bestwk']:+,.0f} | "
                f"${sp['worstwk']:+,.0f} | ${abs(sp['dd']):,.0f} "
                f"({abs(sp['dd'])/ACCOUNT:.0%} of account) | "
                f"{sp['streak']} days | {sp['green']:.0%} |")
    log()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write("\n".join(L) + "\n")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
