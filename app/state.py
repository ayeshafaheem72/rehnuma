"""The learner model.

Claude judges each turn and proposes mastery changes; this module is the bookkeeping that
turns those judgements into progress - mastery per concept, XP, streaks, unlocks, badges.
Keeping the arithmetic here (rather than trusting the model with running totals) means the
numbers on the dashboard are reproducible and auditable.
"""
import time

BADGES = {
    "first_steps":  "Took the first turn",
    "first_unlock": "Unlocked a new concept",
    "on_a_roll":    "Three turns in a row without a hint",
    "own_words":    "Explained an idea in their own words",
    "mastered_one": "Brought a concept to mastery",
    "boss_slayer":  "Cleared a boss challenge",
    "curious":      "Asked a question that ran ahead of the lesson",
    "storyteller":  "Followed the whole story",
}

# The settings a learner may override for themselves from their own screen. Whichever was
# changed most recently - the learner's choice or the admin's - is the one that applies.
PREF_KEYS = ("language", "learner_level", "tone", "pace", "constraints", "learner_profile")


def new_state(concept_map: dict) -> dict:
    concepts = {}
    for c in concept_map.get("concepts", []):
        concepts[c["id"]] = {
            "title": c["title"],
            "mastery": 0.0,
            "baseline": 0.0,          # mastery at first contact, for the outcome report
            "exposures": 0,
            "errors": 0,
            "self_corrections": 0,
            "hints_used": 0,
            "last_turn": 0,           # when it was last touched, for scheduling a review
            "unlocked": not c.get("prerequisites"),
        }
    return {
        "concepts": concepts,
        "xp": 0,
        "streak": 0,
        "best_streak": 0,
        "turns": 0,
        "badges": [],
        "signal_log": [],             # the evidence feed the dashboard renders
        "started_at": time.time(),
        "updated_at": time.time(),
    }


def _clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def effective(cfg: dict, st: dict, cfg_at: dict | None = None) -> dict:
    """The settings this learner is actually taught under: the admin's, with their own
    changes laid on top - unless the admin changed that setting after they did."""
    prefs = st.get("prefs") or {}
    if not prefs:
        return cfg
    out = dict(cfg)
    for k, v in prefs.items():
        if k in PREF_KEYS and (cfg_at or {}).get(k, 0) <= (st.get("prefs_at") or {}).get(k, 0):
            out[k] = v
    return out


def public_state(st: dict) -> dict:
    """What the tutor is shown. The evidence log and the rest of the bookkeeping stay
    behind: they are for the dashboard, and sending them every turn only costs tokens."""
    return {
        "concepts": {cid: {k: c[k] for k in ("title", "mastery", "exposures", "unlocked",
                                             "hints_used")}
                     for cid, c in st.get("concepts", {}).items()},
        "xp": st.get("xp", 0), "streak": st.get("streak", 0), "turns": st.get("turns", 0),
    }


def _unlocks(state: dict, cfg: dict, concept_map: dict) -> list:
    """Open every concept whose prerequisites are understood. A tour only asks that they
    have been visited: its point is the shape of the subject, not depth in one corner."""
    threshold = cfg["mastery_unlock_threshold"]
    touring = state.get("mode") == "tour"
    concepts = state["concepts"]
    newly = []
    by_id = {c["id"]: c for c in concept_map.get("concepts", [])}
    for cid, c in concepts.items():
        if c["unlocked"]:
            continue
        prereqs = by_id.get(cid, {}).get("prerequisites", [])
        ready = all(
            (concepts.get(p, {}).get("exposures", 0) >= 1) if touring
            else (concepts.get(p, {}).get("mastery", 0) >= threshold)
            for p in prereqs)
        if ready:
            c["unlocked"] = True
            newly.append(cid)
    return newly


