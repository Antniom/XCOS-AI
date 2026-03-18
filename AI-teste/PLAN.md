# XcosGen — Detailed Build Plan
### AI-powered Xcos Diagram Generator (Gemini + Scilab + Warm Beige UI)

---

## 0. Critical Pre-Research Findings

### ⚠️ scilab2py is DEPRECATED — Do NOT use it
`scilab2py` was archived in April 2020 and only supports Scilab **5.x** (explicitly states "This library does not support Scilab 6.0"). Modern Scilab is 2024.x/2026.x. Using scilab2py would mean shipping an incompatible, unmaintained dependency.

**The correct approach**: call the official **Scilab CLI** (`scilab-cli`) via Python `subprocess`. Scilab ships with a headless CLI mode (`-nb -nw`) that executes `.sce` scripts. Gemini generates those scripts; Python runs them.

### Xcos File Generation — Official API
Scilab 2024.x has a first-class scripting API for Xcos diagrams:

| Function | Purpose |
|---|---|
| `loadScicos(); loadXcosLibs();` | Loads Xcos simulation engine and all native block interface functions |
| `scicos_diagram()` | Creates a new empty diagram structure (`scs_m`) |
| `BLOCKNAME("define")` | Instantiates a block (e.g. `BIGSOM_f("define")`, `CONST_m("define")`) |
| `scicos_link()` | Creates a wire/connection between blocks |
| `xcosDiagramToScilab(path, scs_m)` | Saves the diagram as `.xcos` (XML) or `.zcos` (compressed) |
| `scicos_block()` | Raw block structure constructor |
| `scicos_graphics()` | Graphical properties: `orig=[x,y]`, `sz=[w,h]`, port arrays |

A minimal working diagram script looks like:
```scilab
loadXcosLibs();
scs_m = scicos_diagram();
scs_m.props.title = "My Diagram";

// Block 1: constant source
scs_m.objs(1) = CONST_m("define");
scs_m.objs(1).graphics.orig = [100, 200];
scs_m.objs(1).graphics.sz   = [40, 30];
scs_m.objs(1).model.rpar    = 1;    // value = 1

// Block 2: scope
scs_m.objs(2) = CSCOPE("define");
scs_m.objs(2).graphics.orig = [300, 200];
scs_m.objs(2).graphics.sz   = [60, 40];

// Link: block 1 output port 1 → block 2 input port 1
lnk = scicos_link();
lnk.from = [1, 1, 0];   // block 1, port 1, output (0)
lnk.to   = [2, 1, 1];   // block 2, port 1, input  (1)
lnk.xx   = [120; 300];  // x waypoints
lnk.yy   = [215; 220];  // y waypoints
lnk.ct   = [1, 1];       // color 1, regular link

// Update port connection indices on blocks
scs_m.objs(1).graphics.pout = 3;  // link index 3
scs_m.objs(2).graphics.pin  = 3;
scs_m.objs(3) = lnk;

xcosDiagramToScilab("C:/output/my_diagram.xcos", scs_m);
```

### Gemini SDK — Use `google-genai` (not deprecated `google-generativeai`)
`google-generativeai` was officially deprecated in November 2025. The new SDK is `google-genai` (`pip install google-genai`). Usage:
```python
from google import genai
client = genai.Client(api_key="YOUR_KEY")
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="..."
)
print(response.text)
```

---

## 1. Project Overview

**Name**: XcosGen  
**Purpose**: Desktop app where users describe a Scilab Xcos block diagram in natural language; Gemini AI generates the corresponding Scilab script; the app executes it to produce a `.xcos` file openable directly in Scilab.

**Platform**: Windows (primary), with cross-platform architecture  
**Runtime requirements** (for end-users): Scilab 2024.x or 2026.x installed (scilab-cli must be in PATH or user must specify its location), internet connection for Gemini API

---

## 2. Technology Stack

| Layer | Technology | Why |
|---|---|---|
| **GUI window** | `pywebview 5.x` | Wraps system WebView2 (Edge Chromium on Windows); renders local HTML/CSS without a browser binary; bidirectional Python↔JS bridge via `js_api` |
| **Frontend UI** | HTML5 + CSS3 + Vanilla JS | Warm Beige design system; drag-and-drop; console; no framework overhead |
| **AI / LLM** | `google-genai` (Gemini 2.5 Flash) | State-of-the-art code generation; multimodal (can read PDFs/images); free tier available |
| **Scilab integration** | `subprocess` → `scilab-cli -nb -nw -f script.sce` | Official headless CLI; zero deprecated dependencies; works with all Scilab 6+ versions |
| **Config persistence** | `appdirs` + JSON file | Stores API key, Scilab path, last output dir in platform-appropriate config dir |
| **Packaging** | `PyInstaller 6.x` | Bundles Python runtime + all dependencies into a distributable folder |
| **Installer** | **Inno Setup 6.x** | Creates a proper Windows `.exe` installer with Start Menu entry, uninstaller, and PATH configuration |

---

## 3. Repository Structure

