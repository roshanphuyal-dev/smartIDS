from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = ROOT / "backend"
for path in (ROOT, BACKEND_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1:5432/testdb")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

from app.detection.router import detect_threats
from app.detection.schemas import DetectionRequest, DetectionResponse, NormalizedRequest, ThreatItem
from app.features.alerts.service import AlertService


def detection_request() -> DetectionRequest:
    return DetectionRequest(
        inspect=["query"],
        detect=["sqli"],
        request=NormalizedRequest(method="POST", path="/login", query={"id": "1 OR 1=1"}),
    )


def detection_response() -> DetectionResponse:
    return DetectionResponse(
        threat_detected=True,
        score=90,
        threats=[
            ThreatItem(
                type="sqli",
                location="query.id",
                confidence=0.95,
                matched_value="1 OR 1=1",
            )
        ],
    )


class DetectionAlertServiceTests(unittest.TestCase):
    def make_service(self) -> AlertService:
        service = AlertService.__new__(AlertService)
        service.upsert_alert = AsyncMock()
        service._realtime_service = type(
            "Realtime",
            (),
            {
                "broadcast_alert": AsyncMock(),
                "broadcast_logs_update": AsyncMock(),
            },
        )()
        service._dashboard_service = type(
            "Dashboard",
            (),
            {
                "broadcast_summary_metrics": AsyncMock(),
                "broadcast_threats_over_time": AsyncMock(),
                "broadcast_attack_distribution": AsyncMock(),
                "broadcast_network_threat_rollups": AsyncMock(),
            },
        )()
        return service

    def test_canonical_dedup_key_is_bounded_and_stable(self) -> None:
        first = AlertService.build_dedup_key(
            session_id="Session-1",
            source="Sensor-A",
            attack_type="DDoS",
            action="Block",
        )
        second = AlertService.build_dedup_key(
            session_id="session-1",
            source="sensor-a",
            attack_type="ddos",
            action="block",
        )

        self.assertEqual(first, second)
        self.assertRegex(first, r"^alert:v1:[0-9a-f]{32}$")

    def test_persistence_failure_is_non_fatal(self) -> None:
        service = self.make_service()
        service.upsert_alert.side_effect = RuntimeError("database unavailable")

        asyncio.run(service.record_http_detection(detection_request(), detection_response()))

        service._realtime_service.broadcast_alert.assert_not_awaited()

    def test_broadcast_failure_is_non_fatal(self) -> None:
        service = self.make_service()
        service._realtime_service.broadcast_alert.side_effect = RuntimeError("websocket unavailable")

        asyncio.run(service.record_http_detection(detection_request(), detection_response()))

        service.upsert_alert.assert_awaited_once()
        service._dashboard_service.broadcast_summary_metrics.assert_awaited_once()

    def test_success_broadcasts_realtime_and_dashboard_updates(self) -> None:
        service = self.make_service()

        asyncio.run(service.record_http_detection(detection_request(), detection_response()))

        service._realtime_service.broadcast_alert.assert_awaited_once()
        service._realtime_service.broadcast_logs_update.assert_awaited_once()
        service._dashboard_service.broadcast_summary_metrics.assert_awaited_once()
        service._dashboard_service.broadcast_threats_over_time.assert_awaited_once()
        service._dashboard_service.broadcast_attack_distribution.assert_awaited_once()
        service._dashboard_service.broadcast_network_threat_rollups.assert_awaited_once()

    def test_router_delegates_detection_alert_handling(self) -> None:
        request = detection_request()
        result = detection_response()
        orchestrator = type("Orchestrator", (), {"process_request": lambda _self, _request: result})()
        alert_service = type("Alerts", (), {"record_http_detection": AsyncMock()})()

        response = asyncio.run(detect_threats(request, orchestrator, alert_service))

        self.assertIs(response, result)
        alert_service.record_http_detection.assert_awaited_once_with(request, result)


if __name__ == "__main__":
    unittest.main()
