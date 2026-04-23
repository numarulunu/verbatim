'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

test('renderer build uses a relative asset base for packaged file:// loads', () => {
  const viteConfig = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'vite.config.ts'), 'utf8');
  assert.match(viteConfig, /base:\s*[']\.\/[']/);
});
