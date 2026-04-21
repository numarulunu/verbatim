/**
 * Runtime helpers — pure-Node utilities used by main.js.
 *
 * Kept in a separate module so they're unit-testable without Electron
 * (tests/runtime-helpers.test.js), matching the converter's pattern.
 */
'use strict';

const path = require('node:path');

/**
 * Resolve where `verbatim-engine.exe` lives, whether running from source
 * or from a packaged electron-builder installer.
 *
 * Packaged: electron-builder `extraResources` copies `engine/` into
 *   `process.resourcesPath/engine/`.
 * Development: the dev runs `pyinstaller ... --distpath verbatim/engine`,
 *   producing `<project>/engine/verbatim-engine.exe` sibling to this file.
 *
 * Arguments are injected so the function stays pure.
 */
function resolveEnginePath(isPackaged, resourcesPath, moduleDirname) {
  if (isPackaged) {
    return path.join(resourcesPath, 'engine', 'verbatim-engine.exe');
  }
  return path.join(moduleDirname, 'engine', 'verbatim-engine.exe');
}

/**
 * Where the daemon-created user-data tree lives. Brief §3 mandates it stay
 * OUTSIDE Electron's userData because auto-updater may wipe userData.
 *
 * Defaults to %LOCALAPPDATA%\Verbatim\data on Windows; the user may override
 * via the Settings panel (Gate 6). On first run, main.js reads a pointer
 * from userData/verbatim-settings.json that records the chosen path.
 */
function defaultDataDir(localAppData) {
  if (!localAppData) {
    throw new Error('defaultDataDir requires LOCALAPPDATA');
  }
  return path.join(localAppData, 'Verbatim', 'data');
}

/**
 * Decide how to invoke the engine based on the environment.
 *
 * Packaged builds ship a PyInstaller folder at `resources/engine/` with a
 * single `verbatim-engine.exe` entry point. Development runs against the
 * repo root's `.venv/Scripts/python.exe engine_daemon.py`.
 *
 * Arguments injected so this stays pure.
 */
function resolveEngineCommand(isPackaged, resourcesPath, moduleDirname) {
  if (isPackaged) {
    return {
      command: path.join(resourcesPath, 'engine', 'verbatim-engine.exe'),
      args: [],
      cwd: path.join(resourcesPath, 'engine'),
    };
  }
  const repoRoot = path.resolve(moduleDirname, '..');
  const python = path.join(repoRoot, '.venv', 'Scripts', 'python.exe');
  return {
    command: python,
    args: ['-u', path.join(repoRoot, 'engine_daemon.py')],
    cwd: repoRoot,
  };
}

module.exports = { resolveEnginePath, defaultDataDir, resolveEngineCommand };
