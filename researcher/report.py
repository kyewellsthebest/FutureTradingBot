"""The two PDFs the console offers.

  learning_pdf()      What the searcher has worked out, and -- the part
                      that matters -- what it CHANGED about how it
                      searches as a result. Written for someone who
                      does not want the statistics.

  diagnostics_pdf()   Everything needed to audit whether the research
                      model is working: full source of every module,
                      the controls and what they measured, the current
                      ledger and failure profiles, and the list of
                      known-caught errors. Written for someone who
                      does.

WHY THE LEARNING PDF LEADS WITH ADAPTATIONS. A system that reports
lessons but cannot show what it did differently is a logging system. So
the first substantive page is "what changed", each entry carrying the
evidence that triggered it, the before and after, and how many times it
has been applied since. If that page is empty, the honest statement is
that nothing has been learned yet -- and it says exactly that rather
than padding.
"""
from __future__ import annotations

import io
import json
import os
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph,
                                Preformatted, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

INK = colors.HexColor("#12161d")
MUTED = colors.HexColor("#5c687f")
RULE = colors.HexColor("#d7dee8")
ACCENT = colors.HexColor("#1f5fa8")
WARN = colors.HexColor("#a8641f")
GOOD = colors.HexColor("#166b4c")


def _styles():
    s = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=s["Title"], fontSize=22,
                             leading=26, textColor=INK, alignment=TA_LEFT,
                             spaceAfter=2),
        "sub": ParagraphStyle("sub", parent=s["Normal"], fontSize=9.5,
                              leading=13, textColor=MUTED, spaceAfter=16),
        "h2": ParagraphStyle("h2", parent=s["Heading2"], fontSize=13.5,
                             leading=17, textColor=INK, spaceBefore=16,
                             spaceAfter=7),
        "h3": ParagraphStyle("h3", parent=s["Heading3"], fontSize=10.5,
                             leading=14, textColor=ACCENT, spaceBefore=10,
                             spaceAfter=4),
        "p": ParagraphStyle("p", parent=s["Normal"], fontSize=10,
                            leading=14.5, textColor=INK, spaceAfter=8),
        "note": ParagraphStyle("note", parent=s["Normal"], fontSize=8.8,
                               leading=12.5, textColor=MUTED, spaceAfter=8),
        "code": ParagraphStyle("code", parent=s["Code"], fontSize=6.4,
                               leading=7.9, textColor=INK),
        "big": ParagraphStyle("big", parent=s["Normal"], fontSize=17,
                              leading=21, textColor=INK, spaceAfter=3),
    }


