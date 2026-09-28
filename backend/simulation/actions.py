from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from backend.simulation.models import EDOperationalState


# Actions the first EDResolve prototype can consider.
WAIT = "WAIT"
EXPEDITE_BED_CLEANING = "EXPEDITE_BED_CLEANING"
REQUEST_ALTERNATIVE_UNIT = "REQUEST_ALTERNATIVE_UNIT"
PRIORITIZE_TRANSPORT = "PRIORITIZE_TRANSPORT"
ESCALATE_TO_BED_MANAGER = "ESCALATE_TO_BED_MANAGER"


@dataclass(frozen=True)
class ActionSpec:
    """
    Description of one operational intervention.
    """

    name: str
    description: str
    cost: float
    requires_bed_manager: bool = False
    requires_transport: bool = False


ACTION_SPECS: dict[str, ActionSpec] = {
    WAIT: ActionSpec(
        name=WAIT,
        description="Take no escalation action and continue normal operations.",
        cost=0.0,
    ),

    EXPEDITE_BED_CLEANING: ActionSpec(
        name=EXPEDITE_BED_CLEANING,
        description="Prioritize preparation of a bed currently waiting for cleaning.",
        cost=1.0,
    ),

    REQUEST_ALTERNATIVE_UNIT: ActionSpec(
        name=REQUEST_ALTERNATIVE_UNIT,
        description="Request an available alternative destination unit.",
        cost=2.0,
    ),

    PRIORITIZE_TRANSPORT: ActionSpec(
        name=PRIORITIZE_TRANSPORT,
        description="Move the transfer to the front of the transport queue.",
        cost=1.5,
        requires_transport=True,
    ),

    ESCALATE_TO_BED_MANAGER: ActionSpec(
        name=ESCALATE_TO_BED_MANAGER,
        description="Escalate the unresolved transfer to the bed manager.",
        cost=3.0,
        requires_bed_manager=True,
    ),
}


def available_actions(state: EDOperationalState) -> list[str]:
    """
    Return actions that are structurally possible in the current state.

    This is intentionally a lightweight feasibility filter.
    The simulator will determine the actual outcome of each action.
    """

    actions: list[str] = [WAIT]

    resources = state.resources

    if resources.beds_waiting_cleaning > 0:
        actions.append(EXPEDITE_BED_CLEANING)

    if resources.hdu_beds_available > 0:
        actions.append(REQUEST_ALTERNATIVE_UNIT)

    if resources.transport_teams_available > 0:
        actions.append(PRIORITIZE_TRANSPORT)

    if resources.bed_manager_available:
        actions.append(ESCALATE_TO_BED_MANAGER)

    return actions


def get_action_spec(action: str) -> ActionSpec:
    """
    Return metadata for an action.
    """

    try:
        return ACTION_SPECS[action]
    except KeyError as exc:
        raise ValueError(f"Unknown EDResolve action: {action}") from exc


def describe_action(action: str) -> str:
    """
    Human-readable description used later by the agent/UI.
    """

    return get_action_spec(action).description