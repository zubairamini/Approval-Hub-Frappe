"""
approval_hub_frappe/utils/settings_utils.py

Helpers for loading and interpreting Approval Hub Settings.
"""

import frappe
from frappe.utils import cint


_SETTINGS_CACHE_KEY = "approval_hub_settings_cache"


def get_approval_hub_settings(use_cache=True) -> dict:
    """
    Load the Approval Hub Settings singleton and return as a plain dict.
    Caches within the current request.
    """
    # Use Frappe's local request cache to avoid repeated DB hits
    if use_cache and hasattr(frappe.local, _SETTINGS_CACHE_KEY):
        return getattr(frappe.local, _SETTINGS_CACHE_KEY)

    try:
        settings_doc = frappe.get_single("Approval Hub Settings")
    except Exception:
        # Settings not yet configured – return safe defaults
        defaults = _default_settings()
        _cache_settings(defaults)
        return defaults

    settings = {
        "enabled": cint(settings_doc.enabled),
        "respect_user_permissions": cint(settings_doc.respect_user_permissions),
        "respect_branch_permissions": cint(settings_doc.respect_branch_permissions),
        "allow_system_manager_override": cint(settings_doc.allow_system_manager_override),
        "aging_warning_days": cint(settings_doc.aging_warning_days) or 3,
        "aging_critical_days": cint(settings_doc.aging_critical_days) or 7,
        "default_page_size": cint(settings_doc.default_page_size) or 20,
    }

    _cache_settings(settings)
    return settings


def _cache_settings(settings: dict):
    setattr(frappe.local, _SETTINGS_CACHE_KEY, settings)


def _default_settings() -> dict:
    return {
        "enabled": 0,
        "respect_user_permissions": 1,
        "respect_branch_permissions": 0,
        "allow_system_manager_override": 1,
        "aging_warning_days": 3,
        "aging_critical_days": 7,
        "default_page_size": 20,
    }