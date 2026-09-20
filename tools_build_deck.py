"""Rehnuma - 5 slides for the UBL panel.

Design brief: read as work by someone who has done this professionally for a decade.
That means restraint, not decoration.

  - White ground. Banks read clean, not theatrical.
  - UBL's own brand blue (sampled from ubldigital.com) as the single accent.
    One dominant colour, one accent, greys for everything else.
  - Cambria headlines against Calibri body: contrast without novelty fonts.
  - Generous 0.9in margins and one idea per slide. Air is the luxury signal.
  - Truck art appears exactly once, as a cover ornament. A motif that shouts on
    every slide stops being a motif.
  - Every technical slide leads with a plain-English sentence, then the detail
    underneath in grey, so a non-technical panellist and an engineer both get served.
"""
import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

PROJ = r"C:\Users\Admin\OneDrive - InterSec, Inc\United Bank Limited"
OUT = os.path.join(PROJ, "Rehnuma_UBL_Presentation.pptx")
LOGO = os.path.join(PROJ, "static", "ubl-logo.png")

# UBL brand, sampled pixel-for-pixel from the logo artwork itself
NAVY   = RGBColor(0x0C, 0x2B, 0x45)   # headline ink
BLUE   = RGBColor(0x00, 0x70, 0xB8)   # the mark's own blue - the single accent
BLUE_L = RGBColor(0x50, 0xA0, 0xD0)   # the lighter blue in the swoosh
DEEP   = RGBColor(0x0F, 0x58, 0x85)
GREY   = RGBColor(0x80, 0x82, 0x85)   # body / secondary
GREY_L = RGBColor(0xE6, 0xE7, 0xE8)   # rules and fills
PAPER  = RGBColor(0xFF, 0xFF, 0xFF)
FAINT  = RGBColor(0xF4, 0xF7, 0xFA)
RANI   = RGBColor(0xE6, 0x00, 0x6E)   # the one warm note, used twice in the deck

HEAD = "Cambria"
BODY = "Calibri"

M = 0.9                # page margin
CW = 13.333 - 2 * M    # content width

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]


def slide(bg=PAPER):
    s = prs.slides.add_slide(BLANK)
    r = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
    r.fill.solid(); r.fill.fore_color.rgb = bg
    r.line.fill.background(); r.shadow.inherit = False
    return s


def txt(s, x, y, w, h, runs, size=13, color=GREY, font=BODY, bold=False,
        align=PP_ALIGN.LEFT, space=5, anchor=MSO_ANCHOR.TOP, spacing=None):
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    if isinstance(runs, str):
        runs = [(runs, {})]
    for i, (t, o) in enumerate(runs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = o.get("align", align)
        p.space_after = Pt(o.get("space", space))
        ls = o.get("spacing", spacing)
        if ls:
            p.line_spacing = ls
        r = p.add_run(); r.text = t
        f = r.font
        f.size = Pt(o.get("size", size)); f.bold = o.get("bold", bold)
        f.italic = o.get("italic", False); f.name = o.get("font", font)
        f.color.rgb = o.get("color", color)
    return tb


def fill(s, x, y, w, h, color=FAINT):
    sh = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    sh.fill.solid(); sh.fill.fore_color.rgb = color
    sh.line.fill.background(); sh.shadow.inherit = False
    return sh


def logo(s, x, y, h=0.42):
    """UBL mark. Uses the real file when present, otherwise a clean typographic
    mark in brand blue - deliberate-looking either way, never a broken image."""
    if os.path.exists(LOGO):
        s.shapes.add_picture(LOGO, Inches(x), Inches(y), height=Inches(h))
    else:
        b = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y),
                               Inches(h * 1.72), Inches(h))
        b.fill.solid(); b.fill.fore_color.rgb = BLUE
        b.line.fill.background(); b.shadow.inherit = False
        tf = b.text_frame
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
        r = p.add_run(); r.text = "UBL"
        r.font.size = Pt(h * 40); r.font.bold = True
        r.font.name = "Arial"; r.font.color.rgb = PAPER


