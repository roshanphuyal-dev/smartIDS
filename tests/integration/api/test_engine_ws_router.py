from __future__ import annotations

import hashlib
import hmac
import os
import time
import unittest
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
from app.features.realtime import engine_ws_manager as engine_ws_manager_module
from app.features.realtime.engine_ws_router import router as engine_ws_router
from app.features.realtime.engine_ws_schemas import ENGINE_WS_AUTH_METHOD, ENGINE_WS_AUTH_PATH


def sign_ws_auth(
    secret: str = TEST_SECRET,
    timestamp: str | None = None,
    nonce: str = "ws-nonce-000000000000000000000000",
) -> dict[str, str]:
    if timestamp is None:
        timestamp = str(time.time())
    body_hash = hashlib.sha256(b"").hexdigest()
    signing_string = f"{ENGINE_WS_AUTH_METHOD}\n{ENGINE_WS_AUTH_PATH}\n{body_hash}\n{timestamp}\n{nonce}"
    signature = hmac.new(secret.encode(), signing_string.encode(), hashlib.sha256).hexdigest()
    return {"signature": signature, "timestamp": timestamp, "nonce": nonce}


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


if __name__ == "__main__":
    unittest.main()
