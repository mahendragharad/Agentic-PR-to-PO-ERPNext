from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from src.agent_router.router import (
    execution_conditional_router,
    gateway_conditional_router,
    orchestrator_conditional_router,
    production_gateway_classifier_node,
)
from src.agents.supervisor import orchestrator_agent_node
from src.agents.tool_executer import create_safe_mcp_execution_node
from src.state.agentState import AgentWorkflowState

def compile_production_mcp_workflow(live_tools: list):
    """
    Compile the high-availability ERPNext Agentic Workflow Graph.
    Ensures safe multi-turn context retention, context-aware intent classification,
    and automated defensive error self-healing.
    """
    workflow = StateGraph(AgentWorkflowState)

    # --- NODE INJECTION & SYSTEM REGISTRATION ---
    workflow.add_node("production_gateway", production_gateway_classifier_node)
    
    workflow.add_node(
        "orchestrator",
        lambda state, config: orchestrator_agent_node(state, config),
    )
    
    workflow.add_node(
        "mcp_execution_bridge",
        create_safe_mcp_execution_node(live_tools),
    )

    # --- DETERMINISTIC GRAPH EDGES ---
    workflow.add_edge(START, "production_gateway")

    # --- STATIC ROUTING ARRAYS (Synchronized with String-Literal Outputs) ---
    
    # 1. Gateway Routing Target Matrix
    workflow.add_conditional_edges(
        "production_gateway",
        gateway_conditional_router,
        {
            "orchestrator": "orchestrator",
            "__end__": END,  # Standardizes string matching from router
        },
    )

    # 2. Orchestrator Routing Target Matrix
    workflow.add_conditional_edges(
        "orchestrator",
        orchestrator_conditional_router,
        {  
            "mcp_execution_bridge": "mcp_execution_bridge",
            "__end__": END,  # Catches conversational outputs and drops cleanly to client
        },
    )

    # 3. Infrastructure Tool Execution Target Matrix
    workflow.add_conditional_edges(
        "mcp_execution_bridge",
        execution_conditional_router,
        {
            "orchestrator": "orchestrator",      # Reroutes to healing loop or next sequence turn
            "production_gateway": "production_gateway", # Resets graph turn space
            "__end__": END,                      # Circuit breaker drops out to user safely
        },
    )

    # --- COMPILATION WITH PERSISTENT VOLATILE CHECKPOINTER ---
    return workflow.compile(checkpointer=MemorySaver())