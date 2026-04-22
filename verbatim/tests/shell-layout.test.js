'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

test('App uses the single-shell components instead of tabbed primary views', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'App.tsx'), 'utf8');
  const settingsRailSource = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'components', 'shell', 'SettingsRail.tsx'), 'utf8');

  assert.match(source, /TitleBar/);
  assert.match(source, /WorkspaceHeader/);
  assert.match(source, /<main className='shell-main'>[\s\S]*<QueuePane\b[\s\S]*<SettingsRail\b[\s\S]*<\/main>/);
  assert.match(source, /BottomActionBar/);
  assert.match(source, /RegistryPanel/);
  assert.match(source, /RedoPanel/);
  assert.match(settingsRailSource, /<Select value='custom'[\s\S]*label: 'Custom'/);
  assert.match(settingsRailSource, /<Button variant='secondary' onClick={onOpenRegistry} disabled={running}>Registry<\/Button>/);
  assert.match(settingsRailSource, /<Button variant='secondary' onClick={onOpenRedo}>Redo<\/Button>/);

  assert.doesNotMatch(source, /type Tab =/);
  assert.doesNotMatch(source, /tab === 'batch'/);
  assert.doesNotMatch(source, /RegistryView/);
  assert.doesNotMatch(source, /RedoView/);
});

test('renderer styling exposes drag helpers for the custom title bar', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'index.css'), 'utf8');

  assert.match(source, /\.app-drag/);
  assert.match(source, /\.app-no-drag/);
  assert.match(source, /\.shell-main\s*\{[\s\S]*grid-template-columns:\s*minmax\(0, 1fr\) 320px/);
  assert.match(source, /\.shell-titlebar\s*\{[\s\S]*height:\s*48px/);
  assert.match(source, /\.shell-header__row\s*\{[\s\S]*grid-template-columns:\s*180px 1fr/);
});

test('main window is frameless for the custom shell chrome', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'main.js'), 'utf8');

  assert.match(source, /frame:\s*false/);
  assert.match(source, /verbatim:window-control/);
});
