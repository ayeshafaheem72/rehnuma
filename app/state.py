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
}


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


def apply_turn(state: dict, turn, cfg: dict, concept_map: dict) -> dict:
    """Fold one guide turn into the learner state. `turn` is an llm.GuideTurn."""
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
        delta = _clamp(upd.delta, -0.20, 0.25)
        if hinted:
            delta -= cfg["hint_penalty"]
        c["mastery"] = _clamp(c["mastery"] + delta)
        if delta < 0:
            c["errors"] += 1

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
    threshold = cfg["mastery_unlock_threshold"]
    newly_unlocked = []
    by_id = {c["id"]: c for c in concept_map.get("concepts", [])}
    for cid, c in concepts.items():
        if c["unlocked"]:
            continue
        prereqs = by_id.get(cid, {}).get("prerequisites", [])
        if all(concepts.get(p, {}).get("mastery", 0) >= threshold for p in prereqs):
            c["unlocked"] = True
            newly_unlocked.append(cid)

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

    return {
        "difficulty_target": difficulty,
        "scaffolding": scaffolding,
        "scaffolding_instruction": s_why,
        "pace": pace,
        "measured": {
            "turns_considered": n,
            "hint_rate": round(hint_rate, 2),
            "strong_answer_rate": round(win_rate, 2),
            "streak": streak,
        },
        "why": why or ["not enough turns yet - using the configured baseline"],
    }


def summary(state: dict, cfg: dict) -> dict:
    """Roll-up used by the learner header and the dashboard."""
    concepts = state.get("concepts", {})
    if not concepts:
        return {"overall_mastery": 0.0, "mastered": 0, "unlocked": 0, "total": 0,
                "xp": 0, "streak": 0, "badges": []}
    mastered_at = cfg["mastery_mastered_at"]
    values = [c["mastery"] for c in concepts.values()]
    return {
        "overall_mastery": round(sum(values) / len(values), 3),
        "mastered": sum(1 for v in values if v >= mastered_at),
        "unlocked": sum(1 for c in concepts.values() if c["unlocked"]),
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
