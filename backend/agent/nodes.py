from __future__ import annotations

import json
import os
import uuid
from typing import Any

from dotenv import load_dotenv
from groq import Groq

from backend.agent.prompts import (
    SYSTEM_PROMPT,
    CANDIDATE_ACTION_PROMPT,
    format_memory_context,
)

from backend.agent.state import (
    EDResolveState,
    BottleneckFingerprint,
    WorldModelSnapshot,
    CandidateAction,
    AuditEvent,
)

from backend.memory.hindsight_memory import EDResolveMemory

from backend.simulation.operational_graph import (
    build_dependency_analysis,
)


load_dotenv()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GROQ_MODEL = os.getenv(
    "EDRESOLVE_REASONING_MODEL",
    "openai/gpt-oss-120b",
)

DEFAULT_BANK_ID = os.getenv(
    "HINDSIGHT_BANK_ID",
    "edresolve",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _audit(
    message: str,
    stage: str,
    data: dict[str, Any] | None = None,
) -> AuditEvent:
    return AuditEvent(
        stage=stage,
        message=message,
        data=data or {},
    )


def _get_groq_client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is missing from the environment."
        )

    return Groq(
        api_key=api_key
    )


def _json_from_response(text: str) -> Any:
    """
    Extract JSON from a normal JSON response or a fenced markdown response.
    """

    cleaned = text.strip()

    if cleaned.startswith("```"):
        lines = cleaned.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        cleaned = "\n".join(lines).strip()

        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    try:
        return json.loads(cleaned)

    except json.JSONDecodeError:

        start = cleaned.find("{")
        end = cleaned.rfind("}")

        if start != -1 and end != -1 and end > start:
            return json.loads(
                cleaned[start:end + 1]
            )

        start = cleaned.find("[")
        end = cleaned.rfind("]")

        if start != -1 and end != -1 and end > start:
            return json.loads(
                cleaned[start:end + 1]
            )

        raise


def _call_reasoning_model(
    system_prompt: str,
    user_prompt: str,
) -> str:

    client = _get_groq_client()

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        temperature=0.15,
        max_tokens=2500,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
    )

    content = response.choices[0].message.content

    if not content:
        raise RuntimeError(
            "GPT-OSS returned an empty response."
        )

    return content


# ---------------------------------------------------------------------------
# 1. Build World Model
# ---------------------------------------------------------------------------

def build_world_model(
    state: EDResolveState,
) -> dict[str, Any]:

    raw = state.get("raw_state")

    if raw is None:
        raise ValueError(
            "EDResolveState.raw_state is required."
        )

    resources = raw.resources

    # ------------------------------------------------------------------
    # Build the operational dependency graph
    # ------------------------------------------------------------------

    analysis = build_dependency_analysis(
        raw
    )

    graph_nodes = [
        str(node)
        for node in analysis.graph.nodes
    ]

    graph_edges = [
        (
            f"{source} -> {target}"
            + (
                f" [{data.get('dependency')}]"
                if data.get("dependency")
                else ""
            )
        )
        for source, target, data
        in analysis.graph.edges(data=True)
    ]

    snapshot = WorldModelSnapshot(
        scenario_type=raw.scenario_type,

        patients_in_ed=raw.patients_in_ed,
        boarding_patients=raw.boarding_patients,
        pending_transfers=raw.pending_transfers,
        unresolved_transfers=raw.unresolved_transfers,

        ICU_beds_available=(
            resources.icu_beds_available
        ),
        HDU_beds_available=(
            resources.hdu_beds_available
        ),

        transport_teams_available=(
            resources.transport_teams_available
        ),
        transport_queue=(
            resources.transport_queue
        ),
        beds_waiting_cleaning=(
            resources.beds_waiting_cleaning
        ),

        bed_manager_available=(
            resources.bed_manager_available
        ),
        senior_coordinator_available=(
            resources.senior_coordinator_available
        ),

        current_time=raw.current_time,

        # NetworkX graph representation
        graph_nodes=graph_nodes,

        graph_edges=graph_edges,

        graph_dominant_dependency=(
            analysis.dominant_dependency
        ),

        graph_criticality={
            str(node): float(score)
            for node, score
            in analysis.criticality.items()
        },

        critical_path=[
            str(node)
            for node in analysis.critical_path
        ],

        process_variant=raw.scenario_type,
    )

    return {
        "world_model": snapshot,

        "audit_log": [
            _audit(
                "Structured ED world model created.",
                "world_model",
                {
                    "scenario_type": raw.scenario_type,

                    "patients_in_ed": (
                        raw.patients_in_ed
                    ),

                    "boarding_patients": (
                        raw.boarding_patients
                    ),

                    "pending_transfers": (
                        raw.pending_transfers
                    ),

                    "graph_nodes": len(
                        graph_nodes
                    ),

                    "graph_edges": len(
                        graph_edges
                    ),

                    "graph_dominant_dependency": (
                        analysis.dominant_dependency
                    ),

                    "critical_path": (
                        analysis.critical_path
                    ),
                },
            )
        ],

        "error": None,
    }


