# Rehnuma — رہنما

**An AI Learning Experience Engine.** Give it any content — a PDF, a Word file, a PowerPoint, a spreadsheet, a web
link, or pasted text — and it turns it into an **illustrated story you watch**, then an **adaptive, voice-enabled game
you play**, in English or Urdu. It never gives a test: what you understand is inferred from how you talk.

Built as a candidate assignment for United Bank Limited (Digital HR & AI Manager), framed as a community
financial-literacy initiative. *Prototype for assessment — not an official UBL service.*

- **Live:** https://rehnuma-4cjj.onrender.com
- **Management view:** https://rehnuma-4cjj.onrender.com/admin
- **Slides (5):** `Rehnuma_UBL_5_Slides.pptx` / `.pdf`
- **Demo walkthrough:** `DEMO_RUNSHEET.md`

---

## The journey

1. **Bring content.** Upload a file, paste a link, or paste text. Choose language, level and any limit
   ("five minutes, on my phone").
2. **A verified concept map.** The material is broken into concepts, each stored with the exact sentences it came from.
   Every quote is checked against the upload before anything is saved ("Grounded: 20 of 20 quotes checked").
3. **The story.** A Prezi-style illustrated road: the camera pulls back and flies to each stop while a truck drives there.
   Nine drawing layouts (comparison, steps, chart, pie, cycle, shield, checklist, timeline, hero), drawn in the browser from
   the document's own ideas and figures.
4. **The game.** Missions, puzzles, boss challenges, and choices with consequences. Replies stream in as they are written.
   Speak or type, Urdu or English (right-to-left, code-switching).
5. **Adaptation and progress.** Difficulty, support, pace and the next concept are set from measured evidence; concepts
   unlock as understanding grows; XP, streaks and badges. The learner can change language, level or a limit mid-session and the
   very next reply obeys.
6. **Management.** Analytics, an evidence feed, filters, CSV exports, a printable learner report, and 28 live settings.

## How it meets the brief

| Requirement | How it is covered | Technology |
|---|---|---|
| Any content → experience | Any document becomes a verified map, a story, then a game | PyMuPDF, Word/PowerPoint parsing, CSV→prose, SSRF-guarded fetch, Claude structured outputs |
| Adaptive personalisation | Difficulty, support, pace, next concept from measured hints/answers; live language/level/limit changes | Deterministic Python learner model, per-learner overrides in SQLite |
| Gamification & interaction | Story road, missions, puzzles, boss, choices, XP, streaks, badges, unlocks | Vanilla-JS SVG scene engine, state machine in code |
| Assessment without tests | Six behaviours judged per reply with the learner's own words as evidence; before/after mastery | Claude structured JSON (signals + deltas), clamped arithmetic in Python |
| Voice + accessibility | Urdu/English speech in and out, code-switching, RTL Nastaliq, talk mode, text fallback, reduced motion, ARIA | Web Speech API, Noto Nastaliq Urdu |
| Accuracy & grounding | Every quote verified against the upload; claims cite a real quote; off-source refused and flagged | `app/grounding.py`, prompt rules, citation chips |
| Highly configurable | 28 settings (level, language, tone, mechanics, thresholds, custom rules), live and validated | Config service on SQLite, admin control room |
| Dashboards & reports | Learner, engagement, mastery, usage, outcome views; filters; CSV exports; printable report | Chart.js (self-hosted), FastAPI analytics |
| Efficient & effective | First words ~3 s; story prepared while the map is read; ~70% prompt-cache hits; measurable mastery gain | SSE streaming, prompt caching, background threads, Opus/Sonnet right-sizing |
| Free cloud deployment | One stateless service on a free tier, redeployed from GitHub on every push | Render free tier, `render.yaml`, GitHub |
| Cybersecurity & privacy | Signed expiring admin sessions, rate limits, strict CSP, validated inputs, SSRF guard, upload never stored, erase + retention | HMAC cookies, slowapi, CSP headers, pydantic |
| Reliable & observable | JSON logs, `/health`, in-app event log, per-turn latency/tokens; offline engine if the AI service fails | Python logging, events table, automatic fallback |

