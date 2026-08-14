"""52-week projection for the pulse book (MNQ + MES + MYM), in the same
format as the basket's Projection_52wk_PerMarketCaps.pdf.

- Daily P&L per micro comes from the REAL validated held-out days
  (data/cap_measure.json, written by cap_measure.py), extremes trimmed
  at p1/p99, chronological order, tiled to 52 weeks.
- Sizing re-evaluated EVERY TRADING DAY at session open (user order:
  "as soon as you can up the position size, do it, doesn't matter if
  it's in the middle of the week").
- Per-market micro caps are MEASURED from the tape: <=10% of the
  notional that trades through our limit price in the first minute,
  at the 25th percentile of all validated fills. Beyond the cap we
  stop being a bystander at our own price level.
- One "unit" = 1 micro on each of the three markets. Policy B adds a
  unit per $3,000 of balance (recommended); Policy C per $2,000
  (aggressive). Intraday margin (~$200/unit) never binds before the
  policy does -- the policy IS the risk rail, not the broker minimum.

Writes deploy/Projection_52wk_Pulse.pdf.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402

from fpdf import FPDF  # noqa: E402

START_BAL = 4000.0
WEEKS = 52
DAYS = WEEKS * 5
POLICIES = {"B": ("RECOMMENDED", 3000.0), "C": ("AGGRESSIVE", 2000.0)}
MARGIN_PER_UNIT = 200.0          # ~$100 MNQ + $50 MES + $50 MYM intraday
NAMES = {"MNQ": "Nasdaq", "MES": "S&P 500", "MYM": "Dow"}

data = json.load(open(os.path.join(fuse.ROOT, "data", "cap_measure.json")))
MKTS = list(data.keys())
CAPS = {m: int(data[m]["cap_micros"]) for m in MKTS}

# ---- daily per-micro series: union of dates, chronological, trimmed ----
dates = sorted(set().union(*(data[m]["daily"].keys() for m in MKTS)))
series = {}
for m in MKTS:
    v = np.array([data[m]["daily"].get(d, 0.0) for d in dates])
    lo, hi = np.percentile(v[v != 0], [1, 99]) if (v != 0).any() else (0, 0)
    series[m] = np.clip(v, lo, hi)
n_real = len(dates)
print(f"{n_real} real held-out days; caps {CAPS}")


def simulate(per_unit_capital):
    bal = START_BAL
    weeks = []
    for w in range(WEEKS):
        d0 = w * 5
        wk_start_units = int(min(bal // per_unit_capital, 10**9))
        wk = {"days": [], "size": max(1, wk_start_units),
              "eff": sum(min(max(1, wk_start_units), CAPS[m])
                         for m in MKTS)}
        for dd in range(5):
            di = (d0 + dd) % n_real
            n_pol = max(1, int(bal // per_unit_capital))
            day_pnl = sum(min(n_pol, CAPS[m]) * series[m][di]
                          for m in MKTS)
            bal += day_pnl
            wk["days"].append(day_pnl)
        wk["pnl"] = sum(wk["days"])
        wk["bal"] = bal
        weeks.append(wk)
    return weeks


results = {p: simulate(k) for p, (_, k) in POLICIES.items()}

# --------------------------------- PDF ---------------------------------
pdf = FPDF(format="A4")
pdf.set_auto_page_break(False)
pdf.set_margins(18, 16)


def line(txt, size=11, style="", h=6.0):
    pdf.set_font("Courier", style, size)
    pdf.cell(0, h, txt, new_x="LMARGIN", new_y="NEXT")


usd = lambda v: f"${v:,.0f}"

# ---- title page ----
pdf.add_page()
line("52-WEEK PROJECTION - PER-MARKET CAPS", 15, "B", 8)
line("the PULSE book (impulse->0.618 pullback->2:1 bracket, tick-true"
     " validated)", 9.5, "", 5)
line("sizes re-checked EVERY SESSION - the moment balance affords a"
     " unit, it trades", 9.5, "", 5)
line("", 9, "", 4)
line("MARKET     HELD-OUT $/wk/micro   MICRO CAP   (10% of measured"
     " level flow)", 10, "B", 6)
wk_all = {m: data[m]["total"] / max(len(data[m]["daily"]) / 5, 1)
          for m in MKTS}
for m in MKTS:
    line(f"{NAMES[m]:<10} {usd(wk_all[m]):>12}          "
         f"{CAPS[m]:>4}   through-vol p25 "
         f"{data[m]['through_p25']:.0f} big/min", 10, "", 5.5)
line("", 9, "", 4)
for p, (label, k) in POLICIES.items():
    wks = results[p]
    final = wks[-1]
    tgt = final["size"]
    line(f"POLICY {p} ({label}, +1 unit per {usd(k)}):", 11, "B", 6)
    line(f"52-wk ending {usd(final['bal'])}   final target {tgt}u,"
         f" effective {final['eff']} micros after caps", 10, "", 6)
line("", 9, "", 4)
line("Built from the strategy's REAL validated held-out days (extremes"
     " trimmed,", 9, "", 4.5)
line("chronological order). NOT a promise - losing streaks arrive in a"
     " different", 9, "", 4.5)
line("order in real life. A unit = 1 micro on each market"
     " (MNQ+MES+MYM);", 9, "", 4.5)
line("each market stops adding size at ITS OWN measured cap. Margin"
     f" ~{usd(MARGIN_PER_UNIT)}/unit", 9, "", 4.5)
line("intraday - the policy binds long before the broker does. Rails"
     " scale with", 9, "", 4.5)
line("size: daily breaker = $1,000 x units. Demo first. Live on your"
     " word.", 9, "", 4.5)
line("Session: 13:30-20:00 UTC (US cash hours) - the only window the"
     " edge is", 9, "", 4.5)
line("validated in.", 9, "", 4.5)

# ---- week pages ----
DAYN = ["Mon", "Tue", "Wed", "Thu", "Fri"]
for p, (label, k) in POLICIES.items():
    wks = results[p]
    for pg in range(0, WEEKS, 4):
        pdf.add_page()
        line(f"Policy {p} ({label}) - weeks {pg + 1}-{min(pg + 4, WEEKS)}",
             12, "B", 8)
        for wi in range(pg, min(pg + 4, WEEKS)):
            wk = wks[wi]
            line(f"WK {wi + 1} size {wk['size']}u eff {wk['eff']} "
                 f"{'+' if wk['pnl'] >= 0 else '-'}"
                 f"${abs(wk['pnl']):,.0f} bal {usd(wk['bal'])}",
                 11, "B", 6.5)
            for dn, dp in zip(DAYN, wk["days"]):
                line(f"{dn} {'+' if dp >= 0 else '-'}$"
                     f"{abs(dp):>10,.0f}", 10, "", 5.2)
            line("", 8, "", 2.5)

out = os.path.join(fuse.ROOT, "deploy", "Projection_52wk_Pulse.pdf")
pdf.output(out)
print("wrote", out)
