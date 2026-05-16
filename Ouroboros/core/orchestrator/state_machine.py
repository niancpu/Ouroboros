"""Empty MetaOrchestrator Tick state-machine interface."""

from __future__ import annotations

from dataclasses import dataclass

from Ouroboros.core.schemas import RunTickCommand, RunTickResult, TickState


META_ORCHESTRATOR_TICK_SEQUENCE: tuple[TickState, ...] = (
    TickState.INIT_TICK,
    TickState.RELEASE_FACTS,
    TickState.PUBLISH_MARKET_VIEW,
    TickState.AGENT_STEP,
    TickState.BARRIER_WAIT,
    TickState.PAYLOAD_SPLIT,
    TickState.MATCH_AND_CLEAR,
    TickState.RISK_AND_LIFECYCLE,
    TickState.REFEREE_PUBLICATION,
    TickState.COMMIT_TICK,
)


@dataclass(frozen=True)
class TickStateTransition:
    current: TickState
    next_state: TickState | None


class MetaOrchestratorStateMachine:
    """State-machine skeleton for MetaOrchestrator.

    It encodes the documented Tick order only. It does not release facts, call
    Agents, match orders, clear trades, publish events, or commit ledger state.
    """

    def __init__(self, initial_state: TickState = TickState.INIT_TICK) -> None:
        if initial_state not in META_ORCHESTRATOR_TICK_SEQUENCE:
            raise ValueError(f"unknown Tick state: {initial_state!r}")
        self._state = initial_state

    @property
    def current_state(self) -> TickState:
        return self._state

    def transition_for(self, state: TickState | str) -> TickStateTransition:
        current = TickState(state)
        index = META_ORCHESTRATOR_TICK_SEQUENCE.index(current)
        next_state = (
            META_ORCHESTRATOR_TICK_SEQUENCE[index + 1]
            if index + 1 < len(META_ORCHESTRATOR_TICK_SEQUENCE)
            else None
        )
        return TickStateTransition(current=current, next_state=next_state)

    def can_advance(self) -> bool:
        return self.transition_for(self._state).next_state is not None

    def advance(self) -> TickStateTransition:
        transition = self.transition_for(self._state)
        if transition.next_state is None:
            return transition
        self._state = transition.next_state
        return transition

    def reset(self, state: TickState = TickState.INIT_TICK) -> None:
        if state not in META_ORCHESTRATOR_TICK_SEQUENCE:
            raise ValueError(f"unknown Tick state: {state!r}")
        self._state = state

    def run_tick(self, command: RunTickCommand) -> RunTickResult:
        """Placeholder for the real Tick orchestration implementation."""

        raise NotImplementedError(
            "MetaOrchestratorStateMachine.run_tick is an interface placeholder"
        )

