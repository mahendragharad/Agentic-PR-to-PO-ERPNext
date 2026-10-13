import json 
from datetime import date
from config.settings import settings
from mcp.server.fastmcp import FastMCP
from config.logging_config import logger
from typing import Dict, Any, List, Optional, Union
from pydantic import ValidationError

from src.erpnext_client.base_client import ERPNextBaseClient
from src.auth.token_manager import ERPNextAuthorizationCodeManager
from pydantic import BaseModel, Field, field_serializer, field_validator
from src.erpnext_client.pyload_schemas import MaterialRequestItemSchema, ConvertPRToPOInput, Purchase_Order_Id_Validator, Material_Request_Id_Validator, MaterialRequestDocSchema, CreateMaterialRequestInput
from src.erpnext_client.exceptions import ERPNextAuthError, TokenCacheNotFoundError, InvalidCredentialsError 

from mcp.types import TextContent, ImageContent, EmbeddedResource

logger.info("--Initialize FastMCP Server--")
mcp = FastMCP(
    name="ERPNext-Core-Engine",
    instructions="Use this server to read and write data across ERPNext modules.",
    host="0.0.0.0",    
    port=8000,
    stateless_http=True,
)

logger.info("🧬 Dependency Initialization Block")
logger.info("Wire up your working, production-ready core components")
token_manager = ERPNextAuthorizationCodeManager(
        token_url=settings.token_url,
        client_id=settings.erpnext_client_id,
        client_secret=settings.erpnext_client_secret,
        cache_file=settings.absolute_token_path,
        scope=settings.erpnext_scope
    )

client = ERPNextBaseClient(
    base_url=str(settings.erpnext_base_url), 
    token_manager=token_manager
)

def format_tool_response(success: bool, action: str, data: Any = None, error_details: Optional[str] = None) -> str:
    """
    Enforces a strict, highly semantic JSON string response contract.
    This structured envelope is designed so that agents can explicitly read
    status and error codes natively in their historical execution stream.
    """
    response = {
        "status": "SUCCESS" if success else "ERROR",
        "action": action,
        "payload": data if success else None,
        "error": {
            "message": error_details,
            "can_retry": "true" if (error_details and "timeout" in error_details.lower() or "50" in error_details) else "false",
            "suggestion": "Check missing parameters or correct data properties based on details." if not success else None
        } if not success else None
    }
    return json.dumps(response, indent=2)

@mcp.tool()
def generate_material_request(doc : MaterialRequestDocSchema) -> str :
    """
    Creates a new Material Request / Purchase Request in ERPNext using the provided item, quantity, pricing, company, warehouse, and date details.
    """
    action_name = "generate_material_request"
    logger.info(f"creating material request for with action {action_name}")
    logger.info(f"MCP Tool Triggered: {action_name} | Building PR for")

    try :
        print("========== MCP TOOL DEBUG ==========")
        print("doc:", doc)
        print("doc type:", type(doc))
        
        if isinstance(doc, MaterialRequestDocSchema):
            validated_doc = doc
        elif isinstance(doc, dict) and "doc" in doc:
            validated_doc = MaterialRequestDocSchema.model_validate(doc["doc"])
        elif isinstance(doc, dict):
            validated_doc = MaterialRequestDocSchema.model_validate(doc)
        else:
            raise ValueError("Target validation payload must resolve to a valid MaterialRequestDocSchema.")

        validated_po_payload = {
            "doc" : validated_doc.model_dump()
        }

        logger.info(f"-- Payload validation completed to generate the Purchase / Material Request--")
        endpoint = "api/method/frappe.client.insert"
        raw_response = client.request("POST", endpoint, json=validated_po_payload)

        if not raw_response:
            raise ValueError(f"ERPNext core mapping engine returned an empty data structure while creating PR/MR request.")

        message: Dict[str, Any] = raw_response["message"]
        items_data = message.get("items", [])

        formatted_items = [
            {
                "qty": item.get("qty", 0.0),
                "uom": item.get("uom", "Nos"),
                "rate": item.get("rate", 0.0),
                "warehouse": item.get("warehouse"),
            }
            for item in items_data
        ]

        response_to_return = {
            "name": message.get("name"),
            "transaction_date": message.get("transaction_date"),
            "schedule_date": message.get("schedule_date"),
            "company": message.get("company"),
            "buying_price_list": message.get("buying_price_list"),
            "set_warehouse": message.get("set_warehouse"),
            "items": formatted_items
        }

        return format_tool_response(success=True, action=action_name, data=response_to_return)
    
    except Exception as e :
        err_msg = f"ERPNext server rejected Purchase Request / Material Request validation criteria: {str(e)}"
        logger.error(f"MCP {action_name} Error: {err_msg}", exc_info=True)
        return format_tool_response(success=False, action=action_name, error_details=err_msg)

