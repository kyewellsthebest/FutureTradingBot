"""FOOTPRINT SCANNER -- a different search space, not a different search.

Everything this project has done searches PRICE for PATTERNS. That space
is effectively infinite, almost entirely noise, and the few real things
in it are published and therefore decayed. Variations on a decayed edge
are still decayed.

This searches MARKET STRUCTURE for CONSTRAINTS instead, and it inverts
the direction of the search:

    old:  find a price pattern -> invent a story for it -> validate
    new:  find a FOOTPRINT of forced flow -> identify the mandate ->
          derive the price prediction -> validate

The inversion is the whole point. Someone obliged to move 5,000 lots at
a fixed time leaves marks whether or not the price move is predictable:
a volume signature, a spread signature, a volatility signature, an
autocorrelation signature. Those marks are RARE and every one has a
cause. Price patterns are infinite and most have none.

It also fixes multiple testing structurally. This scans a few hundred
time buckets, not a billion parameter combinations, and a hit arrives
with a mechanism attached rather than needing one invented for it.

WHAT IS SCANNED, and each is a place a mandate would show up:

    minute of day     settlement windows, auction mechanics, release
                      times, the close. Forced flow has a clock.
    day of month      month-end rebalancing, ETF roll schedules,
                      options expiry, futures roll.
    day of week       weekly option expiry, auction calendars.
    days to expiry    the roll itself -- the single largest recurring
                      forced flow in futures.

WHAT IS MEASURED in each bucket -- deliberately NOT returns:

    volume            somebody had to trade
    trade count       many participants or one large one
    realized vol      the flow moved price
    |autocorrelation| flow arriving in pieces leaves serial correlation

Returns are excluded on purpose. A return anomaly is a strategy looking
for a story. A VOLUME anomaly with no known cause is a footprint, and
the story comes after.

READING IT: the open, the close, and 08:30 ET releases will dominate and
must be ignored -- they are known and crowded. The output worth anything
is a bucket that is anomalous and has NO obvious explanation. That is
where a mandate nobody has priced is hiding.

Output: research/FOOTPRINT_SCAN.md
"""
import gc
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402

OUT = os.path.join(fuse.ROOT, "research", "FOOTPRINT_SCAN.md")
Z = 3.0
L = []

KNOWN = {
    (13, 30): "US cash open", (13, 25): "pre-open auction",
    (12, 30): "US econ releases 08:30 ET",
    (14, 0): "10:00 ET releases", (18, 0): "FOMC / 14:00 ET",
    (19, 50): "MOC imbalance published", (20, 0): "US cash close",
    (21, 0): "CME halt", (22, 0): "CME reopen",
    (7, 0): "London open", (6, 0): "Europe pre-open",
    (15, 0): "11:00 ET", (19, 0): "15:00 ET",
}


def log(s=""):
    print(s, flush=True)
    L.append(s)


def flag(series, label, unit, explain=None):
    """Report buckets more than Z robust-sigmas from the local median."""
    v = series.values.astype(float)
    med = np.nanmedian(v)
    mad = np.nanmedian(np.abs(v - med)) * 1.4826
    if not np.isfinite(mad) or mad <= 0:
        return []
    z = (v - med) / mad
    hits = []
    for i, zz in enumerate(z):
        if abs(zz) >= Z:
            key = series.index[i]
            note = (explain or {}).get(key, "")
            hits.append((abs(zz), key, v[i], zz, note))
    hits.sort(reverse=True)
    return hits


