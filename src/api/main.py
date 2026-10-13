# import uuid
# import logging
# import asyncio
# import json
# import time
# from contextlib import asynccontextmanager
# from typing import Any, Dict, List, Optional, Union
# from src.workflow.inputOutputModel import ChatRequest
# from config.logging_config import logger
# from fastapi import FastAPI, HTTPException, status
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import StreamingResponse  # Added for SSE streaming
# from langchain_core.messages import HumanMessage, AIMessage
# from pydantic import BaseModel, Field

# from langfuse import get_client
# from langfuse.langchain import CallbackHandler

# from src.mcp_server.mcpClient import run_mcp_http_agent
# from src.workflow.agent_workflow import compile_production_mcp_workflow
# from src.observbility.evaluators import ProductionAgentEvaluator
# from src.api.event_stream_generator import event_stream_generator

# langfuse_client = get_client()
# app_state: Dict[str, Any] = {}

# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     logger.info("Initializing MCP HTTP Client and tools...")
#     try:
#         live_mcp_tools = await run_mcp_http_agent()
#         compiled_workflow = compile_production_mcp_workflow(live_tools=live_mcp_tools)
#         app_state["live_mcp_tools"] = live_mcp_tools
#         app_state["workflow"] = compiled_workflow
#         logger.info("MCP Workflow compiled and ready for requests.")
#         yield
#     except Exception as e:
#         logger.critical(f"Failed to initialize MCP services: {str(e)}", exc_info=True)
#         raise e
#     finally:
#         logger.info("Cleaning up MCP Application context and resources...")
#         langfuse_client.shutdown()
#         app_state.clear()

# app = FastAPI(title="Production MCP Agent API", version="1.0.0", lifespan=lifespan)

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# @app.post("/api/v1/chat/stream")
# async def chat_streaming_endpoint(payload: ChatRequest):
#     """Streams the agent turn tokens downstream instantly using SSE protocol."""
#     if not app_state.get("workflow"):
#         raise HTTPException(status_code=503, detail="Agent engine is not ready.")
        
#     return StreamingResponse(
#         event_stream_generator(payload),
#         media_type="text/event-stream"
#     )

# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run("src.workflow.main:app", host="0.0.0.0", port=8001, reload=False)

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langfuse import get_client

from config.logging_config import logger
from src.mcp_server.mcpClient import run_mcp_http_agent
from src.workflow.agent_workflow import compile_production_mcp_workflow
from src.api.routes.chat import router as chat_router

# Initialize external tracking clients
langfuse_client = get_client()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing production MCP HTTP Client and engines...")
    try:
        # 1. Initialize core runtime models/services
        live_mcp_tools = await run_mcp_http_agent()
        compiled_workflow = compile_production_mcp_workflow(live_tools=live_mcp_tools)
        
        # 2. Store components into the isolated app state container
        app.state.live_mcp_tools = live_mcp_tools
        app.state.workflow = compiled_workflow
        
        logger.info("Application state securely mounted. MCP Workflow ready.")
        yield
    except Exception as e:
        logger.critical(f"Critical failure during MCP lifecycle initialization: {str(e)}", exc_info=True)
        raise e
    finally:
        logger.info("Initiating teardown: Cleaning up application context and sockets...")
        langfuse_client.shutdown()
        # Clear attributes to prevent memory leakage
        if hasattr(app.state, "workflow"): del app.state.workflow
        if hasattr(app.state, "live_mcp_tools"): del app.state.live_mcp_tools

# FastAPI App setup
app = FastAPI(
    title="Production MCP Agent API", 
    version="1.0.0", 
    lifespan=lifespan
)

# Cross-Origin Resource Sharing (CORS) setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Tighten this in production configuration
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Router Registration
app.include_router(chat_router, prefix="/api/v1")

if __name__ == "__main__":
    import uvicorn
    # points to this file structure explicitly 
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8001, reload=False)
