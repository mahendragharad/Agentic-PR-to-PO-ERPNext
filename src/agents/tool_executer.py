import re
import json
import logging
import hashlib
import uuid
import copy
from datetime import datetime, timezone
from typing import Dict, Any, List
from pydantic import ValidationError
from langgraph.errors import GraphInterrupt
from langgraph.runtime import Runtime
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt
from config.logging_config import logger
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig 
from src.erpnext_client.pyload_schemas import CreateMaterialRequestInput, ConvertPRToPOInput, Purchase_Order_Id_Validator, Material_Request_Id_Validator, MaterialRequestDocSchema
from utils.cleaner import extract_tool_text, parse_tool_response, clean_mcp_error, clean_last_response
from langfuse import Langfuse
from config.settings import settings

PO_APPROVAL_TOOLS = {"convert_pr_to_draft_po", "submit_purchase_order"}
ERPNEXT_TOOLS = {
    "generate_material_request",
    "submit_material_request",
    "convert_pr_to_draft_po",
    "submit_purchase_order",
    "cancel_purchase_order",
    "delete_purchase_order",
    "get_material_request_details",
    "get_purchase_order_details",
}


def _remove_untrusted_session_args(tool_calls: List[Dict[str, Any]]) -> None:
    for call in tool_calls:
        call_args = call.get("args")
        if isinstance(call_args, dict):
            call_args.pop("erpnext_sid", None)


def _authenticated_execution_state(
    state: Dict[str, Any],
    messages: List[Any],
    last_message: AIMessage,
    tool_call_id: str,
    normalized_args: Dict[str, Any],
    erpnext_sid: str,
) -> Dict[str, Any]:
    execution_state = dict(state)
    execution_messages = list(messages)
    execution_message = copy.deepcopy(last_message)

    for execution_call in execution_message.tool_calls:
        execution_call_args = execution_call.get("args", {})
        if not isinstance(execution_call_args, dict):
            execution_call_args = {}
        else:
            execution_call_args = dict(execution_call_args)
        execution_call_args.pop("erpnext_sid", None)

        if execution_call["id"] == tool_call_id:
            execution_call_args = dict(normalized_args)

        execution_call["args"] = execution_call_args
        if execution_call["name"] in ERPNEXT_TOOLS:
            execution_call["args"]["erpnext_sid"] = erpnext_sid

    execution_messages[-1] = execution_message
    execution_state["messages"] = execution_messages
    return execution_state


def _parse_approval_tool_response(raw_result: Any, tool_name: str) -> Dict[str, Any]:
    result = parse_tool_response(raw_result)
    if str(result.get("status", "")).upper() != "SUCCESS":
        error = result.get("error")
        message = error.get("message") if isinstance(error, dict) else error
        raise RuntimeError(
            f"Could not load review details for {tool_name}: "
            f"{message or 'ERPNext returned an error.'}"
        )

    payload = result.get("payload")
    if not isinstance(payload, dict):
        raise RuntimeError(f"ERPNext returned invalid review details for {tool_name}.")
    return payload


