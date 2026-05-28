from traffic_engine.session_builder.session_builder import SessionBuilder
from traffic_engine.session_builder.session_key import SessionKey
from feature_engine.extractors.session_feature_extractor import SessionFeatureExtractor
from feature_engine.feature_store.feature_store import FeatureStore
from threat_detection.heuristic import HeuristicDetector
from ml.runtime.live_predictor import LivePredictor
from ml.runtime.completed_flow_predictor import CompletedFlowPredictor
from response_engine.auto_blocker import AutoBlocker
from response_engine.policy import ResponsePolicy
from packet_capture.utils.logger import IDSLogger, log_event


class PacketProcessor:
    def __init__(self, alert_publisher=None):
        self.heuristic_detector = HeuristicDetector()
        self.session_builder = SessionBuilder()
        self.feature_extractor = SessionFeatureExtractor()
        self.feature_store = FeatureStore()
        self.heuristic_events = FeatureStore(max_size=1000)
        self.ml_events = FeatureStore(max_size=1000)
        self.live_predictor = LivePredictor()
        self.completed_flow_predictor = CompletedFlowPredictor()
        self.alert_store = FeatureStore(max_size=1000)
        self.alert_publisher = alert_publisher
        self.alert_confidence_threshold = 0.80
        self.auto_blocker = AutoBlocker()
        self.response_policy = ResponsePolicy()
        self._session_alert_state = {}
        self.logger = IDSLogger.get_logger("packet.processor")
        self._log_startup_status()

    def _log_startup_status(self):
        firewall_name = "none"
        if self.auto_blocker.firewall is not None:
            firewall_name = self.auto_blocker.firewall.__class__.__name__

        log_event(
            self.logger,
            "info",
            "packet processor startup status",
            {
                "event_type": "processor_startup",
                "live_model_enabled": self.live_predictor.enabled,
                "live_model_path": str(self.live_predictor.model_path),
                "live_encoder_path": str(self.live_predictor.encoder_path),
                "completed_model_enabled": self.completed_flow_predictor.enabled,
                "completed_model_path": str(self.completed_flow_predictor.model_path),
                "completed_encoder_path": str(self.completed_flow_predictor.encoder_path),
                "alert_publisher_enabled": callable(self.alert_publisher),
                "alert_confidence_threshold": self.alert_confidence_threshold,
                "bruteforce_window_seconds": self.response_policy.bruteforce_window_seconds,
                "bruteforce_attempt_threshold": self.response_policy.bruteforce_attempt_threshold,
                "high_heuristic_block_seconds": self.response_policy.high_heuristic_block_seconds,
                "ml_confirmed_block_seconds": self.response_policy.ml_confirmed_block_seconds,
                "firewall_adapter": firewall_name,
            },
        )

    def process(self, packet):
        self.auto_blocker.expire_blocks()

        heuristic_decision = self.heuristic_detector.evaluate_packet(packet)

        brute_force_suspected = self.response_policy.record_bruteforce_attempt(
            src_ip=packet.src_ip,
            dst_ip=packet.dst_ip,
            dst_port=packet.dst_port,
            timestamp=packet.timestamp,
        )

        if heuristic_decision.suspicious:
            heuristic_event = {
                "src_ip": packet.src_ip,
                "dst_ip": packet.dst_ip,
                "src_port": packet.src_port,
                "dst_port": packet.dst_port,
                "protocol": packet.protocol,
                "packet_size": packet.packet_size,
                "timestamp": packet.timestamp,
                "score": heuristic_decision.score,
                "reason": heuristic_decision.reason,
            }
            self.heuristic_events.add(heuristic_event)

            action = self.response_policy.classify_heuristic_action(heuristic_decision.score)
            if action == "high_temp_block":
                blocked, block_status = self.auto_blocker.temp_block(
                    ip_address=packet.src_ip,
                    duration_seconds=self.response_policy.high_heuristic_block_seconds,
                )
                heuristic_alert = {
                    "type": "heuristic_high_confidence",
                    "attack_type": "Heuristic Suspicious Activity",
                    "confidence": min(0.99, heuristic_decision.score / 10.0),
                    "blocked": blocked,
                    "block_status": block_status,
                    "block_duration_seconds": self.response_policy.high_heuristic_block_seconds,
                    "src_ip": packet.src_ip,
                    "dst_ip": packet.dst_ip,
                    "src_port": packet.src_port,
                    "dst_port": packet.dst_port,
                    "protocol": packet.protocol,
                    "timestamp": packet.timestamp,
                }
                self.alert_store.add(heuristic_alert)
                self._publish_alert(heuristic_alert)

        if brute_force_suspected:
            blocked, block_status = self.auto_blocker.temp_block(
                ip_address=packet.src_ip,
                duration_seconds=self.response_policy.bruteforce_block_seconds,
            )
            brute_force_alert = {
                "type": "heuristic_bruteforce_detected",
                "attack_type": "Brute Force",
                "confidence": 0.9,
                "blocked": blocked,
                "block_status": block_status,
                "block_duration_seconds": self.response_policy.bruteforce_block_seconds,
                "src_ip": packet.src_ip,
                "dst_ip": packet.dst_ip,
                "src_port": packet.src_port,
                "dst_port": packet.dst_port,
                "protocol": packet.protocol,
                "timestamp": packet.timestamp,
            }
            self.alert_store.add(brute_force_alert)
            self._publish_alert(brute_force_alert)

        session_key = SessionKey.from_packet(packet)
        session = self.session_builder.process_packet(packet)

        if self.session_builder.should_predict(packet):
            features = self.feature_extractor.extract(session)
            self.feature_store.add(features)

            prediction = self.live_predictor.predict(features)
            if prediction is not None:
                event = {
                    "src_ip": session.src_ip,
                    "dst_ip": session.dst_ip,
                    "src_port": session.src_port,
                    "dst_port": session.dst_port,
                    "protocol": session.protocol,
                    "label": prediction["label"],
                    "confidence": prediction["confidence"],
                    "encoded": prediction["encoded"],
                    "timestamp": session.last_seen,
                }
                self.ml_events.add(event)
                log_event(
                    self.logger,
                    "info",
                    "ml prediction event",
                    {
                        "event_type": "ml_prediction",
                        "src_ip": session.src_ip,
                        "dst_ip": session.dst_ip,
                        "src_port": session.src_port,
                        "dst_port": session.dst_port,
                        "protocol": session.protocol,
                        "attack_type": prediction["label"],
                        "confidence": prediction["confidence"],
                    },
                )

                if self._should_alert(prediction):
                    blocked, block_status = self.auto_blocker.temp_block(
                        ip_address=session.src_ip,
                        duration_seconds=self.response_policy.ml_confirmed_block_seconds,
                    )
                    alert = {
                        "type": "ml_attack_detected",
                        "attack_type": prediction["label"],
                        "confidence": prediction["confidence"],
                        "blocked": blocked,
                        "block_status": block_status,
                        "block_duration_seconds": self.response_policy.ml_confirmed_block_seconds,
                        "src_ip": session.src_ip,
                        "dst_ip": session.dst_ip,
                        "src_port": session.src_port,
                        "dst_port": session.dst_port,
                        "protocol": session.protocol,
                        "timestamp": session.last_seen,
                    }
                    self._emit_session_alert(session_key, alert)

        finalized = self.session_builder.finalize_session_if_needed(packet)
        if finalized is not None:
            final_session = finalized["session"]
            final_key = finalized["session_key"]
            final_features = self.feature_extractor.extract(final_session)
            final_prediction = self.completed_flow_predictor.predict(final_features)

            if final_prediction is not None and self._should_alert(final_prediction):
                blocked, block_status = self.auto_blocker.temp_block(
                    ip_address=final_session.src_ip,
                    duration_seconds=self.response_policy.ml_confirmed_block_seconds,
                )
                final_alert = {
                    "type": "ml_completed_flow_update",
                    "attack_type": final_prediction["label"],
                    "confidence": final_prediction["confidence"],
                    "blocked": blocked,
                    "block_status": block_status,
                    "block_duration_seconds": self.response_policy.ml_confirmed_block_seconds,
                    "src_ip": final_session.src_ip,
                    "dst_ip": final_session.dst_ip,
                    "src_port": final_session.src_port,
                    "dst_port": final_session.dst_port,
                    "protocol": final_session.protocol,
                    "timestamp": final_session.last_seen,
                    "is_final": True,
                }
                self._emit_session_alert(final_key, final_alert, is_final=True)

    def _should_alert(self, prediction: dict) -> bool:
        if prediction["label"] == "Normal Traffic":
            return False

        return float(prediction["confidence"]) >= self.alert_confidence_threshold

    def _publish_alert(self, alert: dict):
        if not callable(self.alert_publisher):
            return

        try:
            self.alert_publisher(alert)
        except Exception:
            pass

    def _session_key_str(self, session_key: SessionKey) -> str:
        return (
            f"{session_key.src_ip}:{session_key.src_port}-"
            f"{session_key.dst_ip}:{session_key.dst_port}-"
            f"{session_key.protocol}"
        )

    def _emit_session_alert(self, session_key: SessionKey, alert: dict, is_final: bool = False):
        key = self._session_key_str(session_key)
        previous = self._session_alert_state.get(key)
        signature = (alert.get("attack_type"), round(float(alert.get("confidence", 0.0)), 4), bool(alert.get("blocked")))

        if previous is not None and previous.get("signature") == signature and not is_final:
            return

        update_type = "new"
        if previous is not None:
            update_type = "updated"
        if is_final:
            update_type = "final"

        alert["session_id"] = key
        alert["update_type"] = update_type

        self._session_alert_state[key] = {"signature": signature, "last_alert": alert}
        self.alert_store.add(alert)
        log_event(
            self.logger,
            "info",
            "alert emitted",
            {
                "event_type": "alert",
                "update_type": update_type,
                "session_id": key,
                "attack_type": alert.get("attack_type"),
                "confidence": alert.get("confidence"),
                "blocked": alert.get("blocked"),
                "block_status": alert.get("block_status"),
                "src_ip": alert.get("src_ip"),
                "dst_ip": alert.get("dst_ip"),
            },
        )
        self._publish_alert(alert)

        if is_final:
            self._session_alert_state.pop(key, None)
