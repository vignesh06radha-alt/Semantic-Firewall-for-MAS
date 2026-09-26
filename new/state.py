import operator
from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict


class AgentCallLog(TypedDict):
    agent: str
    latency_ms: float
    detail: str


class ModerationState(TypedDict):
    post_id: str
    content: str
    policy_verdict: Optional[Literal["ALLOW", "FLAG", "TAKEDOWN"]]
    iteration_count: int
    # Per-hop latency samples rather than a single running total -- a plain
    # float would need the same operator.add reducer anyway once any branch
    # runs in parallel, and a list keeps each hop's cost inspectable in the
    # audit trail instead of only the sum.
    latency_ms: Annotated[List[float], operator.add]
    agent_path: Annotated[List[str], operator.add]

    # -- fields beyond the spec's minimum state schema, needed to actually
    # run the benchmark (config selection, loop control, audit trail) --
    raw_payload: Dict[str, Any]
    policy_rationale: str
    loop_request: Literal["NONE", "RERUN"]
    final_action: Optional[Literal["ALLOW", "FLAG", "TAKEDOWN"]]
    audit_log: Annotated[List[AgentCallLog], operator.add]
    status: Literal["continue", "approved", "flagged", "removed", "aborted_dos"]
    config_label: Literal["baseline_a", "baseline_b", "proposed"]
