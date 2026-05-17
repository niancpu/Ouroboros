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

from Ouroboros.core.llm.config import LLMConfig
from Ouroboros.core.schemas import LLMRequest, SCHEMA_VERSION, SchemaValidationError
from Ouroboros.core.schemas.common import reject_unknown_keys, require_non_empty_str


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
        provider_name: str = "deterministic_mock",
        config: LLMConfig | None = None,
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
            provider_name if provider_name != "deterministic_mock" else self.config.provider_name
        )
        self._window_started_at = self._clock()
        self._used_in_window = 0

    def complete(self, agent_prompt: LLMRequest | Mapping[str, Any]) -> dict[str, Any]:
        """Return one schema-shaped mock completion for exactly one request."""

        request = self._coerce_request(agent_prompt)
        self._consume_rate_limit()
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

    def _consume_rate_limit(self) -> None:
        now = self._clock()
        if now - self._window_started_at >= self._window_seconds:
            self._window_started_at = now
            self._used_in_window = 0
        if self._used_in_window >= self._max_requests:
            raise SchemaValidationError("rate_limited")
        self._used_in_window += 1

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
