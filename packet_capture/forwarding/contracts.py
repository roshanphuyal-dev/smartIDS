from __future__ import annotations

import hashlib
from datetime import datetime, timezone


def _iso_ts(timestamp: float | datetime) -> str:
    if isinstance(timestamp, datetime):
        return timestamp.astimezone(timezone.utc).isoformat()
    return datetime.fromtimestamp(float(timestamp), tz=timezone.utc).isoformat()


def _session_id(session_key) -> str:
    return (
        f"{session_key.src_ip}:{session_key.src_port}-"
        f"{session_key.dst_ip}:{session_key.dst_port}-"
        f"{session_key.protocol}"
    )


def build_ids_event_payload(
    *,
    session_key,
    session,
    prediction: dict,
    features: dict,
    event_type: str,
    is_final: bool = False,
) -> dict:
    confidence = float(prediction.get("confidence", 0.0))
    label = str(prediction.get("label", "Unknown"))
    model_key = str(prediction.get("model_key", event_type))
    session_id = _session_id(session_key)
    timestamp = float(session.last_seen)
    event_id = _prediction_event_id(session_id, event_type, label, timestamp)
    action = "allow" if label == "Normal Traffic" else "alert"
    forwarded_features = {
        **dict(features),
        "session_id": session_id,
        "source_ip": session.src_ip,
        "destination_ip": session.dst_ip,
        "source_port": session.src_port,
        "destination_port": session.dst_port,
        "session_duration": session.duration(),
        "session_packet_count": session.packet_count,
        "session_byte_count": session.total_bytes,
        "is_final": is_final,
    }

    model_outputs = prediction.get("model_outputs")
    if isinstance(model_outputs, dict):
        forwarded_features["model_outputs"] = model_outputs

    model_stack = prediction.get("model_stack")
    if isinstance(model_stack, dict):
        forwarded_features["model_stack"] = model_stack

    return {
        "schema_version": "1.0",
        "event_id": event_id,
        "ts": _iso_ts(timestamp),
        "source": session.src_ip,
        "source_ip": session.src_ip,
        "destination_ip": session.dst_ip,
        "source_port": session.src_port,
        "destination_port": session.dst_port,
        "protocol": session.protocol,
        "model": model_key,
        "prediction": label,
        "attack_type": label,
        "confidence": confidence,
        "confidence_score": confidence,
        "severity": _severity_from_prediction(label, confidence),
        "action": action,
        "action_taken": action,
        "detection_method": event_type,
        "session_id": session_id,
        "risk_score": confidence,
        "packet_count": session.packet_count,
        "byte_count": session.total_bytes,
        "flow_duration": round(session.duration(), 4),
        "ml_prediction": label,
        "features": forwarded_features,
    }


def build_session_upsert_payload(
    *,
    session_key,
    session,
    session_state: str,
    prediction: dict | None,
    heuristic_decision,
) -> dict:
    session_id = _session_id(session_key)
    confidence = 0.0 if prediction is None else float(prediction.get("confidence", 0.0))
    ml_prediction = None if prediction is None else str(prediction.get("label", "Unknown"))
    heuristic_summary = f"{heuristic_decision.reason}:{heuristic_decision.score}"

    return {
        "session_id": session_id,
        "start_time": _iso_ts(session.start_time),
        "end_time": _iso_ts(session.last_seen),
        "source_ip": session.src_ip,
        "destination_ip": session.dst_ip,
        "source_port": session.src_port,
        "destination_port": session.dst_port,
        "protocol": session.protocol,
        "packet_count": session.packet_count,
        "byte_count": session.total_bytes,
        "duration": session.duration(),
        "risk_score": _risk_score(ml_prediction, confidence, heuristic_decision.score),
        "ml_prediction": ml_prediction,
        "heuristic_result": heuristic_summary,
        "state": session_state,
        "action_taken": "allowed" if session_state == "active" else session_state,
    }


def _prediction_event_id(session_id: str, event_type: str, label: str, timestamp: float) -> str:
    raw = f"{session_id}:{event_type}:{label}:{int(timestamp * 1000)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _severity_from_prediction(label: str, confidence: float) -> str:
    if label == "Normal Traffic":
        return "low"
    if confidence >= 0.8:
        return "high"
    return "medium"


def _risk_score(label: str | None, confidence: float, heuristic_score: int) -> float:
    ml_score = 0.0 if label in (None, "Normal Traffic") else confidence
    heuristic_score_normalized = min(1.0, max(0.0, float(heuristic_score) / 10.0))
    return round(max(ml_score, heuristic_score_normalized), 4)
