'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { runWindowControlAction } = require('../window-controls.js');

function makeWindow(maximized = false) {
  const calls = [];
  let isMaximized = maximized;
  return {
    calls,
    isDestroyed() {
      return false;
    },
    isMaximized() {
      return isMaximized;
    },
    minimize() {
      calls.push('minimize');
    },
    maximize() {
      isMaximized = true;
      calls.push('maximize');
    },
    unmaximize() {
      isMaximized = false;
      calls.push('unmaximize');
    },
    close() {
      calls.push('close');
    },
  };
}

test('runWindowControlAction minimizes the window', () => {
  const win = makeWindow();
  assert.deepEqual(runWindowControlAction(win, 'minimize'), { maximized: false });
  assert.deepEqual(win.calls, ['minimize']);
});

test('runWindowControlAction toggles maximize on', () => {
  const win = makeWindow(false);
  assert.deepEqual(runWindowControlAction(win, 'toggle-maximize'), { maximized: true });
  assert.deepEqual(win.calls, ['maximize']);
});

test('runWindowControlAction toggles maximize off', () => {
  const win = makeWindow(true);
  assert.deepEqual(runWindowControlAction(win, 'toggle-maximize'), { maximized: false });
  assert.deepEqual(win.calls, ['unmaximize']);
});

test('runWindowControlAction closes the window', () => {
  const win = makeWindow();
  assert.deepEqual(runWindowControlAction(win, 'close'), { maximized: false });
  assert.deepEqual(win.calls, ['close']);
});

test('runWindowControlAction rejects unknown actions', () => {
  const win = makeWindow();
  assert.throws(() => runWindowControlAction(win, 'explode'), /Unknown window action/);
});
