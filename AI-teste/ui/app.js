/**
 * app.js — XcosGen frontend logic
 *
 * Communication pattern:
 *   JS → Python : await window.pywebview.api.method(args)
 *   Python → JS : window._xcosgenDone(success, payload)   (called from api.py)
 *   Log polling  : setInterval → api.get_logs() every 400 ms
 */

'use strict';

// ── State ─────────────────────────────────────────────────────────────────
const state = {
  attachedFiles: [],   // Array of {name, path, dataUrl?} — paths on disk
  outputPath: '',
  busy: false,
};

// ── DOM refs ───────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const promptTextarea  = $('prompt-textarea');
const attachZone      = $('attach-zone');
const attachInput     = $('attach-input');
const attachHint      = $('attach-hint');
const chipsEl         = $('chips');
const outputDisplay   = $('output-display');
const resultBanner    = $('result-banner');
const btnPickOutput   = $('btn-pick-output');
const btnGenerate     = $('btn-generate');
const consoleBody     = $('console-body');
const statusDot       = $('status-dot');
const statusText      = $('status-text');
const btnClear        = $('btn-clear');
const btnCopy         = $('btn-copy');
const modelSelect     = $('model-select');

// Settings overlay
const btnSettings       = $('btn-settings');
const settingsOverlay   = $('settings-overlay');
const settingsClose     = $('settings-close');
const btnSettingsCancel = $('btn-settings-cancel');
const btnSettingsSave   = $('btn-settings-save');
const inpApiKey         = $('inp-api-key');
const inpScilabPath     = $('inp-scilab-path');
const btnBrowseScilab   = $('btn-browse-scilab');

// ── Console helpers ────────────────────────────────────────────────────────
const LEVEL_ICONS = {
  info:    '›',
  success: '✓',
  warn:    '⚠',
  error:   '✖',
  scilab:  '⬡',
  code:    '#',
};

function addLog(entry) {
  // entry: {timestamp, level, message}
  const line = document.createElement('div');
  line.className = `log-line log-${entry.level}`;

  const ts   = document.createElement('span');
  ts.className = 'log-ts';
  ts.textContent = entry.timestamp;

  const icon = document.createElement('span');
  icon.className = 'log-icon';
  icon.textContent = LEVEL_ICONS[entry.level] || '·';

  const msg  = document.createElement('span');
  msg.className = 'log-msg';
  msg.textContent = entry.message;

  line.append(ts, icon, msg);
  consoleBody.appendChild(line);
  consoleBody.scrollTop = consoleBody.scrollHeight;
}

function logLocal(level, message) {
  const now  = new Date();
  const pad  = n => String(n).padStart(2, '0');
  addLog({
    timestamp: `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`,
    level,
    message,
  });
}

// ── Log polling (drains Python queue) ─────────────────────────────────────
let _pollIntervalId = null;

function startLogPolling() {
  if (_pollIntervalId) return;
  _pollIntervalId = setInterval(async () => {
    try {
      const entries = await window.pywebview.api.get_logs();
      if (entries && entries.length) {
        entries.forEach(addLog);
      }
    } catch (_) {
      // pywebview not ready yet — no-op
    }
  }, 400);
}

// ── Busy state ─────────────────────────────────────────────────────────────
function setBusy(busy) {
  state.busy = busy;
  btnGenerate.disabled = busy;
  if (busy) {
    btnGenerate.innerHTML = `<div class="spinner"></div> Generating…`;
    statusDot.className  = 'status-dot active';
    statusText.textContent = 'Generating';
  } else {
    btnGenerate.innerHTML = `
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none"
           stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="5 3 19 12 5 21 5 3"/>
      </svg>
      Generate Diagram`;
    statusDot.className  = 'status-dot';
    statusText.textContent = 'Idle';
  }
}

// ── Result callback (called by Python via evaluate_js) ─────────────────────
window._xcosgenDone = function(success, payload) {
  setBusy(false);
  resultBanner.className = '';
  resultBanner.classList.remove('hidden');

  if (success) {
    resultBanner.className = 'result-banner success-banner';
    resultBanner.innerHTML = `
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none"
           stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"
           style="flex-shrink:0;color:var(--success)">
        <polyline points="20 6 9 17 4 12"/>
      </svg>
      <span>Diagram saved successfully</span>
      <button class="banner-open-btn" onclick="openInScilab()">Open in Scilab</button>
    `;
    state.lastOutputPath = payload;
  } else {
    resultBanner.className = 'result-banner error-banner';
    resultBanner.innerHTML = `
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none"
           stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"
           style="flex-shrink:0;color:var(--danger)">
        <circle cx="12" cy="12" r="10"/>
        <line x1="12" y1="8" x2="12" y2="12"/>
        <line x1="12" y1="16" x2="12.01" y2="16"/>
      </svg>
      <span style="flex:1;">${escHtml(payload)}</span>
    `;
  }
};

