/**
 * Tests for the pure-state reducer.
 * Every event type defined in ipc_protocol has at least one test here.
 */
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
  initialState,
  reduceEvent,
  setView,
  ERROR_LOG_CAP,
  WARNING_LOG_CAP,
} = require('../resources/app-state.js');

// ─── Initial shape ─────────────────────────────────────────────────────────

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
  assert.deepEqual(s.corpus.persons, {});
  assert.deepEqual(s.errors, []);
  assert.deepEqual(s.warnings, []);
});

// ─── Lifecycle ─────────────────────────────────────────────────────────────

test('reduceEvent(ready): daemon ready + version + models', () => {
  const s = reduceEvent(initialState(), {
    type: 'ready',
    engine_version: '1.0.0',
    models_loaded: ['faster-whisper:large-v3-turbo'],
  });
  assert.equal(s.daemon.status, 'ready');
  assert.equal(s.daemon.version, '1.0.0');
  assert.deepEqual(s.daemon.modelsLoaded, ['faster-whisper:large-v3-turbo']);
});

test('reduceEvent(ready) without models_loaded: empty list', () => {
  const s = reduceEvent(initialState(), { type: 'ready', engine_version: '1.0.0' });
  assert.deepEqual(s.daemon.modelsLoaded, []);
});

test('reduceEvent(shutting_down): daemon back to down', () => {
  const ready = reduceEvent(initialState(), { type: 'ready', engine_version: '1.0.0' });
  const s = reduceEvent(ready, { type: 'shutting_down' });
  assert.equal(s.daemon.status, 'down');
});

test('reduceEvent(pong): correlation-only, no state change', () => {
  const ready = reduceEvent(initialState(), { type: 'ready', engine_version: '1.0.0' });
  const s = reduceEvent(ready, { type: 'pong', id: 'p-1' });
  assert.equal(s, ready, 'pong must return the same state reference');
});

test('reduceEvent(cancel_accepted): transitions running → cancelling', () => {
  let s = reduceEvent(initialState(), { type: 'batch_started', file_count: 3 });
  s = reduceEvent(s, { type: 'cancel_accepted' });
  assert.equal(s.batch.status, 'cancelling');
});

test('reduceEvent(cancel_accepted): idle batch is unchanged', () => {
  const s = reduceEvent(initialState(), { type: 'cancel_accepted' });
  assert.equal(s.batch.status, 'idle');
});

// ─── Detect ────────────────────────────────────────────────────────────────

test('reduceEvent(system_info): captures cpu / gpu / cuda / tokens', () => {
  const s = reduceEvent(initialState(), {
    type: 'system_info',
    cpu: { logical_cores: 20 },
    gpu: { name: 'GTX 1080 Ti' },
    cuda: true,
    hf_token: true,
    anthropic_api_key: false,
    disk_free_gb: 128.5,
  });
  assert.equal(s.daemon.systemInfo.cuda, true);
  assert.equal(s.daemon.systemInfo.gpu.name, 'GTX 1080 Ti');
  assert.equal(s.daemon.systemInfo.disk_free_gb, 128.5);
});

// ─── Person management ─────────────────────────────────────────────────────

test('reduceEvent(persons_listed): replaces registry.persons', () => {
  const s = reduceEvent(initialState(), {
    type: 'persons_listed',
    persons: [
      { id: 'vasquez', display_name: 'vasquez' },
      { id: 'ionut', display_name: 'Ionuț' },
    ],
  });
  assert.equal(s.registry.persons.length, 2);
  assert.equal(s.registry.persons[0].id, 'vasquez');
});

test('reduceEvent(person_registered): appends (or replaces by id)', () => {
  let s = reduceEvent(initialState(), {
    type: 'persons_listed',
    persons: [{ id: 'vasquez', display_name: 'vasquez' }],
  });
  s = reduceEvent(s, {
    type: 'person_registered',
    person_id: 'ionut',
    record: { id: 'ionut', display_name: 'Ionuț' },
  });
  const ids = s.registry.persons.map((p) => p.id).sort();
  assert.deepEqual(ids, ['ionut', 'vasquez']);
});

