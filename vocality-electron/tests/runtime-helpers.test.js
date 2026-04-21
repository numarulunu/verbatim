/**
 * Tests for pure-Node runtime helpers. Exercises the environment-resolution
 * logic without needing Electron.
 */
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { resolveEnginePath, defaultDataDir, resolveEngineCommand } = require('../runtime-helpers.js');

test('resolveEnginePath: packaged mode uses process.resourcesPath', () => {
  const p = resolveEnginePath(true, '/fake/resources', '/fake/dev');
  assert.equal(p, path.join('/fake/resources', 'engine', 'vocality-engine.exe'));
});

test('resolveEnginePath: dev mode uses __dirname', () => {
  const p = resolveEnginePath(false, '/fake/resources', '/fake/dev');
  assert.equal(p, path.join('/fake/dev', 'engine', 'vocality-engine.exe'));
});

test('defaultDataDir: joins under Vocality/data', () => {
  const p = defaultDataDir('C:/Users/fake/AppData/Local');
  assert.equal(p, path.join('C:/Users/fake/AppData/Local', 'Vocality', 'data'));
});

test('defaultDataDir: throws on missing LOCALAPPDATA', () => {
  assert.throws(() => defaultDataDir(''), /LOCALAPPDATA/);
  assert.throws(() => defaultDataDir(null), /LOCALAPPDATA/);
  assert.throws(() => defaultDataDir(undefined), /LOCALAPPDATA/);
});

test('resolveEngineCommand: packaged → vocality-engine.exe, no args', () => {
  const cmd = resolveEngineCommand(true, '/fake/resources', '/fake/dev');
  assert.equal(cmd.command, path.join('/fake/resources', 'engine', 'vocality-engine.exe'));
  assert.deepEqual(cmd.args, []);
  assert.equal(cmd.cwd, path.join('/fake/resources', 'engine'));
});

test('resolveEngineCommand: dev → .venv python + engine_daemon.py at repo root', () => {
  const cmd = resolveEngineCommand(false, '/fake/resources', '/repo/vocality-electron');
  const repo = path.resolve('/repo/vocality-electron', '..');
  assert.equal(cmd.command, path.join(repo, '.venv', 'Scripts', 'python.exe'));
  assert.deepEqual(cmd.args, ['-u', path.join(repo, 'engine_daemon.py')]);
  assert.equal(cmd.cwd, repo);
});