@mcp.tool()
def submit_material_request(material_request_id : str) -> str :
    """
    Submits an existing Draft Material Request (Purchase Requisition) in ERPNext by its unique document Name/ID.
    Transitions docstatus from 0 (Draft) to 1 (Submitted).
    """
    action_name = "submit_material_request"

    try :
        pr_name = material_request_id
        
        if not pr_name:
            err_msg = "Validation Blocked: The argument parameter key 'material_request_id' is missing or null."
            return format_tool_response(success=False, action=action_name, error_details=err_msg)
        
        logger.info(f"Let's validate the PR _id before submitting it : {pr_name}")
        logger.info(f"Retrieving current draft structure for document: {pr_name}")
        draft_doc = client.request("GET", f"api/resource/Material Request/{pr_name}")
        doc_payload = draft_doc.get("data")

        if not doc_payload :
            raise ValueError(f"Target Material Request '{pr_name}' could not be located while submitting the PR/MR request.")

        if doc_payload.get("docstatus") == 1:
            err_msg = (
                f"Transformation Blocked: The Material Request '{pr_name}' is already submitted. Skipping API action."
                "ERPNext backend mapping engines cannot resubmit resource documents."
            )
            
            logger.warning(f"Document {pr_name} is already submitted. Skipping API action.")

            return format_tool_response(
                    success=False,
                    action=action_name,
                    error_details=err_msg
                )

        logger.info(f"MCP Tool Triggered: {action_name} | Submitting PR: {pr_name}")
        logger.info(f"Dispatching signed submission command payload to ERPNext for {pr_name}...")

        endpoint = f"api/resource/Material Request/{pr_name}"
        raw_response = client.request("PUT", endpoint, json={"docstatus" : 1})

        return format_tool_response(
            success=True,
            action=action_name,
            data=raw_response.get("data", {})
        )

    except Exception as e:
        err_msg = f"ERPNext server failed to submit Material Request: {str(e)}"
        logger.error(f"MCP {action_name} System Error: {err_msg}", exc_info=True)

        return format_tool_response(
            success=False,
            action=action_name,
            error_details=err_msg
        )

