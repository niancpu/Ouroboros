"""Configuration loading for the LLM gateway."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


_ENV_KEYS = {
    "api_key": "OUROBOROS_LLM_API_KEY",
    "base_url": "OUROBOROS_LLM_BASE_URL",
    "model": "OUROBOROS_LLM_MODEL",
    "provider_name": "OUROBOROS_LLM_PROVIDER",
}


@dataclass(frozen=True)
class LLMConfig:
    """Provider connection settings for LLMGateway."""

    api_key: str = ""
    base_url: str = ""
    model: str = "deterministic-mock"
    provider_name: str = "deterministic_mock"

    @classmethod
    def from_env(
        cls,
        *,
        env_path: str | Path = ".env",
        env_file: str | Path | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> "LLMConfig":
        """Load LLM config from process env with a UTF-8 .env fallback."""

        dotenv_path = Path(env_file if env_file is not None else env_path)
        source = dict(_read_dotenv(dotenv_path))
        source.update(dict(environ if environ is not None else os.environ))

        return cls(
            api_key=source.get(_ENV_KEYS["api_key"], "").strip(),
            base_url=source.get(_ENV_KEYS["base_url"], "").strip(),
            model=source.get(_ENV_KEYS["model"], "deterministic-mock").strip()
            or "deterministic-mock",
            provider_name=source.get(
                _ENV_KEYS["provider_name"], "deterministic_mock"
            ).strip()
            or "deterministic_mock",
        )


def _read_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            if not key:
                continue
            values[key] = _clean_env_value(value.strip())
    return values


def _clean_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
