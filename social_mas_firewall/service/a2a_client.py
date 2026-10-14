"""Send a standards-shaped request to the deployed A2A gateway."""
import argparse
import asyncio
import json
import uuid

import httpx
from a2a.types import DataPart, Message, MessageSendParams, Part, SendMessageRequest

from config.settings import settings


async def send(url, scenario_id="clean_00", text=None):
    data = {"scenario_id": scenario_id}
    if text is not None:
        data["text"] = text
    message = Message(role="user", message_id=uuid.uuid4().hex, parts=[Part(root=DataPart(data=data))])
    request = SendMessageRequest(id=uuid.uuid4().hex, params=MessageSendParams(message=message))
    headers = {"Authorization": f"Bearer {settings.A2A_API_KEY}"} if settings.A2A_API_KEY else {}
    async with httpx.AsyncClient(timeout=600) as client:
        response = await client.post(url, json=request.model_dump(mode="json", by_alias=True), headers=headers)
        response.raise_for_status()
        return response.json()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=settings.A2A_PUBLIC_URL)
    parser.add_argument("--scenario", default="clean_00")
    parser.add_argument("--text")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(send(args.url, args.scenario, args.text)), indent=2))
