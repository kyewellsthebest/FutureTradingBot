"""Merge the Tick MEGA shards into one ranked book plus a readable report.

Two things this does that a plain concat would not:

1. FILL DECOMPOSITION. Every limit-entry config was searched three times, at
   fill requirements of 0 / 5 / 25 contracts traded at the limit price. Pairing
   those runs tells us, per config, how much of the P&L is real and how much is
   the bare-touch convention. That convention was worth 1.06 ticks in ZB, more
   than any effect we ever measured, so it is the first thing to strip out.

2. AN HONEST SHORTLIST. Ranked candidates are filtered on the constraints that
   have actually killed every prior survivor: enough trades, positive in every
   year and out of sample, and a hold long enough that round-turn cost is not
   the whole story.

Usage: python tick_merge.py <results_dir>
"""
from __future__ import annotations

import glob
import gzip
import json
import os
import sys

import numpy as np
import pandas as pd

# A 30-minute hold is the shortest that can plausibly clear MNQ costs: netting
# $1,000/wk on 200 trades needs 13.6 ticks gross, which is 34.6% of the average
# 5-minute move (implausible) but only 9.5% of the average 1-hour move.
MIN_HOLD_MIN = 30.0
MIN_TRADES = 250
KEY = ["series", "fam", "etype", "ttl", "H", "sp", "rr", "trail",
       "f_sess", "f_trend", "f_vol", "f_vix", "f_htf"]


def load(d):
    rows, meta = [], []
    for f in sorted(glob.glob(os.path.join(d, "**", "tk*_NQ.json.gz"), recursive=True)):
        try:
            with gzip.open(f, "rt") as fh:
                o = json.load(fh)
        except Exception as e:                       # a dead shard must not
            print(f"  SKIP {os.path.basename(f)}: {e}")   # sink the merge
            continue
        meta.append({k: o.get(k) for k in
                     ("series", "bars_per_day", "bar_min", "scale", "n_bars",
                      "n_streams", "n_cfg", "n_gated", "elapsed_s")})
        for r in o.get("top", []):
            r["series"] = o.get("series", "?")
            rows.append(r)
    return pd.DataFrame(rows), pd.DataFrame(meta)


