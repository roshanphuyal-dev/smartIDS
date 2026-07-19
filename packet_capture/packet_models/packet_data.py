from dataclasses import dataclass
from typing import Optional


@dataclass
class PacketData:
    src_ip: str
    dst_ip: str
    protocol: int
    packet_size: int
    timestamp: float

    src_port: Optional[int] = None
    dst_port: Optional[int] = None
    tcp_flags: Optional[int] = None
    tcp_window_size: Optional[int] = None
    tcp_header_length: Optional[int] = None
    transport_header_length: Optional[int] = None
    payload_size: Optional[int] = None
