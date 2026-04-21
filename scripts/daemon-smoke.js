/**
 * Smoke test for the Vocality daemon — Gate 7.
 *
 * Spawns engine_daemon.py against the real repo state and drives it
 * through the non-pipeline commands plus a dry_run process_batch. No
 * GPU work, but every command-event roundtrip through the real
 * handlers / engine_lock / reporter.
 *
 * Run:  node scripts/daemon-smoke.js
 */
'use strict';

const path = require('node:path');
const { spawn } = require('node:child_process');
const readline = require('node:readline');
const {
  encodeCommand,
  parseEvent,
} = require('../vocality-electron/ipc-protocol.js');

const REPO_ROOT = path.resolve(__dirname, '..');
const PY = path.join(REPO_ROOT, '.venv', 'Scripts', 'python.exe');
const DAEMON = path.join(REPO_ROOT, 'engine_daemon.py');

function startDaemon() {
  const child = spawn(PY, ['-u', DAEMON], {
    cwd: REPO_ROOT,
    stdio: ['pipe', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
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
  child.stderr.on('data', () => {});  // drain
  function next(timeoutMs = 30_000) {
    if (events.length) return Promise.resolve(events.shift());
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`next() timeout ${timeoutMs}ms`)), timeoutMs);
      waiters.push((e) => { clearTimeout(timer); resolve(e); });
    });
  }
  function send(cmd) { child.stdin.write(encodeCommand(cmd)); }
  function waitExit() {
    return new Promise((resolve) => child.on('exit', (code, signal) => resolve({ code, signal })));
  }
  return { child, next, send, waitExit };
}

function log(tag, payload) {
  const short = JSON.stringify(payload, (k, v) => {
    if (typeof v === 'string' && v.length > 180) return v.slice(0, 177) + '...';
    return v;
  });
  console.log(`[${tag}] ${short}`);
}

function fail(msg) {
  console.error(`FAIL: ${msg}`);
  process.exitCode = 1;
}

async function main() {
  const d = startDaemon();
  console.log(`spawned daemon pid=${d.child.pid}`);
  try {
    // 1) Ready on startup
    const ready = await d.next();
    if (ready.type !== 'ready') fail(`expected ready, got ${ready.type}`);
    log('ready', { engine_version: ready.engine_version });

    // 2) Ping → pong
    d.send({ cmd: 'ping', id: 'ping-1' });
    const pong = await d.next();
    if (pong.type !== 'pong' || pong.id !== 'ping-1') fail(`pong mismatch: ${JSON.stringify(pong)}`);
    log('pong', { id: pong.id });

    // 3) System detect
    d.send({ cmd: 'detect', id: 'det-1' });
    const sys = await d.next();
    if (sys.type !== 'system_info') fail(`detect returned ${sys.type}`);
    log('system_info', {
      cuda: sys.cuda,
      gpu: sys.gpu && sys.gpu.name,
      cpu_cores: sys.cpu && sys.cpu.logical_cores,
      hf_token: sys.hf_token,
      anthropic: sys.anthropic_api_key,
      disk_free_gb: sys.disk_free_gb,
    });

    // 4) List persons (real registry)
    d.send({ cmd: 'list_persons', id: 'lp-1' });
    const listed = await d.next();
    if (listed.type !== 'persons_listed') fail(`list_persons returned ${listed.type}`);
    log('persons_listed', {
      count: listed.persons.length,
      ids: listed.persons.map((p) => p.id),
    });

    // 5) Corpus summary (real corpus.json)
    d.send({ cmd: 'get_corpus_summary', id: 'cs-1' });
    const sum = await d.next();
    if (sum.type !== 'corpus_summary') fail(`get_corpus_summary returned ${sum.type}`);
    log('corpus_summary', {
      session_count: sum.session_count,
      persons: Object.keys(sum.persons || {}),
      total_hours: sum.total_hours,
    });

    // 6) Inspect the first person (if any)
    if (listed.persons.length > 0) {
      const first = listed.persons[0].id;
      d.send({ cmd: 'inspect_person', id: 'ip-1', person_id: first });
      const inspected = await d.next();
      if (inspected.type !== 'person_inspected') fail(`inspect returned ${inspected.type}`);
      log('inspect', {
        id: inspected.person.id,
        voice: inspected.person.voice_type,
        role: inspected.person.default_role,
        sessions_teacher: inspected.person.n_sessions_as_teacher,
        sessions_student: inspected.person.n_sessions_as_student,
        voiceprints: inspected.voiceprint_files,
      });
    }

    // 7) Scan Material/test_smoke
    d.send({
      cmd: 'scan_files', id: 'sf-1',
      input_dir: 'Material/test_smoke', probe_duration: false,
    });
    const scanned = await d.next();
    if (scanned.type !== 'files_scanned') fail(`scan returned ${scanned.type}`);
    log('files_scanned', {
      count: scanned.files.length,
      names: scanned.files.map((f) => f.name),
      needs_processing: scanned.files.map((f) => f.needs_processing),
    });

    // 8) Dry-run process_batch on the scanned files
    d.send({
      cmd: 'process_batch', id: 'pb-1',
      files: scanned.files.map((f) => f.path),
      options: { dry_run: true },
    });
    const batchEvents = [];
    while (true) {
      const e = await d.next();
      batchEvents.push(e);
      if (e.type === 'batch_complete') break;
    }
    const types = batchEvents.map((e) => e.type);
    log('batch', {
      n_events: batchEvents.length,
      types_first_last: [types[0], types[types.length - 1]],
      total_files: batchEvents[batchEvents.length - 1].total_files,
      successful: batchEvents[batchEvents.length - 1].successful,
    });

    // 9) cancel_batch (no batch running — must still ack)
    d.send({ cmd: 'cancel_batch', id: 'cb-1' });
    const cancelAck = await d.next();
    if (cancelAck.type !== 'cancel_accepted') fail(`cancel returned ${cancelAck.type}`);
    log('cancel_accepted', { id: cancelAck.id });

    // 10) Clean shutdown
    d.send({ cmd: 'shutdown' });
    const bye = await d.next();
    if (bye.type !== 'shutting_down') fail(`shutdown returned ${bye.type}`);
    const { code } = await d.waitExit();
    log('exit', { code });
    if (code !== 0) fail(`exit code ${code}`);

    if (!process.exitCode) {
      console.log('\nSMOKE PASSED — all 10 steps ok');
    }
  } catch (err) {
    console.error('SMOKE FAILED:', err);
    try { d.child.kill(); } catch (_) {}
    process.exit(1);
  }
}

main();
