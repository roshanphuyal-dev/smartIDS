"""Temporary local loopback HTTP server for browser-based engine registration.

Part A Phase 1 of docs/plans/engine-registration-and-capture-filter.md.
Binds ``127.0.0.1`` on an OS-assigned port and waits for a single
``POST /complete`` call -- the dashboard page relays the credential issued
by ``POST /engines/register/{id}/approve`` straight to this loopback server
(same trust pattern as ``gh auth login`` / Docker Desktop device-linking).

Security: the posted ``registration_id`` must match the one this instance
was created for ("don't trust localhost alone" -- an unrelated local
process must not be able to complete a registration it didn't start).
Self-times-out after ``timeout_seconds`` (~10 minutes) if ``/complete``
never arrives.

stdlib-only (``http.server``) -- no new dependency introduced.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from packet_capture.utils.logger import IDSLogger, log_event

DEFAULT_TIMEOUT_SECONDS = 600.0  # ~10 minutes, per the plan doc


class RegistrationServer:
    def __init__(self, registration_id: str, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.registration_id = registration_id
        self.timeout_seconds = timeout_seconds
        self.result: dict | None = None

        self._done = threading.Event()
        self._shutdown_lock = threading.Lock()
        self._shutdown_started = False
        self._httpd = HTTPServer(("127.0.0.1", 0), self._make_handler())
        self._thread: threading.Thread | None = None
        self._timeout_timer: threading.Timer | None = None
        self._logger = IDSLogger.get_logger("registration.server")

    @property
    def port(self) -> int:
        return self._httpd.server_address[1]

    def start(self) -> None:
        def _serve() -> None:
            self._httpd.serve_forever()
            self._httpd.server_close()

        self._thread = threading.Thread(target=_serve, daemon=True, name="smartids-registration-server")
        self._thread.start()

        self._timeout_timer = threading.Timer(self.timeout_seconds, self._on_timeout)
        self._timeout_timer.daemon = True
        self._timeout_timer.start()

    def wait_for_completion(self, timeout: float | None = None) -> dict | None:
        self._done.wait(timeout=timeout if timeout is not None else self.timeout_seconds + 5)
        return self.result

    def shutdown(self) -> None:
        with self._shutdown_lock:
            if self._shutdown_started:
                return
            self._shutdown_started = True

        if self._timeout_timer is not None:
            self._timeout_timer.cancel()

        # HTTPServer.shutdown() must not be called from the thread running
        # serve_forever() (it would deadlock waiting on itself), so always
        # dispatch it to a fresh thread -- this covers both the "shutdown
        # triggered from inside a request handler" case and the normal
        # external-caller case.
        threading.Thread(target=self._httpd.shutdown, daemon=True).start()

    def _on_timeout(self) -> None:
        if self._done.is_set():
            return
        log_event(
            self._logger,
            "warning",
            "engine registration timed out waiting for browser approval",
            {"event_type": "engine_registration_server_timeout", "registration_id": self.registration_id},
        )
        self._done.set()
        self.shutdown()

    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):  # noqa: A002 - stdlib override signature
                pass  # IDSLogger is the logging convention here, not stderr access logs

            def _write_cors_headers(self) -> None:
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")

            def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib method name
                self.send_response(204)
                self._write_cors_headers()
                self.end_headers()

            def do_POST(self) -> None:  # noqa: N802 - stdlib method name
                if self.path.split("?", 1)[0].rstrip("/") != "/complete":
                    self.send_response(404)
                    self._write_cors_headers()
                    self.end_headers()
                    return

                content_length = int(self.headers.get("Content-Length", "0") or "0")
                raw_body = self.rfile.read(content_length) if content_length > 0 else b""

                try:
                    payload = json.loads(raw_body.decode("utf-8")) if raw_body else None
                except (ValueError, UnicodeDecodeError):
                    payload = None

                if not isinstance(payload, dict) or payload.get("registration_id") != server.registration_id:
                    log_event(
                        server._logger,
                        "warning",
                        "engine registration /complete rejected: registration_id mismatch or bad payload",
                        {"event_type": "engine_registration_complete_rejected"},
                    )
                    self.send_response(403)
                    self._write_cors_headers()
                    self.end_headers()
                    return

                server.result = payload

                self.send_response(200)
                self._write_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok": true}')

                server._done.set()
                server.shutdown()

        return Handler
