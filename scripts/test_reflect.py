from backend.memory.hindsight_memory import EDResolveMemory


def main() -> None:
    memory = EDResolveMemory()

    try:
        result = memory.reflect_on_experiences(
            """
            For an emergency department transfer blocked by
            an ICU bed-cleaning delay, what interventions
            succeeded, what failed, and what should EDResolve
            try first in a similar future case?
            """,
            budget="low",
            max_tokens=800,
        )

        print("\n" + "=" * 70)
        print("HINDSIGHT REFLECTION")
        print("=" * 70)
        print()
        print(result["text"])

        if result["structured_output"] is not None:
            print("\n" + "=" * 70)
            print("STRUCTURED OUTPUT")
            print("=" * 70)
            print(result["structured_output"])

    except Exception as exc:
        print("\nReflection error:")
        print(type(exc).__name__, exc)

    finally:
        memory.close()


if __name__ == "__main__":
    main()

