from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import time
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1:5432/testdb")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("PASSWORD_RESET_BASE_URL", "http://127.0.0.1:3000")

TEST_SECRET = "1234567890abcdef" * 4
os.environ["SMARTIDS_INTERNAL_SERVICE_TOKEN"] = TEST_SECRET

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.redis import get_internal_auth_redis
from app.features.engines.models import EngineStatus
from app.features.realtime import engine_ws_manager as engine_ws_manager_module
from app.features.realtime.engine_ws_router import (
    WS_CLOSE_ENGINE_REVOKED,
    router as engine_ws_router,
)
from app.features.realtime.engine_ws_schemas import ENGINE_WS_AUTH_METHOD, ENGINE_WS_AUTH_PATH


def sign_ws_auth(
    secret: str = TEST_SECRET,
    timestamp: str | None = None,
    nonce: str = "ws-nonce-000000000000000000000000",
    engine_id: str | None = None,
) -> dict[str, str]:
    if timestamp is None:
        timestamp = str(time.time())
    body_hash = hashlib.sha256(b"").hexdigest()
    signing_string = f"{ENGINE_WS_AUTH_METHOD}\n{ENGINE_WS_AUTH_PATH}\n{body_hash}\n{timestamp}\n{nonce}"
    signature = hmac.new(secret.encode(), signing_string.encode(), hashlib.sha256).hexdigest()
    payload = {"signature": signature, "timestamp": timestamp, "nonce": nonce}
    if engine_id is not None:
        payload["engine_id"] = engine_id
    return payload


class FakeAsyncRedis:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def set(self, name: str, value: str, nx: bool = False, ex: int | None = None) -> bool | None:
        if nx and name in self._store:
            return None
        self._store[name] = value
        return True


app = FastAPI()
app.include_router(engine_ws_router, prefix="/api/v1")