def apply_turn(state: dict, turn, cfg: dict, concept_map: dict, opener: bool = False) -> dict:
    """Fold one guide turn into the learner state. `turn` is an llm.GuideTurn.

    The opening beat answers nobody, so it has nothing to judge: whatever signals or
    mastery changes the model attached to it are discarded rather than credited.
    """
    if opener:
        turn.signals, turn.mastery_updates = [], []

    state["turns"] = state.get("turns", 0) + 1
    concepts = state["concepts"]

    signals = {s.name: s for s in turn.signals}
    hinted = turn.hint_given or (signals.get("hint_dependency") and
                                 signals["hint_dependency"].detected)

    # --- mastery ---
    for upd in turn.mastery_updates:
        c = concepts.get(upd.concept_id)
        if not c:
            continue
        if c["exposures"] == 0:
            c["baseline"] = c["mastery"]
        c["exposures"] += 1
        c["last_turn"] = state["turns"]
        delta = _clamp(upd.delta, -0.20, 0.25)
        if hinted:
            delta -= cfg["hint_penalty"]
        c["mastery"] = _clamp(c["mastery"] + delta)
        if delta < 0:
            c["errors"] += 1
        # a learner who asks about a locked concept and shows they can use it has
        # jumped ahead; the board should follow them rather than show it as locked
        if delta > 0 and not c["unlocked"]:
            c["unlocked"] = True

    # a teach beat counts as the concept having been taught even though nothing was judged
    taught = concepts.get(turn.concept_id)
    if turn.interaction_type == "teach" and taught and taught["exposures"] == 0:
        taught["exposures"] = 1
        taught["last_turn"] = state["turns"]

    # --- signal bookkeeping ---
    touched = turn.mastery_updates[0].concept_id if turn.mastery_updates else turn.concept_id
    if signals.get("self_corrected") and signals["self_corrected"].detected:
        if touched in concepts:
            concepts[touched]["self_corrections"] += 1
    if hinted and touched in concepts:
        concepts[touched]["hints_used"] += 1

    for s in turn.signals:
        if s.detected:
            state["signal_log"].append({
                "signal": s.name,
                "evidence": s.evidence,
                "concept_id": touched,
                "at": time.time(),
            })
    state["signal_log"] = state["signal_log"][-100:]

    # --- streak ---
    if not opener:
        if hinted:
            state["streak"] = 0
        else:
            state["streak"] = state.get("streak", 0) + 1
            state["best_streak"] = max(state.get("best_streak", 0), state["streak"])

    # --- xp ---
    if cfg["mechanics"].get("xp", True):
        gained = max(0, int(turn.xp_awarded)) or cfg["xp_per_turn"]
        if not hinted:
            gained += cfg["xp_bonus_no_hint"]
        if cfg["mechanics"].get("streaks", True) and state["streak"] >= 3:
            gained = int(gained * 1.5)
        state["xp"] = state.get("xp", 0) + gained

    # --- unlocks ---
    newly_unlocked = _unlocks(state, cfg, concept_map)

    # --- badges ---
    def award(name):
        if name not in state["badges"]:
            state["badges"].append(name)

    if state["turns"] == 1:
        award("first_steps")
    if newly_unlocked:
        award("first_unlock")
    if state["streak"] >= 3:
        award("on_a_roll")
    if turn.interaction_type == "explain_it" and not hinted:
        award("own_words")
    if turn.interaction_type == "boss" and not hinted:
        award("boss_slayer")
    if signals.get("asked_deepening_question") and signals["asked_deepening_question"].detected:
        award("curious")
    if any(c["mastery"] >= cfg["mastery_mastered_at"] for c in concepts.values()):
        award("mastered_one")

    # rolling window of measured outcomes - this is what drives adaptation
    if not opener:
        positives = sum(1 for sg in turn.signals
                        if sg.detected and sg.name != "hint_dependency")
        state.setdefault("recent", []).append({
            "hinted": bool(hinted),
            "positives": positives,
            "delta": round(sum(u.delta for u in turn.mastery_updates), 3),
            "kind": turn.interaction_type,
        })
        state["recent"] = state["recent"][-8:]

    state["updated_at"] = time.time()
    state["_newly_unlocked"] = newly_unlocked
    return state


LEVEL_BASE = {"beginner": 2, "intermediate": 3, "advanced": 4}


def focus_concept(state: dict, cfg: dict):
    """The concept the next beat should be about, decided here so that the board, the
    unlocks and the tutor all agree on it."""
    unlock_at, mastered_at = cfg["mastery_unlock_threshold"], cfg["mastery_mastered_at"]
    open_ = [(cid, c) for cid, c in state.get("concepts", {}).items()
             if c["unlocked"] and c["mastery"] < mastered_at]
    if not open_:
        return None
    if state.get("mode") == "tour":
        for cid, c in open_:                    # keep moving to whatever is still unseen
            if c["exposures"] == 0:
                return cid
    for cid, c in open_:                        # the earliest concept still short of the bar
        if c["mastery"] < unlock_at:
            return cid
    for cid, c in open_:
        if c["exposures"] == 0:
            return cid
    return min(open_, key=lambda kv: kv[1]["mastery"])[0]


def review_due(state: dict, cfg: dict, focus):
    """A concept the learner cleared a while ago and has not touched since - the natural
    subject of a retrieval beat, and the only honest way to observe retention."""
    turns = state.get("turns", 0)
    unlock_at, mastered_at = cfg["mastery_unlock_threshold"], cfg["mastery_mastered_at"]
    for cid, c in state.get("concepts", {}).items():
        if cid != focus and unlock_at <= c["mastery"] < mastered_at \
                and turns - c.get("last_turn", 0) >= 4:
            return cid
    return None


