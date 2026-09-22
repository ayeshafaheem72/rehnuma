"""Admin-editable settings.

Every value here can be changed from the admin screen while the app is running -
no redeploy, no restart. This is what makes the panel's live test survivable:
they say "make her a beginner, in Urdu, with five minutes to spare" and the next
turn obeys.

Every write is validated against SCHEMA before it is stored. A setting that reaches
the database has already been checked, because a bad value here does not fail once - it
fails on every turn for every learner until someone finds it.
"""
import math
import re
import time

from app import db

DEFAULTS = {
    # --- who is learning ---
    "learner_level":      "beginner",     # beginner | intermediate | advanced
    "language":           "en",           # en | ur | mixed | roman
    "tone":               "friendly",     # formal | friendly | playful
    "pace":               "normal",       # slow | normal | fast
    "learner_profile":    "",             # free text: who they are, e.g. "a first-time saver"
    "constraints":        "",             # free text: operating limits, e.g. "five minutes, on a phone"

    # --- how it teaches ---
    "story_intro":        True,           # open with an illustrated story before the first challenge
    "default_mode":       "challenge",    # story | challenge | tour | deep - how the
                                          # learner is taught; they may override per session
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
    "custom_rules":       "",             # free text: rules the tutor must follow, set by an admin

    # --- thresholds the mastery engine uses ---
    "mastery_unlock_threshold": 0.50,     # mastery needed to unlock the next concept
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
    "auto_fallback": True,                # if the AI service fails (billing, outage, rate limit),
                                          # carry on with the offline engine instead of an error
    "model":        "claude-opus-5",
    "effort":       "low",                # per-turn reasoning depth: low keeps the
                                          # conversation responsive; raise for harder material
    "extraction_effort": "low",           # concept-map and story build
    "story_model":  "claude-sonnet-5",    # the story is narration, not judgement: a faster model
                                          # writes it in about half the time (Urdu especially)
    "max_tokens":   4000,

    # --- safety ---
    "rate_limit_per_min": 20,
    "max_upload_mb":      8,
    "daily_turn_cap":     1500,           # spend ceiling: guide turns per rolling 24 hours
    "retention_days":     30,             # learner data older than this is deleted
}

# Settings the admin screen exposes: (key, widget, options, label).
#   select -> options is the list of allowed values
#   number -> options is (min, max, step); integer steps give integer values
#   bool   -> options is None
#   text   -> options is the maximum length
SCHEMA = [
    ("learner_level", "select", ["beginner", "intermediate", "advanced"], "Learner level"),
    ("language", "select", ["en", "ur", "mixed", "roman"], "Language"),
    ("tone", "select", ["formal", "friendly", "playful"], "Tone"),
    ("pace", "select", ["slow", "normal", "fast"], "Pace"),
    ("learner_profile", "text", 160, "Learner profile (who is learning)"),
    ("constraints", "text", 240, "Operating constraint (time, device, setting)"),
    ("story_intro", "bool", None, "Illustrated story intro"),
    ("default_mode", "select", ["story", "challenge", "tour", "deep"], "Default learning mode"),
    ("difficulty_curve", "select", ["gentle", "adaptive", "steep"], "Difficulty curve"),
    ("response_length", "select", ["short", "medium", "long"], "Response length"),
    ("custom_rules", "text", 400, "Extra rules for the tutor"),
    ("mastery_unlock_threshold", "number", (0, 1, 0.05), "Unlock threshold"),
    ("mastery_mastered_at", "number", (0, 1, 0.05), "Mastered at"),
    ("hint_penalty", "number", (0, 0.5, 0.01), "Hint penalty"),
    ("xp_per_turn", "number", (0, 100, 1), "XP per turn"),
    ("xp_bonus_no_hint", "number", (0, 50, 1), "XP bonus (no hint)"),
    ("strict_grounding", "bool", None, "Strict grounding"),
    ("require_citations", "bool", None, "Require citations"),
    ("urdu_transliteration", "bool", None, "Roman Urdu alongside script"),
    ("demo_mode", "bool", None, "Offline engine only (no API)"),
    ("auto_fallback", "bool", None, "Fall back to offline engine if the AI service fails"),
    ("model", "select", ["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"], "Model"),
    ("story_model", "select", ["claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5"], "Model for the story"),
    ("effort", "select", ["low", "medium", "high", "xhigh"], "Reasoning effort (per turn)"),
    ("extraction_effort", "select", ["low", "medium", "high"], "Reasoning effort (map and story)"),
    ("max_tokens", "number", (256, 16000, 256), "Max response tokens"),
    ("rate_limit_per_min", "number", (1, 120, 1), "Rate limit / min"),
    ("max_upload_mb", "number", (1, 8, 1), "Max upload (MB)"),
    ("daily_turn_cap", "number", (10, 20000, 10), "Daily turn cap"),
    ("retention_days", "number", (1, 365, 1), "Data retention (days)"),
]

LANGUAGE_NAMES = {"en": "English", "ur": "Urdu", "mixed": "English + Urdu (code-switching)",
                  "roman": "Roman Urdu (Urdu in the Latin alphabet)"}

