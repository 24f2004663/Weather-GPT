# WeatherGPT

## Hyperlocal Weather Intelligence & Last-Mile Emergency Alert Platform

> **Forecast → Decision → Action**

WeatherGPT is an AI-powered weather intelligence platform designed to turn weather forecasts, disaster warnings, and location-aware information into clear, contextual, and actionable information for people.

This project was developed as a prototype for Smart India Hackathon (SIH) 2026.

---

# LIVE PROTOTYPE

https://weather-gpt-team-layers.vercel.app/

**Open the link and try it directly. No installation required.**

Try:

- `Weather in my locality`
- `Will it rain today?`
- `Will it rain at 6 PM?`
- `Is it safe to travel today?`

The prototype uses live data and demonstrates the complete WeatherGPT intelligence flow.

---

# Why We Built WeatherGPT

Weather information is already available through many applications, APIs and government systems.

The problem is not the absence of weather data.

The problem is that information is often fragmented across different sources and does not directly answer what a person actually wants to know.

A user may need to determine:

- What is happening right now?
- Will it rain today?
- When is the rain likely?
- Is there an official warning?
- Does that warning affect my location?
- Should I reconsider travelling or going outdoors?
- How can this information reach me quickly?

Most existing solutions primarily focus on:

> **Displaying weather data.**

Our approach is different:

> **Turn weather data and authoritative warnings into contextual, understandable and actionable intelligence.**

That is why we built WeatherGPT.

---

# What Makes WeatherGPT Different?

WeatherGPT is not intended to be another weather dashboard or another generic AI chatbot.

Our core idea is:

```text
Weather Data
     +
Official Warnings
     +
Location / Context
     +
AI Reasoning
     ↓
Actionable Weather Intelligence
     ↓
Web / WhatsApp / SMS
```

## 1. From Weather Display to Weather Intelligence

A traditional weather interface might tell a user:

> Rain probability: 69%

WeatherGPT can help answer:

> **"Will it rain today?"**

and then provide the relevant probability, expected rainfall, timing and practical context.

The goal is to make the information understandable rather than simply displaying more numbers.

---

## 2. Question-Aware Responses

WeatherGPT does not blindly return the same large weather report for every question.

For example:

### `Weather in my locality`

The system can provide:

- Current conditions
- Forecast
- Rain probability
- Official alerts
- Safety/travel information

### `Will it rain today?`

The response focuses on:

- Rain probability
- Expected rainfall
- Likely timing
- Relevant travel information

### `Will it rain at 6 PM?`

The response focuses on:

- Conditions around 6 PM
- Hourly precipitation probability
- Expected rainfall
- Nearby relevant weather context

The system therefore adapts the response to the actual question being asked.

---

# Weather + Disaster Intelligence

WeatherGPT is not limited to forecast information.

It can also incorporate authoritative disaster-warning information such as:

**SACHET / NDMA alerts**

The AI does not independently create an emergency warning.

Instead:

> **Authoritative sources remain the basis for official alerts, while AI helps explain and contextualize that information for the user.**

---

# From Information to Last-Mile Communication

Weather information is only useful if it reaches the people who need it.

WeatherGPT therefore goes beyond the website and demonstrates multiple communication paths:

```text
                  WeatherGPT
                      |
          +-----------+-----------+
          |           |           |
          v           v           v
         Web       WhatsApp      SMS
                     |
                   Baileys
```

The prototype demonstrates:

- Web interaction
- WhatsApp communication
- SMS delivery
- Web Push notifications

This allows WeatherGPT to demonstrate not only weather intelligence, but also a potential last-mile alerting architecture.

---

# How We Built This

The system separates data retrieval, validation, reasoning and communication instead of allowing the AI model to generate weather information by itself.

```text
+-----------------------------+
| Weather / Official Sources  |
+--------------+--------------+
               |
               v
+-----------------------------+
| Data Retrieval & Validation |
+--------------+--------------+
               |
               v
+-----------------------------+
| Location & Context Layer    |
+--------------+--------------+
               |
               v
+-----------------------------+
| AI Intelligence Layer       |
|           Gemini            |
+--------------+--------------+
               |
               v
+-----------------------------+
| Action / Communication      |
+--------------+--------------+
               |
               v
      Web / WhatsApp / SMS
```

