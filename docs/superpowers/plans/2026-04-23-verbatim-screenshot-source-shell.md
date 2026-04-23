# Verbatim Screenshot-Source Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retarget the current Verbatim renderer shell so it visually matches the new screenshot-source UI while preserving Verbatim-specific settings, queue behavior, and Electron bridge behavior.

**Architecture:** Build from the current approved shell state on `master`, not from scratch. Tighten the remaining shell guardrails first, then reshape the chrome, queue, and right rail toward the screenshot in focused passes. Keep Verbatim-only secondary tools available through low-emphasis rail entries and popups so the main shell remains visually faithful.

**Tech Stack:** Electron, React, TypeScript, Vite, Node test runner, Tailwind utility classes, CSS shell tokens

---

## File Structure

**Modify:**
- `verbatim/tests/shell-layout.test.js` - retarget shell guardrails from the older hard-clone assumptions to the screenshot-source shell.
- `verbatim/renderer/src/components/shell/TitleBar.tsx` - align the brand cluster and window controls to the new screenshot while keeping Verbatim branding.
- `verbatim/renderer/src/components/shell/WorkspaceHeader.tsx` - enforce the two-row folder-strip-only header with the compact output utility button.
- `verbatim/renderer/src/components/shell/BottomActionBar.tsx` - keep the flat start slab and body structure while matching the screenshot's density more closely.
- `verbatim/renderer/src/components/shell/QueuePane.tsx` - reduce wrapper chrome so the left pane reads like the screenshot's table shell.
- `verbatim/renderer/src/components/batch/FileList.tsx` - tighten the queue header, empty state, and totals strip toward the screenshot.
- `verbatim/renderer/src/components/batch/FileRow.tsx` - compress row content into the screenshot's dense rhythm without losing Verbatim run-state meaning.
- `verbatim/renderer/src/components/shell/SettingsRail.tsx` - rebuild the right rail to the screenshot's preset-card-plus-sections stack and convert extra Verbatim tools into low-emphasis entries.
- `verbatim/renderer/src/components/shell/RegistryPanel.tsx` - keep popup behavior, but ensure launch points and opened surface fit the new shell language.
- `verbatim/renderer/src/components/shell/RedoPanel.tsx` - same as `RegistryPanel.tsx`, for redo flow.
- `verbatim/renderer/src/index.css` - finish the screenshot-source geometry, spacing, and low-emphasis utility styling across shell regions.
- `verbatim/package.json` - bump the desktop app version for the screenshot-source shell pass.
- `verbatim/package-lock.json` - lockfile update for the version bump.
- `tool_registry.md` - record the screenshot-source shell redesign wave.

**Reference Only:**
- `C:\Users\Gaming PC\Desktop\Transcriptor v2\{47D30056-5EED-40EF-BFF5-3CC7D99D858A}.png`
- `C:\Users\Gaming PC\Desktop\Claude\Convertor\_bolt_frontend\src\components\TopBar.jsx`
- `C:\Users\Gaming PC\Desktop\Claude\Convertor\_bolt_frontend\src\components\FolderPickers.jsx`
- `C:\Users\Gaming PC\Desktop\Claude\Convertor\_bolt_frontend\src\components\FileQueue.jsx`
- `C:\Users\Gaming PC\Desktop\Claude\Convertor\_bolt_frontend\src\components\BottomBar.jsx`
- `C:\Users\Gaming PC\Desktop\Claude\Convertor\_bolt_frontend\src\components\RightPane.jsx`
- `C:\Users\Gaming PC\Desktop\Claude\Convertor\_bolt_frontend\src\components\ProfileDropdown.jsx`

## Task 1: Retarget Shell Guardrails To The Screenshot Source

**Files:**
- Modify: `verbatim/tests/shell-layout.test.js`

- [ ] **Step 1: Add the failing screenshot-source header and footer assertions**

