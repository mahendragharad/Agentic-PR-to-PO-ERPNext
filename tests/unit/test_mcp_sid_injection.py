import unittest

from langchain_core.messages import AIMessage

from src.agents.tool_executer import (
    _authenticated_execution_state,
    _remove_untrusted_session_args,
)


class TestMCPSessionInjection(unittest.TestCase):
    def test_authenticated_sid_is_injected_without_storing_it_in_history(self):
        message = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "generate_material_request",
                    "args": {
                        "doc": {"title": "unvalidated"},
                        "erpnext_sid": "untrusted-sid",
                    },
                    "id": "create-call",
                    "type": "tool_call",
                },
                {
                    "name": "delete_purchase_order",
                    "args": {
                        "purchase_order_id": "PO-1",
                        "erpnext_sid": "untrusted-sid",
                    },
                    "id": "delete-call",
                    "type": "tool_call",
                },
            ],
        )
        _remove_untrusted_session_args(message.tool_calls)
        state = {"messages": [message]}

        execution_state = _authenticated_execution_state(
            state=state,
            messages=[message],
            last_message=message,
            tool_call_id="create-call",
            normalized_args={"doc": {"title": "validated"}},
            erpnext_sid="authenticated-sid",
        )

        self.assertNotIn("erpnext_sid", message.tool_calls[0]["args"])
        self.assertNotIn("erpnext_sid", message.tool_calls[1]["args"])
        self.assertEqual(
            execution_state["messages"][-1].tool_calls[0]["args"],
            {
                "doc": {"title": "validated"},
                "erpnext_sid": "authenticated-sid",
            },
        )
        self.assertEqual(
            execution_state["messages"][-1].tool_calls[1]["args"]["erpnext_sid"],
            "authenticated-sid",
        )
