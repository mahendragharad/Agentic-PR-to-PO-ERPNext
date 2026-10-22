import asyncio
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from langgraph.types import Command
from config.logging_config import logger
from src.api.endpoint_schemas import ApprovalDecisionRequest, ChatRequest
from src.api.dependencies import get_agent_workflow, get_mcp_tools
from src.api.event_stream_generator import event_stream_generator
from src.auth.erp_next_auth import (
    AsyncERPNextService,
    get_authenticated_erp_service,
)
from src.workflow.hitl_manager import (
    get_latest_tool_result,
    get_pending_approval,
    get_tool_result,
)

chat_router = APIRouter(prefix="/chat", tags=["Chat & Agents"])
_thread_locks: dict[str, asyncio.Lock] = {}


def _thread_lock(thread_id: str) -> asyncio.Lock:
    lock = _thread_locks.get(thread_id)
    if lock is None:
        lock = asyncio.Lock()
        _thread_locks[thread_id] = lock
    return lock

@chat_router.post("/stream", summary="Stream agent interactions using SSE")
async def chat_streaming_endpoint(
    payload: ChatRequest,
    workflow: Any = Depends(get_agent_workflow),  # Fixed syntax here
    live_mcp_tools: Any = Depends(get_mcp_tools),
    erp_service: AsyncERPNextService = Depends(get_authenticated_erp_service),
):
    """
    Streams the agent turn tokens downstream instantly using the SSE protocol.
    """
    state_config = {
        "configurable": {
            "thread_id": payload.thread_id,
            "tools": live_mcp_tools,
        }
    }
    snapshot = await workflow.aget_state(state_config)
    if get_pending_approval(snapshot) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This conversation is waiting for an approval decision.",
        )

    return StreamingResponse(
        event_stream_generator(
            payload,
            workflow=workflow,
            live_mcp_tools=live_mcp_tools,
            erpnext_sid=erp_service.cookies["sid"],
        ),
        media_type="text/event-stream"
    )


@chat_router.post("/resume", summary="Approve or reject a pending purchase-order action")
async def resume_approval(
    payload: ApprovalDecisionRequest,
    workflow: Any = Depends(get_agent_workflow),
    live_mcp_tools: Any = Depends(get_mcp_tools),
    erp_service: AsyncERPNextService = Depends(get_authenticated_erp_service),
):
    """Resume only the exact pending approval stored in the graph checkpoint."""
    async with _thread_lock(payload.thread_id):
        config = {
            "configurable": {
                "thread_id": payload.thread_id,
                "tools": live_mcp_tools,
                "erpnext_sid": erp_service.cookies["sid"],
            }
        }
        snapshot = await workflow.aget_state(config)
        approval = get_pending_approval(snapshot)
        if approval is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="There is no pending approval for this conversation.",
            )
        if (
            approval.get("approval_id") != payload.approval_id
            or approval.get("preview_hash") != payload.preview_hash
            or approval.get("thread_id") != payload.thread_id
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The approval request is stale or does not match this conversation.",
            )

        logger.info(
            "Received purchase-order approval decision: decision=%s approval_id=%s document=%s",
            payload.decision,
            payload.approval_id,
            approval.get("document_id"),
        )
        try:
            await workflow.ainvoke(
                Command(
                    resume={
                        "approval_id": payload.approval_id,
                        "preview_hash": payload.preview_hash,
                        "decision": payload.decision,
                    }
                ),
                config=config,
            )
            updated_snapshot = await workflow.aget_state(config)
        except Exception as exc:
            logger.exception(
                "Failed to resume purchase-order approval for thread %s",
                payload.thread_id,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not resume the purchase-order workflow.",
            ) from exc

        next_approval = get_pending_approval(updated_snapshot)
        latest_result = get_latest_tool_result(updated_snapshot)
        if next_approval is not None:
            return {
                "status": "approval_required",
                "approval_payload": next_approval,
                "action_result": latest_result,
            }

        if payload.decision == "rejected":
            return {
                "status": "rejected",
                "document_id": approval.get("document_id"),
                "action_result": latest_result,
            }
        action_result = get_tool_result(
            updated_snapshot,
            approval.get("tool_call_id"),
        )
        if action_result and action_result.get("status") == "STALE_REVIEW":
            return {
                "status": "stale_review",
                "document_id": approval.get("document_id"),
                "message": action_result.get("message"),
            }
        if not isinstance(action_result, dict):
            return {
                "status": "failed",
                "message": "The approved tool call did not return a result.",
            }
        if str(action_result.get("status", "")).upper() != "SUCCESS":
            return {
                "status": "failed",
                "action_result": action_result,
            }

        result_payload = (
            action_result.get("payload")
        )
        po_id = None
        if isinstance(result_payload, dict):
            po_id = result_payload.get("generated_po_id") or result_payload.get("source_po_id")

        return {
            "status": "completed",
            "action_result": action_result,
            "po_id": po_id,
        }
