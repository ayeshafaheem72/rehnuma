# Rehnuma — رہنما

**An AI Learning Experience Engine.** Give it any content — a PDF, a policy, an article —
and it turns that material into an adaptive, voice-enabled, gamified learning journey.
No quizzes. No tests. Understanding is inferred from how a person actually talks.

Built as a candidate assignment for United Bank Limited, framed as a community
financial-literacy initiative. *Prototype for assessment — not an official UBL service.*

---

## What it does

| Requirement | How Rehnuma meets it |
|---|---|
| **Any content → experience** | PDF/text ingestion, then one Claude call builds a concept map with verbatim source quotes |
| **Adaptive personalization** | A persistent learner-state object drives difficulty, depth, pace and examples on every turn |
| **Gamification** | Missions, explain-it, puzzles and boss challenges, plus XP, streaks, badges and concept unlocks |
| **Assessment without tests** | Six behavioural signals judged per turn — application, self-correction, source vocabulary, deepening questions, hint dependency, retention — each with the learner's own words as evidence |
| **Voice + accessibility** | Web Speech API for English and Urdu, RTL Nastaliq rendering, text fallback always visible |
| **Accuracy & grounding** | Every claim cites a verbatim source quote; off-source questions are flagged, never invented |
| **Highly configurable** | 17 settings editable live from the admin screen — no redeploy, no restart |
| **Dashboards & reports** | Mastery, engagement, latency, the evidence feed, per-learner outcome report, CSV export |
| **Efficient & effective** | Prompt caching on the concept map, tunable reasoning effort, before/after mastery as the outcome metric |
| **Free cloud deployment** | Single Render free-tier service |
| **Cybersecurity & privacy** | Rate limits, admin roles, CSP and security headers, input sanitisation, no PII, prompt-injection defence |
| **Reliable & observable** | Structured JSON logs, `/health`, in-app log viewer, per-turn latency and token accounting |

---

## Architecture

One service. FastAPI serves both the API and the pages — no build step, no second
deployment, no CORS.

```
app/
  main.py      FastAPI routes
  llm.py       Claude calls: concept map + the per-turn learning loop
  ingest.py    PDF / text → clean text
  state.py     mastery, XP, streaks, unlocks, badges
  config.py    admin-editable settings
  security.py  roles, rate limits, safe inputs, headers
  db.py        SQLite
static/        learner page, control room, the truck-art visual system
```

**Grounding without a vector database.** The panel uploads one document; it fits in
context. Concepts carry verbatim quotes, every claim cites one, and the UI renders
clickable citation chips. The grounding is visible rather than merely asserted.

**Prompt-injection defence.** Uploaded content is delimited and explicitly marked as
data, never instructions, in both prompts — a malicious PDF cannot hijack the tutor.

---

## Running it locally

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in:

```
ANTHROPIC_API_KEY=sk-ant-...
ADMIN_PASSWORD=choose-something
```

Then:

```bash
uvicorn app.main:app --reload --port 8000
```

- Learner experience — http://localhost:8000
- Control room — http://localhost:8000/admin

---

## Deploying to Render

1. Push this repository to GitHub.
2. In Render: **New → Web Service**, connect the repo. `render.yaml` supplies the rest.
3. Set `ANTHROPIC_API_KEY` and `ADMIN_PASSWORD` in Render's **Environment** tab —
   never in the repository.
4. Free instances sleep after inactivity and take ~50s to wake. Ping `/health` with
   an uptime monitor, and warm it before any live demo.

**Note on storage:** SQLite lives on the instance's disk, which Render's free tier
resets on redeploy. Fine for a demo session; a persistent disk or hosted Postgres
would be the production answer.

---

## Design

The interface is built on *phool patti* — Pakistani truck art — structured as an arcade
board: saturated colour blocks, hard black outlines, chevron strips, rosette medallions
and sticker shadows. A deliberate rejection of the default dark-gradient template, and a
visual argument that this was built for Pakistan rather than translated into it.

Chart colours are the same hues re-stepped for a dark plotting surface and validated for
colourblind separation, lightness band and contrast rather than chosen by eye.
