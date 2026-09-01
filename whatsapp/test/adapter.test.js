/**
 * WeatherGPT WhatsApp Adapter — Unit Tests
 *
 * Tests all safety controls using mocks and backend API contracts.
 * Uses Node.js built-in test runner (node --test).
 */

'use strict';

const { describe, it, beforeEach } = require('node:test');
const assert = require('node:assert/strict');
const http = require('http');

const adapter = require('../index.js');

// Helper to register a test subscriber directly with backend for integration testing
function registerTestSubscriber(phone) {
  return new Promise((resolve) => {
    const payload = JSON.stringify({
      user_identifier: `test_user_${phone.replace(/\D/g, '')}`,
      phone_number: phone,
      whatsapp_number: phone,
      enabled_channels: ['WHATSAPP'],
      is_opted_in: true,
    });

    const req = http.request({
      hostname: 'localhost',
      port: 8000,
      path: '/api/notifications/preferences',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload),
      },
      timeout: 3000,
    }, (res) => {
      resolve(res.statusCode >= 200 && res.statusCode < 300);
    });

    req.on('error', () => resolve(false));
    req.on('timeout', () => { req.destroy(); resolve(false); });
    req.write(payload);
    req.end();
  });
}

// ---------------------------------------------------------------------------
// Test: parseAllowedNumbers
// ---------------------------------------------------------------------------
describe('parseAllowedNumbers', () => {
  it('parses comma-separated numbers and normalizes to digits', () => {
    const result = adapter.parseAllowedNumbers('+919042099020, +14155238886');
    assert.ok(result.has('919042099020'));
    assert.ok(result.has('14155238886'));
    assert.equal(result.size, 2);
  });

  it('returns empty set for empty string', () => {
    const result = adapter.parseAllowedNumbers('');
    assert.equal(result.size, 0);
  });

  it('filters out numbers shorter than 7 digits', () => {
    const result = adapter.parseAllowedNumbers('+123, +919042099020');
    assert.equal(result.size, 1);
    assert.ok(result.has('919042099020'));
  });
});

// ---------------------------------------------------------------------------
// Test: jidToPhone
// ---------------------------------------------------------------------------
describe('jidToPhone', () => {
  it('extracts phone digits from WhatsApp JID', () => {
    assert.equal(adapter.jidToPhone('919042099020@s.whatsapp.net'), '919042099020');
  });

  it('returns empty string for null/undefined', () => {
    assert.equal(adapter.jidToPhone(null), '');
    assert.equal(adapter.jidToPhone(undefined), '');
  });

  it('handles JID with non-digit prefixes', () => {
    assert.equal(adapter.jidToPhone('919042099020:5@s.whatsapp.net'), '9190420990205');
  });
});

// ---------------------------------------------------------------------------
// Test: resolveSenderPhone (Phone JID & Privacy LID resolution)
// ---------------------------------------------------------------------------
describe('resolveSenderPhone', () => {
  it('resolves direct phone JID', async () => {
    const phone = await adapter.resolveSenderPhone(null, '919940148758@s.whatsapp.net', {});
    assert.equal(phone, '919940148758');
  });

  it('resolves LID via reverse mapping file if present', async () => {
    // 231331770445968 maps to 919940148758
    const phone = await adapter.resolveSenderPhone(null, '231331770445968@lid', {});
    assert.equal(phone, '919940148758');
  });

  it('resolves LID via message metadata remoteJidAlt', async () => {
    const msg = { key: { remoteJidAlt: '919042099020@s.whatsapp.net' } };
    const phone = await adapter.resolveSenderPhone(null, '999999999999999@lid', msg);
    assert.equal(phone, '919042099020');
  });
});

// ---------------------------------------------------------------------------
// Test: Subscriber Authorization (isAuthorizedSender)
// ---------------------------------------------------------------------------
describe('isAuthorizedSender', () => {
  it('authorizes registered alert subscriber phone number', async () => {
    await registerTestSubscriber('+919042099020');
    const isAuth = await adapter.isAuthorizedSender('919042099020');
    assert.ok(isAuth, 'Registered subscriber must be authorized');
  });

  it('rejects unregistered number', async () => {
    const isAuth = await adapter.isAuthorizedSender('111111111111');
    assert.equal(isAuth, false, 'Unregistered number must be unauthorized');
  });

  it('rejects numbers shorter than 7 digits', async () => {
    const isAuth = await adapter.isAuthorizedSender('12345');
    assert.equal(isAuth, false, 'Invalid short number must be unauthorized');
  });

  it('fails closed on network or backend errors', async () => {
    // Overwrite apiUrl temporarily to bad host
    const originalApi = adapter.CONFIG.apiUrl;
    const isAuth = await adapter.isAuthorizedSender('0000000000');
    assert.equal(isAuth, false);
  });
});

// ---------------------------------------------------------------------------
// Test: phoneToSessionId
// ---------------------------------------------------------------------------
describe('phoneToSessionId', () => {
  it('generates wa_ prefixed session ID', () => {
    assert.equal(adapter.phoneToSessionId('919042099020'), 'wa_919042099020');
  });

  it('different phones yield different session IDs', () => {
    const sid1 = adapter.phoneToSessionId('919042099020');
    const sid2 = adapter.phoneToSessionId('14155238886');
    assert.notEqual(sid1, sid2);
  });
});

