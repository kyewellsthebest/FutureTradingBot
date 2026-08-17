"""Generate THE SEARCH MODEL -- the full process document, as a PDF.

Everything about how this project looks for strategies: where candidates
come from, the decision tree that runs when the user says "search", every
gate in the validation gauntlet, the complete catalogue of false
positives and what caught each one, and the arithmetic that governs all
of it.

    python research/make_search_model_pdf.py
"""
import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table,
                                TableStyle)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "SEARCH_MODEL.pdf")
INK = colors.HexColor("#12161c")
MUTE = colors.HexColor("#5b6572")
RULE = colors.HexColor("#d4d9e0")
BAD = colors.HexColor("#b3261e")
GOOD = colors.HexColor("#146c43")
BAND = colors.HexColor("#f2f4f7")

ss = getSampleStyleSheet()
S = {
    "title": ParagraphStyle("t", parent=ss["Title"], fontName="Helvetica-Bold",
                            fontSize=26, leading=30, textColor=INK,
                            spaceAfter=4),
    "sub": ParagraphStyle("s", parent=ss["Normal"], fontName="Helvetica",
                          fontSize=11.5, leading=16, textColor=MUTE,
                          spaceAfter=18),
    "h1": ParagraphStyle("h1", parent=ss["Heading1"],
                         fontName="Helvetica-Bold", fontSize=16, leading=20,
                         textColor=INK, spaceBefore=20, spaceAfter=8),
    "h2": ParagraphStyle("h2", parent=ss["Heading2"],
                         fontName="Helvetica-Bold", fontSize=12, leading=16,
                         textColor=INK, spaceBefore=14, spaceAfter=5),
    "body": ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica",
                           fontSize=9.8, leading=14.5, textColor=INK,
                           alignment=TA_LEFT, spaceAfter=7),
    "small": ParagraphStyle("sm", parent=ss["Normal"], fontName="Helvetica",
                            fontSize=8.6, leading=12.5, textColor=MUTE,
                            spaceAfter=6),
    "code": ParagraphStyle("c", parent=ss["Normal"], fontName="Courier",
                           fontSize=8.6, leading=12, textColor=INK,
                           backColor=BAND, borderPadding=7, spaceAfter=9),
    "quote": ParagraphStyle("q", parent=ss["Normal"], fontName="Helvetica-Oblique",
                            fontSize=9.6, leading=14, textColor=MUTE,
                            leftIndent=12, spaceAfter=8),
}
F = []


def P(t, s="body"):
    F.append(Paragraph(t, S[s]))


def H1(t):
    F.append(Paragraph(t, S["h1"]))


def H2(t):
    F.append(Paragraph(t, S["h2"]))


def SP(h=6):
    F.append(Spacer(1, h))


def TBL(rows, widths, align=None, size=8.6, head=True):
    st = [("FONT", (0, 0), (-1, -1), "Helvetica", size),
          ("TEXTCOLOR", (0, 0), (-1, -1), INK),
          ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("TOPPADDING", (0, 0), (-1, -1), 5),
          ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
          ("LEFTPADDING", (0, 0), (-1, -1), 7),
          ("RIGHTPADDING", (0, 0), (-1, -1), 7),
          ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE)]
    if head:
        st += [("FONT", (0, 0), (-1, 0), "Helvetica-Bold", size),
               ("BACKGROUND", (0, 0), (-1, 0), BAND),
               ("LINEBELOW", (0, 0), (-1, 0), 0.9, INK)]
    if align:
        for c, a in align.items():
            st.append(("ALIGN", (c, 0), (c, -1), a))
    t = Table(rows, colWidths=widths, style=TableStyle(st), hAlign="LEFT")
    F.append(t)
    SP(10)


def foot(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTE)
    canvas.drawString(20 * mm, 12 * mm, "THE SEARCH MODEL")
    canvas.drawRightString(190 * mm, 12 * mm, f"{doc.page}")
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.4)
    canvas.line(20 * mm, 15 * mm, 190 * mm, 15 * mm)
    canvas.restoreState()


# ============================== COVER ==============================
SP(40)
P("THE SEARCH MODEL", "title")
P("How this project looks for trading strategies, what it has ruled "
  "out, and how to tell a finding from an artifact.", "sub")
TBL([["repository", "FutureTradingBot"],
     ["branch", "claude/hello-vc2ivo"],
     ["scope", "every process in the search pipeline"],
     ["status", "22 hypotheses closed, 0 survivors"]],
    [38 * mm, 120 * mm], head=False)

