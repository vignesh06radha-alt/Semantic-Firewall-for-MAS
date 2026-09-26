import functools
from typing import Literal

from langgraph.graph import END, START, StateGraph

from agents.enforcement import enforcement_node
from agents.ingestion import ingestion_node
from agents.policy import policy_node
from state import ModerationState


def _loop_router(state: ModerationState) -> str:
    return "ingestion" if state["status"] == "continue" else END


def build_graph(config_label: Literal["baseline_a", "baseline_b", "proposed"]):
    """One compiled graph per experimental condition -- config_label selects
    Policy Evaluator's system prompt (agent_prompts.py) and is otherwise
    inert; the firewall itself lives in firewall/middleware.py, in front of
    this graph, not inside it (see app.py)."""
    graph = StateGraph(ModerationState)
    graph.add_node("ingestion", ingestion_node)
    graph.add_node("policy", functools.partial(policy_node, config_label=config_label))
    graph.add_node("enforcement", enforcement_node)

    graph.add_edge(START, "ingestion")
    graph.add_edge("ingestion", "policy")
    graph.add_edge("policy", "enforcement")
    graph.add_conditional_edges("enforcement", _loop_router, {"ingestion": "ingestion", END: END})

    return graph.compile()
