from __future__ import annotations

import unittest

from ml.features.schema import FEATURE_COLUMNS


class FeatureColumnsOrderTest(unittest.TestCase):
    def test_feature_columns_keep_required_order(self) -> None:
        self.assertEqual(FEATURE_COLUMNS[:2], ["dst_port", "protocol"])
        self.assertEqual(
            FEATURE_COLUMNS[-3:],
            ["init_win_bytes_forward", "act_data_pkt_fwd", "min_seg_size_forward"],
        )
        self.assertEqual(len(FEATURE_COLUMNS), 37)
