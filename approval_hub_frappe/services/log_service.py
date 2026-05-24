"""Approval Hub action logging."""

from __future__ import annotations

import frappe
from frappe.utils import cstr, now_datetime


def create_approval_hub_log(
    doc,
    config: dict,
    action: str,
    from_state: str,
    to_state: str,
    remarks: str | None = None,
) -> str | None:
    if not config.get("track_history"):
        return None

    doctype = doc.doctype
    docname = doc.name
    actor = frappe.session.user

    existing = frappe.db.get_value(
        "Approval Hub Log",
        {
            "reference_doctype": doctype,
            "reference_name": docname,
            "action": cstr(action),
            "from_state": cstr(from_state),
            "to_state": cstr(to_state),
            "acted_by": actor,
        },
        "name",
    )
    if existing:
        return existing

    branch = _resolve_field(doc, config.get("branch_field"))
    requester = _resolve_field(doc, config.get("requester_field"))
    amount = _resolve_field(doc, config.get("amount_field"))

    try:
        log = frappe.get_doc(
            {
                "doctype": "Approval Hub Log",
                "reference_doctype": doctype,
                "reference_name": cstr(docname),
                "from_state": cstr(from_state),
                "to_state": cstr(to_state),
                "action": cstr(action),
                "acted_by": actor,
                "acted_on": now_datetime(),
                "branch": cstr(branch) if branch else None,
                "requester": cstr(requester) if requester else None,
                "amount": amount,
                "remarks": cstr(remarks) if remarks else None,
            }
        )
        log.insert(ignore_permissions=True)
        return log.name
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Approval Hub - Log creation failed")
        return None


def get_logs_for_document(doctype: str, docname: str, limit: int = 50) -> list[dict]:
    return frappe.get_all(
        "Approval Hub Log",
        filters={"reference_doctype": doctype, "reference_name": docname},
        fields=[
            "name",
            "action",
            "from_state",
            "to_state",
            "acted_by",
            "acted_on",
            "branch",
            "requester",
            "amount",
            "remarks",
        ],
        order_by="acted_on desc",
        limit_page_length=limit,
        ignore_permissions=True,
    )


def _resolve_field(doc, field_name: str | None):
    if not field_name:
        return None
    try:
        return getattr(doc, field_name, None) or doc.get(field_name)
    except Exception:
        return None
