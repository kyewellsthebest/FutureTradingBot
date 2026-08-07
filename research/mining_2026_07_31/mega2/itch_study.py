"""Rebuild a real order book from NASDAQ ITCH 5.0 and ask whether it predicts.

The prerequisite question, answered with free data before anyone pays for CME.

Order book imbalance -- resting size at the bid against resting size at the ask
-- is the most documented short-horizon predictor in the microstructure
literature. It is also completely invisible in trade prints, which is why
sixteen families measured on trades came back null and why Databento's MBO
costs what it does. This is equities, so it cannot produce a futures strategy.
What it can do, for nothing, is tell us whether level-3 data carries an edge at
all. If imbalance does not predict here, no amount of CME MBO would have helped.

Parsed by hand rather than through a library, for the same reason dukas.py is:
the format is small and documented, and a dependency that fails at 2am on a
runner costs more than forty lines of struct.unpack_from. NASDAQ's sample files
are a stream of [2-byte big-endian length][message]. After the common 11-byte
header (type, stock_locate, tracking, 6-byte timestamp) the fields we need are
at fixed offsets:

  R  stock directory  -> locate to ticker, so we can track only liquid names
  A  add order        -> ref@11 side@19 shares@20 stock@24 price@32   (36 B)
  F  add w/ attribution, identical through price                      (40 B)
  E  executed         -> ref@11 shares@19                             (31 B)
  C  executed w/price -> ref@11 shares@19                             (36 B)
  X  cancel           -> ref@11 shares@19                             (23 B)
  D  delete           -> ref@11                                       (19 B)
  U  replace          -> old@11 new@19 shares@27 price@31             (35 B)

U is the one the first version of this file ignored. Replaces are a large
fraction of all messages on NASDAQ; dropping them leaves phantom size resting
in the book forever and every imbalance computed off it is fiction.

Measured the way everything else in this project is measured: an information
coefficient against forward returns, a SHUFFLED control so we can see what the
pipeline invents from nothing, a train/holdout split, and the answer converted
into basis points against the spread -- because an IC only matters against what
crossing actually costs.
"""
import glob
import gzip
import os
import struct
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("M2_REPO", os.getcwd())
# the sample is several GB, so on a runner it lives on the big volume, not in
# the checkout -- ITCH_DIR points wherever there is room
ITCH = os.environ.get("ITCH_DIR") or os.path.join(ROOT, "data", "itch")
OUT = os.path.join(ROOT, "research", "ITCH_RESULT.md")
MAXMSG = int(os.environ.get("MAXMSG", "40000000"))
SNAP_EVERY = int(os.environ.get("SNAP_EVERY", "1500"))
# how many snapshots before the measurement is worth making at all
MINSNAP = int(os.environ.get("MINSNAP", "5000"))

# a fixed liquid set, so we track a few thousand orders instead of millions
WANT = set(os.environ.get("SYMS", "AAPL MSFT AMZN TSLA NVDA META GOOGL "
                                  "INTC AMD QQQ SPY BAC").split())

LINES = []


def log(s=""):
    print(s, flush=True)
    LINES.append(s)


def write_and_exit(code=0):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write("\n".join(LINES) + "\n")
    print("\nwrote", OUT, flush=True)
    sys.exit(code)


files = sorted(glob.glob(os.path.join(ITCH, "*.gz")))
if not files:
    log("# ITCH order book study")
    log()
    log("No sample file was downloaded. See the workflow log for what the "
        "NASDAQ directory returned.")
    write_and_exit(0)

src = files[0]
log("# ITCH order book study")
log()
log(f"Source: `{os.path.basename(src)}` ({os.path.getsize(src)/1e9:.2f} GB "
    f"compressed), first {MAXMSG:,} messages.")
log()

# ---------------------------------------------------------------------------
# Parse. An order id is unique for its lifetime, so ref -> [locate, side,
# price, shares] plus locate -> {price: [bid_size, ask_size]} is the whole book.
# ---------------------------------------------------------------------------
u2 = struct.Struct(">H").unpack_from
u4 = struct.Struct(">I").unpack_from
u8 = struct.Struct(">Q").unpack_from

