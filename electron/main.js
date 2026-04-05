const { app, BrowserWindow, ipcMain, Tray, Menu, Notification, nativeImage, dialog } = require('electron');
const { autoUpdater } = require('electron-updater');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const http = require('http');

// Paths
const IS_PACKAGED = app.isPackaged;
const RESOURCES = path.join(__dirname, 'resources');
const DATA_DIR = IS_PACKAGED ? app.getPath('userData') : __dirname;
const SETTINGS_FILE = path.join(DATA_DIR, 'transcriptor-settings.json');

// The backend lives in the original project directory, not in the installed app.
// In dev mode: ../backend. In packaged mode: stored default or auto-detected.
const PROJECT_ROOT = IS_PACKAGED
    ? 'C:\\Users\\Gaming PC\\Desktop\\Transcriptor v2'
    : path.join(__dirname, '..');
const BACKEND_DIR = path.join(PROJECT_ROOT, 'backend');
const VENV_PYTHON = path.join(BACKEND_DIR, '.venv', 'Scripts', 'python.exe');

const API_PORT = 5000;
const API_BASE = `http://localhost:${API_PORT}`;

let win = null;
let tray = null;
let serverProcess = null;
let sseConnection = null;

// Single instance
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) { app.quit(); return; }
app.on('second-instance', () => { if (win) { win.show(); win.focus(); } });

// === Settings ===

const DEFAULT_SETTINGS = {
    inputFolder: '',
    outputFolder: '',
    whisperModel: 'medium',
    whisperLanguage: '',
    whisperBeamSize: 1,
    diarize: true,
    diarizeSpeakers: 2,
    processAudio: true,
    processVideos: true,
    processPdf: true,
    processImages: true,
    processDocx: true,
    processXlsx: true,
    processPptx: true,
    processTxt: true,
    processCsv: true,
    processRtf: true,
    startWithWindows: false,
};

function readSettings() {
    try { return { ...DEFAULT_SETTINGS, ...JSON.parse(fs.readFileSync(SETTINGS_FILE, 'utf-8')) }; }
    catch { return { ...DEFAULT_SETTINGS }; }
}

function writeSettings(settings) {
    fs.writeFileSync(SETTINGS_FILE, JSON.stringify(settings, null, 2));
}

// === API Server Management ===

function startServer() {
    return new Promise((resolve, reject) => {
        // Check if already running
        httpGet(`${API_BASE}/api/status`).then(() => {
            resolve();  // Already running
        }).catch(() => {
            // Start the Flask server
            const env = { ...process.env, PIPELINE_QUIET: '1' };
            serverProcess = spawn(VENV_PYTHON, [
                path.join(BACKEND_DIR, 'api_server.py')
            ], {
                cwd: BACKEND_DIR,
                env,
                stdio: ['ignore', 'pipe', 'pipe'],
                windowsHide: true,
            });

            serverProcess.on('error', (err) => {
                console.error('[server] Spawn error:', err.message);
                reject(err);
            });

            serverProcess.stderr.on('data', (d) => {
                const msg = d.toString();
                // Flask prints its startup message to stderr
                if (msg.includes('Running on')) {
                    resolve();
                }
            });

            // Poll until server responds (max 30s)
            let attempts = 0;
            const poll = setInterval(() => {
                attempts++;
                httpGet(`${API_BASE}/api/status`).then(() => {
                    clearInterval(poll);
                    resolve();
                }).catch(() => {
                    if (attempts > 60) {
                        clearInterval(poll);
                        reject(new Error('Server failed to start within 30s'));
                    }
                });
            }, 500);
        });
    });
}

function stopServer() {
    if (sseConnection) {
        sseConnection.destroy();
        sseConnection = null;
    }
    if (serverProcess) {
        serverProcess.kill();
        serverProcess = null;
    }
}

function httpGet(url) {
    return new Promise((resolve, reject) => {
        const req = http.get(url, { timeout: 3000 }, (res) => {
            let data = '';
            res.on('data', (d) => data += d);
            res.on('end', () => {
                try { resolve(JSON.parse(data)); }
                catch { resolve(data); }
            });
        });
        req.on('error', reject);
        req.on('timeout', () => { req.destroy(); reject(new Error('Timeout')); });
    });
}

function httpPost(url, body) {
    return new Promise((resolve, reject) => {
        const payload = JSON.stringify(body);
        const urlObj = new URL(url);
        const req = http.request({
            hostname: urlObj.hostname,
            port: urlObj.port,
            path: urlObj.pathname,
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) },
            timeout: 5000,
        }, (res) => {
            let data = '';
            res.on('data', (d) => data += d);
            res.on('end', () => {
                try { resolve(JSON.parse(data)); }
                catch { resolve(data); }
            });
        });
        req.on('error', reject);
        req.on('timeout', () => { req.destroy(); reject(new Error('Timeout')); });
        req.write(payload);
        req.end();
    });
}

// === SSE listener for real-time progress ===

