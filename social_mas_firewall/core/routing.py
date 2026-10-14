"""Local JSON-RPC message hub; not a network A2A server.

Permissions are structural controls shared by all experiment conditions.
Only explicit, serialized data crosses each logical agent boundary.
"""
import asyncio
import json
import time
from a2a.types import DataPart, Message, MessageSendParams, Part, SendMessageRequest


AGENT_COMMAND_MAP = {
    "controller": {"monitor"},
    "monitor": {"analyst"},
    "analyst": {"planner"},
    "planner": {"executor"},
    "executor": {"monitor"},
}


class MessageRejected(Exception):
    def __init__(self, request_id, code, reason):
        self.response = {"jsonrpc": "2.0", "id": request_id,
                         "error": {"code": code, "message": reason}}
        super().__init__(reason)


class MessageHub:
    def __init__(self, ctx):
        self.ctx = ctx
        self.queue = asyncio.Queue()
        self.sequence = 0
        self.events = []

    async def deliver(self, sender, recipient, payload):
        self.sequence += 1
        request_id = f"{self.ctx.run_id}:{self.sequence}"
        started = time.perf_counter()
        if recipient not in AGENT_COMMAND_MAP.get(sender, set()):
            raise MessageRejected(request_id, -32001, "Communication route denied")
        # Round-tripping also prevents the receiving node mutating peer state.
        message = Message(role="user", message_id=request_id,
                          metadata={"sender": sender, "recipient": recipient},
                          parts=[Part(root=DataPart(data=payload))])
        request = SendMessageRequest(id=request_id, params=MessageSendParams(message=message))
        request = request.model_dump(mode="json", by_alias=True)
        await self.queue.put(json.dumps(request, ensure_ascii=False))
        wire = await self.queue.get()
        try:
            envelope = json.loads(wire)
            # The SDK validates the protocol envelope; classify application
            # data, not trusted routing fields presented as user-authored prose.
            content = envelope["params"]["message"]["parts"][0]["data"]
            await self.ctx.screen(f"message:{sender}->{recipient}", json.dumps(content, ensure_ascii=False))
            self.events.append({"sender": sender, "recipient": recipient,
                                "ingress_ms": (time.perf_counter() - started) * 1000})
            return envelope["params"]["message"]["parts"][0]["data"]
        finally:
            self.queue.task_done()