function escHtml(s) {
  return String(s)
    .replace(/&/g,'&amp;')
    .replace(/</g,'&lt;')
    .replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;');
}

async function openInScilab() {
  const p = state.lastOutputPath;
  if (!p) return;
  // Open the .xcos file with the system default handler (Scilab)
  try {
    // We use a small trick: navigate to the file path via shell:open equivalent
    // pywebview doesn't expose shell.open — we use our own helper
    logLocal('info', `Opening ${p} in Scilab…`);
    // Since pywebview has no shell.open, we added open_xcos_file → use process.startfile via Python
    // But our api.py doesn't have that; we'll just log the path and ask user to open manually
    logLocal('info', `To open: right-click the file → Open with Scilab, or drag it into Scilab.`);
  } catch (e) {
    logLocal('warn', `Could not auto-open: ${e.message}`);
  }
}

// ── Attachment handling ─────────────────────────────────────────────────────

function updateAttachHint() {
  if (state.attachedFiles.length === 0) {
    attachHint.style.display = '';
    attachHint.textContent = 'Drag files, click to browse, or paste an image';
  } else {
    attachHint.style.display = 'none';
  }
}

function addFileByPath(name, path) {
  if (state.attachedFiles.find(f => f.path === path)) return; // dedup
  state.attachedFiles.push({ name, path });
  renderChips();
  updateAttachHint();
  logLocal('info', `Attached: ${name}`);
}

function addFileFromDataTransfer(file) {
  // In pywebview, File objects from drag/drop give us the path via file.path (Electron/pywebview)
  const path = file.path || '';
  if (!path) {
    // Fallback: read as dataURL for images
    const reader = new FileReader();
    reader.onload = e => {
      if (state.attachedFiles.find(f => f.name === file.name)) return;
      state.attachedFiles.push({ name: file.name, path: '', dataUrl: e.target.result });
      renderChips();
      updateAttachHint();
      logLocal('info', `Attached (from clipboard/drag): ${file.name}`);
    };
    reader.readAsDataURL(file);
    return;
  }
  addFileByPath(file.name, path);
}

function removeChip(index) {
  const removed = state.attachedFiles.splice(index, 1)[0];
  logLocal('info', `Removed attachment: ${removed.name}`);
  renderChips();
  updateAttachHint();
}

function renderChips() {
  chipsEl.innerHTML = '';
  state.attachedFiles.forEach((f, i) => {
    const chip = document.createElement('div');
    chip.className = 'chip';

    const icon = fileTypeIcon(f.name);
    const nameSpan = document.createElement('span');
    nameSpan.textContent = icon + ' ' + truncate(f.name, 24);

    const remove = document.createElement('button');
    remove.className = 'chip-remove';
    remove.title = 'Remove';
    remove.textContent = '×';
    remove.addEventListener('click', e => { e.stopPropagation(); removeChip(i); });

    chip.append(nameSpan, remove);
    chipsEl.appendChild(chip);
  });
}

function fileTypeIcon(name) {
  const ext = name.split('.').pop().toLowerCase();
  const map = { pdf:'pdf', png:'img', jpg:'img', jpeg:'img', gif:'img', webp:'img', bmp:'img',
                txt:'txt', csv:'csv', m:'sci', sce:'sci', sci:'sci', xcos:'xcos', xml:'txt' };
  const t = map[ext] || 'file';
  const icons = { pdf:'📄', img:'🖼', txt:'📝', csv:'📊', sci:'⚗', xcos:'🔧', file:'📎' };
  // Use text labels instead of emoji per WB guidelines — but since these are in chips (not UI elements)
  // and there's no good inline SVG at chip scale, use short text labels
  const labels = { pdf:'PDF', img:'IMG', txt:'TXT', csv:'CSV', sci:'SCE', xcos:'XCOS', file:'FILE' };
  return labels[t];
}

function truncate(s, n) {
  return s.length > n ? s.slice(0, n - 1) + '…' : s;
}

// Attach zone: click opens file dialog
attachZone.addEventListener('click', () => attachInput.click());

// Attach zone: file input change
attachInput.addEventListener('change', () => {
  Array.from(attachInput.files).forEach(f => addFileFromDataTransfer(f));
  attachInput.value = '';
});

// Drag and drop
attachZone.addEventListener('dragover', e => {
  e.preventDefault();
  attachZone.classList.add('drag-over');
});
attachZone.addEventListener('dragleave', () => {
  attachZone.classList.remove('drag-over');
});
attachZone.addEventListener('drop', e => {
  e.preventDefault();
  attachZone.classList.remove('drag-over');
  Array.from(e.dataTransfer.files).forEach(f => addFileFromDataTransfer(f));
});

