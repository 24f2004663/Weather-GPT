# WeatherGPT: Hyper-Local Emergency Disaster Alert and AI Climate Intelligence Platform

Smart India Hackathon (SIH) Internal Hackathon - Round 4 Prototype Submission
IIT Madras BS Degree Programme

Live Prototype Deployment:
- Web Application: https://weather-gpt-team-layers.vercel.app
- Backend API Service: https://weather-gpt-0g4n.onrender.com

---

## Executive Summary

WeatherGPT is an enterprise-grade, hyper-local disaster awareness and AI climate intelligence system designed to bridge official government emergency feeds (SACHET/NDMA and GDACS), real-time meteorological observations (Open-Meteo), 30-year agro-climatological baselines (NASA POWER), and proactive multi-channel notification infrastructure (SMS, WhatsApp, Web Push, Voice/IVR).

The system addresses the critical gap between raw disaster data ingestion and actionable citizen alerts by combining multi-model generative AI analysis with deterministic geographic and severity targeting algorithms.

---

## Live System Architecture

The project is structured as an event-driven monorepo separating real-time data ingestion, AI orchestration, database persistence, and multi-channel delivery:

```
[ SACHET (NDMA India) RSS ]   [ GDACS (UN / EC) RSS ]   [ Open-Meteo / NASA POWER APIs ]
            │                            │                            │
            └────────────────────────────┼────────────────────────────┘
                                         ▼
                   [ Fast-API Emergency Disaster Pipeline ]
                                         │
        ┌────────────────────────────────┼────────────────────────────────┐
        ▼                                ▼                                ▼
[ Ingestion & Normalization ]   [ Geographic & Severity ]   [ Zero-Cost Gemini Router ]
 (CAP XML Parsing & Expiry)     (State/District Resolution) (3.5-Flash-Lite & Fallbacks)
        │                                │                                │
        └────────────────────────────────┼────────────────────────────────┘
                                         ▼
                    [ Supabase PostgreSQL & PostgREST ]
                     (Subscriptions & Seen Deduplication)
                                         │
                                         ▼
                 [ Multi-Channel Notification Orchestrator ]
                                         │
      ┌──────────────────┬───────────────┴───────────────┬──────────────────┐
      ▼                  ▼                               ▼                  ▼
[ TextBee SMS ]   [ Baileys WhatsApp ]           [ VAPID Web Push ]   [ Voice / IVR ]
 (Android Gateway) (Open-Source Sidecar)          (Browser Service Worker) (Bilingual Scripts)
```

---

## Core System Innovations and Engineering Highlights

### 1. Multi-Source Disaster Ingestion and Normalization Engine
- Ingests official Common Alerting Protocol (CAP) XML feeds from SACHET (National Disaster Management Authority, India) and international GDACS RSS feeds.
- Implements strict severity classification: Extreme, Severe, Moderate, Minor, and Unknown.
- Resolves geographic boundaries down to State and District levels, enforcing exact country matching to eliminate false-positive geographic assignments.
- Uses automated batch deduplication and expiration filtering to ignore stale or cancelled disaster bulletins.

### 2. Multi-Model Gemini AI Router with Zero-Cost Quota Management
- Features a multi-tiered LLM router that manages rate-limits and token quotas across Google Gemini models (Gemini 3.5 Flash-Lite, Gemini 3.1 Flash-Lite, Gemma 4 31B, Gemma 4 26B).
- Automatically tracks Requests Per Minute (RPM), Requests Per Day (RPD), and Tokens Per Minute (TPM).
- Implements 60-second quota suppression and silent fallbacks to ensure continuous availability during high-traffic emergency events.
- Executes server-side tool calling for geocoding, current weather, multi-day forecasts, 30-year historical climate tables, and active disaster alerts.

### 3. Hyper-Local Multi-Channel Emergency Dispatch Engine
- **SMS Channel (TextBee Gateway):** Integrates with an Android gateway device running the TextBee service to dispatch real emergency SMS messages to registered mobile numbers without external carrier fees.
- **WhatsApp Channel (Baileys Open-Source Sidecar):** Built on `@whiskeysockets/baileys` Node.js socket layer. Runs as an independent process with live Supabase authorization checks, processing incoming conversational queries and sending outbound alert dispatches.
- **Web Push Channel (Native VAPID Protocol):** Implements RFC 8291/8292 Web Push VAPID protocol using `pywebpush` on the backend and an active Service Worker (`public/sw.js`) on the frontend for browser-native push notifications.
- **Voice/IVR Channel:** Generates structured bilingual (English and Hindi) spoken alert scripts formatted with emergency instructions, affected areas, and official source attributions.

