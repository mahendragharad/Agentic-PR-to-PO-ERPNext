import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient
from config.logging_config import logger 

async def run_mcp_http_agent():
    client = MultiServerMCPClient({
        "erpnext": {
            "transport": "streamable_http",          # note: underscore here, adapter expects this form
            "url": "http://127.0.0.1:8000/mcp",       # full URL: host + port + mount_path
        }
    })

    logger.info("⏳ Connecting to Streamable HTTP MCP server at /mcp...")
    tools = await client.get_tools()
    logger.info(f"✅ Successfully loaded {len(tools)}")
    return tools
