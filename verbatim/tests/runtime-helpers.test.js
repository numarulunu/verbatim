/**
 * Tests for pure-Node runtime helpers. Exercises the environment-resolution
 * logic without needing Electron.
 */
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { resolveEnginePath, defaultDataDir, resolveEngineCommand, resolveRendererTarget } = require('../runtime-helpers.js');

test('resolveEnginePath: packaged mode uses process.resourcesPath', () => {
  const p = resolveEnginePath(true, '/fake/resources', '/fake/dev');
  assert.equal(p, path.join('/fake/resources', 'engine', 'verbatim-engine.exe'));
});

test('resolveEnginePath: dev mode uses __dirname', () => {
  const p = resolveEnginePath(false, '/fake/resources', '/fake/dev');
  assert.equal(p, path.join('/fake/dev', 'engine', 'verbatim-engine.exe'));
});

test('defaultDataDir: joins under Verbatim/data', () => {
  const p = defaultDataDir('C:/Users/fake/AppData/Local');
  assert.equal(p, path.join('C:/Users/fake/AppData/Local', 'Verbatim', 'data'));
});

test('defaultDataDir: throws on missing LOCALAPPDATA', () => {
  assert.throws(() => defaultDataDir(''), /LOCALAPPDATA/);
  assert.throws(() => defaultDataDir(null), /LOCALAPPDATA/);
  assert.throws(() => defaultDataDir(undefined), /LOCALAPPDATA/);
});

test('resolveEngineCommand: packaged → verbatim-engine.exe, no args', () => {
  const cmd = resolveEngineCommand(true, '/fake/resources', '/fake/dev');
  assert.equal(cmd.command, path.join('/fake/resources', 'engine', 'verbatim-engine.exe'));
  assert.deepEqual(cmd.args, []);
  assert.equal(cmd.cwd, path.join('/fake/resources', 'engine'));
});

test('resolveEngineCommand: dev → .venv python + engine_daemon.py at repo root', () => {
  const cmd = resolveEngineCommand(false, '/fake/resources', '/repo/verbatim');
  const repo = path.resolve('/repo/verbatim', '..');
  assert.equal(cmd.command, path.join(repo, '.venv', 'Scripts', 'python.exe'));
  assert.deepEqual(cmd.args, ['-u', path.join(repo, 'engine_daemon.py')]);
  assert.equal(cmd.cwd, repo);
});

test('resolveRendererTarget returns dev URL when VERBATIM_RENDERER_URL is set', () => {
  const result = resolveRendererTarget({
    isPackaged: false,
    rendererUrl: 'http://127.0.0.1:5173',
    appDir: 'C:/repo/verbatim',
    resourcesPath: 'C:/repo/verbatim',
  });
  assert.deepEqual(result, { kind: 'url', value: 'http://127.0.0.1:5173' });
});

test('resolveRendererTarget ignores VERBATIM_RENDERER_URL in packaged mode', () => {
  const result = resolveRendererTarget({
    isPackaged: true,
    rendererUrl: 'http://127.0.0.1:5173',
    appDir: 'C:/repo/verbatim',
    resourcesPath: 'C:/Program Files/Verbatim Transcribe/resources',
  });
  assert.equal(result.kind, 'file');
  assert.match(result.value, /app\.asar[\\/]renderer[\\/]dist[\\/]index\.html$/);
});

test('resolveRendererTarget returns built index.html path in packaged mode', () => {
  const result = resolveRendererTarget({
    isPackaged: true,
    rendererUrl: '',
    appDir: 'C:/repo/verbatim',
    resourcesPath: 'C:/Program Files/Verbatim Transcribe/resources',
  });
  assert.equal(result.kind, 'file');
  assert.match(result.value, /renderer[\\/]dist[\\/]index\.html$/);
});

test('resolveRendererTarget falls back to local renderer dist path in dev mode', () => {
  const result = resolveRendererTarget({
    isPackaged: false,
    rendererUrl: '',
    appDir: 'C:/repo/verbatim',
    resourcesPath: 'C:/repo/verbatim',
  });
  assert.equal(result.kind, 'file');
  assert.match(result.value, /renderer[\\/]dist[\\/]index\.html$/);
});
