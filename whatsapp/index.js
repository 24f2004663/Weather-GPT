/**
 * WeatherGPT WhatsApp Adapter — Baileys Sidecar
 *
 * Bridges WhatsApp messages to the existing WeatherGPT /api/chat endpoint.
 * Runs as an independent Node.js process alongside the Python FastAPI backend.
 *
 * Architecture:
 *   WhatsApp User → Baileys → HTTP POST /api/chat → existing Gemini router → response → Baileys → WhatsApp User
 *
 * Safety controls:
 *   - Disabled by default (WHATSAPP_BOT_ENABLED=false)
 *   - Explicit sender allowlist (supports both standard phone JIDs and WhatsApp privacy LIDs)
 *   - Groups, broadcasts, status, own messages, non-text all ignored
 *   - Per-sender rate limiting (sliding window)
 *   - Message length rejection (not truncation)
 *   - Single controlled error reply on API failure (no retry)
 *   - Auth data stored locally, never committed to Git
 *   - No message content in logs by default
 */

'use strict';

const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
const qrcode = require('qrcode-terminal');
const pino = require('pino');
const path = require('path');
const fs = require('fs');
const http = require('http');
const https = require('https');

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

// Load .env from whatsapp/ directory
require('dotenv').config({ path: path.join(__dirname, '.env') });

const CONFIG = Object.freeze({
  enabled:          (process.env.WHATSAPP_BOT_ENABLED || 'false').toLowerCase() === 'true',
  allowedNumbers:   parseAllowedNumbers(process.env.WHATSAPP_ALLOWED_NUMBERS || ''),
  rateLimitPerMin:  parseInt(process.env.WHATSAPP_RATE_LIMIT_PER_MINUTE || '5', 10),
  maxMessageLen:    parseInt(process.env.WHATSAPP_MAX_MESSAGE_LENGTH || '1000', 10),
  apiUrl:           process.env.WEATHERGPT_API_URL || 'http://localhost:8000',
  authDir:          path.join(__dirname, 'auth'),
});

function parseAllowedNumbers(raw) {
  if (!raw || !raw.trim()) return new Set();
  return new Set(
    raw.split(',')
      .map(n => n.trim().replace(/\D/g, ''))  // Normalize to digits only
      .filter(n => n.length >= 7)
  );
}

/**
 * Normalize a WhatsApp JID to digits-only phone number for allowlist comparison.
 * Example: "919042099020@s.whatsapp.net" → "919042099020"
 */
function jidToPhone(jid) {
  if (!jid) return '';
  return jid.split('@')[0].replace(/\D/g, '');
}

/**
 * Resolves the actual sender phone number from JID, metadata, or auth LID mapping.
 * WhatsApp often delivers messages via privacy LIDs (@lid), e.g. "231331770445968@lid".
 */
async function resolveSenderPhone(socket, jid, msg) {
  if (!jid) return '';

  // 1. Direct phone JID: "919940148758@s.whatsapp.net" -> "919940148758"
  if (jid.endsWith('@s.whatsapp.net')) {
    return jid.split('@')[0].replace(/\D/g, '');
  }

  // 2. LID JID: e.g. "231331770445968@lid"
  if (jid.endsWith('@lid')) {
    const lidDigits = jid.split('@')[0].replace(/\D/g, '');

    // Check message metadata for alternate phone JID
    if (msg?.key?.remoteJidAlt && msg.key.remoteJidAlt.endsWith('@s.whatsapp.net')) {
      return msg.key.remoteJidAlt.split('@')[0].replace(/\D/g, '');
    }
    if (msg?.key?.participantPn && msg.key.participantPn.endsWith('@s.whatsapp.net')) {
      return msg.key.participantPn.split('@')[0].replace(/\D/g, '');
    }

    // Check Baileys signalRepository if available
    try {
      if (socket?.signalRepository?.lidToJid) {
        const mappedJid = await socket.signalRepository.lidToJid(jid);
        if (mappedJid && mappedJid.endsWith('@s.whatsapp.net')) {
          return mappedJid.split('@')[0].replace(/\D/g, '');
        }
      }
    } catch (_) {}

    // Check auth folder reverse mapping file: lid-mapping-<lidDigits>_reverse.json
    try {
      const reverseMapFile = path.join(CONFIG.authDir, `lid-mapping-${lidDigits}_reverse.json`);
      if (fs.existsSync(reverseMapFile)) {
        const rawContent = fs.readFileSync(reverseMapFile, 'utf8');
        const phone = JSON.parse(rawContent);
        if (phone && typeof phone === 'string') {
          return phone.replace(/\D/g, '');
        }
      }
    } catch (_) {}

    return lidDigits;
  }

  return jid.split('@')[0].replace(/\D/g, '');
}

