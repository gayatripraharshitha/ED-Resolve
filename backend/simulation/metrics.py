from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Iterable

from backend.simulation.models import ActionEvaluation, EpisodeOutcome


@dataclass(frozen=True)
class EpisodeMetrics:
    """Normalized metrics for one simulated episode."""

    action: str
    resolved: bool
    resolution_time: float
    boarding_time: float
    escalation_count: int
    resource_conflicts: int


@dataclass(frozen=True)
class AggregateMetrics:
    """Aggregate metrics across repeated simulations."""

    action: str
    episodes: int
    resolution_rate: float
    mean_resolution_time: float
    mean_boarding_time: float
    mean_escalations: float
    mean_resource_conflicts: float


def outcome_to_metrics(outcome: EpisodeOutcome) -> EpisodeMetrics:
    """Convert a detailed episode outcome into evaluation metrics."""

    resolution_time = (
        outcome.resolution_time
        if outcome.resolution_time is not None
        else float("inf")
    )

    return EpisodeMetrics(
        action=outcome.action,
        resolved=outcome.resolved,
        resolution_time=resolution_time,
        boarding_time=outcome.boarding_time,
        escalation_count=outcome.escalation_count,
        resource_conflicts=outcome.resource_conflicts,
    )


def evaluation_to_metrics(
    evaluation: ActionEvaluation,
) -> EpisodeMetrics:
    """Convert a counterfactual action evaluation into metrics."""

    return EpisodeMetrics(
        action=evaluation.action,
        resolved=evaluation.resolution_status == "resolved",
        resolution_time=evaluation.simulated_duration,
        boarding_time=evaluation.boarding_time,
        escalation_count=evaluation.escalation_count,
        resource_conflicts=evaluation.resource_conflicts,
    )


def aggregate_metrics(
    metrics: Iterable[EpisodeMetrics],
) -> list[AggregateMetrics]:
    """
    Aggregate repeated simulation results by action.
    """

    grouped: dict[str, list[EpisodeMetrics]] = {}

    for item in metrics:
        grouped.setdefault(item.action, []).append(item)

    aggregates: list[AggregateMetrics] = []

    for action, items in grouped.items():
        finite_resolution_times = [
            item.resolution_time
            for item in items
            if item.resolution_time != float("inf")
        ]

        aggregates.append(
            AggregateMetrics(
                action=action,
                episodes=len(items),
                resolution_rate=mean(
                    1.0 if item.resolved else 0.0
                    for item in items
                ),
                mean_resolution_time=(
                    mean(finite_resolution_times)
                    if finite_resolution_times
                    else float("inf")
                ),
                mean_boarding_time=mean(
                    item.boarding_time
                    for item in items
                ),
                mean_escalations=mean(
                    item.escalation_count
                    for item in items
                ),
                mean_resource_conflicts=mean(
                    item.resource_conflicts
                    for item in items
                ),
            )
        )

    return aggregates


def utility_score(
    metrics: EpisodeMetrics,
    *,
    alpha: float = 1.0,
    beta: float = 0.5,
    gamma: float = 10.0,
    delta: float = 20.0,
) -> float:
    """
    Compute an operational utility score.

    Lower is better.

    This is an experimental objective for the simulator, not a clinical
    recommendation. We will tune/justify these weights during evaluation.
    """

    unresolved_penalty = 1000.0 if not metrics.resolved else 0.0

    return (
        alpha * metrics.resolution_time
        + beta * metrics.boarding_time
        + gamma * metrics.escalation_count
        + delta * metrics.resource_conflicts
        + unresolved_penalty
    )


def rank_actions(
    evaluations: Iterable[ActionEvaluation],
) -> list[tuple[str, float]]:
    """
    Rank candidate actions according to the experimental utility function.
    """

    scored: list[tuple[str, float]] = []

    for evaluation in evaluations:
        metrics = evaluation_to_metrics(evaluation)

        scored.append(
            (
                evaluation.action,
                utility_score(metrics),
            )
        )

    return sorted(scored, key=lambda item: item[1])