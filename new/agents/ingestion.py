import time

from sandbox import surface_base64
from state import ModerationState
from tagging import tag


async def ingestion_node(state: ModerationState) -> dict:
    """Agent 1: parses post text, OCR text, and metadata into one normalized
    view for the Policy Evaluator. Deterministic parsing only -- no LLM call
    here, reserving the real model call for the agent whose judgment the
    benchmark is actually measuring (matches how the sibling testbeds keep
    their dispatch/perception hops lightweight).

    Surfaces Base64 unconditionally (not just under the firewall) -- an
    unprotected agent doesn't need a firewall to decode Base64 itself, so
    baseline_a/baseline_b shouldn't get accidental immunity from this graph
    simply not bothering to surface it. See sandbox.py::surface_base64."""
    start = time.time()
    payload = state["raw_payload"]

    parts = [payload.get("post_text", "")]
    if payload.get("ocr_text"):
        parts.append(f"[OCR TEXT]: {payload['ocr_text']}")
    if payload.get("metadata"):
        parts.append(f"[METADATA]: {payload['metadata']}")
    content = tag("Ingestion", surface_base64(" ".join(p for p in parts if p)))

    latency_ms = (time.time() - start) * 1000
    return {
        "content": content,
        "iteration_count": state.get("iteration_count", 0) + 1,
        "agent_path": ["Ingestion"],
        "latency_ms": [latency_ms],
        "audit_log": [{"agent": "Ingestion", "latency_ms": latency_ms, "detail": "parsed payload"}],
        "status": "continue",
    }
