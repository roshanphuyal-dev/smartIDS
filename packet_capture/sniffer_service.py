import threading
import os
from queue import Queue
from pathlib import Path

from packet_capture.sniffers.live_sniffer import LiveSniffer
from packet_capture.sniffers.interface_manager import InterfaceManager
from packet_capture.utils.packet_filters import PacketFilters
from packet_capture.processor.packet_processor import PacketProcessor  # type: ignore
from packet_capture.forwarding.fastapi_alert_forwarder import FastAPIAlertForwarder
from packet_capture.utils.logger import IDSLogger, log_event


class SnifferService:

    def __init__(self, interface=None, packet_filter=None, processor=None):
        self._load_project_env()
        self.logger = IDSLogger.get_logger("sniffer.service")

        self.interface = interface or InterfaceManager.get_default_interface()
        self.packet_queue = Queue(maxsize=10000)
        self.packet_filter = packet_filter or PacketFilters.basic_filter()

        fastapi_alert_endpoint = os.getenv("SMARTIDS_ALERT_ENDPOINT", "").strip()
        self.fastapi_alert_endpoint = fastapi_alert_endpoint
        if processor is not None:
            self.processor = processor
        elif fastapi_alert_endpoint:
            forwarder = FastAPIAlertForwarder(endpoint_url=fastapi_alert_endpoint)
            self.processor = PacketProcessor(alert_publisher=forwarder.publish_alert)
        else:
            self.processor = PacketProcessor()

        self.sniffer = LiveSniffer(
            self.packet_queue, self.interface, self.packet_filter
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
            },
        )

        self._consume_packets()

    def _consume_packets(self):
        while True:
            packet = self.packet_queue.get()
            self.processor.process(packet)