SP(10)
H1("The one-paragraph answer")
P("<b>No, we do not mostly find strategies online and turn them into "
  "configs</b> -- though that has happened three times and all three "
  "failed. Predominantly we <b>generate families of rules and "
  "grid-search them</b>, and that method has been tested to "
  "destruction: 1.38 billion configurations in a single family, roughly "
  "six million signals across all families, zero survivors, and a "
  "<i>measured negative return</i> to searching harder. The part of this "
  "project with genuine value is not the search. It is the validation "
  "gauntlet, which caught six false positives in one day -- every one of "
  "which looked exactly like a working strategy.")

P("The single most useful sentence in this document: <b>every error "
  "found in this project made results look BETTER, never worse.</b> Not "
  "once has a bug produced a false negative. That asymmetry is the "
  "signature of motivated error, and it is why the gauntlet is built the "
  "way it is.", "body")

F.append(PageBreak())

# ========================= PART 1 =========================
H1("Part 1 -- Where candidates come from")
P("Three channels. They have very different hit rates and very "
  "different reasons for failing.")

H2("Channel A -- Imported configs")
P("Someone else's parameter set plus a claimed P&amp;L. Arrives as a "
  "leaderboard, a dossier, or a research summary.")
TBL([["import", "claim", "measured"],
     ["INVERSE FADE leaderboard", "+$1,034/day", "-$72/day"],
     ["LEVELRIDE dossier", "+$2,471/week", "retracted, unmeasured"],
     ["778M-config blueprint (ZB/ZN)", "+$4,093/week", "not holdable on $4k"]],
    [62 * mm, 44 * mm, 52 * mm])
P("<b>Process:</b> reproduce the claim in our own engine first. If it "
  "reproduces, vary the ONE assumption under test and watch what moves. "
  "If it does not reproduce, find out why before arguing about whether "
  "it is real.", "body")
P("<b>Hit rate: 0 of 3.</b> All three failed on the same thing -- a fill "
  "assumption that cannot exist -- and in all three cases the author had "
  "flagged the risk in their own document and then put the flattering "
  "number in the headline.", "body")

H2("Channel B -- Generated families, grid searched")
P("Define a rule shape with N parameters, enumerate the parameter space, "
  "score every cell. This is the dominant mode in this repo and it is "
  "the one that does not work.")
TBL([["family", "cells", "survivors"],
     ["Impulse-pullback, causal, both anchors", "28,800", "0"],
     ["High-frequency 15s brackets", "405", "0"],
     ["Overnight/Asia/Europe sessions", "200", "0"],
     ["Fade conditioning (size/hour/vol/range)", "52", "0"],
     ["AND-combos of technical features (FX)", "1,380,000,000", "0"],
     ["Alternative data, multi-day horizons", "180", "1 (= chance)"]],
    [82 * mm, 40 * mm, 36 * mm], align={1: "RIGHT", 2: "RIGHT"})
P("The ledger's own entry #19 records the verdict on the method itself: "
  "<b>selection-by-train-score is HARMFUL -- a measured negative return "
  "to searching harder.</b> As the selection threshold tightens, mean "
  "holdout performance falls from -1.13 to -243 pips while the hit rate "
  "rises to 65.9%. Tighter selection finds configs that win often and "
  "lose enormously.", "body")

H2("Channel C -- Mechanism first")
P("Name the counterparty and why they are trading against their own "
  "interest. If you cannot name them, there is no edge -- you have found "
  "a pattern in noise.")
P("Real examples: index funds must buy at rebalance; futures longs must "
  "roll before expiry; options dealers must delta-hedge; pensions "
  "rebalance at month end; margin calls force liquidation. The flow "
  "exists because of a <i>mandate</i>, which is why it persists after "
  "being published.", "body")
P("<b>Used in this project: almost never.</b> That is the gap. Every "
  "failed family above describes a shape on a chart, not a person with "
  "an obligation.", "body")

F.append(PageBreak())

# ========================= PART 2 =========================
H1('Part 2 -- What runs when you say "search"')
P("The actual decision sequence, in order.")

