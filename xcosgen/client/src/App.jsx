import React, { useState, useEffect, useRef, useCallback } from 'react';
import { 
  Sparkles, 
  Settings, 
  Play, 
  CheckCircle2, 
  Circle,
  Loader2, 
  Terminal, 
  AlertCircle,
  Cpu,
  Copy,
  Download,
  X,
  Plus,
  ChevronDown,
  ChevronUp,
  FileCode,
  Wifi,
  WifiOff,
} from 'lucide-react';

// Map backend step names to pipeline stage indices
// 0=Generation, 1=SimCheck, 2=AutoCorrect, 3=Finalization
const STEP_TO_STAGE = {
  'Generating': 0,
  'Job':        0,
  'Verifying':  1,
  'Fixing':     2,
  'Warning':    2,
  'Finished':   3,
  'Success':    3,
};

function App() {
  const [prompt, setPrompt] = useState('');
  const [model, setModel] = useState('gemini-flash-latest');
  const [isGenerating, setIsGenerating] = useState(false);
  const [logs, setLogs] = useState([]);
  const [pipelineStage, setPipelineStage] = useState(-1); // -1 = idle, 0-3 = active stage
  const [pipelineCompleted, setPipelineCompleted] = useState(-1); // highest index completed
  const [resultXml, setResultXml] = useState(null);
  const [isSuccess, setIsSuccess] = useState(false);
  const [isError, setIsError] = useState(false);
  
  const [initialXml, setInitialXml] = useState('');
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [outputFilename, setOutputFilename] = useState('diagram.xcos');
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isAdvancedOpen, setIsAdvancedOpen] = useState(false);
  const [apiKey, setApiKey] = useState(localStorage.getItem('gemini_api_key') || '');
  const [isDragging, setIsDragging] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  
  const consoleRef = useRef(null);
  const fileInputRef = useRef(null);
  const wsRef = useRef(null);
  const sessionIdRef = useRef(null);

  // Persistent status connection via WebSocket
  useEffect(() => {
    let socket = null;
    let reconnectTimeout = null;
    let isMounted = true;

    const connect = () => {
      if (!isMounted) return;
      socket = new WebSocket('ws://localhost:8000/ws/status');
      wsRef.current = socket;

      socket.onopen = () => {
        if (isMounted) setWsConnected(true);
      };

      socket.onmessage = (event) => {
        if (!isMounted) return;
        let data;
        try { data = JSON.parse(event.data); }
        catch { return; }

        if (!Array.isArray(data)) return;

        // Detect new session (backend restart) and wipe stale UI
        const sessionLog = data.find(
          item => item.step === 'Session' && typeof item.message === 'string' && item.message.startsWith('BACKEND_ID:')
        );
        if (sessionLog) {
          const newId = sessionLog.message;
          if (sessionIdRef.current && sessionIdRef.current !== newId) {
            // Backend restarted — reset everything
            setLogs([]);
            setPipelineStage(-1);
            setPipelineCompleted(-1);
            setIsGenerating(false);
            setIsSuccess(false);
            setIsError(false);
            setResultXml(null);
          }
          sessionIdRef.current = newId;
        }

        // Append logs
        setLogs(prev => [...prev, ...data]);

        // Update pipeline stage from step names
        data.forEach(item => {
          const stage = STEP_TO_STAGE[item.step];
          if (stage !== undefined) {
            setPipelineStage(stage);
            setPipelineCompleted(prev => Math.max(prev, stage - 1));
          }
        });

        // Handle final states
        const finishedItem = data.find(d => d.step === 'Finished');
        if (finishedItem) {
          setIsGenerating(false);
          setIsSuccess(true);
          setPipelineStage(3);
          setPipelineCompleted(3);
          setResultXml(finishedItem.xml);

          // Auto-download the file
          if (finishedItem.xml) {
            triggerDownload(finishedItem.xml, 'diagram.xcos');
          }
        }

        const errorItem = data.find(d => d.step === 'Error');
        if (errorItem) {
          setIsGenerating(false);
          setIsError(true);
          setPipelineStage(-1);
        }
      };

      socket.onclose = () => {
        if (isMounted) {
          setWsConnected(false);
          wsRef.current = null;
          reconnectTimeout = setTimeout(connect, 3000);
        }
      };

      socket.onerror = () => {
        socket.close();
      };
    };

    connect();
    return () => {
      isMounted = false;
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (socket) {
        socket.onclose = null;
        socket.close();
      }
    };
  }, []);

  // Auto-scroll console
  useEffect(() => {
    if (consoleRef.current) {
      consoleRef.current.scrollTop = consoleRef.current.scrollHeight;
    }
  }, [logs]);

  const triggerDownload = (xml, filename) => {
    const blob = new Blob([xml], { type: 'text/xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleDragOver = (e) => { e.preventDefault(); setIsDragging(true); };
  const handleDragLeave = (e) => { e.preventDefault(); setIsDragging(false); };
  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    setSelectedFiles(prev => [...prev, ...Array.from(e.dataTransfer.files)]);
  };

  const handlePaste = (e) => {
    const files = Array.from(e.clipboardData.items)
      .filter(item => item.kind === 'file')
      .map(item => item.getAsFile());
    if (files.length > 0) setSelectedFiles(prev => [...prev, ...files]);
  };

  const handleFileSelect = (e) => {
    setSelectedFiles(prev => [...prev, ...Array.from(e.target.files)]);
  };

  const removeFile = (index) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index));
  };

  const copyLogs = () => {
    const logText = logs.map(l => `[${l.timestamp || ''}] ${l.step}: ${l.message || l.error || ''}`).join('\n');
    navigator.clipboard.writeText(logText);
  };

  const downloadXml = () => {
    if (!resultXml) return;
    const name = outputFilename.endsWith('.xcos') ? outputFilename : `${outputFilename}.xcos`;
    triggerDownload(resultXml, name);
  };

  const loadXcosFile = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => { setInitialXml(ev.target.result); setIsAdvancedOpen(true); };
    reader.readAsText(file);
  };

  const handleGenerate = async () => {
    if (!prompt.trim()) return;

    setIsGenerating(true);
    setIsSuccess(false);
    setIsError(false);
    setResultXml(null);
    setLogs([]);
    setPipelineStage(0);
    setPipelineCompleted(-1);

    const attachments = await Promise.all(selectedFiles.map(file =>
      new Promise(resolve => {
        const reader = new FileReader();
        reader.onload = (e) => resolve({ name: file.name, type: file.type, data: e.target.result });
        reader.readAsDataURL(file);
      })
    ));

    try {
      const response = await fetch('http://localhost:8000/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt,
          model,
          initial_xml: initialXml || null,
          attachments: attachments.length > 0 ? attachments : null,
          api_key: apiKey || null
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to start generation');
      }
    } catch (err) {
      setLogs(prev => [...prev, {
        step: 'Error',
        message: `Network/API Error: ${err.message}`,
        level: 'error',
        timestamp: new Date().toLocaleTimeString()
      }]);
      setIsGenerating(false);
      setIsError(true);
      setPipelineStage(-1);
    }
  };

  // Determine icon/state for each pipeline step
  const getStepState = (index) => {
    if (isSuccess && index === 3) return 'success';
    if (pipelineCompleted >= index) return 'completed';
    if (pipelineStage === index) return 'active';
    if (isError) return 'idle';
    return 'idle';
  };

  return (
    <>
      <div
        className={`layout ${isDragging ? 'drag-active' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <div className="drag-overlay">
          <div className="drag-message">
            <Plus size={48} />
            <h2>Drop files to attach</h2>
            <p>Images, PDFs, and Xcos documents are supported</p>
          </div>
        </div>

        <header className="hero-header">
          <div className="hero-title">
            <Sparkles className="text-accent" size={28} />
            <span>Xcos AI</span>
          </div>
          <div className="header-actions">
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="model-select"
            >
              <option value="gemini-flash-latest">Gemini 3.1 Flash</option>
              <option value="gemini-flash-lite-latest">Gemini 2.5 Flash Lite</option>
              <option value="gemini-3.1-flash-lite-preview">Gemini 3.1 Flash Lite (Preview)</option>
            </select>
            <button className="btn-icon tooltip-host" onClick={() => setIsSettingsOpen(true)}>
              <Settings size={20} />
              <span className="tooltip">Settings</span>
            </button>
          </div>
        </header>

        <main className="main-container animate-fade-in">
          <div className="content-left">
            <section className="input-area">
              <h2>Describe your diagram</h2>
              <textarea
                className="prompt-input"
                placeholder="e.g., A PID controller for a water tank level system..."
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onPaste={handlePaste}
                disabled={isGenerating}
              />

              <div className="input-toolbar">
                <button
                  className="btn-secondary"
                  onClick={() => fileInputRef.current.click()}
                  disabled={isGenerating}
                >
                  <Plus size={16} />
                  <span>Attach Files</span>
                </button>
                <input
                  type="file"
                  ref={fileInputRef}
                  style={{ display: 'none' }}
                  multiple
                  onChange={handleFileSelect}
                />

                <div
                  className="advanced-toggle"
                  onClick={() => setIsAdvancedOpen(!isAdvancedOpen)}
                >
                  {isAdvancedOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  <span>Advanced Options</span>
                </div>
              </div>

              {selectedFiles.length > 0 && (
                <div className="file-list">
                  {selectedFiles.map((f, i) => (
                    <div key={i} className="file-item">
                      <FileCode size={14} className="text-accent" />
                      <span>{f.name}</span>
                      <X size={14} className="file-remove" onClick={() => removeFile(i)} />
                    </div>
                  ))}
                </div>
              )}

              {isAdvancedOpen && (
                <div className="advanced-section animate-fade-in">
                  <div className="form-group">
                    <label className="adv-label">
                      <span>Initial XML / Context</span>
                      <div className="flex gap-2">
                        <label className="btn-ghost adv-load-btn">
                          <FileCode size={12} />
                          <span>Load .xcos</span>
                          <input type="file" accept=".xcos" style={{ display: 'none' }} onChange={loadXcosFile} />
                        </label>
                        <button className="btn-ghost adv-clear-btn" onClick={() => setInitialXml('')}>Clear</button>
                      </div>
                    </label>
                    <textarea
                      className="prompt-input mono-input"
                      placeholder="Paste existing Xcos XML here to improve or analyze it..."
                      value={initialXml}
                      onChange={(e) => setInitialXml(e.target.value)}
                    />
                  </div>
                </div>
              )}

              <div className="generate-row">
                <button
                  className={`btn-primary btn-generate ${isGenerating ? 'is-loading' : ''}`}
                  onClick={handleGenerate}
                  disabled={isGenerating || !prompt.trim()}
                >
                  <span className="btn-icon-wrap">
                    {isGenerating
                      ? <Loader2 size={18} className="spin-icon" />
                      : <Play size={18} />
                    }
                  </span>
                  <span>{isGenerating ? 'Processing...' : 'Generate & Verify'}</span>
                </button>
              </div>
            </section>

            {/* Console */}
            <section className="console-section">
              <div className="console-header">
                <div className="flex-row gap-2 align-center">
                  <Terminal size={18} className="text-secondary-icon" />
                  <h3>Autonomous Loop Logs</h3>
                </div>
                <button className="btn-ghost copy-btn" onClick={copyLogs}>
                  <Copy size={14} />
                  <span>Copy</span>
                </button>
              </div>
              <div className="console-panel" ref={consoleRef}>
                {logs.length === 0 && (
                  <div className="console-empty">
                    Waiting for generation request...
                  </div>
                )}
                {logs.map((log, i) => {
                  const level = log.level || (log.step === 'Error' ? 'error' : log.step === 'Warning' ? 'warn' : log.step === 'Finished' || log.step === 'Success' ? 'success' : 'info');
                  const ts = log.timestamp || '';
                  const msg = log.message || log.error || '';
                  return (
                    <div key={i} className={`console-line ${level}`}>
                      {ts && <span className="log-ts">{ts}</span>}
                      <span className="log-step">{log.step}</span>
                      {log.iteration && <span className="log-iter">#{log.iteration}</span>}
                      {msg && <span className="log-msg">{msg}</span>}
                    </div>
                  );
                })}
              </div>
            </section>
          </div>

          <aside className="sidebar">
            <div className="surface">
              <h3>Pipeline Status</h3>
              <div className="stepper">
                <PipelineStep label="Generation"       state={getStepState(0)} />
                <PipelineStep label="Simulation Check" state={getStepState(1)} />
                <PipelineStep label="Auto-Correction"  state={getStepState(2)} />
                <PipelineStep label="Finalization"     state={getStepState(3)} />
              </div>

              {isSuccess && (
                <div className="success-panel animate-fade-in">
                  <div className="success-title">
                    <CheckCircle2 size={18} />
                    <span>Diagram Verified!</span>
                  </div>
                  <div className="form-group">
                    <label>Output Filename</label>
                    <div className="flex-row gap-2">
                      <input
                        type="text"
                        className="input-text"
                        value={outputFilename}
                        onChange={(e) => setOutputFilename(e.target.value)}
                      />
                      <button className="btn-primary" onClick={downloadXml}>
                        <Download size={18} />
                        <span>Save</span>
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {isError && (
                <div className="error-panel animate-fade-in">
                  <AlertCircle size={16} />
                  <span>Generation failed. Check logs for details.</span>
                </div>
              )}
            </div>

            <div className="surface mt-8">
              <div className="module-header">
                <Cpu size={18} className="text-accent" />
                <h3>Module Info</h3>
              </div>
              <div className="info-table">
                <div className="info-row">
                  <span>Scilab Version</span>
                  <span>2026.0.1</span>
                </div>
                <div className="info-row">
                  <span>Xcos AI Version</span>
                  <span>2.0.0-web</span>
                </div>
                <div className="info-row">
                  <span>Backend</span>
                  <span className={`status-badge ${wsConnected ? 'ok' : 'err'}`}>
                    {wsConnected ? <Wifi size={13} /> : <WifiOff size={13} />}
                    {wsConnected ? 'Connected' : 'Offline'}
                  </span>
                </div>
              </div>
            </div>
          </aside>
        </main>
      </div>

      {isSettingsOpen && (
        <div className="modal-overlay" onClick={() => setIsSettingsOpen(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Settings</h3>
              <button className="btn-icon" onClick={() => setIsSettingsOpen(false)}><X size={20} /></button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label>Gemini API Key</label>
                <input
                  type="password"
                  className="input-text"
                  placeholder="AIzaSy..."
                  value={apiKey}
                  onChange={(e) => {
                    setApiKey(e.target.value);
                    localStorage.setItem('gemini_api_key', e.target.value);
                  }}
                />
                <p className="hint-text">Your API key is saved locally in your browser.</p>
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn-primary" onClick={() => setIsSettingsOpen(false)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function PipelineStep({ label, state }) {
  // state: 'idle' | 'active' | 'completed' | 'success'
  const isActive = state === 'active';
  const isCompleted = state === 'completed' || state === 'success';

  return (
    <div className={`step ${isActive ? 'step-active' : ''} ${isCompleted ? 'step-completed' : ''}`}>
      <span className="step-icon">
        {isCompleted ? (
          <CheckCircle2 size={20} className="icon-success" />
        ) : isActive ? (
          <Loader2 size={20} className="icon-accent spin-icon" />
        ) : (
          <Circle size={20} className="icon-muted" />
        )}
      </span>
      <span className="step-label">{label}</span>
      {isActive && <span className="step-badge">Running</span>}
    </div>
  );
}

export default App;
