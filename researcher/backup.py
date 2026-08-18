"""Ledger backup to GitHub, so durability does not depend on a volume.

WHY THIS EXISTS. The searcher's safety property is that it counts its
own trials and raises its significance bar as sqrt(2 ln N). Lose the
ledger and the count resets, the bar falls from ~5 sigma back to 3.0,
and it starts reporting as discoveries the noise it had already ruled
out. That failure does not degrade the system, it inverts it.

A Railway volume is the right answer to that. But a volume is a piece of
platform configuration that can fail to get attached, get detached, or
be lost in a project migration -- and when it does, the searcher keeps
running and looks fine. So state also gets pushed to GitHub, where it is
versioned, visible, and outside the platform entirely.

  BOTH, not either. The volume is the fast path -- read and written
  every cycle. GitHub is the recovery path -- written once a cycle, read
  only when local state is missing or older.

WHAT IT PUSHES. ledger.json, memory.json, status.json. Small, and they
are the whole memory of the search. Not feed.jsonl, which grows without
bound and is a log rather than state.

WHAT IT WILL NOT DO. It will not merge two divergent ledgers. If two
searchers ever run against the same backup, the second one's push
overwrites the first, and the trial counts do not add up -- which is
exactly why the GitHub Actions workflow has no schedule and Railway is
the only continuous searcher. Two searchers, two ledgers, two bars that
are each too low. The `TRIALS ONLY GO UP` guard below refuses a push
that would lower the recorded trial count, so a fresh process that lost
its volume cannot silently overwrite a good backup with an empty one.

SETUP. One environment variable on the Railway service:

    GITHUB_TOKEN   a fine-grained PAT with Contents: read+write on
                   kyewellsthebest/FutureTradingBot

Optional: BACKUP_REPO (default kyewellsthebest/FutureTradingBot),
BACKUP_BRANCH (default research-state), BACKUP_DIR (default state).

The default branch is a SEPARATE one, not the working branch. Ledger
commits every few minutes would otherwise bury real work in the branch
history and retrigger a Railway deploy on every cycle -- an infinite
build loop.
"""
from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone

import requests

