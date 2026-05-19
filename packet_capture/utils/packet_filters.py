class PacketFilters:
    @staticmethod
    def basic_filter():
        return "ip"

    @staticmethod
    def tcp_udp_filter():
        return "tcp or udp"

    @staticmethod
    def web_traffic_filter():
        return "TCP port 80 or tcp port 443"
