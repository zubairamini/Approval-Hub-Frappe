"""
approval_hub_frappe/services/log_service.py

Logging service for Approval Hub workflow actions.
Creates Approval Hub Log entries when track_history = 1 on config.
"""

import frappe
from frappe.utils import now_datetime, cstr


def create_approval_hub_log(
    doc,
    config: dict,
    action: str,
    from_state: str,
    to_state: str,
    remarks: str = None,
) -> str | None:
    """
    Create an Approval Hub Log record for a workflow action.

    :param doc:        The Frappe document object (already saved/acted upon)
    :param config:     The Approval Hub Doctype Config dict for this doctype
    :param action:     The workflow action string (e.g. "Approve")
    :param from_state: State before the action
    :param to_state:   State after the action
    :param remarks:    Optional remarks from the acting user
    :returns:          Name of the created log, or None if skipped
    """
    if not config.get("track_history"):
        return None

    doctype = doc.doctype
    docname = doc.name

    # Resolve field-mapped values from config
    branch = _resolve_field(doc, config.get("branch_field"))
    requester = _resolve_field(doc, config.get("requester_field"))
    amount = _resolve_field(doc, config.get("amount_field"))

    try:
        log = frappe.get_doc({
            "doctype": "Approval Hub Log",
            "reference_doctype": doctype,
            "reference_name": cstr(docname),
            "from_state": cstr(from_state),
            "to_state": cstr(to_state),
            "action": cstr(action),
            "acted_by": frappe.session.user,
            "acted_on": now_datetime(),
            "branch": cstr(branch) if branch else None,
            "requester": cstr(requester) if requester else None,
            "amount": amount,
            "remarks": cstr(remarks) if remarks else None,
        })
        log.insert(ignore_permissions=True)
        frappe.db.commit()
        return log.name
    except Exception:
        # Log creation failure should never break the workflow action
        frappe.log_error(frappe.get_traceback(), "Approval Hub - Log creation failed")
        return None


def get_logs_for_document(
    doctype: str,
    docname: str,
    limit: int = 50,
) -> list[dict]:
    """Retrieve approval log history for a specific document."""
    return frappe.get_all(
        "Approval Hub Log",
        filters={"reference_doctype": doctype, "reference_name": docname},
        fields=[
            "name", "action", "from_state", "to_state",
            "acted_by", "acted_on", "branch", "requester", "amount", "remarks",
        ],
        order_by="acted_on desc",
        limit=limit,
        ignore_permissions=True,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_field(doc, field_name: str):
    """Safely read a field value from a document object."""
    if not field_name:
        return None
    try:
        return getattr(doc, field_name, None) or doc.get(field_name)
    except Exception:
        return None