```js
const source = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'App.tsx'), 'utf8');
const cssSource = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'index.css'), 'utf8');
const settingsRailSource = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'components', 'shell', 'SettingsRail.tsx'), 'utf8');
const workspaceHeaderSource = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'components', 'shell', 'WorkspaceHeader.tsx'), 'utf8');

assert.match(source, /<TitleBar\s*\/>[\s\S]*<WorkspaceHeader[\s\S]*<main className='shell-main'>/);
assert.match(source, /<BottomActionBar[\s\S]*<RegistryPanel[\s\S]*<RedoPanel/);
assert.match(cssSource, /\.shell-header__row\s*\{[\s\S]*grid-template-columns:\s*44px minmax\(0, 1fr\) auto auto/);
assert.match(cssSource, /\.shell-action\s*\{[\s\S]*grid-template-columns:\s*180px 1fr/);
```

- [ ] **Step 2: Add the failing screenshot-source right-rail entry assertions**

```js
assert.match(settingsRailSource, /onOpenRegistry/);
assert.match(settingsRailSource, /onOpenRedo/);
assert.match(settingsRailSource, /onOpenSettings/);
assert.doesNotMatch(workspaceHeaderSource, /shell-header__actions/);
```

- [ ] **Step 3: Run the focused test**

Run: `node --test tests/shell-layout.test.js`
Expected: FAIL on at least one screenshot-source guardrail that current code does not satisfy yet.

- [ ] **Step 4: Commit the red checkpoint**

```bash
git add tests/shell-layout.test.js
git commit -m "test: retarget shell guardrails to screenshot source"
```

Verify:
- `node --test tests/shell-layout.test.js`

## Task 2: Lock The Title Bar, Header, And Footer To The New Screenshot

**Files:**
- Modify: `verbatim/renderer/src/components/shell/TitleBar.tsx`
- Modify: `verbatim/renderer/src/components/shell/WorkspaceHeader.tsx`
- Modify: `verbatim/renderer/src/components/shell/BottomActionBar.tsx`
- Modify: `verbatim/renderer/src/index.css`
- Test: `verbatim/tests/shell-layout.test.js`

- [ ] **Step 1: Write the failing shell test updates for the new chrome density**

```js
const cssSource = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'index.css'), 'utf8');

assert.match(cssSource, /\.shell-titlebar__logo\s*\{[\s\S]*width:\s*20px;[\s\S]*height:\s*20px/);
assert.match(cssSource, /\.shell-header__field\s*\{[\s\S]*height:\s*30px/);
assert.match(cssSource, /\.shell-action\s*\{[\s\S]*min-height:\s*68px/);
```

- [ ] **Step 2: Run the focused test to confirm the delta**

Run: `node --test tests/shell-layout.test.js`
Expected: FAIL if the current shell still diverges from the screenshot-source density.

- [ ] **Step 3: Implement the screenshot-source title bar and header structure**

```tsx
<header className='app-drag shell-titlebar'>
  <div className='shell-titlebar__brand'>
    <div className='shell-titlebar__logo'>{/* compact Verbatim logo */}</div>
    <div className='shell-titlebar__name'>Verbatim</div>
  </div>
  <div className='shell-titlebar__controls app-no-drag'>{/* window buttons */}</div>
</header>
```

```tsx
<section className='shell-header'>
  <div className='shell-header__paths'>
    <PathRow label='Input' value={inputDir} onBrowse={() => { void browseInput(); }} />
    <PathRow
      label='Output'
      value={outputDir}
      onBrowse={() => { void browseOutput(); }}
      utility={(
        <button type='button' className='shell-header__utility' onClick={() => { void refresh(); }}>
          <RefreshCw size={13} strokeWidth={1.6} />
        </button>
      )}
    />
  </div>
</section>
```

- [ ] **Step 4: Implement the screenshot-source footer density**

```tsx
<footer className='shell-action'>
  {running ? <div className='shell-action__progress' style={{ width: `${progress}%` }} /> : null}
  <button type='button' className={running ? 'shell-action__button shell-action__button--stop' : 'shell-action__button shell-action__button--start'}>
    <span>{running ? 'Stop' : 'Start'}</span>
  </button>
  <div className='shell-action__body'>
    <div className='shell-action__copy'>
      <div className='shell-action__headline'>{headline}</div>
      <div className='shell-action__detail'>{detail}</div>
    </div>
    <button type='button' className='shell-action__link'>Open output folder</button>
  </div>
</footer>
```