The AI acts primarily as an interpretation and communication layer, while weather and warning information comes from external data sources.

---

# Technology Stack Used in the Prototype

The following technologies are what we used to build and demonstrate the current prototype.

> **Important:** These technologies are not being presented as a fixed production-stack commitment.
>
> If selected for the solution-building phase, the architecture and technology choices can be reassessed based on scalability, institutional requirements, security, infrastructure, authorized integrations and deployment constraints.

| Layer | Prototype Technology |
|---|---|
| Frontend | Next.js |
| UI | React + TypeScript + Tailwind CSS |
| Backend | Python + FastAPI |
| AI | Google Gemini |
| Weather Data | Open-Meteo |
| Disaster Alerts | SACHET / NDMA |
| Database | Supabase / PostgreSQL |
| WhatsApp Prototype | Baileys |
| SMS Prototype | TextBee |
| Browser Notifications | Web Push |
| Frontend Deployment | Vercel |
| Backend Deployment | Render |
| Source Control | GitHub |

### 1. Multi-Source Disaster Ingestion and Normalization Engine
- Ingests official Common Alerting Protocol (CAP) XML feeds from SACHET (National Disaster Management Authority, India) and international GDACS RSS feeds.
- Implements strict severity classification: Extreme, Severe, Moderate, Minor, and Unknown.
- Resolves geographic boundaries down to State and District levels, enforcing exact country matching to eliminate false-positive geographic assignments.
- Uses automated batch deduplication and expiration filtering to ignore stale or cancelled disaster bulletins.
- Follows each RSS item through to its full CAP 1.2 document to recover severity, urgency, certainty, expiry, official public-safety instructions and a structured `areaDesc`; the RSS index alone carries none of these.
- Preserves the official regional-language `<cap:info>` block verbatim (`headline_local` / `description_local`), so emergency instructions are never machine-translated.

### 2. Selectable Numerical Weather Prediction Models
- Forecasts default to Open-Meteo's `best_match` multi-model blend, and can be pinned to a single named global NWP system via the `model` query parameter.
- Supported systems: GFS (NOAA NCEP), ICON (DWD), ECMWF IFS, GEM (Environment Canada), JMA GSM/MSM, and the UKMO Unified Model. `GET /api/weather/models` enumerates them with their issuing centres.
- Every response carries a `weather_model` field, so a forecast is always attributable to the system that produced it.
- Model identity is part of the forecast cache key, preventing one model's output from being served under another model's name.

### 3. Multi-Model Gemini AI Router with Zero-Cost Quota Management
- Features a multi-tiered LLM router that manages rate-limits and token quotas across Google Gemini models (Gemini 3.5 Flash-Lite, Gemini 3.1 Flash-Lite, Gemma 4 31B, Gemma 4 26B).
- Automatically tracks Requests Per Minute (RPM), Requests Per Day (RPD), and Tokens Per Minute (TPM).
- Implements 60-second quota suppression and silent fallbacks to ensure continuous availability during high-traffic emergency events.
- Executes server-side tool calling for geocoding, current weather, multi-day forecasts, 30-year historical climate tables, and active disaster alerts.

### 4. Hyper-Local Multi-Channel Emergency Dispatch Engine
- **SMS Channel (TextBee Gateway):** Integrates with an Android gateway device running the TextBee service to dispatch real emergency SMS messages to registered mobile numbers without external carrier fees.
- **WhatsApp Channel (Baileys Open-Source Sidecar):** Built on `@whiskeysockets/baileys` Node.js socket layer. Runs as an independent process with live Supabase authorization checks, processing incoming conversational queries and sending outbound alert dispatches.
- **Web Push Channel (Native VAPID Protocol):** Implements RFC 8291/8292 Web Push VAPID protocol using `pywebpush` on the backend and an active Service Worker (`public/sw.js`) on the frontend for browser-native push notifications.
- **Voice/IVR Channel:** Generates structured bilingual (English and Hindi) spoken alert scripts formatted with emergency instructions, affected areas, and official source attributions.

### 5. Deterministic Deduplication and One-Shot Delivery Guards
- Enforces strict alert deduplication via `public.seen_alerts` and 15-second idempotency debounce keys (`test:{user_id}:{channel}`) to eliminate duplicate notification sends.
- Prevents double-click request repetition on frontend user interfaces.
- Applies strict per-recipient rate limits (maximum 5 notifications per hour).
---

