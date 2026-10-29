"""Loopback-only HTTP UI for the local Studio; stdlib and no outbound transport."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import mimetypes
from pathlib import Path
import secrets
import subprocess
from urllib.parse import urlsplit

from . import api_lab as al
from .studio import MAX_BYTES, ROOT, Store, native_plan, template


def make_server(workspace, port=8765):
    al.require(type(port) is int and 0 <= port <= 65535, "port must be between 0 and 65535")
    # Use the same canonical reader build and assets, not a second frontend.
    try:
        from tools import build_site
    except ImportError as exc:
        raise al.ApiLabError("Studio requires the existing requirements-site.txt environment") from exc
    build_site.build(ROOT / "_site")
    assets = {"/" + rel: rel for rel in (*build_site.ASSETS, *(p.removesuffix('.md') + '.html' for p in build_site.PAGES), 'index.html')}
    assets['/'] = 'index.html'
    store = Store(workspace)
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass  # Research names and request content do not belong in HTTP logs.

        def _trusted(self):
            expected = f"127.0.0.1:{self.server.server_port}"
            origin = self.headers.get("Origin")
            return self.headers.get("Host") == expected and (origin is None or origin == "http://" + expected)

        def _send(self, value, status=200, content_type="application/json; charset=utf-8"):
            raw = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if not self._trusted():
                return self._send({"error": "loopback host/origin required"}, 403)
            path = urlsplit(self.path).path
            try:
                if path in assets:
                    target = ROOT / "_site" / assets[path]
                    raw = target.read_bytes()
                    if assets[path] == "index.html":
                        raw = raw.replace(b'<meta name="studio-token" content="">', b'<meta name="studio-token" content="' + token.encode() + b'">')
                    return self._send(raw, content_type=(mimetypes.guess_type(str(target))[0] or "application/octet-stream") + ("; charset=utf-8" if target.suffix in (".html", ".js", ".css") else ""))
                if path == "/api/studies":
                    return self._send({"studies": store.list()})
                if path.startswith("/api/template/"):
                    return self._send(template(path.removeprefix("/api/template/")))
                if path.startswith("/api/studies/"):
                    parts = path.removeprefix("/api/studies/").split("/")
                    if len(parts) == 1:
                        return self._send(store.get(parts[0]))
                    if len(parts) == 2 and parts[1] == "export":
                        return self._send(store.export(parts[0]))
                    if len(parts) == 3 and parts[1] == "plan":
                        study = store.get(parts[0])
                        al.require(parts[2] in study["runs"], "unknown condition")
                        return self._send(native_plan(study["runs"][parts[2]][-1]["record"]))
                self._send({"error": "not found"}, 404)
            except (ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired) as exc:
                self._send({"error": str(exc)}, 400)

        def do_POST(self):
            if not self._trusted() or self.headers.get("X-Studio-Token") != token:
                return self._send({"error": "local Studio session required; reload the page"}, 403)
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self._send({"error": "application/json required"}, 415)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                al.require(0 < length <= MAX_BYTES, "request must be 1 byte–32 MiB")
                al.require(not self.headers.get("Transfer-Encoding"), "chunked requests unsupported")
                data = json.loads(self.rfile.read(length), parse_constant=lambda x: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
                al.require(isinstance(data, dict), "JSON object required")
                path = urlsplit(self.path).path
                al.require(path.startswith("/api/action/"), "unknown action path")
                self._send(store.command(path.removeprefix("/api/action/"), data))
            except (ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired) as exc:
                self._send({"error": str(exc)}, 409 if "revision conflict" in str(exc) else 400)

    server = HTTPServer(("127.0.0.1", port), Handler)
    server.timeout = 1
    return server


def serve(workspace, port=8765):
    server = make_server(workspace, port)
    print(f"Decisions Lab Studio: http://127.0.0.1:{server.server_port}/#research-studio", flush=True)
    print("Local workspace only. No provider calls. Ctrl-C stops the server.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
