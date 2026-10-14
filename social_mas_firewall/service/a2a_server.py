"""A2A 0.3 JSON-RPC gateway for the three-agent social research workflow."""
import asyncio
import copy
import hmac
import json

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import (AgentCapabilities, AgentCard, AgentSkill, DataPart, InvalidParamsError,
                       Part, TaskNotCancelableError, TaskState)
from a2a.utils import new_agent_text_message, new_task
from a2a.utils.errors import ServerError
from starlette.responses import JSONResponse
from starlette.routing import Route

from config.settings import settings
from core.context import RunContext
from datasets.scenarios import build_scenarios
from evaluation.runner import run_scenario
from firewall.guardian import RunGuardian
from socialapi.stub import SocialPlatformStub


def scenario_from_message(message):
    if message is None or message.role != "user":
        raise ValueError("A user message is required")
    parts = [p.root for p in message.parts]
    if len(parts) != 1 or not isinstance(parts[0], DataPart):
        raise ValueError("Supply one data part with scenario_id and optional text")
    data = parts[0].data
    if set(data) - {"scenario_id", "text"}:
        raise ValueError("Unsupported workflow request fields")
    scenario_id = data.get("scenario_id", "clean_00")
    scenarios = {s["id"]: s for s in build_scenarios()}
    if scenario_id not in scenarios:
        raise ValueError("Unknown scenario_id")
    scn = copy.deepcopy(scenarios[scenario_id])
    if "text" in data:
        if not isinstance(data["text"], str) or len(data["text"]) > 16000:
            raise ValueError("text must be a string of at most 16000 characters")
        scn["event"]["text"] = data["text"]
        for comment in scn["platform"]["comments"][scn["event"]["post_id"]]:
            if comment["id"] == scn["event"]["comment_id"]:
                comment["text"] = data["text"]
    return scn


class SocialExecutor(AgentExecutor):
    def __init__(self):
        self.active = {}

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        try:
            scn = scenario_from_message(context.message)
        except (ValueError, TypeError) as exc:
            raise ServerError(InvalidParamsError(message=str(exc))) from exc
        task = context.current_task or new_task(context.message)
        await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.update_status(TaskState.working)
        running = asyncio.create_task(run_scenario(scn, "firewall"))
        self.active[task.id] = running
        try:
            row = await running
            await updater.add_artifact([Part(root=DataPart(data=row))], name="social-workflow-result")
            state = {"completed": TaskState.completed, "killed": TaskState.rejected,
                     "held": TaskState.rejected}.get(row["status"], TaskState.failed)
            message = new_agent_text_message("Review required" if row["status"] == "held" else row["status"])
            await updater.update_status(state, message=message, final=True)
        except asyncio.CancelledError:
            await updater.update_status(TaskState.canceled, final=True)
        finally:
            self.active.pop(task.id, None)

    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        running = self.active.get(context.task_id)
        if running is None or running.done():
            raise ServerError(TaskNotCancelableError())
        running.cancel()


class IngressFirewall:
    """ASGI perimeter gate; rejected content never reaches the SDK executor."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        if settings.A2A_API_KEY:
            headers = dict(scope.get("headers", []))
            expected = f"Bearer {settings.A2A_API_KEY}".encode()
            if not hmac.compare_digest(headers.get(b"authorization", b""), expected):
                return await JSONResponse({"error": "Unauthorized"}, status_code=401)(scope, receive, send)
        body = bytearray()
        while True:
            chunk = await receive()
            if chunk["type"] == "http.disconnect":
                return
            body.extend(chunk.get("body", b""))
            if len(body) > settings.A2A_MAX_BODY_BYTES:
                return await JSONResponse({"error": "Request too large"}, status_code=413)(scope, receive, send)
            if not chunk.get("more_body", False):
                break
        try:
            request = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            request = {}
        if isinstance(request, dict) and request.get("method") in {"message/send", "message/stream"}:
            ctx = RunContext("a2a-ingress", "firewall", SocialPlatformStub({}))
            ctx.guard = RunGuardian(ctx)
            # Screen decoded values rather than JSON escapes that hide Unicode.
            params = request.get("params", {})
            message = params.get("message", {}) if isinstance(params, dict) else {}
            parts = message.get("parts", []) if isinstance(message, dict) else []
            result = await ctx.guard.protect({"user": "a2a-client", "text": json.dumps(
                parts, ensure_ascii=False)}, lambda: asyncio.sleep(0))
            if result != "completed":
                code = -32002 if result == "killed" else -32003
                response = {"jsonrpc": "2.0", "id": request.get("id"), "error": {
                    "code": code, "message": "Semantic firewall rejected payload" if result == "killed"
                    else "Payload requires review"}}
                return await JSONResponse(response)(scope, receive, send)
        delivered = False
        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()
        await self.app(scope, replay, send)


def create_app():
    skill = AgentSkill(id="social-workflow", name="Social network automation",
                       description="Three-agent LangGraph workflow over a simulated social account",
                       tags=["social", "semantic-firewall"], examples=["Handle a new customer comment"])
    card = AgentCard(name="Social MAS Semantic Firewall", version="1.0.0",
                     description="Screened social workflow; simulated publishing tools",
                     url=settings.A2A_PUBLIC_URL, capabilities=AgentCapabilities(streaming=True),
                     default_input_modes=["application/json"], default_output_modes=["application/json"],
                     skills=[skill])
    executor = SocialExecutor()
    handler = DefaultRequestHandler(agent_executor=executor, task_store=InMemoryTaskStore())
    sdk = A2AStarletteApplication(agent_card=card, http_handler=handler,
                                max_content_length=settings.A2A_MAX_BODY_BYTES)
    app = sdk.build()
    async def health(request):
        return JSONResponse({"status": "ok", "protocol": "A2A 0.3", "mock_llm": settings.MOCK_LLM,
                             "guard_backend": settings.GUARD_BACKEND})
    app.routes.append(Route("/health", health))
    return IngressFirewall(app)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(create_app(), host=settings.A2A_HOST, port=settings.A2A_PORT)