# Why These Tools Were Used for the Prototype

The objective of the prototype was to prove the concept quickly with a working end-to-end system.

- **Next.js** — fast, accessible web interface for evaluation.
- **FastAPI** — backend orchestration for weather data, AI requests, alerts and notifications.
- **Gemini** — natural-language intelligence layer for interpreting retrieved weather information.
- **Open-Meteo** — weather-data source for forecast and precipitation information.
- **SACHET / NDMA** — authoritative disaster-warning information.
- **Baileys** — WhatsApp communication workflow for prototyping.
- **TextBee** — SMS delivery pathway.
- **Supabase / PostgreSQL** — persistence and application data.

---

# Why We Chose a Website for the Prototype

We deliberately chose a web prototype because the primary goal at this stage was:

### Frontend Application
- **Framework:** Next.js 14 (App Router), React 18, TypeScript
- **Styling & Components:** Tailwind CSS, Lucide Icons (`clsx` and `tailwind-merge` are declared but not currently imported)
- **Progressive Web App:** Installable via `public/manifest.json` with maskable icons and a notification badge
- **Geospatial & Visualizations:** Embedded OpenStreetMap viewport, hand-rolled inline-SVG charts (no external charting dependency)
- **Service Worker:** Native Web Push Service Worker (`frontend/public/sw.js`)
> **Prove the complete system with minimum friction for the evaluator.**

A mobile application would require:

- Application installation
- APK distribution
- Device compatibility
- Permissions
- Additional setup

A website reduces this to:

```text
Open Link
    ↓
WeatherGPT
    ↓
Ask Question
    ↓
See Live Result
```

A selector can immediately open:

**https://weather-gpt-team-layers.vercel.app/**

and test the system without installing anything.

This makes the prototype easier to evaluate during SIH.

---

# Website Does Not Mean Website-Only

The website is the prototype interface.

The underlying backend is API-driven.

Therefore the same intelligence layer can support future clients:

```text
                         WeatherGPT
                         Backend/API
                              |
               +--------------+--------------+
               |              |              |
               v              v              v
            Website       Mobile App     Messaging
                                             |
                                      WhatsApp / SMS
```

If selected for the solution-building phase, the appropriate client platform can therefore be evaluated independently from the intelligence backend.

---

# How a Selector Can Verify the Prototype

The prototype is designed to be directly testable.

## Test 1 — General Weather Intelligence

Ask:

```text
Weather in my locality
```

Observe:

- Current conditions
- Forecast
- Rain information
- Official alerts
- Safety/travel context

---

## Test 2 — Rain Question

Ask:

```text
Will it rain today?
```

Observe the focused precipitation answer.

---

## Test 3 — Time-Specific Question

Ask:

```text
Will it rain at 6 PM?
```

### Verification Metrics
- **Backend Unit Tests:** 248 / 248 PASSED
- **WhatsApp Adapter Tests:** 35 / 36 PASSED on a clean checkout. The remaining case asserts a LID-to-phone reverse mapping read from `whatsapp/auth/`, which holds paired-session state and is deliberately gitignored; it passes only on a machine with a live paired WhatsApp session.
- **ESLint Code Inspection:** 0 Errors, 0 Warnings
- **Production Build:** Next.js static pages compiled successfully (127 kB First Load JS)
Observe the hourly-specific response.

---

## Test 4 — Disaster Information

