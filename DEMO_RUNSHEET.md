# Rehnuma — demo walkthrough (about 8 minutes)

The order of the recorded demo, and what each step shows. All of it runs on the live deployment:
https://rehnuma-4cjj.onrender.com (management view at `/admin`).

## Before the demo

1. Open the live URL a few minutes early: a free instance that has been idle takes ~35–45 s to wake.
2. Open `/admin`, sign in, and check the health line at the bottom shows the model and no "AI SERVICE DOWN" warning.
3. In Configuration, press **Reset to defaults**.
4. Use Chrome or Edge (speech input needs one of them; Edge has natural Urdu voices).
5. A sample document that is *not* about banking is in `samples/` (`Warehouse-Safety-Policy.pdf`) to show it adapts to any content.

## The run

| Time | Show | What it demonstrates |
|---|---|---|
| 0:00 | Slide 1 | The problem (quizzes) and the experience (story, then game; English/Urdu; no test) |
| 0:40 | Slide 2 | Architecture: one service, verified quotes, background story, streamed tutor, learner model in code |
| 1:10 | Upload `Warehouse-Safety-Policy.pdf` | **Any content → experience.** The map appears with "Grounded: n of n quotes checked against your document" |
| 2:00 | The story | The Prezi-style road: camera pulls back and flies to each stop, truck drives; each poster shows its source quote |
| 3:20 | First mission | Continues the story; a good answer streams in with citations; the board, XP and streak move; the adaptation card |
| 4:00 | Type `idk` | **Real-time adaptation:** it changes how it teaches (support up, difficulty down, streak reset) with the reason shown |
| 5:00 | "Make it fit you" | **Live test:** switch to Urdu and add "five minutes, on my phone"; the next reply obeys; optional voice |
| 5:50 | `/admin` | **Management view:** filters, tiles (usage, engagement, outcomes, quality), charts, learning curve, evidence feed, struggle table |
| 6:30 | Report, Print, CSV | At least one useful report: printable learner report and outcome/evidence CSV exports |
| 7:00 | Configuration | **Change key settings live:** 28 settings, e.g. tone and an extra tutor rule; the next reply follows it; then Reset |
| 7:40 | Slides 3, 4, 5 | Security, efficiency/effectiveness/measurement, and the requirement-by-requirement table |

## If something breaks

| What happens | What to do |
|---|---|
| A banner says the AI service is not answering | That is the automatic offline fallback (billing, outage or rate limit): the journey continues, simpler and templated, still built only from the document |
| The map or story is slow | Free-tier CPU: about 20 s. The story is prepared while the map is read |
| Upload rejected | Use the **Paste text** tab |
| No Urdu voice on the device | The app says so and keeps the text; use Edge for natural Urdu voices |

## Numbers measured on the deployed app

| | |
|---|---|
| Wake from idle (free tier) | ~35–45 s |
| Concept map build | ~15–22 s |
| Story | ready by the time the map has been read (≤ ~12 s wait at worst) |
| First words of a reply (streamed) | ~3 s (2.7 s and 3.1 s measured); full reply 9–15 s |
| Prompt-cache hit rate | ~70% of input tokens |
| Quotes verbatim from source | 100% across eight kinds of content |
| Rate limit behind the proxy | 429 on the 6th bad sign-in even with a spoofed forwarding header |