test('reduceEvent(person_registered): re-registering the same id replaces', () => {
  let s = reduceEvent(initialState(), {
    type: 'person_registered', person_id: 'x',
    record: { id: 'x', display_name: 'X', voice_type: null },
  });
  s = reduceEvent(s, {
    type: 'person_registered', person_id: 'x',
    record: { id: 'x', display_name: 'X', voice_type: 'tenor' },
  });
  assert.equal(s.registry.persons.length, 1);
  assert.equal(s.registry.persons[0].voice_type, 'tenor');
});

test('reduceEvent(person_inspected): stashes in activeInspect', () => {
  const s = reduceEvent(initialState(), {
    type: 'person_inspected',
    person: { id: 'vasquez' },
    voiceprint_files: ['universal.npy'],
  });
  assert.equal(s.registry.activeInspect.person.id, 'vasquez');
  assert.deepEqual(s.registry.activeInspect.voiceprint_files, ['universal.npy']);
});

test('reduceEvent(person_inspected): mirrors fields into the persons list row', () => {
  let s = reduceEvent(initialState(), {
    type: 'persons_listed',
    persons: [{ id: 'vasquez', display_name: 'Vasquez', voice_type: null }],
  });
  s = reduceEvent(s, {
    type: 'person_inspected',
    person: { id: 'vasquez', display_name: 'Vasquez', voice_type: 'tenor' },
    voiceprint_files: [],
  });
  assert.equal(s.registry.persons[0].voice_type, 'tenor',
    'list row must reflect the inspected record so edits show up without re-list');
});

test('reduceEvent(person_renamed): rewrites id in registry.persons', () => {
  let s = reduceEvent(initialState(), {
    type: 'persons_listed',
    persons: [{ id: 'ionut', display_name: 'Ionuț' }],
  });
  s = reduceEvent(s, { type: 'person_renamed', old_id: 'ionut', new_id: 'ionut_v2' });
  assert.equal(s.registry.persons[0].id, 'ionut_v2');
  assert.equal(s.registry.lastRename.new_id, 'ionut_v2');
});

test('reduceEvent(person_merged): drops source, records lastMerge', () => {
  let s = reduceEvent(initialState(), {
    type: 'persons_listed',
    persons: [{ id: 'a' }, { id: 'b' }],
  });
  s = reduceEvent(s, { type: 'person_merged', source_id: 'a', target_id: 'b' });
  assert.deepEqual(s.registry.persons.map((p) => p.id), ['b']);
  assert.equal(s.registry.lastMerge.source_id, 'a');
});

test('reduceEvent(collision_detected): appends a pair', () => {
  const s = reduceEvent(initialState(), {
    type: 'collision_detected', pair: ['a', 'b'], cosine: 0.92,
  });
  assert.equal(s.registry.collisions.length, 1);
  assert.deepEqual(s.registry.collisions[0].pair, ['a', 'b']);
  assert.equal(s.registry.collisions[0].cosine, 0.92);
});

// ─── Scan ──────────────────────────────────────────────────────────────────

test('reduceEvent(files_scanned): stashes scan result', () => {
  const s = reduceEvent(initialState(), {
    type: 'files_scanned',
    files: [{ path: 'a.mp4', size_bytes: 1000, meta: { parse_ok: true } }],
  });
  assert.equal(s.batch.scan.files.length, 1);
});

// ─── Batch lifecycle ───────────────────────────────────────────────────────

test('reduceEvent(batch_started): resets files + status=running', () => {
  let s = initialState();
  // Pre-populate to verify reset.
  s = reduceEvent(s, { type: 'batch_started', file_count: 1 });
  s = reduceEvent(s, { type: 'file_started', file: 'a.mp4', index: 0, total: 1 });

  const fresh = reduceEvent(s, { type: 'batch_started', file_count: 3, options: {} });
  assert.equal(fresh.batch.status, 'running');
  assert.deepEqual(fresh.batch.files, []);
  assert.equal(fresh.batch.successful, 0);
  assert.equal(fresh.batch.failed, 0);
});

test('reduceEvent(file_started): extends files + sets running', () => {
  let s = reduceEvent(initialState(), { type: 'batch_started', file_count: 2 });
  s = reduceEvent(s, { type: 'file_started', file: 'a.mp4', index: 0, total: 2 });
  assert.equal(s.batch.files.length, 1);
  assert.equal(s.batch.files[0].path, 'a.mp4');
  assert.equal(s.batch.files[0].status, 'running');
  assert.equal(s.batch.currentFileIndex, 0);
});

