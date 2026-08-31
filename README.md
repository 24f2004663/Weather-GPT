# WeatherGPT — AI Weather Intelligence & Disaster Awareness Platform

WeatherGPT is a web-first AI weather intelligence and disaster-awareness platform designed to bridge verified meteorological sources, official disaster alerts (SACHET/NDMA), and multi-channel communications (Web, WhatsApp, SMS, IVR, Web Push) powered by Google Gemini.

---

## 🏛️ Architecture Overview

The system is structured as a clean, decoupled monorepo:

```
├── backend/
│   ├── core/                  # Configuration validation (Pydantic), in-memory TTL caching, safe logging, errors
│   ├── schemas/               # Shared API & data contracts (Location, Weather, Climate, Alerts, Chat, Notifications)
│   ├── services/              # Service adapters & provider abstractions
│   │   ├── weather/           # Open-Meteo, NASA POWER, WMO code interpretation, decision insights
│   │   ├── alerts/            # SACHET/NDMA CAP parser, deduplication, expiration & geographic relevance
│   │   ├── ai/                # Gemini AI orchestration, tool schemas, session store, multilingual prompts
│   │   ├── notifications/     # Event bus, Notification Orchestrator, Exotel SMS/IVR, Meta WhatsApp, Web Push VAPID
│   │   └── audio/             # Groq Whisper (STT), Browser SpeechSynthesis (TTS fallback)
│   ├── db/                    # Supabase PostgreSQL client & migration support
│   ├── tests/                 # Automated unit, integration, and smoke test suite (79 tests)
│   └── main.py                # FastAPI entrypoint, middleware, weather, alerts, chat, voice & notifications endpoints
├── frontend/
│   ├── public/
│   │   └── sw.js              # Service Worker for browser emergency Web Push notifications
│   ├── src/
│   │   ├── app/               # Next.js 14 App Router, Layout, Root Page
│   │   ├── components/        # WeatherGPT UI Design System
│   │   │   ├── Header.tsx                     # Search autocomplete, GPS locator, Notification Modal trigger, Multilingual selector
│   │   │   ├── NotificationSettingsModal.tsx  # Multi-channel disaster alert subscription preferences
│   │   │   ├── CurrentWeatherCard.tsx         # Real-time observations & conditions hero card
│   │   │   ├── PersonalizedInsights.tsx       # Decision-oriented recommendations (umbrella, UV, comfort)
│   │   │   ├── DisasterAlertBanner.tsx        # Official SACHET/NDMA disaster & safety feed
│   │   │   ├── WeatherMap.tsx                 # Interactive geospatial weather & alert zone map
│   │   │   ├── HourlyForecastStrip.tsx        # 24-Hour horizontal timeline with rain probabilities
│   │   │   ├── DailyForecastGrid.tsx          # 7-Day synoptic forecast cards
│   │   │   ├── WeatherCharts.tsx              # Lightweight SVG temperature & rain trend visualizations
│   │   │   ├── ClimateSection.tsx             # NASA POWER 30-year agroclimatological baseline
│   │   │   ├── ChatPanel.tsx                  # Gemini conversational AI with Voice STT and TTS playback
│   │   │   └── SourceAttributionPanel.tsx     # Disclosures & provider attribution
│   │   ├── lib/               # Typed API client (Chat, Location search, Weather, Climate, Alerts, Voice, Notifications)
│   │   └── types/             # Shared TypeScript interface contracts
│   ├── package.json           # Next.js, React, Tailwind CSS dependencies
│   ├── tsconfig.json          # Strict TypeScript configuration
│   └── tailwind.config.js     # Responsive design & WeatherGPT dark aesthetic
├── Dev_Orchestra/             # Development tracking (ChatGPT.md, Spark.md)
├── Test_Orchestra/            # Testing tracking (ChatGPT.md, Tester.md, Spark.md)
├── .env.example               # Complete environment variable specification
├── .gitignore                 # Strict secrets and build artifact exclusions
└── README.md                  # Project documentation
```

---

## 📢 Multi-Channel Emergency Notifications (Phase 7 Final Hardened)

