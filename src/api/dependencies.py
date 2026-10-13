from fastapi import Request, HTTPException, status
from typing import Any

def get_agent_workflow(request: Request) -> Any:
    """
    Dependency to retrieve the compiled LangGraph workflow from the application state.
    Raises a 503 Service Unavailable if the engine failed to initialize.
    """
    workflow = getattr(request.app.state, "workflow", None)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent engine is not ready or failed to initialize."
        )
    
    return workflow

def get_mcp_tools(request: Request) -> Any:
    """Dependency to retrieve the live MCP tools from the application state."""
    tools = getattr(request.app.state, "live_mcp_tools", None)
    if not tools:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MCP tools are not initialized."
        )
    
    return tools
