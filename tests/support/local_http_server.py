from __future__ import annotations

import contextlib
import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any


@dataclass
class RecordingHttpServer:
    """A real HTTP server on localhost, running in a background thread, that
    records every JSON POST body it receives. Used to verify WebhookNotifier
    against genuine sockets rather than a mocked HTTP client -- the same
    "test against something real" discipline used for the MT4/MT5 connectors
    and the ZeroMQ transport layer.
    """

    server: HTTPServer
    received: list[dict[str, Any]] = field(default_factory=list)
    response_status: int = 200

    def start(self) -> threading.Thread:
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        return thread

    def shutdown(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@contextlib.contextmanager
def recording_http_server(
    *, host: str = "127.0.0.1", port: int, response_status: int = 200
) -> Iterator[RecordingHttpServer]:
    received: list[dict[str, Any]] = []
    holder = {"status": response_status}

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - http.server's required method name
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            received.append(json.loads(body.decode("utf-8")))
            self.send_response(holder["status"])
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, format_str: str, *args: Any) -> None:
            return  # silence default stderr request logging

    server = HTTPServer((host, port), _Handler)
    wrapper = RecordingHttpServer(server=server, received=received, response_status=response_status)
    thread = wrapper.start()
    try:
        yield wrapper
    finally:
        wrapper.shutdown()
        thread.join(timeout=2.0)


__all__ = ["RecordingHttpServer", "recording_http_server"]
