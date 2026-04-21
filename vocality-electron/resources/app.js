/**
 * Vocality renderer — dispatcher + view rendering.
 *
 * - state is owned by the module-level `state` variable
 * - incoming daemon events flow through appState.reduceEvent
 * - UI actions (tab clicks, form submits) dispatch through setView or
 *   custom patches
 * - render() is idempotent; called after every dispatch
 *
 * All daemon IO goes through window.vocality.* (preload bridge).
 */
'use strict';

(() => {
  if (!window.vocality) {
    document.body.innerHTML =
      '<main style="padding:24px;color:#b06a6a">ERROR: preload not wired — window.vocality is missing.</main>';
    return;
  }
  if (!window.appState) {
    document.body.innerHTML =
      '<main style="padding:24px;color:#b06a6a">ERROR: app-state.js not loaded before app.js.</main>';
    return;
  }

  const { initialState, reduceEvent, setView } = window.appState;

  let state = initialState();

  function dispatch(patch) {
    state = typeof patch === 'function' ? patch(state) : patch;
    render();
  }

  // Generate an id for correlating responses to commands.
  let _cmdCounter = 0;
  function nextId(prefix) { return `${prefix}-${Date.now()}-${++_cmdCounter}`; }

  // ── DOM refs ────────────────────────────────────────────────────────

  const statusDot = document.querySelector('.status-dot');
  const statusLabel = document.querySelector('.status-label');
  const statusVersion = document.querySelector('.status-version');
  const statusLastError = document.querySelector('.status-last-error');
  const statusUpdate = document.querySelector('.status-update');
  const tabs = Array.from(document.querySelectorAll('.tab'));
  const views = Array.from(document.querySelectorAll('.view'));

  // Batch view
  const batchView = document.querySelector('.view[data-view="batch"]');
  const scanPathInput = batchView.querySelector('.scan-path');
  const scanBtn = batchView.querySelector('[data-action="scan"]');
  const startBtn = batchView.querySelector('[data-action="start"]');
  const cancelBtn = batchView.querySelector('[data-action="cancel"]');
  const batchSummary = batchView.querySelector('.batch-summary');
  const batchFilesEl = batchView.querySelector('.batch-files');
  const fileRowTmpl = document.getElementById('file-row-template');

  // Registry view
  const registryView = document.querySelector('.view[data-view="registry"]');
  const refreshPersonsBtn = registryView.querySelector('[data-action="refresh-persons"]');
  const registrySummary = registryView.querySelector('.registry-summary');
  const personsRowsEl = registryView.querySelector('.persons-rows');
  const collisionsPanel = registryView.querySelector('.collisions-panel');
  const collisionsList = registryView.querySelector('.collisions-list');
  const inspectEmpty = registryView.querySelector('.inspect-empty');
  const inspectDetail = registryView.querySelector('.inspect-detail');
  const inspectIdEl = registryView.querySelector('.inspect-id');
  const inspectDisplayEl = registryView.querySelector('.inspect-display');
  const inspectFields = registryView.querySelector('.inspect-fields');
  const vpList = registryView.querySelector('.vp-list');
  const editBtn = registryView.querySelector('[data-action="edit-person"]');
  const renameBtn = registryView.querySelector('[data-action="rename-person"]');
  const mergeBtn = registryView.querySelector('[data-action="merge-person"]');

  // Redo view
  const redoView = document.querySelector('.view[data-view="redo"]');
  const redoFilter = redoView.querySelector('.redo-filter');
  const redoFindBtn = redoView.querySelector('[data-action="redo-find"]');
  const redoRunBtn = redoView.querySelector('[data-action="redo-run"]');
  const redoCancelBtn = redoView.querySelector('[data-action="redo-cancel"]');
  const redoSummary = redoView.querySelector('.redo-summary');
  const redoFilesEl = redoView.querySelector('.redo-files');

  // Header actions
  const settingsBtn = document.querySelector('[data-action="open-settings"]');

  // Modal
  const modalEl = document.querySelector('.modal');
  const modalTitle = modalEl.querySelector('.modal-title');
  const modalBody = modalEl.querySelector('.modal-body');
  const modalCloseBtn = modalEl.querySelector('.modal-close');
  const modalCancelBtn = modalEl.querySelector('[data-action="modal-cancel"]');
  const modalSubmitBtn = modalEl.querySelector('[data-action="modal-submit"]');

  let modalOnSubmit = null;
  let activePersonId = null;
  let updateStatus = null;

  // ── Rendering ──────────────────────────────────────────────────────

  function render() {
    renderTabs();
    renderStatusBar();
    renderBatchView();
    renderRegistryView();
    renderRedoView();
  }

  function renderTabs() {
    for (const tab of tabs) {
      const isActive = tab.dataset.view === state.view;
      tab.classList.toggle('active', isActive);
      tab.setAttribute('aria-selected', String(isActive));
    }
    for (const v of views) v.hidden = v.dataset.view !== state.view;
  }

  function renderStatusBar() {
    statusDot.dataset.status = state.daemon.status;
    statusLabel.textContent = `daemon: ${state.daemon.status}`;
    statusVersion.textContent = state.daemon.version ? `v${state.daemon.version}` : '';
    const lastError = state.errors[state.errors.length - 1];
    statusLastError.textContent = lastError
      ? `${lastError.error_type}: ${lastError.message}`
      : '';

    // Update channel. Dev mode never fires these — the span stays blank.
    if (!updateStatus) {
      statusUpdate.textContent = '';
    } else {
      switch (updateStatus.kind) {
        case 'checking':     statusUpdate.textContent = 'checking for update…'; break;
        case 'current':      statusUpdate.textContent = ''; break;
        case 'available':    statusUpdate.textContent = `update v${updateStatus.version} available`; break;
        case 'downloading':  statusUpdate.textContent = `downloading update ${Math.round(updateStatus.percent || 0)}%`; break;
        case 'downloaded':   statusUpdate.textContent = `update v${updateStatus.version} ready — restart to install`; break;
        case 'error':        statusUpdate.textContent = `update error: ${updateStatus.message || ''}`; break;
        default:             statusUpdate.textContent = '';
      }
    }
  }

  function renderBatchView() {
    // Button availability
    const daemonReady = state.daemon.status === 'ready';
    const running = state.batch.status === 'running' || state.batch.status === 'cancelling';
    const scanned = state.batch.scan.files;
    const filesToRun = state.batch.files.length > 0 ? state.batch.files : scanned;

    scanBtn.disabled = !daemonReady || running;
    startBtn.disabled = !daemonReady || running || (scanned.length === 0 && state.batch.files.length === 0);
    cancelBtn.disabled = !running;

    // Summary
    const s = state.batch;
    if (s.status === 'running' || s.status === 'cancelling') {
      batchSummary.textContent =
        `running · ${(s.currentFileIndex + 1)}/${s.files.length}`;
    } else if (s.status === 'complete' || s.status === 'failed' || s.status === 'cancelled') {
      batchSummary.textContent =
        `${s.status} · ${s.successful} ok / ${s.failed} failed · ${s.elapsed_s.toFixed(1)}s`;
    } else if (scanned.length > 0) {
      batchSummary.textContent = `${scanned.length} file(s) scanned`;
    } else {
      batchSummary.textContent = '';
    }

    // File rows. During a batch, render state.batch.files (live).
    // Before starting, render scanned files as pending rows.
    const rows = running || s.files.length > 0
      ? state.batch.files.map((f, i) => ({
          path: f.path,
          index: i,
          phase: f.phase,
          phase_progress: f.phase_progress ?? 0,
          completed_phases: f.completed_phases,
          status: f.status,
        }))
      : scanned.map((f, i) => ({
          path: f.path || f.name || '',
          index: i,
          phase: null,
          phase_progress: 0,
          completed_phases: [],
          status: 'pending',
        }));

    // Diff-free replace — few files, cheap enough to re-render.
    batchFilesEl.innerHTML = '';
    for (const row of rows) {
      const el = fileRowTmpl.content.firstElementChild.cloneNode(true);
      el.dataset.index = String(row.index);
      el.dataset.status = row.status || 'pending';
      el.querySelector('.file-name').textContent = basename(row.path);
      el.querySelector('.file-name').title = row.path;
      el.querySelector('.file-phase').textContent = row.phase
        ? `${row.phase} (${row.completed_phases.length}/10)`
        : '—';
      const bar = el.querySelector('.file-progress-bar');
      // Compute overall progress: completed/10 + (phase_progress / 10) of the current phase.
      const completed = row.completed_phases.length;
      const overall = Math.min(1, completed / 10 + (row.phase_progress || 0) / 10);
      bar.style.width = `${Math.round(overall * 100)}%`;
      el.querySelector('.file-progress-label').textContent = row.phase_progress > 0
        ? `${Math.round(row.phase_progress * 100)}%`
        : '';
      el.querySelector('.file-status').textContent = (row.status || 'pending').replace('_', ' ');
      batchFilesEl.appendChild(el);
    }
  }

  function renderRegistryView() {
    const persons = state.registry.persons;
    registrySummary.textContent = persons.length === 0
      ? ''
      : `${persons.length} person${persons.length === 1 ? '' : 's'}`;

    // Row list — plain DOM rewrite (small N).
    personsRowsEl.innerHTML = '';
    for (const p of persons) {
      const row = document.createElement('div');
      row.className = 'person-row';
      row.dataset.personId = p.id;
      if (p.id === activePersonId) row.classList.add('active');
      const cells = [
        p.id,
        p.display_name || '—',
        p.default_role || '—',
        `${p.n_sessions_as_teacher || 0}/${p.n_sessions_as_student || 0}`,
      ];
      for (let i = 0; i < cells.length; i++) {
        const span = document.createElement('span');
        if (i === 3) span.className = 'sessions-col';
        span.textContent = cells[i];
        row.appendChild(span);
      }
      row.addEventListener('click', () => selectPerson(p.id));
      personsRowsEl.appendChild(row);
    }

    // Collisions
    const collisions = state.registry.collisions;
    collisionsPanel.hidden = collisions.length === 0;
    collisionsList.innerHTML = '';
    for (const c of collisions) {
      const line = document.createElement('div');
      line.textContent = `${(c.pair || []).join(' ↔ ')} — cosine ${(c.cosine || 0).toFixed(3)}`;
      collisionsList.appendChild(line);
    }

    // Detail pane
    const inspected = state.registry.activeInspect;
    const showDetail = inspected && inspected.person && inspected.person.id === activePersonId;
    inspectEmpty.hidden = showDetail;
    inspectDetail.hidden = !showDetail;
    if (showDetail) {
      const person = inspected.person;
      inspectIdEl.textContent = person.id || '';
      inspectDisplayEl.textContent = person.display_name || '';

      inspectFields.innerHTML = '';
      const rows = [
        ['Role', person.default_role || '—'],
        ['Voice', person.voice_type || '—'],
        ['Fach', person.fach || '—'],
        ['First seen', person.first_seen || '—'],
        ['Last updated', person.last_updated || '—'],
        ['Sessions (T/S)', `${person.n_sessions_as_teacher || 0} / ${person.n_sessions_as_student || 0}`],
        ['Total hours', (person.total_hours || 0).toFixed(2)],
        ['Regions', (person.observed_regions || []).join(', ') || '—'],
        ['Bootstrap left', String(person.bootstrap_sessions_remaining ?? 0)],
      ];
      for (const [label, value] of rows) {
        const dt = document.createElement('dt'); dt.textContent = label;
        const dd = document.createElement('dd'); dd.textContent = value;
        inspectFields.appendChild(dt);
        inspectFields.appendChild(dd);
      }

      vpList.innerHTML = '';
      for (const f of inspected.voiceprint_files || []) {
        const li = document.createElement('li'); li.textContent = f;
        vpList.appendChild(li);
      }
    }
  }

  function renderRedoView() {
    const daemonReady = state.daemon.status === 'ready';
    const running = state.batch.status === 'running' || state.batch.status === 'cancelling';
    redoFindBtn.disabled = !daemonReady || running;
    redoRunBtn.disabled = !daemonReady || running;
    redoCancelBtn.disabled = !running;

    const s = state.batch;
    if (running) {
      redoSummary.textContent =
        `running · ${(s.currentFileIndex + 1)}/${s.files.length}`;
    } else if (s.status === 'complete' || s.status === 'failed' || s.status === 'cancelled') {
      redoSummary.textContent =
        `${s.status} · ${s.successful} ok / ${s.failed} failed · ${s.elapsed_s.toFixed(1)}s`;
    } else {
      redoSummary.textContent = '';
    }

    redoFilesEl.innerHTML = '';
    for (const f of state.batch.files) {
      const el = fileRowTmpl.content.firstElementChild.cloneNode(true);
      el.dataset.status = f.status || 'pending';
      el.querySelector('.file-name').textContent = basename(f.path);
      el.querySelector('.file-name').title = f.path;
      el.querySelector('.file-phase').textContent = f.phase
        ? `${f.phase} (${f.completed_phases.length}/10)`
        : '—';
      const bar = el.querySelector('.file-progress-bar');
      const completed = f.completed_phases.length;
      const overall = Math.min(1, completed / 10 + (f.phase_progress || 0) / 10);
      bar.style.width = `${Math.round(overall * 100)}%`;
      el.querySelector('.file-progress-label').textContent = f.phase_progress > 0
        ? `${Math.round(f.phase_progress * 100)}%`
        : '';
      el.querySelector('.file-status').textContent = (f.status || 'pending').replace('_', ' ');
      redoFilesEl.appendChild(el);
    }
  }

  function readRedoFilter() {
    const form = new FormData(redoFilter);
    const get = (k) => form.get(k);
    const filter = {};
    const threshold = Number(get('threshold'));
    if (Number.isFinite(threshold)) filter.threshold = threshold;
    const student = (get('student') || '').trim();
    if (student) filter.student = student;
    const teacher = (get('teacher') || '').trim();
    if (teacher) filter.teacher = teacher;
    const conf = Number(get('confidence_below'));
    if (Number.isFinite(conf) && conf > 0) filter.confidence_below = conf;
    const after = (get('after') || '').trim();
    if (after) filter.after = after;
    if (get('all')) filter.all = true;
    return filter;
  }

  function selectPerson(id) {
    activePersonId = id;
    window.vocality.send({ cmd: 'inspect_person', id: nextId('insp'), person_id: id });
    render();
  }

  // ── Modal helper ─────────────────────────────────────────────────────

  function openModal({ title, fields, onSubmit }) {
    modalTitle.textContent = title;
    modalBody.innerHTML = '';
    for (const f of fields) {
      const label = document.createElement('label');
      const span = document.createElement('span'); span.textContent = f.label;
      label.appendChild(span);
      let input;
      if (f.type === 'select') {
        input = document.createElement('select');
        for (const opt of f.options) {
          const o = document.createElement('option');
          o.value = opt.value;
          o.textContent = opt.label;
          if (opt.value === (f.value ?? '')) o.selected = true;
          input.appendChild(o);
        }
      } else {
        input = document.createElement('input');
        input.type = f.type || 'text';
        input.value = f.value ?? '';
      }
      input.name = f.name;
      label.appendChild(input);
      modalBody.appendChild(label);
    }
    modalOnSubmit = onSubmit;
    modalEl.hidden = false;
  }

  function closeModal() {
    modalEl.hidden = true;
    modalOnSubmit = null;
    modalBody.innerHTML = '';
  }

  function readModalValues() {
    const values = {};
    for (const input of modalBody.querySelectorAll('input, select')) {
      values[input.name] = input.value;
    }
    return values;
  }

  modalCloseBtn.addEventListener('click', closeModal);
  modalCancelBtn.addEventListener('click', closeModal);
  modalSubmitBtn.addEventListener('click', () => {
    if (modalOnSubmit) {
      const values = readModalValues();
      modalOnSubmit(values);
    }
    closeModal();
  });
  modalEl.querySelector('.modal-backdrop').addEventListener('click', closeModal);

  function basename(p) {
    if (!p) return '';
    const parts = String(p).split(/[\\/]/);
    return parts[parts.length - 1] || p;
  }

  // ── Event sources ──────────────────────────────────────────────────

  for (const tab of tabs) {
    tab.addEventListener('click', () => {
      const next = tab.dataset.view;
      dispatch((s) => setView(s, next));
      // When entering Registry, refresh the person list from the daemon.
      if (next === 'registry' && state.daemon.status === 'ready') {
        window.vocality.send({ cmd: 'list_persons', id: nextId('lp') });
      }
    });
  }

  refreshPersonsBtn.addEventListener('click', () => {
    window.vocality.send({ cmd: 'list_persons', id: nextId('lp') });
  });

  editBtn.addEventListener('click', () => {
    const person = (state.registry.activeInspect || {}).person;
    if (!person) return;
    openModal({
      title: `Edit ${person.id}`,
      fields: [
        { name: 'display_name', label: 'Display name', value: person.display_name || '' },
        { name: 'disambiguator', label: 'Disambiguator (optional)', value: person.disambiguator || '' },
        {
          name: 'default_role', label: 'Default role', type: 'select',
          value: person.default_role || 'student',
          options: [
            { value: 'student', label: 'student' },
            { value: 'teacher', label: 'teacher' },
          ],
        },
        {
          name: 'voice_type', label: 'Voice type', type: 'select',
          value: person.voice_type || '',
          options: [
            { value: '', label: '— (unset)' },
            ...['bass','baritone','tenor','alto','mezzo','soprano'].map((v) => ({ value: v, label: v })),
          ],
        },
        {
          name: 'fach', label: 'Fach', type: 'select',
          value: person.fach || '',
          options: [
            { value: '', label: '— (unset)' },
            ...['lirico','drammatico','leggero','spinto','buffo'].map((v) => ({ value: v, label: v })),
          ],
        },
      ],
      onSubmit: (values) => {
        const updates = {};
        for (const k of ['display_name', 'disambiguator', 'default_role', 'voice_type', 'fach']) {
          if (values[k] !== undefined && values[k] !== '') updates[k] = values[k];
        }
        window.vocality.send({
          cmd: 'edit_person', id: nextId('edit'),
          person_id: person.id, updates,
        });
      },
    });
  });

  renameBtn.addEventListener('click', () => {
    const person = (state.registry.activeInspect || {}).person;
    if (!person) return;
    openModal({
      title: `Rename ${person.id}`,
      fields: [{ name: 'new_id', label: 'New id (lowercase, [a-z0-9_])', value: person.id }],
      onSubmit: (values) => {
        const newId = (values.new_id || '').trim();
        if (!newId || newId === person.id) return;
        window.vocality.send({
          cmd: 'rename_person', id: nextId('rn'),
          old_id: person.id, new_id: newId,
        });
        activePersonId = newId;
      },
    });
  });

  settingsBtn.addEventListener('click', async () => {
    let existing = {};
    try { existing = await window.vocality.getSettings(); } catch (_) { /* first launch */ }
    openModal({
      title: 'Settings',
      fields: [
        {
          name: 'hf_token', type: 'password', label: 'HF_TOKEN',
          value: existing.hf_token || '',
        },
        {
          name: 'anthropic_api_key', type: 'password', label: 'ANTHROPIC_API_KEY',
          value: existing.anthropic_api_key || '',
        },
        {
          name: 'data_dir', label: 'Data directory (VOCALITY_ROOT override)',
          value: existing.data_dir || '',
        },
      ],
      onSubmit: async (values) => {
        await window.vocality.saveSettings({
          hf_token: (values.hf_token || '').trim(),
          anthropic_api_key: (values.anthropic_api_key || '').trim(),
          data_dir: (values.data_dir || '').trim(),
        });
        // Restart the daemon so it picks up new env.
        try { await window.vocality.restart(); } catch (_) { /* surfaced via onStatus */ }
      },
    });
  });

  redoFindBtn.addEventListener('click', () => {
    const filter = readRedoFilter();
    filter.dry_run = true;
    window.vocality.send({ cmd: 'redo_batch', id: nextId('redo-dry'), filter });
  });

  redoRunBtn.addEventListener('click', () => {
    const filter = readRedoFilter();
    filter.dry_run = false;
    window.vocality.send({ cmd: 'redo_batch', id: nextId('redo'), filter });
  });

  redoCancelBtn.addEventListener('click', () => {
    window.vocality.send({ cmd: 'cancel_batch', id: nextId('cancel') });
  });

  mergeBtn.addEventListener('click', () => {
    const person = (state.registry.activeInspect || {}).person;
    if (!person) return;
    const others = state.registry.persons.filter((p) => p.id !== person.id);
    if (others.length === 0) return;
    openModal({
      title: `Merge ${person.id} into…`,
      fields: [{
        name: 'target_id', label: 'Target id (the kept record)', type: 'select',
        value: others[0].id,
        options: others.map((p) => ({ value: p.id, label: `${p.id} (${p.display_name || ''})` })),
      }],
      onSubmit: (values) => {
        if (!values.target_id) return;
        window.vocality.send({
          cmd: 'merge_persons', id: nextId('mg'),
          source_id: person.id, target_id: values.target_id,
        });
        activePersonId = values.target_id;
      },
    });
  });

  scanBtn.addEventListener('click', () => {
    const path = (scanPathInput.value || '').trim() || 'Material';
    window.vocality.send({
      cmd: 'scan_files',
      id: nextId('scan'),
      input_dir: path,
      probe_duration: false,
    });
  });

  startBtn.addEventListener('click', () => {
    const files = (state.batch.scan.files || [])
      .filter((f) => f.meta && f.meta.parse_ok !== false)
      .map((f) => f.path);
    window.vocality.send({
      cmd: 'process_batch',
      id: nextId('batch'),
      files,
      options: {},
    });
  });

  cancelBtn.addEventListener('click', () => {
    window.vocality.send({ cmd: 'cancel_batch', id: nextId('cancel') });
  });

  window.vocality.onStatus((status) => {
    dispatch((s) => ({ ...s, daemon: { ...s.daemon, status } }));
  });

  window.vocality.onEvent((event) => {
    dispatch((s) => reduceEvent(s, event));
  });

  // electron-updater lifecycle — no-op in dev mode.
  if (typeof window.vocality.onUpdateStatus === 'function') {
    window.vocality.onUpdateStatus((payload) => {
      updateStatus = payload;
      render();
    });
  }

  // Initial status snapshot
  window.vocality.status().then((info) => {
    if (info && info.status) {
      dispatch((s) => ({
        ...s,
        daemon: {
          ...s.daemon,
          status: info.status,
          version: info.lastReady ? info.lastReady.engine_version : s.daemon.version,
          modelsLoaded: info.lastReady && info.lastReady.models_loaded
            ? info.lastReady.models_loaded.slice()
            : s.daemon.modelsLoaded,
        },
      }));
    }
  }).catch(() => { /* will catch up via onStatus */ });

  render();
})();
