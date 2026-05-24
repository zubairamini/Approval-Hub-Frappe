"""Permission and approval helpers."""

from __future__ import annotations

import frappe


FINAL_STATE_KEYWORDS = {
    "approved",
    "rejected",
    "cancelled",
    "canceled",
    "completed",
    "closed",
    "final",
    "submitted",
    "kept",
}


def get_current_user_roles(user: str | None = None) -> list[str]:
    user = user or frappe.session.user
    return frappe.get_roles(user)


def is_system_manager(user: str | None = None) -> bool:
    return "System Manager" in get_current_user_roles(user)


def system_manager_override_applies(user: str, settings: dict | None = None) -> bool:
    if not settings:
        return False
    return bool(settings.get("allow_system_manager_override") and is_system_manager(user))


def has_document_access(user: str, doctype: str, docname: str) -> bool:
    try:
        return bool(frappe.has_permission(doctype=doctype, ptype="read", doc=docname, user=user))
    except Exception:
        return False


def get_user_allowed_branches(user: str | None = None) -> list[str]:
    user = user or frappe.session.user
    if not frappe.db.exists("DocType", "User Permission"):
        return []

    rows = frappe.get_all(
        "User Permission",
        filters={"user": user, "allow": "Branch"},
        fields=["for_value"],
        ignore_permissions=True,
    )
    branches = []
    for row in rows:
        value = row.get("for_value")
        if value and value not in branches:
            branches.append(value)
    return branches


def has_branch_access(user: str, branch: str | None, settings: dict | None = None) -> bool:
    if not settings or not settings.get("respect_branch_permissions"):
        return True
    if not branch:
        return True
    if system_manager_override_applies(user, settings):
        return True

    allowed = get_user_allowed_branches(user)
    if not allowed:
        return True
    return branch in allowed


def resolve_branch_value(doc_dict: dict, config: dict) -> str | None:
    branch_field = config.get("branch_field")
    if not branch_field:
        return None

    mode = config.get("branch_resolution_mode") or "Direct Field"
    if mode == "Expression":
        resolver_hooks = frappe.get_hooks("approval_hub_branch_resolver") or []
        if resolver_hooks:
            try:
                return frappe.get_attr(resolver_hooks[-1])(doc_dict, config)
            except Exception:
                frappe.log_error(frappe.get_traceback(), "Approval Hub Branch Resolver Error")

    return doc_dict.get(branch_field)


def state_looks_final(state: str | None) -> bool:
    if not state:
        return False
    low = state.lower()
    return any(key in low for key in FINAL_STATE_KEYWORDS)


def can_user_approve_document(
    doctype: str,
    docname: str,
    user: str | None = None,
    config: dict | None = None,
    settings: dict | None = None,
) -> dict:
    from approval_hub_frappe.services.workflow_service import get_allowed_actions_for_user

    user = user or frappe.session.user

    if settings and settings.get("respect_user_permissions") and not has_document_access(user, doctype, docname):
        return {"can_approve": False, "allowed_actions": [], "reason": "no_read_permission"}

    if config and settings and settings.get("respect_branch_permissions"):
        doc = frappe.db.get_value(doctype, docname, "*", as_dict=True) or {}
        if not has_branch_access(user, resolve_branch_value(doc, config), settings):
            return {"can_approve": False, "allowed_actions": [], "reason": "branch_not_allowed"}

    actions = get_allowed_actions_for_user(
        doctype=doctype,
        docname=docname,
        user=user,
        workflow_state_field=(config or {}).get("workflow_state_field"),
        override=system_manager_override_applies(user, settings),
    )
    if not actions:
        return {"can_approve": False, "allowed_actions": [], "reason": "no_workflow_actions"}

    return {"can_approve": True, "allowed_actions": actions, "reason": "ok"}
