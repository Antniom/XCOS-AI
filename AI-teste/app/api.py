import base64
import json
import mimetypes
import os
import threading

from app.config_store import ConfigStore
from app.gemini_client import GeminiClient
from app.log_queue import LogQueue


def _prepare_files(files: list, log) -> list:
    """
    Convert JS-side file descriptors into the format expected by GeminiClient:
        {"name": str, "type": "text" | "binary", "content": str}
    Handles both disk-path files and dataUrl (paste/drag) files.
    """
    result = []
    for f in files:
        name = f.get("name", "attachment")
        path = f.get("path", "")
        data_url = f.get("dataUrl", "")

        if path and os.path.isfile(path):
            size = os.path.getsize(path)
            log("info", f"Reading attachment from disk: {name} ({size:,} bytes)")
            mime, _ = mimetypes.guess_type(path)
            is_text = (mime or "").startswith("text") or name.lower().endswith(
                (".sce", ".sci", ".m", ".txt", ".csv", ".xcos", ".xml")
            )
            try:
                if is_text:
                    with open(path, "r", encoding="utf-8", errors="replace") as fh:
                        result.append({"name": name, "type": "text", "content": fh.read()})
                else:
                    with open(path, "rb") as fh:
                        raw = fh.read()
                    result.append({
                        "name": name,
                        "type": "binary",
                        "content": base64.b64encode(raw).decode(),
                    })
            except Exception as e:
                log("warn", f"Could not read {name}: {e}")

        elif data_url:
            log("info", f"Reading attachment from clipboard/paste: {name}")
            # dataUrl format: "data:<mime>;base64,<data>"
            try:
                header, encoded = data_url.split(",", 1)
                mime = header.split(":")[1].split(";")[0]
                result.append({
                    "name": name,
                    "type": "binary",
                    "content": encoded,
                    "mime": mime,
                })
            except Exception as e:
                log("warn", f"Could not decode dataUrl for {name}: {e}")
        else:
            log("warn", f"Skipping attachment '{name}' — no path or data available")

    return result


