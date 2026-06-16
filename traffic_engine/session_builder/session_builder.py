from traffic_engine.session_builder.session_key import SessionKey
from traffic_engine.session_builder.traffic_session import TrafficSession


class SessionBuilder:
    IDLE_TIMEOUT_SECONDS = 30
    MAX_SESSION_DURATION_SECONDS = 120
    MIN_PREDICTION_AGE_SECONDS = 1
    MIN_PREDICTION_PACKET_COUNT = 5
    PREDICT_EVERY_N_PACKETS = 5
    PREDICT_EVERY_M_SECONDS = 1

    def __init__(self):
        self.sessions = {}
        self._prediction_state = {}
        self._pending_finalizations = []

    def process_packet(self, packet):
        self._expire_stale_sessions(packet.timestamp)

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
            self._prediction_state[session_key] = {
                "last_prediction_packet_count": 0,
                "last_prediction_time": packet.timestamp,
            }

        session = self.sessions[session_key]
        session.update(packet)

        if session.is_finished():
            self._mark_session_for_final_prediction(session_key)

        return session

    def get_all_sessions(self):
        return list(self.sessions.values())

    def should_predict(self, packet) -> bool:
        session_key = SessionKey.from_packet(packet)
        session = self.sessions.get(session_key)

        if session is None:
            return False

        state = self._prediction_state.get(session_key)
        if state is None:
            return False

        age_trigger = session.age() >= self.MIN_PREDICTION_AGE_SECONDS
        packet_trigger = session.packet_count >= self.MIN_PREDICTION_PACKET_COUNT

        packets_since_last = (
            session.packet_count - state["last_prediction_packet_count"]
        )
        periodic_packet_trigger = packets_since_last >= self.PREDICT_EVERY_N_PACKETS

        time_since_last = session.last_seen - state["last_prediction_time"]
        periodic_time_trigger = time_since_last >= self.PREDICT_EVERY_M_SECONDS

        end_trigger = session.is_finished()

        minimum_ready = age_trigger and packet_trigger
        first_ready_prediction = (
            minimum_ready and state["last_prediction_packet_count"] == 0
        )
        periodic_prediction = (
            minimum_ready and (periodic_packet_trigger or periodic_time_trigger)
        )

        should_predict_now = (
            first_ready_prediction
            or periodic_prediction
            or end_trigger
        )

        if should_predict_now:
            state["last_prediction_packet_count"] = session.packet_count
            state["last_prediction_time"] = session.last_seen

        return should_predict_now

    def finalize_session_if_needed(self, packet):
        session_key = SessionKey.from_packet(packet)
        session = self.sessions.get(session_key)

        if session is None:
            return None

        if session.is_finished():
            self._prediction_state.pop(session_key, None)
            finalized = self.sessions.pop(session_key, None)
            if finalized is None:
                return None
            return {
                "session": finalized,
                "session_key": session_key,
                "reason": "flow_end",
            }

        return None

    def _expire_stale_sessions(self, now_timestamp: float):
        stale_items = []

        for key, session in self.sessions.items():
            idle_seconds = now_timestamp - session.last_seen
            duration_seconds = now_timestamp - session.start_time

            if idle_seconds >= self.IDLE_TIMEOUT_SECONDS:
                stale_items.append((key, "idle_timeout"))
                continue

            if duration_seconds >= self.MAX_SESSION_DURATION_SECONDS:
                stale_items.append((key, "max_duration"))

        for key, reason in stale_items:
            stale_session = self.sessions.pop(key, None)
            self._prediction_state.pop(key, None)
            if stale_session is None:
                continue
            self._pending_finalizations.append(
                {
                    "session": stale_session,
                    "session_key": key,
                    "reason": reason,
                }
            )

    def drain_finalized_sessions(self):
        finalized = list(self._pending_finalizations)
        self._pending_finalizations.clear()
        return finalized

    def _mark_session_for_final_prediction(self, session_key):
        state = self._prediction_state.get(session_key)
        if state is None:
            return

        state["last_prediction_packet_count"] = 0
