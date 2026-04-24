'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
  encryptValue,
  decryptValue,
  migratePlaintext,
  readSecret,
} = require('../secret-store.js');

/** Fake safeStorage that XORs with 0x5A — deterministic, reversible, nothing real. */
function fakeSafeStorage({ available = true } = {}) {
  return {
    isEncryptionAvailable: () => available,
    encryptString: (s) => {
      const buf = Buffer.from(s, 'utf8');
      for (let i = 0; i < buf.length; i++) buf[i] ^= 0x5a;
      return buf;
    },
    decryptString: (buf) => {
      const out = Buffer.from(buf);
      for (let i = 0; i < out.length; i++) out[i] ^= 0x5a;
      return out.toString('utf8');
    },
  };
}

test('encryptValue returns null when safeStorage is unavailable', () => {
  assert.equal(encryptValue(fakeSafeStorage({ available: false }), 'secret'), null);
  assert.equal(encryptValue(null, 'secret'), null);
});

test('encryptValue / decryptValue round-trip a non-empty string', () => {
  const ss = fakeSafeStorage();
  const encoded = encryptValue(ss, 'hf_abcDEF123');
  assert.equal(typeof encoded, 'string');
  assert.notEqual(encoded, 'hf_abcDEF123');
  assert.equal(decryptValue(ss, encoded), 'hf_abcDEF123');
});

test('encryptValue refuses empty / non-string input', () => {
  const ss = fakeSafeStorage();
  assert.equal(encryptValue(ss, ''), null);
  assert.equal(encryptValue(ss, null), null);
  assert.equal(encryptValue(ss, 42), null);
});

test('decryptValue returns empty on empty input', () => {
  const ss = fakeSafeStorage();
  assert.equal(decryptValue(ss, ''), '');
  assert.equal(decryptValue(ss, undefined), '');
});

test('decryptValue swallows decrypt throws (real safeStorage throws on bad blobs)', () => {
  const throwing = {
    isEncryptionAvailable: () => true,
    decryptString: () => { throw new Error('Invalid encryption scheme'); },
  };
  assert.equal(decryptValue(throwing, 'whatever=='), '');
});

test('migratePlaintext upgrades hf_token + anthropic_api_key to encrypted keys', () => {
  const ss = fakeSafeStorage();
  const { settings, changed } = migratePlaintext(
    { hf_token: 'hf_abc', anthropic_api_key: 'sk-ant-xyz', data_dir: '/tmp' },
    ss,
  );
  assert.equal(changed, true);
  assert.equal(settings.hf_token, undefined);
  assert.equal(settings.anthropic_api_key, undefined);
  assert.ok(settings.hf_token_encrypted);
  assert.ok(settings.anthropic_api_key_encrypted);
  assert.equal(settings.data_dir, '/tmp');
});

test('migratePlaintext is a no-op when only encrypted keys are present', () => {
  const ss = fakeSafeStorage();
  const { settings, changed } = migratePlaintext(
    { hf_token_encrypted: 'abc==', data_dir: '/tmp' },
    ss,
  );
  assert.equal(changed, false);
  assert.equal(settings.hf_token_encrypted, 'abc==');
});

test('migratePlaintext leaves plaintext alone when encryption unavailable', () => {
  const ss = fakeSafeStorage({ available: false });
  const { settings, changed } = migratePlaintext({ hf_token: 'hf_abc' }, ss);
  assert.equal(changed, false);
  assert.equal(settings.hf_token, 'hf_abc');
  assert.equal(settings.hf_token_encrypted, undefined);
});

test('readSecret prefers encrypted sidecar but falls back to plaintext', () => {
  const ss = fakeSafeStorage();
  const encoded = encryptValue(ss, 'hf_real');
  assert.equal(readSecret({ hf_token_encrypted: encoded }, 'hf_token', ss), 'hf_real');
  assert.equal(readSecret({ hf_token: 'hf_legacy' }, 'hf_token', ss), 'hf_legacy');
  assert.equal(readSecret({}, 'hf_token', ss), '');
});