# ---------------------------------------------------------------------------
# 2. Identify Bottleneck
# ---------------------------------------------------------------------------

def identify_bottleneck(
    state: EDResolveState,
) -> dict[str, Any]:

    raw = state.get("raw_state")
    world_model = state.get("world_model")

    if raw is None:
        raise ValueError(
            "raw_state is required."
        )

    if world_model is None:
        raise ValueError(
            "world_model is required."
        )

    resources = raw.resources
    active_case = raw.active_case()

    # ------------------------------------------------------------------
    # NetworkX structural analysis
    # ------------------------------------------------------------------

    graph_analysis = build_dependency_analysis(
        raw
    )

    graph_dependency = (
        graph_analysis.dominant_dependency
    )

    graph_criticality = (
        graph_analysis.criticality.get(
            graph_dependency,
            0.0,
        )
    )

    graph_centrality = (
        graph_analysis.betweenness.get(
            graph_dependency,
            0.0,
        )
    )

    critical_path = [
        str(node)
        for node in graph_analysis.critical_path
    ]

    # ------------------------------------------------------------------
    # Operational pressure signals
    # ------------------------------------------------------------------

    capacity_pressure = 0.0
    transport_pressure = 0.0
    coordination_pressure = 0.0
    process_delay = 0.0
    resource_conflict = 0.0

    dominant_dependency = "UNKNOWN"

    # ------------------------------------------------------------------
    # Capacity pressure
    # ------------------------------------------------------------------

    if resources.icu_beds_available <= 0:
        capacity_pressure = 1.0

    elif resources.hdu_beds_available <= 0:
        capacity_pressure = 0.7

    # ------------------------------------------------------------------
    # Transport pressure
    # ------------------------------------------------------------------

    if resources.transport_queue > 0:
        transport_pressure = min(
            1.0,
            resources.transport_queue / 5.0,
        )

    # ------------------------------------------------------------------
    # Active transfer
    # ------------------------------------------------------------------

    if active_case is not None:

        waiting = active_case.waiting_time(
            raw.current_time
        )

        process_delay = min(
            1.0,
            waiting / 240.0,
        )

        if active_case.bed_blocked:

            capacity_pressure = max(
                capacity_pressure,
                0.9,
            )

            dominant_dependency = "BED"

        elif active_case.transport_blocked:

            transport_pressure = max(
                transport_pressure,
                0.9,
            )

            dominant_dependency = "TRANSPORT"

        elif active_case.coordination_blocked:

            coordination_pressure = 0.95

            dominant_dependency = "COORDINATION"

    # ------------------------------------------------------------------
    # Scenario-specific signal
    # ------------------------------------------------------------------

    if raw.scenario_type == "ICU_BED_CLEANING":

        dominant_dependency = "BED_CLEANING"

        capacity_pressure = max(
            capacity_pressure,
            0.9,
        )

    elif raw.scenario_type == "TRANSPORT_BOTTLENECK":

        dominant_dependency = "TRANSPORT"

        transport_pressure = max(
            transport_pressure,
            0.9,
        )

    elif raw.scenario_type == "COORDINATION_DEADLOCK":

        dominant_dependency = "COORDINATION"

        coordination_pressure = max(
            coordination_pressure,
            0.9,
        )

    elif raw.scenario_type == "ALTERNATIVE_UNIT_AVAILABLE":

        dominant_dependency = "ALTERNATIVE_CAPACITY"

    elif raw.scenario_type == "MIXED_BOTTLENECK":

        if dominant_dependency == "UNKNOWN":

            if graph_dependency != "UNKNOWN":
                dominant_dependency = (
                    graph_dependency
                )

            else:
                dominant_dependency = "MIXED"

    # ------------------------------------------------------------------
    # NetworkX fallback
    # ------------------------------------------------------------------

    if (
        dominant_dependency == "UNKNOWN"
        and graph_dependency != "UNKNOWN"
    ):
        dominant_dependency = (
            graph_dependency
        )

    # ------------------------------------------------------------------
    # Resource conflict
    # ------------------------------------------------------------------

    if (
        resources.transport_queue > 0
        and resources.transport_teams_available <= 0
    ):

        resource_conflict = 1.0

    elif (
        resources.beds_waiting_cleaning > 0
        and resources.icu_beds_available <= 0
    ):

        resource_conflict = 0.8

    # ------------------------------------------------------------------
    # Confidence
    # ------------------------------------------------------------------

    active_pressure_count = sum(
        value >= 0.6
        for value in (
            capacity_pressure,
            transport_pressure,
            coordination_pressure,
            process_delay,
        )
    )

    confidence = min(
        1.0,
        0.55
        + 0.1 * active_pressure_count,
    )

    # Structural graph agreement provides a small
    # confidence boost when the graph supports the
    # heuristic bottleneck classification.

    if (
        graph_dependency == dominant_dependency
        and graph_criticality >= 0.5
    ):

        confidence = min(
            1.0,
            confidence + 0.05,
        )

    fingerprint = BottleneckFingerprint(
        bottleneck_type=raw.scenario_type,

        capacity_pressure=capacity_pressure,

        transport_pressure=(
            transport_pressure
        ),

        coordination_pressure=(
            coordination_pressure
        ),

        process_delay=process_delay,

        resource_conflict=(
            resource_conflict
        ),

        confidence=confidence,

        dominant_dependency=(
            dominant_dependency
        ),

        # NetworkX-derived features

        graph_dominant_dependency=(
            graph_dependency
        ),

        graph_criticality=(
            graph_criticality
        ),

        graph_centrality=(
            graph_centrality
        ),

        critical_path=critical_path,
    )

    return {
        "bottleneck": fingerprint,

        "audit_log": [
            _audit(
                "Operational bottleneck identified.",
                "bottleneck",
                {
                    "type": (
                        raw.scenario_type
                    ),

                    "dominant_dependency": (
                        dominant_dependency
                    ),

                    "confidence": confidence,

                    "graph_dominant_dependency": (
                        graph_dependency
                    ),

                    "graph_criticality": (
                        graph_criticality
                    ),

                    "graph_centrality": (
                        graph_centrality
                    ),

                    "critical_path": (
                        critical_path
                    ),
                },
            )
        ],

        "error": None,
    }


