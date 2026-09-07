#!/usr/bin/env python3
"""A small, pinned HTTP CONNECT proxy for subscription trials.

The subscription runner gives an agent an internal Docker network and this is
its only route to the model service. Each harness has an exact hostname
allowlist, only port 443 is accepted, and a resolved address must be public.
The proxy connects to that already-resolved address, rather than resolving the
hostname a second time, so DNS rebinding cannot change the destination between
the check and the connection.
"""
from __future__ import annotations

import argparse
import ipaddress
import select
import socket
import sys
import threading
import time
from collections.abc import Callable

ALLOW_BY_AGENT = {
    "claude": frozenset({"api.anthropic.com", "platform.claude.com"}),
    "codex": frozenset({"api.openai.com", "auth.openai.com", "chatgpt.com"}),
    "react": frozenset({"openrouter.ai"}),
}
MAX_REQUEST_BYTES = 16 * 1024
CONNECT_TIMEOUT_SECONDS = 20
IDLE_TIMEOUT_SECONDS = 300


def allowed_host(host: str, agent: str) -> bool:
    """True only for an exact vendor hostname for this agent."""
    return host.lower().rstrip(".") in ALLOW_BY_AGENT[agent]


def parse_authority(authority: str) -> tuple[str, int]:
    """Parse a CONNECT authority without accepting an IP literal or userinfo."""
    if authority.count(":") != 1 or any(c in authority for c in "@/\\[]"):
        raise ValueError("CONNECT target must be a hostname followed by one port")
    host, port_text = authority.rsplit(":", 1)
    if not host or not port_text.isascii() or not port_text.isdecimal():
        raise ValueError("invalid CONNECT authority")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("IP CONNECT targets are forbidden")
    port = int(port_text)
    if port != 443:
        raise ValueError("only HTTPS port 443 is allowed")
    return host.lower().rstrip("."), port


def public_addresses(host: str, port: int) -> list[tuple[int, tuple]]:
    """Resolve ``host`` and retain only globally routable TCP destinations."""
    addresses: list[tuple[int, tuple]] = []
    seen: set[tuple[int, tuple]] = set()
    for family, socktype, _proto, _canonname, sockaddr in socket.getaddrinfo(
        host, port, type=socket.SOCK_STREAM
    ):
        if socktype != socket.SOCK_STREAM:
            continue
        ip = ipaddress.ip_address(sockaddr[0])
        if not ip.is_global:
            continue
        item = (family, sockaddr)
        if item not in seen:
            seen.add(item)
            addresses.append(item)
    if not addresses:
        raise OSError("hostname has no public TCP address")
    return addresses


def connect_pinned(addresses: list[tuple[int, tuple]]) -> socket.socket:
    """Connect to a validated address without another DNS lookup."""
    last_error: OSError | None = None
    for family, sockaddr in addresses:
        upstream = socket.socket(family, socket.SOCK_STREAM)
        upstream.settimeout(CONNECT_TIMEOUT_SECONDS)
        try:
            upstream.connect(sockaddr)
            return upstream
        except OSError as exc:
            last_error = exc
            upstream.close()
    raise last_error or OSError("could not connect to public destination")


def pipe(a: socket.socket, b: socket.socket) -> None:
    try:
        while True:
            readable, _, exceptional = select.select([a, b], [], [a, b], IDLE_TIMEOUT_SECONDS)
            if exceptional or not readable:
                return
            for source in readable:
                data = source.recv(65536)
                if not data:
                    return
                (b if source is a else a).sendall(data)
    except OSError:
        return


def _deny(client: socket.socket, log: Callable[[str], None], peer: str, detail: str) -> None:
    client.sendall(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n")
    log(f"deny {peer} {detail}".replace("\r", " ").replace("\n", " "))


def handle(client: socket.socket, addr: tuple, log: Callable[[str], None], agent: str) -> None:
    peer = str(addr[0])
    upstream: socket.socket | None = None
    try:
        client.settimeout(CONNECT_TIMEOUT_SECONDS)
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = client.recv(min(4096, MAX_REQUEST_BYTES + 1 - len(head)))
            if not chunk:
                return
            head += chunk
            if len(head) > MAX_REQUEST_BYTES:
                _deny(client, log, peer, "request headers too large")
                return
        request_line = head.split(b"\r\n", 1)[0].decode("latin-1")
        fields = request_line.split()
        if len(fields) != 3 or fields[0] != "CONNECT" or not fields[2].startswith("HTTP/1."):
            _deny(client, log, peer, f"invalid request {request_line[:160]}")
            return
        host, port = parse_authority(fields[1])
        if not allowed_host(host, agent):
            _deny(client, log, peer, f"CONNECT {host}:{port} (host not allowed for {agent})")
            return
        upstream = connect_pinned(public_addresses(host, port))
        client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        client.settimeout(None)
        upstream.settimeout(None)
        log(f"allow {peer} CONNECT {host}:{port} address={upstream.getpeername()[0]}")
        pipe(client, upstream)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        log(f"error {peer} {type(exc).__name__}: {str(exc)[:200]}")
    finally:
        if upstream is not None:
            upstream.close()
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3128)
    parser.add_argument("--agent", choices=sorted(ALLOW_BY_AGENT), required=True)
    parser.add_argument("--log", default="-")
    args = parser.parse_args()
    out = sys.stdout if args.log == "-" else open(args.log, "a", buffering=1)
    lock = threading.Lock()

    def log(message: str) -> None:
        with lock:
            out.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {message}\n")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.bind, args.port))
    server.listen(64)
    log(f"listening on {args.bind}:{args.port} agent={args.agent} allow={sorted(ALLOW_BY_AGENT[args.agent])}")
    while True:
        client, address = server.accept()
        threading.Thread(target=handle, args=(client, address, log, args.agent), daemon=True).start()


if __name__ == "__main__":
    main()
