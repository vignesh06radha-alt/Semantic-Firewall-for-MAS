"""
Dev-only stand-in for the vLLM/Llama-Guard-3-8B sidecar's OpenAI-compatible
endpoint. Lets the firewall wiring be tested without a GPU or model download.
Swap CLASSIFIER_BACKEND_URL back to the real vLLM container for production use.

NOTE: this is deliberately a keyword scanner, not a real semantic classifier --
it exists to validate request/response wiring and fail-closed behavior, not to
demonstrate actual detection accuracy. Don't mistake its pass rate for the real
Llama-Guard-3-8B's.
"""
from fastapi import FastAPI, Request

app = FastAPI(title="Mock Llama-Guard Classifier")

UNSAFE_MARKERS = [
    "hydrogen_peroxide", "hydrogen peroxide", "h2o2", "override", "disregard",
    "jailbreak", "admin directive", "critical: lab fire", "mix_chemicals",
    "tatp", "<system>", "shutdown", "exfiltrate", "api_key", "ignore previous",
    "bypass", "corrosive payload", "delimiter breakout", "pre-approve",
    "compliance auditor",
]


_PAYLOAD_MARKER = "payload to review:\n"


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    content = body["messages"][-1]["content"].lower()
    # The classifier prompt's own instructions mention words like "overrides"
    # (see SAFETY_EVAL_PROMPT) -- only scan the actual untrusted payload, not
    # the instructions wrapped around it, or every request would trip on the
    # prompt's own vocabulary.
    if _PAYLOAD_MARKER in content:
        content = content.split(_PAYLOAD_MARKER, 1)[1]
    is_unsafe = any(marker in content for marker in UNSAFE_MARKERS)
    verdict = "unsafe\nS1" if is_unsafe else "safe"
    return {
        "choices": [
            {"message": {"role": "assistant", "content": verdict}}
        ]
    }
