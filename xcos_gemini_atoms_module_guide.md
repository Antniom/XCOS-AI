# Implementation Guide: Gemini-Powered Xcos Generator — Scilab ATOMS Module
**Target: Scilab 2026.0.1 | Gemini API | ATOMS Toolbox**

---

## 1. Architecture Overview

The system has five tightly coupled components:

```
┌──────────────────────────────────────────────────────────────┐
│  SCILAB PROCESS                                              │
│                                                              │
│  ┌─────────────┐   http_post/get   ┌────────────────────┐   │
│  │ Scilab .sce │ ◄────────────────► │ Python HTTP Server │   │
│  │ Controller  │                   │ (localhost:5007)    │   │
│  └──────┬──────┘                   └────────┬───────────┘   │
│         │ importXcosDiagram()               │ Gemini API     │
│         │ xcos_simulate()                   │ google-genai   │
│         │ error capture                     │                │
│         ▼                                   ▼                │
│  ┌─────────────┐              ┌─────────────────────────┐   │
│  │ .zcos file  │              │ Web App (SPA, port 5008) │   │
│  │ on disk     │              │ API key input, prompt,  │   │
│  └─────────────┘              │ diagram preview, errors │   │
└──────────────────────────────────────────────────────────────┘
```

**Data flow per request:**
1. User enters prompt + Gemini API key in Web App (port 5008)
2. Web App POSTs to Python server `/generate` (port 5007)
3. Python server calls Gemini API → receives XML string
4. Python server writes `.zcos` to a temp path and signals Scilab
5. Scilab polls `/status`, picks up the file path, validates it
6. If error: Scilab POSTs error message to `/error`, Python sends follow-up to Gemini
7. Loop repeats until simulation succeeds or retry limit reached
8. Success/failure status is streamed back to the Web App via SSE

---

## 2. ATOMS Module File Structure

```
xcosai/
├── DESCRIPTION                    ← ATOMS metadata (name, version, deps)
├── builder.sce                    ← Compile macros, help, etc.
├── loader.sce                     ← Called on atomsLoad
├── etc/
│   ├── xcosai.start               ← Entry point (called on Scilab start/load)
│   └── xcosai.quit                ← Cleanup (kill server process)
├── macros/
│   ├── xcosai_start_server.sci    ← Launch Python server via host()
│   ├── xcosai_validate_diagram.sci← importXcosDiagram + xcos_simulate wrapper
│   ├── xcosai_poll_loop.sci       ← Main validation/feedback loop
│   └── buildmacros.sce
├── server/
│   ├── server.py                  ← Python HTTP server (Flask/http.server)
│   ├── gemini_client.py           ← Gemini API calls + XML prompt engineering
│   ├── requirements.txt
│   └── webapp/
│       ├── index.html
│       ├── app.js
│       └── style.css
├── help/
│   └── en_US/
│       └── xcosai.xml
└── tests/
    └── unit_tests/
        └── test_validate.sce
```

### 2.1 `DESCRIPTION` file

```
ToolboxHandle    : xcosai
Title            : Xcos AI Generator
Summary          : Generate Xcos diagrams from natural language using Gemini
Description      : Launches a local web UI and Python server. Users describe
                   a block diagram in natural language; Gemini generates the
                   .zcos XML, which is validated by Scilab simulation.
Version          : 0.1-1
Author           : Your Name <you@domain.com>
ScilabVersion    : >= 2025.0.0
Category         : Xcos
```

---

## 3. ATOMS Lifecycle Scripts

### 3.1 `etc/xcosai.start`

```scilab
// xcosai.start — runs when toolbox is loaded
// ─────────────────────────────────────────────────────────────

// Add macros to path
getd(TOOLBOX_PATH + "/macros");

// Set module-level globals
global XCOSAI_SERVER_PORT;
global XCOSAI_WEBAPP_PORT;
global XCOSAI_TEMP_DIR;

XCOSAI_SERVER_PORT = 5007;
XCOSAI_WEBAPP_PORT = 5008;
XCOSAI_TEMP_DIR    = SCIHOME + "/xcosai_tmp";

// Create temp dir if missing
if ~isdir(XCOSAI_TEMP_DIR) then
    mkdir(XCOSAI_TEMP_DIR);
end

disp("[xcosai] Toolbox loaded. Run xcosai_start() to launch the server.");
```

### 3.2 `etc/xcosai.quit`

```scilab
// xcosai.quit — graceful shutdown
// ─────────────────────────────────────────────────────────────
global XCOSAI_SERVER_PORT;

// Tell the Python server to shut down
try
    http_get("http://localhost:" + string(XCOSAI_SERVER_PORT) + "/shutdown");
catch
    // Server may already be dead; ignore
end

disp("[xcosai] Server stopped.");
```

