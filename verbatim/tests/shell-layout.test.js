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

function hasClassToken(attribute, token) {
  const value = getStringAttributeValue(attribute);
  return Boolean(value && value.split(/\s+/).includes(token));
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
  const queuePanePath = path.join(__dirname, '..', 'renderer', 'src', 'components', 'shell', 'QueuePane.tsx');
  const { source: settingsRailSource, sourceFile: settingsRailSourceFile } = parseTsxFile(settingsRailPath);
  const { source: workspaceHeaderSource } = parseTsxFile(workspaceHeaderPath);
  const queuePaneSource = fs.readFileSync(queuePanePath, 'utf8');
  const settingsRailJsx = getReturnedJsxTree(settingsRailSourceFile, 'SettingsRail');

  assertOrderedPatterns(source, [
    /<TitleBar\s*\/>/,
    /<main className='shell-main'>/,
    /<QueuePane/,
    /<SettingsRail/,
    /<BottomActionBar/,
    /<RegistryPanel/,
    /<RedoPanel/,
  ]);

  assert.doesNotMatch(source, /<WorkspaceHeader/);
  assert.match(source, /<BottomActionBar[\s\S]*<RegistryPanel[\s\S]*<RedoPanel/);
  assert.match(queuePaneSource, /<WorkspaceHeader[\s\S]*<FileList/);
  const presetControl = findJsxElement(settingsRailJsx, 'select', (opening) => {
    const valueAttr = getJsxAttribute(opening.attributes.properties, 'value');
    const optionsAttr = getJsxAttribute(opening.attributes.properties, 'options');
    const ariaLabelAttr = getJsxAttribute(opening.attributes.properties, 'aria-label');
    const classNameAttr = getJsxAttribute(opening.attributes.properties, 'className');
    const disabledAttr = getJsxAttribute(opening.attributes.properties, 'disabled');
    return getStringAttributeValue(valueAttr) === 'custom'
      && getStringAttributeValue(ariaLabelAttr) === 'Preset shell preview'
      && hasClassToken(classNameAttr, 'shell-rail__preset-control')
      && Boolean(disabledAttr);
  });
  assert.ok(presetControl, 'missing disabled preset control');

  const impactCard = findJsxElement(settingsRailJsx, 'div', (opening) => {
    const classNameAttr = getJsxAttribute(opening.attributes.properties, 'className');
    return hasClassToken(classNameAttr, 'shell-card') && hasClassToken(classNameAttr, 'shell-card--impact');
  });
  assert.ok(impactCard, 'missing shell-card impact summary');

  const heroStats = findJsxElement(impactCard, 'div', (opening) => {
    const classNameAttr = getJsxAttribute(opening.attributes.properties, 'className');
    return hasClassToken(classNameAttr, 'shell-impact__heroes');
  });
  assert.ok(heroStats, 'missing shell-impact__heroes layout');

  const meterRow = findJsxElement(impactCard, 'div', (opening) => {
    const classNameAttr = getJsxAttribute(opening.attributes.properties, 'className');
    return hasClassToken(classNameAttr, 'shell-impact__meters');
  });
  assert.ok(meterRow, 'missing shell-impact__meters layout');

  const chipRow = findJsxElement(impactCard, 'div', (opening) => {
    const classNameAttr = getJsxAttribute(opening.attributes.properties, 'className');
    return hasClassToken(classNameAttr, 'shell-impact__chips');
  });
  assert.ok(chipRow, 'missing shell-impact__chips layout');

  const toolsGroup = findJsxElement(settingsRailJsx, 'div', (opening) => {
    const classNameAttr = getJsxAttribute(opening.attributes.properties, 'className');
    return hasClassToken(classNameAttr, 'shell-rail__tools');
  });
  assert.ok(toolsGroup, 'missing shell-rail__tools launcher group');

  const registryButton = findJsxElement(toolsGroup, 'Button', (opening, node) => {
    const onClickAttr = getJsxAttribute(opening.attributes.properties, 'onClick');
    const classNameAttr = getJsxAttribute(opening.attributes.properties, 'className');
    return onClickAttr && onClickAttr.initializer && ts.isJsxExpression(onClickAttr.initializer) && onClickAttr.initializer.expression && onClickAttr.initializer.expression.getText() === 'onOpenRegistry' && getJsxTextContent(node) === 'Registry' && hasClassToken(classNameAttr, 'shell-rail__tool-link');
  });
  assert.ok(registryButton, 'missing Registry low-emphasis launcher');

  const redoButton = findJsxElement(toolsGroup, 'Button', (opening, node) => {
    const onClickAttr = getJsxAttribute(opening.attributes.properties, 'onClick');
    const classNameAttr = getJsxAttribute(opening.attributes.properties, 'className');
    return onClickAttr && onClickAttr.initializer && ts.isJsxExpression(onClickAttr.initializer) && onClickAttr.initializer.expression && onClickAttr.initializer.expression.getText() === 'onOpenRedo' && getJsxTextContent(node) === 'Redo' && hasClassToken(classNameAttr, 'shell-rail__tool-link');
  });
  assert.ok(redoButton, 'missing Redo low-emphasis launcher');

  const advancedSettingsButton = findJsxElement(toolsGroup, 'Button', (opening, node) => {
    const onClickAttr = getJsxAttribute(opening.attributes.properties, 'onClick');
    const classNameAttr = getJsxAttribute(opening.attributes.properties, 'className');
    return onClickAttr && onClickAttr.initializer && ts.isJsxExpression(onClickAttr.initializer) && onClickAttr.initializer.expression && onClickAttr.initializer.expression.getText() === 'onOpenSettings' && getJsxTextContent(node) === 'Advanced settings' && hasClassToken(classNameAttr, 'shell-rail__tool-link');
  });
  assert.ok(advancedSettingsButton, 'missing Advanced settings low-emphasis launcher');

  assert.doesNotMatch(source, /type Tab =/);
  assert.doesNotMatch(source, /tab === 'batch'/);
  assert.doesNotMatch(source, /RegistryView/);
  assert.doesNotMatch(source, /RedoView/);
  assert.doesNotMatch(settingsRailSource, /shell-card__stats/);
  assert.doesNotMatch(workspaceHeaderSource, /shell-header__actions/);
});

