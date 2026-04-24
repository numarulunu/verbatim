/**
 * settings-store — load/save verbatim-settings.json.
 *
 * Pure-Node (no Electron) so main.js can inject the absolute settings path
 * and `fs` module for tests. Provides corruption-rename on load: a malformed
 * JSON blob is renamed to verbatim-settings.broken.json and the loader
 * returns {}, matching the SessionModal "silent fallback" UX contract while
 * leaving a breadcrumb for bug reports.
 */
'use strict';

const realFs = require('node:fs');
const path = require('node:path');

/**
 * @param {string} filePath
 * @param {object} [deps]
 * @param {typeof realFs} [deps.fs]
 * @param {(...args: unknown[]) => void} [deps.warn]  — console.warn proxy for
 *   tests; defaults to console.warn. The real sink is wired by main.js via
 *   console redirection.
 * @returns {{settings: object, corrupt_path: string | null}}
 */
function loadSettings(filePath, deps = {}) {
  const fs = deps.fs || realFs;
  const warn = deps.warn || console.warn;
  if (!filePath) return { settings: {}, corrupt_path: null };

  let raw;
  try {
    raw = fs.readFileSync(filePath, 'utf8');
  } catch (_) {
    return { settings: {}, corrupt_path: null };
  }

  try {
    return { settings: JSON.parse(raw), corrupt_path: null };
  } catch (err) {
    const broken = path.join(path.dirname(filePath), 'verbatim-settings.broken.json');
    try { fs.renameSync(filePath, broken); } catch (_) { /* ignore */ }
    warn(
      `[settings] ${path.basename(filePath)} is malformed (${err.message}); renamed to ${path.basename(broken)}`,
    );
    return { settings: {}, corrupt_path: broken };
  }
}

/**
 * Keys the daemon actually reads from the settings file (main.js
 * daemonEnv() + renderer SettingsModal). Any key outside this allowlist is
 * dropped silently on save; the renderer can never stash attacker-controlled
 * state in userData.
 *
 * Size cap keeps a compromised renderer from DoS'ing the disk by looping
 * saveSettings with a multi-GB payload.
 */
const ALLOWED_KEYS = Object.freeze([
  // Secrets (Finding 4 stores these via safeStorage under _encrypted keys;
  // plaintext keys survive for backwards compat during the migration window).
  'hf_token',
  'anthropic_api_key',
  'hf_token_encrypted',
  'anthropic_api_key_encrypted',
  // Paths + renderer preferences — non-secret but persisted. Key names match
  // renderer/src/bridge/normalize.ts encodeSettings output.
  'data_dir',
  'default_input',
  'default_output',
  'whisper_model',
  'language',
  'polish',
]);
const MAX_STRING_BYTES = 8 * 1024;      // 8 KB per value; tokens are ~70 bytes
const MAX_PAYLOAD_BYTES = 64 * 1024;    // 64 KB whole file

/**
 * Reduce a raw renderer payload to the allowlist. Unknown keys are dropped.
 * Non-string values for known keys are coerced to empty-string to avoid type
 * confusion when daemonEnv() concatenates them into env vars later. Strings
 * longer than MAX_STRING_BYTES are truncated and a warning is emitted.
 */
function sanitizeSettings(input, deps = {}) {
  const warn = deps.warn || (() => {});
  const out = {};
  if (!input || typeof input !== 'object') return out;
  for (const key of ALLOWED_KEYS) {
    const value = input[key];
    if (value === undefined || value === null) continue;
    if (typeof value !== 'string') {
      warn(`[settings] dropped non-string value for ${key} (type=${typeof value})`);
      continue;
    }
    if (value.length > MAX_STRING_BYTES) {
      warn(`[settings] truncated oversized value for ${key} (${value.length} -> ${MAX_STRING_BYTES})`);
      out[key] = value.slice(0, MAX_STRING_BYTES);
    } else {
      out[key] = value;
    }
  }
  return out;
}

/**
 * Atomic write: tmp + rename. Runs sanitizeSettings first so the on-disk
 * file is always schema-clean. Throws if the serialized payload exceeds
 * MAX_PAYLOAD_BYTES (paranoia for a compromised renderer).
 */
function saveSettings(filePath, settings, deps = {}) {
  const fs = deps.fs || realFs;
  const warn = deps.warn || console.warn;
  const clean = sanitizeSettings(settings, { warn });
  const body = JSON.stringify(clean, null, 2);
  if (Buffer.byteLength(body, 'utf8') > MAX_PAYLOAD_BYTES) {
    throw new Error('Settings payload exceeds size limit');
  }
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  const tmp = filePath + '.tmp';
  fs.writeFileSync(tmp, body);
  fs.renameSync(tmp, filePath);
}

module.exports = {
  loadSettings,
  saveSettings,
  sanitizeSettings,
  ALLOWED_KEYS,
  MAX_STRING_BYTES,
  MAX_PAYLOAD_BYTES,
};