---

## 4. Scilab Macros

### 4.1 `macros/xcosai_start_server.sci`

This is the main entry point the user calls.

```scilab
function xcosai_start()
// xcosai_start — Launch Python server and open web app in browser
// ─────────────────────────────────────────────────────────────
    global XCOSAI_SERVER_PORT;
    global XCOSAI_WEBAPP_PORT;

    toolbox_path = fileparts(which("xcosai_start"), "path");
    // Navigate up from macros/ to module root
    module_root  = fullpath(toolbox_path + "/..");
    server_dir   = module_root + "/server";
    python_script = server_dir + "/server.py";

    // ── 1. Check if already running ──────────────────────────
    [resp, status] = http_get("http://localhost:" + string(XCOSAI_SERVER_PORT) + "/ping");
    if status == 200 then
        disp("[xcosai] Server already running.");
    else
        // ── 2. Launch Python server in background ─────────────
        // host() in 2026.0.0 is the rewritten unified system call
        if getos() == "Windows" then
            cmd = "start /B python """ + python_script + """ 2>""" + ...
                  SCIHOME + "/xcosai_server.log""";
        else
            cmd = "python3 """ + python_script + """ >> """ + ...
                  SCIHOME + "/xcosai_server.log"" 2>&1 &";
        end
        host(cmd);

        // ── 3. Wait for server to be ready (poll up to 10s) ───
        ready = %f;
        for i = 1:20
            sleep(500);
            [resp, status] = http_get("http://localhost:" + ...
                                      string(XCOSAI_SERVER_PORT) + "/ping");
            if status == 200 then
                ready = %t;
                break;
            end
        end

        if ~ready then
            error("[xcosai] Python server failed to start. Check: " + ...
                  SCIHOME + "/xcosai_server.log");
        end
        disp("[xcosai] Server started on port " + string(XCOSAI_SERVER_PORT));
    end

    // ── 4. Open web app in default browser ────────────────────
    webapp_url = "http://localhost:" + string(XCOSAI_WEBAPP_PORT);
    if getos() == "Windows" then
        winopen(webapp_url);
    elseif getos() == "Linux" then
        host("xdg-open """ + webapp_url + """ &");
    else
        host("open """ + webapp_url + """");
    end

    disp("[xcosai] Web app opened: " + webapp_url);
    disp("[xcosai] Listening for diagram requests...");

    // ── 5. Start polling for diagram validation requests ──────
    xcosai_poll_loop();
endfunction
```

### 4.2 `macros/xcosai_validate_diagram.sci`

Core validation logic. Returns structured result so the caller can pass the error back to Gemini.

```scilab
function result = xcosai_validate_diagram(zcos_path)
// xcosai_validate_diagram — try to compile and simulate a .zcos file
//
// Returns a struct:
//   result.ok      : boolean — %t if simulation succeeded
//   result.error   : string  — error message if failed, "" otherwise
//   result.phase   : string  — "import" | "compile" | "simulate"
// ─────────────────────────────────────────────────────────────

    result.ok    = %f;
    result.error = "";
    result.phase = "";

    // ── Phase 1: Load Xcos libraries ──────────────────────────
    loadXcosLibs();

    // ── Phase 2: Import diagram ───────────────────────────────
    result.phase = "import";
    try
        importXcosDiagram(zcos_path);
        // importXcosDiagram sets scs_m in the caller workspace.
        // It's actually set in the *current* scope here.
    catch
        result.error = lasterror();
        return;
    end

    if ~exists("scs_m") then
        result.error = "importXcosDiagram did not produce scs_m structure.";
        return;
    end

    // ── Phase 3: Attempt batch simulation ─────────────────────
    // xcos_simulate returns a boolean status since Scilab 6.x.
    // Use 'nw' flag to suppress any graphical scope windows.
    result.phase = "simulate";
    ierr = execstr("xcos_simulate(scs_m, 4);", "errcatch");
    if ierr ~= 0 then
        result.error = lasterror();
        return;
    end

    result.ok    = %t;
    result.error = "";
endfunction
```

> **Note on `xcos_simulate` flag:** the integer argument is the `needcompile` flag. `4` means compile + simulate. `1` means simulate only (skip compile). Use `4` for first run on any new diagram.

### 4.3 `macros/xcosai_poll_loop.sci`

Long-running loop that listens for tasks from the Python server.

