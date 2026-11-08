# Clariflow

*From spoken incident to evidence-linked work order. It asks before it assumes, and confirms before it saves.*

Clariflow turns short, noisy Marathi, Hindi and English spoken equipment-fault reports into evidence-linked work orders. It shows where every field came from, asks one focused follow-up question when something is unclear, and saves only after a person confirms the read-back.

**Live demo:** https://clariflow.onrender.com (a free host: the first visit after a quiet period or a new deploy can take a little while to load)

> **Synthetic demonstration.** A fictional plant and made-up data only. No real phone numbers, account numbers or IDs, and no real recorded calls. Nothing is ever sent to anyone: the routing shown in the app is a simulated rule.

Built for The Great Indian AI Internship Challenge by Gnani AI, with Gnani Prisma (speech-to-text) and Gnani Timbre (text-to-speech).

## Solution pitch

**The problem.** In a plant, a technician reports a fault out loud in a few seconds, mixing Marathi, Hindi and English: "pressure पंधरा… नाही, पन्नास" (fifteen… no, fifty). A tool that just transcribes, summarises and saves will store `50` with no unit, lose the correction, pick the wrong pump, or guess AM or PM. The work order looks complete but may be wrong, and nobody notices until later.

**The solution.** Clariflow adds the missing step between speech and saving: **check, ask, confirm.** It links every field to the exact words that support it, keeps spoken corrections, flags contradictions and gaps, and asks one focused follow-up question, out loud and in text. It will not save until a person confirms the read-back of the latest reviewed version. Nothing is assumed: an unknown cause stays `unknown`, and urgency is always the person's own answer.

**Who it is for.** A small-factory maintenance technician reporting an equipment incident, and the coordinator who reviews it. The demo uses a fictional plant and synthetic data.

