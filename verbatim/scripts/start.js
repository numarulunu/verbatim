'use strict';

const { spawnSync } = require('node:child_process');
const path = require('node:path');

function buildStartCommands(env = process.env) {
  const commands = [];
  if (!env.VERBATIM_RENDERER_URL) {
    commands.push({ command: 'npm', args: ['run', 'renderer:build'] });
  }
  commands.push({ command: 'electron', args: ['.'] });
  return commands;
}

function resolveCommand(command) {
  if (process.platform === 'win32' && (command === 'npm' || command === 'electron')) {
    return `${command}.cmd`;
  }
  return command;
}

function runStartCommands(commands, env = process.env) {
  const cwd = path.resolve(__dirname, '..');
  for (const step of commands) {
    const result = spawnSync(resolveCommand(step.command), step.args, {
      cwd,
      env,
      stdio: 'inherit',
    });
    if (result.status !== 0) {
      return result.status ?? 1;
    }
  }
  return 0;
}

if (require.main === module) {
  process.exit(runStartCommands(buildStartCommands(process.env)));
}

module.exports = {
  buildStartCommands,
  runStartCommands,
};
