const ipc = window.api;

let settings = {};
let files = [];
let isRunning = false;
let systemInfo = null;

const $ = (id) => document.getElementById(id);

const dom = {
    inputPath: $('inputPath'),
    outputPath: $('outputPath'),
    btnInputFolder: $('btnInputFolder'),
    btnOutputFolder: $('btnOutputFolder'),
    whisperModel: $('whisperModel'),
    whisperLanguage: $('whisperLanguage'),
    diarize: $('diarize'),
    processAudio: $('processAudio'),
    processVideos: $('processVideos'),
    processPdf: $('processPdf'),
    processImages: $('processImages'),
    processDocx: $('processDocx'),
    processXlsx: $('processXlsx'),
    processPptx: $('processPptx'),
    processTxt: $('processTxt'),
    btnRefresh: $('btnRefresh'),
    queueHeader: $('queueHeader'),
    selectAll: $('selectAll'),
    fileCount: $('fileCount'),
    fileQueue: $('fileQueue'),
    systemInfo: $('systemInfo'),
    overallProgress: $('overallProgress'),
    btnStart: $('btnStart'),
};

// === Settings ===

async function loadSettings() {
    settings = await ipc.invoke('read-settings');
    dom.inputPath.textContent = settings.inputFolder || 'No folder selected';
    dom.outputPath.textContent = settings.outputFolder || 'No folder selected';
    dom.whisperModel.value = settings.whisperModel || 'medium';
    dom.whisperLanguage.value = settings.whisperLanguage || '';
    if (settings.diarize === false) dom.diarize.value = 'off';
    else if (settings.diarizeSpeakers === 0) dom.diarize.value = 'auto';
    else dom.diarize.value = String(settings.diarizeSpeakers || 2);
    dom.processAudio.checked = settings.processAudio !== false;
    dom.processVideos.checked = settings.processVideos !== false;
    dom.processPdf.checked = settings.processPdf !== false;
    dom.processImages.checked = settings.processImages !== false;
    dom.processDocx.checked = settings.processDocx !== false;
    dom.processXlsx.checked = settings.processXlsx !== false;
    dom.processPptx.checked = settings.processPptx !== false;
    dom.processTxt.checked = settings.processTxt !== false;
}

async function saveSettings() {
    const diarizeVal = dom.diarize.value;
    settings = {
        ...settings,
        whisperModel: dom.whisperModel.value,
        whisperLanguage: dom.whisperLanguage.value,
        diarize: diarizeVal !== 'off',
        diarizeSpeakers: diarizeVal === 'off' ? 0 : diarizeVal === 'auto' ? 0 : parseInt(diarizeVal),
        processAudio: dom.processAudio.checked,
        processVideos: dom.processVideos.checked,
        processPdf: dom.processPdf.checked,
        processImages: dom.processImages.checked,
        processDocx: dom.processDocx.checked,
        processXlsx: dom.processXlsx.checked,
        processPptx: dom.processPptx.checked,
        processTxt: dom.processTxt.checked,
    };
    await ipc.invoke('write-settings', settings);
}

// Change handlers
[dom.whisperModel, dom.whisperLanguage, dom.diarize,
 dom.processAudio, dom.processVideos, dom.processPdf, dom.processImages,
 dom.processDocx, dom.processXlsx, dom.processPptx, dom.processTxt].forEach(el => {
    el.addEventListener('change', saveSettings);
});

// Folder pickers
dom.btnInputFolder.addEventListener('click', async () => {
    const folder = await ipc.invoke('pick-folder');
    if (folder) {
        settings.inputFolder = folder;
        dom.inputPath.textContent = folder;
        await saveSettings();
        scanFiles();
    }
});

dom.btnOutputFolder.addEventListener('click', async () => {
    const folder = await ipc.invoke('pick-folder');
    if (folder) {
        settings.outputFolder = folder;
        dom.outputPath.textContent = folder;
        await saveSettings();
    }
});

// === Helpers ===

function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    return (bytes / (1024 * 1024 * 1024)).toFixed(1) + ' GB';
}

function formatTime(seconds) {
    if (!seconds || seconds < 0) return '0s';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
}

function formatDuration(seconds) {
    if (!seconds || seconds <= 0) return '';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
    return `${m}:${String(s).padStart(2,'0')}`;
}

function statusIcon(status) {
    switch (status) {
        case 'pending': return '\u2022';
        case 'processing': return '\u25CB';
        case 'done': return '\u2713';
        case 'already_done': return '\u2713';
        case 'failed': return '\u2717';
        default: return '\u2022';
    }
}

function typeLabel(type) {
    const labels = { audio: '\u266B', video: '\u25B6', pdf: '\u25A0', image: '\u25CF', document: '\u25A1' };
    return labels[type] || '';
}

