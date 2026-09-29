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

# Bounded influence of state-aligned experiential evidence.
#
# Positive historical evidence lowers an action's adjusted score.
# Negative historical evidence raises an action's adjusted score.
#
# Memory is still scaled by the applicability gate's prior_scale,
# so LOW-applicability regimes receive no experiential influence.
EXPERIENCE_PRIOR_WEIGHT = 0.35


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
    """
    Compute signed historical evidence for each action.

    +1.0 -> strong historical success
     0.0 -> no clear historical outcome evidence
    -1.0 -> strong historical failure

    The signal is bounded and later scaled by the
    state-conditioned applicability prior.
    """

    weighted_signal: dict[str, float] = {
        action: 0.0
        for action in actions
    }

    weighted_evidence: dict[str, float] = {
        action: 0.0
        for action in actions
    }

    counts: dict[str, int] = {
        action: 0
        for action in actions
    }

    seen_documents: set[str] = set()

    success_statuses = {
        "resolved",
        "success",
        "successful",
    }

    failure_statuses = {
        "failed",
        "failure",
        "unresolved",
        "unsuccessful",
        "timeout",
    }

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

        if not document_id:
            continue

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
            str(tag).strip().lower()
            for tag in tags
        }

        resolution_status = str(
            metadata.get(
                "resolution_status",
                "",
            )
        ).strip().lower()

        # ---------------------------------------------------------------
        # Explicit historical outcome classification
        # ---------------------------------------------------------------

        if (
            resolution_status in success_statuses
            or normalized_tags.intersection(
                {
                    "success",
                    "successful",
                    "resolved",
                }
            )
        ):
            outcome_signal = 1.0

        elif (
            resolution_status in failure_statuses
            or normalized_tags.intersection(
                {
                    "failed",
                    "failure",
                    "unresolved",
                    "unsuccessful",
                    "timeout",
                }
            )
        ):
            outcome_signal = -1.0

        else:
            outcome_signal = 0.0

        weighted_signal[action] += (
            relevance
            * outcome_signal
        )

        weighted_evidence[action] += (
            relevance
        )

        counts[action] += 1

    support: dict[str, float] = {}

    for action in actions:

        evidence = weighted_evidence[action]

        if evidence <= 0:
            support[action] = 0.0
            continue

        normalized_signal = (
            weighted_signal[action]
            / evidence
        )

        # Repeated evidence becomes more trustworthy, but is
        # capped after three relevant experiences.
        coverage = min(
            1.0,
            counts[action] / 3.0,
        )

        support[action] = max(
            -1.0,
            min(
                1.0,
                normalized_signal
                * coverage,
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

    experience_applicability = state.get(
        "experience_applicability",
        {},
    )

    prior_scale = float(
        experience_applicability.get(
            "prior_scale",
            0.0,
        )
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

    experience_applicability = state.get(
        "experience_applicability",
        {},
    )

    applicability_mode = str(
        experience_applicability.get(
            "mode",
            "HIGH",
        )
    ).upper()

    # -------------------------------------------------------------------
    # SAFE MODE 1:
    # Low-applicability regime with only WAIT available.
    # -------------------------------------------------------------------

    if (
        feasible_results
        and applicability_mode == "LOW"
        and len(feasible_results) == 1
        and feasible_results[0].action == "WAIT"
    ):
        return {
            "safe_mode": {
                "active": True,
                "reason": (
                    "The current operational regime is outside "
                    "the system's experiential support and WAIT "
                    "is the only feasible action."
                ),
                "message": (
                    "Autonomous action withheld. "
                    "Human review required."
                ),
                "experience_applicability": (
                    experience_applicability
                ),
                "candidate_count": len(candidates),
                "feasible_count": len(
                    feasible_results
                ),
            },
            "audit_log": [
                _audit(
                    stage="safe_mode",
                    message=(
                        "Autonomy withheld for a low-applicability "
                        "regime with no meaningful intervention."
                    ),
                    data={
                        "experience_applicability": (
                            experience_applicability
                        ),
                        "candidate_count": len(candidates),
                        "feasible_count": len(
                            feasible_results
                        ),
                    },
                )
            ],
            "error": None,
        }

    # -------------------------------------------------------------------
    # SAFE MODE 2:
    # No feasible counterfactual pathway.
    # -------------------------------------------------------------------

    if not feasible_results:

        constraint_feasible_count = sum(
            1
            for result in constraints
            if result.feasible
        )

        if constraint_feasible_count > 0:
            safe_reason = (
                "Current-state counterfactual simulation "
                "found no executable resolution pathway."
            )
            failure_layer = "simulation"

        else:
            safe_reason = (
                "No feasible intervention survived "
                "hard operational constraints."
            )
            failure_layer = "constraints"

        return {
            "safe_mode": {
                "active": True,
                "reason": safe_reason,
                "message": (
                    "Autonomous action withheld. "
                    "Human review required."
                ),
                "experience_applicability": (
                    experience_applicability
                ),
                "candidate_count": len(candidates),
                "feasible_count": 0,
                "failure_layer": failure_layer,
                "constraint_feasible_count": (
                    constraint_feasible_count
                ),
            },
            "audit_log": [
                _audit(
                    stage="safe_mode",
                    message=(
                        "Autonomous action withheld because "
                        "no candidate intervention satisfied "
                        "the hard operational constraints."
                    ),
                    data={
                        "experience_applicability": (
                            experience_applicability
                        ),
                        "candidate_count": len(candidates),
                        "feasible_count": 0,
                    },
                )
            ],
            "error": None,
        }

    # -------------------------------------------------------------------
    # Experience-conditioned deterministic selection
    # -------------------------------------------------------------------

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

    # -------------------------------------------------------------------
    # Current-state simulation utility
    # -------------------------------------------------------------------

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

    # -------------------------------------------------------------------
    # Combined score
    #
    # Lower is better.
    #
    # Current simulation utility remains the base signal.
    #
    # Hindsight contributes a bounded adjustment:
    #
    #   positive historical support -> lower score
    #   negative historical support -> higher score
    #
    # prior_scale comes from the applicability gate, meaning:
    #
    #   HIGH   -> full influence
    #   MEDIUM -> partial influence
    #   LOW    -> zero influence
    #
    # The memory term is deliberately bounded so Hindsight cannot
    # blindly override a very large current-state simulation advantage.
    # -------------------------------------------------------------------

    adjusted_scores: dict[str, float] = {}

    for result in feasible_results:

        utility = float(
            result.utility_score
        )

        raw_support = experience_support.get(
            result.action,
            0.0,
        )

        effective_support = (
            raw_support
            * prior_scale
        )

        memory_adjustment = (
            EXPERIENCE_PRIOR_WEIGHT
            * effective_support
            * 10.0
        )

        adjusted_scores[result.action] = (
            utility
            - memory_adjustment
        )

    # -------------------------------------------------------------------
    # Deterministic final selection
    # -------------------------------------------------------------------

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

    # -------------------------------------------------------------------
    # Hard-constraint rejections
    # -------------------------------------------------------------------

    for constraint in constraints:

        if not constraint.feasible:

            violations = "; ".join(
                constraint.violations
            )

            rejected_actions.append(
                f"{constraint.action}: {violations}"
            )

    # -------------------------------------------------------------------
    # Experience-adjusted alternative rejections
    # -------------------------------------------------------------------

    for result in feasible_results:

        if result.action == selected_action:
            continue

        rejected_actions.append(
            f"{result.action}: higher "
            f"experience-adjusted score "
            f"({adjusted_scores[result.action]:.3f} > "
            f"{adjusted_scores[selected_action]:.3f})"
        )

    # -------------------------------------------------------------------
    # Memory IDs directly attached to the selected candidate
    # -------------------------------------------------------------------

    evidence_memory_ids: list[str] = []

    if selected_candidate is not None:

        evidence_memory_ids = list(
            selected_candidate.evidence_memory_ids
        )

    selected_support = experience_support.get(
        selected_action,
        0.0,
    )

    # -------------------------------------------------------------------
    # Transparent explanation
    # -------------------------------------------------------------------

    reason = (
        f"{selected_action} was selected using the lowest "
        f"bounded experience-adjusted counterfactual score "
        f"({adjusted_scores[selected_action]:.3f}). "
        f"Current-state simulation utility was "
        f"{selected.utility_score:.2f}. "
        f"Historical experience support for this action was "
        f"{selected_support:.3f}. "
        f"Experience applicability was "
        f"{experience_applicability.get('mode', 'LOW')} "
        f"({experience_applicability.get('global_score', 0.0):.3f}), "
        f"with prior scale "
        f"{prior_scale:.2f}."
    )

    decision = DecisionRecord(
        selected_action=selected_action,

        selection_reason=reason,

        selected_utility=selected.utility_score,

        alternatives_considered=(
            alternatives_considered
        ),

        rejected_actions=(
            rejected_actions
        ),

        memory_ids_used=(
            evidence_memory_ids
        ),

        experience_applicability=(
            experience_applicability
        ),

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

                    "selected_utility": (
                        selected.utility_score
                    ),

                    "selected_adjusted_score": (
                        adjusted_scores[
                            selected_action
                        ]
                    ),

                    "experience_applicability": (
                        experience_applicability
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
