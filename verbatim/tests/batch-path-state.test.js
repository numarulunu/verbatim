'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { createBatchPathState } = require('../renderer/src/bridge/batchPathState.ts');

test('pending batch files do not replace the active mapping until the batch starts', () => {
  const state = createBatchPathState();

  state.queue(['C:/clips/a.wav', 'C:/clips/b.wav']);
  state.confirm();
  assert.equal(state.resolve(0), 'C:/clips/a.wav');

  state.queue(['C:/clips/other.wav']);
  assert.equal(state.resolve(0), 'C:/clips/a.wav');

  state.cancelPending();
  assert.equal(state.resolve(1), 'C:/clips/b.wav');
});

test('confirm promotes queued files and clear removes active mappings', () => {
  const state = createBatchPathState();

  state.queue(['C:/clips/fresh.wav']);
  state.confirm();
  assert.equal(state.resolve(0), 'C:/clips/fresh.wav');

  state.clear();
  assert.equal(state.resolve(0), '');
});
