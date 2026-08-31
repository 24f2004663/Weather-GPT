# WeatherGPT Development Orchestration Plan

## Project Goal
Build the complete WeatherGPT prototype as a web-first AI weather intelligence and disaster-awareness platform. The web app is the primary experience; WhatsApp is a secondary conversational channel; SMS is an emergency/proactive alert channel; voice/IVR is an accessibility channel. The prototype must be demonstrable end-to-end and prioritize a reliable core over optional integrations.

## Development Strategy
- Gemini Spark/Antigravity performs implementation.
- Work phase-by-phase; do not give Spark the entire project as one uncontrolled task.
- After each phase, inspect the implementation and Spark's report before authorizing the next phase.
- Every phase must include validation/testing appropriate to the work completed.
- Prefer free/student-accessible services and the already verified integrations.
- Never hard-code secrets; use environment variables and keep `.env` out of version control.
- IMD access is optional/pending institutional permission and must not block the prototype.
- WhatsApp and TTS are integrations to be added when their access is ready; the core application must not depend on them to function.

## Verified / Selected Dependencies
- Gemini API — primary LLM.
- Supabase — PostgreSQL/backend services.
- Open-Meteo — current and forecast weather.
- NASA POWER — historical/climate data.
- SACHET/NDMA — official disaster alert feed.
- Groq Whisper — primary STT.
- Exotel — SMS and Voice/IVR candidate; credentials obtained, integration testing pending.
- Meta WhatsApp Cloud API — official secondary channel; verification/setup pending.
- TTS — free/no-billing solution to be finalized; browser SpeechSynthesis is the fallback.
- Web Push — browser-native push notifications via VAPID.
- IMD — official Indian meteorological source, optional until access is granted.

## Architecture Direction
Web-first architecture:
- Frontend: Next.js + React + TypeScript + Tailwind/shadcn-style component system.
- Backend: FastAPI + Pydantic.
- Database: Supabase PostgreSQL; use PostGIS/pgvector only where justified.
- AI: Gemini with controlled tool/function calling.
- Weather providers: Open-Meteo + NASA POWER; official alerts from SACHET/NDMA.
- AI must not invent or certify official disaster alerts. Official alerts remain traceable to their source; Gemini explains/interprets structured data.
- Communication providers are adapters behind a notification service so providers can be swapped without rewriting the alert engine.

## Phase 1 — Foundation & Architecture
### Objective
Create a clean, runnable monorepo/project foundation and establish the application contracts without prematurely implementing every feature.

## Phase 2 — Core Weather Engine
### Objective
Implement weather/location services and normalized weather data using Open-Meteo, geocoding, NASA POWER where appropriate, caching, validation, and provider abstraction. Keep external API failures graceful.

## Phase 3 — AI WeatherGPT Engine
### Objective
Integrate Gemini with controlled tool/function calling over the weather services, structured context, conversational state, safe response generation, source-aware answers, and clear separation between data retrieval and AI explanation.

## Phase 4 — Main Web Application
### Objective
Build the complete primary web experience: chat, weather dashboard, location, forecast views, charts, alerts view, climate information, responsive UX, language handling, and polished interaction flows.

## Phase 5 — Disaster & Alert Intelligence
### Objective
Integrate SACHET/NDMA ingestion, parsing, deduplication, validation, severity, geographic matching, alert storage, alert presentation, and a notification abstraction. Official alerts must remain authoritative and traceable.

## Phase 6 — Advanced Intelligence & Accessibility
### Objective
Add NASA POWER climate/historical analysis, map experience, personalized insights, multilingual capabilities, STT and voice-query flow where reliable. Use Groq Whisper as the primary STT and keep browser capabilities as practical fallbacks.

## Phase 7 — Communication Channels
### Objective
Integrate Meta WhatsApp Cloud API when verified, Exotel SMS, Exotel Voice/IVR, and Web Push. Implement provider adapters, webhook verification, retries, rate limits, auditability and safe failure behavior. Do not let communication integrations break the core web app.

## Phase 8 — Full Integration, Testing & Demo Hardening
### Objective
Run end-to-end testing across the complete prototype, fix integration issues, improve security/error handling/performance, verify fallbacks, prepare deployment, and harden the judge demonstration flow. Test the primary user journeys from weather query through official alert handling and multi-channel communication options.

## Current Phase
**Phase 8 — Full Integration, System Testing & Demo Hardening**

**Status: COMPLETED — REVIEW REQUIRED**

## Development Prompt History

##Prompt1: Phase 1 — Foundation & Architecture
##Prompt2: Phase 2 — Core Weather Engine
##Prompt3: Phase 3 — AI WeatherGPT Engine
##Prompt4: Phase 3 Improvement — Verification Pass
##Prompt5: Phase 4 — Main Web Application
##Prompt6: Phase 5 — Disaster & Alert Intelligence
##Prompt7: Phase 6 — Advanced Weather Intelligence & Accessibility
##Prompt8: Phase 7 — Multi-Channel Communication & Emergency Notifications
##Prompt9: Phase 7 Correction — Hardening Pass
##Prompt10: Phase 7 Final Correction — End-to-End Readiness
##Prompt11: Phase 8 — Full Integration, System Testing & Demo Hardening
