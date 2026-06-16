from datetime import datetime, timezone
import hashlib
import time

from traffic_engine.session_builder.session_builder import SessionBuilder
from traffic_engine.session_builder.session_key import SessionKey
from feature_engine.extractors.session_feature_extractor import SessionFeatureExtractor
from feature_engine.feature_store.feature_store import FeatureStore
from threat_detection.heuristic import HeuristicDetector
from ml.runtime.live_predictor import LivePredictor
from ml.runtime.completed_flow_predictor import CompletedFlowPredictor
from response_engine.auto_blocker import AutoBlocker
from response_engine.processed_command_store import ProcessedCommandStore
from response_engine.policy import ResponsePolicy
from packet_capture.forwarding.contracts import build_ids_event_payload, build_session_upsert_payload
from packet_capture.utils.logger import IDSLogger, log_event


class PacketProcessor:
    def __init__(
        self,
        alert_publisher=None,
        event_publisher=None,
        session_update_publisher=None,
        block_event_publisher=None,
        telemetry_collector=None,
    ):
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
        self.event_publisher = event_publisher
        self.session_update_publisher = session_update_publisher
        self.block_event_publisher = block_event_publisher
        self.telemetry_collector = telemetry_collector
        self.alert_confidence_threshold = 0.80
        self.auto_blocker = AutoBlocker()
        self.response_policy = ResponsePolicy()
        self._session_alert_state = {}
        self.processed_command_store = ProcessedCommandStore()
        self.logger = IDSLogger.get_logger("packet.processor")
        self._log_startup_status()

    def apply_backend_command(self, command: dict) -> tuple[bool, str]:
        command_id = str(command.get("command_id", "")).strip()
        action = str(command.get("action", "")).strip().lower()
        ip_address = str(command.get("ip_address", "")).strip()
        duration_seconds = int(command.get("duration_seconds", 300) or 300)

        if not action or not ip_address:
            return False, "invalid_command"

        if command_id and self.processed_command_store.contains(command_id):
            return True, "duplicate_command"

        if action == "block":
            ok, status = self.auto_blocker.manual_block(
                ip_address=ip_address,
                duration_seconds=max(1, duration_seconds),
            )
        elif action == "unblock":
            ok, status = self.auto_blocker.manual_unblock(ip_address=ip_address)
        elif action == "watchlist":
            ok, status = self.auto_blocker.watchlist_ip(ip_address=ip_address)
        elif action == "unwatchlist":
            ok, status = self.auto_blocker.unwatchlist_ip(ip_address=ip_address)
        else:
            return False, "unsupported_action"

        if ok and command_id:
            self.processed_command_store.add(command_id)

        if ok:
            mapped_action = "blocked"
            if action == "unblock":
                mapped_action = "unblocked"
            elif action == "watchlist":
                mapped_action = "watchlisted"
            elif action == "unwatchlist":
                mapped_action = "unwatchlisted"

            self._publish_block_event(
                event_id=f"cmd-{command_id}" if command_id else f"cmd-{ip_address}-{action}",
                source_ip=ip_address,
                action_taken=mapped_action,
                reason=f"manual_{action}",
                detection_method="manual",
                session_id=None,
                source_port=None,
                destination_ip=None,
                destination_port=None,
                protocol=None,
                timestamp=time.time(),
            )

        return ok, status

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
                "live_model_error": self.live_predictor.artifact_error,
                "completed_model_enabled": self.completed_flow_predictor.enabled,
                "completed_model_path": str(self.completed_flow_predictor.model_path),
                "completed_encoder_path": str(self.completed_flow_predictor.encoder_path),
                "completed_model_error": self.completed_flow_predictor.artifact_error,
                "alert_publisher_enabled": callable(self.alert_publisher),
                "event_publisher_enabled": callable(self.event_publisher),
                "session_update_publisher_enabled": callable(self.session_update_publisher),
                "block_event_publisher_enabled": callable(self.block_event_publisher),
                "alert_confidence_threshold": self.alert_confidence_threshold,
                "bruteforce_window_seconds": self.response_policy.bruteforce_window_seconds,
                "bruteforce_attempt_threshold": self.response_policy.bruteforce_attempt_threshold,
                "high_heuristic_block_seconds": self.response_policy.high_heuristic_block_seconds,
                "ml_confirmed_block_seconds": self.response_policy.ml_confirmed_block_seconds,
                "firewall_adapter": firewall_name,
            },
        )

    def process(self, packet):
        if self.telemetry_collector is not None:
            self.telemetry_collector.record_packet_processed()

        self.auto_blocker.expire_blocks()

        if self.auto_blocker.is_currently_blocked(packet.src_ip):
            self.auto_blocker.record_detection_activity(
                ip_address=packet.src_ip,
                attack_type="blocked_ip_activity",
                action="blocked",
                timestamp=packet.timestamp,
            )

        if self.auto_blocker.is_watchlisted(packet.src_ip):
            self.auto_blocker.record_detection_activity(
                ip_address=packet.src_ip,
                attack_type="watchlisted_ip_activity",
                action="watchlisted",
                timestamp=packet.timestamp,
            )

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
            self.auto_blocker.record_detection_activity(
                ip_address=packet.src_ip,
                attack_type=heuristic_decision.reason,
                action="allowed",
                timestamp=packet.timestamp,
            )

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
                if blocked:
                    self._publish_block_event(
                        event_id=f"heuristic-{packet.src_ip}-{int(packet.timestamp * 1000)}",
                        source_ip=packet.src_ip,
                        action_taken="blocked",
                        reason="heuristic_high_confidence",
                        detection_method="heuristic",
                        session_id=(
                            f"{packet.src_ip}:{packet.src_port}-"
                            f"{packet.dst_ip}:{packet.dst_port}-"
                            f"{packet.protocol}"
                        ),
                        source_port=packet.src_port,
                        destination_ip=packet.dst_ip,
                        destination_port=packet.dst_port,
                        protocol=packet.protocol,
                        timestamp=packet.timestamp,
                    )

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
            if blocked:
                self._publish_block_event(
                    event_id=f"bruteforce-{packet.src_ip}-{int(packet.timestamp * 1000)}",
                    source_ip=packet.src_ip,
                    action_taken="blocked",
                    reason="bruteforce_detected",
                    detection_method="heuristic",
                    session_id=(
                        f"{packet.src_ip}:{packet.src_port}-"
                        f"{packet.dst_ip}:{packet.dst_port}-"
                        f"{packet.protocol}"
                    ),
                    source_port=packet.src_port,
                    destination_ip=packet.dst_ip,
                    destination_port=packet.dst_port,
                    protocol=packet.protocol,
                    timestamp=packet.timestamp,
                )
            self.auto_blocker.record_detection_activity(
                ip_address=packet.src_ip,
                attack_type="Brute Force",
                action="blocked" if blocked else "allowed",
                timestamp=packet.timestamp,
            )

        session_key = SessionKey.from_packet(packet)
        session = self.session_builder.process_packet(packet)

        expired_finalized = self.session_builder.drain_finalized_sessions()
        for finalized in expired_finalized:
            self._process_finalized_session(finalized, heuristic_decision)

        if self.session_builder.should_predict(packet):
            features = self.feature_extractor.extract(session)
            self.feature_store.add(features)

            prediction_started = time.perf_counter()
            prediction = self.live_predictor.predict(features)
            prediction_duration = time.perf_counter() - prediction_started
            if self.telemetry_collector is not None and prediction is not None:
                self.telemetry_collector.record_ml_prediction(
                    duration_seconds=prediction_duration
                )
            self._publish_session_update(
                session_key=session_key,
                session=session,
                session_state="active",
                prediction=prediction,
                heuristic_decision=heuristic_decision,
            )
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
                self._publish_prediction_event(
                    session_key=session_key,
                    session=session,
                    prediction=prediction,
                    features=features,
                    event_type="ml_live_prediction",
                )
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
                    if blocked:
                        self._publish_block_event(
                            event_id=f"ml-live-{session.src_ip}-{int(session.last_seen * 1000)}",
                            source_ip=session.src_ip,
                            action_taken="blocked",
                            reason=prediction["label"],
                            detection_method="ml",
                            session_id=self._session_key_str(session_key),
                            source_port=session.src_port,
                            destination_ip=session.dst_ip,
                            destination_port=session.dst_port,
                            protocol=session.protocol,
                            timestamp=session.last_seen,
                        )
                    self.auto_blocker.record_detection_activity(
                        ip_address=session.src_ip,
                        attack_type=prediction["label"],
                        action="blocked" if blocked else "allowed",
                        timestamp=session.last_seen,
                    )

        finalized = self.session_builder.finalize_session_if_needed(packet)
        if finalized is not None:
            self._process_finalized_session(finalized, heuristic_decision)

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

    def _publish_block_event(
        self,
        event_id: str,
        source_ip: str,
        action_taken: str,
        reason: str,
        detection_method: str,
        session_id: str | None,
        source_port: int | None,
        destination_ip: str | None,
        destination_port: int | None,
        protocol: int | None,
        timestamp: float,
    ):
        if not callable(self.block_event_publisher):
            return

        payload = {
            "event_id": event_id,
            "timestamp": datetime.fromtimestamp(float(timestamp), tz=timezone.utc).isoformat(),
            "source_ip": source_ip,
            "action_taken": action_taken,
            "reason": reason,
            "detection_method": detection_method,
            "session_id": session_id,
            "source_port": source_port,
            "destination_ip": destination_ip,
            "destination_port": destination_port,
            "protocol": protocol,
        }

        try:
            self.block_event_publisher(payload)
        except Exception:
            pass

    def _publish_prediction_event(
        self,
        session_key: SessionKey,
        session,
        prediction: dict,
        features: dict,
        event_type: str,
        is_final: bool = False,
    ):
        if not callable(self.event_publisher):
            return

        event = build_ids_event_payload(
            session_key=session_key,
            session=session,
            prediction=prediction,
            features=features,
            event_type=event_type,
            is_final=is_final,
        )

        try:
            self.event_publisher(event)
        except Exception:
            pass

    def _publish_session_update(
        self,
        session_key: SessionKey,
        session,
        session_state: str,
        prediction: dict | None,
        heuristic_decision,
    ):
        if not callable(self.session_update_publisher):
            return

        session_update = build_session_upsert_payload(
            session_key=session_key,
            session=session,
            session_state=session_state,
            prediction=prediction,
            heuristic_decision=heuristic_decision,
        )

        try:
            self.session_update_publisher(session_update)
        except Exception:
            pass

    def _risk_score(self, label: str | None, confidence: float, heuristic_score: int) -> float:
        ml_score = 0.0 if label in (None, "Normal Traffic") else confidence
        heuristic_score_normalized = min(1.0, max(0.0, float(heuristic_score) / 10.0))
        return round(max(ml_score, heuristic_score_normalized), 4)

    def _prediction_event_id(
        self,
        session_id: str,
        event_type: str,
        label: str,
        timestamp: float,
    ) -> str:
        raw = f"{session_id}:{event_type}:{label}:{int(timestamp * 1000)}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def _severity_from_prediction(self, label: str, confidence: float) -> str:
        if label == "Normal Traffic":
            return "low"
        if confidence >= self.alert_confidence_threshold:
            return "high"
        return "medium"

    def _process_finalized_session(self, finalized: dict, heuristic_decision):
        final_session = finalized["session"]
        final_key = finalized["session_key"]
        final_features = self.feature_extractor.extract(final_session)
        prediction_started = time.perf_counter()
        final_prediction = self.completed_flow_predictor.predict(final_features)
        prediction_duration = time.perf_counter() - prediction_started
        if self.telemetry_collector is not None and final_prediction is not None:
            self.telemetry_collector.record_ml_prediction(
                duration_seconds=prediction_duration
            )

        self._publish_session_update(
            session_key=final_key,
            session=final_session,
            session_state=finalized["reason"],
            prediction=final_prediction,
            heuristic_decision=heuristic_decision,
        )

        if final_prediction is not None:
            self._publish_prediction_event(
                session_key=final_key,
                session=final_session,
                prediction=final_prediction,
                features=final_features,
                event_type="ml_completed_flow_prediction",
                is_final=True,
            )

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
            if blocked:
                self._publish_block_event(
                    event_id=f"ml-final-{final_session.src_ip}-{int(final_session.last_seen * 1000)}",
                    source_ip=final_session.src_ip,
                    action_taken="blocked",
                    reason=final_prediction["label"],
                    detection_method="ml",
                    session_id=self._session_key_str(final_key),
                    source_port=final_session.src_port,
                    destination_ip=final_session.dst_ip,
                    destination_port=final_session.dst_port,
                    protocol=final_session.protocol,
                    timestamp=final_session.last_seen,
                )
            self.auto_blocker.record_detection_activity(
                ip_address=final_session.src_ip,
                attack_type=final_prediction["label"],
                action="blocked" if blocked else "allowed",
                timestamp=final_session.last_seen,
            )

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
