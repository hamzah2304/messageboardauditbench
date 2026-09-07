"""Unit checks for isolation controls that do not need credentials or a model call."""
from __future__ import annotations

import importlib.util
import socket
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mbab_proxy", ROOT / "sandbox" / "proxy.py")
assert spec and spec.loader
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)
preflight_spec = importlib.util.spec_from_file_location(
    "mbab_isolation_preflight", ROOT / "sandbox" / "isolation_preflight.py"
)
assert preflight_spec and preflight_spec.loader
preflight = importlib.util.module_from_spec(preflight_spec)
preflight_spec.loader.exec_module(preflight)


@pytest.mark.parametrize(
    ("agent", "host", "expected"),
    [
        ("claude", "api.anthropic.com", True),
        ("claude", "API.ANTHROPIC.COM.", True),
        ("claude", "evil.api.anthropic.com", False),
        ("claude", "api.openai.com", False),
        ("codex", "api.openai.com", True),
        ("react", "openrouter.ai", True),
    ],
)
def test_proxy_allowlist_is_exact_and_agent_scoped(agent: str, host: str, expected: bool) -> None:
    assert proxy.allowed_host(host, agent) is expected


@pytest.mark.parametrize(
    "authority",
    [
        "api.anthropic.com:80",
        "api.anthropic.com:444",
        "127.0.0.1:443",
        "[::1]:443",
        "user@api.anthropic.com:443",
        "api.anthropic.com/path:443",
        "api.anthropic.com:not-a-port",
    ],
)
def test_proxy_rejects_non_https_and_ambiguous_connect_authorities(authority: str) -> None:
    with pytest.raises(ValueError):
        proxy.parse_authority(authority)


def test_proxy_filters_loopback_private_and_link_local_dns_answers(monkeypatch) -> None:
    monkeypatch.setattr(
        proxy.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.9", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 443)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 443, 0, 0)),
        ],
    )
    with pytest.raises(OSError, match="no public"):
        proxy.public_addresses("api.anthropic.com", 443)


def test_proxy_keeps_only_public_dns_answers(monkeypatch) -> None:
    monkeypatch.setattr(
        proxy.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.9", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 443)),
        ],
    )
    assert proxy.public_addresses("api.anthropic.com", 443) == [
        (socket.AF_INET, ("1.1.1.1", 443))
    ]


def test_proxy_connects_to_the_checked_address_without_a_second_dns_lookup(monkeypatch) -> None:
    called = []

    class FakeSocket:
        def settimeout(self, _timeout):
            pass

        def connect(self, address):
            called.append(address)

        def close(self):
            pass

    monkeypatch.setattr(proxy.socket, "socket", lambda *_args: FakeSocket())
    result = proxy.connect_pinned([(socket.AF_INET, ("1.2.3.4", 443))])
    assert isinstance(result, FakeSocket)
    assert called == [("1.2.3.4", 443)]


def _write_complete_data(work: Path) -> None:
    data = work / "data"
    data.mkdir()
    (data / ".gitkeep").touch()
    for name in preflight.REQUIRED_DATA_FILES:
        (data / name).write_text('{"record": 1}\n')


def test_native_preflight_hashes_and_reads_every_data_file(tmp_path, monkeypatch) -> None:
    _write_complete_data(tmp_path)
    monkeypatch.setattr(preflight, "_network_interfaces", lambda: ["lo"])

    result = preflight.preflight(tmp_path)

    assert result["ok"] is True
    assert result["network_mode"] == "loopback-only"
    assert set(result["files"]) == preflight.REQUIRED_DATA_FILES
    assert all(value["records"] == 1 and len(value["sha256"]) == 64 for value in result["files"].values())


def test_native_preflight_rejects_extra_visible_files_and_network_interfaces(tmp_path, monkeypatch) -> None:
    _write_complete_data(tmp_path)
    (tmp_path / "README.md").write_text("evaluation leak")
    monkeypatch.setattr(preflight, "_network_interfaces", lambda: ["eth0", "lo"])

    result = preflight.preflight(tmp_path)

    assert result["ok"] is False
    assert any("README.md" in problem for problem in result["problems"])
    assert any("non-loopback" in problem for problem in result["problems"])
