from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from backend.agent.state import (
    AuditEvent,
    EDResolveState,
    OutcomeRecord,
)
from backend.simulation.ed_simulator import EDTransferSimulator


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

COUNTERFACTUAL_SEED = 42
EXECUTION_SEED_NAMESPACE = "edresolve-execution-v1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit(
    stage: str,
    message: str,
    data: dict[str, Any] | None = None,
) -> AuditEvent:
    return AuditEvent(
        stage=stage,
        message=message,
        data=data or {},
    )


def _get_case_id(raw_state: Any) -> str:
    """
    EDOperationalState itself does not own case_id.

    The case identifier belongs to the active TransferCase.
    """

    active_case = raw_state.active_case()

    if active_case is not None:
        return str(active_case.case_id)

    return "unknown-case"


def _execution_seed(
    *,
    case_id: str,
    action: str,
) -> int:
    """
    Create a stable execution seed that is intentionally different from
    the counterfactual seed.

    This keeps the realized simulation reproducible without using exactly
    the same random stream as the counterfactual evaluation.
    """

    material = (
        f"{EXECUTION_SEED_NAMESPACE}:"
        f"{case_id}:"
        f"{action}"
    ).encode("utf-8")

    digest = hashlib.sha256(material).digest()

    return int.from_bytes(
        digest[:8],
        byteorder="big",
    ) % (2**31 - 1)


def _memory_id(memory: Any) -> str | None:
    """
    Extract a memory ID from:
      - a Pydantic memory object,
      - a dictionary,
      - or a generic object exposing memory_id/id.
    """

    if memory is None:
        return None

    if isinstance(memory, dict):

        value = memory.get("memory_id")

        if value is None:
            value = memory.get("id")

        return (
            str(value)
            if value is not None
            else None
        )

    value = getattr(
        memory,
        "memory_id",
        None,
    )

    if value is None:
        value = getattr(
            memory,
            "id",
            None,
        )

    return (
        str(value)
        if value is not None
        else None
    )


def _model_dict(value: Any) -> dict[str, Any]:
    """
    Convert a Pydantic model or dictionary into a dictionary safely.
    """

    if value is None:
        return {}

    if hasattr(value, "model_dump"):
        return value.model_dump()

    if isinstance(value, dict):
        return dict(value)

    return {}


def _pick_fields(
    value: Any,
    fields: list[str],
) -> dict[str, Any]:
    """
    Keep only selected fields from a model/dict.

    Missing fields are ignored so changes to model schemas do not cause
    KeyError failures here.
    """

    data = _model_dict(value)

    return {
        field: data[field]
        for field in fields
        if field in data
    }


def _truncate(
    value: Any,
    limit: int = 300,
) -> Any:
    """
    Keep retained textual fields compact.

    Non-string values are returned unchanged.
    """

    if not isinstance(value, str):
        return value

    text = value.strip()

    if len(text) <= limit:
        return text

    return text[: limit - 3] + "..."


# ---------------------------------------------------------------------------
# 1. Execute selected action
# ---------------------------------------------------------------------------

def execute_selected_action(
    state: EDResolveState,
) -> dict[str, Any]:

    raw_state = state.get("raw_state")
    decision = state.get("decision")

    if raw_state is None:
        raise ValueError(
            "raw_state is required before action execution."
        )

    if decision is None:
        raise ValueError(
            "decision is required before action execution."
        )

    action = decision.selected_action

    case_id = _get_case_id(
        raw_state
    )

    execution_seed = _execution_seed(
        case_id=case_id,
        action=action,
    )

    simulator = EDTransferSimulator(
        seed=execution_seed,
    )

    outcome = simulator.run_episode(
        raw_state,
        action,
    )

    return {
        "simulated_outcome": outcome,
        "audit_log": [
            _audit(
                stage="execution",
                message=(
                    "Selected intervention executed in the "
                    "operational simulator."
                ),
                data={
                    "case_id": case_id,
                    "action": action,
                    "seed": execution_seed,
                    "resolved": outcome.resolved,
                    "resolution_time": (
                        outcome.resolution_time
                    ),
                    "boarding_time": (
                        outcome.boarding_time
                    ),
                },
            )
        ],
        "error": None,
    }


