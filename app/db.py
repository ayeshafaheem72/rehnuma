"""SQLite storage. One file, no ORM - everything the app remembers lives here."""
import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager

DB_PATH = os.environ.get("REHNUMA_DB", os.path.join("data", "rehnuma.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    raw_text    TEXT NOT NULL DEFAULT '',  -- kept empty: only verified quotes are stored
    concept_map TEXT NOT NULL,          -- JSON: concepts + verbatim source quotes
    char_count  INTEGER NOT NULL DEFAULT 0,
    created_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS learners (
    id         TEXT PRIMARY KEY,
    label      TEXT NOT NULL,
    source_id  TEXT,
    state      TEXT NOT NULL,           -- JSON: the learner model (mastery, xp, streak...)
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS turns (
    id           TEXT PRIMARY KEY,
    learner_id   TEXT NOT NULL,
    role         TEXT NOT NULL,         -- 'learner' | 'guide'
    content      TEXT NOT NULL,
    signals      TEXT,                  -- JSON: the evidence behind each mastery change
    concept_id   TEXT,
    latency_ms   INTEGER,
    tokens_in    INTEGER,
    tokens_out   INTEGER,
    created_at   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turns_learner ON turns(learner_id, created_at);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL                 -- JSON-encoded
);

CREATE TABLE IF NOT EXISTS events (
    id         TEXT PRIMARY KEY,
    level      TEXT NOT NULL,           -- info | warn | error
    message    TEXT NOT NULL,
    meta       TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_time ON events(created_at DESC);

CREATE TABLE IF NOT EXISTS feedback (
    id         TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL,
    rating     INTEGER NOT NULL,        -- 1 = helpful, -1 = not helpful
    concept_id TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_learner ON feedback(learner_id);
"""


@contextmanager
def conn():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        # WAL lets the story prefetch thread write while requests read, without either
        # waiting on the other
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


# ---------- sources ----------

def save_source(title: str, concept_map: dict, char_count: int) -> str:
    """The upload itself is not kept. Everything the tutor may say comes from the verified
    quotes inside the concept map, so the full text has no reader - and a document a
    learner handed over should not outlive the need for it."""
    sid = new_id()
    with conn() as c:
        c.execute(
            "INSERT INTO sources (id,title,raw_text,concept_map,char_count,created_at)"
            " VALUES (?,?,?,?,?,?)",
            (sid, title, "", json.dumps(concept_map), int(char_count), time.time()),
        )
    return sid


def get_source(sid: str):
    with conn() as c:
        row = c.execute("SELECT * FROM sources WHERE id=?", (sid,)).fetchone()
    return dict(row) if row else None


def list_sources():
    with conn() as c:
        rows = c.execute(
            "SELECT id,title,char_count,created_at FROM sources ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


# ---------- learners ----------

def save_learner(learner_id: str, label: str, source_id: str, state: dict):
    now = time.time()
    with conn() as c:
        c.execute(
            "INSERT INTO learners (id,label,source_id,state,created_at,updated_at)"
            " VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET state=excluded.state,"
            " label=excluded.label, source_id=excluded.source_id, updated_at=excluded.updated_at",
            (learner_id, label, source_id, json.dumps(state), now, now),
        )


def get_learner(learner_id: str):
    with conn() as c:
        row = c.execute("SELECT * FROM learners WHERE id=?", (learner_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["state"] = json.loads(d["state"])
    return d


def list_learners():
    with conn() as c:
        rows = c.execute("SELECT * FROM learners ORDER BY updated_at DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["state"] = json.loads(d["state"])
        out.append(d)
    return out


# ---------- turns ----------

def save_turn(learner_id, role, content, signals=None, concept_id=None,
              latency_ms=None, tokens_in=None, tokens_out=None) -> str:
    tid = new_id()
    with conn() as c:
        c.execute(
            "INSERT INTO turns (id,learner_id,role,content,signals,concept_id,"
            "latency_ms,tokens_in,tokens_out,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (tid, learner_id, role, content,
             json.dumps(signals) if signals else None,
             concept_id, latency_ms, tokens_in, tokens_out, time.time()),
        )
    return tid


def get_turns(learner_id: str, limit: int = 200):
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM turns WHERE learner_id=? ORDER BY created_at ASC LIMIT ?",
            (learner_id, limit),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["signals"] = json.loads(d["signals"]) if d["signals"] else None
        out.append(d)
    return out


def all_turns(limit: int = 2000):
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM turns ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["signals"] = json.loads(d["signals"]) if d["signals"] else None
        out.append(d)
    return out


def count_guide_turns_since(ts: float) -> int:
    with conn() as c:
        row = c.execute(
            "SELECT COUNT(*) AS n FROM turns WHERE role='guide' AND created_at>=?", (ts,)
        ).fetchone()
    return int(row["n"])


# ---------- feedback & privacy ----------

def save_feedback(learner_id: str, rating: int, concept_id: str | None = None):
    with conn() as c:
        c.execute(
            "INSERT INTO feedback (id,learner_id,rating,concept_id,created_at) VALUES (?,?,?,?,?)",
            (new_id(), learner_id, 1 if rating > 0 else -1, concept_id, time.time()),
        )


def feedback_summary(learner_id: str | None = None) -> dict:
    q = "SELECT rating, COUNT(*) AS n FROM feedback"
    args: tuple = ()
    if learner_id:
        q += " WHERE learner_id=?"
        args = (learner_id,)
    with conn() as c:
        rows = c.execute(q + " GROUP BY rating", args).fetchall()
    up = sum(r["n"] for r in rows if r["rating"] > 0)
    down = sum(r["n"] for r in rows if r["rating"] < 0)
    return {"up": up, "down": down, "total": up + down,
            "helpful_rate": round(up / (up + down), 3) if up + down else None}


def delete_learner(learner_id: str) -> bool:
    """Erasure: the learner, everything they said, and their feedback."""
    with conn() as c:
        c.execute("DELETE FROM turns WHERE learner_id=?", (learner_id,))
        c.execute("DELETE FROM feedback WHERE learner_id=?", (learner_id,))
        cur = c.execute("DELETE FROM learners WHERE id=?", (learner_id,))
    return cur.rowcount > 0


def purge_older_than(days: int) -> dict:
    """Retention. Learner data past its window goes, along with any source no remaining
    learner is using and log lines that have outlived their usefulness."""
    cutoff = time.time() - days * 86400
    with conn() as c:
        old = [r["id"] for r in c.execute(
            "SELECT id FROM learners WHERE updated_at<?", (cutoff,)).fetchall()]
        for lid in old:
            c.execute("DELETE FROM turns WHERE learner_id=?", (lid,))
            c.execute("DELETE FROM feedback WHERE learner_id=?", (lid,))
        c.execute("DELETE FROM learners WHERE updated_at<?", (cutoff,))
        src = c.execute(
            "DELETE FROM sources WHERE created_at<? AND id NOT IN "
            "(SELECT source_id FROM learners WHERE source_id IS NOT NULL)", (cutoff,)).rowcount
        ev = c.execute("DELETE FROM events WHERE created_at<?", (cutoff,)).rowcount
    return {"learners": len(old), "sources": src, "events": ev}


# ---------- settings ----------

def get_setting(key: str, default=None):
    with conn() as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def set_setting(key: str, value):
    with conn() as c:
        c.execute(
            "INSERT INTO settings (key,value) VALUES (?,?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )


# ---------- events (observability) ----------

def log_event(level: str, message: str, meta: dict | None = None):
    with conn() as c:
        c.execute(
            "INSERT INTO events (id,level,message,meta,created_at) VALUES (?,?,?,?,?)",
            (new_id(), level, message, json.dumps(meta) if meta else None, time.time()),
        )


def recent_events(limit: int = 100):
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM events ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["meta"] = json.loads(d["meta"]) if d["meta"] else None
        out.append(d)
    return out
