from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from hindsight_client import Hindsight


class EDResolveMemory:
    """
    Hindsight-backed experiential memory for EDResolve.

    Stores operational experiences from ED bottleneck-resolution
    episodes and supports:
        - RETAIN
        - RECALL
        - REFLECT
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        bank_id: str = "edresolve",
    ) -> None:

        self.base_url = (
            base_url
            or os.getenv("HINDSIGHT_API_URL")
            or "http://localhost:8888"
        )

        self.api_key = (
            api_key
            or os.getenv("HINDSIGHT_API_KEY")
        )

        self.bank_id = bank_id

        self.client = Hindsight(
            base_url=self.base_url,
            api_key=self.api_key,
        )

    # ================================================================
    # BANK
    # ================================================================

    def ensure_bank(self) -> Any:
        """
        Create or configure the EDResolve Hindsight memory bank.
        """

        return self.client.create_bank(
            bank_id=self.bank_id,
            name="EDResolve Operational Memory",

            retain_mission=(
                "Extract durable emergency-department operational "
                "experience. Focus on bottlenecks, constraints, "
                "decisions, interventions, failed approaches, "
                "successful approaches, resource conflicts, "
                "escalations, resolution time, and the conditions "
                "under which an intervention worked or failed."
            ),

            reflect_mission=(
                "Help EDResolve reason from previous emergency-"
                "department operational experiences. Prefer concrete "
                "evidence from similar cases. Distinguish successful "
                "and failed interventions and identify the conditions "
                "that affected the outcome."
            ),

            enable_observations=True,
            enable_text_search=True,
            enable_temporal_retrieval=True,
            enable_graph_retrieval=True,
            enable_reranking=True,
        )

    # ================================================================
    # RETAIN
    # ================================================================

    def retain_experience(
        self,
        experience: dict[str, Any],
        *,
        timestamp: datetime | None = None,
        tags: list[str] | None = None,
    ) -> Any:
        """
        Store a complete ED resolution episode in Hindsight.

        The complete episode is retained rather than reducing it
        to a small manually written summary.
        """

        occurred_at = (
            timestamp
            or datetime.now(timezone.utc)
        )

        content = json.dumps(
            experience,
            indent=2,
            ensure_ascii=False,
            default=str,
        )

        metadata = {
            "system": "edresolve",
            "memory_type": "resolution_experience",

            "bottleneck_type": str(
                experience.get(
                    "bottleneck_type",
                    "unknown",
                )
            ),

            "resolution_status": str(
                experience.get(
                    "resolution_status",
                    "unknown",
                )
            ),
        }

        return self.client.retain(
            bank_id=self.bank_id,
            content=content,
            timestamp=occurred_at,

            context=(
                "Emergency Department operational "
                "resolution episode"
            ),

            metadata=metadata,

            tags=(
                tags
                or [
                    "edresolve",
                    "resolution-experience",
                ]
            ),
        )

    # ================================================================
    # RECALL
    # ================================================================

    def recall_experiences(
        self,
        query: str,
        *,
        max_tokens: int = 2500,
        budget: str = "low",
        tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve previous experiences relevant to the
        current ED operational state.
        """

        response = self.client.recall(
            bank_id=self.bank_id,
            query=query,

            max_tokens=max_tokens,
            budget=budget,

            include_entities=True,
            include_chunks=False,
            include_source_facts=False,

            tags=tags,
            prefer_observations=True,
        )

        return [
            {
                "id": result.id,
                "text": result.text,
                "type": result.type,
                "context": result.context,

                "occurred_start": (
                    result.occurred_start
                ),

                "occurred_end": (
                    result.occurred_end
                ),

                "document_id": (
                    result.document_id
                ),

                "metadata": result.metadata,
                "tags": result.tags,
                "entities": result.entities,

                "scores": (
                    result.scores.model_dump()
                    if result.scores is not None
                    else None
                ),

                "source_fact_ids": (
                    result.source_fact_ids
                ),
            }
            for result in response.results
        ]

    # ================================================================
    # REFLECT
    # ================================================================

    def reflect_on_experiences(
        self,
        query: str,
        *,
        budget: str = "low",
        max_tokens: int = 500,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Synthesize lessons from previous experiences.

        Reflection is deliberately constrained because EDResolve
        runs on a Groq account with a limited TPM budget.

        The observation-search budget is also explicitly limited.
        """

        response = self.client.reflect(
            bank_id=self.bank_id,

            query=query,

            budget=budget,

            max_tokens=max_tokens,

            tags=tags,

            # Avoid additional fact payloads.
            include_facts=False,

            # Avoid tool-call payloads.
            include_tool_calls=False,
            include_tool_call_output=False,

            # IMPORTANT:
            # This controls the internal observation-search
            # token budget used during reflection.
            reflect_search_observations_max_tokens=500,

            # Avoid attaching large entity payloads.
            reflect_search_observations_include_entities=False,
        )

        return {
            "text": response.text,

            "structured_output": (
                response.structured_output
            ),

            "structured_output_error": (
                response.structured_output_error
            ),

            "based_on": (
                response.based_on.model_dump()
                if response.based_on is not None
                else None
            ),
        }

    # ================================================================
    # CLOSE
    # ================================================================

    def close(self) -> None:
        """
        Close the underlying Hindsight client.
        """

        self.client.close()