/**
 * Format phone for session_id: "wa_<digits>"
 * Compatible with backend SessionStore which accepts any non-empty string.
 */
function phoneToSessionId(phone) {
  return `wa_${phone}`;
}

// ---------------------------------------------------------------------------
// Structured Logging (no private message content)
// ---------------------------------------------------------------------------

function log(event, data = {}) {
  const entry = {
    timestamp: new Date().toISOString(),
    service: 'weathergpt-whatsapp',
    whatsapp_event: event,
    ...data,
  };
  // Never log message content or auth credentials
  delete entry.content;
  delete entry.auth;
  delete entry.credentials;
  console.log(JSON.stringify(entry));
}

// ---------------------------------------------------------------------------
// Per-Sender Rate Limiter (sliding window)
// ---------------------------------------------------------------------------

/** @type {Map<string, number[]>} phone → array of timestamps */
const rateLimitWindows = new Map();

/**
 * Returns true if the sender is within rate limits.
 * Returns false if they have exceeded the configured limit.
 */
function checkRateLimit(phone) {
  const now = Date.now();
  const windowMs = 60_000; // 1 minute
  const maxRequests = CONFIG.rateLimitPerMin;

  let timestamps = rateLimitWindows.get(phone);
  if (!timestamps) {
    timestamps = [];
    rateLimitWindows.set(phone, timestamps);
  }

  // Prune expired entries
  const cutoff = now - windowMs;
  while (timestamps.length > 0 && timestamps[0] <= cutoff) {
    timestamps.shift();
  }

  if (timestamps.length >= maxRequests) {
    return false; // Rate limited
  }

  timestamps.push(now);
  return true;
}

// ---------------------------------------------------------------------------
// WeatherGPT /api/chat Bridge
// ---------------------------------------------------------------------------

/**
 * Sends a chat request to the existing WeatherGPT /api/chat endpoint.
 * Returns the assistant's response text, or throws on failure.
 *
 * @param {string} messageText - The user's weather query
 * @param {string} sessionId - Per-sender session token
 * @returns {Promise<string>} Assistant response text
 */
async function callWeatherGPTChat(messageText, sessionId) {
  const chatRequest = {
    messages: [
      {
        role: 'user',
        content: messageText,
      }
    ],
    session_id: sessionId,
  };

  const url = new URL('/api/chat', CONFIG.apiUrl);
  const payload = JSON.stringify(chatRequest);

  return new Promise((resolve, reject) => {
    const transport = url.protocol === 'https:' ? https : http;
    const req = transport.request(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload),
      },
      timeout: 60_000, // 60s — Gemini tool loops can take time
    }, (res) => {
      let body = '';
      res.on('data', chunk => { body += chunk; });
      res.on('end', () => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          try {
            const parsed = JSON.parse(body);
            const text = parsed?.response_message?.content;
            if (text) {
              resolve(text);
            } else {
              reject(new Error(`Unexpected response shape from /api/chat (status ${res.statusCode})`));
            }
          } catch (e) {
            reject(new Error(`Failed to parse /api/chat response: ${e.message}`));
          }
        } else {
          // Extract error type without leaking secrets
          let errorType = 'UnknownError';
          try {
            const errBody = JSON.parse(body);
            errorType = errBody.error_type || `HTTP_${res.statusCode}`;
          } catch (_) {
            errorType = `HTTP_${res.statusCode}`;
          }
          reject(new Error(`/api/chat returned ${res.statusCode}: ${errorType}`));
        }
      });
    });

    req.on('error', (err) => reject(new Error(`Network error calling /api/chat: ${err.message}`)));
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('/api/chat request timed out after 60s'));
    });
    req.write(payload);
    req.end();
  });
}

