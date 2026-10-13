import os
import json

# Set PYTHONPATH programmatically
import sys
sys.path.append(".")

# Import schemas and server function directly
from src.erpnext_client.pyload_schemas import CreateMaterialRequestInput, MaterialRequestDocSchema, MaterialRequestItemSchema
from src.mcp_server.server import generate_material_request, submit_material_request, submit_purchase_order

def submit_po_():
    data = {
        "purchase_order_id" : "PUR-PO-00001"
    }

    submit_res = submit_purchase_order(ctx=data)

    print(submit_res)

if __name__ == "__main__":
    submit_po_()