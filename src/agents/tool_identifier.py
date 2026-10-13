from typing import List
from pydantic import BaseModel, Field, field_validator
from config.logging_config import logger
from src.llm_client.groq_client import LLMProvider
from langchain_core.messages import HumanMessage, SystemMessage

def retrieve_relevant_tool_definitions(user_query: str, all_mcp_tools: list, config: dict) -> list:
    """
    Production-Grade Dynamic Tool Pruning Engine.
    Keeps the structural validation contract purely inside the class body expression.
    """
    if not all_mcp_tools:
        return []
        
    # Guardrail: Handle non-actionable queries or empty spaces instantly
    clean_query = str(user_query).strip().lower()
    if not clean_query or clean_query in ["yes", "no", "ok", "ack", "confirm", "proceed", "hello", "hi"]:
        logger.info("ℹ️ Conversational turn detected. Skipping tool pruning, returning empty toolset.")
        return []

    # 1. Capture names for internal class validation reference closure
    valid_tool_names = [tool.name for tool in all_mcp_tools]
    valid_names_set = {name.strip().lower() for name in valid_tool_names}

    # 2. DEFINE THE CONTRACT STRICTLY INSIDE THE LOCAL SCOPE
    class DynamicToolSelectionContract(BaseModel):
        selected_tool_names: List[str] = Field(
            default=[],
            description="List of tool names strictly necessary to fulfill the request. Leave empty if no tool is needed."
        )
        is_conversational_only: bool = Field(
            description="Set to true if the query is a simple greeting, conversational confirmation, or contains no business action items."
        )

        # Class-level validator that enforces the runtime enum barrier
        @field_validator("selected_tool_names", mode="after")
        @classmethod
        def enforce_runtime_enum(cls, value: List[str]) -> List[str]:
            # Scrubs away any items that are not explicitly present in our active inventory array
            return [name for name in value if name.strip().lower() in valid_names_set]

    # Build the lightweight schema context catalog
    tool_directory = [
        {"name": tool.name, "description": getattr(tool, "description", "")} 
        for tool in all_mcp_tools
    ]
    
    llm = LLMProvider.get_conversational_engine() 
    structured_retriever = llm.with_structured_output(DynamicToolSelectionContract)
    
    system_instruction = (
        "You are an isolated, strict routing gatekeeper for an ERPNext agent platform.\n"
        "Your task is to analyze the user query and select ONLY the tools from the directory "
        "that are explicitly needed to construct the immediate underlying payload.\n\n"
        f"ALLOWED VALID ENUMS: {valid_tool_names}\n\n"
        "CRITICAL RULES:\n"
        "- If a query cannot be answered by a tool, or is purely conversational, select an empty list [].\n"
        "- Do not select 'nice to have' or secondary tools. Only select direct matches."
    )
    
    human_input = f"User Request: '{user_query}'\n\nAvailable System Tools:\n{tool_directory}"
    
    try:
        selection = structured_retriever.invoke(
            [
                SystemMessage(content=system_instruction),
                HumanMessage(content=human_input)
            ],
            config=config
        )
        
        if selection.is_conversational_only:
            logger.info("🎯 Classifier determined query is conversational-only. Pruning down to 0 tools.")
            return []

        # 3. DETERMINISTIC RE-MAPPING FROM SANITIZED SELECTION
        selected_names_set = {name.strip().lower() for name in selection.selected_tool_names}
        filtered_tools = [
            tool for tool in all_mcp_tools 
            if tool.name.strip().lower() in selected_names_set
        ]
        
        logger.info(f"🎯 Successfully pruned tools array from {len(all_mcp_tools)} down to {len(filtered_tools)} tools.")
        return filtered_tools
        
    except Exception as e:
        logger.error(f"🚨 Dynamic Retriever Exception: {e}. Falling back safely to empty tool routing.")
        return []
