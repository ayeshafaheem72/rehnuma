"""Rehnuma - an AI Learning Experience Engine.

One service: it serves the pages and the API. Everything the panel touches lives here.

Handlers that call the model are plain `def`, not `async def`: FastAPI runs those on a worker
thread. An `async def` that makes a ten-second blocking call freezes the whole event loop,
and with it every other learner and the health check Render polls.
"""
import csv
import html
import io
import json
import logging
import os
import queue
import threading
import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse, RedirectResponse,
                               StreamingResponse)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from starlette.concurrency import run_in_threadpool

load_dotenv()

from app import config, db, ingest, llm, security, state, storycache  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format='{"t":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
)
log = logging.getLogger("rehnuma")

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
STARTED_AT = time.time()
VERSION = "1.4"


@asynccontextmanager
async def lifespan(_app):
    db.init()
    if security.IS_PROD and not os.environ.get("ADMIN_PASSWORD"):
        db.log_event("warn", "ADMIN_PASSWORD is not set: admin sign-in is disabled")
    purged = db.purge_older_than(config.current()["retention_days"])
    db.log_event("info", "service started", {"version": VERSION, "purged": purged})
    log.info("rehnuma started")
    yield


limiter = Limiter(key_func=security.client_ip)
app = FastAPI(title="Rehnuma", docs_url=None, redoc_url=None, openapi_url=None,
              lifespan=lifespan)
app.state.limiter = limiter
app.add_middleware(security.SecurityHeadersMiddleware)


@app.exception_handler(RateLimitExceeded)
async def too_fast(request: Request, exc: RateLimitExceeded):
    # the page reads `detail`, so a limit hit reads as advice rather than as a failure
    return JSONResponse(
        {"detail": "That is faster than the service allows. Give it a few seconds and try again."},
        status_code=429, headers={"Retry-After": "10"})


def turn_limit():
    return f"{config.current()['rate_limit_per_min']}/minute"


def check_budget(cfg: dict):
    """The spend ceiling. Rate limits stop one caller; this stops a crowd of them."""
    if db.count_guide_turns_since(time.time() - 86400) >= cfg["daily_turn_cap"]:
        db.log_event("warn", "daily turn cap reached", {"cap": cfg["daily_turn_cap"]})
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Today's practice allowance for this service has been used up. "
                            "Please try again tomorrow.")


# ------------------------------------------------------------ pages

@app.get("/")
def learner_page():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/admin")
def admin_page():
    return FileResponse(os.path.join(STATIC_DIR, "admin.html"))


@app.get("/health")
def health(request: Request):
    """Public callers learn only that the service is up. Model, key and counts are for the
    admin: they describe how the deployment is run, which is not the public's business."""
    out = {"status": "ok", "uptime_s": round(time.time() - STARTED_AT, 1), "version": VERSION}
    if security.is_admin(request):
        cfg = config.current()
        out.update({
            "model": cfg["model"],
            "demo_mode": cfg["demo_mode"],
            "api_key_present": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "sources": len(db.list_sources()),
            "learners": len(db.list_learners()),
        })
    return out


# ------------------------------------------------------------ content in

def public_map(payload: dict) -> dict:
    """What the browser is sent. `numbers` exists only so the story can be checked."""
    return {k: v for k, v in payload.items() if k != "numbers"}


def _too_big(request: Request, limit: int):
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit + 1_048_576:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"That file is larger than {limit // 1_048_576} MB. "
                            "Please upload a smaller one.")


def _build_source(text: str, title: str, truncated: bool):
    cfg = config.current()
    try:
        payload, usage, latency = llm.build_concept_map(text, title)
    except ValueError as e:
        db.log_event("warn", "concept map rejected", {"reason": str(e)[:200]})
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "That material did not give enough teachable, quotable content. "
                            "A longer or more text-heavy source works better.")
    except Exception as e:
        db.log_event("error", "concept map failed", {"error": str(e)[:400]})
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            "The concept map could not be built. Please try again.")
    sid = db.save_source(title, payload, len(text))
    u = llm.usage_dict(usage)
    db.log_event("info", "source ingested", {
        "source_id": sid, "title": title, "chars": len(text),
        "concepts": len(payload["concepts"]), "latency_ms": latency,
        "tokens_in": u["in"], "tokens_out": u["out"]})
    if cfg["story_intro"]:
        # written in the background while the learner reads the map and picks a mode
        storycache.prefetch(sid, payload, cfg)
    return {"source_id": sid, "concept_map": public_map(payload), "latency_ms": latency,
            "chars": len(text), "truncated": truncated, "title": title,
            "grounding": payload.get("grounding")}


@app.post("/api/source/upload")
@limiter.limit("10/minute")
async def upload_source(request: Request, file: UploadFile = File(...)):
    limit = min(security.MAX_UPLOAD_BYTES, config.current()["max_upload_mb"] * 1_048_576)
    _too_big(request, limit)
    data = await file.read()
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"That file is larger than {limit // 1_048_576} MB. "
                            "Please upload a smaller one.")
    try:
        text, truncated = await run_in_threadpool(ingest.from_upload, file.filename, data)
    except ingest.IngestError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    title = security.clean_text(ingest.title_from(file.filename, text), 120) or "Untitled"
    return await run_in_threadpool(_build_source, text, title, truncated)


class PasteIn(BaseModel):
    title: str = ""
    text: str


@app.post("/api/source/paste")
@limiter.limit("10/minute")
def paste_source(request: Request, body: PasteIn):
    raw = security.clean_text(body.text, security.MAX_PASTE_CHARS)
    try:
        text, truncated = ingest.from_text(raw)
    except ingest.IngestError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    title = security.clean_text(body.title, 120) or ingest.title_from("", text)
    return _build_source(text, title, truncated)


class UrlIn(BaseModel):
    url: str
    title: str = ""


@app.post("/api/source/url")
@limiter.limit("10/minute")
def url_source(request: Request, body: UrlIn):
    url = security.clean_text(body.url, 2000)
    try:
        text, truncated = ingest.from_url(url)
    except ingest.IngestError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    title = security.clean_text(body.title, 120) or ingest.title_from("", text)
    return _build_source(text, title, truncated)


@app.get("/api/sources")
def sources(_=Depends(security.require_admin)):
    return {"sources": db.list_sources()}


# ------------------------------------------------------------ learning

MODES = {"story", "challenge", "tour", "deep"}


def _turn_payload(turn, learner_state: dict, cfg: dict):
    return {
        "message": turn.message,
        "interaction_type": turn.interaction_type,
        "concept_id": turn.concept_id,
        "choices": [c.model_dump() for c in turn.choices],
        "citations": [c.model_dump() for c in turn.citations],
        "off_source": turn.off_source,
        "hint_given": turn.hint_given,
        "signals": [s.model_dump() for s in turn.signals if s.detected],
        "mastery_updates": [m.model_dump() for m in turn.mastery_updates],
        "state": {**state.public_state(learner_state),
                  "_newly_unlocked": learner_state.get("_newly_unlocked", [])},
        "summary": state.summary(learner_state, cfg),
        "newly_unlocked": learner_state.get("_newly_unlocked", []),
        "adaptation": state.adaptation(learner_state, cfg),
        "effective": _effective_view(cfg),
    }


def _effective_view(cfg: dict) -> dict:
    return {k: cfg.get(k, "") for k in state.PREF_KEYS}


def _signals_dict(turn, usage=None):
    out = {
        "signals": [s.model_dump() for s in turn.signals if s.detected],
        "mastery_updates": [m.model_dump() for m in turn.mastery_updates],
        "interaction_type": turn.interaction_type,
        "off_source": turn.off_source,
        "hint_given": turn.hint_given,
        "citations": len(turn.citations),
    }
    if usage is not None:
        u = llm.usage_dict(usage)
        out["cache_read"], out["cache_write"] = u["cache_read"], u["cache_write"]
    return out


def _load(learner_id: str):
    """The learner, their source's map and the settings they are taught under."""
    lid = security.safe_id(learner_id)
    learner = db.get_learner(lid)
    if not learner:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That session has expired.")
    src = db.get_source(learner["source_id"])
    if not src:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The source material is gone.")
    cmap = json.loads(src["concept_map"])
    cfg = state.effective(config.current(), learner["state"], config.updated_at())
    return lid, learner, cmap, cfg


def _finish(lid: str, learner: dict, turn, usage, latency: int, cmap: dict, cfg: dict,
            opener: bool = False):
    st = state.apply_turn(learner["state"], turn, cfg, cmap, opener=opener)
    db.save_learner(lid, learner["label"], learner["source_id"], st)
    u = llm.usage_dict(usage)
    db.save_turn(lid, "guide", turn.message, _signals_dict(turn, usage), turn.concept_id,
                 latency, u["in"], u["out"])
    out = _turn_payload(turn, st, cfg)
    out["latency_ms"] = latency
    return out


def _run_opening(lid: str, learner: dict, cmap: dict, cfg: dict):
    try:
        turn, usage, latency = llm.run_turn(cmap, learner["state"], [], "", cfg)
    except Exception as e:
        db.log_event("error", "opening turn failed", {"error": str(e)[:400]})
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            "Could not start the session. Please try again.")
    return _finish(lid, learner, turn, usage, latency, cmap, cfg, opener=True)


class StartIn(BaseModel):
    source_id: str
    label: str = "Learner"
    mode: str = ""              # story | challenge | tour | deep; blank falls back to config
    language: str = ""          # optional per-learner choices made on the setup screen
    learner_level: str = ""
    constraints: str = ""
    defer_opening: bool = False  # true: return as soon as the story is ready, fetch the opener next


@app.post("/api/session/start")
@limiter.limit("20/minute")
def start_session(request: Request, body: StartIn):
    sid = security.safe_id(body.source_id)
    src = db.get_source(sid)
    if not src:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That source no longer exists.")
    cmap = json.loads(src["concept_map"])
    base = config.current()
    check_budget(base)

    st = state.new_state(cmap)
    # how this learner wants to be taught - the prompt layer reads it off the state
    st["mode"] = body.mode if body.mode in MODES else base["default_mode"]
    chosen = {k: v for k, v in (("language", body.language),
                                ("learner_level", body.learner_level),
                                ("constraints", body.constraints)) if v}
    if chosen:
        try:
            st["prefs"] = config.validate(chosen)
        except config.ConfigError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
        st["prefs_at"] = {k: time.time() for k in st["prefs"]}
    cfg = state.effective(base, st, config.updated_at())
    st["language"] = cfg["language"]

    story = None
    # Only a client that will play the story (it asks for the opening separately) waits
    # for one; anything else would pay the wait for a story it never shows.
    if cfg["story_intro"] and body.defer_opening:
        story = storycache.get(sid, cmap, cfg)
        if story:
            st["story"] = {
                "title": story["title"], "character": story["character"],
                "setting": story["setting"], "scene_titles": [s["title"] for s in story["scenes"]],
                "scenes": len(story["scenes"]), "viewed": 0, "completed": False,
                "skipped": False,
            }

    lid = db.new_id()
    label = security.clean_text(body.label, 60) or "Learner"
    db.save_learner(lid, label, sid, st)
    learner = {"id": lid, "label": label, "source_id": sid, "state": st}

    out = {"learner_id": lid, "concept_map": public_map(cmap), "story": story,
           "mode": st["mode"], "effective": _effective_view(cfg)}
    if body.defer_opening:
        out.update({"opening": None, "summary": state.summary(st, cfg),
                    "adaptation": state.adaptation(st, cfg)})
        return out
    out.update(_run_opening(lid, learner, cmap, cfg))
    return out


@app.post("/api/session/{learner_id}/opening")
@limiter.limit("20/minute")
def opening(request: Request, learner_id: str):
    lid, learner, cmap, cfg = _load(learner_id)
    if learner["state"].get("turns", 0) > 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "That session has already begun.")
    check_budget(cfg)
    return _run_opening(lid, learner, cmap, cfg)


class TurnIn(BaseModel):
    message: str


def _prepare_turn(request: Request, learner_id: str, body: TurnIn):
    lid, learner, cmap, cfg = _load(learner_id)
    check_budget(cfg)
    message = security.clean_text(body.message, security.MAX_MESSAGE_CHARS)
    if not message:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Say something first.")
    history = [{"role": t["role"], "content": t["content"]} for t in db.get_turns(lid)]
    db.save_turn(lid, "learner", message)
    return lid, learner, cmap, cfg, message, history


@app.post("/api/session/{learner_id}/turn")
@limiter.limit(turn_limit)
def take_turn(request: Request, learner_id: str, body: TurnIn):
    lid, learner, cmap, cfg, message, history = _prepare_turn(request, learner_id, body)
    try:
        turn, usage, latency = llm.run_turn(cmap, learner["state"], history, message, cfg)
    except Exception as e:
        db.log_event("error", "turn failed", {"learner": lid, "error": str(e)[:400]})
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            "That response did not come through. Please try again.")
    return _finish(lid, learner, turn, usage, latency, cmap, cfg)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/session/{learner_id}/turn/stream")