test('renderer styling exposes drag helpers for the custom title bar', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'index.css'), 'utf8');
  const queuePaneSource = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'components', 'shell', 'QueuePane.tsx'), 'utf8');
  const fileRowSource = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'components', 'batch', 'FileRow.tsx'), 'utf8');

  assert.match(source, /\.app-drag\s*\{[\s\S]*-webkit-app-region:\s*drag/);
  assert.match(source, /\.app-no-drag\s*\{[\s\S]*-webkit-app-region:\s*no-drag/);
  assert.match(source, /\.shell-app\s*\{[\s\S]*min-width:\s*960px/);
  assert.match(source, /\.shell-app\s*\{[\s\S]*min-height:\s*640px/);
  assert.match(source, /\.shell-main\s*\{[\s\S]*grid-template-columns:\s*minmax\(0, 1fr\) 320px/);
  assert.match(source, /\.shell-titlebar\s*\{[\s\S]*height:\s*48px/);
  assert.match(source, /\.shell-titlebar__logo\s*\{[\s\S]*width:\s*20px;[\s\S]*height:\s*20px/);
  assert.match(source, /\.shell-header__row\s*\{[\s\S]*grid-template-columns:\s*44px minmax\(0, 1fr\) auto auto/);
  assert.match(source, /\.shell-header__field\s*\{[\s\S]*height:\s*30px/);
  assert.match(source, /\.shell-action\s*\{[\s\S]*grid-template-columns:\s*168px 1fr/);
  assert.match(source, /\.shell-action\s*\{[\s\S]*min-height:\s*68px/);
  assert.match(source, /\.shell-queue__table-head\s*\{[\s\S]*font-size:\s*10px/);
  assert.match(source, /\.shell-queue__row\s*\{[\s\S]*min-height:\s*44px/);
  assert.doesNotMatch(queuePaneSource, /shell-queue__head/);
  assert.doesNotMatch(queuePaneSource, /shell-queue__footer/);
  assert.match(fileRowSource, /return 'Audio';/);
  assert.match(fileRowSource, /<div className='shell-queue__class'>\{[^}]+\}<\/div>/);
  assert.match(fileRowSource, /<div className=\{statusTone\(progress, file\.alreadyProcessed\)\}>\{statusLabel\(progress, file\.alreadyProcessed\)\}<\/div>/);
  assert.doesNotMatch(fileRowSource, /<div className='shell-queue__class'>\{statusLabel\(progress, file\.alreadyProcessed\)\}<\/div>/);
});

test('title bar clones the Minifier wordmark layout with Verbatim branding and version metadata', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'components', 'shell', 'TitleBar.tsx'), 'utf8');

  assert.match(source, /shell-titlebar__wordmark/);
  assert.match(source, /shell-titlebar__meta/);
  assert.match(source, /Verbatim/);
  assert.match(source, /APP_VERSION/);
  assert.match(source, /v\{APP_VERSION\}/);
  assert.doesNotMatch(source, />Transcribe</);
});

test('main window is frameless for the custom shell chrome', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'main.js'), 'utf8');

  assert.match(source, /new BrowserWindow\(\{[\s\S]*frame:\s*false/);
  assert.match(source, /minWidth:\s*960/);
  assert.match(source, /minHeight:\s*640/);
  assert.match(source, /verbatim:window-control/);
});

test('impact card stays compact and does not render verbose detail copy', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'components', 'shell', 'SettingsRail.tsx'), 'utf8');

  assert.doesNotMatch(source, /shell-impact__hero-detail/);
  assert.doesNotMatch(source, /shell-meter__detail/);
});

