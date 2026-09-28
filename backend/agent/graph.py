from __future__ import annotations

from typing import Any, Callable

from langgraph.graph import END, START, StateGraph

from backend.agent.state import EDResolveState

from backend.agent.nodes import (
    build_world_model,
    identify_bottleneck,
    build_memory_query,
    recall_experiences,
    generate_candidate_actions,
    handle_agent_error,
)

from backend.agent.decision import (
    validate_candidates,
    run_counterfactual_simulations,
    select_action,
)

from backend.agent.outcome import (
    execute_selected_action,
    analyze_outcome,
    build_experience_for_hindsight,
)

from backend.agent.memory import (
    retain_completed_experience,
)


# ---------------------------------------------------------------------------
# Generic node wrapper
# ---------------------------------------------------------------------------

def _run_node(
    node_fn: Callable[[EDResolveState], dict[str, Any]],
    state: EDResolveState,
) -> dict[str, Any]:

    try:
        return node_fn(state)

    except Exception as exc:

        return {
            "error": str(exc),
            "audit_log": [
                {
                    "stage": "error",
                    "message": f"{node_fn.__name__} failed.",
                    "data": {
                        "node": node_fn.__name__,
                        "exception": str(exc),
                    },
                }
            ],
        }


# ---------------------------------------------------------------------------
# Agent nodes
# ---------------------------------------------------------------------------

def world_model_node(
    state: EDResolveState,
) -> dict[str, Any]:
    return _run_node(
        build_world_model,
        state,
    )


def bottleneck_node(
    state: EDResolveState,
) -> dict[str, Any]:
    return _run_node(
        identify_bottleneck,
        state,
    )


def memory_query_node(
    state: EDResolveState,
) -> dict[str, Any]:
    return _run_node(
        build_memory_query,
        state,
    )


def recall_node(
    state: EDResolveState,
) -> dict[str, Any]:
    return _run_node(
        recall_experiences,
        state,
    )


def candidate_node(
    state: EDResolveState,
) -> dict[str, Any]:
    return _run_node(
        generate_candidate_actions,
        state,
    )


def constraint_node(
    state: EDResolveState,
) -> dict[str, Any]:
    return _run_node(
        validate_candidates,
        state,
    )


def counterfactual_node(
    state: EDResolveState,
) -> dict[str, Any]:
    return _run_node(
        run_counterfactual_simulations,
        state,
    )


def decision_node(
    state: EDResolveState,
) -> dict[str, Any]:
    return _run_node(
        select_action,
        state,
    )


def execution_node(
    state: EDResolveState,
) -> dict[str, Any]:
    return _run_node(
        execute_selected_action,
        state,
    )


def outcome_node(
    state: EDResolveState,
) -> dict[str, Any]:
    return _run_node(
        analyze_outcome,
        state,
    )


def experience_node(
    state: EDResolveState,
) -> dict[str, Any]:
    return _run_node(
        build_experience_for_hindsight,
        state,
    )


def retain_node(
    state: EDResolveState,
) -> dict[str, Any]:
    return _run_node(
        retain_completed_experience,
        state,
    )


def error_node(
    state: EDResolveState,
) -> dict[str, Any]:
    return handle_agent_error(state)


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def _route(
    state: EDResolveState,
    next_node: str,
) -> str:

    if state.get("error"):
        return "error"

    return next_node


def route_world_model(
    state: EDResolveState,
) -> str:
    return _route(
        state,
        "bottleneck",
    )


def route_bottleneck(
    state: EDResolveState,
) -> str:
    return _route(
        state,
        "memory_query",
    )


def route_memory_query(
    state: EDResolveState,
) -> str:
    return _route(
        state,
        "recall",
    )


def route_recall(
    state: EDResolveState,
) -> str:
    return _route(
        state,
        "candidates",
    )


def route_candidates(
    state: EDResolveState,
) -> str:
    return _route(
        state,
        "constraints",
    )


def route_constraints(
    state: EDResolveState,
) -> str:
    return _route(
        state,
        "counterfactuals",
    )


def route_counterfactuals(
    state: EDResolveState,
) -> str:
    return _route(
        state,
        "decision",
    )


def route_decision(
    state: EDResolveState,
) -> str:
    return _route(
        state,
        "execution",
    )


def route_execution(
    state: EDResolveState,
) -> str:
    return _route(
        state,
        "outcome",
    )


def route_outcome(
    state: EDResolveState,
) -> str:
    return _route(
        state,
        "experience",
    )


def route_experience(
    state: EDResolveState,
) -> str:
    return _route(
        state,
        "retain",
    )


