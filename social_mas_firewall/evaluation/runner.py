import time
import uuid

from config.settings import settings
from core.context import RunContext
from core.routing import MessageRejected
from firewall.guardian import RunGuardian
from graph.workflow import build_graph, initial_state
from socialapi.stub import SocialPlatformStub

MODES = ("baseline", "in_context", "firewall")


async def run_scenario(scn: dict, mode: str, parallel: bool | None = None, layers: set[str] | None = None) -> dict:
    """Runs one scenario end to end under one defence mode and returns the
    raw facts the metrics are computed from. Nothing here judges success."""
    platform = SocialPlatformStub(scn["platform"])
    ctx = RunContext(run_id=f"{scn['id']}-{mode}-{uuid.uuid4().hex[:6]}", mode=mode, platform=platform)
    graph = build_graph(ctx)

    async def runner():
        return await graph.ainvoke(initial_state(scn["event"]), config={"recursion_limit": 400})

    ctx.t0 = time.perf_counter()
    status, error = "completed", ""
    protocol_error = None
    try:
        if mode == "firewall":
            ctx.guard = RunGuardian(ctx, parallel=parallel, layers=layers)
            status = await ctx.guard.protect(scn["event"], runner)
        else:
            await runner()
    except MessageRejected as exc:
        status, error = "route_denied", str(exc)
        protocol_error = exc.response
    except Exception as exc:  # a crashed run is recorded, never silently dropped
        status, error = "error", f"{type(exc).__name__}: {exc}"
    wall_ms = (time.perf_counter() - ctx.t0) * 1000

    g = ctx.guard
    if status in {"held", "killed"}:
        protocol_error = {"jsonrpc": "2.0", "id": ctx.run_id, "error": {
            "code": -32002 if status == "killed" else -32003,
            "message": "Semantic firewall rejected payload" if status == "killed" else "Payload requires review"}}
    return {
        "architecture": "three_agent_screened_ingress_v2", "protocol_error": protocol_error,
        "mock_llm": settings.MOCK_LLM, "agent_model": settings.AGENT_MODEL,
        "ollama_num_ctx": settings.OLLAMA_NUM_CTX, "ollama_keep_alive": settings.OLLAMA_KEEP_ALIVE,
        "guard_backend": settings.GUARD_BACKEND if g else None,
        "guard_policy": "social_injection_custom_S1_S4_v1" if g and settings.GUARD_BACKEND.startswith("llama_guard") else None,
        "guard_model": (settings.LLAMA_GUARD_OLLAMA_MODEL if settings.GUARD_BACKEND == "llama_guard_ollama"
                        else settings.LLAMA_GUARD_MODEL if settings.GUARD_BACKEND.startswith("llama_guard")
                        else settings.GUARD_MODEL) if g else None,
        "message_events": ctx.hub.events,
        "id": scn["id"], "category": scn["category"], "mode": mode,
        "goal": scn["ground_truth"]["goal"], "vector": scn["ground_truth"]["vector"],
        "location": scn["ground_truth"]["location"],
        "status": status, "error": error, "wall_ms": wall_ms,
        "llm_calls": ctx.llm_calls, "tokens": ctx.prompt_tokens + ctx.completion_tokens,
        "iterations": ctx.iterations, "tool_calls": platform.tool_calls, "followups": ctx.followups_total,
        "executed": ctx.executed, "held": ctx.held,
        "guard_llm_calls": g.guard_llm_calls if g else 0, "guard_tokens": g.guard_tokens if g else 0,
        "killed": status == "killed", "kill_reason": g.kill_reason if g else "",
        "t_kill_ms": g.t_kill_ms if g else None,
        "quarantine": g.quarantine_reasons if g else [],
        "guard_events": g.events if g else [],
    }