orders = {}          # ref -> [locate, is_bid, price_int, shares]
book = {}            # locate -> {price_int: [bid, ask]}
loc2sym = {}
tracked = set()      # stock_locate values we care about
rows = []
counts = {}
nmsg = 0
buf = b""

with gzip.open(src, "rb") as fh:
    while nmsg < MAXMSG:
        chunk = fh.read(1 << 24)
        if not chunk:
            break
        buf += chunk
        pos, n = 0, len(buf)
        while nmsg < MAXMSG:
            if n - pos < 2:
                break
            ln = u2(buf, pos)[0]
            if n - pos < 2 + ln:
                break
            m = buf[pos + 2: pos + 2 + ln]
            pos += 2 + ln
            nmsg += 1
            t = m[0:1]
            counts[t] = counts.get(t, 0) + 1

            if t == b"R":
                sym = m[11:19].decode("ascii", "ignore").strip()
                loc = u2(m, 1)[0]
                loc2sym[loc] = sym
                if sym in WANT:
                    tracked.add(loc)
                continue

            if t == b"A" or t == b"F":
                loc = u2(m, 1)[0]
                if loc not in tracked:
                    continue
                ref = u8(m, 11)[0]
                isb = m[19:20] == b"B"
                sh = u4(m, 20)[0]
                px = u4(m, 32)[0]
                orders[ref] = [loc, isb, px, sh]
                lv = book.setdefault(loc, {}).setdefault(px, [0, 0])
                lv[0 if isb else 1] += sh

            elif t == b"E" or t == b"C" or t == b"X":
                ref = u8(m, 11)[0]
                o = orders.get(ref)
                if o is None:
                    continue
                k = min(u4(m, 19)[0], o[3])
                o[3] -= k
                lv = book.get(o[0], {}).get(o[2])
                if lv:
                    lv[0 if o[1] else 1] -= k
                if o[3] <= 0:
                    del orders[ref]

            elif t == b"D":
                o = orders.pop(u8(m, 11)[0], None)
                if o is None:
                    continue
                lv = book.get(o[0], {}).get(o[2])
                if lv:
                    lv[0 if o[1] else 1] -= o[3]

            elif t == b"U":
                # replace: the old id dies entirely, a new one takes its place
                # at a new price and size. Skipping this leaves phantom size.
                o = orders.pop(u8(m, 11)[0], None)
                if o is None:
                    continue
                lv = book.get(o[0], {}).get(o[2])
                if lv:
                    lv[0 if o[1] else 1] -= o[3]
                nref = u8(m, 19)[0]
                nsh = u4(m, 27)[0]
                npx = u4(m, 31)[0]
                orders[nref] = [o[0], o[1], npx, nsh]
                lv = book.setdefault(o[0], {}).setdefault(npx, [0, 0])
                lv[0 if o[1] else 1] += nsh

            if nmsg % SNAP_EVERY == 0:
                # the 6-byte header timestamp is nanoseconds since midnight ET.
                # Decoding it on every message would cost more than the parse;
                # at snapshot time it is 40,000 calls instead of 60 million.
                tns = int.from_bytes(m[5:11], "big")
                for loc, lv in book.items():
                    bb = bp = 0
                    aa = 0
                    ap = 1 << 62
                    for p, s in lv.items():
                        if s[0] > 0 and p > bp:
                            bp, bb = p, s[0]
                        if s[1] > 0 and p < ap:
                            ap, aa = p, s[1]
                    if bp == 0 or ap == 1 << 62 or ap <= bp:
                        continue
                    if ap - bp > bp * 0.02:      # a two percent spread is junk
                        continue
                    rows.append((nmsg, tns, loc, bp, bb, ap, aa))
        buf = buf[pos:]

log(f"Parsed **{nmsg:,} messages**, {len(rows):,} book snapshots across "
    f"{len(tracked)} tracked symbols ({len(loc2sym):,} listed).")
log()
log("Message mix: " + ", ".join(
    f"`{k.decode()}`={v:,}" for k, v in
    sorted(counts.items(), key=lambda x: -x[1])[:8]))
log()