## Architecture

One FastAPI service serves both the pages and the API — no build step, no second deployment, no CORS. SQLite holds the
verified map, learners, turns, settings and logs. Handlers that call the model run on worker threads so a slow call never
freezes the service or its health check.

```
app/
  main.py        routes, streaming replies, dashboard, exports, printable report
  llm.py         concept map, storyteller, tutor turn (blocking + streaming), prompts, offline fallback
  state.py       learner model: mastery, unlocks, adaptation, focus concept, reviews
  grounding.py   verifies every quote against the upload
  storycache.py  writes the story in the background while the learner reads the map
  ingest.py      PDF / Word / PowerPoint / HTML / text / CSV / URL -> text
  config.py      28 live settings, validated on the server
  security.py    signed sessions, rate-limit keys, CSP and security headers
  db.py          SQLite
  demo.py        the offline engine (automatic fallback)
static/          learner page, story engine, control room, the truck-art visual system
samples/         documents to try (safety policy, biology, HR leave policy, Urdu health text, sales table, banking guide)
```

**Grounding without a vector database.** One uploaded document fits in context. Concepts carry verbatim quotes, every claim
cites one, and the UI shows clickable citation chips, so the grounding is visible rather than merely asserted.

**Prompt-injection defence.** Uploaded content and chat messages are marked as data, never instructions, and stripped of our
own prompt delimiters. The story can only *name* a layout and an icon; the browser draws everything, so a hostile document
cannot inject markup.

## Run it locally

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in `ANTHROPIC_API_KEY` and `ADMIN_PASSWORD`, then:

```bash
uvicorn app.main:app --reload --port 8000
```

Learner: http://localhost:8000 · Control room: http://localhost:8000/admin
(Locally, if `ADMIN_PASSWORD` is unset the admin password is `rehnuma`. In production there is no default: an unset password
disables admin sign-in.)

## Deploy to Render (free tier)

1. Push to GitHub. 2. Render → New → Web Service → connect the repo (`render.yaml` supplies the rest).
3. Set `ANTHROPIC_API_KEY` and `ADMIN_PASSWORD` in the Environment tab — never in the repository.
4. A free instance sleeps after inactivity and takes ~35–45 s to wake; open the URL a few minutes before a demo.
   SQLite lives on the instance disk, which the free tier resets on redeploy.

## Security and privacy, in brief

Signed, expiring admin sessions · no default password in production · per-client rate limits that hold behind the proxy ·
daily spend cap · every setting validated server-side · strict content-security policy (no inline or third-party script) ·
public-web-only fetching with redirect checks · size/type/archive limits · uploads are not stored, only the verified map ·
no personal data (a first-name label and a random id) · retention purge · learner and admin erasure.

## Tested on

Eight kinds of content — biology, a safety policy (.docx), a Python tutorial (.pptx), history (.pdf), an Urdu health text, a
sales table (.csv), an HR leave policy (UTF-16 .txt) and a tiny paste — every one ingested with 100% verbatim quotes and
stayed in the world of its own subject. Live checks on the deployed service confirmed streaming, Urdu, the rate limit
behind the proxy, and the admin lock-down.

## Honest limitations

- Free-tier storage is ephemeral and the instance sleeps when idle; production needs Postgres and a paid instance.
- Speech recognition needs Chrome or Edge; Urdu voice output needs a device voice (Edge has natural Urdu voices). Text is always available.
- Mastery is an estimate from behavioural signals; every change is logged with the learner's own words so it can be audited.
- If the AI service is unavailable, a simpler templated offline engine takes over and says so.

## Deck

`python tools_build_deck.py` rebuilds `Rehnuma_UBL_5_Slides.pptx` from the screenshots in `docs/screens/`
(needs `pip install python-pptx pillow`).