```scilab
function xcosai_poll_loop()
// xcosai_poll_loop — main event loop: polls server for new diagrams,
//                    validates them, posts results back.
// ─────────────────────────────────────────────────────────────
    global XCOSAI_SERVER_PORT;
    global XCOSAI_TEMP_DIR;

    MAX_RETRIES = 5;
    POLL_MS     = 1000;  // 1 second between polls

    disp("[xcosai] Poll loop running. Press Ctrl+C in console to stop.");

    while %t
        sleep(POLL_MS);

        // ── Ask server if there's a pending validation task ───
        [resp, status] = http_get("http://localhost:" + ...
                                  string(XCOSAI_SERVER_PORT) + "/task");
        if status ~= 200 then
            continue;
        end

        task = fromJSON(resp);
        if task.status ~= "pending" then
            continue;
        end

        task_id   = task.task_id;
        zcos_path = task.zcos_path;
        attempt   = task.attempt;

        disp("[xcosai] Validating task " + task_id + ...
             " (attempt " + string(attempt) + "/" + string(MAX_RETRIES) + ")");

        // ── Validate diagram ───────────────────────────────────
        validation = xcosai_validate_diagram(zcos_path);

        if validation.ok then
            // ── Success: notify server ─────────────────────────
            payload = struct();
            payload.task_id = task_id;
            payload.success = %t;
            http_post("http://localhost:" + string(XCOSAI_SERVER_PORT) + ...
                      "/result", payload);
            disp("[xcosai] ✓ Diagram validated: " + zcos_path);

        elseif attempt >= MAX_RETRIES then
            // ── Give up ────────────────────────────────────────
            payload = struct();
            payload.task_id  = task_id;
            payload.success  = %f;
            payload.error    = validation.error;
            payload.phase    = validation.phase;
            payload.give_up  = %t;
            http_post("http://localhost:" + string(XCOSAI_SERVER_PORT) + ...
                      "/result", payload);
            disp("[xcosai] ✗ Max retries exceeded for task " + task_id);

        else
            // ── Failure: send error for Gemini follow-up ───────
            payload = struct();
            payload.task_id  = task_id;
            payload.success  = %f;
            payload.error    = validation.error;
            payload.phase    = validation.phase;
            payload.give_up  = %f;
            http_post("http://localhost:" + string(XCOSAI_SERVER_PORT) + ...
                      "/result", payload);
            disp("[xcosai] ✗ Validation error (phase=" + ...
                 validation.phase + "): " + validation.error);
        end
    end
endfunction
```

---

## 5. Python Server (`server/server.py`)

Use Flask. It serves both the REST API (port 5007) and the static web app (port 5008 via a separate thread, or serve the SPA from the same Flask app under `/`).