- [ ] **Step 5: Run verification**

Run: `node --test tests/shell-layout.test.js`
Expected: PASS.

Run: `npm run renderer:build --silent`
Expected: PASS.

- [ ] **Step 6: Commit the chrome pass**

```bash
git add tests/shell-layout.test.js renderer/src/components/shell/TitleBar.tsx renderer/src/components/shell/WorkspaceHeader.tsx renderer/src/components/shell/BottomActionBar.tsx renderer/src/index.css
git commit -m "feat: retarget Verbatim shell chrome to screenshot source"
```

Verify:
- `node --test tests/shell-layout.test.js`
- `npm run renderer:build --silent`

## Task 3: Densify The Left Queue To The Screenshot's Table Rhythm

**Files:**
- Modify: `verbatim/renderer/src/components/batch/FileList.tsx`
- Modify: `verbatim/renderer/src/components/batch/FileRow.tsx`
- Modify: `verbatim/renderer/src/components/shell/QueuePane.tsx`
- Modify: `verbatim/renderer/src/index.css`

- [ ] **Step 1: Write the failing queue-shell guardrail updates**

```js
const cssSource = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'index.css'), 'utf8');
const queuePaneSource = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'components', 'shell', 'QueuePane.tsx'), 'utf8');

assert.match(cssSource, /\.shell-queue__table-head\s*\{[\s\S]*font-size:\s*10px/);
assert.match(cssSource, /\.shell-queue__row\s*\{[\s\S]*min-height:\s*44px/);
assert.match(queuePaneSource, /shell-queue__footer/);
```

- [ ] **Step 2: Run the focused test**

Run: `node --test tests/shell-layout.test.js`
Expected: FAIL if the left-pane density markers are not yet present.

- [ ] **Step 3: Replace the empty state and table shell with the screenshot-style table**

```tsx
if (files.length === 0) {
  return (
    <div className='shell-queue__table flex-1 min-h-0'>
      <div className='shell-queue__table-head' style={{ gridTemplateColumns: QUEUE_GRID }}>
        <input type='checkbox' checked={false} disabled />
        <span>Filename</span>
        <span>Class</span>
        <span>Size</span>
        <span>Status</span>
      </div>
      <div className='shell-queue__empty-row'>Pick an input folder.</div>
    </div>
  );
}
```

- [ ] **Step 4: Compress each row to the screenshot rhythm**

```tsx
const QUEUE_GRID = '28px minmax(0, 1fr) 92px 72px 120px';
const classLabel = 'Audio';
const stateLabel = progress?.state === 'running' ? 'Running' : file.alreadyProcessed ? 'Processed' : 'Queued';
```

```tsx
<div className='shell-queue__row' style={{ gridTemplateColumns: QUEUE_GRID }}>
  <input type='checkbox' checked={selected} onChange={onToggle} />
  <div className='shell-queue__file'>{file.name}</div>
  <div className='shell-queue__class'>{classLabel}</div>
  <div className='shell-queue__size'>{fmtSize(file.size)}</div>
  <div className='shell-queue__state'>{stateLabel}</div>
</div>
```

- [ ] **Step 5: Run verification**

Run: `node --test tests/shell-layout.test.js`
Expected: PASS.

Run: `npm run renderer:build --silent`
Expected: PASS.

- [ ] **Step 6: Commit the queue pass**

```bash
git add tests/shell-layout.test.js renderer/src/components/batch/FileList.tsx renderer/src/components/batch/FileRow.tsx renderer/src/components/shell/QueuePane.tsx renderer/src/index.css
git commit -m "feat: retarget Verbatim queue to screenshot source"
```

Verify:
- `node --test tests/shell-layout.test.js`
- `npm run renderer:build --silent`

## Task 4: Rebuild The Right Rail And Hide Extra Tools Behind Low-Emphasis Entries

**Files:**
- Modify: `verbatim/renderer/src/components/shell/SettingsRail.tsx`
- Modify: `verbatim/renderer/src/components/shell/RegistryPanel.tsx`
- Modify: `verbatim/renderer/src/components/shell/RedoPanel.tsx`
- Modify: `verbatim/renderer/src/index.css`

