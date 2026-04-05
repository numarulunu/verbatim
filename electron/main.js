const { app, BrowserWindow, ipcMain, Tray, Menu, Notification, nativeImage, dialog, shell } = require('electron');
const { autoUpdater } = require('electron-updater');
const { spawn, execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const readline = require('readline');

// Paths
const IS_PACKAGED = app.isPackaged;
const RESOURCES = path.join(__dirname, 'resources');
const PROJECT_ROOT = IS_PACKAGED
    ? 'C:\\Users\\Gaming PC\\Desktop\\Transcriptor v2'
    : path.join(__dirname, '..');
const VENV_PYTHON = path.join(PROJECT_ROOT, 'backend', '.venv', 'Scripts', 'python.exe');
const BRIDGE = path.join(IS_PACKAGED ? path.dirname(app.getPath('exe')) : __dirname, 'bridge.py');
const DATA_DIR = IS_PACKAGED ? app.getPath('userData') : __dirname;
const SETTINGS_FILE = path.join(DATA_DIR, 'transcriptor-settings.json');

let win = null;
let tray = null;
let engineProcess = null;

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
    startWithWindows: false,
};

function readSettings() {
    try { return { ...DEFAULT_SETTINGS, ...JSON.parse(fs.readFileSync(SETTINGS_FILE, 'utf-8')) }; }
    catch { return { ...DEFAULT_SETTINGS }; }
}

function writeSettings(settings) {
    fs.writeFileSync(SETTINGS_FILE, JSON.stringify(settings, null, 2));
}

// === Engine communication ===

function runBridge(args) {
    return spawn(VENV_PYTHON, [BRIDGE, ...args], {
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true,
    });
}

function runBridgeAsync(args) {
    return new Promise((resolve, reject) => {
        const proc = runBridge(args);
        let stdout = '';
        let stderr = '';
        proc.stdout.on('data', (d) => { stdout += d.toString(); });
        proc.stderr.on('data', (d) => { stderr += d.toString(); });
        proc.on('close', (code) => {
            if (code === 0) resolve(stdout.trim());
            else reject(new Error(stderr.substring(0, 500) || `Exit code ${code}`));
        });
        proc.on('error', reject);
    });
}

function writeJobFile(data) {
    const jobFile = path.join(DATA_DIR, 'current-job.json');
    fs.writeFileSync(jobFile, JSON.stringify(data, null, 2), 'utf-8');
    return jobFile;
}

// === IPC Handlers ===

ipcMain.handle('detect-system', async () => {
    try {
        const raw = await runBridgeAsync(['--detect']);
        return JSON.parse(raw);
    } catch (err) {
        return { error: err.message, whisper: false, cuda: false, tesseract: false };
    }
});

ipcMain.handle('scan-files', async (_, { inputFolder, outputFolder }) => {
    try {
        const jobFile = writeJobFile({ input: inputFolder, output: outputFolder });
        const raw = await runBridgeAsync(['--scan', '--job', jobFile]);
        return JSON.parse(raw);
    } catch (err) {
        return { files: [], done: [], error: err.message };
    }
});

ipcMain.handle('start-processing', async (_, settings) => {
    if (engineProcess) return { error: 'Already running' };

    const jobFile = writeJobFile({
        input: settings.inputFolder,
        output: settings.outputFolder,
        whisperModel: settings.whisperModel,
        whisperLanguage: settings.whisperLanguage,
        whisperBeamSize: settings.whisperBeamSize || 1,
        diarize: settings.diarize,
        diarizeSpeakers: settings.diarizeSpeakers || 0,
        processAudio: settings.processAudio,
        processVideos: settings.processVideos,
        processPdf: settings.processPdf,
        processImages: settings.processImages,
        processDocx: settings.processDocx,
        processXlsx: settings.processXlsx,
        processPptx: settings.processPptx,
        processTxt: settings.processTxt,
        files: settings.selectedFiles || [],
    });

    engineProcess = runBridge(['--run', '--job', jobFile]);

    const rl = readline.createInterface({ input: engineProcess.stdout });
    rl.on('line', (line) => {
        try {
            const data = JSON.parse(line);
            if (data.type === 'file_done') {
                win?.webContents.send('processing-file-done', data);
            } else if (data.type === 'batch_done') {
                win?.webContents.send('processing-batch-done', data);
            } else if (data.type === 'status') {
                win?.webContents.send('processing-status', data);
            } else if (data.type === 'error') {
                win?.webContents.send('processing-error', data);
            }
        } catch {}
    });

    engineProcess.stderr.on('data', (d) => {
        // Whisper/torch prints warnings to stderr — ignore
    });

    engineProcess.on('close', () => {
        engineProcess = null;
    });

    engineProcess.on('error', (err) => {
        win?.webContents.send('processing-error', { message: err.message });
        engineProcess = null;
    });

    return { started: true };
});

ipcMain.on('stop-processing', () => {
    if (engineProcess) {
        try {
            execSync(`taskkill /PID ${engineProcess.pid} /T /F`, { windowsHide: true, stdio: 'ignore' });
        } catch {}
        engineProcess = null;
    }
});

ipcMain.handle('delete-files', async (_, filePaths) => {
    const deleted = [];
    const failed = [];
    for (const fp of filePaths) {
        try {
            await shell.trashItem(fp);
            deleted.push(fp);
        } catch (err) {
            failed.push({ path: fp, error: err.message });
        }
    }
    return { deleted: deleted.length, failed };
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

app.whenReady().then(() => {
    createTray();
    createWindow();

    const prefs = readSettings();
    if (prefs.startWithWindows) {
        app.setLoginItemSettings({ openAtLogin: true, path: process.execPath });
    }

    if (IS_PACKAGED) {
        setTimeout(() => autoUpdater.checkForUpdates().catch(() => {}), 5000);
    }
});

app.on('window-all-closed', (e) => e.preventDefault());

app.on('before-quit', () => {
    if (engineProcess) {
        try {
            execSync(`taskkill /PID ${engineProcess.pid} /T /F`, { windowsHide: true, stdio: 'ignore' });
        } catch {}
        engineProcess = null;
    }
});
