import os
import json

# Set PYTHONPATH programmatically
import sys
sys.path.append(".")

# Import schemas and server function directly
from src.erpnext_client.pyload_schemas import CreateMaterialRequestInput, MaterialRequestDocSchema, MaterialRequestItemSchema, ConvertPRToPOInput
from src.mcp_server.server import generate_material_request, submit_material_request, convert_pr_to_draft_po

def submit_pr_to_po_as_draft() :

    # raw_payload_no_id = {
    #     "material_request_id": "MAT-MR-2026-00035",
    #     "naming_series": "PUR-ORD-.YYYY.-",
    #     "transaction_date": "2026-09-15",
    #     "schedule_date": "2026-09-25",
    #     "company": "Maahi's Foudation",
    #     "supplier": "Test Supplier API", 
    #     "currency": "INR",
    #     "buying_price_list": "Standard Buying",
    #     "set_warehouse": "All Warehouses - MF",
    #     "items": [
    #         {
    #             "item_code": "ITEM-001",
    #             "qty": 15,
    #             "uom": "Nos",
    #             "rate": 100,
    #             "warehouse": "All Warehouses - MF",
    #             "material_request": "MAT-MR-2026-00035",
    #             "material_request_item": "i1hhegsdkm"
    #         }
    #     ]
    # }

    

    raw_payload_no_id = {
        "currency": "INR",
        "material_request_id": "MAT-MR-2026-00036",
        "supplier": "Test Supplier API"
    }

    po_details = {
    "ctx": {
        "doc": {
        "currency": "INR",
        "supplier": "Test Supplier API",
        "material_request_id": "MAT-MR-2026-00036"
        }
    }
    }

    currency = "INR"
    material_request_id = "MAT-MR-2026-00036"
    supplier = "Test Supplier API"

    response = convert_pr_to_draft_po(material_request_id, supplier, currency)
    print(response)

if __name__ == "__main__":
    submit_pr_to_po_as_draft()