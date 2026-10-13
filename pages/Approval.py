import json

import httpx
import streamlit as st

RESUME_URL = "http://127.0.0.1:8001/api/v1/chat/resume"

st.set_page_config(
    page_title="Purchase Order Approval",
    page_icon="🔒",
    layout="wide",
)

ss = st.session_state
ss.setdefault("approval_pending", False)
ss.setdefault("approval_payload", None)
ss.setdefault("approval_error", None)
ss.setdefault("messages", [])
ss.setdefault("health", "ready")
ss.setdefault("thread_id", None)

ACTION_LABELS = {
    "convert_pr_to_draft_po": "Create draft purchase order",
    "submit_purchase_order": "Submit purchase order",
}


def append_assistant_message(content: str) -> None:
    ss.messages.append({"role": "assistant", "content": content})


def describe_action_result(action_result) -> str:
    if not isinstance(action_result, dict):
        return ""

    payload = action_result.get("payload")
    if not isinstance(payload, dict):
        payload = {}

    details = []
    message = payload.get("message")
    po_id = payload.get("generated_po_id") or payload.get("source_po_id")
    if message:
        details.append(str(message))
    if po_id and str(po_id) not in str(message):
        details.append(f"Purchase Order ID: {po_id}")

    if not details:
        return ""
    return " " + " ".join(details)


def submit_decision(decision: str) -> None:
    current_payload = ss.approval_payload or {}
    action_name = current_payload.get("tool_name")
    action_label = ACTION_LABELS.get(action_name, action_name or "requested action")

    try:
        response = httpx.post(
            RESUME_URL,
            json={"thread_id": ss.thread_id, "decision": decision},
            timeout=30.0,
        )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError("The backend returned an invalid approval response.")

        status = result.get("status")
        if status == "approval_required":
            next_payload = result.get("approval_payload")
            if not isinstance(next_payload, dict):
                raise ValueError(
                    "The backend requested another approval but did not provide its payload."
                )

            if decision == "approved":
                summary = describe_action_result(result.get("action_result"))
                append_assistant_message(
                    f"Approved: {action_label}.{summary} "
                    "Another approval is required before the next purchase-order action."
                )
            ss.approval_pending = True
            ss.approval_payload = next_payload
            ss.approval_error = None
            ss.health = "pending_approval"
            st.rerun()

        elif status == "completed":
            summary = describe_action_result(result.get("action_result"))
            po_id = result.get("po_id")
            if po_id and str(po_id) not in summary:
                summary += f" Purchase Order ID: {po_id}."
            append_assistant_message(
                f"Approved: {action_label} completed.{summary}"
            )
            ss.approval_pending = False
            ss.approval_payload = None
            ss.approval_error = None
            ss.health = "ready"
            st.switch_page("streamlit_app.py")

        elif status == "rejected":
            po_id = result.get("po_id")
            detail = ""
            if action_name == "submit_purchase_order" and po_id:
                detail = f" The draft Purchase Order {po_id} remains unsubmitted."
            append_assistant_message(
                f"Rejected: {action_label} was not performed.{detail}"
            )
            ss.approval_pending = False
            ss.approval_payload = None
            ss.approval_error = None
            ss.health = "ready"
            st.switch_page("streamlit_app.py")

        else:
            raise ValueError(f"Unexpected backend approval status: {status!r}.")

    except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
        ss.approval_pending = True
        ss.approval_error = f"Could not process this approval: {exc}"
        ss.health = "err"
        st.rerun()


st.title("Purchase Order Approval")

for message in ss.messages[-6:]:
    with st.chat_message(message.get("role", "assistant")):
        st.markdown(message.get("content", ""))

if not ss.approval_pending or not isinstance(ss.approval_payload, dict):
    st.info("There is no purchase-order approval waiting for a decision.")
    st.page_link("streamlit_app.py", label="Return to chat", icon="💬")
    st.stop()

approval_payload = ss.approval_payload
tool_name = approval_payload.get("tool_name")
action_label = ACTION_LABELS.get(tool_name, tool_name or "Requested operation")
st.subheader(f"Approval required: {action_label}")
st.caption("Review the requested action before approving or rejecting it.")
st.json(approval_payload)

if ss.approval_error:
    st.error(ss.approval_error)

approve_col, reject_col = st.columns(2)
if approve_col.button("Approve", type="primary"):
    with st.spinner("Applying approval and continuing the workflow..."):
        submit_decision("approved")

if reject_col.button("Reject"):
    with st.spinner("Recording rejection..."):
        submit_decision("rejected")
