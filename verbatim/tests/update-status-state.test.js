'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { createUpdateStatusState } = require('../update-status-state.js');

test('createUpdateStatusState remembers the latest updater payload for late subscribers', () => {
  const state = createUpdateStatusState();

  assert.equal(state.current(), null);

  state.set({ kind: 'checking' });
  assert.deepEqual(state.current(), { kind: 'checking' });

  state.set({ kind: 'downloaded', version: '0.1.2' });
  assert.deepEqual(state.current(), { kind: 'downloaded', version: '0.1.2' });
});
