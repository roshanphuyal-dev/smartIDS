from __future__ import annotations

import time
from collections import deque
from datetime import datetime, timezone
from queue import Queue
from threading import Lock
from typing import Callable


class EngineTelemetryCollector:
    def __init__(
        self,
        *,
        clock: Callable[[], float] | None = None,
        packet_window_seconds: float = 30.0,
        max_exchange_count: int = 20,
    ) -> None:
        self._clock = clock or time.time
        self._packet_window_seconds = packet_window_seconds
        self._max_exchange_count = max_exchange_count
        self._lock = Lock()
        self._packets_received_total = 0
        self._packets_processed_total = 0
        self._packets_dropped_total = 0
        self._ml_predictions_total = 0
        self._last_ml_prediction_latency_ms = 0.0
        self._packet_received_times: deque[float] = deque()
        self._ml_prediction_times: deque[float] = deque()

    def record_packet_received(self) -> None:
        now = self._clock()
        with self._lock:
            self._packets_received_total += 1
            self._packet_received_times.append(now)
            self._trim(self._packet_received_times, now)

    def record_packet_processed(self) -> None:
        with self._lock:
            self._packets_processed_total += 1

    def record_packet_dropped(self) -> None:
        with self._lock:
            self._packets_dropped_total += 1

    def record_ml_prediction(self, *, duration_seconds: float) -> None:
        now = self._clock()
        with self._lock:
            self._ml_predictions_total += 1
            self._ml_prediction_times.append(now)
            self._last_ml_prediction_latency_ms = round(max(0.0, duration_seconds) * 1000.0, 4)
            self._trim(self._ml_prediction_times, now)

    def snapshot(self, *, packet_queue: Queue, session_builder) -> dict:
        now = self._clock()
        with self._lock:
            self._trim(self._packet_received_times, now)
            self._trim(self._ml_prediction_times, now)
            packets_received_total = self._packets_received_total
            packets_processed_total = self._packets_processed_total
            packets_dropped_total = self._packets_dropped_total
            packets_received_per_window = len(self._packet_received_times)
            ml_predictions_total = self._ml_predictions_total
            ml_predictions_per_window = len(self._ml_prediction_times)
            last_ml_latency_ms = self._last_ml_prediction_latency_ms

        queue_size = _safe_qsize(packet_queue)
        queue_maxsize = max(0, int(getattr(packet_queue, "maxsize", 0) or 0))
        queue_usage_percent = 0.0
        if queue_maxsize > 0:
            queue_usage_percent = round((queue_size / queue_maxsize) * 100.0, 4)

        active_sessions = list(getattr(session_builder, "sessions", {}).values())
        return {
            "ts": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
            "packets_received_total": packets_received_total,
            "packets_received_per_30s": packets_received_per_window,
            "packets_processed_total": packets_processed_total,
            "packets_dropped_total": packets_dropped_total,
            "packets_lost_total": packets_dropped_total,
            "packet_loss_detected": packets_dropped_total > 0,
            "packet_queue_size": queue_size,
            "packet_queue_maxsize": queue_maxsize,
            "packet_queue_usage_percent": queue_usage_percent,
            "active_sessions": len(active_sessions),
            "ml_predictions_total": ml_predictions_total,
            "ml_predictions_per_30s": ml_predictions_per_window,
            "ml_processing_rate_per_30s": ml_predictions_per_window,
            "last_ml_prediction_latency_ms": last_ml_latency_ms,
            "application_attribution_available": False,
            "application_attribution_note": (
                "Passive packet capture cannot reliably map flows to local process "
                "or application names cross-platform; active network exchanges are "
                "reported as endpoint pairs."
            ),
            "active_network_exchanges": [
                _session_exchange(session)
                for session in active_sessions[: self._max_exchange_count]
            ],
        }

    def _trim(self, timestamps: deque[float], now: float) -> None:
        cutoff = now - self._packet_window_seconds
        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()


def _safe_qsize(packet_queue: Queue) -> int:
    try:
        return int(packet_queue.qsize())
    except NotImplementedError:
        return 0


def _session_exchange(session) -> dict:
    return {
        "source_ip": session.src_ip,
        "destination_ip": session.dst_ip,
        "source_port": session.src_port,
        "destination_port": session.dst_port,
        "protocol": session.protocol,
        "packet_count": session.packet_count,
        "byte_count": session.total_bytes,
        "duration": round(float(session.duration()), 4),
    }

