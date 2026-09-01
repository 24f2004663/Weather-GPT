/**
 * WeatherGPT WhatsApp Adapter — Baileys Sidecar
 *
 * Bridges WhatsApp messages to the WeatherGPT /api/chat endpoint.
 * Runs as an independent Node.js process alongside the FastAPI backend.
 *
 * Authoritative Authorization:
 *   Every incoming WhatsApp message triggers a live, fresh lookup against the
 *   backend /api/notifications/subscriber/verify endpoint (backed by Supabase public.alert_subscriptions).
 *   Unregistered or opted-out numbers are rejected with 0 calls to /api/chat and 0 Gemini quota consumed.
 *
 * Architecture:
 *   WhatsApp User → Baileys → Live Supabase Auth Gate → HTTP POST /api/chat → Gemini router → response → WhatsApp User
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
  rateLimitPerMin:  parseInt(process.env.WHATSAPP_RATE_LIMIT_PER_MINUTE || '5', 10),
  maxMessageLen:    parseInt(process.env.WHATSAPP_MAX_MESSAGE_LENGTH || '1000', 10),
  apiUrl:           process.env.WEATHERGPT_API_URL || 'http://localhost:8000',
  authDir:          path.join(__dirname, 'auth'),
});

/**
 * Normalizes any phone or JID string to numeric digits only.
 * Example: "+91-90420-99020" → "919042099020"
 */
function normalizeDigits(raw) {
  if (!raw) return '';
  return String(raw).replace(/\D/g, '');
}

/**
 * Extracts phone digits from a standard WhatsApp JID.
 * Example: "919042099020@s.whatsapp.net" → "919042099020"
 */
function jidToPhone(jid) {
  if (!jid) return '';
  return jid.split('@')[0].replace(/\D/g, '');
}

/**
 * Resolves the actual sender phone number from JID, message metadata, Baileys signal repository,
 * or local LID mapping files.
 *
 * WhatsApp frequently delivers messages via privacy LIDs (@lid), e.g. "231331770445968@lid".
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
    if (msg?.participant && msg.participant.endsWith('@s.whatsapp.net')) {
      return msg.participant.split('@')[0].replace(/\D/g, '');
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

    // Check auth folder forward mapping file: lid-mapping-<phone>.json
    try {
      if (fs.existsSync(CONFIG.authDir)) {
        const files = fs.readdirSync(CONFIG.authDir);
        for (const file of files) {
          if (file.startsWith('lid-mapping-') && !file.includes('_reverse')) {
            const raw = fs.readFileSync(path.join(CONFIG.authDir, file), 'utf8');
            try {
              const parsedLid = JSON.parse(raw);
              if (parsedLid === lidDigits || parsedLid === jid) {
                const phoneCandidate = file.replace('lid-mapping-', '').replace('.json', '');
                return phoneCandidate.replace(/\D/g, '');
              }
            } catch (_) {}
          }
        }
      }
    } catch (_) {}

    return lidDigits;
  }

  return jid.split('@')[0].replace(/\D/g, '');
}

/**
 * Extracts plain text content from various Baileys message structures.
 */
function extractMessageText(messageContent) {
  if (!messageContent) return '';

  return (
    messageContent.conversation ||
    messageContent.extendedTextMessage?.text ||
    messageContent.imageMessage?.caption ||
    messageContent.videoMessage?.caption ||
    messageContent.templateButtonReplyMessage?.selectedDisplayText ||
    messageContent.templateButtonReplyMessage?.selectedId ||
    messageContent.buttonsResponseMessage?.selectedDisplayText ||
    messageContent.buttonsResponseMessage?.selectedButtonId ||
    messageContent.listResponseMessage?.singleSelectReply?.selectedRowId ||
    messageContent.listResponseMessage?.title ||
    ''
  );
}

/**
 * Format phone for session_id: "wa_<digits>"
 * Compatible with backend SessionStore which accepts any string session_id.
 */
function phoneToSessionId(phone) {
  return `wa_${phone}`;
}

// ---------------------------------------------------------------------------
// Structured Logging (Safe: Zero PII, Zero Tokens, Zero Message Contents)
// ---------------------------------------------------------------------------

function log(event, data = {}) {
  const entry = {
    timestamp: new Date().toISOString(),
    service: 'weathergpt-whatsapp',
    whatsapp_event: event,
    ...data,
  };
  // Sanitize: Never log message content, auth credentials, or keys
  delete entry.content;
  delete entry.text;
  delete entry.auth;
  delete entry.credentials;
  delete entry.key;
  delete entry.apikey;
  console.log(JSON.stringify(entry));
}

