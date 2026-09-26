from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from firewall.middleware import SemanticFirewallMiddleware
from graph import build_graph


def _initial_state(payload: dict, config_label: str) -> dict:
    return {
        "post_id": payload.get("post_id", "unknown"),
        "raw_payload": payload,
        "content": "",
        "policy_verdict": None,
        "policy_rationale": "",
        "loop_request": "NONE",
        "final_action": None,
        "iteration_count": 0,
        "latency_ms": [],
        "agent_path": [],
        "audit_log": [],
        "status": "continue",
        "config_label": config_label,
    }


def create_app(config_label: Literal["baseline_a", "baseline_b", "proposed"]) -> FastAPI:
    """One FastAPI instance per experimental condition. The compiled graph
    (and, for "proposed", the firewall middleware) are fixed at construction
    time -- the benchmark harness builds three of these and never mixes
    conditions within one app instance."""
    fastapi_app = FastAPI()
    compiled_graph = build_graph(config_label)

    @fastapi_app.post("/moderate")
    async def moderate(request: Request):
        payload = await request.json()
        final_state = await compiled_graph.ainvoke(_initial_state(payload, config_label))
        return JSONResponse({
            "post_id": final_state["post_id"],
            "final_action": final_state["final_action"],
            "status": final_state["status"],
            "iteration_count": final_state["iteration_count"],
            "policy_rationale": final_state["policy_rationale"],
            "agent_path": final_state["agent_path"],
            "audit_log": final_state["audit_log"],
            "total_latency_ms": sum(final_state["latency_ms"]),
        })

    if config_label == "proposed":
        fastapi_app.add_middleware(SemanticFirewallMiddleware)

    return fastapi_app