class EngineWSRouterTest(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["SMARTIDS_INTERNAL_SERVICE_TOKEN"] = TEST_SECRET
        get_settings.cache_clear()
        self.fake_redis = FakeAsyncRedis()
        app.dependency_overrides[get_internal_auth_redis] = lambda: self.fake_redis
        engine_ws_manager_module.engine_ws_manager._connections.clear()

    def tearDown(self) -> None:
        app.dependency_overrides.pop(get_internal_auth_redis, None)
        engine_ws_manager_module.engine_ws_manager._connections.clear()

    def test_valid_auth_frame_is_accepted_and_registers_connection(self) -> None:
        auth = sign_ws_auth(nonce="ws-nonce-accept-0000000000000000")
        with TestClient(app) as client:
            with client.websocket_connect("/api/v1/realtime/engine-ws") as ws:
                ws.send_json({"type": "auth", "id": "1", "ts": time.time(), "payload": auth})
                reply = ws.receive_json()

                self.assertEqual(reply["type"], "auth")
                self.assertEqual(reply["payload"]["status"], "ok")
                self.assertTrue(engine_ws_manager_module.engine_ws_manager.has_connections())

    def test_bad_signature_closes_connection_without_registering(self) -> None:
        auth = sign_ws_auth(nonce="ws-nonce-badsig-0000000000000000")
        auth["signature"] = "0" * len(auth["signature"])
        with TestClient(app) as client:
            with client.websocket_connect("/api/v1/realtime/engine-ws") as ws:
                ws.send_json({"type": "auth", "id": "1", "ts": time.time(), "payload": auth})
                with self.assertRaises(Exception):
                    ws.receive_json()

        self.assertFalse(engine_ws_manager_module.engine_ws_manager.has_connections())

    def test_expired_timestamp_is_rejected(self) -> None:
        stale_timestamp = str(time.time() - 120)
        auth = sign_ws_auth(timestamp=stale_timestamp, nonce="ws-nonce-expired-0000000000000000")
        with TestClient(app) as client:
            with client.websocket_connect("/api/v1/realtime/engine-ws") as ws:
                ws.send_json({"type": "auth", "id": "1", "ts": time.time(), "payload": auth})
                with self.assertRaises(Exception):
                    ws.receive_json()

    def test_replayed_nonce_is_rejected_on_second_connection(self) -> None:
        auth = sign_ws_auth(nonce="ws-nonce-replay-0000000000000000")
        with TestClient(app) as client:
            with client.websocket_connect("/api/v1/realtime/engine-ws") as ws:
                ws.send_json({"type": "auth", "id": "1", "ts": time.time(), "payload": auth})
                reply = ws.receive_json()
                self.assertEqual(reply["payload"]["status"], "ok")

            with client.websocket_connect("/api/v1/realtime/engine-ws") as ws2:
                ws2.send_json({"type": "auth", "id": "2", "ts": time.time(), "payload": auth})
                with self.assertRaises(Exception):
                    ws2.receive_json()

    def test_missing_auth_fields_are_rejected(self) -> None:
        with TestClient(app) as client:
            with client.websocket_connect("/api/v1/realtime/engine-ws") as ws:
                ws.send_json({"type": "auth", "id": "1", "ts": time.time(), "payload": {}})
                with self.assertRaises(Exception):
                    ws.receive_json()

    def test_first_frame_must_be_auth_type(self) -> None:
        with TestClient(app) as client:
            with client.websocket_connect("/api/v1/realtime/engine-ws") as ws:
                ws.send_json({"type": "ping", "id": "1", "ts": time.time(), "payload": {}})
                with self.assertRaises(Exception):
                    ws.receive_json()

    def test_ping_after_auth_receives_pong(self) -> None:
        auth = sign_ws_auth(nonce="ws-nonce-ping-00000000000000000000")
        with TestClient(app) as client:
            with client.websocket_connect("/api/v1/realtime/engine-ws") as ws:
                ws.send_json({"type": "auth", "id": "1", "ts": time.time(), "payload": auth})
                ws.receive_json()

                ws.send_json({"type": "ping", "id": "2", "ts": time.time(), "payload": {}})
                reply = ws.receive_json()

                self.assertEqual(reply["type"], "pong")

    def test_command_ack_frame_invokes_engine_command_service(self) -> None:
        calls = []

        class FakeService:
            def __init__(self, _session) -> None:
                pass

            async def acknowledge_command(self, payload):
                calls.append(payload)
                return {"acked": True}

        class FakeSession:
            async def commit(self) -> None:
                pass

            async def rollback(self) -> None:
                pass

        class FakeSessionCM:
            async def __aenter__(self):
                return FakeSession()

            async def __aexit__(self, *exc):
                return False

        auth = sign_ws_auth(nonce="ws-nonce-ack-000000000000000000000")

        with (
            patch("app.features.realtime.engine_ws_router.EngineCommandService", FakeService),
            patch("app.features.realtime.engine_ws_router.async_session_factory", lambda: FakeSessionCM()),
        ):
            with TestClient(app) as client:
                with client.websocket_connect("/api/v1/realtime/engine-ws") as ws:
                    ws.send_json({"type": "auth", "id": "1", "ts": time.time(), "payload": auth})
                    ws.receive_json()

                    ws.send_json(
                        {
                            "type": "command_ack",
                            "id": "2",
                            "ts": time.time(),
                            "payload": {
                                "command_id": "cmd-ws-ack-1",
                                "status": "blocked",
                                "acked_at": time.time(),
                            },
                        }
                    )
                    # The server loop awaits command_ack handling fully
                    # before reading the next frame, so a ping/pong
                    # round-trip after it guarantees the ack was processed.
                    ws.send_json({"type": "ping", "id": "3", "ts": time.time(), "payload": {}})
                    pong = ws.receive_json()
                    self.assertEqual(pong["type"], "pong")

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].command_id, "cmd-ws-ack-1")
        self.assertEqual(calls[0].status, "blocked")
        self.assertEqual(calls[0].ack_source, "engine_ws")


