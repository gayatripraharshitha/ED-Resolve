
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from backend.agent.graph import get_agent_graph
from backend.simulation.ed_simulator import EDTransferSimulator


app = FastAPI(title="EDResolve Dashboard")
STATIC_DIR = Path(__file__).resolve().parent / "static"


def serialize(value: Any) -> Any:
    if value is None:
        return None

    if hasattr(value, "model_dump"):
        return serialize(value.model_dump())

    if isinstance(value, dict):
        return {
            str(k): serialize(v)
            for k, v in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [serialize(v) for v in value]

    if hasattr(value, "value") and not isinstance(
        value,
        (str, int, float, bool),
    ):
        try:
            return value.value
        except Exception:
            pass

    return value


def build_raw_state(mode: str):
    seed = 45 if mode == "known" else 53

    simulator = EDTransferSimulator(seed=seed)

    raw_state = simulator.create_deadlock_state(
        case_id=(
            "ED-DEMO-KNOWN"
            if mode == "known"
            else "ED-DEMO-NOVEL"
        ),
        scenario_type="ICU_BED_CLEANING",
    )

    if mode == "novel":
        raw_state.scenario_type = (
            "CASCADE_RESOURCE_COLLAPSE_X53"
        )

        resources = raw_state.resources

        resources.icu_beds_available = 0
        resources.hdu_beds_available = 0
        resources.transport_teams_available = 0
        resources.beds_waiting_cleaning = 0
        resources.transport_queue = 0
        resources.bed_manager_available = False
        resources.senior_coordinator_available = False

        for case in getattr(
            raw_state,
            "transfer_cases",
            [],
        ):
            if hasattr(case, "bed_blocked"):
                case.bed_blocked = False

            if hasattr(case, "transport_blocked"):
                case.transport_blocked = False

            if hasattr(case, "coordination_blocked"):
                case.coordination_blocked = False

    return raw_state


@app.get("/")
async def index():
    return FileResponse(
        STATIC_DIR / "index.html"
    )


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "service": "EDResolve",
    }


@app.get("/api/demo/{mode}")
async def demo(mode: str):
    if mode not in {"known", "novel"}:
        raise HTTPException(
            status_code=400,
            detail="mode must be known or novel",
        )

    try:
        raw_state = build_raw_state(mode)

        graph = get_agent_graph()

        result = await graph.ainvoke(
            {
                "case_id": (
                    "ED-DEMO-KNOWN"
                    if mode == "known"
                    else "ED-DEMO-NOVEL"
                ),
                "timestamp": (
                    datetime.now(timezone.utc)
                    .isoformat()
                ),
                "raw_state": raw_state,
            }
        )

        decision = result.get("decision")
        applicability = result.get(
            "experience_applicability",
            {},
        )
        bottleneck = result.get(
            "bottleneck",
            {},
        )
        world_model = result.get(
            "world_model",
            {},
        )
        safe_mode = result.get(
            "safe_mode",
            {},
        )

        simulation_results = result.get(
            "counterfactual_results",
            [],
        )

        if not simulation_results and decision is not None:
            simulation_results = getattr(
                decision,
                "simulation_results",
                [],
            )

        selected_action = None

        if decision is not None:
            selected_action = getattr(
                decision,
                "selected_action",
                None,
            )

        return serialize(
            {
                "ok": True,
                "mode": mode,
                "scenario": raw_state.scenario_type,
                "raw_state": raw_state,
                "world_model": world_model,
                "bottleneck": bottleneck,
                "applicability": applicability,
                "candidates": result.get(
                    "candidate_actions",
                    [],
                ),
                "constraints": result.get(
                    "constraint_results",
                    [],
                ),
                "simulation_results": simulation_results,
                "decision": decision,
                "selected_action": selected_action,
                "safe_mode": safe_mode,
                "outcome": result.get(
                    "outcome"
                ),
                "experience_to_retain": result.get(
                    "experience_to_retain"
                ),
                "error": result.get("error"),
            }
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc
