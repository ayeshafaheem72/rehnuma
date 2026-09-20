"""Rehnuma - an AI Learning Experience Engine.

One service: it serves the pages and the API. Everything the panel touches lives here.
"""
import csv
import io
import json
import logging
import os
import time

from dotenv import load_dotenv
from fastapi import (Depends, FastAPI, File, Form, HTTPException, Request,
                     Response, UploadFile, status)
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

load_dotenv()

from app import config, db, ingest, llm, security, state  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format='{"t":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
)
log = logging.getLogger("rehnuma")

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Rehnuma", docs_url=None, redoc_url=None)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.middleware("http")(security.add_security_headers)

STARTED_AT = time.time()


def turn_limit():
    return f"{config.current()['rate_limit_per_min']}/minute"


@app.on_event("startup")
def startup():
    db.init()
    db.log_event("info", "service started")
    log.info("rehnuma started")


# ------------------------------------------------------------ pages

@app.get("/")
def learner_page():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/admin")
def admin_page():
    return FileResponse(os.path.join(STATIC_DIR, "admin.html"))


@app.get("/health")
def health():
    cfg = config.current()
    return {
        "status": "ok",
        "uptime_s": round(time.time() - STARTED_AT, 1),
        "model": cfg["model"],
        "api_key_present": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "sources": len(db.list_sources()),
        "learners": len(db.list_learners()),
    }


# ------------------------------------------------------------ content in

def _build_source(text: str, title: str):
    cmap, usage, latency = llm.build_concept_map(text, title)
    payload = cmap.model_dump()
    sid = db.save_source(title, text, payload)
    db.log_event("info", "source ingested", {
        "source_id": sid, "title": title, "chars": len(text),
        "concepts": len(payload["concepts"]), "latency_ms": latency,
        "tokens_in": usage.input_tokens, "tokens_out": usage.output_tokens,
    })
    return {"source_id": sid, "concept_map": payload, "latency_ms": latency,
            "chars": len(text)}


@app.post("/api/source/upload")
@limiter.limit("10/minute")
async def upload_source(request: Request, file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > security.MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            "That file is larger than 8 MB. Please upload a smaller one.")
    try:
        text, truncated = ingest.from_upload(file.filename, data)
    except ingest.IngestError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    title = ingest.title_from(file.filename, text)
    try:
        out = _build_source(text, title)
    except Exception as e:
        db.log_event("error", "concept map failed", {"error": str(e)[:400]})
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            "The concept map could not be built. Please try again.")
    out["truncated"] = truncated
    out["title"] = title
    return out


class PasteIn(BaseModel):
    title: str = ""
    text: str


@app.post("/api/source/paste")
@limiter.limit("10/minute")
async def paste_source(request: Request, body: PasteIn):
    raw = security.clean_text(body.text, security.MAX_PASTE_CHARS)
    try:
        text, truncated = ingest.from_text(raw)
    except ingest.IngestError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    title = security.clean_text(body.title, 120) or ingest.title_from("", text)
    try:
        out = _build_source(text, title)
    except Exception as e:
        db.log_event("error", "concept map failed", {"error": str(e)[:400]})
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            "The concept map could not be built. Please try again.")
    out["truncated"] = truncated
    out["title"] = title
    return out


@app.get("/api/sources")
def sources():
    return {"sources": db.list_sources()}


# ------------------------------------------------------------ learning

class StartIn(BaseModel):
    source_id: str
    label: str = "Learner"


def _turn_payload(turn, learner, cfg):
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
        "state": learner,
        "summary": state.summary(learner, cfg),
        "newly_unlocked": learner.get("_newly_unlocked", []),
    }


@app.post("/api/session/start")
@limiter.limit("20/minute")
async def start_session(request: Request, body: StartIn):
    sid = security.safe_id(body.source_id)
    src = db.get_source(sid)
    if not src:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That source no longer exists.")
    cmap = json.loads(src["concept_map"])
    cfg = config.current()

    learner_id = db.new_id()
    st = state.new_state(cmap)
    db.save_learner(learner_id, security.clean_text(body.label, 60) or "Learner", sid, st)

    try:
        turn, usage, latency = llm.run_turn(cmap, st, [], "")
    except Exception as e:
        db.log_event("error", "opening turn failed", {"error": str(e)[:400]})
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            "Could not start the session. Please try again.")

    st = state.apply_turn(st, turn, cfg, cmap)
    db.save_learner(learner_id, body.label or "Learner", sid, st)
    db.save_turn(learner_id, "guide", turn.message, _signals_dict(turn), turn.concept_id,
                 latency, usage.input_tokens, usage.output_tokens)

    out = _turn_payload(turn, st, cfg)
    out["learner_id"] = learner_id
    out["concept_map"] = cmap
    out["latency_ms"] = latency
    return out


def _signals_dict(turn):
    return {
        "signals": [s.model_dump() for s in turn.signals if s.detected],
        "mastery_updates": [m.model_dump() for m in turn.mastery_updates],
        "interaction_type": turn.interaction_type,
        "off_source": turn.off_source,
        "hint_given": turn.hint_given,
    }


class TurnIn(BaseModel):
    message: str


