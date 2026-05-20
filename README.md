# CivicDigest 🏛️

**Local government intelligence. Plain English. On demand.**

[**→ Try the live demo**](https://civicdigest-production.up.railway.app)

---

Your city council meets every month and makes decisions that affect your rent, your roads, your taxes, and your schools. The minutes are public record. But they're written in bureaucratic language most people don't have time to decode.

CivicDigest reads them for you — and delivers a plain English summary plus a broadcast-style AI news report, automatically.

---

## What it does

Type any city. Get:

- **Audio broadcast** — a 45–60 second spoken summary, playable instantly in your browser
- **Plain English summary** — 2 paragraphs covering what was decided, what was proposed, and what affects residents
- **Broadcast video** — an AI-generated news report with anchor delivery, rendered automatically in the background and emailed to you when ready

No login. No paywall. No bureaucratic jargon.

---

## How it works

1. You type a city and topic ("Chicago budget vote")
2. CivicDigest searches for the most recent city council meeting records
3. A locally fine-tuned AI model reads the records and writes a plain English summary
4. The summary is rewritten as a broadcast script and delivered as audio via ElevenLabs
5. A HeyGen AI anchor records the broadcast video in the background
6. The composited broadcast — with news graphics, headline bar, and ticker — is delivered to your inbox

The whole pipeline from query to audio takes about 2 minutes. The broadcast video takes about 30 minutes to render and composite.

---

## The model

CivicDigest is built on a fine-tuned language model trained specifically to understand city council meeting minutes — trained locally on Apple Silicon with no cloud compute. The intelligence layer is purpose-built for this domain, not a general-purpose chatbot pointed at government documents.

Training data spans city council records from major US cities including Chicago, Seattle, Denver, Phoenix, Detroit, Oakland, New York City, and San Francisco.

---

## Covered cities

CivicDigest works best with cities that publish meeting minutes publicly online. Major US cities with active Legistar portals or well-indexed public records will produce the strongest results. Smaller cities may produce thinner summaries depending on what's publicly available.

---

## Limitations

- Summaries are AI-generated and may contain errors or omissions — always verify against official records
- Very recent meetings (last 24–48 hours) may not yet be indexed
- Smaller cities with limited online records may produce sparse results
- This is not a substitute for official meeting minutes or legal counsel

---

## Built with

- Fine-tuned language model trained on Apple Silicon
- [ElevenLabs](https://elevenlabs.io) — voice synthesis
- [HeyGen](https://heygen.com) — AI anchor video
- [Tavily](https://tavily.com) — real-time web search
- [Cloudflare R2](https://cloudflare.com/r2) — audio and video hosting
- [Railway](https://railway.app) — always-on deployment

---

## Run locally

**Requirements:** Python 3.11+, API keys for Anthropic, ElevenLabs, HeyGen, Tavily, SendGrid, Cloudflare R2

```bash
git clone https://github.com/Brandi-Kinard/civicdigest.git
cd civicdigest
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Set environment variables (see `.env.example`), then:

```bash
python server.py
```

Open `http://localhost:5050` in your browser.

---

## License

MIT

---

*Built by [Brandi Kinard](https://www.linkedin.com/in/brandikinard) — product designer and AI engineer*
