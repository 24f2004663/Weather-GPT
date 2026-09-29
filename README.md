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

Observe the hourly-specific response.

---

## Test 4 — Disaster Information

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
