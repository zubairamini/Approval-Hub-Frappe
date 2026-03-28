"""
approval_hub_frappe/utils/permission_utils.py

Helper functions for user role, branch, and document-level permission checks
used throughout the Approval Hub engine.
"""

import frappe
from frappe import _
from frappe.utils import cint


# ---------------------------------------------------------------------------
# Role helpers
# ---------------------------------------------------------------------------

def get_current_user_roles(user: str = None) -> list[str]:
    """Return list of role names assigned to the user."""
    user = user or frappe.session.user
    return frappe.get_roles(user)


def is_system_manager(user: str = None) -> bool:
    user = user or frappe.session.user
    return "System Manager" in get_current_user_roles(user)


# ---------------------------------------------------------------------------
# Branch helpers
# ---------------------------------------------------------------------------

def get_user_allowed_branches(user: str = None) -> list[str]:
    """
    Return branch names the user is permitted to access.

    Strategy (in priority order):
    1. If user has System Manager role (and override is not being suppressed
       externally), return [] meaning "all branches".
    2. Look up User Permission records for 'Branch' doctype.
    3. Return a deduplicated list.

    Returns an empty list to signal "no branch restriction" (all branches
    allowed) only when the user has no Branch user-permissions set.
    Callers must distinguish between [] = "unrestricted" and a populated
    list = "restricted to these branches".
    """
    user = user or frappe.session.user

    branch_permissions = frappe.get_all(
        "User Permission",
        filters={"user": user, "allow": "Branch"},
        fields=["for_value"],
        ignore_permissions=True,
    )

    branches = [p["for_value"] for p in branch_permissions if p.get("for_value")]
    return branches


def has_branch_access(user: str, branch: str, settings: dict = None) -> bool:
    """
    Return True if user is allowed to access the given branch.

    - If respect_branch_permissions is off in settings, always return True.
    - If branch is blank/None, return True (unset branch = not restricted).
    - System Manager override: if allow_system_manager_override, always True.
    """
    if not branch:
        return True

    if settings is None:
        from approval_hub_frappe.utils.settings_utils import get_approval_hub_settings
        settings = get_approval_hub_settings()

    if not settings.get("respect_branch_permissions"):
        return True

    if settings.get("allow_system_manager_override") and is_system_manager(user):
        return True

    allowed = get_user_allowed_branches(user)
    # Empty allowed list means the user has no branch restrictions → full access
    if not allowed:
        return True

    return branch in allowed


def resolve_branch_value(doc_dict: dict, config: dict) -> str | None:
    """
    Resolve the branch value from the document according to the config's
    branch_resolution_mode.

    - Direct Field: read the mapped field directly.
    - Linked Field: read field, then follow a link (future – v1 reads directly).
    - Expression: hook point for custom apps (v1 reads directly).
    """
    branch_field = config.get("branch_field")
    if not branch_field:
        return None

    mode = config.get("branch_resolution_mode", "Direct Field")

    if mode == "Direct Field":
        return doc_dict.get(branch_field)

    elif mode == "Linked Field":
        # v1: treat same as Direct Field. Future: traverse link chain.
        return doc_dict.get(branch_field)

    elif mode == "Expression":
        # Hook for custom resolution. Fall back to direct field.
        hook_method = frappe.get_hooks("approval_hub_branch_resolver")
        if hook_method:
            try:
                return frappe.get_attr(hook_method[-1])(doc_dict, config)
            except Exception:
                frappe.log_error("Custom branch resolver failed", "Approval Hub")
        return doc_dict.get(branch_field)

    return doc_dict.get(branch_field)


# ---------------------------------------------------------------------------
# Document access helpers
# ---------------------------------------------------------------------------

def has_document_access(user: str, doctype: str, docname: str) -> bool:
    """Check if user has at minimum 'read' permission on the document."""
    try:
        return frappe.has_permission(doctype, "read", docname, user=user)
    except Exception:
        return False


def can_user_approve_document(
    doctype: str,
    docname: str,
    user: str = None,
    config: dict = None,
    settings: dict = None,
) -> dict:
    """
    Determine if a user can take a workflow action on a document.

    Returns:
        {
            "can_approve": bool,
            "allowed_actions": list[str],
            "reason": str,
        }
    """
    from approval_hub_frappe.services.workflow_service import (
        get_allowed_actions_for_user,
        get_workflow_state,
    )

    user = user or frappe.session.user

    if settings is None:
        from approval_hub_frappe.utils.settings_utils import get_approval_hub_settings
        settings = get_approval_hub_settings()

    # System Manager override
    if settings.get("allow_system_manager_override") and is_system_manager(user):
        actions = get_allowed_actions_for_user(doctype, docname, user, override=True)
        return {
            "can_approve": bool(actions),
            "allowed_actions": actions,
            "reason": "system_manager_override" if actions else "no_workflow_actions",
        }

    # Standard permission check
    if settings.get("respect_user_permissions"):
        if not has_document_access(user, doctype, docname):
            return {
                "can_approve": False,
                "allowed_actions": [],
                "reason": "no_read_permission",
            }

    # Branch permission check
    if settings.get("respect_branch_permissions") and config:
        try:
            doc_dict = frappe.db.get_value(
                doctype,
                docname,
                "*",
                as_dict=True,
            ) or {}
            branch = resolve_branch_value(doc_dict, config)
            if not has_branch_access(user, branch, settings):
                return {
                    "can_approve": False,
                    "allowed_actions": [],
                    "reason": "branch_not_allowed",
                }
        except Exception:
            pass

    actions = get_allowed_actions_for_user(doctype, docname, user)
    return {
        "can_approve": bool(actions),
        "allowed_actions": actions,
        "reason": "ok" if actions else "no_workflow_actions",
    }