# ---------------------------------------------------------------------------
# 3. Build Hindsight Query
# ---------------------------------------------------------------------------

def build_memory_query(
    state: EDResolveState,
) -> dict[str, Any]:

    raw = state.get("raw_state")
    world_model = state.get("world_model")
    bottleneck = state.get("bottleneck")

    if raw is None:
        raise ValueError(
            "raw_state is required."
        )

    if world_model is None:
        raise ValueError(
            "world_model is required."
        )

    if bottleneck is None:
        raise ValueError(
            "bottleneck is required."
        )

    critical_path_text = (
        " -> ".join(
            bottleneck.critical_path
        )
        if bottleneck.critical_path
        else "UNKNOWN"
    )

    query = (
        "Emergency Department operational resolution experience. "

        f"Scenario={raw.scenario_type}. "

        f"Bottleneck="
        f"{bottleneck.bottleneck_type}. "

        f"Dominant dependency="
        f"{bottleneck.dominant_dependency}. "

        f"Graph dominant dependency="
        f"{bottleneck.graph_dominant_dependency}. "

        f"Graph criticality="
        f"{bottleneck.graph_criticality:.3f}. "

        f"Graph centrality="
        f"{bottleneck.graph_centrality:.3f}. "

        f"Critical operational path="
        f"{critical_path_text}. "

        f"Capacity pressure="
        f"{bottleneck.capacity_pressure:.2f}. "

        f"Transport pressure="
        f"{bottleneck.transport_pressure:.2f}. "

        f"Coordination pressure="
        f"{bottleneck.coordination_pressure:.2f}. "

        f"Process delay="
        f"{bottleneck.process_delay:.2f}. "

        f"Resource conflict="
        f"{bottleneck.resource_conflict:.2f}. "

        f"Patients in ED="
        f"{world_model.patients_in_ed}. "

        f"Boarding patients="
        f"{world_model.boarding_patients}. "

        f"Pending transfers="
        f"{world_model.pending_transfers}. "

        f"ICU beds="
        f"{world_model.ICU_beds_available}. "

        f"HDU beds="
        f"{world_model.HDU_beds_available}. "

        f"Transport queue="
        f"{world_model.transport_queue}. "

        f"Beds waiting cleaning="
        f"{world_model.beds_waiting_cleaning}. "

        "Retrieve prior successful and failed interventions "
        "under structurally similar operational conditions. "
        "Prioritize experiences whose bottleneck, dominant "
        "dependency, critical path, capacity pressure, and "
        "resource conditions resemble the current state."
    )

    return {
        "memory_query": query,

        "audit_log": [
            _audit(
                "Constructed graph-conditioned Hindsight retrieval query.",
                "memory_query",
                {
                    "query_length": len(query),

                    "graph_dependency": (
                        bottleneck.graph_dominant_dependency
                    ),

                    "critical_path": (
                        bottleneck.critical_path
                    ),
                },
            )
        ],

        "error": None,
    }


