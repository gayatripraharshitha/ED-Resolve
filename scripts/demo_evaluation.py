from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.agent.graph import get_agent_graph
from backend.simulation.ed_simulator import EDTransferSimulator


OUTPUT = Path("data/evaluation/initial_demo_results.json")


def get_value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def build_state(
    simulator: EDTransferSimulator,
    *,
    scenario_type: str,
    case_id: str,
) -> Any:

    raw_state = simulator.create_deadlock_state(
        case_id=case_id,
        scenario_type=scenario_type,
    )

    if scenario_type == "CASCADE_RESOURCE_COLLAPSE_X53":

        raw_state.scenario_type = scenario_type

        resources = raw_state.resources

        resources.icu_beds_available = 0
        resources.hdu_beds_available = 0
        resources.transport_teams_available = 0
        resources.beds_waiting_cleaning = 0
        resources.transport_queue = 0
        resources.bed_manager_available = False
        resources.senior_coordinator_available = False

        for case in getattr(raw_state, "transfer_cases", []):
            if hasattr(case, "bed_blocked"):
                case.bed_blocked = False
            if hasattr(case, "transport_blocked"):
                case.transport_blocked = False
            if hasattr(case, "coordination_blocked"):
                case.coordination_blocked = False

    return raw_state


async def run_case(
    graph: Any,
    *,
    scenario_type: str,
    case_id: str,
) -> dict[str, Any]:

    simulator = EDTransferSimulator(seed=53)

    raw_state = build_state(
        simulator,
        scenario_type=scenario_type,
        case_id=case_id,
    )

    result = await graph.ainvoke(
        {
            "case_id": case_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "raw_state": raw_state,
        }
    )

    applicability = result.get(
        "experience_applicability",
        {},
    )

    decision = result.get(
        "decision",
        None,
    )

    safe_mode = result.get(
        "safe_mode",
        {},
    )

    simulation_results = result.get(
        "counterfactual_results",
        [],
    )

    selected_action = None

    if decision is not None:
        selected_action = get_value(
            decision,
            "selected_action",
        )

    best_simulation = []

    for item in simulation_results:
        best_simulation.append(
            {
                "action": get_value(item, "action"),
                "feasible": get_value(item, "feasible"),
                "resolved": get_value(item, "resolved"),
                "resolution_time": get_value(
                    item,
                    "resolution_time",
                ),
                "utility_score": get_value(
                    item,
                    "utility_score",
                ),
            }
        )

    safe_active = bool(
        safe_mode.get(
            "active",
            False,
        )
        if isinstance(safe_mode, dict)
        else False
    )

    return {
        "case_id": case_id,
        "scenario": raw_state.scenario_type,
        "error": result.get("error"),
        "applicability_mode": applicability.get("mode"),
        "prior_scale": applicability.get("prior_scale"),
        "global_applicability": applicability.get(
            "global_score"
        ),
        "structurally_unseen": applicability.get(
            "structurally_unseen"
        ),
        "bottleneck_matches": applicability.get(
            "bottleneck_matches"
        ),
        "scenario_matches": applicability.get(
            "scenario_matches"
        ),
        "graph_matches": applicability.get(
            "graph_matches"
        ),
        "selected_action": selected_action,
        "safe_mode": safe_active,
        "safe_mode_reason": (
            safe_mode.get("reason")
            if isinstance(safe_mode, dict)
            else None
        ),
        "failure_layer": (
            safe_mode.get("failure_layer")
            if isinstance(safe_mode, dict)
            else None
        ),
        "decision_reason": (
            get_value(
                decision,
                "selection_reason",
            )
            if decision is not None
            else None
        ),
        "simulation_results": best_simulation,
    }


def print_summary(results: list[dict[str, Any]]) -> None:

    print()
    print("=" * 100)
    print("EDResolve - INITIAL DEMO EVIDENCE")
    print("=" * 100)

    print()
    print(
        f"{'CASE':<28}"
        f"{'APPLICABILITY':<14}"
        f"{'PRIOR':<8}"
        f"{'UNSEEN':<9}"
        f"{'ACTION':<28}"
        f"{'SAFE MODE':<10}"
    )
    print("-" * 100)

    for item in results:

        action = item["selected_action"] or "NONE"

        print(
            f"{item['scenario']:<28}"
            f"{str(item['applicability_mode']):<14}"
            f"{str(item['prior_scale']):<8}"
            f"{str(item['structurally_unseen']):<9}"
            f"{action:<28}"
            f"{str(item['safe_mode']):<10}"
        )

    print("-" * 100)

    for item in results:

        print()
        print(f"CASE: {item['scenario']}")
        print(
            "  applicability:",
            item["applicability_mode"],
            item["global_applicability"],
        )
        print(
            "  structural matches:",
            item["bottleneck_matches"],
            item["scenario_matches"],
            item["graph_matches"],
        )
        print(
            "  unseen:",
            item["structurally_unseen"],
        )
        print(
            "  selected action:",
            item["selected_action"],
        )
        print(
            "  safe mode:",
            item["safe_mode"],
        )

        if item["failure_layer"]:
            print(
                "  failure layer:",
                item["failure_layer"],
            )

        if item["safe_mode_reason"]:
            print(
                "  safe-mode reason:",
                item["safe_mode_reason"],
            )

        if item["decision_reason"]:
            print(
                "  decision reason:",
                item["decision_reason"],
            )

        if item["error"]:
            print(
                "  ERROR:",
                item["error"],
            )


async def main() -> None:

    graph = get_agent_graph()

    cases = [
        (
            "ICU_BED_CLEANING",
            "DEMO-KNOWN-001",
        ),
        (
            "MIXED_BOTTLENECK",
            "DEMO-MIXED-002",
        ),
        (
            "CASCADE_RESOURCE_COLLAPSE_X53",
            "DEMO-UNSEEN-003",
        ),
    ]

    results = []

    for scenario_type, case_id in cases:

        print(
            f"\nRunning {scenario_type} ..."
        )

        try:

            result = await run_case(
                graph,
                scenario_type=scenario_type,
                case_id=case_id,
            )

        except Exception as exc:

            result = {
                "case_id": case_id,
                "scenario": scenario_type,
                "error": str(exc),
            }

        results.append(result)

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT.write_text(
        json.dumps(
            results,
            indent=2,
            default=str,
        )
    )

    print_summary(results)

    print()
    print(
        f"Saved evidence: {OUTPUT}"
    )


asyncio.run(main())
