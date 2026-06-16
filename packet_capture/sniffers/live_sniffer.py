from queue import Queue
from scapy.all import sniff  # type: ignore

from packet_capture.parsers.packet_parser import PacketParser  # type: ignore
from queue import Full


class LiveSniffer:
    def __init__(self, packet_queue: Queue, interface, packet_filter, telemetry_collector=None):
        self.packet_queue = packet_queue
        self.parser = PacketParser()
        self.interface = interface
        self.packet_filter = packet_filter
        self.telemetry_collector = telemetry_collector

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
            if self.telemetry_collector is not None:
                self.telemetry_collector.record_packet_received()
            try:
                self.packet_queue.put_nowait(parsed_packet)
            except Full:
                if self.telemetry_collector is not None:
                    self.telemetry_collector.record_packet_dropped()


# Later need to work on packet prioritization, adaptive sampling, dynamic queue sizing, flow-aware dropping, multiprocessing consumers
