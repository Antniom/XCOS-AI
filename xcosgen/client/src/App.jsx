import React, { useState, useEffect, useRef } from 'react';
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
  FileText,
  Image as ImageIcon
} from 'lucide-react';

function App() {
  const [prompt, setPrompt] = useState('');
  const [model, setModel] = useState('gemini-flash-latest');
  const [isGenerating, setIsGenerating] = useState(false);
  const [logs, setLogs] = useState([]);
  const [status, setStatus] = useState(null);
  const [resultXml, setResultXml] = useState(null);
  
  const [initialXml, setInitialXml] = useState('');
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [outputFilename, setOutputFilename] = useState('diagram.xcos');
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isAdvancedOpen, setIsAdvancedOpen] = useState(false);
  const [apiKey, setApiKey] = useState(localStorage.getItem('gemini_api_key') || '');
  const [isDragging, setIsDragging] = useState(false);
  const [ws, setWs] = useState(null);
  
  const consoleRef = useRef(null);
  const fileInputRef = useRef(null);

  // Persistent status connection
  useEffect(() => {
    let socket = null;
    let reconnectTimeout = null;

    const connect = () => {
      socket = new WebSocket('ws://localhost:8000/ws/status');
      socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        setLogs(prev => [...prev, ...data]);
        
        const validStatuses = ['Generating', 'Verifying', 'Fixing', 'Success', 'Error'];
        let newStatus = null;

        for (const item of data) {
            if (item.step === 'Finished' || item.step === 'Success') {
                newStatus = 'Success';
            } else if (item.step === 'Error') {
                newStatus = 'Error';
            } else if (validStatuses.includes(item.step)) {
                newStatus = item.step;
            }
        }
        
        if (newStatus) {
            setStatus(prevStatus => {
                // Only update if it's different and don't allow backward flow if we are already success
                if (newStatus !== prevStatus) {
                    return newStatus;
                }
                return prevStatus;
            });
        }

        const finishedItem = data.find(d => d.step === 'Finished');
        if (finishedItem) {
            setIsGenerating(false);
            setStatus('Success');
            setResultXml(finishedItem.xml);
            
            // Auto-download the file
            const blob = new Blob([finishedItem.xml], { type: 'text/xml' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'diagram.xcos';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }
      };
      
      socket.onclose = () => {
        reconnectTimeout = setTimeout(connect, 3000); // Auto-reconnect
      };
      
      setWs(socket);
    };

    connect();
    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (socket) {
        socket.onclose = null; // Prevent auto-reconnect on unmount
        socket.close();
      }
    };
  }, []);

  useEffect(() => {
    if (consoleRef.current) {
      consoleRef.current.scrollTop = consoleRef.current.scrollHeight;
    }
  }, [logs]);

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const files = Array.from(e.dataTransfer.files);
    setSelectedFiles(prev => [...prev, ...files]);
  };

  const handlePaste = (e) => {
    const items = Array.from(e.clipboardData.items);
    const files = items
      .filter(item => item.kind === 'file')
      .map(item => item.getAsFile());
    
    if (files.length > 0) {
      setSelectedFiles(prev => [...prev, ...files]);
    }
  };

  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files);
    setSelectedFiles(prev => [...prev, ...files]);
  };

  const removeFile = (index) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index));
  };

  const copyLogs = () => {
    const logText = logs.map(l => `[${new Date().toLocaleTimeString()}] ${l.step}: ${l.error || '...'}`).join('\n');
    navigator.clipboard.writeText(logText);
    alert('Logs copied to clipboard!');
  };

  const downloadXml = () => {
    if (!resultXml) return;
    const blob = new Blob([resultXml], { type: 'text/xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = outputFilename.endsWith('.xcos') ? outputFilename : `${outputFilename}.xcos`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const loadXcosFile = (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev) => {
          setInitialXml(ev.target.result);
          setIsAdvancedOpen(true);
      };
      reader.readAsText(file);
  };

  const handleGenerate = async () => {
    if (!prompt.trim()) return;

    setIsGenerating(true);
    setStatus('Generating');
    setResultXml(null);

    // Prepare attachments
    const attachments = await Promise.all(selectedFiles.map(async (file) => {
        const reader = new FileReader();
        console.log(`Processing attachment: ${file.name} (${file.type})`);
        return new Promise((resolve) => {
            reader.onload = (e) => {
                console.log(`Finished reading ${file.name}`);
                resolve({
                    name: file.name,
                    type: file.type,
                    data: e.target.result
                });
            };
            reader.readAsDataURL(file);
        });
    }));

    try {
      console.log('Sending generation request to backend...', { 
        promptLength: prompt.length, 
        model, 
        hasApiKey: !!apiKey,
        attachmentCount: attachments.length 
      });

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

      console.log('Backend response status:', response.status);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        console.error('Backend returned error:', errorData);
        throw new Error(errorData.detail || 'Failed to start generation');
      }
      
      console.log('Generation started successfully');

    } catch (err) {
      console.error('Generation request failed:', err);
      setLogs(prev => [...prev, { step: 'Error', error: `Network/API Error: ${err.message}` }]);
      setIsGenerating(false);
      setStatus('Error');
    }
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
            <span>Xcos AI Web Dashboard</span>
          </div>
          <div className="flex items-center gap-4">
            <select 
              value={model} 
              onChange={(e) => setModel(e.target.value)}
              className="btn-ghost px-3 py-1"
            >
              <option value="gemini-flash-latest">Gemini 3.1 Flash</option>
              <option value="gemini-flash-lite-latest">Gemini 2.5 Flash Lite</option>
              <option value="gemini-3.1-flash-lite-preview">Gemini 3.1 Flash Lite (Preview)</option>
            </select>
            <button className="btn-icon" onClick={() => setIsSettingsOpen(true)}>
              <Settings size={20} />
              <span className="tooltip">Settings</span>
            </button>
          </div>
        </header>

        <main className="main-container animate-fade-in">
          <div className="content-left">
            <section className="input-area">
              <h2 className="mb-4">Describe your diagram</h2>
              <textarea 
                className="prompt-input"
                placeholder="e.g., A PID controller for a water tank level system..."
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onPaste={handlePaste}
                disabled={isGenerating}
              />

              <div className="flex items-center gap-4 mt-4">
                  <button 
                      className="btn-secondary text-sm"
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
                          <label className="flex items-center justify-between">
                              <span>Initial XML / Context</span>
                              <div className="flex gap-2">
                                  <label className="btn-ghost text-xs cursor-pointer flex items-center gap-1 px-2 py-1">
                                      <FileCode size={12} />
                                      <span>Load .xcos</span>
                                      <input type="file" accept=".xcos" style={{display:'none'}} onChange={loadXcosFile} />
                                  </label>
                                  <button className="btn-ghost text-xs px-2 py-1" onClick={() => setInitialXml('')}>Clear</button>
                              </div>
                          </label>
                          <textarea 
                              className="prompt-input text-sm font-mono h-[200px]"
                              placeholder="Paste existing Xcos XML here to improve or analyze it..."
                              value={initialXml}
                              onChange={(e) => setInitialXml(e.target.value)}
                          />
                      </div>
                  </div>
              )}
              <div className="mt-6 flex justify-end">
                <button 
                  className="btn-primary" 
                  onClick={handleGenerate}
                  disabled={isGenerating || !prompt.trim()}
                >
                  {isGenerating ? <Loader2 className="animate-spin" /> : <Play size={18} />}
                  <span>{isGenerating ? 'Processing...' : 'Generate & Verify'}</span>
                </button>
              </div>
            </section>

            <section className="mt-12">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Terminal size={18} className="text-text-secondary" />
                  <h3>Autonomous Loop Logs</h3>
                </div>
                <button className="btn-ghost text-sm px-3 py-1 flex items-center gap-2" onClick={copyLogs}>
                  <Copy size={14} />
                  <span>Copy Logs</span>
                </button>
              </div>
              <div className="console-panel" ref={consoleRef}>
                {logs.length === 0 && (
                  <div className="h-full flex items-center justify-center opacity-30 select-none">
                    Waiting for generation request...
                  </div>
                )}
                {logs.map((log, i) => (
                  <div key={i} className={`console-line ${log.level || (log.step === 'Error' ? 'error' : 'info')}`}>
                    <span className="opacity-50 mr-2">[{new Date().toLocaleTimeString()}]</span>
                    <strong>{log.step}:</strong> {log.iteration ? `(Iter #${log.iteration})` : ''} {log.message || log.error || 'Processing...'}
                  </div>
                ))}
              </div>
            </section>
          </div>

          <aside className="sidebar">
            <div className="surface">
              <h3>Pipeline Status</h3>
              <div className="stepper mt-6">
                <Step 
                  label="Generation" 
                  active={status === 'Generating'} 
                  completed={['Verifying', 'Fixing', 'Success'].includes(status)} 
                />
                <Step 
                  label="Simulation Check" 
                  active={status === 'Verifying'} 
                  completed={['Success'].includes(status)} 
                />
                <Step 
                  label="Auto-Correction" 
                  active={status === 'Fixing'} 
                  completed={status === 'Success'} 
                  isFixing={status === 'Fixing'}
                />
                <Step 
                  label="Finalization" 
                  active={status === 'Success'} 
                  completed={status === 'Success'} 
                />
              </div>

              {status === 'Success' && (
                  <div className="mt-8 p-6 bg-success/5 rounded-lg border border-success/20 animate-fade-in">
                      <div className="flex items-center gap-2 text-success font-semibold mb-4">
                          <CheckCircle2 size={18} />
                          <span>Diagram Verified!</span>
                      </div>
                      
                      <div className="form-group">
                          <label>Output Filename</label>
                          <div className="flex gap-2">
                              <input 
                                  type="text" 
                                  className="input-text"
                                  value={outputFilename}
                                  onChange={(e) => setOutputFilename(e.target.value)}
                              />
                              <button className="btn-primary" onClick={downloadXml}>
                                  <Download size={18} />
                                  <span>Download</span>
                              </button>
                          </div>
                      </div>
                  </div>
              )}
            </div>

            <div className="surface mt-8">
              <div className="flex items-center gap-2 mb-4">
                  <Cpu size={18} className="text-accent" />
                  <h3>Module Info</h3>
              </div>
              <div className="text-sm text-text-secondary">
                <div className="flex justify-between py-1 border-bottom border-muted">
                    <span>Scilab Version</span>
                    <span>2026.0.1</span>
                </div>
                <div className="flex justify-between py-1 border-bottom border-muted">
                    <span>Xcos AI Version</span>
                    <span>2.0.0-web</span>
                </div>
                <div className="flex justify-between py-1">
                    <span>Backend Status</span>
                    <span className={`${ws?.readyState === 1 ? 'text-success' : 'text-error'} flex items-center gap-1`}>
                        <span className={`w-2 h-2 rounded-full ${ws?.readyState === 1 ? 'bg-success' : 'bg-error'}`}></span> 
                        {ws?.readyState === 1 ? 'Connected' : 'Disconnected'}
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
                      <h3>Dashboard Settings</h3>
                      <button className="btn-icon" onClick={() => setIsSettingsOpen(false)}><X size={20}/></button>
                  </div>
                  <div className="modal-body">
                      <div className="form-group">
                          <label>Gemini API Key</label>
                          <input 
                            type="password" 
                            className="input-text" 
                            placeholder="sk-..." 
                            value={apiKey}
                            onChange={(e) => {
                                setApiKey(e.target.value);
                                localStorage.setItem('gemini_api_key', e.target.value);
                            }}
                          />
                          <p className="text-xs text-text-tertiary mt-2">
                              Your API key is saved locally in your browser.
                          </p>
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

function Step({ label, active, completed, isFixing }) {
  return (
    <div className={`step ${active ? 'active' : ''} ${completed ? 'completed' : ''}`}>
      {completed ? (
        <CheckCircle2 className="text-success" size={20} />
      ) : active ? (
        <Loader2 className="text-accent animate-spin" size={20} />
      ) : isFixing ? (
        <AlertCircle className="text-warning" size={20} />
      ) : (
        <Circle className="text-text-tertiary" size={20} />
      )}
      <span className="font-semibold">{label}</span>
      {isFixing && <span className="text-xs bg-warning/20 text-warning px-2 py-0.5 rounded-full ml-auto">Retrying</span>}
    </div>
  );
}

export default App;
