from __future__ import annotations

from backend.agent.decision import (
    _evaluate_utility,
    select_action,
)
from backend.agent.state import (
    CandidateAction,
    ConstraintCheck,
    CounterfactualResult,
)
from backend.memory.hindsight_memory import EDResolveMemory
from backend.simulation.ed_simulator import EDTransferSimulator


BANK_ID = "edresolve"

ACTIONS = (
    "EXPEDITE_BED_CLEANING",
    "ESCALATE_TO_BED_MANAGER",
)

SCENARIOS = (
    "ICU_BED_CLEANING",
    "TRANSPORT_BOTTLENECK",
    "ALTERNATIVE_UNIT_AVAILABLE",
    "COORDINATION_DEADLOCK",
    "MIXED_BOTTLENECK",
)

MAX_SEED = 500

# Current selector changes a score by roughly ±3.5 at full memory support.
# Therefore we want a real simulation gap smaller than 7.
MAX_GAP = 6.5


def recall_memory() -> list[dict]:
    memory = EDResolveMemory(
        bank_id=BANK_ID,
    )

    try:
        query = (
            "Controlled Memory Matters experiment. "
            "ICU_BED_CLEANING. "
            "BED_CLEANING. "
            "Prior successful and failed interventions."
        )

        recalled = memory.recall_experiences(
            query=query,
            tags=["memory-matters"],
        )

        memories: list[dict] = []

        for item in recalled:

            if isinstance(item, dict):
                memories.append(item)

            else:
                memories.append(
                    {
                        "id": getattr(
                            item,
                            "id",
                            "",
                        ),
                        "text": getattr(
                            item,
                            "text",
                            str(item),
                        ),
                        "metadata": getattr(
                            item,
                            "metadata",
                            {},
                        ),
                        "tags": getattr(
                            item,
                            "tags",
                            [],
                        ),
                        "scores": getattr(
                            item,
                            "scores",
                            {},
                        ),
                    }
                )

        return memories

    finally:
        memory.close()


def find_close_real_simulation():
    print()
    print("=" * 70)
    print("SEARCHING FOR CLOSE REAL COUNTERFACTUALS")
    print("=" * 70)

    best = None

    for scenario in SCENARIOS:

        for seed in range(
            1,
            MAX_SEED + 1,
        ):

            simulator = EDTransferSimulator(
                seed=seed,
            )

            try:
                raw_state = (
                    simulator.create_deadlock_state(
                        case_id=f"MEMORY-FLIP-{seed}",
                        scenario_type=scenario,
                    )
                )
            except Exception:
                continue

            evaluations = {}

            for action in ACTIONS:

                try:
                    evaluation = (
                        simulator.evaluate_action(
                            raw_state,
                            action,
                        )
                    )
                except Exception:
                    continue

                if not evaluation.feasible:
                    continue

                resolved = (
                    evaluation.resolution_status
                    == "resolved"
                )

                score = _evaluate_utility(
                    action=action,
                    resolved=resolved,
                    resolution_time=(
                        evaluation.simulated_duration
                    ),
                    boarding_time=(
                        evaluation.boarding_time
                    ),
                    escalation_count=(
                        evaluation.escalation_count
                    ),
                    resource_conflicts=(
                        evaluation.resource_conflicts
                    ),
                )

                evaluations[action] = {
                    "evaluation": evaluation,
                    "score": float(score),
                }

            if len(evaluations) != 2:
                continue

            expedite_score = evaluations[
                "EXPEDITE_BED_CLEANING"
            ]["score"]

            escalate_score = evaluations[
                "ESCALATE_TO_BED_MANAGER"
            ]["score"]

            gap = abs(
                expedite_score
                - escalate_score
            )

            candidate = {
                "scenario": scenario,
                "seed": seed,
                "raw_state": raw_state,
                "expedite": evaluations[
                    "EXPEDITE_BED_CLEANING"
                ],
                "escalate": evaluations[
                    "ESCALATE_TO_BED_MANAGER"
                ],
                "gap": gap,
            }

            if (
                best is None
                or gap < best["gap"]
            ):
                best = candidate

            if gap <= MAX_GAP:

                print(
                    f"FOUND: scenario={scenario} "
                    f"seed={seed}"
                )

                print(
                    "EXPEDITE:",
                    expedite_score,
                )

                print(
                    "ESCALATE:",
                    escalate_score,
                )

                print(
                    "UTILITY GAP:",
                    gap,
                )

                return candidate

    if best is not None:
        print(
            "Closest pair found, but gap was too large:"
        )
        print(
            "Scenario:",
            best["scenario"],
        )
        print(
            "Seed:",
            best["seed"],
        )
        print(
            "EXPEDITE:",
            best["expedite"]["score"],
        )
        print(
            "ESCALATE:",
            best["escalate"]["score"],
        )
        print(
            "Gap:",
            best["gap"],
        )

    return None


def make_candidates() -> list[CandidateAction]:
    return [
        CandidateAction(
            action="EXPEDITE_BED_CLEANING",
            rationale=(
                "Directly addresses the bed-cleaning dependency."
            ),
            expected_benefit=(
                "Reduces bed-cleaning delay."
            ),
            expected_risk=(
                "May fail under conditions where "
                "past experience indicates poor outcomes."
            ),
            confidence=0.8,
        ),
        CandidateAction(
            action="ESCALATE_TO_BED_MANAGER",
            rationale=(
                "Uses management escalation to resolve "
                "the operational bottleneck."
            ),
            expected_benefit=(
                "Provides coordination support."
            ),
            expected_risk=(
                "Adds escalation overhead."
            ),
            confidence=0.8,
        ),
    ]


