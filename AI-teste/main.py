"""main.py — XcosGen entry point."""

import sys
import os

import webview

from app.api import XcosGenAPI


def main() -> None:
    api = XcosGenAPI()

    # Resolve ui/ path relative to this file (works both in dev and PyInstaller)
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    ui_path = os.path.join(base, "ui", "index.html")

    window = webview.create_window(
        "XcosGen — AI Xcos Diagram Generator",
        url=ui_path,
        js_api=api,
        width=1200,
        height=800,
        min_size=(900, 640),
        background_color="#F5F0E8",  # warm beige base
        zoomable=False,
        confirm_close=False,
    )

    api.set_window(window)

    # Launch with Edge WebView2 on Windows, default renderer elsewhere
    webview.start(
        debug="--dev" in sys.argv,
    )


if __name__ == "__main__":
    main()
