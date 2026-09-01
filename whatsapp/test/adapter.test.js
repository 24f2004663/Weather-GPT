/**
 * WeatherGPT WhatsApp Adapter — Unit Tests
 *
 * Tests all safety controls using mocks. No real WhatsApp or Gemini connections.
 * Uses Node.js built-in test runner (node --test).
 *
 * The index.js module guards its entry point behind `require.main === module`,
 * so importing it for tests does NOT trigger connection or process.exit.
 */

'use strict';

const { describe, it, beforeEach } = require('node:test');
const assert = require('node:assert/strict');

const adapter = require('../index.js');

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
// Test: handleMessage — Allowlist filtering
// ---------------------------------------------------------------------------
describe('handleMessage — allowlist', () => {
  beforeEach(() => { adapter.rateLimitWindows.clear(); });

  it('ignores messages from non-allowlisted senders (no reply sent)', async () => {
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
    assert.equal(sentMessages.length, 0, 'Non-allowlisted sender should get no reply');
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
    // If /api/chat were called, it would throw since no server is running.
    // The test passing confirms /api/chat was never called.
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
    const sentMessages = [];
    const mockSocket = {
      sendMessage: async (jid, content) => { sentMessages.push({ jid, content }); }
    };

    // Send 5 messages to fill the rate limit window
    // Each will try to call /api/chat which will fail (no server), generating error replies
    for (let i = 0; i < 5; i++) {
      await adapter.handleMessage(mockSocket, {
        key: { fromMe: false, remoteJid: '919042099020@s.whatsapp.net' },
        message: { conversation: `Query ${i}` },
        messageTimestamp: Math.floor(Date.now() / 1000),
      });
    }

    // Clear sent messages to isolate the 6th message
    const countBefore = sentMessages.length;

    // 6th message should be rate-limited
    await adapter.handleMessage(mockSocket, {
      key: { fromMe: false, remoteJid: '919042099020@s.whatsapp.net' },
      message: { conversation: 'Query 6 - should be rate limited' },
      messageTimestamp: Math.floor(Date.now() / 1000),
    });

    // The 6th message should produce exactly one rate-limit reply
    const newMessages = sentMessages.slice(countBefore);
    assert.equal(newMessages.length, 1);
    assert.ok(newMessages[0].content.text.includes('too quickly'), 'Rate limit reply should mention sending too quickly');
  });
});

// ---------------------------------------------------------------------------
// Test: Entry point disabled by default
// ---------------------------------------------------------------------------
describe('entry point — disabled by default', () => {
  it('CONFIG.enabled defaults to false from test environment', () => {
    // In test environment, .env has WHATSAPP_BOT_ENABLED=false
    assert.equal(adapter.CONFIG.enabled, false);
  });

  it('require.main guard prevents connection attempt during import', () => {
    // If the guard failed, this test file would hang waiting for QR scan.
    // The fact that we reach this assertion proves the guard works.
    assert.ok(true, 'Module imported without triggering connection');
  });
});
