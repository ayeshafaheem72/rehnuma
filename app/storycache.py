"""The story is written while the learner is still choosing how to learn.

A story takes as long to write as a reply does, and it stands between the learner and the
first thing they can do. So it starts the moment the concept map exists - in the background,
in the language and at the level the learner is currently set to - and by the time they press
Start it is usually already waiting. If the settings change in between, the key no longer
matches and a fresh one is written instead of serving the wrong language.
"""
import hashlib
import json
import threading

from app import db, llm

_LOCK = threading.Lock()
_CACHE: dict = {}
_MAX_ENTRIES = 48


def _key(source_id: str, cfg: dict) -> tuple:
    block = json.dumps(llm._learner_block(cfg), sort_keys=True, ensure_ascii=False)
    return source_id, hashlib.sha1(block.encode("utf-8")).hexdigest()[:12]


def _work(entry: dict, source_id: str, cmap: dict, cfg: dict):
    try:
        story, usage, latency = llm.build_story(cmap, cfg)
        entry["story"] = story
        db.log_event("info", "story built", {
            "source_id": source_id, "scenes": len(story["scenes"]), "latency_ms": latency,
            **{f"tokens_{k}": v for k, v in llm.usage_dict(usage).items()}})
    except Exception as e:                       # the journey simply starts without one
        entry["error"] = str(e)[:300]
        db.log_event("error", "story failed", {"source_id": source_id, "error": entry["error"]})
    finally:
        entry["done"].set()


def prefetch(source_id: str, cmap: dict, cfg: dict) -> dict:
    key = _key(source_id, cfg)
    with _LOCK:
        entry = _CACHE.get(key)
        if entry is not None:
            return entry
        if len(_CACHE) >= _MAX_ENTRIES:
            _CACHE.pop(next(iter(_CACHE)))
        entry = {"done": threading.Event(), "story": None, "error": None}
        _CACHE[key] = entry
    threading.Thread(target=_work, args=(entry, source_id, cmap, cfg), daemon=True).start()
    return entry


def get(source_id: str, cmap: dict, cfg: dict, timeout: float = 90.0):
    """The story for this source and these settings, waiting for it if it is still being
    written. None if it failed or ran out of time - never an exception."""
    entry = prefetch(source_id, cmap, cfg)
    entry["done"].wait(timeout)
    if entry["story"] is None:
        with _LOCK:                              # forget failures so a retry can succeed
            if _CACHE.get(_key(source_id, cfg)) is entry and entry["done"].is_set():
                _CACHE.pop(_key(source_id, cfg), None)
        return None
    return entry["story"]
