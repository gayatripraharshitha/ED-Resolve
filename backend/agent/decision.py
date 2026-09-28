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
# 3. Experience-conditioned deterministic action selection
# ---------------------------------------------------------------------------

EXPERIENCE_PRIOR_WEIGHT = 0.15

EXPERIENCE_ACTIONS = {
    "WAIT",
    "EXPEDITE_BED_CLEANING",
    "REQUEST_ALTERNATIVE_UNIT",
    "PRIORITIZE_TRANSPORT",
    "ESCALATE_TO_BED_MANAGER",
}


def _memory_action(
    memory: dict[str, Any],
) -> str | None:

    tags = memory.get(
        "tags",
        [],
    )

    if isinstance(
        tags,
        list,
    ):

        for tag in tags:

            action = str(
                tag
            ).strip().upper()

            if action in EXPERIENCE_ACTIONS:
                return action

    text = str(
        memory.get(
            "text",
            "",
        )
    )

    for key in (
        '"selected_action"',
        '"action"',
    ):

        marker_index = text.find(
            key
        )

        if marker_index < 0:
            continue

        fragment = text[
            marker_index:
            marker_index + 120
        ]

        for action in EXPERIENCE_ACTIONS:

            if f'"{action}"' in fragment:
                return action

    return None


def _build_experience_support(
    memories: list[dict[str, Any]],
    actions: list[str],
) -> dict[str, float]:

    weighted_success: dict[str, float] = {
        action: 0.0
        for action in actions
    }

    weighted_relevance: dict[str, float] = {
        action: 0.0
        for action in actions
    }

    counts: dict[str, int] = {
        action: 0
        for action in actions
    }

    seen_documents: set[str] = set()

    for memory in memories:

        if not isinstance(
            memory,
            dict,
        ):
            continue

        metadata = memory.get(
            "metadata",
            {},
        )

        if not isinstance(
            metadata,
            dict,
        ):
            metadata = {}

        if metadata.get(
            "memory_type"
        ) != "resolution_experience":
            continue

        document_id = str(
            memory.get(
                "document_id",
                memory.get(
                    "id",
                    "",
                ),
            )
        )

        if document_id in seen_documents:
            continue

        seen_documents.add(
            document_id
        )

        action = _memory_action(
            memory
        )

        if action not in actions:
            continue

        scores = memory.get(
            "scores",
            {},
        )

        if not isinstance(
            scores,
            dict,
        ):
            scores = {}

        relevance = scores.get(
            "reranker",
            scores.get(
                "semantic",
                0.5,
            ),
        )

        try:
            relevance = float(
                relevance
            )
        except (
            TypeError,
            ValueError,
        ):
            relevance = 0.5

        relevance = max(
            0.0,
            min(
                1.0,
                relevance,
            ),
        )

        tags = memory.get(
            "tags",
            [],
        )

        if not isinstance(
            tags,
            list,
        ):
            tags = []

        normalized_tags = {
            str(tag).lower()
            for tag in tags
        }

        resolution_status = str(
            metadata.get(
                "resolution_status",
                "",
            )
        ).lower()

        successful = (
            resolution_status == "resolved"
            or "successful"
            in normalized_tags
        )

        success_factor = (
            1.0
            if successful
            else 0.25
        )

        weighted_success[action] += (
            relevance
            * success_factor
        )

        weighted_relevance[action] += (
            relevance
        )

        counts[action] += 1

    support: dict[str, float] = {}

    for action in actions:

        relevance_total = (
            weighted_relevance[action]
        )

        if relevance_total <= 0:
            support[action] = 0.0
            continue

        quality = (
            weighted_success[action]
            / relevance_total
        )

        coverage = min(
            1.0,
            counts[action] / 3.0,
        )

        support[action] = max(
            0.0,
            min(
                1.0,
                quality * coverage,
            ),
        )

    return support


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

    memories = state.get(
        "recalled_experiences",
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

    feasible_actions = [
        result.action
        for result in feasible_results
    ]

    experience_support = (
        _build_experience_support(
            memories,
            feasible_actions,
        )
    )

    utilities = [
        float(
            result.utility_score
        )
        for result in feasible_results
    ]

    minimum_utility = min(
        utilities
    )

    maximum_utility = max(
        utilities
    )

    utility_range = (
        maximum_utility
        - minimum_utility
    )

    adjusted_scores: dict[str, float] = {}

    for result in feasible_results:

        utility = float(
            result.utility_score
        )

        if utility_range <= 1e-9:

            normalized_simulation_score = 0.0

        else:

            normalized_simulation_score = (
                utility
                - minimum_utility
            ) / utility_range

        memory_penalty = (
            EXPERIENCE_PRIOR_WEIGHT
            * (
                1.0
                - experience_support.get(
                    result.action,
                    0.0,
                )
            )
        )

        adjusted_scores[result.action] = (
            normalized_simulation_score
            + memory_penalty
        )

    # Current-state simulation remains dominant because
    # memory contributes only a bounded normalized prior.
    selected = min(
        feasible_results,
        key=lambda result:
        adjusted_scores[result.action],
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

    for constraint in constraints:

        if not constraint.feasible:

            violations = "; ".join(
                constraint.violations
            )

            rejected_actions.append(
                f"{constraint.action}: {violations}"
            )

    for result in feasible_results:

        if result.action == selected_action:
            continue

        rejected_actions.append(
            f"{result.action}: higher "
            f"experience-adjusted score "
            f"({adjusted_scores[result.action]:.3f} > "
            f"{adjusted_scores[selected_action]:.3f})"
        )

    evidence_memory_ids: list[str] = []

    if selected_candidate is not None:

        evidence_memory_ids = list(
            selected_candidate.evidence_memory_ids
        )

    selected_support = experience_support.get(
        selected_action,
        0.0,
    )

    reason = (
        f"{selected_action} was selected using the lowest "
        f"bounded experience-adjusted counterfactual score "
        f"({adjusted_scores[selected_action]:.3f}). "
        f"Current-state simulation utility was "
        f"{selected.utility_score:.2f}. "
        f"Historical experience support for this action was "
        f"{selected_support:.3f}."
    )

    decision = DecisionRecord(
        selected_action=selected_action,
        selection_reason=reason,
        selected_utility=selected.utility_score,
        alternatives_considered=alternatives_considered,
        rejected_actions=rejected_actions,
        memory_ids_used=evidence_memory_ids,
        experience_support={
            action: round(
                value,
                4,
            )
            for action, value
            in experience_support.items()
        },
        experience_adjusted_scores={
            action: round(
                value,
                4,
            )
            for action, value
            in adjusted_scores.items()
        },
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
                message=(
                    "Operational intervention selected using "
                    "current-state counterfactual simulation "
                    "with bounded state-conditioned "
                    "experiential support."
                ),
                data={
                    "selected_action": selected_action,
                    "selected_utility": selected.utility_score,
                    "selected_adjusted_score": (
                        adjusted_scores[selected_action]
                    ),
                    "experience_support": (
                        experience_support
                    ),
                    "alternatives": (
                        alternatives_considered
                    ),
                    "memory_ids_used": (
                        evidence_memory_ids
                    ),
                },
            )
        ],
        "error": None,
    }
