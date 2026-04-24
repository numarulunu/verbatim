'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { openPathAction } = require('../open-path-handler.js');

test('openPathAction returns ok:true when shell reports empty error', async () => {
  const result = await openPathAction({
    targetPath: 'C:/tmp/file.txt',
    shellOpenPath: async () => '',
  });
  assert.deepEqual(result, { ok: true, error: null });
});

test('openPathAction returns ok:false when shell yields a non-empty error', async () => {
  const result = await openPathAction({
    targetPath: 'C:/tmp/file.txt',
    shellOpenPath: async () => 'Failed to open: no app registered',
  });
  assert.deepEqual(result, { ok: false, error: 'Failed to open: no app registered' });
});

test('openPathAction throws on non-string targetPath', async () => {
  await assert.rejects(
    openPathAction({ targetPath: 42, shellOpenPath: async () => '' }),
    /Path is required/,
  );
});

test('openPathAction throws on empty/whitespace targetPath', async () => {
  await assert.rejects(
    openPathAction({ targetPath: '   ', shellOpenPath: async () => '' }),
    /Path is required/,
  );
});

test('openPathAction refuses dangerous extensions', async () => {
  const tries = ['C:/tmp/malware.exe', 'C:/tmp/script.bat', 'C:/tmp/link.lnk', 'C:/tmp/installer.msi', 'C:/tmp/payload.ps1'];
  for (const p of tries) {
    let called = false;
    const result = await openPathAction({
      targetPath: p,
      shellOpenPath: async () => { called = true; return ''; },
    });
    assert.equal(result.ok, false, `expected refusal for ${p}`);
    assert.match(result.error, /executable file type/);
    assert.equal(called, false, 'shellOpenPath must not be invoked for dangerous ext');
  }
});

test('openPathAction refuses paths outside allowedRoots', async () => {
  let called = false;
  const result = await openPathAction({
    targetPath: 'C:/some/stranger/place/data.txt',
    shellOpenPath: async () => { called = true; return ''; },
    allowedRoots: ['C:/Users/ionut'],
  });
  assert.equal(result.ok, false);
  assert.match(result.error, /outside the allowed/);
  assert.equal(called, false, 'shellOpenPath must not be invoked for out-of-root path');
});

test('openPathAction accepts paths under allowedRoots (case-insensitive)', async () => {
  let opened = null;
  const result = await openPathAction({
    targetPath: 'C:/Users/Ionut/Documents/out',
    shellOpenPath: async (p) => { opened = p; return ''; },
    allowedRoots: ['c:/users/ionut'],
  });
  assert.equal(result.ok, true);
  assert.ok(opened, 'shellOpenPath was invoked');
});