| Method | Endpoint | Description | Request Parameters / Body |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/health` | System diagnostics and service readiness status | None |
| `GET` | `/api/weather/current` | Real-time weather observations for coordinates | `lat` (float), `lon` (float) |
| `GET` | `/api/weather/forecast` | Multi-day daily and hourly forecast | `lat` (float), `lon` (float), `days` (int), `model` (string, optional) |
| `GET` | `/api/weather/by-city` | Unified city search and weather forecast | `city` (string), `days` (int), `model` (string, optional) |
| `GET` | `/api/weather/models` | Selectable Numerical Weather Prediction models and issuing centres | None |
| `GET` | `/api/climate/historical` | 30-year NASA POWER agro-climatological data | `lat` (float), `lon` (float) |
| `GET` | `/api/alerts` | Active SACHET & GDACS disaster alerts | `lat`, `lon`, `state`, `district`, `active_only` |
| `POST` | `/api/chat` | Conversational weather AI query with tool calling | Body: `{ messages: [...], session_id: string }` |
| `POST` | `/api/audio/transcribe` | Audio speech-to-text via Groq Whisper | Form Data: `file` (audio blob), `language` |
| `GET` | `/api/notifications/preferences` | Retrieve subscriber notification settings | `user_id` (string) |
| `POST` | `/api/notifications/preferences` | Opt-in / update alert preferences and channels | Body: Subscription JSON |
| `POST` | `/api/notifications/test` | Trigger one-shot channel delivery test | Body: `{ channel: string, user_id: string }` |
| `GET` | `/api/notifications/subscriber/verify` | Live auth gate endpoint for Baileys sidecar | `phone` (string) |
Ask about weather conditions during an active warning and observe how official warning information can be surfaced alongside weather intelligence.

---

## Test 5 — Communication Layer

The WhatsApp and SMS workflows can be demonstrated separately to show how the intelligence layer can extend beyond the browser.

---

# Safety & Data Philosophy

WeatherGPT follows a simple principle:

> **AI should interpret authoritative information, not fabricate authoritative information.**

The conceptual pipeline is:

```text
Authoritative Source
        ↓
Data Retrieval
        ↓
Validation
        ↓
Location Relevance
        ↓
Context / Severity
        ↓
Safety Processing
        ↓
AI Explanation
        ↓
User Communication
```

This separation is particularly important when dealing with disaster-related information.

---

# Prototype Architecture

```text
                         USER
                           |
                           v
                 +-----------------+
                 |  Next.js Web UI |
                 +--------+--------+
                          |
                          v
                 +-----------------+
                 | FastAPI Backend |
                 +--------+--------+
                          |
          +---------------+----------------+
          |               |                |
          v               v                v
   +------------+  +--------------+  +------------+
   | Open-Meteo |  | SACHET / NDMA|  | Supabase   |
   |  Weather   |  |    Alerts    |  | PostgreSQL |
   +------+-----+  +------+-------+  +------------+
          |               |
          +---------------+----------------+
                          |
                          v
                 +-----------------+
                 | Gemini AI Layer |
                 +--------+--------+
                          |
                          v
                 +-----------------+
                 | Action / Alerts |
                 +--------+--------+
                          |
              +-----------+-----------+
              |           |           |
              v           v           v
            Web        WhatsApp       SMS
                       Baileys       TextBee
```

---

# If Selected: Solution-Building Direction

The current stack should be viewed as a working proof-of-concept, not a final technology lock-in.

If selected, the next phase would focus on evaluating:

- Production-grade infrastructure
- Scalability
- Reliability
- Security
- Official institutional integrations
- Authorized government/IMD data access
- Production notification infrastructure
- Mobile deployment requirements
- Distributed processing
- Monitoring and observability
- Data governance

The prototype proves the concept and end-to-end workflow.

The solution-building phase can then optimize the implementation for real-world deployment requirements.

---

# What the Prototype Proves

The current prototype demonstrates that the following workflow is technically feasible:

```text
Real Weather Data
       +
Authoritative Alerts
       ↓
Contextual Processing
       ↓
AI Interpretation
       ↓
Natural-Language Intelligence
       ↓
Actionable Response
       ↓
Web / WhatsApp / SMS
```

> **WeatherGPT is not only a concept described in a presentation. It is a working prototype that demonstrates the complete intelligence and communication flow.**

---

# Our Core Vision

Traditional weather systems often follow:

```text
DATA → DISPLAY
```

WeatherGPT explores:

```text
DATA
  ↓
UNDERSTAND
  ↓
CONTEXTUALIZE
  ↓
DECIDE
  ↓
COMMUNICATE
```

Our vision is to make weather information more useful by bringing together:

**Forecast + Context + Official Warnings + AI + Last-Mile Communication**

into a single intelligence layer.

---

# Project Links

### Live Prototype

https://weather-gpt-team-layers.vercel.app/

### GitHub

https://github.com/24f2004663/Weather-GPT

---

# Team

## Team Seekers

**Smart India Hackathon 2026**

---

# WeatherGPT

### Forecast → Decision → Action

> **We don't want to build another place where people look at weather data.**
>
> **We want to build a system that helps people understand what that information means and what they can do with it.**