if len(rows) < MINSNAP:
    log("**Too few snapshots to measure anything.** The book never populated, "
        "which means the parse is wrong rather than the market being quiet.")
    write_and_exit(0)

d = pd.DataFrame(rows, columns=["seq", "tns", "loc", "bid", "bsz", "ask", "asz"])
d["sym"] = d["loc"].map(loc2sym)

# REGULAR HOURS ONLY. Pre-market books are thin and their spreads are several
# times the RTH spread, so measuring the signal across the whole session and
# then pricing it against a session-wide median spread compares a number earned
# mostly in the open auction against a cost paid mostly at 4am.
RTH = (d.tns >= 34_200_000_000_000) & (d.tns < 57_600_000_000_000)
_sp = (d.ask - d.bid) / ((d.ask + d.bid) / 2) * 10000
_in = _sp[RTH].median() if RTH.any() else float("nan")
_out = _sp[~RTH].median() if (~RTH).any() else float("nan")
log(f"Session: {RTH.mean()*100:.0f}% of snapshots fall in 09:30-16:00 ET. "
    f"Median spread {_in:.1f} bps in hours against {_out:.1f} bps outside.")
log()
if RTH.sum() >= MINSNAP:
    d = d[RTH].copy()
    log(f"Keeping the {len(d):,} in-hours snapshots and discarding the rest.")
    log()
d = d.sort_values(["sym", "seq"], kind="stable").reset_index(drop=True)
d["mid"] = (d.bid + d.ask) / 2.0                      # still in 1e-4 dollars
d["spread_bps"] = (d.ask - d.bid) / d.mid * 10000
d["imb"] = (d.bsz - d.asz) / (d.bsz + d.asz)

