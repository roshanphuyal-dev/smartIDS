from __future__ import annotations

import unittest

from scripts.seed.dataset import build_seed_plan


class SeedDatasetTest(unittest.TestCase):
    def test_seed_plan_has_expected_core_volume(self) -> None:
        plan = build_seed_plan()

        self.assertGreaterEqual(len(plan.users), 8)
        self.assertGreaterEqual(len(plan.network_sessions), 20)
        self.assertGreaterEqual(len(plan.ids_events), 100)
        self.assertGreaterEqual(len(plan.alerts), 20)
        self.assertGreaterEqual(len(plan.block_events), 20)

    def test_seed_plan_excludes_notifications_until_schema_is_real(self) -> None:
        plan = build_seed_plan()

        excluded = {item.table_name: item.reason for item in plan.excluded_tables}
        self.assertIn("notifications", excluded)
        self.assertIn("migration", excluded["notifications"].lower())

    def test_demo_credentials_reflect_real_auth_constraints(self) -> None:
        plan = build_seed_plan()
        by_email = {item.email: item for item in plan.demo_credentials}

        self.assertEqual(by_email["analyst@smartids-demo.dev"].password, "AnalystPass!123")
        self.assertIsNone(by_email["github.alice@smartids-demo.dev"].password)
        self.assertIn("no role", by_email["manager@smartids-demo.dev"].notes.lower())
