import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Electron 41 ships Chromium 138, so we can target a modern baseline and
// skip legacy transforms. Sourcemaps off by default — the renderer is
// packaged inside app.asar and we don't want to ship stack frames that
// reference TSX source lines to end users. Console/debugger statements
// are stripped in prod so accidental diagnostic prints do not leak into
// the released build (main-process logs still land in the log sink; see
// SMAC 2026-04-23 Finding 3). manualChunks splits the bundle so React +
// the icon set cache independently from app code on updater diffs.
export default defineConfig({
  base: './',
  plugins: [react()],
  build: {
    target: 'chrome130',
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom'],
          icons: ['lucide-react'],
        },
      },
    },
  },
  esbuild: {
    drop: ['console', 'debugger'],
  },
});
