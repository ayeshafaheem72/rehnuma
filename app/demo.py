"""Demo fallback - the full experience with no API calls.

Two reasons this exists:

1. Insurance. If the network, the billing or a rate limit fails during a live demo,
   flipping one switch keeps the whole journey working in front of the panel.
2. Rehearsal. The experience can be practised end to end without spending anything.

It is deliberately NOT a fixed script. It reads whatever document was actually
uploaded, pulls verbatim quotes out of it, and builds the journey from those - so it
still behaves correctly on content it has never seen. What it cannot do is reason:
the teaching language is templated, and the mastery signals come from heuristics on
the learner's words rather than judgement. Live mode is the real product; this is
the spare wheel, and the admin screen says so.
"""
import re

from app.llm import (Choice, Citation, Concept, ConceptMap, GuideTurn,
                     MasteryUpdate, Signal, SourceQuote)

SIGNAL_NAMES = ["applied_correctly", "self_corrected", "used_source_vocabulary",
                "asked_deepening_question", "hint_dependency", "retention"]

HEDGES = ("idk", "i don't know", "i dont know", "not sure", "no idea", "dunno",
          "confused", "help", "hint", "?", "pata nahi", "samajh nahi")

CORRECTIONS = ("actually", "wait", "no —", "no,", "i mean", "sorry", "rather")


# ------------------------------------------------------- concept mapping

def _sentences(text: str):
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p.strip() for p in parts if len(p.strip()) > 30]


def _title_for(para: str) -> str:
    """A short human label from the paragraph's opening clause."""
    first = _sentences(para)[0] if _sentences(para) else para
    first = re.sub(r'^(a|an|the)\s+', '', first.strip(), flags=re.I)
    words = first.split()
    cut = words[:6]
    label = " ".join(cut).rstrip(',;:.')
    return label[:1].upper() + label[1:] if label else "Key idea"


