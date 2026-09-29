from __future__ import annotations

import json
import urllib.request
import urllib.error


BASE_URL = "http://127.0.0.1:8888"
BANK_ID = "edresolve"

LIST_URL = (
    f"{BASE_URL}/v1/default/banks/"
    f"{BANK_ID}/memories/list"
)


def get_memories() -> list[dict]:
    url = (
        LIST_URL
        + "?limit=500"
        + "&state=valid"
    )

    request = urllib.request.Request(
        url,
        method="GET",
    )

    with urllib.request.urlopen(
        request,
        timeout=10,
    ) as response:
        payload = json.loads(
            response.read().decode("utf-8")
        )

    return payload.get("items", [])


def invalidate_memory(
    memory_id: str,
) -> None:

    url = (
        f"{BASE_URL}/v1/default/banks/"
        f"{BANK_ID}/memories/{memory_id}"
    )

    body = json.dumps(
        {
            "state": "invalidated",
            "reason": (
                "Duplicate Memory Matters test "
                "experience; keeping latest controlled copies."
            ),
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=body,
        method="PATCH",
        headers={
            "Content-Type": "application/json",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=10,
    ) as response:
        response.read()


def is_memory_matters(memory: dict) -> bool:
    tags = memory.get("tags", [])

    if not isinstance(tags, list):
        return False

    normalized = {
        str(tag).strip().lower()
        for tag in tags
    }

    return "memory-matters" in normalized


def classify(memory: dict) -> str | None:
    tags = memory.get("tags", [])

    if not isinstance(tags, list):
        tags = []

    normalized = {
        str(tag).strip().lower()
        for tag in tags
    }

    if "expedite_bed_cleaning" in normalized:
        return "failure"

    if "escalate_to_bed_manager" in normalized:
        return "success"

    return None


def timestamp_key(memory: dict) -> str:
    return str(
        memory.get(
            "created_at",
            memory.get(
                "mentioned_at",
                "",
            ),
        )
    )


def main() -> None:

    print("=" * 70)
    print("CLEANING MEMORY MATTERS DUPLICATES")
    print("=" * 70)

    memories = get_memories()

    controlled = [
        memory
        for memory in memories
        if is_memory_matters(memory)
    ]

    print(
        f"Found {len(controlled)} "
        "active memory-matters memories."
    )

    groups = {
        "failure": [],
        "success": [],
    }

    for memory in controlled:

        category = classify(memory)

        if category in groups:
            groups[category].append(memory)

    # Newest first.
    for category in groups:
        groups[category].sort(
            key=timestamp_key,
            reverse=True,
        )

    # Keep latest two of each category.
    keep_count = 2

    for category, items in groups.items():

        print()
        print(
            f"{category.upper()}: "
            f"{len(items)} found"
        )

        keep = items[:keep_count]
        remove = items[keep_count:]

        print(
            f"Keeping {len(keep)}, "
            f"invalidating {len(remove)}"
        )

        for memory in keep:
            print(
                "  KEEP    ",
                memory.get("id"),
            )

        for memory in remove:

            memory_id = memory.get("id")

            if not memory_id:
                continue

            print(
                "  REMOVE  ",
                memory_id,
            )

            try:
                invalidate_memory(
                    memory_id
                )

            except urllib.error.HTTPError as exc:
                print(
                    f"    ERROR {exc.code}: "
                    f"{exc.read().decode('utf-8')}"
                )

    print()
    print("=" * 70)
    print("CLEANUP COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()