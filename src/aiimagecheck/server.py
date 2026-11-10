"""`aiimagecheck serve`: a page on this machine to drop images and PDFs onto.

Loopback only, refused otherwise: files may be private, and this is a tool
for the person at the keyboard, not a service. The page posts the file's
raw bytes (no multipart form, so nothing beyond the standard library), and
gets the report back as JSON with any source thumbnail inline.
"""

from __future__ import annotations

import ipaddress
import json
import signal
import socket
import socketserver
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources

from . import check

MAX_UPLOAD = 50 * 1024 * 1024  # bytes; larger than any photo or most PDFs, small enough to refuse abuse


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def split_listen(listen: str) -> tuple[str, int]:
    host, sep, port = listen.rpartition(":")
    if not sep or not port.isdigit():
        raise ValueError(f"listen address {listen!r} needs host:port")
    return host.strip("[]"), int(port)


class Handler(BaseHTTPRequestHandler):
    server_version = "aiimagecheck"
    trust_settings: dict | None = None

    def do_GET(self):
        if self.path != "/":
            return self._send(404, "text/plain; charset=utf-8", b"not found")
        page = resources.files("aiimagecheck").joinpath("page.html").read_bytes()
        self._send(200, "text/html; charset=utf-8", page)

    def do_POST(self):
        if self.path != "/check":
            return self._send(404, "text/plain; charset=utf-8", b"not found")
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self._json(411, {"error": "Content-Length required"})
        if length <= 0 or length > MAX_UPLOAD:
            return self._json(413, {"error": f"file must be between 1 byte and {MAX_UPLOAD // (1024 * 1024)} MB"})
        data = self.rfile.read(length)
        name = (self.headers.get("X-Filename") or "upload")[:200]
        report = check.check_bytes(data, name, self.trust_settings)
        self._json(200, report.to_dict(thumbnails=True))

    def _json(self, status: int, body: dict):
        self._send(status, "application/json", json.dumps(body).encode())

    def _send(self, status: int, ctype: str, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # The page is ours and inline; nothing else may load into it.
        self.send_header("Content-Security-Policy", "default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # UTC timestamps, to stderr
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        sys.stderr.write(f"{stamp} {self.address_string()} {fmt % args}\n")


class LoopbackServer(ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self):
        # HTTPServer.server_bind looks up its own hostname with
        # socket.getfqdn, a reverse DNS query that took 35 s to time out on a
        # Mac with no reverse record for 127.0.0.1. A loopback server has no
        # use for the name, so bind without the lookup.
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name, self.server_port = host, port


def make_server(listen: str) -> ThreadingHTTPServer:
    host, port = split_listen(listen)
    if not is_loopback(host):
        raise ValueError(f"listen address {listen!r} is not loopback; the page serves on 127.0.0.1 or ::1 only")
    Handler.trust_settings = check.default_trust()
    cls = LoopbackServer
    if ":" in host:
        cls = type("LoopbackServerV6", (LoopbackServer,), {"address_family": socket.AF_INET6})
    return cls((host, port), Handler)


def run(listen: str) -> int:
    try:
        srv = make_server(listen)
    except (ValueError, OSError) as err:
        print(f"aiimagecheck serve: {err}", file=sys.stderr)
        return 2 if isinstance(err, ValueError) else 1
    host, port = srv.server_address[:2]
    print(f"aiimagecheck: open http://{'[' + host + ']' if ':' in host else host}:{port}/  (Ctrl-C to stop)", file=sys.stderr)
    if Handler.trust_settings is None:
        print("note: trust lists not downloaded, so signers can't be confirmed (run `aiimagecheck update-trust`)", file=sys.stderr)
    # SIGTERM stops it as cleanly as Ctrl-C does.
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=srv.shutdown).start())
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    print("aiimagecheck: stopped", file=sys.stderr)
    return 0
