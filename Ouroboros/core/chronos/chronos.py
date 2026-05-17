"""Chronos Layer 0 implementation.

Chronos owns historical facts and releases only the slice made visible by the
Meta-Orchestrator's current tick. It does not create ticks, advance sessions, or
publish initial market seeds to Agent-visible channels.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Protocol

from Ouroboros.core.schemas import (
    CreateSessionCommand,
    InitialMarketSeed,
    InternalVisibility,
    Level2Book,
    OfficialNewsEvent,
    ReleaseFactsCommand,
    ReleaseFactsResult,
    SCHEMA_VERSION,
    SchemaValidationError,
    SourceType,
)
from Ouroboros.core.schemas.common import (
    coerce_enum,
    require_int,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    to_plain_data,
)


CHRONOS_MODE_ENV = "OUROBOROS_CHRONOS_MODE"
CHRONOS_MODE_IN_MEMORY = "in_memory"
CHRONOS_MODE_DEMO = "demo"
CHRONOS_MODE_EXTERNAL = "external"
CHRONOS_MODE_REAL = "real"
CHRONOS_MODES = frozenset(
    {
        CHRONOS_MODE_IN_MEMORY,
        CHRONOS_MODE_DEMO,
        CHRONOS_MODE_EXTERNAL,
        CHRONOS_MODE_REAL,
    }
)
_DEMO_INITIAL_MARKET_SEEDS: dict[str, dict[str, Any]] = {
    "demo_stock": {
        "schema_version": SCHEMA_VERSION,
        "seed_id": "seed_demo_stock",
        "symbol": "demo_stock",
        "previous_close": 10.0,
        "limit_up": 11.0,
        "limit_down": 9.0,
        "initial_l2_snapshot": {
            "bids": [["9.99", 1000], ["9.98", 1200]],
            "asks": [["10.01", 1000], ["10.02", 1200]],
        },
    }
}


class ChronosConfigurationError(SchemaValidationError):
    """Raised when Chronos runtime mode cannot be wired safely."""


@dataclass(frozen=True)
class ChronosFact:
    """A full Layer 0 historical fact record.

    This is internal Chronos data. Agent-facing releases are converted to
    `OfficialNewsEvent`, and retrieval returns sanitized `ChronosSearchResult`
    records only.
    """

    fact_id: str
    symbol: str
    fact_time: str
    source_type: SourceType
    source_name: str
    title: str
    summary: str
    confidence: str
    permission_tags: list[str]
    event_id: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ChronosFact":
        data = require_mapping(data, "ChronosFact")
        return cls(
            fact_id=require_non_empty_str(data.get("fact_id"), "fact_id"),
            symbol=require_non_empty_str(data.get("symbol"), "symbol"),
            fact_time=require_non_empty_str(data.get("fact_time"), "fact_time"),
            source_type=coerce_enum(SourceType, data.get("source_type"), "source_type"),
            source_name=require_non_empty_str(data.get("source_name"), "source_name"),
            title=require_non_empty_str(data.get("title"), "title"),
            summary=require_non_empty_str(data.get("summary"), "summary"),
            confidence=require_non_empty_str(data.get("confidence"), "confidence"),
            permission_tags=require_str_list(
                data.get("permission_tags", []), "permission_tags"
            ),
            event_id=(
                require_non_empty_str(data["event_id"], "event_id")
                if data.get("event_id") is not None
                else None
            ),
        )

    def to_official_news_event(
        self, *, tick_id: str, trace_id: str, created_at: str
    ) -> OfficialNewsEvent:
        return OfficialNewsEvent.from_dict(
            {
                "schema_version": SCHEMA_VERSION,
                "event_id": self.event_id or self.fact_id,
                "tick_id": tick_id,
                "trace_id": trace_id,
                "producer": "chronos",
                "visibility": InternalVisibility.PUBLIC.value,
                "created_at": created_at,
                "symbol": self.symbol,
                "fact_time": self.fact_time,
                "source_type": self.source_type.value,
                "source_name": self.source_name,
                "fact_id": self.fact_id,
                "title": self.title,
                "summary": self.summary,
                "confidence": self.confidence,
                "permission_tags": self.permission_tags,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


@dataclass(frozen=True)
class ChronosSearchResult:
    fact_id: str
    summary: str
    source_type: SourceType
    fact_time: str

    def to_dict(self) -> dict[str, Any]:
        return to_plain_data(self)


class ChronosPublisher(Protocol):
    def publish_official_news(self, event: OfficialNewsEvent) -> None:
        """Publish an Official_News event to the bus implementation."""


@dataclass
class InMemoryOfficialNewsPublisher:
    """Test-friendly publisher that records released Official_News events."""

    published_events: list[OfficialNewsEvent] = field(default_factory=list)

    def publish_official_news(self, event: OfficialNewsEvent) -> None:
        self.published_events.append(event)


@dataclass
class InMemoryChronosRepository:
    """Compatibility/test Chronos repository backed only by caller-provided data.

    This repository is for unit tests and local demo runs. It is not a real
    Chronos Data source and does not imply historical news, filings, market
    data, dragon-tiger lists, or vector retrieval are available.
    """

    facts: list[ChronosFact] = field(default_factory=list)
    initial_market_seeds: dict[str, InitialMarketSeed] = field(default_factory=dict)

    @classmethod
    def from_dicts(
        cls,
        *,
        facts: list[Mapping[str, Any]] | None = None,
        initial_market_seeds: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> "InMemoryChronosRepository":
        return cls(
            facts=[ChronosFact.from_dict(item) for item in (facts or [])],
            initial_market_seeds={
                symbol: InitialMarketSeed.from_dict(seed)
                for symbol, seed in (initial_market_seeds or {}).items()
            },
        )

    def facts_in_release_window(
        self, *, symbol: str, from_time: datetime, to_time: datetime
    ) -> list[ChronosFact]:
        return [
            fact
            for fact in self.facts
            if fact.symbol == symbol
            and from_time <= _parse_iso_datetime(fact.fact_time, "fact_time") <= to_time
        ]

    def count_future_facts(self, *, symbol: str, tick_time: datetime) -> int:
        return sum(
            1
            for fact in self.facts
            if fact.symbol == symbol
            and _parse_iso_datetime(fact.fact_time, "fact_time") > tick_time
        )

    def search_visible_facts(
        self,
        *,
        tick_time: datetime,
        query: str,
        limit: int,
        symbol: str | None = None,
    ) -> list[ChronosFact]:
        query_text = query.casefold()
        matches = [
            fact
            for fact in self.facts
            if (symbol is None or fact.symbol == symbol)
            and _parse_iso_datetime(fact.fact_time, "fact_time") <= tick_time
            and _matches_query(fact, query_text)
        ]
        matches.sort(key=lambda fact: _parse_iso_datetime(fact.fact_time, "fact_time"), reverse=True)
        return matches[:limit]

    def get_initial_market_seed(self, symbol: str) -> InitialMarketSeed:
        try:
            return self.initial_market_seeds[symbol]
        except KeyError as exc:
            raise SchemaValidationError(f"initial market seed not found for symbol {symbol!r}") from exc


@dataclass
class Chronos:
    """Layer 0 facade called by Meta-Orchestrator."""

    repository: InMemoryChronosRepository
    publisher: ChronosPublisher

    def release_facts(
        self, command: ReleaseFactsCommand | Mapping[str, Any]
    ) -> ReleaseFactsResult:
        command = _coerce_release_command(command)
        tick_time = _parse_iso_datetime(command.tick_id, "tick_id")
        window_from = _parse_iso_datetime(command.release_window.from_tick, "release_window.from")
        window_to = _parse_iso_datetime(command.release_window.to_tick, "release_window.to")

        if window_to > tick_time:
            raise SchemaValidationError("release_window.to must not be later than tick_id")
        if window_from > window_to:
            raise SchemaValidationError("release_window.from must not be later than release_window.to")

        facts = self.repository.facts_in_release_window(
            symbol=command.symbol,
            from_time=window_from,
            to_time=window_to,
        )
        published_event_ids: list[str] = []
        for fact in facts:
            event = fact.to_official_news_event(
                tick_id=command.tick_id,
                trace_id=command.trace_id,
                created_at=command.tick_id,
            )
            self.publisher.publish_official_news(event)
            published_event_ids.append(event.event_id)

        return ReleaseFactsResult(
            schema_version=SCHEMA_VERSION,
            command_id=command.command_id,
            tick_id=command.tick_id,
            status="ok",
            published_event_ids=published_event_ids,
            withheld_future_count=self.repository.count_future_facts(
                symbol=command.symbol, tick_time=tick_time
            ),
        )

    def build_initial_market_seed(
        self, session_config: CreateSessionCommand | Mapping[str, Any]
    ) -> InitialMarketSeed:
        config = _coerce_session_config(session_config)
        return self.repository.get_initial_market_seed(config.symbol)

    def search_visible_events(
        self,
        *,
        tick_id: str,
        query: str,
        limit: int = 10,
        symbol: str | None = None,
    ) -> list[ChronosSearchResult]:
        tick_time = _parse_iso_datetime(tick_id, "tick_id")
        query = require_non_empty_str(query, "query")
        limit = require_int(limit, "limit", minimum=1)
        if symbol is not None:
            symbol = require_non_empty_str(symbol, "symbol")

        return [
            ChronosSearchResult(
                fact_id=fact.fact_id,
                summary=fact.summary,
                source_type=fact.source_type,
                fact_time=fact.fact_time,
            )
            for fact in self.repository.search_visible_facts(
                tick_time=tick_time,
                query=query,
                limit=limit,
                symbol=symbol,
            )
        ]


def _coerce_release_command(
    command: ReleaseFactsCommand | Mapping[str, Any],
) -> ReleaseFactsCommand:
    if isinstance(command, ReleaseFactsCommand):
        return command
    return ReleaseFactsCommand.from_dict(command)


def _coerce_session_config(
    session_config: CreateSessionCommand | Mapping[str, Any],
) -> CreateSessionCommand:
    if isinstance(session_config, CreateSessionCommand):
        return session_config
    return CreateSessionCommand.from_dict(session_config)


def chronos_mode_from_env(environ: Mapping[str, str] | None = None) -> str:
    source = environ if environ is not None else os.environ
    mode = (
        source.get(CHRONOS_MODE_ENV, CHRONOS_MODE_IN_MEMORY).strip().lower()
        or CHRONOS_MODE_IN_MEMORY
    )
    if mode not in CHRONOS_MODES:
        allowed = ", ".join(sorted(CHRONOS_MODES))
        raise ChronosConfigurationError(f"{CHRONOS_MODE_ENV} must be one of: {allowed}")
    return mode


def create_chronos_repository(
    *,
    mode: str | None = None,
    environ: Mapping[str, str] | None = None,
    initial_market_seeds: Mapping[str, Mapping[str, Any]] | None = None,
    facts: list[Mapping[str, Any]] | None = None,
) -> InMemoryChronosRepository:
    """Create the configured Chronos repository implementation.

    ``in_memory`` and ``demo`` are explicit local/test modes. ``real`` and
    ``external`` fail fast until a production Chronos adapter exists.
    """

    chronos_mode = chronos_mode_from_env(environ) if mode is None else _normalize_chronos_mode(mode)
    if chronos_mode in {CHRONOS_MODE_IN_MEMORY, CHRONOS_MODE_DEMO}:
        seed_source = initial_market_seeds
        if seed_source is None and chronos_mode == CHRONOS_MODE_DEMO:
            seed_source = _DEMO_INITIAL_MARKET_SEEDS
        return InMemoryChronosRepository.from_dicts(
            facts=facts,
            initial_market_seeds=seed_source,
        )
    if chronos_mode in {CHRONOS_MODE_EXTERNAL, CHRONOS_MODE_REAL}:
        raise ChronosConfigurationError(
            f"{CHRONOS_MODE_ENV}={chronos_mode} requires a real Chronos repository "
            "adapter, but this repository currently provides only the in-memory "
            f"demo/test repository; set {CHRONOS_MODE_ENV}=in_memory or demo for "
            "local tests or demos."
        )
    raise ChronosConfigurationError(f"unsupported Chronos mode: {chronos_mode}")


def _normalize_chronos_mode(mode: str | None) -> str:
    normalized = (mode or CHRONOS_MODE_IN_MEMORY).strip().lower() or CHRONOS_MODE_IN_MEMORY
    if normalized not in CHRONOS_MODES:
        allowed = ", ".join(sorted(CHRONOS_MODES))
        raise ChronosConfigurationError(f"{CHRONOS_MODE_ENV} must be one of: {allowed}")
    return normalized


def _parse_iso_datetime(value: str, field_name: str) -> datetime:
    value = require_non_empty_str(value, field_name)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SchemaValidationError(f"{field_name} must be an ISO 8601 datetime") from exc
    if parsed.tzinfo is None:
        raise SchemaValidationError(f"{field_name} must include timezone information")
    return parsed


def _matches_query(fact: ChronosFact, query: str) -> bool:
    haystack = " ".join(
        [
            fact.fact_id,
            fact.title,
            fact.summary,
            fact.source_name,
            fact.source_type.value,
        ]
    ).casefold()
    return query in haystack
