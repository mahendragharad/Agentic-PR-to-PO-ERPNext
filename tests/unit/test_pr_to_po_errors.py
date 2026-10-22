import json
import unittest

from src.agents.tool_executer import _normalize_pr_to_po_error


class TestPurchaseOrderConversionErrors(unittest.TestCase):
    def test_extracts_and_articulates_missing_supplier_error(self):
        content = json.dumps(
            {
                "status": "ERROR",
                "action": "convert_pr_to_draft_po",
                "payload": None,
                "error": {
                    "message": (
                        "ERPNext server failed to convert Material Request to the PO Draft: "
                        'ERPNext API returned unexpected error 417: '
                        '{"exception":"frappe.exceptions.LinkValidationError: '
                        'Could not find Supplier: Maahi","exc":"traceback"}'
                    ),
                    "suggestion": "Check missing parameters.",
                },
            }
        )

        result = json.loads(_normalize_pr_to_po_error(content))

        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["action"], "convert_pr_to_draft_po")
        self.assertEqual(
            result["error"]["message"],
            "Supplier 'Maahi' was not found in ERPNext. "
            "Check the supplier name and try again.",
        )
        self.assertEqual(result["error"]["suggestion"], "Check missing parameters.")

    def test_does_not_change_successful_conversion_response(self):
        content = json.dumps(
            {
                "status": "SUCCESS",
                "action": "convert_pr_to_draft_po",
                "payload": {"generated_po_id": "PO-001"},
            }
        )

        self.assertEqual(_normalize_pr_to_po_error(content), content)

    def test_does_not_change_non_json_tool_response(self):
        content = "unexpected MCP response"

        self.assertEqual(_normalize_pr_to_po_error(content), content)


if __name__ == "__main__":
    unittest.main()
