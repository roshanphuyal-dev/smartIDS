import os
from queue import Queue
from scapy.all import sniff  # type: ignore

from packet_capture.parsers.packet_parser import PacketParser  # type: ignore
from queue import Full
from packet_capture.utils.logger import IDSLogger, log_event


class LiveSniffer:
    def __init__(self, packet_queue: Queue, interface, packet_filter, telemetry_collector=None):
        self.packet_queue = packet_queue
        self.parser = PacketParser()
        self.interface = interface
        self.packet_filter = packet_filter
        self.telemetry_collector = telemetry_collector
        self.logger = IDSLogger.get_logger("sniffer.capture")
        self.capture_health_logging_enabled = os.getenv("SMARTIDS_CAPTURE_HEALTH_LOG", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.capture_health_log_interval = max(
            1,
            int(os.getenv("SMARTIDS_CAPTURE_HEALTH_LOG_INTERVAL", "25")),
        )
        self._seen_packets = 0

    def start(self):
        sniff(
            iface=self.interface,
            prn=self._handle_packet,
            store=False,
            filter=self.packet_filter,
        )

    def _handle_packet(self, packet):
        parsed_packet = self.parser.parse(packet)

        if parsed_packet is not None:
            self._seen_packets += 1
            if self.telemetry_collector is not None:
                self.telemetry_collector.record_packet_received()
            try:
                self.packet_queue.put_nowait(parsed_packet)
                if self.capture_health_logging_enabled and self._seen_packets % self.capture_health_log_interval == 0:
                    log_event(
                        self.logger,
                        "info",
                        "packet capture health",
                        {
                            "event_type": "packet_capture_health",
                            "seen_packets": self._seen_packets,
                            "packet_queue_size": self.packet_queue.qsize(),
                            "src_ip": parsed_packet.src_ip,
                            "dst_ip": parsed_packet.dst_ip,
                            "protocol": parsed_packet.protocol,
                            "src_port": parsed_packet.src_port,
                            "dst_port": parsed_packet.dst_port,
                        },
                    )
            except Full:
                if self.telemetry_collector is not None:
                    self.telemetry_collector.record_packet_dropped()


# Later need to work on packet prioritization, adaptive sampling, dynamic queue sizing, flow-aware dropping, multiprocessing consumers
