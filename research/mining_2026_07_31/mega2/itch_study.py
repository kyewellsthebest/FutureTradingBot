"""Rebuild the order book from NASDAQ ITCH and ask whether it predicts anything.

The prerequisite question, answered with free data before anyone pays for CME.

Order book imbalance -- resting size at the bid against resting size at the ask
-- is the most documented short-horizon predictor in the microstructure
literature. It is also completely invisible in trade prints, which is why
sixteen families measured on trades came back null and why Databento's MBO
costs what it does.

This reconstructs the real book from ITCH messages (add / cancel / delete /
execute, with order IDs) and measures the imbalance the same way everything
else in this project was measured:

  information coefficient against forward returns
  a SHUFFLED control, so we see what the pipeline invents from nothing
  train and holdout split by time
  converted to money, because an IC only matters against what trading costs

If imbalance predicts on NASDAQ equities, CME MBO is worth buying. If it does
not, we learned that for nothing.
"""
import os, sys, glob, gzip
import numpy as np, pandas as pd

ROOT = os.environ.get("M2_REPO", os.getcwd())
ITCH = os.path.join(ROOT, "data", "itch")
OUT = os.path.join(ROOT, "research", "ITCH_RESULT.md")
MAXMSG = int(os.environ.get("MAXMSG", "12000000"))
NSYM = int(os.environ.get("NSYM", "12"))
SNAP_EVERY = int(os.environ.get("SNAP_EVERY", "2000"))   # messages between reads


def log(s):
    print(s, flush=True)
    LINES.append(s)


LINES = []
files = sorted(glob.glob(os.path.join(ITCH, "*.gz")))
if not files:
    LINES = ["# ITCH study", "", "No sample file was downloaded -- see "
             "data/itch/NO_SAMPLES for what the directory returned."]
    open(OUT, "w").write("\n".join(LINES)); sys.exit(0)

from itch.parser import MessageParser

log(f"# ITCH order book study\n")
log(f"Source: `{os.path.basename(files[0])}` "
    f"({os.path.getsize(files[0])/1e6:.0f} MB compressed)\n")

# ---------------------------------------------------------------------------
# Book reconstruction. An ITCH order id is unique for its lifetime, so a dict
# from id -> (symbol, side, price, shares) is the entire book. Adds insert,
# cancels reduce, deletes remove, executes reduce and print a trade.
# ---------------------------------------------------------------------------
orders = {}                       # id -> [sym, side, price, shares]
book = {}                         # sym -> {price -> [bid_sz, ask_sz]}
rows = []                         # sampled snapshots
nmsg = 0
counts = {}

parser = MessageParser()
with gzip.open(files[0], "rb") as fh:
    while nmsg < MAXMSG:
        chunk = fh.read(1 << 22)
        if not chunk: break
        for m in parser.read_message_from_bytes(chunk):
            nmsg += 1
            t = m.message_type
            counts[t] = counts.get(t, 0) + 1
            try:
                if t in (b"A", b"F"):
                    sym = m.stock.strip() if isinstance(m.stock, bytes) else str(m.stock).strip()
                    side = m.buy_sell_indicator
                    px = m.price / 10000.0
                    sh = m.shares
                    orders[m.order_reference_number] = [sym, side, px, sh]
                    b = book.setdefault(sym, {}).setdefault(px, [0, 0])
                    b[0 if side in (b"B", "B") else 1] += sh
                elif t in (b"E", b"C", b"X"):
                    o = orders.get(m.order_reference_number)
                    if o:
                        n = getattr(m, "executed_shares", None) or getattr(m, "cancelled_shares", 0)
                        n = min(n or 0, o[3]); o[3] -= n
                        bb = book.get(o[0], {}).get(o[2])
                        if bb: bb[0 if o[1] in (b"B", "B") else 1] -= n
                        if o[3] <= 0: orders.pop(m.order_reference_number, None)
                elif t == b"D":
                    o = orders.pop(m.order_reference_number, None)
                    if o:
                        bb = book.get(o[0], {}).get(o[2])
                        if bb: bb[0 if o[1] in (b"B", "B") else 1] -= o[3]
            except Exception:
                continue
            # periodically snapshot the top of book for the busiest names
            if nmsg % SNAP_EVERY == 0 and book:
                for sym, lv in book.items():
                    bids = [(p, s[0]) for p, s in lv.items() if s[0] > 0]
                    asks = [(p, s[1]) for p, s in lv.items() if s[1] > 0]
                    if not bids or not asks: continue
                    bp, bs = max(bids); ap, asz = min(asks)
                    if ap <= bp or ap - bp > bp * 0.02: continue
                    rows.append((nmsg, sym, bp, bs, ap, asz))

