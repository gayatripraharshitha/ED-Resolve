from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TransferCase:
    """
    Represents one ED patient-flow transfer case.

    This is an operational simulation object, not a clinical treatment model.
    """

    case_id: str
    destination_unit: str
    ready_for_transfer: bool = True
    waiting_since: float = 0.0
    priority: int = 2

    # Operational blockers
    bed_blocked: bool = False
    transport_blocked: bool = False
    coordination_blocked: bool = False

    def waiting_time(self, current_time: float) -> float:
        return max(0.0, current_time - self.waiting_since)


@dataclass
class ResourceState:
    """
    Operational resources available to the ED.
    """

    icu_beds_available: int = 0
    hdu_beds_available: int = 0
    transport_teams_available: int = 1

    # Operational queues
    beds_waiting_cleaning: int = 0
    transport_queue: int = 0

    # Coordination resources
    bed_manager_available: bool = True
    senior_coordinator_available: bool = True


@dataclass
class EDOperationalState:
    """
    Complete simulator state for the EDResolve operational environment.

    This is an operational decision-support simulation.
    It does not model diagnosis, medication, or clinical treatment.

    Time is represented in simulation minutes from the beginning
    of an episode.
    """

    # Simulation clock
    current_time: float = 0.0

    # Scenario identity
    scenario_type: str = "ICU_BED_CLEANING"

    # ED flow
    patients_in_ed: int = 40
    boarding_patients: int = 5

    # Transfer workload
    pending_transfers: int = 1
    unresolved_transfers: int = 1

    # Resources
    resources: ResourceState = field(default_factory=ResourceState)

    # Active transfer cases
    transfer_cases: list[TransferCase] = field(
        default_factory=list
    )

    # Escalation / coordination state
    escalation_count: int = 0
    coordination_attempts: int = 0

    # Episode outcome
    resolved: bool = False
    resolution_time: float | None = None

    def snapshot(self) -> dict[str, Any]:
        """
        Return a serializable state snapshot.

        Useful for:
        - Hindsight memory
        - simulation logging
        - evaluation
        - debugging
        """

        return asdict(self)

    def active_case(self) -> TransferCase | None:
        """
        Return the first active transfer case.
        """

        for case in self.transfer_cases:
            if not self.resolved:
                return case

        return None

    def total_resource_capacity(self) -> int:
        """
        Current immediately usable transfer-related capacity.
        """

        return (
            self.resources.icu_beds_available
            + self.resources.hdu_beds_available
            + self.resources.transport_teams_available
        )


@dataclass
class ActionEvaluation:
    """
    Result of evaluating one intervention against the
    simulated state.
    """

    action: str

    feasible: bool

    resolution_status: str

    simulated_duration: float

    boarding_time: float

    escalation_count: int

    resource_conflicts: int

    explanation: str = ""

    # Allows additional metrics without changing the core schema.
    extra_metrics: dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EpisodeOutcome:
    """
    Final result of running an intervention in the simulator.
    """

    case_id: str
    action: str

    resolved: bool
    resolution_time: float | None

    boarding_time: float
    escalation_count: int
    resource_conflicts: int

    initial_state: dict[str, Any]
    final_state: dict[str, Any]

    events: list[dict[str, Any]] = field(
        default_factory=list
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)