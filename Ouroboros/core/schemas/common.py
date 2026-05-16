"""Common enums and validation helpers for core schemas."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from enum import StrEnum
from typing import Any, Iterable, Mapping, TypeVar


SCHEMA_VERSION = "v1"


class SchemaValidationError(ValueError):
    """Raised when a payload violates a documented schema contract."""


class InternalVisibility(StrEnum):
    PUBLIC = "public"
    AGENT_PRIVATE = "agent_private"
    FRONTEND_ONLY = "frontend_only"
    CONTROL_ONLY = "control_only"


class WebVisibility(StrEnum):
    PUBLIC = "public"
    AGENT_PRIVATE_SNAPSHOT = "agent_private_snapshot"
    FRONTEND_ONLY = "frontend_only"
    CONTROL_ONLY_VIEW = "control_only_view"


INTERNAL_TO_WEB_VISIBILITY: dict[InternalVisibility, WebVisibility] = {
    InternalVisibility.PUBLIC: WebVisibility.PUBLIC,
    InternalVisibility.AGENT_PRIVATE: WebVisibility.AGENT_PRIVATE_SNAPSHOT,
    InternalVisibility.FRONTEND_ONLY: WebVisibility.FRONTEND_ONLY,
    InternalVisibility.CONTROL_ONLY: WebVisibility.CONTROL_ONLY_VIEW,
}


def map_internal_visibility_to_web(visibility: InternalVisibility | str) -> WebVisibility:
    """Map internal event visibility to the Web API visibility enum."""

    internal_visibility = coerce_enum(InternalVisibility, visibility, "visibility")
    return INTERNAL_TO_WEB_VISIBILITY[internal_visibility]


@dataclass(frozen=True)
class CommonEventHeader:
    """Common internal cross-module event header.

    Defined by docs/internal_contracts/module_interface_registry.md.
    """

    schema_version: str
    event_id: str
    tick_id: str
    trace_id: str
    visibility: InternalVisibility

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CommonEventHeader":
        data = require_mapping(data, "CommonEventHeader")
        ensure_schema_version(data)
        return cls(
            schema_version=SCHEMA_VERSION,
            event_id=require_non_empty_str(data.get("event_id"), "event_id"),
            tick_id=require_non_empty_str(data.get("tick_id"), "tick_id"),
            trace_id=require_non_empty_str(data.get("trace_id"), "trace_id"),
            visibility=coerce_enum(InternalVisibility, data.get("visibility"), "visibility"),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


class AgentType(StrEnum):
    MUTUAL_FUND = "mutual_fund"
    HOT_MONEY = "hot_money"
    QUANT_ALGO = "quant_algo"
    RETAIL = "retail"
    NATIONAL_TEAM = "national_team"


class TickState(StrEnum):
    INIT_TICK = "INIT_TICK"
    RELEASE_FACTS = "RELEASE_FACTS"
    PUBLISH_MARKET_VIEW = "PUBLISH_MARKET_VIEW"
    AGENT_STEP = "AGENT_STEP"
    BARRIER_WAIT = "BARRIER_WAIT"
    PAYLOAD_SPLIT = "PAYLOAD_SPLIT"
    MATCH_AND_CLEAR = "MATCH_AND_CLEAR"
    RISK_AND_LIFECYCLE = "RISK_AND_LIFECYCLE"
    REFEREE_PUBLICATION = "REFEREE_PUBLICATION"
    COMMIT_TICK = "COMMIT_TICK"


class SessionStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class RunMode(StrEnum):
    STEP = "step"
    CONTINUOUS = "continuous"


class LifecycleState(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    MARGIN_CALL = "margin_call"
    LIQUIDATING = "liquidating"
    TERMINATED = "terminated"


class RiskState(StrEnum):
    NORMAL = "normal"
    WARNING = "warning"
    MARGIN_CALL = "margin_call"
    LIQUIDATING = "liquidating"
    TERMINATED = "terminated"


class OrderActionType(StrEnum):
    BUY = "buy"
    SELL = "sell"
    CANCEL = "cancel"
    HOLD = "hold"
    POST_FORUM = "post_forum"


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    LIMIT = "limit"
    MARKET = "market"


class TimeInForce(StrEnum):
    DAY = "day"
    IOC = "ioc"


class OrderKind(StrEnum):
    NORMAL = "normal"
    FORCED_LIQUIDATION = "forced_liquidation"


class LimitState(StrEnum):
    NORMAL = "normal"
    LIMIT_UP = "limit_up"
    LIMIT_DOWN = "limit_down"
    HALTED = "halted"


class Stance(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class Sentiment(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TapeAlertType(StrEnum):
    LARGE_SELL_PRESSURE = "large_sell_pressure"
    LARGE_BUY_PRESSURE = "large_buy_pressure"
    LIMIT_UP_PRESSURE = "limit_up_pressure"
    LIMIT_DOWN_PRESSURE = "limit_down_pressure"
    LIQUIDITY_VACUUM = "liquidity_vacuum"
    VOLUME_SPIKE = "volume_spike"


class SourceType(StrEnum):
    ANNOUNCEMENT = "announcement"
    FINANCIAL_REPORT = "financial_report"
    REGULATORY_NOTICE = "regulatory_notice"
    MACRO = "macro"
    NEWS = "news"
    HISTORICAL_DRAGON_TIGER = "historical_dragon_tiger"
    INITIAL_MARKET_SEED = "initial_market_seed"


class CausalStepType(StrEnum):
    OFFICIAL_NEWS = "official_news"
    PUBLIC_MESSAGE = "public_message"
    TAPE_ALERT = "tape_alert"
    BELIEF_SHIFT = "belief_shift"
    ORDER_FLOW = "order_flow"
    PRICE_MOVE = "price_move"
    RISK_EVENT = "risk_event"
    END_OF_DAY_DISCLOSURE = "end_of_day_disclosure"


class ErrorCode(StrEnum):
    BAD_REQUEST = "BAD_REQUEST"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    SESSION_STATE_CONFLICT = "SESSION_STATE_CONFLICT"
    SCHEMA_VERSION_UNSUPPORTED = "SCHEMA_VERSION_UNSUPPORTED"
    RATE_LIMITED = "RATE_LIMITED"
    ORCHESTRATOR_BUSY = "ORCHESTRATOR_BUSY"
    SNAPSHOT_REQUIRED = "SNAPSHOT_REQUIRED"
    WS_BACKPRESSURE = "WS_BACKPRESSURE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


PRIVATE_FIELD_NAMES = frozenset(
    {
        "thought",
        "belief_shift",
        "reason",
        "order_reason",
        "private_memory",
        "memory_update",
        "prompt",
        "raw_payload",
        "expected_fill",
        "new_cash",
        "new_position",
    }
)

PUBLIC_MARKET_FORBIDDEN_FIELD_NAMES = PRIVATE_FIELD_NAMES | frozenset(
    {
        "agent_id",
        "client_order_id",
        "buy_order_id",
        "sell_order_id",
        "order_id",
        "author_private_id",
    }
)


EnumT = TypeVar("EnumT", bound=StrEnum)


def coerce_enum(enum_type: type[EnumT], value: Any, field_name: str) -> EnumT:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except ValueError as exc:
        allowed = ", ".join(member.value for member in enum_type)
        raise SchemaValidationError(
            f"{field_name} must be one of: {allowed}; got {value!r}"
        ) from exc


def require_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SchemaValidationError(f"{field_name} must be an object")
    return value


def require_keys(data: Mapping[str, Any], keys: Iterable[str], schema_name: str) -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        raise SchemaValidationError(
            f"{schema_name} missing required field(s): {', '.join(missing)}"
        )


def reject_unknown_keys(
    data: Mapping[str, Any], allowed_keys: Iterable[str], schema_name: str
) -> None:
    allowed = set(allowed_keys)
    unknown = sorted(str(key) for key in data.keys() if key not in allowed)
    if unknown:
        raise SchemaValidationError(
            f"{schema_name} has unknown field(s): {', '.join(unknown)}"
        )


def ensure_schema_version(data: Mapping[str, Any]) -> None:
    if data.get("schema_version") != SCHEMA_VERSION:
        raise SchemaValidationError(
            f"schema_version must be {SCHEMA_VERSION!r}; got {data.get('schema_version')!r}"
        )


def require_non_empty_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchemaValidationError(f"{field_name} must be a non-empty string")
    return value


def optional_str(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return require_non_empty_str(value, field_name)


def require_int(value: Any, field_name: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SchemaValidationError(f"{field_name} must be an integer")
    if minimum is not None and value < minimum:
        raise SchemaValidationError(f"{field_name} must be >= {minimum}")
    return value


def require_number(value: Any, field_name: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SchemaValidationError(f"{field_name} must be a number")
    number = float(value)
    if minimum is not None and number < minimum:
        raise SchemaValidationError(f"{field_name} must be >= {minimum}")
    return number


def require_str_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise SchemaValidationError(f"{field_name} must be a list")
    return [require_non_empty_str(item, f"{field_name}[]") for item in value]


def require_str_dict(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SchemaValidationError(f"{field_name} must be an object")
    result: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            raise SchemaValidationError(f"{field_name} keys must be non-empty strings")
        result[key] = item
    return result


def require_int_map(value: Any, field_name: str) -> dict[str, int]:
    data = require_str_dict(value, field_name)
    return {key: require_int(item, f"{field_name}.{key}", minimum=0) for key, item in data.items()}


def find_forbidden_key(value: Any, forbidden: set[str] | frozenset[str]) -> str | None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str) and key in forbidden:
                return key
            nested = find_forbidden_key(item, forbidden)
            if nested:
                return nested
    elif isinstance(value, list):
        for item in value:
            nested = find_forbidden_key(item, forbidden)
            if nested:
                return nested
    return None


def ensure_no_forbidden_keys(
    value: Any, forbidden: set[str] | frozenset[str], schema_name: str
) -> None:
    key = find_forbidden_key(value, forbidden)
    if key:
        raise SchemaValidationError(f"{schema_name} must not contain private field {key!r}")


def to_plain_data(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value):
        return {
            key: to_plain_data(item)
            for key, item in asdict(value).items()
            if item is not None
        }
    if isinstance(value, Mapping):
        return {key: to_plain_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_plain_data(item) for item in value]
    if isinstance(value, tuple):
        return [to_plain_data(item) for item in value]
    return value
