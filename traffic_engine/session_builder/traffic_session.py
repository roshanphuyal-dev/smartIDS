from dataclasses import dataclass, field

from traffic_engine.session_builder.running_stats import RunningStats


@dataclass
class TrafficSession:
    src_ip: str
    dst_ip: str
    protocol: int
    start_time: float
    last_seen: float

    src_port: int | None = None
    dst_port: int | None = None

    packet_count: int = 0
    total_bytes: int = 0

    packet_lengths: list[int] = field(default_factory=list)
    fwd_packet_lengths: list[int] = field(default_factory=list)
    packet_timestamps: list[float] = field(default_factory=list)
    fwd_packet_timestamps: list[float] = field(default_factory=list)

    # Incremental (Welford) mirrors of packet_lengths / fwd_packet_lengths above.
    # Kept alongside the raw lists (not replacing them yet) so both computation
    # paths can be validated against each other before any cutover.
    packet_length_stats: RunningStats = field(default_factory=RunningStats)
    fwd_packet_length_stats: RunningStats = field(default_factory=RunningStats)

    fwd_packet_count: int = 0
    fwd_total_bytes: int = 0

    flag_counts: dict[str, int] = field(
        default_factory=lambda: {
            "fin": 0,
            "syn": 0,
            "rst": 0,
            "psh": 0,
            "ack": 0,
            "urg": 0,
        }
    )

    fwd_header_length: int = 0
    init_win_bytes_forward: int | None = None
    act_data_pkt_fwd: int = 0
    min_seg_size_forward: int | None = None

    finished: bool = False

    def update(self, packet):
        self.packet_count += 1
        self.total_bytes += packet.packet_size
        self.last_seen = packet.timestamp

        self.packet_lengths.append(packet.packet_size)
        self.packet_timestamps.append(packet.timestamp)
        self.packet_length_stats.update(packet.packet_size)

        is_forward = packet.src_ip == self.src_ip and packet.dst_ip == self.dst_ip

        if is_forward:
            self.fwd_packet_count += 1
            self.fwd_total_bytes += packet.packet_size
            self.fwd_packet_lengths.append(packet.packet_size)
            self.fwd_packet_timestamps.append(packet.timestamp)
            self.fwd_packet_length_stats.update(packet.packet_size)

            header_len = packet.transport_header_length
            if header_len is not None:
                self.fwd_header_length += int(header_len)

            if self.init_win_bytes_forward is None and packet.tcp_window_size is not None:
                self.init_win_bytes_forward = int(packet.tcp_window_size)

            if packet.payload_size is not None and int(packet.payload_size) > 0:
                self.act_data_pkt_fwd += 1

            segment_size = packet.payload_size
            if segment_size is not None:
                segment_size = int(segment_size)
                if segment_size > 0:
                    if self.min_seg_size_forward is None:
                        self.min_seg_size_forward = segment_size
                    else:
                        self.min_seg_size_forward = min(self.min_seg_size_forward, segment_size)

        self._update_tcp_flags(packet)

    def _update_tcp_flags(self, packet):
        if packet.tcp_flags is None:
            return

        flags = int(packet.tcp_flags)

        if flags & 0x01:
            self.flag_counts["fin"] += 1
            self.finished = True
        if flags & 0x02:
            self.flag_counts["syn"] += 1
        if flags & 0x04:
            self.flag_counts["rst"] += 1
            self.finished = True
        if flags & 0x08:
            self.flag_counts["psh"] += 1
        if flags & 0x10:
            self.flag_counts["ack"] += 1
        if flags & 0x20:
            self.flag_counts["urg"] += 1

    def duration(self):
        return max(0.0, self.last_seen - self.start_time)

    def average_packet_size(self):
        if self.packet_count == 0:
            return 0

        return self.total_bytes / self.packet_count

    def age(self):
        return self.duration()

    def is_finished(self):
        return self.finished
