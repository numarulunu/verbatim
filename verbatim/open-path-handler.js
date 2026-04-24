/**
 * open-path-handler — pure action for the `verbatim:open-path` IPC.
 *
 * Extracted from main.js so it is unit-testable (main.js imports `electron`
 * at module load, which node:test cannot require). shell.openPath is
 * injected; the handler validates input, applies security allowlists, and
 * maps shell's string-error convention to a {ok, error} result.
 *
 * Security (SMAC Finding 5): `shell.openPath` dispatches via the OS default
 * handler, which on Windows executes `.exe`, `.bat`, `.cmd`, `.lnk`, `.ps1`,
 * `.msi`, `.scr`, `.vbs`, `.js` directly. A compromised renderer (XSS via
 * remote font CSS, a future preview feature) with unrestricted openPath
 * becomes an RCE pivot. We reject dangerous extensions and require the
 * resolved path to sit inside an allowed root — typically VERBATIM_ROOT
 * (output folder) plus Downloads/Documents/Desktop.
 */
'use strict';

const path = require('node:path');

const DANGEROUS_EXTENSIONS = new Set([
  '.exe', '.bat', '.cmd', '.com', '.lnk', '.ps1', '.psm1',
  '.msi', '.msp', '.scr', '.vbs', '.vbe', '.js', '.jse',
  '.wsh', '.wsf', '.reg', '.cpl', '.hta', '.jar', '.pif',
]);

function isUnderAnyRoot(resolvedPath, roots) {
  const normalizedPath = resolvedPath.toLowerCase();
  for (const root of roots) {
    if (!root) continue;
    const normalizedRoot = path.resolve(root).toLowerCase();
    // Ensure we only match full path segments (not a prefix of a sibling).
    const rootWithSep = normalizedRoot.endsWith(path.sep)
      ? normalizedRoot
      : normalizedRoot + path.sep;
    if (normalizedPath === normalizedRoot || normalizedPath.startsWith(rootWithSep)) {
      return true;
    }
  }
  return false;
}

/**
 * @param {object} args
 * @param {unknown} args.targetPath — raw input from the renderer
 * @param {(p: string) => Promise<string>} args.shellOpenPath
 * @param {string[]} [args.allowedRoots] — absolute paths under which
 *   targetPath must resolve. Empty/absent → legacy permissive mode (used
 *   only by tests that explicitly opt out).
 * @returns {Promise<{ok: boolean, error: string | null}>}
 */
async function openPathAction({ targetPath, shellOpenPath, allowedRoots }) {
  if (typeof targetPath !== 'string' || !targetPath.trim()) {
    throw new Error('Path is required');
  }

  const resolved = path.resolve(targetPath);
  const ext = path.extname(resolved).toLowerCase();
  if (DANGEROUS_EXTENSIONS.has(ext)) {
    return { ok: false, error: `Refusing to open executable file type (${ext})` };
  }

  if (Array.isArray(allowedRoots) && allowedRoots.length > 0) {
    if (!isUnderAnyRoot(resolved, allowedRoots)) {
      return { ok: false, error: 'Path is outside the allowed data directories' };
    }
  }

  const error = await shellOpenPath(resolved);
  return { ok: error.length === 0, error: error || null };
}

module.exports = { openPathAction, DANGEROUS_EXTENSIONS };
