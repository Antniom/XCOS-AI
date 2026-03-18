import subprocess
import tempfile
import os
import shutil
import platform
import glob

# Executable names to look for inside a Scilab bin/ directory (preference order).
# Scilex.exe  — console-subsystem binary (Scilab 2026 headless, equivalent to -nwni)
# scilab-cli.exe — older headless binary (Scilab 2024 and earlier)
# WScilex-cli.exe — Win32-subsystem CLI; may hang in subprocess, use as last resort
SCILAB_CLI_NAMES = ["Scilex.exe", "scilab-cli.exe", "WScilex-cli.exe", "scilab-cli", "WScilex-cli"]

# Base directories that may contain a scilab-XXXX subfolder
_WIN_PROGRAM_DIRS = [
    r"C:\Program Files",
    r"C:\Program Files (x86)",
]


def _find_scilab_win() -> str | None:
    """Scan Program Files for any scilab-* install and return first CLI found."""
    for base in _WIN_PROGRAM_DIRS:
        if not os.path.isdir(base):
            continue
        # Sort descending so newest version wins (e.g. scilab-2026 before scilab-2024)
        candidates = sorted(
            (d for d in os.listdir(base) if d.lower().startswith("scilab")),
            reverse=True,
        )
        for folder in candidates:
            bin_dir = os.path.join(base, folder, "bin")
            for exe_name in SCILAB_CLI_NAMES:
                full = os.path.join(bin_dir, exe_name)
                if os.path.isfile(full):
                    return full
    return None


class ScilabNotFoundError(FileNotFoundError):
    pass


class ScilabRunner:
    def __init__(self, user_path: str = ""):
        self.scilab_exe = self._resolve(user_path)

    def _resolve(self, user_path: str) -> str:
        """
        Find scilab CLI executable.
        Priority: user override → PATH → dynamic Program Files scan.
        Raises ScilabNotFoundError if nothing found.
        """
        if user_path and os.path.isfile(user_path):
            return user_path

        # Try PATH (catches user-added entries) — prefer headless binaries
        for name in ("Scilex", "scilab-cli", "WScilex-cli", "scilab"):
            found = shutil.which(name)
            if found:
                return found

        # Dynamically scan known install roots on Windows
        if platform.system() == "Windows":
            found = _find_scilab_win()
            if found:
                return found

        raise ScilabNotFoundError(
            "Scilab CLI not found. Please set the Scilab executable path in Settings "
            "(e.g. C:\\Program Files\\scilab-2026.0.1\\bin\\WScilex-cli.exe), "
            "or ensure Scilab is installed."
        )

    def run_script(self, script: str) -> tuple:
        """
        Write script to a temp .sce file, execute headlessly with:
            scilab-cli -nb -f <temp.sce>
        Note: -nw was removed in Scilab 2026.
        Returns (exit_code: int, stdout: str, stderr: str).
        The temp file is always deleted after execution.
        """
        tmp_path = None
        try:
            # Ensure quit() is at the end before writing the file
            if "quit()" not in script:
                script = script.rstrip() + "\nquit();\n"

            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".sce",
                delete=False,
                encoding="utf-8",
                prefix="xcosgem_",
            ) as f:
                f.write(script)
                tmp_path = f.name

            result = subprocess.run(
                [self.scilab_exe, "-nb", "-f", tmp_path],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=600,
                encoding="utf-8",
                errors="replace",
            )
            return result.returncode, result.stdout, result.stderr

        except subprocess.TimeoutExpired:
            return -1, "", "Scilab execution timed out after 600 seconds."
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    @property
    def exe_path(self) -> str:
        return self.scilab_exe
