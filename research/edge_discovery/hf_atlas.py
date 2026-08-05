"""HF signal atlas: conditional forward returns for second-scale states.

For each candidate state, measure on IN-SAMPLE ONLY (Sep 2023 - Feb 2025):
  * events/week
  * E[forward move] at 5/10/30/60/120 traded-seconds, in NQ ticks
  * t-stat of the 30s horizon
A state qualifies for simulation only if |E| >= ~0.75 tick at some horizon
with >= 1,500 events/week (fills will be a fraction of signals).

Forward returns use close-to-close of traded seconds — no fill modeling here;
this is the physics scan, not the P&L scan.
"""
import sys, warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from tick_features import load_sec

TICK = 0.25
IS_END = pd.Timestamp("2025-03-01", tz="America/New_York")

df = load_sec(columns=["n_trades", "volume", "delta", "ret", "ret_sd",
                       "r10", "r30", "r60", "ofi10", "ofi60", "burst",
                       "big_delta", "gap_s"])
c = df["close"]
fwd = {h: (c.shift(-h) - c) / TICK for h in (5, 10, 30, 60, 120)}
is_mask = np.asarray(df.index < IS_END)
rth = df["rth"].values
act = (df["n_trades"].rolling(30).sum() > 150).values     # genuinely busy tape
weeks_is = (IS_END - df.index[0]).days / 7

# tick-displacement over short windows, in ticks
d5 = (c - c.shift(5)) / TICK
d15 = (c - c.shift(15)) / TICK
d60 = (c - c.shift(60)) / TICK
ofi10, ofi60 = df["ofi10"], df["ofi60"]
burst = df["burst"]
bigd = df["big_delta"]
hh = df["hhmm"].values
morning = (hh >= 930) & (hh < 1130)
pm = (hh >= 1330) & (hh < 1600)

STATES = {}
def S(name, cond):
    STATES[name] = cond.values if hasattr(cond, "values") else cond

# displacement states (both busy and any-tape)
for k in (4, 8, 12):
    S(f"d5<=-{k}", (d5 <= -k) & act & rth)
    S(f"d5>=+{k}", (d5 >= k) & act & rth)
for k in (8, 16, 24):
    S(f"d15<=-{k}", (d15 <= -k) & act & rth)
    S(f"d15>=+{k}", (d15 >= k) & act & rth)
    S(f"d60<=-{k}", (d60 <= -k) & act & rth)
    S(f"d60>=+{k}", (d60 >= k) & act & rth)
# imbalance states
for q in (0.4, 0.7):
    S(f"ofi10<=-{q}", (ofi10 <= -q) & act & rth)
    S(f"ofi10>=+{q}", (ofi10 >= q) & act & rth)
S("ofi60<=-0.3", (ofi60 <= -0.3) & act & rth)
S("ofi60>=+0.3", (ofi60 >= 0.3) & act & rth)
# flow-vs-price divergence
S("divg_dnflow_upmv", (ofi10 <= -0.4) & (d15 >= 4) & act & rth)
S("divg_upflow_dnmv", (ofi10 >= 0.4) & (d15 <= -4) & act & rth)
# displacement WITH confirming/opposing flow
S("d15<=-8&sellflow", (d15 <= -8) & (ofi10 <= -0.3) & act & rth)
S("d15<=-8&buyflow", (d15 <= -8) & (ofi10 >= 0.3) & act & rth)
S("d15>=+8&buyflow", (d15 >= 8) & (ofi10 >= 0.3) & act & rth)
S("d15>=+8&sellflow", (d15 >= 8) & (ofi10 <= -0.3) & act & rth)
# burst-conditioned displacement
S("burst&d5<=-6", (burst > 3) & (d5 <= -6) & rth)
S("burst&d5>=+6", (burst > 3) & (d5 >= 6) & rth)
# big-lot impulse
S("bigd<=-40", (bigd <= -40) & act & rth)
S("bigd>=+40", (bigd >= 40) & act & rth)
# session windows (displacement in morning vs pm)
S("am_d15<=-8", (d15 <= -8) & act & morning)
S("pm_d15<=-8", (d15 <= -8) & act & pm)
S("am_d15>=+8", (d15 >= 8) & act & morning)
S("pm_d15>=+8", (d15 >= 8) & act & pm)

print(f"{'state':<22s} {'ev/wk':>7s} | " + " ".join(f"E{h:>3d}s" for h in (5, 10, 30, 60, 120)) + " | t30")
rows = []
for name, cond in STATES.items():
    m = cond & is_mask
    n = m.sum()
    if n < 200:
        print(f"{name:<22s} {'<200':>7s}")
        continue
    evwk = n / weeks_is
    es = []
    for h in (5, 10, 30, 60, 120):
        es.append(fwd[h].values[m].mean())
    f30 = fwd[30].values[m]
    f30 = f30[~np.isnan(f30)]
    t30 = f30.mean() / (f30.std() / np.sqrt(len(f30)) + 1e-12)
    rows.append((name, evwk, es, t30))
    print(f"{name:<22s} {evwk:>7.0f} | " + " ".join(f"{e:>5.2f}" for e in es) + f" | {t30:>5.1f}")

print("\n=== QUALIFIERS (|E|>=0.75 tick at some horizon, >=1500 ev/wk) ===")
for name, evwk, es, t30 in rows:
    if evwk >= 1500 and max(abs(e) for e in es) >= 0.75:
        print(f"{name:<22s} ev/wk={evwk:.0f} maxE={max(es, key=abs):+.2f}t t30={t30:+.1f}")
