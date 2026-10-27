import asyncio
import json
import time
from dataclasses import dataclass, field

import httpx

from config.settings import settings
from llm import mock_backend


@dataclass
class LLMResult:
    data: dict
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    ok: bool = True
    raw: str = field(default="", repr=False)


async def chat_json(*, purpose: str, model: str, system: str, user: str, schema: dict,
                    num_predict: int = 220, timeout_ms: int | None = None) -> LLMResult:
    """One structured-output chat call. `format` is a JSON schema, so the model
    is constrained to emit parseable output rather than free text we'd have to
    regex -- parse failures return ok=False with empty data, never a guess."""
    start = time.perf_counter()
    if settings.MOCK_LLM:
        data = mock_backend.mock_chat(purpose, system, user)
        await asyncio.sleep(0.005)
        return LLMResult(data, (len(system) + len(user)) // 4, len(json.dumps(data)) // 4,
                         (time.perf_counter() - start) * 1000)

    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "format": schema,
        "options": {"temperature": 0, "num_predict": num_predict},
        "keep_alive": settings.OLLAMA_KEEP_ALIVE,
    }
    if settings.OLLAMA_NUM_CTX > 0:
        body["options"]["num_ctx"] = settings.OLLAMA_NUM_CTX
    timeout = (timeout_ms or settings.AGENT_TIMEOUT_MS) / 1000.0
    async with httpx.AsyncClient(timeout=timeout) as client:
        base_url = (settings.GUARD_BASE_URL or settings.OLLAMA_BASE_URL) if purpose == "guardian" else settings.OLLAMA_BASE_URL
        resp = await client.post(f"{base_url.rstrip('/')}/api/chat", json=body)
        resp.raise_for_status()
        payload = resp.json()
    raw = payload.get("message", {}).get("content", "")
    try:
        data = json.loads(raw)
        ok = isinstance(data, dict)
    except json.JSONDecodeError:
        data, ok = {}, False
    return LLMResult(data if isinstance(data, dict) else {}, payload.get("prompt_eval_count", 0),
                     payload.get("eval_count", 0), (time.perf_counter() - start) * 1000, ok, raw)
