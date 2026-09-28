from __future__ import annotations

import copy
import random
from dataclasses import dataclass
from typing import Any

import simpy

from backend.simulation.actions import (
    ESCALATE_TO_BED_MANAGER,
    EXPEDITE_BED_CLEANING,
    PRIORITIZE_TRANSPORT,
    REQUEST_ALTERNATIVE_UNIT,
    WAIT,
    get_action_spec,
)
from backend.simulation.models import (
    ActionEvaluation,
    EDOperationalState,
    EpisodeOutcome,
    ResourceState,
    TransferCase,
)


SCENARIO_TYPES = [
    "ICU_BED_CLEANING",
    "TRANSPORT_BOTTLENECK",
    "ALTERNATIVE_UNIT_AVAILABLE",
    "COORDINATION_DEADLOCK",
    "MIXED_BOTTLENECK",
]


@dataclass(frozen=True)
class SimulationConfig:
    """
    Synthetic operational parameters used for controlled experiments.

    These numbers are simulation assumptions, not real hospital
    performance measurements.
    """

    normal_bed_cleaning_time: float = 60.0
    expedited_bed_cleaning_time: float = 25.0

    normal_transport_time: float = 60.0
    prioritized_transport_time: float = 20.0

    normal_coordination_time: float = 35.0
    escalated_coordination_time: float = 12.0

    alternative_unit_time: float = 35.0

    baseline_transfer_time: float = 10.0

    # Severe enough that a coordination deadlock can time out.
    coordination_deadlock_wait: float = 280.0

    max_simulation_time: float = 240.0

    max_jitter: float = 5.0


