from __future__ import annotations

import asyncio
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = ROOT / "backend"
for path in (ROOT, BACKEND_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1:5432/testdb")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("PASSWORD_RESET_BASE_URL", "http://127.0.0.1:3000")

from app.features.engine_telemetry.schemas import EngineTelemetryIngestRequest
from app.features.engine_telemetry.service import EngineTelemetryService
from app.features.ids_events.schemas import IDSEventIngestRequest
from app.features.ids_events.service import IDSEventService
from app.features.sessions.schemas import NetworkSessionUpsertRequest
from app.features.sessions.service import NetworkSessionService


class FakeRealtimeService:
    def __init__(self, _manager) -> None:
        self.alert_messages = []
        self.log_messages = []
        self.session_messages = []
        self.traffic_messages = []
        self.health_messages = []
        self.dashboard_messages = []

    async def broadcast_alert(self, payload) -> None:
        self.alert_messages.append(payload)

    async def broadcast_logs_update(self, payload) -> None:
        self.log_messages.append(payload)

    async def broadcast_session_update(self, payload) -> None:
        self.session_messages.append(payload)

    async def broadcast_traffic_update(self, payload) -> None:
        self.traffic_messages.append(payload)

    async def broadcast_health_update(self, payload) -> None:
        self.health_messages.append(payload)

    async def broadcast_dashboard_metrics(self, payload) -> None:
        self.dashboard_messages.append(payload)


class FakeDashboardService:
    def __init__(self, _session) -> None:
        self.broadcasts = 0

    async def broadcast_summary_metrics(self) -> None:
        self.broadcasts += 1


class FakeTelemetrySnapshot:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)
        self.id = kwargs.get("id", "telemetry-1")
        self.created_at = kwargs.get("created_at", kwargs["ts"])
        self.updated_at = kwargs.get("updated_at", kwargs["ts"])


class FakeTelemetryRepository:
    def __init__(self, _session) -> None:
        self.created = []

    async def create(self, snapshot):
        self.created.append(snapshot)
        return snapshot

    async def get_latest(self):
        return self.created[-1] if self.created else None

    async def list_history(self, *, limit: int, offset: int):
        items = list(reversed(self.created))[offset : offset + limit]
        return items, len(self.created)


class FakeIDSEvent:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)
        now = kwargs.get("ts", datetime.now(timezone.utc))
        self.id = kwargs.get("id", "evt-1")
        self.created_at = now
        self.updated_at = now


class FakeIDSEventRepository:
    def __init__(self, _session) -> None:
        self.created = []

    async def get_by_event_id(self, _event_id: str):
        return None

    async def create(self, event):
        self.created.append(event)
        return event

    async def list_events(self, **_kwargs):
        return [], 0


class FakeAlertService:
    def __init__(self, _session) -> None:
        self.requests = []

    async def upsert_alert(self, payload) -> None:
        self.requests.append(payload)


class FakeNetworkSession:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)
        now = datetime.now(timezone.utc)
        self.updated_at = kwargs.get("updated_at", now)
        self.created_at = kwargs.get("created_at", now)


class FakeSessionRepository:
    def __init__(self, _session) -> None:
        self.existing = None
        self.created = None
        self.saved = None

    async def get_by_session_id(self, _session_id: str):
        return self.existing

    async def create(self, session_row):
        self.created = session_row
        return session_row

    async def save(self, session_row):
        self.saved = session_row
        return session_row

    async def list_sessions(self, **_kwargs):
        return [], 0


