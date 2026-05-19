import threading
from queue import Queue

from packet_capture.sniffers.live_sniffer import LiveSniffer
from packet_capture.sniffers.interface_manager import InterfaceManager
from packet_capture.utils.packet_filters import PacketFilters
from packet_capture.processors.packet_processor import PacketProcessor


class SnifferService:

    def __init__(self, interface=None, packet_filter=None, processor=None):
        self.interface = interface or InterfaceManager.get_default_interface()
        self.packet_queue = Queue()
        self.packet_filter = packet_filter or PacketFilters.basic_filter()
        self.processor = processor or PacketProcessor()
        self.sniffer = LiveSniffer(
            self.packet_queue, self.interface, self.packet_filter
        )

    def start(self):
        sniff_thread = threading.Thread(target=self.sniffer.start, daemon=True)

        sniff_thread.start()

        print("Sniffer Service started... ... ... .. .")

        self._consume_packets()

    def _consume_packets(self):
        while True:
            packet = self.packet_queue.get()
            self.processor.process(packet)
