"""What happens AFTER a resting order fills. The number never measured here.

Every simulation in this project has been about entries. Not one has asked the
market maker's only question: when your passive order gets hit, was that good
luck or was someone taking you out?

The arithmetic that makes it urgent. At the $1,499 tier a round turn costs
$0.72. One MNQ tick is $0.50, so resting on both sides of MNQ loses 22 cents
before anything happens -- market making it is not hard, it is impossible. MES
is a $1.25 tick against the same $0.72, so it has $0.53 of headroom. Whether
that headroom survives is decided entirely by adverse selection, and adverse
selection has never been measured.

NASDAQ ITCH answers it for free, and answers it EXACTLY, because it carries
order IDs. That is the whole reason this is worth doing on equities before
spending anything on CME MBO:

  WITHOUT order IDs (all we have for futures) you can only guess -- "about 40
  contracts were resting ahead of me, has 40 traded yet?" Cancels ahead of you
  are invisible, so the guess is wrong in an unknown direction.

  WITH order IDs you snapshot the exact set of orders ahead of you when you
  join the queue, then watch that specific set drain. An execution against one
  of them moves you up AND is real volume. A cancel moves you up and is not.
  You fill when the set is empty and the next execution arrives. No estimate.

That distinction is the thing kaspar-hft exploits and the thing MBO is sold
for. Here it costs nothing.

What gets measured, per passive order placed at the touch:

  FILL RATE        how often a resting order at the touch actually trades
  ADVERSE SELECTION where the mid went AFTER the fill, in bps, several horizons
  NET              the half-spread you captured, minus where the mid went
  BY IMBALANCE     the same, split by book imbalance at placement -- because
                   imbalance scored a holdout IC of +0.15 on this very data,
                   and the maker's use for a signal is not to predict the move
                   but to decline the fill

If the half-spread does not survive adverse selection on a real level-3 book
with no commission at all, the maker path is closed and no futures data opens
it. If it does survive, the size of what survives says exactly what CME MBO is
worth buying.
"""
import glob
import gzip
import os
import struct
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("M2_REPO", os.getcwd())
ITCH = os.environ.get("ITCH_DIR") or os.path.join(ROOT, "data", "itch")
OUT = os.path.join(ROOT, "research", "MM_ADVERSE_SELECTION.md")
MAXMSG = int(os.environ.get("MAXMSG", "200000000"))
PLACE_EVERY = int(os.environ.get("PLACE_EVERY", "20000"))   # msgs between tries
MAXLIVE = int(os.environ.get("MAXLIVE", "400"))    # concurrent resting orders
GIVEUP = int(os.environ.get("GIVEUP", "2000000"))  # msgs before we cancel
HORIZONS = [int(x) for x in os.environ.get("HORIZONS", "100,1000,10000").split(",")]
WANT = set(os.environ.get("SYMS", "AAPL MSFT AMZN TSLA NVDA META GOOGL "
                                  "INTC AMD QQQ SPY BAC").split())
RTH0, RTH1 = 34_200_000_000_000, 57_600_000_000_000

LINES = []


def log(s=""):
    print(s, flush=True)
    LINES.append(s)


def finish(code=0):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write("\n".join(LINES) + "\n")
    print("\nwrote", OUT, flush=True)
    sys.exit(code)


files = sorted(glob.glob(os.path.join(ITCH, "*.gz")))
log("# What happens after a resting order fills")
log()
if not files:
    log("No ITCH sample was downloaded; nothing measured.")
    finish(0)
src = files[0]
log(f"Source: `{os.path.basename(src)}` ({os.path.getsize(src)/1e9:.2f} GB), "
    f"first {MAXMSG:,} messages, regular hours only.")
log()

u2 = struct.Struct(">H").unpack_from
u4 = struct.Struct(">I").unpack_from
u8 = struct.Struct(">Q").unpack_from

# orders[ref] = [locate, is_bid, price, shares, ARRIVAL SEQ]
# The arrival sequence is what makes "ahead of me" an O(1) question instead of
# a set-membership one: the exchange matches strict FIFO, so an order is ahead
# of my order exactly when it arrived first. No snapshot sets, no scanning.
orders = {}
book = {}                    # locate -> {price: [bid_size, ask_size]}
lvl = {}                     # (locate, price, is_bid) -> set of refs
waiting = {}                 # (locate, price, is_bid) -> list of experiments
sched = {}                   # target message number -> [(experiment, horizon)]
loc2sym, tracked = {}, set()
best = {}
done = []
nlive = 0
nmsg = 0
buf = b""


