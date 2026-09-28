from __future__ import annotations

from typing import Any, TypedDict

from pydantic import BaseModel, Field

from backend.simulation.models import EDOperationalState, EpisodeOutcome


# ---------------------------------------------------------------------------
# World model
# ---------------------------------------------------------------------------

class BottleneckFingerprint(BaseModel):
    bottleneck_type: str
    capacity_pressure: float = 0.0
    transport_pressure: float = 0.0
    coordination_pressure: float = 0.0
    process_delay: float = 0.0
    resource_conflict: float = 0.0
    confidence: float = 0.0
    dominant_dependency: str = "UNKNOWN"


class WorldModelSnapshot(BaseModel):
    scenario_type: str

    patients_in_ed: int
    boarding_patients: int
    pending_transfers: int
    unresolved_transfers: int

    ICU_beds_available: int
    HDU_beds_available: int

    transport_teams_available: int
    transport_queue: int
    beds_waiting_cleaning: int

    bed_manager_available: bool
    senior_coordinator_available: bool

    current_time: float

    graph_nodes: list[str] = Field(default_factory=list)
    graph_edges: list[str] = Field(default_factory=list)

    process_variant: str = ""


# ---------------------------------------------------------------------------
# Hindsight memory
# ---------------------------------------------------------------------------

class MemoryExperience(BaseModel):
    memory_id: str
    text: str

    memory_type: str = "unknown"
    context: str = ""

    metadata: dict[str, Any] = Field(
        default_factory=dict
    )

    tags: list[str] = Field(
        default_factory=list
    )

    entities: list[Any] = Field(
        default_factory=list
    )

    scores: dict[str, float] = Field(
        default_factory=dict
    )


# ---------------------------------------------------------------------------
# Agent candidates
# ---------------------------------------------------------------------------

class CandidateAction(BaseModel):
    action: str
    rationale: str

    evidence_memory_ids: list[str] = Field(
        default_factory=list
    )

    expected_benefit: str = ""
    expected_risk: str = ""

    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Constraint validation
# ---------------------------------------------------------------------------

class ConstraintCheck(BaseModel):
    action: str
    feasible: bool

    violations: list[str] = Field(
        default_factory=list
    )


# ---------------------------------------------------------------------------
# Counterfactual simulation
# ---------------------------------------------------------------------------

class CounterfactualResult(BaseModel):
    action: str
    feasible: bool

    resolved: bool

    resolution_time: float | None = None
    boarding_time: float | None = None

    escalation_count: int = 0
    resource_conflicts: int = 0

    utility_score: float | None = None

    scenario_type: str = ""

    explanation: str = ""

    events: list[Any] = Field(
        default_factory=list
    )


# ---------------------------------------------------------------------------
# Final decision
# ---------------------------------------------------------------------------

class DecisionRecord(BaseModel):
    selected_action: str

    selection_reason: str

    selected_utility: float

    alternatives_considered: list[str] = Field(
        default_factory=list
    )

    rejected_actions: list[str] = Field(
        default_factory=list
    )

    memory_ids_used: list[str] = Field(
        default_factory=list
    )

    simulation_results: list[dict[str, Any]] = Field(
        default_factory=list
    )


# ---------------------------------------------------------------------------
# Outcome / learning
# ---------------------------------------------------------------------------

class OutcomeRecord(BaseModel):
    action: str

    expected_resolution_time: float | None = None
    actual_resolution_time: float | None = None

    prediction_error: float = 0.0

    resolved: bool = False

    escalation_count: int = 0
    resource_conflicts: int = 0

    resolution_status: str = "unknown"

    lesson: str = ""


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------

class AuditEvent(BaseModel):
    stage: str
    message: str

    data: dict[str, Any] = Field(
        default_factory=dict
    )


# ---------------------------------------------------------------------------
# Main LangGraph state
# ---------------------------------------------------------------------------

class EDResolveState(TypedDict, total=False):

    # Case identity
    case_id: str
    timestamp: str

    # Raw/current operational state
    raw_state: EDOperationalState

    # Structured reasoning state
    world_model: WorldModelSnapshot
    bottleneck: BottleneckFingerprint

    # Hindsight
    memory_query: str
    recalled_experiences: list[dict[str, Any]]
    reflection: str

    # Candidate generation
    candidate_actions: list[CandidateAction]

    # Feasibility
    constraint_results: list[ConstraintCheck]

    # Counterfactual reasoning
    counterfactual_results: list[CounterfactualResult]

    # Decision
    decision: DecisionRecord

    # Actual selected-action execution
    simulated_outcome: EpisodeOutcome

    # Learning
    outcome: OutcomeRecord

    # Hindsight retention payload
    experience_to_retain: dict[str, Any]

    # Observability
    audit_log: list[AuditEvent]

    # Error propagation
    error: str | None