// === File Queue ===

function renderFiles() {
    if (files.length === 0) {
        dom.fileQueue.innerHTML = '<div class="empty-state">No files found</div>';
        dom.queueHeader.style.display = 'none';
        dom.btnStart.disabled = true;
        return;
    }

    // Group into sections
    const pending = [];
    const completed = [];
    const alreadyDone = [];
    files.forEach((f, i) => {
        f._idx = i;
        if (f.status === 'done' || f.status === 'failed') completed.push(f);
        else if (f.status === 'already_done') alreadyDone.push(f);
        else pending.push(f);
    });

    // Header
    const selectedFiles = pending.filter(f => f.selected !== false);
    const totalSize = selectedFiles.reduce((s, f) => s + (f.size || 0), 0);
    dom.queueHeader.style.display = 'flex';
    let summary = `${selectedFiles.length} to process`;
    if (alreadyDone.length > 0) summary += ` | ${alreadyDone.length} already done`;
    if (totalSize > 0) summary += ` | ${formatSize(totalSize)}`;
    dom.fileCount.textContent = summary;


    function renderRow(f) {
        const i = f._idx;
        const durStr = formatDuration(f.duration);
        const resultText = f.resultText || (f.status === 'already_done' ? `Already done (${formatSize(f.output_size || 0)})` : '');
        const rowClass = f.status === 'already_done' ? 'file-row already_done' : f.status === 'done' ? 'file-row' : 'file-row';
        const cbDisabled = (f.status !== 'pending' && f.status !== 'already_done') ? 'disabled' : '';

        return `
        <div class="${rowClass}" id="file-${i}">
            <input type="checkbox" class="file-check" id="check-${i}" ${f.selected !== false ? 'checked' : ''} ${cbDisabled}>
            <div class="file-status ${f.status}" id="status-${i}">${statusIcon(f.status)}</div>
            <div class="file-type dim">${typeLabel(f.type)}</div>
            <div class="file-name">${f.name}</div>
            <div class="file-duration dim">${durStr}</div>
            <div class="file-size">${formatSize(f.size)}</div>
            <div class="file-result ${f.status === 'failed' ? 'failed' : ''}" id="result-${i}">${resultText}</div>
        </div>`;
    }

    let html = '';
    if (pending.length > 0) html += pending.map(renderRow).join('');
    if (completed.length > 0) {
        html += `<div class="section-divider">Completed (${completed.length})</div>`;
        html += completed.map(renderRow).join('');
    }
    if (alreadyDone.length > 0) {
        html += `<div class="section-divider">Already transcribed (${alreadyDone.length})</div>`;
        html += alreadyDone.map(renderRow).join('');
    }
    dom.fileQueue.innerHTML = html;

    // Checkbox handlers
    files.forEach((f, i) => {
        const cb = document.getElementById(`check-${i}`);
        if (cb) cb.addEventListener('change', () => {
            f.selected = cb.checked;
            if (cb.checked && f.status === 'already_done') {
                f.status = 'pending';
                const row = document.getElementById(`file-${i}`);
                if (row) row.className = 'file-row';
                const el = document.getElementById(`result-${i}`);
                if (el) el.textContent = 'Will re-transcribe';
            } else if (!cb.checked && f._wasDone) {
                f.status = 'already_done';
                const row = document.getElementById(`file-${i}`);
                if (row) row.className = 'file-row already_done';
                const el = document.getElementById(`result-${i}`);
                if (el) el.textContent = `Already done (${formatSize(f.output_size || 0)})`;
            }
            updateStartButton();
        });
    });

    updateStartButton();
}

function updateStartButton() {
    if (isRunning) { dom.btnStart.disabled = false; return; }
    dom.btnStart.disabled = !files.some(f => f.status === 'pending' && f.selected !== false);
}

// === Scan ===

async function scanFiles() {
    if (!settings.inputFolder) {
        dom.fileQueue.innerHTML = '<div class="empty-state">Select an Input folder first</div>';
        return;
    }
    if (!settings.outputFolder) {
        dom.fileQueue.innerHTML = '<div class="empty-state">Select an Output folder first</div>';
        return;
    }

    dom.fileQueue.innerHTML = '<div class="empty-state">Scanning...</div>';

    const result = await ipc.invoke('scan-files', {
        inputFolder: settings.inputFolder,
        outputFolder: settings.outputFolder,
    });

    if (result.error) {
        dom.fileQueue.innerHTML = `<div class="empty-state">Error: ${result.error}</div>`;
        return;
    }

    files = (result.files || []).map(f => ({
        ...f,
        status: 'pending',
        resultText: '',
        selected: true,
    }));

    const doneFiles = (result.done || []).map(f => ({
        ...f,
        status: 'already_done',
        resultText: `Already done (${formatSize(f.output_size || 0)})`,
        selected: false,
        _wasDone: true,
    }));
    files = [...files, ...doneFiles];

    renderFiles();
}

