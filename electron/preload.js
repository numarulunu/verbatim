const { contextBridge, ipcRenderer, shell } = require('electron');

contextBridge.exposeInMainWorld('api', {
    send: (channel, data) => {
        const allowed = ['stop-processing'];
        if (allowed.includes(channel)) ipcRenderer.send(channel, data);
    },
    invoke: (channel, data) => {
        const allowed = ['detect-system', 'scan-files', 'start-processing', 'pick-folder',
                         'read-settings', 'write-settings', 'delete-files'];
        if (allowed.includes(channel)) return ipcRenderer.invoke(channel, data);
    },
    on: (channel, callback) => {
        const allowed = ['processing-file-done', 'processing-batch-done', 'processing-status', 'processing-error'];
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
