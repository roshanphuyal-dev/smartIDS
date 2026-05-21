class SessionFeatureExtractor:

    def extract(self, session):
        duration = session.duration()

        if duration <= 0:
            packet_rate = 0
            byte_rate = 0

        else:
            packet_rate = session.packet_count / duration
            byte_rate = session.total_bytes / duration

        return {
            "protocol": session.protocol,
            "packet_count": session.packet_count,
            "total_bytes": session.total_bytes,
            "duration": duration,
            "avg_packet_size": session.average_packet_size(),
            "packet_rate": packet_rate,
            "byte_rate": byte_rate,
            "src_port": session.src_port,
            "dst_port": session.dst_port,
        }
