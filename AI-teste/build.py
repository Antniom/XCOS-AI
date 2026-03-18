"""
build.py — One-command build pipeline for XcosGen
Run from the project root:
    python build.py              → PyInstaller only
    python build.py --installer  → PyInstaller + Inno Setup
    python build.py --dev        → Launch app in dev mode (no build)
"""

import argparse
import os
import shutil
import subprocess
import sys


ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist", "XcosGen")
SPEC = os.path.join(ROOT, "installer", "xcosgen.spec")
ISS  = os.path.join(ROOT, "installer", "setup.iss")


def banner(msg: str) -> None:
    print(f"\n{'═'*58}\n  {msg}\n{'═'*58}")


def run(cmd: list, **kwargs) -> int:
    print(f"  » {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, **kwargs)
    return result.returncode


def ensure_deps() -> None:
    banner("Checking / installing Python dependencies")
    rc = run([sys.executable, "-m", "pip", "install", "-r",
              os.path.join(ROOT, "requirements.txt"), "--quiet"])
    if rc != 0:
        sys.exit("pip install failed — check your network and Python environment.")
    # Install PyInstaller separately (it's in build requirements)
    run([sys.executable, "-m", "pip", "install", "pyinstaller>=6.0.0", "--quiet"])


def build_exe() -> None:
    banner("Building executable with PyInstaller")

    # Clean previous dist
    if os.path.exists(DIST):
        print(f"  Removing old dist: {DIST}")
        shutil.rmtree(DIST)

    rc = run([
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        SPEC,
        f"--distpath={os.path.join(ROOT, 'dist')}",
        f"--workpath={os.path.join(ROOT, 'build_tmp')}",
        f"--log-level=WARN",
    ], cwd=ROOT)

    if rc != 0:
        sys.exit("PyInstaller build failed.")

    print(f"\n  Output: {DIST}")


def build_installer() -> None:
    banner("Building Windows installer with Inno Setup")

    # Try to find iscc (Inno Setup Compiler)
    iscc = shutil.which("iscc") or shutil.which("ISCC")
    if not iscc:
        # Common default install paths
        candidates = [
            r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            r"C:\Program Files\Inno Setup 6\ISCC.exe",
        ]
        for c in candidates:
            if os.path.exists(c):
                iscc = c
                break

    if not iscc:
        print("  ⚠  Inno Setup not found. Skipping installer creation.")
        print("     Install Inno Setup 6 from https://jrsoftware.org/isinfo.php")
        print(f"     Then run manually:  iscc \"{ISS}\"")
        return

    out_dir = os.path.join(ROOT, "dist", "installer")
    os.makedirs(out_dir, exist_ok=True)

    rc = run([iscc, ISS], cwd=ROOT)
    if rc != 0:
        sys.exit("Inno Setup compilation failed.")

    # Find the produced Setup file
    for f in os.listdir(out_dir):
        if f.endswith(".exe"):
            print(f"\n  Installer: {os.path.join(out_dir, f)}")
            break


def dev_mode() -> None:
    banner("Launching XcosGen in development mode")
    os.execv(sys.executable, [sys.executable, os.path.join(ROOT, "main.py"), "--dev"])


def main() -> None:
    parser = argparse.ArgumentParser(description="XcosGen build tool")
    parser.add_argument("--installer", action="store_true",
                        help="Also build Windows installer with Inno Setup")
    parser.add_argument("--dev", action="store_true",
                        help="Launch app in dev mode (no build)")
    parser.add_argument("--skip-deps", action="store_true",
                        help="Skip pip install step")
    args = parser.parse_args()

    if args.dev:
        dev_mode()
        return

    if not args.skip_deps:
        ensure_deps()

    build_exe()

    if args.installer:
        build_installer()

    banner("Build complete")
    print(f"  Executable: {os.path.join(DIST, 'XcosGen.exe')}")
    print()


if __name__ == "__main__":
    main()
