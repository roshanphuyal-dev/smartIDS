from __future__ import annotations

import random
import unittest
from statistics import mean, pstdev, pvariance

from traffic_engine.session_builder.running_stats import RunningStats


class RunningStatsTest(unittest.TestCase):
    def test_zero_packets_returns_zeroed_stats(self) -> None:
        stats = RunningStats()

        self.assertEqual(stats.count, 0)
        self.assertEqual(stats.get_min(), 0.0)
        self.assertEqual(stats.get_max(), 0.0)
        self.assertEqual(stats.get_mean(), 0.0)
        self.assertEqual(stats.variance(), 0.0)
        self.assertEqual(stats.std(), 0.0)

    def test_single_packet_matches_naive_computation(self) -> None:
        stats = RunningStats()
        stats.update(42)

        self.assertEqual(stats.count, 1)
        self.assertEqual(stats.get_min(), 42.0)
        self.assertEqual(stats.get_max(), 42.0)
        self.assertEqual(stats.get_mean(), 42.0)
        self.assertEqual(stats.variance(), 0.0)
        self.assertEqual(stats.std(), 0.0)

    def test_identical_values_have_zero_variance(self) -> None:
        stats = RunningStats()
        for _ in range(10):
            stats.update(100)

        self.assertEqual(stats.count, 10)
        self.assertEqual(stats.get_min(), 100.0)
        self.assertEqual(stats.get_max(), 100.0)
        self.assertEqual(stats.get_mean(), 100.0)
        self.assertAlmostEqual(stats.variance(), 0.0)
        self.assertAlmostEqual(stats.std(), 0.0)

    def test_matches_naive_recomputation_across_insertion_orders(self) -> None:
        values = [60, 110, 90, 1500, 40, 40, 1500, 88, 512, 64]

        for ordering in (
            values,
            list(reversed(values)),
            sorted(values),
            sorted(values, reverse=True),
        ):
            with self.subTest(ordering=ordering):
                stats = RunningStats()
                for value in ordering:
                    stats.update(value)

                self.assertAlmostEqual(stats.get_min(), float(min(values)))
                self.assertAlmostEqual(stats.get_max(), float(max(values)))
                self.assertAlmostEqual(stats.get_mean(), mean(values))
                self.assertAlmostEqual(stats.variance(), pvariance(values))
                self.assertAlmostEqual(stats.std(), pstdev(values))

    def test_matches_naive_recomputation_on_shuffled_random_inputs(self) -> None:
        rng = random.Random(1234)
        values = [rng.uniform(1, 1500) for _ in range(500)]

        shuffled = list(values)
        rng.shuffle(shuffled)

        stats = RunningStats()
        for value in shuffled:
            stats.update(value)

        self.assertEqual(stats.count, len(values))
        self.assertAlmostEqual(stats.get_min(), min(values))
        self.assertAlmostEqual(stats.get_max(), max(values))
        self.assertAlmostEqual(stats.get_mean(), mean(values))
        self.assertAlmostEqual(stats.variance(), pvariance(values))
        self.assertAlmostEqual(stats.std(), pstdev(values))

    def test_negative_and_mixed_sign_values(self) -> None:
        values = [-50, 0, 50, -100, 100]

        stats = RunningStats()
        for value in values:
            stats.update(value)

        self.assertAlmostEqual(stats.get_min(), float(min(values)))
        self.assertAlmostEqual(stats.get_max(), float(max(values)))
        self.assertAlmostEqual(stats.get_mean(), mean(values))
        self.assertAlmostEqual(stats.variance(), pvariance(values))
        self.assertAlmostEqual(stats.std(), pstdev(values))


if __name__ == "__main__":
    unittest.main()
