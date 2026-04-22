'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

test('App uses the single-shell components instead of tabbed primary views', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'App.tsx'), 'utf8');
  const settingsRailSource = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'components', 'shell', 'SettingsRail.tsx'), 'utf8');

  assert.match(source, /<TitleBar\s*\/>[\s\S]*<WorkspaceHeader[\s\S]*<main className='shell-main'>[\s\S]*<QueuePane[\s\S]*<SettingsRail[\s\S]*<\/main>[\s\S]*<BottomActionBar[\s\S]*<RegistryPanel[\s\S]*<RedoPanel/);
  assert.match(settingsRailSource, /value='custom'[\s\S]*label:\s*'Custom'/);
  assert.match(settingsRailSource, /onClick={onOpenRegistry}[\s\S]*Registry/);
  assert.match(settingsRailSource, /onClick={onOpenRedo}[\s\S]*Redo/);

  assert.doesNotMatch(source, /type Tab =/);
  assert.doesNotMatch(source, /tab === 'batch'/);
  assert.doesNotMatch(source, /RegistryView/);
  assert.doesNotMatch(source, /RedoView/);
});

test('renderer styling exposes drag helpers for the custom title bar', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'index.css'), 'utf8');

  assert.match(source, /\.app-drag\s*\{[\s\S]*-webkit-app-region:\s*drag/);
  assert.match(source, /\.app-no-drag\s*\{[\s\S]*-webkit-app-region:\s*no-drag/);
  assert.match(source, /\.shell-main\s*\{[\s\S]*grid-template-columns:\s*minmax\(0, 1fr\) 360px/);
  assert.match(source, /\.shell-titlebar\s*\{[\s\S]*height:\s*48px/);
  assert.match(source, /\.shell-header__row\s*\{[\s\S]*grid-template-columns:\s*70px minmax\(0, 1fr\) 116px/);
});

test('main window is frameless for the custom shell chrome', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'main.js'), 'utf8');

  assert.match(source, /new BrowserWindow\(\{[\s\S]*frame:\s*false/);
  assert.match(source, /verbatim:window-control/);
});
