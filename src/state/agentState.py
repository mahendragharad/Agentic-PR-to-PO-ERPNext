from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from typing import List, Dict, Any, Optional, Literal, Annotated
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage, SystemMessage

class AgentWorkflowState(TypedDict) :
    messages : Annotated[List[BaseMessage], add_messages]
    retry_counter : Dict[str, int]
    max_retries : int
    last_error_context: Optional[Dict[str, Any]]
    is_greeting: Optional[bool] 

    pr_details: Dict[str, Any]      # Saved extraction fields across turns
    active_pr_id: Optional[str]     # Tracks current PR ID (e.g., MAT-MR-2026-00052)
    active_po_id: Optional[str]     # Tracks current PO ID

    approval_status: Optional[Literal["pending", "approved", "rejected"]]
    approval_payload: Optional[Dict[str, Any]]  # Holds the staging arguments for the PO tool


class ApprovalPayload(TypedDict):
    approval_id: str
    tool_name: Literal["convert_pr_to_draft_po", "submit_purchase_order"]
    tool_call_id: str
    document_type: Literal["Material Request", "Purchase Order"]
    document_id: str
    action_label: str
    preview: Dict[str, Any]
    preview_hash: str
    created_at: str