@mcp.tool()
def convert_pr_to_draft_po(material_request_id : str, supplier : str, currency : str) -> str :
    """
    Converts a submitted ERPNext Material Request (PR) into a fresh, saved Draft Purchase Order.
    Enforces strict pre-flight docstatus check gates to prevent engine process crashes.
    """
    action_name = "convert_pr_to_draft_po"
    pr_id = material_request_id

    if not pr_id:
        err_msg = "Validation Blocked: The argument parameter key 'material_request_id' is missing or null."
        return format_tool_response(success=False, action=action_name, error_details=err_msg)
    
    logger.info(f"MCP Tool Triggered: {action_name} | Target Source PR: {pr_id}")

    try :
        logger.info(f"Executing safety pre-flight check on document: {pr_id}")
        raw_pr_response = client.request("GET", f"api/resource/Material Request/{pr_id}")
        pr_data = raw_pr_response.get("data", {})

        if not pr_data:
            raise ValueError(f"ERPNext core mapping engine returned an empty data structure for {pr_id}.")

        items_data = pr_data.get("items", [])
        pr_status = pr_data.get("status")
        
        # Guard clause against empty items array before index access
        if not items_data:
            raise ValueError(f"ERPNext core mapping engine returned no items for {pr_id}.")
        items = items_data[0]

        if not pr_status:
            raise ValueError(f"ERPNext core mapping engine returned an empty status structure for {pr_id}.")

        logger.info("Extracting docstatus configuration flags")
        # In ERPNext, docstatus is an integer (0, 1, or 2), not a dict. Defaulting to None if missing.
        docstatus = pr_data.get("docstatus")

        # ----------------------------------------------------------------------
        # Unified State Verification Breakpoint
        # ----------------------------------------------------------------------
        is_draft = docstatus == 0
        is_already_ordered = pr_status == "Ordered"

        if is_draft or is_already_ordered:
            if is_draft:
                err_msg = (
                    f"Transformation Blocked: The Material Request '{pr_id}' is currently in a 'Draft' state (docstatus: 0). "
                    "ERPNext backend mapping engines cannot convert unsubmitted resource documents."
                )
            else:
                err_msg = (
                    f"Transformation Blocked: The Material Request '{pr_id}' has already been converted to a Purchase Order. "
                    "ERPNext backend mapping engines cannot convert already processed resources."
                )

            logger.warning(f"MCP {action_name} Breakpoint Triggered: {err_msg}")
            
            return format_tool_response(
                success=False,
                action=action_name,
                error_details=err_msg
            )

        mapper_endpoint = "api/method/erpnext.stock.doctype.material_request.material_request.make_purchase_order"
        logger.info(f"Dispatching POST conversion map request to RPC endpoint for {pr_id}...")

        mapper_response = client.request("POST",  endpoint=mapper_endpoint, json = {"source_name" : pr_id})
        po_mapped_structure = mapper_response.get("message", {})

        if not po_mapped_structure:
            raise ValueError(f"ERPNext core mapping engine returned an empty data structure for {pr_id}.")
        
        save_point = "api/resource/Purchase Order"
        logger.info("Persisting unsaved mapped document matrix to database as an official Draft Purchase Order...")

        logger.info("Validating the material request payload to convert it into the PO")
        processed_items = [
                 {
                    "item_code" : items.get("item_code"),
                    "qty" : items.get("qty"),
                    "uom" : items.get("uom"),
                    "rate" : items.get("rate"),
                    "warehouse" : items.get("warehouse"),
                    "material_request" : pr_data.get("name"),
                    "material_request_item" : items.get("name")
                }
            ]

        po_payload = {
                "doctype": "Purchase Order",
                "naming_series": "PUR-ORD-.YYYY.-",
                "transaction_date": pr_data.get("transaction_date", {}),
                "schedule_date": pr_data.get("schedule_date", {}),
                "company": pr_data.get("company", {}),
                "supplier": supplier,
                "currency": currency,
                "buying_price_list": pr_data.get("buying_price_list", {}),
                "set_warehouse": pr_data.get("set_warehouse", {}),
                "items": processed_items
            }

        saved_po_data = client.request("POST", endpoint=save_point, json=po_payload)
        if not saved_po_data:
            raise ValueError(f"ERPNext core mapping engine returned an empty data structure for {pr_id}.")

        final_po_details = saved_po_data.get("data", {})
        generated_po_id = final_po_details.get("name", {})

        logger.info(f"POST conversion map request to RPC endpoint for {pr_id}... Completed")

        return format_tool_response(
            success=True,
            action=action_name,
            data={
                "message": f"Successfully mapped and generated Draft Purchase Order from {pr_id}.",
                "source_pr_id": pr_id,
                "generated_po_id": generated_po_id,
                "docstatus": 0,
                "doctype": "Purchase Order"
            }
        )

    except Exception as e:
        err_msg = f"ERPNext server failed to convert Material Request to the PO Draft: {str(e)}"
        logger.error(f"MCP {action_name} System Error: {err_msg}", exc_info=True)
        return format_tool_response(
            success=False,
            action=action_name,
            error_details=err_msg
        )

