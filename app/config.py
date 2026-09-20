"""Admin-editable settings.

Every value here can be changed from the admin screen while the app is running -
no redeploy, no restart. This is what makes the panel's live test survivable:
they say "make her a beginner, in Urdu" and the next turn obeys.
"""
from app import db

DEFAULTS = {
    # --- who is learning ---
    "learner_level":      "beginner",     # beginner | intermediate | advanced
    "language":           "en",           # en | ur | mixed
    "tone":               "friendly",     # formal | friendly | playful
    "pace":               "normal",       # slow | normal | fast

    # --- how it teaches ---
    "difficulty_curve":   "adaptive",     # gentle | adaptive | steep
    "response_length":    "short",        # short | medium | long
    "mechanics": {
        "missions":   True,
        "explain_it": True,
        "puzzles":    True,
        "boss":       True,
        "xp":         True,
        "streaks":    True,
    },

    # --- thresholds the mastery engine uses ---
    "mastery_unlock_threshold": 0.60,     # mastery needed to unlock the next concept
    "mastery_mastered_at":      0.85,     # counts as "mastered" above this
    "hint_penalty":             0.05,     # mastery cost of leaning on a hint
    "xp_per_turn":              10,
    "xp_bonus_no_hint":         5,

    # --- grounding rules ---
    "strict_grounding":   True,           # refuse vs. answer-and-flag when off-source
    "require_citations":  True,           # every factual claim must cite a source quote
    "urdu_transliteration": False,        # show roman Urdu alongside script

    # --- model ---
    "demo_mode":    False,                # run from templates, no API calls (see app/demo.py)
    "model":        "claude-opus-5",
    "effort":       "low",                # per-turn reasoning depth: low keeps the
                                          # conversation responsive; raise for harder material
    "extraction_effort": "low",           # concept-map build. Measured on the UBL brief:
                                          # low 18s, medium 23s, high 24s - all 100% verbatim
                                          # quotes and 9 concepts, so low is the default.
    "max_tokens":   4000,

    # --- safety ---
    "rate_limit_per_min": 20,
    "max_upload_mb":      5,
}

# Settings the admin screen exposes, with the widget to render for each.
SCHEMA = [
    ("learner_level", "select", ["beginner", "intermediate", "advanced"], "Learner level"),
    ("language", "select", ["en", "ur", "mixed"], "Language"),
    ("tone", "select", ["formal", "friendly", "playful"], "Tone"),
    ("pace", "select", ["slow", "normal", "fast"], "Pace"),
    ("difficulty_curve", "select", ["gentle", "adaptive", "steep"], "Difficulty curve"),
    ("response_length", "select", ["short", "medium", "long"], "Response length"),
    ("mastery_unlock_threshold", "number", (0, 1, 0.05), "Unlock threshold"),
    ("mastery_mastered_at", "number", (0, 1, 0.05), "Mastered at"),
    ("hint_penalty", "number", (0, 0.5, 0.01), "Hint penalty"),
    ("xp_per_turn", "number", (0, 100, 1), "XP per turn"),
    ("strict_grounding", "bool", None, "Strict grounding"),
    ("require_citations", "bool", None, "Require citations"),
    ("urdu_transliteration", "bool", None, "Roman Urdu alongside script"),
    ("demo_mode", "bool", None, "Demo fallback (no API)"),
    ("model", "select", ["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"], "Model"),
    ("effort", "select", ["low", "medium", "high", "xhigh"], "Reasoning effort (per turn)"),
    ("extraction_effort", "select", ["low", "medium", "high"], "Reasoning effort (concept map)"),
    ("max_tokens", "number", (256, 16000, 256), "Max response tokens"),
    ("rate_limit_per_min", "number", (1, 120, 1), "Rate limit / min"),
]

LANGUAGE_NAMES = {"en": "English", "ur": "Urdu", "mixed": "English + Urdu (code-switching)"}


def current() -> dict:
    """Stored settings layered over the defaults."""
    cfg = dict(DEFAULTS)
    stored = db.get_setting("config", {}) or {}
    for k, v in stored.items():
        if k == "mechanics" and isinstance(v, dict):
            merged = dict(DEFAULTS["mechanics"])
            merged.update(v)
            cfg["mechanics"] = merged
        elif k in DEFAULTS:
            cfg[k] = v
    return cfg


def update(patch: dict) -> dict:
    stored = db.get_setting("config", {}) or {}
    for k, v in patch.items():
        if k not in DEFAULTS:
            continue
        if k == "mechanics" and isinstance(v, dict):
            m = dict(stored.get("mechanics", {}))
            m.update({mk: bool(mv) for mk, mv in v.items() if mk in DEFAULTS["mechanics"]})
            stored["mechanics"] = m
        else:
            stored[k] = v
    db.set_setting("config", stored)
    db.log_event("info", "config updated", {"keys": sorted(patch.keys())})
    return current()


def reset():
    db.set_setting("config", {})
    db.log_event("info", "config reset to defaults")
    return current()