def adaptation(state: dict, cfg: dict) -> dict:
    """Turn measured performance into concrete teaching parameters.

    This is the adaptation mechanism, deliberately kept in code rather than left to
    the model's discretion: the same inputs always produce the same instruction, and
    every decision carries the reason that produced it, so it can be audited and
    demonstrated rather than asserted.
    """
    recent = state.get("recent", [])[-5:]
    n = len(recent)
    hint_rate = (sum(1 for r in recent if r["hinted"]) / n) if n else 0.0
    win_rate = (sum(1 for r in recent if r["positives"] >= 2 and not r["hinted"]) / n) if n else 0.0
    streak = state.get("streak", 0)

    base = LEVEL_BASE.get(cfg.get("learner_level", "beginner"), 2)
    curve = cfg.get("difficulty_curve", "adaptive")

    step, why = 0, []
    if n >= 2:
        if hint_rate >= 0.40:
            step -= 1
            why.append(f"needed hints on {int(hint_rate*100)}% of recent turns")
        if win_rate >= 0.60 and hint_rate == 0:
            step += 1
            why.append(f"answered {int(win_rate*100)}% of recent turns strongly, unaided")
        if streak >= 4:
            step += 1
            why.append(f"{streak} turns in a row without a hint")
    if curve == "gentle":
        step = min(step, 0)
    elif curve == "steep":
        step += 1

    difficulty = max(1, min(5, base + step))

    if hint_rate >= 0.40:
        scaffolding, s_why = "high", "break the idea into steps and give a worked example first"
    elif hint_rate <= 0.15 and streak >= 3:
        scaffolding, s_why = "low", "drop the scaffolding, ask directly, let them do the work"
    else:
        scaffolding, s_why = "normal", "explain, then ask"

    pace = cfg.get("pace", "normal")
    if n >= 3:
        if hint_rate >= 0.40:
            pace = "slow"
        elif streak >= 4 and hint_rate == 0:
            pace = "fast"

    concepts = state.get("concepts", {})
    focus = focus_concept(state, cfg)
    return {
        "difficulty_target": difficulty,
        "scaffolding": scaffolding,
        "scaffolding_instruction": s_why,
        "pace": pace,
        "focus_concept": focus,
        "focus_title": concepts.get(focus, {}).get("title") if focus else None,
        "unlocked_concepts": [cid for cid, c in concepts.items() if c["unlocked"]],
        "review_due": review_due(state, cfg, focus),
        "measured": {
            "turns_considered": n,
            "hint_rate": round(hint_rate, 2),
            "strong_answer_rate": round(win_rate, 2),
            "streak": streak,
        },
        "why": why or ["not enough turns yet - using the configured baseline"],
    }


def summary(state: dict, cfg: dict) -> dict:
    """Roll-up used by the learner header and the dashboard.

    overall_mastery is the average over the concepts the learner has actually met. Averaged
    over the whole map it would read as a few percent for most of a session, which describes
    how much is left to do, not how well this person understands what they have done;
    coverage carries that other half.
    """
    concepts = state.get("concepts", {})
    if not concepts:
        return {"overall_mastery": 0.0, "coverage": 0.0, "mastered": 0, "unlocked": 0,
                "touched": 0, "total": 0, "xp": 0, "streak": 0, "best_streak": 0,
                "turns": 0, "badges": []}
    mastered_at = cfg["mastery_mastered_at"]
    values = [c["mastery"] for c in concepts.values()]
    met = [c["mastery"] for c in concepts.values() if c["exposures"] > 0]
    mastered = sum(1 for v in values if v >= mastered_at)
    return {
        "overall_mastery": round(sum(met) / len(met), 3) if met else 0.0,
        "coverage": round(mastered / len(values), 3),
        "mastered": mastered,
        "unlocked": sum(1 for c in concepts.values() if c["unlocked"]),
        "touched": len(met),
        "total": len(concepts),
        "xp": state.get("xp", 0),
        "streak": state.get("streak", 0),
        "best_streak": state.get("best_streak", 0),
        "turns": state.get("turns", 0),
        "badges": state.get("badges", []),
    }


def outcome_report(state: dict, cfg: dict) -> list:
    """Before/after per concept - the 'measurable learning outcome' the rubric asks for."""
    rows = []
    for cid, c in state.get("concepts", {}).items():
        rows.append({
            "concept_id": cid,
            "concept": c["title"],
            "baseline": round(c.get("baseline", 0.0), 3),
            "current": round(c["mastery"], 3),
            "gain": round(c["mastery"] - c.get("baseline", 0.0), 3),
            "exposures": c["exposures"],
            "errors": c["errors"],
            "self_corrections": c["self_corrections"],
            "hints_used": c["hints_used"],
            "status": ("mastered" if c["mastery"] >= cfg["mastery_mastered_at"]
                       else "in progress" if c["unlocked"] else "locked"),
        })
    return sorted(rows, key=lambda r: r["concept_id"])
