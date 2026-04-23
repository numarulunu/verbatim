'use strict';

function createUpdateStatusState() {
  let currentStatus = null;

  return {
    current() {
      return currentStatus;
    },
    set(status) {
      currentStatus = status;
      return currentStatus;
    },
    clear() {
      currentStatus = null;
    },
  };
}

module.exports = {
  createUpdateStatusState,
};
