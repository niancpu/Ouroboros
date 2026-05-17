"""Deterministic in-process LLM gateway.

This module owns only model-call plumbing, local rate limiting, and structured
output shape prechecks. Permission decisions, context assembly, and persistence
belong to upstream modules.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from Ouroboros.core.llm.config import (
    LLM_PROVIDER_DETERMINISTIC_MOCK,
    LLM_PROVIDER_OPENAI_COMPATIBLE,
    LLMConfig,
)
from Ouroboros.core.schemas import LLMRequest, SCHEMA_VERSION, SchemaValidationError
from Ouroboros.core.schemas.common import reject_unknown_keys, require_non_empty_str


class LLMConfigurationError(RuntimeError):
    """Raised when a real LLM run is requested without usable provider config."""


class LLMGateway:
    """Deterministic gateway for mock LLM completion tests."""

    _OUTPUT_KEYS = frozenset(
        {
            "schema_version",
            "request_id",
            "agent_id",
            "tick_id",
            "provider",
            "output_schema_ref",
            "candidates",
        }
    )
    _CANDIDATE_KEYS = frozenset({"content", "finish_reason"})
    _FINISH_REASONS = frozenset({"stop", "length"})

    def __init__(
        self,
        *,
        max_requests: int = 60,
        window_seconds: float = 60.0,
        clock: Callable[[], float] | None = None,
        provider_name: str = LLM_PROVIDER_DETERMINISTIC_MOCK,
        config: LLMConfig | None = None,
        require_provider_config: bool = False,
    ) -> None:
        if max_requests < 1:
            raise SchemaValidationError("max_requests must be >= 1")
        if window_seconds <= 0:
            raise SchemaValidationError("window_seconds must be > 0")
        self.config = config or LLMConfig.from_env()
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._clock = clock or time.monotonic
        self._provider_name = (
            provider_name
            if provider_name != LLM_PROVIDER_DETERMINISTIC_MOCK
            else self.config.provider_name
        )
        self._require_provider_config = require_provider_config
        self._window_started_at = self._clock()
        self._used_in_window = 0

    def complete(self, agent_prompt: LLMRequest | Mapping[str, Any]) -> dict[str, Any]:
        """Return one schema-shaped completion for exactly one request."""

        request = self._coerce_request(agent_prompt)
        self._consume_rate_limit()
        self._ensure_provider_ready()
        if self._should_call_provider():
            return self._complete_openai_compatible(request)
        return self.precheck_structured_output(
            {
                "schema_version": SCHEMA_VERSION,
                "request_id": request.request_id,
                "agent_id": request.agent_id,
                "tick_id": request.tick_id,
                "provider": self._provider_name,
                "output_schema_ref": request.output_schema_ref,
                "candidates": [
                    {
                        "content": json.dumps(
                            {
                                "schema_version": SCHEMA_VERSION,
                                "agent_id": request.agent_id,
                                "tick_id": request.tick_id,
                                "action": {"action_type": "hold"},
                                "evidence_refs": [],
                            },
                            ensure_ascii=True,
                            sort_keys=True,
                        ),
                        "finish_reason": "stop",
                    }
                ],
            }
        )

    def precheck_structured_output(self, raw_output: str | Mapping[str, Any]) -> dict[str, Any]:
        """Validate JSON/object shape without applying business permissions."""

        output = self._parse_output(raw_output)
        reject_unknown_keys(output, self._OUTPUT_KEYS, "LLMStructuredOutput")

        if output.get("schema_version") != SCHEMA_VERSION:
            raise SchemaValidationError(
                f"schema_version must be {SCHEMA_VERSION!r}; got {output.get('schema_version')!r}"
            )
        require_non_empty_str(output.get("request_id"), "request_id")
        require_non_empty_str(output.get("agent_id"), "agent_id")
        require_non_empty_str(output.get("tick_id"), "tick_id")
        require_non_empty_str(output.get("provider"), "provider")
        require_non_empty_str(output.get("output_schema_ref"), "output_schema_ref")

        candidates = output.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise SchemaValidationError("candidates must be a non-empty list")
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, Mapping):
                raise SchemaValidationError(f"candidates[{index}] must be an object")
            reject_unknown_keys(candidate, self._CANDIDATE_KEYS, f"candidates[{index}]")
            content = require_non_empty_str(candidate.get("content"), f"candidates[{index}].content")
            try:
                json.loads(content)
            except json.JSONDecodeError as exc:
                raise SchemaValidationError(
                    f"candidates[{index}].content must be JSON"
                ) from exc
            finish_reason = require_non_empty_str(
                candidate.get("finish_reason"), f"candidates[{index}].finish_reason"
            )
            if finish_reason not in self._FINISH_REASONS:
                allowed = ", ".join(sorted(self._FINISH_REASONS))
                raise SchemaValidationError(
                    f"candidates[{index}].finish_reason must be one of: {allowed}"
                )

        return dict(output)

    def validate_provider_config(self) -> None:
        """Raise a clear error when strict real-provider config is incomplete."""

        self._ensure_provider_ready()

    def _consume_rate_limit(self) -> None:
        now = self._clock()
        if now - self._window_started_at >= self._window_seconds:
            self._window_started_at = now
            self._used_in_window = 0
        if self._used_in_window >= self._max_requests:
            raise SchemaValidationError("rate_limited")
        self._used_in_window += 1

    def _should_call_provider(self) -> bool:
        return (
            self._provider_name == LLM_PROVIDER_OPENAI_COMPATIBLE
            and bool(self.config.api_key)
            and bool(self.config.base_url)
        )

    def _ensure_provider_ready(self) -> None:
        if not self._require_provider_config:
            return
        if self._provider_name != LLM_PROVIDER_OPENAI_COMPATIBLE:
            raise LLMConfigurationError(
                "llm_provider_not_configured: deterministic_mock is mock/test only; "
                "set OUROBOROS_AGENT_MODE=mock_hold for mock agent runs or "
                "OUROBOROS_LLM_PROVIDER=openai_compatible for llm agent mode"
            )
        missing = []
        if not self.config.api_key:
            missing.append("OUROBOROS_LLM_API_KEY")
        if not self.config.base_url:
            missing.append("OUROBOROS_LLM_BASE_URL")
        if missing:
            raise LLMConfigurationError(
                "llm_provider_not_configured: missing " + ", ".join(missing)
            )

    def _complete_openai_compatible(self, request: LLMRequest) -> dict[str, Any]:
        endpoint = self.config.base_url.rstrip("/") + "/chat/completions"
        body = {
            "model": self.config.model,
            "messages": [message.__dict__ for message in request.messages],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        http_request = Request(
            endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(http_request, timeout=request.deadline_ms / 1000) as response:
                raw_body = response.read().decode("utf-8")
        except HTTPError as exc:
            raise SchemaValidationError(f"llm_provider_error:{exc.code}") from exc
        except URLError as exc:
            raise SchemaValidationError("llm_provider_error") from exc
        except TimeoutError as exc:
            raise SchemaValidationError("llm_provider_timeout") from exc

        try:
            provider_output = json.loads(raw_body)
            content = provider_output["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise SchemaValidationError("llm_provider_invalid_response") from exc
        if not isinstance(content, str) or not content.strip():
            raise SchemaValidationError("llm_provider_invalid_response")

        return self.precheck_structured_output(
            {
                "schema_version": SCHEMA_VERSION,
                "request_id": request.request_id,
                "agent_id": request.agent_id,
                "tick_id": request.tick_id,
                "provider": self._provider_name,
                "output_schema_ref": request.output_schema_ref,
                "candidates": [
                    {
                        "content": content,
                        "finish_reason": "stop",
                    }
                ],
            }
        )

    def _coerce_request(self, value: LLMRequest | Mapping[str, Any]) -> LLMRequest:
        if isinstance(value, LLMRequest):
            return value
        return LLMRequest.from_dict(value)

    def _parse_output(self, value: str | Mapping[str, Any]) -> Mapping[str, Any]:
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError as exc:
                raise SchemaValidationError("LLMStructuredOutput must be JSON") from exc
            if not isinstance(parsed, Mapping):
                raise SchemaValidationError("LLMStructuredOutput must be an object")
            return parsed
        if isinstance(value, Mapping):
            return value
        raise SchemaValidationError("LLMStructuredOutput must be JSON or an object")
