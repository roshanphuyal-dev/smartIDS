from dataclasses import dataclass


@dataclass
class TrafficSession:
    src_ip: str
    dst_ip: str
    protocol: str
    start_time: float
    last_seen: float

    src_port: int | None = None
    dst_port: int | None = None

    packet_count: int = 0
    total_bytes: int = 0

    def update(self, packet):
        self.packet_count += 1
        self.total_bytes += packet.packet_size
        self.last_seen = packet.timestamp

    def duration(self):
        return self.last_seen - self.start_time

    def average_packet_size(self):
        if self.packet_count == 0:
            return 0

        return self.total_bytes / self.packet_count
