/**
 * Unit tests for the protocol loader — pure JS, no daemon spawn.
 */
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
  PROTOCOL_VERSION,
  PHASE_NAMES,
  TOTAL_PHASES,
  ERROR_TYPES,
  WARNING_TYPES,
  COMMAND_NAMES,
  EVENT_TYPES,
  encodeCommand,
  parseEvent,
  isValidCommandName,
  isValidEventType,
} = require('../ipc-protocol.js');

test('protocol metadata: version 1.0, 10 phases, known commands + events', () => {
  assert.equal(PROTOCOL_VERSION, '1.0');
  assert.equal(TOTAL_PHASES, 10);
  assert.equal(PHASE_NAMES.length, 10);
  assert.ok(PHASE_NAMES.includes('asr'));
  assert.ok(PHASE_NAMES.includes('corpus_update'));
  assert.ok(ERROR_TYPES.includes('daemon_crash'));
  assert.ok(WARNING_TYPES.includes('drift_detected'));
  assert.ok(COMMAND_NAMES.includes('ping'));
  assert.ok(COMMAND_NAMES.includes('shutdown'));
  assert.ok(COMMAND_NAMES.includes('process_batch'));
  assert.ok(EVENT_TYPES.includes('ready'));
  assert.ok(EVENT_TYPES.includes('pong'));
});

test('metadata arrays are frozen (defensive — callers must not mutate)', () => {
  assert.throws(() => { PHASE_NAMES.push('x'); });
  assert.throws(() => { ERROR_TYPES.push('x'); });
  assert.throws(() => { COMMAND_NAMES.push('x'); });
});

test('encodeCommand: emits single JSON line terminated by \\n', () => {
  const line = encodeCommand({ cmd: 'ping', id: 'id-1' });
  assert.ok(line.endsWith('\n'));
  assert.equal(line.indexOf('\n'), line.length - 1, 'no embedded newlines');
  const parsed = JSON.parse(line);
  assert.equal(parsed.cmd, 'ping');
  assert.equal(parsed.id, 'id-1');
});

test('encodeCommand: rejects unknown cmd + missing cmd + non-objects', () => {
  assert.throws(() => encodeCommand({ cmd: 'nope' }), /unknown cmd/);
  assert.throws(() => encodeCommand({ id: 'x' }), /`cmd` is required/);
  assert.throws(() => encodeCommand(null), /must be an object/);
  assert.throws(() => encodeCommand('ping'), /must be an object/);
});

test('parseEvent: accepts a well-formed event, rejects unknowns', () => {
  const evt = parseEvent('{"type":"ready","engine_version":"1.0.0","models_loaded":[]}');
  assert.equal(evt.type, 'ready');
  assert.equal(evt.engine_version, '1.0.0');

  assert.throws(() => parseEvent(''), /empty line/);
  assert.throws(() => parseEvent('not json'), SyntaxError);
  assert.throws(() => parseEvent('[]'), /not a JSON object/);
  assert.throws(() => parseEvent('{"foo":1}'), /missing `type`/);
  assert.throws(() => parseEvent('{"type":"made_up"}'), /unknown event type/);
});

test('validators: isValidCommandName + isValidEventType', () => {
  assert.equal(isValidCommandName('ping'), true);
  assert.equal(isValidCommandName('nope'), false);
  assert.equal(isValidEventType('pong'), true);
  assert.equal(isValidEventType('nope'), false);
});
