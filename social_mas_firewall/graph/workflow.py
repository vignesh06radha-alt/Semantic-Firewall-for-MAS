import operator
from typing import Annotated, Any, List, TypedDict

from langgraph.graph import END, START, StateGraph

from agents.nodes import make_nodes
from core.actions import make_executor
from core.context import RunContext
from core.routing import MessageHub


class SocialState(TypedDict):
    event: dict
    iteration_count: int
    pending: List[dict]
    new_comments: List[dict]
    visited: List[str]
    view_raw: str
    items: List[Any]
    analysis: dict
    plan: List[dict]
    status: str
    agent_path: Annotated[List[str], operator.add]
    sender: str


def initial_state(event: dict) -> dict:
    return {"event": event, "iteration_count": 0, "pending": [], "new_comments": [], "visited": [],
            "view_raw": "", "items": [], "analysis": {}, "plan": [], "status": "continue", "agent_path": [],
            "sender": "controller"}


def build_graph(ctx: RunContext):
    """Three LLM agents plus one deterministic, gated execution node.

    LangGraph retains coordinator state. Individual roles receive only their
    declared input projection, copied through the queue-based message hub.
    """
    nodes = make_nodes(ctx)
    nodes["executor"] = make_executor(ctx)
    hub = MessageHub(ctx)
    ctx.hub = hub
    inputs = {
        "monitor": ("event", "iteration_count", "new_comments", "pending"),
        "analyst": ("event", "items", "view_raw", "visited"),
        "planner": ("items", "analysis", "view_raw"),
        "executor": ("event", "view_raw", "new_comments", "iteration_count", "plan", "analysis"),
    }

    def boundary(name, fn):
        async def receive(state):
            payload = {key: state[key] for key in inputs[name]}
            payload = await hub.deliver(state["sender"], name, payload)
            result = await fn(payload)
            return {**result, "sender": name}
        return receive

    g = StateGraph(SocialState)
    for name, fn in nodes.items():
        g.add_node(name, boundary(name, fn))
    g.add_edge(START, "monitor")
    g.add_edge("monitor", "analyst")
    g.add_edge("analyst", "planner")
    g.add_edge("planner", "executor")
    g.add_conditional_edges("executor", lambda s: "monitor" if s["status"] == "continue" else END,
                            {"monitor": "monitor", END: END})
    return g.compile()
