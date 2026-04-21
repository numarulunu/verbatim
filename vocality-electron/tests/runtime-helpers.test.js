/**
 * Tests for pure-Node runtime helpers. Exercises the environment-resolution
 * logic without needing Electron.
 */
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { resolveEnginePath, defaultDataDir } = require('../runtime-helpers.js');

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
