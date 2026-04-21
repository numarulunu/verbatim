/**
 * fetch-ffmpeg — downloads ffmpeg.exe + ffprobe.exe into build/ffmpeg/bin/
 * so `build-engine.spec` can bundle them alongside the frozen daemon.
 *
 * Cached: if the files are already present, this is a no-op.
 *
 * Source: gyan.dev's "release-essentials" build (LGPL, redistributable).
 * URL is pinned to the `release` alias so the latest stable build is
 * fetched each time. Swap to a specific version tag if reproducibility
 * matters.
 *
 * Windows-only — uses PowerShell's Expand-Archive for the unzip.
 *
 * Usage:  node scripts/fetch-ffmpeg.js
 */
'use strict';

const https = require('node:https');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { execFileSync } = require('node:child_process');

const REPO_ROOT = path.resolve(__dirname, '..');
const DEST = path.join(REPO_ROOT, 'build', 'ffmpeg', 'bin');
const URL = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip';
const EXES = ['ffmpeg.exe', 'ffprobe.exe'];

function alreadyCached() {
  return EXES.every((n) => fs.existsSync(path.join(DEST, n)));
}

function httpGet(url, to) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        res.resume();
        return resolve(httpGet(res.headers.location, to));
      }
      if (res.statusCode !== 200) {
        return reject(new Error(`HTTP ${res.statusCode} for ${url}`));
      }
      const total = Number(res.headers['content-length']) || 0;
      let got = 0;
      const out = fs.createWriteStream(to);
      res.on('data', (chunk) => {
        got += chunk.length;
        if (total) {
          process.stderr.write(
            `\rdownloading ffmpeg… ${((got / total) * 100).toFixed(1)}%   `,
          );
        }
      });
      res.on('end', () => process.stderr.write('\n'));
      res.pipe(out);
      out.on('finish', () => out.close(() => resolve(to)));
      out.on('error', reject);
    });
    req.on('error', reject);
  });
}

async function main() {
  if (alreadyCached()) {
    console.log(`ffmpeg already cached at ${DEST}`);
    return;
  }
  fs.mkdirSync(DEST, { recursive: true });

  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'vocality-ffmpeg-'));
  const zipPath = path.join(tmpDir, 'ffmpeg.zip');

  console.log(`fetching ${URL} → ${zipPath}`);
  await httpGet(URL, zipPath);

  const extractDir = path.join(tmpDir, 'extract');
  fs.mkdirSync(extractDir, { recursive: true });
  console.log('extracting…');
  execFileSync('powershell.exe', [
    '-NoProfile', '-NonInteractive',
    '-Command', `Expand-Archive -Path "${zipPath}" -DestinationPath "${extractDir}" -Force`,
  ], { stdio: 'inherit' });

  const releaseDir = fs.readdirSync(extractDir)
    .map((n) => path.join(extractDir, n))
    .find((p) => fs.statSync(p).isDirectory());
  if (!releaseDir) throw new Error('ffmpeg zip contained no directory');
  const binDir = path.join(releaseDir, 'bin');

  for (const name of EXES) {
    const src = path.join(binDir, name);
    const dst = path.join(DEST, name);
    if (!fs.existsSync(src)) throw new Error(`missing ${name} in archive`);
    fs.copyFileSync(src, dst);
    console.log(`installed ${dst}`);
  }

  // Cleanup: best-effort; leaves the zip on failure.
  try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch (_) {}
}

main().catch((err) => {
  console.error('fetch-ffmpeg failed:', err && err.message);
  process.exit(1);
});
