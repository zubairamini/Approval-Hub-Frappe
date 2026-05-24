"""Settings helpers for Approval Hub."""

from __future__ import annotations

import frappe
from frappe.utils import cint

_SETTINGS_CACHE_KEY = "approval_hub_settings_cache"

_DEFAULTS = {
    "enabled": 0,
    "respect_user_permissions": 1,
    "respect_branch_permissions": 0,
    "allow_system_manager_override": 1,
    "aging_warning_days": 3,
    "aging_critical_days": 7,
    "default_page_size": 20,
}


def get_approval_hub_settings(use_cache: bool = True) -> dict:
    """Return settings dict with schema-safe fallbacks."""
    if use_cache and hasattr(frappe.local, _SETTINGS_CACHE_KEY):
        return getattr(frappe.local, _SETTINGS_CACHE_KEY)

    settings = dict(_DEFAULTS)

    if not frappe.db.exists("DocType", "Approval Hub Settings"):
        _cache_settings(settings)
        return settings

    try:
        meta = frappe.get_meta("Approval Hub Settings")
        cols = set(meta.get_valid_columns())
        row = frappe.db.get_value("Approval Hub Settings", "Approval Hub Settings", "*", as_dict=True) or {}
    except Exception:
        _cache_settings(settings)
        return settings

    int_fields = [
        "enabled",
        "respect_user_permissions",
        "respect_branch_permissions",
        "allow_system_manager_override",
        "aging_warning_days",
        "aging_critical_days",
        "default_page_size",
    ]

    for fieldname in int_fields:
        if fieldname in cols and fieldname in row:
            settings[fieldname] = cint(row.get(fieldname))

    settings["enabled"] = 1 if settings["enabled"] else 0
    settings["respect_user_permissions"] = 1 if settings["respect_user_permissions"] else 0
    settings["respect_branch_permissions"] = 1 if settings["respect_branch_permissions"] else 0
    settings["allow_system_manager_override"] = 1 if settings["allow_system_manager_override"] else 0
    settings["aging_warning_days"] = max(0, settings["aging_warning_days"] or _DEFAULTS["aging_warning_days"])
    settings["aging_critical_days"] = max(settings["aging_warning_days"] + 1, settings["aging_critical_days"] or _DEFAULTS["aging_critical_days"])
    settings["default_page_size"] = min(500, max(1, settings["default_page_size"] or _DEFAULTS["default_page_size"]))

    _cache_settings(settings)
    return settings


def _cache_settings(settings: dict) -> None:
    setattr(frappe.local, _SETTINGS_CACHE_KEY, settings)