// ---------------------------------------------------------------------------
// Message Handler
// ---------------------------------------------------------------------------

/**
 * Processes an incoming WhatsApp message through all safety gates.
 *
 * @param {object} socket - Baileys WASocket
 * @param {object} msg - Baileys message object
 */
async function handleMessage(socket, msg) {
  // 1. Ignore own messages
  if (msg.key.fromMe) return;

  const jid = msg.key.remoteJid;
  if (!jid) return;

  // 2. Ignore groups, broadcasts, status
  if (jid.endsWith('@g.us') || jid === 'status@broadcast' || jid.includes('@broadcast')) {
    log('ignored', { reason: 'group_or_broadcast', jid_type: jid.split('@')[1] });
    return;
  }

  // 3. Extract text only (ignore media, stickers, etc.)
  const text = msg.message?.conversation
    || msg.message?.extendedTextMessage?.text
    || '';

  if (!text || !text.trim()) {
    log('ignored', { reason: 'non_text_message', jid_suffix: jid.slice(-15) });
    return;
  }

  // 4. Resolve sender phone number (handles both @s.whatsapp.net and privacy @lid)
  const phone = await resolveSenderPhone(socket, jid, msg);

  // 5. Allowlist check
  if (!CONFIG.allowedNumbers.has(phone)) {
    log('ignored', { reason: 'not_allowlisted', phone_suffix: phone.slice(-4) });
    return;
  }

  log('received', { phone_suffix: phone.slice(-4), message_length: text.length });

  // 6. Message length check — reject, do NOT truncate
  if (text.length > CONFIG.maxMessageLen) {
    log('ignored', { reason: 'message_too_long', length: text.length, limit: CONFIG.maxMessageLen });
    try {
      await socket.sendMessage(jid, {
        text: `⚠️ Your message is too long (${text.length} characters). Please keep it under ${CONFIG.maxMessageLen} characters and try again.`
      });
      log('send', { type: 'length_rejection', phone_suffix: phone.slice(-4) });
    } catch (sendErr) {
      log('error', { reason: 'send_length_rejection_failed', error: sendErr.message });
    }
    return;
  }

  // 7. Rate limit check
  if (!checkRateLimit(phone)) {
    log('ignored', { reason: 'rate_limited', phone_suffix: phone.slice(-4), limit: CONFIG.rateLimitPerMin });
    try {
      await socket.sendMessage(jid, {
        text: '⏳ You\'re sending messages too quickly. Please wait a minute before trying again.'
      });
    } catch (_) { /* best effort */ }
    return;
  }

  // 8. Call /api/chat
  const sessionId = phoneToSessionId(phone);
  log('chat_request', { phone_suffix: phone.slice(-4), session_id: sessionId });

  try {
    const response = await callWeatherGPTChat(text.trim(), sessionId);
    log('chat_response', { phone_suffix: phone.slice(-4), response_length: response.length });

    // 9. Send response back via WhatsApp
    await socket.sendMessage(jid, { text: response });
    log('send', { type: 'chat_response', phone_suffix: phone.slice(-4) });

  } catch (err) {
    // Single controlled error — no retry
    log('error', { reason: 'chat_api_failed', error: err.message, phone_suffix: phone.slice(-4) });
    try {
      await socket.sendMessage(jid, {
        text: '🌧️ WeatherGPT is temporarily unable to process your request. Please try again in a moment.'
      });
      log('send', { type: 'error_reply', phone_suffix: phone.slice(-4) });
    } catch (sendErr) {
      log('error', { reason: 'send_error_reply_failed', error: sendErr.message });
    }
  }
}

// ---------------------------------------------------------------------------
// Baileys Connection Manager
// ---------------------------------------------------------------------------

let reconnectAttempt = 0;
const MAX_RECONNECT_DELAY = 60_000; // 60 seconds

