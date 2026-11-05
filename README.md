# Clariflow

Clariflow turns short, noisy Marathi, Hindi and English spoken equipment-fault reports into evidence-linked work orders, asking one focused follow-up question and saving only after a person confirms the read-back.

**Live demo:** https://clariflow.onrender.com

This is a synthetic demonstration: a fictional plant and made-up data only. The demo runs on a free host, so the first visit after a quiet period or a new deploy can take a little while to load.

## How it works

1. **Speak** the problem in Marathi, Hindi, English or a mix.
2. **Check** the draft. Every field links to the exact words you said, and if something is unclear it asks one question, out loud and in text.
3. **Confirm** the read-back. Only then is the work order saved.

## Built with

Gnani Prisma (speech-to-text) and Timbre (text-to-speech), FastAPI, SQLite, and a React + Vite + TypeScript web app.

## Run it locally

You need Python 3.11 or newer, Node.js, and a Gnani API key.

```
pip install -r requirements.txt
cp .env.example .env          # then add your Gnani key to .env
cd frontend && npm install && npm run build && cd ..
uvicorn backend.app.main:create_app --factory --port 8000
```

Open http://localhost:8000. Run the tests with `pytest` (backend) and `npm test` inside `frontend` (web app).

## Status

Work in progress, built for The Great Indian AI Internship Challenge by Gnani AI. The Marathi and Hindi wording is a draft awaiting native-speaker review.
