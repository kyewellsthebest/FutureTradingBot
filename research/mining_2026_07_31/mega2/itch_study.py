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
                    rows.append((nmsg, loc, bp, bb, ap, aa))
        buf = buf[pos:]

log(f"Parsed **{nmsg:,} messages**, {len(rows):,} book snapshots across "
    f"{len(tracked)} tracked symbols ({len(loc2sym):,} listed).")
log()
log("Message mix: " + ", ".join(
    f"`{k.decode()}`={v:,}" for k, v in
    sorted(counts.items(), key=lambda x: -x[1])[:8]))
log()

if len(rows) < 5000:
    log("**Too few snapshots to measure anything.** The book never populated, "
        "which means the parse is wrong rather than the market being quiet.")
    write_and_exit(0)

d = pd.DataFrame(rows, columns=["seq", "loc", "bid", "bsz", "ask", "asz"])
d["sym"] = d["loc"].map(loc2sym)
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
            best = (h, ih, float(np.nanmedian(np.abs(fwd))))
log()

if best[0]:
    h, icv, mv = best
    # what the feature is worth is what it beats its own control by, not its
    # raw value -- the circular shift is as persistent as imbalance is and
    # carries no information, so anything it scores is the pipeline talking
    sh = ctrl.get((h, "shifted"), np.nan)
    edge = abs(icv) - (abs(sh) if np.isfinite(sh) else 0.0)
    worth = max(edge, 0.0) * mv
    raw = abs(icv) * mv
    sp = float(d.spread_bps.median())
    log(f"**Best: imbalance {icv:+.4f} at {h} snapshots ahead, against a "
        f"time-shifted control of {sh:+.4f}.** A typical move over that horizon "
        f"is {mv:.1f} bps.")
    log()
    log(f"- raw, before the control: {raw:.2f} bps a trade")
    log(f"- **net of the control: {worth:.2f} bps a trade**")
    log(f"- crossing the spread costs **{sp:.1f} bps**, so a taker needs "
        f"{sp/max(worth,1e-9):.1f}x this to break even")
    log(f"- **verdict: "
        f"{'clears the spread -- CME MBO is worth pricing' if worth > sp else 'does NOT clear the spread'}**")
else:
    log("**No finite holdout IC at any horizon.** Nothing was measured; do not "
        "read the train column as a result.")
log()
log("Two controls, both of which imbalance has to beat -- not zero. `shuffled` "
    "is a plain permutation; `shifted` is the same series rolled forward inside "
    "each symbol, so it keeps imbalance's persistence and loses only its "
    "alignment with the future. The second is the harder bar and the honest one.")
write_and_exit(0)
