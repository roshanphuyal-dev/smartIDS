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
from packet_capture.forwarding.background_publisher import BackgroundPublisher
from packet_capture.forwarding.disk_spill_store import DiskSpillStore
from packet_capture.realtime.engine_ws_client import EngineWSClient
from packet_capture.telemetry.engine_telemetry import EngineTelemetryCollector
from packet_capture.utils.logger import IDSLogger, log_event
from packet_capture.auth.request_signer import InternalRequestSigner
from packet_capture.registration.local_config import EngineLocalConfig
from packet_capture.registration.capture_config_client import fetch_capture_watch_port
from response_engine.backend_command_poller import BackendCommandPoller


class SnifferService:

    def __init__(self, interface=None, packet_filter=None, processor=None):
        self._load_project_env()
        self.logger = IDSLogger.get_logger("sniffer.service")

        self.capture_interface_override = os.getenv("SMARTIDS_CAPTURE_INTERFACE", "").strip()
        self.interface = interface or InterfaceManager.resolve_interface(self.capture_interface_override)
        self.packet_queue = Queue(maxsize=10000)
        self._explicit_packet_filter = packet_filter

        fastapi_alert_endpoint = os.getenv("SMARTIDS_ALERT_ENDPOINT", "").strip()
        fastapi_ids_event_endpoint = os.getenv("SMARTIDS_IDS_EVENT_ENDPOINT", "").strip()
        fastapi_session_update_endpoint = os.getenv("SMARTIDS_SESSION_UPDATE_ENDPOINT", "").strip()
        fastapi_block_event_endpoint = os.getenv("SMARTIDS_BLOCK_EVENT_ENDPOINT", "").strip()
        fastapi_engine_telemetry_endpoint = os.getenv("SMARTIDS_ENGINE_TELEMETRY_ENDPOINT", "").strip()
        backend_commands_endpoint = os.getenv("SMARTIDS_COMMANDS_ENDPOINT", "").strip()
        backend_commands_ack_endpoint = os.getenv("SMARTIDS_COMMANDS_ACK_ENDPOINT", "").strip()
        internal_service_token = os.getenv("SMARTIDS_INTERNAL_SERVICE_TOKEN", "").strip()
        internal_request_signer = self._resolve_internal_request_signer(internal_service_token)
        self.packet_filter = self._explicit_packet_filter or PacketFilters.build_capture_filter(
            watch_ips=self._csv_env("SMARTIDS_CAPTURE_WATCH_IPS"),
            watch_ports=self._resolve_watch_ports(internal_request_signer),
            exclude_ips=self._csv_env("SMARTIDS_CAPTURE_EXCLUDE_IPS"),
            exclude_ports=self._csv_env("SMARTIDS_CAPTURE_EXCLUDE_PORTS"),
        )
        backend_commands_poll_interval_seconds = float(
            os.getenv("SMARTIDS_COMMANDS_POLL_INTERVAL_SECONDS", "1.5")
        )
        # Workstream 6c: persistent WS push in place of the 1.5s poll above.
        # Default off — when disabled (or misconfigured), behavior is
        # unchanged: the poll loop is the only command delivery path.
        engine_ws_enabled = os.getenv("SMARTIDS_ENGINE_WS_ENABLED", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        engine_ws_url = os.getenv("SMARTIDS_ENGINE_WS_URL", "").strip()
        self.fastapi_alert_endpoint = fastapi_alert_endpoint
        self.fastapi_ids_event_endpoint = fastapi_ids_event_endpoint
        self.fastapi_session_update_endpoint = fastapi_session_update_endpoint
        self.fastapi_block_event_endpoint = fastapi_block_event_endpoint
        self.fastapi_engine_telemetry_endpoint = fastapi_engine_telemetry_endpoint
        self.backend_commands_endpoint = backend_commands_endpoint
        self.backend_commands_ack_endpoint = backend_commands_ack_endpoint
        self.backend_commands_poll_interval_seconds = max(0.5, backend_commands_poll_interval_seconds)
        self.backend_command_poller = None
        self.engine_ws_enabled = engine_ws_enabled
        self.engine_ws_url = engine_ws_url
        self.engine_ws_client = None
        self.telemetry_collector = EngineTelemetryCollector()
        self.telemetry_forwarder = None
        self.telemetry_interval_seconds = max(
            5.0,
            float(os.getenv("SMARTIDS_ENGINE_TELEMETRY_INTERVAL_SECONDS", "30")),
        )
        self.capture_health_logging_enabled = os.getenv("SMARTIDS_CAPTURE_HEALTH_LOG", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.forwarder_queue_size = max(
            32,
            int(os.getenv("SMARTIDS_FORWARDER_QUEUE_SIZE", "1024")),
        )
        self.forwarder_drop_log_every = max(
            1,
            int(os.getenv("SMARTIDS_FORWARDER_DROP_LOG_EVERY", "25")),
        )
        # Phase 3: local event buffering when the backend is unreachable.
        # Default off -- when disabled, BackgroundPublisher gets no
        # spill_store and behavior is byte-for-byte unchanged from today
        # (failed publishes are still discarded, not durably buffered).
        self.disk_spill_enabled = os.getenv("SMARTIDS_DISK_SPILL_ENABLED", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.disk_spill_max_entries = max(
            1,
            int(os.getenv("SMARTIDS_DISK_SPILL_MAX_ENTRIES", "2000")),
        )
        if fastapi_engine_telemetry_endpoint:
            self.telemetry_forwarder = FastAPIEngineTelemetryForwarder(
                endpoint_url=fastapi_engine_telemetry_endpoint,
                signer=internal_request_signer,
            )
        if backend_commands_endpoint:
            self.backend_command_poller = BackendCommandPoller(
                endpoint_url=backend_commands_endpoint,
                signer=internal_request_signer,
            )
        if self.engine_ws_enabled:
            if engine_ws_url and internal_request_signer is not None and self.backend_command_poller is not None:
                self.engine_ws_client = EngineWSClient(
                    ws_url=engine_ws_url,
                    signer=internal_request_signer,
                    apply_command=lambda command: self.processor.apply_backend_command(command),
                    catchup_poller=self.backend_command_poller,
                    catchup_ack_endpoint_url=backend_commands_ack_endpoint or None,
                )
            else:
                log_event(
                    self.logger,
                    "warning",
                    "engine ws enabled but misconfigured, falling back to command poll loop",
                    {
                        "event_type": "engine_ws_misconfigured",
                        "engine_ws_url_set": bool(engine_ws_url),
                        "internal_request_signer_set": internal_request_signer is not None,
                        "backend_commands_endpoint_set": bool(backend_commands_endpoint),
                    },
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
                    signer=internal_request_signer,
                )
                alert_publisher = self._build_background_publisher(
                    name="alerts",
                    publish=alert_forwarder.publish_alert,
                )

            if fastapi_ids_event_endpoint:
                event_forwarder = FastAPIIDSEventForwarder(
                    endpoint_url=fastapi_ids_event_endpoint,
                    signer=internal_request_signer,
                )
                event_publisher = self._build_background_publisher(
                    name="ids-events",
                    publish=event_forwarder.publish_event,
                )

            if fastapi_session_update_endpoint:
                session_update_forwarder = FastAPISessionUpdateForwarder(
                    endpoint_url=fastapi_session_update_endpoint,
                    signer=internal_request_signer,
                )
                session_update_publisher = self._build_background_publisher(
                    name="session-updates",
                    publish=session_update_forwarder.publish_session_update,
                )

            if fastapi_block_event_endpoint:
                block_event_forwarder = FastAPIBlockEventForwarder(
                    endpoint_url=fastapi_block_event_endpoint,
                    signer=internal_request_signer,
                )
                block_event_publisher = self._build_background_publisher(
                    name="block-events",
                    publish=block_event_forwarder.publish_block_event,
                )

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

    @staticmethod
    def _csv_env(env_name):
        raw = os.getenv(env_name, "").strip()
        if not raw:
            return None
        return [item.strip() for item in raw.split(",") if item.strip()]

    def _resolve_watch_ports(self, internal_request_signer):
        """Ports to watch: the local ``SMARTIDS_CAPTURE_WATCH_PORTS`` env var,
        plus (if this engine is browser-registered) whatever port is set on
        its dashboard capture config. Best-effort — a missing local config or
        an unreachable backend just means no remote port is added, same as
        today's env-var-only behavior.
        """
        watch_ports = self._csv_env("SMARTIDS_CAPTURE_WATCH_PORTS") or []

        local_engine_config = EngineLocalConfig().load()
        if local_engine_config and internal_request_signer is not None:
            remote_port = fetch_capture_watch_port(
                local_engine_config["backend_url"], internal_request_signer
            )
            if remote_port is not None:
                watch_ports = watch_ports + [str(remote_port)]

        return watch_ports or None

    def _resolve_internal_request_signer(self, internal_service_token: str):
        """Chooses the engine's internal-auth signer, in priority order:

        1. A previously saved local engine config (browser-registered
           credential) -- attaches ``x-smartids-engine-id`` alongside the
           HMAC signature on every request.
        2. ``SMARTIDS_INTERNAL_SERVICE_TOKEN`` (today's global-token path,
           unchanged) -- no engine id attached.
        3. ``SMARTIDS_ENGINE_REGISTRATION_ENABLED=true`` -- kicks off the
           browser registration flow (blocking, bounded by its own
           timeout); on success behaves like (1), on failure/timeout falls
           through to no signer.
        4. Otherwise: no signer (today's existing fallback).

        Purely additive: when there's no local config and the registration
        flag is unset (the default), this is byte-for-byte the same as the
        old ``InternalRequestSigner(internal_service_token) if
        internal_service_token else None`` inline logic.
        """
        local_engine_config = EngineLocalConfig().load()
        if local_engine_config:
            log_event(
                self.logger,
                "info",
                "using locally registered engine credential for internal auth",
                {
                    "event_type": "engine_auth_mode_local_config",
                    "engine_id": local_engine_config.get("engine_id"),
                },
            )
            return InternalRequestSigner(
                local_engine_config["engine_secret"],
                engine_id=local_engine_config.get("engine_id"),
            )

        if internal_service_token:
            return InternalRequestSigner(internal_service_token)

        engine_registration_enabled = os.getenv(
            "SMARTIDS_ENGINE_REGISTRATION_ENABLED", ""
        ).strip().lower() in {"1", "true", "yes", "on"}
        if not engine_registration_enabled:
            return None

        from packet_capture.registration.registration_client import run_registration

        log_event(
            self.logger,
            "info",
            "no local engine config or internal service token, starting browser registration",
            {"event_type": "engine_registration_starting"},
        )
        registered_config = run_registration()
        if not registered_config:
            log_event(
                self.logger,
                "warning",
                "engine registration did not complete, continuing without internal auth signer",
                {"event_type": "engine_registration_not_completed"},
            )
            return None

        return InternalRequestSigner(
            registered_config["engine_secret"],
            engine_id=registered_config.get("engine_id"),
        )

    def start(self):
        sniff_thread = threading.Thread(target=self.sniffer.start, daemon=True)

        sniff_thread.start()

        if self.engine_ws_client is not None:
            # WS push replaces the poll loop; the WS client still does one
            # catch-up GET /engine-commands per (re)connect internally, so
            # the durable queue keeps being drained even though this thread
            # never starts.
            self.engine_ws_client.start()
        elif self.backend_command_poller is not None:
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
                "capture_interface_override": self.capture_interface_override or None,
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
                "forwarder_queue_size": self.forwarder_queue_size,
                "forwarder_drop_log_every": self.forwarder_drop_log_every,
                "capture_health_logging_enabled": self.capture_health_logging_enabled,
                "disk_spill_enabled": self.disk_spill_enabled,
                "disk_spill_max_entries": self.disk_spill_max_entries,
                "backend_commands_enabled": bool(self.backend_commands_endpoint),
                "backend_commands_endpoint": self.backend_commands_endpoint,
                "backend_commands_poll_interval_seconds": self.backend_commands_poll_interval_seconds,
                "engine_ws_enabled": self.engine_ws_enabled,
                "engine_ws_active": self.engine_ws_client is not None,
                "engine_ws_url": self.engine_ws_url,
                "command_delivery_mode": "websocket" if self.engine_ws_client is not None else "poll",
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
            telemetry_extras = getattr(self.processor, "telemetry_extras", None)
            if callable(telemetry_extras):
                snapshot.update(telemetry_extras())
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

    def _build_background_publisher(self, *, name: str, publish):
        spill_store = None
        if self.disk_spill_enabled:
            spill_store = DiskSpillStore(
                file_path=f"logs/spill_{name}.jsonl",
                max_entries=self.disk_spill_max_entries,
            )
        dispatcher = BackgroundPublisher(
            name=name,
            publish=publish,
            max_queue_size=self.forwarder_queue_size,
            drop_log_every=self.forwarder_drop_log_every,
            spill_store=spill_store,
        )
        return dispatcher.submit
