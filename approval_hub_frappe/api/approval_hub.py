"""
approval_hub_frappe/api/approval_hub.py

Public API methods exposed to the Approval Hub page and external callers.
All whitelisted methods enforce session user and permission checks.
"""

import frappe
from frappe import _
from approval_hub_frappe.services.pending_engine import PendingApprovalEngine
from approval_hub_frappe.services.workflow_service import apply_workflow_action
from approval_hub_frappe.services.log_service import create_approval_hub_log
from approval_hub_frappe.utils.permission_utils import (
    get_current_user_roles,
    get_user_allowed_branches,
    can_user_approve_document,
    has_document_access,
)
from approval_hub_frappe.utils.settings_utils import get_approval_hub_settings
from approval_hub_frappe.utils.config_utils import get_active_doctype_configs


# ---------------------------------------------------------------------------
# Settings & Config
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_settings():
    """Return Approval Hub Settings for the current session."""
    return get_approval_hub_settings()


@frappe.whitelist()
def get_doctype_configs():
    """Return all active doctype configs ordered by sequence."""
    return get_active_doctype_configs()


# ---------------------------------------------------------------------------
# Pending approvals
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_pending_approvals(filters=None, page=1, page_size=None):
    """
    Return paginated list of documents pending approval for the current user.

    :param filters: dict – optional extra filters {doctype, branch, workflow_state,
                    date_from, date_to}
    :param page:    int  – 1-based page number
    :param page_size: int – override default page size from settings
    :returns: {items: [...], total: int, page: int, page_size: int}
    """
    if isinstance(filters, str):
        import json
        filters = json.loads(filters) if filters else {}

    filters = filters or {}
    page = int(page or 1)

    settings = get_approval_hub_settings()

    if not settings.get("enabled"):
        frappe.throw(_("Approval Hub is currently disabled."), frappe.ValidationError)

    if not page_size:
        page_size = settings.get("default_page_size") or 20
    page_size = int(page_size)

    engine = PendingApprovalEngine(
        user=frappe.session.user,
        settings=settings,
        filters=filters,
    )
    result = engine.get_pending(page=page, page_size=page_size)
    return result


# ---------------------------------------------------------------------------
# Summary / dashboard
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_approval_summary(filters=None):
    """
    Return summary counts for the dashboard cards:
      - my_pending
      - overdue
      - approved_today
      - rejected_today
    """
    if isinstance(filters, str):
        import json
        filters = json.loads(filters) if filters else {}

    filters = filters or {}

    settings = get_approval_hub_settings()
    if not settings.get("enabled"):
        return {"my_pending": 0, "overdue": 0, "approved_today": 0, "rejected_today": 0}

    engine = PendingApprovalEngine(
        user=frappe.session.user,
        settings=settings,
        filters=filters,
    )
    return engine.get_summary()


# ---------------------------------------------------------------------------
# Branches
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_branches(user=None):
    """Return branches the current (or given) user is allowed to act on."""
    user = user or frappe.session.user
    # Only System Manager can query for another user
    if user != frappe.session.user and "System Manager" not in get_current_user_roles():
        frappe.throw(_("Not permitted."), frappe.PermissionError)
    return get_user_allowed_branches(user)


# ---------------------------------------------------------------------------
# Document eligibility check
# ---------------------------------------------------------------------------

@frappe.whitelist()
def check_can_approve(doctype, docname, user=None):
    """Return whether the current user can approve a specific document."""
    user = user or frappe.session.user
    if user != frappe.session.user and "System Manager" not in get_current_user_roles():
        frappe.throw(_("Not permitted."), frappe.PermissionError)
    return can_user_approve_document(doctype, docname, user)


# ---------------------------------------------------------------------------
# Workflow action
# ---------------------------------------------------------------------------

@frappe.whitelist()
def apply_workflow_action_from_hub(doctype, docname, action, remarks=None):
    """
    Apply a workflow action on a document from the Approval Hub page.

    :param doctype:  str
    :param docname:  str
    :param action:   str – e.g. "Approve", "Reject", "Send Back"
    :param remarks:  str – optional remarks stored in the log
    :returns: {"success": True, "new_state": "...", "message": "..."}
    """
    frappe.has_permission(doctype, "write", docname, throw=True)

    settings = get_approval_hub_settings()
    if not settings.get("enabled"):
        frappe.throw(_("Approval Hub is currently disabled."))

    result = apply_workflow_action(
        doctype=doctype,
        docname=docname,
        action=action,
        user=frappe.session.user,
        remarks=remarks,
        settings=settings,
    )
    return result