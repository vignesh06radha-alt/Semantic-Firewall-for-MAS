"""Deterministic action validation and execution; this is not an LLM agent."""
import re

from config.settings import settings
from core.context import RunContext


def validate_actions(plan: list[dict]) -> None:
    """Validate the whole plan before allowing any outward action."""
    if not isinstance(plan, list):
        raise ValueError("Invalid social action plan")
    for action in plan:
        if (not isinstance(action, dict)
                or action.get("type") not in {"reply", "publish", "dm", "none"}
                or not isinstance(action.get("text"), str)
                or not isinstance(action.get("target"), str)):
            raise ValueError("Invalid social action proposal")


def make_executor(ctx: RunContext):
    async def execute_actions(state: dict) -> dict:
        ctx.check_alive()
        validate_actions(state["plan"])
        platform = ctx.platform
        event = state["event"]
        known_users = {event["user"]} | set(re.findall(r"@(\w+)", state["view_raw"]))
        default_user = (state["new_comments"][-1]["user"]
                        if state["iteration_count"] > 1 and state["new_comments"]
                        else event["user"])
        for action in state["plan"]:
            text = action["text"].strip()
            if action["type"] == "none" or not text:
                continue
            if await ctx.commit(action) == "hold":
                ctx.held.append(action)
                continue
            raw_target = action["target"].lstrip("@")
            target = raw_target if raw_target in known_users else default_user
            if action["type"] == "reply":
                platform.publish_reply(event["post_id"], target, text)
            elif action["type"] == "publish":
                platform.publish_post(text)
            elif action["type"] == "dm":
                platform.send_dm(target, text)
            ctx.executed.append(platform.actions[-1])

        new_comments = platform.drain_new_comments()
        followups = state["analysis"].get("followups", [])
        keep_going = bool(followups or new_comments)
        keep_going = keep_going and state["iteration_count"] < settings.MAX_ITERATIONS
        return {
            "pending": followups,
            "new_comments": new_comments,
            "status": "continue" if keep_going else "done",
        }

    return execute_actions
