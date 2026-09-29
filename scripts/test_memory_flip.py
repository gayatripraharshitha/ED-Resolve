from backend.agent.decision import select_action
from backend.agent.state import (
    CandidateAction,
    ConstraintCheck,
    CounterfactualResult,
)


def memory(
    *,
    action: str,
    status: str,
    memory_id: str,
) -> dict:
    return {
        "id": memory_id,
        "document_id": memory_id,
        "text": f'{{"selected_action": "{action}"}}',
        "metadata": {
            "memory_type": "resolution_experience",
            "bottleneck_type": "ICU_BED_CLEANING",
            "resolution_status": status,
        },
        "tags": [
            "edresolve",
            "resolution-experience",
            action,
        ],
        "scores": {
            "reranker": 0.95,
        },
    }


def build_state(memories):
    return {
        "candidate_actions": [
            CandidateAction(
                action="EXPEDITE_BED_CLEANING",
                rationale="Current simulation slightly favors cleaning.",
            ),
            CandidateAction(
                action="ESCALATE_TO_BED_MANAGER",
                rationale="Historical experience may favor escalation.",
            ),
        ],

        "constraint_results": [
            ConstraintCheck(
                action="EXPEDITE_BED_CLEANING",
                feasible=True,
            ),
            ConstraintCheck(
                action="ESCALATE_TO_BED_MANAGER",
                feasible=True,
            ),
        ],

        "counterfactual_results": [
            CounterfactualResult(
                action="EXPEDITE_BED_CLEANING",
                feasible=True,
                resolved=True,
                resolution_time=48.0,
                boarding_time=48.0,
                escalation_count=0,
                resource_conflicts=0,
                utility_score=72.0,
                scenario_type="ICU_BED_CLEANING",
            ),
            CounterfactualResult(
                action="ESCALATE_TO_BED_MANAGER",
                feasible=True,
                resolved=True,
                resolution_time=49.0,
                boarding_time=49.0,
                escalation_count=1,
                resource_conflicts=0,
                utility_score=73.0,
                scenario_type="ICU_BED_CLEANING",
            ),
        ],

        "recalled_experiences": memories,

        "experience_applicability": {
            "global_score": 0.95,
            "mode": "HIGH",
            "prior_scale": 1.0,
            "memory_count": len(memories),
            "bottleneck_matches": len(memories),
            "scenario_matches": len(memories),
            "structurally_unseen": False,
        },
    }


# ============================================================
# MEMORY OFF
# ============================================================

without_memory = build_state([])

result_without = select_action(
    without_memory
)

decision_without = (
    result_without["decision"].selected_action
)


# ============================================================
# MEMORY ON
# ============================================================

with_memory = build_state([
    memory(
        action="EXPEDITE_BED_CLEANING",
        status="failed",
        memory_id="failed-clean-1",
    ),
    memory(
        action="EXPEDITE_BED_CLEANING",
        status="failed",
        memory_id="failed-clean-2",
    ),
    memory(
        action="ESCALATE_TO_BED_MANAGER",
        status="resolved",
        memory_id="success-escalate-1",
    ),
    memory(
        action="ESCALATE_TO_BED_MANAGER",
        status="resolved",
        memory_id="success-escalate-2",
    ),
])

result_with = select_action(
    with_memory
)

decision_with = (
    result_with["decision"].selected_action
)


# ============================================================
# OUTPUT
# ============================================================

print()
print("=" * 60)
print("ED RESOLVE — MEMORY MATTERS EXPERIMENT")
print("=" * 60)

print()
print("MEMORY OFF")
print("Decision:", decision_without)

print()
print("MEMORY ON")
print("Decision:", decision_with)

print()
print("EXPERIENCE SUPPORT")
print(
    result_with["decision"].experience_support
)

print()
print("ADJUSTED SCORES")
print(
    result_with["decision"].experience_adjusted_scores
)

print()
print(
    "MEMORY CHANGED DECISION:",
    decision_without != decision_with,
)

print("=" * 60)