steps = [
    ("1. Has this been tested?",
     "grep research/HYPOTHESIS_LEDGER.md before writing any code. The "
     "ledger is append-only so that no search rediscovers a corpse. "
     "22 entries, most of them NULL."),
    ("2. What is the mechanism?",
     "Who is forced to trade, and why? No mechanism means the prior is "
     "near zero and the result should be read accordingly. This step is "
     "skipped far too often here."),
    ("3. What horizon?",
     "The horizon sets the cost bar and nothing else matters as much. "
     "10 minutes needs IC 0.040; a week needs 0.0019. Twenty times "
     "easier for the same signal."),
    ("4. Is the bar reachable?",
     "edge = IC x sigma(horizon), against commission plus spread. If the "
     "best plausible IC cannot clear it, do not run the test -- the "
     "answer is already known."),
    ("5. What is the control?",
     "Decided BEFORE running, never after. A RANDOM arm in the same "
     "geometry, a shuffled target, a time-shifted feature, or a "
     "synthetic with a known answer. Usually several."),
    ("6. What is the success criterion?",
     "Written into the script header before execution, so it cannot "
     "move once results are visible. Every research file in this repo "
     "carries its bar in its docstring."),
    ("7. Run it.",
     "Background, logged, with a monitor. Machine limits: 4 cores, "
     "15 GiB, no swap. Heavy jobs go to GitHub Actions."),
    ("8. Read the CONTROL first.",
     "Not the result. If RANDOM is also profitable, the result is "
     "meaningless no matter how good it looks -- and this is exactly how "
     "the overnight false positive was caught."),
    ("9. If positive: assume artifact.",
     "Hunt for the bug before celebrating. Six for six so far. Check "
     "fill prices, look-ahead, overlap, selection, and whether the "
     "sample is conditioned on the answer."),
    ("10. If negative: check the harness works.",
     "Plant a synthetic edge and confirm it is found. A harness that "
     "cannot detect a known signal proves nothing when it reports "
     "nothing."),
]
for a, b in steps:
    F.append(KeepTogether([Paragraph(f"<b>{a}</b>", S["h2"]),
                           Paragraph(b, S["body"])]))

SP(4)
P("Steps 9 and 10 are deliberately asymmetric, and that asymmetry is a "
  "known weakness. Positives get audited hard; negatives get audited "
  "lightly. It is bounded only by the live account -- a systematic "
  "false-negative bias would show up as the bot making money while the "
  "model said it should not. It is doing the opposite.", "small")

F.append(PageBreak())

# ========================= PART 3 =========================
H1("Part 3 -- The validation gauntlet")
P("Eleven gates. Each catches a different failure. Most candidates die "
  "at gate 3 or 5.")

TBL([["#", "gate", "what it catches", "caught in practice"],
     ["0", "Data integrity", "corrupt or misordered source data",
      "8 contracts vs Polygon: 99.4-99.7%, range 1.000"],
     ["1", "Harness calibration",
      "a measuring device that cannot measure",
      "planted edge found; zero-drift walk must return 0"],
     ["2", "Criterion fixed first", "moving the goalposts",
      "every script header states its bar"],
     ["3", "RANDOM control, same geometry",
      "results that are geometry, not skill",
      "overnight: RANDOM also +$0.89/trade"],
     ["4", "Measured noise floor",
      "theoretical error bars that are too tight",
      "6-sample floor passed 5 fakes; 100-sample passed 1"],
     ["5", "Fill physics",
      "prices the market never offered",
      "fade: +$147/day at-level vs -$72 honest"],
     ["6", "All-cell empirical null",
      "the best of many cells looking good by luck",
      "conditioning: best cell below the p99 null"],
     ["7", "Out-of-sample / walk-forward",
      "curve fitting",
      "standard, but blind to fill-model error"],
     ["8", "Stale placebo",
      "signals that work when deliberately delayed",
      "delay_bars in causal_engine"],
     ["9", "Executor convergence",
      "backtest and bot disagreeing",
      "29/29 identical trades on the Friday tape"],
     ["10", "Live or paper fills",
      "everything the simulator cannot see",
      "predicted -$2.81/trade, live -$3.64"]],
    [8 * mm, 34 * mm, 52 * mm, 64 * mm], size=8.0)

P("<b>Gate 7 is the one most people stop at, and it is the weakest.</b> "
  "Out-of-sample testing catches overfitting. It cannot catch a wrong "
  "fill model, because the same wrong model is applied to both halves. "
  "Both imported leaderboards passed out-of-sample and failed gate 5.", "body")

F.append(PageBreak())

# ========================= PART 4 =========================
H1("Part 4 -- The failure catalogue")
P("Every false positive found in a single day, with what produced it "
  "and what caught it. This table is the most valuable thing in the "
  "document.")

