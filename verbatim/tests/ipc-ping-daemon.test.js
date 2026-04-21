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

test('detect: emits system_info with cpu + cuda flag + disk', { skip: !pythonAvailable, timeout: 90_000 }, async () => {
  const d = startDaemon();
  try {
    const ready = await d.nextEvent();
    assert.equal(ready.type, 'ready');

    d.send({ cmd: 'detect', id: 'det-1' });
    // First detect on a fresh daemon triggers a cold `import torch` — ~20-30s
    // on Windows machines with aggressive AV. This is first-detect latency,
    // not a test flake; the generous timeout reflects packaged-app reality.
    const info = await d.nextEvent(90_000);
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

test('process_batch: empty file list emits batch_started + batch_complete with counts=0', { skip: !pythonAvailable }, async () => {
  const d = startDaemon();
  try {
    const ready = await d.nextEvent();
    assert.equal(ready.type, 'ready');

    d.send({ cmd: 'process_batch', id: 'pb-1', files: [], options: { dry_run: true } });

    const started = await d.nextEvent();
    assert.equal(started.type, 'batch_started');
    assert.equal(started.id, 'pb-1');
    assert.equal(started.file_count, 0);

    const complete = await d.nextEvent();
    assert.equal(complete.type, 'batch_complete');
    assert.equal(complete.id, 'pb-1');
    assert.equal(complete.total_files, 0);
    assert.equal(complete.successful, 0);
    assert.equal(complete.failed, 0);
  } finally {
    d.send({ cmd: 'shutdown' });
    await d.waitExit();
  }
});

test('process_batch (dry_run): emits file_started + file_complete per path, then batch_complete', { skip: !pythonAvailable }, async () => {
  const d = startDaemon();
  try {
    const ready = await d.nextEvent();
    assert.equal(ready.type, 'ready');

    d.send({
      cmd: 'process_batch', id: 'pb-2',
      files: ['fake/a.mp4', 'fake/b.mp4'],
      options: { dry_run: true },
    });

    const started = await d.nextEvent();
    assert.equal(started.type, 'batch_started');
    assert.equal(started.file_count, 2);

    const f0s = await d.nextEvent();
    assert.equal(f0s.type, 'file_started');
    assert.equal(f0s.index, 0);

    const f0c = await d.nextEvent();
    assert.equal(f0c.type, 'file_complete');
    assert.equal(f0c.stats.ok, true);
    assert.equal(f0c.stats.dry_run, true);

    const f1s = await d.nextEvent();
    assert.equal(f1s.type, 'file_started');
    assert.equal(f1s.index, 1);

    const f1c = await d.nextEvent();
    assert.equal(f1c.type, 'file_complete');

    const complete = await d.nextEvent();
    assert.equal(complete.type, 'batch_complete');
    assert.equal(complete.total_files, 2);
    assert.equal(complete.successful, 2);
    assert.equal(complete.failed, 0);
  } finally {
    d.send({ cmd: 'shutdown' });
    await d.waitExit();
  }
});

test('process_batch: daemon stays responsive to list_persons while batch is running', { skip: !pythonAvailable }, async () => {
  const d = startDaemon();
  try {
    const ready = await d.nextEvent();
    assert.equal(ready.type, 'ready');

    // Kick off a large-ish dry_run batch so it spans several event-loop turns.
    const manyFiles = Array.from({ length: 20 }, (_, i) => `fake/f${i}.mp4`);
    d.send({ cmd: 'process_batch', id: 'pb-3', files: manyFiles, options: { dry_run: true } });

    const started = await d.nextEvent();
    assert.equal(started.type, 'batch_started');

    // Intersperse a sync command — must receive its response even mid-batch.
    d.send({ cmd: 'list_persons', id: 'lp-mid' });

    // Drain events until we see the interleaved list_persons response.
    let sawListPersons = false;
    let sawBatchComplete = false;
    for (let i = 0; i < 200 && !(sawListPersons && sawBatchComplete); i++) {
      const evt = await d.nextEvent();
      if (evt.type === 'persons_listed' && evt.id === 'lp-mid') sawListPersons = true;
      if (evt.type === 'batch_complete' && evt.id === 'pb-3') sawBatchComplete = true;
    }
    assert.ok(sawListPersons, 'list_persons response must arrive during running batch');
    assert.ok(sawBatchComplete, 'batch_complete must still arrive');
  } finally {
    d.send({ cmd: 'shutdown' });
    await d.waitExit();
  }
});

test('process_batch: second process_batch while one is running is rejected', { skip: !pythonAvailable }, async () => {
  const d = startDaemon();
  try {
    const ready = await d.nextEvent();
    assert.equal(ready.type, 'ready');

    const manyFiles = Array.from({ length: 30 }, (_, i) => `fake/f${i}.mp4`);
    d.send({ cmd: 'process_batch', id: 'pb-4a', files: manyFiles, options: { dry_run: true } });
    const started = await d.nextEvent();
    assert.equal(started.type, 'batch_started');

    // Second request — must be rejected, the first keeps going.
    d.send({ cmd: 'process_batch', id: 'pb-4b', files: ['fake/x.mp4'], options: { dry_run: true } });

    let sawReject = false;
    let sawOriginalComplete = false;
    for (let i = 0; i < 200 && !(sawReject && sawOriginalComplete); i++) {
      const evt = await d.nextEvent();
      if (evt.type === 'error' && evt.id === 'pb-4b' && evt.error_type === 'invalid_command_payload') {
        sawReject = true;
      }
      if (evt.type === 'batch_complete' && evt.id === 'pb-4a') {
        sawOriginalComplete = true;
      }
    }
    assert.ok(sawReject, 'second process_batch must be rejected');
    assert.ok(sawOriginalComplete, 'original batch must still complete');
  } finally {
    d.send({ cmd: 'shutdown' });
    await d.waitExit();
  }
});

test('cancel_batch interrupts a running batch', { skip: !pythonAvailable }, async () => {
  const d = startDaemon();
  try {
    const ready = await d.nextEvent();
    assert.equal(ready.type, 'ready');

    const manyFiles = Array.from({ length: 500 }, (_, i) => `fake/f${i}.mp4`);
    d.send({ cmd: 'process_batch', id: 'pb-c', files: manyFiles, options: { dry_run: true } });
    const started = await d.nextEvent();
    assert.equal(started.type, 'batch_started');

    // Cancel immediately.
    d.send({ cmd: 'cancel_batch', id: 'can-1' });

    let sawAck = false;
    let completeEvt = null;
    for (let i = 0; i < 2000 && !(sawAck && completeEvt); i++) {
      const evt = await d.nextEvent();
      if (evt.type === 'cancel_accepted' && evt.id === 'can-1') sawAck = true;
      if (evt.type === 'batch_complete' && evt.id === 'pb-c') completeEvt = evt;
    }
    assert.ok(sawAck, 'cancel_accepted must arrive');
    assert.ok(completeEvt, 'batch_complete must arrive after cancel');
    // Cancellation should short-circuit before we process all 500 files.
    assert.ok(
      completeEvt.successful + completeEvt.failed < manyFiles.length,
      'cancellation should stop before completing all files',
    );
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