@mcp.tool()
def submit_purchase_order(purchase_order_id : str) :
    """
    Converts a submitted ERPNext draft Purchase order (PO) into a fresh final Purchase Order.
    Enforces strict pre-flight docstatus check gates to prevent engine process crashes.
    """
    try :
        action_name = "submit_purchase_order"
        po_id = purchase_order_id

        if not po_id:
            err_msg = "Validation Blocked: The argument parameter key 'purchase order id' is missing or null."
            return format_tool_response(success=False, action=action_name, error_details=err_msg)

        logger.info(f"MCP Tool Triggered: {action_name} | Target Source PR: {po_id}")
        logger.info(f"Executing safety pre-flight check on po_id: {po_id}")
        po_response = client.request("GET", f"api/resource/Purchase Order/{po_id}")
        po_response = po_response.get("data", {})

        if not po_response:
            raise ValueError(f"ERPNext core mapping engine returned an empty data structure for {po_id}.")

        if po_response.get("docstatus", {}) == 1 :
            err_msg = (
                f"Transformation Blocked: The Purchase Order '{po_id}' is Already Submitted (docstatus 1). "
                "ERPNext backend mapping engines cannot resubmit this resource document."
            )

            return format_tool_response(
                success=False,
                action=action_name,
                error_details=err_msg
            )

        logger.info(f"Executing Final API Call To Convert {po_id} from draft to Final PO")
        endpoint = f"api/resource/Purchase Order/{po_id}"
        po_response = client.request("PUT", endpoint=endpoint, json={"docstatus": 1})

        return format_tool_response(
            success=True,
            action=action_name,
            data={
                "message": f"Successfully Submitted Purchase Order {po_id}.",
                "source_po_id": po_id,
                "docstatus": 1,
                "doctype": "Purchase Order"
            }
        )
    
    except Exception as e:
        err_msg = f"ERPNext server failed to convert Submit Purchase Order: {str(e)}"
        logger.error(f"MCP {action_name} System Error: {err_msg}", exc_info=True)
        return format_tool_response(
            success=False,
            action=action_name,
            error_details=err_msg
        )
    
@mcp.tool() 
def cancel_purchase_order(purchase_order_id : str) :
    """
    Cancels an ERPNext Purchase Order (PO) only after strict pre-flight validation.
    Enforces docstatus and eligibility checks to prevent deletion of submitted or otherwise non-deletable POs and avoid engine process failures.
    """
    try :
        action_name = "cancel_purchase_order"
        po_id = purchase_order_id
        logger.info(f"MCP Tool Triggered: {action_name} | Target Source PR: {po_id}")

        if not po_id:
            err_msg = "Validation Blocked: The argument parameter key 'purchase order id' is missing or null."
            return format_tool_response(success=False, action=action_name, error_details=err_msg)
        
        logger.info(f"Executing safety pre-flight check on po_id: {po_id}")
        logger.info("Fetching the PO details for validation")
        po_response = client.request("GET", f"api/resource/Purchase Order/{po_id}")
        po_response = po_response.get("data", {})

        if not po_response:
            raise ValueError(f"ERPNext core mapping engine returned an empty data structure for {po_id}.")
        
        if po_response.get("docstatus", {}) == 2 :
            err_msg = (
                f"Transformation Blocked: The Purchase Order '{po_id}' is Already cancelled. "
                "ERPNext backend mapping engines cannot cancel this resource document."
            )
        
            return format_tool_response(
                success=False,
                action=action_name,
                error_details=err_msg
            )

        logger.info(f"Applying Final API Call To Cancel The Purchase Order with PO Id {po_id}")
        po_response = client.request("PUT", f"api/resource/Purchase Order/{po_id}", json={"docstatus" : 2})
        po_response = po_response.get("data", {})

        if not po_response:
            raise ValueError(f"ERPNext core mapping engine returned an empty data structure for while cancelling the po {po_id}.")

        return format_tool_response(
            success=True,
            action=action_name,
            data=f"Purchase Order Cancelled Successfully for PO ID {po_id}"
        )

    except Exception as e :
        err_msg = f"ERPNext server failed to cancel Purchase Order: {str(e)}"
        logger.error(f"MCP {action_name} System Error: {err_msg}", exc_info=True)
        return format_tool_response(
            success=False,
            action=action_name,
            error_details=err_msg
        )