```python
# server/server.py
import os
import sys
import json
import uuid
import threading
from pathlib import Path
from flask import Flask, request, jsonify, Response, send_from_directory
from gemini_client import GeminiXcosClient

# ── Configuration ─────────────────────────────────────────────────────────────
SERVER_PORT = 5007
WEBAPP_PORT = 5008        # Only needed if serving from a second process/port
TEMP_DIR    = os.environ.get("XCOSAI_TEMP_DIR",
                              os.path.join(Path.home(), ".Scilab", "xcosai_tmp"))
os.makedirs(TEMP_DIR, exist_ok=True)

# ── State ─────────────────────────────────────────────────────────────────────
# task_store: dict keyed by task_id
#   {
#     "status":    "pending" | "validating" | "done" | "error",
#     "zcos_path": str,
#     "attempt":   int,
#     "history":   list[dict],   # full conversation for multi-turn Gemini
#     "sse_queue": queue.Queue,  # for streaming to browser
#     "result":    dict | None
#   }
import queue
task_store: dict = {}
task_lock = threading.Lock()

app = Flask(__name__, static_folder="webapp", static_url_path="")

# ── Helpers ───────────────────────────────────────────────────────────────────
def active_task():
    """Return the first task with status 'pending', or None."""
    with task_lock:
        for tid, t in task_store.items():
            if t["status"] == "pending":
                return tid, t
    return None, None

# ── Routes: Web App ───────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("webapp", "index.html")

# ── Routes: Scilab polling ────────────────────────────────────────────────────
@app.route("/ping")
def ping():
    return jsonify({"ok": True}), 200

@app.route("/shutdown")
def shutdown():
    os._exit(0)

@app.route("/task")
def get_task():
    """Scilab polls this endpoint every second."""
    tid, task = active_task()
    if task is None:
        return jsonify({"status": "idle"}), 200
    with task_lock:
        task["status"] = "validating"
    return jsonify({
        "status":    "pending",
        "task_id":   tid,
        "zcos_path": task["zcos_path"],
        "attempt":   task["attempt"],
    }), 200

@app.route("/result", methods=["POST"])
def post_result():
    """Scilab posts validation results here."""
    data    = request.get_json()
    task_id = data.get("task_id")

    with task_lock:
        task = task_store.get(task_id)
        if task is None:
            return jsonify({"error": "unknown task"}), 404

        if data.get("success"):
            task["status"] = "done"
            task["result"] = {"success": True, "zcos_path": task["zcos_path"]}
            # Notify browser via SSE
            task["sse_queue"].put({"type": "done",
                                   "zcos_path": task["zcos_path"]})
        elif data.get("give_up"):
            task["status"] = "error"
            task["result"] = {"success": False, "error": data.get("error", "")}
            task["sse_queue"].put({"type": "error",
                                   "error": data.get("error", "")})
        else:
            # Trigger Gemini follow-up in a background thread
            task["status"] = "regenerating"
            err_msg   = data.get("error", "")
            err_phase = data.get("phase", "")
            threading.Thread(
                target=regenerate_diagram,
                args=(task_id, err_msg, err_phase),
                daemon=True
            ).start()

    return jsonify({"ok": True}), 200

# ── Routes: Web App API ───────────────────────────────────────────────────────
@app.route("/generate", methods=["POST"])
def generate():
    """Browser POSTs here to start a new diagram generation."""
    data    = request.get_json()
    api_key = data.get("api_key", "").strip()
    prompt  = data.get("prompt", "").strip()
    model   = data.get("model", "gemini-2.5-pro-preview-05-06")

    if not api_key or not prompt:
        return jsonify({"error": "api_key and prompt are required"}), 400

    task_id   = str(uuid.uuid4())[:8]
    zcos_path = os.path.join(TEMP_DIR, f"diagram_{task_id}.zcos")
    sse_q     = queue.Queue()

    with task_lock:
        task_store[task_id] = {
            "status":    "generating",
            "api_key":   api_key,
            "model":     model,
            "prompt":    prompt,
            "zcos_path": zcos_path,
            "attempt":   0,
            "history":   [],     # Gemini multi-turn chat history
            "sse_queue": sse_q,
            "result":    None,
        }

    # First generation in background thread
    threading.Thread(
        target=first_generate,
        args=(task_id,),
        daemon=True
    ).start()

    return jsonify({"task_id": task_id}), 202

@app.route("/events/<task_id>")
def events(task_id):
    """SSE stream for a given task_id. Browser listens here."""
    def stream():
        with task_lock:
            task = task_store.get(task_id)
        if task is None:
            yield f"data: {json.dumps({'type': 'error', 'error': 'unknown task'})}\n\n"
            return
        sse_q = task["sse_queue"]
        while True:
            try:
                msg = sse_q.get(timeout=30)
                yield f"data: {json.dumps(msg)}\n\n"
                if msg["type"] in ("done", "error"):
                    break
            except queue.Empty:
                yield "data: {\"type\": \"heartbeat\"}\n\n"
    return Response(stream(), mimetype="text/event-stream")

# ── Background Workers ────────────────────────────────────────────────────────
def first_generate(task_id: str):
    with task_lock:
        task = task_store[task_id]
    client = GeminiXcosClient(api_key=task["api_key"], model=task["model"])
    _do_generate(task_id, task, client, task["prompt"])

def regenerate_diagram(task_id: str, error_msg: str, error_phase: str):
    with task_lock:
        task = task_store[task_id]
    client = GeminiXcosClient(api_key=task["api_key"], model=task["model"])
    follow_up = _build_followup_prompt(error_msg, error_phase, task["attempt"])
    _do_generate(task_id, task, client, follow_up)

def _do_generate(task_id: str, task: dict, client, prompt_text: str):
    try:
        # Notify browser
        task["sse_queue"].put({
            "type":    "generating",
            "attempt": task["attempt"] + 1,
            "message": "Calling Gemini..."
        })

        xml_str, history = client.generate_xcos_xml(
            prompt_text,
            history=task["history"]
        )

        # Write .zcos file
        with open(task["zcos_path"], "w", encoding="utf-8") as f:
            f.write(xml_str)

        with task_lock:
            task["history"] = history
            task["attempt"] += 1
            task["status"]   = "pending"   # Ready for Scilab to pick up

        task["sse_queue"].put({
            "type":    "validating",
            "attempt": task["attempt"],
            "message": "Diagram written, waiting for Scilab validation..."
        })

    except Exception as e:
        with task_lock:
            task["status"] = "error"
            task["result"] = {"success": False, "error": str(e)}
        task["sse_queue"].put({"type": "error", "error": str(e)})

def _build_followup_prompt(error_msg: str, phase: str, attempt: int) -> str:
    return (
        f"The Xcos diagram you generated failed validation during the '{phase}' phase "
        f"with this error from Scilab 2026.0.1:\n\n"
        f"```\n{error_msg}\n```\n\n"
        f"Please fix the XML and return the corrected complete .zcos file. "
        f"Only return the XML, no explanation. "
        f"Common causes:\n"
        f"- Wrong simulation function name (check BLOCK_CATALOGUE)\n"
        f"- Mismatched port counts or types\n"
        f"- Missing required block parameters\n"
        f"- Link source/target UIDs not matching any block UID\n"
        f"- Missing CLOCK_c for discrete blocks\n"
    )

# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"[xcosai server] Starting on port {SERVER_PORT}")
    print(f"[xcosai server] Web app on port {SERVER_PORT} at /")
    print(f"[xcosai server] Temp dir: {TEMP_DIR}")
    app.run(host="127.0.0.1", port=SERVER_PORT, threaded=True)
```

