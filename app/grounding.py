"""Grounding: prove the concept map says only what the source says.

The model is asked to copy quotes verbatim, but asking is not proof. Every quote is
checked against the uploaded text here, before anything is saved: an exact quote is kept,
a near-miss is repaired to the real sentence it was reaching for, and anything that cannot
be found is dropped. A concept left with no verifiable quote is dropped with it, because
the tutor is only ever allowed to teach what it can cite.

Nothing from the upload is kept afterwards except what this module lets through, so the
verification result travels with the map and the dashboard can show it.
"""
import difflib
import re

_WS = re.compile(r"\s+")
_FOLD = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", " ": " ", "…": "...",
})
_SENTENCE_END = re.compile(r"(?<=[.!?۔])\s+|\n+")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")

# A near-miss above this is the same sentence with a slip in it; below, it is a different one.
REPAIR_RATIO = 0.86


def norm(text: str) -> str:
    """Fold typography and whitespace so a curly quote never fails a genuine match."""
    return _WS.sub(" ", (text or "").translate(_FOLD)).strip().lower()


def numbers_in(text: str) -> list:
    """Every figure that appears in the source, comma-free, so the story can be held to it."""
    found = set()
    for m in _NUMBER.findall(text or ""):
        cleaned = m.replace(",", "").rstrip(".")
        if cleaned:
            found.add(cleaned)
    return sorted(found)[:600]


def _sentences(raw: str) -> list:
    return [s.strip() for s in _SENTENCE_END.split(raw) if len(s.strip()) > 20]


def _repair(quote: str, sentences: list, folded: list):
    """The source sentence this quote was reaching for, or None."""
    target = norm(quote)
    if not target:
        return None
    best, best_ratio = None, 0.0
    for original, cand in zip(sentences, folded):
        if abs(len(cand) - len(target)) > max(40, len(target)):
            continue
        matcher = difflib.SequenceMatcher(None, target, cand, autojunk=False)
        if matcher.real_quick_ratio() < REPAIR_RATIO or matcher.quick_ratio() < REPAIR_RATIO:
            continue
        ratio = matcher.ratio()
        if ratio > best_ratio:
            best, best_ratio = original, ratio
    return best if best_ratio >= REPAIR_RATIO else None


def verify_concept_map(cmap: dict, raw_text: str) -> dict:
    """Mutates `cmap` so every remaining quote is real; returns the tally.

    Raises ValueError when too little survives to teach from.
    """
    source = norm(raw_text)
    sentences, folded = None, None       # built only if a quote needs repairing
    total = verbatim = repaired = dropped = 0
    keep = []
    before = len(cmap.get("concepts", []))

    for concept in cmap.get("concepts", []):
        good = []
        for q in concept.get("quotes", []):
            total += 1
            text = (q.get("text") or "").strip()
            if text and norm(text) in source:
                q["verified"] = True
                verbatim += 1
                good.append(q)
                continue
            if sentences is None:
                sentences = _sentences(raw_text)
                folded = [norm(s) for s in sentences]
            fixed = _repair(text, sentences, folded)
            if fixed:
                q["text"], q["verified"], q["repaired"] = fixed, True, True
                repaired += 1
                good.append(q)
            else:
                dropped += 1
        if good:
            concept["quotes"] = good
            keep.append(concept)

    if len(keep) < 2:
        raise ValueError("too few concepts could be tied to the source text")

    # A concept that was dropped must not linger as somebody's prerequisite, or the
    # journey would lock a whole branch behind something that no longer exists.
    ids = {c["id"] for c in keep}
    for c in keep:
        c["prerequisites"] = [p for p in c.get("prerequisites", []) if p in ids and p != c["id"]]
    cmap["concepts"] = keep

    stats = {"quotes_total": total, "verbatim": verbatim, "repaired": repaired,
             "dropped": dropped, "concepts_dropped": before - len(keep)}
    cmap["grounding"] = stats
    cmap["numbers"] = numbers_in(raw_text)
    return stats
