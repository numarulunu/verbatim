'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const { createLogSink } = require('../log-sink.js');

function tmpLogsDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'verbatim-log-sink-'));
}

test('createLogSink creates the logs dir and returns a writable sink', () => {
  const dir = path.join(tmpLogsDir(), 'nested');
  const sink = createLogSink(dir);
  try {
    assert.ok(fs.existsSync(dir), 'logs dir created');
    assert.equal(sink.dir, dir);
    sink.append('log', 'hello world');
    sink.close();
    const text = fs.readFileSync(sink.logPath, 'utf8');
    assert.match(text, /LOG hello world/);
    assert.match(text, /^\[\d{4}-\d{2}-\d{2}T/);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('createLogSink rotates the previous log to .1 on each call', () => {
  const dir = tmpLogsDir();
  try {
    const a = createLogSink(dir);
    a.append('log', 'session A');
    a.close();

    const b = createLogSink(dir);
    b.append('log', 'session B');
    b.close();

    const rotated = fs.readFileSync(`${a.logPath}.1`, 'utf8');
    const current = fs.readFileSync(b.logPath, 'utf8');
    assert.match(rotated, /session A/);
    assert.match(current, /session B/);
    assert.doesNotMatch(current, /session A/);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('install() redirects console.* and returns a restore fn', () => {
  const dir = tmpLogsDir();
  const sink = createLogSink(dir);
  const origLog = console.log;
  const origError = console.error;
  let nativeCallCount = 0;
  console.log = () => { nativeCallCount++; };
  console.error = () => { nativeCallCount++; };
  try {
    const restore = sink.install();
    console.log('from-log');
    console.error('from-err', new Error('boom'));
    restore();
    console.log('post-restore');
    sink.close();

    const text = fs.readFileSync(sink.logPath, 'utf8');
    assert.match(text, /LOG from-log/);
    assert.match(text, /ERROR from-err/);
    assert.match(text, /boom/);            // Error stack/message was formatted
    assert.doesNotMatch(text, /post-restore/);
    assert.ok(nativeCallCount >= 3, 'original console was still called during install');
  } finally {
    console.log = origLog;
    console.error = origError;
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('createLogSink throws when logsDir is missing', () => {
  assert.throws(() => createLogSink(''), /requires a logsDir/);
  assert.throws(() => createLogSink(null), /requires a logsDir/);
});
