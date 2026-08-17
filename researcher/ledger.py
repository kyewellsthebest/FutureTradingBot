"""Persistent memory for the autonomous researcher.

Three jobs, and the second is the one that makes continuous search safe
rather than actively harmful.

  1  NEVER RETEST. Every hypothesis is fingerprinted. A corpse is never
     dug up, so the search always moves into new ground.

  2  COUNT THE TRIALS AND RAISE THE BAR. This is the whole reason a
     24/7 searcher does not simply manufacture a beautiful lie. The
     best-of-N maximum of pure noise grows roughly as sqrt(2 ln N)
     standard deviations, so a fixed threshold guarantees a false
     positive eventually -- the more compute you spend, the more
     convincing it looks. The bar therefore rises with the number of
     trials already spent. This is the Bonferroni/deflated-Sharpe idea
     applied to a process that never stops.

  3  SEAL A VAULT. The most recent slice of history is never touched by
     the search. A hypothesis may be tested against it AT MOST ONCE,
     ever, and only after it has already survived everything else. Once
     a candidate touches the vault, that touch is recorded permanently
     -- so the vault cannot be mined by attrition.

This repo has measured the cost of ignoring point 2: hypothesis ledger
entry #19 records 1.38 billion configurations with a NEGATIVE return to
searching harder -- as selection tightened, holdout performance fell
from -1.13 to -243 pips while the hit rate rose to 65.9%. Tighter
selection found configs that win often and lose enormously. A continuous
searcher without a rising bar reproduces that outcome faster.
"""
import hashlib
import json
import math
import os
import time
from datetime import datetime, timezone

DEFAULT = os.path.join(os.environ.get("RESEARCH_DIR", "data/research"),
                       "ledger.json")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Ledger:
    def __init__(self, path=None):
        self.path = path or DEFAULT
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.d = {"trials": 0, "tested": {}, "survivors": [],
                  "vault_touches": {}, "families": {},
                  "started": _now(), "halts": []}
        if os.path.exists(self.path):
            try:
                self.d.update(json.load(open(self.path)))
            except Exception:                                 # noqa: BLE001
                self.d["halts"].append(
                    {"t": _now(), "why": "ledger unreadable, restarted"})

    # ---------- identity ----------
    @staticmethod
    def fingerprint(hyp: dict) -> str:
        """Stable id for a hypothesis, independent of dict ordering."""
        s = json.dumps(hyp, sort_keys=True, separators=(",", ":"))
        return hashlib.sha1(s.encode()).hexdigest()[:16]

    def seen(self, hyp) -> bool:
        return self.fingerprint(hyp) in self.d["tested"]

    # ---------- the rising bar ----------
    def bar(self, extra=0) -> float:
        """Significance threshold in sigmas, given trials already spent.

        The expected maximum of N independent standard normals is about
        sqrt(2 ln N). Requiring that plus a margin means the bar rises
        as the search continues, so spending more compute cannot by
        itself produce a "finding". At 100 trials this is ~3.0 sigma; at
        100,000 it is ~4.8.
        """
        n = max(self.d["trials"] + extra, 1)
        return max(3.0, math.sqrt(2.0 * math.log(n)) + 0.8)

    def record(self, hyp, result: dict, family=None):
        fp = self.fingerprint(hyp)
        self.d["trials"] += 1
        self.d["tested"][fp] = {
            "t": _now(), "hyp": hyp, "result": result,
            "bar_at_test": round(self.bar(), 2), "family": family}
        if family:
            f = self.d["families"].setdefault(
                family, {"n": 0, "best_z": -99.0, "sum_edge": 0.0})
            f["n"] += 1
            f["best_z"] = max(f["best_z"], float(result.get("z", -99)))
            f["sum_edge"] += float(result.get("edge", 0.0))
        if float(result.get("z", 0)) >= self.bar():
            self.d["survivors"].append({"t": _now(), "fp": fp,
                                        "hyp": hyp, "result": result})
        return fp

    # ---------- the sealed vault ----------
    def can_touch_vault(self, hyp) -> bool:
        return self.fingerprint(hyp) not in self.d["vault_touches"]

    def touch_vault(self, hyp, result):
        fp = self.fingerprint(hyp)
        if fp in self.d["vault_touches"]:
            raise RuntimeError(
                f"vault already used for {fp} -- a hypothesis gets ONE "
                f"look at held-back data, ever. Re-testing it is how a "
                f"holdout stops being a holdout.")
        self.d["vault_touches"][fp] = {"t": _now(), "result": result}

    # ---------- family priors ----------
    def family_prior(self, family) -> float:
        """Weight for allocating effort. Families that have produced
        nothing across many trials get less attention -- not zero,
        because a family is not disproved by its members failing, but
        less. This is the only "learning" claimed here and it is
        deliberately modest."""
        f = self.d["families"].get(family)
        if not f or f["n"] < 5:
            return 1.0
        mean_edge = f["sum_edge"] / f["n"]
        decay = 1.0 / (1.0 + 0.06 * f["n"])
        boost = 1.0 + max(0.0, mean_edge) * 4.0
        return max(0.05, decay * boost)

    def halt(self, why):
        self.d["halts"].append({"t": _now(), "why": why})
        self.save()

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(self.d, fh, indent=1)
        os.replace(tmp, self.path)

    def summary(self) -> dict:
        fam = sorted(self.d["families"].items(),
                     key=lambda kv: -kv[1]["best_z"])
        return {
            "trials": self.d["trials"],
            "current_bar_sigma": round(self.bar(), 2),
            "distinct_tested": len(self.d["tested"]),
            "survivors": len(self.d["survivors"]),
            "vault_used": len(self.d["vault_touches"]),
            "families": [{"name": k, "n": v["n"],
                          "best_z": round(v["best_z"], 2)}
                         for k, v in fam[:12]],
            "halts": self.d["halts"][-5:],
            "started": self.d.get("started"),
        }
