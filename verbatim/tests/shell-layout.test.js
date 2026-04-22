'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require(path.join(__dirname, '..', 'renderer', 'node_modules', 'typescript'));

function assertOrderedPatterns(source, patterns) {
  let cursor = 0;

  for (const pattern of patterns) {
    const match = pattern.exec(source.slice(cursor));
    assert.ok(match, `missing ${pattern}`);
    cursor += match.index + match[0].length;
  }
}

function parseTsxFile(filePath) {
  const source = fs.readFileSync(filePath, 'utf8');
  const sourceFile = ts.createSourceFile(filePath, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  return { source, sourceFile };
}

function walk(node, visit) {
  visit(node);
  ts.forEachChild(node, (child) => walk(child, visit));
}

function getJsxTagName(node) {
  if (ts.isJsxSelfClosingElement(node) || ts.isJsxOpeningElement(node)) {
    return node.tagName.getText();
  }

  return null;
}

function getJsxAttributes(node) {
  if (ts.isJsxSelfClosingElement(node) || ts.isJsxOpeningElement(node)) {
    return node.attributes.properties;
  }

  return [];
}

function getJsxTextContent(node) {
  let text = '';

  for (const child of node.children) {
    if (ts.isJsxText(child)) {
      text += child.getText().trim();
    }
  }

  return text;
}

function findJsxElement(sourceFile, tagName, predicate) {
  let found = null;

  walk(sourceFile, (node) => {
    if (found) {
      return;
    }

    if (!ts.isJsxSelfClosingElement(node) && !ts.isJsxElement(node)) {
      return;
    }

    const opening = ts.isJsxElement(node) ? node.openingElement : node;
    if (opening.tagName.getText() !== tagName) {
      return;
    }

    if (predicate(opening, node)) {
      found = node;
    }
  });

  return found;
}

function getJsxAttribute(attributes, name) {
  return attributes.find((attribute) => ts.isJsxAttribute(attribute) && attribute.name.getText() === name) || null;
}

function getStringAttributeValue(attribute) {
  if (!attribute || !attribute.initializer || !ts.isStringLiteral(attribute.initializer)) {
    return null;
  }

  return attribute.initializer.text;
}

function optionsContainCustomObject(attribute) {
  if (!attribute || !attribute.initializer || !ts.isJsxExpression(attribute.initializer) || !attribute.initializer.expression || !ts.isArrayLiteralExpression(attribute.initializer.expression)) {
    return false;
  }

  return attribute.initializer.expression.elements.some((element) => {
    if (!ts.isObjectLiteralExpression(element)) {
      return false;
    }

    const valueProp = element.properties.find((prop) => ts.isPropertyAssignment(prop) && prop.name.getText() === 'value');
    const labelProp = element.properties.find((prop) => ts.isPropertyAssignment(prop) && prop.name.getText() === 'label');
    return Boolean(
      valueProp
      && labelProp
      && ts.isStringLiteral(valueProp.initializer)
      && valueProp.initializer.text === 'custom'
      && ts.isStringLiteral(labelProp.initializer)
      && labelProp.initializer.text === 'Custom'
    );
  });
}

test('App uses the single-shell components instead of tabbed primary views', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'App.tsx'), 'utf8');
  const settingsRailPath = path.join(__dirname, '..', 'renderer', 'src', 'components', 'shell', 'SettingsRail.tsx');
  const { sourceFile: settingsRailSourceFile } = parseTsxFile(settingsRailPath);

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

  const select = findJsxElement(settingsRailSourceFile, 'Select', (opening) => {
    const valueAttr = getJsxAttribute(opening.attributes.properties, 'value');
    const optionsAttr = getJsxAttribute(opening.attributes.properties, 'options');
    return getStringAttributeValue(valueAttr) === 'custom' && optionsContainCustomObject(optionsAttr);
  });
  assert.ok(select, 'missing Select custom option');

  const registryButton = findJsxElement(settingsRailSourceFile, 'Button', (opening, node) => {
    const onClickAttr = getJsxAttribute(opening.attributes.properties, 'onClick');
    return onClickAttr && onClickAttr.initializer && ts.isJsxExpression(onClickAttr.initializer) && onClickAttr.initializer.expression && onClickAttr.initializer.expression.getText() === 'onOpenRegistry' && getJsxTextContent(node) === 'Registry';
  });
  assert.ok(registryButton, 'missing Registry button');

  const redoButton = findJsxElement(settingsRailSourceFile, 'Button', (opening, node) => {
    const onClickAttr = getJsxAttribute(opening.attributes.properties, 'onClick');
    return onClickAttr && onClickAttr.initializer && ts.isJsxExpression(onClickAttr.initializer) && onClickAttr.initializer.expression && onClickAttr.initializer.expression.getText() === 'onOpenRedo' && getJsxTextContent(node) === 'Redo';
  });
  assert.ok(redoButton, 'missing Redo button');

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