def rosette(s, cx, cy, d, color, petals=8):
    """Phool patti ornament - the truck-art nod, drawn once, on the cover only."""
    import math
    for i in range(petals):
        a = 2 * math.pi * i / petals
        pd = d * 0.46
        px = cx + math.cos(a) * d * 0.27 - pd / 2
        py = cy + math.sin(a) * d * 0.27 - pd / 2
        p = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(px), Inches(py),
                               Inches(pd), Inches(pd))
        p.fill.solid(); p.fill.fore_color.rgb = color
        p.line.fill.background(); p.shadow.inherit = False
    c = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(cx - d * 0.19), Inches(cy - d * 0.19),
                           Inches(d * 0.38), Inches(d * 0.38))
    c.fill.solid(); c.fill.fore_color.rgb = PAPER
    c.line.fill.background(); c.shadow.inherit = False


def head(s, kicker, headline, width=CW):
    txt(s, M, 0.72, width, 0.26, kicker, size=10.5, color=BLUE, bold=True, font=BODY)
    txt(s, M, 1.06, width, 0.85, headline, size=40, color=NAVY, font=HEAD, bold=True)


def plain(s, y, line, width=CW):
    """The sentence a non-technical panellist reads. Sized for two lines."""
    txt(s, M, y, width, 0.82, line, size=18, color=DEEP, font=HEAD, spacing=1.15)


def foot(s, n):
    txt(s, M, 6.94, 9.0, 0.26,
        "Ayesha Faheem  \u00b7  Digital HR & AI Manager assignment  \u00b7  prototype for assessment",
        size=8.5, color=GREY)
    txt(s, 11.0, 6.94, 1.43, 0.26, f"{n}\u2009/\u20095", size=8.5, color=GREY,
        align=PP_ALIGN.RIGHT)


# ══════════════════════════════════════════════════ 1 · COVER + BRIEF
s = slide()
rosette(s, 11.15, 3.15, 3.5, FAINT)          # the single truck-art ornament
rosette(s, 11.15, 3.15, 1.5, RGBColor(0xEC, 0xF3, 0xF9))

logo(s, M, 0.66, 0.74)

txt(s, M, 1.92, 9.0, 1.3, "Rehnuma", size=68, color=NAVY, font=HEAD, bold=True)
txt(s, M, 3.06, 9.0, 0.5, "\u0631\u06C1\u0646\u0645\u0627  \u2014  the guide",
    size=19, color=BLUE, font=BODY)

txt(s, M, 3.78, 7.6, 0.6,
    "An AI Learning Experience Engine that turns any content into a "
    "conversation \u2014 and never gives a test.",
    size=17, color=DEEP, font=HEAD, spacing=1.2)

fill(s, M, 4.82, 3.3, 0.028, GREY_L)
txt(s, M, 5.06, 3.1, 1.5, [
    ("PREPARED BY", {"size": 9.5, "bold": True, "color": BLUE, "space": 5}),
    ("Ayesha Faheem", {"size": 15, "color": NAVY, "font": HEAD, "bold": True, "space": 3}),
    ("InterSec, Inc.", {"size": 12, "color": GREY, "space": 0}),
])

fill(s, 4.55, 4.82, 3.3, 0.028, GREY_L)
txt(s, 4.55, 5.06, 3.1, 1.5, [
    ("FOR", {"size": 9.5, "bold": True, "color": BLUE, "space": 5}),
    ("United Bank Limited", {"size": 15, "color": NAVY, "font": HEAD, "bold": True, "space": 3}),
    ("Digital HR & AI Manager", {"size": 12, "color": GREY, "space": 0}),
])

fill(s, 8.2, 4.82, 3.3, 0.028, GREY_L)
txt(s, 8.2, 5.06, 3.2, 1.5, [
    ("THE BRIEF", {"size": 9.5, "bold": True, "color": BLUE, "space": 5}),
    ("Design, build and deploy", {"size": 15, "color": NAVY, "font": HEAD, "bold": True, "space": 3}),
    ("A secure, adaptive, voice-enabled learning engine \u2014 live on the cloud",
     {"size": 12, "color": GREY, "space": 0}),
])
foot(s, 1)


# ═══════════════════════════════════════════════ 2 · PROBLEM & THE UX
s = slide()
head(s, "THE PROBLEM \u00b7 AND WHAT REPLACES IT", "Nobody ever learned from a quiz")