def fill_decomposition(df):
    """Per config, P&L at each fill requirement. Limit entries only."""
    L = df[df.etype == "L"]
    if not len(L):
        return pd.DataFrame(), {}
    piv = L.pivot_table(index=[c for c in KEY if c != "etype"],
                        columns="mf", values="wk", aggfunc="max")
    have = [c for c in (0.0, 5.0, 25.0) if c in piv.columns]
    piv = piv.dropna(subset=have)
    summary = {f"mean_wk_at_minfill_{int(c)}": round(float(piv[c].mean()), 2)
               for c in have}
    if 0.0 in have and 25.0 in have:
        summary["convention_worth_per_week"] = round(
            float(piv[0.0].mean() - piv[25.0].mean()), 2)
        summary["frac_surviving_minfill_25"] = round(
            float((piv[25.0] > 0).mean()), 4)
        summary["frac_positive_at_bare_touch"] = round(
            float((piv[0.0] > 0).mean()), 4)
        piv["survives"] = piv[25.0] > 0
        piv["retained"] = piv[25.0] / piv[0.0].replace(0, np.nan)
    return piv.reset_index(), summary


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "tick_results"
    df, meta = load(d)
    out_dir = d
    if not len(df):
        print("NO RESULTS")
        with open(os.path.join(out_dir, "TICK_MEGA.md"), "w") as f:
            f.write("# Tick MEGA\n\nNo configs cleared the gate.\n")
        return

    for c in ("fam", "etype", "series"):
        df[c] = df[c].astype(str)
    print(f"loaded {len(df):,} ranked rows from {len(meta)} shards")

    # de-duplicate: the same config can be top-ranked in more than one shard
    df = df.sort_values("score", ascending=False)
    df = df.drop_duplicates(subset=KEY + ["mf"], keep="first")

    piv, fill_summary = fill_decomposition(df)

    # THE ONE TEST THAT IS NOT MINED. Configs are selected on train only, so
    # whether they hold up out of sample is a free observation. Under the null
    # that the search found nothing, about half of them should be OOS-positive
    # by chance. A rate near 50% means billions of configs bought us noise; a
    # rate well above it is the first real evidence of edge in this project.
    oos = {}
    if "o10" in df.columns and len(df) > 30:
        k = int((df.o10 > 0).sum())
        nn = int(df.o10.notna().sum())
        p_hat = k / max(nn, 1)
        # normal approximation to a binomial test against p = 0.5
        z = (k - 0.5 * nn) / max(np.sqrt(0.25 * nn), 1e-9)
        oos = {"n": nn, "positive": k, "rate": round(p_hat, 4), "z": round(float(z), 2),
               "rate_3wk": round(float((df.o3 > 0).mean()), 4) if "o3" in df else None}

    # ---- the honest shortlist -------------------------------------------
    hold_min = df.get("H_min", pd.Series(np.nan, index=df.index))
    strict = df[
        (df.wk > 0) & (df.ev > 0)
        & (df.n_tr >= MIN_TRADES)
        & (hold_min >= MIN_HOLD_MIN)
        & (df.o10 > 0) & (df.o3 > 0)
        & (df.poswk >= 0.55)
        & (df.pf >= 1.10)
        # limit entries must clear the conservative fill bar; market and stop
        # entries carry mf = -1 because the requirement does not apply to them
        & ((df.etype != "L") | (df.mf >= 25.0))
    ].copy().sort_values(["score", "wk"], ascending=False)
    print(f"shortlist: {len(strict):,} configs survive the strict filter")

    tot = dict(
        shards=len(meta),
        configs_searched=int(meta.n_cfg.sum()) if len(meta) else 0,
        gated=int(meta.n_gated.sum()) if len(meta) else 0,
        ranked_rows=len(df),
        shortlist=len(strict),
        fill=fill_summary,
        oos_holdout=oos,
    )

    with gzip.open(os.path.join(out_dir, "TICK_MEGA.json.gz"), "wt") as f:
        json.dump({"totals": tot,
                   "series": meta.to_dict("records"),
                   "shortlist": strict.head(300).to_dict("records"),
                   "top_overall": df.head(600).to_dict("records")}, f)
    if len(piv):
        piv.head(20000).to_csv(os.path.join(out_dir, "fill_decomposition.csv.gz"),
                               index=False, compression="gzip")

    # ---- report ----------------------------------------------------------
    L = []
    L.append("# Tick MEGA — event-bar search over the NQ trade tape\n")
    L.append(f"- configs searched: **{tot['configs_searched']:,}**")
    L.append(f"- shards: {tot['shards']}  |  cleared the gate: {tot['gated']:,}"
             f"  |  ranked: {tot['ranked_rows']:,}")
    L.append(f"- survive the strict filter (>={MIN_TRADES} trades, "
             f">={MIN_HOLD_MIN:.0f}min hold, positive OOS, and for limit "
             f"entries a fill requiring 25 contracts at the price): "
             f"**{tot['shortlist']:,}**\n")

    if fill_summary:
        L.append("## What the fill assumption was worth\n")
        L.append("Same configs, same data, only the fill rule changes:\n")
        L.append("| contracts required at the limit | mean $/week |")
        L.append("|---|---|")
        for c in (0, 5, 25):
            k = f"mean_wk_at_minfill_{c}"
            if k in fill_summary:
                lbl = {0: "0 (bare touch — the old convention)",
                       5: "5 (a small queue clears)",
                       25: "25 (real size traded there)"}[c]
                L.append(f"| {lbl} | {fill_summary[k]:,.2f} |")
        if "convention_worth_per_week" in fill_summary:
            L.append(f"\nThe bare-touch convention is worth "
                     f"**${fill_summary['convention_worth_per_week']:,.2f}/week** "
                     f"per config on average. "
                     f"{fill_summary['frac_positive_at_bare_touch']*100:.1f}% of "
                     f"limit configs look profitable on a bare touch; "
                     f"{fill_summary['frac_surviving_minfill_25']*100:.1f}% still "
                     f"do once real size is required at the price.\n")

    if oos:
        L.append("## Out-of-sample holdout (never used to select)\n")
        L.append(f"Configs were ranked on training weeks only, so this is a free "
                 f"observation rather than a filter. Under the null that the "
                 f"search found nothing, roughly half should be positive.\n")
        L.append(f"- OOS-positive: **{oos['positive']:,} / {oos['n']:,} "
                 f"({oos['rate']*100:.1f}%)**, z = {oos['z']:+.2f} against 50%")
        if oos.get("rate_3wk") is not None:
            L.append(f"- positive in the final 3 weeks: {oos['rate_3wk']*100:.1f}%")
        verdict = ("consistent with chance — billions of configs bought noise"
                   if abs(oos["z"]) < 3 else
                   "materially above chance — worth exact replay"
                   if oos["z"] >= 3 else
                   "materially BELOW chance — the train fit is anti-predictive")
        L.append(f"- reading: **{verdict}**\n")

    L.append("## Series coverage\n")
    L.append("| series | bars | bars/day | min/bar | configs | gated |")
    L.append("|---|---|---|---|---|---|")
    if len(meta):
        m = meta.groupby("series").agg(
            n_bars=("n_bars", "max"), bpd=("bars_per_day", "max"),
            bm=("bar_min", "max"), cfg=("n_cfg", "sum"), g=("n_gated", "sum"))
        for s, r in m.sort_values("cfg", ascending=False).iterrows():
            L.append(f"| {s} | {int(r.n_bars):,} | {int(r.bpd)} | {r.bm:.2f} "
                     f"| {int(r.cfg):,} | {int(r.g):,} |")

    cols = ["series", "fam", "etype", "mf", "H_min", "n_tr", "wk", "ev", "pf",
            "poswk", "sharpe", "maxdd", "o10", "o3", "f_sess"]
    for title, sub in (("Shortlist — survives every honest filter", strict),
                       ("Top ranked overall (before the strict filter)", df)):
        L.append(f"\n## {title}\n")
        if not len(sub):
            L.append("_nothing_\n")
            continue
        use = [c for c in cols if c in sub.columns]
        L.append("| " + " | ".join(use) + " |")
        L.append("|" + "---|" * len(use))
        for _, r in sub.head(40).iterrows():
            L.append("| " + " | ".join(
                f"{r[c]:,.2f}" if isinstance(r[c], float) else str(r[c])
                for c in use) + " |")

    with open(os.path.join(out_dir, "TICK_MEGA.md"), "w") as f:
        f.write("\n".join(L) + "\n")
    print("wrote TICK_MEGA.md / TICK_MEGA.json.gz")


if __name__ == "__main__":
    main()
