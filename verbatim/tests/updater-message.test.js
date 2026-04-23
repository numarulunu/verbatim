'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { normalizeUpdaterMessage } = require('../updater-message.js');

test('normalizeUpdaterMessage hides raw GitHub provider failures', () => {
  const message = normalizeUpdaterMessage({
    message: '404 method: GET url: https://github.com/numarulunu/verbatim/releases.atom',
  });

  assert.equal(message, 'Auto-update is unavailable for this build.');
});

test('normalizeUpdaterMessage returns a plain network failure message', () => {
  const message = normalizeUpdaterMessage({
    message: 'net::ERR_INTERNET_DISCONNECTED',
  });

  assert.equal(message, 'Update check failed. Check your connection and try again later.');
});

test('normalizeUpdaterMessage falls back to a generic failure copy', () => {
  assert.equal(normalizeUpdaterMessage(new Error('something odd happened')), 'Update check failed.');
  assert.equal(normalizeUpdaterMessage(null), 'Update check failed.');
});
