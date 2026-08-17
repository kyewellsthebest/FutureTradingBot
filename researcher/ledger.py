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
import threading
import time
from datetime import datetime, timezone

DEFAULT = os.path.join(os.environ.get("RESEARCH_DIR", "data/research"),
                       "ledger.json")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# THE AUTHORITATIVE LIVE TRIAL COUNT.
#
# The console's headline number used to be mirrored by hand in the search
# loop, which meant it was only correct on the code path that remembered
# to mirror it. Feature scoring goes through bump() in bulk and never
# touched the mirror, so the number on screen froze for minutes at a time
# while the search was working perfectly -- the display looked dead
# because it was reading a copy nobody had updated.
#
# Every path that changes the trial count goes through _record or bump,
# both in this file and both under the lock, so setting it here means
# there is no path left that can forget. The API reads it without taking
# the lock: an int assignment is atomic and a reader that is one trial
# behind does not matter.
LIVE_TRIALS = {"n": 0, "t": 0.0}


class Ledger:
    def __init__(self, path=None):
        # THREAD SAFETY. Market sweeps run in parallel and all of them
        # write here. `self.d["trials"] += 1` is a read-modify-write, so
        # without this lock concurrent sweeps LOSE trial increments --
        # and a trial count that is too low makes the significance bar
        # too low, which is the one direction of error that manufactures
        # findings rather than hiding them.
        self._lock = threading.RLock()
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
        # seed the live mirror so the console shows the real total the
        # instant the process comes back, not 0 until the first trial
        LIVE_TRIALS["n"] = max(LIVE_TRIALS["n"], int(self.d["trials"]))

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
        with self._lock:
            return self._record(hyp, result, family)

    def _record(self, hyp, result: dict, family=None):
        fp = self.fingerprint(hyp)
        self.d["trials"] += 1
        LIVE_TRIALS["n"] = self.d["trials"]
        LIVE_TRIALS["t"] = time.time()
        self.d["tested"][fp] = {
            "t": _now(), "hyp": hyp, "result": result,
            "bar_at_test": round(self.bar(), 2), "family": family,
            "epoch": self.DATA_EPOCH}
        if family:
            f = self.d["families"].setdefault(
                family, {"n": 0, "best_z": -99.0, "sum_edge": 0.0})
            f["n"] += 1
            f["best_z"] = max(f["best_z"], float(result.get("z", -99)))
            f["sum_edge"] += float(result.get("edge", 0.0))
        # NOT a survivor yet. Clearing the bar only makes something a
        # CANDIDATE; it still has to survive the delay control, the
        # empirical null, period stability, the stale placebo and the
        # vault. Counting it here made the console report "47 strategies
        # found" on a cycle where all 47 were killed as artifacts -- the
        # single most misleading thing this dashboard could say.
        return fp

    def confirm(self, hyp, result, note=""):
        """Record something that survived the WHOLE gauntlet."""
        with self._lock:
            self.d["survivors"].append(
                {"t": _now(), "fp": self.fingerprint(hyp), "hyp": hyp,
                 "result": result, "note": note})
            self._save()
        return fp

    # ---------- the sealed vault ----------
    def can_touch_vault(self, hyp) -> bool:
        return self.fingerprint(hyp) not in self.d["vault_touches"]

    def touch_vault(self, hyp, result):
        with self._lock:
            return self._touch_vault(hyp, result)

    def _touch_vault(self, hyp, result):
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

    # Bump when the underlying DATA changes in a way that invalidates
    # past measurements. Entries stamped with an older epoch are not
    # results any more -- they are measurements of a tape that no longer
    # exists -- so they are excluded from the leaderboard and from the
    # survivor list.
    #
    # 2 : tier-2 bars were built from unsorted ticks. 85.3% of rows in
    #     the raw files are out of chronological order and close was
    #     taken as the last row in FILE order, making every close a
    #     random trade from inside its bar. Everything measured on the
    #     deep tier before the sort was a measurement of noise.
    DATA_EPOCH = 2

    # WHICH TAPES EACH EPOCH ACTUALLY INVALIDATED.
    #
    # A data epoch says "the tape changed", but it almost never changes
    # ALL of it. The tick-sorting bug lived in tier-2 bar construction;
    # tier-1 five-minute bars come from a different file entirely and
    # tier-3 book snapshots were never rebuilt. Treating an epoch bump
    # as invalidating every past measurement wiped the leaderboard to
    # zero rows -- 209,170 hypotheses tested and nothing to show -- while
    # the search itself was working perfectly. That is a worse lie than
    # showing a stale row, because it reports the search as barren when
    # what actually happened is that the display threw its own results
    # away.
    #
    # An epoch with no entry here is unscoped and does invalidate
    # everything, which is the safe default for a change nobody has
    # characterised.
    EPOCH_SCOPE = {
        2: (2,),        # deep tick tier only
    }

    def stale(self, rec):
        """Was this measured on a tape that has since been corrected?

        Scoped by tier: an entry is only stale if one of the epochs it
        predates actually touched the tape it was measured on.
        """
        e = int(rec.get("epoch") or 1)
        if e >= self.DATA_EPOCH:
            return False
        tier = (rec.get("hyp") or {}).get("tier")
        for ep in range(e + 1, self.DATA_EPOCH + 1):
            scope = self.EPOCH_SCOPE.get(ep)
            if scope is None:
                return True            # uncharacterised bump: assume all
            if tier is None:
                return True            # cannot tell which tape: assume so
            if int(tier) in scope:
                return True
        return False

    def epoch_summary(self):
        n = sum(1 for r in self.d["tested"].values() if self.stale(r))
        return {"epoch": self.DATA_EPOCH, "stale_entries": n}

    def kill(self, hyp, reasons):
        """Record that a candidate FAILED the gauntlet, permanently.

        Without this the ledger only knows a hypothesis cleared the bar,
        and the leaderboard keeps showing it forever -- including
        artifacts found before a control existed. The deployed console
        was ranking "after close_low, go long" first at 97% win and RR
        6.06, a pure order-statistic artifact, on the same screen as
        "0 strategies found".
        """
        with self._lock:
            rec = self.d["tested"].get(self.fingerprint(hyp))
            if rec is not None:
                rec["killed"] = {"t": _now(), "reasons": list(reasons)[:6]}

    def near_misses(self, k=20):
        """The best things found, whether or not they passed.

        A console that only shows what cleared the bar shows nothing for
        weeks and looks broken. The near-misses are the honest picture of
        what the search is actually turning up, and they carry their own
        warning: these did NOT pass, most of them are the top of a pile
        of noise, and the highest z out of tens of thousands of trials is
        expected to be large even when nothing is there.
        """
        # RANK BY SIGNED z AMONG THINGS THAT AT LEAST PAY, not by |z|.
        # Sorting on absolute z surfaced cells at z = -160: those are not
        # near-misses, they are the search discovering with total
        # confidence that something loses money. Closeness to passing
        # means a positive net and a z approaching the bar.
        #
        # ADMISSION IS GRADED, not all-or-nothing. Something has been
        # tested a quarter of a million times; "nothing to show" is never
        # the honest answer, it just means every row was excluded by a
        # filter. So: prefer clean rows, fall back to stale ones, fall
        # back to killed ones, and label whatever gets shown. The board
        # is empty only when the search genuinely has not run.
        def gather(allow_stale, allow_killed):
            rows = []
            for fp, rec in self.d["tested"].items():
                killed = bool(rec.get("killed"))
                if killed and not allow_killed:
                    continue      # failed a control; not a near miss
                st = self.stale(rec)
                if st and not allow_stale:
                    continue      # measured on data that has since been
                                  # corrected; not a result any more
                r = rec.get("result") or {}
                if not r:
                    continue
                z = float(r.get("z", 0) or 0)
                net = float(r.get("net", 0) or 0)
                # net-positive first, then by z. A net-negative cell can
                # still be listed if nothing pays, but it ranks below.
                rows.append(((1 if net > 0 else 0), z, fp, rec, st, killed))
            rows.sort(key=lambda t: (t[0], t[1]), reverse=True)
            # DEDUPE IDENTICAL MEASUREMENTS. Two hypotheses can describe
            # the same cell by different routes and get separate
            # fingerprints, which put the same result in first AND second
            # place. On a board of five that is a fifth of the display
            # spent saying one thing twice.
            seen, uniq = set(), []
            for row in rows:
                r = row[3].get("result") or {}
                sig = (round(float(r.get("z", 0) or 0), 4),
                       round(float(r.get("net", 0) or 0), 4),
                       r.get("n"))
                if sig in seen:
                    continue
                seen.add(sig)
                uniq.append(row)
            return uniq

        for allow_stale, allow_killed in ((False, False), (True, False),
                                          (True, True)):
            rows = gather(allow_stale, allow_killed)
            if rows:
                break

        out = []
        for _pos, _z, fp, rec, st, killed in rows[:k]:
            r = rec.get("result") or {}
            out.append({"fp": fp, "hyp": rec.get("hyp", {}),
                        "family": rec.get("family"),
                        "z": r.get("z"), "net": r.get("net"),
                        "gross": r.get("edge"), "n": r.get("n"),
                        "win_rate": r.get("win_rate"), "rr": r.get("rr"),
                        "per_week": r.get("per_week"),
                        "bar_at_test": rec.get("bar_at_test"),
                        "checked": bool(rec.get("checked")),
                        "stale": st,
                        "killed": bool(killed),
                        "kill_reasons": (rec.get("killed") or {}).get(
                            "reasons", []) if killed else [],
                        "passed": bool(r.get("z", 0) >= (rec.get("bar_at_test") or 99)
                                       and r.get("net", 0) > 0
                                       and not killed and not st)})
        return out

    def halt(self, why):
        self.d["halts"].append({"t": _now(), "why": why})
        self.save()

    def bump(self, n):
        """Add n trials atomically. Feature scoring is search too."""
        with self._lock:
            self.d["trials"] += int(n)
            LIVE_TRIALS["n"] = self.d["trials"]
            LIVE_TRIALS["t"] = time.time()

    def save(self):
        with self._lock:
            return self._save()

    def _save(self):
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
