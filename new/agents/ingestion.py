import time

from state import ModerationState
from tagging import tag


async def ingestion_node(state: ModerationState) -> dict:
    """Agent 1: parses post text, OCR text, and metadata into one normalized
    view for the Policy Evaluator. Deterministic parsing only -- no LLM call
    here, reserving the real model call for the agent whose judgment the
    benchmark is actually measuring (matches how the sibling testbeds keep
    their dispatch/perception hops lightweight)."""
    start = time.time()
    payload = state["raw_payload"]

    parts = [payload.get("post_text", "")]
    if payload.get("ocr_text"):
        parts.append(f"[OCR TEXT]: {payload['ocr_text']}")
    if payload.get("metadata"):
        parts.append(f"[METADATA]: {payload['metadata']}")
    content = tag("Ingestion", " ".join(p for p in parts if p))

    latency_ms = (time.time() - start) * 1000
    return {
        "content": content,
        "iteration_count": state.get("iteration_count", 0) + 1,
        "agent_path": ["Ingestion"],
        "latency_ms": [latency_ms],
        "audit_log": [{"agent": "Ingestion", "latency_ms": latency_ms, "detail": "parsed payload"}],
        "status": "continue",
    }