```
xcosgem/
│
├── main.py                    # Entry point — creates pywebview window, wires js_api
│
├── app/
│   ├── __init__.py
│   ├── api.py                 # XcosGenAPI class: all methods callable from JS via window.pywebview.api
│   ├── gemini_client.py       # Wraps google-genai; builds prompt; parses response
│   ├── scilab_runner.py       # Finds scilab-cli, writes temp .sce, runs subprocess, captures output
│   ├── config_store.py        # Read/write JSON config (API key, scilab path, output dir)
│   └── log_queue.py           # Thread-safe deque for console log entries; JS polls it
│
├── ui/
│   ├── index.html             # Single-page app (all UI in one file for pywebview simplicity)
│   ├── wb-styles.css          # Warm Beige design system: tokens, keyframes, utilities
│   └── app.js                 # Frontend logic: prompt, files, console, popup, API calls
│
├── assets/
│   ├── icon.ico               # App icon (used by PyInstaller + Inno Setup)
│   └── icon.png               # PNG version for pywebview title bar
│
├── build/
│   ├── build.py               # Runs PyInstaller programmatically with correct settings
│   ├── xcosgen.spec           # PyInstaller spec file (generated by build.py, commit it)
│   └── installer.iss          # Inno Setup script — references dist/ folder
│
├── requirements.txt           # All pip dependencies
└── README.md
```

---

## 4. Module-by-Module Design

### 4.1 `main.py` — Entry Point

```python
import webview
from app.api import XcosGenAPI
import sys, os

def get_ui_path():
    # Works both in dev (file path) and PyInstaller (sys._MEIPASS)
    base = getattr(sys, '_MEIPASS', os.path.dirname(__file__))
    return os.path.join(base, 'ui', 'index.html')

if __name__ == '__main__':
    api = XcosGenAPI()
    window = webview.create_window(
        title='XcosGen',
        url=get_ui_path(),
        js_api=api,
        width=1100,
        height=750,
        min_size=(800, 600),
    )
    # Expose window reference so api can call window.evaluate_js() for push-style logs
    api.set_window(window)
    webview.start(debug=False)
```

**Key points**:
- `js_api=api` makes every public method of `XcosGenAPI` callable from JavaScript as `await window.pywebview.api.method_name(args)`
- `url=get_ui_path()` uses `file://` internally; this works for local HTML + CSS + JS
- No Flask server needed — pywebview can serve a local file directly

---

### 4.2 `app/api.py` — Python↔JS Bridge

All methods must be **non-blocking from the JS perspective**. pywebview wraps calls in Promises automatically. Methods that do long work (Gemini call, Scilab run) must offload to a thread and push logs asynchronously.

```python
import threading, json, queue, os
from app.gemini_client import GeminiClient
from app.scilab_runner import ScilabRunner
from app.config_store import ConfigStore
from app.log_queue import LogQueue
import tkinter as tk
from tkinter import filedialog

class XcosGenAPI:
    def __init__(self):
        self.config = ConfigStore()
        self.logs = LogQueue()
        self._window = None

    def set_window(self, window):
        self._window = window

    # ── Config ──────────────────────────────────────────────────
    def get_config(self) -> dict:
        """Return config dict to JS on startup."""
        return self.config.load()

    def save_config(self, data: dict) -> bool:
        """Save API key and Scilab path from settings modal."""
        self.config.save(data)
        return True

    # ── File Picker (save dialog) ────────────────────────────────
    def pick_save_file(self) -> str | None:
        """Open native save-as dialog; return chosen path or None."""
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.asksaveasfilename(
            defaultextension=".xcos",
            filetypes=[("Xcos Diagram", "*.xcos"), ("Compressed Xcos", "*.zcos")],
            title="Save Xcos Diagram As"
        )
        root.destroy()
        return path or None

    def pick_scilab_exe(self) -> str | None:
        """Open file picker to locate scilab-cli executable."""
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askopenfilename(
            filetypes=[("Executable", "*.exe"), ("All files", "*")],
            title="Locate scilab-cli or scilab executable"
        )
        root.destroy()
        return path or None

    # ── Log polling ──────────────────────────────────────────────
    def get_logs(self) -> list[dict]:
        """JS calls this every 400ms to drain the log queue."""
        return self.logs.drain()

    # ── Main generation flow ─────────────────────────────────────
    def generate_diagram(self, prompt: str, files: list[dict], output_path: str) -> dict:
        """
        Kick off generation in a background thread.
        Returns immediately with {"started": True}.
        Progress is pushed via log queue; completion fires window.evaluate_js().
        """
        cfg = self.config.load()
        api_key = cfg.get("gemini_api_key", "")
        scilab_path = cfg.get("scilab_path", "")

        if not api_key:
            return {"error": "No Gemini API key set. Open Settings to add one."}
        if not output_path:
            return {"error": "No output file selected."}

        thread = threading.Thread(
            target=self._run_generation,
            args=(prompt, files, output_path, api_key, scilab_path),
            daemon=True
        )
        thread.start()
        return {"started": True}

    def _run_generation(self, prompt, files, output_path, api_key, scilab_path):
        """Background thread: Gemini → Scilab script → execute → done."""
        try:
            self.logs.push("info", "Starting generation…")
            self.logs.push("info", f"Output target: {output_path}")

            # 1. Build Gemini client
            self.logs.push("info", "Connecting to Gemini API…")
            client = GeminiClient(api_key)

            # 2. Call Gemini
            self.logs.push("info", "Sending prompt to Gemini 2.5 Flash…")
            sce_script = client.generate_xcos_script(prompt, files, output_path)
            self.logs.push("success", "Gemini returned a Scilab script.")
            self.logs.push("code", sce_script[:500] + ("…" if len(sce_script) > 500 else ""))

            # 3. Execute Scilab
            self.logs.push("info", "Launching Scilab CLI to execute script…")
            runner = ScilabRunner(scilab_path)
            exit_code, stdout, stderr = runner.run_script(sce_script)

            if stdout:
                for line in stdout.splitlines():
                    self.logs.push("scilab", line)
            if stderr:
                for line in stderr.splitlines():
                    self.logs.push("warn", line)

            # 4. Check output
            if os.path.exists(output_path):
                self.logs.push("success", f"✓ Diagram saved: {output_path}")
                if self._window:
                    self._window.evaluate_js(
                        f"window._xcosgenDone(true, {json.dumps(output_path)})"
                    )
            else:
                self.logs.push("error", f"Scilab exited with code {exit_code} but output file not found.")
                if self._window:
                    self._window.evaluate_js(
                        "window._xcosgenDone(false, 'Output file not created. Check console for errors.')"
                    )

        except Exception as e:
            self.logs.push("error", f"Exception: {e}")
            if self._window:
                self._window.evaluate_js(
                    f"window._xcosgenDone(false, {json.dumps(str(e))})"
                )
```