---

## 6. Gemini Client (`server/gemini_client.py`)

```python
# server/gemini_client.py
import re
import json
from google import genai
from google.genai import types

SYSTEM_PROMPT = """
You are an expert Scilab Xcos diagram generator. Your task is to generate valid
.zcos XML files (the native Scilab 2026.0.1 Xcos format) from a user description.

RULES:
1. Return ONLY the raw XML of the .zcos file. No Markdown, no code fences,
   no explanation before or after the XML.
2. The root element must be <XcosDiagram> with the correct namespace.
3. Every block must have a unique `id` attribute (use integer strings: "1", "2", ...).
4. Every Link must have valid `source` and `target` attributes matching existing block IDs.
5. Use only standard Scilab 2026.0.1 Xcos blocks (see BLOCK_CATALOGUE below).
6. Always include a CLOCK_c block when any discrete blocks are present.
7. Block positions (x, y) must not overlap: use 100-pixel grid spacing.
8. The <finalIntegrationTime> must be a positive number (default 10).

BLOCK_CATALOGUE (name → simulation function, typical params):
- CONST_m       → cstblk4, param: real value
- GAINBLK_f     → gain_f,  param: gain scalar or matrix  
- SUMMATION     → summation, params: [signs list e.g. "1;1"], number of inputs
- INTEGRAL_m    → integrator_m, param: initial condition
- CLSS          → clss, params: A B C D matrices (state-space continuous)
- DERIV         → deriv (no parameters)
- PRODUCT       → product, param: [1;1] for multiply, [1;-1] for divide
- TOWS_c        → writec, param: variable name string
- FROMWSB       → fromws_c, param: variable name string
- CLOCK_c       → csuper (event clock, period=0.1 default)
- SCOPE         → oscilloscope (CSCOPE), param: refresh period
- CSCOPE        → cscope, params: ymin, ymax, refresh_period
- AFFICHE_m     → affich4 (digital display)
- STEP_FUNCTION → step_func, param: step time, initial value, final value
- MUX           → multiplex, param: number of inputs
- DEMUX         → demultiplex, param: number of outputs
- SWITCH2_m     → switch2_m, param: threshold
- SATURATION    → satur, params: lower bound, upper bound
- SINUSOID_GENERATOR → genscd, params: amplitude, frequency, phase
- RAMP          → ramp, params: slope, start_time, initial_value
- PID_AUTO_TUNING → PID (not recommended: use separate P/I/D blocks)
- SUPER_f       → superblock (used for hierarchical diagrams)

MINIMAL VALID .ZCOS TEMPLATE:
<XcosDiagram background="-1" finalIntegrationTime="10" title="Diagram">
  <mxCell id="0"/>
  <mxCell id="1" parent="0"/>
  <Block id="2" parent="1" SimulationFunctionName="cstblk4"
         interfaceFunctionName="CONST_m" style="CONST_m" vertex="1">
    <mxGeometry x="100" y="100" width="40" height="40" as="geometry"/>
    <ScicosProperties>
      <ScicosProperty name="exprs"><![CDATA["1"]]></ScicosProperty>
    </ScicosProperties>
  </Block>
  <Link id="3" source="2" target="4" edge="1" parent="1">
    <mxGeometry relative="1" as="geometry"/>
  </Link>
</XcosDiagram>
""".strip()


class GeminiXcosClient:
    def __init__(self, api_key: str, model: str = "gemini-2.5-pro-preview-05-06"):
        self.client = genai.Client(api_key=api_key)
        self.model  = model

    def generate_xcos_xml(
        self,
        prompt: str,
        history: list[dict] | None = None
    ) -> tuple[str, list[dict]]:
        """
        Generate or repair a .zcos XML from a user prompt.

        Args:
            prompt:  The user's request or the follow-up error prompt.
            history: Prior conversation turns (for multi-turn repair).

        Returns:
            (xml_string, updated_history)
        """
        if history is None:
            history = []

        # Build contents list
        contents = list(history)
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.2,     # Low temp = more deterministic XML
                max_output_tokens=8192,
            )
        )

        raw_text  = response.text
        xml_str   = self._extract_xml(raw_text)

        # Append assistant turn to history for multi-turn repair
        updated_history = contents + [
            {"role": "model", "parts": [{"text": raw_text}]}
        ]

        return xml_str, updated_history

    @staticmethod
    def _extract_xml(text: str) -> str:
        """Strip Markdown fences and leading/trailing whitespace."""
        # Remove ```xml ... ``` or ``` ... ``` wrappers
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text.strip(), flags=re.MULTILINE)
        text = re.sub(r"\n?```$", "", text.strip(), flags=re.MULTILINE)
        text = text.strip()

        # Validate it starts with XML declaration or root element
        if not (text.startswith("<?xml") or text.startswith("<XcosDiagram")):
            raise ValueError(
                f"Gemini response does not appear to be valid XML. "
                f"First 200 chars: {text[:200]}"
            )
        return text
