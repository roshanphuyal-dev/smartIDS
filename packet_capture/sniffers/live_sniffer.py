from queue import Queue
from scapy.all import sniff  # type: ignore

from packet_capture.parsers.packet_parser import PacketParser  # type: ignore


class LiveSniffer:
    def __init__(self, packet_queue: Queue, interface, packet_filter):
        self.packet_queue = packet_queue
        self.parser = PacketParser()
        self.interface = interface
        self.packet_filter = packet_filter

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
            self.packet_queue.put(parsed_packet)