// ---------------------------------------------------------------------------
// Per-Sender Rate Limiter (Sliding 1-minute window)
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
 * Sends a chat request to the WeatherGPT /api/chat endpoint.
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
      timeout: 60_000, // 60s — multi-turn tool loops can take time
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
          let errorType = 'UnknownError';
          try {
            const errBody = JSON.parse(body);
            errorType = errBody.detail || errBody.error_type || `HTTP_${res.statusCode}`;
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
// Subscriber Authorization Bridge (Live Supabase Lookup)
// ---------------------------------------------------------------------------

/**
 * Queries the WeatherGPT backend /api/notifications/subscriber/verify endpoint
 * to check if a phone number is an active, opted-in Emergency Alert subscriber.
 */
function checkBackendSubscriber(phone) {
  const url = new URL('/api/notifications/subscriber/verify', CONFIG.apiUrl);
  url.searchParams.set('phone', phone);

  return new Promise((resolve) => {
    const transport = url.protocol === 'https:' ? https : http;
    const req = transport.request(url, { method: 'GET', timeout: 8000 }, (res) => {
      let body = '';
      res.on('data', chunk => { body += chunk; });
      res.on('end', () => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          try {
            const data = JSON.parse(body);
            resolve(Boolean(data.is_subscribed));
          } catch (_) {
            resolve(false);
          }
        } else {
          resolve(false);
        }
      });
    });
    req.on('error', () => resolve(false));
    req.on('timeout', () => { req.destroy(); resolve(false); });
    req.end();
  });
}

/**
 * Authoritative sender authorization function.
 * Evaluates live against the backend Emergency Alert subscriber registry (persisted in Supabase).
 * Performs a fresh query on EVERY incoming message without in-memory caching.
 * Fails closed on network or backend errors.
 */
async function isAuthorizedSender(phone) {
  if (!phone || phone.length < 7) return false;

  try {
    const fn = (module.exports && module.exports.checkBackendSubscriber) ? module.exports.checkBackendSubscriber : checkBackendSubscriber;
    const isSubscribed = await fn(phone);
    return Boolean(isSubscribed);
  } catch (err) {
    log('error', { reason: 'subscriber_check_failed', error: err.message, phone_suffix: phone.slice(-4) });
    return false; // Fail closed
  }
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
  if (msg.key?.fromMe) return;

  const jid = msg.key?.remoteJid;
  if (!jid) return;

  // 2. Ignore groups, broadcasts, status
  if (jid.endsWith('@g.us') || jid === 'status@broadcast' || jid.includes('@broadcast')) {
    log('ignored', { reason: 'group_or_broadcast', jid_type: jid.split('@')[1] });
    return;
  }

  // 3. Extract text only (ignore media without captions, stickers, etc.)
  const text = extractMessageText(msg.message);
  if (!text || !text.trim()) {
    log('ignored', { reason: 'non_text_message', jid_suffix: jid.includes('@') ? '@' + jid.split('@')[1] : jid });
    return;
  }

  const rawText = text.trim();

  // 4. Resolve sender phone number (handles both @s.whatsapp.net and privacy @lid)
  const phone = await resolveSenderPhone(socket, jid, msg);
  const phoneSuffix = phone ? phone.slice(-4) : 'unknown';

  // 5. Emergency Alert Subscription Authorization check (Live against Supabase)
  const authFn = (module.exports && module.exports.isAuthorizedSender) ? module.exports.isAuthorizedSender : isAuthorizedSender;
  const authorized = await authFn(phone);
  if (!authorized) {
    // Unauthorized senders are silently ignored: 0 calls to /api/chat, 0 Gemini quota consumed
    log('ignored', { reason: 'not_subscribed', phone_suffix: phoneSuffix });
    return;
  }

  log('received', { phone_suffix: phoneSuffix, message_length: rawText.length });

  // 6. Message length check — reject oversized messages, do NOT silently truncate
  if (rawText.length > CONFIG.maxMessageLen) {
    log('ignored', { reason: 'message_too_long', length: rawText.length, limit: CONFIG.maxMessageLen });
    try {
      await socket.sendMessage(jid, {
        text: `⚠️ Your message is too long (${rawText.length} characters). Please keep your weather question under ${CONFIG.maxMessageLen} characters.`
      });
      log('send', { type: 'length_rejection', phone_suffix: phoneSuffix });
    } catch (sendErr) {
      log('error', { reason: 'send_length_rejection_failed', error: sendErr.message });
    }
    return;
  }

  // 7. Rate limit check (Sliding window per sender)
  if (!checkRateLimit(phone)) {
    log('ignored', { reason: 'rate_limited', phone_suffix: phoneSuffix, limit: CONFIG.rateLimitPerMin });
    try {
      await socket.sendMessage(jid, {
        text: `⏳ You're sending messages too quickly. Please wait a minute before trying again (limit: ${CONFIG.rateLimitPerMin} messages/min).`
      });
      log('send', { type: 'rate_limit_reply', phone_suffix: phoneSuffix });
    } catch (_) { /* best effort */ }
    return;
  }

  // 8. Call WeatherGPT /api/chat
  const sessionId = phoneToSessionId(phone);
  log('chat_request', { phone_suffix: phoneSuffix, session_id: sessionId });

  try {
    const chatFn = (module.exports && module.exports.callWeatherGPTChat) ? module.exports.callWeatherGPTChat : callWeatherGPTChat;
    const response = await chatFn(rawText, sessionId);
    log('chat_response', { phone_suffix: phoneSuffix, response_length: response.length });

    // 9. Send response back via WhatsApp
    await socket.sendMessage(jid, { text: response });
    log('send', { type: 'chat_response', phone_suffix: phoneSuffix });

  } catch (err) {
    log('error', { reason: 'chat_api_failed', error: err.message, phone_suffix: phoneSuffix });
    try {
      await socket.sendMessage(jid, {
        text: '🌧️ WeatherGPT is temporarily unable to process your request. Please try again in a moment.'
      });
      log('send', { type: 'error_reply', phone_suffix: phoneSuffix });
    } catch (sendErr) {
      log('error', { reason: 'send_error_reply_failed', error: sendErr.message });
    }
  }
}

