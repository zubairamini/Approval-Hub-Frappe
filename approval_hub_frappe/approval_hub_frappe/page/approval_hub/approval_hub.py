"""
approval_hub_frappe/page/approval_hub/approval_hub.py

Frappe Desk page controller for the Approval Hub page.
Methods here are called directly by the page JS via frappe.call.
"""

import frappe
from frappe import _

# Re-export API methods so they can be called as
#   frappe.call("approval_hub_frappe.page.approval_hub.approval_hub.<method>")
# OR via the cleaner api module path.

from approval_hub_frappe.api.approval_hub import (  # noqa: F401
    get_settings,
    get_doctype_configs,
    get_pending_approvals,
    get_approval_summary,
    get_branches,
    check_can_approve,
    apply_workflow_action_from_hub,
)


@frappe.whitelist()
def get_page_context():
    """
    Return all initial data needed to bootstrap the page in one round-trip:
    - settings
    - doctype_configs (for the doctype filter dropdown)
    - summary counts
    - user_branches (for the branch filter dropdown)
    """
    from approval_hub_frappe.utils.settings_utils import get_approval_hub_settings
    from approval_hub_frappe.utils.config_utils import get_active_doctype_configs
    from approval_hub_frappe.utils.permission_utils import get_user_allowed_branches

    settings = get_approval_hub_settings()

    if not settings.get("enabled"):
        return {
            "enabled": False,
            "message": _("Approval Hub is currently disabled. Please contact your system administrator."),
        }

    configs = get_active_doctype_configs(for_pending=True)
    branches = get_user_allowed_branches(frappe.session.user)

    from approval_hub_frappe.services.pending_engine import PendingApprovalEngine
    engine = PendingApprovalEngine(
        user=frappe.session.user,
        settings=settings,
        filters={},
    )
    summary = engine.get_summary()

    return {
        "enabled": True,
        "settings": settings,
        "configs": [
            {"value": c["doctype_name"], "label": c.get("label") or c["doctype_name"]}
            for c in configs
        ],
        "branches": branches,
        "summary": summary,
    }