# ---------------------------------------------------------------------------
# 2. Compare expected vs realized outcome
# ---------------------------------------------------------------------------

def analyze_outcome(
    state: EDResolveState,
) -> dict[str, Any]:

    decision = state.get("decision")

    simulation_results = state.get(
        "counterfactual_results",
        [],
    )

    outcome = state.get(
        "simulated_outcome",
    )

    if decision is None:
        raise ValueError(
            "decision is required for outcome analysis."
        )

    if outcome is None:
        raise ValueError(
            "simulated_outcome is required for outcome analysis."
        )

    expected = None

    for result in simulation_results:

        if result.action == decision.selected_action:
            expected = result
            break

    if expected is None:
        raise ValueError(
            "Expected counterfactual result for the selected "
            "action was not found."
        )

    expected_time = (
        expected.resolution_time
        if expected.resolution_time is not None
        else float("inf")
    )

    actual_time = (
        outcome.resolution_time
        if outcome.resolution_time is not None
        else float("inf")
    )

    if (
        expected_time == float("inf")
        and actual_time == float("inf")
    ):
        prediction_error = 0.0

    elif expected_time == float("inf"):

        prediction_error = 1.0

    elif actual_time == float("inf"):

        prediction_error = 1.0

    else:

        prediction_error = abs(
            actual_time - expected_time
        )

    resolution_status = (
        "resolved"
        if outcome.resolved
        else "unresolved"
    )

    # ------------------------------------------------------------------
    # Grounded lesson
    # ------------------------------------------------------------------

    if not outcome.resolved:

        lesson = (
            f"{decision.selected_action} did not resolve the "
            f"{outcome.case_id} episode under the realized "
            f"synthetic operational conditions. Future cases with "
            f"similar conditions should treat this intervention as "
            f"a potential failure mode and validate it again before "
            f"reuse."
        )

    elif (
        expected_time != float("inf")
        and actual_time > expected_time
    ):

        deviation = (
            actual_time - expected_time
        )

        lesson = (
            f"{decision.selected_action} resolved the episode, "
            f"but required {actual_time:.1f} minutes versus an "
            f"expected {expected_time:.1f} minutes. The simulation "
            f"underestimated resolution time by {deviation:.1f} "
            f"minutes under the realized synthetic conditions."
        )

    elif (
        expected_time != float("inf")
        and actual_time < expected_time
    ):

        improvement = (
            expected_time - actual_time
        )

        lesson = (
            f"{decision.selected_action} resolved the episode "
            f"{improvement:.1f} minutes faster than predicted, "
            f"with a realized resolution time of "
            f"{actual_time:.1f} minutes. The historical and "
            f"counterfactual estimate was conservative for this "
            f"synthetic episode."
        )

    else:

        lesson = (
            f"{decision.selected_action} successfully resolved "
            f"the episode in {actual_time:.1f} minutes under the "
            f"realized synthetic operational conditions."
        )

    outcome_record = OutcomeRecord(
        action=decision.selected_action,
        expected_resolution_time=(
            expected.resolution_time
        ),
        actual_resolution_time=(
            outcome.resolution_time
        ),
        prediction_error=prediction_error,
        resolved=outcome.resolved,
        escalation_count=outcome.escalation_count,
        resource_conflicts=(
            outcome.resource_conflicts
        ),
        resolution_status=resolution_status,
        lesson=lesson,
    )

    return {
        "outcome": outcome_record,
        "audit_log": [
            _audit(
                stage="outcome_analysis",
                message=(
                    "Realized outcome compared against "
                    "counterfactual expectation."
                ),
                data={
                    "action": decision.selected_action,
                    "expected_resolution_time": (
                        expected.resolution_time
                    ),
                    "actual_resolution_time": (
                        outcome.resolution_time
                    ),
                    "prediction_error": prediction_error,
                    "resolved": outcome.resolved,
                },
            )
        ],
        "error": None,
    }