TBL([["what it claimed", "true value", "cause", "caught by"],
     ["Overnight edge +$1.23/trade", "-$1.33",
      "timeouts booked at zero instead of marked to market; 57% of trades",
      "RANDOM control was also profitable"],
     ["Maker entry +$3.62", "negative",
      "marked against the wrong mid",
      "magnitude sanity check"],
     ["Maker mark +7 ticks", "+2.00",
      "volume credited to our queue regardless of trade price",
      "same error class as the fade"],
     ["Fade +$147/day", "-$72/day",
      "entry booked at a level the market had already left",
      "three fill models run side by side"],
     ["Breakeven exit +$129/day", "worse than no rule",
      "exit booked at entry while 50pt underwater",
      "zero-drift synthetic printed +$43/day"],
     ["5 alt-data survivors", "1 (= chance)",
      "noise floor estimated from only 6 samples, biased low",
      "theoretical SE did not match the floor"],
     ["Instrument table complete", "empty",
      "exception swallowed silently; confident prose over no data",
      "noticed the table had no rows"],
     ["LEVELRIDE -$43/week", "unmeasured",
      "EOD flatten never fired; open winners dropped",
      "calibration against a known answer"]],
    [40 * mm, 24 * mm, 54 * mm, 40 * mm], size=7.8)

H2("The pattern")
P("<b>Eight errors. Eight false positives. Zero false negatives.</b> "
  "Not one bug ever made a strategy look worse than it was.", "body")
P("Three of the eight are literally the same error wearing different "
  "hats: <b>booking a fill at a price the market has already left.</b> "
  "The fade entering at a stale level, the maker marking against a "
  "departed mid, and a breakeven stop 'exiting at entry' with the market "
  "50 points away. It is the easiest way in the world to manufacture an "
  "edge, and it produces plausible numbers -- +$211/day, not "
  "+$1 million -- which is exactly why it survives review.", "body")
P("<b>What caught them was never code reading.</b> It was controls and "
  "calibration. A RANDOM arm that also makes money, or a driftless "
  "synthetic that prints profit, is unmissable. Reading the code, they "
  "were missed every time.", "body")

F.append(PageBreak())

# ========================= PART 5 =========================
H1("Part 5 -- The arithmetic that governs everything")

H2("The four formulas")
P("edge   = IC x sigma(horizon)<br/>"
  "cost   = commission + spread crossed<br/>"
  "tradability = edge / cost<br/>"
  "IR     = IC x sqrt(N)        [Grinold]<br/>"
  "breakeven win rate = (S + cost) / (S + T)", "code")

H2("Horizon sets the cost bar")
TBL([["horizon", "sigma (MNQ $)", "cost", "IC needed"],
     ["10 min", "$46", "$1.83", "0.040"],
     ["1 hour", "$118", "$1.83", "0.016"],
     ["4 hours", "$354", "$1.83", "0.005"],
     ["1 day", "$428", "$1.83", "0.0043"],
     ["1 week", "$957", "$1.83", "0.0019"]],
    [30 * mm, 36 * mm, 26 * mm, 32 * mm],
    align={1: "RIGHT", 2: "RIGHT", 3: "RIGHT"})
P("Book imbalance measures IC 0.0425 -- eight times what a daily horizon "
  "needs. It fails only because it decays to nothing inside five "
  "minutes. <b>A weak, persistent signal beats a strong, fleeting "
  "one.</b>", "body")

H2("Breadth sets the IC you need")
TBL([["independent bets / year", "IC needed for IR = 1.0"],
     ["25", "0.200"],
     ["250  (one asset, daily)", "0.063"],
     ["2,500", "0.020"],
     ["25,000  (500-name cross-section)", "0.006"]],
    [66 * mm, 54 * mm], align={1: "RIGHT"})
P("Professionals do not find bigger ICs. They find the same tiny ICs and "
  "multiply by a much larger square root of N. Everything in this repo "
  "is single-asset time series, which is the smallest N available.", "body")

H2("Instrument, measured")
TBL([["instrument", "sigma 1h", "spread+comm", "budget", "margin"],
     ["MNQ", "$118", "$1.83", "64.3x", "$100"],
     ["MGC", "$106", "$2.33", "45.5x", "$300"],
     ["MES", "$60", "$2.58", "23.1x", "$200"],
     ["ZB 30y", "$158", "$33.75", "4.7x", "$4,200"],
     ["ZN 10y", "$83", "$18.12", "4.6x", "$2,100"]],
    [30 * mm, 26 * mm, 32 * mm, 26 * mm, 26 * mm],
    align={1: "RIGHT", 2: "RIGHT", 3: "RIGHT", 4: "RIGHT"})
