import json
import os
import httpx
import streamlit as st
from config.settings import settings
from dotenv import load_dotenv

load_dotenv()

BASE_API_URL = st.secrets.get("BASE_API_URL") or os.getenv("BASE_API_URL")
if not BASE_API_URL:
    raise RuntimeError("Configure BASE_API_URL in Streamlit secrets or the environment.")

BASE_API_URL = str(BASE_API_URL).rstrip("/")
RESUME_URL = f"{BASE_API_URL}/api/v1/chat/resume"
AUTH_COOKIE_NAME = "erpnext_auth_token"

st.set_page_config(
    page_title="Purchase Order Approval",
    page_icon="🔒",
    layout="wide",
)

ss = st.session_state
ss.setdefault("erpnext_auth_cookie", None)
ss.setdefault("approval_pending", False)
ss.setdefault("approval_payload", None)
ss.setdefault("approval_error", None)
ss.setdefault("messages", [])
ss.setdefault("health", "ready")
ss.setdefault("thread_id", None)
ss.setdefault("user_id", None)

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
    decision_payload = {
        "thread_id": ss.thread_id,
        "approval_id": current_payload.get("approval_id"),
        "preview_hash": current_payload.get("preview_hash"),
        "decision": decision,
    }

    try:
        response = httpx.post(
            RESUME_URL,
            json=decision_payload,
            headers={
                "Cookie": f"{AUTH_COOKIE_NAME}={ss.erpnext_auth_cookie}"
            },
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
            st.switch_page("app.py")

        elif status == "rejected":
            po_id = result.get("po_id") or result.get("document_id")
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
            st.switch_page("app.py")

        elif status == "stale_review":
            append_assistant_message(
                f"Review expired: {result.get('message', 'The document changed. Please request a new review.')}"
            )
            ss.approval_pending = False
            ss.approval_payload = None
            ss.approval_error = None
            ss.health = "ready"
            st.switch_page("app.py")

        elif status == "failed":
            action_result = result.get("action_result")
            detail = ""
            if isinstance(action_result, dict):
                error = action_result.get("error")
                if isinstance(error, dict):
                    detail = str(error.get("message") or "")
            detail = detail or str(result.get("message") or "The approved action failed.")
            append_assistant_message(f"{action_label} failed: {detail}")
            ss.approval_pending = False
            ss.approval_payload = None
            ss.approval_error = None
            ss.health = "err"
            st.switch_page("app.py")

        else:
            raise ValueError(f"Unexpected backend approval status: {status!r}.")

    except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
        ss.approval_pending = True
        ss.approval_error = f"Could not process this approval: {exc}"
        ss.health = "err"
        st.rerun()


st.title("Purchase Order Approval")

if not ss.erpnext_auth_cookie:
    st.warning("Your ERPNext session is missing. Return to chat and log in again.")
    st.page_link("streamlit_app.py", label="Return to chat", icon="💬")
    st.stop()

for message in ss.messages[-6:]:
    with st.chat_message(message.get("role", "assistant")):
        st.markdown(message.get("content", ""))

if not ss.approval_pending or not isinstance(ss.approval_payload, dict):
    st.info("There is no purchase-order approval waiting for a decision.")
    st.page_link("streamlit_app.py", label="Return to chat", icon="💬")
    st.stop()

approval_payload = ss.approval_payload
tool_name = approval_payload.get("tool_name")
if tool_name not in ACTION_LABELS:
    st.error("The backend provided an unsupported approval action.")
    st.stop()
action_label = ACTION_LABELS.get(tool_name, tool_name or "Requested operation")
st.subheader(f"Approval required: {action_label}")
st.caption("Review the ERPNext document below. Your decision applies only to this displayed version.")

preview = approval_payload.get("preview")
if not isinstance(preview, dict) or not isinstance(preview.get("document"), dict):
    st.error("The backend approval payload is missing its document preview.")
    st.stop()

document = preview["document"]
conversion = preview.get("conversion", {})
st.markdown(f"**{approval_payload.get('document_type', 'Document')}: {document.get('name', '')}**")
if document.get("title"):
    st.markdown(f"#### {document['title']}")
if document.get("remark"):
    st.caption(f"Justification: {document['remark']}")

if tool_name == "convert_pr_to_draft_po":
    st.warning("Approving this step creates a draft purchase order. It does not submit the PO.")
    supplier_col, currency_col = st.columns(2)
    supplier_col.metric("Supplier to use", conversion.get("supplier") or "Not provided")
    currency_col.metric("Currency", conversion.get("currency") or "INR")
else:
    st.warning("Approving this step submits this draft purchase order to ERPNext.")

left, middle, right = st.columns(3)
left.metric("Company", document.get("company") or "—")
middle.metric("Status", document.get("status") or f"docstatus {document.get('docstatus', '—')}")
right.metric("Transaction date", document.get("transaction_date") or "—")
if document.get("department") or document.get("material_request_type"):
    department_col, request_type_col = st.columns(2)
    department_col.metric("Department", document.get("department") or "—")
    request_type_col.metric("Request type", document.get("material_request_type") or "—")

date_col, warehouse_col = st.columns(2)
date_col.metric("Required date", document.get("schedule_date") or "—")
warehouse_col.metric("Warehouse", document.get("set_warehouse") or "—")

if document.get("supplier") or document.get("supplier_name"):
    st.metric("Supplier", document.get("supplier_name") or document.get("supplier"))
if document.get("currency"):
    st.metric("Currency", document.get("currency"))

items = document.get("items") or []
st.markdown("#### Items")
item_columns = [
    key for key in (
        "item_code", "item_name", "description", "qty", "uom",
        "rate", "amount", "schedule_date", "warehouse",
    )
    if any(item.get(key) not in (None, "") for item in items)
]
st.dataframe(
    [{key: item.get(key) for key in item_columns} for item in items],
    hide_index=True,
    use_container_width=True,
)

if tool_name == "submit_purchase_order":
    total_col, grand_total_col, qty_col = st.columns(3)
    total_col.metric("Total", document.get("total", "—"))
    grand_total_col.metric("Grand total", document.get("grand_total", "—"))
    qty_col.metric("Total quantity", document.get("total_qty", "—"))
    if document.get("taxes"):
        st.markdown("#### Taxes and charges")
        st.dataframe(document["taxes"], hide_index=True, use_container_width=True)

if ss.approval_error:
    st.error(ss.approval_error)

approve_col, reject_col = st.columns(2)
approve_label = (
    "Approve & create draft"
    if tool_name == "convert_pr_to_draft_po"
    else "Approve & submit PO"
)
if approve_col.button(approve_label, type="primary"):
    with st.spinner("Applying approval and continuing the workflow..."):
        submit_decision("approved")

if reject_col.button("Reject"):
    with st.spinner("Recording rejection..."):
        submit_decision("rejected")