@limiter.limit(turn_limit)
def take_turn_stream(request: Request, learner_id: str, body: TurnIn):
    """The same turn, delivered as it is written: `token` events carry the reply's words,
    then one `final` event carries everything else (citations, choices, mastery, board).

    The work runs on its own thread and feeds a queue, so a learner who closes the tab
    mid-reply still gets their progress saved instead of losing the turn."""
    lid, learner, cmap, cfg, message, history = _prepare_turn(request, learner_id, body)
    events: queue.Queue = queue.Queue()

    def work():
        try:
            turn, usage, latency = llm.run_turn_stream(
                cmap, learner["state"], history, message, cfg,
                lambda piece: events.put(("token", {"t": piece})))
            events.put(("final", _finish(lid, learner, turn, usage, latency, cmap, cfg)))
        except Exception as e:
            db.log_event("error", "turn failed", {"learner": lid, "error": str(e)[:400]})
            events.put(("error", {"detail": "That response did not come through. "
                                            "Please try again."}))
        finally:
            events.put(None)

    threading.Thread(target=work, daemon=True).start()

    def frames():
        while True:
            try:
                item = events.get(timeout=15)
            except queue.Empty:
                yield ": keep-alive\n\n"          # stops an idle proxy closing the stream
                continue
            if item is None:
                return
            yield _sse(*item)

    return StreamingResponse(frames(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.get("/api/session/{learner_id}")
def get_session(learner_id: str):
    lid, learner, cmap, cfg = _load(learner_id)
    st = learner["state"]
    return {
        "learner_id": lid,
        "label": learner["label"],
        "state": {**state.public_state(st), "_currentConcept": None},
        "summary": state.summary(st, cfg),
        "adaptation": state.adaptation(st, cfg),
        "concept_map": public_map(cmap),
        "mode": st.get("mode"),
        "effective": _effective_view(cfg),
        "history": [{"role": t["role"], "content": t["content"], "concept_id": t["concept_id"]}
                    for t in db.get_turns(lid)],
    }


@app.post("/api/session/{learner_id}/prefs")
@limiter.limit("30/minute")
def set_prefs(request: Request, learner_id: str, patch: dict):
    """A learner changes their own language, level, pace, tone or constraint mid-session.
    The next reply obeys it, whatever the admin's defaults say."""
    lid, learner, cmap, cfg = _load(learner_id)
    wanted = {k: v for k, v in patch.items() if k in state.PREF_KEYS}
    try:
        clean = config.validate(wanted)
    except config.ConfigError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    st = learner["state"]
    st.setdefault("prefs", {}).update(clean)
    st.setdefault("prefs_at", {}).update({k: time.time() for k in clean})
    st["language"] = state.effective(config.current(), st, config.updated_at())["language"]
    db.save_learner(lid, learner["label"], learner["source_id"], st)
    db.log_event("info", "learner changed settings", {"keys": sorted(clean)})
    eff = state.effective(config.current(), st, config.updated_at())
    return {"effective": _effective_view(eff), "adaptation": state.adaptation(st, eff)}


class FeedbackIn(BaseModel):
    rating: int
    concept_id: str = ""


@app.post("/api/session/{learner_id}/feedback")
@limiter.limit("60/minute")
def feedback(request: Request, learner_id: str, body: FeedbackIn):
    lid, _l, _c, _cfg = _load(learner_id)
    db.save_feedback(lid, body.rating, security.safe_id(body.concept_id) if body.concept_id
                     else None)
    return {"ok": True}


class EventIn(BaseModel):
    type: str
    viewed: int = 0


@app.post("/api/session/{learner_id}/event")
@limiter.limit("60/minute")
def learner_event(request: Request, learner_id: str, body: EventIn):
    """Engagement the server cannot see for itself: how far through the story they got."""
    lid, learner, _c, _cfg = _load(learner_id)
    st = learner["state"]
    story = st.get("story")
    if story:
        if body.type == "story_progress":
            story["viewed"] = max(story.get("viewed", 0), min(body.viewed, story["scenes"]))
        elif body.type == "story_done":
            story["completed"], story["viewed"] = True, story["scenes"]
            if "storyteller" not in st["badges"]:
                st["badges"].append("storyteller")
        elif body.type == "story_skipped":
            story["skipped"] = True
        db.save_learner(lid, learner["label"], learner["source_id"], st)
    return {"ok": True}


@app.delete("/api/session/{learner_id}")
@limiter.limit("10/minute")
def erase_session(request: Request, learner_id: str):
    """A learner deleting their own session, everything they said included."""
    lid = security.safe_id(learner_id)
    db.log_event("info", "learner erased their session")
    return {"deleted": db.delete_learner(lid)}


# ------------------------------------------------------------ config

@app.get("/api/config")
def read_config(request: Request):
    admin = security.is_admin(request)
    return {
        "config": config.current() if admin else config.public(),
        "schema": [{"key": k, "kind": kind, "options": opts, "label": label}
                   for k, kind, opts, label in config.SCHEMA] if admin else [],
        "is_admin": admin,
    }


@app.post("/api/config")
def write_config(request: Request, patch: dict, _=Depends(security.require_admin)):
    try:
        return {"config": config.update(patch)}
    except config.ConfigError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@app.post("/api/config/reset")
def reset_config(request: Request, _=Depends(security.require_admin)):
    return {"config": config.reset()}


# ------------------------------------------------------------ admin auth

class LoginIn(BaseModel):
    password: str


@app.post("/api/admin/login")
@limiter.limit("5/minute")
def admin_login(request: Request, body: LoginIn):
    if not security.check_password(body.password):
        db.log_event("warn", "failed admin sign-in", {"ip": security.client_ip(request)})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That password is not right.")
    resp = JSONResponse({"ok": True})
    security.grant_admin(resp)
    db.log_event("info", "admin signed in")
    return resp


@app.post("/api/admin/logout")
def admin_logout():
    resp = JSONResponse({"ok": True})
    security.revoke_admin(resp)
    return resp


@app.delete("/api/admin/learner/{learner_id}")
def admin_erase(learner_id: str, _=Depends(security.require_admin)):
    lid = security.safe_id(learner_id)
    db.log_event("info", "admin erased a learner", {"learner": lid})
    return {"deleted": db.delete_learner(lid)}


@app.post("/api/admin/purge")
def admin_purge(_=Depends(security.require_admin)):
    result = db.purge_older_than(config.current()["retention_days"])
    db.log_event("info", "retention purge", result)
    return result


# ------------------------------------------------------------ dashboard

def _percentile(values, pct):
    if not values:
        return 0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((pct / 100) * (len(s) - 1)))))
    return s[k]


