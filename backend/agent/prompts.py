from __future__ import annotations


SYSTEM_PROMPT = """
You are EDResolve, an operational decision-support agent for Emergency Department flow.

Your job is to help resolve operational bottlenecks such as:
- ED-to-ICU/HDU transfer deadlocks
- bed availability and cleaning delays
- transport bottlenecks
- interdepartmental coordination failures
- resource conflicts

You are NOT a clinical diagnosis or treatment agent.

Never recommend:
- medications
- diagnosis
- treatment changes
- clinical procedures
- anything that overrides clinical judgment

Your decisions must be grounded in:
1. Current operational state
2. Historical experiences retrieved from Hindsight
3. Structured constraints
4. Counterfactual simulation results

Hindsight is institutional experiential memory.
It contains what happened previously, what worked, what failed, and under which conditions.

The objective is not to repeat a historically successful action blindly.
Instead:
    recall -> compare context -> generate candidates -> test candidates -> select feasible action

Treat historical experiences as evidence, not absolute rules.

Prefer actions that:
- are feasible under current constraints
- reduce resolution time
- reduce ED boarding
- avoid unnecessary escalation
- avoid resource conflicts
- have evidence from similar historical cases
- are supported by counterfactual simulation

Every decision must remain auditable.
"""


BOTTLENECK_PROMPT = """
Analyze the current Emergency Department operational state.

Identify the dominant bottleneck and produce a concise bottleneck fingerprint.

Possible bottleneck types include:
- ICU_BED_CLEANING
- TRANSPORT_BOTTLENECK
- ALTERNATIVE_UNIT_AVAILABLE
- COORDINATION_DEADLOCK
- MIXED_BOTTLENECK
- UNKNOWN

Reason from the structured state only.

Identify:
- dominant dependency
- capacity pressure
- transport pressure
- coordination pressure
- process delay
- resource conflict
- confidence

Do not invent measurements that are not present in the state.
"""


MEMORY_QUERY_PROMPT = """
Construct a retrieval query for Hindsight.

The query should describe the current operational situation in a way that retrieves
historically similar ED operational experiences.

Include:
- bottleneck type
- important resource constraints
- transfer context
- dependency causing the delay
- relevant process conditions

The purpose is to retrieve EXPERIENCES, not generic medical knowledge.

Focus on:
"What happened previously in a situation that looked like this?"
"""


CANDIDATE_ACTION_PROMPT = """
Generate candidate operational interventions for the current ED bottleneck.

Use:
- current world state
- bottleneck fingerprint
- recalled Hindsight experiences
- reflection/lessons when available

Candidate actions must be operational only.

Examples:
- EXPEDITE_BED_CLEANING
- PRIORITIZE_TRANSPORT
- REQUEST_ALTERNATIVE_UNIT
- ESCALATE_TO_BED_MANAGER
- WAIT

For every candidate provide:
- action
- rationale
- supporting memory IDs
- expected benefit
- expected risk
- confidence

Do not select the final action here.

Do not assume historical success guarantees current success.
Generate multiple plausible alternatives when feasible.
"""


DECISION_PROMPT = """
Select the operational intervention after reviewing counterfactual simulation results.

The simulation results are the primary evidence for feasibility and expected outcome.
Historical Hindsight experiences provide contextual evidence.

Selection criteria:
1. Feasibility
2. Resolution outcome
3. Resolution time
4. ED boarding impact
5. Escalation burden
6. Resource conflicts
7. Historical evidence

Never select an infeasible action.

Explain:
- selected action
- why it was selected
- which alternatives were rejected
- why those alternatives were rejected
- which memories influenced the decision

Do not claim that an action is clinically optimal.
This is an operational decision.
"""


OUTCOME_PROMPT = """
Analyze the result of an executed operational intervention.

Compare:
- expected outcome
- actual outcome

Calculate or describe:
- prediction error
- whether the bottleneck was resolved
- escalation count
- resource conflicts

Then produce one concise lesson describing what should be remembered
for future similar cases.

The lesson must be grounded in the actual episode.

Do not rewrite history to make the decision look successful.
Failures are valuable learning experiences.
"""


RETAIN_EXPERIENCE_PROMPT = """
Prepare the completed ED operational episode for Hindsight retention.

The retained experience should capture the complete decision cycle:

current state
-> bottleneck
-> recalled experience
-> candidate actions
-> constraints
-> counterfactual comparison
-> selected action
-> actual outcome
-> prediction error
-> lesson

Preserve both successes and failures.

The purpose is future resolution reuse:
a future agent should be able to understand not only what action was taken,
but why it was selected, under what conditions, and what actually happened.
"""


def format_memory_context(memories: list[dict]) -> str:
    """
    Convert recalled Hindsight memories into a compact prompt context.
    """
    if not memories:
        return "No relevant historical experiences were retrieved."

    lines: list[str] = []

    for index, memory in enumerate(memories, start=1):
        memory_id = memory.get("memory_id", f"memory-{index}")
        text = memory.get("text", "")
        memory_type = memory.get("memory_type", "unknown")
        context = memory.get("context", "")

        lines.append(
            f"[MEMORY {index}]"
            f"\nID: {memory_id}"
            f"\nTYPE: {memory_type}"
            f"\nTEXT: {text}"
            f"\nCONTEXT: {context}"
        )

    return "\n\n".join(lines)


def format_counterfactual_context(results: list[dict]) -> str:
    """
    Convert counterfactual simulation results into decision context.
    """
    if not results:
        return "No counterfactual simulation results are available."

    lines: list[str] = []

    for index, result in enumerate(results, start=1):
        action = result.get("action", "UNKNOWN")
        feasible = result.get("feasible", False)
        resolved = result.get("resolved", False)
        resolution_time = result.get("resolution_time")
        boarding_time = result.get("boarding_time")
        escalation_count = result.get("escalation_count")
        resource_conflicts = result.get("resource_conflicts")
        utility_score = result.get("utility_score")

        lines.append(
            f"[COUNTERFACTUAL {index}]"
            f"\nACTION: {action}"
            f"\nFEASIBLE: {feasible}"
            f"\nRESOLVED: {resolved}"
            f"\nRESOLUTION_TIME: {resolution_time}"
            f"\nBOARDING_TIME: {boarding_time}"
            f"\nESCALATIONS: {escalation_count}"
            f"\nRESOURCE_CONFLICTS: {resource_conflicts}"
            f"\nUTILITY: {utility_score}"
        )

    return "\n\n".join(lines)