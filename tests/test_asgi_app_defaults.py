from __future__ import annotations

import unittest
from collections import Counter

from Ouroboros.asgi_app import _create_runner, _default_agent_specs


class AsgiAppDefaultAgentTests(unittest.TestCase):
    def test_default_agent_specs_have_expected_24_agent_distribution(self) -> None:
        specs = _default_agent_specs()

        self.assertEqual(len(specs), 24)
        self.assertEqual(
            Counter(spec.permission_profile.agent_type.value for spec in specs),
            {
                "mutual_fund": 2,
                "hot_money": 2,
                "quant_algo": 2,
                "national_team": 2,
                "retail": 16,
            },
        )

    def test_default_runner_hold_actions_cover_all_default_agents(self) -> None:
        specs = _default_agent_specs()
        runner = _create_runner()
        runtime = runner._agent_runtime_factory()

        self.assertEqual(
            runtime._default_actions,
            {spec.agent_id: {"action_type": "hold"} for spec in specs},
        )

    def test_default_agent_permissions_follow_identity_matrix(self) -> None:
        specs = _default_agent_specs()

        for spec in specs:
            profile = spec.permission_profile
            subscriptions = set(profile.subscriptions)
            with self.subTest(agent_id=spec.agent_id):
                self.assertIn("Market_Price", subscriptions)
                self.assertIn("Account_Snapshot:self", subscriptions)
                self.assertIn("Tape_Alerts", subscriptions)
                self.assertIn("End_of_Day", subscriptions)
                self.assertEqual(
                    profile.publish_permissions.forum_post,
                    profile.agent_type.value == "hot_money",
                )
                if profile.agent_type.value == "retail":
                    self.assertNotIn("Official_News", subscriptions)
                    self.assertIn("Forum_Rumors", subscriptions)
                    self.assertEqual(profile.official_news_scope, [])
                else:
                    self.assertIn("Official_News", subscriptions)


if __name__ == "__main__":
    unittest.main()
