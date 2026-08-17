"""Failure memory and self-calibration -- learning from mistakes, with
an actual mechanism behind each lesson.

WHY "IT LEARNS FROM ITS MISTAKES" IS USUALLY A LIE IN THIS DOMAIN.

The obvious design is: record which hypotheses lost, fit something to
that, and search where the fitted thing says to look. That is a model
trained on the search's own noise. It is precisely how 1.38 billion
configs produced a MEASURED NEGATIVE return to searching harder (ledger
#19) -- tighter selection found configs that won often and lost
enormously, because the selection was learning the noise.

So the learning here is restricted to lessons that have a MECHANISM,
not a correlation. Two of them:

  1  FAILURE MODE, NOT FAILURE. "It lost" carries no information -- 95%
     of everything loses. "It was directionally right at 8.4 sigma but
     the move was smaller than the round-trip cost" carries a great
     deal, and the correct response is not to abandon the idea but to
     hold it longer. That response follows from arithmetic (cost is
     fixed per trade, move size grows as sqrt(time)), not from fitting.

  2  ITS OWN SHRINKAGE. Every candidate that reaches the vault arrives
     with a predicted strength and leaves with a realised one. The
     ratio, measured across candidates, is this system's overfitting
     coefficient -- how much of what it finds in the search set is
     real. Nothing else in the pipeline measures that, and with enough
     touches it replaces the theoretical rising bar with an empirical
     one.

     Until there are touches, it reports that it does not know. A
     calibration with no observations behind it is the most dangerous
     object in a research system, because it looks like knowledge.

THE FAILURE MODES, and what each one licenses:

  thin          fewer trades than the minimum. Says nothing about the
                idea; says the bucket is rare. Licenses: aggregate the
                bucket with neighbours, or find it in more markets.
  no_signal     |z| inside the noise. The honest majority. Licenses
                nothing -- this is what a dead hypothesis looks like.
  wrong_sign    significantly negative. NOT an inverted edge to be
                flipped: flipping on the strength of a backtest sign is
                fitting the sign. Licenses only: note it, and if the
                whole family points one way, that is a real asymmetry
                worth a fresh, separately-counted hypothesis.
  cost_bound    gross edge positive and significant, net negative. The
                valuable failure. Licenses: longer holds in this family.
  vault_killed  survived everything and died on held-back data. The
                most informative event available, and it feeds
                calibration directly.
"""
import json
import math
import os
from datetime import datetime, timezone

MODES = ["thin", "no_signal", "wrong_sign", "cost_bound", "vault_killed",
         "confirmed"]


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def classify(result, bar, cost):
    """Why did this hypothesis die? Returns one of MODES.

    Order matters. cost_bound is checked before no_signal because a
    result can be strongly significant AND unprofitable, and calling
    that "no signal" throws away the only actionable failure there is.
    """
    if result is None:
        return "thin"
    z, net, gross = result["z"], result["net"], result["edge"]
    if result["n"] < 1:
        return "thin"
    if z >= bar and net > 0:
        return "confirmed"
    # gross edge clears cost-free significance but the cost eats it
    if gross > 0 and net <= 0:
        gz = z * (gross / max(abs(net), 1e-9)) if net else z
        if gross > 0.5 * cost or abs(gz) > bar:
            return "cost_bound"
    if z <= -bar:
        return "wrong_sign"
    return "no_signal"