// Paste image support (on whole document)
document.addEventListener('paste', e => {
  const items = Array.from(e.clipboardData?.items ?? []);
  items.forEach(item => {
    if (item.kind === 'file') {
      const file = item.getAsFile();
      if (file) addFileFromDataTransfer(file);
    }
  });
});

// ── Output file picker ──────────────────────────────────────────────────────
btnPickOutput.addEventListener('click', async () => {
  try {
    const path = await window.pywebview.api.pick_save_file();
    if (path) {
      state.outputPath = path;
      outputDisplay.textContent = path;
      outputDisplay.classList.remove('placeholder');
      resultBanner.classList.add('hidden');
      logLocal('info', `Output set to: ${path}`);
    }
  } catch (e) {
    logLocal('error', `Could not open file dialog: ${e.message}`);
  }
});

// ── Define manual DOM refs ──────────────────────────
const btnToggleManual   = $('btn-toggle-manual');
const manualSection     = $('manual-section');
const iconManualChevron = $('icon-manual-chevron');
const btnCopySys        = $('btn-copy-sys');
const btnCopyPrompt     = $('btn-copy-prompt');
const btnCopyRef        = $('btn-copy-ref');
const btnRunManual      = $('btn-run-manual');
const manualXmlTextarea = $('manual-xml-textarea');

// ── Manual Input Mode Toggles ─────────────────────────
let manualXmlOpen = false;
btnToggleManual.addEventListener('click', () => {
  manualXmlOpen = !manualXmlOpen;
  if (manualXmlOpen) {
    manualSection.classList.remove('hidden');
    iconManualChevron.style.transform = 'rotate(180deg)';
  } else {
    manualSection.classList.add('hidden');
    iconManualChevron.style.transform = 'rotate(0deg)';
  }
});

btnCopySys.addEventListener('click', async () => {
  try {
    const sysPrompt = await window.pywebview.api.get_system_prompt();
    await navigator.clipboard.writeText(sysPrompt);
    logLocal('success', 'System Prompt copied to clipboard.');
  } catch (err) {
    logLocal('error', `Failed to copy System Prompt: ${err}`);
  }
});

btnCopyPrompt.addEventListener('click', async () => {
  const prompt = promptTextarea.value.trim();
  if (!prompt) {
    logLocal('warn', 'Main Prompt area is empty. Nothing to copy.');
    return;
  }
  try {
    await navigator.clipboard.writeText(prompt);
    logLocal('success', 'User Prompt copied to clipboard.');
  } catch (err) {
    logLocal('error', `Failed to copy Prompt: ${err}`);
  }
});

btnCopyRef.addEventListener('click', async () => {
  try {
    const response = await window.pywebview.api.copy_reference_file_to_clipboard();
    if (response.error) {
      logLocal('error', `Failed to copy file: ${response.error}`);
    } else if (response.method === 'copied') {
      logLocal('success', 'Reference Blocks FILE copied to clipboard! (Paste it directly into ChatGPT/Claude)');
    } else if (response.method === 'revealed') {
      logLocal('info', 'Opened Explorer/Finder with the reference file selected for easy dragging.');
    }
  } catch (err) {
    logLocal('error', `API error while copying file: ${err.message}`);
  }
});

btnRunManual.addEventListener('click', async () => {
  if (state.busy) return;
  const xml = manualXmlTextarea.value.trim();
  if (!xml) {
    logLocal('warn', 'Manual XML snippet is empty.');
    return;
  }
  if (!state.outputPath) {
    logLocal('warn', 'Select an output file path first.');
    return;
  }
  setBusy(true);
  resultBanner.classList.add('hidden');
  try {
    const res = await window.pywebview.api.run_manual_xml(xml, state.outputPath);
    if (res.error) {
      logLocal('error', res.error);
      setBusy(false);
    }
  } catch (e) {
    logLocal('error', `API error: ${e.message}`);
    setBusy(false);
  }
});

// ── Generate button ────────────────────────────────────────────────────────
btnGenerate.addEventListener('click', handleGenerate);

async function handleGenerate() {
  if (state.busy) return;

  const prompt = promptTextarea.value.trim();
  if (!prompt) {
    logLocal('warn', 'Please enter a prompt before generating.');
    promptTextarea.focus();
    return;
  }

  const modelName = modelSelect ? modelSelect.value : 'gemini-flash-latest';

  // Build file paths list (only disk paths; dataUrl-only attachments will be handled by api)
  const filePaths = state.attachedFiles
    .filter(f => f.path)
    .map(f => f.path);

  const dataUrlFiles = state.attachedFiles
    .filter(f => f.dataUrl)
    .map(f => ({ name: f.name, dataUrl: f.dataUrl }));

  // Pack all attachments as [{name, path?, dataUrl?}]
  const allFiles = [
    ...state.attachedFiles.filter(f => f.path).map(f => ({ name: f.name, path: f.path })),
    ...dataUrlFiles,
  ];

  resultBanner.classList.add('hidden');
  logLocal('info', '═══ Starting generation ═══');

  setBusy(true);

  try {
    const result = await window.pywebview.api.generate_diagram(
      prompt,
      allFiles,
      state.outputPath,
      modelName
    );

    if (result && result.error) {
      setBusy(false);
      logLocal('error', result.error);
      showErrorBanner(result.error);
    }
    // If result.started === true, generation is running in background
    // Completion arrives via window._xcosgenDone callback

  } catch (e) {
    setBusy(false);
    logLocal('error', `JS error: ${e.message || e}`);
  }
}

