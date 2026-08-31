# WeatherGPT — Production Deployment Guide

This guide documents the complete step-by-step instructions for deploying WeatherGPT to production with **Vercel** (Frontend) and **Render** (Backend FastAPI).

---

## 1. Architecture Overview

```
[ Browser / Mobile Client ]
            │
            ▼
    [ Vercel (Next.js) ]
            │  (REST / HTTPS)
            ▼
   [ Render (FastAPI) ] ────► [ Google Gemini 2.5 Flash ]
            │           ────► [ Groq Whisper STT ]
            │           ────► [ Twilio Voice & SMS ]
            │           ────► [ Web Push VAPID ]
            │           ────► [ Open-Meteo & SACHET ]
            ▲
            │ (Inbound Webhook)
    [ Twilio WhatsApp Sandbox ]
```

---

## 2. Backend Deployment — Render

### Service Configuration
- **Service Type**: Web Service
- **Environment / Runtime**: `Python 3`
- **Root Directory**: `.` (Root of repository)
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- **Health Check Path**: `/api/health`
- **Auto-Deploy**: Enabled on Git push to `main` branch

### Environment Variables for Render
Configure these in **Render Dashboard ➔ Environment**:

| Variable Name | Required | Description / Example |
|---|---|---|
| `PYTHON_VERSION` | Yes | `3.11.8` |
| `ENVIRONMENT` | Yes | `production` |
| `DEBUG` | Yes | `false` |
| `ALLOWED_ORIGINS` | Yes | `https://your-frontend.vercel.app,http://localhost:3000` |
| `GEMINI_API_KEY` | Yes | Secret API Key from Google AI Studio |
| `GEMINI_MODEL` | Optional | `gemini-2.5-flash` |
| `GROQ_API_KEY` | Yes | Secret API Key from Groq Cloud |
| `GROQ_WHISPER_MODEL` | Optional | `whisper-large-v3` |
| `TWILIO_ACCOUNT_SID` | Yes | Twilio Account SID (`AC...`) |
| `TWILIO_AUTH_TOKEN` | Yes | Twilio Auth Token |
| `TWILIO_SMS_FROM` | Yes | Twilio Long Code (e.g., `+17372508034`) |
| `TWILIO_VOICE_FROM` | Yes | Twilio Voice Caller ID (e.g., `+17372508034`) |
| `TWILIO_WHATSAPP_FROM` | Yes | WhatsApp Sender (`whatsapp:+14155238886`) |
| `TWILIO_WHATSAPP_TO` | Optional | Target recipient (`whatsapp:+919042099020`) |
| `SMS_PROVIDER` | Optional | `twilio` |
| `VOICE_PROVIDER` | Optional | `twilio` |
| `WHATSAPP_PROVIDER` | Optional | `twilio` |
| `VAPID_PUBLIC_KEY` | Yes | VAPID ECDSA Public Key |
| `VAPID_PRIVATE_KEY` | Yes | VAPID ECDSA Private Key |
| `VAPID_CLAIM_EMAIL` | Yes | `mailto:admin@weathergpt.local` |
| `NOTIFICATION_DRY_RUN` | Yes | `true` (Safe default) |

---

## 3. Frontend Deployment — Vercel

### Project Configuration
- **Framework Preset**: `Next.js`
- **Root Directory**: `frontend` (or select root with build override)
- **Build Command**: `npm run build`
- **Output Directory**: `.next`
- **Install Command**: `npm install`

### Environment Variables for Vercel
Configure in **Vercel Dashboard ➔ Settings ➔ Environment Variables**:

| Variable Name | Required | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | Yes | Full HTTPS URL of your deployed Render backend (e.g., `https://weathergpt-backend.onrender.com`) |

> [!IMPORTANT]
> Never put backend secrets (`GEMINI_API_KEY`, `TWILIO_AUTH_TOKEN`, `VAPID_PRIVATE_KEY`) in Vercel environment variables. Only public client variables prefixed with `NEXT_PUBLIC_` should be configured in Vercel.

---

## 4. Twilio WhatsApp Inbound Webhook Configuration

After the Render backend is deployed, configure Twilio to route incoming WhatsApp messages to WeatherGPT:

1. Log in to [Twilio Console](https://console.twilio.com/).
2. Navigate to **Messaging** ➔ **Try it out** ➔ **Send a WhatsApp message** ➔ **Sandbox Settings**.
3. Under **WHEN A MESSAGE COMES IN**, set:
   - **Method**: `HTTP POST`
   - **URL**: `https://<YOUR-RENDER-BACKEND-DOMAIN>/api/notifications/webhook/twilio-whatsapp`
4. Click **Save**.

### Inbound Flow
- User sends a question on WhatsApp (e.g., *"Will it rain today in Chennai?"*).
- Twilio forwards the webhook payload (`From`, `Body`) to WeatherGPT.
- WeatherGPT's Gemini AI engine computes the weather intelligence response.
- WeatherGPT returns standard TwiML `<Response><Message>...</Message></Response>`.
- The user receives the AI weather analysis directly in their WhatsApp chat.

---

## 5. Security & Repository Hygiene Rules

- **Zero Secrets in Git**: All `.env` and credential files are strictly excluded via `.gitignore`.
- **Environment Example Files**: Safe templates with placeholder values are available at [`.env.example`](file:///c:/Users/Kmano/Dropbox/Projects/CurrentProject/.env.example), [`backend/.env.example`](file:///c:/Users/Kmano/Dropbox/Projects/CurrentProject/backend/.env.example), and [`frontend/.env.example`](file:///c:/Users/Kmano/Dropbox/Projects/CurrentProject/frontend/.env.example).
- **CORS Protection**: Render backend dynamically accepts requests from localhost development and any `https://*.vercel.app` frontend domain.