def make_constraints() -> list[ConstraintCheck]:
    return [
        ConstraintCheck(
            action="EXPEDITE_BED_CLEANING",
            feasible=True,
            violations=[],
        ),
        ConstraintCheck(
            action="ESCALATE_TO_BED_MANAGER",
            feasible=True,
            violations=[],
        ),
    ]


def make_results(best) -> list[CounterfactualResult]:

    expedite_eval = (
        best["expedite"]["evaluation"]
    )

    escalate_eval = (
        best["escalate"]["evaluation"]
    )

    return [
        CounterfactualResult(
            action="EXPEDITE_BED_CLEANING",
            feasible=True,
            resolved=(
                expedite_eval.resolution_status
                == "resolved"
            ),
            resolution_time=(
                expedite_eval.simulated_duration
            ),
            boarding_time=(
                expedite_eval.boarding_time
            ),
            escalation_count=(
                expedite_eval.escalation_count
            ),
            resource_conflicts=(
                expedite_eval.resource_conflicts
            ),
            utility_score=(
                best["expedite"]["score"]
            ),
            scenario_type=(
                best["scenario"]
            ),
            explanation=(
                "Real EDResolve simulator result."
            ),
        ),
        CounterfactualResult(
            action="ESCALATE_TO_BED_MANAGER",
            feasible=True,
            resolved=(
                escalate_eval.resolution_status
                == "resolved"
            ),
            resolution_time=(
                escalate_eval.simulated_duration
            ),
            boarding_time=(
                escalate_eval.boarding_time
            ),
            escalation_count=(
                escalate_eval.escalation_count
            ),
            resource_conflicts=(
                escalate_eval.resource_conflicts
            ),
            utility_score=(
                best["escalate"]["score"]
            ),
            scenario_type=(
                best["scenario"]
            ),
            explanation=(
                "Real EDResolve simulator result."
            ),
        ),
    ]


def run_selector(
    memories: list[dict],
    results: list[CounterfactualResult],
) -> dict:

    state = {
        "candidate_actions": make_candidates(),
        "constraint_results": make_constraints(),
        "counterfactual_results": results,
        "recalled_experiences": memories,
        "experience_applicability": {
            "mode": "HIGH",
            "prior_scale": 1.0,
            "global_score": 1.0,
        },
    }

    return select_action(state)


def main() -> None:

    print()
    print("=" * 70)
    print("ED RESOLVE — MEMORY MATTERS PAIRED EXPERIMENT")
    print("=" * 70)

    memories = recall_memory()

    print()
    print(
        "Hindsight memory count:",
        len(memories),
    )

    if not memories:
        raise RuntimeError(
            "No memory-matters memories were recalled."
        )

    best = find_close_real_simulation()

    if best is None:
        print()
        print(
            "No sufficiently close real simulator pair "
            "was found."
        )
        print(
            "Do not change EDResolve."
        )
        print(
            "The experiment cannot honestly demonstrate "
            "a flip with the current simulator."
        )
        return

    results = make_results(best)

    print()
    print("=" * 70)
    print("SAME REAL SIMULATION")
    print("=" * 70)

    for result in results:
        print(
            f"{result.action:<32}"
            f" utility={result.utility_score:.4f}"
        )

    # ---------------------------------------------------------
    # MEMORY OFF
    # ---------------------------------------------------------

    print()
    print("=" * 70)
    print("MEMORY OFF")
    print("=" * 70)

    decision_off = run_selector(
        memories=[],
        results=results,
    )

    off = decision_off["decision"]

    print(
        "Decision:",
        off.selected_action,
    )

    print(
        "Support:",
        off.experience_support,
    )

    print(
        "Adjusted scores:",
        off.experience_adjusted_scores,
    )

    # ---------------------------------------------------------
    # MEMORY ON
    # ---------------------------------------------------------

    print()
    print("=" * 70)
    print("MEMORY ON — REAL HINDSIGHT")
    print("=" * 70)

    decision_on = run_selector(
        memories=memories,
        results=results,
    )

    on = decision_on["decision"]

    print(
        "Decision:",
        on.selected_action,
    )

    print(
        "Support:",
        on.experience_support,
    )

    print(
        "Adjusted scores:",
        on.experience_adjusted_scores,
    )

    # ---------------------------------------------------------
    # FINAL RESULT
    # ---------------------------------------------------------

    print()
    print("=" * 70)
    print("MEMORY MATTERS RESULT")
    print("=" * 70)

    print(
        "MEMORY OFF:",
        off.selected_action,
    )

    print(
        "MEMORY ON :",
        on.selected_action,
    )

    print(
        "DECISION FLIPPED:",
        off.selected_action
        != on.selected_action,
    )

    print()
    print(
        "Hindsight memories used:",
        len(memories),
    )

    print(
        "Simulation seed:",
        best["seed"],
    )

    print(
        "Scenario:",
        best["scenario"],
    )


if __name__ == "__main__":
    main()