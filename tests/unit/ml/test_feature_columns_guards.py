from __future__ import annotations

import unittest

from ml.features.schema import FEATURE_COLUMNS, LABEL_COLUMN


class FeatureColumnsGuardsTest(unittest.TestCase):
    def test_feature_columns_keep_required_contract(self) -> None:
        self.assertEqual(FEATURE_COLUMNS[0], "dst_port")
        self.assertEqual(FEATURE_COLUMNS[1], "protocol")
        self.assertNotIn("src_port", FEATURE_COLUMNS)
        self.assertEqual(LABEL_COLUMN, "Attack Type")
        self.assertEqual(len(FEATURE_COLUMNS), len(set(FEATURE_COLUMNS)))
