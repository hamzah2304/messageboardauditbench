"""Find the local Chrome/Chromium executable used to render publication figures."""
from __future__ import annotations

import os
import shutil
from pathlib import Path


def find_chromium() -> str:
    override = os.environ.get("CHROME_BIN")
    if override:
        executable = shutil.which(os.path.expanduser(override))
        if not executable:
            raise RuntimeError("CHROME_BIN must name an executable Chrome/Chromium binary")
        return executable
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        executable = shutil.which(name)
        if executable:
            return executable
    candidates = [
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
    ]
    for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        if os.environ.get(variable):
            candidates.append(Path(os.environ[variable]) / "Google/Chrome/Application/chrome.exe")
    for path in candidates:
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    raise RuntimeError("Install Chrome/Chromium or set CHROME_BIN to its executable path")
