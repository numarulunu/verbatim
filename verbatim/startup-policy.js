'use strict';

function deriveTopBarStatus(status, running) {
  if (!running) {
    return status;
  }
  if (status === 'down' || status === 'shutting_down' || status === 'crashed') {
    return status;
  }
  return 'busy';
}

function shouldStartBackgroundServices(rendererLoaded) {
  return rendererLoaded;
}

const startupPolicy = {
  deriveTopBarStatus,
  shouldStartBackgroundServices,
};

module.exports = startupPolicy;
module.exports.default = startupPolicy;
