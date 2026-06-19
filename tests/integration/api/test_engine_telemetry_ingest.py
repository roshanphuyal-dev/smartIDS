from __future__ import annotations

import os
import sys
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

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1:5432/testdb")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("PASSWORD_RESET_BASE_URL", "http://127.0.0.1:3000/reset-password")
os.environ["INTERNAL_SERVICE_TOKEN"] = "test-token"

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.common.exception_handlers import register_exception_handlers
from app.core.config import get_settings
from app.features.engine_telemetry.dependencies import get_engine_telemetry_service
from app.features.engine_telemetry.router import router


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
        os.environ["INTERNAL_SERVICE_TOKEN"] = "test-token"
        get_settings.cache_clear()
        FakeEngineTelemetryService.payloads = []
        self.app = FastAPI()
        register_exception_handlers(self.app)
        self.app.include_router(router, prefix="/api/v1")
        self.app.dependency_overrides[get_engine_telemetry_service] = lambda: FakeEngineTelemetryService()
        self.client = TestClient(self.app)

    def test_rejects_anonymous_ingest(self) -> None:
        response = self.client.post(
            "/api/v1/engine-telemetry",
            json=self._payload(),
        )

        self.assertEqual(response.status_code, 401)

    def test_ingests_runtime_payload(self) -> None:
        response = self.client.post(
            "/api/v1/engine-telemetry",
            json=self._payload(),
            headers={"x-smartids-internal-token": "test-token"},
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