### 4. Deterministic Deduplication and One-Shot Delivery Guards
- Enforces strict alert deduplication via `public.seen_alerts` and 15-second idempotency debounce keys (`test:{user_id}:{channel}`) to eliminate duplicate notification sends.
- Prevents double-click request repetition on frontend user interfaces.
- Applies strict per-recipient rate limits (maximum 5 notifications per hour).

---

## Technology Stack

### Backend Services
- **Framework:** Python 3.10+ / FastAPI / Uvicorn ASGI Server
- **Database & Persistence:** Supabase PostgreSQL with PostgREST REST API
- **AI & Natural Language:** Google GenAI SDK (`gemini-3.5-flash-lite`), Groq Whisper STT (`whisper-large-v3`)
- **HTTP Client & Parsing:** `httpx` (Async HTTP execution), `xml.etree.ElementTree` (CAP XML parser)
- **Web Push Engine:** `pywebpush` VAPID protocol generator

### Frontend Application
- **Framework:** Next.js 14 (App Router), React 18, TypeScript
- **Styling & Components:** Tailwind CSS, Lucide Icons, Headless UI
- **Geospatial & Visualizations:** Leaflet OpenStreetMap, Recharts climate charts
- **Service Worker:** Native Web Push Service Worker (`frontend/public/sw.js`)

### WhatsApp Sidecar
- **Runtime:** Node.js 18+
- **Socket Engine:** `@whiskeysockets/baileys` (Multi-file session authentication)
- **Process Supervisor:** PowerShell background supervisor (`whatsapp/start_whatsapp_supervisor.ps1`)

---

## Comprehensive Test Suite and Verification

The platform maintains a complete automated test suite verifying system contracts, data schemas, API adapters, and notification routing.

### Test Execution Commands

Backend Unit & Integration Test Suite:
```bash
python -m unittest discover -s backend/tests -v
```

WhatsApp Baileys Adapter Test Suite:
```bash
node --test whatsapp/test/adapter.test.js
```

Frontend Static Linting & Type Validation:
```bash
npm run lint
```

Production Build Compilation Verification:
```bash
npm run build
```

### Verification Metrics
- **Backend Unit Tests:** 181 / 181 PASSED
- **WhatsApp Adapter Tests:** 36 / 36 PASSED
- **ESLint Code Inspection:** 0 Errors, 0 Warnings
- **Production Build:** Next.js static pages compiled successfully

---

## REST API Specification

| Method | Endpoint | Description | Request Parameters / Body |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/health` | System diagnostics and service readiness status | None |
| `GET` | `/api/weather/current` | Real-time weather observations for coordinates | `lat` (float), `lon` (float) |
| `GET` | `/api/weather/forecast` | Multi-day daily and hourly forecast | `lat` (float), `lon` (float), `days` (int) |
| `GET` | `/api/weather/by-city` | Unified city search and weather forecast | `city` (string), `days` (int) |
| `GET` | `/api/climate/historical` | 30-year NASA POWER agro-climatological data | `lat` (float), `lon` (float) |
| `GET` | `/api/alerts` | Active SACHET & GDACS disaster alerts | `lat`, `lon`, `state`, `district`, `active_only` |
| `POST` | `/api/chat` | Conversational weather AI query with tool calling | Body: `{ messages: [...], session_id: string }` |
| `POST` | `/api/audio/transcribe` | Audio speech-to-text via Groq Whisper | Form Data: `file` (audio blob), `language` |
| `GET` | `/api/notifications/preferences` | Retrieve subscriber notification settings | `user_id` (string) |
| `POST` | `/api/notifications/preferences` | Opt-in / update alert preferences and channels | Body: Subscription JSON |
| `POST` | `/api/notifications/test` | Trigger one-shot channel delivery test | Body: `{ channel: string, user_id: string }` |
| `GET` | `/api/notifications/subscriber/verify` | Live auth gate endpoint for Baileys sidecar | `phone` (string) |

---

## Local Setup and Installation

### 1. Repository Setup
```bash
git clone https://github.com/24f2004663/Weather-GPT.git
cd Weather-GPT
```

### 2. Environment Configuration
Copy environment templates and configure required keys:
```bash
cp backend/.env.example backend/.env
cp whatsapp/.env.example whatsapp/.env
```

### 3. Backend Installation and Execution
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn backend.main:app --port 8000 --reload
```

### 4. Frontend Installation and Execution
```bash
cd frontend
npm install
npm run dev
```

### 5. WhatsApp Sidecar Execution
```bash
cd whatsapp
npm install
node index.js
```

---

## License and Project Disclosures

WeatherGPT is developed for the Smart India Hackathon (SIH) Internal Hackathon, IIT Madras BS Degree Programme. All meteorological and emergency alert data are sourced from public official APIs (NDMA SACHET, GDACS, Open-Meteo, NASA POWER).
