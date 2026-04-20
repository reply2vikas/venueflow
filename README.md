# VenueFlow 🏟️
> Crowd-aware, accessibility-first event navigator for large sporting venues.
> Powered by Google Cloud Run, Firestore, Pub/Sub, BigQuery, Vertex AI (Gemini 1.5 Flash), and Cloud Translation API.

[![CI/CD](https://github.com/YOUR_USERNAME/venueflow/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/YOUR_USERNAME/venueflow/actions)

## Live Demo
**🌐 [https://venueflow-xxxx-em.a.run.app](https://venueflow-xxxx-em.a.run.app)**
> Scan the QR code at any entrance gate to open instantly — no download needed.

---

## The Problem
50,000 people at a stadium. One family with a wheelchair. Three blocked ramps, two inaccessible staircases, no real-time guidance. VenueFlow solves this.

## Chosen Persona
**Priya**, attending an IPL match with her son Dev (powered wheelchair user). VenueFlow routes them around crowds, pre-schedules restroom stops, answers questions via AI, and alerts them before the exit rush.

---

## Architecture
```
Turnstile sensors → Pub/Sub → Cloud Run Worker → Firestore
                                                      ↓
Phone (PWA) ←── Cloud Run API (FastAPI) ←── BigQuery (history)
                      ↓                ↓
               Vertex AI Gemini   Maps Routes API
               (AI assistant)     (accessible paths)
```

## Google Services Used

| Service | Role |
|---|---|
| **Cloud Run** | Hosts FastAPI API + Pub/Sub worker; auto-scales 1–50 instances |
| **Firestore** | Real-time zone density; live push to all connected clients |
| **Pub/Sub** | Ingests sensor burst events; decouples sensors from processing |
| **BigQuery** | Historical wait-time patterns for prediction blending |
| **Vertex AI (Gemini 1.5 Flash)** | Natural language Q&A with live crowd context |
| **Cloud Translation API** | Kannada / Hindi / Tamil alert translations |
| **Google Maps Routes API** | Indoor step-free pathfinding for wheelchair users |
| **Cloud Build** | Docker image build and push on every CI run |
| **Secret Manager** | Secure API key storage (never in code) |

---

## Key Features
- ♿ **Wheelchair routing** — step-free by default; stairs hard-blocked
- 📊 **Live crowd density** — 5-level colour map, updates every 30s
- ⏱ **Predictive wait times** — 60% live data + 40% BigQuery history
- 🤖 **Gemini AI assistant** — ask "which gate is fastest?" in plain English
- 🔔 **Real-time nudges** — WebSocket push; polls /api/alerts as fallback
- 🌐 **Offline PWA** — service worker caches last zone data
- 🔐 **Security** — CSP headers, Firestore rules, rate limiting, input sanitisation
- 🌏 **Multi-language** — Kannada, Hindi, Tamil via Cloud Translation API
- ✅ **CI/CD** — GitHub Actions: lint → test (70% coverage) → deploy on push

---

## Run Locally
```bash
git clone https://github.com/YOUR_USERNAME/venueflow
cd venueflow
cp .env.example .env         # add your GCP project + Maps API key
pip install -r requirements.txt
uvicorn api.main:app --reload
# Open http://localhost:8080
# API docs: http://localhost:8080/docs
```

## Run Tests
```bash
pytest tests/ -v --cov=api --cov-report=term-missing
```

## Deploy to Cloud Run
```bash
export GCP_PROJECT=your-project-id
bash deploy.sh
# Done in ~4 minutes. Prints live URL.
```

## Simulate Crowd Data (Demo)
```bash
export GCP_PROJECT=your-project-id
python data/simulate_crowd.py
# Publishes realistic sensor events to Pub/Sub every 15 seconds
# Simulates pre-match, in-play, and post-match surge phases
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness probe (Cloud Run + CI) |
| GET | `/api/zones` | Live crowd density all zones |
| POST | `/api/route` | Crowd-aware accessible routing |
| GET | `/api/waittimes` | Predicted queue wait times |
| GET | `/api/alerts` | Active venue alerts |
| POST | `/api/chat` | Gemini AI natural language Q&A |
| WS | `/ws/live` | Real-time nudge/emergency push |
| GET | `/docs` | Swagger UI |

---

## Security
- HTTPS enforced by Cloud Run
- CSP, HSTS, X-Frame-Options on every response
- Rate limiting: 60 req/min (zones), 30 req/min (routes), 10 req/min (AI)
- Firestore rules: public read-only; no client writes
- Anonymous sessions only — zero PII collected
- Input sanitisation on AI endpoint (prompt injection prevention)
- Secrets in Google Secret Manager, never in code

## Assumptions
- Venue provides turnstile count data (simulated via `simulate_crowd.py`)
- Google Maps Indoor Maps enabled for production routing
- One venue per deployment (multi-venue: add `VENUE_ID` env var)

## Future Improvements
- Steward admin dashboard (lift outage reporting, manual alerts)
- ML model replacing BigQuery weighted average
- BLE beacon indoor positioning (removes manual gate entry)
- Seat upgrade suggestions based on empty sections near accessible areas
