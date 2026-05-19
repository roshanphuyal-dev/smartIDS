from enum import Enum


class ProtocolType(Enum):
    TCP = "TCP"
    UDP = "UDP"
    ICMP = "ICMP"
    UNKNOWN = "UNKNOWN"
