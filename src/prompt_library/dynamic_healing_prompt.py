def generate_dynamic_healing_prompt(error_context: str) -> str:
    """
    Production-grade Prompt Factory. 
    Classifies error type strings and dynamically generates contextual recovery tracks.
    """
    # Base structural framing
    header = (
        "⚠️ CRITICAL SYSTEM NOTICE [SELF-HEALING FEEDBACK LOOP]:\n"
        "Your immediate prior tool call execution failed. You must repair this transaction.\n"
        "----------------------------------------\n"
        f"RAW ERROR LOG: {error_context}\n"
        "----------------------------------------\n"
    )
    
    # Category 1: Local Pydantic Parameter / Type Mismatches
    if "ValidationError" in error_context or "Validation Fail" in error_context:
        instruction = (
            "DIAGNOSIS: Parameter Schema Mismatch / Validation Error.\n"
            "INSTRUCTIONS FOR RECOVERY:\n"
            "1. Review your generated argument keys and data types against the required tool schema.\n"
            "2. Pay strict attention to date formats (must be YYYY-MM-DD and strictly in the future) "
            "and numerical types (floats/integers, do not pass text like '50k').\n"
            "3. Correct the values, re-nest arrays inside 'items' properly, and emit a fixed payload."
        )
        
    # Category 2: ERPNext Server-Side Missing Master Data (e.g., Missing Supplier, Warehouse, or Item Code)
    elif any(key in error_context for key in ["Not Found", "404", "DoesNotExist", "Missing"]):
        instruction = (
            "DIAGNOSIS: Database Master Data Entity Referential Integrity Error.\n"
            "INSTRUCTIONS FOR RECOVERY:\n"
            "1. The ERPNext database rejected your argument because the specified Entity (Item Code, Supplier Name, or Warehouse) does not exist in the master ledger.\n"
            "2. Check if you made a typo or spelling mistake in the item name, supplier name, or warehouse naming conventions.\n"
            "3. If the user query implies a specific name, use the closest logical standard string or ask the user for clarification. Do not make up a non-existent name."
        )

    # Category 3: System Business Logic / State Conflicts (e.g., Submitting an already cancelled document)
    elif any(key in error_context for key in ["Conflict", "409", "Invalid Status", "Submitted"]):
        instruction = (
            "DIAGNOSIS: Document Workflow State Conflict.\n"
            "INSTRUCTIONS FOR RECOVERY:\n"
            "1. The document is in an invalid state for the requested operation (e.g., trying to submit a document that is already submitted or cancelled).\n"
            "2. Do not retry the exact same action. Verify the workflow sequence.\n"
            "3. If necessary, first call a getter tool (like 'get_material_request_details') to check the document state, or explain the workflow conflict to the user conversationally."
        )

    # Category 4: Infrastructure / Network Transport Crashes (e.g., Connection timeouts)
    else:
        instruction = (
            "DIAGNOSIS: Low-Level Network Transport / Infrastructure Interruption.\n"
            "INSTRUCTIONS FOR RECOVERY:\n"
            "1. The transaction failed due to a transient infrastructure connection issue, not your code formatting.\n"
            "2. You may attempt to re-call the exact same tool payload one more time to see if the network has recovered."
        )

    return f"{header}\n{instruction}"
