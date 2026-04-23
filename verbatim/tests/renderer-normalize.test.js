'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { encodeRendererCommand } = require('../renderer/src/bridge/commands.ts');

const {
  DEFAULT_RENDERER_SETTINGS,
  encodeSettings,
  normalizeDaemonEvent,
  normalizeSettings,
  normalizeStatus,
} = require('../renderer/src/bridge/normalize.ts');

test('normalizeSettings maps preload keys into renderer state', () => {
  assert.deepEqual(
    normalizeSettings({
      huggingface_token: 'hf_123',
      anthropic_api_key: 'sk-ant-123',
      default_input: '/in',
      default_output: '/out',
      whisper_model: 'large',
      language: 'ro',
      polish: 'claude',
      data_dir: '~/.verbatim',
    }),
    {
      hf: 'hf_123',
      anth: 'sk-ant-123',
      defInput: '/in',
      defOutput: '/out',
      model: 'large',
      lang: 'ro',
      polish: 'claude',
      dataDir: '~/.verbatim',
    },
  );
});

test('encodeSettings maps renderer state back to daemon keys', () => {
  assert.deepEqual(
    encodeSettings({
      hf: 'hf_123',
      anth: 'sk-ant-123',
      defInput: '/in',
      defOutput: '/out',
      model: 'large',
      lang: 'ro',
      polish: 'claude',
      dataDir: '~/.verbatim',
    }),
    {
      hf_token: 'hf_123',
      anthropic_api_key: 'sk-ant-123',
      default_input: '/in',
      default_output: '/out',
      whisper_model: 'large',
      language: 'ro',
      polish: 'claude',
      data_dir: '~/.verbatim',
    },
  );
});

test('normalizeDaemonEvent keeps phase_progress fields stable', () => {
  assert.deepEqual(
    normalizeDaemonEvent({
      type: 'phase_progress',
      file_index: 4,
      phase: 'asr',
      phase_progress: 0.25,
    }),
    {
      type: 'phase_progress',
      file_index: 4,
      phase: 'asr',
      phaseIndex: 3,
      phase_progress: 0.25,
    },
  );
});

test('normalizeDaemonEvent prefers protocol order for vad and decode phases', () => {
  assert.deepEqual(
    normalizeDaemonEvent({
      type: 'phase_started',
      file_index: 1,
      phase: 'vad',
    }),
    {
      type: 'phase_started',
      file_index: 1,
      phase: 'vad',
      phaseIndex: 1,
    },
  );

  assert.deepEqual(
    normalizeDaemonEvent({
      type: 'phase_started',
      file_index: 1,
      phase: 'decode',
    }),
    {
      type: 'phase_started',
      file_index: 1,
      phase: 'decode',
      phaseIndex: 2,
    },
  );
});

test('normalizeDaemonEvent maps batch events needed by the current UI', () => {
  assert.deepEqual(
    normalizeDaemonEvent({
      type: 'phase_started',
      file_index: 2,
      phase: 'diarization',
    }),
    {
      type: 'phase_started',
      file_index: 2,
      phase: 'diarization',
      phaseIndex: 5,
    },
  );

  assert.deepEqual(
    normalizeDaemonEvent({
      type: 'file_started',
      index: 1,
      file: 'C:/clips/a.wav',
    }),
    {
      type: 'file_started',
      file_index: 1,
      path: 'C:/clips/a.wav',
    },
  );

  assert.deepEqual(
    normalizeDaemonEvent({
      type: 'batch_complete',
      total_files: 2,
      successful: 1,
      failed: 1,
      total_elapsed_s: 9.5,
      failures: [{ file: 'C:/clips/b.wav', reason: 'decoder failed' }],
    }),
    {
      type: 'batch_complete',
      total_files: 2,
      successful: 1,
      failed: 1,
      total_elapsed_s: 9.5,
      failures: [{ file: 'C:/clips/b.wav', reason: 'decoder failed' }],
    },
  );
});

test('normalizeDaemonEvent maps files_scanned into renderer file rows', () => {
  assert.deepEqual(
    normalizeDaemonEvent({
      type: 'files_scanned',
      files: [
        { path: 'C:/clips/a.wav', size_bytes: 4096, duration_s: 12.5, meta: { parse_ok: true } },
        { path: 'C:/clips/b.flac', size_bytes: 2048, meta: { parse_ok: false } },
      ],
    }),
    {
      type: 'files_scanned',
      files: [
        { path: 'C:/clips/a.wav', name: 'a.wav', duration: 12.5, size: 4096, alreadyProcessed: false, parseStatus: 'ok' },
        { path: 'C:/clips/b.flac', name: 'b.flac', duration: 0, size: 2048, alreadyProcessed: false, parseStatus: 'unreadable' },
      ],
    },
  );
});