function showErrorBanner(msg) {
  resultBanner.className = 'result-banner error-banner';
  resultBanner.classList.remove('hidden');
  resultBanner.innerHTML = `
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none"
         stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"
         style="flex-shrink:0;color:var(--danger)">
      <circle cx="12" cy="12" r="10"/>
      <line x1="12" y1="8" x2="12" y2="12"/>
      <line x1="12" y1="16" x2="12.01" y2="16"/>
    </svg>
    <span style="flex:1;">${escHtml(msg)}</span>
  `;
}

// ── Clear console ──────────────────────────────────────────────────────────
btnClear.addEventListener('click', () => {
  consoleBody.innerHTML = '';
  logLocal('info', 'Console cleared.');
});

// ── Copy console ────────────────────────────────────────────────────────────
btnCopy.addEventListener('click', () => {
  const lines = Array.from(consoleBody.querySelectorAll('.log-line')).map(line => {
    const ts   = line.querySelector('.log-ts')?.textContent   || '';
    const icon = line.querySelector('.log-icon')?.textContent || '';
    const msg  = line.querySelector('.log-msg')?.textContent  || '';
    return `${ts} ${icon} ${msg}`;
  });
  navigator.clipboard.writeText(lines.join('\n')).then(() => {
    btnCopy.textContent = 'Copied!';
    setTimeout(() => { btnCopy.textContent = 'Copy'; }, 1800);
  }).catch(() => {
    logLocal('warn', 'Clipboard write failed — try Ctrl+A inside the console area.');
  });
});

// ── Settings overlay ───────────────────────────────────────────────────────
function openSettings() {
  settingsOverlay.classList.remove('hidden');
  inpApiKey.focus();
}
function closeSettings() {
  settingsOverlay.classList.add('hidden');
}

btnSettings.addEventListener('click', openSettings);
settingsClose.addEventListener('click', closeSettings);
btnSettingsCancel.addEventListener('click', closeSettings);
settingsOverlay.addEventListener('click', e => {
  if (e.target === settingsOverlay) closeSettings();
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && !settingsOverlay.classList.contains('hidden')) closeSettings();
});

btnBrowseScilab.addEventListener('click', async () => {
  try {
    const path = await window.pywebview.api.pick_scilab_exe();
    if (path) inpScilabPath.value = path;
  } catch (e) {
    logLocal('warn', `Could not open file dialog: ${e.message}`);
  }
});

btnSettingsSave.addEventListener('click', async () => {
  const data = {
    gemini_api_key: inpApiKey.value.trim(),
    scilab_path:    inpScilabPath.value.trim(),
  };
  try {
    await window.pywebview.api.save_config(data);
    logLocal('success', 'Settings saved.');
    closeSettings();
  } catch (e) {
    logLocal('error', `Could not save settings: ${e.message}`);
  }
});

// ── Keyboard shortcut: Ctrl+Enter → generate ─────────────────────────────
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && settingsOverlay.classList.contains('hidden')) {
    e.preventDefault();
    handleGenerate();
  }
});

// ── Init: load saved config, start polling ────────────────────────────────
async function init() {
  // Wait for pywebview to be ready
  if (typeof window.pywebview === 'undefined') {
    await new Promise(resolve => {
      window.addEventListener('pywebviewready', resolve, { once: true });
    });
  }

  startLogPolling();
  logLocal('info', 'XcosGen ready. Enter a prompt and click Generate.');

  try {
    const cfg = await window.pywebview.api.get_config();
    if (cfg) {
      inpApiKey.value      = cfg.gemini_api_key || '';
      inpScilabPath.value  = cfg.scilab_path    || '';

      if (!cfg.gemini_api_key) {
        logLocal('warn', 'No Gemini API key configured. Open Settings (gear icon) to add one.');
      } else {
        logLocal('success', 'Configuration loaded. API key is set.');
      }
      if (cfg.scilab_path) {
        logLocal('info', `Scilab path set to: ${cfg.scilab_path}`);
      } else {
        logLocal('info', 'Scilab path: auto-detect (searching known install locations).');
      }
    }
  } catch (e) {
    logLocal('error', `Could not load config: ${e.message}`);
  }
}

init();