class XcosGenAPI:
    """
    Public API exposed to the pywebview JS frontend via js_api.
    Every public method is callable from JavaScript as:
        await window.pywebview.api.method_name(args)
    Long-running methods offload to a background thread and communicate
    progress via LogQueue, which JS drains every 400 ms.
    """

    def __init__(self):
        self.config = ConfigStore()
        self.logs = LogQueue()
        self._window = None
        self._busy = False

    def set_window(self, window) -> None:
        self._window = window

    # ── Configuration ──────────────────────────────────────────────────────

    def get_config(self) -> dict:
        """Called on startup to pre-fill Settings fields."""
        cfg = self.config.load()
        # Never expose raw key in full; return masked version for display
        key = cfg.get("gemini_api_key", "")
        return {
            "gemini_api_key": key,
            "scilab_path": cfg.get("scilab_path", ""),
        }

    def save_config(self, data: dict) -> dict:
        """Save Settings form values."""
        # Validate keys we accept
        allowed = {"gemini_api_key", "scilab_path"}
        clean = {k: str(v) for k, v in data.items() if k in allowed}
        self.config.save(clean)
        return {"ok": True}

    # ── Native dialogs ──────────────────────────────────────────────────────

    def pick_save_file(self) -> str:
        """Open a native Save As dialog. Returns path string or empty string."""
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = filedialog.asksaveasfilename(
                defaultextension=".xcos",
                filetypes=[
                    ("Xcos Diagram", "*.xcos"),
                    ("Compressed Xcos", "*.zcos"),
                ],
                title="Save Xcos Diagram As",
            )
            root.destroy()
            return path or ""
        except Exception as e:
            self.logs.push("error", f"File dialog error: {e}")
            return ""

    def pick_scilab_exe(self) -> str:
        """Open a file picker to locate scilab-cli. Returns path or empty string."""
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = filedialog.askopenfilename(
                filetypes=[
                    ("Executable", "*.exe"),
                    ("All files", "*"),
                ],
                title="Locate scilab-cli.exe",
            )
            root.destroy()
            return path or ""
        except Exception as e:
            self.logs.push("error", f"File dialog error: {e}")
            return ""

    # ── Log polling ─────────────────────────────────────────────────────────

    def get_logs(self) -> list:
        """Drain the log queue. JS calls this every 400 ms."""
        return self.logs.drain()

    def is_busy(self) -> bool:
        return self._busy

    # ── Manual Diagnostics / External AI Integrations ──────────────────────

    def get_system_prompt(self) -> str:
        """Returns the current SYSTEM_PROMPT for manual copying."""
        try:
            from app.gemini_client import SYSTEM_PROMPT
            return SYSTEM_PROMPT
        except Exception as e:
            return f"Error loading system prompt: {e}"

    def get_reference_blocks(self) -> str:
        """Returns the content of reference_blocks.xcos."""
        try:
            import re
            reference_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reference_blocks.xcos")
            if os.path.exists(reference_path):
                with open(reference_path, "r", encoding="utf-8") as f:
                    content = f.read()
                # apply same token optimization
                content = re.sub(r'^[ \t]+', '', content, flags=re.MULTILINE)
                return re.sub(r'\n+', '\n', content)
            return "Error: reference_blocks.xcos not found"
        except Exception as e:
            return f"Error loading reference blocks: {e}"

    def copy_reference_file_to_clipboard(self) -> dict:
        """Copies the actual file object reference_blocks.xcos to the clipboard."""
        import subprocess
        import os
        import platform
        try:
            reference_path = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "reference_blocks.xcos"))
            if not os.path.exists(reference_path):
                return {"error": "reference_blocks.xcos not found"}
            
            if platform.system() == "Windows":
                # Uses PowerShell to place the file object in the OS clipboard
                CREATE_NO_WINDOW = 0x08000000
                subprocess.run(
                    ["powershell", "-command", f"Get-Item '{reference_path}' | Set-Clipboard"], 
                    check=True, 
                    creationflags=CREATE_NO_WINDOW
                )
                return {"ok": True, "method": "copied"}
            elif platform.system() == "Darwin":
                # Fallback for Mac: open in Finder highlighted, so user can easily drag
                subprocess.run(["open", "-R", reference_path])
                return {"ok": True, "method": "revealed"}
            else:
                return {"ok": False, "error": "OS not supported for file copying"}
        except Exception as e:
            return {"error": str(e)}

    def run_manual_xml(self, xml_code: str, output_path: str) -> dict:
        """Writes manually provided XML and directly notifies success."""
        if self._busy:
            return {"error": "Already busy. Please wait."}
        if not output_path:
            return {"error": "No output file selected."}
        if not xml_code.strip():
            return {"error": "XML code is empty."}
            
        self._busy = True
        t = threading.Thread(
            target=self._run_manual_xml_thread,
            args=(xml_code, output_path),
            daemon=True,
        )
        t.start()
        return {"started": True}

    def _run_manual_xml_thread(self, xml_code: str, output_path: str) -> None:
        try:
            self.logs.push("info", "─── Manual Override ───")
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(xml_code)
            self.logs.push("success", f"Manual XML saved to {output_path}")
            self._finish(True, output_path)
        except Exception as e:
            self.logs.push("error", f"Failed to save manual XML: {e}")
            self._finish(False, str(e))

    # ── Generation ──────────────────────────────────────────────────────────

    def generate_diagram(self, prompt: str, files: list, output_path: str, model_name: str = "gemini-flash-latest") -> dict:
        """
        Kick off diagram generation in a background thread.
        Returns {"started": True} immediately, or {"error": "..."} if pre-check fails.
        """
        if self._busy:
            return {"error": "Already generating a diagram. Please wait."}

        cfg = self.config.load()
        api_key = cfg.get("gemini_api_key", "").strip()

        if not api_key:
            return {
                "error": "No Gemini API key set. Open Settings (gear icon) to add one."
            }
        if not output_path:
            return {"error": "No output file selected. Click the folder icon to choose a save location."}

        self._busy = True
        t = threading.Thread(
            target=self._run_generation,
            args=(prompt, files, output_path, api_key, model_name),
            daemon=True,
        )
        t.start()
        return {"started": True}

    def _run_generation(
        self,
        prompt: str,
        files: list,
        output_path: str,
        api_key: str,
        model_name: str,
    ) -> None:
        """Background thread: Gemini -> .xcos XML -> write to disk -> notify JS."""
        try:
            self.logs.push("info", "─── Generation started ───")
            self.logs.push("info", f"Output target: {output_path}")
            self.logs.push("info", f"Attached files: {len(files)}")

            # 1 -- Prepare file attachments (read from disk / decode dataUrl)
            self.logs.push("info", f"Processing {len(files)} attachment(s)...")
            prepared_files = _prepare_files(files, self.logs.push)
            self.logs.push(
                "info",
                f"{len(prepared_files)} attachment(s) ready for Gemini "
                f"({sum(1 for f in prepared_files if f['type']=='binary')} binary, "
                f"{sum(1 for f in prepared_files if f['type']=='text')} text)",
            )

            # 2 -- Gemini generates .xcos XML
            self.logs.push("info", f"Connecting to Gemini API ({model_name})...")
            client = GeminiClient(api_key)

            self.logs.push("info", "Sending prompt + attachments to Gemini -- waiting for response...")
            xml_content = client.generate_xcos_xml(prompt, prepared_files, model_name=model_name, log_push=self.logs.push)

            xml_lines = xml_content.splitlines()
            self.logs.push("success", f"Gemini returned XML ({len(xml_content):,} chars, {len(xml_lines)} lines).")
            preview = "\n".join(xml_lines[:30])
            if len(xml_lines) > 30:
                preview += f"\n... ({len(xml_lines) - 30} more lines)"
            self.logs.push("code", preview)

            # Sanity checks
            if "<XcosDiagram" not in xml_content:
                self.logs.push(
                    "warn",
                    "Response does not contain '<XcosDiagram'. "
                    "Gemini may have returned non-XML content.",
                )
            if not xml_content.rstrip().endswith("</XcosDiagram>"):
                self.logs.push(
                    "error",
                    "Gemini response is truncated -- the XML is missing its "
                    "closing </XcosDiagram> tag (output-token limit hit). "
                    "Try a simpler diagram, fewer blocks, or a shorter prompt.",
                )
                self._finish(False, "Truncated XML -- try a simpler diagram.")
                return

            block_count = xml_content.count("<BasicBlock")
            self.logs.push("info", f"Blocks found in XML: {block_count}")

            # 3 -- Write XML to disk
            self.logs.push("info", "Writing .xcos file to disk...")
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as fh:
                fh.write(xml_content)

            size = os.path.getsize(output_path)
            self.logs.push("success", f"Diagram saved: {output_path} ({size:,} bytes)")
            self._finish(True, output_path)

        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            self.logs.push("error", msg)
            self._finish(False, msg)

        finally:
            self._busy = False

    def retry_with_error(self, error_context: str) -> dict:
        """
        Re-send the last generated script to Gemini along with the Scilab
        error message, asking it to fix the script.
        """
        if self._busy:
            return {"error": "Already generating. Please wait."}
        return {"error": "No previous script to retry. Generate a diagram first."}

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _finish(self, success: bool, payload: str) -> None:
        """Push completion event back to JS via evaluate_js."""
        if self._window:
            js_payload = json.dumps(payload).replace("\\", "\\\\")
            self._window.evaluate_js(
                f"window._xcosgenDone({str(success).lower()}, {json.dumps(payload)})"
            )
