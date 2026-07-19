"""Persistent engine<->backend WebSocket client (Workstream 6c).

Replaces the 1.5s HTTP poll (``response_engine/backend_command_poller.py``,
driven by ``SnifferService._poll_backend_commands``) with a persistent,
HMAC-authenticated WebSocket connection for *pushing* commands to the engine
the instant they're created on the backend. This is a latency optimization
layered on top of the existing DB-backed command queue, which stays as the
durable fallback — see ``_run_catchup`` below, which does one
``GET /engine-commands`` poll (reusing ``BackendCommandPoller`` unchanged) on
every connect/reconnect before settling into WS-only operation.

Gated entirely behind ``SMARTIDS_ENGINE_WS_ENABLED`` (see
``packet_capture/sniffer_service.py``) — when unset/false, this module is
never instantiated and the old poll loop runs exactly as before.

Runs on its own thread with its own asyncio event loop, since the rest of
the engine is synchronous/thread-based (``websockets`` requires asyncio).

WS auth handshake signing convention
-------------------------------------
A WebSocket handshake has no HTTP method/path/body to sign, so a fixed
stand-in string is signed with the *same* ``InternalRequestSigner.sign()``
used for real HTTP requests, substituting the constants below for method and
path with an empty body::

    signer.sign(ENGINE_WS_AUTH_METHOD, ENGINE_WS_AUTH_PATH, b"")

These MUST match byte-for-byte with the backend's
``app/features/realtime/engine_ws_schemas.py`` constants of the same name —
the backend re-derives the expected signature using the same two constants.

Envelope shape
--------------
``{"type": "auth"|"command"|"command_ack"|"event"|"telemetry"|"ping"|"pong",
"id": "<uuid4>", "ts": <unix epoch seconds>, "payload": {...}}``. This client
only produces/consumes ``auth``, ``command``, ``command_ack``, ``ping``, and
``pong`` — ``event``/``telemetry`` push stays on the five existing
``fastapi_*_forwarder.py`` HTTP paths, out of scope for this workstream.

Outbound backpressure
---------------------
Outgoing ``command_ack`` frames go through a bounded, drop-on-full
``BackgroundPublisher`` queue (the same class and pattern used by every
other engine->backend push path) rather than being written directly, so one
slow/stuck connection degrades the same way the existing per-forwarder
queues do instead of growing unbounded. The publisher's worker thread hands
each ack off to this client's asyncio loop via
``asyncio.run_coroutine_threadsafe`` to actually write it to the socket.
"""

from __future__ import annotations

import asyncio
import json
import random
import threading
import time
import uuid
from typing import Callable

import websockets

from packet_capture.auth.request_signer import InternalRequestSigner
from packet_capture.forwarding.background_publisher import BackgroundPublisher
from packet_capture.utils.logger import IDSLogger, log_event
from response_engine.backend_command_poller import BackendCommandPoller

# Must match backend/app/features/realtime/engine_ws_schemas.py exactly.
ENGINE_WS_AUTH_METHOD = "WS_AUTH"
ENGINE_WS_AUTH_PATH = "/api/v1/realtime/engine-ws"

DEFAULT_RECONNECT_BASE_SECONDS = 1.0
DEFAULT_RECONNECT_CAP_SECONDS = 60.0
DEFAULT_CONNECT_TIMEOUT_SECONDS = 10.0
DEFAULT_AUTH_TIMEOUT_SECONDS = 10.0
DEFAULT_COMMAND_ACK_QUEUE_SIZE = 256


class EngineWSAuthError(Exception):
    """Raised when the backend rejects (or never replies to) the auth frame."""


