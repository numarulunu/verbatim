/**
 * Guards that the engine/ drop location exists and is documented.
 *
 * This isn't a unit test — it's a structural assertion run under `npm test`
 * so a broken extraResources layout trips the test suite before packaging.
 * In Gate 3 we only assert the placeholder exists. Gate 5 extends this to
 * verify `verbatim-engine.exe` runs and emits a `ready` event.
 */
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { resolveRendererTarget } = require('../runtime-helpers.js');

function readPackageJson() {
  return JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'package.json'), 'utf8'));
}

test('engine directory exists (electron-builder extraResources target)', () => {
  const enginePath = path.join(__dirname, '..', 'engine');
  assert.ok(
    fs.existsSync(enginePath),
    `engine/ must exist (PyInstaller drops verbatim-engine.exe here at build time). Missing: ${enginePath}`,
  );
});

test('engine/README.md documents the build-time drop', () => {
  const readme = path.join(__dirname, '..', 'engine', 'README.md');
  assert.ok(
    fs.existsSync(readme),
    'engine/README.md should explain how verbatim-engine.exe lands in this directory.',
  );
});

test('build-config/electron-builder.yml exists', () => {
  const cfg = path.join(__dirname, '..', 'build-config', 'electron-builder.yml');
  assert.ok(
    fs.existsSync(cfg),
    'build-config/electron-builder.yml must be present for `npm run build`.',
  );
});

test('packaged renderer target resolves to renderer/dist/index.html inside app.asar', () => {
  const target = resolveRendererTarget({
    isPackaged: true,
    rendererUrl: '',
    appDir: path.join('C:', 'repo', 'verbatim'),
    resourcesPath: path.join('C:', 'Program Files', 'Verbatim Transcribe', 'resources'),
  });

  assert.deepEqual(target, {
    kind: 'file',
    value: path.join(
      'C:',
      'Program Files',
      'Verbatim Transcribe',
      'resources',
      'app.asar',
      'renderer',
      'dist',
      'index.html',
    ),
  });
});

test('start script routes through the conditional helper', () => {
  const pkg = readPackageJson();
  assert.equal(pkg.scripts.start, 'node scripts/start.js');
});

test('publish-win runs prep steps before electron-builder publish', () => {
  const pkg = readPackageJson();
  assert.match(pkg.scripts.publishWin || pkg.scripts['publish-win'], /fetch-ffmpeg/);
  assert.match(pkg.scripts.publishWin || pkg.scripts['publish-win'], /build-engine/);
  assert.match(pkg.scripts.publishWin || pkg.scripts['publish-win'], /renderer:build/);
  assert.match(pkg.scripts.publishWin || pkg.scripts['publish-win'], /electron-builder --win --publish always/);
});

test('build-win runs the same prep steps as publish-win', () => {
  // SMAC 2026-04-23 Finding 16: previously `build-win` skipped fetch-ffmpeg
  // and build-engine, so a fresh `npm run build-win` would package whatever
  // stale engine/ directory was on disk. The script now chains the prep.
  const pkg = readPackageJson();
  const buildWin = pkg.scripts['build-win'];
  assert.ok(buildWin, 'build-win script should exist');
  assert.match(buildWin, /fetch-ffmpeg/, 'build-win must run fetch-ffmpeg');
  assert.match(buildWin, /build-engine/, 'build-win must run build-engine');
  assert.match(
    buildWin,
    /build-win:electron-only|renderer:build/,
    'build-win must reach the renderer build + electron-builder step',
  );
});

test('build-win:electron-only is the bare electron-builder path for fast iteration', () => {
  const pkg = readPackageJson();
  const electronOnly = pkg.scripts['build-win:electron-only'];
  assert.ok(electronOnly, 'build-win:electron-only must exist as the prep-skipping escape hatch');
  assert.match(electronOnly, /renderer:build/);
  assert.match(electronOnly, /electron-builder --win/);
  assert.doesNotMatch(electronOnly, /fetch-ffmpeg/);
  assert.doesNotMatch(electronOnly, /build-engine/);
});
