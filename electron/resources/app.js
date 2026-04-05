const ipc = window.api;

// State
let settings = {};
let isRunning = false;
let preflightData = null;

// DOM refs
const $ = (id) => document.getElementById(id);

const dom = {
    backendWarning: $('backendWarning'),
    inputPath: $('inputPath'),
    outputPath: $('outputPath'),
    btnInputFolder: $('btnInputFolder'),
    btnOutputFolder: $('btnOutputFolder'),
    whisperModel: $('whisperModel'),
    whisperLanguage: $('whisperLanguage'),
    diarize: $('diarize'),
    btnRefresh: $('btnRefresh'),
    processAudio: $('processAudio'),
    processVideos: $('processVideos'),
    processPdf: $('processPdf'),
    processImages: $('processImages'),
    processDocx: $('processDocx'),
    processXlsx: $('processXlsx'),
    processPptx: $('processPptx'),
    processTxt: $('processTxt'),
    logArea: $('logArea'),
    emptyState: $('emptyState'),
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
    if (settings.diarize === false || settings.diarize === 'off') {
        dom.diarize.value = 'off';
    } else if (settings.diarizeSpeakers === 0) {
        dom.diarize.value = 'auto';
    } else {
        dom.diarize.value = String(settings.diarizeSpeakers || 2);
    }
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
        inputFolder: settings.inputFolder || '',
        outputFolder: settings.outputFolder || '',
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
dom.whisperModel.addEventListener('change', saveSettings);
dom.whisperLanguage.addEventListener('change', saveSettings);
dom.diarize.addEventListener('change', saveSettings);
dom.processAudio.addEventListener('change', saveSettings);
dom.processVideos.addEventListener('change', saveSettings);
dom.processPdf.addEventListener('change', saveSettings);
dom.processImages.addEventListener('change', saveSettings);
dom.processDocx.addEventListener('change', saveSettings);
dom.processXlsx.addEventListener('change', saveSettings);
dom.processPptx.addEventListener('change', saveSettings);
dom.processTxt.addEventListener('change', saveSettings);

// Folder pickers
dom.btnInputFolder.addEventListener('click', async () => {
    const folder = await ipc.invoke('pick-folder');
    if (folder) {
        settings.inputFolder = folder;
        dom.inputPath.textContent = folder;
        await saveSettings();
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

// === Log display ===

function addLog(message, level = 'info', timestamp = null) {
    if (dom.emptyState) {
        dom.logArea.innerHTML = '';
    }
    const line = document.createElement('div');
    line.className = `log-line ${level.toLowerCase()}`;
    const ts = timestamp || new Date().toLocaleTimeString();
    line.innerHTML = `<span class="timestamp">${ts}</span>${escapeHtml(message)}`;
    dom.logArea.appendChild(line);
    dom.logArea.scrollTop = dom.logArea.scrollHeight;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function clearLog() {
    dom.logArea.innerHTML = '';
}

// === Preflight / Scan ===

function formatTime(minutes) {
    if (minutes < 1) return '<1 min';
    if (minutes < 60) return `${Math.round(minutes)} min`;
    const h = Math.floor(minutes / 60);
    const m = Math.round(minutes % 60);
    return `${h}h ${m}m`;
}

async function runPreflight() {
    if (!settings.inputFolder || !settings.outputFolder) {
        addLog('Select input and output folders first', 'warn');
        return;
    }

    clearLog();
    addLog('Scanning files...');

    // Save config to backend
    const backendConfig = {
        source_directory: settings.inputFolder,
        output_directory: settings.outputFolder,
        whisper_model: settings.whisperModel,
        whisper_language: settings.whisperLanguage,
        whisper_diarize: settings.diarize !== false && settings.diarize !== 'off',
        whisper_diarize_speakers: settings.diarizeSpeakers || 0,
        whisper_beam_size: 1,
        process_audio: settings.processAudio,
        process_videos: settings.processVideos,
        process_pdf: settings.processPdf,
        process_images: settings.processImages,
        process_docx: settings.processDocx,
        process_xlsx: settings.processXlsx,
        process_pptx: settings.processPptx,
        process_txt: settings.processTxt,
        process_csv: false,
        process_rtf: false,
    };

    await ipc.invoke('save-config', backendConfig);
    const result = await ipc.invoke('preflight', backendConfig);

    if (!result || !result.success) {
        addLog(result?.error || 'Preflight failed', 'error');
        return;
    }

    if (result.total_files === 0) {
        addLog(result.message || 'No files to process', 'warn');
        dom.btnStart.disabled = true;
        return;
    }

    preflightData = result;

    // Show preflight card
    clearLog();
    const est = result.estimates;
    let html = '<div class="preflight-card"><h3>Ready to process</h3>';

    if (est.audio.count > 0)
        html += `<div class="preflight-row"><span>Audio</span><span class="count">${est.audio.count} files</span><span class="time">~${formatTime(est.audio.processing_time)}</span></div>`;
    if (est.videos.count > 0)
        html += `<div class="preflight-row"><span>Video</span><span class="count">${est.videos.count} files</span><span class="time">~${formatTime(est.videos.processing_time)}</span></div>`;
    if (est.pdfs.count > 0)
        html += `<div class="preflight-row"><span>PDF</span><span class="count">${est.pdfs.count} files</span><span class="time">~${formatTime(est.pdfs.processing_time)}</span></div>`;
    if (est.images.count > 0)
        html += `<div class="preflight-row"><span>Images</span><span class="count">${est.images.count} files</span><span class="time">~${formatTime(est.images.processing_time)}</span></div>`;
    if (est.documents.count > 0)
        html += `<div class="preflight-row"><span>Documents</span><span class="count">${est.documents.count} files</span><span class="time">~${formatTime(est.documents.processing_time)}</span></div>`;

    html += `<div class="preflight-total"><span>Total: ${result.total_files} files</span><span>~${formatTime(est.total_time)}</span></div>`;
    html += '</div>';

    dom.logArea.innerHTML = html;
    dom.btnStart.disabled = false;
}

dom.btnRefresh.addEventListener('click', () => {
    if (!isRunning) runPreflight();
});

// === Processing ===

dom.btnStart.addEventListener('click', async () => {
    if (isRunning) {
        ipc.send('stop-processing');
        isRunning = false;
        dom.btnStart.textContent = 'Start';
        dom.btnStart.classList.remove('stop');
        addLog('Processing stopped by user', 'warn');
        return;
    }

    if (!settings.inputFolder || !settings.outputFolder) return;

    isRunning = true;
    dom.btnStart.textContent = 'Stop';
    dom.btnStart.classList.add('stop');
    clearLog();
    addLog('Starting processing...');

    const backendConfig = {
        source_directory: settings.inputFolder,
        output_directory: settings.outputFolder,
        whisper_model: settings.whisperModel,
        whisper_language: settings.whisperLanguage,
        whisper_diarize: settings.diarize !== false && settings.diarize !== 'off',
        whisper_diarize_speakers: settings.diarizeSpeakers || 0,
        whisper_beam_size: 1,
        process_audio: settings.processAudio,
        process_videos: settings.processVideos,
        process_pdf: settings.processPdf,
        process_images: settings.processImages,
        process_docx: settings.processDocx,
        process_xlsx: settings.processXlsx,
        process_pptx: settings.processPptx,
        process_txt: settings.processTxt,
        process_csv: false,
        process_rtf: false,
    };

    const result = await ipc.invoke('start-processing', backendConfig);
    if (!result || !result.success) {
        addLog(result?.error || 'Failed to start', 'error');
        isRunning = false;
        dom.btnStart.textContent = 'Start';
        dom.btnStart.classList.remove('stop');
    }
});

// Progress events
ipc.on('processing-progress', (data) => {
    const pct = data.total > 0 ? Math.round(data.current / data.total * 100) : 0;
    dom.overallProgress.textContent = `${data.current}/${data.total} files | ${pct}%`;
});

ipc.on('processing-log', (data) => {
    addLog(data.message, data.level, data.timestamp);
});

ipc.on('processing-complete', (data) => {
    isRunning = false;
    dom.btnStart.textContent = 'Start';
    dom.btnStart.classList.remove('stop');

    const parts = [];
    if (data.audio_processed) parts.push(`${data.audio_processed} audio`);
    if (data.videos_processed) parts.push(`${data.videos_processed} video`);
    if (data.pdfs_processed) parts.push(`${data.pdfs_processed} PDF`);
    if (data.images_processed) parts.push(`${data.images_processed} image`);
    if (data.documents_processed) parts.push(`${data.documents_processed} doc`);
    const total = (data.audio_processed || 0) + (data.videos_processed || 0) +
                  (data.pdfs_processed || 0) + (data.images_processed || 0) + (data.documents_processed || 0);

    let summary = `Done: ${total} transcribed`;
    if (parts.length) summary += ` (${parts.join(', ')})`;
    if (data.errors) summary += ` | ${data.errors} failed`;
    dom.overallProgress.textContent = summary;
    addLog('Processing complete!', 'success');
});

ipc.on('processing-error', (data) => {
    addLog(data.message || 'Unknown error', 'error');
});

// === Init ===

async function checkBackend() {
    try {
        const result = await ipc.invoke('get-status');
        if (result && result.success) {
            dom.backendWarning.style.display = 'none';
            dom.systemInfo.textContent = 'Backend ready';
            return true;
        }
    } catch {}
    dom.backendWarning.style.display = 'block';
    dom.systemInfo.textContent = 'Backend not running';
    return false;
}

(async () => {
    await loadSettings();

    // Poll for backend readiness (server takes a few seconds to start)
    let ready = false;
    for (let i = 0; i < 20; i++) {
        ready = await checkBackend();
        if (ready) break;
        await new Promise(r => setTimeout(r, 1000));
    }

    if (ready && settings.inputFolder && settings.outputFolder) {
        runPreflight();
    }
})();