# ---------------------------------------------------------------------------
# 3. Build compact Hindsight experience
# ---------------------------------------------------------------------------

def build_experience_for_hindsight(
    state: EDResolveState,
) -> dict[str, Any]:

    raw_state = state.get("raw_state")
    world_model = state.get("world_model")
    bottleneck = state.get("bottleneck")

    memories = state.get(
        "recalled_experiences",
        [],
    )

    candidates = state.get(
        "candidate_actions",
        [],
    )

    constraints = state.get(
        "constraint_results",
        [],
    )

    counterfactuals = state.get(
        "counterfactual_results",
        [],
    )

    decision = state.get(
        "decision",
    )

    outcome = state.get(
        "outcome",
    )

    simulated_outcome = state.get(
        "simulated_outcome",
    )

    if raw_state is None:
        raise ValueError(
            "raw_state is required."
        )

    if bottleneck is None:
        raise ValueError(
            "bottleneck is required."
        )

    if decision is None:
        raise ValueError(
            "decision is required."
        )

    if outcome is None:
        raise ValueError(
            "outcome is required."
        )

    if simulated_outcome is None:
        raise ValueError(
            "simulated_outcome is required."
        )

    case_id = _get_case_id(
        raw_state
    )

    active_case = raw_state.active_case()

    bottleneck_type = str(
        getattr(
            bottleneck,
            "bottleneck_type",
            "UNKNOWN",
        )
    )

    # ------------------------------------------------------------------
    # Current-state fingerprint
    # ------------------------------------------------------------------

    bottleneck_data = _pick_fields(
        bottleneck,
        [
            "bottleneck_type",
            "capacity_pressure",
            "transport_pressure",
            "coordination_pressure",
            "process_delay",
            "resource_conflict",
            "confidence",
            "dominant_dependency",
        ],
    )

    world_data = _pick_fields(
        world_model,
        [
            "scenario_type",
            "patients_in_ed",
            "boarding_patients",
            "pending_transfers",
            "unresolved_transfers",
            "ICU_beds_available",
            "HDU_beds_available",
            "transport_teams_available",
            "transport_queue",
            "beds_waiting_cleaning",
            "bed_manager_available",
            "senior_coordinator_available",
            "current_time",
        ],
    )

    # ------------------------------------------------------------------
    # Historical evidence
    # ------------------------------------------------------------------

    memory_ids = [
        memory_id
        for memory_id in (
            _memory_id(memory)
            for memory in memories
        )
        if memory_id is not None
    ]

    historical_context = {
        "memory_ids": memory_ids[:10],
        "memory_count": len(memory_ids),
    }

    # ------------------------------------------------------------------
    # Candidate action summary
    # ------------------------------------------------------------------

    compact_candidates: list[dict[str, Any]] = []

    for candidate in candidates:

        data = _model_dict(candidate)

        compact_candidates.append(
            {
                "action": data.get("action"),
                "confidence": data.get("confidence"),
                "expected_benefit": _truncate(
                    data.get("expected_benefit"),
                    300,
                ),
                "expected_risk": _truncate(
                    data.get("expected_risk"),
                    300,
                ),
                "evidence_memory_ids": (
                    data.get(
                        "evidence_memory_ids",
                        [],
                    )[:8]
                ),
            }
        )

    # ------------------------------------------------------------------
    # Constraint summary
    # ------------------------------------------------------------------

    compact_constraints: list[dict[str, Any]] = []

    for constraint in constraints:

        data = _model_dict(constraint)

        compact_constraints.append(
            {
                key: data[key]
                for key in (
                    "action",
                    "feasible",
                    "reason",
                    "violations",
                )
                if key in data
            }
        )

    # ------------------------------------------------------------------
    # Counterfactual summary
    # ------------------------------------------------------------------

    compact_counterfactuals: list[dict[str, Any]] = []

    for result in counterfactuals:

        data = _model_dict(result)

        compact_counterfactuals.append(
            {
                key: data[key]
                for key in (
                    "action",
                    "feasible",
                    "resolved",
                    "resolution_time",
                    "boarding_time",
                    "escalation_count",
                    "resource_conflicts",
                    "utility_score",
                )
                if key in data
            }
        )

    # ------------------------------------------------------------------
    # Realized outcome
    # ------------------------------------------------------------------

    realized_outcome = {
        "resolved": simulated_outcome.resolved,
        "resolution_time": simulated_outcome.resolution_time,
        "boarding_time": simulated_outcome.boarding_time,
        "escalation_count": (
            simulated_outcome.escalation_count
        ),
        "resource_conflicts": (
            simulated_outcome.resource_conflicts
        ),
    }

    # ------------------------------------------------------------------
    # Compact experiential memory
    # ------------------------------------------------------------------

    episode_id = (
        f"edresolve-"
        f"{raw_state.scenario_type}-"
        f"{_now_iso()}"
    )

    experience = {
        "episode_id": episode_id,

        "case_id": case_id,

        "timestamp": _now_iso(),

        "scenario_type": raw_state.scenario_type,

        "bottleneck_type": bottleneck_type,

        "resolution_status": (
            "resolved"
            if simulated_outcome.resolved
            else "unresolved"
        ),

        "selected_action": (
            decision.selected_action
        ),

        # --------------------------------------------------------------
        # State fingerprint
        # --------------------------------------------------------------

        "state_fingerprint": {
            "destination_unit": (
                active_case.destination_unit
                if active_case is not None
                else None
            ),
            "operational_state": world_data,
            "bottleneck": bottleneck_data,
        },

        # --------------------------------------------------------------
        # Historical experience used for this episode
        # --------------------------------------------------------------

        "historical_context": historical_context,

        # --------------------------------------------------------------
        # Candidate actions considered
        # --------------------------------------------------------------

        "candidate_actions": compact_candidates,

        "constraint_results": compact_constraints,

        "counterfactual_results": compact_counterfactuals,

        # --------------------------------------------------------------
        # Decision
        # --------------------------------------------------------------

        "decision": {
            "selected_action": (
                decision.selected_action
            ),
            "selection_reason": _truncate(
                decision.selection_reason,
                500,
            ),
            "selected_utility": (
                decision.selected_utility
            ),
            "alternatives_considered": list(
                decision.alternatives_considered
            ),
            "rejected_actions": [
                _truncate(
                    item,
                    250,
                )
                for item in decision.rejected_actions
            ],
        },

        # --------------------------------------------------------------
        # Realized outcome
        # --------------------------------------------------------------

        "realized_outcome": realized_outcome,

        # --------------------------------------------------------------
        # Learning signal
        # --------------------------------------------------------------

        "learning": {
            "expected_resolution_time": (
                outcome.expected_resolution_time
            ),
            "actual_resolution_time": (
                outcome.actual_resolution_time
            ),
            "prediction_error": (
                outcome.prediction_error
            ),
            "resolved": outcome.resolved,
            "resolution_status": (
                outcome.resolution_status
            ),
            "escalation_count": (
                outcome.escalation_count
            ),
            "resource_conflicts": (
                outcome.resource_conflicts
            ),
        },

        # --------------------------------------------------------------
        # Future-use lesson
        # --------------------------------------------------------------

        "lesson": _truncate(
            outcome.lesson,
            600,
        ),

        "learning_signal": {
            "prediction_error": (
                outcome.prediction_error
            ),
            "successful": (
                outcome.resolved
            ),
            "failed_action": (
                not outcome.resolved
            ),
        },
    }

    return {
        "experience_to_retain": experience,
        "audit_log": [
            _audit(
                stage="experience",
                message=(
                    "Compact operational experience prepared "
                    "for Hindsight retention."
                ),
                data={
                    "episode_id": episode_id,
                    "case_id": case_id,
                    "bottleneck_type": (
                        bottleneck_type
                    ),
                    "selected_action": (
                        decision.selected_action
                    ),
                    "successful": (
                        outcome.resolved
                    ),
                    "prediction_error": (
                        outcome.prediction_error
                    ),
                    "memory_count": (
                        len(memory_ids)
                    ),
                },
            )
        ],
        "error": None,
    }