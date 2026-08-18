"""What the searcher has worked out, written for whoever searches next.

THE DIVISION OF LABOUR THIS FILE EXISTS TO SERVE.

The searcher is better than any person at four things: volume, memory,
uniform application of controls, and never getting bored. It tested
359,074 hypotheses in a day, forgot none of them, charged every look
against a rising bar, and put every survivor through the same six
checks in the same order every time.

It is worse than a person at exactly one thing, and it is the thing
that decides whether any of the rest matters: it optimises inside the
question it was given and never asks whether that is the question. It
computed `cu = +110 RT` and `z = 0.151` for the same cell and had no
mechanism to notice those cannot both be true. It reported the same
silence for a family it had tested and found empty as for a family it
could not express. It spent a third of a million trials without once
computing whether an edge of a plausible size could have been seen.

So this module does not try to make the searcher reason. It makes the
searcher REPORT, in the form that the reasoning needs:

    RULED OUT      where we looked, how small an edge we could have
                   seen, and therefore what is now genuinely excluded
    BLIND          where we looked and could NOT have seen anything
                   worth having, so the silence means nothing
    UNREACHABLE    where the question could not be asked at all
    CONTRADICTIONS numbers that cannot both be true
    CONSTRAINT     which of those is currently the binding one
    NEXT           what follows from the four above

Nothing here is a new measurement. Every number already existed
somewhere in the ledger, the archive, the memory or the calibration.
What did not exist was any place they were put together and turned into
a conclusion, which is why finding each of the above took a person
reading four files and doing arithmetic in their head.

A brief that says "nothing found" is a failure of this module. "Nothing
found, here is what that does and does not rule out, and here is the
one thing stopping us" is the job.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone

# An edge larger than this is, by this project's own standing rule, far
# more likely to be a bug than a discovery -- six of them have been, and
# zero have been real. Any cell whose smallest detectable effect is
# above it could only ever have found bug territory, and its silence is
# therefore uninformative.
BUG_TERRITORY_RT = float(os.environ.get("BRIEF_BUG_RT", "1.0"))
# The largest edge worth planning around. Reachability analysis puts a
# plausible real edge well under this.
PLAUSIBLE_RT = float(os.environ.get("BRIEF_PLAUSIBLE_RT", "0.30"))


def _num(v, d=None):
    try:
        f = float(v)
        return f if f == f else d
    except (TypeError, ValueError):
        return d


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------- sections
def coverage(led):
    """What has been looked at, and how small an edge each look could see.

    The distinction the console never drew: a cell that found nothing
    and COULD have seen +0.2 RT has ruled out +0.2 RT there. A cell that
    found nothing and could only have seen +9 RT has ruled out nothing
    at all. Counting both as "tested" is how 359,074 trials came to feel
    like evidence of absence when most of them were not evidence of
    anything.
    """
    seen = blind = informative = 0
    best_mde = None
    mdes = []
    for rec in (led.get("tested") or {}).values():
        if not isinstance(rec, dict) or rec.get("stub"):
            continue
        r = rec.get("result") or {}
        if not r:
            continue
        seen += 1
        m = _num(r.get("mde"))
        if m is None or m <= 0:
            continue
        mdes.append(m)
        if m > BUG_TERRITORY_RT:
            blind += 1
        else:
            informative += 1
            if best_mde is None or m < best_mde:
                best_mde = m
    mdes.sort()

    def pct(q):
        if not mdes:
            return None
        i = min(len(mdes) - 1, int(q / 100.0 * len(mdes)))
        return round(mdes[i], 3)

    return {
        "measured": seen,
        "informative": informative,
        "blind": blind,
        "blind_share": round(blind / seen, 3) if seen else None,
        "smallest_edge_ever_visible": (round(best_mde, 4)
                                       if best_mde is not None else None),
        "mde_p10": pct(10), "mde_p50": pct(50), "mde_p90": pct(90),
    }


def ruled_out(led, min_cells=200):
    """Per family: what size of edge its silence actually excludes.

    A family is only "ruled out" down to the smallest edge its own cells
    had the power to detect. Reported per family because the answer
    differs by an order of magnitude between them, and a single global
    claim would be wrong in both directions at once.
    """
    fams = {}
    for rec in (led.get("tested") or {}).values():
        if not isinstance(rec, dict) or rec.get("stub"):
            continue
        r = rec.get("result") or {}
        fam = rec.get("family")
        if not fam or not r:
            continue
        m = _num(r.get("mde"))
        d = fams.setdefault(fam, {"cells": 0, "informative": 0,
                                  "best_mde": None, "best_z": None})
        d["cells"] += 1
        z = _num(r.get("z"))
        if z is not None and (d["best_z"] is None or z > d["best_z"]):
            d["best_z"] = z
        if m is None or m <= 0:
            continue
        if m <= BUG_TERRITORY_RT:
            d["informative"] += 1
            if d["best_mde"] is None or m < d["best_mde"]:
                d["best_mde"] = m
    out = []
    for fam, d in fams.items():
        if d["cells"] < min_cells:
            continue
        out.append({
            "family": fam, "cells": d["cells"],
            "informative_cells": d["informative"],
            "best_z": round(d["best_z"], 2) if d["best_z"] is not None else None,
            "excludes_edges_above": (round(d["best_mde"], 3)
                                     if d["best_mde"] is not None else None),
            "verdict": ("nothing ruled out -- every cell was blind"
                        if not d["informative"] else
                        f"edges above {d['best_mde']:.3f} RT are excluded here"),
        })
    out.sort(key=lambda r: (r["excludes_edges_above"] is None,
                            r["excludes_edges_above"] or 9e9))
    return out


def unreachable(mem, min_n=20):
    """Families the searcher could not ASK, as opposed to could not find.

    This is the section that would have caught the feature grower being
    unable to see high and low. A family here has not been tested and
    must never be counted as explored.
    """
    out = []
    for fam, f in (mem.get("families") or {}).items():
        n = int(f.get("n") or 0)
        une = int(f.get("unevaluable") or 0)
        if n < min_n or not une:
            continue
        share = une / n
        if share < 0.25:
            continue
        out.append({"family": fam, "attempts": n, "unevaluable": une,
                    "share": round(share, 3),
                    "verdict": ("this family has NOT been tested -- the "
                                "question could not be asked on these "
                                "tapes")})
    out.sort(key=lambda r: -r["share"])
    return out


def contradictions(led, arch, k=12):
    """Numbers that cannot both be true, stated as such.

    Every real bug this project has found was noticed this way first: a
    figure that could not be right, reasoned back to its cause. That
    step is encoded here so it happens on every cycle instead of when
    somebody happens to look.
    """
    # GROUPED BY KIND, not listed one per cell. Twelve map cells all
    # showing the same impossibility is ONE finding about the search,
    # and printing it twelve times buries whatever else is in here.
    groups = {}

    def add(kind, where, claim, why, sort=0.0):
        g = groups.setdefault(kind, {"kind": kind, "count": 0,
                                     "worst": None, "why_impossible": why,
                                     "_s": -9e9})
        g["count"] += 1
        if sort > g["_s"]:
            g["_s"] = sort
            g["worst"] = {"where": where, "claim": claim}

    for key, c in ((arch or {}).get("cells") or {}).items():
        cu, z = _num(c.get("cu")), _num(c.get("z"))
        n, eff = _num(c.get("n")), _num(c.get("eff_n"))
        # NO cu-VERSUS-z CHECK. An earlier version flagged "a big
        # effect at a small z" as impossible. It is not merely weak, it
        # is VACUOUS: z is defined as cu/se, so a large cu with a small
        # z means exactly and only that se is large. The condition can
        # never be violated and it fired on fifteen cells in the first
        # live brief, every one of them ordinary noise, each carrying
        # the instruction "one of the two numbers is wrong". A detector
        # that manufactures leads is worse than no detector, because
        # acting on it costs the time this file exists to save.
        #
        # What DOES contradict is a raw trade count read as a sample
        # size, below -- that is a real error and the numbers really
        # cannot both be what they appear to be.
        if cu is not None and eff is not None and eff < 30 and abs(cu) > 1.0:
            add("a big number from almost no data",
                f"map cell {key} ({c.get('market')})",
                f"{cu:+.2f} RT on {eff:,.0f} independent observations",
                ("the mean of a few overlapping observations can be "
                 "anything; a selection maximum, not a measurement error "
                 "-- never breed from it or show it as a finding"),
                sort=abs(cu))
        if n and eff and eff < n / 20.0 and n >= 200:
            add("trade count is not a sample size",
                f"map cell {key} ({c.get('market')})",
                f"{n:,.0f} trades but {eff:,.0f} independent "
                f"({n / max(eff, 1):.0f}x overlap)",
                ("holds that span many bars make consecutive trades "
                 "share most of their path; the raw count must never be "
                 "read as evidence"),
                sort=n / max(eff, 1))

    out = []
    for g in groups.values():
        g.pop("_s", None)
        w = g.pop("worst") or {}
        out.append({"where": w.get("where", "?"),
                    "claim": (f"{g['count']} cells -- worst: {w.get('claim')}"
                              if g["count"] > 1 else w.get("claim")),
                    "kind": g["kind"], "count": g["count"],
                    "why_impossible": g["why_impossible"]})
    out.sort(key=lambda r: -r["count"])
    for rec in (led.get("tested") or {}).values():
        if not isinstance(rec, dict) or rec.get("stub"):
            continue
        r = rec.get("result") or {}
        wr, net, rr = _num(r.get("win_rate")), _num(r.get("net")), _num(r.get("rr"))
        if wr is not None and net is not None and rr is not None:
            if wr > 0.70 and net < 0 and rr > 0.9:
                out.append({
                    "where": f"{(rec.get('hyp') or {}).get('market')} "
                             f"{rec.get('family')}",
                    "claim": f"wins {wr:.0%} at RR {rr:.2f} and still "
                             f"loses {net:+.3f}/trade",
                    "why_impossible": ("winning most trades at parity "
                                       "reward-to-risk cannot lose money "
                                       "unless the cost or the fill model "
                                       "is wrong"),
                })
        if len(out) >= k:
            break
    return out[:k]


def binding_constraint(cov, led, mem, cal, ruled):
    """The one sentence a person would write after reading the rest.

    Ordered, because these are not independent and the first true one
    makes the others moot. There is no point tuning the controls if
    nothing can reach them, and no point widening the search if the
    search cannot see.
    """
    trials = int(led.get("trials") or 0)
    survivors = len(led.get("survivors") or [])
    fams = mem.get("families") or {}
    tot = sum(int(f.get("n") or 0) for f in fams.values()) or 1
    une = sum(int(f.get("unevaluable") or 0) for f in fams.values())
    confirmed = sum(int(f.get("confirmed") or 0) for f in fams.values())
    killed = len([1 for rec in (led.get("tested") or {}).values()
                  if isinstance(rec, dict) and rec.get("killed")])

    if une / tot > 0.40:
        return {
            "constraint": "EXPRESSIVENESS",
            "says": (f"{une:,} of {tot:,} attempts ({une/tot:.0%}) could "
                     f"not be evaluated at all. Most of what the searcher "
                     f"draws, it cannot ask."),
            "do": ("fix the generator or the tape columns before reading "
                   "anything else here -- these results are a sample "
                   "selected by what the code can express"),
        }
    blind_share = cov.get("blind_share")
    if blind_share is not None and blind_share > 0.75:
        return {
            "constraint": "POWER",
            "says": (f"{blind_share:.0%} of measured cells could not have "
                     f"detected an edge below {BUG_TERRITORY_RT:.1f} RT. "
                     f"Their silence is not evidence of absence."),
            "do": ("spend the budget where detection is possible: shorter "
                   "holds, tighter brackets, higher-frequency cells, and "
                   "pooling -- not more trials in the same places"),
        }
    if confirmed == 0 and trials > 50_000:
        return {
            "constraint": "NOTHING REACHES THE CONTROLS",
            "says": (f"{trials:,} trials and not one cell has cleared the "
                     f"bar to even be tested by the gauntlet."),
            "do": ("the bar is doing its job; the question is whether the "
                   "space being searched can contain an edge that clears "
                   "it, which is a question about WHERE to look, not how "
                   "much"),
        }
    if confirmed and survivors == 0 and killed:
        return {
            "constraint": "CONTROLS",
            "says": (f"{confirmed} cells cleared the bar and {killed} were "
                     f"killed by a control. The search finds things; the "
                     f"checks reject them."),
            "do": ("read the kill reasons -- if one control dominates, "
                   "that is the artifact the search keeps rediscovering"),
        }
    if survivors:
        return {
            "constraint": "NONE -- there is something to verify",
            "says": f"{survivors} survivor(s) are through every control.",
            "do": "reproduce out of sample before anything else happens",
        }
    return {
        "constraint": "UNCLEAR",
        "says": "no single factor dominates the current failure profile.",
        "do": "widen coverage and re-read next cycle",
    }


def next_actions(cov, unreach, contra, ruled, cal):
    """What follows, ranked, each with the observation that implies it."""
    acts = []
    for u in unreach[:3]:
        acts.append({
            "priority": 1,
            "do": f"make {u['family']} expressible, or drop it",
            "because": (f"{u['unevaluable']:,} of {u['attempts']:,} "
                        f"attempts could not be asked, so this family is "
                        f"counted as explored and has not been"),
        })
    for c in contra[:3]:
        acts.append({
            "priority": 1,
            "do": f"explain or fix: {c['claim']} at {c['where']}",
            "because": c["why_impossible"],
        })
    bs = cov.get("blind_share")
    if bs is not None and bs > 0.5:
        acts.append({
            "priority": 2,
            "do": ("move the budget to cells that can see -- shorter "
                   "holds, tighter exits, more markets pooled"),
            "because": (f"{bs:.0%} of everything measured could not have "
                        f"detected an edge worth having, and every one of "
                        f"those trials still raised the bar for the rest"),
        })
    reach = (cal or {}).get("reachability") or []
    good = [r for r in reach
            if _num(r.get("smallest_edge_rt"), 9e9) <= PLAUSIBLE_RT]
    if reach and not good:
        acts.append({
            "priority": 2,
            "do": ("get finer data or more markets -- no hold on the "
                   "current tapes can resolve a plausible edge"),
            "because": (f"the best reachable size on this tape is "
                        f"{min(_num(r.get('smallest_edge_rt'), 9e9) for r in reach):.3f} "
                        f"RT, against a plausible edge of "
                        f"{PLAUSIBLE_RT:.2f} RT"),
        })
    elif good:
        acts.append({
            "priority": 3,
            "do": (f"concentrate on holds up to "
                   f"{max(int(_num(r.get('hold_s'), 0)) for r in good)}s"),
            "because": ("those are the only holds on this tape where a "
                        "plausible edge is resolvable at all"),
        })
    solid = [r for r in ruled if r.get("excludes_edges_above") is not None]
    if solid:
        acts.append({
            "priority": 4,
            "do": (f"stop re-testing {solid[0]['family']}"),
            "because": (f"{solid[0]['cells']:,} cells there already "
                        f"exclude edges above "
                        f"{solid[0]['excludes_edges_above']:.3f} RT"),
        })
    acts.sort(key=lambda a: a["priority"])
    return acts


# ---------------------------------------------------------------- build
def build(led, mem, arch=None, cal=None, status=None, experiments=None):
    """The whole brief, from state the searcher already had."""
    led = led or {}
    mem = mem or {}
    cov = coverage(led)
    ruled = ruled_out(led)
    unreach = unreachable(mem)
    contra = contradictions(led, arch)
    return {
        "t": _now(),
        "trials": int(led.get("trials") or 0),
        "survivors": len(led.get("survivors") or []),
        "coverage": cov,
        "ruled_out": ruled,
        "unreachable": unreach,
        "contradictions": contra,
        "binding_constraint": binding_constraint(cov, led, mem, cal, ruled),
        # ANSWERS TO QUESTIONS SOMEBODY ASKED, as opposed to the search's
        # own output. These are the ones a person wrote down and the
        # searcher answered while they were away.
        "experiments": [
            {"name": k, "question": v.get("question"),
             "runs": v.get("runs"), "verdict": v.get("verdict"),
             "error": v.get("error")}
            for k, v in sorted((experiments or {}).items())
            if v.get("verdict") or v.get("error")],
        "next": next_actions(cov, unreach, contra, ruled, cal),
    }


def render(b):
    """The brief as text, for a person or for the next model to read."""
    L = []
    A = L.append
    A(f"RESEARCH BRIEF  {b['t']}")
    A(f"{b['trials']:,} trials charged, {b['survivors']} survivor(s)")
    A("")
    bc = b["binding_constraint"]
    A(f"BINDING CONSTRAINT: {bc['constraint']}")
    A(f"  {bc['says']}")
    A(f"  -> {bc['do']}")
    A("")
    c = b["coverage"]
    A("WHAT THE COVERAGE ACTUALLY BUYS")
    A(f"  {c['measured']:,} cells measured")
    A(f"  {c['informative']:,} could have seen an edge worth having")
    A(f"  {c['blind']:,} could not -- their silence means nothing")
    if c.get("smallest_edge_ever_visible") is not None:
        A(f"  smallest edge ever visible anywhere: "
          f"{c['smallest_edge_ever_visible']:.3f} RT/trade")
    A("")
    if b["unreachable"]:
        A("NOT TESTED -- COULD NOT BE ASKED")
        for u in b["unreachable"]:
            A(f"  {u['family']}: {u['unevaluable']:,}/{u['attempts']:,} "
              f"({u['share']:.0%}) unevaluable")
        A("")
    if b["contradictions"]:
        A("CANNOT BOTH BE TRUE")
        for x in b["contradictions"]:
            A(f"  {x['where']}: {x['claim']}")
            A(f"      {x['why_impossible']}")
        A("")
    if b["ruled_out"]:
        A("GENUINELY RULED OUT")
        for r in b["ruled_out"][:8]:
            A(f"  {r['family']}: {r['cells']:,} cells -- {r['verdict']}")
        A("")
    if b.get("experiments"):
        A("QUESTIONS ANSWERED WHILE YOU WERE AWAY")
        for x in b["experiments"]:
            A(f"  {x['name']}  ({x['runs']} run(s))")
            A(f"      Q: {x['question']}")
            A(f"      A: {x.get('verdict') or ('FAILED: ' + str(x.get('error')))}")
        A("")
    A("NEXT")
    for a in b["next"]:
        A(f"  [{a['priority']}] {a['do']}")
        A(f"      because {a['because']}")
    return "\n".join(L)


def selftest(verbose=True):
    """The brief must not congratulate itself on blind coverage."""
    fails = []
    # a ledger of cells that all could see nothing
    blind = {"trials": 60000, "survivors": [], "tested": {}}
    for i in range(400):
        blind["tested"][f"{i:016x}"] = {
            "family": "shape/gap", "hyp": {"market": "NQ"},
            "result": {"z": 0.2, "mde": 9.0, "n": 300, "net": -0.5}}
    b = build(blind, {"families": {}})
    ok = (b["coverage"]["blind"] == 400
          and b["coverage"]["informative"] == 0
          and b["binding_constraint"]["constraint"] == "POWER")
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  400 blind cells are reported "
              f"as blind, not as coverage  — constraint "
              f"{b['binding_constraint']['constraint']}")
    if not ok:
        fails.append("blind coverage counted as evidence")

    # a family that cannot be asked must be named, not scored
    mem = {"families": {"feature/d1": {"n": 500, "unevaluable": 480}}}
    b2 = build({"trials": 500, "tested": {}, "survivors": []}, mem)
    ok = (b2["unreachable"] and b2["unreachable"][0]["family"] == "feature/d1"
          and b2["binding_constraint"]["constraint"] == "EXPRESSIVENESS")
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  a family that could not be "
              f"asked is reported as untested, not as empty")
    if not ok:
        fails.append("unevaluable family not surfaced")

    # a big number on almost no data must be named as such
    arch = {"cells": {"1,4,0,1": {"cu": 110.2, "z": 0.151, "n": 391,
                                  "eff_n": 2, "market": "NQ@NQM5@15s"}}}
    b3 = build({"trials": 1, "tested": {}, "survivors": []},
               {"families": {}}, arch=arch)
    ok = any("almost no data" in x["kind"] for x in b3["contradictions"])
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  '+110 RT on 2 independent "
              f"observations' is named as a selection maximum")
    if not ok:
        fails.append("did not flag the thin cell")

    # AND THE DETECTOR MUST NOT MANUFACTURE LEADS. A large effect with a
    # small z is not a contradiction -- z IS cu/se, so it means only
    # that se is large. The first live brief fired this on fifteen
    # ordinary cells, each with "one of the two numbers is wrong"
    # attached. Chasing a lead that cannot exist costs exactly the time
    # this module is meant to save.
    ordinary = {"cells": {"1,0,0,1": {"cu": 8.89, "z": 0.98, "n": 3000,
                                      "eff_n": 2000,
                                      "market": "NQ@NQZ5@15s"}}}
    b5 = build({"trials": 1, "tested": {}, "survivors": []},
               {"families": {}}, arch=ordinary)
    ok = not b5["contradictions"]
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  a large effect with a small "
              f"z on a REAL sample raises nothing  — "
              f"{len(b5['contradictions'])} flagged (expect 0)")
    if not ok:
        fails.append("manufactured a contradiction from z = cu/se")

    # informative silence IS reported as ruled out
    good = {"trials": 60000, "survivors": [], "tested": {}}
    for i in range(300):
        good["tested"][f"{i:016x}"] = {
            "family": "shape/run_dn", "hyp": {"market": "NQ"},
            "result": {"z": 0.4, "mde": 0.22, "n": 9000, "net": -0.01}}
    b4 = build(good, {"families": {}})
    ok = (b4["ruled_out"] and
          b4["ruled_out"][0]["excludes_edges_above"] is not None)
    if verbose:
        print(f"  {'PASS' if ok else 'FAIL'}  silence from cells that "
              f"COULD see is reported as a real exclusion  — "
              f"{b4['ruled_out'][0]['verdict'] if b4['ruled_out'] else 'none'}")
    if not ok:
        fails.append("informative silence not converted to an exclusion")
    return fails


if __name__ == "__main__":
    f = selftest()
    print("\nbrief selftest:", "PASS" if not f else f"FAIL {f}")
