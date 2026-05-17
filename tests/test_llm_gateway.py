from __future__ import annotations

import json
import os
import socket
import tempfile
import unittest
from contextlib import contextmanager
from inspect import signature
from pathlib import Path
from unittest.mock import patch

from Ouroboros.core import llm as llm_module
from Ouroboros.core.llm import LLMGateway
from Ouroboros.core.schemas import LLMRequest, SchemaValidationError


def llm_request(
    agent_id: str = "agent_a",
    *,
    request_id: str = "llm_req_001",
    content: str = "Only use this agent context.",
) -> dict[str, object]:
    return {
        "schema_version": "v1",
        "request_id": request_id,
        "agent_id": agent_id,
        "tick_id": "2024-01-02T14:02:00+08:00",
        "prompt_profile_id": "retail_default",
        "messages": [{"role": "user", "content": content}],
        "output_schema_ref": "agent_payload.v1",
        "deadline_ms": 30000,
    }


class MutableClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class LLMGatewayTests(unittest.TestCase):
    def _llm_config_type(self) -> type:
        config_type = getattr(llm_module, "LLMConfig", None)
        self.assertIsNotNone(
            config_type,
            "Ouroboros.core.llm must export LLMConfig for api_key/base_url/model/provider_name",
        )
        return config_type

    def _load_llm_config(self, *, env_file: Path | None = None) -> object:
        config_type = self._llm_config_type()
        if hasattr(config_type, "from_env"):
            if env_file is None:
                return config_type.from_env()
            parameters = signature(config_type.from_env).parameters
            if "env_path" in parameters:
                return config_type.from_env(env_path=env_file)
            if "env_file" in parameters:
                return config_type.from_env(env_file=env_file)
            self.fail("LLMConfig.from_env() must accept an env_path or env_file argument")

        loader = getattr(llm_module, "load_llm_config", None)
        self.assertIsNotNone(
            loader,
            "LLM config must be loadable via LLMConfig.from_env() or load_llm_config()",
        )
        if env_file is None:
            return loader()
        parameters = signature(loader).parameters
        if "env_path" in parameters:
            return loader(env_path=env_file)
        if "env_file" in parameters:
            return loader(env_file=env_file)
        self.fail("load_llm_config() must accept an env_path or env_file argument")

    def _mock_gateway(self, **kwargs: object) -> LLMGateway:
        config_type = self._llm_config_type()
        return LLMGateway(config=config_type(provider_name="deterministic_mock"), **kwargs)

    @contextmanager
    def _forbid_network(self):
        with patch.object(
            socket.socket,
            "connect",
            side_effect=AssertionError("LLM config tests must not access the network"),
        ):
            yield

    def test_complete_returns_schema_shaped_mock_output(self) -> None:
        gateway = self._mock_gateway()

        output = gateway.complete(LLMRequest.from_dict(llm_request()))

        self.assertEqual(output["schema_version"], "v1")
        self.assertEqual(output["agent_id"], "agent_a")
        candidate = output["candidates"][0]
        content = json.loads(candidate["content"])
        self.assertEqual(content["action"]["action_type"], "hold")
        self.assertEqual(content["agent_id"], "agent_a")

    def test_complete_accepts_explicit_llm_config_without_leaking_secrets(self) -> None:
        config_type = self._llm_config_type()
        config = config_type(
            api_key="test-api-key",
            base_url="https://llm.example.test/v1",
            model="test-model",
            provider_name="configured_mock",
        )
        gateway = LLMGateway(config=config)

        with self._forbid_network():
            output = gateway.complete(LLMRequest.from_dict(llm_request()))

        self.assertEqual(output["provider"], "configured_mock")
        serialized_output = json.dumps(output, sort_keys=True)
        self.assertNotIn("test-api-key", serialized_output)
        self.assertNotIn("https://llm.example.test/v1", serialized_output)
        self.assertNotIn("test-model", serialized_output)

    def test_llm_config_loads_from_environment(self) -> None:
        env = {
            "OUROBOROS_LLM_API_KEY": "env-api-key",
            "OUROBOROS_LLM_BASE_URL": "https://env-llm.example.test/v1",
            "OUROBOROS_LLM_MODEL": "env-model",
            "OUROBOROS_LLM_PROVIDER": "env_provider",
        }

        with patch.dict(os.environ, env, clear=False):
            config = self._load_llm_config()

        self.assertEqual(config.api_key, "env-api-key")
        self.assertEqual(config.base_url, "https://env-llm.example.test/v1")
        self.assertEqual(config.model, "env-model")
        self.assertEqual(config.provider_name, "env_provider")

        gateway = LLMGateway(config=config)
        with self._forbid_network():
            output = gateway.complete(llm_request())

        self.assertEqual(output["provider"], "env_provider")

    def test_llm_config_loads_from_dotenv_when_environment_is_absent(self) -> None:
        llm_env_keys = (
            "OUROBOROS_LLM_API_KEY",
            "OUROBOROS_LLM_BASE_URL",
            "OUROBOROS_LLM_MODEL",
            "OUROBOROS_LLM_PROVIDER",
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            env_file = Path(tmp_dir) / ".env"
            env_file.write_text(
                "\n".join(
                    [
                        "OUROBOROS_LLM_API_KEY=dotenv-api-key",
                        "OUROBOROS_LLM_BASE_URL=https://dotenv-llm.example.test/v1",
                        "OUROBOROS_LLM_MODEL=dotenv-model",
                        "OUROBOROS_LLM_PROVIDER=dotenv_provider",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {key: "" for key in llm_env_keys}, clear=False):
                for key in llm_env_keys:
                    os.environ.pop(key, None)
                config = self._load_llm_config(env_file=env_file)

        self.assertEqual(config.api_key, "dotenv-api-key")
        self.assertEqual(config.base_url, "https://dotenv-llm.example.test/v1")
        self.assertEqual(config.model, "dotenv-model")
        self.assertEqual(config.provider_name, "dotenv_provider")

    def test_rate_limit_is_deterministic_and_resets_by_window(self) -> None:
        clock = MutableClock()
        gateway = self._mock_gateway(max_requests=2, window_seconds=10.0, clock=clock)

        gateway.complete(llm_request(request_id="llm_req_001"))
        gateway.complete(llm_request(request_id="llm_req_002"))
        with self.assertRaisesRegex(SchemaValidationError, "rate_limited"):
            gateway.complete(llm_request(request_id="llm_req_003"))

        clock.now += 10.0
        output = gateway.complete(llm_request(request_id="llm_req_004"))
        self.assertEqual(output["request_id"], "llm_req_004")

    def test_precheck_accepts_json_string_and_does_not_apply_permissions(self) -> None:
        gateway = self._mock_gateway()
        raw_output = json.dumps(
            {
                "schema_version": "v1",
                "request_id": "llm_req_001",
                "agent_id": "agent_a",
                "tick_id": "2024-01-02T14:02:00+08:00",
                "provider": "deterministic_mock",
                "output_schema_ref": "agent_payload.v1",
                "candidates": [
                    {
                        "content": json.dumps(
                            {
                                "schema_version": "v1",
                                "agent_id": "agent_a",
                                "tick_id": "2024-01-02T14:02:00+08:00",
                                "action": {"action_type": "post_forum"},
                            }
                        ),
                        "finish_reason": "stop",
                    }
                ],
            }
        )

        output = gateway.precheck_structured_output(raw_output)

        candidate_content = json.loads(output["candidates"][0]["content"])
        self.assertEqual(candidate_content["action"]["action_type"], "post_forum")

    def test_precheck_rejects_illegal_top_level_and_candidate_fields(self) -> None:
        gateway = self._mock_gateway()
        output = gateway.complete(llm_request())

        with self.assertRaisesRegex(SchemaValidationError, "unknown field"):
            gateway.precheck_structured_output({**output, "other_agent_context": {}})

        bad_candidate = dict(output)
        bad_candidate["candidates"] = [
            {**output["candidates"][0], "permission_granted": True}
        ]
        with self.assertRaisesRegex(SchemaValidationError, "unknown field"):
            gateway.precheck_structured_output(bad_candidate)

    def test_complete_does_not_swallow_or_merge_other_agent_context(self) -> None:
        gateway = self._mock_gateway()
        request = llm_request(
            "agent_a",
            content=(
                "agent_a private context. other_agent_context="
                "{'agent_id': 'agent_b', 'secret': 'must_not_be_merged'}"
            ),
        )

        output = gateway.complete(request)

        self.assertEqual(output["agent_id"], "agent_a")
        self.assertNotIn("agent_b", json.dumps(output, sort_keys=True))
        self.assertNotIn("must_not_be_merged", json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
