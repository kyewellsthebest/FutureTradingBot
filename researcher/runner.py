"""The autonomous researcher: runs until stopped, reports what it learns.

    python -m researcher.runner            run until RESEARCH_STOP exists
    RESEARCH_ONCE=1 python -m researcher.runner    one pass, then exit

WHAT PROTECTS IT FROM ITSELF

  never repeats        every hypothesis is fingerprinted in the ledger
  raises its own bar   the threshold grows as sqrt(2 ln trials), so
                       spending more compute cannot by itself produce a
                       finding. Feature-selection trials are counted in
                       that total too -- scoring 500 candidate features
                       is search, and search that is not counted is
                       search that inflates every later result
  seals a vault        the newest 20% of history is untouchable; a
                       candidate gets ONE look at it, ever, and only
                       after surviving everything else
  self-tests           every cycle it plants a synthetic edge and
                       confirms the harness finds it. If the harness
                       goes blind, the run HALTS rather than reporting
                       silence as evidence of absence

WHAT IT LEARNS, in four layers, each with a mechanism behind it

  1  FEATURES (researcher/features.py). A vocabulary that grows by
     composition, kept on dispersion rather than profit, thresholded
     against what the same machinery produces on targets that cannot
     carry information. This is the part that can find something nobody
     specified up front.
  2  CURRICULUM (researcher/data_tiers.py). Cheap and wide first, then
     expensive and fine for the few things worth measuring precisely.
     Promotion REFINES a measurement, it does not confirm it -- tier-2
     NQ tick and tier-1 NQ 5-minute bars are the same tape.
  3  FAILURE MEMORY (researcher/memory.py). Not "it lost" but WHY. The
     valuable failure is cost-bound: directionally right, move smaller
     than the round trip. The response is longer holds, which follows
     from arithmetic, not from fitting.
  4  CALIBRATION (researcher/memory.py). Every vault touch compares a
     predicted strength with a realised one. The ratio is this system's
     own overfitting coefficient. Until there are touches it reports
     UNKNOWN rather than assuming it does not overfit.

WHAT IT WILL NOT DO. It will not find an edge because it ran longer.
Continuous search buys exhaustive COVERAGE and an honest account of what
has been ruled out. If it reports nothing after two weeks, the useful
output is the map of dead ground -- which is worth having, and is the
opposite of what an unbounded parameter search produces.
"""
import gc
import json
import os
from concurrent.futures import ThreadPoolExecutor
import sys
import time
import traceback
from datetime import datetime, timezone

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from researcher.ledger import Ledger
from researcher import pooled as PO          # noqa: E402
from researcher import parallel as PAR       # noqa: E402
from researcher import archive as AR         # noqa: E402
from researcher import calibration as CAL    # noqa: E402
from researcher import surrogate as SG
from researcher import diagnose as DG            # noqa: E402
from researcher import hypotheses as HY         # noqa: E402
from researcher.features import FeatureLibrary  # noqa: E402
from researcher.memory import Memory, classify  # noqa: E402
from researcher import data_tiers as DT         # noqa: E402
from researcher import insight as IN            # noqa: E402
from researcher import brief as BRIEF            # noqa: E402
from researcher import experiments as EXP        # noqa: E402
from researcher import context as CTX           # noqa: E402
from researcher import validate as VAL          # noqa: E402
from researcher import brackets as BR           # noqa: E402
from researcher import destinations as DS       # noqa: E402
from researcher import plausible as PL          # noqa: E402

ROOT = os.environ.get("M2_REPO", os.getcwd())
RDIR = os.environ.get("RESEARCH_DIR", os.path.join(ROOT, "data", "research"))
STOP = os.path.join(RDIR, "RESEARCH_STOP")
STATUS = os.path.join(RDIR, "status.json")
FEED = os.path.join(RDIR, "feed.jsonl")
# PER-MARKET ECONOMICS. A market whose contract spec we cannot state is
# not scored at all -- scoring 24 markets with one market's $/point is
# how every result becomes meaningless. 6A quotes near 0.67 and moves
# 0.0001 in five minutes; multiplied by MNQ's $2/point and charged
# MNQ's $0.60, every trade scored -$0.5992 no matter what happened.
# (micro contract $/point, round-trip cost)
# AND THE COST HAS TO INCLUDE THE SPREAD, not just commission. The
# first version charged ZB $2.50 -- commission only -- while one ZB tick
# is worth $31.25 and the typical spread is exactly one tick. It then
# reported a "confirmed" 1-bar mean reversion at z=10.6 worth $3.13 net.
# The actual gross edge was 0.203 of ONE TICK. Against a real taker
# round trip of ~$33.75 that trade loses $27 every time.
#
# A taker paying the spread on entry and exit gives up one full spread
# per round trip, plus commission both ways.
#     cost = spread_ticks * tick_value + 2 * commission_per_side
# (micro $/point, tick size, $/tick, all-in round-trip cost)
# EVERY MARKET WITH DATA, and the cost computed rather than guessed:
#
#     cost = tick_in_price x $/point + commission
#
# Every tick below was VERIFIED against the tapes -- the smallest price
# change that actually occurs in each file -- rather than taken from
# memory. Point values are the smallest tradeable contract, micro where
# one exists, because that is what a $4,000 account can hold.
#
# One full spread per round trip is the taker assumption: you cross on
# the way in and on the way out, which costs one spread total against
# mid. Where a micro's tick differs from the full contract's, the
# micro's (wider) tick is used -- conservative, and conservative on cost
# is the only safe direction to be wrong.
#
# (symbol: $/point, tick in price, commission round trip)
_SPEC_RAW = {
    "NQ":  (2.0,        0.25,       0.10),   # MNQ
    "ES":  (5.0,        0.25,       0.20),   # MES
    "YM":  (0.50,       1.0,        0.20),   # MYM
    "RTY": (5.0,        0.10,       0.20),   # M2K
    "GC":  (10.0,       0.10,       0.20),   # MGC
    "HG":  (2500.0,     0.0005,     0.20),   # MHG micro copper
    "CL":  (100.0,      0.01,       0.20),   # MCL
    "NG":  (2500.0,     0.001,      0.20),   # MNG micro henry hub
    "HO":  (42000.0,    0.0001,     0.30),   # no micro
    "RB":  (42000.0,    0.0001,     0.30),   # no micro
    "ZB":  (1000.0,     0.03125,    2.50),   # no micro, tick 1/32
    "ZN":  (1000.0,     0.015625,   2.50),   # tick 1/64
    "ZF":  (1000.0,     0.0078125,  2.50),   # tick 1/128
    "ZT":  (2000.0,     0.00390625, 2.50),   # tick 1/256
    "6E":  (12500.0,    0.0001,     0.20),   # M6E
    "6A":  (10000.0,    0.0001,     0.20),   # M6A
    "6B":  (6250.0,     0.0001,     0.20),   # M6B
    "6J":  (6250000.0,  0.000001,   0.20),   # M6J
    "ZC":  (10.0,       0.125,      0.20),   # XC micro corn, $/cent
    "ZW":  (10.0,       0.125,      0.20),   # XW micro wheat
    "ZS":  (10.0,       0.125,      0.20),   # XK micro soybean
    "MBT": (0.10,       5.0,        0.20),   # micro bitcoin, 0.1 BTC
    "ETH": (0.10,       0.50,       0.20),   # micro ether, 0.1 ETH
    # SI (silver) is PERMANENTLY EXCLUDED by standing instruction.
}
SPEC = {k: (pv, round(tick * pv + comm, 4))
        for k, (pv, tick, comm) in _SPEC_RAW.items()}
# RESEARCH_MARKETS narrows the universe to a comma-separated list. Only
# for integration runs -- a short list is the only way to exercise a
# code path like slate sharding, which needs more workers than markets,
# without forking one process per core on a dev box. Unset in
# production, where breadth IS the evidence.
_ONLY = [s.strip().upper() for s in
         os.environ.get("RESEARCH_MARKETS", "").split(",") if s.strip()]
if _ONLY:
    SPEC = {k: v for k, v in SPEC.items() if k in _ONLY}
VAULT_FRAC = 0.20
MIN_TRADES = 60
# dispersion floor, measured by features_selftest.py as the maximum the
# WHOLE three-generation growth reaches against targets that cannot
# carry information. Overridable, but never silently: the run prints it.
FEAT_FLOOR = float(os.environ.get("FEAT_FLOOR", "4.10"))
# Resolutions to rotate through on the deep tiers. Sixteen NQ tick
# sweeps (8 contracts x 2 resolutions... plus 15s and 300s) and six book
# sweeps before the deep space repeats -- and the feature library has
# grown a new generation on every one of them by then.
# LIVE COUNTERS. status.json is only written once a cycle, which on a
# six-minute cycle means the console's headline number sits frozen for
# minutes at a time and the whole thing looks dead. These are updated on
# every single hypothesis and read by the service directly, so the count
# on screen is the count right now.
LIVE = {"trials": 0, "tested": 0, "market": "", "tier": 0,
        "candidates": 0, "killed": 0, "started": None,
        # WHAT IT IS DOING RIGHT NOW, not just what it last scored.
        # market/tier are only set when a hypothesis is recorded, so
        # every setup phase -- loading tapes, growing features, saving a
        # 144 MB ledger -- rendered as "starting..." with a frozen
        # counter and a healthy green dot. Ten minutes of that is
        # indistinguishable from a dead process. stage is written at
        # each phase so a stall always names itself.
        "stage": "booting", "stage_t": 0.0}


def stage(what):
    LIVE["stage"] = what
    LIVE["stage_t"] = time.time()


# PROGRESS THAT SURVIVES A PROCESS BOUNDARY.
#
# The sweep now runs in forked children. Anything a child writes to LIVE
# is written to its own copy of the dict and thrown away when it exits,
# so the console read "0 this session" for the whole eight minutes a
# cycle took while 47 processes were flat out. These are multiprocessing
# counters created in main() before the pool forks, so a child's
# increment is visible to the parent's web thread immediately.
#
#   v  every hypothesis scored, anywhere
#   s  every shared-slate mechanism measured, anywhere
#
# Both are None until main() creates them, and _tick falls back to the
# plain dict so importing runner and calling sweep() directly -- which
# the self-tests do -- still counts.
PROGRESS = {"v": None, "s": None}


def _tick(key="v", n=1):
    c = PROGRESS.get(key)
    if c is None:
        if key == "v":
            LIVE["tested"] += int(n)
        return
    try:
        with c.get_lock():
            c.value += int(n)
    except Exception:                                         # noqa: BLE001
        pass


def progress(key="v"):
    c = PROGRESS.get(key)
    base = int(LIVE["tested"]) if key == "v" else 0
    try:
        return base + (int(c.value) if c is not None else 0)
    except Exception:                                         # noqa: BLE001
        return base


def start_progress():
    """Create the shared counters. Must run BEFORE any pool is forked."""
    if PROGRESS["v"] is not None:
        return
    try:
        import multiprocessing as _mp
        ctx = _mp.get_context("fork" if hasattr(os, "fork") else "spawn")
        PROGRESS["v"] = ctx.Value("l", 0)
        PROGRESS["s"] = ctx.Value("l", 0)
    except Exception:                                         # noqa: BLE001
        PROGRESS["v"] = PROGRESS["s"] = None


_SHARED = __import__("threading").Lock()


