import threading
import os
import time
from queue import Queue
from pathlib import Path

from packet_capture.sniffers.live_sniffer import LiveSniffer
from packet_capture.sniffers.interface_manager import InterfaceManager
from packet_capture.utils.packet_filters import PacketFilters
from packet_capture.processor.packet_processor import PacketProcessor  # type: ignore
from packet_capture.forwarding.fastapi_alert_forwarder import FastAPIAlertForwarder
from packet_capture.forwarding.fastapi_block_event_forwarder import FastAPIBlockEventForwarder
from packet_capture.forwarding.fastapi_ids_event_forwarder import FastAPIIDSEventForwarder
from packet_capture.forwarding.fastapi_session_update_forwarder import FastAPISessionUpdateForwarder
from packet_capture.forwarding.fastapi_engine_telemetry_forwarder import FastAPIEngineTelemetryForwarder
from packet_capture.telemetry.engine_telemetry import EngineTelemetryCollector
from packet_capture.utils.logger import IDSLogger, log_event
from response_engine.backend_command_poller import BackendCommandPoller


class SnifferService:

    def __init__(self, interface=None, packet_filter=None, processor=None):
        self._load_project_env()
        self.logger = IDSLogger.get_logger("sniffer.service")

        self.interface = interface or InterfaceManager.get_default_interface()
        self.packet_queue = Queue(maxsize=10000)
        self.packet_filter = packet_filter or PacketFilters.basic_filter()

        fastapi_alert_endpoint = os.getenv("SMARTIDS_ALERT_ENDPOINT", "").strip()
        fastapi_ids_event_endpoint = os.getenv("SMARTIDS_IDS_EVENT_ENDPOINT", "").strip()
        fastapi_session_update_endpoint = os.getenv("SMARTIDS_SESSION_UPDATE_ENDPOINT", "").strip()
        fastapi_block_event_endpoint = os.getenv("SMARTIDS_BLOCK_EVENT_ENDPOINT", "").strip()
        fastapi_engine_telemetry_endpoint = os.getenv("SMARTIDS_ENGINE_TELEMETRY_ENDPOINT", "").strip()
        backend_commands_endpoint = os.getenv("SMARTIDS_COMMANDS_ENDPOINT", "").strip()
        backend_commands_ack_endpoint = os.getenv("SMARTIDS_COMMANDS_ACK_ENDPOINT", "").strip()
        internal_service_token = os.getenv("SMARTIDS_INTERNAL_SERVICE_TOKEN", "").strip()
        backend_commands_poll_interval_seconds = float(
            os.getenv("SMARTIDS_COMMANDS_POLL_INTERVAL_SECONDS", "1.5")
        )
        self.fastapi_alert_endpoint = fastapi_alert_endpoint
        self.fastapi_ids_event_endpoint = fastapi_ids_event_endpoint
        self.fastapi_session_update_endpoint = fastapi_session_update_endpoint
        self.fastapi_block_event_endpoint = fastapi_block_event_endpoint
        self.fastapi_engine_telemetry_endpoint = fastapi_engine_telemetry_endpoint
        self.backend_commands_endpoint = backend_commands_endpoint
        self.backend_commands_ack_endpoint = backend_commands_ack_endpoint
        self.backend_commands_poll_interval_seconds = max(0.5, backend_commands_poll_interval_seconds)
        self.backend_command_poller = None
        self.telemetry_collector = EngineTelemetryCollector()
        self.telemetry_forwarder = None
        self.telemetry_interval_seconds = max(
            5.0,
            float(os.getenv("SMARTIDS_ENGINE_TELEMETRY_INTERVAL_SECONDS", "30")),
        )
        if fastapi_engine_telemetry_endpoint:
            self.telemetry_forwarder = FastAPIEngineTelemetryForwarder(
                endpoint_url=fastapi_engine_telemetry_endpoint,
                internal_service_token=internal_service_token,
            )
        if backend_commands_endpoint:
            self.backend_command_poller = BackendCommandPoller(
                endpoint_url=backend_commands_endpoint,
                internal_service_token=internal_service_token,
            )
        if processor is not None:
            self.processor = processor
        else:
            alert_publisher = None
            event_publisher = None
            session_update_publisher = None
            block_event_publisher = None

            if fastapi_alert_endpoint:
                alert_forwarder = FastAPIAlertForwarder(
                    endpoint_url=fastapi_alert_endpoint,
                    internal_service_token=internal_service_token,
                )
                alert_publisher = alert_forwarder.publish_alert

            if fastapi_ids_event_endpoint:
                event_forwarder = FastAPIIDSEventForwarder(
                    endpoint_url=fastapi_ids_event_endpoint,
                    internal_service_token=internal_service_token,
                )
                event_publisher = event_forwarder.publish_event

            if fastapi_session_update_endpoint:
                session_update_forwarder = FastAPISessionUpdateForwarder(
                    endpoint_url=fastapi_session_update_endpoint,
                    internal_service_token=internal_service_token,
                )
                session_update_publisher = session_update_forwarder.publish_session_update

            if fastapi_block_event_endpoint:
                block_event_forwarder = FastAPIBlockEventForwarder(
                    endpoint_url=fastapi_block_event_endpoint,
                    internal_service_token=internal_service_token,
                )
                block_event_publisher = block_event_forwarder.publish_block_event

            self.processor = PacketProcessor(
                alert_publisher=alert_publisher,
                event_publisher=event_publisher,
                session_update_publisher=session_update_publisher,
                block_event_publisher=block_event_publisher,
                telemetry_collector=self.telemetry_collector,
            )

        self.sniffer = LiveSniffer(
            self.packet_queue,
            self.interface,
            self.packet_filter,
            telemetry_collector=self.telemetry_collector,
        )

    def _load_project_env(self):
        env_path = Path(".env")
        if not env_path.exists() or not env_path.is_file():
            return

        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key and key not in os.environ:
                os.environ[key] = value

    def start(self):
        sniff_thread = threading.Thread(target=self.sniffer.start, daemon=True)

        sniff_thread.start()

        if self.backend_command_poller is not None:
            command_thread = threading.Thread(
                target=self._poll_backend_commands,
                daemon=True,
            )
            command_thread.start()

        if self.telemetry_forwarder is not None:
            telemetry_thread = threading.Thread(
                target=self._publish_engine_telemetry,
                daemon=True,
            )
            telemetry_thread.start()

        log_event(
            self.logger,
            "info",
            "sniffer service started",
            {
                "event_type": "service_start",
                "interface": self.interface,
                "packet_filter": self.packet_filter,
                "packet_queue_maxsize": self.packet_queue.maxsize,
                "forwarding_enabled": bool(self.fastapi_alert_endpoint),
                "forwarding_endpoint": self.fastapi_alert_endpoint,
                "ids_event_forwarding_enabled": bool(self.fastapi_ids_event_endpoint),
                "ids_event_forwarding_endpoint": self.fastapi_ids_event_endpoint,
                "session_update_forwarding_enabled": bool(self.fastapi_session_update_endpoint),
                "session_update_forwarding_endpoint": self.fastapi_session_update_endpoint,
                "block_event_forwarding_enabled": bool(self.fastapi_block_event_endpoint),
                "block_event_forwarding_endpoint": self.fastapi_block_event_endpoint,
                "engine_telemetry_forwarding_enabled": bool(self.fastapi_engine_telemetry_endpoint),
                "engine_telemetry_forwarding_endpoint": self.fastapi_engine_telemetry_endpoint,
                "engine_telemetry_interval_seconds": self.telemetry_interval_seconds,
                "backend_commands_enabled": bool(self.backend_commands_endpoint),
                "backend_commands_endpoint": self.backend_commands_endpoint,
                "backend_commands_poll_interval_seconds": self.backend_commands_poll_interval_seconds,
            },
        )

        self._consume_packets()

    def _consume_packets(self):
        while True:
            packet = self.packet_queue.get()
            self.processor.process(packet)

    def _publish_engine_telemetry(self):
        while True:
            snapshot = self.telemetry_collector.snapshot(
                packet_queue=self.packet_queue,
                session_builder=self.processor.session_builder,
            )
            ok = self.telemetry_forwarder.publish_telemetry(snapshot)
            if not ok:
                log_event(
                    self.logger,
                    "warning",
                    "engine telemetry forwarding failed",
                    {
                        "event_type": "engine_telemetry_forward_failed",
                        "packets_dropped_total": snapshot.get("packets_dropped_total", 0),
                        "packet_queue_size": snapshot.get("packet_queue_size", 0),
                    },
                )
            elif snapshot.get("packet_loss_detected"):
                log_event(
                    self.logger,
                    "warning",
                    "engine telemetry reports packet loss",
                    {
                        "event_type": "engine_packet_loss_detected",
                        "packets_dropped_total": snapshot.get("packets_dropped_total", 0),
                        "packet_queue_size": snapshot.get("packet_queue_size", 0),
                        "packet_queue_maxsize": snapshot.get("packet_queue_maxsize", 0),
                    },
                )
            time.sleep(self.telemetry_interval_seconds)

    def _poll_backend_commands(self):
        while True:
            commands = self.backend_command_poller.poll_commands()
            for command in commands:
                ok, status = self.processor.apply_backend_command(command)
                if self.backend_commands_ack_endpoint:
                    command_id = str(command.get("command_id", "")).strip()
                    if command_id:
                        self.backend_command_poller.ack_command(
                            ack_endpoint_url=self.backend_commands_ack_endpoint,
                            command_id=command_id,
                            status=status if ok else f"error:{status}",
                        )
            time.sleep(self.backend_commands_poll_interval_seconds)
