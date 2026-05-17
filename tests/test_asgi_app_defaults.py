from __future__ import annotations

import unittest
from collections import Counter
from unittest.mock import patch

from Ouroboros.asgi_app import (
    _bus_mode_from_env,
    _create_chronos_repository,
    _create_runner,
    _default_agent_profiles,
    _default_agent_specs,
    _default_prompt_profiles,
    _llm_max_requests_from_env,
    _llm_window_seconds_from_env,
)
from Ouroboros.core.chronos import ChronosConfigurationError
from Ouroboros.core.llm import LLMConfig, LLMConfigurationError
from Ouroboros.core.routing import BusConfigurationError
from Ouroboros.core.schemas import OrderActionType, TickContext


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

    def test_default_runner_does_not_inject_default_agent_actions(self) -> None:
        specs = _default_agent_specs()
        valid_config = LLMConfig(
            api_key="test-api-key",
            base_url="https://llm.example.test/v1",
            model="test-model",
            provider_name="openai_compatible",
        )
        with patch.dict("os.environ", {}, clear=True), patch(
            "Ouroboros.asgi_app.LLMConfig.from_env",
            return_value=valid_config,
        ):
            runner = _create_runner()
            runtime = runner._agent_runtime_factory()

        self.assertEqual(specs[0].agent_id, "mutual_fund_a")
        self.assertEqual(runtime._default_actions, {})

    def test_asgi_default_profiles_use_non_runtime_default_prompt_refs(self) -> None:
        agent_profiles = _default_agent_profiles()
        prompt_profiles = _default_prompt_profiles()

        self.assertEqual(set(agent_profiles), {spec.agent_id for spec in _default_agent_specs()})
        self.assertNotIn("runtime_default", prompt_profiles)
        for spec in _default_agent_specs():
            profile = agent_profiles[spec.agent_id]
            with self.subTest(agent_id=spec.agent_id):
                self.assertNotEqual(profile["prompt_profile_ref"], "runtime_default")
                self.assertIn(profile["prompt_profile_ref"], prompt_profiles)
                self.assertEqual(
                    prompt_profiles[profile["prompt_profile_ref"]]["agent_type"],
                    spec.permission_profile.agent_type.value,
                )

    def test_llm_runtime_factory_receives_default_prompt_profiles(self) -> None:
        valid_config = LLMConfig(
            api_key="test-api-key",
            base_url="https://llm.example.test/v1",
            model="test-model",
            provider_name="openai_compatible",
        )
        with patch.dict("os.environ", {}, clear=True), patch(
            "Ouroboros.asgi_app.LLMConfig.from_env",
            return_value=valid_config,
        ):
            runner = _create_runner()
            runtime = runner._agent_runtime_factory()

        self.assertEqual(
            runtime._agent_profiles["mutual_fund_a"].prompt_profile_ref,
            "prompt_mutual_fund_v1",
        )
        self.assertIn("prompt_mutual_fund_v1", runtime._prompt_profiles)
        self.assertEqual(runtime._llm_gateway._max_requests, 2400)

    def test_llm_rate_limit_policy_is_configurable_for_continuous_runs(self) -> None:
        env = {
            "OUROBOROS_LLM_MAX_REQUESTS_PER_WINDOW": "4800",
            "OUROBOROS_LLM_WINDOW_SECONDS": "30",
        }

        self.assertEqual(_llm_max_requests_from_env(env), 4800)
        self.assertEqual(_llm_window_seconds_from_env(env), 30.0)

    def test_llm_runtime_uses_hold_fallback_for_provider_output_failures(self) -> None:
        valid_config = LLMConfig(
            api_key="test-api-key",
            base_url="https://llm.example.test/v1",
            model="test-model",
            provider_name="openai_compatible",
        )
        with patch.dict("os.environ", {}, clear=True), patch(
            "Ouroboros.asgi_app.LLMConfig.from_env",
            return_value=valid_config,
        ):
            runner = _create_runner()
            runtime = runner._agent_runtime_factory()

        self.assertFalse(runtime.raises_llm_errors)

    def test_asgi_default_bus_mode_is_in_memory(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(_bus_mode_from_env(), "in_memory")

    def test_asgi_default_chronos_mode_uses_demo_seed_repository(self) -> None:
        repository = _create_chronos_repository({})

        seed = repository.get_initial_market_seed("demo_stock")

        self.assertEqual(seed.seed_id, "seed_demo_stock")

    def test_asgi_explicit_in_memory_chronos_mode_uses_demo_seed_repository(self) -> None:
        repository = _create_chronos_repository(
            {"OUROBOROS_CHRONOS_MODE": "in_memory"}
        )

        seed = repository.get_initial_market_seed("demo_stock")

        self.assertEqual(seed.seed_id, "seed_demo_stock")

    def test_asgi_external_chronos_mode_fails_fast_without_adapter(self) -> None:
        with self.assertRaisesRegex(ChronosConfigurationError, "real Chronos repository adapter"):
            _create_chronos_repository({"OUROBOROS_CHRONOS_MODE": "external"})

    def test_asgi_real_chronos_mode_fails_fast_without_demo_seed(self) -> None:
        with patch.dict(
            "os.environ",
            {"OUROBOROS_CHRONOS_MODE": "real", "OUROBOROS_AGENT_MODE": "mock_hold"},
            clear=True,
        ):
            with self.assertRaisesRegex(ChronosConfigurationError, "real Chronos repository adapter"):
                _create_runner()

    def test_asgi_redis_bus_mode_fails_fast(self) -> None:
        with patch.dict("os.environ", {"OUROBOROS_BUS_MODE": "redis"}, clear=True):
            with self.assertRaisesRegex(BusConfigurationError, "requires a real Redis bus adapter"):
                _create_runner()

    def test_default_llm_mode_rejects_missing_provider_config(self) -> None:
        with patch.dict("os.environ", {}, clear=True), patch(
            "Ouroboros.asgi_app.LLMConfig.from_env",
            return_value=LLMConfig(provider_name="deterministic_mock"),
        ):
            runner = _create_runner()
            with self.assertRaisesRegex(LLMConfigurationError, "OUROBOROS_LLM_PROVIDER"):
                runner._agent_runtime_factory()

    def test_mock_hold_mode_actions_cover_all_default_agents(self) -> None:
        specs = _default_agent_specs()
        with patch.dict("os.environ", {"OUROBOROS_AGENT_MODE": "mock_hold"}, clear=True):
            runner = _create_runner()
        runtime = runner._agent_runtime_factory()

        self.assertEqual(set(runtime._default_actions), {spec.agent_id for spec in specs})
        for spec in specs:
            action = runtime._default_actions[spec.agent_id]
            with self.subTest(agent_id=spec.agent_id):
                self.assertEqual(action["action_type"], "hold")

    def test_mock_hold_mode_runtime_act_returns_schema_valid_hold_payload(self) -> None:
        with patch.dict("os.environ", {"OUROBOROS_AGENT_MODE": "mock_hold"}, clear=True):
            runner = _create_runner()
        runtime = runner._agent_runtime_factory()
        context = TickContext.from_dict(
            {
                "schema_version": "v1",
                "tick_id": "2024-01-02T14:02:00+08:00",
                "trace_id": "trace_abc",
                "agent_id": "mutual_fund_a",
                "agent_role": "mutual_fund",
                "public_inputs": {"market_price": {"symbol": "demo_stock", "last_price": 10.0}},
                "private_inputs": {
                    "account_snapshot": {"agent_id": "mutual_fund_a", "cash": 1000},
                },
                "constraints": {
                    "allowed_actions": ["hold", "buy", "sell", "cancel"],
                    "deadline_ms": 30000,
                    "can_post_forum": False,
                },
            }
        )

        payload = runtime.act(context)

        self.assertEqual(payload.schema_version, "v1")
        self.assertEqual(payload.agent_id, "mutual_fund_a")
        self.assertEqual(payload.tick_id, "2024-01-02T14:02:00+08:00")
        self.assertEqual(payload.trace_id, "trace_abc")
        self.assertEqual(payload.action.action_type, OrderActionType.HOLD)
        self.assertEqual(payload.evidence_refs, [])
        self.assertIsNone(payload.belief_shift)
        self.assertIsNone(payload.forum_post)
        self.assertIsNone(payload.memory_update)
        self.assertEqual(payload.to_dict()["schema_version"], "v1")

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
