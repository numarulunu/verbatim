'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

test('App uses the single-shell components instead of tabbed primary views', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'App.tsx'), 'utf8');
  const settingsRailSource = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'components', 'shell', 'SettingsRail.tsx'), 'utf8');

  assert.ok(source.indexOf('<TitleBar />') < source.indexOf('<WorkspaceHeader'));
  assert.ok(source.indexOf('<WorkspaceHeader') < source.indexOf("<main className='shell-main'>"));
  assert.ok(source.indexOf("<main className='shell-main'>") < source.indexOf('<QueuePane workspace={workspace} status={status} />'));
  assert.ok(source.indexOf('<QueuePane workspace={workspace} status={status} />') < source.indexOf('<SettingsRail'));
  assert.ok(source.indexOf('<SettingsRail') < source.indexOf('<BottomActionBar'));
  assert.ok(source.indexOf('<BottomActionBar') < source.indexOf('<RegistryPanel'));
  assert.ok(source.indexOf('<RegistryPanel') < source.indexOf('<RedoPanel'));

  assert.ok(settingsRailSource.includes("label: 'Custom'"));
  assert.ok(settingsRailSource.includes('onOpenRegistry'));
  assert.ok(settingsRailSource.includes('Registry'));
  assert.ok(settingsRailSource.includes('onOpenRedo'));
  assert.ok(settingsRailSource.includes('Redo'));

  assert.doesNotMatch(source, /type Tab =/);
  assert.doesNotMatch(source, /tab === 'batch'/);
  assert.doesNotMatch(source, /RegistryView/);
  assert.doesNotMatch(source, /RedoView/);
});

test('renderer styling exposes drag helpers for the custom title bar', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'index.css'), 'utf8');

  assert.match(source, /\.app-drag\s*\{[\s\S]*-webkit-app-region:\s*drag/);
  assert.match(source, /\.app-no-drag\s*\{[\s\S]*-webkit-app-region:\s*no-drag/);
  assert.match(source, /\.shell-main\s*\{[\s\S]*grid-template-columns:\s*minmax\(0, 1fr\) 320px/);
  assert.match(source, /\.shell-titlebar\s*\{[\s\S]*height:\s*48px/);
  assert.match(source, /\.shell-header__row\s*\{[\s\S]*grid-template-columns:\s*180px 1fr/);
});

test('main window is frameless for the custom shell chrome', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'main.js'), 'utf8');

  assert.match(source, /new BrowserWindow\(\{[\s\S]*frame:\s*false/);
  assert.match(source, /verbatim:window-control/);
});
