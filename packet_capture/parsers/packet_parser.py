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
        tcp_flags = None
        tcp_window_size = None
        tcp_header_length = None
        transport_header_length = None
        payload_size = 0

        if packet.haslayer(TCP):
            tcp_layer = packet[TCP]
            protocol = ProtocolType.TCP
            src_port = tcp_layer.sport
            dst_port = tcp_layer.dport
            tcp_flags = int(tcp_layer.flags)
            tcp_window_size = int(tcp_layer.window)
            tcp_header_length = int(tcp_layer.dataofs) * 4 if tcp_layer.dataofs is not None else 0
            transport_header_length = tcp_header_length
            payload_size = len(bytes(tcp_layer.payload))

        elif packet.haslayer(UDP):
            udp_layer = packet[UDP]
            protocol = ProtocolType.UDP
            src_port = udp_layer.sport
            dst_port = udp_layer.dport
            transport_header_length = 8
            payload_size = len(bytes(udp_layer.payload))

        elif packet.haslayer(ICMP):
            icmp_layer = packet[ICMP]
            protocol = ProtocolType.ICMP
            transport_header_length = 8
            payload_size = len(bytes(icmp_layer.payload))

        return PacketData(
            src_ip=src_ip,
            dst_ip=dst_ip,
            protocol=protocol.value,
            packet_size=len(packet),
            timestamp=time.time(),
            src_port=src_port,
            dst_port=dst_port,
            tcp_flags=tcp_flags,
            tcp_window_size=tcp_window_size,
            tcp_header_length=tcp_header_length,
            transport_header_length=transport_header_length,
            payload_size=payload_size,
        )