def route_retain(
    state: EDResolveState,
) -> str:
    return _route(
        state,
        "end",
    )


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_agent_graph():

    graph = StateGraph(
        EDResolveState
    )

    # ---------------------------------------------------------
    # Register nodes
    # ---------------------------------------------------------

    graph.add_node(
        "world_model",
        world_model_node,
    )

    graph.add_node(
        "bottleneck",
        bottleneck_node,
    )

    graph.add_node(
        "memory_query",
        memory_query_node,
    )

    graph.add_node(
        "recall",
        recall_node,
    )

    graph.add_node(
        "candidates",
        candidate_node,
    )

    graph.add_node(
        "constraints",
        constraint_node,
    )

    graph.add_node(
        "counterfactuals",
        counterfactual_node,
    )

    graph.add_node(
        "decision",
        decision_node,
    )

    graph.add_node(
        "execution",
        execution_node,
    )

    graph.add_node(
        "outcome",
        outcome_node,
    )

    graph.add_node(
        "experience",
        experience_node,
    )

    graph.add_node(
        "retain",
        retain_node,
    )

    graph.add_node(
        "error",
        error_node,
    )

    # ---------------------------------------------------------
    # Entry
    # ---------------------------------------------------------

    graph.add_edge(
        START,
        "world_model",
    )

    # ---------------------------------------------------------
    # World model
    # ---------------------------------------------------------

    graph.add_conditional_edges(
        "world_model",
        route_world_model,
        {
            "bottleneck": "bottleneck",
            "error": "error",
        },
    )

    # ---------------------------------------------------------
    # Bottleneck
    # ---------------------------------------------------------

    graph.add_conditional_edges(
        "bottleneck",
        route_bottleneck,
        {
            "memory_query": "memory_query",
            "error": "error",
        },
    )

    # ---------------------------------------------------------
    # Memory query
    # ---------------------------------------------------------

    graph.add_conditional_edges(
        "memory_query",
        route_memory_query,
        {
            "recall": "recall",
            "error": "error",
        },
    )

    # ---------------------------------------------------------
    # Hindsight recall
    # ---------------------------------------------------------

    graph.add_conditional_edges(
        "recall",
        route_recall,
        {
            "candidates": "candidates",
            "error": "error",
        },
    )

    # ---------------------------------------------------------
    # Candidate generation
    # ---------------------------------------------------------

    graph.add_conditional_edges(
        "candidates",
        route_candidates,
        {
            "constraints": "constraints",
            "error": "error",
        },
    )

    # ---------------------------------------------------------
    # Hard constraints
    # ---------------------------------------------------------

    graph.add_conditional_edges(
        "constraints",
        route_constraints,
        {
            "counterfactuals": "counterfactuals",
            "error": "error",
        },
    )

    # ---------------------------------------------------------
    # Counterfactual simulation
    # ---------------------------------------------------------

    graph.add_conditional_edges(
        "counterfactuals",
        route_counterfactuals,
        {
            "decision": "decision",
            "error": "error",
        },
    )

    # ---------------------------------------------------------
    # Deterministic decision
    # ---------------------------------------------------------

    graph.add_conditional_edges(
        "decision",
        route_decision,
        {
            "execution": "execution",
            "error": "error",
        },
    )

    # ---------------------------------------------------------
    # Execute selected intervention
    # ---------------------------------------------------------

    graph.add_conditional_edges(
        "execution",
        route_execution,
        {
            "outcome": "outcome",
            "error": "error",
        },
    )

    # ---------------------------------------------------------
    # Expected vs actual
    # ---------------------------------------------------------

    graph.add_conditional_edges(
        "outcome",
        route_outcome,
        {
            "experience": "experience",
            "error": "error",
        },
    )

    # ---------------------------------------------------------
    # Build Hindsight experience
    # ---------------------------------------------------------

    graph.add_conditional_edges(
        "experience",
        route_experience,
        {
            "retain": "retain",
            "error": "error",
        },
    )

    # ---------------------------------------------------------
    # Hindsight retain
    # ---------------------------------------------------------

    graph.add_conditional_edges(
        "retain",
        route_retain,
        {
            "end": END,
            "error": "error",
        },
    )

    # ---------------------------------------------------------
    # Terminal error path
    # ---------------------------------------------------------

    graph.add_edge(
        "error",
        END,
    )

    return graph.compile()


# ---------------------------------------------------------------------------
# Compiled graph
# ---------------------------------------------------------------------------

agent_graph = build_agent_graph()


def get_agent_graph():
    return agent_graph