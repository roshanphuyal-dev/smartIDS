from collections import deque
from threading import Lock


class FeatureStore:
    def __init__(self, max_size=1000):
        self.features = deque(maxlen=max_size)
        self._lock = Lock()

    def add(self, feature):
        with self._lock:
            self.features.append(feature)

    def get_all(self):
        with self._lock:
            return list(self.features)

    def size(self):
        with self._lock:
            return len(self.features)
