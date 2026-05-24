"""
approval_hub_frappe/utils/config_utils.py

Helpers for loading and interpreting Approval Hub Doctype Config records.
"""

import json
import frappe
from frappe import _
from frappe.utils import cint


def get_active_doctype_configs(for_pending=True, for_dashboard=False) -> list[dict]:
    """
    Return active Approval Hub Doctype Config records as list of dicts.

    :param for_pending:   If True, only configs with track_pending = 1
    :param for_dashboard: If True, only configs with show_in_dashboard = 1
    """
    filters = {"is_active": 1}
    if for_pending:
        filters["track_pending"] = 1
    if for_dashboard:
        filters["show_in_dashboard"] = 1

    requested_fields = [
        "name",
        "doctype_name",
        "is_active",
        "sequence",
        "module",
        "label",
        "description",
        "workflow_required",
        "track_pending",
        "track_history",
        "show_in_dashboard",
        "allow_quick_action",
        "enable_overdue_tracking",
        "sla_days",
        "branch_field",
        "department_field",
        "company_field",
        "requester_field",
        "owner_field",
        "title_field",
        "amount_field",
        "date_field",
        "priority_field",
        "status_field",
        "workflow_state_field",
        "assigned_to_field",
        "employee_field",
        "base_filters_json",
        "permission_mode",
        "branch_resolution_mode",
    ]

    # Keep queries compatible with instances where the DocType schema
    # has not yet been migrated to include all optional fields.
    meta = frappe.get_meta("Approval Hub Doctype Config")
    existing_fields = set(meta.get_valid_columns())
    fields_to_select = [f for f in requested_fields if f in existing_fields]

    configs = frappe.get_all(
        "Approval Hub Doctype Config",
        filters=filters,
        fields=fields_to_select,
        order_by="sequence asc, creation asc",
    )

    result = []
    for config in configs:
        config = _parse_config(config)
        result.append(config)

    return result


def _parse_config(config: dict) -> dict:
    """Parse JSON fields and normalise types."""
    # Parse base_filters_json safely
    raw_filters = config.get("base_filters_json") or ""
    if raw_filters:
        try:
            config["base_filters"] = json.loads(raw_filters)
        except (ValueError, TypeError):
            frappe.log_error(
                f"Invalid base_filters_json on Approval Hub Doctype Config: {config.get('name')}",
                "Approval Hub Config Parse Error",
            )
            config["base_filters"] = {}
    else:
        config["base_filters"] = {}

    # Coerce boolean-like int fields
    bool_fields = [
        "workflow_required", "track_pending", "track_history",
        "show_in_dashboard", "allow_quick_action", "enable_overdue_tracking",
    ]
    for f in bool_fields:
        config[f] = bool(cint(config.get(f)))

    # Defaults for permission / branch modes
    config.setdefault("permission_mode", "Standard")
    config.setdefault("branch_resolution_mode", "Direct Field")

    return config


def get_config_for_doctype(doctype_name: str) -> dict | None:
    """Return the active config for a specific doctype, or None."""
    configs = get_active_doctype_configs(for_pending=False)
    for config in configs:
        if config["doctype_name"] == doctype_name:
            return config
    return None