P("'Budget' is how many round trips one hour of movement pays for. MNQ "
  "ranks first of ten measured instruments. Commission-per-tick -- the "
  "metric that recommended Treasuries -- ranks the table almost exactly "
  "backwards because it ignores the spread.", "body")

F.append(PageBreak())

# ========================= PART 6 =========================
H1("Part 6 -- The infrastructure")
TBL([["component", "role"],
     ["causal_engine.py",
      "the reference executor. Every fill archetype (resting limit, "
      "stop, market), gap-aware stops, lockouts, both level definitions. "
      "Validated 29/29 against the live bot."],
     ["book_ic.py + selftest",
      "IC harness for order-book features. Self-test plants an edge and "
      "a six-hour feed hole; must find one and not leak the other."],
     ["book_maker.py + selftest",
      "queue model for passive fills. Four hand-checkable cases."],
     ["hft_ic.py", "order flow as a predictor at 5-60 second bars."],
     ["fusion_ceiling.py",
      "LightGBM ceiling across data types, purged CV, overlap-corrected "
      "noise floor."],
     ["accuracy_curve.py",
      "measured target-first rate minus the random-walk expectation, "
      "across every bracket geometry."],
     ["tick_constraint.py / treasury_check.py",
      "instrument ranking by movement per unit of cost."],
     ["data_audit.py",
      "tape versus an independent vendor, per contract."],
     ["HYPOTHESIS_LEDGER.md",
      "append-only record so no search repeats a corpse."]],
    [46 * mm, 112 * mm], size=8.2)

H1("Part 7 -- What is closed")
TBL([["family", "verdict"],
     ["Impulse-pullback, all variants", "NULL"],
     ["Mean reversion, VWAP, opening range, squeeze, gaps", "NULL"],
     ["Volume spikes, calendar, hour-of-day", "NULL"],
     ["Cross-market lead-lag (15 markets)", "NULL"],
     ["Trailing-stop exits (13 rules)", "NULL"],
     ["AND-combos (1.38B configs)", "NULL, and anti-persistent"],
     ["COT positioning, daily GEX", "NULL"],
     ["Back-of-queue market making", "NEGATIVE, maker path closed"],
     ["Leg-grammar cell", "REAL but an order of magnitude too small"],
     ["Book imbalance", "REAL: IC 0.0425, 44x floor, 1/12 of the spread"],
     ["Order flow 5-60s", "REAL: 20x floor, 4-8x under cost"],
     ["Alt data, multi-day", "1 of 180 = chance"]],
    [86 * mm, 72 * mm], size=8.4)
P("Three things in this project's history have shown genuine predictive "
  "information. All three are too small to pay the toll. Everything else "
  "showed nothing at all.", "body")

H1("Part 8 -- What would change the answer")
TBL([["lever", "worth", "available?"],
     ["Perfect execution (free, instant, exact)", "+$2.27/trade",
      "no -- and still short of the $2.81 gap"],
     ["Membership commission", "+$0.97/trade", "yes"],
     ["Instrument choice", "1.5-4x", "already optimal"],
     ["Longer horizon", "20x lower cost bar", "YES -- untested"],
     ["Cross-sectional breadth", "10-100x less IC needed", "YES -- untested"],
     ["Mechanism-driven hypotheses", "changes the prior entirely",
      "YES -- barely used"],
     ["Portfolio netting", "70-90% cost reduction", "needs capital"],
     ["More capital", "fixes the binding constraint", "the real answer"]],
    [58 * mm, 42 * mm, 58 * mm], size=8.2)

P("<b>The constraint is not the search method, the tooling, the broker, "
  "the instrument, or the cost structure.</b> Those have all been "
  "measured and all are either favourable or nearly optimal. The "
  "constraint is that one micro contract carries $7,160 of annual "
  "volatility against a $4,000 account -- 179% -- so the minimum "
  "tradeable position is roughly twelve times larger than a "
  "professionally sized one. No strategy fixes that.", "body")

doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=20 * mm,
                        rightMargin=20 * mm, topMargin=18 * mm,
                        bottomMargin=22 * mm,
                        title="The Search Model",
                        author="FutureTradingBot research")
doc.build(F, onFirstPage=foot, onLaterPages=foot)
print("wrote", OUT, os.path.getsize(OUT), "bytes")