class Memory:
    """Per-family failure profiles and the system's own shrinkage."""

    def __init__(self, path):
        self.path = path
        self.d = {"families": {}, "vault": [], "started": _now()}
        if os.path.exists(path):
            try:
                self.d.update(json.load(open(path)))
            except Exception:                                 # noqa: BLE001
                pass

    # ---------- failure profiles ----------
    def note(self, family, mode, result=None):
        f = self.d["families"].setdefault(
            family, {m: 0 for m in MODES} | {"n": 0, "best_gross": 0.0,
                                             "sum_hold": 0.0, "n_hold": 0})
        f["n"] += 1
        f[mode] = f.get(mode, 0) + 1
        if result:
            f["best_gross"] = max(f["best_gross"], float(result.get("edge", 0)))

    def note_hold(self, family, hold_s, was_cost_bound):
        f = self.d["families"].get(family)
        if f is not None and was_cost_bound:
            f["sum_hold"] += float(hold_s)
            f["n_hold"] += 1

    def lesson(self, family):
        """What this family's failure profile licenses. Mechanism only.

        Returns (advice, hold_multiplier). The multiplier is the ONLY
        thing that changes what gets searched, and it is bounded --
        a lesson that can reshape the search arbitrarily is a fitted
        model wearing a lesson's clothes.
        """
        f = self.d["families"].get(family)
        if not f or f["n"] < 20:
            return ("not enough failures to say anything", 1.0)
        n = f["n"]
        cb, thin = f.get("cost_bound", 0), f.get("thin", 0)
        if cb / n > 0.25:
            # directionally right, too small to pay. Cost is fixed per
            # trade and move size grows as sqrt(time), so the fix is
            # arithmetic, not search.
            return (f"{cb}/{n} failures were cost-bound: right direction, "
                    f"move smaller than the round trip. Extending holds.",
                    2.0)
        if thin / n > 0.50:
            return (f"{thin}/{n} failures were too thin to test. The "
                    f"buckets are rare, not wrong.", 1.0)
        if f.get("no_signal", 0) / n > 0.90 and n >= 200:
            return (f"{f['no_signal']}/{n} showed nothing at all. "
                    f"De-prioritised, not disproved.", 1.0)
        return ("mixed failures, no single mechanism indicated", 1.0)

    def hold_multiplier(self, family):
        return self.lesson(family)[1]

    # ---------- self-calibration ----------
    def note_vault(self, fam, z_search, z_vault, n_search, n_vault):
        self.d["vault"].append({"t": _now(), "family": fam,
                                "z_search": z_search, "z_vault": z_vault,
                                "n_search": n_search, "n_vault": n_vault})

    def shrinkage(self):
        """How much of what the search finds survives held-back data?

        This is the system watching its own predictions get killed. With
        no touches it says so -- an uncalibrated calibration that
        defaults to 1.0 would silently claim the search never overfits,
        which is the opposite of everything measured in this repo.
        """
        v = self.d["vault"]
        if not v:
            return {"n": 0, "known": False,
                    "note": "no candidate has reached the vault yet -- "
                            "shrinkage is UNKNOWN, not 1.0"}
        rs = [x["z_vault"] / x["z_search"] for x in v
              if x.get("z_search") and abs(x["z_search"]) > 1e-9
              and x.get("z_vault") is not None]
        if not rs:
            return {"n": len(v), "known": False, "note": "touches recorded "
                    "but no usable ratios"}
        rs.sort()
        med = rs[len(rs) // 2]
        return {"n": len(rs), "known": True,
                "median_ratio": round(med, 3),
                "kept": sum(1 for r in rs if r > 0.5),
                "note": (f"{sum(1 for r in rs if r > 0.5)}/{len(rs)} "
                         f"candidates kept more than half their apparent "
                         f"strength on held-back data")}

    def empirical_bar(self, theoretical):
        """Raise the theoretical bar by the measured shrinkage.

        If candidates historically keep only 40% of their search-set z,
        then a candidate needs 1/0.40 times the bar to be worth
        believing. Only applied once there are enough touches for the
        median to mean anything, and never allowed to LOWER the bar --
        a shrinkage estimate that says "we do not overfit" is far more
        likely to be a small sample than a fact.
        """
        s = self.shrinkage()
        if not s.get("known") or s["n"] < 5:
            return theoretical, "theoretical (no calibration data yet)"
        r = max(0.05, min(1.0, s["median_ratio"]))
        return (theoretical / r,
                f"theoretical {theoretical:.2f} / measured shrinkage "
                f"{r:.2f} across {s['n']} vault touches")

    # ---------- io ----------
    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(self.d, fh, indent=1)
        os.replace(tmp, self.path)

    def summary(self, top=8):
        out = []
        fams = sorted(self.d["families"].items(), key=lambda kv: -kv[1]["n"])
        for k, v in fams[:top]:
            adv, mult = self.lesson(k)
            out.append({"family": k, "n": v["n"],
                        "cost_bound": v.get("cost_bound", 0),
                        "no_signal": v.get("no_signal", 0),
                        "thin": v.get("thin", 0),
                        "hold_x": mult, "lesson": adv})
        return {"families": out, "shrinkage": self.shrinkage()}
