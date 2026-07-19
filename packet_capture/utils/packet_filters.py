import ipaddress

from packet_capture.utils.logger import IDSLogger


class PacketFilters:
    @staticmethod
    def basic_filter():
        return "ip"

    @staticmethod
    def tcp_udp_filter():
        return "tcp or udp"

    @staticmethod
    def web_traffic_filter():
        return "(tcp port 80) or (tcp port 443)"

    @staticmethod
    def _valid_ips(ips, *, label):
        valid = []
        for raw in ips or []:
            candidate = raw.strip()
            if not candidate:
                continue
            try:
                ipaddress.ip_address(candidate)
            except ValueError:
                IDSLogger.get_logger("packet.filters").warning("Skipping invalid %s IP: %r", label, raw)
                continue
            valid.append(candidate)
        return valid

    @staticmethod
    def _valid_ports(ports, *, label):
        valid = []
        for raw in ports or []:
            candidate = raw.strip() if isinstance(raw, str) else raw
            if candidate == "" or candidate is None:
                continue
            try:
                parsed = int(candidate)
            except (TypeError, ValueError):
                IDSLogger.get_logger("packet.filters").warning("Skipping invalid %s port: %r", label, raw)
                continue
            if not (0 < parsed <= 65535):
                IDSLogger.get_logger("packet.filters").warning("Skipping out-of-range %s port: %r", label, raw)
                continue
            valid.append(parsed)
        return valid

    @staticmethod
    def build_capture_filter(*, watch_ips=None, watch_ports=None, exclude_ips=None, exclude_ports=None):
        watch_ips = PacketFilters._valid_ips(watch_ips, label="watch")
        watch_ports = PacketFilters._valid_ports(watch_ports, label="watch")
        exclude_ips = PacketFilters._valid_ips(exclude_ips, label="exclude")
        exclude_ports = PacketFilters._valid_ports(exclude_ports, label="exclude")

        clauses = [PacketFilters.basic_filter()]

        watch_terms = [f"host {ip}" for ip in watch_ips] + [f"port {port}" for port in watch_ports]
        if watch_terms:
            clauses.append("(" + " or ".join(watch_terms) + ")")

        exclude_terms = [f"host {ip}" for ip in exclude_ips] + [f"port {port}" for port in exclude_ports]
        if exclude_terms:
            clauses.append("not (" + " or ".join(exclude_terms) + ")")

        return " and ".join(clauses)
