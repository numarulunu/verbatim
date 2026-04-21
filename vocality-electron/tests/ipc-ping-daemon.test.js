/**
 * End-to-end IPC test: spawn the Python daemon, exchange `ping`/`pong`, then
 * send `shutdown` and assert clean exit. This is the Gate 4 acceptance gate.
 *
 * Skipped unless `.venv/Scripts/python.exe` exists at the repo root so the
 * JS-only unit tests still run on machines without the Python venv installed.
 */
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const readline = require('node:readline');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const PYTHON = path.join(REPO_ROOT, '.venv', 'Scripts', 'python.exe');
const DAEMON_SCRIPT = path.join(REPO_ROOT, 'engine_daemon.py');

const pythonAvailable =
  fs.existsSync(PYTHON) && fs.existsSync(DAEMON_SCRIPT);

const { encodeCommand, parseEvent } = require('../ipc-protocol.js');

/**
 * Spawn the daemon and return a small controller that exposes nextEvent()
 * (one JSON line at a time), send(command), and waitExit().
 */
function startDaemon() {
  const child = spawn(PYTHON, ['-u', DAEMON_SCRIPT], {
    cwd: REPO_ROOT,
    stdio: ['pipe', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
  });

  const events = [];
  const waiters = [];
  const rl = readline.createInterface({ input: child.stdout });
  rl.on('line', (line) => {
    const event = parseEvent(line);
    if (waiters.length > 0) {
      waiters.shift()(event);
    } else {
      events.push(event);
    }
  });

  // Drain stderr so the pipe buffer never fills (logs are diagnostic only).
  child.stderr.on('data', () => {});

  function nextEvent(timeoutMs = 15_000) {
    if (events.length > 0) {
      return Promise.resolve(events.shift());
    }
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        reject(new Error(`nextEvent timed out after ${timeoutMs}ms`));
      }, timeoutMs);
      waiters.push((event) => {
        clearTimeout(timer);
        resolve(event);
      });
    });
  }

  function send(command) {
    child.stdin.write(encodeCommand(command));
  }

  function waitExit(timeoutMs = 15_000) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        reject(new Error(`daemon did not exit within ${timeoutMs}ms`));
      }, timeoutMs);
      child.on('exit', (code, signal) => {
        clearTimeout(timer);
        resolve({ code, signal });
      });
    });
  }

  return { child, nextEvent, send, waitExit };
}

test('daemon emits ready on startup', { skip: !pythonAvailable }, async () => {
  const d = startDaemon();
  try {
    const ready = await d.nextEvent();
    assert.equal(ready.type, 'ready');
    assert.equal(typeof ready.engine_version, 'string');
    assert.ok(Array.isArray(ready.models_loaded));
  } finally {
    d.send({ cmd: 'shutdown' });
    await d.waitExit();
  }
});

test('ping → pong with matching id', { skip: !pythonAvailable }, async () => {
  const d = startDaemon();
  try {
    const ready = await d.nextEvent();
    assert.equal(ready.type, 'ready');

    d.send({ cmd: 'ping', id: 'ping-1' });
    const pong = await d.nextEvent();
    assert.equal(pong.type, 'pong');
    assert.equal(pong.id, 'ping-1');
    assert.equal(typeof pong.timestamp, 'string');
  } finally {
    d.send({ cmd: 'shutdown' });
    await d.waitExit();
  }
});

test('shutdown: emits shutting_down, exits 0', { skip: !pythonAvailable }, async () => {
  const d = startDaemon();
  const ready = await d.nextEvent();
  assert.equal(ready.type, 'ready');

  d.send({ cmd: 'shutdown' });
  const bye = await d.nextEvent();
  assert.equal(bye.type, 'shutting_down');

  const { code } = await d.waitExit();
  assert.equal(code, 0);
});

test('second daemon while first is alive: fails fast with engine_lock_held', { skip: !pythonAvailable }, async () => {
  const first = startDaemon();
  try {
    const ready = await first.nextEvent();
    assert.equal(ready.type, 'ready');

    // Start a second daemon while the first still holds the lock.
    const second = startDaemon();
    const evt = await second.nextEvent();
    assert.equal(evt.type, 'error');
    assert.equal(evt.error_type, 'engine_lock_held');
    assert.equal(evt.recoverable, false);
    const { code: secondCode } = await second.waitExit();
    assert.equal(secondCode, 3);
  } finally {
    first.send({ cmd: 'shutdown' });
    await first.waitExit();
  }
});

test('detect: emits system_info with cpu + cuda flag + disk', { skip: !pythonAvailable }, async () => {
  const d = startDaemon();
  try {
    const ready = await d.nextEvent();
    assert.equal(ready.type, 'ready');

    d.send({ cmd: 'detect', id: 'det-1' });
    const info = await d.nextEvent();
    assert.equal(info.type, 'system_info');
    assert.equal(info.id, 'det-1');
    assert.equal(typeof info.cuda, 'boolean');
    assert.ok(info.cpu && typeof info.cpu === 'object');
    assert.ok(Number.isFinite(info.disk_free_gb));
  } finally {
    d.send({ cmd: 'shutdown' });
    await d.waitExit();
  }
});

test('list_persons: returns an array (may be non-empty from prior sessions)', { skip: !pythonAvailable }, async () => {
  const d = startDaemon();
  try {
    const ready = await d.nextEvent();
    assert.equal(ready.type, 'ready');

    d.send({ cmd: 'list_persons', id: 'lp-1' });
    const listed = await d.nextEvent();
    assert.equal(listed.type, 'persons_listed');
    assert.equal(listed.id, 'lp-1');
    assert.ok(Array.isArray(listed.persons));
  } finally {
    d.send({ cmd: 'shutdown' });
    await d.waitExit();
  }
});

test('unknown command: emits error event, daemon stays up', { skip: !pythonAvailable }, async () => {
  const d = startDaemon();
  try {
    const ready = await d.nextEvent();
    assert.equal(ready.type, 'ready');

    // Bypass encodeCommand's client-side guard — we want to verify the
    // daemon's own unknown-command handling, so write raw.
    d.child.stdin.write(JSON.stringify({ cmd: 'nonsense', id: 'x' }) + '\n');
    const err = await d.nextEvent();
    assert.equal(err.type, 'error');
    assert.equal(err.error_type, 'unknown_command');
    assert.equal(err.recoverable, true);

    // Daemon should still be responsive.
    d.send({ cmd: 'ping', id: 'ping-after-err' });
    const pong = await d.nextEvent();
    assert.equal(pong.type, 'pong');
    assert.equal(pong.id, 'ping-after-err');
  } finally {
    d.send({ cmd: 'shutdown' });
    await d.waitExit();
  }
});