```

**`server/requirements.txt`:**
```
flask>=3.0
google-genai>=1.0
```

---

## 7. Web App (`server/webapp/`)

### `index.html`

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Xcos AI Generator</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <div class="container">
    <h1>⚡ Xcos AI Generator</h1>
    <p class="subtitle">Describe a block diagram — Gemini generates the .zcos file.</p>

    <div class="card" id="config-card">
      <label>Gemini API Key
        <input type="password" id="api-key" placeholder="AIza..." autocomplete="off">
      </label>
      <label>Model
        <select id="model">
          <option value="gemini-2.5-pro-preview-05-06">Gemini 2.5 Pro (best)</option>
          <option value="gemini-2.0-flash">Gemini 2.0 Flash (fast)</option>
        </select>
      </label>
    </div>

    <div class="card">
      <label>Describe your diagram
        <textarea id="prompt" rows="5"
          placeholder="Example: A PID control loop with a step input, a first-order plant G(s)=1/(s+1), and a scope to visualize the output."></textarea>
      </label>
      <button id="generate-btn" onclick="generate()">Generate Diagram</button>
    </div>

    <div class="card" id="status-card" style="display:none">
      <div id="status-log"></div>
      <div id="progress-bar"><div id="progress-fill"></div></div>
    </div>

    <div class="card success" id="result-card" style="display:none">
      <h2>✅ Diagram Ready</h2>
      <p id="result-path"></p>
      <button onclick="openInXcos()">Open in Xcos</button>
      <button onclick="copyPath()">Copy Path</button>
    </div>

    <div class="card error" id="error-card" style="display:none">
      <h2>❌ Generation Failed</h2>
      <pre id="error-msg"></pre>
    </div>
  </div>
  <script src="app.js"></script>
</body>
</html>
```

### `app.js`

```javascript
let currentTaskId = null;
let eventSource   = null;
let resultZcosPath = "";

function log(message, type = "info") {
  const el = document.getElementById("status-log");
  const line = document.createElement("div");
  line.className = `log-line ${type}`;
  line.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
  el.appendChild(line);
  el.scrollTop = el.scrollHeight;
}

function setProgress(pct) {
  document.getElementById("progress-fill").style.width = pct + "%";
}

async function generate() {
  const apiKey = document.getElementById("api-key").value.trim();
  const prompt = document.getElementById("prompt").value.trim();
  const model  = document.getElementById("model").value;

  if (!apiKey) { alert("Please enter your Gemini API key."); return; }
  if (!prompt) { alert("Please describe a diagram."); return; }

  // Reset UI
  document.getElementById("result-card").style.display = "none";
  document.getElementById("error-card").style.display  = "none";
  document.getElementById("status-card").style.display = "block";
  document.getElementById("status-log").innerHTML = "";
  setProgress(5);
  log("Sending request to server...");

  // Stop any existing SSE
  if (eventSource) { eventSource.close(); eventSource = null; }

  const resp = await fetch("/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: apiKey, prompt, model })
  });

  if (!resp.ok) {
    const err = await resp.json();
    log("Error: " + (err.error || "Unknown error"), "error");
    return;
  }

  const { task_id } = await resp.json();
  currentTaskId = task_id;
  log(`Task ID: ${task_id}`);
  setProgress(15);

  // Listen for SSE events
  eventSource = new EventSource(`/events/${task_id}`);

  eventSource.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    handleEvent(msg);
  };

  eventSource.onerror = () => {
    log("Connection to server lost.", "error");
    eventSource.close();
  };
}

function handleEvent(msg) {
  switch (msg.type) {
    case "heartbeat":
      break;

    case "generating":
      log(`Attempt ${msg.attempt}: ${msg.message}`, "info");
      setProgress(20 + (msg.attempt - 1) * 15);
      break;

    case "validating":
      log(`Attempt ${msg.attempt}: ${msg.message}`, "info");
      setProgress(40 + (msg.attempt - 1) * 15);
      break;

    case "done":
      setProgress(100);
      resultZcosPath = msg.zcos_path;
      log("✓ Diagram validated successfully!", "success");
      document.getElementById("result-path").textContent = msg.zcos_path;
      document.getElementById("result-card").style.display = "block";
      eventSource.close();
      break;

    case "error":
      setProgress(0);
      log("✗ Error: " + msg.error, "error");
      document.getElementById("error-msg").textContent = msg.error;
      document.getElementById("error-card").style.display = "block";
      eventSource.close();
      break;
  }
}

function openInXcos() {
  // Tell Scilab via a special endpoint to call xcos(path)
  fetch("/open_xcos", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ zcos_path: resultZcosPath })
  });
}

function copyPath() {
  navigator.clipboard.writeText(resultZcosPath).then(() => {
    alert("Path copied to clipboard!");
  });
}
```

