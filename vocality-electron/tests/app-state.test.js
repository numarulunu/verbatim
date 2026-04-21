/**
 * Tests for the pure-state reducer. Node's native test runner (no Jest/Mocha
 * — matches converter's pattern per brief §2).
 */
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { initialState, reduceEvent } = require('../app-state.js');

test('initialState: batch view + down daemon + empty collections', () => {
  const s = initialState();
  assert.equal(s.view, 'batch');
  assert.equal(s.daemon.status, 'down');
  assert.equal(s.daemon.version, null);
  assert.deepEqual(s.daemon.modelsLoaded, []);
  assert.deepEqual(s.batch.files, []);
  assert.equal(s.batch.status, 'idle');
  assert.deepEqual(s.registry.persons, []);
  assert.deepEqual(s.registry.collisions, []);
});

test('reduceEvent(ready): daemon ready + version + models', () => {
  const s = reduceEvent(initialState(), {
    type: 'ready',
    engine_version: '1.0.0',
    models_loaded: ['faster-whisper:large-v3-turbo', 'pyannote/speaker-diarization-3.1'],
  });
  assert.equal(s.daemon.status, 'ready');
  assert.equal(s.daemon.version, '1.0.0');
  assert.deepEqual(s.daemon.modelsLoaded, [
    'faster-whisper:large-v3-turbo',
    'pyannote/speaker-diarization-3.1',
  ]);
});

test('reduceEvent(ready) with no models_loaded: empty list, not crash', () => {
  const s = reduceEvent(initialState(), {
    type: 'ready',
    engine_version: '1.0.0',
    // no models_loaded
  });
  assert.deepEqual(s.daemon.modelsLoaded, []);
});

test('reduceEvent(shutting_down): daemon back to down', () => {
  const ready = reduceEvent(initialState(), { type: 'ready', engine_version: '1.0.0' });
  const s = reduceEvent(ready, { type: 'shutting_down' });
  assert.equal(s.daemon.status, 'down');
});

test('reduceEvent is pure: input state is never mutated', () => {
  const s = initialState();
  const before = JSON.stringify(s);
  reduceEvent(s, { type: 'ready', engine_version: '1.0.0' });
  assert.equal(JSON.stringify(s), before, 'input state must not change');
});

test('reduceEvent(unknown type): returns same state reference', () => {
  const s = initialState();
  const next = reduceEvent(s, { type: 'something_weird' });
  assert.equal(next, s, 'unknown events must return the original state unchanged');
});