def main():
    meta = fuse.tape_meta()
    cons = [c for c in fuse.NQ_CONTRACTS if c in meta]
    frames = []
    for cn in cons[:4]:
        ts, px, sz = fuse.load_tape(meta[cn]["path"])
        o_ = np.argsort(ts, kind="stable")
        ts, px, sz = ts[o_], px[o_], sz[o_]
        idx = pd.to_datetime(ts)
        g = pd.Series(px, index=idx).resample("1min")
        b = pd.DataFrame({
            "close": g.last(), "n": g.count(),
            "vol": pd.Series(sz, index=idx).resample("1min").sum(),
            "hi": g.max(), "lo": g.min()})
        b = b.dropna(subset=["close"])
        b["ret"] = b["close"].diff()
        frames.append(b)
        del ts, px, sz, idx, g
        gc.collect()
        print(f"{cn} done", flush=True)
    B = pd.concat(frames)
    del frames
    gc.collect()
    B["hm"] = list(zip(B.index.hour, B.index.minute))
    B["dom"] = B.index.day
    B["dow"] = B.index.dayofweek
    B["absret"] = B["ret"].abs()

    log("# Footprint scan -- searching structure, not price")
    log()
    log("Every search in this project so far looked for PRICE PATTERNS. "
        "That space is infinite, almost all noise, and its few real "
        "inhabitants are published and therefore decayed. Variations on "
        "a decayed edge are still decayed.")
    log()
    log("This searches for **footprints of forced flow** instead, and "
        "inverts the direction:")
    log()
    log("    old:  find a price pattern -> invent a story -> validate")
    log("    new:  find a FOOTPRINT -> identify the mandate -> derive "
        "the prediction -> validate")
    log()
    log("Someone obliged to move 5,000 lots at a fixed time leaves marks "
        "whether or not the price move is predictable: volume, spread, "
        "volatility, serial correlation. Those marks are **rare and each "
        "has a cause**. Price patterns are infinite and most have none.")
    log()
    log("**Returns are deliberately not scanned.** A return anomaly is a "
        "strategy hunting for a story. A VOLUME anomaly with no known "
        "cause is a footprint, and the story comes afterwards.")
    log()
    log(f"NQ, {len(cons[:4])} quarters, {len(B):,} minute bars. A bucket "
        f"is flagged at {Z} robust sigmas (median absolute deviation) "
        f"from the median of its own dimension.")
    log()

    for dim, col, unit in (("hm", "vol", "contracts/min"),
                           ("hm", "n", "prints/min"),
                           ("hm", "absret", "pts/min"),
                           ("dom", "vol", "contracts/min"),
                           ("dow", "vol", "contracts/min")):
        s = B.groupby(dim)[col].median()
        hits = flag(s, dim, unit, KNOWN if dim == "hm" else None)
        dname = {"hm": "minute of day (UTC)", "dom": "day of month",
                 "dow": "day of week"}[dim]
        log(f"## {col} by {dname}")
        log()
        if not hits:
            log("_nothing beyond the threshold._")
            log()
            continue
        log("| bucket | value | z | known cause? |")
        log("|---|---|---|---|")
        for zz, key, val, z, note in hits[:12]:
            kt = (f"{key[0]:02d}:{key[1]:02d}" if isinstance(key, tuple)
                  else str(key))
            log(f"| {kt} | {val:,.1f} | {z:+.1f} | "
                f"{note if note else '**UNEXPLAINED**'} |")
        log()

    log("## How to use this")
    log()
    log("Ignore every row with a known cause. The open, the close, the "
        "08:30 releases and the CME halt will dominate and they are the "
        "most crowded moments of the day -- there is no edge in being "
        "the ten-thousandth person to notice the open is busy.")
    log()
    log("**The rows marked UNEXPLAINED are the output.** Each one is a "
        "place where somebody is trading who did not have to choose to, "
        "and we do not yet know who. For each: identify the mandate, "
        "derive what it forces them to do, predict the price consequence "
        "-- and only then run it through the gauntlet.")
    log()
    log("A footprint with no mechanism is not a strategy. But unlike a "
        "price pattern, it is a question with an answer, and the answer "
        "is findable in exchange rules and fund mandates rather than in "
        "more data.")
    log()
    open(OUT, "w").write("\n".join(L) + "\n")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