Add a `/open_xcos` route to `server.py` that sets a flag, which Scilab's poll loop also checks and handles with `xcos(path)`.

---

## 8. The Validation–Repair Loop in Detail

Here is the precise sequence of events showing how all components interact:

```
Browser          Python Server            Gemini API          Scilab
   │                  │                       │                  │
   │─ POST /generate ─►│                       │                  │
   │                  │─ generate_content() ──►│                  │
   │                  │◄─ XML response ────────│                  │
   │                  │                       │                  │
   │                  │  write .zcos to disk  │                  │
   │                  │  task.status="pending"│                  │
   │◄─ SSE: validating─│                       │                  │
   │                  │                       │◄── GET /task ────│
   │                  │──────── task JSON ─────────────────────► │
   │                  │                       │                  │
   │                  │                       │  importXcosDiagram()
   │                  │                       │  xcos_simulate()  │
   │                  │                       │                  │
   │                  │                       │  [SUCCESS] ──────►│
   │                  │◄──────── POST /result (success=true) ───-│
   │◄─ SSE: done ──────│                       │                  │
   │                  │                       │                  │
   │                  │─ [OR: FAILURE] ────────────────────────► │
   │                  │◄──────── POST /result (success=false) ───│
   │                  │                       │                  │
   │                  │─ regenerate_diagram() thread             │
   │                  │─ build followup prompt│                  │
   │                  │─ generate_content() ──►│                  │
   │                  │◄─ corrected XML ───────│                  │
   │                  │                       │                  │
   │                  │  write new .zcos file │                  │
   │                  │  task.status="pending"│                  │
   │◄─ SSE: validating─│                       │                  │
   │                  │                       │  [loop repeats]  │
```

---

## 9. Error Message Engineering

The quality of the follow-up prompt determines repair success. Structure it precisely:

```python
def _build_followup_prompt(error_msg: str, phase: str, attempt: int) -> str:
    phase_hints = {
        "import": (
            "The XML is structurally invalid. Check:\n"
            "- Root element must be <XcosDiagram>\n"
            "- All tags properly closed\n"
            "- CDATA sections for expressions\n"
            "- Valid UTF-8, no stray characters\n"
        ),
        "simulate": (
            "The diagram structure is valid but the simulation failed. Check:\n"
            "- SimulationFunctionName must match Scilab 2026.0.1 exactly\n"
            "- All connected ports must have matching data types\n"
            "- No algebraic loops without an integrator\n"
            "- Continuous blocks need final simulation time > 0\n"
            "- Matrix dimensions in block parameters must be consistent\n"
        ),
    }
    hints = phase_hints.get(phase, "")
    return (
        f"The Xcos diagram failed during '{phase}' with this error:\n\n"
        f"```\n{error_msg}\n```\n\n"
        f"{hints}"
        f"Return ONLY the corrected complete .zcos XML. No explanation."
    )
```

---

## 10. Startup Sequence and Dependency Bootstrap

### 10.1 Python Dependency Installer (called from `xcosai.start`)

Add this to `xcosai.start` before the server launch:

```scilab
function xcosai_install_deps()
    global XCOSAI_TEMP_DIR;
    toolbox_path = fileparts(which("xcosai_start"), "path");
    module_root  = fullpath(toolbox_path + "/..");
    req_file     = module_root + "/server/requirements.txt";
    flag_file    = XCOSAI_TEMP_DIR + "/.deps_installed";

    if isfile(flag_file) then
        return;
    end

    disp("[xcosai] Installing Python dependencies...");
    if getos() == "Windows" then
        cmd = "pip install -r """ + req_file + """ --quiet";
    else
        cmd = "pip3 install -r """ + req_file + """ --quiet";
    end

    ret = host(cmd);
    if ret == 0 then
        mputl("ok", flag_file);
        disp("[xcosai] Dependencies installed.");
    else
        error("[xcosai] pip install failed. Check your Python installation.");
    end
endfunction
```

### 10.2 Retry-safe `http_get` wrapper