class LiveDashboardServicesTest(unittest.TestCase):
    def test_engine_telemetry_persists_and_broadcasts(self) -> None:
        service_state = {}

        def repo_factory(_session):
            repo = FakeTelemetryRepository(_session)
            service_state["repo"] = repo
            return repo

        def dashboard_factory(_session):
            dashboard = FakeDashboardService(_session)
            service_state["dashboard"] = dashboard
            return dashboard

        with patch("app.features.engine_telemetry.service.EngineTelemetryRepository", side_effect=repo_factory), patch(
            "app.features.engine_telemetry.service.DashboardService", side_effect=dashboard_factory
        ), patch("app.features.engine_telemetry.service.RealtimeService", FakeRealtimeService), patch(
            "app.features.engine_telemetry.service.EngineTelemetrySnapshot", FakeTelemetrySnapshot
        ):
            service = EngineTelemetryService(SimpleNamespace())
            payload = EngineTelemetryIngestRequest(
                ts=datetime(2026, 6, 17, tzinfo=timezone.utc),
                packets_received_total=10,
                packets_received_per_30s=4,
                packets_processed_total=9,
                packets_dropped_total=1,
                packets_lost_total=1,
                packet_loss_detected=True,
                packet_queue_size=3,
                packet_queue_maxsize=10,
                packet_queue_usage_percent=30.0,
                active_sessions=2,
                ml_predictions_total=20,
                ml_predictions_per_30s=5,
                ml_processing_rate_per_30s=5.0,
                last_ml_prediction_latency_ms=12.5,
                application_attribution_available=False,
                application_attribution_note="Unavailable",
                active_network_exchanges=[],
            )

            result = asyncio.run(service.ingest(payload))
            latest = asyncio.run(service.get_latest_snapshot())
            history, total = asyncio.run(service.list_history(limit=10, offset=0))

        self.assertTrue(result["accepted"])
        self.assertEqual(service_state["dashboard"].broadcasts, 1)
        self.assertEqual(len(service._realtime_service.health_messages), 1)
        self.assertEqual(len(service._realtime_service.dashboard_messages), 1)
        self.assertEqual(latest.packets_received_total, 10)
        self.assertEqual(total, 1)
        self.assertEqual(history[0].packet_queue_size, 3)

    def test_ids_event_ingest_broadcasts_threat_and_logs_channels(self) -> None:
        with patch("app.features.ids_events.service.IDSEventRepository", FakeIDSEventRepository), patch(
            "app.features.ids_events.service.AlertService", FakeAlertService
        ), patch("app.features.ids_events.service.DashboardService", FakeDashboardService), patch(
            "app.features.ids_events.service.RealtimeService", FakeRealtimeService
        ), patch("app.features.ids_events.service.IDSEvent", FakeIDSEvent):
            service = IDSEventService(SimpleNamespace())
            payload = IDSEventIngestRequest(
                schema_version="v1",
                event_id="event-1",
                ts=datetime(2026, 6, 17, tzinfo=timezone.utc),
                source="sensor-a",
                model="xgboost",
                prediction="DDoS",
                confidence=0.94,
                severity="high",
                action="block",
                protocol=6,
                source_ip="10.0.0.1",
                destination_ip="10.0.0.2",
                source_port=1234,
                destination_port=443,
                session_id="session-1",
                attack_type="DDoS",
                features={"session_packet_count": 5, "session_byte_count": 900},
            )

            event, created, alert_triggered = asyncio.run(service.ingest_event(payload))

        self.assertTrue(created)
        self.assertTrue(alert_triggered)
        self.assertEqual(event.source_ip, "10.0.0.1")
        self.assertEqual(event.session_id, "session-1")
        self.assertEqual(len(service._realtime_service.alert_messages), 1)
        self.assertEqual(len(service._realtime_service.log_messages), 1)

    def test_ids_event_ingest_keeps_benign_events_out_of_threat_channel(self) -> None:
        with patch("app.features.ids_events.service.IDSEventRepository", FakeIDSEventRepository), patch(
            "app.features.ids_events.service.AlertService", FakeAlertService
        ), patch("app.features.ids_events.service.DashboardService", FakeDashboardService), patch(
            "app.features.ids_events.service.RealtimeService", FakeRealtimeService
        ), patch("app.features.ids_events.service.IDSEvent", FakeIDSEvent):
            service = IDSEventService(SimpleNamespace())
            payload = IDSEventIngestRequest(
                schema_version="v1",
                event_id="event-normal-1",
                ts=datetime(2026, 6, 17, tzinfo=timezone.utc),
                source="sensor-a",
                model="xgboost",
                prediction="Normal Traffic",
                confidence=0.02,
                severity="low",
                action="allow",
                protocol=6,
                source_ip="10.0.0.10",
                destination_ip="10.0.0.11",
                source_port=4567,
                destination_port=80,
                session_id="session-normal-1",
                attack_type="Normal Traffic",
                action_taken="allow",
                features={"session_packet_count": 4, "session_byte_count": 256},
            )

            _event, created, alert_triggered = asyncio.run(service.ingest_event(payload))

        self.assertTrue(created)
        self.assertFalse(alert_triggered)
        self.assertEqual(len(service._realtime_service.alert_messages), 0)
        self.assertEqual(len(service._realtime_service.log_messages), 1)

    def test_session_upsert_broadcasts_session_and_traffic_channels(self) -> None:
        with patch("app.features.sessions.service.NetworkSessionRepository", FakeSessionRepository), patch(
            "app.features.sessions.service.DashboardService", FakeDashboardService
        ), patch("app.features.sessions.service.RealtimeService", FakeRealtimeService), patch(
            "app.features.sessions.service.NetworkSession", FakeNetworkSession
        ):
            service = NetworkSessionService(SimpleNamespace())
            payload = NetworkSessionUpsertRequest(
                session_id="session-123",
                start_time=datetime(2026, 6, 17, tzinfo=timezone.utc),
                end_time=None,
                last_seen_at=datetime(2026, 6, 17, 0, 0, 5, tzinfo=timezone.utc),
                source_ip="10.0.0.1",
                destination_ip="10.0.0.2",
                source_port=1234,
                destination_port=80,
                protocol=6,
                packet_count=5,
                byte_count=2048,
                duration=3.5,
                risk_score=0.9,
                ml_prediction="SQL Injection",
                heuristic_result="suspicious",
                state="active",
            )

            session, created = asyncio.run(service.upsert_session(payload))

        self.assertTrue(created)
        self.assertEqual(session.last_seen_at, payload.last_seen_at)
        self.assertEqual(len(service._realtime_service.session_messages), 1)
        self.assertEqual(len(service._realtime_service.traffic_messages), 1)