test('reduceEvent(phase_started + phase_complete): tracks phase + completed_phases', () => {
  let s = reduceEvent(initialState(), { type: 'batch_started', file_count: 1 });
  s = reduceEvent(s, { type: 'file_started', file: 'a.mp4', index: 0, total: 1 });
  s = reduceEvent(s, { type: 'phase_started', file_index: 0, phase: 'decode', phase_index: 3 });
  assert.equal(s.batch.files[0].phase, 'decode');
  assert.equal(s.batch.files[0].phase_index, 3);
  assert.equal(s.batch.files[0].phase_progress, 0);

  s = reduceEvent(s, { type: 'phase_complete', file_index: 0, phase: 'decode', elapsed_s: 0.1 });
  assert.equal(s.batch.files[0].phase_progress, 1);
  assert.deepEqual(s.batch.files[0].completed_phases, ['decode']);

  // Duplicate phase_complete must not double-append.
  s = reduceEvent(s, { type: 'phase_complete', file_index: 0, phase: 'decode', elapsed_s: 0.2 });
  assert.deepEqual(s.batch.files[0].completed_phases, ['decode']);
});

test('reduceEvent(phase_progress): clamps to [0, 1]', () => {
  let s = reduceEvent(initialState(), { type: 'batch_started', file_count: 1 });
  s = reduceEvent(s, { type: 'file_started', file: 'a.mp4', index: 0, total: 1 });
  s = reduceEvent(s, { type: 'phase_progress', file_index: 0, phase: 'asr', phase_progress: 1.7 });
  assert.equal(s.batch.files[0].phase_progress, 1);
  s = reduceEvent(s, { type: 'phase_progress', file_index: 0, phase: 'asr', phase_progress: -0.5 });
  assert.equal(s.batch.files[0].phase_progress, 0);
});

test('reduceEvent(file_complete): stats.ok=true → complete', () => {
  let s = reduceEvent(initialState(), { type: 'batch_started', file_count: 1 });
  s = reduceEvent(s, { type: 'file_started', file: 'a.mp4', index: 0, total: 1 });
  s = reduceEvent(s, {
    type: 'file_complete', file_index: 0,
    output_path: '03_polished/a.json',
    stats: { ok: true },
  });
  assert.equal(s.batch.files[0].status, 'complete');
  assert.equal(s.batch.files[0].output_path, '03_polished/a.json');
});

test('reduceEvent(file_complete): stats.ok=false → failed', () => {
  let s = reduceEvent(initialState(), { type: 'batch_started', file_count: 1 });
  s = reduceEvent(s, { type: 'file_started', file: 'a.mp4', index: 0, total: 1 });
  s = reduceEvent(s, {
    type: 'file_complete', file_index: 0,
    output_path: '', stats: { ok: false },
  });
  assert.equal(s.batch.files[0].status, 'failed');
});

test('reduceEvent(batch_complete): records counts + marks complete', () => {
  let s = reduceEvent(initialState(), { type: 'batch_started', file_count: 2 });
  s = reduceEvent(s, {
    type: 'batch_complete',
    total_files: 2, successful: 2, failed: 0, total_elapsed_s: 15.0,
  });
  assert.equal(s.batch.status, 'complete');
  assert.equal(s.batch.successful, 2);
  assert.equal(s.batch.elapsed_s, 15.0);
});

test('reduceEvent(batch_complete) after cancel: status=cancelled, not complete', () => {
  let s = reduceEvent(initialState(), { type: 'batch_started', file_count: 3 });
  s = reduceEvent(s, { type: 'cancel_accepted' });
  s = reduceEvent(s, {
    type: 'batch_complete', total_files: 3, successful: 1, failed: 2,
    total_elapsed_s: 5.0,
  });
  assert.equal(s.batch.status, 'cancelled');
});

test('reduceEvent(batch_complete): all-failed → status=failed', () => {
  let s = reduceEvent(initialState(), { type: 'batch_started', file_count: 2 });
  s = reduceEvent(s, {
    type: 'batch_complete', total_files: 2, successful: 0, failed: 2,
    total_elapsed_s: 0.2,
  });
  assert.equal(s.batch.status, 'failed');
});

// ─── Corpus ────────────────────────────────────────────────────────────────