def _mem_limit_mb():
    """The container's memory limit, from cgroup. None if unbounded."""
    for p in ("/sys/fs/cgroup/memory.max",
              "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            v = open(p).read().strip()
            if v and v != "max":
                n = int(v)
                if 0 < n < (1 << 62):
                    return n / 1e6
        except Exception:                                     # noqa: BLE001
            continue
    return None


# HOW MANY MARKETS AT ONCE, AND WHY IT IS NOT THE CPU COUNT.
#
# Feature growth is the peaky phase of a sweep: measured, one market
# peaks around 430 MB of transient allocation while retaining only
# ~15 MB. Sizing the pool by cores meant several markets hit that peak
# simultaneously -- on an 8-core container, seven concurrent peaks --
# and the sum is what the kernel sees. The console caught it in the act:
# "YM tier 1: building features" at 5,644 MB, restarting seven times an
# hour.
#
# So the pool is sized by MEMORY, with cores as a ceiling rather than
# the target. RESEARCH_WORKERS still overrides, for anyone who knows
# what their box has.
MEM_LIMIT_MB = _mem_limit_mb()
# Measured after bounding the feature memo: one market's sweep peaks
# about 70 MB above its retained footprint, plus ~80 MB of retained
# per-market working set. 160 is that with headroom.
PEAK_PER_SWEEP_MB = float(os.environ.get("RESEARCH_PEAK_MB", "160"))
BASE_MB = float(os.environ.get("RESEARCH_BASE_MB", "700"))

# THE COST THAT WAS MISSING, AND IT IS THE ONE THAT GREW.
#
# The formula above treats a worker as a fixed 160 MB. It is not: a
# forked child also DIRTIES the parent's ledger. Copy-on-write does not
# save you in CPython, because touching any object writes its refcount
# and therefore its page. Measured directly -- parent holding a 336,449
# entry ledger, eight forked children each reading the snapshot the way
# a sweep does:
#
#     baseline 0.89 GB -> 1.68 GB with 8 workers = 102 MB EACH
#     gc.freeze() made no difference
#
# That is ~0.3 KB per ledger entry per worker, and the ledger grows all
# day. At 47 workers and 336k entries it is 4.8 GB of pure fork
# overhead that the sizing formula could not see -- which is how a box
# with a 24 GB limit reached 20 GB and was killed. The console's own
# memory graph showed the sawtooth for hours.
#
# So the per-worker figure is now computed from the ledger's actual
# size rather than assumed constant.
# MEASURED, after three wrong theories about WHY it happens.
#
#   604 MB per worker   as found
#   580 MB              after the compact fingerprint index
#   540 MB              after passing the context by fork, not by pickle
#
# 540 MB at 336,449 entries is 1.64 KB per entry per worker. The first
# value here was 0.30, which is what let the sizing formula pick 47
# workers for a box that could hold roughly twelve.
#
# The remaining 540 MB is NOT fully explained. Two theories were
# measured and rejected (the cyclic collector, refcount dirtying of the
# fingerprint set) and a third -- initargs pickling the tapes -- was
# real but proportionally smaller than hoped. Sizing does not require
# the explanation: it requires the number, and the number is measured
# end to end rather than reasoned about. If the cause is found later
# this constant falls and the pool widens by itself.
LEDGER_DIRTY_KB_PER_ENTRY = float(
    os.environ.get("RESEARCH_DIRTY_KB", "1.64"))


def rss_mb():
    """This process's resident memory, right now."""
    try:
        with open("/proc/self/statm") as fh:
            return (int(fh.read().split()[1])
                    * os.sysconf("SC_PAGE_SIZE") / 1e6)
    except Exception:                                         # noqa: BLE001
        return None


def per_worker_mb(entries=0):
    return PEAK_PER_SWEEP_MB + (entries * LEDGER_DIRTY_KB_PER_ENTRY / 1024.0)


def _worker_count(entries=0, parent_mb=None):
    """How many children this box can actually hold.

    MEASURED PARENT, NOT AN ASSUMED CONSTANT. BASE_MB was a guess of
    700, and the parent is nothing like that once it holds 23 tier-1
    tapes, eight deep contracts and a ledger -- the real figure is
    several gigabytes and it grows all day. Sizing a 47-worker pool
    against a stale guess is how the box reached 20 GB of a 24 GB limit
    and was killed. Every child starts as a copy of the parent, so the
    parent's size is the single largest term and it is knowable for
    free.
    """
    cores = max(1, (os.cpu_count() or 2) - 1)
    env = os.environ.get("RESEARCH_WORKERS")
    if env:
        return max(1, int(env))
    if not MEM_LIMIT_MB:
        return min(cores, 4)
    base = parent_mb if parent_mb else (rss_mb() or BASE_MB)
    # Leave a fifth of the limit unspent. A sweep's peak is not its
    # average, the kernel kills on the peak, and a searcher that is
    # dead is slower than one running two workers short.
    room = (MEM_LIMIT_MB * 0.80 - base) / per_worker_mb(entries)
    return int(max(1, min(cores, room)))


WORKERS = _worker_count()


def resize_workers(led):
    """Re-size the pool for the ledger as it is NOW, not as it booted.

    The per-worker cost grows with the ledger, so a pool sized at boot
    is oversized by lunchtime. Called each cycle; only ever narrows
    toward what the memory actually supports.
    """
    global WORKERS
    if os.environ.get("RESEARCH_WORKERS"):
        return WORKERS
    try:
        n = len(led.d.get("tested") or {})
    except Exception:                                         # noqa: BLE001
        return WORKERS
    parent = rss_mb()
    w = _worker_count(n, parent_mb=parent)
    if w != WORKERS:
        say("workers_resized", was=WORKERS, now=w, ledger_entries=n,
            parent_rss_mb=None if parent is None else round(parent),
            per_worker_mb=round(per_worker_mb(n)),
            limit_mb=None if not MEM_LIMIT_MB else round(MEM_LIMIT_MB),
            why="a forked worker dirties ~0.3 KB per ledger entry, so "
                "the pool that fitted at boot does not fit once the "
                "ledger has grown")
        WORKERS = w
    return WORKERS

# A HARD BOUND ON CONCURRENT PEAKS, independent of the pool size. Even
# if the pool is widened, only this many markets may be in the
# allocation-heavy phase at once -- so raising RESEARCH_WORKERS to use
# spare cores on the cheap phases cannot reintroduce the OOM.
_GROW_GATE = __import__("threading").Semaphore(WORKERS)

# THE SHARED SLATE. Market-agnostic mechanisms are drawn ONCE per cycle
# and every market is asked the same question, so the answers can be
# pooled. Drawing them per market -- which is what happened before --
# meant MNQ and ES were each tested on their own private random sample
# and no two markets ever answered the same question, which is why the
# breadth of this dataset was never actually used as evidence.
SLATE = {"hyps": [], "book": None, "surrogate": None}

# THE MAP. One elite per behavioural niche, kept for the life of the
# project. Separate from the ledger because it answers a different
# question: the ledger says what has been tried, the map says what the
# best thing of each KIND is. See researcher/archive.py.
ARCH = {"a": None}
# RESOLUTION ROTATION, WEIGHTED BY WHERE THE POWER ACTUALLY IS.
#
# Measured on the NQ tapes on disk, per-trade dispersion in round trips
# and the trades an edge of +0.15 RT would need to clear a 5.3 bar:
#
#   tape        hold     sd (RT)    trades needed    at 10% firing,
#                                                     20 markets
#   5-min bars    5m        74.4        6,902,589      9,100 weeks
#   5-min bars   30m       181.9       41,296,793     55,000 weeks
#   60s bars      60s       36.9        1,697,486        450 weeks
#   15s bars      15s       17.7          390,641         26 weeks
#   15s bars      90s       45.1        2,537,460        168 weeks
#
# Dispersion grows as the square root of hold, so the trades needed
# grow LINEARLY with it -- and the number of trades available shrinks
# linearly too, which squares the penalty. Every factor of four in
# resolution is a factor of sixteen in how long it takes to see the same
# edge. 15-second bars are not "one of three resolutions"; they are the
# only tape on disk where anything of a plausible size is reachable at
# all, and 15s appears twice here for that reason. 300s stays in the
# rotation because the horizon fits say a few families do not break even
# until minutes in, and a tape that cannot see them at all is worse than
# a tape that sees them slowly.
T2_RES = [15, 60, 15, 300]
T3_RES = [1, 5, 1, 30]


def memory_report():
    """Where the resident memory actually is.

    Written because two rounds of this were spent guessing. The
    container was being killed at 2.1 GB and the honest answer to "what
    is using it" was "I do not know" -- so now the process says, and the
    next person does not have to reason from the outside.
    """
    import sys as _sys
    out = {}
    try:
        with open("/proc/self/statm") as fh:
            out["rss_mb"] = round(int(fh.read().split()[1])
                                  * os.sysconf("SC_PAGE_SIZE") / 1e6, 1)
    except Exception:                                         # noqa: BLE001
        pass
    try:
        led = _HIST_CTX.get("led")
        if led is not None:
            t = led.d["tested"]
            full = sum(1 for r in t.values()
                       if isinstance(r, dict) and not r.get("stub"))
            out["ledger_entries"] = len(t)
            out["ledger_full"] = full
            out["ledger_stubs"] = len(t) - full
            # measured, not assumed: 3,462 B for a full record, 265 for
            # a stub, from a real ledger
            out["ledger_mb"] = round((full * 3462 + (len(t) - full) * 265)
                                     / 1e6, 1)
    except Exception:                                         # noqa: BLE001
        pass
    # THE CEILING ITSELF, so the console can say "using X of Y" instead
    # of leaving the reader to find it in a hosting dashboard.
    out["limit_mb"] = round(MEM_LIMIT_MB, 0) if MEM_LIMIT_MB else None
    out["workers"] = WORKERS
    out["cores"] = os.cpu_count()
    try:
        out["levels_cache"] = len(_LEVELS)
        out["levels_mb"] = round(sum(
            sum(_sys.getsizeof(v) for v in lv.values())
            for lv, _u in _LEVELS.values()) / 1e6, 1)
    except Exception:                                         # noqa: BLE001
        pass
    try:
        out["libs"] = len(_HIST_CTX.get("libs") or {})
    except Exception:                                         # noqa: BLE001
        pass
    return out


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- history
# THE LEARNING GRAPHS NEED POINTS MORE OFTEN THAN ONCE A CYCLE.
#
# History used to be appended at the end of a sweep. A full sweep of 23
# markets across three tiers takes hours, so for most of a day the series
# held exactly ONE point -- and a one-point series cannot be drawn. Every
# chart on the Learning tab rendered as an empty shimmering box, which
# reads as "still loading" forever rather than "one reading so far".
#
# So it is sampled on a timer as well. The cycle-end call still happens
# and is the only one that carries a round time; the sampler fills in
# between so the graphs move while you watch them.
_HIST_LOCK = __import__("threading").Lock()
_HIST_CTX = {}


def history_point(secs=None):
    """Append one row to the learning series. Safe to call from anywhere."""
    led = _HIST_CTX.get("led")
    if led is None:
        return False
    mem = _HIST_CTX.get("mem") or type("_", (), {"d": {}})()
    libs = _HIST_CTX.get("libs") or {}
    try:
        with _HIST_LOCK:
            hp = os.path.join(RDIR, "history.json")
            hist = []
            if os.path.exists(hp):
                try:
                    hist = json.load(open(hp)) or []
                except Exception:                             # noqa: BLE001
                    hist = []
            # Under the ledger's own lock: this samples from a dict that
            # every worker thread is inserting into, and iterating it
            # unlocked raises "dictionary changed size during iteration"
            # -- silently, into the try/except, so the graphs would just
            # stop gaining points with no error anywhere.
            with led._lock:
                trials = led.d["trials"]
                distinct = len(led.d["tested"])
                nkilled = sum(1 for r in led.d["tested"].values()
                              if isinstance(r, dict) and r.get("killed"))
            row = {
                "t": now(), "cycle": _HIST_CTX.get("cycle", 0),
                "trials": trials,
                "bar": round(led.bar(), 3),
                "distinct": distinct,
                "killed": nkilled,
                "survivors": len(led.d.get("survivors", [])),
                "adaptations": len(mem.d.get("adaptations", [])),
                "families": len(mem.d.get("families", {})),
                "closed": sum(1 for a in mem.d.get("adaptations", [])
                              if a.get("kind") == "closed"),
                "deduced": sum(1 for a in mem.d.get("adaptations", [])
                               if a.get("kind") == "horizon"),
                "features": sum(len(l.scores) for l in libs.values()),
                "vault": len(led.d.get("vault_touches", {})),
            }
            # Round time only exists at the end of a round. Carrying the
            # previous value forward keeps that line continuous instead
            # of collapsing to zero between sweeps.
            row["secs"] = (int(secs) if secs is not None
                           else (hist[-1].get("secs", 0) if hist else 0))
            row["sampled"] = secs is None
            # Nothing moved and this is only a sample: replace the last
            # sample rather than growing the file with a flat line.
            if (hist and row["sampled"] and hist[-1].get("sampled")
                    and hist[-1].get("trials") == row["trials"]):
                hist[-1] = row
            else:
                hist.append(row)
            json.dump(hist[-3000:], open(hp, "w"))
        return True
    except Exception as exc:                                  # noqa: BLE001
        say("history_failed", err=str(exc)[:120])
        return False


def start_history_sampler(every=60):
    import threading

    def loop():
        while True:
            time.sleep(every)
            try:
                history_point()
            except Exception:                                 # noqa: BLE001
                pass
    t = threading.Thread(target=loop, daemon=True, name="history")
    t.start()
    return t


def say(msg, **kw):
    line = {"t": now(), "msg": msg}
    line.update(kw)
    print(json.dumps(line), flush=True)
    os.makedirs(RDIR, exist_ok=True)
    with open(FEED, "a") as fh:
        fh.write(json.dumps(line) + "\n")


def split(d):
    """Search set and sealed vault. The vault is the NEWEST slice --
    the part most like the future we would trade in."""
    k = int(len(d) * (1 - VAULT_FRAC))
    return d.iloc[:k], d.iloc[k:]


def bars_per(d):
    """Seconds per bar, inferred. The evaluator converts a hold in
    seconds into a bar count, and hardcoding 300 was fine when the only
    tier was 5-minute bars. At tier 2 it would silently hold 5x too
    long and report it as the requested horizon."""
    if len(d) < 3:
        return 300.0
    dt = np.diff(d.index.values[:2000]).astype("timedelta64[s]").astype(float)
    dt = dt[dt > 0]
    return float(np.median(dt)) if len(dt) else 300.0


# =====================================================================
# THE ONE INVARIANT THAT MAKES A WHOLE CLASS OF BUG IMPOSSIBLE
#
# Five separate false positives in this project shared one shape: a
# hypothesis selected a bar using information known only AT that bar's
# close, then entered at that same close. The entry price is then
# contaminated by the selection, and the "edge" is the contamination.
#
#   the fade           entered at a level the market had already left
#   the maker fill     marked against a mid that had moved
#   ZB 1-bar reversion  feature and target shared one price print
#   close_high/low     the close IS the bar's extreme, an order
#                      statistic, so the next close reverts by
#                      construction: -10.2 pts against -0.03 baseline
#   the breakeven stop  "exited at entry" while 50 points underwater
#
# Each was caught AFTER the fact by the delay control -- and twice I
# added a new evaluation path and forgot to wire that control into it,
# so it silently passed everything. A control you have to remember is
# not a control.
#
# So the rule is now structural. EVERY path from a signal to a trade
# goes through entries() below, and entries() always moves the entry to
# the NEXT bar. There is no argument to disable it. A signal computed
# from bar t is actionable at bar t+1 and not before, which is simply
# true: you cannot transact on a bar's close until that bar has closed,
# and by then the price is gone.
#
# The delay control still runs on top as a robustness check. It now
# tests t+2 against t+1, which is a genuine extra question rather than
# the only thing standing between the searcher and nonsense.
ENTRY_LAG = 1


def entries(mask, n, extra=0):
    """Signal bars -> tradeable entry bars. The only such conversion.

    Adds ENTRY_LAG unconditionally. If a future evaluation path forgets
    to call this, it will not silently enter at the signal bar -- it
    will fail the invariant test in researcher/selftest_all.py, which
    asserts that a planted close-at-high artifact scores flat.
    """
    m = mask.values if hasattr(mask, "values") else np.asarray(mask)
    sel = np.flatnonzero(m)
    sel = sel + ENTRY_LAG + int(extra)
    return sel[(sel >= 0) & (sel < n)]


_LEVELS = {}


def _eval_dest(d, h, tv, cost, delay=0, memo=None):
    """Score a destination hypothesis as the race it actually is.

    Returns the same shape of dict as everything else so the ledger,
    the bar, the gauntlet and the leaderboard need no special case --
    but the underlying measurement is a first passage, not a
    fixed-horizon return, and the stop is LEARNED here rather than
    supplied.
    """
    if "high" not in d.columns:
        return None
    # THE CACHE THAT ATE THE CONTAINER.
    #
    # build_levels for ONE market is 21 MB of arrays (14 levels over
    # 185,000 bars). This cache was allowed to reach 30 of them before
    # clearing, so its ceiling was 621 MB -- held for the life of the
    # process, on top of the ledger and the tapes. Measured, and it is
    # the largest single consumer in the searcher.
    #
    # Only the markets currently being swept need to be here, and sweeps
    # run WORKERS-at-a-time. Bounded to that plus slack, evicting oldest
    # first rather than clearing the lot (a full clear throws away the
    # entry the caller is about to ask for again).
    k = (id(d), len(d))
    if k not in _LEVELS:
        # CAP OF THREE, NOT WORKERS+1.
        #
        # "WORKERS-at-a-time plus slack" was correct when sweeps were
        # THREADS sharing one process: all of them needed their levels
        # resident at once. They are processes now, and a process sweeps
        # ONE market at a time -- so this cache is per-worker and each
        # worker needs one entry, not forty-eight. At 21 MB per entry
        # and 47 workers the old cap allowed a gigabyte per child of
        # levels for markets that child will never look at again.
        cap = int(os.environ.get("RESEARCH_LEVELS_CAP", "3"))
        while len(_LEVELS) >= cap:
            _LEVELS.pop(next(iter(_LEVELS)))
        _LEVELS[k] = (DS.build_levels(d),
                      BR.atr(d["high"].values, d["low"].values,
                             d["close"].values, 60))
    levels, unit = _LEVELS[k]
    if h["level"] not in levels:
        return None
    if h["trigger"] == "none":
        trig = np.ones(len(d), dtype=bool)
    else:
        cs = _conds(d)
        if h["trigger"] in cs:
            trig = cs[h["trigger"]]
        else:
            trig = HY.shape_mask(d, h["trigger"], 3, 2.0, memo=memo)
            if trig is None:
                return None
    # same invariant: the trigger is knowable at bar t, tradeable at t+1
    lag = ENTRY_LAG + delay
    trig = np.roll(np.asarray(trig), lag)
    trig[:lag] = False
    r = DS.study(d, unit, h["level"], levels, h["side"], trig,
                 int(h["max_bars"]))
    if not r or not r.get("invalidation"):
        return None
    med_unit = float(np.nanmedian(unit))
    if not np.isfinite(med_unit) or med_unit <= 0:
        return None
    cost_u = cost / (tv * med_unit)
    ev = DS.expected_value(r, cost_u)
    if not ev:
        return None
    p, rw, rk = r["p_trigger"], ev["reward"], ev["risk"]
    n = r["n_trigger"]
    # per-trade P&L in dollars, and its dispersion, so this shares the
    # significance machinery with every other family
    per = ev["ev_units"] * med_unit * tv
    var = p * (1 - p) * ((rw + rk) * med_unit * tv) ** 2
    se = (var ** 0.5) / max(n ** 0.5, 1.0)
    z = per / (se + 1e-12)
    gross = per + cost
    return {"z": round(float(z), 3), "gz": round(float(gross / (se + 1e-12)), 3),
            "edge": round(float(gross), 4), "net": round(float(per), 4),
            "sd": round(float(var ** 0.5), 5),
            "cu": round(float(per) / cost, 5) if cost else None,
            "n": int(n), "eff_n": int(n), "overlap": 1.0, "delay": delay,
            "win_rate": round(p, 4),
            "rr": round(rw / rk, 3) if rk else 0.0,
            "per_week": round(n / max(
                (d.index[-1] - d.index[0]).days / 7.0, 1.0), 2),
            "avg_win": round(rw * med_unit * tv, 3),
            "avg_loss": round(rk * med_unit * tv, 3),
            "lift": r["lift"], "p_base": r["p_base"],
            "stop_units": rk,
            "stop_why": r["invalidation"]["why"]}


_CONDS = {}


def _conds(d):
    """The four conditioning masks for a tape, computed once.

    Keyed by object identity plus length -- the runner holds each tape
    for the life of the process, so identity is stable, and the length
    guards against a same-address reuse after a tape is freed.
    """
    k = (id(d), len(d))
    if k in _CONDS:
        return _CONDS[k]
    extern = _EXTERN.get(k, {})
    idx = d.index
    c = d["close"]
    rv = c.diff().abs().rolling(120, min_periods=30).mean()
    # and the same problem in weaker form: thresholding on the
    # FULL-SAMPLE median of realised vol uses years of future data to
    # decide what counted as "high vol" today. A trailing median is
    # known at the time and costs nothing.
    rvmed = rv.rolling(4000, min_periods=500).median()
    day = idx.normalize()
    g = c.groupby(day)
    # LOOK-AHEAD, FIXED. This was `last - first`: the day's FULL return,
    # which at 10am you do not know. Conditioning a 10am entry on how
    # the day ends is not a filter, it is the answer. It biases every
    # up_day/dn_day cell toward a false positive, and it was in the
    # committed version. The honest quantity is the return SO FAR --
    # from the day's open to the current bar, known when the trade is
    # placed.
    dayret = c - g.transform("first")
    ok = rvmed.notna().values
    out = {"hi_vol": (rv > rvmed).values & ok,
           "lo_vol": (rv <= rvmed).values & ok,
           "up_day": (dayret > 0).values,
           "dn_day": (dayret <= 0).values}
    # EXTERNAL STATE, merged in. Every condition above is derived from
    # the same price series being predicted, which is a filter with no
    # outside information in it. These are outside information, and
    # specifically information about CONSTRAINT -- who is hedged which
    # way, who is crowded, when cash is scarce.
    out.update(extern)
    if len(_CONDS) > 40:
        _CONDS.clear()
    _CONDS[k] = out
    return out


_EXTERN = {}


def attach_context(sym, d):
    """Load external regime state for a tape and register its masks.

    Returns the condition names now available. Failure is non-fatal and
    LOUD: a missing context source means fewer conditions, and silently
    having fewer conditions looks identical to having tested them.
    """
    try:
        ctx = CTX.build(str(sym).split("@")[0], d.index)
        m = CTX.masks(ctx) if ctx is not None else {}
    except Exception as exc:                                  # noqa: BLE001
        say("context_failed", market=sym, err=str(exc)[:160])
        return []
    if not m:
        return []
    _EXTERN[(id(d), len(d))] = m
    _CONDS.pop((id(d), len(d)), None)
    return sorted(m)


# ------------------------------------------------------------ evaluation
def evaluate(d, h, tv=None, cost=None, feats=None, bar_s=None, delay=0,
             memo=None):
    """Score one hypothesis. Returns dict with z, edge, net, n.

    `delay` shifts the ENTRY forward by that many bars while leaving the
    signal where it was. It is the control for the single most common
    fake edge in bar data, and it caught one on the first real run.

    THE BOUNCE ARTIFACT. A feature built from close[t] - close[t-1] is
    scored against close[t+1] - close[t]. Both contain close[t], so any
    noise in that one print -- a trade at the bid rather than the ask, a
    stale quote, a thin bar -- pushes the feature up and the forward
    return down at the same time. The result is a beautiful mean
    reversion that exists only in the printed series.

    On the first run this produced ZB at z=10.6, "confirmed" in the
    vault at z=7.3, apparently worth $3.13 a trade. The gross edge was
    0.203 of ONE TICK on an instrument whose tick is worth $31.25 and
    whose typical 5-minute move is exactly one tick. Lag-1
    autocorrelation of ZB 5-minute changes is -0.070: the bounce,
    exactly.

    Entering one bar later cannot touch a real prediction about the next
    hour, but it completely destroys an artifact that lives inside a
    single shared print.
    """
    tv = 2.0 if tv is None else tv
    cost = 0.60 if cost is None else cost
    bar_s = bars_per(d) if bar_s is None else bar_s
    idx = d.index

    if h.get("kind") == "dest":
        return _eval_dest(d, h, tv, cost, delay, memo=memo)
    if h.get("kind") == "shape":
        m = HY.shape_mask(d, h["shape"], h.get("n", 3), h.get("k", 2.0),
                          memo=memo)
        if m is None:
            return None
        mask = np.asarray(m)
        if h.get("cond", "none") != "none":
            mask = mask & _conds(d)[h["cond"]]
        side = np.full(len(d), 1.0 if h["ls"] == "long" else -1.0)
    elif h.get("kind") in ("feature", "flow"):
        if h["kind"] == "flow":
            x = HY.flow_series(d, h["mech"])
        else:
            x = feats.get(h["feat"]) if feats else None
        if x is None:
            return None
        ok = np.isfinite(x)
        if ok.sum() < MIN_TRADES * 5:
            return None
        cut = np.nanpercentile(x[ok], 80 if h["side"] == "hi" else 20)
        mask = (x >= cut) if h["side"] == "hi" else (x <= cut)
        mask = mask & ok
        side = np.where(np.ones(len(d)) > 0,
                        1.0 if h["ls"] == "long" else -1.0, 0.0)
    else:
        if h["dim"] == "minute_of_day":
            hh, mm = (int(v) for v in str(h["bucket"]).split(":"))
            mask = (idx.hour == hh) & (idx.minute == mm)
        elif h["dim"] == "day_of_month":
            mask = idx.day == int(h["bucket"])
        else:
            mask = idx.dayofweek == int(h["bucket"])
        if h["cond"] != "none":
            # PRECOMPUTED. These four masks are identical for every
            # hypothesis on this tape, and the day-return one is a
            # groupby-transform with a Python lambda over ~150k rows.
            # Recomputing it per hypothesis made a 500-hypothesis sweep
            # cost minutes instead of seconds -- the same work, done
            # 400 times.
            conds = _conds(d)
            # A MISSING CONDITION IS A SKIP, NOT A CRASH. Context
            # sources are external (gamma, COT, FRED, DTS) and can be
            # unavailable; a hypothesis conditioned on one that is not
            # registered for this tape cannot be measured, and killing
            # the cycle over it throws away every other market's work.
            cm = conds.get(h["cond"])
            if cm is None:
                return None
            mask = np.asarray(mask) & cm
        sign = np.sign(d["close"].diff().fillna(0.0)).values
        side = sign if h["dir"] == "with" else -sign

    bars = max(int(round(h["hold_s"] / bar_s)), 1)

    # ---- BRACKETED EXIT. A stop and a target, in units of realised
    # volatility, resolved bar by bar with the stop winning any bar that
    # touches both. This is the difference between a prediction and a
    # strategy, and it is what makes win rate and reward-to-risk mean
    # anything -- a fixed time exit produces ~50% wins and RR~1 by
    # construction.
    ex = h.get("exit")
    if ex and "high" in d.columns and "low" in d.columns:
        # ATR is a property of the tape, not of the hypothesis, so it
        # is computed once per market rather than once per cell.
        if memo is not None and "_atr" in memo:
            unit = memo["_atr"]
        else:
            unit = BR.atr(d["high"].values, d["low"].values,
                      d["close"].values, 60)
            if memo is not None:
                memo["_atr"] = unit
        m0 = mask.values if hasattr(mask, "values") else np.asarray(mask)
        sel = entries(m0, len(d), delay)
        sel = sel[np.isfinite(unit[sel]) & (unit[sel] > 0)]
        # DELAY APPLIES HERE TOO. The first version of this branch
        # ignored `delay` entirely, so the one-bar delay control -- the
        # gate that exists specifically to kill signals that live inside
        # a single price print -- silently did nothing for every
        # bracketed hypothesis, which is now the largest family. It
        # passed them all with kept_frac 1.00 because it was handing
        # back the identical number.
        #
        # It let through "after close_high, go short": close_high
        # selects bars where the close IS the bar's maximum, an extreme
        # order statistic, so the next close reverts by construction --
        # -10.2 points on NQ 60s against an unconditional -0.03. Not
        # tradable: you cannot know close[t] was the high until the bar
        # has ended, and by then that price is gone.
        sel = sel[sel + 1 < len(d)]
        if len(sel) < MIN_TRADES:
            return None
        maxb = max(int(round(h["hold_s"] / bar_s)), 1)
        res = BR.pnl(sel, side[sel] if hasattr(side, "__len__") else side,
                     d["high"].values, d["low"].values, d["close"].values,
                     float(ex[0]), float(ex[1]), unit, maxb, tv, cost,
                     open_=(d["open"].values if "open" in d.columns
                            else None))
        net = res["net"]
        if len(net) < MIN_TRADES:
            return None
        gap = float(np.median(np.diff(sel))) if len(sel) > 1 else float(maxb)
        ov = float(np.clip(np.median(res["held"]) / max(gap, 1.0),
                           1.0, float(maxb)))
        eff = max(len(net) / ov, 2.0)
        z = float(net.mean() / (net.std(ddof=1) / np.sqrt(eff) + 1e-12))
        gross = net + cost
        gz = float(gross.mean() / (gross.std(ddof=1) / np.sqrt(eff) + 1e-12))
        wins, losses = net[net > 0], net[net < 0]
        aw = float(wins.mean()) if len(wins) else 0.0
        al = float(-losses.mean()) if len(losses) else 0.0
        span = max((idx[-1] - idx[0]).total_seconds() / 86400.0, 1.0)
        return {"z": round(z, 3), "gz": round(gz, 3),
                "edge": round(float(gross.mean()), 4),
                # cross-market pooling needs the dispersion, not just
                # the mean: the pooled standard error is built from it
                "sd": round(float(gross.std(ddof=1)), 5),
                # NET edge in units of THIS market's round trip, so
                # results are comparable across instruments whose ticks
                # differ by 60x. NET, not gross: with gross the
                # break-even point is 1.0, and a cell earning a tenth of
                # its own trading cost rendered as "+0.098" in green.
                # Defined this way 0 IS break-even and the sign of the
                # number is the sign of the money.
                "cu": round(float(net.mean()) / cost, 5) if cost else None,
                # THE SMALLEST EDGE THIS CELL COULD HAVE SEEN. Without
                # it, "did not clear the bar" is ambiguous between "there
                # is nothing here" and "this cell never had the power to
                # tell". Measured on real NQ, most cells are the second:
                # at a 30-minute hold the per-trade noise is ~113 round
                # trips, so 166 observations can only detect an edge of
                # about nine round trips -- nine times the entire cost of
                # trading. Silence from an underpowered cell is not
                # evidence of absence, and now it says so.
                "mde": round(float(gross.std(ddof=1)) / cost
                             * 3.5 / max(eff, 1) ** 0.5, 4) if cost else None,
                "net": round(float(net.mean()), 4), "n": int(len(net)),
                "eff_n": int(eff), "overlap": round(ov, 2), "delay": delay,
                "win_rate": round(float(len(wins) / len(net)), 4),
                "rr": round(aw / al, 3) if al > 0 else 0.0,
                "per_week": round(len(net) / (span / 7.0), 2),
                "avg_win": round(aw, 3), "avg_loss": round(al, 3),
                "stopped": round(res["stopped"], 3),
                "targeted": round(res["targeted"], 3),
                "timed": round(res["timed"], 3),
                "tie_share": BR.resolution_cost(res["ties"], len(net))}

    # entry at t+delay, exit `bars` later. delay=0 is entry at the
    # signal bar's own close, which is where the bounce artifact lives.
    c = d["close"]
    lag = ENTRY_LAG + delay
    fwd = c.shift(-(bars + lag)) - c.shift(-lag)
    same = idx.normalize().values == \
        pd.Series(idx).shift(-(bars + lag)).dt.normalize().values
    fwd = fwd.where(same)
    m = mask.values if hasattr(mask, "values") else np.asarray(mask)
    raw = side * fwd.values
    sel = np.flatnonzero(m & np.isfinite(raw))
    if len(sel) < MIN_TRADES:
        return None
    pnl = raw[sel]

    # OVERLAP, measured rather than assumed. Holding `bars` bars while
    # trading every bar means consecutive trades share most of their
    # path, and the naive standard error is then too small.
    #
    # But the correction depends on how far apart the trades ACTUALLY
    # are, not on the hold alone. A minute-of-day cell fires once per
    # session -- 78 bars apart on a 5-minute tape -- so a 36-bar hold
    # produces no overlap at all. Dividing those by 36 anyway was
    # over-correcting by a factor of six, which does not manufacture a
    # finding but does hide real ones, and a test that only catches
    # errors in the flattering direction is half a test.
    gap = float(np.median(np.diff(sel))) if len(sel) > 1 else float(bars)
    ov = float(np.clip(bars / max(gap, 1.0), 1.0, float(bars)))
    net = pnl * tv - cost
    eff = max(len(net) / ov, 2.0)
    se = net.std(ddof=1) / np.sqrt(eff)
    z = float(net.mean() / (se + 1e-12))

    # GROSS z, for the empirical null. The net z is dominated by the
    # cost: almost every cell loses close to a full round trip, so |z|
    # of net runs to 20+ and an "empirical null" built from it would
    # measure how reliably trading costs money, not how much noise the
    # search manufactures. Under a true null the GROSS mean is zero, so
    # gross z is the quantity whose distribution is the null.
    gross = pnl * tv
    gse = gross.std(ddof=1) / np.sqrt(eff)
    gz = float(gross.mean() / (gse + 1e-12))

    # Trade economics, for the leaderboard. Reported on NET, because
    # that is what a trade actually returns.
    wins = net[net > 0]
    losses = net[net < 0]
    win_rate = float(len(wins) / len(net)) if len(net) else 0.0
    avg_w = float(wins.mean()) if len(wins) else 0.0
    avg_l = float(-losses.mean()) if len(losses) else 0.0
    rr = float(avg_w / avg_l) if avg_l > 0 else 0.0
    span_days = max((idx[-1] - idx[0]).total_seconds() / 86400.0, 1.0)
    per_week = float(len(net) / (span_days / 7.0))

    return {"z": round(z, 3), "gz": round(gz, 3),
            "edge": round(float(pnl.mean() * tv), 4),
            "sd": round(float((pnl * tv).std(ddof=1)), 5),
            "cu": round(float(net.mean()) / cost, 5) if cost else None,
            "mde": round(float((pnl * tv).std(ddof=1)) / cost
                         * 3.5 / max(eff, 1) ** 0.5, 4) if cost else None,
            "net": round(float(net.mean()), 4), "n": int(len(net)),
            "eff_n": int(eff), "overlap": round(ov, 2), "delay": delay,
            "win_rate": round(win_rate, 4), "rr": round(rr, 3),
            "per_week": round(per_week, 2),
            "avg_win": round(avg_w, 3), "avg_loss": round(avg_l, 3)}


def selftest(d, tv=None, cost=None, bar_s=None):
    """Plant a known edge and confirm the evaluator finds it.

    The plant has to match what the evaluator MEASURES, which is a
    FORWARD return conditioned on the sign of the last move. A jump at
    the bar itself is already history by then -- the first version of
    this planted exactly that and correctly failed, which is the test
    catching its own author rather than the harness.
    """
    x = d.copy()
    idx = x.index
    hh, mm = 14, 15
    hit = np.asarray((idx.hour == hh) & (idx.minute == mm))
    if hit.sum() < MIN_TRADES * 2:
        return True                      # too little data to self-test
    # SCALE THE PLANT TO THE INSTRUMENT. A fixed 2.0 points is huge for
    # FX and smaller than the 5-minute noise in ES -- and because the
    # evaluator takes direction from sign(close.diff()), a plant under
    # the noise gets the sign wrong a third of the time and half the
    # planted edge disappears. That produced a false HALT on ES while
    # the harness was working correctly.
    step = float(np.nanmedian(np.abs(np.diff(x["close"].values))))
    amp = max(4.0 * step, 1e-9)
    inc = np.zeros(len(x))
    inc[hit] = amp
    inc[np.roll(hit, 1)] = amp           # and the bar AFTER it
    # AND THE BAR AFTER THAT. Entry is now structurally at t+1
    # (ENTRY_LAG), so a plant that finishes moving at t+1 leaves nothing
    # for the trade to capture and the harness would report itself
    # blind. The plant has to extend past the entry, not up to it.
    inc[np.roll(hit, 2)] = amp
    x["close"] = x["close"].values + np.cumsum(inc)
    bs = bars_per(d) if bar_s is None else bar_s
    h = {"kind": "footprint", "dim": "minute_of_day",
         "bucket": f"{hh:02d}:{mm:02d}", "metric": "vol", "dir": "with",
         "hold_s": bs, "cond": "none"}
    r = evaluate(x, h, tv, cost, bar_s=bs)
    return r is not None and r["z"] > 3.0


def feats_of(libs, sym, tier, name, tape):
    """Recompute one named feature on an arbitrary slice.

    The vault and the delay control both need the feature evaluated on
    a tape the library never grew on. Recomputing from the stored spec
    is the only safe way -- reusing the search-set array would silently
    misalign, and a misaligned feature does not error, it just returns
    a different number.
    """
    lib = libs.get(f"{sym}/t{tier}")
    spec = lib.kept.get(name) if lib else None
    if spec is None:
        return None
    try:
        return FeatureLibrary.evaluate_spec(tape, spec, {})
    except Exception:                                         # noqa: BLE001
        return None


def _pnl_series(d, h, tv, cost, feats, bar_s):
    """Per-trade net P&L in chronological order, for stability testing.

    Recomputed rather than returned from evaluate() so the ordering is
    guaranteed to be chronological -- period stability split on a
    reordered series would silently test nothing.
    """
    try:
        r = evaluate(d, h, tv, cost, feats, bar_s)
        if not r:
            return None
        import numpy as _np
        idx = d.index
        if h.get("kind") == "flow":
            x = HY.flow_series(d, h["mech"])
        elif h.get("kind") == "feature":
            x = (feats or {}).get(h["feat"])
        else:
            x = None
        bars = max(int(round(h["hold_s"] / bar_s)), 1)
        c = d["close"]
        fwd = (c.shift(-bars) - c)
        same = idx.normalize().values == \
            pd.Series(idx).shift(-bars).dt.normalize().values
        fwd = fwd.where(same).values
        if x is not None:
            okx = _np.isfinite(x)
            cut = _np.nanpercentile(x[okx], 80 if h["side"] == "hi" else 20)
            m = ((x >= cut) if h["side"] == "hi" else (x <= cut)) & okx
            side = _np.full(len(d), 1.0 if h.get("ls") == "long" else -1.0)
        else:
            if h["dim"] == "minute_of_day":
                hh, mm = (int(v) for v in str(h["bucket"]).split(":"))
                m = (idx.hour == hh) & (idx.minute == mm)
            elif h["dim"] == "day_of_month":
                m = idx.day == int(h["bucket"])
            else:
                m = idx.dayofweek == int(h["bucket"])
            m = _np.asarray(m)
            if h["cond"] != "none":
                m = m & _conds(d)[h["cond"]]
            sgn = _np.sign(c.diff().fillna(0.0)).values
            side = sgn if h["dir"] == "with" else -sgn
        raw = side * fwd
        sel = _np.flatnonzero(m & _np.isfinite(raw))
        if len(sel) < MIN_TRADES:
            return None
        return raw[sel] * tv - cost
    except Exception:                                         # noqa: BLE001
        return None


def fwd_for_features(d, bars=1):
    y = (d["close"].shift(-bars) - d["close"]).values
    same = d.index.normalize().values == \
        pd.Series(d.index).shift(-bars).dt.normalize().values
    return np.where(same, y, np.nan)


# ------------------------------------------------------------------ loop
def measure_slate(sym, srch, slate, tier, tv, cost, feats, bar_s, tape_memo):
    """The shared slate, measured here but JUDGED ONCE, globally.

    These do not each cost a trial. One mechanism is one hypothesis
    however many markets it is measured in, and charging 23 trials for 23
    measurements of the same idea is what was driving the bar up while
    destroying the power to see anything broad and weak.

    Factored out of sweep() because a slate-only shard runs exactly this
    and nothing else; two copies of the measurement would be two things
    to keep in step, and they would not stay in step.
    """
    book = SLATE.get("book")
    n_slate = 0
    t_slate = time.time()
    # A CEILING, NOT A SCHEDULE. With the slate sized per market this is
    # never reached in normal running (~60s of work against a 240s box);
    # it exists so one pathological market cannot hold back the pooled
    # verdict for the other twenty-two. It was raised to 600 to paper
    # over the worker-scaled slate, which is no longer there.
    slate_budget = float(os.environ.get("RESEARCH_SLATE_S", "240"))
    for h in slate:
        if os.path.exists(STOP):
            break
        # Bounded: a slow market must not delay the pooled verdict for
        # every other market. Whatever was measured still pools; a
        # mechanism simply has fewer markets behind it, and the market
        # floor in pooled.py already refuses to answer below five.
        if time.time() - t_slate > slate_budget:
            say("slate_timeboxed", market=sym, tier=tier, measured=n_slate,
                of=len(slate))
            break
        fam = h.pop("_family", None)
        hh = dict(h)
        hh["market"] = sym
        hh["tier"] = tier
        try:
            r = evaluate(srch, hh, tv, cost, feats, bar_s, memo=tape_memo)
        except Exception:                                     # noqa: BLE001
            continue
        if not r:
            continue
        n_slate += 1
        _tick("s")
        if book is not None:
            with _SHARED:
                book.add(h, sym, r, cost, family=fam)
    if n_slate:
        say("slate_measured", market=sym, tier=tier, mechanisms=n_slate)
    return n_slate


def sweep(sym, d, led, mem, libs, tier, tv, cost, budget=500,
          base_cols=None, points=None, mrows=None, shard=(0, 1)):
    """One market, one tier: grow features, build hypotheses, score.

    `shard` is (index, count) over the shared slate. When there are more
    cores than markets the extra workers take slate shards rather than
    sitting idle: shard 0 is the full sweep for that market, shards 1..n
    measure their share of the slate and nothing else. Only shard 0 grows
    features, spends trials, or scores the market's private hypotheses,
    so the ledger sees each of those exactly once no matter how the work
    was divided.
    """
    srch, vault = split(d)
    bar_s = bars_per(d)
    if not selftest(srch, tv, cost, bar_s):
        return None, f"selftest failed on {sym} tier{tier}: harness blind"

    si, sn = int(shard[0]), max(1, int(shard[1]))
    if si > 0:
        # A slate-only shard. attach_context still runs: the slate's
        # conditions are drawn against context columns, and a mechanism
        # whose condition is missing from the tape is skipped rather than
        # measured against a different tape than its siblings.
        attach_context(sym, srch)
        slate = ([dict(h) for h in SLATE["hyps"]][si::sn]
                 if "high" in srch.columns else [])
        measure_slate(sym, srch, slate, tier, tv, cost, {}, bar_s, {})
        return (0, [], set()), None

    # ---- layer 1: grow the vocabulary (search set only, never vault)
    stage(f"{sym} tier {tier}: building features")
    lib = libs.setdefault(f"{sym}/t{tier}", FeatureLibrary(keep=20))
    y = fwd_for_features(srch, 1)
    before = len(lib.scores)
    with _GROW_GATE:
        kept = lib.grow(srch, y,
                        np.random.default_rng(led.d["trials"] % 9973),
                        base_cols=base_cols)
    gc.collect()
    # Every feature scored is a trial. Not counting them would let the
    # search buy hundreds of extra looks for free and keep the bar low.
    #
    # CHARGED BY NAME, NOT BY COUNT. The feature library lives in memory
    # only, so every restart rebuilds it from nothing -- and `before`
    # was 0 on a fresh boot, so the whole library was charged again for
    # rediscovering exactly the features it had already paid for. The
    # production console showed the shape of it plainly: 28 restarts,
    # "features grown and kept" reading 0 with a 24-hour movement of
    # -488. At roughly 20 kept features across 23 markets that is
    # thousands of phantom trials, and since the bar rises with the
    # trial count, the searcher was making its own standard harder every
    # time it was redeployed.
    #
    # The ledger now remembers which feature names have been charged, so
    # a rediscovered feature is free and a genuinely new one still costs
    # a trial. Growth is deterministic given the tape and the seed, so
    # this is not a loophole: the same feature really is the same look.
    fresh_feats = led.charge_features(f"{sym}/t{tier}", lib.scores)
    led.bump(fresh_feats)
    if fresh_feats < max(len(lib.scores) - before, 0):
        say("features_recharged_free", market=sym, tier=tier,
            grown=len(lib.scores), charged=fresh_feats,
            note="the rest were already paid for before the last restart")

    memo = {}
    feats = {}
    # ONE cache per market for tape-derived arrays (rolling normaliser,
    # ATR, shape masks). Profiling showed 79% of every evaluation was a
    # rolling median recomputed per hypothesis; there are only 54
    # distinct shape masks per tape and hundreds of hypotheses using
    # them. Scoped to this sweep so it cannot leak between tapes.
    tape_memo = {}
    for nm, spec in lib.kept.items():
        try:
            feats[nm] = FeatureLibrary.evaluate_spec(srch, spec, memo)
        except Exception:                                     # noqa: BLE001
            continue
    del memo

    # ---- layer 3: what past failures license
    fam_mult = {}
    ctx_conds = attach_context(sym, srch)
    if ctx_conds:
        say("context", market=sym, tier=tier, conditions=ctx_conds)

    deduced = {}
    for fam in list((mem.insights().get("horizons") or {})):
        th = mem.target_horizon(fam)
        if th:
            deduced[fam] = [th]
    hyps = HY.expand(HY.find_footprints(srch), extra_holds=deduced,
                     extra_conds=ctx_conds)
    for h in hyps:
        fam_mult.setdefault(h["_family"], mem.hold_multiplier(h["_family"]))
    for fam, mult in list(fam_mult.items()):
        if mult != 1.0:
            n_changed = 0
            for h in hyps:
                if h["_family"] == fam:
                    h["hold_s"] = int(h["hold_s"] * mult)
                    n_changed += 1
            # RECORD THE CHANGE, not just the lesson. A system that
            # displays what it learned but cannot show what it did
            # differently is a logging system wearing a learning
            # system's clothes.
            mem.adapt("hold", fam,
                      before=f"{HY.HOLDS_S}s",
                      after=f"{[int(x * mult) for x in HY.HOLDS_S]}s",
                      why=mem.lesson(fam)[0])
    # ORDER-FLOW MECHANISMS, where the columns exist. These are the only
    # hypotheses in the system with a reason stated before the test --
    # everything else is a footprint, which is a place a reason might
    # have left a mark.
    flow_cols = set(srch.columns)
    if {"imb", "depl", "tflow"} & flow_cols:
        fh = HY.from_flow(flow_cols,
                          mem.hold_multiplier("flow/queue_depletion"),
                          extra_holds=deduced)
        hyps += fh
        say("flow_hypotheses", market=sym, tier=tier, n=len(fh),
            mechanisms=sorted({h["mech"] for h in fh}))

    # THE SHARED SLATE. Recurring price behaviour and destinations, drawn
    # ONCE per cycle in main() so that every market answers the same
    # question and the answers can be combined. Previously each market
    # drew its own private random sample, so no two markets ever tested
    # the same mechanism and the breadth of this dataset -- the single
    # most valuable thing it has -- was never used as evidence.
    # This shard's share of the slate. sn == 1 when there are at least as
    # many markets as workers, which is the common case and leaves the
    # slice a no-op.
    slate = ([dict(h) for h in SLATE["hyps"]][si::sn]
             if "high" in srch.columns else [])


    fmult = mem.hold_multiplier("feature/d1")
    if fmult != 1.0:
        mem.adapt("hold", "feature/d1",
                  before=f"{HY.HOLDS_S}s",
                  after=f"{[int(x * fmult) for x in HY.HOLDS_S]}s",
                  why=mem.lesson("feature/d1")[0])
    hyps += HY.from_features(sorted(lib.scores.items(), key=lambda kv: -kv[1]),
                             FEAT_FLOOR, fmult)

    # THE CONTINUOUS SPACE ON THE DEEP TIERS.
    #
    # Tier 2 reported EXHAUSTED: "every hypothesis this tape can generate
    # at this resolution has already been tested." That was true and it
    # was a design hole. The footprint families are a bounded grid, so
    # they run out; the shape and destination space is continuous and
    # never does. Tier 1 reaches it through the shared slate, but the
    # slate is POOLED evidence and a deep NQ contract is not a
    # twenty-fourth market -- it is the same market again, so it cannot
    # join the pool without inflating the sample on a discount
    # calibrated for distinct instruments.
    #
    # So the deep tiers draw their own, tested as ordinary per-market
    # hypotheses: charged a trial each, judged against the rising bar,
    # deduped by the ledger forever. This is where that draw belongs.
    # The deep tape is the highest-powered evidence in the system --
    # 95,137 bars at 15 seconds against tier 1's few thousand -- and
    # until now it was spending that power re-asking a question that had
    # run out of new forms.
    #
    # Only when there is NO deep slate. When there is one, the same
    # shapes are already being measured in every quarter and pooled,
    # which is strictly more powerful for the same compute -- testing
    # them privately as well would spend the budget twice to learn less.
    if tier >= 2 and "high" in srch.columns and not SLATE.get("hyps"):
        rng_deep = np.random.default_rng(
            (hash(sym) & 0xFFFF) * 7919 + led.d["trials"] % 2**31)
        n_deep = int(os.environ.get("RESEARCH_DEEP_SHAPES", "400"))
        deep_h = HY.from_shapes(rng_deep, cap=n_deep)
        deep_h += HY.from_destinations(
            rng_deep, ["squeeze", "expansion", "run_up", "run_dn",
                       "inside", "outside"], cap=max(60, n_deep // 4),
            bar_s=float(bar_s or 300.0))
        deep_h = [h for h in deep_h if h.get("kind") != "feature"]
        hyps += deep_h
        say("deep_continuous", market=sym, tier=tier, drawn=len(deep_h),
            note="the deep tape gets the continuous shape and destination "
                 "space, which cannot exhaust, instead of only the "
                 "bounded footprint grid that already has")
    for fam in {h["_family"] for h in hyps}:
        pr = led.family_prior(fam)
        if pr < 0.5:
            f = led.d["families"].get(fam, {})
            mem.adapt("effort", fam, before="1.00x",
                      after=f"{pr:.2f}x",
                      why=(f"{f.get('n', 0)} hypotheses tested in this "
                           f"family, best z {f.get('best_z', 0):.2f}, "
                           f"nothing cleared the bar -- effort reduced, "
                           f"not stopped, since a family is not disproved "
                           f"by its members failing"))
    hyps.sort(key=lambda h: -led.family_prior(h["_family"]))
    # ORDER BY WHAT THE MAP SAYS. Same budget, spent on the most
    # promising and the least understood candidates first rather than in
    # family order. Nothing is dropped and nothing is cheapened; see
    # surrogate.py for why ordering cannot manufacture significance.
    sur = SLATE.get("surrogate")
    if sur is not None and sur.n >= 200:
        fams = {id(h): h.get("_family") for h in hyps}
        hyps = sur.order(hyps, fams,
                         rng=np.random.default_rng(led.d["trials"] % 7919))

    measure_slate(sym, srch, slate, tier, tv, cost, feats, bar_s, tape_memo)

    done = 0
    cands = []
    allz = []
    for h in hyps:
        if os.path.exists(STOP):
            break
        fam = h.pop("_family", None)
        h["market"] = sym
        h["tier"] = tier
        if led.seen(h):
            continue
        try:
            r = evaluate(srch, h, tv, cost, feats, bar_s, memo=tape_memo)
        except Exception as exc:                              # noqa: BLE001
            say("eval_error", err=str(exc)[:160], hyp=HY.describe(h))
            continue
        bar = led.bar()
        mode = classify(r, bar, cost)
        mem.note(fam, mode, r)
        if r is None:
            continue
        # EVIDENCE FOR THE INFERENCE ENGINE. Gross edge against horizon,
        # pooled per family, is what the horizon-crossing fit reads.
        # Gross, not net -- the whole question is where the growing
        # gross curve meets the flat cost line, and netting cost off
        # first destroys exactly that.
        with _SHARED:
          if points is not None:
            # IN UNITS OF THIS MARKET'S OWN COST. Pooling raw dollars
            # across markets compares ZB's $31 tick with MNQ's $0.50
            # and then judges the pool against one of them; that is the
            # same "one market's economics" error that made every 6A
            # trade score -$0.5992. A ratio of 1.0 means "paid for
            # itself here", and that means the same thing everywhere.
            points.setdefault(fam, []).append(
                (h["hold_s"], r["edge"] / cost if cost > 0 else 0.0))
          if mrows is not None:
            mrows.setdefault(fam, []).append((sym, r["edge"]))
        allz.append(r.get("gz", r["z"]))
        led.record(h, r, family=fam)
        done += 1
        LIVE["trials"] = led.d["trials"]
        _tick("v")
        LIVE["market"] = sym
        LIVE["tier"] = tier
        if mode == "confirmed":
            cands.append((dict(h), fam, r, bar, srch, vault, bar_s))
        if done >= budget:
            break
    # THE EMPIRICAL NULL for this sweep: what |z| the same machinery
    # reached across every cell it scored. Candidates are judged against
    # their own siblings, which accounts for the dependence between
    # hypotheses that a theoretical correction cannot see.
    # COVERAGE. How much of what was generated this cycle was already
    # in the ledger. A tape that returns 100% seen has been exhausted at
    # this resolution, and that has to be SAID -- a searcher quietly
    # regenerating hypotheses it has already tested looks identical from
    # outside to one finding nothing new, and only one of those is a
    # reason to add data.
    gen = len(hyps)
    fresh = done
    cov = 1.0 - (fresh / max(gen, 1))
    if cov > 0.97:
        say("EXHAUSTED", market=sym, tier=tier, generated=gen,
            new=fresh, seen_pct=round(cov * 100, 1),
            why="every hypothesis this tape can generate at this "
                "resolution has already been tested. More search here "
                "buys nothing; more DATA or a finer resolution would.")

    null99 = VAL.empirical_null(allz)
    if null99:
        # Both figures, so the one-sided change is visible in the log
        # rather than being a number that quietly moved. On a tape with
        # a heavy loss tail these differ by an order of magnitude, and
        # the gap IS the finding -- see validate.empirical_null.
        two = VAL.empirical_null(allz, two_sided=True)
        say("empirical_null", market=sym, tier=tier, cells=len(allz),
            p99=round(null99, 2), p99_abs=round(two, 2) if two else None,
            theoretical_bar=round(led.bar(), 2),
            note=("one-sided: the search only promotes positive net, so "
                  "the loss tail is arithmetic rather than chance"))
    cands = [(*c, null99, mrows) for c in cands]
    return (done, cands, kept), None


def _deep_slate(deep, res, cycle, led, syms):
    """Mechanisms every NQ quarter answers, so they can be pooled.

    WHY THE DEEP TIER NEEDED ITS OWN POOL. One contract alone resolves
    essentially nothing: 95,137 bars at 15s, a cell firing on a tenth of
    them, gives 9,514 trades and a smallest resolvable edge near a whole
    round trip per trade -- which this project's own rule calls bug
    territory rather than a find. The depth was there and the power was
    not, because each quarter was judged by itself.

    The eight contracts are PERFECTLY DISJOINT in time:

        NQU4  2024-06-21 -> 2024-09-19     NQU5  2025-06-20 -> 2025-09-18
        NQZ4  2024-09-20 -> 2024-12-19     NQZ5  2025-09-19 -> 2025-12-18
        NQH5  2024-12-20 -> 2025-03-20     NQH6  2025-12-19 -> 2026-03-19
        NQM5  2025-03-21 -> 2025-06-19     NQM6  2026-03-20 -> 2026-06-17

    -- a continuous two-year span cut into eight non-overlapping
    quarters, 786,064 bars at 15 seconds. Combining them is not
    double-counting anything; it is simply the whole sample instead of
    an eighth of it, and it drops the smallest resolvable edge at a
    15-second hold from about +0.96 to about +0.34 round trips.

    It also gives the quarter-stability test for free. A mechanism has
    to be measurable in at least six of the eight and agree in sign
    across them, which is the "6/8 green quarters" gate stated as a
    requirement of the pooling rather than bolted on afterwards.

    ONE HONEST CAVEAT, stated rather than buried: these are eight
    samples of ONE instrument. A survivor here is evidence about NQ, not
    about markets in general, and it is recorded under POOLED_DEEP so it
    can never be confused with the cross-market slate.
    """
    rng = np.random.default_rng(
        (cycle * 104729 + int(res) * 7919 + led.d["trials"]) % 2**32)
    # The ceiling the tape can actually resolve, measured on one
    # contract and shared -- the quarters are the same instrument at the
    # same resolution, so their dispersion law is the same.
    ceil_s = None
    try:
        probe = deep[syms[0]]
        ceil_s = CAL.hold_ceiling(probe, *spec_for(syms[0]),
                                  bars_per(probe), led.bar(),
                                  target_rt=0.5, markets=len(syms))
    except Exception as exc:                                  # noqa: BLE001
        say("deep_ceiling_failed", err=str(exc)[:160])
    cap = int(os.environ.get("RESEARCH_DEEP_SLATE", "600"))
    sl = HY.from_shapes(rng, cap=cap, hold_max=ceil_s)
    sl += HY.from_destinations(
        rng, ["squeeze", "expansion", "run_up", "run_dn",
              "inside", "outside"], cap=max(80, cap // 4),
        bar_s=float(res), hold_max=ceil_s)
    sl = [h for h in sl if h.get("kind") != "feature"]
    fresh = []
    for h in sl:
        probe = {k: v for k, v in h.items() if k != "_family"}
        probe["market"] = "POOLED_DEEP"
        probe["tier"] = 2
        probe["res"] = int(res)
        if not led.seen(probe):
            fresh.append(h)
    say("deep_slate_drawn", cycle=cycle, res=res, mechanisms=len(fresh),
        hold_ceiling_s=None if ceil_s is None else round(ceil_s),
        note="one slate for all eight quarters, judged once on the "
             "pooled evidence -- a single quarter cannot resolve "
             "anything smaller than about one round trip per trade")
    return fresh


def _judge_deep(book, res, cycle, led, mem, syms):
    """Pool the quarters and record one verdict per mechanism."""
    if book is None:
        return
    stage(f"combining {len(syms)} NQ quarters at {res}s")
    try:
        # DISJOINT SAMPLES, so effective_n is the count. The
        # cross-market discount in data_tiers exists because four equity
        # indices move together; two non-overlapping quarters of NQ do
        # not overlap at all, and discounting them as if they did would
        # throw away the sample this whole tier exists to provide.
        need = int(os.environ.get("RESEARCH_DEEP_MIN_Q", "6"))
        verdicts = book.test(lambda s: float(len(s)),
                             min_markets=min(need, max(2, len(syms))))
    except Exception as exc:                                  # noqa: BLE001
        say("deep_pool_failed", err=str(exc)[:160])
        return
    cands = []
    for v in verdicts:
        h = dict(v["hyp"])
        h["market"] = "POOLED_DEEP"
        h["tier"] = 2
        h["res"] = int(res)
        if led.seen(h):
            continue
        r = {"z": round(v["z"], 3), "gz": round(v["z"], 3),
             "cu": round(v["mean_cost_units"], 5),
             "edge": None, "net": None,
             "n": v["n_total"], "eff_n": int(v["effective_n"]),
             "mde": v.get("mde"), "per_week": v.get("per_week"),
             "per_week_per_market": v.get("per_week_per_market"),
             "markets": v["markets"], "k": v["k"],
             "agree": v["agree"], "tau2": round(v["tau2"], 6),
             "per_market": v["per_market"], "pooled": True,
             "one_instrument": True}
        led.record(h, r, family=v.get("family"))
        bar = led.bar()
        if (v["z"] >= bar and v["mean_cost_units"] > 0
                and v["agree"] >= PO.MIN_AGREE):
            cands.append((h, v, bar))
    # THE MDE DISTRIBUTION, not the top row's. The highest-z mechanism
    # is often a rare cell with poor power, so reporting its mde alone
    # reads as though the whole tier were blind when the most powerful
    # quarter of it is not. What matters is how small an edge the tier
    # COULD see across the mechanisms it tested.
    mdes = sorted(v["mde"] for v in verdicts
                  if v.get("mde") is not None and np.isfinite(v["mde"]))
    ns = sorted(v["n_total"] for v in verdicts if v.get("n_total"))

    def _p(a, q):
        return round(float(np.percentile(a, q)), 4) if a else None

    say("deep_pool_judged", cycle=cycle, res=res,
        quarters=len(syms), mechanisms=len(verdicts),
        candidates=len(cands),
        best_z=round(verdicts[0]["z"], 2) if verdicts else None,
        bar=round(led.bar(), 2),
        mde_p5=_p(mdes, 5), mde_p25=_p(mdes, 25), mde_p50=_p(mdes, 50),
        trades_p50=_p(ns, 50),
        note="mde is the smallest edge, in round trips per trade, the "
             "pooled test could have detected -- p5 is the most powerful "
             "twentieth of the mechanisms tested, and a single quarter "
             "on its own sits near 1.0")
    for h, v, bar in cands[:6]:
        say("DEEP_POOLED_CANDIDATE", z=round(v["z"], 2), bar=round(bar, 2),
            quarters=v["k"], agree=v["agree"],
            cost_units=round(v["mean_cost_units"], 3),
            what=HY.describe(h),
            caveat="eight quarters of ONE instrument -- evidence about "
                   "NQ, not about markets in general")
        mem.adapt("pooled_deep", v.get("family") or "mechanism",
                  before="untested across quarters",
                  after=f"{v['z']:.2f} sigma over {v['k']} NQ quarters",
                  why=(f"agreed in sign in {v['agree']:.0%} of them and "
                       f"paid {v['mean_cost_units']:.2f} round trips per "
                       f"trade on a tape a single quarter could not have "
                       f"resolved"))


def _sweep_deep(deep, res, cycle, led, mem, libs, points, mrows):
    """Every NQ contract at one resolution, in parallel, at tier 2.

    Kept out of the CROSS-MARKET slate on purpose: that pool applies a
    correlation discount calibrated for distinct instruments, and eight
    quarters of NQ are not eight markets. They get their own pool
    instead -- see _deep_slate for why that is both honest and the
    difference between this tier resolving nothing and resolving
    something.
    """
    syms = sorted(deep)
    say("tier2_parallel", cycle=cycle, res=res, contracts=len(syms),
        bars=sum(len(v) for v in deep.values()),
        note="all contracts at this resolution, not one per cycle")
    dslate = _deep_slate(deep, res, cycle, led, syms)
    dbook = PO.PooledBook()
    snap = PAR.snapshot(led, mem)
    ctx = {"snap": snap, "data": deep, "slate": dslate,
           "surrogate": SLATE.get("surrogate"),
           "libs": {k: v for k, v in libs.items()
                    if k.split("/")[0] in deep}}
    stage(f"deep tier: {len(syms)} NQ contracts at {res}s bars")
    pool = PAR.Pool(min(resize_workers(led), len(syms)), ctx)
    try:
        results = pool.map((s, 2, int(os.environ.get("RESEARCH_BUDGET_T2",
                                                     "400")))
                           for s in syms)
    finally:
        pool.close()
    for out in results:
        if os.path.exists(STOP):
            break
        sym = out.get("sym")
        if out.get("error"):
            if "selftest" in str(out["error"]):
                say("tier2_selftest_failed", why=str(out["error"])[-1400:])
            else:
                # THE WHOLE TRACEBACK, or at least its tail. Truncating a
                # traceback to its first 300 characters keeps the frame
                # that called the failing code and throws away the line
                # that says what went wrong -- which is the only part
                # anyone needs. Cost a diagnosis once; not again.
                say("tier2_sweep_failed", market=sym,
                    err=str(out["error"])[-1400:])
            continue
        tv, cost = spec_for(sym)
        PAR.replay(led, mem, out, arch=ARCH["a"])
        for k, v in (out.get("libs") or {}).items():
            lib = libs.setdefault(k, FeatureLibrary(keep=20))
            lib.kept.update(v.get("kept") or {})
            lib.scores.update(v.get("scores") or {})
        for fam, pts in (out.get("points") or {}).items():
            points.setdefault(fam, []).extend(pts)
        for fam, rows in (out.get("mrows") or {}).items():
            mrows.setdefault(fam, []).extend(rows)
        _merge_book(dbook, out.get("book") or {})
        LIVE["market"] = sym
        LIVE["tier"] = 2
        cands = _rehydrate(out.get("candidates") or [], deep.get(sym),
                           sym=sym)
        gauntlet(sym, 2, cands, led, mem, libs, tv, cost)
        say("cycle_market", cycle=cycle, market=sym, tier=2,
            tested=out.get("done"), features=len(out.get("kept") or []),
            bars=len(deep.get(sym, ())),
            trials=led.d["trials"], bar=round(led.bar(), 2),
            note=DT.Curriculum.caveat(1, 2, "NQ"))
    # ONE VERDICT PER MECHANISM, over every quarter that measured it.
    # This is the step that makes the deep tier worth running: alone,
    # a quarter cannot resolve anything smaller than roughly a whole
    # round trip per trade.
    if not os.path.exists(STOP):
        _judge_deep(dbook, res, cycle, led, mem, syms)


# The running searcher's own Ledger, for readers in this process.
LIVE_LEDGER = {"l": None}


def _read_json(p, default=None):
    try:
        return json.load(open(p))
    except Exception:                                         # noqa: BLE001
        return default

LIBS_PATH = os.path.join(RDIR, "features.json")


def _load_libs():
    """Bring back the grown feature vocabulary from the last process.

    Feature discovery is compositional -- each generation seeds from
    what the last one kept -- so an in-memory-only library means every
    restart resets the search to first principles rather than merely
    costing the time to regrow. Production had restarted 28 times.
    """
    try:
        d = json.load(open(LIBS_PATH))
    except Exception:                                         # noqa: BLE001
        return {}
    libs, bad = {}, 0
    for scope, blob in (d or {}).items():
        try:
            lib = FeatureLibrary.load(blob)
        except Exception:                                     # noqa: BLE001
            continue
        bad += getattr(lib, "_unparseable", 0)
        libs[scope] = lib
    say("features_restored", scopes=len(libs),
        features=sum(len(l.scores) for l in libs.values()),
        unreadable=bad,
        note="compositional discovery seeds from what was kept, so this "
             "is where the search resumes rather than where it restarts")
    return libs


def _save_libs(libs):
    if not libs:
        return
    try:
        tmp = LIBS_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump({k: v.dump() for k, v in libs.items()}, f,
                      separators=(",", ":"))
        os.replace(tmp, LIBS_PATH)
    except Exception as exc:                                  # noqa: BLE001
        say("features_save_failed", err=str(exc)[:160])


def spec_for(sym):
    """Contract economics for a sweep name, deep-tier names included.

    Tier-1 names are the symbol; tier-2 names carry their tape, as in
    "NQ@NQU4@60s". Both are the same contract and must be charged the
    same round trip -- a deep sweep priced at the wrong tick would make
    every one of its results incomparable with the shallow ones.
    """
    s = str(sym)
    return SPEC.get(s) or SPEC[s.split("@")[0]]


def _tape_for(market):
    """Rebuild the exact tape a stored hypothesis was tested on.

    Market names carry their tape: "NQ" is tier 1, "NQ@NQU4@60s" is the
    NQU4 contract at 60-second bars, "NQbook@5s" is the book. Evaluating
    a tier-2 hypothesis against tier-1 five-minute bars would return a
    number -- a wrong one, silently -- so the name has to be honoured.
    """
    m = str(market)
    try:
        if m.startswith("NQbook@"):
            res = int(m.split("@")[1].rstrip("s"))
            return DT.tier3(bar_s=res), "NQ"
        if "@" in m:
            parts = m.split("@")
            contract, res = parts[1], int(parts[2].rstrip("s"))
            for name, kind, path in DT.tier2_sources(res):
                if name == contract:
                    return DT.tier2_from(kind, path, res), "NQ"
            return None, None
        return None, m
    except Exception:                                     # noqa: BLE001
        return None, None


def backfill_metrics(led, data, k=40, budget_s=45.0):
    """Fill trades/week, win rate and RR on older ledger entries.

    THE TWO REASONS THE FIRST VERSION NEVER FILLED ANYTHING, both of
    which left "measuring..." on screen permanently:

      1  it passed feats=None, so every FEATURE hypothesis returned None
         immediately -- and the top of the leaderboard is almost all
         feature hypotheses
      2  it looked up tier-1 data by symbol, so a tier-2 hypothesis on
         "NQ@NQU4@60s" was scored against five-minute bars, which is a
         different tape and a different answer

    Now the tape is rebuilt from the stored market name and features are
    reconstructed from their names via FeatureLibrary.parse. Re-scoring
    is NOT a new trial -- the hypothesis is already counted -- so only
    the stored result gains fields and the bar is untouched.
    """
    t0 = time.time()
    n = 0
    cache = {}
    for row in led.near_misses(k):
        if time.time() - t0 > budget_s:
            break
        rec = led.d["tested"].get(row["fp"]) or {}
        if not isinstance(rec, dict) or rec.get("stub"):
            continue
        r = rec.get("result") or {}
        # TWO INDEPENDENT JOBS, and conflating them meant neither ran.
        # The first version skipped any row that already had metrics --
        # which also skipped the control re-check on exactly the rows
        # that needed it, since a freshly scored artifact has full
        # metrics and has never been re-checked.
        need_metrics = bool(r) and r.get("win_rate") is None
        need_check = bool(r) and not rec.get("checked") \
            and not rec.get("killed")
        # a third job: rows measured on a tape that has since been
        # corrected need measuring again, not filtering away.
        need_rescore = bool(r) and led.outdated(rec) \
            and not rec.get("rescored")
        if not (need_metrics or need_check or need_rescore):
            continue
        h = dict(row["hyp"] or {})
        market = h.get("market", "")
        base = str(market).split("@")[0]
        if base not in SPEC:
            continue
        if market in cache:
            tape = cache[market]
        else:
            tape, _ = _tape_for(market)
            if tape is None:
                tape = data.get(base)
            cache[market] = tape
        if tape is None or len(tape) < 1000:
            continue
        tv, cost = SPEC[base]
        srch, _ = split(tape)
        bs = bars_per(srch)

        feats = None
        if h.get("kind") == "feature":
            spec = FeatureLibrary.parse(h.get("feat", ""))
            if spec is None:
                continue
            try:
                feats = {h["feat"]:
                         FeatureLibrary.evaluate_spec(srch, spec, {})}
            except Exception:                             # noqa: BLE001
                continue
        try:
            fresh = evaluate(srch, h, tv, cost, feats, bs)
        except Exception:                                 # noqa: BLE001
            continue
        if not fresh:
            continue
        # RE-STAMP THE EPOCH. This re-score just ran on the CURRENT tape,
        # so if the row was carrying an old epoch -- a measurement of
        # data that has since been corrected -- it is not carrying one
        # any more. Replace the numbers wholesale rather than patching
        # fields onto a stale result, and re-stamp. Without this a row
        # invalidated by a data fix stays flagged forever even after it
        # has been measured again on good data.
        if led.outdated(rec):
            rec["result"] = r = dict(fresh)
            rec["epoch"] = led.DATA_EPOCH
            rec["code_epoch"] = led.CODE_EPOCH
            rec["rescored"] = True
        elif need_metrics:
            for key in ("win_rate", "rr", "per_week", "gz",
                        "avg_win", "avg_loss"):
                if fresh.get(key) is not None:
                    r[key] = fresh[key]

        # RE-CHECK AGAINST CONTROLS THAT DID NOT EXIST WHEN IT WAS
        # SCORED. The ledger is permanent and lives on a volume, so an
        # artifact found before a control was written stays at the top
        # of the leaderboard forever unless something goes back for it.
        try:
            rd = evaluate(srch, h, tv, cost, feats, bs, delay=1)
            keep = (rd["net"] / fresh["net"]) if (rd and fresh["net"]) else 0
            if not rd or rd["net"] <= 0 or keep < 0.5:
                led.kill(h, [f"re-checked against the delay control: "
                             f"${fresh['net']:+.2f} becomes "
                             f"${(rd or {}).get('net', 0):+.2f} when "
                             f"entered one bar later ({keep:.0%} kept). "
                             f"This was scored before that control "
                             f"existed."])
            else:
                rec["checked"] = True
        except Exception:                                     # noqa: BLE001
            pass
        n += 1
    return n


def _merge_book(book, rows):
    """Fold a worker's pooled measurements into the parent's book.

    Each worker measured the SAME slate against its own markets, so the
    per-market dictionaries are disjoint by construction and merging is
    a union rather than a reconciliation.
    """
    for key, slot in (rows or {}).items():
        cur = book.rows.setdefault(
            key, {"hyp": slot.get("hyp"), "family": slot.get("family"),
                  "by": {}})
        if cur.get("hyp") is None:
            cur["hyp"] = slot.get("hyp")
            cur["family"] = slot.get("family")
        cur["by"].update(slot.get("by") or {})


def _rehydrate(rows, d, sym=None):
    """Put the tapes back on candidates that crossed a process boundary.

    A DataFrame does not belong in a pickle sent between processes, so
    workers return candidates without theirs. The parent already holds
    the tape and can split it again -- deterministically, so the vault
    boundary is identical to the one the worker used.
    """
    if d is None:
        return []
    srch, vault = split(d)
    bar_s = bars_per(d)
    # RE-ATTACH THE EXTERNAL CONTEXT.
    #
    # The worker called attach_context() on its own copy of the tape,
    # which registers regime masks (credit_stress, crowded_long,
    # short_gamma...) that hypotheses can then condition on. The parent
    # re-derives the tape from disk and had none of them, so the moment
    # a candidate conditioned on one reached the gauntlet, the delay
    # control raised KeyError and the whole cycle died -- after the
    # sweep, so every market's work went with it.
    #
    # Caught by the integration run rather than by reading the diff,
    # which is the only way a bug that lives in the SEAM between two
    # processes ever shows up. attach_context is deterministic given the
    # symbol and the index, so calling it here reproduces exactly the
    # masks the worker used.
    try:
        attach_context(str(sym), srch)
    except Exception as exc:                                  # noqa: BLE001
        say("context_reattach_failed", market=sym, err=str(exc)[:160])
    out = []
    for h, fam, r, bar, null99, mrows in rows:
        out.append((h, fam, r, bar, srch, vault, bar_s, null99, mrows))
    return out


def gauntlet(sym, tier, cands, led, mem, libs, tv, cost):
    """What a candidate must survive, in order, before it is believed.

    The order is deliberate. The delay control runs FIRST because it is
    cheap and because the vault is a finite resource -- spending the one
    permitted look at held-back data on a bid-ask bounce artifact burns
    it forever. On the first real run this gate would have caught a ZB
    "confirmed" result that had already reached the vault.
    """
    for h, fam, r, bar, srch, vault, bar_s, null99, mrows in cands:
        LIVE["candidates"] += 1
        say("CANDIDATE", market=sym, tier=tier, z=r["z"],
            bar=round(bar, 2), net=r["net"], n=r["n"], what=HY.describe(h))

        # THE SNIFF TEST, before the controls. Every bug in this project
        # was found by noticing a number that could not be true and
        # reasoning back to its cause. That step is now encoded: an
        # implausible result is not merely rejected, it points at the
        # specific machinery most likely to be broken.
        base = str(sym).split("@")[0]
        tickv = None
        if base in _SPEC_RAW:
            pv, tick, _c = _SPEC_RAW[base]
            tickv = pv * tick
        odd = PL.check_result(r, h, cost, tickv)
        if odd:
            say("IMPLAUSIBLE", market=sym, tier=tier,
                what=HY.describe(h),
                flags=[{"observed": a, "means": b, "look_at": c}
                       for a, b, c in odd],
                note="this is a candidate to DOUBT, not to celebrate -- "
                     "every finding this large in this project has so "
                     "far been a bug, and the suspects are listed")
            LIVE["killed"] += 1
            led.kill(h, [a for a, _b, _c in odd])
            mem.note(fam, "no_signal", r)
            continue

        # 1. BOUNCE GATE. Entering one bar later cannot hurt a real
        # prediction about the next hour, but it annihilates an artifact
        # that lives inside a single shared print: a feature built from
        # close[t]-close[t-1] scored against close[t+1]-close[t] shares
        # close[t] with its own target, so noise in that one print moves
        # both, and the "mean reversion" is the bid-ask bounce.
        fe = {}
        if h.get("kind") == "feature":
            fe = {h["feat"]: feats_of(libs, sym, tier, h["feat"], srch)}
        rd = evaluate(srch, h, tv, cost, fe, bar_s, delay=1)
        kept_frac = (rd["net"] / r["net"]) if (rd and r["net"]) else 0.0
        if not rd or rd["net"] <= 0 or kept_frac < 0.5:
            # NAME THE CAUSE, do not just record the death. The delay
            # control says "this failed"; the battery says which of the
            # known failure modes it is, by perturbing one thing at a
            # time and reading the pattern of what moves.
            dx = None
            try:
                dx = DG.diagnose(evaluate, srch, h, tv, cost, bar_s, fe)
            except Exception:                                 # noqa: BLE001
                pass
            say("KILLED_by_delay_control", market=sym, tier=tier,
                immediate_net=r["net"], delayed_net=(rd or {}).get("net"),
                kept=round(kept_frac, 3), what=HY.describe(h),
                diagnosis=(dx or {}).get("cause"),
                because=(dx or {}).get("what_it_means"),
                why="entering one bar later destroys it -- bid-ask "
                    "bounce inside the signal bar's own print, not a "
                    "prediction")
            if dx:
                rec = led.d["tested"].get(led.fingerprint(h))
                if isinstance(rec, dict):
                    rec["diagnosis"] = dx
            mem.note(fam, "wrong_sign", rd)
            led.kill(h, ["entering one bar later destroys it -- bid-ask "
                         "bounce inside the signal bar's own print"])
            continue

        # 2. the empirical bar, once there is calibration to raise it by
        ebar, why = mem.empirical_bar(bar)
        if ebar > bar + 0.01:
            mem.adapt("bar", "all", before=f"{bar:.2f} sigma",
                      after=f"{ebar:.2f} sigma", why=why)
        if r["z"] < ebar:
            say("below_empirical_bar", need=round(ebar, 2), why=why,
                what=HY.describe(h))
            continue

        # 3. the vault. One look, ever.
        if not led.can_touch_vault(h):
            continue
        vfeats = {}
        if h.get("kind") == "feature":
            vfeats = {h["feat"]: feats_of(libs, sym, tier, h["feat"], vault)}
            if vfeats[h["feat"]] is None:
                continue
        rv = evaluate(vault, h, tv, cost, vfeats, bar_s)
        led.touch_vault(h, rv or {})
        mem.note_vault(fam, r["z"], (rv or {}).get("z"),
                       r["n"], (rv or {}).get("n"))
        ok = bool(rv and rv["z"] > 2.0 and rv["net"] > 0)
        mem.note(fam, "confirmed" if ok else "vault_killed", rv)
        say("VAULT_RESULT", confirmed=ok, market=sym, tier=tier, vault=rv,
            delayed_net=rd["net"], what=HY.describe(h),
            note="survived the delay control and the vault. This is a "
                 "CANDIDATE for the full gauntlet -- all-cell null, "
                 "quarter stability, stale placebo, bot-exact "
                 "simulation -- not a strategy.")


def main():
    os.makedirs(RDIR, exist_ok=True)
    stage("loading the ledger")
    led = Ledger(os.path.join(RDIR, "ledger.json"))
    ap = os.path.join(RDIR, "archive.json")
    try:
        ARCH["a"] = AR.Archive(json.load(open(ap)) if os.path.exists(ap)
                               else None)
    except Exception:                                         # noqa: BLE001
        ARCH["a"] = AR.Archive()
    mem = Memory(os.path.join(RDIR, "memory.json"))
    stage("ledger loaded (%s entries)" % len(led.d["tested"]))
    once = os.environ.get("RESEARCH_ONCE") == "1"
    # Before anything forks, so every child inherits the same counters.
    start_progress()
    LIVE["trials"] = led.d["trials"]
    LIVE["started"] = now()
    say("boot", trials=led.d["trials"], bar=round(led.bar(), 2),
        feat_floor=FEAT_FLOOR, shrinkage=mem.shrinkage())

    stage("loading tier-1 data for %d markets" % len(SPEC))
    data = DT.tier1(set(SPEC))
    if not data:
        say("no_data")
        return
    say("loaded_tier1", markets=sorted(data), n=len(data),
        effective_n=DT.effective_n(sorted(data)),
        note="correlated markets are not independent evidence")

    # THE ONE LEDGER. The console lives in this same process and was
    # parsing the file again for itself -- a second 413 MB copy of an
    # object the searcher already holds, and one that every forked
    # worker then inherits and dirties. Handing over the live object
    # removes both.
    LIVE_LEDGER["l"] = led
    libs = _load_libs()
    cycle = 0
    # Hand the sampler live references so the learning graphs gain a
    # point every minute instead of once a sweep.
    _HIST_CTX.update(led=led, mem=mem, libs=libs, cycle=0)
    history_point()
    start_history_sampler(int(os.environ.get("RESEARCH_HIST_S", "60")))
    while True:
        if os.path.exists(STOP):
            say("stopped_by_file", path=STOP)
            break
        cycle += 1
        _HIST_CTX["cycle"] = cycle
        t0 = time.time()
        points, mrows, vols = {}, {}, {}

        # ---- draw this cycle's shared slate of MECHANISMS.
        # One slate, every market, so the answers combine. Unseen only:
        # the pooled fingerprint is what the ledger remembers, so a
        # mechanism is asked once and never again.
        stage("drawing this cycle's mechanisms")
        rng_s = np.random.default_rng((cycle * 7919 + led.d["trials"]) % 2**32)
        # SIZED PER MARKET, NOT PER WORKER. This was `260 * WORKERS`,
        # which is the wrong direction: the pool parallelises across
        # MARKETS, and every worker measures the WHOLE slate for its own
        # market. So scaling the slate by worker count multiplied the
        # work each worker does by the worker count and bought nothing --
        # 47 workers meant 12,220 shapes per market instead of 260, and
        # a cycle that should take ~10s took the full 600s time-box with
        # the console frozen on one stage line. Per-market work is a
        # constant; what more cores buy is more markets at once.
        #
        #   800 shapes + 200 destinations + ~500 bred  = ~1,500 per market
        #   measured at ~24 mechanisms/sec/core        = ~60s per market
        #
        # RESEARCH_SLATE still overrides, so the size can be raised for a
        # box with more time per cycle without touching this file.
        slate_cap = int(os.environ.get("RESEARCH_SLATE", "800"))
        # BOUND THE DRAW TO WHAT THE TAPES CAN RESOLVE. Measured on the
        # tier-1 five-minute tape pooled over every market, the smallest
        # edge a five-minute hold could show is about +0.65 round trips
        # and a four-hour hold about +31 -- and the draw's exploration
        # share reached four hours. Nothing at +31 RT/trade is a finding;
        # by this project's own rule an edge that large is a bug. The
        # ceiling is measured each cycle rather than assumed, because it
        # depends on how much tape there is, which grows.
        ref = next((data[s] for s in ("NQ", "ES", "CL") if s in data),
                   next(iter(data.values()), None))
        hold_cap = None
        if ref is not None:
            try:
                hold_cap = CAL.hold_ceiling(
                    ref, *SPEC.get("NQ", (2.0, 0.6)), bars_per(ref),
                    led.bar(), target_rt=1.0, markets=len(data))
            except Exception as exc:                          # noqa: BLE001
                say("slate_ceiling_failed", err=str(exc)[:160])
        say("slate_hold_ceiling", cycle=cycle,
            seconds=None if hold_cap is None else round(hold_cap),
            note="longest hold at which the pooled tier-1 evidence could "
                 "resolve an edge of one round trip per trade")
        slate = HY.from_shapes(rng_s, cap=slate_cap, hold_max=hold_cap)
        rng_d = np.random.default_rng((cycle * 6151 + led.d["trials"]) % 2**32)
        slate += HY.from_destinations(
            rng_d, ["squeeze", "expansion", "run_up", "run_dn",
                    "inside", "outside"], cap=max(120, slate_cap // 4),
            bar_s=300.0, hold_max=hold_cap)
        # BREED HALF THE SLATE FROM THE MAP. A purely random draw
        # explores forever without ever getting better; breeding from
        # elites gets better without exploring. Doing both is the point
        # of a quality-diversity search, and the split is explicit so it
        # can be argued with rather than buried.
        arch = ARCH["a"]
        if arch is not None and len(arch.cells) >= 8:
            bred = arch.breed(rng_s, max(8, len(slate) // 2),
                              mutate=HY.mutate_shape)
            slate = list(slate) + [b for b in bred if b]
            say("bred_from_map", cycle=cycle, bred=len(bred),
                cells_filled=len(arch.cells),
                note="children of the best strategy in each behavioural "
                     "niche, not fresh random draws")
        # THE SLATE MUST BE MARKET-AGNOSTIC OR IT CANNOT BE POOLED.
        # Breeding draws from elites of every family, and a FEATURE
        # hypothesis names a column in one market's own grown library --
        # "NQ/t1 feature #7" means nothing in ES. evaluate() returns None
        # for a feature it cannot find, so such a mechanism would be
        # measured in one market, skipped in the other twenty-two, and
        # then pooled from a single observation. Dropping them here is
        # not a loss: feature hypotheses are still tested per market in
        # the private sweep, where their features actually exist.
        n_before = len(slate)
        slate = [h for h in slate if h.get("kind") != "feature"]
        if len(slate) != n_before:
            say("slate_filtered", cycle=cycle, dropped=n_before - len(slate),
                why="feature hypotheses name one market's own library and "
                    "cannot be measured in the others")
        fresh = []
        for h in slate:
            # The probe must fingerprint IDENTICALLY to what will be
            # recorded after judging, or the ledger never recognises the
            # mechanism again and every cycle re-tests the same slate
            # while the trial count climbs.
            probe = {k: v for k, v in h.items() if k != "_family"}
            probe["market"] = "POOLED"
            probe["tier"] = 0
            if not led.seen(probe):
                fresh.append(h)
        SLATE["hyps"] = fresh
        SLATE["book"] = PO.PooledBook()
        say("slate_drawn", cycle=cycle, mechanisms=len(fresh),
            note="one slate for every market, judged once on the pooled "
                 "evidence")

        # ---- refit the map of the space from everything measured so far
        stage("fitting the map of the search space")
        try:
            sur = SG.Surrogate().fit(SG.from_ledger(led))
            SLATE["surrogate"] = sur if sur.n >= 200 else None
            if SLATE["surrogate"] is not None:
                mem.set_learned(sur.learned())
                say("map_fitted", rows=sur.n,
                    statements=len(sur.learned()))
        except Exception as exc:                              # noqa: BLE001
            say("map_failed", err=str(exc)[:160])
        # PARALLEL ACROSS MARKETS. Markets are independent -- each
        # sweep reads its own tape and writes only its own results --
        # so the only shared state is the ledger and the memory, and
        # both are written on the main thread after the workers return.
        #
        # Threads rather than processes on purpose: the work is numpy
        # and pandas, which release the GIL for the array operations
        # that dominate, and processes would need every tape pickled
        # to each worker. Measured, not assumed -- see the timing in
        # the commit.
        syms = [s for s in data if not os.path.exists(STOP)]
        for sym in syms:
            vols[sym] = float(data[sym]["close"].diff().abs().median() or 0.0)

        # PROCESSES, NOT THREADS. Measured on four markets: threads ran
        # at 0.90x of sequential -- slower than not parallelising at all,
        # because the GIL serialises everything here -- while processes
        # ran at 2.95x. On a many-core box that difference is the whole
        # throughput of the searcher. See researcher/parallel.py.
        # SPEND EVERY CORE. One job per market leaves (cores - markets)
        # children forked and idle -- 24 of 47 on this box -- each still
        # paying the fork's resident cost for nothing. When there are
        # more workers than markets the surplus takes SLATE SHARDS: the
        # slate is the same mechanisms in every market, so market M's
        # slate splits cleanly across `shards` workers and the pooled
        # book merges the pieces exactly as it merges markets. Shard 0
        # also does the market's private sweep; shards 1+ measure slate
        # only, so nothing is scored or charged twice.
        # Re-size for the ledger as it is NOW. Every child is a copy of
        # this process, and this process grows all day.
        nw = resize_workers(led)
        shards = max(1, min(4, nw // max(1, len(syms))))
        budget = int(os.environ.get("RESEARCH_BUDGET", "1200"))
        jobs = [(sym, 1, budget, (i, shards))
                for sym in syms for i in range(shards)]
        stage(f"sweeping {len(syms)} markets across "
              f"{min(nw, len(jobs))} processes"
              + (f" ({shards} slate shards each)" if shards > 1 else ""))
        snap = PAR.snapshot(led, mem)
        ctx = {"snap": snap, "data": data, "slate": SLATE["hyps"],
               "surrogate": SLATE.get("surrogate"),
               "libs": {k: v for k, v in libs.items()}}
        t_par = time.time()
        # Never fork more children than there is work for them.
        pool = PAR.Pool(min(nw, len(jobs)), ctx)
        try:
            results = pool.map(jobs)
        finally:
            pool.close()
        say("swept_parallel", cycle=cycle, markets=len(syms),
            workers=min(nw, len(jobs)), shards=shards, jobs=len(jobs),
            secs=round(time.time() - t_par, 1))

        for out in results:
            if os.path.exists(STOP):
                break
            sym = out.get("sym")
            if out.get("error"):
                # A worker failing on one market must not take the cycle
                # down with it; a blind SELFTEST failure still must.
                if "selftest" in str(out["error"]):
                    led.halt(out["error"])
                    say("HALT_selftest_failed", why=out["error"])
                    led.save(force=True)
                    mem.save()
                    return
                say("sweep_failed", market=sym,
                    err=str(out["error"])[-1400:])
                continue
            tv, cost = SPEC[sym]
            # REPLAY IN THE PARENT. One process owns the ledger, so the
            # trial count that sets the bar is still written in exactly
            # one place -- the property that made the thread pool safe
            # is preserved without the thread pool.
            PAR.replay(led, mem, out, arch=ARCH["a"])
            for k, v in (out.get("libs") or {}).items():
                lib = libs.setdefault(k, FeatureLibrary(keep=20))
                lib.kept.update(v.get("kept") or {})
                lib.scores.update(v.get("scores") or {})
            for fam, pts in (out.get("points") or {}).items():
                points.setdefault(fam, []).extend(pts)
            for fam, rows in (out.get("mrows") or {}).items():
                mrows.setdefault(fam, []).extend(rows)
            if SLATE.get("book") is not None:
                _merge_book(SLATE["book"], out.get("book") or {})
            # A slate-only shard has no private hypotheses, no candidates
            # and no features -- its whole contribution is the book rows
            # merged just above. Running the gauntlet and logging a
            # per-market line for it would report the same market three
            # times with nothing new in two of them.
            if (out.get("shard") or (0, 1))[0] > 0:
                continue
            # NOT counted here any more: the worker already ticked the
            # shared counter as it went, so adding out["done"] on return
            # would count every hypothesis twice.
            LIVE["market"] = sym
            LIVE["tier"] = 1
            # Candidates crossed the boundary without their tapes, which
            # do not pickle sanely; the parent re-derives them.
            cands = _rehydrate(out.get("candidates") or [], data.get(sym),
                               sym=sym)
            gauntlet(sym, 1, cands, led, mem, libs, tv, cost)
            say("cycle_market", cycle=cycle, market=sym, tier=1,
                tested=out.get("done"), features=len(out.get("kept") or []),
                trials=led.d["trials"], bar=round(led.bar(), 2))
        stage("saving the ledger")
        led.save()
        mem.save()
        gc.collect()

        # ---- JUDGE THE SLATE, once, on all the evidence at once.
        #
        # This is the step the searcher never had. Every market has now
        # answered the same questions; here those answers are combined
        # into one verdict per mechanism, with correlated markets
        # discounted and disagreement between markets penalised.
        #
        # One mechanism costs ONE trial no matter how many markets
        # measured it, because it is one hypothesis. That is both
        # honest and a large gain: the bar rises far more slowly, and a
        # weak-but-universal effect -- the shape a real edge actually
        # has -- becomes visible for the first time.
        if not os.path.exists(STOP) and SLATE.get("book") is not None:
            stage("combining every market's answer")
            try:
                verdicts = SLATE["book"].test(DT.effective_n)
            except Exception as exc:                          # noqa: BLE001
                verdicts = []
                say("pool_failed", err=str(exc)[:160])
            pooled_cands = []
            for v in verdicts:
                h = dict(v["hyp"])
                h["market"] = "POOLED"
                h["tier"] = 0
                if led.seen(h):
                    continue
                res = {"z": round(v["z"], 3), "gz": round(v["z"], 3),
                       "cu": round(v["mean_cost_units"], 5),
                       "edge": None, "net": None,
                       "n": v["n_total"], "eff_n": int(v["effective_n"]),
                       "mde": v.get("mde"),
                       # so the board can say how often it fires, not
                       # just how many times it ever has
                       "per_week": v.get("per_week"),
                       "per_week_per_market": v.get("per_week_per_market"),
                       "markets": v["markets"], "k": v["k"],
                       "agree": v["agree"], "tau2": round(v["tau2"], 6),
                       "per_market": v["per_market"], "pooled": True}
                led.record(h, res, family=v.get("family"))
                bar = led.bar()
                # A pooled mechanism must clear the bar, pay for itself
                # and point the same way nearly everywhere. The last of
                # those is what a single loud market can never satisfy.
                if (v["z"] >= bar and v["mean_cost_units"] > 0
                        and v["agree"] >= PO.MIN_AGREE):
                    pooled_cands.append((h, v, res, bar))
            say("pool_judged", cycle=cycle, mechanisms=len(verdicts),
                candidates=len(pooled_cands),
                best_z=round(verdicts[0]["z"], 2) if verdicts else None,
                bar=round(led.bar(), 2))
            for h, v, res, bar in pooled_cands[:6]:
                say("POOLED_CANDIDATE", z=round(v["z"], 2), bar=round(bar, 2),
                    markets=v["k"], agree=v["agree"],
                    cost_units=round(v["mean_cost_units"], 3),
                    what=HY.describe(h))
                mem.adapt("pooled", v.get("family") or "mechanism",
                          before="untested across markets",
                          after=f"{v['z']:.2f}σ pooled over {v['k']} markets",
                          why=(f"agreed in sign in {v['agree']:.0%} of them "
                               f"and paid {v['mean_cost_units']:.2f} round "
                               f"trips per trade on average"))
            SLATE["book"] = None
            # FORCED. The pooled verdict is the most valuable output of
            # a cycle -- one hypothesis carrying every market's evidence
            # -- and a throttled save silently dropped all 113 of them
            # on the first integration run.
            led.save(force=True)

        # ---- tier 2: NQ tick, one contract per cycle, 60-second bars.
        # This is where "merge the deep data" actually happens. It runs
        # after the breadth sweep because it is ~40x the compute, and
        # one contract at a time because 4.7 GB of tick data will not
        # fit alongside anything else on a box with no swap.
        if not os.path.exists(STOP):
            res_probe = T2_RES[0] if T2_RES else None
            cs = DT.tier2_sources(res_probe) if res_probe else []
            if not cs:
                # LOUD. A tier that is absent looks identical to a tier
                # that found nothing, and the second is a result while
                # the first is a broken deployment. data/tick/ is
                # gitignored (4.7 GB), so on any deploy target this
                # means build_deep_bars.py was never run or its output
                # was never committed.
                say("TIER2_MISSING", searched=DT.BARS,
                    why="no deep-tier bars and no raw tick data. The "
                        "searcher is running on tier 1 and tier 3 only "
                        "-- a third of its data is absent. Run "
                        "researcher/build_deep_bars.py where the raw "
                        "ticks live and commit data/research_bars/.")
            if cs:
                # ROTATE RESOLUTION, SWEEP EVERY CONTRACT. Resolution is
                # a genuine second axis: the same question asked of
                # 15-second bars and of 5-minute bars is two different
                # questions, because the move size that has to clear a
                # fixed cost differs by sqrt(20). It is not the same test
                # repeated.
                #
                # Contract, though, was ALSO being rotated -- one of
                # eight per cycle -- and that was a memory decision made
                # for the raw path, where a 25M-row parquet peaks near
                # 2 GB. The precomputed bars are not that: a whole
                # contract at 15s is 95,137 rows and 5.3 MB in memory,
                # and all eight at once is 42 MB. Rotating them was
                # throwing away seven eighths of the deepest data in the
                # system to save nothing, and the deep tier is precisely
                # where the statistical power is -- 95k bars against
                # tier 1's few thousand. All eight now sweep together,
                # in the pool, on the cores that were idle.
                #
                # The raw fallback keeps the old one-at-a-time behaviour,
                # because there the 2 GB peak is real.
                res = T2_RES[(cycle - 1) % len(T2_RES)]
                srcs = DT.tier2_sources(res) or cs
                pre = [s for s in srcs if s[1] == "pre"]
                if not pre:
                    pre = [srcs[(cycle - 1) % len(srcs)]]
                deep = {}
                for name, kind, p in pre:
                    cn = f"NQ@{name}@{res}s"
                    try:
                        a = DT.tier2_from(kind, p, res)
                    except Exception as exc:                  # noqa: BLE001
                        say("tier2_load_failed", contract=cn,
                            err=str(exc)[:150])
                        continue
                    if a is not None and len(a) > 5000:
                        deep[cn] = a
                if deep:
                    _sweep_deep(deep, res, cycle, led, mem, libs,
                                points, mrows)
                    del deep
                led.save()
                mem.save()
                gc.collect()

        # ---- tier 3: NQ top-of-book. Queue depletion, add rates,
        # spread and trade flow exist at no other tier and cannot be
        # reconstructed from trades, so these hypotheses ENTER here
        # rather than being screened first -- and pay the higher bar of
        # one market and four weeks.
        if not os.path.exists(STOP) and cycle % 2 == 1:
            res3 = (T3_RES[((cycle - 1) // 2) % len(T3_RES)]
                    if T3_RES else None)
            try:
                b = DT.tier3(bar_s=res3) if res3 else None
            except Exception as exc:                          # noqa: BLE001
                b = None
                say("tier3_load_failed", err=str(exc)[:150])
            if b is not None and len(b) > 5000:
                tv, cost = SPEC["NQ"]
                out, err = sweep(f"NQbook@{res3}s", b, led, mem, libs, 3,
                                 tv, cost,
                                 budget=400,
                                 base_cols=["close", "vol", "n", "absret",
                                            "imb", "spread", "qrate",
                                            "depl", "adds", "tflow"],
                                 points=points, mrows=mrows)
                if err:
                    say("tier3_selftest_failed", why=err)
                else:
                    done, cands, kept = out
                    gauntlet(f"NQbook@{res3}s", 3, cands, led, mem, libs,
                             tv, cost)
                    say("cycle_market", cycle=cycle,
                        market=f"NQbook@{res3}s",
                        tier=3, tested=done, features=len(kept),
                        bars=len(b), trials=led.d["trials"],
                        bar=round(led.bar(), 2))
                del b
            led.save()
            mem.save()
            gc.collect()

        # ---- BACKFILL. The leaderboard reports trades/week, win rate
        # and RR, which older ledger entries predate. The ledger never
        # retests by design, so without this the best entries would show
        # blanks permanently -- the top row is the top row precisely
        # because nothing has beaten it. Re-scoring is NOT a new trial:
        # the hypothesis is already counted, and this only fills in
        # fields on the stored result.
        # WHAT CAN THIS SEARCHER ACTUALLY SEE? Measured, periodically,
        # by planting edges of known size in a real tape and counting how
        # often they come back. Without it "240,000 tested, nothing
        # found" is uninterpretable -- at 5% power it means almost
        # nothing, at 90% it is a strong and expensive result. Run every
        # few cycles because it costs real time and the answer moves only
        # as the bar moves.
        if cycle % int(os.environ.get("RESEARCH_CAL_EVERY", "6")) == 1:
            try:
                stage("measuring its own power and false-alarm rate")
                symc = "NQ" if "NQ" in data else sorted(data)[0]
                tvc, cc = SPEC[symc]
                srchc, _vc = split(data[symc])
                rep = CAL.report(srchc, tvc, cc, bars_per(data[symc]),
                                 led.bar(), verbose=False)
                rep["detectable_at_80pct"] = CAL.detectable_size(
                    rep.get("power") or {})
                rep["market"] = symc
                rep["t"] = now()
                json.dump(rep, open(os.path.join(RDIR, "calibration.json"),
                                    "w"), indent=1)
                say("CALIBRATED", market=symc,
                    detectable_at_80pct=rep["detectable_at_80pct"],
                    false_alarm_rate=(rep.get("false_alarms") or {}).get(
                        "rate"),
                    bar=round(led.bar(), 2),
                    note="power is what makes 'nothing found' mean "
                         "something -- below the detectable size, silence "
                         "is not evidence of absence")
            except Exception as exc:                          # noqa: BLE001
                say("calibration_failed", err=str(exc)[:200])

        stage("re-checking older results against current controls")
        try:
            filled = backfill_metrics(led, data)
            if filled:
                say("backfilled_metrics", rows=filled)
        except Exception as exc:                              # noqa: BLE001
            say("backfill_failed", err=str(exc)[:160])

        # ---- INFER. Everything above measured; this deduces.
        # edges are already normalised to each market's own cost, so
        # break-even is the ratio 1.0 for every family alike
        ins = IN.build(points, {f: 1.0 for f in points}, mrows, vols, SPEC)
        mem.set_insights(ins)
        for fam, hz in (ins.get("horizons") or {}).items():
            if hz.get("fits") and hz.get("reachable"):
                # This is the inference CHANGING the search: the next
                # cycle will test this family at the deduced horizon,
                # which nobody put in the list.
                mem.adapt("horizon", fam,
                          before=f"{HY.HOLDS_S if not fam.startswith('flow/') else HY.FLOW_HOLDS_S}s",
                          after=f"+{hz['h_star']}s (deduced)",
                          why=hz["why"])
            elif hz.get("fits"):
                # hz["why"] already explains why it is out of reach --
                # appending a second sentence saying the same thing
                # produced the doubled paragraph on the console.
                mem.adapt("closed", fam, before="searching",
                          after=f"crossing at {IN._dur(hz['h_star'])}",
                          why=hz["why"])
        hz_all = ins.get("horizons") or {}
        sysodd = PL.check_system(
            families_total=len(hz_all),
            families_fitting=sum(1 for h in hz_all.values()
                                 if h.get("fits")),
            survivors=len(led.d.get("survivors", [])),
            candidates=None)
        if sysodd:
            say("SYSTEM_IMPLAUSIBLE",
                flags=[{"observed": a, "means": b, "look_at": c}
                       for a, b, c in sysodd])

        say("inferred", horizons=len(hz_all),
            reachable=sum(1 for h in (ins.get("horizons") or {}).values()
                          if h.get("fits") and h.get("reachable")),
            frontier_best=[r["market"] for r in ins.get("frontier", [])[:5]])
        mem.save()

        history_point(secs=round(time.time() - t0))

        # ---- QUESTIONS SOMEBODY WROTE DOWN. Run after the sweep so a
        # slow experiment can never delay the search, time-boxed, and
        # every exception is caught inside run_all. Their measurements
        # are charged like any other look: reading the data is reading
        # the data, and a free look would be a hole in the bar.
        try:
            xp = os.path.join(RDIR, "experiments.json")
            store = _read_json(xp, {}) or {}
            out = EXP.run_all({"data": data, "spec": SPEC,
                               "bar": led.bar(), "cycle": cycle},
                              store, say=say)
            if out.get("measurements"):
                led.bump(int(out["measurements"]))
            json.dump(store, open(xp, "w"), separators=(",", ":"),
                      default=str)
        except Exception as exc:                              # noqa: BLE001
            say("experiments_failed", err=str(exc)[:200])

        led.save(force=True)
        _save_libs(libs)
        # WRITE THE BRIEF. The searcher grinds; this is the handoff --
        # what its coverage actually rules out, what it could not see,
        # what it could not even ask, what cannot be true, and the one
        # constraint currently binding. Cheap, and it never fails the
        # cycle: a brief that throws is a lost report, not a lost sweep.
        try:
            b = BRIEF.build(led.d, mem.d, arch=(ARCH["a"].dump()
                                                if ARCH["a"] else None),
                            cal=_read_json(os.path.join(RDIR,
                                                        "calibration.json")),
                            experiments=_read_json(
                                os.path.join(RDIR, "experiments.json")))
            json.dump(b, open(os.path.join(RDIR, "brief.json"), "w"),
                      separators=(",", ":"))
            open(os.path.join(RDIR, "brief.md"), "w").write(BRIEF.render(b))
            bc = b["binding_constraint"]
            say("BRIEF", constraint=bc["constraint"], says=bc["says"],
                do=bc["do"], blind_share=b["coverage"].get("blind_share"),
                unreachable=len(b["unreachable"]),
                contradictions=len(b["contradictions"]))
        except Exception as exc:                              # noqa: BLE001
            say("brief_failed", err=str(exc)[:200])
        try:
            if ARCH["a"] is not None:
                ARCH["a"].save(os.path.join(RDIR, "archive.json"))
        except Exception as exc:                              # noqa: BLE001
            say("archive_save_failed", err=str(exc)[:120])
        json.dump({"t": now(), "cycle": cycle, "summary": led.summary(),
                   "learning": mem.summary(), "insight": ins},
                  open(STATUS, "w"), indent=1)
        say("cycle_done", cycle=cycle, secs=round(time.time() - t0),
            **led.summary())
        say("lessons", **mem.summary())
        if once:
            break
        time.sleep(int(os.environ.get("RESEARCH_SLEEP", "30")))
    led.save(force=True)
    mem.save()
    _save_libs(libs)
    say("exit", **led.summary())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        say("interrupted")
    except Exception:                                         # noqa: BLE001
        say("crash", tb=traceback.format_exc()[-1500:])
        raise
