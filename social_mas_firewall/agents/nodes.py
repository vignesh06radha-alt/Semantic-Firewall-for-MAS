import json

from agents.prompts import PROMPT_ANALYST, PROMPT_MONITOR, PROMPT_PLANNER, tag, with_defense
from config.settings import settings
from core.context import RunContext

MONITOR_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "user": {"type": "string"},
            "intent": {"type": "string", "enum": ["question", "praise", "complaint", "spam", "other"]},
            "needs_reply": {"type": "boolean"},
            "summary": {"type": "string"},
        },
        "required": ["user", "intent", "needs_reply", "summary"]}}},
    "required": ["items"],
}
ANALYST_SCHEMA = {
    "type": "object",
    "properties": {
        "priority": {"type": "string", "enum": ["low", "medium", "high"]},
        "followups": {"type": "array", "items": {
            "type": "object",
            "properties": {"kind": {"type": "string", "enum": ["investigate_user", "recheck_post"]},
                           "target": {"type": "string"}},
            "required": ["kind", "target"]}},
        "summary": {"type": "string"},
    },
    "required": ["priority", "followups", "summary"],
}
PLANNER_SCHEMA = {
    "type": "object",
    "properties": {"actions": {"type": "array", "items": {
        "type": "object",
        "properties": {"type": {"type": "string", "enum": ["reply", "publish", "dm", "none"]},
                       "target": {"type": "string"}, "text": {"type": "string"}},
        "required": ["type", "target", "text"]}}},
    "required": ["actions"],
}


def _comment_line(c: dict) -> str:
    return f"[comment {c['id']}] @{c['user']}: {c['text']}"


def _profile_line(p: dict) -> str:
    return f"[profile @{p['user']}] bio: {p['bio']} | followers: [{', '.join(p['followers'])}]"


def make_nodes(ctx: RunContext) -> dict:
    """Three independent LLM agents, each with its own prompt and schema."""
    platform = ctx.platform
    mode = ctx.mode

    async def monitor(state: dict) -> dict:
        ctx.check_alive()
        n = state["iteration_count"] + 1
        event = state["event"]
        post_id = event["post_id"]
        lines, incoming = [], []

        if n == 1:
            post = platform.posts.get(post_id, {})
            lines.append(f"Post {post_id} caption: {post.get('caption', '')}")
            comments = platform.fetch_comments(post_id)
            lines.append("NEW COMMENT TO HANDLE:")
            lines.extend(_comment_line(c) for c in comments if c["id"] == event["comment_id"])
            lines.append(_profile_line(platform.fetch_profile(event["user"])))
            earlier = [c for c in comments if c["id"] != event["comment_id"]]
            if earlier:
                lines.append("Earlier comments on this post (background context only, already handled):")
                lines.extend(_comment_line(c) for c in earlier)
            incoming.append(event["text"])
        else:
            lines.append("NEW ACTIVITY TO HANDLE:")
            for c in state["new_comments"]:
                lines.append(_comment_line(c))
                incoming.append(c["text"])
            reviewed = state["pending"][:settings.MAX_FETCH_PER_PASS]
            if reviewed:
                lines.append("Data requested for review:")
            for t in reviewed:
                if t["kind"] == "investigate_user":
                    lines.append(_profile_line(platform.fetch_profile(t["target"])))
                elif t["kind"] == "recheck_post":
                    lines.extend(_comment_line(c) for c in platform.fetch_comments(t["target"]))

        view_raw = "\n".join(lines)
        # Screen all fetched material before the Monitor's model sees it.
        await ctx.screen(f"tool:pass{n}", view_raw)
        if ctx.guard:
            ctx.guard.note_iteration(n, incoming)
        ctx.check_alive()
        # Counted only once the pass is actually allowed to proceed, so a pass
        # the watch layer refuses to start is not scored as work performed.
        ctx.iterations = n

        data = await ctx.llm("monitor", with_defense(PROMPT_MONITOR, mode), view_raw, MONITOR_SCHEMA)
        return {"iteration_count": n, "view_raw": view_raw, "items": data.get("items", []), "agent_path": ["Monitor"]}

    async def analyst(state: dict) -> dict:
        ctx.check_alive()
        post_id = state["event"]["post_id"]
        user = (
            f"{tag('Monitor', json.dumps(state['items']))}\n"
            f"Engagement for {post_id}: {json.dumps(platform.get_engagement(post_id))}\n"
            f"Raw activity data:\n{state['view_raw']}"
        )
        data = await ctx.llm("analyst", with_defense(PROMPT_ANALYST, mode), user, ANALYST_SCHEMA)
        visited = set(state["visited"])
        # Hygiene, identical in every mode: a follow-up on the commenter or the
        # current post adds no information (both are already in context), and a
        # repeat of an earlier follow-up is a no-op. Everything else is kept.
        already_in_hand = {state["event"]["user"].lstrip("@"), post_id}
        followups = []
        for f in data.get("followups", []) or []:
            target = str(f.get("target", "")).lstrip("@")
            key = f"{f.get('kind')}:{target}"
            if f.get("kind") and target and target not in already_in_hand and key not in visited:
                visited.add(key)
                followups.append({"kind": f["kind"], "target": target})
        ctx.followups_total += len(followups)
        if ctx.guard:
            ctx.guard.note_followups(len(followups))
        return {"analysis": {**data, "followups": followups}, "visited": sorted(visited), "agent_path": ["Analyst"]}

    async def planner(state: dict) -> dict:
        ctx.check_alive()
        user = (
            f"{tag('Monitor', json.dumps(state['items']))}\n"
            f"{tag('Analyst', json.dumps(state['analysis']))}\n"
            f"Raw activity data:\n{state['view_raw']}"
        )
        data = await ctx.llm("planner", with_defense(PROMPT_PLANNER, mode), user, PLANNER_SCHEMA, num_predict=300)
        return {"plan": (data.get("actions") or [])[:6], "agent_path": ["Planner"]}

    return {"monitor": monitor, "analyst": analyst, "planner": planner}
