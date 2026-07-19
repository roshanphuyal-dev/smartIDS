import math


class RunningStats:
    """Incremental mean/variance/min/max using Welford's online algorithm.

    Maintains O(1) state (count, running mean, running sum of squared
    deviations, min, max) so per-packet statistics no longer require
    replaying the full history of a session on every prediction trigger.
    Numerically stable, but not guaranteed bit-identical to a naive
    from-scratch recomputation over the same values.
    """

    def __init__(self):
        self.count = 0
        self.mean = 0.0
        self._m2 = 0.0
        self._min = None
        self._max = None

    def update(self, value) -> None:
        value = float(value)

        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        delta2 = value - self.mean
        self._m2 += delta * delta2

        if self._min is None or value < self._min:
            self._min = value
        if self._max is None or value > self._max:
            self._max = value

    def get_min(self) -> float:
        return 0.0 if self._min is None else float(self._min)

    def get_max(self) -> float:
        return 0.0 if self._max is None else float(self._max)

    def get_mean(self) -> float:
        return 0.0 if self.count == 0 else float(self.mean)

    def variance(self) -> float:
        """Population variance, matching ``statistics.pvariance`` semantics."""
        if self.count < 2:
            return 0.0
        return self._m2 / self.count

    def std(self) -> float:
        """Population standard deviation, matching ``statistics.pstdev``."""
        return math.sqrt(self.variance())
