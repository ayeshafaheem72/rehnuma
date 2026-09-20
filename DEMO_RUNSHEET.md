# Rehnuma — demo run sheet

For the UBL panel. Read this once the night before and once in the car.

---

## Pre-flight — 30 minutes before you present

| # | Do this | Why |
|---|---|---|
| 1 | Open the live URL and let a page load fully | Render's free tier sleeps. First wake takes ~50s. **Never let the panel watch this.** |
| 2 | Run one throwaway session end to end | Warms the instance *and* confirms the API key and credits are alive today |
| 3 | Open `/admin`, sign in, leave the tab open | You will switch to it mid-demo; signing in live wastes 20 seconds |
| 4 | Check `/health` shows `api_key_present: true` | Catches a billing or key problem while you can still fix it |
| 5 | Set **demo_mode = off** in config | Live mode is the real product. Fallback is insurance only |
| 6 | Reset config to defaults | So language starts at English and nothing is left over from rehearsal |
| 7 | Have a **second browser tab** already on the learner page | If one tab misbehaves you switch, you don't reload |
| 8 | Phone hotspot ready | Venue wifi is the single most likely failure |

**Know where the kill switch is.** Admin → Configuration → **Demo fallback (no API)** → On → Save. If the API dies mid-demo, that one toggle keeps you running. Practise finding it blind.

---

## The run — 7 minutes

### 0:00–0:45 · Open with the thesis, not the tech

> "Every training tool ends with a quiz. A quiz tells you what someone remembered this morning — not whether they can use it. Rehnuma never tests anyone. It works out what you understand from how you talk."

**Slide 1.** Don't read it. Ten seconds, then go to the app.

### 0:45–1:45 · Give them the upload

Ask the panel for their content **now**, not later:

> "Rather than show you something I prepared, what would you like it to teach?"

Upload it. While the concept map builds, narrate:

> "It's reading the document and pulling out the ideas inside it — and against each one, the exact sentences it came from. Those quotes matter, I'll show you why in a moment."

Show the concept list. **Start learning.**

### 1:45–3:15 · Play one mission properly

Answer the first mission **well** — a full, thoughtful sentence. Then point at the board:

> "That concept just moved. Nobody scored me. It read how I answered."

Click a **citation chip**.

> "Every factual claim is tied to a line in *your* document. Click it, you see the source. The tutor cannot tell your staff something that isn't in the material."

### 3:15–4:15 · Now deliberately fail

Type **"idk"** and send it.

> "Watch what it does when I'm lost."

Point out: it drops the challenge, rephrases, the streak resets, mastery dips. Say the line:

> "It didn't mark me wrong. It changed how it was teaching."

**This is the moment that wins the room.** Don't rush it.

### 4:15–5:15 · The live test, on your terms

Switch to the admin tab. Change **Language → Urdu**, **Learner level → beginner**. Save. Back to the learner tab, answer again.

> "No redeploy, no restart. Seventeen settings work like this — tone, pace, difficulty, which game mechanics are on, the grounding rules."

If they ask for something else changed — change it in front of them. That's what the screen is for.

Optional, if the room is quiet enough: press the **microphone** and speak an answer.

### 5:15–6:30 · The control room

Go to `/admin`. Three things, in this order:

1. **The evidence feed** — *"This is the answer to 'how do you know they learned'. Every signal, beside the learner's own words that triggered it. Auditable, not asserted."*
2. **Mastery and latency** — read the real numbers off the screen. *"That's live, from this session."*
3. **Export CSV** — click it. *"Before-and-after mastery per concept, per learner."*

### 6:30–7:00 · Close on the bank's concern

**Slide 3.**

> "One thing I'd flag as the real risk. Uploaded content is an attack surface — a document can contain text written to hijack the model. Every upload here is marked as data, never instructions. And a tutor that invents a fact about a financial product is a liability, which is why nothing is said without a citation."

Stop there. Let them ask.

---

## If something breaks

| What happens | What you do |
|---|---|
| API error, slow, or billing fails | Admin → **Demo fallback: On** → Save. Carry on. Say *"I'll switch to the offline engine"* — it's a feature, not an excuse |
| Page won't load | Second tab. Then hotspot |
| Upload rejected | Use the **Paste text** tab — ask them to paste instead |
| Scanned PDF (no text) | It tells you plainly. Ask for a text-based file or paste |
| Voice doesn't catch Urdu | Type it. Say *"speech recognition for Urdu is uneven across browsers, so text is always available"* — honest and true |
| Something is genuinely wrong | Say so plainly and move on. Panels forgive a bug; they don't forgive bluffing |

---

## Questions they will probably ask

**"How do you stop it making things up?"**
Concepts carry verbatim quotes from the source. Every claim cites one. Ask it something outside the material and it says so and flags it rather than guessing. There's a strict-grounding switch for how hard that refusal is.

**"Why no vector database?"**
Because one uploaded document fits in context. Retrieval would add a day of work, another moving part and another failure mode, and would hide the grounding instead of showing it. At corpus scale — a whole policy library — retrieval is the right call, and it slots in behind the same interface.

**"How does it scale?"**
Stateless service, state in the database, so it scales horizontally. The honest limits today are the free tier: the instance sleeps, and SQLite resets on redeploy. Production answer is a persistent database and a paid instance.

**"Is mastery scoring accurate?"**
It's an estimate from behavioural signals, and I'd treat it as directional rather than exact. What makes it defensible is that every change is logged with the evidence, so you can audit *why* it moved — which you can't do with a quiz score.

**"What did this cost to run?"**
Read it off the dashboard. Fractions of a cent per turn.

---

## Two honest limitations — say these before they find them

Volunteering these makes you credible. Hiding them and being caught does the opposite.

1. **Free-tier storage is ephemeral.** Learner data resets when Render redeploys. Fine for a pilot, wrong for production — a persistent database is the fix, and it's a config change, not a rewrite.
2. **Urdu speech recognition is browser-dependent.** It's good in Chrome, uneven elsewhere. Text input is always visible for exactly that reason.
