from __future__ import annotations

from dataclasses import dataclass

from backend.simulation.actions import (
    ESCALATE_TO_BED_MANAGER,
    EXPEDITE_BED_CLEANING,
    PRIORITIZE_TRANSPORT,
    REQUEST_ALTERNATIVE_UNIT,
    WAIT,
)
from backend.simulation.models import EDOperationalState


@dataclass(frozen=True)
class ConstraintResult:
    action: str
    feasible: bool
    violations: list[str]


def check_action_constraints(
    state: EDOperationalState,
    action: str,
) -> ConstraintResult:

    violations: list[str] = []

    resources = state.resources

    if action == WAIT:
        pass

    elif action == EXPEDITE_BED_CLEANING:

        if resources.beds_waiting_cleaning <= 0:
            violations.append(
                "No bed is currently waiting for cleaning."
            )

    elif action == REQUEST_ALTERNATIVE_UNIT:

        if resources.hdu_beds_available <= 0:
            violations.append(
                "No alternative HDU capacity is currently available."
            )

    elif action == PRIORITIZE_TRANSPORT:

        if resources.transport_queue <= 0:
            violations.append(
                "There is no transport queue to prioritize."
            )

    elif action == ESCALATE_TO_BED_MANAGER:

        if not resources.bed_manager_available:
            violations.append(
                "Bed manager is currently unavailable."
            )

    else:
        violations.append(
            f"Unknown action: {action}"
        )

    return ConstraintResult(
        action=action,
        feasible=len(violations) == 0,
        violations=violations,
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