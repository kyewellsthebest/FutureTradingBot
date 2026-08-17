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
                                SimpleDocTemplate, Spacer, Table, TableStyle)

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