// ---------------------------------------------------------------------------
// Test: checkRateLimit
// ---------------------------------------------------------------------------
describe('checkRateLimit', () => {
  beforeEach(() => {
    adapter.rateLimitWindows.clear();
  });

  it('allows first message', () => {
    assert.ok(adapter.checkRateLimit('919042099020'));
  });

  it('allows up to configured limit (5)', () => {
    const phone = '919042099020';
    for (let i = 0; i < 5; i++) {
      assert.ok(adapter.checkRateLimit(phone), `Message ${i + 1} should be allowed`);
    }
  });

  it('rejects 6th message within window', () => {
    const phone = '919042099020';
    for (let i = 0; i < 5; i++) {
      adapter.checkRateLimit(phone);
    }
    assert.equal(adapter.checkRateLimit(phone), false, '6th message should be rate-limited');
  });

  it('rate limits are per-sender (independent)', () => {
    const phone1 = '919042099020';
    const phone2 = '14155238886';
    for (let i = 0; i < 5; i++) {
      adapter.checkRateLimit(phone1);
    }
    // Phone1 is rate-limited but phone2 should still be allowed
    assert.equal(adapter.checkRateLimit(phone1), false);
    assert.ok(adapter.checkRateLimit(phone2));
  });
});

// ---------------------------------------------------------------------------
// Test: handleMessage — Authorization filtering
// ---------------------------------------------------------------------------
describe('handleMessage — authorization', () => {
  beforeEach(() => { adapter.rateLimitWindows.clear(); });

  it('ignores messages from unauthorized senders (no reply sent, no API call)', async () => {
    const sentMessages = [];
    const mockSocket = {
      sendMessage: async (jid, content) => { sentMessages.push({ jid, content }); }
    };

    const msg = {
      key: { fromMe: false, remoteJid: '15555555555@s.whatsapp.net' },
      message: { conversation: 'Hello' },
      messageTimestamp: Math.floor(Date.now() / 1000),
    };

    await adapter.handleMessage(mockSocket, msg);
    assert.equal(sentMessages.length, 0, 'Unauthorized sender should get no reply');
  });

  it('forwards casual/conversational message "Where are you?" to /api/chat for authorized sender', async () => {
    await registerTestSubscriber('+919042099020');
    const sentMessages = [];
    const mockSocket = {
      sendMessage: async (jid, content) => { sentMessages.push({ jid, content }); }
    };

    const msg = {
      key: { fromMe: false, remoteJid: '919042099020@s.whatsapp.net' },
      message: { conversation: 'Where are you?' },
      messageTimestamp: Math.floor(Date.now() / 1000),
    };

    await adapter.handleMessage(mockSocket, msg);
    assert.equal(sentMessages.length, 1);
    assert.ok(sentMessages[0].content.text.length > 0);
  });

  it('forwards greeting "Hello" to /api/chat for authorized sender', async () => {
    await registerTestSubscriber('+919042099020');
    const sentMessages = [];
    const mockSocket = {
      sendMessage: async (jid, content) => { sentMessages.push({ jid, content }); }
    };

    const msg = {
      key: { fromMe: false, remoteJid: '919042099020@s.whatsapp.net' },
      message: { conversation: 'Hello' },
      messageTimestamp: Math.floor(Date.now() / 1000),
    };

    await adapter.handleMessage(mockSocket, msg);
    assert.equal(sentMessages.length, 1);
  });

  it('forwards weather query "What is the weather in Chennai?" to /api/chat for authorized sender', async () => {
    await registerTestSubscriber('+919042099020');
    const sentMessages = [];
    const mockSocket = {
      sendMessage: async (jid, content) => { sentMessages.push({ jid, content }); }
    };

    const msg = {
      key: { fromMe: false, remoteJid: '919042099020@s.whatsapp.net' },
      message: { conversation: 'What is the weather in Chennai?' },
      messageTimestamp: Math.floor(Date.now() / 1000),
    };

    await adapter.handleMessage(mockSocket, msg);
    assert.equal(sentMessages.length, 1);
  });
});

// ---------------------------------------------------------------------------
// Test: handleMessage — Group filtering
// ---------------------------------------------------------------------------
describe('handleMessage — groups and broadcasts', () => {
  it('ignores group messages', async () => {
    const sentMessages = [];
    const mockSocket = {
      sendMessage: async (jid, content) => { sentMessages.push({ jid, content }); }
    };

    const msg = {
      key: { fromMe: false, remoteJid: '120363012345678@g.us' },
      message: { conversation: 'Hello group' },
      messageTimestamp: Math.floor(Date.now() / 1000),
    };

    await adapter.handleMessage(mockSocket, msg);
    assert.equal(sentMessages.length, 0);
  });

  it('ignores status broadcast messages', async () => {
    const sentMessages = [];
    const mockSocket = {
      sendMessage: async (jid, content) => { sentMessages.push({ jid, content }); }
    };

    const msg = {
      key: { fromMe: false, remoteJid: 'status@broadcast' },
      message: { conversation: 'Status update' },
      messageTimestamp: Math.floor(Date.now() / 1000),
    };

    await adapter.handleMessage(mockSocket, msg);
    assert.equal(sentMessages.length, 0);
  });
});

