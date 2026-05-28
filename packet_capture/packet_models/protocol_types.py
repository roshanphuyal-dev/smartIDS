from enum import Enum


class ProtocolType(Enum):
    TCP = 6
    UDP = 17
    ICMP = 1
    UNKNOWN = 0