WINDOWS = {"1h": 3600, "24h": 86400, "7d": 604800}


def _scope(learner: str, concept: str, since: str):
    """The learners and guide turns a filter selects, shared by every view and export so
    the numbers, the charts and the CSV always agree with each other."""
    learners = db.list_learners()
    guide = [t for t in db.all_turns() if t["role"] == "guide"]
    cutoff = time.time() - WINDOWS[since] if since in WINDOWS else 0.0
    if learner:
        lid = security.safe_id(learner)
        learners = [l for l in learners if l["id"] == lid]
        guide = [t for t in guide if t["learner_id"] == lid]
    if cutoff:
        guide = [t for t in guide if (t["created_at"] or 0) >= cutoff]
        learners = [l for l in learners if (l["updated_at"] or 0) >= cutoff]
    if concept:
        cid = security.safe_id(concept)
        guide = [t for t in guide
                 if t["concept_id"] == cid
                 or any(m.get("concept_id") == cid
                        for m in (t["signals"] or {}).get("mastery_updates", []))]
    return learners, guide, cutoff


_last_purge = [0.0]


def _maybe_purge(cfg: dict):
    if time.time() - _last_purge[0] > 3600:
        _last_purge[0] = time.time()
        db.purge_older_than(cfg["retention_days"])


