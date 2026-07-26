"""Per-task egress allowlist via a filtering proxy sidecar.

When a task declares ``environment.allowed_hosts`` and the run has a network, the
task container is attached to an internal-only Docker network whose sole route out
is a small proxy. The proxy (a stdlib CONNECT/HTTP forwarder, run in a
``python:3.12-slim`` sidecar) permits only the allowlisted host suffixes and denies
everything else. Because the task has no other interface, it cannot bypass the
filter. See SECURITY.md.
"""

from __future__ import annotations

PROXY_PORT = 8888
PROXY_ALIAS = "reforge-proxy"


def egress_allowed(host: str, allowed: set[str]) -> bool:
    """True if ``host`` is exactly, or a subdomain of, an allowlisted entry."""
    host = (host or "").strip().lower().rsplit(":", 1)[0]
    if not host:
        return False
    return any(host == a or host.endswith("." + a) for a in (a.lower() for a in allowed))


# The proxy program, run as ``python -c PROXY_SRC host1 host2 ...`` in the sidecar.
# Kept dependency-free so it runs in a stock python image. The allow rule mirrors
# egress_allowed above; keep the two in sync.
PROXY_SRC = r"""
import socket, sys, threading, select

ALLOWED = [h.lower() for h in sys.argv[1:]]


def ok(host):
    host = (host or "").strip().lower().rsplit(":", 1)[0]
    return bool(host) and any(host == a or host.endswith("." + a) for a in ALLOWED)


def pipe(a, b):
    try:
        while True:
            r, _, _ = select.select([a, b], [], [], 120)
            if not r:
                break
            for s in r:
                data = s.recv(65536)
                if not data:
                    return
                (b if s is a else a).sendall(data)
    except OSError:
        pass


def handle(client):
    up = None
    try:
        client.settimeout(30)
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = client.recv(4096)
            if not chunk:
                return
            buf += chunk
            if len(buf) > 65536:
                return
        head = buf.split(b"\r\n", 1)[0].decode("latin1", "replace")
        parts = head.split(" ")
        if len(parts) < 2:
            return
        method, target = parts[0], parts[1]
        if method == "CONNECT":
            host, _, port = target.partition(":")
            if not ok(host):
                client.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
                return
            up = socket.create_connection((host, int(port or 443)), timeout=30)
            client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        else:
            # Proxied plain-HTTP requests use an absolute URI: "GET http://host/path".
            # Rewrite it to origin-form ("GET /path") so the origin server accepts it.
            host, path = "", target
            if "://" in target:
                rest = target.split("://", 1)[1]
                hostport, slash, tail = rest.partition("/")
                host = hostport
                path = "/" + tail if slash else "/"
            if not ok(host):
                client.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
                return
            name, _, port = host.partition(":")
            up = socket.create_connection((name, int(port or 80)), timeout=30)
            version = parts[2] if len(parts) > 2 else "HTTP/1.1"
            rest_bytes = buf.split(b"\r\n", 1)[1]
            line = (method + " " + path + " " + version).encode("latin1")
            up.sendall(line + b"\r\n" + rest_bytes)
        up.settimeout(None)
        client.settimeout(None)
        pipe(client, up)
    except Exception:
        pass
    finally:
        client.close()
        if up is not None:
            up.close()


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", 8888))
    srv.listen(128)
    while True:
        conn, _ = srv.accept()
        threading.Thread(target=handle, args=(conn,), daemon=True).start()


main()
"""


def proxy_env() -> dict[str, str]:
    """Environment that routes a container's HTTP(S) traffic through the sidecar."""
    url = f"http://{PROXY_ALIAS}:{PROXY_PORT}"
    return {
        "HTTP_PROXY": url,
        "HTTPS_PROXY": url,
        "http_proxy": url,
        "https_proxy": url,
        "NO_PROXY": "",
        "no_proxy": "",
    }
