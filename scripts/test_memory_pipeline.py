

import socket
import subprocess
import time
from datetime import datetime, timezone

from backend.agent.graph import get_agent_graph
from backend.memory.hindsight_memory import EDResolveMemory
from frontend.server import build_raw_state


HOST = "127.0.0.1"
PORT = 8888
BANK_ID = "edresolve"


def hindsight_running() -> bool:
    try:
        with socket.create_connection(
            (HOST, PORT),
            timeout=1,
        ):
            return True
    except OSError:
        return False


def start_hindsight() -> subprocess.Popen | None:
    if hindsight_running():
        print("Hindsight API already running.")
        return None

    print(
        "Starting Hindsight API on "
        "127.0.0.1:8888..."
    )

    process = subprocess.Popen(
        [
            "hindsight-api",
            "--host",
            HOST,
            "--port",
            str(PORT),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    deadline = time.time() + 20

    while time.time() < deadline:

        if hindsight_running():
            print(
                "Hindsight API started successfully."
            )
            return process

        if process.poll() is not None:
            raise RuntimeError(
                "hindsight-api exited before "
                "port 8888 became available."
            )

        time.sleep(0.5)

    process.terminate()

    raise RuntimeError(
        "Hindsight API did not become available "
        "within 20 seconds."
    )


def retain_test_memories() -> None:

    memory = EDResolveMemory(
        base_url=f"http://{HOST}:{PORT}",
        bank_id=BANK_ID,
    )

    try:

        print(
            "Ensuring Hindsight bank exists..."
        )

        memory.ensure_bank()

        experiences = [
            (
                "EXPEDITE_BED_CLEANING",
                "unresolved",
                "memory-test-failure-1",
                (
                    "Expediting bed cleaning failed "
                    "under the ICU bed cleaning bottleneck."
                ),
            ),
            (
                "EXPEDITE_BED_CLEANING",
                "unresolved",
                "memory-test-failure-2",
                (
                    "Expediting bed cleaning failed "
                    "again under the same ICU bed cleaning dependency."
                ),
            ),
            (
                "ESCALATE_TO_BED_MANAGER",
                "resolved",
                "memory-test-success-1",
                (
                    "Escalating to the bed manager successfully "
                    "resolved the ICU bed cleaning bottleneck."
                ),
            ),
            (
                "ESCALATE_TO_BED_MANAGER",
                "resolved",
                "memory-test-success-2",
                (
                    "Escalating to the bed manager successfully "
                    "resolved a similar ICU bed cleaning episode."
                ),
            ),
        ]

        print()
        print(
            "Retaining controlled experiences..."
        )

        for (
            action,
            status,
            case_id,
            lesson,
        ) in experiences:

            resolved = (
                status == "resolved"
            )

            experience = {
                "episode_id": case_id,

                "case_id": case_id,

                "timestamp": datetime.now(
                    timezone.utc
                ).isoformat(),

                "problem": {
                    "scenario_type": (
                        "ICU_BED_CLEANING"
                    ),
                    "description": (
                        "Controlled Memory Matters "
                        "experiment."
                    ),
                },

                "bottleneck": {
                    "bottleneck_type": (
                        "ICU_BED_CLEANING"
                    ),
                    "dominant_dependency": (
                        "BED_CLEANING"
                    ),
                },

                "decision": {
                    "selected_action": action,
                },

                "realized_simulated_outcome": {
                    "resolved": resolved,
                    "resolution_time": (
                        60.0
                        if resolved
                        else 95.0
                    ),
                },

                "resolution_status": status,

                "learning": {
                    "resolved": resolved,
                    "prediction_error": 1.0,
                    "resolution_status": status,
                },

                "lesson": lesson,
            }

            tags = [
                "edresolve",
                "operational-experience",
                "icu_bed_cleaning",
                "bed_cleaning",
                action.lower(),
                (
                    "successful"
                    if resolved
                    else "failed"
                ),
                "memory-matters",
            ]

            memory.retain_experience(
                experience=experience,
                tags=tags,
            )

            print(
                f"  {action:<32} "
                f"{status}"
            )

    finally:

        memory.close()


def run_actual_pipeline() -> None:

    print()
    print("-" * 70)
    print(
        "RUNNING ACTUAL ED RESOLVE PIPELINE"
    )
    print("-" * 70)

    raw_state = build_raw_state(
        "known"
    )

    graph = get_agent_graph()

    result = graph.invoke(
        {
        "case_id": "ED-MEMORY-MATTERS",
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
        "raw_state": raw_state,
        "memory_recall_tags": [
            "memory-matters",
        ],
        }
    )

    recalled = result.get(
        "recalled_experiences",
        [],
    )

    applicability = result.get(
        "experience_applicability",
        {},
    )

    decision = result.get(
        "decision"
    )

    # ---------------------------------------------------------
    # Hindsight recall summary
    # ---------------------------------------------------------

    print()
    print("HINDSIGHT RECALL")

    print(
        "Recalled experiences:",
        len(recalled),
    )

    print(
        "Applicability:",
        applicability.get(
            "mode"
        ),
    )

    print(
        "Global score:",
        applicability.get(
            "global_score"
        ),
    )

    print(
        "Bottleneck matches:",
        applicability.get(
            "bottleneck_matches"
        ),
    )

    print(
        "Scenario matches:",
        applicability.get(
            "scenario_matches"
        ),
    )

    # ---------------------------------------------------------
    # IMPORTANT:
    # Inspect exactly what Hindsight returned.
    # ---------------------------------------------------------

    print()
    print(
        "RECALLED MEMORY DETAILS"
    )
    print(
        "-" * 70
    )

    for index, memory in enumerate(
        recalled,
        start=1,
    ):

        print()
        print(
            f"MEMORY {index}"
        )

        if not isinstance(
            memory,
            dict,
        ):
            print(
                "Type:",
                type(memory).__name__,
            )

            print(
                "Value:",
                memory,
            )

            continue

        memory_id = memory.get(
            "id",
            memory.get(
                "memory_id"
            ),
        )

        document_id = memory.get(
            "document_id"
        )

        metadata = memory.get(
            "metadata",
            {},
        )

        if not isinstance(
            metadata,
            dict,
        ):
            metadata = {}

        print(
            "ID:",
            memory_id,
        )

        print(
            "Document:",
            document_id,
        )

        print(
            "Memory type:",
            metadata.get(
                "memory_type"
            ),
        )

        print(
            "Resolution status:",
            metadata.get(
                "resolution_status"
            ),
        )

        print(
            "Bottleneck:",
            metadata.get(
                "bottleneck_type"
            ),
        )

        print(
            "Tags:",
            memory.get(
                "tags",
                [],
            ),
        )

        print(
            "Scores:",
            memory.get(
                "scores",
                {},
            ),
        )

        text = str(
            memory.get(
                "text",
                "",
            )
        )

        print(
            "Text:",
            text[:500],
        )

    # ---------------------------------------------------------
    # Candidate actions
    # ---------------------------------------------------------

    candidates = result.get(
        "candidate_actions",
        [],
    )

    print()
    print(
        "CANDIDATE ACTIONS"
    )

    for candidate in candidates:

        print(
            " ",
            getattr(
                candidate,
                "action",
                candidate,
            ),
        )

    # ---------------------------------------------------------
    # Counterfactual simulation
    # ---------------------------------------------------------

    simulations = result.get(
        "counterfactual_results",
        [],
    )

    print()
    print(
        "COUNTERFACTUAL SIMULATION"
    )

    for result_item in simulations:

        print(
            f"  "
            f"{result_item.action:<32}"
            f" utility={result_item.utility_score}"
            f" feasible={result_item.feasible}"
            f" resolved={result_item.resolved}"
        )

    # ---------------------------------------------------------
    # Final decision
    # ---------------------------------------------------------

    print()
    print("=" * 70)
    print(
        "FINAL DECISION"
    )
    print("=" * 70)

    if decision is None:

        print(
            "No autonomous decision."
        )

        return

    print(
        "Selected action:",
        decision.selected_action,
    )

    print()
    print(
        "Experience support:"
    )

    print(
        decision.experience_support
    )

    print()
    print(
        "Experience-adjusted scores:"
    )

    print(
        decision.experience_adjusted_scores
    )

    print()
    print(
        "Decision reason:"
    )

    print(
        decision.selection_reason
    )

    # ---------------------------------------------------------
    # Diagnostic
    # ---------------------------------------------------------

    print()
    print("=" * 70)
    print(
        "DIAGNOSTIC"
    )
    print("=" * 70)

    support = decision.experience_support

    print(
        "Failure evidence detected:",
        support.get(
            "EXPEDITE_BED_CLEANING",
            0.0,
        ) < 0,
    )

    print(
        "Success evidence detected:",
        support.get(
            "ESCALATE_TO_BED_MANAGER",
            0.0,
        ) > 0,
    )

    # ---------------------------------------------------------
    # Compare recalled controlled memories
    # ---------------------------------------------------------

    controlled_failures = 0
    controlled_successes = 0

    for memory in recalled:

        if not isinstance(
            memory,
            dict,
        ):
            continue

        tags = memory.get(
            "tags",
            [],
        )

        if not isinstance(
            tags,
            list,
        ):
            tags = []

        normalized_tags = {
            str(tag).strip().lower()
            for tag in tags
        }

        metadata = memory.get(
            "metadata",
            {},
        )

        if not isinstance(
            metadata,
            dict,
        ):
            metadata = {}

        status = str(
            metadata.get(
                "resolution_status",
                "",
            )
        ).strip().lower()

        if (
            "memory-matters"
            in normalized_tags
            and (
                "expedite_bed_cleaning"
                in normalized_tags
            )
            and (
                status == "unresolved"
                or "failed"
                in normalized_tags
            )
        ):
            controlled_failures += 1

        if (
            "memory-matters"
            in normalized_tags
            and (
                "escalate_to_bed_manager"
                in normalized_tags
            )
            and (
                status == "resolved"
                or "successful"
                in normalized_tags
            )
        ):
            controlled_successes += 1

    print()
    print(
        "Controlled failure memories recalled:",
        controlled_failures,
    )

    print(
        "Controlled success memories recalled:",
        controlled_successes,
    )


def main() -> None:

    print()
    print("=" * 70)
    print(
        "ED RESOLVE — REAL HINDSIGHT MEMORY PIPELINE TEST"
    )
    print("=" * 70)

    start_hindsight()

    retain_test_memories()

    run_actual_pipeline()

    print()
    print("=" * 70)
    print(
        "TEST COMPLETE"
    )
    print("=" * 70)


if __name__ == "__main__":
    main()