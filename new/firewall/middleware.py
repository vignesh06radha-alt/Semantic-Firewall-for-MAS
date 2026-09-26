import asyncio
import json

from ollama_client import guard_classify
from sandbox import sandbox_payload

_MODERATE_PATH = "/moderate"


async def _send_403(send, verdict: str) -> None:
    body = json.dumps({
        "jsonrpc": "2.0",
        "error": {"code": -32001, "message": "ERR_SEC_FIREWALL_BLOCKED", "details": verdict},
    }).encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": 403,
        "headers": [(b"content-type", b"application/json")],
    })
    await send({"type": "http.response.body", "body": body})


class SemanticFirewallMiddleware:
    """Pure-ASGI (not Starlette's BaseHTTPMiddleware) ingress sidecar: reads
    the request body directly off the ASGI `receive` channel before FastAPI's
    routing/validation ever sees it, sandboxes it, and classifies it with the
    local Llama Guard model. Only mounted for the "proposed" configuration
    (see app.py) -- baseline_a/baseline_b requests never pass through this
    class at all, which is the point of the comparison.

    Body buffering: an ASGI request body can only be read once from
    `receive`. This class drains it fully, then hands the downstream app a
    replacement `receive` callable that replays the same bytes, so the route
    handler's own `await request.json()` still works normally.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") != _MODERATE_PATH:
            await self.app(scope, receive, send)
            return

        body_chunks = []
        more_body = True
        while more_body:
            message = await receive()
            body_chunks.append(message.get("body", b""))
            more_body = message.get("more_body", False)
        body_bytes = b"".join(body_chunks)

        try:
            payload = json.loads(body_bytes or b"{}")
        except json.JSONDecodeError:
            payload = {}

        raw_text = " ".join(str(payload.get(k, "")) for k in ("post_text", "ocr_text", "metadata") if payload.get(k))
        sandboxed = sandbox_payload(raw_text)

        # Asynchronous parallelization: fire the guard classification off as
        # its own task immediately, so it overlaps with whatever ingress-side
        # work doesn't depend on its verdict (here: nothing else blocks
        # before dispatch, since the LangGraph itself is pre-compiled at
        # import time -- this task *is* the concurrent unit of work the spec
        # asks to run alongside "primary LangGraph initialization").
        guard_task = asyncio.create_task(guard_classify(sandboxed))
        is_safe, verdict = await guard_task

        if not is_safe:
            await _send_403(send, verdict)
            return

        replayed = False

        async def replay_receive():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body_bytes, "more_body": False}
            return {"type": "http.disconnect"}

        await self.app(scope, replay_receive, send)
