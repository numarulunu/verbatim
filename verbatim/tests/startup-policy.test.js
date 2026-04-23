'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { deriveTopBarStatus, shouldStartBackgroundServices } = require('../startup-policy.js');

test('deriveTopBarStatus keeps fatal daemon states visible during an active batch', () => {
  assert.equal(deriveTopBarStatus('ready', true), 'busy');
  assert.equal(deriveTopBarStatus('crashed', true), 'crashed');
  assert.equal(deriveTopBarStatus('down', true), 'down');
  assert.equal(deriveTopBarStatus('shutting_down', true), 'shutting_down');
});

test('shouldStartBackgroundServices blocks engine startup after renderer load failure', () => {
  assert.equal(shouldStartBackgroundServices(true), true);
  assert.equal(shouldStartBackgroundServices(false), false);
});
