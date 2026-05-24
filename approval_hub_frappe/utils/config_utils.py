"""Config helpers for Approval Hub."""

from __future__ import annotations

import json

import frappe
from frappe.utils import cint


def get_active_doctype_configs(for_pending: bool = True, for_dashboard: bool = False) -> list[dict]:
    """Return active, schema-safe config rows."""
    if not frappe.db.exists("DocType", "Approval Hub Doctype Config"):
        return []

    meta = frappe.get_meta("Approval Hub Doctype Config")
    existing_columns = set(meta.get_valid_columns())

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
    select_fields = [f for f in requested_fields if f in existing_columns]

    filters = {"is_active": 1}
    if for_pending and "track_pending" in existing_columns:
        filters["track_pending"] = 1
    if for_dashboard and "show_in_dashboard" in existing_columns:
        filters["show_in_dashboard"] = 1

    order_by = "creation asc"
    if "sequence" in existing_columns:
        order_by = "sequence asc, creation asc"

    rows = frappe.get_all(
        "Approval Hub Doctype Config",
        filters=filters,
        fields=select_fields,
        order_by=order_by,
        limit_page_length=0,
    )

    out = []
    for row in rows:
        parsed = _parse_config_row(row)
        if not parsed.get("doctype_name"):
            continue
        if not frappe.db.exists("DocType", parsed["doctype_name"]):
            continue
        out.append(parsed)
    return out


def get_config_for_doctype(doctype_name: str) -> dict | None:
    for config in get_active_doctype_configs(for_pending=False):
        if config.get("doctype_name") == doctype_name:
            return config
    return None


def validate_config_field_mapping(config: dict, source_meta) -> dict:
    """Keep only mapped fields that exist on source doctype."""
    valid_columns = set(source_meta.get_valid_columns())
    mapped = [
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
    ]

    safe = dict(config)
    for key in mapped:
        value = safe.get(key)
        if value and value not in valid_columns:
            safe[key] = None

    return safe


def _parse_config_row(config: dict) -> dict:
    config = dict(config)
    raw = config.get("base_filters_json") or ""
    if raw:
        try:
            parsed = json.loads(raw)
            config["base_filters"] = parsed if isinstance(parsed, dict) else {}
        except Exception:
            frappe.log_error(
                f"Invalid base_filters_json on Approval Hub Doctype Config: {config.get('name')}",
                "Approval Hub Config Parse Error",
            )
            config["base_filters"] = {}
    else:
        config["base_filters"] = {}

    for field in [
        "is_active",
        "workflow_required",
        "track_pending",
        "track_history",
        "show_in_dashboard",
        "allow_quick_action",
        "enable_overdue_tracking",
    ]:
        config[field] = bool(cint(config.get(field)))

    config["sla_days"] = max(0, cint(config.get("sla_days") or 0))
    config.setdefault("label", config.get("doctype_name"))
    config.setdefault("permission_mode", "Standard")
    config.setdefault("branch_resolution_mode", "Direct Field")
    return config