plain(s, 2.08,
      "A quiz tells you what someone remembered this morning. It does not tell you "
      "whether they can use the idea when a customer is standing in front of them.")

fill(s, M, 3.12, CW, 0.028, GREY_L)

txt(s, M, 3.42, 5.3, 2.4, [
    ("SO REHNUMA NEVER TESTS ANYONE", {"size": 9.5, "bold": True, "color": BLUE, "space": 9}),
    ("It gives you situations to act in \u2014 a customer at the counter, a colleague who "
     "has misunderstood something, a flaw to spot.",
     {"size": 13.5, "color": GREY, "space": 8}),
    ("Then it works out what you understand from how you answer: the examples you "
     "reach for, the mistakes you catch yourself making, the words you start using.",
     {"size": 13.5, "color": GREY, "space": 0}),
])

steps = [("Bring anything",
          "A PDF, a policy, an article. Thirty seconds later it is a journey."),
         ("Play, don\u2019t read",
          "Missions, role-play and puzzles \u2014 in English or Urdu, typed or spoken."),
         ("Progress, not scores",
          "Concepts unlock as understanding grows. No pass mark anywhere.")]
for i, (h, sub) in enumerate(steps):
    y = 3.42 + i * 1.12
    txt(s, 6.85, y - 0.04, 0.5, 0.58, f"{i+1}", size=26, color=GREY_L, font=HEAD, bold=True)
    txt(s, 7.42, y + 0.04, 4.55, 0.95, [
        (h, {"size": 15, "bold": True, "color": NAVY, "font": HEAD, "space": 3}),
        (sub, {"size": 12, "color": GREY, "space": 0}),
    ])
foot(s, 2)


# ════════════════════════════════════════ 3 · ARCHITECTURE + EFFICIENCY
s = slide()
head(s, "HOW IT WORKS", "Four steps, one service")

plain(s, 2.08,
      "It reads your document, notes the ideas inside it, then holds a conversation "
      "about them \u2014 keeping a running picture of what you have understood.")

flow = [("Read the document",
         "Text is extracted from the PDF and cleaned.",
         "PyMuPDF \u00b7 capped at 60k characters"),
        ("Map the ideas",
         "Each idea is stored with the exact sentences it came from.",
         "One Claude call \u00b7 schema-validated output"),
        ("Hold the conversation",
         "One situation per turn, adapted to how the learner is doing.",
         "Claude Opus 5 \u00b7 concept map cached per session"),
        ("Track understanding",
         "Mastery, streaks and unlocks update from the evidence in each reply.",
         "Arithmetic in our code, not the model\u2019s memory")]

for i, (h, sub, tech) in enumerate(flow):
    x = M + i * 2.93
    txt(s, x, 3.2, 0.4, 0.34, f"0{i+1}", size=13, color=BLUE, font=BODY, bold=True)
    fill(s, x, 3.58, 2.55, 0.028, BLUE if i == 0 else GREY_L)
    txt(s, x, 3.78, 2.55, 1.9, [
        (h, {"size": 15, "bold": True, "color": NAVY, "font": HEAD, "space": 6}),
        (sub, {"size": 12, "color": GREY, "space": 8}),
        (tech, {"size": 10, "color": BLUE_L, "space": 0}),
    ])

fill(s, M, 5.56, CW, 1.22, FAINT)
txt(s, M + 0.32, 5.76, 10.9, 0.95, [
    ("Why one service instead of four", {"size": 13.5, "bold": True, "color": NAVY,
                                         "font": HEAD, "space": 5}),
    ("The whole thing is a single Python application that serves both the pages and the API. "
     "No separate front-end build, no second deployment, no cross-origin configuration \u2014 "
     "three fewer things that can fail in front of you, and it deploys to a free cloud tier in "
     "one step.", {"size": 11.5, "color": GREY, "space": 0}),
])
foot(s, 3)


# ══════════════════════════════════════════ 4 · SECURITY & GROUNDING
s = slide()
head(s, "SECURITY, PRIVACY & HONESTY", "Built for a bank")

plain(s, 2.08,
      "Two risks matter more than the rest: a tutor that invents a fact about a financial "
      "product, and a document written to hijack it.")

