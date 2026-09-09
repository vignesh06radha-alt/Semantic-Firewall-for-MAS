import asyncio
from typing import Any, Callable, Coroutine, Tuple
from protocols.a2a_schema import A2AMessage, A2AError
from firewall.sanitizer import sanitize_and_inoculate
from firewall.corba_guard import corba_guard
from firewall.classifier import check_payload_safety


class SidecarFirewall:
    def __init__(self):
        self.cancel_token = asyncio.Event()

    async def intercept_and_race(
        self,
        envelope: A2AMessage,
        agent_executor: Callable[[str, asyncio.Event], Coroutine[Any, Any, Any]]
    ) -> Tuple[bool, Any]:
        self.cancel_token.clear()
        raw_content = envelope.params.get("content", "")

        # 1. State-Aware Anti-CORBA Hop & Frequency Validation
        is_linear, corba_err = corba_guard.evaluate_packet(
            session_id=envelope.metadata.trace_id,
            hop_count=envelope.metadata.hop_count,
            canonical_content=raw_content
        )
        if not is_linear:
            return False, A2AError(
                id=envelope.id,
                error={"code": -32002, "message": corba_err, "details": "Loop circuit breaker tripped."}
            )

        # 2. Syntactic Normalization & XML Containment
        inoculated_content = sanitize_and_inoculate(raw_content)

        # 3. Asymmetric Race Coordinator (asyncio.create_task)
        agent_task = asyncio.create_task(agent_executor(inoculated_content, self.cancel_token))
        safety_task = asyncio.create_task(check_payload_safety(inoculated_content))

        # Await safety validation
        is_safe = await safety_task

        if not is_safe:
            # Deterministic Execution Interruption: Trip kill-switch
            self.cancel_token.set()
            agent_task.cancel()
            return False, A2AError(
                id=envelope.id,
                error={
                    "code": -32001,
                    "message": "ERR_SEC_001_INJECTION_DETECTED",
                    "details": "Payload rejected by Inline Semantic Firewall."
                }
            )

        # Release execution gate and resolve agent outcome
        agent_result = await agent_task
        return True, agent_result


sidecar = SidecarFirewall()
