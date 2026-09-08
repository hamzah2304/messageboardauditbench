import pytest

from viewers import browser_executable


def test_explicit_browser_override(monkeypatch):
    monkeypatch.setenv("CHROME_BIN", "/custom/chrome")
    monkeypatch.setattr(browser_executable.shutil, "which", lambda name: name)
    assert browser_executable.find_chromium() == "/custom/chrome"


def test_invalid_override_fails_instead_of_silently_using_another_browser(monkeypatch):
    monkeypatch.setenv("CHROME_BIN", "/missing/chrome")
    monkeypatch.setattr(browser_executable.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="CHROME_BIN"):
        browser_executable.find_chromium()


def test_chromium_on_path(monkeypatch):
    monkeypatch.delenv("CHROME_BIN", raising=False)
    monkeypatch.setattr(browser_executable.shutil, "which",
                        lambda name: "/usr/bin/chromium" if name == "chromium" else None)
    assert browser_executable.find_chromium() == "/usr/bin/chromium"
