from __future__ import annotations

from pathlib import Path

import pandas as pd

from backend.simulation.actions import (
    ESCALATE_TO_BED_MANAGER,
    EXPEDITE_BED_CLEANING,
    PRIORITIZE_TRANSPORT,
    REQUEST_ALTERNATIVE_UNIT,
    PRIORITIZE_TRANSPORT,
    WAIT,
)
from backend.simulation.constraints import check_action_constraints
from backend.simulation.ed_simulator import (
    EDTransferSimulator,
    SCENARIO_TYPES,
)
from backend.simulation.metrics import (
    evaluation_to_metrics,
    utility_score,
)


ACTIONS = [
    WAIT,
    EXPEDITE_BED_CLEANING,
    REQUEST_ALTERNATIVE_UNIT,
    PRIORITIZE_TRANSPORT,
    ESCALATE_TO_BED_MANAGER,
]

SEEDS = range(100)

OUTPUT_PATH = Path(
    "data/synthetic/counterfactual_results.csv"
)


def main() -> None:
    rows: list[dict] = []

    for seed in SEEDS:

        simulator = EDTransferSimulator(
            seed=seed
        )

        state = simulator.create_deadlock_state(
            case_id=f"ED-{seed:03d}"
        )

        scenario = state.scenario_type

        for action in ACTIONS:

            constraint = check_action_constraints(
                state,
                action,
            )

            # Always record the action.
            # This is important for measuring feasibility.
            if not constraint.feasible:

                rows.append(
                    {
                        "seed": seed,
                        "case_id": f"ED-{seed:03d}",
                        "scenario_type": scenario,
                        "action": action,
                        "feasible": False,
                        "resolved": False,
                        "resolution_time": None,
                        "boarding_time": None,
                        "escalations": None,
                        "resource_conflicts": None,
                        "utility_score": None,
                    }
                )

                continue

            evaluation = simulator.evaluate_action(
                state,
                action,
            )

            metrics = evaluation_to_metrics(
                evaluation
            )

            score = utility_score(
                metrics
            )

            rows.append(
                {
                    "seed": seed,
                    "case_id": f"ED-{seed:03d}",
                    "scenario_type": scenario,
                    "action": action,
                    "feasible": True,
                    "resolved": metrics.resolved,
                    "resolution_time": metrics.resolution_time,
                    "boarding_time": metrics.boarding_time,
                    "escalations": metrics.escalation_count,
                    "resource_conflicts": (
                        metrics.resource_conflicts
                    ),
                    "utility_score": score,
                }
            )

    results = pd.DataFrame(rows)

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    results.to_csv(
        OUTPUT_PATH,
        index=False,
    )

    # ------------------------------------------------------------
    # FEASIBILITY SUMMARY
    # ------------------------------------------------------------

    feasibility_summary = (
        results
        .groupby(["scenario_type", "action"])
        .agg(
            episodes=("seed", "count"),
            feasible_rate=("feasible", "mean"),
        )
        .reset_index()
    )

    # ------------------------------------------------------------
    # OUTCOME SUMMARY
    # Only compare actions on episodes where they were feasible.
    # ------------------------------------------------------------

    feasible_results = results[
        results["feasible"]
    ].copy()

    outcome_summary = (
        feasible_results
        .groupby(["scenario_type", "action"])
        .agg(
            feasible_episodes=("seed", "count"),
            resolution_rate=("resolved", "mean"),
            mean_resolution_time=(
                "resolution_time",
                "mean",
            ),
            mean_boarding_time=(
                "boarding_time",
                "mean",
            ),
            mean_escalations=(
                "escalations",
                "mean",
            ),
            mean_resource_conflicts=(
                "resource_conflicts",
                "mean",
            ),
            mean_utility=(
                "utility_score",
                "mean",
            ),
        )
        .reset_index()
        .sort_values(
            [
                "scenario_type",
                "mean_utility",
            ]
        )
    )

    # ------------------------------------------------------------
    # PRINT RESULTS
    # ------------------------------------------------------------

    print("\n" + "=" * 90)
    print("EDResolve Counterfactual Evaluation")
    print("=" * 90)

    print(
        f"\nSeeds: {len(SEEDS)}"
        f"\nScenarios: {len(SCENARIO_TYPES)}"
        f"\nAction space: {len(ACTIONS)}"
        f"\nTotal action-state evaluations: {len(results)}"
    )

    print("\n" + "-" * 90)
    print("FEASIBILITY BY SCENARIO")
    print("-" * 90)

    print(
        feasibility_summary.to_string(
            index=False,
            float_format=lambda x: f"{x:.3f}",
        )
    )

    print("\n" + "-" * 90)
    print("OUTCOMES — FEASIBLE ACTIONS ONLY")
    print("-" * 90)

    print(
        outcome_summary.to_string(
            index=False,
            float_format=lambda x: f"{x:.3f}",
        )
    )

    # ------------------------------------------------------------
    # BEST FEASIBLE ACTION PER SCENARIO
    # ------------------------------------------------------------

    print("\n" + "-" * 90)
    print("LOWEST-UTILITY FEASIBLE ACTION PER SCENARIO")
    print("-" * 90)

    for scenario in SCENARIO_TYPES:

        scenario_results = outcome_summary[
            outcome_summary["scenario_type"]
            == scenario
        ]

        if scenario_results.empty:
            print(
                f"{scenario}: no feasible actions"
            )
            continue

        best = scenario_results.iloc[0]

        print(
            f"{scenario}: "
            f"{best['action']} "
            f"(mean utility="
            f"{best['mean_utility']:.3f})"
        )

    print(
        f"\nSaved to: {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()