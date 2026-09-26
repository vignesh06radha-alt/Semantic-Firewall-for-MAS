import time

from config import settings
from state import ModerationState


async def enforcement_node(state: ModerationState) -> dict:
    """Agent 3: executes the verdict (ALLOW/FLAG/TAKEDOWN) and logs the audit
    trail. Also owns the hard-cycle-limit decision: if Policy Evaluator's
    output asked for a re-run (LOOP_REQUEST: RERUN -- see agent_prompts.py's
    OUTPUT_CONTRACT), Enforcement either sends the post back to Ingestion for
    another pass or, once iteration_count would exceed MAX_ITERATIONS,
    aborts instead of looping forever. This is the DoS-loop-exhaustion
    detector the spec asks for, as a plain counter cap rather than the
    content-hash ring buffer ../mas_security_firewall/firewall/corba_guard.py
    uses -- simpler, and sufficient since the attack surface here is an
    agent *complying* with an explicit repeat-yourself instruction, not a
    coincidental ping-pong loop between independent agents."""
    start = time.time()
    verdict = state.get("policy_verdict") or "FLAG"
    loop_request = state.get("loop_request", "NONE")
    iteration_count = state["iteration_count"]

    action_map = {"ALLOW": "approved", "FLAG": "flagged", "TAKEDOWN": "removed"}

    if loop_request == "RERUN" and iteration_count < settings.MAX_ITERATIONS:
        status = "continue"
        final_action = None
        detail = f"honored LOOP_REQUEST, iteration {iteration_count}/{settings.MAX_ITERATIONS}"
    elif loop_request == "RERUN":
        status = "aborted_dos"
        final_action = verdict
        detail = f"MAX_ITERATIONS ({settings.MAX_ITERATIONS}) exceeded -- DoS loop exhaustion detected, aborting"
    else:
        status = action_map.get(verdict, "flagged")
        final_action = verdict
        detail = f"final_action={verdict}"

    latency_ms = (time.time() - start) * 1000
    return {
        "final_action": final_action,
        "status": status,
        "agent_path": ["Enforcement"],
        "latency_ms": [latency_ms],
        "audit_log": [{"agent": "Enforcement", "latency_ms": latency_ms, "detail": detail}],
    }
