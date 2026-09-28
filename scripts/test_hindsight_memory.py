from backend.memory.hindsight_memory import EDResolveMemory


def main() -> None:
    memory = EDResolveMemory()

    print("\nCreating EDResolve memory bank...")
    try:
        result = memory.ensure_bank()
        print("Bank created/verified:")
        print(result)
    except Exception as exc:
        print("Bank setup error:")
        print(type(exc).__name__, exc)
        return

    experience = {
        "case_id": "ED-DEMO-001",
        "bottleneck_type": "ICU_BED_CLEANING",
        "current_state": {
            "icu_beds_available": 0,
            "hdu_beds_available": 0,
            "transport_teams_available": 1,
            "beds_waiting_cleaning": 1,
            "transport_queue": 1,
        },
        "actions_considered": [
            "WAIT",
            "EXPEDITE_BED_CLEANING",
            "PRIORITIZE_TRANSPORT",
            "ESCALATE_TO_BED_MANAGER",
        ],
        "action_taken": "EXPEDITE_BED_CLEANING",
        "expected_outcome": {
            "resolution": "faster transfer resolution"
        },
        "actual_outcome": {
            "resolution_status": "resolved",
            "resolution_time_minutes": 48.0,
            "escalations": 0,
        },
        "failed_actions": [
            "WAIT"
        ],
        "successful_actions": [
            "EXPEDITE_BED_CLEANING"
        ],
        "resolution_status": "resolved",
        "lesson": (
            "When ICU capacity is blocked by a bed-cleaning delay, "
            "expediting bed preparation resolved the transfer without "
            "requiring escalation."
        ),
    }

    print("\nRetaining experience...")

    try:
        retain_result = memory.retain_experience(
            experience,
            tags=[
                "edresolve",
                "icu-bed-cleaning",
                "successful-resolution",
            ],
        )

        print("Retain result:")
        print(retain_result)
    except Exception as exc:
        print("Retain error:")
        print(type(exc).__name__, exc)
        return

    print("\nRecalling experience...")

    try:
        recalled = memory.recall_experiences(
            """
            Emergency department transfer is blocked because
            ICU bed preparation is delayed. What interventions
            worked in similar cases?
            """
        )

        for index, item in enumerate(recalled, start=1):
            print(f"\n--- Recall {index} ---")
            print(item)
    except Exception as exc:
        print("Recall error:")
        print(type(exc).__name__, exc)
        return

    print("\nReflecting on experience...")

    try:
        reflection = memory.reflect_on_experiences(
            """
            What should EDResolve learn from previous cases where
            an ED-to-ICU transfer was blocked by an ICU bed-cleaning
            delay? Distinguish successful and failed interventions.
            """
        )

        print("\n--- Reflection ---")
        print(reflection["text"])
    except Exception as exc:
        print("Reflect error:")
        print(type(exc).__name__, exc)

    memory.close()


if __name__ == "__main__":
    main()