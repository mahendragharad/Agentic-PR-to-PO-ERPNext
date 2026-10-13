import os
import sys
import time
from config.settings import settings
from config.logging_config import logger
from src.auth.erpnext_auth import ERPNextBearerAuth
from src.erpnext_client.base_client import ERPNextBaseClient
from src.auth.token_manager import ERPNextAuthorizationCodeManager


def run_integration_wiring_test():
    logger.info("=============================logger.info================")
    logger.info("🚀 STARTING ERPNEXT AUTH MODULE WIRING TEST")
    logger.info("==================================================")

    # 1. Component Verification: Load Pydantic Config settings
    logger.info(f"[1] Environment settings initialized successfully.")
    logger.info(f"    - Target Server: {settings.erpnext_base_url}")
    logger.info(f"    - Cache Target:  {settings.token_url}")
    logger.info(f"    - Absoulute token target Target:  {settings.absolute_token_path}")


    # 2. Component Verification: Instantiate the Token Manager
    logger.info("\n[2] Wiring up the Token Manager Engine...")
    token_manager = ERPNextAuthorizationCodeManager(
        token_url=settings.token_url,
        client_id=settings.erpnext_client_id,
        client_secret=settings.erpnext_client_secret,
        cache_file=settings.absolute_token_path,
        scope=settings.erpnext_scope
    )

    logger.info("[3] generating the token")
    token = token_manager._get_valid_token()
    logger.info(f"[4] Token Generated Successfully {token}")

    # 3. Component Verification: Wire the Manager into the HTTP Base Client
    logger.info("[3] Wiring Token Manager into the ERPNext Base Client...")
    client = ERPNextBaseClient(
        base_url=str(settings.erpnext_base_url), 
        token_manager=token_manager
    )

    payload =  {
            "doc": {
                "doctype": "Material Request",
                "material_request_type": "Purchase",
                "transaction_date": "2026-09-10",
                "schedule_date": "2026-09-25",
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
                    "schedule_date": "2026-09-25",
                    "warehouse": "All Warehouses - MF",
                    "rate": 2500.00
                }
                ]
            }
        }

    # 4. Component Verification: Execute Live Connection and Exception Catching Loop
    logger.info("\n[4] Triggering Live Integrated Auth Verification Round...")
    try:
        # We test by forcing a standard read request to check permissions
        # This triggers: Client -> Interceptor -> Token Manager Cache Check -> Network Sync
        logger.info("    -> Sending request to read active Material Requests...")
        # response_data = client.request("GET", "api/resource/Purchase Order?limit_page_length=5")

        response_data = client.request("POST", "api/method/frappe.client.insert", json=payload)
        
        logger.info("\n==================================================")
        logger.info("🎉 SUCCESS: All components are wired together perfectly!")
        logger.info("==================================================")
        logger.info(f"Server Sample Response: {response_data}")
        
    except Exception as e:
        logger.error("\n[❌] WIRING BREAKAGE DETECTED", exc_info=True)


if __name__ == "__main__":
    print("🔥 containers.py execution started")
    run_integration_wiring_test()

