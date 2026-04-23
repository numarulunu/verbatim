'use strict';

function normalizeUpdaterMessage(error) {
  const raw = typeof error?.message === 'string' ? error.message.trim() : '';

  if (!raw) {
    return 'Update check failed.';
  }

  if (
    /releases\.atom/i.test(raw) ||
    /github\.com/i.test(raw) ||
    /status code 404/i.test(raw) ||
    /cannot find any staging user id/i.test(raw)
  ) {
    return 'Auto-update is unavailable for this build.';
  }

  if (/(ECONN|ENOTFOUND|ETIMEDOUT|network|net::)/i.test(raw)) {
    return 'Update check failed. Check your connection and try again later.';
  }

  return 'Update check failed.';
}

module.exports = {
  normalizeUpdaterMessage,
};