class EngineWSClient:
    def __init__(
        self,
        *,
        ws_url: str,
        signer: InternalRequestSigner,
        apply_command: Callable[[dict], tuple[bool, str]],
        catchup_poller: BackendCommandPoller | None = None,
        catchup_ack_endpoint_url: str | None = None,
        command_ack_queue_size: int = DEFAULT_COMMAND_ACK_QUEUE_SIZE,
        command_ack_drop_log_every: int = 25,
        reconnect_base_seconds: float = DEFAULT_RECONNECT_BASE_SECONDS,
        reconnect_cap_seconds: float = DEFAULT_RECONNECT_CAP_SECONDS,
        connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS,
        auth_timeout_seconds: float = DEFAULT_AUTH_TIMEOUT_SECONDS,
    ) -> None:
        self._ws_url = ws_url
        self._signer = signer
        self._apply_command = apply_command
        self._catchup_poller = catchup_poller
        self._catchup_ack_endpoint_url = catchup_ack_endpoint_url
        self._reconnect_base_seconds = max(0.1, reconnect_base_seconds)
        self._reconnect_cap_seconds = max(self._reconnect_base_seconds, reconnect_cap_seconds)
        self._connect_timeout_seconds = connect_timeout_seconds
        self._auth_timeout_seconds = auth_timeout_seconds

        self._logger = IDSLogger.get_logger("realtime.engine_ws_client")
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ws = None

        self._ack_publisher = BackgroundPublisher(
            name="engine-ws-command-ack",
            publish=self._publish_command_ack_sync,
            max_queue_size=command_ack_queue_size,
            drop_log_every=command_ack_drop_log_every,
        )

    # -- lifecycle -----------------------------------------------------

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run_thread, daemon=True, name="smartids-engine-ws-client")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        loop = self._loop
        ws = self._ws
        if loop is not None and ws is not None:
            try:
                asyncio.run_coroutine_threadsafe(ws.close(), loop)
            except Exception:
                pass

    def is_connected(self) -> bool:
        return self._ws is not None

    def command_ack_queue_size(self) -> int:
        return self._ack_publisher.queue_size()

    def command_ack_dropped_total(self) -> int:
        return self._ack_publisher.dropped_total()

    # -- event loop thread ----------------------------------------------

    def _run_thread(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._connect_loop())
        finally:
            self._loop = None
            loop.close()

    async def _connect_loop(self) -> None:
        attempt = 0
        while not self._stop_event.is_set():
            try:
                await self._run_connection()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log_event(
                    self._logger,
                    "warning",
                    "engine ws connection failed",
                    {
                        "event_type": "engine_ws_connect_failed",
                        "ws_url": self._ws_url,
                        "error": str(exc),
                    },
                )

            if self._stop_event.is_set():
                break

            delay = self._next_backoff_delay(attempt)
            attempt += 1
            log_event(
                self._logger,
                "info",
                "engine ws reconnecting",
                {
                    "event_type": "engine_ws_reconnect_wait",
                    "attempt": attempt,
                    "delay_seconds": round(delay, 2),
                },
            )
            await asyncio.sleep(delay)

    def _next_backoff_delay(self, attempt: int) -> float:
        """Exponential backoff with full jitter, base 1s / cap 60s (defaults)."""
        uncapped = self._reconnect_base_seconds * (2**attempt)
        capped = min(self._reconnect_cap_seconds, uncapped)
        return random.uniform(0, capped)

    # -- one connection attempt ------------------------------------------

    async def _run_connection(self) -> None:
        async with websockets.connect(
            self._ws_url,
            open_timeout=self._connect_timeout_seconds,
        ) as ws:
            self._ws = ws
            try:
                await self._authenticate(ws)
                log_event(
                    self._logger,
                    "info",
                    "engine ws connected and authenticated",
                    {"event_type": "engine_ws_connected", "ws_url": self._ws_url},
                )
                await self._run_catchup()
                async for raw in ws:
                    await self._handle_incoming(raw)
            finally:
                self._ws = None

    async def _authenticate(self, ws) -> None:
        headers = self._signer.sign(ENGINE_WS_AUTH_METHOD, ENGINE_WS_AUTH_PATH, b"")
        await ws.send(
            json.dumps(
                {
                    "type": "auth",
                    "id": str(uuid.uuid4()),
                    "ts": time.time(),
                    "payload": {
                        "signature": headers["x-smartids-signature"],
                        "timestamp": headers["x-smartids-timestamp"],
                        "nonce": headers["x-smartids-nonce"],
                        "engine_id": headers.get("x-smartids-engine-id"),
                    },
                }
            )
        )
        raw = await asyncio.wait_for(ws.recv(), timeout=self._auth_timeout_seconds)
        reply = json.loads(raw)
        payload = reply.get("payload") if isinstance(reply, dict) else None
        status = payload.get("status") if isinstance(payload, dict) else None
        if not isinstance(reply, dict) or reply.get("type") != "auth" or status != "ok":
            raise EngineWSAuthError("engine ws authentication rejected by backend")

    async def _run_catchup(self) -> None:
        """One durable-queue catch-up poll per (re)connect.

        Reuses ``BackendCommandPoller`` (the same class/HTTP path the
        1.5s poller uses when WS is disabled) so any commands queued while
        disconnected are still delivered exactly once WS auth succeeds,
        before this connection settles into WS-only push/ack.
        """
        if self._catchup_poller is None:
            return

        loop = asyncio.get_running_loop()
        commands = await loop.run_in_executor(None, self._catchup_poller.poll_commands)
        if not commands:
            return

        log_event(
            self._logger,
            "info",
            "engine ws catch-up poll returned commands",
            {"event_type": "engine_ws_catchup", "command_count": len(commands)},
        )
        for command in commands:
            await loop.run_in_executor(None, self._apply_and_ack_via_rest, command)

    def _apply_and_ack_via_rest(self, command: dict) -> None:
        ok, status = self._apply_command(command)
        if self._catchup_ack_endpoint_url is None or self._catchup_poller is None:
            return
        command_id = str(command.get("command_id", "")).strip()
        if not command_id:
            return
        self._catchup_poller.ack_command(
            ack_endpoint_url=self._catchup_ack_endpoint_url,
            command_id=command_id,
            status=status if ok else f"error:{status}",
        )

    # -- inbound frame handling ------------------------------------------

    async def _handle_incoming(self, raw) -> None:
        try:
            message = json.loads(raw)
        except (ValueError, TypeError):
            return
        if not isinstance(message, dict):
            return

        msg_type = message.get("type")
        payload = message.get("payload")
        payload = payload if isinstance(payload, dict) else {}

        if msg_type == "command":
            await self._handle_command(payload)
        elif msg_type == "ping":
            await self._send_envelope("pong", {})
        elif msg_type == "pong":
            return
        else:
            log_event(
                self._logger,
                "debug",
                "engine ws ignoring unrecognized frame",
                {"event_type": "engine_ws_unrecognized_frame", "frame_type": msg_type},
            )

    async def _handle_command(self, command: dict) -> None:
        loop = asyncio.get_running_loop()
        ok, status = await loop.run_in_executor(None, self._apply_command, command)
        command_id = str(command.get("command_id", "")).strip()
        if not command_id:
            return

        submitted = self._ack_publisher.submit(
            {
                "command_id": command_id,
                "status": status if ok else f"error:{status}",
                "acked_at": time.time(),
                "ack_source": "engine_ws",
            }
        )
        if not submitted:
            log_event(
                self._logger,
                "warning",
                "engine ws command ack queue full, ack dropped",
                {"event_type": "engine_ws_ack_dropped", "command_id": command_id},
            )

    # -- outbound frame writing -------------------------------------------

    async def _send_envelope(self, msg_type: str, payload: dict) -> None:
        ws = self._ws
        if ws is None:
            return
        await ws.send(
            json.dumps({"type": msg_type, "id": str(uuid.uuid4()), "ts": time.time(), "payload": payload})
        )

    def _publish_command_ack_sync(self, payload: dict) -> bool:
        """``BackgroundPublisher`` worker-thread callback.

        Hands the ack off to this client's asyncio loop thread (the only
        thread allowed to touch the websocket) via
        ``run_coroutine_threadsafe`` and waits briefly for the write to
        complete.
        """
        loop = self._loop
        ws = self._ws
        if loop is None or ws is None:
            return False

        future = asyncio.run_coroutine_threadsafe(self._send_envelope("command_ack", payload), loop)
        try:
            future.result(timeout=5.0)
            return True
        except Exception:
            return False
