from __future__ import annotations

import os
from typing import Any

from backend.agent.state import (
    AuditEvent,
    EDResolveState,
)
from backend.memory.hindsight_memory import EDResolveMemory


DEFAULT_BANK_ID = os.getenv(
    "HINDSIGHT_BANK_ID",
    "edresolve",
)


def _audit(
    stage: str,
    message: str,
    data: dict[str, Any] | None = None,
) -> AuditEvent:
    return AuditEvent(
        stage=stage,
        message=message,
        data=data or {},
    )


def retain_completed_experience(
    state: EDResolveState,
) -> dict[str, Any]:

    experience = state.get(
        "experience_to_retain"
    )

    if not experience:
        raise ValueError(
            "experience_to_retain is required before Hindsight retention."
        )

    memory = EDResolveMemory(
        bank_id=DEFAULT_BANK_ID,
    )

    try:
        problem = experience.get(
            "problem",
            {},
        ) or {}

        bottleneck = experience.get(
            "bottleneck",
            {},
        ) or {}

        decision = experience.get(
            "decision",
            {},
        ) or {}

        learning = experience.get(
            "learning",
            {},
        ) or {}

        realized_outcome = experience.get(
            "realized_simulated_outcome",
            experience.get(
                "actual_outcome",
                {},
            ),
        ) or {}

        case_id = str(
            experience.get(
                "case_id",
                "unknown-case",
            )
        )

        scenario_type = str(
            problem.get(
                "scenario_type",
                "UNKNOWN",
            )
        )

        bottleneck_type = str(
            bottleneck.get(
                "bottleneck_type",
                "UNKNOWN",
            )
        )

        dominant_dependency = str(
            bottleneck.get(
                "dominant_dependency",
                "UNKNOWN",
            )
        )

        selected_action = str(
            decision.get(
                "selected_action",
                "UNKNOWN",
            )
        )

        resolved = bool(
            realized_outcome.get(
                "resolved",
                learning.get(
                    "resolved",
                    False,
                ),
            )
        )

        prediction_error = learning.get(
            "prediction_error",
            0.0,
        )

        # -------------------------------------------------------------
        # Tags
        #
        # These are deliberately derived from the operational episode
        # rather than being arbitrary labels.
        # -------------------------------------------------------------

        tags = [
            "edresolve",
            "operational-experience",
            scenario_type.lower(),
            bottleneck_type.lower(),
            dominant_dependency.lower(),
            selected_action.lower(),
        ]

        if resolved:
            tags.append("successful")
        else:
            tags.append("failed")

        # Remove duplicates while preserving order.
        tags = list(
            dict.fromkeys(
                tag
                for tag in tags
                if tag
                and tag != "unknown"
            )
        )

        # -------------------------------------------------------------
        # Hindsight owns the serialization of the complete episode.
        #
        # We intentionally pass the entire structured experience
        # instead of reducing it to a manually constructed summary.
        # -------------------------------------------------------------

        retain_result = memory.retain_experience(
            experience=experience,
            tags=tags,
        )

        return {
            "audit_log": [
                _audit(
                    stage="retain",
                    message=(
                        "Completed operational episode retained "
                        "in Hindsight."
                    ),
                    data={
                        "case_id": case_id,
                        "scenario_type": scenario_type,
                        "bottleneck_type": bottleneck_type,
                        "selected_action": selected_action,
                        "resolved": resolved,
                        "prediction_error": prediction_error,
                        "tags": tags,
                        "hindsight_success": getattr(
                            retain_result,
                            "success",
                            None,
                        ),
                        "hindsight_items_count": getattr(
                            retain_result,
                            "items_count",
                            None,
                        ),
                    },
                )
            ],
            "error": None,
        }

    finally:
        memory.close()