@app.get("/api/dashboard")
def dashboard(request: Request, _=Depends(security.require_admin),
              learner: str = "", concept: str = "", signal: str = "", since: str = ""):
    """Filterable analytics. Every view below narrows to the same filter set."""
    cfg = config.current()
    _maybe_purge(cfg)
    learners, guide, cutoff = _scope(learner, concept, since)
    if signal:
        guide = [t for t in guide
                 if any(x["name"] == signal for x in (t["signals"] or {}).get("signals", []))]
    latencies = [t["latency_ms"] for t in guide if t["latency_ms"]]

    signal_counts, interaction_counts = {}, {}
    for t in guide:
        sig = t["signals"] or {}
        for s in sig.get("signals", []):
            signal_counts[s["name"]] = signal_counts.get(s["name"], 0) + 1
        it = sig.get("interaction_type")
        if it:
            interaction_counts[it] = interaction_counts.get(it, 0) + 1

    rows, gains, minutes = [], [], []
    story_started = story_done = story_skipped = 0
    by_mode, by_language, by_level = {}, {}, {}
    concept_agg = {}
    for l in learners:
        st = l["state"]
        s = state.summary(st, cfg)
        report = [r for r in state.outcome_report(st, cfg) if r["exposures"] > 0]
        if report:
            gains.append(sum(r["gain"] for r in report) / len(report))
        minutes.append(max(0.0, ((st.get("updated_at") or 0) - (st.get("started_at") or 0)) / 60))
        story = st.get("story")
        if story:
            story_started += 1
            story_done += 1 if story.get("completed") else 0
            story_skipped += 1 if story.get("skipped") else 0
        by_mode[st.get("mode", "challenge")] = by_mode.get(st.get("mode", "challenge"), 0) + 1
        lang = st.get("language", "en")
        by_language[lang] = by_language.get(lang, 0) + 1
        level = (st.get("prefs") or {}).get("learner_level", cfg["learner_level"])
        by_level[level] = by_level.get(level, 0) + 1
        for cid, c in st.get("concepts", {}).items():
            if c["exposures"] <= 0:
                continue
            a = concept_agg.setdefault(cid, {"concept_id": cid, "title": c["title"],
                                             "learners": 0, "mastery": 0.0, "hints": 0,
                                             "errors": 0})
            a["learners"] += 1
            a["mastery"] += c["mastery"]
            a["hints"] += c["hints_used"]
            a["errors"] += c["errors"]
        rows.append({
            "learner_id": l["id"], "label": l["label"],
            "turns": s["turns"], "xp": s["xp"], "streak": s["streak"],
            "overall_mastery": s["overall_mastery"], "coverage": s["coverage"],
            "mastered": s["mastered"], "total": s["total"],
            "badges": len(s["badges"]), "mode": st.get("mode", ""),
            "language": st.get("language", ""), "updated_at": l["updated_at"],
        })

    concept_stats = sorted((
        {"concept_id": a["concept_id"], "title": a["title"], "learners": a["learners"],
         "avg_mastery": round(a["mastery"] / a["learners"], 3),
         "avg_hints": round(a["hints"] / a["learners"], 2),
         "avg_errors": round(a["errors"] / a["learners"], 2)}
        for a in concept_agg.values()), key=lambda r: r["concept_id"])

    # learning curve: how much mastery the average learner gained on their nth reply
    by_turn = {}
    per_learner = {}
    for t in sorted(guide, key=lambda t: t["created_at"] or 0):
        n = per_learner[t["learner_id"]] = per_learner.get(t["learner_id"], 0) + 1
        gain = sum(m.get("delta", 0) for m in (t["signals"] or {}).get("mastery_updates", []))
        by_turn.setdefault(n, []).append(gain)
    gain_by_turn = [[n, round(sum(v) / len(v), 3)] for n, v in sorted(by_turn.items())][:15]

    cache_read = sum((t["signals"] or {}).get("cache_read", 0) for t in guide)
    cache_write = sum((t["signals"] or {}).get("cache_write", 0) for t in guide)
    fresh_in = sum(t["tokens_in"] or 0 for t in guide)
    prompt_total = cache_read + cache_write + fresh_in
    ids = [l["id"] for l in learners]
    fb = db.feedback_summary(ids[0] if len(ids) == 1 and learner else None)

    evidence = []
    for l in learners:
        for e in l["state"].get("signal_log", [])[-40:]:
            if signal and e.get("signal") != signal:
                continue
            if concept and e.get("concept_id") != concept:
                continue
            if cutoff and (e.get("at", 0) < cutoff):
                continue
            evidence.append({**e, "learner": l["label"], "learner_id": l["id"]})
    evidence.sort(key=lambda e: e.get("at", 0), reverse=True)

    sources = db.list_sources()
    all_concepts = {}
    for src in sources:
        full = db.get_source(src["id"])
        for c in json.loads(full["concept_map"]).get("concepts", []):
            all_concepts[c["id"]] = c
    grounding_totals = {"quotes_total": 0, "verbatim": 0, "repaired": 0, "dropped": 0}
    for src in sources:
        g = (json.loads(db.get_source(src["id"])["concept_map"]).get("grounding") or {})
        for k in grounding_totals:
            grounding_totals[k] += g.get(k, 0)

    return {
        "totals": {
            "learners": len(learners),
            "sessions": len(learners),
            "turns": len(guide),
            "tokens_in": sum(t["tokens_in"] or 0 for t in guide),
            "tokens_out": sum(t["tokens_out"] or 0 for t in guide),
            "sources": len(sources),
        },
        "latency": {
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
            "avg": int(sum(latencies) / len(latencies)) if latencies else 0,
            "samples": len(latencies),
        },
        "outcomes": {
            "avg_gain": round(sum(gains) / len(gains), 3) if gains else None,
            "avg_mastery": round(sum(r["overall_mastery"] for r in rows) / len(rows), 3)
                           if rows else None,
            "concepts_mastered": sum(r["mastered"] for r in rows),
            "avg_turns": round(sum(r["turns"] for r in rows) / len(rows), 1) if rows else None,
            "avg_minutes": round(sum(minutes) / len(minutes), 1) if minutes else None,
            "story": {"started": story_started, "completed": story_done,
                      "skipped": story_skipped},
            "feedback": fb,
            "cache_hit_rate": round(cache_read / prompt_total, 3) if prompt_total else None,
            "grounding": grounding_totals,
        },
        "usage": {"by_mode": by_mode, "by_language": by_language, "by_level": by_level},
        "gain_by_turn": gain_by_turn,
        "concept_stats": concept_stats,
        "signal_counts": signal_counts,
        "interaction_counts": interaction_counts,
        "learners": rows,
        "evidence": evidence[:40],
        "config": cfg,
        "filters": {
            "applied": {"learner": learner, "concept": concept,
                        "signal": signal, "since": since},
            "learners": [{"id": l["id"], "label": l["label"]} for l in db.list_learners()],
            "concepts": sorted(all_concepts.items()),
            "signals": llm.SIGNAL_NAMES,
            "windows": [["", "All time"], ["1h", "Last hour"],
                        ["24h", "Last 24 hours"], ["7d", "Last 7 days"]],
        },
    }


