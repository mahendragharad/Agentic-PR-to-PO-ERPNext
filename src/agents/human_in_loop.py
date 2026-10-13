from config.logging_config import logger
from langchain_core.messages import AIMessage
from src.state.agentState import AgentWorkflowState

def hitl_po_staging_node(state: AgentWorkflowState) -> dict:
    """Stage an approval request for a PR-to-PO operation."""
    messages = state.get("messages") or []
    if not messages:
        raise ValueError("Approval staging failed: workflow state has no messages.")

    last_msg = messages[-1]
    if not isinstance(last_msg, AIMessage):
        raise ValueError(
            "Approval staging failed: the latest workflow message is not an AIMessage."
        )

    tool_calls = last_msg.tool_calls
    if not tool_calls:
        raise ValueError(
            "Approval staging failed: the latest AIMessage has no tool calls."
        )

    tool_call = tool_calls[0]
    tool_name = tool_call.get("name")
    tool_call_id = tool_call.get("id")
    args = tool_call.get("args")

    if not tool_name or not tool_call_id or not isinstance(args, dict):
        raise ValueError(
            "Approval staging failed: tool call must include a name, ID, and argument object."
        )

    if tool_name not in {"convert_pr_to_draft_po", "submit_purchase_order"}:
        raise ValueError(
            f"Approval staging failed: unexpected tool '{tool_name}' reached the PO approval node."
        )

    logger.info(
        "Approval requested for tool %s (call ID %s): %s",
        tool_name,
        tool_call_id,
        args,
    )

    return {
        "approval_status": "pending",
        "approval_payload": {
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "args": args,
        },
    }