'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

test('App uses the single-shell components instead of tabbed primary views', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'App.tsx'), 'utf8');
  const settingsRailSource = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'components', 'shell', 'SettingsRail.tsx'), 'utf8');
  const paneSource = `${source}\n${settingsRailSource}`;

  assert.match(source, /TitleBar/);
  assert.match(source, /WorkspaceHeader/);
  assert.match(source, /QueuePane/);
  assert.match(source, /SettingsRail/);
  assert.match(source, /BottomActionBar/);
  assert.match(source, /RegistryPanel/);
  assert.match(source, /RedoPanel/);
  assert.match(paneSource, /Custom/);
  assert.match(paneSource, /\bRegistry\b/);
  assert.match(paneSource, /\bRedo\b/);
  assert.match(paneSource, /QueuePane[\s\S]*SettingsRail[\s\S]*Custom[\s\S]*RegistryPanel[\s\S]*RedoPanel/);

  assert.doesNotMatch(source, /type Tab =/);
  assert.doesNotMatch(source, /tab === 'batch'/);
  assert.doesNotMatch(source, /RegistryView/);
  assert.doesNotMatch(source, /RedoView/);
});

test('renderer styling exposes drag helpers for the custom title bar', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'index.css'), 'utf8');

  assert.match(source, /\.app-drag/);
  assert.match(source, /\.app-no-drag/);
  assert.match(source, /shell-main/);
  assert.match(source, /320px/);
  assert.match(source, /48px/);
  assert.match(source, /180px 1fr/);
});

test('main window is frameless for the custom shell chrome', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'main.js'), 'utf8');

  assert.match(source, /frame:\s*false/);
  assert.match(source, /verbatim:window-control/);
});
