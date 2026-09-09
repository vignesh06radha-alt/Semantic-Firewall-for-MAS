import operator
from typing import Annotated, Dict, List, Literal, TypedDict
from langchain_core.messages import BaseMessage


class LabSwarmState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    literature_bounds: Dict[str, float]
    suggested_params: Dict[str, float]
    safety_clearance: bool
    robot_code: str
    cad_design: str
    crystallinity_score: float
    iteration_count: int
    status: Literal["continue", "approved", "aborted"]
