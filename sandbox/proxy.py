#!/usr/bin/env python3
"""Allowlisting HTTP CONNECT proxy.

The sandbox user can only reach 127.0.0.1 (iptables), so every outbound
connection from an agent has to come through here, and only hosts in ALLOW get
through. Everything else is refused and logged, which doubles as a record of
what the agent tried to reach.

Usage: proxy.py [--port 3128] [--log denied.log]
"""
import argparse
import select
import socket
import sys
import threading
import time

ALLOW = {
    # Claude Code (subscription or API key)
    "api.anthropic.com",
    "platform.claude.com",
    # Codex CLI (ChatGPT subscription login talks to chatgpt.com; API key to api.openai.com)
    "chatgpt.com",
    "api.openai.com",
    "auth.openai.com",
}


def allowed(host: str) -> bool:
    host = host.lower()
    return any(host == a or host.endswith("." + a) for a in ALLOW)


def pipe(a: socket.socket, b: socket.socket) -> None:
    socks = [a, b]
    try:
        while True:
            r, _, x = select.select(socks, [], socks, 300)
            if x or not r:
                return
            for s in r:
                data = s.recv(65536)
                if not data:
                    return
                (b if s is a else a).sendall(data)
    except OSError:
        return


def handle(client: socket.socket, addr, log) -> None:
    try:
        client.settimeout(30)
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = client.recv(4096)
            if not chunk:
                return
            head += chunk
        line = head.split(b"\r\n", 1)[0].decode("latin-1")
        parts = line.split()
        if len(parts) < 2 or parts[0] != "CONNECT":
            # Plain HTTP is never needed by the CLIs; refuse it.
            client.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
            log(f"deny {addr[0]} {line}")
            return
        host, _, port = parts[1].rpartition(":")
        if not allowed(host):
            client.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
            log(f"deny {addr[0]} CONNECT {host}:{port}")
            return
        upstream = socket.create_connection((host, int(port)), timeout=30)
        client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        client.settimeout(None)
        upstream.settimeout(None)
        log(f"allow {addr[0]} CONNECT {host}:{port}")
        pipe(client, upstream)
        upstream.close()
    except Exception as e:  # noqa: BLE001
        log(f"error {addr[0]} {e}")
    finally:
        client.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=3128)
    ap.add_argument("--log", default="-")
    args = ap.parse_args()
    out = sys.stdout if args.log == "-" else open(args.log, "a", buffering=1)
    lock = threading.Lock()

    def log(msg: str) -> None:
        with lock:
            out.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}\n")

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", args.port))
    srv.listen(64)
    log(f"listening on 127.0.0.1:{args.port} allow={sorted(ALLOW)}")
    while True:
        c, a = srv.accept()
        threading.Thread(target=handle, args=(c, a, log), daemon=True).start()


if __name__ == "__main__":
    main()
