'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { buildStartCommands } = require('../scripts/start.js');

test('buildStartCommands skips renderer build when VERBATIM_RENDERER_URL is set', () => {
  assert.deepEqual(buildStartCommands({ VERBATIM_RENDERER_URL: 'http://127.0.0.1:5173' }), [
    { command: 'electron', args: ['.'] },
  ]);
});

test('buildStartCommands keeps the existing build-first flow without a dev URL', () => {
  assert.deepEqual(buildStartCommands({}), [
    { command: 'npm', args: ['run', 'renderer:build'] },
    { command: 'electron', args: ['.'] },
  ]);
});
