from typing import Any, Dict, Optional

from langchain_core.messages import ToolMessage
from utils.cleaner import parse_tool_response


def get_pending_approval(snapshot: Any) -> Optional[Dict[str, Any]]:
    """Return the first approval interrupt stored in a LangGraph state snapshot."""
    for task in getattr(snapshot, "tasks", ()):
        for pending_interrupt in getattr(task, "interrupts", ()):
            value = getattr(pending_interrupt, "value", None)
            if isinstance(value, dict) and value.get("approval_id"):
                return value
    return None


def get_tool_result(
    snapshot: Any,
    tool_call_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Return a JSON tool response from a graph snapshot, if present."""
    values = getattr(snapshot, "values", {}) or {}
    for message in reversed(values.get("messages", [])):
        if not isinstance(message, ToolMessage):
            continue
        if tool_call_id and message.tool_call_id != tool_call_id:
            continue
        result = parse_tool_response(message.content)
        if isinstance(result, dict):
            return result
    return None


def get_latest_tool_result(snapshot: Any) -> Optional[Dict[str, Any]]:
    return get_tool_result(snapshot)