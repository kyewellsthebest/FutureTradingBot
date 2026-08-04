"""Fold every shard's leaderboard back into the standing ones, and write the
one page worth reading.

Shards each hunt in isolation and each come home with their own board. Merging
is not just concatenation: rows are only comparable within a friction regime,
and the same parameter vector found by two shards is one finding, not two.
"""
import json, os, sys, glob
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ART = sys.argv[1] if len(sys.argv) > 1 else "boards"


def fold(name, keyfn, cap):
    rows, standing = [], os.path.join(HERE, name)
    if os.path.exists(standing):
        rows += json.load(open(standing)).get("best", [])
    runs = evals = 0
    for f in glob.glob(os.path.join(ART, "**", name), recursive=True):
        try:
            b = json.load(open(f))
        except Exception:
            continue
        rows += b.get("best", []); runs += b.get("runs", 0); evals += b.get("evals", 0)
    seen, ded = set(), []
    for r in sorted(rows, key=lambda x: -x.get("wkly", 0)):
        k = keyfn(r)
        if k in seen: continue
        seen.add(k); ded.append(r)
    ded = ded[:cap]
    json.dump({"best": ded, "runs": runs, "evals": evals}, open(standing, "w"), indent=1)
    return ded, runs, evals


sb, sr, se = fold("hunter_board.json", lambda r: (
    r.get("mkt"), r.get("tf"), r.get("mech", "imp"), r.get("slip"), r.get("commx"),
    round(r.get("lb", 0)), round(r.get("k", 0), 1), round(r.get("pb", 0), 2),
    round(r.get("sp", 0), 1), r.get("maxpos")), 400)
mb, mr, me = fold("multi_board.json", lambda r: (
    r.get("mech"), r.get("tf"), r.get("slip"), r.get("commx"),
    round(r.get("lb", 0)), round(r.get("k", 0), 1), round(r.get("pb", 0), 2),
    round(r.get("sp", 0), 1), round(r.get("rr", 0), 1)), 300)

L = ["# Standing leaderboard", "",
     f"Single-market: {se:,} parameter vectors evaluated over {sr:,} runs.",
     f"Multi-market: {me:,} vectors over {mr:,} runs.", "",
     "Every row is net of commission and exit slippage at the rate stamped on it.",
     "`holdout` columns are the last quarter of history, never used to select.", ""]

if mb:
    d = pd.DataFrame(mb)
    L += ["## One strategy, every market", "",
          "The shape that matters: a single parameter vector run on every market",
          "at once, with the position limit applied to the merged book. Counts as",
          "one strategy against the cap of four.", "",
          d.head(15)[["mech", "tf", "nmkt", "risk", "tpw", "wr", "wkly", "ho_wkly",
                      "maxdd", "worst_wk", "green_wk", "streak"]].to_markdown(index=False), ""]
else:
    L += ["## One strategy, every market", "", "_Nothing has survived yet._", ""]

if sb:
    d = pd.DataFrame(sb)
    L += ["## Single market", "",
          d.head(20)[["mkt", "tf", "mech", "risk", "tpw", "wr", "wkly", "maxdd",
                      "worst_wk", "green_wk", "streak", "ho"]].to_markdown(index=False), "",
          "### by mechanism", "",
          d.groupby("mech").agg(found=("wkly", "size"), best_wkly=("wkly", "max"),
                                med_tpw=("tpw", "median"), med_wr=("wr", "median"),
                                med_holdout=("ho", "median")).round(3).to_markdown(), ""]

open(os.path.join(HERE, "LEADERBOARD.md"), "w").write("\n".join(L))
print("\n".join(L[:40]))
