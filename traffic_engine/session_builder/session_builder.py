from traffic_engine.session_builder.session_key import SessionKey
from traffic_engine.session_builder.traffic_session import TrafficSession


class SessionBuilder:
    def __init__(self):
        self.sessions = {}

    def process_packet(self, packet):
        session_key = SessionKey.from_packet(packet)

        if session_key not in self.sessions:
            self.sessions[session_key] = TrafficSession(
                src_ip=packet.src_ip,
                dst_ip=packet.dst_ip,
                protocol=packet.protocol,
                src_port=packet.src_port,
                dst_port=packet.dst_port,
                start_time=packet.timestamp,
                last_seen=packet.timestamp,
            )

        session = self.sessions[session_key]
        session.update(packet)

        return session

    def get_all_sessions(self):
        return list(self.sessions.values())
