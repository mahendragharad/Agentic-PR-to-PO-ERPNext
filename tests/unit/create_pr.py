import os
import json

# Set PYTHONPATH programmatically
import sys
sys.path.append(".")

# Import schemas and server function directly
from src.erpnext_client.pyload_schemas import MaterialRequestDocSchema, MaterialRequestItemSchema
from src.mcp_server.server import generate_material_request, submit_material_request
from config.logging_config import logger
from src.mcp_server.server import client, format_tool_response
from typing import Dict, Any

def test_pr_create_and_submit_workflow():

    raw_payload = {
        "doc": {
            "doctype": "Material Request",
            "material_request_type": "Purchase",
            "transaction_date": "2026-12-10",
            "schedule_date": "2026-12-25",
            "company": "Maahi's Foudation",
            "department": "Management",
            "set_warehouse": "All Warehouses - MF",
            "title": "Quarterly IT & Hardware Procurement",
            "remark": "Urgent requisition for upcoming engineering team onboarding.",
            "items": [
            {
                "item_code": "ITEM-001",
                "item_name": "Test Item",
                "description": "High-performance workstation component with extended 3-year hardware warranty.",
                "qty": 15,
                "uom": "Nos",
                "schedule_date": "2026-12-25",
                "warehouse": "All Warehouses - MF",
                "rate": 2500.00
            }
            ]
        }
    }

    new_payload = {'doc': {'doctype': 'Material Request', 'material_request_type': 'Purchase', 'transaction_date': '2026-12-10', 'schedule_date': '2026-12-30', 'company': "Maahi's Foudation", 'department': 'Management', 'set_warehouse': 'All Warehouses - MF', 'title': 'Quarterly IT Procurement', 'remark': 'Direct script integration test', 'items': [{'item_code': 'ITEM-001', 'qty': 15.0, 'uom': 'Nos', 'schedule_date': '2026-12-30', 'warehouse': 'All Warehouses - MF', 'rate': 2500.0}]}}

    
    print("\n--- 2. Invoking MCP Tool ---")
    print("\n--- 2. Creating the purchase request ---")
    response_json = generate_material_request(doc=raw_payload)
    print(response_json)
    create_res = json.loads(response_json)
    
if __name__ == "__main__":
    test_pr_create_and_submit_workflow()