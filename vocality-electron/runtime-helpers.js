/**
 * Runtime helpers — pure-Node utilities used by main.js.
 *
 * Kept in a separate module so they're unit-testable without Electron
 * (tests/runtime-helpers.test.js), matching the converter's pattern.
 */
'use strict';

const path = require('node:path');

/**
 * Resolve where `vocality-engine.exe` lives, whether running from source
 * or from a packaged electron-builder installer.
 *
 * Packaged: electron-builder `extraResources` copies `engine/` into
 *   `process.resourcesPath/engine/`.
 * Development: the dev runs `pyinstaller ... --distpath vocality-electron/engine`,
 *   producing `<project>/engine/vocality-engine.exe` sibling to this file.
 *
 * Arguments are injected so the function stays pure.
 */
function resolveEnginePath(isPackaged, resourcesPath, moduleDirname) {
  if (isPackaged) {
    return path.join(resourcesPath, 'engine', 'vocality-engine.exe');
  }
  return path.join(moduleDirname, 'engine', 'vocality-engine.exe');
}

/**
 * Where the daemon-created user-data tree lives. Brief §3 mandates it stay
 * OUTSIDE Electron's userData because auto-updater may wipe userData.
 *
 * Defaults to %LOCALAPPDATA%\Vocality\data on Windows; the user may override
 * via the Settings panel (Gate 6). On first run, main.js reads a pointer
 * from userData/vocality-settings.json that records the chosen path.
 */
function defaultDataDir(localAppData) {
  if (!localAppData) {
    throw new Error('defaultDataDir requires LOCALAPPDATA');
  }
  return path.join(localAppData, 'Vocality', 'data');
}

module.exports = { resolveEnginePath, defaultDataDir };
