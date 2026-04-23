'use strict';

function buildStatusEnvelope(engine) {
  if (!engine) {
    return {
      status: 'down',
      lastReady: null,
      lastExit: null,
    };
  }

  return {
    status: engine.status,
    lastReady: engine.lastReady,
    lastExit: engine.lastExit ?? null,
  };
}

module.exports = {
  buildStatusEnvelope,
};