# TWO controls, because one is not enough. A plain shuffle destroys the
# autocorrelation of imbalance along with its information, so a feature that
# scores only because it is slow-moving still beats it. A circular shift keeps
# the series exactly as persistent as it really is and only breaks its
# alignment with the future -- that is the control that has to be beaten.
rng = np.random.default_rng(11)
d["shuffled"] = rng.permutation(d.imb.values)
d["shifted"] = d.groupby("sym", group_keys=False)["imb"].apply(
    lambda x: pd.Series(np.roll(x.values, max(1, len(x) // 3)), index=x.index))

log(f"Symbols: {', '.join(sorted(d.sym.dropna().unique()))}")
log()
log(f"Median spread **{d.spread_bps.median():.1f} bps**, median top of book "
    f"{d.bsz.median():.0f} x {d.asz.median():.0f} shares, "
    f"{len(d):,} snapshots.")
log()


def ic(x, y):
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 500:
        return np.nan
    a = pd.Series(x[m]).rank().values
    b = pd.Series(y[m]).rank().values
    a = a - a.mean()
    b = b - b.mean()
    den = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / den) if den > 0 else np.nan


log("## Does book imbalance predict the next move?")
log()
ctrl = {}
log("| horizon | feature | train IC | holdout IC | sign held |")
log("|---|---|---|---|---|")
best = (None, 0.0, 0.0)
# split on the SEQUENCE, not on position in a symbol-sorted frame. The frame is
# sorted by symbol so that forward returns never step across a symbol boundary;
# slicing it positionally would put whole symbols in the holdout and call that
# a time split.
seqcut = d.seq.quantile(0.7)
early = (d.seq < seqcut).values
late = ~early
for h in (1, 5, 20, 50):
    fwd = d.groupby("sym", group_keys=False)["mid"].apply(
        lambda x: (x.shift(-h) / x - 1.0) * 10000).values
    for col in ("imb", "shuffled", "shifted"):
        it = ic(d[col].values[early], fwd[early])
        ih = ic(d[col].values[late], fwd[late])
        held = ("yes" if np.isfinite(it) and np.isfinite(ih)
                and np.sign(it) == np.sign(ih) else "no")
        log(f"| {h} snapshots | {col} | {it:+.4f} | {ih:+.4f} | {held} |")
        ctrl[(h, col)] = ih
        if col == "imb" and np.isfinite(ih) and abs(ih) > abs(best[1]):
            # NOT the median absolute move. Between consecutive snapshots the
            # mid usually does not move at all, so the median is exactly zero
            # and IC x 0 prices a real signal at nothing -- which is what the
            # first version of this file reported. The standard deviation is
            # the scale an IC is defined against.
            best = (h, ih, float(np.nanstd(fwd)), float(np.nanmean(np.abs(fwd))),
                    float(np.nanmean(fwd != 0)))
log()

# The IC-times-sigma conversion assumes a linear relationship. This does not
# assume anything: sort the holdout snapshots by imbalance, take the extreme
# deciles, and read off what actually happened next. If the top decile does not
# out-earn the bottom by more than the spread, there is no trade here whatever
# the IC says.
log("## What actually happened next, by imbalance decile (holdout only)")
log()
H = d[late].copy()
hbest = best[0] or 1
H["fwd"] = d.groupby("sym", group_keys=False)["mid"].apply(
    lambda x: (x.shift(-hbest) / x - 1.0) * 10000).values[late]
H = H[np.isfinite(H.fwd)]
try:
    H["dec"] = pd.qcut(H.imb, 10, labels=False, duplicates="drop")
    g = H.groupby("dec").fwd.agg(["mean", "count", "std"])
    log(f"| decile | mean forward move ({hbest} snaps) | n | +/- |")
    log("|---|---|---|---|")
    for i, r in g.iterrows():
        log(f"| {int(i)} | {r['mean']:+.3f} bps | {int(r['count']):,} | "
            f"{r['std']/np.sqrt(r['count']):.3f} |")
    lo_, hi_ = g.iloc[0], g.iloc[-1]
    spread_dec = hi_["mean"] - lo_["mean"]
    dse = np.sqrt(lo_["std"] ** 2 / lo_["count"] + hi_["std"] ** 2 / hi_["count"])
    log()
    log(f"**Top decile minus bottom: {spread_dec:+.3f} bps "
        f"+/- {dse:.3f} ({abs(spread_dec)/max(dse,1e-9):.1f} sigma).** "
        f"Acting on one side of that captures about half of it, "
        f"{spread_dec/2:+.3f} bps, against a half-spread of "
        f"{float(d.spread_bps.median())/2:.2f} bps to cross.")
except Exception as e:
    log(f"decile table unavailable: {type(e).__name__}: {e}")
log()

if best[0]:
    h, icv, sd, ma, nz = best
    # what the feature is worth is what it beats its own control by, not its
    # raw value -- the circular shift is as persistent as imbalance is and
    # carries no information, so anything it scores is the pipeline talking
    sh = ctrl.get((h, "shifted"), np.nan)
    edge = abs(icv) - (abs(sh) if np.isfinite(sh) else 0.0)
    worth = max(edge, 0.0) * sd
    sp = float(d.spread_bps.median())
    log(f"**Best: imbalance {icv:+.4f} at {h} snapshots ahead, against a "
        f"time-shifted control of {sh:+.4f}.**")
    log()
    log(f"- forward move over that horizon: sigma {sd:.2f} bps, mean absolute "
        f"{ma:.2f} bps, and the mid moves at all only {nz*100:.0f}% of the time")
    log(f"- raw, before the control: {abs(icv)*sd:.2f} bps a trade")
    log(f"- **net of the control: {worth:.2f} bps a trade**")
    log(f"- crossing the spread costs **{sp:.1f} bps**, so a taker needs "
        f"{sp/max(worth,1e-9):.1f}x this to break even")
    log(f"- a maker who never crosses pays no spread, and for them the bar is "
        f"queue position and adverse selection, not {sp:.1f} bps")
    log(f"- **verdict as a TAKER: "
        f"{'clears the spread' if worth > sp else 'does NOT clear the spread'}**")
else:
    log("**No finite holdout IC at any horizon.** Nothing was measured; do not "
        "read the train column as a result.")
log()
log("Two controls, both of which imbalance has to beat -- not zero. `shuffled` "
    "is a plain permutation; `shifted` is the same series rolled forward inside "
    "each symbol, so it keeps imbalance's persistence and loses only its "
    "alignment with the future. The second is the harder bar and the honest one.")
write_and_exit(0)
