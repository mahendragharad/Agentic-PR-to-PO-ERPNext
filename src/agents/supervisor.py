import time
import json
import copy
from config.logging_config import logger
from src.llm_client.groq_client import LLMProvider
from src.state.agentState import AgentWorkflowState
from typing import Dict, Any
from src.prompt_library.agent_prompts import AgentPrompt_Library
from langchain_core.messages import ToolMessage, SystemMessage

try:
    MAX_HISTORY_TURNS = 6  # Kept small (6 turns) for maximum generation speed
    PROMPT_REGISTRY = AgentPrompt_Library()
    logger.info("Successfully cached production prompts from Langfuse.")
except Exception as e:
    logger.critical(f"Failed to initialize Prompt Registry: {e}")
    raise e

def orchestrator_agent_node(state: AgentWorkflowState, config: Dict[str, Any]) -> Dict[str, Any]:
    conversation_history = state.get("messages", [])
    mcp_tools = config.get("configurable", {}).get("tools", [])
    llm = LLMProvider.get_conversational_engine()

    # --- 1. EVENT-DRIVEN MEMORY LEDGER (O(1) CONSTANT TIME) ---
    # Instead of looping through all history, we check ONLY the last message if it's a new tool execution.
    pr_details = state.get("pr_details", {}) or {}
    
    if conversation_history and isinstance(conversation_history[-1], ToolMessage):
        last_tool_msg = conversation_history[-1]
        content_str = str(last_tool_msg.content)
        
        # Fast, isolated field extraction from the immediate incoming tool payload
        try:
            parsed_content = json.loads(content_str)
            if isinstance(parsed_content, dict) and "extracted_fields" in parsed_content:
                pr_details.update(parsed_content["extracted_fields"])
                logger.info(f"⚡ Fast-track memory updated: {parsed_content['extracted_fields']}")
        except (json.JSONDecodeError, TypeError):
            pass

    # --- 2. TOKEN OPTIMIZATION: CONTEXT WINDOW TRUNCATION & CLEANING ---
    chat_messages = [m for m in conversation_history if not isinstance(m, SystemMessage)]
    recent_chat = chat_messages[-MAX_HISTORY_TURNS:] if len(chat_messages) > MAX_HISTORY_TURNS else chat_messages

    sanitized_chat = []
    for msg in recent_chat:
        clean_msg = copy.deepcopy(msg)
        
        # Immediate total clearance of heavy tool metadata schemas from the payload window
        if hasattr(clean_msg, "response_metadata") and isinstance(clean_msg.response_metadata, dict):
            clean_msg.response_metadata.clear()
            
        if hasattr(clean_msg, "additional_kwargs") and isinstance(clean_msg.additional_kwargs, dict):
            clean_msg.additional_kwargs.pop("tools", None)
            clean_msg.additional_kwargs.pop("tool_defs", None)
            clean_msg.additional_kwargs.pop("schemas", None)
            
        sanitized_chat.append(clean_msg)

    # --- 3. GROUNDING GROUNDWORK: STATIC LEDGER INJECTION ---
    # Injects parameters explicitly so the LLM remembers variables even if they slid out of history.
    memory_ledger_context = (
        f"### SESSION MEMORY LEDGER ###\n"
        f"Cached Operational Data: {json.dumps(pr_details)}\n"
        f"##############################\n\n"
    )

    enriched_system_prompt = memory_ledger_context + PROMPT_REGISTRY.orchestrator_prompt
    
    active_payload_messages = [SystemMessage(content=enriched_system_prompt)] + sanitized_chat

    started_at = time.perf_counter()

    # --- 4. EXECUTION ---
    llm_with_mcp_tools = llm.bind_tools(mcp_tools)
    ai_message = llm_with_mcp_tools.invoke(
        active_payload_messages, 
        config={"callbacks": config.get("callbacks", [])}
    )

    duration_seconds = time.perf_counter() - started_at
    logger.info(f"⚡ High-Performance Orchestrator turn executed in {duration_seconds:.3f}s")

    # --- 5. RETURN MUTATED STATES BACK TO CHECKPOINTER ---
    return {
        "messages": [ai_message],
        "last_error_context": None,
        "pr_details": pr_details
    }
