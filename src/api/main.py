import os
import sys
import asyncio
import logging
import subprocess
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langfuse import get_client
from pathlib import Path 
# Keep your relative infrastructure imports intact
from config.logging_config import logger
from src.mcp_server.mcpClient import run_mcp_http_agent
from src.workflow.agent_workflow import compile_production_mcp_workflow
from src.api.routes.chat import chat_router
from src.api.routes.login import user_router   

# Initialize external tracking clients
langfuse_client = get_client()


async def _wait_for_mcp_server(process: subprocess.Popen, timeout: float = 30.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    last_error = None

    while loop.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"MCP Server exited during startup with code {process.returncode}. "
                "Check the MCP Server output above for its startup error."
            )

        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", 8000),
                timeout=1.0,
            )
            writer.close()
            await writer.wait_closed()
            return
        except (OSError, asyncio.TimeoutError) as exc:
            last_error = exc
            await asyncio.sleep(0.25)

    raise RuntimeError(
        f"MCP Server did not accept connections on 127.0.0.1:8000 "
        f"within {timeout:.0f} seconds. Last connection error: {last_error}"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Declare globally at the start of the lifespan scope to prevent UnboundLocal errors
    global mcp_process
    mcp_process = None
    
    logger.info("Initializing production MCP HTTP Client and engines...")
    try:

        project_root = Path(__file__).resolve().parents[2]
        logger.info(f"Resolved MCP Server path target: {project_root}")
        
        logger.info("Launching background MCP Server process on port 8000...")

        env_context = os.environ.copy()
        env_context["PYTHONIOENCODING"] = "utf-8"
        env_context["PYTHONUTF8"] = "1"

        mcp_process = subprocess.Popen(
            [sys.executable, "-m", "src.mcp_server.server"],
            cwd=project_root,
            stdout=None,
            stderr=None,
            env=env_context,
        )

        await _wait_for_mcp_server(mcp_process)
            
        logger.info("MCP Server is accepting connections on port 8000.")

        # Trigger client orchestration handshake
        live_mcp_tools = await run_mcp_http_agent()
        compiled_workflow = compile_production_mcp_workflow(live_tools=live_mcp_tools)
        
        # Store active state components inside the framework container
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
        
        # FIX 3: Safe cleanup block wrapping to handle process closures
        if mcp_process:
            logger.info("Terminating background MCP process...")
            mcp_process.terminate()
            mcp_process.wait()
            
        # Prevent runtime memory leak issues
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
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Router Registration
app.include_router(router=chat_router, prefix="/api/v1")
app.include_router(router=user_router, prefix="/api/v2")

if __name__ == "__main__":
    import uvicorn
    # Read Render's assigned $PORT variable, fallback to 8001 for local testing.
    port_assignment = int(os.environ.get("PORT", 8001))
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=port_assignment, reload=False)
