"""
approval_hub_frappe/services/workflow_service.py

Workflow-aware helpers:
- Detect workflow attached to a doctype
- Determine current document workflow state
- Determine allowed transitions for the current user by role
- Apply workflow actions safely
"""

import frappe
from frappe import _
from frappe.model.workflow import (
    get_workflow_name,
    apply_workflow,
)


# ---------------------------------------------------------------------------
# Workflow detection
# ---------------------------------------------------------------------------

def get_workflow_for_doctype(doctype: str) -> str | None:
    """Return the active workflow name for a doctype, or None."""
    try:
        wf_name = get_workflow_name(doctype)
    except (frappe.DoesNotExistError, frappe.ValidationError):
        return None
    return wf_name or None


def get_workflow_doc(doctype: str):
    """Return the Workflow document object, or None."""
    wf_name = get_workflow_for_doctype(doctype)
    if not wf_name:
        return None
    try:
        return frappe.get_doc("Workflow", wf_name)
    except (frappe.DoesNotExistError, frappe.ValidationError):
        return None


def doctype_has_workflow(doctype: str) -> bool:
    """Return True if the doctype has an active workflow attached."""
    return bool(get_workflow_for_doctype(doctype))


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def get_workflow_state(doctype: str, docname: str, workflow_state_field: str = "workflow_state") -> str | None:
    """
    Return the current workflow state of a document.
    Uses the mapped workflow_state_field if provided, falls back to
    'workflow_state' (Frappe default).
    """
    field = workflow_state_field or "workflow_state"
    try:
        return frappe.db.get_value(doctype, docname, field)
    except (frappe.DoesNotExistError, frappe.ValidationError):
        return None


# ---------------------------------------------------------------------------
# Transition helpers
# ---------------------------------------------------------------------------

def get_allowed_transitions(doctype: str, current_state: str, user_roles: list[str]) -> list[dict]:
    """
    Return list of workflow transitions the user is allowed to take
    from the given state.

    Each item: {"action": str, "next_state": str, "allowed_roles": list[str]}
    """
    wf_doc = get_workflow_doc(doctype)
    if not wf_doc:
        return []

    allowed = []
    for transition in wf_doc.transitions:
        if transition.state != current_state:
            continue
        # Check if user has any of the allowed roles for this transition
        allowed_roles = [r.strip() for r in (transition.allowed or "").split(",") if r.strip()]
        if not allowed_roles:
            # No role restriction – everyone can take this action
            allowed.append({
                "action": transition.action,
                "next_state": transition.next_state,
                "allowed_roles": [],
            })
        elif any(role in user_roles for role in allowed_roles):
            allowed.append({
                "action": transition.action,
                "next_state": transition.next_state,
                "allowed_roles": allowed_roles,
            })

    return allowed


def get_allowed_actions_for_user(
    doctype: str,
    docname: str,
    user: str,
    workflow_state_field: str = None,
    override: bool = False,
) -> list[str]:
    """
    Return the list of action names the user can take on a document.

    :param override: If True (System Manager override), return ALL available
                     actions for the current state regardless of role.
    """
    wf_doc = get_workflow_doc(doctype)
    if not wf_doc:
        return []

    wf_state_field = workflow_state_field or wf_doc.workflow_state_field or "workflow_state"
    current_state = get_workflow_state(doctype, docname, wf_state_field)
    if not current_state:
        return []

    if override:
        # Return all actions from this state
        return [
            t.action
            for t in wf_doc.transitions
            if t.state == current_state
        ]

    user_roles = frappe.get_roles(user)
    transitions = get_allowed_transitions(doctype, current_state, user_roles)
    return [t["action"] for t in transitions]


# ---------------------------------------------------------------------------
# Apply workflow action
# ---------------------------------------------------------------------------

def apply_workflow_action(
    doctype: str,
    docname: str,
    action: str,
    user: str,
    remarks: str = None,
    settings: dict = None,
) -> dict:
    """
    Apply a workflow transition action on a document.

    Returns:
        {"success": bool, "new_state": str, "message": str}
    """
    from approval_hub_frappe.services.log_service import create_approval_hub_log
    from approval_hub_frappe.utils.config_utils import get_config_for_doctype

    config = get_config_for_doctype(doctype)
    wf_doc = get_workflow_doc(doctype)

    if not wf_doc:
        frappe.throw(_("No active workflow found for {0}.").format(doctype))

    wf_state_field = wf_doc.workflow_state_field or "workflow_state"
    from_state = get_workflow_state(doctype, docname, wf_state_field)

    # Verify the user can take this action
    allowed_actions = get_allowed_actions_for_user(doctype, docname, user, wf_state_field)

    if settings and settings.get("allow_system_manager_override"):
        from approval_hub_frappe.utils.permission_utils import is_system_manager
        if is_system_manager(user):
            # Override: allow all actions from this state
            allowed_actions = get_allowed_actions_for_user(
                doctype, docname, user, wf_state_field, override=True
            )

    if action not in allowed_actions:
        frappe.throw(
            _("Action '{0}' is not permitted for you on this document.").format(action),
            frappe.PermissionError,
        )

    # Apply the workflow transition via Frappe's built-in method
    doc = frappe.get_doc(doctype, docname)

    # Frappe's apply_workflow needs the action to be set on the doc
    doc.workflow_action = action  # some versions use this attribute
    try:
        apply_workflow(doc, action)
        comment = _("Action '{0}' applied from Approval Hub.").format(action)
        if remarks:
            comment = f"{comment} {remarks}"
        doc.add_comment("Workflow", comment)
        doc.save(ignore_permissions=False)
    except (frappe.ValidationError, frappe.PermissionError) as e:
        frappe.log_error(frappe.get_traceback(), "Approval Hub - apply_workflow error")
        frappe.throw(_("Failed to apply workflow action: {0}").format(str(e)))

    new_state = get_workflow_state(doctype, docname, wf_state_field)

    # Log the action
    if config and config.get("track_history"):
        create_approval_hub_log(
            doc=doc,
            config=config,
            action=action,
            from_state=from_state,
            to_state=new_state,
            remarks=remarks,
        )

    return {
        "success": True,
        "new_state": new_state,
        "message": _("Action '{0}' applied successfully. New state: {1}").format(action, new_state),
    }
