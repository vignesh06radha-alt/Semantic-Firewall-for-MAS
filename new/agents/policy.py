import re
import time

from agent_prompts import BASELINE_A_PROMPT, BASELINE_B_PROMPT, PROPOSED_PROMPT, OUTPUT_CONTRACT
from config import settings
from ollama_client import agent_complete
from state import ModerationState
from tagging import tag

_PROMPTS = {
    "baseline_a": BASELINE_A_PROMPT,
    "baseline_b": BASELINE_B_PROMPT,
    "proposed": PROPOSED_PROMPT,
}

_VERDICT_RE = re.compile(r"VERDICT:\s*(ALLOW|FLAG|TAKEDOWN)", re.IGNORECASE)
_LOOP_RE = re.compile(r"LOOP_REQUEST:\s*(NONE|RERUN)", re.IGNORECASE)

# Markers for the offline mock -- deliberately loose/robust (single shared
# substrings like "loop_request") rather than matching the exact wording of
# any one payload template, so the mock keeps working if dataset/build_dataset.py's
# phrasing changes. This is a wiring stand-in for the real model's judgment,
# not a claim about what a real classifier would catch -- see README.
_HIJACK_MARKERS = ("system override", "verdict: allow", "policy_override", "trust & safety",
                    "ignore all prior instructions", "ignore your guidelines", "admin note")
_LOOP_MARKERS = ("loop_request",)
_TOXIC_MARKERS = ("[targeted slur]", "[protected group placeholder]", "unlicensed firearms",
                   "counterfeit", "crypto giveaway", "unmarked prescription", "subhuman", "deport all")
_SUSPICIOUS_MARKERS = ("great deal on watches", "keep to themselves", "extra prescription meds",
                        "causes nothing but trouble")


def _mock_policy(content: str, config_label: str) -> tuple[str, str, str]:
    lowered = content.lower()
    is_toxic = any(m in lowered for m in _TOXIC_MARKERS)
    is_suspicious = any(m in lowered for m in _SUSPICIOUS_MARKERS)
    has_hijack_marker = any(m in lowered for m in _HIJACK_MARKERS)
    has_loop_marker = any(m in lowered for m in _LOOP_MARKERS)

    if config_label == "baseline_b":
        # Vaccinated: refuses to comply with embedded directives, and leans
        # FLAG on anything merely adversarial-*looking* -- the Security Tax.
        loop_request = "NONE"
        looks_adversarial = has_hijack_marker or has_loop_marker or is_suspicious
        verdict = "TAKEDOWN" if is_toxic else ("FLAG" if looks_adversarial else "ALLOW")
    else:
        # baseline_a / proposed: a naive model complies with whatever
        # instruction-shaped text actually reaches it. Under "proposed" this
        # branch only ever sees attack payloads the firewall failed to
        # catch, since the ASGI middleware blocks the rest at ingress.
        loop_request = "RERUN" if has_loop_marker else "NONE"
        if is_toxic:
            verdict = "TAKEDOWN"
        elif has_hijack_marker:
            verdict = "ALLOW"
        elif is_suspicious:
            verdict = "FLAG"
        else:
            verdict = "ALLOW"
    return verdict, f"mock heuristic ({config_label})", loop_request


def _extract(pattern: re.Pattern, text: str, default: str) -> str:
    m = pattern.search(text)
    return m.group(1).upper() if m else default


async def policy_node(state: ModerationState, config_label: str) -> dict:
    """Agent 2: analyzes the parsed content against community guidelines.
    The only agent in this graph that calls a real LLM -- see README for why
    Ingestion/Enforcement stay deterministic."""
    start = time.time()

    if settings.MOCK_AGENTS:
        verdict, rationale, loop_request = _mock_policy(state["content"], config_label)
        raw = f"VERDICT: {verdict}\nRATIONALE: {rationale}\nLOOP_REQUEST: {loop_request}"
    else:
        system_prompt = _PROMPTS[config_label] + OUTPUT_CONTRACT
        try:
            raw = await agent_complete(system_prompt, state["content"])
        except Exception as exc:
            # Conservative fail-safe, not a security gate: an unreachable
            # agent model should not silently default to ALLOW.
            raw = f"VERDICT: FLAG\nRATIONALE: agent call failed ({exc.__class__.__name__})\nLOOP_REQUEST: NONE"
        verdict = _extract(_VERDICT_RE, raw, default="FLAG")
        loop_request = _extract(_LOOP_RE, raw, default="NONE")
        rationale = raw

    tagged_content = tag("PolicyEvaluator", raw)
    latency_ms = (time.time() - start) * 1000
    return {
        "policy_verdict": verdict.upper(),
        "policy_rationale": rationale,
        "loop_request": loop_request.upper(),
        "content": tagged_content,
        "agent_path": ["PolicyEvaluator"],
        "latency_ms": [latency_ms],
        "audit_log": [{
            "agent": "PolicyEvaluator", "latency_ms": latency_ms,
            "detail": f"verdict={verdict} loop_request={loop_request}",
        }],
    }
