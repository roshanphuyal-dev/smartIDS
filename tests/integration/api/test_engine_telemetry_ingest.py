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
os.environ.setdefault("PASSWORD_RESET_BASE_URL", "http://127.0.0.1:3000/reset-password")
os.environ["SMARTIDS_INTERNAL_SERVICE_TOKEN"] = TEST_SECRET

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.common.exception_handlers import register_exception_handlers
from app.core.config import get_settings
from app.core.redis import get_internal_auth_redis
from app.features.engine_telemetry.dependencies import get_engine_telemetry_service
from app.features.engine_telemetry.router import router


def sign_request(method: str, path_with_query: str, body: bytes = b"") -> dict[str, str]:
    """Build valid x-smartids-* signing headers, mirroring the production
    signing-string construction in app.common.internal_auth."""
    timestamp = str(time.time())
    nonce = "test-nonce-0000000000000000"
    body_hash = hashlib.sha256(body).hexdigest()
    signing_string = f"{method.upper()}\n{path_with_query}\n{body_hash}\n{timestamp}\n{nonce}"
    signature = hmac.new(TEST_SECRET.encode(), signing_string.encode(), hashlib.sha256).hexdigest()
    return {
        "x-smartids-signature": signature,
        "x-smartids-timestamp": timestamp,
        "x-smartids-nonce": nonce,
        "Content-Type": "application/json",
    }


class FakeAsyncRedis:
    """Minimal in-memory stand-in for redis.asyncio.Redis's SET NX EX usage."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def set(self, name: str, value: str, nx: bool = False, ex: int | None = None) -> bool | None:
        if nx and name in self._store:
            return None
        self._store[name] = value
        return True


class FakeEngineTelemetryService:
    payloads = []

    async def ingest(self, payload):
        self.payloads.append(payload)
        return {
            "accepted": True,
            "packets_received_total": payload.packets_received_total,
            "active_sessions": payload.active_sessions,
            "packet_loss_detected": payload.packet_loss_detected,
            "packet_queue_size": payload.packet_queue_size,
        }


class EngineTelemetryIngestTest(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["SMARTIDS_INTERNAL_SERVICE_TOKEN"] = TEST_SECRET
        get_settings.cache_clear()
        FakeEngineTelemetryService.payloads = []
        self.app = FastAPI()
        register_exception_handlers(self.app)
        self.app.include_router(router, prefix="/api/v1")
        self.app.dependency_overrides[get_engine_telemetry_service] = lambda: FakeEngineTelemetryService()
        self.app.dependency_overrides[get_internal_auth_redis] = lambda: FakeAsyncRedis()
        self.client = TestClient(self.app)

    def test_rejects_anonymous_ingest(self) -> None:
        response = self.client.post(
            "/api/v1/engine-telemetry",
            json=self._payload(),
        )

        self.assertEqual(response.status_code, 401)

    def test_ingests_runtime_payload(self) -> None:
        body = json.dumps(self._payload()).encode("utf-8")
        headers = sign_request("POST", "/api/v1/engine-telemetry", body=body)
        response = self.client.post(
            "/api/v1/engine-telemetry",
            content=body,
            headers=headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(FakeEngineTelemetryService.payloads), 1)
        payload = FakeEngineTelemetryService.payloads[0]
        self.assertEqual(payload.packets_received_total, 10)
        self.assertEqual(payload.packets_received_per_30s, 4)
        self.assertEqual(payload.active_sessions, 2)
        self.assertEqual(payload.packet_queue_size, 3)
        self.assertEqual(payload.packets_lost_total, 1)
        self.assertTrue(payload.packet_loss_detected)
        self.assertEqual(payload.ml_predictions_per_30s, 5)
        self.assertEqual(payload.active_network_exchanges[0].destination_port, 443)
        self.assertEqual(payload.secondary_model_queue_size, 12)
        self.assertEqual(payload.secondary_model_queue_maxsize, 256)
        self.assertEqual(payload.secondary_model_queue_usage_percent, 4.6875)
        self.assertEqual(payload.secondary_model_predictions_dropped_total, 2)
        self.assertEqual(payload.secondary_model_predictions_total, 40)
        self.assertEqual(payload.secondary_model_predictions_per_30s, 6)

    def test_ingests_runtime_payload_without_secondary_model_fields_defaults_to_zero(self) -> None:
        payload_dict = self._payload()
        for field in (
            "secondary_model_queue_size",
            "secondary_model_queue_maxsize",
            "secondary_model_queue_usage_percent",
            "secondary_model_predictions_dropped_total",
            "secondary_model_predictions_total",
            "secondary_model_predictions_per_30s",
        ):
            payload_dict.pop(field, None)

        body = json.dumps(payload_dict).encode("utf-8")
        headers = sign_request("POST", "/api/v1/engine-telemetry", body=body)
        response = self.client.post(
            "/api/v1/engine-telemetry",
            content=body,
            headers=headers,
        )

        self.assertEqual(response.status_code, 200)
        payload = FakeEngineTelemetryService.payloads[0]
        self.assertEqual(payload.secondary_model_queue_size, 0)
        self.assertEqual(payload.secondary_model_queue_maxsize, 0)
        self.assertEqual(payload.secondary_model_queue_usage_percent, 0.0)
        self.assertEqual(payload.secondary_model_predictions_dropped_total, 0)
        self.assertEqual(payload.secondary_model_predictions_total, 0)
        self.assertEqual(payload.secondary_model_predictions_per_30s, 0)

    @staticmethod
    def _payload() -> dict:
        return {
            "ts": datetime(2026, 6, 16, tzinfo=timezone.utc).isoformat(),
            "packets_received_total": 10,
            "packets_received_per_30s": 4,
            "packets_processed_total": 9,
            "packets_dropped_total": 1,
            "packets_lost_total": 1,
            "packet_loss_detected": True,
            "packet_queue_size": 3,
            "packet_queue_maxsize": 10,
            "packet_queue_usage_percent": 30.0,
            "active_sessions": 2,
            "ml_predictions_total": 20,
            "ml_predictions_per_30s": 5,
            "ml_processing_rate_per_30s": 5,
            "last_ml_prediction_latency_ms": 12.5,
            "secondary_model_queue_size": 12,
            "secondary_model_queue_maxsize": 256,
            "secondary_model_queue_usage_percent": 4.6875,
            "secondary_model_predictions_dropped_total": 2,
            "secondary_model_predictions_total": 40,
            "secondary_model_predictions_per_30s": 6,
            "application_attribution_available": False,
            "application_attribution_note": "Process attribution is unavailable.",
            "active_network_exchanges": [
                {
                    "source_ip": "10.0.0.1",
                    "destination_ip": "10.0.0.2",
                    "source_port": 12345,
                    "destination_port": 443,
                    "protocol": 6,
                    "packet_count": 5,
                    "byte_count": 500,
                    "duration": 1.2,
                }
            ],
        }