@mcp.tool() 
def delete_purchase_order(purchase_order_id : str) :
    """
    Deletes an ERPNext Purchase Order (PO) only after strict pre-flight validation.
    Enforces docstatus and eligibility checks to prevent deletion of submitted or otherwise non-deletable POs and avoid engine process failures.
    """
    try :
        action_name = "delete_purchase_order"
        logger.info("Fetching the PO details for validation")

        po_id = purchase_order_id
        if not po_id:
            err_msg = "Validation Blocked: The argument parameter key 'purchase order id' is missing or null."
            return format_tool_response(success=False, action=action_name, error_details=err_msg)

        logger.info(f"MCP Tool Triggered: {action_name} | Target Source PR: {po_id}")
        logger.info(f"Executing safety pre-flight check on po_id: {po_id}")
        po_response = client.request("GET", f"api/resource/Purchase Order/{po_id}")
        po_response = po_response.get("data", {})

        if not po_response:
            raise ValueError(f"ERPNext core mapping engine returned an empty data structure for {po_id}.")
        
        if po_response.get("docstatus", {}) != 2 :
            err_msg = (
                f"Transformation Blocked: The Purchase Order '{po_id}' is In The Draft Mode First Please Cancel It. "
                "ERPNext backend mapping engines cannot delete this resource document."
            )
        
            return format_tool_response(
                success=False,
                action=action_name,
                error_details=err_msg
            )

        logger.info(f"Applying Final API Call - To Delete The PO - {po_id}")
        po_response = client.request("DELETE", f"api/resource/Purchase Order/{po_id}")
        po_response = po_response.get("data", {})

        if not po_response:
            raise ValueError(f"ERPNext core mapping engine returned an empty data structure for while deleting the po {po_id}.")

        return format_tool_response(
            success=True,
            action=action_name,
            data=f"Purchase Order Deleted Successfully for PO ID {po_id}",
        )

    except Exception as e :
        err_msg = f"ERPNext server failed to delete Purchase Order: {str(e)}"
        logger.error(f"MCP {action_name} System Error: {err_msg}", exc_info=True)
        return format_tool_response(
            success=False,
            action=action_name,
            error_details=err_msg
        )


@mcp.tool()
def get_material_request_details(material_request_id : str) :
    """
    Retrieves complete Purchase Requisition (PR) / Material Request details from ERPNext using the specified PR identifier.
    Performs pre-flight validation to ensure the requested PR exists and returns structured PR data, including request metadata and line items, for downstream agent processing and workflow decisions.
    """
    action_name = "purchase_request_details_retriever" 
    pr_id = material_request_id

    try :
        if not pr_id:
            err_msg = "Validation Blocked: The argument parameter key 'material/purchase request id' is missing or null."
            return format_tool_response(success=False, action=action_name, error_details=err_msg)

        logger.info(f"MCP Tool Triggered: {action_name} | Target Source PR: {pr_id}")
        pr_response = client.request("GET", f"api/resource/Material Request/{pr_id}")

        if not pr_response:
            raise ValueError(f"ERPNext core mapping engine returned an empty data structure for {pr_id}.")
        
        message = pr_response.get("data", {})

        response_to_return = {
                "name": message.get("name", ""),
                "title": message.get("title", ""),
                "material_request_type": message.get("material_request_type", ""),
                "company": message.get("company", ""),
                "docstatus": message.get("docstatus", 0),
                "status": message.get("status", ""),
                "transaction_date": message.get("transaction_date", ""),
                "schedule_date": message.get("schedule_date", ""),
                "buying_price_list": message.get("buying_price_list", ""),
                "set_warehouse": message.get("set_warehouse", ""),
                "items": [
                    {
                        "item_code": item.get("item_code", ""),
                        "item_name": item.get("item_name", ""),
                        "description": item.get("description", ""),
                        "qty": item.get("qty", 0),
                        "uom": item.get("uom", ""),
                        "schedule_date": item.get("schedule_date", ""),
                        "warehouse": item.get("warehouse", ""),
                        "rate": item.get("rate", 0),
                        "amount": item.get("amount", 0),
                        "expense_account": item.get("expense_account", ""),
                        "cost_center": item.get("cost_center", ""),
                        "ordered_qty": item.get("ordered_qty", 0),
                        "received_qty": item.get("received_qty", 0)
                    }
                    for item in message.get("items", [])
                ]
            }

        return format_tool_response(
            success=True,
            action=action_name,
            data = response_to_return
        )
        
    except Exception as e :
        err_msg = f"ERPNext server failed to retrieve material request details: {str(e)}"
        logger.error(f"MCP {action_name} System Error: {err_msg}", exc_info=True)
        return format_tool_response(
            success=False,
            action=action_name,
            error_details=err_msg
        )