WeatherGPT features an event-driven emergency notification engine:
- **Decoupled Orchestration**: `SACHET Feed -> DisasterAlertTriggeredEvent -> NotificationOrchestrator -> [WhatsApp, SMS, Voice, Web Push]`.
- **Explicit User Opt-In**: Requires user consent via `/api/notifications/preferences` before dispatching proactive alerts.
- **Web Push End-to-End**: Browser Service Worker (`frontend/public/sw.js`) and VAPID key exchange (`/api/notifications/vapid-public-key`) with secure private key preservation on the server.
- **Strict Concurrency & Fault Isolation**: `asyncio.gather(..., return_exceptions=True)` ensures one failing provider cannot block others or crash alert ingestion.
- **Strict Idempotency**: Suppresses duplicate alerts within 24 hours per recipient and channel (`idempotency_key = {alert_id}:{recipient}:{channel}`).
- **Phone Number Validation & PII Masking**: Validates E.164 phone formats and masks PII in API responses and logs (`+91 9876 ****10`).
- **Rate Limiting**: Caps delivery to a maximum of 5 alerts per recipient per hour.
- **Severity & Geographic Filtering**: Dispatches alerts matching user-selected thresholds (`Severe`, `Extreme`) and locations (State/District).
- **Multilingual Emergency Bulletins**: Formats localized messages in English, Hindi (`हिंदी`), Tamil (`தமிழ்`), Telugu (`తెలుగు`), and Bengali (`বাংলা`) while preserving official source text.
- **Safe Dry-Run Default**: `NOTIFICATION_DRY_RUN=true` simulates dispatches without charging accounts or spamming devices during testing.

### ⚠️ Prototype Architecture Disclosures & Limitations
1. **In-Memory Preferences**: In the current Phase 7 prototype, subscriptions and idempotency keys are managed within a concurrency-safe in-memory store (`NotificationOrchestrator`). Subscriptions persist during the active process and reset on server restart.
2. **Device / Client Identity**: Client user identifiers (`user_identifier`) provide device-scoped isolation for prototype sessions and do not represent full OAuth2/JWT user authentication.
3. **Provider Acceptance vs. Final Delivery**: Provider API requests return `PROVIDER_REQUEST_ACCEPTED` when acknowledged by upstream carrier gateways; final device delivery status depends on carrier handoff and user network connectivity.

---

## 🎙️ Advanced Intelligence & Accessibility (Phase 6)

- **Personalized Weather Insights**: Decision-oriented recommendations for umbrella necessity, UV skin protection, thermal comfort index, and optimal outdoor activity windows.
- **Interactive Geospatial Map**: Leaflet OpenStreetMap coordinate view with real-time temperature badge and disaster hazard scope indicators.
- **Voice-Query Speech-to-Text (Groq Whisper)**: Backend `POST /api/audio/transcribe` utilizing `whisper-large-v3` with microphone capture and pre-send transcript review.
- **Client Speech Synthesis (TTS)**: In-browser SpeechSynthesis playback with language matching and stop/pause controls.

---

## 🚨 Disaster & Alert Intelligence (Phase 5)

WeatherGPT integrates official CAP emergency alerts from **SACHET / NDMA**:
- **Authoritative XML/CAP Parser**: Secure parser resolving event types, severity, urgency, certainty, and official instructions.
- **Controlled Severity Normalization**: Normalized into `Extreme`, `Severe`, `Moderate`, `Minor`, and `Unknown` while preserving source severity.
- **Deterministic Deduplication**: Prevents repeated alert items per ingestion batch.
- **Expiration & Status Control**: Automatically filters expired and cancelled warnings.
- **Geographic Precision Matching**: Matches alerts to user location by District, State, or National scope.

---

## 🤖 AI WeatherGPT Engine & Server Tools

The AI Engine (`backend/services/ai/gemini.py`) integrates Google Gemini with an explicit server-side tool allowlist:

