from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import networkx as nx


@dataclass(frozen=True)
class DependencyAnalysis:
    """
    Graph-derived operational dependency analysis.

    `criticality` combines operational pressure with structural
    importance in the current dependency graph.
    """

    graph: nx.DiGraph
    node_pressure: dict[str, float]
    betweenness: dict[str, float]
    criticality: dict[str, float]
    dominant_dependency: str
    critical_path: list[str]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def build_operational_graph(
    raw_state: Any,
) -> nx.DiGraph:
    """
    Build the current ED operational dependency graph.

    The graph represents operational flow, not clinical decision-making.
    """

    graph = nx.DiGraph()

    resources = raw_state.resources
    active_case = raw_state.active_case()

    # ------------------------------------------------------------------
    # Core operational nodes
    # ------------------------------------------------------------------

    graph.add_node(
        "ED",
        node_type="source",
        pressure=_clamp(
            min(1.0, raw_state.boarding_patients / 10.0)
        ),
    )

    graph.add_node(
        "ICU",
        node_type="destination",
        pressure=(
            1.0
            if resources.icu_beds_available <= 0
            else 0.0
        ),
    )

    graph.add_node(
        "HDU",
        node_type="alternative_destination",
        pressure=(
            1.0
            if resources.hdu_beds_available <= 0
            else 0.0
        ),
    )

    graph.add_node(
        "BED_CLEANING",
        node_type="process",
        pressure=(
            1.0
            if resources.beds_waiting_cleaning > 0
            else 0.0
        ),
    )

    graph.add_node(
        "TRANSPORT",
        node_type="resource",
        pressure=_clamp(
            resources.transport_queue / 5.0
        ),
    )

    graph.add_node(
        "COORDINATION",
        node_type="coordination",
        pressure=(
            0.8
            if not resources.senior_coordinator_available
            else 0.0
        ),
    )

    graph.add_node(
        "BED_MANAGER",
        node_type="coordination",
        pressure=(
            0.8
            if not resources.bed_manager_available
            else 0.0
        ),
    )

    # ------------------------------------------------------------------
    # Standard operational flow
    # ------------------------------------------------------------------

    graph.add_edge(
        "ED",
        "ICU",
        dependency="capacity",
    )

    graph.add_edge(
        "ED",
        "TRANSPORT",
        dependency="transport",
    )

    graph.add_edge(
        "ED",
        "COORDINATION",
        dependency="coordination",
    )

    graph.add_edge(
        "BED_CLEANING",
        "ICU",
        dependency="bed_cleaning",
    )

    graph.add_edge(
        "TRANSPORT",
        "ICU",
        dependency="transport",
    )

    graph.add_edge(
        "COORDINATION",
        "ICU",
        dependency="coordination",
    )

    graph.add_edge(
        "BED_MANAGER",
        "BED_CLEANING",
        dependency="resource_reprioritization",
    )

    # ------------------------------------------------------------------
    # Alternative unit pathway
    # ------------------------------------------------------------------

    if resources.hdu_beds_available > 0:
        graph.add_edge(
            "ED",
            "HDU",
            dependency="alternative_capacity",
        )

    # ------------------------------------------------------------------
    # Active-case-specific dependencies
    # ------------------------------------------------------------------

    if active_case is not None:

        if active_case.bed_blocked:
            graph.add_edge(
                "ED",
                "BED_CLEANING",
                dependency="active_bed_block",
            )

        if active_case.transport_blocked:
            graph.add_edge(
                "ED",
                "TRANSPORT",
                dependency="active_transport_block",
            )

        if active_case.coordination_blocked:
            graph.add_edge(
                "ED",
                "COORDINATION",
                dependency="active_coordination_block",
            )

    # ------------------------------------------------------------------
    # Scenario-specific edges
    # ------------------------------------------------------------------

    scenario = str(
        raw_state.scenario_type
    )

    if scenario == "ICU_BED_CLEANING":
        graph.add_edge(
            "ED",
            "BED_CLEANING",
            dependency="scenario_bed_cleaning",
        )

    elif scenario == "TRANSPORT_BOTTLENECK":
        graph.add_edge(
            "ED",
            "TRANSPORT",
            dependency="scenario_transport",
        )

    elif scenario == "COORDINATION_DEADLOCK":
        graph.add_edge(
            "ED",
            "COORDINATION",
            dependency="scenario_coordination",
        )

    elif scenario == "ALTERNATIVE_UNIT_AVAILABLE":
        graph.add_edge(
            "ED",
            "HDU",
            dependency="scenario_alternative_capacity",
        )

    elif scenario == "MIXED_BOTTLENECK":

        graph.add_edge(
            "ED",
            "BED_CLEANING",
            dependency="mixed_bed_cleaning",
        )

        graph.add_edge(
            "ED",
            "TRANSPORT",
            dependency="mixed_transport",
        )

        graph.add_edge(
            "ED",
            "COORDINATION",
            dependency="mixed_coordination",
        )

    return graph


def analyze_operational_graph(
    graph: nx.DiGraph,
) -> DependencyAnalysis:
    """
    Compute graph-derived dependency importance.

    Criticality =
        0.60 * operational pressure
        +
        0.40 * structural centrality

    This intentionally keeps the score interpretable rather than
    introducing a learned opaque graph model.
    """

    node_pressure: dict[str, float] = {}

    for node, data in graph.nodes(data=True):

        node_pressure[node] = _clamp(
            data.get(
                "pressure",
                0.0,
            )
        )

    betweenness_raw = nx.betweenness_centrality(
        graph,
        normalized=True,
    )

    betweenness = {
        node: _clamp(score)
        for node, score in betweenness_raw.items()
    }

    criticality: dict[str, float] = {}

    for node in graph.nodes:

        pressure = node_pressure.get(
            node,
            0.0,
        )

        structural_importance = betweenness.get(
            node,
            0.0,
        )

        criticality[node] = _clamp(
            0.60 * pressure
            + 0.40 * structural_importance
        )

    dependency_candidates = {
        node: score
        for node, score in criticality.items()
        if graph.nodes[node].get("node_type")
        in {
            "process",
            "resource",
            "coordination",
            "alternative_destination",
        }
    }

    if dependency_candidates:

        dominant_dependency = max(
            dependency_candidates,
            key=dependency_candidates.get,
        )

    else:
        dominant_dependency = "UNKNOWN"

    # ------------------------------------------------------------------
    # Critical operational path
    # ------------------------------------------------------------------

    critical_path: list[str] = []

    candidate_destinations = [
        destination
        for destination in (
            "ICU",
            "HDU",
        )
        if destination in graph
    ]

    if "ED" in graph and candidate_destinations:

        destination = max(
            candidate_destinations,
            key=lambda node: criticality.get(
                node,
                0.0,
            ),
        )

        try:
            paths = list(
                nx.all_simple_paths(
                    graph,
                    source="ED",
                    target=destination,
                    cutoff=5,
                )
            )

            if paths:

                critical_path = max(
                    paths,
                    key=lambda path: sum(
                        criticality.get(
                            node,
                            0.0,
                        )
                        for node in path
                    ),
                )

        except nx.NetworkXNoPath:
            critical_path = []

    return DependencyAnalysis(
        graph=graph,
        node_pressure=node_pressure,
        betweenness=betweenness,
        criticality=criticality,
        dominant_dependency=dominant_dependency,
        critical_path=critical_path,
    )


def build_dependency_analysis(
    raw_state: Any,
) -> DependencyAnalysis:

    graph = build_operational_graph(
        raw_state
    )

    return analyze_operational_graph(
        graph
    )