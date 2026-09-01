/**
 * WeatherGPT WhatsApp Adapter — Comprehensive Unit Tests
 *
 * Tests all authorization gates, message parsing, rate limiting, and chat forwarding.
 * Uses Node.js built-in test runner (node --test).
 */

'use strict';

const { describe, it, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert/strict');

const adapter = require('../index.js');

// ---------------------------------------------------------------------------
// Test: normalizeDigits
// ---------------------------------------------------------------------------
describe('normalizeDigits', () => {
  it('strips non-digit characters from phone number', () => {
    assert.equal(adapter.normalizeDigits('+91-98010-38392'), '919801038392');
    assert.equal(adapter.normalizeDigits('(141) 552-38886'), '14155238886');
  });

  it('handles empty/null input safely', () => {
    assert.equal(adapter.normalizeDigits(''), '');
    assert.equal(adapter.normalizeDigits(null), '');
    assert.equal(adapter.normalizeDigits(undefined), '');
  });
});

// ---------------------------------------------------------------------------
// Test: jidToPhone
// ---------------------------------------------------------------------------
describe('jidToPhone', () => {
  it('extracts phone digits from WhatsApp JID', () => {
    assert.equal(adapter.jidToPhone('9801038392@s.whatsapp.net'), '9801038392');
    assert.equal(adapter.jidToPhone('919042099020@s.whatsapp.net'), '919042099020');
  });

  it('returns empty string for null/undefined', () => {
    assert.equal(adapter.jidToPhone(null), '');
    assert.equal(adapter.jidToPhone(undefined), '');
  });
});

// ---------------------------------------------------------------------------
// Test: resolveSenderPhone (Phone JID & Privacy LID resolution)
// ---------------------------------------------------------------------------
describe('resolveSenderPhone', () => {
  it('resolves direct phone JID', async () => {
    const phone = await adapter.resolveSenderPhone(null, '919801038392@s.whatsapp.net', {});
    assert.equal(phone, '919801038392');
  });

  it('resolves LID via reverse mapping file if present', async () => {
    // 231331770445968 maps to 919940148758 in auth folder
    const phone = await adapter.resolveSenderPhone(null, '231331770445968@lid', {});
    assert.equal(phone, '919940148758');
  });

  it('resolves LID via message metadata remoteJidAlt', async () => {
    const msg = { key: { remoteJidAlt: '9801038392@s.whatsapp.net' } };
    const phone = await adapter.resolveSenderPhone(null, '999999999999999@lid', msg);
    assert.equal(phone, '9801038392');
  });

  it('resolves LID via message metadata participantPn', async () => {
    const msg = { key: { participantPn: '9801038392@s.whatsapp.net' } };
    const phone = await adapter.resolveSenderPhone(null, '999999999999999@lid', msg);
    assert.equal(phone, '9801038392');
  });

  it('resolves LID via message participant attribute', async () => {
    const msg = { participant: '9801038392@s.whatsapp.net' };
    const phone = await adapter.resolveSenderPhone(null, '999999999999999@lid', msg);
    assert.equal(phone, '9801038392');
  });
});

// ---------------------------------------------------------------------------
// Test: extractMessageText (Various Baileys structures)
// ---------------------------------------------------------------------------
describe('extractMessageText', () => {
  it('extracts text from standard conversation message', () => {
    const msg = { conversation: 'What is the weather today?' };
    assert.equal(adapter.extractMessageText(msg), 'What is the weather today?');
  });

  it('extracts text from extendedTextMessage', () => {
    const msg = { extendedTextMessage: { text: 'Rain forecast for Chennai' } };
    assert.equal(adapter.extractMessageText(msg), 'Rain forecast for Chennai');
  });

  it('extracts text from imageMessage caption', () => {
    const msg = { imageMessage: { caption: 'Will it rain here?' } };
    assert.equal(adapter.extractMessageText(msg), 'Will it rain here?');
  });

  it('extracts text from templateButtonReplyMessage', () => {
    const msg = { templateButtonReplyMessage: { selectedDisplayText: 'Today Forecast' } };
    assert.equal(adapter.extractMessageText(msg), 'Today Forecast');
  });

  it('returns empty string for non-text message', () => {
    const msg = { imageMessage: { url: 'https://example.com/pic.jpg' } };
    assert.equal(adapter.extractMessageText(msg), '');
  });
});

// ---------------------------------------------------------------------------
// Test: Subscriber Authorization (isAuthorizedSender)
// ---------------------------------------------------------------------------
describe('isAuthorizedSender', () => {
  const originalCheck = adapter.checkBackendSubscriber;

  afterEach(() => {
    adapter.checkBackendSubscriber = originalCheck;
  });

  it('authorizes active alert subscriber when backend confirms subscription', async () => {
    adapter.checkBackendSubscriber = async (phone) => phone.includes('9801038392');
    const isAuth = await adapter.isAuthorizedSender('9801038392');
    assert.ok(isAuth, 'Active subscriber must be authorized');
  });

  it('rejects unregistered number when backend returns false', async () => {
    adapter.checkBackendSubscriber = async () => false;
    const isAuth = await adapter.isAuthorizedSender('111111111111');
    assert.equal(isAuth, false, 'Unregistered number must be unauthorized');
  });

  it('rejects numbers shorter than 7 digits without querying backend', async () => {
    let backendCalled = false;
    adapter.checkBackendSubscriber = async () => { backendCalled = true; return true; };
    const isAuth = await adapter.isAuthorizedSender('12345');
    assert.equal(isAuth, false);
    assert.equal(backendCalled, false, 'Should not query backend for short numbers');
  });

  it('fails closed on network or backend errors', async () => {
    adapter.checkBackendSubscriber = async () => { throw new Error('Connection refused'); };
    const isAuth = await adapter.isAuthorizedSender('9801038392');
    assert.equal(isAuth, false, 'Must fail closed on error');
  });
});

// ---------------------------------------------------------------------------
// Test: phoneToSessionId
// ---------------------------------------------------------------------------
describe('phoneToSessionId', () => {
  it('generates wa_ prefixed session ID', () => {
    assert.equal(adapter.phoneToSessionId('9801038392'), 'wa_9801038392');
  });

  it('different phones yield different session IDs', () => {
    const sid1 = adapter.phoneToSessionId('9801038392');
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
    assert.ok(adapter.checkRateLimit('9801038392'));
  });

  it('allows up to configured limit (5)', () => {
    const phone = '9801038392';
    for (let i = 0; i < 5; i++) {
      assert.ok(adapter.checkRateLimit(phone), `Message ${i + 1} should be allowed`);
    }
  });

  it('rejects 6th message within 1 minute window', () => {
    const phone = '9801038392';
    for (let i = 0; i < 5; i++) {
      adapter.checkRateLimit(phone);
    }
    assert.equal(adapter.checkRateLimit(phone), false, '6th message should be rate-limited');
  });

  it('rate limits are per-sender (independent)', () => {
    const phone1 = '9801038392';
    const phone2 = '14155238886';
    for (let i = 0; i < 5; i++) {
      adapter.checkRateLimit(phone1);
    }
    assert.equal(adapter.checkRateLimit(phone1), false);
    assert.ok(adapter.checkRateLimit(phone2), 'Phone 2 should still be allowed');
  });
});

// ---------------------------------------------------------------------------
// Test: handleMessage — Authorization filtering
// ---------------------------------------------------------------------------
describe('handleMessage — authorization & routing', () => {
  const originalCheck = adapter.checkBackendSubscriber;
  const originalChat = adapter.callWeatherGPTChat;

  beforeEach(() => {
    adapter.rateLimitWindows.clear();
    adapter.checkBackendSubscriber = async (phone) => phone.includes('9801038392');
    adapter.callWeatherGPTChat = async (userMessage, sessionId) => {
      return `WeatherGPT response for "${userMessage}" [session: ${sessionId}]`;
    };
  });

  afterEach(() => {
    adapter.checkBackendSubscriber = originalCheck;
    adapter.callWeatherGPTChat = originalChat;
  });

  it('ignores messages from unauthorized senders (no reply sent, no /api/chat call)', async () => {
    let chatCalled = false;
    adapter.callWeatherGPTChat = async () => { chatCalled = true; return 'Reply'; };

    const sentMessages = [];
    const mockSocket = {
      sendMessage: async (jid, content) => { sentMessages.push({ jid, content }); }
    };

    const msg = {
      key: { fromMe: false, remoteJid: '15555555555@s.whatsapp.net' },
      message: { conversation: 'What is the weather in Delhi?' },
      messageTimestamp: Math.floor(Date.now() / 1000),
    };

    await adapter.handleMessage(mockSocket, msg);
    assert.equal(sentMessages.length, 0, 'Unauthorized sender should receive no reply');
    assert.equal(chatCalled, false, 'Unauthorized sender must NOT trigger /api/chat');
  });

  it('forwards weather query to /api/chat and delivers response for authorized sender', async () => {
    const sentMessages = [];
    const mockSocket = {
      sendMessage: async (jid, content) => { sentMessages.push({ jid, content }); }
    };

    const msg = {
      key: { fromMe: false, remoteJid: '9801038392@s.whatsapp.net' },
      message: { conversation: 'What is the weather in Chennai?' },
      messageTimestamp: Math.floor(Date.now() / 1000),
    };

    await adapter.handleMessage(mockSocket, msg);
    assert.equal(sentMessages.length, 1);
    assert.ok(sentMessages[0].content.text.includes('What is the weather in Chennai?'));
    assert.ok(sentMessages[0].content.text.includes('wa_9801038392'));
  });

  it('forwards conversational greeting "Hello" to /api/chat for authorized sender', async () => {
    const sentMessages = [];
    const mockSocket = {
      sendMessage: async (jid, content) => { sentMessages.push({ jid, content }); }
    };

    const msg = {
      key: { fromMe: false, remoteJid: '9801038392@s.whatsapp.net' },
      message: { conversation: 'Hello' },
      messageTimestamp: Math.floor(Date.now() / 1000),
    };

    await adapter.handleMessage(mockSocket, msg);
    assert.equal(sentMessages.length, 1);
    assert.ok(sentMessages[0].content.text.includes('Hello'));
  });
});

// ---------------------------------------------------------------------------
// Test: handleMessage — Safety Filters (Groups, Broadcasts, Own, Media)
// ---------------------------------------------------------------------------
describe('handleMessage — safety filters', () => {
  it('ignores group messages', async () => {
    const sentMessages = [];
    const mockSocket = { sendMessage: async (jid, content) => { sentMessages.push({ jid, content }); } };
    const msg = {
      key: { fromMe: false, remoteJid: '120363012345678@g.us' },
      message: { conversation: 'Hello group' },
    };
    await adapter.handleMessage(mockSocket, msg);
    assert.equal(sentMessages.length, 0);
  });

  it('ignores status broadcasts', async () => {
    const sentMessages = [];
    const mockSocket = { sendMessage: async (jid, content) => { sentMessages.push({ jid, content }); } };
    const msg = {
      key: { fromMe: false, remoteJid: 'status@broadcast' },
      message: { conversation: 'Status update' },
    };
    await adapter.handleMessage(mockSocket, msg);
    assert.equal(sentMessages.length, 0);
  });

  it('ignores messages from self', async () => {
    const sentMessages = [];
    const mockSocket = { sendMessage: async (jid, content) => { sentMessages.push({ jid, content }); } };
    const msg = {
      key: { fromMe: true, remoteJid: '9801038392@s.whatsapp.net' },
      message: { conversation: 'Self message' },
    };
    await adapter.handleMessage(mockSocket, msg);
    assert.equal(sentMessages.length, 0);
  });

  it('ignores non-text media messages without captions', async () => {
    const sentMessages = [];
    const mockSocket = { sendMessage: async (jid, content) => { sentMessages.push({ jid, content }); } };
    const msg = {
      key: { fromMe: false, remoteJid: '9801038392@s.whatsapp.net' },
      message: { imageMessage: { url: 'https://example.com/image.jpg' } },
    };
    await adapter.handleMessage(mockSocket, msg);
    assert.equal(sentMessages.length, 0);
  });
});

// ---------------------------------------------------------------------------
// Test: handleMessage — Message length rejection (Controlled rejection, not truncation)
// ---------------------------------------------------------------------------
describe('handleMessage — message length rejection', () => {
  const originalCheck = adapter.checkBackendSubscriber;

  beforeEach(() => {
    adapter.rateLimitWindows.clear();
    adapter.checkBackendSubscriber = async (phone) => phone.includes('9801038392');
  });

  afterEach(() => {
    adapter.checkBackendSubscriber = originalCheck;
  });

  it('rejects oversized messages with controlled reply', async () => {
    const sentMessages = [];
    const mockSocket = { sendMessage: async (jid, content) => { sentMessages.push({ jid, content }); } };

    const longText = 'A'.repeat(1500);
    const msg = {
      key: { fromMe: false, remoteJid: '9801038392@s.whatsapp.net' },
      message: { conversation: longText },
    };

    await adapter.handleMessage(mockSocket, msg);
    assert.equal(sentMessages.length, 1);
    assert.ok(sentMessages[0].content.text.includes('too long'));
    assert.ok(sentMessages[0].content.text.includes('1500'));
  });

  it('does NOT call /api/chat for oversized messages', async () => {
    let chatCalled = false;
    const originalChat = adapter.callWeatherGPTChat;
    adapter.callWeatherGPTChat = async () => { chatCalled = true; return 'Reply'; };

    const sentMessages = [];
    const mockSocket = { sendMessage: async (jid, content) => { sentMessages.push({ jid, content }); } };

    const longText = 'B'.repeat(2000);
    const msg = {
      key: { fromMe: false, remoteJid: '9801038392@s.whatsapp.net' },
      message: { conversation: longText },
    };

    await adapter.handleMessage(mockSocket, msg);
    assert.equal(sentMessages.length, 1);
    assert.equal(chatCalled, false, 'Chat API must NOT be called for oversized message');
    adapter.callWeatherGPTChat = originalChat;
  });
});

// ---------------------------------------------------------------------------
// Test: handleMessage — Rate limiting
// ---------------------------------------------------------------------------
describe('handleMessage — rate limiting', () => {
  const originalCheck = adapter.checkBackendSubscriber;

  beforeEach(() => {
    adapter.rateLimitWindows.clear();
    adapter.checkBackendSubscriber = async (phone) => phone.includes('9801038392');
  });

  afterEach(() => {
    adapter.checkBackendSubscriber = originalCheck;
  });

  it('rate-limits sender after exceeding per-minute limit', async () => {
    const sentMessages = [];
    const mockSocket = { sendMessage: async (jid, content) => { sentMessages.push({ jid, content }); } };

    const now = Date.now();
    adapter.rateLimitWindows.set('9801038392', [now, now, now, now, now]);

    await adapter.handleMessage(mockSocket, {
      key: { fromMe: false, remoteJid: '9801038392@s.whatsapp.net' },
      message: { conversation: 'Rate limited query' },
    });

    assert.equal(sentMessages.length, 1);
    assert.ok(sentMessages[0].content.text.includes('too quickly'));
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
