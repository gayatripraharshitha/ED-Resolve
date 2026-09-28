from __future__ import annotations

from dataclasses import dataclass

from ortools.sat.python import cp_model

from backend.simulation.actions import (
    ESCALATE_TO_BED_MANAGER,
    EXPEDITE_BED_CLEANING,
    PRIORITIZE_TRANSPORT,
    REQUEST_ALTERNATIVE_UNIT,
    WAIT,
)
from backend.simulation.models import EDOperationalState


CP_SAT_TIME_LIMIT_SECONDS = 0.25


@dataclass(frozen=True)
class ConstraintResult:
    action: str
    feasible: bool
    violations: list[str]
    solver_status: str = "UNKNOWN"


def _build_feasibility_model(
    state: EDOperationalState,
    action: str,
) -> tuple[cp_model.CpModel, cp_model.IntVar, list[str]]:

    model = cp_model.CpModel()

    selected = model.NewBoolVar(
        f"select_{action.lower()}"
    )

    # Exactly this candidate is being tested.
    model.Add(selected == 1)

    resources = state.resources
    violations: list[str] = []

    # ------------------------------------------------------------------
    # Operational resource capacities
    # ------------------------------------------------------------------

    beds_waiting_cleaning = max(
        0,
        int(resources.beds_waiting_cleaning),
    )

    hdu_beds_available = max(
        0,
        int(resources.hdu_beds_available),
    )

    transport_queue = max(
        0,
        int(resources.transport_queue),
    )

    bed_manager_available = int(
        bool(resources.bed_manager_available)
    )

    # ------------------------------------------------------------------
    # Action-specific resource constraints
    # ------------------------------------------------------------------

    if action == WAIT:

        # WAIT consumes no scarce operational resource.
        pass

    elif action == EXPEDITE_BED_CLEANING:

        cleaning_consumption = model.NewIntVar(
            0,
            1,
            "cleaning_consumption",
        )

        model.Add(
            cleaning_consumption == selected
        )

        model.Add(
            cleaning_consumption <= beds_waiting_cleaning
        )

        if beds_waiting_cleaning <= 0:
            violations.append(
                "No bed is currently waiting for cleaning."
            )

    elif action == REQUEST_ALTERNATIVE_UNIT:

        alternative_unit_consumption = model.NewIntVar(
            0,
            1,
            "alternative_unit_consumption",
        )

        model.Add(
            alternative_unit_consumption == selected
        )

        model.Add(
            alternative_unit_consumption <= hdu_beds_available
        )

        if hdu_beds_available <= 0:
            violations.append(
                "No alternative HDU capacity is currently available."
            )

    elif action == PRIORITIZE_TRANSPORT:

        transport_consumption = model.NewIntVar(
            0,
            1,
            "transport_consumption",
        )

        model.Add(
            transport_consumption == selected
        )

        model.Add(
            transport_consumption <= transport_queue
        )

        if transport_queue <= 0:
            violations.append(
                "There is no transport queue to prioritize."
            )

    elif action == ESCALATE_TO_BED_MANAGER:

        escalation_consumption = model.NewIntVar(
            0,
            1,
            "bed_manager_consumption",
        )

        model.Add(
            escalation_consumption == selected
        )

        model.Add(
            escalation_consumption <= bed_manager_available
        )

        if not bed_manager_available:
            violations.append(
                "Bed manager is currently unavailable."
            )

    else:

        # Unknown actions are made mathematically infeasible.
        model.Add(selected == 0)

        violations.append(
            f"Unknown action: {action}"
        )

    return model, selected, violations


def check_action_constraints(
    state: EDOperationalState,
    action: str,
) -> ConstraintResult:

    model, _, rule_violations = _build_feasibility_model(
        state,
        action,
    )

    solver = cp_model.CpSolver()

    # Deterministic single-threaded CP-SAT execution.
    solver.parameters.max_time_in_seconds = (
        CP_SAT_TIME_LIMIT_SECONDS
    )
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0

    status = solver.Solve(model)

    status_name = solver.StatusName(status)

    feasible = status in (
        cp_model.OPTIMAL,
        cp_model.FEASIBLE,
    )

    violations = list(rule_violations)

    if not feasible and not violations:
        violations.append(
            "CP-SAT could not find a feasible assignment "
            "under the current operational constraints."
        )

    return ConstraintResult(
        action=action,
        feasible=feasible,
        violations=violations,
        solver_status=status_name,
    )


def filter_feasible_actions(
    state: EDOperationalState,
    actions: list[str],
) -> list[str]:

    feasible: list[str] = []

    for action in actions:

        result = check_action_constraints(
            state,
            action,
        )

        if result.feasible:
            feasible.append(action)

    return feasible
