import time

from scapy.layers.inet import IP, TCP, UDP, ICMP  # type: ignore

from packet_capture.packet_models.packet_data import PacketData
from packet_capture.packet_models.protocol_types import ProtocolType  # type: ignore


class PacketParser:
    def parse(self, packet):
        if not packet.haslayer(IP):
            return None

        ip_layer = packet[IP]

        src_ip = ip_layer.src
        dst_ip = ip_layer.dst

        protocol = ProtocolType.UNKNOWN
        src_port = None
        dst_port = None

        if packet.haslayer(TCP):
            protocol = ProtocolType.TCP
            src_port = packet[TCP].sport
            dst_port = packet[TCP].dport

        elif packet.haslayer(UDP):
            protocol = ProtocolType.UDP
            src_port = packet[UDP].sport
            dst_port = packet[UDP].dport

        elif packet.haslayer(ICMP):
            protocol = ProtocolType.ICMP

        return PacketData(
            src_ip=src_ip,
            dst_ip=dst_ip,
            protocol=protocol.value,
            packet_size=len(packet),
            timestamp=time.time(),
            src_port=src_port,
            dst_port=dst_port,
        )
