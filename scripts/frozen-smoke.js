/**
 * Smoke test against the PyInstaller-frozen engine.
 * Mirrors scripts/daemon-smoke.js but spawns verbatim-engine.exe instead
 * of Python + engine_daemon.py. Catches hidden-import / packaging bugs
 * that only surface at runtime, before we wrap in the installer.
 */
'use strict';

const path = require('node:path');
const { spawn } = require('node:child_process');
const readline = require('node:readline');
const { encodeCommand, parseEvent } = require('../verbatim/ipc-protocol.js');

const REPO_ROOT = path.resolve(__dirname, '..');
const ENGINE_EXE = path.join(REPO_ROOT, 'verbatim', 'engine', 'verbatim-engine.exe');

function startDaemon() {
  const child = spawn(ENGINE_EXE, [], {
    cwd: path.dirname(ENGINE_EXE),
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  const events = [];
  const waiters = [];
  const rl = readline.createInterface({ input: child.stdout });
  rl.on('line', (line) => {
    let event;
    try { event = parseEvent(line); }
    catch (err) { event = { type: 'bad_line', error: err.message, raw: line }; }
    if (waiters.length) waiters.shift()(event);
    else events.push(event);
  });
  const stderrBuf = [];
  child.stderr.on('data', (d) => stderrBuf.push(d.toString()));
  function next(timeoutMs = 120_000) {
    if (events.length) return Promise.resolve(events.shift());
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        reject(new Error(`next() timeout ${timeoutMs}ms. Stderr tail:\n` + stderrBuf.slice(-30).join('')));
      }, timeoutMs);
      waiters.push((e) => { clearTimeout(timer); resolve(e); });
    });
  }
  function send(cmd) { child.stdin.write(encodeCommand(cmd)); }
  function waitExit() {
    return new Promise((resolve) => child.on('exit', (code, signal) => resolve({ code, signal })));
  }
  return { child, next, send, waitExit, stderrBuf };
}

async function main() {
  const d = startDaemon();
  console.log(`spawned frozen engine pid=${d.child.pid}`);
  try {
    const ready = await d.next();
    if (ready.type !== 'ready') {
      console.error('FAIL: expected ready, got', ready);
      console.error('stderr tail:', d.stderrBuf.slice(-30).join(''));
      process.exit(1);
    }
    console.log(`[ready] engine_version=${ready.engine_version}`);

    d.send({ cmd: 'ping', id: 'p-1' });
    const pong = await d.next();
    if (pong.type !== 'pong' || pong.id !== 'p-1') {
      console.error('FAIL: bad pong', pong);
      process.exit(1);
    }
    console.log('[pong] ok');

    d.send({ cmd: 'detect', id: 'd-1' });
    const info = await d.next(180_000);
    if (info.type !== 'system_info') {
      console.error('FAIL: detect returned', info);
      console.error('stderr tail:', d.stderrBuf.slice(-30).join(''));
      process.exit(1);
    }
    console.log(`[detect] cuda=${info.cuda} gpu=${info.gpu && info.gpu.name} hf=${info.hf_token}`);

    d.send({ cmd: 'shutdown' });
    const bye = await d.next();
    if (bye.type !== 'shutting_down') {
      console.error('FAIL: shutdown returned', bye);
      process.exit(1);
    }
    const { code } = await d.waitExit();
    if (code !== 0) {
      console.error('FAIL: exit code', code);
      process.exit(1);
    }
    console.log('\nFROZEN SMOKE PASSED');
  } catch (err) {
    console.error('SMOKE FAILED:', err && err.message);
    console.error('stderr tail:', d.stderrBuf.slice(-30).join(''));
    try { d.child.kill(); } catch (_) {}
    process.exit(1);
  }
}

main();