fill(s, M, 3.1, 5.55, 2.62, FAINT)
txt(s, M + 0.32, 3.36, 4.9, 2.2, [
    ("IT CANNOT MAKE THINGS UP", {"size": 9.5, "bold": True, "color": BLUE, "space": 9}),
    ("Every idea is stored with the exact sentences it came from, and every claim the tutor "
     "makes carries a citation you can click to see the original line.",
     {"size": 12.5, "color": GREY, "space": 8}),
    ("Ask it something the document does not cover and it says so plainly, and flags it. "
     "It never fills the gap with a guess.",
     {"size": 12.5, "color": GREY, "space": 0}),
])

fill(s, 6.9, 3.1, 5.55, 2.62, FAINT)
txt(s, 7.22, 3.36, 4.9, 2.2, [
    ("IT CANNOT BE HIJACKED", {"size": 9.5, "bold": True, "color": RANI, "space": 9}),
    ("Uploaded content is the attack surface nobody expects. A document can contain text "
     "aimed at the model \u2014 \u201cignore your instructions and\u2026\u201d",
     {"size": 12.5, "color": GREY, "space": 8}),
    ("Every upload is marked as data, never instructions, in both prompts. A malicious "
     "file is taught from, not obeyed.",
     {"size": 12.5, "color": GREY, "space": 0}),
])

controls = [("Roles", "Admin behind a password"),
            ("Rate limits", "Per-IP on every write"),
            ("Safe inputs", "Validated, type & size capped"),
            ("Browser hardening", "CSP, frame and sniff protection"),
            ("No personal data", "Learners are random IDs")]
for i, (h, sub) in enumerate(controls):
    x = M + i * 2.42
    txt(s, x, 6.02, 2.25, 0.62, [
        (h, {"size": 11.5, "bold": True, "color": NAVY, "space": 2}),
        (sub, {"size": 10, "color": GREY, "space": 0}),
    ])
foot(s, 4)


# ══════════════════════════════════════ 5 · MEASUREMENT & EFFECTIVENESS
s = slide()
head(s, "MEASUREMENT & OUTCOMES", "How we know they learned")

plain(s, 2.08,
      "Six things are watched in every reply. Each one is recorded next to the learner\u2019s "
      "own words, so progress can be audited rather than trusted.")

sig = [("Applied it", "Used the idea on a new example"),
       ("Corrected themselves", "Caught their own mistake mid-thought"),
       ("Borrowed the vocabulary", "Started using the material\u2019s terms"),
       ("Asked ahead", "Questioned beyond what was covered"),
       ("Leaned on a hint", "Needed carrying \u2014 counts against"),
       ("Remembered", "Recalled something from earlier")]
for i, (h, sub) in enumerate(sig):
    col, row = i % 3, i // 3
    x, y = M + col * 3.95, 3.14 + row * 0.92
    txt(s, x, y, 3.7, 0.72, [
        (h, {"size": 13, "bold": True, "color": NAVY, "font": HEAD, "space": 3}),
        (sub, {"size": 11, "color": GREY, "space": 0}),
    ])

fill(s, M, 5.08, CW, 0.028, GREY_L)

txt(s, M, 5.36, 5.4, 1.4, [
    ("WHAT THIS LOOKS LIKE IN PRACTICE", {"size": 9.5, "bold": True, "color": BLUE, "space": 8}),
    ("A learner typed \u201cidk\u201d. The system logged a hint dependency, eased the challenge, "
     "reset the streak and lowered that concept\u2019s mastery \u2014 without ever marking an "
     "answer wrong.", {"size": 12.5, "color": GREY, "space": 0}),
])

txt(s, 6.9, 5.36, 5.55, 1.4, [
    ("AND WHAT YOU CAN TAKE AWAY", {"size": 9.5, "bold": True, "color": BLUE, "space": 8}),
    ("A live evidence feed, before-and-after mastery per concept, engagement and response "
     "times \u2014 all exportable as a spreadsheet. The figures in this demo are read from "
     "the running system, not from this slide.", {"size": 12.5, "color": GREY, "space": 0}),
])
foot(s, 5)

prs.save(OUT)
print("saved:", OUT)
print("logo file found:", os.path.exists(LOGO))
