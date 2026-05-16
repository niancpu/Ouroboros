"""Deterministic in-process event bus used by Layer 2 routing."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Mapping
import copy
import itertools
import time


EventHandler = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class BufferedEvent:
    """A short-lived routed event retained for replay."""

    sequence: int
    channel: str
    payload: dict[str, Any]
    published_at: float
    expires_at: float

    def is_expired(self, now: float) -> bool:
        return now >= self.expires_at


class RedisBus:
    """In-process Redis-like pub/sub and replay buffer.

    The class intentionally has no Redis dependency. It models the small subset
    Layer 2 needs now: deterministic publish order, subscription callbacks, and
    TTL-bound replay buffers.
    """

    def __init__(
        self,
        *,
        default_ttl_seconds: float = 60.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if default_ttl_seconds <= 0:
            raise ValueError("default_ttl_seconds must be > 0")
        self._default_ttl_seconds = float(default_ttl_seconds)
        self._clock = clock or time.monotonic
        self._sequence = itertools.count(1)
        self._buffers: dict[str, list[BufferedEvent]] = defaultdict(list)
        self._subscribers: dict[str, dict[int, EventHandler]] = defaultdict(dict)
        self._subscription_ids = itertools.count(1)

    @staticmethod
    def namespaced_channel(session_id: str, channel: str) -> str:
        if not session_id or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        if not channel or not channel.strip():
            raise ValueError("channel must be a non-empty string")
        return f"{session_id}:{channel}"

    def publish(
        self,
        channel: str,
        payload: Mapping[str, Any],
        *,
        ttl_seconds: float | None = None,
    ) -> BufferedEvent:
        ttl = self._default_ttl_seconds if ttl_seconds is None else float(ttl_seconds)
        if ttl <= 0:
            raise ValueError("ttl_seconds must be > 0")

        self.evict_expired()
        now = self._clock()
        event = BufferedEvent(
            sequence=next(self._sequence),
            channel=channel,
            payload=copy.deepcopy(dict(payload)),
            published_at=now,
            expires_at=now + ttl,
        )
        self._buffers[channel].append(event)

        for handler in tuple(self._subscribers.get(channel, {}).values()):
            handler(copy.deepcopy(event.payload))
        return event

    def subscribe(self, channel: str, handler: EventHandler) -> int:
        subscription_id = next(self._subscription_ids)
        self._subscribers[channel][subscription_id] = handler
        return subscription_id

    def unsubscribe(self, channel: str, subscription_id: int) -> None:
        subscribers = self._subscribers.get(channel)
        if subscribers is None:
            return
        subscribers.pop(subscription_id, None)
        if not subscribers:
            self._subscribers.pop(channel, None)

    def replay(self, channel: str) -> list[dict[str, Any]]:
        self.evict_expired()
        return [copy.deepcopy(event.payload) for event in self._buffers.get(channel, [])]

    def events(self, channel: str) -> list[BufferedEvent]:
        self.evict_expired()
        return list(self._buffers.get(channel, []))

    def evict_expired(self) -> int:
        now = self._clock()
        removed = 0
        for channel in list(self._buffers.keys()):
            retained = [event for event in self._buffers[channel] if not event.is_expired(now)]
            removed += len(self._buffers[channel]) - len(retained)
            if retained:
                self._buffers[channel] = retained
            else:
                self._buffers.pop(channel, None)
        return removed

    def evict_channel(self, channel: str) -> int:
        events = self._buffers.pop(channel, [])
        return len(events)

    def clear(self) -> None:
        self._buffers.clear()
        self._subscribers.clear()
