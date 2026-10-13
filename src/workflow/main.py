import uuid
import logging
import asyncio
import json
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Union
from src.api.endpoint_schemas import ChatRequest
from config.logging_config import logger
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse  # Added for SSE streaming
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import BaseModel, Field

from langfuse import get_client
from langfuse.langchain import CallbackHandler

from src.mcp_server.mcpClient import run_mcp_http_agent
from src.workflow.agent_workflow import compile_production_mcp_workflow
from src.observbility.evaluators import ProductionAgentEvaluator

langfuse_client = get_client()
app_state: Dict[str, Any] = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing MCP HTTP Client and tools...")
    try:
        live_mcp_tools = await run_mcp_http_agent()
        compiled_workflow = compile_production_mcp_workflow(live_tools=live_mcp_tools)
        app_state["live_mcp_tools"] = live_mcp_tools
        app_state["workflow"] = compiled_workflow
        logger.info("MCP Workflow compiled and ready for requests.")
        yield
    except Exception as e:
        logger.critical(f"Failed to initialize MCP services: {str(e)}", exc_info=True)
        raise e
    finally:
        logger.info("Cleaning up MCP Application context and resources...")
        langfuse_client.shutdown()
        app_state.clear()

app = FastAPI(title="Production MCP Agent API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def event_stream_generator(payload: ChatRequest):   
    workflow = app_state.get("workflow")
    live_mcp_tools = app_state.get("live_mcp_tools")
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

    # 1. Fetch the existing state history checkpoint ledger from the checkpointer
        # 1. Fetch the existing state history checkpoint ledger from the checkpointer
    state_history = await workflow.aget_state(config)

    # ✨ ADD THIS LINE: Intercept the form payload passed from the Streamlit UI frame
    state_history = await workflow.aget_state(config)
    form_data = payload.metadata.get("structured_doc", {}) if payload.metadata else {}

    # 2. CRITICAL DEDUPLICATION CHECK & INITIALIZATION:
    if not state_history.values:
        inputs = {
            "messages": [new_message],
            "retry_counter": {},
            "max_retries": 3,
            "last_error_context": None,
            "is_greeting": False,
            # 🔒 Entire form dictionary containing the dates gets pre-seeded perfectly
            "pr_details": form_data, 
            "active_pr_id": None,
            "active_po_id": None,
            "session_token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        }
    else:
        # Subsequent turns: send ONLY the new message.
        # If the form was updated mid-session, optionally allow merging values
        logger.info(f"🔄 Appending execution parameters to historical thread container context: {payload.thread_id}")
        inputs = {
            "messages": [new_message]
        }
        if form_data:
            inputs["pr_details"] = form_data

    
    captured_final_state = {}
    
    # Track whether token text has already been dynamically streamed to the client
    has_streamed_chunks = False
    
    try:
        # Stream events using LangGraph v2 streaming tokens protocol
        async for event in workflow.astream_events(inputs, config=config, version="v2"):
            kind = event.get("event")

            # Continuously extract state blueprints as they traverse your self-healing chains
            if "state" in event.get("metadata", {}):
                captured_final_state = event["metadata"]["state"]
            
            # Track A: Catch standard conversational chat model streaming tokens (Used by Orchestrator)
            if kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    has_streamed_chunks = True
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk.content})}\n\n"
                    
            # 🔥 Track B: FALLBACK FIX FOR GREETINGS AND NON-STREAMED RESPONSES
            # Only flushes full messages if the streaming token system above did not execute.
            elif (
                kind == "on_chain_end"
                and event.get("name") in {"production_gateway", "orchestrator"}
            ):
                if has_streamed_chunks:
                    # Skip duplication: the token engine has already processed and transmitted this text
                    continue

                output_data = event.get("data", {}).get("output", {})
                messages = output_data.get("messages", [])

                if messages:
                    last_msg = messages[-1]

                    # If the gateway node successfully built an assistant response message, stream it down
                    if isinstance(last_msg, AIMessage):
                        content = last_msg.content

                        if isinstance(content, str) and content.strip():
                            logger.info(f"✨ Fallback path executed for node {event.get('name')}. Flushing full message payload.")
                            yield (
                                f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
                            )
                                    
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

@app.post("/api/v1/chat/stream")
async def chat_streaming_endpoint(payload: ChatRequest):
    """Streams the agent turn tokens downstream instantly using SSE protocol."""
    if not app_state.get("workflow"):
        raise HTTPException(status_code=503, detail="Agent engine is not ready.")
        
    return StreamingResponse(
        event_stream_generator(payload),
        media_type="text/event-stream"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.workflow.main:app", host="0.0.0.0", port=8001, reload=False)
