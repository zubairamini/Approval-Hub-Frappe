import json
import frappe
from frappe import _
from approval_hub_frappe.services.pending_engine import PendingApprovalEngine
from approval_hub_frappe.services.workflow_service import apply_workflow_action
from approval_hub_frappe.utils.permission_utils import can_user_approve_document
from approval_hub_frappe.utils.settings_utils import get_approval_hub_settings
from approval_hub_frappe.utils.config_utils import get_active_doctype_configs, get_config_for_doctype


def _parse_filters(filters):
    if isinstance(filters, str):
        return json.loads(filters) if filters else {}
    return filters or {}


@frappe.whitelist()
def get_pending_approvals(filters=None, start=0, page_length=20, page=None, page_size=None):
    filters = _parse_filters(filters)
    settings = get_approval_hub_settings()
    if not settings.get("enabled"):
        frappe.throw(_("Approval Hub is currently disabled."), frappe.ValidationError)

    if page is None:
        page_length = int(page_size or page_length or settings.get("default_page_size") or 20)
        start = int(start or 0)
        page = (start // page_length) + 1
    else:
        page = int(page)
        page_length = int(page_size or page_length or settings.get("default_page_size") or 20)

    engine = PendingApprovalEngine(user=frappe.session.user, settings=settings, filters=filters)
    return engine.get_pending(page=page, page_size=page_length)


@frappe.whitelist()
def get_approval_summary(filters=None):
    filters = _parse_filters(filters)
    settings = get_approval_hub_settings()
    if not settings.get("enabled"):
        return {"total_pending": 0, "critical": 0, "warning": 0, "normal": 0, "by_doctype": {}}
    engine = PendingApprovalEngine(user=frappe.session.user, settings=settings, filters=filters)
    return engine.get_summary()


@frappe.whitelist()
def check_can_approve(doctype, docname):
    config = get_config_for_doctype(doctype)
    settings = get_approval_hub_settings()
    return can_user_approve_document(doctype, docname, frappe.session.user, config=config, settings=settings)


@frappe.whitelist()
def apply_workflow_action_from_hub(doctype, docname, action, remarks=None):
    settings = get_approval_hub_settings()
    if not settings.get("enabled"):
        frappe.throw(_("Approval Hub is currently disabled."))
    can_do = check_can_approve(doctype, docname)
    if action not in (can_do.get("allowed_actions") or []):
        frappe.throw(_("You cannot perform this action."), frappe.PermissionError)
    return apply_workflow_action(doctype=doctype, docname=docname, action=action, user=frappe.session.user, remarks=remarks, settings=settings)


@frappe.whitelist()
def get_page_context():
    settings = get_approval_hub_settings()
    if not settings.get("enabled"):
        return {"enabled": False, "message": _("Approval Hub is currently disabled.")}
    configs = get_active_doctype_configs(for_pending=True)
    engine = PendingApprovalEngine(user=frappe.session.user, settings=settings, filters={})
    return {
        "enabled": True,
        "settings": settings,
        "configs": [{"value": c["doctype_name"], "label": c.get("label") or c["doctype_name"]} for c in configs],
        "summary": engine.get_summary(),
    }