def build_concept_map(raw_text: str, title: str):
    """Paragraph-based map. Quotes are real substrings of the upload, so the
    citation chips still show genuine source text."""
    paras = [p.strip() for p in raw_text.split("\n\n") if len(p.strip()) > 120]
    if len(paras) < 3:                       # fall back to sentence grouping
        sents = _sentences(raw_text)
        paras = ["\n".join(sents[i:i + 3]) for i in range(0, len(sents), 3)]
        paras = [p for p in paras if len(p) > 120]

    paras = paras[:7] or [raw_text[:600]]
    concepts, qn = [], 1

    for i, para in enumerate(paras):
        sents = _sentences(para) or [para[:200]]
        quotes = []
        for s in sents[:2]:
            quotes.append(SourceQuote(id=f"q{qn}", text=s[:400]))
            qn += 1
        concepts.append(Concept(
            id=f"c{i+1}",
            title=_title_for(para),
            summary=sents[0][:220],
            difficulty=min(5, 1 + i // 2),
            prerequisites=[f"c{i}"] if i else [],
            quotes=quotes,
        ))

    cmap = ConceptMap(
        title=title,
        subject=_title_for(raw_text[:400]),
        concepts=concepts,
    )
    usage = type("U", (), {"input_tokens": 0, "output_tokens": 0})()
    return cmap, usage, 180


# --------------------------------------------------------------- turns

OPENERS = {
    "en": ("Welcome. We are not going to sit and read — we are going to use this. "
           "I will put you in real situations and you decide what to do.\n\nFirst up: {title}.\n\n{quote}\n\n"
           "Here is the situation: a colleague reads that and asks you what it means in practice. "
           "What do you tell them?"),
    "ur": ("خوش آمدید۔ ہم صرف پڑھیں گے نہیں — ہم اسے استعمال کریں گے۔ میں آپ کو اصل صورتحال میں رکھوں گا "
           "اور آپ فیصلہ کریں گے۔\n\nپہلا موضوع: {title}۔\n\n{quote}\n\n"
           "صورتحال یہ ہے: ایک ساتھی یہ پڑھ کر آپ سے پوچھتا ہے کہ عملی طور پر اس کا کیا مطلب ہے۔ آپ کیا کہیں گے؟"),
}

# Deliberately subject-neutral. The engine must work on ANY uploaded material - a
# policy, a safety manual, a biology chapter, a spreadsheet - so no template may
# assume a setting, an industry or a role.
MISSION = {
    "en": ("Someone who has just read this comes to you and says: \"be straight with me, "
           "what does {hook} actually mean in practice?\"\n\nThe material says:\n{quote}\n\n"
           "How do you answer them?"),
    "ur": ("کوئی شخص یہ پڑھ کر آپ کے پاس آتا ہے اور کہتا ہے: \"صاف بتائیں، "
           "{hook} کا عملی طور پر کیا مطلب ہے؟\"\n\nمواد کہتا ہے:\n{quote}\n\n"
           "آپ کیا جواب دیں گے؟"),
}

EXPLAIN = {
    "en": ("Good. Now the harder version.\n\nA new trainee has read this line and not understood it:\n"
           "{quote}\n\nExplain it to them in your own words — no jargon, the way you would to a friend."),
    "ur": ("بہت خوب۔ اب ذرا مشکل مرحلہ۔\n\nایک نئے ٹرینی نے یہ سطر پڑھی ہے اور سمجھ نہیں پایا:\n"
           "{quote}\n\nاسے اپنے الفاظ میں سمجھائیں — آسان زبان میں، جیسے کسی دوست کو بتاتے ہیں۔"),
}

PUZZLE = {
    "en": ("Spot the problem.\n\nSomeone summarises this material as: \"{wrong}\"\n\n"
           "The source actually says:\n{quote}\n\nWhat did they get wrong?"),
    "ur": ("غلطی پکڑیں۔\n\nکوئی اس مواد کا خلاصہ یوں کرتا ہے: \"{wrong}\"\n\n"
           "جبکہ اصل متن کہتا ہے:\n{quote}\n\nانہوں نے کیا غلط سمجھا؟"),
}

HINT = {
    "en": ("No problem — let me put it a different way.\n\n{quote}\n\n"
           "Forget the wording for a second. In one sentence, what is that actually protecting "
           "someone from, or getting them?"),
    "ur": ("کوئی بات نہیں — میں دوسرے انداز میں بتاتا ہوں۔\n\n{quote}\n\n"
           "الفاظ چھوڑ دیں۔ ایک جملے میں بتائیں: یہ اصل میں کس چیز سے بچاتا ہے یا کیا فائدہ دیتا ہے؟"),
}

OFF_SOURCE = {
    "en": ("Straight answer: the uploaded material does not cover that, and I will not invent it.\n\n"
           "What it does cover is this:\n{quote}\n\nWant to work from there?"),
    "ur": ("صاف بات: اپلوڈ کیے گئے مواد میں یہ موجود نہیں، اور میں خود سے نہیں بناؤں گا۔\n\n"
           "البتہ اس میں یہ ضرور ہے:\n{quote}\n\nکیا ہم یہاں سے آگے بڑھیں؟"),
}

CHOICES = {
    "en": [("a", "Walk them through it line by line"),
           ("b", "Give them one concrete worked example"),
           ("c", "Ask what they already think it means, then correct from there")],
    "ur": [("a", "انہیں سطر بہ سطر سمجھائیں"),
           ("b", "ایک ٹھوس عملی مثال دیں"),
           ("c", "پہلے پوچھیں کہ وہ کیا سمجھتے ہیں، پھر درست کریں")],
}


def _lang(cfg):
    return "ur" if cfg.get("language") == "ur" else "en"


def _pick_concept(cmap: dict, learner_state: dict, cfg: dict):
    """Next unlocked concept below mastery, else the least mastered."""
    concepts = learner_state.get("concepts", {})
    mastered_at = cfg.get("mastery_mastered_at", 0.85)
    for c in cmap["concepts"]:
        cs = concepts.get(c["id"], {})
        if cs.get("unlocked") and cs.get("mastery", 0) < mastered_at:
            return c
    return min(cmap["concepts"],
               key=lambda c: concepts.get(c["id"], {}).get("mastery", 0))


def _read_signals(message: str, concept: dict):
    """Heuristics standing in for the model's judgement."""
    low = message.lower().strip()
    words = len(low.split())
    hedging = any(h in low for h in HEDGES) or words <= 3
    corrected = any(c in low for c in CORRECTIONS)
    asked = low.endswith("?") and words > 4

    vocab = [w for q in concept.get("quotes", [])
             for w in re.findall(r'\b[a-z]{6,}\b', q["text"].lower())]
    borrowed = next((w for w in set(vocab) if w in low), "")

    detected = {
        "applied_correctly":        (not hedging and words >= 12, message[:160]),
        "self_corrected":           (corrected, message[:160]),
        "used_source_vocabulary":   (bool(borrowed), borrowed),
        "asked_deepening_question": (asked, message[:160]),
        "hint_dependency":          (hedging, message[:160]),
        "retention":                (not hedging and words >= 25, message[:160]),
    }
    return [Signal(name=n, detected=d, evidence=(e if d else ""))
            for n, (d, e) in detected.items()], hedging


def run_turn(concept_map: dict, learner_state: dict, history: list,
             learner_message: str, cfg: dict):
    lang = _lang(cfg)
    concept = _pick_concept(concept_map, learner_state, cfg)
    quotes = concept.get("quotes") or [{"id": "q1", "text": concept["summary"]}]
    quote = quotes[0]
    opener = not learner_message.strip()

    off_source = False

    if opener:
        signals = [Signal(name=n, detected=False, evidence="") for n in SIGNAL_NAMES]
        hedging = False
        text = OPENERS[lang].format(title=concept["title"], quote=f'"{quote["text"]}"')
        kind, choices = "teach", []
    else:
        signals, hedging = _read_signals(learner_message, concept)
        turn_no = learner_state.get("turns", 0)
        asked_off = any(s.name == "asked_deepening_question" and s.detected for s in signals)

        if hedging:
            kind = "dialogue"
            text = HINT[lang].format(quote=f'"{quote["text"]}"')
            choices = []
        elif asked_off and turn_no % 4 == 3:
            kind = "dialogue"
            text = OFF_SOURCE[lang].format(quote=f'"{quote["text"]}"')
            choices = []
            off_source = True
        elif turn_no % 3 == 0:
            kind = "explain_it"
            text = EXPLAIN[lang].format(quote=f'"{quote["text"]}"')
            choices = []
        elif turn_no % 3 == 1:
            kind = "puzzle"
            wrong = quote["text"].split()[:9]
            text = PUZZLE[lang].format(
                wrong=("it basically means " + " ".join(wrong) + " — and nothing else"),
                quote=f'"{quote["text"]}"')
            choices = [Choice(id=c[0], text=c[1]) for c in CHOICES[lang]]
        else:
            kind = "mission"
            hook = concept["title"].lower()
            text = MISSION[lang].format(hook=hook, quote=f'"{quote["text"]}"')
            choices = [Choice(id=c[0], text=c[1]) for c in CHOICES[lang]]

    positives = sum(1 for s in signals
                    if s.detected and s.name not in ("hint_dependency",))
    delta = -0.05 if hedging else min(0.25, 0.06 + 0.05 * positives)
    updates = [] if opener else [MasteryUpdate(
        concept_id=concept["id"],
        delta=delta,
        reason=("leaned on a hint" if hedging
                else f"{positives} understanding signal(s) in their own words"),
    )]

    turn = GuideTurn(
        concept_id=concept["id"],
        interaction_type=kind,
        message=text,
        choices=choices,
        citations=[Citation(quote_id=quote["id"], claim=concept["title"])],
        off_source=off_source,
        hint_given=hedging,
        signals=signals,
        mastery_updates=updates,
        xp_awarded=(cfg.get("xp_per_turn", 10) if not hedging else 3),
    )
    usage = type("U", (), {"input_tokens": 0, "output_tokens": 0})()
    return turn, usage, 140
