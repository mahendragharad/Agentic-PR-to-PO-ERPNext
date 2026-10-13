import uuid
import logging
import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Union
from config.logging_config import logger
from src.api.endpoint_schemas import ChatRequest
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import BaseModel, Field

from langfuse import get_client
from langfuse.langchain import CallbackHandler
from src.observbility.evaluators import ProductionAgentEvaluator

langfuse_client = get_client()

# 🚀 PRODUCTION STANDARD: Pure functional generator decoupled from global variable states.
async def event_stream_generator(payload: ChatRequest, workflow: Any, live_mcp_tools: List[Any]):   
    start_execution_timestamp = time.time()
    target_trace_id = str(uuid.uuid4())
    langfuse_handler = CallbackHandler()

    config = {
        "callbacks": [langfuse_handler],
        "run_id": target_trace_id,
        "session_id": payload.thread_id,
        "metadata": {
            "langfuse_user_id": payload.user_id,        
            "langfuse_session_id": payload.thread_id,   
            "langfuse_tags": ["fastapi-production", "mcp-agent-stream"],
            **payload.metadata                          
        },
        "configurable": {
            "thread_id": payload.thread_id,
            "tools": live_mcp_tools,
        },
    }

    new_message = HumanMessage(content=payload.query)

    # ✅ This will now run perfectly without throwing NoneType exceptions
    state_history = await workflow.aget_state(config)
    form_data = payload.metadata.get("structured_doc", {}) if payload.metadata else {}

    if not state_history.values:
        inputs = {
            "messages": [new_message],
            "retry_counter": {},
            "max_retries": 3,
            "last_error_context": None,
            "is_greeting": False,
            "pr_details": form_data, 
            "active_pr_id": None,
            "active_po_id": None,
            "session_token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        }
    else:
        logger.info(f"🔄 Appending execution parameters to historical thread container context: {payload.thread_id}")
        inputs = {
            "messages": [new_message]
        }
        if form_data:
            inputs["pr_details"] = form_data

    captured_final_state = {}
    has_streamed_chunks = False
    
    try:
        async for event in workflow.astream_events(inputs, config=config, version="v2"):
            kind = event.get("event")

            if "state" in event.get("metadata", {}):
                captured_final_state = event["metadata"]["state"]
            
            if kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    has_streamed_chunks = True
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk.content})}\n\n"
                    
            elif (
                kind == "on_chain_end"
                and event.get("name") in {"production_gateway", "orchestrator"}
            ):
                if has_streamed_chunks:
                    continue

                output_data = event.get("data", {}).get("output", {})
                messages = output_data.get("messages", [])

                if messages:
                    last_msg = messages[-1]
                    if isinstance(last_msg, AIMessage):
                        content = last_msg.content
                        if isinstance(content, str) and content.strip():
                            logger.info(f"✨ Fallback path executed for node {event.get('name')}. Flushing full message payload.")
                            yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"

    except Exception as exc:
        logger.error(f"Streaming Error on thread {payload.thread_id}: {str(exc)}", exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'content': 'Internal pipeline error'})}\n\n"

    finally:
        try:
            real_trace_id = None
            if hasattr(langfuse_handler, "last_trace_id") and langfuse_handler.last_trace_id:
                real_trace_id = langfuse_handler.last_trace_id
            elif hasattr(langfuse_handler, "trace_id") and langfuse_handler.trace_id:
                real_trace_id = langfuse_handler.trace_id

            if not captured_final_state:
                latest_graph_snapshot = await workflow.aget_state(config)
                captured_final_state = latest_graph_snapshot.values if latest_graph_snapshot else {}

            if captured_final_state:
                ProductionAgentEvaluator.evaluate_and_score_trace(
                    trace_id=real_trace_id,  
                    user_query=payload.query,
                    final_state=captured_final_state,
                    start_time=start_execution_timestamp
                )
        except Exception as eval_crash:
            logger.error(f"CRITICAL: Evaluator crashed internally: {str(eval_crash)}", exc_info=True)
        finally:
            try:
                langfuse_client.flush()  
            except Exception as flush_err:
                logger.error(f"Failed to flush Langfuse buffers: {str(flush_err)}")