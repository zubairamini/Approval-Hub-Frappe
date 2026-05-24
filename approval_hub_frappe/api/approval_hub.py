"""Approval Hub API endpoints."""

from __future__ import annotations

import json

import frappe
from frappe import _

from approval_hub_frappe.services.pending_engine import PendingApprovalEngine
from approval_hub_frappe.services.workflow_service import apply_workflow_action
from approval_hub_frappe.utils.config_utils import get_active_doctype_configs, get_config_for_doctype
from approval_hub_frappe.utils.permission_utils import can_user_approve_document
from approval_hub_frappe.utils.settings_utils import get_approval_hub_settings


def _parse_filters(filters):
    if isinstance(filters, str):
        return json.loads(filters) if filters else {}
    return filters or {}


def _validate_doc_ref(doctype: str, docname: str) -> None:
    if not doctype or not docname:
        frappe.throw(_("doctype and docname are required."), frappe.ValidationError)
    if not frappe.db.exists("DocType", doctype):
        frappe.throw(_("Invalid doctype."), frappe.ValidationError)
    if not frappe.db.exists(doctype, docname):
        frappe.throw(_("Document not found."), frappe.DoesNotExistError)


@frappe.whitelist()
def get_pending_approvals(filters=None, start=0, page_length=20, page=None, page_size=None):
    settings = get_approval_hub_settings()
    if not settings.get("enabled"):
        frappe.throw(_("Approval Hub is currently disabled."), frappe.ValidationError)

    safe_filters = _parse_filters(filters)

    if page is not None:
        safe_page_size = int(page_size or page_length or settings.get("default_page_size") or 20)
        safe_start = max(0, (int(page) - 1) * safe_page_size)
        safe_page_length = safe_page_size
    else:
        safe_start = int(start or 0)
        safe_page_length = int(page_size or page_length or settings.get("default_page_size") or 20)

    engine = PendingApprovalEngine(user=frappe.session.user, settings=settings, filters=safe_filters)
    return engine.get_pending(start=safe_start, page_length=safe_page_length)


@frappe.whitelist()
def get_approval_summary(filters=None):
    settings = get_approval_hub_settings()
    if not settings.get("enabled"):
        return {
            "total_pending": 0,
            "critical": 0,
            "warning": 0,
            "normal": 0,
            "my_available_actions": 0,
            "oldest_pending": 0,
            "by_doctype": {},
            "by_branch": {},
            "by_state": {},
        }

    safe_filters = _parse_filters(filters)
    engine = PendingApprovalEngine(user=frappe.session.user, settings=settings, filters=safe_filters)
    return engine.get_summary()


@frappe.whitelist()
def check_can_approve(doctype, docname):
    _validate_doc_ref(doctype, docname)
    config = get_config_for_doctype(doctype)
    settings = get_approval_hub_settings()
    return can_user_approve_document(
        doctype=doctype,
        docname=docname,
        user=frappe.session.user,
        config=config,
        settings=settings,
    )


@frappe.whitelist()
def apply_workflow_action_from_hub(doctype, docname, action, remarks=None):
    _validate_doc_ref(doctype, docname)
    if not action:
        frappe.throw(_("Action is required."), frappe.ValidationError)

    settings = get_approval_hub_settings()
    if not settings.get("enabled"):
        frappe.throw(_("Approval Hub is currently disabled."), frappe.ValidationError)

    can_do = check_can_approve(doctype, docname)
    if action not in (can_do.get("allowed_actions") or []):
        frappe.throw(_("You cannot perform this action."), frappe.PermissionError)

    result = apply_workflow_action(
        doctype=doctype,
        docname=docname,
        action=action,
        user=frappe.session.user,
        remarks=remarks,
        settings=settings,
    )

    engine = PendingApprovalEngine(user=frappe.session.user, settings=settings, filters={})
    summary = engine.get_summary()
    return {
        "success": bool(result.get("success")),
        "message": result.get("message") or _("Action applied."),
        "new_state": result.get("new_state"),
        "refresh_needed": True,
        "summary": summary,
    }


@frappe.whitelist()
def get_page_context():
    settings = get_approval_hub_settings()
    if not settings.get("enabled"):
        return {"enabled": False, "message": _("Approval Hub is currently disabled.")}

    configs = get_active_doctype_configs(for_pending=True)
    engine = PendingApprovalEngine(user=frappe.session.user, settings=settings, filters={})
    summary = engine.get_summary()

    branches = sorted(k for k in summary.get("by_branch", {}).keys() if k and k != "Unspecified")
    workflow_states = sorted(summary.get("by_state", {}).keys())

    return {
        "enabled": True,
        "settings": settings,
        "configs": [{"value": c["doctype_name"], "label": c.get("label") or c["doctype_name"]} for c in configs],
        "branches": branches,
        "workflow_states": workflow_states,
        "summary": summary,
    }