# ---------------------------------------------------------------------------
# 4. Hindsight Recall
# ---------------------------------------------------------------------------

def recall_experiences(
    state: EDResolveState,
) -> dict[str, Any]:

    query = state.get(
        "memory_query"
    )

    if not query:
        raise ValueError(
            "memory_query is required before recall."
        )

    memory = EDResolveMemory(
        bank_id=DEFAULT_BANK_ID,
    )

    try:

        recalled = memory.recall_experiences(
            query=query,
        )

        experiences: list[dict[str, Any]] = []

        for item in recalled:

            if isinstance(item, dict):

                experiences.append(
                    item
                )

            else:

                experiences.append(
                    {
                        "memory_id": getattr(
                            item,
                            "id",
                            str(uuid.uuid4()),
                        ),

                        "text": getattr(
                            item,
                            "text",
                            str(item),
                        ),

                        "memory_type": getattr(
                            item,
                            "type",
                            "unknown",
                        ),

                        "context": getattr(
                            item,
                            "context",
                            "",
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

        return {
            "recalled_experiences": (
                experiences
            ),

            "audit_log": [
                _audit(
                    "Historical operational experiences recalled from Hindsight.",
                    "recall",
                    {
                        "memory_count": (
                            len(experiences)
                        ),
                    },
                )
            ],

            "error": None,
        }

    finally:

        memory.close()


# ---------------------------------------------------------------------------
# 5. Generate Candidate Actions
# ---------------------------------------------------------------------------

def generate_candidate_actions(
    state: EDResolveState,
) -> dict[str, Any]:

    world_model = state.get(
        "world_model"
    )

    bottleneck = state.get(
        "bottleneck"
    )

    memories = state.get(
        "recalled_experiences",
        [],
    )

    if world_model is None:
        raise ValueError(
            "world_model is required."
        )

    if bottleneck is None:
        raise ValueError(
            "bottleneck is required."
        )

    memory_context = format_memory_context(
        memories
    )

    user_prompt = f"""
CURRENT WORLD MODEL
-------------------
{world_model.model_dump_json(indent=2)}

BOTTLENECK
----------
{bottleneck.model_dump_json(indent=2)}

HISTORICAL EXPERIENCES
---------------------
{memory_context}

TASK
----
Generate 2 to 5 operational intervention candidates.

Return ONLY valid JSON using exactly this structure:

{{
  "candidates": [
    {{
      "action": "ACTION_NAME",
      "rationale": "why this may work",
      "evidence_memory_ids": ["memory-id"],
      "expected_benefit": "expected operational benefit",
      "expected_risk": "main operational risk",
      "confidence": 0.0
    }}
  ]
}}

Allowed actions:
- WAIT
- EXPEDITE_BED_CLEANING
- REQUEST_ALTERNATIVE_UNIT
- PRIORITIZE_TRANSPORT
- ESCALATE_TO_BED_MANAGER

Rules:
- Do not select the final action.
- Do not invent historical memories.
- Use recalled experiences as evidence, not certainty.
- Generate alternatives only when operationally plausible.
"""

    response_text = _call_reasoning_model(
        SYSTEM_PROMPT
        + "\n\n"
        + CANDIDATE_ACTION_PROMPT,
        user_prompt,
    )

    parsed = _json_from_response(
        response_text
    )

    if isinstance(parsed, dict):

        raw_candidates = parsed.get(
            "candidates",
            [],
        )

    elif isinstance(parsed, list):

        raw_candidates = parsed

    else:

        raise ValueError(
            "Unexpected candidate-action response format."
        )

    candidates: list[CandidateAction] = []

    for item in raw_candidates:

        if not isinstance(item, dict):
            continue

        action = str(
            item.get(
                "action",
                "",
            )
        ).strip().upper()

        if not action:
            continue

        try:

            confidence = float(
                item.get(
                    "confidence",
                    0.0,
                )
            )

        except (
            TypeError,
            ValueError,
        ):

            confidence = 0.0

        evidence_ids = item.get(
            "evidence_memory_ids",
            [],
        )

        if not isinstance(
            evidence_ids,
            list,
        ):
            evidence_ids = []

        candidates.append(
            CandidateAction(
                action=action,

                rationale=str(
                    item.get(
                        "rationale",
                        "",
                    )
                ),

                evidence_memory_ids=[
                    str(memory_id)
                    for memory_id
                    in evidence_ids
                ],

                expected_benefit=str(
                    item.get(
                        "expected_benefit",
                        "",
                    )
                ),

                expected_risk=str(
                    item.get(
                        "expected_risk",
                        "",
                    )
                ),

                confidence=max(
                    0.0,
                    min(
                        1.0,
                        confidence,
                    ),
                ),
            )
        )

    if not candidates:

        raise RuntimeError(
            "GPT-OSS produced no usable candidate actions."
        )

    return {
        "candidate_actions": candidates,

        "audit_log": [
            _audit(
                "GPT-OSS generated operational intervention candidates.",
                "candidate_generation",
                {
                    "model": GROQ_MODEL,

                    "candidate_count": (
                        len(candidates)
                    ),
                },
            )
        ],

        "error": None,
    }


# ---------------------------------------------------------------------------
# Error handler
# ---------------------------------------------------------------------------

def handle_agent_error(
    state: EDResolveState,
) -> dict[str, Any]:

    error = state.get(
        "error"
    )

    return {
        "audit_log": [
            _audit(
                "Agent execution encountered an error.",
                "error",
                {
                    "error": error,
                },
            )
        ]
    }