---

### 4.3 `app/gemini_client.py` — Gemini Integration

```python
from google import genai

SYSTEM_PROMPT = """
You are an expert Scilab Xcos diagram builder. Your task is to generate a complete, 
executable Scilab script (.sce) that creates an Xcos block diagram and saves it to disk.

MANDATORY RULES:
1. The script MUST start with
loadScicos();
loadXcosLibs();
2. Create the diagram with: scs_m = scicos_diagram();
3. Use ONLY block names from the Xcos standard library (see list below).
4. Position blocks with non-overlapping coordinates: scs_m.objs(i).graphics.orig = [x, y];
5. Set block sizes: scs_m.objs(i).graphics.sz = [width, height];
6. Set block parameters via .model.rpar (real params) or .graphics.exprs (string params).
7. Create links with scicos_link() and set .from, .to, .xx, .yy, .ct fields.
8. Update pin/pout arrays on connected blocks to the link's index in scs_m.objs.
9. Save using: xcosDiagramToScilab("OUTPUT_PATH", scs_m);
   (The OUTPUT_PATH placeholder will be replaced by the application.)
10. Return ONLY the Scilab code — no markdown fences, no explanation text.

SCICOS_LINK STRUCTURE:
  lnk = scicos_link();
  lnk.from = [src_block_idx, src_port, 0];  // 0 = output side
  lnk.to   = [dst_block_idx, dst_port, 1];  // 1 = input side
  lnk.xx   = [x_src; x_dst];
  lnk.yy   = [y_src; y_dst];
  lnk.ct   = [1, 1];                        // color, type (1=regular, -1=activation, 2=implicit)
  link_idx = length(scs_m.objs) + 1;
  scs_m.objs(link_idx) = lnk;
  // Then update blocks:
  scs_m.objs(src_block_idx).graphics.pout(src_port) = link_idx;
  scs_m.objs(dst_block_idx).graphics.pin(dst_port)  = link_idx;

COMMON BLOCK NAMES (use these exactly):
  Sources:        CONST_m, STEP_FUNCTION, GENSIN_f, CLOCK_c, FROMWSB
  Math:           BIGSOM_f, GAINBLK_f, PRODUCT, ABS_VALUE, SINBLK_f, COSBLK_f,
                  SQRT_f, SUM_f, SUMMATION, MUX, DEMUX
  Continuous:     INTEGRAL_f, DERIVATIVE, PID, CLR, CLSS
  Discrete:       DELAYV_f, SAMPHOLD_m
  Routing:        FROM, GOTO, SWITCH2_m, IF_THEN_ELSE
  Sinks:          CSCOPE, CMSCOPE, AFFICH_m, TOWS_c, WFILE_f
  Sources/Electrical: VsourceAC, Resistor, Capacitor, Inductor, Ground, VoltageSensor
  Logical:        LOGIC, DLATCH, DFLIPFLOP
  Signal:         CLKIN_f, CLKOUT_f, IN_f, OUT_f
"""

class GeminiClient:
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)

    def generate_xcos_script(self, prompt: str, files: list[dict], output_path: str) -> str:
        """
        files: list of {"name": str, "content": str (text content)}
        Returns a Scilab .sce script string.
        """
        parts = [SYSTEM_PROMPT, "\n\nUSER REQUEST:\n", prompt]

        if files:
            parts.append("\n\nATTACHED FILES (use as additional context):\n")
            for f in files:
                parts.append(f"\n--- {f['name']} ---\n{f['content']}\n")

        parts.append(f'\n\nOUTPUT_PATH for xcosDiagramToScilab: "{output_path}"')

        full_prompt = "".join(parts)

        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=full_prompt,
        )

        script = response.text.strip()
        # Strip markdown fences if model adds them despite instructions
        if script.startswith("```"):
            lines = script.splitlines()
            script = "\n".join(
                line for line in lines
                if not line.startswith("```")
            ).strip()

        return script
