import sys
import os
import sys
import asyncio
import logging
from langchain_core.messages import HumanMessage
from langchain_core.messages import HumanMessage
from src.mcp_server.mcpClient import run_mcp_http_agent
from src.agents.supervisor import orchestrator_agent_node
from src.workflow.agent_workflow import compile_production_mcp_workflow
from langchain_mcp_adapters.client import MultiServerMCPClient
from langfuse.langchain import CallbackHandler

async def run_execution() :

    live_mcp_tools = await run_mcp_http_agent()   
    app = compile_production_mcp_workflow(live_tools=live_mcp_tools)

    handler = CallbackHandler()
    
    # Define thread session configuration parameters
    config = {
        "callbacks": [handler], 
        "configurable": {
            "thread_id": "user_session_abc_123", # Unique per user chat room session
            "tools": live_mcp_tools
        }
    }

    # Initial State setup values (used to seed the graph structure)
    initial_state = {
        "messages": [],
        "retry_counter": {},
        "max_retries": 3,
        "last_error_context": None
    }

    # =====================================================================
    # NEW RUNTIME INTERACTIVE LOOP
    # =====================================================================

    print("\n🚀 Production MCP Workflow Activated.")
    print("Type your queries below. Type 'exit' or 'quit' to stop.\n")

    # Flag to check if we need to send the full initial state layout on the very first turn
    is_first_turn = True

    while True:
        try:
            # 1. Capture live query from the terminal
            user_query = input("\nYou: ")
            
            # Exit conditions
            if user_query.lower() in ["exit", "quit", "q"]:
                print("Ending session. Goodbye!")
                break
                
            if not user_query.strip():
                continue

            # 2. Package the query as a LangChain Message object
            new_message = HumanMessage(content=user_query)

            print("🤖 Agents are working and executing MCP tools...")

            # 3. Invoke the graph
            if is_first_turn:
                # First turn: Pass initial configuration keys along with the message
                initial_state["messages"] = [new_message]
                response = await app.ainvoke(initial_state, config=config)
                is_first_turn = False
            else:
                # Subsequent turns: LangGraph's thread_id automatically manages history.
                # Just pass the new message; it appends it seamlessly.
                response = await app.ainvoke({"messages": [new_message]}, config=config)

            # 4. Print the final response from the agent collection
            if "messages" in response and response["messages"]:
                last_msg = response["messages"][-1]
                print(f"\nAgent:\n{last_msg.content}")
            else:
                print(f"\nSystem State Update:\n{response}")

        except KeyboardInterrupt:
            print("\nSession interrupted.")
            break

if __name__ == "__main__":
    asyncio.run(run_execution())