test('reduceEvent(corpus_summary): replaces the corpus slice', () => {
  const s = reduceEvent(initialState(), {
    type: 'corpus_summary',
    session_count: 42,
    persons: { vasquez: { total_hours: 10.5 } },
    total_hours: 12.3,
  });
  assert.equal(s.corpus.session_count, 42);
  assert.equal(s.corpus.persons.vasquez.total_hours, 10.5);
  assert.equal(s.corpus.total_hours, 12.3);
});

// ─── Diagnostics ───────────────────────────────────────────────────────────

test('reduceEvent(error): appends to errors', () => {
  const s = reduceEvent(initialState(), {
    type: 'error', error_type: 'daemon_crash', message: 'boom', recoverable: false,
  });
  assert.equal(s.errors.length, 1);
  assert.equal(s.errors[0].error_type, 'daemon_crash');
});

test('reduceEvent(error): caps at ERROR_LOG_CAP', () => {
  let s = initialState();
  for (let i = 0; i < ERROR_LOG_CAP + 10; i++) {
    s = reduceEvent(s, { type: 'error', error_type: 'x', message: String(i) });
  }
  assert.equal(s.errors.length, ERROR_LOG_CAP);
  // Last entry is the most recent — `${ERROR_LOG_CAP + 10 - 1}`.
  assert.equal(s.errors[s.errors.length - 1].message, String(ERROR_LOG_CAP + 10 - 1));
});

test('reduceEvent(warning): appends, capped at WARNING_LOG_CAP', () => {
  let s = initialState();
  for (let i = 0; i < WARNING_LOG_CAP + 5; i++) {
    s = reduceEvent(s, { type: 'warning', warning_type: 'drift_detected', message: String(i) });
  }
  assert.equal(s.warnings.length, WARNING_LOG_CAP);
});

// ─── Purity ────────────────────────────────────────────────────────────────

test('reduceEvent is pure: input state never mutated', () => {
  const s = initialState();
  const before = JSON.stringify(s);
  reduceEvent(s, { type: 'ready', engine_version: '1.0.0' });
  reduceEvent(s, { type: 'batch_started', file_count: 1 });
  reduceEvent(s, { type: 'error', error_type: 'daemon_crash', message: 'x' });
  assert.equal(JSON.stringify(s), before);
});

test('reduceEvent(unknown type): returns same state reference', () => {
  const s = initialState();
  const next = reduceEvent(s, { type: 'made_up' });
  assert.equal(next, s);
});

test('reduceEvent(malformed event with no type): returns same state', () => {
  const s = initialState();
  assert.equal(reduceEvent(s, {}), s);
  assert.equal(reduceEvent(s, null), s);
  assert.equal(reduceEvent(s, undefined), s);
});

// ─── End-to-end sequence ───────────────────────────────────────────────────

// ─── View switch ──────────────────────────────────────────────────────────

test('setView(registry): flips state.view', () => {
  const s = setView(initialState(), 'registry');
  assert.equal(s.view, 'registry');
});

test('setView(same view): returns same state reference', () => {
  const s = initialState();
  assert.equal(setView(s, 'batch'), s);
});

test('setView(unknown): returns same state', () => {
  const s = initialState();
  assert.equal(setView(s, 'nonsense'), s);
});

test('end-to-end: ready → batch_started → phases → batch_complete', () => {
  let s = initialState();
  s = reduceEvent(s, { type: 'ready', engine_version: '1.0.0' });
  s = reduceEvent(s, { type: 'batch_started', file_count: 1, options: {} });
  s = reduceEvent(s, { type: 'file_started', file: 'a.mp4', index: 0, total: 1 });
  const phases = ['decode', 'vad', 'asr', 'alignment', 'diarization', 'identification', 'verification', 'polish', 'corpus_update'];
  phases.forEach((p, i) => {
    s = reduceEvent(s, { type: 'phase_started', file_index: 0, phase: p, phase_index: i + 2 });
    s = reduceEvent(s, { type: 'phase_complete', file_index: 0, phase: p, elapsed_s: 0.1 });
  });
  s = reduceEvent(s, {
    type: 'file_complete', file_index: 0,
    output_path: '03_polished/a.json',
    stats: { ok: true },
  });
  s = reduceEvent(s, {
    type: 'batch_complete', total_files: 1, successful: 1, failed: 0,
    total_elapsed_s: 0.9,
  });
  assert.equal(s.batch.status, 'complete');
  assert.deepEqual(s.batch.files[0].completed_phases, phases);
  assert.equal(s.batch.files[0].status, 'complete');
});
