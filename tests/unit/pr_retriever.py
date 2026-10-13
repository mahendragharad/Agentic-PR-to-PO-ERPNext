import os
import json

# Set PYTHONPATH programmatically
import sys
sys.path.append(".")

# Import schemas and server function directly
from src.erpnext_client.pyload_schemas import CreateMaterialRequestInput, MaterialRequestDocSchema, MaterialRequestItemSchema
from src.mcp_server.server import generate_material_request, submit_material_request, submit_purchase_order, get_purchase_order_details, get_material_request_details

def submit_po_():
    payload = {
        "material_request_id" : "MAT-MR-2026-00036"
    }
    submit_res = get_material_request_details(ctx=payload)

    print(submit_res)

if __name__ == "__main__":
    submit_po_()