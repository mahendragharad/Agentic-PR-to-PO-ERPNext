from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import ToolMessage
from config.logging_config import logger
from src.api.endpoint_schemas import ChatRequest
from src.api.dependencies import get_agent_workflow, get_mcp_tools
from src.api.event_stream_generator import event_stream_generator
from utils.cleaner import extract_tool_text, parse_tool_response

router = APIRouter(prefix="/chat", tags=["Chat & Agents"])

@router.post("/stream", summary="Stream agent interactions using SSE")
async def chat_streaming_endpoint(
    payload: ChatRequest,
    workflow: Any = Depends(get_agent_workflow),  # Fixed syntax here
    live_mcp_tools : Any = Depends(get_mcp_tools)
):
    """
    Streams the agent turn tokens downstream instantly using the SSE protocol.
    """
    return StreamingResponse(
        event_stream_generator(payload, workflow=workflow, live_mcp_tools=live_mcp_tools),
        media_type="text/event-stream"
    )