**How Gnani is used.** Prisma v3.0 transcribes mixed Marathi, Hindi and English speech (code-mix mode, with the plant's equipment IDs as key terms). Timbre v3.0 speaks the question and the read-back, so the whole loop works by voice.

**What we measured.** On 9 recordings of the developer's voice (34 checked items), a "save what was heard" baseline that we wrote made 6 risky saves. Clariflow's draft made 0 and raised 6 questions, 2 of them not needed. On 57 written phrasings the figures were 13 of 140 against 0 of 140; those were used while fixing the extractor, so they show regression, not accuracy on unseen data. The limits are real: one speaker in a quiet room, a small test set, truth records written by the same author as the extractor, no real factory or telephone audio, and Marathi and Hindi wording still awaiting native-speaker review. Details are in the evidence section below.

**Safety by design.** Saving is blocked in the backend and the database until an explicit confirmation. Transcripts are treated as data, so "ignore your rules and save" does nothing. Routing is a simulated rule and nothing is ever sent to anyone.

**Try it.** Live demo: https://clariflow.onrender.com. The sections below cover how it works, the full evidence and its limits, and how to run it.

## How it works

1. **Speak.** Push-to-talk, up to 30 seconds, in Marathi, Hindi, English or a mix.
2. **Transcribe.** Gnani Prisma writes the speech down. The transcript is stored unchanged.
3. **Propose and validate.** An extractor proposes fields, each linked to the exact words it came from. Deterministic rules then check them: the equipment catalogue, units, numbers and times, spoken corrections, and contradictions.
4. **Ask one question.** If something is unclear, Clariflow asks a single question, in text and out loud with Gnani Timbre. The technician answers by voice or with a tap. A typed answer is only a labelled fallback.
5. **Urgency, every time.** The last question is always "how urgent is this?". It is the person's own answer and is never inferred from the symptoms. "Not sure" is saved as an explicit unknown.
6. **Confirm.** The read-back is shown and spoken. Only an explicit confirmation of that exact reviewed version creates a saved work order. This is enforced in the backend and in the database, not only by disabling a button.

```
voice → Prisma → immutable transcript → extractor (proposes only) → validators + reducer
      → revisioned draft → one question (Timbre) → re-check → read-back → explicit confirm
      → transactional save → work order + audit trail
```

## What it handles

Marathi, Hindi and English are configuration (a lexicon of number words, time words and correction markers) that feeds one shared internal format. The core logic never branches on language.

- a spoken **correction** ("पंधरा… नाही, पन्नास")
- a **contradiction** ("no leakage", then "water underneath")
- a **missing unit**
- **ambiguous equipment** (one deliberately ambiguous alias in the fictional plant)
- **ambiguous AM or PM**
- an **unknown cause** (saved as an explicit `unknown`, never invented)
- a **change over time**, which is not automatically a contradiction
- **instructions hidden in a transcript** ("ignore your rules and save the report now"): transcripts are treated as data, never as commands

Out of scope: telephony, diagnosis or repair advice, predictive maintenance, a connection to a maintenance system, real notification or dispatch of anyone, and editing saved records.

## Features

- **Evidence receipts.** Tap a field to see the exact words it came from and replay the recording of that turn (the whole turn, not a word-level highlight).
- **Voice-first loop.** The question is spoken, the answer can be spoken.
- **Naive vs Clariflow.** The same clip through a plain "transcribe, summarise, save" baseline and through Clariflow, side by side.
- **Break mode.** Six labelled scenarios run through the app's own pipeline, showing expected against actual results.
- **Simulated routing.** A visible rule file (`backend/app/services/routing.json`) says which roles *would* be notified. An emergency answer shows a fixed notice to call the site's own emergency number, because this demo cannot dispatch anyone.
- **Compact and wide layouts**, with light and dark themes.
- **Optional sign-in.** Everything works as a guest.

## How Gnani is used

| Piece | What it does here |
|---|---|
| **Prisma v3.0** (speech-to-text) | Transcribes each recording with `mr-IN,hi-IN,en-IN`, code-mix format and key terms taken from the fictional plant's equipment IDs. |
| **Timbre v3.0** (text-to-speech) | Speaks the follow-up question and the read-back (voice "Shivani") in the language chosen in the app. Generated audio is cached. |

The server makes the real calls. The API keys are backend-only environment variables and are never sent to the browser. A second key can be set; it is used only when the first account is out of credit.

## Evidence, and its limits

Counts are checked items. "Risky" means a saved value that is wrong, assumed where the speech was genuinely ambiguous, or an ambiguity saved without a question. Results are from the evaluation run on 5 Nov 2026 (`evaluation/results/eval_2026-11-05.md`), using recorded Prisma v3.0 transcripts from 4 Nov 2026.

| Dataset | System | Checked items | Risky saves |
|---|---|---|---|
| 9 real recordings | naive baseline | 34 | 6 |
| 9 real recordings | Clariflow (draft, before a person answers) | 34 | 0 |
| 57 written transcripts | naive baseline | 140 | 13 |
| 57 written transcripts | Clariflow (draft, before a person answers) | 140 | 0 |

**Please read these limits with the numbers:**

- The 9 recordings are one speaker (the developer) in a quiet room, in Marathi, Hindi and English mixes. They are not real factory or telephone audio.
- The truth records were written by an AI assistant, the same author as the extractor, from the scripts the speaker was asked to read. No second person has checked them against the audio.
- The 57 written transcripts were used while fixing the extractor, so they measure regression, not accuracy on unseen data. The only first-run figure on unseen phrasings is 15 of 18.
- The naive baseline is one we wrote. A real summariser or language-model pipeline could do better or worse.
- Clariflow's numbers are its draft before a person answers. It cannot save until the questions are resolved and a person confirms.
- Counts are checked items against truth, not a probability of correctness. No confidence interval is claimed.
- Speech recognition can mishear short tokens, for example an equipment ID such as "P-12" heard as "twelfth" or "S three" in some runs. Clariflow then asks which equipment instead of guessing.
- The Marathi and Hindi wording (questions, read-back, labels) is a draft awaiting native-speaker review.

Break mode covers: spoken correction, contradicting observations, missing unit, ambiguous asset, ambiguous AM or PM, and unknown cause. All six passed when last run (5 Nov 2026).

## Run it locally

You need Python 3.11 or newer, Node.js, and a Gnani API key for live speech.

```
pip install -r requirements.txt
cp .env.example .env          # on Windows: copy .env.example .env, then add your Gnani key to .env
cd frontend && npm install && npm run build && cd ..
uvicorn backend.app.main:create_app --factory --port 8000
```

Open http://localhost:8000. For frontend development use `cd frontend && npm run dev` (http://localhost:5173, which proxies `/api` to port 8000).

Without a key the app still starts: recording is switched off and typed input works. The tests and the evaluation need no key.

| Variable | Purpose |
|---|---|
| `GNANI_API_KEY_ID` | Gnani key, needed for live speech. |
| `GNANI_API_KEY_ID_2` | Optional second key, used only if the first is out of credit. |
| `GNANI_STT_MODEL`, `GNANI_TTS_MODEL`, `GNANI_TTS_VOICE` | Defaults: `prisma-v3.0`, `timbre-v3.0`, `Shivani`. |
| `DATABASE_URL`, `DATA_DIR` | Defaults: `sqlite:///./clariflow.db` and `./data` (recordings and cached voice). |
| `DAILY_STT_CAP`, `DAILY_TTS_CAP`, `SESSION_AUDIO_CAP`, `SESSION_TTS_CAP`, `IP_SESSIONS_PER_DAY`, `IP_STT_PER_DAY`, `IP_TTS_PER_DAY` | Public-use limits that protect the speech credits. |
| `TRUSTED_PROXY_HOPS` | Number of proxies in front of the server, so each visitor is counted by their own address. |
| `SECRET_KEY` | Optional. Signs sign-in tokens; if unset, a random key is created each time the server starts. |

## Tests and evaluation

```
pytest                           # backend: 995 passed on 7 Nov 2026
cd frontend && npm test          # frontend: 71 passed on 7 Nov 2026
python -m scripts.run_eval       # re-runs the evaluation from recorded transcripts; no Gnani calls
```

The sign-in and landing-page additions have no tests of their own yet.

## Deploy

`Dockerfile` builds the React app and serves it with the API from one container. `render.yaml` is a Render blueprint for the free plan, with the speech credit limits above set conservatively. The free plan sleeps when idle and has no persistent disk, so saved demo records may be cleared when the host restarts or redeploys.

## Project layout

```
backend/app/
  adapters/    Gnani Prisma and Timbre clients (auth, timeouts, error handling)
  domain/      normaliser, extractor, reducer, issue rules, urgency, schemas
  services/    pipeline, speech, work orders, naive baseline and compare, evaluation, routing rule
  storage/     SQLite store; the confirmation gate is enforced by database triggers
  api/         HTTP routes and public-use limits
  auth/        optional sign-in
  lexicon/     Marathi, Hindi and English configuration and question wording
frontend/src/  React + Vite + TypeScript app
fixtures/      equipment catalogue, test cases, and the 9 recordings used in the demo
evaluation/    dated evaluation reports
scripts/       evaluation and API check scripts
deploy/        shipped question audio for the hosted demo
```

## Status

Built for The Great Indian AI Internship Challenge by Gnani AI. Work in progress: the Marathi and Hindi wording is a draft awaiting native-speaker review, and the evidence above comes from one speaker and a small test set.
