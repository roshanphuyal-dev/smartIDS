from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import types
import importlib.metadata

ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = ROOT / "backend"
for path in (ROOT, BACKEND_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

# 64 hex chars (256 bits) — satisfies Settings' production-strength validator
# even though these tests run with ENVIRONMENT=development.
TEST_SECRET = "1234567890abcdef" * 4

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1:5432/testdb")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("PASSWORD_RESET_BASE_URL", "http://127.0.0.1:3000")
os.environ["SMARTIDS_INTERNAL_SERVICE_TOKEN"] = TEST_SECRET

if "authlib" not in sys.modules:
    authlib_module = types.ModuleType("authlib")
    integrations_module = types.ModuleType("authlib.integrations")
    httpx_client_module = types.ModuleType("authlib.integrations.httpx_client")

    class _DummyAsyncOAuth2Client:  # pragma: no cover - test harness stub
        def __init__(self, *args, **kwargs):
            pass

        def create_authorization_url(self, *args, **kwargs):
            return ("", None)

        async def fetch_token(self, *args, **kwargs):
            return {}

        async def get(self, *args, **kwargs):
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: {},
            )

    httpx_client_module.AsyncOAuth2Client = _DummyAsyncOAuth2Client
    integrations_module.httpx_client = httpx_client_module
    authlib_module.integrations = integrations_module
    sys.modules["authlib"] = authlib_module
    sys.modules["authlib.integrations"] = integrations_module
    sys.modules["authlib.integrations.httpx_client"] = httpx_client_module

if "argon2" not in sys.modules:
    argon2_module = types.ModuleType("argon2")
    argon2_exceptions_module = types.ModuleType("argon2.exceptions")

    class _DummyPasswordHasher:  # pragma: no cover - test harness stub
        def hash(self, value):
            return f"hashed:{value}"

        def verify(self, hashed, value):
            return hashed == f"hashed:{value}"

    argon2_module.PasswordHasher = _DummyPasswordHasher
    argon2_exceptions_module.InvalidHashError = ValueError
    argon2_exceptions_module.VerifyMismatchError = ValueError
    sys.modules["argon2"] = argon2_module
    sys.modules["argon2.exceptions"] = argon2_exceptions_module

if "email_validator" not in sys.modules:
    email_validator_module = types.ModuleType("email_validator")

    class _DummyEmailNotValidError(ValueError):
        pass

    def _dummy_validate_email(email, *args, **kwargs):  # pragma: no cover - test harness stub
        return types.SimpleNamespace(email=email, normalized=email, local_part=email.split("@", 1)[0])

    email_validator_module.EmailNotValidError = _DummyEmailNotValidError
    email_validator_module.validate_email = _dummy_validate_email
    sys.modules["email_validator"] = email_validator_module

_original_metadata_version = importlib.metadata.version


def _metadata_version(name: str) -> str:
    if name == "email-validator":
        return "2.0.0"
    return _original_metadata_version(name)


importlib.metadata.version = _metadata_version

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.common.exception_handlers import register_exception_handlers
from app.core.config import get_settings
from app.core.redis import get_internal_auth_redis
from app.features.alerts.dependencies import get_alert_service
from app.features.alerts.router import router as alerts_router
from app.features.block_events.dependencies import get_block_event_service
from app.features.block_events.router import router as block_events_router
from app.features.engine_commands.dependencies import get_engine_command_service
from app.features.engine_commands.router import router as engine_commands_router
from app.features.engine_telemetry.dependencies import get_engine_telemetry_service
from app.features.engine_telemetry.router import router as engine_telemetry_router
from app.features.ids_events.dependencies import get_ids_event_service
from app.features.ids_events.router import router as ids_events_router
from app.features.sessions.dependencies import get_network_session_service
from app.features.sessions.router import router as sessions_router
from app.features.sql_injection.dependencies import get_sql_injection_service
from app.features.sql_injection.router import router as sql_injection_router