def refresh_best(loc):
    lv = book.get(loc)
    if not lv:
        return
    bp = bs = 0
    ap, asz = 1 << 62, 0
    for p, s in lv.items():
        if s[0] > 0 and p > bp:
            bp, bs = p, s[0]
        if s[1] > 0 and p < ap:
            ap, asz = p, s[1]
    if bp == 0 or ap == 1 << 62 or ap <= bp or ap - bp > bp * 0.02:
        best.pop(loc, None)
    else:
        best[loc] = (bp, bs, ap, asz)


def try_place(loc):
    """Join the back of the queue at the touch, both sides."""
    global nlive
    b = best.get(loc)
    if b is None:
        return
    bp, bs, ap, asz = b
    for side, px, isb in ((1, bp, True), (-1, ap, False)):
        refs = lvl.get((loc, px, isb))
        if not refs:
            continue
        qsz = 0
        for r in refs:
            o = orders.get(r)
            if o is not None:
                qsz += o[3]
        if qsz <= 0:
            continue
        e = dict(loc=loc, side=side, px=px, isb=isb, qsz=qsz, seq=nmsg,
                 start=nmsg, mid0=(bp + ap) / 2.0, spread=(ap - bp),
                 imb=(bs - asz) / (bs + asz), filled=None, after={})
        waiting.setdefault((loc, px, isb), []).append(e)
        nlive += 1


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

            if t == b"R":
                sym = m[11:19].decode("ascii", "ignore").strip()
                loc = u2(m, 1)[0]
                loc2sym[loc] = sym
                if sym in WANT:
                    tracked.add(loc)
                continue

            touched = None
            if t == b"A" or t == b"F":
                loc = u2(m, 1)[0]
                if loc not in tracked:
                    continue
                ref = u8(m, 11)[0]
                isb = m[19:20] == b"B"
                sh, px = u4(m, 20)[0], u4(m, 32)[0]
                orders[ref] = [loc, isb, px, sh, nmsg]
                book.setdefault(loc, {}).setdefault(px, [0, 0])[0 if isb else 1] += sh
                lvl.setdefault((loc, px, isb), set()).add(ref)
                touched = loc

            elif t in (b"E", b"C", b"X", b"D", b"U"):
                ref = u8(m, 11)[0]
                o = orders.get(ref)
                if o is None:
                    continue
                loc, isb, px, sz, oseq = o
                is_exec = t in (b"E", b"C")
                k = sz if t in (b"D", b"U") else min(u4(m, 19)[0], sz)

                # only the waiters at THIS level care, and only those that
                # arrived after this order -- everyone else is unaffected
                w = waiting.get((loc, px, isb))
                if w:
                    for e in w:
                        if e["filled"] is None and oseq < e["seq"]:
                            e["qsz"] -= k
                    if is_exec:
                        for e in w:
                            # nobody left ahead and real volume just traded
                            # here: on a FIFO book that volume was ours
                            if e["filled"] is None and e["qsz"] <= 0:
                                e["filled"] = nmsg
                                for h in HORIZONS:
                                    sched.setdefault(nmsg + h, []).append((e, h))

                lv = book.get(loc, {}).get(px)
                if lv:
                    lv[0 if isb else 1] -= k
                o[3] -= k
                if o[3] <= 0:
                    orders.pop(ref, None)
                    s_ = lvl.get((loc, px, isb))
                    if s_:
                        s_.discard(ref)
                if t == b"U":
                    nref, nsh, npx = u8(m, 19)[0], u4(m, 27)[0], u4(m, 31)[0]
                    orders[nref] = [loc, isb, npx, nsh, nmsg]
                    book.setdefault(loc, {}).setdefault(npx, [0, 0])[0 if isb else 1] += nsh
                    lvl.setdefault((loc, npx, isb), set()).add(nref)
                touched = loc

            if touched is not None:
                refresh_best(touched)

            # O(1): only experiments whose horizon lands on this exact message
            hit = sched.pop(nmsg, None)
            if hit:
                for e, h in hit:
                    b = best.get(e["loc"])
                    if b:
                        e["after"][h] = (b[0] + b[2]) / 2.0

            # sweep rarely -- filled orders retire once their last horizon is
            # recorded, unfilled ones once the touch leaves them behind
            if nmsg % 4096 == 0 and nlive:
                for key, w in list(waiting.items()):
                    b = best.get(key[0])
                    keep = []
                    for e in w:
                        if e["filled"] is not None:
                            if nmsg - e["filled"] > max(HORIZONS):
                                done.append(e); nlive -= 1
                            else:
                                keep.append(e)
                            continue
                        if nmsg - e["start"] > GIVEUP:
                            done.append(e); nlive -= 1
                            continue
                        # the touch moved past us; a real maker re-quotes
                        if b and ((e["side"] > 0 and b[0] > e["px"])
                                  or (e["side"] < 0 and b[2] < e["px"])):
                            done.append(e); nlive -= 1
                            continue
                        keep.append(e)
                    if keep:
                        waiting[key] = keep
                    else:
                        del waiting[key]

            if nmsg % PLACE_EVERY == 0 and nlive < MAXLIVE:
                tns = int.from_bytes(m[5:11], "big")
                if RTH0 <= tns < RTH1:
                    for loc in tracked:
                        if nlive >= MAXLIVE:
                            break
                        try_place(loc)
        buf = buf[pos:]

