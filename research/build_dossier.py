"""Build the research dossier PDF: everything searched, five months."""
from __future__ import annotations

import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "RESEARCH_DOSSIER.pdf")

INK = colors.HexColor("#111318")
MUTE = colors.HexColor("#5b6472")
RULE = colors.HexColor("#d4d8e0")
BAND = colors.HexColor("#f2f4f8")
GOOD = colors.HexColor("#1a7f4b")
BAD = colors.HexColor("#b4232a")
ACC = colors.HexColor("#1f4e9c")

ss = getSampleStyleSheet()


def S(name, **kw):
    base = dict(fontName="Helvetica", fontSize=8.6, leading=11.6,
                textColor=INK, spaceAfter=0)
    base.update(kw)
    return ParagraphStyle(name, **base)


TITLE = S("t", fontName="Helvetica-Bold", fontSize=21, leading=24,
          textColor=INK, spaceAfter=2)
SUB = S("s", fontSize=10, leading=13, textColor=MUTE, spaceAfter=12)
H1 = S("h1", fontName="Helvetica-Bold", fontSize=12.5, leading=15,
       textColor=ACC, spaceBefore=13, spaceAfter=5)
H2 = S("h2", fontName="Helvetica-Bold", fontSize=9.4, leading=12,
       textColor=INK, spaceBefore=8, spaceAfter=3)
BODY = S("b", spaceAfter=5)
SMALL = S("sm", fontSize=7.8, leading=10, textColor=MUTE)
CELL = S("c", fontSize=7.7, leading=9.6)
CELLB = S("cb", fontSize=7.7, leading=9.6, fontName="Helvetica-Bold")
NUM = S("n", fontSize=7.7, leading=9.6, alignment=2)
HEAD = S("hd", fontSize=7.4, leading=9.2, fontName="Helvetica-Bold",
         textColor=colors.white)


def P(t, st=BODY):
    return Paragraph(t, st)


def table(data, widths, align_right=(), head=True, size=7.7):
    rows = []
    for ri, row in enumerate(data):
        out = []
        for ci, c in enumerate(row):
            if ri == 0 and head:
                out.append(Paragraph(str(c), HEAD))
            else:
                st = NUM if ci in align_right else CELL
                out.append(Paragraph(str(c), st))
        rows.append(out)
    t = Table(rows, colWidths=widths, repeatRows=1 if head else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, RULE),
    ]
    if head:
        style += [("BACKGROUND", (0, 0), (-1, 0), INK),
                  ("LINEBELOW", (0, 0), (-1, 0), 0, colors.white)]
        for r in range(2, len(rows), 2):
            style.append(("BACKGROUND", (0, r), (-1, r), BAND))
    t.setStyle(TableStyle(style))
    return t


def bignum(items):
    """A row of oversized headline figures."""
    cells, sty = [], [("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                      ("TOPPADDING", (0, 0), (-1, -1), 7),
                      ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]
    for i, (v, lab, col) in enumerate(items):
        cells.append(Paragraph(
            f'<font size="17" color="{col}"><b>{v}</b></font><br/>'
            f'<font size="7" color="#5b6472">{lab}</font>',
            S("bn", alignment=TA_CENTER, leading=20)))
        sty.append(("BACKGROUND", (i, 0), (i, 0), BAND))
    w = (170 * mm) / len(items)
    t = Table([cells], colWidths=[w] * len(items))
    t.setStyle(TableStyle(sty))
    return t


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 6.8)
    canvas.setFillColor(MUTE)
    canvas.drawString(20 * mm, 11 * mm,
                      "FutureTradingBot — research dossier")
    canvas.drawRightString(190 * mm, 11 * mm, f"page {doc.page}")
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.3)
    canvas.line(20 * mm, 14 * mm, 190 * mm, 14 * mm)
    canvas.restoreState()


