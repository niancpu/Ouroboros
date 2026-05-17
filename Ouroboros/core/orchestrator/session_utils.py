"""Pure helpers shared by the session runner."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta

from Ouroboros.core.schemas import CreateSessionCommand, SchemaValidationError
from Ouroboros.core.schemas.common import require_non_empty_str


def next_tick_id(tick_id: str, tick_interval: str) -> str:
    current = parse_datetime(tick_id, "tick_id")
    return (current + parse_interval(tick_interval)).isoformat()


def previous_tick_id(tick_id: str, tick_interval: str) -> str:
    current = parse_datetime(tick_id, "tick_id")
    return (current - parse_interval(tick_interval)).isoformat()


def tick_after_end(tick_id: str, end_tick_id: str) -> bool:
    return parse_datetime(tick_id, "tick_id") > parse_datetime(end_tick_id, "end_tick_id")


def is_final_tick(tick_id: str, end_tick_id: str) -> bool:
    return parse_datetime(tick_id, "tick_id") >= parse_datetime(end_tick_id, "end_tick_id")


def parse_datetime(value: str, field_name: str) -> datetime:
    value = require_non_empty_str(value, field_name)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SchemaValidationError(f"{field_name} must be an ISO 8601 datetime") from exc
    if parsed.tzinfo is None:
        raise SchemaValidationError(f"{field_name} must include timezone information")
    return parsed


def parse_interval(value: str) -> timedelta:
    value = require_non_empty_str(value, "tick_interval").strip().lower()
    unit = value[-1]
    try:
        amount = int(value[:-1])
    except ValueError as exc:
        raise SchemaValidationError("tick_interval must look like 5m, 1h, or 30s") from exc
    if amount <= 0:
        raise SchemaValidationError("tick_interval amount must be > 0")
    if unit == "s":
        return timedelta(seconds=amount)
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    raise SchemaValidationError("tick_interval unit must be s, m, or h")


def frontend_safe_refs(refs: Iterable[str], prefixes: tuple[str, ...]) -> list[str]:
    return [ref for ref in refs if ref.startswith(prefixes)]


def position_value(
    positions: Mapping[str, int],
    mark_prices: Mapping[str, float],
) -> float:
    return sum(float(quantity) * float(mark_prices.get(symbol, 0.0)) for symbol, quantity in positions.items())


def default_session_id(command: CreateSessionCommand, sequence: int, *, prefix: str) -> str:
    return f"{prefix}_{stable_id(command.scenario_id)}_{sequence:06d}"


def stable_id(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in str(value)).strip("_") or "unknown"