```

**Key design decisions**:
- The system prompt embeds the full Xcos scripting API so Gemini doesn't need to guess
- `OUTPUT_PATH` is injected into the prompt so the script uses the user's chosen path
- Markdown fence stripping is a defensive safety net
- For file attachments, text content is inlined in the prompt. PDFs/images: extract text with `pdfminer` / `Pillow` (see §7)

---

### 4.4 `app/scilab_runner.py` — Scilab Execution

```python
import subprocess, tempfile, os, shutil, platform

SCILAB_CANDIDATES_WIN = [
    r"C:\Program Files\Scilab-2026.0.1\bin\scilab-cli.exe",
    r"C:\Program Files\Scilab-2025.0.0\bin\scilab-cli.exe",
    r"C:\Program Files\Scilab-2024.1.0\bin\scilab-cli.exe",
    r"C:\Program Files (x86)\Scilab-2024.1.0\bin\scilab-cli.exe",
]

class ScilabRunner:
    def __init__(self, user_path: str = ""):
        self.scilab_exe = self._resolve(user_path)

    def _resolve(self, user_path: str) -> str:
        """Find scilab-cli: user override → PATH → known install locations."""
        if user_path and os.path.isfile(user_path):
            return user_path
        # Try PATH
        found = shutil.which("scilab-cli") or shutil.which("scilab")
        if found:
            return found
        # Try known Windows paths
        if platform.system() == "Windows":
            for p in SCILAB_CANDIDATES_WIN:
                if os.path.isfile(p):
                    return p
        raise FileNotFoundError(
            "scilab-cli not found. Set the path in Settings or ensure Scilab is installed."
        )

    def run_script(self, script: str) -> tuple[int, str, str]:
        """
        Write script to a temp .sce file, execute with scilab-cli -nb -nw,
        return (exit_code, stdout, stderr).
        """
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.sce', delete=False, encoding='utf-8'
        ) as f:
            f.write(script)
            tmp_path = f.name

        try:
            result = subprocess.run(
                [self.scilab_exe, "-nb", "-nw", "-f", tmp_path],
                capture_output=True,
                text=True,
                timeout=120,   # 2-minute timeout; complex diagrams take time to load
                encoding='utf-8',
                errors='replace',
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Scilab execution timed out after 120 seconds."
        finally:
            os.unlink(tmp_path)
```

**Scilab CLI flags used**:
- `-nb` — no banner (suppress startup logo)
- `-nw` — no window (headless, no Scilab GUI)
- `-f script.sce` — execute the file and exit

---

### 4.5 `app/config_store.py` — Persistent Configuration

```python
import json, os
from appdirs import user_config_dir

APP_NAME = "XcosGen"
APP_AUTHOR = "XcosGen"

class ConfigStore:
    def __init__(self):
        config_dir = user_config_dir(APP_NAME, APP_AUTHOR)
        os.makedirs(config_dir, exist_ok=True)
        self.path = os.path.join(config_dir, "config.json")

    def load(self) -> dict:
        if not os.path.exists(self.path):
            return {}
        with open(self.path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save(self, data: dict):
        existing = self.load()
        existing.update(data)
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(existing, f, indent=2)
```

**Security note**: The API key is stored in the user's local config dir (`%APPDATA%\XcosGen\XcosGen\config.json` on Windows). It is never transmitted anywhere except the Gemini API endpoint. On a multi-user machine, this is per-user and not world-readable by default on Windows. For enhanced security in a future version, Windows DPAPI (`win32crypt`) can encrypt the key at rest.

---

### 4.6 `app/log_queue.py` — Thread-safe Console

```python
import threading
from collections import deque
from datetime import datetime

class LogQueue:
    def __init__(self):
        self._q = deque(maxlen=500)
        self._lock = threading.Lock()

    def push(self, level: str, message: str):
        """Called from background thread. Levels: info, success, warn, error, scilab, code."""
        entry = {
            "level": level,
            "message": message,
            "time": datetime.now().strftime("%H:%M:%S"),
        }
        with self._lock:
            self._q.append(entry)

    def drain(self) -> list[dict]:
        """Called from JS poll thread. Returns and clears all pending entries."""
        with self._lock:
            entries = list(self._q)
            self._q.clear()
            return entries
```

---

## 5. Frontend UI — Warm Beige Design System

### 5.1 Layout (`ui/index.html`)

```
┌─────────────────────────────────────────────────────────┐
│  [SVG XcosGen logo]    XcosGen          [⚙ Settings]    │  ← Header bar
├───────────────────────────────────┬─────────────────────┤
│                                   │                     │
│  PROMPT PANEL                     │  CONSOLE PANEL      │
│  ┌─────────────────────────────┐  │  ┌───────────────┐  │
│  │ Describe the diagram...     │  │  │ 10:23:01 info │  │
│  │ (textarea, resizable)       │  │  │ Connecting... │  │
│  └─────────────────────────────┘  │  │ 10:23:02 ok   │  │
│                                   │  │ Gemini resp.  │  │
│  DROP FILES HERE                  │  │ ...           │  │
│  ┌─────────────────────────────┐  │  └───────────────┘  │
│  │ [drag chip] [drag chip]     │  │  [Clear] [Copy all] │
│  └─────────────────────────────┘  │                     │
│                                   │                     │
│  OUTPUT:  [path/to/file.xcos] [📁]│                     │
│                                   │                     │
│           [▶ Generate Diagram]    │                     │
│                                   │                     │
└───────────────────────────────────┴─────────────────────┘
```

### 5.2 Design Tokens (`ui/wb-styles.css`)

Full Warm Beige `:root` block:
```css
:root {
  /* Colors */
  --bg-main:        #F3F1E9;
  --bg-card:        #FFFFFF;
  --bg-surface:     #FAF9F5;
  --text-primary:   #2C2A24;
  --text-secondary: #6B6760;
  --text-muted:     #9E9B95;
  --accent:         #C0392B;
  --accent-hover:   #A93226;
  --accent-glow:    rgba(192, 57, 43, 0.18);
  --accent-subtle:  #FCF0EE;
  --border:         #E4E2D9;
  --border-focus:   #C0392B;
  --shadow-sm:      0 1px 3px rgba(44,42,36,.08);
  --shadow-md:      0 4px 16px rgba(44,42,36,.12);
  --shadow-lg:      0 8px 32px rgba(44,42,36,.16);

  /* Console-specific (dark surface) */
  --console-bg:     #1E1D18;
  --console-text:   #E8E6DC;

  /* Typography */
  --font-heading:   'Merriweather', Georgia, serif;
  --font-body:      'Inter', system-ui, sans-serif;
  --font-mono:      'JetBrains Mono', 'Fira Code', Consolas, monospace;

  /* Spacing / Radius */
  --radius-sm:  8px;
  --radius-md:  12px;
  --radius-lg:  16px;

  /* Log level accent colors */
  --log-info:     #5B8CDB;
  --log-success:  #27AE60;
  --log-warn:     #E67E22;
  --log-error:    #E74C3C;
  --log-scilab:   #8E44AD;
  --log-code:     #2ECC71;
}
```

### 5.3 Keyframes (`ui/wb-styles.css`)

```css
@keyframes fadeIn      { from { opacity:0; transform:translateY(8px) } to { opacity:1; transform:none } }
@keyframes iconPopIn   { 0%{opacity:0;transform:scale(0) translateY(8px)} 70%{transform:scale(1.12) translateY(-2px)} 100%{opacity:1;transform:scale(1) translateY(0)} }
@keyframes tooltipFade { from { opacity:0; transform:translateX(-50%) translateY(4px) } to { opacity:1; transform:translateX(-50%) translateY(0) } }
@keyframes pulseRing   { 0%,100%{box-shadow:0 0 0 0 var(--accent-glow)} 50%{box-shadow:0 0 0 6px transparent} }
@keyframes draw-in     { from { stroke-dashoffset: 200 } to { stroke-dashoffset: 0 } }
@keyframes paint-in    { from { opacity:0 } to { opacity:0.18 } }
@keyframes spin        { to { transform: rotate(360deg) } }
@keyframes logEntry    { from { opacity:0; transform:translateX(-4px) } to { opacity:1; transform:none } }
```

### 5.4 Interactive Components

**Prompt Textarea**
- Grows with content (`field-sizing: content` CSS, fallback via JS `auto`-height)
- Focus: `box-shadow: 0 0 0 3px var(--accent-glow)` + `border-color: var(--border-focus)`

**File Drop Zone**
- Entire textarea row acts as drop target
- `dragover`: border pulses red, background shifts to `var(--accent-subtle)`
- Supports: drag-and-drop files, `Ctrl+V` paste (for copied text/HTML), `<input type="file" multiple>` click
- Accepted types: `.sce`, `.txt`, `.pdf`, `.png`, `.jpg`, `.md`, `.csv` — shown as dismissible chips
- File content is read client-side (FileReader API) and sent to Python as `{name, content}` objects

**Console Panel**
- Dark surface (`--console-bg`) fixed-height, `overflow-y: auto`, auto-scroll to bottom
- Each entry: `[HH:MM:SS]` timestamp + level badge + message
- Level badge colors map to `--log-*` tokens
- `.log-code` entries render in `--font-mono` with subtle green tint
- "Clear" button: clears rendered entries, calls `api.clear_logs()` (bonus)
- "Copy all" button: copies all text to clipboard

**Output File Picker**
- Text input (read-only, shows chosen path)
- `[📁]` button calls `await window.pywebview.api.pick_save_file()` → native save dialog
- On return, updates the input value

**Generate Button**
- `.btn-primary` with `translateY(-1px)` hover lift
- During generation: shows an SVG spinner + "Generating…" text; disabled
- On complete: returns to "Generate Diagram" text

**Settings Modal**
- Slides in from right (`transform: translateX(100%)` → `translateX(0)`)
- Fields: Gemini API Key (password input), Scilab CLI Path (text + browse button)
- Save button calls `api.save_config({gemini_api_key, scilab_path})`

---

## 6. Data Flow — End-to-End

```
User types prompt
       │
       ▼
[Generate Diagram button clicked]
       │
       ├─ JS reads: prompt text, attached file contents, output_path
       ├─ Validates: output_path set? api_key set?
       └─ Calls: await window.pywebview.api.generate_diagram(prompt, files, output_path)
                         │
                         │  (returns {started:true} immediately)
                         │
                         ▼
              Background thread starts
                         │
             ┌───────────────────────────────┐
             │  1. LogQueue.push("info", …)  │
             │  2. GeminiClient.generate_    │
             │     xcos_script(prompt, …)    │
             │     → HTTPS to Gemini API     │
             │     ← returns .sce string     │
             │  3. LogQueue.push("code", …)  │
             │  4. ScilabRunner.run_script() │
             │     → writes tmp .sce file    │
             │     → subprocess scilab-cli   │
             │     ← stdout/stderr captured  │
             │  5. check os.path.exists(out) │
             │  6. window.evaluate_js(       │
             │       "_xcosgenDone(true,…)"  │
             │     )                         │
             └───────────────────────────────┘
                         │
              (every 400ms, JS polls)
       ──────►  await api.get_logs()  ◄──────
                         │
                         ▼
              Console panel receives log entries
              → animated in with logEntry keyframe

              On _xcosgenDone(true, path):
              → success toast + "Open in Scilab" button
              On _xcosgenDone(false, msg):
              → error toast + message in console
```

---

## 7. File Attachment Handling

### Supported formats and extraction strategy

| Extension | How content is extracted |
|---|---|
| `.txt`, `.sce`, `.md`, `.csv` | `FileReader.readAsText()` — send as-is |
| `.pdf` | Python-side: `pdfminer.six` extracts text. JS sends raw ArrayBuffer; Python decodes |
| `.png`, `.jpg`, `.jpeg` | Convert to base64 in JS; send as `{name, type:"image", data: base64}`. In Python: use Gemini's vision input (multimodal parts) |

### JS-side file reading (`app.js`)

```javascript
async function readFile(file) {
    const textTypes = ['text/plain','text/csv','text/markdown','application/x-scilab'];
    if (textTypes.includes(file.type) || /\.(sce|txt|md|csv)$/i.test(file.name)) {
        const text = await file.text();
        return { name: file.name, type: 'text', content: text };
    }
    // Binary: send base64 ArrayBuffer
    const buffer = await file.arrayBuffer();
    const bytes = new Uint8Array(buffer);
    const b64 = btoa(String.fromCharCode(...bytes));
    return { name: file.name, type: 'binary', content: b64 };
}
```

### Python-side binary handling (`gemini_client.py`)
For binary files (PDF/image), `GeminiClient.generate_xcos_script()` uses Gemini's multimodal Parts API:
```python
from google.genai import types as genai_types

parts = [genai_types.Part(text=system_prompt + "\n\nUSER:\n" + prompt)]
for f in files:
    if f.get("type") == "binary":
        import base64
        mime = "application/pdf" if f["name"].endswith(".pdf") else "image/png"
        parts.append(genai_types.Part(
            inline_data=genai_types.Blob(
                mime_type=mime,
                data=base64.b64decode(f["content"])
            )
        ))
    else:
        parts.append(genai_types.Part(text=f"\n--- {f['name']} ---\n{f['content']}"))

response = self.client.models.generate_content(model="gemini-2.5-flash", contents=parts)
```

---

## 8. Installer & Distribution

### 8.1 PyInstaller Build (`build/build.py`)

```python
import PyInstaller.__main__

PyInstaller.__main__.run([
    'main.py',
    '--name=XcosGen',
    '--onedir',          # folder bundle, not single-file (faster startup)
    '--windowed',        # no console window (we have our own console in UI)
    '--icon=assets/icon.ico',
    '--add-data=ui;ui',  # bundle the entire ui/ folder
    '--add-data=assets;assets',
    '--hidden-import=google.genai',
    '--hidden-import=webview',
    '--hidden-import=pdfminer',
    '--hidden-import=appdirs',
    '--collect-all=webview',
    '--collect-all=google.genai',
    '--noconfirm',
    '--distpath=dist',
    '--workpath=build_tmp',
    '--specpath=build',
])
```

**output**: `dist/XcosGen/XcosGen.exe` + all DLLs/libs in `dist/XcosGen/`

### 8.2 Inno Setup Script (`build/installer.iss`)

```iss
[Setup]
AppName=XcosGen
AppVersion=1.0.0
AppPublisher=XcosGen
DefaultDirName={autopf}\XcosGen
DefaultGroupName=XcosGen
OutputDir=dist
OutputBaseFilename=XcosGen_Setup_v1.0.0
SetupIconFile=assets\icon.ico
Compression=lzma2/ultra64
PrivilegesRequired=lowest   ; install to user folder without admin

[Files]
Source: "dist\XcosGen\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{group}\XcosGen";     Filename: "{app}\XcosGen.exe"
Name: "{userdesktop}\XcosGen"; Filename: "{app}\XcosGen.exe"

[Run]
Filename: "{app}\XcosGen.exe"; Description: "Launch XcosGen"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
```

**Build steps to create the final installer**:
1. `pip install pyinstaller` (on build machine)
2. `python build/build.py` → generates `dist/XcosGen/`
3. Open Inno Setup → compile `build/installer.iss` → produces `dist/XcosGen_Setup_v1.0.0.exe`
4. Distribute `XcosGen_Setup_v1.0.0.exe` — it is self-contained; users do NOT need Python

### 8.3 `requirements.txt`

```
pywebview>=5.0.0
google-genai>=1.5.0
appdirs>=1.4.4
pdfminer.six>=20221105
Pillow>=10.0.0
pyinstaller>=6.0.0   # dev/build only
```

---

## 9. Scilab Xcos Scripting — Reference for the Gemini Prompt

This section documents every interaction Gemini needs to know about. It is embedded verbatim in the system prompt.

### Block port indexing rules
- **`scs_m.objs` is 1-indexed** (Scilab uses 1-based arrays)
- Blocks occupy indices 1…N, links occupy the remaining indices
- When adding a link, its index is `length(scs_m.objs) + 1` before inserting

### Connecting blocks correctly
```scilab
// Suppose block 1 has 1 output, block 2 has 1 input.
// Link will be scs_m.objs(3).

lnk = scicos_link();
lnk.from = [1, 1, 0];  // from block 1, port 1, output side
lnk.to   = [2, 1, 1];  // to   block 2, port 1, input side
lnk.xx   = [scs_m.objs(1).graphics.orig(1) + scs_m.objs(1).graphics.sz(1);
             scs_m.objs(2).graphics.orig(1)];
lnk.yy   = [scs_m.objs(1).graphics.orig(2) + scs_m.objs(1).graphics.sz(2)/2;
             scs_m.objs(2).graphics.orig(2) + scs_m.objs(2).graphics.sz(2)/2];
lnk.ct   = [1, 1];
scs_m.objs(3) = lnk;

// CRITICAL — update port arrays on both blocks:
scs_m.objs(1).graphics.pout = 3;   // block 1's output port 1 is linked to obj 3
scs_m.objs(2).graphics.pin  = 3;   // block 2's input port 1 is linked from obj 3
```

### Setting block parameters
```scilab
// CONST_m: set constant value
blk = CONST_m("define");
blk.model.rpar = 5.0;      // constant value = 5
blk.graphics.exprs = "5";  // display expression

// GAINBLK_f: set gain
blk = GAINBLK_f("define");
blk.model.rpar = 2.5;
blk.graphics.exprs = "2.5";

// STEP_FUNCTION: step signal
// model.rpar = [step_time, initial_value, final_value]
blk = STEP_FUNCTION("define");
blk.model.rpar = [1, 0, 1];  // step at t=1 from 0→1

// GENSIN_f: sinusoidal source
// model.rpar = [magnitude, frequency, phase]
blk = GENSIN_f("define");
blk.model.rpar = [1, 1, 0];  // amp=1, freq=1 Hz, phase=0

// CSCOPE: oscilloscope (sink)
blk = CSCOPE("define");       // default settings usually fine
```

### scicos_diagram properties
```scilab
scs_m = scicos_diagram();
scs_m.props.title     = "My Diagram";   // diagram title
scs_m.props.tol       = [1e-6, 1e-8, 1e-10, 100, 0, 1, 0, 0, 0];  // simulation tolerances
scs_m.props.tf        = 10;   // final simulation time
scs_m.props.context   = "";   // Scilab context code (variables available in diagram)
```

### Activation (clock) links
Event/activation links use `ct = [1, -1]` (type = -1 for activation):
```scilab
clk_lnk = scicos_link();
clk_lnk.from = [clock_block_idx, 1, 0];
clk_lnk.to   = [discrete_block_idx, 1, 1];
clk_lnk.ct   = [1, -1];  // activation link
```
Update `peout`/`pein` (not `pout`/`pin`) on the respective blocks.

---

## 10. Error Handling Strategy

| Failure point | Detection | User feedback |
|---|---|---|
| No API key | `api_key == ""` before Gemini call | Error toast immediately |
| Scilab not found | `FileNotFoundError` in `ScilabRunner._resolve()` | Error log + link to Settings to browse for exe |
| Gemini API error | `google.genai` exception | Log error stacktrace; show message to user |
| Gemini returns non-Scilab text | Heuristic: does script contain `loadXcosLibs`? | Warn user + show generated text for inspection |
| Scilab script syntax error | `exit_code != 0` or `stderr` contains `!--error` | Show full Scilab stderr in console |
| Output file not created | `not os.path.exists(output_path)` | Error with hint to check console |
| Scilab timeout | `subprocess.TimeoutExpired` | "Timed out after 120s" + suggest simpler diagram |
| File read error (attachment) | `FileReader.onerror` in JS | Dismiss chip, show warning in console |

---

## 11. Security Considerations

1. **API key storage**: Stored in `%APPDATA%\XcosGen\` (Windows). Never logged. Never sent to any server except `generativelanguage.googleapis.com`. Shown as password field with reveal toggle.
2. **Scilab subprocess**: The executed `.sce` file is written to `tempfile.gettempdir()` (e.g. `%TEMP%`) and deleted after execution. The `output_path` comes from a native save dialog (no path injection from Gemini). The Gemini-generated script runs with the user's own Scilab installation permissions — no privilege escalation.
3. **File content in prompt**: File content is sent to Google's API. Users should not attach files with sensitive personal data. A warning is shown in the drop zone.
4. **Input sanitization**: `output_path` is validated with `os.path.isabs()` and checked to not contain shell metacharacters before being embedded in the script string.
5. **No `eval()`** in JavaScript; no `exec()` in Python for user-provided strings.
6. **CORS**: pywebview's WebView2 runs local `file://` pages — no CORS issues, no external HTTP server exposed.

---

## 12. Implementation Phases

### Phase 1 — Core Pipeline (Day 1–2)
- [ ] `requirements.txt` + `venv` setup
- [ ] `app/config_store.py` — JSON config with `appdirs`
- [ ] `app/log_queue.py` — thread-safe deque
- [ ] `app/scilab_runner.py` — subprocess wrapper, auto-detect scilab-cli
- [ ] `app/gemini_client.py` — google-genai integration, system prompt
- [ ] `app/api.py` — `XcosGenAPI` class with all bridge methods
- [ ] `main.py` — pywebview window creation

**Validation**: Run from CLI, call `api.generate_diagram()` with a hardcoded test prompt, verify `.xcos` file is produced and opens in Scilab.

### Phase 2 — UI (Day 3–4)
- [ ] `ui/wb-styles.css` — full Warm Beige token set + all keyframes
- [ ] `ui/index.html` — layout: header, prompt panel, file zone, console, output row, generate button
- [ ] `ui/app.js` — file drag/drop/paste logic
- [ ] `ui/app.js` — log polling loop (setInterval 400ms)
- [ ] `ui/app.js` — Settings modal with save
- [ ] `ui/app.js` — generate flow: gather inputs → call api → handle `_xcosgenDone`
- [ ] Animated SVG icons: logo (gear + circuit), file drop (inbox), settings (gear), generate (rocket/arrow)

**Validation**: Full UI flow — prompt → generate → see logs stream in — see success/failure.

### Phase 3 — Polish & Edge Cases (Day 5)
- [ ] File attachment: PDF handling (pdfminer), image (base64 to Gemini vision)
- [ ] Settings: Scilab path browse button
- [ ] Error toasts (fade-in/out animations)
- [ ] "Open in Scilab" button after success (calls `os.startfile(output_path)` on Windows)
- [ ] Retry logic: if Scilab errors, offer "Retry with error context" → sends Scilab stderr back to Gemini for a fixed script
- [ ] Window title update with diagram name

### Phase 4 — Packaging (Day 6)
- [ ] `assets/icon.ico` (256×256 + 48×48 + 32×32 + 16×16)
- [ ] `build/build.py` PyInstaller config
- [ ] Test PyInstaller output: run `dist/XcosGen/XcosGen.exe`, verify no import errors
- [ ] `build/installer.iss` Inno Setup script
- [ ] Build and test final installer on a clean Windows machine (or VM)
- [ ] Write `README.md`

---

## 13. Recommended Gemini Model Configuration

| Parameter | Value | Reason |
|---|---|---|
| Model | `gemini-2.5-flash` | Best price/performance for code generation; 1M token context |
| Temperature | `0.2` (via `config` param) | Low temp for deterministic code output |
| Max output tokens | `8192` | Xcos scripts with 20+ blocks fit easily in 4K; headroom for complex diagrams |
| System instruction | Embedded in `contents[0]` (google-genai doesn't have a dedicated system field in the same way as OpenAI) |

For the retry flow (send Scilab error back):
```python
retry_prompt = (
    f"The following Scilab script you generated produced this error:\n\n"
    f"ERROR:\n{stderr}\n\n"
    f"ORIGINAL SCRIPT:\n{original_script}\n\n"
    f"Please fix the script so it runs without errors and produces the Xcos file."
)
```

---

## 14. Testing Plan

### Unit tests (pytest)
- `test_config_store.py` — read/write/update cycle
- `test_log_queue.py` — concurrent push/drain
- `test_scilab_runner.py` — mock subprocess, verify arg construction
- `test_gemini_client.py` — mock google-genai, verify prompt construction and response parsing

### Integration tests
- `test_e2e_simple.py` — given a live Gemini API key and Scilab install, generate "a sine wave going into a scope" and verify the `.xcos` file is created and is valid XML

### Manual UI tests
- File drag-and-drop from `.sce` file
- Copy/paste a block of text into the drop zone
- Settings save/restore persists across app restart
- Error when no API key is set
- Error when Scilab not found
- Long diagram (10+ blocks) generates without timeout

---

## 15. Known Limitations & Future Work

| Limitation | Future solution |
|---|---|
| Gemini sometimes gets `pout`/`pin` indexing wrong on complex diagrams | Add a post-processing validator in Python that parses the `.sce` script and checks link-block consistency before execution |
| No diagram preview before execution | Parse the generated `.sce` and render a rough block diagram using `mxGraph` or `cytoscape.js` in the UI |
| Scilab must be installed by user | Bundle a portable Scilab — legal if distributing the standard Scilab binary; check GPL-compatible Scilab license |
| PDF text extraction is imperfect for formula-heavy PDFs | Add Gemini vision for PDF pages (pass each page as an image) |
| Single file output only | Allow batch generation: multiple prompts → multiple `.xcos` files |
| No undo/history | Store last N generated scripts in config dir; show "Previous Diagrams" panel |