function connectSSE() {
    if (sseConnection) sseConnection.destroy();

    const req = http.get(`${API_BASE}/api/events`, (res) => {
        sseConnection = res;
        let buffer = '';

        res.on('data', (chunk) => {
            buffer += chunk.toString();
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        if (data.type === 'progress') {
                            win?.webContents.send('processing-progress', data.data);
                        } else if (data.type === 'log') {
                            win?.webContents.send('processing-log', data.data);
                        } else if (data.type === 'complete') {
                            win?.webContents.send('processing-complete', data.data);
                        }
                    } catch {}
                }
            }
        });

        res.on('end', () => {
            sseConnection = null;
            // Reconnect after 2s
            setTimeout(connectSSE, 2000);
        });
    });

    req.on('error', () => {
        sseConnection = null;
        setTimeout(connectSSE, 2000);
    });
}

// === IPC Handlers ===

ipcMain.handle('get-config', async () => {
    try {
        const result = await httpGet(`${API_BASE}/api/config`);
        return result;
    } catch (err) {
        return { success: false, error: err.message };
    }
});

ipcMain.handle('save-config', async (_, config) => {
    try {
        return await httpPost(`${API_BASE}/api/config`, config);
    } catch (err) {
        return { success: false, error: err.message };
    }
});

ipcMain.handle('preflight', async (_, config) => {
    try {
        return await httpPost(`${API_BASE}/api/preflight`, config);
    } catch (err) {
        return { success: false, error: err.message };
    }
});

ipcMain.handle('start-processing', async (_, config) => {
    try {
        connectSSE();
        return await httpPost(`${API_BASE}/api/start`, config);
    } catch (err) {
        return { success: false, error: err.message };
    }
});

ipcMain.handle('get-status', async () => {
    try {
        return await httpGet(`${API_BASE}/api/status`);
    } catch (err) {
        return { success: false, error: err.message };
    }
});

ipcMain.on('stop-processing', () => {
    // Kill the server process to stop processing
    stopServer();
    // Restart for next use
    startServer().catch(() => {});
});

ipcMain.handle('pick-folder', async () => {
    const result = await dialog.showOpenDialog(win, { properties: ['openDirectory'] });
    if (result.canceled || result.filePaths.length === 0) return null;
    return result.filePaths[0];
});

ipcMain.handle('read-settings', () => readSettings());

ipcMain.handle('write-settings', (_, settings) => {
    writeSettings(settings);
    return true;
});

// === Window ===

function createWindow() {
    win = new BrowserWindow({
        width: 950,
        height: 700,
        minWidth: 750,
        minHeight: 550,
        show: false,
        backgroundColor: '#111111',
        icon: path.join(RESOURCES, 'icon.png'),
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, 'preload.js'),
        },
    });

    win.loadFile(path.join(RESOURCES, 'index.html'));
    win.once('ready-to-show', () => win.show());
    win.on('close', (e) => {
        if (!app.isQuitting) { e.preventDefault(); win.hide(); }
    });
}

// === Tray ===

function createTray() {
    let icon;
    try {
        icon = nativeImage.createFromPath(path.join(RESOURCES, 'icon.png')).resize({ width: 16, height: 16 });
    } catch {
        icon = nativeImage.createEmpty();
    }
    tray = new Tray(icon);
    tray.setToolTip('Transcriptor');

    const rebuildMenu = () => {
        const prefs = readSettings();
        tray.setContextMenu(Menu.buildFromTemplate([
            { label: 'Show / Hide', click: () => { win?.isVisible() ? win.hide() : (win.show(), win.focus()); } },
            { type: 'separator' },
            {
                label: 'Start with Windows',
                type: 'checkbox',
                checked: prefs.startWithWindows,
                click: (item) => {
                    const s = readSettings();
                    s.startWithWindows = item.checked;
                    writeSettings(s);
                    app.setLoginItemSettings({ openAtLogin: item.checked, path: process.execPath });
                }
            },
            { type: 'separator' },
            { label: 'Quit', click: () => { app.isQuitting = true; app.quit(); } },
        ]));
    };

    tray.on('click', () => { win?.isVisible() ? win.hide() : (win.show(), win.focus()); });
    rebuildMenu();
}

// === Auto-updater ===

autoUpdater.autoDownload = true;
autoUpdater.autoInstallOnAppQuit = true;

autoUpdater.on('update-downloaded', (info) => {
    if (Notification.isSupported()) {
        new Notification({
            title: 'Transcriptor Update Ready',
            body: `Version ${info.version} will install on next restart.`,
        }).show();
    }
});

autoUpdater.on('error', (err) => {
    console.error('Auto-update error:', err.message);
});

// === App lifecycle ===

app.whenReady().then(async () => {
    createTray();
    createWindow();

    const prefs = readSettings();
    if (prefs.startWithWindows) {
        app.setLoginItemSettings({ openAtLogin: true, path: process.execPath });
    }

    // Start the Flask API server
    try {
        await startServer();
        win?.webContents.send('processing-log', { message: 'Backend ready', level: 'INFO' });
    } catch (err) {
        console.error('Failed to start backend:', err.message);
    }

    if (IS_PACKAGED) {
        setTimeout(() => autoUpdater.checkForUpdates().catch(() => {}), 5000);
    }
});

app.on('window-all-closed', (e) => e.preventDefault());

app.on('before-quit', () => {
    stopServer();
});
