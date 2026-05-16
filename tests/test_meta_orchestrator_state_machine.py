from __future__ import annotations

import unittest

from Ouroboros.core.orchestrator import (
    META_ORCHESTRATOR_TICK_SEQUENCE,
    MetaOrchestratorStateMachine,
)
from Ouroboros.core.schemas import TickState


class MetaOrchestratorStateMachineTests(unittest.TestCase):
    def test_tick_sequence_matches_contract_order(self) -> None:
        self.assertEqual(
            META_ORCHESTRATOR_TICK_SEQUENCE,
            (
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
            ),
        )

    def test_empty_state_machine_advances_without_side_effects(self) -> None:
        machine = MetaOrchestratorStateMachine()

        transition = machine.advance()

        self.assertEqual(transition.current, TickState.INIT_TICK)
        self.assertEqual(transition.next_state, TickState.RELEASE_FACTS)
        self.assertEqual(machine.current_state, TickState.RELEASE_FACTS)

    def test_run_tick_is_explicitly_unimplemented(self) -> None:
        machine = MetaOrchestratorStateMachine()

        with self.assertRaises(NotImplementedError):
            machine.run_tick(None)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
