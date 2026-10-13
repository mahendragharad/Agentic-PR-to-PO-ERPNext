import json

import json

def clean_mcp_error(state_response):
    """
    Extracts and cleans the core error messaging from a raw MCP tool error dictionary.
    """
    try:
        # Get the nested error block
        error_data = state_response.get('response', {}).get('error', {})
        raw_msg = error_data.get('message', '')
        
        # Look for the internal JSON payload inside the error message string
        if 'unexpected error 404:' in raw_msg:
            # Extract the JSON string following the 404 error
            json_part = raw_msg.split('unexpected error 404:')[1].strip()
            parsed_json = json.loads(json_part)
            
            # Extract the actual Frappe/ERPNext system message string
            server_msg_str = json.loads(parsed_json.get('_server_messages', '[]'))[0]
            server_msg_dict = json.loads(server_msg_str)
            
            # The cleanest actual error message text
            clean_message = server_msg_dict.get('message', raw_msg)
        else:
            clean_message = raw_msg if raw_msg else "An unknown ERPNext error occurred."
            
    except Exception:
        # Fallback if structural parsing fails due to unexpected formatting changes
        clean_message = state_response.get('response', {}).get('error', {}).get('message', str(state_response))

    # Construct a lean, highly readable summary dict for the LLM
    return {
        "tool_failed": state_response.get('tool'),
        "action": state_response.get('response', {}).get('action'),
        "error_summary": clean_message,
        "suggestion": error_data.get('suggestion')
    }


def extract_tool_text(content) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = []

        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))

        return "\n".join(text_parts)

    if isinstance(content, dict):
        return json.dumps(content)

    return str(content)


def parse_tool_response(content) -> dict:
    text = extract_tool_text(content)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {
            "status": "ERROR",
            "error": {
                "message": text,
                "can_retry": "false"
            }
        }

    if isinstance(parsed, dict):
        return parsed

    return {
        "status": "ERROR",
        "error": {
            "message": "MCP returned a non-object response.",
            "details": parsed,
            "can_retry": "false"
        }
    }


import re
import json

def clean_last_response(last_res):
    """
    Safely extracts tool execution data and cleans deeply escaped inner 
    ERPNext/Frappe exception messages from a ToolMessage object.
    """
    # 1. Safely extract tool details from the object attributes
    tool_name = getattr(last_res, 'name', 'Unknown Tool')
    tool_call_id = getattr(last_res, 'tool_call_id', 'Unknown ID')
    
    # 2. Extract the raw text content
    content_list = getattr(last_res, 'content', [])
    raw_text = ""
    if content_list and isinstance(content_list, list):
        raw_text = content_list[0].get('text', '')
    
    # Defaults in case JSON parsing completely fails
    action = "Unknown Action"
    clean_error = "An unexpected error occurred."
    suggestion = "Please check parameters."
    
    # 3. Parse the outer JSON structure
    if raw_text:
        try:
            data = json.loads(raw_text)
            action = data.get('action', action)
            error_block = data.get('error', {})
            suggestion = error_block.get('suggestion', suggestion)
            raw_message = error_block.get('message', '')
            
            # 4. Use Regex to dig out the deeply escaped actual human message
            # Matches anything between \"message\":\" and \",\"as_table\"
            match = re.search(r'\\+"message\\+":\\+"(.*?)\\+"', raw_message)
            if match:
                clean_error = match.group(1).replace(r'\\', '') # Remove residual slashes
            else:
                # Fallback to the main message string if regex doesn't match
                clean_error = raw_message.split("unexpected error 404:")[0].strip()
                
        except Exception:
            clean_error = "Failed to parse the server error layout."

    # 5. Build the lean, optimal layout for your LLM or system logs
    return {
        "tool_failed": tool_name,
        "tool_call_id": tool_call_id,
        "action_context": action,
        "clean_error_message": clean_error,
        "suggestion": suggestion
    }
