import time
import uuid
from typing import Any, Dict, List
from pydantic import BaseModel, Field


class A2AMetadata(BaseModel):
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    hop_count: int = 0
    originating_agent: str
    provenance_chain: List[str] = Field(default_factory=list)


class A2AMessage(BaseModel):
    jsonrpc: str = "2.0"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sender: str
    recipient: str
    method: str
    params: Dict[str, Any]
    metadata: A2AMetadata
    timestamp: float = Field(default_factory=time.time)


class A2AError(BaseModel):
    jsonrpc: str = "2.0"
    id: str
    error: Dict[str, Any]