class FakeEngineRepository:
    """Stand-in for EngineRepository, patched into engine_ws_router so the
    per-engine dual-secret (rotation grace window) auth tests below don't
    require a real database — mirrors the fake used in
    tests/integration/api/test_internal_service_auth.py."""

    engines_by_public_id: dict[str, SimpleNamespace] = {}

    def __init__(self, _session) -> None:
        pass

    async def get_by_public_id(self, engine_public_id: str):
        return FakeEngineRepository.engines_by_public_id.get(engine_public_id)

    async def update(self, engine):
        return engine


class FakeSession:
    def add(self, _obj) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


class FakeSessionCM:
    async def __aenter__(self):
        return FakeSession()

    async def __aexit__(self, *exc):
        return False


class EngineWSCredentialRotationAuthTest(unittest.TestCase):
    """Covers the dual-secret (current + previous) auth path added to
    _authenticate for engine-scoped WS connections, mirroring
    EngineHeaderInternalAuthTest's rotation coverage in
    test_internal_service_auth.py but for the WS auth handshake."""

    def setUp(self) -> None:
        os.environ["SMARTIDS_INTERNAL_SERVICE_TOKEN"] = TEST_SECRET
        get_settings.cache_clear()
        self.fake_redis = FakeAsyncRedis()
        app.dependency_overrides[get_internal_auth_redis] = lambda: self.fake_redis
        engine_ws_manager_module.engine_ws_manager._connections.clear()
        FakeEngineRepository.engines_by_public_id = {}
        self.repository_patcher = patch(
            "app.features.realtime.engine_ws_router.EngineRepository", FakeEngineRepository
        )
        self.session_patcher = patch(
            "app.features.realtime.engine_ws_router.async_session_factory",
            lambda: FakeSessionCM(),
        )
        self.repository_patcher.start()
        self.session_patcher.start()

    def tearDown(self) -> None:
        self.session_patcher.stop()
        self.repository_patcher.stop()
        app.dependency_overrides.pop(get_internal_auth_redis, None)
        engine_ws_manager_module.engine_ws_manager._connections.clear()
        FakeEngineRepository.engines_by_public_id = {}

    def test_current_secret_accepted_for_active_engine(self) -> None:
        secret = "engine-ws-secret-current-0000000"
        FakeEngineRepository.engines_by_public_id["engine-ws-1"] = SimpleNamespace(
            engine_public_id="engine-ws-1",
            status=EngineStatus.active,
            secret=secret,
            previous_secret=None,
            previous_secret_expires_at=None,
        )
        auth = sign_ws_auth(
            secret=secret, nonce="ws-nonce-rotate-current-000000000", engine_id="engine-ws-1"
        )
        with TestClient(app) as client:
            with client.websocket_connect("/api/v1/realtime/engine-ws") as ws:
                ws.send_json({"type": "auth", "id": "1", "ts": time.time(), "payload": auth})
                reply = ws.receive_json()
                self.assertEqual(reply["payload"]["status"], "ok")

    def test_previous_secret_accepted_within_grace_window(self) -> None:
        old_secret = "engine-ws-secret-previous-000000"
        FakeEngineRepository.engines_by_public_id["engine-ws-2"] = SimpleNamespace(
            engine_public_id="engine-ws-2",
            status=EngineStatus.active,
            secret="engine-ws-secret-new-0000000000",
            previous_secret=old_secret,
            previous_secret_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        auth = sign_ws_auth(
            secret=old_secret, nonce="ws-nonce-rotate-grace-0000000000", engine_id="engine-ws-2"
        )
        with TestClient(app) as client:
            with client.websocket_connect("/api/v1/realtime/engine-ws") as ws:
                ws.send_json({"type": "auth", "id": "1", "ts": time.time(), "payload": auth})
                reply = ws.receive_json()
                self.assertEqual(reply["payload"]["status"], "ok")

    def test_previous_secret_rejected_after_grace_window_expires(self) -> None:
        old_secret = "engine-ws-secret-expired-0000000"
        FakeEngineRepository.engines_by_public_id["engine-ws-3"] = SimpleNamespace(
            status=EngineStatus.active,
            secret="engine-ws-secret-new-0000000001",
            previous_secret=old_secret,
            previous_secret_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        auth = sign_ws_auth(
            secret=old_secret, nonce="ws-nonce-rotate-expired-000000000", engine_id="engine-ws-3"
        )
        with TestClient(app) as client:
            with client.websocket_connect("/api/v1/realtime/engine-ws") as ws:
                ws.send_json({"type": "auth", "id": "1", "ts": time.time(), "payload": auth})
                with self.assertRaises(Exception):
                    ws.receive_json()


class EngineWSForceDisconnectTest(unittest.TestCase):
    """Covers Phase 3 'revocation, made live': engine_ws_manager.connect()
    now registers engine-scoped connections by engine_public_id, and
    force_disconnect() (what EngineService.revoke_engine calls after the DB
    revoke succeeds) actually closes a live connection with the dedicated
    WS_CLOSE_ENGINE_REVOKED close code."""

    def setUp(self) -> None:
        os.environ["SMARTIDS_INTERNAL_SERVICE_TOKEN"] = TEST_SECRET
        get_settings.cache_clear()
        self.fake_redis = FakeAsyncRedis()
        app.dependency_overrides[get_internal_auth_redis] = lambda: self.fake_redis
        engine_ws_manager_module.engine_ws_manager._connections.clear()
        engine_ws_manager_module.engine_ws_manager._by_engine_id.clear()
        FakeEngineRepository.engines_by_public_id = {}
        self.repository_patcher = patch(
            "app.features.realtime.engine_ws_router.EngineRepository", FakeEngineRepository
        )
        self.session_patcher = patch(
            "app.features.realtime.engine_ws_router.async_session_factory",
            lambda: FakeSessionCM(),
        )
        self.repository_patcher.start()
        self.session_patcher.start()

    def tearDown(self) -> None:
        self.session_patcher.stop()
        self.repository_patcher.stop()
        app.dependency_overrides.pop(get_internal_auth_redis, None)
        engine_ws_manager_module.engine_ws_manager._connections.clear()
        engine_ws_manager_module.engine_ws_manager._by_engine_id.clear()
        FakeEngineRepository.engines_by_public_id = {}

    def test_force_disconnect_closes_live_engine_scoped_connection(self) -> None:
        secret = "engine-ws-secret-force-close-00"
        FakeEngineRepository.engines_by_public_id["engine-ws-force-1"] = SimpleNamespace(
            engine_public_id="engine-ws-force-1",
            status=EngineStatus.active,
            secret=secret,
            previous_secret=None,
            previous_secret_expires_at=None,
        )
        auth = sign_ws_auth(
            secret=secret, nonce="ws-nonce-force-close-000000000", engine_id="engine-ws-force-1"
        )
        with TestClient(app) as client:
            with client.websocket_connect("/api/v1/realtime/engine-ws") as ws:
                ws.send_json({"type": "auth", "id": "1", "ts": time.time(), "payload": auth})
                reply = ws.receive_json()
                self.assertEqual(reply["payload"]["status"], "ok")

                closed = asyncio.run(
                    engine_ws_manager_module.engine_ws_manager.force_disconnect(
                        "engine-ws-force-1", code=WS_CLOSE_ENGINE_REVOKED, reason="revoked"
                    )
                )
                self.assertTrue(closed)

                with self.assertRaises(Exception):
                    ws.receive_json()

    def test_force_disconnect_returns_false_for_unconnected_engine(self) -> None:
        closed = asyncio.run(
            engine_ws_manager_module.engine_ws_manager.force_disconnect(
                "engine-ws-never-connected", code=WS_CLOSE_ENGINE_REVOKED, reason="revoked"
            )
        )
        self.assertFalse(closed)


if __name__ == "__main__":
    unittest.main()