async function connectToWhatsApp() {
  log('startup', { config: {
    enabled: CONFIG.enabled,
    allowlist_count: CONFIG.allowedNumbers.size,
    rate_limit: CONFIG.rateLimitPerMin,
    max_message_len: CONFIG.maxMessageLen,
    api_url: CONFIG.apiUrl,
    auth_dir: CONFIG.authDir,
  }});

  // Ensure auth directory exists
  if (!fs.existsSync(CONFIG.authDir)) {
    fs.mkdirSync(CONFIG.authDir, { recursive: true });
  }

  const { state, saveCreds } = await useMultiFileAuthState(CONFIG.authDir);

  const socket = makeWASocket({
    auth: state,
    printQRInTerminal: false,
    logger: pino({ level: 'silent' }), // Suppress noisy Baileys internals
  });

  // Connection lifecycle
  socket.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      log('qr_generated', { action: 'scan_with_whatsapp' });
      console.log('\n========================================');
      console.log('  SCAN THIS QR CODE WITH WHATSAPP');
      console.log('  Settings > Linked Devices > Link a Device');
      console.log('========================================\n');
      qrcode.generate(qr, { small: true });
      console.log('');
    }

    if (connection === 'open') {
      reconnectAttempt = 0;
      log('connected', { user_id: socket.user?.id ? '***authenticated***' : 'unknown' });
    }

    if (connection === 'close') {
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

      log('disconnected', {
        status_code: statusCode,
        logged_out: statusCode === DisconnectReason.loggedOut,
        will_reconnect: shouldReconnect,
      });

      if (shouldReconnect) {
        // Exponential backoff: 3s, 6s, 12s, 24s, 48s, 60s (capped)
        const delay = Math.min(3000 * Math.pow(2, reconnectAttempt), MAX_RECONNECT_DELAY);
        reconnectAttempt++;
        log('reconnecting', { delay_ms: delay, attempt: reconnectAttempt });
        setTimeout(() => connectToWhatsApp(), delay);
      } else {
        log('logged_out', { action: 'manual_re_authentication_required' });
        process.exit(0);
      }
    }
  });

  // Persist credentials on update
  socket.ev.on('creds.update', saveCreds);

  // Message handler
  socket.ev.on('messages.upsert', async (m) => {
    if (m.type !== 'notify') return;

    for (const msg of m.messages) {
      try {
        await handleMessage(socket, msg);
      } catch (err) {
        log('error', { reason: 'unhandled_message_error', error: err.message });
      }
    }
  });
}

// ---------------------------------------------------------------------------
// Exports for testing (must be before entry point guard)
// ---------------------------------------------------------------------------
module.exports = {
  CONFIG,
  parseAllowedNumbers,
  jidToPhone,
  resolveSenderPhone,
  phoneToSessionId,
  checkRateLimit,
  callWeatherGPTChat,
  handleMessage,
  rateLimitWindows,
  log,
};

// ---------------------------------------------------------------------------
// Entry Point (only when run directly, NOT when imported by tests)
// ---------------------------------------------------------------------------
if (require.main === module) {
  if (!CONFIG.enabled) {
    log('disabled', { reason: 'WHATSAPP_BOT_ENABLED is false', action: 'exiting' });
    console.log('[WeatherGPT WhatsApp] Bot is DISABLED. Set WHATSAPP_BOT_ENABLED=true in whatsapp/.env to activate.');
    process.exit(0);
  }

  if (CONFIG.allowedNumbers.size === 0) {
    log('error', { reason: 'no_allowed_numbers', action: 'exiting' });
    console.error('[WeatherGPT WhatsApp] ERROR: WHATSAPP_ALLOWED_NUMBERS is empty. At least one number is required.');
    process.exit(1);
  }

  connectToWhatsApp().catch((err) => {
    log('error', { reason: 'startup_failed', error: err.message });
    process.exit(1);
  });

  // Graceful shutdown
  process.on('SIGINT', () => {
    log('shutdown', { reason: 'SIGINT' });
    process.exit(0);
  });

  process.on('SIGTERM', () => {
    log('shutdown', { reason: 'SIGTERM' });
    process.exit(0);
  });
}
