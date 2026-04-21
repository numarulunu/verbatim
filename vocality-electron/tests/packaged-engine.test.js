/**
 * Guards that the engine/ drop location exists and is documented.
 *
 * This isn't a unit test — it's a structural assertion run under `npm test`
 * so a broken extraResources layout trips the test suite before packaging.
 * In Gate 3 we only assert the placeholder exists. Gate 5 extends this to
 * verify `vocality-engine.exe` runs and emits a `ready` event.
 */
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

test('engine directory exists (electron-builder extraResources target)', () => {
  const enginePath = path.join(__dirname, '..', 'engine');
  assert.ok(
    fs.existsSync(enginePath),
    `engine/ must exist (PyInstaller drops vocality-engine.exe here at build time). Missing: ${enginePath}`,
  );
});

test('engine/README.md documents the build-time drop', () => {
  const readme = path.join(__dirname, '..', 'engine', 'README.md');
  assert.ok(
    fs.existsSync(readme),
    'engine/README.md should explain how vocality-engine.exe lands in this directory.',
  );
});

test('build-config/electron-builder.yml exists', () => {
  const cfg = path.join(__dirname, '..', 'build-config', 'electron-builder.yml');
  assert.ok(
    fs.existsSync(cfg),
    'build-config/electron-builder.yml must be present for `npm run build`.',
  );
});
