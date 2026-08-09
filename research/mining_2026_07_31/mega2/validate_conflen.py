"""The one honest test left: does conf_len survive on data the search never saw?

Out of 103,680 structural strategies, one family topped the edge ranking and it
was coherent rather than scattered: `conf_len` at R=20 with a stop at 1.5x the
recent median swing, long side, +3 to +4pp above geometry-and-shuffle.

conf_len is how long the confirmation took -- after the swing low, how many
price changes did price need to travel 20 points back up. A high value means a
SLOW, grinding recovery rather than a sharp snap-back. The claim is: after a
slow grind up off a low, go long.

That is a story, and stories are cheap after the fact. Three reasons to doubt it:

  * the best of 81,348 tries is +4.16pp, while pure chance at that sample size
    produces +7.51pp, so it is not even an impressive maximum
  * nine of the top twelve are the same family at the same scale, which is
    either one mechanism or one lucky corner counted twelve times
  * every survivor is long, on a market that rose

And one reason it deserves a real test: the five TRAINING contracts -- 389
million price changes -- were excluded from the entire search. They are clean.
Nothing about them influenced which strategies rose to the top, so if conf_len
is a mechanism it shows up there at similar strength, and if it is selection
noise it collapses to zero.

Same two controls as the search: each trade's own geometry S/(S+T), and the
identical measurement on a shuffled-increment tape. This is the test that
distinguishes a finding from a story.
"""
import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DELAY", "1")
import structsearch as S  # noqa: E402

OUT = os.path.join(S.ROOT, "research", "VALIDATE_CONFLEN.md")
TRAIN = ["NQU4", "NQZ4", "NQH5", "NQM5", "NQU5"]
HOLD = ["NQH6", "NQM6", "NQZ5"]
# the family that topped the search, exactly as it was specified there
CAND = [("conf_len", 0.78, ("m1.5", 1.5), ("r1.0", -1.0), 1),
        ("conf_len", 0.7, ("m1.5", 1.5), ("r1.0", -1.0), 1),
        ("conf_len", 0.6, ("m1.5", 1.5), ("r1.0", -1.0), 1),
        ("conf_len", 0.5, ("m1.5", 1.5), ("r1.0", -1.0), 1),
        ("conf_len", 0.78, ("m1.5", 1.5), ("r0.75", -0.75), 1),
        ("conf_len", 0.7, ("m1.5", 1.5), ("mm0.6", 0.6), 1),
        ("conf_len", 0.7, ("m1.5", 1.5), ("mm1.0", 1.0), 1),
        ("prev_size", 0.5, ("m1.5", 1.5), ("r1.0", -1.0), 1)]
R = 20
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def prep(tape, key):
    P = S.pivot_frame(tape, R)
    if P is None:
        return None
    P["pcpiv"] = tape[P["piv"]].astype(np.float64)
    ent, up, dn = S.tau_tables(tape, P["conf"])
    row = np.full(len(P["conf"]), -1, np.int64)
    pos = np.searchsorted(ent, P["conf"])
    h = (pos < len(ent)) & (ent[np.minimum(pos, len(ent) - 1)] == P["conf"])
    row[h] = pos[h]
    P["row"] = row
    P["thr"] = {}
    return P, up, dn


rng = np.random.default_rng(S.SEED + 1)
store = {}
for p in sorted(glob.glob(os.path.join(S.CACHE, "NQ*_R4.npz"))):
    c = os.path.basename(p).split("_")[0]
    pc = np.load(p, allow_pickle=False)["pc"].astype(np.int64)
    d = np.diff(pc).copy()
    rng.shuffle(d)
    sh = np.r_[pc[0], pc[0] + np.cumsum(d)].astype(np.int64)
    store[(c, "real")] = prep(pc, c)
    store[(c, "shuf")] = prep(sh, c + "s")
    print(f"  {c} ready", flush=True)