live = [e for w in waiting.values() for e in w]
done.extend(live)
log(f"Parsed {nmsg:,} messages. Placed **{len(done):,} passive orders** at the "
    f"touch across {len(tracked)} symbols.")
log()

rows = []
for e in done:
    if e["filled"] is None:
        rows.append((loc2sym.get(e["loc"], "?"), e["side"], 0, np.nan,
                     e["spread"], e["imb"], *[np.nan] * len(HORIZONS)))
        continue
    aft = e.get("after", {})
    moves = []
    for h in HORIZONS:
        m1 = aft.get(h)
        moves.append(np.nan if m1 is None
                     else (m1 - e["mid0"]) / e["mid0"] * 10000 * e["side"])
    rows.append((loc2sym.get(e["loc"], "?"), e["side"], 1, e["mid0"],
                 e["spread"], e["imb"], *moves))

cols = ["sym", "side", "fill", "mid", "spread", "imb"] + [f"h{h}" for h in HORIZONS]
D = pd.DataFrame(rows, columns=cols)
if not len(D) or D.fill.sum() < 50:
    log(f"Only {int(D.fill.sum()) if len(D) else 0} fills -- too few to measure.")
    finish(0)

D["half_bps"] = D.spread / D.mid * 10000 / 2.0
F = D[D.fill == 1]
log(f"**Fill rate {D.fill.mean()*100:.1f}%** ({int(D.fill.sum()):,} of "
    f"{len(D):,}). Median half-spread captured on a fill: "
    f"**{F.half_bps.median():.2f} bps**.")
log()
log("## Where the mid went after we were filled")
log()
log("| horizon | adverse move | +/- | half-spread | NET | n |")
log("|---|---|---|---|---|---|")
for h in HORIZONS:
    v = F[f"h{h}"].dropna()
    if len(v) < 30:
        log(f"| {h} msgs | too few ({len(v)}) | | | | |")
        continue
    se = v.std() / np.sqrt(len(v))
    half = F.loc[v.index, "half_bps"].median()
    log(f"| {h} msgs | {v.mean():+.3f} bps | {se:.3f} | {half:.2f} bps | "
        f"**{half + v.mean():+.3f} bps** | {len(v):,} |")
log()
log("The adverse column is signed so that NEGATIVE means the market moved "
    "against the fill. NET is the half-spread you captured plus that move: "
    "positive means resting made money, negative means you were run over.")
log()

hmid = HORIZONS[len(HORIZONS) // 2]
log(f"## Does book imbalance let a maker decline the bad fills? (h={hmid})")
log()
try:
    F2 = F.dropna(subset=[f"h{hmid}"]).copy()
    F2["dec"] = pd.qcut(F2.imb, 5, labels=False, duplicates="drop")
    g = F2.groupby("dec").agg(n=("imb", "size"), adverse=(f"h{hmid}", "mean"),
                              half=("half_bps", "median"))
    log("| imbalance quintile at placement | n | adverse move | NET |")
    log("|---|---|---|---|")
    for i, r in g.iterrows():
        log(f"| {int(i)} | {int(r['n']):,} | {r['adverse']:+.3f} bps | "
            f"{r['half'] + r['adverse']:+.3f} bps |")
except Exception as ex:
    log(f"quintile table unavailable: {type(ex).__name__}: {ex}")
log()
log("A maker does not need a signal that predicts the move. It needs one that "
    "says which fills to refuse. If the net is positive in some quintiles and "
    "negative in others, that is a business; if it is negative everywhere, no "
    "amount of CME order book data changes the answer.")
finish(0)