@app.get("/api/report/{learner_id}")
def learner_report(request: Request, learner_id: str, _=Depends(security.require_admin)):
    lid = security.safe_id(learner_id)
    learner = db.get_learner(lid)
    if not learner:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such learner.")
    cfg = config.current()
    return {
        "learner": learner["label"],
        "rows": state.outcome_report(learner["state"], cfg),
        "summary": state.summary(learner["state"], cfg),
    }


@app.get("/api/report.csv")
def report_csv(request: Request, _=Depends(security.require_admin),
               learner: str = "", concept: str = "", since: str = ""):
    """Export follows the dashboard's filters, so what you see is what you get."""
    cfg = config.current()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["learner_id", "learner", "concept_id", "concept", "baseline_mastery",
                "current_mastery", "gain", "exposures", "errors", "self_corrections",
                "hints_used", "status"])
    learners, _guide, _cut = _scope(learner, concept, since)
    for l in learners:
        for r in state.outcome_report(l["state"], cfg):
            if concept and r["concept_id"] != concept:
                continue
            w.writerow([l["id"], l["label"], r["concept_id"], r["concept"], r["baseline"],
                        r["current"], r["gain"], r["exposures"], r["errors"],
                        r["self_corrections"], r["hints_used"], r["status"]])
    return StreamingResponse(
        iter(["﻿" + buf.getvalue()]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="rehnuma-outcomes.csv"'},
    )


@app.get("/api/evidence.csv")
def evidence_csv(request: Request, _=Depends(security.require_admin),
                 learner: str = "", concept: str = "", signal: str = "", since: str = ""):
    """Every inferred signal beside the learner's own words that triggered it."""
    learners, _g, cutoff = _scope(learner, concept, since)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["time_utc", "learner", "concept_id", "signal", "learner_words"])
    for l in learners:
        for e in l["state"].get("signal_log", []):
            if (signal and e.get("signal") != signal) or (concept and e.get("concept_id") != concept) \
                    or (cutoff and e.get("at", 0) < cutoff):
                continue
            w.writerow([time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(e.get("at", 0))),
                        l["label"], e.get("concept_id", ""), e.get("signal", ""),
                        e.get("evidence", "")])
    return StreamingResponse(
        iter(["﻿" + buf.getvalue()]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="rehnuma-evidence.csv"'},
    )


@app.get("/admin/report/{learner_id}", response_class=HTMLResponse)
def printable_report(request: Request, learner_id: str):
    """One page a person can hand over: outcome per concept, the evidence behind it, and
    how the numbers were arrived at. Print it or save it as a PDF from the browser."""
    if not security.is_admin(request):
        return RedirectResponse("/admin")
    lid = security.safe_id(learner_id)
    learner = db.get_learner(lid)
    if not learner:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such learner.")
    cfg = config.current()
    st = learner["state"]
    rows = state.outcome_report(st, cfg)
    summ = state.summary(st, cfg)
    src = db.get_source(learner["source_id"]) or {}
    e = html.escape
    pct = lambda v: f"{round(v * 100)}%"

    body_rows = "".join(
        f"<tr><td>{e(r['concept'])}</td><td class=n>{pct(r['baseline'])}</td>"
        f"<td class=n>{pct(r['current'])}</td>"
        f"<td class=n>{'+' if r['gain'] >= 0 else ''}{round(r['gain'] * 100)}%</td>"
        f"<td><span class=bar><i style='width:{round(r['current'] * 100)}%'></i></span></td>"
        f"<td class=n>{r['exposures']}</td><td class=n>{r['hints_used']}</td>"
        f"<td>{e(r['status'])}</td></tr>" for r in rows)
    evidence = "".join(
        f"<li><b>{e(x['signal'].replace('_', ' '))}</b> &mdash; &ldquo;{e(x.get('evidence', ''))}&rdquo;</li>"
        for x in st.get("signal_log", [])[-10:] if x.get("evidence"))
    badges = ", ".join(e(b.replace("_", " ")) for b in st.get("badges", [])) or "none yet"
    story = st.get("story") or {}
    story_line = ("completed" if story.get("completed") else "skipped" if story.get("skipped")
                  else f"{story.get('viewed', 0)} of {story.get('scenes', 0)} scenes"
                  ) if story else "not used"
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Outcome report - {e(learner['label'])}</title>
<style>
 body{{font:15px/1.55 system-ui,'Segoe UI',sans-serif;color:#111;max-width:880px;margin:28px auto;padding:0 18px}}
 h1{{font-size:26px;margin:0}} h2{{font-size:16px;margin:26px 0 8px;border-bottom:2px solid #111;padding-bottom:4px}}
 .sub{{color:#555;margin:2px 0 18px}} .tiles{{display:flex;gap:10px;flex-wrap:wrap}}
 .tile{{border:2px solid #111;padding:8px 14px;min-width:120px}} .tile b{{display:block;font-size:22px}}
 table{{border-collapse:collapse;width:100%}} th,td{{border-bottom:1px solid #ccc;padding:6px 8px;text-align:left;vertical-align:middle}}
 th{{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:#444}} td.n{{text-align:right;font-variant-numeric:tabular-nums}}
 .bar{{display:block;width:110px;height:10px;background:#e4e4e4;border-radius:5px;overflow:hidden}} .bar i{{display:block;height:100%;background:#00805c}}
 li{{margin:4px 0}} .note{{font-size:13px;color:#444;border-left:4px solid #E6006E;padding:4px 12px;margin-top:22px}}
 button{{font:inherit;padding:8px 16px;border:2px solid #111;background:#FFC402;cursor:pointer;font-weight:700}}
 @media print{{button{{display:none}} body{{margin:0}}}}
</style></head><body>
<button id="printBtn" type="button">Print / save as PDF</button>
<h1>Learning outcome report</h1>
<p class="sub">{e(learner['label'])} &middot; {e(src.get('title', 'Untitled source'))} &middot; {time.strftime('%d %B %Y', time.gmtime())}</p>
<div class="tiles">
 <div class="tile"><b>{pct(summ['overall_mastery'])}</b>mastery of concepts met</div>
 <div class="tile"><b>{summ['mastered']} / {summ['total']}</b>concepts mastered</div>
 <div class="tile"><b>{summ['turns']}</b>conversation turns</div>
 <div class="tile"><b>{summ['xp']}</b>XP earned</div>
</div>
<h2>Before and after, by concept</h2>
<table><thead><tr><th>Concept</th><th>Before</th><th>Now</th><th>Gain</th><th></th><th>Beats</th><th>Hints</th><th>Status</th></tr></thead>
<tbody>{body_rows}</tbody></table>
<h2>What the learner's own words showed</h2>
<ul>{evidence or '<li>No signals recorded yet.</li>'}</ul>
<h2>Engagement</h2>
<p>Story: {e(story_line)}. Learning mode: {e(st.get('mode', ''))}. Badges: {badges}. Best streak: {summ['best_streak']}.</p>
<p class="note">Mastery here is an estimate inferred from how the learner talked &mdash; applying an idea to a new
example, correcting themselves, using the material's own vocabulary, asking a question that ran ahead, needing hints,
recalling earlier ideas &mdash; not the score of a test. Every change is logged with the words that caused it, so the
figure can be audited rather than taken on trust.</p>
<script src="/static/print.js"></script></body></html>"""
    return HTMLResponse(page)


@app.get("/api/events")
def events(request: Request, _=Depends(security.require_admin)):
    return {"events": db.recent_events(80)}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
