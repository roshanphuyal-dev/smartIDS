from dataclasses import dataclass
from typing import Optional


@dataclass
class PacketData:
    src_ip: str
    dst_ip: str
    protocol: str
    packet_size: int
    timestamp: float

    src_port: Optional[int] = None
    dst_port: Optional[int] = None
