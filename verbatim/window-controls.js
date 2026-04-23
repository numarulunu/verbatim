'use strict';

function getWindowControlState(window) {
  return {
    maximized: Boolean(window && !window.isDestroyed() && window.isMaximized()),
  };
}

function runWindowControlAction(window, action) {
  if (!window || window.isDestroyed()) {
    throw new Error('Window is not available');
  }

  switch (action) {
    case 'minimize':
      window.minimize();
      break;
    case 'toggle-maximize':
      if (window.isMaximized()) {
        window.unmaximize();
      } else {
        window.maximize();
      }
      break;
    case 'close':
      window.close();
      break;
    default:
      throw new Error(`Unknown window action: ${action}`);
  }

  return getWindowControlState(window);
}

module.exports = {
  getWindowControlState,
  runWindowControlAction,
};