# What an unauthenticated learner's browser is told. Model, limits and caps stay server-side.
PUBLIC_KEYS = ("language", "learner_level", "tone", "pace", "default_mode", "story_intro",
               "mechanics", "mastery_unlock_threshold", "mastery_mastered_at",
               "urdu_transliteration", "demo_mode", "difficulty_curve", "auto_fallback")

_BY_KEY = {k: (kind, opts, label) for k, kind, opts, label in SCHEMA}
_CONTROL = re.compile(r"[\x00-\x1f\x7f<>]")
_TAGS = re.compile(r"<[^<>]{0,120}>")


class ConfigError(ValueError):
    """A submitted setting was not acceptable. The message is safe to show the admin."""


def _coerce(key: str, value):
    kind, opts, label = _BY_KEY[key]
    if kind == "select":
        if value not in opts:
            raise ConfigError(f"{label}: choose one of {', '.join(opts)}.")
        return value
    if kind == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return value.lower() == "true"
        raise ConfigError(f"{label}: must be on or off.")
    if kind == "number":
        lo, hi, step = opts
        if isinstance(value, bool):
            raise ConfigError(f"{label}: must be a number.")
        try:
            n = float(value)
        except (TypeError, ValueError):
            raise ConfigError(f"{label}: must be a number.") from None
        if math.isnan(n) or math.isinf(n) or not lo <= n <= hi:
            raise ConfigError(f"{label}: must be between {lo} and {hi}.")
        return int(round(n)) if float(step).is_integer() else round(n, 4)
    if kind == "text":
        if not isinstance(value, str):
            raise ConfigError(f"{label}: must be text.")
        # Angle brackets are how content would try to close a prompt block, so they never
        # make it into a setting that is later placed inside one. Whole tags go first, so
        # "<b>5</b> minutes" reads "5 minutes" rather than "b 5 /b minutes".
        cleaned = " ".join(_CONTROL.sub(" ", _TAGS.sub(" ", value)).split())
        if len(cleaned) > opts:
            raise ConfigError(f"{label}: keep it under {opts} characters.")
        return cleaned
    raise ConfigError(f"{label}: unsupported setting.")


def validate(patch: dict) -> dict:
    """The patch, cleaned and coerced. Raises ConfigError naming every bad field."""
    if not isinstance(patch, dict):
        raise ConfigError("Settings must be sent as an object.")
    clean, problems = {}, []
    for k, v in patch.items():
        if k == "mechanics":
            if not isinstance(v, dict):
                problems.append("Game mechanics: must be a set of on/off switches.")
                continue
            clean["mechanics"] = {mk: bool(mv) for mk, mv in v.items()
                                  if mk in DEFAULTS["mechanics"]}
        elif k in _BY_KEY:
            try:
                clean[k] = _coerce(k, v)
            except ConfigError as e:
                problems.append(str(e))
    if clean.get("mastery_unlock_threshold") is not None and \
            clean.get("mastery_mastered_at") is not None and \
            clean["mastery_unlock_threshold"] > clean["mastery_mastered_at"]:
        problems.append("Unlock threshold cannot be higher than the mastered-at level.")
    if problems:
        raise ConfigError(" ".join(problems))
    return clean


def current() -> dict:
    """Stored settings layered over the defaults. A stored value that no longer validates
    is ignored rather than trusted, so an old or hand-edited row cannot break the app."""
    cfg = dict(DEFAULTS)
    cfg["mechanics"] = dict(DEFAULTS["mechanics"])
    stored = db.get_setting("config", {}) or {}
    for k, v in stored.items():
        if k == "mechanics" and isinstance(v, dict):
            cfg["mechanics"].update({mk: bool(mv) for mk, mv in v.items()
                                     if mk in DEFAULTS["mechanics"]})
        elif k in _BY_KEY:
            try:
                cfg[k] = _coerce(k, v)
            except ConfigError:
                continue
    return cfg


def public() -> dict:
    cfg = current()
    return {k: cfg[k] for k in PUBLIC_KEYS}


def updated_at() -> dict:
    """When each setting was last changed by an admin. A learner's own choice for the same
    setting only stands if it is newer than this."""
    return (db.get_setting("config", {}) or {}).get("_at", {})


def update(patch: dict) -> dict:
    clean = validate(patch)
    stored = db.get_setting("config", {}) or {}
    before = current()
    stamps = dict(stored.get("_at", {}))
    now = time.time()
    for k, v in clean.items():
        if k == "mechanics":
            merged = dict(stored.get("mechanics", {}))
            merged.update(v)
            stored["mechanics"] = merged
        else:
            stored[k] = v
            # only a real change counts, so saving the untouched form does not overrule
            # what a learner chose for themselves a moment ago
            if before.get(k) != v:
                stamps[k] = now
    stored["_at"] = stamps
    db.set_setting("config", stored)
    db.log_event("info", "config updated", {"keys": sorted(clean.keys())})
    return current()


def reset():
    now = time.time()
    db.set_setting("config", {"_at": {k: now for k in DEFAULTS}})
    db.log_event("info", "config reset to defaults")
    return current()