dom.btnRefresh.addEventListener('click', () => {
    if (!isRunning) scanFiles();
});

dom.selectAll.addEventListener('change', () => {
    const checked = dom.selectAll.checked;
    files.forEach((f, i) => {
        if (f.status === 'pending') {
            f.selected = checked;
            const cb = document.getElementById(`check-${i}`);
            if (cb) cb.checked = checked;
        }
    });
    updateStartButton();
});

// === Processing ===

dom.btnStart.addEventListener('click', async () => {
    if (isRunning) {
        ipc.send('stop-processing');
        isRunning = false;
        dom.btnStart.textContent = 'Start';
        dom.btnStart.classList.remove('stop');
        return;
    }

    if (!settings.inputFolder || !settings.outputFolder) return;

    isRunning = true;
    dom.btnStart.textContent = 'Stop';
    dom.btnStart.classList.add('stop');
    dom.overallProgress.textContent = 'Starting...';

    const selectedNames = [];
    files.forEach(f => {
        if (f.selected !== false && f.status === 'pending') {
            f.resultText = '';
            selectedNames.push(f.name);
        }
    });
    renderFiles();

    try {
        const payload = { ...settings, selectedFiles: selectedNames };
        dom.overallProgress.textContent = `Starting (${selectedNames.length} files)...`;
        const result = await ipc.invoke('start-processing', payload);
        if (result && result.error) {
            isRunning = false;
            dom.btnStart.textContent = 'Start';
            dom.btnStart.classList.remove('stop');
            dom.overallProgress.textContent = `Error: ${result.error}`;
        }
    } catch (err) {
        isRunning = false;
        dom.btnStart.textContent = 'Start';
        dom.btnStart.classList.remove('stop');
        dom.overallProgress.textContent = `Error: ${err.message || err}`;
    }
});

// === Progress Events ===

ipc.on('processing-status', (data) => {
    dom.overallProgress.textContent = data.message;
});

ipc.on('processing-file-done', (data) => {
    const idx = files.findIndex(f => f.name === data.file);
    if (idx >= 0) {
        files[idx].status = data.success ? 'done' : 'failed';
        files[idx].resultText = data.success ? `Done [${formatTime(data.elapsed_seconds)}]` : 'Failed';

        const statusEl = document.getElementById(`status-${idx}`);
        const resultEl = document.getElementById(`result-${idx}`);
        if (statusEl) {
            statusEl.className = `file-status ${files[idx].status}`;
            statusEl.textContent = statusIcon(files[idx].status);
        }
        if (resultEl) {
            resultEl.className = `file-result ${files[idx].status === 'failed' ? 'failed' : ''}`;
            resultEl.textContent = files[idx].resultText;
        }
    }

    // Update overall
    dom.overallProgress.textContent = `${data.done}/${data.total} files | ${data.percent}% | ETA ${formatTime(data.eta_seconds)}`;
});

ipc.on('processing-batch-done', (data) => {
    isRunning = false;
    dom.btnStart.textContent = 'Start';
    dom.btnStart.classList.remove('stop');

    let summary = `${data.processed} transcribed`;
    if (data.failed > 0) summary += `, ${data.failed} failed`;
    summary += ` | ${formatTime(data.elapsed_seconds)}`;
    dom.overallProgress.textContent = summary;

    renderFiles();
});

ipc.on('processing-error', (data) => {
    isRunning = false;
    dom.btnStart.textContent = 'Start';
    dom.btnStart.classList.remove('stop');
    dom.overallProgress.textContent = `Error: ${data.message}`;
});


// === System Detection ===

async function detectSystem() {
    systemInfo = await ipc.invoke('detect-system');

    if (systemInfo.error) {
        dom.systemInfo.textContent = `Backend error: ${systemInfo.error}`;
        return;
    }

    let info = '';
    if (systemInfo.cuda) info += `GPU: ${systemInfo.gpu_name} | `;
    else info += 'CPU only | ';
    info += systemInfo.whisper ? 'Whisper ready' : 'Whisper not found';
    if (systemInfo.tesseract) info += ' | OCR ready';
    dom.systemInfo.textContent = info;
    dom.btnStart.disabled = files.length === 0;
}

// === Init ===

(async () => {
    await loadSettings();
    await detectSystem();
    if (settings.inputFolder && settings.outputFolder) {
        await scanFiles();
    }
})();