@app.post("/api/session/{learner_id}/turn")
@limiter.limit(turn_limit)
async def take_turn(request: Request, learner_id: str, body: TurnIn):
    lid = security.safe_id(learner_id)
    learner = db.get_learner(lid)
    if not learner:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That session has expired.")
    message = security.clean_text(body.message, security.MAX_MESSAGE_CHARS)
    if not message:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Say something first.")

    src = db.get_source(learner["source_id"])
    if not src:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The source material is gone.")
    cmap = json.loads(src["concept_map"])
    cfg = config.current()
    history = [{"role": t["role"], "content": t["content"]} for t in db.get_turns(lid)]

    db.save_turn(lid, "learner", message)
    try:
        turn, usage, latency = llm.run_turn(cmap, learner["state"], history, message)
    except Exception as e:
        db.log_event("error", "turn failed", {"learner": lid, "error": str(e)[:400]})
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            "That response did not come through. Please try again.")

    st = state.apply_turn(learner["state"], turn, cfg, cmap)
    db.save_learner(lid, learner["label"], learner["source_id"], st)
    db.save_turn(lid, "guide", turn.message, _signals_dict(turn), turn.concept_id,
                 latency, usage.input_tokens, usage.output_tokens)

    out = _turn_payload(turn, st, cfg)
    out["latency_ms"] = latency
    return out


@app.get("/api/session/{learner_id}")
def get_session(learner_id: str):
    lid = security.safe_id(learner_id)
    learner = db.get_learner(lid)
    if not learner:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That session has expired.")
    src = db.get_source(learner["source_id"])
    cfg = config.current()
    return {
        "learner_id": lid,
        "label": learner["label"],
        "state": learner["state"],
        "summary": state.summary(learner["state"], cfg),
        "concept_map": json.loads(src["concept_map"]) if src else None,
        "history": db.get_turns(lid),
    }


# ------------------------------------------------------------ config

@app.get("/api/config")
def read_config(request: Request):
    return {
        "config": config.current(),
        "schema": [{"key": k, "kind": kind, "options": opts, "label": label}
                   for k, kind, opts, label in config.SCHEMA],
        "is_admin": security.is_admin(request),
    }


@app.post("/api/config")
def write_config(request: Request, patch: dict, _=Depends(security.require_admin)):
    return {"config": config.update(patch)}


@app.post("/api/config/reset")
def reset_config(request: Request, _=Depends(security.require_admin)):
    return {"config": config.reset()}


# ------------------------------------------------------------ admin auth

class LoginIn(BaseModel):
    password: str


@app.post("/api/admin/login")
@limiter.limit("5/minute")
async def admin_login(request: Request, body: LoginIn):
    if not security.check_password(body.password):
        db.log_event("warn", "failed admin sign-in", {"ip": get_remote_address(request)})
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


# ------------------------------------------------------------ dashboard

def _percentile(values, pct):
    if not values:
        return 0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((pct / 100) * (len(s) - 1)))))
    return s[k]


@app.get("/api/dashboard")
def dashboard(request: Request, _=Depends(security.require_admin)):
    cfg = config.current()
    learners = db.list_learners()
    turns = db.all_turns()
    guide_turns = [t for t in turns if t["role"] == "guide"]
    latencies = [t["latency_ms"] for t in guide_turns if t["latency_ms"]]

    signal_counts = {}
    for t in guide_turns:
        for s in (t["signals"] or {}).get("signals", []):
            signal_counts[s["name"]] = signal_counts.get(s["name"], 0) + 1

    interaction_counts = {}
    for t in guide_turns:
        it = (t["signals"] or {}).get("interaction_type")
        if it:
            interaction_counts[it] = interaction_counts.get(it, 0) + 1

    rows = []
    for l in learners:
        s = state.summary(l["state"], cfg)
        rows.append({
            "learner_id": l["id"], "label": l["label"],
            "turns": s["turns"], "xp": s["xp"], "streak": s["streak"],
            "overall_mastery": s["overall_mastery"],
            "mastered": s["mastered"], "total": s["total"],
            "badges": len(s["badges"]),
            "updated_at": l["updated_at"],
        })

    evidence = []
    for l in learners:
        for e in l["state"].get("signal_log", [])[-20:]:
            evidence.append({**e, "learner": l["label"], "learner_id": l["id"]})
    evidence.sort(key=lambda e: e.get("at", 0), reverse=True)

    return {
        "totals": {
            "learners": len(learners),
            "sessions": len(learners),
            "turns": len(guide_turns),
            "tokens_in": sum(t["tokens_in"] or 0 for t in guide_turns),
            "tokens_out": sum(t["tokens_out"] or 0 for t in guide_turns),
            "sources": len(db.list_sources()),
        },
        "latency": {
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
            "avg": int(sum(latencies) / len(latencies)) if latencies else 0,
            "samples": len(latencies),
        },
        "signal_counts": signal_counts,
        "interaction_counts": interaction_counts,
        "learners": rows,
        "evidence": evidence[:40],
        "config": cfg,
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
def report_csv(request: Request, _=Depends(security.require_admin)):
    cfg = config.current()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["learner_id", "learner", "concept_id", "concept", "baseline_mastery",
                "current_mastery", "gain", "exposures", "errors", "self_corrections",
                "hints_used", "status"])
    for l in db.list_learners():
        for r in state.outcome_report(l["state"], cfg):
            w.writerow([l["id"], l["label"], r["concept_id"], r["concept"], r["baseline"],
                        r["current"], r["gain"], r["exposures"], r["errors"],
                        r["self_corrections"], r["hints_used"], r["status"]])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="rehnuma-outcomes.csv"'},
    )


@app.get("/api/events")
def events(request: Request, _=Depends(security.require_admin)):
    return {"events": db.recent_events(80)}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
