import json
from typing import List, Any
MAX_HISTORY_TOKENS = 6000
MAX_ERROR_CONTEXT_CHARS = 2000

def _format_error_context(error_context: Any) -> str:
    """Convert structured tool errors to a bounded string for the healing prompt."""
    if isinstance(error_context, dict):
        response = error_context.get("response")
        details = error_context.get("details")

        summary = {
            "source": error_context.get("source"),
            "tool": error_context.get("tool"),
            "error_type": error_context.get("error_type"),
            "message": error_context.get("message"),
            "response": response,
            "details": details,
        }
        return json.dumps(summary, default=str)[:MAX_ERROR_CONTEXT_CHARS]

    return str(error_context)[:MAX_ERROR_CONTEXT_CHARS]