log("# Does conf_len survive on data the search never saw?")
log()
log("One family topped the 103,680-strategy search and it was coherent rather "
    "than scattered: `conf_len` at 20-point structure, stop at 1.5x the recent "
    "median swing, long. It says that after a **slow, grinding** recovery off a "
    "low — as opposed to a sharp snap-back — price continues up.")
log()
log("The five TRAINING contracts, 389 million price changes, were excluded "
    "from that entire search. Nothing about them influenced which strategies "
    "rose to the top. If this is a mechanism it appears there at similar "
    "strength; if it is selection noise it collapses.")
log()
log("| strategy | split | trades | hit | geometry | above geo | shuffle | "
    "**edge** | $/trade | net |")
log("|---|---|---|---|---|---|---|---|---|---|")
res = {}
for feat, q, sr, tr, sd in CAND:
    tag = f"{feat}>=q{q:g} stop={sr[0]} tgt={tr[0]}"
    for split, cs in (("HELD-OUT (was searched)", HOLD),
                      ("TRAINING (never searched)", TRAIN)):
        acc = {}
        for src in ("real", "shuf"):
            N = H = G = 0
            gr = 0.0
            for c in cs:
                k = (c, src)
                if store.get(k) is None:
                    continue
                P, up, dn = store[k]
                r = S.evaluate(P, None, up, dn, feat, q, sr, tr, sd)
                if r is None:
                    continue
                N += r["n"]; H += r["hit"] * r["n"]; G += r["geo"] * r["n"]
                gr += r["gross"] * r["n"]
            if N:
                acc[src] = (N, H / N, G / N, gr / N)
        if "real" not in acc or "shuf" not in acc:
            continue
        n, h, g, gross = acc["real"]
        _, sh_, sg, _ = acc["shuf"]
        edge = (h - g) - (sh_ - sg)
        res.setdefault(tag, {})[split] = (edge, n, gross)
        log(f"| `{tag}` | {split} | {n:,} | {h*100:.2f}% | {g*100:.2f}% | "
            f"{(h-g)*100:+.2f} pp | {(sh_-sg)*100:+.2f} pp | "
            f"**{edge*100:+.2f} pp** | ${gross:+.3f} | ${gross-S.COST:+.2f} |")
log()
log("## The verdict")
log()
he = [v["HELD-OUT (was searched)"][0] for v in res.values()
      if "HELD-OUT (was searched)" in v]
te = [v["TRAINING (never searched)"][0] for v in res.values()
      if "TRAINING (never searched)" in v]
if he and te:
    log(f"| | mean edge | strategies positive |")
    log(f"|---|---|---|")
    log(f"| held-out, which the search selected on | "
        f"**{np.mean(he)*100:+.2f} pp** | {sum(1 for x in he if x > 0)}/{len(he)} |")
    log(f"| training, which it never touched | "
        f"**{np.mean(te)*100:+.2f} pp** | {sum(1 for x in te if x > 0)}/{len(te)} |")
    log()
    keep = np.mean(te) / np.mean(he) if np.mean(he) else float("nan")
    log(f"Retention: **{keep*100:.0f}%** of the edge carries to untouched data.")
    log()
    if np.mean(te) > 0.5 * np.mean(he) and sum(1 for x in te if x > 0) >= len(te) * 0.7:
        log("**It survives.** The edge is not an artifact of choosing the best "
            "of 103,680 on one sample — it reproduces where selection had no "
            "reach. That makes it the first structural result in this repo "
            "worth carrying to a trade-level replay.")
    else:
        log("**It does not survive.** The edge was a property of the contracts "
            "the search picked it on, which is what selecting the best of "
            "103,680 does to noise. No trade-level replay is warranted.")
log()
log("---")
log("Same two controls as the search. First touch on the real tick sequence. "
    "The training contracts were excluded from the search by construction, so "
    "nothing about them shaped which strategies were ranked highest.")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w").write("\n".join(L) + "\n")
print("\nwrote", OUT)
