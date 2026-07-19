import os
from dataclasses import dataclass
from collections import deque


@dataclass
class HeuristicDecision:
    suspicious: bool
    reason: str
    score: int


class HeuristicDetector:
    """Early packet-level heuristic detector.

    This runs before flow/session aggregation and before ML inference so
    obvious malicious patterns can be flagged immediately.
    """

    def __init__(self, max_tracked_ips: int | None = None):
        self.enabled = True
        self.burst_window_seconds = 2.0
        self.burst_packet_threshold = 40
        self.port_sweep_window_seconds = 5.0
        self.port_sweep_unique_ports_threshold = 15
        self.syn_window_seconds = 3.0
        self.syn_only_threshold = 20
        self.sensitive_ports = {21, 22, 23, 25, 53, 80, 110, 135, 139, 143, 443, 445, 3389}

        self._src_packet_times = {}
        self._src_recent_dst_ports = {}
        self._src_syn_only_times = {}
        self._last_seen: dict[str, float] = {}
        self.max_tracked_ips = self._positive_int(
            max_tracked_ips,
            env_name="SMARTIDS_HEURISTIC_MAX_TRACKED_IPS",
            default=10000,
        )
        # The full-dict sweep in _prune_tracked_ips is O(N) over every tracked
        # source IP. Running it on every single packet would reintroduce the
        # same per-packet-cost-scales-with-load problem this detector exists
        # to catch (many distinct IPs during a scan/flood). Per-current-IP
        # trimming already happens inline in the _append_* methods below, so
        # the full sweep (idle-IP GC + max_tracked_ips eviction) only needs to
        # run periodically, not every packet.
        self._prune_interval_seconds = self._positive_int(
            None,
            env_name="SMARTIDS_HEURISTIC_PRUNE_INTERVAL_SECONDS",
            default=1,
        )
        self._last_pruned_at: float | None = None

    @staticmethod
    def _positive_int(value: int | None, *, env_name: str, default: int) -> int:
        if value is None:
            value = os.getenv(env_name, str(default))
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(1, parsed)

    def _append_time(self, src_ip: str, timestamp: float):
        packet_times = self._src_packet_times.setdefault(src_ip, deque())
        packet_times.append(timestamp)
        self._last_seen[src_ip] = timestamp

        cutoff = timestamp - self.burst_window_seconds
        while packet_times and packet_times[0] < cutoff:
            packet_times.popleft()

    def _append_dst_port(self, src_ip: str, dst_port, timestamp: float):
        if dst_port is None:
            return

        recent_ports = self._src_recent_dst_ports.setdefault(src_ip, deque())
        recent_ports.append((timestamp, int(dst_port)))
        self._last_seen[src_ip] = timestamp

        cutoff = timestamp - self.port_sweep_window_seconds
        while recent_ports and recent_ports[0][0] < cutoff:
            recent_ports.popleft()

    def _append_syn_only(self, src_ip: str, tcp_flags, timestamp: float):
        if tcp_flags is None:
            return

        flags = int(tcp_flags)
        syn_set = (flags & 0x02) != 0
        ack_set = (flags & 0x10) != 0
        syn_only = syn_set and not ack_set

        if not syn_only:
            return

        syn_times = self._src_syn_only_times.setdefault(src_ip, deque())
        syn_times.append(timestamp)
        self._last_seen[src_ip] = timestamp

        cutoff = timestamp - self.syn_window_seconds
        while syn_times and syn_times[0] < cutoff:
            syn_times.popleft()

    def _prune_tracked_ips(self, now: float) -> None:
        tracked_ips = set(self._src_packet_times) | set(self._src_recent_dst_ports) | set(
            self._src_syn_only_times
        )

        burst_cutoff = now - self.burst_window_seconds
        port_sweep_cutoff = now - self.port_sweep_window_seconds
        syn_cutoff = now - self.syn_window_seconds

        for src_ip in tracked_ips:
            packet_times = self._src_packet_times.get(src_ip)
            if packet_times is not None:
                while packet_times and packet_times[0] < burst_cutoff:
                    packet_times.popleft()

            recent_ports = self._src_recent_dst_ports.get(src_ip)
            if recent_ports is not None:
                while recent_ports and recent_ports[0][0] < port_sweep_cutoff:
                    recent_ports.popleft()

            syn_times = self._src_syn_only_times.get(src_ip)
            if syn_times is not None:
                while syn_times and syn_times[0] < syn_cutoff:
                    syn_times.popleft()

            is_empty = not packet_times and not recent_ports and not syn_times
            if is_empty:
                self._src_packet_times.pop(src_ip, None)
                self._src_recent_dst_ports.pop(src_ip, None)
                self._src_syn_only_times.pop(src_ip, None)
                self._last_seen.pop(src_ip, None)

        tracked_ips = set(self._src_packet_times) | set(self._src_recent_dst_ports) | set(
            self._src_syn_only_times
        )
        overflow = len(tracked_ips) - self.max_tracked_ips
        if overflow <= 0:
            return

        ordered_ips = sorted(
            tracked_ips,
            key=lambda src_ip: self._last_seen.get(src_ip, 0.0),
        )
        for src_ip in ordered_ips[:overflow]:
            self._src_packet_times.pop(src_ip, None)
            self._src_recent_dst_ports.pop(src_ip, None)
            self._src_syn_only_times.pop(src_ip, None)
            self._last_seen.pop(src_ip, None)

    def evaluate_packet(self, packet) -> HeuristicDecision:
        if not self.enabled:
            return HeuristicDecision(False, "disabled", 0)

        score = 0
        reasons = []

        timestamp = float(packet.timestamp)
        src_ip = str(packet.src_ip)

        self._append_time(src_ip, timestamp)
        self._append_dst_port(src_ip, packet.dst_port, timestamp)
        self._append_syn_only(src_ip, packet.tcp_flags, timestamp)

        if (
            self._last_pruned_at is None
            or timestamp - self._last_pruned_at >= self._prune_interval_seconds
        ):
            self._prune_tracked_ips(timestamp)
            self._last_pruned_at = timestamp

        if packet.src_port is None and packet.dst_port is None:
            score += 2
            reasons.append("no_transport_ports")

        if packet.packet_size <= 0:
            score += 3
            reasons.append("invalid_packet_size")

        if packet.packet_size < 40:
            score += 1
            reasons.append("tiny_packet")

        if packet.dst_port is not None and int(packet.dst_port) in self.sensitive_ports:
            score += 1
            reasons.append("sensitive_service_probe")

        packet_times = self._src_packet_times.get(src_ip, deque())
        if len(packet_times) >= self.burst_packet_threshold:
            score += 3
            reasons.append("scan_burst")

        recent_ports = self._src_recent_dst_ports.get(src_ip, deque())
        unique_ports = {port for _, port in recent_ports}
        if len(unique_ports) >= self.port_sweep_unique_ports_threshold:
            score += 3
            reasons.append("port_sweep")

        syn_only_times = self._src_syn_only_times.get(src_ip, deque())
        if len(syn_only_times) >= self.syn_only_threshold:
            score += 4
            reasons.append("syn_only_surge")

        suspicious = score >= 2
        reason_text = ",".join(reasons) if reasons else "clean"

        return HeuristicDecision(
            suspicious=suspicious,
            reason=reason_text,
            score=score,
        )