class EDTransferSimulator:
    """
    Operational ED transfer simulator.

    Models:
        - capacity
        - transport
        - coordination
        - transfer queues
        - interventions

    Does not model:
        - diagnosis
        - medication
        - treatment
    """

    def __init__(
        self,
        config: SimulationConfig | None = None,
        seed: int = 42,
    ) -> None:

        self.config = config or SimulationConfig()
        self.seed = seed

    # ================================================================
    # SCENARIO GENERATION
    # ================================================================

    def create_deadlock_state(
        self,
        *,
        case_id: str = "ED-001",
        scenario_type: str | None = None,
    ) -> EDOperationalState:

        rng = random.Random(self.seed)

        if scenario_type is None:

            scenario_type = SCENARIO_TYPES[
                self.seed % len(SCENARIO_TYPES)
            ]

        if scenario_type not in SCENARIO_TYPES:
            raise ValueError(
                f"Unknown scenario type: {scenario_type}"
            )

        resources = ResourceState()

        bed_blocked = False
        transport_blocked = False
        coordination_blocked = False

        # ------------------------------------------------------------
        # Scenario 1
        # ------------------------------------------------------------

        if scenario_type == "ICU_BED_CLEANING":

            resources.icu_beds_available = 0
            resources.hdu_beds_available = 0
            resources.transport_teams_available = 1
            resources.beds_waiting_cleaning = 1
            resources.transport_queue = 1
            resources.bed_manager_available = True
            resources.senior_coordinator_available = True

            bed_blocked = True
            coordination_blocked = True

        # ------------------------------------------------------------
        # Scenario 2
        # ------------------------------------------------------------

        elif scenario_type == "TRANSPORT_BOTTLENECK":

            resources.icu_beds_available = 1
            resources.hdu_beds_available = 0
            resources.transport_teams_available = 0
            resources.beds_waiting_cleaning = 0
            resources.transport_queue = 3
            resources.bed_manager_available = True
            resources.senior_coordinator_available = True

            transport_blocked = True

        # ------------------------------------------------------------
        # Scenario 3
        # ------------------------------------------------------------

        elif scenario_type == "ALTERNATIVE_UNIT_AVAILABLE":

            resources.icu_beds_available = 0
            resources.hdu_beds_available = 1
            resources.transport_teams_available = 1
            resources.beds_waiting_cleaning = 0
            resources.transport_queue = 1
            resources.bed_manager_available = True
            resources.senior_coordinator_available = True

            bed_blocked = True
            coordination_blocked = True

        # ------------------------------------------------------------
        # Scenario 4
        # ------------------------------------------------------------

        elif scenario_type == "COORDINATION_DEADLOCK":

            resources.icu_beds_available = 1
            resources.hdu_beds_available = 0
            resources.transport_teams_available = 1
            resources.beds_waiting_cleaning = 0
            resources.transport_queue = 1
            resources.bed_manager_available = True

            # Critical coordination bottleneck.
            resources.senior_coordinator_available = False

            coordination_blocked = True

        # ------------------------------------------------------------
        # Scenario 5
        # ------------------------------------------------------------

        elif scenario_type == "MIXED_BOTTLENECK":

            resources.icu_beds_available = 0
            resources.hdu_beds_available = 1
            resources.transport_teams_available = 0
            resources.beds_waiting_cleaning = 1
            resources.transport_queue = 3
            resources.bed_manager_available = True
            resources.senior_coordinator_available = True

            bed_blocked = True
            transport_blocked = True
            coordination_blocked = True

        patients_in_ed = 40 + rng.randint(0, 8)
        boarding_patients = 4 + rng.randint(0, 4)

        transfer_case = TransferCase(
            case_id=case_id,
            destination_unit="ICU",
            ready_for_transfer=True,
            waiting_since=0.0,
            priority=1,
            bed_blocked=bed_blocked,
            transport_blocked=transport_blocked,
            coordination_blocked=coordination_blocked,
        )

        return EDOperationalState(
            current_time=0.0,
            scenario_type=scenario_type,
            patients_in_ed=patients_in_ed,
            boarding_patients=boarding_patients,
            pending_transfers=1,
            unresolved_transfers=1,
            resources=resources,
            transfer_cases=[transfer_case],
            escalation_count=0,
            coordination_attempts=0,
            resolved=False,
            resolution_time=None,
        )

    # ================================================================
    # CONSTRAINT CHECK
    # ================================================================

    def _validate_action(
        self,
        state: EDOperationalState,
        action: str,
    ) -> tuple[bool, str]:

        spec = get_action_spec(action)
        resources = state.resources

        if (
            spec.requires_bed_manager
            and not resources.bed_manager_available
        ):
            return False, "Bed manager is unavailable."

        if action == EXPEDITE_BED_CLEANING:

            if resources.beds_waiting_cleaning <= 0:
                return (
                    False,
                    "No bed is currently waiting for cleaning.",
                )

        if action == REQUEST_ALTERNATIVE_UNIT:

            if resources.hdu_beds_available <= 0:
                return (
                    False,
                    "No alternative HDU capacity is available.",
                )

        if action == PRIORITIZE_TRANSPORT:

            if resources.transport_queue <= 0:
                return (
                    False,
                    "No transport queue is available.",
                )

        return True, ""

    # ================================================================
    # ACTION -> COUNTERFACTUAL PLAN
    # ================================================================

    def _action_plan(
        self,
        state: EDOperationalState,
        action: str,
    ) -> dict[str, Any]:

        config = self.config
        scenario = state.scenario_type

        plan = {
            "bed_time": 0.0,
            "transport_time": 0.0,
            "coordination_time": 0.0,
            "escalations": 0,
            "alternative_destination": False,
        }

        # ------------------------------------------------------------
        # BASELINE SCENARIO
        # ------------------------------------------------------------

        if scenario == "ICU_BED_CLEANING":

            plan["bed_time"] = (
                config.normal_bed_cleaning_time
            )

            plan["transport_time"] = (
                config.baseline_transfer_time
            )

            plan["coordination_time"] = (
                config.normal_coordination_time
                * 0.30
            )

        elif scenario == "TRANSPORT_BOTTLENECK":

            plan["transport_time"] = (
                config.normal_transport_time
            )

            plan["coordination_time"] = (
                config.normal_coordination_time
                * 0.30
            )

        elif scenario == "ALTERNATIVE_UNIT_AVAILABLE":

            plan["transport_time"] = (
                config.baseline_transfer_time
            )

            plan["coordination_time"] = (
                config.normal_coordination_time
            )

        elif scenario == "COORDINATION_DEADLOCK":

            plan["transport_time"] = (
                config.baseline_transfer_time
            )

            plan["coordination_time"] = (
                config.coordination_deadlock_wait
            )

        elif scenario == "MIXED_BOTTLENECK":

            plan["bed_time"] = (
                config.normal_bed_cleaning_time
            )

            plan["transport_time"] = (
                config.normal_transport_time
            )

            plan["coordination_time"] = (
                config.normal_coordination_time
                * 0.43
            )

        # ------------------------------------------------------------
        # ACTION EFFECTS
        # ------------------------------------------------------------

        if action == WAIT:
            pass

        # ------------------------------------------------------------

        elif action == EXPEDITE_BED_CLEANING:

            if scenario in {
                "ICU_BED_CLEANING",
                "MIXED_BOTTLENECK",
            }:

                plan["bed_time"] = (
                    config.expedited_bed_cleaning_time
                )

        # ------------------------------------------------------------

        elif action == PRIORITIZE_TRANSPORT:

            if scenario == "TRANSPORT_BOTTLENECK":

                plan["transport_time"] = (
                    config.prioritized_transport_time
                )

            elif scenario in {
                "ICU_BED_CLEANING",
                "ALTERNATIVE_UNIT_AVAILABLE",
                "COORDINATION_DEADLOCK",
            }:

                # Small benefit when transport is not the primary
                # bottleneck.
                plan["transport_time"] = (
                    config.baseline_transfer_time
                    * 0.50
                )

            elif scenario == "MIXED_BOTTLENECK":

                plan["transport_time"] = (
                    config.prioritized_transport_time
                )

        # ------------------------------------------------------------

        elif action == REQUEST_ALTERNATIVE_UNIT:

            if scenario == "ALTERNATIVE_UNIT_AVAILABLE":

                plan["alternative_destination"] = True

                plan["bed_time"] = (
                    config.alternative_unit_time
                    * 0.45
                )

                plan["transport_time"] = (
                    config.baseline_transfer_time
                )

                plan["coordination_time"] = (
                    config.normal_coordination_time
                    * 0.43
                )

            elif scenario == "MIXED_BOTTLENECK":

                plan["alternative_destination"] = True

                # Bypass the ICU bed bottleneck.
                plan["bed_time"] = (
                    config.alternative_unit_time
                )

                # Alternative placement also gets coordinated
                # transport priority.
                plan["transport_time"] = (
                    config.prioritized_transport_time
                )

                plan["coordination_time"] = (
                    config.normal_coordination_time
                    * 0.43
                )

        # ------------------------------------------------------------

        elif action == ESCALATE_TO_BED_MANAGER:

            plan["escalations"] = 1

            if scenario == "ICU_BED_CLEANING":

                plan["bed_time"] = (
                    config.normal_bed_cleaning_time
                    * 0.83
                )

                plan["transport_time"] = (
                    config.baseline_transfer_time
                )

                plan["coordination_time"] = (
                    config.escalated_coordination_time
                )

            elif scenario == "TRANSPORT_BOTTLENECK":

                # Escalation does NOT magically solve a transport
                # bottleneck.
                plan["transport_time"] = (
                    config.normal_transport_time
                )

                plan["coordination_time"] = (
                    config.escalated_coordination_time
                )

            elif scenario == "ALTERNATIVE_UNIT_AVAILABLE":

                # Escalation attempts to recover the blocked ICU
                # destination instead of using the immediately
                # available alternative.
                plan["bed_time"] = (
                    config.normal_bed_cleaning_time
                    + 15.0
                )

                plan["transport_time"] = (
                    config.baseline_transfer_time
                )

                plan["coordination_time"] = (
                    config.escalated_coordination_time
                )

            elif scenario == "COORDINATION_DEADLOCK":

                plan["transport_time"] = (
                    config.baseline_transfer_time
                )

                plan["coordination_time"] = (
                    config.escalated_coordination_time
                )

            elif scenario == "MIXED_BOTTLENECK":

                plan["bed_time"] = (
                    config.normal_bed_cleaning_time
                    * 0.83
                )

                plan["transport_time"] = (
                    config.normal_transport_time
                    * 0.75
                )

                plan["coordination_time"] = (
                    config.escalated_coordination_time
                )

        else:

            raise ValueError(
                f"Unsupported action: {action}"
            )

        return plan

    # ================================================================
    # SIMULATION
    # ================================================================

    def _run_simulation(
        self,
        initial_state: EDOperationalState,
        action: str,
    ) -> EpisodeOutcome:

        state = copy.deepcopy(initial_state)

        env = simpy.Environment()

        rng = random.Random(self.seed)

        events: list[dict[str, Any]] = []

        feasible, reason = self._validate_action(
            state,
            action,
        )

        case = state.active_case()

        if case is None:

            return EpisodeOutcome(
                case_id="unknown",
                action=action,
                resolved=False,
                resolution_time=None,
                boarding_time=0.0,
                escalation_count=0,
                resource_conflicts=0,
                initial_state=initial_state.snapshot(),
                final_state=state.snapshot(),
                events=[],
            )

        if not feasible:

            return EpisodeOutcome(
                case_id=case.case_id,
                action=action,
                resolved=False,
                resolution_time=None,
                boarding_time=(
                    self.config.max_simulation_time
                ),
                escalation_count=0,
                resource_conflicts=1,
                initial_state=initial_state.snapshot(),
                final_state=state.snapshot(),
                events=[
                    {
                        "time": 0.0,
                        "event": "action_rejected",
                        "action": action,
                        "reason": reason,
                    }
                ],
            )

        plan = self._action_plan(
            state,
            action,
        )

        # An action must have an explicit operational pathway in the
        # simulator. An unsupported/unknown regime must not become an
        # instant successful transfer merely because all simulated
        # durations are zero.
        has_resolution_path = (
            plan["alternative_destination"]
            or plan["bed_time"] > 0
            or plan["transport_time"] > 0
            or plan["coordination_time"] > 0
        )

        if not has_resolution_path:
            return EpisodeOutcome(
                case_id=case.case_id,
                action=action,
                resolved=False,
                resolution_time=None,
                boarding_time=self.config.max_simulation_time,
                escalation_count=plan["escalations"],
                resource_conflicts=1,
                initial_state=initial_state.snapshot(),
                final_state=state.snapshot(),
                events=[
                    {
                        "time": 0.0,
                        "event": "no_resolution_path",
                        "action": action,
                        "scenario_type": state.scenario_type,
                    }
                ],
            )

        state.escalation_count += (
            plan["escalations"]
        )

        state.coordination_attempts += 1

        events.append(
            {
                "time": 0.0,
                "event": "intervention_started",
                "scenario_type": state.scenario_type,
                "action": action,
            }
        )

        jitter = rng.uniform(
            0.0,
            self.config.max_jitter,
        )

        def transfer_process():

            # --------------------------------------------------------
            # Alternative destination
            # --------------------------------------------------------

            if plan["alternative_destination"]:

                yield env.timeout(
                    max(
                        0.0,
                        plan["coordination_time"],
                    )
                )

                events.append(
                    {
                        "time": env.now,
                        "event": "alternative_destination_confirmed",
                    }
                )

            # --------------------------------------------------------
            # Bed
            # --------------------------------------------------------

            if plan["bed_time"] > 0:

                yield env.timeout(
                    plan["bed_time"]
                )

                state.resources.beds_waiting_cleaning = max(
                    0,
                    state.resources.beds_waiting_cleaning - 1,
                )

                if (
                    state.resources.icu_beds_available == 0
                    and not plan["alternative_destination"]
                ):

                    state.resources.icu_beds_available = 1

                events.append(
                    {
                        "time": env.now,
                        "event": "bed_capacity_resolved",
                    }
                )

            # --------------------------------------------------------
            # Coordination
            # --------------------------------------------------------

            if (
                plan["coordination_time"] > 0
                and not plan["alternative_destination"]
            ):

                yield env.timeout(
                    plan["coordination_time"]
                )

                events.append(
                    {
                        "time": env.now,
                        "event": "coordination_completed",
                    }
                )

            # --------------------------------------------------------
            # Transport
            # --------------------------------------------------------

            if plan["transport_time"] > 0:

                yield env.timeout(
                    plan["transport_time"]
                )

                if (
                    state.resources.transport_teams_available
                    <= 0
                ):

                    state.resources.transport_teams_available = 1

                state.resources.transport_queue = max(
                    0,
                    state.resources.transport_queue - 1,
                )

                events.append(
                    {
                        "time": env.now,
                        "event": "transport_completed",
                    }
                )

            # --------------------------------------------------------
            # Final jitter
            # --------------------------------------------------------

            yield env.timeout(
                jitter
            )

            state.current_time = env.now

            state.resolved = True

            state.resolution_time = env.now

            state.unresolved_transfers = max(
                0,
                state.unresolved_transfers - 1,
            )

            state.pending_transfers = max(
                0,
                state.pending_transfers - 1,
            )

            state.boarding_patients = max(
                0,
                state.boarding_patients - 1,
            )

            events.append(
                {
                    "time": env.now,
                    "event": "transfer_resolved",
                    "case_id": case.case_id,
                    "scenario_type": state.scenario_type,
                }
            )

        env.process(
            transfer_process()
        )

        env.run(
            until=self.config.max_simulation_time
        )

        if not state.resolved:

            state.current_time = (
                self.config.max_simulation_time
            )

            events.append(
                {
                    "time": env.now,
                    "event": "simulation_timeout",
                }
            )

        resolution_time = state.resolution_time

        if resolution_time is None:

            boarding_time = (
                self.config.max_simulation_time
            )

        else:

            boarding_time = resolution_time

        return EpisodeOutcome(
            case_id=case.case_id,
            action=action,
            resolved=state.resolved,
            resolution_time=resolution_time,
            boarding_time=boarding_time,
            escalation_count=state.escalation_count,
            resource_conflicts=0,
            initial_state=initial_state.snapshot(),
            final_state=state.snapshot(),
            events=events,
        )

    # ================================================================
    # PUBLIC API
    # ================================================================

    def evaluate_action(
        self,
        state: EDOperationalState,
        action: str,
    ) -> ActionEvaluation:

        outcome = self._run_simulation(
            state,
            action,
        )

        duration = (
            outcome.resolution_time
            if outcome.resolution_time is not None
            else self.config.max_simulation_time
        )

        return ActionEvaluation(
            action=action,
            feasible=outcome.resolved,
            resolution_status=(
                "resolved"
                if outcome.resolved
                else "unresolved"
            ),
            simulated_duration=duration,
            boarding_time=outcome.boarding_time,
            escalation_count=(
                outcome.escalation_count
            ),
            resource_conflicts=(
                outcome.resource_conflicts
            ),
            explanation=(
                f"{state.scenario_type}: action "
                f"'{action}' produced a simulated "
                f"resolution time of "
                f"{duration:.2f} minutes."
            ),
            extra_metrics={
                "scenario_type": state.scenario_type,
                "events": len(outcome.events),
            },
        )

    def run_episode(
        self,
        state: EDOperationalState,
        action: str,
    ) -> EpisodeOutcome:

        return self._run_simulation(
            state,
            action,
        )