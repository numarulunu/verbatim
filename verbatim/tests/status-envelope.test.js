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

test('buildStatusEnvelope passes stderr_tail through on lastExit', () => {
  const envelope = buildStatusEnvelope({
    status: 'crashed',
    lastReady: null,
    lastExit: {
      code: 1,
      signal: null,
      message: 'engine failed to start',
      stderr_tail: 'Traceback (most recent call last):\n  ImportError',
    },
  });
  assert.equal(envelope.lastExit.code, 1);
  assert.equal(envelope.lastExit.message, 'engine failed to start');
  assert.match(envelope.lastExit.stderr_tail, /ImportError/);
});
