/**
 * log-sink — append-only file sink for the Electron main process.
 *
 * Packaged builds launched from the Start menu have no attached console,
 * so bare console.* calls vanish. This module writes the same lines to
 * {userLogsDir}/verbatim-main.log with ISO timestamps, rotating the
 * previous log as .1 on every app start so the current session is
 * easy to find.
 *
 * Pure Node: no Electron dependency. Callers (main.js) inject logsDir
 * from app.getPath('logs').
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');

const ROTATE_KEEP = 1;

function pad2(n) { return String(n).padStart(2, '0'); }
function pad3(n) { return String(n).padStart(3, '0'); }
function isoStamp() {
  const d = new Date();
  return (
    `${d.getUTCFullYear()}-${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())}T` +
    `${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}:${pad2(d.getUTCSeconds())}.` +
    `${pad3(d.getUTCMilliseconds())}Z`
  );
}

function formatArg(arg) {
  if (arg instanceof Error) return arg.stack || arg.message || String(arg);
  if (typeof arg === 'string') return arg;
  try { return JSON.stringify(arg); } catch (_) { return String(arg); }
}

/**
 * Create a log sink writing to logsDir/verbatim-main.log.
 *
 * Rotation: on createLogSink() call, if verbatim-main.log exists, it is
 * renamed to verbatim-main.log.1 (overwriting any prior .1). Keeps a
 * single previous session; older logs roll off.
 *
 * @param {string} logsDir  — absolute path to the directory that holds logs
 * @returns {{
 *   logPath: string,
 *   dir: string,
 *   append: (level: string, ...args: unknown[]) => void,
 *   install: () => () => void,   // redirect console.*; returns restore fn
 *   close: () => void,
 * }}
 */
function createLogSink(logsDir) {
  if (!logsDir || typeof logsDir !== 'string') {
    throw new TypeError('createLogSink requires a logsDir string');
  }
  fs.mkdirSync(logsDir, { recursive: true });
  const logPath = path.join(logsDir, 'verbatim-main.log');

  // Rotate previous session's log once, at sink creation.
  if (fs.existsSync(logPath)) {
    const rotated = `${logPath}.${ROTATE_KEEP}`;
    try { fs.rmSync(rotated, { force: true }); } catch (_) { /* ignore */ }
    try { fs.renameSync(logPath, rotated); } catch (_) { /* ignore */ }
  }

  // Sync writes keep the tests straightforward and are cheap at the log
  // volume a GUI main process emits (a few lines per minute at steady state,
  // bursts around daemon crashes). Failures degrade to a no-op silently.
  let disabled = false;
  try {
    fs.appendFileSync(logPath, '');
  } catch (_) {
    disabled = true;
  }

  function append(level, ...args) {
    if (disabled) return;
    const line = `[${isoStamp()}] ${level.toUpperCase()} ${args.map(formatArg).join(' ')}\n`;
    try { fs.appendFileSync(logPath, line); } catch (_) { /* ignore */ }
  }

  function install() {
    const orig = {
      log: console.log.bind(console),
      warn: console.warn.bind(console),
      error: console.error.bind(console),
      info: console.info.bind(console),
    };
    console.log = (...a) => { orig.log(...a); append('log', ...a); };
    console.warn = (...a) => { orig.warn(...a); append('warn', ...a); };
    console.error = (...a) => { orig.error(...a); append('error', ...a); };
    console.info = (...a) => { orig.info(...a); append('info', ...a); };
    return () => {
      console.log = orig.log;
      console.warn = orig.warn;
      console.error = orig.error;
      console.info = orig.info;
    };
  }

  function close() {
    // Sync file I/O leaves nothing to flush — close is a no-op kept for
    // API symmetry so callers can always dispose the sink uniformly.
  }

  return { logPath, dir: logsDir, append, install, close };
}

module.exports = { createLogSink };