def build():
    doc = SimpleDocTemplate(
        OUT, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=16 * mm, bottomMargin=18 * mm,
        title="FutureTradingBot - Research Dossier",
        author="Research log")
    E = []
    W = 170 * mm

    # ---------------------------------------------------------- cover
    E.append(P("What Was Searched", TITLE))
    E.append(P("Five months of systematic strategy research on CME futures "
               "&mdash; the complete record of every family tested, how "
               "large each search was, and what it returned.", SUB))
    E.append(bignum([
        ("27.55B", "configurations evaluated", ACC),
        ("48", "families closed", INK),
        ("23", "markets", INK),
        ("1", "survivor", GOOD),
    ]))
    E.append(Spacer(1, 9))
    E.append(P(
        "Every number in this document is read from the repository's own "
        "result files and its append-only hypothesis ledger. Nothing is "
        "estimated. The single most important conclusion is not any "
        "individual result but the arithmetic in section 5: <b>a search of "
        "27.55 billion configurations demands 7.73 sigma of evidence, and "
        "nothing in finance clears that bar.</b> The largest searches in "
        "this project could not have found a real edge even while looking "
        "directly at one.", BODY))

    # ------------------------------------------------- 1. the scale
    E.append(P("1 &nbsp; The scale", H1))
    E.append(table([
        ["Campaign", "Configurations", "Cleared gate", "Survived"],
        ["Megatick &mdash; tick-event configurations", "26,131,683,248",
         "&mdash;", "<font color='#b4232a'><b>0</b></font>"],
        ["FX / AND-combos of technical features", "1,379,701,482",
         "&mdash;", "<font color='#b4232a'><b>0</b></font>"],
        ["Feature search (FSEARCH + F2, 6 markets)", "33,142,022",
         "13,785,856", "<font color='#b4232a'><b>146, then 0</b></font>"],
        ["Needle &mdash; 1.2M strategies, all 8 contracts", "1,209,600",
         "&mdash;", "<font color='#b4232a'><b>0</b></font>"],
        ["Structural strategies (103,680 space)", "81,348",
         "&mdash;", "<font color='#b4232a'><b>0</b></font>"],
        ["Targeted searches (final phase)", "13,433",
         "&mdash;", "<font color='#1a7f4b'><b>1</b></font>"],
        ["<b>TOTAL</b>", "<b>27,545,831,133</b>", "", "<b>1</b>"],
    ], [68 * mm, 36 * mm, 34 * mm, 32 * mm], align_right=(1, 2, 3)))
    E.append(Spacer(1, 4))
    E.append(P(
        "The feature-search family alone scanned 33.1 million candidates; "
        "13.8 million cleared an in-sample gate, 1.28 million also paid on "
        "a held-out 40%, and <b>146 survived every quarter</b> &mdash; of "
        "which none survived a shuffled control. That funnel is the shape "
        "of the whole project.", SMALL))

    # ------------------------------------------- 2. the brute-force era
    E.append(P("2 &nbsp; Phase one &mdash; the brute-force era "
               "(35 ledger families)", H1))
    E.append(P(
        "An append-only ledger recorded each family so no later search "
        "would rediscover a corpse. Verdicts are quoted from it.", SMALL))
    E.append(Spacer(1, 4))
    led = [["#", "Family", "Scale", "Verdict"]]
    for n, fam, scale, verd in [
        ("1", "Impulse-pullback, all variants", "1000s of configs", "NULL"),
        ("2-7", "Mean reversion, VWAP, opening range, squeeze, gap, "
                "volume spike", "grids", "NULL"),
        ("8", "Hour-of-day / weekday / weekday x hour", "grid", "NULL"),
        ("9", "Cross-market lead-lag", "grid", "NULL"),
        ("10", "Order-flow imbalance (trade prints)", "grid", "NULL"),
        ("11-13", "Position sizing, calendar effects, sweeps/absorption",
         "grids", "NULL"),
        ("14", "Trailing-stop exits (13 rules)", "full", "NULL"),
        ("15", "AND-combos of technical features", "1.38B configs", "NULL"),
        ("16", "Daily GEX / options positioning", "daily", "NULL"),
        ("17", "Book imbalance", "IC study",
         "<font color='#1a7f4b'>REAL, small</font>"),
        ("18", "COT / positioning", "weekly", "NULL"),
        ("19", "Selection-by-train-score as a method", "1.38B",
         "<font color='#b4232a'>HARMFUL</font>"),
        ("20", "FX impulse at 97% lower costs", "full sim", "NULL"),
        ("21", "Leg-grammar conditional cells", "~750 cells/scale",
         "RETRACTED &mdash; tape artifact"),
        ("22", "Back-of-queue market making", "full day",
         "NEGATIVE &mdash; maker path closed"),
        ("23", "<b>Megatick tick-event configurations</b>",
         "<b>26,131,683,248</b>", "NULL"),
        ("24", "Selectivity: are runaway swings visible in advance?",
         "13 features x 5 quintiles",
         "<font color='#1a7f4b'>REAL, far too small</font>"),
        ("25", "Exit targets instead of waiting for the turn",
         "45 combinations", "NULL"),
        ("26", "Brackets: first-touch on the real tick path",
         "56 shapes x 2 directions", "NULL &mdash; decisive"),
        ("27", "Cost reduction by switching instrument (bonds)", "&mdash;",
         "WRONG &mdash; withdrawn"),
        ("28", "CME order-book data as the remaining hope", "&mdash;",
         "CLOSED without buying"),
        ("29", "Structural targets: prior swing highs/lows as attractors",
         "268k / 125k / 46k trades", "REAL but INVERTED"),
        ("30", "103,680 structural strategies", "81,348 scored", "NULL"),
        ("31", "Symmetric-barrier directional asymmetry",
         "+/-24, 48, 96 ticks", "NULL &mdash; retracted same session"),
        ("32", "conf_len &mdash; top result of the 103,680 search",
         "8 strategies x 2 splits", "NULL &mdash; pure selection noise"),
        ("33", "LOCATION: ten pre-named destinations", "14 rows x 2 splits",
         "NULL"),
        ("34", "Needle: 1.2M strategies, pass in ALL 8 contracts",
         "1,209,600 x 2 arms", "NULL &mdash; 123x worse than control"),
        ("35", "<b>THE CEILING</b>: gradient-boosted model over the whole "
               "feature set", "4 horizons x 2 arms, purged",
         "<b>ZERO</b> &mdash; bounds every other result"),
    ]:
        led.append([n, fam, scale, verd])
    E.append(table(led, [12 * mm, 71 * mm, 36 * mm, 51 * mm]))

    E.append(PageBreak())

    # --------------------------------- 3. the targeted phase
    E.append(P("3 &nbsp; Phase two &mdash; 13 targeted searches", H1))
    E.append(P(
        "After the brute-force era closed, the method changed: far fewer "
        "configurations, each aimed at a region the arithmetic said could "
        "work, every one reporting the smallest effect it could have "
        "detected. Thirteen searches, 13,433 configurations in total.", SMALL))
    E.append(Spacer(1, 4))
    E.append(table([
        ["Search", "What it tested", "Configs", "Result"],
        ["cadence", "Trade the 18-hour signal once instead of 400 times",
         "24", "&minus;$573 &rarr; <b>+$246/wk</b>"],
        ["perm400", "20 independent permutations at h=400", "21",
         "<b>p = 0.048</b>, IC 3.0 se"],
        ["tradestats", "Trade-level statistics on one micro", "3",
         "Edge sat in the WEAK signals"],
        ["riskcap", "Does it survive a hard dollar stop?", "8",
         "Survived (&minus;18%), DD unchanged"],
        ["<b>ablate</b>", "Which feature family carries the result?", "6",
         "<font color='#b4232a'><b>KILLED IT</b></font>"],
        ["xsec", "Cross-sectional ranking, 30 min to 3 days", "168",
         "0 winners, max |t| 1.64"],
        ["wide", "18 markets x 3 horizons, cross-market ML", "108",
         "0 of 54; NG 4.4 sigma but $58/wk"],
        ["trend", "Trend following, 4 to 12 week holds", "48",
         "Calmar 1.08 &mdash; MDE $645 vs $271"],
        ["lowdd", "Max $2,000 drawdown at 20 micros", "72",
         "0 of 72; floor was $15,504"],
        ["mindd", "The full drawdown frontier", "144",
         "Every point below its noise floor"],
        ["daily_stats", "Daily marks at 2 minis", "2",
         "<font color='#b4232a'>Sign FLIPPED</font> on longer data"],
        ["lowfreq", "Calendar, session, COT, volatility regime", "318",
         "<font color='#1a7f4b'><b>1 survivor</b></font>"],
        ["brackets_wide", "45% win at 1:2, daily-scale brackets", "12,672",
         "2 met the brief, 0 survived"],
        ["fib_verify", "Independent rebuild of a handed-over strategy", "6",
         "<font color='#b4232a'>Shuffle BEAT it</font>"],
    ], [24 * mm, 70 * mm, 18 * mm, 58 * mm], align_right=(2,)))

    # ------------------------------------- 4. the survivor
    E.append(P("4 &nbsp; The one survivor &mdash; overnight drift", H1))
    E.append(P(
        "Buy the regular-session close, sell the next regular-session "
        "open. One trade a day, no intraday exposure.", BODY))
    E.append(table([
        ["Market", "$/trade", "t", "Win rate", "Same market, INTRADAY"],
        ["Gold (GC)", "+$38.2", "2.58", "58.9%", "&minus;1.12"],
        ["Nasdaq (NQ)", "+$29.2", "2.01", "56.5%", "+0.04"],
        ["Copper (HG)", "+$10.3", "1.60", "53.0%", "&minus;0.73"],
        ["S&amp;P (ES)", "+$10.6", "1.49", "56.1%", "+0.60"],
        ["Russell (RTY)", "+$3.4", "0.87", "54.1%", "&minus;0.11"],
    ], [34 * mm, 26 * mm, 20 * mm, 28 * mm, 62 * mm],
        align_right=(1, 2, 3, 4)))
    E.append(Spacer(1, 5))
    E.append(table([
        ["Pooled book", "$/week", "t", "Win rate", "Max DD", "Calmar"],
        ["Equity + metals, OVERNIGHT", "<b>$304</b>", "<b>2.20</b>",
         "57.2%", "$10,282", "1.54"],
        ["the same book, intraday", "&minus;$54", "&minus;0.37", "53.1%",
         "$16,136", "&minus;0.18"],
    ], [56 * mm, 22 * mm, 20 * mm, 22 * mm, 26 * mm, 24 * mm],
        align_right=(1, 2, 3, 4, 5)))
    E.append(Spacer(1, 5))
    E.append(P(
        "<b>Why this one and nothing else.</b> It is the only result in "
        "five months with all three properties: a published mechanism "
        "rather than a found pattern; agreement across correlated markets "
        "(the test that killed the NQ breakout, which scored 3.86 sigma on "
        "Nasdaq and 0.17 on the S&amp;P); and a control that fails in the "
        "<i>right</i> direction &mdash; the same markets are flat to "
        "negative during the day session. It is also stable year by year: "
        "$310, $311 and $304 per week in 2024, 2025 and 2026, so it is not "
        "a recent artifact.", BODY))
    E.append(P(
        "<b>What it is not.</b> t = 2.20 against a 4.19 sigma bar for the "
        "318 configurations it came from. Four years is not enough to "
        "settle it. And because it holds positions overnight, it cannot be "
        "run inside a funded account, which requires flat by the close.",
        BODY))

    E.append(PageBreak())

    # ------------------------------------ 5. the arithmetic
    E.append(P("5 &nbsp; The finding that reframes all of it", H1))
    E.append(P(
        "The significance bar rises with the number of things tried, as "
        "the square root of twice the log of the count. Every extra "
        "configuration raises the evidence bar for <i>all</i> of them.",
        BODY))
    E.append(table([
        ["Search size", "Bar to clear", "Would it accept a real 4.4 sigma edge?"],
        ["54 configurations", "3.62 sigma",
         "<font color='#1a7f4b'><b>YES</b></font>"],
        ["12,672 configurations", "5.15 sigma",
         "<font color='#b4232a'>no</font>"],
        ["1,209,600 configurations", "6.32 sigma",
         "<font color='#b4232a'>no</font>"],
        ["26,131,683,248 configurations", "<b>7.73 sigma</b>",
         "<font color='#b4232a'><b>NO</b></font>"],
    ], [52 * mm, 38 * mm, 80 * mm], align_right=(1,)))
    E.append(Spacer(1, 5))
    E.append(P(
        "Natural gas measured <b>4.36 sigma</b> in this project &mdash; the "
        "strongest statistical result found. Discovered inside a 54-config "
        "search it clears comfortably. The identical result inside the "
        "26-billion sweep <b>fails</b>. Same signal, same data, same "
        "strength; accepted or rejected purely by how much else was looked "
        "at alongside it.", BODY))
    E.append(P(
        "<b>Brute force did not merely waste time. It destroyed the "
        "ability to detect an edge.</b> Twenty-six billion configurations "
        "could not have found natural gas even while looking straight at "
        "it. Thirteen thousand aimed configurations found more real signal "
        "than twenty-seven billion unaimed ones.", BODY))

    # ------------------------------- 6. second finding
    E.append(P("6 &nbsp; The second blind spot &mdash; measured power", H1))
    E.append(P(
        "Edges of known size were planted in the engine's own data and it "
        "was asked to find them:", BODY))
    E.append(table([
        ["Planted edge", "Worth, per week", "Detected"],
        ["+0.05 round trips / trade", "~$80", "<b>0%</b>"],
        ["+0.50 round trips / trade", "~$800", "<b>0%</b>"],
        ["+2.00 round trips / trade", "~$3,200", "60%"],
    ], [58 * mm, 46 * mm, 66 * mm], align_right=(1, 2)))
    E.append(Spacer(1, 5))
    E.append(P(
        "An edge worth <b>$800 a week was invisible 100% of the time</b>. "
        "So “nothing found” never meant “nothing is there” "
        "&mdash; it meant “nothing large enough for this search to "
        "see”. The repository's own calibration module had said so all "
        "along: <i>“its silence was never evidence of absence; it was "
        "evidence of no power.”</i> Every search in the final phase "
        "now prints that number beside its result, found or not.", BODY))

    # ------------------------------- 7. cost
    E.append(P("7 &nbsp; Why the short-horizon work could never pay", H1))
    E.append(table([
        ["Holding period", "Average NQ move", "Share eaten by $1.99 cost",
         "Must forecast"],
        ["1 minute", "$36", "5.5%", "5.5% of the move"],
        ["5 minutes", "$81", "2.4%", "2.4%"],
        ["30 minutes", "$195", "1.0%", "1.0%"],
        ["<b>2 hours</b>", "<b>$371</b>", "<b>0.54%</b>",
         "<b>0.54%</b>"],
    ], [38 * mm, 36 * mm, 48 * mm, 48 * mm], align_right=(1, 2, 3)))
    E.append(Spacer(1, 4))
    E.append(P(
        "Essentially all 27.5 billion configurations were tested between "
        "15 seconds and 50 minutes &mdash; the region where the toll is "
        "largest. Cost is fixed per trade while the move grows with time, "
        "so the problem was never commission. It was trading quickly. "
        "Execution work (cheapest broker, limit orders, no slippage) takes "
        "$1.99 down to about $1.44 against a break-even of $0.70: still "
        "twice over, and a dead end in that direction.", BODY))

    # ------------------------------- 8. what is left
    E.append(P("8 &nbsp; What remains", H1))
    E.append(table([
        ["Lane", "Status", "What would settle it"],
        ["Short-horizon price patterns", "<font color='#b4232a'>Closed</font>",
         "27.5B configurations. Decisively dead."],
        ["Maker / passive fills", "<font color='#b4232a'>Closed</font>",
         "6.6% measured fill rate on MNQ."],
        ["Cross-sectional ranking", "<font color='#b4232a'>Closed</font>",
         "168 configs with power behind the null."],
        ["Cross-market ML at 18 hours", "<font color='#b4232a'>Closed</font>",
         "A shuffled target out-earned it."],
        ["Positioning (COT, 9 years)", "<font color='#b4232a'>Closed</font>",
         "Shifted control beat the real signal."],
        ["Trend following", "Unresolved",
         "Needs ~15 years; 4.2 on disk. Free download."],
        ["<b>Overnight drift</b>",
         "<font color='#1a7f4b'><b>Alive</b></font>",
         "<b>Testable to the 1990s with free daily data.</b>"],
    ], [48 * mm, 28 * mm, 94 * mm]))
    E.append(Spacer(1, 7))
    E.append(KeepTogether([
        P("The single next step", H2),
        P(
            "Three of the four remaining questions have the same answer: "
            "<b>long price history</b>. Trend following needs about fifteen "
            "years and has four. Overnight drift is testable back to the "
            "1990s. The Nasdaq breakout could be settled with daily data to "
            "2010. All three are free downloads rather than discoveries. "
            "After 27.55 billion configurations, the binding constraint is "
            "no longer ideas or compute &mdash; it is that two to four years "
            "of tape cannot tell a real effect from a lucky one.", BODY),
    ]))

    E.append(Spacer(1, 8))
    E.append(P(
        "Compiled from the repository's result files "
        "(CADENCE, PERM_H400, ABLATE_H400, XSEC, WIDE, TREND, LOWDD, MINDD, "
        "DAILY_STATS, LOWFREQ, BRACKETS_WIDE, FIB_VERIFY) and the "
        "append-only hypothesis ledger. Costs throughout are the measured "
        "$1.99 per MNQ round turn taken from real fills, never a "
        "hopeful figure.", SMALL))

    doc.build(E, onFirstPage=footer, onLaterPages=footer)
    print("wrote", OUT, os.path.getsize(OUT), "bytes")


if __name__ == "__main__":
    build()
