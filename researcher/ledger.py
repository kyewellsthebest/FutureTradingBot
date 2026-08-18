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


def _parse_t(v):
    """Epoch seconds from the ISO stamps _now() writes. None on junk.

    Entries written before timestamps were read back carry the same
    format, so this needs no migration -- but an unreadable stamp must
    return None rather than 0, or a window query would silently treat
    every ancient row as brand new.
    """
    try:
        s = str(v).replace("Z", "+00:00")
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.timestamp()
    except Exception:                                         # noqa: BLE001
        return None


def _num(v, default=0.0):
    """float() that survives None and junk. Used on result fields that
    legitimately do not exist for every kind of result."""
    try:
        f = float(v)
        return f if f == f else default        # NaN -> default
    except (TypeError, ValueError):
        return default


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
        # COMPACT IMMEDIATELY, before anything else allocates. Loading a
        # large ledger is the high-water mark of this process's memory
        # and the reason it was being OOM-killed on restart; shrinking
        # here means the peak is paid once rather than held forever.
        self._last_save = 0.0
        self._saved_trials = int(self.d.get("trials", 0))
        try:
            n = self._compact()
            if n:
                print(f"[ledger] compacted {n:,} old entries "
                      f"({len(self.d['tested']):,} total)", flush=True)
        except Exception:                                     # noqa: BLE001
            pass
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
            "epoch": self.DATA_EPOCH, "code_epoch": self.CODE_EPOCH}
        if family:
            f = self.d["families"].setdefault(
                family, {"n": 0, "best_z": -99.0, "sum_edge": 0.0})
            f["n"] += 1
            # `float(None)` raises, and a pooled result deliberately has
            # no single-market edge in dollars -- its currency is round
            # trips per trade. Reading these defensively rather than
            # assuming every result has every field.
            f["best_z"] = max(f["best_z"], _num(result.get("z"), -99.0))
            f["sum_edge"] += _num(result.get("edge"),
                                  _num(result.get("cu"), 0.0))
        # NOT a survivor yet. Clearing the bar only makes something a
        # CANDIDATE; it still has to survive the delay control, the
        # empirical null, period stability, the stale placebo and the
        # vault. Counting it here made the console report "47 strategies
        # found" on a cycle where all 47 were killed as artifacts -- the
        # single most misleading thing this dashboard could say.
        return fp

    def confirm(self, hyp, result, note=""):
        """Record something that survived the WHOLE gauntlet.

        `return fp` here referenced a name that does not exist in this
        scope -- a NameError primed to fire on the single most important
        event this system can produce, and unreachable until then.
        """
        fp = self.fingerprint(hyp)
        with self._lock:
            self.d["survivors"].append(
                {"t": _now(), "fp": fp, "hyp": hyp,
                 "result": result, "note": note})
            self._save(force=True)      # a survivor is never lost to a throttle
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

    # THE OTHER KIND OF STALENESS, and the one that actually bit.
    #
    # DATA_EPOCH covers the tape changing underneath a measurement.
    # CODE_EPOCH covers the MEASUREMENT ITSELF being superseded: a row
    # scored before ENTRY_LAG existed was allowed to enter at the bar it
    # was selected on, and a row scored before the delay control existed
    # was never asked whether its edge survives entering one bar later.
    # Those are not weak results, they are not results.
    #
    # This was not hypothetical. A ledger built by the current engine
    # holds 907 close_low/close_high rows whose best z is 0.92; the
    # deployed ledger, built partly before the fix, holds the same family
    # at z = 8.52 paying $7.14 a trade. Same idea, same market, same
    # bar -- the only difference is which version measured it. Without
    # this stamp the leaderboard ranks the pre-fix artifacts first, and
    # they are the most convincing thing on the screen.
    #
    # 2 : entries must clear ENTRY_LAG (no entering on the selection
    #     bar), the one-bar delay control, honest stop fills, and the
    #     full round-trip cost including the spread.
    CODE_EPOCH = 2

    def code_stale(self, rec):
        """Measured by an engine version whose controls have since changed."""
        if not isinstance(rec, dict) or rec.get("stub"):
            return False
        return int(rec.get("code_epoch") or 1) < self.CODE_EPOCH

    def outdated(self, rec):
        """Either kind of staleness. Not presentable as a finding."""
        return self.stale(rec) or self.code_stale(rec)

    def stale(self, rec):
        """Was this measured on a tape that has since been corrected?

        Scoped by tier: an entry is only stale if one of the epochs it
        predates actually touched the tape it was measured on.
        """
        if not isinstance(rec, dict) or rec.get("stub"):
            return False        # a stub carries no result to be stale
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
        n = sum(1 for r in self.d["tested"].values() if self.stale(r))  # noqa
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
            if isinstance(rec, dict) and not rec.get("stub"):
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
                if not isinstance(rec, dict) or rec.get("stub"):
                    continue        # compacted away; nothing to rank
                killed = bool(rec.get("killed"))
                if killed and not allow_killed:
                    continue      # failed a control; not a near miss
                # A row re-scored by backfill carries current numbers and
                # has been through the current controls, so it counts as
                # current whatever epoch it was born in.
                st = self.outdated(rec) and not rec.get("rescored")
                if st and not allow_stale:
                    continue      # measured on data, or by an engine,
                                  # that has since been corrected
                r = rec.get("result") or {}
                if not r:
                    continue
                z = _num(r.get("z"))
                # A pooled mechanism has no dollars-per-trade: its
                # currency is round trips per trade, because that is the
                # only unit comparable across markets whose ticks differ
                # by sixty times. Rank on whichever it has.
                net = _num(r.get("net"), _num(r.get("cu")))
                # net-positive first, then by z. A net-negative cell can
                # still be listed if nothing pays, but it ranks below.
                # `st` drove admission; the row reports the two kinds of
                # staleness separately so the console can say which one
                # applies instead of blaming the tape for a code change.
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
                        # WHEN IT WAS FOUND. The board ranks by strength
                        # and strength is a HIGH-WATER MARK, so a good
                        # early result sits at the top for weeks and the
                        # board looks frozen no matter how much work has
                        # happened since. Without a date there is no way
                        # to tell a searcher that has found nothing new
                        # from one that has stopped searching -- and
                        # those are opposite conditions.
                        "t": rec.get("t"),
                        "eff_n": r.get("eff_n"),
                        "z": r.get("z"), "net": r.get("net"),
                        "gross": r.get("edge"), "n": r.get("n"),
                        # cross-market rows carry a different currency:
                        # round trips per trade, and how many markets
                        # agreed. Rendering those as "$/trade" would be
                        # a category error on the front page.
                        "cu": r.get("cu"), "k": r.get("k"),
                        "mde": r.get("mde"),
                        "agree": r.get("agree"),
                        "pooled": bool(r.get("pooled")),
                        "win_rate": r.get("win_rate"), "rr": r.get("rr"),
                        "per_week": r.get("per_week"),
                        "per_week_per_market": r.get("per_week_per_market"),
                        "bar_at_test": rec.get("bar_at_test"),
                        "checked": bool(rec.get("checked")),
                        "stale": self.stale(rec) and not rec.get("rescored"),
                        "code_stale": self.code_stale(rec)
                                      and not rec.get("rescored"),
                        "outdated": st,
                        "killed": bool(killed),
                        "kill_reasons": (rec.get("killed") or {}).get(
                            "reasons", []) if killed else [],
                        "passed": bool(
                            _num(r.get("z")) >= (rec.get("bar_at_test") or 99)
                            and _num(r.get("net"), _num(r.get("cu"))) > 0
                            and not killed and not st)})
        return out

    def recent_best(self, hours=24, k=5):
        """The best of what was measured RECENTLY, however it ranks overall.

        THE COMPLAINT THIS ANSWERS, verbatim: "it's showing the exact
        same strategies, no updates ... after 200,000 searches it hasn't
        found one strategy, even if unprofitable, that's a bit better
        than the five we found this morning."

        That observation was correct and the board was not broken. It
        ranks by strength, strength is a MAXIMUM over everything ever
        tested, and a maximum only moves when something beats it. The
        top of the board sat at z 5.37 against a bar of 5.77, so every
        one of those 200,000 later trials -- almost all of which score
        below 3 -- left it untouched. A frozen high-water mark is what
        SUCCESS at not overfitting looks like, and it is visually
        identical to a dead process. That is the actual defect: not the
        ranking, the absence of any second view.

        So this reports the best of a WINDOW. It moves every cycle
        because it is not a maximum over all time, and comparing it with
        the all-time board is what tells you whether the search is still
        turning anything up.
        """
        now = time.time()
        rows = []
        for fp, rec in self.d["tested"].items():
            if not isinstance(rec, dict) or rec.get("stub"):
                continue
            ts = _parse_t(rec.get("t"))
            if ts is None or now - ts > hours * 3600.0:
                continue
            r = rec.get("result") or {}
            if not r:
                continue
            z = _num(r.get("z"))
            net = _num(r.get("net"), _num(r.get("cu")))
            rows.append(((1 if net > 0 else 0), z, fp, rec))
        rows.sort(key=lambda t: (t[0], t[1]), reverse=True)
        out = []
        for _pos, z, fp, rec in rows[:k]:
            r = rec.get("result") or {}
            h = rec.get("hyp") or {}
            out.append({
                "fp": fp, "hyp": h, "family": rec.get("family"),
                "t": rec.get("t"), "z": r.get("z"),
                "net": r.get("net"), "cu": r.get("cu"), "n": r.get("n"),
                "eff_n": r.get("eff_n"), "mde": r.get("mde"),
                "k": r.get("k"), "agree": r.get("agree"),
                "pooled": bool(r.get("pooled")),
                "market": h.get("market"),
                "bar_at_test": rec.get("bar_at_test"),
                "killed": bool(rec.get("killed"))})
        return {"hours": hours, "considered": len(rows), "rows": out}

    def halt(self, why):
        self.d["halts"].append({"t": _now(), "why": why})
        self.save(force=True)

    def bump(self, n):
        """Add n trials atomically. Feature scoring is search too."""
        with self._lock:
            self.d["trials"] += int(n)
            LIVE_TRIALS["n"] = self.d["trials"]
            LIVE_TRIALS["t"] = time.time()

    def charge_features(self, scope, names):
        """How many of these feature names have never been charged before.

        The feature library is in-memory only, so every restart regrows
        it and the caller used to charge the whole thing again -- the
        same look paid for twice, or in production twenty-eight times.
        Since the bar rises as sqrt(2 ln N), phantom trials do not merely
        misreport effort, they raise the standard that every real
        hypothesis has to clear.

        Records the names under their scope (market/tier), because the
        same feature expression grown on ES is a different look from the
        one grown on NQ and does deserve its own trial. Returns the
        count to charge; the caller bumps.

        This is a set of short strings, not results, so it costs a few
        hundred kilobytes at the sizes involved and compacts with
        everything else.
        """
        with self._lock:
            seen = self.d.setdefault("features_charged", {})
            have = seen.get(scope)
            if have is None:
                have = seen[scope] = []
            hs = set(have)
            new = [n for n in names if n not in hs]
            have.extend(new)
            # BOUNDED, oldest first. The kept set is small and churns
            # slowly, so this is generous -- but "small and churns
            # slowly" is an observation about today's grower, and an
            # unbounded list inside the ledger is how that file reached
            # 144 MB the last time. Re-charging a name evicted thousands
            # of features ago costs one trial and is the right trade.
            cap = int(os.environ.get("LEDGER_FEATURES_CAP", "4000"))
            if len(have) > cap:
                del have[:len(have) - cap]
            return len(new)

    # ---------- persistence ----------
    #
    # THIS FILE OUTGREW ITS FORMAT AND STALLED THE SEARCH.
    #
    # At 212,673 entries the ledger is ~144 MB written with indent=1.
    # save() ran after every market -- 23 times a cycle -- and each call
    # held the lock that every worker thread needs in order to record a
    # trial. Measured: 6.8s per save on four cores, so over two minutes
    # per cycle spent serialising with all workers blocked, and worse on
    # a two-core container where the 1.5 GB in-memory expansion is also
    # competing for RAM. The console showed a live green dot, no errors,
    # and a counter that had not moved in ten minutes.
    #
    # Three changes: write compact (6.8s -> 1.7s, 144 MB -> 104 MB),
    # throttle to at most one write per SAVE_EVERY_S unless forced, and
    # compact the oldest entries down to the fields that are actually
    # needed once a hypothesis is old and unremarkable.
    SAVE_EVERY_S = float(os.environ.get("LEDGER_SAVE_S", "60"))
    # Also flush after this many new trials, so a crash costs bounded
    # WORK rather than bounded time. A throttle alone means a process
    # that dies every 90s never persists anything.
    SAVE_EVERY_N = int(os.environ.get("LEDGER_SAVE_N", "1500"))
    # entries kept in full; older ones are reduced to a stub
    KEEP_FULL = int(os.environ.get("LEDGER_KEEP_FULL", "15000"))

    def save(self, force=False):
        with self._lock:
            return self._save(force=force)

    def _save(self, force=False):
        now_s = time.time()
        due_time = now_s - self._last_save >= self.SAVE_EVERY_S
        due_work = (self.d["trials"] - self._saved_trials
                    >= self.SAVE_EVERY_N)
        if not (force or due_time or due_work):
            return False
        self._compact()
        tmp = self.path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(self.d, fh, separators=(",", ":"))
        os.replace(tmp, self.path)
        self._last_save = time.time()
        self._saved_trials = self.d["trials"]
        self.save_secs = round(self._last_save - now_s, 2)
        return True

    def _compact(self):
        """Reduce old, unremarkable entries to a one-key stub.

        THIS IS A MEMORY FIX, NOT A TIDINESS FIX. Measured on a real
        ledger: the average full record is 3,462 bytes of Python
        objects, so 212,673 of them is 736 MB resident -- before
        json.load's own transient copy during startup. On a small
        container that is an OOM kill, and an OOM kill looks exactly
        like what was on screen: the round counter back to 1 every few
        minutes, the trial count sliding backwards to the last save, and
        a learning graph that climbs and then falls off a cliff.

        The ledger must remember every fingerprint forever -- that is
        what stops a hypothesis being retested and the rising bar being
        gamed. It does NOT need the full hypothesis and result of the
        150,000th losing cell. A stub is 265 bytes, so the same ledger
        costs 56 MB instead of 736 MB.

        Kept whole: anything killed, anything with |z| >= 2 (it could
        still reach the leaderboard or be re-checked), and everything
        recent.
        """
        t = self.d["tested"]
        excess = len(t) - self.KEEP_FULL
        if excess <= 0:
            return 0
        done = 0
        for fp, rec in t.items():          # insertion order: oldest first
            if done >= excess:
                break
            if not isinstance(rec, dict) or "hyp" not in rec:
                continue                   # already a stub
            if rec.get("killed"):
                continue
            r = rec.get("result") or {}
            if abs(float(r.get("z", 0) or 0)) >= 2.0:
                continue
            # Replacing a value for an existing key does not resize the
            # dict, so mutating during iteration is safe here.
            t[fp] = {"stub": 1}
            done += 1
        return done

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