async def _get_po_approval_request(
    tool_name: str,
    args: Dict[str, Any],
    thread_id: str,
    tool_call_id: str,
    mcp_tools: list,
    erpnext_sid: str,
) -> Dict[str, Any]:
    if tool_name == "convert_pr_to_draft_po":
        document_id = args["material_request_id"]
        document_type = "Material Request"
        reader_name = "get_material_request_details"
        reader_args = {"material_request_id": document_id}
    else:
        document_id = args["purchase_order_id"]
        document_type = "Purchase Order"
        reader_name = "get_purchase_order_details"
        reader_args = {"purchase_order_id": document_id}

    reader = next((tool for tool in mcp_tools if tool.name == reader_name), None)
    if reader is None:
        raise RuntimeError(f"Required read-only MCP tool '{reader_name}' is unavailable.")

    document = _parse_approval_tool_response(
        await reader.ainvoke({**reader_args, "erpnext_sid": erpnext_sid}),
        reader_name,
    )
    if document.get("name") != document_id:
        raise RuntimeError(
            f"ERPNext returned a different {document_type} than the one requested."
        )
    if not isinstance(document.get("items"), list) or not document["items"]:
        raise RuntimeError(f"{document_type} '{document_id}' has no reviewable line items.")

    if tool_name == "convert_pr_to_draft_po":
        if document.get("docstatus") != 1 or document.get("status") == "Ordered":
            raise RuntimeError(
                f"Material Request '{document_id}' is no longer eligible for conversion."
            )
        preview = {
            "document": document,
            "conversion": {
                "supplier": args["supplier"],
                "currency": args.get("currency", "INR"),
            },
        }
        action_label = "Create draft purchase order"
    else:
        if document.get("docstatus") != 0:
            raise RuntimeError(
                f"Purchase Order '{document_id}' is not a draft and cannot be submitted."
            )
        preview = {"document": document}
        action_label = "Submit purchase order"

    canonical_preview = json.dumps(
        preview,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    preview_hash = hashlib.sha256(canonical_preview.encode("utf-8")).hexdigest()
    approval_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"pr-to-po:{thread_id}:{tool_call_id}:{preview_hash}",
        )
    )

    return {
        "approval_id": approval_id,
        "tool_name": tool_name,
        "tool_call_id": tool_call_id,
        "thread_id": thread_id,
        "document_type": document_type,
        "document_id": document_id,
        "action_label": action_label,
        "preview": preview,
        "preview_hash": preview_hash,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


langfuse_client = Langfuse(
    public_key=settings.LANGFUSE_PUBLIC_KEY,
    secret_key=settings.LANGFUSE_SECRET_KEY,
    host=settings.LANGFUSE_BASE_URL
)

def truncate_erpnext_payload(content: str, max_chars: int = 1500) -> str:
    """
    Examines responses returned by tools and compresses massive JSON outputs
    to protect the context window token payload limits.
    """
    if not content:
        return content
    try:
        data = json.loads(content)
        # If the response contains a huge list of row data items, grab a lightweight sample
        if isinstance(data, dict) and "message" in data and isinstance(data["message"], list):
            records = data["message"]
            if len(records) > 2:
                data["message"] = records[:2]
                data["_meta_info"] = f"... [Truncated {len(records) - 2} raw items to optimize token limits] ..."
                return json.dumps(data)
    except Exception:
        pass # Not a valid JSON payload string, drop through to default string slicing

    if len(content) > max_chars:
        return content[:max_chars] + "\n... [Remaining payload output truncated to save system memory] ..."
    return content


def _normalize_pr_to_po_error(content: str) -> str:
    try:
        response = json.loads(content)
    except json.JSONDecodeError:
        return content

    if not isinstance(response, dict) or str(response.get("status", "")).upper() != "ERROR":
        return content

    error = response.get("error")
    if not isinstance(error, dict) or not isinstance(error.get("message"), str):
        return content

    message = error["message"].strip()
    prefix = "ERPNext server failed to convert Material Request to the PO Draft:"
    if prefix in message:
        message = message.split(prefix, 1)[1].strip()

    http_error = re.search(r"ERPNext API returned unexpected error (\d+):\s*", message)
    if http_error:
        status_code = http_error.group(1)
        try:
            response_body = json.loads(message[http_error.end():])
        except json.JSONDecodeError:
            message = f"ERPNext rejected the draft purchase order request (HTTP {status_code})."
        else:
            if not isinstance(response_body, dict):
                message = f"ERPNext rejected the draft purchase order request (HTTP {status_code})."
            else:
                detail = response_body.get("exception")
                if isinstance(detail, str) and detail.strip():
                    message = detail.split(":", 1)[-1].splitlines()[0].strip()
                else:
                    server_messages = response_body.get("_server_messages")
                    if isinstance(server_messages, str):
                        try:
                            server_messages = json.loads(server_messages)
                        except json.JSONDecodeError:
                            server_messages = []

                    found_server_message = False
                    if isinstance(server_messages, list):
                        for server_message in server_messages:
                            if isinstance(server_message, str):
                                try:
                                    server_message = json.loads(server_message)
                                except json.JSONDecodeError:
                                    continue
                            if isinstance(server_message, dict) and isinstance(
                                server_message.get("message"), str
                            ):
                                message = re.sub(
                                    r"\s+", " ",
                                    re.sub(
                                        r"<[^>]*>",
                                        " ",
                                        server_message["message"],
                                    ),
                                ).strip()
                                found_server_message = True
                                break
                    if not found_server_message:
                        message = f"ERPNext rejected the draft purchase order request (HTTP {status_code})."

    missing_link = re.fullmatch(
        r"Could not find\s+(.+?):\s*(.+)",
        message,
        flags=re.IGNORECASE,
    )
    if missing_link:
        entity, value = missing_link.groups()
        entity = entity.strip()
        message = (
            f"{entity} '{value.strip()}' was not found in ERPNext. "
            f"Check the {entity.lower()} name and try again."
        )

    if len(message) > 900:
        message = message[:897].rstrip() + "..."

    error["message"] = message
    return json.dumps(response, ensure_ascii=False)


def create_safe_mcp_execution_node(mcp_tools: list):
    """
    Closure Factory creating a production-hardened LangGraph Safe Execution Node.
    """
    notebook_tools = list(mcp_tools)
    underlying_tool_node = ToolNode(notebook_tools)
    
    async def safe_execution_node(state: dict, config: RunnableConfig) -> dict:
        print("\n" + "═"*80)
        print(" 🚀 STARTING SAFE MCP EXECUTION GATEWAY")
        print("═"*80)
        
        # 1. Fetch conversational timeline from state
        messages = state.get("messages", [])
        if not messages:
            print("⚠️ [State Guard] No messages found in context state array. Exiting node.")
            return {"messages": []}
            
        last_message = messages[-1]
        
        # Guard Clause: Confirm the orchestrator actually emitted structural tool dependencies
        if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
            print("ℹ️ [Execution Bridge Bypassed]: Last message does not contain executable tool calls.")
            return {"messages": []}
            
        tool_calls = last_message.tool_calls
        _remove_untrusted_session_args(tool_calls)

        tool_call = tool_calls[0] if isinstance(tool_calls, list) else tool_calls
        tool_name = tool_call["name"]
        tool_call_id = tool_call["id"]
        protected_calls = [
            call for call in tool_calls
            if call.get("name") in PO_APPROVAL_TOOLS
        ]
        
        print(f"🎯 [Target Tool Detected]: {tool_name}")
        
        # Extract the dictionary of arguments generated by the orchestrator engine
        original_args = tool_call.get("args", {})
        normalized_args = original_args.copy()

        # Clone and seed retry boundary logs state variables
        retry_counter = state.get("retry_counter") or {}
        if not isinstance(retry_counter, dict):
            retry_counter = {}
        retry_counter = retry_counter.copy()
        
        if tool_name not in retry_counter:
            retry_counter[tool_name] = 0

        # Initialize or clone permanent tracking metrics states safely
        pr_details = (state.get("pr_details") or {}).copy()
        active_pr_id = state.get("active_pr_id", None)
        active_po_id = state.get("active_po_id", None)

        # =====================================================================
        # STEP A: THE DEFENSIVE RUNTIME INTERCEPTOR GATEWAYS
        # =====================================================================
        if "ctx" in normalized_args and isinstance(normalized_args["ctx"], dict):
            normalized_args = normalized_args["ctx"]
        elif "payload" in normalized_args and isinstance(normalized_args["payload"], dict):
            normalized_args = normalized_args["payload"]

        # Session credentials come only from the authenticated request context.
        normalized_args.pop("erpnext_sid", None)

        # =====================================================================
        # STEP B: PRE-NETWORK LOCAL PYDANTIC CONTRACT VALIDATION
        # =====================================================================
        try:
            print(f"📋 [Validation Stage]: Running schema rules logic for [{tool_name}]...")
            
            if tool_name == "generate_material_request":
                raw_doc_payload = normalized_args.get("doc", normalized_args)
                validated_doc_model = MaterialRequestDocSchema.model_validate(raw_doc_payload)
                normalized_args = {"doc": validated_doc_model.model_dump()}

            elif tool_name in ["submit_material_request", "get_material_request_details"]:
                Material_Request_Id_Validator.model_validate(normalized_args)

            elif tool_name in ["submit_purchase_order", "cancel_purchase_order", "delete_purchase_order", "get_purchase_order_details"]:
                Purchase_Order_Id_Validator.model_validate(normalized_args)
                
            elif tool_name == "convert_pr_to_draft_po":
                normalized_args = ConvertPRToPOInput.model_validate(
                    normalized_args
                ).model_dump()
            else:
                target_tool = next((t for t in mcp_tools if t.name == tool_name), None)
                if target_tool and hasattr(target_tool, "args_schema") and target_tool.args_schema:
                    target_tool.args_schema.model_validate(normalized_args)

            print(f"🎉 SUCCESS: Validation pipeline completed perfectly for tool: [{tool_name}]. Sending to execution network.")

            if protected_calls and len(tool_calls) != 1:
                return {
                    "messages": [
                        ToolMessage(
                            content=(
                                "Purchase-order approval actions must be requested one at a time. "
                                "No tool in this request was executed."
                            ),
                            tool_call_id=call["id"],
                        )
                        for call in tool_calls
                    ],
                    "last_error_context": None,
                }

            if tool_name in PO_APPROVAL_TOOLS:
                thread_id = config.get("configurable", {}).get("thread_id")
                if not thread_id:
                    raise RuntimeError("A thread ID is required for purchase-order approval.")
                erpnext_sid = config.get("configurable", {}).get("erpnext_sid")
                if not erpnext_sid:
                    raise RuntimeError("An authenticated ERPNext session is required.")

                approval_request = await _get_po_approval_request(
                    tool_name=tool_name,
                    args=normalized_args,
                    thread_id=thread_id,
                    tool_call_id=tool_call_id,
                    mcp_tools=mcp_tools,
                    erpnext_sid=erpnext_sid,
                )
                logger.info(
                    "Purchase-order approval requested: tool=%s document=%s approval_id=%s",
                    tool_name,
                    approval_request["document_id"],
                    approval_request["approval_id"],
                )
                decision = interrupt(approval_request)
                if (
                    not isinstance(decision, dict)
                    or decision.get("approval_id") != approval_request["approval_id"]
                    or decision.get("preview_hash") != approval_request["preview_hash"]
                ):
                    result_code = "STALE_REVIEW"
                    result_text = (
                        "The reviewed document changed after it was displayed. "
                        "No purchase-order action was performed; request a fresh review."
                    )
                elif decision.get("decision") != "approved":
                    result_code = "REJECTED"
                    result_text = "The user rejected this purchase-order action. No action was performed."
                else:
                    result_code = None
                    result_text = ""

                if result_code:
                    return {
                        "messages": [
                            ToolMessage(
                                content=json.dumps(
                                    {"status": result_code, "message": result_text}
                                ),
                                tool_call_id=tool_call_id,
                            )
                        ],
                        "last_error_context": None,
                    }

            # Inject the user's ERPNext session only into the isolated execution copy.
            execution_state = state
            if any(
                call.get("name") in ERPNEXT_TOOLS
                for call in last_message.tool_calls
            ):
                erpnext_sid = config.get("configurable", {}).get("erpnext_sid")
                if not erpnext_sid:
                    raise RuntimeError("An authenticated ERPNext session is required.")
                execution_state = _authenticated_execution_state(
                    state=state,
                    messages=messages,
                    last_message=last_message,
                    tool_call_id=tool_call_id,
                    normalized_args=normalized_args,
                    erpnext_sid=erpnext_sid,
                )

            # 2. Execute underlying node over the infrastructure network
            base_output = await underlying_tool_node.ainvoke(
                execution_state,
                runtime=Runtime(),
            )
            emitted_messages = base_output.get("messages", [])

            if not emitted_messages:
                raise RuntimeError(f"MCP tool '{tool_name}' returned no ToolMessage.")

            # 3. Parse and sanitize tool response content size
            last_res = emitted_messages[-1]
            
            # Apply token payload compression guardrails before appending to history state
            tool_content = extract_tool_text(last_res.content)
            if tool_name == "convert_pr_to_draft_po":
                tool_content = _normalize_pr_to_po_error(tool_content)
            last_res.content = truncate_erpnext_payload(tool_content)
            
            tool_response = parse_tool_response(last_res.content)
            status = str(tool_response.get("status", "")).upper()
            mcp_error = tool_response.get("error")

            # 4. Handle Application-level Errors securely
            if status == "ERROR" or mcp_error:
                retry_counter[tool_name] += 1
                error_payload = {
                    "error_type": "ApplicationError",
                    "tool": tool_name,
                    "message": str(mcp_error or "ERPNext tool operation flagged execution failure status.")
                }
                return {
                    "messages": emitted_messages,
                    "last_error_context": json.dumps(error_payload),  # Safe string serialization
                    "retry_counter": retry_counter
                }

            # # If execution passes completely cleanly:
            # return {
            #     "messages": emitted_messages,
            #     "last_error_context": None, # Clean up lingering error context values
            #     "retry_counter": retry_counter
            # }

            # =====================================================================
            # ✨ EXTRACTION LAYER: AUTO-LOCK ASSETS INTO STATE UPON CLEAN SUCCESS
            # =====================================================================
            content_str = str(last_res.content)
            
            # Use dynamic regex strings to scan tool response output text for generated names
            pr_match = re.search(r"(MAT-MR-\d{4}-\d+)", content_str)
            po_match = re.search(r"(PO-\d{4}-\d+)", content_str)
            
            if pr_match:
                active_pr_id = pr_match.group(1)
                logger.info(f"🔑 Safe Node caught PR instantiation: {active_pr_id}")
            if po_match:
                active_po_id = po_match.group(1)
                logger.info(f"🔑 Safe Node caught PO instantiation: {active_po_id}")

            # Keep parameters loaded during user entry up-to-date
            if tool_name == "generate_material_request" and isinstance(normalized_args, dict):
                pr_details.update(normalized_args.get("doc", normalized_args))

            # Return mutated structural keys alongside the tool messages
            return {
                "messages": emitted_messages,
                "last_error_context": None, 
                "retry_counter": retry_counter,
                "pr_details": pr_details,
                "active_pr_id": active_pr_id,
                "active_po_id": active_po_id
            }

        # =====================================================================
        # STEP C: PRODUCTION COMPREHENSIVE EXCEPTION CATCHING & STRINGIFICATION
        # =====================================================================
        except GraphInterrupt:
            raise

        except ValidationError as val_err:
            retry_counter[tool_name] += 1
            error_payload = {
                "error_type": "ValidationError",
                "tool": tool_name,
                "message": "Pydantic contract parameter format enforcement failed.",
                "details": val_err.errors()
            }
            logger.warning(f"⚠️ Validation error encountered on tool [{tool_name}]: {val_err}")
            
            # Formulate an error message to feed back into the graph thread execution line
            err_msg = ToolMessage(
                content=f"Validation Failure: {str(val_err.errors())}",
                tool_call_id=tool_call_id
            )
            return {
                "messages": [err_msg],
                "last_error_context": json.dumps(error_payload), # Stringified for dynamic healing prompts
                "retry_counter": retry_counter
            }

        except Exception as e:
            retry_counter[tool_name] += 1
            error_payload = {
                "error_type": type(e).__name__,
                "tool": tool_name,
                "message": str(e)
            }
            logger.error(f"🚨 Runtime crash caught in execution gateway bridge for [{tool_name}]: {e}")
            
            err_msg = ToolMessage(
                content=f"Execution System Error: {str(e)}",
                tool_call_id=tool_call_id
            )
            return {
                "messages": [err_msg],
                "last_error_context": json.dumps(error_payload),
                "retry_counter": retry_counter
            }
            
    return safe_execution_node