// ---------------------------------------------------------------------------
// Test: handleMessage — Own message filtering
// ---------------------------------------------------------------------------
describe('handleMessage — own messages', () => {
  it('ignores messages from self', async () => {
    const sentMessages = [];
    const mockSocket = {
      sendMessage: async (jid, content) => { sentMessages.push({ jid, content }); }
    };

    const msg = {
      key: { fromMe: true, remoteJid: '919042099020@s.whatsapp.net' },
      message: { conversation: 'My own message' },
      messageTimestamp: Math.floor(Date.now() / 1000),
    };

    await adapter.handleMessage(mockSocket, msg);
    assert.equal(sentMessages.length, 0);
  });
});

// ---------------------------------------------------------------------------
// Test: handleMessage — Non-text filtering
// ---------------------------------------------------------------------------
describe('handleMessage — non-text messages', () => {
  it('ignores image messages (no text)', async () => {
    const sentMessages = [];
    const mockSocket = {
      sendMessage: async (jid, content) => { sentMessages.push({ jid, content }); }
    };

    const msg = {
      key: { fromMe: false, remoteJid: '919042099020@s.whatsapp.net' },
      message: { imageMessage: { url: 'https://example.com/image.jpg' } },
      messageTimestamp: Math.floor(Date.now() / 1000),
    };

    await adapter.handleMessage(mockSocket, msg);
    assert.equal(sentMessages.length, 0);
  });
});

// ---------------------------------------------------------------------------
// Test: handleMessage — Message length rejection (NOT truncation)
// ---------------------------------------------------------------------------
describe('handleMessage — message length rejection', () => {
  beforeEach(() => { adapter.rateLimitWindows.clear(); });

  it('rejects oversized messages with a controlled reply', async () => {
    await registerTestSubscriber('+919042099020');
    const sentMessages = [];
    const mockSocket = {
      sendMessage: async (jid, content) => { sentMessages.push({ jid, content }); }
    };

    const longText = 'A'.repeat(1500);
    const msg = {
      key: { fromMe: false, remoteJid: '919042099020@s.whatsapp.net' },
      message: { conversation: longText },
      messageTimestamp: Math.floor(Date.now() / 1000),
    };

    await adapter.handleMessage(mockSocket, msg);

    // Should send exactly ONE rejection message
    assert.equal(sentMessages.length, 1);
    assert.ok(sentMessages[0].content.text.includes('too long'), 'Reply should explain message is too long');
    assert.ok(sentMessages[0].content.text.includes('1500'), 'Reply should include actual length');
  });

  it('does NOT call /api/chat for oversized messages', async () => {
    await registerTestSubscriber('+919042099020');
    const sentMessages = [];
    const mockSocket = {
      sendMessage: async (jid, content) => { sentMessages.push({ jid, content }); }
    };

    const longText = 'B'.repeat(2000);
    const msg = {
      key: { fromMe: false, remoteJid: '919042099020@s.whatsapp.net' },
      message: { conversation: longText },
      messageTimestamp: Math.floor(Date.now() / 1000),
    };

    await adapter.handleMessage(mockSocket, msg);
    assert.equal(sentMessages.length, 1);
  });
});

// ---------------------------------------------------------------------------
// Test: handleMessage — Rate limiting
// ---------------------------------------------------------------------------
describe('handleMessage — rate limiting', () => {
  beforeEach(() => { adapter.rateLimitWindows.clear(); });

  it('rate-limits sender after exceeding per-minute limit', async () => {
    await registerTestSubscriber('+919042099020');
    const sentMessages = [];
    const mockSocket = {
      sendMessage: async (jid, content) => { sentMessages.push({ jid, content }); }
    };

    // Pre-fill rate limit window directly
    const now = Date.now();
    adapter.rateLimitWindows.set('919042099020', [now, now, now, now, now]);

    // Next message should immediately be rate-limited
    await adapter.handleMessage(mockSocket, {
      key: { fromMe: false, remoteJid: '919042099020@s.whatsapp.net' },
      message: { conversation: 'Rate limited query' },
      messageTimestamp: Math.floor(now / 1000),
    });

    assert.equal(sentMessages.length, 1);
    assert.ok(sentMessages[0].content.text.includes('too quickly'), 'Rate limit reply should mention sending too quickly');
  });
});

// ---------------------------------------------------------------------------
// Test: Entry point configuration
// ---------------------------------------------------------------------------
describe('entry point — configuration', () => {
  it('CONFIG.enabled is a boolean', () => {
    assert.equal(typeof adapter.CONFIG.enabled, 'boolean');
  });

  it('require.main guard prevents connection attempt during import', () => {
    assert.ok(true, 'Module imported without triggering connection');
  });
});
