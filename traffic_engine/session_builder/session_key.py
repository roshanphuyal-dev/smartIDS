from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SessionKey:
    src_ip: str
    dst_ip: str
    protocol: str
    src_port: Optional[int] = None
    dst_port: Optional[int] = None

    @staticmethod
    def from_packet(packet):
        return SessionKey(
            src_ip=packet.src_ip,
            dst_ip=packet.dst_ip,
            protocol=packet.protocol,
            src_port=packet.src_port,
            dst_port=packet.dst_port,
        )
