import json
from typing import List, Literal
from pydantic import BaseModel, Field
from config.logging_config import logger
from langgraph.graph import StateGraph, START, END
from src.llm_client.groq_client import LLMProvider
from src.state.agentState import AgentWorkflowState
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage, SystemMessage

class RouteIntent(BaseModel):
    """Structured schema enforcing a deterministic JSON contract for workflow classification."""
    requires_erp_tools: bool = Field(
        description="Set to True if the user wants to execute an action, fetch data, submit, confirm, proceed, or modify an ERPNext document like a PR or PO. Set to False ONLY for completely non-transactional chatter, greetings, or out-of-scope interactions."
    )
    suggested_conversational_reply: str = Field(
        description="If requires_erp_tools is False, generate a brief, polite conversational reply. If requires_erp_tools is True, leave this blank."
    )

def gateway_conditional_router(state: AgentWorkflowState) -> str:
    """Decides whether to route to the heavy orchestrator or end early."""
    if state.get("is_greeting") is True:
        return "__end__"
    return "orchestrator"

def orchestrator_conditional_router(state: AgentWorkflowState) -> str:
    """Determines whether a tool execution step is required or if we stop."""
    messages = state.get("messages", [])
    if not messages or not isinstance(messages[-1], AIMessage):
        return "__end__"
    
    if messages[-1].tool_calls:
        logger.info(f"🎯 Orchestrator routing to tool execution bridge for calls: {messages[-1].tool_calls}")
        return "mcp_execution_bridge"
        
    return "__end__"

def execution_conditional_router(state: AgentWorkflowState) -> str:
    """Diverts failed requests to healing loops or hands back control to the user."""
    messages = state.get("messages", [])
    last_error = state.get("last_error_context")
    
    if not last_error:
        return "orchestrator"
        
    tool_name = "unknown_tool"
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            tool_name = msg.tool_calls[0]["name"]
            break

    retry_dict = state.get("retry_counter") or {}
    if isinstance(retry_dict, str):
        try:
            retry_dict = json.loads(retry_dict)
        except Exception:
            retry_dict = {}

    current_retries = retry_dict.get(tool_name, 0)
    max_retries = state.get("max_retries", 3)

    if current_retries >= max_retries:
        logger.error(f"🚨 Circuit Breaker Triggered for [{tool_name}]. Dropping control to prevent token loop.")
        return "__end__"

    logger.warning(f"⚠️ Error detected during execution. Diverting to healing loop for: [{tool_name}]")
    return "orchestrator"

async def production_gateway_classifier_node(state: AgentWorkflowState) -> dict:
    """
    Enterprise-Grade Semantic Intent Classifier Node.
    Context-aware turn analysis that protects transactional confirmations from routing dropout.
    """
    conversation_history = state.get("messages", [])
    
    if not conversation_history:
        return {
            "messages": [AIMessage(content="Hello! How can I assist you with your ERPNext system today?")],
            "is_greeting": True
        }

    # FIX: Evaluate the context window to prevent dropping confirmations
    recent_messages = conversation_history[-3:] if len(conversation_history) > 3 else conversation_history
    
    # Format a compact history block so the classifier sees what happened right before
    formatted_context = ""
    for msg in recent_messages:
        role = "User" if msg.type == "human" else "Agent"
        formatted_context += f"{role}: {msg.content}\n"

    llm = LLMProvider.get_conversational_engine()
    structured_classifier = llm.with_structured_output(RouteIntent)
    
    system_prompt = (
        "You are an enterprise-grade intent routing classifier for an ERPNext agent network.\n"
        "Analyze the interaction context history snippet. Determine if the user's latest message "
        "is an active transaction request, OR a direct confirmation/acknowledgment/proceed instruction "
        "for a transaction the agent just proposed.\n\n"
        "CRITICAL RULE:\n"
        "- If the user says 'confirm', 'go ahead', 'yes', or 'proceed' following an agent setup proposal, "
        "you MUST classify requires_erp_tools as TRUE."
    )
    
    try:
        classification_result: RouteIntent = await structured_classifier.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Recent Interaction Window:\n{formatted_context}")
        ])
        
        if not classification_result.requires_erp_tools:
            logger.info("🛡️ Intent Classifier: Detected conversational turn. Deflecting payload to early exit lane.")
            return {
                "messages": [AIMessage(content=classification_result.suggested_conversational_reply)],
                "is_greeting": True
            }
            
        logger.info("🎯 Intent Classifier: Valid ERP operational sequence verified. Routing payload to Orchestrator.")
        return {"is_greeting": False}
        
    except Exception as e:
        logger.error(f"🚨 Production Classifier Exception: {e}. Executing safe failover route.")
        return {"is_greeting": False}