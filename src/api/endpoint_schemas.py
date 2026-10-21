from typing import Any, Dict, List, Optional, Union, Literal
from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    query: str = Field(..., json_schema_extra={"example": "What are the latest system metrics?"})
    thread_id: str = Field(..., json_schema_extra={"example": "user_session_abc_123"})
    user_id: Optional[str] = Field(default=None, json_schema_extra={"example": "user_42"})
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

class ApprovalDecisionRequest(BaseModel):
    thread_id: str
    approval_id: str
    preview_hash: str
    decision: Literal["approved", "rejected"]