| Tool Name | Purpose | Target Provider |
| :--- | :--- | :--- |
| `resolve_location` | Geocodes place queries to coordinates | Open-Meteo Geocoding |
| `get_current_weather` | Retrieves real-time observations | Open-Meteo |
| `get_weather_forecast` | Retrieves multi-day/hourly forecasts | Open-Meteo |
| `get_historical_climate` | 30-year climatology baseline averages | NASA POWER |
| `get_active_alerts` | Official active disaster alerts | SACHET/NDMA |

---

## 🛰️ REST API Surface

| Method | Endpoint | Description | Request / Parameters |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/notifications/preferences` | Retrieve user notification preferences | `user_id` (string) |
| `POST` | `/api/notifications/preferences` | Save / Opt-in emergency preferences | Body: `SubscriptionRequest` |
| `DELETE` | `/api/notifications/preferences` | Unsubscribe user from all alerts | `user_id` (string) |
| `GET` | `/api/notifications/providers/status` | Public status of notification channels | None |
| `GET` | `/api/notifications/vapid-public-key` | Public VAPID key for browser Web Push | None |
| `POST` | `/api/notifications/preview` | Preview formatted alert across channels & languages | Body: `NotificationPreviewRequest` |
| `POST` | `/api/audio/transcribe` | Transcribes audio via Groq Whisper (`whisper-large-v3`) | Form data: `file`, `language` |
| `GET` | `/api/alerts` | Active disaster alerts from SACHET/NDMA | `lat`, `lon`, `state`, `district`, `active_only` |
| `POST` | `/api/chat` | Conversational weather queries with Gemini & tool calling | Body: `ChatRequest` |
| `GET` | `/api/location/search` | Geocodes place names into normalized locations | `q` (string), `count` (int) |
| `GET` | `/api/weather/current` | Normalized current conditions | `lat` (float), `lon` (float) |
| `GET` | `/api/weather/forecast` | Normalized daily & hourly forecast | `lat` (float), `lon` (float), `days` (int) |
| `GET` | `/api/weather/by-city` | Unified location search + forecast in one step | `city` (string), `days` (int) |
| `GET` | `/api/climate/historical` | 30-year NASA POWER agroclimatology baseline | `lat` (float), `lon` (float) |
| `GET` | `/api/health` | System diagnostics & adapter readiness | None |
| `GET` | `/api/config` | Public configuration & masked service status | None |

---

## 🧪 Running Automated Tests

Execute the backend test suite:
```bash
python3 -m unittest discover -s backend/tests -v
```

All **79 automated tests** verify:
- Web Push browser lifecycle, service worker integration, and VAPID key exchange.
- Phone number normalization, regex validation, and masking.
- Multi-channel notification delivery (WhatsApp, SMS, Voice, Web Push).
- Notification orchestrator severity, geographic, and rate-limiting filters.
- Idempotency key duplicate suppression over 24 hours.
- Explicit subscription management (subscribe, get, unsubscribe).
- Cross-user subscription isolation.
- Groq Whisper STT adapter, audio transcription endpoint, and error boundaries.
- Browser SpeechSynthesis metadata and TTS provider fallback.
- SACHET/NDMA CAP feed parsing, XML validation, deduplication, and expiration.
- AI tool calling loop including `get_active_alerts`.
- In-memory cache operations, TTL expiration, and eviction.
- WMO weather code interpretation and safe fallbacks.
- Open-Meteo and NASA POWER data normalization and schema compliance.
- FastAPI endpoint contracts and HTTP status codes.

---

## 🗺️ Project Phases Roadmap

- [x] **Phase 1 — Foundation & Architecture** (Completed)
- [x] **Phase 2 — Core Weather Engine** (Completed)
- [x] **Phase 3 — AI WeatherGPT Engine** (Completed & Verified)
- [x] **Phase 4 — Main Web Application** (Completed & Verified)
- [x] **Phase 5 — Disaster & Alert Intelligence** (Completed & Verified)
- [x] **Phase 6 — Advanced Intelligence & Accessibility** (Completed & Verified)
- [x] **Phase 7 — Communication Channels & End-to-End Verification** (Completed & Verified)
- [ ] **Phase 8 — Full Integration, Testing & Demo Hardening**