- [ ] **Step 1: Write the failing right-rail guardrail updates**

```js
const settingsRailSource = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'src', 'components', 'shell', 'SettingsRail.tsx'), 'utf8');

assert.match(settingsRailSource, /<Select value='custom'/);
assert.match(settingsRailSource, /shell-card/);
assert.match(settingsRailSource, /shell-rail__tools/);
assert.match(settingsRailSource, /onOpenRegistry/);
assert.match(settingsRailSource, /onOpenRedo/);
assert.match(settingsRailSource, /onOpenSettings/);
```

- [ ] **Step 2: Run the focused test**

Run: `node --test tests/shell-layout.test.js`
Expected: FAIL until the screenshot-source low-emphasis tool stack exists.

- [ ] **Step 3: Rebuild the rail to the screenshot's dropdown-card-sections stack**

```tsx
<aside className='shell-rail'>
  <div className='shell-rail__top'>
    <Select value='custom' onChange={() => {}} options={[{ value: 'custom', label: 'Custom' }]} />
    <div className='shell-card'>{/* impact summary */}</div>
  </div>
  <div className='shell-rail__body'>{/* Verbatim settings sections */}</div>
</aside>
```

- [ ] **Step 4: Move `Registry`, `Redo`, and advanced settings into low-emphasis rail entries**

```tsx
<div className='shell-rail__tools'>
  <button type='button' className='shell-rail__tool-link' onClick={onOpenRegistry}>Registry</button>
  <button type='button' className='shell-rail__tool-link' onClick={onOpenRedo}>Redo</button>
  <button type='button' className='shell-rail__tool-link' onClick={onOpenSettings}>Advanced settings</button>
</div>
```

- [ ] **Step 5: Align popup surfaces to the screenshot-source shell language**

```tsx
<RegistryPanel open={registryOpen} onClose={() => setRegistryOpen(false)} pushToast={pushToast} />
<RedoPanel open={redoOpen} onClose={() => setRedoOpen(false)} running={workspace.running} setRunning={workspace.setRunning} pushToast={pushToast} />
```

```css
.shell-rail__tools { display: flex; flex-direction: column; gap: 6px; }
.shell-rail__tool-link { justify-content: flex-start; font-size: 12px; color: #a0a0a0; }
```

- [ ] **Step 6: Run verification**

Run: `node --test tests/shell-layout.test.js`
Expected: PASS.

Run: `npm run renderer:build --silent`
Expected: PASS.

- [ ] **Step 7: Commit the right-rail pass**

```bash
git add tests/shell-layout.test.js renderer/src/components/shell/SettingsRail.tsx renderer/src/components/shell/RegistryPanel.tsx renderer/src/components/shell/RedoPanel.tsx renderer/src/index.css
git commit -m "feat: retarget Verbatim right rail to screenshot source"
```

Verify:
- `node --test tests/shell-layout.test.js`
- `npm run renderer:build --silent`

## Task 5: Final Shell Polish, Version Bump, And Desktop Verification

**Files:**
- Modify: `verbatim/package.json`
- Modify: `verbatim/package-lock.json`
- Modify: `tool_registry.md`

- [ ] **Step 1: Bump the app version for the screenshot-source shell wave**

```json
{
  "version": "0.1.6"
}
```

- [ ] **Step 2: Record the redesign wave in the tool registry**

```md
| 2026-04-23 | v1.0 | Verbatim Screenshot-Source Shell | Electron desktop app | Retargeted the renderer shell to the new screenshot source of truth while keeping Verbatim-specific settings and secondary tools. |
```

- [ ] **Step 3: Run final verification**

Run: `node --test tests/shell-layout.test.js`
Expected: PASS.

Run: `npm run renderer:build --silent`
Expected: PASS.

Run: `npm test --silent`
Expected: PASS or only pre-existing unrelated failures.

- [ ] **Step 4: Commit the release polish**

```bash
git add package.json package-lock.json ../tool_registry.md tests/shell-layout.test.js
git commit -m "chore: finalize screenshot-source shell pass"
```

Verify:
- `node --test tests/shell-layout.test.js`
- `npm run renderer:build --silent`
- `npm test --silent`