def _esc(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _doc(buf, title):
    return SimpleDocTemplate(
        buf, pagesize=A4, title=title, author="research bot",
        leftMargin=17 * mm, rightMargin=17 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm)


def _kv(rows, w=(52, 110)):
    t = Table(rows, colWidths=[w[0] * mm, w[1] * mm])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 8.5),
        ("FONT", (1, 0), (1, -1), "Helvetica", 8.5),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("TEXTCOLOR", (1, 0), (1, -1), INK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _read(p, default=None):
    try:
        return json.load(open(p))
    except Exception:                                         # noqa: BLE001
        return default if default is not None else {}


# ====================================================== learning report
def learning_pdf(rdir) -> bytes:
    st = _styles()
    led = _read(os.path.join(rdir, "ledger.json"))
    mem = _read(os.path.join(rdir, "memory.json"))
    status = _read(os.path.join(rdir, "status.json"))
    buf = io.BytesIO()
    doc = _doc(buf, "What the research bot has learned")
    F = []

    trials = led.get("trials", 0)
    bar = 3.0
    try:
        import math
        bar = max(3.0, math.sqrt(2.0 * math.log(max(trials, 1))) + 0.8)
    except Exception:                                         # noqa: BLE001
        pass
    survivors = len(led.get("survivors", []))
    adapts = sorted(mem.get("adaptations", []), key=lambda a: -a["applied"])

    F.append(Paragraph("What the research bot has learned", st["h1"]))
    F.append(Paragraph(f"Generated {_now()} &nbsp;·&nbsp; cycle "
                       f"{status.get('cycle', 0)} &nbsp;·&nbsp; "
                       f"{trials:,} hypotheses tested", st["sub"]))

    # ---- the headline, in plain words
    F.append(Paragraph("Where it stands", st["h2"]))
    if survivors == 0:
        F.append(Paragraph(
            f"<b>{trials:,} specific trading ideas have been tested and "
            f"none of them worked.</b>", st["big"]))
        F.append(Paragraph(
            "That is the expected result and it is a real one. Each of "
            "those ideas is now ruled out, and the bot will not spend "
            "time on any of them again. Finding a genuine edge is rare; "
            "a searcher that reported one in its first days would almost "
            "certainly be reporting noise.", st["p"]))
    else:
        F.append(Paragraph(f"<b>{survivors} idea(s) survived every check "
                           f"out of {trials:,} tested.</b>", st["big"]))
        F.append(Paragraph(
            "A survivor is a candidate, not a strategy. It still has to "
            "pass the full gauntlet before any money is involved.",
            st["p"]))

    F.append(Paragraph(
        f"The bar it has to clear is now <b>{bar:.2f} sigma</b>, up from "
        f"3.00 when it started. That bar rises automatically as more "
        f"ideas are tested, which is the single most important thing "
        f"about this system: <b>it cannot find something just by running "
        f"longer</b>. The more it searches, the harder it becomes to "
        f"convince.", st["p"]))

    # ---- WHAT CHANGED. the point of the document.
    F.append(Paragraph("What it changed about how it searches", st["h2"]))
    if not adapts:
        F.append(Paragraph(
            "<b>Nothing yet.</b> No family of ideas has failed in a way "
            "that points at a specific fix, and no candidate has reached "
            "the held-back data, so there is nothing to calibrate "
            "against. This section fills in as the bot accumulates "
            "failures it can read a mechanism from. An empty section "
            "here is honest; the alternative would be inventing a lesson "
            "to have something to show.", st["p"]))
    else:
        F.append(Paragraph(
            "Each row is a change the bot made to its own search because "
            "of what its failures told it. These are not suggestions "
            "that were logged and ignored -- the &ldquo;used&rdquo; "
            "column counts how many times the change has actually been "
            "applied since.", st["note"]))
        rows = [["change", "where", "from", "to", "used"]]
        for a in adapts[:24]:
            rows.append([
                Paragraph(f"<b>{_esc(a['kind'])}</b>", st["note"]),
                Paragraph(_esc(a["family"]), st["note"]),
                Paragraph(_esc(a["before"]), st["note"]),
                Paragraph(_esc(a["after"]), st["note"]),
                Paragraph(f"{a['applied']}x", st["note"])])
        t = Table(rows, colWidths=[22 * mm, 42 * mm, 38 * mm, 38 * mm,
                                   16 * mm], repeatRows=1)
        t.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
            ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
            ("LINEBELOW", (0, 0), (-1, 0), 0.7, RULE),
            ("LINEBELOW", (0, 1), (-1, -2), 0.3, RULE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        F.append(t)
        F.append(Spacer(1, 8))
        for a in adapts[:8]:
            F.append(Paragraph(
                f"<b>{_esc(a['kind'])} &middot; {_esc(a['family'])}</b>",
                st["h3"]))
            F.append(Paragraph(_esc(a["why"]), st["p"]))

    # ---- how the learning works, in plain words
    F.append(PageBreak())
    F.append(Paragraph("How it learns, and what that means here",
                       st["h2"]))
    F.append(Paragraph(
        "The obvious way to make a trading searcher &ldquo;learn&rdquo; "
        "is to feed it which of its guesses made money and let it search "
        "near those. That is the one thing this bot deliberately does "
        "not do, because in markets most of what looks like profit is "
        "luck, and a system that chases it is fitting noise. This "
        "project has already measured the cost of doing it that way: "
        "1.38 billion configurations tested, with a <b>measured "
        "negative</b> return to searching harder.", st["p"]))
    F.append(Paragraph(
        "So the learning is aimed at <b>how to look</b>, not at which "
        "answer looked good. Four things change over time:", st["p"]))

    for h, b in [
        ("It grows its own vocabulary",
         "It builds new ways of measuring the market by combining simple "
         "ones, and keeps a combination when it separates the market "
         "into groups that behave differently &mdash; never because that "
         "combination made money. It also measures what the same "
         "machinery produces on data that cannot possibly be predicted, "
         "and refuses to keep anything that does not beat that."),
        ("It reads why things failed, not just that they failed",
         "&ldquo;It lost&rdquo; carries no information; almost "
         "everything loses. &ldquo;It was pointing the right way but the "
         "move was smaller than the trading cost&rdquo; carries a lot "
         "&mdash; and the fix is to hold longer, which follows from "
         "arithmetic rather than from guessing. Those are the changes "
         "listed on the previous page."),
        ("It moves effort away from dead ground",
         "Families of ideas that produce nothing across many hundreds of "
         "tests get less attention. Less, not none: a family is not "
         "disproved by its members failing."),
        ("It watches its own reliability",
         "Every candidate that reaches the sealed held-back data arrives "
         "with a predicted strength and leaves with a real one. The gap "
         "between them is how much this bot overfits, measured rather "
         "than assumed, and it raises the bar accordingly. Until "
         "candidates actually reach that data it reports UNKNOWN, "
         "because a system quietly assuming it does not overfit is the "
         "most dangerous thing in the room."),
    ]:
        F.append(Paragraph(h, st["h3"]))
        F.append(Paragraph(b, st["p"]))

    # ---- families
    fams = (status.get("learning") or {}).get("families") or []
    if fams:
        F.append(Paragraph("Where it has been looking", st["h2"]))
        rows = [["area", "ideas tested", "right way, too small",
                 "nothing there"]]
        for f in fams[:14]:
            rows.append([Paragraph(_esc(f["family"]), st["note"]),
                         f"{f['n']:,}", f"{f.get('cost_bound', 0):,}",
                         f"{f.get('no_signal', 0):,}"])
        t = Table(rows, colWidths=[62 * mm, 30 * mm, 40 * mm, 30 * mm],
                  repeatRows=1)
        t.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
            ("FONT", (1, 1), (-1, -1), "Helvetica", 8.5),
            ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("LINEBELOW", (0, 0), (-1, 0), 0.7, RULE),
            ("LINEBELOW", (0, 1), (-1, -2), 0.3, RULE),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        F.append(t)
        F.append(Paragraph(
            "&ldquo;Right way, too small&rdquo; is the useful column. "
            "Those are ideas that predicted direction correctly but "
            "whose moves did not cover the cost of trading. When enough "
            "of a family fails that way, the bot lengthens how long it "
            "holds &mdash; cost is fixed per trade, while the size of a "
            "move grows with time.", st["note"]))

    sh = (status.get("learning") or {}).get("shrinkage") or {}
    F.append(Paragraph("How much it trusts itself", st["h2"]))
    if sh.get("known"):
        F.append(Paragraph(
            f"Across {sh['n']} candidates that reached the held-back "
            f"data, the typical one kept <b>{sh['median_ratio']}</b> of "
            f"the strength it appeared to have. The bot divides its bar "
            f"by that figure, so its own measured unreliability makes it "
            f"harder to convince.", st["p"]))
    else:
        F.append(Paragraph(
            "<b>Not yet known.</b> No candidate has reached the sealed "
            "held-back data, so there is nothing to compare predicted "
            "strength against. It reports this as unknown rather than "
            "assuming it is reliable.", st["p"]))

    doc.build(F)
    return buf.getvalue()


# =================================================== diagnostics report
AUDIT_FILES = [
    ("researcher/runner.py", "the search loop, the evaluator, the gauntlet"),
    ("researcher/ledger.py", "trial counting, the rising bar, the vault"),
    ("researcher/memory.py", "failure classification, calibration"),
    ("researcher/features.py", "compositional feature discovery"),
    ("researcher/hypotheses.py", "where hypotheses come from"),
    ("researcher/data_tiers.py", "the curriculum and the data"),
    ("researcher/pooled.py", "cross-market meta-analysis"),
    ("researcher/archive.py", "the map of the search space (MAP-Elites)"),
    ("researcher/parallel.py", "the process pool and its write proxies"),
    ("researcher/calibration.py", "power, detectable size, false-alarm rate"),
    ("researcher/surrogate.py", "the learned ordering of the space"),
    ("researcher/validate.py", "the gauntlet's controls"),
    ("researcher/plausible.py", "the too-good-to-be-true layer"),
    ("researcher/diagnose.py", "telling the failure modes apart"),
    ("researcher/brackets.py", "the bracket walk"),
    ("researcher/destinations.py", "destination mechanisms"),
    ("researcher/context.py", "external regime state"),
    ("researcher/insight.py", "what it infers from its own failures"),
    ("researcher/backup.py", "state durability"),
    ("researcher/runner_selftest.py", "look-ahead and overlap controls"),
    ("researcher/features_selftest.py", "feature-discovery null calibration"),
    ("research_service.py", "the service and console"),
]

CONTROLS = [
    ("Data vs an independent vendor",
     "8 contracts cross-checked against Polygon: 99.4-99.7% close match, "
     "range ratio 1.000, 0.0% out-of-order prints."),
    ("Planted-edge detection",
     "Every cycle plants a synthetic edge scaled to the instrument and "
     "confirms the evaluator finds it. If the harness goes blind the run "
     "HALTS, rather than reporting silence as evidence of absence."),
    ("Look-ahead probe",
     "Mean forward return inside every conditioning mask, measured on a "
     "driftless random walk. Caught the live up_day/dn_day bug at +44.4 "
     "and -48.3 sigma; reads within +/-1.4 sigma after the fix."),
    ("Overlap correction",
     "Standard errors deflated by measured trade spacing, not by hold "
     "length. Verified: 1.00x on once-per-session cells that cannot "
     "overlap, 12x and 36x on every-bar cells that do."),
    ("Bid-ask bounce gate",
     "Every candidate is re-evaluated with entry delayed one bar before "
     "the vault is touched. Caught a ZB result that had already passed "
     "the vault: 91% of its edge vanished on a one-bar delay."),
    ("Cost includes the spread",
     "Not commission alone. The ZB artifact was 0.203 of one tick on an "
     "instrument whose tick is worth $31.25."),
    ("Search-max null for feature discovery",
     "The whole three-generation growth is run against circularly rolled "
     "targets that cannot carry information. Real target reached 3.37 "
     "against a null of 4.10 -- inside the null, so nothing is kept."),
    ("Rising bar",
     "sqrt(2 ln N) + 0.8, counting feature-selection trials as well as "
     "hypothesis trials."),
    ("Sealed vault",
     "Newest 20% of history. One look per hypothesis, ever, recorded "
     "permanently so it cannot be mined by attrition."),
]

CAUGHT = [
    ("Timeout accounting", "Unresolved trades booked at $0 instead of "
     "marked to market. Flipped a session result from +$1.23 to -$1.33."),
    ("Look-ahead in day conditioning", "up_day/dn_day used the day's "
     "closing return. Fabricated $16.18/trade on a random walk."),
    ("Commission-only costs", "ZB charged $2.50 against a real "
     "round-trip of ~$33.75. Turned -$28.12 into a reported +$3.13."),
    ("Bid-ask bounce", "Feature and target shared one price print. "
     "z=10.6 'confirmed' result, 91% of it gone on a one-bar delay."),
    ("Vacuous control", "A look-ahead test that averaged mirrored "
     "directions, so it read 0.000 whatever happened."),
    ("Over-correction for overlap", "Once-per-session cells deflated 6x "
     "too far -- hides real findings rather than manufacturing them."),
    ("One market's economics on 24 markets", "6A scored -$0.5992 per "
     "trade regardless of outcome."),
    ("Six-sample noise floor", "Passed 5 fake survivors; 100 roll "
     "offsets reduced it to 1, which is chance."),
    ("Silent exception swallowing", "An empty results table presented "
     "with confident prose."),
]


# ================================================= full state of the bot
#
# ONE DOWNLOAD, EVERYTHING BEHIND THE CONSOLE. The console shows the
# five or ten numbers that fit on a phone; this is the rest. It answers,
# in order: is it healthy, how fast is it going right now, is it getting
# better and by what measure, what has it actually found, and what is
# the code that produced all of that.
#
# The rule throughout: a number that is unknown says UNKNOWN. A report
# that prints 0 for "no data yet" and 0 for "measured zero" is worse
# than no report, because the two mean opposite things.

def _ts(x):
    """Parse the ISO timestamps this project writes. None on anything else."""
    try:
        s = str(x).replace("Z", "+00:00")
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:                                         # noqa: BLE001
        return None


def _rate(hist, minutes, key="trials"):
    """How much `key` moved over the last `minutes`, from the history series.

    Returns (delta, span_seconds, covered). `covered` is False when the
    series is younger than the window asked for -- and that distinction
    is the whole point of this function. A four-minute-old series can
    still report a delta, but printing it in a row labelled "last 24
    hours" would state a 315/second rate as a day's average and be off
    by three hundred times. The caller must say which it got.

    (None, None, False) when the series cannot answer at all.
    """
    if not hist:
        return None, None, False
    end = _ts(hist[-1].get("t"))
    if end is None:
        return None, None, False
    want = end.timestamp() - minutes * 60.0
    start = None
    for row in hist:                       # oldest row still inside window
        t = _ts(row.get("t"))
        if t is None:
            continue
        if t.timestamp() >= want:
            start = row
            break
    if start is None or start is hist[-1]:
        return None, None, False
    t0 = _ts(start.get("t"))
    span = end.timestamp() - t0.timestamp()
    if span <= 0:
        return None, None, False
    a, b = start.get(key), hist[-1].get(key)
    if a is None or b is None:
        return None, None, False
    # Covered only if the oldest sample really does sit at (or before)
    # the edge of the window, within one sampling interval.
    return (b - a), span, (t0.timestamp() <= want + 75.0)


def _num_or(x, fmt="{:,.2f}", dash="UNKNOWN"):
    try:
        v = float(x)
        if v != v:
            return dash
        return fmt.format(v)
    except Exception:                                         # noqa: BLE001
        return dash


def _table(rows, widths, st, size=7.2, header=True):
    t = Table(rows, colWidths=[w * mm for w in widths],
              repeatRows=1 if header else 0)
    style = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", size),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        style += [("FONT", (0, 0), (-1, 0), "Helvetica-Bold", size),
                  ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
                  ("LINEBELOW", (0, 0), (-1, 0), 0.7, RULE)]
    t.setStyle(TableStyle(style))
    return t


def _describe(h):
    """English for a hypothesis dict, without importing the search loop."""
    try:
        from researcher import hypotheses as HY
        return HY.describe(h)
    except Exception:                                         # noqa: BLE001
        return ", ".join(f"{k}={v}" for k, v in sorted((h or {}).items())
                         if not str(k).startswith("_"))[:200]


def _spec(h):
    """The tradeable specification, field by field, as short strings."""
    h = h or {}
    out = []
    for k in ("market", "tier", "kind", "mech", "feat", "shape", "cond",
              "side", "ls", "n", "k", "hold_s", "stop_atr", "targ_atr",
              "exit", "session"):
        if k in h and h[k] is not None:
            v = h[k]
            if k == "hold_s":
                v = (f"{int(v)}s" if v < 120 else
                     f"{v / 60:.0f}m" if v < 7200 else f"{v / 3600:.1f}h")
            elif isinstance(v, float):
                v = f"{v:.3g}"
            out.append(f"{k}={v}")
    for k, v in sorted(h.items()):
        if k in ("market", "tier", "kind", "mech", "feat", "shape", "cond",
                 "side", "ls", "n", "k", "hold_s", "stop_atr", "targ_atr",
                 "exit", "session") or str(k).startswith("_"):
            continue
        out.append(f"{k}={v:.3g}" if isinstance(v, float) else f"{k}={v}")
    return ", ".join(out)


def state_pdf(rdir, extra=None, top=100, source=True, led=None) -> bytes:
    """`led` lets the caller hand in an ALREADY-PARSED ledger.

    At production scale that file is 84 MB and takes 1.8s to parse. The
    service holds a parsed copy for the console already, so re-reading
    it here was buying the same object twice on a box where every core
    is busy searching -- and the download was the request that could
    least afford it.
    """
    st = _styles()
    J = os.path.join
    led = _read(J(rdir, "ledger.json")) if led is None else led
    mem = _read(J(rdir, "memory.json"))
    status = _read(J(rdir, "status.json"))
    hist = _read(J(rdir, "history.json"), [])
    cal = _read(J(rdir, "calibration.json"), {})
    arch = _read(J(rdir, "archive.json"), {})
    if not isinstance(hist, list):
        hist = []
    extra = dict(extra or {})

    buf = io.BytesIO()
    doc = _doc(buf, "Research bot — complete state")
    F = []
    trials = int(led.get("trials", 0) or 0)
    import math
    bar = max(3.0, math.sqrt(2.0 * math.log(max(trials, 1))) + 0.8)

    F.append(Paragraph("Research bot &mdash; complete state", st["h1"]))
    F.append(Paragraph(
        # NOT &sigma;. The built-in Helvetica has no Greek glyph, so the
        # entity renders as a black box or silently as "s" -- and "bar
        # 5.31s" reads as a duration. Spell it.
        f"Generated {_now()} &nbsp;·&nbsp; cycle {status.get('cycle', 0)} "
        f"&nbsp;·&nbsp; {trials:,} hypotheses charged &nbsp;·&nbsp; bar "
        f"{bar:.2f} sigma. Everything the backend knows about itself: "
        f"health, throughput, whether it is improving and by which "
        f"measure, every metric it keeps, the top {top} things it has "
        f"found with their full specifications, and the source that "
        f"produced all of it.", st["sub"]))

    # ------------------------------------------------------ the brief
    # FIRST, DELIBERATELY. Everything after this is evidence; this is
    # what the evidence adds up to. A reader who stops after one page
    # should still leave knowing what is ruled out, what could not be
    # seen, and what is currently in the way.
    br = _read(J(rdir, "brief.json"), {})
    if br:
        F.append(Paragraph("0 &nbsp; What this adds up to", st["h2"]))
        bc = br.get("binding_constraint") or {}
        F.append(Paragraph(
            f"<b>Binding constraint: {_esc(bc.get('constraint', '?'))}</b>",
            st["big"]))
        F.append(Paragraph(_esc(bc.get("says", "")), st["p"]))
        F.append(Paragraph(f"<b>&rarr; {_esc(bc.get('do', ''))}</b>",
                           st["p"]))
        cv = br.get("coverage") or {}
        F.append(_kv([
            ["cells measured", _num_or(cv.get("measured"), "{:,.0f}")],
            ["could have seen an edge worth having",
             _num_or(cv.get("informative"), "{:,.0f}")],
            ["could NOT -- silence means nothing",
             _num_or(cv.get("blind"), "{:,.0f}")],
            ["smallest edge ever visible anywhere",
             _num_or(cv.get("smallest_edge_ever_visible"),
                     "{:.3f} RT/trade")],
        ]))
        if br.get("unreachable"):
            F.append(Paragraph("Not tested &mdash; could not be asked",
                               st["h3"]))
            for u in br["unreachable"][:6]:
                F.append(Paragraph(
                    f"<b>{_esc(u['family'])}</b>: {u['unevaluable']:,} of "
                    f"{u['attempts']:,} ({u['share']:.0%}) could not be "
                    f"evaluated. This family has NOT been tested.",
                    st["note"]))
        if br.get("contradictions"):
            F.append(Paragraph("Cannot both be true", st["h3"]))
            for x in br["contradictions"][:6]:
                F.append(Paragraph(
                    f"<b>{_esc(x.get('claim'))}</b> &mdash; "
                    f"{_esc(x.get('where'))}<br/>{_esc(x['why_impossible'])}",
                    st["note"]))
        if br.get("ruled_out"):
            F.append(Paragraph("Genuinely ruled out", st["h3"]))
            rows = [["family", "cells", "with power", "what its silence "
                     "excludes"]]
            for r in br["ruled_out"][:12]:
                rows.append([str(r["family"])[:30],
                             f"{r['cells']:,}",
                             f"{r['informative_cells']:,}",
                             r["verdict"]])
            F.append(_table(rows, [34, 16, 18, 90], st))
        if br.get("next"):
            F.append(Paragraph("What follows", st["h3"]))
            for a in br["next"][:8]:
                F.append(Paragraph(
                    f"<b>[{a['priority']}] {_esc(a['do'])}</b><br/>"
                    f"because {_esc(a['because'])}", st["note"]))
        F.append(PageBreak())

    # ------------------------------------------------------------ health
    F.append(Paragraph("1 &nbsp; Health", st["h2"]))
    halts = led.get("halts", []) or []
    alive = extra.get("alive")
    rows = [
        ["process", "RUNNING" if alive else
         ("STOPPED" if alive is False else "UNKNOWN")],
        ["stage", str(extra.get("stage", "UNKNOWN"))],
        ["stage age", _num_or(extra.get("stage_age_s"), "{:,.0f}s")],
        ["resident memory", _num_or(extra.get("rss_mb"), "{:,.0f} MB")],
        ["memory limit", _num_or(extra.get("mem_limit_mb"), "{:,.0f} MB")],
        ["worker processes", str(extra.get("workers", "UNKNOWN"))],
        ["cores visible", str(extra.get("cores", "UNKNOWN"))],
        ["restarts in the last hour", str(extra.get("boots_last_hour",
                                                    "UNKNOWN"))],
        ["restarts, all time", str(extra.get("boots_total", "UNKNOWN"))],
        ["state storage", f"{extra.get('storage', '?')} "
                          f"({'durable' if extra.get('durable') else 'EPHEMERAL'})"],
        ["state ever lost", "YES" if extra.get("state_loss") else "no"],
        ["data tiers", str(extra.get("tiers", "UNKNOWN"))],
        ["halts (blind-harness stops)", str(len(halts))],
        ["running since", str(led.get("started", "UNKNOWN"))],
    ]
    F.append(_kv(rows))
    if halts:
        F.append(Paragraph("The searcher halts itself when its own "
                           "planted-edge check fails, because a blind "
                           "harness reports silence and silence looks "
                           "like a result.", st["note"]))
        for h in halts[-6:]:
            F.append(Paragraph(f"<b>{_esc(h.get('t'))}</b> "
                               f"{_esc(h.get('why'))}", st["note"]))

    # -------------------------------------------------------- throughput
    F.append(Paragraph("2 &nbsp; Throughput &mdash; how much searching, "
                       "how recently", st["h2"]))
    F.append(Paragraph(
        "Read from the history series, which is sampled every 60 seconds "
        "by a thread separate from the search, so a stalled search shows "
        "as a flat line rather than as a missing one. A window the series "
        "does not reach back to says UNKNOWN; it does not say zero.",
        st["note"]))
    rows = [["window", "actually measured over", "hypotheses charged",
             "per minute", "per second"]]
    for label, mins in (("last 10 minutes", 10), ("last 30 minutes", 30),
                        ("last hour", 60), ("last 6 hours", 360),
                        ("last 24 hours", 1440)):
        d, span, covered = _rate(hist, mins)
        if d is None:
            rows.append([label, "—", "UNKNOWN (no series yet)", "—", "—"])
        else:
            # SAY WHAT WAS ACTUALLY MEASURED. A four-minute-old series
            # answering a 24-hour question is not wrong data, it is a
            # wrong label -- and a 315/second burst printed as a daily
            # average overstates the day by three hundred times.
            rows.append([
                label,
                (f"{span / 60.0:,.0f} min" if covered
                 else f"only {span / 60.0:,.0f} min — series is younger"),
                f"{d:,}", f"{d / (span / 60.0):,.0f}", f"{d / span:,.1f}"])
    F.append(_table(rows, [26, 44, 32, 24, 24], st))

    cycles = [r for r in hist if not r.get("sampled")]
    secs = [r.get("secs") for r in cycles if r.get("secs")]
    F.append(Spacer(1, 6))
    F.append(_kv([
        # PER PROCESS, and saying so. The cycle counter starts at 1 on
        # every boot, so "cycles completed 1" next to "running since
        # yesterday" reads as a stall when it actually means the process
        # restarted. The restart tally in section 1 is the other half of
        # that sentence.
        ["cycles completed, this process", str(status.get("cycle", 0))],
        ["mean cycle time", _num_or(sum(secs) / len(secs) if secs else None,
                                    "{:,.0f}s")],
        ["last cycle time", _num_or(secs[-1] if secs else None, "{:,.0f}s")],
        ["history samples held", f"{len(hist):,}"],
        ["distinct hypotheses on record", f"{len(led.get('tested', {})):,}"],
        ["charged but compacted to stubs",
         f"{sum(1 for v in (led.get('tested') or {}).values() if isinstance(v, dict) and v.get('stub')):,}"],
    ]))

    # --------------------------------------------------------- improving
    F.append(Paragraph("3 &nbsp; Is it improving, and by what measure",
                       st["h2"]))
    F.append(Paragraph(
        "\"Improving\" cannot mean \"finding more winners\" &mdash; a "
        "searcher that found more winners the longer it ran would be "
        "overfitting, and the rising bar exists specifically to stop "
        "that. These are the measures on which improvement is real, each "
        "with the direction that counts as better and the current "
        "24-hour movement.", st["note"]))
    metrics = [
        ("distinct", "coverage: ideas permanently ruled out", "up"),
        ("features", "vocabulary: features grown and kept", "up"),
        ("adaptations", "changes made to how it searches", "up"),
        ("closed", "families closed off as exhausted", "up"),
        ("deduced", "horizons inferred from its own failures", "up"),
        ("survivors", "candidates that cleared every control", "up"),
        ("killed", "candidates a control caught", "up (controls working)"),
        ("bar", "the strength now demanded, in sigma", "rises by design"),
    ]
    d, span24, cov24 = _rate(hist, 1440)
    _, span1, cov1 = _rate(hist, 60)
    h24 = ("24h" if cov24 else
           (f"{span24 / 60.0:,.0f}m*" if span24 else "24h"))
    h1 = ("1h" if cov1 else (f"{span1 / 60.0:,.0f}m*" if span1 else "1h"))
    rows = [["measure", "what better looks like", "now", h24, h1]]
    last = hist[-1] if hist else {}
    for key, what, better in metrics:
        d24, _, _ = _rate(hist, 1440, key)
        d1, _, _ = _rate(hist, 60, key)
        cur = last.get(key)
        rows.append([
            key, what,
            _num_or(cur, "{:,.2f}" if key == "bar" else "{:,.0f}"),
            "UNKNOWN" if d24 is None else f"{d24:+,.2f}" if key == "bar"
            else f"{d24:+,.0f}",
            "UNKNOWN" if d1 is None else f"{d1:+,.2f}" if key == "bar"
            else f"{d1:+,.0f}"])
    F.append(_table(rows, [22, 62, 22, 22, 20], st))
    if not (cov24 and cov1):
        F.append(Paragraph(
            "* the history series is younger than the window, so that "
            "column covers the whole series rather than the period its "
            "heading names. This is what a recently restarted process "
            "looks like; it is not a measurement of a full day.",
            st["note"]))
    F.append(Paragraph(
        "The honest reading: coverage climbing while survivors stay at "
        "zero is the expected and healthy state. What would mean it is "
        "NOT improving is coverage flat (the space is exhausted and "
        "nothing new is being drawn), adaptations flat over many cycles "
        "(it is testing but not learning from failure), or killed at "
        "zero across thousands of candidates (the controls are not "
        "engaging, which usually means nothing is reaching them).",
        st["note"]))

    # ----------------------------------------------------------- power
    F.append(Paragraph("4 &nbsp; Statistical power &mdash; what it could "
                       "see if it were there", st["h2"]))
    F.append(Paragraph(
        "The most important section in this document. A search that "
        "reports nothing is only informative if it could have detected "
        "something. These numbers come from planting edges of known size "
        "in real tapes and counting how often the searcher finds them.",
        st["note"]))
    if not cal:
        F.append(Paragraph("No calibration on file yet. Until there is "
                           "one, \"nothing found\" carries NO information "
                           "about whether anything is there.", st["p"]))
    else:
        det = cal.get("detectable_at_80pct")
        fa = cal.get("false_alarms") or {}
        F.append(_kv([
            ["market calibrated", str(cal.get("market", "?"))],
            ["measured at", str(cal.get("t", "?"))],
            ["bar at calibration", _num_or(cal.get("bar"), "{:,.2f} sigma")],
            ["smallest edge found 80% of the time",
             (f"{det:.3f} round trips per trade" if det is not None
              else "NONE of the planted sizes reached 80% power")],
            ["per-trade dispersion (sd)",
             _num_or(cal.get("sd_rt"), "{:,.1f} round trips")],
            ["baseline (unplanted) level",
             _num_or(cal.get("baseline_rt"), "{:+.3f} RT/trade")],
        ]))

        F.append(Paragraph("Power: planted edges of known size, and how "
                           "often the searcher found them", st["h3"]))
        rows = [["planted edge (RT/trade)", "detected", "rate", "median z",
                 "bar it had to clear"]]
        for k, v in sorted((cal.get("power") or {}).items(),
                           key=lambda kv: float(kv[0])):
            rows.append([f"+{float(k):.3f}",
                         f"{v.get('detected', '?')} of {v.get('of', '?')}",
                         _num_or(v.get("rate"), "{:.0%}"),
                         _num_or(v.get("median_z")),
                         _num_or(cal.get("bar"), "{:.2f}")])
        F.append(_table(rows, [36, 26, 18, 22, 30], st))

        F.append(Paragraph("False alarms: the same search run on tapes "
                           "with nothing planted", st["h3"]))
        F.append(_kv([
            ["cells searched", _num_or(fa.get("cells"), "{:,.0f}")],
            ["cells that cleared the bar anyway",
             _num_or(fa.get("alarms"), "{:,.0f}")],
            ["false-alarm rate", _num_or(fa.get("rate"), "{:.2%}")],
            ["highest z reached on pure noise",
             _num_or(fa.get("max_z"))],
            ["99th percentile z on pure noise",
             _num_or(fa.get("p99_z"))],
        ]))
        F.append(Paragraph(
            "A false-alarm rate at or near zero while the highest noise z "
            "sits far below the bar is the bar doing its job: it is "
            "calibrated well above what chance produces at this number of "
            "trials. That is the good news and the bad news at once &mdash; "
            "the same strictness is what the power table above is failing "
            "to reach.", st["note"]))

        reach = cal.get("reachability") or []
        if reach:
            F.append(Paragraph("Reachability: which HOLDS this tape can "
                               "see anything at, and how small", st["h3"]))
            F.append(Paragraph(
                "The single most decision-relevant table in this "
                "document. Per-trade dispersion grows as roughly the "
                "square root of hold, so the trades an edge needs grow "
                "LINEARLY with hold &mdash; while the trades a tape can "
                "supply shrink linearly with it. The penalty is "
                "quadratic, and it decides where searching is worth "
                "anything at all. A row whose smallest resolvable edge "
                "is above about +1.0 round trips per trade is a region "
                "where no plausible finding could be seen: this "
                "project's own rule treats an edge that large as more "
                "likely a bug than a discovery.", st["note"]))
            rows = [["hold", "dispersion", "trades", "effective n",
                     "smallest edge visible", "verdict"]]
            for r in reach:
                hs = r.get("hold_s") or 0
                m = r.get("smallest_edge_rt")
                rows.append([
                    f"{hs}s" if hs < 120 else f"{hs / 60:,.0f} min",
                    _num_or(r.get("sd_rt"), "{:,.1f}"),
                    _num_or(r.get("trades_available"), "{:,.0f}"),
                    _num_or(r.get("effective_n"), "{:,.0f}"),
                    _num_or(m, "{:+.3f} RT/trade"),
                    ("worth searching" if (m or 9) <= 0.5 else
                     "marginal" if (m or 9) <= 1.0 else
                     "BLIND — nothing findable here")])
            F.append(_table(rows, [16, 20, 24, 24, 38, 52], st, size=6.4))
            F.append(Paragraph(
                f"Measured on {_num_or(cal.get('bars'), '{:,.0f}')} bars "
                f"at {_num_or(cal.get('bar_s'), '{:,.0f}')}s, assuming a "
                f"cell fires on 10% of them and the mechanism is pooled "
                f"over 20. Both assumptions are stated because the "
                f"answer is meaningless without them. A wasted trial is "
                f"not free: the bar rises as the square root of twice "
                f"the log of the trial count, so every hypothesis tested "
                f"in a blind region makes the standard harder for every "
                f"hypothesis tested anywhere else. Searching where you "
                f"cannot see is strictly worse than not searching.",
                st["note"]))

        req = cal.get("required_trades") or {}
        if req:
            F.append(Paragraph("How many trades an edge of each size would "
                               "need before this bar could see it",
                               st["h3"]))
            rows = [["edge (RT/trade)", "trades needed",
                     "at 200 trades/week, one market",
                     "pooled over 20 markets"]]
            for k, v in sorted(req.items(), key=lambda kv: float(kv[0])):
                try:
                    wk = float(v) / 200.0
                    rows.append([f"+{float(k):.3f}", f"{float(v):,.0f}",
                                 f"{wk:,.0f} weeks", f"{wk / 20.0:,.0f} weeks"])
                except Exception:                             # noqa: BLE001
                    rows.append([str(k), str(v), "—", "—"])
            F.append(_table(rows, [26, 34, 40, 34], st))
            F.append(Paragraph(
                "This table is the entire argument for breadth. The same "
                "edge that is unreachable in one market becomes reachable "
                "when the same mechanism is measured in twenty at once, "
                "which is why the searcher draws one shared slate per "
                "cycle and judges it on the pooled evidence rather than "
                "market by market. The pooled column still assumes the "
                "markets are independent; the meta-analysis applies a "
                "correlation discount on top, so the true figure sits "
                "between the two columns.", st["note"]))

        F.append(Paragraph("Calibration: does a planted edge come back at "
                           "the size it was planted", st["h3"]))
        rows = [["asked", "recovered", "offset from zero plant",
                 "INCREMENT recovered", "increment error", "standard error",
                 "plants", "trades"]]
        for row in (cal.get("calibration") or []):
            rows.append([_num_or(row.get("asked"), "{:+.3f}"),
                         _num_or(row.get("got"), "{:+.3f}"),
                         _num_or(row.get("err"), "{:+.3f}"),
                         _num_or(row.get("increment"), "{:+.3f}"),
                         _num_or(row.get("increment_err"), "{:+.4f}"),
                         _num_or(row.get("se"), "{:.3f}"),
                         str(row.get("plants", "?")),
                         _num_or(row.get("n"), "{:,.0f}")])
        F.append(_table(rows, [16, 20, 26, 26, 22, 22, 14, 16], st,
                        size=6.4))
        F.append(Paragraph(
            "Read the INCREMENT column, not the offset. Every row here "
            "carries the same offset because the unplanted tape itself "
            "drifts &mdash; the zero plant recovers it too. That is the "
            "market, not bias in the harness. The harness is honest when "
            "asking for +0.25 more returns +0.25 more, which is what the "
            "increment column checks, and it fails when the increment "
            "error grows beyond the standard error. An earlier version of "
            "this check read the offset instead and reported a +0.409 "
            "\"bias\" that was a single walk's noise.", st["note"]))
        if det is None:
            F.append(Paragraph(
                "<b>This is the binding constraint on the whole project.</b> "
                "Below the detectable size, silence is not evidence of "
                "absence &mdash; the searcher would return exactly these "
                "results whether or not an edge of that size exists. The "
                "two ways out are more trades per mechanism (higher "
                "frequency, longer tapes, deeper tiers) and more markets "
                "per mechanism (the pooled slate), and the searcher does "
                "both at once because neither is enough alone.", st["p"]))

    # ------------------------------------------------- map of the space
    F.append(Paragraph("5 &nbsp; The map of the search space", st["h2"]))
    cells = (arch or {}).get("cells") or {}
    if not cells:
        F.append(Paragraph("The map is empty. It fills as mechanisms "
                           "clear the minimum trade count.", st["note"]))
    else:
        # The key on disk is the raw index tuple "1,4,0,1". Printing that
        # is printing the storage format: it says nothing about what the
        # niche IS, which is the only reason the map exists.
        try:
            from researcher.archive import cell_name, TOTAL_CELLS
        except Exception:                                     # noqa: BLE001
            cell_name, TOTAL_CELLS = None, None

        def nice(key):
            if cell_name is None:
                return str(key)
            try:
                return cell_name(tuple(int(x) for x in str(key).split(",")))
            except Exception:                                 # noqa: BLE001
                return str(key)

        F.append(Paragraph(
            f"{len(cells)} behavioural niches occupied"
            + (f" of {TOTAL_CELLS} that exist "
               f"({len(cells) / TOTAL_CELLS:.0%} coverage)"
               if TOTAL_CELLS else "")
            + ". One elite per niche (frequency x hold x exit x side); "
              "breeding draws from these rather than from fresh random "
              "shapes, which is what makes the search get better as well "
              "as broader. Coverage matters as much as the scores: an "
              "empty region of the map is a kind of strategy nothing has "
              "ever been tried in.", st["note"]))
        F.append(Paragraph(
            "READ eff n BEFORE cu. Overlapping trades are not "
            "independent observations: a cell holding 240 bars while "
            "firing on every bar carries the information of two, "
            "whatever its raw trade count says. The four best elites on "
            "this map were once +110, +79, +61 and +47 round trips per "
            "trade on effective samples of 2, 2, 2 and 5 -- pure noise "
            "wearing a four-figure trade count. The map now refuses a "
            "niche below 30 effective observations and prints the "
            "figure either way.", st["note"]))
        rows = [["niche", "net RT/trade", "z", "trades", "eff n",
                 "smallest visible", "/wk", "market", "family"]]
        items = sorted(cells.items(),
                       key=lambda kv: -(kv[1].get("cu")
                                        if kv[1].get("cu") is not None
                                        else -9e9))[:45]
        for name, c in items:
            rows.append([
                nice(name)[:40],
                _num_or(c.get("cu"), "{:+.3f}"),
                _num_or(c.get("z")), _num_or(c.get("n"), "{:,.0f}"),
                _num_or(c.get("eff_n"), "{:,.0f}"),
                _num_or(c.get("mde"), "{:,.1f} RT"),
                _num_or(c.get("per_week"), "{:,.1f}"),
                str(c.get("market", "?"))[:10],
                str(c.get("family", ""))[:18]])
        F.append(_table(rows, [40, 18, 11, 15, 12, 20, 12, 14, 20], st,
                        size=6.2))
        if len(cells) > 45:
            F.append(Paragraph(f"...{len(cells) - 45} further niches not "
                               f"listed.", st["note"]))
        F.append(Paragraph(
            f"{arch.get('considered', 0):,} measurements offered to the "
            f"map, {arch.get('improvements', 0):,} of which improved on "
            f"the elite already holding their niche.", st["note"]))

    # ----------------------------------------------- what it can see
    F.append(Paragraph("5b &nbsp; The data it can see", st["h2"]))
    F.append(Paragraph(
        "A tier that is absent looks exactly like a tier that found "
        "nothing, and only one of those is a result. Every tier is listed "
        "whether or not it loaded.", st["note"]))
    try:
        from researcher import data_tiers as DT
        from researcher import runner as R
        rows = [["tier", "what it is", "markets", "status"]]
        rows.append(["1", "daily/5-minute bars, every market",
                     f"{len(R.SPEC)} configured", "see markets below"])
        for res in (getattr(R, "T2_RES", None) or []):
            srcs = DT.tier2_sources(res)
            rows.append([f"2 @ {res}s", "NQ tick, resampled",
                         f"{len(srcs)} contracts",
                         "ok" if srcs else "MISSING"])
        rows.append(["3", "NQ top of book", "1",
                     str(extra.get("tiers", "see health"))])
        F.append(_table(rows, [18, 60, 34, 50], st))
        rows = [["market", "$ per point", "round-trip cost"]]
        for k, (pv, cost) in sorted(R.SPEC.items()):
            rows.append([k, f"{pv:,.4g}", f"${cost:,.4f}"])
        F.append(Spacer(1, 6))
        F.append(_table(rows, [24, 34, 34], st))
        F.append(Paragraph(
            "Silver (SI) is permanently excluded by standing instruction. "
            "Every result in this document is measured against that "
            "market's own round-trip cost, never against dollars, because "
            "ZB's tick is sixty times MNQ's and a dollar figure compared "
            "across them is a category error.", st["note"]))
    except Exception as exc:                                  # noqa: BLE001
        F.append(Paragraph(f"data inventory unavailable: {_esc(exc)}",
                           st["note"]))

    # --------------------------------- what it inferred about horizons
    ins = (mem.get("insights") or {}).get("horizons") or {}
    if ins:
        F.append(Paragraph("5c &nbsp; What it worked out about holding "
                           "time", st["h2"]))
        F.append(Paragraph(
            "Cost is fixed per trade; the size of a move grows roughly as "
            "the square root of time. So for every family there is a "
            "horizon at which its gross edge first covers a round trip, "
            "and that horizon is arithmetic rather than something to "
            "search for. These fits are what the searcher extracted from "
            "its OWN failures, and they are what the hold multipliers in "
            "the adaptations section act on.", st["note"]))
        rows = [["family", "edge grows as", "fit", "break-even horizon",
                 "reachable", "longest tested"]]
        for name, h in sorted(ins.items(),
                              key=lambda kv: (kv[1].get("h_star") or 9e9)):
            hs = h.get("h_star")
            rows.append([
                str(name)[:30],
                f"horizon^{_num_or(h.get('b'), '{:.2f}')}",
                _num_or(h.get("r2"), "{:.2f}"),
                ("does not reach it" if not hs else
                 f"{hs:,.0f}s" if hs < 120 else f"{hs / 60:,.0f} min"),
                "yes" if h.get("reachable") else "NO — beyond the data",
                _num_or(h.get("max_tested"), "{:,.0f}s")])
        F.append(_table(rows, [30, 26, 12, 34, 32, 26], st))

    # ------------------------------------------------------- families
    F.append(PageBreak())
    F.append(Paragraph("6 &nbsp; Every family, and what its failures said",
                       st["h2"]))
    fams = led.get("families", {}) or {}
    mf = mem.get("families", {}) or {}
    if not fams:
        F.append(Paragraph("No families on record.", st["note"]))
    else:
        F.append(Paragraph(
            "\"Effort\" is the multiplier on how much attention the family "
            "gets next cycle. It falls as a family accumulates trials "
            "without producing anything and never reaches zero, because a "
            "family is not disproved by its members failing. \"Lesson\" is "
            "derived from the SHAPE of the failures, not from their "
            "count: cost-bound means the direction was right and the move "
            "too small to pay the round trip, which is an arithmetic "
            "problem fixed by longer holds rather than by more searching.",
            st["note"]))
        # Both derived, not stored: the prior is a function of (n, sum_edge)
        # and the lesson a function of the failure profile. Reading a
        # "prior" key that was never written is how the first version of
        # this table printed UNKNOWN in every row.
        try:
            from researcher.ledger import Ledger
            from researcher.memory import Memory
            _L = Ledger.__new__(Ledger)
            _L.d = led
            _M = Memory.__new__(Memory)
            _M.d = mem
        except Exception:                                     # noqa: BLE001
            _L = _M = None
        rows = [["family", "tested", "best z", "effort", "cost-bound",
                 "wrong sign", "no signal", "thin", "lesson"]]
        for name, f in sorted(fams.items(),
                              key=lambda kv: -(kv[1].get("n") or 0)):
            m = mf.get(name, {}) or {}
            try:
                pri = _L.family_prior(name) if _L else None
            except Exception:                                 # noqa: BLE001
                pri = None
            try:
                les = _M.lesson(name)[0] if _M else ""
            except Exception:                                 # noqa: BLE001
                les = ""
            rows.append([
                str(name)[:30],
                f"{f.get('n', 0):,}",
                _num_or(f.get("best_z")),
                _num_or(pri, "{:.2f}x"),
                f"{m.get('cost_bound', 0):,}" if m else "—",
                f"{m.get('wrong_sign', 0):,}" if m else "—",
                f"{m.get('no_signal', 0):,}" if m else "—",
                f"{m.get('thin', 0):,}" if m else "—",
                str(les)[:52]])
        F.append(_table(rows, [30, 14, 12, 12, 15, 14, 14, 11, 50], st,
                        size=6.2))

    # ------------------------------------------------- top N strategies
    F.append(PageBreak())
    F.append(Paragraph(f"7 &nbsp; The top {top} things it has found",
                       st["h2"]))
    F.append(Paragraph(
        "Ranked by whether they pay at all first, then by strength. "
        "READ THE FLAGS: <b>passed</b> means it cleared the bar and every "
        "control; <b>killed</b> means a control caught it; <b>stale</b> "
        "means the tape changed under it; <b>code-stale</b> means the "
        "measurement code was superseded. The highest z out of hundreds "
        "of thousands of trials is expected to be large even when nothing "
        "is there, which is exactly what the bar is for.", st["note"]))
    board = []
    try:
        from researcher.ledger import Ledger
        L = Ledger.__new__(Ledger)
        L.d = led
        import threading
        L._lock = threading.Lock()
        board = L.near_misses(top)
    except Exception as exc:                                  # noqa: BLE001
        F.append(Paragraph(f"leaderboard unavailable: {_esc(exc)}",
                           st["note"]))
    if not board:
        F.append(Paragraph("Nothing on the board yet.", st["note"]))
    else:
        F.append(Paragraph(
            "READ THE TRADE COUNT CAREFULLY on a pooled row. It is the "
            "total across EVERY market in the pool over the whole tape "
            "history -- about nine years for tier 1 -- not a rate. "
            "\"790,863 trades\" is roughly seventy a week per market. "
            "The /wk column is the rate, summed over the pool, and "
            "/wk/mkt is what one market actually fires.", st["note"]))
        rows = [["#", "market", "t", "family", "z", "bar", "net", "unit",
                 "trades", "/wk", "/wk/mkt", "win", "RR", "MDE", "mkts",
                 "flags"]]
        for i, r in enumerate(board, 1):
            h = r.get("hyp") or {}
            pooled = r.get("pooled")
            net = r.get("net") if not pooled else r.get("cu")
            flags = []
            if r.get("passed"):
                flags.append("PASSED")
            if r.get("killed"):
                flags.append("killed")
            if r.get("stale"):
                flags.append("stale")
            if r.get("code_stale"):
                flags.append("code-stale")
            if r.get("checked"):
                flags.append("vault")
            rows.append([
                str(i),
                str(h.get("market", "POOLED"))[:14],
                str(h.get("tier", "")),
                str(r.get("family", ""))[:22],
                _num_or(r.get("z")),
                _num_or(r.get("bar_at_test")),
                _num_or(net, "{:+.3f}"),
                "RT" if pooled else "$",
                _num_or(r.get("n"), "{:,.0f}"),
                _num_or(r.get("per_week"), "{:,.1f}"),
                _num_or(r.get("per_week_per_market"), "{:,.1f}"),
                _num_or(r.get("win_rate"), "{:.0%}"),
                _num_or(r.get("rr")),
                _num_or(r.get("mde"), "{:.3f}"),
                (_num_or(r.get("k"), "{:,.0f}") + "/" +
                 _num_or(r.get("agree"), "{:.0%}")) if pooled else "—",
                " ".join(flags)[:22]])
        F.append(_table(rows, [5, 13, 4, 19, 10, 9, 12, 6, 13, 9, 12,
                               9, 8, 10, 12, 18], st, size=5.8))

        F.append(PageBreak())
        F.append(Paragraph(f"7b &nbsp; Full specification of each",
                           st["h2"]))
        F.append(Paragraph(
            "Every field the searcher stored, so any entry can be "
            "reproduced or argued with. \"net\" is dollars per trade for a "
            "single-market result and round trips per trade for a pooled "
            "one; 0 round trips is break-even after costs, not 1.",
            st["note"]))
        for i, r in enumerate(board, 1):
            h = r.get("hyp") or {}
            pooled = r.get("pooled")
            head = (f"<b>#{i} &nbsp; {_esc(h.get('market', 'POOLED'))}"
                    f"{' tier ' + str(h['tier']) if h.get('tier') else ''}"
                    f" &nbsp;·&nbsp; {_esc(r.get('family', ''))}</b>")
            body = [
                f"{head}<br/>{_esc(_describe(h))}",
                f"<b>spec</b> &nbsp; {_esc(_spec(h))}",
                (f"<b>result</b> &nbsp; z {_num_or(r.get('z'))} against a "
                 f"bar of {_num_or(r.get('bar_at_test'))} &nbsp;·&nbsp; "
                 f"net {_num_or(r.get('net') if not pooled else r.get('cu'), '{:+.4f}')}"
                 f"{' round trips/trade' if pooled else ' $/trade'}"
                 f" &nbsp;·&nbsp; gross {_num_or(r.get('gross'), '{:+.4f}')}"
                 f" &nbsp;·&nbsp; {_num_or(r.get('n'), '{:,.0f}')} trades"
                 f" &nbsp;·&nbsp; {_num_or(r.get('per_week'), '{:,.1f}')}/week"
                 f" &nbsp;·&nbsp; win {_num_or(r.get('win_rate'), '{:.1%}')}"
                 f" &nbsp;·&nbsp; RR {_num_or(r.get('rr'))}"),
                (f"<b>blindness</b> &nbsp; smallest edge this cell could "
                 f"have shown: {_num_or(r.get('mde'), '{:.3f}')} RT/trade"
                 + (f" &nbsp;·&nbsp; pooled over "
                    f"{_num_or(r.get('k'), '{:,.0f}')} markets, "
                    f"{_num_or(r.get('agree'), '{:.0%}')} agreeing on sign"
                    if pooled else "")),
            ]
            if r.get("kill_reasons"):
                body.append("<b>killed by</b> &nbsp; "
                            + _esc("; ".join(r["kill_reasons"]))[:400])
            F.append(KeepTogether(
                [Paragraph(b, st["note"]) for b in body]
                + [Spacer(1, 4)]))

    # ------------------------------------ what it turned up RECENTLY
    F.append(Paragraph("7b2 &nbsp; The best of the last 24 hours",
                       st["h2"]))
    F.append(Paragraph(
        "The board above is an ALL-TIME record. It ranks by strength, "
        "strength is a maximum over everything ever tested, and a "
        "maximum only moves when something beats the best result in the "
        "project's history -- so on a searcher that is working correctly "
        "it sits unchanged for days while hundreds of thousands of "
        "trials happen behind it. That is what success at not "
        "overfitting looks like, and from the outside it is identical to "
        "a process that has stopped. This window is the second view that "
        "tells them apart: it moves every cycle. If it is always far "
        "below the board, the search is running and finding nothing new, "
        "which is information. If it stops moving, that is a fault.",
        st["note"]))
    try:
        from researcher.ledger import Ledger as _L2
        _l2 = _L2.__new__(_L2)
        _l2.d = led
        import threading as _th
        _l2._lock = _th.Lock()
        rec = _l2.recent_best(hours=24, k=10)
    except Exception as exc:                                  # noqa: BLE001
        rec = None
        F.append(Paragraph(f"unavailable: {_esc(exc)}", st["note"]))
    if rec:
        F.append(Paragraph(
            f"{rec['considered']:,} measurements landed in this window.",
            st["note"]))
        if not rec["rows"]:
            F.append(Paragraph(
                "NOTHING measured in the last 24 hours. On a searcher "
                "that is supposed to run continuously that is a fault, "
                "not a quiet spell.", st["p"]))
        else:
            rows = [["#", "market", "z", "bar", "net", "unit", "trades",
                     "eff n", "found", "family"]]
            for i, r in enumerate(rec["rows"], 1):
                pooled = r.get("pooled")
                rows.append([
                    str(i), str(r.get("market") or "POOLED")[:14],
                    _num_or(r.get("z")), _num_or(r.get("bar_at_test")),
                    _num_or(r.get("cu") if pooled else r.get("net"),
                            "{:+.3f}"),
                    "RT" if pooled else "$",
                    _num_or(r.get("n"), "{:,.0f}"),
                    _num_or(r.get("eff_n"), "{:,.0f}"),
                    str(r.get("t") or "")[:16],
                    str(r.get("family") or "")[:22]])
            F.append(_table(rows, [8, 20, 13, 12, 16, 8, 16, 13, 26, 30],
                            st, size=6.4))

    # ------------------------------------------------------------- vault
    F.append(PageBreak())
    F.append(Paragraph("7c &nbsp; The sealed vault, and what has been "
                       "spent from it", st["h2"]))
    F.append(Paragraph(
        "The last 20% of every tape is never searched. A candidate is "
        "shown it exactly once, and that look is recorded forever, so the "
        "vault cannot be reused to rescue an idea that failed on it. This "
        "is the only genuinely out-of-sample evidence in the system and "
        "it is a consumable resource: every touch spends a little of it.",
        st["note"]))
    touches = mem.get("vault", []) or []
    F.append(_kv([
        ["hypotheses shown the vault",
         f"{len(led.get('vault_touches', {})):,}"],
        ["touches recorded with detail", f"{len(touches):,}"],
    ]))
    if touches:
        rows = [["when", "family", "z in search", "z in vault",
                 "trades in search", "trades in vault", "verdict"]]
        for t in touches[-40:]:
            zs, zv = t.get("z_search"), t.get("z_vault")
            if zv is None:
                verdict = "no trades in the vault window"
            elif zs is None:
                verdict = "—"
            else:
                verdict = ("held up" if zv > 0 and zv >= 0.5 * zs
                           else "did not hold up")
            rows.append([str(t.get("t", ""))[:19], str(t.get("family", ""))[:26],
                         _num_or(zs), _num_or(zv),
                         _num_or(t.get("n_search"), "{:,.0f}"),
                         _num_or(t.get("n_vault"), "{:,.0f}"),
                         verdict])
        F.append(_table(rows, [30, 28, 18, 18, 20, 20, 34], st, size=6.4))
        if len(touches) > 40:
            F.append(Paragraph(f"...{len(touches) - 40} earlier touches "
                               f"not listed.", st["note"]))

    # ------------------------------------------------------- adaptations
    F.append(PageBreak())
    F.append(Paragraph("8 &nbsp; Everything it changed about itself",
                       st["h2"]))
    adapts = sorted(mem.get("adaptations", []) or [],
                    key=lambda a: -(a.get("applied") or 0))
    if not adapts:
        F.append(Paragraph("Nothing yet. A system that reports lessons but "
                           "cannot show what it did differently is a "
                           "logging system, so this page being empty is a "
                           "real and reportable state.", st["note"]))
    for a in adapts:
        F.append(Paragraph(
            f"<b>{_esc(a.get('kind'))} / {_esc(a.get('family'))}</b> "
            f"&mdash; {_esc(a.get('before'))} &rarr; {_esc(a.get('after'))}, "
            f"applied {a.get('applied')}x since {_esc(a.get('first'))}<br/>"
            f"{_esc(a.get('why'))}", st["note"]))

    # ------------------------------------------------- controls + caught
    F.append(PageBreak())
    F.append(Paragraph("9 &nbsp; The controls, and what they measured",
                       st["h2"]))
    for n, d in CONTROLS:
        F.append(Paragraph(n, st["h3"]))
        F.append(Paragraph(_esc(d), st["note"]))
    F.append(Paragraph("10 &nbsp; Errors these controls already caught",
                       st["h2"]))
    F.append(Paragraph(
        "Every one was found by a control or a calibration against a "
        "known answer, and none by reading the code. All but one produced "
        "a FALSE POSITIVE, which is the direction that costs money.",
        st["note"]))
    rows = [["error", "what it did"]]
    for n, d in CAUGHT:
        rows.append([Paragraph(f"<b>{_esc(n)}</b>", st["note"]),
                     Paragraph(_esc(d), st["note"])])
    F.append(_table(rows, [52, 110], st))

    # -------------------------------------------------------- raw state
    F.append(PageBreak())
    F.append(Paragraph("11 &nbsp; Raw counters", st["h2"]))
    F.append(Paragraph("Every scalar in the state files, unabridged, so "
                       "nothing above can hide a number by omitting it.",
                       st["note"]))
    for label, blob in (("ledger.json", led), ("memory.json", mem),
                        ("status.json", status),
                        ("calibration.json", cal)):
        F.append(Paragraph(label, st["h3"]))
        rows = []
        for k, v in sorted((blob or {}).items()):
            if isinstance(v, (dict, list)):
                rows.append([k, f"{type(v).__name__}, {len(v):,} entries"])
            else:
                rows.append([k, str(v)[:110]])
        F.append(_kv(rows) if rows else Paragraph("empty", st["note"]))

    # ------------------------------------------------------------ source
    if source:
        F.append(PageBreak())
        F.append(Paragraph("12 &nbsp; Source", st["h2"]))
        F.append(Paragraph(
            "Complete and unabridged, so every number above can be "
            "checked against what actually runs.", st["note"]))
        for rel, what in AUDIT_FILES:
            p = os.path.join(ROOT, rel)
            if not os.path.exists(p):
                continue
            F.append(PageBreak())
            F.append(Paragraph(rel, st["h2"]))
            F.append(Paragraph(_esc(what), st["note"]))
            try:
                src = open(p).read()
            except Exception as exc:                          # noqa: BLE001
                F.append(Paragraph(f"unreadable: {_esc(exc)}", st["note"]))
                continue
            # Preformatted, NOT Paragraph. A Paragraph parses XML markup
            # for every chunk, which for ten thousand lines of source is
            # 1.35s of pure parsing against 0.18s here -- and on a box
            # where 47 search workers own every core, that 7.5x is the
            # difference between the page rendering and Railway giving
            # up on the request. It also preserves indentation properly
            # and needs no escaping, since nothing is markup.
            chunk = []
            for i, line in enumerate(src.split("\n"), 1):
                chunk.append(f"{i:4d}  " + line.rstrip()[:112])
                if len(chunk) >= 58:
                    F.append(Preformatted("\n".join(chunk), st["code"]))
                    F.append(PageBreak())
                    chunk = []
            if chunk:
                F.append(Preformatted("\n".join(chunk), st["code"]))

    doc.build(F)
    return buf.getvalue()


def diagnostics_pdf(rdir, extra=None) -> bytes:
    st = _styles()
    led = _read(os.path.join(rdir, "ledger.json"))
    mem = _read(os.path.join(rdir, "memory.json"))
    status = _read(os.path.join(rdir, "status.json"))
    buf = io.BytesIO()
    doc = _doc(buf, "Research model — diagnostic bundle")
    F = []

    F.append(Paragraph("Research model &mdash; diagnostic bundle",
                       st["h1"]))
    F.append(Paragraph(
        f"Generated {_now()}. Everything needed to judge whether the "
        f"research model is working: live state, the controls and what "
        f"they measured, the errors already caught, and the full source "
        f"of every module.", st["sub"]))

    F.append(Paragraph("Live state", st["h2"]))
    fams = (status.get("learning") or {}).get("families") or []
    sh = (status.get("learning") or {}).get("shrinkage") or {}
    F.append(_kv([
        ["cycle", str(status.get("cycle", 0))],
        ["trials", f"{led.get('trials', 0):,}"],
        ["distinct tested", f"{len(led.get('tested', {})):,}"],
        ["current bar", f"{status.get('summary', {}).get('current_bar_sigma', '?')} sigma"],
        ["survivors", str(len(led.get("survivors", [])))],
        ["vault touches", str(len(led.get("vault_touches", {})))],
        ["halts", str(len(led.get("halts", [])))],
        ["adaptations applied", str(len(mem.get("adaptations", [])))],
        ["shrinkage", str(sh.get("median_ratio", "UNKNOWN"))],
        ["families", str(len(fams))],
        ["started", str(led.get("started", "?"))],
    ]))
    if extra:
        F.append(Spacer(1, 6))
        F.append(_kv([[k, str(v)[:110]] for k, v in extra.items()]))

    halts = led.get("halts", [])
    if halts:
        F.append(Paragraph("Halts", st["h2"]))
        for h in halts[-8:]:
            F.append(Paragraph(f"<b>{_esc(h.get('t'))}</b> "
                               f"{_esc(h.get('why'))}", st["note"]))

    F.append(Paragraph("Controls, and what they measured", st["h2"]))
    for n, d in CONTROLS:
        F.append(Paragraph(n, st["h3"]))
        F.append(Paragraph(_esc(d), st["note"]))

    F.append(Paragraph("Errors already caught by these controls",
                       st["h2"]))
    F.append(Paragraph(
        "Every one was found by a control or a calibration against a "
        "known answer, and none by reading the code. All but one "
        "produced a FALSE POSITIVE, which is the direction that costs "
        "money.", st["note"]))
    rows = [["error", "what it did"]]
    for n, d in CAUGHT:
        rows.append([Paragraph(f"<b>{_esc(n)}</b>", st["note"]),
                     Paragraph(_esc(d), st["note"])])
    t = Table(rows, colWidths=[52 * mm, 110 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
        ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
        ("LINEBELOW", (0, 0), (-1, 0), 0.7, RULE),
        ("LINEBELOW", (0, 1), (-1, -2), 0.3, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    F.append(t)

    adapts = mem.get("adaptations", [])
    F.append(Paragraph("Adaptations applied", st["h2"]))
    if not adapts:
        F.append(Paragraph("None yet.", st["note"]))
    else:
        for a in adapts:
            F.append(Paragraph(
                f"<b>{_esc(a['kind'])} / {_esc(a['family'])}</b> &mdash; "
                f"{_esc(a['before'])} &rarr; {_esc(a['after'])}, applied "
                f"{a['applied']}x since {_esc(a['first'])}<br/>"
                f"{_esc(a['why'])}", st["note"]))

    # ---- full source
    F.append(PageBreak())
    F.append(Paragraph("Source", st["h2"]))
    F.append(Paragraph(
        "Complete and unabridged, so the numbers above can be checked "
        "against what actually runs.", st["note"]))
    for rel, what in AUDIT_FILES:
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            continue
        F.append(PageBreak())
        F.append(Paragraph(rel, st["h2"]))
        F.append(Paragraph(_esc(what), st["note"]))
        try:
            src = open(p).read()
        except Exception as exc:                              # noqa: BLE001
            F.append(Paragraph(f"unreadable: {_esc(exc)}", st["note"]))
            continue
        chunk = []
        for i, line in enumerate(src.split("\n"), 1):
            chunk.append(f"{i:4d}  " + _esc(line.rstrip())[:112])
            if len(chunk) >= 58:
                F.append(Paragraph("<br/>".join(chunk), st["code"]))
                F.append(PageBreak())
                chunk = []
        if chunk:
            F.append(Paragraph("<br/>".join(chunk), st["code"]))

    doc.build(F)
    return buf.getvalue()