@mcp.tool()
def get_purchase_order_details(purchase_order_id : str) :
    """
    Retrieves complete Purchase Order (PO) details from ERPNext using the specified PO identifier.
    Performs pre-flight validation to ensure the requested PO exists and returns structured PO data for downstream agent processing and workflow decisions.
    """
    action_name = "Purchase_order_details_retriever"
    po_id = purchase_order_id

    try : 
        if not po_id:
            err_msg = "Validation Blocked: The argument parameter key 'purchase order id' is missing or null."
            return format_tool_response(success=False, action=action_name, error_details=err_msg)

        logger.info(f"MCP Tool Triggered: {action_name} | Target Source PR: {po_id}")
        po_response = client.request("GET", f"api/resource/Purchase Order/{po_id}")

        if not po_response:
            raise ValueError(f"ERPNext core mapping engine returned an empty data structure for {po_id}.")

        message = po_response.get("data", {})
        items_data = message.get("items", [])

        response_to_return = {
            "name": message.get("name", ""),
            "docstatus": message.get("docstatus", 0),
            "status": message.get("status", ""),
            "supplier": message.get("supplier", ""),
            "supplier_name": message.get("supplier_name", ""),
            "transaction_date": message.get("transaction_date", ""),
            "schedule_date": message.get("schedule_date", ""),
            "company": message.get("company", ""),
            "currency": message.get("currency", ""),
            "buying_price_list": message.get("buying_price_list", ""),
            "set_warehouse": message.get("set_warehouse", ""),
            "total_qty": message.get("total_qty", 0),
            "total": message.get("total", 0),
            "grand_total": message.get("grand_total", 0),
            "per_billed": message.get("per_billed", 0),
            "per_received": message.get("per_received", 0),
            "items": [
                {
                    "item_code": item.get("item_code", ""),
                    "item_name": item.get("item_name", ""),
                    "description": item.get("description", ""),
                    "qty": item.get("qty", 0),
                    "uom": item.get("uom", ""),
                    "schedule_date": item.get("schedule_date", ""),
                    "warehouse": item.get("warehouse", ""),
                    "rate": item.get("rate", 0),
                    "amount": item.get("amount", 0),
                    "material_request": item.get("material_request", ""),
                    "material_request_item": item.get("material_request_item", ""),
                    "received_qty": item.get("received_qty", 0),
                    "returned_qty": item.get("returned_qty", 0),
                    "billed_amt": item.get("billed_amt", 0),
                    "expense_account": item.get("expense_account", ""),
                    "cost_center": item.get("cost_center", "")
                }
                for item in items_data
            ]
        }

        return format_tool_response(
            success=True,
            action=action_name,
            data=response_to_return
        )

    except Exception as e :
        err_msg = f"ERPNext server failed to retrieve Purchase Order Details: {str(e)}"
        logger.error(f"MCP {action_name} System Error: {err_msg}", exc_info=True)
        return format_tool_response(
            success=False,
            action=action_name,
            error_details=err_msg
        )

if __name__ == "__main__":
    print("🚀 Starting ERPNext FastMCP Server via Streamable-HTTP...")
    mcp.run(
        transport="streamable-http",
        mount_path="/mcp",
    )