def sign_request(
    method: str,
    path_with_query: str,
    body: bytes = b"",
    secret: str = TEST_SECRET,
    timestamp: str | None = None,
    nonce: str = "test-nonce-0000000000000000",
) -> dict[str, str]:
    """Build valid x-smartids-* signing headers, mirroring the production
    signing-string construction in app.common.internal_auth."""
    if timestamp is None:
        timestamp = str(time.time())
    body_hash = hashlib.sha256(body).hexdigest()
    signing_string = f"{method.upper()}\n{path_with_query}\n{body_hash}\n{timestamp}\n{nonce}"
    signature = hmac.new(secret.encode(), signing_string.encode(), hashlib.sha256).hexdigest()
    return {
        "x-smartids-signature": signature,
        "x-smartids-timestamp": timestamp,
        "x-smartids-nonce": nonce,
    }


def json_dumps(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


class FakeAsyncRedis:
    """Minimal in-memory stand-in for redis.asyncio.Redis's SET NX EX usage."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def set(self, name: str, value: str, nx: bool = False, ex: int | None = None) -> bool | None:
        if nx and name in self._store:
            return None
        self._store[name] = value
        return True


class FakeIDSEventService:
    async def ingest_event(self, payload):
        now = datetime.now(timezone.utc)
        event = SimpleNamespace(
            id="ids-1",
            event_id=payload.event_id,
            schema_version=payload.schema_version,
            ts=payload.ts,
            source=payload.source,
            model=payload.model,
            prediction=payload.prediction,
            confidence=payload.confidence,
            severity=payload.severity,
            action=payload.action,
            protocol=payload.protocol,
            features=payload.features,
            created_at=now,
            updated_at=now,
        )
        return event, True, False


class FakeAlertService:
    async def upsert_alert(self, payload):
        now = datetime.now(timezone.utc)
        alert = SimpleNamespace(
            id="alert-1",
            dedup_key=payload.dedup_key,
            event_id=payload.event_id,
            prediction=payload.prediction,
            severity=payload.severity,
            confidence=payload.confidence,
            action=payload.action,
            source=payload.source,
            status=payload.status,
            first_seen_at=now,
            last_seen_at=now,
            occurrence_count=1,
            threat_id=payload.threat_id,
            detection_method=payload.detection_method,
            action_taken=payload.action_taken,
            session_id=payload.session_id,
            source_ip=payload.source_ip,
            destination_ip=payload.destination_ip,
            source_port=payload.source_port,
            destination_port=payload.destination_port,
            protocol=payload.protocol,
            risk_score=payload.risk_score,
            is_final=payload.is_final,
            created_at=now,
            updated_at=now,
        )
        return alert, True


class FakeNetworkSessionService:
    async def upsert_session(self, payload):
        now = datetime.now(timezone.utc)
        session = SimpleNamespace(
            id="session-1",
            session_id=payload.session_id,
            start_time=payload.start_time,
            end_time=payload.end_time,
            source_ip=payload.source_ip,
            destination_ip=payload.destination_ip,
            source_port=payload.source_port,
            destination_port=payload.destination_port,
            protocol=payload.protocol,
            packet_count=payload.packet_count,
            byte_count=payload.byte_count,
            duration=payload.duration,
            risk_score=payload.risk_score,
            ml_prediction=payload.ml_prediction,
            heuristic_result=payload.heuristic_result,
            state=payload.state,
            created_at=now,
            updated_at=now,
        )
        return session, True


class FakeBlockEventService:
    async def upsert(self, payload):
        now = datetime.now(timezone.utc)
        event = SimpleNamespace(
            id="block-1",
            event_id=payload.event_id,
            ts=payload.timestamp,
            source_ip=payload.source_ip,
            action_taken=payload.action_taken,
            reason=payload.reason,
            detection_method=payload.detection_method,
            session_id=payload.session_id,
            source_port=payload.source_port,
            destination_ip=payload.destination_ip,
            destination_port=payload.destination_port,
            protocol=payload.protocol,
            created_at=now,
            updated_at=now,
        )
        return event, True


class FakeEngineCommandService:
    async def enqueue_command(self, payload):
        return (
            {
                "command_id": payload.command_id,
                "action": payload.action,
                "ip_address": str(payload.ip_address),
                "duration_seconds": payload.duration_seconds,
                "status": "queued",
            },
            True,
        )

    async def poll_commands(self, limit: int):
        return [
            {
                "command_id": "cmd-1",
                "action": "watchlist",
                "ip_address": "203.0.113.10",
                "duration_seconds": 300,
                "status": "queued",
            }
        ][:limit]

    async def acknowledge_command(self, payload):
        return {
            "command_id": payload.command_id,
            "acked": True,
            "status": payload.status,
            "ack_source": payload.ack_source,
        }


class FakeEngineTelemetryService:
    async def ingest(self, payload):
        return {
            "accepted": True,
            "packets_received_total": payload.packets_received_total,
            "active_sessions": payload.active_sessions,
            "packet_loss_detected": payload.packet_loss_detected,
        }


class FakeSQLInjectionService:
    async def decide(self, payload):
        detected = bool(payload.detected)
        return SimpleNamespace(
            request_id=payload.request_id,
            decision="block" if detected else "allow",
            http_status=400 if detected else 200,
            detected=detected,
            confidence=payload.confidence,
            reason=payload.reason,
            model_dump=lambda mode="json": {
                "request_id": payload.request_id,
                "decision": "block" if detected else "allow",
                "http_status": 400 if detected else 200,
                "detected": detected,
                "confidence": payload.confidence,
                "reason": payload.reason,
            },
        )


app = FastAPI()
register_exception_handlers(app)
app.include_router(ids_events_router, prefix="/api/v1")
app.include_router(alerts_router, prefix="/api/v1")
app.include_router(sessions_router, prefix="/api/v1")
app.include_router(block_events_router, prefix="/api/v1")
app.include_router(engine_commands_router, prefix="/api/v1")
app.include_router(engine_telemetry_router, prefix="/api/v1")
app.include_router(sql_injection_router, prefix="/api/v1")

app.dependency_overrides[get_ids_event_service] = lambda: FakeIDSEventService()
app.dependency_overrides[get_alert_service] = lambda: FakeAlertService()
app.dependency_overrides[get_network_session_service] = lambda: FakeNetworkSessionService()
app.dependency_overrides[get_block_event_service] = lambda: FakeBlockEventService()
app.dependency_overrides[get_engine_command_service] = lambda: FakeEngineCommandService()
app.dependency_overrides[get_engine_telemetry_service] = lambda: FakeEngineTelemetryService()
app.dependency_overrides[get_sql_injection_service] = lambda: FakeSQLInjectionService()


class InternalServiceAuthTest(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["SMARTIDS_INTERNAL_SERVICE_TOKEN"] = TEST_SECRET
        get_settings.cache_clear()
        # Fresh in-memory nonce store per test so replay checks don't leak
        # across test cases (and no real Redis is required to run this file).
        self.fake_redis = FakeAsyncRedis()
        app.dependency_overrides[get_internal_auth_redis] = lambda: self.fake_redis

    def tearDown(self) -> None:
        app.dependency_overrides.pop(get_internal_auth_redis, None)

    def test_anonymous_requests_are_rejected(self) -> None:
        with TestClient(app) as client:
            cases = [
                ("post", "/api/v1/ids-events", {"schema_version": "v1", "event_id": "e-1", "ts": "2026-06-15T00:00:00Z", "source": "smoke", "model": "m", "prediction": "p", "confidence": 0.5, "severity": "low", "action": "allow"}),
                ("post", "/api/v1/alerts/upsert", {"dedup_key": "k", "event_id": "e-1", "prediction": "p", "severity": "low", "confidence": 0.5, "action": "allow", "source": "smoke"}),
                ("post", "/api/v1/sessions/upsert", {"session_id": "s-1", "start_time": "2026-06-15T00:00:00Z", "source_ip": "10.0.0.1", "destination_ip": "10.0.0.2", "protocol": 6}),
                ("post", "/api/v1/block-events/upsert", {"event_id": "b-1", "timestamp": "2026-06-15T00:00:00Z", "source_ip": "10.0.0.1", "action_taken": "blocked", "reason": "smoke", "detection_method": "manual"}),
                ("post", "/api/v1/engine-commands", {"command_id": "c-1", "action": "watchlist", "ip_address": "203.0.113.10", "duration_seconds": 300}),
                ("get", "/api/v1/engine-commands?limit=1", None),
                ("post", "/api/v1/engine-commands/ack", {"command_id": "c-1", "status": "queued"}),
                ("post", "/api/v1/engine-telemetry", {"packets_received_total": 1, "packets_received_per_30s": 1, "packets_processed_total": 1, "packets_dropped_total": 0, "packets_lost_total": 0, "packet_loss_detected": False, "packet_queue_size": 0, "packet_queue_maxsize": 1000, "packet_queue_usage_percent": 0.0, "active_sessions": 0, "ml_predictions_total": 0, "ml_predictions_per_30s": 0, "ml_processing_rate_per_30s": 0.0, "application_attribution_available": False}),
                ("post", "/api/v1/sql-injection/decide", {"request_id": "sqli-1", "ts": "2026-06-15T00:00:00Z", "source": "smoke", "query": "SELECT 1", "detected": False, "confidence": 0.5}),
            ]

            for method, path, payload in cases:
                with self.subTest(path=path):
                    response = client.request(method, path, json=payload)
                    self.assertEqual(response.status_code, 401, response.text)

    def test_valid_signed_request_allows_ingest(self) -> None:
        # Uses the engine-commands endpoint (not ids-events): FakeIDSEventService
        # in this file is missing several attributes IDSEventResponse now
        # requires (source_ip, destination_ip, source_port, destination_port,
        # attack_type, session_id) — a pre-existing schema-drift bug unrelated
        # to internal-auth signing, previously masked because the old bare-token
        # check always returned 401 before reaching response serialization.
        payload = {
            "command_id": "c-allow",
            "action": "watchlist",
            "ip_address": "203.0.113.15",
            "duration_seconds": 300,
        }
        body = json_dumps(payload)
        headers = sign_request("POST", "/api/v1/engine-commands", body=body)
        headers["Content-Type"] = "application/json"

        with TestClient(app) as client:
            response = client.post("/api/v1/engine-commands", content=body, headers=headers)

            self.assertNotEqual(response.status_code, 401)
            self.assertEqual(response.status_code, 201, response.text)

    def test_tampered_signature_rejected(self) -> None:
        payload = {"command_id": "c-tampered", "action": "watchlist", "ip_address": "203.0.113.11", "duration_seconds": 300}
        body = json_dumps(payload)
        headers = sign_request("POST", "/api/v1/engine-commands", body=body)
        flipped = ("0" if headers["x-smartids-signature"][0] != "0" else "1") + headers["x-smartids-signature"][1:]
        headers["x-smartids-signature"] = flipped

        with TestClient(app) as client:
            response = client.post("/api/v1/engine-commands", content=body, headers=headers)
            self.assertEqual(response.status_code, 401, response.text)

    def test_body_signed_but_different_body_sent_rejected(self) -> None:
        signed_body = json_dumps({"command_id": "c-signed", "action": "watchlist", "ip_address": "203.0.113.12", "duration_seconds": 300})
        sent_body = json_dumps({"command_id": "c-sent-instead", "action": "watchlist", "ip_address": "203.0.113.12", "duration_seconds": 300})
        headers = sign_request("POST", "/api/v1/engine-commands", body=signed_body)

        with TestClient(app) as client:
            response = client.post("/api/v1/engine-commands", content=sent_body, headers=headers)
            self.assertEqual(response.status_code, 401, response.text)

    def test_expired_timestamp_rejected(self) -> None:
        payload = {"command_id": "c-expired", "action": "watchlist", "ip_address": "203.0.113.13", "duration_seconds": 300}
        body = json_dumps(payload)
        stale_timestamp = str(time.time() - 120)  # > 30s window
        headers = sign_request("POST", "/api/v1/engine-commands", body=body, timestamp=stale_timestamp)

        with TestClient(app) as client:
            response = client.post("/api/v1/engine-commands", content=body, headers=headers)
            self.assertEqual(response.status_code, 401, response.text)

    def test_replayed_nonce_rejected(self) -> None:
        payload = {"command_id": "c-replay", "action": "watchlist", "ip_address": "203.0.113.14", "duration_seconds": 300}
        body = json_dumps(payload)
        headers = sign_request("POST", "/api/v1/engine-commands", body=body, nonce="replay-nonce-fixed")
        headers["Content-Type"] = "application/json"

        with TestClient(app) as client:
            first = client.post("/api/v1/engine-commands", content=body, headers=headers)
            self.assertEqual(first.status_code, 201, first.text)

            second = client.post("/api/v1/engine-commands", content=body, headers=headers)
            self.assertEqual(second.status_code, 401, second.text)


if __name__ == "__main__":
    unittest.main()
