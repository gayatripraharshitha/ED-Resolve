from __future__ import annotations

from typing import Any

from backend.agent.state import (
    AuditEvent,
    ConstraintCheck,
    CounterfactualResult,
    DecisionRecord,
    EDResolveState,
)
from backend.simulation.constraints import check_action_constraints
from backend.simulation.ed_simulator import EDTransferSimulator
from backend.simulation.metrics import (
    EpisodeMetrics,
    utility_score,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

UTILITY_ALPHA = 1.0
UTILITY_BETA = 0.5
UTILITY_GAMMA = 10.0
UTILITY_DELTA = 20.0

COUNTERFACTUAL_SEED = 42


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _evaluate_utility(
    *,
    action: str,
    resolved: bool,
    resolution_time: float,
    boarding_time: float,
    escalation_count: int,
    resource_conflicts: int,
) -> float:
    """
    Compute the current deterministic baseline objective.

    Lower is better.

    The simulator/metrics layer owns the actual utility definition.
    This function only adapts the counterfactual result into the
    EpisodeMetrics contract expected by utility_score().

    A later Architecture v2 upgrade will replace this point-estimate
    objective with distributional/risk-aware evaluation.
    """

    metrics = EpisodeMetrics(
        action=action,
        resolved=resolved,
        resolution_time=resolution_time,
        boarding_time=boarding_time,
        escalation_count=escalation_count,
        resource_conflicts=resource_conflicts,
    )

    return utility_score(
        metrics,
        alpha=UTILITY_ALPHA,
        beta=UTILITY_BETA,
        gamma=UTILITY_GAMMA,
        delta=UTILITY_DELTA,
    )


# ---------------------------------------------------------------------------
# 1. Hard constraint validation
# ---------------------------------------------------------------------------

def validate_candidates(
    state: EDResolveState,
) -> dict[str, Any]:

    raw_state = state.get("raw_state")
    candidates = state.get(
        "candidate_actions",
        [],
    )

    if raw_state is None:
        raise ValueError(
            "raw_state is required before constraint validation."
        )

    if not candidates:
        raise ValueError(
            "No candidate actions were generated."
        )

    constraint_results: list[ConstraintCheck] = []

    for candidate in candidates:

        result = check_action_constraints(
            raw_state,
            candidate.action,
        )

        constraint_results.append(
            ConstraintCheck(
                action=candidate.action,
                feasible=result.feasible,
                violations=list(
                    result.violations
                ),
            )
        )

    feasible_count = sum(
        1
        for result in constraint_results
        if result.feasible
    )

    return {
        "constraint_results": constraint_results,
        "audit_log": [
            _audit(
                stage="constraints",
                message="Hard operational constraints evaluated.",
                data={
                    "candidate_count": len(candidates),
                    "feasible_count": feasible_count,
                },
            )
        ],
        "error": None,
    }


# ---------------------------------------------------------------------------
# 2. Counterfactual simulation
# ---------------------------------------------------------------------------

def run_counterfactual_simulations(
    state: EDResolveState,
) -> dict[str, Any]:

    raw_state = state.get("raw_state")
    candidates = state.get(
        "candidate_actions",
        [],
    )
    constraints = state.get(
        "constraint_results",
        [],
    )

    if raw_state is None:
        raise ValueError(
            "raw_state is required before simulation."
        )

    if not candidates:
        raise ValueError(
            "Candidate actions are required before simulation."
        )

    constraint_map = {
        item.action: item
        for item in constraints
    }

    simulator = EDTransferSimulator(
        seed=COUNTERFACTUAL_SEED,
    )

    results: list[CounterfactualResult] = []

    for candidate in candidates:

        constraint = constraint_map.get(
            candidate.action
        )

        if constraint is None:
            continue

        # ---------------------------------------------------------------
        # Hard-constraint rejection
        # ---------------------------------------------------------------

        if not constraint.feasible:

            results.append(
                CounterfactualResult(
                    action=candidate.action,
                    feasible=False,
                    resolved=False,
                    resolution_time=None,
                    boarding_time=None,
                    escalation_count=0,
                    resource_conflicts=len(
                        constraint.violations
                    ),
                    utility_score=None,
                    scenario_type=raw_state.scenario_type,
                    explanation=(
                        "Rejected before simulation because "
                        "one or more hard constraints failed."
                    ),
                    events=[],
                )
            )

            continue

        # ---------------------------------------------------------------
        # Counterfactual evaluation
        # ---------------------------------------------------------------

        evaluation = simulator.evaluate_action(
            raw_state,
            candidate.action,
        )

        resolved = (
            evaluation.resolution_status
            == "resolved"
        )

        resolution_time = (
            evaluation.simulated_duration
        )

        boarding_time = (
            evaluation.boarding_time
        )

        escalation_count = (
            evaluation.escalation_count
        )

        resource_conflicts = (
            evaluation.resource_conflicts
        )

        score = _evaluate_utility(
            action=candidate.action,
            resolved=resolved,
            resolution_time=resolution_time,
            boarding_time=boarding_time,
            escalation_count=escalation_count,
            resource_conflicts=resource_conflicts,
        )

        extra_metrics = dict(
            getattr(
                evaluation,
                "extra_metrics",
                {},
            )
        )

        results.append(
            CounterfactualResult(
                action=candidate.action,
                feasible=evaluation.feasible,
                resolved=resolved,
                resolution_time=(
                    resolution_time
                    if evaluation.feasible
                    else None
                ),
                boarding_time=(
                    boarding_time
                    if evaluation.feasible
                    else None
                ),
                escalation_count=escalation_count,
                resource_conflicts=resource_conflicts,
                utility_score=score,
                scenario_type=raw_state.scenario_type,
                explanation=evaluation.explanation,
                events=[
                    {
                        "metric": key,
                        "value": value,
                    }
                    for key, value in extra_metrics.items()
                ],
            )
        )

    feasible_results = [
        result
        for result in results
        if result.feasible
    ]

    return {
        "counterfactual_results": results,
        "audit_log": [
            _audit(
                stage="counterfactual",
                message="Counterfactual interventions simulated.",
                data={
                    "simulated_actions": len(results),
                    "feasible_actions": len(
                        feasible_results
                    ),
                },
            )
        ],
        "error": None,
    }


# ---------------------------------------------------------------------------
# 3. Deterministic action selection
# ---------------------------------------------------------------------------

def select_action(
    state: EDResolveState,
) -> dict[str, Any]:

    results = state.get(
        "counterfactual_results",
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

    if not results:
        raise ValueError(
            "No counterfactual results available."
        )

    feasible_results = [
        result
        for result in results
        if result.feasible
        and result.utility_score is not None
    ]

    if not feasible_results:
        raise RuntimeError(
            "No feasible intervention survived constraint validation."
        )

    # Lower utility is better.
    selected = min(
        feasible_results,
        key=lambda result: result.utility_score,
    )

    selected_action = selected.action

    candidate_map = {
        candidate.action: candidate
        for candidate in candidates
    }

    selected_candidate = candidate_map.get(
        selected_action
    )

    alternatives_considered = [
        result.action
        for result in feasible_results
        if result.action != selected_action
    ]

    rejected_actions: list[str] = []

    # Hard-constraint rejections.
    for constraint in constraints:

        if not constraint.feasible:

            violations = "; ".join(
                constraint.violations
            )

            rejected_actions.append(
                f"{constraint.action}: {violations}"
            )

    # Feasible alternatives that scored worse.
    for result in feasible_results:

        if result.action == selected_action:
            continue

        rejected_actions.append(
            f"{result.action}: higher counterfactual utility "
            f"({result.utility_score:.2f} > "
            f"{selected.utility_score:.2f})"
        )

    evidence_memory_ids: list[str] = []

    if selected_candidate is not None:

        evidence_memory_ids = list(
            selected_candidate.evidence_memory_ids
        )

    reason = (
        f"{selected_action} was selected because it produced "
        f"the lowest feasible counterfactual utility "
        f"({selected.utility_score:.2f}) under the current "
        f"operational constraints."
    )

    decision = DecisionRecord(
        selected_action=selected_action,
        selection_reason=reason,
        selected_utility=selected.utility_score,
        alternatives_considered=alternatives_considered,
        rejected_actions=rejected_actions,
        memory_ids_used=evidence_memory_ids,
        simulation_results=[
            result.model_dump()
            for result in feasible_results
        ],
    )

    return {
        "decision": decision,
        "audit_log": [
            _audit(
                stage="decision",
                message="Operational intervention selected.",
                data={
                    "selected_action": selected_action,
                    "selected_utility": selected.utility_score,
                    "alternatives": alternatives_considered,
                    "memory_ids_used": evidence_memory_ids,
                },
            )
        ],
        "error": None,
    }