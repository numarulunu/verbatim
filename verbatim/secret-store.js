/**
 * secret-store — encrypt/decrypt long-lived secrets via Electron safeStorage.
 *
 * safeStorage uses DPAPI on Windows, Keychain on macOS, and libsecret on
 * Linux. It is the Electron-recommended way to persist tokens outside of
 * plain text. We keep the encrypted blob base64-serialized inside the same
 * settings file under `{key}_encrypted` so the layout stays human-readable.
 *
 * Injection points:
 *   - `safeStorage` is injected so main.js can pass the real Electron module
 *     and tests can pass a fake with a predictable transform.
 *   - Each call checks `isEncryptionAvailable()`; if unavailable (Linux
 *     without a keyring, or a boot where DPAPI is temporarily unreachable)
 *     we fall back to plaintext storage and mark the value as such so the
 *     next successful boot can upgrade it.
 */
'use strict';

function encryptValue(safeStorage, plaintext) {
  if (typeof plaintext !== 'string' || plaintext === '') return null;
  if (!safeStorage || !safeStorage.isEncryptionAvailable || !safeStorage.isEncryptionAvailable()) {
    return null;
  }
  const buf = safeStorage.encryptString(plaintext);
  return Buffer.isBuffer(buf) ? buf.toString('base64') : null;
}

function decryptValue(safeStorage, encoded) {
  if (typeof encoded !== 'string' || encoded === '') return '';
  if (!safeStorage || !safeStorage.isEncryptionAvailable || !safeStorage.isEncryptionAvailable()) {
    return '';
  }
  try {
    const buf = Buffer.from(encoded, 'base64');
    return safeStorage.decryptString(buf);
  } catch (_) {
    return '';
  }
}

/**
 * Upgrade a raw settings blob by replacing plaintext secret fields with
 * their encrypted counterparts. Returns { settings, changed }: `changed`
 * is true when the caller should persist the upgraded blob.
 *
 * Secret fields (plaintext -> encrypted):
 *   hf_token           -> hf_token_encrypted
 *   anthropic_api_key  -> anthropic_api_key_encrypted
 */
const SECRET_FIELDS = [
  { plain: 'hf_token',           encrypted: 'hf_token_encrypted' },
  { plain: 'anthropic_api_key',  encrypted: 'anthropic_api_key_encrypted' },
];

function migratePlaintext(settings, safeStorage) {
  if (!settings || typeof settings !== 'object') {
    return { settings: {}, changed: false };
  }
  const next = { ...settings };
  let changed = false;
  for (const { plain, encrypted } of SECRET_FIELDS) {
    const plaintext = next[plain];
    if (typeof plaintext === 'string' && plaintext.length > 0) {
      const encoded = encryptValue(safeStorage, plaintext);
      if (encoded) {
        next[encrypted] = encoded;
        delete next[plain];
        changed = true;
      }
      // If encryption unavailable, leave plaintext for a later boot.
    }
  }
  return { settings: next, changed };
}

/**
 * Return the decrypted secret for a given plain-key name. Reads the
 * encrypted sidecar if present, falling back to the plaintext field so a
 * mid-migration boot still works.
 */
function readSecret(settings, plainKey, safeStorage) {
  if (!settings || typeof settings !== 'object') return '';
  const encryptedKey = `${plainKey}_encrypted`;
  if (settings[encryptedKey]) {
    const out = decryptValue(safeStorage, settings[encryptedKey]);
    if (out) return out;
  }
  return typeof settings[plainKey] === 'string' ? settings[plainKey] : '';
}

module.exports = {
  encryptValue,
  decryptValue,
  migratePlaintext,
  readSecret,
  SECRET_FIELDS,
};
