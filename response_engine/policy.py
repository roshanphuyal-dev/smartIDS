from collections import deque
import os


class ResponsePolicy:
    def __init__(self):
        self.low_heuristic_score_max = 2
        self.high_heuristic_score_min = 3

        self.high_heuristic_block_seconds = 300
        self.ml_confirmed_block_seconds = 900
        self.bruteforce_block_seconds = 600

        self.bruteforce_window_seconds = float(
            os.getenv("SMARTIDS_BRUTEFORCE_WINDOW_SECONDS", "90")
        )
        self.bruteforce_attempt_threshold = int(
            os.getenv("SMARTIDS_BRUTEFORCE_ATTEMPT_THRESHOLD", "25")
        )
        self.bruteforce_service_ports = {21, 22, 23, 25, 110, 143, 3389}

        self._attempts = {}

    def classify_heuristic_action(self, score: int) -> str:
        if score >= self.high_heuristic_score_min:
            return "high_temp_block"
        if score <= self.low_heuristic_score_max:
            return "alert_only"
        return "alert_only"

    def record_bruteforce_attempt(self, src_ip: str, dst_ip: str, dst_port, timestamp: float) -> bool:
        if dst_port is None:
            return False

        port = int(dst_port)
        if port not in self.bruteforce_service_ports:
            return False

        key = (str(src_ip), str(dst_ip), port)
        bucket = self._attempts.setdefault(key, deque())
        bucket.append(float(timestamp))

        cutoff = float(timestamp) - self.bruteforce_window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        return len(bucket) >= self.bruteforce_attempt_threshold
