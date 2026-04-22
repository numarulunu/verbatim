'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

function assertOrderedPatterns(source, patterns) {
  let cursor = 0;

  for (const pattern of patterns) {
    const match = pattern.exec(source.slice(cursor));
    assert.ok(match, `missing ${pattern}`);
    cursor += match.index + match[0].length;
  }
}

test('App uses the single-shell components instead of tabbed primary views', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'App.tsx'), 'utf8');
  const settingsRailSource = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'components', 'shell', 'SettingsRail.tsx'), 'utf8');

  assertOrderedPatterns(source, [
    /<TitleBar\s*\/>/,
    /<WorkspaceHeader/,
    /<main className='shell-main'>/,
    /<QueuePane/,
    /<SettingsRail/,
    /<BottomActionBar/,
    /<RegistryPanel/,
    /<RedoPanel/,
  ]);

  assert.match(settingsRailSource, /options=\{\[\{\s*value:\s*'custom',\s*label:\s*'Custom'/);
  assert.match(settingsRailSource, /onClick=\{onOpenRegistry\}[\s\S]*>Registry<\/?Button>/);
  assert.match(settingsRailSource, /onClick=\{onOpenRedo\}[\s\S]*>Redo<\/?Button>/);

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
