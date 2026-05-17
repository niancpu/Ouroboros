"""Control-plane orchestration interfaces.

This package only exposes the MetaOrchestrator state-machine skeleton. The real
Tick side effects are implemented by Layer 0, Agent Runtime, Layer 3, and
Referee modules.
"""

from .state_machine import (
    META_ORCHESTRATOR_TICK_SEQUENCE,
    MetaOrchestratorStateMachine,
    TickStateTransition,
)

__all__ = [
    "META_ORCHESTRATOR_TICK_SEQUENCE",
    "MetaOrchestratorStateMachine",
    "TickStateTransition",
]
