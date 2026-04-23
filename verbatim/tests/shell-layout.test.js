'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const typescriptPath = require.resolve('typescript', { paths: [path.join(__dirname, '..', 'renderer')] });
const ts = require(typescriptPath);

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

function unwrapParenthesized(node) {
  let current = node;

  while (current && ts.isParenthesizedExpression(current)) {
    current = current.expression;
  }

  return current;
}

function getReturnedJsxTree(sourceFile, functionName) {
  let returned = null;

  walk(sourceFile, (node) => {
    if (returned || !ts.isFunctionDeclaration(node) || !node.name || node.name.text !== functionName || !node.body) {
      return;
    }

    walk(node.body, (child) => {
      if (returned || !ts.isReturnStatement(child) || !child.expression) {
        return;
      }

      const expression = unwrapParenthesized(child.expression);
      if (ts.isJsxElement(expression) || ts.isJsxSelfClosingElement(expression)) {
        returned = expression;
      }
    });
  });

  return returned;
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

function findJsxElement(root, tagName, predicate) {
  let found = null;

  walk(root, (node) => {
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
  const workspaceHeaderPath = path.join(__dirname, '..', 'renderer', 'src', 'components', 'shell', 'WorkspaceHeader.tsx');
  const { sourceFile: settingsRailSourceFile } = parseTsxFile(settingsRailPath);
  const { source: workspaceHeaderSource } = parseTsxFile(workspaceHeaderPath);
  const settingsRailJsx = getReturnedJsxTree(settingsRailSourceFile, 'SettingsRail');

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

  assert.match(source, /<TitleBar\s*\/>[\s\S]*<WorkspaceHeader[\s\S]*<main className='shell-main'>/);
  assert.match(source, /<BottomActionBar[\s\S]*<RegistryPanel[\s\S]*<RedoPanel/);

  const select = findJsxElement(settingsRailJsx, 'Select', (opening) => {
    const valueAttr = getJsxAttribute(opening.attributes.properties, 'value');
    const optionsAttr = getJsxAttribute(opening.attributes.properties, 'options');
    return getStringAttributeValue(valueAttr) === 'custom' && optionsContainCustomObject(optionsAttr);
  });
  assert.ok(select, 'missing Select custom option');

  assert.doesNotMatch(source, /type Tab =/);
  assert.doesNotMatch(source, /tab === 'batch'/);
  assert.doesNotMatch(source, /RegistryView/);
  assert.doesNotMatch(source, /RedoView/);
  assert.doesNotMatch(workspaceHeaderSource, /shell-header__actions/);
});

test('renderer styling exposes drag helpers for the custom title bar', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'index.css'), 'utf8');

  assert.match(source, /\.app-drag\s*\{[\s\S]*-webkit-app-region:\s*drag/);
  assert.match(source, /\.app-no-drag\s*\{[\s\S]*-webkit-app-region:\s*no-drag/);
  assert.match(source, /\.shell-main\s*\{[\s\S]*grid-template-columns:\s*minmax\(0, 1fr\) 320px/);
  assert.match(source, /\.shell-titlebar\s*\{[\s\S]*height:\s*48px/);
  assert.match(source, /\.shell-titlebar__logo\s*\{[\s\S]*width:\s*20px;[\s\S]*height:\s*20px/);
  assert.match(source, /\.shell-header__row\s*\{[\s\S]*grid-template-columns:\s*44px minmax\(0, 1fr\) auto auto/);
  assert.match(source, /\.shell-header__field\s*\{[\s\S]*height:\s*30px/);
  assert.match(source, /\.shell-action\s*\{[\s\S]*grid-template-columns:\s*180px 1fr/);
  assert.match(source, /\.shell-action\s*\{[\s\S]*min-height:\s*68px/);
});

test('main window is frameless for the custom shell chrome', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'main.js'), 'utf8');

  assert.match(source, /new BrowserWindow\(\{[\s\S]*frame:\s*false/);
  assert.match(source, /verbatim:window-control/);
});