API = "https://api.github.com"
# brief.md rides along DELIBERATELY, and it is the only one here that
# is not state. Everything else exists so a wiped container can be
# restored; the brief exists so the searcher's own conclusions can be
# READ without anyone having to get a file off a phone. It is three
# kilobytes of text and it is the one artefact somebody actually needs
# between sessions -- what its coverage rules out, what it could not
# see, what it could not ask, and what is currently in the way.
#
# experiments.json rides along for the reason the feature library had to:
# an experiment accumulates its answer over many cycles, and this
# container has restarted 28 times. A store that dies on restart turns a
# five-run experiment into a permanent one-run experiment that never
# reaches done() and re-answers the same question forever.
FILES = ["ledger.json", "memory.json", "status.json",
         "brief.md", "brief.json", "experiments.json"]


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Backup:
    def __init__(self, rdir, token=None, repo=None, branch=None, sub=None):
        self.rdir = str(rdir)
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.repo = repo or os.environ.get(
            "BACKUP_REPO", "kyewellsthebest/FutureTradingBot")
        self.branch = branch or os.environ.get("BACKUP_BRANCH",
                                               "research-state")
        self.sub = sub or os.environ.get("BACKUP_DIR", "state")
        self.last = None
        self.enabled = bool(self.token)

    # ---------- plumbing ----------
    def _h(self):
        return {"Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"}

    def _path(self, name):
        return f"{self.sub}/{name}"

    def _get(self, name):
        """Returns (text, sha) or (None, None)."""
        r = requests.get(f"{API}/repos/{self.repo}/contents/"
                         f"{self._path(name)}",
                         headers=self._h(), params={"ref": self.branch},
                         timeout=30)
        if r.status_code != 200:
            return None, None
        j = r.json()
        try:
            return base64.b64decode(j["content"]).decode(), j["sha"]
        except Exception:                                     # noqa: BLE001
            return None, j.get("sha")

    def _put(self, name, text, sha, msg):
        body = {"message": msg, "branch": self.branch,
                "content": base64.b64encode(text.encode()).decode()}
        if sha:
            body["sha"] = sha
        r = requests.put(f"{API}/repos/{self.repo}/contents/"
                         f"{self._path(name)}",
                         headers=self._h(), json=body, timeout=30)
        return r.status_code in (200, 201), r.status_code, r.text[:200]

    def ensure_branch(self):
        """Create the state branch off the default branch if absent."""
        r = requests.get(f"{API}/repos/{self.repo}/branches/{self.branch}",
                         headers=self._h(), timeout=30)
        if r.status_code == 200:
            return True, "exists"
        rr = requests.get(f"{API}/repos/{self.repo}", headers=self._h(),
                          timeout=30)
        if rr.status_code != 200:
            return False, f"cannot read repo: {rr.status_code}"
        base = rr.json().get("default_branch", "main")
        rb = requests.get(f"{API}/repos/{self.repo}/git/ref/heads/{base}",
                          headers=self._h(), timeout=30)
        if rb.status_code != 200:
            return False, f"cannot read {base}: {rb.status_code}"
        sha = rb.json()["object"]["sha"]
        rc = requests.post(f"{API}/repos/{self.repo}/git/refs",
                           headers=self._h(), timeout=30,
                           json={"ref": f"refs/heads/{self.branch}",
                                 "sha": sha})
        return rc.status_code in (200, 201), f"created from {base}"

    # ---------- the two operations ----------
    def trials_local(self):
        try:
            return int(json.load(
                open(os.path.join(self.rdir, "ledger.json")))["trials"])
        except Exception:                                     # noqa: BLE001
            return 0

    def trials_remote(self):
        t, _ = self._get("ledger.json")
        if not t:
            return 0
        try:
            return int(json.loads(t)["trials"])
        except Exception:                                     # noqa: BLE001
            return 0

    def push(self):
        """Save state. Refuses to go backwards.

        TRIALS ONLY GO UP. A process that lost its volume starts at zero
        trials, and pushing that over a good backup would destroy the
        only surviving copy of the bar. So a push that would LOWER the
        recorded trial count is refused, and the refusal is reported --
        it means the local state is the damaged one and should be
        restored, not saved.
        """
        if not self.enabled:
            return {"ok": False, "why": "no GITHUB_TOKEN"}
        lt, rt = self.trials_local(), self.trials_remote()
        if lt < rt:
            self.last = {"t": _now(), "ok": False, "local": lt, "remote": rt,
                         "why": (f"REFUSED: local has {lt:,} trials, backup "
                                 f"has {rt:,}. Pushing would destroy the "
                                 f"better copy. Restore instead.")}
            return self.last
        ok, note = self.ensure_branch()
        if not ok:
            self.last = {"t": _now(), "ok": False, "why": note}
            return self.last
        done, failed = [], []
        for f in FILES:
            p = os.path.join(self.rdir, f)
            if not os.path.exists(p):
                continue
            try:
                text = open(p).read()
            except Exception as exc:                          # noqa: BLE001
                failed.append(f"{f}: {exc}")
                continue
            _, sha = self._get(f)
            good, code, body = self._put(
                f, text, sha, f"research state {_now()} ({lt:,} trials)")
            (done if good else failed).append(
                f if good else f"{f}: {code} {body}")
        self.last = {"t": _now(), "ok": not failed, "pushed": done,
                     "failed": failed, "trials": lt,
                     "url": f"https://github.com/{self.repo}/tree/"
                            f"{self.branch}/{self.sub}"}
        return self.last

    def restore_if_better(self):
        """Pull state back when the backup is ahead of local.

        This is what makes the searcher survive a lost volume. It runs
        once at boot: if GitHub holds more trials than the local ledger,
        the local one is a fresh empty container and the backup is the
        real history.
        """
        if not self.enabled:
            return {"ok": False, "why": "no GITHUB_TOKEN"}
        lt, rt = self.trials_local(), self.trials_remote()
        if rt <= lt:
            return {"ok": True, "restored": False, "local": lt,
                    "remote": rt, "why": "local state is current"}
        os.makedirs(self.rdir, exist_ok=True)
        got = []
        for f in FILES:
            text, _ = self._get(f)
            if text is None:
                continue
            with open(os.path.join(self.rdir, f), "w") as fh:
                fh.write(text)
            got.append(f)
        return {"ok": True, "restored": True, "files": got,
                "local_was": lt, "restored_to": rt,
                "why": (f"local ledger had {lt:,} trials, backup had "
                        f"{rt:,} -- storage was lost and has been "
                        f"recovered from GitHub")}
