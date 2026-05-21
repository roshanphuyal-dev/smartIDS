from collections import deque


class FeatureStore:
    def __init__(self, max_size=1000):
        self.features = deque(maxlen=max_size)

    def add(self, feature):
        self.features.append(feature)

    def get_all(self):
        return list(self.features)

    def size(self):
        return len(self.features)
