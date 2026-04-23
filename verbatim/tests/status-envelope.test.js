'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { buildStatusEnvelope } = require('../status-envelope.js');

test('buildStatusEnvelope includes last exit details when the daemon crashed', () => {
  assert.deepEqual(
    buildStatusEnvelope({
      status: 'crashed',
      lastReady: { type: 'ready', engine_version: '1.0.0' },
      lastExit: { code: 139, signal: 'SIGSEGV' },
    }),
    {
      status: 'crashed',
      lastReady: { type: 'ready', engine_version: '1.0.0' },
      lastExit: { code: 139, signal: 'SIGSEGV' },
    },
  );
});

test('buildStatusEnvelope falls back to a down envelope without engine state', () => {
  assert.deepEqual(buildStatusEnvelope(null), {
    status: 'down',
    lastReady: null,
    lastExit: null,
  });
});
