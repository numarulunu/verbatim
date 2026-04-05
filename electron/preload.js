const { contextBridge, ipcRenderer, shell } = require('electron');

contextBridge.exposeInMainWorld('api', {
    send: (channel, data) => {
        const allowed = ['minimize', 'close', 'stop-processing'];
        if (allowed.includes(channel)) ipcRenderer.send(channel, data);
    },
    invoke: (channel, data) => {
        const allowed = ['get-config', 'save-config', 'start-processing', 'get-status',
                         'pick-folder', 'read-settings', 'write-settings', 'preflight'];
        if (allowed.includes(channel)) return ipcRenderer.invoke(channel, data);
    },
    on: (channel, callback) => {
        const allowed = ['processing-progress', 'processing-log', 'processing-complete', 'processing-error'];
        if (allowed.includes(channel)) {
            ipcRenderer.on(channel, (_, data) => callback(data));
        }
    },
    removeAllListeners: (channel) => {
        ipcRenderer.removeAllListeners(channel);
    },
    openExternal: (url) => {
        shell.openExternal(url);
    },
});