test('normalizeDaemonEvent maps registry events into real person data', () => {
  assert.deepEqual(
    normalizeDaemonEvent({
      type: 'persons_listed',
      persons: [
        {
          id: 'spk_1',
          display_name: 'Ada',
          default_role: 'teacher',
          n_sessions_as_teacher: 5,
          n_sessions_as_student: 1,
          total_hours: 12.5,
          voice_type: 'Soprano',
          fach: 'Lyric',
          first_seen: '2024-01-01',
          last_updated: '2024-01-02',
          observed_regions: ['RO-Bucharest'],
          bootstrap_sessions_remaining: 2,
          voiceprint_files: ['C:/voiceprints/universal.npy'],
        },
      ],
    }),
    {
      type: 'persons_listed',
      persons: [
        {
          id: 'spk_1',
          displayName: 'Ada',
          role: 'teacher',
          sessionsTeacher: 5,
          sessionsStudent: 1,
          totalHours: 12.5,
          voiceType: 'Soprano',
          fach: 'Lyric',
          firstSeen: '2024-01-01',
          lastUpdated: '2024-01-02',
          observedRegions: ['RO-Bucharest'],
          bootstrapCounter: 2,
          voiceprintFiles: [{ name: 'universal.npy', bytes: 0 }],
        },
      ],
    },
  );

  assert.deepEqual(
    normalizeDaemonEvent({
      type: 'person_inspected',
      person: {
        id: 'spk_2',
        name: 'Bea',
        role: 'student',
        total_hours: 9.2,
      },
      voiceprint_files: [
        { name: 'speaking.npy', bytes: 98304 },
        'singing.npy',
      ],
    }),
    {
      type: 'person_inspected',
      person: {
        id: 'spk_2',
        displayName: 'Bea',
        role: 'student',
        sessionsTeacher: 0,
        sessionsStudent: 0,
        totalHours: 9.2,
        voiceType: undefined,
        fach: undefined,
        firstSeen: '',
        lastUpdated: '',
        observedRegions: [],
        bootstrapCounter: 0,
        voiceprintFiles: [
          { name: 'speaking.npy', bytes: 98304 },
          { name: 'singing.npy', bytes: 0 },
        ],
      },
    },
  );
});

test('normalizeDaemonEvent maps collision and corpus summary payloads', () => {
  assert.deepEqual(
    normalizeDaemonEvent({
      type: 'collision_detected',
      pair: ['spk_1', 'spk_2'],
      cosine: 0.9321,
    }),
    {
      type: 'collision_detected',
      pair: ['spk_1', 'spk_2'],
      cosine: 0.9321,
    },
  );

  assert.deepEqual(
    normalizeDaemonEvent({
      type: 'corpus_summary',
      session_count: 12,
      persons: { spk_1: 8, spk_2: 4 },
      total_hours: 41.5,
    }),
    {
      type: 'corpus_summary',
      session_count: 12,
      persons: { spk_1: 8, spk_2: 4 },
      total_hours: 41.5,
    },
  );
});

test('encodeRendererCommand rewrites scan_files inputDir without leaking camelCase keys', () => {
  assert.deepEqual(
    encodeRendererCommand({ type: 'scan_files', inputDir: 'C:/clips', probe_duration: false }),
    { cmd: 'scan_files', input_dir: 'C:/clips', probe_duration: false },
  );
});

test('encodeRendererCommand maps registry and redo command names directly', () => {
  assert.deepEqual(
    encodeRendererCommand({ type: 'rename_person', old_id: 'spk_1', new_id: 'spk_2' }),
    { cmd: 'rename_person', old_id: 'spk_1', new_id: 'spk_2' },
  );

  assert.deepEqual(
    encodeRendererCommand({ type: 'redo_batch', filter: { ignore_filter: true } }),
    { cmd: 'redo_batch', filter: { ignore_filter: true } },
  );
});

test('normalizeDaemonEvent preserves file context on error events', () => {
  assert.deepEqual(
    normalizeDaemonEvent({
      type: 'error',
      error_type: 'transcription_failed',
      message: 'decoder failed',
      file: 'C:/clips/a.wav',
    }),
    {
      type: 'error',
      title: 'decoder failed',
      body: 'C:/clips/a.wav',
      file: 'C:/clips/a.wav',
    },
  );
});

test('normalizeStatus accepts an envelope or string', () => {
  assert.equal(normalizeStatus({ status: 'busy', lastReady: null }), 'busy');
  assert.equal(normalizeStatus('ready'), 'ready');
  assert.equal(DEFAULT_RENDERER_SETTINGS.model, 'large-v3-turbo');
});
