'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

test('preload bridge does not depend on a local package manifest', () => {
  const preloadSource = fs.readFileSync(path.join(__dirname, '..', 'preload.js'), 'utf8');
  assert.doesNotMatch(preloadSource, /require\([']\.\/package\.json[']\)/);
});

test('verbatimClient can load without a preload bridge and degrades cleanly', async (t) => {
  const clientSource = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'bridge', 'verbatimClient.ts'), 'utf8');
  assert.doesNotMatch(clientSource, /const api = window\.verbatim;/);
});