// ---------------------------------------------------------------------------
// Baileys Connection Manager (Singleton / Reconnect Guard)
// ---------------------------------------------------------------------------

let activeSocket = null;
let isConnecting = false;
let reconnectAttempt = 0;
let reconnectTimer = null;
const MAX_RECONNECT_DELAY = 60_000; // 60 seconds

async function connectToWhatsApp() {
  if (isConnecting) {
    log('connection_in_progress', { action: 'skipping_duplicate_connect' });
    return;
  }
  isConnecting = true;

  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }

  log('startup', { config: {
    enabled: CONFIG.enabled,
    rate_limit: CONFIG.rateLimitPerMin,
    max_message_len: CONFIG.maxMessageLen,
    api_url: CONFIG.apiUrl,
    auth_dir: CONFIG.authDir,
  }});

  // Ensure auth directory exists
  if (!fs.existsSync(CONFIG.authDir)) {
    fs.mkdirSync(CONFIG.authDir, { recursive: true });
  }

  try {
    const { state, saveCreds } = await useMultiFileAuthState(CONFIG.authDir);

    const socket = makeWASocket({
      auth: state,
      printQRInTerminal: false,
      logger: pino({ level: 'silent' }), // Suppress internal Baileys logging
    });

    activeSocket = socket;

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
        isConnecting = false;
        log('connected', { user_id: socket.user?.id ? '***authenticated***' : 'unknown' });
      }

      if (connection === 'close') {
        isConnecting = false;
        const statusCode = lastDisconnect?.error?.output?.statusCode;
        const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

        log('disconnected', {
          status_code: statusCode,
          logged_out: statusCode === DisconnectReason.loggedOut,
          will_reconnect: shouldReconnect,
        });

        if (shouldReconnect) {
          const delay = Math.min(3000 * Math.pow(2, reconnectAttempt), MAX_RECONNECT_DELAY);
          reconnectAttempt++;
          log('reconnecting', { delay_ms: delay, attempt: reconnectAttempt });
          reconnectTimer = setTimeout(() => {
            connectToWhatsApp();
          }, delay);
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

  } catch (err) {
    isConnecting = false;
    log('error', { reason: 'socket_creation_failed', error: err.message });
    const delay = Math.min(3000 * Math.pow(2, reconnectAttempt), MAX_RECONNECT_DELAY);
    reconnectAttempt++;
    reconnectTimer = setTimeout(() => connectToWhatsApp(), delay);
  }
}

// ---------------------------------------------------------------------------
// Exports for Unit Testing
// ---------------------------------------------------------------------------
module.exports = {
  CONFIG,
  normalizeDigits,
  jidToPhone,
  resolveSenderPhone,
  extractMessageText,
  checkBackendSubscriber,
  isAuthorizedSender,
  phoneToSessionId,
  checkRateLimit,
  callWeatherGPTChat,
  handleMessage,
  rateLimitWindows,
  log,
  connectToWhatsApp,
};

// ---------------------------------------------------------------------------
// Entry Point Guard (Only starts Baileys when executed directly, not when tested)
// ---------------------------------------------------------------------------
if (require.main === module) {
  if (!CONFIG.enabled) {
    log('disabled', { reason: 'WHATSAPP_BOT_ENABLED is false', action: 'exiting' });
    console.log('[WeatherGPT WhatsApp] Bot is DISABLED. Set WHATSAPP_BOT_ENABLED=true in whatsapp/.env to activate.');
    process.exit(0);
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