log(f"Parsed **{nmsg:,} messages**, {len(rows):,} book snapshots, "
    f"{len(book):,} symbols.\n")
log("Message mix: " + ", ".join(f"`{k.decode()}`={v:,}" for k, v in
                                sorted(counts.items(), key=lambda x: -x[1])[:8]) + "\n")

if len(rows) < 5000:
    log("\n**Too few snapshots to measure anything.** The book never populated, "
        "which means the parse is wrong rather than the market being quiet.")
    open(OUT, "w").write("\n".join(LINES)); sys.exit(0)

d = pd.DataFrame(rows, columns=["seq", "sym", "bid", "bsz", "ask", "asz"])
# keep the most active names -- thin books are noise, not information
top = d.sym.value_counts().head(NSYM).index
d = d[d.sym.isin(top)].sort_values(["sym", "seq"]).reset_index(drop=True)
d["mid"] = (d.bid + d.ask) / 2.0
d["spread_bps"] = (d.ask - d.bid) / d.mid * 10000
# THE feature: resting size on one side against the other
d["imb"] = (d.bsz - d.asz) / (d.bsz + d.asz)
rng = np.random.default_rng(11)
d["shuffled"] = rng.permutation(d.imb.values)

log(f"Kept {len(d):,} snapshots across the {len(top)} busiest symbols: "
    f"{', '.join(list(top)[:8])}\n")
log(f"Median spread {d.spread_bps.median():.1f} bps, "
    f"median top-of-book {d.bsz.median():.0f} x {d.asz.median():.0f} shares\n")


def ic(x, y):
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 500: return np.nan
    a = pd.Series(x[m]).rank().values; b = pd.Series(y[m]).rank().values
    a = a - a.mean(); b = b - b.mean()
    den = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / den) if den > 0 else np.nan


log("\n## Does book imbalance predict the next move?\n")
log("| horizon | feature | train IC | holdout IC | held sign |")
log("|---|---|---|---|---|")
best = (None, 0.0, 0)
for h in (1, 5, 20, 50):
    g = d.groupby("sym", group_keys=False)
    fwd = g.apply(lambda x: (x.mid.shift(-h) / x.mid - 1.0) * 10000,
                  include_groups=False).values      # forward move in bps
    cut = int(len(d) * 0.7)
    for col in ("imb", "shuffled"):
        it = ic(d[col].values[:cut], fwd[:cut])
        ih = ic(d[col].values[cut:], fwd[cut:])
        held = "yes" if np.isfinite(it) and np.isfinite(ih) and np.sign(it) == np.sign(ih) else "no"
        log(f"| {h} snapshots | {col} | {it:+.4f} | {ih:+.4f} | {held} |")
        if col == "imb" and np.isfinite(ih) and abs(ih) > abs(best[1]):
            best = (h, ih, np.nanmedian(np.abs(fwd)))

log("")
if best[0]:
    h, icv, mv = best
    # an IC of x on a move of mv bps is worth about x*mv bps a trade, against
    # a spread of `spread_bps` -- the only comparison that decides anything
    worth = abs(icv) * mv
    sp = d.spread_bps.median()
    log(f"**Best: {icv:+.4f} at {h} snapshots ahead.** A typical move over that "
        f"horizon is {mv:.1f} bps, so the signal is worth about **{worth:.2f} bps** "
        f"per trade against a **{sp:.1f} bps** spread.\n")
    log(f"- crossing the spread costs {sp:.1f} bps, so a taker needs "
        f"{sp/max(worth,1e-9):.1f}x this signal to break even")
    log(f"- **verdict: {'worth pursuing on CME' if worth > sp else 'does NOT clear the spread'}**")
log("\nThe shuffled row is the control. Imbalance has to beat it, not zero.")
open(OUT, "w").write("\n".join(LINES))
print("\nwrote", OUT)
