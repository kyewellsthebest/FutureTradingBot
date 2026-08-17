"""Month-end rebalancing: the first mechanism-first test in this repo.

THE MECHANISM, stated before any code runs. A 60/40 pension fund whose
equity sleeve has rallied during the month is over-weight equities at
month end. Its mandate obliges it to sell equities and buy bonds to
restore the ratio, on a schedule, regardless of price or view. That is a
counterparty who is forced to trade against their own interest at a
known time -- which is the only kind of edge worth looking for, and the
one thing every failed family in this project lacked.

    prediction:  strong equity month  -> equities SOLD into month end
                 weak equity month    -> equities BOUGHT into month end
                 and the bond leg trades OPPOSITE

The bond leg matters. If the effect is really rebalancing, it must show
up with the opposite sign in ZN. If equities alone move and bonds do
not, it is not rebalancing -- it is something else wearing its clothes,
and the mechanism claim is false.

WHAT THIS FIXES IN THE OBVIOUS IMPLEMENTATION. The natural way to write
this produces a false positive twice over:

  ONE EVENT, NOT ONE PER BAR. A month-end window is ~780 one-minute RTH
  bars. Firing on every bar gives ~780 overlapping "trades" a month
  instead of one, each sharing 239/240 of its forward return with its
  neighbours. Here each month end is exactly ONE observation.

  THE CONTROL MUST PRESERVE CLUSTERING. Matching only the trade COUNT
  compares ~24 clustered real events against hundreds of scattered
  random ones. Scattered samples have far lower variance, so the real
  arm clears them by luck far more often than the p-value suggests. The
  control here draws the SAME NUMBER of month-end-shaped events at
  random month positions, so the clustering is identical and only the
  timing differs.

Costs: charged in full, per trade, both legs.
Success bar, fixed here: net positive after cost AND an empirical
p-value below 0.05 against the matched control.

Output: research/MONTHEND_FLOW.md
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
POLY = os.path.join(ROOT, "data", "polygon")
OUT = os.path.join(ROOT, "research", "MONTHEND_FLOW.md")
NSIM = 2000
# file, $/point, round-trip cost
MKT = {
    "MES": ("ES_5min.csv", 5.0, 2.58),
    "MNQ": ("NQ_5min.csv", 2.0, 1.83),
    "MYM": ("YM_5min.csv", 0.5, 1.83),
    "M2K": ("RTY_5min.csv", 5.0, 1.38),
    "ZN":  ("ZN_5min.csv", 1000.0, 18.12),
    "ZB":  ("ZB_5min.csv", 1000.0, 33.75),
}
HOLD_D = [1, 2, 3, 5]
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def daily(fn):
    d = pd.read_csv(os.path.join(POLY, fn))
    d["ts"] = pd.to_datetime(d["ts"], utc=True)
    s = d.set_index("ts")["close"].resample("1D").last().dropna()
    s.index = s.index.normalize().tz_localize(None)
    return s[s.index.dayofweek < 5]


def main():
    log("# Month-end rebalancing -- the first mechanism-first test here")
    log()
    log("**The mechanism, stated before the code ran.** A 60/40 pension "
        "fund whose equity sleeve rallied during the month is "
        "over-weight equities at month end. Its mandate obliges it to "
        "sell equities and buy bonds on a schedule, regardless of price "
        "or view. That is a counterparty forced to trade against their "
        "own interest at a known time -- the only kind of edge worth "
        "looking for, and the thing every failed family in this project "
        "lacked.")
    log()
    log("    strong equity month -> equities SOLD into month end")
    log("    weak equity month   -> equities BOUGHT into month end")
    log("    and the BOND leg must trade opposite")
    log()
    log("The bond leg is the real test. If this is rebalancing it has to "
        "appear with the opposite sign in ZN and ZB. If equities move "
        "and bonds do not, it is not rebalancing and the mechanism claim "
        "is false.")
    log()
    log("Each month end is **one observation**, not one per bar. The "
        "control draws the same number of month-end-shaped events at "
        "random month positions, so **clustering is preserved** and only "
        "the timing differs -- matching trade count alone compares "
        "clustered events against scattered ones and inflates every "
        "p-value.")
    log()

    # THE CONDITIONING VARIABLE IS ALWAYS THE EQUITY MONTH.
    # A pension rebalances because ITS EQUITY SLEEVE moved. So the bond
    # leg must be conditioned on how EQUITIES did, not on how bonds did.
    # Conditioning ZN on ZN's own month return tests "if bonds rallied,
    # buy bonds" -- a different and irrelevant hypothesis, and getting
    # that wrong nearly retired the mechanism on a broken falsification.
    try:
        eq = daily(MKT["MES"][0])
        eqm = pd.DataFrame({"px": eq})
        eqm["ym"] = eqm.index.to_period("M")
        eq_start = eqm.groupby("ym")["px"].first()
    except Exception as exc:                                  # noqa: BLE001
        print(f"equity reference failed: {exc}")
        return

    def eq_ret(asof, m):
        """Equity month-to-date return as of `asof`, no look-ahead."""
        if m not in eq_start.index:
            return None
        prior = eqm.index[(eqm["ym"] == m) & (eqm.index <= asof)]
        if not len(prior):
            return None
        return float(eqm.at[prior[-1], "px"] / eq_start.at[m] - 1.0)

    rows = []
    for name, (fn, ppt, cost) in MKT.items():
        try:
            s = daily(fn)
        except Exception as exc:                              # noqa: BLE001
            print(f"  {name}: {str(exc)[:70]}")
            continue
        df = pd.DataFrame({"px": s})
        df["ym"] = df.index.to_period("M")
        # position of each day within its month, counted from the END
        df["from_end"] = df.groupby("ym").cumcount(ascending=False)
        df["n_in_m"] = df.groupby("ym")["px"].transform("size")
        months = sorted(df["ym"].unique())
        rng = np.random.default_rng(4)
        for hold in HOLD_D:
            real = []
            for m in months[1:]:
                sub = df[df["ym"] == m]
                if len(sub) < 15:
                    continue
                # month return measured to the entry bar, no look-ahead
                ent_i = sub.index[max(len(sub) - 1 - hold, 0)]
                mret = eq_ret(ent_i, m)
                if mret is None:
                    continue
                nxt = df.index[df.index > ent_i]
                if len(nxt) < hold:
                    continue
                exit_i = nxt[hold - 1]
                move = df.at[exit_i, "px"] - df.at[ent_i, "px"]
                # rebalance: SELL equities after a strong month.
                # bonds take the opposite side.
                side = -np.sign(mret) if name not in ("ZN", "ZB") \
                    else np.sign(mret)
                if side == 0:
                    continue
                real.append(side * move * ppt - cost)
            if len(real) < 20:
                continue
            real = np.array(real)
            obs = real.mean()
            # matched control: same count, same clustering, random month
            # position instead of month end
            beats = 0
            allday = df.index.values
            for _ in range(NSIM):
                sim = []
                for m in months[1:]:
                    sub = df[df["ym"] == m]
                    if len(sub) < 15:
                        continue
                    k = int(rng.integers(1, len(sub) - hold - 1))
                    ent_i = sub.index[k]
                    mret = eq_ret(ent_i, m)
                    if mret is None:
                        continue
                    nxt = df.index[df.index > ent_i]
                    if len(nxt) < hold:
                        continue
                    exit_i = nxt[hold - 1]
                    move = df.at[exit_i, "px"] - df.at[ent_i, "px"]
                    side = -np.sign(mret) if name not in ("ZN", "ZB") \
                        else np.sign(mret)
                    if side == 0:
                        continue
                    sim.append(side * move * ppt - cost)
                if sim and np.mean(sim) >= obs:
                    beats += 1
            p = beats / NSIM
            rows.append((p, obs, name, hold, len(real),
                         obs * len(real) / (len(real) / 12.0)))
        del df
    rows.sort()

    log("| market | hold | trades | $/trade | $/year | p vs matched "
        "control |")
    log("|" + "---|" * 6)
    for p, obs, name, hold, n, yr in rows:
        log(f"| {name} | {hold}d | {n} | **${obs:+.2f}** | ${yr:+,.0f} | "
            f"{p:.3f} |")
    log()
    hits = [r for r in rows if r[0] < 0.05 and r[1] > 0]
    log(f"**Positive after cost AND p < 0.05: {len(hits)} of "
        f"{len(rows)}**")
    log()
    for p, obs, name, hold, n, yr in hits:
        log(f"- {name} at {hold} days: ${obs:+.2f}/trade over {n} month "
            f"ends, p = {p:.3f}")
    log()
    log("## How to read a hit")
    log()
    log("A single market clearing p < 0.05 across roughly 24 tests is "
        "expected about once by luck. The claim only becomes "
        "interesting if the EQUITY markets and the BOND markets both "
        "clear it with the signs the mechanism predicts -- that is a "
        "joint statement luck does not easily produce, and it is the "
        "difference between a statistical artifact and a description of "
        "something a pension fund is actually obliged to do.")
    log()
    open(OUT, "w").write("\n".join(L) + "\n")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