Since `http_get` throws on non-200, wrap it:

```scilab
function [resp, status] = xcosai_safe_get(url)
    resp   = "";
    status = -1;
    try
        [resp, status] = http_get(url);
    catch
        // Connection refused or timeout — treat as status -1
    end
endfunction
```

---

## 11. Key Scilab 2026.0.1 Specifics

| Topic | Detail |
|---|---|
| `host()` | Fully rewritten in 2026.0.0; replaces `unix()`, `dos()`, `unix_w()` etc. Always use `host()` for system calls. Background execution: append `&` on Linux/macOS, use `start /B` on Windows. |
| `importXcosDiagram(path)` | Sets `scs_m` in current scope. Returns `result` (boolean). `.xcos` and `.zcos` both supported. |
| `xcos_simulate(scs_m, 4)` | `4` = compile + simulate. Returns `status` (%t/%f). Invoke with `execstr(..., "errcatch")` to capture errors. |
| `lasterror()` | Returns the last error message as a string. Call immediately after the failed `execstr`. |
| `loadXcosLibs()` | Must be called before any `importXcosDiagram` or `xcos_simulate` in batch mode. |
| `http_post(url, struct)` | Scilab struct is auto-serialized to JSON. Ensure all fields are scalar strings/numbers. |
| `fromJSON(str)` | Parses JSON into Scilab struct. NaN/Inf supported since 2025.1.0. |
| `sleep(ms)` | Millisecond precision sleep. Use in poll loop. |
| Zombie fix | Bug #17473 (background Scilab spawning zombies on Windows) is fixed in 2026.0.0. The module benefits from this directly. |

---

## 12. Common Failure Modes and Mitigations

| Failure | Root Cause | Fix |
|---|---|---|
| `importXcosDiagram` crashes Scilab | Malformed XML (not well-formed) | Pre-validate with Python `xml.etree.ElementTree.parse()` before writing to disk; return 400 to Scilab if invalid |
| Simulation hangs indefinitely | Algebraic loop or infinite simulation time | Set `scs_m.props.tf` to a hard cap (e.g. 30 s) in Scilab before calling `xcos_simulate` |
| Port mismatch error | Gemini uses wrong port count | Include full port schema in system prompt; parse error and tell Gemini exactly which block and port failed |
| `lasterror()` returns "" | Error already consumed | Use `execstr` + `errcatch` + check `ierr ~= 0`; the message is in the second return of `lasterror(msg, n)` |
| Server not found on poll | Race condition at startup | Use exponential backoff polling (500 ms → 1 s → 2 s) during the startup wait |
| Flask port already in use | Previous session not cleaned up | Add port-check at startup; auto-increment port and save to a `SCIHOME/xcosai_port.json` file |
| Gemini returns non-XML | Model hallucinated explanation | `_extract_xml()` checks for XML start; throws with context if not found, triggers immediate retry |

---

## 13. Complete `builder.sce`

```scilab
// builder.sce — builds the toolbox (run once after checkout)
// ─────────────────────────────────────────────────────────────
TOOLBOX_NAME = "xcosai";
TOOLBOX_TITLE = "Xcos AI Generator";

tbx_build_macros(TOOLBOX_NAME, get_absolute_file_path("builder.sce") + "macros/");
tbx_build_help(TOOLBOX_NAME, get_absolute_file_path("builder.sce") + "help/");

disp(TOOLBOX_TITLE + " built successfully.");
```

---

## 14. Complete `loader.sce`

```scilab
// loader.sce — loads the toolbox into the current Scilab session
// ─────────────────────────────────────────────────────────────
TOOLBOX_PATH = get_absolute_file_path("loader.sce");

getd(TOOLBOX_PATH + "macros");

// Execute the start script
exec(TOOLBOX_PATH + "etc/xcosai.start", -1);
```

---

## 15. Usage Summary

After installing (`atomsInstall("xcosai")`), the user does:

```scilab
// In the Scilab console:
xcosai_start();
// → Installs Python deps on first run
// → Starts Python server on localhost:5007
// → Opens http://localhost:5007 in browser
// → Enters the poll loop (non-blocking via background Scilab)
```

Then in the browser:
1. Paste Gemini API key
2. Select model (2.5 Pro recommended for complex diagrams)
3. Write prompt
4. Click **Generate**
5. Watch the status bar: Generating → Validating → ✅ Done (or retry loop)
6. Click **Open in Xcos** to load the diagram directly

---

## 16. Security Notes

- The server binds only to `127.0.0.1` — not exposed to the network.
- The Gemini API key is stored only in RAM (Python process) for the session duration; it is never written to disk.
- Use `https` if ever exposing beyond localhost (add `ssl_context='adhoc'` to Flask `app.run()`).
